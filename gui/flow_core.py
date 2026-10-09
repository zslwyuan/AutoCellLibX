"""The AutoCellLibX pipeline as a configurable, observable, cancellable run.

This is a faithful port of ``pySrc/main.py``'s control flow with three
additions the GUI needs: progress callbacks, cooperative cancellation, and a
few knobs (which stages to run, a cap on ASTRAN launches).  The algorithm
itself -- thresholds, the trace-keyed de-duplication, the "exclude a pattern
whose layout is 0 x 0" guards, the incremental bestRecord write -- is kept
identical so a GUI run and a ``python main.py`` run produce the same cells.

Two deliberate differences from ``main()``, both to expose progress:

* ``loadDataAndPreprocess`` is inlined as graph -> baseline -> cluster ->
  dataset, because the ASTRAN baseline must be generated *between* building
  the graph (which yields the cell types) and loading the baseline areas.
  ``main()`` gets the same effect by calling the whole thing first.
* It is Qt-free: the caller supplies a ``Hooks`` object.  See flow_worker for
  the Qt bridge.
"""
import glob
import os
import shutil
import subprocess
import sys
import threading
import time

from . import artifacts, paths

# (key, human label) for the stage list shown in the UI.
STAGES = [
    ("env", "环境检查 Environment"),
    ("parse", "解析库与网表 Parse library + netlist"),
    ("baseline", "ASTRAN 基线单元 Baseline cells"),
    ("cluster", "初始模式聚类 Initial clustering"),
    ("mine", "模式挖掘与生长 Mine & grow"),
    ("layout", "复杂单元版图 Complex layouts"),
    ("phase2", "逐模式明细 Per-pattern records"),
    ("records", "写出结果 Write records"),
]

STAGE_LABELS = dict(STAGES)


class Cancelled(Exception):
    """Raised inside the runner when the user requests a stop."""


class AstranLaunchError(RuntimeError):
    """ASTRAN could not be started at all (as opposed to a cell that failed)."""


def _popen_astran(run_path, log_fh, **kwargs):
    """Launch ASTRAN, translating OS-level launch failures into clear guidance.

    The binary is a documented false positive for 360 Total Security
    (HEUR/QVM...Malware.Gen): it gets quarantined on first execution, so a
    path that existed at probe time can raise FileNotFoundError/PermissionError
    here.  A raw traceback tells the user nothing; this does.

    On Windows the child gets CREATE_NO_WINDOW: the GUI runs console-less
    (pythonw), so without it every ASTRAN cell launch would pop a black
    console window.  CREATE_NEW_PROCESS_GROUP keeps cancel able to kill the
    solver with it.
    """
    cmd = [paths.ASTRAN_BINARY, "--shell", run_path]
    try:
        if sys.platform == "win32":
            kwargs["creationflags"] = (subprocess.CREATE_NEW_PROCESS_GROUP |
                                       subprocess.CREATE_NO_WINDOW)
        return subprocess.Popen(cmd, cwd=paths.PYSRC_DIR, stdout=log_fh,
                                stderr=subprocess.STDOUT, **kwargs)
    except (PermissionError, FileNotFoundError, OSError) as exc:
        raise AstranLaunchError(
            "无法启动 ASTRAN 二进制 / cannot launch ASTRAN.\n"
            "  路径/path: %s\n  错误/error: %s\n\n"
            "最常见原因：360 Total Security 把 Astran.exe 误判为恶意软件并隔离"
            "（HEUR/QVM...Malware.Gen，误报，见 AGENTS.md 陷阱）。\n"
            "处理：在 360 的信任区加入 tools/astran/build/bin/（或 Astran.exe），"
            "然后重新构建：bash tools/astran/build_astran.sh"
            % (paths.ASTRAN_BINARY, exc)) from exc


class FlowConfig(object):
    """Everything the Configure tab can change."""

    def __init__(self):
        self.benchmarks = ["adder"]
        # User-added BLIF inputs: name -> absolute path.  A name in this map
        # shadows a same-named standard benchmark under benchmark/blif/.
        self.custom_blifs = {}
        # PDK inputs.  None means "use the repository defaults" (GSCL45 lib,
        # vendored ASTRAN technology file, ...); absolute paths override.
        self.liberty_file = None        # .lib (cell pin directions)
        self.spice_lib_file = None      # .sp (transistor-level cell bodies)
        self.technology_file = None     # .rul (ASTRAN design rules)
        self.lef_file = None            # .lef (nominal cell widths for area)
        self.layer_map_file = None      # Cadence layer map (stream -> name)
        # ASTRAN geometry overrides; None keeps pySrc/Astran.py constants.
        # Keys: cellsHeight, hGrid, vGrid, supplySize, nwellPos, cellTemplate.
        self.geometry = None
        self.top_thr = 5            # main.py: topThr
        self.ratio_thr = 0.05       # main.py: ratioThr
        self.cnt_thr = 30           # main.py: cntThr
        self.max_cells = 11         # patterns with >= this many cells are skipped
        self.grow_beam = 2          # heads grown per round (P0-3; 1 = legacy)
        self.max_rt_density = None  # routability gate (P0-4); None = report only
        self.layout_sanity_gate = True   # structural layout gate (P2 phase 0)
        self.use_width_proxy_for_growth = False  # P2 phase 1; report-only default
        self.require_reuse_eligible = False  # synthesis-reuse gate (AUDIT 5.25)
        self.do_baseline = True
        self.do_layouts = True
        self.do_phase2 = True
        self.force_regenerate = False   # ignore the .gds/.sp mtime cache
        self.clean_outputs = False      # remove stale COMPLEX* before running
        self.max_astran_runs = 0        # 0 = unlimited (a cap gives quick runs)

    # -------------------------------------------------- PDK path resolution
    def liberty(self):
        return self.liberty_file or paths.LIBERTY_FILE

    def spice_lib(self):
        return self.spice_lib_file or paths.SPICE_LIB_FILE

    def technology(self):
        return self.technology_file or paths.ASTRAN_TECHNOLOGY

    def lef(self):
        return self.lef_file or paths.LEF_FILE

    def layer_map(self):
        return self.layer_map_file or paths.LAYER_MAP_FILE

    def describe(self):
        extra = ""
        if self.custom_blifs:
            extra = " custom=%d" % len(self.custom_blifs)
        if self.liberty_file or self.spice_lib_file or self.technology_file \
                or self.lef_file or self.geometry:
            extra += " pdk=自定义"
        return ("benchmarks=%s topThr=%d ratioThr=%g cntThr=%d layouts=%s "
                "phase2=%s cap=%s%s" % (",".join(self.benchmarks), self.top_thr,
                                        self.ratio_thr, self.cnt_thr,
                                        self.do_layouts, self.do_phase2,
                                        self.max_astran_runs or "-", extra))


class Hooks(object):
    """Callback surface.  Override only what you need."""

    def log(self, message, level="info"):
        pass

    def stage(self, key, status, message="", progress=None):
        """status: pending|running|done|skipped|failed; progress: (cur,total)."""

    def design(self, info):
        """Design/library statistics once the netlist is parsed."""

    def pattern(self, info):
        """One candidate pattern was evaluated."""

    def cell(self, info):
        """An ASTRAN cell started, progressed or finished."""

    def metric(self, info):
        """The running saveArea for an iteration."""

    def record(self, info):
        """A bestRecord-* file was (re)written."""

    def finished(self, summary):
        pass


class FlowRunner(object):
    def __init__(self, config, hooks=None, cancel_event=None):
        self.cfg = config
        self.hooks = hooks or Hooks()
        self.cancel = cancel_event or threading.Event()
        self._astran_runs = 0
        self._done_stages = []
        self._flow = None            # imported flow modules namespace
        self._summary = {}

    # ---------------------------------------------------------------- utils
    def _check_cancel(self):
        if self.cancel.is_set():
            raise Cancelled()

    def _log(self, msg, level="info"):
        self.hooks.log(msg, level)

    def _stage(self, key, status, message="", progress=None):
        self.hooks.stage(key, status, message, progress)
        if status in ("done", "skipped", "failed") and key not in self._done_stages:
            self._done_stages.append(key)

    def _import_flow(self):
        """Import the pySrc modules (matplotlib forced to a headless backend).

        matplotlib.pyplot is used by the flow's pattern drawings; forcing Agg
        keeps those off any GUI event loop and out of the Qt backend's way.
        """
        if self._flow is not None:
            return self._flow
        paths.ensure_pysrc_on_path()
        import matplotlib
        matplotlib.use("Agg", force=True)
        import Astran
        import BLIFPreProc
        import BLIFGraphUtil
        import BLIFPatternGrowth
        import spice
        import GDSIIAnalysis
        import benefit
        import routability
        import electrical
        import timing_power
        import yosys_import
        import layout_sanity
        import width_proxy
        import liberty_gen
        import reuse
        self._flow = dict(Astran=Astran, BLIFPreProc=BLIFPreProc,
                          BLIFGraphUtil=BLIFGraphUtil,
                          BLIFPatternGrowth=BLIFPatternGrowth,
                          spice=spice, GDSIIAnalysis=GDSIIAnalysis,
                          benefit=benefit, routability=routability,
                          electrical=electrical, timing_power=timing_power,
                          yosys_import=yosys_import,
                          layout_sanity=layout_sanity,
                          width_proxy=width_proxy,
                          liberty_gen=liberty_gen, reuse=reuse)
        return self._flow

    def _rel(self, abs_path):
        """Path as the flow expects it: relative to pySrc, './'-prefixed."""
        rel = os.path.relpath(abs_path, paths.PYSRC_DIR)
        return "./" + rel.replace("\\", "/")

    def _blif_path(self, name):
        """Where a benchmark's netlist lives (custom BLIF shadows the standard dir)."""
        return self.cfg.custom_blifs.get(name) or paths.benchmark_path(name)

    # ------------------------------------------------------------- ASTRAN
    def _run_astran(self, name, netlist_abs, command_dir_abs, label=None,
                    netlist_lib=None, technology_path=None, geometry=None):
        """Run ASTRAN for one cell, streaming its log.  Returns an AstranLog.

        Reuses ``Astran.buildAstranCommands`` so the geometry constants stay
        centralised (AGENTS.md invariant 2) and the emitted ``.run`` matches
        what the CLI flow writes.  ``geometry`` lets the GUI override the
        constants (row height, grid, supply rails, ...) per the Configure tab.
        A single cell is run at a time: ASTRAN writes ILPmodel.lp/.sol into
        the process working directory, so concurrent runs would clobber each other.
        """
        flow = self._import_flow()
        Astran = flow["Astran"]

        netlist_rel = self._rel(netlist_abs)
        command_dir_rel = self._rel(command_dir_abs)
        script = Astran.buildAstranCommands(
            Astran.GUROBI_CL, technology_path or Astran.ASTRAN_TECHNOLOGY,
            netlist_rel, name, command_dir_rel, geometry=geometry)

        run_path = os.path.join(command_dir_abs, name + ".run")
        with open(run_path, "w") as fh:
            print(script, file=fh)
        log_path = os.path.join(command_dir_abs, name + ".Astranlog")

        self._astran_runs += 1
        t0 = time.time()
        self.hooks.cell({"name": name, "label": label or name, "state": "start",
                         "path": log_path, "attempt": 0, "phase": "launching",
                         "fraction": 0.0, "elapsed": 0.0})

        with open(log_path, "w") as log_fh:
            kwargs = {}
            if sys.platform == "win32":
                # Own process group so a cancel can take the solver with it.
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            proc = _popen_astran(run_path, log_fh, **kwargs)

            try:
                while proc.poll() is None:
                    if self.cancel.is_set():
                        self._kill(proc)
                        raise Cancelled()
                    log = artifacts.parse_astran_log(log_path, tail_bytes=400000)
                    self.hooks.cell({
                        "name": name, "label": label or name, "state": "running",
                        "path": log_path, "attempt": log.attempt_index,
                        "tracks": log.attempts[-1][0] if log.attempts else None,
                        "conservative": log.attempts[-1][1] if log.attempts else None,
                        "phase": log.last_phase or "starting",
                        "fraction": log.phase_fraction,
                        "width": log.width_um, "elapsed": time.time() - t0,
                        "solver_vars": log.solver_vars,
                        "solver_cons": log.solver_cons,
                        "status": log.solver_status,
                        "ntrans": log.n_transistors,
                    })
                    time.sleep(0.4)
                    log_fh.flush()
            finally:
                if proc.poll() is None:
                    self._kill(proc)
                try:
                    proc.wait(timeout=10)
                except Exception:
                    pass

        log = artifacts.parse_astran_log(log_path)
        state = "done" if log.complete and (log.width_um or 0) > 0 else "failed"
        self.hooks.cell({
            "name": name, "label": label or name, "state": state,
            "path": log_path, "attempt": log.attempt_index,
            "phase": log.last_phase, "fraction": 1.0 if state == "done" else 0.0,
            "width": log.width_um, "height": log.height_um,
            "elapsed": time.time() - t0, "log": log,
            "option3_retries": log.option3_retries,
            "repairs": log.spacing_repairs[-1] if log.spacing_repairs else None,
            "ntrans": log.n_transistors,
        })
        return log

    @staticmethod
    def _kill(proc):
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                               capture_output=True)
            else:
                proc.terminate()
        except Exception:      # pragma: no cover - best effort
            pass

    def astran_available(self):
        return os.path.exists(paths.ASTRAN_BINARY)

    # ------------------------------------------------------------- driver
    def run(self):
        t0 = time.time()
        prev_cwd = os.getcwd()
        try:
            # The flow modules reach for ../stdCelllib and ./outputs, so they
            # only work with cwd = pySrc.  Everything the GUI itself touches is
            # an absolute path (see paths.py), so this is safe.
            os.chdir(paths.PYSRC_DIR)
            self._run_all(t0)
        finally:
            os.chdir(prev_cwd)

    def _run_all(self, t0):
        try:
            self._import_flow()
        except Exception as exc:                       # noqa: BLE001
            self._stage("env", "failed", "无法导入流程模块 / cannot import flow: %s" % exc)
            self.hooks.finished({"ok": False, "error": str(exc),
                                 "elapsed": time.time() - t0})
            return

        self._stage("env", "running", "检查工具链 / probing toolchain")
        checks = paths.probe_environment()
        bad = [c for c in checks if not c.ok and c.required]
        if bad:
            self._stage("env", "failed", "; ".join(
                "%s: %s" % (c.label, c.detail) for c in bad))
            self._log("必需组件缺失 / missing required components: "
                      + ", ".join(c.label for c in bad), "error")
            for c in bad:
                self._log("  ! %s -> %s" % (c.label, c.hint or c.detail), "error")
            self.hooks.finished({"ok": False, "error": "environment not ready",
                                 "elapsed": time.time() - t0})
            return
        self._stage("env", "done", "%d 项检查通过 / %d checks passed"
                    % (len(checks), len(checks)))

        try:
            for bench in self.cfg.benchmarks:
                self._check_cancel()
                self._run_benchmark(bench, t0)
            self._summary = {"ok": True, "elapsed": time.time() - t0}
        except Cancelled:
            self._log("已取消 / cancelled", "warn")
            self._summary = {"ok": False, "cancelled": True,
                             "elapsed": time.time() - t0}
        except AstranLaunchError as exc:
            self._log(str(exc), "error")
            self._summary = {"ok": False, "error": "ASTRAN 无法启动 / launch failed",
                             "elapsed": time.time() - t0}
        except Exception as exc:                        # noqa: BLE001
            import traceback
            self._log(traceback.format_exc(), "error")
            self._summary = {"ok": False, "error": str(exc),
                             "elapsed": time.time() - t0}
        self.hooks.finished(self._summary)

    # ---------------------------------------------------------- per benchmark
    def _clean_output(self, out_dir):
        for pat in ("COMPLEX*.sp", "COMPLEX*.gds", "COMPLEX*.png",
                    "COMPLEX*.Astranlog", "COMPLEX*.run", "COMPLEX*.gds.bak",
                    "bestRecord-*"):
            for f in glob.glob(os.path.join(out_dir, pat)):
                try:
                    os.remove(f)
                except OSError:
                    pass
        self._log("已清空输出目录中的旧产物 / cleared stale outputs in %s"
                  % self._rel(out_dir), "warn")

    def _run_benchmark(self, bench, t0):
        flow = self._import_flow()
        BLIFPreProc = flow["BLIFPreProc"]
        BLIFGraphUtil = flow["BLIFGraphUtil"]
        BLIFPatternGrowth = flow["BLIFPatternGrowth"]
        spice = flow["spice"]
        GDSIIAnalysis = flow["GDSIIAnalysis"]

        blif_abs = self._blif_path(bench)
        if not os.path.exists(blif_abs):
            self._stage("parse", "failed", "找不到基准 / no such benchmark: " + bench)
            return

        out_dir = paths.output_dir(bench)
        os.makedirs(out_dir, exist_ok=True)
        self._log("=" * 78)
        self._log("%s  (%s, %.1f KB)" % (bench, self._rel(blif_abs),
                                         os.path.getsize(blif_abs) / 1024.0), "accent")
        if self.cfg.clean_outputs:
            self._clean_output(out_dir)

        # ---- parse: library + design graph ---------------------------------
        self._stage("parse", "running", "解析 liberty + BLIF / parsing design")
        self._check_cancel()
        (BLIFGraph, cells, netlist, stdCellTypesForFeature) = \
            BLIFPreProc.genGraphFromLibertyAndBLIF(
                self._rel(self.cfg.liberty()), self._rel(blif_abs))

        type_count = {}
        for cell in cells:
            name = cell.stdCellType.typeName
            type_count[name] = type_count.get(name, 0) + 1
        hist = sorted(type_count.items(), key=lambda kv: (-kv[1], kv[0]))
        stop_types = sum(1 for c in cells if c.stopType)
        self.hooks.design({
            "benchmark": bench, "nodes": BLIFGraph.number_of_nodes(),
            "edges": BLIFGraph.number_of_edges(), "std_types": len(type_count),
            "type_hist": hist, "stop_cells": stop_types,
            "feature_types": stdCellTypesForFeature,
        })
        self._log("设计图 / design graph: %d 单元 %d 连接，%d 种单元类型"
                  % (BLIFGraph.number_of_nodes(), BLIFGraph.number_of_edges(),
                     len(type_count)))
        self._stage("parse", "done", "%d nodes / %d edges"
                    % (BLIFGraph.number_of_nodes(), BLIFGraph.number_of_edges()))

        # ---- baseline: ASTRAN reference cells ------------------------------
        self._run_baseline(stdCellTypesForFeature, t0)

        # ---- cluster --------------------------------------------------------
        self._stage("cluster", "running", "按编码聚类模式 / grouping by pattern code")
        self._check_cancel()
        clusterSeqs, clusterNum = \
            BLIFPreProc.heuristicLabelSomeNodesAndGetInitialClusters(
                BLIFGraph, cells, netlist)
        dataset, maxLabelIndex = BLIFPreProc.convertBLIFGraphIntoDataset(
            BLIFGraph, stdCellTypesForFeature, 36)
        self._log("初始模式序列 / initial pattern sequences: %d" % len(clusterSeqs))
        self._stage("cluster", "done", "%d pattern sequences" % len(clusterSeqs))

        # ---- areas ----------------------------------------------------------
        # GSCL reference widths come from the LEF the user configured (default:
        # gscl45nm.lef); same METRIC as loadOrignalGSCL45nmGDS, any PDK.
        stdType2GSCLArea = artifacts.read_lef_widths(self.cfg.lef())
        oriArea = BLIFPreProc.getArea(cells, stdType2GSCLArea)
        stdType2AstranArea = GDSIIAnalysis.loadAstranGDS()
        astranArea = BLIFPreProc.getArea(cells, stdType2AstranArea)
        self._log("面积基准 / area baseline: GSCL=%.2f, ASTRAN=%.2f (总宽 µm)"
                  % (oriArea, astranArea))
        self._stage("baseline", "done", "ASTRAN baseline %.1f µm" % astranArea)

        clusterSeqs = BLIFGraphUtil.sortPatternClusterSeqs(clusterSeqs)

        context = dict(
            flow=flow, bench=bench, out_dir=out_dir, cells=cells,
            BLIFGraph=BLIFGraph, clusterNum=clusterNum, patternNum=len(clusterSeqs),
            stdType2GSCLArea=stdType2GSCLArea, stdType2AstranArea=stdType2AstranArea,
            oriArea=oriArea, astranArea=astranArea, subckts=None,
            dumpedPaterns={}, detectedPatterns=[], startTime=t0)

        # Online-calibrated shrink model for growth benefit estimation
        # (P0-3), mirroring main.py: vetoes predicted-loss growth branches
        # before they cost an ASTRAN run.
        context["shrinkModel"] = flow["benefit"].ShrinkModel()
        context["growthBenefitEstimator"] = \
            flow["benefit"].makeGrowthBenefitEstimator(
                stdType2AstranArea, context["shrinkModel"])

        # Electrical context per candidate (P1-7, report-only).
        context["cellElectricalMetrics"] = \
            flow["electrical"].loadCellElectricalMetrics(
                str(self.cfg.liberty()))
        context["cellTimingPower"] = flow["timing_power"].loadTimingPower(
            str(self.cfg.liberty()))
        context["libFunctions"] = flow["liberty_gen"].loadLibertyFunctions(
            str(self.cfg.liberty()))

        # Yosys re-import: design-level area/histogram cross-check
        # (graceful when no yosys executable is installed).
        design_lib_area = 0.0
        for c in cells:
            m = context["cellElectricalMetrics"].get(c.stdCellType.typeName)
            if m is not None and m["area"] is not None:
                design_lib_area += m["area"]
        yosys_stat = flow["yosys_import"].runYosysStat(
            str(self.cfg.liberty()), str(self._blif_path(bench)))
        self._log("yosys stat 交叉校验 / cross-check: %s"
                  % flow["yosys_import"].compareWithFlowArea(
                      yosys_stat, design_lib_area))
        our_type_counts = {}
        for c in cells:
            if c.stopType:
                continue
            t = c.stdCellType.typeName
            our_type_counts[t] = our_type_counts.get(t, 0) + 1
        self._log("yosys 单元计数交叉校验 / cell-count cross-check: %s"
                  % flow["yosys_import"].compareCellCounts(
                      yosys_stat, our_type_counts))

        # Width proxy (P2 phase 1, mirrors main.py): report-only default.
        transistor_counts = flow["width_proxy"].countTransistorsPerType(
            self._rel(self.cfg.spice_lib()))
        wp_samples = flow["width_proxy"].collectSamples(
            sorted(glob.glob(os.path.join(paths.PYSRC_DIR, "outputs", "*"))),
            transistor_counts, stdType2AstranArea)
        context["transistorCounts"] = transistor_counts
        context["widthProxy"] = None
        if len(wp_samples) >= 4:
            context["widthProxy"] = flow["width_proxy"].WidthProxy().fit(
                wp_samples)
            self._log("宽度代理 / width proxy LOO: %s"
                      % flow["width_proxy"].evaluateLOO(wp_samples))
        if (self.cfg.use_width_proxy_for_growth
                and context["widthProxy"] is not None):
            context["growthBenefitEstimator"] = \
                flow["width_proxy"].makeProxyBenefitEstimator(
                    context["widthProxy"], stdType2AstranArea,
                    transistor_counts)

        context["subckts"] = spice.loadSpiceSubcircuits(
            self._rel(self.cfg.spice_lib()))

        # ---- main mining loop ----------------------------------------------
        self._stage("mine", "running", "贪心挖掘 / greedy mining")
        self._mine(context, clusterSeqs)

        # ---- phase 2 --------------------------------------------------------
        if self.cfg.do_phase2 and context["detectedPatterns"]:
            self._stage("phase2", "running", "逐模式明细 / per-pattern records")
            self._phase2(context)
        elif self.cfg.do_phase2:
            self._stage("phase2", "skipped", "没有检测到模式 / no patterns detected")
        else:
            self._stage("phase2", "skipped", "已禁用 / disabled")

        self._stage("records", "done", "结果写入 %s" % self._rel(out_dir))
        self._log("基准 %s 完成，用时 %.1f s" % (bench, time.time() - t0), "ok")

    def _baseline_is_stale_geometry(self):
        """Whether the cached baseline cells match the configured geometry.

        A custom ASTRAN technology file, or geometry values that differ from
        the pySrc/Astran.py constants, invalidate every cached baseline cell:
        the area comparison needs the baseline and the generated cells at the
        same row height (AGENTS.md invariant 10).
        """
        cfg = self.cfg
        if cfg.geometry is None and cfg.technology_file is None:
            return False
        if cfg.technology_file is not None:
            return True
        Astran = self._import_flow()["Astran"]
        g = cfg.geometry
        return not (g["cellsHeight"] == Astran.ASTRAN_CELLS_HEIGHT and
                    g["hGrid"] == Astran.ASTRAN_HGRID and
                    g["vGrid"] == Astran.ASTRAN_VGRID and
                    g["supplySize"] == Astran.ASTRAN_SUPPLY_SIZE and
                    g["nwellPos"] == Astran.ASTRAN_NWELL_POS and
                    g["cellTemplate"] == Astran.ASTRAN_CELL_TEMPLATE)

    def _run_baseline(self, stdCellTypesForFeature, t0):
        """Generate the ASTRAN reference layouts the area comparison needs.

        Width is only an area proxy at a matched row height, so the baseline
        goes through ``runAstranForNetlist`` with the same geometry constants
        as the generated cells.  A custom geometry/technology configured in
        the GUI invalidates the cache and regenerates every baseline cell.
        """
        if not self.cfg.do_baseline:
            self._stage("baseline", "skipped", "已禁用 / disabled")
            return
        if not self.astran_available():
            self._stage("baseline", "skipped", "ASTRAN 不可用 / ASTRAN not built")
            return

        base_dir = paths.ORIGINAL_CELLS_DIR
        os.makedirs(base_dir, exist_ok=True)
        force_all = self._baseline_is_stale_geometry()
        todo = []
        for t in stdCellTypesForFeature:
            if "bool" in t:
                continue
            if t.startswith("minorType"):
                continue
            if not force_all and \
                    os.path.exists(os.path.join(base_dir, t + ".Astranlog")) and \
                    not self.cfg.force_regenerate:
                continue
            todo.append(t)

        if force_all and todo:
            self._log("自定义几何/工艺：基线单元将全部重新生成（同高对比必需）"
                      "/ custom geometry or technology: regenerating the whole "
                      "ASTRAN baseline", "warn")

        if not todo:
            self._stage("baseline", "done", "全部已存在 / all baseline cells cached")
            return

        self._stage("baseline", "running",
                    "生成 %d 个基线单元 / generating %d baseline cells"
                    % (len(todo), len(todo)), (0, len(todo)))
        for i, t in enumerate(todo):
            self._check_cancel()
            self._stage("baseline", "running", "基线单元 %s" % t,
                        (i, len(todo)))
            try:
                self._run_astran(t, self.cfg.spice_lib(), base_dir,
                                 label="baseline %s" % t,
                                 technology_path=self.cfg.technology(),
                                 geometry=self.cfg.geometry)
            except Cancelled:
                raise
            except Exception as exc:                    # noqa: BLE001
                self._log("基线单元 %s 失败 / baseline %s failed: %s"
                          % (t, t, exc), "error")
            self._stage("baseline", "running", "已生成 %d/%d" % (i + 1, len(todo)),
                        (i + 1, len(todo)))
        self._stage("baseline", "done", "%d baseline cells" % len(todo))

    # ------------------------------------------------------------ mining loop
    def _mine(self, ctx, clusterSeqs):
        """Port of main.py lines 89-215 (the greedy iteration)."""
        flow, hooks, cfg = ctx["flow"], self.hooks, self.cfg
        out_dir, cells = ctx["out_dir"], ctx["cells"]
        BLIFGraph = ctx["BLIFGraph"]
        dumpedPaterns, detectedPatterns = ctx["dumpedPaterns"], ctx["detectedPatterns"]

        patternNum = len(clusterSeqs)
        bestSaveArea = 0.0
        lastSaveGSCLArea = 0.0
        lastComplexSelection = []
        bench = ctx["bench"]
        total_it = cfg.top_thr

        for i in range(0, cfg.top_thr):
            self._check_cancel()
            if len(clusterSeqs) == 0 or len(clusterSeqs[0].patternClusters) == 0:
                break
            if len(clusterSeqs[0].patternClusters[0].cellIdsContained) >= cfg.max_cells:
                # Pop, don't just continue: re-testing the same oversized
                # head would burn the whole iteration budget doing nothing.
                clusterSeqs = clusterSeqs[1:]
                continue

            self._stage("mine", "running", "第 %d/%d 轮迭代 / iteration %d"
                        % (i + 1, total_it, i + 1), (i, total_it))
            saveArea = 0.0
            saveGSCLArea = 0.0
            complexSelection = []
            # Cells already claimed by a candidate counted this round (see
            # main.py): overlapping clusters are counted once.
            coveredCellIds = set()
            for j in range(0, cfg.top_thr):
                self._check_cancel()
                if j >= len(clusterSeqs):
                    break
                tmpClusterSeq = clusterSeqs[j]
                patternTraceId = tmpClusterSeq.patternClusters[0].clusterTypeId
                patternSubgraph = BLIFGraph.subgraph(
                    tmpClusterSeq.patternClusters[0].cellIdsContained)

                # A pattern's identity is its trace: a later iteration can
                # reproduce the same pattern under a new clusterTypeId. Skipping
                # it keeps the area savings from double-counting it.
                if tmpClusterSeq.patternExtensionTrace in dumpedPaterns:
                    continue
                if len(tmpClusterSeq.patternClusters[0].cellIdsContained) >= cfg.max_cells:
                    continue

                self._log("处理模式 / pattern #%d '%s' ×%d (size=%d)"
                          % (patternTraceId, tmpClusterSeq.patternExtensionTrace,
                             len(tmpClusterSeq.patternClusters),
                             len(tmpClusterSeq.patternClusters[0].cellIdsContained)))

                coverage = (len(tmpClusterSeq.patternClusters[0].cellIdsContained) *
                            len(tmpClusterSeq.patternClusters))
                if coverage < cfg.ratio_thr * len(cells) and \
                        len(tmpClusterSeq.patternClusters) < cfg.cnt_thr:
                    self._log("模式过小被跳过 / pattern too small: coverage=%d << %d"
                              % (coverage, len(cells)), "warn")
                    break
                dumpedPaterns[tmpClusterSeq.patternExtensionTrace] = patternTraceId
                detectedPatterns.append(tmpClusterSeq.patternExtensionTrace)

                flow["BLIFGraphUtil"].drawColorfulFigureForGraphWithAttributes(
                    patternSubgraph,
                    save_to_file=os.path.join(out_dir, "COMPLEX%d.png" % patternTraceId),
                    withLabel=True, figsize=(20, 20))

                flow["spice"].exportSpiceNetlist(
                    tmpClusterSeq, ctx["subckts"], str(patternTraceId), out_dir)

                # Layout + area for this candidate.
                width = None
                if cfg.do_layouts and self.astran_available():
                    width = self._generate_complex_layout(ctx, patternTraceId)
                    if width is None:
                        continue

                if width is not None and width <= 0:
                    continue

                exampleCells = [cells[cid] for cid in
                                tmpClusterSeq.patternClusters[0].cellIdsContained]
                oriUnitAstranArea = flow["BLIFPreProc"].getArea(
                    exampleCells, ctx["stdType2AstranArea"])
                oriUnitGSCLArea = flow["BLIFPreProc"].getArea(
                    exampleCells, ctx["stdType2GSCLArea"])
                newUnitAstranArea = width
                if newUnitAstranArea is None:
                    try:
                        newUnitAstranArea = flow["Astran"].loadAstranArea(
                            out_dir, "COMPLEX%d" % patternTraceId)
                    except Exception:                   # noqa: BLE001
                        continue
                if newUnitAstranArea <= 0:
                    continue
                ctx["shrinkModel"].observe(
                    len(exampleCells), oriUnitAstranArea, newUnitAstranArea)

                # Second metric beside width (P0-4): routing congestion
                # parsed from the cell's own log; reported in the pattern
                # event, enforced only when cfg.max_rt_density is set.
                rt_metrics = flow["routability"].loadCellRoutability(
                    out_dir, "COMPLEX%d" % patternTraceId)
                if rt_metrics is not None:
                    self._log("可布性 / routability COMPLEX%d: %s"
                              % (patternTraceId, rt_metrics.asDict()))
                if (rt_metrics is not None
                        and cfg.max_rt_density is not None
                        and rt_metrics.rtDensity > cfg.max_rt_density):
                    self._log("COMPLEX%d rtDensity %d > gate %d，剔除 / "
                              "excluded by routability gate"
                              % (patternTraceId, rt_metrics.rtDensity,
                                 cfg.max_rt_density), "warn")
                    continue

                elec_metrics = flow["electrical"].patternElectricalMetrics(
                    exampleCells, ctx["cellElectricalMetrics"])
                timing_metrics = flow["timing_power"].patternTimingPower(
                    exampleCells, ctx["cellTimingPower"],
                    ctx["cellElectricalMetrics"])
                # Synthesis-reuse eligibility (AUDIT 5.25): abc only uses
                # single-output simple-function cells; report always, gate
                # when cfg.require_reuse_eligible is set.
                reuse_info = flow["reuse"].reuseEligible(
                    exampleCells, ctx["libFunctions"])
                if (self.cfg.require_reuse_eligible
                        and not reuse_info["eligible"]):
                    self._log("COMPLEX%d 不可综合复用（%s），剔除 / not "
                              "synthesis-reuse eligible, excluded"
                              % (patternTraceId, reuse_info["reason"]),
                              "warn")
                    continue
                proxy_width = None
                if ctx["widthProxy"] is not None:
                    proxy_width = ctx["widthProxy"].predict(
                        len(exampleCells),
                        sum(ctx["transistorCounts"].get(
                            c.stdCellType.typeName, 0)
                            for c in exampleCells),
                        oriUnitAstranArea)

                # Structural layout sanity (P2 phase 0, mirrors main.py).
                cell_name = "COMPLEX%d" % patternTraceId
                sanity = flow["layout_sanity"].checkLayout(
                    os.path.join(out_dir, cell_name + ".gds"),
                    logPath=os.path.join(out_dir, cell_name + ".Astranlog"))
                if not sanity.ok():
                    self._log("版图体检 / layout sanity %s: %s"
                              % (cell_name, sanity.asDict()), "warn")
                if cfg.layout_sanity_gate and not sanity.ok():
                    self._log("COMPLEX%d 版图体检未过，剔除 / failed sanity, "
                              "excluded" % patternTraceId, "warn")
                    continue

                # Liberty fragment for the generated cell (mirrors main.py):
                # area from the layout width, timing/power from the LUT
                # mini-STA sweep; written on change only.
                lib_text, _lib_report = flow["liberty_gen"].generateComplexLiberty(
                    tmpClusterSeq, cell_name, newUnitAstranArea,
                    ctx["cellTimingPower"], ctx["cellElectricalMetrics"],
                    ctx["libFunctions"])
                lib_path = os.path.join(out_dir, cell_name + ".lib")
                if (not os.path.exists(lib_path)
                        or open(lib_path).read() != lib_text):
                    with open(lib_path, "w") as fh:
                        fh.write(lib_text)

                n_clusters = len(tmpClusterSeq.patternClusters)
                counted_clusters = n_clusters
                if oriUnitAstranArea - newUnitAstranArea > 0:
                    counted_clusters = flow["BLIFGraphUtil"].countUncoveredClusters(
                        tmpClusterSeq.patternClusters, coveredCellIds)
                    if counted_clusters == 0:
                        continue
                    complexSelection.append((
                        "COMPLEX%d" % patternTraceId, counted_clusters,
                        len(tmpClusterSeq.patternClusters[0].cellIdsContained),
                        tmpClusterSeq.patternExtensionTrace))
                    saveArea += (oriUnitAstranArea - newUnitAstranArea) * counted_clusters
                    saveGSCLArea += (oriUnitGSCLArea - newUnitAstranArea) * counted_clusters

                hooks.pattern({
                    "name": "COMPLEX%d" % patternTraceId,
                    "id": patternTraceId,
                    "trace": tmpClusterSeq.patternExtensionTrace,
                    "clusters": counted_clusters,
                    "size": len(tmpClusterSeq.patternClusters[0].cellIdsContained),
                    "coverage": coverage,
                    "width_um": newUnitAstranArea,
                    "orig_width_um": oriUnitAstranArea,
                    "save_unit": oriUnitAstranArea - newUnitAstranArea,
                    "save_total": (oriUnitAstranArea - newUnitAstranArea) * counted_clusters,
                    "routability": rt_metrics.asDict() if rt_metrics else None,
                    "electrical": elec_metrics,
                    "timing_power": timing_metrics,
                    "width_proxy_pred": proxy_width,
                    "reuse": reuse_info,
                    "out_dir": out_dir,
                })

            self._check_cancel()
            ratio = saveArea / ctx["astranArea"] * 100 if ctx["astranArea"] else 0.0
            self._log("本轮节省 / saveArea=%.2f (%.2f%%)" % (saveArea, ratio))
            self.hooks.metric({"benchmark": bench, "iteration": i, "save_area": saveArea,
                               "ratio": ratio, "best": bestSaveArea})
            if saveArea > bestSaveArea:
                bestSaveArea = saveArea
                lastSaveGSCLArea = saveGSCLArea
                lastComplexSelection = complexSelection
                self._write_best_record(ctx, bestSaveArea, lastSaveGSCLArea,
                                        lastComplexSelection)
            else:
                break

            # Beam growth (P0-3, mirrors main.py): grow the first
            # cfg.grow_beam heads per round; each grown branch is
            # pre-screened by the benefit estimator so predicted-loss
            # shapes never cost an ASTRAN run.
            grown_heads = 0
            for head_seq in list(clusterSeqs):
                if grown_heads >= cfg.grow_beam:
                    break
                if len(head_seq.patternClusters) == 0:
                    clusterSeqs.remove(head_seq)
                    continue
                head_size = len(head_seq.patternClusters[0].cellIdsContained)
                if grown_heads == 0:
                    assert cfg.ratio_thr > 0
                    if (head_size * len(head_seq.patternClusters) <
                            cfg.ratio_thr * len(cells)
                            and len(head_seq.patternClusters) < cfg.cnt_thr):
                        break
                if head_size >= cfg.max_cells - 1:
                    # a grown max_cells+ candidate is excluded at layout
                    # time anyway; growing it here would only churn the pool
                    clusterSeqs.remove(head_seq)
                    continue
                newSeqOfClusters, patternNum = \
                    flow["BLIFPatternGrowth"].growASeqOfClusters(
                        BLIFGraph, head_seq, ctx["clusterNum"], patternNum,
                        paintPattern=True,
                        benefitEstimator=ctx["growthBenefitEstimator"])
                clusterSeqs.remove(head_seq)
                clusterSeqs += newSeqOfClusters
                grown_heads += 1
                if len(newSeqOfClusters) > 1:
                    # Export under the grown pattern's own id: reusing
                    # len(clusterSeqs) collides with an id already dumped
                    # and overwrites its .sp.
                    flow["spice"].exportSpiceNetlist(
                        newSeqOfClusters[0], ctx["subckts"],
                        newSeqOfClusters[0].patternClusters[0].clusterTypeId,
                        out_dir)

            clusterSeqs = flow["BLIFGraphUtil"].removeEmptySeqsAndDisableClusters(clusterSeqs)
            clusterSeqs = flow["BLIFGraphUtil"].sortPatternClusterSeqs(clusterSeqs)

        ctx["bestSaveArea"] = bestSaveArea
        ctx["runtime"] = time.time() - ctx["startTime"]
        self._stage("mine", "done", "best saveArea=%.2f µm" % bestSaveArea)

    def _generate_complex_layout(self, ctx, patternTraceId):
        """Run ASTRAN for one COMPLEX cell; None means 'exclude this pattern'.

        Mirrors main.py: the stale-layout cache is honoured, a 0-width layout
        counts as a failure, and a pattern whose layout cannot be produced at
        all is dropped instead of failing the benchmark.
        """
        flow, out_dir, cfg = ctx["flow"], ctx["out_dir"], self.cfg
        name = "COMPLEX%d" % patternTraceId
        gds_path = os.path.join(out_dir, name + ".gds")
        sp_path = os.path.join(out_dir, name + ".sp")

        if not cfg.force_regenerate and \
                not flow["Astran"].astranLayoutIsStale(gds_path, sp_path):
            self._log("%s: 复用已缓存版图 / reusing cached layout" % name)
            try:
                width = flow["Astran"].loadAstranArea(out_dir, name)
            except Exception:                            # noqa: BLE001
                return None
            return width if width > 0 else None

        if cfg.max_astran_runs and self._astran_runs >= cfg.max_astran_runs:
            self._log("达到 ASTRAN 运行上限，跳过 %s / run cap reached" % name, "warn")
            return None

        hooks = self.hooks
        try:
            log = self._run_astran(name, sp_path, out_dir, label=name,
                                   technology_path=cfg.technology(),
                                   geometry=cfg.geometry)
        except Cancelled:
            raise
        except Exception as exc:                         # noqa: BLE001
            self._log("%s: 无法生成版图 / layout failed: %s -> excluded"
                      % (name, exc), "error")
            return None
        if not log.complete or not log.width_um or log.width_um <= 0:
            self._log("%s: 宽度为 0（求解失败），排除该模式 / zero width; excluded"
                      % name, "error")
            return None
        return log.width_um

    def _write_best_record(self, ctx, save_astran, save_gscl, selection):
        out_dir, bench = ctx["out_dir"], ctx["bench"]
        astranArea, oriArea = ctx["astranArea"], ctx["oriArea"]
        path = os.path.join(out_dir, "bestRecord-" + bench)
        with open(path, "w") as fh:
            print(save_astran, " <- compared to Astran GDS area", file=fh)
            print(save_astran / astranArea * 100, "% <- compared to Astran GDS area",
                  file=fh)
            print(save_gscl, " <- compared to GSCL GDS area", file=fh)
            print(save_gscl / oriArea * 100, "% <- compared to GSCL GDS area", file=fh)
            print("The generated complex cells are (name, clusterNum, "
                  "cellNumInOneCluster, patternCode):", file=fh)
            for item in selection:
                print(item, file=fh)
            print("\n runtime:", time.time() - ctx["startTime"], " (s)", file=fh)
        self.hooks.record({"benchmark": bench, "path": path, "kind": "best",
                           "save_area": save_astran,
                           "ratio": save_astran / astranArea * 100 if astranArea else 0,
                           "selection": list(selection)})

    # ------------------------------------------------------------- phase 2
    def _phase2(self, ctx):
        """Port of main.py lines 244-387 (per-pattern detail records)."""
        flow, cfg = ctx["flow"], self.cfg
        out_dir, bench = ctx["out_dir"], ctx["bench"]
        dumpedPaterns = ctx["dumpedPaterns"]
        detectedPatterns = list(ctx["detectedPatterns"])
        detectedPatterns.reverse()

        countedSet = set()
        recordPatternDetails = []
        path = os.path.join(out_dir, "bestRecord-seperate" + bench)
        oriArea = ctx["oriArea"]
        astranArea = ctx["astranArea"]

        for idx, targetPatternTrace in enumerate(detectedPatterns):
            self._check_cancel()
            if targetPatternTrace in countedSet:
                continue
            self._stage("phase2", "running",
                        "模式 %d/%d / pattern %d/%d"
                        % (idx + 1, len(detectedPatterns), idx + 1,
                           len(detectedPatterns)),
                        (idx, len(detectedPatterns)))

            (BLIFGraph, cells, netlist, _types) = \
                flow["BLIFPreProc"].genGraphFromLibertyAndBLIF(
                    self._rel(self.cfg.liberty()),
                    self._rel(self._blif_path(bench)))
            clusterSeqs, clusterNum = \
                flow["BLIFPreProc"].heuristicLabelSomeNodesAndGetInitialClusters_BasedOn(
                    BLIFGraph, cells, netlist, targetPatternTrace)

            stdType2AstranArea = flow["GDSIIAnalysis"].loadAstranGDS()
            stdType2GSCLArea = ctx["stdType2GSCLArea"]
            clusterSeqs = flow["BLIFGraphUtil"].sortPatternClusterSeqs(clusterSeqs)
            patternNum = len(clusterSeqs)

            for _i in range(0, 10):
                self._check_cancel()
                if len(clusterSeqs) == 0 or len(clusterSeqs[0].patternClusters) == 0:
                    break
                if len(clusterSeqs[0].patternClusters[0].cellIdsContained) >= cfg.max_cells:
                    # Pop, don't just continue (same fix as the phase-1 loop).
                    clusterSeqs = clusterSeqs[1:]
                    continue

                saveArea = 0.0
                saveGSCLArea = 0.0
                complexSelection = []
                touch = False
                tmpClusterSeq = None
                for j in range(0, 1):
                    if j >= len(clusterSeqs):
                        break
                    tmpClusterSeq = clusterSeqs[j]
                    if tmpClusterSeq.patternExtensionTrace not in dumpedPaterns:
                        break       # grew past the dumped patterns: nothing to record
                    patternTraceId = dumpedPaterns[tmpClusterSeq.patternExtensionTrace]

                    exampleCells = [cells[cid] for cid in
                                    tmpClusterSeq.patternClusters[0].cellIdsContained]
                    complexSelection.append((
                        "COMPLEX%d" % patternTraceId,
                        len(tmpClusterSeq.patternClusters),
                        len(tmpClusterSeq.patternClusters[0].cellIdsContained),
                        tmpClusterSeq.patternExtensionTrace))
                    oriUnitAstranArea = flow["BLIFPreProc"].getArea(
                        exampleCells, stdType2AstranArea)
                    oriUnitGSCLArea = flow["BLIFPreProc"].getArea(
                        exampleCells, stdType2GSCLArea)
                    try:
                        newUnitAstranArea = flow["Astran"].loadAstranArea(
                            out_dir, "COMPLEX%d" % patternTraceId)
                    except Exception:                    # noqa: BLE001
                        self._log("%s 无可用版图，跳过 / no usable layout"
                                  % ("COMPLEX%d" % patternTraceId), "warn")
                        continue
                    if newUnitAstranArea <= 0:
                        self._log("%s 宽度为 0，跳过 / zero width; skipped"
                                  % ("COMPLEX%d" % patternTraceId), "warn")
                        continue
                    n_clusters = len(tmpClusterSeq.patternClusters)
                    saveArea += (oriUnitAstranArea - newUnitAstranArea) * n_clusters
                    saveGSCLArea += (oriUnitGSCLArea - newUnitAstranArea) * n_clusters
                    touch = True

                if tmpClusterSeq is None:
                    break
                if touch and tmpClusterSeq.patternExtensionTrace not in countedSet:
                    countedSet.add(tmpClusterSeq.patternExtensionTrace)
                    recordPatternDetails.append((
                        saveArea, saveArea / astranArea * 100 if astranArea else 0.0,
                        len(tmpClusterSeq.patternClusters),
                        len(tmpClusterSeq.patternClusters[0].cellIdsContained),
                        (len(tmpClusterSeq.patternClusters[0].cellIdsContained) *
                         len(tmpClusterSeq.patternClusters)),
                        "COMPLEX%d" % patternTraceId,
                        tmpClusterSeq.patternExtensionTrace))
                    if targetPatternTrace == complexSelection[0][3]:
                        break

                clusterSeq = clusterSeqs[0]
                if (len(clusterSeq.patternClusters[0].cellIdsContained) *
                        len(clusterSeq.patternClusters) < cfg.ratio_thr * len(cells)
                        and len(clusterSeq.patternClusters) < cfg.cnt_thr):
                    break

                newSeqOfClusters, patternNum = \
                    flow["BLIFPatternGrowth"].growASeqOfClusters_BasedOn(
                        BLIFGraph, clusterSeq, clusterNum, patternNum,
                        paintPattern=True, targetPatternTrace=targetPatternTrace)
                clusterSeqs = clusterSeqs[1:]
                clusterSeqs += newSeqOfClusters
                clusterSeqs = flow["BLIFGraphUtil"].removeEmptySeqsAndDisableClusters(clusterSeqs)
                clusterSeqs = flow["BLIFGraphUtil"].sortPatternClusterSeqs(clusterSeqs)

        recordPatternDetails = sorted(recordPatternDetails, key=lambda x: -x[0])
        with open(path, "w") as fh:
            print("| designOverallArea | saveArea | saveRatio | patternCnt | "
                  "patternSize | patternCoverage | patternName | patternCode |",
                  file=fh)
            for (saveArea, saveRatio, patternCnt, patternSize, patternCoverage,
                 patternName, patternCode) in recordPatternDetails:
                print('|', oriArea, '|', saveArea, '|', saveRatio, '|', patternCnt,
                      '|', patternSize, '|', patternCoverage, '|', patternName,
                      '|', patternCode, '|', file=fh)
        self.hooks.record({"benchmark": bench, "path": path, "kind": "separate",
                           "rows": len(recordPatternDetails)})
        self._stage("phase2", "done", "%d pattern records" % len(recordPatternDetails))


def clean_outputs(benchmark):
    """Remove stale COMPLEX*/bestRecord-* from one benchmark's output dir."""
    out_dir = paths.output_dir(benchmark)
    removed = 0
    for pat in ("COMPLEX*.sp", "COMPLEX*.gds", "COMPLEX*.png",
                "COMPLEX*.Astranlog", "COMPLEX*.run", "COMPLEX*.gds.bak",
                "bestRecord-*"):
        for f in glob.glob(os.path.join(out_dir, pat)):
            try:
                os.remove(f)
                removed += 1
            except OSError:
                pass
    return removed


def regenerate_cell(benchmark, cell, shared_netlist=False, hooks=None,
                    cancel_event=None, geometry=None, technology_path=None,
                    spice_lib=None):
    """Rebuild one cell's layout without re-running the mining pipeline.

    Same job as ``pySrc/regenerate_cells.py``; used by the Layouts tab.  A
    ``.gds`` is moved aside first (``.gds.bak``) so a failed run cannot leave a
    stale layout claiming to be current.  ``geometry``/``technology_path``/
    ``spice_lib`` override the ASTRAN defaults (the Configure tab's PDK
    settings).
    """
    hooks = hooks or Hooks()
    paths.ensure_pysrc_on_path()
    import matplotlib
    matplotlib.use("Agg", force=True)
    import Astran

    out_dir = paths.output_dir(benchmark)
    name = os.path.basename(cell)
    netlist = (spice_lib or paths.SPICE_LIB_FILE if shared_netlist
               else os.path.join(out_dir, name + ".sp"))
    if not os.path.exists(netlist):
        raise FileNotFoundError("no netlist %s" % netlist)

    gds = os.path.join(out_dir, name + ".gds")
    if os.path.exists(gds):
        shutil.move(gds, gds + ".bak")

    script = Astran.buildAstranCommands(
        Astran.GUROBI_CL, technology_path or Astran.ASTRAN_TECHNOLOGY,
        _rel_to_pysrc(netlist), name, _rel_to_pysrc(out_dir),
        geometry=geometry)
    run_path = os.path.join(out_dir, name + ".run")
    with open(run_path, "w") as fh:
        print(script, file=fh)

    log_path = os.path.join(out_dir, name + ".Astranlog")
    hooks.log("重新生成 %s / regenerating %s (netlist=%s)"
              % (name, name, os.path.basename(netlist)), "accent")
    with open(log_path, "w") as log_fh:
        proc = _popen_astran(run_path, log_fh)
        t0 = time.time()
        while proc.poll() is None:
            if cancel_event is not None and cancel_event.is_set():
                FlowRunner._kill(proc)
                raise Cancelled()
            log = artifacts.parse_astran_log(log_path, tail_bytes=400000)
            hooks.cell({"name": name, "label": name, "state": "running",
                        "path": log_path, "attempt": log.attempt_index,
                        "phase": log.last_phase or "starting",
                        "fraction": log.phase_fraction, "width": log.width_um,
                        "elapsed": time.time() - t0})
            time.sleep(0.4)
            log_fh.flush()
    log = artifacts.parse_astran_log(log_path)
    hooks.cell({"name": name, "label": name,
                "state": "done" if log.complete else "failed",
                "path": log_path, "width": log.width_um, "height": log.height_um,
                "log": log, "elapsed": time.time() - t0, "fraction": 1.0})
    return log


def _rel_to_pysrc(p):
    return "./" + os.path.relpath(p, paths.PYSRC_DIR).replace("\\", "/")


def parse_design(benchmark, hooks=None, cancel_event=None, blif_path=None,
                 liberty_file=None):
    """Parse one benchmark's BLIF + liberty into a graph (no clustering).

    Used by the Design tab: it is the cheap part of the pipeline (no ASTRAN,
    no clustering), so it can run on demand even for benchmarks the user has
    not fully mined.  ``blif_path`` lets the caller point at an arbitrary
    user-supplied BLIF; ``liberty_file`` at a custom PDK library; either
    defaults to the repository's standard files.
    Returns the design info dict (also emitted to hooks).
    """
    hooks = hooks or Hooks()
    paths.ensure_pysrc_on_path()
    import matplotlib
    matplotlib.use("Agg", force=True)
    import BLIFPreProc

    blif_abs = blif_path or paths.benchmark_path(benchmark)
    if not os.path.exists(blif_abs):
        raise FileNotFoundError("no such benchmark: %s (%s)" % (benchmark, blif_abs))
    lib_abs = liberty_file or paths.LIBERTY_FILE

    hooks.log("解析设计 / parsing design graph: %s" % benchmark, "accent")
    prev = os.getcwd()
    os.chdir(paths.PYSRC_DIR)
    try:
        BLIFGraph, cells, netlist, stdCellTypesForFeature = \
            BLIFPreProc.genGraphFromLibertyAndBLIF(
                _rel_to_pysrc(lib_abs), _rel_to_pysrc(blif_abs))
    finally:
        os.chdir(prev)

    type_count = {}
    for cell in cells:
        name = cell.stdCellType.typeName
        type_count[name] = type_count.get(name, 0) + 1
    hist = sorted(type_count.items(), key=lambda kv: (-kv[1], kv[0]))

    def _sig(p):
        try:
            return (p, os.path.getmtime(p))
        except OSError:
            return (p, None)

    info = {
        "benchmark": benchmark,
        "graph": BLIFGraph,
        "cells": cells,
        "netlist": netlist,
        "nodes": BLIFGraph.number_of_nodes(),
        "edges": BLIFGraph.number_of_edges(),
        "std_types": len(type_count),
        "type_hist": hist,
        "stop_cells": sum(1 for c in cells if c.stopType),
        "feature_types": stdCellTypesForFeature,
        # Input signature so the Design tab can reuse the cached graph
        # instead of re-parsing when nothing changed.
        "_parse_sig": (_sig(blif_abs), _sig(lib_abs)),
    }
    hooks.design(info)
    hooks.log("设计图完成 / design graph: %d nodes, %d edges, %d types"
              % (info["nodes"], info["edges"], info["std_types"]), "ok")
    # The caller's worker emits finished; parse_design returns the info dict.
    return info
