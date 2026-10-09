"""Unit tests for pySrc/core/config.py (FlowConfig)."""
import pytest

from core.config import FlowConfig


def test_defaults_match_legacy_behavior():
    cfg = FlowConfig()
    assert cfg.topThr == 5
    assert cfg.ratioThr == 0.05
    assert cfg.cntThr == 30
    assert cfg.growBeamWidth == 2
    assert cfg.layoutSanityGate is True
    assert cfg.useWidthProxyForGrowth is False
    assert cfg.requireReuseEligible is False
    assert cfg.benchmarks == ("adder",)
    assert cfg.outputDir("adder") == "./outputs/adder/"


def test_tc008_special_threshold():
    cfg = FlowConfig()
    assert cfg.ratioThrFor("adder") == 0.05
    assert cfg.ratioThrFor("tc_008_arthmetic_sin") == 0.025


def test_from_env_reuse_mode(monkeypatch):
    monkeypatch.delenv("AUTOCELL_REUSE_MODE", raising=False)
    cfg = FlowConfig.from_env()
    assert cfg.reuseMode is False
    assert cfg.outputSuffix == ""
    assert cfg.requireReuseEligible is False
    monkeypatch.setenv("AUTOCELL_REUSE_MODE", "1")
    cfg2 = FlowConfig.from_env()
    assert cfg2.reuseMode is True
    assert cfg2.outputSuffix == "_reuse"
    assert cfg2.requireReuseEligible is True
    assert cfg2.outputDir("adder") == "./outputs/adder_reuse/"


def test_astran_disabled_by_default():
    assert FlowConfig().astranBuildPath == ""
