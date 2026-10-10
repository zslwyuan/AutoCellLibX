"""Unit tests for the SMT cell-synthesis engine (flow/smt_engine)."""
import pytest

from smt_engine import synth_cell
from smt_engine.gds import cell_gds, row_geometry
from smt_engine.layout_model import solve_layout
from smt_engine.netlist import (CellNetlist, build_diffusion_blocks,
                                diffusion_access_points, exposed_net_set,
                                find_parallel_groups, find_series_chains,
                                gate_access_points)
from smt_engine.route_model import _access_points, solve_routing
from smt_cell_placer import parse_spice_subckt

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


def test_chain_and_group_structure():
    nl = CellNetlist(parse_spice_subckt(NAND2))
    chains, internal = find_series_chains(nl)
    assert [d.name for d in chains[0]] == ["MnA", "MnB"]
    assert internal == {"n1"}
    groups = find_parallel_groups(nl)
    assert len(groups) == 1
    assert [d.name for d in groups[0]] == ["MpA", "MpB"]
    blocks = build_diffusion_blocks(nl)
    byKind = {}
    for b in blocks:
        byKind.setdefault(b.kind, []).append(b)
    assert len(byKind["series"]) == 1 and len(byKind["parallel"]) == 1
    # alternating orientation: shared edges same-net
    gp = byKind["parallel"][0]
    assert gp.members[0].right_net == gp.members[1].left_net == "Y"


def test_internal_node_with_gate_is_not_a_chain():
    # a net that is also a gate cannot be a diffusion-sharing point
    sp = """\
.subckt T VCC Y A B GND
M1 Y A n1 GND NMOS W=0.5u L=0.05u
M2 n1 B GND GND NMOS W=0.5u L=0.05u
M3 Y n1 VCC VCC PMOS W=0.5u L=0.05u
.end
"""
    nl = CellNetlist(parse_spice_subckt(sp))
    chains, internal = find_series_chains(nl)
    assert internal == set()        # n1 feeds a gate -> not shareable
    assert len(chains) == 3 and all(len(c) == 1 for c in chains)


def test_exposed_nets_exclude_pure_internal_nodes():
    nl = CellNetlist(parse_spice_subckt(NAND2))
    exposed = exposed_net_set(nl)
    assert "n1" not in exposed
    assert {"VCC", "GND", "Y"} <= exposed


def test_inv_full_chain(tmp_path):
    r = synth_cell(INV, layout_time_s=10, route_time_s=15)
    assert r.ok
    assert r.layout.width_cols == 3
    assert r.route.hseg_count == 1
    lib, pins = cell_gds(r.netlist, r.layout.devices, r.route)
    assert pins and all(p[2] in ("Y", "A", "VCC", "GND") for p in pins)


def test_nand2_full_chain():
    r = synth_cell(NAND2, layout_time_s=15, route_time_s=25)
    assert r.ok, "violations: %s" % (r.report.violations if r.report else None)
    assert r.layout.width_cols == 6
    assert r.route.hseg_count >= 3
    assert r.route.vseg_count >= 4


def test_nand2_deterministic():
    a = synth_cell(NAND2, layout_time_s=15, route_time_s=25)
    b = synth_cell(NAND2, layout_time_s=15, route_time_s=25)
    assert a.layout.width_cols == b.layout.width_cols
    assert a.route.hseg == b.route.hseg
    assert a.route.col_owner_n == b.route.col_owner_n


def test_power_ends_reach_power_rails():
    nl = CellNetlist(parse_spice_subckt(NAND2))
    sol = solve_layout(nl, time_limit_s=15)
    rt = solve_routing(nl, sol.devices, time_limit_s=25)
    assert rt.ok
    for c in range(rt.width_cols):
        for net, lo, hi, slot in rt.stripes(c):
            if (net in ("VCC", "VDD")):
                assert hi == 5
            if (net in ("GND", "VSS")):
                assert hi == 4


def test_pn_stripes_may_share_a_column():
    """NAND2 packs P and N ends into the same columns (real GSCL45
    NAND2X1 behaviour): both slots of one column may be occupied."""
    nl = CellNetlist(parse_spice_subckt(NAND2))
    sol = solve_layout(nl, time_limit_s=15)
    rt = solve_routing(nl, sol.devices, time_limit_s=25)
    shared = [c for c in range(rt.width_cols)
              if rt.col_owner_n[c] is not None
              and rt.col_owner_p[c] is not None]
    assert shared, "expected at least one P/N shared column"


def test_row_geometry_rails_are_y_ordered():
    railY, rows = row_geometry(2.47, 0.19)
    assert railY[4] < railY[0] < railY[1] < railY[2] < railY[3] < railY[5]


def test_engine_gds_consumed_by_existing_checkers(in_flow, tmp_path):
    """The emitted GDS must pass the repo's own layout-sanity checker
    (with units_per_um=1.0: the engine writes an honest header)."""
    from layout_sanity import check_layout
    r = synth_cell(NAND2, layout_time_s=15, route_time_s=25)
    assert r.ok
    gds = str(tmp_path / "nand2.gds")
    lib, pins = cell_gds(r.netlist, r.layout.devices, r.route)
    lib.write_gds(gds)
    report = check_layout(gds, units_per_um=1.0)
    assert report.ok(), report.as_dict()


def test_unroutable_cell_reports_cleanly():
    """A cell the model cannot route must fail loudly, not silently."""
    sp = """\
.subckt BIG VCC Y A B C GND
Mp Y A n1 VCC PMOS W=1.0u L=0.05u
Mn n1 B GND GND NMOS W=1.0u L=0.05u
.end
"""
    r = synth_cell(sp, layout_time_s=5, route_time_s=5)
    # either the model routes it, or the failure is loud and clean
    assert (r.ok
            or (r.route is not None and not r.route.ok
                and r.report is None))


def test_pn_halves_join_at_a_dual_column():
    """NAND2's Y (P ends + N ends) must be one electrically continuous
    net: the solver picks a dual column whose two bars both reach the
    well boundary, and the exact connectivity check passes."""
    nl = CellNetlist(parse_spice_subckt(NAND2))
    sol = solve_layout(nl, time_limit_s=15)
    rt = solve_routing(nl, sol.devices, time_limit_s=25)
    assert rt.ok
    duals = [c for c in range(rt.width_cols)
             if rt.col_owner_n[c] is not None
             and rt.col_owner_n[c] == rt.col_owner_p[c]]
    assert duals, "expected a same-net dual column"
    for c in duals:
        assert rt.reachB_n[c] and rt.reachB_p[c]
    from smt_engine.verify import verify_cell
    report = verify_cell(nl, sol.devices, rt)
    assert report.ok(), report.violations


def test_cross_net_dual_bars_must_not_both_reach_boundary():
    """NAND2 packs GND and VCC ends into one column (different nets):
    legal because neither bar reaches the boundary; forcing both to
    reach it is a short and must be reported."""
    nl = CellNetlist(parse_spice_subckt(NAND2))
    sol = solve_layout(nl, time_limit_s=15)
    rt = solve_routing(nl, sol.devices, time_limit_s=25)
    assert rt.ok
    cross = [c for c in range(rt.width_cols)
             if rt.col_owner_n[c] is not None
             and rt.col_owner_p[c] is not None
             and rt.col_owner_n[c] != rt.col_owner_p[c]]
    assert cross, "expected a cross-net dual column (GND|VCC)"
    from smt_engine.route_model import RouteResult
    broken = RouteResult(rt.status_name, rt.col_owner_n, rt.col_owner_p,
                         rt.lo_n, rt.hi_n, rt.lo_p, rt.hi_p, rt.hseg, rt.pj,
                         [True] * rt.width_cols, [True] * rt.width_cols,
                         rt.width_cols, rt.hseg_count, rt.vseg_count,
                         rt.pj_count)
    from smt_engine.verify import verify_cell
    report = verify_cell(nl, sol.devices, broken)
    assert not report.ok()
    assert any("both reach the well boundary" in v for v in report.violations)


def test_poly_jump_legality_checks():
    """Hand-built routes with poly jumps: legal over field crossing a
    same-net gate; violations for over-active, foreign-gate crossing and
    floating (unanchored) runs."""
    from smt_engine.route_model import RouteResult
    nl = CellNetlist(parse_spice_subckt(NAND2))
    sol = solve_layout(nl, time_limit_s=15)
    rt = solve_routing(nl, sol.devices, time_limit_s=25)
    assert rt.ok
    base = (rt.status_name, rt.col_owner_n, rt.col_owner_p, rt.lo_n,
            rt.hi_n, rt.lo_p, rt.hi_p)
    from smt_engine.verify import verify_cell

    def with_pj(pj):
        return RouteResult(*(base + (rt.hseg, pj, rt.reachB_n,
                                     rt.reachB_p, rt.width_cols,
                                     rt.hseg_count, rt.vseg_count,
                                     len(pj))))

    # rail 1 and rail 3 are empty rows in NAND2 (all devices sit in row
    # 0): a poly jump on rail 1 crossing the A gate at column 1 is legal.
    # The same-net M1 segment at (1,0) must go: a layer switch without a
    # gate junction breaks the wire (the E5 rule).
    hseg = dict(rt.hseg)
    if (hseg.get((1, 0)) == "A"):
        del hseg[(1, 0)]
    hseg[(1, 1)] = "A"
    legal = dict(rt.pj)
    legal[(1, 1)] = True
    r = RouteResult(*(base + (hseg, legal, rt.reachB_n, rt.reachB_p,
                              rt.width_cols, len(hseg),
                              rt.vseg_count, 1)))
    report = verify_cell(nl, sol.devices, r)
    assert report.ok(), report.violations
    # over active: rail 0 at columns 1..2 carries MnA's diffusion
    bad1 = with_pj({(0, 1): True})
    bad1.hseg[(0, 1)] = "Y"
    report = verify_cell(nl, sol.devices, bad1)
    assert not report.ok()
    assert any("crosses active" in v for v in report.violations)
    # foreign gate: a Y jump crossing the A gate at column 1
    bad2 = with_pj({(1, 1): True})
    bad2.hseg[(1, 1)] = "Y"
    report = verify_cell(nl, sol.devices, bad2)
    assert not report.ok()
    assert any("foreign gate" in v for v in report.violations)
    # floating run: a poly jump with no same-net gate in its run
    bad3 = with_pj({(1, 2): True})
    bad3.hseg[(1, 2)] = "Y"
    report = verify_cell(nl, sol.devices, bad3)
    assert not report.ok()
    assert any("no gate" in v for v in report.violations)


def test_poly_jump_never_used_by_m1_optimal():
    """NAND2 routes on M1 alone: enabling the poly-jump option must not
    change the optimum (the objective penalises poly), and both models
    produce verify-clean routes."""
    from smt_engine.verify import verify_cell
    nl = CellNetlist(parse_spice_subckt(NAND2))
    sol = solve_layout(nl, time_limit_s=15)
    with_jumps = solve_routing(nl, sol.devices, poly_jumps=True,
                               time_limit_s=25)
    without = solve_routing(nl, sol.devices, poly_jumps=False,
                            time_limit_s=25)
    assert with_jumps.ok and without.ok
    assert with_jumps.pj_count == 0
    assert verify_cell(nl, sol.devices, with_jumps).ok()
    assert verify_cell(nl, sol.devices, without).ok()


PJ_REQUIRED = """\
.subckt T VCC Y Z Q A GND
MnL Y A GND GND NMOS W=0.5u L=0.05u
MpX Q A VCC VCC PMOS W=0.5u L=0.05u
MpR Z A VCC VCC PMOS W=0.5u L=0.05u
.end
"""


def test_poly_jump_required_cell_routes():
    """A gate net (A) whose M1 path is blocked on all four rails (GND and
    VCC stripes both at column 2) can still route: a poly jump leaves the
    N gate at the device edge, crosses the power stripes over field oxide
    (row 0 is empty), and merges with the P gate -- the exact real-world
    poly-jump use.  M1-only is infeasible."""
    from smt_engine.layout_model import PlacedTransistor
    from smt_engine.verify import verify_cell
    nl = CellNetlist(parse_spice_subckt(PJ_REQUIRED))
    byName = {d.name: d for d in nl.devices}
    placement = {
        byName["MnL"]: PlacedTransistor(1, 0, 3, 1),   # row 1, cols 0..3
        byName["MpX"]: PlacedTransistor(0, 0, 1, 3),   # row 0, cols 0..3
        byName["MpR"]: PlacedTransistor(1, 6, 1, 3),   # row 1, cols 6..9
    }
    with_jumps = solve_routing(nl, placement, poly_jumps=True,
                               time_limit_s=25)
    without = solve_routing(nl, placement, poly_jumps=False,
                            time_limit_s=25)
    assert not without.ok            # M1 cannot cross the stripes
    assert with_jumps.ok
    assert with_jumps.pj_count > 0   # the poly jump is actually used
    report = verify_cell(nl, placement, with_jumps)
    assert report.ok(), report.violations
