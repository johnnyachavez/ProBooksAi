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
from desktop_app.qt_combo_ids import coerce_combo_int_id
from desktop_app.qt_mnemonic import (
    CSV_EXPORT_OK_TIP_SUFFIX,
    escape_ampersand_for_qt,
    message_box_critical_ok,
    message_box_information_ok,
    message_box_question_yes_no,
    message_box_warning_ok,
)
from desktop_app.flexible_date import (
    attach_line_edit_us_date_normalization,
    line_edit_to_iso_or_raw,
)
from desktop_app.table_clipboard import (
    CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX,
    QLIST_PLAIN_TEXT_ROLE,
    VIEW_BANK_REGISTER_KEYS_TOOLTIP,
    NumericAmountTableItem,
    copy_qlistwidget_row_text,
    copy_table_row_as_tsv,
    plain_display_table_item,
)
from probooksai.gl import GLDatabase, write_journal_export_csv


class JournalTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, coa_list: list[str] | None = None, parent=None):
        super().__init__(parent)
        self._gl = GLDatabase(conn)
        self._coa_list: list[str] = coa_list or []
        self._build_ui()
        self._refresh_list()

    def refresh_coa(self, coa_list: list[str]) -> None:
        """Update the COA list used in the entry editor (called when COA changes)."""
        self._coa_list = coa_list

    def _build_ui(self):
        self.setToolTip(
            "General journal: browse entries and GL lines with a date filter; export CSV (UTF-8 BOM for Excel; "
            "F5 refreshes when Journal has focus). "
            "Same company SQLite database as other main tabs; File → Backup / Restore (probooks.backup)."
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        row = QHBoxLayout()
        lbl_j_from = QLabel("Filter from:")
        lbl_j_from.setToolTip(
            "Lower bound for journal entry dates; type flexibly, shown as MM/DD/YYYY when valid; "
            "queries use yyyy-mm-dd when parsing succeeds."
        )
        row.addWidget(lbl_j_from)
        self._start = QLineEdit()
        self._start.setToolTip(
            "Earliest entry date to include, optional; blank means no lower bound. "
            "Flexible US-style entry; normalized to MM/DD/YYYY on commit when valid."
        )
        attach_line_edit_us_date_normalization(self._start)
        row.addWidget(self._start)
        lbl_j_to = QLabel("to:")
        lbl_j_to.setToolTip(
            "Upper bound for journal entry dates; use the field to the right (optional)."
        )
        row.addWidget(lbl_j_to)
        self._end = QLineEdit()
        self._end.setToolTip(
            "Latest entry date to include, optional; blank means no upper bound. "
            "Flexible US-style entry; normalized to MM/DD/YYYY on commit when valid."
        )
        attach_line_edit_us_date_normalization(self._end)
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
            "Export journal entries in the current date filter range to CSV. "
            "UTF-8 with BOM for Excel."
        )
        btn_export.clicked.connect(self._export_csv)
        row.addWidget(btn_export)

        row.addSpacing(16)
        btn_new = QPushButton("✚  New Entry")
        btn_new.setToolTip(
            "Create a new manually balanced journal entry. "
            "Debits must equal credits to save."
        )
        btn_new.clicked.connect(self._on_new_entry)
        row.addWidget(btn_new)

        self._btn_edit = QPushButton("✏  Edit Entry")
        self._btn_edit.setToolTip("Edit the selected journal entry's date, memo, and lines.")
        self._btn_edit.setEnabled(False)
        self._btn_edit.clicked.connect(self._on_edit_selected)
        row.addWidget(self._btn_edit)

        self._btn_delete = QPushButton("🗑  Delete Entry")
        self._btn_delete.setToolTip(
            "Permanently delete the selected journal entry and all its lines. "
            "Back up with File → Backup first."
        )
        self._btn_delete.setEnabled(False)
        self._btn_delete.clicked.connect(self._on_delete_selected)
        row.addWidget(self._btn_delete)

        row.addStretch()
        layout.addLayout(row)

        split = QSplitter(Qt.Orientation.Horizontal)
        self._list = QListWidget()
        self._list.setToolTip(
            "Journal entries matching the date filter; select one to show its lines on the right. "
            "Toolbar Export CSV uses UTF-8 BOM for Excel. "
            "Right-click for Keyboard shortcuts… (including on empty area)."
        )
        self._list.currentRowChanged.connect(self._show_lines)
        self._list.currentRowChanged.connect(self._update_entry_buttons)
        self._list.doubleClicked.connect(lambda _: self._on_edit_selected())
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
            "GL lines for the selected journal entry. Toolbar Export CSV uses UTF-8 BOM for Excel. "
            "Right-click for Keyboard shortcuts… "
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
            "Export CSV uses UTF-8 BOM for Excel. "
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

    # ── Button state ──────────────────────────────────────────────────────────

    def _update_entry_buttons(self, row: int = -1) -> None:
        has_sel = row >= 0 and row < self._list.count()
        self._btn_edit.setEnabled(has_sel)
        self._btn_delete.setEnabled(has_sel)

    def _selected_entry_id(self) -> int | None:
        row = self._list.currentRow()
        if row < 0:
            return None
        it = self._list.item(row)
        return coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole)) if it else None

    # ── New / Edit / Delete ───────────────────────────────────────────────────

    def _on_new_entry(self) -> None:
        from desktop_app.journal_entry_dialog import JournalEntryDialog
        dlg = JournalEntryDialog(self._gl, entry_id=None, coa_list=self._coa_list, parent=self)
        if dlg.exec():
            self._refresh_list()

    def _on_edit_selected(self) -> None:
        eid = self._selected_entry_id()
        if eid is None:
            return
        from desktop_app.journal_entry_dialog import JournalEntryDialog
        dlg = JournalEntryDialog(self._gl, entry_id=eid, coa_list=self._coa_list, parent=self)
        if dlg.exec():
            self._refresh_list()

    def _on_delete_selected(self) -> None:
        eid = self._selected_entry_id()
        if eid is None:
            return
        entry = self._gl.get_journal_entry(eid)
        if entry is None:
            return
        d = dict(entry)
        date_s = d.get("entry_date") or ""
        memo_s = (d.get("memo") or "")[:80]
        lines  = self._gl.get_entry_lines(eid)
        ans = message_box_question_yes_no(
            self,
            "Delete journal entry?",
            f"Permanently delete journal entry #{eid}?\n\n"
            f"  Date:  {date_s}\n"
            f"  Memo:  {escape_ampersand_for_qt(memo_s)}\n"
            f"  Lines: {len(lines)}\n\n"
            "All GL lines will be removed. This cannot be undone.\n"
            "Back up with File → Backup before deleting.",
            yes_tip="Delete this entry and all its lines permanently.",
            no_tip="Cancel — keep the entry.",
        )
        if not ans:
            return
        try:
            self._gl.delete_journal_entry(eid)
        except ValueError as exc:
            message_box_warning_ok(
                self, "Cannot delete",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close.",
            )
            return
        self._refresh_list()

    def _on_journal_list_context_menu(self, pos):
        idx = self._list.indexAt(pos)
        m = QMenu(self)
        act_keys = m.addAction(
            "Keyboard shortcuts…",
            lambda: show_more_main_tabs_keyboard_shortcuts_dialog(self),
        )
        act_keys.setToolTip(
            "Same summary as Help → More tab shortcuts (F5)… (Journal, COA, Reports, Audit chords). "
            + VIEW_BANK_REGISTER_KEYS_TOOLTIP
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        if not idx.isValid():
            m.exec(self._list.viewport().mapToGlobal(pos))
            return
        row = idx.row()
        it = self._list.item(row)
        eid = coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole)) if it else None
        m.addSeparator()
        act_edit = m.addAction("✏  Edit entry…", self._on_edit_selected)
        act_edit.setToolTip("Open the entry editor to change date, memo, or lines.")
        act_edit.setEnabled(eid is not None)
        act_del = m.addAction("🗑  Delete entry…", self._on_delete_selected)
        act_del.setToolTip(
            "Permanently delete this journal entry and all its lines. "
            "Back up with File → Backup first."
        )
        act_del.setEnabled(eid is not None)
        m.addSeparator()
        act_copy = m.addAction(
            "Copy entry line",
            partial(copy_qlistwidget_row_text, self._list, row),
        )
        act_copy.setToolTip(
            "Copy the selected journal entry summary line as plain text. "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
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
            + VIEW_BANK_REGISTER_KEYS_TOOLTIP
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
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
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        m.exec(self._lines.viewport().mapToGlobal(pos))

    def _refresh_list(self):
        self._list.clear()
        start = line_edit_to_iso_or_raw(self._start)
        end = line_edit_to_iso_or_raw(self._end)
        raw = self._gl.list_journal_entries(start, end)
        self._entries = [
            e for e in raw if coerce_combo_int_id(e["id"]) is not None
        ]
        for e in self._entries:
            eid = coerce_combo_int_id(e["id"])
            memo = (e["memo"] or "")[:60]
            label = f"{e['entry_date']}  #{eid}  {memo}"
            it = QListWidgetItem(escape_ampersand_for_qt(label))
            it.setData(Qt.ItemDataRole.UserRole, eid)
            it.setData(QLIST_PLAIN_TEXT_ROLE, label)
            self._list.addItem(it)
        if len(self._entries) > 0:
            self._list.setCurrentRow(0)
        self._update_entry_buttons(self._list.currentRow())

    def _export_csv(self):
        start = line_edit_to_iso_or_raw(self._start)
        end = line_edit_to_iso_or_raw(self._end)
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
            ok_tip="Close; open the CSV from the path shown." + CSV_EXPORT_OK_TIP_SUFFIX,
        )

    def _show_lines(self, row: int):
        if row < 0 or row >= self._list.count():
            self._lines.setRowCount(0)
            return
        it = self._list.item(row)
        if it is None:
            self._lines.setRowCount(0)
            return
        eid_int = coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole))
        if eid_int is None:
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

