"""A collapsible per-page usage guide.

Every tab gets one of these above its content, so a first-time user sees what
the page does and how to drive it without reading documentation.  The body is
a numbered list of short step lines; clicking the header toggles it.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from .. import theme


class GuidePanel(QWidget):
    def __init__(self, lines, title="使用引导 / Guide", parent=None):
        """``lines``: list of (step_text, explanation) shown as numbered rows."""
        super().__init__(parent)
        self._expanded = True

        card = QFrame()
        card.setObjectName("Card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 8, 12, 10)
        lay.setSpacing(4)

        head = QHBoxLayout()
        head.setSpacing(8)
        bulb = QLabel("💡")
        self.title = QLabel(title)
        self.title.setStyleSheet("font-weight:600; color:%s;" % theme.TEXT)
        head.addWidget(bulb)
        head.addWidget(self.title)
        head.addStretch(1)
        self.btn = QPushButton("收起 ▴")
        self.btn.setFlat(True)
        self.btn.setStyleSheet(
            "QPushButton { color:%s; border:none; padding:2px 8px; }"
            "QPushButton:hover { color:%s; }" % (theme.TEXT_DIM, theme.TEXT))
        self.btn.clicked.connect(self.toggle)
        head.addWidget(self.btn)
        lay.addLayout(head)

        self._body = QWidget()
        body_lay = QVBoxLayout(self._body)
        body_lay.setContentsMargins(24, 2, 0, 0)
        body_lay.setSpacing(3)
        for i, (step, text) in enumerate(lines):
            row = QHBoxLayout()
            row.setSpacing(9)
            num = QLabel(str(i + 1))
            num.setFixedSize(17, 17)
            num.setAlignment(Qt.AlignCenter)
            num.setStyleSheet(
                "background:%s; color:#0b0f14; border-radius:8px;"
                "font-weight:700; font-size:10px;" % theme.ACCENT)
            label = QLabel("%s — %s" % (step, text))
            label.setWordWrap(True)
            label.setObjectName("Subtle")
            label.setStyleSheet("color:%s;" % theme.TEXT_DIM)
            row.addWidget(num, 0, Qt.AlignTop)
            row.addWidget(label, 1)
            body_lay.addLayout(row)
        lay.addWidget(self._body)

    def toggle(self):
        self._expanded = not self._expanded
        self._body.setVisible(self._expanded)
        self.btn.setText("收起 ▴" if self._expanded else "展开 ▾")

    def set_guide(self, lines):
        """Replace the steps (used when a page's content depends on context)."""
        body_lay = self._body.layout()
        while body_lay.count():
            item = body_lay.takeAt(0)
            if item.layout() is not None:
                while item.layout().count():
                    w = item.layout().takeAt(0).widget()
                    if w is not None:
                        w.deleteLater()
        for i, (step, text) in enumerate(lines):
            row = QHBoxLayout()
            row.setSpacing(9)
            num = QLabel(str(i + 1))
            num.setFixedSize(17, 17)
            num.setAlignment(Qt.AlignCenter)
            num.setStyleSheet(
                "background:%s; color:#0b0f14; border-radius:8px;"
                "font-weight:700; font-size:10px;" % theme.ACCENT)
            label = QLabel("%s — %s" % (step, text))
            label.setWordWrap(True)
            label.setObjectName("Subtle")
            row.addWidget(num, 0, Qt.AlignTop)
            row.addWidget(label, 1)
            body_lay.addLayout(row)
