"""Unit tests for flow/yosys_import.py."""
import pytest

from yosys_import import (compare_cell_counts, compare_with_flow_area, find_yosys,
                          parse_stat_json, run_yosys_stat)

# Real Yosys 0.69 schema (measured with yowasp-yosys).
FIXTURE = """{
   "creator": "Yosys 0.69",
   "modules": {
      "\\top": {
         "num_wires": 966,
         "num_cells": 707,
         "num_cells_by_type": {"NAND2X1": 192, "OR2X1": 71, "DFF_X1": 12}
      }
   }
}"""

LEGACY_HISTOGRAM = """{
  "modules": {
    "adder": {
      "num_wires": 800,
      "num_cells": 710,
      "area": "1518.34",
      "cell_histogram": {"NAND2X1": 192, "OR2X1": 55, "DFF_X1": 12}
    }
  }
}"""


def test_parse_real_schema_and_log_wrapped_json():
    r = parse_stat_json(FIXTURE)
    assert r["num_cells"] == 707
    assert r["area"] is None
    assert r["histogram"]["NAND2X1"] == 192


def test_parse_legacy_histogram_key_and_area_string():
    r = parse_stat_json(LEGACY_HISTOGRAM)
    assert r["area"] == pytest.approx(1518.34)
    assert r["histogram"]["NAND2X1"] == 192


def test_parse_tolerates_log_prefix_and_missing_keys():
    r = parse_stat_json('noise log line\n{\n "modules": {"m": {"num_cells": 3}}\n}\n_end of script.')
    assert r["area"] is None
    assert r["num_cells"] == 3
    assert r["histogram"] == {}


def test_run_stat_graceful_without_yosys():
    r = run_yosys_stat("lib", "blif", yosys_exe="definitely-not-yosys-xyz")
    assert r["ok"] is False
    assert "reason" in r


def test_run_stat_real_yosys_if_available(in_flow):
    if (find_yosys() is None):
        pytest.skip("no yosys executable")
    r = run_yosys_stat("../std_celllib/gscl45nm.lib",
                     "../benchmark/blif/adder.blif")
    assert r["ok"] is True
    assert r["num_cells"] == 707
    assert r["histogram"].get("NAND2X1") == 192


def test_compare_with_flow_area():
    r = compare_with_flow_area({"ok": True, "area": 100.0}, 110.0)
    assert r["compared"] is True
    assert r["rel_diff"] == pytest.approx(10.0 / 110.0)
    r2 = compare_with_flow_area({"ok": False, "reason": "missing"}, 110.0)
    assert r2["compared"] is False


def test_compare_cell_counts():
    stat = {"ok": True, "histogram": {"NAND2X1": 192, "OR2X1": 71}}
    same = compare_cell_counts(stat, {"NAND2X1": 192, "OR2X1": 71})
    assert same["compared"] is True
    assert same["diff"] == {}
    assert same["total_yosys"] == same["total_flow"] == 263
    off = compare_cell_counts(stat, {"NAND2X1": 191, "OR2X1": 71, "X": 1})
    assert off["diff"] == {"NAND2X1": (192, 191), "X": (0, 1)}
    assert compare_cell_counts({"ok": False}, {})["compared"] is False


def test_find_yosys_type():
    assert find_yosys() is None or isinstance(find_yosys(), str)
