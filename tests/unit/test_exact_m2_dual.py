"""The exact model's metal2 dual-crossover vocabulary
(smt_engine.route_model build_routing_model m2_spans=True).

The heuristic side's metal2 vertical freedom (commit c4b3e9c:
RouteResult.m2v spans + node-level m2via vias) could not be expressed
by the exact model: the same-net dual rule forced both bars to reach
T3 (the rail-to-rail blanket), and there were no vertical-M2 variables.
This module pins the additive extension:

- default byte-identity: m2_spans=False (the default) builds a model
  with NO span variables and solves/routes identically (the exact-engine
  pins in test_smt_engine.py stay untouched);
- the dual relaxation: "both bars reach T3" becomes "both bars reach T3
  OR an M2 span crossover connects the halves" -- a hand-built
  dual-column case whose merge is FORBIDDEN is INFEASIBLE without the
  vocabulary and closes through the span with it (the constraint the
  verify BFS's connectivity verdict already proved sound);
- the decoded vocabulary is the heuristic side's shape (m2v keys
  (col, t_lo, t_hi) with t_lo < t_hi, m2via keys (track, col)), so
  verify.py's BFS traversal, smt_engine/gds.py's renderer and
  route_grid.route_signature consume exact-model spans unchanged;
- the window fixer (solve_window_routing) creates spans for window
  nets, merges them with kept outside verticals, and stays honest about
  kept-span blockages;
- determinism (AGENTS.md invariants 8/9): single-worker CP-SAT, sorted
  iteration -- identical spans in-process and across PYTHONHASHSEED.

The probe verdict on the diagnosed failing cells (adder/COMPLEX10,
max/COMPLEX20, XOR2X1/XNOR2X1, MUX2X1/TBUFX2, LATCH, DFFNEGX1/DFFPOSX1)
is pinned where runtime allows: the M2 dual-crossover alone does NOT
close them (all INFEASIBLE, fast proofs) -- LATCH decides the
sequential class.  The residual class and the next lever are named in
doc/AUDIT_REPORT.md (5.49).
"""
import os
import subprocess
import sys

import pytest

from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from smt_engine.route_model import build_routing_model, solve_routing
from smt_engine.route_model import solve_window_routing
from smt_engine.route_model import verify_style_access_points
from smt_engine.verify import verify_cell

INV = """\
.subckt INV VCC Y A GND
Mp Y A VCC VCC PMOS W=0.5u L=0.05u
Mn Y A GND GND NMOS W=0.5u L=0.05u
.end
"""


def _lib_subckt(name):
    """A cell's .subckt text from the ASTRAN-friendly library."""
    import re
    lib_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))),
        "std_celllib", "cellsAstranFriendly.sp")
    lib = open(lib_path).read()
    m = re.search(r"\.subckt\s+%s\b.*?\.ends" % name, lib, re.S | re.I)
    assert m, "%s not in the library" % name
    return m.group(0)


def _netlist(sp):
    return CellNetlist(parse_spice_subckt(sp))


def _inv_slot_chain():
    """fold -> blocks -> seeds -> euler -> SA -> cols (the INVX1 slot
    chain whose column 1 is Y's dual column -- the hand-pinned
    crossover geometry in test_bigcell_slot_geometry)."""
    from tests.unit.test_bigcell_slot_geometry import _chain
    nl = _netlist(INV)
    nl3, lw, op2, on2, pl, cols, bd = _chain(INV)
    return nl3, pl, cols, list(op2) + list(on2)


def _force_unmerged(rm, col=1):
    """Forbid the T3 merge at one dual column (probe form: the model
    must then connect the halves through the M2 span or fail)."""
    rm.model.Add(rm.reachT3_n[col] == 0)
    rm.model.Add(rm.reachT3_p[col] == 0)
    return rm


def _solve(nl3, pl, width_cols, blocks, m2_spans, force_unmerged_col=None):
    """Solve the full model on a slot placement (production accesses);
    returns (status, m2v, m2via) with m2v/m2via None when unsolvable."""
    accesses = verify_style_access_points(nl3, pl, blocks)
    rm = build_routing_model(nl3, pl, width_cols=width_cols,
                             accesses=accesses, m2_spans=m2_spans)
    if (force_unmerged_col is not None):
        _force_unmerged(rm, force_unmerged_col)
    from ortools.sat.python import cp_model
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.max_time_in_seconds = 60.0
    status = solver.Solve(rm.model)
    from smt_engine.route_model import _status_name, _decode_spans
    if (status not in (cp_model.OPTIMAL, cp_model.FEASIBLE)):
        return _status_name(status), None, None
    m2v, m2via = _decode_spans(rm, solver)
    return _status_name(status), m2v, m2via


# --- default byte-identity ----------------------------------------------

def test_default_build_has_no_span_vocabulary():
    """m2_spans=False (default) exposes no span structures and solves
    with empty m2v/m2via -- the exact-engine routes render and verify
    exactly as before (additive extension, c4b3e9c's 19-positional-arg
    RouteResult contract untouched)."""
    from smt_engine.layout_model import solve_layout
    nl = _netlist(INV)
    layout = solve_layout(nl, time_limit_s=20.0)
    if (layout.width_cols is None):
        pytest.skip("exact layout solve found no placement")
    rm = build_routing_model(nl, layout.devices,
                             width_cols=layout.width_cols)
    assert rm.span_on is None and rm.span_start is None
    assert rm.span_end is None and rm.span_cmp is None and rm.nv is None
    rt = solve_routing(nl, layout.devices, time_limit_s=25.0)
    assert rt.ok
    assert rt.m2v == {} and rt.m2via == {}
    rm2 = build_routing_model(nl, layout.devices,
                              width_cols=layout.width_cols,
                              m2_spans=True)
    assert rm2.span_on is not None and rm2.nv is not None


# --- the dual relaxation: connect through M2, fail without it -----------

def test_dual_column_connects_through_m2_and_fails_without():
    """THE hand-built dual-column case: INVX1's slot chain has Y's dual
    column at column 1 (both slots).  With the T3 merge FORBIDDEN the
    baseline model is INFEASIBLE (the only N<->P crossover was the
    forced merge); with the span vocabulary the model closes through an
    M2 span crossover -- and decodes to exactly the hand-pinned
    vocabulary of test_m2_crossover_hand_route_verifies."""
    nl3, pl, cols, blocks = _inv_slot_chain()
    route_width = cols + 1
    status, _m2v, _m2via = _solve(nl3, pl, route_width, blocks,
                                  m2_spans=False, force_unmerged_col=1)
    assert status == "INFEASIBLE"
    status, m2v, m2via = _solve(nl3, pl, route_width, blocks,
                                m2_spans=True, force_unmerged_col=1)
    assert status in ("OPTIMAL", "FEASIBLE")
    # the span vocabulary shape: (col, t_lo, t_hi), t_lo < t_hi
    assert m2v == {(1, 2, 4): "Y"}
    assert m2via == {(2, 1): True, (4, 1): True}


def test_span_crossover_route_verifies_and_renders(tmp_path, monkeypatch):
    """End to end on the positive control: solve -> verify -> gds ->
    layout_sanity.  The renderer draws the span as one metal2 rectangle
    per span plus one via1 square per node via (the c4b3e9c renderer
    conventions), and the structural sanity gate accepts the cell."""
    from layout_sanity import check_layout
    from smt_engine.gds import write_cell_gds
    from tests.unit.test_bigcell_slot_geometry import _chain
    nl = _netlist(INV)
    nl3, lw, op2, on2, pl, cols, bd = _chain(INV)
    blocks = list(op2) + list(on2)
    route_width = cols + 1
    orig_build = build_routing_model

    def patched(*a, **kw):
        return _force_unmerged(orig_build(*a, **kw))

    monkeypatch.setattr(
        "smt_engine.route_model.build_routing_model", patched)
    fix = solve_window_routing(nl3, pl, route_width, (0, route_width),
                               blocks=blocks, m2_spans=True)
    monkeypatch.undo()
    assert fix.route is not None, fix.note
    route = fix.route
    report = verify_cell(nl3, pl, route, blocks=blocks)
    assert report.ok(), report.violations
    gds = str(tmp_path / "inv_span.gds")
    write_cell_gds(gds, nl3, pl, route)
    import gdstk
    lib = gdstk.read_gds(gds)
    cell = lib.top_level()[0]
    m2_polys = [p for p in cell.polygons if p.layer == 51]
    via_polys = [p for p in cell.polygons if p.layer == 50]
    assert m2_polys, "the span must be drawn on metal2 (layer 51)"
    assert len(via_polys) >= 2, "the node vias must be drawn on via1"
    srep = check_layout(gds, units_per_um=1.0)
    assert srep.ok(), srep.violations


# --- the window fixer's span path ---------------------------------------

def test_window_fixer_creates_span_for_forced_unmerged_dual(monkeypatch):
    """Whole-cell window with the vocabulary: a forced-unmerged dual is
    connected through a model-created span, decoded in window
    coordinates, and the merged route verifies clean."""
    from tests.unit.test_bigcell_slot_geometry import _chain
    nl = _netlist(INV)
    nl3, lw, op2, on2, pl, cols, bd = _chain(INV)
    blocks = list(op2) + list(on2)
    route_width = cols + 1
    orig_build = build_routing_model

    def patched(*a, **kw):
        return _force_unmerged(orig_build(*a, **kw))

    monkeypatch.setattr(
        "smt_engine.route_model.build_routing_model", patched)
    fix = solve_window_routing(nl3, pl, route_width, (0, route_width),
                               blocks=blocks, m2_spans=True)
    monkeypatch.undo()
    assert fix.route is not None, fix.note
    assert fix.route.m2v == {(1, 2, 4): "Y"}
    assert fix.route.m2via == {(2, 1): True, (4, 1): True}
    report = verify_cell(nl3, pl, fix.route, blocks=blocks)
    assert report.ok(), report.violations


def test_window_merge_keeps_kept_spans_and_bans_their_points():
    """A kept (non-window-owner) span at a window column survives the
    merge, and the window solve is banned from its metal: the merged
    route carries the kept span, the window's own spans (if any) never
    overlap it, and the route verifies clean."""
    from tests.unit.test_bigcell_slot_geometry import _chain
    nl = _netlist(INV)
    nl3, lw, op2, on2, pl, cols, bd = _chain(INV)
    blocks = list(op2) + list(on2)
    route_width = cols + 1
    from smt_engine.route_model import RouteResult, _win_kept_geometry
    partial = RouteResult(
        "FEASIBLE",
        [None] * route_width, [None] * route_width,
        [0] * route_width, [0] * route_width,
        [8] * route_width, [8] * route_width,
        {}, {}, {}, {}, [False] * route_width, [False] * route_width,
        route_width, 0, 0, 0, 0, 0,
        m2v={(1, 3, 5): "ZZZ"})     # inside the (0, 2) window, foreign
    window_owners = {"Y", "VCC", "GND"}   # ZZZ is not a window net
    kept_stripes, kept_segments, kept_m2v, kept_m2via = \
        _win_kept_geometry(partial, 0, 2, window_owners)
    assert kept_m2v == {(1, 3, 5): "ZZZ"}
    fix = solve_window_routing(nl3, pl, route_width, (0, 2),
                               partial=partial, blocks=blocks,
                               m2_spans=True)
    assert fix.route is not None, fix.note
    merged = fix.route
    assert merged.m2v.get((1, 3, 5)) == "ZZZ"
    # the window's own spans (if any) never overlap the kept range
    for (c, t1, t2), net in merged.m2v.items():
        if (net == "ZZZ"):
            continue
        assert c != 1 or t2 < 3 or t1 > 5
    report = verify_cell(nl3, pl, merged, blocks=blocks)
    assert report.ok(), report.violations


# --- the probe verdict on the diagnosed cells (fast proofs) -------------

@pytest.fixture(scope="module")
def latch_slot():
    from bigcell_engine.engine import _heuristic_placement
    nl3, pl, w, lws, blocks, _orderings, _seed_tr = _heuristic_placement(
        _netlist(_lib_subckt("LATCH")))
    return nl3, pl, w, lws, blocks


def test_latch_m2_dual_crossover_is_not_sufficient(latch_slot):
    """THE probe table's decisive row (doc/AUDIT_REPORT.md 5.49): the
    sequential class' smallest cell on its rung-3 slot placement stays
    exactly-unroutable WITH the dual-crossover vocabulary -- CP-SAT
    proof in seconds, not a budget timeout.  The M2 dual-crossover
    frees the corridor above the N rail but does not free the
    contested M1 point supply (the T3 lane + gate-contact tracks)."""
    nl3, pl, w, _lws, blocks = latch_slot
    route_width = w + 1
    status, _m2v, _m2via = _solve(nl3, pl, route_width, blocks,
                                  m2_spans=True)
    assert status == "INFEASIBLE"


# --- determinism (AGENTS.md invariants 8/9) -----------------------------

def _span_signature():
    """The positive control's decoded span/via signature."""
    nl3, pl, cols, blocks = _inv_slot_chain()
    status, m2v, m2via = _solve(nl3, pl, cols + 1, blocks,
                                m2_spans=True, force_unmerged_col=1)
    assert status in ("OPTIMAL", "FEASIBLE")
    return (status, sorted(m2v.items()), sorted(m2via.items()))


def test_span_solve_deterministic_in_process():
    assert _span_signature() == _span_signature()


def test_span_solve_deterministic_cross_process_hash_seed(repo_dir):
    child = (
        "import sys, os\n"
        "repo = {repo!r}\n"
        "sys.path.insert(0, os.path.join(repo, 'flow'))\n"
        "sys.path.insert(0, repo)\n"
        "from tests.unit.test_exact_m2_dual import _span_signature\n"
        "print(_span_signature())\n"
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
