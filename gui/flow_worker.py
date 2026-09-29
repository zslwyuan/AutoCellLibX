"""Qt bridge: run flow_core on a worker thread and re-emit callbacks as signals.

``FlowRunner`` is pure Python with a callback object; this module supplies a
``Hooks`` implementation that turns each callback into a Qt signal.  Signals
cross the thread boundary with a queued connection, which is why the callbacks
must hand over plain data (dicts) plus, for the live log view, the parsed
AstranLog object (emitted as ``object``).
"""
import threading
import traceback

from PySide6.QtCore import QObject, Signal, Slot

from . import flow_core


class _SignalHooks(flow_core.Hooks):
    def __init__(self, worker):
        self._w = worker

    def log(self, message, level="info"):
        self._w.logMessage.emit(str(message), level)

    def stage(self, key, status, message="", progress=None):
        self._w.stageChanged.emit(key, status, message, progress)

    def design(self, info):
        self._w.designReady.emit(info)

    def pattern(self, info):
        self._w.patternReady.emit(info)

    def cell(self, info):
        self._w.cellProgress.emit(info)

    def metric(self, info):
        self._w.metricReady.emit(info)

    def record(self, info):
        self._w.recordReady.emit(info)

    def finished(self, summary):
        # FlowRunner.run() reports completion only through this callback, so it
        # must be the one that fires the worker's finished signal.  (parse_design
        # and regenerate_cell return their result instead; their workers emit
        # finished themselves.)
        self._w.finished.emit(summary)


class PipelineWorker(QObject):
    """Owns one FlowRunner execution."""

    logMessage = Signal(str, str)             # message, level
    stageChanged = Signal(str, str, str, object)   # key, status, message, progress
    designReady = Signal(dict)
    patternReady = Signal(dict)
    cellProgress = Signal(dict)
    metricReady = Signal(dict)
    recordReady = Signal(dict)
    finished = Signal(dict)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.cancel_event = threading.Event()

    @Slot()
    def request_cancel(self):
        self.cancel_event.set()

    @Slot()
    def run(self):
        try:
            runner = flow_core.FlowRunner(self.config, _SignalHooks(self),
                                          self.cancel_event)
            runner.run()
        except Exception:                          # noqa: BLE001
            self.logMessage.emit(traceback.format_exc(), "error")
            self.finished.emit({"ok": False, "error": "worker crashed"})


class DesignWorker(QObject):
    """Parse a design's graph on demand (the cheap front part of the flow)."""

    logMessage = Signal(str, str)
    designReady = Signal(object)          # design info dict (holds the graph)
    finished = Signal(dict)

    def __init__(self, benchmark, blif_path=None, liberty_file=None):
        super().__init__()
        self.benchmark = benchmark
        self.blif_path = blif_path        # custom BLIF, or None for the standard dir
        self.liberty_file = liberty_file  # custom PDK .lib, or None for GSCL45
        self.cancel_event = threading.Event()

    @Slot()
    def request_cancel(self):
        self.cancel_event.set()

    @Slot()
    def run(self):
        result = {"ok": False, "benchmark": self.benchmark}
        try:
            info = flow_core.parse_design(self.benchmark, _SignalHooks(self),
                                          self.cancel_event,
                                          blif_path=self.blif_path,
                                          liberty_file=self.liberty_file)
            result = {"ok": True, "benchmark": self.benchmark,
                      "nodes": info["nodes"], "edges": info["edges"]}
        except Exception:                      # noqa: BLE001
            self.logMessage.emit(traceback.format_exc(), "error")
            result["error"] = "parse failed"
        self.finished.emit(result)


class RegenWorker(QObject):
    """Rebuild one cell's layout (the CLI's regenerate_cells.py, in a thread)."""

    logMessage = Signal(str, str)
    cellProgress = Signal(dict)
    finished = Signal(dict)

    def __init__(self, benchmark, cell, shared_netlist=False, config=None):
        super().__init__()
        self.benchmark = benchmark
        self.cell = cell
        self.shared_netlist = shared_netlist
        self.config = config or flow_core.FlowConfig()
        self.cancel_event = threading.Event()

    @Slot()
    def request_cancel(self):
        self.cancel_event.set()

    @Slot()
    def run(self):
        result = {"ok": False}
        try:
            cfg = self.config
            log = flow_core.regenerate_cell(
                self.benchmark, self.cell, self.shared_netlist,
                hooks=_SignalHooks(self), cancel_event=self.cancel_event,
                geometry=cfg.geometry, technology_path=cfg.technology(),
                spice_lib=cfg.spice_lib())
            result = {"ok": bool(log.complete and (log.width_um or 0) > 0),
                      "cell": self.cell, "width_um": log.width_um,
                      "height_um": log.height_um, "log": log}
        except flow_core.Cancelled:
            self.logMessage.emit("已取消 / cancelled", "warn")
            result = {"ok": False, "cancelled": True, "cell": self.cell}
        except flow_core.AstranLaunchError as exc:
            self.logMessage.emit(str(exc), "error")
            result = {"ok": False, "cell": self.cell, "error": str(exc)}
        except Exception as exc:                   # noqa: BLE001
            self.logMessage.emit(traceback.format_exc(), "error")
            result = {"ok": False, "cell": self.cell, "error": str(exc)}
        self.finished.emit(result)


def start_worker(worker, on_finished=None):
    """Move ``worker`` to a fresh QThread, connect and start it.

    Returns the QThread.  The thread is started with ``started -> worker.run``
    so the worker's own slots live in the worker thread.
    """
    from PySide6.QtCore import QThread

    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)

    def _cleanup(*_args):
        thread.quit()
        thread.wait(5000)

    worker.finished.connect(_cleanup)
    if on_finished is not None:
        worker.finished.connect(on_finished)
    # Keep a reference alive on the thread object so neither is GC'd mid-run.
    thread._worker = worker
    thread.start()
    return thread
