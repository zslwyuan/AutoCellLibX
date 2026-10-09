"""Unit tests for flow/electrical.py (P1-7)."""
from electrical import load_cell_electrical_metrics, pattern_electrical_metrics
from blif_graph_util import StdCellType, DesignCell, DesignNet


def test_real_liberty_metrics(in_flow):
    m = load_cell_electrical_metrics("../std_celllib/gscl45nm.lib")
    assert len(m) > 25
    nand = m["NAND2X1"]
    assert nand["leakage"] > 0
    assert nand["input_cap"] > 0
    assert nand["delay_proxy"] is not None and nand["delay_proxy"] > 0
    # input cap is the sum over input pins: two pins -> roughly 2x one pin
    inv = m["INVX1"]
    assert inv["input_cap"] < nand["input_cap"]


def test_parse_cache_returns_copy(in_flow):
    a = load_cell_electrical_metrics("../std_celllib/gscl45nm.lib")
    a["NAND2X1"]["leakage"] = -1
    b = load_cell_electrical_metrics("../std_celllib/gscl45nm.lib")
    assert b["NAND2X1"]["leakage"] > 0


def _cell(cid, name):
    t = StdCellType(name)
    t.add_pin("I0", "input")
    t.add_pin("O0", "output")
    return DesignCell(cid, "c%d" % cid, t)


def _link(src, dst, nid):
    net = DesignNet(nid, "n%d" % nid)
    net.add_pin("O0", src, False)
    net.add_pin("I0", dst, True)
    src.add_output_net(net)
    dst.add_input_net(net)


def test_pattern_metrics_count_internal_nets():
    a, b, c = _cell(0, "NAND2X1"), _cell(1, "NAND2X1"), _cell(2, "OR2X1")
    _link(a, b, 0)          # a -> b : internal (both inside the pattern)
    _link(b, c, 1)          # b -> c : crosses the pattern boundary
    metrics = {"NAND2X1": {"leakage": 2.0, "input_cap": 0.5,
                           "delay_proxy": 1.0}}
    m = pattern_electrical_metrics([a, b], metrics)
    assert m["leakage_sum"] == 4.0
    assert m["input_cap_sum"] == 1.0
    assert m["delay_proxy_avg"] == 1.0
    assert m["internal_nets"] == 1        # only the a->b net is internal


def test_pattern_metrics_tolerates_unknown_types():
    a, _b = _cell(0, "FOO"), _cell(1, "BAR")
    _link(a, _b, 0)
    m = pattern_electrical_metrics([a, _b], {})
    assert m["leakage_sum"] == 0.0
    assert m["delay_proxy_avg"] is None
    assert m["internal_nets"] == 1
