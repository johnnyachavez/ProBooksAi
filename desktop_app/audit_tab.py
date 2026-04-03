"""Recent audit log entries (Phase 23).

**F5** (when this tab or its children have focus) runs the same reload as **Refresh**.
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
    QMessageBox,
)

from desktop_app.qt_mnemonic import escape_ampersand_for_qt
from desktop_app.table_clipboard import (
    IntSortTableItem,
    copy_table_row_as_tsv,
    plain_display_table_item,
)
from probooksai.audit_log import list_filtered, write_audit_csv


class AuditTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        btn_refresh = QPushButton("Refresh")
        btn_refresh.setToolTip(
            "Reload the audit grid with the current filter. "
            "Shortcut: F5 (when Audit has focus)."
        )
        btn_refresh.clicked.connect(self._refresh)
        row.addWidget(btn_refresh)
        row.addWidget(QPushButton("Export CSV…", clicked=self._export_csv))
        row.addStretch()
        row.addWidget(QLabel("Entity type:"))
        self._ent_type = QComboBox()
        self._ent_type.addItem("All recent", "")
        self._ent_type.addItem("bank_transaction", "bank_transaction")
        self._ent_type.addItem("bank_import_batch", "bank_import_batch")
        self._ent_type.addItem("coa_account", "coa_account")
        row.addWidget(self._ent_type)
        row.addWidget(QLabel("Entity id:"))
        self._ent_id = QLineEdit()
        self._ent_id.setFixedWidth(90)
        self._ent_id.setPlaceholderText("optional")
        row.addWidget(self._ent_id)
        row.addWidget(QPushButton("Apply filter", clicked=self._refresh))
        lay.addLayout(row)
        hint = QLabel(
            "Leave type as “All recent” for the latest changes. "
            "Pick a type and id to view history for one bank transaction or COA row. "
            "You can also open change history from the Register, Bank Import, or COA tab "
            "(right-click a row). F5 refreshes like the Refresh button."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #A0A0B0; font-size: 11px;")
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
        lay.addWidget(self._tbl)
        sc_f5 = QShortcut(QKeySequence("F5"), self)
        sc_f5.setContext(Qt.WidgetWithChildrenShortcut)
        sc_f5.activated.connect(self._refresh)
        self._refresh()

    def _on_audit_context_menu(self, pos):
        idx = self._tbl.indexAt(pos)
        if not idx.isValid():
            return
        row = idx.row()
        m = QMenu(self)
        m.addAction("Copy row", partial(copy_table_row_as_tsv, self._tbl, row))
        m.exec(self._tbl.viewport().mapToGlobal(pos))

    def _export_csv(self):
        et = (self._ent_type.currentData() or "").strip()
        id_txt = self._ent_id.text().strip()
        eid = None
        if id_txt:
            try:
                eid = int(id_txt)
            except ValueError:
                QMessageBox.warning(self, "Audit log", "Entity id must be an integer.")
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
            QMessageBox.critical(
                self, "Export failed", escape_ampersand_for_qt(str(exc))
            )
            return
        QMessageBox.information(
            self,
            "Export complete",
            f"Exported {n} row(s) to:\n{escape_ampersand_for_qt(path)}",
        )

    def _refresh(self):
        et = (self._ent_type.currentData() or "").strip()
        id_txt = self._ent_id.text().strip()
        eid = None
        if id_txt:
            try:
                eid = int(id_txt)
            except ValueError:
                QMessageBox.warning(self, "Audit log", "Entity id must be an integer.")
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
