"""Shared application state: the config, the selection, the in-session caches.

The tabs never talk to each other directly; they read/write this object and
react to its signals.  That keeps "the run just produced a pattern" and "the
user switched benchmark" from needing per-tab plumbing.
"""
import os

from PySide6.QtCore import QObject, Signal

from . import artifacts, flow_core, paths


class AppState(QObject):
    benchmarkChanged = Signal(str)       # the benchmark the viewer is looking at
    configChanged = Signal()             # Configure tab edited FlowConfig
    runStateChanged = Signal(bool)       # True while a pipeline/regen runs
    outputsChanged = Signal(str)         # a benchmark's on-disk outputs changed
    designChanged = Signal(str)          # a benchmark's graph got parsed

    def __init__(self):
        super().__init__()
        self.config = flow_core.FlowConfig()
        self.benchmarks = [name for name, _size, _p in paths.list_benchmarks()]
        self.current_benchmark = self._default_benchmark()
        self.running = False

        # Session-only views of things the flow reports: the Patterns tab
        # shows live candidates as they are evaluated, the Results tab the
        # running save_area, the Design tab the parsed graph.
        self.patterns = {}               # bench -> [pattern dict] (from the run)
        self.metrics = {}                # bench -> [metric dict]
        self.designs = {}                # bench -> dict(graph, stats, hist)
        self.last_summary = None

    # ----------------------------------------------------------- selection
    def _default_benchmark(self):
        existing = artifacts.list_output_benchmarks(paths.OUTPUTS_DIR)
        for b in ("adder", "ctrl", "router"):
            if b in self.benchmarks:
                return b
        return self.benchmarks[0] if self.benchmarks else ""

    def set_benchmark(self, name):
        if name and name != self.current_benchmark:
            self.current_benchmark = name
            self.benchmarkChanged.emit(name)

    def set_running(self, running):
        if running != self.running:
            self.running = running
            self.runStateChanged.emit(running)

    # -------------------------------------------------------------- caches
    def add_pattern(self, bench, info):
        self.patterns.setdefault(bench, []).append(info)
        self.outputsChanged.emit(bench)

    def add_metric(self, bench, info):
        self.metrics.setdefault(bench, []).append(info)

    def set_design(self, bench, info):
        self.designs[bench] = info
        self.designChanged.emit(bench)

    def reset_run_caches(self, bench):
        self.patterns[bench] = []
        self.metrics[bench] = []

    def mark_outputs_changed(self, bench):
        self.outputsChanged.emit(bench)

    # ------------------------------------------------------------ shortcuts
    def output_dir(self, bench=None):
        return paths.output_dir(bench or self.current_benchmark)

    def blif_path(self, name):
        """Absolute path of a benchmark's BLIF (custom file shadows the standard)."""
        return self.config.custom_blifs.get(name) or paths.benchmark_path(name)

    def blif_sources(self):
        """(name, path, is_custom) for every selectable input, sorted."""
        out = []
        for name, _size, p in paths.list_benchmarks():
            out.append((name, p, False))
        for name, p in sorted(self.config.custom_blifs.items()):
            hit = next((i for i, (n, _p, c) in enumerate(out)
                        if n == name and not c), None)
            if hit is not None:
                out[hit] = (name, p, True)     # custom shadows the standard
            else:
                out.append((name, p, True))
        return out

    def scan_cells(self, bench=None):
        return artifacts.scan_output_dir(self.output_dir(bench))

    def best_record(self, bench=None):
        return artifacts.read_best_record(
            os.path.join(self.output_dir(bench), "bestRecord-" +
                         (bench or self.current_benchmark)))

    def separate_record(self, bench=None):
        return artifacts.read_separate_record(
            os.path.join(self.output_dir(bench), "bestRecord-seperate" +
                         (bench or self.current_benchmark)))


class AppContext(object):
    """A light handle tabs use to reach the window and the shared state."""

    def __init__(self, window, state):
        self.window = window
        self.state = state

    # --- run control (owned by the window) ---
    def start_run(self):
        self.window.start_run()

    def stop_run(self):
        self.window.stop_run()

    def start_regen(self, cell, shared_netlist=False):
        self.window.start_regen(cell, shared_netlist)

    def start_design_parse(self, bench):
        self.window.start_design_parse(bench)

    def log(self, message, level="info"):
        self.window.log(message, level)

    def status(self, message):
        self.window.show_status(message)

    def show_page(self, key):
        self.window.show_page(key)
