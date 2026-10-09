"""Integration test: mining -> growth -> SPICE export (no ASTRAN needed).

Marked ``slow`` because it runs the real preprocessing on a benchmark.
"""
import os

import pytest

pytestmark = pytest.mark.slow

LIB = "../stdCelllib/gscl45nm.lib"
BLIF = "../benchmark/blif/adder.blif"


def test_mining_growth_and_export(in_pysrc, tmp_path):
    from blif_preproc import load_data_and_preprocess
    from blif_graph_util import sort_pattern_cluster_seqs
    from blif_pattern_growth import grow_sequence_of_clusters
    from spice import load_spice_subcircuits, export_spice_netlist

    G, cells, netlist, types, ds, ml, seqs, cn = load_data_and_preprocess(
        lib_file_name=LIB, blif_file_name=BLIF, start_time=0)
    assert len(seqs) > 0, "no patterns mined"
    seqs = sort_pattern_cluster_seqs(seqs)

    new_seqs, pattern_num = grow_sequence_of_clusters(G, seqs[0], len(seqs), len(seqs))
    assert pattern_num >= len(seqs)
    assert len(new_seqs) > 0

    subs = load_spice_subcircuits("../stdCelllib/cellsAstranFriendly.sp")
    export_spice_netlist(new_seqs[0], subs, 0, str(tmp_path))
    out = os.path.join(str(tmp_path), "COMPLEX0.sp")
    assert os.path.exists(out)
    assert open(out).read().startswith(".subckt COMPLEX0")
