"""Unit tests for pySrc/yosys_eval.py."""
import pytest

from yosys_eval import (buildExtendedLiberty, compareMappedArea,
                        evaluateDesignSavings)

BASE_LIB = """library (demo) {
  cell (NAND2X1) { area : 1.8772; }
}
"""
FRAG = """  cell (COMPLEX0) {
    area : 5.6316;
    /* pattern: [NAND2X1,NAND2X1,OR2X1] */
  }
"""


def test_build_extended_liberty_inserts_before_close():
    merged = buildExtendedLiberty(BASE_LIB, [FRAG])
    assert merged.count("cell (") == 2
    assert merged.rstrip().endswith("}")
    assert "COMPLEX0" in merged
    from liberty.parser import parse_liberty
    parsed = parse_liberty(merged)
    assert len(parsed.get_groups("cell")) == 2


def test_build_extended_liberty_rejects_broken_base():
    with pytest.raises(ValueError):
        buildExtendedLiberty("no braces here", [FRAG])


def test_evaluate_design_savings_math():
    stat = {"ok": True, "histogram": {"NAND2X1": 100, "OR2X1": 10}}
    libAreas = {"NAND2X1": 2.0, "OR2X1": 3.0}
    accepted = [("COMPLEX9", 10, ["NAND2X1", "NAND2X1", "OR2X1"])]
    complexAreas = {"COMPLEX9": 5.5}
    r = evaluateDesignSavings(stat, accepted, libAreas, complexAreas)
    assert r["compared"] is True
    assert r["baseline_area"] == pytest.approx(230.0)
    # 10 x ((2+2+3) - 5.5) = 15
    assert r["saved_area"] == pytest.approx(15.0)
    assert r["saved_pct"] == pytest.approx(15.0 / 230.0 * 100)
    assert r["patterns"][0]["member_area"] == pytest.approx(7.0)


def test_evaluate_design_savings_handles_missing():
    stat = {"ok": False, "reason": "no yosys"}
    r = evaluateDesignSavings(stat, [], {}, {})
    assert r["compared"] is False
    stat2 = {"ok": True, "histogram": {"UNKNOWN": 3}}
    r2 = evaluateDesignSavings(stat2, [], {}, {})
    assert r2["compared"] is True
    assert r2["missing_area_types"] == ["UNKNOWN"]
    assert r2["baseline_area"] == 0


def test_compare_mapped_area():
    b = {"ok": True, "area": 100.0, "histogram": {}}
    e = {"ok": True, "area": 90.0,
         "histogram": {"COMPLEX9": 5, "NAND2X1": 10}}
    r = compareMappedArea(b, e)
    assert r["area_saved"] == pytest.approx(10.0)
    assert r["area_saved_pct"] == pytest.approx(10.0)
    assert r["complex_instances"] == 5
