"""The main window: navigation, pages, worker orchestration, status."""
import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMainWindow, QMessageBox, QStackedWidget,
                               QVBoxLayout, QWidget)

from . import __version__, flow_core, flow_worker, paths, theme
from .state import AppContext, AppState
from .tabs.configure import ConfigureTab
from .tabs.design import DesignTab
from .tabs.layouts import LayoutsTab
from .tabs.overview import OverviewTab
from .tabs.patterns import PatternsTab
from .tabs.pdk import PdkTab
from .tabs.results import ResultsTab
from .tabs.run import RunTab


class MainWindow(QMainWindow):
    PAGES = [
        ("overview", "总览", "Overview", "⌂"),
        ("configure", "配置", "Configure", "⚙"),
        ("run", "运行", "Run", "▶"),
        ("patterns", "模式", "Patterns", "⬡"),
        ("layouts", "版图", "Layouts", "▦"),
        ("results", "结果", "Results", "∑"),
        ("design", "设计", "Design", "⌘"),
        ("pdk", "PDK 编辑", "PDK Editor", "⚒"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AutoCellLibX · 标准单元扩展工作台")
        self.resize(1360, 860)

        self.state = AppState()
        self.ctx = AppContext(self, self.state)
        self._thread = None
        self._worker = None

        self._build_ui()
        self._build_menu()
        self._connect()

        # initial data
        self.overview_tab.refresh()
        self.patterns_tab.reload_benchmarks()
        self.layouts_tab.reload_benchmarks()
        self.results_tab.reload_benchmarks()
        self.show_page("overview")
        self.show_status("就绪 / ready — 选择一个基准并点击『配置』或『运行』开始")

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.nav = QListWidget()
        self.nav.setObjectName("Nav")
        self.nav.setFixedWidth(190)
        self.nav.setSpacing(2)
        for key, name, sub, glyph in self.PAGES:
            item = QListWidgetItem("  %s   %s" % (glyph, name))
            item.setData(Qt.UserRole, key)
            item.setToolTip(sub)
            self.nav.addItem(item)
        self.nav.currentRowChanged.connect(self._nav_changed)
        root.addWidget(self.nav)

        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)

        self.stack = QStackedWidget()
        right_lay.addWidget(self.stack, 1)

        self.overview_tab = OverviewTab(self.ctx)
        self.configure_tab = ConfigureTab(self.ctx)
        self.run_tab = RunTab(self.ctx)
        self.patterns_tab = PatternsTab(self.ctx)
        self.layouts_tab = LayoutsTab(self.ctx)
        self.results_tab = ResultsTab(self.ctx)
        self.design_tab = DesignTab(self.ctx)
        self.pdk_tab = PdkTab(self.ctx)
        self._page_by_key = {
            "overview": self.overview_tab,
            "configure": self.configure_tab,
            "run": self.run_tab,
            "patterns": self.patterns_tab,
            "layouts": self.layouts_tab,
            "results": self.results_tab,
            "design": self.design_tab,
            "pdk": self.pdk_tab,
        }
        for key, _n, _s, _g in self.PAGES:
            self.stack.addWidget(self._page_by_key[key])

        root.addWidget(right, 1)

        # status bar: run state + current benchmark on the right
        self.status_run = QLabel("")
        self.status_bench = QLabel("")
        self.statusBar().addPermanentWidget(self.status_run)
        self.statusBar().addPermanentWidget(QLabel("  "))
        self.statusBar().addPermanentWidget(self.status_bench)
        self._update_status_chrome()

    def _build_menu(self):
        menu = self.menuBar()

        file_m = menu.addMenu("文件 (&F)")
        act = QAction("打开输出目录", self)
        act.triggered.connect(self._open_outputs)
        file_m.addAction(act)
        file_m.addSeparator()
        act = QAction("导出运行日志…", self)
        act.triggered.connect(self.run_tab.log._save)
        file_m.addAction(act)
        file_m.addSeparator()
        act = QAction("退出", self)
        act.setShortcut(QKeySequence.Quit)
        act.triggered.connect(self.close)
        file_m.addAction(act)

        view_m = menu.addMenu("视图 (&V)")
        for i, (key, name, sub, glyph) in enumerate(self.PAGES):
            act = QAction("%s (%s)" % (name, sub), self)
            act.setShortcut("Ctrl+%d" % (i + 1))
            act.triggered.connect(lambda _c=False, k=key: self.show_page(k))
            view_m.addAction(act)
        view_m.addSeparator()
        act = QAction("刷新当前页", self)
        act.setShortcut("F5")
        act.triggered.connect(self.refresh_current)
        view_m.addAction(act)

        tools_m = menu.addMenu("工具 (&T)")
        act = QAction("重建 ASTRAN…", self)
        act.triggered.connect(self._rebuild_astran)
        tools_m.addAction(act)
        act = QAction("清空当前基准的旧产物…", self)
        act.triggered.connect(self._clean_outputs)
        tools_m.addAction(act)

        help_m = menu.addMenu("帮助 (&H)")
        act = QAction("关于 AutoCellLibX", self)
        act.triggered.connect(self._about)
        help_m.addAction(act)

    def _connect(self):
        self.state.benchmarkChanged.connect(lambda _b: self._update_status_chrome())
        self.state.runStateChanged.connect(lambda _r: self._update_status_chrome())

    # ---------------------------------------------------------------- nav
    def _nav_changed(self, row):
        if 0 <= row < len(self.PAGES):
            self.stack.setCurrentIndex(row)

    def show_page(self, key):
        for i, (k, _n, _s, _g) in enumerate(self.PAGES):
            if k == key:
                self.nav.setCurrentRow(i)
                self.stack.setCurrentIndex(i)
                page = self._page_by_key[key]
                if hasattr(page, "refresh"):
                    page.refresh()
                return

    def refresh_current(self):
        key = self.PAGES[self.stack.currentIndex()][0]
        page = self._page_by_key[key]
        if hasattr(page, "refresh"):
            page.refresh()
        self.overview_tab.refresh()

    # ------------------------------------------------------------ run control
    def start_run(self):
        if self.state.running:
            self.show_status("已有任务在运行")
            return
        cfg = self.state.config
        if not cfg.benchmarks:
            self.show_page("configure")
            self.show_status("请先在『配置』中选择至少一个基准")
            return
        self.run_tab.refresh_config_line()
        for bench in cfg.benchmarks:
            self.state.reset_run_caches(bench)
        worker = flow_worker.PipelineWorker(cfg)
        worker.logMessage.connect(self.log)
        worker.stageChanged.connect(self._on_stage)
        worker.designReady.connect(self._on_design)
        worker.patternReady.connect(self._on_pattern)
        worker.cellProgress.connect(self._on_cell)
        worker.metricReady.connect(self._on_metric)
        worker.recordReady.connect(self._on_record)
        worker.finished.connect(self._on_run_finished)
        self._launch(worker, "pipeline")
        self.log("开始运行 / starting run: %s" % cfg.describe(), "accent")

    def stop_run(self):
        if self._worker is not None and hasattr(self._worker, "request_cancel"):
            self._worker.request_cancel()
            self.log("正在停止… / stopping (当前 ASTRAN 单元会被终止)", "warn")
            self.show_status("正在停止…")

    def start_regen(self, cell, shared_netlist=False):
        if self.state.running:
            self.show_status("已有任务在运行，无法重新生成")
            return
        bench = self.state.current_benchmark
        worker = flow_worker.RegenWorker(bench, cell, shared_netlist,
                                         config=self.state.config)
        worker.logMessage.connect(self.log)
        worker.cellProgress.connect(self._on_cell)
        worker.finished.connect(self._on_regen_finished)
        self._launch(worker, "regen")
        self.show_page("run")
        self.log("重新生成 %s / regenerating %s" % (cell, cell), "accent")

    def start_design_parse(self, bench):
        if self.state.running:
            self.show_status("任务运行中，暂不能解析设计")
            self.design_tab.set_busy(False)
            return
        worker = flow_worker.DesignWorker(bench, self.state.blif_path(bench),
                                          self.state.config.liberty())
        worker.logMessage.connect(self.log)
        worker.designReady.connect(self._on_design)
        worker.finished.connect(self._on_design_finished)
        self._launch(worker, "design", track_running=False)

    def _launch(self, worker, kind, track_running=True):
        self._worker = worker
        self._thread = flow_worker.start_worker(worker)
        if track_running:
            self._set_running(True)

    def _set_running(self, running):
        self.state.set_running(running)
        self.run_tab.set_running(running)
        self.configure_tab.set_running(running)

    # ------------------------------------------------------------ worker slots
    def _on_stage(self, key, status, message, progress):
        self.run_tab.on_stage(key, status, message, progress)
        self.overview_tab.set_stage_state(key, status)

    def _on_design(self, info):
        self.state.set_design(info.get("benchmark", ""), info)
        self.design_tab.set_design(info)

    def _on_pattern(self, info):
        bench = info.get("benchmark", self.state.current_benchmark)
        self.patterns_tab.add_live_pattern(bench, info)
        self.log("模式 / pattern %s: 宽 %.2f µm, 单元节省 %.2f µm ×%d"
                 % (info.get("name"), info.get("width_um") or 0,
                    info.get("save_unit") or 0, info.get("clusters") or 0), "info")

    def _on_cell(self, info):
        self.run_tab.on_cell(info)

    def _on_metric(self, info):
        self.run_tab.on_metric(info)

    def _on_record(self, info):
        self.log("写出结果 / wrote %s (%s)" % (info.get("kind"),
                                             os.path.basename(info.get("path", ""))),
                 "ok")
        self.results_tab.add_record(info)

    def _on_run_finished(self, summary):
        self.state.last_summary = summary
        self.run_tab.on_finished(summary)
        self._set_running(False)
        self._refresh_outputs()
        ok = summary.get("ok")
        if summary.get("cancelled"):
            self.show_status("已取消 / cancelled")
        elif ok:
            self.show_status("运行完成 / run finished — 查看『结果』页")
        else:
            self.show_status("运行失败 / run failed — 查看日志")
        self._worker = None

    def _on_regen_finished(self, result):
        self._set_running(False)
        self._refresh_outputs()
        if result.get("ok"):
            self.log("重新生成完成 %s: %.2f µm" % (result.get("cell"),
                                                result.get("width_um") or 0), "ok")
            self.show_status("重新生成完成 %s (%.2f µm)"
                             % (result.get("cell"), result.get("width_um") or 0))
        else:
            self.show_status("重新生成失败 %s" % result.get("cell"))
        self._worker = None

    def _on_design_finished(self, result):
        self.design_tab.set_busy(False)

    def _refresh_outputs(self):
        self.overview_tab.refresh()
        self.patterns_tab.reload_benchmarks()
        self.layouts_tab.reload_benchmarks()
        self.results_tab.reload_benchmarks()

    # ------------------------------------------------------------ misc
    def log(self, message, level="info"):
        self.run_tab.append_log(str(message), level)
        if level in ("error", "warn"):
            self.show_status(str(message).splitlines()[0][:160])

    def show_status(self, message):
        self.statusBar().showMessage(message, 8000)

    def _update_status_chrome(self):
        bench = self.state.current_benchmark or "—"
        self.status_bench.setText("基准: %s" % bench)
        running = self.state.running
        self.status_run.setText("● 运行中" if running else "○ 空闲")
        self.status_run.setStyleSheet("color:%s; font-weight:600;"
                                      % (theme.RUN if running else theme.TEXT_DIM))

    def _open_outputs(self):
        out = self.state.output_dir()
        if os.path.isdir(out):
            if os.name == "nt":
                os.startfile(out)
        else:
            self.show_status("该基准尚无输出目录")

    def _rebuild_astran(self):
        self.show_status("重建 ASTRAN：请在终端运行 bash tools/astran/build_astran.sh")
        QMessageBox.information(
            self, "重建 ASTRAN",
            "在仓库根目录的终端里执行：\n\n"
            "    bash tools/astran/build_astran.sh\n\n"
            "构建产物为 tools/astran/build/bin/Astran.exe。\n"
            "（此操作需在 MSYS2 环境下进行，GUI 不代为执行长时间编译。）")

    def _clean_outputs(self):
        bench = self.state.current_benchmark
        reply = QMessageBox.question(
            self, "清空旧产物",
            "将删除 outputs/%s/ 下的 COMPLEX*.{sp,gds,png,Astranlog,run} 与 "
            "bestRecord-*。\n\n这会清掉该基准的全部已生成版图，且不可撤销。继续？"
            % bench)
        if reply == QMessageBox.Yes:
            n = flow_core.clean_outputs(bench)
            self.log("已清空 %s 的 %d 个旧产物文件" % (bench, n), "warn")
            self._refresh_outputs()

    def _about(self):
        QMessageBox.about(
            self, "AutoCellLibX",
            "AutoCellLibX 标准单元扩展工作台 v%s\n\n"
            "从门级网表挖掘频繁子电路，合并为复杂单元，并用 ASTRAN 做晶体管级版图，\n"
            "以缩减设计面积。\n\n"
            "面积以『宽度』为代理（行高固定）；所有文件契约与命令行 main.py 一致。"
            % __version__)

    # ------------------------------------------------------------------ close
    def closeEvent(self, event):
        if self.state.running:
            reply = QMessageBox.question(
                self, "退出",
                "任务仍在运行。退出会终止当前 ASTRAN 单元。确定退出？")
            if reply == QMessageBox.Yes:
                self.stop_run()
                QTimer.singleShot(300, QTimer(self), timeout=self.close)
                event.ignore()
                return
            event.ignore()
            return
        event.accept()
