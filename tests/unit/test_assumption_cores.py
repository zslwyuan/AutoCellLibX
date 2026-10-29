"""The routing model's assumption-literal families
(smt_engine.route_model build_routing_model assumptions=True) -- the
core-extraction probe mode named by doc/AUDIT_REPORT.md 5.50.

Pins:

- default byte-identity: assumptions=False (the default) builds a
  model with NO assumption machinery -- no ``asm_*`` variables, no
  registered assumptions, ``RoutingModel.assumptions is None`` (the
  m2_spans-style additive contract; the proto hash of the default
  build was separately verified identical to the pre-change build on
  the COMPLEX0 slot model, 201ea3e1...);
- the all-assumed model is exactly the default one: same solvability
  verdict on a solvable cell and on a forced-unroutable one;
- the core extraction: on the INVX1 slot chain with the T3 merge
  forbidden at the dual column (fd4fee3's positive control), the
  sufficient-assumptions core names dual:Y (the family the M2-span
  vocabulary relaxed -- m2_spans closes exactly this case), and
  assuming all-but-dual:Y is OPTIMAL (minimality direction);
- determinism (AGENTS.md invariants 8/9): the family registry is
  identical across rebuilds (sorted structures, single-worker CP-SAT).

The per-cell core table (XOR/MUX/LATCH entangled class, DFF/deep
class, TBUFX2 exact placement) lives in the probe
flow/_stage3_check/_core_probe.py + _core_probe_results.json and is
reported in doc/AUDIT_REPORT.md; the unit tests pin the machinery and
its positive control, not the (solve-budget-sized) table.
"""
import os
import re

import pytest

from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist
from smt_engine.route_model import build_routing_model, solve_routing
from smt_engine.route_model import verify_style_access_points

INV = """\
.subckt INV VCC Y A GND
Mp Y A VCC VCC PMOS W=0.5u L=0.05u
Mn Y A GND GND NMOS W=0.5u L=0.05u
.end
"""


def _netlist(sp):
    return CellNetlist(parse_spice_subckt(sp))


def _inv_slot_chain():
    """fold -> blocks -> seeds -> euler -> SA -> cols (the INVX1 slot
    chain whose column 1 is Y's dual column)."""
    from tests.unit.test_bigcell_slot_geometry import _chain
    nl = _netlist(INV)
    nl3, _lw, op2, on2, pl, cols, _bd = _chain(INV)
    return nl3, pl, cols, list(op2) + list(on2)


# --- default byte-identity ----------------------------------------------

def test_default_build_has_no_assumption_machinery():
    """assumptions=False (default): no asm_* variables, no registered
    assumptions, .assumptions None -- byte-identical additive contract."""
    from ortools.sat.python import cp_model
    nl = _netlist(INV)
    from smt_engine.layout_model import solve_layout
    layout = solve_layout(nl, time_limit_s=20.0)
    if (layout.width_cols is None):
        pytest.skip("exact layout solve found no placement")
    rm = build_routing_model(nl, layout.devices,
                             width_cols=layout.width_cols)
    assert rm.assumptions is None
    proto = str(rm.model.Proto())
    assert "asm_" not in proto
    assert not rm.model.Proto().assumptions
    # and the m2_spans=True build is equally untouched by the plumbing
    rm2 = build_routing_model(nl, layout.devices,
                              width_cols=layout.width_cols, m2_spans=True)
    assert rm2.assumptions is None
    assert "asm_" not in str(rm2.model.Proto())


def _lib_subckt(name):
    """A cell's .subckt text from the ASTRAN-friendly library."""
    lib_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))),
        "std_celllib", "cellsAstranFriendly.sp")
    lib = open(lib_path).read()
    m = re.search(r"\.subckt\s+%s\b.*?\.ends" % name, lib, re.S | re.I)
    assert m, "%s not in the library" % name
    return m.group(0)


def test_assumptions_mode_registers_all_families():
    """assumptions=True: one Boolean per family instance, every one
    registered as a CP-SAT assumption, registry exposed on the model.

    Registration is lazy per constraint site (a family with no
    constraints in the geometry -- e.g. E5 on a width-2 window -- has
    no literal), so the global-rule families are pinned on a wider
    model (LATCH's slot placement, build only)."""
    from bigcell_engine.engine import _heuristic_placement
    nl3, pl, cols, blocks = _inv_slot_chain()
    accesses = verify_style_access_points(nl3, pl, blocks)
    rm = build_routing_model(nl3, pl, width_cols=cols + 1,
                             accesses=accesses, assumptions=True)
    fam = rm.assumptions
    assert fam is not None and len(fam.names) == len(fam.lits)
    assert all(n in fam.lits for n in fam.names)
    proto = rm.model.Proto()
    assert len(proto.assumptions) == len(fam.names)
    assert all(v.Name().startswith("asm_")
               for v in fam.lits.values())
    # every family with constraints in this geometry is enumerated
    names = set(fam.names)
    for expect in ("barorder", "barban:A", "barban:Y", "acc:Y", "pwr:GND",
                   "pwr:VCC", "dual:Y", "t3excl", "csP:Y", "csS:Y",
                   "pres:Y", "acccon:Y"):
        assert expect in names, names
    # the wider model carries the adjacency/via/poly global rules too
    nll = CellNetlist(parse_spice_subckt(_lib_subckt("LATCH")))
    nl3l, pll, wl, _lws, blocksl, _orderings, _seed_tr = _heuristic_placement(nll)
    accl = verify_style_access_points(nl3l, pll, blocksl)
    rml = build_routing_model(nl3l, pll, width_cols=wl + 1,
                              accesses=accl, assumptions=True)
    namesl = set(rml.assumptions.names)
    for expect in ("t3excl", "pjleg", "e5diff", "e5same:CLK", "viabound",
                   "viaforce", "m2run", "bridge:CLK", "tjoin:CLK",
                   "gjoin:CLK", "gate:CLK", "pjanchor:CLK"):
        assert expect in namesl, sorted(namesl)


def test_family_registry_deterministic():
    """AGENTS.md invariant 9: the registry is identical across rebuilds
    (sorted iteration; no set/dict order reaches the model)."""
    nl3, pl, cols, blocks = _inv_slot_chain()
    accesses = verify_style_access_points(nl3, pl, blocks)
    a = build_routing_model(nl3, pl, width_cols=cols + 1,
                            accesses=accesses, assumptions=True)
    b = build_routing_model(nl3, pl, width_cols=cols + 1,
                            accesses=accesses, assumptions=True)
    assert a.assumptions.names == b.assumptions.names


# --- the all-assumed model is exactly the default model ------------------

def test_all_assumed_matches_default_verdicts():
    """Same solvability verdicts with every family literal assumed: a
    solvable cell stays solvable, the forced-unroutable control stays
    INFEASIBLE -- the assumption set adds no freedom and no rule."""
    from ortools.sat.python import cp_model
    nl3, pl, cols, blocks = _inv_slot_chain()
    accesses = verify_style_access_points(nl3, pl, blocks)
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.max_time_in_seconds = 30.0

    def verdict(**kw):
        rm = build_routing_model(nl3, pl, width_cols=cols + 1,
                                 accesses=accesses, **kw)
        return solver.Solve(rm.model)

    st_default = verdict()
    st_assumed = verdict(assumptions=True)
    assert solver.StatusName(st_default) == solver.StatusName(st_assumed)
    assert st_default in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    assert st_assumed in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    # forced-unroutable: the T3 merge forbidden at the dual column
    for kw in ({}, {"assumptions": True}):
        rm = build_routing_model(nl3, pl, width_cols=cols + 1,
                                 accesses=accesses, **kw)
        rm.model.Add(rm.reachT3_n[1] == 0)
        rm.model.Add(rm.reachT3_p[1] == 0)
        assert solver.Solve(rm.model) == cp_model.INFEASIBLE


# --- the core extraction and its positive control ------------------------

def test_core_names_the_dual_rule_on_the_forced_unmerged_control():
    """THE positive control (fd4fee3's hand-pinned case): with the T3
    merge forbidden at Y's dual column the sufficient-assumptions core
    names dual:Y -- the exact family the M2-span vocabulary relaxes --
    and dropping it alone restores feasibility (the core's minimality
    direction).  The raw core is sufficient, not minimal; this test
    only requires it to be sufficient and to contain dual:Y."""
    from ortools.sat.python import cp_model
    nl3, pl, cols, blocks = _inv_slot_chain()
    accesses = verify_style_access_points(nl3, pl, blocks)
    rm = build_routing_model(nl3, pl, width_cols=cols + 1,
                             accesses=accesses, assumptions=True)
    rm.model.Add(rm.reachT3_n[1] == 0)
    rm.model.Add(rm.reachT3_p[1] == 0)
    fam = rm.assumptions
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.max_time_in_seconds = 30.0
    assert solver.Solve(rm.model) == cp_model.INFEASIBLE
    core = fam.core_names(solver)
    assert 0 < len(core) <= len(fam.names)
    assert "dual:Y" in core, core
    # minimality direction: assume all-but-dual:Y -> feasible
    rm.model.ClearAssumptions()
    for name in fam.names:
        if (name != "dual:Y"):
            rm.model.AddAssumption(fam.lits[name])
    st = solver.Solve(rm.model)
    assert st in (cp_model.OPTIMAL, cp_model.FEASIBLE), \
        solver.StatusName(st)


def test_solve_routing_passes_assumptions_through():
    """solve_routing(assumptions=True) builds the same verdict as the
    default public path (the pass-through keeps solve callers honest)."""
    nl = _netlist(INV)
    from smt_engine.layout_model import solve_layout
    layout = solve_layout(nl, time_limit_s=20.0)
    if (layout.width_cols is None):
        pytest.skip("exact layout solve found no placement")
    r0 = solve_routing(nl, layout.devices,
                       width_cols=layout.width_cols, time_limit_s=30.0)
    r1 = solve_routing(nl, layout.devices,
                       width_cols=layout.width_cols, time_limit_s=30.0,
                       assumptions=True)
    assert r0.ok and r1.ok
    assert r0.status_name == r1.status_name
    assert r0.hseg == r1.hseg
