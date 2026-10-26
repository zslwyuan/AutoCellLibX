"""Unit tests for the benchmark harness (flow/bigcell_engine.benchmark).

Covers the loader (determinism + schema), .Astranlog width parsing and
the baseline cache (read/write/stale/corrupt), report assembly with
INJECTED fakes -- no ASTRAN, no CP-SAT, no GDS writing in this file --
and the quality panel (pin access / sanity metrics / layer counts /
runtime) plus the generalization band machinery.
"""
import json
import os

import pytest

from bigcell_engine import benchmark as benchmark_mod
from bigcell_engine.benchmark import (BenchmarkCell, LIBRARY_LOG_DIR,
                                      baseline_cache_path,
                                      band_closure,
                                      generalization_verdict,
                                      get_astran_baselines,
                                      load_benchmark_cells,
                                      load_holdout_cells,
                                      run_benchmark, run_generalization,
                                      runtime_from_attempts, size_band)
from bigcell_engine.engine import UnsupportedCell
from smt_cell_placer import parse_spice_subckt
from smt_engine.netlist import CellNetlist

INV = """\
.subckt INV VCC Y A GND
Mp Y A VCC VCC PMOS W=0.5u L=0.05u
Mn Y A GND GND NMOS W=0.5u L=0.05u
.ends INV
"""

NAND2 = """\
.subckt NAND2 VCC Y A B GND
MpA Y A VCC VCC PMOS W=0.5u L=0.05u
MpB VCC B Y VCC PMOS W=0.5u L=0.05u
MnA Y A n1 GND NMOS W=0.5u L=0.05u
MnB n1 B GND GND NMOS W=0.5u L=0.05u
.ends NAND2
"""


def _cell(rel, text, name=None, log_dir=None):
    parsed = parse_spice_subckt(text)
    # the loader names cells by the parsed subckt; real decks name the
    # subckt after the file, so the fakes do the same
    return BenchmarkCell(name=name or os.path.basename(rel)[:-3],
                         source=rel, netlist=CellNetlist(parsed),
                         transistors=len(parsed.devices), text=text,
                         log_dir=log_dir)


def _mk_file(tmp_path, rel, text):
    path = os.path.join(str(tmp_path), *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as fh:
        fh.write(text)
    return path


# --- loader: determinism + schema over the real benchmark set -----------

def test_loader_deterministic_sorted_deduped(flow_dir):
    a = load_benchmark_cells(flow_dir)
    b = load_benchmark_cells(flow_dir)
    ta = [(c.name, c.source, c.transistors) for c in a]
    tb = [(c.name, c.source, c.transistors) for c in b]
    assert ta == tb                          # deterministic across calls
    assert ta == sorted(ta)                  # sorted by (name, source)
    assert len(set(c.source for c in a)) == len(a)   # de-duplicated
    for c in a:
        assert isinstance(c.netlist, CellNetlist)
        assert c.transistors == len(c.netlist.devices)
        assert c.source.endswith(".sp")
        assert c.text and ".subckt" in c.text


def test_loader_covers_the_known_set(flow_dir):
    cells = load_benchmark_cells(flow_dir)
    by_source = {c.source: c for c in cells}
    # both globs are walked (original_astran_cells holds no .sp today)
    for src in ("outputs/adder/COMPLEX0.sp", "outputs/max/COMPLEX5.sp",
                "outputs/pdk_drc/inv.sp", "outputs/ctrl/COMPLEX11.sp"):
        assert src in by_source, src
    assert by_source["outputs/max/COMPLEX5.sp"].transistors == 6
    assert by_source["outputs/adder/COMPLEX10.sp"].transistors == 36
    assert by_source["outputs/pdk_drc/inv.sp"].name == "INV"
    # names collide across benchmarks (invariant 6): the same COMPLEX id
    # names different patterns in different dirs -- sources disambiguate
    names = [c.name for c in cells]
    assert names.count("COMPLEX0") >= 2


# --- loader: the standard-cell LIBRARY file ------------------------------

def test_loader_includes_library_cells(flow_dir):
    cells = load_benchmark_cells(flow_dir)
    lib = [c for c in cells if c.source.startswith("library/")]
    assert len(lib) > 0                     # the library file is in the set
    by_source = {c.source: c for c in lib}
    # the gates the Python ladder closes are now benchmarked
    assert "library/INVX1.sp" in by_source
    assert "library/NAND2X1.sp" in by_source
    assert by_source["library/INVX1.sp"].transistors == 2
    assert by_source["library/NAND2X1.sp"].transistors == 4
    for c in lib:
        assert c.log_dir == LIBRARY_LOG_DIR   # baseline dir wired
        assert c.source.endswith(".sp")
        # one block per cell: the deck text is the subckt, not the file
        assert c.text.lower().count(".subckt") == 1
        assert c.text.lower().count(".ends") == 1
    # one record per subckt, deterministic (name, source) order
    names = [c.name for c in lib]
    assert names == sorted(names)
    assert len(set(c.source for c in lib)) == len(lib)


def test_library_blocks_parsed_independently(tmp_path, monkeypatch):
    # parse_spice_subckt reads the FIRST .subckt header but EVERY MOS
    # line of its input: without the per-block split the first subckt
    # would inherit the devices of the whole file
    deck = INV + "\n" + NAND2 + "\n" + ".end\n"
    _mk_file(tmp_path, "libsrc/all.sp", deck)
    monkeypatch.setattr(benchmark_mod, "LIBRARY_SOURCES", ("libsrc/all.sp",))
    cells = load_benchmark_cells(str(tmp_path))
    by_name = {c.name: c for c in cells}
    assert sorted(by_name) == ["INV", "NAND2"]
    assert by_name["INV"].transistors == 2      # not the file's 6 devices
    assert by_name["NAND2"].transistors == 4
    assert by_name["INV"].source == "library/INV.sp"
    assert by_name["INV"].text.count("Mp") == 1
    assert by_name["NAND2"].text.count("Mp") == 2


def test_library_unparseable_and_duplicate_blocks_skipped(tmp_path,
                                                          monkeypatch):
    deck = (INV
            + "\n.subckt EMPTY VCC GND\n.ends EMPTY\n"       # no MOS devices
            + "\n" + INV)                                     # duplicate name
    _mk_file(tmp_path, "libsrc/all.sp", deck)
    monkeypatch.setattr(benchmark_mod, "LIBRARY_SOURCES", ("libsrc/all.sp",))
    cells = load_benchmark_cells(str(tmp_path))
    assert [c.name for c in cells] == ["INV"]
    assert cells[0].text == INV.rstrip("\n")     # first occurrence's block


# --- library baselines: wired log directory ------------------------------

def test_library_baselines_wired_to_original_astran_logs(flow_dir, tmp_path):
    # the library cells have no .sp deck next to their logs: the wired
    # LIBRARY_LOG_DIR is the only place their baselines can be found
    cells = [c for c in load_benchmark_cells(flow_dir)
             if c.source.startswith("library/")]
    base = get_astran_baselines(cells,
                                cache_path=os.path.join(str(tmp_path),
                                                        "cache.json"),
                                flow_dir=str(flow_dir))
    parsed = {s: e for s, e in base.items()
              if e["origin"] == "log" and e["width_um"]}
    assert len(parsed) >= 15                 # at least 15 logs carry a width
    assert parsed["library/INVX1.sp"]["width_um"] == 0.57
    assert parsed["library/NAND2X1.sp"]["width_um"] == 0.76
    assert parsed["library/INVX1.sp"]["origin"] == "log"
    # truncated logs (no Cell Size line) are honest misses, not drops
    misses = [base[c.source] for c in cells if c.source not in parsed]
    for e in misses:
        assert e["width_um"] is None
        assert "no Cell Size" in e["note"] or "rejected" in e["note"]


def test_baseline_wired_log_dir_resolution(tmp_path):
    _mk_file(tmp_path, "library/FOO.sp", INV)          # virtual-source log
    _mk_file(tmp_path, "baselogs/FOO.Astranlog",
             "-> Cell Size (W x H): 0.57 x 2.47\n"
             "-> Number of transistors before folding: 2 -> P(1) N(1)\n")
    base = get_astran_baselines(
        [_cell("library/FOO.sp", INV, log_dir="baselogs")],
        cache_path=os.path.join(str(tmp_path), "cache.json"),
        flow_dir=str(tmp_path))
    e = base["library/FOO.sp"]
    assert e["width_um"] == 0.57 and e["origin"] == "log"
    # without the wiring the same log is invisible (fresh cache: the
    # first call's entry must not mask the resolution difference)
    base2 = get_astran_baselines(
        [_cell("library/FOO.sp", INV)],
        cache_path=os.path.join(str(tmp_path), "cache2.json"),
        flow_dir=str(tmp_path))
    e2 = base2["library/FOO.sp"]
    assert e2["width_um"] is None and e2["origin"] == "missing"
    assert "no .Astranlog next to the .sp (allow_runs=False)" in e2["note"]


def test_baseline_stale_wired_log_rejected(tmp_path):
    _mk_file(tmp_path, "library/FOO.sp", INV)
    _mk_file(tmp_path, "baselogs/FOO.Astranlog",
             "-> Cell Size (W x H): 3.61 x 2.47\n"
             "-> Number of transistors before folding: 30 -> P(15) N(15)\n")
    base = get_astran_baselines(
        [_cell("library/FOO.sp", INV, log_dir="baselogs")],
        cache_path=os.path.join(str(tmp_path), "cache.json"),
        flow_dir=str(tmp_path))
    e = base["library/FOO.sp"]
    assert e["width_um"] is None and e["origin"] == "missing"
    assert "rejected" in e["note"]           # stale wired log: never used


# --- name-overlap dedupe: baseline decks vs the library ------------------

def _with_libsrc(tmp_path, monkeypatch, deck):
    _mk_file(tmp_path, "libsrc/all.sp", deck)
    monkeypatch.setattr(benchmark_mod, "LIBRARY_SOURCES", ("libsrc/all.sp",))


def test_dedupe_prefers_baseline_deck_with_sibling_log(tmp_path, monkeypatch):
    # a same-named original_astran_cells deck WITH its .Astranlog wins
    # over the library record (its baseline needs no directory wiring)
    _mk_file(tmp_path, "original_astran_cells/INV.sp", INV)
    _mk_file(tmp_path, "original_astran_cells/INV.Astranlog",
             "-> Cell Size (W x H): 0.57 x 2.47\n"
             "-> Number of transistors before folding: 2 -> P(1) N(1)\n")
    _with_libsrc(tmp_path, monkeypatch, INV)
    names = [(c.name, c.source) for c in load_benchmark_cells(str(tmp_path))]
    assert names == [("INV", "original_astran_cells/INV.sp")]


def test_dedupe_keeps_both_when_no_sibling_log(tmp_path, monkeypatch):
    _mk_file(tmp_path, "original_astran_cells/INV.sp", INV)
    _with_libsrc(tmp_path, monkeypatch, INV)
    names = sorted((c.name, c.source)
                   for c in load_benchmark_cells(str(tmp_path)))
    # no log to prefer: both sources stay as distinct records
    assert names == [("INV", "library/INV.sp"),
                     ("INV", "original_astran_cells/INV.sp")]


def test_dedupe_never_collapses_outputs_against_library(tmp_path, monkeypatch):
    # invariant 6: outputs names are per-run ids -- a same-named outputs
    # cell may be a different pattern and is never name-deduped away,
    # even when the outputs deck has its own sibling log
    _mk_file(tmp_path, "outputs/x/INV.sp", INV)
    _mk_file(tmp_path, "outputs/x/INV.Astranlog",
             "-> Cell Size (W x H): 0.57 x 2.47\n"
             "-> Number of transistors before folding: 2 -> P(1) N(1)\n")
    _with_libsrc(tmp_path, monkeypatch, INV)
    names = sorted((c.name, c.source)
                   for c in load_benchmark_cells(str(tmp_path)))
    assert names == [("INV", "library/INV.sp"),
                     ("INV", "outputs/x/INV.sp")]


# --- virtual sources keep run_benchmark artifacts inside out_dir ---------

def test_report_artifacts_for_virtual_library_source(tmp_path):
    out = os.path.join(str(tmp_path), "out")
    report = run_benchmark(
        [_cell("library/INVX1.sp", INV, log_dir="original_astran_cells")],
        out, baselines={"library/INVX1.sp":
                        {"name": "INVX1", "transistors": 2,
                         "width_um": 0.57, "origin": "log", "note": ""}},
        synth_runner=_fake_synth_ok, gds_writer=_fake_gds_writer,
        verify_fn=lambda nl, pl, rt: _OkReport(),
        sanity_checker=lambda p: _SanityReport(True, 0.57),
        flow_dir=str(tmp_path))
    rec = report["cells"][0]
    assert rec["status"] == "ok" and rec["astran_um"] == 0.57
    # artifacts mirror the VIRTUAL source under out_dir -- never next to
    # the real library deck (which lives outside the flow directory)
    assert open(os.path.join(out, "library", "INVX1.sp"),
                newline="").read() == INV
    assert os.path.exists(os.path.join(out, "library", "INVX1.gds"))
    assert "| INVX1 | library/INVX1.sp | 2 | 0.57 | 0.57 |" in \
        open(os.path.join(out, "report.md")).read()


# --- .Astranlog width parsing + baseline cache --------------------------

def _with_log(tmp_path, rel, log_lines):
    _mk_file(tmp_path, rel, INV)
    log_rel = rel[:-3] + ".Astranlog"
    _mk_file(tmp_path, log_rel,
             "-> Placing transistors...\n" + "".join(
                 l + "\n" for l in log_lines))


def test_baseline_width_parsed_from_log(tmp_path):
    _with_log(tmp_path, "outputs/x/FOO.sp",
              ["-> Cell Size (W x H): 2.09 x 2.47",
               "-> Number of transistors before folding: 2 -> P(1) N(1)"])
    base = get_astran_baselines(
        [_cell("outputs/x/FOO.sp", INV)],
        cache_path=os.path.join(str(tmp_path), "cache.json"),
        flow_dir=str(tmp_path))
    e = base["outputs/x/FOO.sp"]
    assert e["width_um"] == 2.09
    assert e["origin"] == "log"
    assert e["transistors"] == 2


def test_baseline_stale_log_rejected(tmp_path):
    # AUDIT 5.6: a log whose transistor count differs describes another
    # netlist -- its width must not become the baseline
    _with_log(tmp_path, "outputs/x/FOO.sp",
              ["-> Cell Size (W x H): 3.61 x 2.47",
               "-> Number of transistors before folding: 30 -> P(15) N(15)"])
    base = get_astran_baselines(
        [_cell("outputs/x/FOO.sp", INV)],
        cache_path=os.path.join(str(tmp_path), "cache.json"),
        flow_dir=str(tmp_path))
    e = base["outputs/x/FOO.sp"]
    assert e["width_um"] is None
    assert e["origin"] == "missing"
    assert "rejected" in e["note"] and "30" in e["note"]


def test_baseline_log_without_cell_size_is_honest(tmp_path):
    _with_log(tmp_path, "outputs/x/FOO.sp",
              ["-> Number of transistors before folding: 2 -> P(1) N(1)"])
    base = get_astran_baselines(
        [_cell("outputs/x/FOO.sp", INV)],
        cache_path=os.path.join(str(tmp_path), "cache.json"),
        flow_dir=str(tmp_path))
    e = base["outputs/x/FOO.sp"]
    assert e["width_um"] is None and e["origin"] == "missing"
    assert "no Cell Size" in e["note"]


def test_baseline_cache_round_trip(tmp_path):
    _with_log(tmp_path, "outputs/x/FOO.sp",
              ["-> Cell Size (W x H): 2.09 x 2.47",
               "-> Number of transistors before folding: 2 -> P(1) N(1)"])
    cache = os.path.join(str(tmp_path), "cache.json")
    cells = [_cell("outputs/x/FOO.sp", INV)]
    first = get_astran_baselines(cells, cache_path=cache, flow_dir=str(tmp_path))
    assert first["outputs/x/FOO.sp"]["origin"] == "log"
    assert os.path.exists(cache)
    data = json.load(open(cache))
    assert data["cells"]["outputs/x/FOO.sp"]["width_um"] == 2.09
    # the cached entry survives without the log on disk
    os.remove(os.path.join(str(tmp_path), "outputs", "x", "FOO.Astranlog"))
    second = get_astran_baselines(cells, cache_path=cache,
                                  flow_dir=str(tmp_path))
    e = second["outputs/x/FOO.sp"]
    assert e["origin"] == "cache" and e["width_um"] == 2.09


def test_baseline_cache_revalidated_on_transistor_count(tmp_path):
    # a cached entry belongs to the netlist it was measured from: when
    # the .sp's device count changes, the entry must be recomputed
    _with_log(tmp_path, "outputs/x/FOO.sp",
              ["-> Cell Size (W x H): 2.09 x 2.47",
               "-> Number of transistors before folding: 2 -> P(1) N(1)"])
    cache = os.path.join(str(tmp_path), "cache.json")
    get_astran_baselines([_cell("outputs/x/FOO.sp", INV)],
                         cache_path=cache, flow_dir=str(tmp_path))
    # now the same source holds a 4-transistor netlist: the cached
    # 2-transistor entry must not be reused
    _mk_file(tmp_path, "outputs/x/FOO.sp", NAND2)
    base = get_astran_baselines([_cell("outputs/x/FOO.sp", NAND2)],
                                cache_path=cache, flow_dir=str(tmp_path))
    e = base["outputs/x/FOO.sp"]
    assert e["origin"] == "missing"          # log says 2 T, .sp has 4 T
    assert e["width_um"] is None


def test_baseline_missing_without_runs(tmp_path):
    base = get_astran_baselines(
        [_cell("outputs/x/FOO.sp", INV)],
        cache_path=os.path.join(str(tmp_path), "cache.json"),
        flow_dir=str(tmp_path))
    e = base["outputs/x/FOO.sp"]
    assert e["width_um"] is None and e["origin"] == "missing"
    assert "allow_runs=False" in e["note"]


def test_baseline_cache_corrupt_tolerated(tmp_path):
    _with_log(tmp_path, "outputs/x/FOO.sp",
              ["-> Cell Size (W x H): 2.09 x 2.47",
               "-> Number of transistors before folding: 2 -> P(1) N(1)"])
    cache = os.path.join(str(tmp_path), "cache.json")
    with open(cache, "w") as fh:
        fh.write("{not json")
    base = get_astran_baselines([_cell("outputs/x/FOO.sp", INV)],
                                cache_path=cache, flow_dir=str(tmp_path))
    assert base["outputs/x/FOO.sp"]["width_um"] == 2.09


def test_baseline_fresh_run_cached(tmp_path):
    _mk_file(tmp_path, "outputs/x/FOO.sp", INV)
    runs = []

    def fake_runner(sp_path, work_dir, name):
        runs.append((sp_path, work_dir, name))
        # per-cell work dir, never shared (the LP cwd discipline)
        assert work_dir.endswith(os.path.join("_stage3_check", "work",
                                              "outputs", "x", "FOO"))
        _mk_file(tmp_path,
                 "_stage3_check/work/outputs/x/FOO/FOO.Astranlog",
                 "-> Cell Size (W x H): 1.52 x 2.47\n"
                 "-> Number of transistors before folding: 2 -> P(1) N(1)\n")

    cache = os.path.join(str(tmp_path), "cache.json")
    base = get_astran_baselines([_cell("outputs/x/FOO.sp", INV)],
                                cache_path=cache, allow_runs=True,
                                astran_runner=fake_runner,
                                flow_dir=str(tmp_path))
    e = base["outputs/x/FOO.sp"]
    assert len(runs) == 1
    assert e["origin"] == "run" and e["width_um"] == 1.52
    # the run's outcome is cached: a second call re-runs nothing
    base2 = get_astran_baselines([_cell("outputs/x/FOO.sp", INV)],
                                 cache_path=cache, allow_runs=True,
                                 astran_runner=fake_runner,
                                 flow_dir=str(tmp_path))
    assert base2["outputs/x/FOO.sp"]["origin"] == "cache"
    assert len(runs) == 1


# --- report assembly with fakes -----------------------------------------

class _FakeRoute(object):
    ok = True
    status_name = "OPTIMAL"
    width_cols = 3


class _OkReport(object):
    def __init__(self):
        self.violations = []

    def ok(self):
        return True


class _SanityReport(object):
    def __init__(self, ok=True, width=0.57):
        self.violations = [] if ok else [("height", "bad")]
        self.metrics = {"width_um": width}

    def ok(self):
        return not self.violations


def _fake_gds_writer(path, netlist, placement, route):
    with open(path, "wb") as fh:
        fh.write(b"fake-gds")


def _fake_synth_ok(netlist, exact_budget_s=60.0, grid_budget_s=120.0,
                   grid_router=None):
    return ({}, _FakeRoute(),
            {"engine": "smt-exact", "width_um": 0.57, "width_cols": 3,
             "attempts": [{"rung": 1, "engine": "smt-exact",
                           "stage": "layout", "ok": True,
                           "status": "OPTIMAL"}]})


def _fake_synth_unsupported(netlist, exact_budget_s=60.0,
                            grid_budget_s=120.0, grid_router=None):
    raise UnsupportedCell(
        "FOO: no engine closed the cell [rung1 smt-exact/routing SKIPPED]",
        meta={"attempts": [{"rung": 1, "engine": "smt-exact",
                            "stage": "routing", "ok": False,
                            "status": "SKIPPED", "note": "width 20 > 14"}]})


_BASELINES = {
    "outputs/x/FOO.sp": {"name": "FOO", "transistors": 2, "width_um": 0.95,
                         "origin": "log", "note": ""},
    "outputs/y/BAR.sp": {"name": "BAR", "transistors": 4, "width_um": None,
                         "origin": "missing", "note": "no log"},
}


def _artifact(out_dir, source, suffix):
    """Path of an artifact for a source, or None when absent on disk."""
    stem = source[:-3] if source.endswith(".sp") else source
    path = os.path.join(out_dir, *stem.split("/")) + suffix
    return path if os.path.exists(path) else None


def _fake_cells():
    return [_cell("outputs/x/FOO.sp", INV),
            _cell("outputs/y/BAR.sp", NAND2)]


def test_report_assembly_with_fakes(tmp_path):
    out = os.path.join(str(tmp_path), "out")
    report = run_benchmark(_fake_cells(), out, baselines=dict(_BASELINES),
                           synth_runner=_fake_synth_ok,
                           gds_writer=_fake_gds_writer,
                           verify_fn=lambda nl, pl, rt: _OkReport(),
                           sanity_checker=lambda p: _SanityReport(True, 0.57),
                           flow_dir=str(tmp_path))
    recs = report["cells"]
    assert [r["status"] for r in recs] == ["ok", "ok"]
    by_src = {r["source"]: r for r in recs}
    foo = by_src["outputs/x/FOO.sp"]
    bar = by_src["outputs/y/BAR.sp"]
    # the deliverable's per-cell schema
    assert foo["name"] == "FOO" and foo["T"] == 2
    assert foo["astran_um"] == 0.95 and foo["python_um"] == 0.57
    assert foo["engine"] == "smt-exact"
    assert foo["verdicts"]["verify"]["ok"] is True
    assert foo["verdicts"]["sanity"]["ok"] is True
    assert bar["astran_um"] is None            # honest: no baseline
    # artifacts mirror the source layout under out_dir
    sp = os.path.join(out, "outputs", "x", "FOO.sp")
    gds = os.path.join(out, "outputs", "x", "FOO.gds")
    assert open(sp, newline="").read() == INV
    assert os.path.exists(gds)
    # report files
    rj = json.load(open(os.path.join(out, "report.json")))
    assert rj["summary"]["ok"] == 2
    assert rj["summary"]["verified_ok"] == 2
    assert rj["summary"]["baselines"]["log"] == 1
    assert rj["summary"]["baselines"]["missing_or_failed"] == 1
    assert rj["summary"]["width_ratio_python_over_astran"]["n"] == 1
    assert abs(rj["summary"]["width_ratio_python_over_astran"]["median"]
               - 0.57 / 0.95) < 1e-3
    md = open(os.path.join(out, "report.md")).read()
    assert "| FOO | outputs/x/FOO.sp | 2 | 0.95 | 0.57 |" in md
    # the missing-baseline cell prints "-" for its astran width
    assert "| BAR | outputs/y/BAR.sp | 4 | - |" in md
    assert "Summary" in md


def test_report_records_unsupported_honestly(tmp_path):
    out = os.path.join(str(tmp_path), "out")
    report = run_benchmark(_fake_cells(), out, baselines=dict(_BASELINES),
                           synth_runner=_fake_synth_unsupported,
                           gds_writer=_fake_gds_writer,
                           verify_fn=lambda nl, pl, rt: _OkReport(),
                           sanity_checker=lambda p: _SanityReport(),
                           flow_dir=str(tmp_path))
    recs = report["cells"]
    assert [r["status"] for r in recs] == ["unsupported", "unsupported"]
    for r in recs:
        assert r["python_um"] is None
        assert r["attempts"] and r["attempts"][0]["rung"] == 1
        assert "no engine closed the cell" in r["note"]
        # a failed cell leaves no .gds behind (the .sp is the deck only)
        assert _artifact(out, r["source"], ".gds") is None
    assert report["summary"]["unsupported"] == 2
    assert report["summary"]["ok"] == 0


def test_report_records_engine_crash(tmp_path):
    def crashing_synth(netlist, **kw):
        raise RuntimeError("solver exploded")

    out = os.path.join(str(tmp_path), "out")
    report = run_benchmark(_fake_cells()[:1], out,
                           baselines=dict(_BASELINES),
                           synth_runner=crashing_synth,
                           gds_writer=_fake_gds_writer,
                           verify_fn=lambda nl, pl, rt: _OkReport(),
                           sanity_checker=lambda p: _SanityReport(),
                           flow_dir=str(tmp_path))
    rec = report["cells"][0]
    assert rec["status"] == "error"
    assert "RuntimeError" in rec["note"]
    assert report["summary"]["errors"] == 1


# --- artifact cache contract (invariant 7) ------------------------------

def test_artifact_cache_contract_resume(tmp_path):
    out = os.path.join(str(tmp_path), "out")
    calls = []

    def counting_synth(netlist, **kw):
        calls.append(netlist)
        return _fake_synth_ok(netlist, **kw)

    kwargs = dict(baselines=dict(_BASELINES),
                  synth_runner=counting_synth,
                  gds_writer=_fake_gds_writer,
                  verify_fn=lambda nl, pl, rt: _OkReport(),
                  sanity_checker=lambda p: _SanityReport(True, 0.57),
                  flow_dir=str(tmp_path))
    cells = _fake_cells()[:1]

    report = run_benchmark(cells, out, **kwargs)
    assert len(calls) == 1 and report["cells"][0]["status"] == "ok"
    sp = os.path.join(out, "outputs", "x", "FOO.sp")
    mtime_after_first = os.path.getmtime(sp)

    # second pass: .sp content unchanged + .gds fresh -> no synthesis
    report = run_benchmark(cells, out, **kwargs)
    assert len(calls) == 1
    rec = report["cells"][0]
    assert rec["status"] == "cached" and rec["cached"] is True
    assert rec["python_um"] == 0.57        # measured from the artifact
    assert os.path.getmtime(sp) == mtime_after_first   # content-only write

    # resume=False forces synthesis even though the pair is fresh
    report = run_benchmark(cells, out, resume=False, **kwargs)
    assert len(calls) == 2 and report["cells"][0]["status"] == "ok"

    # a stale .gds (older than its .sp) is regenerated
    os.utime(sp, (os.path.getmtime(sp) + 10,) * 2)
    report = run_benchmark(cells, out, **kwargs)
    assert len(calls) == 3 and report["cells"][0]["status"] == "ok"


def test_sp_written_once_when_content_unchanged(tmp_path):
    out = os.path.join(str(tmp_path), "out")
    os.makedirs(out)
    _mk_file(tmp_path, "out/outputs/x/FOO.sp", INV)
    sp = os.path.join(out, "outputs", "x", "FOO.sp")
    before = os.path.getmtime(sp)
    run_benchmark(_fake_cells()[:1], out, baselines=dict(_BASELINES),
                  synth_runner=_fake_synth_ok, gds_writer=_fake_gds_writer,
                  verify_fn=lambda nl, pl, rt: _OkReport(),
                  sanity_checker=lambda p: _SanityReport(),
                  flow_dir=str(tmp_path))
    assert os.path.getmtime(sp) == before


# --- quality panel: pin access, sanity metrics, layers, runtime -----------

def _write_engine_like_gds(path):
    """A minimal engine-like GDS: two metal1 pin labels, one poly-blocked.

    Same construction as test_pin_accessibility's synthetic deck: pin
    A on-grid and free (score 1.0), pin B on-grid under a poly stripe
    (score 0.5) -- cell score 0.75.
    """
    import gdstk
    cell = gdstk.Cell("T")
    cell.add(gdstk.rectangle((0.0, 0.0), (1.14, 2.47), layer=235))
    cell.add(gdstk.rectangle((0.0, 0.0), (1.14, 0.13), layer=49))   # rail
    cell.add(gdstk.rectangle((0.0, 2.34), (1.14, 2.47), layer=49))  # rail
    cell.add(gdstk.rectangle((0.38, 1.0), (0.76, 1.4), layer=49))   # pin A
    cell.add(gdstk.Label("A", origin=(0.57, 1.2), layer=49))
    cell.add(gdstk.rectangle((0.95, 1.0), (1.33, 1.4), layer=49))   # pin B
    cell.add(gdstk.Label("B", origin=(1.14, 1.2), layer=49))
    cell.add(gdstk.rectangle((0.9, 0.7), (1.4, 1.8), layer=9))      # poly
    lib = gdstk.Library(unit=1e-6, precision=1e-9)
    lib.add(cell)
    lib.write_gds(path)


class _GdsWritingFake(object):
    """gds_writer fake that writes a real minimal GDS."""

    def __call__(self, path, netlist, placement, route):
        _write_engine_like_gds(path)


def _fake_synth_rich(netlist, exact_budget_s=60.0, grid_budget_s=120.0,
                     grid_router=None):
    """A fake synth whose meta carries runtime-bearing attempts."""
    return ({}, _FakeRoute(),
            {"engine": "bigcell-full", "width_um": 1.14, "width_cols": 6,
             "attempts": [
                 {"rung": 1, "engine": "smt-exact", "stage": "layout",
                  "ok": True, "status": "OPTIMAL", "seconds": 4.0},
                 {"rung": 1, "engine": "smt-exact", "stage": "routing",
                  "ok": False, "status": "SKIPPED", "seconds": 0.0},
                 {"rung": 2, "engine": "bigcell-grid", "ok": False,
                  "status": "FAILED", "seconds": 7.5},
                 {"rung": 2.5, "engine": "bigcell-window-fix", "ok": False,
                  "status": "SKIPPED", "stage": "routing", "seconds": 1.25,
                  "window": [0, 6]},
                 {"rung": 3, "engine": "bigcell-full", "ok": True,
                  "stage": "placement", "status": "OK", "seconds": 2.0},
                 {"rung": 3, "engine": "bigcell-full", "ok": True,
                  "stage": "routing", "status": "OK", "seconds": 3.0}]})


class _RichSanityReport(object):
    def __init__(self):
        self.violations = []
        self.metrics = {"width_um": 1.14, "height_um": 2.47,
                        "labels": ["A", "B", "GND", "VCC"]}

    def ok(self):
        return True


def test_quality_panel_in_report(tmp_path):
    out = os.path.join(str(tmp_path), "out")
    report = run_benchmark(_fake_cells()[:1], out,
                           baselines=dict(_BASELINES),
                           synth_runner=_fake_synth_rich,
                           gds_writer=_GdsWritingFake(),
                           verify_fn=lambda nl, pl, rt: _OkReport(),
                           sanity_checker=lambda p: _RichSanityReport(),
                           flow_dir=str(tmp_path))
    rec = report["cells"][0]
    q = rec["quality"]
    # pin access measured on the produced GDS (real scorer, real file)
    assert q["pin_access"] == {"score": 0.75, "n_pins": 2, "on_track": 2,
                               "blocked": 1, "crowded_pins": 0}
    # the sanity metrics dict surfaces verbatim (sorted keys)
    assert q["sanity_metrics"] == {"height_um": 2.47,
                                   "labels": ["A", "B", "GND", "VCC"],
                                   "width_um": 1.14}
    # per-layer polygon counts, sorted str keys
    assert q["layer_counts"]["49"] == 4
    assert q["layer_counts"]["9"] == 1
    assert list(q["layer_counts"]) == sorted(q["layer_counts"])
    # runtime: place 4.0+2.0, route 0.0+7.5+3.0, window 1.25
    assert q["runtime_s"] == {"total": 17.8, "place": 6.0, "route": 10.5,
                              "window": 1.2}
    # the summary quality block aggregates the same measurements
    quality = report["summary"]["quality"]
    assert quality["closure_rate"] == 1.0
    assert quality["engine_mix"] == {"bigcell-full": 1}
    assert quality["pin_access"] == {"n": 1, "median": 0.75}
    assert quality["runtime_s"]["n"] == 1
    assert quality["runtime_s"]["max"] == 17.8
    # same-semantics ratios only count slot-model engines
    assert quality["ratio_same_semantics"]["n"] == 1
    assert abs(quality["ratio_same_semantics"]["median"]
               - 1.14 / 0.95) < 1e-3
    # the markdown carries the panel: quality line + table columns
    md = open(os.path.join(out, "report.md")).read()
    assert "**Quality**" in md
    assert "median pin access 0.750" in md
    assert "| pin | run s | note |" in md
    assert "| FOO | outputs/x/FOO.sp | 2 | 0.95 | 1.14 |" in md


def test_quality_panel_degrades_honestly(tmp_path):
    # an unreadable GDS must yield None measurements, never invented ones
    out = os.path.join(str(tmp_path), "out")

    def raising_sanity(path):
        raise RuntimeError("no GDS")

    report = run_benchmark(_fake_cells()[:1], out,
                           baselines=dict(_BASELINES),
                           synth_runner=_fake_synth_rich,
                           gds_writer=_fake_gds_writer,
                           verify_fn=lambda nl, pl, rt: _OkReport(),
                           sanity_checker=raising_sanity,
                           flow_dir=str(tmp_path))
    rec = report["cells"][0]
    assert rec["quality"]["sanity_metrics"] is None
    assert rec["quality"]["layer_counts"] is None
    assert rec["quality"]["pin_access"]["score"] is None
    assert "raised" in rec["quality"]["pin_access"]["note"]
    # the runtime survives: it does not depend on the artifact
    assert rec["quality"]["runtime_s"]["total"] == 17.8
    quality = report["summary"]["quality"]
    assert quality["pin_access"]["n"] == 0     # no score -> excluded, n=0
    assert quality["runtime_s"]["n"] == 1


def test_quality_summary_same_semantics_only(tmp_path):
    # bigcell-grid/smt-exact ratios are NOT same-semantics: the summary
    # quality block must exclude them while the legacy field keeps them
    def synth_grid(netlist, **kw):
        return ({}, _FakeRoute(),
                {"engine": "bigcell-grid", "width_um": 2.28,
                 "width_cols": 12, "attempts": []})

    cells = _fake_cells()
    out = os.path.join(str(tmp_path), "out")
    report = run_benchmark(
        cells, out, baselines=dict(_BASELINES),
        synth_runner=_fake_synth_rich, gds_writer=_GdsWritingFake(),
        verify_fn=lambda nl, pl, rt: _OkReport(),
        sanity_checker=lambda p: _RichSanityReport(),
        flow_dir=str(tmp_path))
    assert report["summary"]["width_ratio_python_over_astran"]["n"] == 1
    # now swap the engine on the same baseline-bearing cell
    report2 = run_benchmark(
        cells[:1], out + "2", baselines=dict(_BASELINES),
        synth_runner=synth_grid, gds_writer=_GdsWritingFake(),
        verify_fn=lambda nl, pl, rt: _OkReport(),
        sanity_checker=lambda p: _RichSanityReport(),
        flow_dir=str(tmp_path))
    assert report2["summary"]["width_ratio_python_over_astran"]["n"] == 1
    assert report2["summary"]["quality"]["ratio_same_semantics"]["n"] == 0
    assert report2["summary"]["quality"]["ratio_same_semantics"][
        "median"] is None


def test_quality_runtime_percentiles_and_failures(tmp_path):
    # p90 over ALL cells with a measured runtime -- closures AND
    # unsupported cells (their solver time is real cost)
    state = {"n": 0}
    attempts_pool = [[{"seconds": 1.0}],
                     [{"seconds": 2.0}, {"seconds": 10.0}]]

    def synth(netlist, **kw):
        att = attempts_pool[state["n"]]
        state["n"] += 1
        return ({}, _FakeRoute(),
                {"engine": "bigcell-full", "width_um": 0.57,
                 "width_cols": 3, "attempts": att})

    out = os.path.join(str(tmp_path), "out")
    report = run_benchmark(
        _fake_cells(), out, baselines={}, synth_runner=synth,
        gds_writer=_fake_gds_writer,
        verify_fn=lambda nl, pl, rt: _OkReport(),
        sanity_checker=lambda p: _SanityReport(True, 0.57),
        flow_dir=str(tmp_path))
    run_summary = report["summary"]["quality"]["runtime_s"]
    # totals [1.0, 12.0]: p50 interpolates to 6.5, p90 to 10.9
    assert run_summary["n"] == 2
    assert run_summary["p50"] == 6.5
    assert run_summary["p90"] == 10.9
    assert run_summary["max"] == 12.0


def test_runtime_from_attempts_pure():
    assert runtime_from_attempts(None) == {"total": 0.0, "place": 0.0,
                                           "route": 0.0, "window": 0.0}
    assert runtime_from_attempts([]) == {"total": 0.0, "place": 0.0,
                                         "route": 0.0, "window": 0.0}
    # a stageless attempt (the rung-2 router) counts as route time
    assert runtime_from_attempts(
        [{"seconds": 2.5}]) == {"total": 2.5, "place": 0.0, "route": 2.5,
                                "window": 0.0}
    # attempts without seconds are ignored, window beats stage
    assert runtime_from_attempts(
        [{"rung": 1, "stage": "layout"},
         {"rung": 2.5, "stage": "routing", "window": [0, 4], "seconds": 9.94},
         {"rung": 1, "stage": "layout", "seconds": 1.0},
         {"rung": 3, "stage": "placement", "seconds": 2.06},
         {"rung": 3, "stage": "routing", "seconds": 3.0}]) == {
        "total": 16.0, "place": 3.1, "route": 3.0, "window": 9.9}


def test_unsupported_cell_carries_runtime(tmp_path):
    out = os.path.join(str(tmp_path), "out")
    report = run_benchmark(_fake_cells()[:1], out, baselines={},
                           synth_runner=_fake_synth_unsupported,
                           gds_writer=_fake_gds_writer,
                           verify_fn=lambda nl, pl, rt: _OkReport(),
                           sanity_checker=lambda p: _SanityReport(),
                           flow_dir=str(tmp_path))
    rec = report["cells"][0]
    assert rec["status"] == "unsupported"
    assert rec["quality"]["pin_access"] is None
    assert rec["quality"]["runtime_s"]["total"] == 0.0


def test_cached_cell_keeps_runtime_and_remeasures_pins(tmp_path):
    out = os.path.join(str(tmp_path), "out")
    kwargs = dict(baselines=dict(_BASELINES),
                  synth_runner=_fake_synth_rich,
                  gds_writer=_GdsWritingFake(),
                  verify_fn=lambda nl, pl, rt: _OkReport(),
                  sanity_checker=lambda p: _RichSanityReport(),
                  flow_dir=str(tmp_path))
    cells = _fake_cells()[:1]
    first = run_benchmark(cells, out, **kwargs)
    assert first["cells"][0]["status"] == "ok"
    second = run_benchmark(cells, out, **kwargs)
    rec = second["cells"][0]
    assert rec["status"] == "cached"
    # runtime carried from the synthesis that made the artifacts
    assert rec["quality"]["runtime_s"]["total"] == 17.8
    # pin access re-measured on the artifact (fresh GDS read)
    assert rec["quality"]["pin_access"]["score"] == 0.75


# --- generalization: bands, verdict, hold-out loader ----------------------

def test_size_band_boundaries():
    assert size_band(1) == "small"
    assert size_band(8) == "small"
    assert size_band(9) == "medium"
    assert size_band(16) == "medium"
    assert size_band(17) == "large"
    assert size_band(64) == "large"
    assert size_band(0) is None


def _rec(t, status):
    return {"name": "c%d" % t, "source": "s%d" % t, "T": t,
            "status": status}


def test_band_closure_counts_and_rates():
    records = [_rec(2, "ok"), _rec(6, "cached"), _rec(4, "unsupported"),
               _rec(10, "ok"), _rec(12, "unsupported"),
               _rec(20, "ok"), _rec(30, "error")]
    bands = band_closure(records)
    assert bands["small"] == {"cells": 3, "closed": 2, "rate": round(2 / 3, 4)}
    assert bands["medium"] == {"cells": 2, "closed": 1, "rate": 0.5}
    assert bands["large"] == {"cells": 2, "closed": 1, "rate": 0.5}
    # an empty band is rate None, never a fabricated 0%
    assert band_closure([])["small"] == {"cells": 0, "closed": 0,
                                         "rate": None}


def test_generalization_verdict_rules():
    dev = {"small": {"cells": 10, "closed": 10, "rate": 1.0},
           "medium": {"cells": 10, "closed": 5, "rate": 0.5},
           "large": {"cells": 10, "closed": 0, "rate": 0.0}}
    # consistent: every band within the tolerance
    hold = {"small": {"cells": 5, "closed": 5, "rate": 1.0},
            "medium": {"cells": 4, "closed": 2, "rate": 0.5},
            "large": {"cells": 2, "closed": 0, "rate": 0.0}}
    verdict, worst = generalization_verdict(hold, dev)
    assert "consistent" in verdict
    # all deltas are 0.0: the first band in SIZE_BANDS order is "worst"
    assert worst[0] == "small" and worst[1] == 0.0
    # a drop beyond the tolerance names the band and the overfit signal
    hold2 = {"small": {"cells": 5, "closed": 5, "rate": 1.0},
             "medium": {"cells": 4, "closed": 1, "rate": 0.25},
             "large": {"cells": 2, "closed": 0, "rate": 0.0}}
    verdict2, worst2 = generalization_verdict(hold2, dev)
    assert "drops" in verdict2 and "overfit" in verdict2
    assert worst2[0] == "medium" and abs(worst2[1] + 0.25) < 1e-9
    # a band missing on either side is simply not compared
    verdict3, worst3 = generalization_verdict(
        {"small": {"cells": 3, "closed": 0, "rate": 0.0}}, dev)
    assert "drops" in verdict3 and worst3[0] == "small"
    # no dev rates at all: honest unknown, never success
    verdict4, worst4 = generalization_verdict(hold, None)
    assert "unavailable" in verdict4 and worst4 is None
    verdict5, worst5 = generalization_verdict(
        {"small": {"cells": 0, "closed": 0, "rate": None}}, dev)
    assert "unavailable" in verdict5 and worst5 is None


def test_load_holdout_cells_from_fake_dir(tmp_path, monkeypatch):
    hold = os.path.join(str(tmp_path), "hold")
    _mk_file(hold, "alpha.sp", INV.replace("INV", "ALPHA"))
    _mk_file(hold, "beta.sp", NAND2.replace("NAND2", "BETA"))
    _mk_file(hold, "unparseable.sp", ".subckt EMPTY VCC GND\n.ends\n")
    _mk_file(hold, "notes.txt", "not a deck")
    monkeypatch.setattr(benchmark_mod, "HOLDOUT_DIR", "hold")
    cells = load_holdout_cells(str(tmp_path))
    # deterministic, sorted, one BenchmarkCell per parseable deck
    assert [c.name for c in cells] == ["ALPHA", "BETA"]
    assert [c.source for c in cells] == ["hold/alpha.sp", "hold/beta.sp"]
    assert cells[0].transistors == 2 and cells[1].transistors == 4
    assert isinstance(cells[0].netlist, CellNetlist)
    again = load_holdout_cells(str(tmp_path))
    assert [(c.name, c.source) for c in again] == \
        [(c.name, c.source) for c in cells]


def test_run_generalization_end_to_end_with_fakes(tmp_path, monkeypatch):
    hold = os.path.join(str(tmp_path), "hold")
    _mk_file(hold, "alpha.sp", INV.replace("INV", "ALPHA"))       # small ok
    _mk_file(hold, "beta.sp", NAND2.replace("NAND2", "BETA"))     # small ok
    monkeypatch.setattr(benchmark_mod, "HOLDOUT_DIR", "hold")
    out = os.path.join(str(tmp_path), "gen")
    dev = {"cells": [_rec(2, "ok"), _rec(4, "unsupported"),
                     _rec(10, "ok")]}
    result = run_generalization(
        out, dev_report=dev, baselines={},
        synth_runner=_fake_synth_ok, gds_writer=_fake_gds_writer,
        verify_fn=lambda nl, pl, rt: _OkReport(),
        sanity_checker=lambda p: _SanityReport(True, 0.57),
        pin_access_scorer=False, flow_dir=str(tmp_path))
    # bands from the hold-out run, dev bands from the injected records
    assert result["bands"]["small"] == {"cells": 2, "closed": 2, "rate": 1.0}
    assert result["bands"]["medium"]["cells"] == 0
    assert result["dev_bands"]["small"]["rate"] == 0.5
    # small 100% vs dev 50%: no drop, the verdict is consistency
    assert "consistent" in result["verdict"]
    # the quality panel of the hold-out run is carried through
    quality = result["holdout"]["summary"]["quality"]
    assert quality["closure_rate"] == 1.0
    assert quality["pin_access"]["n"] == 0      # scorer disabled
    # files written: run_benchmark's own + the generalization pair
    assert os.path.exists(os.path.join(out, "report.json"))
    gen_md = open(os.path.join(out, "generalization.md")).read()
    assert "# Generalization" in gen_md and "Verdict" in gen_md
    assert "| ALPHA | 2 | small |" in gen_md
    gen_json = json.load(open(os.path.join(out, "generalization.json")))
    assert gen_json["bands"]["small"]["closed"] == 2
    assert gen_json["dev_source"] == "injected"   # a dict was injected


def test_run_generalization_without_dev_report_is_honest(tmp_path,
                                                         monkeypatch):
    hold = os.path.join(str(tmp_path), "hold")
    _mk_file(hold, "alpha.sp", INV.replace("INV", "ALPHA"))
    monkeypatch.setattr(benchmark_mod, "HOLDOUT_DIR", "hold")
    monkeypatch.setattr(benchmark_mod, "DEV_REPORT_PATH",
                        "no/such/report.json")
    out = os.path.join(str(tmp_path), "gen")
    result = run_generalization(
        out, baselines={}, synth_runner=_fake_synth_ok,
        gds_writer=_fake_gds_writer,
        verify_fn=lambda nl, pl, rt: _OkReport(),
        sanity_checker=lambda p: _SanityReport(True, 0.57),
        pin_access_scorer=False, flow_dir=str(tmp_path))
    assert result["dev_bands"] is None
    assert "unavailable" in result["verdict"]
    md = open(os.path.join(out, "generalization.md")).read()
    assert "unavailable" in md and "unknown" in md


def test_run_generalization_requires_cells(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark_mod, "HOLDOUT_DIR", "empty_dir")
    with pytest.raises(RuntimeError) as exc:
        run_generalization(os.path.join(str(tmp_path), "gen"),
                           flow_dir=str(tmp_path))
    assert "no hold-out cells" in str(exc.value)
