"""Regenerate specific ASTRAN cells from their existing .sp netlists.

Reruns the project's own run_astran_for_netlist() for the named COMPLEX cells in
a benchmark output directory, without re-running the (slow) pattern-mining
pipeline.  Useful when a netlist changed but a stale layout is still cached.

Usage:
    python regenerate_cells.py [--dir outputs/adder] COMPLEX1 COMPLEX9 ...
"""
import argparse
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from astran import (ASTRAN_BUILD_PATH, ASTRAN_TECHNOLOGY, GUROBI_CL,
                    run_astran_for_netlist)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cells", nargs="+", help="cell names, e.g. COMPLEX1")
    parser.add_argument("--dir", default="outputs/adder",
                        help="directory holding the .sp/.gds files")
    parser.add_argument("--netlist", default=None,
                        help="shared netlist for every cell (default: "
                             "<dir>/<cell>.sp); original_astran_cells selects "
                             "cells by name from one shared library file")
    args = parser.parse_args()

    outdir = os.path.abspath(args.dir)
    if not os.path.isdir(outdir):
        parser.error("no such directory: %s" % outdir)

    for name in args.cells:
        sp = args.netlist or os.path.join(outdir, name + ".sp")
        if not os.path.exists(sp):
            print("[regen] skip %s: no %s" % (name, sp))
            continue
        gds = os.path.join(outdir, name + ".gds")
        if os.path.exists(gds):
            shutil.move(gds, gds + ".bak")
        t0 = time.time()
        print("[regen] start %s (%s)" % (name, time.strftime("%H:%M:%S")),
              flush=True)
        run_astran_for_netlist(astran_path=ASTRAN_BUILD_PATH, gurobi_path=GUROBI_CL,
                            technology_path=ASTRAN_TECHNOLOGY,
                            spice_netlist_path=sp, complex_name=name,
                            command_dir=outdir)
        size = "NO LOG"
        log = os.path.join(outdir, name + ".Astranlog")
        if os.path.exists(log):
            for line in open(log, errors="replace"):
                if "Cell Size (W x H)" in line:
                    size = line.strip()
        print("[regen] done %s in %.0fs -> %s" % (name, time.time() - t0, size),
              flush=True)


if __name__ == "__main__":
    main()
