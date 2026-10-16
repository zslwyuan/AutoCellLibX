"""Width/checker benchmark: bigcell engine vs the ASTRAN baseline
(stage 3, doc/STAGE3_BIGCELL_ENGINE.md section 4).

Fixed benchmark set: the ASTRAN baseline cell decks
(``BENCHMARK_GLOBS``), the mined COMPLEX cells, and the standard-cell
LIBRARY cells (``LIBRARY_SOURCES`` -- one BenchmarkCell per .subckt
block of ``std_celllib/cellsAstranFriendly.sp``, the gates the Python
ladder closes).  Per-cell record: device count, ASTRAN width, Python
width, producing engine, verify/layout-sanity verdicts.  Reports are
written as JSON + markdown.  This is the continuous-verification
backbone for the ASTRAN replacement -- every engine change re-runs it.

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
                  flow_dir=None):
    """Run the engine over ``cells`` and write report.json + report.md.

    Per cell: synthesize (``synth_runner``, default
    :func:`bigcell_engine.engine.synth_cell`), write ``<source>.sp`` /
    ``<source>.gds`` under ``out_dir`` honouring the cache contract
    (invariant 7), verify structurally (``verify_fn``) and on the
    artifact (``sanity_checker``, default layout_sanity.check_layout --
    standalone, no GUI/log context needed), and record
    {name, T, astran_um, python_um, engine, verdicts, ...}.  A resumed
    (cached) cell carries its width/engine/verify verdict from the
    previous ``out_dir/report.json`` and re-runs only the artifact
    sanity check.

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
            try:
                sanity = sanity_checker(gds_path)
            except Exception as exc:               # noqa: BLE001
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
            records.append(record)
            continue
        except Exception as exc:                   # noqa: BLE001
            record["note"] = "engine raised %s: %s" % (
                type(exc).__name__, exc)
            records.append(record)
            continue
        synth_calls += 1

        # rung 3 places against the (possibly fold/tree-expanded) netlist:
        # the artifacts and verify must use the engine's own view.
        layout_nl = meta.get("cell_netlist") or cell.netlist
        layout_blocks = meta.get("blocks")
        vkw = {"blocks": layout_blocks} if layout_blocks is not None else {}

        os.makedirs(os.path.dirname(gds_path), exist_ok=True)
        if (meta.get("slot_emit") is not None):
            # slot-model cell: the ASTRAN-style emitter needs the
            # orderings + leg widths, not just the placement IR
            se = meta["slot_emit"]
            gds_cells.write_cell_gds(
                gds_path, layout_nl, placement, se["width_cols"],
                se["ordering_p"], se["ordering_n"], se["leg_widths"],
                route=route)
        else:
            gds_writer(gds_path, layout_nl, placement, route)
        try:
            record["verdicts"]["verify"] = _verdict(
                verify_fn(layout_nl, placement, route, **vkw))
        except Exception as exc:                   # noqa: BLE001
            record["verdicts"]["verify"] = {
                "ok": None,
                "note": "verify raised %s: %s" % (type(exc).__name__, exc)}
        try:
            record["verdicts"]["sanity"] = _verdict(sanity_checker(gds_path))
        except Exception as exc:                   # noqa: BLE001
            record["verdicts"]["sanity"] = {
                "ok": None, "note": "sanity raised %s: %s" % (
                    type(exc).__name__, exc)}

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
    }


def _render_markdown(report):
    summary = report["summary"]
    base = summary["baselines"]
    ratio = summary["width_ratio_python_over_astran"]
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
        "Ratios are same-semantics comparable only for `bigcell-*` "
        "engines (slot model: W vertical, doc/BIGCELL_SLOT_GEOMETRY.md); "
        "`smt-exact` cells draw device W as horizontal columns (the "
        "exact engine's own IR, unchanged) and their ratios overstate "
        "width against ASTRAN's slot geometry.",
        "",
        "| cell | source | T | astran um | python um | ratio | engine "
        "| verify | sanity | note |",
        "|---|---|---|---|---|---|---|---|---|---|",
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

        note = (r.get("note") or "")[:80]
        lines.append("| %s | %s | %d | %s | %s | %s | %s | %s | %s | %s |"
                     % (r["name"], r["source"], r["T"],
                        _fmt_um(r["astran_um"]), _fmt_um(r["python_um"]),
                        ratio_txt, r.get("engine") or "-",
                        _flag(verify), _flag(sanity), note))
    return "\n".join(lines) + "\n"
