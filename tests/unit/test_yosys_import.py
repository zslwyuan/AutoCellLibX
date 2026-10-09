"""Unit tests for pySrc/yosys_import.py."""
import pytest

from yosys_import import (compareWithFlowArea, findYosys, parseStatJson,
                          runYosysStat)

FIXTURE = """{
  "modules": {
    "adder": {
      "num_wires": 800,
      "num_cells": 710,
      "area": "1518.34",
      "cell_histogram": {"NAND2X1": 192, "OR2X1": 55, "DFF_X1": 12}
    }
  }
}"""


def test_parse_stat_json_coerces_strings():
    r = parseStatJson(FIXTURE)
    assert r["area"] == pytest.approx(1518.34)
    assert r["num_cells"] == 710
    assert r["histogram"]["NAND2X1"] == 192
    assert r["modules"] == ["adder"]


def test_parse_stat_json_tolerates_missing_keys():
    r = parseStatJson('{"modules": {"m": {"num_cells": 3}}}')
    assert r["area"] is None
    assert r["num_cells"] == 3
    assert r["histogram"] == {}


def test_run_stat_graceful_without_yosys():
    r = runYosysStat("lib", "blif", yosysExe="definitely-not-yosys-xyz")
    assert r["ok"] is False
    assert "reason" in r


def test_compare_with_flow_area():
    r = compareWithFlowArea({"ok": True, "area": 100.0}, 110.0)
    assert r["compared"] is True
    assert r["rel_diff"] == pytest.approx(10.0 / 110.0)
    r2 = compareWithFlowArea({"ok": False, "reason": "missing"}, 110.0)
    assert r2["compared"] is False


def test_find_yosys_type():
    assert findYosys() is None or isinstance(findYosys(), str)
