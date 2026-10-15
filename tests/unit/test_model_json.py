"""Unit tests for the stage-1 JSON compaction model path.

Covers tools/gurobi_cl/model_json.py (schema loader + python-mip builder with
the legacy solver policy) and tools/gurobi_cl/lp_to_json.py (LP -> JSON
bridge, so the JSON path can be validated before the in-ASTRAN dump hook is
compiled in).  Conventions follow tests/unit/test_cpsat_backend.py.
"""
import json
import os
import subprocess
import sys

import pytest

TOOLS = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..",
                 "tools", "gurobi_cl"))
sys.path.insert(0, TOOLS)

lp_to_json = pytest.importorskip("lp_to_json")
model_json = pytest.importorskip("model_json")

# Same tiny model as tests/unit/test_cpsat_backend.py (known optimum: the
# minimal width is 52; xa >= 13, xb >= xa + 26, width >= xb + 13).
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

TINY_JSON = {
    "meta": {
        "format_version": 1,
        "generator": "unit-test",
        "source_lp": "tiny.lp",
        "objective": {"sense": "min",
                      "terms": [{"var": "width", "coef": 5000.0},
                                {"var": "xa", "coef": 3.0},
                                {"var": "bsel", "coef": 1.0}]},
        "dropped_no_operator": 0,
        "dropped_nonfinite_terms": 0,
    },
    "variables": [
        {"name": "xgpos", "lb": 0, "ub": None, "integer": True},
        {"name": "bsel", "lb": 0, "ub": 1, "integer": True},
        {"name": "width", "lb": 0, "ub": None, "integer": True},
        {"name": "xa", "lb": 0, "ub": None, "integer": False},
        {"name": "xb", "lb": 0, "ub": None, "integer": False},
        {"name": "ZERO", "lb": 0, "ub": None, "integer": False},
    ],
    "constraints": [
        {"name": "c1", "terms": [{"var": "xb", "coef": 1.0},
                                 {"var": "xa", "coef": -1.0}],
         "sense": ">=", "rhs": 26.0},
        {"name": "c2", "terms": [{"var": "width", "coef": 1.0},
                                 {"var": "xb", "coef": -1.0}],
         "sense": ">=", "rhs": 13.0},
        {"name": "c3", "terms": [{"var": "xa", "coef": 1.0},
                                 {"var": "ZERO", "coef": -1.0}],
         "sense": ">=", "rhs": 13.0},
        {"name": "c6", "terms": [{"var": "ZERO", "coef": 1.0}],
         "sense": "=", "rhs": 0.0},
    ],
}


def _write_json(tmp_path, data, name="model.json"):
    path = tmp_path / name
    path.write_text(json.dumps(data))
    return str(path)


def test_build_mip_model_variables_and_constraints(tmp_path):
    import mip
    data = model_json.load_model(_write_json(tmp_path, TINY_JSON))
    model = model_json.build_mip_model(data)
    # column order == JSON variables order == legacy creation order
    assert [v.name for v in model.vars] == \
        [v["name"] for v in TINY_JSON["variables"]]
    kinds = {v.name: v.var_type for v in model.vars}
    assert kinds["bsel"] == mip.BINARY
    assert kinds["xgpos"] == mip.INTEGER
    assert kinds["width"] == mip.INTEGER
    assert kinds["xa"] == mip.CONTINUOUS
    # 4 JSON constraints, none filtered without drop_option3
    assert len(model.constrs) == 4


def test_build_mip_model_option3_drop(tmp_path):
    data = json.loads(json.dumps(TINY_JSON))
    data["constraints"].append(
        {"name": "c7", "terms": [{"var": "xb", "coef": 1.0},
                                 {"var": "RELAXATION", "coef": -1.0},
                                 {"var": "b0_1_3_7", "coef": -1.0}],
         "sense": ">=", "rhs": 26.0})
    data["variables"].append(
        {"name": "RELAXATION", "lb": 0, "ub": None, "integer": False})
    data["variables"].append(
        {"name": "b0_1_3_7", "lb": 0, "ub": 1, "integer": True})
    model = model_json.build_mip_model(data)
    assert len(model.constrs) == 5
    dropped = model_json.build_mip_model(data, drop_option3=True)
    assert len(dropped.constrs) == 4   # only the option-3 disjunct removed


def test_is_option3_disjunct_matches_legacy_semantics():
    def con(terms):
        return {"name": "C", "terms": terms, "sense": ">=", "rhs": 0.0}

    # selector b<A>_<B>_<option=3>_<uid> + RELAXATION term: the repair target
    assert model_json.is_option3_disjunct(con(
        [{"var": "x13a2", "coef": 1.0}, {"var": "x3b", "coef": -1.0},
         {"var": "y13a2", "coef": 1.0}, {"var": "y3b", "coef": -1.0},
         {"var": "RELAXATION", "coef": 1.0},
         {"var": "b3_13_3", "coef": -20.0}]))
    # ... also when the uid continues after the _3 option field
    assert model_json.is_option3_disjunct(con(
        [{"var": "x1", "coef": 1.0}, {"var": "RELAXATION", "coef": 1.0},
         {"var": "b13_19_3_108", "coef": -1.0}]))
    # RELAXATION but a non-3 selector: not an option-3 disjunct
    assert not model_json.is_option3_disjunct(con(
        [{"var": "x1", "coef": 1.0}, {"var": "RELAXATION", "coef": 1.0},
         {"var": "b13_19_2", "coef": -1.0}]))
    # _3 selector but no RELAXATION: not an option-3 disjunct
    assert not model_json.is_option3_disjunct(con(
        [{"var": "x1", "coef": 1.0}, {"var": "b13_19_3", "coef": -1.0}]))
    # no terms at all
    assert not model_json.is_option3_disjunct(con([]))


def test_option3_repair_fires_on_proved_infeasible(tmp_path):
    """A model that is infeasible only through an option-3 disjunct is
    INFEASIBLE first, then solved after dropping that disjunct."""
    data = {
        "meta": {"format_version": 1, "generator": "unit-test",
                 "source_lp": "t.lp",
                 "objective": {"sense": "min", "terms":
                               [{"var": "x", "coef": 1.0}]},
                 "dropped_no_operator": 0, "dropped_nonfinite_terms": 0},
        "variables": [
            {"name": "x", "lb": 0, "ub": None, "integer": False},
            {"name": "RELAXATION", "lb": 0, "ub": None, "integer": False},
            {"name": "bA_B_3_7", "lb": 0, "ub": 1, "integer": True},
            {"name": "ZERO", "lb": 0, "ub": None, "integer": False},
        ],
        "constraints": [
            # pin the selector to 0 (as ASTRAN's end-line pinning does), so
            # the disjunct below is enforced unconditionally
            {"name": "C0", "terms": [{"var": "bA_B_3_7", "coef": 1.0}],
             "sense": "<=", "rhs": 0.0},
            {"name": "C1", "terms": [{"var": "x", "coef": 1.0}],
             "sense": "<=", "rhs": 0.0},
            {"name": "C2", "terms": [{"var": "RELAXATION", "coef": 1.0}],
             "sense": "<=", "rhs": 0.0},
            # option-3 disjunct: with the selector at 0 it forces x >= 1,
            # contradicting C1 -- the model is *proved* INFEASIBLE
            {"name": "C3", "terms": [{"var": "x", "coef": 1.0},
                                     {"var": "RELAXATION", "coef": -1.0},
                                     {"var": "bA_B_3_7", "coef": -1.0}],
             "sense": ">=", "rhs": 1.0},
            {"name": "C4", "terms": [{"var": "ZERO", "coef": 1.0}],
             "sense": "=", "rhs": 0.0},
        ],
    }
    assert model_json.is_option3_disjunct(data["constraints"][3])
    import mip
    # phase 1 on the unmodified model: proved INFEASIBLE
    first = model_json.build_mip_model(data, drop_option3=False)
    assert first.optimize(max_seconds=60) == mip.OptimizationStatus.INFEASIBLE
    # the policy's recovery (drop the option-3 disjuncts) makes it feasible
    status, model = model_json.solve_with_policy(data, phase1=60, retry=0)
    assert status in (mip.OptimizationStatus.OPTIMAL,
                      mip.OptimizationStatus.FEASIBLE)
    byname = {v.name: v.x for v in model.vars}
    assert byname["x"] == 0
    # and the full policy recovers on its own when the first phase proves
    # infeasibility (run via run_json_path, which also writes the .sol)
    jpath = _write_json(tmp_path, data)
    sol = tmp_path / "t.sol"
    assert model_json.run_json_path(jpath, 60, str(sol), phase1=60, retry=0) == 0
    entries = {}
    for line in sol.read_text().splitlines():
        if line.startswith("#"):
            continue
        name, value = line.rsplit(" ", 1)
        entries[name] = int(value)
    assert entries == {"x": 0, "RELAXATION": 0, "bA_B_3_7": 0, "ZERO": 0}


def test_lp_to_json_drops_inf_terms(tmp_path):
    """inf coefficients mean 'no bound': the term vanishes in the JSON
    (never clamped to big-M), like the legacy parser."""
    lp = tmp_path / "inf.lp"
    lp.write_text("""Minimize
 3 width
Subject To
 c1: width - xa >= 13
 c2: xa - ZERO >= 13
 c3: astranExpr0 - ya - inf xa = 0
 c4: ya - ZERO >= 2
 czero: ZERO = 0
Generals
 width
End
""")
    data = lp_to_json.convert_lp_to_json(str(lp))
    byname = {c["name"]: c for c in data["constraints"]}
    # the inf term is gone from c3; the definition constraint survives as an
    # ordinary constraint (never collapsed)
    assert [(t["var"], t["coef"]) for t in byname["c3"]["terms"]] == \
        [("astranExpr0", 1.0), ("ya", -1.0)]
    assert data["meta"]["dropped_nonfinite_terms"] == 1
    # names verbatim, including the constant-zero constraint
    assert byname["czero"]["terms"] == [{"var": "ZERO", "coef": 1.0}]
    assert byname["czero"]["sense"] == "="
    # xa still exists (it appears in c1), but not inside c3
    names = [v["name"] for v in data["variables"]]
    assert "xa" in names and "astranExpr0" in names

    import mip
    status, model = model_json.solve_with_policy(data, phase1=60, retry=0)
    assert status in (mip.OptimizationStatus.OPTIMAL,
                      mip.OptimizationStatus.FEASIBLE)
    assert model.objective_value == pytest.approx(78.0)  # 3 * (13 + 13)


def test_lp_to_json_tiny_lp_optimum_via_json_path(tmp_path):
    lp = tmp_path / "tiny.lp"
    lp.write_text(TINY_LP)
    data = lp_to_json.convert_lp_to_json(str(lp))
    # constraint names preserved verbatim
    assert [c["name"] for c in data["constraints"]] == \
        ["c1", "c2", "c3", "c4", "c5", "c6"]
    import mip
    status, model = model_json.solve_with_policy(data, phase1=60, retry=0)
    assert status in (mip.OptimizationStatus.OPTIMAL,
                      mip.OptimizationStatus.FEASIBLE)
    values = {v.name: v.x for v in model.vars}
    assert values["width"] == pytest.approx(52)
    # big-M terms are carried as-is (c5's 20000 bsel)
    c5 = [c for c in data["constraints"] if c["name"] == "c5"][0]
    assert {"var": "bsel", "coef": 20000.0} in c5["terms"]


def test_sol_output_name_fidelity(tmp_path):
    """The .sol keeps the exact names ASTRAN looks up, incl. astranExprN."""
    data = json.loads(json.dumps(TINY_JSON))
    data["variables"] += [
        {"name": "astranExpr3", "lb": 0, "ub": None, "integer": False},
    ]
    data["constraints"].append(
        {"name": "cexpr3", "terms": [{"var": "astranExpr3", "coef": 1.0},
                                     {"var": "xb", "coef": -1.0}],
         "sense": "=", "rhs": 0.0})
    jpath = _write_json(tmp_path, data)
    sol = tmp_path / "out.sol"
    assert model_json.run_json_path(jpath, 60, str(sol), phase1=60, retry=0) == 0
    entries = {}
    for line in sol.read_text().splitlines():
        if line.startswith("#"):
            continue
        name, value = line.rsplit(" ", 1)
        entries[name] = int(value)
    assert set(entries) == {v["name"] for v in data["variables"]}
    assert entries["width"] == 52
    assert entries["astranExpr3"] == entries["xb"] == 39
    assert "# Objective value = " in sol.read_text()


def test_gurobi_cl_json_env_end_to_end(tmp_path):
    """gurobi_cl.py with ASTRAN_MODEL_DUMP set to a fresh JSON solves the
    JSON, not the LP (additive env-gated branch)."""
    lp = tmp_path / "m.lp"
    lp.write_text(TINY_LP)
    data = lp_to_json.convert_lp_to_json(str(lp))
    jpath = _write_json(tmp_path, data)
    sol = tmp_path / "m.sol"
    env = dict(os.environ, ASTRAN_MODEL_DUMP=jpath, GUROBI_CL_SOLVER="cbc")
    proc = subprocess.run(
        [sys.executable, os.path.join(TOOLS, "gurobi_cl.py"),
         "TimeLimit=60", "ResultFile=%s" % sol, str(lp)],
        capture_output=True, text=True, env=env, cwd=TOOLS)
    assert proc.returncode == 0, proc.stderr
    values = {}
    for line in sol.read_text().splitlines():
        if line.startswith("#"):
            continue
        name, value = line.rsplit(" ", 1)
        values[name] = int(value)
    assert values["width"] == 52
    assert "JSON model path" in (proc.stdout + proc.stderr)


def test_gurobi_cl_legacy_default_unchanged(tmp_path):
    """Without ASTRAN_MODEL_DUMP the shim must behave exactly as before
    (legacy LP path)."""
    lp = tmp_path / "m.lp"
    lp.write_text(TINY_LP)
    sol = tmp_path / "m.sol"
    env = dict(os.environ)
    env.pop("ASTRAN_MODEL_DUMP", None)
    env["GUROBI_CL_SOLVER"] = "cbc"
    proc = subprocess.run(
        [sys.executable, os.path.join(TOOLS, "gurobi_cl.py"),
         "TimeLimit=60", "ResultFile=%s" % sol, str(lp)],
        capture_output=True, text=True, env=env, cwd=TOOLS)
    assert proc.returncode == 0, proc.stderr
    assert "JSON model path" not in (proc.stdout + proc.stderr)
    values = {}
    for line in sol.read_text().splitlines():
        if line.startswith("#"):
            continue
        name, value = line.rsplit(" ", 1)
        values[name] = int(value)
    assert values["width"] == 52


def test_load_model_rejects_invalid(tmp_path):
    bad = json.loads(json.dumps(TINY_JSON))
    bad["meta"]["format_version"] = 99
    with pytest.raises(ValueError):
        model_json.load_model(_write_json(tmp_path, bad, "v.json"))
    bad = json.loads(json.dumps(TINY_JSON))
    bad["constraints"][0]["sense"] = "=="
    with pytest.raises(ValueError):
        model_json.load_model(_write_json(tmp_path, bad, "s.json"))
    bad = json.loads(json.dumps(TINY_JSON))
    del bad["variables"]
    with pytest.raises(ValueError):
        model_json.load_model(_write_json(tmp_path, bad, "m.json"))


def test_usable_json_model_staleness(tmp_path):
    import time
    lp = tmp_path / "m.lp"
    lp.write_text(TINY_LP)
    jpath = _write_json(tmp_path, TINY_JSON)   # JSON written after the LP
    assert model_json.usable_json_model(jpath, str(lp))
    # JSON older than the LP = stale leftover of an earlier solve
    old = time.time() - 3600
    os.utime(jpath, (old, old))
    assert not model_json.usable_json_model(jpath, str(lp))
    # missing or invalid files are never usable
    assert not model_json.usable_json_model(str(tmp_path / "nope.json"))
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert not model_json.usable_json_model(str(bad))
