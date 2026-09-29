"""Run tab: stage-by-stage progress, the live ASTRAN cell panel, and the log."""
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QProgressBar,
                               QPushButton, QScrollArea, QSplitter, QVBoxLayout,
                               QWidget)

from .. import flow_core, theme
from ..widgets.common import (Card, KeyValue, StatTile, StatusDot, badge, faint,
                              h1, h2)
from ..widgets.guide import GuidePanel
from ..widgets.log_view import LogView


class StageRow(QWidget):
    def __init__(self, key, label, parent=None):
        super().__init__(parent)
        self.key = key
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 3, 2, 3)
        lay.setSpacing(3)
        top = QHBoxLayout()
        self.dot = StatusDot("", "pending")
        self.dot.label.setStyleSheet("font-weight:600; color:%s;" % theme.TEXT)
        top.addWidget(self.dot, 1)
        self.progress = QProgressBar()
        self.progress.setObjectName("Stage")
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedWidth(86)
        self.progress.hide()
        top.addWidget(self.progress)
        lay.addLayout(top)
        self.msg = QLabel("")
        self.msg.setObjectName("Faint")
        self.msg.setWordWrap(True)
        self.msg.setIndent(17)
        lay.addWidget(self.msg)
        self._label = label
        self.set_state("pending")

    def set_state(self, status, message="", progress=None):
        self.dot.set_state(status)
        short = self._label.split(" ", 1)[0]
        english = self._label.split(" ", 1)[1] if " " in self._label else ""
        self.dot.setText("%s  %s" % (short, english))
        if message:
            self.msg.setText(message)
        if progress and progress[1]:
            self.progress.show()
            self.progress.setValue(int(100 * progress[0] / max(1, progress[1])))
        elif status == "running":
            self.progress.setRange(0, 0)     # indeterminate
            self.progress.show()
        else:
            self.progress.hide()


class RunTab(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._start_time = None
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._cell_running = False

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        # --- control bar ---
        bar = QHBoxLayout()
        bar.addWidget(h1("运行 / Run"))
        bar.addStretch(1)
        self.elapsed = QLabel("00:00")
        self.elapsed.setStyleSheet("font-size:16px; font-weight:600;")
        bar.addWidget(self.elapsed)
        self.stop_btn = QPushButton("■ 停止")
        self.stop_btn.setObjectName("Danger")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.ctx.stop_run)
        bar.addWidget(self.stop_btn)
        self.start_btn = QPushButton("▶ 开始运行")
        self.start_btn.setObjectName("Primary")
        self.start_btn.clicked.connect(self.ctx.start_run)
        bar.addWidget(self.start_btn)
        root.addLayout(bar)

        self.guide = GuidePanel([
            ("启动", "点「▶ 开始运行」；「■ 停止」随时取消（正在跑的 ASTRAN 单元会被终止）。"),
            ("读进度", "左侧「流水线进度」逐个阶段点亮；带进度条的阶段正在计数"
             "（如基线单元 3/12）。"),
            ("读单元", "「当前单元」显示 ASTRAN 正在处理的单元：阶段（折叠→布局→布线→压缩）、"
             "LP 规模、求解状态、宽度；每个单元约 5–10 分钟。"),
            ("看日志", "右侧日志分级着色：✖错误 / ▲警告 / ✔完成 / ▸阶段；可勾选级别过滤、"
             "搜索、导出。"),
            ("收尾", "结束后「运行结果」卡片给出节省与用时；去「结果」「模式」「版图」页看细节。"),
            ("排障", "若报「无法启动 ASTRAN 二进制」：360 误报隔离了 Astran.exe，"
             "按提示加入信任区并重建。"),
        ])
        root.addWidget(self.guide)

        self.config_line = faint("")
        root.addWidget(self.config_line)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)   # sides cannot be squashed flat
        root.addWidget(splitter, 1)

        # --- left: stages + current cell ---
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(10)

        stages_card = Card("流水线进度 / Pipeline progress")
        self._stage_rows = {}
        for key, label in flow_core.STAGES:
            row = StageRow(key, label)
            self._stage_rows[key] = row
            stages_card.add(row)
        stages_card.add_widget = None
        left_lay.addWidget(stages_card)

        self.cell_card = Card("当前单元 / Current cell")
        self.cell_head = QHBoxLayout()
        self.cell_name = QLabel("—")
        self.cell_name.setStyleSheet("font-size:15px; font-weight:600;")
        self.cell_head.addWidget(self.cell_name)
        self.cell_badge = badge("idle", theme.TEXT_DIM)
        self.cell_head.addStretch(1)
        self.cell_head.addWidget(self.cell_badge)
        self.cell_card.add_layout(self.cell_head)

        self.cell_phase = QProgressBar()
        self.cell_phase.setRange(0, 100)
        self.cell_phase.setValue(0)
        self.cell_phase.setFormat("—")
        self.cell_card.add(self.cell_phase)

        self.cell_info = KeyValue()
        self.cell_card.add(self.cell_info)
        left_lay.addWidget(self.cell_card)

        self.summary_card = Card("运行结果 / Outcome")
        self.summary_tiles = QVBoxLayout()
        self.summary_card.add_layout(self.summary_tiles)
        self.summary_card.hide()
        left_lay.addWidget(self.summary_card)
        left_lay.addStretch(1)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QScrollArea.NoFrame)
        left_scroll.setWidget(left)
        left_scroll.setMinimumWidth(330)
        left_scroll.setMaximumWidth(390)
        splitter.addWidget(left_scroll)

        # --- right: log ---
        self.log = LogView()
        splitter.addWidget(self.log)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        self.refresh_config_line()

    # ------------------------------------------------------------------ api
    def refresh_config_line(self):
        cfg = self.ctx.state.config
        self.config_line.setText("配置：%s" % cfg.describe())

    def set_running(self, running):
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        if running:
            self._start_time = time.time()
            self._timer.start()
            self.summary_card.hide()
            for row in self._stage_rows.values():
                row.set_state("pending", "")
            self._set_cell_idle()
        else:
            self._timer.stop()
            if not self._cell_running:
                self._set_cell_idle()

    def append_log(self, message, level):
        self.log.append(message, level)

    # ------------------------------------------------------------- signals
    def on_stage(self, key, status, message, progress):
        row = self._stage_rows.get(key)
        if row is not None:
            row.set_state(status, message, progress)

    def on_cell(self, info):
        state = info.get("state")
        self.cell_name.setText(info.get("label", info.get("name", "—")))
        if state == "start":
            self._cell_running = True
            self.cell_badge.setText("running")
            self.cell_badge.setStyleSheet("color:%s; border-color:%s;"
                                          % (theme.RUN, theme.RUN))
            self.cell_phase.setFormat("启动 / launching")
            self.cell_phase.setValue(0)
            self.cell_info.clear()
        elif state == "running":
            self._cell_running = True
            self.cell_badge.setText("running")
            self.cell_badge.setStyleSheet("color:%s; border-color:%s;"
                                          % (theme.RUN, theme.RUN))
            phase = info.get("phase", "")
            frac = info.get("fraction", 0.0)
            self.cell_phase.setValue(int(frac * 100))
            attempt = info.get("attempt")
            tracks = info.get("tracks")
            cons = info.get("conservative")
            suffix = ""
            if tracks is not None:
                suffix = " · 轨道 %d / cons %d" % (tracks, cons)
            if attempt is not None and attempt > 0:
                suffix = " · 第%d次尝试" % (attempt + 1) + suffix
            self.cell_phase.setFormat("%s %d%%%s" % (phase, int(frac * 100), suffix))
            self._fill_cell_info(info)
        else:  # done / failed
            self._cell_running = False
            ok = state == "done"
            self.cell_badge.setText("done" if ok else "failed")
            colour = theme.OK if ok else theme.ERROR
            self.cell_badge.setStyleSheet("color:%s; border-color:%s;" % (colour, colour))
            width = info.get("width")
            height = info.get("height")
            self.cell_phase.setFormat("完成 %.2f × %.2f µm" % (width, height)
                                      if ok and width else "失败 / failed")
            self.cell_phase.setValue(100 if ok else 0)
            self._fill_cell_info(info, final=True)

    def on_metric(self, info):
        self.ctx.state.add_metric(info.get("benchmark", ""), info)

    def on_finished(self, summary):
        self.set_running(False)
        self._show_summary(summary)

    # ------------------------------------------------------------- internals
    def _set_cell_idle(self):
        self.cell_name.setText("—")
        self.cell_badge.setText("idle")
        self.cell_badge.setStyleSheet("color:%s; border-color:%s;"
                                      % (theme.TEXT_DIM, theme.TEXT_DIM))
        self.cell_phase.setValue(0)
        self.cell_phase.setFormat("—")
        self.cell_info.clear()

    def _fill_cell_info(self, info, final=False):
        self.cell_info.clear()
        phase = info.get("phase")
        if phase:
            self.cell_info.add("阶段", phase)
        if info.get("ntrans"):
            self.cell_info.add("晶体管", info["ntrans"])
        if info.get("solver_vars"):
            self.cell_info.add("LP 规模", "%s 变量 / %s 约束"
                               % (info["solver_vars"], info["solver_cons"]))
        if info.get("status"):
            self.cell_info.add("求解状态", info["status"])
        if info.get("width"):
            h = info.get("height")
            self.cell_info.add("宽度", "%.2f%s" % (info["width"],
                                                  " µm × %.2f µm" % h if h else " µm"),
                               theme.OK)
        if info.get("option3_retries"):
            self.cell_info.add("option-3 重试", info["option3_retries"])
        if info.get("repairs") is not None:
            self.cell_info.add("间距修复", "%s 处违规" % info["repairs"],
                               theme.OK if info["repairs"] == 0 else theme.WARN)
        if info.get("elapsed"):
            self.cell_info.add("用时", "%.1f s" % info["elapsed"])

    def _tick(self):
        if self._start_time is not None:
            sec = int(time.time() - self._start_time)
            self.elapsed.setText("%02d:%02d:%02d" % (sec // 3600, (sec % 3600) // 60,
                                                     sec % 60))

    def _show_summary(self, summary):
        self.summary_card.show()
        while self.summary_tiles.count():
            item = self.summary_tiles.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        ok = summary.get("ok")
        if summary.get("cancelled"):
            self.summary_tiles.addWidget(StatTile("状态", "已取消", ""))
        elif ok:
            self.summary_tiles.addWidget(StatTile("状态", "成功", ""))
        else:
            self.summary_tiles.addWidget(StatTile("状态", "失败", ""))
            err = QLabel(str(summary.get("error", "")))
            err.setObjectName("Faint")
            err.setWordWrap(True)
            self.summary_tiles.addWidget(err)
        best = self.ctx.state.best_record(self.ctx.state.current_benchmark)
        if best.exists and best.save_ratio_astran is not None:
            row = QHBoxLayout()
            row.addWidget(StatTile("节省 (ASTRAN)", "%.1f µm" % best.save_area_astran,
                                   "%.2f%%" % best.save_ratio_astran))
            row.addWidget(StatTile("节省 (GSCL)", "%.1f µm" % best.save_area_gscl,
                                   "%.2f%%" % best.save_ratio_gscl))
            self.summary_tiles.addLayout(row)
        if summary.get("elapsed"):
            self.summary_tiles.addWidget(StatTile("总用时", "%.0f s" % summary["elapsed"], ""))
