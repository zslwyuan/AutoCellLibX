"""Small, reusable presentation pieces (cards, labels, key/value rows)."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QVBoxLayout, QWidget)

from .. import theme


def h1(text):
    lab = QLabel(text)
    lab.setObjectName("H1")
    return lab


def h2(text):
    lab = QLabel(text)
    lab.setObjectName("H2")
    return lab


def subtle(text):
    lab = QLabel(text)
    lab.setObjectName("Subtle")
    lab.setWordWrap(True)
    return lab


def faint(text):
    lab = QLabel(text)
    lab.setObjectName("Faint")
    lab.setWordWrap(True)
    return lab


def badge(text, colour=None):
    lab = QLabel(text)
    lab.setObjectName("Badge")
    if colour:
        lab.setStyleSheet("color: %s; border-color: %s;" % (colour, colour))
    return lab


def hline():
    line = QFrame()
    line.setObjectName("HLine")
    line.setFrameShape(QFrame.HLine)
    line.setFixedHeight(1)
    return line


class Card(QFrame):
    """A titled panel with an optional right-aligned header widget."""

    def __init__(self, title=None, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(14, 12, 14, 12)
        self._outer.setSpacing(8)
        self.header = None
        if title is not None:
            row = QHBoxLayout()
            row.setSpacing(8)
            self._title = h2(title)
            row.addWidget(self._title)
            row.addStretch(1)
            self.header = row
            self._outer.addLayout(row)
        self.body = QVBoxLayout()
        self.body.setSpacing(6)
        self._outer.addLayout(self.body)

    def add(self, widget):
        self.body.addWidget(widget)
        return widget

    def add_layout(self, layout):
        self.body.addLayout(layout)
        return layout

    def set_header_widget(self, widget):
        if self.header is not None:
            self.header.addWidget(widget)

    def set_title(self, text):
        if hasattr(self, "_title"):
            self._title.setText(text)


class StatTile(QFrame):
    """A compact number + caption tile for the overview/status strips."""

    def __init__(self, caption, value="--", hint="", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setSpacing(1)
        self.caption = QLabel(caption)
        self.caption.setObjectName("Faint")
        self.value = QLabel(value)
        self.value.setStyleSheet("font-size: 20px; font-weight: 600;")
        self.hint = QLabel(hint)
        self.hint.setObjectName("Faint")
        lay.addWidget(self.caption)
        lay.addWidget(self.value)
        lay.addWidget(self.hint)

    def set_value(self, value, colour=None):
        self.value.setText(str(value))
        self.value.setStyleSheet(
            "font-size: 20px; font-weight: 600; color: %s;"
            % (colour or theme.TEXT))

    def set_hint(self, text):
        self.hint.setText(text)


class KeyValue(QWidget):
    """A wrapped grid of key/value rows, used in the inspection panels."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(14)
        self._grid.setVerticalSpacing(4)
        self._grid.setColumnStretch(1, 1)
        self._row = 0

    def clear(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._row = 0

    def add(self, key, value, value_colour=None):
        k = QLabel(str(key))
        k.setObjectName("Faint")
        v = QLabel(str(value))
        v.setWordWrap(True)
        v.setTextInteractionFlags(Qt.TextSelectableByMouse)
        if value_colour:
            v.setStyleSheet("color: %s;" % value_colour)
        self._grid.addWidget(k, self._row, 0, Qt.AlignTop)
        self._grid.addWidget(v, self._row, 1, Qt.AlignTop)
        self._row += 1
        return v

    def add_span(self, widget):
        self._grid.addWidget(widget, self._row, 0, 1, 2)
        self._row += 1
        return widget


class StatusDot(QWidget):
    """A coloured dot + label, used for stage state and health checks."""

    COLOURS = {"pending": theme.TEXT_FAINT, "running": theme.RUN,
               "done": theme.OK, "ok": theme.OK, "skipped": theme.TEXT_DIM,
               "failed": theme.ERROR, "warn": theme.WARN, "error": theme.ERROR}

    def __init__(self, text="", state="pending", parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.dot = QLabel()
        self.dot.setFixedSize(9, 9)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        row.addWidget(self.dot, 0, Qt.AlignTop)
        row.addWidget(self.label, 1)
        self.set_state(state)
        self.setText(text)

    def set_state(self, state):
        colour = self.COLOURS.get(state, theme.TEXT_DIM)
        self.dot.setStyleSheet(
            "background: %s; border-radius: 4px;" % colour)
        self.label.setStyleSheet("color: %s;" % (
            theme.TEXT if state in ("running", "done", "ok") else colour))

    def setText(self, text):
        self.label.setText(text)
