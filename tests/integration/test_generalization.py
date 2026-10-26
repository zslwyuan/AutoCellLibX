"""Integration tests for the hold-out generalization evaluation
(flow/_generalization + bigcell_engine.benchmark.run_generalization).

Two layers, both marked ``slow``:

- the committed hold-out decks reproduce byte-for-byte from their
  Verilog sources through the real yosys+abc+flatten pipeline (the
  determinism contract of the hold-out set; needs the vendored yosys,
  skipped when it is absent);
- the REAL engine ladder (no ASTRAN, no baselines) runs a
  representative slice of the hold-out set end to end -- the four
  single-gate small cells must close with verify/sanity/quality, and
  the NOR3-class probe (a known dev-set wall) must close OR fail with
  its honest structural diagnosis recorded (the harness is pinned
  here, not the research outcome).
"""
import json
import os

import pytest

pytestmark = pytest.mark.slow

from bigcell_engine import benchmark as benchmark_mod       # noqa: E402
from bigcell_engine.benchmark import (load_holdout_cells,     # noqa: E402
                                      run_generalization)


def test_holdout_decks_reproduce_from_verilog(in_flow, tmp_path):
    """yosys -> abc -> flatten must regenerate the committed decks."""
    from yosys_import import find_yosys
    if (find_yosys() is None):
        pytest.skip("no yosys executable (vendored tools/yosys missing)")

    import importlib.util
    flow_dir = os.path.dirname(os.path.dirname(os.path.abspath(
        benchmark_mod.__file__)))
    gen_py = os.path.join(flow_dir, "_generalization", "generate.py")
    spec = importlib.util.spec_from_file_location("holdout_generate",
                                                  gen_py)
    holdout_generate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(holdout_generate)

    generated = holdout_generate.generate(str(tmp_path))
    ok, rows = holdout_generate.check_against_committed(generated)
    assert ok, ("regenerated decks differ from the committed ones: %s"
                % [r["module"] for r in rows if not r["match"]])
    assert len(generated) >= 20                  # the ~20-module contract
    # every deck is a single .subckt named after its module
    for stem, info in sorted(generated.items()):
        header = info["spice"].splitlines()[0]
        assert header.startswith(".subckt %s " % stem), header
        assert info["transistors"] > 0


def test_generalization_ladder_on_holdout_slice(in_flow, tmp_path):
    """The real ladder over a representative hold-out slice.

    The four single-gate small cells (AND/AOI/OAI classes -- all close
    on the dev set) must close with the full quality panel; the NOR3
    probe must either close or report its structural diagnosis.  No
    ASTRAN baseline exists or is generated -- the hold-out contract.
    """
    cells = load_holdout_cells()
    by_name = {c.name: c for c in cells}
    for name in ("and2v", "aoi21v", "aoi22v", "oai21v", "nor3v"):
        assert name in by_name, name
    slice_cells = [by_name[n] for n in
                   ("and2v", "aoi21v", "aoi22v", "oai21v", "nor3v")]

    out = os.path.join(str(tmp_path), "gen")
    dev = {"cells": [                    # dev-set proxy for the verdict
        {"name": "AND2X1", "source": "library/AND2X1.sp", "T": 6,
         "status": "ok"},
        {"name": "AOI21X1", "source": "library/AOI21X1.sp", "T": 6,
         "status": "ok"},
        {"name": "AOI22X1", "source": "library/AOI22X1.sp", "T": 8,
         "status": "ok"},
        {"name": "NOR3X1", "source": "library/NOR3X1.sp", "T": 9,
         "status": "unsupported"},
    ]}
    result = run_generalization(out, dev_report=dev, cells=slice_cells,
                                baselines={})
    records = {r["name"]: r for r in result["holdout"]["cells"]}

    for name in ("and2v", "aoi21v", "aoi22v", "oai21v"):
        rec = records[name]
        assert rec["status"] in ("ok", "cached"), (name, rec.get("note"))
        assert rec["engine"], name
        assert rec["python_um"] > 0, name
        assert rec["verdicts"]["verify"]["ok"] is True, name
        assert rec["verdicts"]["sanity"]["ok"] is True, name
        quality = rec["quality"]
        assert isinstance(quality["pin_access"]["score"], float), name
        assert 0.0 <= quality["pin_access"]["score"] <= 1.0, name
        assert quality["pin_access"]["n_pins"] > 0, name
        # the sanity metrics surface the artifact's own geometry: the
        # metal1 extent (which includes the route escape overhang --
        # wider than the nominal width by design) and the row height
        assert quality["sanity_metrics"]["width_um"] > 0, name
        assert quality["sanity_metrics"]["height_um"] == \
            pytest.approx(2.47, abs=0.05), name
        assert quality["runtime_s"]["total"] >= 0.0, name
        # the artifacts honour the cache contract
        stem = rec["source"][:-3]
        gds = os.path.join(out, *stem.split("/")) + ".gds"
        assert os.path.exists(gds), gds
        assert rec["astran_um"] is None        # no baseline, by design

    nor = records["nor3v"]
    if (nor["status"] in ("ok", "cached")):
        assert nor["verdicts"]["verify"]["ok"] is True
    else:
        assert nor["status"] == "unsupported"
        assert "no engine closed the cell" in nor["note"]
        assert nor["attempts"]                # the honest diagnosis trail
        assert nor["quality"]["runtime_s"]["total"] > 0.0

    # the band table and the verdict are computed from the run
    assert result["bands"]["small"]["cells"] == 4
    assert result["bands"]["medium"]["cells"] == 1
    # dev proxy: three small cells (T<=8) all closed; NOR3X1 (9T) is a
    # MEDIUM-band dev cell, unsupported there
    assert result["dev_bands"]["small"]["rate"] == 1.0
    assert result["dev_bands"]["medium"] == {"cells": 1, "closed": 0,
                                             "rate": 0.0}
    assert result["verdict"]
    gen_md = open(os.path.join(out, "generalization.md")).read()
    assert "Verdict" in gen_md and "nor3v" in gen_md
    gen_json = json.load(open(os.path.join(out, "generalization.json")))
    assert gen_json["bands"]["small"]["cells"] == 4
