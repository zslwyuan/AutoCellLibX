"""Unit tests for pySrc/blif_graph_util.py: data structures and helpers."""
from blif_graph_util import (
    StdCellType,
    DesignCell,
    DesignNet,
    DesignPatternCluster,
    DesignPatternClusterSeq,
    remove_empty_seqs_and_disable_clusters,
    sort_pattern_cluster_seqs,
)


def _mk_cells(n, type_name="X"):
    t = StdCellType(type_name)
    return [DesignCell(i, "c%d" % i, t) for i in range(n)]


class TestStdCellType:
    def test_pin_directions(self):
        t = StdCellType("NAND2X1")
        t.add_pin("A", "input")
        t.add_pin("B", "input")
        t.add_pin("Y", "output")
        assert t.input_pins == ["A", "B"]
        assert t.output_pins == ["Y"]
        assert t.pins == ["A", "B", "Y"]

    def test_unknown_direction_is_neither(self):
        t = StdCellType("X")
        t.add_pin("P", "inout")
        assert t.input_pins == [] and t.output_pins == []
        assert t.pins == ["P"]


class TestDesignCell:
    def test_add_cell_pin_routes_by_direction(self):
        t = StdCellType("NAND2X1")
        t.add_pin("A", "input")
        t.add_pin("Y", "output")
        c = DesignCell(0, "c0", t)
        c.add_cell_pin("A", "n1")
        c.add_cell_pin("Y", "n2")
        assert c.input_pin_ref_names == ["A"] and c.input_net_names == ["n1"]
        assert c.output_pin_ref_names == ["Y"] and c.output_net_names == ["n2"]

    def test_defaults(self):
        c = DesignCell(0, "c0", StdCellType("X"))
        assert c.cluster_id == -1
        assert c.cluster is None
        assert c.stop_type is False


class TestDesignNet:
    def test_pred_succ_links(self):
        t = StdCellType("X")
        t.add_pin("A", "input")
        t.add_pin("Y", "output")
        src = DesignCell(0, "s", t)
        dst = DesignCell(1, "d", t)
        net = DesignNet(0, "n")
        net.add_pin("Y", src, False)   # driver
        net.add_pin("A", dst, True)    # sink
        assert net.pred_cell is src and net.pred_pin == "Y"
        assert net.succ_cells == [dst] and net.succ_pins == ["A"]


class TestPatternCluster:
    def test_trace_strips_quotes(self):
        cells = _mk_cells(2)
        cl = DesignPatternCluster(0, "['A','B']", cells, [0, 1], 3)
        assert cl.pattern_extension_trace == "[A,B]"
        assert cl.cluster_type_id == 3
        assert [c.id for c in cl.cells] == [0, 1]

    def test_add_cell(self):
        cells = _mk_cells(2)
        cl = DesignPatternCluster(0, "[A]", cells, [0], 0)
        cl.add_cell(cells[1])
        assert cl.cell_ids == [0, 1]
        assert cl.cells[-1] is cells[1]

    def test_seq_trace_strips_quotes(self):
        s = DesignPatternClusterSeq("['A','B']")
        assert s.pattern_extension_trace == "[A,B]"
        assert s.pattern_clusters == []


class TestPruningAndSorting:
    def test_remove_empty_and_disabled(self):
        cells = _mk_cells(4)
        s1 = DesignPatternClusterSeq("[A]")
        c1 = DesignPatternCluster(0, "[A]", cells, [0], 0)
        c2 = DesignPatternCluster(1, "[A]", cells, [1], 0)
        c2.disabled = True
        s1.add_cluster(c1)
        s1.add_cluster(c2)
        s2 = DesignPatternClusterSeq("[B]")  # no clusters -> dropped
        out = remove_empty_seqs_and_disable_clusters([s1, s2])
        assert len(out) == 1
        assert [c.cluster_id for c in out[0].pattern_clusters] == [0]

    def test_sort_by_coverage_then_size(self):
        cells = _mk_cells(10)

        def make_seq(nclusters, size, cid):
            s = DesignPatternClusterSeq("[A]")
            for k in range(nclusters):
                ids = list(range(k * size, k * size + size))
                s.add_cluster(DesignPatternCluster(cid, "[A]", cells, ids, cid))
            return s

        big_cov = make_seq(3, 2, 0)    # coverage = 6
        small_cov = make_seq(2, 2, 1)  # coverage = 4
        out = sort_pattern_cluster_seqs([small_cov, big_cov])
        assert out[0] is big_cov
        assert out[1] is small_cov


class TestCountUncoveredClusters:
    """Savings de-dup (roadmap P0-2): clusters overlapping cells already
    claimed by an earlier candidate in the same round must not be counted
    again."""

    def test_disjoint_clusters_all_counted(self):
        from blif_graph_util import count_uncovered_clusters
        cells = _mk_cells(6)
        clusters = [DesignPatternCluster(i, "[A]", cells, [2 * i, 2 * i + 1], 0)
                    for i in range(3)]
        covered = set()
        assert count_uncovered_clusters(clusters, covered) == 3
        assert covered == {0, 1, 2, 3, 4, 5}

    def test_overlapping_cluster_skipped_once(self):
        from blif_graph_util import count_uncovered_clusters
        cells = _mk_cells(6)
        covered = set()
        first = [DesignPatternCluster(0, "[A]", cells, [0, 1], 0)]
        second = [DesignPatternCluster(1, "[B]", cells, [1, 2], 0),
                  DesignPatternCluster(2, "[B]", cells, [3, 4], 0)]
        assert count_uncovered_clusters(first, covered) == 1
        # cluster 1 overlaps cell 1 -> skipped; cluster 2 is clean -> counted
        assert count_uncovered_clusters(second, covered) == 1
        assert covered == {0, 1, 3, 4}

    def test_fully_covered_candidate_counts_zero(self):
        from blif_graph_util import count_uncovered_clusters
        cells = _mk_cells(4)
        clusters = [DesignPatternCluster(0, "[A]", cells, [0, 1], 0)]
        covered = {0, 1}
        assert count_uncovered_clusters(clusters, covered) == 0
