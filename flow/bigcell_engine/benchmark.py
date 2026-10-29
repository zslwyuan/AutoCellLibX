"""Width/checker benchmark: bigcell engine vs the ASTRAN baseline
(stage 3, doc/STAGE3_BIGCELL_ENGINE.md section 4).

Fixed benchmark set: the ASTRAN baseline cell decks
(``BENCHMARK_GLOBS``), the mined COMPLEX cells, and the standard-cell
LIBRARY cells (``LIBRARY_SOURCES`` -- one BenchmarkCell per .subckt
block of ``std_celllib/cellsAstranFriendly.sp``, the gates the Python
ladder closes).  Per-cell record: device count, ASTRAN width, Python
width, producing engine, verify/layout-sanity verdicts **plus a quality
panel** (pin accessibility on the engine's own GDS, the layout-sanity
metrics dict, per-layer polygon counts, and per-cell runtime aggregated
from the engine's meta attempts).  Reports are written as JSON +
markdown.  This is the continuous-verification backbone for the ASTRAN
replacement -- every engine change re-runs it.

Measurement discipline (doc section 4 + AGENTS.md invariants):

- **width** is the nominal cell width in um on the fixed H = 2.47 um row
  height on BOTH sides (invariants 1/10): ASTRAN widths come from the
  existing ``.Astranlog`` "Cell Size (W x H)" lines (or a fresh run into
  a scratch dir, cached in ``_stage3_check/astran_baseline.json``), the
  engine's from its column count x the 0.19 um grid.
- **artifact cache** (invariant 7): the benchmark writes ``<cell>.sp``
  only when its content changed (so the mtime stays a usable freshness
  signal) and regenerates ``<cell>.gds`` when it is missing or older
  than its ``.sp``; with ``resume=True`` a fresh pair skips synthesis
  and is re-checked from the artifact instead.
- **honesty**: a cell ASTRAN cannot lay out (no log width, lint failure,
  0 x 0 result) is reported as missing/failed, never dropped; an engine
  failure is reported with its diagnosis (which rung, why).
- **determinism**: cell order, records and reports are deterministic
  functions of the benchmark set (sorted iteration everywhere); no
  timestamps enter the reports.
"""

import glob
import json
import os
import re
import statistics
from dataclasses import dataclass

from smt_cell_placer import astran_width_from_log, parse_spice_subckt
from smt_engine.netlist import CellNetlist
from smt_engine.verify import verify_cell

from .engine import GRID_UM, UnsupportedCell, synth_cell
from . import gds_cells

BENCHMARK_GLOBS = ("original_astran_cells/*.sp", "outputs/*/*.sp")

#: Multi-subckt library decks: one BenchmarkCell per .subckt block, in
#: file order.  Each block is reported under a VIRTUAL flow-relative
#: source ``<LIBRARY_SOURCE_DIR>/<name>.sp``: the real deck sits OUTSIDE
#: the flow directory (``../std_celllib/``), and a source that escapes
#: the flow dir would make run_benchmark's artifact tree (built by
#: joining ``out_dir`` with the source) write outside ``out_dir``.  The
#: virtual source keeps every downstream path join (.sp/.gds artifacts,
#: work dirs) inside the benchmark's own tree; the real file is wired by
#: name below.
LIBRARY_SOURCES = ("../std_celllib/cellsAstranFriendly.sp",)
LIBRARY_SOURCE_DIR = "library"

#: Where the library cells' ASTRAN baseline logs live.  The baselines
#: were run from cellsAstranFriendly.sp directly (each
#: ``original_astran_cells/<name>.Astranlog`` records "Loading cells
#: netlist from file: ../stdCelllib/cellsAstranFriendly.sp"), so there
#: is no per-cell .sp deck next to them -- the wired directory is the
#: only place a library baseline can be found.
LIBRARY_LOG_DIR = "original_astran_cells"

#: scratch area (git-ignored by convention) for the baseline cache, the
#: per-cell ASTRAN work dirs and benchmark artifacts.
STAGE3_CHECK_DIR = "_stage3_check"
BASELINE_CACHE_NAME = "astran_baseline.json"
BASELINE_WORK_SUBDIR = "work"

HEIGHT_UM = 2.47                  # matched row height (invariant 10)
ASTRAN_LOG_SUFFIX = ".Astranlog"

_LOG_TCOUNT_RE = re.compile(
    r"Number of transistors before folding:\s*(\d+)")


@dataclass
class BenchmarkCell:
    """One benchmark cell: identity + parsed netlist + raw deck text.

    ``name`` (the subckt name) is NOT unique across the benchmark set --
    COMPLEX ids are per-run assignments (AGENTS.md invariant 6), so the
    same name can denote different patterns in different outputs dirs.
    ``source`` (the flow-relative posix path of the .sp) is the unique
    key; reports carry both.  Library subckts carry the virtual
    ``library/<name>.sp`` source (see LIBRARY_SOURCES).

    ``log_dir`` is an optional flow-relative directory holding the
    cell's ``<name>.Astranlog`` when that log is NOT a sibling of the
    .sp (library cells: LIBRARY_LOG_DIR -- their baseline logs sit next
    to the baseline decks, not next to any per-cell .sp).  ``None``
    keeps the historical log-next-to-the-.sp resolution only.
    """

    name: str
    source: str
    netlist: CellNetlist
    transistors: int
    text: str
    log_dir: str = None


_SUBCKT_START_RE = re.compile(r"^[ \t]*\.subckt\b.*$", re.IGNORECASE
                              | re.MULTILINE)
_ENDS_RE = re.compile(r"^[ \t]*\.ends\b.*$", re.IGNORECASE | re.MULTILINE)


def _iter_subckt_blocks(text):
    """The .subckt ... .ends blocks of a deck, in file order.

    ``parse_spice_subckt`` reads the FIRST .subckt header of its input
    but every MOS line of the WHOLE text, so a multi-subckt deck must be
    split before it is parsed: a whole-file parse would attribute every
    device of the file to the first block.  Each block spans its .subckt
    line through the .ends line (missing .ends: through the next .subckt
    or EOF) -- devices outside any block are never picked up.
    """
    starts = [m.start() for m in _SUBCKT_START_RE.finditer(text)]
    for i, start in enumerate(starts):
        limit = starts[i + 1] if (i + 1 < len(starts)) else len(text)
        end = limit
        m = _ENDS_RE.search(text, start, limit)
        if (m):
            end = m.end()
        yield text[start:end]


def _parse_or_none(text):
    """parse_spice_subckt with OSError folded away (no deck, no cell)."""
    try:
        return parse_spice_subckt(text)
    except ValueError:
        return None


def load_benchmark_cells(flow_dir=None):
    """Return the sorted, de-duplicated benchmark cell list.

    Walks BENCHMARK_GLOBS relative to ``flow_dir`` (default: the flow
    directory this package lives in) and parses every .subckt with
    ``parse_spice_subckt``; then splits each LIBRARY_SOURCES deck into
    per-subckt blocks and yields one BenchmarkCell per parseable block
    under its virtual ``library/<name>.sp`` source.  Returns everything
    sorted by (name, source).

    De-duplication is by source path (the unique key -- names collide
    across benchmarks, invariant 6); a duplicated subckt name inside one
    library deck keeps the FIRST occurrence (file order).  Decks or
    blocks the shared parser cannot read are skipped: the benchmark
    benchmarks cells, not the parser.

    Name overlap between the baseline decks (``original_astran_cells/``)
    and the library is resolved by baseline availability: when a
    same-named baseline .sp has its .Astranlog as a true sibling, its
    record wins and the library record is dropped; otherwise both
    sources are kept as distinct records.
    """
    if (flow_dir is None):
        flow_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    seen = set()
    cells = []

    def _add(source, text, parsed, log_dir=None):
        # unique by source; keep the first occurrence (deterministic)
        if (parsed is None or source in seen):
            return
        seen.add(source)
        cells.append(BenchmarkCell(
            name=parsed.subckt_name, source=source,
            netlist=CellNetlist(parsed), transistors=len(parsed.devices),
            text=text, log_dir=log_dir))

    for pattern in BENCHMARK_GLOBS:
        for path in sorted(glob.glob(os.path.join(flow_dir, pattern))):
            rel = os.path.relpath(path, flow_dir).replace(os.sep, "/")
            if (rel in seen):
                continue
            try:
                with open(path, "r", errors="replace", newline="") as fh:
                    text = fh.read()
            except OSError:
                continue
            _add(rel, text, _parse_or_none(text))
    for lib_rel in LIBRARY_SOURCES:
        path = os.path.join(flow_dir, lib_rel)
        try:
            with open(path, "r", errors="replace", newline="") as fh:
                text = fh.read()
        except OSError:
            continue
        for block in _iter_subckt_blocks(text):
            parsed = _parse_or_none(block)
            if (parsed is None):
                continue
            _add("%s/%s.sp" % (LIBRARY_SOURCE_DIR, parsed.subckt_name),
                 block, parsed, log_dir=LIBRARY_LOG_DIR)
    cells = _prefer_logged_baseline(cells, flow_dir)
    cells.sort(key=lambda c: (c.name, c.source))
    return cells


def _prefer_logged_baseline(cells, flow_dir):
    """Same-named original_astran_cells / library records: keep one.

    The baseline decks and the library describe the SAME gates.  When a
    baseline deck's own .Astranlog exists next to it (baseline
    availability, i.e. an ASTRAN log that needs no directory wiring),
    its record wins and the same-named library record is dropped; when
    it does not, both records stay (name+source is the identity).  Only
    this pair of source families is name-deduped: outputs/* COMPLEX ids
    are per-run (invariant 6) -- a same-named outputs cell is a
    different pattern and is never collapsed against the library.
    """
    logged = set()
    for c in cells:
        if (not (c.source.startswith("original_astran_cells/")
                 and c.source.endswith(".sp"))):
            continue
        stem = c.source[:-3]
        if (os.path.basename(stem) != c.name):
            continue                    # log is named after the deck
        if (os.path.exists(os.path.join(flow_dir,
                                        stem + ASTRAN_LOG_SUFFIX))):
            logged.add(c.name)
    if (not logged):
        return cells
    return [c for c in cells
            if not (c.source.startswith(LIBRARY_SOURCE_DIR + "/")
                    and c.name in logged)]


def baseline_cache_path(flow_dir=None):
    """Path of the ASTRAN baseline width cache (created on first save)."""
    if (flow_dir is None):
        flow_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(flow_dir, STAGE3_CHECK_DIR, BASELINE_CACHE_NAME)


def _log_transistor_count(log_path):
    """Transistor count the log's layout was built from, or None.

    The "Number of transistors before folding" line is the freshness
    check of AUDIT 5.6/5.37: a log whose count differs from the .sp's
    device count describes another netlist, and its width is rejected.
    """
    try:
        with open(log_path, "r", errors="ignore") as fh:
            for line in fh:
                m = _LOG_TCOUNT_RE.search(line)
                if (m):
                    return int(m.group(1))
    except OSError:
        return None
    return None


def _validate_log_width(log_path, transistors):
    """(width_um, note) from an .Astranlog, honestly validated.

    width is None when the log has no Cell Size line (a failed run) or
    when its transistor count contradicts the .sp (stale log).  A log
    without the transistor-count line is accepted but flagged -- width
    provenance must never be silently assumed.
    """
    width = astran_width_from_log(log_path)
    if (width is None):
        return None, "log present but has no Cell Size line"
    tcount = _log_transistor_count(log_path)
    if (tcount is not None and tcount != transistors):
        return None, ("log width %.2f rejected: log built from %d "
                      "transistors, .sp has %d" % (width, tcount,
                                                   transistors))
    if (tcount is None):
        return width, "accepted without transistor-count validation"
    return width, ""


def _default_astran_runner(sp_path, work_dir, cell_name):
    """Run one cell through ASTRAN with its OWN work dir.

    The LP model/solution are written relative to the process cwd, so
    every cell gets ``work_dir`` as both cwd and command_dir (the
    astran_queue discipline; two ASTRAN runs must never share a cwd).
    """
    from astran import (ASTRAN_BUILD_PATH, ASTRAN_TECHNOLOGY, GUROBI_CL,
                        run_astran_for_netlist)
    run_astran_for_netlist(
        astran_path=ASTRAN_BUILD_PATH, gurobi_path=GUROBI_CL,
        technology_path=ASTRAN_TECHNOLOGY, spice_netlist_path=sp_path,
        complex_name=cell_name, command_dir=work_dir, work_dir=work_dir)


def _load_cache(cache_path):
    if (os.path.exists(cache_path)):
        try:
            with open(cache_path, "r") as fh:
                data = json.load(fh)
            if (isinstance(data, dict) and isinstance(data.get("cells"),
                                                      dict)):
                return data
        except (OSError, ValueError):
            pass
    return {"version": 1, "cells": {}}


def _save_cache(cache_path, data):
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    tmp = cache_path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
    os.replace(tmp, cache_path)


def get_astran_baselines(cells, cache_path=None, allow_runs=False,
                         astran_runner=None, flow_dir=None):
    """ASTRAN baseline widths for the cells: {source: entry}.

    Entry: {name, transistors, width_um (None when ASTRAN cannot lay the
    cell out), origin ("cache" | "log" | "run" | "missing" | "failed"),
    note}.  Resolution order per cell:

    1. a valid cache entry (same transistor count) -- origin "cache";
    2. the .Astranlog next to the .sp -- or, when the cell wires one
       (``log_dir``, library cells), ``<log_dir>/<name>.Astranlog`` --
       width validated against the log's transistor count (stale logs
       are rejected, not used);
    3. only with ``allow_runs``: a fresh ASTRAN run into a per-cell
       work dir under ``_stage3_check/work/<source>/`` (never a shared
       cwd), linted first, result parsed from the run's log and cached.

    A missing/failed baseline is reported as width None with a note --
    the report marks it, it is never silently dropped.  Cache entries
    persist both widths and determinate failures (lint reject, run
    without a Cell Size line); a crashed run is not cached so the next
    run retries it.
    """
    if (flow_dir is None):
        flow_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if (cache_path is None):
        cache_path = baseline_cache_path(flow_dir)
    if (astran_runner is None):
        astran_runner = _default_astran_runner

    cache = _load_cache(cache_path)
    result = {}
    dirty = False
    for cell in cells:
        entry = None
        cached = cache["cells"].get(cell.source)
        if (cached is not None and cached.get("transistors") == cell.transistors):
            entry = dict(cached)
            entry["origin"] = "cache"
        if (entry is None):
            log_path = os.path.join(
                flow_dir, (cell.source[:-3] + ASTRAN_LOG_SUFFIX)
                if cell.source.endswith(".sp") else
                (cell.source + ASTRAN_LOG_SUFFIX))
            if (not os.path.exists(log_path) and cell.log_dir):
                # wired baseline directory: library subckts have no
                # per-cell .sp deck, their logs live with the baseline
                # decks (see LIBRARY_LOG_DIR)
                log_path = os.path.join(flow_dir, cell.log_dir,
                                        cell.name + ASTRAN_LOG_SUFFIX)
            if (os.path.exists(log_path)):
                width, note = _validate_log_width(log_path, cell.transistors)
                entry = {"name": cell.name,
                         "transistors": cell.transistors,
                         "width_um": width,
                         "origin": "log" if width is not None else "missing",
                         "note": note}
                cache["cells"][cell.source] = dict(entry)
                dirty = True
            elif (allow_runs):
                entry = _run_baseline(cell, flow_dir, astran_runner)
                if (entry["origin"] in ("run", "failed")):
                    cache["cells"][cell.source] = dict(entry)
                    dirty = True
            else:
                note = "no .Astranlog next to the .sp"
                if (cell.log_dir):
                    note += " or in %s" % cell.log_dir
                entry = {"name": cell.name,
                         "transistors": cell.transistors,
                         "width_um": None, "origin": "missing",
                         "note": note + " (allow_runs=False)"}
        result[cell.source] = entry
    if (dirty):
        _save_cache(cache_path, cache)
    return result


def _run_baseline(cell, flow_dir, astran_runner):
    """One fresh ASTRAN baseline run in a per-cell work dir."""
    from astran_lint import errors as lint_errors
    from astran_lint import lint_netlist

    stem = cell.source[:-3] if cell.source.endswith(".sp") else cell.source
    work_dir = os.path.join(flow_dir, STAGE3_CHECK_DIR,
                            BASELINE_WORK_SUBDIR, *stem.split("/"))
    os.makedirs(work_dir, exist_ok=True)
    sp_path = os.path.join(flow_dir, cell.source)
    if (not os.path.exists(sp_path)):
        # virtual source (library subckt, see LIBRARY_SOURCES): there is
        # no on-disk deck to point ASTRAN at -- materialize the cell's
        # own block text in the per-cell work dir instead of writing
        # anywhere near the real library file
        sp_path = os.path.join(work_dir, cell.name + ".sp")
        _write_if_changed(sp_path, cell.text)
    lint = lint_netlist(sp_path)
    errs = lint_errors(lint)
    if (errs):
        return {"name": cell.name, "transistors": cell.transistors,
                "width_um": None, "origin": "failed",
                "note": "ASTRAN lint rejected the netlist (%d errors)" %
                        len(errs)}
    try:
        astran_runner(sp_path, work_dir, cell.name)
    except Exception as exc:                       # noqa: BLE001
        # a crashed run is transient: report it, cache nothing
        return {"name": cell.name, "transistors": cell.transistors,
                "width_um": None, "origin": "missing",
                "note": "ASTRAN run raised %s: %s" % (
                    type(exc).__name__, exc)}
    log_path = os.path.join(work_dir, cell.name + ASTRAN_LOG_SUFFIX)
    width, note = _validate_log_width(log_path, cell.transistors)
    return {"name": cell.name, "transistors": cell.transistors,
            "width_um": width,
            "origin": "run" if width is not None else "failed",
            "note": (note or "fresh ASTRAN run") if width is not None
            else (note or "run produced no Cell Size (0x0 / failed?)")}


def _write_if_changed(path, text):
    """Write only when the content differs (invariant 7: the .sp mtime
    must stay a usable freshness signal).  Returns True when written."""
    if (os.path.exists(path)):
        try:
            with open(path, "r", errors="replace", newline="") as fh:
                if (fh.read() == text):
                    return False
        except OSError:
            pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as fh:
        fh.write(text)
    return True


def _default_sanity_checker(gds_path):
    """layout_sanity.check_layout on the engine's own GDS.

    The smt_engine GDS writer is honest (1 um user units -- no ASTRAN
    bogus-UNITS calibration), hence units_per_um=1.0, the same call the
    queue's SMT path makes.  Standalone: reads the GDS with gdstk, no
    GUI or log context needed.
    """
    from layout_sanity import check_layout
    return check_layout(gds_path, units_per_um=1.0,
                        expected_height_um=HEIGHT_UM, grid_um=GRID_UM)


# --- quality panel: pin access, layer counts, runtime ----------------------

#: the engines whose width is drawn in ASTRAN's own slot semantics (W
#: vertical, doc/BIGCELL_SLOT_GEOMETRY.md) -- only their python/astran
#: width ratios are same-semantics comparable.  ``bigcell-grid`` /
#: ``smt-exact`` cells keep the exact IR's placement (W drawn as
#: horizontal columns), so their ratios overstate width.
SAME_SEMANTICS_ENGINES = ("bigcell-full", "bigcell-full+window-fix")


def _default_pin_access_scorer(gds_path):
    """Pin accessibility of a produced cell, via flow/pin_accessibility.

    The engine's GDS carries pin labels on metal1 (stream 49) and an
    honest 1 um header, so no log calibration is needed: the score is
    the mean per-pin score in [0, 1] (0.5 on-track + 0.5 not blocked,
    -0.1 per crowd up to 3 -- see pin_accessibility.py).  Returns a
    compact summary {score, n_pins, on_track, blocked, crowded_pins};
    None when the GDS cannot be read (the record then carries the
    error note instead of a fabricated score).
    """
    from pin_accessibility import cell_pin_accessibility
    rep = cell_pin_accessibility(gds_path, grid_um=GRID_UM)
    pins = rep.pins
    return {
        "score": round(rep.score, 3),
        "n_pins": len(pins),
        "on_track": sum(1 for p in pins if p["on_track"]),
        "blocked": sum(1 for p in pins if p["blocked"]),
        "crowded_pins": sum(1 for p in pins if p["crowd"]),
    }


def _layer_counts(gds_path):
    """Per-stream polygon counts of the produced GDS (sorted str keys).

    The DRC-quality signal beyond sanity ok/not: which layers the cell
    actually drew and how dense each is (poly stripes, contacts, M1
    segments, M2 jumps).  None when the file is unreadable -- never a
    made-up histogram.
    """
    import gdstk
    lib = gdstk.read_gds(gds_path)
    counts = {}
    for cell in lib.top_level() or lib.cells:
        for poly in cell.polygons:
            key = str(poly.layer)
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items())) or None


def runtime_from_attempts(attempts):
    """Per-cell runtime seconds aggregated from the engine's meta attempts.

    Every attempt carries rounded wall seconds (engine.py ``_attempt``);
    this splits them the way the ladder spends them: ``place`` (the
    layout/routing-solve *placement* stages), ``route`` (router stages
    plus the stageless rung-2 router call) and ``window`` (the window
    fixer's attempts, which carry a ``window``).  ``total`` is the sum
    of everything -- the honest wall-clock cost of the cell, ladder
    retries included.  Pure function of the attempts list.
    """
    total = place = route = window = 0.0
    for a in (attempts or []):
        s = a.get("seconds")
        if (not isinstance(s, (int, float))):
            continue
        total += s
        if ("window" in a):
            window += s
        elif (a.get("stage") in ("layout", "placement")):
            place += s
        else:
            route += s
    return {"total": round(total, 1), "place": round(place, 1),
            "route": round(route, 1), "window": round(window, 1)}


def _percentile(values, q):
    """Linear-interpolation percentile (numpy's default method).

    Deterministic, dependency-free; ``values`` must be pre-sorted.
    """
    if (not values):
        return None
    if (len(values) == 1):
        return values[0]
    pos = (len(values) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(values) - 1)
    frac = pos - lo
    return values[lo] + (values[hi] - values[lo]) * frac


def _quality_panel(gds_path, sanity_report, attempts,
                   pin_access_scorer=None):
    """The per-cell quality panel: pin access + sanity metrics + layers
    + runtime.  Every component degrades to None (with the error kept
    as a note) instead of being invented -- a panel entry that is
    missing says the measurement failed, not that the quality is good.
    """
    panel = {"pin_access": None, "sanity_metrics": None,
             "layer_counts": None, "runtime_s": None}
    if (pin_access_scorer is not None):
        try:
            panel["pin_access"] = pin_access_scorer(gds_path)
        except Exception as exc:                   # noqa: BLE001
            panel["pin_access"] = {"score": None, "n_pins": None,
                                   "note": "pin access raised %s: %s" % (
                                       type(exc).__name__, exc)}
    if (sanity_report is not None):
        metrics = getattr(sanity_report, "metrics", None)
        if (isinstance(metrics, dict)):
            panel["sanity_metrics"] = dict(
                (k, v) for k, v in sorted(metrics.items()))
    try:
        panel["layer_counts"] = _layer_counts(gds_path)
    except Exception:                              # noqa: BLE001
        panel["layer_counts"] = None
    if (attempts is not None):
        panel["runtime_s"] = runtime_from_attempts(attempts)
    return panel


def _verdict(report, note=None):
    """Normalize a report-like (VerifyReport / LayoutSanityReport)."""
    if (report is None):
        return {"ok": None, "note": note}
    out = {"ok": bool(report.ok()),
           "violations": [list(v) if isinstance(v, tuple) else v
                          for v in getattr(report, "violations", [])]}
    if (note):
        out["note"] = note
    return out


def _fmt_um(value):
    return ("%.2f" % value) if isinstance(value, (int, float)) else "-"


def run_benchmark(cells, out_dir, exact_budget_s=60.0, grid_budget_s=120.0,
                  grid_router=None, resume=True, baselines=None,
                  allow_baseline_runs=False, synth_runner=None,
                  gds_writer=None, verify_fn=None, sanity_checker=None,
                  pin_access_scorer=None, flow_dir=None):
    """Run the engine over ``cells`` and write report.json + report.md.

    Per cell: synthesize (``synth_runner``, default
    :func:`bigcell_engine.engine.synth_cell`), write ``<source>.sp`` /
    ``<source>.gds`` under ``out_dir`` honouring the cache contract
    (invariant 7), verify structurally (``verify_fn``) and on the
    artifact (``sanity_checker``, default layout_sanity.check_layout --
    standalone, no GUI/log context needed), and record
    {name, T, astran_um, python_um, engine, verdicts, quality, ...}.
    The quality panel (``_quality_panel``) carries the per-closed-cell
    pin accessibility (``pin_access_scorer``, default
    :func:`_default_pin_access_scorer` on flow/pin_accessibility; False
    disables it), the sanity metrics dict, per-layer polygon counts and
    the runtime split place/route/window aggregated from the meta
    attempts.  A resumed (cached) cell carries its width/engine/verify
    verdict (and its measured runtime) from the previous
    ``out_dir/report.json`` and re-runs only the artifact checks.

    ``baselines`` injects a precomputed {source: entry} mapping; by
    default :func:`get_astran_baselines` runs with the persistent cache
    (``allow_baseline_runs`` gates fresh ASTRAN runs -- off by default
    so a benchmark pass is CI-safe; without a log the baseline is an
    honest "missing").

    Returns the report dict {summary, cells}; the same content lands in
    ``report.json`` (sorted keys, no timestamps) and ``report.md``.
    """
    if (flow_dir is None):
        flow_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if (synth_runner is None):
        synth_runner = synth_cell
    if (gds_writer is None):
        from smt_engine.gds import write_cell_gds
        gds_writer = write_cell_gds
    if (verify_fn is None):
        verify_fn = verify_cell
    if (sanity_checker is None):
        sanity_checker = _default_sanity_checker
    if (pin_access_scorer is None):
        pin_access_scorer = _default_pin_access_scorer
    if (baselines is None):
        baselines = get_astran_baselines(cells, allow_runs=allow_baseline_runs,
                                         flow_dir=flow_dir)

    ordered = sorted(cells, key=lambda c: (c.name, c.source))
    os.makedirs(out_dir, exist_ok=True)
    # the previous report is the per-cell sidecar: a resumed (cached)
    # cell carries its synthesized width / engine / verify verdict from
    # it instead of re-deriving a width from the GDS bounding box
    prev = {}
    prev_path = os.path.join(out_dir, "report.json")
    if (resume and os.path.exists(prev_path)):
        try:
            with open(prev_path, "r") as fh:
                for r in json.load(fh).get("cells", []):
                    if (r.get("source")):
                        prev[r["source"]] = r
        except (OSError, ValueError):
            prev = {}
    records = []
    synth_calls = 0
    for cell in ordered:
        sp_path = os.path.join(out_dir, *cell.source.split("/"))
        gds_path = (sp_path[:-3] + ".gds") if sp_path.endswith(".sp") \
            else (sp_path + ".gds")
        record = {"name": cell.name, "source": cell.source,
                  "T": cell.transistors,
                  "astran_um": baselines.get(cell.source, {}).get("width_um"),
                  "python_um": None, "engine": None,
                  "verdicts": {}, "status": "error", "cached": False,
                  "note": ""}

        # --- artifacts: .sp content-only, .gds only when stale --------
        wrote_sp = _write_if_changed(sp_path, cell.text)
        fresh = (resume and not wrote_sp and os.path.exists(gds_path)
                 and os.path.getmtime(gds_path) >= os.path.getmtime(sp_path))
        if (fresh):
            record["status"] = "cached"
            record["cached"] = True
            old = prev.get(cell.source, {})
            record["python_um"] = old.get("python_um")
            record["engine"] = old.get("engine") or "bigcell (cached)"
            old_verify = (old.get("verdicts") or {}).get("verify") or {}
            record["verdicts"]["verify"] = {
                "ok": old_verify.get("ok"),
                "note": "carried from the previous report (cached "
                        "artifacts carry no placement/route)"}
            # provenance of the cached synthesis: the attempts (and the
            # runtime they encode) describe the artifacts on disk
            record["attempts"] = old.get("attempts") or []
            try:
                sanity = sanity_checker(gds_path)
            except Exception as exc:               # noqa: BLE001
                sanity = None
                record["verdicts"]["sanity"] = {
                    "ok": None, "note": "sanity raised %s: %s" % (
                        type(exc).__name__, exc)}
            else:
                record["verdicts"]["sanity"] = _verdict(sanity)
                if (record["python_um"] is None):
                    # no previous report: fall back to the artifact's
                    # measured M1 extent (includes the rail overhang)
                    record["python_um"] = getattr(
                        sanity, "metrics", {}).get("width_um")
            record["quality"] = _quality_panel(
                gds_path, sanity,
                record["attempts"] if record["attempts"] else None,
                pin_access_scorer=pin_access_scorer)
            record["note"] = "fresh artifact pair; synthesis skipped " \
                             "(invariant 7)"
            records.append(record)
            continue

        # --- synthesize ------------------------------------------------
        try:
            placement, route, meta = synth_runner(
                cell.netlist, exact_budget_s=exact_budget_s,
                grid_budget_s=grid_budget_s, grid_router=grid_router)
        except UnsupportedCell as exc:
            record["status"] = "unsupported"
            record["note"] = exc.diagnosis
            record["attempts"] = exc.meta.get("attempts", [])
            # a failed ladder run burns time too: the runtime of the
            # attempts is the honest cost of the "unsupported" verdict
            record["quality"] = {
                "pin_access": None, "sanity_metrics": None,
                "layer_counts": None,
                "runtime_s": runtime_from_attempts(
                    record["attempts"])}
            records.append(record)
            continue
        except Exception as exc:                   # noqa: BLE001
            record["note"] = "engine raised %s: %s" % (
                type(exc).__name__, exc)
            record["quality"] = {"pin_access": None, "sanity_metrics": None,
                                 "layer_counts": None, "runtime_s": None}
            records.append(record)
            continue
        synth_calls += 1

        # rung 3 places against the (possibly fold/tree-expanded) netlist:
        # the artifacts and verify must use the engine's own view.
        layout_nl = meta.get("cell_netlist") or cell.netlist
        layout_blocks = meta.get("blocks")
        vkw = {"blocks": layout_blocks} if layout_blocks is not None else {}
        # the seed capture's track domain (AUDIT 5.63): verify must speak
        # the vertical vocabulary the route was solved on
        se_dom = meta.get("slot_emit", {}).get("tracks")
        if (se_dom is not None and se_dom != "bar9"):
            vkw["tracks"] = se_dom

        os.makedirs(os.path.dirname(gds_path), exist_ok=True)
        if (meta.get("slot_emit") is not None):
            # slot-model cell: the ASTRAN-style emitter needs the
            # orderings + leg widths, not just the placement IR
            se = meta["slot_emit"]
            gds_cells.write_cell_gds(
                gds_path, layout_nl, placement, se["width_cols"],
                se["ordering_p"], se["ordering_n"], se["leg_widths"],
                route=route, tracks=se.get("tracks", "bar9"))
        else:
            gds_writer(gds_path, layout_nl, placement, route)
        try:
            record["verdicts"]["verify"] = _verdict(
                verify_fn(layout_nl, placement, route, **vkw))
        except Exception as exc:                   # noqa: BLE001
            record["verdicts"]["verify"] = {
                "ok": None,
                "note": "verify raised %s: %s" % (type(exc).__name__, exc)}
        sanity_report = None
        try:
            sanity_report = sanity_checker(gds_path)
            record["verdicts"]["sanity"] = _verdict(sanity_report)
        except Exception as exc:                   # noqa: BLE001
            record["verdicts"]["sanity"] = {
                "ok": None, "note": "sanity raised %s: %s" % (
                    type(exc).__name__, exc)}
        record["quality"] = _quality_panel(
            gds_path, sanity_report, meta.get("attempts", []),
            pin_access_scorer=pin_access_scorer)

        record["python_um"] = meta.get("width_um")
        if (record["python_um"] is None
                and getattr(route, "width_cols", None)):
            record["python_um"] = route.width_cols * GRID_UM
        record["engine"] = meta.get("engine")
        record["attempts"] = meta.get("attempts", [])
        record["status"] = "ok"
        records.append(record)

    summary = _summarize(records, baselines)
    report = {"summary": summary, "cells": records,
              "parameters": {"exact_budget_s": exact_budget_s,
                             "grid_budget_s": grid_budget_s,
                             "grid_router": bool(grid_router),
                             "resume": resume,
                             "row_height_um": HEIGHT_UM,
                             "grid_um": GRID_UM}}
    with open(os.path.join(out_dir, "report.json"), "w") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
    with open(os.path.join(out_dir, "report.md"), "w") as fh:
        fh.write(_render_markdown(report))
    return report


def _quality_summary(records):
    """The SUMMARY quality block over the per-cell records.

    - ``closure_rate``: ok+cached over all records (the ladder's honest
      hit rate, unsupported/errors included in the denominator);
    - ``ratio_same_semantics``: python/astran width ratios restricted to
      the slot-model engines (SAME_SEMANTICS_ENGINES) -- the only
      ratios that compare like-for-like against ASTRAN's slot geometry;
    - ``pin_access``: median mean-pin score over the closed cells that
      have one (n says how many did);
    - ``runtime_s``: p50/p90/max of the per-cell total runtime over ALL
      cells with a measured one -- closures AND honest failures (an
      unsupported cell burns real solver time; excluding it would
      understate the ladder's cost);
    - ``engine_mix``: which rung closed what (the ladder's histogram).

    Every statistic is a deterministic function of the records; n
    counts are carried next to the numbers so a median over 3 cells
    can never masquerade as a population statement.
    """
    closed = [r for r in records if r["status"] in ("ok", "cached")]
    mix = {}
    for r in closed:
        if (r.get("engine")):
            mix[r["engine"]] = mix.get(r["engine"], 0) + 1
    ratios = sorted(r["python_um"] / r["astran_um"] for r in closed
                    if (isinstance(r.get("astran_um"), (int, float))
                        and r["astran_um"]
                        and isinstance(r.get("python_um"), (int, float))
                        and r.get("engine") in SAME_SEMANTICS_ENGINES))
    scores = []
    for r in closed:
        pa = (r.get("quality") or {}).get("pin_access") or {}
        if (isinstance(pa.get("score"), (int, float))):
            scores.append(pa["score"])
    scores.sort()
    runtimes = []
    for r in records:
        rt = ((r.get("quality") or {}).get("runtime_s") or {})
        if (isinstance(rt.get("total"), (int, float))):
            runtimes.append(rt["total"])
    runtimes.sort()
    n_records = len(records)
    return {
        "closure_rate": round(len(closed) / n_records, 4) if n_records else None,
        "ratio_same_semantics": {
            "n": len(ratios),
            "median": round(statistics.median(ratios), 4) if ratios else None,
            "max": round(ratios[-1], 4) if ratios else None,
        },
        "pin_access": {
            "n": len(scores),
            "median": round(statistics.median(scores), 4) if scores else None,
        },
        "runtime_s": {
            "n": len(runtimes),
            "p50": round(_percentile(runtimes, 0.50), 1)
                if runtimes else None,
            "p90": round(_percentile(runtimes, 0.90), 1)
                if runtimes else None,
            "max": round(runtimes[-1], 1) if runtimes else None,
        },
        "engine_mix": dict(sorted(mix.items())),
    }


def _summarize(records, baselines):
    produced = [r for r in records if r["status"] in ("ok", "cached")
                and r["python_um"] is not None]
    ratios = sorted(r["python_um"] / r["astran_um"] for r in produced
                    if r["astran_um"])
    origins = {}
    for entry in baselines.values():
        origins[entry["origin"]] = origins.get(entry["origin"], 0) + 1
    verify_ok = sum(1 for r in records
                    if r["verdicts"].get("verify", {}).get("ok") is True)
    sanity_ok = sum(1 for r in records
                    if r["verdicts"].get("sanity", {}).get("ok") is True)
    return {
        "cells": len(records),
        "ok": sum(1 for r in records if r["status"] == "ok"),
        "cached": sum(1 for r in records if r["status"] == "cached"),
        "unsupported": sum(1 for r in records
                           if r["status"] == "unsupported"),
        "errors": sum(1 for r in records if r["status"] == "error"),
        "verified_ok": verify_ok,
        "sanity_ok": sanity_ok,
        "baselines": {
            "log": origins.get("log", 0),
            "cache": origins.get("cache", 0),
            "run": origins.get("run", 0),
            "missing_or_failed": origins.get("missing", 0)
            + origins.get("failed", 0),
        },
        "width_ratio_python_over_astran": {
            "n": len(ratios),
            "median": round(statistics.median(ratios), 4) if ratios else None,
            "worst": round(ratios[-1], 4) if ratios else None,
        },
        "quality": _quality_summary(records),
    }


def _render_markdown(report):
    summary = report["summary"]
    base = summary["baselines"]
    ratio = summary["width_ratio_python_over_astran"]
    quality = summary.get("quality") or {}
    q_ratio = quality.get("ratio_same_semantics") or {}
    q_pin = quality.get("pin_access") or {}
    q_run = quality.get("runtime_s") or {}
    mix = quality.get("engine_mix") or {}
    lines = [
        "# Big-cell benchmark (stage 3)",
        "",
        "Width = nominal cell width at the fixed H = %.2f um row height on "
        "both sides (AGENTS.md invariants 1/10); engine widths are columns "
        "x %.2f um grid." % (report["parameters"]["row_height_um"],
                             report["parameters"]["grid_um"]),
        "",
        "**Summary**: %d cells -- %d ok, %d cached, %d unsupported, "
        "%d errors; verify ok %d/%d produced; sanity ok %d/%d; ASTRAN "
        "baselines: %d from logs, %d cached, %d fresh runs, %d "
        "missing/failed; median width ratio python/astran %s (n=%d)." % (
            summary["cells"], summary["ok"], summary["cached"],
            summary["unsupported"], summary["errors"],
            summary["verified_ok"],
            summary["ok"] + summary["cached"], summary["sanity_ok"],
            summary["cells"], base["log"], base["cache"], base["run"],
            base["missing_or_failed"],
            _fmt_um(ratio["median"]) if ratio["median"] is not None
            else "n/a", ratio["n"]),
        "",
        "**Quality**: closure rate %s; same-semantics ratio (%s) median "
        "%s / max %s (n=%d); median pin access %s (n=%d); runtime p50 "
        "%s s, p90 %s s, max %s s (n=%d); engine mix: %s." % (
            ("%.0f%%" % (quality["closure_rate"] * 100))
            if quality.get("closure_rate") is not None else "n/a",
            ", ".join(SAME_SEMANTICS_ENGINES),
            _fmt_um(q_ratio.get("median")) if q_ratio.get("median")
            is not None else "n/a",
            _fmt_um(q_ratio.get("max")) if q_ratio.get("max")
            is not None else "n/a",
            q_ratio.get("n") or 0,
            ("%.3f" % q_pin["median"]) if q_pin.get("median") is not None
            else "n/a",
            q_pin.get("n") or 0,
            _fmt_um(q_run.get("p50")) if q_run.get("p50") is not None
            else "-",
            _fmt_um(q_run.get("p90")) if q_run.get("p90") is not None
            else "-",
            _fmt_um(q_run.get("max")) if q_run.get("max") is not None
            else "-",
            q_run.get("n") or 0,
            ", ".join("%s x%d" % kv for kv in sorted(mix.items()))
            or "none"),
        "",
        "Ratios are same-semantics comparable only for `bigcell-full` "
        "engines (slot model: W vertical, doc/BIGCELL_SLOT_GEOMETRY.md); "
        "`bigcell-grid` cells keep the exact engine's placement (W drawn "
        "as horizontal columns) and `smt-exact` cells likewise -- their "
        "ratios overstate width against ASTRAN's slot geometry. Pin "
        "access is the mean per-pin score of flow/pin_accessibility in "
        "[0, 1] (on-track, unblocked, uncrowded metal1 pins); runtime is "
        "the ladder's total wall seconds for the cell (place + route + "
        "window retries).",
        "",
        "| cell | source | T | astran um | python um | ratio | engine "
        "| verify | sanity | pin | run s | note |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in report["cells"]:
        both = (isinstance(r["python_um"], (int, float))
                and isinstance(r["astran_um"], (int, float))
                and r["astran_um"])
        ratio_txt = ("%.2f" % (r["python_um"] / r["astran_um"])
                     if both else "-")
        verify = r["verdicts"].get("verify", {})
        sanity = r["verdicts"].get("sanity", {})

        def _flag(v):
            if (v.get("ok") is True):
                return "ok"
            if (v.get("ok") is False):
                return "FAIL"
            return "n/a" if v.get("ok") is None else "-"

        quality = r.get("quality") or {}
        pin = (quality.get("pin_access") or {}).get("score")
        pin_txt = ("%.2f" % pin) if isinstance(pin, (int, float)) else "-"
        run_s = (quality.get("runtime_s") or {}).get("total")
        run_txt = ("%.0f" % run_s) if isinstance(run_s, (int, float)) \
            else "-"
        note = (r.get("note") or "")[:80]
        lines.append("| %s | %s | %d | %s | %s | %s | %s | %s | %s | %s "
                     "| %s | %s |"
                     % (r["name"], r["source"], r["T"],
                        _fmt_um(r["astran_um"]), _fmt_um(r["python_um"]),
                        ratio_txt, r.get("engine") or "-",
                        _flag(verify), _flag(sanity), pin_txt, run_txt,
                        note))
    return "\n".join(lines) + "\n"


# --- generalization: the hold-out evaluation -------------------------------

#: The committed hold-out set: fresh combinational Verilog modules the
#: ladder has never seen (they are NOT part of the 49-cell development
#: benchmark -- no deck, no log, no baseline), synthesized once into
#: ASTRAN-ready .sp decks by ``flow/_generalization/generate.py`` and
#: committed next to their sources.  Determinism: the modules are fixed
#: files, the decks are committed artifacts (yosys+abc is deterministic
#: for a fixed binary/liberty), nothing is generated at run time.
HOLDOUT_DIR = "_generalization"

#: (name, min_T, max_T) size bands of the generalization verdict --
#: transistor counts per flattened cell.
SIZE_BANDS = (("small", 1, 8), ("medium", 9, 16), ("large", 17, None))

#: The development-set report the hold-out closure rates are compared
#: against (49 cells; regenerate with run_benchmark over
#: load_benchmark_cells()).  Scratch location by convention -- when it
#: is absent the comparison degrades to an honest "dev rates unknown".
DEV_REPORT_PATH = os.path.join(STAGE3_CHECK_DIR, "bench_int7", "report.json")

#: A hold-out band within this many percentage points of the dev band
#: counts as "consistent" (closure-rate noise for n<=20 cells).
GENERALIZATION_TOLERANCE = 0.10


def size_band(transistors):
    """The SIZE_BANDS name of a transistor count (None when it fits none)."""
    for name, lo, hi in SIZE_BANDS:
        if (transistors >= lo and (hi is None or transistors <= hi)):
            return name
    return None


def load_holdout_cells(flow_dir=None):
    """The committed hold-out cells, sorted by (name, source).

    One BenchmarkCell per ``<HOLDOUT_DIR>/*.sp`` deck -- the same
    identity rule as the development set (source is the unique key;
    the subckt name is the cell name).  A deck the shared parser
    cannot read is skipped: the hold-out set holds cells, not parser
    fixtures.
    """
    if (flow_dir is None):
        flow_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cells = []
    for path in sorted(glob.glob(os.path.join(flow_dir, HOLDOUT_DIR,
                                              "*.sp"))):
        rel = os.path.relpath(path, flow_dir).replace(os.sep, "/")
        try:
            with open(path, "r", errors="replace", newline="") as fh:
                text = fh.read()
        except OSError:
            continue
        parsed = _parse_or_none(text)
        if (parsed is None):
            continue
        cells.append(BenchmarkCell(
            name=parsed.subckt_name, source=rel,
            netlist=CellNetlist(parsed), transistors=len(parsed.devices),
            text=text))
    cells.sort(key=lambda c: (c.name, c.source))
    return cells


def band_closure(records):
    """Per-band closure over report cell records.

    {band: {"cells": n, "closed": k, "rate": r}}; a band with no cells
    carries rate None (never a fabricated 0%).  Closure is status
    ok/cached -- the same definition the summary uses.
    """
    out = {}
    for name, lo, hi in SIZE_BANDS:
        band = [r for r in records
                if (isinstance(r.get("T"), int) and r["T"] >= lo
                    and (hi is None or r["T"] <= hi))]
        closed = [r for r in band if r["status"] in ("ok", "cached")]
        out[name] = {"cells": len(band), "closed": len(closed),
                     "rate": (round(len(closed) / len(band), 4)
                              if band else None)}
    return out


def generalization_verdict(holdout_bands, dev_bands,
                           tolerance=GENERALIZATION_TOLERANCE):
    """The honest one-line verdict from the per-band closure rates.

    Compares every band that has hold-out cells AND dev cells; the
    verdict follows the WORST band (a single dropped band is an overfit
    signal even when the others hold).  Returns (verdict, worst) where
    worst is (band, delta_rate) or None when no band is comparable --
    the caller reports that as "dev rates unknown", never as success.
    """
    worst = None
    for name, _lo, _hi in SIZE_BANDS:
        h = (holdout_bands or {}).get(name) or {}
        d = (dev_bands or {}).get(name) or {}
        if (not h.get("cells") or not d.get("cells")):
            continue
        delta = h["rate"] - d["rate"]
        if (worst is None or delta < worst[1]):
            worst = (name, delta)
    if (worst is None):
        return ("no comparable band (development-set rates unavailable)",
                None)
    band, delta = worst
    if (delta >= -tolerance):
        return ("consistent with the development set (worst band %s at "
                "%+.0f pp)" % (band, delta * 100), worst)
    return ("closure drops on the hold-out set (worst band %s at %+.0f "
            "pp) -- an overfit signal" % (band, delta * 100), worst)


def run_generalization(out_dir, dev_report=None, cells=None,
                       exact_budget_s=60.0, grid_budget_s=120.0,
                       flow_dir=None, **kwargs):
    """Run the ladder over the committed hold-out set; write the report.

    The hold-out cells go through :func:`run_benchmark` unchanged (the
    same ladder, the same verify/sanity/quality gates) with NO ASTRAN
    baselines -- these cells have no .Astranlog and none is generated,
    so the deliverable is the closure rate and, where the ladder
    closes, the quality panel; where it fails, the per-cell diagnosis
    (which rung, why -- the note carried verbatim into the report).

    ``dev_report`` (a report dict, a {"cells": [...]} mapping, or a
    path to a report.json; default: DEV_REPORT_PATH when it exists)
    supplies the development-set band rates the verdict compares
    against; without it the comparison degrades to an honest "unknown".

    Writes ``generalization.json`` + ``generalization.md`` next to
    run_benchmark's own report files and returns
    {holdout, bands, dev_bands, dev_source, verdict, worst_band}.
    """
    if (flow_dir is None):
        flow_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if (cells is None):
        cells = load_holdout_cells(flow_dir)
    if (not cells):
        raise RuntimeError("no hold-out cells under %s (expected the "
                           "committed decks next to their .v sources)"
                           % HOLDOUT_DIR)

    report = run_benchmark(cells, out_dir, exact_budget_s=exact_budget_s,
                           grid_budget_s=grid_budget_s, flow_dir=flow_dir,
                           **kwargs)
    bands = band_closure(report["cells"])

    dev_bands = None
    dev_source = None
    dev_records = _dev_records(dev_report, flow_dir)
    if (dev_records is not None):
        dev_bands = band_closure(dev_records)
        dev_source = (dev_report if isinstance(dev_report, str)
                      else ("injected" if dev_report is not None
                            else DEV_REPORT_PATH))
    verdict, worst = generalization_verdict(bands, dev_bands)

    result = {"holdout": report, "bands": bands, "dev_bands": dev_bands,
              "dev_source": dev_source, "verdict": verdict,
              "worst_band": list(worst) if worst else None,
              "parameters": {"size_bands": [
                  [n, lo, hi] for n, lo, hi in SIZE_BANDS],
                  "tolerance": GENERALIZATION_TOLERANCE,
                  "holdout_dir": HOLDOUT_DIR}}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "generalization.json"), "w") as fh:
        json.dump(result, fh, indent=2, sort_keys=True)
    with open(os.path.join(out_dir, "generalization.md"), "w") as fh:
        fh.write(_render_generalization_markdown(result))
    return result


def _dev_records(dev_report, flow_dir):
    """Development-set cell records from a report (dict/path), or None.

    Accepts a report dict, a {"cells": [...]} mapping or a JSON path;
    the default (dev_report=None) reads DEV_REPORT_PATH when present.
    Anything unreadable degrades to None -- the generalization report
    then says "dev rates unknown" instead of inventing a comparison.
    """
    data = dev_report
    if (data is None):
        path = os.path.join(flow_dir, DEV_REPORT_PATH)
        if (not os.path.exists(path)):
            return None
        data = path
    if (isinstance(data, str)):
        try:
            with open(data, "r") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return None
    if (isinstance(data, dict)):
        records = data.get("cells")
        if (isinstance(records, list) and records
                and all(isinstance(r, dict) for r in records)):
            return records
    return None


def _render_generalization_markdown(result):
    """The hold-out report: per-cell table, per-band comparison, verdict."""
    report = result["holdout"]
    bands = result["bands"]
    dev_bands = result["dev_bands"]
    quality = report["summary"].get("quality") or {}
    lines = [
        "# Generalization: the hold-out evaluation",
        "",
        "%d committed hold-out cells (%s/*.sp, synthesized from fresh "
        "Verilog the ladder has never seen; no ASTRAN baselines exist). "
        "Closure = the Python ladder alone; every failure keeps its "
        "structural diagnosis." % (report["summary"]["cells"], HOLDOUT_DIR),
        "",
        "**Verdict**: %s." % result["verdict"],
        "",
        "| band | T range | cells | closed | rate | dev rate | delta |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, lo, hi in SIZE_BANDS:
        b = bands.get(name) or {}
        d = (dev_bands or {}).get(name) or {}
        dev_txt = ("%.0f%%" % (d["rate"] * 100)) if d.get("rate") is not \
            None else "unknown"
        if (b.get("rate") is not None and d.get("rate") is not None):
            delta = "%+.0f pp" % ((b["rate"] - d["rate"]) * 100)
        else:
            delta = "-"
        trange = "%d-%s" % (lo, "inf" if hi is None else hi)
        rate = ("%.0f%%" % (b["rate"] * 100)) if b.get("rate") is not \
            None else "-"
        lines.append("| %s | %s | %d | %d | %s | %s | %s |"
                     % (name, trange, b.get("cells", 0),
                        b.get("closed", 0), rate, dev_txt, delta))
    q_pin = quality.get("pin_access") or {}
    q_run = quality.get("runtime_s") or {}
    mix = quality.get("engine_mix") or {}
    lines += [
        "",
        "**Quality panel** (closed cells): engine mix %s; median pin "
        "access %s (n=%d); runtime p50 %s s / p90 %s s / max %s s (n=%d). "
        "Width ratios vs ASTRAN: n/a on hold-out by design (no "
        "baselines exist for these cells)." % (
            ", ".join("%s x%d" % kv for kv in sorted(mix.items())) or "none",
            ("%.3f" % q_pin["median"]) if q_pin.get("median") is not None
            else "n/a", q_pin.get("n") or 0,
            _fmt_um(q_run.get("p50")) if q_run.get("p50") is not None
            else "-", _fmt_um(q_run.get("p90")) if q_run.get("p90")
            is not None else "-",
            _fmt_um(q_run.get("max")) if q_run.get("max") is not None
            else "-", q_run.get("n") or 0),
        "",
        "| cell | T | band | engine | closure | verify | sanity | um | "
        "pin | run s |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(report["cells"], key=lambda r: (r["T"], r["name"])):
        quality = r.get("quality") or {}
        pin = (quality.get("pin_access") or {}).get("score")
        run_s = (quality.get("runtime_s") or {}).get("total")
        closed = r["status"] in ("ok", "cached")
        verdicts = r.get("verdicts") or {}

        def _flag(v):
            if (v.get("ok") is True):
                return "ok"
            if (v.get("ok") is False):
                return "FAIL"
            return "n/a" if v.get("ok") is None else "-"

        lines.append(
            "| %s | %d | %s | %s | %s | %s | %s | %s | %s | %s |"
            % (r["name"], r["T"], size_band(r["T"]) or "-",
               r.get("engine") or "-",
               "closed" if closed else "OPEN (%s)" % r["status"],
               _flag(verdicts.get("verify", {})),
               _flag(verdicts.get("sanity", {})),
               _fmt_um(r.get("python_um")),
               ("%.2f" % pin) if isinstance(pin, (int, float)) else "-",
               ("%.0f" % run_s) if isinstance(run_s, (int, float))
               else "-"))
    if (dev_bands is None):
        lines += ["", "_Development-set rates unavailable (%s not found); "
                  "the comparison band is empty -- regenerate the 49-cell "
                  "report first._" % DEV_REPORT_PATH]
    lines += ["", "## Honest failure diagnoses", ""]
    for r in sorted(report["cells"], key=lambda r: (r["T"], r["name"])):
        if (r["status"] in ("ok", "cached")):
            continue
        note = (r.get("note") or "")[:300]
        lines.append("- **%s** (T=%d, %s): %s"
                     % (r["name"], r["T"], size_band(r["T"]) or "-",
                        note or r["status"]))
    return "\n".join(lines) + "\n"
