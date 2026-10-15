"""Big-cell engine orchestration: the ladder between the exact engine and
ASTRAN (stage 3, doc/STAGE3_BIGCELL_ENGINE.md section 2.4 / section 5).

Ladder per cell:

- **rung 1 -- smt-exact** (exists, in flow/smt_engine): solve_layout +
  solve_routing(metal2=True, single worker) + verify_cell.  Attempted only
  inside the measured boundary (doc section 2.4): the placement is at most
  ``EXACT_MAX_WIDTH_COLS`` columns wide AND the netlist has at most
  ``EXACT_MAX_NETS`` signal nets -- beyond that the O(N^2*T*W)
  crossing-safety constraints blow past the budget, so routing is skipped
  without burning it.  The layout solve always runs: every later rung
  consumes its placement.
- **rung 2 -- bigcell-grid**: the negotiated-congestion router
  (flow/bigcell_engine/route_grid.py, the GraphRouter port) on the
  exact-engine placement.  By default the real router runs and its route
  is verify-gated inside the ladder; an explicitly injected callable
  replaces it (its route stays "verify deferred" -- the injected contract
  is for tests), ``False`` disables the rung, and a stub raising
  NotImplementedError is treated as "unavailable", not as a cell failure
  cause of its own.
- **rung 3 -- bigcell-full**: the heuristic placement chain
  (netlist_ext.fold_devices -> build_bigcell_blocks -> row_seeds ->
  place_euler -> place_sa -> geometry.layout_cell) routed by the same
  grid router.  This is the doc section 2.2 composition and the path for
  cells the exact placement cannot serve (big/irregular).  Its placement
  is factored as :func:`_heuristic_placement` so tests can stub it.

Nothing here re-implements a solve: this module only sequences rungs,
records every attempt in ``meta`` (the benchmark report's provenance),
and raises :class:`UnsupportedCell` with a diagnosis (which rung failed,
why) when no rung closes the cell.  ASTRAN stays the per-cell fallback
behind this ladder until the doc section 4 gates are met.

Determinism: the rungs are the existing deterministic engines (single
CP-SAT worker, invariant 9); no wall-clock logic is added here -- the
budgets are passed straight to the solvers as their documented safety
nets.  Meta records rounded wall seconds for the report only; they never
feed back into results.
"""

import time

from smt_engine.layout_model import solve_layout
from smt_engine.route_model import solve_routing
from smt_engine.verify import verify_cell

GRID_UM = 0.19                    # the placement grid (invariant 2)

#: rung-1 boundary, doc section 2.4: exact routing is attempted only when
#: W <= 14 AND N <= 12 (W = placement width in 0.19 um columns, N = signal
#: nets); beyond it, routing is skipped without burning the budget.
EXACT_MAX_WIDTH_COLS = 14
EXACT_MAX_NETS = 12

_ENG_EXACT = "smt-exact"
_ENG_GRID = "bigcell-grid"
_ENG_FULL = "bigcell-full"


def _default_grid_router():
    """The production rung-2/3 router, resolved lazily for testability."""
    from .route_grid import route_cell
    return route_cell


def _heuristic_placement(netlist):
    """Rung-3 placement: fold -> blocks -> seeds -> euler -> SA -> columns.

    Returns (netlist3, placements, width_cols, leg_widths) where
    ``netlist3`` is the (possibly fold-expanded) netlist the placement is
    expressed against.  Deterministic; raises on structural failure.
    """
    from . import geometry
    from .netlist_ext import (build_bigcell_blocks, fold_devices,
                              row_seeds)
    from .place_euler import euler_orderings
    from .place_sa import sa_refine

    netlist3, leg_widths = fold_devices(netlist)
    blocks = build_bigcell_blocks(netlist3)
    seeds = row_seeds(blocks, leg_widths)
    ordering_p, ordering_n = euler_orderings(seeds, leg_widths)
    ordering_p, ordering_n, _cost = sa_refine(
        ordering_p, ordering_n, netlist3, leg_widths)
    placements, width_cols = geometry.layout_cell(
        ordering_p, ordering_n, leg_widths)
    return netlist3, placements, width_cols, leg_widths


class UnsupportedCell(Exception):
    """No rung of the ladder closed the cell.

    ``diagnosis`` says which rung failed and why; ``meta`` carries the
    full per-attempt record so callers (benchmark, queue) can report
    provenance even when the call raised.
    """

    def __init__(self, diagnosis, meta=None):
        super().__init__(diagnosis)
        self.diagnosis = diagnosis
        self.meta = meta if meta is not None else {}


def exact_routing_boundary(width_cols, net_count,
                           max_width_cols=EXACT_MAX_WIDTH_COLS,
                           max_nets=EXACT_MAX_NETS):
    """(allowed, reason) for offering one placement to rung-1 routing.

    Pure function of the two numbers, so the boundary is pinned and
    unit-testable (doc section 2.4: "attempted only when W <= 14 and
    N <= 12 ... beyond that it is skipped without burning the budget").
    """
    if (width_cols > max_width_cols):
        return False, ("width %d > %d columns" % (width_cols,
                                                  max_width_cols))
    if (net_count > max_nets):
        return False, ("%d nets > %d" % (net_count, max_nets))
    return True, "width %d <= %d and %d nets <= %d" % (
        width_cols, max_width_cols, net_count, max_nets)


def _attempt(meta, rung, engine, ok, status=None, stage=None, note=None,
             seconds=None):
    entry = {"rung": rung, "engine": engine, "ok": bool(ok)}
    if (status is not None):
        entry["status"] = status
    if (stage is not None):
        entry["stage"] = stage
    if (note is not None):
        entry["note"] = note
    if (seconds is not None):
        entry["seconds"] = round(seconds, 1)
    meta["attempts"].append(entry)
    return entry


def _diagnosis(cell_name, attempts):
    parts = []
    for a in attempts:
        if (a.get("ok")):
            continue
        piece = "rung%d %s" % (a["rung"], a["engine"])
        if (a.get("stage")):
            piece += "/%s" % a["stage"]
        piece += " %s" % a.get("status", "FAILED")
        if (a.get("note")):
            piece += " (%s)" % a["note"]
        parts.append(piece)
    return "%s: no engine closed the cell [%s]" % (cell_name, "; ".join(parts))


def _leg_widths_from_placement(placement):
    """{device name: (legs, leg_width_cols)} -- route_grid's fold input."""
    return {dev.name: (p.legs, p.leg_width_cols)
            for dev, p in placement.items()}


def _failed_route(status_name):
    """A RouteResult-shaped failure, mirroring solve_routing's own."""
    from smt_engine.route_model import RouteResult
    return RouteResult(status_name, [], [], [], [], [], [],
                       {}, {}, {}, {}, [], [], 0, 0, 0, 0, 0, 0)


def synth_cell(netlist, exact_budget_s=60.0, grid_budget_s=120.0,
               grid_router=None):
    """Lay out + route one cell; return (placement, route, meta).

    ``netlist`` is a smt_engine CellNetlist; the returned placement maps
    Device -> PlacedTransistor (smt_engine's own IR) and the route is
    RouteResult-compatible, so smt_engine/gds.py, verify.py and the
    benchmark consume the output unchanged.

    ``meta`` records every attempt (rung, engine, stage, status, verify
    outcome, seconds) and the winning engine/width; on failure
    :class:`UnsupportedCell` is raised with the same ``meta`` attached.

    Rung 1 verifies its own route (verify_cell must be clean before the
    rung counts as closed).  Rung 2's route is returned unverified --
    verification is the caller's continuous-verification gate (the
    benchmark runs verify_cell on every produced cell); the attempt
    record marks it accordingly.

    ``grid_budget_s`` is recorded in meta and reserved for the real
    route_grid budget; the injected router's signature is fixed at
    (netlist, placement, width_cols, leg_widths).
    """
    cell_name = getattr(getattr(netlist, "subckt", None), "subckt_name",
                        "?")
    meta = {
        "cell": cell_name,
        "engine": None,
        "width_cols": None,
        "width_um": None,
        "exact_budget_s": exact_budget_s,
        "grid_budget_s": grid_budget_s,
        "attempts": [],
    }

    # --- rung 1, stage layout: every rung needs a placement -------------
    t0 = time.time()
    try:
        layout = solve_layout(netlist, time_limit_s=exact_budget_s)
    except Exception as exc:                       # noqa: BLE001
        _attempt(meta, 1, _ENG_EXACT, False, status="ERROR", stage="layout",
                 note="%s: %s" % (type(exc).__name__, exc),
                 seconds=time.time() - t0)
        raise UnsupportedCell(_diagnosis(cell_name, meta["attempts"]),
                              meta=meta) from exc
    if (layout.width_cols is None):
        _attempt(meta, 1, _ENG_EXACT, False, status=layout.status_name,
                 stage="layout",
                 note="no placement within %gs" % exact_budget_s,
                 seconds=time.time() - t0)
        raise UnsupportedCell(_diagnosis(cell_name, meta["attempts"]),
                              meta=meta)
    _attempt(meta, 1, _ENG_EXACT, True, status=layout.status_name,
             stage="layout", seconds=time.time() - t0)

    net_count = len(netlist.signal_nets())
    meta["nets"] = net_count
    leg_widths = _leg_widths_from_placement(layout.devices)

    # --- rung 1, stage routing: only inside the measured boundary -------
    allowed, reason = exact_routing_boundary(layout.width_cols, net_count)
    if (not allowed):
        _attempt(meta, 1, _ENG_EXACT, False, status="SKIPPED",
                 stage="routing", note=reason)
    else:
        t0 = time.time()
        try:
            route = solve_routing(netlist, layout.devices, metal2=True,
                                  time_limit_s=exact_budget_s)
        except Exception as exc:                   # noqa: BLE001
            _attempt(meta, 1, _ENG_EXACT, False, status="ERROR",
                     stage="routing",
                     note="%s: %s" % (type(exc).__name__, exc),
                     seconds=time.time() - t0)
            route = None
        if (route is not None):
            if (not route.ok):
                _attempt(meta, 1, _ENG_EXACT, False,
                         status=getattr(route, "status_name", "UNKNOWN"),
                         stage="routing", seconds=time.time() - t0)
            else:
                try:
                    report = verify_cell(netlist, layout.devices, route)
                except Exception as exc:           # noqa: BLE001
                    report = None
                    vnote = "verify raised %s: %s" % (
                        type(exc).__name__, exc)
                else:
                    vnote = None
                if (report is not None and report.ok()):
                    _attempt(meta, 1, _ENG_EXACT, True,
                             status=getattr(route, "status_name"),
                             stage="routing", note="verify ok",
                             seconds=time.time() - t0)
                    meta["engine"] = _ENG_EXACT
                    meta["width_cols"] = layout.width_cols
                    meta["width_um"] = layout.width_cols * GRID_UM
                    return layout.devices, route, meta
                if (vnote is None):
                    vnote = "verify failed: %s" % (
                        report.violations[:2] if report else [])
                _attempt(meta, 1, _ENG_EXACT, False,
                         status=getattr(route, "status_name"),
                         stage="routing", note=vnote,
                         seconds=time.time() - t0)

    # --- rung 2: the grid router on the exact-engine placement ----------
    # grid_router: None = the real route_grid (verify-gated here);
    # False = explicitly disabled; callable = injected (verify deferred).
    using_real_router = grid_router is None
    if (grid_router is False):
        _attempt(meta, 2, _ENG_GRID, False, status="UNAVAILABLE",
                 note="router disabled")
    elif (grid_router is not None and not callable(grid_router)):
        _attempt(meta, 2, _ENG_GRID, False, status="UNAVAILABLE",
                 note="injected router is not callable")
    else:
        router = grid_router if grid_router is not None \
            else _default_grid_router()
        t0 = time.time()
        try:
            route2 = router(netlist, layout.devices, layout.width_cols,
                            leg_widths)
        except NotImplementedError as exc:
            _attempt(meta, 2, _ENG_GRID, False, status="UNAVAILABLE",
                     note=str(exc) or "router stub", seconds=time.time() - t0)
        except Exception as exc:                   # noqa: BLE001
            _attempt(meta, 2, _ENG_GRID, False, status="ERROR",
                     note="%s: %s" % (type(exc).__name__, exc),
                     seconds=time.time() - t0)
        else:
            if (not getattr(route2, "ok", True)):
                _attempt(meta, 2, _ENG_GRID, False,
                         status=getattr(route2, "status_name", "UNKNOWN"),
                         note=getattr(route2, "fail_note", None),
                         seconds=time.time() - t0)
            else:
                vnote = "verify deferred to the caller"
                if (using_real_router):
                    try:
                        report2 = verify_cell(netlist, layout.devices,
                                              route2)
                    except Exception as exc:       # noqa: BLE001
                        report2 = None
                        vnote = "verify raised %s: %s" % (
                            type(exc).__name__, exc)
                    if (report2 is None or not report2.ok()):
                        if (vnote == "verify deferred to the caller"):
                            vnote = "verify failed: %s" % (
                                report2.violations[:2] if report2 else [])
                        _attempt(meta, 2, _ENG_GRID, False,
                                 status=getattr(route2, "status_name",
                                                "UNKNOWN"),
                                 note=vnote, seconds=time.time() - t0)
                        route2 = None
                    else:
                        vnote = "verify ok"
                if (route2 is not None):
                    width_cols = getattr(route2, "width_cols",
                                         layout.width_cols)
                    _attempt(meta, 2, _ENG_GRID, True,
                             status=getattr(route2, "status_name", "OK"),
                             note=vnote, seconds=time.time() - t0)
                    meta["engine"] = _ENG_GRID
                    meta["width_cols"] = width_cols
                    meta["width_um"] = width_cols * GRID_UM
                    return layout.devices, route2, meta

    # --- rung 3: heuristic placement chain + the grid router ------------
    t0 = time.time()
    try:
        netlist3, placements3, width3, leg_widths3 = \
            _heuristic_placement(netlist)
    except Exception as exc:                       # noqa: BLE001
        _attempt(meta, 3, _ENG_FULL, False, status="ERROR", stage="placement",
                 note="%s: %s" % (type(exc).__name__, exc),
                 seconds=time.time() - t0)
        raise UnsupportedCell(_diagnosis(cell_name, meta["attempts"]),
                              meta=meta)
    _attempt(meta, 3, _ENG_FULL, True, status="OK", stage="placement",
             note="width %d cols" % width3, seconds=time.time() - t0)
    meta["folded"] = netlist3 is not netlist
    meta["cell_netlist"] = netlist3

    t0 = time.time()
    try:
        route3 = _default_grid_router()(netlist3, placements3, width3,
                                        leg_widths3)
    except NotImplementedError as exc:
        _attempt(meta, 3, _ENG_FULL, False, status="UNAVAILABLE",
                 note=str(exc) or "router stub", seconds=time.time() - t0)
        route3 = None
    except Exception as exc:                       # noqa: BLE001
        _attempt(meta, 3, _ENG_FULL, False, status="ERROR",
                 note="%s: %s" % (type(exc).__name__, exc),
                 seconds=time.time() - t0)
        route3 = None
    if (route3 is not None and getattr(route3, "ok", True)):
        try:
            report3 = verify_cell(netlist3, placements3, route3)
        except Exception as exc:                   # noqa: BLE001
            report3 = None
            vnote = "verify raised %s: %s" % (type(exc).__name__, exc)
        else:
            vnote = ("verify ok" if report3.ok()
                     else "verify failed: %s" % (report3.violations[:2],))
        if (report3 is not None and report3.ok()):
            _attempt(meta, 3, _ENG_FULL, True,
                     status=getattr(route3, "status_name", "OK"),
                     stage="routing", note=vnote, seconds=time.time() - t0)
            meta["engine"] = _ENG_FULL
            meta["width_cols"] = width3
            meta["width_um"] = width3 * GRID_UM
            return placements3, route3, meta
        _attempt(meta, 3, _ENG_FULL, False,
                 status=getattr(route3, "status_name", "UNKNOWN"),
                 stage="routing", note=vnote, seconds=time.time() - t0)
    elif (route3 is not None):
        _attempt(meta, 3, _ENG_FULL, False,
                 status=getattr(route3, "status_name", "UNKNOWN"),
                 stage="routing", note=getattr(route3, "fail_note", None),
                 seconds=time.time() - t0)

    raise UnsupportedCell(_diagnosis(cell_name, meta["attempts"]), meta=meta)
