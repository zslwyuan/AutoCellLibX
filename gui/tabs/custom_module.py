"""Custom-module tab: ad-hoc Verilog -> merged complex cells (verilog2cells).

Wraps the Qt-free flow/verilog2cells.py driver in a worker thread: pick a
Verilog module, tune the partition/jobs options, run, watch the log, then
inspect each produced block's layout in the shared GDS canvas.  The tab
owns its worker (independent of the mining pipeline's), but refuses to
start while the main flow is running -- the main flow still shares one
LP working directory per process, and an ASTRAN run from this tab would
clobber it (the queue's per-cell cwd only protects queue clients).
"""
import os
import sys

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSpinBox, QSplitter, QTextBrowser,
                               QVBoxLayout, QWidget)

from ..widgets.common import Card
from ..widgets.gds_canvas import GdsCanvas, LayerPanel
from ..widgets.guide import GuidePanel
from ..widgets.log_view import LogView

_REPO = os.path.normpath(os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "..", ".."))
_FLOW = os.path.join(_REPO, "flow")


class _V2CWorker(QThread):
    logLine = Signal(str, str)
    finishedOk = Signal(int)
    failed = Signal(str)

    def __init__(self, argv, parent=None):
        super().__init__(parent)
        self._argv = argv

    def run(self):
        sys.path.insert(0, _FLOW)
        import verilog2cells

        def note(msg):
            level = ("warn" if "skipped" in msg.lower() else "info")
            self.logLine.emit(msg, level)

        try:
            rc = verilog2cells.main(
                self._argv, on_note=note,
                should_cancel=self.isInterruptionRequested)
        except Exception as exc:                       # noqa: BLE001
            from astran_queue import CancelledError
            if isinstance(exc, (CancelledError, SystemExit)):
                self.logLine.emit("已取消 / cancelled", "warn")
                self.finishedOk.emit(2)
                return
            self.failed.emit(str(exc))
            return
        self.finishedOk.emit(rc or 0)


class CustomModuleTab(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._worker = None
        self._blocks = []

        root = QVBoxLayout(self)
        root.addWidget(GuidePanel([
            ("选择 Verilog", "任意组合模块 .v 文件；综合用内置 yosys+abc 映射到 GSCL45"),
            ("配置并运行", "划分预算默认 36T（已验证区间）；--jobs 并行安全（独立 LP 目录）"),
            ("查看结果", "左侧报告、右侧版图；勾选 liberty-closure 可得 abc 重映射的设计级收益"),
        ], title="自定义模块 → 自定义 cell / Custom module flow"))

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, 1)

        # ------------------------------------------------ left: form + log
        left = QWidget()
        left_lay = QVBoxLayout(left)
        form_card = Card("输入与选项 / Input && options")
        form = QFormLayout()

        self.verilog_edit = QLineEdit()
        vbtn = QPushButton("浏览…")
        vbtn.clicked.connect(self._pick_verilog)
        vrow = QHBoxLayout()
        vrow.addWidget(self.verilog_edit, 1)
        vrow.addWidget(vbtn)
        form.addRow("Verilog 文件", vrow)

        self.out_edit = QLineEdit()
        obtn = QPushButton("浏览…")
        obtn.clicked.connect(self._pick_out)
        orow = QHBoxLayout()
        orow.addWidget(self.out_edit, 1)
        orow.addWidget(obtn)
        form.addRow("输出目录", orow)

        self.top_edit = QLineEdit()
        self.top_edit.setPlaceholderText("留空 = auto-top")
        form.addRow("顶层模块", self.top_edit)

        self.jobs_spin = QSpinBox()
        self.jobs_spin.setRange(1, 8)
        self.jobs_spin.setValue(2)
        form.addRow("并行 jobs", self.jobs_spin)

        self.maxt_spin = QSpinBox()
        self.maxt_spin.setRange(8, 200)
        self.maxt_spin.setValue(36)
        form.addRow("单块晶体管预算", self.maxt_spin)

        self.chk_resume = QCheckBox("resume（复用未变网表的版图）")
        self.chk_resume.setChecked(True)
        self.chk_skip_verify = QCheckBox("跳过等价验证")
        self.chk_no_png = QCheckBox("不渲染 PNG")
        self.chk_psearch = QCheckBox("划分搜索（宽度代理预筛）")
        self.chk_closure = QCheckBox("liberty 闭环（abc 重映射验证）")
        for chk in (self.chk_resume, self.chk_skip_verify, self.chk_no_png,
                    self.chk_psearch, self.chk_closure):
            form.addRow(chk)

        btn_row = QHBoxLayout()
        self.run_btn = QPushButton("运行 / Run")
        self.run_btn.setObjectName("Primary")
        self.run_btn.clicked.connect(self._run)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        btn_row.addWidget(self.run_btn)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addStretch(1)
        form.addRow(btn_row)
        form_card.body.addLayout(form)
        left_lay.addWidget(form_card)

        self.log = LogView()
        left_lay.addWidget(self.log, 1)
        splitter.addWidget(left)

        # ------------------------------------------- right: report + gds
        right = QWidget()
        right_lay = QVBoxLayout(right)
        self.report = QTextBrowser()
        self.report.setOpenExternalLinks(False)
        right_lay.addWidget(self.report, 1)

        self.block_row = QHBoxLayout()
        self.block_row.addWidget(QLabel("版图 / Layout:"))
        self.block_combo = QComboBox()
        self.block_combo.currentTextChanged.connect(self._show_block)
        self.block_row.addWidget(self.block_combo, 1)
        right_lay.addLayout(self.block_row)

        self.canvas = GdsCanvas()
        right_lay.addWidget(self.canvas, 2)
        self.layer_panel = LayerPanel()
        right_lay.addWidget(self.layer_panel)
        splitter.addWidget(right)
        splitter.setSizes([520, 760])

    # ------------------------------------------------------------- helpers
    def _pick_verilog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Verilog 文件", "", "Verilog (*.v *.sv)")
        if path:
            self.verilog_edit.setText(path)
            if not self.out_edit.text():
                stem = os.path.splitext(os.path.basename(path))[0]
                self.out_edit.setText(os.path.join(
                    os.path.dirname(path), stem + "_cells"))

    def _pick_out(self):
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if path:
            self.out_edit.setText(path)

    def _argv(self):
        argv = [self.verilog_edit.text(),
                "--out", self.out_edit.text(),
                "--jobs", str(self.jobs_spin.value()),
                "--max-transistors", str(self.maxt_spin.value())]
        if self.top_edit.text().strip():
            argv += ["--top", self.top_edit.text().strip()]
        if self.chk_resume.isChecked():
            argv.append("--resume")
        if self.chk_skip_verify.isChecked():
            argv.append("--skip-verify")
        if self.chk_no_png.isChecked():
            argv.append("--no-png")
        if self.chk_psearch.isChecked():
            argv.append("--partition-search")
        if self.chk_closure.isChecked():
            argv.append("--liberty-closure")
        return argv

    # ---------------------------------------------------------------- run
    def _run(self):
        if self._worker is not None:
            self.ctx.log("自定义模块任务已在运行", "warn")
            return
        if getattr(self.ctx.state, "running", False):
            self.ctx.log("主流程运行中——自定义模块页签此时禁用"
                         "（主流程仍共享 LP 工作目录）", "error")
            return
        if not os.path.isfile(self.verilog_edit.text()):
            self.ctx.log("请选择存在的 Verilog 文件", "error")
            return
        self.report.clear()
        self.block_combo.clear()
        self.canvas.set_layout(None)
        self.log.clear()
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)

        self._worker = _V2CWorker(self._argv(), self)
        self._worker.logLine.connect(self.log.append)
        self._worker.finishedOk.connect(self._done)
        self._worker.failed.connect(self._failed)
        self._worker.finished.connect(self._teardown)
        self._worker.start()

    def _cancel(self):
        if self._worker is not None:
            self._worker.requestInterruption()
            self.log.append("请求取消：等待当前阶段/cell 收尾…", "warn")

    def _done(self, rc):
        if rc == 0:
            self.log.append("完成 / done", "ok")
            self._load_results()

    def _failed(self, message):
        self.log.append("失败 / failed: %s" % message, "error")

    def _teardown(self):
        self._worker.deleteLater()
        self._worker = None
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    # ------------------------------------------------------------ results
    def _load_results(self):
        out = self.out_edit.text()
        report_path = os.path.join(out, "report.md")
        if os.path.exists(report_path):
            text = open(report_path, encoding="utf-8").read()
            self.report.setMarkdown(text)
        self._blocks = sorted(
            os.path.splitext(f)[0] for f in os.listdir(out)
            if f.endswith(".gds") and not f.endswith(".bak"))
        self.block_combo.addItems(self._blocks)
        if self._blocks:
            self._show_block(self._blocks[0])

    def _show_block(self, name):
        if not name:
            return
        out = self.out_edit.text()
        gds = os.path.join(out, name + ".gds")
        log = os.path.join(out, name + ".Astranlog")
        if not os.path.exists(gds):
            return
        try:
            from .. import gds_model
            model = gds_model.load_layout(gds, log_path=log)
        except Exception as exc:                        # noqa: BLE001
            self.log.append("读取 %s 版图失败: %s" % (name, exc), "error")
            return
        self.canvas.set_layout(model)
        self.layer_panel.set_model(model)
