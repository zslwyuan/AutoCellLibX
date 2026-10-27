"""Unit tests for the geometry VARIABLES (AUDIT 5.61's round).

The two freedoms ASTRAN's LP-compacted layouts use that the fixed slot
model lacked, now landed additively:

- **region widths**: a member's terminal region spans k columns
  (``leg_widths`` entry ``(1, k)``) -- terminals at the run's edges,
  the gate at its centre column (``start + k//2``, the formula every
  consumer shares);
- **row x-offsets**: ``place_row(..., x_offset=...)`` /
  ``layout_cell(..., x_offsets=...)`` shift a whole row right.

Everything is default-off and byte-identical to the historical chain
(x_offset 0, one-column runs).  Pinned here: the offset arithmetic,
the k>1 slot derivations, the ``is_slot_placement`` blocks-hint (the
one case the placement IR alone cannot decide), the GDS rendering
with offsets (including the gate-contact-at-centre-column rule the
legacy walk got wrong for k>1), the seed geometry overlay, and the
encoding's measured lesson: a widened member that splits a merged
gate pair is exact-INFEASIBLE while the aligned variants close.
"""
import os

import pytest

from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from smt_engine import die_view

from bigcell_engine.geometry import (BREAK_GAP_COLS, GRID_UM,
                                     block_width_cols, layout_cell,
                                     place_row, row_edges,
                                     row_gate_columns,
                                     slot_diffusion_access)
from bigcell_engine.gds_cells import cell_gds
from bigcell_engine.netlist_ext import build_bigcell_blocks, fold_devices
from bigcell_engine.place_euler import euler_orderings
from bigcell_engine.netlist_ext import row_seeds

NAND2 = """\
.subckt NAND2 VCC Y A B GND
MpA Y A VCC VCC PMOS W=0.5u L=0.05u
MpB VCC B Y VCC PMOS W=0.5u L=0.05u
MnA Y A n1 GND NMOS W=0.5u L=0.05u
MnB n1 B GND GND NMOS W=0.5u L=0.05u
.end
"""


def _nl(text=NAND2):
    return CellNetlist(parse_spice_subckt(text))


def _orderings(nl):
    nl3, lws = fold_devices(nl)
    seeds = row_seeds(build_bigcell_blocks(nl3), lws)
    op, on = euler_orderings(seeds, lws)
    return nl3, lws, op, on


# --------------------------------------------------------------------------
# the x-offset variable
# --------------------------------------------------------------------------

def test_place_row_x_offset_shifts_the_whole_row():
    nl = _nl()
    nl3, lws, op, on = _orderings(nl)
    base, base_end = place_row(0, op, lws)
    off, off_end = place_row(0, op, lws, x_offset=3)
    for dev in base:
        assert off[dev].start_col == base[dev].start_col + 3
        assert off[dev].end_col == base[dev].end_col + 3
        assert off[dev].legs == base[dev].legs
        assert off[dev].leg_width_cols == base[dev].leg_width_cols
    assert off_end == base_end + 3


def test_layout_cell_offsets_and_width():
    nl = _nl()
    nl3, lws, op, on = _orderings(nl)
    pl0, w0 = layout_cell(op, on, lws)
    pl1, w1 = layout_cell(op, on, lws, x_offsets=(0, 2))
    # the P row unchanged, the N row shifted 2
    for dev in nl3.devices:
        if dev.is_p:
            assert pl1[dev].start_col == pl0[dev].start_col
        else:
            assert pl1[dev].start_col == pl0[dev].start_col + 2
    assert w1 >= w0
    # the width is the max row END (offset included)
    row_ends = {}
    for dev in nl3.devices:
        p = pl1[dev]
        row_ends[p.row] = max(row_ends.get(p.row, 0), p.end_col)
    assert w1 == max(row_ends.values())


def test_offsets_default_is_byte_identical():
    nl = _nl()
    nl3, lws, op, on = _orderings(nl)
    pl0, w0 = layout_cell(op, on, lws)
    pl1, w1 = layout_cell(op, on, lws, x_offsets=None)
    pl2, w2 = layout_cell(op, on, lws, x_offsets=(0, 0))
    assert w0 == w1 == w2
    assert {d.name: (p.row, p.start_col) for d, p in pl0.items()} == \
        {d.name: (p.row, p.start_col) for d, p in pl1.items()} == \
        {d.name: (p.row, p.start_col) for d, p in pl2.items()}


def test_row_edges_and_gate_columns_shift_with_the_offset():
    nl = _nl()
    nl3, lws, op, on = _orderings(nl)
    edges0 = row_edges(op, lws)
    edges3 = row_edges(op, lws, x_offset=3)
    assert [e[0] for e in edges3] == [e[0] + 3 for e in edges0]
    assert [e[1] for e in edges3] == [e[1] for e in edges0]
    gates0 = row_gate_columns(op, lws)
    gates3 = row_gate_columns(op, lws, x_offset=3)
    assert [g[0] for g in gates3] == [g[0] + 3 for g in gates0]


# --------------------------------------------------------------------------
# the region-width variable (k>1 members)
# --------------------------------------------------------------------------

def test_k_member_edges_and_centre_gate():
    nl = _nl()
    nl3, lws, op, on = _orderings(nl)
    # widen the first P member to a 3-column region
    name = op[0].members[0].device.name
    wide = dict(lws)
    wide[name] = (1, 3)
    pl, w = layout_cell(op, on, wide)
    p = pl[[d for d in nl3.devices if d.name == name][0]]
    assert p.leg_width_cols == 3 and p.legs == 1
    assert p.end_col == p.start_col + 3
    # terminals at the run's edges
    edges = dict((e, n) for e, n, _w in row_edges(op, wide))
    assert edges[p.start_col] == op[0].members[0].left_net
    assert edges[p.end_col] == op[0].members[0].right_net
    # the gate at the run's centre column (start + k//2)
    gates = dict((c, n) for c, n, d in row_gate_columns(op, wide))
    assert gates[p.start_col + 1] == \
        op[0].members[0].device.gate


def test_slot_access_uses_placement_positions_with_offsets():
    nl = _nl()
    nl3, lws, op, on = _orderings(nl)
    name = op[0].members[0].device.name
    wide = dict(lws)
    wide[name] = (1, 2)
    pl, w = layout_cell(op, on, wide, x_offsets=(0, 2))
    sig, pow_ = slot_diffusion_access(nl3, pl, (op, on), wide)
    # every access column is a placed device edge
    for pts in list(sig.values()) + list(pow_.values()):
        for c, dev in pts:
            p = pl[dev]
            assert c in (p.start_col, p.end_col)
    # the N row's accesses shifted by the offset
    n_dev = [d for d in nl3.devices if not d.is_p][0]
    assert pl[n_dev].start_col >= 2


def test_is_slot_placement_blocks_hint():
    nl = _nl()
    nl3, lws, op, on = _orderings(nl)
    blocks = list(op) + list(on)
    wide = dict(lws)
    name = op[0].members[0].device.name
    wide[name] = (1, 2)
    pl, w = layout_cell(op, on, wide)
    # all-one placements: True regardless of the hint (historical)
    pl1, _w = layout_cell(op, on, lws)
    assert die_view.is_slot_placement(pl1)
    assert die_view.is_slot_placement(pl1, blocks)
    # a k>1 placement: only the slot chain's block view says True --
    # the exact engine's folded devices (same IR shape, blocks=None)
    # must keep the historical walk
    assert not die_view.is_slot_placement(pl)
    assert die_view.is_slot_placement(pl, blocks)
    # a view that does not cover the placement does not upgrade it
    half_blocks = list(op)
    assert not die_view.is_slot_placement(pl, half_blocks)


def test_die_slot_access_points_edges_for_k_members():
    nl = _nl()
    nl3, lws, op, on = _orderings(nl)
    name = op[0].members[0].device.name
    wide = dict(lws)
    wide[name] = (1, 2)
    pl, w = layout_cell(op, on, wide, x_offsets=(0, 3))
    blocks = list(op) + list(on)
    sig, pow_ = die_view.die_slot_access_points(nl3, pl, blocks=blocks)
    for net, pts in list(sig.items()) + list(pow_.items()):
        for c, dev in pts:
            p = pl[dev]
            assert c in (p.start_col, p.end_col)


# --------------------------------------------------------------------------
# GDS rendering with the variables
# --------------------------------------------------------------------------

def _polys(lib, layer):
    cell = lib.top_level()[0]
    out = []
    for p in cell.polygons:
        if p.layer == layer:
            r = p.bounding_box()
            out.append((round(r[0][0], 4), round(r[0][1], 4),
                        round(r[1][0], 4), round(r[1][1], 4)))
    return sorted(out)


def test_gds_offsets_shift_the_rows():
    nl = _nl()
    nl3, lws, op, on = _orderings(nl)
    pl0, w0 = layout_cell(op, on, lws)
    pl1, w1 = layout_cell(op, on, lws, x_offsets=(0, 2))
    lib0, _ = cell_gds(nl3, pl0, w0, op, on, lws)
    lib1, _ = cell_gds(nl3, pl1, w1, op, on, lws, x_offsets=(0, 2))
    act0 = [r for r in _polys(lib0, 1)]
    act1 = [r for r in _polys(lib1, 1)]
    # the N row's strips shifted by 2 columns; the P row's did not
    mid = 1.235
    p0 = [r for r in act0 if (r[1] + r[3]) / 2 > mid]
    p1 = [r for r in act1 if (r[1] + r[3]) / 2 > mid]
    n0 = [r for r in act0 if (r[1] + r[3]) / 2 <= mid]
    n1 = [r for r in act1 if (r[1] + r[3]) / 2 <= mid]
    assert [r[0] for r in p1] == [r[0] for r in p0]
    assert [round(r[0] - 2 * GRID_UM, 6) for r in n1] == \
        [round(r[0], 6) for r in n0]
    # the outline widened by the offset
    bb1 = lib1.top_level()[0].bounding_box()
    bb0 = lib0.top_level()[0].bounding_box()
    assert round(bb1[1][0] - bb1[0][0], 4) == pytest.approx(
        bb0[1][0] - bb0[0][0] + 2 * GRID_UM, abs=1e-6)


def test_gds_k_member_gate_contact_at_centre_column(tmp_path):
    # the gate-contact drawing rule for k>1: the contact square sits at
    # the gate column's centre x (start + k//2), NOT the run's left
    # edge -- the legacy walk's ``col + j*legw`` agreed with the shared
    # centre formula only while every leg was one column wide
    nl = _nl()
    nl3, lws, op, on = _orderings(nl)
    name = op[0].members[0].device.name
    wide = dict(lws)
    wide[name] = (1, 2)
    pl, w = layout_cell(op, on, wide)
    lib, _ = cell_gds(nl3, pl, w, op, on, wide)
    p = pl[[d for d in nl3.devices if d.name == name][0]]
    gate_col = p.start_col + p.leg_width_cols // 2
    mid = 1.235
    # the P row's own poly stripes (disjoint y from the N row's)
    p_stripes = [r for r in _polys(lib, 9) if (r[1] + r[3]) / 2 > mid]
    p_xs = sorted(set(round((r[0] + r[2]) / 2, 4) for r in p_stripes))
    assert round(0.2375 + (gate_col + 0.5) * GRID_UM, 4) in p_xs
    assert round(0.2375 + (p.start_col + 0.5) * GRID_UM, 4) not in p_xs


# --------------------------------------------------------------------------
# the seed geometry overlay
# --------------------------------------------------------------------------

def test_seed_geometry_overlays_the_leg_map():
    from bigcell_engine.gds_seeds import seed_geometry
    entry = {"p": [("M0", "VCC", "Y"), ("M1", "Y", "VCC")],
             "n": [("M2", "GND", "Y"), ("M3", "GND", "Y")],
             "p_widths": (1, 3), "n_widths": (2, 1),
             "x_offsets": (0, 4)}
    base = {"M0": (1, 1), "M1": (1, 1), "M2": (1, 1), "M3": (1, 1)}
    lws, offs = seed_geometry(entry, base)
    assert lws == {"M0": (1, 1), "M1": (1, 3), "M2": (1, 2),
                   "M3": (1, 1)}
    assert offs == (0, 4)
    # a legacy entry without geometry keeps the base map and zero
    lws2, offs2 = seed_geometry({"p": entry["p"], "n": entry["n"]},
                                base)
    assert lws2 == base and offs2 == (0, 0)


# --------------------------------------------------------------------------
# the encoding's measured lesson: a split gate pair is caged
# --------------------------------------------------------------------------

def test_widened_member_splitting_a_gate_pair_is_infeasible():
    """AUDIT 5.61's measured encoding lesson, pinned.

    Widening ONE member of a P/N gate pair moves that row's gate
    column while its partner stays -- the pair splits, each gate needs
    its own crossing, and the thin-strip gate's crossing is statically
    caged by the power column's forced metal.  The exact model proves
    the split projection INFEASIBLE while the ALIGNED variants (widen
    BOTH members, or neither) stay solvable -- the gate-anchored
    projection exists to keep the pairs merged."""
    from smt_engine.route_model import (solve_routing,
                                        verify_style_access_points)
    nl = _nl()
    nl3, lws, op, on = _orderings(nl)
    p_name = op[0].members[0].device.name
    n_name = on[0].members[0].device.name
    assert op[0].members[0].device.gate == on[0].members[0].device.gate
    blocks = list(op) + list(on)

    def exact(extra):
        l2 = dict(lws)
        l2.update(extra)
        pl, w = layout_cell(op, on, l2)
        acc = verify_style_access_points(nl3, pl, blocks)
        return solve_routing(nl3, pl, w + 1, metal2=True, m2_spans=True,
                             jump_m2=True, accesses=acc,
                             time_limit_s=60.0)

    assert exact({}).status_name in ("OPTIMAL", "FEASIBLE")
    assert exact({p_name: (1, 3), n_name: (1, 3)}).status_name in \
        ("OPTIMAL", "FEASIBLE")
    assert exact({p_name: (1, 2)}).status_name == "INFEASIBLE"
    assert exact({n_name: (1, 2)}).status_name == "INFEASIBLE"
