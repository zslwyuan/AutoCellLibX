"""Roadmap P0-5: pin the parity of ``pySrc/main.py`` and ``gui/flow_core.py``.

``gui/flow_core.py`` is a port of ``main.py``'s mining control flow; so far
their equivalence (thresholds, trace-keyed de-dup, 0x0-layout exclusion,
incremental bestRecord writes) rested on code review only.  This test runs
both end to end on a throwaway copy of the repository inputs with ASTRAN
stubbed out, then asserts identical records (modulo the runtime line),
identical exported netlists, and identical detected/dumped pattern traces.

The ASTRAN stub derives a deterministic pseudo width from the exported
netlist bytes + cell name, so identical netlists (the property under test)
yield identical widths in both flows.  A stubbed "run" writes exactly the
two files the flows consume: ``<name>.gds`` (existence is all the mtime
cache checks) and ``<name>.Astranlog`` carrying the
``-> Cell Size (W x H):`` line that ``loadAstranArea`` parses.

Everything happens under ``tmp_path``; the tracked artifacts in
``pySrc/outputs/`` are never touched.  Both flows run their default
configuration (including beam growth, ``growBeamWidth=2``).

Capture points (kept symmetric -- main.py star-imports its helpers into its
own module namespace, flow_core calls them as module attributes):

* ``exportSpiceNetlist`` (patched on ``main`` for the CLI flow, on the
  ``spice`` module for the GUI flow): in phase 1 every dumped pattern is
  drawn and immediately exported under its id, so an export whose id equals
  the most recent draw is a dump; the remaining calls are growth exports.
  This reconstructs each flow's ``detectedPatterns`` (in order) and
  ``dumpedPaterns`` (trace -> id) exactly.
* ``drawColorfulFigureForGraphWithAttributes`` (patched on ``main`` /
  ``BLIFGraphUtil``): the dumped COMPLEX id sequence.
* ``heuristic_label_initial_clusters_based_on`` (patched on
  ``main`` / ``BLIFPreProc``): the phase-2 target trace sequence.
"""
import hashlib
import os
import re
import shutil

import matplotlib
matplotlib.use("Agg")   # headless, before any flow import pulls in pyplot

import pytest

REPO_DIR = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
STDCELLLIB_DIR = os.path.join(REPO_DIR, "stdCelllib")
BLIF_DIR = os.path.join(REPO_DIR, "benchmark", "blif")

CELL_HEIGHT_UM = 2.47   # the row height both flows are configured for


# ------------------------------------------------------------- ASTRAN stubs
def _fake_cell_width(spice_netlist_path, cell_name):
    """Deterministic pseudo width (multiple of 0.19 um, the M1 pitch).

    Same (netlist bytes, cell name) -> same width in both flows; distinct
    cells almost always differ, so the mining loop exercises its real
    branching instead of degenerate all-equal areas.
    """
    with open(spice_netlist_path, "rb") as fh:
        digest = hashlib.md5(fh.read() + cell_name.encode("utf-8")).hexdigest()
    return 0.19 * (6 + int(digest, 16) % 25)


def _write_fake_layout(command_dir, cell_name, width):
    os.makedirs(command_dir, exist_ok=True)
    # A minimal but *valid* GDS: the flow's layout sanity gate
    # (pySrc/layout_sanity.py) parses the file and requires metal1-active
    # polygons spanning the row height plus supply labels.
    import gdstk
    from layout_sanity import ASTRAN_GDS_UNITS_PER_UM
    lib = gdstk.Library("FAKE")
    cell = lib.new_cell(cell_name)
    unit = ASTRAN_GDS_UNITS_PER_UM
    cell.add(gdstk.rectangle((0.1 * unit, 0.1 * unit),
                             (0.2 * unit, 0.2 * unit), layer=1))
    cell.add(gdstk.rectangle((0.3 * unit, 0.3 * unit),
                             (0.4 * unit, 0.4 * unit), layer=9))
    cell.add(gdstk.rectangle((0, 0), (width * unit, CELL_HEIGHT_UM * unit),
                             layer=49))
    cell.add(gdstk.Label("VCC", (0.05 * unit, 0.05 * unit), layer=49))
    cell.add(gdstk.Label("GND", (0.05 * unit,
                                 (CELL_HEIGHT_UM - 0.1) * unit), layer=49))
    lib.write_gds(os.path.join(command_dir, cell_name + ".gds"))
    with open(os.path.join(command_dir, cell_name + ".Astranlog"), "w") as fh:
        fh.write("stubbed ASTRAN run\n")
        fh.write("-> Cell Size (W x H): %.2f x %.2f\n"
                 % (width, CELL_HEIGHT_UM))


def _fake_run_astran_for_netlist(AstranPath, gurobiPath, technologyPath,
                                 spiceNetlistPath, complexName, commandDir):
    """Drop-in for ``Astran.runAstranForNetlist`` in main.py's namespace."""
    _write_fake_layout(commandDir, complexName,
                       _fake_cell_width(spiceNetlistPath, complexName))


# ------------------------------------------------------------------ sandbox
def _make_sandbox(base_dir):
    """Minimal repo layout the flows' relative paths resolve against."""
    pysrc = os.path.join(base_dir, "pySrc")
    os.makedirs(os.path.join(pysrc, "outputs"))
    os.makedirs(os.path.join(pysrc, "originalAstranStdCells"))
    lib_dir = os.path.join(base_dir, "stdCelllib")
    os.makedirs(lib_dir)
    for name in ("gscl45nm.lib", "cellsAstranFriendly.sp", "gscl45nm.lef"):
        shutil.copyfile(os.path.join(STDCELLLIB_DIR, name),
                        os.path.join(lib_dir, name))
    blif_dir = os.path.join(base_dir, "benchmark", "blif")
    os.makedirs(blif_dir)
    shutil.copyfile(os.path.join(BLIF_DIR, "adder.blif"),
                    os.path.join(blif_dir, "adder.blif"))
    return {"pysrc": pysrc, "lib": lib_dir, "blif": blif_dir}


def _png_id(filename):
    m = re.match(r"^COMPLEX(\d+)\.png$", filename)
    assert m, "unexpected drawn file %r" % filename
    return int(m.group(1))


class _DumpTracker(object):
    """Reconstruct detectedPatterns/dumpedPaterns from draw+export spies.

    Phase 1 dumps a pattern by drawing it and immediately exporting its
    netlist under the same id; growth exports arrive without a preceding
    draw of that id.  Watching the two event streams therefore reproduces
    exactly what the flow appended to its (local) bookkeeping structures.
    """

    def __init__(self):
        self.draw_ids = []
        self.detected = []      # traces, in dump order
        self.dumped = {}        # trace -> COMPLEX id

    def on_draw(self, save_to_file):
        self.draw_ids.append(_png_id(os.path.basename(str(save_to_file))))

    def on_export(self, cluster_seq, merge_cell_type_id):
        pattern_id = int(merge_cell_type_id)
        if self.draw_ids and pattern_id == self.draw_ids[-1] \
                and cluster_seq.patternExtensionTrace not in self.dumped:
            self.detected.append(cluster_seq.patternExtensionTrace)
            self.dumped[cluster_seq.patternExtensionTrace] = pattern_id


# --------------------------------------------------------------- the runners
def _run_main_flow(sandbox, monkeypatch):
    """Run pySrc/main.py's main() in the sandbox.

    Returns (out_dir, tracker, phase2_targets): the tracker reconstructs
    main's own detectedPatterns/dumpedPaterns; phase2_targets is the target
    trace sequence its phase 2 re-derived, in iteration order.
    """
    import core.pipeline
    import core.config

    tracker = _DumpTracker()
    phase2_targets = []
    real_draw = core.pipeline.drawColorfulFigureForGraphWithAttributes
    real_export = core.pipeline.exportSpiceNetlist
    real_based_on =         core.pipeline.heuristic_label_initial_clusters_based_on

    def spy_draw(*args, **kwargs):
        tracker.on_draw(kwargs.get("save_to_file", ""))
        return real_draw(*args, **kwargs)

    def spy_export(cluster_seq, subckts, merge_cell_type_id, output_dir):
        tracker.on_export(cluster_seq, merge_cell_type_id)
        return real_export(cluster_seq, subckts, merge_cell_type_id,
                           output_dir)

    def spy_based_on(graph, cells, netlist, trace,
                 singleOutputSeeds=False):
        phase2_targets.append(trace)
        return real_based_on(graph, cells, netlist, trace)

    monkeypatch.setattr("core.pipeline.runAstranForNetlist",
                        _fake_run_astran_for_netlist)
    monkeypatch.setattr(
        "core.pipeline.drawColorfulFigureForGraphWithAttributes",
        spy_draw)
    monkeypatch.setattr("core.pipeline.exportSpiceNetlist", spy_export)
    monkeypatch.setattr(
        "core.pipeline.heuristic_label_initial_clusters_based_on",
        spy_based_on)
    monkeypatch.chdir(sandbox["pysrc"])
    cfg = core.config.FlowConfig.from_env()
    cfg.astranBuildPath = "stub"          # enable the (stubbed) layout path
    core.pipeline.runPipeline(cfg)
    return (os.path.join(sandbox["pysrc"], "outputs", "adder"),
            tracker, phase2_targets)


def _run_gui_flow(sandbox, monkeypatch):
    """Run gui/flow_core.py in its own sandbox.

    Returns (out_dir, summary, tracker, phase2_targets) -- the same
    symmetric capture as the main run.
    """
    import BLIFGraphUtil
    import BLIFPreProc
    import spice
    from gui import artifacts, flow_core

    def fake_run_astran(self, name, netlist_abs, command_dir_abs, label=None,
                        netlist_lib=None, technology_path=None, geometry=None):
        _write_fake_layout(command_dir_abs, name,
                           _fake_cell_width(netlist_abs, name))
        # Return the same object the real _run_astran returns after parsing.
        return artifacts.parse_astran_log(
            os.path.join(command_dir_abs, name + ".Astranlog"))

    cfg = flow_core.FlowConfig()
    cfg.benchmarks = ["adder"]
    cfg.do_layouts = True
    cfg.do_phase2 = True
    cfg.liberty_file = os.path.join(sandbox["lib"], "gscl45nm.lib")
    cfg.spice_lib_file = os.path.join(sandbox["lib"], "cellsAstranFriendly.sp")
    cfg.lef_file = os.path.join(sandbox["lib"], "gscl45nm.lef")
    cfg.custom_blifs = {"adder": os.path.join(sandbox["blif"], "adder.blif")}

    monkeypatch.setattr(flow_core.paths, "PYSRC_DIR", sandbox["pysrc"])
    monkeypatch.setattr(flow_core.paths, "OUTPUTS_DIR",
                        os.path.join(sandbox["pysrc"], "outputs"))
    monkeypatch.setattr(flow_core.paths, "ORIGINAL_CELLS_DIR",
                        os.path.join(sandbox["pysrc"], "originalAstranStdCells"))
    monkeypatch.setattr(flow_core.paths, "probe_environment", lambda: [])
    monkeypatch.setattr(flow_core.FlowRunner, "astran_available",
                        lambda self: True)
    monkeypatch.setattr(flow_core.FlowRunner, "_run_astran", fake_run_astran)

    # Symmetric capture: flow_core resolves these as module attributes.
    tracker = _DumpTracker()
    phase2_targets = []
    real_draw = BLIFGraphUtil.drawColorfulFigureForGraphWithAttributes
    real_export = spice.exportSpiceNetlist
    real_based_on = \
        BLIFPreProc.heuristic_label_initial_clusters_based_on

    def spy_draw(*args, **kwargs):
        tracker.on_draw(kwargs.get("save_to_file", ""))
        return real_draw(*args, **kwargs)

    def spy_export(cluster_seq, subckts, merge_cell_type_id, output_dir):
        tracker.on_export(cluster_seq, merge_cell_type_id)
        return real_export(cluster_seq, subckts, merge_cell_type_id,
                           output_dir)

    def spy_based_on(graph, cells, netlist, trace,
                 singleOutputSeeds=False):
        phase2_targets.append(trace)
        return real_based_on(graph, cells, netlist, trace)

    import core.pipeline
    monkeypatch.setattr(
        core.pipeline, "drawColorfulFigureForGraphWithAttributes", spy_draw)
    monkeypatch.setattr(core.pipeline, "exportSpiceNetlist", spy_export)
    monkeypatch.setattr(
        core.pipeline,
        "heuristic_label_initial_clusters_based_on", spy_based_on)

    summary_box = {}

    class _Hooks(flow_core.Hooks):
        def finished(self, summary):
            summary_box["summary"] = summary

    flow_core.FlowRunner(cfg, _Hooks()).run()
    return (os.path.join(sandbox["pysrc"], "outputs", "adder"),
            summary_box.get("summary", {}), tracker, phase2_targets)


# --------------------------------------------------------------- comparisons
def _strip_runtime_line(text):
    """Remove the ``\\n runtime: <t>  (s)`` trailer of a bestRecord file."""
    out = []
    for line in text.splitlines():
        if line.lstrip().startswith("runtime:"):
            # print("\\n runtime:", ...) leaves a blank line just before it.
            if out and out[-1].strip() == "":
                out.pop()
            continue
        out.append(line)
    return "\n".join(out) + "\n"


def _record_rows(path):
    """Rows of a bestRecord-seperate<bench> file as (id, trace) pairs."""
    rows = []
    with open(path, "r") as fh:
        for line in fh:
            line = line.strip()
            if not line.startswith("|") or "patternCode" in line:
                continue    # blank lines and the header row
            cols = [c.strip() for c in line.split("|")]
            cols = [c for c in cols if c != ""]
            assert len(cols) == 8, "unexpected record row: %r" % line
            m = re.match(r"^COMPLEX(\d+)$", cols[6])
            assert m, "unexpected patternName %r" % cols[6]
            rows.append((int(m.group(1)), cols[7]))
    return rows


def _spice_exports(out_dir):
    """filename -> bytes of every exported COMPLEX netlist in out_dir."""
    return {f: open(os.path.join(out_dir, f), "rb").read()
            for f in sorted(os.listdir(out_dir)) if f.endswith(".sp")}


# --------------------------------------------------------------------- test
def test_mining_flow_parity_adder(tmp_path, monkeypatch):
    main_sandbox = _make_sandbox(str(tmp_path / "main_repo"))
    gui_sandbox = _make_sandbox(str(tmp_path / "gui_repo"))

    main_out, main_cap, main_targets = _run_main_flow(
        main_sandbox, monkeypatch)
    gui_out, summary, gui_cap, gui_targets = _run_gui_flow(
        gui_sandbox, monkeypatch)

    assert summary.get("ok") is True, "GUI flow failed: %r" % (summary,)
    assert len(main_cap.detected) > 0, \
        "no patterns detected; the test is vacuous"

    # -- pattern identity: same traces dumped in the same order under the
    #    same COMPLEX ids, and the same phase-2 re-derivation sequence
    assert main_cap.detected == gui_cap.detected, \
        "detectedPatterns diverged:\nmain.py:   %r\nflow_core: %r" \
        % (main_cap.detected, gui_cap.detected)
    assert main_cap.dumped == gui_cap.dumped, \
        "dumpedPaterns (trace -> id) diverged:\nmain.py:   %r\nflow_core: %r" \
        % (main_cap.dumped, gui_cap.dumped)
    assert main_cap.draw_ids == gui_cap.draw_ids
    assert main_targets == gui_targets, \
        "phase-2 target traces diverged:\nmain.py:   %r\nflow_core: %r" \
        % (main_targets, gui_targets)

    # -- the exported complex netlists are byte-identical
    main_sp = _spice_exports(main_out)
    gui_sp = _spice_exports(gui_out)
    assert main_sp == gui_sp, \
        "exported netlists diverged: main-only=%r gui-only=%r" % (
            sorted(set(main_sp) - set(gui_sp)),
            sorted(set(gui_sp) - set(main_sp)))

    # -- bestRecord-adder identical modulo the runtime line
    main_best = os.path.join(main_out, "bestRecord-adder")
    gui_best = os.path.join(gui_out, "bestRecord-adder")
    assert os.path.exists(main_best) and os.path.exists(gui_best)
    with open(main_best, "r") as fh:
        main_best_txt = fh.read()
    with open(gui_best, "r") as fh:
        gui_best_txt = fh.read()
    assert _strip_runtime_line(main_best_txt) == \
        _strip_runtime_line(gui_best_txt), \
        "bestRecord-adder diverged:\n--- main.py ---\n%s\n" \
        "--- flow_core ---\n%s" % (main_best_txt, gui_best_txt)

    # -- per-pattern records byte-identical, and their patternCode column
    #    is a subset of the detected traces in both flows (a detected
    #    pattern legitimately earns no row when phase 2 never re-derives
    #    it as a walk head)
    main_sep = os.path.join(main_out, "bestRecord-seperateadder")
    gui_sep = os.path.join(gui_out, "bestRecord-seperateadder")
    assert os.path.exists(main_sep) and os.path.exists(gui_sep)
    with open(main_sep, "rb") as fh:
        main_sep_bytes = fh.read()
    with open(gui_sep, "rb") as fh:
        gui_sep_bytes = fh.read()
    assert main_sep_bytes == gui_sep_bytes, \
        "bestRecord-seperateadder diverged:\n--- main.py ---\n%r\n" \
        "--- flow_core ---\n%r" % (main_sep_bytes, gui_sep_bytes)
    main_record_traces = set(t for _, t in _record_rows(main_sep))
    gui_record_traces = set(t for _, t in _record_rows(gui_sep))
    assert main_record_traces == gui_record_traces
    assert main_record_traces <= set(main_cap.detected)
    assert gui_record_traces <= set(gui_cap.detected)
