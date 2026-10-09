"""Unit tests for flow/benefit.py (growth benefit estimation, P0-3)."""
import pytest

from benefit import ShrinkModel, make_growth_benefit_estimator


def test_unseen_size_falls_back_to_prior():
    m = ShrinkModel(prior=0.95)
    assert m.estimate_shrink(4) == 0.95
    assert m.estimate_benefit([0.76], 0.95, 2, 10) > 0


def test_observed_shrink_uses_conservative_max():
    m = ShrinkModel()
    m.observe(4, 4.0, 3.6)          # shrink 0.9
    m.observe(4, 4.0, 4.4)          # shrink 1.1 (worse than the sum)
    assert m.estimate_shrink(4) == pytest.approx(1.1)


def test_complex10_shape_would_be_pruned_after_observation():
    # The adder lesson: at 5 cells the generated layout came out wider
    # (5.89) than the sum of its baselines (4.94).
    m = ShrinkModel()
    m.observe(5, 4.94, 5.89)
    est = m.estimate_benefit([0.76, 0.76, 0.95, 1.52], 0.95, 5, 59)
    assert est < 0


def test_ignores_degenerate_observations():
    m = ShrinkModel()
    m.observe(3, 0.0, 4.0)          # 0x0 layout: no signal
    m.observe(3, 4.0, -1.0)
    assert m.estimate_shrink(3) == m.prior


def test_estimator_unknown_width_does_not_veto():
    est = make_growth_benefit_estimator({"NAND2X1": 0.76}, ShrinkModel())
    assert est(["NAND2X1"], "MISSINGTYPE", 2, 5) == float("inf")
    assert est(["MISSINGTYPE"], "NAND2X1", 2, 5) == float("inf")
