"""Patterns tab: what was mined -- the table, the figure, and the SPICE."""
import os
import subprocess

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QPlainTextEdit,
                               QPushButton, QSplitter, QTabWidget, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from .. import artifacts, paths, theme
from ..widgets.common import KeyValue, faint, h1, subtle
from ..widgets.guide import GuidePanel
from ..widgets.image_view import ZoomableImage


class PatternsTab(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._rows = []

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        bar = QHBoxLayout()
        bar.addWidget(h1("挖掘到的模式 / Mined patterns"))
        bar.addStretch(1)
        bar.addWidget(QLabel("基准"))
        self.bench = QComboBox()
        self.bench.setMinimumWidth(140)
        self.bench.currentTextChanged.connect(self._on_bench)
        bar.addWidget(self.bench)
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.refresh)
        bar.addWidget(self.refresh_btn)
        self.open_btn = QPushButton("打开输出目录")
        self.open_btn.clicked.connect(self._open_dir)
        bar.addWidget(self.open_btn)
        root.addLayout(bar)

        self.guide = GuidePanel([
            ("读表格", "每行是一个合并后的复杂单元：模式码（唯一身份）、出现次数、"
             "大小（含几个单元）、覆盖（出现×大小）、宽度 µm、节省与节省率。"),
            ("看细节", "点击任意行：右侧显示该模式的子图与晶体管级网表 .sp"
             "（端口、晶体管数、包含单元）。"),
            ("跑一次", "「—」表示本次会话还没运行过；运行后会填充。"),
            ("操作", "「重新生成版图」用当前 .sp 重跑 ASTRAN（不重挖模式）；"
             "「在版图页查看」跳转到版图页。"),
            ("注意", "COMPLEX 编号每次运行会变（临时分配），别拿旧 bestRecord 对号入座。"),
        ])
        root.addWidget(self.guide)
        root.addWidget(subtle(
            "每行是一个合并后的复杂单元：它的模式码（patternExtensionTrace）、出现次数、"
            "版图宽度与由此带来的面积收益。点击行查看子图与晶体管网表。"))

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)   # panels cannot be squashed flat
        root.addWidget(splitter, 1)

        # ---- left: table ----
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(8)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["名称", "模式码", "出现", "大小", "覆盖", "宽 µm", "节省", "节省率"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 92)
        self.table.setColumnWidth(1, 210)
        self.table.setColumnWidth(2, 46)
        self.table.setColumnWidth(3, 46)
        self.table.setColumnWidth(4, 58)
        self.table.setColumnWidth(5, 62)
        self.table.setColumnWidth(6, 60)
        self.table.setTextElideMode(Qt.ElideMiddle)
        self.table.itemSelectionChanged.connect(self._on_select)
        left_lay.addWidget(self.table, 1)

        act = QHBoxLayout()
        self.regen_btn = QPushButton("重新生成版图")
        self.regen_btn.setToolTip("用当前 .sp 重新跑一次 ASTRAN（不改挖掘）")
        self.regen_btn.clicked.connect(self._regen)
        self.regen_btn.setEnabled(False)
        act.addWidget(self.regen_btn)
        self.view_layout_btn = QPushButton("在版图页查看")
        self.view_layout_btn.clicked.connect(self._view_layout)
        self.view_layout_btn.setEnabled(False)
        act.addWidget(self.view_layout_btn)
        act.addStretch(1)
        self.count_label = faint("")
        act.addWidget(self.count_label)
        left_lay.addLayout(act)
        splitter.addWidget(left)

        # ---- right: figure + spice ----
        right = QSplitter(Qt.Vertical)
        right.setChildrenCollapsible(False)
        self.figure = ZoomableImage()
        right.addWidget(self.figure)

        self.spice_tabs = QTabWidget()
        self.spice_info = KeyValue()
        info_scroll = QWidget()
        info_lay = QVBoxLayout(info_scroll)
        info_lay.setContentsMargins(10, 10, 10, 10)
        info_lay.addWidget(self.spice_info)
        info_lay.addStretch(1)
        self.spice_tabs.addTab(info_scroll, "概要")

        self.spice_text = QPlainTextEdit()
        self.spice_text.setReadOnly(True)
        self.spice_tabs.addTab(self.spice_text, "网表 (.sp)")
        right.addWidget(self.spice_tabs)
        right.setStretchFactor(0, 3)      # the figure gets most of the height
        right.setStretchFactor(1, 2)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 11)
        splitter.setStretchFactor(1, 10)

        self.reload_benchmarks()

    # ------------------------------------------------------------ benchmark
    def reload_benchmarks(self):
        cur = self.ctx.state.current_benchmark
        self.bench.blockSignals(True)
        self.bench.clear()
        for b in artifacts.list_output_benchmarks(paths.OUTPUTS_DIR):
            self.bench.addItem(b)
        if self.bench.findText(cur) < 0 and cur:
            self.bench.addItem(cur)
        if cur:
            self.bench.setCurrentText(cur)
        self.bench.blockSignals(False)
        self.refresh()

    def _on_bench(self, name):
        if name:
            self.ctx.state.set_benchmark(name)
        self.refresh()

    # ---------------------------------------------------------------- data
    def refresh(self):
        bench = self.bench.currentText() or self.ctx.state.current_benchmark
        out_dir = paths.output_dir(bench)
        session = {p["name"]: p for p in self.ctx.state.patterns.get(bench, [])}
        separate = {r.name: r for r in self.ctx.state.separate_record(bench)}

        self._rows = []
        for cell in artifacts.scan_output_dir(out_dir):
            sp = artifacts.read_spice_netlist(cell.sp_path)
            log = artifacts.parse_astran_log(cell.log_path)
            name = cell.name
            sinfo = session.get(name, {})
            srow = separate.get(name)
            occ = sp.occurrences if sp.occurrences is not None \
                else sinfo.get("clusters")
            size = len(sp.cells) if sp.cells else sinfo.get("size")
            coverage = sinfo.get("coverage")
            if coverage is None and occ and size:
                coverage = occ * size
            save = sinfo.get("save_total")
            if save is None and srow is not None:
                save = srow.save_area
            self._rows.append({
                "name": name,
                "trace": sinfo.get("trace") or sp.pattern_code or "—",
                "occ": occ, "size": size, "coverage": coverage,
                "width": log.width_um if log.complete else sinfo.get("width_um"),
                "ntrans": log.n_transistors or sp.n_transistors,
                "save": save,
                "ratio": srow.save_ratio if srow else None,
                "has_sp": cell.has_sp, "has_gds": cell.has_gds,
                "has_png": cell.has_png, "has_log": cell.has_log,
                "cell": cell, "sp": sp, "log": log,
            })

        self.table.setRowCount(0)
        for r in self._rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self._set(row, 0, r["name"], bold=True)
            self._set(row, 1, r["trace"])
            self._set(row, 2, r["occ"])
            self._set(row, 3, r["size"])
            self._set(row, 4, r["coverage"])
            self._set(row, 5, "%.2f" % r["width"] if r["width"] else "—",
                      colour=theme.OK if r["width"] else None)
            save = r["save"]
            self._set(row, 6, "%.1f" % save if save is not None else "—",
                      colour=theme.OK if (save or 0) > 0 else None)
            self._set(row, 7, "%.1f%%" % r["ratio"] if r["ratio"] is not None else "—")
        self.count_label.setText("%d 个复杂单元" % len(self._rows))
        self._clear_detail()

    def _set(self, row, col, value, colour=None, bold=False):
        text = "—" if value is None else str(value)
        item = QTableWidgetItem(text)
        if value not in (None, "—"):
            item.setToolTip(str(value))          # full text when the cell elides
        if colour:
            item.setForeground(QColor(colour))
        if bold:
            item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.setItem(row, col, item)

    def _selected_row(self):
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def _on_select(self):
        r = self._selected_row()
        ok = 0 <= r < len(self._rows)
        self.regen_btn.setEnabled(ok and self._rows[r]["has_sp"])
        self.view_layout_btn.setEnabled(ok and self._rows[r]["has_gds"])
        if not ok:
            return
        row = self._rows[r]
        cell = row["cell"]
        if row["has_png"]:
            self.figure.set_image(cell.png_path, row["name"])
        else:
            self.figure.set_text("该模式尚无子图预览\n运行流程后会自动生成 COMPLEX*.png")
        self._fill_spice(row)

    def _fill_spice(self, row):
        sp = row["sp"]
        self.spice_info.clear()
        self.spice_info.add("名称", row["name"])
        self.spice_info.add("模式码", row["trace"])
        if sp.occurrences is not None:
            self.spice_info.add("出现次数", sp.occurrences)
        if sp.ports:
            self.spice_info.add("端口 (%d)" % len(sp.ports), "  ".join(sp.ports))
        if sp.n_transistors:
            self.spice_info.add("晶体管", "%d (P %d / N %d)"
                                % (sp.n_transistors, sp.n_pmos, sp.n_nmos))
        if row["width"]:
            self.spice_info.add("版图宽度", "%.2f µm × %.2f µm"
                                % (row["width"], row["log"].height_um or 0))
        if sp.cells:
            self.spice_info.add("包含单元", "  ".join(sp.cells))
        self.spice_text.setPlainText("\n".join(sp.all_lines) if sp.exists else
                                     "（尚未导出 .sp 网表；运行流程后生成）")

    def _clear_detail(self):
        self.figure.set_text("")
        self.spice_info.clear()
        self.spice_text.clear()
        self.regen_btn.setEnabled(False)
        self.view_layout_btn.setEnabled(False)

    # ---------------------------------------------------------------- actions
    def _open_dir(self):
        out_dir = paths.output_dir(self.bench.currentText() or
                                   self.ctx.state.current_benchmark)
        if os.path.isdir(out_dir):
            os.startfile(out_dir) if os.name == "nt" else subprocess.Popen(
                ["xdg-open", out_dir])

    def _regen(self):
        r = self._selected_row()
        if r >= 0:
            self.ctx.start_regen(self._rows[r]["name"])

    def _view_layout(self):
        r = self._selected_row()
        if r >= 0:
            self.ctx.window.layouts_tab.select_cell(self._rows[r]["name"])
            self.ctx.show_page("layouts")

    def add_live_pattern(self, bench, info):
        if bench == (self.bench.currentText() or self.ctx.state.current_benchmark):
            self.ctx.state.add_pattern(bench, info)
            self.refresh()
