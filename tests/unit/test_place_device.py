"""Unit tests for flow/bigcell_engine/place_device.py: the
DEVICE-granularity placement space -- a strict superset of ASTRAN's block
spaces (the structural answer to AUDIT 5.50-5.58's entangled-wall
class).

This file pins:

- the two views: blocks_to_devices / devices_to_blocks are total,
  orientation-preserving, and the ROUND TRIP reproduces a block-chain
  arrangement's geometry (placement, width), member walk and census
  exactly -- adjacent same-net blocks fuse into one run (their shared
  boundary carries no geometry), break-separated blocks reproduce
  block-for-block;
- the converted view feeds the EXISTING machinery unchanged:
  layout_cell -> route_cell(blocks=view) -> verify_cell(blocks=view)
  closes NAND2X1 end to end on a device arrangement;
- the move set: every drawn move type (flip / adjacent swap / any-pair
  swap / row-move, single- and both-row composites) is legal, and
  apply + apply(inverse) restores the arrangement and the cost exactly;
- the incremental==full discipline: random seeded device-move sequences
  keep the incremental cost equal to the full recompute (asserted by
  device_sa itself at every iteration boundary and here after every
  random sequence);
- determinism (invariant 9): place_devices is a pure function of its
  inputs -- in-process double calls agree, and the arrangement
  signature is PYTHONHASHSEED-independent across subprocesses;
- the census steering: the winner never has a worse cage than the best
  seed (the cage term dominates the legacy cost), the (0,0)
  short-circuit stops at the winning seed, and the reported census
  equals the public place_sa penalties on the returned arrangement;
- budget scaling: place_devices runs to completion at budget 1 (the
  iteration-count budget, never wall-clock) on the biggest corpus cell.

Fast tests use INV/NAND2/COMPLEX0-scale inputs; the XOR2X1 evidence uses
the library cell through the flow_dir fixture.  All randomness stays
inside the content-hash seed discipline (invariants 8/9).
"""
import os
import random
import re
import subprocess
import sys

import pytest

from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from bigcell_engine.geometry import layout_cell
from bigcell_engine.netlist_ext import (build_bigcell_blocks, fold_devices,
                                        mirror_block, row_seeds)
from bigcell_engine.place_euler import euler_orderings
from bigcell_engine.place_sa import (cell_seed, crossing_cage_penalty,
                                     gate_cage_penalty, ordering_signature)
from bigcell_engine import place_device as pdev
from bigcell_engine.place_device import (DEVICE_ENGINE_VERSION, _DeviceState,
                                         blocks_to_devices, device_census,
                                         device_sa, device_seed, device_seeds,
                                         devices_to_blocks, place_devices)

INV = """\
.subckt INV VCC Y A GND
Mp Y A VCC VCC PMOS W=0.5u L=0.05u
Mn Y A GND GND NMOS W=0.5u L=0.05u
.end
"""

NAND2 = """\
.subckt NAND2 VCC Y A B GND
MpA Y A VCC VCC PMOS W=0.5u L=0.05u
MpB VCC B Y VCC PMOS W=0.5u L=0.05u
MnA Y A n1 GND NMOS W=0.5u L=0.05u
MnB n1 B GND GND NMOS W=0.5u L=0.05u
.end
"""

COMPLEX0 = """\
.subckt TEST14T VCC cl0#Y GND cl1#Y cl2#Y cl1#A cl1#B cl2#B cl2#A
Mcl0#0 cl0#Y cl1#Y VCC VCC PMOS W=0.5u L=0.05u
Mcl0#1 VCC cl2#Y cl0#Y VCC PMOS W=0.5u L=0.05u
Mcl0#2 cl0#a_9_6# cl1#Y GND GND NMOS W=0.5u L=0.05u
Mcl0#3 cl0#Y cl2#Y cl0#a_9_6# GND NMOS W=0.5u L=0.05u
Mcl1#0 cl1#Y cl1#A VCC VCC PMOS W=0.5u L=0.05u
Mcl1#1 VCC cl1#B cl1#Y VCC PMOS W=0.5u L=0.05u
Mcl1#2 cl1#a_9_6# cl1#A GND GND NMOS W=0.5u L=0.05u
Mcl1#3 cl1#Y cl1#B cl1#a_9_6# GND NMOS W=0.5u L=0.05u
Mcl2#0 cl2#a_9_54# cl2#A cl2#a_2_54# VCC PMOS W=1u L=0.05u
Mcl2#1 VCC cl2#B cl2#a_9_54# VCC PMOS W=1u L=0.05u
Mcl2#2 cl2#Y cl2#a_2_54# VCC VCC PMOS W=0.5u L=0.05u
Mcl2#3 cl2#a_2_54# cl2#A GND GND NMOS W=0.25u L=0.05u
Mcl2#4 GND cl2#B cl2#a_2_54# GND NMOS W=0.25u L=0.05u
Mcl2#5 cl2#Y cl2#a_2_54# GND GND NMOS W=0.25u L=0.05u
.end
"""


def _pipeline(text):
    """fold -> blocks -> seeds -> euler: the pre-SA block chain."""
    nl0 = CellNetlist(parse_spice_subckt(text))
    nl, leg_widths = fold_devices(nl0)
    seeds = row_seeds(build_bigcell_blocks(nl), leg_widths)
    eop, eon = euler_orderings(seeds, leg_widths)
    return nl, leg_widths, eop, eon


def _lib_subckt(cell, flow_dir):
    path = os.path.join(flow_dir, "..", "std_celllib",
                        "cellsAstranFriendly.sp")
    text = open(path, errors="ignore").read()
    return next(m.group(0) for m in re.finditer(
        r"\.subckt\s+%s\b.*?\.ends" % cell, text, re.S | re.I))


def _member_walk(rows):
    """The concatenated (device, left, right) member walk of a block view
    -- the geometry-bearing content, kind labels aside."""
    return tuple((m.device.name, m.left_net, m.right_net)
                 for row in rows for block in row for m in block.members)


def _walk_of_rows(ordering_p, ordering_n):
    return _member_walk((ordering_p, ordering_n))


def _placements_equal(pa, pb):
    if set(pa) != set(pb):
        return False
    for dev, p in pa.items():
        q = pb[dev]
        if (p.row, p.start_col, p.legs, p.leg_width_cols) != \
                (q.row, q.start_col, q.legs, q.leg_width_cols):
            return False
    return True


# --------------------------------------------------------------------------
# the two views
# --------------------------------------------------------------------------

def test_blocks_to_devices_is_total_and_orientation_preserving():
    nl3, lw, eop, eon = _pipeline(COMPLEX0)
    dp, dn = blocks_to_devices(eop, eon)
    # every device exactly once, polarity per row
    names_p = [b.members[0].device.name for b in dp]
    names_n = [b.members[0].device.name for b in dn]
    devices = sorted(d.name for d in nl3.devices)
    assert sorted(names_p + names_n) == devices
    assert all(b.members[0].device.is_p for b in dp)
    assert all(not b.members[0].device.is_p for b in dn)
    # each member's orientation kept verbatim
    for row, op in ((dp, eop), (dn, eon)):
        flat = [(m.device.name, m.left_net, m.right_net)
                for b in op for m in b.members]
        assert flat == [(b.members[0].device.name, b.members[0].left_net,
                         b.members[0].right_net) for b in row]


def test_round_trip_reproduces_geometry_member_walk_and_census():
    """A block-chain arrangement converted to devices and back reproduces
    it: identical placement, width, member walk and both censuses."""
    for text in (INV, NAND2, COMPLEX0):
        nl3, lw, eop, eon = _pipeline(text)
        dp, dn = blocks_to_devices(eop, eon)
        bp, bn = devices_to_blocks(dp, dn)
        pl1, w1 = layout_cell(eop, eon, lw)
        pl2, w2 = layout_cell(bp, bn, lw)
        assert w1 == w2
        assert _placements_equal(pl1, pl2)
        assert _walk_of_rows(eop, eon) == _walk_of_rows(bp, bn)
        assert device_census(dp, dn, nl3, lw) == {
            "cage": gate_cage_penalty(eop, eon, nl3, lw)[0],
            "crossing": crossing_cage_penalty(eop, eon, nl3, lw)[0]}


def _break_separated_row(seeds):
    """Deterministically find a row arrangement where every adjacent
    block boundary is a diffusion break (facing nets differ), searching
    both rows' flip combinations in a fixed order; None when the cell's
    rows abut everywhere (COMPLEX0 is not such a cell)."""
    import itertools
    for r in (0, 1):
        row = seeds[r]
        for flips in itertools.product((0, 1), repeat=len(row)):
            cand = [mirror_block(b) if f else b for b, f in zip(row, flips)]
            if all(cand[i].right_net != cand[i + 1].left_net
                   for i in range(len(cand) - 1)):
                return r, cand
    return None, None


def test_round_trip_block_list_exact_when_break_separated():
    """When adjacent blocks face DIFFERENT nets (a break column between
    every pair), the fused view reproduces the block list member-for-
    member (kinds aside -- the fused label is "device_run")."""
    nl3, lw, _eop, _eon = _pipeline(COMPLEX0)
    seeds = row_seeds(build_bigcell_blocks(nl3), lw)
    r, row = _break_separated_row(seeds)
    assert row is not None
    other = seeds[1 - r]
    # polarity-ordered explode: the found row goes into its own slot
    dp, dn = blocks_to_devices(row, other) if r == 0 \
        else blocks_to_devices(other, row)
    bp, bn = devices_to_blocks(dp, dn)
    src = bp if r == 0 else bn
    assert [(tuple((m.device.name, m.left_net, m.right_net)
                   for m in b.members)) for b in row] == \
        [(tuple((m.device.name, m.left_net, m.right_net)
                for m in b.members)) for b in src]


def test_round_trip_fuses_same_net_adjacent_blocks():
    """Two adjacent blocks sharing their facing net fuse into ONE run --
    the boundary carries no geometry (place_row inserts no break column
    there), so placement and census are unchanged."""
    nl3, lw, _eop, _eon = _pipeline(NAND2)
    seeds = row_seeds(build_bigcell_blocks(nl3), lw)
    # NAND2's P row is one parallel block whose left net is VCC: any
    # second VCC-left block placed adjacent shares the facing edge
    blocks = build_bigcell_blocks(nl3)
    p_blocks = [b for b in blocks if b.first.is_p]
    assert len(p_blocks) == 1
    b0 = p_blocks[0]
    # [b0 | mirrored b0] face on VCC (b0.right == mirror(b0).left)
    row = [b0, mirror_block(b0)]
    assert row[0].right_net == row[1].left_net
    pl1, w1 = layout_cell(row, seeds[1], lw)
    dp, dn = blocks_to_devices(row, seeds[1])
    bp, _bn = devices_to_blocks(dp, dn)
    pl2, w2 = layout_cell(bp, seeds[1], lw)
    # the whole chain shares every facing edge -> ONE fused run of all
    # four members (the block boundary between b0 and mirror(b0) carries
    # no geometry: place_row inserts no break column there)
    assert len(bp) == 1 and len(bp[0].members) == 2 * len(b0.members)
    assert _placements_equal(pl1, pl2) and w1 == w2


def test_devices_to_blocks_kinds_are_labels_only():
    """The fused kind labels are exactly "single" / "device_run"."""
    nl3, lw, eop, eon = _pipeline(COMPLEX0)
    dp, dn = blocks_to_devices(eop, eon)
    bp, bn = devices_to_blocks(dp, dn)
    kinds = {b.kind for row in (bp, bn) for b in row}
    assert kinds <= {"single", "device_run"}
    assert "device_run" in kinds or all(len(b.members) == 1
                                        for row in (bp, bn) for b in row)


# --------------------------------------------------------------------------
# the existing machinery consumes the converted view unchanged
# --------------------------------------------------------------------------

def test_converted_view_closes_nand2_through_route_and_verify(in_flow):
    """The acceptance: a device arrangement, converted to the block view,
    lays out, routes (the production two-phase grid router,
    blocks-aware) and verifies CLEAN through the existing machinery with
    zero changes to route/verify/gds."""
    from bigcell_engine.route_grid import route_cell
    from smt_engine.verify import verify_cell
    nl3, lw, _eop, _eon = _pipeline(NAND2)
    op, on, bd = place_devices(nl3, lw)
    assert bd["census"] == {"cage": 0, "crossing": 0}
    bp, bn = devices_to_blocks(op, on)
    placements, width = layout_cell(bp, bn, lw)
    view = list(bp) + list(bn)
    route = route_cell(nl3, placements, width, lw, blocks=view)
    assert route.ok
    report = verify_cell(nl3, placements, route, blocks=view)
    assert report.ok()


def test_converted_view_layout_invariants_hold_without_a_route(in_flow):
    """verify's LAYOUT invariants (abutment / diffusion break /
    overlap) depend only on the placement and the block view: even a
    failed route must never report a layout violation for a converted
    device arrangement."""
    from bigcell_engine.route_grid import route_cell
    from smt_engine.verify import verify_cell
    nl3, lw, _eop, _eon = _pipeline(COMPLEX0)
    op, on, _bd = place_devices(nl3, lw, budget=2)
    bp, bn = devices_to_blocks(op, on)
    placements, width = layout_cell(bp, bn, lw)
    view = list(bp) + list(bn)
    route = route_cell(nl3, placements, width, lw, blocks=view,
                       max_attempts=200)
    report = verify_cell(nl3, placements, route, blocks=view)
    bad = [v for v in report.violations
           if "abut" in v or "diffusion break" in v or "overlap" in v]
    assert bad == []


def test_die_view_reads_the_converted_orientation(in_flow):
    """The converted view is orientation-consistent for die_view: the
    shared die orientation map agrees with the arrangement's own member
    orientations on every device."""
    from smt_engine import die_view
    nl3, lw, _eop, _eon = _pipeline(COMPLEX0)
    op, on, _bd = place_devices(nl3, lw, budget=2)
    bp, bn = devices_to_blocks(op, on)
    placements, width = layout_cell(bp, bn, lw)
    view = list(bp) + list(bn)
    dmap = die_view.die_orientation_map(nl3, placements, blocks=view)
    for row in (op, on):
        for b in row:
            m = b.members[0]
            assert dmap[m.device.name] == (m.left_net, m.right_net)


# --------------------------------------------------------------------------
# the move set
# --------------------------------------------------------------------------

def _device_state(nl3, lw, eop, eon, census=True):
    dp, dn = blocks_to_devices(eop, eon)
    crit = frozenset(pdev._signal_nets(nl3))
    return _DeviceState(dp, dn, lw, netlist=nl3 if census else None,
                        critical_nets=crit if census else None)


def test_every_move_type_is_drawn_and_legal():
    nl3, lw, eop, eon = _pipeline(COMPLEX0)
    state = _device_state(nl3, lw, eop, eon)
    rng = random.Random(1234)
    kinds = {"flip": 0, "adjacent": 0, "any_pair": 0, "row_move": 0,
             "both_rows": 0}
    for _ in range(400):
        mv = state.draw_move(rng)
        rows = {r for r, _o, _s, _m, _d in mv}
        if len(rows) == 2:
            kinds["both_rows"] += 1
        for r, origin, size, mirror, dest in mv:
            assert size == 1                      # device-granularity ops
            assert 0 <= origin < len(state.rows[r])
        ops = [(r, o, m, d) for r, o, _s, m, d in mv]
        if len(ops) == 1 and ops[0][2]:           # mirror=True -> flip
            kinds["flip"] += 1
        elif len(ops) == 1 and ops[0][3] == ops[0][1] + 1:
            kinds["adjacent"] += 1                # shift by one -> swap
        elif len(ops) == 1:
            kinds["row_move"] += 1
        else:
            kinds["any_pair"] += 1
        delta = state.apply(mv)
        assert isinstance(delta, int)
        state.apply(state.inverse(mv))            # exact undo
    assert all(kinds[k] > 0 for k in kinds)
    assert state.full_recompute() == state.cost()


def test_apply_inverse_restores_arrangement_and_cost():
    nl3, lw, eop, eon = _pipeline(COMPLEX0)
    for census in (True, False):
        state = _device_state(nl3, lw, eop, eon, census=census)
        before_cost = state.cost()
        before_sig = ordering_signature(*state.orderings())
        rng = random.Random(99)
        for _ in range(200):
            mv = state.draw_move(rng)
            state.apply(mv)
            state.apply(state.inverse(mv))
            assert state.cost() == before_cost
        assert ordering_signature(*state.orderings()) == before_sig


def test_incremental_equals_full_after_random_sequences():
    """The inherited discipline at device granularity: after every random
    move sequence the incremental cost equals the full recompute."""
    nl3, lw, eop, eon = _pipeline(COMPLEX0)
    state = _device_state(nl3, lw, eop, eon)
    rng = random.Random(7)
    cost = state.cost()
    for _seq in range(30):
        for _ in range(10):
            mv = state.draw_move(rng)
            delta = state.apply(mv)
            cost += delta
            if rng.randrange(2):                 # undo half of them
                state.apply(state.inverse(mv))
                cost = state.cost()
        assert state.full_recompute() == cost
        cost = state.cost()


# --------------------------------------------------------------------------
# the search: determinism, steering, budgets
# --------------------------------------------------------------------------

def test_device_seed_is_content_derived_and_distinct_stream():
    nl3, _lw, _eop, _eon = _pipeline(NAND2)
    a = device_seed(nl3)
    assert a == device_seed(nl3)                  # pure
    assert a != cell_seed(nl3)                   # its own RNG stream
    assert a != device_seed(nl3, salt=1)         # restart salt works
    assert DEVICE_ENGINE_VERSION == "bigcell-device/1"


def test_place_devices_is_deterministic():
    for text, budget in ((NAND2, None), (COMPLEX0, 3)):
        nl3, lw, eop, eon = _pipeline(text)
        op1, on1, bd1 = place_devices(nl3, lw, budget=budget)
        op2, on2, bd2 = place_devices(nl3, lw, budget=budget)
        assert ordering_signature(op1, on1) == ordering_signature(op2, on2)
        assert bd1["census"] == bd2["census"]
        assert bd1["total"] == bd2["total"]
        assert bd1["seed_kind"] == bd2["seed_kind"]
        assert bd1["candidates"] == bd2["candidates"]


_HASH_HELPER = r'''
import os
import re
import sys

sys.path.insert(0, os.getcwd())
from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from bigcell_engine.netlist_ext import fold_devices
from bigcell_engine.place_device import place_devices, devices_to_blocks
from bigcell_engine.place_sa import ordering_signature

text = open("../std_celllib/cellsAstranFriendly.sp",
            errors="ignore").read()
m = re.search(r"\.subckt\s+NAND2X1\b.*?\.ends", text, re.S | re.I)
nl = CellNetlist(parse_spice_subckt(m.group(0)))
nl3, lw = fold_devices(nl)
op, on, bd = place_devices(nl3, lw, budget=3)
bp, bn = devices_to_blocks(op, on)
print(ordering_signature(bp, bn))
'''


def test_place_devices_arrangement_signature_is_hash_seed_independent(
        flow_dir, tmp_path):
    """PYTHONHASHSEED 0 vs 1: the winning arrangement's signature is a
    pure function of the inputs (invariant 9, cross-process)."""
    helper = tmp_path / "device_hash_helper.py"
    helper.write_text(_HASH_HELPER)
    outs = set()
    for seed in ("0", "1"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run([sys.executable, str(helper)], cwd=flow_dir,
                              env=env, capture_output=True, text=True,
                              check=True)
        outs.add(proc.stdout.strip().splitlines()[-1])
    assert len(outs) == 1


def test_census_steering_never_worsens_the_cage(flow_dir):
    """The cage term dominates the legacy cost: the returned arrangement's
    caged-gate count is never above the best seed's (measured on the
    entangled class's smallest cell)."""
    nl3, lw = fold_devices(CellNetlist(parse_spice_subckt(
        _lib_subckt("XOR2X1", flow_dir))))
    seeds = device_seeds(nl3, lw)
    seed_cage = min(device_census(sp, sn, nl3, lw)["cage"]
                    for _k, sp, sn in seeds)
    op, on, bd = place_devices(nl3, lw, budget=6)
    assert bd["census"]["cage"] <= seed_cage
    assert bd["census"] == device_census(op, on, nl3, lw)


def test_zero_zero_short_circuits_the_seed_sweep():
    """The probe's acceptance: the first seed reaching census (0, 0)
    wins immediately -- no further seeds are tried (INV's euler seed is
    already (0, 0), so exactly one candidate runs)."""
    nl3, lw = fold_devices(CellNetlist(parse_spice_subckt(INV)))
    op, on, bd = place_devices(nl3, lw)
    assert bd["census"] == {"cage": 0, "crossing": 0}
    assert len(bd["candidates"]) == 1
    assert bd["candidates"][0]["seed_kind"] == bd["seed_kind"] == "euler"


def test_legacy_mode_keeps_the_pure_astran_cost():
    """census=False: no census runs (the reported counts are inert zeros),
    the search refines the pure legacy cost, and the winner ranks by
    total cost only."""
    nl3, lw, eop, eon = _pipeline(COMPLEX0)
    op, on, bd = place_devices(nl3, lw, budget=3, census=False)
    assert bd["census"] == {"cage": 0, "crossing": 0}
    seed_total = _DeviceState(*blocks_to_devices(eop, eon), lw).total
    assert bd["total"] <= seed_total
    # the full census-steered chain never costs more than the legacy
    # one on the same seed pair (the cage term only adds)
    op2, on2, bd2 = place_devices(nl3, lw, budget=3, census=True)
    assert bd2["total"] >= bd["total"]


def test_budget_is_iteration_count_and_scales(flow_dir):
    """budget=1 completes on the corpus's biggest test cell: the budget is
    an iteration count (never wall-clock), and larger budgets stay
    bounded and deterministic."""
    text = os.path.join(flow_dir, "outputs", "adder", "COMPLEX10.sp")
    if not os.path.exists(text):
        pytest.skip("outputs/adder/COMPLEX10.sp not in this checkout")
    nl3, lw = fold_devices(CellNetlist(parse_spice_subckt(
        open(text, errors="ignore").read())))
    op1, on1, bd1 = place_devices(nl3, lw, budget=1, init_moves=8)
    op2, on2, bd2 = place_devices(nl3, lw, budget=1, init_moves=8)
    assert ordering_signature(op1, on1) == ordering_signature(op2, on2)
    assert bd1["width_cols"] > 0
    # every device placed exactly once
    names = [b.members[0].device.name for row in (op1, on1) for b in row]
    assert sorted(names) == sorted(d.name for d in nl3.devices)


def test_device_sa_reports_public_census_and_width():
    nl3, lw, eop, eon = _pipeline(NAND2)
    dp, dn = blocks_to_devices(eop, eon)
    op, on, bd = device_sa(dp, dn, nl3, lw, iterations=3)
    assert bd["census"] == {"cage": gate_cage_penalty(op, on, nl3, lw)[0],
                            "crossing": crossing_cage_penalty(
                                op, on, nl3, lw)[0]}
    pl, width = layout_cell(*devices_to_blocks(op, on), lw)
    assert bd["width_cols"] == width
    for term in ("width", "gaps", "gate_mismatch", "span",
                 "max_congestion", "local_congestion", "total"):
        assert term in bd
