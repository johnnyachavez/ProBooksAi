"""Shared audit history dialog (Phase 23)."""

from __future__ import annotations

import sqlite3
from functools import partial

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QMenu,
    QTableWidget,
    QWidget,
    QVBoxLayout,
)

from desktop_app.qt_mnemonic import escape_ampersand_for_qt
from desktop_app.table_clipboard import copy_table_row_as_tsv, plain_display_table_item
from probooksai.audit_log import list_for_entity


def _audit_history_table_context_menu(
    table: QTableWidget, parent_widget: QWidget, pos
) -> None:
    idx = table.indexAt(pos)
    if not idx.isValid():
        return
    row = idx.row()
    m = QMenu(parent_widget)
    m.addAction("Copy row", partial(copy_table_row_as_tsv, table, row))
    m.exec(table.viewport().mapToGlobal(pos))


def show_entity_audit_history(
    parent: QWidget,
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: int,
    *,
    window_title: str,
    empty_message: str = "No audit entries recorded yet.",
    limit: int = 500,
) -> None:
    rows = list_for_entity(conn, entity_type, entity_id, limit=limit)
    dlg = QDialog(parent)
    dlg.setWindowTitle(escape_ampersand_for_qt(window_title))
    dlg.resize(640, 320)
    lay = QVBoxLayout(dlg)
    if not rows:
        lay.addWidget(QLabel(escape_ampersand_for_qt(empty_message)))
    else:
        tbl = QTableWidget()
        tbl.setColumnCount(4)
        tbl.setHorizontalHeaderLabels(
            ["When", "Field", "Old value", "New value"]
        )
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tbl.verticalHeader().setVisible(False)
        tbl.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        tbl.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        tbl.setSortingEnabled(False)
        tbl.setRowCount(len(rows))
        for i, r in enumerate(rows):
            d = dict(r)
            tbl.setItem(
                i,
                0,
                plain_display_table_item((d.get("changed_at") or "")[:19]),
            )
            tbl.setItem(i, 1, plain_display_table_item(d.get("field") or ""))
            tbl.setItem(i, 2, plain_display_table_item(d.get("old_value") or ""))
            tbl.setItem(i, 3, plain_display_table_item(d.get("new_value") or ""))
        tbl.setSortingEnabled(True)
        tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tbl.customContextMenuRequested.connect(
            lambda pos, t=tbl, d=dlg: _audit_history_table_context_menu(t, d, pos)
        )
        lay.addWidget(tbl)
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    box.rejected.connect(dlg.reject)
    lay.addWidget(box)
    dlg.exec()
