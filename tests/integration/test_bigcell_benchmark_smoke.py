"""Integration smoke for the bigcell benchmark harness (marked ``slow``).

Runs the REAL engine (rung 1: smt-exact) end to end over two real
benchmark cells and checks that honest artifacts (.sp/.gds pairs,
invariant 7) plus verify/sanity-clean records come out of it.  Needs
only the Python engine -- no ASTRAN run is triggered (the pdk_drc cells
have no .Astranlog, so their baseline is an honest "missing").
"""
import json
import os

import pytest

pytestmark = pytest.mark.slow

from bigcell_engine.benchmark import load_benchmark_cells, run_benchmark


def _pick(cells, sources):
    by_src = {c.source: c for c in cells}
    return [by_src[s] for s in sources]


def test_benchmark_end_to_end_exact_rung(in_flow, tmp_path):
    """End-to-end through the ladder's narrowest-closing policy: rung 1
    closes as a candidate, the slot chain wins on width, and the report
    carries the slot-model artifacts with a same-semantics ratio."""
    cells = _pick(load_benchmark_cells(),
                  ["outputs/pdk_drc/inv.sp", "outputs/pdk_drc/nand2.sp"])
    out = os.path.join(str(tmp_path), "bench")
    report = run_benchmark(cells, out, exact_budget_s=60.0,
                           allow_baseline_runs=False)
    recs = {r["source"]: r for r in report["cells"]}
    for src, rec in recs.items():
        assert rec["status"] == "ok", (src, rec.get("note"))
        assert rec["engine"] == "bigcell-full"
        assert rec["python_um"] and rec["python_um"] > 0
        assert rec["astran_um"] is None and \
            report["summary"]["baselines"]["missing_or_failed"] == 2
        # real artifacts on disk, .gds fresher than its .sp (invariant 7)
        stem = src[:-3]
        sp = os.path.join(out, *stem.split("/")) + ".sp"
        gds = os.path.join(out, *stem.split("/")) + ".gds"
        assert os.path.exists(sp) and os.path.exists(gds)
        assert os.path.getmtime(gds) >= os.path.getmtime(sp)
        assert rec["verdicts"]["verify"]["ok"] is True
        assert rec["verdicts"]["sanity"]["ok"] is True
    # the report is self-describing
    on_disk = json.load(open(os.path.join(out, "report.json")))
    assert on_disk["summary"]["ok"] == 2
    assert on_disk["summary"]["verified_ok"] == 2
    assert on_disk["summary"]["sanity_ok"] == 2
