"""Unit tests for the core/evaluate + core/external facades."""
import pytest


def test_evaluate_facade_exposes_the_evaluation_surface():
    import core.evaluate as ev
    for name in ("load_cell_electrical_metrics", "pattern_electrical_metrics",
                 "load_timing_power", "pattern_timing_power", "stage_delay_slew",
                 "load_cell_routability", "check_layout", "reuse_eligible",
                 "function_complexity", "WidthProxy", "collect_samples",
                 "make_proxy_benefit_estimator", "ShrinkModel",
                 "generate_complex_liberty", "load_liberty_functions",
                 "get_pdk", "pdk_geometry_dict"):
        assert hasattr(ev, name), name


def test_external_facade_exposes_the_tool_surface():
    import core.external as ex
    for name in ("run_astran_for_netlist", "load_astran_area",
                 "astran_layout_is_stale", "ASTRAN_BUILD_PATH", "GUROBI_CL",
                 "ASTRAN_TECHNOLOGY", "load_astran_gds",
                 "load_original_gscl45_gds", "find_yosys", "run_yosys_stat",
                 "compare_cell_counts", "build_extended_liberty",
                 "evaluate_design_savings"):
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
    for name in ("run_astran_for_netlist", "load_astran_area",
                 "astran_layout_is_stale", "ASTRAN_BUILD_PATH", "GUROBI_CL",
                 "ASTRAN_TECHNOLOGY", "load_astran_gds",
                 "load_original_gscl45_gds", "find_yosys", "run_yosys_stat",
                 "compare_cell_counts", "load_cell_electrical_metrics",
                 "pattern_electrical_metrics", "load_timing_power",
                 "pattern_timing_power", "load_cell_routability", "check_layout",
                 "reuse_eligible", "WidthProxy", "collect_samples",
                 "make_proxy_benefit_estimator", "ShrinkModel",
                 "generate_complex_liberty", "load_liberty_functions"):
        fac = getattr(ev, name, None) or getattr(ex, name, None)
        assert fac is not None, name
        assert getattr(pl, name) is fac, name
