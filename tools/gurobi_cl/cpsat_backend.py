"""CP-SAT backend for the gurobi_cl adapter (P2 phase 2).

TransRoute (DAC'25) showed CP-SAT competitive on routing-style
formulations; the compaction LP ASTRAN emits is the same family
(difference constraints + big-M disjunctions + mostly-boolean
decisions).  This backend solves the *same* parsed LP the CBC path
uses (``_read_cplex_lp`` + ``_parse_terms`` from gurobi_cl), so the two
solvers can be compared apples-to-apples on identical models.

CP-SAT is integer-only, so continuous coordinates are scaled by
``scale`` (adaptive: 1 for ASTRAN's all-integer DBU model, 10000 -- 1e-4
um resolution, four orders below the 0.19 um grid -- for a foreign LP
with fractional coefficients).

Selected with GUROBI_CL_SOLVER=cpsat; CBC stays the default.
"""

import os
import re

# Single source of truth for LP term parsing (including the inf-term
# drop: ASTRAN emits "inf" coefficients meaning "no bound", see
# gurobi_cl.py).  Importing gurobi_cl here is safe: it only imports
# cpsat_backend lazily inside main(), and as a script it registers as
# __main__, so this module gets a clean module object.
from gurobi_cl import _parse_terms

_DOMAIN = 10**9           # covers RELAXATION=20000um x any sane scale

# solver status vocabulary shared with gurobi_cl.main
OPTIMAL = "OPTIMAL"
FEASIBLE = "FEASIBLE"
INFEASIBLE = "INFEASIBLE"
NO_SOLUTION = "NO_SOLUTION_FOUND"

_DECIMAL_RE = re.compile(r"\.\d*[1-9]")


def _needsScaling(*texts):
    """Whether any coefficient carries a *non-zero* fractional part.
    ASTRAN's compaction LP is all-integer (rules x 400 DBU) apart from
    literal "0.000000" coefficients, so no scaling is needed in practice;
    scale only makes a foreign LP consumable."""
    return any(_DECIMAL_RE.search(t) for t in texts if t)




def solve_lp_with_cp_sat(obj_text, cons, int_vars, bin_vars,
                     timelimit_s, drop_option3=None,
                     drop_predicate=None, workers=None, log=False):
    """Solve the parsed LP with CP-SAT.

    Returns (status, {var_name: float}, objective).  ``drop_option3``
    and ``drop_predicate`` mirror the CBC recovery path: when truthy,
    constraints matching the predicate are skipped (the option-3
    disjunct retry fires only on a *proved* infeasible, never on a
    timeout).
    """
    from ortools.sat.python import cp_model

    scale = 10000 if _needsScaling(obj_text, *cons) else 1

    def sint(x):
        v = x * scale
        return int(v + 0.5) if v >= 0 else -int(-v + 0.5)

    model = cp_model.CpModel()
    cache = {}
    bin_set = set(bin_vars)
    int_set = set(int_vars)

    def var(name):
        v = cache.get(name)
        if (v is None):
            if (name in bin_set):
                v = model.NewBoolVar(name)
            else:
                v = model.NewIntVar(0, _DOMAIN, name)
            cache[name] = v
        return v

    # objective (collect terms first so every variable exists)
    obj_terms = _parse_terms(obj_text)
    obj_expr = sum(sint(c) * var(n) for c, n in obj_terms if n is not None)
    model.Minimize(obj_expr)

    skipped = 0
    for body in cons:
        if (drop_option3 and drop_predicate is not None
                and drop_predicate(body)):
            skipped += 1
            continue
        m = re.match(r"^(.*?)(<=|>=|=)(.*)$", body)
        if (not m):
            continue
        lhs, op, rhs = m.group(1), m.group(2), m.group(3)
        lt = _parse_terms(lhs)
        rt = _parse_terms(rhs)
        lhs_expr = sum(sint(c) * var(n) for c, n in lt if n is not None)
        rhs_expr = sum(sint(c) * var(n) for c, n in rt if n is not None)
        bound = sint(sum(c for c, n in rt if n is None)
                      - sum(c for c, n in lt if n is None))
        if (op == "<="):
            model.Add(lhs_expr - rhs_expr <= bound)
        elif (op == ">="):
            model.Add(lhs_expr - rhs_expr >= bound)
        else:
            model.Add(lhs_expr - rhs_expr == bound)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(timelimit_s)
    solver.parameters.num_search_workers = workers or min(
        8, os.cpu_count() or 1)
    if (log):
        solver.parameters.log_search_progress = True
    status = solver.Solve(model)

    if (status in (cp_model.OPTIMAL, cp_model.FEASIBLE)):
        values = {n: solver.Value(v) / scale for n, v in cache.items()}
        return (OPTIMAL if status == cp_model.OPTIMAL else FEASIBLE,
                values, solver.ObjectiveValue() / scale)
    if (status == cp_model.INFEASIBLE):
        return INFEASIBLE, {}, None
    return NO_SOLUTION, {}, None
