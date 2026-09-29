"""A dark-styled matplotlib canvas for embedding charts in tabs.

The figures are built with the ``Figure`` API only (no pyplot), so the flow's
Agg-pyplot drawings in the worker thread can never fight the GUI backend.
"""
from matplotlib.figure import Figure

import matplotlib
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

from PySide6.QtWidgets import QSizePolicy

from .. import theme

# CJK-capable sans fonts, resolved at draw time.  The UI is bilingual, so the
# charts must be able to render Chinese labels (DejaVu Sans, matplotlib's
# default, has no CJK glyphs).
matplotlib.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Microsoft YaHei UI", "Microsoft YaHei", "SimHei",
                        "Segoe UI", "Noto Sans CJK SC", "PingFang SC",
                        "DejaVu Sans"],
    "axes.unicode_minus": False,
})


def _rc():
    return {
        "axes.facecolor": theme.PANEL,
        "figure.facecolor": theme.PANEL,
        "savefig.facecolor": theme.PANEL,
        "axes.edgecolor": theme.BORDER,
        "axes.labelcolor": theme.TEXT_DIM,
        "axes.titlecolor": theme.TEXT,
        "xtick.color": theme.TEXT_DIM,
        "ytick.color": theme.TEXT_DIM,
        "text.color": theme.TEXT,
        "grid.color": theme.BORDER,
        "axes.grid": True,
        "grid.linestyle": "-",
        "grid.alpha": 0.35,
        "font.size": 10,
    }


class MplCanvas(FigureCanvasQTAgg):
    def __init__(self, parent=None, height=3.0):
        fig = Figure(figsize=(5, height), dpi=100, constrained_layout=True)
        super().__init__(fig)
        self.fig = fig
        self.ax = fig.add_subplot(111)
        self.setStyleSheet("background-color: %s;" % theme.PANEL)
        # Follow the container's size instead of pinning the figsize, so a
        # stretched card cannot squash the chart into a flat strip.
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(220)
        self.fresh()

    def draw_now(self):
        self.fig.canvas.draw_idle()

    def _apply_style(self):
        rc = _rc()
        ax = self.ax
        ax.set_facecolor(rc["axes.facecolor"])
        self.fig.set_facecolor(rc["figure.facecolor"])
        for spine in ax.spines.values():
            spine.set_color(rc["axes.edgecolor"])
        ax.tick_params(colors=rc["xtick.color"], labelsize=9)
        ax.xaxis.label.set_color(rc["axes.labelcolor"])
        ax.yaxis.label.set_color(rc["axes.labelcolor"])
        ax.title.set_color(rc["axes.titlecolor"])
        ax.grid(rc["axes.grid"], linestyle="-", alpha=0.3,
                color=rc["grid.color"])

    def fresh(self, title=""):
        self.ax.clear()
        self._apply_style()
        if title:
            self.ax.set_title(title, loc="left", pad=8)
        return self.ax
