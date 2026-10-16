"""Unit tests for the routability-aware selection stage in
flow/bigcell_engine/place_sa.py (stage 3, doc STAGE3_BIGCELL_ENGINE.md
section 2.2 "Composition" -- ASTRAN's speculate loop,
autocell2.cpp:187-216).

The problem (proven in tests/unit/test_bigcell_route_grid.py and commit
bd3fda4): SA's cost is blind to routability, so the library NAND2X1's
cost-optimal orientation is structurally unroutable (both power
accesses on the input gate's column; the input crossing and the output
P<->N merge fight over one corridor node) while an electrically
identical mirrored orientation routes in ONE attempt.  The selection
stage generates a deterministic pool of candidate orderings (SA best,
row mirror / die-mirror variants, the pre-SA euler seed's variants,
cost-ranked per-block flip combinations), trial-routes each at a
REDUCED attempt budget, and returns the first FEASIBLE candidate --
else the lowest (conflicts, cost, index) one.

Fast tests inject a fake trial router; only the end-to-end closure
tests run the real router (each bounded well under 15 s).  All
randomness stays inside sa_refine's content-hash discipline; the
selection is pure (invariants 8/9).
"""
import os
import re
from types import SimpleNamespace

import pytest

from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from smt_engine.verify import verify_cell
from bigcell_engine.geometry import layout_cell
from bigcell_engine.netlist_ext import (build_bigcell_blocks, fold_devices,
                                        mirror_block, row_seeds)
from bigcell_engine.place_euler import euler_orderings
from bigcell_engine.place_sa import (_UNROUTABLE, DEFAULT_CANDIDATES,
                                     DEFAULT_TRIAL_ATTEMPTS,
                                     generate_candidates, ordering_signature,
                                     sa_refine, sa_refine_routable,
                                     select_orderings)
from bigcell_engine.route_grid import route_cell, route_signature

INVX1 = """\
.subckt INVX1 VCC Y A GND
M0 Y A VCC VCC PMOS W=0.5u L=0.05u
M1 Y A GND GND NMOS W=0.25u L=0.05u
.ends INVX1
"""

NAND2 = """\
.subckt NAND2 VCC Y A B GND
MpA Y A VCC VCC PMOS W=0.5u L=0.05u
MpB VCC B Y VCC PMOS W=0.5u L=0.05u
MnA Y A n1 GND NMOS W=0.5u L=0.05u
MnB n1 B GND GND NMOS W=0.5u L=0.05u
.ends NAND2
"""


def _pipeline(text):
    """fold -> blocks -> seeds -> euler: the pre-SA state."""
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


def _fail(conflicts=None):
    """A failed RouteResult-shaped stub; conflicts=None = build failure."""
    if conflicts is None:
        note = "impossible to find a path for net X"
    else:
        note = ("no conflict-free routing after %d attempts (best %d "
                "conflicts at attempt 2; unresolved: N)"
                % (DEFAULT_TRIAL_ATTEMPTS, conflicts))
    return SimpleNamespace(ok=False, fail_note=note, status_name="UNKNOWN",
                           attempts_used=DEFAULT_TRIAL_ATTEMPTS)


def _ok():
    return SimpleNamespace(ok=True, fail_note=None, status_name="FEASIBLE",
                           attempts_used=1)


# --------------------------------------------------------------------------
# candidate pool: distinctness, mirror coverage, determinism, cap
# --------------------------------------------------------------------------

def test_pool_dedupes_and_is_deterministic():
    nl, lw, eop, eon = _pipeline(NAND2)
    bp, bn, _bd = sa_refine(eop, eon, nl, lw, iterations=2, quality=2.0,
                            init_moves=100)
    a = generate_candidates(bp, bn, eop, eon, lw)
    b = generate_candidates(bp, bn, eop, eon, lw)
    assert [(kind, ordering_signature(op, on)) for kind, op, on in a] \
        == [(kind, ordering_signature(op, on)) for kind, op, on in b]
    sigs = [ordering_signature(op, on) for _k, op, on in a]
    assert len(sigs) == len(set(sigs)), "pool entries must be distinct"


def test_pool_leads_with_the_cost_best_and_covers_mirrors():
    nl, lw, eop, eon = _pipeline(NAND2)
    bp, bn, _bd = sa_refine(eop, eon, nl, lw, iterations=2, quality=2.0,
                            init_moves=100)
    pool = generate_candidates(bp, bn, eop, eon, lw)
    kinds = [kind for kind, _op, _on in pool]
    assert kinds[0] == "best"
    assert ordering_signature(pool[0][1], pool[0][2]) == \
        ordering_signature(bp, bn)
    # the mandated mirror variants are all present (single-block rows
    # collapse some spellings onto the same ordering -- hence sets)
    assert "flip-both" in kinds and "flip-P" in kinds and "flip-N" in kinds
    # the flip-both candidate is electrically identical: per row the same
    # device multiset, every member's end nets swapped (a different die
    # image, hence a different signature)
    fb = dict((k, (op, on)) for k, op, on in pool)["flip-both"]
    for got, ref in zip(fb, (bp, bn)):
        assert sorted(m.device.name for b in got for m in b.members) == \
            sorted(m.device.name for b in ref for m in b.members)
    assert ordering_signature(*fb) != ordering_signature(bp, bn)


def test_pool_carries_the_seed_ordering_when_it_differs(flow_dir):
    """When the SA moved away from the euler seed, the seed and its
    flip / die-mirror variants join the pool (the alternative block
    ORDER the SA search never revisits)."""
    path = os.path.join(flow_dir, "outputs", "ctrl", "COMPLEX0.sp")
    nl, lw, eop, eon = _pipeline(open(path).read())
    bp, bn, _bd = sa_refine(eop, eon, nl, lw)
    assert ordering_signature(bp, bn) != ordering_signature(eop, eon), \
        "ctrl's SA must move the seed for this test to be meaningful"
    pool = generate_candidates(bp, bn, eop, eon, lw)
    kinds = [kind for kind, _op, _on in pool]
    assert {"seed", "seed-flip-both", "seed-die-both"} <= set(kinds)
    seed = dict((k, (op, on)) for k, op, on in pool)["seed"]
    assert ordering_signature(*seed) == ordering_signature(eop, eon)


def test_pool_truncates_to_candidate_count():
    nl, lw, eop, eon = _pipeline(NAND2)
    bp, bn, _bd = sa_refine(eop, eon, nl, lw, iterations=2, quality=2.0,
                            init_moves=100)
    assert len(generate_candidates(bp, bn, eop, eon, lw, 3)) == 3
    assert len(generate_candidates(bp, bn, eop, eon, lw, 1)) == 1


def test_pool_beyond_fixed_classes_is_cost_ranked(flow_dir):
    """With room beyond the ten fixed classes, per-block flip
    combinations fill in, ranked by SA cost (the ctrl 8T cell has
    6 blocks -> 64 combinations)."""
    path = os.path.join(flow_dir, "outputs", "ctrl", "COMPLEX0.sp")
    nl, lw, eop, eon = _pipeline(open(path).read())
    bp, bn, _bd = sa_refine(eop, eon, nl, lw)
    pool = generate_candidates(bp, bn, eop, eon, lw,
                               candidate_count=DEFAULT_CANDIDATES + 5)
    combo_kinds = [k for k, _op, _on in pool if k.startswith("flip0")]
    assert combo_kinds, "cost-ranked flip combinations must appear"
    # no duplicate signatures even past the fixed classes
    sigs = [ordering_signature(op, on) for _k, op, on in pool]
    assert len(sigs) == len(set(sigs))
    # the combos are cost-ranked: the first surviving combination is the
    # cheapest flip assignment the SA cost can see (identity itself
    # deduped away against the pool head)
    from bigcell_engine.place_sa import _SAState
    by_kind = dict((k, (op, on)) for k, op, on in pool)
    costs = [_SAState(by_kind[k][0], by_kind[k][1], lw).total
             for k in combo_kinds]
    assert costs == sorted(costs)


# --------------------------------------------------------------------------
# selection with an injected (fake) trial router
# --------------------------------------------------------------------------

def _select(nl, lw, eop, eon, router, **kw):
    bp, bn, _bd = sa_refine(eop, eon, nl, lw, iterations=2, quality=2.0,
                            init_moves=100)
    return (bp, bn) + select_orderings(bp, bn, eop, eon, nl, lw,
                                       trial_router=router, **kw)


def test_select_first_feasible_in_pool_order():
    """The cost-best candidate is tried first; the first FEASIBLE
    candidate wins (here the proven mirror class), and later
    candidates are never trialed (short-circuit)."""
    nl, lw, eop, eon = _pipeline(NAND2)
    seen = []

    def router(_nl, _pl, _w, _lw, max_attempts=0):
        seen.append(max_attempts)
        if len(seen) == 1:
            return _fail(2)                    # the cost best plateaus
        return _ok()                           # the mirror routes

    _bp, _bn, op, on, report = _select(nl, lw, eop, eon, router)
    assert report["feasible"] and report["conflicts"] == 0
    assert report["kind"] == "flip-both"
    assert [e["kind"] for e in report["candidates"]] == ["best", "flip-both"]
    assert seen == [DEFAULT_TRIAL_ATTEMPTS] * 2
    # the selected orderings are the flip-both pool entry
    pool = generate_candidates(_bp, _bn, eop, eon, lw)
    assert ordering_signature(op, on) == ordering_signature(*pool[1][1:])


def test_select_fallback_ranks_by_conflicts_then_cost():
    nl, lw, eop, eon = _pipeline(NAND2)
    # scenario A: strictly worsening conflicts -> the pool head wins on
    # conflicts alone
    order = []

    def router2(_nl, _pl, _w, _lw, max_attempts=0):
        del max_attempts
        order.append(1)
        return _fail(2 + len(order))           # 3, 4, 5, ...

    _bp, _bn, op, on, report = _select(nl, lw, eop, eon, router2)
    assert not report["feasible"]
    assert report["conflicts"] == 3 and report["selected"] == 0
    pool = generate_candidates(_bp, _bn, eop, eon, lw)
    assert ordering_signature(op, on) == ordering_signature(*pool[0][1:])
    # scenario B: a strictly-lower-conflict LATER candidate must beat
    # the head (tie-break = conflicts first)
    calls = {"n": 0}

    def router3(_nl, _pl, _w, _lw, max_attempts=0):
        del max_attempts
        calls["n"] += 1
        return _fail(9) if calls["n"] < 3 else _fail(1)

    _bp2, _bn2, op2, on2, report2 = _select(nl, lw, eop, eon, router3)
    assert not report2["feasible"] and report2["conflicts"] == 1
    assert report2["selected"] == 2
    assert ordering_signature(op2, on2) == \
        ordering_signature(*pool[2][1:])


def test_select_build_failure_scores_worse_than_any_plateau():
    nl, lw, eop, eon = _pipeline(NAND2)
    calls = {"n": 0}

    def router(_nl, _pl, _w, _lw, max_attempts=0):
        del max_attempts
        calls["n"] += 1
        return _fail(9) if calls["n"] == 1 else _fail(None)

    _bp, _bn, op, on, report = _select(nl, lw, eop, eon, router)
    assert report["conflicts"] == 9            # a 9-conflict plateau
    assert report["selected"] == 0          # beats every build failure
    scored = {e["index"]: e["conflicts"] for e in report["candidates"]}
    assert any(v == _UNROUTABLE for v in scored.values())


def test_select_passes_the_trial_budget_to_the_router():
    nl, lw, eop, eon = _pipeline(NAND2)
    got = []

    def router(_nl, _pl, _w, _lw, max_attempts=0):
        got.append(max_attempts)
        return _ok()

    _select(nl, lw, eop, eon, router, trial_attempts=123)
    assert got and got[0] == 123


def test_select_survives_a_raising_router_candidate():
    nl, lw, eop, eon = _pipeline(NAND2)
    calls = {"n": 0}

    def router(_nl, _pl, _w, _lw, max_attempts=0):
        del max_attempts
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return _fail(4)

    _bp, _bn, op, on, report = _select(nl, lw, eop, eon, router)
    assert not report["feasible"] and report["conflicts"] == 4
    first = report["candidates"][0]
    assert first["conflicts"] == _UNROUTABLE and "boom" in first["note"]


def test_select_is_deterministic_in_process():
    nl, lw, eop, eon = _pipeline(NAND2)
    a = _select(nl, lw, eop, eon, lambda *a, **k: _fail(1))
    b = _select(nl, lw, eop, eon, lambda *a, **k: _fail(1))
    assert ordering_signature(a[2], a[3]) == ordering_signature(b[2], b[3])
    assert a[4]["candidates"] == b[4]["candidates"]


def test_sa_refine_routable_keeps_the_pure_cost_path_when_it_routes():
    """When every candidate routes, the SA-best (pool head) wins: the
    selection must not move a cell off its cost-optimal orientation."""
    nl, lw, eop, eon = _pipeline(NAND2)
    ref_p, ref_n, _bd = sa_refine(eop, eon, nl, lw, iterations=2,
                                  quality=2.0, init_moves=100)
    op, on, bd = sa_refine_routable(eop, eon, nl, lw, iterations=2,
                                    quality=2.0, init_moves=100,
                                    trial_router=lambda *a, **k: _ok())
    assert ordering_signature(op, on) == ordering_signature(ref_p, ref_n)
    assert bd["selection"]["feasible"] and bd["selection"]["kind"] == "best"
    # breakdown describes the SELECTED ordering
    from bigcell_engine.place_sa import _SAState
    assert bd["total"] == _SAState(op, on, lw).total


def test_sa_refine_routable_return_shape_and_membership():
    nl, lw, eop, eon = _pipeline(NAND2)
    op, on, bd = sa_refine_routable(eop, eon, nl, lw, iterations=2,
                                    quality=2.0, init_moves=100,
                                    trial_router=lambda *a, **k: _fail(1))
    assert set(bd) >= {"width", "gaps", "gate_mismatch", "span",
                       "max_congestion", "local_congestion", "total",
                       "selection"}
    for row in (op, on):
        names = [b.first.name for b in row]
        assert len(names) == len(set(names))
    assert sum(len(b.members) for b in op) + \
        sum(len(b.members) for b in on) == \
        sum(len(b.members) for b in eop) + \
        sum(len(b.members) for b in eon)


# --------------------------------------------------------------------------
# end to end: the real router, the three plateau cells + the two closers
# --------------------------------------------------------------------------

def _chain(text, **kw):
    nl, lw, eop, eon = _pipeline(text)
    op, on, bd = sa_refine_routable(eop, eon, nl, lw, **kw)
    return nl, lw, op, on, bd


def _closed_loop(text, label):
    """place (routability-aware) -> route -> verify; returns the chain."""
    nl, lw, op, on, bd = _chain(text)
    placements, width = layout_cell(op, on, lw)
    r = route_cell(nl, placements, width, lw)
    assert r.ok, (label, r.status_name, getattr(r, "fail_note", None))
    rep = verify_cell(nl, placements, r, blocks=list(op) + list(on))
    assert rep.ok(), "%s: %s" % (label, rep.violations)
    return bd, r


def test_invx1_stays_closing_end_to_end():
    bd, r = _closed_loop(INVX1, "INVX1")
    assert bd["selection"]["kind"] == "best"    # cost path untouched
    assert r.status_name == "FEASIBLE"


def test_inline_nand2_stays_closing_end_to_end():
    bd, r = _closed_loop(NAND2, "NAND2")
    assert bd["selection"]["kind"] == "best"
    assert r.status_name == "FEASIBLE"


def test_lib_nand2x1_closes_end_to_end(flow_dir):
    """THE regression, updated by the metal2 freedom: the library
    NAND2X1's cost-best orientation used to be structurally unroutable
    (both power accesses on the input gate's column; bd3fda4) and the
    speculate loop had to select the mirrored orientation.  With the
    router's metal2 verticals (node-level vias + M2 spans) the corridor
    contest the cost-best orientation used to lose is dissolvable -- it
    now routes FEASIBLE itself, lifting Y's N<->P merge onto metal2,
    and verifies clean.  (The mirror-escape machinery stays proven by
    NAND3X1 below.)"""
    bd, r = _closed_loop(_lib_subckt("NAND2X1", flow_dir), "NAND2X1")
    sel = bd["selection"]
    assert sel["feasible"], sel
    assert sel["kind"] == "best"                # the cost best routes now
    assert r.status_name == "FEASIBLE"
    # the freedom's fingerprint: the route lifts Y onto metal2
    assert r.m2v, "expected an M2 span in the closing route"
    assert getattr(r, "attempts_used", 99) <= 300


def test_lib_nand2x1_selection_is_deterministic(flow_dir):
    text = _lib_subckt("NAND2X1", flow_dir)
    a = _chain(text)
    b = _chain(text)
    assert ordering_signature(a[2], a[3]) == ordering_signature(b[2], b[3])
    assert a[4]["selection"]["kind"] == b[4]["selection"]["kind"]
    assert a[4]["selection"]["candidates"] == \
        b[4]["selection"]["candidates"]


def test_lib_nand3x1_closes_via_the_mirror_candidate(flow_dir):
    """Updated by the metal2 freedom (was: honest plateau in both naive
    orientations, 1 residual conflict): NAND3X1's cost-best orientation
    still plateaus (net A's crossing), but the mirrored orientation now
    ROUTES -- the speculate loop selects flip-both, the cell closes
    FEASIBLE and verifies clean.  The mirror escape machinery the
    stage exists for, demonstrated end to end."""
    bd, r = _closed_loop(_lib_subckt("NAND3X1", flow_dir), "NAND3X1")
    sel = bd["selection"]
    assert sel["feasible"], sel
    assert sel["kind"] in ("flip-both", "die-both", "seed-flip-both",
                           "seed-die-both")
    assert r.status_name == "FEASIBLE"


def test_ctrl_complex0_fixed_pool_honest_plateau(flow_dir):
    """ctrl/COMPLEX0 (8T) through the FIXED candidate pool (no
    decomposition variants): every mirror class is trialed, none routes,
    the fallback keeps the lowest-conflict candidate and the cell fails
    HONESTLY.  Updated by the metal2 freedom: the trial floor dropped
    from 4 conflicts to 1 (the escapes that used to be corridor-locked
    now lift onto metal2), and the structural note names what remains
    beyond metal2 -- the gate-contact contest: both cl0#B's and
    cl0#a_2_6#'s only surviving crossing track is T3, and M2 cannot
    lift an M1 gate contact.  The cell CLOSES only through the variant
    pool (test_bigcell_variants)."""
    path = os.path.join(flow_dir, "outputs", "ctrl", "COMPLEX0.sp")
    nl, lw, op, on, bd = _chain(open(path).read())
    sel = bd["selection"]
    assert not sel["feasible"]
    kinds = [e["kind"] for e in sel["candidates"]]
    assert {"flip-both", "die-both", "seed-flip-both"} <= set(kinds)
    assert sel["conflicts"] == 1                # the metal2-era trial floor
    placements, width = layout_cell(op, on, lw)
    r = route_cell(nl, placements, width, lw, max_attempts=1000)
    assert not r.ok and r.status_name == "UNKNOWN"
    note = getattr(r, "fail_note", None) or ""
    assert "no conflict-free routing" in note
    assert "unresolved: cl0#B" in note          # the same blocker class
    # the residual is named as beyond metal2: gate contacts, not escapes
    assert "gate contact" in note
    assert "does not dissolve" in note
    assert "terminal clash" not in note
    assert r.width_cols >= max(p.end_col for p in placements.values())


_SLOT_HASH_HELPER = """\
import hashlib, os, sys
sys.path.insert(0, os.getcwd())
from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from bigcell_engine.netlist_ext import (build_bigcell_blocks, fold_devices,
                                        row_seeds)
from bigcell_engine.place_euler import euler_orderings
from bigcell_engine.place_sa import ordering_signature, sa_refine_routable

SP = %r

nl = CellNetlist(parse_spice_subckt(SP))
nl3, lw = fold_devices(nl)
seeds = row_seeds(build_bigcell_blocks(nl3), lw)
eop, eon = euler_orderings(seeds, lw)
op, on, bd = sa_refine_routable(eop, eon, nl3, lw)
print(bd["selection"]["kind"], bd["selection"]["conflicts"],
      hashlib.sha256(repr(ordering_signature(op, on)).encode()).hexdigest())
"""


def test_selection_is_byte_stable_across_processes(flow_dir, tmp_path):
    """Cross-process determinism (invariant 9): identical selection
    (kind, conflicts, ordering signature) under different
    PYTHONHASHSEED values."""
    import subprocess
    import sys
    helper = tmp_path / "speculate_hash_helper.py"
    helper.write_text(_SLOT_HASH_HELPER
                      % _lib_subckt("NAND2X1", flow_dir))
    digests = set()
    for seed in ("0", "1"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run([sys.executable, str(helper)], cwd=flow_dir,
                              env=env, capture_output=True, text=True,
                              check=True)
        digests.add(proc.stdout.strip().splitlines()[-1])
    assert len(digests) == 1, digests
