"""Unit tests for the 2026-10 bigcell runtime tuning (round-5 followup).

Two levers, both fully deterministic (AGENTS.md invariants 8/9):

- **route_grid.route_cell's phase-1 skip gate**: the static forced-demand
  diagnosis (:meth:`route_grid._RouteGrid.structural_diagnosis`) runs on
  the PHASE-1 grid before the negotiation.  The phase-1 cage graph is a
  sub-graph of the phase-2 one (no M2 vertical arcs; node vias are
  forbidden by the phase-1 post-pass rule (d)) and the diagnosis only
  ever over-states reachability, so a contested corridor column or a
  statically caged terminal it reports is a PROVEN floor of the
  pre-freedom vocabulary: the doomed phase-1 negotiation is skipped and
  phase 2 -- whose negotiation is independent of phase 1's -- runs
  unchanged (byte-identical results and fail notes).  Provenance lands
  on the RouteResult (``phase1_skipped`` / ``phase1_skip_reason``); the
  fail_note is NOT touched (engine.parse_fail_nets keeps parsing it for
  the window fixer).
- **place_sa's size-aware per-variant budgets**: full on small cells (at
  most ~12 blocks -- worst-case split 6 x 6 = 36), shrinking linearly
  with the P x N problem size to the euler-only / no-nominee floor at
  _VARIANT_SA_PROBLEM_CAP (variants are cheap probes of a different
  structure on big cells, not full refinements).

The byte-identity of clean-diagnosis routes is pinned by the existing
c4b3e9c fingerprints (test_bigcell_route_grid.py); here we pin the gate
itself, its provenance contract and the budget formulas.
"""
import hashlib
import os
import re
import subprocess
import sys

import pytest

from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from smt_engine.verify import verify_cell
from bigcell_engine import place_sa as ps
from bigcell_engine.geometry import layout_cell
from bigcell_engine.netlist_ext import (build_bigcell_blocks, fold_devices,
                                        row_seeds)
from bigcell_engine.place_euler import euler_orderings
from bigcell_engine.place_sa import sa_refine, sa_refine_routable
from bigcell_engine.route_grid import (_RouteGrid, route_cell,
                                       route_signature)
from smt_engine.layout_model import PlacedTransistor

INVX1_SP = """\
.subckt INVX1 VCC Y A GND
M0 Y A VCC VCC PMOS W=0.5u L=0.05u
M1 Y A GND GND NMOS W=0.25u L=0.05u
.ends INVX1
"""

INLINE_NAND2_SP = """\
.subckt NAND2 VCC Y A B GND
MpA Y A VCC VCC PMOS W=0.5u L=0.05u
MpB VCC B Y VCC PMOS W=0.5u L=0.05u
MnA Y A n1 GND NMOS W=0.5u L=0.05u
MnB n1 B GND GND NMOS W=0.5u L=0.05u
.ends NAND2
"""

PADLOCK_SP = """\
.subckt PADLOCK VCC Y A GND
MpY Y A VCC VCC PMOS W=0.5u L=0.05u
MnY Y A GND GND NMOS W=0.5u L=0.05u
.ends PADLOCK
"""


def _lib_subckt(cell, flow_dir):
    path = os.path.join(flow_dir, "..", "std_celllib",
                        "cellsAstranFriendly.sp")
    text = open(path, errors="ignore").read()
    return next(m.group(0) for m in re.finditer(
        r"\.subckt\s+%s\b.*?\.ends" % cell, text, re.S | re.I))


def _pure_cost_state(sp):
    """(netlist3, placement, width, leg_widths) via the pure-cost chain:
    fold -> blocks -> seeds -> euler -> sa_refine -- NO speculate stage,
    i.e. exactly the cost-best orientation route_cell receives first."""
    nl = CellNetlist(parse_spice_subckt(sp))
    nl3, lws = fold_devices(nl)
    blocks = build_bigcell_blocks(nl3)
    seeds = row_seeds(blocks, lws)
    op, on = euler_orderings(seeds, lws)
    bp, bn, _bd = sa_refine(op, on, nl3, lws)
    pl, w = layout_cell(bp, bn, lws)
    return nl3, pl, w, lws


@pytest.fixture(scope="module")
def nand2x1_cost_best(flow_dir):
    """The library NAND2X1's pure-cost orientation -- the arrangement
    whose phase-1 vocabulary is proven unroutable (bd3fda4) while the
    metal2 freedom closes it (the phase-1 skip's showcase cell)."""
    return _pure_cost_state(_lib_subckt("NAND2X1", flow_dir))


@pytest.fixture(scope="module")
def ctrl_pure_cost(flow_dir):
    """ctrl/COMPLEX0 through the fixed speculate pool (the
    structural-diagnosis specimen of test_bigcell_route_grid): its gate
    contacts contest the corridor beyond every vocabulary."""
    path = os.path.join(flow_dir, "outputs", "ctrl", "COMPLEX0.sp")
    nl = CellNetlist(parse_spice_subckt(open(path).read()))
    nl3, lws = fold_devices(nl)
    blocks = build_bigcell_blocks(nl3)
    seeds = row_seeds(blocks, lws)
    op, on = euler_orderings(seeds, lws)
    bp, bn, _bd = sa_refine_routable(op, on, nl3, lws,
                                     variant_classes=False)
    pl, w = layout_cell(bp, bn, lws)
    return nl3, pl, w, lws


# ---------------- the phase-1 skip gate ----------------

def test_phase1_diagnosis_proves_what_phase2_dissolves(nand2x1_cost_best):
    """The gate's semantics on its showcase cell: the PHASE-1 grid's
    diagnosis reports the corridor contest (a proven floor of the
    pre-freedom vocabulary) while the phase-2 grid's diagnosis is CLEAN
    -- the metal2 freedom dissolves exactly what doomed phase 1."""
    nl3, pl, w, _lws = nand2x1_cost_best
    g1 = _RouteGrid(nl3, pl, w, metal2_verticals=False)
    contests1, _walled1 = g1.structural_diagnosis()
    assert contests1, "the cost-best arrangement must contest phase 1"
    g2 = _RouteGrid(nl3, pl, w, metal2_verticals=True)
    contests2, walled2 = g2.structural_diagnosis()
    assert contests2 == {} and walled2 == []


def test_phase1_skip_lets_phase2_close_with_provenance(
        nand2x1_cost_best):
    """Doomed phase 1 skipped, phase 2 closes, provenance recorded: the
    pre-tuning path burned a full 8000-attempt phase-1 stall here before
    phase 2 closed (the M2 freedom)."""
    nl3, pl, w, lws = nand2x1_cost_best
    r = route_cell(nl3, pl, w, lws)
    assert r.ok and r.status_name == "FEASIBLE", (r.status_name,
                                                  r.fail_note)
    assert r.phase1_skipped is True
    reason = r.phase1_skip_reason
    assert "contested corridor cols" in reason or "caged" in reason
    # the reason's columns are exactly the phase-1 diagnosis's contests
    g1 = _RouteGrid(nl3, pl, w, metal2_verticals=False)
    contests, _walled = g1.structural_diagnosis()
    assert ("cols [%s]" % ", ".join(str(c) for c in sorted(contests))) \
        in reason
    rep = verify_cell(nl3, pl, r)
    assert rep.ok(), rep.violations


def test_clean_diagnosis_keeps_the_two_phase_order():
    """No invented skips: cells whose phase 1 closes carry
    phase1_skipped=False and no skip reason at all."""
    for sp in (INVX1_SP, INLINE_NAND2_SP):
        nl3, pl, w, lws = _pure_cost_state(sp)
        r = route_cell(nl3, pl, w, lws)
        assert r.ok, (r.status_name, r.fail_note)
        assert r.phase1_skipped is False
        assert not hasattr(r, "phase1_skip_reason")


def test_build_time_failure_needs_no_skip_and_keeps_its_note():
    """A build-time failure (gate past the last segment column) never
    reaches a negotiation: no diagnosis, no skip, byte-identical note."""
    nl = CellNetlist(parse_spice_subckt(PADLOCK_SP))
    by = {d.name: d for d in nl.devices}
    placement = {by["MpY"]: PlacedTransistor(0, 0, 1, 2),
                 by["MnY"]: PlacedTransistor(1, 2, 1, 2)}
    r = route_cell(nl, placement, 4, {})
    assert not r.ok and r.status_name == "UNKNOWN"
    assert "past the last segment column" in r.fail_note
    assert r.phase1_skipped is False
    assert not hasattr(r, "phase1_skip_reason")


def test_skipped_failure_keeps_the_honest_note_parseable(ctrl_pure_cost):
    """On a cell where phase 2 cannot dissolve the contest either, the
    skip changes NOTHING observable except the provenance: same status,
    same honest note fragments, and the window fixer's parser
    (engine.parse_fail_nets) still extracts the conflicted nets."""
    from bigcell_engine.engine import parse_fail_nets
    nl3, pl, w, lws = ctrl_pure_cost
    r = route_cell(nl3, pl, w, lws, max_attempts=5)
    assert not r.ok and r.status_name == "UNKNOWN"
    assert r.phase1_skipped is True
    assert r.phase1_skip_reason
    note = r.fail_note
    assert "no conflict-free routing" in note
    assert "corridor T3 over-subscribed" in note
    assert "phase-1" not in note and "skipped" not in note  # note untouched
    nets = parse_fail_nets(note)
    assert nets and all(isinstance(n, str) and n for n in nets)


def test_skip_decision_is_deterministic_in_process(nand2x1_cost_best):
    """The gate is a pure function of the build-time geometry
    (invariant 9): two route_cell runs agree on outcome and provenance."""
    nl3, pl, w, lws = nand2x1_cost_best
    sigs = set()
    for _run in range(2):
        r = route_cell(nl3, pl, w, lws)
        assert r.ok
        assert r.phase1_skipped is True
        sigs.add((hashlib.sha256(route_signature(r).encode()).hexdigest(),
                  r.phase1_skip_reason))
    assert len(sigs) == 1


def test_skip_route_is_byte_stable_across_processes(flow_dir,
                                                    nand2x1_cost_best,
                                                    tmp_path):
    """Cross-process determinism (invariant 9) through the skip gate:
    identical route signature + provenance under PYTHONHASHSEED 0/1."""
    nl3, pl, w, _lws = nand2x1_cost_best
    helper = tmp_path / "skip_hash_helper.py"
    helper.write_text(
        "import hashlib, sys\n"
        "sys.path.insert(0, %r)\n"
        "from smt_cell_placer import parse_spice_subckt\n"
        "from smt_engine.netlist import CellNetlist\n"
        "from bigcell_engine.netlist_ext import (build_bigcell_blocks,\n"
        "    fold_devices, row_seeds)\n"
        "from bigcell_engine.place_euler import euler_orderings\n"
        "from bigcell_engine.place_sa import sa_refine\n"
        "from bigcell_engine.geometry import layout_cell\n"
        "from bigcell_engine.route_grid import route_cell,"
        " route_signature\n"
        "sp = %r\n"
        "nl = CellNetlist(parse_spice_subckt(sp))\n"
        "nl3, lws = fold_devices(nl)\n"
        "seeds = row_seeds(build_bigcell_blocks(nl3), lws)\n"
        "op, on = euler_orderings(seeds, lws)\n"
        "bp, bn, _bd = sa_refine(op, on, nl3, lws)\n"
        "pl, w = layout_cell(bp, bn, lws)\n"
        "r = route_cell(nl3, pl, w, lws)\n"
        "assert r.ok and r.phase1_skipped is True\n"
        "print(hashlib.sha256(route_signature(r).encode()).hexdigest(),\n"
        "      hashlib.sha256(r.phase1_skip_reason.encode())\n"
        "      .hexdigest())\n"
        % (str(flow_dir), _lib_subckt("NAND2X1", flow_dir)))
    digests = set()
    for seed in ("0", "1"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run([sys.executable, str(helper)],
                              cwd=flow_dir, env=env,
                              capture_output=True, text=True,
                              check=True)
        digests.add(proc.stdout.strip())
    assert len(digests) == 1, digests


# ---------------- size-aware per-variant budgets ----------------

def test_variant_sa_moves_formula():
    """Full budget on small cells (problem <= 36 == worst-case 6x6 split
    of ~12 blocks), linear shrink to the euler-only floor at the skip
    cap (120).  Pure functions: monotone, deterministic."""
    for size in (1, 9, 25, 36):
        assert ps._variant_sa_moves(size) == ps.VARIANT_SA_MOVES
        assert ps._alignment_pair_cap(size) == ps._ALIGN_PAIR_CAP
    assert ps._variant_sa_moves(37) == int(
        ps.VARIANT_SA_MOVES * (120 - 37) / (120 - 36))
    assert ps._variant_sa_moves(78) == ps.VARIANT_SA_MOVES // 2
    assert ps._variant_sa_moves(120) == 0
    assert ps._alignment_pair_cap(78) == ps._ALIGN_PAIR_CAP // 2
    assert ps._alignment_pair_cap(120) == 0
    moves = [ps._variant_sa_moves(s) for s in range(1, 121)]
    assert moves == sorted(moves, reverse=True)
    caps = [ps._alignment_pair_cap(s) for s in range(1, 121)]
    assert caps == sorted(caps, reverse=True)


def test_variant_sa_iterations_small_cells_keep_todays_budget():
    """The pinned small-cell behaviour: for every small problem (<= 36 ==
    worst-case 6x6 split of ~12 blocks) the iteration count is EXACTLY
    the pre-tuning flat-budget formula -- the var:singles-align4
    acceptance evidence is untouched by the tuning."""
    def legacy(problem_size):
        reps = int(problem_size * ps.DEFAULT_QUALITY)
        return max(1, min(ps.VARIANT_SA_ITERATIONS,
                          ps.VARIANT_SA_MOVES // reps))
    for size in (1, 9, 25, 30, 36):
        assert ps._variant_sa_iterations(size) == legacy(size)
    assert ps._variant_sa_iterations(9) == ps.VARIANT_SA_ITERATIONS
    # a mid/big problem shrinks strictly below the flat legacy budget
    assert ps._variant_sa_iterations(55) < legacy(55)


def test_small_cell_variant_classes_keep_the_full_budget(flow_dir):
    """decomposition_variant_classes on ctrl/COMPLEX0 (6 blocks) still
    refines every variant with the FULL per-variant budget."""
    path = os.path.join(flow_dir, "outputs", "ctrl", "COMPLEX0.sp")
    nl = CellNetlist(parse_spice_subckt(open(path).read()))
    nl3, lws = fold_devices(nl)
    seen = []
    orig = ps.sa_refine

    def spy(*a, **kw):
        seen.append(kw.get("iterations"))
        return orig(*a, **kw)
    monkey = pytest.MonkeyPatch()
    monkey.setattr(ps, "sa_refine", spy)
    try:
        classes = ps.decomposition_variant_classes(nl3, lws)
    finally:
        monkey.undo()
    kinds = [k for k, _op, _on in classes]
    assert any(k.startswith("var:singles-align") for k in kinds)
    assert seen and all(it == ps.VARIANT_SA_ITERATIONS for it in seen)


def test_big_cell_variant_budgets_shrink(flow_dir):
    """multiplier/COMPLEX0 (22T): mid-size variants refine with a
    STRICTLY smaller iteration count than the flat legacy budget would
    give, small variants keep the full budget, and the over-cap variant
    (singles, 11x11 = 121 > 120) skips its refine entirely."""
    path = os.path.join(flow_dir, "outputs", "multiplier", "COMPLEX0.sp")
    nl = CellNetlist(parse_spice_subckt(open(path).read()))
    nl3, lws = fold_devices(nl)
    seen = []
    orig = ps.sa_refine

    def spy(*a, **kw):
        seen.append(kw.get("iterations"))
        return orig(*a, **kw)
    monkey = pytest.MonkeyPatch()
    monkey.setattr(ps, "sa_refine", spy)
    try:
        ps.decomposition_variant_classes(nl3, lws)
    finally:
        monkey.undo()
    legacy_55 = min(ps.VARIANT_SA_ITERATIONS,
                    ps.VARIANT_SA_MOVES // (55 * int(ps.DEFAULT_QUALITY)))
    assert legacy_55 == 5                    # the flat pre-tuning count
    assert seen == [ps.VARIANT_SA_ITERATIONS, 4, 4,
                    ps.VARIANT_SA_ITERATIONS]


def test_alignment_nominees_survive_on_small_cells(flow_dir):
    """The alignment nomination itself is untouched on the pinned small
    cell: ctrl/COMPLEX0's singles split still nominates its aligned
    orderings (the var:singles-align4 acceptance)."""
    path = os.path.join(flow_dir, "outputs", "ctrl", "COMPLEX0.sp")
    nl = CellNetlist(parse_spice_subckt(open(path).read()))
    nl3, lws = fold_devices(nl)
    blocks = build_bigcell_blocks(nl3, variant="singles")
    p_blocks = [b for b in blocks if b.first.is_p]
    n_blocks = [b for b in blocks if not b.first.is_p]
    got = ps.alignment_candidates(p_blocks, n_blocks, lws)
    assert 1 <= len(got) <= ps.ALIGN_CANDIDATES
