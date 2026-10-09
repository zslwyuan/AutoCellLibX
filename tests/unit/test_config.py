"""Unit tests for pySrc/core/config.py (FlowConfig)."""
import pytest

from core.config import FlowConfig


def test_defaults_match_legacy_behavior():
    cfg = FlowConfig()
    assert cfg.top_thr == 5
    assert cfg.ratio_thr == 0.05
    assert cfg.cnt_thr == 30
    assert cfg.grow_beam_width == 2
    assert cfg.layout_sanity_gate is True
    assert cfg.use_width_proxy_for_growth is False
    assert cfg.require_reuse_eligible is False
    assert cfg.benchmarks == ("adder",)
    assert cfg.output_dir("adder") == "./outputs/adder/"


def test_tc008_special_threshold():
    cfg = FlowConfig()
    assert cfg.ratio_thr_for("adder") == 0.05
    assert cfg.ratio_thr_for("tc_008_arthmetic_sin") == 0.025


def test_from_env_reuse_mode(monkeypatch):
    monkeypatch.delenv("AUTOCELL_REUSE_MODE", raising=False)
    cfg = FlowConfig.from_env()
    assert cfg.reuse_mode is False
    assert cfg.output_suffix == ""
    assert cfg.require_reuse_eligible is False
    monkeypatch.setenv("AUTOCELL_REUSE_MODE", "1")
    cfg2 = FlowConfig.from_env()
    assert cfg2.reuse_mode is True
    assert cfg2.output_suffix == "_reuse"
    assert cfg2.require_reuse_eligible is True
    assert cfg2.output_dir("adder") == "./outputs/adder_reuse/"


def test_astran_disabled_by_default():
    assert FlowConfig().astran_build_path == ""
