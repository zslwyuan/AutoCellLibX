"""Unit tests for the dual-basin speculate pool (bench_int5 ->
bench_int6 restoration) in flow/bigcell_engine/place_sa.py.

The cage steering (commit 0106c02) is a DIFFERENT SEARCH BASIN, not a
strict improvement: where it lands well it wins (adder/COMPLEX1's
zero-caged search, the round-6 gains), but a steered chain's pool no
longer contains the pure-cost (legacy) arrangements, so a closure that
lives in the legacy basin loses its candidate.  The dual-basin pool of
a steered chain (``sa_refine_routable`` with ``cage`` truthy) runs BOTH
refines and joins

- the legacy MAIN best to the fixed pool (``best-legacy`` plus its
  proven both-rows flip / die-mirror), ranked after the ten steered
  fixed classes and before the flip combinations;
- the legacy-refined decomposition-variant twins
  (``var:<name>-legacy`` and its mirrors) as a lazy THIRD speculate
  phase, fired only when the steered phases left no cage-free FEASIBLE
  winner -- every cell closing in phases 1/2 keeps its exact pool,
  trials and selection (the ctrl/COMPLEX0 M2-fingerprint contract).

Selection stays trial-driven and basin-blind: a legacy-basin FEASIBLE
beats every steered plateau, the census only breaks ties BETWEEN
feasible candidates, and real conflict floors keep the verbatim
(conflicts, cost, index) rank -- so a legacy candidate with a better
measured floor wins the fallback (measured on adder/COMPLEX1: trial
floor 136 vs 202, full-route floor 125 vs 202, width 17 vs 22 cols,
walled == [] on both).

Per-cell note (bench_int5 -> bench_int6): the four round-5 closures the
restoration targets (CLKBUF1/2/3, multiplier/COMPLEX4) rode the
pre-6b35cee die view -- their parallel_phase placements reconstruct
pristinely to a MIRRORED die (the device-adjacency check fails), and
the honest HEAD router/verifier pair rejects every arrangement this
module's pools can offer; the honest residuals are pinned in
:func:`test_clkbuf1_chain_residual_is_corridor_only` /
:func:`test_complex4_chain_residual_is_corridor_only` so any future
policy change that worsens them is caught.

Fast tests use ctrl/COMPLEX0 (8T) and injected trial routers; the two
chain pins and the cross-process determinism pins run the real router.
All randomness stays inside sa_refine's content-hash discipline
(invariants 8/9).
"""
import hashlib
import os
import re
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
from bigcell_engine.place_sa import (_UNROUTABLE, DEFAULT_CANDIDATES,
                                     DEFAULT_TRIAL_ATTEMPTS,
                                     LEGACY_BASIN_CLASSES,
                                     decomposition_variant_classes,
                                     generate_candidates,
                                     ordering_signature,
                                     sa_refine, sa_refine_routable,
                                     select_orderings)
from bigcell_engine.route_grid import route_cell

NAND2 = """\
.subckt NAND2 VCC Y A B GND
MpA Y A VCC VCC PMOS W=0.5u L=0.05u
MpB VCC B Y VCC PMOS W=0.5u L=0.05u
MnA Y A n1 GND NMOS W=0.5u L=0.05u
MnB n1 B GND GND NMOS W=0.5u L=0.05u
.ends NAND2
"""


def _pipeline(text, variant=None):
    """fold -> blocks -> seeds -> euler: the pre-SA state."""
    nl = CellNetlist(parse_spice_subckt(text))
    nl3, lw = fold_devices(nl)
    blocks = build_bigcell_blocks(nl3, **({"variant": variant}
                                          if variant else {}))
    seeds = row_seeds(blocks, lw)
    eop, eon = euler_orderings(seeds, lw)
    return nl3, lw, eop, eon


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
# agent E's size-aware variant budgets stay intact (the dual refine
# reuses them verbatim)
# --------------------------------------------------------------------------

def test_variant_budget_scaling_unchanged():
    assert ps.VARIANT_SA_MOVES == 6000
    assert ps.VARIANT_SA_ITERATIONS == 12
    assert ps._variant_sa_moves(36) == 6000
    assert ps._variant_sa_moves(64) == 4000
    assert ps._variant_sa_moves(120) == 0
    assert ps._variant_sa_iterations(16) == 12
    assert ps._variant_sa_iterations(64) == 3
    assert ps._alignment_pair_cap(16) == ps._ALIGN_PAIR_CAP
    assert ps._alignment_pair_cap(64) == 133333
    assert ps._alignment_pair_cap(120) == 0


# --------------------------------------------------------------------------
# the fixed-pool legacy classes (generate_candidates legacy_best)
# --------------------------------------------------------------------------

def test_legacy_classes_rank_after_fixed_before_combos():
    nl3, lw, eop, eon = _pipeline(open(_CTRL_SP).read())
    bp, bn, _bd = sa_refine(eop, eon, nl3, lw)
    leg_p, leg_n, _lbd = sa_refine(eop, eon, nl3, lw, cage=True)
    assert ordering_signature(leg_p, leg_n)         != ordering_signature(bp, bn), "ctrl's basins must differ"
    pool = generate_candidates(bp, bn, eop, eon, lw, candidate_count=100,
                               legacy_best=(leg_p, leg_n))
    kinds = [k for k, _op, _on in pool]
    assert "best-legacy" in kinds
    # the trio sits directly after the last steered fixed class
    fixed_tail = "seed-die-both"
    assert kinds.index("best-legacy") == kinds.index(fixed_tail) + 1
    assert kinds[kinds.index("best-legacy"):kinds.index("best-legacy") + 3] \
        == ["best-legacy", "best-legacy-flip-both",
            "best-legacy-die-both"]
    # the legacy trio precedes every flip combination
    combos = [i for i, k in enumerate(kinds) if k.startswith("flip0")]
    if combos:
        assert min(combos) > kinds.index("best-legacy-die-both")


def test_legacy_classes_dedupe_when_basins_coincide():
    """A cell whose steered refine lands on the pure-cost best (the cage
    term does not move it) adds NO legacy class (dedupe by content)."""
    nl3, lw, eop, eon = _pipeline(NAND2)
    bp, bn, _bd = sa_refine(eop, eon, nl3, lw)
    leg_p, leg_n, _lbd = sa_refine(eop, eon, nl3, lw, cage=True)
    if ordering_signature(leg_p, leg_n) != ordering_signature(bp, bn):
        pytest.skip("NAND2's basins differ; the dedupe pin needs a cell "
                    "whose steered refine is the pure-cost best")
    pool = generate_candidates(bp, bn, eop, eon, lw,
                               legacy_best=(leg_p, leg_n))
    assert all(not k.startswith("best-legacy") for k, _o, _n in pool)


def test_legacy_pool_is_deterministic():
    nl3, lw, eop, eon = _pipeline(open(_CTRL_SP).read())
    bp, bn, _bd = sa_refine(eop, eon, nl3, lw)
    leg = sa_refine(eop, eon, nl3, lw, cage=True)[:2]
    a = generate_candidates(bp, bn, eop, eon, lw, legacy_best=leg)
    b = generate_candidates(bp, bn, eop, eon, lw, legacy_best=leg)
    assert [(k, ordering_signature(o1, o2)) for k, o1, o2 in a] \
        == [(k, ordering_signature(o1, o2)) for k, o1, o2 in b]


# --------------------------------------------------------------------------
# the variant twins (decomposition_variant_classes basin="legacy")
# --------------------------------------------------------------------------

_CTRL_SP = os.path.join(os.path.dirname(__file__), "..", "..", "flow",
                        "outputs", "ctrl", "COMPLEX0.sp")


def test_variant_legacy_twins_refine_the_pure_cost():
    """basin='legacy' refines with cage=False and suffixes the kinds;
    each twin's ordering equals sa_refine(cage=False) on the same
    variant seeds."""
    nl3, lw, _eop, _eon = _pipeline(open(_CTRL_SP).read())
    steered = decomposition_variant_classes(nl3, lw, cage=True)
    legacy = decomposition_variant_classes(nl3, lw, cage=True,
                                           basin="legacy")
    s_kinds = [k for k, _o1, _o2 in steered]
    l_kinds = [k for k, _o1, _o2 in legacy]
    assert any(k.endswith("-legacy") for k in l_kinds)
    assert not any(k.endswith("-legacy") for k in s_kinds)
    # shape parity: stripping the suffix maps legacy kinds onto steered
    # kinds of the same class shape (the align nominees are identical
    # enumerations and dedupe against the steered ones in the caller)
    strip = lambda k: k.replace("-legacy", "")          # noqa: E731
    assert sorted(strip(k) for k in l_kinds if "align" not in k) \
        == sorted(k for k in s_kinds if "align" not in k)
    # spot-verify one twin against its own variant's pure-cost refine
    from bigcell_engine.netlist_ext import row_seeds
    from bigcell_engine.place_euler import euler_orderings as eo
    twin = dict((k, (o1, o2)) for k, o1, o2 in legacy)
    for kind in ("var:singles-legacy", "var:parallel_phase-legacy"):
        if kind not in twin:
            continue
        name = kind.replace("-legacy", "").replace("var:", "")
        seeds = row_seeds(build_bigcell_blocks(nl3, variant=name), lw)
        seop, seon = eo(seeds, lw)
        rp, rn, _bd = sa_refine(seop, seon, nl3, lw, cage=False)
        assert ordering_signature(*twin[kind]) == \
            ordering_signature(rp, rn)


def test_variant_legacy_twins_deterministic_and_total():
    nl3, lw, _eop, _eon = _pipeline(open(_CTRL_SP).read())
    a = decomposition_variant_classes(nl3, lw, cage=True, basin="legacy")
    b = decomposition_variant_classes(nl3, lw, cage=True, basin="legacy")
    assert [(k, ordering_signature(o1, o2)) for k, o1, o2 in a] \
        == [(k, ordering_signature(o1, o2)) for k, o1, o2 in b]
    ref = sorted(d.name for d in nl3.devices)
    for _k, o1, o2 in a:
        seen = [m.device.name for row in (o1, o2) for blk in row
                for m in blk.members]
        assert sorted(seen) == ref


def test_unknown_basin_raises():
    nl3, lw, _eop, _eon = _pipeline(NAND2)
    with pytest.raises(ValueError):
        decomposition_variant_classes(nl3, lw, basin="nope")


# --------------------------------------------------------------------------
# selection: basin-blind, trial-driven (injected routers)
# --------------------------------------------------------------------------

def _routable_dual(nl3, lw, eop, eon):
    bp, bn, _bd = sa_refine(eop, eon, nl3, lw, cage=True)
    leg = sa_refine(eop, eon, nl3, lw, cage=False)[:2]
    return (bp, bn), leg


def test_legacy_feasible_beats_steered_plateau():
    """THE restoration contract: a legacy-basin FEASIBLE must never lose
    to a steered INFEASIBLE/plateau, however late it sits in pool
    order."""
    nl3, lw, eop, eon = _pipeline(open(_CTRL_SP).read())
    (bp, bn), leg = _routable_dual(nl3, lw, eop, eon)
    pool_kinds = [k for k, _o1, _o2 in generate_candidates(
        bp, bn, eop, eon, lw,
        candidate_count=DEFAULT_CANDIDATES + LEGACY_BASIN_CLASSES,
        legacy_best=leg)]
    assert pool_kinds[0] == "best" and "best-legacy" in pool_kinds
    legacy_idx = pool_kinds.index("best-legacy")
    calls = {"n": 0}

    def router(_nl, _pl, _w, _lw, max_attempts=0):
        del max_attempts
        calls["n"] += 1
        if calls["n"] == legacy_idx + 1:
            return _ok()          # ONLY the legacy specimen routes
        return _fail(9)

    _op, _on, report = select_orderings(
        bp, bn, eop, eon, nl3, lw,
        candidate_count=DEFAULT_CANDIDATES + LEGACY_BASIN_CLASSES,
        trial_router=router, legacy_best=leg)
    assert report["feasible"] and report["conflicts"] == 0
    assert report["kind"] == "best-legacy"
    assert report["selected"] == legacy_idx


def test_steered_head_short_circuits_before_legacy_classes():
    """A steered head that routes cage-free wins immediately: the legacy
    classes are never built into trials (the closers' unaffected
    path)."""
    nl3, lw, eop, eon = _pipeline(open(_CTRL_SP).read())
    (bp, bn), leg = _routable_dual(nl3, lw, eop, eon)
    seen = []

    def router(_nl, _pl, _w, _lw, max_attempts=0):
        del max_attempts
        seen.append(1)
        return _ok()

    _op, _on, report = select_orderings(bp, bn, eop, eon, nl3, lw,
                                        trial_router=router,
                                        legacy_best=leg)
    assert report["kind"] == "best" and report["cage"] == 0
    assert len(seen) == 1


def test_legacy_floor_wins_the_fallback_when_measured_better():
    """Real conflict floors keep the verbatim (conflicts, cost, index)
    rank -- basin-blind: a legacy candidate whose measured floor is
    better than every steered floor wins the no-route fallback (the
    adder/COMPLEX1 evidence, miniaturized)."""
    nl3, lw, eop, eon = _pipeline(open(_CTRL_SP).read())
    (bp, bn), leg = _routable_dual(nl3, lw, eop, eon)
    pool_kinds = [k for k, _o1, _o2 in generate_candidates(
        bp, bn, eop, eon, lw,
        candidate_count=DEFAULT_CANDIDATES + LEGACY_BASIN_CLASSES,
        legacy_best=leg)]
    legacy_idx = pool_kinds.index("best-legacy")
    calls = {"n": 0}

    def router(_nl, _pl, _w, _lw, max_attempts=0):
        del max_attempts
        calls["n"] += 1
        if calls["n"] == legacy_idx + 1:
            return _fail(4)       # the legacy floor: better than all
        return _fail(9)

    _op, _on, report = select_orderings(
        bp, bn, eop, eon, nl3, lw,
        candidate_count=DEFAULT_CANDIDATES + LEGACY_BASIN_CLASSES,
        trial_router=router, legacy_best=leg)
    assert not report["feasible"] and report["conflicts"] == 4
    assert report["kind"] == "best-legacy"


def test_no_legacy_classes_without_legacy_best():
    """cage=False chains (legacy_best=None) keep today's exact pool:
    the first DEFAULT_CANDIDATES kinds are the ten fixed classes."""
    nl3, lw, eop, eon = _pipeline(open(_CTRL_SP).read())
    bp, bn, _bd = sa_refine(eop, eon, nl3, lw)
    pool = generate_candidates(bp, bn, eop, eon, lw,
                               candidate_count=DEFAULT_CANDIDATES)
    kinds = [k for k, _o1, _o2 in pool]
    assert kinds[0] == "best"
    assert len(kinds) == DEFAULT_CANDIDATES
    assert not any(k.startswith("best-legacy") for k in kinds)


# --------------------------------------------------------------------------
# sa_refine_routable: the dual refine wiring
# --------------------------------------------------------------------------

def test_routable_dual_refine_joins_the_legacy_basin():
    """A steered chain refines twice: the selection report carries the
    fixed-pool legacy classes when the basins differ, and the candidate
    count grows by exactly LEGACY_BASIN_CLASSES."""
    path = os.path.join(os.path.dirname(__file__), "..", "..", "flow",
                        "outputs", "ctrl", "COMPLEX0.sp")
    nl3, lw, eop, eon = _pipeline(open(path).read())

    def router(_nl, _pl, _w, _lw, max_attempts=0):
        del max_attempts
        return _fail(7)

    _op, _on, bd = sa_refine_routable(
        eop, eon, nl3, lw, trial_router=router, variant_classes=True)
    sel = bd["selection"]
    kinds = [e["kind"] for e in sel["candidates"]]
    assert "best-legacy" in kinds
    # the legacy classes sit after the ten steered fixed classes (the
    # fixed pool grew by exactly LEGACY_BASIN_CLASSES); the report's
    # candidate_count is the FINAL pool length (phases 2/3 grow it)
    assert kinds.index("best-legacy") == 10
    assert kinds[10:13] == ["best-legacy", "best-legacy-flip-both",
                            "best-legacy-die-both"]
    assert sel["candidate_count"] == len(kinds)


def test_routable_pure_cost_chain_has_no_legacy_pool():
    """variant_classes=False (cage binds to False): today's exact pool,
    no legacy classes, no third phase."""
    nl3, lw, eop, eon = _pipeline(NAND2)
    _op, _on, bd = sa_refine_routable(
        eop, eon, nl3, lw, trial_router=lambda *a, **k: _fail(1),
        variant_classes=False)
    kinds = [e["kind"] for e in bd["selection"]["candidates"]]
    assert not any("legacy" in k for k in kinds)


def test_phase3_legacy_twins_fire_only_after_steered_variants_fail():
    """The lazy third phase: with a steered chain whose steered variant
    classes all plateau, the legacy twins join and are trialed after
    every steered class; with a cage-free FEASIBLE found in phase 2a
    they are never built."""
    path = os.path.join(os.path.dirname(__file__), "..", "..", "flow",
                        "outputs", "ctrl", "COMPLEX0.sp")
    nl3, lw, eop, eon = _pipeline(open(path).read())
    # every candidate plateaus: phase 3 must fire and be trialed LAST
    calls = []

    def router(_nl, _pl, _w, _lw, max_attempts=0):
        del max_attempts
        calls.append(1)
        return _fail(6)

    _op, _on, bd = sa_refine_routable(
        eop, eon, nl3, lw, trial_router=router, variant_classes=True)
    kinds = [e["kind"] for e in bd["selection"]["candidates"]]
    legacy_var = [k for k in kinds if k.startswith("var:")
                  and "-legacy" in k]
    assert legacy_var, "phase 3 must join the legacy variant twins"
    first_legacy = min(kinds.index(k) for k in legacy_var)
    # every legacy twin comes after every steered variant class
    steered_var = [k for k in kinds if k.startswith("var:")
                   and "-legacy" not in k]
    assert first_legacy > max(kinds.index(k) for k in steered_var)
    # and the winning fallback is the best measured floor across both
    assert bd["selection"]["conflicts"] == 6
    # a phase-2a cage-free FEASIBLE skips phase 3 entirely (the ctrl
    # M2-fingerprint contract): the real-router closure pin lives in
    # test_bigcell_variants / test_bigcell_route_grid and still passes.


# --------------------------------------------------------------------------
# per-cell honest-residual regression pins (real router; the round-5
# closures are NOT restorable -- see the module docstring)
# --------------------------------------------------------------------------

def _lib_subckt(cell, flow_dir):
    """One .subckt block from the ASTRAN-friendly library file."""
    path = os.path.join(flow_dir, "..", "std_celllib",
                        "cellsAstranFriendly.sp")
    text = open(path, errors="ignore").read()
    return next(m.group(0) for m in re.finditer(
        r"\.subckt\s+%s\b.*?\.ends" % cell, text, re.S | re.I))


@pytest.fixture(scope="module")
def clkbuf1_chain(flow_dir):
    return _full_chain_text(_lib_subckt("CLKBUF1", flow_dir))


@pytest.fixture(scope="module")
def complex4_chain(flow_dir):
    return _full_chain(flow_dir, "outputs", "multiplier", "COMPLEX4.sp")


def _full_chain(flow_dir, *rel):
    path = os.path.join(flow_dir, *rel)
    return _full_chain_text(open(path).read())


def _full_chain_text(text):
    nl = CellNetlist(parse_spice_subckt(text))
    from bigcell_engine.engine import _heuristic_placement
    nl3, pl, w, lws, blocks, _ord = _heuristic_placement(nl)
    r = route_cell(nl3, pl, w, lws)
    return nl3, pl, w, lws, blocks, r


def test_clkbuf1_chain_residual_is_corridor_only(clkbuf1_chain):
    """CLKBUF1 (16T) through the production chain at HEAD+dual-basin:
    the honest residual stays a corridor contest with NO statically
    caged gate (the round-5 phantom closure -- a mirrored-die route the
    pre-6b35cee router/verifier pair shared -- is not reproducible; pin
    the honest floor so a policy change cannot silently worsen it)."""
    nl3, pl, w, lws, blocks, r = clkbuf1_chain
    assert not r.ok
    note = getattr(r, "fail_note", None) or ""
    assert "statically caged" not in note
    from bigcell_engine.route_grid import _RouteGrid
    _contests, walled = _RouteGrid(nl3, pl, w).structural_diagnosis()
    assert walled == []
    assert r.width_cols >= max(p.end_col for p in pl.values())


def test_complex4_chain_residual_is_corridor_only(complex4_chain):
    """multiplier/COMPLEX4 (14T): same honest-residual contract as
    CLKBUF1 (its round-5 winner was a census-mirrored parallel_phase
    alignment nominee; the honest die view walls the placement)."""
    nl3, pl, w, lws, blocks, r = complex4_chain
    assert not r.ok
    note = getattr(r, "fail_note", None) or ""
    assert "statically caged" not in note
    from bigcell_engine.route_grid import _RouteGrid
    _contests, walled = _RouteGrid(nl3, pl, w).structural_diagnosis()
    assert walled == []


# --------------------------------------------------------------------------
# cross-process determinism (invariant 9) on the dual-basin chains
# --------------------------------------------------------------------------

_BASIN_HASH_HELPER = """\
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


@pytest.mark.parametrize("sp", ["CLKBUF1", "COMPLEX4"])
def test_dual_basin_chains_are_byte_stable_across_processes(
        flow_dir, tmp_path, sp):
    if sp == "CLKBUF1":
        src = tmp_path / "CLKBUF1.sp"
        src.write_text(_lib_subckt("CLKBUF1", flow_dir))
        cell_path = str(src)
    else:
        cell_path = os.path.join(flow_dir, "outputs", "multiplier",
                                 "COMPLEX4.sp")
    helper = tmp_path / "basin_hash_helper.py"
    helper.write_text(_BASIN_HASH_HELPER % cell_path)
    digests = set()
    for seed in ("0", "1"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run([sys.executable, str(helper)], cwd=flow_dir,
                              env=env, capture_output=True, text=True,
                              check=True)
        digests.add(proc.stdout.strip().splitlines()[-1])
    assert len(digests) == 1, digests
