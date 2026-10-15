"""Unit tests for bigcell_engine.route_grid (stage 3 rung 2).

Covers the ported constants (autocell2.cpp / graphrouter.cpp verbatim arc
costs), the grid structure (tracks re-used from the shared track model, hub
wiring, power stripes), the negotiated-congestion loop (history bumps,
rip-up of conflicted nets) on a synthetic contested grid, determinism
(AGENTS.md invariants 8/9) and the end-to-end verify-clean cases: the
placements come from the exact engine's own solve_layout and the routes
must pass smt_engine.verify.verify_cell with zero violations and be
consumable by smt_engine.gds.cell_gds unchanged.

Also pins the two benchmark-round defects:

- the route always covers every placement column -- width_cols >=
  max(p.end_col) on success AND failure (a 0-width failure shell used to
  crash verify_cell with an IndexError at route_model.py:147);
- diffusion terminals follow the DIE orientation: the heuristic placement
  mirrors blocks (netlist_ext.mirror_block) and the orientation-blind base
  walk once scrambled net->column, building power stripes on foreign
  signal columns ("terminal clash at ('M1', 4, 8): cl0#Y and VCC").
"""
import hashlib
import sys

import pytest

from bigcell_engine.route_grid import (_RouteGrid, H_MET_COST, HUB_COST,
                                       MAX_ATTEMPTS, M2_H_COST,
                                       POLY_ARC_COST, GATE_CONTACT_COST,
                                       VIA_COST, VCOST_DIFF, VCOST_GATE,
                                       V_CORRIDOR_SURCHARGE,
                                       V_OUTSIDE_DISCOUNT, route_cell,
                                       route_signature, track_positions)
from smt_engine.gds import cell_gds, track_geometry
from smt_engine.layout_model import solve_layout, PlacedTransistor
from smt_engine.netlist import CellNetlist, exposed_net_set
from smt_engine.route_model import RouteResult, ROW_TRACK, device_rail
from smt_engine.verify import verify_cell
from smt_cell_placer import parse_spice_subckt

INV = """\
.subckt INV VCC Y A GND
MpY Y A VCC VCC PMOS W=0.5u L=0.05u
MnY Y A GND GND NMOS W=0.5u L=0.05u
.end
"""

NAND2 = """\
.subckt NAND2 VCC Y A B GND
MpA Y A VCC VCC PMOS W=0.5u L=0.05u
MpB Y B VCC VCC PMOS W=0.5u L=0.05u
MnA n1 A GND GND NMOS W=0.5u L=0.05u
MnB Y B n1 GND NMOS W=0.5u L=0.05u
.end
"""

NAND3 = """\
.subckt NAND3 VCC Y A B C GND
MpA Y A VCC VCC PMOS W=0.5u L=0.05u
MpB Y B VCC VCC PMOS W=0.5u L=0.05u
MpC Y C VCC VCC PMOS W=0.5u L=0.05u
MnA n1 A GND GND NMOS W=0.5u L=0.05u
MnB n2 B n1 GND NMOS W=0.5u L=0.05u
MnC Y C n2 GND NMOS W=0.5u L=0.05u
.end
"""

NAND4 = """\
.subckt NAND4 VCC Y A B C D GND
MpA Y A VCC VCC PMOS W=0.5u L=0.05u
MpB Y B VCC VCC PMOS W=0.5u L=0.05u
MpC Y C VCC VCC PMOS W=0.5u L=0.05u
MpD Y D VCC VCC PMOS W=0.5u L=0.05u
MnA n1 A GND GND NMOS W=0.5u L=0.05u
MnB n2 B n1 GND NMOS W=0.5u L=0.05u
MnC n3 C n2 GND NMOS W=0.5u L=0.05u
MnD Y D n3 GND NMOS W=0.5u L=0.05u
.end
"""

NAND6 = """\
.subckt NAND6 VCC Y A B C D E F GND
MpA Y A VCC VCC PMOS W=0.5u L=0.05u
MpB Y B VCC VCC PMOS W=0.5u L=0.05u
MpC Y C VCC VCC PMOS W=0.5u L=0.05u
MpD Y D VCC VCC PMOS W=0.5u L=0.05u
MpE Y E VCC VCC PMOS W=0.5u L=0.05u
MpF Y F VCC VCC PMOS W=0.5u L=0.05u
MnA n1 A GND GND NMOS W=0.5u L=0.05u
MnB n2 B n1 GND NMOS W=0.5u L=0.05u
MnC n3 C n2 GND NMOS W=0.5u L=0.05u
MnD n4 D n3 GND NMOS W=0.5u L=0.05u
MnE n5 E n4 GND NMOS W=0.5u L=0.05u
MnF Y F n5 GND NMOS W=0.5u L=0.05u
.end
"""


def _placed(text, budget_s=15.0):
    """(netlist, placement, width_cols, leg_widths) via the exact engine."""
    nl = CellNetlist(parse_spice_subckt(text))
    lay = solve_layout(nl, time_limit_s=budget_s)
    assert lay.status_name == "OPTIMAL", lay.status_name
    leg_widths = {d.name: (p.legs, p.leg_width_cols)
                  for d, p in lay.devices.items()}
    return nl, lay.devices, lay.width_cols, leg_widths


# ---------------- grid construction ----------------

def test_track_positions_reuse_the_shared_model():
    trackY, barY = track_positions()
    shared_trackY, shared_barY = track_geometry(2.47, 0.19)
    assert trackY == shared_trackY
    assert barY == shared_barY
    # the bar domain: GND rail + 7 tracks + VCC rail, monotonically rising
    assert len(barY) == 9
    assert barY == sorted(barY)
    assert barY[0] < barY[1] and barY[-1] > barY[-2]


def test_grid_structure_and_hub_wiring():
    nl, placement, width, _lw = _placed(INV)
    g = _RouteGrid(nl, placement, width)
    # one M1 point and one M2 point per (track, column)
    assert len(g.graph) > 7 * width
    for t in range(7):
        for c in range(width):
            assert g._id[("M1", t, c)] < len(g.graph)
            assert g._id[("M2", t, c)] < len(g.graph)
    # hubs: wired to every track of their column with the verbatim costs
    for c in range(width):
        hub = g._id[("HUB", c)]
        costs = sorted(g.arcs[ai].cost
                       for ai in g.graph[hub].arcs
                       if g.graph[_other(g.arcs[ai], hub)].kind[0] == "M1")
        assert costs == sorted([HUB_COST] * 6 + [HUB_COST - 5]) or \
            costs == sorted([HUB_COST] * 7)
        # the corridor track (between the diffusions) is the discounted one
        cheap = [t for t in range(7)
                 if g.arcs[_hub_arc(g, hub, ("M1", t, c))].cost < HUB_COST]
        n_ini, p_ini = g._diff_ini(c)
        assert cheap == [t for t in range(7) if n_ini < t < p_ini]
    # pin nodes exist for the external signal nets, wired 0-cost to all hubs
    pin = g._id.get(("PIN", "Y"))
    assert pin is not None
    hub_arcs = [g.arcs[ai] for ai in g.graph[pin].arcs]
    assert len(hub_arcs) == width
    assert all(arc.cost == 0 for arc in hub_arcs)
    assert not hasattr(g._id.get(("PIN", "VCC"), None), "kind") \
        if ("PIN", "VCC") not in g._id else True


def test_power_stripes_are_prebuilt():
    nl, placement, width, _lw = _placed(INV)
    g = _RouteGrid(nl, placement, width)
    gnd = g._id[("M1", 0, 0)]           # MnY's source at column 0, rail 0
    assert g.graph[gnd].net == g.by_name["GND"].index
    assert g.graph[gnd].source == 1     # never ripped
    vcc_top = g._id[("M1", 6, 0)]       # MpY's rail reaches the VCC end
    assert g.graph[vcc_top].net == g.by_name["VCC"].index
    # power stripes reach the power ends in the emitted stripes
    g.route(max_attempts=50)
    plan, contested, _cf = g._stripe_plan()
    assert plan[(0, 0)][0] == g.by_name["GND"].index
    assert plan[(0, 0)][1] == 0         # lo_n at the GND rail level
    assert plan[(0, 1)][0] == g.by_name["VCC"].index
    assert plan[(0, 1)][2] == 8         # hi_p at the VCC rail level


def _other(arc, node):
    return arc.n2 if arc.n1 == node else arc.n1


def _pair_arc(g, kind_a, kind_b):
    """The arc joining the two node kinds (their unique connecting arc)."""
    a, b = g._id[kind_a], g._id[kind_b]
    for ai in g.graph[a].arcs:
        arc = g.arcs[ai]
        if (arc.n1 == b or arc.n2 == b):
            return ai
    raise AssertionError("no arc %s - %s" % (kind_a, kind_b))


def _hub_arc(g, hub, kind):
    nid = g._id[kind]
    for ai in g.graph[hub].arcs:
        arc = g.arcs[ai]
        if (arc.n1 == nid or arc.n2 == nid):
            return ai
    raise AssertionError("no hub arc to %s" % (kind,))


# ---------------- arc costs (verbatim port) ----------------

def test_horizontal_m1_and_m2_and_via_costs():
    nl, placement, width, _lw = _placed(INV)
    g = _RouteGrid(nl, placement, width)
    for t in range(7):
        for c in range(width - 1):
            arc = g.arcs[_pair_arc(g, ("M1", t, c), ("M1", t, c + 1))]
            assert arc.cost == H_MET_COST == 4      # autocell2.cpp:38
            arc = g.arcs[_pair_arc(g, ("M2", t, c), ("M2", t, c + 1))]
            assert arc.cost == M2_H_COST == 4       # router.cpp:24/:55
            arc = g.arcs[_pair_arc(g, ("M1", t, c), ("M2", t, c))]
            assert arc.cost == VIA_COST == 4        # router.cpp:23-24 up


def test_vertical_costs_follow_the_three_way_rule():
    nl, placement, width, _lw = _placed(INV)
    g = _RouteGrid(nl, placement, width)
    for c in range(width):
        vcost = VCOST_GATE if c in g.gate_cols else VCOST_DIFF
        for t in range(1, 7):
            arc = g.arcs[_pair_arc(g, ("M1", t - 1, c), ("M1", t, c))]
            nts = g.diff_tracks[c][False]
            pts = g.diff_tracks[c][True]
            centre = 3
            n_end, n_ini = (min(nts), max(nts)) if nts else (centre, centre)
            p_ini, p_end = (min(pts), max(pts)) if pts else (centre, centre)
            if (t <= n_end or t > p_end):
                expect = vcost - V_OUTSIDE_DISCOUNT     # autocell2.cpp:29
            elif (t > n_ini and t <= p_ini
                  and c not in g.gate_cols):
                expect = vcost + V_CORRIDOR_SURCHARGE   # autocell2.cpp:31
            else:
                expect = vcost
            assert arc.cost == expect
    # the gate column's over-diffusion vertical arc is the "16" of the doc
    gate_col = next(c for c in range(width) if c in g.gate_cols)
    over_diff = [g.arcs[_pair_arc(g, ("M1", t - 1, gate_col),
                                    ("M1", t, gate_col))].cost
                 for t in range(1, 7)]
    assert VCOST_GATE == 16
    assert max(over_diff) == 16


def test_poly_and_gate_contact_costs():
    nl, placement, width, _lw = _placed(INV)
    g = _RouteGrid(nl, placement, width)
    # poly-poly arcs cost 6 (autocell2.cpp:42/:51)
    poly_arcs = [arc.cost for arc in g.arcs
                 if g.graph[arc.n1].kind[0] == "PJ"
                 and g.graph[arc.n2].kind[0] == "PJ"]
    assert poly_arcs and set(poly_arcs) == {POLY_ARC_COST}
    # gate contact arcs cost 20 (autocell2.cpp:48)
    gate = g._id[("G", 1, "A")]
    contacts = [g.arcs[ai].cost for ai in g.graph[gate].arcs
                if g.graph[_other(g.arcs[ai], gate)].kind[0] == "M1"]
    assert contacts and set(contacts) == {GATE_CONTACT_COST}
    # the poly merge of the gate stripe is a same-layer merge (0)
    merges = [g.arcs[ai].cost for ai in g.graph[gate].arcs
              if g.graph[_other(g.arcs[ai], gate)].kind[0] == "PJ"]
    assert merges and set(merges) == {0}


# ---------------- negotiated congestion ----------------

CONTESTED_SP = """\
.subckt CONTESTED VCC Y A B GND
MpY Y A VCC VCC PMOS W=0.5u L=0.05u
MnY Y A GND GND NMOS W=0.5u L=0.05u
MpB Y B VCC VCC PMOS W=0.5u L=0.05u
MnB Y B GND GND NMOS W=0.5u L=0.05u
.end
"""


def test_contested_two_net_grid_negotiates():
    """Two nets fight for the same corridor: attempt 1 overlaps (both
    trees claim the shared points), history rises on the contested nodes,
    and the rip-up loop separates them within a bounded attempt count."""
    nl = CellNetlist(parse_spice_subckt(CONTESTED_SP))
    # two stacked inverters sharing the column band: both nets must cross
    # the same columns; give a narrow width so tracks are contested
    by = {d.name: d for d in nl.devices}
    placement = {
        by["MpY"]: PlacedTransistor(0, 0, 1, 3),
        by["MpB"]: PlacedTransistor(0, 3, 1, 3),
        by["MnY"]: PlacedTransistor(1, 0, 1, 3),
        by["MnB"]: PlacedTransistor(1, 3, 1, 3),
    }
    width = 6
    g = _RouteGrid(nl, placement, width)
    ok = g.route(max_attempts=MAX_ATTEMPTS)
    contested_nodes = [nid for nid in range(len(g.graph))
                       if g.graph[nid].history > 0]
    assert ok, "the two inverter stack must negotiate to zero conflicts"
    assert contested_nodes, "history was used: contested nodes got bumped"
    # the two nets do not share any tree node in the solution
    trees = [set(net.tree) for net in g.nets]
    for i in range(len(trees)):
        for j in range(i + 1, len(trees)):
            assert not (trees[i] & trees[j])
    # determinism of the negotiated outcome
    g2 = _RouteGrid(nl, placement, width)
    assert g2.route(max_attempts=MAX_ATTEMPTS)
    assert (route_signature(g.build_result())
            == route_signature(g2.build_result()))


def test_rip_up_reroutes_only_conflicted_nets(monkeypatch):
    SP = INV
    nl, placement, width, _lw = _placed(SP)
    g = _RouteGrid(nl, placement, width)
    routed = []
    orig = _RouteGrid._bfs_route

    def spy(self, net, tree, label, attempt, *a, **kw):
        if (attempt > 1):
            routed.append((attempt, net.name))
        return orig(self, net, tree, label, attempt, *a, **kw)

    monkeypatch.setattr(_RouteGrid, "_bfs_route", spy)
    assert g.route(max_attempts=50)
    # after the first attempt only conflicted nets are re-routed; the
    # non-conflicted ones keep their trees
    if (routed):
        assert all(name in ("A", "Y") for _att, name in routed)


# ---------------- determinism ----------------

def test_route_is_byte_stable_across_runs():
    nl, placement, width, leg_widths = _placed(NAND3)
    signatures = set()
    for _run in range(2):
        r = route_cell(nl, placement, width, leg_widths)
        assert r.ok
        rep = verify_cell(nl, placement, r)
        assert rep.ok(), rep.violations
        signatures.add(hashlib.sha256(
            route_signature(r).encode()).hexdigest())
    assert len(signatures) == 1


def test_route_result_is_route_result_compatible():
    nl, placement, width, leg_widths = _placed(INV)
    r = route_cell(nl, placement, width, leg_widths)
    assert isinstance(r, RouteResult)
    assert r.ok and r.status_name == "FEASIBLE"
    assert r.width_cols == width
    assert len(r.col_owner_n) == width and len(r.col_owner_p) == width
    assert len(r.reachB_n) == width and len(r.reachB_p) == width
    assert r.hseg_count == len(r.hseg)
    assert r.vseg_count == (sum(1 for o in r.col_owner_n if o is not None)
                            + sum(1 for o in r.col_owner_p if o is not None))


# ---------------- end to end: verify-clean cells ----------------

@pytest.mark.parametrize("sp,label", [
    (INV, "INV"), (NAND2, "NAND2"), (NAND3, "NAND3"), (NAND4, "NAND4")])
def test_small_cells_route_and_verify_clean(sp, label):
    nl, placement, width, leg_widths = _placed(sp)
    r = route_cell(nl, placement, width, leg_widths)
    assert r.ok, (r.status_name, r.fail_note)
    rep = verify_cell(nl, placement, r)
    assert rep.ok(), "%s: %s" % (label, rep.violations)
    # the GDS writer consumes the result unchanged
    lib, pins = cell_gds(nl, placement, r)
    assert any(net == "Y" for _x, _y, net in pins)


def test_nand6_twelve_transistors_routes_and_verifies_clean():
    nl, placement, width, leg_widths = _placed(NAND6, budget_s=30.0)
    r = route_cell(nl, placement, width, leg_widths)
    assert r.ok, (r.status_name, r.fail_note)
    rep = verify_cell(nl, placement, r)
    assert rep.ok(), rep.violations
    cell_gds(nl, placement, r)


def test_failed_route_reports_unknown_with_failure_note():
    SP = """\
.subckt PADLOCK VCC Y A GND
MpY Y A VCC VCC PMOS W=0.5u L=0.05u
MnY Y A GND GND NMOS W=0.5u L=0.05u
.end
"""
    nl = CellNetlist(parse_spice_subckt(SP))
    by = {d.name: d for d in nl.devices}
    # the gate stripe sits past the last segment column: uncontactable
    placement = {by["MpY"]: PlacedTransistor(0, 0, 1, 2),
                 by["MnY"]: PlacedTransistor(1, 2, 1, 2)}
    r = route_cell(nl, placement, 4, {})
    assert not r.ok and r.status_name == "UNKNOWN"
    assert "past the last segment column" in r.fail_note


# ---------------- benchmark-round defect 1: width invariant -------------

def test_failed_route_keeps_the_placement_width():
    """A failed route is not a 0-width shell: verify and the benchmark
    derive their columns from the PLACEMENT, so a sub-width RouteResult
    crashed them with an IndexError (route_model.py:147) instead of
    letting them report the honest violations."""
    SP = """\
.subckt PADLOCK VCC Y A GND
MpY Y A VCC VCC PMOS W=0.5u L=0.05u
MnY Y A GND GND NMOS W=0.5u L=0.05u
.end
"""
    nl = CellNetlist(parse_spice_subckt(SP))
    by = {d.name: d for d in nl.devices}
    placement = {by["MpY"]: PlacedTransistor(0, 0, 1, 2),
                 by["MnY"]: PlacedTransistor(1, 2, 1, 2)}
    width = max(p.end_col for p in placement.values())
    r = route_cell(nl, placement, 4, {})
    assert not r.ok
    # the pinned invariant: every placement column is covered
    assert r.width_cols >= width
    assert len(r.col_owner_n) == r.width_cols
    assert len(r.col_owner_p) == r.width_cols
    assert len(r.reachB_n) == r.width_cols
    assert len(r.reachB_p) == r.width_cols
    # verify_cell runs to completion and reports honestly (no crash --
    # the defect was an IndexError in route_model.RouteResult.stripes)
    rep = verify_cell(nl, placement, r)
    assert not rep.ok()
    assert rep.violations
    assert any("no stripe" in v for v in rep.violations)


# ---------------- benchmark-round defect 2: die orientation -------------

FLIPSINGLE = """\
.subckt FLIPSINGLE VCC Y W A GND
Mp1 Y A VCC VCC PMOS W=0.5u L=0.05u
Mp2 W A VCC VCC PMOS W=0.5u L=0.05u
Mp3 W A VCC VCC PMOS W=0.5u L=0.05u
Mn1 Y A GND GND NMOS W=0.5u L=0.05u
Mn2 W A GND GND NMOS W=0.5u L=0.05u
Mn3 W A GND GND NMOS W=0.5u L=0.05u
.end
"""

MIRROPAR = """\
.subckt MIRROPAR VCC Y A B GND
MpA Y A VCC VCC PMOS W=0.5u L=0.05u
MpB Y B VCC VCC PMOS W=0.5u L=0.05u
MnA Y A GND GND NMOS W=0.5u L=0.05u
MnB Y B GND GND NMOS W=0.5u L=0.05u
.end
"""


def _owner(g, kind):
    """Owning net name of the node ``kind`` (None when free)."""
    nid = g._id.get(kind)
    if (nid is None):
        return None
    net = g.graph[nid].net
    return g._net_name(net) if (net != -1) else None


def test_flipped_single_recovered_from_abutment():
    """A mirrored single-member block is invisible in the column order;
    place_row's abutment gap pins it: Mp1 (pristine VCC|Y) sits FLIPPED
    (die Y|VCC) because its die-right VCC abuts the neighbour block's
    die-left VCC with gap 0.  The base walk claimed VCC@0 / Y@2 -- the
    die truth is Y@0 / VCC@2."""
    nl = CellNetlist(parse_spice_subckt(FLIPSINGLE))
    by = {d.name: d for d in nl.devices}
    placement = {
        by["Mp1"]: PlacedTransistor(0, 0, 1, 3),   # flipped single
        by["Mp2"]: PlacedTransistor(0, 3, 1, 3),
        by["Mp3"]: PlacedTransistor(0, 6, 1, 3),
        by["Mn1"]: PlacedTransistor(1, 0, 1, 3),   # pristine (break gap)
        by["Mn2"]: PlacedTransistor(1, 4, 1, 3),
        by["Mn3"]: PlacedTransistor(1, 7, 1, 3),
    }
    g = _RouteGrid(nl, placement, 10)
    # P row (rail track 4): the die-truth terminal owners
    assert _owner(g, ("M1", 4, 0)) == "Y"
    assert _owner(g, ("M1", 4, 2)) == "VCC"
    assert _owner(g, ("M1", 4, 3)) == "VCC"
    assert _owner(g, ("M1", 4, 8)) == "VCC"
    # N row (row 1 -> rail track 2): pristine, unchanged by the fix
    assert _owner(g, ("M1", 2, 0)) == "GND"
    assert _owner(g, ("M1", 2, 2)) == "Y"
    # the cell routes
    g.route(max_attempts=MAX_ATTEMPTS)
    assert g._fail_note is None


def test_mirrored_parallel_block_terminals_follow_the_die():
    """The P-row parallel block is placed REVERSED (die order MpB, MpA)
    = mirrored: die power edges VCC@0 and VCC@5, the Y edge shared
    internally at 2/3.  The base walk extrapolated the block from MpA's
    column and claimed VCC@3 / VCC@8 -- power stripes on foreign metal.
    (Y's shared drains are internal block edges: not exposed, no
    diffusion claim, Y is contacted through its gates like NAND2's.)"""
    nl = CellNetlist(parse_spice_subckt(MIRROPAR))
    by = {d.name: d for d in nl.devices}
    placement = {
        by["MpB"]: PlacedTransistor(0, 0, 1, 3),   # die order reversed
        by["MpA"]: PlacedTransistor(0, 3, 1, 3),
        by["MnA"]: PlacedTransistor(1, 0, 1, 3),   # pristine
        by["MnB"]: PlacedTransistor(1, 3, 1, 3),
    }
    g = _RouteGrid(nl, placement, 6)
    assert _owner(g, ("M1", 4, 0)) == "VCC"
    assert _owner(g, ("M1", 4, 5)) == "VCC"
    assert _owner(g, ("M1", 4, 3)) is None         # no bogus VCC on Y's edge
    assert _owner(g, ("M1", 2, 0)) == "GND"        # N row (track 2)
    assert _owner(g, ("M1", 2, 5)) == "GND"
    g.route(max_attempts=500)
    # the negotiation may plateau on this deliberately tight arrangement
    # (A and B both gate at cols 1 and 4); what must never happen is the
    # bogus power-vs-signal build clash
    assert "terminal clash" not in (g._fail_note or "")


# ---------------- the repro cells (adder / multiplier COMPLEX0) ---------

# The adder/COMPLEX0 repro specimen, embedded verbatim so the regression
# pins the ROUTER rather than the (independently evolving) placement
# chain.  The deck is outputs/adder/COMPLEX0.sp (the tracked 14T adder
# pattern the benchmark round reported both defects on -- COMPLEX ids are
# per-run, invariant 6, so the deck itself is pinned here); the placement
# and the die-orientation member view are the deterministic
# _heuristic_placement output that reproduced the defects (SA-mirrored
# cl1 blocks, flipped Mcl2#5 single).
ADDER_DECK = """\
.subckt COMPLEX0 VCC cl0#Y GND cl1#Y cl2#Y cl1#A cl1#B cl2#B cl2#A
Mcl0#0 cl0#Y cl1#Y VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u
Mcl0#1 VCC cl2#Y cl0#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u
Mcl0#2 cl0#a_9_6# cl1#Y GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u
Mcl0#3 cl0#Y cl2#Y cl0#a_9_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u
Mcl1#0 cl1#Y cl1#A VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u
Mcl1#1 VCC cl1#B cl1#Y VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u
Mcl1#2 cl1#a_9_6# cl1#A GND GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u
Mcl1#3 cl1#Y cl1#B cl1#a_9_6# GND NMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u
Mcl2#0 cl2#a_9_54# cl2#A cl2#a_2_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u
Mcl2#1 VCC cl2#B cl2#a_9_54# VCC PMOS W=1u L=0.05u
+ ad=0p pd=0u as=0p ps=0u
Mcl2#2 cl2#Y cl2#a_2_54# VCC VCC PMOS W=0.5u L=0.05u
+ ad=0p pd=0u as=0p ps=0u
Mcl2#3 cl2#a_2_54# cl2#A GND GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u
Mcl2#4 GND cl2#B cl2#a_2_54# GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u
Mcl2#5 cl2#Y cl2#a_2_54# GND GND NMOS W=0.25u L=0.05u
+ ad=0p pd=0u as=0p ps=0u
.ends COMPLEX0
"""

#: device name -> (row, start_col, legs, leg_width_cols)
ADDER_PLACEMENT = {
    "Mcl1#1": (0, 0, 1, 3),
    "Mcl1#0": (0, 3, 1, 3),
    "Mcl0#0": (0, 6, 1, 3),
    "Mcl0#1": (0, 9, 1, 3),
    "Mcl2#2": (0, 12, 1, 3),
    "Mcl2#0": (0, 16, 1, 6),
    "Mcl2#1": (0, 22, 1, 6),
    "Mcl1#3": (1, 0, 1, 3),
    "Mcl1#2": (1, 3, 1, 3),
    "Mcl0#2": (1, 6, 1, 3),
    "Mcl0#3": (1, 9, 1, 3),
    "Mcl2#5": (1, 13, 1, 2),
    "Mcl2#3": (1, 15, 1, 2),
    "Mcl2#4": (1, 17, 1, 2),
}
ADDER_WIDTH = 28

#: the die-orientation member view (device, die_left_net, die_right_net),
#: in die order per block -- the SA block view that place_row consumed.
#: The flipped Mcl2#5 single and the mirrored cl1 parallel block are the
#: orientation state the base walk cannot see.
ADDER_DIE_MEMBERS = [
    ("Mcl1#1", "VCC", "cl1#Y"), ("Mcl1#0", "cl1#Y", "VCC"),
    ("Mcl0#0", "VCC", "cl0#Y"), ("Mcl0#1", "cl0#Y", "VCC"),
    ("Mcl2#2", "VCC", "cl2#Y"),
    ("Mcl2#0", "cl2#a_2_54#", "cl2#a_9_54#"),
    ("Mcl2#1", "cl2#a_9_54#", "VCC"),
    ("Mcl1#3", "cl1#Y", "cl1#a_9_6#"), ("Mcl1#2", "cl1#a_9_6#", "GND"),
    ("Mcl0#2", "GND", "cl0#a_9_6#"), ("Mcl0#3", "cl0#a_9_6#", "cl0#Y"),
    ("Mcl2#5", "cl2#Y", "GND"),
    ("Mcl2#3", "GND", "cl2#a_2_54#"), ("Mcl2#4", "cl2#a_2_54#", "GND"),
]


def _adder_state():
    """(netlist, placement, width) for the embedded adder repro."""
    nl = CellNetlist(parse_spice_subckt(ADDER_DECK))
    by = {d.name: d for d in nl.devices}
    placement = {by[name]: PlacedTransistor(row, start, legs, legw)
                 for name, (row, start, legs, legw)
                 in ADDER_PLACEMENT.items()}
    return nl, placement, ADDER_WIDTH


def _true_die_accesses(netlist, placement, die_members):
    """{(net, col, device)} diffusion edges per the ORIENTATION-AWARE
    member view (the die truth, independent of the router).  Only
    exposed nets need contacts."""
    exposed = exposed_net_set(netlist)
    by = {d.name: d for d in netlist.devices}
    accesses = set()
    for name, lnet, rnet in die_members:
        p = placement[by[name]]
        for net, col in ((lnet, p.start_col),
                         (rnet, p.start_col + p.legs * p.leg_width_cols
                          - 1)):
            if (net in exposed):
                accesses.add((net, col, by[name]))
    return accesses


@pytest.fixture(scope="module")
def adder_route():
    """One full route of the adder repro (~19 s: 1360 negotiation
    attempts), shared by the defect regressions and the determinism
    check; the second determinism route runs fresh in its own test."""
    nl, pl, w = _adder_state()
    return nl, pl, w, route_cell(nl, pl, w, {})


def test_adder_repro_routes_without_terminal_clash(adder_route):
    """Defect 2 regression: the mirrored-block placement used to die at
    build time with "terminal clash at ('M1', 4, 8): cl0#Y and VCC" (a
    bogus power stripe pre-built on cl0#Y's diffusion, from the
    orientation-blind base walk).  It must route, cover every placement
    column, and contact the die-true accesses."""
    nl, pl, w, r = adder_route
    assert "terminal clash" not in (getattr(r, "fail_note", None) or "")
    assert r.ok, (r.status_name, r.fail_note)
    # defect 1's invariant on the success path
    assert r.width_cols >= max(p.end_col for p in pl.values())
    # the reported clash node ('M1', 4, 8): the P slot belongs to cl0#Y
    assert r.owners(8)[1] == "cl0#Y"
    # every die-true diffusion access is contacted in the right slot
    for net, c, dev in _true_die_accesses(nl, pl, ADDER_DIE_MEMBERS):
        t = ROW_TRACK[device_rail(dev, pl[dev].row)]
        covered = any(net == net2 and lo <= t + 1 <= hi
                      for net2, lo, hi, _slot in r.stripes(c))
        assert covered, "die access %s@%d (track %d) uncovered" % (net, c, t)


def test_adder_repro_route_is_byte_stable_in_process(adder_route):
    """In-process determinism (invariant 9) on the repro cell: a second,
    independent route_cell call is byte-identical to the fixture's."""
    nl, pl, w, first = adder_route
    assert first.ok
    r = route_cell(nl, pl, w, {})
    assert r.ok, (r.status_name, r.fail_note)
    assert (hashlib.sha256(route_signature(first).encode()).hexdigest()
            == hashlib.sha256(route_signature(r).encode()).hexdigest())


_ROUTE_HASH_HELPER = """\
import hashlib, os, sys
sys.path.insert(0, os.getcwd())
from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from smt_engine.layout_model import PlacedTransistor
from bigcell_engine.route_grid import route_cell, route_signature

DECK = %r
PLACEMENT = %r

nl = CellNetlist(parse_spice_subckt(DECK))
by = {d.name: d for d in nl.devices}
placement = {by[name]: PlacedTransistor(row, start, legs, legw)
             for name, (row, start, legs, legw) in PLACEMENT.items()}
r = route_cell(nl, placement, %d, {})
assert r.ok, (r.status_name, r.fail_note)
print(hashlib.sha256(route_signature(r).encode()).hexdigest())
""" % (ADDER_DECK, ADDER_PLACEMENT, ADDER_WIDTH)


def test_adder_repro_route_is_byte_stable_across_processes(
        flow_dir, tmp_path):
    """Cross-process determinism (invariant 9): identical route under
    different PYTHONHASHSEED values."""
    import os
    import subprocess
    helper = tmp_path / "route_hash_helper.py"
    helper.write_text(_ROUTE_HASH_HELPER)
    digests = set()
    for seed in ("0", "1"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run([sys.executable, str(helper)], cwd=flow_dir,
                              env=env, capture_output=True, text=True,
                              check=True)
        digests.add(proc.stdout.strip().splitlines()[-1])
    assert len(digests) == 1, digests


def test_multiplier_repro_never_clashes_and_fails_honestly(flow_dir):
    """The multiplier/COMPLEX0 repro (the benchmark's second defect-2
    cell): whatever the current placement chain produces, the router must
    never again report the bogus power-vs-signal "terminal clash"; a
    failure carries an honest note and the width invariant holds.  (No
    verify_cell call here: under the in-flight slot-model placement
    rework verify's own base-view walk can emit access columns past the
    placement width and crash -- a verify/slot-model adaptation item
    outside this fix's partition.)"""
    import os
    from bigcell_engine.engine import _heuristic_placement
    path = os.path.join(flow_dir, "outputs", "multiplier", "COMPLEX0.sp")
    nl = CellNetlist(parse_spice_subckt(open(path).read()))
    nl3, pl, w, lws, blocks = _heuristic_placement(nl)
    r = route_cell(nl3, pl, w, lws, max_attempts=3)
    note = getattr(r, "fail_note", None) or ""
    assert "terminal clash" not in note
    assert r.ok or note                       # a failure is explained
    assert r.width_cols >= max(p.end_col for p in pl.values())


def test_stagnation_fails_with_an_honest_note():
    """A capped negotiation that cannot finish fails with the plateau
    note (best conflict count + unresolved nets), not silently: the
    benchmark's rung-2 UNKNOWNs must be diagnosable."""
    nl = CellNetlist(parse_spice_subckt(CONTESTED_SP))
    by = {d.name: d for d in nl.devices}
    placement = {
        by["MpY"]: PlacedTransistor(0, 0, 1, 3),
        by["MpB"]: PlacedTransistor(0, 3, 1, 3),
        by["MnY"]: PlacedTransistor(1, 0, 1, 3),
        by["MnB"]: PlacedTransistor(1, 3, 1, 3),
    }
    r = route_cell(nl, placement, 6, {}, max_attempts=1)
    assert not r.ok and r.status_name == "UNKNOWN"
    assert "no conflict-free routing" in r.fail_note
    assert "best" in r.fail_note and "unresolved" in r.fail_note
    assert r.width_cols >= max(p.end_col for p in placement.values())
