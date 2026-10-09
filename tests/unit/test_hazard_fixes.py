"""Regression tests for the hazard fixes logged in AUDIT_REPORT §5.17."""
import warnings

import pytest

from astran import load_astran_area


def test_load_astran_area_raises_instead_of_fabricating(tmp_path):
    # A missing log must raise: the old assert(False) was stripped under
    # `python -O` and silently returned a fabricated width of 123.
    with pytest.raises(RuntimeError):
        load_astran_area(str(tmp_path), "NOSUCHCELL")


def test_load_astran_area_parses_cell_size(tmp_path):
    log = tmp_path / "C1.Astranlog"
    log.write_text("noise\n-> Cell Size (W x H): 4.37 x 2.47\n")
    assert load_astran_area(str(tmp_path), "C1") == pytest.approx(4.37)


def test_unknown_cell_type_raises(in_pysrc, tmp_path):
    from blif_preproc import gen_graph_from_liberty_and_blif

    blif = tmp_path / "bad.blif"
    blif.write_text(
        ".model top\n.inputs a b\n.outputs y\n"
        ".subckt FOOX1 A=a B=b Y=y\n.end\n")
    with pytest.raises(ValueError, match="FOOX1"):
        gen_graph_from_liberty_and_blif("../stdCelllib/gscl45nm.lib", str(blif))


def test_multi_driver_net_warns_and_keeps_last():
    from blif_graph_util import DesignCell, DesignNet, StdCellType

    t = StdCellType("NAND2X1")
    c1, c2 = DesignCell(0, "c1", t), DesignCell(1, "c2", t)
    net = DesignNet(0, "n1")
    before = DesignNet.multi_driver_count
    net.add_pin("Y", c1, False)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        net.add_pin("Y", c2, False)
    assert DesignNet.multi_driver_count == before + 1
    assert any("multiple drivers" in str(w.message) for w in caught)
    assert net.pred_cell is c2
