"""Unit tests for flow/astran_queue.py (resume, parallelism, lint gate).

ASTRAN itself is replaced by an injectable fake runner that drops a log
with a Cell Size line and a dummy .gds, so the queue logic is exercised
without the slow layout runs.
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "flow"))

from astran_queue import run_queue          # noqa: E402

SP = (".subckt {name} A Y VCC GND\n"
      "M0 Y A VCC VCC PMOS W=0.5u L=0.05u\n"
      "M1 Y A GND GND NMOS W=0.25u L=0.05u\n"
      ".ends {name}\n")


def make_cell(outdir, name, width=1.9):
    with open(os.path.join(outdir, name + ".sp"), "w") as fh:
        fh.write(SP.format(name=name))


def make_runner(calls, width=1.9):
    def fake(**kwargs):
        calls.append(kwargs)
        name = kwargs["complex_name"]
        outdir = kwargs["command_dir"]
        with open(os.path.join(outdir, name + ".Astranlog"), "w") as fh:
            fh.write("-> Cell Size (W x H): %s x 2.47\n" % width)
        with open(os.path.join(outdir, name + ".gds"), "w") as fh:
            fh.write("GDS\n")
    return fake


def test_serial_run_produces_widths_and_manifest(tmp_path):
    make_cell(tmp_path, "CELLA")
    calls = []
    results = run_queue(["CELLA"], str(tmp_path), runner=make_runner(calls))
    assert len(calls) == 1
    assert results[0].ok and results[0].width == 1.9
    assert os.path.exists(os.path.join(str(tmp_path), ".astran_queue.json"))
    # the LP working directory was per-cell, never the shared cwd
    assert calls[0]["work_dir"].endswith(os.path.join(".lpwork", "CELLA"))


def test_resume_skips_unchanged_cells(tmp_path):
    make_cell(tmp_path, "CELLA")
    calls = []
    runner = make_runner(calls)
    run_queue(["CELLA"], str(tmp_path), runner=runner)
    assert len(calls) == 1
    results = run_queue(["CELLA"], str(tmp_path), resume=True, runner=runner)
    assert len(calls) == 1                       # runner NOT called again
    assert results[0].skipped and results[0].ok and results[0].width == 1.9


def test_changed_sp_invalidates_cache(tmp_path):
    make_cell(tmp_path, "CELLA")
    calls = []
    runner = make_runner(calls)
    run_queue(["CELLA"], str(tmp_path), runner=runner)
    time.sleep(0.02)
    make_cell(tmp_path, "CELLA")                 # rewrite -> new mtime
    os.utime(os.path.join(str(tmp_path), "CELLA.sp"))
    results = run_queue(["CELLA"], str(tmp_path), resume=True, runner=runner)
    assert len(calls) == 2
    assert not results[0].skipped


def test_missing_gds_invalidates_cache(tmp_path):
    make_cell(tmp_path, "CELLA")
    calls = []
    runner = make_runner(calls)
    run_queue(["CELLA"], str(tmp_path), runner=runner)
    os.remove(os.path.join(str(tmp_path), "CELLA.gds"))
    run_queue(["CELLA"], str(tmp_path), resume=True, runner=runner)
    assert len(calls) == 2


def test_parallel_jobs_run_all_cells(tmp_path):
    for name in ("CELLA", "CELLB", "CELLC"):
        make_cell(tmp_path, name)
    calls = []
    results = run_queue(["CELLA", "CELLB", "CELLC"], str(tmp_path),
                        jobs=3, runner=make_runner(calls))
    assert len(calls) == 3
    assert all(r.ok for r in results)
    # every cell still got a private LP cwd
    assert {c["work_dir"] for c in calls} == {
        os.path.join(str(tmp_path), ".lpwork", n)
        for n in ("CELLA", "CELLB", "CELLC")}


def test_lint_failure_blocks_runner(tmp_path):
    with open(os.path.join(str(tmp_path), "BAD.sp"), "w") as fh:
        fh.write(SP.replace("M0 Y A", "g0#M0 Y A").format(name="BAD"))
    calls = []
    results = run_queue(["BAD"], str(tmp_path), runner=make_runner(calls))
    assert calls == []
    assert not results[0].ok
    assert "lint" in results[0].note


def test_zero_width_is_reported_as_failure(tmp_path):
    make_cell(tmp_path, "CELLZ")
    results = run_queue(["CELLZ"], str(tmp_path),
                        runner=make_runner([], width=0.0))
    assert not results[0].ok
    assert "0x0" in results[0].note


def test_events_fire_in_order(tmp_path):
    make_cell(tmp_path, "CELLA")
    events = []
    run_queue(["CELLA"], str(tmp_path), runner=make_runner([]),
              on_event=lambda kind, payload: events.append(kind))
    assert events == ["start", "done"]
