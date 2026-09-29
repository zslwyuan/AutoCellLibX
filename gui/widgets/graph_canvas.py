"""An interactive painter for networkx subgraphs (patterns, design neighbourhoods).

Colour encodes the standard-cell type, which is exactly what the encoder keys
on, so the picture matches the ``patternExtensionTrace`` string: nodes of one
colour that share a shape are the "same" pattern.
"""
import math

import networkx as nx
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QPainter, QPainterPath,
                           QPen, QPolygonF)
from PySide6.QtWidgets import QToolTip, QWidget

from .. import theme

# Distinct, readable hues for cell types (cycled).
TYPE_COLOURS = [
    "#4c8dff", "#3fb950", "#d29922", "#f85149", "#b083f0", "#39c5cf",
    "#e879a6", "#8fbf58", "#d9793e", "#6f8cff", "#c9b458", "#5fbfa0",
    "#c07ad0", "#7fa8d8", "#d0a05b", "#8f9aa8",
]


def type_colour_map(types):
    """Stable type -> colour mapping (sorted, so it is reproducible)."""
    return {t: TYPE_COLOURS[i % len(TYPE_COLOURS)]
            for i, t in enumerate(sorted(set(types)))}


class GraphCanvas(QWidget):
    """Pan/zoom graph view. Left-drag pans, wheel zooms, click selects a node."""

    nodeSelected = Signal(object)
    nodeHovered = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 300)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self._graph = None
        self._pos = {}                 # node -> (x, y) in graph units
        self._type_colour = {}
        self._highlight = set()
        self._dim = set()
        self._labels = True
        self._title = ""
        self._hover = None
        self._selected = None
        self._zoom = 1.0
        self._offset = QPointF(0, 0)
        self._drag_from = None
        self._fit_pending = True
        self._radius = 13.0
        self._placeholder = "选择一个模式或单元以查看其子图\nSelect a pattern or cell to view its subgraph"

    # ------------------------------------------------------------------ api
    def clear(self):
        self._graph = None
        self._pos = {}
        self._highlight = set()
        self.update()

    def set_graph(self, graph, colour_attr="type", highlight=None,
                  dim=None, layout="spring", seed=1, title="", labels=True):
        self._graph = graph
        self._title = title
        self._labels = labels
        self._highlight = set(highlight or ())
        self._dim = set(dim or ())
        self._selected = None
        if graph is None or graph.number_of_nodes() == 0:
            self._pos = {}
            self.update()
            return

        attrs = nx.get_node_attributes(graph, colour_attr)
        self._type_colour = type_colour_map(attrs.values()) if attrs else {}
        self._pos = self._compute_layout(graph, attrs, layout, seed)
        self._radius = 20.0 if graph.number_of_nodes() <= 8 else (
            12.0 if graph.number_of_nodes() <= 60 else 7.0)
        self._fit_pending = True
        self.update()

    @staticmethod
    def _compute_layout(graph, attrs, layout, seed):
        n = graph.number_of_nodes()
        if layout == "spring" and n > 1:
            # Grouping by type first makes the spring layout legible: identical
            # cell types sit together, which is what the pattern code encodes.
            try:
                return nx.spring_layout(graph, seed=seed, k=1.6 / math.sqrt(n),
                                        iterations=60 if n < 400 else 25)
            except Exception:                        # noqa: BLE001
                pass
        return nx.circular_layout(graph)

    def set_highlight(self, node_ids):
        self._highlight = set(node_ids or ())
        self.update()

    def fit(self):
        self._fit_pending = True
        self.update()

    # -------------------------------------------------------------- painting
    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(theme.BG_ALT))

        if not self._pos:
            self._draw_placeholder(painter)
            return

        if self._fit_pending:
            self._fit()

        # Everything is drawn in screen space: node radius, edge width and
        # arrow heads are constant in pixels regardless of the fit zoom.
        self._draw_edges(painter)
        self._draw_nodes(painter)
        self._draw_overlay(painter)

    def _draw_placeholder(self, painter):
        painter.setPen(QColor(theme.TEXT_FAINT))
        font = QFont()
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, self._placeholder)

    def _draw_overlay(self, painter):
        if self._title:
            painter.setPen(QColor(theme.TEXT_DIM))
            painter.drawText(12, 20, self._title)
        if not self._type_colour:
            return
        # Type legend, bottom-left, wrapped into columns of 16 px rows.
        entries = sorted(self._type_colour.items())
        row_h = 16
        per_col = max(1, (self.height() - 24) // row_h)
        base_y = self.height() - row_h * min(len(entries), per_col) - 8
        for i, (type_name, colour) in enumerate(entries):
            col, row = divmod(i, per_col)
            x = 12 + col * 170
            y = base_y + row * row_h
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(colour)))
            painter.drawEllipse(QRectF(x, y - 7, 8, 8))
            painter.setPen(QColor(theme.TEXT_DIM))
            painter.drawText(x + 14, y, str(type_name))

    def _draw_edges(self, painter):
        pen = QPen(QColor("#46586b"))
        pen.setWidthF(2.4)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        for u, v in self._graph.edges():
            if u not in self._pos or v not in self._pos:
                continue
            p1 = self._to_screen(*self._pos[u])
            p2 = self._to_screen(*self._pos[v])
            painter.drawLine(p1, p2)
            self._draw_arrow(painter, p1, p2)

    def _draw_arrow(self, painter, p1, p2):
        dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
        length = math.hypot(dx, dy)
        if length < 1e-6:
            return
        ux, uy = dx / length, dy / length
        r = self._radius
        tip_x = p2.x() - ux * (r + 2)
        tip_y = p2.y() - uy * (r + 2)
        size = max(7.0, r * 0.55)
        left = QPointF(tip_x - ux * size - uy * size * 0.55,
                       tip_y - uy * size + ux * size * 0.55)
        right = QPointF(tip_x - ux * size + uy * size * 0.55,
                        tip_y - uy * size - ux * size * 0.55)
        painter.setBrush(QBrush(QColor("#5d7a9a")))
        painter.drawPolygon(QPolygonF([QPointF(tip_x, tip_y), left, right]))
        painter.setBrush(Qt.NoBrush)

    def _draw_nodes(self, painter):
        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)
        r = self._radius
        small = self._graph.number_of_nodes() <= 8

        for node, (x, y) in self._pos.items():
            data = self._graph.nodes[node]
            type_name = data.get("type", "?")
            colour = QColor(self._type_colour.get(type_name, theme.TEXT_DIM))
            if node in self._dim:
                colour.setAlpha(70)
            c = self._to_screen(x, y)
            is_hi = node in self._highlight
            is_sel = node == self._selected
            is_hover = node == self._hover

            if is_hi or is_sel or is_hover:
                ring = QColor(theme.ACCENT if (is_sel or is_hover) else theme.OK)
                pen = QPen(ring)
                pen.setWidthF(2.5)
                painter.setPen(pen)
                painter.setBrush(QBrush(colour))
                painter.drawEllipse(c, r * 1.22, r * 1.22)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(colour))
            painter.drawEllipse(c, r, r)

            if self._labels and r >= 8:
                painter.setPen(QColor(theme.TEXT))
                label = str(data.get("name", node))
                if small:
                    label = "%s\n%s" % (type_name, label)
                painter.drawText(QRectF(c.x() - 80, c.y() + r + 3, 160, 40),
                                 Qt.AlignHCenter | Qt.AlignTop, label)

    # --------------------------------------------------------------- transform
    def _fit(self):
        self._fit_pending = False
        if not self._pos:
            return
        xs = [p[0] for p in self._pos.values()]
        ys = [-p[1] for p in self._pos.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        w = max(max_x - min_x, 1e-6)
        h = max(max_y - min_y, 1e-6)
        margin = 60
        sx = (self.width() - 2 * margin) / w
        sy = (self.height() - 2 * margin) / h
        self._zoom = max(0.05, min(sx, sy))
        cx = (min_x + max_x) / 2.0
        cy = (min_y + max_y) / 2.0
        self._offset = QPointF(self.width() / 2.0 - cx * self._zoom,
                               self.height() / 2.0 - cy * self._zoom)

    def _to_screen(self, x, y):
        return QPointF(x * self._zoom + self._offset.x(),
                       -y * self._zoom + self._offset.y())

    def _node_at(self, px, py):
        best, best_d = None, 1e9
        for node, (x, y) in self._pos.items():
            c = self._to_screen(x, y)
            d = math.hypot(c.x() - px, c.y() - py)
            if d < max(self._radius, 10) and d < best_d:
                best, best_d = node, d
        return best

    # ----------------------------------------------------------------- events
    def wheelEvent(self, event):
        if not self._pos:
            return
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        pos = event.position()
        before_x = (pos.x() - self._offset.x()) / self._zoom
        before_y = (pos.y() - self._offset.y()) / self._zoom
        self._zoom = max(0.05, min(60.0, self._zoom * factor))
        self._offset = QPointF(pos.x() - before_x * self._zoom,
                               pos.y() - before_y * self._zoom)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._pos:
            self._drag_from = event.position()
            node = self._node_at(event.position().x(), event.position().y())
            if node is not None:
                self._selected = node
                self.nodeSelected.emit(node)
                self.update()

    def mouseMoveEvent(self, event):
        if self._drag_from is not None and event.buttons() & Qt.LeftButton:
            delta = event.position() - self._drag_from
            self._offset += delta
            self._drag_from = event.position()
            self.update()
            return
        if not self._pos:
            return
        node = self._node_at(event.position().x(), event.position().y())
        if node != self._hover:
            self._hover = node
            self.update()
            if node is not None:
                data = self._graph.nodes[node]
                QToolTip.showText(event.globalPosition().toPoint(),
                                  "id=%s\n类型 %s\n实例 %s"
                                  % (node, data.get("type", "?"),
                                     data.get("name", "?")), self)
                self.nodeHovered.emit(node)

    def mouseReleaseEvent(self, _event):
        self._drag_from = None

    def mouseDoubleClickEvent(self, _event):
        self.fit()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Plus, Qt.Key_Equal):
            self.wheelEvent(_FakeWheel(120))
        elif event.key() == Qt.Key_Minus:
            self.wheelEvent(_FakeWheel(-120))
        else:
            super().keyPressEvent(event)


class _FakeWheel(object):
    """Minimal stand-in for QWheelEvent for keyboard zoom."""

    def __init__(self, delta):
        self._d = delta

    def angleDelta(self):
        from PySide6.QtCore import QPoint
        return QPoint(0, self._d)

    def position(self):
        return QPointF(0, 0)
