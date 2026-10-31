"""The astran13 track domain: ASTRAN's own rule-derived 16-track grid.

The domain (smt_engine/gds.py TRACK_DOMAINS) ports ASTRAN's calcArea
trackPos list (autocell2.cpp:83-100) at the production geometry: 16
signal tracks at the 0.13 um rule pitch anchored at the 1.14 central
track, plus the two rail levels -- the vertical vocabulary ASTRAN routed
the 21 unsupported cells on, which the bar9 7-track model provably
cannot express (AUDIT 5.60/5.61's wall).

The capture protocol (flow/_stage3_check's funnel): an EXTRACTED_TABLE
arrangement -> seed placement -> full-vocabulary exact solve
(solve_routing(metal2=True, m2_spans=True, jump_m2=True,
accesses=verify_style_access_points(...), tracks="astran13")) ->
verify_cell(tracks="astran13") -> gds_cells.write_cell_gds ->
layout_sanity.  These pins lock what that protocol honestly yields on
the current tree:

- **CLKBUF1 closes**: OPTIMAL, verify clean, sanity clean, die width
  2.095 um = 1.103x ASTRAN -- the first of the 15 wall cells that
  closes, on ASTRAN's own grid.  The closure is deterministic across
  PYTHONHASHSEED (pinned cross-process, invariant 9).
- **the same arrangement stays bar9-INFEASIBLE** with the identical
  vocabulary: the capture is a DOMAIN effect, not a verify or model
  weakening.
- **max/COMPLEX0 is the known model-vs-verifier gap**: the solve is
  OPTIMAL at die 1.715 um = 1.003x ASTRAN, but verify rejects it with
  exactly "net cl1#Y is not connected" -- and verify is RIGHT.  The
  optimum hangs cl1#Y's P access left of the net's column span
  (hseg(9,2) at column 2, track 9: y 1.365..1.435) while the chain runs
  on tracks 6/7 (y <= 1.175): two metal clusters 0.06 um apart, no
  touch.  The BFS traversal is complete here -- the defect is in
  route_model.build_routing_model's connectivity sweep: track
  transitions are checked for columns [cmin+1, cmax], but the access
  rule lets an access's same-track segment sit at (t, cmin-1), LEFT of
  the sweep, so the track change INTO the first access column joins
  the chain nowhere.  The hole is domain-independent in principle;
  only astran13's tight 16-track grid ever cornered the solver into it
  (the unfixed optimum 469 vs the connected optimum 492 -- every
  unfixed optimum is disconnected).  The domain-scoped fix (extend the
  transition sweep to cmin for non-bar9 domains) is validated in
  scratch (flow/_stage3_check/_smt_patched + _astran13_fixprobe.py +
  _astran13_funnel_postfix.py): post-fix max/COMPLEX0 closes clean at
  the same width (1.715 um, cl1#Y re-routed through the shared
  boundary-track-8 corridor, ASTRAN's own style), CLKBUF1 is unchanged,
  the other 13 cells stay INFEASIBLE and bar9 stays byte-identical.
  The live-solve pin below FLIPS when that fix lands in
  smt_engine/route_model.py; the fixture pin (the dumped route) must
  keep failing forever -- that route is disconnected metal.
"""
import os
import subprocess
import sys

import pytest

from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from smt_engine.route_model import (RouteResult, solve_routing,
                                    verify_style_access_points)
from smt_engine.verify import verify_cell
from bigcell_engine.gds_cells import write_cell_gds
from bigcell_engine.geometry import layout_cell, width_um
from bigcell_engine.gds_seeds import (EXTRACTED_TABLE, seed_orderings,
                                      seed_geometry)

LIB_DECK = os.path.join("..", "std_celllib", "cellsAstranFriendly.sp")

CLKBUF1 = ("CLKBUF1", "8cf4a81927d7")
MAX_COMPLEX0 = ("COMPLEX0", "e6b547710f5e")


def _load_cell(entry_source, flow_dir):
    """The CellNetlist an EXTRACTED_TABLE entry speaks (test_gds_seeds'
    loader: mined cells carry their own .sp, library cells the shared
    deck)."""
    if entry_source.startswith("outputs/"):
        return CellNetlist(parse_spice_subckt(
            open(os.path.join(flow_dir, entry_source[:-4] + ".sp"),
                 errors="ignore").read()))
    import re
    name = os.path.basename(entry_source)[:-4]
    text = open(os.path.join(flow_dir, LIB_DECK),
                errors="ignore").read()
    blk = re.split(r"\.subckt\s+%s\b" % name, text)[1].split(".ends")[0]
    return CellNetlist(parse_spice_subckt(
        ".subckt %s x\n%s.ends" % (name, blk)))


def _seed_setup(key, flow_dir):
    """(netlist, placement, width, blocks view, orderings, leg widths,
    offsets) of one table entry's arrangement through the seed
    projection (AUDIT 5.61's measured region widths + row offsets)."""
    entry = EXTRACTED_TABLE[key]
    nl = _load_cell(entry["source"], flow_dir)
    ordering_p, ordering_n = seed_orderings(nl, entry)
    leg_widths, offsets = seed_geometry(entry, None)
    placements, width = layout_cell(ordering_p, ordering_n, leg_widths,
                                    x_offsets=offsets)
    blocks = list(ordering_p) + list(ordering_n)
    return (nl, placements, width, blocks, entry, ordering_p, ordering_n,
            leg_widths, offsets)


def _capture_solve(nl, placements, width, blocks, tracks="astran13"):
    """The funnel protocol's exact solve (full vocabulary, verify-style
    accesses, route grid = placement W + 1 escape lane)."""
    accesses = verify_style_access_points(nl, placements, blocks)
    return solve_routing(nl, placements, width_cols=width + 1, metal2=True,
                         time_limit_s=120.0, m2_spans=True, jump_m2=True,
                         accesses=accesses, tracks=tracks)


# --------------------------------------------------------------------------
# the domain record itself
# --------------------------------------------------------------------------

def test_astran13_domain_record():
    from smt_engine.gds import track_domain
    dom = track_domain("astran13")
    assert dom.n_tracks == 16 and dom.bar_levels == 18
    assert dom.boundary_t == 8                       # the 1.27 um track
    assert dom.trackY[7] == pytest.approx(1.14)      # ASTRAN's central
    assert dom.trackY[8] == pytest.approx(1.27)      # the shared merge
    assert dom.trackY[15] == pytest.approx(2.18)
    assert dom.row_track == {0: 3, 1: 6, 2: 9, 3: 12}
    # the terminal bands: N rail 1 -> 1.01, P rail 2 -> 1.40
    assert dom.trackY[dom.row_track[1]] == pytest.approx(1.01)
    assert dom.trackY[dom.row_track[2]] == pytest.approx(1.40)
    assert dom.strip_anchored                     # slot-model strips
    assert sorted(dom.row_of_track) == list(range(16))
    # bar9's record is untouched by the domain plumbing
    bar9 = track_domain("bar9")
    assert (bar9.n_tracks, bar9.bar_levels, bar9.boundary_t) == (7, 9, 3)
    assert bar9.row_track == {0: 0, 1: 2, 2: 4, 3: 6}
    assert bar9.row_tracks == (0, 2, 4, 6)


# --------------------------------------------------------------------------
# the CLKBUF1 closure (the capture that exists today)
# --------------------------------------------------------------------------

def test_clkbuf1_closes_on_astran13(flow_dir, tmp_path):
    (nl, placements, width, blocks, entry,
     ordering_p, ordering_n, leg_widths, offsets) = \
        _seed_setup(CLKBUF1, flow_dir)
    route = _capture_solve(nl, placements, width, blocks)
    assert route.status_name == "OPTIMAL"
    assert route.width_cols == width + 1
    report = verify_cell(nl, placements, route, blocks=blocks,
                         tracks="astran13")
    assert report.ok(), report.violations
    gds = str(tmp_path / "clkbuf1_astran13.gds")
    write_cell_gds(gds, nl, placements, width, ordering_p, ordering_n,
                   leg_widths, route=route, x_offsets=offsets,
                   tracks="astran13")
    from layout_sanity import check_layout
    sanity = check_layout(gds, units_per_um=1.0)
    assert sanity.ok(), sanity.violations
    die = width_um(width)
    assert die == pytest.approx(2.095)
    assert die / entry["astran_um"] == pytest.approx(1.103, abs=0.001)


def test_clkbuf1_seed_arrangement_stays_bar9_infeasible(flow_dir):
    """The 5.60/5.61 wall is untouched: the SAME arrangement, SAME
    vocabulary, bar9 domain -> INFEASIBLE.  The astran13 closure is a
    track-domain effect, not a weakened model or verifier."""
    nl, placements, width, blocks, _e, _op, _on, _lw, _of = \
        _seed_setup(CLKBUF1, flow_dir)
    route = _capture_solve(nl, placements, width, blocks, tracks="bar9")
    assert route.status_name == "INFEASIBLE"


# --------------------------------------------------------------------------
# the max/COMPLEX0 known model-vs-verifier gap
# --------------------------------------------------------------------------

def test_max_complex0_closes_on_astran13(flow_dir):
    """THE SECOND CAPTURE, post model-fix: the transition-into-cmin sweep
    hole in route_model.build_routing_model is closed (the unfixed
    optimum was always the disconnected left-hang, pricing BELOW every
    connected route, 469 < 492) -- max/COMPLEX0 now solves OPTIMAL and
    verifies CLEAN at die 1.715 um = 1.003x ASTRAN (1.71), nearly
    ASTRAN-equal width."""
    nl, placements, width, blocks, _e, _op, _on, _lw, _of = \
        _seed_setup(MAX_COMPLEX0, flow_dir)
    route = _capture_solve(nl, placements, width, blocks)
    assert route.status_name == "OPTIMAL"
    assert route.width_cols == width + 1
    report = verify_cell(nl, placements, route, blocks=blocks,
                         tracks="astran13")
    assert report.ok(), report.violations[:3]
    # the re-routed cl1#Y runs on the shared boundary track -- ASTRAN's
    # own corridor style (the disconnected left-hang is gone)
    assert route.hseg_count == 16 and route.vseg_count == 11


def test_verify_rejects_the_left_hang_optimum_by_geometry(flow_dir):
    """Solver-independent BFS pin: the EXACT route the unfixed model
    emits for max/COMPLEX0 (dumped from the deterministic single-worker
    solve) fails verify's exact BFS with exactly the cl1#Y
    disconnection -- no solver in the loop.  cl1#Y's P access hangs left
    (hseg(9,2), track 9) while the chain runs tracks 6/7; nothing joins
    the clusters.  This must STILL fail after the model fix: the route
    itself is disconnected metal, whatever the model believed."""
    nl, placements, width, blocks, _e, _op, _on, _lw, _of = \
        _seed_setup(MAX_COMPLEX0, flow_dir)
    n, p, q = "cl1#a_2_10#", "cl1#Y", "cl0#Y"
    route = RouteResult(
        "OPTIMAL",
        [n, "GND", None, None, p, p, "GND", q],           # col_owner_n
        [n, "VCC", None, p, None, None, "VCC", q],        # col_owner_p
        [1, 0, 0, 0, 7, 7, 0, 1],                         # lo_n
        [8, 7, 0, 0, 7, 8, 7, 7],                         # hi_n
        [10, 10, 10, 9, 10, 10, 10, 9],                   # lo_p
        [16, 17, 10, 10, 10, 10, 17, 16],                 # hi_p
        {(5, 3): "cl1#S", (5, 4): "cl1#S",
         (6, 3): p, (6, 4): p,
         (7, 0): n, (7, 1): n, (7, 2): n, (7, 3): n,
         (7, 5): p, (7, 6): p,
         (8, 0): "cl1#S", (8, 1): "cl1#B", (8, 5): "cl1#A",
         (9, 2): p, (9, 4): n,
         (10, 1): "cl1#S", (10, 2): "cl1#S"},
        {(8, 1): True},                                   # poly jumps
        {(10, 1): True},                                  # M2 segments
        {(10, 2): True},                                  # M1<->M2 vias
        [False] * 8,                                      # reachB_n
        [False, False, False, True, False, False, False, True],  # reachB_p
        8, 17, 11, 1, 1, 1,
        m2v={(0, 7, 9): n, (1, 8, 10): "cl1#S", (3, 5, 10): "cl1#S",
             (4, 7, 9): n, (7, 6, 8): q},
        m2via={(5, 3): True, (6, 7): True, (7, 0): True, (7, 4): True,
               (8, 1): True, (8, 7): True, (9, 0): True, (9, 4): True,
               (10, 3): True})
    report = verify_cell(nl, placements, route, blocks=blocks,
                         tracks="astran13")
    assert report.violations == ["net cl1#Y is not connected"]


# --------------------------------------------------------------------------
# the MUX2X1 closure: the FIRST ROUTER-BASED capture (AUDIT 5.69)
# --------------------------------------------------------------------------

MUX2X1 = ("MUX2X1", "6028a7b039e2")


def test_mux2x1_closes_on_the_ported_router(flow_dir, tmp_path):
    """THE THIRD CAPTURE, and the first that is the ROUTER's, not the
    solver's.  The exact model stays INFEASIBLE on this arrangement (the
    multi-interval half-column vocabulary is beyond the SMT encoding;
    the ported ASTRAN router walks it natively -- GraphRouter has no
    stripe concept at all, graphrouter.h:33-44).  The closure rides
    route_cell_ported phase 2 end to end, and its two vocabulary pieces
    -- the S gate-5 half-slot stub (the C++'s centre-anchored contact,
    which the full-slot form would short) and the node vias onto the
    col-6 bars -- are exactly what the round-565df1e..b04afae chain
    built them for."""
    (nl, placements, width, blocks, entry,
     ordering_p, ordering_n, leg_widths, offsets) = \
        _seed_setup(MUX2X1, flow_dir)
    from bigcell_engine.router_port import route_cell_ported
    route = route_cell_ported(nl, placements, width, blocks=blocks,
                              tracks="astran13")
    assert route.ok, route.fail_note
    assert route.router_phase == 2
    # the half-slot stubs: (8, 5) carries S's gate-5 contact at the M1
    # run's end; (9, 1) is the C++'s own contact on S@1's stripe (the
    # M2 escape it fed was dead geometry, but the contact is real --
    # the via-anchored form draws it now instead of dropping it)
    assert sorted(k for k, v in route.gate_stub.items() if v) == \
        [(8, 5), (9, 1)]
    assert route.hseg.get((8, 4)) == "S"      # the (8, 5) stub's anchor
    # the a_2_10# wire drops onto its own col-6 bars through two node
    # vias -- one at the M2 wire's end, one at the bar the C++ landed
    # on inside the diffusion strip (the widened coverage)
    assert (4, 6) in route.m2via and (12, 6) in route.m2via
    report = verify_cell(nl, placements, route, blocks=blocks,
                         tracks="astran13")
    assert report.ok(), report.violations
    gds = str(tmp_path / "mux2x1_astran13.gds")
    write_cell_gds(gds, nl, placements, width, ordering_p, ordering_n,
                   leg_widths, route=route, x_offsets=offsets,
                   tracks="astran13")
    from layout_sanity import check_layout
    sanity = check_layout(gds, units_per_um=1.0)
    assert sanity.ok(), sanity.violations
    die = width_um(width)
    assert die == pytest.approx(1.525, abs=0.001)
    assert die / entry["astran_um"] == pytest.approx(1.147, abs=0.001)


def test_mux2x1_seed_arrangement_stays_exact_infeasible(flow_dir):
    """The honest boundary: the SAME arrangement through the EXACT model
    (the closure funnel's own solve, full vocabulary, astran13 domain)
    stays INFEASIBLE -- the closure is the ported router's, and this pin
    keeps the solver from silently growing the vocabulary the router
    owns."""
    (nl, placements, width, blocks, _e, _op, _on, _lw, _of) = \
        _seed_setup(MUX2X1, flow_dir)
    route = _capture_solve(nl, placements, width, blocks)
    assert route.status_name == "INFEASIBLE"


def test_mux2x1_closes_through_the_production_ladder(flow_dir):
    """The table entry reproduces through synth_cell: the seed wins the
    pool -- its trial runs the PORTED router on its own domain (the bar9
    grid router would misprice the capture at 42 conflicts and the pool
    would drop it, AUDIT 5.69) -- and rung 3 closes it verify-clean on
    ASTRAN's own arrangement."""
    from bigcell_engine.engine import synth_cell
    nl = _load_cell(EXTRACTED_TABLE[MUX2X1]["source"], flow_dir)
    placement, route, meta = synth_cell(nl, exact_budget_s=20.0)
    assert meta["engine"] == "bigcell-full"
    assert meta["slot_emit"]["tracks"] == "astran13"
    assert route.ok and route.router_phase == 2
    report = verify_cell(nl, placement, route, blocks=meta["blocks"],
                         tracks="astran13")
    assert report.ok(), report.violations


# --------------------------------------------------------------------------
# the COMPLEX11 closure: the second router-based capture (AUDIT 5.70)
# --------------------------------------------------------------------------

COMPLEX11 = ("COMPLEX11", "419776c896b9")


def test_complex11_closes_on_the_ported_router(flow_dir, tmp_path):
    """THE FOURTH CAPTURE, the second router-owned one, and the biggest
    cell the ported router has closed (32T, die 3.995 um = 1.051x
    ASTRAN).  The three vocabulary pieces the MUX2X1 round built carry
    its hard nets: the via-anchored gate stubs (cl0#Y's G13 contact
    lands on a bare M1 point that climbs straight into its M2 chain),
    the +1-slot via retry (cl3#a_12_41#'s contact stub displaced the
    M2 wire's slot, the via lands on the run's end node), and the
    over-foreign-slot extra_m2 segments (both M2 bridges cross foreign
    M1 slots -- layers coexist, the C++ nodes did exactly that)."""
    (nl, placements, width, blocks, entry,
     ordering_p, ordering_n, leg_widths, offsets) = \
        _seed_setup(COMPLEX11, flow_dir)
    from bigcell_engine.router_port import route_cell_ported
    route = route_cell_ported(nl, placements, width, blocks=blocks,
                              tracks="astran13")
    assert route.ok, route.fail_note
    assert route.router_phase == 2
    # the load-bearing vocabulary pieces (AUDIT 5.70's three forms)
    stubs = sorted(k for k, v in route.gate_stub.items() if v)
    assert (4, 13) in stubs and (9, 15) in stubs and (10, 13) in stubs
    assert route.hseg.get((4, 14)) is not None      # M1 near the stub
    extras = sorted((t, c) for (t, c, _n) in route.extra_m2)
    assert (6, 16) in extras and (7, 4) in extras
    report = verify_cell(nl, placements, route, blocks=blocks,
                         tracks="astran13")
    assert report.ok(), report.violations
    gds = str(tmp_path / "complex11_astran13.gds")
    write_cell_gds(gds, nl, placements, width, ordering_p, ordering_n,
                   leg_widths, route=route, x_offsets=offsets,
                   tracks="astran13")
    from layout_sanity import check_layout
    sanity = check_layout(gds, units_per_um=1.0)
    assert sanity.ok(), sanity.violations
    die = width_um(width)
    assert die == pytest.approx(3.995, abs=0.001)
    assert die / entry["astran_um"] == pytest.approx(1.051, abs=0.001)


def test_complex11_seed_arrangement_stays_exact_infeasible(flow_dir):
    """The honest boundary: 32T through the EXACT model (the closure
    funnel's own solve, full vocabulary, astran13 domain) stays
    INFEASIBLE (~47 s CP-SAT proof) -- the over-slot M2 coexistence is
    beyond the SMT encoding's single-occupancy hseg, and the ported
    router's GraphRouter has no such rule (graphrouter.h:33-44)."""
    (nl, placements, width, blocks, _e, _op, _on, _lw, _of) = \
        _seed_setup(COMPLEX11, flow_dir)
    route = _capture_solve(nl, placements, width, blocks)
    assert route.status_name == "INFEASIBLE"


def test_complex11_closes_through_the_production_ladder(flow_dir):
    """The table entry reproduces through synth_cell: the seed wins the
    pool (its trial runs the ported router on astran13) and rung 3
    closes the 32T cell verify-clean at width 19 columns."""
    from bigcell_engine.engine import synth_cell
    nl = _load_cell(EXTRACTED_TABLE[COMPLEX11]["source"], flow_dir)
    placement, route, meta = synth_cell(nl, exact_budget_s=20.0)
    assert meta["engine"] == "bigcell-full"
    assert meta["slot_emit"]["tracks"] == "astran13"
    assert meta["width_cols"] == 19
    assert route.ok and route.router_phase == 2
    report = verify_cell(nl, placement, route, blocks=meta["blocks"],
                         tracks="astran13")
    assert report.ok(), report.violations


# --------------------------------------------------------------------------
# determinism (invariant 9): the closure is hash-seed independent
# --------------------------------------------------------------------------

_DETERMINISM_HELPER = r'''
import hashlib, os, sys, tempfile
sys.path.insert(0, os.getcwd())
from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from smt_engine.route_model import (solve_routing,
                                    verify_style_access_points)
from bigcell_engine.gds_seeds import (EXTRACTED_TABLE, seed_orderings,
                                      seed_geometry)
from bigcell_engine.geometry import layout_cell
from bigcell_engine.gds_cells import write_cell_gds

entry = EXTRACTED_TABLE[("CLKBUF1", "8cf4a81927d7")]
text = open(os.path.join("..", "std_celllib", "cellsAstranFriendly.sp"),
            errors="ignore").read()
import re
blk = re.split(r"\.subckt\s+CLKBUF1\b", text)[1].split(".ends")[0]
nl = CellNetlist(parse_spice_subckt(
    ".subckt CLKBUF1 x\n%s.ends" % blk))
op, on = seed_orderings(nl, entry)
lws, offs = seed_geometry(entry, None)
placements, w = layout_cell(op, on, lws, x_offsets=offs)
blocks = list(op) + list(on)
acc = verify_style_access_points(nl, placements, blocks)
route = solve_routing(nl, placements, width_cols=w + 1, metal2=True,
                      time_limit_s=120.0, m2_spans=True, jump_m2=True,
                      accesses=acc, tracks="astran13")
assert route.status_name == "OPTIMAL", route.status_name
out = tempfile.mktemp(suffix=".gds")
write_cell_gds(out, nl, placements, w, op, on, lws, route=route,
               x_offsets=offs, tracks="astran13")
print(hashlib.md5(open(out, "rb").read()).hexdigest())
os.unlink(out)
'''


def test_astran13_closure_is_hash_seed_independent(flow_dir, tmp_path):
    """The captured cell's GDS is byte-identical across PYTHONHASHSEED
    (the exported closure is a pure function of the table entry)."""
    helper = tmp_path / "astran13_hash_helper.py"
    helper.write_text(_DETERMINISM_HELPER)
    digests = set()
    for seed in (0, 1):
        env = dict(os.environ, PYTHONHASHSEED=str(seed))
        proc = subprocess.run([sys.executable, str(helper)], cwd=flow_dir,
                              env=env, capture_output=True, text=True,
                              check=True)
        digests.add(proc.stdout.strip().splitlines()[-1])
    assert len(digests) == 1, digests
