"""Resumable, optionally parallel ASTRAN cell queue.

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
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from astran import (ASTRAN_BUILD_PATH, ASTRAN_TECHNOLOGY, GUROBI_CL,
                    run_astran_for_netlist)
from astran_lint import errors as lint_errors
from astran_lint import format_issues, lint_netlist

MANIFEST_NAME = ".astran_queue.json"
LPWORK_DIR = ".lpwork"


@dataclass
class CellResult:
    name: str
    ok: bool
    skipped: bool = False
    width: float = None
    height: float = None
    seconds: float = 0.0
    note: str = ""


class CancelledError(Exception):
    """Raised when the queue's should_cancel callable fires."""


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
              should_cancel=None):
    """Run each cell of ``cells`` (names of <outdir>/<cell>.sp) through
    ASTRAN; returns [CellResult] in the input order.

    ``runner`` is injectable for tests.  ``on_event`` receives
    ("start"|"done", CellResult|name) callbacks for progress reporting.
    ``should_cancel`` is polled before each cell (serial mode) or before
    scheduling (parallel mode); when it returns True the queue raises
    CancelledError -- in-flight cells finish, pending ones never start.
    """
    outdir = os.path.abspath(outdir)
    manifest = _load_manifest(outdir)
    results = {}

    def emit(kind, payload):
        if on_event:
            on_event(kind, payload)

    def run_one(name):
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
                            seconds=seconds, note=note)
        manifest[name] = {
            "ok": ok, "width": width, "height": height,
            "seconds": round(seconds, 1),
            "sp_mtime": os.path.getmtime(sp_path),
        }
        return result

    pending = [c for c in cells
               if not (resume and c in manifest and
                       _is_fresh(manifest[c],
                                 os.path.join(outdir, c + ".sp"),
                                 os.path.join(outdir, c + ".gds")))]
    # Cached cells keep their results without touching the runner.
    for name in cells:
        if name not in pending:
            entry = manifest[name]
            results[name] = CellResult(name=name, ok=True, skipped=True,
                                       width=entry.get("width"),
                                       height=entry.get("height"),
                                       note="cached layout")

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
