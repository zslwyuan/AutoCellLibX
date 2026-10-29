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
- **rungs 2.5 / 3.5 -- window fix**: when a grid-router attempt fails
  (its honest ``fail_note``), the exact engine returns in its doc
  section 2.4 rung-1 role as a WINDOW FIXER: the conflicted region is
  re-solved exactly on a <=12-column window with the plateaued router
  solution outside the window fixed as blockages
  (smt_engine.route_model.solve_window_routing).  The merged route is
  verify-gated like every other rung; an INFEASIBLE window is itself
  decisive evidence (the region is exactly-unroutable -- the blocker is
  the placement/vocabulary, not the router's heuristic) and is recorded
  as a failed attempt.

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
_ENG_WINDOW = "bigcell-window-fix"
_ENG_GRID_WINDOW = "bigcell-grid+window-fix"
_ENG_FULL_WINDOW = "bigcell-full+window-fix"


def parse_fail_nets(note):
    """Conflicted net names from route_grid's fail_note.

    The failed RouteResult's ``fail_note`` is route_grid's public
    failure payload; this parses its three forms deterministically:
    the stagnation note ("...(best N conflicts at attempt A; unresolved:
    n1, n2)<suffix>"), a path failure ("impossible to find a path for
    net X") and a build-time terminal clash ("terminal clash at (...):
    X and Y").  The unresolved list terminates at its closing paren
    (newer route_grid notes append a structural analysis after it).
    """
    if (not note):
        return []
    if ("unresolved:" in note):
        tail = note.split("unresolved:", 1)[1].split(")", 1)[0].strip()
        if (tail in ("", "-")):
            return []
        return [s.strip() for s in tail.split(",") if s.strip()]
    marker = "impossible to find a path for net "
    if (marker in note):
        return [note.split(marker, 1)[1].strip()]
    if ("terminal clash at" in note and ": " in note):
        tail = note.split(": ", 1)[1]
        return [p.strip() for p in tail.split(" and ") if p.strip()]
    return []


def window_region(cols, route_width, max_cols=None):
    """(window, reason) from the conflicted nets' access columns.

    The window is the access span padded by one column per side,
    clipped to the route grid; None with an honest reason when the
    region exceeds the window budget (doc section 2.4: <=12 columns).
    """
    if (max_cols is None):
        from smt_engine.route_model import WINDOW_MAX_COLS
        max_cols = WINDOW_MAX_COLS
    if (not cols):
        return None, "conflicted nets have no access columns"
    w0 = max(0, min(cols) - 1)
    w1 = min(route_width, max(cols) + 2)
    if (w1 - w0 > max_cols):
        return None, ("conflicted region spans %d columns > %d window "
                      "budget" % (w1 - w0, max_cols))
    return (w0, w1), "access span padded to [%d,%d) of %d" % (w0, w1,
                                                              route_width)


def _plateau_partial(netlist, placement, width_cols, blocks=None):
    """The router's plateaued solution, recovered deterministically.

    The failed RouteResult carries only the fail_note, but the window
    fixer needs the per-column stripes and outside-window segments as
    blockages.  The re-run replicates route_cell's EXACT two-phase
    sequence -- the phase-1 skip gate (a dirty structural diagnosis
    skips phase 1 entirely), then the phase-2 metal2-freedom grid on a
    phase-1 stall -- so the failure state reproduced is the PHASE-2
    grid's final trees in every failure mode; a single-phase re-run
    reproduces a DIFFERENT failure state and the window fixer would
    refuse it.  route_grid is deterministic (AGENTS.md invariants 8/9)
    and ``blocks`` is the orientation-aware block view the rung-3
    router was wired with (route_cell forwards it into both of its
    phase grids), so the re-run sees the identical graph; if the re-run
    does NOT fail the same way, refuse to fix a moving target.  Returns
    a RouteResult-shaped snapshot of the final trees (build_result) or
    None.
    """
    from bigcell_engine.route_grid import MAX_ATTEMPTS, _RouteGrid
    grid = _RouteGrid(netlist, placement, width_cols, blocks=blocks)
    if (grid._fail_note is not None):
        return None              # build-time failure: no plateau state
    skip = False
    contests, walled = grid.structural_diagnosis()
    if (contests or walled):
        skip = True              # phase 1 is a proven stall: skip it
    if (not skip and grid.route(max_attempts=MAX_ATTEMPTS)):
        return None              # the re-run closes: not a moving target
    grid = _RouteGrid(netlist, placement, width_cols,
                      metal2_verticals=True, blocks=blocks)
    if (grid.route(max_attempts=MAX_ATTEMPTS)):
        return None
    return grid.build_result()


def _window_fix_rung(meta, rung, netlist, placement, blocks, failed_route,
                     tracks="bar9"):
    """One window-fix attempt: the exact engine on the conflicted region.

    Derives the window from the failed route's fail_note (parsed via
    :func:`parse_fail_nets`) and the conflicted nets' access columns,
    solves it exactly (whole-cell windows need no plateau state; strict
    sub-windows re-run the deterministic router for the blockage
    geometry), and verify-gates the merged result like every other
    rung.  Returns the merged RouteResult or None; every outcome is
    recorded in ``meta`` with the window attached.
    """
    from smt_engine import route_model
    from smt_engine.verify import verify_cell
    route_width = getattr(failed_route, "width_cols", None) or max(
        p.end_col for p in placement.values())
    names = parse_fail_nets(getattr(failed_route, "fail_note", None))
    if (not names):
        _attempt(meta, rung, _ENG_WINDOW, False, status="SKIPPED",
                 stage="routing",
                 note="fail note names no conflicted nets")
        return None
    diffusion, gate, _power = route_model.verify_style_access_points(
        netlist, placement, blocks)
    cols = set()
    for name in names:
        cols.update(c for c, _dev in diffusion.get(name, ()))
        cols.update(gate.get(name, ()))
    window, reason = window_region(cols, route_width)
    if (window is None):
        _attempt(meta, rung, _ENG_WINDOW, False, status="SKIPPED",
                 stage="routing", note=reason)
        return None
    if (route_width <= route_model.WINDOW_MAX_COLS):
        # the route vocabulary includes the trailing edge-escape column
        # (slot geometry: route grid = placement W + 1) -- a window that
        # stops at the placement width would deny the exact model the
        # escape lane the heuristic router never had.  Whole-cell
        # windows that fit the budget also need no plateau state.
        window = (0, route_width)
    partial = None
    if (window != (0, route_width)):
        partial = _plateau_partial(netlist, placement, route_width,
                                   blocks=blocks)
        if (partial is None):
            _attempt(meta, rung, _ENG_WINDOW, False, status="SKIPPED",
                     stage="routing",
                     note="plateau state not reproduced by the "
                          "deterministic router re-run")
            return None
    t0 = time.time()
    try:
        fix = route_model.solve_window_routing(
            netlist, placement, route_width, window, partial=partial,
            blocks=blocks, m2_spans=True, jump_m2=True, tracks=tracks)
    except Exception as exc:                       # noqa: BLE001
        _attempt(meta, rung, _ENG_WINDOW, False, status="ERROR",
                 stage="routing", window=list(window),
                 note="%s: %s" % (type(exc).__name__, exc),
                 seconds=time.time() - t0)
        return None
    seconds = time.time() - t0
    if (fix.route is None):
        _attempt(meta, rung, _ENG_WINDOW, False, status=fix.status_name,
                 stage="routing", window=list(window), note=fix.note,
                 seconds=seconds)
        return None
    try:
        report = verify_cell(netlist, placement, fix.route, blocks=blocks)
    except Exception as exc:                       # noqa: BLE001
        _attempt(meta, rung, _ENG_WINDOW, False, status=fix.status_name,
                 stage="routing", window=list(window),
                 note="verify raised %s: %s" % (type(exc).__name__, exc),
                 seconds=seconds)
        return None
    if (not report.ok()):
        _attempt(meta, rung, _ENG_WINDOW, False, status=fix.status_name,
                 stage="routing", window=list(window),
                 note="merged verify failed: %s" % (report.violations[:2],),
                 seconds=seconds)
        return None
    _attempt(meta, rung, _ENG_WINDOW, True, status=fix.status_name,
             stage="routing", window=list(window),
             note="window [%d,%d) fixed and verified (%.1fs)"
                  % (window[0], window[1], fix.seconds),
             seconds=seconds)
    return fix.route


def _default_grid_router():
    """The production rung-2/3 router, resolved lazily for testability."""
    from .route_grid import route_cell
    return route_cell


def _heuristic_placement(netlist):
    """Rung-3 placement: fold -> blocks -> seeds -> euler -> SA -> columns.

    Returns (netlist3, placements, width_cols, leg_widths, blocks,
    orderings) where ``netlist3`` is the (possibly fold-expanded) netlist
    the placement is expressed against, ``blocks`` is the ORIENTATION-
    AWARE block view the placement was built from (the refined orderings'
    blocks, whose members carry the SA mirror state -- verify_cell must
    consult these, not build_bigcell_blocks' pristine list, or every
    mirrored block pair reads as a missing diffusion break), and
    ``orderings`` is the (ordering_p, ordering_n) tuple the GDS slot
    emitter needs.
    Deterministic; raises on structural failure.
    """
    from . import geometry
    from .netlist_ext import (build_bigcell_blocks, fold_devices,
                              row_seeds)
    from .place_euler import euler_orderings
    from .place_sa import sa_refine_routable

    netlist3, leg_widths = fold_devices(netlist)
    blocks = build_bigcell_blocks(netlist3)
    seeds = row_seeds(blocks, leg_widths)
    ordering_p, ordering_n = euler_orderings(seeds, leg_widths)
    ordering_p, ordering_n, cost = sa_refine_routable(
        ordering_p, ordering_n, netlist3, leg_widths, variant_classes=True,
        core_guided=True)
    # fold-variant winner (place_sa's lazy phase 6): the selected
    # orderings decompose the OVERRIDE fold decision, so every consumer
    # below (layout, router, verify, GDS emit) must work against the
    # variant's own netlist/leg map -- recovered deterministically
    sel = cost.get("selection", {})
    if sel.get("fold_overrides"):
        netlist3, leg_widths = fold_devices(
            netlist3, fold_overrides=sel["fold_overrides"])
    # GDS-seed winner (place_sa's seed_ctx, AUDIT 5.61-5.63): the
    # selected orderings decompose the EXTRACTED arrangement -- its
    # measured terminal-region widths replace the leg map, its per-row
    # x-offsets shift place_row, and its TRACK DOMAIN carries the
    # closure's vertical vocabulary, so every consumer below (layout,
    # router, verify, GDS emit) reproduces ASTRAN's own columns on
    # ASTRAN's own grid
    x_offsets = (0, 0)
    tracks3 = "bar9"
    if sel.get("seed_leg_widths"):
        leg_widths = {n: tuple(v) for n, v
                      in sel["seed_leg_widths"].items()}
    if sel.get("seed_x_offsets"):
        x_offsets = tuple(sel["seed_x_offsets"])
    if sel.get("seed_tracks"):
        tracks3 = sel["seed_tracks"]
    placements, width_cols = geometry.layout_cell(
        ordering_p, ordering_n, leg_widths, x_offsets=x_offsets)
    blocks_view = list(ordering_p) + list(ordering_n)
    return (netlist3, placements, width_cols, leg_widths, blocks_view,
            (ordering_p, ordering_n), tracks3)


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
             seconds=None, window=None):
    entry = {"rung": rung, "engine": engine, "ok": bool(ok)}
    if (status is not None):
        entry["status"] = status
    if (stage is not None):
        entry["stage"] = stage
    if (note is not None):
        entry["note"] = note
    if (window is not None):
        entry["window"] = window
    if (seconds is not None):
        entry["seconds"] = round(seconds, 1)
    meta["attempts"].append(entry)
    return entry


def _diagnosis(cell_name, attempts):
    parts = []
    for a in attempts:
        if (a.get("ok")):
            continue
        piece = "rung%s %s" % (a["rung"], a["engine"])
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
    outcome, seconds, window for the window-fix rungs) and the winning
    engine/width; on failure :class:`UnsupportedCell` is raised with the
    same ``meta`` attached.

    Rung 1 verifies its own route (verify_cell must be clean before the
    rung counts as closed).  Rung 2's route is returned unverified --
    verification is the caller's continuous-verification gate (the
    benchmark runs verify_cell on every produced cell); the attempt
    record marks it accordingly.  Rungs 2.5/3.5 (the window fixer)
    verify-gate their merged route inside the ladder like rung 1.

    ``grid_budget_s`` is recorded in meta and reserved for the real
    route_grid budget; the injected router's signature is fixed at
    (netlist, placement, width_cols, leg_widths).
    """
    cell_name = getattr(getattr(netlist, "subckt", None), "subckt_name",
                        "?")
    best = None   # narrowest verified closing candidate so far (rung 2/2.5)
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
                    # candidate, not a return: rung 3's slot placement is
                    # often narrower (the exact IR draws W horizontally) --
                    # the ladder returns the narrowest verified closing
                    # result.  Rung 2 is skipped: same placement, no new
                    # information from a second router.
                    best = {"placements": layout.devices, "route": route,
                            "engine": _ENG_EXACT,
                            "width_cols": layout.width_cols}
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
    # Skipped entirely when rung 1 closed: same placement, no new
    # information from a second router.
    using_real_router = grid_router is None
    if (best is not None):
        _attempt(meta, 2, _ENG_GRID, False, status="SKIPPED",
                 note="rung 1 already closed this exact placement")
    elif (grid_router is False):
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
                # rung 2.5: the exact engine as a window fixer on the
                # conflicted region of the exact-engine placement
                if (using_real_router):
                    fixed2 = _window_fix_rung(meta, 2.5, netlist,
                                              layout.devices, None,
                                              route2)
                    if (fixed2 is not None):
                        # candidate, not a return: the slot chain may still
                        # be narrower -- the ladder returns the narrowest
                        # VERIFIED closing result, not the first closing one
                        best = {"placements": layout.devices,
                                "route": fixed2,
                                "engine": _ENG_GRID_WINDOW,
                                "width_cols": fixed2.width_cols}
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
                    best = {"placements": layout.devices, "route": route2,
                            "engine": _ENG_GRID, "width_cols": width_cols}
                    # no early return: rung 3's slot placement is often
                    # much narrower (the exact-engine placement draws W
                    # horizontally) -- the ladder picks the narrowest
                    # verified closing result

    # --- rung 3: heuristic placement chain + the grid router ------------
    t0 = time.time()
    try:
        (netlist3, placements3, width3, leg_widths3, blocks3, orderings3,
         tracks3) = _heuristic_placement(netlist)
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
    meta["blocks"] = blocks3

    t0 = time.time()
    try:
        # blocks3 (the orientation-aware view placements3 was built from)
        # goes into the router exactly as it goes into verify_cell below:
        # the router and the verifier must derive their slot accesses
        # from the SAME view (route_grid threads it into both phase
        # grids' die_view fallbacks); on every placement the pristine
        # reconstruction explains, the route is byte-identical to the
        # blocks-less run.  astran13 seeds route through the PORTED
        # ASTRAN router (router_port.route_cell_ported -- AutoCell's
        # element graph + GraphRouter on ASTRAN's own track layout, the
        # router that closed the .gds layouts these arrangements were
        # extracted from); bar9 keeps route_grid byte-identical.
        if tracks3 == "astran13":
            from .router_port import route_cell_ported
            route3 = route_cell_ported(netlist3, placements3, width3,
                                       leg_widths3, blocks=blocks3,
                                       tracks=tracks3)
        else:
            route3 = _default_grid_router()(netlist3, placements3, width3,
                                            leg_widths3, blocks=blocks3,
                                            tracks=tracks3)
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
            report3 = verify_cell(netlist3, placements3, route3,
                                  blocks=blocks3, tracks=tracks3)
        except Exception as exc:                   # noqa: BLE001
            report3 = None
            vnote = "verify raised %s: %s" % (type(exc).__name__, exc)
        else:
            vnote = ("verify ok" if report3.ok()
                     else "verify failed: %s" % (report3.violations[:2],))
        if (report3 is not None and report3.ok()):
            if (best is not None and best["width_cols"] <= width3):
                _attempt(meta, 3, _ENG_FULL, True,
                         status=getattr(route3, "status_name", "OK"),
                         stage="routing",
                         note=vnote + "; rung-%s candidate already narrower"
                              % best["engine"], seconds=time.time() - t0)
            else:
                _attempt(meta, 3, _ENG_FULL, True,
                         status=getattr(route3, "status_name", "OK"),
                         stage="routing", note=vnote,
                         seconds=time.time() - t0)
                meta["engine"] = _ENG_FULL
                meta["width_cols"] = width3
                meta["width_um"] = width3 * GRID_UM
                meta["slot_emit"] = {"width_cols": width3,
                                     "ordering_p": orderings3[0],
                                     "ordering_n": orderings3[1],
                                     "leg_widths": leg_widths3,
                                     "tracks": tracks3}
                return placements3, route3, meta
        _attempt(meta, 3, _ENG_FULL, False,
                 status=getattr(route3, "status_name", "UNKNOWN"),
                 stage="routing", note=vnote, seconds=time.time() - t0)
    elif (route3 is not None):
        _attempt(meta, 3, _ENG_FULL, False,
                 status=getattr(route3, "status_name", "UNKNOWN"),
                 stage="routing", note=getattr(route3, "fail_note", None),
                 seconds=time.time() - t0)

    # --- rung 3.5: the exact engine as a window fixer on the failed
    # rung-3 route's conflicted region (doc section 2.4, rung 1's
    # narrowed role).  Three fire forms: (a) a bar9 router FAILURE
    # carries the honest fail_note -- the conflicted-region window fix;
    # (b) a NON-bar9 seed's router failure -- the window fixer's tie
    # planner is bar9-specific, so the seed's own closure form fires
    # instead: the whole-cell exact solve on the route's domain; (c) a
    # verify-dirty router SUCCESS (the heuristic found a zero-conflict
    # route the verifier rejects -- observed on astran13 seeds, AUDIT
    # 5.63) -- the whole-cell exact solve as well.

    def _direct_exact_solve():
        """The whole-cell exact solve (forms b and c): the seed
        captures' own closure form -- solve_routing with the full
        vocabulary on the route's own domain, verify-gated."""
        t0x = time.time()
        try:
            from smt_engine.route_model import (solve_routing,
                                                verify_style_access_points)
            acc = verify_style_access_points(netlist3, placements3,
                                             blocks3)
            ex = solve_routing(
                netlist3, placements3, width3 + 1, metal2=True,
                m2_spans=True, jump_m2=True, accesses=acc,
                tracks=tracks3, time_limit_s=120.0)
        except Exception as exc:                   # noqa: BLE001
            _attempt(meta, 3.5, _ENG_FULL_WINDOW, False, status="ERROR",
                     stage="routing",
                     note="%s: %s" % (type(exc).__name__, exc),
                     seconds=time.time() - t0x)
            return None
        okx = getattr(ex, "status_name", None) in ("OPTIMAL", "FEASIBLE")
        _attempt(meta, 3.5, _ENG_FULL_WINDOW, okx,
                 status=ex.status_name, stage="routing",
                 window=[0, width3 + 1], seconds=time.time() - t0x)
        if (not okx):
            return None
        try:
            rep = verify_cell(netlist3, placements3, ex, blocks=blocks3,
                              tracks=tracks3)
        except Exception:                          # noqa: BLE001
            return None
        return ex if rep.ok() else None

    if (route3 is not None and not getattr(route3, "ok", True)):
        if (tracks3 == "bar9"):
            fixed3 = _window_fix_rung(meta, 3.5, netlist3, placements3,
                                      blocks3, route3, tracks=tracks3)
        else:
            # form (b): the bar9-specific window fixer cannot plan ties
            # on a non-bar9 domain; the direct exact solve replaces it
            fixed3 = _direct_exact_solve()
    elif (route3 is not None and report3 is not None
          and not report3.ok()):
        # form (c): the verify-dirty heuristic route
        fixed3 = _direct_exact_solve()
    else:
        fixed3 = None
    if (fixed3 is not None and (best is None
                                or fixed3.width_cols
                                < best["width_cols"])):
            meta["engine"] = _ENG_FULL_WINDOW
            meta["width_cols"] = fixed3.width_cols
            meta["width_um"] = fixed3.width_cols * GRID_UM
            meta["slot_emit"] = {"width_cols": width3,
                                 "ordering_p": orderings3[0],
                                 "ordering_n": orderings3[1],
                                 "leg_widths": leg_widths3,
                                 "tracks": tracks3}
            return placements3, fixed3, meta

    if (best is not None):
        # the slot chain did not beat the earlier closing rung -- hand
        # back its result with a consistent meta (legacy writer path:
        # exact-engine IR has no slot emit context)
        meta["engine"] = best["engine"]
        meta["width_cols"] = best["width_cols"]
        meta["width_um"] = best["width_cols"] * GRID_UM
        meta.pop("slot_emit", None)
        meta["cell_netlist"] = netlist
        meta["blocks"] = None
        return best["placements"], best["route"], meta

    raise UnsupportedCell(_diagnosis(cell_name, meta["attempts"]), meta=meta)
