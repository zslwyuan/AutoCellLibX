"""Integration test: mining -> growth -> SPICE export (no ASTRAN needed).

Marked ``slow`` because it runs the real preprocessing on a benchmark.
"""
import os

import pytest

pytestmark = pytest.mark.slow

LIB = "../stdCelllib/gscl45nm.lib"
BLIF = "../benchmark/blif/adder.blif"


def test_mining_growth_and_export(in_pysrc, tmp_path):
    from blif_preproc import loadDataAndPreprocess
    from blif_graph_util import sortPatternClusterSeqs
    from blif_pattern_growth import grow_sequence_of_clusters
    from spice import load_spice_subcircuits, exportSpiceNetlist

    G, cells, netlist, types, ds, ml, seqs, cn = loadDataAndPreprocess(
        libFileName=LIB, blifFileName=BLIF, startTime=0)
    assert len(seqs) > 0, "no patterns mined"
    seqs = sortPatternClusterSeqs(seqs)

    newSeqs, patternNum = grow_sequence_of_clusters(G, seqs[0], len(seqs), len(seqs))
    assert patternNum >= len(seqs)
    assert len(newSeqs) > 0

    subs = load_spice_subcircuits("../stdCelllib/cellsAstranFriendly.sp")
    exportSpiceNetlist(newSeqs[0], subs, 0, str(tmp_path))
    out = os.path.join(str(tmp_path), "COMPLEX0.sp")
    assert os.path.exists(out)
    assert open(out).read().startswith(".subckt COMPLEX0")
