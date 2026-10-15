"""Resumable, optionally parallel layout-cell queue (ASTRAN / SMT).

Two lessons from running big batches are built in here:

* **Resume.**  A multi-hour batch that dies midway (host sleep, session
  interruption) used to restart from zero -- ASTRAN is deterministic, so
  the lost work is reproducible but not free.  The queue records per-cell
  results in ``<outdir>/.astran_queue.json`` and skips any cell whose
  ``.sp`` has not changed since its layout was produced (same freshness
  contract as ``astran_layout_is_stale``: the .sp mtime is the signal).

* **Safe parallelism.**  The old "never two ASTRAN cells at once" rule
  exists because the LP solver model/solution (ILPmodel.lp/.sol) is
  written relative to the process cwd.  Here every cell gets its own cwd
  (``<outdir>/.lpwork/<cell>/``, git-ignored), so ``jobs > 1`` cannot
  clobber anything.  One caveat remains: ASTRAN also writes
  ``GDSIILTable.txt`` next to the exported .gds (designmng.cpp:336), and
  cells sharing one outdir write identical content there -- harmless in
  practice but keep ``jobs`` modest.

Every cell is linted with :mod:`astran_lint` before a run is attempted, so
a malformed netlist fails in milliseconds instead of after the layout
loop, and a 0x0 result (LP failure symptom) is reported as a failure,
never silently counted.

**Engine selection** (``engine=`` / verilog2cells ``--engine``): the
queue can also drive the pure-Python SMT engine (:mod:`smt_engine`) for
small, conservatively-shaped cells -- see :func:`smt_eligible`.  ``auto``
tries SMT first for eligible cells and falls back to ASTRAN on any
failure; every CellResult and manifest entry records the producing
engine.  The default ``astran`` keeps historical behaviour untouched.
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from astran import (ASTRAN_BUILD_PATH, ASTRAN_TECHNOLOGY, GUROBI_CL,
                    run_astran_for_netlist)
from astran_lint import errors as lint_errors
from astran_lint import format_issues, lint_netlist, lint_text

MANIFEST_NAME = ".astran_queue.json"
LPWORK_DIR = ".lpwork"

# --- pure-Python SMT engine (flow/smt_engine) ---------------------------
# A cell is offered to the SMT engine only when it is squarely inside the
# engine's proven range: small, literally-modelled, numerically sized.
SMT_MAX_TRANSISTORS = 8
SMT_BUDGET_S = 120.0        # total CP-SAT budget per cell (layout+route)
ENGINES = ("auto", "smt", "astran")


@dataclass
class CellResult:
    name: str
    ok: bool
    skipped: bool = False
    width: float = None
    height: float = None
    seconds: float = 0.0
    note: str = ""
    engine: str = "astran"


class CancelledError(Exception):
    """Raised when the queue's should_cancel callable fires."""


def smt_eligible(sp_path, max_transistors=SMT_MAX_TRANSISTORS):
    """(eligible, reason) for offering one .sp to the SMT engine.

    Reuses :mod:`astran_lint` (a deck that fails lint cannot satisfy
    either engine), then adds the SMT-specific conservatism: literal
    PMOS/NMOS models (the engine's parser knows no others) and a
    transistor budget.  Deterministic and filesystem-only.
    """
    text = open(sp_path, "r", errors="replace").read()
    errs = lint_errors(lint_text(text, source=os.path.basename(sp_path)))
    if errs:
        return False, "lint: " + format_issues(errs[:2], sp_path)
    n_trans = 0
    models = set()
    for raw in text.splitlines():
        words = raw.split()
        if (not words or words[0][0].upper() != "M"
                or words[0].upper().startswith(".")):
            continue
        if (len(words) >= 6):
            models.add(words[5].upper())
            n_trans += 1
    if (n_trans > max_transistors):
        return False, ("%d transistors > smt budget %d"
                       % (n_trans, max_transistors))
    bad = sorted(models - {"PMOS", "NMOS"})
    if (bad):
        return False, "models %s are not literal PMOS/NMOS" % bad
    return True, "%d transistors" % n_trans


def run_smt_cell(name, sp_path, gds_path,
                 layout_time_s=0.4 * SMT_BUDGET_S,
                 route_time_s=0.6 * SMT_BUDGET_S,
                 check_sanity=True):
    """Lay out one cell with the pure-Python SMT engine.

    Returns a CellResult; the .gds is written ONLY on success (a cell
    that fails the engine's verify leaves no artifact, so the .sp/.gds
    freshness contract of invariant 7 stays honest).  Width is reported
    in um (cols x the engine's 0.19 grid) at the engine's 2.47 um row
    height -- the same width-per-height semantics as the ASTRAN log.
    """
    t0 = time.time()
    from smt_engine import synth_cell
    from smt_engine.gds import write_cell_gds
    from smt_engine.layout_model import DEFAULT_GRID_UM, DEFAULT_HEIGHT_UM
    text = open(sp_path, "r", errors="replace").read()
    result = synth_cell(text, layout_time_s=layout_time_s,
                        route_time_s=route_time_s)
    seconds = time.time() - t0
    if (result.route is None or not result.route.ok):
        status = (result.route.status_name if result.route is not None
                  else result.layout.status_name)
        return CellResult(name=name, ok=False, seconds=seconds,
                          engine="smt", note="smt: %s" % status)
    if (result.report is None or not result.report.ok()):
        viols = result.report.violations[:2] if result.report else []
        return CellResult(name=name, ok=False, seconds=seconds,
                          engine="smt",
                          note="smt: verify failed %s" % (viols,))
    write_cell_gds(gds_path, result.netlist, result.layout.devices,
                   result.route)
    width_um = result.route.width_cols * DEFAULT_GRID_UM
    note = ("smt: %d cols, verify ok"
            % result.route.width_cols)
    if (check_sanity):
        try:
            from layout_sanity import check_layout
            report = check_layout(gds_path, units_per_um=1.0)
            if (not report.ok()):
                return CellResult(
                    name=name, ok=False, seconds=seconds, engine="smt",
                    note="smt: sanity failed %s" % (report.violations[:2],))
            note += ", sanity ok"
        except Exception as exc:                       # noqa: BLE001
            note += ", sanity skipped (%s)" % exc
    try:
        from pin_accessibility import cell_pin_accessibility
        score = cell_pin_accessibility(gds_path,
                                       grid_um=DEFAULT_GRID_UM).score
        note += ", pin %.2f" % score
    except Exception:                              # noqa: BLE001
        pass
    return CellResult(name=name, ok=True, width=width_um,
                      height=DEFAULT_HEIGHT_UM, seconds=seconds,
                      note=note, engine="smt")


def _read_cell_size(log_path):
    """(width, height) from an ASTRAN log, or (None, None)."""
    if not os.path.exists(log_path):
        return None, None
    for line in open(log_path, "r", errors="replace"):
        if "-> Cell Size (W x H): " in line:
            try:
                wh = line.split("-> Cell Size (W x H): ")[1].strip().split("x")
                return float(wh[0]), float(wh[1])
            except (IndexError, ValueError):
                return None, None
    return None, None


def _load_manifest(outdir):
    path = os.path.join(outdir, MANIFEST_NAME)
    if os.path.exists(path):
        try:
            return json.load(open(path))
        except (OSError, ValueError):
            return {}
    return {}


def _save_manifest(outdir, manifest):
    path = os.path.join(outdir, MANIFEST_NAME)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    os.replace(tmp, path)


def _is_fresh(entry, sp_path, gds_path):
    """Manifest entry is reusable when it matches the .sp that produced it
    and the .gds is still on disk (same contract as the layout cache in
    main.py: regenerate when the .gds is missing or older than its .sp)."""
    return (entry.get("ok") and
            entry.get("sp_mtime") == os.path.getmtime(sp_path) and
            os.path.exists(gds_path))


def run_queue(cells, outdir, jobs=1, resume=True,
              runner=run_astran_for_netlist, on_event=None,
              should_cancel=None, engine="astran",
              smt_max_transistors=SMT_MAX_TRANSISTORS,
              smt_budget_s=SMT_BUDGET_S, smt_runner=None):
    """Run each cell of ``cells`` (names of <outdir>/<cell>.sp) through a
    layout engine; returns [CellResult] in the input order.

    ``engine`` selects the layout engine per cell:

    * ``"astran"`` (default) -- exactly the historical behaviour: every
      cell goes to ASTRAN;
    * ``"smt"`` -- the pure-Python engine only; a cell outside its
      envelope (see :func:`smt_eligible`) is a hard error;
    * ``"auto"`` -- eligible cells try the SMT engine first (within
      ``smt_budget_s``), and fall back to ASTRAN on any failure
      (infeasible, timeout, verify/sanity failure) transparently; every
      CellResult records which engine produced it.

    ``runner``/``smt_runner`` are injectable for tests.  ``on_event``
    receives ("start"|"done", CellResult|name) callbacks for progress
    reporting.  ``should_cancel`` is polled before each cell (serial
    mode) or before scheduling (parallel mode); when it returns True the
    queue raises CancelledError -- in-flight cells finish, pending ones
    never start.
    """
    if (engine not in ENGINES):
        raise ValueError("engine must be one of %s, got %r"
                         % (ENGINES, engine))
    outdir = os.path.abspath(outdir)
    manifest = _load_manifest(outdir)
    results = {}
    if (smt_runner is None):
        smt_runner = run_smt_cell

    def emit(kind, payload):
        if on_event:
            on_event(kind, payload)

    def cached_engine(entry):
        return entry.get("engine", "astran")

    def entry_usable(name):
        """Resume check, engine-aware: an explicit engine mode refuses
        cached results produced by the other engine; auto accepts both."""
        entry = manifest.get(name)
        if (not entry):
            return False
        expected = {"astran": "astran", "smt": "smt"}.get(engine)
        if (expected and cached_engine(entry) != expected):
            return False
        return _is_fresh(entry,
                         os.path.join(outdir, name + ".sp"),
                         os.path.join(outdir, name + ".gds"))

    def run_astran_cell(name):
        sp_path = os.path.join(outdir, name + ".sp")
        gds_path = os.path.join(outdir, name + ".gds")
        log_path = os.path.join(outdir, name + ".Astranlog")

        lint = lint_netlist(sp_path)
        errs = lint_errors(lint)
        if errs:
            return CellResult(name=name, ok=False,
                              note="lint: " + format_issues(errs, name))

        if os.path.exists(gds_path):
            os.replace(gds_path, gds_path + ".bak")

        t0 = time.time()
        emit("start", name)
        runner(astran_path=ASTRAN_BUILD_PATH, gurobi_path=GUROBI_CL,
               technology_path=ASTRAN_TECHNOLOGY,
               spice_netlist_path=sp_path, complex_name=name,
               command_dir=outdir,
               work_dir=os.path.join(outdir, LPWORK_DIR, name))
        seconds = time.time() - t0

        width, height = _read_cell_size(log_path)
        ok = width is not None and width > 0
        note = ""
        if not ok:
            note = ("no Cell Size in log (run failed?)"
                    if width is None else
                    "0x0 cell -- LP failure symptom, check the log")
        result = CellResult(name=name, ok=ok, width=width, height=height,
                            seconds=seconds, note=note, engine="astran")
        manifest[name] = {
            "ok": ok, "width": width, "height": height,
            "seconds": round(seconds, 1), "engine": "astran",
            "sp_mtime": os.path.getmtime(sp_path),
        }
        return result

    smt_fail_reason = {}

    def run_smt_or_note(name):
        """One SMT attempt; None means 'not produced' (caller falls back).

        A raised exception counts as a failure too -- an engine crash
        must degrade to ASTRAN, never kill the batch (auto mode)."""
        sp_path = os.path.join(outdir, name + ".sp")
        gds_path = os.path.join(outdir, name + ".gds")
        emit("start", name)
        try:
            result = smt_runner(
                name, sp_path, gds_path,
                layout_time_s=0.4 * smt_budget_s,
                route_time_s=0.6 * smt_budget_s)
        except Exception as exc:                   # noqa: BLE001
            smt_fail_reason[name] = "engine raised %s: %s" % (
                type(exc).__name__, exc)
            return None
        if (result.ok):
            manifest[name] = {
                "ok": True, "width": result.width, "height": result.height,
                "seconds": round(result.seconds, 1), "engine": "smt",
                "sp_mtime": os.path.getmtime(sp_path),
            }
        else:
            smt_fail_reason[name] = result.note
        return result if result.ok else None

    def run_one(name):
        if (engine == "astran"):
            return run_astran_cell(name)
        eligible, reason_txt = smt_eligible(sp_path_of(name),
                                            smt_max_transistors)
        if (engine == "smt" and not eligible):
            raise RuntimeError(
                "cell %s is not SMT-eligible (%s) and --engine smt "
                "forbids the ASTRAN fallback" % (name, reason_txt))
        if (eligible):
            result = run_smt_or_note(name)
            if (result is not None):
                return result
        if (engine == "smt"):
            raise RuntimeError(
                "cell %s failed in the SMT engine" % name)
        result = run_astran_cell(name)
        if (engine == "auto"):
            reason = smt_fail_reason.get(name)
            if (reason is None and not eligible):
                reason = "not eligible: " + reason_txt
            result.note = ("smt fallback (%s): %s" % (reason, result.note)
                           if result.note else
                           "smt fallback (%s)" % (reason or "unknown"))
        return result

    def sp_path_of(name):
        return os.path.join(outdir, name + ".sp")

    pending = [c for c in cells if not (resume and entry_usable(c))]
    # Cached cells keep their results without touching the runner.
    for name in cells:
        if name not in pending:
            entry = manifest[name]
            results[name] = CellResult(
                name=name, ok=True, skipped=True,
                width=entry.get("width"), height=entry.get("height"),
                note="cached layout", engine=cached_engine(entry))

    if jobs <= 1:
        for name in pending:
            if should_cancel and should_cancel():
                _save_manifest(outdir, manifest)
                raise CancelledError(
                    "cancelled before cell %s" % name)
            results[name] = run_one(name)
            emit("done", results[name])
    else:
        if should_cancel and should_cancel():
            _save_manifest(outdir, manifest)
            raise CancelledError("cancelled before scheduling")
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            for name, result in zip(pending, pool.map(run_one, pending)):
                results[name] = result
                emit("done", result)

    _save_manifest(outdir, manifest)
    return [results[name] for name in cells]
