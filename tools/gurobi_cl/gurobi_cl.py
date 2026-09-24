#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gurobi_cl compatible wrapper based on python-mip + COIN-OR CBC (open-source MILP).

ASTRAN (compaction.cpp / placer.cpp / router.cpp) invokes the configured
LP solver as:  <solver> TimeLimit=<sec> ResultFile=<sol> <model.lp>
It writes the model in CPLEX LP format and expects:
  - stdout lines whose first token is one of
    ERROR/Time/Unable/Wrote/Optimal/Model (printed back to the ASTRAN log)
  - a solution file in Gurobi .sol format:
        # Objective value = ...
        varname value
  ("#" comments are skipped; values are rounded to int by ASTRAN)
"""
import os
import sys

if "HOME" not in os.environ:
    os.environ["HOME"] = os.environ.get("USERPROFILE", "C:\\Users\\Administrator")
if "USERPROFILE" not in os.environ:
    os.environ["USERPROFILE"] = "C:\\Users\\Administrator"


def main():
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

    import mip
    import os

    # ASTRAN's LP writer does not emit the CPLEX 'End' keyword; CoinLpIO
    # (CBC) segfaults without it.  Work on a normalized copy in the same dir.
    fixed = modelfile
    if not modelfile.lower().endswith(".mps"):
        base = os.path.splitext(modelfile)[0]
        fixed = base + ".fixed.lp"
        with open(modelfile, "r") as f:
            text = f.read()
        stripped = text.rstrip()
        if not stripped.lower().endswith("end"):
            text = stripped + "\nEnd\n"
        with open(fixed, "w") as f:
            f.write(text)

    try:
        m = mip.Model()
        m.read(fixed)
    except Exception as e:  # noqa: BLE001
        print("Unable to read model file %s (%s)" % (modelfile, e))
        return 0

    m.max_mip_gap = 0.0
    try:
        status = m.optimize(max_seconds=timelimit)
        ok = status == mip.OptimizationStatus.OPTIMAL
    except Exception as e:  # noqa: BLE001
        print("Unable to solve model (%s)" % e)
        return 0

    with open(resultfile, "w") as f:
        if ok and m.objective_value is not None:
            f.write("# Objective value = %g\n" % m.objective_value)
        else:
            f.write("# Objective value = 0\n")
        if ok:
            for v in m.vars:
                if v.x is not None:
                    f.write("%s %d\n" % (v.name, round(v.x)))

    if ok:
        print("Optimal solution found, objective %g" % m.objective_value)
    else:
        print("Unable to solve problem to optimality (%s), writing best solution" % status)
    return 0


if __name__ == "__main__":
    sys.exit(main())
