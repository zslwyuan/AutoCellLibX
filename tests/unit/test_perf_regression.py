"""Performance-regression pins for the 2026-10 route_grid tuning round
(negotiation-loop cost cuts with byte-identical routes).

The tuning round optimized bigcell_engine/route_grid's negotiated-
congestion solver on the measured hotspots only -- no semantic change
anywhere:

- the per-attempt vocabulary pass (_post_pass) walks the nets' TREES
  (collected + sorted into the exact enumeration order the full-grid
  scans used) instead of scanning every (track, column) of the grid per
  net per rule;
- _complete_junctions' foreign-tree membership test is served from a
  reverse tree-membership index maintained at every tree mutation,
  replacing a full scan of every other net's tree per net per attempt;
- the A* relaxation loop (_bfs_route) runs on precomputed neighbour
  tuples with the GraphRouter cost rule inlined and the static _allow
  filter precomputed per net; the heap discipline (seed heapify, then
  append + heappop -- NOT a min-first queue) is preserved exactly,
  because the whole solver's byte-identity rides on its precise pop
  sequence (verified: heappush-style pushes change the routes);
- structural_diagnosis computes each banned-cage cut test once per
  (terminal, corridor node) instead of once per terminal PAIR.

These pins hold the line on both fronts:

- **outcome**: the NAND6 negotiation (the 12-transistor exact-engine
  closer, 66 attempts of real rip-up/reroute traffic) must keep its
  exact route signature -- byte-identical routing, invariant 9;
- **cost**: the same route must stay inside a wall-time budget generous
  enough for CI variance (~4x the measured 0.14-0.18s on the dev
  machine) but far below the pre-tuning cost (~0.4-0.6s measured with
  the HEAD router on the same cell): a reintroduced per-attempt grid
  scan or all-trees rescan pushes a route of this shape well past it.

The signature digest is pinned as sha256(route_signature(route)) --
route_signature is the canonical serialization the determinism tests
use, so the pin is exactly the established byte-identity contract.
"""
import hashlib
import time

from bigcell_engine.route_grid import route_cell, route_signature
from smt_engine.layout_model import solve_layout
from smt_engine.netlist import CellNetlist
from smt_engine.verify import verify_cell
from smt_cell_placer import parse_spice_subckt

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

#: sha256(route_signature(route))[:16] for the pinned NAND6 route (the
#: 2026-10-27 tuned router AND the HEAD router produce this -- the
#: tuning is byte-identical by construction; this pin holds it there)
NAND6_SIG_SHA = "31c874e04bc2d8d5"
#: negotiation attempts the pinned route takes (the router's own
#: attempts_used -- a different negotiation length means different
#: dynamics, i.e. a behavioural change)
NAND6_ATTEMPTS = 66
#: wall-time budget for the pinned route (seconds).  Measured 0.14-0.18
#: on the dev machine (2026-10-27, tuned router); ~0.4-0.6 with the
#: pre-tuning router.  0.75 is ~4x the tuned measurement (CI variance
#: headroom) while a reintroduced per-attempt full-grid scan or
#: all-trees rescan blows well past it.
NAND6_ROUTE_BUDGET_S = 0.75


def _nand6_placed():
    nl = CellNetlist(parse_spice_subckt(NAND6))
    lay = solve_layout(nl, time_limit_s=15.0)
    assert lay.status_name == "OPTIMAL", lay.status_name
    leg_widths = {d.name: (p.legs, p.leg_width_cols)
                  for d, p in lay.devices.items()}
    return nl, lay.devices, lay.width_cols, leg_widths


def test_nand6_negotiation_route_signature_pin():
    """The tuned router's NAND6 route is byte-identical: exact signature
    digest, exact negotiation length, verify clean."""
    nl, placement, width, leg_widths = _nand6_placed()
    route = route_cell(nl, placement, width, leg_widths)
    assert route.ok, route.fail_note
    assert route.attempts_used == NAND6_ATTEMPTS, route.attempts_used
    sig = route_signature(route)
    digest = hashlib.sha256(sig.encode()).hexdigest()[:16]
    assert digest == NAND6_SIG_SHA, (digest, sig[:400])
    rep = verify_cell(nl, placement, route)
    assert rep.ok(), rep.violations


def test_nand6_negotiation_route_wall_budget():
    """The same route stays inside the wall-time budget (a performance
    regression guard: the byte-identity pin above proves the route is
    unchanged, this one proves the negotiation still runs at the tuned
    cost)."""
    nl, placement, width, leg_widths = _nand6_placed()
    t0 = time.perf_counter()
    route = route_cell(nl, placement, width, leg_widths)
    elapsed = time.perf_counter() - t0
    assert route.ok, route.fail_note
    assert elapsed <= NAND6_ROUTE_BUDGET_S, (
        "NAND6 route took %.2fs > %.2fs budget (tuned router measured "
        "0.14-0.18s, pre-tuning ~0.4-0.6s) -- the negotiation loop "
        "regressed" % (elapsed, NAND6_ROUTE_BUDGET_S))
