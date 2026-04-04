"""
desktop_app.bank_import_tab
============================
**Architecture:** This tab owns **bank account** setup, **import batches**, **CSV/PDF** intake,
and **statement reconciliation**. The **Bank register** tab is the primary grid for working
existing **bank_transactions** (COA, cleared, GL posting, payment links). The right-hand
**register preview** is a batch-scoped, register-styled readout of imported rows—not a second
full register.

PySide6 widget for bank account setup, CSV import, and statement reconciliation.
**CSV import** shows a **QProgressDialog** titled **Importing bank CSV**; its **Cancel** button has its own hover tooltip (dialog chrome also has a summary tooltip).

**F5** (when this tab or its children have focus) reloads accounts and import batches and
re-selects the same batch when it still exists, refreshing transactions and reconciliation.
**Help** → **Bank import shortcuts…** shows the same **F5** summary and points at Register shortcuts.
**Right-click** the **Import Batches** table, **register preview** grid, or **Manage Bank Accounts** tables
(including empty area) for **Keyboard shortcuts…** and row actions; each **QAction** has **setToolTip** where shown.
Those tables have hover **tooltips** summarizing the same; **Import Batches** column headers have **setToolTip** per section. The right-pane **BlankBankRegisterTable** uses the same stylesheet as the Register tab grid and **setToolTip** on each column header.

Tabs / widgets
--------------
  BankImportTab          – top-level QWidget (root **setToolTip**; left **batch list** column **QWidget** hint + **batch workflow** hint under **Import Batches:**; header **Bank Account** label + combo; **Import formats** hint under the import buttons; horizontal + vertical **QSplitter** tooltips; footer **F5** hint tooltip)
  ManageAccountsDialog   – CRUD dialog for bank_accounts (window tooltip; add/edit sub-dialog window + field tooltips; delete **Yes**/**No**)
  StatementPeriodDialog  – statement dates and balances (window + field + note tooltips; OK/Cancel via ``tip_qdialog_button_box``)
  ColumnMappingDialog    – map CSV headers (window + combo + OK/Cancel via ``tip_qdialog_button_box``)
  BlankBankRegisterTable – **QTableWidget** (Date…Balance; blank editable rows, or read-only import rows + padded blanks when a batch is selected)
  ReconciliationPanel    – statement vs import summary (**QGroupBox** + value labels + status **tooltips**)
  StatementLineMatchPanel – mock statement extract vs register (**Matched** / **Missing** / **Extra**; review checkboxes, UI-only); **Run mock extract & compare** also pushes **Stmt match** onto the **Bank register** tab when a ``register_tab`` is wired (optional **after_stmt_match_sync** focuses that tab).
"""

from __future__ import annotations

import sqlite3
from functools import partial
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QDate, QSettings, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from probooksai.bank_import import (
    ACCOUNT_TYPES,
    BankDatabase,
    parse_csv,
)
from probooksai.coa_db import COADatabase

from desktop_app.audit_dialog import show_entity_audit_history
from desktop_app.qt_combo_ids import (
    coerce_combo_int_id,
    combo_index_for_int_user_data,
    combo_int_ids_equal,
)
from desktop_app.csv_import_worker import CsvImportWorker
from desktop_app.open_attachment import open_local_attachment
from desktop_app.qt_mnemonic import (
    escape_ampersand_for_qt,
    message_box_critical_ok,
    message_box_information_ok,
    message_box_warning_ok,
    tip_message_box_buttons,
    tip_qdialog_button_box,
)
from desktop_app.table_clipboard import (
    CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX,
    QTABLE_PLAIN_TEXT_ROLE,
    copy_table_row_as_tsv,
    plain_display_table_item,
)
from desktop_app.statement_line_match_panel import StatementLineMatchPanel
from desktop_app.theme import (
    AMOUNT_NEGATIVE,
    AMOUNT_POSITIVE,
    register_table_style_sheet,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ACCOUNT_TYPE_LABELS = {
    "checking": "Checking",
    "savings": "Savings",
    "credit_card": "Credit Card",
    "other": "Other",
}


def _format_currency(value: Optional[float]) -> str:
    if value is None:
        return ""
    return f"${value:,.2f}"


def _bank_import_keyboard_shortcuts_help_text() -> str:
    """Plain text for **Help → Bank import shortcuts…** (aligned with **F5** behavior)."""
    return (
        "F5 — Refresh accounts and import batches. If an import batch is selected, it is "
        "re-opened when it still exists (register preview and reconciliation update).\n\n"
        "AI-assisted line reconciliation (right-hand panel): **Run mock extract & compare** "
        "fills the **Bank register** **Stmt match** column for the same bank account and "
        "switches the main window to that tab (reconciliation mode turns on there). "
        "If that account cannot be opened on the register, a warning explains that **Stmt match** was not updated. "
        "On success the main **status bar** also shows a short confirmation, then restores the company line.\n\n"
        "Manage Bank Accounts (dialog): right-click the accounts table (including empty area) "
        "for Keyboard shortcuts… (same as this dialog).\n\n"
        "Document Intake:\n"
        "Help → Document intake shortcuts… (includes File → Backup / Restore via probooks.backup).\n\n"
        "COA, Journal, Reports, Audit:\n"
        "Help → More tab shortcuts (F5)…\n\n"
        "Register tab has additional shortcuts:\n"
        "Help → Bank register keyboard shortcuts…\n\n"
        "Business tab (rules, invoices, bills, payroll):\n"
        "Help → Business shortcuts…"
    )


def show_bank_import_keyboard_shortcuts_dialog(parent: QWidget) -> None:
    message_box_information_ok(
        parent,
        "Bank import shortcuts",
        _bank_import_keyboard_shortcuts_help_text(),
        ok_tip="Close; shortcuts apply when Bank Import has focus. "
        "Company .db: File → Backup / Restore (probooks.backup).",
    )


# ===========================================================================
# ManageAccountsDialog
# ===========================================================================

class ManageAccountsDialog(QDialog):
    """CRUD dialog for bank accounts."""

    accountsChanged = Signal()

    def __init__(self, db: BankDatabase, coa_db: Optional[COADatabase] = None, parent=None):
        super().__init__(parent)
        self._db = db
        self._coa_db = coa_db
        self.setWindowTitle("Manage Bank Accounts")
        self.setToolTip(
            "Add, edit, or delete bank accounts used for CSV/PDF import and the register. "
            "Changes write to the open company .db — use File → Backup / probooks backup before risky edits."
        )
        self.resize(560, 400)
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["Name", "Account #", "Bank", "Type"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_accounts_table_context_menu)
        self._table.setSortingEnabled(True)
        self._table.setToolTip(
            "Bank accounts used for import and the register. Right-click for Keyboard shortcuts… "
            "(including on empty area)."
        )
        layout.addWidget(self._table)

        # Buttons
        btn_row = QHBoxLayout()
        self._btn_add = QPushButton("➕  Add Account")
        self._btn_add.setToolTip("Add a bank account.")
        self._btn_add.clicked.connect(self._on_add)
        self._btn_edit = QPushButton("✏️  Edit")
        self._btn_edit.setToolTip("Edit the selected account.")
        self._btn_edit.clicked.connect(self._on_edit)
        self._btn_del = QPushButton("🗑️  Delete")
        self._btn_del.setToolTip(
            "Delete the selected account and its transactions. "
            "Back up the company .db from File → Backup / probooks backup first."
        )
        self._btn_del.clicked.connect(self._on_delete)
        btn_row.addWidget(self._btn_add)
        btn_row.addWidget(self._btn_edit)
        btn_row.addWidget(self._btn_del)
        btn_row.addStretch()
        btn_close = QPushButton("Close")
        btn_close.setToolTip("Close this dialog.")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _on_accounts_table_context_menu(self, pos):
        idx = self._table.indexAt(pos)
        m = QMenu(self)
        act_keys = m.addAction(
            "Keyboard shortcuts…",
            lambda: show_bank_import_keyboard_shortcuts_dialog(self),
        )
        act_keys.setToolTip(
            "Same summary as Help → Bank import shortcuts… "
            "(F5, batches, transactions, Manage Accounts). "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        if not idx.isValid():
            m.exec(self._table.viewport().mapToGlobal(pos))
            return
        row = idx.row()
        it = self._table.item(row, 0)
        if it is None or coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole)) is None:
            m.exec(self._table.viewport().mapToGlobal(pos))
            return
        m.addSeparator()
        act_copy = m.addAction("Copy row", partial(copy_table_row_as_tsv, self._table, row))
        act_copy.setToolTip(
            "Copy this account row as tab-separated text for pasting into a spreadsheet or editor. "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        m.exec(self._table.viewport().mapToGlobal(pos))

    def _refresh(self):
        self._table.setSortingEnabled(False)
        accounts = self._db.list_bank_accounts()
        packed = [
            (aid, acct)
            for acct in accounts
            if (aid := coerce_combo_int_id(acct["id"])) is not None
        ]
        self._table.setRowCount(len(packed))
        for r, (aid, acct) in enumerate(packed):
            name_it = plain_display_table_item(acct["name"] or "")
            name_it.setData(Qt.ItemDataRole.UserRole, aid)
            self._table.setItem(r, 0, name_it)
            self._table.setItem(
                r, 1, plain_display_table_item(acct["account_number"] or "")
            )
            self._table.setItem(r, 2, plain_display_table_item(acct["bank_name"] or ""))
            type_lbl = _ACCOUNT_TYPE_LABELS.get(
                acct["account_type"], acct["account_type"]
            )
            self._table.setItem(r, 3, plain_display_table_item(str(type_lbl)))
        self._table.setSortingEnabled(True)

    def _selected_account(self):
        row = self._table.currentRow()
        if row < 0:
            return None
        it = self._table.item(row, 0)
        if it is None:
            return None
        aid = coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole))
        if aid is None:
            return None
        return self._db.get_bank_account(aid)

    def _on_add(self):
        dlg = _AccountEditDialog(db=self._db, coa_db=self._coa_db, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh()
            self.accountsChanged.emit()

    def _on_edit(self):
        acct = self._selected_account()
        if not acct:
            message_box_information_ok(
                self,
                "No Selection",
                "Please select an account to edit.",
                ok_tip="Close; click a row in the accounts table first.",
            )
            return
        dlg = _AccountEditDialog(db=self._db, coa_db=self._coa_db, account=acct, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh()
            self.accountsChanged.emit()

    def _on_delete(self):
        acct = self._selected_account()
        if not acct:
            message_box_information_ok(
                self,
                "No Selection",
                "Please select an account to delete.",
                ok_tip="Close; click a row in the accounts table first.",
            )
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Confirm Delete")
        box.setText(
            "Delete account '"
            f"{escape_ampersand_for_qt(acct['name'] or '')}' and all its transactions?"
            "\n\nThis cannot be undone."
        )
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        box.setToolTip(
            "Permanently removes this bank account and all imported transactions for it; cannot be undone. "
            "Back up the company .db from File → Backup / probooks backup first."
        )
        tip_message_box_buttons(
            box,
            yes="Permanently delete this bank account and its imported transactions.",
            no="Keep the account and all transactions.",
        )
        reply = box.exec()
        if reply == QMessageBox.StandardButton.Yes:
            aid = coerce_combo_int_id(acct["id"])
            if aid is None:
                message_box_warning_ok(
                    self,
                    "Cannot delete",
                    "This account row has no valid id.",
                    ok_tip="Close; refresh the list (F5) or pick another row.",
                )
                return
            self._db.delete_bank_account(aid)
            self._refresh()
            self.accountsChanged.emit()


class _AccountEditDialog(QDialog):
    """Add/edit a single bank account."""

    def __init__(self, db: BankDatabase, coa_db: Optional[COADatabase] = None, account=None, parent=None):
        super().__init__(parent)
        self._db = db
        self._coa_db = coa_db
        self._account = account
        self.setWindowTitle("Add Bank Account" if account is None else "Edit Bank Account")
        self.setMinimumWidth(360)
        self.setToolTip(
            "Bank account label, institution, type, and optional GL cash line for register posting."
        )
        self._build_ui()
        if account:
            self._populate(account)

    def _build_ui(self):
        layout = QFormLayout(self)
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self._name = QLineEdit()
        self._name.setToolTip("Friendly label for this bank account in ProBooks+ai (required).")
        self._number = QLineEdit()
        self._number.setToolTip("Bank account number or mask (optional; for your reference).")
        self._bank = QLineEdit()
        self._bank.setToolTip("Institution name (optional).")
        self._type = QComboBox()
        for key in ACCOUNT_TYPES:
            self._type.addItem(_ACCOUNT_TYPE_LABELS[key], key)
        self._type.setToolTip("Checking, savings, credit card, or other — used for import behavior hints.")

        layout.addRow("Account Name *", self._name)
        layout.addRow("Account Number", self._number)
        layout.addRow("Bank Name", self._bank)
        layout.addRow("Account Type", self._type)

        self._gl_combo: Optional[QComboBox] = None
        if self._coa_db is not None:
            self._gl_combo = QComboBox()
            self._gl_combo.setEditable(True)
            self._gl_combo.addItem("(not mapped)", "")
            for disp in self._coa_db.display_list():
                self._gl_combo.addItem(escape_ampersand_for_qt(disp), disp)
            self._gl_combo.setToolTip(
                "Chart-of-accounts cash or bank line used when posting from this bank account."
            )
            layout.addRow("GL cash account", self._gl_combo)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        tip_qdialog_button_box(
            btns,
            ok="Save this bank account and close the dialog.",
            cancel="Close without saving this bank account.",
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def _populate(self, acct):
        self._name.setText(acct["name"] or "")
        self._number.setText(acct["account_number"] or "")
        self._bank.setText(acct["bank_name"] or "")
        idx = ACCOUNT_TYPES.index(acct["account_type"]) if acct["account_type"] in ACCOUNT_TYPES else 0
        self._type.setCurrentIndex(idx)
        if self._gl_combo is not None:
            ad = dict(acct)
            gl = (ad.get("gl_display_account") or "").strip()
            ix = self._gl_combo.findData(gl)
            if ix >= 0:
                self._gl_combo.setCurrentIndex(ix)
            elif gl:
                self._gl_combo.setCurrentText(gl)
            else:
                self._gl_combo.setCurrentIndex(0)

    def _on_accept(self):
        name = self._name.text().strip()
        if not name:
            message_box_warning_ok(
                self,
                "Validation",
                "Account Name is required.",
                ok_tip="Close; enter a display name for this bank account.",
            )
            return
        account_type = self._type.currentData()
        gl_display = ""
        if self._gl_combo is not None:
            gl_display = (self._gl_combo.currentData() or self._gl_combo.currentText() or "").strip()
        if self._account is None:
            self._db.add_bank_account(
                name=name,
                account_number=self._number.text().strip(),
                bank_name=self._bank.text().strip(),
                account_type=account_type,
                gl_display_account=gl_display,
                imp_csv_date_col="",
                imp_csv_amount_col="",
                imp_csv_desc_col="",
                imp_csv_ref_col="",
            )
        else:
            o = dict(self._account)
            edit_id = coerce_combo_int_id(self._account["id"])
            if edit_id is None:
                message_box_warning_ok(
                    self,
                    "Cannot save",
                    "This account has no valid id.",
                    ok_tip="Close; cancel and reopen Manage Accounts.",
                )
                return
            self._db.update_bank_account(
                account_id=edit_id,
                name=name,
                account_number=self._number.text().strip(),
                bank_name=self._bank.text().strip(),
                account_type=account_type,
                institution=o.get("institution") or "",
                last4=o.get("last4") or "",
                notes=o.get("notes") or "",
                is_active=bool(int(o.get("is_active", 1))),
                gl_display_account=gl_display if self._gl_combo is not None else None,
                imp_csv_date_col=o.get("imp_csv_date_col") or "",
                imp_csv_amount_col=o.get("imp_csv_amount_col") or "",
                imp_csv_desc_col=o.get("imp_csv_desc_col") or "",
                imp_csv_ref_col=o.get("imp_csv_ref_col") or "",
            )
        self.accept()


# ===========================================================================
# ColumnMappingDialog
# ===========================================================================

class ColumnMappingDialog(QDialog):
    """Maps CSV column headers to the required import fields."""

    def __init__(self, headers: list[str], parent=None, preset: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle("Map CSV Columns")
        self.setMinimumWidth(380)
        self.setToolTip(
            "Choose which CSV columns hold transaction dates and amounts (required); "
            "description and reference are optional."
        )
        self._headers = headers
        self._preset = preset or {}
        self._build_ui()

    def _build_ui(self):
        layout = QFormLayout(self)

        def _combo(required=True):
            cb = QComboBox()
            if not required:
                cb.addItem("(none)", "")
            for h in self._headers:
                cb.addItem(escape_ampersand_for_qt(h), h)
            return cb

        self._date_col = _combo(required=True)
        self._amount_col = _combo(required=True)
        self._desc_col = _combo(required=False)
        self._ref_col = _combo(required=False)

        # Smart defaults
        for i, h in enumerate(self._headers):
            hl = h.lower()
            if any(k in hl for k in ("date", "txn_date", "trans date")):
                self._date_col.setCurrentIndex(i)
            if any(k in hl for k in ("amount", "amt", "debit", "credit")):
                self._amount_col.setCurrentIndex(i)
            if any(k in hl for k in ("desc", "memo", "narrative")):
                self._desc_col.setCurrentIndex(i + 1)  # +1 for "(none)"
            if any(k in hl for k in ("ref", "check", "chk", "number")):
                self._ref_col.setCurrentIndex(i + 1)

        self._apply_saved_preset()

        self._date_col.setToolTip("CSV column containing each transaction date.")
        self._amount_col.setToolTip(
            "CSV column for amount. Outflows should be negative if your file uses signed amounts."
        )
        self._desc_col.setToolTip("Optional column for payee, memo, or description text.")
        self._ref_col.setToolTip("Optional column for check number, reference, or external ID.")

        layout.addRow("Date column *", self._date_col)
        layout.addRow("Amount column *", self._amount_col)
        layout.addRow("Description column", self._desc_col)
        layout.addRow("Reference / check # column", self._ref_col)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        tip_qdialog_button_box(
            btns,
            ok="Apply this column mapping and continue the CSV import.",
            cancel="Cancel mapping; no rows will be imported from this step.",
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def _apply_saved_preset(self):
        p = self._preset
        if not p:
            return

        def _pick(cb: QComboBox, name: str):
            want = (p.get(name) or "").strip()
            if not want:
                return
            idx = cb.findData(want, Qt.ItemDataRole.UserRole)
            if idx < 0:
                return
            cb.setCurrentIndex(idx)

        _pick(self._date_col, "date_col")
        _pick(self._amount_col, "amount_col")
        _pick(self._desc_col, "description_col")
        _pick(self._ref_col, "ref_col")

    @property
    def date_col(self) -> str:
        d = self._date_col.currentData(Qt.ItemDataRole.UserRole)
        return str(d) if d is not None else ""

    @property
    def amount_col(self) -> str:
        d = self._amount_col.currentData(Qt.ItemDataRole.UserRole)
        return str(d) if d is not None else ""

    @property
    def description_col(self) -> str:
        data = self._desc_col.currentData(Qt.ItemDataRole.UserRole)
        if data == "":
            return ""
        return str(data) if data is not None else ""

    @property
    def ref_col(self) -> str:
        data = self._ref_col.currentData(Qt.ItemDataRole.UserRole)
        if data == "":
            return ""
        return str(data) if data is not None else ""


# ===========================================================================
# StatementPeriodDialog
# ===========================================================================

class StatementPeriodDialog(QDialog):
    """Capture statement start/end dates and beginning/ending balances."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(
            escape_ampersand_for_qt("Statement Period & Balances")
        )
        self.setMinimumWidth(360)
        self.setToolTip(
            "Statement dates and opening/closing balances from the bank; stored on this import batch for reconciliation."
        )
        self._build_ui()

    def _build_ui(self):
        layout = QFormLayout(self)

        self._start = QDateEdit()
        self._start.setCalendarPopup(True)
        self._start.setDisplayFormat("yyyy-MM-dd")

        self._end = QDateEdit()
        self._end.setCalendarPopup(True)
        self._end.setDisplayFormat("yyyy-MM-dd")
        self._end.setDate(QDate.currentDate())
        self._start.setDate(QDate.currentDate().addMonths(-1))

        self._begin_bal = QDoubleSpinBox()
        self._begin_bal.setRange(-9_999_999.99, 9_999_999.99)
        self._begin_bal.setDecimals(2)
        self._begin_bal.setPrefix("$ ")

        self._end_bal = QDoubleSpinBox()
        self._end_bal.setRange(-9_999_999.99, 9_999_999.99)
        self._end_bal.setDecimals(2)
        self._end_bal.setPrefix("$ ")

        self._start.setToolTip("First date on the bank statement (inclusive).")
        self._end.setToolTip("Last date on the bank statement (inclusive).")
        self._begin_bal.setToolTip("Account balance at the start of the statement, from the bank.")
        self._end_bal.setToolTip("Account balance at the end of the statement, from the bank.")

        layout.addRow("Statement Start *", self._start)
        layout.addRow("Statement End *", self._end)
        layout.addRow("Beginning Balance *", self._begin_bal)
        layout.addRow("Ending Balance *", self._end_bal)

        note = QLabel(
            "Tip: Beginning and ending balances are taken from your bank statement.\n"
            "Outflows (payments, withdrawals) must be negative in the CSV."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #555; font-size: 11px;")
        note.setToolTip(
            "Balances must match the bank statement; CSV amounts for outflows should be negative when signed."
        )
        layout.addRow(note)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        tip_qdialog_button_box(
            btns,
            ok="Continue import using this statement period and opening/closing balances.",
            cancel="Cancel without setting statement period.",
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def _on_accept(self):
        if self._start.date() > self._end.date():
            message_box_warning_ok(
                self,
                "Invalid Dates",
                "Statement Start must not be after Statement End.",
                ok_tip="Close; adjust start and end so the period is valid.",
            )
            return
        self.accept()

    @property
    def statement_start(self) -> str:
        return self._start.date().toString("yyyy-MM-dd")

    @property
    def statement_end(self) -> str:
        return self._end.date().toString("yyyy-MM-dd")

    @property
    def beginning_balance(self) -> float:
        return self._begin_bal.value()

    @property
    def ending_balance(self) -> float:
        return self._end_bal.value()


# ===========================================================================
# BlankBankRegisterTable
# ===========================================================================

class BlankBankRegisterTable(QTableWidget):
    """Register-style grid: blank editable rows, or import-batch rows (read-only) + padded blanks."""

    COLUMNS = ["Date", "Description", "Debit", "Credit", "Balance"]
    _HEADER_TIPS = (
        "Transaction date from the import (ISO).",
        "Payee or memo text from the import.",
        "Positive amounts (typical deposits / inflows) for this batch; shown in green.",
        "Absolute value of negative amounts (payments / outflows); shown in red.",
        "Running total after each row when the batch has a beginning balance "
        "(green if ≥ 0, red if negative; same accent colors as the Register tab).",
    )
    DEFAULT_ROW_COUNT = 15
    _RO_FLAGS = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("bankRegisterTable")
        self.setStyleSheet(register_table_style_sheet())
        self.setColumnCount(len(self.COLUMNS))
        self.setHorizontalHeaderLabels(self.COLUMNS)
        for col, tip in enumerate(self._HEADER_TIPS):
            h = self.horizontalHeaderItem(col)
            if h is not None:
                h.setToolTip(tip)
        self.reset_blank()
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setWordWrap(True)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.setSortingEnabled(False)
        self.setToolTip(
            "Register-style preview: select an import batch to load its rows (debit/credit split); "
            "running balance fills when the batch has a beginning balance. "
            "Padding rows stay editable scratch space. Right-click for Keyboard shortcuts… "
            "(including on empty area)."
        )

    def reset_blank(self) -> None:
        """Restore default empty editable rows (no batch selection)."""
        self.setRowCount(self.DEFAULT_ROW_COUNT)
        for r in range(self.DEFAULT_ROW_COUNT):
            for c in range(len(self.COLUMNS)):
                it = QTableWidgetItem("")
                it.setFlags(
                    Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsEditable
                )
                self.setItem(r, c, it)

    def populate_import_batch(
        self,
        transactions: list,
        *,
        beginning_balance: Optional[float] = None,
    ) -> None:
        """Debit/credit split; optional running balance from *beginning_balance* + each row amount (date order)."""
        n = len(transactions)
        total_rows = max(n, self.DEFAULT_ROW_COUNT)
        self.setRowCount(total_rows)

        running: Optional[float] = (
            float(beginning_balance) if beginning_balance is not None else None
        )

        for r in range(n):
            row = dict(transactions[r])
            tid = row.get("id")
            date_it = plain_display_table_item(row.get("txn_date") or "")
            tid_coerced = coerce_combo_int_id(tid)
            if tid_coerced is not None:
                date_it.setData(Qt.ItemDataRole.UserRole, tid_coerced)
            date_it.setFlags(self._RO_FLAGS)
            self.setItem(r, 0, date_it)

            desc_it = plain_display_table_item(row.get("description") or "")
            desc_it.setFlags(self._RO_FLAGS)
            self.setItem(r, 1, desc_it)

            amt = float(row.get("amount") or 0.0)
            debit_txt = f"${amt:,.2f}" if amt > 0 else ""
            credit_txt = f"${abs(amt):,.2f}" if amt < 0 else ""
            debit_it = QTableWidgetItem(escape_ampersand_for_qt(debit_txt))
            debit_it.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            debit_it.setFlags(self._RO_FLAGS)
            debit_it.setData(QTABLE_PLAIN_TEXT_ROLE, debit_txt)
            if debit_txt:
                debit_it.setForeground(QColor(AMOUNT_POSITIVE))
            self.setItem(r, 2, debit_it)
            credit_it = QTableWidgetItem(escape_ampersand_for_qt(credit_txt))
            credit_it.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            credit_it.setFlags(self._RO_FLAGS)
            credit_it.setData(QTABLE_PLAIN_TEXT_ROLE, credit_txt)
            if credit_txt:
                credit_it.setForeground(QColor(AMOUNT_NEGATIVE))
            self.setItem(r, 3, credit_it)

            if running is not None:
                running = round(running + amt, 2)
                bal_txt = f"${running:,.2f}"
            else:
                bal_txt = ""
            bal_it = QTableWidgetItem(escape_ampersand_for_qt(bal_txt))
            bal_it.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            bal_it.setFlags(self._RO_FLAGS)
            if bal_txt:
                bal_it.setForeground(
                    QColor(AMOUNT_NEGATIVE)
                    if running < 0
                    else QColor(AMOUNT_POSITIVE)
                )
            bal_it.setData(QTABLE_PLAIN_TEXT_ROLE, bal_txt)
            self.setItem(r, 4, bal_it)

        for r in range(n, total_rows):
            for c in range(len(self.COLUMNS)):
                it = QTableWidgetItem("")
                it.setFlags(
                    Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsEditable
                )
                self.setItem(r, c, it)


# ===========================================================================
# ReconciliationPanel
# ===========================================================================

class ReconciliationPanel(QGroupBox):
    """
    Displays reconciliation summary and the Mark Reconciled button.

    Emits :attr:`reconcileRequested` when the button is clicked.
    Emits :attr:`exportCsvRequested` when the user asks for a CSV reconciliation report.
    Emits :attr:`toleranceChanged` when the user changes the reconcile tolerance (saved in QSettings).
    """

    reconcileRequested = Signal()
    exportCsvRequested = Signal()
    toleranceChanged = Signal()

    def __init__(self, parent=None):
        super().__init__("Reconciliation", parent)
        self.setToolTip(
            "Compares statement dates and balances to imported transactions for the selected batch."
        )
        self._build_ui()
        self._reset()

    def _build_ui(self):
        layout = QFormLayout(self)

        def _lbl():
            l = QLabel("—")
            l.setAlignment(Qt.AlignmentFlag.AlignRight)
            l.setToolTip("Populates when you select an import batch with statement metadata.")
            return l

        self._lbl_start = _lbl()
        self._lbl_end = _lbl()
        self._lbl_begin = _lbl()
        self._lbl_ending = _lbl()
        self._lbl_sum = _lbl()
        self._lbl_computed = _lbl()
        self._lbl_diff = _lbl()

        layout.addRow("Statement start:", self._lbl_start)
        layout.addRow("Statement end:", self._lbl_end)
        layout.addRow("Beginning balance:", self._lbl_begin)
        layout.addRow("Ending balance (bank):", self._lbl_ending)
        layout.addRow("Sum of imported transactions:", self._lbl_sum)
        layout.addRow("Computed ending balance:", self._lbl_computed)
        layout.addRow("Difference:", self._lbl_diff)

        self._spin_tol = QDoubleSpinBox()
        self._spin_tol.setRange(0.0, 999.99)
        self._spin_tol.setDecimals(2)
        self._spin_tol.setSingleStep(0.01)
        self._spin_tol.setPrefix("±$ ")
        self._spin_tol.setToolTip(
            "Mark Reconciled is enabled when the absolute difference "
            "is within this amount (pennies rounding or small bank fees)."
        )
        s = QSettings()
        self._spin_tol.blockSignals(True)
        self._spin_tol.setValue(float(s.value("reconciliation/tolerance", 0.0)))
        self._spin_tol.blockSignals(False)
        self._spin_tol.valueChanged.connect(self._on_tolerance_changed)
        layout.addRow("Match within:", self._spin_tol)

        btn_row = QHBoxLayout()
        self._btn_reconcile = QPushButton("✔  Mark Reconciled")
        self._btn_reconcile.setToolTip(
            "Mark the selected import batch reconciled when the difference is within "
            "Match within (see tolerance field tooltip)."
        )
        self._btn_reconcile.setEnabled(False)
        self._btn_reconcile.clicked.connect(self.reconcileRequested)
        btn_row.addWidget(self._btn_reconcile)
        self._btn_export_csv = QPushButton("Export report CSV\u2026")
        self._btn_export_csv.setToolTip(
            "Export a reconciliation summary CSV for the selected import batch."
        )
        self._btn_export_csv.setEnabled(False)
        self._btn_export_csv.clicked.connect(self.exportCsvRequested.emit)
        btn_row.addWidget(self._btn_export_csv)
        layout.addRow(btn_row)

        self._lbl_status = QLabel("")
        self._lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_status.setToolTip(
            "Reconciliation outcome: balanced within tolerance, difference too large, or already reconciled."
        )
        layout.addRow(self._lbl_status)

    def _on_tolerance_changed(self, value: float):
        QSettings().setValue("reconciliation/tolerance", float(value))
        self.toleranceChanged.emit()

    def reconciliation_tolerance(self) -> float:
        return round(float(self._spin_tol.value()), 2)

    def _reset(self):
        for lbl in (self._lbl_start, self._lbl_end, self._lbl_begin,
                    self._lbl_ending, self._lbl_sum, self._lbl_computed, self._lbl_diff):
            lbl.setText("—")
        self._btn_reconcile.setEnabled(False)
        self._btn_export_csv.setEnabled(False)
        self._lbl_status.setText("")

    def update_from_batch(self, batch, recon_result: Optional[dict] = None):
        """Populate panel fields from *batch* row and optional *recon_result* dict."""
        self._btn_export_csv.setEnabled(True)
        self._lbl_start.setText(batch["statement_start"] or "—")
        self._lbl_end.setText(batch["statement_end"] or "—")
        self._lbl_begin.setText(_format_currency(batch["beginning_balance"]))
        self._lbl_ending.setText(_format_currency(batch["ending_balance"]))

        if recon_result:
            tol = self.reconciliation_tolerance()
            self._lbl_sum.setText(_format_currency(recon_result["sum_of_amounts"]))
            self._lbl_computed.setText(_format_currency(recon_result["computed_ending"]))
            diff = recon_result["difference"]
            self._lbl_diff.setText(_format_currency(diff))

            if recon_result["can_reconcile"]:
                self._lbl_diff.setStyleSheet("color: green; font-weight: bold;")
            else:
                self._lbl_diff.setStyleSheet("color: red; font-weight: bold;")

            if batch["is_reconciled"]:
                self._btn_reconcile.setEnabled(False)
                self._lbl_status.setText("✅  Already reconciled")
                self._lbl_status.setStyleSheet("color: green; font-weight: bold;")
            elif recon_result["can_reconcile"]:
                self._btn_reconcile.setEnabled(True)
                if tol <= 0.0:
                    self._lbl_status.setText(
                        "Difference is $0.00 – ready to reconcile."
                    )
                else:
                    self._lbl_status.setText(
                        f"Within ±{_format_currency(tol)} tolerance – ready to reconcile."
                    )
                self._lbl_status.setStyleSheet("color: green;")
            else:
                self._btn_reconcile.setEnabled(False)
                self._lbl_status.setText(
                    f"Difference {_format_currency(abs(diff))} exceeds "
                    f"allowed ±{_format_currency(tol)}."
                )
                self._lbl_status.setStyleSheet("color: red;")
        else:
            self._lbl_sum.setText("—")
            self._lbl_computed.setText("—")
            self._lbl_diff.setText("—")
            self._btn_reconcile.setEnabled(False)

    def set_reconciled(self):
        self._btn_reconcile.setEnabled(False)
        self._lbl_status.setText("✅  Reconciled!")
        self._lbl_status.setStyleSheet("color: green; font-weight: bold;")


# ===========================================================================
# BankImportTab
# ===========================================================================

class BankImportTab(QWidget):
    """
    Main Bank Import tab.

    Layout (horizontal splitter):
      Left  – account selector, batch list, import & manage buttons
      Right – top: **BlankBankRegisterTable** (import batch rows when selected); bottom: **Statement reconciliation** … + **Reconciliation** panel
    """

    def __init__(
        self,
        db: BankDatabase,
        coa_db: Optional[COADatabase] = None,
        *,
        register_tab=None,
        after_stmt_match_sync: Optional[Callable[[], None]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._db = db
        self._coa_db = coa_db
        self._register_tab = register_tab
        self._after_stmt_match_sync = after_stmt_match_sync
        self._current_batch_id: Optional[int] = None
        self._current_account_id: Optional[int] = None
        self._import_worker: Optional[CsvImportWorker] = None
        self._build_ui()
        self._refresh_accounts()

    def _forward_line_match_to_register(self, bank_account_id: object, results: list) -> None:
        """Sync AI line reconciliation table to **Bank register → Stmt match** overlay."""
        if self._register_tab is None:
            return
        aid = coerce_combo_int_id(bank_account_id)
        if aid is None:
            message_box_warning_ok(
                self,
                "Stmt match sync",
                "Invalid bank account id for Stmt match sync.",
                ok_tip="Close; select a bank account on Bank Import, then run compare again.",
            )
            return
        applied = self._register_tab.apply_line_match_results_from_import(
            aid, list(results)
        )
        if not applied:
            message_box_warning_ok(
                self,
                "Stmt match sync",
                "Could not select that bank account on Bank register. "
                "It may have been removed or the lists are out of date. "
                "Stmt match was not updated.",
                ok_tip="Close; try F5 on Bank Import and Register, or Manage Accounts….",
            )
        fn = self._after_stmt_match_sync
        if applied and fn is not None:
            fn()

    def _build_ui(self):
        self.setToolTip(
            "Bank CSV/PDF import and reconciliation: choose an account, import batches, transactions, "
            "and match statement balances (F5 refreshes when this tab has focus). "
            "Same company SQLite database as other main tabs; File → Backup / Restore (probooks.backup)."
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        # ── Header row ──────────────────────────────────────────────────────
        hdr_row = QHBoxLayout()
        hdr_lbl = QLabel("🏦  Bank Account:")
        hdr_lbl.setToolTip(
            "Label for the account selector; import batches below belong to this bank account."
        )
        hdr_row.addWidget(hdr_lbl)

        self._acct_combo = QComboBox()
        self._acct_combo.setMinimumWidth(220)
        self._acct_combo.setToolTip(
            "Bank account whose import batches are listed below."
        )
        self._acct_combo.currentIndexChanged.connect(self._on_account_changed)
        hdr_row.addWidget(self._acct_combo)

        btn_manage = QPushButton("Manage Accounts…")
        btn_manage.setToolTip(
            "Add, edit, or delete bank accounts (writes to the company .db). "
            "The accounts table context menu includes Keyboard shortcuts… (including on empty area). "
            "Use File → Backup / probooks backup before destructive changes."
        )
        btn_manage.clicked.connect(self._on_manage_accounts)
        hdr_row.addWidget(btn_manage)

        btn_import = QPushButton("📥  Import CSV…")
        btn_import.setToolTip(
            "Import bank transactions from a CSV file for the selected account (writes to the company .db). "
            "File → Backup / probooks backup before re-import experiments or large replaces."
        )
        btn_import.clicked.connect(self._on_import_csv)
        hdr_row.addWidget(btn_import)

        btn_pdf = QPushButton("📄  Import PDF\u2026")
        btn_pdf.setToolTip(
            "Digital PDFs with a text layer only. Scanned statements need OCR (not included). "
            "Parsed rows write to the company SQLite file (File → Backup / probooks backup first if unsure)."
        )
        btn_pdf.clicked.connect(self._on_import_pdf)
        hdr_row.addWidget(btn_pdf)

        hdr_row.addStretch()
        outer.addLayout(hdr_row)

        import_hint = QLabel(
            "Import formats: <b>CSV</b> — typical bank export. "
            "<b>PDF</b> — digital statements with <i>selectable</i> text only; "
            "image-only (scanned) PDFs are not supported yet — use CSV or a download from your bank."
        )
        import_hint.setTextFormat(Qt.TextFormat.RichText)
        import_hint.setWordWrap(True)
        import_hint.setStyleSheet("color: #A0A0B0; font-size: 11px;")
        import_hint.setToolTip(
            "ProBooks+ai reads text embedded in PDFs; it does not OCR scans. "
            "For photo or scanned statements, use CSV until automatic OCR ships (Phase 7)."
        )
        outer.addWidget(import_hint)

        # ── Splitter: batch list (left) | detail (right) ──────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: batch list
        left = QWidget()
        left.setToolTip(
            "Import batches column for the selected bank account; pick a batch to load transactions and reconciliation on the right. "
            "Batches and transactions live in the company SQLite file (File → Backup / Restore, probooks.backup)."
        )
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        lbl_import_batches = QLabel("Import Batches:")
        lbl_import_batches.setToolTip(
            "CSV import batches for the selected bank account; choose one to load transactions and reconciliation. "
            "Same shared company .db as the rest of the app (File → Backup / probooks backup)."
        )
        left_layout.addWidget(lbl_import_batches)
        batch_hint = QLabel(
            "Batches appear after you <b>Import CSV</b> or <b>Import PDF</b> for the account above. "
            "Select a batch to load transactions and reconciliation on the right."
        )
        batch_hint.setTextFormat(Qt.TextFormat.RichText)
        batch_hint.setWordWrap(True)
        batch_hint.setStyleSheet("color: #A0A0B0; font-size: 11px;")
        batch_hint.setToolTip(
            "Each import creates a batch for the selected bank account. "
            "Use Manage Accounts… if no account is listed yet."
        )
        left_layout.addWidget(batch_hint)
        self._batch_table = QTableWidget()
        self._batch_table.setColumnCount(3)
        self._batch_table.setHorizontalHeaderLabels(["Imported", "Statement Period", "Reconciled"])
        for col, tip in enumerate(
            (
                "Date this batch was imported (YYYY-MM-DD).",
                "Statement start → end dates for this batch, if provided at import.",
                "Whether Mark Reconciled has been applied for this batch.",
            )
        ):
            h = self._batch_table.horizontalHeaderItem(col)
            if h is not None:
                h.setToolTip(tip)
        self._batch_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._batch_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._batch_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._batch_table.itemSelectionChanged.connect(self._on_batch_selected)
        self._batch_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._batch_table.customContextMenuRequested.connect(
            self._on_batch_context_menu
        )
        self._batch_table.setSortingEnabled(True)
        self._batch_table.setToolTip(
            "Import batches for the selected bank account; pick one to load its transactions. "
            "Right-click for Keyboard shortcuts… (including on empty area). "
            "Batches live in the company .db (File → Backup / Restore, probooks.backup)."
        )
        left_layout.addWidget(self._batch_table)
        splitter.addWidget(left)

        # Right: blank register shell + reconciliation
        right_splitter = QSplitter(Qt.Orientation.Vertical)

        txn_col = QWidget()
        txn_col_layout = QVBoxLayout(txn_col)
        txn_col_layout.setContentsMargins(0, 0, 0, 0)
        txn_col_layout.setSpacing(6)

        self._txn_table = BlankBankRegisterTable()
        self._txn_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._txn_table.customContextMenuRequested.connect(
            self._on_import_txn_context_menu
        )
        txn_col_layout.addWidget(self._txn_table, stretch=1)
        right_splitter.addWidget(txn_col)

        recon_col = QWidget()
        recon_col_layout = QVBoxLayout(recon_col)
        recon_col_layout.setContentsMargins(0, 0, 0, 0)
        recon_col_layout.setSpacing(6)

        lbl_recon_header = QLabel("Statement reconciliation:")
        lbl_recon_header.setToolTip(
            "Statement period, opening and closing balances, and Mark Reconciled for the batch "
            "selected on the left. Same company .db (File → Backup / probooks backup)."
        )
        recon_col_layout.addWidget(lbl_recon_header)

        self._recon_placeholder = QLabel()
        self._recon_placeholder.setTextFormat(Qt.TextFormat.RichText)
        self._recon_placeholder.setWordWrap(True)
        self._recon_placeholder.setStyleSheet("color: #A0A0B0; font-size: 11px;")
        self._recon_placeholder.setToolTip(
            "Statement period, balances, and Mark Reconciled apply to the batch highlighted on the left."
        )
        recon_col_layout.addWidget(self._recon_placeholder)

        self._recon_panel_empty_hint = QLabel(
            "Select a batch on the left to view statement reconciliation"
        )
        self._recon_panel_empty_hint.setWordWrap(True)
        self._recon_panel_empty_hint.setStyleSheet("color: #A0A0B0; font-size: 11px;")
        self._recon_panel_empty_hint.setToolTip(
            "Statement balances, difference, and Mark Reconciled populate after you pick a batch on the left."
        )
        recon_col_layout.addWidget(self._recon_panel_empty_hint)

        self._recon_panel = ReconciliationPanel()
        self._recon_panel.reconcileRequested.connect(self._on_reconcile)
        self._recon_panel.exportCsvRequested.connect(self._on_export_reconciliation_csv)
        self._recon_panel.toleranceChanged.connect(
            self._on_reconciliation_tolerance_changed
        )
        recon_col_layout.addWidget(self._recon_panel, stretch=1)

        lbl_ai_line = QLabel("AI-assisted line reconciliation:")
        lbl_ai_line.setToolTip(
            "Mock PDF extract vs register (Matched / Missing / Extra). "
            "Reconciled checkboxes are UI-only; register data is unchanged."
        )
        recon_col_layout.addWidget(lbl_ai_line)
        self._line_match_panel = StatementLineMatchPanel(self._db, parent=self)
        recon_col_layout.addWidget(self._line_match_panel)
        self._line_match_panel.set_context(None, None)
        if self._register_tab is not None:
            self._line_match_panel.line_match_results_ready.connect(
                self._forward_line_match_to_register
            )

        right_splitter.addWidget(recon_col)

        right_splitter.setSizes([400, 200])
        right_splitter.setToolTip(
            "Drag to give more space to the register preview or to the reconciliation panel. "
            "Both panes show data from the shared company SQLite file (File → Backup / probooks backup)."
        )
        splitter.addWidget(right_splitter)
        splitter.setSizes([280, 720])
        splitter.setToolTip(
            "Drag to widen the import batch list or the register preview and reconciliation area. "
            "All bank import data is in the open company .db (File → Backup / Restore, probooks.backup)."
        )

        outer.addWidget(splitter)

        tip = QLabel(
            "F5 refreshes accounts and import batches; if a batch is selected, it is re-opened when "
            "it still exists (preview + reconciliation refresh). "
            "Right-click the batch or register preview, or the Manage Bank Accounts table "
            "(even on empty area), for Keyboard shortcuts…. "
            "Help → Bank import shortcuts…; Register tab: Help → Bank register keyboard shortcuts…. "
            "Company SQLite: File → Backup / Restore (probooks.backup, CLI probooks backup/restore)."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #A0A0B0; font-size: 11px;")
        tip.setToolTip(
            "F5 reloads accounts and batches; right-click tables for Keyboard shortcuts… "
            "(see Help → Bank import shortcuts…). "
            "Back up the company .db from File → Backup / probooks backup before destructive imports."
        )
        outer.addWidget(tip)

        sc_reload = QShortcut(QKeySequence("F5"), self)
        sc_reload.setContext(Qt.WidgetWithChildrenShortcut)
        sc_reload.activated.connect(self._reload_bank_import_view)

        self._sync_right_pane_placeholder_visibility()

    def _sync_right_pane_placeholder_visibility(self) -> None:
        """Show short hints when no batch is loaded so the reconciliation area reads clearly."""
        aid = self._current_account_id
        batches = getattr(self, "_batches", None)
        if self._current_batch_id is not None:
            self._recon_placeholder.setVisible(False)
            self._recon_panel_empty_hint.setVisible(False)
            return

        self._recon_placeholder.setVisible(True)
        self._recon_panel_empty_hint.setVisible(False)

        if aid is None:
            self._recon_placeholder.setText(
                "After you select an account and an <b>import batch</b>, statement balances and "
                "<b>Mark Reconciled</b> apply here."
            )
        elif batches is not None and len(batches) == 0:
            self._recon_placeholder.setText(
                "Reconciliation needs an import batch with statement dates and balances—create one via "
                "<b>Import CSV</b> or <b>Import PDF</b> first."
            )
        else:
            self._recon_placeholder.setVisible(False)
            self._recon_panel_empty_hint.setVisible(True)

    # -----------------------------------------------------------------------
    # Account helpers
    # -----------------------------------------------------------------------

    def _reload_bank_import_view(self) -> None:
        """Reload account combo and batches; re-open the same import batch when it still exists."""
        saved_account = self._current_account_id
        saved_batch = self._current_batch_id
        self._refresh_accounts()
        if saved_account is None or saved_batch is None:
            return
        for r in range(self._batch_table.rowCount()):
            it = self._batch_table.item(r, 0)
            if it is None:
                continue
            bid = coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole))
            if bid is None or not combo_int_ids_equal(bid, saved_batch):
                continue
            self._batch_table.selectRow(r)
            self._on_batch_selected()
            return

    def _show_bank_import_keyboard_shortcuts_help(self) -> None:
        show_bank_import_keyboard_shortcuts_dialog(self)

    def _refresh_accounts(self):
        self._acct_combo.blockSignals(True)
        prev_id = self._current_account_id
        self._acct_combo.clear()
        accounts = self._db.list_bank_accounts()
        self._accounts = accounts
        if not accounts:
            self._acct_combo.addItem("(no accounts – click Manage Accounts)", None)
        else:
            for acct in accounts:
                aid = coerce_combo_int_id(acct["id"])
                if aid is None:
                    continue
                label = f"{acct['name']} – {acct['bank_name'] or 'Bank'}"
                self._acct_combo.addItem(escape_ampersand_for_qt(label), aid)
        self._acct_combo.blockSignals(False)

        # Restore previous selection if possible (int-safe: combo userData may not match type)
        if prev_id is not None:
            ix = combo_index_for_int_user_data(self._acct_combo, prev_id)
            if ix is not None:
                self._acct_combo.setCurrentIndex(ix)

        self._on_account_changed()

    def _on_account_changed(self):
        aid = coerce_combo_int_id(self._acct_combo.currentData())
        self._current_account_id = aid
        self._current_batch_id = None
        self._txn_table.reset_blank()
        self._recon_panel._reset()
        self._line_match_panel.set_context(aid, None)
        if aid is not None:
            self._refresh_batches(aid)
        else:
            self._batch_table.setRowCount(0)
            self._batches = []
        self._sync_right_pane_placeholder_visibility()

    # -----------------------------------------------------------------------
    # Batch list
    # -----------------------------------------------------------------------

    def _refresh_batches(self, account_id: int):
        self._batch_table.setSortingEnabled(False)
        batches = self._db.list_batches(account_id)
        self._batches = batches
        packed = [
            (bid, b)
            for b in batches
            if (bid := coerce_combo_int_id(b["id"])) is not None
        ]
        self._batch_table.setRowCount(len(packed))
        for r, (bid, b) in enumerate(packed):
            imported_at = (b["imported_at"] or "")[:10]
            period = ""
            if b["statement_start"] and b["statement_end"]:
                period = f"{b['statement_start']} → {b['statement_end']}"
            reconciled_text = "✅ Yes" if b["is_reconciled"] else "No"

            item0 = plain_display_table_item(imported_at)
            item0.setData(Qt.ItemDataRole.UserRole, bid)
            self._batch_table.setItem(r, 0, item0)
            self._batch_table.setItem(r, 1, plain_display_table_item(period))
            item_recon = plain_display_table_item(reconciled_text)
            if b["is_reconciled"]:
                item_recon.setForeground(QColor("green"))
            self._batch_table.setItem(r, 2, item_recon)
        self._batch_table.setSortingEnabled(True)
        self._sync_right_pane_placeholder_visibility()

    def _on_import_txn_context_menu(self, pos):
        idx = self._txn_table.indexAt(pos)
        menu = QMenu(self)
        act_keys = menu.addAction(
            "Keyboard shortcuts…", self._show_bank_import_keyboard_shortcuts_help
        )
        act_keys.setToolTip(
            "Same summary as Help → Bank import shortcuts… "
            "(F5, batches, register preview, reconciliation). "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        if not idx.isValid():
            menu.exec(self._txn_table.viewport().mapToGlobal(pos))
            return
        row = idx.row()
        it = self._txn_table.item(row, 0)
        tid = (
            coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole)) if it is not None else None
        )
        if tid is None:
            menu.exec(self._txn_table.viewport().mapToGlobal(pos))
            return
        menu.addSeparator()
        act_att = menu.addAction(
            "Open attachment…",
            partial(self._open_import_txn_attachment, tid),
        )
        act_att.setToolTip("Open the linked file for this imported transaction if a path is set.")
        act_copy = menu.addAction("Copy row", partial(copy_table_row_as_tsv, self._txn_table, row))
        act_copy.setToolTip(
            "Copy this transaction row as tab-separated text for pasting into a spreadsheet or editor. "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        act_history = menu.addAction("View change history…")
        act_history.setToolTip(
            "Open field-level audit history for this bank transaction (import/register edits)."
        )
        chosen = menu.exec(self._txn_table.viewport().mapToGlobal(pos))
        if chosen == act_history:
            show_entity_audit_history(
                self,
                self._db._conn,
                "bank_transaction",
                tid,
                window_title=f"Change history — transaction #{tid}",
                empty_message="No audit entries recorded for this transaction yet.",
            )

    def _open_import_txn_attachment(self, txn_id: int) -> None:
        row = self._db.get_transaction(txn_id)
        if row is None:
            return
        apath = (dict(row).get("attachment_path") or "").strip()
        open_local_attachment(
            self,
            apath,
            empty_message="No attachment path is set for this transaction.",
        )

    def _on_batch_context_menu(self, pos):
        idx = self._batch_table.indexAt(pos)
        menu = QMenu(self)
        act_keys = menu.addAction(
            "Keyboard shortcuts…", self._show_bank_import_keyboard_shortcuts_help
        )
        act_keys.setToolTip(
            "Same summary as Help → Bank import shortcuts… "
            "(F5, batches, register preview, reconciliation). "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        if not idx.isValid():
            menu.exec(self._batch_table.viewport().mapToGlobal(pos))
            return
        row = idx.row()
        it = self._batch_table.item(row, 0)
        bid = (
            coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole)) if it is not None else None
        )
        if bid is None:
            menu.exec(self._batch_table.viewport().mapToGlobal(pos))
            return
        menu.addSeparator()
        act_copy = menu.addAction("Copy row", partial(copy_table_row_as_tsv, self._batch_table, row))
        act_copy.setToolTip(
            "Copy this import batch row as tab-separated text for pasting into a spreadsheet or editor. "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        act_history = menu.addAction("View change history…")
        act_history.setToolTip(
            "Open field-level audit history for this import batch (metadata and reconciliation edits)."
        )
        chosen = menu.exec(self._batch_table.viewport().mapToGlobal(pos))
        if chosen == act_history:
            show_entity_audit_history(
                self,
                self._db._conn,
                "bank_import_batch",
                bid,
                window_title=f"Change history — import batch #{bid}",
                empty_message="No audit entries recorded for this import batch yet.",
            )

    def _on_batch_selected(self):
        row = self._batch_table.currentRow()
        if not hasattr(self, "_batches") or row < 0:
            self._current_batch_id = None
            self._txn_table.reset_blank()
            self._recon_panel._reset()
            self._line_match_panel.set_context(self._current_account_id, None)
            self._sync_right_pane_placeholder_visibility()
            return
        it = self._batch_table.item(row, 0)
        if it is None:
            self._current_batch_id = None
            self._txn_table.reset_blank()
            self._recon_panel._reset()
            self._line_match_panel.set_context(self._current_account_id, None)
            self._sync_right_pane_placeholder_visibility()
            return
        bid = coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole))
        if bid is None:
            self._current_batch_id = None
            self._txn_table.reset_blank()
            self._recon_panel._reset()
            self._line_match_panel.set_context(self._current_account_id, None)
            self._sync_right_pane_placeholder_visibility()
            return
        batch = next(
            (b for b in self._batches if combo_int_ids_equal(b["id"], bid)), None
        )
        if batch is None:
            self._current_batch_id = None
            self._txn_table.reset_blank()
            self._recon_panel._reset()
            self._line_match_panel.set_context(self._current_account_id, None)
            self._sync_right_pane_placeholder_visibility()
            return
        self._current_batch_id = bid
        self._load_batch(batch)
        self._line_match_panel.set_context(self._current_account_id, dict(batch))

    def _on_reconciliation_tolerance_changed(self):
        if self._current_batch_id is None or not hasattr(self, "_batches"):
            return
        batch = next(
            (
                b
                for b in self._batches
                if combo_int_ids_equal(b["id"], self._current_batch_id)
            ),
            None,
        )
        if batch is not None:
            self._load_batch(batch)

    def _load_batch(self, batch):
        """Load transactions and reconciliation info for the selected batch."""
        txns = self._db.list_transactions(
            bank_account_id=batch["bank_account_id"],
            statement_start=batch["statement_start"],
            statement_end=batch["statement_end"],
        )
        self._txn_table.populate_import_batch(
            txns,
            beginning_balance=batch.get("beginning_balance"),
        )

        # Compute reconciliation (no side effects)
        if batch["beginning_balance"] is not None and batch["ending_balance"] is not None:
            from probooksai.bank_import import compute_reconciliation
            recon = compute_reconciliation(
                transactions=[dict(t) for t in txns],
                beginning_balance=batch["beginning_balance"],
                ending_balance=batch["ending_balance"],
                statement_start=batch["statement_start"],
                statement_end=batch["statement_end"],
                tolerance=self._recon_panel.reconciliation_tolerance(),
            )
            self._recon_panel.update_from_batch(batch, recon)
        else:
            self._recon_panel.update_from_batch(batch, None)
        self._sync_right_pane_placeholder_visibility()

    # -----------------------------------------------------------------------
    # Import CSV
    # -----------------------------------------------------------------------

    def _on_import_pdf(self):
        if self._current_account_id is None:
            message_box_information_ok(
                self,
                "No Account",
                "Please create and select a bank account first (Manage Accounts).",
                ok_tip="Close; use Manage Accounts to add an account, then select it above.",
            )
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import bank statement PDF (selectable text required)",
            "",
            "PDF documents (*.pdf);;All files (*.*)",
        )
        if not path:
            return

        ocr_result = None
        text_layer_empty = False
        try:
            from probooksai.statement_extract import parse_statement_text
            from probooksai.statement_ocr_stub import (
                StatementScanStatus,
                extract_rows_from_statement_scan,
            )
            from probooksai.statement_pdf import extract_text_from_pdf

            text = extract_text_from_pdf(path)
            text_layer_empty = not (text or "").strip()
            rows = parse_statement_text(text)
            if text_layer_empty or not rows:
                ocr_result = extract_rows_from_statement_scan(
                    path, mime_type="application/pdf"
                )
                if ocr_result.rows:
                    rows = ocr_result.rows
        except ImportError as exc:
            message_box_warning_ok(
                self,
                "PDF dependency",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; install the missing package or use Import CSV.",
            )
            return
        except Exception as exc:
            message_box_critical_ok(
                self,
                "PDF error",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; try another PDF or use Import CSV.",
            )
            return

        if not rows:
            lines = [
                "No transaction lines could be imported from this PDF.",
                "",
            ]
            if text_layer_empty:
                lines.append(
                    "No selectable text was found in this file. It may be a scanned PDF "
                    "(image-only) with no text layer."
                )
                lines.append("")
            else:
                lines.append(
                    "No lines with a leading date and trailing amount were found in the "
                    "extracted text."
                )
                lines.append("")
            lines.append("Digital PDFs with selectable text work best for Import PDF.")
            lines.append("")
            if (
                ocr_result is not None
                and ocr_result.status == StatementScanStatus.FAILED
                and ocr_result.error
            ):
                lines.append(
                    escape_ampersand_for_qt(
                        f"Statement scan could not finish: {ocr_result.error}"
                    )
                )
                lines.append("")
            elif (
                ocr_result is not None
                and ocr_result.status == StatementScanStatus.NOT_IMPLEMENTED
            ):
                lines.append(
                    "Automatic OCR for scanned statements is not available in this build yet "
                    "(Phase 7 vision path)."
                )
                lines.append("")
            lines.append("You can still use Import CSV.")
            message_box_information_ok(
                self,
                "No transaction lines",
                "\n".join(lines),
                ok_tip="Close; use a text-based PDF or import via CSV.",
            )
            return

        period_dlg = StatementPeriodDialog(parent=self)
        if period_dlg.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            from probooksai.rules_engine import apply_rules_to_parsed_rows

            apply_rules_to_parsed_rows(self._db._conn, rows)
        except sqlite3.OperationalError:
            pass

        batch_id = self._db.create_batch(
            self._current_account_id,
            filename=Path(path).name,
            statement_start=period_dlg.statement_start,
            statement_end=period_dlg.statement_end,
            beginning_balance=period_dlg.beginning_balance,
            ending_balance=period_dlg.ending_balance,
        )
        result = self._db.import_transactions(
            batch_id, self._current_account_id, rows
        )
        self._refresh_batches(self._current_account_id)
        message_box_information_ok(
            self,
            "Import complete",
            f"Imported {result['inserted']} new transaction(s) from PDF.\n"
            f"Skipped {result['skipped']} duplicate(s).",
            ok_tip="Close; review batches and transactions below.",
        )

    def _on_import_csv(self):
        if self._current_account_id is None:
            message_box_information_ok(
                self,
                "No Account",
                "Please create and select a bank account first (Manage Accounts).",
                ok_tip="Close; use Manage Accounts to add an account, then select it above.",
            )
            return

        # 1. Pick file
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import bank transactions CSV (map columns next)",
            "",
            "CSV spreadsheets (*.csv);;All files (*.*)",
        )
        if not path:
            return

        # 2. Read & detect headers
        try:
            content = Path(path).read_text(encoding="utf-8-sig")
        except Exception as exc:
            message_box_critical_ok(
                self,
                "File Error",
                f"Could not read file:\n{escape_ampersand_for_qt(str(exc))}",
                ok_tip="Close; check the path, encoding, and that the file is not open elsewhere.",
            )
            return

        import csv, io
        reader = csv.reader(io.StringIO(content))
        try:
            headers = next(reader)
        except StopIteration:
            message_box_critical_ok(
                self,
                "File Error",
                "CSV file appears to be empty.",
                ok_tip="Close; pick a CSV with a header row and data.",
            )
            return

        # 3. Column mapping (pre-fill from saved profile when present)
        acct_row = self._db.get_bank_account(self._current_account_id)
        preset = {}
        if acct_row is not None:
            ar = dict(acct_row)
            preset = {
                "date_col": ar.get("imp_csv_date_col") or "",
                "amount_col": ar.get("imp_csv_amount_col") or "",
                "description_col": ar.get("imp_csv_desc_col") or "",
                "ref_col": ar.get("imp_csv_ref_col") or "",
            }
        col_dlg = ColumnMappingDialog(headers, parent=self, preset=preset)
        if col_dlg.exec() != QDialog.DialogCode.Accepted:
            return

        # 4. Statement period & balances
        period_dlg = StatementPeriodDialog(parent=self)
        if period_dlg.exec() != QDialog.DialogCode.Accepted:
            return

        self._db.save_import_column_profile(
            self._current_account_id,
            date_col=col_dlg.date_col,
            amount_col=col_dlg.amount_col,
            description_col=col_dlg.description_col,
            ref_col=col_dlg.ref_col,
        )

        # 5. Import on background thread (keeps UI responsive for large files)
        import_kw = dict(
            bank_account_id=self._current_account_id,
            csv_content=content,
            date_col=col_dlg.date_col,
            amount_col=col_dlg.amount_col,
            description_col=col_dlg.description_col,
            ref_col=col_dlg.ref_col,
            filename=Path(path).name,
            statement_start=period_dlg.statement_start,
            statement_end=period_dlg.statement_end,
            beginning_balance=period_dlg.beginning_balance,
            ending_balance=period_dlg.ending_balance,
        )

        cancel_csv = QPushButton("Cancel")
        cancel_csv.setToolTip(
            "Stop importing after the current batch of rows; transactions already written stay in the database."
        )
        prog_dlg = QProgressDialog(self)
        prog_dlg.setCancelButton(cancel_csv)
        prog_dlg.setToolTip(
            "CSV import progress. Cancel stops further rows; some transactions may already be saved."
        )
        prog_dlg.setLabelText("Importing…")
        prog_dlg.setWindowTitle("Importing bank CSV")
        prog_dlg.setWindowModality(Qt.WindowModality.WindowModal)
        prog_dlg.setMinimumDuration(0)
        prog_dlg.setRange(0, 0)

        worker = CsvImportWorker(self._db._db_path, import_kw)
        self._import_worker = worker

        def on_progress(cur: int, total: int):
            prog_dlg.setRange(0, max(total, 1))
            prog_dlg.setValue(min(cur, prog_dlg.maximum()))
            prog_dlg.setLabelText(f"Importing rows… {cur} / {total}")

        def on_done(result: dict):
            prog_dlg.reset()
            prog_dlg.accept()
            self._import_worker = None
            worker.deleteLater()
            self._refresh_batches(self._current_account_id)
            extra = ""
            if result.get("cancelled"):
                extra = "\n\nImport was cancelled; some rows may have been saved."
            message_box_information_ok(
                self,
                "Import complete",
                f"Imported {result['inserted']} new transaction(s).\n"
                f"Skipped {result['skipped']} duplicate(s)."
                + extra,
                ok_tip="Close; review batches and transactions; partial import may remain if cancelled.",
            )

        def on_fail(msg: str):
            prog_dlg.reset()
            prog_dlg.accept()
            self._import_worker = None
            worker.deleteLater()
            message_box_critical_ok(
                self,
                "Import failed",
                escape_ampersand_for_qt(msg),
                ok_tip="Close; fix the CSV mapping or data and try again.",
            )

        worker.progress.connect(on_progress)
        worker.finished_ok.connect(on_done)
        worker.failed.connect(on_fail)
        prog_dlg.canceled.connect(worker.request_cancel)
        worker.start()
        prog_dlg.exec()

    # -----------------------------------------------------------------------
    # Manage accounts
    # -----------------------------------------------------------------------

    def _on_manage_accounts(self):
        dlg = ManageAccountsDialog(self._db, coa_db=self._coa_db, parent=self)
        dlg.accountsChanged.connect(self._refresh_accounts)
        dlg.exec()
        self._refresh_accounts()

    # -----------------------------------------------------------------------
    # Reconcile
    # -----------------------------------------------------------------------

    def _on_export_reconciliation_csv(self):
        if self._current_batch_id is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save bank reconciliation report (CSV)",
            "",
            "CSV spreadsheets (*.csv);;All files (*.*)",
        )
        if not path:
            return
        try:
            self._db.export_batch_reconciliation_csv(
                self._current_batch_id,
                path,
                tolerance=self._recon_panel.reconciliation_tolerance(),
            )
        except Exception as exc:
            message_box_critical_ok(
                self,
                "Export failed",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; check path, permissions, and disk space.",
            )
            return
        message_box_information_ok(
            self,
            "Export complete",
            f"Reconciliation report saved to:\n{escape_ampersand_for_qt(path)}",
            ok_tip="Close; open the CSV from the path shown.",
        )

    def _on_reconcile(self):
        if self._current_batch_id is None:
            return
        tol = self._recon_panel.reconciliation_tolerance()
        result = self._db.reconcile_batch(self._current_batch_id, tolerance=tol)
        if result["reconciled"]:
            self._recon_panel.set_reconciled()
            self._refresh_batches(self._current_account_id)
            message_box_information_ok(
                self,
                "Reconciled",
                "This statement has been marked as reconciled. ✅",
                ok_tip="Close; this batch is marked reconciled in the list.",
            )
        else:
            message_box_warning_ok(
                self,
                "Cannot Reconcile",
                f"The difference is ${result['difference']:,.2f}.\n"
                f"Reconciliation is allowed when |difference| is within ±${tol:,.2f}.",
                ok_tip="Close; adjust tolerance, fix imports, or correct statement balances.",
            )
