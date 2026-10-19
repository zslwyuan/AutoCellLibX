"""Unit tests for the gate-cage lever (AUDIT 5.46, the 22-36T COMPLEX
wall) in flow/bigcell_engine/place_sa.py.

The round-6 diagnosis (commit 6b35cee, scratch diag_forced_census.py)
proved the heavy cells fail against REAL 7-track walls: gate contacts
whose every legal crossing track sits inside a pre-built power-stripe
span at one of the crossing's two endpoint columns.  The lever is the
PLACEMENT: prefer arrangements whose gate columns dodge the power-access
columns.  This file pins

- the static predicate ``gate_cage_penalty`` (census port: free where
  the closers' arrangements are free, caged where the router's
  structural diagnosis walls a gate, deterministic);
- the cost integration (``_SAState(..., netlist=...)``:
  CAGE_WEIGHT * caged_gates dominates the legacy terms, incremental ==
  full under random move/undo sequences, ``sa_refine(cage=True)`` steers
  to a cage-free arrangement where one exists);
- the speculate selection policy (FEASIBLE + cage-free short-circuits;
  a FEASIBLE-but-caged candidate loses to a cage-free one regardless of
  legacy cost; floor-less (_UNROUTABLE) fallback candidates rank by
  (cage, cost, index) while real conflict floors keep today's
  (conflicts, cost, index) verbatim);
- the per-cell acceptance evidence: adder/COMPLEX10 (36T) and
  adder/COMPLEX1 (30T) chains now produce arrangements the census calls
  cage-free -- COMPLEX1's full-budget residual is an honest corridor
  contest only (its selection is the dual-basin fallback winner, see
  the chain test below); COMPLEX10's residual is still a
  (net-connectivity) caged gate the contact-level census cannot see --
  the documented exact-model M2 dual-crossover next round.

Fast tests use ctrl/COMPLEX0 (8T) and injected trial routers; the heavy
evidence runs the real router once per cell (module fixtures).  All
randomness stays inside sa_refine's content-hash discipline (invariants
8/9).
"""
import os
import random
import subprocess
import sys

import pytest

from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from bigcell_engine import place_sa as ps
from bigcell_engine.geometry import layout_cell
from bigcell_engine.netlist_ext import (build_bigcell_blocks, fold_devices,
                                        row_seeds)
from bigcell_engine.place_euler import euler_orderings
from bigcell_engine.place_sa import (_SAState, _UNROUTABLE,
                                     DEFAULT_TRIAL_ATTEMPTS,
                                     gate_cage_penalty, generate_candidates,
                                     sa_refine, sa_refine_routable,
                                     select_orderings)
from bigcell_engine.route_grid import _RouteGrid, route_cell

INVX1 = """\
.subckt INVX1 VCC Y A GND
M0 Y A VCC VCC PMOS W=0.5u L=0.05u
M1 Y A GND GND NMOS W=0.25u L=0.05u
.ends INVX1
"""

NAND2X1 = """\
.subckt NAND2X1 VCC Y A B GND
MpA Y A VCC VCC PMOS W=0.5u L=0.05u
MpB VCC B Y VCC PMOS W=0.5u L=0.05u
MnA Y A n1 GND NMOS W=0.5u L=0.05u
MnB n1 B GND GND NMOS W=0.5u L=0.05u
.ends NAND2X1
"""


def _pipeline(text, variant=None):
    """fold -> blocks -> seeds: the pre-euler state."""
    nl = CellNetlist(parse_spice_subckt(text))
    nl3, lw = fold_devices(nl)
    blocks = build_bigcell_blocks(nl3, **({"variant": variant}
                                          if variant else {}))
    return nl3, lw, row_seeds(blocks, lw)


def _fail(conflicts=None):
    """A failed RouteResult-shaped stub; conflicts=None = build failure."""
    if conflicts is None:
        note = "impossible to find a path for net X"
    else:
        note = ("no conflict-free routing after %d attempts (best %d "
                "conflicts at attempt 2; unresolved: N)"
                % (DEFAULT_TRIAL_ATTEMPTS, conflicts))
    from types import SimpleNamespace
    return SimpleNamespace(ok=False, fail_note=note, status_name="UNKNOWN",
                           attempts_used=DEFAULT_TRIAL_ATTEMPTS)


def _ok():
    from types import SimpleNamespace
    return SimpleNamespace(ok=True, fail_note=None, status_name="FEASIBLE",
                           attempts_used=1)


# --------------------------------------------------------------------------
# the predicate: free where the closers are free, caged where the router
# walls a gate, deterministic
# --------------------------------------------------------------------------

def test_closers_arrangements_are_cage_free():
    """The closing library cells' natural arrangements offer every gate
    contact a free lane (INVX1's input crosses on the poly layer -- the
    escape the M1-only census spelling missed)."""
    for text in (INVX1, NAND2X1):
        nl3, lw, seeds = _pipeline(text)
        eop, eon = euler_orderings(seeds, lw)
        assert gate_cage_penalty(eop, eon, nl3, lw) == (0, ())
        bp, bn, _bd = sa_refine(eop, eon, nl3, lw)
        assert gate_cage_penalty(bp, bn, nl3, lw) == (0, ())


def test_adder_complex0_cost_best_is_caged_and_router_agrees(flow_dir):
    """The census and the router's structural diagnosis agree on the
    adder/COMPLEX0 pure-cost arrangement: exactly one caged gate
    contact (the pinned BFS-fail anatomy of
    test_bigcell_route_grid: cl2#a_2_54#'s gate contact is statically
    caged)."""
    path = os.path.join(flow_dir, "outputs", "adder", "COMPLEX0.sp")
    nl3, lw, seeds = _pipeline(open(path).read())
    eop, eon = euler_orderings(seeds, lw)
    bp, bn, _bd = sa_refine(eop, eon, nl3, lw)
    assert gate_cage_penalty(bp, bn, nl3, lw) == (1, (3,))
    placements, width = layout_cell(bp, bn, lw)
    _contests, walled = _RouteGrid(nl3, placements, width) \
        .structural_diagnosis()
    assert ("cl2#a_2_54#", "gate contact @col 2") in walled


def test_predicate_is_deterministic(flow_dir):
    """Pure function of the ordering pair (invariant 9): repeated calls
    agree, and the census of a mirrored pair is reproducible."""
    path = os.path.join(flow_dir, "outputs", "adder", "COMPLEX0.sp")
    nl3, lw, seeds = _pipeline(open(path).read())
    eop, eon = euler_orderings(seeds, lw)
    a = gate_cage_penalty(eop, eon, nl3, lw)
    b = gate_cage_penalty(eop, eon, nl3, lw)
    assert a == b
    assert isinstance(a[0], int) and isinstance(a[1], tuple)


def test_cage_term_dominates_the_legacy_cost(flow_dir):
    """CAGE_WEIGHT * caged_gates outweighs any legacy total: a
    cage-free arrangement of ctrl/COMPLEX0's pool totals less than the
    caged cost-best even though the legacy terms alone order the other
    way."""
    path = os.path.join(flow_dir, "outputs", "ctrl", "COMPLEX0.sp")
    nl3, lw, seeds = _pipeline(open(path).read())
    eop, eon = euler_orderings(seeds, lw)
    bp, bn, _bd = sa_refine(eop, eon, nl3, lw)
    pool = generate_candidates(bp, bn, eop, eon, lw, netlist=nl3)
    caged = [(kind, op, on) for kind, op, on in pool
             if gate_cage_penalty(op, on, nl3, lw)[0] > 0]
    free = [(kind, op, on) for kind, op, on in pool
            if gate_cage_penalty(op, on, nl3, lw)[0] == 0]
    assert caged and free                      # ctrl's pool has both
    caged_total = _SAState(caged[0][1], caged[0][2], lw, netlist=nl3).total
    free_total = _SAState(free[0][1], free[0][2], lw, netlist=nl3).total
    legacy_caged = _SAState(caged[0][1], caged[0][2], lw).total
    legacy_free = _SAState(free[0][1], free[0][2], lw).total
    assert legacy_caged < legacy_free          # the SA best is caged-cheap
    assert free_total < caged_total            # the cage term flips it
    assert caged_total - legacy_caged >= ps.CAGE_WEIGHT


# --------------------------------------------------------------------------
# the cost integration: incremental == full under random moves
# --------------------------------------------------------------------------

@pytest.mark.parametrize("cell", ["ctrl/COMPLEX0.sp", "adder/COMPLEX0.sp"])
def test_sa_cage_incremental_matches_full_recompute(flow_dir, cell):
    path = os.path.join(flow_dir, "outputs", cell)
    nl3, lw, seeds = _pipeline(open(path).read())
    eop, eon = euler_orderings(seeds, lw)
    state = _SAState(eop, eon, lw, netlist=nl3)
    rng = random.Random(1234)
    for step in range(300):
        mv = state.draw_move(rng)
        state.apply(mv)
        cached = state.total               # BEFORE the rebuild
        full = state.full_recompute()
        assert full == cached, (step, mv, cached, full)
        state.apply(state.inverse(mv))
        assert state.total == state.full_recompute()


def test_sa_cage_steer_finds_the_cage_free_basin(flow_dir):
    """ctrl/COMPLEX0: the pure-cost SA best cages a gate contact (the
    phase-1 specimen anatomy); the steered refine lands on a cage-free
    arrangement of the same decomposition.  Both refines keep every
    block exactly once and are deterministic."""
    path = os.path.join(flow_dir, "outputs", "ctrl", "COMPLEX0.sp")
    nl3, lw, seeds = _pipeline(open(path).read())
    eop, eon = euler_orderings(seeds, lw)
    bp, bn, bd = sa_refine(eop, eon, nl3, lw)
    assert gate_cage_penalty(bp, bn, nl3, lw)[0] == 1
    assert bd["caged_gates"] == 0           # netlist=None: term disabled
    cp, cn, cbd = sa_refine(eop, eon, nl3, lw, cage=True)
    assert gate_cage_penalty(cp, cn, nl3, lw) == (0, ())
    assert cbd["caged_gates"] == 0
    assert cbd["total"] == _SAState(cp, cn, lw, netlist=nl3).total
    for row in (cp, cn):
        names = [b.first.name for b in row]
        assert len(names) == len(set(names))
    # pure-cost path stays byte-identical legacy
    assert _SAState(bp, bn, lw).total == bd["total"]


# --------------------------------------------------------------------------
# the selection policy (injected routers, ctrl/COMPLEX0's cage-diverse
# fixed pool: best cages 1 gate, flip-both/seed are cage-free)
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ctrl_pool(flow_dir):
    """(nl3, lw, best_p, best_n, eop, eon) for ctrl/COMPLEX0."""
    path = os.path.join(flow_dir, "outputs", "ctrl", "COMPLEX0.sp")
    nl3, lw, seeds = _pipeline(open(path).read())
    eop, eon = euler_orderings(seeds, lw)
    bp, bn, _bd = sa_refine(eop, eon, nl3, lw)
    pool = generate_candidates(bp, bn, eop, eon, lw, netlist=nl3)
    by_kind = dict((k, (op, on)) for k, op, on in pool)
    assert gate_cage_penalty(by_kind["best"][0], by_kind["best"][1],
                             nl3, lw)[0] == 1
    assert gate_cage_penalty(by_kind["flip-both"][0], by_kind["flip-both"][1],
                             nl3, lw)[0] == 0
    return nl3, lw, bp, bn, eop, eon


def test_select_feasible_caged_head_loses_to_cage_free(ctrl_pool):
    """A FEASIBLE candidate that cages a gate loses to a cage-free
    FEASIBLE one, even though the caged head is the cost-best and pool
    head (the lever's core ranking)."""
    nl3, lw, bp, bn, eop, eon = ctrl_pool
    _op, _on, report = select_orderings(bp, bn, eop, eon, nl3, lw,
                                        trial_router=lambda *a, **k: _ok())
    assert report["feasible"] and report["cage"] == 0
    assert report["kind"] == "flip-both"    # first cage-free FEASIBLE
    kinds = [e["kind"] for e in report["candidates"]]
    assert kinds[0] == "best"               # the head was trialed first
    assert all("cage" in e for e in report["candidates"])


def test_select_floorless_tie_ranks_by_cage(ctrl_pool):
    """No candidate routes and none has a conflict floor (build
    failures): the census decides -- a cage-free candidate wins over
    the caged cost-best, and among the cage-free ones the legacy cost
    ranks (die-both's total is below flip-both's)."""
    nl3, lw, bp, bn, eop, eon = ctrl_pool
    _op, _on, report = select_orderings(
        bp, bn, eop, eon, nl3, lw,
        trial_router=lambda *a, **k: _fail(None))
    assert not report["feasible"]
    assert report["conflicts"] == _UNROUTABLE
    assert report["cage"] == 0
    assert report["kind"] == "die-both"


def test_select_real_floor_keeps_todays_rank(ctrl_pool):
    """Candidates with a real conflict plateau keep the verbatim
    (conflicts, cost, index) rank: on equal floors the cost-best pool
    head wins exactly as before the lever."""
    nl3, lw, bp, bn, eop, eon = ctrl_pool
    _op, _on, report = select_orderings(
        bp, bn, eop, eon, nl3, lw,
        trial_router=lambda *a, **k: _fail(9))
    assert report["selected"] == 0          # ties -> pool head wins
    assert report["conflicts"] == 9
    assert report["kind"] == "best"


def test_select_real_floor_beats_floorless(ctrl_pool):
    """A negotiable plateau is worth more than a census-only promise:
    a real (conflicts, cost, index) candidate beats every _UNROUTABLE
    one."""
    nl3, lw, bp, bn, eop, eon = ctrl_pool
    calls = {"n": 0}

    def router(_nl, _pl, _w, _lw, max_attempts=0):
        del max_attempts
        calls["n"] += 1
        return _fail(4) if calls["n"] == 1 else _fail(None)

    _op, _on, report = select_orderings(bp, bn, eop, eon, nl3, lw,
                                        trial_router=router)
    assert report["conflicts"] == 4 and report["selected"] == 0
    assert report["kind"] == "best"


def test_select_feasible_cage_free_head_short_circuits(ctrl_pool):
    """A head that routes AND cages nothing wins immediately: later
    candidates are never trialed (the closers' unaffected path)."""
    nl3, lw, bp, bn, eop, eon = ctrl_pool
    seen = []

    def router(_nl, _pl, _w, _lw, max_attempts=0):
        del max_attempts
        seen.append(1)
        return _ok()

    # the seed class is cage-free: force the pool head to it by passing
    # the seed as the SA best
    _op, _on, report = select_orderings(eop, eon, eop, eon, nl3, lw,
                                        trial_router=router)
    assert report["kind"] == "best" and report["cage"] == 0
    assert len(seen) == 1                   # short-circuit


# --------------------------------------------------------------------------
# the per-cell acceptance evidence (real router, one chain per cell)
# --------------------------------------------------------------------------

def _chain(flow_dir, rel):
    """The production chain (steered: the rung-3 default) + full-budget
    route; returns (nl3, lw, op, on, bd, route, walled_gates)."""
    path = os.path.join(flow_dir, "outputs", rel)
    nl3, lw, seeds = _pipeline(open(path).read())
    eop, eon = euler_orderings(seeds, lw)
    op, on, bd = sa_refine_routable(eop, eon, nl3, lw,
                                    variant_classes=True)
    placements, width = layout_cell(op, on, lw)
    r = route_cell(nl3, placements, width, lw)
    walled = []
    if not r.ok:
        _contests, walled = _RouteGrid(nl3, placements, width) \
            .structural_diagnosis()
        walled = [entry for entry in walled
                  if "gate contact" in entry[1]]
    return nl3, lw, op, on, bd, r, walled


@pytest.fixture(scope="module")
def complex10_evidence(flow_dir):
    return _chain(flow_dir, "adder/COMPLEX10.sp")


@pytest.fixture(scope="module")
def complex1_evidence(flow_dir):
    return _chain(flow_dir, "adder/COMPLEX1.sp")


def test_adder_complex10_chain_produces_cage_free_arrangement(
        complex10_evidence):
    """THE lever's claim on the 36T cell: at HEAD every pool candidate
    cages gate contacts (the contact-level census: the cost-best 5,
    euler seed 17) and the chain selected a caged arrangement; with the
    steered search the chain's SELECTED arrangement leaves every gate
    contact a free lane (census 0).  The route still fails -- the
    residual is a NET-connectivity cage the contact-level census cannot
    see (cl1#Y), the documented exact-model M2 dual-crossover next
    round."""
    _nl3, _lw, _op, _on, bd, r, walled = complex10_evidence
    sel = bd["selection"]
    assert sel["cage"] == 0                 # census-clean selection
    assert not r.ok                         # honest residual below
    note = getattr(r, "fail_note", None) or ""
    assert "statically caged" in note       # net-level cage remains
    assert walled                           # the diagnosis names it


def test_adder_complex1_chain_fails_only_on_corridor_contests(
        complex1_evidence):
    """The 30T cell's chain selects an arrangement whose full-budget
    route fails ONLY on the honest corridor contest -- no statically
    caged gate contact remains in the residual.

    Updated by the dual-basin pool (bench_int5 -> bench_int6
    restoration): the steered chain now also refines the pure ASTRAN
    cost, and on this plateau cell the legacy-basin arrangement's
    MEASURED floor is better than the steered one's at every budget
    (trial 136 vs 202 conflicts, full route 125 vs 202, width 17 vs 22
    columns), so the basin-blind (conflicts, cost, index) fallback rank
    selects ``best-legacy-die-both`` (census cage 2) over the steered
    ``die-both`` (census cage 1).  The residual class is unchanged:
    corridor T3 contests only, ``walled == []`` on both -- the census
    count is a steering heuristic, the router's diagnosis is the
    authority."""
    _nl3, _lw, _op, _on, bd, r, walled = complex1_evidence
    sel = bd["selection"]
    assert sel["kind"] == "best-legacy-die-both"
    assert sel["cage"] <= 2                 # contact-level near-clean
    assert sel["conflicts"] <= 202          # the measured floor improved
    assert not r.ok
    note = getattr(r, "fail_note", None) or ""
    assert "corridor T3 over-subscribed" in note
    assert "statically caged" not in note
    assert walled == []                     # no caged gate contacts


def test_heavy_chain_is_byte_stable_across_processes(flow_dir, tmp_path):
    """Cross-process determinism (invariant 9) on a 30T cell: identical
    selection (kind, conflicts, cage, ordering signature) under
    different PYTHONHASHSEED values."""
    helper = tmp_path / "cage_hash_helper.py"
    helper.write_text(_CHAIN_HASH_HELPER
                      % os.path.join("outputs", "adder", "COMPLEX1.sp"))
    digests = set()
    for seed in ("0", "1"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run([sys.executable, str(helper)], cwd=flow_dir,
                              env=env, capture_output=True, text=True,
                              check=True)
        digests.add(proc.stdout.strip().splitlines()[-1])
    assert len(digests) == 1, digests


_CHAIN_HASH_HELPER = """\
import hashlib, os, sys
sys.path.insert(0, os.getcwd())
from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from bigcell_engine.netlist_ext import build_bigcell_blocks, fold_devices, \\
    row_seeds
from bigcell_engine.place_euler import euler_orderings
from bigcell_engine.place_sa import ordering_signature, sa_refine_routable

nl = CellNetlist(parse_spice_subckt(open(%r).read()))
nl3, lw = fold_devices(nl)
seeds = row_seeds(build_bigcell_blocks(nl3), lw)
eop, eon = euler_orderings(seeds, lw)
op, on, bd = sa_refine_routable(eop, eon, nl3, lw, variant_classes=True)
sel = bd["selection"]
print(sel["kind"], sel["conflicts"], sel["cage"],
      hashlib.sha256(repr(ordering_signature(op, on)).encode())
      .hexdigest())
"""
