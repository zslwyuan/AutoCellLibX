"""Unit tests for the window-fixing mode of the exact engine
(smt_engine.route_model.solve_window_routing) and its ladder rungs
2.5 / 3.5 (flow/bigcell_engine.engine).

The window fixer is doc/STAGE3_BIGCELL_ENGINE.md section 2.4 rung 1's
narrowed role: after the negotiated-congestion router leaves a local
region conflicted, the exact model is re-run on a <=12-column window
with everything outside fixed as blockages, and the merged result is
verify-gated like every other rung.  The tests pin:

- the whole-cell window (a routable slot placement closes and verifies);
- the sub-window merge (outside-window geometry is preserved byte for
  byte, the window is re-routed, the merge verifies clean);
- the sound tie machinery (a straddling net must reach its kept outside
  part through a junction the verify BFS actually joins -- exercised by
  the sub-window merge closing on the straddling output net);
- honest refusals: INFEASIBLE windows are decisive evidence (the region
  is exactly-unroutable -- the blocker is the placement/vocabulary, not
  the router's heuristic), never silently shipped;
- determinism (AGENTS.md invariants 8/9): identical inputs give
  identical merged routes in-process and across PYTHONHASHSEED.
"""
import os
import subprocess
import sys

import pytest

from bigcell_engine import engine as eng
from bigcell_engine.engine import (parse_fail_nets, synth_cell,
                                   window_region)
from bigcell_engine.route_grid import route_cell, route_signature
from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from smt_engine.route_model import solve_window_routing
from smt_engine.verify import verify_cell

NAND2 = """\
.subckt NAND2 VCC Y A B GND
MpA Y A VCC VCC PMOS W=0.5u L=0.05u
MpB VCC B Y VCC PMOS W=0.5u L=0.05u
MnA Y A n1 GND NMOS W=0.5u L=0.05u
MnB n1 B GND GND NMOS W=0.5u L=0.05u
.ends NAND2
"""

COMPLEX0_NOTE = (
    "no conflict-free routing after 8000 attempts (best 3 conflicts at "
    "attempt 309; unresolved: cl0#B, cl0#Y, cl1#Y)")


def _netlist(sp):
    return CellNetlist(parse_spice_subckt(sp))


@pytest.fixture(scope="module")
def nand2_slot():
    from bigcell_engine.engine import _heuristic_placement
    nl3, pl, w, lws, blocks, _orderings = _heuristic_placement(
        _netlist(NAND2))
    return nl3, pl, w, lws, blocks


@pytest.fixture(scope="module")
def complex0_slot(flow_dir):
    """The engine._heuristic_placement chain on the real ctrl/COMPLEX0
    (the acceptance cell: the router plateaus at 3 conflicts and the
    window fixer proves the placement exactly-unroutable)."""
    from bigcell_engine.engine import _heuristic_placement
    sp = open(os.path.join(str(flow_dir), "outputs", "ctrl",
                           "COMPLEX0.sp")).read()
    nl3, pl, w, lws, blocks, _orderings = _heuristic_placement(_netlist(sp))
    return nl3, pl, w, lws, blocks


def _failed_shell(width, note):
    """A route_grid-shaped failure carrying the public fail_note."""
    from smt_engine.route_model import BAR_LEVELS, RouteResult
    result = RouteResult(
        "UNKNOWN", [None] * width, [None] * width,
        [0] * width, [0] * width, [BAR_LEVELS - 1] * width,
        [BAR_LEVELS - 1] * width, {}, {}, {}, {},
        [False] * width, [False] * width, width, 0, 0, 0, 0, 0)
    result.fail_note = note
    return result


def _failing_router(note):
    def router(netlist, placement, width_cols, leg_widths):
        width = max(width_cols,
                    max(p.end_col for p in placement.values())) + 1
        return _failed_shell(width, note)
    return router


# --- the window fixer itself (smt_engine.route_model) -------------------

def test_whole_cell_window_closes_and_verifies(nand2_slot):
    nl3, pl, w, _lws, blocks = nand2_slot
    route_width = w + 1                     # the slot edge axis
    fix = solve_window_routing(nl3, pl, route_width, (0, route_width),
                               blocks=blocks)
    assert fix.route is not None
    assert fix.status_name in ("OPTIMAL", "FEASIBLE")
    assert fix.window == (0, route_width)
    report = verify_cell(nl3, pl, fix.route, blocks=blocks)
    assert report.ok(), report.violations[:4]


def test_subwindow_merge_preserves_outside_and_verifies(nand2_slot):
    nl3, pl, w, lws, blocks = nand2_slot
    good = route_cell(nl3, pl, w, lws)
    assert good.ok
    window = (1, w + 1)                     # everything but column 0
    fix = solve_window_routing(nl3, pl, good.width_cols, window,
                               partial=good, blocks=blocks)
    assert fix.route is not None, fix.note
    merged = fix.route
    report = verify_cell(nl3, pl, merged, blocks=blocks)
    assert report.ok(), report.violations[:4]
    # the untouched outside region is byte-identical to the partial's
    for c in range(window[0]):
        assert merged.col_owner_n[c] == good.col_owner_n[c]
        assert merged.col_owner_p[c] == good.col_owner_p[c]
        assert merged.lo_n[c] == good.lo_n[c]
        assert merged.hi_n[c] == good.hi_n[c]
        assert merged.lo_p[c] == good.lo_p[c]
        assert merged.hi_p[c] == good.hi_p[c]
    for (t, c), net in good.hseg.items():
        if (c < window[0]):
            assert merged.hseg.get((t, c)) == net
    # the window columns were re-derived by the exact model
    assert merged.width_cols == good.width_cols


def test_window_rejects_oversized_and_invalid():
    fix = solve_window_routing(None, None, 20, (0, 13))
    assert fix.route is None and fix.status_name == "SKIPPED"
    assert "12" in fix.note
    fix = solve_window_routing(None, None, 5, (3, 3))
    assert fix.route is None and fix.status_name == "SKIPPED"


def test_single_column_window_refuses_uncrossable_gate(nand2_slot):
    # a one-column window has no segment slots: the gate whose stripe
    # sits in it can never be crossed -- an honest INFEASIBLE, the same
    # empty-clause refusal the exact engine emits for the placement
    nl3, pl, w, _lws, blocks = nand2_slot
    fix = solve_window_routing(nl3, pl, w + 1, (1, 2), blocks=blocks)
    assert fix.route is None
    assert fix.status_name == "INFEASIBLE"
    assert "exactly-unroutable" in fix.note


def test_complex0_whole_cell_window_is_exactly_unroutable(complex0_slot):
    """ACCEPTANCE (doc section 2.4 rung 1): ctrl/COMPLEX0's W=6 slot
    placement -- the router's 8000-attempt plateau region IS the whole
    cell (7 route columns <= 12), and the window fixer proves it
    exactly-unroutable: the blocker is the placement/vocabulary (the
    single T3 N<->P crossover, walled by the power stripes), not the
    router's heuristic.  Decisive evidence in sub-seconds."""
    nl3, pl, w, _lws, blocks = complex0_slot
    route_width = w + 1
    assert route_width <= 12
    fix = solve_window_routing(nl3, pl, route_width, (0, route_width),
                               blocks=blocks)
    assert fix.route is None
    assert fix.status_name == "INFEASIBLE"
    assert "exactly-unroutable" in fix.note
    assert fix.window == (0, route_width)


# --- determinism (AGENTS.md invariants 8/9) -----------------------------

def _signature(sp):
    """Whole-pipeline merged-route signature (netlist parse -> slot
    placement -> whole-cell window solve -> route_signature)."""
    from bigcell_engine.engine import _heuristic_placement
    nl3, pl, w, _lws, blocks, _orderings = _heuristic_placement(
        _netlist(sp))
    route_width = w + 1
    fix = solve_window_routing(nl3, pl, route_width, (0, route_width),
                               blocks=blocks)
    assert fix.route is not None
    return route_signature(fix.route)


def test_determinism_in_process():
    first = _signature(NAND2)
    second = _signature(NAND2)
    assert first == second


def test_determinism_cross_process_hash_seed(repo_dir):
    """Identical inputs -> identical merged route across processes with
    different PYTHONHASHSEED (invariant 9)."""
    child = (
        "import sys, os\n"
        "repo = {repo!r}\n"
        "sys.path.insert(0, os.path.join(repo, 'flow'))\n"
        "sys.path.insert(0, repo)\n"
        "from tests.unit.test_window_fixer import _signature, NAND2\n"
        "print(_signature(NAND2))\n"
    ).format(repo=str(repo_dir))
    outs = []
    for seed in ("0", "1"):
        env = dict(os.environ)
        env["PYTHONHASHSEED"] = seed
        proc = subprocess.run([sys.executable, "-c", child], env=env,
                              capture_output=True, text=True, timeout=300)
        assert proc.returncode == 0, proc.stderr[-2000:]
        outs.append(proc.stdout.strip())
    assert outs[0] and outs[0] == outs[1], outs


# --- the fail-note parser and the window derivation ---------------------

def test_parse_fail_nets_forms():
    stagnation = ("no conflict-free routing after 8000 attempts (best 3 "
                  "conflicts at attempt 309; unresolved: cl0#B, cl0#Y, "
                  "cl1#Y)")
    structural = stagnation + (
        "); structural: corridor T3 over-subscribed at col 1: cl0#B "
        "(gate contact) vs cl1#Y)")
    assert parse_fail_nets(structural) == ["cl0#B", "cl0#Y", "cl1#Y"]
    assert parse_fail_nets(stagnation) == ["cl0#B", "cl0#Y", "cl1#Y"]
    assert parse_fail_nets(
        "impossible to find a path for net cl2#a_2_54#") == \
        ["cl2#a_2_54#"]
    assert parse_fail_nets(
        "terminal clash at ('M1', 4, 8): cl3#Y and VCC") == \
        ["cl3#Y", "VCC"]
    assert parse_fail_nets("...unresolved: -)") == []
    assert parse_fail_nets(None) == []
    assert parse_fail_nets("") == []


def test_window_region_pads_and_caps():
    window, _reason = window_region({0, 3, 6}, 7)
    assert window == (0, 7)                 # padded, clipped to the grid
    window, _reason = window_region({4, 5}, 20)
    assert window == (3, 7)
    window, reason = window_region(set(range(30)), 40)
    assert window is None
    assert "31 columns > 12" in reason
    window, reason = window_region(set(), 7)
    assert window is None and "no access columns" in reason


# --- the ladder rungs (flow/bigcell_engine.engine) ----------------------

def test_rung35_window_fix_closes_when_router_fails(monkeypatch,
                                                    nand2_slot):
    """The full window-fix rung end to end: the injected router fails
    with the plateau's honest fail_note, the engine derives the window
    from the conflicted net's access columns (whole cell here), the
    exact model re-routes it, and the verify gate closes the cell."""
    monkeypatch.setattr(eng, "solve_routing",
                        lambda *a, **k: eng._failed_route("INFEASIBLE"))
    monkeypatch.setattr(eng, "_default_grid_router",
                        lambda: _failing_router(
                            "no conflict-free routing after 5 attempts "
                            "(best 2 conflicts at attempt 3; unresolved: "
                            "Y)"))
    placement, route, meta = synth_cell(_netlist(NAND2),
                                        exact_budget_s=20.0)
    assert meta["engine"] == "bigcell-full+window-fix"
    assert route.ok
    runs = [(a["rung"], a["engine"], a["ok"]) for a in meta["attempts"]]
    assert (3.5, "bigcell-window-fix", True) in runs
    fix_attempt = [a for a in meta["attempts"] if a["rung"] == 3.5][-1]
    assert fix_attempt["window"] == [0, 3]
    assert "verified" in fix_attempt["note"]
    # the merged route verifies against the same placement/blocks view
    nl3, pl, _w, _lws, blocks = nand2_slot
    report = verify_cell(nl3, pl, route, blocks=blocks)
    assert report.ok(), report.violations[:4]


def test_rung35_infeasible_window_is_decisive_evidence(
        monkeypatch, complex0_slot, flow_dir):
    """An exactly-unroutable window is an honest INFEASIBLE record: the
    ladder's diagnosis carries the CP-SAT proof instead of a heuristic
    stall, and no unverified route is merged."""
    nl3, pl, w, _lws, blocks = complex0_slot
    sp = open(os.path.join(str(flow_dir), "outputs", "ctrl",
                           "COMPLEX0.sp")).read()
    monkeypatch.setattr(eng, "solve_routing",
                        lambda *a, **k: eng._failed_route("INFEASIBLE"))
    monkeypatch.setattr(eng, "_default_grid_router",
                        lambda: _failing_router(COMPLEX0_NOTE))
    with pytest.raises(eng.UnsupportedCell) as excinfo:
        synth_cell(_netlist(sp), exact_budget_s=30.0)
    meta = excinfo.value.meta
    fixes = [a for a in meta["attempts"] if a["rung"] == 3.5]
    assert fixes and fixes[-1]["ok"] is False
    assert fixes[-1]["status"] == "INFEASIBLE"
    assert fixes[-1]["window"] == [0, w + 1]
    assert "exactly-unroutable" in excinfo.value.diagnosis
    assert "blocker is the placement/vocabulary" in excinfo.value.diagnosis


def test_rung35_skipped_when_note_names_no_nets(monkeypatch):
    monkeypatch.setattr(eng, "solve_routing",
                        lambda *a, **k: eng._failed_route("INFEASIBLE"))
    monkeypatch.setattr(eng, "_default_grid_router",
                        lambda: _failing_router(None))
    with pytest.raises(eng.UnsupportedCell) as excinfo:
        synth_cell(_netlist(NAND2), exact_budget_s=20.0)
    meta = excinfo.value.meta
    fixes = [a for a in meta["attempts"] if a["rung"] == 3.5]
    assert fixes and fixes[-1]["status"] == "SKIPPED"
    assert "no conflicted nets" in fixes[-1]["note"]
