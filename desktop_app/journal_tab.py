"""Journal entry viewer (Phase 5 GL register)."""

from __future__ import annotations

import sqlite3
from functools import partial

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QMenu,
    QPushButton,
    QSplitter,
    QTableWidget,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from desktop_app.qt_mnemonic import escape_ampersand_for_qt
from desktop_app.table_clipboard import (
    QLIST_PLAIN_TEXT_ROLE,
    NumericAmountTableItem,
    copy_qlistwidget_row_text,
    copy_table_row_as_tsv,
    plain_display_table_item,
)
from probooksai.gl import GLDatabase, write_journal_export_csv


class JournalTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._gl = GLDatabase(conn)
        self._build_ui()
        self._refresh_list()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        row = QHBoxLayout()
        row.addWidget(QLabel("Filter from (yyyy-mm-dd):"))
        self._start = QLineEdit()
        row.addWidget(self._start)
        row.addWidget(QLabel("to:"))
        self._end = QLineEdit()
        row.addWidget(self._end)
        b = QPushButton("Refresh")
        b.clicked.connect(self._refresh_list)
        row.addWidget(b)
        row.addWidget(QPushButton("Export CSV…", clicked=self._export_csv))
        row.addStretch()
        layout.addLayout(row)

        split = QSplitter(Qt.Orientation.Horizontal)
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._show_lines)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_journal_list_context_menu)
        split.addWidget(self._list)

        self._lines = QTableWidget()
        self._lines.setColumnCount(5)
        self._lines.setHorizontalHeaderLabels(
            ["Account", "Debit", "Credit", "Description", "Entry memo"]
        )
        self._lines.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._lines.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._lines.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._lines.customContextMenuRequested.connect(self._on_lines_context_menu)
        self._lines.setSortingEnabled(True)
        split.addWidget(self._lines)
        split.setSizes([260, 600])
        layout.addWidget(split)

        self._entries: list = []

    def _on_journal_list_context_menu(self, pos):
        idx = self._list.indexAt(pos)
        if not idx.isValid():
            return
        row = idx.row()
        m = QMenu(self)
        m.addAction(
            "Copy entry line",
            partial(copy_qlistwidget_row_text, self._list, row),
        )
        m.exec(self._list.viewport().mapToGlobal(pos))

    def _on_lines_context_menu(self, pos):
        idx = self._lines.indexAt(pos)
        if not idx.isValid():
            return
        row = idx.row()
        m = QMenu(self)
        m.addAction("Copy row", partial(copy_table_row_as_tsv, self._lines, row))
        m.exec(self._lines.viewport().mapToGlobal(pos))

    def _refresh_list(self):
        self._list.clear()
        start = self._start.text().strip() or None
        end = self._end.text().strip() or None
        self._entries = self._gl.list_journal_entries(start, end)
        for e in self._entries:
            memo = (e["memo"] or "")[:60]
            label = f"{e['entry_date']}  #{e['id']}  {memo}"
            it = QListWidgetItem(escape_ampersand_for_qt(label))
            it.setData(Qt.ItemDataRole.UserRole, e["id"])
            it.setData(QLIST_PLAIN_TEXT_ROLE, label)
            self._list.addItem(it)
        if len(self._entries) > 0:
            self._list.setCurrentRow(0)

    def _export_csv(self):
        start = self._start.text().strip() or None
        end = self._end.text().strip() or None
        rows = self._gl.journal_export_rows(start, end)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export journal lines",
            "journal_lines.csv",
            "CSV (*.csv);;All Files (*.*)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            n = write_journal_export_csv(path, rows)
        except OSError as exc:
            QMessageBox.critical(
                self, "Export failed", escape_ampersand_for_qt(str(exc))
            )
            return
        QMessageBox.information(
            self,
            "Export complete",
            f"Exported {n} journal line(s) to:\n{escape_ampersand_for_qt(path)}",
        )

    def _show_lines(self, row: int):
        if row < 0 or row >= self._list.count():
            self._lines.setRowCount(0)
            return
        it = self._list.item(row)
        if it is None:
            self._lines.setRowCount(0)
            return
        eid = it.data(Qt.ItemDataRole.UserRole)
        if eid is None:
            self._lines.setRowCount(0)
            return
        try:
            eid_int = int(eid)
        except (TypeError, ValueError):
            self._lines.setRowCount(0)
            return
        entry = self._gl.get_journal_entry(eid_int)
        lines = self._gl.get_entry_lines(eid_int)
        self._lines.setSortingEnabled(False)
        self._lines.setRowCount(len(lines))
        memo = entry["memo"] if entry else ""
        align_rc = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        for r, ln in enumerate(lines):
            acct = ln["account"] or ""
            self._lines.setItem(r, 0, plain_display_table_item(acct))
            debit = float(ln["debit"] or 0)
            credit = float(ln["credit"] or 0)
            d_it = NumericAmountTableItem(debit)
            d_it.setTextAlignment(align_rc)
            self._lines.setItem(r, 1, d_it)
            c_it = NumericAmountTableItem(credit)
            c_it.setTextAlignment(align_rc)
            self._lines.setItem(r, 2, c_it)
            desc = ln["description"] or ""
            self._lines.setItem(r, 3, plain_display_table_item(desc))
            mem = memo or ""
            self._lines.setItem(r, 4, plain_display_table_item(mem))
        self._lines.setSortingEnabled(True)
