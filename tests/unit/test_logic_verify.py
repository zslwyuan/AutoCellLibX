"""Unit tests for flow/logic_verify.py."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "flow"))

import logic_verify as lv          # noqa: E402

TOY_LIB = """\
library (toy) {
  cell (XOR2X1) {
    area : 1.0;
    pin(A) { direction : input; }
    pin(B) { direction : input; }
    pin(Y) { direction : output; function : "(A^B)"; }
  }
  cell (INVX1) {
    area : 1.0;
    pin(A) { direction : input; }
    pin(Y) { direction : output; function : "(!A)"; }
  }
  cell (AND2X1) {
    area : 1.0;
    pin(A) { direction : input; }
    pin(B) { direction : input; }
    pin(Y) { direction : output; function : "(A B)"; }
  }
  cell (OR2X1) {
    area : 1.0;
    pin(A) { direction : input; }
    pin(B) { direction : input; }
    pin(Y) { direction : output; function : "(A+B)"; }
  }
  cell (MUX2X1) {
    area : 1.0;
    pin(A) { direction : input; }
    pin(B) { direction : input; }
    pin(S) { direction : input; }
    pin(Y) { direction : output; function : "(!((S A) + (!S B)))"; }
  }
  cell (FAX1) {
    area : 1.0;
    pin(A) { direction : input; }
    pin(B) { direction : input; }
    pin(C) { direction : input; }
    pin(YS) { direction : output; function : "((A^B)^C)"; }
    pin(YC) { direction : output;
              function : "(((A B) + (B C)) + (A C))"; }
  }
}
"""

GOLD_BLIF = """\
.model toy
.inputs a b c
.outputs y z
.names $false
.names $true
1
.names a b n1
10 1
01 1
.names n1 a c y
1-1 1
-10 1
.names n1 c z
10 1
01 1
.end
"""

# n1g = a^b; z = n1g^c; y = (n1g&c) | (a&~c) via gates
GATE_BLIF = """\
.model toy
.inputs a b c
.outputs y z
.names $false
.names $true
1
.gate XOR2X1 A=a B=b Y=n1g
.gate XOR2X1 A=n1g B=c Y=z
.gate AND2X1 A=n1g B=c Y=and1
.gate INVX1 A=c Y=nc
.gate AND2X1 A=a B=nc Y=and2
.gate OR2X1 A=and1 B=and2 Y=y
.end
"""

# same but n1g = a AND b instead of a XOR b -- must be caught
GATE_BLIF_BAD = GATE_BLIF.replace(".gate XOR2X1 A=a B=b Y=n1g",
                                  ".gate AND2X1 A=a B=b Y=n1g")


@pytest.fixture
def lib_funcs():
    return lv.parse_liberty_functions(TOY_LIB)


def test_liberty_function_parser(lib_funcs):
    assert set(lib_funcs) == {"XOR2X1", "INVX1", "AND2X1", "OR2X1",
                              "MUX2X1", "FAX1"}
    # implicit AND adjacency: "(A B)" parses as A&B
    assert lv._eval_ast(lib_funcs["AND2X1"]["Y"], {"A": 1, "B": 0}) == 0
    assert lv._eval_ast(lib_funcs["AND2X1"]["Y"], {"A": 1, "B": 1}) == 1
    # the inverting mux: Y = !((S A) + (!S B)) = S?~A:~B
    env = {"S": 1, "A": 1, "B": 0}
    assert lv._eval_ast(lib_funcs["MUX2X1"]["Y"], env) == 0
    env = {"S": 0, "A": 1, "B": 0}
    assert lv._eval_ast(lib_funcs["MUX2X1"]["Y"], env) == 1
    # multi-output cell: both pins parsed
    assert set(lib_funcs["FAX1"]) == {"YS", "YC"}


def test_parse_blif_names_and_gates():
    blif = lv.parse_blif(GOLD_BLIF)
    assert blif.inputs == ["a", "b", "c"]
    assert blif.outputs == ["y", "z"]
    assert blif.nodes["n1"][0] == "names"
    gate = lv.parse_blif(GATE_BLIF)
    assert gate.nodes["y"][0] == "gate"
    assert gate.nodes["y"][1] == "OR2X1"


def test_sequential_design_rejected(tmp_path):
    bad = GOLD_BLIF.replace(".names n1 c z", ".latch n1 z 0")
    path = tmp_path / "seq.blif"
    path.write_text(bad)
    with pytest.raises(ValueError, match="latch"):
        lv.parse_blif(bad)


def test_equivalent_netlists_pass(tmp_path, lib_funcs):
    gold = tmp_path / "gold.blif"
    gate = tmp_path / "gate.blif"
    gold.write_text(GOLD_BLIF)
    gate.write_text(GATE_BLIF)
    report = lv.verify(str(gold), str(gate), lib_funcs)
    assert report.ok
    assert report.mode == "exhaustive"
    assert report.vectors_checked == 8


def test_broken_netlist_fails_with_counterexample(tmp_path, lib_funcs):
    gold = tmp_path / "gold.blif"
    gate = tmp_path / "gate.blif"
    gold.write_text(GOLD_BLIF)
    gate.write_text(GATE_BLIF_BAD)
    report = lv.verify(str(gold), str(gate), lib_funcs)
    assert not report.ok
    assert report.mismatches
    vector, g_out, m_out = report.mismatches[0]
    assert g_out != m_out


def test_multi_output_gate_simulation(lib_funcs):
    blif = lv.parse_blif("""\
.model fa
.inputs a b c
.outputs s co
.names $false
.names $true
1
.gate FAX1 A=a B=b C=c YS=s YC=co
.end
""")
    out = lv.simulate(blif, {"a": 1, "b": 1, "c": 0}, lib_funcs)
    assert out == {"s": 0, "co": 1}
    out = lv.simulate(blif, {"a": 1, "b": 0, "c": 1}, lib_funcs)
    assert out == {"s": 0, "co": 1}
    out = lv.simulate(blif, {"a": 1, "b": 0, "c": 0}, lib_funcs)
    assert out == {"s": 1, "co": 0}


def test_real_gscl45_liberty_parses():
    repo = os.path.join(os.path.dirname(__file__), "..", "..")
    lib_path = os.path.join(repo, "std_celllib", "gscl45nm.lib")
    if not os.path.exists(lib_path):
        pytest.skip("gscl45nm.lib not found")
    funcs = lv.parse_liberty_functions(open(lib_path).read())
    assert lv._eval_ast(funcs["XOR2X1"]["Y"], {"A": 1, "B": 0}) == 1
    assert lv._eval_ast(funcs["MUX2X1"]["Y"],
                        {"S": 1, "A": 1, "B": 0}) == 0     # inverting mux
    assert lv._eval_ast(funcs["OAI21X1"]["Y"],
                        {"A": 1, "B": 0, "C": 0}) == 1
    assert lv._eval_ast(funcs["OAI21X1"]["Y"],
                        {"A": 1, "B": 0, "C": 1}) == 0
