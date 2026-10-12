"""Regenerate specific ASTRAN cells from their existing .sp netlists.

Runs the project's own run_astran_for_netlist() for the named cells in a
benchmark output directory, without re-running the (slow) pattern-mining
pipeline.  Built on astran_queue, so every cell is lint-checked first,
runs are resumable, and --jobs > 1 runs cells in parallel safely (each
cell gets its own LP working directory; see astran_queue).

Usage:
    python regenerate_cells.py [--dir outputs/adder] [--jobs 2] [--resume] \
        COMPLEX1 COMPLEX9 ...
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from astran import (ASTRAN_BUILD_PATH, ASTRAN_TECHNOLOGY, GUROBI_CL,   # noqa: E402
                    run_astran_for_netlist)
from astran_queue import run_queue          # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cells", nargs="+", help="cell names, e.g. COMPLEX1")
    parser.add_argument("--dir", default="outputs/adder",
                        help="directory holding the .sp/.gds files")
    parser.add_argument("--netlist", default=None,
                        help="shared netlist for every cell (default: "
                             "<dir>/<cell>.sp); original_astran_cells selects "
                             "cells by name from one shared library file.  "
                             "Shared-netlist runs stay serial (one cellgen "
                             "select per run, one LP cwd).")
    parser.add_argument("--jobs", type=int, default=1,
                        help="parallel ASTRAN workers (default 1; each cell "
                             "gets its own LP cwd, so >1 is safe)")
    parser.add_argument("--resume", action="store_true",
                        help="skip cells whose .sp has not changed since "
                             "their layout was produced")
    args = parser.parse_args()

    outdir = os.path.abspath(args.dir)
    if not os.path.isdir(outdir):
        parser.error("no such directory: %s" % outdir)

    cells = [name for name in args.cells
             if args.netlist or os.path.exists(
                 os.path.join(outdir, name + ".sp"))]
    for name in args.cells:
        if name not in cells:
            print("[regen] skip %s: no %s" % (name, name + ".sp"))
    if not cells:
        return 0

    if args.netlist:
        # Legacy shared-netlist mode: one .sp holds many subckts and
        # `cellgen select` picks one per run.  Serial on purpose -- every
        # run shares the process cwd for its LP files.
        import shutil
        for name in cells:
            gds = os.path.join(outdir, name + ".gds")
            if os.path.exists(gds):
                shutil.move(gds, gds + ".bak")
            t0 = time.time()
            print("[regen] start %s (%s)" % (name, time.strftime("%H:%M:%S")),
                  flush=True)
            run_astran_for_netlist(
                astran_path=ASTRAN_BUILD_PATH, gurobi_path=GUROBI_CL,
                technology_path=ASTRAN_TECHNOLOGY,
                spice_netlist_path=args.netlist, complex_name=name,
                command_dir=outdir)
            size = "NO LOG"
            log = os.path.join(outdir, name + ".Astranlog")
            if os.path.exists(log):
                for line in open(log, errors="replace"):
                    if "Cell Size (W x H)" in line:
                        size = line.strip()
            print("[regen] done %s in %.0fs -> %s"
                  % (name, time.time() - t0, size), flush=True)
        return 0

    def report(kind, payload):
        if kind == "start":
            print("[regen] start %s (%s)" % (payload, time.strftime("%H:%M:%S")),
                  flush=True)
        else:
            print("[regen] done %s in %.0fs -> %s%s" % (
                payload.name, payload.seconds,
                ("width %.2f" % payload.width) if payload.width else "NO SIZE",
                (" [cached]" if payload.skipped else
                 "" if payload.ok else " FAILED: " + payload.note)),
                flush=True)

    results = run_queue(cells, outdir, jobs=args.jobs,
                        resume=args.resume, on_event=report)
    failed = [r for r in results if not r.ok]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main() or 0)
