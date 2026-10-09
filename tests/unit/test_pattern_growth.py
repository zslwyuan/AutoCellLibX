"""Unit tests for the pattern growth algorithm (pySrc/blif_pattern_growth.py).

Regression covered: ``grow_sequence_of_clusters`` skipped neighbours that already
belonged to another cluster of the *same* pattern on the input-predecessor
side, but not on the output-successor side.  As a result a cluster could
absorb cells of a sibling instance (which then got disabled), silently
merging same-pattern instances.
"""
from blif_graph_util import (
    StdCellType,
    DesignCell,
    DesignNet,
    DesignPatternCluster,
    DesignPatternClusterSeq,
    sort_pattern_cluster_seqs,
)
from blif_pattern_growth import grow_sequence_of_clusters

LIB = "../stdCelllib/gscl45nm.lib"
BLIF = "../benchmark/blif/adder.blif"


def _cell(cid, name="INVX1"):
    t = StdCellType(name)
    t.add_pin("I0", "input")
    t.add_pin("O0", "output")
    return DesignCell(cid, "c%d" % cid, t)


def _link(src, dst, net_id):
    net = DesignNet(net_id, "n%d" % net_id)
    net.add_pin("O0", src, False)
    net.add_pin("I0", dst, True)
    src.add_output_net(net)
    dst.add_input_net(net)


def test_output_side_does_not_absorb_same_pattern_cluster():
    # two instances of the same 2-cell pattern
    x1, x2, y1, y2 = (_cell(i) for i in range(4))
    cells = [x1, x2, y1, y2]

    _link(x1, x2, 0)   # X cluster: x1 -> x2
    _link(y1, y2, 1)   # Y cluster: y1 -> y2
    _link(x2, y1, 2)   # X cluster's output-side neighbour is y1 (in Y cluster)

    c1 = DesignPatternCluster(0, "[INVX1,INVX1]", cells, [x1.id, x2.id], 0)
    c2 = DesignPatternCluster(1, "[INVX1,INVX1]", cells, [y1.id, y2.id], 0)
    for cid in c1.cell_ids:
        cells[cid].set_cluster(c1)
        cells[cid].set_cluster_id(0)
    for cid in c2.cell_ids:
        cells[cid].set_cluster(c2)
        cells[cid].set_cluster_id(1)

    seq = DesignPatternClusterSeq("[INVX1,INVX1]")
    seq.add_cluster(c1)
    seq.add_cluster(c2)

    grow_sequence_of_clusters(None, seq, 2, 2)

    assert not c2.disabled, "sibling same-pattern cluster must not be disabled"
    assert y1.id not in c1.cell_ids
    assert c1.cell_ids == [x1.id, x2.id]


def test_input_side_does_not_absorb_same_pattern_cluster():
    # mirror case: the neighbour is an input predecessor belonging to a sibling
    x1, x2, y1, y2 = (_cell(i) for i in range(4))
    cells = [x1, x2, y1, y2]

    _link(x1, x2, 0)
    _link(y1, y2, 1)
    _link(y2, x1, 2)   # y2 (Y cluster) drives x1 (X cluster)

    c1 = DesignPatternCluster(0, "[INVX1,INVX1]", cells, [x1.id, x2.id], 0)
    c2 = DesignPatternCluster(1, "[INVX1,INVX1]", cells, [y1.id, y2.id], 0)
    for cid in c1.cell_ids:
        cells[cid].set_cluster(c1)
        cells[cid].set_cluster_id(0)
    for cid in c2.cell_ids:
        cells[cid].set_cluster(c2)
        cells[cid].set_cluster_id(1)

    seq = DesignPatternClusterSeq("[INVX1,INVX1]")
    seq.add_cluster(c1)
    seq.add_cluster(c2)

    grow_sequence_of_clusters(None, seq, 2, 2)

    assert not c2.disabled
    assert y2.id not in c1.cell_ids


def test_growth_invariants_on_benchmark(in_pysrc):
    from blif_preproc import load_data_and_preprocess

    G, cells, netlist, types, ds, ml, seqs, cn = load_data_and_preprocess(
        lib_file_name=LIB, blif_file_name=BLIF, start_time=0)
    seqs = sort_pattern_cluster_seqs(seqs)

    new_seqs, pattern_num = grow_sequence_of_clusters(
        G, seqs[0], len(seqs), len(seqs))

    assert pattern_num >= len(seqs)
    for s in new_seqs:
        assert len(s.pattern_clusters) > 0
        seen = set()
        for cl in s.pattern_clusters:
            for cid in cl.cell_ids:
                assert cid not in seen, "a cell may not appear in two clusters"
                seen.add(cid)


def _seq_with_two_neighbor_classes():
    """One 2-cell cluster whose output fans out to two XOR2X1 (count-2
    feature) and one OR2X1 (count-1 feature)."""
    def cell(cid, name):
        t = StdCellType(name)
        t.add_pin("I0", "input")
        t.add_pin("I1", "input")
        t.add_pin("O0", "output")
        return DesignCell(cid, "c%d" % cid, t)

    cells = [cell(i, n) for i, n in enumerate(
        ["NAND2X1", "NAND2X1", "XOR2X1", "XOR2X1", "OR2X1"])]
    c0, c1, x0, x1, o0 = cells
    _link(c0, c1, 0)
    net1 = DesignNet(1, "n1")
    net1.add_pin("O0", c1, False)
    net1.add_pin("I0", x0, True)
    net1.add_pin("I0", x1, True)
    c1.add_output_net(net1)
    x0.add_input_net(net1)
    x1.add_input_net(net1)
    _link(c1, o0, 2)

    cluster = DesignPatternCluster(0, "[NAND2X1,NAND2X1]", cells, [0, 1], 0)
    for cid in (0, 1):
        cells[cid].set_cluster(cluster)
        cells[cid].set_cluster_id(0)
    seq = DesignPatternClusterSeq("[NAND2X1,NAND2X1]")
    seq.add_cluster(cluster)
    return seq


def test_growth_prunes_vetoed_branch_and_takes_next():
    """The top-frequency branch is vetoed by the estimator -> the second
    branch is grown instead (P0-3)."""
    seq = _seq_with_two_neighbor_classes()

    def veto_xor(member_types, neighbor_type, new_size, occurrences):
        return -1.0 if neighbor_type == "XOR2X1" else 100.0

    res_seqs, _ = grow_sequence_of_clusters(
        None, seq, 1, 1, benefit_estimator=veto_xor)
    assert len(res_seqs) == 2                     # grown seq + leftover seq
    trace = res_seqs[0].pattern_clusters[0].pattern_extension_trace
    assert "+OR2X1" in trace
    assert "XOR2X1" not in trace


def test_growth_all_branches_pruned_returns_ungrown():
    seq = _seq_with_two_neighbor_classes()
    res_seqs, _ = grow_sequence_of_clusters(
        None, seq, 1, 1, benefit_estimator=lambda *a: -1.0)
    assert len(res_seqs) == 1
    assert res_seqs[0] is seq
    assert seq.pattern_clusters[0].pattern_extension_trace == \
        "[NAND2X1,NAND2X1]"


def test_growth_without_estimator_keeps_legacy_top1():
    seq = _seq_with_two_neighbor_classes()
    res_seqs, _ = grow_sequence_of_clusters(None, seq, 1, 1)
    assert len(res_seqs) == 2
    trace = res_seqs[0].pattern_clusters[0].pattern_extension_trace
    assert "+XOR2X1" in trace                    # frequency-top branch


def test_growth_tolerates_beam_disabled_clusters():
    """Beam growth (grow_beam>1): the first head can disable clusters of a
    later head's seq by stealing their cells.  Growing that second head
    must skip the disabled clusters instead of asserting (the pool is only
    cleaned after the whole beam)."""
    a1, a2, b1, b2 = (_cell(i) for i in range(4))
    cells = [a1, a2, b1, b2]
    _link(a1, a2, 0)
    _link(a2, b1, 1)          # b1 is growable from seq1 AND belongs to seq2
    _link(b1, b2, 2)
    c1 = DesignPatternCluster(0, "[INVX1,INVX1]", cells, [0, 1], 0)
    c2 = DesignPatternCluster(1, "[INVX1,INVX1]", cells, [2, 3], 1)
    for c, cl in ((a1, c1), (a2, c1), (b1, c2), (b2, c2)):
        c.set_cluster(cl)
        c.set_cluster_id(cl.cluster_id)
    seq1 = DesignPatternClusterSeq("[INVX1,INVX1]")
    seq1.add_cluster(c1)
    seq2 = DesignPatternClusterSeq("[INVX1,INVX1]")
    seq2.add_cluster(c2)

    # first beam head grows and steals b1, disabling c2
    grown1, _ = grow_sequence_of_clusters(None, seq1, 2, 2)
    assert c2.disabled

    # second beam head: only disabled clusters left -> no crash, no growth
    res_seqs, _ = grow_sequence_of_clusters(None, seq2, 2, 3)
    assert len(res_seqs) == 1
    assert res_seqs[0].pattern_clusters == []
