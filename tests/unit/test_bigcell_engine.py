"""Unit tests for the bigcell engine ladder (flow/bigcell_engine.engine).

The ladder logic is tested with INJECTED fake routers and, where a rung
must fail, by monkeypatching the rung function in the engine's namespace
-- no CP-SAT solve beyond the tiny INV/NAND2 netlists, no ASTRAN.
"""
import pytest

from bigcell_engine import engine as eng
from bigcell_engine.engine import (EXACT_MAX_NETS, EXACT_MAX_WIDTH_COLS,
                                   UnsupportedCell, exact_routing_boundary,
                                   synth_cell)
from smt_cell_placer import parse_spice_subckt
from smt_engine.layout_model import PlacementSolution, solve_layout
from smt_engine.netlist import CellNetlist

INV = """\
.subckt INV VCC Y A GND
Mp Y A VCC VCC PMOS W=0.5u L=0.05u
Mn Y A GND GND NMOS W=0.5u L=0.05u
.ends INV
"""

NAND2 = """\
.subckt NAND2 VCC Y A B GND
MpA Y A VCC VCC PMOS W=0.5u L=0.05u
MpB VCC B Y VCC PMOS W=0.5u L=0.05u
MnA Y A n1 GND NMOS W=0.5u L=0.05u
MnB n1 B GND GND NMOS W=0.5u L=0.05u
.ends NAND2
"""


def _netlist(sp):
    return CellNetlist(parse_spice_subckt(sp))


def real_layout_width(placement):
    """Width in columns of a placement (max device end)."""
    return max(p.end_col for p in placement.values())


class _FakeRoute(object):
    def __init__(self, width_cols=7, ok=True):
        self.ok = ok
        self.status_name = "OPTIMAL" if ok else "INFEASIBLE"
        self.width_cols = width_cols


# --- the pinned rung-1 boundary (doc section 2.4) -----------------------

def test_boundary_constants_and_logic():
    assert (EXACT_MAX_WIDTH_COLS, EXACT_MAX_NETS) == (14, 12)
    assert exact_routing_boundary(14, 12)[0] is True
    ok, why = exact_routing_boundary(15, 12)
    assert ok is False and "width 15 > 14" in why
    ok, why = exact_routing_boundary(14, 13)
    assert ok is False and "13 nets > 12" in why


# --- rung 1 closes for real (tiny cell, real solve) ---------------------

def test_exact_rung_closes_and_meta_records_attempts():
    """Rung-1 success is a CANDIDATE under the narrowest-closing policy:
    the ladder evaluates the slot chain (rung 3) and returns whichever
    closing result is narrower -- on the inline INV that is the slot
    chain (1 column, 0.575 um) versus the exact IR's 3 columns.  The
    rung-1 attempt stays in the record as the verify-ok candidate."""
    placement, route, meta = synth_cell(_netlist(INV), exact_budget_s=20.0)
    assert meta["engine"] == "bigcell-full"
    assert meta["width_cols"] < 3
    assert meta["width_um"] == meta["width_cols"] * 0.19
    assert placement                     # Device -> PlacedTransistor
    assert route.ok
    runs = [(a["rung"], a.get("stage"), a["ok"]) for a in meta["attempts"]]
    assert (1, "layout", True) in runs
    assert (1, "routing", True) in runs
    # rung-1 success is its own verification gate
    assert any("verify ok" in (a.get("note") or "")
               for a in meta["attempts"])
    # rung 2 skipped: rung 1 already closed this exact placement
    rung2 = [a for a in meta["attempts"] if a["rung"] == 2]
    assert rung2 and rung2[0]["status"] == "SKIPPED"
    for a in meta["attempts"]:
        assert {"rung", "engine", "ok"} <= set(a)


# --- rung 1 fails -> injected grid router is called ---------------------

def _fail_exact_routing(monkeypatch, status="INFEASIBLE"):
    monkeypatch.setattr(
        eng, "solve_routing",
        lambda *a, **k: eng._failed_route(status))


def _disable_rung3(monkeypatch):
    """Silence the rung-3 rescue so rung-2 handling can be pinned."""
    def boom(netlist):
        raise RuntimeError("rung 3 disabled for this test")
    monkeypatch.setattr(eng, "_heuristic_placement", boom)


def _rung_attempt(meta, rung):
    """The first attempt record of ``rung`` (search, not [-1]: rung 3
    appends after rung 2 when it runs)."""
    for a in meta["attempts"]:
        if a["rung"] == rung:
            return a
    raise AssertionError("no rung-%d attempt in %r" % (rung, meta["attempts"]))


def test_exact_failure_falls_to_injected_grid_router(monkeypatch):
    _fail_exact_routing(monkeypatch)
    calls = []

    def fake_router(netlist, placement, width_cols, leg_widths):
        calls.append((netlist, placement, width_cols, leg_widths))
        return _FakeRoute(width_cols=7)

    nl = _netlist(NAND2)
    placement, route, meta = synth_cell(nl, exact_budget_s=20.0,
                                        grid_router=fake_router)
    # the injected router is consulted exactly once and stays
    # verify-deferred; its result is a CANDIDATE -- the ladder returns
    # the narrowest verified closing result, and rung 3's slot chain is
    # narrower than the fake's 7 columns on NAND2
    assert len(calls) == 1
    called_nl, called_pl, width_cols, leg_widths = calls[0]
    assert called_nl is nl
    assert width_cols == real_layout_width(called_pl)
    assert leg_widths == {dev.name: (p.legs, p.leg_width_cols)
                          for dev, p in called_pl.items()}
    grid = _rung_attempt(meta, 2)
    assert grid["ok"] is True and "verify deferred" in grid["note"]
    assert meta["engine"] == "bigcell-full"
    assert meta["width_cols"] <= 7
    runs = [(a["rung"], a.get("stage"), a["ok"]) for a in meta["attempts"]]
    assert runs[0] == (1, "layout", True)
    assert runs[1] == (1, "routing", False)
    assert (2, None, True) in runs


def test_grid_route_returned_unverified_note_present(monkeypatch):
    _fail_exact_routing(monkeypatch)
    meta = synth_cell(_netlist(NAND2), exact_budget_s=20.0,
                      grid_router=lambda *a: _FakeRoute())[2]
    grid_attempt = _rung_attempt(meta, 2)
    assert grid_attempt["rung"] == 2 and grid_attempt["ok"] is True
    assert "verify deferred" in grid_attempt["note"]


# --- rung 2 unavailable / failing variants ------------------------------

def test_grid_stub_not_implemented_is_unavailable(monkeypatch):
    _fail_exact_routing(monkeypatch)
    _disable_rung3(monkeypatch)

    def stub_router(*a, **k):
        raise NotImplementedError("route_grid.route_cell")

    nl = _netlist(NAND2)
    with pytest.raises(UnsupportedCell) as excinfo:
        synth_cell(nl, exact_budget_s=20.0, grid_router=stub_router)
    meta = excinfo.value.meta
    grid = _rung_attempt(meta, 2)
    assert grid["status"] == "UNAVAILABLE"
    assert "route_grid.route_cell" in grid["note"]
    assert meta["engine"] is None
    assert "no engine closed the cell" in excinfo.value.diagnosis
    assert "NAND2" in excinfo.value.diagnosis


def test_default_router_is_real_and_closes_rung2(monkeypatch):
    """grid_router=None resolves to the real route_grid and its route is
    verify-gated inside the ladder.  With the narrowest-closing policy
    the returned cell is rung 3's slot placement (3 cols) -- narrower
    than rung 2's exact-engine placement -- and the rung-2 attempt stays
    in the record as the verify-ok candidate it was."""
    _fail_exact_routing(monkeypatch)
    placement, route, meta = synth_cell(_netlist(NAND2),
                                        exact_budget_s=20.0)
    grid = _rung_attempt(meta, 2)
    assert grid["ok"] is True and grid["note"] == "verify ok"
    assert meta["engine"] == "bigcell-full"
    assert meta["width_cols"] == 2          # the slot chain's NAND2 width
    assert route.width_cols >= real_layout_width(placement)


def test_rung3_closes_when_rung2_disabled(monkeypatch):
    """The full heuristic placement chain + grid router rescues a cell
    whose exact route and rung-2 offering were both unavailable.

    CLOSED (doc/BIGCELL_SLOT_GEOMETRY.md section 8 adapted in
    route_grid): the router now runs on the slot geometry -- diffusion
    terminals on the true member EDGE columns (die view, smt_engine
    die_view), every slot of a multi-region net exposed, the grid on the
    edge axis (member columns + the right edge column), and gate-only
    nets crossed on the poly layer.  The inline NAND2's slot placement
    (width 2 vs the exact engine's 6) routes FEASIBLE on the first
    negotiation attempt and verifies clean inside the ladder.
    """
    _fail_exact_routing(monkeypatch)
    placement, route, meta = synth_cell(_netlist(NAND2),
                                        exact_budget_s=20.0,
                                        grid_router=False)
    assert meta["engine"] == "bigcell-full"
    assert route.ok and route.status_name == "FEASIBLE"
    assert route.width_cols >= real_layout_width(placement)
    rung3 = [a for a in meta["attempts"] if a["rung"] == 3]
    # the placement stage is fine (the slot chain works)
    placement_attempts = [a for a in rung3 if a.get("stage") == "placement"]
    assert placement_attempts and placement_attempts[-1]["ok"] is True
    # the routing stage closed with a clean verification
    routing = [a for a in rung3 if a.get("stage") == "routing"]
    assert routing and routing[-1]["ok"] is True
    assert routing[-1]["note"] == "verify ok"


def test_rung3_placement_failure_is_recorded(monkeypatch):
    _fail_exact_routing(monkeypatch)
    _disable_rung3(monkeypatch)
    with pytest.raises(UnsupportedCell) as excinfo:
        synth_cell(_netlist(NAND2), exact_budget_s=20.0,
                   grid_router=False)
    meta = excinfo.value.meta
    full = _rung_attempt(meta, 3)
    assert full["stage"] == "placement" and full["status"] == "ERROR"
    assert "rung 3 disabled" in full["note"]
    assert meta["engine"] is None


def test_router_crash_is_recorded_not_raised(monkeypatch):
    _fail_exact_routing(monkeypatch)
    _disable_rung3(monkeypatch)

    def crashing_router(*a, **k):
        raise RuntimeError("boom")

    with pytest.raises(UnsupportedCell) as excinfo:
        synth_cell(_netlist(NAND2), exact_budget_s=20.0,
                   grid_router=crashing_router)
    meta = excinfo.value.meta
    grid = _rung_attempt(meta, 2)
    assert grid["status"] == "ERROR"
    assert "RuntimeError: boom" in grid["note"]


def test_grid_route_failure_recorded(monkeypatch):
    _fail_exact_routing(monkeypatch)
    _disable_rung3(monkeypatch)
    with pytest.raises(UnsupportedCell) as excinfo:
        synth_cell(_netlist(NAND2), exact_budget_s=20.0,
                   grid_router=lambda *a: _FakeRoute(ok=False))
    meta = excinfo.value.meta
    grid = _rung_attempt(meta, 2)
    assert grid["ok"] is False
    assert grid["status"] == "INFEASIBLE"


# --- layout failure and the boundary skip -------------------------------

def test_layout_failure_skips_grid_router(monkeypatch):
    monkeypatch.setattr(
        eng, "solve_layout",
        lambda *a, **k: PlacementSolution("UNKNOWN", None, None, {}, 0))

    def must_not_run(*a, **k):
        raise AssertionError("no placement -> no later rung")

    with pytest.raises(UnsupportedCell) as excinfo:
        synth_cell(_netlist(NAND2), exact_budget_s=1.0,
                   grid_router=must_not_run)
    meta = excinfo.value.meta
    assert len(meta["attempts"]) == 1
    assert meta["attempts"][0]["rung"] == 1
    assert meta["attempts"][0]["stage"] == "layout"
    assert meta["attempts"][0]["ok"] is False
    assert "UNKNOWN" in excinfo.value.diagnosis


def test_boundary_skips_exact_routing_but_grid_runs(monkeypatch):
    nl = _netlist(NAND2)
    real = solve_layout(nl, time_limit_s=15)
    wide = PlacementSolution("OPTIMAL", 20, 20 * 0.19, real.devices,
                             real.aligned)
    monkeypatch.setattr(eng, "solve_layout", lambda *a, **k: wide)

    def must_not_route(*a, **k):
        raise AssertionError("exact routing must be skipped beyond the "
                             "boundary")

    monkeypatch.setattr(eng, "solve_routing", must_not_route)
    called = []

    def fake_router(netlist, placement, width_cols, leg_widths):
        called.append(width_cols)
        return _FakeRoute(width_cols=20)

    placement, route, meta = synth_cell(nl, exact_budget_s=5,
                                        grid_router=fake_router)
    assert called == [20]
    skipped = [a for a in meta["attempts"] if a.get("status") == "SKIPPED"]
    assert len(skipped) == 1
    assert skipped[0]["rung"] == 1 and skipped[0]["stage"] == "routing"
    assert "width 20 > 14" in skipped[0]["note"]
    # the ladder returns the narrowest verified closing result: the fake
    # router's 20-column candidate loses to rung 3's slot placement
    assert meta["engine"] == "bigcell-full"


# --- rungs 2.5 / 3.5: the exact engine as a window fixer ----------------

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


def test_window_fix_never_fires_for_injected_routers(monkeypatch):
    """Rungs 2.5/3.5 respond to the REAL router's plateau; an injected
    router is test scaffolding with a verify-deferred contract, not a
    failure to fix."""
    _fail_exact_routing(monkeypatch)
    meta = synth_cell(_netlist(NAND2), exact_budget_s=20.0,
                      grid_router=lambda *a: _FakeRoute(ok=False))[2]
    assert not [a for a in meta["attempts"] if a["rung"] == 2.5]
    assert not [a for a in meta["attempts"] if a["rung"] == 3.5]


def test_rung25_window_close_via_jump_capacity(monkeypatch):
    """A real-router failure at route width <= WINDOW_MAX_COLS gets a
    WHOLE-CELL window (the route vocabulary includes the trailing
    edge-escape column, and a whole-cell window needs no plateau
    state) -- under the jump-M2 capacity the exact solve closes NAND2
    at rung 2.5."""
    import bigcell_engine.route_grid as rg

    def failing_route_cell(netlist, placement, width_cols,
                           leg_widths, blocks=None):
        width = max(width_cols,
                    max(p.end_col for p in placement.values())) + 1
        return _failed_shell(
            width, "no conflict-free routing after 4 attempts (best 2 "
                   "conflicts at attempt 2; unresolved: Y)")

    monkeypatch.setattr(eng, "solve_routing",
                        lambda *a, **k: eng._failed_route("INFEASIBLE"))
    monkeypatch.setattr(rg, "route_cell", failing_route_cell)
    placement, route, meta = synth_cell(_netlist(NAND2),
                                        exact_budget_s=20.0)
    # the ladder closes through rung 3.5 (the slot-chain placement's
    # whole-cell window); rung 2.5's window solve on the exact-engine
    # IR stays INFEASIBLE -- recorded, not a regression
    assert meta["engine"] == "bigcell-full+window-fix"
    assert route.ok
    fix = [a for a in meta["attempts"] if a["rung"] == 3.5][-1]
    assert fix["ok"] is True and fix["status"] == "OPTIMAL"


def test_rung25_honesty_guard_skips_unreproducible_plateau(monkeypatch):
    """A route width ABOVE WINDOW_MAX_COLS forces a strict sub-window,
    and the honesty guard refuses a plateau the deterministic re-run
    does not reproduce (NAND2 actually routes -- no plateau to fix, no
    moving target).  Nothing closes; the refusals are recorded."""
    import bigcell_engine.route_grid as rg

    def failing_route_cell(netlist, placement, width_cols,
                           leg_widths, blocks=None):
        width = max(width_cols,
                    max(p.end_col for p in placement.values())) + 11
        return _failed_shell(
            width, "no conflict-free routing after 4 attempts (best 2 "
                   "conflicts at attempt 2; unresolved: Y)")

    monkeypatch.setattr(eng, "solve_routing",
                        lambda *a, **k: eng._failed_route("INFEASIBLE"))
    monkeypatch.setattr(rg, "route_cell", failing_route_cell)
    with pytest.raises(eng.UnsupportedCell) as excinfo:
        synth_cell(_netlist(NAND2), exact_budget_s=20.0)
    meta = excinfo.value.meta
    for rung in (2.5, 3.5):
        att = [a for a in meta["attempts"] if a["rung"] == rung]
        assert att and att[-1]["status"] == "SKIPPED"
        assert "not reproduced" in att[-1]["note"]
