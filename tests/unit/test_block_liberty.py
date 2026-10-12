"""Unit tests for flow/block_liberty.py."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "flow"))

import block_liberty as bl        # noqa: E402
import gate_flatten as gf         # noqa: E402
import logic_verify as lv         # noqa: E402

TOY_LIB = """\
library (toy) {
  cell (NAND2X1) {
    area : 1.0;
    pin(A) { direction : input; capacitance : 0.001; }
    pin(B) { direction : input; capacitance : 0.001; }
    pin(Y) { direction : output; capacitance : 0;
             max_capacitance : 0.1; function : "(!(A B))"; }
  }
  cell (INVX1) {
    area : 0.5;
    pin(A) { direction : input; capacitance : 0.002; }
    pin(Y) { direction : output; capacitance : 0;
             max_capacitance : 0.2; function : "(!A)"; }
  }
  cell (XOR2X1) {
    area : 2.0;
    pin(A) { direction : input; capacitance : 0.003; }
    pin(B) { direction : input; capacitance : 0.003; }
    pin(Y) { direction : output; capacitance : 0;
             max_capacitance : 0.3; function : "(A^B)"; }
  }
}
"""

MAPPED = """\
module toy(a, b, c, y);
  input a;
  input b;
  input c;
  output y;
  wire n1;
  NAND2X1 _1_ (
    .A(a),
    .B(b),
    .Y(n1)
  );
  XOR2X1 _2_ (
    .A(n1),
    .B(c),
    .Y(y)
  );
endmodule
"""


@pytest.fixture
def lib_funcs():
    return lv.parse_liberty_functions(TOY_LIB)


@pytest.fixture
def insts():
    return gf.parse_mapped_verilog(
        MAPPED, known_cells={"NAND2X1", "INVX1", "XOR2X1"})


def test_compose_two_level_function(lib_funcs, insts):
    funcs = bl.compose_block_functions(["_1_", "_2_"], insts,
                                       lib_funcs, ["y"])
    # y = (!(a b)) ^ c
    assert bl.ast_to_liberty(funcs["y"]) == "((!(a b)) ^ c)"


def test_compose_passthrough_for_block_input(lib_funcs, insts):
    funcs = bl.compose_block_functions(["_1_"], insts, lib_funcs, ["n1"])
    assert bl.ast_to_liberty(funcs["n1"]) == "(!(a b))"


def test_ast_rendering_operators(lib_funcs):
    assert bl.ast_to_liberty(("and", ("net", "a"), ("net", "b"))) == "(a b)"
    assert bl.ast_to_liberty(("or", ("net", "a"), ("net", "b"))) == "(a + b)"
    assert bl.ast_to_liberty(("xor", ("net", "a"), ("net", "b"))) == "(a ^ b)"
    assert bl.ast_to_liberty(("not", ("net", "a"))) == "(!a)"
    assert bl.ast_to_liberty(("const", 1)) == "1"


def test_parse_pin_caps():
    caps = bl.parse_pin_caps(TOY_LIB)
    assert caps[("NAND2X1", "A")]["capacitance"] == 0.001
    assert caps[("XOR2X1", "Y")]["max_capacitance"] == 0.3


def test_block_pin_caps_sums_fanout(lib_funcs, insts):
    caps_lib = bl.parse_pin_caps(TOY_LIB)
    caps = bl.block_pin_caps(["_1_", "_2_"], insts, ["a", "b", "c", "y"],
                             caps_lib)
    assert caps["a"] == 0.001          # NAND2 A
    assert caps["b"] == 0.001          # NAND2 B
    assert caps["c"] == 0.003          # XOR2 B
    assert caps["__max__"]["y"] == 0.3


def test_emit_fragment_structure(lib_funcs, insts):
    funcs = bl.compose_block_functions(["_1_", "_2_"], insts,
                                       lib_funcs, ["y"])
    text = bl.emit_fragment("BLK0", funcs, ["a", "b", "c", "y"],
                            area_um2=10.79,
                            pin_caps={"a": 0.001, "b": 0.001, "c": 0.003,
                                      "__max__": {"y": 0.3}})
    assert "cell (BLK0) {" in text
    assert "area : 10.790000;" in text
    assert 'function : "((!(a b)) ^ c)";' in text
    assert "max_capacitance : 0.300000;" in text
    assert text.count("pin(") == 4


def test_sanitize():
    assert bl._sanitize("\\w[0]") == "_w_0_"
    assert bl._sanitize("_01_") == "_01_"
    assert bl._sanitize("a$b") == "a_b"
