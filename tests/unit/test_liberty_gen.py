"""Unit tests for pySrc/liberty_gen.py (COMPLEX cell .lib generation)."""
import pytest

from liberty_gen import (DEFAULT_LOADS, DEFAULT_SLEWS, _substitute,
                         generateComplexLiberty, loadLibertyFunctions)

LIB = "../stdCelllib/gscl45nm.lib"
BLIF = "../benchmark/blif/adder.blif"


def test_load_liberty_functions(in_pysrc):
    funcs = loadLibertyFunctions(LIB)
    assert ("NAND2X1", "Y") in funcs
    assert funcs[("NAND2X1", "Y")] == "(!(A B))"
    assert funcs[("INVX1", "Y")] == "(!A)"


def test_substitute_whole_word():
    # the replacement is parenthesised to preserve precedence
    assert _substitute("(!(A B))", {"A": "(x y)"}) == "(!(((x y)) B))"
    # pin name must not match inside a longer name
    assert _substitute("(!(AB A))", {"A": "x"}) == "(!(AB (x)))"


def test_generate_real_cluster_liberty(in_pysrc):
    from blif_preproc import (gen_graph_from_liberty_and_blif,
                             heuristic_label_initial_clusters)
    from blif_graph_util import sortPatternClusterSeqs
    from electrical import loadCellElectricalMetrics
    from timing_power import loadTimingPower

    G, cells, netlist, types = gen_graph_from_liberty_and_blif(LIB, BLIF)
    seqs, _ = heuristic_label_initial_clusters(G, cells, netlist)
    seq = sortPatternClusterSeqs(seqs)[0]
    em = loadCellElectricalMetrics(LIB)
    tp = loadTimingPower(LIB)
    funcs = loadLibertyFunctions(LIB)
    text, report = generateComplexLiberty(
        seq, "COMPLEX0", 2.28, tp, em, funcs)

    assert "cell (COMPLEX0)" in text
    assert report["area"] == pytest.approx(2.28 * 2.47)
    assert report["leakage"] > 0
    assert report["inputs"] > 0 and report["outputs"] >= 1
    assert "cell_rise" in text and "internal_power" in text
    assert "function :" in text
    # delay values must be non-negative and finite
    import re
    vals = [float(v) for v in
            re.findall(r"[-+]?\d+\.\d+", text)]
    assert all(v >= 0 for v in vals)
    # the fragment must parse as liberty
    from liberty.parser import parse_liberty
    parsed = parse_liberty("library (t) {\n" + text + "}\n")
    cells_parsed = parsed.get_groups("cell")
    assert len(cells_parsed) == 1
