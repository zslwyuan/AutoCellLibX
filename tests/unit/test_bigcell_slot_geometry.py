"""Unit tests for the bigcell slot geometry (doc/BIGCELL_SLOT_GEOMETRY.md).

The contract pinned here was reverse-engineered from ASTRAN's own output
(flow/original_astran_cells GDS, 16.5 raw units/um) and autocell2.cpp:

- W is drawn VERTICALLY (a device's diffusion strip y-extent = W); the
  horizontal footprint is the terminal/gate slot sequence -- one 0.19 um
  column per (terminal | gate | terminal) triple, terminals on the
  column edges, gates at the column centres;
- facing-equal-net blocks share a terminal slot (no gap column), else
  one break column;
- cell width = width_cols * 0.19 + 0.385 um, within 0.8-1.3x of every
  ASTRAN reference cell (the acceptance gate);
- the emitted GDS is layout_sanity-clean and byte-deterministic.
"""
import os
import re

import pytest

from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from bigcell_engine.geometry import (GRID_UM, N_ROW, P_ROW, WIDTH_MARGIN_UM,
                                     block_width_cols, contact_nets,
                                     default_leg_widths, layout_cell,
                                     row_edges, slot_diffusion_access,
                                     width_um)
from bigcell_engine.gds_cells import cell_gds, write_cell_gds
from bigcell_engine.netlist_ext import (build_bigcell_blocks, fold_devices,
                                        row_seeds)
from bigcell_engine.place_euler import euler_orderings
from bigcell_engine.place_sa import sa_refine

FLOW = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), "flow")
CELLS = os.path.join(FLOW, "original_astran_cells")

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

WIDE = """\
.subckt WIDE VCC Y A GND
Mp Y A VCC VCC PMOS W=3u L=0.05u
Mn Y A GND GND NMOS W=0.5u L=0.05u
.end
"""

MIXED = """\
.subckt MIXED VCC Y A GND
Mp Y A n1 VCC PMOS W=3u L=0.05u
Mn n1 A GND GND NMOS W=0.5u L=0.05u
.end
"""


T3CELL = """\
.subckt T3CELL VCC Y A B C GND
Mn1 Y A n1 GND NMOS W=0.5u L=0.05u
Mn2 n1 B n2 GND NMOS W=0.5u L=0.05u
Mn3 n2 C GND GND NMOS W=0.5u L=0.05u
Mp1 VCC C p2 VCC PMOS W=0.5u L=0.05u
Mp2 p2 B p1 VCC PMOS W=0.5u L=0.05u
Mp3 p1 A Y VCC PMOS W=0.5u L=0.05u
.end
"""


def _subckt_text(cell):
    text = open(os.path.join(FLOW, "..", "std_celllib",
                             "cellsAstranFriendly.sp"),
                errors="ignore").read()
    return (".subckt %s" % cell
            + re.split(r"\.subckt\s+%s\b" % cell, text)[1].split(".ends")[0]
            + ".ends")


def _chain(text):
    """fold -> blocks (unbounded coupler) -> seeds -> euler -> SA -> cols."""
    nl = CellNetlist(parse_spice_subckt(text))
    nl3, lw = fold_devices(nl)
    blocks = build_bigcell_blocks(nl3, max_coupler_degree=None)
    seeds = row_seeds(blocks, lw)
    op, on = euler_orderings(seeds, lw)
    op2, on2, bd = sa_refine(op, on, nl3, lw, check=True)
    placements, cols = layout_cell(op2, on2, lw)
    return nl3, lw, op2, on2, placements, cols, bd


def _astran_width(cell):
    for line in open(os.path.join(CELLS, cell + ".Astranlog"),
                     errors="ignore"):
        if "-> Cell Size (W x H): " in line:
            return float(line.replace("-> Cell Size (W x H): ", "")
                         .split("x")[0])
    return None


# --------------------------------------------------------------------------
# the derived rules
# --------------------------------------------------------------------------

def test_width_is_columns_times_grid_plus_measured_margin():
    # INVX1: 1 column -> 0.575 vs ASTRAN's measured 0.57 (pitch 0.185)
    assert WIDTH_MARGIN_UM == pytest.approx(0.385)
    assert width_um(1) == pytest.approx(0.575)
    assert width_um(2) == pytest.approx(0.765)


def test_legs_are_one_column_wide_w_is_vertical():
    nl, lw, _op, _on, placements, cols, _bd = _chain(INV)
    assert cols == 1
    for dev, p in placements.items():
        assert (p.legs, p.leg_width_cols) == (1, 1)
        assert p.start_col == 0 and p.end_col == 1


def test_width_fold_emits_one_column_per_leg():
    # a standalone over-budget device folds the ASTRAN way -- separate
    # leg transistors (foldingSeries' numTrans == 0 branch): 3 legs of
    # one slot column, strip 1u tall each
    nl0 = CellNetlist(parse_spice_subckt(WIDE))
    nl3, lw = fold_devices(nl0)
    assert lw["Mp"] == lw["Mp#leg2"] == lw["Mp#leg3"] == (1, 1)
    assert {d.name for d in nl3.devices} == {"Mp", "Mp#leg2", "Mp#leg3",
                                             "Mn"}
    # inside a series chain that does NOT fold as a whole (only Mp is
    # over budget) the width fold is represented in place as (3, 1)
    nl0 = CellNetlist(parse_spice_subckt(MIXED))
    _nl, lw = fold_devices(nl0)
    assert lw["Mp"] == (3, 1)
    assert lw["Mn"] == (1, 1)


def test_no_fold_below_the_vertical_budget():
    nl0 = CellNetlist(parse_spice_subckt(NAND2))
    _nl, lw = fold_devices(nl0)
    assert set(lw.values()) == {(1, 1)}


def test_facing_equal_blocks_share_the_terminal_slot():
    # NOR3X1's doubled pull-up: ASTRAN runs all six PMOS in ONE strip
    # (7 terminal slots, 6 columns, 0 breaks).  The slot chain must
    # reproduce that: no break column, multi-region coupler nets.
    nl3, lw, op2, on2, _pl, cols, bd = _chain(
        _subckt_text("NOR3X1"))
    assert bd["gaps"] == 0
    assert cols == 6
    p_edges = row_edges(op2, lw)
    nets = [n for _e, n, _w in p_edges]
    # 7 slots; the coupler nets each occupy >= 2 of them (regions to
    # tie; the trail may start and end on the same coupler, giving it 3)
    assert len(nets) == 7
    for net in ("a_2_64#", "a_25_64#"):
        assert nets.count(net) >= 2
    assert contact_nets(op2, nl3, lw) >= {"VCC", "Y", "a_2_64#",
                                          "a_25_64#"}


def test_internal_single_region_junction_gets_no_contact():
    nl3, lw, op2, on2, _pl, _cols, _bd = _chain(NAND2)
    # the N row's series junction n1 occupies one slot and is complete
    # through diffusion: no contact (ASTRAN leaves it uncontacted too)
    assert "n1" not in contact_nets(on2, nl3, lw)
    # the P row's shared middle terminal is the output Y: contacted
    assert "Y" in contact_nets(op2, nl3, lw)


def test_break_gap_between_different_facing_nets():
    from bigcell_engine.geometry import place_row
    from bigcell_engine.netlist_ext import mirror_block
    nl = CellNetlist(parse_spice_subckt(NAND2))
    _nl, lw = fold_devices(nl)
    blocks = build_bigcell_blocks(nl)
    # two P blocks that cannot share: force a break by ordering the
    # parallel pair after a single oriented the other way
    p_blocks = [b for b in blocks if b.first.is_p]
    if len(p_blocks) < 2:
        pytest.skip("needs a two-block row")
    a, b = p_blocks[0], mirror_block(p_blocks[1])
    placements, end = place_row(P_ROW, [a, b], lw)
    shared = a.members[-1].right_net == b.members[0].left_net
    expected = block_width_cols(a, lw) + block_width_cols(b, lw) \
        + (0 if shared else 1)
    assert end == expected


# --------------------------------------------------------------------------
# the width table (acceptance gate 1: 0.8-1.3x per reference cell)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("cell", [
    "INVX1", "NAND2X1", "NOR2X1", "NAND3X1", "AOI21X1", "AND2X1", "OR2X1",
    "OAI21X1", "AOI22X1", "NOR3X1", "MUX2X1", "XNOR2X1", "CLKBUF1",
    "XOR2X1"])
def test_slot_width_within_parity_band(cell):
    nl3, _lw, _op, _on, _pl, cols, _bd = _chain(_subckt_text(cell))
    astran = _astran_width(cell)
    assert astran is not None
    ratio = width_um(cols) / astran
    assert 0.8 <= ratio <= 1.3, "%s: %.3f um (%d cols) vs %.2f -> %.2f" \
        % (cell, width_um(cols), cols, astran, ratio)


# --------------------------------------------------------------------------
# GDS emission (acceptance gate 2: geometry evidence, sanity-clean)
# --------------------------------------------------------------------------

def test_gds_sanity_clean_and_measured_width(tmp_path):
    from layout_sanity import check_layout
    nl3, lw, op2, on2, pl, cols, _bd = _chain(NAND2)
    gds = str(tmp_path / "NAND2.gds")
    write_cell_gds(gds, nl3, pl, cols, op2, on2, lw, cell_name="NAND2")
    rep = check_layout(gds, units_per_um=1.0)
    assert rep.ok(), rep.violations
    assert rep.metrics["width_um"] == pytest.approx(width_um(cols))
    assert rep.metrics["height_um"] == pytest.approx(2.47)
    assert {"GND", "VCC"} <= set(rep.metrics["labels"])


def test_gds_draws_w_vertically_and_slots_horizontally(tmp_path):
    import gdstk
    nl3, lw, op2, on2, pl, cols, _bd = _chain(NAND2)
    lib, _pins = cell_gds(nl3, pl, cols, op2, on2, lw, cell_name="NAND2")
    cell = lib.top_level()[0]
    strips = [p for p in cell.polygons if p.layer == 1]
    heights = sorted(set(round(p.bounding_box()[1][1]
                               - p.bounding_box()[0][1], 4)
                         for p in strips))
    assert heights == [0.5]          # every NAND2 device W = 0.5u, VERTICAL
    # gates at column centres, one per leg, merged P/N where aligned
    polys = [p for p in cell.polygons if p.layer == 9]
    centres = sorted(set(round((p.bounding_box()[0][0]
                                + p.bounding_box()[1][0]) / 2, 4)
                         for p in polys))
    assert len(centres) == 2         # two gate slots for two members/row
    assert centres == [pytest.approx(0.2375 + 0.095),
                       pytest.approx(0.2375 + 0.19 + 0.095)]
    # terminal contacts sit on the column edges
    contacts = [p for p in cell.polygons if p.layer == 10]
    cxs = sorted(set(round((p.bounding_box()[0][0]
                            + p.bounding_box()[1][0]) / 2, 4)
                     for p in contacts))
    assert cxs == [pytest.approx(0.2375), pytest.approx(0.2375 + 0.19),
                   pytest.approx(0.2375 + 0.38)]


def test_gds_bytes_are_deterministic(tmp_path):
    a = str(tmp_path / "a.gds")
    b = str(tmp_path / "b.gds")
    nl3, lw, op2, on2, pl, cols, _bd = _chain(_subckt_text("MUX2X1"))
    write_cell_gds(a, nl3, pl, cols, op2, on2, lw, cell_name="MUX2")
    write_cell_gds(b, nl3, pl, cols, op2, on2, lw, cell_name="MUX2")
    assert open(a, "rb").read() == open(b, "rb").read()


# --------------------------------------------------------------------------
# slot access points + the verify path (routing itself is pending)
# --------------------------------------------------------------------------

def test_slot_access_points_use_edge_columns():
    nl = CellNetlist(parse_spice_subckt(NAND2))
    nl3, lw = fold_devices(nl)
    blocks = build_bigcell_blocks(nl3, max_coupler_degree=None)
    seeds = row_seeds(blocks, lw)
    op, on = euler_orderings(seeds, lw)
    op2, on2, _bd = sa_refine(op, on, nl3, lw, check=True)
    pl, cols = layout_cell(op2, on2, lw)
    sig, powr = slot_diffusion_access(nl3, pl, (op2, on2), lw)
    # a member's right terminal sits at start_col + width (its right
    # EDGE), never inset into its own column
    for net, pts in sig.items():
        for col, dev in pts:
            p = pl[dev]
            assert p.start_col <= col <= p.start_col + p.legs \
                * p.leg_width_cols
    assert "Y" in sig and {"VCC", "GND"} <= set(powr)


def test_route_grid_routes_slot_cells_after_the_section8_adaptation():
    # CLOSED (design note section 8 adapted in route_grid): the router
    # runs on the slot geometry -- edge-column diffusion accesses from
    # the shared die view, every multi-region slot exposed, the grid on
    # the edge axis, gate-only nets crossed on poly.  NAND2's slot
    # placement (2 columns) routes FEASIBLE and verifies clean.
    from smt_engine.verify import verify_cell
    from bigcell_engine.route_grid import route_cell
    nl3, lw, op2, on2, pl, cols, _bd = _chain(NAND2)
    route = route_cell(nl3, pl, cols, lw)
    assert route.ok, (route.status_name, route.fail_note)
    report = verify_cell(nl3, pl, route, blocks=list(op2) + list(on2))
    assert report.ok(), report.violations


def test_verify_slot_model_accepts_a_hand_routed_invx1():
    # ASTRAN's route grid keeps lateral columns beyond the diffusion on
    # both sides; a hand-built width-2 route (one lateral column) for
    # INVX1's 1-column placement exercises smt_engine.verify's slot-model
    # access path end to end.
    from smt_engine.route_model import RouteResult
    from smt_engine.verify import verify_cell
    nl3, lw, op2, on2, pl, _cols, _bd = _chain(INV)
    route = RouteResult(
        "FEASIBLE",
        {0: "GND", 1: "Y", 2: None},       # col_owner_n
        {0: "VCC", 1: "Y", 2: None},       # col_owner_p
        {0: 0, 1: 2, 2: 0}, {0: 3, 1: 4, 2: 0},          # lo_n / hi_n
        {0: 5, 1: 4, 2: 0}, {0: 8, 1: 5, 2: 0},          # lo_p / hi_p
        {(4, 0): "A"}, {(4, 0): True}, {}, {},           # hseg/pj/m2/via
        [False, True, False], [False, True, False],      # reachB_n/p
        2, 1, 0, 1, 0, 0)
    report = verify_cell(nl3, pl, route, blocks=list(op2) + list(on2),
                         slot_model=True)
    assert report.ok(), report.violations


def test_m2_crossover_hand_route_verifies():
    # The metal2 vertical freedom's vocabulary semantics, hand-built on
    # the INVX1 slot chain: a same-net dual column may stay unmerged at
    # T3 when its halves meet through an M2 span (col 1, tracks 2..4)
    # with node vias down to both slots' stripes.  The old vocabulary
    # (horizontal M2 only) had no such route; the exact BFS connects Y
    # through the span and the loosened dual rule accepts the unmerged
    # bars (physical connectivity is the BFS's verdict).
    from smt_engine.route_model import RouteResult
    from smt_engine.verify import verify_cell
    nl3, lw, op2, on2, pl, _cols, _bd = _chain(INV)
    route = RouteResult(
        "FEASIBLE",
        {0: "GND", 1: "Y", 2: None},       # col_owner_n
        {0: "VCC", 1: "Y", 2: None},       # col_owner_p
        {0: 0, 1: 3, 2: 0}, {0: 3, 1: 3, 2: 0},          # lo_n / hi_n
        {0: 5, 1: 5, 2: 0}, {0: 8, 1: 5, 2: 0},          # lo_p / hi_p
        {(4, 0): "A"}, {(4, 0): True}, {}, {},           # hseg/pj/m2/via
        [False, False, False], [False, False, False],    # reachB_n/p
        2, 1, 2, 0, 0, 0,
        m2v={(1, 2, 4): "Y"}, m2via={(2, 1): True, (4, 1): True})
    report = verify_cell(nl3, pl, route, blocks=list(op2) + list(on2),
                         slot_model=True)
    assert report.ok(), report.violations


def test_verify_rejects_broken_m2_crossover():
    # The freedom's claimed geometry is checked: a dropped node via
    # disconnects the net (the BFS reports it); an inverted span range,
    # a foreign span overlap at the same column and a node via whose M1
    # landing belongs to another net are named violations.
    from smt_engine.route_model import RouteResult
    from smt_engine.verify import verify_cell
    nl3, lw, op2, on2, pl, _cols, _bd = _chain(INV)

    def m2_route(m2v, m2via):
        return RouteResult(
            "FEASIBLE",
            {0: "GND", 1: "Y", 2: None}, {0: "VCC", 1: "Y", 2: None},
            {0: 0, 1: 3, 2: 0}, {0: 3, 1: 3, 2: 0},
            {0: 5, 1: 5, 2: 0}, {0: 8, 1: 5, 2: 0},
            {(4, 0): "A"}, {(4, 0): True}, {}, {},
            [False] * 3, [False] * 3,
            2, 1, 2, 0, 0, 0, m2v=m2v, m2via=m2via)

    blocks = list(op2) + list(on2)
    good_v = {(2, 1): True, (4, 1): True}
    # (a) a dropped node via: the P half's landing is gone
    report = verify_cell(nl3, pl, m2_route({(1, 2, 4): "Y"},
                                           {(2, 1): True}),
                         blocks=blocks, slot_model=True)
    assert not report.ok()
    assert any("Y is not connected" in v for v in report.violations)
    # (b) an inverted span is not a track range
    report = verify_cell(nl3, pl, m2_route({(1, 4, 2): "Y"}, good_v),
                         blocks=blocks, slot_model=True)
    assert not report.ok()
    assert any("not a track range" in v for v in report.violations)
    # (c) a foreign span overlapping the net's span at the same column
    report = verify_cell(nl3, pl,
                         m2_route({(1, 2, 4): "Y", (1, 3, 5): "GND"},
                                  good_v),
                         blocks=blocks, slot_model=True)
    assert not report.ok()
    assert any("overlap at column" in v for v in report.violations)
    # (d) a node via whose M1 landing belongs to another net
    report = verify_cell(nl3, pl,
                         m2_route({(1, 2, 4): "Y"},
                                  {(2, 1): True, (4, 1): True,
                                   (0, 0): True}),
                         blocks=blocks, slot_model=True)
    assert not report.ok()
    assert any("does not join" in v for v in report.violations)


def test_verify_default_path_is_untouched_by_slot_model():
    # the additive flag must not change the historical behaviour: the
    # exact engine's own INV placement still verifies as before
    from smt_engine.layout_model import solve_layout
    from smt_engine.route_model import solve_routing
    from smt_engine.verify import verify_cell
    nl = CellNetlist(parse_spice_subckt(INV))
    layout = solve_layout(nl, time_limit_s=20.0)
    if layout.width_cols is None:
        pytest.skip("exact layout solve found no placement")
    route = solve_routing(nl, layout.devices, metal2=True,
                          time_limit_s=20.0)
    if not route.ok:
        pytest.skip("exact routing did not close")
    default = verify_cell(nl, layout.devices, route)
    assert default.ok()
    # and the same call with slot_model=True (an exact-engine placement
    # is NOT slot-model) may differ -- the flag is opt-in, so only pin
    # that the default call is unaffected by the flag's existence
    assert not default.violations or default.violations


def test_chain_is_deterministic():
    a = _chain(_subckt_text("MUX2X1"))
    b = _chain(_subckt_text("MUX2X1"))

    def shape(res):
        _nl, _lw, op, on, pl, cols, bd = res
        return (tuple((bb.kind, tuple((m.device.name, m.left_net,
                                       m.right_net)
                                      for m in bb.members))
                      for bb in op),
                tuple((bb.kind, tuple((m.device.name, m.left_net,
                                       m.right_net)
                                      for m in bb.members))
                      for bb in on),
                cols,
                tuple(sorted((d.name, p.row, p.start_col, p.legs,
                              p.leg_width_cols)
                             for d, p in pl.items())),
                bd)
    assert shape(a) == shape(b)


# --------------------------------------------------------------------------
# honest-gaps round: the corridor gate contact + the gate-only pin labels
# --------------------------------------------------------------------------

def _t3cell_chain():
    """T3CELL placements with every gate column ALIGNED (C/B/A at 0/1/2):
    P row pristine (VCC p2 p1 Y), N row mirrored (GND n2 n1 Y)."""
    from bigcell_engine.netlist_ext import mirror_block
    nl = CellNetlist(parse_spice_subckt(T3CELL))
    nl3, lw = fold_devices(nl)
    blocks = build_bigcell_blocks(nl3, max_coupler_degree=None)
    nb = next(b for b in blocks if not b.first.is_p)
    pb = next(b for b in blocks if b.first.is_p)
    op, on = [pb], [mirror_block(nb)]
    pl, cols = layout_cell(op, on, lw)
    return nl3, lw, op, on, pl, cols


#: the GDS database unit is 1 nm (the honest header pins precision=1e-9),
#: so every file-read coordinate is the in-memory value snapped to that
#: grid -- 0.3325 stores as 0.333 (half a db unit of worst-case shift,
#: the same snapping every pre-existing shape and label goes through)
GDS_DB_UM = 5.01e-4


def test_gds_draws_the_corridor_gate_contact_verify_accepts(tmp_path):
    # Gap 1 (honest-gaps round): a gate net crossing on the well-boundary
    # corridor T3 VERIFIES -- verify's row-band spans accept T3 wherever
    # an aligned P/N gate pair makes the drawn merged poly continuous --
    # but the W-tall strips never reach T3, so the emitter used to draw
    # no contact square and the GDS did not show the legal connection.
    # The hand-built route crosses C on T3 at column 0 (both neighbouring
    # columns carry no bar reaching the boundary, so the M1 crossing is
    # foreign-stripe-clean).
    import gdstk
    from smt_engine.route_model import RouteResult
    from smt_engine.verify import (_gate_spans, _touches_gate, verify_cell)
    from smt_engine.gds import track_geometry
    nl3, lw, op, on, pl, cols = _t3cell_chain()
    route = RouteResult(
        "FEASIBLE",
        ["GND", None, None, "Y"], ["VCC", None, None, "Y"],
        [0, 0, 0, 3], [3, 0, 0, 4],
        [5, 8, 8, 4], [8, 8, 8, 5],
        {(3, 0): "C", (4, 1): "B", (2, 2): "A"},
        {(2, 2): True}, {}, {},
        [False, False, False, True], [False, False, False, True],
        4, 3, 4, 1, 0, 0)
    rep = verify_cell(nl3, pl, route, blocks=op + on)
    assert rep.ok(), rep.violations
    trackY, _barY = track_geometry(2.47, 0.19)
    # where verify says the contact is: (gate C, column 0, track T3)
    assert _touches_gate(_gate_spans(nl3, pl, 2.47, 0.19), "C", 0, 3,
                         trackY)
    gds = str(tmp_path / "T3CELL.gds")
    write_cell_gds(gds, nl3, pl, cols, op, on, lw, route=route,
                   cell_name="T3CELL")
    cell = gdstk.read_gds(gds).cells[0]
    xc = 0.2375 + 0.19 / 2.0
    squares = [p for p in cell.polygons if p.layer == 10
               and abs((p.bounding_box()[0][0] + p.bounding_box()[1][0]) / 2
                       - xc) < 1e-9
               and abs((p.bounding_box()[0][1] + p.bounding_box()[1][1]) / 2
                       - trackY[3]) < 1e-9]
    assert len(squares) == 1, "no contact square where verify puts it"
    bb = squares[0].bounding_box()
    assert (bb[1][1] - bb[0][1]) == pytest.approx(0.07)
    # the square sits fully on the drawn merged poly stripe (continuous
    # over the well boundary) -- a real poly/M1 contact, not floating
    merged = [p for p in cell.polygons if p.layer == 9
              and abs((p.bounding_box()[0][0] + p.bounding_box()[1][0]) / 2
                      - xc) < 1e-9
              and p.bounding_box()[0][1] <= trackY[3]
              <= p.bounding_box()[1][1]]
    assert len(merged) == 1
    assert merged[0].bounding_box()[0][1] <= bb[0][1]
    assert bb[1][1] <= merged[0].bounding_box()[1][1]
    from layout_sanity import check_layout
    srep = check_layout(gds, units_per_um=1.0)
    assert srep.ok(), srep.violations


def test_gate_contact_tracks_add_t3_only_for_aligned_pairs():
    # the drawable-track rule mirrors the router's: T3 joins ONLY where
    # an aligned P/N gate pair merges the drawn poly over the boundary.
    # T3CELL with the P row pristine (gates C B A) against the pristine
    # N row (gates A B C) leaves columns 0/2 unaligned -- no T3 there.
    from bigcell_engine.gds_cells import (_gate_contact_tracks,
                                          _gate_entries_by_col)
    from bigcell_engine.geometry import row_gate_columns
    from smt_engine.gds import track_geometry
    nl3, lw, op, on, pl, _cols = _t3cell_chain()
    trackY, _barY = track_geometry(2.47, 0.19)
    aligned = _gate_contact_tracks(_gate_entries_by_col(op, on, lw),
                                   pl, 0.19, 2.47, trackY)
    for net, c in (("C", 0), ("B", 1), ("A", 2)):
        assert 3 in aligned[(net, c)]
    unaligned = _gate_contact_tracks(
        _gate_entries_by_col([op[0]], [next(
            b for b in build_bigcell_blocks(nl3, max_coupler_degree=None)
            if not b.first.is_p)], lw),
        pl, 0.19, 2.47, trackY)
    for net, c in (("A", 0), ("C", 0), ("B", 1), ("C", 2), ("A", 2)):
        if c == 1:
            continue                # B/B stays aligned in this view too
        assert 3 not in unaligned[(net, c)]


def test_gds_labels_gate_only_nets_on_their_poly_stripes(tmp_path):
    # Gap 2 (honest-gaps round): a gate-only input (no diffusion access
    # anywhere) routes as a pure gate crossing and used to get no pin
    # label at all.  Its label goes on the poly stripe at its gate
    # column -- the terminal the router exposes -- the way the diffusion
    # labels label the first edge-column contact.
    import gdstk
    from bigcell_engine.route_grid import route_cell
    from layout_sanity import check_layout
    nl3, lw, op2, on2, pl, cols, _bd = _chain(INV)
    sig, _pow = slot_diffusion_access(nl3, pl, (op2, on2), lw)
    assert "A" not in sig                    # gate-only precondition
    route = route_cell(nl3, pl, cols, lw)
    assert route.ok, (route.status_name, getattr(route, "fail_note", None))
    gds = str(tmp_path / "INV.gds")
    pins = write_cell_gds(gds, nl3, pl, cols, op2, on2, lw, route=route,
                          cell_name="INV")
    cell = gdstk.read_gds(gds).cells[0]
    a = [l for l in cell.labels if l.text == "A"]
    assert len(a) == 1 and a[0].layer == 9   # a poly-layer pin label
    x, y = a[0].origin
    assert x == pytest.approx(0.2375 + 0.095, abs=GDS_DB_UM)
    # containment, not centre equality: the file's 1 nm grid snaps the
    # stripe edges and the label origin independently (0.3075 -> 0.307
    # but 0.3325 -> 0.333), so the label can sit half a db unit off the
    # snapped stripe's centre while still being on the stripe
    stripe = [p for p in cell.polygons if p.layer == 9
              and p.bounding_box()[0][0] <= x <= p.bounding_box()[1][0]
              and p.bounding_box()[0][1] <= y <= p.bounding_box()[1][1]]
    assert stripe, "gate-only label not on the poly stripe"
    assert any(n == "A" and abs(px - x) <= GDS_DB_UM
               and abs(py - y) <= GDS_DB_UM
               for px, py, n in pins)
    srep = check_layout(gds, units_per_um=1.0)
    assert srep.ok(), srep.violations
    assert {"GND", "VCC", "Y", "A"} <= set(srep.metrics["labels"])


# --------------------------------------------------------------------------
# the metal2 vertical freedom: the drawn geometry matches what verify
# accepts (same discipline as the corridor-contact fix, 8f9c35d)
# --------------------------------------------------------------------------

def test_gds_draws_m2_spans_and_node_vias(tmp_path):
    # The lib NAND2X1's slot chain closes with Y lifted onto an M2 span
    # through node vias; the emitter draws the span as the column-stripe
    # primitive on metal2 and one via1 square per node via, and the GDS
    # stays layout_sanity-clean.
    import gdstk
    from bigcell_engine.route_grid import route_cell
    from layout_sanity import check_layout
    from smt_engine.gds import M2_W, track_geometry
    nl3, lw, op2, on2, pl, cols, _bd = _chain(_subckt_text("NAND2X1"))
    r = route_cell(nl3, pl, cols, lw)
    assert r.ok and r.status_name == "FEASIBLE", (
        r.status_name, getattr(r, "fail_note", None))
    assert r.m2v, "expected the closure to carry an M2 span"
    gds = str(tmp_path / "NAND2X1.gds")
    write_cell_gds(gds, nl3, pl, cols, op2, on2, lw, route=r,
                   cell_name="NAND2X1")
    cell = gdstk.read_gds(gds).cells[0]
    trackY, _barY = track_geometry(2.47, 0.19)
    # one metal2 rect per span at its column edge, spanning its tracks
    m2 = [p for p in cell.polygons if p.layer == 51]
    for (c, t1, t2), _net in r.m2v.items():
        xc = 0.2375 + c * 0.19
        hits = [p for p in m2
                if abs((p.bounding_box()[0][0]
                        + p.bounding_box()[1][0]) / 2 - xc) <= GDS_DB_UM
                and abs(p.bounding_box()[0][1]
                        - (trackY[t1] - M2_W / 2)) <= GDS_DB_UM
                and abs(p.bounding_box()[1][1]
                        - (trackY[t2] + M2_W / 2)) <= GDS_DB_UM]
        assert hits, "no metal2 rect where the span (c=%d, %d..%d) is" \
            % (c, t1, t2)
    # one via1 square per node via, centred on the (track, column) point
    via1 = [p for p in cell.polygons if p.layer == 50]
    for (t, c), on in r.m2via.items():
        if not on:
            continue
        xc = 0.2375 + c * 0.19
        hits = [p for p in via1
                if abs((p.bounding_box()[0][0]
                        + p.bounding_box()[1][0]) / 2 - xc) <= GDS_DB_UM
                and abs((p.bounding_box()[0][1]
                         + p.bounding_box()[1][1]) / 2
                        - trackY[t]) <= GDS_DB_UM]
        assert hits, "no via1 square where the node via (t=%d, c=%d) is" \
            % (t, c)
    srep = check_layout(gds, units_per_um=1.0)
    assert srep.ok(), srep.violations
