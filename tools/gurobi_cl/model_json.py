#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JSON model front end for the gurobi_cl shim (STAGE 1 of the ASTRAN -> Python
compaction port).

Instead of parsing the CPLEX-LP text that ASTRAN's compaction step writes
(fragile: expression-valued column names, inf coefficients, see AGENTS.md
invariant 3), this module consumes an equivalent JSON model that is produced
at the source, either by

  - the in-ASTRAN dump (tools/astran/src/modeldump.cpp, activated by
    ASTRAN_MODEL_DUMP=<path>), or
  - tools/gurobi_cl/lp_to_json.py from an existing ILPmodel.lp
    (validation path until the C++ hook is compiled in).

Schema (``meta.format_version`` 1)::

    {"variables":   [{"name": str, "lb": num, "ub": num|null,
                      "integer": bool}, ...],
     "constraints": [{"name": str,
                      "terms": [{"var": str, "coef": num}, ...],
                      "sense": "<=|=|>=", "rhs": num}, ...],
     "meta": {"format_version": 1, "generator": str, "source_lp": str,
              "objective": {"sense": "min|max",
                            "terms": [{"var": str, "coef": num}]},
              "dropped_no_operator": int, "dropped_nonfinite_terms": int}}

Fidelity contract (both producers honour it, and this builder relies on it):

- Expression columns appear as the plain ``astranExprN`` variables the LP
  writer renamed them to; their ``CexprN`` definition constraints are kept as
  ordinary constraints (never collapsed into free variables).
- Terms with a non-finite (inf) coefficient mean "no bound" and were dropped
  at the source; "ub": null means +inf, only real bounds are emitted.
- Constraint names are preserved verbatim (the INFEASIBLE repair reports
  against them; the option-3 filter keys on the term names inside the body).
- ``variables`` is ordered exactly like the legacy builder creates columns
  (Generals, Binary, Semi, objective scan, constraint scan), so a model built
  here has the same column order as the legacy LP-parsed model and CBC sees
  an identical model.

Solver policy mirrors the legacy CBC branch of ``gurobi_cl.main`` exactly:
2% relative gap, first-phase budget GUROBI_CL_TIME_LIMIT (default 300 s),
extended search only when nothing was found, FEASIBLE counts as success, and
a *proved* INFEASIBLE retries once without the option-3 spacing disjuncts.
"""
import json
import os
import re

try:
    # single source of truth for the .sol rounding rule
    from gurobi_cl import _round_away
except ImportError:  # pragma: no cover - direct import of this module only
    def _round_away(x):
        return int(x + 0.5) if x >= 0 else -int(-x + 0.5)


FORMAT_VERSION = 1


def load_model(path):
    """Load and validate a JSON model file; raises ValueError when invalid."""
    with open(path, "r") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("model must be a JSON object")
    meta = data.get("meta")
    if not isinstance(meta, dict) or meta.get("format_version") != FORMAT_VERSION:
        raise ValueError("meta.format_version must be %d" % FORMAT_VERSION)
    for key in ("variables", "constraints"):
        if not isinstance(data.get(key), list):
            raise ValueError("missing '%s' list" % key)
    for v in data["variables"]:
        if not isinstance(v, dict) or "name" not in v:
            raise ValueError("bad variable entry: %r" % (v,))
    for c in data["constraints"]:
        if (not isinstance(c, dict) or "terms" not in c
                or c.get("sense") not in ("<=", ">=", "=")):
            raise ValueError("bad constraint entry: %r" % (c,))
    return data


def usable_json_model(json_path, lp_path=None):
    """Whether ``json_path`` is a JSON model the shim should consume instead
    of the LP file.

    The file must parse and carry ``meta.format_version == 1``.  When the LP
    file is available it must not be NEWER than the JSON: the in-ASTRAN dump
    rewrites the JSON right after writing the LP, so a JSON older than the LP
    would be a stale leftover of an earlier solve shadowing a changed model.
    """
    try:
        data = load_model(json_path)
    except (OSError, ValueError):
        return False
    del data
    try:
        if lp_path and os.path.getmtime(lp_path) > os.path.getmtime(json_path):
            return False
    except OSError:
        pass
    return True


def is_option3_disjunct(constraint):
    """Whether a JSON constraint is the *third* option of a spacing
    disjunction; the JSON-side twin of ``gurobi_cl._is_option3_disjunct``.

    The legacy shim tests the constraint *body text* for the RELAXATION
    variable and a ``b<A>_<B>_<option>_<uid>`` selector ending in ``_3``.
    In the JSON the body is structured, so the same test runs on the term
    names (space-joined, which preserves the ``\\b`` word boundaries the
    regex relies on).  See compaction.cpp/autocell2.cpp: the option-3 rules
    are the ones emitted with a ``b..._3`` selector and a RELAXATION term.
    """
    body = " ".join(t.get("var", "") for t in constraint.get("terms", []))
    if "RELAXATION" not in body:
        return False
    return re.search(r"\bb[A-Za-z0-9_]*_3(?:_|[^0-9]|$)", body) is not None


def build_mip_model(data, drop_option3=False):
    """Build a python-mip model from a loaded JSON model.

    Mirrors the legacy CBC branch of ``gurobi_cl.main`` (build()): variable
    kinds/bounds, expression construction and the 2% mip gap are identical,
    so CBC receives the same rows/columns in the same order.
    """
    import mip

    model = mip.Model()
    model.verbose = 1 if os.environ.get("GUROBI_CL_VERBOSE") else 0

    cache = {}

    def var(name):
        v = cache.get(name)
        if v is None:
            raise KeyError("constraint references undeclared variable %r" % name)
        return v

    # declare every variable upfront, in the stored (legacy creation) order
    for entry in data["variables"]:
        name = entry["name"]
        lb = entry.get("lb", 0)
        ub = entry.get("ub", None)
        integer = bool(entry.get("integer", False))
        # BINARY vs INTEGER: a general var can never carry an explicit [0,1]
        # bound in the schema (only Binary-section vars get ub 1), so this
        # reconstruction is unambiguous for both producers.
        if integer and lb == 0 and ub == 1:
            vtype = mip.BINARY
        elif integer:
            vtype = mip.INTEGER
        else:
            # Semi-section vars are continuous here on purpose: the legacy
            # shim declares them CONTINUOUS, and parity beats purity.
            vtype = mip.CONTINUOUS
        if name in cache:
            raise ValueError("duplicate variable %r" % name)
        cache[name] = model.add_var(name=name, var_type=vtype,
                                    lb=lb, ub=mip.INF if ub is None else ub)

    # objective (always minimise, like the legacy path)
    obj_terms = [(t["coef"], t["var"])
                 for t in data.get("meta", {}).get("objective", {}).get("terms", [])]
    model.objective = mip.minimize(
        mip.xsum(coef * var(n) for coef, n in obj_terms))

    # constraints, in file order
    for con in data["constraints"]:
        if drop_option3 and is_option3_disjunct(con):
            continue
        expr = mip.xsum(t["coef"] * var(t["var"]) for t in con["terms"])
        rhs = con["rhs"]
        if con["sense"] == "<=":
            model += expr <= rhs
        elif con["sense"] == ">=":
            model += expr >= rhs
        else:
            model += expr == rhs

    # Compaction runs on an already-legal layout, so a loose relative gap
    # only reduces how aggressively a cell is shrunk -- same rationale and
    # same value as the legacy path.
    model.max_mip_gap = 0.02
    return model


def solve_with_policy(data, phase1, retry):
    """Build and solve with the legacy failure policy.

    ``phase1``/``retry`` are the first-phase and extended-search budgets in
    seconds.  Returns ``(status, model)``; FEASIBLE counts as success, a
    *proved* INFEASIBLE gets exactly one retry without the option-3
    spacing disjuncts (never on a timeout, mirroring the legacy path).
    """
    import mip

    def solve(model):
        try:
            status = model.optimize(max_seconds=phase1)
            if (status == mip.OptimizationStatus.NO_SOLUTION_FOUND and retry > 0):
                status = model.optimize(max_seconds=retry)
        except Exception as e:  # noqa: BLE001
            print("Unable to solve model (%s)" % e)
            return mip.OptimizationStatus.NO_SOLUTION_FOUND
        return status

    model = build_mip_model(data, drop_option3=False)
    status = solve(model)

    if status == mip.OptimizationStatus.INFEASIBLE:
        print("WARNING: compaction model %s; retrying without the option-3 "
              "spacing disjuncts (repair pass enforces real spacing)" % status)
        model = build_mip_model(data, drop_option3=True)
        status = solve(model)

    return status, model


def write_result(resultfile, status, model):
    """Write the Gurobi-style ``varname value`` .sol ASTRAN reads back."""
    import mip

    ok = status in (mip.OptimizationStatus.OPTIMAL,
                    mip.OptimizationStatus.FEASIBLE)
    with open(resultfile, "w") as f:
        if ok and model.objective_value is not None:
            f.write("# Objective value = %g\n" % model.objective_value)
        else:
            f.write("# Objective value = 0\n")
        if ok:
            for v in model.vars:
                if v.x is not None:
                    f.write("%s %d\n" % (v.name, _round_away(v.x)))
    return ok


def run_json_path(json_path, timelimit, resultfile, phase1=None, retry=None):
    """Entry point used by gurobi_cl.py when ASTRAN_MODEL_DUMP selects the
    JSON model.  ``phase1``/``retry`` default to the same environment
    variables as the legacy path (GUROBI_CL_TIME_LIMIT / GUROBI_CL_RETRY_LIMIT).
    """
    import mip

    solver_name = os.environ.get("GUROBI_CL_SOLVER", "cpsat").lower()
    if solver_name == "cpsat":
        print("NOTE: JSON model path (ASTRAN_MODEL_DUMP) solves with CBC; "
              "GUROBI_CL_SOLVER=cpsat is not supported on this path yet")

    data = load_model(json_path)

    if phase1 is None:
        phase1 = int(os.environ.get("GUROBI_CL_TIME_LIMIT", "300"))
        phase1 = max(60, min(phase1, timelimit))
    if retry is None:
        retry = int(os.environ.get("GUROBI_CL_RETRY_LIMIT", "900"))
        retry = max(0, min(retry, timelimit - phase1))

    status, model = solve_with_policy(data, phase1, retry)
    ok = write_result(resultfile, status, model)

    if ok:
        print("Solver status %s, objective %g (JSON model path)"
              % (status, model.objective_value))
    else:
        print("WARNING: no usable LP solution (%s); the all-zero solution "
              "written below will make ASTRAN emit a 0 x 0 cell" % status)
    return 0
