"""Integration tests for the vendored ASTRAN build (marked ``slow``).

These need the ASTRAN binary from ``tools/astran/build/bin`` -- run
``bash tools/astran/build_astran.sh`` first.
"""
import os
import re

import pytest

pytestmark = pytest.mark.slow


def test_astran_tool_paths_resolve():
    from astran import ASTRAN_BUILD_PATH, ASTRAN_TECHNOLOGY, GUROBI_CL
    exe = os.path.join(ASTRAN_BUILD_PATH, "bin", "Astran")
    assert os.path.exists(exe) or os.path.exists(exe + ".exe"), (
        "ASTRAN binary not found; run: bash tools/astran/build_astran.sh")
    assert os.path.exists(ASTRAN_TECHNOLOGY), ASTRAN_TECHNOLOGY
    assert os.path.exists(GUROBI_CL), GUROBI_CL


def test_astran_runs_invx1_smoke(in_pysrc, tmp_path):
    import gdstk

    from astran import (ASTRAN_BUILD_PATH, ASTRAN_TECHNOLOGY, GUROBI_CL,
                        run_astran_for_netlist)

    netlist = os.path.abspath("../stdCelllib/cellsAstranFriendly.sp")
    outdir = str(tmp_path)

    run_astran_for_netlist(astran_path=ASTRAN_BUILD_PATH, gurobi_path=GUROBI_CL,
                        technology_path=ASTRAN_TECHNOLOGY,
                        spice_netlist_path=netlist,
                        complex_name="INVX1", command_dir=outdir)

    gds = os.path.join(outdir, "INVX1.gds")
    assert os.path.exists(gds), "ASTRAN produced no GDS (see INVX1.Astranlog)"

    # The log's "Cell Size (W x H)" is the authoritative dimension (AGENTS.md
    # invariant 1): ASTRAN writes a bogus GDS UNITS record on purpose, so GDS
    # user units are NOT microns -- the GUI viewer calibrates against the log
    # (gui/gds_model.py).  Assert the compacted size from the log and that the
    # GDS cell is a non-degenerate rectangle.
    log = open(os.path.join(outdir, "INVX1.Astranlog")).read()
    m = re.search(r"Cell Size \(W x H\): ([\d.]+) x ([\d.]+)", log)
    assert m, "log must report a cell size"
    w, h = (float(v) for v in m.groups())
    assert 0 < w < 5 and 0 < h < 5

    lib = gdstk.read_gds(gds)
    cell = next(c for c in lib.cells if c.name == "INVX1")
    bb = cell.bounding_box()
    assert bb[1][0] > bb[0][0] and bb[1][1] > bb[0][1]


def test_astran_runs_nor3x1_gap_ordering_smoke(in_pysrc, tmp_path):
    """NOR3X1 has unequal P/N counts (6 P, 3 N), which pads the transistor
    ordering with link == -1 GAP slots and produces single-transistor series
    legs; both used to read trans[-1] in seriesFolding/route() and crash."""
    from astran import (ASTRAN_BUILD_PATH, ASTRAN_TECHNOLOGY, GUROBI_CL,
                        run_astran_for_netlist)

    netlist = os.path.abspath("../stdCelllib/cellsAstranFriendly.sp")
    outdir = str(tmp_path)

    run_astran_for_netlist(astran_path=ASTRAN_BUILD_PATH, gurobi_path=GUROBI_CL,
                        technology_path=ASTRAN_TECHNOLOGY,
                        spice_netlist_path=netlist,
                        complex_name="NOR3X1", command_dir=outdir)

    log = open(os.path.join(outdir, "NOR3X1.Astranlog")).read()
    assert "-> Cell Size (W x H):" in log
    assert "WARNING" not in log, log  # no solver failure / skipped compaction
