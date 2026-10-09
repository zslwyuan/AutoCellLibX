"""Regression tests for subgraph encoding (pySrc/blif_preproc.py).

Bug fixed: ``extract_and_encode_subgraph_tree`` appended an entry to ``encodes``
even when the predecessor was already in ``tree``.  For multi-output cells
(one driver feeding several pins of the same sink) the encoded pattern string
was longer than the node list, so structurally-equal patterns got different
codes and were split apart.
"""
from blif_graph_util import StdCellType, DesignCell, DesignNet
from blif_preproc import extract_and_encode_subgraph_tree


def _cell(cid, name, nin, nout):
    t = StdCellType(name)
    for i in range(nin):
        t.add_pin("I%d" % i, "input")
    for i in range(nout):
        t.add_pin("O%d" % i, "output")
    return DesignCell(cid, "c%d" % cid, t)


def _link(src, src_pin, dst, dst_pin, net_id, cells):
    net = DesignNet(net_id, "n%d" % net_id)
    net.add_pin(src_pin, src, False)
    net.add_pin(dst_pin, dst, True)
    src.add_output_net(net)
    dst.add_input_net(net)


def test_multi_output_driver_is_encoded_once():
    # FAX1-like driver with two outputs driving two pins of the same sink.
    driver = _cell(0, "FAX1", 3, 2)
    sink = _cell(1, "AND2X1", 2, 1)
    cells = [driver, sink]

    _link(driver, "O0", sink, "I0", 0, cells)   # SUM  -> sink A
    _link(driver, "O1", sink, "I1", 1, cells)   # COUT -> sink B

    tree, code = extract_and_encode_subgraph_tree(cells, sink.id, depth_limit=1)

    assert tree == [sink.id, driver.id]          # de-duplicated node list
    assert code == ["AND2X1", "FAX1"]            # paired 1:1 with tree
    assert len(tree) == len(code)


def test_encoding_pairs_one_to_one_on_benchmark(in_pysrc):
    from blif_preproc import gen_graph_from_liberty_and_blif

    G, cells, netlist, types = gen_graph_from_liberty_and_blif(
        "../stdCelllib/gscl45nm.lib", "../benchmark/blif/adder.blif")

    checked = 0
    for cell in cells[:300]:
        for depth in (1, 2):
            tree, code = extract_and_encode_subgraph_tree(cells, cell.id, depth)
            assert len(tree) == len(code), (cell.id, depth, tree, code)
            checked += 1
    assert checked > 0


def test_tree_nodes_are_unique(in_pysrc):
    from blif_preproc import gen_graph_from_liberty_and_blif

    G, cells, netlist, types = gen_graph_from_liberty_and_blif(
        "../stdCelllib/gscl45nm.lib", "../benchmark/blif/adder.blif")
    for cell in cells[:200]:
        tree, _ = extract_and_encode_subgraph_tree(cells, cell.id, depth_limit=2)
        assert len(tree) == len(set(tree))


def test_canonical_code_sorts_children_after_root():
    from blif_preproc import canonical_pattern_code

    assert canonical_pattern_code(
        ["OR2X1", "XNOR2X1", "NAND2X1", "NAND2X1"]) == \
        "[OR2X1,NAND2X1,NAND2X1,XNOR2X1]"
    # already-canonical input is stable
    assert canonical_pattern_code(["A", "B", "C"]) == "[A,B,C]"


def test_canonical_code_is_net_order_invariant():
    """Two isomorphic instances whose input nets enumerate in different
    orders must produce the same pattern code (they used to be split into
    separate groups, under-counting the pattern's frequency)."""
    from blif_preproc import extract_and_encode_subgraph_tree, canonical_pattern_code

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

    cells_a, root_a = build(0)
    cells_b, root_b = build(1)
    _, code_a = extract_and_encode_subgraph_tree(cells_a, root_a.id, depth_limit=1)
    _, code_b = extract_and_encode_subgraph_tree(cells_b, root_b.id, depth_limit=1)
    assert code_a != code_b                      # raw order differs (the bug)
    assert canonical_pattern_code(code_a) == canonical_pattern_code(code_b)


def test_benchmark_codes_are_canonical(in_pysrc):
    """Every initial-cluster trace on the benchmark must be in canonical
    form (children after the root are sorted)."""
    from blif_preproc import (gen_graph_from_liberty_and_blif,
                             heuristic_label_initial_clusters)

    G, cells, netlist, types = gen_graph_from_liberty_and_blif(
        "../stdCelllib/gscl45nm.lib", "../benchmark/blif/adder.blif")
    cluster_seqs, _ = heuristic_label_initial_clusters(
        G, cells, netlist)
    assert cluster_seqs, "expected at least one initial cluster"
    for seq in cluster_seqs:
        trace = seq.pattern_clusters[0].pattern_extension_trace
        base = trace.split("+")[0].strip("[]")
        parts = base.split(",")
        assert parts[1:] == sorted(parts[1:]), trace
