"""Unit tests for the verilog2cells engine selection (stage 2 M2 landing).

Fast tests only: ASTRAN is replaced by an injectable fake runner and the
SMT engine by an injectable fake ``smt_runner`` (plus one real INV-sized
SMT solve that stays well under the 10 s budget).  They pin:

* the ``--engine auto|smt|astran`` CLI contract (default auto);
* the SMT eligibility rule (small, literal PMOS/NMOS, numeric W/L);
* transparent fallback: a failing SMT attempt must route the cell
  through ASTRAN and record that;
* the engine record: CellResult.engine, the queue manifest, and the
  driver's report.md all say which engine produced each cell.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "flow"))

import verilog2cells as v2c                     # noqa: E402
from astran_queue import CellResult, run_queue  # noqa: E402
from astran_queue import (run_smt_cell, smt_eligible,
                          SMT_MAX_TRANSISTORS)  # noqa: E402

INV_SP = (".subckt {name} A Y VCC GND\n"
          "M0 Y A VCC VCC PMOS W=0.5u L=0.05u\n"
          "M1 Y A GND GND NMOS W=0.25u L=0.05u\n"
          ".ends {name}\n")

# a mapped netlist yosys might have produced for an inverter chain
MAPPED_V = """\
module tiny(input a, output y);
  wire n1;
  INVX1 g1 (.A(a), .Y(n1));
  INVX1 g2 (.A(n1), .Y(y));
endmodule
"""


def make_cell(outdir, name, text=None):
    with open(os.path.join(str(outdir), name + ".sp"), "w") as fh:
        fh.write((text or INV_SP).format(name=name))


def make_astran_runner(calls, width=1.9):
    def fake(**kwargs):
        calls.append(kwargs)
        name = kwargs["complex_name"]
        outdir = kwargs["command_dir"]
        with open(os.path.join(outdir, name + ".Astranlog"), "w") as fh:
            fh.write("-> Cell Size (W x H): %s x 2.47\n" % width)
        with open(os.path.join(outdir, name + ".gds"), "w") as fh:
            fh.write("GDS\n")
    return fake


def make_smt_runner(calls, ok=True, width=0.57, note="smt: 3 cols"):
    """Fake run_smt_cell: records the call, drops a .gds when it 'works'
    (the real one only writes on success -- the freshness contract)."""
    def fake(name, sp_path, gds_path, layout_time_s, route_time_s):
        calls.append({"name": name, "sp": sp_path,
                      "layout_time_s": layout_time_s,
                      "route_time_s": route_time_s})
        if ok:
            with open(gds_path, "w") as fh:
                fh.write("GDS\n")
            return CellResult(name=name, ok=True, width=width, height=2.47,
                              seconds=0.1, note=note, engine="smt")
        return CellResult(name=name, ok=False, seconds=0.1,
                          note="smt: INFEASIBLE", engine="smt")
    return fake


# ---- CLI contract -------------------------------------------------------

def test_engine_defaults_to_auto():
    args = v2c._build_parser().parse_args(["mod.v"])
    assert args.engine == "auto"
    assert args.smt_budget == pytest.approx(120.0)
    assert args.smt_max_transistors == SMT_MAX_TRANSISTORS == 8


def test_engine_choices_are_enforced():
    with pytest.raises(SystemExit):
        v2c._build_parser().parse_args(["mod.v", "--engine", "gurobi"])
    for choice in ("auto", "smt", "astran"):
        args = v2c._build_parser().parse_args(["mod.v", "--engine", choice])
        assert args.engine == choice


# ---- eligibility --------------------------------------------------------

def test_smt_eligible_small_literal_deck(tmp_path):
    make_cell(tmp_path, "CELLA")
    eligible, reason = smt_eligible(os.path.join(str(tmp_path), "CELLA.sp"))
    assert eligible, reason
    assert "2 transistors" in reason


def test_smt_eligible_rejects_over_budget(tmp_path):
    # 10 inverters in one cell -> beyond the conservative budget
    lines = [".subckt BIG A Y VCC GND"]
    for i in range(10):
        lines.append("M%d n%d A VCC VCC PMOS W=0.5u L=0.05u" % (2 * i, i))
        lines.append("M%d n%d A GND GND NMOS W=0.25u L=0.05u" % (2 * i + 1, i))
    lines.append(".ends BIG")
    path = os.path.join(str(tmp_path), "BIG.sp")
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    eligible, reason = smt_eligible(path)
    assert not eligible
    assert "20 transistors > smt budget 8" in reason


def test_smt_eligible_rejects_non_literal_models(tmp_path):
    make_cell(tmp_path, "CELLA", INV_SP.replace("PMOS", "CMOSP"))
    eligible, reason = smt_eligible(os.path.join(str(tmp_path), "CELLA.sp"))
    assert not eligible
    assert "literal PMOS/NMOS" in reason


def test_smt_eligible_rejects_parametrised_w(tmp_path):
    # L={LCH} atof's to 0 -- an astran_lint error, so not eligible either
    make_cell(tmp_path, "CELLA", INV_SP.replace("L=0.05u", "L={{LCH}}"))
    eligible, reason = smt_eligible(os.path.join(str(tmp_path), "CELLA.sp"))
    assert not eligible
    assert "lint" in reason


# ---- queue behaviour ----------------------------------------------------

def test_astran_mode_keeps_historical_behaviour(tmp_path):
    make_cell(tmp_path, "CELLA")
    smt_calls, astran_calls = [], []
    results = run_queue(["CELLA"], str(tmp_path),
                        runner=make_astran_runner(astran_calls),
                        smt_runner=make_smt_runner(smt_calls),
                        engine="astran")
    assert smt_calls == []                     # never offered to SMT
    assert len(astran_calls) == 1
    assert results[0].ok and results[0].engine == "astran"


def test_auto_uses_smt_for_eligible_cell(tmp_path):
    make_cell(tmp_path, "CELLA")
    smt_calls, astran_calls = [], []
    results = run_queue(["CELLA"], str(tmp_path),
                        runner=make_astran_runner(astran_calls),
                        smt_runner=make_smt_runner(smt_calls),
                        engine="auto")
    assert len(smt_calls) == 1 and astran_calls == []
    assert results[0].ok and results[0].engine == "smt"
    assert results[0].width == pytest.approx(0.57)
    # the budget reaches the engine as layout/route slices
    assert smt_calls[0]["layout_time_s"] + smt_calls[0]["route_time_s"] \
        == pytest.approx(120.0)
    manifest = json.load(open(os.path.join(str(tmp_path),
                                           ".astran_queue.json")))
    assert manifest["CELLA"]["engine"] == "smt"


def test_auto_falls_back_to_astran_on_smt_failure(tmp_path):
    make_cell(tmp_path, "CELLA")
    smt_calls, astran_calls = [], []
    results = run_queue(["CELLA"], str(tmp_path),
                        runner=make_astran_runner(astran_calls),
                        smt_runner=make_smt_runner(smt_calls, ok=False),
                        engine="auto")
    assert len(smt_calls) == 1                 # the SMT attempt happened
    assert len(astran_calls) == 1              # and ASTRAN took over
    assert results[0].ok
    assert results[0].engine == "astran"       # ASTRAN produced the cell
    assert "smt fallback" in results[0].note
    manifest = json.load(open(os.path.join(str(tmp_path),
                                           ".astran_queue.json")))
    assert manifest["CELLA"]["engine"] == "astran"


def test_auto_falls_back_when_smt_runner_raises(tmp_path):
    make_cell(tmp_path, "CELLA")

    def exploding_smt(name, sp_path, gds_path, layout_time_s, route_time_s):
        raise RuntimeError("solver exploded")

    astran_calls = []
    results = run_queue(["CELLA"], str(tmp_path),
                        runner=make_astran_runner(astran_calls),
                        smt_runner=exploding_smt,
                        engine="auto")
    # the fallback is transparent: the cell still gets a layout
    assert len(astran_calls) == 1
    assert results[0].ok and results[0].engine == "astran"


def test_smt_mode_hard_errors_on_ineligible_cell(tmp_path):
    make_cell(tmp_path, "CELLA", INV_SP.replace("PMOS", "CMOSP"))
    with pytest.raises(RuntimeError, match="not SMT-eligible"):
        run_queue(["CELLA"], str(tmp_path),
                  runner=make_astran_runner([]),
                  smt_runner=make_smt_runner([]),
                  engine="smt")


def test_smt_mode_hard_errors_when_the_engine_fails(tmp_path):
    make_cell(tmp_path, "CELLA")
    with pytest.raises(RuntimeError, match="failed in the SMT engine"):
        run_queue(["CELLA"], str(tmp_path),
                  runner=make_astran_runner([]),
                  smt_runner=make_smt_runner([], ok=False),
                  engine="smt")


def test_resume_is_engine_aware(tmp_path):
    make_cell(tmp_path, "CELLA")
    astran_calls = []
    run_queue(["CELLA"], str(tmp_path),
              runner=make_astran_runner(astran_calls),
              smt_runner=make_smt_runner([]),
              engine="auto")               # produced by smt, cached
    assert astran_calls == []
    # an auto re-run happily reuses the SMT-era cache entry
    results = run_queue(["CELLA"], str(tmp_path),
                        runner=make_astran_runner(astran_calls),
                        smt_runner=make_smt_runner([]),
                        engine="auto", resume=True)
    assert astran_calls == []
    assert results[0].skipped and results[0].engine == "smt"
    # an explicit astran re-run must not reuse the SMT-era cache entry
    results = run_queue(["CELLA"], str(tmp_path),
                        runner=make_astran_runner(astran_calls),
                        smt_runner=make_smt_runner([]),
                        engine="astran", resume=True)
    assert len(astran_calls) == 1
    assert results[0].ok and results[0].engine == "astran"


def test_engine_summary_counts():
    from astran_queue import CellResult
    results = [CellResult(name="A", ok=True, engine="smt"),
               CellResult(name="B", ok=True, engine="smt"),
               CellResult(name="C", ok=True, engine="astran")]
    assert v2c.engine_summary(results) == {"smt": 2, "astran": 1}


# ---- driver report ------------------------------------------------------

def test_report_records_engine_per_block(tmp_path, monkeypatch):
    """main() with synthesis and the queue patched out: the written
    report.md must carry an engine column naming the producing engine."""
    outdir = str(tmp_path)
    mapped_path = os.path.join(outdir, "mapped.v")
    with open(mapped_path, "w") as fh:
        fh.write(MAPPED_V)
    log_path = os.path.join(outdir, "yosys.log")
    with open(log_path, "w") as fh:
        fh.write("")
    monkeypatch.setattr(
        v2c, "run_synthesis",
        lambda *a, **k: ({"mapped_v": mapped_path, "log": log_path},
                         {"histogram": {"INVX1": 2}}))
    results = [CellResult(name="BLK0", ok=True, width=1.14, height=2.47,
                          engine="smt")]
    captured = {}

    def fake_queue(cells, out, **kw):
        captured["engine"] = kw.get("engine")
        return results

    monkeypatch.setattr(v2c, "run_queue", fake_queue)
    verilog = os.path.join(outdir, "tiny.v")
    with open(verilog, "w") as fh:
        fh.write("module tiny(input a, output y);\nendmodule\n")
    rc = v2c.main([verilog, "--out", outdir, "--skip-verify", "--no-png"])
    assert rc == 0
    assert captured["engine"] == "auto"
    report = open(os.path.join(outdir, "report.md")).read()
    assert "| engine |" in report
    assert "| BLK0 | 2x (INVX1) | 4 | smt |" in report
    assert "laid out by the pure-Python SMT engine" in report


# ---- one real SMT cell (fast: 2 transistors) ----------------------------

def test_run_smt_cell_produces_artifacts(tmp_path):
    make_cell(tmp_path, "CELLA")
    sp_path = os.path.join(str(tmp_path), "CELLA.sp")
    gds_path = os.path.join(str(tmp_path), "CELLA.gds")
    result = run_smt_cell("CELLA", sp_path, gds_path,
                          layout_time_s=5, route_time_s=8)
    assert result.ok, result.note
    assert result.engine == "smt"
    assert result.width > 0 and result.height == pytest.approx(2.47)
    assert os.path.exists(gds_path)
    assert "verify ok" in result.note
