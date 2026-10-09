"""Unit tests for the ASTRAN run-script builder (pySrc/astran.py)."""
import astran
from astran import (ASTRAN_CELLS_HEIGHT, ASTRAN_CELL_TEMPLATE,
                    ASTRAN_SUPPLY_SIZE, ASTRAN_VGRID, buildAstranCommands)


def _cmd(**over):
    kwargs = dict(gurobiPath=r"C:\tools\gurobi_cl.cmd",
                  technologyPath=r"C:\tech\tech_freePDK45.rul",
                  spiceNetlistPath=r"C:\out\COMPLEX1.sp",
                  complexName="COMPLEX1", commandDir=r"C:\out")
    kwargs.update(over)
    return buildAstranCommands(**kwargs)


def test_every_placeholder_is_substituted():
    script = _cmd()
    assert "@" not in script


def test_script_sets_geometry_explicitly():
    script = _cmd()
    assert "set rowheight %d" % ASTRAN_CELLS_HEIGHT in script
    assert "set supplysize %g" % ASTRAN_SUPPLY_SIZE in script
    assert 'set celltemplate "%s"' % ASTRAN_CELL_TEMPLATE in script
    # the command name must survive substitution (it shares a word with its
    # value in a naive implementation)
    assert "set supplysize" in script


def test_script_wires_lpsolve_paths_and_cell_name():
    script = _cmd()
    assert 'set lpsolve "C:\\tools\\gurobi_cl.cmd"' in script
    assert 'load technology "C:\\tech\\tech_freePDK45.rul"' in script
    assert 'load netlist "C:\\out\\COMPLEX1.sp"' in script
    assert "cellgen select COMPLEX1" in script
    assert "cellgen autoflow" in script
    assert "COMPLEX1.gds" in script


def test_default_geometry_matches_the_gscl45_row_height():
    # GSCL45's CoreSite is 0.38 x 2.47 and its M1 pitch is 0.19, so the flow
    # uses 13 rows of 0.19 = the exact site height (width, the area proxy, is
    # only comparable at a fixed height).
    assert ASTRAN_VGRID == 0.19
    assert abs(ASTRAN_CELLS_HEIGHT * ASTRAN_VGRID - 2.47) < 1e-9


def test_geometry_constants_drive_the_script(monkeypatch):
    """Calibrating the row height is a constants change, nothing else."""
    monkeypatch.setattr(astran, "ASTRAN_VGRID", 0.2)
    script = _cmd()
    assert "set grid 0.19 0.2" in script
