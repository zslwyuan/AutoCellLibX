"""Design tab: understand the benchmark before mining it.

Parses the BLIF + liberty into the design graph (the cheap front part of the
flow) and shows the cell-type histogram plus an interactive neighbourhood
explorer around a sample instance of any cell type.
"""
import os

import networkx as nx
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QSpinBox, QSplitter, QVBoxLayout,
                               QWidget)

from .. import paths, theme
from ..widgets.chart import MplCanvas
from ..widgets.common import Card, StatTile, badge, faint, h1, subtle
from ..widgets.graph_canvas import GraphCanvas
from ..widgets.guide import GuidePanel

MAX_NEIGHBOURHOOD = 140


class DesignTab(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._design = None

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        bar = QHBoxLayout()
        bar.addWidget(h1("设计浏览 / Design explorer"))
        bar.addStretch(1)
        bar.addWidget(QLabel("基准"))
        self.bench = QComboBox()
        self.bench.setMinimumWidth(170)
        bar.addWidget(self.bench)
        self.parse_btn = QPushButton("解析设计")
        self.parse_btn.setObjectName("Primary")
        self.parse_btn.clicked.connect(self._parse)
        bar.addWidget(self.parse_btn)
        root.addLayout(bar)

        self.guide = GuidePanel([
            ("解析", "选一个基准（含 📄 自定义 BLIF），点「解析设计」加载网表图——只解析、"
             "不挖掘不跑版图，小设计几秒完成。"),
            ("读统计", "四个数字：单元数、连接数、单元类型数、时序/bypass 数"
             "（DFF/bool 不参与模式聚类）。"),
            ("看分布", "左侧直方图：单元类型分布（Top 24），了解设计的逻辑构成。"),
            ("探索", "右侧「邻居探索」：选一个类型 → 调深度 → 「显示示例」，画出该类型一个实例的"
             "上下游邻居子图（高亮=根）；点击节点看详情。"),
            ("缓存", "已解析的设计按输入（BLIF/PDK 路径与时间戳）缓存：同一基准重复点"
             "「解析设计」且输入未变时直接显示缓存；更换 BLIF 或 PDK 后自动重新解析。"),
        ])
        root.addWidget(self.guide)
        self.hint = subtle("解析网表后，可查看单元类型分布，并在任意类型周围探索其邻居子图。"
                           "大设计解析较慢且不可中断。")
        root.addWidget(self.hint)

        # --- stats ---
        self.tiles = QGridLayout()
        self.tile_nodes = StatTile("单元", "--", "")
        self.tile_edges = StatTile("连接", "--", "")
        self.tile_types = StatTile("单元类型", "--", "")
        self.tile_stop = StatTile("时序/bypass", "--", "不参与聚类")
        for i, t in enumerate((self.tile_nodes, self.tile_edges,
                               self.tile_types, self.tile_stop)):
            self.tiles.addWidget(t, 0, i)
        root.addLayout(self.tiles)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)   # panels cannot be squashed flat
        root.addWidget(splitter, 1)

        # --- left: histogram ---
        hist_card = Card("单元类型分布 / Cell-type histogram (top 24)")
        self.hist_chart = MplCanvas(height=5.0)
        hist_card.add(self.hist_chart)
        splitter.addWidget(hist_card)

        # --- right: neighbourhood explorer ---
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(8)

        controls = Card("邻居探索 / Neighbourhood")
        crow = QHBoxLayout()
        crow.addWidget(QLabel("类型"))
        self.type_combo = QComboBox()
        self.type_combo.setMinimumWidth(150)
        crow.addWidget(self.type_combo, 1)
        crow.addWidget(QLabel("深度"))
        self.depth = QSpinBox()
        self.depth.setRange(1, 3)
        self.depth.setValue(1)
        crow.addWidget(self.depth)
        self.show_btn = QPushButton("显示示例")
        self.show_btn.clicked.connect(self._show_neighbourhood)
        crow.addWidget(self.show_btn)
        controls.add_layout(crow)
        # Changing the depth re-renders the neighbourhood immediately.
        self.depth.valueChanged.connect(self._show_neighbourhood)
        self.sample_note = faint("选择类型后点击『显示示例』，查看一个实例的邻居子图（高亮为根）；"
                                 "调节深度会立即刷新。")
        controls.add(self.sample_note)
        right_lay.addWidget(controls)

        self.graph = GraphCanvas()
        right_lay.addWidget(self.graph, 1)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        self.graph.nodeSelected.connect(self._on_node)

        # show a previously parsed design if the benchmark already has one
        self.refresh_benchmarks()
        self.bench.currentIndexChanged.connect(lambda _i: self._maybe_restore())

    # ------------------------------------------------------------------ api
    def refresh_benchmarks(self):
        """Rebuild the input picker (standard + custom BLIFs), keeping selection."""
        cur = self.bench.currentData() or self.ctx.state.current_benchmark
        self.bench.blockSignals(True)
        self.bench.clear()
        for name, path, is_custom in self.ctx.state.blif_sources():
            if is_custom:
                label = "📄 %s  (自定义)" % name
            else:
                size = os.path.getsize(path) if os.path.exists(path) else 0
                label = name if size <= paths.LARGE_BLIF_BYTES else \
                    "%s (%.0f MB)" % (name, size / 1e6)
            self.bench.addItem(label, name)
            self.bench.setItemData(self.bench.count() - 1, path, Qt.ToolTipRole)
        if cur and self.bench.findData(cur) >= 0:
            self.bench.setCurrentIndex(self.bench.findData(cur))
        self.bench.blockSignals(False)
        self._maybe_restore()

    def refresh(self):
        self.refresh_benchmarks()
    def set_design(self, info):
        """Called by the window when a design parse (or a pipeline run) reports
        statistics.  A pipeline run sends stats but no graph, so the explorer
        stays disabled until the user runs『解析设计』."""
        has_graph = "graph" in info
        if has_graph:
            self._design = info
        self.tile_nodes.set_value(info["nodes"])
        self.tile_edges.set_value(info["edges"])
        self.tile_types.set_value(info["std_types"])
        self.tile_stop.set_value(info["stop_cells"], theme.WARN if info["stop_cells"] else None)
        self.hint.setText("已解析 %s：%d 单元，%d 连接。" % (
            info["benchmark"], info["nodes"], info["edges"]))
        self._fill_hist(info["type_hist"])
        self.type_combo.clear()
        for name, count in info["type_hist"]:
            self.type_combo.addItem("%s  (%d)" % (name, count), name)
        if has_graph:
            self._show_neighbourhood()
        else:
            self.sample_note.setText(
                "此统计来自流水线运行；点击『解析设计』以启用邻居探索。")
        self.set_busy(False)

    def set_busy(self, busy):
        self.parse_btn.setEnabled(not busy)
        self.parse_btn.setText("解析中…" if busy else "解析设计")

    # ------------------------------------------------------------ internals
    def _maybe_restore(self):
        name = self.bench.currentData()
        if not name:
            return
        info = self.ctx.state.designs.get(name)
        if info:
            self.set_design(info)
        else:
            self.hint.setText("点击『解析设计』以加载 %s。" % name)

    def _parse(self):
        name = self.bench.currentData()
        if not name:
            return
        # Reuse this session's cached graph when the inputs are unchanged:
        # re-parsing a benchmark (liberty + BLIF) is the slow part.
        cached = self.ctx.state.designs.get(name)
        if cached and cached.get("graph") is not None and \
                cached.get("_parse_sig"):
            blif = self.ctx.state.blif_path(name)
            lib = self.ctx.state.config.liberty()

            def _sig(p):
                try:
                    return (p, os.path.getmtime(p))
                except OSError:
                    return (p, None)

            if cached["_parse_sig"] == (_sig(blif), _sig(lib)):
                self.hint.setText("输入未变化，直接显示已解析的 %s。" % name)
                self.set_design(cached)
                return
        self.set_busy(True)
        self.hint.setText("正在解析 %s …" % name)
        self.ctx.start_design_parse(name)

    def _fill_hist(self, hist):
        ax = self.hist_chart.fresh("单元类型计数")
        top = hist[:24]
        names = [n for n, _c in top]
        vals = [c for _n, c in top]
        y = list(range(len(names)))[::-1]
        ax.barh(y, vals, color=theme.ACCENT, height=0.66)
        ax.set_yticks(y)
        ax.set_yticklabels(names, fontsize=8)
        for yi, v in zip(y, vals):
            ax.text(v, yi, " %d" % v, va="center", fontsize=8,
                    color=theme.TEXT_DIM)
        ax.set_xlim(0, max(vals + [1]) * 1.18)
        self.hist_chart.draw_now()

    def _show_neighbourhood(self):
        if not self._design:
            return
        type_name = self.type_combo.currentData()
        if not type_name:
            return
        depth = self.depth.value()
        graph = self._design["graph"]
        cells = self._design["cells"]

        root_id = None
        for i, cell in enumerate(cells):
            if cell.stdCellType.typeName == type_name:
                root_id = cell.id
                break
        if root_id is None:
            self.graph.clear()
            return

        # BFS over predecessors/successors up to depth.  The frontier must be
        # the nodes discovered *this* layer only (unioning it into `keep`
        # before computing the next frontier would always empty it), and the
        # collection is capped so one dense layer cannot flood the canvas.
        keep = {root_id}
        frontier = {root_id}
        for _d in range(depth):
            nxt = set()
            for node in frontier:
                for nb in graph.successors(node):
                    if nb not in keep and len(keep) + len(nxt) < MAX_NEIGHBOURHOOD:
                        nxt.add(nb)
                for nb in graph.predecessors(node):
                    if nb not in keep and len(keep) + len(nxt) < MAX_NEIGHBOURHOOD:
                        nxt.add(nb)
                if len(keep) + len(nxt) >= MAX_NEIGHBOURHOOD:
                    break
            if not nxt:
                break
            keep |= nxt
            frontier = nxt
            if len(keep) >= MAX_NEIGHBOURHOOD:
                break
        sub = graph.subgraph(sorted(keep)).copy()
        self.graph.set_graph(
            sub, highlight={root_id},
            title="%s 的一个实例（%d/%d 节点，深度 %d）"
                  % (type_name, sub.number_of_nodes(), graph.number_of_nodes(), depth))
        self.sample_note.setText(
            "高亮的是 %s 的一个实例；共显示 %d 个邻居节点。" % (type_name,
                                                             sub.number_of_nodes()))

    def _on_node(self, node):
        if not self._design:
            return
        data = self._design["graph"].nodes[node]
        self.sample_note.setText("节点 %s · 类型 %s · 实例 %s"
                                 % (node, data.get("type", "?"),
                                    data.get("name", "?")))
