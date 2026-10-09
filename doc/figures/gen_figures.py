# -*- coding: utf-8 -*-
"""Generate the figures for doc/ALGORITHM_DESIGN.md.

Run:  python doc/figures/gen_figures.py
Output: doc/figures/*.png

Pure matplotlib (no graphviz). All diagrams are hand-laid-out so they render
identically everywhere. Chinese text uses Microsoft YaHei / SimHei.
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle, Circle, Polygon
from matplotlib.lines import Line2D

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DengXian"]
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["axes.unicode_minus"] = False

OUT = os.path.dirname(os.path.abspath(__file__))

# ---- palette --------------------------------------------------------------
C_FRONT = "#DCE9F7"   # front-end (python) fill
E_FRONT = "#2E6DB4"
C_BACK = "#FCE3C8"    # back-end (ASTRAN) fill
E_BACK = "#C77414"
C_SOLV = "#EAD9F7"    # solver fill
E_SOLV = "#6A4D8A"
C_IO = "#E4F2DA"      # inputs / outputs fill
E_IO = "#4E8A3C"
C_DATA = "#F2F2F2"    # data / file fill
E_DATA = "#7A7A7A"
C_DEC = "#FFF3C4"     # decision fill
E_DEC = "#B58A00"
C_OK = "#D9F2D9"
C_BAD = "#F6D5D5"
TXT = "#1A1A1A"


def newfig(w, h, xlim=None, ylim=None):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, xlim if xlim else w)
    ax.set_ylim(0, ylim if ylim else h)
    ax.axis("off")
    return fig, ax


def rbox(ax, cx, cy, w, h, text, fc=C_FRONT, ec=E_FRONT, fs=11, tc=TXT,
         bold=False, style="round,pad=0.02,rounding_size=0.12", lw=1.6):
    box = FancyBboxPatch((cx - w / 2, cy - h / 2), w, h,
                         boxstyle=style, linewidth=lw,
                         edgecolor=ec, facecolor=fc, mutation_aspect=1)
    ax.add_patch(box)
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs, color=tc,
            weight=("bold" if bold else "normal"), linespacing=1.25)
    return box


def diamond(ax, cx, cy, w, h, text, fc=C_DEC, ec=E_DEC, fs=10.5):
    pts = [(cx, cy + h / 2), (cx + w / 2, cy), (cx, cy - h / 2), (cx - w / 2, cy)]
    ax.add_patch(Polygon(pts, closed=True, facecolor=fc, edgecolor=ec, lw=1.6))
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs, color=TXT,
            linespacing=1.2)


def txt(ax, x, y, s, fs=10, color=TXT, ha="center", va="center", bold=False,
        rot=0, style=None):
    ax.text(x, y, s, ha=ha, va=va, fontsize=fs, color=color,
            weight=("bold" if bold else "normal"), rotation=rot,
            linespacing=1.25, fontstyle=(style or "normal"))


def arr(ax, p1, p2, text=None, color="#333333", lw=1.8, fs=9.5, toff=(0, 0.18),
        style="-|>", cs="arc3,rad=0.0", ms=16):
    a = FancyArrowPatch(p1, p2, arrowstyle=style, mutation_scale=ms,
                        lw=lw, color=color, connectionstyle=cs,
                        shrinkA=2, shrinkB=2, zorder=1)
    ax.add_patch(a)
    if text:
        mx, my = (p1[0] + p2[0]) / 2 + toff[0], (p1[1] + p2[1]) / 2 + toff[1]
        ax.text(mx, my, text, ha="center", va="center", fontsize=fs,
                color="#222", bbox=dict(boxstyle="round,pad=0.15", fc="white",
                                        ec="none", alpha=0.85))


def elbow(ax, pts, color="#333333", lw=1.8, ms=16):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    ax.plot(xs[:-1], ys[:-1], color=color, lw=lw, zorder=1,
            solid_capstyle="round")
    a = FancyArrowPatch(pts[-2], pts[-1], arrowstyle="-|>", mutation_scale=ms,
                        lw=lw, color=color, shrinkA=0, shrinkB=0, zorder=1)
    ax.add_patch(a)


def title(ax, x, y, s, fs=13):
    ax.text(x, y, s, ha="left", va="top", fontsize=fs, weight="bold", color=TXT)


def save(fig, name):
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor="white",
                pad_inches=0.12)
    plt.close(fig)
    print("wrote", name)


# ===========================================================================
# F1  系统总览（端到端）
# ===========================================================================
def f1():
    fig, ax = newfig(16, 8)
    # zone backgrounds
    ax.add_patch(Rectangle((0.2, 0.4), 3.3, 7.2, fc="#F7FAF2", ec=E_IO, lw=1.4, zorder=0))
    ax.add_patch(Rectangle((3.8, 0.4), 6.2, 7.2, fc="#F4F8FD", ec=E_FRONT, lw=1.4, zorder=0))
    ax.add_patch(Rectangle((10.2, 0.4), 3.3, 7.2, fc="#FDF6EE", ec=E_BACK, lw=1.4, zorder=0))
    ax.add_patch(Rectangle((13.7, 0.4), 2.1, 7.2, fc="#F7FAF2", ec=E_IO, lw=1.4, zorder=0))
    txt(ax, 1.85, 7.35, "输入", 12, E_IO, bold=True)
    txt(ax, 6.9, 7.35, "AutoCellLibX 前端（Python / flow）", 12, E_FRONT, bold=True)
    txt(ax, 11.85, 7.35, "ASTRAN 后端（C++）", 12, E_BACK, bold=True)
    txt(ax, 14.75, 7.35, "输出", 12, E_IO, bold=True)

    # inputs
    rbox(ax, 1.85, 6.2, 2.9, 1.0, "门级网表\nbenchmark/blif/*.blif\n(Yosys 技术映射后)", C_IO, E_IO, 9.5)
    rbox(ax, 1.85, 4.9, 2.9, 0.9, "时序库\ngscl45nm.lib", C_IO, E_IO, 9.5)
    rbox(ax, 1.85, 3.7, 2.9, 0.9, "单元晶体管级网表\ncellsAstranFriendly.sp", C_IO, E_IO, 9.0)
    rbox(ax, 1.85, 2.5, 2.9, 0.9, "原始单元 GDS/LEF\noriginal_gscl45_cells", C_IO, E_IO, 9.0)

    # front-end stages (vertical loop)
    rbox(ax, 6.9, 6.3, 5.4, 0.95, "① 解析与构图  (BLIFPreProc)\nliberty+BLIF → DesignCell/DesignNet → 有向图", C_FRONT, E_FRONT, 9.5)
    rbox(ax, 6.9, 5.2, 5.4, 0.9, "② 模式种子挖掘\n深度受限树编码 → 频次聚类", C_FRONT, E_FRONT, 9.5)
    rbox(ax, 6.9, 4.1, 5.4, 0.9, "③ 模式生长  (BLIFPatternGrowth)\n吸收同特征邻居，扩展 pattern_extension_trace", C_FRONT, E_FRONT, 9.5)
    rbox(ax, 6.9, 3.0, 5.4, 0.9, "④ 候选评估与组合  (main.py)\n(save_area = Σ(原宽−新宽)×出现次数)", C_FRONT, E_FRONT, 9.0)
    rbox(ax, 6.9, 1.9, 5.4, 0.85, "⑤ SPICE 导出  (spice.py)\n合并子电路 → COMPLEX<n>.sp", C_FRONT, E_FRONT, 9.5)

    # back-end
    rbox(ax, 11.85, 4.6, 3.0, 1.5, "cellgen autoflow\n折叠→布局→布线\n→ILP 压缩", C_BACK, E_BACK, 10, bold=True)
    rbox(ax, 11.85, 2.6, 3.0, 1.0, "LP 求解器\ngurobi_cl.cmd →\npython-mip + CBC", C_SOLV, E_SOLV, 9.5)

    # outputs
    rbox(ax, 14.75, 5.6, 1.9, 0.9, "COMPLEX<n>.gds\n晶体管级版图", C_IO, E_IO, 9.0)
    rbox(ax, 14.75, 4.4, 1.9, 0.8, "COMPLEX<n>.sp\n/ .png", C_IO, E_IO, 9.0)
    rbox(ax, 14.75, 3.2, 1.9, 0.9, "bestRecord-*\n面积节省记录", C_IO, E_IO, 9.0)

    # arrows inputs -> frontend
    for y in (6.2, 4.9, 3.7):
        arr(ax, (3.3, y), (4.2, 6.3), color=E_IO, lw=1.5)
    arr(ax, (3.3, 2.5), (4.2, 6.3), color=E_IO, lw=1.5, cs="arc3,rad=0.1")
    # frontend vertical
    for y0, y1 in [(5.82, 5.65), (4.75, 4.55), (3.65, 3.45), (2.55, 2.32)]:
        arr(ax, (6.9, y0), (6.9, y1), color=E_FRONT, lw=1.6)
    # loop back from ④ to ③ (growth feeds combination)
    elbow(ax, [(9.6, 3.0), (9.95, 3.0), (9.95, 4.1), (9.6, 4.1)], color=E_FRONT, lw=1.4)
    txt(ax, 10.05, 3.55, "生长新\n模式入池", 8, E_FRONT, ha="left")
    # frontend ⑤ -> astran
    arr(ax, (9.6, 1.9), (10.2, 4.3), "COMPLEX.sp\n+ .run 脚本", color=E_BACK, lw=1.8, toff=(-0.4, 0.2))
    # astran <-> solver
    arr(ax, (11.2, 3.85), (11.2, 3.1), "ILPmodel.lp", color=E_SOLV, lw=1.5, toff=(0.8, 0))
    arr(ax, (12.5, 3.1), (12.5, 3.85), "ILPmodel.sol", color=E_SOLV, lw=1.5, toff=(0.85, 0))
    # astran -> gds output
    arr(ax, (13.35, 4.6), (13.8, 5.4), color=E_BACK, lw=1.8)
    # frontend -> records output
    elbow(ax, [(9.6, 1.9), (10.0, 1.9), (10.0, 3.2), (13.8, 3.2)], color=E_FRONT, lw=1.3)
    arr(ax, (13.8, 4.4), (12.9, 1.9), "", color=E_FRONT, lw=0)  # dummy no
    save(fig, "sys_overview.png")


# ===========================================================================
# F2  前端算法流程（main.py 主循环）
# ===========================================================================
def f2():
    fig, ax = newfig(10.5, 12)
    cx = 5.25
    rbox(ax, cx, 11.4, 8.6, 0.8, "加载 liberty + BLIF + 单元 SPICE；构建有向图与初始模式簇", C_IO, E_IO, 10.5)
    rbox(ax, cx, 10.3, 8.6, 0.75, "sort_pattern_cluster_seqs：按 簇数×簇大小 降序排列", C_FRONT, E_FRONT, 10)
    rbox(ax, cx, 9.35, 7.6, 0.7, "外层循环 i = 0 … top_thr-1（top_thr=5）", C_FRONT, E_FRONT, 10, bold=True)

    # inner block
    ax.add_patch(Rectangle((1.3, 4.4), 7.9, 4.2, fc="#F4F8FD", ec=E_FRONT, lw=1.2, ls="--", zorder=0))
    txt(ax, 5.25, 8.35, "内层循环 j：考察排序后的前 top_thr 个模式序列", 9.5, E_FRONT)

    rbox(ax, cx, 7.7, 7.2, 0.6, "取候选模式；按 pattern_extension_trace 去重", C_FRONT, E_FRONT, 9.5)
    diamond(ax, cx, 6.75, 4.4, 1.1, "簇大小<11 且\n覆盖率达标？\n(ratio_thr/cnt_thr)")
    rbox(ax, cx, 5.55, 7.2, 0.75, "画模式子图 PNG；导出 COMPLEX.sp；调用 ASTRAN 生成版图", C_FRONT, E_FRONT, 9.5)
    diamond(ax, cx, 4.8, 4.6, 0.95, "版图有效？\n(宽度 > 0)")

    rbox(ax, cx, 3.7, 8.2, 0.8, "累加 save_area = (原单元宽度和 − COMPLEX 宽度) × 簇数", C_FRONT, E_FRONT, 10)

    diamond(ax, cx, 2.55, 4.6, 1.05, "本轮 save_area >\n历史最佳？")

    rbox(ax, 2.5, 1.2, 4.0, 0.85, "是：写 bestRecord-基准名\n（最佳组合）", C_OK, E_IO, 9.5)
    rbox(ax, 8.1, 1.2, 3.6, 0.85, "否：停止扩展\n该基准", C_BAD, "#B03030", 9.5)
    rbox(ax, cx, 0.35, 8.6, 0.6, "grow_sequence_of_clusters：生长 top1 模式 → 新模式回池 → 重排 → 下一轮", C_FRONT, E_FRONT, 9.0)

    # arrows
    arr(ax, (cx, 11.0), (cx, 10.68), color=E_IO)
    arr(ax, (cx, 9.92), (cx, 9.7), color=E_FRONT)
    arr(ax, (cx, 9.0), (cx, 8.05), color=E_FRONT)
    arr(ax, (cx, 7.4), (cx, 7.28), color=E_FRONT)
    arr(ax, (cx, 6.2), (cx, 5.95), "是", color=E_FRONT, toff=(0.4, 0.1))
    arr(ax, (1.05, 6.75), (0.6, 6.75), "", color=E_FRONT)  # placeholder
    # no-branch of diamond1 -> skip to next j (right side up)
    elbow(ax, [(7.45, 6.75), (9.0, 6.75), (9.0, 8.1), (9.2, 8.1)], color="#888", lw=1.2)
    txt(ax, 9.0, 7.4, "否：跳过", 8.5, "#666", rot=90)
    arr(ax, (cx, 5.17), (cx, 5.28+0.0), "", color=E_FRONT)
    arr(ax, (cx, 4.32), (cx, 4.12), "是", color=E_FRONT, toff=(0.4, 0.05))
    elbow(ax, [(7.55, 4.8), (8.9, 4.8), (8.9, 5.55), (8.85, 5.55)], color="#888", lw=1.2)
    txt(ax, 8.95, 5.15, "否：排除该模式", 8.5, "#666", rot=90)
    arr(ax, (cx, 3.3), (cx, 3.1), color=E_FRONT)
    arr(ax, (3.0, 2.05), (2.7, 1.62), "是", color=E_IO, toff=(-0.3, 0.1))
    arr(ax, (7.5, 2.05), (7.9, 1.62), "否", color="#B03030", toff=(0.3, 0.1))
    # loop back from bottom to inner loop
    elbow(ax, [(1.0, 0.35), (0.6, 0.35), (0.6, 7.7), (1.5, 7.7)], color=E_FRONT, lw=1.4)
    txt(ax, 0.5, 4.0, "继续下一轮", 8.5, E_FRONT, rot=90)
    save(fig, "frontend_pipeline.png")


# ===========================================================================
# F3  门级图建模 + 树编码
# ===========================================================================
def f3():
    fig, ax = newfig(13, 6.2)
    title(ax, 0.2, 6.0, "左：一段门级网表（逻辑门 + 互连）          右：映射成的有向图（节点=单元实例，边=驱动→负载）", 12)

    # left: gates
    def gate(x, y, label, fc):
        rbox(ax, x, y, 1.7, 0.9, label, fc, E_DATA, 10, bold=True, style="round,pad=0.02,rounding_size=0.1")
    gate(1.2, 4.6, "NAND2X1", "#E8F0FB")
    gate(1.2, 3.1, "NAND2X1", "#E8F0FB")
    gate(3.4, 3.85, "OR2X1", "#FDEEDA")
    gate(5.4, 3.85, "XNOR2X1", "#EFE3F7")
    # wires
    arr(ax, (2.05, 4.6), (2.55, 4.05), color="#555", lw=1.4)
    arr(ax, (2.05, 3.1), (2.55, 3.65), color="#555", lw=1.4)
    arr(ax, (4.25, 3.85), (4.55, 3.85), color="#555", lw=1.4)
    txt(ax, 3.0, 4.35, "net a", 8, "#666")
    txt(ax, 3.0, 3.35, "net b", 8, "#666")
    txt(ax, 4.4, 4.1, "net c", 8, "#666")

    # right: digraph nodes
    def node(x, y, label, fc, ec):
        c = Circle((x, y), 0.42, fc=fc, ec=ec, lw=1.6, zorder=3)
        ax.add_patch(c)
        txt(ax, x, y, label, 9, TXT, bold=True)
    node(8.0, 4.9, "NAND2", "#E8F0FB", E_FRONT)
    node(8.0, 3.0, "NAND2", "#E8F0FB", E_FRONT)
    node(10.0, 4.0, "OR2", "#FDEEDA", E_BACK)
    node(12.0, 4.0, "XNOR2", "#EFE3F7", E_SOLV)
    arr(ax, (8.4, 4.75), (9.62, 4.2), color="#333", lw=1.6)
    arr(ax, (8.4, 3.2), (9.62, 3.85), color="#333", lw=1.6)
    arr(ax, (10.42, 4.0), (11.58, 4.0), color="#333", lw=1.6)

    # encoding callout
    ax.add_patch(Rectangle((7.0, 0.5), 5.6, 1.7, fc="#FFFDF4", ec=E_DEC, lw=1.3))
    txt(ax, 9.8, 2.0, "深度受限树编码（以 OR2 为根，depth=1）", 10, E_DEC, bold=True)
    txt(ax, 9.8, 1.35, "反向收集前驱：NAND2、NAND2，加上根 OR2\n编码串 = “[NAND2X1, NAND2X1, OR2X1]”", 9.5, TXT)
    save(fig, "graph_model.png")


# ===========================================================================
# F4  模式种子挖掘 → 聚类
# ===========================================================================
def f4():
    fig, ax = newfig(13, 6.5)
    title(ax, 0.2, 6.3, "在整个设计图里，所有结构同构的子图被同一编码串识别出来，聚成一个“模式簇序列”", 12)
    # big design area
    ax.add_patch(Rectangle((0.3, 0.6), 7.4, 5.2, fc="#FBFCFE", ec="#B9C6D6", lw=1.2))
    txt(ax, 4.0, 5.5, "设计有向图（数百~数万单元）", 10, "#5A6B7F")

    # three isomorphic mini-subgraphs
    def mini(x, y, scale=1.0):
        n1 = (x, y + 0.55 * scale); n2 = (x, y - 0.55 * scale); n3 = (x + 0.95 * scale, y)
        for (nx_, ny_) in (n1, n2, n3):
            ax.add_patch(Circle((nx_, ny_), 0.2 * scale, fc="#E8F0FB", ec=E_FRONT, lw=1.3, zorder=3))
        arr(ax, (x + 0.18 * scale, y + 0.5 * scale), (x + 0.78 * scale, y + 0.08 * scale), color="#333", lw=1.0)
        arr(ax, (x + 0.18 * scale, y - 0.5 * scale), (x + 0.78 * scale, y - 0.08 * scale), color="#333", lw=1.0)
        # dashed highlight
        ax.add_patch(Rectangle((x - 0.35 * scale, y - 0.85 * scale), 1.6 * scale, 1.7 * scale,
                               fc="none", ec="#D43A2F", lw=1.6, ls=(0, (4, 3)), zorder=2))
    mini(1.6, 4.3); mini(3.6, 2.6); mini(5.6, 4.4)
    # some background dots
    import random
    random.seed(3)
    for _ in range(26):
        x = random.uniform(0.8, 7.2); y = random.uniform(1.0, 5.0)
        ax.add_patch(Circle((x, y), 0.07, fc="#C9D4E2", ec="none", zorder=1))

    # arrow to cluster box
    arr(ax, (7.7, 3.2), (8.6, 3.2), "同一编码\n[NAND2X1,NAND2X1,OR2X1]", color="#333", lw=1.6, toff=(0, 0.5))
    rbox(ax, 10.7, 3.9, 4.0, 1.0, "DesignPatternClusterSeq\n（同构子图的集合）", C_FRONT, E_FRONT, 10.5, bold=True)
    rbox(ax, 10.7, 2.4, 4.0, 1.0, "簇数 = 出现次数\n簇大小 = 3 个单元\npatternExtensionTrace = 编码串", C_DATA, E_DATA, 9.5)
    arr(ax, (10.7, 3.4), (10.7, 2.9), color=E_DATA)
    save(fig, "pattern_mining.png")


# ===========================================================================
# F5  模式生长（吸收邻居）
# ===========================================================================
def f5():
    fig, ax = newfig(14, 6.6)
    title(ax, 0.2, 6.4, "模式生长：统计模式所有实例的“边界邻居特征”，把出现最多的那一类邻居吸收进模式", 12)

    # left cluster (3 cells)
    ax.add_patch(Rectangle((0.4, 1.4), 3.6, 3.9, fc="#F4F8FD", ec=E_FRONT, lw=1.4))
    txt(ax, 2.2, 5.0, "当前模式（一个实例）", 10, E_FRONT, bold=True)
    for (x, y, lab) in [(1.2, 4.2, "NAND2"), (1.2, 2.4, "NAND2"), (2.8, 3.3, "OR2")]:
        ax.add_patch(Circle((x, y), 0.32, fc="#E8F0FB", ec=E_FRONT, lw=1.4, zorder=3))
        txt(ax, x, y, lab, 8.5, TXT, bold=True)
    arr(ax, (1.5, 4.1), (2.5, 3.5), color="#333", lw=1.3)
    arr(ax, (1.5, 2.5), (2.5, 3.15), color="#333", lw=1.3)

    # boundary neighbors with codes
    ax.add_patch(Circle((4.7, 3.3), 0.34, fc="#FDEEDA", ec=E_BACK, lw=1.6, zorder=3))
    txt(ax, 4.7, 3.3, "OAI21", 8.5, TXT, bold=True)
    arr(ax, (3.12, 3.3), (4.35, 3.3), "c2o0", color="#D43A2F", lw=1.6, toff=(0, 0.28))
    ax.add_patch(Circle((4.6, 5.0), 0.3, fc="#EFE3F7", ec=E_SOLV, lw=1.4, zorder=3))
    txt(ax, 4.6, 5.0, "XOR2", 8, TXT, bold=True)
    arr(ax, (3.05, 3.6), (4.35, 4.85), "c2o1", color="#999", lw=1.1, toff=(-0.1, 0.2))

    # neighbor feature histogram
    ax.add_patch(Rectangle((5.6, 1.4), 3.6, 3.9, fc="#FFFDF4", ec=E_DEC, lw=1.3))
    txt(ax, 7.4, 5.0, "邻居特征计数（跨所有实例）", 10, E_DEC, bold=True)
    bars = [("c2o0_OAI21X1", 60, "#D43A2F"), ("c2o1_XOR2X1", 12, "#C9D4E2"), ("c0i0_INVX1", 8, "#C9D4E2")]
    by = 4.2
    for name, cnt, col in bars:
        ax.add_patch(Rectangle((6.0, by - 0.18), cnt / 60 * 2.6, 0.36, fc=col, ec="none"))
        txt(ax, 5.9, by, name, 8.5, TXT, ha="right")
        txt(ax, 6.1 + cnt / 60 * 2.6, by, str(cnt), 8.5, "#333", ha="left")
        by -= 0.7
    txt(ax, 7.4, 1.75, "取最高频 → c2o0_OAI21X1", 9.5, "#B03030", bold=True)

    # arrow to grown
    arr(ax, (9.3, 3.2), (10.1, 3.2), "吸收", color="#333", lw=1.8)

    # grown cluster (4 cells)
    ax.add_patch(Rectangle((10.3, 1.4), 3.4, 3.9, fc="#F4F8FD", ec=E_IO, lw=1.4))
    txt(ax, 12.0, 5.0, "生长后的模式（4 单元）", 10, E_IO, bold=True)
    for (x, y, lab, fc, ec) in [(10.9, 4.2, "NAND2", "#E8F0FB", E_FRONT),
                                (10.9, 2.4, "NAND2", "#E8F0FB", E_FRONT),
                                (12.1, 3.5, "OR2", "#E8F0FB", E_FRONT),
                                (13.0, 3.0, "OAI21", "#FDEEDA", E_BACK)]:
        ax.add_patch(Circle((x, y), 0.32, fc=fc, ec=ec, lw=1.4, zorder=3))
        txt(ax, x, y, lab, 8, TXT, bold=True)
    txt(ax, 12.0, 1.7, "trace += “+OAI21X1_c2o0”", 9, "#B03030")
    save(fig, "pattern_growth.png")


# ===========================================================================
# F6  ASTRAN autoflow 7 阶段
# ===========================================================================
def f6():
    fig, ax = newfig(11.5, 11)
    cx = 4.0
    stages = [
        ("1. cellgen select", "选中单元并展平层次\ngetFlattenCell：把子实例展开成晶体管网表"),
        ("2. calcArea", "计算行高 H=rowheight×v_grid=2.6µm\n确定 P/N 扩散区与金属轨道列表 trackPos[]"),
        ("3. foldTrans", "晶体管折叠\n宽度>扩散区高度的管子拆成多条并联腿\n(seriesFolding 保持串联堆叠对齐)"),
        ("4. placeTrans", "晶体管排序\nThresholdAccept（模拟退火变体）\n代价=宽度+栅极失配+布线长度+拥塞+空隙"),
        ("5. route", "单元内布线\nGraphRouter：Pathfinder 迷宫路由\n拆线重布 + Steiner 点优化"),
        ("6. compact", "ILP/LP 压缩\n写出 ILPmodel.lp → 外部求解器 → 读 .sol\n目标：最小化单元宽度 width"),
        ("7. export layout", "写出 GDSII\n按层映射表生成 .gds"),
    ]
    y = 10.0
    boxh = 1.18
    centers = []
    for i, (name, desc) in enumerate(stages):
        rbox(ax, cx, y, 2.6, boxh, name, C_BACK, E_BACK, 11, bold=True)
        # description box to the right
        rbox(ax, 8.2, y, 5.6, boxh, desc, C_DATA, E_DATA, 8.8)
        centers.append(y)
        if i < len(stages) - 1:
            arr(ax, (cx, y - boxh / 2), (cx, y - boxh / 2 - (1.32 - boxh)), color=E_BACK, lw=1.8)
        y -= 1.32
    # retry bracket
    ax.add_patch(Rectangle((1.0, centers[-1] - 0.7), 0.25, (centers[0] - centers[-1]) + 1.4,
                           fc="none", ec="#888", lw=1.2, ls=(0, (4, 3))))
    txt(ax, 0.75, (centers[0] + centers[-1]) / 2,
        "失败重试：轨道数 2→4、conservative 0→4，仍失败则抛错", 8.5, "#666", rot=90)
    save(fig, "astran_autoflow.png")


# ===========================================================================
# F7  标准单元物理结构剖面
# ===========================================================================
def f7():
    fig, ax = newfig(13, 7.2)
    # canvas in um: width 0..6, height 0..2.6 (scale to drawing)
    x0, x1 = 2.6, 12.4
    um = (x1 - x0) / 6.0           # 6 um wide example
    H = 2.6
    y0 = 0.9
    sy = 4.6 / H                    # vertical scale
    def Y(v): return y0 + v * sy

    # cell boundary
    ax.add_patch(Rectangle((x0, Y(0)), (x1 - x0), H * sy, fc="white", ec="#333", lw=1.8))
    # n-well (top region above nwellpos)
    nw = 1.14
    ax.add_patch(Rectangle((x0, Y(nw)), (x1 - x0), (H - nw) * sy, fc="#FCE9DA", ec="none"))
    txt(ax, x1 - 0.4, Y((H + nw) / 2), "N 阱", 10, "#B5651D", ha="right")

    # VDD rail (top), GND rail (bottom) : supplysize 0.72
    ss = 0.72
    ax.add_patch(Rectangle((x0, Y(H - ss)), (x1 - x0), ss * sy, fc="#9DB2C8", ec="#33475B"))
    ax.add_patch(Rectangle((x0, Y(0)), (x1 - x0), ss * sy, fc="#9DB2C8", ec="#33475B"))
    txt(ax, x0 + 0.15, Y(H - ss / 2), "VDD (MET1)", 9, "white", ha="left", bold=True)
    txt(ax, x0 + 0.15, Y(ss / 2), "GND (MET1)", 9, "white", ha="left", bold=True)

    # P diffusion (in nwell) and N diffusion (bottom)
    pd_y0, pd_y1 = 1.5, 2.1
    nd_y0, nd_y1 = 0.85, 1.45
    ax.add_patch(Rectangle((x0 + 0.4 * um, Y(pd_y0)), (x1 - x0 - 0.8 * um), (pd_y1 - pd_y0) * sy, fc="#F4C7A1", ec="#B5651D"))
    ax.add_patch(Rectangle((x0 + 0.4 * um, Y(nd_y0)), (x1 - x0 - 0.8 * um), (nd_y1 - nd_y0) * sy, fc="#BFE3C0", ec="#3E7A46"))
    txt(ax, x0 + 0.55 * um, Y((pd_y0 + pd_y1) / 2), "P 扩散（PMOS）", 9, "#7A3E12", ha="left")
    txt(ax, x0 + 0.55 * um, Y((nd_y0 + nd_y1) / 2), "N 扩散（NMOS）", 9, "#2F5B34", ha="left")

    # vertical poly gates crossing both diffusions
    for gx in [1.4, 2.6, 3.8, 5.0]:
        X = x0 + gx * um
        ax.add_patch(Rectangle((X - 0.05 * um, Y(0.8)), 0.1 * um, (2.15 - 0.8) * sy, fc="#C0392B", ec="#7B241C"))
    txt(ax, x0 + 3.2 * um, Y(2.3), "Poly 栅（竖直）", 9, "#7B241C")

    # metal1 routing tracks (horizontal) in the middle
    for ty in [0.95, 1.3, 1.65, 1.95]:
        ax.plot([x0 + 0.2 * um, x1 - 0.2 * um], [Y(ty), Y(ty)], color="#5B7C99", lw=1.0, ls=(0, (6, 3)), alpha=0.7)
    txt(ax, x1 - 0.3 * um, Y(1.62), "MET1 布线轨道", 8.5, "#33475B", ha="right")

    # contacts (squares) from diffusion to rail/track
    for cx_ in [1.4, 3.8, 5.0]:
        X = x0 + cx_ * um
        ax.add_patch(Rectangle((X - 0.06 * um, Y(pd_y1) - 0.06 * um), 0.12 * um, 0.12 * um, fc="#333", ec="none"))
        ax.plot([X, X], [Y(pd_y1), Y(H - ss)], color="#33475B", lw=1.2)
        ax.add_patch(Rectangle((X - 0.06 * um, Y(nd_y0) - 0.06 * um), 0.12 * um, 0.12 * um, fc="#333", ec="none"))
        ax.plot([X, X], [Y(nd_y0), Y(ss)], color="#33475B", lw=1.2)

    # height annotation
    ax.annotate("", xy=(x1 + 0.3, Y(0)), xytext=(x1 + 0.3, Y(H)),
                arrowprops=dict(arrowstyle="<->", color="#333"))
    txt(ax, x1 + 0.45, Y(H / 2), "行高 H = 2.6 µm\n= rowheight(13) × v_grid(0.20)", 9.5, "#333", ha="left")
    # width annotation
    ax.annotate("", xy=(x0, y0 - 0.25), xytext=(x1, y0 - 0.25),
                arrowprops=dict(arrowstyle="<->", color="#333"))
    txt(ax, (x0 + x1) / 2, y0 - 0.45, "单元宽度 W（面积 ∝ W，行高固定）", 9.5, "#333")
    # nwellpos annotation
    ax.plot([x0, x0 - 0.25], [Y(nw), Y(nw)], color="#B5651D", lw=1.2)
    txt(ax, x0 - 0.35, Y(nw), "nwellpos=1.14", 8.5, "#B5651D", ha="right")
    title(ax, 0.2, 6.9, "标准单元的物理结构（剖面示意）：上下电源轨、N 阱/P/N 扩散、竖直 Poly 栅、水平 MET1 轨道", 11.5)
    save(fig, "cell_structure.png")


# ===========================================================================
# F8  晶体管折叠
# ===========================================================================
def f8():
    fig, ax = newfig(13, 5.6)
    title(ax, 0.2, 5.3, "晶体管折叠：超过扩散区可用高度的宽晶体管，拆成多条并联的“腿”，既降宽又适配行高", 11.5)

    def pmos(x, y, w_units, label, wscale=0.28):
        # draw a PMOS finger: poly gate vertical bar + diffusion width label
        ax.add_patch(Rectangle((x - 0.06, y - 0.7), 0.12, 1.4, fc="#C0392B", ec="#7B241C"))
        ax.add_patch(Rectangle((x - w_units * wscale / 2, y - 0.35), w_units * wscale, 0.7,
                               fc="#F4C7A1", ec="#B5651D", alpha=0.9))
        txt(ax, x, y + 0.95, label, 8.5, "#333")

    # left: single wide transistor
    ax.add_patch(Rectangle((0.5, 0.9), 5.2, 3.9, fc="#FDF6EE", ec=E_BACK, lw=1.2))
    txt(ax, 3.1, 4.5, "折叠前：一个 W=4µm 的宽晶体管", 10, E_BACK, bold=True)
    pmos(3.1, 2.6, 4, "W = 4 µm")
    txt(ax, 3.1, 1.3, "超过 P 扩散区可用高度 → 放不下", 9, "#B03030")

    arr(ax, (5.9, 2.6), (6.8, 2.6), "拆成 2 条腿", color="#333", lw=1.8, toff=(0, 0.4))

    # right: two parallel legs
    ax.add_patch(Rectangle((7.0, 0.9), 5.6, 3.9, fc="#F4F8FD", ec=E_IO, lw=1.2))
    txt(ax, 9.8, 4.5, "折叠后：2 条 W=2µm 的并联腿（共享栅）", 10, E_IO, bold=True)
    pmos(8.7, 2.6, 2, "W = 2 µm")
    pmos(10.7, 2.6, 2, "W = 2 µm")
    # shared gate connection
    ax.plot([8.7, 10.7], [3.3, 3.3], color="#7B241C", lw=1.6)
    txt(ax, 9.8, 3.5, "同一栅信号", 8, "#7B241C")
    txt(ax, 9.8, 1.3, "总驱动能力不变，宽度方向更省", 9, "#2F5B34")
    save(fig, "folding.png")


# ===========================================================================
# F9  ILP 压缩
# ===========================================================================
def f9():
    fig, ax = newfig(13.5, 6.4)
    title(ax, 0.2, 6.1, "压缩（Compaction）：把布线后的几何图元坐标作为变量，建一个以“单元宽度最小”为目标的 ILP/LP，交给求解器", 11.5)

    # left: loose layout with coordinate vars
    ax.add_patch(Rectangle((0.4, 1.5), 5.6, 4.0, fc="#FBFCFE", ec="#B9C6D6", lw=1.2))
    txt(ax, 3.2, 5.2, "布线后的几何（坐标未定）", 10, "#5A6B7F")
    shapes = [(1.0, 2.2, 1.0, 0.8, "#F4C7A1"), (2.6, 2.6, 1.2, 0.7, "#BFE3C0"),
              (4.3, 2.1, 0.9, 0.9, "#DCE9F7"), (2.0, 3.9, 1.6, 0.5, "#9DB2C8")]
    for i, (x, y, w, h, c) in enumerate(shapes):
        ax.add_patch(Rectangle((x, y), w, h, fc=c, ec="#555", lw=1.2))
        ax.annotate("", xy=(x, y - 0.12), xytext=(x + w, y - 0.12),
                    arrowprops=dict(arrowstyle="<->", color="#B03030", lw=1))
        txt(ax, x + w / 2, y - 0.32, f"x{i}a..x{i}b", 8, "#B03030")
    # spacing constraint
    ax.annotate("", xy=(3.8, 2.95), xytext=(4.3, 2.95),
                arrowprops=dict(arrowstyle="<->", color="#2E6DB4", lw=1.2))
    txt(ax, 4.05, 3.2, "间距 ≥ 规则", 8, "#2E6DB4")

    arr(ax, (6.1, 3.5), (7.0, 3.5), "建模", color="#333", lw=1.8, toff=(0, 0.4))

    # middle: LP model
    rbox(ax, 8.6, 4.6, 3.0, 1.4, "ILPmodel.lp\n变量：x/y 坐标、0/1 析取\n约束：间距/重叠/网格对齐\n目标：min 宽度 width", C_SOLV, E_SOLV, 8.6)
    rbox(ax, 8.6, 2.5, 3.0, 1.0, "gurobi_cl.cmd\n→ gurobi_cl.py\n→ python-mip + CBC", C_SOLV, E_SOLV, 9)
    arr(ax, (8.6, 3.9), (8.6, 3.0), color=E_SOLV, lw=1.5)

    arr(ax, (10.1, 2.5), (11.0, 3.2), "解 .sol", color="#333", lw=1.8, toff=(0.2, 0.1))

    # right: compacted layout
    ax.add_patch(Rectangle((11.2, 1.8), 2.0, 3.4, fc="#F4F8FD", ec=E_IO, lw=1.3))
    txt(ax, 12.2, 4.9, "压缩后的版图", 10, E_IO, bold=True)
    cs = [(11.35, 2.3, 0.8, 0.7, "#F4C7A1"), (12.3, 2.5, 0.7, 0.6, "#BFE3C0"),
          (11.5, 3.5, 1.4, 0.45, "#9DB2C8"), (12.0, 2.0, 0.6, 0.6, "#DCE9F7")]
    for (x, y, w, h, c) in cs:
        ax.add_patch(Rectangle((x, y), w, h, fc=c, ec="#333", lw=1.0))
    ax.annotate("", xy=(11.2, 1.6), xytext=(13.2, 1.6),
                arrowprops=dict(arrowstyle="<->", color="#333"))
    txt(ax, 12.2, 1.35, "width（最小化）", 8.5, "#333")
    save(fig, "compaction_lp.png")


# ===========================================================================
# F10  前后端接口契约
# ===========================================================================
def f10():
    fig, ax = newfig(15, 6.6)
    title(ax, 0.2, 6.3, "前后端接口契约：文件即接口。网表 + 运行脚本驱动 ASTRAN；LP 文件驱动求解器；日志回读宽度", 11.5)

    def fbox(x, y, w, h, name, sub, fc, ec):
        rbox(ax, x, y, w, h, "", fc, ec, 10)
        txt(ax, x, y + h / 2 - 0.28, name, 10, ec, bold=True)
        txt(ax, x, y - 0.15, sub, 8.2, "#444")

    fbox(1.5, 5.2, 2.6, 1.1, "COMPLEX<n>.sp", "晶体管级网表\n(端口顺序=插入序)", C_DATA, E_DATA)
    fbox(1.5, 3.6, 2.6, 1.1, "COMPLEX<n>.run", "ASTRAN 脚本\n(set 几何参数…)", C_DATA, E_DATA)
    rbox(ax, 5.3, 4.4, 2.6, 2.2, "Astran.exe\n--shell\ncellgen\nautoflow", C_BACK, E_BACK, 10.5, bold=True)
    fbox(9.0, 5.4, 2.4, 0.95, "ILPmodel.lp", "压缩模型(变量/约束/目标)", C_SOLV, E_SOLV)
    rbox(ax, 12.1, 4.4, 2.4, 2.2, "gurobi_cl.cmd\n→ gurobi_cl.py\n→ python-mip/CBC", C_SOLV, E_SOLV, 9.5, bold=True)
    fbox(9.0, 3.2, 2.4, 0.95, "ILPmodel.sol", "变量解（坐标）", C_SOLV, E_SOLV)
    fbox(5.3, 1.3, 2.6, 1.0, "COMPLEX<n>.gds", "版图输出", C_IO, E_IO)
    fbox(8.6, 1.3, 2.8, 1.0, "COMPLEX<n>.Astranlog", "“Cell Size (W×H)”\n回读宽度", C_IO, E_IO)

    arr(ax, (2.8, 5.2), (4.0, 5.0), "", color="#333", lw=1.6)
    arr(ax, (2.8, 3.6), (4.0, 3.9), "", color="#333", lw=1.6)
    arr(ax, (6.6, 5.4), (7.8, 5.4), "写出", color=E_SOLV, lw=1.5, toff=(0, 0.25))
    arr(ax, (10.2, 5.4), (10.9, 5.2), "", color=E_SOLV, lw=1.5)
    arr(ax, (10.9, 3.7), (10.2, 3.6), "", color=E_SOLV, lw=1.5)
    arr(ax, (7.8, 3.6), (6.6, 3.9), "读入坐标", color=E_SOLV, lw=1.5, toff=(0, -0.3))
    arr(ax, (5.3, 3.3), (5.3, 2.3), "", color=E_BACK, lw=1.6)
    arr(ax, (6.6, 1.5), (7.2, 1.4), "", color=E_IO, lw=1.5)

    # contract notes
    ax.add_patch(Rectangle((11.0, 0.3), 3.9, 2.2, fc="#FFFDF4", ec=E_DEC, lw=1.2))
    txt(ax, 12.95, 2.25, "关键契约", 10, E_DEC, bold=True)
    txt(ax, 11.2, 1.9, "• 缓存：.sp 比 .gds 新 → 重新生成", 8.6, "#333", ha="left")
    txt(ax, 11.2, 1.5, "• FEASIBLE 也算成功（gap 容差）", 8.6, "#333", ha="left")
    txt(ax, 11.2, 1.1, "• inf 系数按“无界”丢弃", 8.6, "#333", ha="left")
    txt(ax, 11.2, 0.7, "• 0×0 版图 = 求解失败 → 排除", 8.6, "#333", ha="left")
    save(fig, "interface_contract.png")


# ===========================================================================
# F11  面积评估
# ===========================================================================
def f11():
    fig, ax = newfig(13, 5.8)
    title(ax, 0.2, 5.5, "面积评估与组合选择：把模式内的原始单元宽度之和，与合并后 COMPLEX 版图宽度之差，乘以出现次数", 11.5)

    # bar comparison: a generic 3-cell pattern (illustrative, self-consistent)
    ax.add_patch(Rectangle((0.4, 0.9), 6.0, 4.0, fc="#FBFCFE", ec="#B9C6D6", lw=1.2))
    txt(ax, 3.4, 4.6, "示意算例：一个 3 单元模式（方法学演示）", 9.5, "#5A6B7F")
    orig = [("NAND2", 0.8), ("NAND2", 0.8), ("OR2", 1.0)]
    bx = 1.0; tot = 0
    for name, w in orig:
        ax.add_patch(Rectangle((bx, 2.4), w, 0.8, fc="#DCE9F7", ec=E_FRONT, lw=1.2))
        txt(ax, bx + w / 2, 2.8, name, 7.5, TXT)
        bx += w; tot += w
    txt(ax, bx + 0.08, 2.8, f"= {tot:.1f} µm", 9, E_FRONT, ha="left", bold=True)
    txt(ax, 1.0, 3.45, "原方案：3 个独立单元并排（宽度相加）", 8.5, "#333", ha="left")
    # complex bar
    ax.add_patch(Rectangle((1.0, 1.2), 1.8, 0.8, fc="#FCE3C8", ec=E_BACK, lw=1.4))
    txt(ax, 1.0 + 1.8 / 2, 1.6, "COMPLEX\n(合并版图)", 7.5, TXT)
    txt(ax, 1.0 + 1.9, 1.6, "= 1.8 µm", 9, E_BACK, ha="left", bold=True)
    txt(ax, 1.0, 0.95, "每处省 0.8 µm；出现 N 次则省 0.8 × N", 9, "#B03030", ha="left", bold=True)

    # formula box
    ax.add_patch(Rectangle((6.8, 1.2), 5.9, 3.6, fc="#F4F8FD", ec=E_FRONT, lw=1.3))
    txt(ax, 9.75, 4.35, "贪心组合选择", 10.5, E_FRONT, bold=True)
    txt(ax, 9.75, 3.55, "save_area = Σ ( Σ w(原单元) − w(COMPLEX) ) × 簇数", 9.5, TXT)
    txt(ax, 9.75, 2.75, "每一轮：在 top_thr 个候选里累计正的 save_area，\n若超过历史最佳则写入 bestRecord，否则停止。", 9.2, "#333")
    txt(ax, 9.75, 1.75, "最终选出的组合 = 使总节省最大的一组 COMPLEX 单元", 9.2, E_FRONT)
    save(fig, "area_eval.png")


if __name__ == "__main__":
    f1(); f2(); f3(); f4(); f5(); f6(); f7(); f8(); f9(); f10(); f11()
    print("done")
