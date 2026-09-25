#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gurobi_cl-compatible wrapper based on python-mip + COIN-OR CBC (open-source MILP).

ASTRAN (compaction.cpp) invokes the configured LP solver as:

    <solver> TimeLimit=<sec> ResultFile=<sol> <model.lp>

It writes a CPLEX-LP model and expects, in the solution file, Gurobi's
"varname value" format (rounded to integers by ASTRAN).

Why this wrapper parses the LP itself instead of letting CBC's CoinLpIO do it:
ASTRAN occasionally stores *expressions* where a variable name is expected,
e.g. "x0b + RELAXATION" or "b0_17_1 + b0_17_2 + b0_17_3" (Gurobi tolerates this
and expands the expression).  CoinLpIO rejects those column names
("Invalid column names") and silently falls back to default names, which
disconnects every column from the model.  Parsing the file here and building
the model through the python-mip API keeps the names and expands the
expressions correctly.
"""
import math
import os
import re
import sys

if "HOME" not in os.environ:
    os.environ["HOME"] = os.environ.get("USERPROFILE", "C:\\Users\\Administrator")
if "USERPROFILE" not in os.environ:
    os.environ["USERPROFILE"] = "C:\\Users\\Administrator"


def _wrap_long_lines(text, limit=200):
    """Wrap over-long LP lines at whitespace (kept for readability/robustness)."""
    out = []
    for line in text.split("\n"):
        while len(line) > limit:
            cut = line.rfind(" ", 0, limit)
            if cut <= 0:
                cut = line.find(" ")
                if cut < 0:
                    break
            out.append(line[:cut])
            line = line[cut + 1:]
        out.append(line)
    return "\n".join(out)


def _parse_terms(text):
    """Parse a linear expression like '3 a - 2 b + c' -> [(3.0,'a'), (-2.0,'b'), (1.0,'c')].

    ASTRAN variable names never contain '+'/'-', so splitting on those operators
    (with surrounding whitespace added) is exact.  A number is a coefficient
    when a variable follows it, otherwise it is a constant term (this matters
    for forms like "0 - x", where 0 is a constant, not a coefficient of x).
    """
    toks = text.replace("+", " + ").replace("-", " - ").split()
    terms = []
    sign = 1.0
    i = 0
    while i < len(toks):
        t = toks[i]
        if t == "+":
            sign = 1.0
            i += 1
            continue
        if t == "-":
            sign = -1.0
            i += 1
            continue
        try:
            coef = float(t)
        except ValueError:
            terms.append((sign * 1.0, t))       # variable with implicit coefficient 1
            i += 1
        else:
            if not math.isfinite(coef):
                # ASTRAN emits "inf" coefficients from a numeric overflow in its
                # bound rules (e.g. "y184_width - inf x184_width").  An infinite
                # coefficient means "no bound", so drop the term.  Clamping it to
                # a big-M instead makes the model numerically hostile: CBC then
                # reports NO_SOLUTION_FOUND, which silently voids the compaction
                # and leaves the cell much larger than it should be.
                i += 2 if (i + 1 < len(toks) and toks[i + 1] not in ("+", "-")) else 1
                sign = 1.0
                continue
            if i + 1 < len(toks) and toks[i + 1] not in ("+", "-"):
                terms.append((sign * coef, toks[i + 1]))   # coefficient * variable
                i += 2
            else:
                terms.append((sign * coef, None))          # bare constant
                i += 1
        sign = 1.0
    return terms


def _read_cplex_lp(path):
    """Return (objective_terms, constraints, int_vars, bin_vars, semi_vars)."""
    obj_text = ""
    cons = []          # list of (body_without_name)
    int_vars, bin_vars, semi_vars = [], [], []
    mode = None
    for raw in open(path, "r", errors="replace"):
        t = raw.strip()
        if not t:
            continue
        low = t.lower()
        if low in ("minimize", "maximize"):
            mode = "obj"; continue
        if low in ("subject to", "st", "s.t.", "such that"):
            mode = "cons"; continue
        if low in ("generals", "general", "gen", "integers"):
            mode = "int"; continue
        if low in ("binary", "binaries", "bin"):
            mode = "bin"; continue
        if low in ("semi-continuous", "semi", "semis"):
            mode = "semi"; continue
        if low in ("end",):
            break
        if low.startswith("sos"):
            mode = "sos"; continue
        if mode == "obj":
            obj_text += " " + t
        elif mode == "cons":
            body = t.split(":", 1)[1] if ":" in t else t
            cons.append(body.strip().rstrip(";"))
        elif mode == "int":
            int_vars += t.split()
        elif mode == "bin":
            bin_vars += t.split()
        elif mode == "semi":
            semi_vars += t.split()
    return obj_text, cons, int_vars, bin_vars, semi_vars


def _round_away(x):
    return int(x + 0.5) if x >= 0 else -int(-x + 0.5)


def main():
    import mip

    args = sys.argv[1:]
    timelimit = 3600
    resultfile = None
    modelfile = None
    for a in args:
        if a.startswith("TimeLimit="):
            try:
                timelimit = int(a.split("=", 1)[1])
            except ValueError:
                timelimit = 3600
        elif a.startswith("ResultFile="):
            resultfile = a.split("=", 1)[1]
        elif a.lower().endswith(".lp") or a.lower().endswith(".mps"):
            modelfile = a

    if modelfile is None or resultfile is None:
        print("ERROR: usage: gurobi_cl TimeLimit=<sec> ResultFile=<sol> <model>")
        return 2

    obj_text, cons, int_vars, bin_vars, semi_vars = _read_cplex_lp(modelfile)

    model = mip.Model()
    model.verbose = 1 if os.environ.get("GUROBI_CL_VERBOSE") else 0
    _cache = {}

    def var(name, vtype=None):
        v = _cache.get(name)
        if v is None:
            v = model.add_var(name=name, var_type=vtype or mip.CONTINUOUS)
            _cache[name] = v
        return v

    int_set = set(int_vars)
    bin_set = set(bin_vars)
    semi_set = set(semi_vars)

    # declare typed variables first so their type is fixed
    for name in int_vars:
        var(name, mip.INTEGER)
    for name in bin_vars:
        var(name, mip.BINARY)
    for name in semi_vars:
        var(name, mip.CONTINUOUS)

    def vtype_of(name):
        if name in bin_set:
            return mip.BINARY
        if name in int_set:
            return mip.INTEGER
        return mip.CONTINUOUS

    # objective
    obj_terms = _parse_terms(obj_text)
    model.objective = mip.minimize(
        mip.xsum(coef * var(n, vtype_of(n)) for coef, n in obj_terms if n is not None))

    # constraints
    for body in cons:
        m = re.match(r"^(.*?)(<=|>=|=)(.*)$", body)
        if not m:
            continue
        lhs, op, rhs = m.group(1), m.group(2), m.group(3)
        lt = _parse_terms(lhs)
        rt = _parse_terms(rhs)
        lhs_expr = mip.xsum(c * var(n, vtype_of(n)) for c, n in lt if n is not None)
        rhs_expr = mip.xsum(c * var(n, vtype_of(n)) for c, n in rt if n is not None)
        lhs_const = sum(c for c, n in lt if n is None)
        rhs_const = sum(c for c, n in rt if n is None)
        if op == "<=":
            model += lhs_expr - rhs_expr <= (rhs_const - lhs_const)
        elif op == ">=":
            model += lhs_expr - rhs_expr >= (rhs_const - lhs_const)
        else:
            model += lhs_expr - rhs_expr == (rhs_const - lhs_const)

    # Compaction runs on an already-legal layout, so a loose relative gap only
    # reduces how aggressively a cell is shrunk -- it never makes the result
    # illegal.  CBC finds a good feasible solution on ASTRAN's big-M models but
    # cannot prove optimality (the LP bound is too weak), so a short first phase
    # accepts that solution; only when NOTHING was found does the search get the
    # remaining budget.  This bounds the runtime while keeping the layouts
    # legal.  For provable optimality use real Gurobi.  GUROBI_CL_TIME_LIMIT
    # sets the first-phase length.
    model.max_mip_gap = 0.02
    phase1 = int(os.environ.get("GUROBI_CL_TIME_LIMIT", "300"))
    phase1 = max(60, min(phase1, timelimit))
    # Extended search only when the first phase found nothing at all.
    retry = int(os.environ.get("GUROBI_CL_RETRY_LIMIT", "900"))
    retry = max(0, min(retry, timelimit - phase1))
    try:
        status = model.optimize(max_seconds=phase1)
        if (status == mip.OptimizationStatus.NO_SOLUTION_FOUND and retry > 0):
            status = model.optimize(max_seconds=retry)
        ok = status in (mip.OptimizationStatus.OPTIMAL,
                        mip.OptimizationStatus.FEASIBLE)
    except Exception as e:  # noqa: BLE001
        print("Unable to solve model (%s)" % e)
        return 0

    with open(resultfile, "w") as f:
        if ok and model.objective_value is not None:
            f.write("# Objective value = %g\n" % model.objective_value)
        else:
            f.write("# Objective value = 0\n")
        if ok:
            for v in model.vars:
                if v.x is not None:
                    f.write("%s %d\n" % (v.name, _round_away(v.x)))

    if ok:
        print("Solver status %s, objective %g" % (status, model.objective_value))
    else:
        print("WARNING: no usable LP solution (%s); the all-zero solution "
              "written below will make ASTRAN emit a 0 x 0 cell" % status)
    return 0


if __name__ == "__main__":
    sys.exit(main())
