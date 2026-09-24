"""Integration tests for the vendored ASTRAN build (marked ``slow``).

These need the ASTRAN binary from ``tools/astran/build/bin`` -- run
``bash tools/astran/build_astran.sh`` first.
"""
import os

import pytest

pytestmark = pytest.mark.slow


def test_astran_tool_paths_resolve():
    from Astran import ASTRAN_BUILD_PATH, ASTRAN_TECHNOLOGY, GUROBI_CL
    exe = os.path.join(ASTRAN_BUILD_PATH, "bin", "Astran")
    assert os.path.exists(exe) or os.path.exists(exe + ".exe"), (
        "ASTRAN binary not found; run: bash tools/astran/build_astran.sh")
    assert os.path.exists(ASTRAN_TECHNOLOGY), ASTRAN_TECHNOLOGY
    assert os.path.exists(GUROBI_CL), GUROBI_CL


def test_astran_runs_invx1_smoke(in_pysrc, tmp_path):
    import gdstk

    from Astran import (ASTRAN_BUILD_PATH, ASTRAN_TECHNOLOGY, GUROBI_CL,
                        runAstranForNetlist)

    netlist = os.path.abspath("../stdCelllib/cellsAstranFriendly.sp")
    outdir = str(tmp_path)

    runAstranForNetlist(AstranPath=ASTRAN_BUILD_PATH, gurobiPath=GUROBI_CL,
                        technologyPath=ASTRAN_TECHNOLOGY,
                        spiceNetlistPath=netlist,
                        complexName="INVX1", commandDir=outdir)

    gds = os.path.join(outdir, "INVX1.gds")
    assert os.path.exists(gds), "ASTRAN produced no GDS (see INVX1.Astranlog)"

    lib = gdstk.read_gds(gds)
    cell = next(c for c in lib.cells if c.name == "INVX1")
    bb = cell.bounding_box()
    w, h = bb[1][0] - bb[0][0], bb[1][1] - bb[0][1]
    assert 0 < w < 5 and 0 < h < 5

    # the ASTRAN log must report a cell size
    log = open(os.path.join(outdir, "INVX1.Astranlog")).read()
    assert "-> Cell Size (W x H):" in log
