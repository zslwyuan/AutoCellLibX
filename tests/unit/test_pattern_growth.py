"""Unit tests for the pattern growth algorithm (pySrc/BLIFPatternGrowth.py).

Regression covered: ``growASeqOfClusters`` skipped neighbours that already
belonged to another cluster of the *same* pattern on the input-predecessor
side, but not on the output-successor side.  As a result a cluster could
absorb cells of a sibling instance (which then got disabled), silently
merging same-pattern instances.
"""
from BLIFGraphUtil import (
    StdCellType,
    DesignCell,
    DesignNet,
    DesignPatternCluster,
    DesignPatternClusterSeq,
    sortPatternClusterSeqs,
)
from BLIFPatternGrowth import growASeqOfClusters

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

    growASeqOfClusters(None, seq, 2, 2)

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

    growASeqOfClusters(None, seq, 2, 2)

    assert not c2.disabled
    assert y2.id not in c1.cellIdsContained


def test_growth_invariants_on_benchmark(in_pysrc):
    from BLIFPreProc import loadDataAndPreprocess

    G, cells, netlist, types, ds, ml, seqs, cn = loadDataAndPreprocess(
        libFileName=LIB, blifFileName=BLIF, startTime=0)
    seqs = sortPatternClusterSeqs(seqs)

    newSeqs, patternNum = growASeqOfClusters(
        G, seqs[0], len(seqs), len(seqs))

    assert patternNum >= len(seqs)
    for s in newSeqs:
        assert len(s.patternClusters) > 0
        seen = set()
        for cl in s.patternClusters:
            for cid in cl.cellIdsContained:
                assert cid not in seen, "a cell may not appear in two clusters"
                seen.add(cid)
