"""Unit tests for pySrc/portorder.py (P1-9)."""
import os

from portorder import (generate_port_orders, parse_subckt_header,
                       write_port_order_variants)

SP = """.subckt COMPLEX1 cl2#Y GND VCC cl1#B cl1#A cl2#A cl2#B cl2#C
Mcl0#0 VCC cl1#Y cl0#a_2_6# VCC PMOS W=1u L=0.05u
Mcl0#1 GND cl1#Y GND GND NMOS W=0.5u L=0.05u
.ends COMPLEX1
* pattern code: [XNOR2X1,XOR2X1,OAI21X1]
"""


def test_parse_header():
    name, ports = parse_subckt_header(SP.split("\n"))
    assert name == "COMPLEX1"
    assert ports[0] == "cl2#Y" and "VCC" in ports and "GND" in ports


def test_variants_deterministic_unique_and_identity_first():
    ports = ["cl2#Y", "GND", "VCC", "cl1#B", "cl1#A", "cl2#A"]
    a = generate_port_orders(ports, 4)
    b = generate_port_orders(ports, 4)
    assert a == b                                # deterministic
    assert a[0] == ports                         # identity first
    assert len({tuple(v) for v in a}) == len(a)  # unique
    assert all(sorted(v) == sorted(ports) for v in a)
    assert len(a) <= 4


def test_canonical_puts_supply_first():
    ports = ["cl2#Y", "GND", "VCC", "cl1#B", "cl1#A"]
    canonical = generate_port_orders(ports, 2)[1]
    assert canonical[:2] == ["GND", "VCC"]
    assert canonical[2:] == sorted(["cl1#A", "cl1#B", "cl2#Y"])


def test_write_variants_rewrites_header_only(tmp_path):
    src = tmp_path / "COMPLEX1.sp"
    src.write_text(SP)
    out_dir = tmp_path / "variants"
    paths = write_port_order_variants(str(src), str(out_dir), 3)
    assert len(paths) == 3
    src_lines = SP.split("\n")
    for p in paths:
        lines = open(p).read().split("\n")
        assert lines[0].startswith(".subckt COMPLEX1 ")
        assert lines[1:] == src_lines[1:]       # body untouched
        assert sorted(lines[0].split()[2:]) == sorted(src_lines[0].split()[2:])
    # v0 is byte-identical to the source
    assert open(paths[0]).read() == SP


def test_real_complex1_parses(in_pysrc):
    path = "./outputs/adder/COMPLEX1.sp"
    if not os.path.exists(path):
        import pytest
        pytest.skip("outputs snapshot not present")
    name, ports = parse_subckt_header(open(path).read().split("\n"))
    assert name == "COMPLEX1"
    assert "VCC" in ports and "GND" in ports
