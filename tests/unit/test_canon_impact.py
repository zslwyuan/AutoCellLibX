"""Unit tests for pySrc/canon_impact.py (P1-10 prototype)."""
from BLIFGraphUtil import StdCellType, DesignCell, DesignNet
from canon_impact import canonicalizationImpact


def _cell(cid, name):
    t = StdCellType(name)
    t.addPin("I0", "input")
    t.addPin("I1", "input")
    t.addPin("O0", "output")
    return DesignCell(cid, "c%d" % cid, t)


def _link(src, src_pin, dst, dst_pin, nid):
    net = DesignNet(nid, "n%d" % nid)
    net.addPin(src_pin, src, False)
    net.addPin(dst_pin, dst, True)
    src.addOutputNet(net)
    dst.addInputNet(net)


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

    report = canonicalizationImpact(cells)
    assert report["legacyGroups"] == 2        # order-sensitive split
    assert report["canonicalGroups"] == 1     # merged by canonical form
    assert report["mergedGroups"] == 1
    assert report["recoveredInstances"] == 1  # 2-instance group vs biggest 1


def test_adder_report_structure(in_pysrc):
    from BLIFPreProc import genGraphFromLibertyAndBLIF
    _, cells, _, _ = genGraphFromLibertyAndBLIF(
        "../stdCelllib/gscl45nm.lib", "../benchmark/blif/adder.blif")
    report = canonicalizationImpact(cells)
    assert report["canonicalGroups"] <= report["legacyGroups"]
    assert report["codedCells"] > 0
    assert report["mergedGroups"] >= 0
