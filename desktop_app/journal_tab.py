"""Journal entry viewer (Phase 5 GL register).

**F5** (when this tab or its children have focus) runs the same reload as **Refresh** (entry list + lines).
**Help → More tab shortcuts (F5)…**; entry list and line-detail **right-click** menus set **QAction** tooltips for **Keyboard shortcuts…** and **Copy** (including empty area).
The tab **root** has a hover hint. Date filter **labels**, fields, the entry / lines panes, the **splitter**, and footer **F5** hint use **setToolTip** on hover.
"""

from __future__ import annotations

import sqlite3
from functools import partial

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSplitter,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from desktop_app.more_main_tabs_shortcuts import (
    show_more_main_tabs_keyboard_shortcuts_dialog,
)
from desktop_app.qt_mnemonic import (
    escape_ampersand_for_qt,
    message_box_critical_ok,
    message_box_information_ok,
)
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
        self.setToolTip(
            "General journal: browse entries and GL lines with a date filter; export CSV (F5 refreshes when Journal has focus). "
            "Same company SQLite database as other main tabs; File → Backup / Restore (probooks.backup)."
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        row = QHBoxLayout()
        lbl_j_from = QLabel("Filter from (yyyy-mm-dd):")
        lbl_j_from.setToolTip(
            "Lower bound for journal entry dates (ISO yyyy-mm-dd); the field to the right sets the value."
        )
        row.addWidget(lbl_j_from)
        self._start = QLineEdit()
        self._start.setToolTip(
            "Earliest entry date to include (ISO yyyy-mm-dd), optional; blank means no lower bound."
        )
        row.addWidget(self._start)
        lbl_j_to = QLabel("to:")
        lbl_j_to.setToolTip(
            "Upper bound for journal entry dates; use the field to the right (optional)."
        )
        row.addWidget(lbl_j_to)
        self._end = QLineEdit()
        self._end.setToolTip(
            "Latest entry date to include (ISO yyyy-mm-dd), optional; blank means no upper bound."
        )
        row.addWidget(self._end)
        b = QPushButton("Refresh")
        b.setToolTip(
            "Reload the journal entry list and line detail for the current date filter. "
            "Shortcut: F5 (when Journal has focus)."
        )
        b.clicked.connect(self._refresh_list)
        row.addWidget(b)
        btn_export = QPushButton("Export CSV…")
        btn_export.setToolTip(
            "Export journal entries in the current date filter range to CSV."
        )
        btn_export.clicked.connect(self._export_csv)
        row.addWidget(btn_export)
        row.addStretch()
        layout.addLayout(row)

        split = QSplitter(Qt.Orientation.Horizontal)
        self._list = QListWidget()
        self._list.setToolTip(
            "Journal entries matching the date filter; select one to show its lines on the right. "
            "Right-click for Keyboard shortcuts… (including on empty area)."
        )
        self._list.currentRowChanged.connect(self._show_lines)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_journal_list_context_menu)
        split.addWidget(self._list)

        self._lines = QTableWidget()
        self._lines.setColumnCount(5)
        self._lines.setHorizontalHeaderLabels(
            ["Account", "Debit", "Credit", "Description", "Entry memo"]
        )
        self._lines.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._lines.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._lines.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._lines.customContextMenuRequested.connect(self._on_lines_context_menu)
        self._lines.setSortingEnabled(True)
        self._lines.setToolTip(
            "GL lines for the selected journal entry. Right-click for Keyboard shortcuts… "
            "(including on empty area)."
        )
        split.addWidget(self._lines)
        split.setSizes([260, 600])
        split.setToolTip(
            "Entries list on the left; general-ledger lines for the selected entry on the right."
        )
        layout.addWidget(split)

        tip = QLabel(
            "F5 reloads the entry list and lines for the current date filter. "
            "Help → More tab shortcuts (F5)…; right-click either pane for Keyboard shortcuts…."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #A0A0B0; font-size: 11px;")
        tip.setToolTip(
            "Same as the text above: F5 Refresh; Help menu lists chords shared with COA, Reports, and Audit."
        )
        layout.addWidget(tip)

        sc_refresh = QShortcut(QKeySequence("F5"), self)
        sc_refresh.setContext(Qt.WidgetWithChildrenShortcut)
        sc_refresh.activated.connect(self._refresh_list)

        self._entries: list = []

    def _on_journal_list_context_menu(self, pos):
        idx = self._list.indexAt(pos)
        m = QMenu(self)
        act_keys = m.addAction(
            "Keyboard shortcuts…",
            lambda: show_more_main_tabs_keyboard_shortcuts_dialog(self),
        )
        act_keys.setToolTip(
            "Same summary as Help → More tab shortcuts (F5)… (Journal, COA, Reports, Audit chords). "
            "Company .db safety: File → Backup / Restore (probooks.backup)."
        )
        if not idx.isValid():
            m.exec(self._list.viewport().mapToGlobal(pos))
            return
        row = idx.row()
        m.addSeparator()
        act_copy = m.addAction(
            "Copy entry line",
            partial(copy_qlistwidget_row_text, self._list, row),
        )
        act_copy.setToolTip(
            "Copy the selected journal entry summary line as plain text. "
            "Company .db safety: File → Backup / Restore (probooks.backup)."
        )
        m.exec(self._list.viewport().mapToGlobal(pos))

    def _on_lines_context_menu(self, pos):
        idx = self._lines.indexAt(pos)
        m = QMenu(self)
        act_keys = m.addAction(
            "Keyboard shortcuts…",
            lambda: show_more_main_tabs_keyboard_shortcuts_dialog(self),
        )
        act_keys.setToolTip(
            "Same summary as Help → More tab shortcuts (F5)… (Journal lines pane, F5 refresh). "
            "Company .db safety: File → Backup / Restore (probooks.backup)."
        )
        if not idx.isValid():
            m.exec(self._lines.viewport().mapToGlobal(pos))
            return
        row = idx.row()
        m.addSeparator()
        act_copy = m.addAction(
            "Copy row", partial(copy_table_row_as_tsv, self._lines, row)
        )
        act_copy.setToolTip(
            "Copy this GL line row as tab-separated text for pasting into a spreadsheet or editor. "
            "Company .db safety: File → Backup / Restore (probooks.backup)."
        )
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
            message_box_critical_ok(
                self,
                "Export failed",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; check the path, permissions, and disk space.",
            )
            return
        message_box_information_ok(
            self,
            "Export complete",
            f"Exported {n} journal line(s) to:\n{escape_ampersand_for_qt(path)}",
            ok_tip="Close; open the CSV from the path shown.",
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

