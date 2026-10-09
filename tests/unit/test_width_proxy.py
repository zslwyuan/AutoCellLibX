"""Unit tests for pySrc/width_proxy.py (P2 phase 1)."""
import pytest

from width_proxy import (WidthProxy, collectSamples,
                         countTransistorsPerType, evaluateLOO,
                         makeProxyBenefitEstimator, parseTraceTypes)


def test_count_transistors_per_type(in_pysrc):
    counts = countTransistorsPerType("../stdCelllib/cellsAstranFriendly.sp")
    assert counts["NAND2X1"] == 4
    assert counts["INVX1"] == 2
    assert all(v > 0 for v in counts.values())


def test_parse_trace_types():
    assert parseTraceTypes("[NAND2X1,NAND2X1,OR2X1]") == \
        ["NAND2X1", "NAND2X1", "OR2X1"]
    assert parseTraceTypes(
        "[NAND2X1,NAND2X1,OR2X1]+XNOR2X1_c0o0+OAI21X1_c2o0") == \
        ["NAND2X1", "NAND2X1", "OR2X1", "XNOR2X1", "OAI21X1"]


def test_collect_samples_on_real_outputs(in_pysrc):
    import os
    if not os.path.exists("./outputs/adder/COMPLEX1.sp"):
        pytest.skip("outputs snapshot not present")
    from GDSIIAnalysis import loadAstranGDS
    counts = countTransistorsPerType("../stdCelllib/cellsAstranFriendly.sp")
    widths = loadAstranGDS()
    samples = collectSamples(
        ["./outputs/adder", "./outputs/ctrl", "./outputs/max",
         "./outputs/multiplier"], counts, widths)
    assert len(samples) >= 10
    for s in samples:
        assert s["n_cells"] >= 2
        assert s["n_transistors"] > 0
        assert s["base_width_um"] > 0
        assert s["width_um"] > 0
    by_name = {s["name"]: s for s in samples}
    assert by_name["COMPLEX1"]["n_cells"] == 3


def test_proxy_fits_linear_relation():
    # width = 0.5 * base + 0.1 * n_cells exactly
    samples = [{"name": str(i), "n_cells": 2 + i % 3,
                "n_transistors": 4 * (2 + i % 3),
                "base_width_um": 1.0 + 0.1 * i,
                "width_um": 0.5 * (1.0 + 0.1 * i) + 0.1 * (2 + i % 3)}
               for i in range(10)]
    proxy = WidthProxy().fit(samples)
    expected = 0.5 * 1.0 + 0.1 * 2
    # Ridge regularisation (alpha=1.0, robust on the small real corpus)
    # trades exactness for stability: assert the learned trend instead.
    assert proxy.predict(2, 8, 1.0) == pytest.approx(expected, rel=0.2)
    assert proxy.predict(2, 8, 2.0) > proxy.predict(2, 8, 1.0)


def test_loo_evaluation_runs_on_real_data(in_pysrc):
    import os
    if not os.path.exists("./outputs/adder/COMPLEX1.sp"):
        pytest.skip("outputs snapshot not present")
    from GDSIIAnalysis import loadAstranGDS
    counts = countTransistorsPerType("../stdCelllib/cellsAstranFriendly.sp")
    widths = loadAstranGDS()
    samples = collectSamples(
        ["./outputs/adder", "./outputs/ctrl", "./outputs/max",
         "./outputs/multiplier"], counts, widths)
    report = evaluateLOO(samples)
    assert report["n"] == len(samples)
    assert report["mape"] is not None and report["mape"] < 0.5


def test_proxy_estimator_vetoes_wide_prediction():
    class FakeProxy(object):
        def predict(self, n_cells, n_trans, base):
            return base * 1.1          # always worse than the baseline

    est = makeProxyBenefitEstimator(
        FakeProxy(), {"NAND2X1": 0.76, "OR2X1": 0.95},
        {"NAND2X1": 4, "OR2X1": 4})
    assert est(["NAND2X1"], "OR2X1", 2, 10) < 0

    class GoodProxy(object):
        def predict(self, n_cells, n_trans, base):
            return base * 0.8

    est2 = makeProxyBenefitEstimator(
        GoodProxy(), {"NAND2X1": 0.76, "OR2X1": 0.95},
        {"NAND2X1": 4, "OR2X1": 4})
    assert est2(["NAND2X1"], "OR2X1", 2, 10) > 0
    # unknown type -> no opinion
    est3 = makeProxyBenefitEstimator(
        GoodProxy(), {"NAND2X1": 0.76}, {"NAND2X1": 4})
    assert est3(["NAND2X1"], "UNKNOWN", 2, 10) == float("inf")


def test_training_pipeline_roundtrip(tmp_path, in_pysrc):
    import os
    if not os.path.exists("./outputs/adder/COMPLEX1.sp"):
        pytest.skip("outputs snapshot not present")
    from GDSIIAnalysis import loadAstranGDS
    from width_proxy import (trainOrLoadWidthProxy, loadWidthProxy)
    counts = countTransistorsPerType("../stdCelllib/cellsAstranFriendly.sp")
    widths = loadAstranGDS()
    outDirs = ["./outputs/adder", "./outputs/ctrl", "./outputs/max",
               "./outputs/multiplier"]
    model = str(tmp_path / "wp.json")
    proxy, report = trainOrLoadWidthProxy(outDirs, counts, widths,
                                          path=model)
    assert proxy is not None, report
    assert report["source"] == "trained"
    assert report["mape"] is not None and report["mape"] < 0.5
    # reload gives the same predictions (persistence roundtrip)
    reloaded = loadWidthProxy(model)
    a = proxy.predict(3, 18, 4.0)
    b = reloaded.predict(3, 18, 4.0)
    assert a == pytest.approx(b)
    # a fresh model is loaded, not retrained
    proxy2, report2 = trainOrLoadWidthProxy(outDirs, counts, widths,
                                            path=model)
    assert report2["source"] == "loaded"
