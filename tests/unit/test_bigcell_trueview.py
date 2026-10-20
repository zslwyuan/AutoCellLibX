"""Unit tests for the TRUE-VIEW trial contract in
flow/bigcell_engine/place_sa.py (the multiplier/COMPLEX4 14T closure).

The blocks-less trial ranked a tree-arrangement candidate by a die view
the production route never recreates: the router consumes the
candidate's OWN orientation-aware block view (a7b23cc wired it into
route_cell and verify), but the speculate trials called the router
without it -- on multiplier/COMPLEX4 the closers
``var:parallel_phase-flip-both``/``-align3`` trialed BELOW
``var:parallel_phase-die-both`` (blocks-less floors 3/6 vs 2) while
their own views route CLEAN and die-both's own view is full-budget
floor 4 with a CP-SAT-proven unwirable window.  The contract fix:
``select_orderings`` probes the router once
(:func:`place_sa._router_accepts_blocks`) and passes
``blocks=list(ordering_p) + list(ordering_n)`` per candidate to every
router that accepts the keyword (the real ``route_grid.route_cell``,
``**kwargs`` stubs); routers without it -- every injected fake that
predates the contract -- keep the exact blocks-less legacy call.

Fast tests inject fakes; the COMPLEX4 acceptance group runs the real
production chain (place -> select -> route -> verify -> gds sanity).
All randomness stays inside sa_refine's content-hash discipline; the
selection is pure (invariants 8/9).
"""
import hashlib
import os
import re
import subprocess
import sys
from types import SimpleNamespace

import pytest

from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from smt_engine.verify import verify_cell
from bigcell_engine.geometry import GRID_UM, layout_cell
from bigcell_engine.netlist_ext import (build_bigcell_blocks, fold_devices,
                                        row_seeds)
from bigcell_engine.place_euler import euler_orderings
from bigcell_engine.place_sa import (DEFAULT_CANDIDATES,
                                     DEFAULT_TRIAL_ATTEMPTS,
                                     _UNROUTABLE, _router_accepts_blocks,
                                     generate_candidates, ordering_signature,
                                     sa_refine, select_orderings)
from bigcell_engine.route_grid import route_cell, route_signature

NAND2 = """\
.subckt NAND2 VCC Y A B GND
MpA Y A VCC VCC PMOS W=0.5u L=0.05u
MpB VCC B Y VCC PMOS W=0.5u L=0.05u
MnA Y A n1 GND NMOS W=0.5u L=0.05u
MnB n1 B GND GND NMOS W=0.5u L=0.05u
.ends NAND2
"""

COMPLEX4_PATH_PARTS = ("outputs", "multiplier", "COMPLEX4.sp")


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


def _fail(conflicts):
    note = ("no conflict-free routing after %d attempts (best %d "
            "conflicts at attempt 2; unresolved: N)"
            % (DEFAULT_TRIAL_ATTEMPTS, conflicts))
    return SimpleNamespace(ok=False, fail_note=note,
                           status_name="UNKNOWN",
                           attempts_used=DEFAULT_TRIAL_ATTEMPTS)


def _ok():
    return SimpleNamespace(ok=True, fail_note=None,
                           status_name="FEASIBLE", attempts_used=1)


def _view_sig(blocks_view):
    """Content key of a flat blocks view: (P-row key, N-row key)."""
    p = [b for b in blocks_view if b.first.is_p]
    n = [b for b in blocks_view if not b.first.is_p]
    return ordering_signature(p, n)


# --------------------------------------------------------------------------
# the contract: who receives blocks, and what exactly
# --------------------------------------------------------------------------

def test_router_probe_discriminates_the_contract_generations():
    """The probe is a pure function of the router object: the real
    route_cell (blocks parameter since a7b23cc) and **kwargs stubs take
    the true-view call; the legacy 5-argument fakes keep the blocks-less
    call."""
    assert _router_accepts_blocks(route_cell)
    assert _router_accepts_blocks(lambda *a, **k: None)

    def legacy(_nl, _pl, _w, _lw, max_attempts=0):
        del max_attempts

    assert not _router_accepts_blocks(legacy)

    class LegacyFake(object):
        def __call__(self, _nl, _pl, _w, _lw, max_attempts=0):
            del max_attempts

    assert not _router_accepts_blocks(LegacyFake())


def test_blocks_aware_router_receives_each_candidates_own_view():
    """A router declaring ``blocks`` gets, for every trialed candidate,
    exactly that candidate's orientation-aware block view
    (list(ordering_p) + list(ordering_n) -- the engine's meta["blocks"]
    shape for the winner), a TOTAL decomposition of the netlist."""
    nl, lw, eop, eon = _pipeline(NAND2)
    bp, bn, _bd = sa_refine(eop, eon, nl, lw, iterations=2, quality=2.0,
                            init_moves=100)
    pool = generate_candidates(bp, bn, eop, eon, lw,
                               candidate_count=DEFAULT_CANDIDATES,
                               netlist=nl)
    got = []

    def router(_nl, _pl, _w, _lw, max_attempts=0, blocks=None):
        del max_attempts
        got.append(blocks)
        return _fail(9)                       # trial every candidate

    _op, _on, report = select_orderings(bp, bn, eop, eon, nl, lw,
                                        trial_router=router)
    assert report["trial_view"] == "blocks"
    assert len(got) == len(pool)              # every candidate was trialed
    device_names = {d.name for d in nl.devices}
    for blocks_view, (_kind, op, on) in zip(got, pool):
        assert _view_sig(blocks_view) == ordering_signature(op, on)
        seen = []
        for blk in blocks_view:
            for member in blk.members:
                seen.append(member.device.name)
        assert len(seen) == len(set(seen))    # no device twice
        assert set(seen) == device_names      # ... and none missing


def test_var_kwargs_router_receives_blocks_and_head_short_circuits():
    """A **kwargs stub receives the view too (k["blocks"]); a FEASIBLE
    head still short-circuits the scan after one trial."""
    nl, lw, eop, eon = _pipeline(NAND2)
    bp, bn, _bd = sa_refine(eop, eon, nl, lw, iterations=2, quality=2.0,
                            init_moves=100)
    seen = []

    def router(*a, **k):
        seen.append(k.get("blocks"))
        return _ok()

    _op, _on, report = select_orderings(bp, bn, eop, eon, nl, lw,
                                        trial_router=router)
    assert report["kind"] == "best" and report["selected"] == 0
    assert len(seen) == 1
    blocks_view = seen[0]
    assert isinstance(blocks_view, list) and blocks_view
    assert _view_sig(blocks_view) == ordering_signature(bp, bn)


def test_legacy_fake_router_keeps_the_blocks_less_call():
    """Today's injected fakes (no ``blocks`` parameter, no **kwargs)
    keep their exact legacy call: the selection completes with the same
    policy (fallback = pool head on equal floors) and the report names
    the blocks-less view."""
    nl, lw, eop, eon = _pipeline(NAND2)
    bp, bn, _bd = sa_refine(eop, eon, nl, lw, iterations=2, quality=2.0,
                            init_moves=100)
    pool = generate_candidates(bp, bn, eop, eon, lw,
                               candidate_count=DEFAULT_CANDIDATES,
                               netlist=nl)
    calls = []

    def router(_nl, _pl, _w, _lw, max_attempts=0):
        del max_attempts
        calls.append(1)
        return _fail(1)                       # equal floors everywhere

    _op, _on, report = select_orderings(bp, bn, eop, eon, nl, lw,
                                        trial_router=router)
    assert report["trial_view"] == "blocks-less"
    assert report["selected"] == 0 and report["kind"] == "best"
    assert report["conflicts"] == 1
    assert len(calls) == len(pool)


# --------------------------------------------------------------------------
# the acceptance: multiplier/COMPLEX4 closes through the full chain
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def complex4_chain(flow_dir):
    """The full production chain on multiplier/COMPLEX4, twice over the
    module: (run1) engine._heuristic_placement (true-view select) ->
    route3 with the selected blocks view -> verify; (run2) the same
    chain again for the in-process determinism pin; plus the speculate
    report of the engine's exact placement parameters."""
    from bigcell_engine.engine import _heuristic_placement

    path = os.path.join(flow_dir, *COMPLEX4_PATH_PARTS)

    def _run():
        nl = CellNetlist(parse_spice_subckt(open(path).read()))
        nl3, pl, w, lws, blocks, orderings = _heuristic_placement(nl)
        r = route_cell(nl3, pl, w, lws, blocks=blocks)
        rep = verify_cell(nl3, pl, r, blocks=blocks) if r.ok else None
        return nl3, pl, w, lws, blocks, orderings, r, rep

    run1 = _run()
    run2 = _run()
    # the speculate report of the engine's exact placement stage
    # (fold -> blocks -> seeds -> euler -> dual-basin refine -> select;
    # variant_classes=True binds the steered refine's cage term)
    nl, lw, eop, eon = _pipeline(open(path).read())
    bp, bn, _bd = sa_refine(eop, eon, nl, lw, cage=True)
    leg_p, leg_n, _lbd = sa_refine(eop, eon, nl, lw, cage=False)
    _op, _on, sel = select_orderings(
        bp, bn, eop, eon, nl, lw,
        candidate_count=DEFAULT_CANDIDATES + 3, variant_classes=True,
        cage=True, legacy_best=(leg_p, leg_n))
    return run1, run2, sel


def test_complex4_selection_is_the_true_view_closer(complex4_chain):
    """THE regression: the speculate selection must pick a true-view
    FEASIBLE cage-free candidate -- var:parallel_phase-flip-both, the
    first closer in pool order (align3 also closes but sits later) --
    never the blocks-less floor winner var:parallel_phase-die-both
    whose own view is full-budget floor 4 with a proven-unwirable
    window."""
    (nl3, pl, w, lws, blocks, orderings, r, rep), _run2, sel = \
        complex4_chain
    del nl3, pl, lws, blocks, orderings
    assert sel["trial_view"] == "blocks"
    assert sel["feasible"] and sel["conflicts"] == 0 and sel["cage"] == 0
    assert sel["kind"] == "var:parallel_phase-flip-both"
    # the closer is picked by TRIAL, in pool order, short-circuiting the
    # scan: every earlier candidate's true-view floor is pinned below
    kinds = [e["kind"] for e in sel["candidates"]]
    floors = dict((e["kind"], e["conflicts"]) for e in sel["candidates"])
    assert kinds == ["best", "flip-both", "die-both", "flip-P", "flip-N",
                     "die-P", "die-N", "seed", "seed-flip-both",
                     "seed-die-both", "best-legacy",
                     "best-legacy-flip-both", "best-legacy-die-both",
                     "var:parallel_phase",
                     "var:parallel_phase-flip-both"]
    assert floors["best"] == 11
    assert floors["flip-both"] == _UNROUTABLE   # build failure (caged)
    assert floors["die-both"] == 4
    assert floors["var:parallel_phase"] == 2
    assert floors["var:parallel_phase-flip-both"] == 0
    # ... and the engine chain closes at the documented width
    assert w == 10 and round(w * GRID_UM, 2) == 1.90
    assert r.ok and r.status_name == "FEASIBLE"
    assert rep is not None and rep.ok()


def test_complex4_chain_is_deterministic_in_process(complex4_chain):
    """Two full chains in the same process: identical width, ordering
    signature, route signature and verify verdict (invariant 9)."""
    run1, run2, _sel = complex4_chain
    _nl3a, _pla, wa, _lwsa, _blocksa, orderings_a, r_a, rep_a = run1
    _nl3b, _plb, wb, _lwsb, _blocksb, orderings_b, r_b, rep_b = run2
    assert wa == wb
    assert ordering_signature(*orderings_a) == \
        ordering_signature(*orderings_b)
    assert route_signature(r_a) == route_signature(r_b)
    assert rep_a is not None and rep_a.ok()
    assert r_a.ok and r_b.ok


def test_complex4_route_and_gds_sanity(complex4_chain, tmp_path):
    """gds sanity at 10 cols = 1.90 um: the closing route emits a clean
    cell (write_cell_gds -> layout_sanity)."""
    from layout_sanity import check_layout
    from bigcell_engine.gds_cells import write_cell_gds

    (nl3, pl, w, lws, blocks, orderings, r, rep), _run2, _sel = \
        complex4_chain
    assert r.ok and rep.ok()
    ordering_p, ordering_n = orderings
    assert [b for b in blocks if b.first.is_p] == list(ordering_p)
    gds = str(tmp_path / "COMPLEX4.gds")
    write_cell_gds(gds, nl3, pl, w, ordering_p, ordering_n, lws,
                   route=r, cell_name="COMPLEX4")
    sanity = check_layout(gds, units_per_um=1.0)
    assert sanity.ok(), sanity.violations


_TV_HASH_HELPER = """\
import hashlib, os, sys
sys.path.insert(0, os.getcwd())
from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from bigcell_engine.engine import _heuristic_placement
from bigcell_engine.place_sa import ordering_signature
from bigcell_engine.route_grid import route_cell, route_signature

path = %r
nl = CellNetlist(parse_spice_subckt(open(path).read()))
nl3, pl, w, lws, blocks, orderings = _heuristic_placement(nl)
r = route_cell(nl3, pl, w, lws, blocks=blocks)
print(w, bool(r.ok), route_signature(r),
      hashlib.sha256(repr(ordering_signature(*orderings)).encode())
      .hexdigest())
"""


def test_complex4_chain_is_byte_stable_across_processes(flow_dir, tmp_path):
    """Cross-process determinism (invariant 9) on the newly closing
    cell: identical width/route/ordering digest under different
    PYTHONHASHSEED values."""
    helper = tmp_path / "tv_complex4_hash_helper.py"
    helper.write_text(_TV_HASH_HELPER
                      % os.path.join(flow_dir, *COMPLEX4_PATH_PARTS))
    digests = set()
    for seed in ("0", "1"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run([sys.executable, str(helper)], cwd=flow_dir,
                              env=env, capture_output=True, text=True,
                              check=True)
        digests.add(proc.stdout.strip().splitlines()[-1])
    assert len(digests) == 1, digests


# --------------------------------------------------------------------------
# CLKBUF1: an honest residual the true view IMPROVES (no silent shift)
# --------------------------------------------------------------------------

def _clkbuf1_sp(flow_dir):
    return _lib_subckt("CLKBUF1", flow_dir)


def test_clkbuf1_true_view_shift_improves_the_residual(flow_dir):
    """CLKBUF1 (16T) does NOT close -- but the true-view trials
    honestly IMPROVE its fallback: the blocks-less trials ranked
    ``var:parallel_phase-legacy`` first (trial floor 13, census-caged,
    width 11, full-budget floor 26); on their own views its floor is 26
    while the steered head ``best`` keeps floor 14 census-free, so the
    (conflicts, cost, index) fallback now returns ``best`` -- width 8
    (1.52 um) and full-budget floor 6 (was 26 at width 11).  Pinning
    the shift: the residual stays a pure negotiation plateau (no
    statically caged gate)."""
    from bigcell_engine.engine import _heuristic_placement
    from bigcell_engine.route_grid import _RouteGrid

    nl = CellNetlist(parse_spice_subckt(_clkbuf1_sp(flow_dir)))
    nl3, pl, w, lws, blocks, orderings = _heuristic_placement(nl)
    r = route_cell(nl3, pl, w, lws, blocks=blocks)
    assert not r.ok
    note = getattr(r, "fail_note", None) or ""
    assert "statically caged" not in note
    _contests, walled = _RouteGrid(nl3, pl, w).structural_diagnosis()
    assert walled == []
    # the shifted-to arrangement: the steered head at width 8
    assert w == 8
    assert ordering_signature(*orderings) == ordering_signature(
        *_tv_clkbuf1_selected_orderings(flow_dir)[0:2])


def _tv_clkbuf1_selected_orderings(flow_dir):
    """The speculate stage's selected orderings for CLKBUF1 at the
    engine's parameters (the selection report's winner)."""
    nl, lw, eop, eon = _pipeline(_clkbuf1_sp(flow_dir))
    bp, bn, _bd = sa_refine(eop, eon, nl, lw, cage=True)
    leg_p, leg_n, _lbd = sa_refine(eop, eon, nl, lw, cage=False)
    op, on, sel = select_orderings(
        bp, bn, eop, eon, nl, lw,
        candidate_count=DEFAULT_CANDIDATES + 3, variant_classes=True,
        cage=True, legacy_best=(leg_p, leg_n))
    assert sel["kind"] == "best" and sel["cage"] == 0
    assert sel["conflicts"] == 14        # trial floor of the steered head
    return op, on


def test_clkbuf1_chain_is_byte_stable_across_processes(flow_dir, tmp_path):
    """Cross-process determinism (invariant 9) on a small library cell
    under the true-view trials.  CLKBUF1 is a LIBRARY cell: its deck has
    no file of its own, so the extracted subckt text is materialised to
    a real temp file -- the helper opens a PATH, not the text (the
    original passed the text and died with FileNotFoundError)."""
    sp = tmp_path / "CLKBUF1.sp"
    sp.write_text(_clkbuf1_sp(flow_dir))
    helper = tmp_path / "tv_clkbuf1_hash_helper.py"
    helper.write_text(_TV_HASH_HELPER % str(sp))
    digests = set()
    for seed in ("0", "1"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run([sys.executable, str(helper)], cwd=flow_dir,
                              env=env, capture_output=True, text=True,
                              check=True)
        digests.add(proc.stdout.strip().splitlines()[-1])
    assert len(digests) == 1, digests
