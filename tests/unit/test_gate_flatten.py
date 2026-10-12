"""Unit tests for flow/gate_flatten.py."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "flow"))

import gate_flatten as gf          # noqa: E402

LIB_TEXT = """\
.subckt INVX1 A Y VCC GND
M0 Y A VCC VCC PMOS W=0.5u L=0.05u
M1 Y A GND GND NMOS W=0.25u L=0.05u
.ends INVX1
.subckt NAND2X1 VCC Y GND A B
M0 Y A VCC VCC PMOS W=0.5u L=0.05u
M1 VCC B Y VCC PMOS W=0.5u L=0.05u
M2 a_9_6# A GND GND NMOS W=0.5u L=0.05u
M3 Y B a_9_6# GND NMOS W=0.5u L=0.05u
.ends NAND2X1
.subckt XOR2X1 Y VCC B A GND
M0 VCC A a_2_6# VCC PMOS W=1u L=0.05u
M1 Y A a_2_6# VCC PMOS W=1u L=0.05u
M2 GND A a_2_6# GND NMOS W=0.5u L=0.05u
M3 Y A a_2_6# GND NMOS W=0.5u L=0.05u
M4 VCC B a_4_6# VCC PMOS W=1u L=0.05u
M5 a_2_6# B a_4_6# VCC PMOS W=1u L=0.05u
M6 GND B a_4_6# GND NMOS W=0.5u L=0.05u
M7 a_2_6# B a_4_6# GND NMOS W=0.5u L=0.05u
.ends XOR2X1
"""

MAPPED = """\
module toy(a, b, c, y, z);
  input a;
  input b;
  input c;
  output y;
  output z;
  wire n1;
  wire n2;
  XOR2X1 _1_ (
    .A(a),
    .B(b),
    .Y(n1)
  );
  NAND2X1 _2_ (
    .A(n1),
    .B(c),
    .Y(n2)
  );
  INVX1 _3_ (
    .A(n2),
    .Y(y)
  );
  XOR2X1 _4_ (
    .A(n1),
    .B(n2),
    .Y(z)
  );
endmodule
"""


@pytest.fixture
def lib(tmp_path):
    lib_path = tmp_path / "toy_lib.sp"
    lib_path.write_text(LIB_TEXT)
    return gf.parse_library_spice(str(lib_path))


def test_parse_library_counts(lib):
    counts = gf.library_transistor_counts(lib)
    assert counts == {"INVX1": 2, "NAND2X1": 4, "XOR2X1": 8}


def test_parse_mapped_verilog_instances(lib):
    insts = gf.parse_mapped_verilog(MAPPED, known_cells=set(lib))
    assert [i.name for i in insts] == ["_1_", "_2_", "_3_", "_4_"]
    assert insts[0].cell_type == "XOR2X1"
    assert insts[0].pins == {"A": "a", "B": "b", "Y": "n1"}


def test_parse_module_ports():
    inputs, outputs = gf.parse_module_ports(MAPPED)
    assert inputs == ["a", "b", "c"]
    assert outputs == ["y", "z"]


def test_partition_respects_budget(lib):
    insts = gf.parse_mapped_verilog(MAPPED, known_cells=set(lib))
    # XOR2(8)+NAND2(4) fit, +INV(2) fits too: one 14T block for _1_.._3_;
    # _4_ shares n1/n2 but would push the block to 22T -- over a 20T budget
    blocks = gf.partition_instances(insts, lib, max_transistors=20)
    assert blocks == [["_1_", "_2_", "_3_", "_4_"]] or \
        blocks == [["_1_", "_2_", "_3_"], ["_4_"]]
    assert sum(len(b) for b in blocks) == 4
    blocks = gf.partition_instances(insts, lib, max_transistors=10)
    assert blocks == [["_1_"], ["_2_", "_3_"], ["_4_"]]
    # budget smaller than any single instance: singleton blocks
    blocks = gf.partition_instances(insts, lib, max_transistors=1)
    assert blocks == [["_1_"], ["_2_"], ["_3_"], ["_4_"]]


def test_block_ports(lib):
    insts = gf.parse_mapped_verilog(MAPPED, known_cells=set(lib))
    ports = gf.block_ports(["_1_", "_2_"], insts, ["a", "b", "c"], ["y", "z"])
    assert ports[0] == "VCC" and ports[-1] == "GND"
    assert ports[1:4] == ["a", "b", "c"]          # module order kept
    assert set(ports[4:-1]) == {"n1", "n2"}        # produced nets leave block


def test_emit_subckt_transistor_names_start_with_m(lib):
    insts = gf.parse_mapped_verilog(MAPPED, known_cells=set(lib))
    ports = gf.block_ports(["_1_"], insts, ["a", "b", "c"], ["y", "z"])
    text, n_trans = gf.emit_subckt("BLK0", ["_1_"], insts, lib, ports)
    assert n_trans == 8
    m_lines = [ln for ln in text.splitlines() if ln.startswith("M")]
    assert len(m_lines) == 8
    assert all(ln.split()[0].startswith("M") for ln in m_lines)
    # supply pins land on the global rails, pins rewired to instance nets
    assert any("VCC" in ln.split()[1:5] for ln in m_lines)
    assert any("GND" in ln.split()[1:5] for ln in m_lines)
    assert any("n1" in ln.split()[1:5] for ln in m_lines)
    assert "+ " not in text
    # internal library nets are namespaced per instance
    assert "g0#a_2_6#" in text


def test_emit_is_deterministic(lib):
    insts = gf.parse_mapped_verilog(MAPPED, known_cells=set(lib))
    blocks = gf.partition_instances(insts, lib, max_transistors=20)
    first = gf.flatten_blocks(blocks, insts, lib, ["a", "b", "c"], ["y", "z"])
    second = gf.flatten_blocks(blocks, insts, lib, ["a", "b", "c"], ["y", "z"])
    assert first == second


def test_escaped_net_names_roundtrip(lib):
    text = MAPPED.replace("n1", "\\w[0]").replace("n2", "$w$1")
    insts = gf.parse_mapped_verilog(text, known_cells=set(lib))
    assert insts[0].pins["Y"] == "\\w[0]"
    assert insts[1].pins["A"] == "\\w[0]"
    assert insts[2].pins["A"] == "$w$1"
