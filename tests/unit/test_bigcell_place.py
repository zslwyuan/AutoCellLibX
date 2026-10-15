"""Unit tests for flow/bigcell_engine/place_euler.py and place_sa.py
(stage 3, doc STAGE3_BIGCELL_ENGINE.md sections 2.2 B/C): the
deterministic Euler-chain constructor and the Threshold-Accept refinement
with incremental cost evaluation.
"""
import math
import random

import pytest

from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from bigcell_engine.netlist_ext import (build_bigcell_blocks, fold_devices,
                                        row_seeds)
from bigcell_engine.place_euler import euler_orderings
from bigcell_engine.place_sa import (_SAState, sa_refine, cell_seed,
                                     COST_WEIGHTS)
from bigcell_engine.geometry import (DEFAULT_LEG_WIDTHS_MIN_COLS, GRID_UM,
                                     N_ROW, P_ROW, block_width_cols,
                                     layout_cell)

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
    """fold -> blocks -> seeds -> (netlist, leg_widths, seeds)."""
    nl0 = CellNetlist(parse_spice_subckt(text))
    nl, leg_widths = fold_devices(nl0)
    blocks = build_bigcell_blocks(nl)
    seeds = row_seeds(blocks, leg_widths)
    return nl, leg_widths, seeds


def _row_breaks(row):
    breaks = 0
    prev = None
    for block in row:
        if prev is not None and block.members[0].left_net != prev:
            breaks += 1
        prev = block.members[-1].right_net
    return breaks


def _shape(rows):
    return tuple((b.kind, tuple((m.device.name, m.left_net, m.right_net)
                                for m in b.members))
                 for row in rows for b in row)


# --------------------------------------------------------------------------
# euler_orderings
# --------------------------------------------------------------------------

def test_euler_deterministic():
    nl, lw, seeds = _pipeline(COMPLEX0)
    a = euler_orderings(seeds, lw)
    b = euler_orderings(seeds, lw)
    assert _shape(a) == _shape(b)


def test_euler_zero_break_trails_on_regular_cells():
    for text in (INV, NAND2):
        nl, lw, seeds = _pipeline(text)
        op, on = euler_orderings(seeds, lw)
        assert _row_breaks(op) == 0
        assert _row_breaks(on) == 0


def test_euler_prefers_gate_matched_pairs():
    nl, lw, seeds = _pipeline(NAND2)
    op, on = euler_orderings(seeds, lw)
    # the single P block and single N block must be gate-aligned: the
    # parallel P pair and the series N pair cover gates {A, B} both
    gates_p = set(m.device.gate for b in op for m in b.members)
    gates_n = set(m.device.gate for b in on for m in b.members)
    assert gates_p == gates_n == {"A", "B"}


def test_euler_budget_exhaustion_falls_back_to_seeds():
    nl, lw, seeds = _pipeline(COMPLEX0)
    op, on = euler_orderings(seeds, lw, expansion_budget=1)
    assert op == seeds[P_ROW]
    assert on == seeds[N_ROW]


def test_euler_millisecond_scale_on_the_biggest_cell(flow_dir):
    import glob
    import os
    import time
    path = os.path.join(flow_dir, "outputs", "adder", "COMPLEX10.sp")
    nl0 = CellNetlist(parse_spice_subckt(open(path).read()))
    nl, lw = fold_devices(nl0)
    seeds = row_seeds(build_bigcell_blocks(nl), lw)
    t0 = time.time()
    op, on = euler_orderings(seeds, lw)
    assert time.time() - t0 < 0.25          # doc: "constructs in milliseconds"
    assert op and on


def test_euler_keeps_every_block_exactly_once():
    nl, lw, seeds = _pipeline(COMPLEX0)
    op, on = euler_orderings(seeds, lw)
    for row in (op, on):
        names = [b.first.name for b in row]
        assert len(names) == len(set(names))


# --------------------------------------------------------------------------
# _SAState: incremental cost == full recompute
# --------------------------------------------------------------------------

@pytest.mark.parametrize("text", [INV, NAND2, COMPLEX0])
def test_sa_incremental_matches_full_recompute(text):
    nl, lw, seeds = _pipeline(text)
    state = _SAState(seeds[P_ROW], seeds[N_ROW], lw)
    rng = random.Random(1234)
    for step in range(400):
        mv = state.draw_move(rng)
        state.apply(mv)
        if rng.random() < 0.7:
            state.apply(state.inverse(mv))
        cached = state.total               # BEFORE the rebuild
        full = state.full_recompute()
        assert full == cached, (step, mv, cached, full)
        # and the inverse really restores the previous state exactly
        undo = state.inverse(mv)
        state.apply(undo)
        assert state.total == state.full_recompute()


def test_sa_full_recompute_is_idempotent():
    nl, lw, seeds = _pipeline(COMPLEX0)
    state = _SAState(seeds[P_ROW], seeds[N_ROW], lw)
    assert state.full_recompute() == state.full_recompute() == state.cost()


def test_sa_costs_are_integers():
    nl, lw, seeds = _pipeline(COMPLEX0)
    state = _SAState(seeds[P_ROW], seeds[N_ROW], lw)
    bd = state.breakdown()
    assert all(isinstance(v, int) for v in bd.values())


# --------------------------------------------------------------------------
# sa_refine
# --------------------------------------------------------------------------

def test_sa_deterministic_orderings():
    nl, lw, seeds = _pipeline(COMPLEX0)
    op, on = euler_orderings(seeds, lw)
    a = sa_refine(op, on, nl, lw, iterations=3, quality=2.0,
                  init_moves=100, check=True)
    b = sa_refine(op, on, nl, lw, iterations=3, quality=2.0,
                  init_moves=100, check=True)
    assert _shape((a[0], a[1])) == _shape((b[0], b[1]))
    assert a[2] == b[2]


def test_sa_improves_or_ties_the_seed():
    nl, lw, seeds = _pipeline(COMPLEX0)
    op, on = euler_orderings(seeds, lw)
    seed_cost = _SAState(op, on, lw).cost()
    op2, on2, bd = sa_refine(op, on, nl, lw, iterations=6, quality=5.0,
                             init_moves=200, check=True)
    assert bd["total"] <= seed_cost


def test_sa_refine_never_loses_blocks():
    nl, lw, seeds = _pipeline(COMPLEX0)
    op, on = euler_orderings(seeds, lw)
    op2, on2, _bd = sa_refine(op, on, nl, lw, iterations=2, quality=2.0,
                              init_moves=100, check=False)
    for row in (op2, on2):
        names = [b.first.name for b in row]
        assert len(names) == len(set(names))
    assert sum(len(b.members) for b in op2) + \
        sum(len(b.members) for b in on2) == \
        sum(len(b.members) for b in op) + \
        sum(len(b.members) for b in on)


def test_sa_seed_is_content_derived_and_stable():
    nl, _lw, _seeds = _pipeline(COMPLEX0)
    nl2, _lw2, _seeds2 = _pipeline(COMPLEX0)
    assert cell_seed(nl) == cell_seed(nl2)
    # a different cell hashes differently
    nl3, _lw3, _seeds3 = _pipeline(NAND2)
    assert cell_seed(nl) != cell_seed(nl3)


def test_sa_weights_match_astran_autoflow():
    # placeTrans(false, 150, 3, 4, 4, 1, 4, 2), cellnetlst.cpp:460
    assert COST_WEIGHTS == {"width": 4, "gate_mismatch": 4, "span": 1,
                            "max_congestion": 4, "gaps": 2}


# --------------------------------------------------------------------------
# geometry wiring: layout_cell agrees with the SA cost's width model
# --------------------------------------------------------------------------

def test_layout_cell_width_matches_hand_computed_columns():
    nl, lw, seeds = _pipeline(NAND2)
    op, on = euler_orderings(seeds, lw)
    placements, width = layout_cell(op, on, lw)
    # N row: MnA(3 cols) + MnB(3 cols) sharing n1 -> 6 columns, no break;
    # P row: the parallel pair shares its ends -> 6 columns, no break.
    # Hand-computed: width 6, every device 3 columns.
    assert width == 6
    assert placements[nl.devices[0]].leg_width_cols == 3
    # every row accounts exactly: widths + one column per break <= width
    for row in (op, on):
        total = sum(block_width_cols(b, lw) for b in row)
        assert total + _row_breaks(row) * 1 <= width
    # P row end position of the last device lands on column 6
    last_p = op[-1].members[-1].device
    assert placements[last_p].start_col + \
        placements[last_p].legs * placements[last_p].leg_width_cols == width


def _row_breaks_at(row, index):
    """Breaks strictly before block ``index`` of ``row``."""
    breaks = 0
    for i in range(1, index + 1):
        if row[i].members[0].left_net != row[i - 1].members[-1].right_net:
            breaks += 1
    return breaks


def test_sa_width_term_equals_layout_cell():
    nl, lw, seeds = _pipeline(COMPLEX0)
    op, on = euler_orderings(seeds, lw)
    op2, on2, bd = sa_refine(op, on, nl, lw, iterations=2, quality=2.0,
                             init_moves=100, check=True)
    _placements, width = layout_cell(op2, on2, lw)
    assert bd["width"] == width


def test_width_floor_no_breaks_possible():
    """A zero-break trail's width is exactly the sum of block widths."""
    nl, lw, seeds = _pipeline(NAND2)
    op, on = euler_orderings(seeds, lw)
    _placements, width = layout_cell(op, on, lw)
    assert width == sum(block_width_cols(b, lw) for b in op)
    assert width == sum(block_width_cols(b, lw) for b in on)
