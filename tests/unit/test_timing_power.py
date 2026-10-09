"""Unit tests for pySrc/timing_power.py (liberty LUTs + mini pattern STA)."""
import pytest

from timing_power import (bilinear, loadTimingPower, patternTimingPower,
                          stageDelaySlew, stageEnergy)
from electrical import loadCellElectricalMetrics
from blif_graph_util import StdCellType, DesignCell, DesignNet

LIB = "../stdCelllib/gscl45nm.lib"


def test_lut_parsing_real_lib(in_pysrc):
    tp = loadTimingPower(LIB)
    nand = tp["NAND2X1"]
    assert set(nand["arcs"].keys()) >= {"A", "B"}
    loads, slews, values = nand["arcs"]["A"]["cell_rise"]
    assert len(loads) == len(values) == 6
    assert len(slews) == len(values[0]) == 6
    assert values[0][0] == pytest.approx(0.345107)
    assert any("rise_power" in tbls for tbls in nand["power"].values())


def test_bilinear_exact_interp_and_clamp():
    grid1 = [0.1, 0.5, 1.0]
    grid2 = [0.06, 1.8]
    values = [[1.0, 2.0],
              [3.0, 4.0],
              [5.0, 6.0]]
    assert bilinear(grid1, grid2, values, 0.1, 0.06) == pytest.approx(1.0)
    assert bilinear(grid1, grid2, values, 1.0, 1.8) == pytest.approx(6.0)
    assert bilinear(grid1, grid2, values, 0.5, 0.93) == pytest.approx(3.5)
    assert bilinear(grid1, grid2, values, 0.001, 0.06) == pytest.approx(1.0)
    assert bilinear(grid1, grid2, values, 99, 1.8) == pytest.approx(6.0)


def test_stage_delay_monotone_in_load(in_pysrc):
    nand = loadTimingPower(LIB)["NAND2X1"]
    d_small, _ = stageDelaySlew(nand, 0.06, 0.06)
    d_big, _ = stageDelaySlew(nand, 5.0, 0.06)
    assert 0 < d_small < d_big
    assert stageEnergy(nand, 0.06, 0.06) >= 0


def _cell(cid, name):
    t = StdCellType(name)
    t.addPin("I0", "input")
    t.addPin("O0", "output")
    return DesignCell(cid, "c%d" % cid, t)


def test_pattern_sta_chain_accumulates(in_pysrc):
    a, b = _cell(0, "NAND2X1"), _cell(1, "NAND2X1")
    net = DesignNet(0, "n0")
    net.addPin("O0", a, False)
    net.addPin("I0", b, True)
    a.addOutputNet(net)
    b.addInputNet(net)
    tp = loadTimingPower(LIB)
    em = loadCellElectricalMetrics(LIB)
    r = patternTimingPower([a, b], tp, em)
    assert r["stages_timed"] == 2
    single, _ = stageDelaySlew(tp["NAND2X1"], 0.0, 0.06)
    assert r["critical_path_ns"] > single
    assert r["toggle_energy"] > 0
