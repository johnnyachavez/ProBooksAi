"""Recent audit log entries (Phase 23).

**F5** (when this tab or its children have focus) runs the same reload as **Refresh**.
**Help → More tab shortcuts (F5)…**; log grid **right-click** **Keyboard shortcuts…** (including empty area).
The tab **root** has a hover hint. **Entity type** / **Entity id** labels and controls use **setToolTip**; the hint line and log grid have hover hints.
The log grid **right-click** menu sets **QAction** tooltips for **Keyboard shortcuts…** and **Copy row**.
"""

from __future__ import annotations

import sqlite3
from functools import partial

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from desktop_app.more_main_tabs_shortcuts import (
    show_more_main_tabs_keyboard_shortcuts_dialog,
)
from desktop_app.qt_mnemonic import (
    escape_ampersand_for_qt,
    message_box_critical_ok,
    message_box_information_ok,
    message_box_warning_ok,
)
from desktop_app.table_clipboard import (
    CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX,
    IntSortTableItem,
    copy_table_row_as_tsv,
    plain_display_table_item,
)
from probooksai.audit_log import list_filtered, write_audit_csv


class AuditTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self.setToolTip(
            "Audit trail: field-level changes with optional entity type and id filter; export CSV (F5 refreshes when Audit has focus). "
            "Same company SQLite database as other main tabs; File → Backup / Restore (probooks.backup)."
        )
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        btn_refresh = QPushButton("Refresh")
        btn_refresh.setToolTip(
            "Reload the audit grid with the current filter. "
            "Shortcut: F5 (when Audit has focus)."
        )
        btn_refresh.clicked.connect(self._refresh)
        row.addWidget(btn_refresh)
        btn_export = QPushButton("Export CSV…")
        btn_export.setToolTip(
            "Export the current audit log grid to CSV (respects Entity type and optional id)."
        )
        btn_export.clicked.connect(self._export_csv)
        row.addWidget(btn_export)
        row.addStretch()
        lbl_audit_ent_type = QLabel("Entity type:")
        lbl_audit_ent_type.setToolTip(
            "Which kind of record to focus on, or All recent for mixed changes."
        )
        row.addWidget(lbl_audit_ent_type)
        self._ent_type = QComboBox()
        self._ent_type.addItem("All recent", "")
        self._ent_type.addItem("bank_transaction", "bank_transaction")
        self._ent_type.addItem("bank_import_batch", "bank_import_batch")
        self._ent_type.addItem("coa_account", "coa_account")
        self._ent_type.setToolTip(
            "Limit the log to one entity kind, or All recent for the latest changes across types."
        )
        row.addWidget(self._ent_type)
        lbl_audit_ent_id = QLabel("Entity id:")
        lbl_audit_ent_id.setToolTip(
            "Numeric primary key of the record when a specific entity type is selected."
        )
        row.addWidget(lbl_audit_ent_id)
        self._ent_id = QLineEdit()
        self._ent_id.setFixedWidth(90)
        self._ent_id.setPlaceholderText("optional")
        self._ent_id.setToolTip(
            "Optional numeric id: with a specific entity type, show only changes for that record."
        )
        row.addWidget(self._ent_id)
        btn_apply = QPushButton("Apply filter")
        btn_apply.setToolTip(
            "Reload the log using Entity type and optional id (same as Refresh / F5)."
        )
        btn_apply.clicked.connect(self._refresh)
        row.addWidget(btn_apply)
        lay.addLayout(row)
        hint = QLabel(
            "Leave type as “All recent” for the latest changes. "
            "Pick a type and id to view history for one bank transaction or COA row. "
            "You can also open change history from the Register, Bank Import, or COA tab "
            "(right-click a row). F5 refreshes like the Refresh button. "
            "The log reflects the open company SQLite file (File → Backup / probooks backup)."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #A0A0B0; font-size: 11px;")
        hint.setToolTip(
            "Summary: All recent shows latest edits; type + id narrows to one record. "
            "F5 and Refresh reload the grid. Audit rows reflect the open company .db (File → Backup)."
        )
        lay.addWidget(hint)
        self._tbl = QTableWidget()
        self._tbl.setColumnCount(6)
        self._tbl.setHorizontalHeaderLabels(
            ["When", "Entity", "ID", "Field", "Old", "New"]
        )
        self._tbl.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._tbl.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self._tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tbl.customContextMenuRequested.connect(self._on_audit_context_menu)
        self._tbl.setSortingEnabled(True)
        self._tbl.setToolTip(
            "Change history for the current filter. Right-click for Keyboard shortcuts… "
            "(including on empty area). Logged against the company SQLite file (probooks.backup / File → Backup)."
        )
        lay.addWidget(self._tbl)
        sc_f5 = QShortcut(QKeySequence("F5"), self)
        sc_f5.setContext(Qt.WidgetWithChildrenShortcut)
        sc_f5.activated.connect(self._refresh)
        self._refresh()

    def _on_audit_context_menu(self, pos):
        idx = self._tbl.indexAt(pos)
        m = QMenu(self)
        act_keys = m.addAction(
            "Keyboard shortcuts…",
            lambda: show_more_main_tabs_keyboard_shortcuts_dialog(self),
        )
        act_keys.setToolTip(
            "Same summary as Help → More tab shortcuts (F5)… "
            "(Audit log, filters, export, File → Backup / probooks.backup)."
        )
        if not idx.isValid():
            m.exec(self._tbl.viewport().mapToGlobal(pos))
            return
        row = idx.row()
        m.addSeparator()
        act_copy = m.addAction("Copy row", partial(copy_table_row_as_tsv, self._tbl, row))
        act_copy.setToolTip(
            "Copy this audit log row as tab-separated text for pasting into a spreadsheet or editor. "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        m.exec(self._tbl.viewport().mapToGlobal(pos))

    def _export_csv(self):
        et = (self._ent_type.currentData() or "").strip()
        id_txt = self._ent_id.text().strip()
        eid = None
        if id_txt:
            try:
                eid = int(id_txt)
            except ValueError:
                message_box_warning_ok(
                    self,
                    "Audit log",
                    "Entity id must be an integer.",
                    ok_tip="Close; enter digits only or clear Entity id to filter by type.",
                )
                return
        if et and eid is None:
            rows = list_filtered(self._conn, entity_type=et, entity_id=None, limit=500)
        else:
            rows = list_filtered(
                self._conn,
                entity_type=et or None,
                entity_id=eid,
                limit=500,
            )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export audit log",
            "",
            "CSV (*.csv);;All Files (*.*)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            n = write_audit_csv(path, list(rows))
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
            f"Exported {n} row(s) to:\n{escape_ampersand_for_qt(path)}",
            ok_tip="Close; open the CSV from the path shown.",
        )

    def _refresh(self):
        et = (self._ent_type.currentData() or "").strip()
        id_txt = self._ent_id.text().strip()
        eid = None
        if id_txt:
            try:
                eid = int(id_txt)
            except ValueError:
                message_box_warning_ok(
                    self,
                    "Audit log",
                    "Entity id must be an integer.",
                    ok_tip="Close; enter digits only or clear Entity id to filter by type.",
                )
                return
        if et and eid is None:
            rows = list_filtered(self._conn, entity_type=et, entity_id=None, limit=500)
        else:
            rows = list_filtered(
                self._conn,
                entity_type=et or None,
                entity_id=eid,
                limit=500,
            )
        self._tbl.setSortingEnabled(False)
        self._tbl.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self._tbl.setItem(
                i, 0, plain_display_table_item((r["changed_at"] or "")[:19])
            )
            self._tbl.setItem(i, 1, plain_display_table_item(r["entity_type"]))
            eid = int(r["entity_id"])
            self._tbl.setItem(i, 2, IntSortTableItem(str(eid), eid))
            self._tbl.setItem(i, 3, plain_display_table_item(r["field"]))
            self._tbl.setItem(i, 4, plain_display_table_item(r["old_value"] or ""))
            self._tbl.setItem(i, 5, plain_display_table_item(r["new_value"] or ""))
        self._tbl.setSortingEnabled(True)
