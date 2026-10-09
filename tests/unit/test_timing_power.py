"""Unit tests for flow/timing_power.py (liberty LUTs + mini pattern STA)."""
import pytest

from timing_power import (bilinear, load_timing_power, pattern_timing_power,
                          stage_delay_slew, stage_energy)
from electrical import load_cell_electrical_metrics
from blif_graph_util import StdCellType, DesignCell, DesignNet

LIB = "../std_celllib/gscl45nm.lib"


def test_lut_parsing_real_lib(in_flow):
    tp = load_timing_power(LIB)
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


def test_stage_delay_monotone_in_load(in_flow):
    nand = load_timing_power(LIB)["NAND2X1"]
    d_small, _ = stage_delay_slew(nand, 0.06, 0.06)
    d_big, _ = stage_delay_slew(nand, 5.0, 0.06)
    assert 0 < d_small < d_big
    assert stage_energy(nand, 0.06, 0.06) >= 0


def _cell(cid, name):
    t = StdCellType(name)
    t.add_pin("I0", "input")
    t.add_pin("O0", "output")
    return DesignCell(cid, "c%d" % cid, t)


def test_pattern_sta_chain_accumulates(in_flow):
    a, b = _cell(0, "NAND2X1"), _cell(1, "NAND2X1")
    net = DesignNet(0, "n0")
    net.add_pin("O0", a, False)
    net.add_pin("I0", b, True)
    a.add_output_net(net)
    b.add_input_net(net)
    tp = load_timing_power(LIB)
    em = load_cell_electrical_metrics(LIB)
    r = pattern_timing_power([a, b], tp, em)
    assert r["stages_timed"] == 2
    single, _ = stage_delay_slew(tp["NAND2X1"], 0.0, 0.06)
    assert r["critical_path_ns"] > single
    assert r["toggle_energy"] > 0
