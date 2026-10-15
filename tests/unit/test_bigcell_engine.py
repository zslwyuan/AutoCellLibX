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
    placement, route, meta = synth_cell(_netlist(INV), exact_budget_s=20.0)
    assert meta["engine"] == "smt-exact"
    assert meta["width_cols"] == 3
    assert abs(meta["width_um"] - 3 * 0.19) < 1e-9
    assert placement                     # Device -> PlacedTransistor
    assert route.ok
    runs = [(a["rung"], a.get("stage"), a["ok"]) for a in meta["attempts"]]
    assert (1, "layout", True) in runs
    assert (1, "routing", True) in runs
    # rung-1 success is its own verification gate
    assert any("verify ok" in (a.get("note") or "")
               for a in meta["attempts"])
    for a in meta["attempts"]:
        assert {"rung", "engine", "ok"} <= set(a)


# --- rung 1 fails -> injected grid router is called ---------------------

def _fail_exact_routing(monkeypatch, status="INFEASIBLE"):
    monkeypatch.setattr(
        eng, "solve_routing",
        lambda *a, **k: eng._failed_route(status))


def test_exact_failure_falls_to_injected_grid_router(monkeypatch):
    _fail_exact_routing(monkeypatch)
    calls = []

    def fake_router(netlist, placement, width_cols, leg_widths):
        calls.append((netlist, placement, width_cols, leg_widths))
        return _FakeRoute(width_cols=7)

    nl = _netlist(NAND2)
    placement, route, meta = synth_cell(nl, exact_budget_s=20.0,
                                        grid_router=fake_router)
    assert meta["engine"] == "bigcell-grid"
    assert route is not None and route.width_cols == 7
    assert meta["width_cols"] == 7
    assert len(calls) == 1
    called_nl, called_pl, width_cols, leg_widths = calls[0]
    assert called_nl is nl
    assert width_cols == real_layout_width(called_pl)
    # the router receives the rung-1 placement and its fold decision
    assert leg_widths == {dev.name: (p.legs, p.leg_width_cols)
                          for dev, p in called_pl.items()}
    # meta records every attempt in order: layout ok, routing failed,
    # grid ok
    runs = [(a["rung"], a.get("stage"), a["ok"]) for a in meta["attempts"]]
    assert runs == [(1, "layout", True), (1, "routing", False),
                    (2, None, True)]


def test_grid_route_returned_unverified_note_present(monkeypatch):
    _fail_exact_routing(monkeypatch)
    meta = synth_cell(_netlist(NAND2), exact_budget_s=20.0,
                      grid_router=lambda *a: _FakeRoute())[2]
    grid_attempt = meta["attempts"][-1]
    assert grid_attempt["rung"] == 2 and grid_attempt["ok"] is True
    assert "verify deferred" in grid_attempt["note"]


# --- rung 2 unavailable / failing variants ------------------------------

def test_grid_stub_not_implemented_is_unavailable(monkeypatch):
    _fail_exact_routing(monkeypatch)

    def stub_router(*a, **k):
        raise NotImplementedError("route_grid.route_cell")

    nl = _netlist(NAND2)
    with pytest.raises(UnsupportedCell) as excinfo:
        synth_cell(nl, exact_budget_s=20.0, grid_router=stub_router)
    meta = excinfo.value.meta
    last = meta["attempts"][-1]
    assert last["rung"] == 2 and last["status"] == "UNAVAILABLE"
    assert "route_grid.route_cell" in last["note"]
    assert meta["engine"] is None
    assert "no engine closed the cell" in excinfo.value.diagnosis
    assert "NAND2" in excinfo.value.diagnosis


def test_no_router_injected_raises_unsupported(monkeypatch):
    _fail_exact_routing(monkeypatch)
    with pytest.raises(UnsupportedCell) as excinfo:
        synth_cell(_netlist(NAND2), exact_budget_s=20.0)
    last = excinfo.value.meta["attempts"][-1]
    assert last["rung"] == 2 and last["status"] == "UNAVAILABLE"
    assert "no router injected" in last["note"]


def test_router_crash_is_recorded_not_raised(monkeypatch):
    _fail_exact_routing(monkeypatch)

    def crashing_router(*a, **k):
        raise RuntimeError("boom")

    with pytest.raises(UnsupportedCell) as excinfo:
        synth_cell(_netlist(NAND2), exact_budget_s=20.0,
                   grid_router=crashing_router)
    last = excinfo.value.meta["attempts"][-1]
    assert last["rung"] == 2 and last["status"] == "ERROR"
    assert "RuntimeError: boom" in last["note"]


def test_grid_route_failure_recorded(monkeypatch):
    _fail_exact_routing(monkeypatch)
    with pytest.raises(UnsupportedCell) as excinfo:
        synth_cell(_netlist(NAND2), exact_budget_s=20.0,
                   grid_router=lambda *a: _FakeRoute(ok=False))
    last = excinfo.value.meta["attempts"][-1]
    assert last["rung"] == 2 and last["ok"] is False
    assert last["status"] == "INFEASIBLE"


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
    assert meta["engine"] == "bigcell-grid"
