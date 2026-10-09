"""Unit tests for flow/llm_hint_provider.py (P2 stage 3)."""
import pytest

from llm_hint_provider import (Hint, OfflineHintProvider, OpenAiHintProvider,
                               get_hint_provider, hint_cache_key,
                               suggest_hints_batch)

WIDE_NETLIST = """\
.subckt C0 VCC Y GND
Ma Y A VCC VCC PMOS W=2.4u L=0.05u
Mb Y A GND GND NMOS W=0.5u L=0.05u
.end
"""


def test_offline_hints_deterministic():
    p = OfflineHintProvider(max_leg_um=1.0)
    a = p.suggest_hints("C0", WIDE_NETLIST)
    b = p.suggest_hints("C0", WIDE_NETLIST)
    assert [h.as_dict() for h in a] == [h.as_dict() for h in b]
    assert len(a) == 1
    assert a[0].kind == "fold_max"
    assert a[0].target == "Ma"
    assert a[0].value == 3          # ceil(2.4 / 1.0)
    assert a[0].source == "offline"


def test_offline_no_hints_for_narrow_devices():
    p = OfflineHintProvider(max_leg_um=1.0)
    assert p.suggest_hints("C0", WIDE_NETLIST.replace("W=2.4u", "W=1.0u")) == []


def test_hint_cache_key_is_content_addressed():
    k1 = hint_cache_key("net", {"grid": 0.19}, "m1")
    k2 = hint_cache_key("net", {"grid": 0.19}, "m1")
    k3 = hint_cache_key("net2", {"grid": 0.19}, "m1")
    assert k1 == k2 and k1 != k3
    assert len(k1) == 64            # sha256 hex


def test_mode_gating(monkeypatch):
    env = {}
    assert get_hint_provider(env=env) is None          # default off
    assert get_hint_provider(mode="offline", env=env) is not None
    assert get_hint_provider(mode="off", env=env) is None
    assert get_hint_provider(mode="bogus", env=env) is None
    env2 = {"AUTOCELL_HINT_MODE": "llm"}             # no API key -> offline
    assert isinstance(get_hint_provider(env=env2), OfflineHintProvider)
    env3 = {"AUTOCELL_HINT_MODE": "llm",
            "AUTOCELL_LLM_API_KEY": "sk-test"}
    assert isinstance(get_hint_provider(env=env3), OpenAiHintProvider)


def test_cache_hit_skips_network(tmp_path):
    p = OpenAiHintProvider(api_key="sk-test", cache_path=str(tmp_path / "c.json"))
    key = hint_cache_key("net", None, p.model)
    p._cache[key] = [{"kind": "fold_max", "target": "Ma", "value": 2}]
    hints = p.suggest_hints("C0", "net")
    assert hints == [Hint("fold_max", "Ma", 2.0, "cache")]
    assert p._client is None                        # network never touched


def test_llm_failure_degrades_to_empty(monkeypatch):
    class Boom(object):
        class chat(object):
            @staticmethod
            def completions():
                raise RuntimeError("no network")
    p = OpenAiHintProvider(api_key="sk-test",
                           cache_path=tmp_path_str())
    monkeypatch.setattr(p, "_client", Boom)
    assert p.suggest_hints("C0", WIDE_NETLIST) == []


def tmp_path_str():
    import tempfile
    import os
    return os.path.join(tempfile.gettempdir(), "hint_test_%d.json"
                        % id(object()))


def test_batch_preserves_order_and_is_deterministic():
    p = OfflineHintProvider(max_leg_um=1.0)
    cells = [("C%d" % i, WIDE_NETLIST) for i in range(8)]
    a = suggest_hints_batch(cells, p, max_workers=4)
    b = suggest_hints_batch(cells, p, max_workers=4)
    assert list(a.keys()) == list(b.keys()) == ["C%d" % i for i in range(8)]
    assert all(len(v) == 1 and v[0].target == "Ma" for v in a.values())
    assert a == b


def test_batch_with_none_provider():
    cells = [("C0", "net")]
    assert suggest_hints_batch(cells, None) == {"C0": []}


def test_flow_config_reads_hint_mode(monkeypatch):
    from core.config import FlowConfig
    monkeypatch.setenv("AUTOCELL_HINT_MODE", "llm")
    assert FlowConfig.from_env().hint_mode == "llm"
    monkeypatch.delenv("AUTOCELL_HINT_MODE")
    assert FlowConfig.from_env().hint_mode == "off"
