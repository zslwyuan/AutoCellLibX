"""Compare the CBC and CP-SAT backends on the same LP (P2 phase 2).

    python compare_backends.py <model.lp> [timelimit_seconds]

Runs gurobi_cl.py twice -- once default (CBC), once with
GUROBI_CL_SOLVER=cpsat -- and prints objective / solve status / the
layout ``width`` variable from each .sol.  The LP is read-only; .sol
files go to a temp directory.
"""

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GUROBI_CL = os.path.join(HERE, "gurobi_cl.py")


def _run(env, lp, resultfile, timelimit):
    env = dict(env)
    env["GUROBI_CL_TIME_LIMIT"] = str(timelimit)
    env["GUROBI_CL_RETRY_LIMIT"] = str(timelimit)
    proc = subprocess.run(
        [sys.executable, GUROBI_CL,
         "TimeLimit=%d" % timelimit, "ResultFile=%s" % resultfile, lp],
        capture_output=True, text=True, env=env)
    out = (proc.stdout or "") + (proc.stderr or "")
    objective = None
    width = None
    if (os.path.exists(resultfile)):
        for line in open(resultfile):
            if (line.startswith("# Objective value = ")):
                objective = float(line.split("=")[1])
            elif (line.split() and line.split()[0] == "width"):
                width = float(line.split()[1])
    return {"objective": objective, "width": width,
            "log_tail": out.strip().splitlines()[-3:]}


def compare(lpPath, timelimit=120):
    results = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name, extra in (("cbc", {}),
                            ("cpsat", {"GUROBI_CL_SOLVER": "cpsat"})):
            env = dict(os.environ)
            env.update(extra)
            results[name] = _run(
                env, lpPath, os.path.join(tmp, name + ".sol"), timelimit)
    return results


if __name__ == "__main__":
    lp = sys.argv[1] if len(sys.argv) > 1 else "ILPmodel.lp"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    res = compare(lp, limit)
    print("%-8s %-14s %-10s %s" % ("backend", "objective", "width", "log"))
    for name, r in res.items():
        print("%-8s %-14s %-10s %s"
              % (name, r["objective"], r["width"],
                 " | ".join(r["log_tail"])))
    if (res["cbc"]["objective"] and res["cpsat"]["objective"]):
        diff = abs(res["cbc"]["objective"] - res["cpsat"]["objective"]) \
            / res["cbc"]["objective"]
        print("objective relative diff: %.4f%%" % (diff * 100))
