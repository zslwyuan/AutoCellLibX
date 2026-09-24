"""Regression tests for subgraph encoding (pySrc/BLIFPreProc.py).

Bug fixed: ``extractAndEncodeSubgraph_Tree`` appended an entry to ``encodes``
even when the predecessor was already in ``tree``.  For multi-output cells
(one driver feeding several pins of the same sink) the encoded pattern string
was longer than the node list, so structurally-equal patterns got different
codes and were split apart.
"""
from BLIFGraphUtil import StdCellType, DesignCell, DesignNet
from BLIFPreProc import extractAndEncodeSubgraph_Tree


def _cell(cid, name, nin, nout):
    t = StdCellType(name)
    for i in range(nin):
        t.addPin("I%d" % i, "input")
    for i in range(nout):
        t.addPin("O%d" % i, "output")
    return DesignCell(cid, "c%d" % cid, t)


def _link(src, srcPin, dst, dstPin, netId, cells):
    net = DesignNet(netId, "n%d" % netId)
    net.addPin(srcPin, src, False)
    net.addPin(dstPin, dst, True)
    src.addOutputNet(net)
    dst.addInputNet(net)


def test_multi_output_driver_is_encoded_once():
    # FAX1-like driver with two outputs driving two pins of the same sink.
    driver = _cell(0, "FAX1", 3, 2)
    sink = _cell(1, "AND2X1", 2, 1)
    cells = [driver, sink]

    _link(driver, "O0", sink, "I0", 0, cells)   # SUM  -> sink A
    _link(driver, "O1", sink, "I1", 1, cells)   # COUT -> sink B

    tree, code = extractAndEncodeSubgraph_Tree(cells, sink.id, depthLimit=1)

    assert tree == [sink.id, driver.id]          # de-duplicated node list
    assert code == ["AND2X1", "FAX1"]            # paired 1:1 with tree
    assert len(tree) == len(code)


def test_encoding_pairs_one_to_one_on_benchmark(in_pysrc):
    from BLIFPreProc import genGraphFromLibertyAndBLIF

    G, cells, netlist, types = genGraphFromLibertyAndBLIF(
        "../stdCelllib/gscl45nm.lib", "../benchmark/blif/adder.blif")

    checked = 0
    for cell in cells[:300]:
        for depth in (1, 2):
            tree, code = extractAndEncodeSubgraph_Tree(cells, cell.id, depth)
            assert len(tree) == len(code), (cell.id, depth, tree, code)
            checked += 1
    assert checked > 0


def test_tree_nodes_are_unique(in_pysrc):
    from BLIFPreProc import genGraphFromLibertyAndBLIF

    G, cells, netlist, types = genGraphFromLibertyAndBLIF(
        "../stdCelllib/gscl45nm.lib", "../benchmark/blif/adder.blif")
    for cell in cells[:200]:
        tree, _ = extractAndEncodeSubgraph_Tree(cells, cell.id, depthLimit=2)
        assert len(tree) == len(set(tree))
