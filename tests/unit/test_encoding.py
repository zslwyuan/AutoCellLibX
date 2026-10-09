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


def test_canonical_code_sorts_children_after_root():
    from BLIFPreProc import canonicalPatternCode

    assert canonicalPatternCode(
        ["OR2X1", "XNOR2X1", "NAND2X1", "NAND2X1"]) == \
        "[OR2X1,NAND2X1,NAND2X1,XNOR2X1]"
    # already-canonical input is stable
    assert canonicalPatternCode(["A", "B", "C"]) == "[A,B,C]"


def test_canonical_code_is_net_order_invariant():
    """Two isomorphic instances whose input nets enumerate in different
    orders must produce the same pattern code (they used to be split into
    separate groups, under-counting the pattern's frequency)."""
    from BLIFPreProc import extractAndEncodeSubgraph_Tree, canonicalPatternCode

    def build(order):
        # root AND2X1 driven by NAND2X1 and OR2X1 in the given order
        n0, n1 = ("NAND2X1", "OR2X1") if order == 0 else ("OR2X1", "NAND2X1")
        d0 = _cell(0, n0, 2, 1)
        d1 = _cell(1, n1, 2, 1)
        root = _cell(2, "AND2X1", 2, 1)
        cells = [d0, d1, root]
        _link(d0, "O0", root, "I0", 0, cells)
        _link(d1, "O0", root, "I1", 1, cells)
        return cells, root

    cellsA, rootA = build(0)
    cellsB, rootB = build(1)
    _, codeA = extractAndEncodeSubgraph_Tree(cellsA, rootA.id, depthLimit=1)
    _, codeB = extractAndEncodeSubgraph_Tree(cellsB, rootB.id, depthLimit=1)
    assert codeA != codeB                      # raw order differs (the bug)
    assert canonicalPatternCode(codeA) == canonicalPatternCode(codeB)


def test_benchmark_codes_are_canonical(in_pysrc):
    """Every initial-cluster trace on the benchmark must be in canonical
    form (children after the root are sorted)."""
    from BLIFPreProc import (genGraphFromLibertyAndBLIF,
                             heuristicLabelSomeNodesAndGetInitialClusters)

    G, cells, netlist, types = genGraphFromLibertyAndBLIF(
        "../stdCelllib/gscl45nm.lib", "../benchmark/blif/adder.blif")
    clusterSeqs, _ = heuristicLabelSomeNodesAndGetInitialClusters(
        G, cells, netlist)
    assert clusterSeqs, "expected at least one initial cluster"
    for seq in clusterSeqs:
        trace = seq.patternClusters[0].patternExtensionTrace
        base = trace.split("+")[0].strip("[]")
        parts = base.split(",")
        assert parts[1:] == sorted(parts[1:]), trace
