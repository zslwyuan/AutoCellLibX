"""Unit tests for the core/evaluate + core/external facades."""
import pytest


def test_evaluate_facade_exposes_the_evaluation_surface():
    import core.evaluate as ev
    for name in ("loadCellElectricalMetrics", "patternElectricalMetrics",
                 "loadTimingPower", "patternTimingPower", "stageDelaySlew",
                 "loadCellRoutability", "checkLayout", "reuseEligible",
                 "functionComplexity", "WidthProxy", "collectSamples",
                 "makeProxyBenefitEstimator", "ShrinkModel",
                 "generateComplexLiberty", "loadLibertyFunctions",
                 "getPdk", "pdkGeometryDict"):
        assert hasattr(ev, name), name


def test_external_facade_exposes_the_tool_surface():
    import core.external as ex
    for name in ("runAstranForNetlist", "loadAstranArea",
                 "astranLayoutIsStale", "ASTRAN_BUILD_PATH", "GUROBI_CL",
                 "ASTRAN_TECHNOLOGY", "loadAstranGDS",
                 "loadOrignalGSCL45nmGDS", "findYosys", "runYosysStat",
                 "compareCellCounts", "buildExtendedLiberty",
                 "evaluateDesignSavings"):
        assert hasattr(ex, name), name


def test_facades_are_qt_free():
    import core.evaluate, core.external
    import inspect, sys
    for mod in (core.evaluate, core.external):
        assert "PySide6" not in inspect.getsource(mod)


def test_pipeline_imports_match_facade_objects():
    """The names pipeline uses must resolve to the very same objects the
    facades export (single source of truth, no duplicate bindings)."""
    import core.pipeline as pl
    import core.evaluate as ev
    import core.external as ex
    for name in ("runAstranForNetlist", "loadAstranArea",
                 "astranLayoutIsStale", "ASTRAN_BUILD_PATH", "GUROBI_CL",
                 "ASTRAN_TECHNOLOGY", "loadAstranGDS",
                 "loadOrignalGSCL45nmGDS", "findYosys", "runYosysStat",
                 "compareCellCounts", "loadCellElectricalMetrics",
                 "patternElectricalMetrics", "loadTimingPower",
                 "patternTimingPower", "loadCellRoutability", "checkLayout",
                 "reuseEligible", "WidthProxy", "collectSamples",
                 "makeProxyBenefitEstimator", "ShrinkModel",
                 "generateComplexLiberty", "loadLibertyFunctions"):
        fac = getattr(ev, name, None) or getattr(ex, name, None)
        assert fac is not None, name
        assert getattr(pl, name) is fac, name
