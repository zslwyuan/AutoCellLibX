"""PDK Editor tab: view / edit / save ASTRAN technology rules (.rul) and
Cadence layer maps (.map), with a Chinese+English explanation for every field.

The editing model is ``gui.pdk_editor``: rows keep their original raw text
(lossless round-trip), each cell carries its own explanation, and the raw-text
preview on the right re-renders live from the table edits.
"""
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout,
                               QHeaderView, QLabel, QMessageBox, QPlainTextEdit,
                               QPushButton, QSplitter, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout,
                               QWidget)

from .. import pdk_editor as pdk, paths, theme
from ..widgets.common import Card, KeyValue, faint, h1
from ..widgets.guide import GuidePanel


class _FileEditor(QWidget):
    """One editable PDK file: toolbar + table + explanations + raw preview."""

    fileSaved = Signal(str, str)          # (kind, new_path)

    def __init__(self, title, kind, load_fn, render_fn, parse_fn, parent=None):
        super().__init__(parent)
        self.kind = kind                  # "rul" | "map"
        self.path = ""
        self.rows = []
        self._dirty = False
        self._load_fn = load_fn           # () -> path (the configured default)
        self._render = render_fn          # (row, cells...) -> raw
        self._parse = parse_fn            # (path) -> rows

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        bar = QHBoxLayout()
        bar.addWidget(QLabel(title))
        self.path_label = QLabel("")
        self.path_label.setObjectName("Faint")
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bar.addWidget(self.path_label, 1)
        browse = QPushButton("选择文件…")
        browse.clicked.connect(self._browse)
        bar.addWidget(browse)
        self.reload_btn = QPushButton("重新加载")
        self.reload_btn.setToolTip("从磁盘重新读取，放弃未保存的修改")
        self.reload_btn.clicked.connect(self._reload)
        bar.addWidget(self.reload_btn)
        self.save_btn = QPushButton("保存")
        self.save_btn.setObjectName("Primary")
        self.save_btn.setToolTip("校验并写回当前文件")
        self.save_btn.clicked.connect(self._save)
        bar.addWidget(self.save_btn)
        self.saveas_btn = QPushButton("另存为…")
        self.saveas_btn.clicked.connect(self._save_as)
        bar.addWidget(self.saveas_btn)
        root.addLayout(bar)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)   # panels cannot be squashed flat
        root.addWidget(splitter, 1)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["名称", "值", "单位", "说明", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked |
                                   QAbstractItemView.EditKeyPressed |
                                   QAbstractItemView.SelectedClicked)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setColumnHidden(4, True)
        self.table.itemChanged.connect(self._cell_edited)
        self.table.itemSelectionChanged.connect(self._show_explanation)
        splitter.addWidget(self.table)

        right = QVBoxLayout()
        right.setSpacing(6)
        self.expl = KeyValue()
        right.addWidget(QLabel("选中字段说明 / Field explanation"))
        right.addWidget(self.expl, 1)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(150)
        right.addWidget(QLabel("原始文本（只读预览） / Raw text"))
        right.addWidget(self.preview, 2)
        right_widget = QWidget()
        right_widget.setLayout(right)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        self.status = faint("")
        root.addWidget(self.status)

        self.load()

    # ------------------------------------------------------------------ api
    def load(self):
        """(Re)load from the configured path; safe to call repeatedly."""
        new_path = self._load_fn()
        if self._dirty and new_path == self.path:
            return
        self.path = new_path
        self.rows = self._parse(new_path)
        self._dirty = False
        self._fill_table()
        self._refresh_preview()
        self.path_label.setText(self.path)
        self.path_label.setToolTip(self.path)
        self.save_btn.setEnabled(False)
        self.status.setText("已加载 %d 行（可编辑：双击单元格）"
                            % len([r for r in self.rows if r.cells]))

    def set_dirty(self):
        self._dirty = True
        self.save_btn.setEnabled(True)
        self.path_label.setText(self.path + "  ●未保存")
        self.path_label.setStyleSheet("color:%s; font-weight:600;" % theme.WARN)

    # ------------------------------------------------------------- table
    def _fill_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for row in self.rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for col, (text, _expl, editable) in enumerate(row.cells[:4]):
                item = QTableWidgetItem(text)
                if not editable:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    item.setForeground(QColor(theme.TEXT_DIM))
                item.setData(Qt.UserRole, (r, col))
                self.table.setItem(r, col, item)
            if row.error:
                for col in range(4):
                    item = self.table.item(r, col)
                    if item:
                        item.setForeground(QColor(theme.ERROR))
        # No fixed row height: rows follow the font so text is never cropped.
        self.table.verticalHeader().setDefaultSectionSize(
            self.table.fontMetrics().height() + 12)
        self.table.blockSignals(False)
        self._show_explanation()

    def _cell_edited(self, item):
        if item.column() >= 4:
            return
        r, col = item.row(), item.column()
        if r >= len(self.rows):
            return
        row = self.rows[r]
        text = item.text()
        try:
            if row.kind == "rule":
                name = self.table.item(r, 0).text().strip()
                value = self.table.item(r, 1).text().strip()
                if name in pdk.TEXT_GLOBALS:
                    pass
                elif name in pdk.INT_GLOBALS:
                    pdk.validate_int(value)
                else:
                    pdk.validate_number(value)
                pdk.render_rule_row(row, name, value)
            elif row.kind == "layer":
                name = self.table.item(r, 0).text().strip()
                cif = self.table.item(r, 1).text().strip()
                gdsii = self.table.item(r, 2).text().strip()
                tech = self.table.item(r, 3).text().strip()
                pdk.validate_int(gdsii)
                pdk.render_layer_row(row, name, cif, gdsii, tech)
            else:  # map "row"
                name = self.table.item(r, 0).text().strip()
                purpose = self.table.item(r, 1).text().strip()
                stream = self.table.item(r, 2).text().strip()
                datatype = self.table.item(r, 3).text().strip()
                pdk.validate_int(stream)
                pdk.validate_int(datatype)
                pdk.render_map_row(row, name, purpose, stream, datatype)
            row.error = None
            self._resync_row(r)
        except ValueError as exc:
            self.status.setText("第 %d 行：%s" % (r + 1, exc))
            self.status.setStyleSheet("color:%s; font-weight:600;" % theme.ERROR)
            return
        self.status.setText("")
        self.set_dirty()
        self._refresh_preview()

    def _resync_row(self, r):
        """Push the re-rendered cells (explanations, unit) back into the table."""
        row = self.rows[r]
        self.table.blockSignals(True)
        for col, (text, expl, _editable) in enumerate(row.cells[:4]):
            item = self.table.item(r, col)
            if item is None:
                continue
            if item.text() != text:
                item.setText(text)
            item.setData(Qt.ToolTipRole, expl)
        self.table.blockSignals(False)

    def _show_explanation(self):
        self.expl.clear()
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        r = rows[0].row()
        if not (0 <= r < len(self.rows)):
            return
        row = self.rows[r]
        self.expl.add("类型", {"rule": "设计规则", "layer": "ASTRAN 层表行",
                               "row": "层映射行", "comment": "注释",
                               "blank": "空行"}.get(row.kind, row.kind))
        for col, (text, expl, _editable) in enumerate(row.cells[:4]):
            label = ["名称", "值", "单位", "说明"][col]
            self.expl.add(label, "%s — %s" % (text, expl))

    # ---------------------------------------------------------------- text
    def _refresh_preview(self):
        self.preview.setPlainText(
            pdk.rul_to_text(self.rows) if self.kind == "rul"
            else pdk.map_to_text(self.rows))

    # ---------------------------------------------------------------- actions
    def _browse(self):
        filt = ("ASTRAN rule files (*.rul);;All files (*)" if self.kind == "rul"
                else "Layer maps (*.map *.txt);;All files (*)")
        path, _ = QFileDialog.getOpenFileName(self, "选择文件", "", filt)
        if path:
            if self._dirty and not self._confirm_discard():
                return
            self.path = os.path.abspath(path)
            self.rows = self._parse(self.path)
            self._dirty = False
            self._fill_table()
            self._refresh_preview()
            self.path_label.setText(self.path)
            self.path_label.setToolTip(self.path)
            self.save_btn.setEnabled(False)
            self._publish_path()
            self.status.setText("已加载 %s" % self.path)

    def _reload(self):
        if self._dirty and not self._confirm_discard():
            return
        self.load()

    def _save(self):
        ok, msg = pdk.validate_rows(self.rows)
        if not ok:
            self.status.setText(msg)
            self.status.setStyleSheet("color:%s; font-weight:600;" % theme.ERROR)
            return
        try:
            with open(self.path, "w", newline="\n", encoding="utf-8") as fh:
                fh.write(pdk.rul_to_text(self.rows) if self.kind == "rul"
                         else pdk.map_to_text(self.rows))
        except OSError as exc:
            self.status.setText("保存失败：%s" % exc)
            self.status.setStyleSheet("color:%s; font-weight:600;" % theme.ERROR)
            return
        self._dirty = False
        self.save_btn.setEnabled(False)
        self.path_label.setText(self.path)
        self.path_label.setStyleSheet("")
        self.status.setText("✔ 已保存 %s" % self.path)
        self.status.setStyleSheet("color:%s;" % theme.OK)
        self._publish_path()

    def _save_as(self):
        filt = ("ASTRAN rule files (*.rul);;All files (*)" if self.kind == "rul"
                else "Layer maps (*.map *.txt);;All files (*)")
        path, _ = QFileDialog.getSaveFileName(self, "另存为", self.path, filt)
        if not path:
            return
        self.path = os.path.abspath(path)
        self._save()

    def _publish_path(self):
        """Tell the window the configured PDK file may have moved."""
        self.fileSaved.emit(self.kind, self.path)

    def _confirm_discard(self):
        reply = QMessageBox.question(
            self, "放弃修改？", "当前文件有未保存的修改，确定放弃？")
        return reply == QMessageBox.Yes


class PdkTab(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)
        root.addWidget(h1("PDK 编辑器 / PDK editor"))
        root.addWidget(GuidePanel([
            ("查看", "两个页签分别打开工艺规则 (.rul) 与层映射 (.map)；"
             "左侧表格逐行显示，右侧给出选中字段的中英解释与原始文本。"),
            ("编辑", "双击单元格修改；规则值必须是数值，流号必须是整数，"
             "非法输入会即时提示。注释与空行原样保留。"),
            ("保存", "「保存」写回当前文件；「另存为…」写新文件并自动设为运行配置；"
             "「重新加载」放弃修改。"),
            ("生效", "保存的 .rul 在下次运行 ASTRAN 时生效（基线需重算）；"
             "保存的 .map 立即作用于版图查看器的层名。"),
        ]))
        root.addWidget(faint(
            "直接编辑 PDK 文本：工艺规则（间距/包含/宽度，µm）与层映射（层名/用途 → "
            "GDSII 流号）。修改后请重新运行并做 DRC 验证。"))

        tabs = QTabWidget()
        self.rul_editor = _FileEditor(
            "工艺规则 technology rules (.rul)", "rul",
            load_fn=lambda: self.ctx.state.config.technology(),
            render_fn=None, parse_fn=pdk.parse_rul_file)
        self.map_editor = _FileEditor(
            "层映射 layer map (.map)", "map",
            load_fn=lambda: self.ctx.state.config.layer_map(),
            render_fn=None, parse_fn=pdk.parse_map_file)
        tabs.addTab(self.rul_editor, "工艺规则 .rul")
        tabs.addTab(self.map_editor, "层映射 .map")
        root.addWidget(tabs, 1)

        self.rul_editor.fileSaved.connect(self._on_saved)
        self.map_editor.fileSaved.connect(self._on_saved)

    def _on_saved(self, kind, path):
        cfg = self.ctx.state.config
        if kind == "rul":
            cfg.technology_file = path
        else:
            cfg.layer_map_file = path
        self.ctx.state.configChanged.emit()
        self.ctx.log("PDK 文件已保存：%s" % path, "ok")

    def refresh(self):
        self.rul_editor.load()
        self.map_editor.load()
