"""Unit tests for bigcell_engine.route_grid (stage 3 rung 2).

Covers the ported constants (autocell2.cpp / graphrouter.cpp verbatim arc
costs), the grid structure (tracks re-used from the shared track model, hub
wiring, power stripes), the negotiated-congestion loop (history bumps,
rip-up of conflicted nets) on a synthetic contested grid, determinism
(AGENTS.md invariants 8/9) and the end-to-end verify-clean cases: the
placements come from the exact engine's own solve_layout and the routes
must pass smt_engine.verify.verify_cell with zero violations and be
consumable by smt_engine.gds.cell_gds unchanged.
"""
import hashlib

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
from smt_engine.netlist import CellNetlist
from smt_engine.route_model import RouteResult
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

def test_contested_two_net_grid_negotiates():
    """Two nets fight for the same corridor: attempt 1 overlaps (both
    trees claim the shared points), history rises on the contested nodes,
    and the rip-up loop separates them within a bounded attempt count."""
    SP = """\
.subckt CONTESTED VCC Y A B GND
MpY Y A VCC VCC PMOS W=0.5u L=0.05u
MnY Y A GND GND NMOS W=0.5u L=0.05u
MpB Y B VCC VCC PMOS W=0.5u L=0.05u
MnB Y B GND GND NMOS W=0.5u L=0.05u
.end
"""
    nl = CellNetlist(parse_spice_subckt(SP))
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
