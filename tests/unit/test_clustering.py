"""Unit tests for heuristic initial clustering (pySrc/BLIFPreProc.py).

Regression covered: in ``heuristic_label_initial_clusters_based_on``
the pattern counter ``labelId`` was incremented even for patterns whose cluster
sequence was discarded, leaving holes in ``clusterTypeId``.  Those holes later
collided with the new-pattern numbering used by main.py.
"""
import pytest

from BLIFPreProc import (
    loadDataAndPreprocess,
    heuristic_label_initial_clusters,
    heuristic_label_initial_clusters_based_on,
)

LIB = "../stdCelllib/gscl45nm.lib"
BLIF = "../benchmark/blif/adder.blif"


@pytest.fixture(scope="module")
def adder_data():
    """Load once; the functions mutate cell state, so re-derive per test."""
    return None


def _preprocess(bypass=False):
    return loadDataAndPreprocess(
        libFileName=LIB, blifFileName=BLIF, startTime=0,
        bypassInitialCluster=bypass)


def test_initial_clustering_structure(in_pysrc):
    G, cells, netlist, types, ds, ml, seqs, cn = _preprocess()
    assert len(seqs) > 0
    for s in seqs:
        assert len(s.patternClusters) > 0
        assert s.patternExtensionTrace.startswith("[")

    ids = [cl.clusterId for s in seqs for cl in s.patternClusters]
    assert len(ids) == len(set(ids)), "cluster ids must be unique"

    # every cluster holds >= 2 cells and a distinct pattern code
    for s in seqs:
        for cl in s.patternClusters:
            assert len(cl.cellIdsContained) >= 2


def test_pattern_ids_dense_for_initial_clustering(in_pysrc):
    G, cells, netlist, types, ds, ml, seqs, cn = _preprocess()
    ids = sorted(set(cl.clusterTypeId for s in seqs for cl in s.patternClusters))
    assert ids == list(range(len(seqs)))


def test_pattern_ids_dense_for_based_on(in_pysrc):
    """Regression: _BasedOn must not leave holes in clusterTypeId."""
    G, cells, netlist, types, ds, ml, seqs, cn = _preprocess()
    target = seqs[0].patternExtensionTrace

    G2, cells2, netlist2, _, _, _, _, _ = _preprocess(bypass=True)
    seqs2, _ = heuristic_label_initial_clusters_based_on(
        G2, cells2, netlist2, target)

    assert len(seqs2) > 0
    ids = sorted(set(cl.clusterTypeId for s in seqs2 for cl in s.patternClusters))
    assert ids == list(range(len(seqs2))), (ids, len(seqs2))


def test_based_on_only_keeps_target_prefix(in_pysrc):
    G, cells, netlist, types, ds, ml, seqs, cn = _preprocess()
    target = seqs[0].patternExtensionTrace

    G2, cells2, netlist2, _, _, _, _, _ = _preprocess(bypass=True)
    seqs2, _ = heuristic_label_initial_clusters_based_on(
        G2, cells2, netlist2, target)

    for s in seqs2:
        assert s.patternExtensionTrace in target or target.startswith(
            s.patternExtensionTrace)
