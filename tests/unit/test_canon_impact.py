"""Unit tests for flow/canon_impact.py (P1-10 prototype)."""
from blif_graph_util import StdCellType, DesignCell, DesignNet
from canon_impact import canonicalization_impact


def _cell(cid, name):
    t = StdCellType(name)
    t.add_pin("I0", "input")
    t.add_pin("I1", "input")
    t.add_pin("O0", "output")
    return DesignCell(cid, "c%d" % cid, t)


def _link(src, src_pin, dst, dst_pin, nid):
    net = DesignNet(nid, "n%d" % nid)
    net.add_pin(src_pin, src, False)
    net.add_pin(dst_pin, dst, True)
    src.add_output_net(net)
    dst.add_input_net(net)


def test_merges_order_split_instances():
    # instance A: AND2X1 <- (NAND2X1 on I0, OR2X1 on I1)
    # instance B: AND2X1 <- (OR2X1 on I0, NAND2X1 on I1)  (same shape,
    #             different net enumeration order)
    cells = [
        _cell(0, "NAND2X1"), _cell(1, "OR2X1"), _cell(2, "AND2X1"),
        _cell(3, "OR2X1"), _cell(4, "NAND2X1"), _cell(5, "AND2X1"),
    ]
    _link(cells[0], "O0", cells[2], "I0", 0)
    _link(cells[1], "O0", cells[2], "I1", 1)
    _link(cells[3], "O0", cells[5], "I0", 2)
    _link(cells[4], "O0", cells[5], "I1", 3)

    report = canonicalization_impact(cells)
    assert report["legacy_groups"] == 2        # order-sensitive split
    assert report["canonical_groups"] == 1     # merged by canonical form
    assert report["merged_groups"] == 1
    assert report["recovered_instances"] == 1  # 2-instance group vs biggest 1


def test_adder_report_structure(in_flow):
    from blif_preproc import gen_graph_from_liberty_and_blif
    _, cells, _, _ = gen_graph_from_liberty_and_blif(
        "../std_celllib/gscl45nm.lib", "../benchmark/blif/adder.blif")
    report = canonicalization_impact(cells)
    assert report["canonical_groups"] <= report["legacy_groups"]
    assert report["coded_cells"] > 0
    assert report["merged_groups"] >= 0
