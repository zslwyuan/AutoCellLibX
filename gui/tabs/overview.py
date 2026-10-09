"""Overview tab: what the tool does, the pipeline, and a health check."""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from .. import artifacts, flow_core, paths, theme
from ..widgets.common import (Card, StatTile, StatusDot, badge, faint, h1, h2,
                              hline, subtle)
from ..widgets.guide import GuidePanel

STAGE_DESCRIPTIONS = {
    "env": ("检查工具链", "确认 ASTRAN 二进制、工艺规则、LP 求解器与 Python 依赖是否就绪。"),
    "parse": ("解析设计", "读取 GSCL45 liberty 与 BLIF 网表，构建有向图，统计单元类型。"),
    "baseline": ("ASTRAN 基线", "为库中每个原始单元生成同高 ASTRAN 版图，作为面积对比基准。"),
    "cluster": ("初始聚类", "按结构编码把频繁子图聚成模式序列，只保留高频 Top。"),
    "mine": ("模式挖掘", "贪心迭代：导出候选 SPICE、生成版图、读回宽度、累计收益。"),
    "layout": ("复杂版图", "对每个复杂单元执行 ASTRAN autoflow：折叠→布局→布线→压缩。"),
    "phase2": ("逐模式明细", "单独评估每个模式的覆盖与收益，写出 bestRecord-seperate。"),
    "records": ("写出结果", "生成 bestRecord-* 结果文件，并给出图形化的面积对比。"),
}

QUICK_STEPS = [
    ("1", "选择基准", "在『配置』里勾选一个或多个 BLIF 基准（先用 adder 试运行）。"),
    ("2", "调整参数", "阈值决定挖掘的激进度；第一次用保持默认即可。"),
    ("3", "运行流程", "在『运行』里启动，实时查看每个单元版图的生成进度。"),
    ("4", "查看结果", "到『模式』『版图』『结果』里检查挖掘出的模式、版图与面积收益。"),
]


class OverviewTab(QWidget):
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
        body.setSpacing(14)

        # --- header ---
        head = QHBoxLayout()
        head.addWidget(h1("AutoCellLibX · 标准单元扩展工作台"))
        head.addStretch(1)
        refresh = QPushButton("重新检查环境")
        refresh.clicked.connect(self.refresh)
        head.addWidget(refresh)
        run_btn = QPushButton("运行默认基准 (adder) ▶")
        run_btn.setObjectName("Primary")
        run_btn.clicked.connect(self._quick_run)
        head.addWidget(run_btn)
        body.addLayout(head)

        self.guide = GuidePanel([
            ("读数字", "顶部四个数字：基准数、已生成基线单元、已有结果目录、最佳节省率。"),
            ("读环境", "「环境检查」红=必需项缺失（如 ASTRAN 被 360 隔离）、黄=可选缺失；"
             "把鼠标停在条目上看修复提示。"),
            ("看流程", "「流水线」是八个阶段：运行时在「运行」页逐个点亮。"),
            ("快速跑通", "点右上角「运行默认基准 (adder) ▶」直接开始。"),
        ])
        body.addWidget(self.guide)
        body.addWidget(subtle(
            "从已映射的门级网表中挖掘频繁出现的子电路，把每个模式合并成一个复杂单元，"
            "再用 ASTRAN 在晶体管级自动布局布线，从而缩减整个设计的面积。"))

        # --- key numbers ---
        stats_card = Card("数据与产物 / Data & artifacts")
        tiles = QHBoxLayout()
        tiles.setSpacing(10)
        self.tile_benchmarks = StatTile("基准", "--", "benchmark/blif/")
        self.tile_baseline = StatTile("基线单元", "--", "original_astran_cells/")
        self.tile_outputs = StatTile("已有结果", "--", "outputs/*/")
        self.tile_best = StatTile("最佳节省", "--", "bestRecord-adder")
        for t in (self.tile_benchmarks, self.tile_baseline,
                  self.tile_outputs, self.tile_best):
            tiles.addWidget(t, 1)
        stats_card.add_layout(tiles)
        body.addWidget(stats_card)

        # --- quick start ---
        steps = Card("快速上手 / Quick start")
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        for i, (num, title, desc) in enumerate(QUICK_STEPS):
            cell = QVBoxLayout()
            title_row = QHBoxLayout()
            title_row.addWidget(badge(num, theme.ACCENT))
            title_row.addWidget(h2(title))
            title_row.addStretch(1)
            cell.addLayout(title_row)
            cell.addWidget(faint(desc))
            wrapper = QWidget()
            wrapper.setLayout(cell)
            grid.addWidget(wrapper, i // 2, i % 2)
        steps.add_layout(grid)
        body.addWidget(steps)

        # --- pipeline stages ---
        pipe = Card("流水线 / Pipeline")
        body_note = faint("每个阶段对应下方一栏；运行时『运行』页会逐个标记进度。")
        pipe.add(body_note)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        self._stage_dots = {}
        for i, (key, label) in enumerate(flow_core.STAGES):
            frame = Card()
            lay = frame.body
            dot = StatusDot("", "pending")
            row = QHBoxLayout()
            row.addWidget(dot)
            row.addWidget(badge(str(i + 1), theme.ACCENT_DIM))
            row.addStretch(1)
            lay.addLayout(row)
            title, desc = STAGE_DESCRIPTIONS.get(key, (key, ""))
            lay.addWidget(h2(title))
            lay.addWidget(faint(desc))
            frame.setMinimumWidth(210)
            self._stage_dots[key] = dot
            grid.addWidget(frame, i // 4, i % 4)
        pipe.add_layout(grid)
        body.addWidget(pipe)

        # --- environment ---
        self.env_card = Card("环境检查 / Environment")
        self._env_layout = QVBoxLayout()
        self.env_card.add_layout(self._env_layout)
        body.addWidget(self.env_card)

        body.addWidget(hline())
        body.addWidget(faint(
            "提示：版图与结果使用与命令行相同的文件契约（COMPLEX*.sp/gds、bestRecord-*），"
            "可与 flow/main.py 互相复用。此界面不会破坏任何工程不变量。"))

        self.refresh()

    # ------------------------------------------------------------ actions
    def _quick_run(self):
        self.ctx.state.config.benchmarks = ["adder"]
        self.ctx.state.configChanged.emit()
        self.ctx.show_page("run")
        self.ctx.start_run()

    def refresh(self):
        sources = self.ctx.state.blif_sources()
        n_custom = sum(1 for _n, _p, c in sources if c)
        self.tile_benchmarks.set_value(len(sources))
        self.tile_benchmarks.set_hint(
            "benchmark/blif/%s" % ("+ 自定义" if n_custom else ""))
        n_base = 0
        if os.path.isdir(paths.ORIGINAL_CELLS_DIR):
            n_base = len([f for f in os.listdir(paths.ORIGINAL_CELLS_DIR)
                          if f.endswith(".Astranlog")])
        self.tile_baseline.set_value(n_base)
        outs = artifacts.list_output_benchmarks(paths.OUTPUTS_DIR)
        self.tile_outputs.set_value(len(outs))
        best = self.ctx.state.best_record("adder")
        if best.exists and best.save_ratio_astran is not None:
            self.tile_best.set_value("%.2f%%" % best.save_ratio_astran, theme.OK)
        else:
            self.tile_best.set_value("--")

        # environment
        while self._env_layout.count():
            item = self._env_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        checks = paths.probe_environment()
        for c in checks:
            dot = StatusDot("", "ok" if c.ok else ("error" if c.required else "warn"))
            row = QHBoxLayout()
            row.addWidget(dot)
            lab = QLabel(c.label)
            lab.setStyleSheet("font-weight:600;")
            row.addWidget(lab)
            detail = c.detail if len(str(c.detail)) < 70 else "…" + str(c.detail)[-66:]
            det = QLabel(str(detail))
            det.setObjectName("Faint")
            det.setWordWrap(True)
            row.addWidget(det, 1)
            self._env_layout.addLayout(row)
            if not c.ok and c.hint:
                hint = QLabel("    ↳ " + c.hint)
                hint.setObjectName("Faint")
                hint.setWordWrap(True)
                self._env_layout.addWidget(hint)
        self._env_layout.addStretch(1)

    def set_stage_state(self, key, status):
        dot = self._stage_dots.get(key)
        if dot is not None:
            dot.set_state(status)
