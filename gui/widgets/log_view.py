"""The live console: levelled, filterable, searchable, saveable."""
from collections import deque

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QPushButton,
                               QVBoxLayout, QWidget)

from .. import theme

LEVEL_ORDER = ["error", "warn", "ok", "accent", "info", "debug"]

LEVEL_COLOUR = {
    "error": theme.ERROR,
    "warn": theme.WARN,
    "ok": theme.OK,
    "accent": theme.ACCENT,
    "info": theme.TEXT_DIM,
    "debug": theme.TEXT_FAINT,
}

LEVEL_LABEL = {
    "error": "错误", "warn": "警告", "ok": "完成", "accent": "阶段",
    "info": "信息", "debug": "调试",
}


class LogView(QWidget):
    """A bounded console with level filters and a text search."""

    MAX_ENTRIES = 4000

    entryAdded = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries = deque(maxlen=self.MAX_ENTRIES)
        self._enabled = {lvl: True for lvl in LEVEL_ORDER}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        bar = QHBoxLayout()
        bar.setSpacing(8)

        for lvl in LEVEL_ORDER:
            cb = QCheckBox(LEVEL_LABEL[lvl])
            cb.setChecked(True)
            cb.setToolTip("显示/隐藏 %s 级别" % lvl)
            cb.toggled.connect(lambda on, l=lvl: self._set_level(l, on))
            setattr(self, "_cb_" + lvl, cb)
            bar.addWidget(cb)

        bar.addSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("过滤文本 / filter text…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _t: self._rerender())
        bar.addWidget(self.search, 1)

        self.autoscroll = QCheckBox("自动滚动")
        self.autoscroll.setChecked(True)
        bar.addWidget(self.autoscroll)

        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self.clear)
        bar.addWidget(clear_btn)

        save_btn = QPushButton("导出")
        save_btn.clicked.connect(self._save)
        bar.addWidget(save_btn)

        root.addLayout(bar)

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(self.MAX_ENTRIES + 10)
        self.view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.view.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        root.addWidget(self.view, 1)

    # ------------------------------------------------------------------ api
    def append(self, message, level="info"):
        level = level if level in self._enabled else "info"
        self._entries.append((level, message))
        self.entryAdded.emit(message, level)
        if not self._visible(level, message):
            return
        self._append_block(level, message)
        if self.autoscroll.isChecked():
            self.view.moveCursor(QTextCursor.End)

    def clear(self):
        self._entries.clear()
        self.view.clear()

    def text(self):
        return "\n".join("".join(m) for _l, m in self._entries)

    # ------------------------------------------------------------- internals
    def _visible(self, level, message):
        if not self._enabled.get(level, True):
            return False
        needle = self.search.text().strip().lower()
        return (not needle) or (needle in message.lower())

    def _append_block(self, level, message):
        from html import escape
        colour = LEVEL_COLOUR.get(level, theme.TEXT_DIM)
        prefix = {"error": "✖ ", "warn": "▲ ", "ok": "✔ ",
                  "accent": "▸ ", "info": "", "debug": "· "}.get(level, "")
        html = ('<span style="color:%s;">%s%s</span>'
                % (colour, prefix, escape(str(message))))
        self.view.appendHtml(html)

    def _rerender(self):
        self.view.setUpdatesEnabled(False)
        self.view.clear()
        for level, message in self._entries:
            if self._visible(level, message):
                self._append_block(level, message)
        self.view.setUpdatesEnabled(True)
        if self.autoscroll.isChecked():
            self.view.moveCursor(QTextCursor.End)

    def _set_level(self, level, on):
        self._enabled[level] = on
        self._rerender()

    def _save(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出日志 / Save log", "autocellibx_run.log",
            "Log files (*.log *.txt);;All files (*)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.text() + "\n")
