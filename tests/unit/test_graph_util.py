"""Unit tests for pySrc/blif_graph_util.py: data structures and helpers."""
from blif_graph_util import (
    StdCellType,
    DesignCell,
    DesignNet,
    DesignPatternCluster,
    DesignPatternClusterSeq,
    removeEmptySeqsAndDisableClusters,
    sortPatternClusterSeqs,
)


def _mk_cells(n, typeName="X"):
    t = StdCellType(typeName)
    return [DesignCell(i, "c%d" % i, t) for i in range(n)]


class TestStdCellType:
    def test_pin_directions(self):
        t = StdCellType("NAND2X1")
        t.addPin("A", "input")
        t.addPin("B", "input")
        t.addPin("Y", "output")
        assert t.inputPins == ["A", "B"]
        assert t.outputPins == ["Y"]
        assert t.pins == ["A", "B", "Y"]

    def test_unknown_direction_is_neither(self):
        t = StdCellType("X")
        t.addPin("P", "inout")
        assert t.inputPins == [] and t.outputPins == []
        assert t.pins == ["P"]


class TestDesignCell:
    def test_add_cell_pin_routes_by_direction(self):
        t = StdCellType("NAND2X1")
        t.addPin("A", "input")
        t.addPin("Y", "output")
        c = DesignCell(0, "c0", t)
        c.addCellPin("A", "n1")
        c.addCellPin("Y", "n2")
        assert c.inputPinRefNames == ["A"] and c.inputNetNames == ["n1"]
        assert c.outputPinRefNames == ["Y"] and c.outputNetNames == ["n2"]

    def test_defaults(self):
        c = DesignCell(0, "c0", StdCellType("X"))
        assert c.clusterId == -1
        assert c.cluster is None
        assert c.stopType is False


class TestDesignNet:
    def test_pred_succ_links(self):
        t = StdCellType("X")
        t.addPin("A", "input")
        t.addPin("Y", "output")
        src = DesignCell(0, "s", t)
        dst = DesignCell(1, "d", t)
        net = DesignNet(0, "n")
        net.addPin("Y", src, False)   # driver
        net.addPin("A", dst, True)    # sink
        assert net.predCell is src and net.predPin == "Y"
        assert net.succCells == [dst] and net.succPins == ["A"]


class TestPatternCluster:
    def test_trace_strips_quotes(self):
        cells = _mk_cells(2)
        cl = DesignPatternCluster(0, "['A','B']", cells, [0, 1], 3)
        assert cl.patternExtensionTrace == "[A,B]"
        assert cl.clusterTypeId == 3
        assert [c.id for c in cl.cellsContained] == [0, 1]

    def test_add_cell(self):
        cells = _mk_cells(2)
        cl = DesignPatternCluster(0, "[A]", cells, [0], 0)
        cl.addCell(cells[1])
        assert cl.cellIdsContained == [0, 1]
        assert cl.cellsContained[-1] is cells[1]

    def test_seq_trace_strips_quotes(self):
        s = DesignPatternClusterSeq("['A','B']")
        assert s.patternExtensionTrace == "[A,B]"
        assert s.patternClusters == []


class TestPruningAndSorting:
    def test_remove_empty_and_disabled(self):
        cells = _mk_cells(4)
        s1 = DesignPatternClusterSeq("[A]")
        c1 = DesignPatternCluster(0, "[A]", cells, [0], 0)
        c2 = DesignPatternCluster(1, "[A]", cells, [1], 0)
        c2.disabled = True
        s1.addCluster(c1)
        s1.addCluster(c2)
        s2 = DesignPatternClusterSeq("[B]")  # no clusters -> dropped
        out = removeEmptySeqsAndDisableClusters([s1, s2])
        assert len(out) == 1
        assert [c.clusterId for c in out[0].patternClusters] == [0]

    def test_sort_by_coverage_then_size(self):
        cells = _mk_cells(10)

        def make_seq(nclusters, size, cid):
            s = DesignPatternClusterSeq("[A]")
            for k in range(nclusters):
                ids = list(range(k * size, k * size + size))
                s.addCluster(DesignPatternCluster(cid, "[A]", cells, ids, cid))
            return s

        big_cov = make_seq(3, 2, 0)    # coverage = 6
        small_cov = make_seq(2, 2, 1)  # coverage = 4
        out = sortPatternClusterSeqs([small_cov, big_cov])
        assert out[0] is big_cov
        assert out[1] is small_cov


class TestCountUncoveredClusters:
    """Savings de-dup (roadmap P0-2): clusters overlapping cells already
    claimed by an earlier candidate in the same round must not be counted
    again."""

    def test_disjoint_clusters_all_counted(self):
        from blif_graph_util import countUncoveredClusters
        cells = _mk_cells(6)
        clusters = [DesignPatternCluster(i, "[A]", cells, [2 * i, 2 * i + 1], 0)
                    for i in range(3)]
        covered = set()
        assert countUncoveredClusters(clusters, covered) == 3
        assert covered == {0, 1, 2, 3, 4, 5}

    def test_overlapping_cluster_skipped_once(self):
        from blif_graph_util import countUncoveredClusters
        cells = _mk_cells(6)
        covered = set()
        first = [DesignPatternCluster(0, "[A]", cells, [0, 1], 0)]
        second = [DesignPatternCluster(1, "[B]", cells, [1, 2], 0),
                  DesignPatternCluster(2, "[B]", cells, [3, 4], 0)]
        assert countUncoveredClusters(first, covered) == 1
        # cluster 1 overlaps cell 1 -> skipped; cluster 2 is clean -> counted
        assert countUncoveredClusters(second, covered) == 1
        assert covered == {0, 1, 3, 4}

    def test_fully_covered_candidate_counts_zero(self):
        from blif_graph_util import countUncoveredClusters
        cells = _mk_cells(4)
        clusters = [DesignPatternCluster(0, "[A]", cells, [0, 1], 0)]
        covered = {0, 1}
        assert countUncoveredClusters(clusters, covered) == 0
