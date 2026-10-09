"""Interactive GDSII layout viewer: layer control, ruler, measurement.

The drawing model is ``gui.gds_model.LayoutModel`` -- polygons already scaled
to microns and bucketed by layer.  Everything here is presentation: QPainter
paths are cached per layer and re-used across repaints (a complex cell has
~1000 polygons; rebuilding the paths on every wheel tick would stutter).
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QPainter, QPainterPath, QPen,
                           QPixmap)
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QPushButton,
                               QSizePolicy, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from .. import theme


class GdsCanvas(QWidget):
    """Pan/zoom layout view.  Wheel zooms, left-drag pans, F fits."""

    cursorMoved = Signal(float, float)      # microns, or NaN when outside
    measureChanged = Signal(float)          # microns between the two points
    measureCleared = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 260)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self._model = None
        self._paths = {}
        self._visible = {}
        self._zoom = 40.0
        self._offset = QPointF(0, 0)
        self._drag_from = None
        self._cursor_um = None
        self._fit_pending = True
        self._show_grid = True
        self._measure_mode = False
        self._measure = []              # [(x, y), (x, y)]
        self._measure_done = False
        self._placeholder = ("载入一个 COMPLEX 单元以查看版图\n"
                             "Load a COMPLEX cell to inspect its layout")

    # ------------------------------------------------------------------ api
    def set_layout(self, model):
        self._model = model
        self._paths = {}
        self._measure = []
        self._measure_done = False
        if model is not None:
            self._visible = {key: layer.visible
                             for key, layer in model.layers.items()}
        self._fit_pending = True
        self.update()

    def layers(self):
        return [] if self._model is None else self._model.ordered_layers()

    def set_layer_visible(self, key, visible):
        self._visible[key] = bool(visible)
        self.update()

    def layer_visible(self, key):
        return self._visible.get(key, True)

    def set_layers_visible(self, keys, visible):
        for key in keys:
            self._visible[key] = bool(visible)
        self.update()

    def set_show_grid(self, on):
        self._show_grid = bool(on)
        self.update()

    def set_measure_mode(self, on):
        self._measure_mode = bool(on)
        if not on:
            self._measure = []
            self._measure_done = False
            self.measureCleared.emit()
        self.setCursor(Qt.CrossCursor if on else Qt.ArrowCursor)
        self.update()

    def clear_measure(self):
        self._measure = []
        self._measure_done = False
        self.measureCleared.emit()
        self.update()

    def fit(self):
        self._fit_pending = True
        self.update()

    def zoom_by(self, factor):
        self._zoom_at(factor, QPointF(self.width() / 2.0, self.height() / 2.0))

    def export_png(self, path, scale=2):
        pm = QPixmap(self.size() * scale)
        pm.setDevicePixelRatio(scale)
        self.render(pm)
        pm.save(path, "PNG")

    def has_layout(self):
        return self._model is not None

    # -------------------------------------------------------------- transform
    def _fit(self):
        self._fit_pending = False
        if self._model is None:
            return
        x0, y0, x1, y1 = self._model.full_bbox
        w = max(x1 - x0, 1e-3)
        h = max(y1 - y0, 1e-3)
        margin = 46
        sx = (self.width() - 2 * margin) / w
        sy = (self.height() - 2 * margin) / h
        self._zoom = max(0.5, min(sx, sy))
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        self._offset = QPointF(self.width() / 2.0 - cx * self._zoom,
                               self.height() / 2.0 + cy * self._zoom)

    def _to_screen(self, x, y):
        return QPointF(x * self._zoom + self._offset.x(),
                       -y * self._zoom + self._offset.y())

    def _to_world(self, sx, sy):
        return ((sx - self._offset.x()) / self._zoom,
                -(sy - self._offset.y()) / self._zoom)

    def _zoom_at(self, factor, pos):
        if self._model is None:
            return
        wx, wy = self._to_world(pos.x(), pos.y())
        self._zoom = max(0.5, min(4000.0, self._zoom * factor))
        self._offset = QPointF(pos.x() - wx * self._zoom,
                               pos.y() + wy * self._zoom)
        self.update()

    # -------------------------------------------------------------- painting
    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#0a0e13"))

        if self._model is None:
            painter.setPen(QColor(theme.TEXT_FAINT))
            painter.drawText(self.rect(), Qt.AlignCenter, self._placeholder)
            return

        if self._fit_pending:
            self._fit()

        if self._show_grid:
            self._draw_grid(painter)

        for layer in self._model.ordered_layers():
            key = (layer.layer, layer.datatype)
            if not self._visible.get(key, layer.visible):
                continue
            painter.save()
            painter.translate(self._offset)
            painter.scale(self._zoom, -self._zoom)
            self._draw_layer(painter, layer)
            painter.restore()

        painter.save()
        painter.translate(self._offset)
        painter.scale(self._zoom, -self._zoom)
        self._draw_boundary(painter)
        painter.restore()

        self._draw_dimensions(painter)
        self._draw_measure(painter)
        self._draw_scalebar(painter)

    def _layer_path(self, layer):
        key = (layer.layer, layer.datatype)
        path = self._paths.get(key)
        if path is None:
            path = QPainterPath()
            for pts in layer.polygons:
                if len(pts) < 3:
                    continue
                path.moveTo(pts[0][0], pts[0][1])
                for x, y in pts[1:]:
                    path.lineTo(x, y)
                path.closeSubpath()
            self._paths[key] = path
        return path

    # Per-layer fill alpha: wells/implants stay subtle so the active/poly/poly
    # detail above them reads; structural layers stay vivid.
    _ALPHA = {2: 46, 3: 46, 4: 120, 5: 120, 1: 175, 9: 210, 10: 235,
              49: 165, 50: 215, 51: 160, 61: 205, 62: 155, 30: 195,
              31: 150, 32: 190, 33: 150}

    def _draw_layer(self, painter, layer):
        path = self._layer_path(layer)
        if path.isEmpty():
            return
        colour = QColor(layer.colour)
        if layer.layer == 235:               # pr_boundary: dashed outline only
            pen = QPen(colour)
            pen.setWidthF(max(0.006, 1.1 / self._zoom))
            pen.setStyle(Qt.DashLine)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(pen)
            painter.drawPath(path)
            return
        fill = QColor(colour)
        fill.setAlpha(self._ALPHA.get(layer.layer, 165))
        painter.setBrush(QBrush(fill))

        outline = QColor(colour).darker(120)
        pen = QPen(outline)
        pen.setWidthF(max(0.004, 0.9 / self._zoom))
        pen.setJoinStyle(Qt.MiterJoin)
        painter.setPen(pen)
        painter.drawPath(path)

    def _draw_boundary(self, painter):
        x0, y0, x1, y1 = self._model.bbox
        pen = QPen(QColor("#e0b341"))
        pen.setWidthF(max(0.006, 1.2 / self._zoom))
        pen.setStyle(Qt.DashLine)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(pen)
        painter.drawRect(QRectF(QPointF(x0, y0), QPointF(x1, y1)))

    def _draw_grid(self, painter):
        # Draw the routing grid only when it is legible (>= 6 px pitch).
        model = self._model
        if model is None:
            return
        x0, y0, x1, y1 = model.full_bbox
        pen = QPen(QColor("#16202b"))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        # 0.19 um M1 pitch, the library granularity the cells are built on.
        pitch = 0.19
        if pitch * self._zoom < 6:
            pitch *= 5
        if pitch * self._zoom < 6:
            return
        start_x = math.floor(x0 / pitch) * pitch
        x = start_x
        while x <= x1:
            p = self._to_screen(x, 0)
            painter.drawLine(QPointF(p.x(), self.height() * 0.0),
                             QPointF(p.x(), float(self.height())))
            x += pitch
        start_y = math.floor(y0 / pitch) * pitch
        y = start_y
        while y <= y1:
            p = self._to_screen(0, y)
            painter.drawLine(QPointF(0.0, p.y()),
                             QPointF(float(self.width()), p.y()))
            y += pitch

    def _draw_dimensions(self, painter):
        model = self._model
        x0, y0, x1, y1 = model.bbox
        painter.setPen(QColor(theme.TEXT_DIM))
        font = QFont()
        font.setPointSizeF(max(8.0, min(13.0, self._zoom * 0.16)))
        painter.setFont(font)

        p0 = self._to_screen(x0, y0)
        p1 = self._to_screen(x1, y1)
        label = "W %.2f µm × H %.2f µm" % (x1 - x0, y1 - y0)
        painter.drawText(QPointF(p0.x(), p0.y() + 22), label)
        pen = QPen(QColor("#e0b341"))
        pen.setWidthF(1.2)
        painter.setPen(pen)
        y_line = p1.y() - 12
        painter.drawLine(QPointF(p0.x(), y_line), QPointF(p1.x(), y_line))
        for px in (p0.x(), p1.x()):
            painter.drawLine(QPointF(px, y_line - 5), QPointF(px, y_line + 5))

    def _draw_measure(self, painter):
        if len(self._measure) < 2 and not self._measure:
            return
        pen = QPen(QColor(theme.INFO))
        pen.setWidthF(1.6)
        painter.setPen(pen)
        pts = [self._to_screen(x, y) for x, y in self._measure]
        if len(pts) == 2:
            painter.drawLine(pts[0], pts[1])
            dist = math.hypot(self._measure[1][0] - self._measure[0][0],
                              self._measure[1][1] - self._measure[0][1])
            mid = QPointF((pts[0].x() + pts[1].x()) / 2,
                          (pts[0].y() + pts[1].y()) / 2)
            painter.drawText(mid + QPointF(6, -6), "%.3f µm" % dist)
        for p in pts:
            painter.setBrush(QBrush(QColor(theme.INFO)))
            painter.drawEllipse(p, 3, 3)
        painter.setBrush(Qt.NoBrush)

    def _draw_scalebar(self, painter):
        # Pick a round micron length that is 60-160 px on screen.
        target_px = 110.0
        raw = target_px / self._zoom
        nice = _nice_number(raw)
        length_px = nice * self._zoom
        x = self.width() - length_px - 22
        y = self.height() - 22
        painter.setPen(QColor(theme.TEXT_DIM))
        painter.drawLine(QPointF(x, y), QPointF(x + length_px, y))
        painter.drawLine(QPointF(x, y - 4), QPointF(x, y + 4))
        painter.drawLine(QPointF(x + length_px, y - 4),
                         QPointF(x + length_px, y + 4))
        painter.drawText(QPointF(x, y - 8), "%.3g µm" % nice)

    # ----------------------------------------------------------------- events
    def wheelEvent(self, event):
        if self._model is None:
            return
        factor = 1.18 if event.angle_delta().y() > 0 else 1 / 1.18
        self._zoom_at(factor, event.position())

    def mousePressEvent(self, event):
        if self._model is None:
            return
        pos = event.position()
        if self._measure_mode and event.button() == Qt.LeftButton:
            wx, wy = self._to_world(pos.x(), pos.y())
            if len(self._measure) == 2 or self._measure_done:
                self._measure = []
            self._measure.append((wx, wy))
            if len(self._measure) == 2:
                self._measure_done = True
                dist = math.hypot(self._measure[1][0] - self._measure[0][0],
                                  self._measure[1][1] - self._measure[0][1])
                self.measureChanged.emit(dist)
            self.update()
            return
        if event.button() == Qt.LeftButton:
            self._drag_from = pos

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._drag_from is not None and event.buttons() & Qt.LeftButton:
            self._offset += pos - self._drag_from
            self._drag_from = pos
            self.update()
        if self._model is None:
            return
        wx, wy = self._to_world(pos.x(), pos.y())
        self._cursor_um = (wx, wy)
        self.cursorMoved.emit(wx, wy)

    def mouseReleaseEvent(self, _event):
        self._drag_from = None

    def leaveEvent(self, _event):
        self.cursorMoved.emit(float("nan"), float("nan"))

    def mouseDoubleClickEvent(self, _event):
        self.fit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F:
            self.fit()
        elif event.key() in (Qt.Key_Plus, Qt.Key_Equal):
            self.zoom_by(1.25)
        elif event.key() == Qt.Key_Minus:
            self.zoom_by(1 / 1.25)
        else:
            super().keyPressEvent(event)


def _nice_number(value):
    if value <= 0:
        return 1.0
    exp = math.floor(math.log10(value))
    base = 10 ** exp
    for mult in (1, 2, 5, 10):
        if value <= mult * base:
            return mult * base
    return 10 * base


class LayerPanel(QWidget):
    """Per-layer visibility with colour swatches plus quick presets."""

    layerToggled = Signal(object, bool)

    PRESETS = {
        "全部": None,
        "金属": [49, 50, 51, 61, 62, 30, 31, 32, 33],
        "有源区": [1, 2, 3, 4, 5, 9, 10, 235],
        "仅M1": [49, 235],
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = None
        self._canvas = None
        self._updating = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        preset_row = QHBoxLayout()
        preset_row.setSpacing(5)
        preset_row.addWidget(QLabel("预设"))
        for name in self.PRESETS:
            btn = QPushButton(name)
            btn.setToolTip("只显示该组图层")
            btn.clicked.connect(lambda _c=False, n=name: self._apply_preset(n))
            preset_row.addWidget(btn)
        preset_row.addStretch(1)
        root.addLayout(preset_row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["层", "名称", "形状数", "面积 µm²"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 58)
        self.table.setColumnWidth(1, 96)
        self.table.setColumnWidth(2, 62)
        self.table.itemChanged.connect(self._item_changed)
        root.addWidget(self.table, 1)

    def set_model(self, model):
        self._model = model
        self._updating = True
        self.table.setRowCount(0)
        if model is not None:
            for layer in model.ordered_layers():
                row = self.table.row_count()
                self.table.insertRow(row)
                check = QTableWidgetItem("%s/%s" % (layer.layer, layer.datatype))
                check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                check.setCheckState(Qt.Checked if layer.visible else Qt.Unchecked)
                check.setData(Qt.UserRole, (layer.layer, layer.datatype))
                check.setForeground(QColor(layer.colour))
                self.table.setItem(row, 0, check)
                self.table.setItem(row, 1, QTableWidgetItem(layer.name))
                self.table.setItem(row, 2, QTableWidgetItem(str(layer.count)))
                self.table.setItem(row, 3, QTableWidgetItem("%.3f" % layer.area_um2))
        self._updating = False

    def sync_from_canvas(self, canvas):
        """Reflect the canvas' current visibility (used after a preset)."""
        self._updating = True
        for row in range(self.table.row_count()):
            item = self.table.item(row, 0)
            key = item.data(Qt.UserRole)
            item.setCheckState(Qt.Checked if canvas.layer_visible(key) else Qt.Unchecked)
        self._updating = False

    def _item_changed(self, item):
        if self._updating or item.column() != 0:
            return
        key = item.data(Qt.UserRole)
        self.layerToggled.emit(key, item.checkState() == Qt.Checked)

    def bind_canvas(self, canvas):
        """Connect this panel to a GdsCanvas: toggles drive it, presets resync."""
        self._canvas = canvas
        self.layerToggled.connect(canvas.set_layer_visible)

    def _apply_preset(self, name):
        if self._model is None:
            return
        wanted = self.PRESETS[name]
        for layer in self._model.ordered_layers():
            key = (layer.layer, layer.datatype)
            visible = (wanted is None) or (layer.layer in wanted)
            self.layerToggled.emit(key, visible)
        if self._canvas is not None:
            self.sync_from_canvas(self._canvas)
