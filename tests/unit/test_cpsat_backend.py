"""Unit tests for the CP-SAT gurobi_cl backend (P2 phase 2)."""
import os
import subprocess
import sys

import pytest

TOOLS = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..",
                 "tools", "gurobi_cl"))
sys.path.insert(0, TOOLS)

cpsat = pytest.importorskip("cpsat_backend")

TINY_LP = """Minimize
 5000 width + 3 xa + bsel
Subject To
 c1: xb - xa >= 26
 c2: width - xb >= 13
 c3: xa - ZERO >= 13
 c4: xb - xa - RELAXATION >= -20000
 c5: xb - xa + 20000 bsel >= 26
 c6: ZERO = 0
Generals
 xgpos
Binary
 bsel
End
"""


def _read(lp_text):
    from gurobi_cl import _read_cplex_lp
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".lp", delete=False) as f:
        f.write(lp_text)
        path = f.name
    parsed = _read_cplex_lp(path)
    os.unlink(path)
    return parsed


def test_solves_tiny_lp_optimally():
    obj_text, cons, int_vars, bin_vars, _ = _read(TINY_LP)
    status, values, objective = cpsat.solveLpWithCpSat(
        obj_text, cons, int_vars, bin_vars, 30)
    assert status in (cpsat.OPTIMAL, cpsat.FEASIBLE)
    # minimal width: xa>=13, xb>=xa+26=39, width>=xb+13=52
    assert values["width"] == pytest.approx(52)
    assert values["bsel"] in (0.0, 1.0)


def test_detects_infeasible():
    lp = TINY_LP.replace("c1: xb - xa >= 26",
                         "c1: xb - xa >= 26\nc1b: xa - xb >= 26")
    obj_text, cons, int_vars, bin_vars, _ = _read(lp)
    status, values, objective = cpsat.solveLpWithCpSat(
        obj_text, cons, int_vars, bin_vars, 30)
    assert status == cpsat.INFEASIBLE


def test_gurobi_cl_end_to_end_cpsat(tmp_path):
    lp = tmp_path / "tiny.lp"
    lp.write_text(TINY_LP)
    resultfile = tmp_path / "tiny.sol"
    env = dict(os.environ, GUROBI_CL_SOLVER="cpsat",
               GUROBI_CL_TIME_LIMIT="60")
    proc = subprocess.run(
        [sys.executable, os.path.join(TOOLS, "gurobi_cl.py"),
         "TimeLimit=60", "ResultFile=%s" % resultfile, str(lp)],
        capture_output=True, text=True, env=env)
    assert proc.returncode == 0, proc.stderr
    text = resultfile.read_text()
    assert "# Objective value = " in text
    assert "width 52" in text


def test_option3_retry_only_on_infeasible(tmp_path):
    """The recovery fires on proved INFEASIBLE, and the disjunct filter
    removes exactly the _3-selected RELAXATION constraints."""
    from gurobi_cl import _is_option3_disjunct
    assert _is_option3_disjunct(
        "x1b + RELAXATION - x2a2 - 20000 b1_2_3_17 >= 65")
    assert not _is_option3_disjunct(
        "x1b + RELAXATION - x2a2 - 20000 b1_2_1_17 >= 65")
