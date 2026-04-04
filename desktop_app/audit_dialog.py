"""Shared audit history dialog (Phase 23).

Change history grid: **right-click** **Keyboard shortcuts…** (including empty area) explains
**Copy row**; main-window **Help** shortcuts are on the main window.
The dialog **window** has a hover hint; **Close** uses ``tip_qdialog_button_box``; the change-history **table** has a hover hint when rows are shown.
The **empty-state** message label has a tooltip when there is no history yet.
Context menu **Keyboard shortcuts…** and **Copy row** use **setToolTip** on each **QAction**.
**Keyboard shortcuts…** help uses ``message_box_information_ok`` (hover **Ok** tooltip).
"""

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

from desktop_app.qt_mnemonic import (
    escape_ampersand_for_qt,
    message_box_information_ok,
    tip_qdialog_button_box,
)
from desktop_app.table_clipboard import (
    CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX,
    copy_table_row_as_tsv,
    plain_display_table_item,
)
from probooksai.audit_log import list_for_entity


def _audit_history_shortcuts_help(parent: QWidget) -> None:
    message_box_information_ok(
        parent,
        "Change history",
        "Copy row — copies the selected row as tab-separated text. "
        + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        + "\n\n"
        "For main-window shortcuts (F5, Help menus), use Help on the main window.",
        ok_tip="Close this shortcuts summary.",
    )


def _audit_history_table_context_menu(
    table: QTableWidget, parent_widget: QWidget, pos
) -> None:
    idx = table.indexAt(pos)
    m = QMenu(parent_widget)
    act_keys = m.addAction(
        "Keyboard shortcuts…",
        lambda: _audit_history_shortcuts_help(parent_widget),
    )
    act_keys.setToolTip(
        "This dialog’s shortcuts summary (Copy row); use the main window Help menu for global chords. "
        + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
    )
    if not idx.isValid():
        m.exec(table.viewport().mapToGlobal(pos))
        return
    row = idx.row()
    m.addSeparator()
    act_copy = m.addAction("Copy row", partial(copy_table_row_as_tsv, table, row))
    act_copy.setToolTip(
        "Copy this audit row as tab-separated text for pasting into a spreadsheet or editor. "
        + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
    )
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
    dlg.setToolTip(
        "Field-level audit trail for this record. Right-click the grid (when shown) for shortcuts and copy."
    )
    lay = QVBoxLayout(dlg)
    if not rows:
        empty_lbl = QLabel(escape_ampersand_for_qt(empty_message))
        empty_lbl.setToolTip("No field-level audit entries are stored for this record yet.")
        lay.addWidget(empty_lbl)
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
        tbl.setToolTip(
            "Field-level changes for this record. Right-click for Keyboard shortcuts… "
            "(including on empty area)."
        )
        lay.addWidget(tbl)
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    tip_qdialog_button_box(box, close="Close this change history dialog.")
    box.rejected.connect(dlg.reject)
    lay.addWidget(box)
    dlg.exec()
