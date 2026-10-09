"""Unit tests for pySrc/reuse.py (synthesis-reuse eligibility)."""
from blif_graph_util import StdCellType, DesignCell, DesignNet, \
    DesignPatternCluster, DesignPatternClusterSeq
from reuse import function_complexity, interface_output_count, reuse_eligible
from liberty_gen import load_liberty_functions

LIB = "../stdCelllib/gscl45nm.lib"


def _cell(cid, name):
    t = StdCellType(name)
    t.add_pin("A", "input")
    t.add_pin("B", "input")
    t.add_pin("Y", "output")
    return DesignCell(cid, "c%d" % cid, t)


def _pins(*cells):
    for c in cells:
        c.add_cell_pin("A", c.name + "_a")
        c.add_cell_pin("B", c.name + "_b")
        c.add_cell_pin("Y", c.name + "_y")


def _link(src, dst, nid):
    net = DesignNet(nid, "n%d" % nid)
    net.add_pin("Y", src, False)
    net.add_pin("A", dst, True)
    src.add_output_net(net)
    dst.add_input_net(net)


def _output_net(src, nid):
    """A dangling output net (no loads -> counts as an escaping pin)."""
    net = DesignNet(nid, "n%d" % nid)
    net.add_pin("Y", src, False)
    src.add_output_net(net)
    return net


def _single_output_cluster():
    """NAND2(a,b) -> OR2 <- NAND2(c,d): one escaping output (OR2.Y)."""
    n1, n2, o = _cell(0, "NAND2X1"), _cell(1, "NAND2X1"), _cell(2, "OR2X1")
    _pins(n1, n2, o)
    _link(n1, o, 0)
    _link(n2, o, 1)
    _output_net(o, 2)                       # OR2.Y escapes
    cells = [n1, n2, o]
    cluster = DesignPatternCluster(0, "[NAND2X1,NAND2X1,OR2X1]",
                                   cells, [0, 1, 2], 0)
    seq = DesignPatternClusterSeq("[NAND2X1,NAND2X1,OR2X1]")
    seq.add_cluster(cluster)
    return seq


def load_electrical_metrics():
    from electrical import load_cell_electrical_metrics
    return load_cell_electrical_metrics("../stdCelllib/gscl45nm.lib")


def test_function_complexity():
    assert function_complexity("(!(A B))") == (2, 2)
    # two logical levels read as paren depth 4 (each operator level is
    # parenthesised, plus the substitution wrapping)
    assert function_complexity("((A B)+(C D))") == (4, 2)
    assert function_complexity(None) is None


def test_single_output_cluster_is_eligible(in_pysrc):
    seq = _single_output_cluster()
    members = seq.pattern_clusters[0].cells
    funcs = load_liberty_functions("../stdCelllib/gscl45nm.lib")
    assert interface_output_count(members) == 1
    r = reuse_eligible(members, funcs)
    assert r["eligible"] is True, r
    f = list(r["functions"].values())[0]
    assert function_complexity(f)[0] == 4


def test_multi_output_cluster_is_not_eligible(in_pysrc):
    """An outside load on a member output makes it escape -> 2 outputs."""
    n1, n2, o = _cell(0, "NAND2X1"), _cell(1, "NAND2X1"), _cell(2, "OR2X1")
    ext = _cell(3, "INVX1")
    _pins(n1, n2, o, ext)
    _link(n1, o, 0)
    _link(n2, o, 1)
    _output_net(o, 3)
    # fanout is one net with several loads in the real flow: add ext as a
    # second load of n1's output net (n0)
    net0 = n1.output_nets[0]
    net0.add_pin("A", ext, True)
    ext.add_input_net(net0)
    cells = [n1, n2, o, ext]
    cluster = DesignPatternCluster(0, "[NAND2X1,NAND2X1,OR2X1]",
                                   cells, [0, 1, 2], 0)
    r = reuse_eligible(cluster.cells,
                      load_liberty_functions("../stdCelllib/gscl45nm.lib"))
    assert r["outputs"] == 2
    assert r["eligible"] is False
    assert "outputs=2" in r["reason"]


def test_adder_top_patterns_are_not_eligible(in_pysrc):
    """Evidence for AUDIT 5.25: the mined patterns are all multi-output,
    which is why abc never touches them -- the reuse path needs the
    internalize_only growth bias or single-output seeds."""
    from blif_preproc import gen_graph_from_liberty_and_blif, \
        heuristic_label_initial_clusters
    from blif_graph_util import sort_pattern_cluster_seqs
    G, cells, netlist, types = gen_graph_from_liberty_and_blif(
        LIB, "../benchmark/blif/adder.blif")
    seqs, _ = heuristic_label_initial_clusters(G, cells, netlist)
    seqs = sort_pattern_cluster_seqs(seqs)
    funcs = load_liberty_functions(LIB)
    eligible = 0
    for seq in seqs[:10]:
        r = reuse_eligible(seq.pattern_clusters[0].cells, funcs)
        if r["eligible"]:
            eligible += 1
        assert r["outputs"] >= 1
    assert eligible == 0


def test_end_to_end_abc_uses_generated_single_output_complex(in_pysrc):
    """The full reuse path: a single-output complex cluster -> .lib
    fragment -> abc picks it up on a design with the matching function.
    Self-skips without the vendored abc-capable yosys."""
    import json, os, re, subprocess, tempfile
    from yosys_import import find_yosys
    from yosys_eval import build_extended_liberty
    from electrical import load_cell_electrical_metrics
    from timing_power import load_timing_power
    from liberty_gen import load_liberty_functions, generate_complex_liberty

    exe = find_yosys()
    if (exe is None):
        pytest.skip("no yosys executable")
    seq = _single_output_cluster()
    em = load_electrical_metrics()
    tp = load_timing_power("../stdCelllib/gscl45nm.lib")
    funcs = load_liberty_functions("../stdCelllib/gscl45nm.lib")
    frag, _report = generate_complex_liberty(
        seq, "COMPLEX_SO", 2.0, tp, em, funcs)
    base = open("../stdCelllib/gscl45nm.lib").read()
    ext = build_extended_liberty(base, [frag])
    with tempfile.NamedTemporaryFile("w", suffix=".lib",
                                     delete=False) as f:
        f.write(ext)
        lib_path = f.name
    with tempfile.NamedTemporaryFile("w", suffix=".v",
                                     delete=False) as f:
        f.write("module top(input a, b, c, d, output y);"
                " assign y = ~(a & b) | ~(c & d); endmodule\n")
        v_path = f.name
    try:
        env = dict(os.environ)
        # yosys' abc temp dir breaks on mixed separators: give it a
        # forward-slash TEMP so "<TEMP>/yosys-abc-XXX/output.blif" works
        env["TEMP"] = env.get("TEMP", "").replace("\\", "/")
        env["TMP"] = env.get("TMP", "").replace("\\", "/")
        proc = subprocess.run(
            [exe, "-Q", "-T",
             "-p", ("read_liberty -lib %s; read -sv %s; synth -top top; "
                    "abc -liberty %s; stat -json" % (lib_path, v_path,
                                                     lib_path))],
            capture_output=True, text=True, timeout=300, env=env)
        m = re.search(r"\{.*\}", proc.stdout + proc.stderr, re.S)
        assert m is not None, (proc.returncode, (proc.stderr or "")[-200:])
        hist = list(json.loads(m.group(0))["modules"].values())[0][
            "num_cells_by_type"]
        assert hist.get("COMPLEX_SO", 0) >= 1, hist
    finally:
        os.unlink(lib_path)
        os.unlink(v_path)


def test_function_to_verilog():
    from reuse import function_to_verilog, verilog_design_for_function
    assert function_to_verilog("(!(A B))", {"A": "a", "B": "b"}) == "( ~ ( a & b ) )"
    assert function_to_verilog("(A+B)", {"A": "a", "B": "b"}) == "( a | b )"
    f = "(((!((cl0_A) (cl0_B))))+((!((cl1_A) (cl1_B)))))"
    expected = "( ( ( ~ ( ( a ) & ( b ) ) ) ) | ( ( ~ ( ( c ) & ( d ) ) ) ) )"
    got = function_to_verilog(f, {"cl0_A": "a", "cl0_B": "b", "cl1_A": "c", "cl1_B": "d"})
    assert got == expected, (got, expected)
    v = verilog_design_for_function("(!(A B))")
    assert "assign y = ( ~ ( a & b ) )" in v and "module top" in v
