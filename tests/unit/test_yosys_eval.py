"""Unit tests for pySrc/yosys_eval.py."""
import pytest

from yosys_eval import (build_extended_liberty, compare_mapped_area,
                        evaluate_design_savings)

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
    merged = build_extended_liberty(BASE_LIB, [FRAG])
    assert merged.count("cell (") == 2
    assert merged.rstrip().endswith("}")
    assert "COMPLEX0" in merged
    from liberty.parser import parse_liberty
    parsed = parse_liberty(merged)
    assert len(parsed.get_groups("cell")) == 2


def test_build_extended_liberty_rejects_broken_base():
    with pytest.raises(ValueError):
        build_extended_liberty("no braces here", [FRAG])


def test_evaluate_design_savings_math():
    stat = {"ok": True, "histogram": {"NAND2X1": 100, "OR2X1": 10}}
    lib_areas = {"NAND2X1": 2.0, "OR2X1": 3.0}
    accepted = [("COMPLEX9", 10, ["NAND2X1", "NAND2X1", "OR2X1"])]
    complex_areas = {"COMPLEX9": 5.5}
    r = evaluate_design_savings(stat, accepted, lib_areas, complex_areas)
    assert r["compared"] is True
    assert r["baseline_area"] == pytest.approx(230.0)
    # 10 x ((2+2+3) - 5.5) = 15
    assert r["saved_area"] == pytest.approx(15.0)
    assert r["saved_pct"] == pytest.approx(15.0 / 230.0 * 100)
    assert r["patterns"][0]["member_area"] == pytest.approx(7.0)


def test_evaluate_design_savings_handles_missing():
    stat = {"ok": False, "reason": "no yosys"}
    r = evaluate_design_savings(stat, [], {}, {})
    assert r["compared"] is False
    stat2 = {"ok": True, "histogram": {"UNKNOWN": 3}}
    r2 = evaluate_design_savings(stat2, [], {}, {})
    assert r2["compared"] is True
    assert r2["missing_area_types"] == ["UNKNOWN"]
    assert r2["baseline_area"] == 0


def test_compare_mapped_area():
    b = {"ok": True, "area": 100.0, "histogram": {}}
    e = {"ok": True, "area": 90.0,
         "histogram": {"COMPLEX9": 5, "NAND2X1": 10}}
    r = compare_mapped_area(b, e)
    assert r["area_saved"] == pytest.approx(10.0)
    assert r["area_saved_pct"] == pytest.approx(10.0)
    assert r["complex_instances"] == 5


def test_abc_uses_function_matched_custom_cell(in_pysrc):
    """Pins the corrected conclusion (AUDIT 5.25): abc's liberty mapping
    is cone-driven -- a single-output cell whose function matches the
    logic IS used, so complex_used=0 on adder is a cone-matching issue,
    not a multi-output skip (which a second-output variant also disproves).
    Self-skips when the vendored abc-capable yosys is unavailable."""
    import subprocess
    from yosys_eval import build_extended_liberty
    from yosys_import import find_yosys
    exe = find_yosys()
    if (exe is None):
        pytest.skip("no yosys executable")
    base = open("../stdCelllib/gscl45nm.lib").read()
    frag = """
  cell (C2O) {
    area : 6.0;
    cell_leakage_power : 1.0;
    pin (A) { direction : input; capacitance : 0.002; }
    pin (B) { direction : input; capacitance : 0.002; }
    pin (C) { direction : input; capacitance : 0.002; }
    pin (D) { direction : input; capacitance : 0.002; }
    pin (Y) {
      direction : output;
      capacitance : 0;
      function : "((A B)+(C D))";
      timing() {
        related_pin : "A";
        cell_rise(delay_template_6x6) {
          index_1 ("0.1, 0.5, 1.2, 3, 4, 5");
          index_2 ("0.06, 0.24, 0.48, 0.9, 1.2, 1.8");
          values ( \
            "0.1, 0.1, 0.1, 0.1, 0.1, 0.1", \
            "0.1, 0.1, 0.1, 0.1, 0.1, 0.1", \
            "0.1, 0.1, 0.1, 0.1, 0.1, 0.1", \
            "0.1, 0.1, 0.1, 0.1, 0.1, 0.1", \
            "0.1, 0.1, 0.1, 0.1, 0.1, 0.1", \
            "0.1, 0.1, 0.1, 0.1, 0.1, 0.1");
        }
        cell_fall(delay_template_6x6) {
          index_1 ("0.1, 0.5, 1.2, 3, 4, 5");
          index_2 ("0.06, 0.24, 0.48, 0.9, 1.2, 1.8");
          values ( \
            "0.1, 0.1, 0.1, 0.1, 0.1, 0.1", \
            "0.1, 0.1, 0.1, 0.1, 0.1, 0.1", \
            "0.1, 0.1, 0.1, 0.1, 0.1, 0.1", \
            "0.1, 0.1, 0.1, 0.1, 0.1, 0.1", \
            "0.1, 0.1, 0.1, 0.1, 0.1, 0.1", \
            "0.1, 0.1, 0.1, 0.1, 0.1, 0.1");
        }
        rise_transition(delay_template_6x6) {
          index_1 ("0.1, 0.5, 1.2, 3, 4, 5");
          index_2 ("0.06, 0.24, 0.48, 0.9, 1.2, 1.8");
          values ( \
            "0.1, 0.1, 0.1, 0.1, 0.1, 0.1", \
            "0.1, 0.1, 0.1, 0.1, 0.1, 0.1", \
            "0.1, 0.1, 0.1, 0.1, 0.1, 0.1", \
            "0.1, 0.1, 0.1, 0.1, 0.1, 0.1", \
            "0.1, 0.1, 0.1, 0.1, 0.1, 0.1", \
            "0.1, 0.1, 0.1, 0.1, 0.1, 0.1");
        }
        fall_transition(delay_template_6x6) {
          index_1 ("0.1, 0.5, 1.2, 3, 4, 5");
          index_2 ("0.06, 0.24, 0.48, 0.9, 1.2, 1.8");
          values ( \
            "0.1, 0.1, 0.1, 0.1, 0.1, 0.1", \
            "0.1, 0.1, 0.1, 0.1, 0.1, 0.1", \
            "0.1, 0.1, 0.1, 0.1, 0.1, 0.1", \
            "0.1, 0.1, 0.1, 0.1, 0.1, 0.1", \
            "0.1, 0.1, 0.1, 0.1, 0.1, 0.1", \
            "0.1, 0.1, 0.1, 0.1, 0.1, 0.1");
        }
      }
    }
  }
"""
    import os, re, tempfile
    lib_text = build_extended_liberty(base, [frag])
    with tempfile.NamedTemporaryFile("w", suffix=".lib",
                                     delete=False) as f:
        f.write(lib_text)
        lib_path = f.name
    with tempfile.NamedTemporaryFile("w", suffix=".v",
                                     delete=False) as f:
        f.write("module top(input a, b, c, d, output y);"
                " assign y = (a & b) | (c & d); endmodule\n")
        v_path = f.name
    try:
        proc = subprocess.run(
            [exe, "-Q", "-T",
             "-p", ("read_liberty -lib %s; read -sv %s; synth -top top; "
                    "abc -liberty %s; stat -json" % (lib_path, v_path,
                                                     lib_path))],
            capture_output=True, text=True, timeout=300)
        m = re.search(r"\{.*\}", proc.stdout + proc.stderr, re.S)
        assert m is not None, (proc.returncode, (proc.stderr or "")[-200:])
        import json
        hist = list(json.loads(m.group(0))["modules"].values())[0][
            "num_cells_by_type"]
        assert hist.get("C2O", 0) >= 1, hist
    finally:
        os.unlink(lib_path)
        os.unlink(v_path)
