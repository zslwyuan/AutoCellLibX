"""A pan/zoom viewer for the pattern figures (COMPLEX<n>.png)."""
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QPainter, QPen, QPixmap, QColor
from PySide6.QtWidgets import QLabel, QWidget

from .. import theme


class ZoomableImage(QWidget):
    """Wheel zooms, left-drag pans, double-click fits, F fits."""

    imageLoaded = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 260)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._pm = QPixmap()
        self._zoom = 1.0
        self._offset = QPointF(0, 0)
        self._drag_from = None
        self._fit_pending = True
        self._caption = ""
        self._placeholder = "该模式尚无子图预览\nNo pattern figure yet"

    def set_image(self, path, caption=""):
        self._caption = caption
        if path:
            self._pm = QPixmap(path)
        else:
            self._pm = QPixmap()
        self._fit_pending = True
        if not self._pm.isNull():
            self.imageLoaded.emit(path)
        self.update()

    def set_text(self, message):
        self._pm = QPixmap()
        self._placeholder = message
        self.update()

    def fit(self):
        self._fit_pending = True
        self.update()

    def has_image(self):
        return not self._pm.isNull()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0a0e13"))
        if self._pm.isNull():
            painter.setPen(QColor(theme.TEXT_FAINT))
            painter.drawText(self.rect(), Qt.AlignCenter, self._placeholder)
            return
        if self._fit_pending:
            self._fit()
        painter.translate(self._offset)
        painter.scale(self._zoom, self._zoom)
        painter.setRenderHint(QPainter.SmoothPixmapTransform,
                              self._zoom < 1.0)
        painter.drawPixmap(0, 0, self._pm)
        painter.resetTransform()
        if self._caption:
            painter.setPen(QColor(theme.TEXT_DIM))
            painter.drawText(10, 18, self._caption)

    def _fit(self):
        self._fit_pending = False
        if self._pm.isNull():
            return
        w = max(self._pm.width(), 1)
        h = max(self._pm.height(), 1)
        margin = 16
        sx = (self.width() - 2 * margin) / w
        sy = (self.height() - 2 * margin) / h
        self._zoom = max(0.02, min(sx, sy))
        self._offset = QPointF(self.width() / 2.0 - w * self._zoom / 2.0,
                               self.height() / 2.0 - h * self._zoom / 2.0)

    def wheelEvent(self, event):
        if self._pm.isNull():
            return
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        pos = event.position()
        before = QPointF((pos.x() - self._offset.x()) / self._zoom,
                         (pos.y() - self._offset.y()) / self._zoom)
        self._zoom = max(0.02, min(40.0, self._zoom * factor))
        self._offset = QPointF(pos.x() - before.x() * self._zoom,
                               pos.y() - before.y() * self._zoom)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_from = event.position()

    def mouseMoveEvent(self, event):
        if self._drag_from is not None and event.buttons() & Qt.LeftButton:
            self._offset += event.position() - self._drag_from
            self._drag_from = event.position()
            self.update()

    def mouseReleaseEvent(self, _event):
        self._drag_from = None

    def mouseDoubleClickEvent(self, _event):
        self.fit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F:
            self.fit()
        else:
            super().keyPressEvent(event)
