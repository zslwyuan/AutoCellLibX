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
    sortPatternClusterSeqs,
)
from blif_pattern_growth import grow_sequence_of_clusters

LIB = "../stdCelllib/gscl45nm.lib"
BLIF = "../benchmark/blif/adder.blif"


def _cell(cid, name="INVX1"):
    t = StdCellType(name)
    t.addPin("I0", "input")
    t.addPin("O0", "output")
    return DesignCell(cid, "c%d" % cid, t)


def _link(src, dst, netId):
    net = DesignNet(netId, "n%d" % netId)
    net.addPin("O0", src, False)
    net.addPin("I0", dst, True)
    src.addOutputNet(net)
    dst.addInputNet(net)


def test_output_side_does_not_absorb_same_pattern_cluster():
    # two instances of the same 2-cell pattern
    x1, x2, y1, y2 = (_cell(i) for i in range(4))
    cells = [x1, x2, y1, y2]

    _link(x1, x2, 0)   # X cluster: x1 -> x2
    _link(y1, y2, 1)   # Y cluster: y1 -> y2
    _link(x2, y1, 2)   # X cluster's output-side neighbour is y1 (in Y cluster)

    c1 = DesignPatternCluster(0, "[INVX1,INVX1]", cells, [x1.id, x2.id], 0)
    c2 = DesignPatternCluster(1, "[INVX1,INVX1]", cells, [y1.id, y2.id], 0)
    for cid in c1.cellIdsContained:
        cells[cid].setCluster(c1)
        cells[cid].setClusterId(0)
    for cid in c2.cellIdsContained:
        cells[cid].setCluster(c2)
        cells[cid].setClusterId(1)

    seq = DesignPatternClusterSeq("[INVX1,INVX1]")
    seq.addCluster(c1)
    seq.addCluster(c2)

    grow_sequence_of_clusters(None, seq, 2, 2)

    assert not c2.disabled, "sibling same-pattern cluster must not be disabled"
    assert y1.id not in c1.cellIdsContained
    assert c1.cellIdsContained == [x1.id, x2.id]


def test_input_side_does_not_absorb_same_pattern_cluster():
    # mirror case: the neighbour is an input predecessor belonging to a sibling
    x1, x2, y1, y2 = (_cell(i) for i in range(4))
    cells = [x1, x2, y1, y2]

    _link(x1, x2, 0)
    _link(y1, y2, 1)
    _link(y2, x1, 2)   # y2 (Y cluster) drives x1 (X cluster)

    c1 = DesignPatternCluster(0, "[INVX1,INVX1]", cells, [x1.id, x2.id], 0)
    c2 = DesignPatternCluster(1, "[INVX1,INVX1]", cells, [y1.id, y2.id], 0)
    for cid in c1.cellIdsContained:
        cells[cid].setCluster(c1)
        cells[cid].setClusterId(0)
    for cid in c2.cellIdsContained:
        cells[cid].setCluster(c2)
        cells[cid].setClusterId(1)

    seq = DesignPatternClusterSeq("[INVX1,INVX1]")
    seq.addCluster(c1)
    seq.addCluster(c2)

    grow_sequence_of_clusters(None, seq, 2, 2)

    assert not c2.disabled
    assert y2.id not in c1.cellIdsContained


def test_growth_invariants_on_benchmark(in_pysrc):
    from blif_preproc import loadDataAndPreprocess

    G, cells, netlist, types, ds, ml, seqs, cn = loadDataAndPreprocess(
        libFileName=LIB, blifFileName=BLIF, startTime=0)
    seqs = sortPatternClusterSeqs(seqs)

    newSeqs, patternNum = grow_sequence_of_clusters(
        G, seqs[0], len(seqs), len(seqs))

    assert patternNum >= len(seqs)
    for s in newSeqs:
        assert len(s.patternClusters) > 0
        seen = set()
        for cl in s.patternClusters:
            for cid in cl.cellIdsContained:
                assert cid not in seen, "a cell may not appear in two clusters"
                seen.add(cid)


def _seq_with_two_neighbor_classes():
    """One 2-cell cluster whose output fans out to two XOR2X1 (count-2
    feature) and one OR2X1 (count-1 feature)."""
    def cell(cid, name):
        t = StdCellType(name)
        t.addPin("I0", "input")
        t.addPin("I1", "input")
        t.addPin("O0", "output")
        return DesignCell(cid, "c%d" % cid, t)

    cells = [cell(i, n) for i, n in enumerate(
        ["NAND2X1", "NAND2X1", "XOR2X1", "XOR2X1", "OR2X1"])]
    c0, c1, x0, x1, o0 = cells
    _link(c0, c1, 0)
    net1 = DesignNet(1, "n1")
    net1.addPin("O0", c1, False)
    net1.addPin("I0", x0, True)
    net1.addPin("I0", x1, True)
    c1.addOutputNet(net1)
    x0.addInputNet(net1)
    x1.addInputNet(net1)
    _link(c1, o0, 2)

    cluster = DesignPatternCluster(0, "[NAND2X1,NAND2X1]", cells, [0, 1], 0)
    for cid in (0, 1):
        cells[cid].setCluster(cluster)
        cells[cid].setClusterId(0)
    seq = DesignPatternClusterSeq("[NAND2X1,NAND2X1]")
    seq.addCluster(cluster)
    return seq


def test_growth_prunes_vetoed_branch_and_takes_next():
    """The top-frequency branch is vetoed by the estimator -> the second
    branch is grown instead (P0-3)."""
    seq = _seq_with_two_neighbor_classes()

    def veto_xor(member_types, neighbor_type, new_size, occurrences):
        return -1.0 if neighbor_type == "XOR2X1" else 100.0

    resSeqs, _ = grow_sequence_of_clusters(
        None, seq, 1, 1, benefitEstimator=veto_xor)
    assert len(resSeqs) == 2                     # grown seq + leftover seq
    trace = resSeqs[0].patternClusters[0].patternExtensionTrace
    assert "+OR2X1" in trace
    assert "XOR2X1" not in trace


def test_growth_all_branches_pruned_returns_ungrown():
    seq = _seq_with_two_neighbor_classes()
    resSeqs, _ = grow_sequence_of_clusters(
        None, seq, 1, 1, benefitEstimator=lambda *a: -1.0)
    assert len(resSeqs) == 1
    assert resSeqs[0] is seq
    assert seq.patternClusters[0].patternExtensionTrace == \
        "[NAND2X1,NAND2X1]"


def test_growth_without_estimator_keeps_legacy_top1():
    seq = _seq_with_two_neighbor_classes()
    resSeqs, _ = grow_sequence_of_clusters(None, seq, 1, 1)
    assert len(resSeqs) == 2
    trace = resSeqs[0].patternClusters[0].patternExtensionTrace
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
        c.setCluster(cl)
        c.setClusterId(cl.clusterId)
    seq1 = DesignPatternClusterSeq("[INVX1,INVX1]")
    seq1.addCluster(c1)
    seq2 = DesignPatternClusterSeq("[INVX1,INVX1]")
    seq2.addCluster(c2)

    # first beam head grows and steals b1, disabling c2
    grown1, _ = grow_sequence_of_clusters(None, seq1, 2, 2)
    assert c2.disabled

    # second beam head: only disabled clusters left -> no crash, no growth
    resSeqs, _ = grow_sequence_of_clusters(None, seq2, 2, 3)
    assert len(resSeqs) == 1
    assert resSeqs[0].patternClusters == []
