"""
desktop_app.bank_import_tab
============================
PySide6 widget for bank account setup, CSV import, and statement reconciliation.

**F5** (when this tab or its children have focus) reloads accounts and import batches and
re-selects the same batch when it still exists, refreshing transactions and reconciliation.

Tabs / widgets
--------------
  BankImportTab          – top-level QWidget (intended as a tab in MainWindow)
  ManageAccountsDialog   – CRUD dialog for bank_accounts
  StatementPeriodDialog  – capture statement start/end dates + opening/closing balances
  ColumnMappingDialog    – map CSV headers to required fields
  TransactionsTable      – QTableWidget showing imported bank_transactions
  ReconciliationPanel    – shows computed reconciliation and Mark Reconciled button
"""

from __future__ import annotations

import sqlite3
from functools import partial
from pathlib import Path
from typing import Optional

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
from desktop_app.csv_import_worker import CsvImportWorker
from desktop_app.open_attachment import open_local_attachment
from desktop_app.qt_mnemonic import escape_ampersand_for_qt
from desktop_app.table_clipboard import (
    NumericAmountTableItem,
    copy_table_row_as_tsv,
    plain_display_table_item,
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


def _color_for_amount(amount: float) -> QColor:
    return QColor("#C62828") if amount < 0 else QColor("#1B5E20")


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
        layout.addWidget(self._table)

        # Buttons
        btn_row = QHBoxLayout()
        self._btn_add = QPushButton("➕  Add Account")
        self._btn_add.clicked.connect(self._on_add)
        self._btn_edit = QPushButton("✏️  Edit")
        self._btn_edit.clicked.connect(self._on_edit)
        self._btn_del = QPushButton("🗑️  Delete")
        self._btn_del.clicked.connect(self._on_delete)
        btn_row.addWidget(self._btn_add)
        btn_row.addWidget(self._btn_edit)
        btn_row.addWidget(self._btn_del)
        btn_row.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _on_accounts_table_context_menu(self, pos):
        idx = self._table.indexAt(pos)
        if not idx.isValid():
            return
        row = idx.row()
        m = QMenu(self)
        m.addAction("Copy row", partial(copy_table_row_as_tsv, self._table, row))
        m.exec(self._table.viewport().mapToGlobal(pos))

    def _refresh(self):
        self._table.setSortingEnabled(False)
        accounts = self._db.list_bank_accounts()
        self._table.setRowCount(len(accounts))
        for r, acct in enumerate(accounts):
            name_it = plain_display_table_item(acct["name"] or "")
            name_it.setData(Qt.ItemDataRole.UserRole, int(acct["id"]))
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
        aid = it.data(Qt.ItemDataRole.UserRole)
        if aid is None:
            return None
        try:
            aid_int = int(aid)
        except (TypeError, ValueError):
            return None
        return self._db.get_bank_account(aid_int)

    def _on_add(self):
        dlg = _AccountEditDialog(db=self._db, coa_db=self._coa_db, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh()
            self.accountsChanged.emit()

    def _on_edit(self):
        acct = self._selected_account()
        if not acct:
            QMessageBox.information(self, "No Selection", "Please select an account to edit.")
            return
        dlg = _AccountEditDialog(db=self._db, coa_db=self._coa_db, account=acct, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh()
            self.accountsChanged.emit()

    def _on_delete(self):
        acct = self._selected_account()
        if not acct:
            QMessageBox.information(self, "No Selection", "Please select an account to delete.")
            return
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            "Delete account '"
            f"{escape_ampersand_for_qt(acct['name'] or '')}' and all its transactions?"
            "\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._db.delete_bank_account(acct["id"])
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
        self._build_ui()
        if account:
            self._populate(account)

    def _build_ui(self):
        layout = QFormLayout(self)
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self._name = QLineEdit()
        self._number = QLineEdit()
        self._bank = QLineEdit()
        self._type = QComboBox()
        for key in ACCOUNT_TYPES:
            self._type.addItem(_ACCOUNT_TYPE_LABELS[key], key)

        layout.addRow("Account Name *", self._name)
        layout.addRow("Account Number", self._number)
        layout.addRow("Bank Name", self._bank)
        layout.addRow("Account Type", self._type)

        self._gl_combo: Optional[QComboBox] = None
        if coa_db is not None:
            self._gl_combo = QComboBox()
            self._gl_combo.setEditable(True)
            self._gl_combo.addItem("(not mapped)", "")
            for disp in coa_db.display_list():
                self._gl_combo.addItem(escape_ampersand_for_qt(disp), disp)
            layout.addRow("GL cash account", self._gl_combo)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
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
            QMessageBox.warning(self, "Validation", "Account Name is required.")
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
            self._db.update_bank_account(
                account_id=self._account["id"],
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

        layout.addRow("Date column *", self._date_col)
        layout.addRow("Amount column *", self._amount_col)
        layout.addRow("Description column", self._desc_col)
        layout.addRow("Reference / check # column", self._ref_col)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
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
        layout.addRow(note)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def _on_accept(self):
        if self._start.date() > self._end.date():
            QMessageBox.warning(
                self, "Invalid Dates",
                "Statement Start must not be after Statement End."
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
# TransactionsTable
# ===========================================================================

class TransactionsTable(QTableWidget):
    """Displays bank transactions (read-only)."""

    COLUMNS = ["Date", "Description", "Amount", "Reference"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(len(self.COLUMNS))
        self.setHorizontalHeaderLabels(self.COLUMNS)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.setSortingEnabled(True)

    def populate(self, transactions: list):
        self.setSortingEnabled(False)
        self.setRowCount(len(transactions))
        for r, txn in enumerate(transactions):
            date_item = plain_display_table_item(txn["txn_date"] or "")
            date_item.setData(Qt.ItemDataRole.UserRole, txn["id"])
            self.setItem(r, 0, date_item)
            self.setItem(r, 1, plain_display_table_item(txn["description"] or ""))

            amount = float(txn["amount"])
            amt_item = NumericAmountTableItem(amount)
            amt_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            amt_item.setForeground(_color_for_amount(amount))
            self.setItem(r, 2, amt_item)

            self.setItem(r, 3, plain_display_table_item(txn["ref_number"] or ""))
        self.setSortingEnabled(True)


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
        self._build_ui()
        self._reset()

    def _build_ui(self):
        layout = QFormLayout(self)

        def _lbl():
            l = QLabel("—")
            l.setAlignment(Qt.AlignmentFlag.AlignRight)
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
        self._btn_reconcile.setEnabled(False)
        self._btn_reconcile.clicked.connect(self.reconcileRequested)
        btn_row.addWidget(self._btn_reconcile)
        self._btn_export_csv = QPushButton("Export report CSV\u2026")
        self._btn_export_csv.setEnabled(False)
        self._btn_export_csv.clicked.connect(self.exportCsvRequested.emit)
        btn_row.addWidget(self._btn_export_csv)
        layout.addRow(btn_row)

        self._lbl_status = QLabel("")
        self._lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
      Right – top: transactions table; bottom: reconciliation panel
    """

    def __init__(self, db: BankDatabase, coa_db: Optional[COADatabase] = None, parent=None):
        super().__init__(parent)
        self._db = db
        self._coa_db = coa_db
        self._current_batch_id: Optional[int] = None
        self._current_account_id: Optional[int] = None
        self._import_worker: Optional[CsvImportWorker] = None
        self._build_ui()
        self._refresh_accounts()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        # ── Header row ──────────────────────────────────────────────────────
        hdr_row = QHBoxLayout()
        hdr_lbl = QLabel("🏦  Bank Account:")
        hdr_row.addWidget(hdr_lbl)

        self._acct_combo = QComboBox()
        self._acct_combo.setMinimumWidth(220)
        self._acct_combo.currentIndexChanged.connect(self._on_account_changed)
        hdr_row.addWidget(self._acct_combo)

        btn_manage = QPushButton("Manage Accounts…")
        btn_manage.clicked.connect(self._on_manage_accounts)
        hdr_row.addWidget(btn_manage)

        btn_import = QPushButton("📥  Import CSV…")
        btn_import.clicked.connect(self._on_import_csv)
        hdr_row.addWidget(btn_import)

        btn_pdf = QPushButton("📄  Import PDF\u2026")
        btn_pdf.setToolTip(
            "Digital PDFs with a text layer only. Scanned statements need OCR (not included)."
        )
        btn_pdf.clicked.connect(self._on_import_pdf)
        hdr_row.addWidget(btn_pdf)

        hdr_row.addStretch()
        outer.addLayout(hdr_row)

        # ── Splitter: batch list (left) | detail (right) ──────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: batch list
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Import Batches:"))
        self._batch_table = QTableWidget()
        self._batch_table.setColumnCount(3)
        self._batch_table.setHorizontalHeaderLabels(["Imported", "Statement Period", "Reconciled"])
        self._batch_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._batch_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._batch_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._batch_table.itemSelectionChanged.connect(self._on_batch_selected)
        self._batch_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._batch_table.customContextMenuRequested.connect(
            self._on_batch_context_menu
        )
        self._batch_table.setSortingEnabled(True)
        left_layout.addWidget(self._batch_table)
        splitter.addWidget(left)

        # Right: transactions + reconciliation
        right_splitter = QSplitter(Qt.Orientation.Vertical)

        self._txn_table = TransactionsTable()
        self._txn_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._txn_table.customContextMenuRequested.connect(
            self._on_import_txn_context_menu
        )
        right_splitter.addWidget(self._txn_table)

        self._recon_panel = ReconciliationPanel()
        self._recon_panel.reconcileRequested.connect(self._on_reconcile)
        self._recon_panel.exportCsvRequested.connect(self._on_export_reconciliation_csv)
        self._recon_panel.toleranceChanged.connect(
            self._on_reconciliation_tolerance_changed
        )
        right_splitter.addWidget(self._recon_panel)

        right_splitter.setSizes([400, 200])
        splitter.addWidget(right_splitter)
        splitter.setSizes([280, 720])

        outer.addWidget(splitter)

        tip = QLabel(
            "F5 refreshes accounts and import batches; if a batch is selected, it is re-opened when "
            "it still exists (updates transactions and reconciliation). "
            "More shortcuts: Help → Bank register keyboard shortcuts (Register tab)."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #A0A0B0; font-size: 11px;")
        outer.addWidget(tip)

        sc_reload = QShortcut(QKeySequence("F5"), self)
        sc_reload.setContext(Qt.WidgetWithChildrenShortcut)
        sc_reload.activated.connect(self._reload_bank_import_view)

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
            bid = it.data(Qt.ItemDataRole.UserRole)
            if bid is None:
                continue
            try:
                if int(bid) != int(saved_batch):
                    continue
            except (TypeError, ValueError):
                continue
            self._batch_table.selectRow(r)
            self._on_batch_selected()
            return

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
                label = f"{acct['name']} – {acct['bank_name'] or 'Bank'}"
                self._acct_combo.addItem(
                    escape_ampersand_for_qt(label), acct["id"]
                )
        self._acct_combo.blockSignals(False)

        # Restore previous selection if possible
        if prev_id is not None:
            for i in range(self._acct_combo.count()):
                if self._acct_combo.itemData(i) == prev_id:
                    self._acct_combo.setCurrentIndex(i)
                    break

        self._on_account_changed()

    def _on_account_changed(self):
        aid = self._acct_combo.currentData()
        self._current_account_id = aid
        self._current_batch_id = None
        self._txn_table.setRowCount(0)
        self._recon_panel._reset()
        if aid is not None:
            self._refresh_batches(aid)
        else:
            self._batch_table.setRowCount(0)

    # -----------------------------------------------------------------------
    # Batch list
    # -----------------------------------------------------------------------

    def _refresh_batches(self, account_id: int):
        self._batch_table.setSortingEnabled(False)
        batches = self._db.list_batches(account_id)
        self._batches = batches
        self._batch_table.setRowCount(len(batches))
        for r, b in enumerate(batches):
            imported_at = (b["imported_at"] or "")[:10]
            period = ""
            if b["statement_start"] and b["statement_end"]:
                period = f"{b['statement_start']} → {b['statement_end']}"
            reconciled_text = "✅ Yes" if b["is_reconciled"] else "No"

            item0 = plain_display_table_item(imported_at)
            item0.setData(Qt.ItemDataRole.UserRole, b["id"])
            self._batch_table.setItem(r, 0, item0)
            self._batch_table.setItem(r, 1, plain_display_table_item(period))
            item_recon = plain_display_table_item(reconciled_text)
            if b["is_reconciled"]:
                item_recon.setForeground(QColor("green"))
            self._batch_table.setItem(r, 2, item_recon)
        self._batch_table.setSortingEnabled(True)

    def _on_import_txn_context_menu(self, pos):
        idx = self._txn_table.indexAt(pos)
        if not idx.isValid():
            return
        row = idx.row()
        it = self._txn_table.item(row, 0)
        if it is None:
            return
        tid = it.data(Qt.ItemDataRole.UserRole)
        if tid is None:
            return
        menu = QMenu(self)
        menu.addAction(
            "Open attachment…",
            partial(self._open_import_txn_attachment, int(tid)),
        )
        menu.addAction("Copy row", partial(copy_table_row_as_tsv, self._txn_table, row))
        act_history = menu.addAction("View change history…")
        chosen = menu.exec(self._txn_table.viewport().mapToGlobal(pos))
        if chosen == act_history:
            show_entity_audit_history(
                self,
                self._db._conn,
                "bank_transaction",
                int(tid),
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
        if not idx.isValid():
            return
        row = idx.row()
        it = self._batch_table.item(row, 0)
        if it is None:
            return
        bid = it.data(Qt.ItemDataRole.UserRole)
        if bid is None:
            return
        menu = QMenu(self)
        menu.addAction("Copy row", partial(copy_table_row_as_tsv, self._batch_table, row))
        act_history = menu.addAction("View change history…")
        chosen = menu.exec(self._batch_table.viewport().mapToGlobal(pos))
        if chosen == act_history:
            show_entity_audit_history(
                self,
                self._db._conn,
                "bank_import_batch",
                int(bid),
                window_title=f"Change history — import batch #{bid}",
                empty_message="No audit entries recorded for this import batch yet.",
            )

    def _on_batch_selected(self):
        row = self._batch_table.currentRow()
        if not hasattr(self, "_batches") or row < 0:
            return
        it = self._batch_table.item(row, 0)
        if it is None:
            return
        bid = it.data(Qt.ItemDataRole.UserRole)
        if bid is None:
            return
        try:
            bid_int = int(bid)
        except (TypeError, ValueError):
            return
        batch = next((b for b in self._batches if int(b["id"]) == bid_int), None)
        if batch is None:
            self._current_batch_id = None
            return
        self._current_batch_id = batch["id"]
        self._load_batch(batch)

    def _on_reconciliation_tolerance_changed(self):
        if self._current_batch_id is None or not hasattr(self, "_batches"):
            return
        batch = next(
            (b for b in self._batches if b["id"] == self._current_batch_id),
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
        self._txn_table.populate(txns)

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

    # -----------------------------------------------------------------------
    # Import CSV
    # -----------------------------------------------------------------------

    def _on_import_pdf(self):
        if self._current_account_id is None:
            QMessageBox.information(
                self, "No Account",
                "Please create and select a bank account first (Manage Accounts).",
            )
            return

        path, _ = QFileDialog.getOpenFileName(
            self, "Select bank statement PDF", "", "PDF Files (*.pdf);;All Files (*)"
        )
        if not path:
            return

        try:
            from probooksai.statement_pdf import extract_text_from_pdf
            from probooksai.statement_extract import parse_statement_text

            text = extract_text_from_pdf(path)
            rows = parse_statement_text(text)
        except ImportError as exc:
            QMessageBox.warning(
                self,
                "PDF dependency",
                escape_ampersand_for_qt(str(exc)),
            )
            return
        except Exception as exc:
            QMessageBox.critical(
                self, "PDF error", escape_ampersand_for_qt(str(exc))
            )
            return

        if not rows:
            QMessageBox.information(
                self,
                "No transaction lines",
                "No lines with a leading date and trailing amount were found.\n\n"
                "This works on digital PDFs with selectable text. "
                "Scanned statements require OCR (Phase 7 vision path). "
                "You can still use Import CSV.",
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
        QMessageBox.information(
            self,
            "Import complete",
            f"Imported {result['inserted']} new transaction(s) from PDF.\n"
            f"Skipped {result['skipped']} duplicate(s).",
        )

    def _on_import_csv(self):
        if self._current_account_id is None:
            QMessageBox.information(
                self, "No Account",
                "Please create and select a bank account first (Manage Accounts)."
            )
            return

        # 1. Pick file
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Bank Statement CSV", "", "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return

        # 2. Read & detect headers
        try:
            content = Path(path).read_text(encoding="utf-8-sig")
        except Exception as exc:
            QMessageBox.critical(
                self,
                "File Error",
                f"Could not read file:\n{escape_ampersand_for_qt(str(exc))}",
            )
            return

        import csv, io
        reader = csv.reader(io.StringIO(content))
        try:
            headers = next(reader)
        except StopIteration:
            QMessageBox.critical(self, "File Error", "CSV file appears to be empty.")
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

        dlg = QProgressDialog(self)
        dlg.setLabelText("Importing…")
        dlg.setWindowTitle("CSV import")
        dlg.setCancelButtonText("Cancel")
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setRange(0, 0)

        worker = CsvImportWorker(self._db._db_path, import_kw)
        self._import_worker = worker

        def on_progress(cur: int, total: int):
            dlg.setRange(0, max(total, 1))
            dlg.setValue(min(cur, dlg.maximum()))
            dlg.setLabelText(f"Importing rows… {cur} / {total}")

        def on_done(result: dict):
            dlg.reset()
            dlg.accept()
            self._import_worker = None
            worker.deleteLater()
            self._refresh_batches(self._current_account_id)
            extra = ""
            if result.get("cancelled"):
                extra = "\n\nImport was cancelled; some rows may have been saved."
            QMessageBox.information(
                self,
                "Import Complete",
                f"Imported {result['inserted']} new transaction(s).\n"
                f"Skipped {result['skipped']} duplicate(s)."
                + extra,
            )

        def on_fail(msg: str):
            dlg.reset()
            dlg.accept()
            self._import_worker = None
            worker.deleteLater()
            QMessageBox.critical(
                self, "Import failed", escape_ampersand_for_qt(msg)
            )

        worker.progress.connect(on_progress)
        worker.finished_ok.connect(on_done)
        worker.failed.connect(on_fail)
        dlg.canceled.connect(worker.request_cancel)
        worker.start()
        dlg.exec()

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
            "Save reconciliation report",
            "",
            "CSV Files (*.csv);;All Files (*)",
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
            QMessageBox.critical(
                self, "Export failed", escape_ampersand_for_qt(str(exc))
            )
            return
        QMessageBox.information(
            self,
            "Export complete",
            f"Reconciliation report saved to:\n{escape_ampersand_for_qt(path)}",
        )

    def _on_reconcile(self):
        if self._current_batch_id is None:
            return
        tol = self._recon_panel.reconciliation_tolerance()
        result = self._db.reconcile_batch(self._current_batch_id, tolerance=tol)
        if result["reconciled"]:
            self._recon_panel.set_reconciled()
            self._refresh_batches(self._current_account_id)
            QMessageBox.information(
                self, "Reconciled",
                "This statement has been marked as reconciled. ✅"
            )
        else:
            QMessageBox.warning(
                self, "Cannot Reconcile",
                f"The difference is ${result['difference']:,.2f}.\n"
                f"Reconciliation is allowed when |difference| is within ±${tol:,.2f}."
            )
