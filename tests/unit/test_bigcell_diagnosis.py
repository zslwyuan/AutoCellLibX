"""Diagnosis-pinned behaviour of the bigcell decomposition chain on the
SEQUENTIAL (feedback-loop) cells: LATCH and DFFNEGX1.

The 2026-10 round-5 benchmark left the sequential class unsupported on a
suspected structural-model defect ("the device graph is cyclic -- does
the decomposition loop/garbage/misdecompose?").  These tests pin what
actually happens, so the verdict is regression-proof:

- the diffusion graph of these cells DOES contain cycles (the P/N tower
  pairs close through the VCC/GND rails: M1-M2-M3-M4 in LATCH), but the
  cycles are cut at gate-sharing / degree-4 junction nets, so
  find_series_chains terminates and produces electrically correct
  sub-chains -- no infinite loop, no garbage blocks;
- the feedback hub nets (a_23_6# in LATCH/DFFNEGX1) carry FOUR diffusion
  terminals plus gates: they are neither series-internal (gateCount > 0)
  nor degree-3 couplers under the default max_coupler_degree=3, so the
  default decomposition is exactly smt_engine's base blocks;
- totality and the abutment contract ("members chain") hold, and the
  fold -> seeds -> euler -> layout chain runs to a legal placement.

The routing failure of these cells is therefore NOT a decomposition
defect: it is the routing vocabulary (gate contacts of narrow devices
caged by the feedback net's dual diffusion accesses + the corridor T3
contest), diagnosed in flow/_stage3_check/diag_seq_cycle.py,
diag_forced_census.py and diag_corridor_sweep.py.
"""
import re

import pytest

from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import (CellNetlist, build_diffusion_blocks,
                                find_series_chains)
from bigcell_engine.netlist_ext import (build_bigcell_blocks, fold_devices,
                                        row_seeds)
from bigcell_engine.geometry import N_ROW, P_ROW, layout_cell
from bigcell_engine.place_euler import euler_orderings

LIB = None


def _cell(flow_dir, name):
    global LIB
    if LIB is None:
        import os
        path = os.path.join(flow_dir, "..", "std_celllib",
                            "cellsAstranFriendly.sp")
        LIB = open(path).read()
    m = re.search(r"\.subckt\s+%s\b(.*?)\.ends" % name, LIB, re.S | re.I)
    return CellNetlist(parse_spice_subckt(".subckt %s%s\n.ends"
                                          % (name, m.group(1))))


def _check_blocks(netlist, blocks):
    seen = {}
    for block in blocks:
        for a, b in zip(block.members, block.members[1:]):
            assert a.right_net == b.left_net, (block.kind, a.name, b.name)
        for member in block.members:
            seen[member.device.name] = seen.get(member.device.name, 0) + 1
    assert sorted(seen) == sorted(d.name for d in netlist.devices)
    assert all(count == 1 for count in seen.values())


@pytest.mark.parametrize("name", ["LATCH", "DFFNEGX1"])
def test_cyclic_netlist_decomposes_total_and_chaining(flow_dir, name):
    """The feedback loop does not hang, duplicate or misplace a device."""
    nl = _cell(flow_dir, name)
    chains, _internal = find_series_chains(nl)
    # termination is implicit (the call returned); coverage + validity:
    chained = [d for c in chains for d in c]
    assert sorted(d.name for d in chained) == \
        sorted(d.name for d in nl.devices)
    blocks = build_bigcell_blocks(nl)
    _check_blocks(nl, blocks)


def test_latch_cycle_is_cut_at_the_feedback_hub(flow_dir):
    """LATCH's P tower M1-M2-M3-M4 closes a diffusion cycle through VCC
    (M1: a_18_74#-VCC, M4: VCC-a_35_84#, M2/M3 chaining a_23_6#).  The
    cycle must be cut at a_23_6# (4 diffusion terminals + 2 gates) into
    the two series sub-chains [M1, M2] and [M3, M4]."""
    nl = _cell(flow_dir, "LATCH")
    blocks = build_bigcell_blocks(nl)
    by_first = {b.first.name: b for b in blocks if b.kind == "series"}
    m1 = by_first["M1"]
    assert [(m.name, m.left_net, m.right_net) for m in m1.members] == \
        [("M1", "VCC", "a_18_74#"), ("M2", "a_18_74#", "a_23_6#")]
    m3 = by_first["M3"]
    assert [(m.name, m.left_net, m.right_net) for m in m3.members] == \
        [("M3", "a_23_6#", "a_35_84#"), ("M4", "a_35_84#", "VCC")]
    # the feedback hub is a degree-4 node: NOT a coupler under the
    # default, so no tree block absorbs the two sub-chains
    assert not any(b.kind == "tree" for b in blocks)


def test_sequential_chain_runs_to_a_legal_placement(flow_dir):
    """fold -> blocks -> seeds -> euler -> layout_cell terminates with a
    total placement for both sequential cells (the rung-3 chain's
    non-routing stages are cycle-safe)."""
    for name in ("LATCH", "DFFNEGX1"):
        nl = _cell(flow_dir, name)
        nl3, leg_widths = fold_devices(nl)
        blocks = build_bigcell_blocks(nl3)
        _check_blocks(nl3, blocks)
        seeds = row_seeds(blocks, leg_widths)
        assert set(seeds) == {P_ROW, N_ROW}
        order_p, order_n = euler_orderings(seeds, leg_widths)
        placements, width = layout_cell(order_p, order_n, leg_widths)
        assert len(placements) == len(nl3.devices)
        assert width >= 1
        cols = set()
        for p in placements.values():
            assert p.start_col >= 0 and p.end_col > p.start_col
            cols.add((p.row, p.start_col))
        assert len(cols) == len(placements)    # no two devices per slot
