"""
desktop_app.coa_tab
====================
PySide6 widget for viewing and editing the Chart of Accounts.

Issue #41 – COA editor (minimal): UI to view/add/edit/deactivate COA accounts.
COA entries populate category dropdowns throughout the app.

Widgets
-------
  COATab          – top-level QWidget (intended as a tab in MainWindow)
  AddEditCOADialog – dialog for creating or editing a single COA account
"""

from __future__ import annotations

import sqlite3
from functools import partial
from typing import Optional

from PySide6.QtCore import Qt, Signal
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
from desktop_app.qt_mnemonic import escape_ampersand_for_qt
from desktop_app.table_clipboard import (
    QTABLE_PLAIN_TEXT_ROLE,
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

        self._f_name = QLineEdit()
        self._f_name.setPlaceholderText("e.g. Checking Account")
        self._f_name.setMinimumWidth(200)

        self._f_type = QComboBox()
        for key, label in _TYPE_LABELS.items():
            self._f_type.addItem(label, userData=key)

        self._f_subtype = QLineEdit()
        self._f_subtype.setPlaceholderText("e.g. Cash and Cash Equivalents")

        self._f_description = QLineEdit()
        self._f_description.setPlaceholderText("Optional description")

        self._f_active = QCheckBox("Active")
        self._f_active.setChecked(True)

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
            QMessageBox.warning(self, "Validation", "Account number is required.")
            return
        if not name:
            QMessageBox.warning(self, "Validation", "Account name is required.")
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
            QMessageBox.critical(
                self, "Error", escape_ampersand_for_qt(str(exc))
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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Toolbar
        toolbar = QHBoxLayout()
        self._btn_add = QPushButton("+ Add Account")
        self._btn_edit = QPushButton("Edit")
        self._btn_edit.setEnabled(False)
        self._btn_deactivate = QPushButton("Deactivate")
        self._btn_deactivate.setEnabled(False)
        self._chk_inactive = QCheckBox("Show inactive")

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
        layout.addWidget(self._table)

        # Footer
        self._lbl_count = QLabel("")
        layout.addWidget(self._lbl_count)

    # -- data ----------------------------------------------------------------

    def _refresh(self):
        include_inactive = self._chk_inactive.isChecked()
        rows = self._db.list_accounts(include_inactive=include_inactive)
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            num_it = _CoaAccountNumberTableItem(
                str(row["account_number"]), int(row["id"])
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

        count = len(rows)
        self._lbl_count.setText(f"{count} account{'s' if count != 1 else ''}")

    def _selected_id(self) -> Optional[int]:
        rows = self._table.selectedItems()
        if not rows:
            return None
        r = self._table.currentRow()
        item = self._table.item(r, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_coa_context_menu(self, pos):
        idx = self._table.indexAt(pos)
        if not idx.isValid():
            return
        row = idx.row()
        item = self._table.item(row, 0)
        if item is None:
            return
        aid = item.data(Qt.ItemDataRole.UserRole)
        if aid is None:
            return
        menu = QMenu(self)
        menu.addAction("Copy row", partial(copy_table_row_as_tsv, self._table, row))
        act_history = menu.addAction("View change history…")
        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))
        if chosen == act_history:
            show_entity_audit_history(
                self,
                self._db._conn,
                "coa_account",
                int(aid),
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
            confirm = QMessageBox.question(
                self,
                "Deactivate Account",
                "Deactivate '"
                f"{escape_ampersand_for_qt(name or '')}"
                "'? It will no longer appear in dropdowns.",
            )
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
