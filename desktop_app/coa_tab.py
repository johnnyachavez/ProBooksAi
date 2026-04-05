"""
desktop_app.coa_tab
====================
PySide6 widget for viewing and editing the Chart of Accounts.

Issue #41 – COA editor (minimal): UI to view/add/edit/deactivate COA accounts.
COA entries populate category dropdowns throughout the app.

**F5** (when this tab or its children have focus) reloads the grid from the database (same as after
add/edit/deactivate; respects **Show inactive**). **Help → More tab shortcuts (F5)…**; grid **right-click**
**Keyboard shortcuts…** / **Copy** / **View change history** use **QAction** **setToolTip** (including empty area). The grid has a hover **tooltip**.
The **COATab** root **QWidget** has a hover hint. The account **count** line and footer **F5** hint use **setToolTip** on hover.
Deactivate confirm **Yes**/**No** use **tip_message_box_buttons**.

Widgets
-------
  COATab          – top-level QWidget (intended as a tab in MainWindow)
  AddEditCOADialog – dialog for creating or editing a single COA account (window + field + **Save**/**Cancel** via ``tip_qdialog_button_box``)
"""

from __future__ import annotations

import sqlite3
from functools import partial
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from probooksai.coa_db import COADatabase, COA_ACCOUNT_TYPES

from desktop_app.audit_dialog import show_entity_audit_history
from desktop_app.qt_combo_ids import coerce_combo_int_id
from desktop_app.more_main_tabs_shortcuts import (
    show_more_main_tabs_keyboard_shortcuts_dialog,
)
from desktop_app.qt_mnemonic import (
    escape_ampersand_for_qt,
    message_box_critical_ok,
    message_box_warning_ok,
    tip_message_box_buttons,
    tip_qdialog_button_box,
)
from desktop_app.table_clipboard import (
    CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX,
    QTABLE_PLAIN_TEXT_ROLE,
    VIEW_BANK_REGISTER_KEYS_TOOLTIP,
    copy_table_row_as_tsv,
    plain_display_table_item,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _CoaAccountNumberTableItem(QTableWidgetItem):
    """# column: escaped display, plain copy role, numeric sort when number is all digits."""

    def __init__(self, account_number: str, account_id: int) -> None:
        raw = str(account_number or "")
        super().__init__(escape_ampersand_for_qt(raw))
        self.setData(Qt.ItemDataRole.UserRole, int(account_id))
        self.setData(QTABLE_PLAIN_TEXT_ROLE, raw)
        sk = raw.strip()
        self._int_key: int | None = int(sk) if sk.isdigit() else None

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, _CoaAccountNumberTableItem):
            if self._int_key is not None and other._int_key is not None:
                return self._int_key < other._int_key
            a = (self.data(QTABLE_PLAIN_TEXT_ROLE) or "").strip().lower()
            b = (other.data(QTABLE_PLAIN_TEXT_ROLE) or "").strip().lower()
            return a < b
        return super().__lt__(other)

_TYPE_LABELS = {
    "asset":     "Asset",
    "liability": "Liability",
    "equity":    "Equity",
    "income":    "Income",
    "expense":   "Expense",
}


# ===========================================================================
# AddEditCOADialog
# ===========================================================================

class AddEditCOADialog(QDialog):
    """Dialog for adding or editing a single COA account."""

    def __init__(self, db: COADatabase, account_id: Optional[int] = None, parent=None):
        super().__init__(parent)
        self._db = db
        self._account_id = account_id
        self.setWindowTitle("Edit Account" if account_id else "Add Account")
        self.resize(420, 340)
        self.setToolTip(
            "Add or edit one chart-of-accounts row: number, name, type, optional sub-type and description."
        )
        self._build_ui()
        if account_id is not None:
            self._load(account_id)

    # -- UI ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._f_number = QLineEdit()
        self._f_number.setMaxLength(20)
        self._f_number.setPlaceholderText("e.g. 1010")
        self._f_number.setToolTip(
            "Unique account number or code used in reports and journal entries (required)."
        )

        self._f_name = QLineEdit()
        self._f_name.setPlaceholderText("e.g. Checking Account")
        self._f_name.setMinimumWidth(200)
        self._f_name.setToolTip("Display name for this account in lists and reports (required).")

        self._f_type = QComboBox()
        for key, label in _TYPE_LABELS.items():
            self._f_type.addItem(label, userData=key)
        self._f_type.setToolTip(
            "High-level category (asset, liability, equity, income, expense). "
            "Determines normal debit/credit balance."
        )

        self._f_subtype = QLineEdit()
        self._f_subtype.setPlaceholderText("e.g. Cash and Cash Equivalents")
        self._f_subtype.setToolTip(
            "Optional finer grouping (e.g. current asset, operating expense) for your own organization."
        )

        self._f_description = QLineEdit()
        self._f_description.setPlaceholderText("Optional description")
        self._f_description.setToolTip("Optional longer notes shown when editing this account.")

        self._f_active = QCheckBox("Active")
        self._f_active.setChecked(True)
        self._f_active.setToolTip(
            "Inactive accounts are hidden from pickers unless you choose to show them elsewhere."
        )

        form.addRow("Account #:", self._f_number)
        form.addRow("Name:",      self._f_name)
        form.addRow("Type:",      self._f_type)
        form.addRow("Sub-type:",  self._f_subtype)
        form.addRow("Description:", self._f_description)
        form.addRow("",           self._f_active)

        layout.addLayout(form)
        layout.addStretch()

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        tip_qdialog_button_box(
            btns,
            save="Save this COA account and close the dialog.",
            cancel="Close without saving changes to this account.",
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    # -- load ----------------------------------------------------------------

    def _load(self, account_id: int):
        row = self._db.get_account(account_id)
        if row is None:
            return
        self._f_number.setText(row["account_number"] or "")
        self._f_name.setText(row["account_name"] or "")
        # Set type combo
        idx = self._f_type.findData(row["account_type"])
        if idx >= 0:
            self._f_type.setCurrentIndex(idx)
        self._f_subtype.setText(row["sub_type"] or "")
        self._f_description.setText(row["description"] or "")
        self._f_active.setChecked(bool(row["is_active"]))

    # -- save ----------------------------------------------------------------

    def _save(self):
        number = self._f_number.text().strip()
        name   = self._f_name.text().strip()
        if not number:
            message_box_warning_ok(
                self,
                "Validation",
                "Account number is required.",
                ok_tip="Close; enter an account number before saving.",
            )
            return
        if not name:
            message_box_warning_ok(
                self,
                "Validation",
                "Account name is required.",
                ok_tip="Close; enter an account name before saving.",
            )
            return

        acct_type   = self._f_type.currentData()
        sub_type    = self._f_subtype.text().strip()
        description = self._f_description.text().strip()
        is_active   = self._f_active.isChecked()

        # Infer normal balance from type
        normal_balance = "credit" if acct_type in ("liability", "equity", "income") else "debit"

        try:
            if self._account_id is None:
                self._db.add_account(
                    account_number=number,
                    account_name=name,
                    account_type=acct_type,
                    sub_type=sub_type,
                    normal_balance=normal_balance,
                    description=description,
                    is_active=is_active,
                )
            else:
                self._db.update_account(
                    account_id=self._account_id,
                    account_number=number,
                    account_name=name,
                    account_type=acct_type,
                    sub_type=sub_type,
                    normal_balance=normal_balance,
                    description=description,
                    is_active=is_active,
                )
        except (ValueError, sqlite3.IntegrityError) as exc:
            message_box_critical_ok(
                self,
                "Error",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; fix duplicates or invalid values and try again.",
            )
            return

        self.accept()


# ===========================================================================
# COATab
# ===========================================================================

class COATab(QWidget):
    """
    Tab widget for viewing and managing the Chart of Accounts.

    Emits ``coaChanged`` whenever the COA is modified so other widgets
    (e.g. bank import transaction table) can refresh their dropdowns.
    """

    coaChanged = Signal()

    def __init__(self, db: COADatabase, parent=None):
        super().__init__(parent)
        self._db = db
        self._build_ui()
        self._refresh()

    # -- UI ------------------------------------------------------------------

    def _build_ui(self):
        self.setToolTip(
            "Chart of accounts: add, edit, or deactivate rows; grid and shortcuts (F5 reloads when this tab has focus). "
            "Same company SQLite database as other main tabs; File → Backup / Restore (probooks.backup)."
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Toolbar
        toolbar = QHBoxLayout()
        self._btn_add = QPushButton("+ Add Account")
        self._btn_add.setToolTip("Create a new chart-of-accounts entry.")
        self._btn_edit = QPushButton("Edit")
        self._btn_edit.setEnabled(False)
        self._btn_edit.setToolTip("Edit the selected account (double-click a row or use Edit).")
        self._btn_deactivate = QPushButton("Deactivate")
        self._btn_deactivate.setEnabled(False)
        self._btn_deactivate.setToolTip(
            "Deactivate the selected account (show it again with Show inactive)."
        )
        self._chk_inactive = QCheckBox("Show inactive")
        self._chk_inactive.setToolTip(
            "Include inactive accounts. F5 reloads the grid from the database."
        )

        self._btn_add.clicked.connect(self._on_add)
        self._btn_edit.clicked.connect(self._on_edit)
        self._btn_deactivate.clicked.connect(self._on_deactivate)
        self._chk_inactive.toggled.connect(self._refresh)

        toolbar.addWidget(self._btn_add)
        toolbar.addWidget(self._btn_edit)
        toolbar.addWidget(self._btn_deactivate)
        toolbar.addStretch()
        toolbar.addWidget(self._chk_inactive)
        layout.addLayout(toolbar)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels([
            "#", "Account Name", "Type", "Sub-type", "Normal Balance", "Active"
        ])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(0, 70)
        self._table.setColumnWidth(2, 90)
        self._table.setColumnWidth(3, 160)
        self._table.setColumnWidth(4, 120)
        self._table.setColumnWidth(5, 60)
        self._table.itemSelectionChanged.connect(self._on_selection)
        self._table.doubleClicked.connect(self._on_edit)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_coa_context_menu)
        self._table.setSortingEnabled(True)
        self._table.setToolTip(
            "Chart of accounts: double-click to edit; right-click for Keyboard shortcuts… and "
            "change history (empty area OK). F5 reloads when this tab has focus. "
            "COA rows live in the company .db (File → Backup / Restore, probooks.backup)."
        )
        layout.addWidget(self._table)

        # Footer
        self._lbl_count = QLabel("")
        self._lbl_count.setToolTip(
            "Number of accounts shown and inactive count when Show inactive is on."
        )
        layout.addWidget(self._lbl_count)

        tip = QLabel(
            "F5 reloads the chart from the database (respects Show inactive). "
            "Journal and Bank import tabs also use F5 to refresh. "
            "Company SQLite: File → Backup / Restore (probooks.backup, CLI probooks backup/restore)."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #A0A0B0; font-size: 11px;")
        tip.setToolTip(
            "F5 refreshes this grid; double-click a row to edit; right-click for shortcuts and change history. "
            "Back up the company .db from File → Backup / probooks backup before bulk COA edits."
        )
        layout.addWidget(tip)

        sc_refresh = QShortcut(QKeySequence("F5"), self)
        sc_refresh.setContext(Qt.WidgetWithChildrenShortcut)
        sc_refresh.activated.connect(self._refresh)

    # -- data ----------------------------------------------------------------

    def _refresh(self):
        include_inactive = self._chk_inactive.isChecked()
        rows = self._db.list_accounts(include_inactive=include_inactive)
        packed = [
            (aid, row)
            for row in rows
            if (aid := coerce_combo_int_id(row["id"])) is not None
        ]
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(packed))
        for r, (aid, row) in enumerate(packed):
            num_it = _CoaAccountNumberTableItem(
                str(row["account_number"]), aid
            )
            self._table.setItem(r, 0, num_it)
            self._table.setItem(r, 1, plain_display_table_item(row["account_name"] or ""))
            type_lbl = _TYPE_LABELS.get(row["account_type"], row["account_type"])
            self._table.setItem(r, 2, plain_display_table_item(str(type_lbl)))
            self._table.setItem(r, 3, plain_display_table_item(row["sub_type"] or ""))
            nb = (row["normal_balance"] or "").title()
            self._table.setItem(r, 4, plain_display_table_item(nb))
            active_item = plain_display_table_item(
                "✓" if row["is_active"] else "—"
            )
            active_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(r, 5, active_item)
        self._table.setSortingEnabled(True)

        count = len(packed)
        self._lbl_count.setText(f"{count} account{'s' if count != 1 else ''}")

    def _selected_id(self) -> Optional[int]:
        rows = self._table.selectedItems()
        if not rows:
            return None
        r = self._table.currentRow()
        item = self._table.item(r, 0)
        if item is None:
            return None
        return coerce_combo_int_id(item.data(Qt.ItemDataRole.UserRole))

    def _on_coa_context_menu(self, pos):
        idx = self._table.indexAt(pos)
        menu = QMenu(self)
        act_keys = menu.addAction(
            "Keyboard shortcuts…",
            lambda: show_more_main_tabs_keyboard_shortcuts_dialog(self),
        )
        act_keys.setToolTip(
            "Same summary as Help → More tab shortcuts (F5)… "
            "(COA, Journal, Reports, Audit chords). "
            + VIEW_BANK_REGISTER_KEYS_TOOLTIP
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        if not idx.isValid():
            menu.exec(self._table.viewport().mapToGlobal(pos))
            return
        row = idx.row()
        item = self._table.item(row, 0)
        aid = (
            coerce_combo_int_id(item.data(Qt.ItemDataRole.UserRole))
            if item is not None
            else None
        )
        if aid is None:
            menu.exec(self._table.viewport().mapToGlobal(pos))
            return
        menu.addSeparator()
        act_copy = menu.addAction("Copy row", partial(copy_table_row_as_tsv, self._table, row))
        act_copy.setToolTip(
            "Copy this COA row as tab-separated text for pasting into a spreadsheet or editor. "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        act_history = menu.addAction("View change history…")
        act_history.setToolTip(
            "Open field-level audit history for this chart-of-accounts account."
        )
        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))
        if chosen == act_history:
            show_entity_audit_history(
                self,
                self._db._conn,
                "coa_account",
                aid,
                window_title=f"Change history — COA account #{aid}",
                empty_message="No audit entries recorded for this account yet.",
            )

    # -- actions -------------------------------------------------------------

    def _on_selection(self):
        has_sel = self._selected_id() is not None
        self._btn_edit.setEnabled(has_sel)
        self._btn_deactivate.setEnabled(has_sel)

    def _on_add(self):
        dlg = AddEditCOADialog(self._db, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh()
            self.coaChanged.emit()

    def _on_edit(self):
        acct_id = self._selected_id()
        if acct_id is None:
            return
        dlg = AddEditCOADialog(self._db, account_id=acct_id, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh()
            self.coaChanged.emit()

    def _on_deactivate(self):
        acct_id = self._selected_id()
        if acct_id is None:
            return
        row = self._db.get_account(acct_id)
        if row is None:
            return
        name = row["account_name"]
        currently_active = bool(row["is_active"])
        if currently_active:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Question)
            box.setWindowTitle("Deactivate Account")
            box.setText(
                "Deactivate '"
                f"{escape_ampersand_for_qt(name or '')}"
                "'? It will no longer appear in dropdowns."
            )
            box.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            box.setToolTip(
                "Deactivated accounts stay in the database but are hidden from COA pickers until shown again. "
                "Consider File → Backup / probooks backup before bulk COA changes."
            )
            tip_message_box_buttons(
                box,
                yes="Deactivate this account; it hides from pick lists (data stays in the company .db — File → Backup before wide COA changes).",
                no="Keep the account active (cancel deactivation).",
            )
            confirm = box.exec()
            if confirm != QMessageBox.StandardButton.Yes:
                return
        self._set_account_active(row, acct_id, not currently_active)
        self._refresh()
        self.coaChanged.emit()

    def _set_account_active(self, row, account_id: int, is_active: bool):
        """Toggle the is_active flag on an account row, preserving all other fields."""
        self._db.update_account(
            account_id=account_id,
            account_number=row["account_number"],
            account_name=row["account_name"],
            account_type=row["account_type"],
            sub_type=row["sub_type"] or "",
            normal_balance=row["normal_balance"] or "debit",
            description=row["description"] or "",
            is_active=is_active,
        )
