"""Configure tab: pick benchmarks and tune the mining thresholds."""
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QGridLayout, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton,
                               QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from .. import paths, theme
from ..widgets.common import Card, badge, faint, h1, hline, subtle
from ..widgets.guide import GuidePanel

PRESETS = {
    "默认 (default)": dict(top_thr=5, ratio_thr=0.05, cnt_thr=30, max_cells=11,
                       do_baseline=True, do_layouts=True, do_phase2=True,
                       max_astran_runs=0, clean_outputs=False),
    "快速试跑 (quick)": dict(top_thr=3, ratio_thr=0.05, cnt_thr=30, max_cells=8,
                        do_baseline=False, do_layouts=True, do_phase2=False,
                        max_astran_runs=3, clean_outputs=False),
    "仅挖掘，不生成版图": dict(top_thr=5, ratio_thr=0.05, cnt_thr=30, max_cells=11,
                         do_baseline=False, do_layouts=False, do_phase2=True,
                         max_astran_runs=0, clean_outputs=False),
    "完全重算 (clean)": dict(top_thr=5, ratio_thr=0.05, cnt_thr=30, max_cells=11,
                        do_baseline=True, do_layouts=True, do_phase2=True,
                        max_astran_runs=0, clean_outputs=True),
}


class ConfigureTab(QWidget):
    configEdited = Signal()

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        container = QWidget()
        scroll.setWidget(container)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

        body = QVBoxLayout(container)
        body.setContentsMargins(22, 18, 22, 24)
        body.setSpacing(12)

        head = QHBoxLayout()
        head.addWidget(h1("配置 / Configure"))
        head.addStretch(1)
        head.addWidget(QLabel("预设"))
        self.preset = QComboBox()
        self.preset.addItems(list(PRESETS.keys()))
        self.preset.currentTextChanged.connect(self._apply_preset)
        head.addWidget(self.preset)
        body.addLayout(head)

        self.guide = GuidePanel([
            ("选择输入", "勾选内置基准，或用「📄 添加 BLIF 文件…」导入你自己的网表"
             "（自定义项会标 📄，与内置同名时以自定义为准）。"),
            ("换 PDK", "「输入文件 (PDK)」可分别指定 .lib / .sp / .rul / .lef / 层映射；"
             "留空 = 仓库默认 GSCL45。"),
            ("调约束", "「版图参数约束」一般保持默认；改行高/网格会写进 ASTRAN 脚本，"
             "且自定义几何会让基线单元全部重生成（同高对比才可信）。"),
            ("开始", "点底部「开始运行 ▶」跳到运行页启动；「恢复默认」还原全部设置。"),
        ])
        body.addWidget(self.guide)
        body.addWidget(subtle("选择要运行的基准与挖掘参数。所有设置只在点击『运行』时生效。"))

        cols = QHBoxLayout()
        cols.setSpacing(12)
        body.addLayout(cols, 1)

        # ---- benchmarks ----
        bench_card = Card("基准 / Benchmarks")
        note = faint("勾选要运行的 BLIF 设计。大设计解析耗时较长，建议先用小基准试跑。")
        bench_card.add(note)
        # Action row ABOVE the list: selection helpers + the add-BLIF entry,
        # so the buttons are visible without scrolling past the list.
        top_row = QHBoxLayout()
        top_row.setSpacing(5)
        for text, fn in (("全选", self._select_all), ("全不选", self._select_none),
                         ("仅小基准", self._select_small)):
            b = QPushButton(text)
            b.setToolTip({"全选": "勾选所有输入（内置 + 自定义）",
                          "全不选": "清空勾选",
                          "仅小基准": "只勾选解析快的基准"}[text])
            b.clicked.connect(fn)
            top_row.addWidget(b)
        top_row.addStretch(1)
        self.add_blif_btn = QPushButton("📄 添加 BLIF 文件…")
        self.add_blif_btn.setToolTip("选择一个或多个网表文件（BLIF 格式）作为额外输入")
        self.add_blif_btn.clicked.connect(self._add_custom_files)
        top_row.addWidget(self.add_blif_btn)
        bench_card.add_layout(top_row)

        self.bench_list = QListWidget()
        self.bench_list.setSelectionMode(QListWidget.SingleSelection)
        self.bench_list.itemChanged.connect(self._bench_changed)
        bench_card.add(self.bench_list)

        bottom_row = QHBoxLayout()
        self.remove_blif_btn = QPushButton("移除所选自定义")
        self.remove_blif_btn.setEnabled(False)
        self.remove_blif_btn.clicked.connect(self._remove_selected_custom)
        bottom_row.addWidget(self.remove_blif_btn)
        bottom_row.addStretch(1)
        bench_card.add_layout(bottom_row)
        self.bench_list.currentRowChanged.connect(self._update_remove_btn)
        self._bench_hint = faint("")
        bench_card.add(self._bench_hint)
        cols.addWidget(bench_card, 1)

        # ---- parameters ----
        right = QVBoxLayout()
        right.setSpacing(12)
        cols.addLayout(right, 1)

        param_card = Card("挖掘参数 / Mining parameters")
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        self.top_thr = self._spin(1, 30, 5,
                                  "外层轮数与每轮考察的候选数上限（main.py: top_thr）")
        self.ratio_thr = self._dspin(0.0, 1.0, 0.05, 0.005, 3,
                                     "模式覆盖率下限：size×cnt ≥ ratio×总单元数（main.py: ratio_thr）")
        self.cnt_thr = self._spin(1, 1000, 30,
                                  "模式出现次数下限（main.py: cnt_thr）")
        self.max_cells = self._spin(2, 20, 11,
                                    "单个复杂单元最多含的原始单元数（< 此值）")
        self.max_astran_runs = self._spin(0, 200, 0,
                                          "本轮最多生成几个复杂单元版图（0=不限；用于快速试跑）")
        form.addRow("top_thr", self.top_thr)
        form.addRow("ratio_thr", self.ratio_thr)
        form.addRow("cnt_thr", self.cnt_thr)
        form.addRow("最大单元数", self.max_cells)
        form.addRow("ASTRAN 运行上限", self.max_astran_runs)
        param_card.add_layout(form)
        right.addWidget(param_card)

        stage_card = Card("阶段与选项 / Stages & options")
        self.cb_baseline = self._check("生成 ASTRAN 基线单元（已存在则跳过）", True,
                                       "面积对比需要同高的 ASTRAN 基线；首次运行必须开启")
        self.cb_layouts = self._check("为复杂单元生成版图（ASTRAN autoflow）", True,
                                      "关闭则只做挖掘与收益估算（读取已有版图，若无则为 0）")
        self.cb_phase2 = self._check("逐模式明细（phase 2，写出 bestRecord-seperate）", True,
                                     "单独评估每个模式，给出每模式收益表")
        self.cb_clean = self._check("运行前清空该基准的旧产物 (COMPLEX*/bestRecord-*)", False,
                                    "避免旧文件与新模式 id 冲突（AGENTS.md 陷阱）")
        self.cb_force = self._check("强制重新生成已有版图（忽略缓存）", False,
                                    "默认按 .gds/.sp 时间戳复用缓存；开启后全部重算，耗时")
        for cb in (self.cb_baseline, self.cb_layouts, self.cb_phase2,
                   self.cb_clean, self.cb_force):
            stage_card.add(cb)
        right.addWidget(stage_card)

        # ---- PDK inputs: the library / technology files the flow parses ----
        inputs_card = Card("输入文件 / Input files (PDK)")
        note = faint("留空使用仓库默认（GSCL45 库与 vendored ASTRAN 工艺文件）。"
                     "换成其他 PDK 时，层映射让版图页按新层号显示。")
        inputs_card.add(note)
        self._file_value = {}
        self._pdk_defaults = {
            "liberty_file": ("Liberty 单元库 (.lib)", paths.LIBERTY_FILE,
                             "Liberty files (*.lib);;All files (*)",
                             "单元引脚方向（解析 BLIF 必需）"),
            "spice_lib_file": ("SPICE 库 (.sp)", paths.SPICE_LIB_FILE,
                               "SPICE netlists (*.sp);;All files (*)",
                               "原始单元的晶体管级子电路（导出 COMPLEX 网表用）"),
            "technology_file": ("工艺规则 (.rul)", paths.ASTRAN_TECHNOLOGY,
                                "Rule files (*.rul);;All files (*)",
                                "ASTRAN 设计规则（load technology）"),
            "lef_file": ("LEF (.lef)", paths.LEF_FILE,
                         "LEF files (*.lef);;All files (*)",
                         "单元标称宽度来源（面积对比用；空则 GSCL45 LEF）"),
            "layer_map_file": ("层映射 (.map)", paths.LAYER_MAP_FILE,
                               "Layer maps (*.map *.txt);;All files (*)",
                               "Cadence 层映射（stream→名称），供版图查看器使用"),
        }
        for key, (title, default, filt, tip) in self._pdk_defaults.items():
            inputs_card.add(self._file_row(key, title, default, filt, tip))
        right.addWidget(inputs_card)

        # ---- layout constraints: ASTRAN geometry, editable ----
        geo_card = Card("版图参数约束 / Layout constraints")
        geo_note = faint("写入 ASTRAN .run 脚本的几何参数（默认取 pySrc/astran.py 常量）。"
                         "行高 H = cells_height × v_grid；改行高需重新做 DRC 验证。")
        geo_card.add(geo_note)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        self.geo_cells_height = self._spin(1, 60, 13,
                                           "行高的轨道数；H = cells_height × v_grid")
        self.geo_hgrid = self._dspin(0.001, 10.0, 0.19, 0.01, 3,
                                     "水平网格（µm），M1 布线节距")
        self.geo_vgrid = self._dspin(0.001, 10.0, 0.19, 0.01, 3,
                                     "垂直网格（µm）")
        self.geo_supply = self._dspin(0.001, 10.0, 0.26, 0.01, 3,
                                      "电源轨宽度（µm，GSCL45 接界轨风格）")
        self.geo_nwell = self._dspin(0.001, 10.0, 1.235, 0.01, 3,
                                     "N 阱下沿位置（µm）；H/2 时 P/N 阱等高")
        self.geo_template = QComboBox()
        self.geo_template.setEditable(True)
        self.geo_template.addItems(["Tapless"])
        self.geo_template.setToolTip("ASTRAN 单元模板（当前使用 Tapless）")
        for w in (self.geo_cells_height, self.geo_hgrid, self.geo_vgrid,
                  self.geo_supply, self.geo_nwell, self.geo_template):
            if isinstance(w, QComboBox):
                w.currentTextChanged.connect(lambda _t: self._geometry_changed())
            else:
                w.valueChanged.connect(lambda _v: self._geometry_changed())
        form.addRow("cells_height", self.geo_cells_height)
        form.addRow("h_grid", self.geo_hgrid)
        form.addRow("v_grid", self.geo_vgrid)
        form.addRow("supply_size", self.geo_supply)
        form.addRow("nwell_pos", self.geo_nwell)
        form.addRow("cell_template", self.geo_template)
        geo_card.add_layout(form)
        reset_geo = QPushButton("恢复默认 (astran.py 常量)")
        reset_geo.clicked.connect(self._reset_geometry)
        geo_card.add(reset_geo)
        self._geo_hint = faint("")
        geo_card.add(self._geo_hint)
        right.addWidget(geo_card)
        right.addStretch(1)

        # ---- footer ----
        body.addWidget(hline())
        foot = QHBoxLayout()
        self._summary = faint("")
        foot.addWidget(self._summary, 1)
        reset = QPushButton("恢复默认")
        reset.clicked.connect(self._reset_defaults)
        foot.addWidget(reset)
        self.start_btn = QPushButton("开始运行 ▶")
        self.start_btn.setObjectName("Primary")
        self.start_btn.clicked.connect(self._start)
        foot.addWidget(self.start_btn)
        body.addLayout(foot)

        self._load_benchmarks()
        self._sync_from_config()
        self._load_geometry()

    # --------------------------------------------------------------- helpers
    def _file_row(self, key, title, default, filt, tip):
        """One input-file row: elided value + 浏览… + 默认 buttons."""
        row = QHBoxLayout()
        lab = QLabel(title)
        lab.setFixedWidth(120)
        lab.setToolTip(tip)
        value = QLabel("")
        value.setObjectName("Faint")
        value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        value.setToolTip(tip)
        browse = QPushButton("浏览…")
        browse.setToolTip("选择 " + title)

        def _browse():
            p, _ = QFileDialog.getOpenFileName(self, "选择 " + title, "", filt)
            if p:
                self._set_pdk(key, os.path.abspath(p))

        def _reset():
            self._set_pdk(key, None)

        browse.clicked.connect(_browse)
        reset = QPushButton("默认")
        reset.setToolTip("使用仓库默认：%s" % default)
        reset.clicked.connect(_reset)
        row.addWidget(lab)
        row.addWidget(value, 1)
        row.addWidget(browse)
        row.addWidget(reset)
        self._file_value[key] = value
        wrapper = QWidget()
        wrapper.setLayout(row)
        return wrapper

    def _set_pdk(self, key, path):
        cfg = self.ctx.state.config
        setattr(cfg, key, path)
        self._sync_pdk_row(key)
        self.ctx.state.configChanged.emit()
        self._update_summary()

    def _sync_pdk_row(self, key):
        cfg = self.ctx.state.config
        value = getattr(cfg, key)
        default = self._pdk_defaults[key][1]
        lab = self._file_value[key]
        if value:
            lab.setText(os.path.basename(value))
            lab.setToolTip(value)
            lab.setStyleSheet("color:%s; font-weight:600;" % theme.ACCENT)
        else:
            lab.setText("默认：%s" % os.path.basename(default))
            lab.setToolTip(default)

    def _sync_pdk(self):
        for key in self._pdk_defaults:
            self._sync_pdk_row(key)

    # ---------------------------------------------------------- geometry
    def _load_geometry(self):
        """Load the astran.py constants as the defaults for the editable fields."""
        try:
            paths.ensure_pysrc_on_path()
            import astran
            self._geo_defaults = {
                "cells_height": astran.ASTRAN_CELLS_HEIGHT,
                "h_grid": astran.ASTRAN_HGRID,
                "v_grid": astran.ASTRAN_VGRID,
                "supply_size": astran.ASTRAN_SUPPLY_SIZE,
                "nwell_pos": astran.ASTRAN_NWELL_POS,
                "cell_template": astran.ASTRAN_CELL_TEMPLATE,
            }
        except Exception as exc:                        # noqa: BLE001
            self._geo_defaults = {"cells_height": 13, "h_grid": 0.19, "v_grid": 0.19,
                                  "supply_size": 0.26, "nwell_pos": 1.235,
                                  "cell_template": "Tapless"}
            self.ctx.log("读取 Astran 几何常量失败，使用默认值：%s" % exc, "warn")
        self._sync_geometry()

    def _sync_geometry(self):
        cfg = self.ctx.state.config
        defaults = getattr(self, "_geo_defaults", {}) or {}
        geo = cfg.geometry or defaults
        for key, widget in (("cells_height", self.geo_cells_height),
                            ("h_grid", self.geo_hgrid),
                            ("v_grid", self.geo_vgrid),
                            ("supply_size", self.geo_supply),
                            ("nwell_pos", self.geo_nwell)):
            widget.blockSignals(True)
            widget.setValue(geo.get(key, defaults.get(key, widget.value())))
            widget.blockSignals(False)
        self.geo_template.blockSignals(True)
        self.geo_template.setCurrentText(
            geo.get("cell_template", defaults.get("cell_template", "Tapless")))
        self.geo_template.blockSignals(False)
        H = geo.get("cells_height", 13) * geo.get("v_grid", 0.19)
        self._geo_hint.setText("当前行高 H = %.2f µm%s"
                               % (H, "（默认值）" if cfg.geometry is None else ""))
        self._geometry_changed(update_hint=False)

    def _geometry_changed(self, update_hint=True):
        cfg = self.ctx.state.config
        cfg.geometry = {
            "cells_height": self.geo_cells_height.value(),
            "h_grid": self.geo_hgrid.value(),
            "v_grid": self.geo_vgrid.value(),
            "supply_size": self.geo_supply.value(),
            "nwell_pos": self.geo_nwell.value(),
            "cell_template": self.geo_template.currentText(),
        }
        if update_hint:
            H = cfg.geometry["cells_height"] * cfg.geometry["v_grid"]
            self._geo_hint.setText("当前行高 H = %.2f µm（自定义）" % H)
        self.ctx.state.configChanged.emit()
        self._update_summary()

    def _reset_geometry(self):
        self.ctx.state.config.geometry = None
        self._sync_geometry()
        self.ctx.log("已恢复 ASTRAN 几何默认值 (pySrc/astran.py)", "info")

    def _spin(self, lo, hi, val, tip):
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setValue(val)
        s.setToolTip(tip)
        s.valueChanged.connect(lambda _v: self._apply_to_config())
        return s

    def _dspin(self, lo, hi, val, step, decimals, tip):
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setValue(val)
        s.setSingleStep(step)
        s.setDecimals(decimals)
        s.setToolTip(tip)
        s.valueChanged.connect(lambda _v: self._apply_to_config())
        return s

    def _check(self, text, checked, tip):
        c = QCheckBox(text)
        c.setChecked(checked)
        c.setToolTip(tip)
        c.toggled.connect(lambda _v: self._apply_to_config())
        return c

    def _load_benchmarks(self, checked=None):
        """(Re)build the input list from standard benchmarks + custom BLIFs.

        ``checked`` (list of names) preserves the selection across reloads;
        None falls back to the previous selection or "adder" on first load.
        """
        state = self.ctx.state
        if checked is None:
            checked = [self.bench_list.item(i).data(Qt.UserRole)
                       for i in range(self.bench_list.count())
                       if self.bench_list.item(i).checkState() == Qt.Checked]
        if not checked and state.config.benchmarks:
            checked = list(state.config.benchmarks)

        self.bench_list.blockSignals(True)
        self.bench_list.clear()
        for name, path, is_custom in state.blif_sources():
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if name in checked else Qt.Unchecked)
            if is_custom:
                exists = os.path.exists(path)
                item.setText("📄 %s   (自定义 BLIF)" % name)
                item.setToolTip(path)
                if not exists:
                    item.setText("📄 %s   ⚠ 文件不存在" % name)
                    item.setForeground(QColor(theme.ERROR))
            else:
                size = os.path.getsize(path) if os.path.exists(path) else 0
                kb = size / 1024.0
                item.setText("%s   (%.0f KB)" % (name, kb))
                item.setToolTip("%s  (%.0f KB)" % (name, kb))
                if size > paths.LARGE_BLIF_BYTES:
                    item.setText("%s   ⚠ %.1f MB" % (name, size / 1e6))
                    item.setForeground(QColor(theme.WARN))
            self.bench_list.addItem(item)
        self.bench_list.blockSignals(False)
        self._update_summary()

    def _sync_from_config(self):
        cfg = self.ctx.state.config
        self._apply_preset_dict({
            "top_thr": cfg.top_thr, "ratio_thr": cfg.ratio_thr,
            "cnt_thr": cfg.cnt_thr, "max_cells": cfg.max_cells,
            "do_baseline": cfg.do_baseline, "do_layouts": cfg.do_layouts,
            "do_phase2": cfg.do_phase2, "max_astran_runs": cfg.max_astran_runs,
            "clean_outputs": cfg.clean_outputs})
        self.cb_force.setChecked(cfg.force_regenerate)
        self._select_benchmarks(cfg.benchmarks)
        self._sync_pdk()
        self._sync_geometry()
        self._update_summary()

    # ------------------------------------------------------------ selection
    def _selected_benchmarks(self):
        out = []
        for i in range(self.bench_list.count()):
            item = self.bench_list.item(i)
            if item.checkState() == Qt.Checked:
                out.append(item.data(Qt.UserRole))
        return out

    def _select_benchmarks(self, names):
        self.bench_list.blockSignals(True)
        names = set(names)
        for i in range(self.bench_list.count()):
            item = self.bench_list.item(i)
            item.setCheckState(Qt.Checked if item.data(Qt.UserRole) in names
                               else Qt.Unchecked)
        self.bench_list.blockSignals(False)
        self._update_summary()

    def _select_all(self):
        names = [name for name, _p, _c in self.ctx.state.blif_sources()]
        self._select_benchmarks(names)

    def _select_none(self):
        self._select_benchmarks([])

    def _select_small(self):
        small = [name for name, size, _p in paths.list_benchmarks()
                 if size <= paths.LARGE_BLIF_BYTES]
        self._select_benchmarks(small)

    # ------------------------------------------------------------ custom BLIF
    def _add_custom_files(self):
        chosen, _ = QFileDialog.getOpenFileNames(
            self, "选择 BLIF 网表文件 / Select BLIF netlists",
            "", "BLIF netlists (*.blif);;All files (*)")
        if not chosen:
            return
        cfg = self.ctx.state.config
        added = []
        for p in chosen:
            name = os.path.splitext(os.path.basename(p))[0]
            cfg.custom_blifs[name] = os.path.abspath(p)
            if name not in cfg.benchmarks:
                cfg.benchmarks.append(name)
            added.append(name)
        self._load_benchmarks()
        self._apply_to_config()
        self.ctx.log("已添加 %d 个自定义 BLIF 输入：%s"
                     % (len(added), ", ".join(added)), "accent")
        self.ctx.status("已添加 %d 个自定义 BLIF" % len(added))

    def _remove_selected_custom(self):
        row = self.bench_list.currentRow()
        if row < 0:
            return
        name = self.bench_list.item(row).data(Qt.UserRole)
        cfg = self.ctx.state.config
        if name not in cfg.custom_blifs:
            return
        del cfg.custom_blifs[name]
        if name in cfg.benchmarks:
            cfg.benchmarks.remove(name)
        self._load_benchmarks()
        self._apply_to_config()
        self.ctx.log("已移除自定义输入 %s" % name, "info")

    def _update_remove_btn(self, row):
        custom = False
        if row >= 0:
            name = self.bench_list.item(row).data(Qt.UserRole)
            custom = name in self.ctx.state.config.custom_blifs
        self.remove_blif_btn.setEnabled(custom)

    def _bench_changed(self, _item):
        self._apply_to_config()
        self._update_summary()

    # ---------------------------------------------------------------- config
    def _apply_preset(self, name):
        self._apply_preset_dict(PRESETS[name])

    def _apply_preset_dict(self, d):
        widgets = [(self.top_thr, "top_thr"), (self.cnt_thr, "cnt_thr"),
                   (self.max_cells, "max_cells"),
                   (self.max_astran_runs, "max_astran_runs")]
        for w, key in widgets:
            if key in d:
                w.blockSignals(True)
                w.setValue(d[key])
                w.blockSignals(False)
        if "ratio_thr" in d:
            self.ratio_thr.blockSignals(True)
            self.ratio_thr.setValue(d["ratio_thr"])
            self.ratio_thr.blockSignals(False)
        for cb, key in ((self.cb_baseline, "do_baseline"),
                        (self.cb_layouts, "do_layouts"),
                        (self.cb_phase2, "do_phase2"),
                        (self.cb_clean, "clean_outputs")):
            if key in d:
                cb.blockSignals(True)
                cb.setChecked(d[key])
                cb.blockSignals(False)
        self._apply_to_config()

    def _apply_to_config(self):
        cfg = self.ctx.state.config
        cfg.top_thr = self.top_thr.value()
        cfg.ratio_thr = self.ratio_thr.value()
        cfg.cnt_thr = self.cnt_thr.value()
        cfg.max_cells = self.max_cells.value()
        cfg.max_astran_runs = self.max_astran_runs.value()
        cfg.do_baseline = self.cb_baseline.isChecked()
        cfg.do_layouts = self.cb_layouts.isChecked()
        cfg.do_phase2 = self.cb_phase2.isChecked()
        cfg.clean_outputs = self.cb_clean.isChecked()
        cfg.force_regenerate = self.cb_force.isChecked()
        cfg.benchmarks = self._selected_benchmarks()
        self.ctx.state.configChanged.emit()
        self.configEdited.emit()
        self._update_summary()

    def _update_summary(self):
        n = len(self._selected_benchmarks())
        cfg = self.ctx.state.config
        layout = "生成版图" if cfg.do_layouts else "不生成版图"
        custom = " · %d 个自定义" % len(cfg.custom_blifs) if cfg.custom_blifs else ""
        pdk = " · 自定义PDK" if (cfg.liberty_file or cfg.spice_lib_file or
                                 cfg.technology_file or cfg.lef_file or
                                 cfg.geometry) else ""
        geo = ""
        if cfg.geometry:
            H = cfg.geometry["cells_height"] * cfg.geometry["v_grid"]
            geo = " · H=%.2f" % H
        self._summary.setText(
            "将运行 %d 个基准%s%s%s · top_thr=%d · ratio=%g · cnt=%d · %s%s"
            % (n, custom, pdk, geo, cfg.top_thr, cfg.ratio_thr, cfg.cnt_thr,
               layout,
               " · 上限 %d" % cfg.max_astran_runs if cfg.max_astran_runs else ""))
        if n == 0:
            self._bench_hint.setText("⚠ 未选择任何基准")
        else:
            self._bench_hint.setText("已选 %d 个基准" % n)

    def _reset_defaults(self):
        cfg = self.ctx.state.config
        cfg.custom_blifs.clear()
        for key in self._pdk_defaults:
            setattr(cfg, key, None)
        cfg.geometry = None
        self.preset.blockSignals(True)
        self.preset.setCurrentText("默认 (default)")
        self.preset.blockSignals(False)
        self._apply_preset("默认 (default)")
        self._select_benchmarks(["adder"])
        self._sync_pdk()
        self._sync_geometry()
        self._apply_to_config()

    def _start(self):
        self._apply_to_config()
        if not self.ctx.state.config.benchmarks:
            self.ctx.status("请先选择至少一个基准")
            self._bench_hint.setText("⚠ 请先勾选至少一个基准")
            return
        self.ctx.show_page("run")
        self.ctx.start_run()

    def set_running(self, running):
        self.start_btn.setEnabled(not running)
