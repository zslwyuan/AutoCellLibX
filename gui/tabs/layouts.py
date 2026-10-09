"""Layouts tab: the interactive GDS viewer with layer control and cell info."""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
                               QLabel, QPushButton, QScrollArea, QSplitter,
                               QVBoxLayout, QWidget)

from .. import artifacts, gds_model, paths, theme
from ..widgets.common import Card, KeyValue, faint, h1, subtle
from ..widgets.gds_canvas import GdsCanvas, LayerPanel
from ..widgets.guide import GuidePanel


class LayoutsTab(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._cells = []
        self._model = None

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        # --- toolbar ---
        bar = QHBoxLayout()
        bar.addWidget(h1("版图 / Layouts"))
        bar.addStretch(1)
        bar.addWidget(QLabel("基准"))
        self.bench = QComboBox()
        self.bench.setMinimumWidth(120)
        self.bench.currentTextChanged.connect(self._on_bench)
        bar.addWidget(self.bench)
        bar.addWidget(QLabel("单元"))
        self.cell = QComboBox()
        self.cell.setMinimumWidth(140)
        self.cell.currentTextChanged.connect(self._on_cell)
        bar.addWidget(self.cell)
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.reload)
        bar.addWidget(self.refresh_btn)
        self.regen_btn = QPushButton("重新生成")
        self.regen_btn.setEnabled(False)
        self.regen_btn.clicked.connect(self._regen)
        bar.addWidget(self.regen_btn)
        self.export_btn = QPushButton("导出 PNG")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._export)
        bar.addWidget(self.export_btn)
        root.addLayout(bar)

        self.guide = GuidePanel([
            ("交互", "滚轮缩放、左键拖拽平移、双击或 F 适应窗口、± 缩放；"
             "勾选「测量 (M)」后点两点量距离。"),
            ("看图层", "右侧「图层」勾选显隐，预设一键切换（全部/金属/有源区/仅M1）；"
             "层名与配置页的 PDK 层映射一致。"),
            ("读信息", "「单元信息」：尺寸 µm、晶体管数、LP 规模、求解状态"
             "（OPTIMAL/FEASIBLE 正常）、间距修复违规数（应为 0）、标定比例。"),
            ("看边界", "黄色虚线框 = 单元边界（pr_boundary）；右下角比例尺；左下角光标坐标 µm。"),
            ("操作", "「导出 PNG」保存当前视图；「重新生成」重跑 ASTRAN（改过几何/工艺时基线也重算）。"),
            ("口径", "面积以『宽度』为代理（行高固定）；GDS 文件的 UNITS 记录不可信，"
             "查看器按日志标定（16.5 GDS单位/µm）。"),
        ])
        root.addWidget(self.guide)
        root.addWidget(subtle(
            "晶体管级版图（GDSII）。滚轮缩放、拖拽平移、双击/F 适应、M 测量；右侧控制图层显隐。"))

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)   # panels cannot be squashed flat
        root.addWidget(splitter, 1)

        self.canvas = GdsCanvas()
        splitter.addWidget(self.canvas)

        # --- right: layers + info + view controls ---
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(10)

        layer_card = Card("图层 / Layers")
        self.layer_panel = LayerPanel()
        self.layer_panel.bind_canvas(self.canvas)
        layer_card.add(self.layer_panel)
        right_lay.addWidget(layer_card, 1)

        info_card = Card("单元信息 / Cell info")
        self.info = KeyValue()
        info_card.add(self.info)
        right_lay.addWidget(info_card)

        view_card = Card("视图 / View")
        vrow = QHBoxLayout()
        self.grid_cb = QCheckBox("网格")
        self.grid_cb.setChecked(True)
        self.grid_cb.toggled.connect(self.canvas.set_show_grid)
        vrow.addWidget(self.grid_cb)
        self.measure_cb = QCheckBox("测量 (M)")
        self.measure_cb.setCheckable(True)
        self.measure_cb.toggled.connect(self._toggle_measure)
        vrow.addWidget(self.measure_cb)
        fit_btn = QPushButton("适应 (F)")
        fit_btn.clicked.connect(self.canvas.fit)
        vrow.addWidget(fit_btn)
        vrow.addStretch(1)
        view_card.add_layout(vrow)
        right_lay.addWidget(view_card)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QScrollArea.NoFrame)
        right_scroll.setWidget(right)
        right_scroll.setMinimumWidth(300)
        right_scroll.setMaximumWidth(360)
        splitter.addWidget(right_scroll)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        # --- status strip ---
        status = QHBoxLayout()
        self.coord = QLabel("—")
        self.coord.setObjectName("Faint")
        status.addWidget(self.coord)
        status.addStretch(1)
        self.measure_label = QLabel("")
        self.measure_label.setStyleSheet("color:%s; font-weight:600;" % theme.INFO)
        status.addWidget(self.measure_label)
        root.addLayout(status)
        self.canvas.cursorMoved.connect(self._on_cursor)
        self.canvas.measureChanged.connect(
            lambda d: self.measure_label.setText("测量距离：%.3f µm" % d))
        self.canvas.measureCleared.connect(lambda: self.measure_label.setText(""))

        self.reload_benchmarks()

    # ---------------------------------------------------------------- data
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
        self.reload()

    def reload(self):
        bench = self.bench.currentText() or self.ctx.state.current_benchmark
        out_dir = paths.output_dir(bench)
        prev = self.cell.currentText()
        self._cells = artifacts.scan_output_dir(out_dir)
        self.cell.blockSignals(True)
        self.cell.clear()
        for c in self._cells:
            if c.has_gds:
                self.cell.addItem(c.name)
        self.cell.blockSignals(False)
        if prev and self.cell.findText(prev) >= 0:
            self.cell.setCurrentText(prev)
        self._on_cell(self.cell.currentText())

    def select_cell(self, name):
        """Jump here from the Patterns tab: pick the benchmark cell by name."""
        bench = self.ctx.state.current_benchmark
        if self.bench.findText(bench) >= 0:
            self.bench.setCurrentText(bench)
        if self.cell.findText(name) >= 0:
            self.cell.setCurrentText(name)

    def _on_bench(self, name):
        if name:
            self.ctx.state.set_benchmark(name)
        self.reload()

    def _on_cell(self, name):
        bench = self.bench.currentText() or self.ctx.state.current_benchmark
        if not name:
            self.canvas.set_layout(None)
            self.export_btn.setEnabled(False)
            self.regen_btn.setEnabled(False)
            self.info.clear()
            self.info.add("提示", "该基准尚无版图；运行流程后生成。")
            return
        out_dir = paths.output_dir(bench)
        gds = os.path.join(out_dir, name + ".gds")
        log = os.path.join(out_dir, name + ".Astranlog")
        try:
            layer_map = artifacts.read_layer_map(
                self.ctx.state.config.layer_map())
            self._model = gds_model.load_layout(gds, log, layer_map=layer_map)
        except Exception as exc:                        # noqa: BLE001
            self.canvas.set_layout(None)
            self.ctx.log("读取 %s 失败 / failed to read layout: %s" % (name, exc),
                         "error")
            return
        self.canvas.set_layout(self._model)
        self.layer_panel.set_model(self._model)
        self.export_btn.setEnabled(True)
        self.regen_btn.setEnabled(True)
        self._fill_info(name, gds, log)

    def _fill_info(self, name, gds, log_path):
        self.info.clear()
        log = artifacts.parse_astran_log(log_path)
        model = self._model
        self.info.add("单元", name)
        if model.width_um and model.height_um:
            self.info.add("尺寸", "%.2f × %.2f µm" % (model.width_um, model.height_um),
                          theme.OK)
        if model.log_width_um:
            self.info.add("面积(宽)", "%.2f µm" % model.log_width_um)
        if log.n_transistors:
            self.info.add("晶体管", "%d (P %d / N %d)"
                          % (log.n_transistors, log.n_pmos or 0, log.n_nmos or 0))
        if log.solver_vars:
            self.info.add("LP 规模", "%s 变量 / %s 约束"
                          % (log.solver_vars, log.solver_cons))
        if log.solver_status:
            colour = theme.OK if "FEASIBLE" in log.solver_status or \
                "OPTIMAL" in log.solver_status else theme.WARN
            self.info.add("求解状态", log.solver_status, colour)
        if log.attempts:
            tracks, cons = log.attempts[-1]
            self.info.add("布线轨道/保守系数", "%d 轨 / cons=%d (共 %d 次尝试)"
                          % (tracks, cons, len(log.attempts)))
        if log.option3_retry:
            self.info.add("option-3 重试", "%d 次（恢复方案）" % log.option3_retries,
                          theme.WARN)
        if log.spacing_repairs:
            last = log.spacing_repairs[-1]
            self.info.add("间距修复", "%d 处违规" % last,
                          theme.OK if last == 0 else theme.ERROR)
        self.info.add("形状数", model.polygon_count)
        self.info.add("标定", "%.2f GDS单位/µm%s" % (model.units_per_um,
                                                "" if model.calibrated else " (默认)"))

    # ---------------------------------------------------------------- actions
    def _toggle_measure(self, on):
        self.canvas.set_measure_mode(on)
        if on:
            self.measure_label.setText("点击两点以测量…")

    def _regen(self):
        name = self.cell.currentText()
        if name:
            self.ctx.start_regen(name)

    def _export(self):
        if self._model is None:
            return
        name = self.cell.currentText() or "layout"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出版图 / Export layout", name + ".png", "PNG image (*.png)")
        if path:
            self.canvas.export_png(path)
            self.ctx.status("已导出 %s" % path)

    def _on_cursor(self, x, y):
        if x != x:          # NaN: cursor left the canvas
            self.coord.setText("—")
            return
        self.coord.setText("(%.3f, %.3f) µm" % (x, y))

    def refresh(self):
        self.reload_benchmarks()
