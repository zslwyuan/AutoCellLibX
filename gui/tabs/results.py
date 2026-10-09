"""Results tab: the area story -- per-pattern and design-level savings."""
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QSplitter, QTabWidget,
                               QVBoxLayout, QWidget)

from .. import artifacts, paths, theme
from ..widgets.chart import MplCanvas
from ..widgets.common import (Card, KeyValue, StatTile, faint, h1, subtle)
from ..widgets.guide import GuidePanel
from ..widgets.log_view import LogView


class ResultsTab(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        bar = QHBoxLayout()
        bar.addWidget(h1("结果 / Results"))
        bar.addStretch(1)
        bar.addWidget(QLabel("基准"))
        self.bench = QComboBox()
        self.bench.setMinimumWidth(130)
        self.bench.currentTextChanged.connect(self._on_bench)
        bar.addWidget(self.bench)
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.refresh)
        bar.addWidget(self.refresh_btn)
        root.addLayout(bar)

        self.guide = GuidePanel([
            ("这一页讲什么", "流程在网表里挖掘『反复出现的子电路』（模式），把每个模式合并成一个"
             "复杂单元（COMPLEX*），并用 ASTRAN 自动生成晶体管级版图。因为一个复杂单元顶替了原先"
             "并排的多个标准单元，面积变小 —— 本页就是这份面积账的汇总与明细。"),
            ("顶部六个数字", "① 最佳节省 (ASTRAN)：全部入选模式的『单位节省 × 出现次数』之和"
             "（µm）；② 节省率 = ① ÷ 整个设计原先的总宽；③④ 换用 GSCL 库的 LEF 标称宽度作基准"
             "重复同样的计算；⑤ 挖掘用时：整个流程的墙钟时间；⑥ 复杂单元：生成了版图并计入的模式数。"),
            ("读第一图", "对每个模式：灰色柱子 = 组成它的原始单元一个个并排的总宽度，蓝色 = 合并成"
             "一个复杂单元后的宽度。柱顶数字是『合并 − 并排』，为负才是节省；红色 = 合并后反而更宽，"
             "说明该模式不划算，不会计入任何节省数字。"),
            ("读第二图", "每个模式的累计收益 = 单位节省 × 它在全设计里出现的次数（柱顶第一行，µm）；"
             "第二行是相对该模式原始总宽的节省率。红色柱 = 负收益（该模式合并后更宽）。"),
            ("读第三图", "把设计里所有入选模式的节省加总：橙色 = 相对 ASTRAN 基线，青色 = 相对 GSCL "
             "标称宽度。两个基准口径不同，数值不必相等，各自与同基准的节省率一起看才有意义。"),
            ("看原文", "底部两个标签页是流程写出的第一手记录：bestRecord（设计级汇总）与 "
             "bestRecord-seperate（逐模式明细）。逐行格式见本页『如何读记录文件』卡片。"),
            ("口径", "面积用『宽度』做代理：行高固定时 面积 ∝ 宽度。所有对比都在同一行高（默认 "
             "2.47 µm，GSCL45 CoreSite）下进行；跨工具链版本的数字会变，勿跨版本比较。"),
        ])
        root.addWidget(self.guide)
        root.addWidget(subtle(
            "阅读顺序：① 顶部六个数字看整体结论；② 第一图看每个模式的单位节省是怎么来的；"
            "③ 第二图看每个模式在全设计里累计省了多少；④ 第三图看设计级总额；"
            "⑤ 底部原文核对第一手数据。所有宽度单位均为 µm（行高固定，宽度即面积代理）。"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        container = QWidget()
        scroll.setWidget(container)
        root.addWidget(scroll, 1)
        body = QVBoxLayout(container)
        body.setSpacing(12)

        # --- summary tiles ---
        tiles_card = Card("设计级节省 / Design-level savings")
        self.tiles = QGridLayout()
        self.tiles.setSpacing(10)
        self.tile_best = StatTile("最佳节省 (ASTRAN)", "--",
                                  "相对 ASTRAN 基线的总节省 (µm)")
        self.tile_ratio_a = StatTile("节省率 (ASTRAN)", "--",
                                     "节省 ÷ 设计原总宽")
        self.tile_best_g = StatTile("最佳节省 (GSCL)", "--",
                                    "相对 GSCL LEF 标称宽度的总节省 (µm)")
        self.tile_ratio_g = StatTile("节省率 (GSCL)", "--",
                                     "节省 ÷ 设计原总宽")
        self.tile_runtime = StatTile("挖掘用时", "--",
                                     "模式挖掘 + 版图生成，墙钟时间")
        self.tile_patterns = StatTile("复杂单元", "--", "生成了版图的模式数")
        for i, t in enumerate((self.tile_best, self.tile_ratio_a,
                               self.tile_best_g, self.tile_ratio_g,
                               self.tile_runtime, self.tile_patterns)):
            self.tiles.addWidget(t, 0, i)
        tiles_card.add_layout(self.tiles)
        tiles_card.add(faint(
            "怎么算：单位节省 = 并排宽度和 − 合并宽度；模式总节省 = 单位节省 × 出现次数；"
            "设计级节省 = 全部入选模式总节省之和；节省率 = 设计级节省 ÷ 设计原总宽。"
            "两个基准口径不同：ASTRAN 基线是同一版图工具在相同行高下生成的原始单元（同口径比较），"
            "GSCL 是库 LEF 里的标称参考宽度（业界习惯口径）。"))
        body.addWidget(tiles_card)

        # --- charts ---
        charts = QGridLayout()
        charts.setSpacing(12)
        charts.setRowStretch(0, 1)
        charts.setColumnStretch(0, 1)
        charts.setColumnStretch(1, 1)
        body.addLayout(charts)

        self.width_chart_card = Card("为什么省面积：并排 vs 合并 / Width comparison")
        self.width_chart = MplCanvas(height=3.2)
        self.width_chart_card.add(self.width_chart)
        self.width_chart_card.add(faint(
            "灰色 = 原始单元逐个并排的总宽度；蓝色 = 合并成一个复杂单元后的宽度。"
            "柱顶数字 = 蓝色 − 灰色（负数才是节省，红色 = 合并反而更宽）。"
            "『并排』宽度 = 组成该模式的每个原始单元在 ASTRAN 基线中的宽度之和。"))
        charts.addWidget(self.width_chart_card, 0, 0)

        self.save_chart_card = Card("每模式节省 / Per-pattern savings")
        self.save_chart = MplCanvas(height=3.2)
        self.save_chart_card.add(self.save_chart)
        self.save_chart_card.add(faint(
            "总节省 = (并排宽 − 合并宽) × 出现次数，覆盖该模式在整个设计中的所有出现位置；"
            "柱顶第一行为总节省 (µm)，第二行为节省率 = 单位节省 ÷ 并排宽度和。"
            "出现次数越多，同一单位节省的累计收益越大。"))
        charts.addWidget(self.save_chart_card, 0, 1)

        self.design_chart_card = Card("设计面积构成 / Design area breakdown")
        self.design_chart = MplCanvas(height=2.6)
        self.design_chart_card.add(self.design_chart)
        self.design_chart_card.add(faint(
            "设计级节省 = Σ(模式总节省)。ASTRAN 基准（版图合成结果）与 GSCL 基准（库 LEF 标称宽度）"
            "口径不同，数值不必相等；请把每个数值与同基准的节省率（括号内百分比）配对阅读。"))
        body.addWidget(self.design_chart_card)

        # --- glossary ---
        gloss = Card("术语表 / Glossary")
        kv = KeyValue()
        for term, meaning in [
            ("模式 pattern", "网表中反复出现的子电路：相同的单元类型以相同的连接方式组成。"),
            ("复杂单元 COMPLEX*", "把一个模式合并成的单个标准单元（COMPLEX0、COMPLEX1…）。"
             "编号每次运行重新分配，不代表固定的模式对应关系。"),
            ("出现次数 clusters", "该模式在整个设计中被匹配到的位置数（一个模式的全部出现实例）。"),
            ("覆盖 coverage", "模式大小 × 出现次数，即该模式占用的单元总数；"
             "覆盖率 = 覆盖 ÷ 设计总单元数，是模式是否值得合成的门槛之一。"),
            ("模式码 pattern code", "模式连接结构的编码串（pattern_extension_trace），"
             "是模式的唯一身份；同一模式在多次运行中会拿到不同的 COMPLEX 编号，但模式码不变。"),
            ("ASTRAN 基线", "用同一版图工具、在相同行高与工艺参数下为原始标准单元生成的版图宽度 —— "
             "与复杂单元同口径，是节省计算的主要基准。"),
            ("GSCL 基准", "GSCL45 库 LEF 中标称单元的宽度，业界参考口径；"
             "与 ASTRAN 基线数值不同，勿混用。"),
            ("并排宽度 / 合并宽度", "并排 = 模式内原始单元宽度之和（未合并）；"
             "合并 = 复杂单元版图的实际宽度。"),
            ("单位节省 / 总节省", "单位节省 = 并排宽 − 合并宽（一个出现位置省下的宽度）；"
             "总节省 = 单位节省 × 出现次数（全设计累计）。"),
            ("节省率", "节省 ÷ 对比基准总宽的百分比（ASTRAN 或 GSCL 两个口径）。"),
            ("0×0 排除", "版图合成失败（LP 求解无解或超时）的单元宽度为 0，"
             "该模式会被排除，不计入任何数字 —— 日志里可见『zero width; excluded』。"),
        ]:
            kv.add(term, meaning)
        gloss.add(kv)
        body.addWidget(gloss)

        # --- raw records ---
        self.record_card = Card("bestRecord 文件 / Raw records")
        self.record_card.add(faint(
            "bestRecord-<基准>：第 1 行 = 相对 ASTRAN 基准的总节省 (µm)，第 2 行 = 对应节省率 (%)；"
            "第 3、4 行是相对 GSCL 基准的同样两个数；随后每行一个入选模式："
            "(名称, 出现次数, 模式大小, 模式码)；末尾 runtime 为流程总用时。"
            "bestRecord-seperate-<基准>：每个模式一行，按节省降序："
            "设计总面积 | 节省 | 节省率 | 出现次数 | 大小 | 覆盖 | 名称 | 模式码。"))
        self.record_tabs = QTabWidget()
        self.best_text = _text_area()
        self.separate_text = _text_area()
        self.record_tabs.addTab(self.best_text, "bestRecord")
        self.record_tabs.addTab(self.separate_text, "bestRecord-seperate")
        self.record_card.add(self.record_tabs)
        body.addWidget(self.record_card)

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
        best = self.ctx.state.best_record(bench)
        separate = self.ctx.state.separate_record(bench)
        baseline = artifacts.load_baseline_widths(paths.ORIGINAL_CELLS_DIR)

        # collect per-pattern rows
        session = {p["name"]: p for p in self.ctx.state.patterns.get(bench, [])}
        sep_by_name = {r.name: r for r in separate}
        rows = []
        for cell in artifacts.scan_output_dir(out_dir):
            log = artifacts.parse_astran_log(cell.log_path)
            sp = artifacts.read_spice_netlist(cell.sp_path)
            name = cell.name
            sinfo = session.get(name, {})
            srow = sep_by_name.get(name)
            trace = sinfo.get("trace") or sp.pattern_code
            width = log.width_um if log.complete else sinfo.get("width_um")
            orig = (sinfo.get("orig_width_um") or
                    artifacts.pattern_original_width(trace, baseline))
            occ = sp.occurrences if sp.occurrences is not None \
                else sinfo.get("clusters")
            save_total = None
            if srow:
                save_total = srow.save_area
            elif orig is not None and width and occ:
                save_total = (orig - width) * occ
            rows.append({"name": name, "trace": trace, "width": width,
                         "orig": orig, "occ": occ, "save": save_total,
                         "ratio": srow.save_ratio if srow else None})
        rows.sort(key=lambda r: -(r["save"] or 0))

        self._fill_tiles(best, rows)
        self._draw_width_chart(rows)
        self._draw_save_chart(rows)
        self._draw_design_chart(best, rows)
        self._fill_records(best, separate)

    def _fill_tiles(self, best, rows):
        if best.exists:
            if best.save_area_astran is not None:
                self.tile_best.set_value("%.1f µm" % best.save_area_astran, theme.OK)
                self.tile_ratio_a.set_value("%.2f%%" % (best.save_ratio_astran or 0),
                                            theme.OK)
            if best.save_area_gscl is not None:
                self.tile_best_g.set_value("%.1f µm" % best.save_area_gscl, theme.OK)
                self.tile_ratio_g.set_value("%.2f%%" % (best.save_ratio_gscl or 0),
                                            theme.OK)
            if best.runtime_s:
                self.tile_runtime.set_value("%.1f s" % best.runtime_s)
        else:
            for t in (self.tile_best, self.tile_ratio_a, self.tile_best_g,
                      self.tile_ratio_g, self.tile_runtime):
                t.set_value("--")
        self.tile_patterns.set_value(len(rows))

    # ---------------------------------------------------------------- charts
    def _draw_width_chart(self, rows):
        ax = self.width_chart.fresh("每个模式：并排宽度 vs 合并宽度 (µm)")
        usable = [r for r in rows if r["orig"] and r["width"]]
        if not usable:
            self.width_chart.draw_now()
            return
        names = [r["name"] for r in usable]
        x = list(range(len(names)))
        w = 0.4
        ax.bar([i - w / 2 for i in x], [r["orig"] for r in usable], w,
               label="并排 (原始单元宽度和)", color=theme.TEXT_DIM)
        ax.bar([i + w / 2 for i in x], [r["width"] for r in usable], w,
               label="合并 (复杂单元宽度)", color=theme.ACCENT)
        for i, r in enumerate(usable):
            save = r["orig"] - r["width"]
            ax.text(i, max(r["orig"], r["width"]), "%+.2f" % (-save),
                    ha="center", va="bottom", fontsize=8,
                    color=theme.OK if save > 0 else theme.ERROR)
        ax.set_xticks(x)
        ax.set_xticklabels(names, rotation=20, ha="right")
        ax.set_ylabel("宽度 µm")
        leg = ax.legend(frameon=False, fontsize=8, loc="upper right")
        for t in leg.get_texts():
            t.set_color(theme.TEXT_DIM)
        self.width_chart.draw_now()

    def _draw_save_chart(self, rows):
        ax = self.save_chart.fresh("每模式总节省 (µm) 与节省率")
        usable = [r for r in rows if r["save"] is not None]
        if not usable:
            self.save_chart.draw_now()
            return
        names = [r["name"] for r in usable]
        x = list(range(len(names)))
        colours = [theme.OK if (r["save"] or 0) > 0 else theme.ERROR for r in usable]
        ax.bar(x, [r["save"] for r in usable], 0.62, color=colours)
        for i, r in enumerate(usable):
            label = "%.1f" % r["save"]
            if r["ratio"] is not None:
                label += "\n%.1f%%" % r["ratio"]
            ax.text(i, r["save"], label, ha="center",
                    va="bottom" if r["save"] >= 0 else "top", fontsize=8,
                    color=colours[i])
        ax.axhline(0, color=theme.TEXT_FAINT, lw=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels(names, rotation=20, ha="right")
        ax.set_ylabel("节省 µm")
        self.save_chart.draw_now()

    def _draw_design_chart(self, best, rows):
        ax = self.design_chart.fresh("设计面积构成（宽度总量，µm）")
        if not best.exists or best.save_area_astran is None:
            self.design_chart.draw_now()
            return
        # ASTRAN baseline total = saved + kept; GSCL shown for reference.
        saved_a = best.save_area_astran or 0
        saved_g = best.save_area_gscl or 0
        cats = ["节省 (ASTRAN)", "节省 (GSCL)"]
        vals = [saved_a, saved_g]
        colours = [theme.ACCENT, theme.INFO]
        b = ax.barh(cats, vals, color=colours, height=0.55)
        for rect, v, r in zip(b, vals,
                              [best.save_ratio_astran, best.save_ratio_gscl]):
            ax.text(rect.get_width(), rect.get_y() + rect.get_height() / 2,
                    "  %.1f µm  (%.2f%%)" % (v, r or 0), va="center",
                    color=theme.TEXT_DIM, fontsize=9)
        ax.set_xlim(0, max(vals + [1]) * 1.35)
        ax.set_ylabel("")
        self.design_chart.draw_now()

    def _fill_records(self, best, separate):
        if best.exists and os.path.exists(best.path):
            self.best_text.setPlainText(open(best.path, errors="replace").read())
        else:
            self.best_text.setPlainText("（尚无 bestRecord；运行流程后生成）")
        lines = [r.as_row() for r in separate]
        if lines:
            header = ["名称", "节省", "节省率", "出现", "大小", "覆盖", "模式码"]
            self.separate_text.setPlainText(
                "\t".join(header) + "\n" + "\n".join("\t".join(l) for l in lines))
        else:
            self.separate_text.setPlainText(
                "（尚无逐模式明细；开启 phase 2 并运行后生成）")

    def add_record(self, info):
        if info.get("benchmark") == (self.bench.currentText() or
                                     self.ctx.state.current_benchmark):
            self.refresh()


def _text_area():
    from PySide6.QtWidgets import QPlainTextEdit
    w = QPlainTextEdit()
    w.setReadOnly(True)
    w.setMinimumHeight(150)
    return w
