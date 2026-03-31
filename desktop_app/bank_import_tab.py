"""
desktop_app.bank_import_tab
============================
PySide6 widget for bank account setup, CSV import, and statement reconciliation.

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

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
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
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QDate

from probooksai.bank_import import (
    ACCOUNT_TYPES,
    BankDatabase,
    parse_csv,
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

    def __init__(self, db: BankDatabase, parent=None):
        super().__init__(parent)
        self._db = db
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

    def _refresh(self):
        accounts = self._db.list_bank_accounts()
        self._table.setRowCount(len(accounts))
        self._accounts = accounts
        for r, acct in enumerate(accounts):
            self._table.setItem(r, 0, QTableWidgetItem(acct["name"]))
            self._table.setItem(r, 1, QTableWidgetItem(acct["account_number"] or ""))
            self._table.setItem(r, 2, QTableWidgetItem(acct["bank_name"] or ""))
            self._table.setItem(r, 3, QTableWidgetItem(
                _ACCOUNT_TYPE_LABELS.get(acct["account_type"], acct["account_type"])
            ))

    def _selected_account(self):
        row = self._table.currentRow()
        if row < 0 or row >= len(self._accounts):
            return None
        return self._accounts[row]

    def _on_add(self):
        dlg = _AccountEditDialog(db=self._db, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh()
            self.accountsChanged.emit()

    def _on_edit(self):
        acct = self._selected_account()
        if not acct:
            QMessageBox.information(self, "No Selection", "Please select an account to edit.")
            return
        dlg = _AccountEditDialog(db=self._db, account=acct, parent=self)
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
            f"Delete account '{acct['name']}' and all its transactions?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._db.delete_bank_account(acct["id"])
            self._refresh()
            self.accountsChanged.emit()


class _AccountEditDialog(QDialog):
    """Add/edit a single bank account."""

    def __init__(self, db: BankDatabase, account=None, parent=None):
        super().__init__(parent)
        self._db = db
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

    def _on_accept(self):
        name = self._name.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Account Name is required.")
            return
        account_type = self._type.currentData()
        if self._account is None:
            self._db.add_bank_account(
                name=name,
                account_number=self._number.text().strip(),
                bank_name=self._bank.text().strip(),
                account_type=account_type,
            )
        else:
            self._db.update_bank_account(
                account_id=self._account["id"],
                name=name,
                account_number=self._number.text().strip(),
                bank_name=self._bank.text().strip(),
                account_type=account_type,
            )
        self.accept()


# ===========================================================================
# ColumnMappingDialog
# ===========================================================================

class ColumnMappingDialog(QDialog):
    """Maps CSV column headers to the required import fields."""

    def __init__(self, headers: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Map CSV Columns")
        self.setMinimumWidth(380)
        self._headers = headers
        self._build_ui()

    def _build_ui(self):
        layout = QFormLayout(self)

        def _combo(required=True):
            cb = QComboBox()
            if not required:
                cb.addItem("(none)", "")
            cb.addItems(self._headers)
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

    @property
    def date_col(self) -> str:
        return self._date_col.currentText()

    @property
    def amount_col(self) -> str:
        return self._amount_col.currentText()

    @property
    def description_col(self) -> str:
        data = self._desc_col.currentData()
        return "" if data == "" else self._desc_col.currentText()

    @property
    def ref_col(self) -> str:
        data = self._ref_col.currentData()
        return "" if data == "" else self._ref_col.currentText()


# ===========================================================================
# StatementPeriodDialog
# ===========================================================================

class StatementPeriodDialog(QDialog):
    """Capture statement start/end dates and beginning/ending balances."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Statement Period & Balances")
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
            self.setItem(r, 0, QTableWidgetItem(txn["txn_date"]))
            self.setItem(r, 1, QTableWidgetItem(txn["description"] or ""))

            amount = txn["amount"]
            amt_item = QTableWidgetItem(f"{amount:,.2f}")
            amt_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            amt_item.setForeground(_color_for_amount(amount))
            self.setItem(r, 2, amt_item)

            self.setItem(r, 3, QTableWidgetItem(txn["ref_number"] or ""))
        self.setSortingEnabled(True)


# ===========================================================================
# ReconciliationPanel
# ===========================================================================

class ReconciliationPanel(QGroupBox):
    """
    Displays reconciliation summary and the Mark Reconciled button.

    Emits :attr:`reconcileRequested` when the button is clicked.
    """

    reconcileRequested = Signal()

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

        self._btn_reconcile = QPushButton("✔  Mark Reconciled")
        self._btn_reconcile.setEnabled(False)
        self._btn_reconcile.clicked.connect(self.reconcileRequested)
        layout.addRow(self._btn_reconcile)

        self._lbl_status = QLabel("")
        self._lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addRow(self._lbl_status)

    def _reset(self):
        for lbl in (self._lbl_start, self._lbl_end, self._lbl_begin,
                    self._lbl_ending, self._lbl_sum, self._lbl_computed, self._lbl_diff):
            lbl.setText("—")
        self._btn_reconcile.setEnabled(False)
        self._lbl_status.setText("")

    def update_from_batch(self, batch, recon_result: Optional[dict] = None):
        """Populate panel fields from *batch* row and optional *recon_result* dict."""
        self._lbl_start.setText(batch["statement_start"] or "—")
        self._lbl_end.setText(batch["statement_end"] or "—")
        self._lbl_begin.setText(_format_currency(batch["beginning_balance"]))
        self._lbl_ending.setText(_format_currency(batch["ending_balance"]))

        if recon_result:
            self._lbl_sum.setText(_format_currency(recon_result["sum_of_amounts"]))
            self._lbl_computed.setText(_format_currency(recon_result["computed_ending"]))
            diff = recon_result["difference"]
            self._lbl_diff.setText(_format_currency(diff))

            if abs(diff) < 0.005:
                self._lbl_diff.setStyleSheet("color: green; font-weight: bold;")
            else:
                self._lbl_diff.setStyleSheet("color: red; font-weight: bold;")

            if batch["is_reconciled"]:
                self._btn_reconcile.setEnabled(False)
                self._lbl_status.setText("✅  Already reconciled")
                self._lbl_status.setStyleSheet("color: green; font-weight: bold;")
            elif recon_result["can_reconcile"]:
                self._btn_reconcile.setEnabled(True)
                self._lbl_status.setText("Difference is $0.00 – ready to reconcile.")
                self._lbl_status.setStyleSheet("color: green;")
            else:
                self._btn_reconcile.setEnabled(False)
                self._lbl_status.setText(f"Difference must be $0.00 to reconcile.")
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

    def __init__(self, db: BankDatabase, parent=None):
        super().__init__(parent)
        self._db = db
        self._current_batch_id: Optional[int] = None
        self._current_account_id: Optional[int] = None
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
        left_layout.addWidget(self._batch_table)
        splitter.addWidget(left)

        # Right: transactions + reconciliation
        right_splitter = QSplitter(Qt.Orientation.Vertical)

        self._txn_table = TransactionsTable()
        right_splitter.addWidget(self._txn_table)

        self._recon_panel = ReconciliationPanel()
        self._recon_panel.reconcileRequested.connect(self._on_reconcile)
        right_splitter.addWidget(self._recon_panel)

        right_splitter.setSizes([400, 200])
        splitter.addWidget(right_splitter)
        splitter.setSizes([280, 720])

        outer.addWidget(splitter)

    # -----------------------------------------------------------------------
    # Account helpers
    # -----------------------------------------------------------------------

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
                self._acct_combo.addItem(f"{acct['name']} – {acct['bank_name'] or 'Bank'}", acct["id"])
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
        if aid is not None:
            self._refresh_batches(aid)
        else:
            self._batch_table.setRowCount(0)

    # -----------------------------------------------------------------------
    # Batch list
    # -----------------------------------------------------------------------

    def _refresh_batches(self, account_id: int):
        batches = self._db.list_batches(account_id)
        self._batches = batches
        self._batch_table.setRowCount(len(batches))
        for r, b in enumerate(batches):
            imported_at = (b["imported_at"] or "")[:10]
            period = ""
            if b["statement_start"] and b["statement_end"]:
                period = f"{b['statement_start']} → {b['statement_end']}"
            reconciled_text = "✅ Yes" if b["is_reconciled"] else "No"

            self._batch_table.setItem(r, 0, QTableWidgetItem(imported_at))
            self._batch_table.setItem(r, 1, QTableWidgetItem(period))
            item_recon = QTableWidgetItem(reconciled_text)
            if b["is_reconciled"]:
                item_recon.setForeground(QColor("green"))
            self._batch_table.setItem(r, 2, item_recon)

    def _on_batch_selected(self):
        row = self._batch_table.currentRow()
        if not hasattr(self, "_batches") or row < 0 or row >= len(self._batches):
            return
        batch = self._batches[row]
        self._current_batch_id = batch["id"]
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
            )
            self._recon_panel.update_from_batch(batch, recon)
        else:
            self._recon_panel.update_from_batch(batch, None)

    # -----------------------------------------------------------------------
    # Import CSV
    # -----------------------------------------------------------------------

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
            QMessageBox.critical(self, "File Error", f"Could not read file:\n{exc}")
            return

        import csv, io
        reader = csv.reader(io.StringIO(content))
        try:
            headers = next(reader)
        except StopIteration:
            QMessageBox.critical(self, "File Error", "CSV file appears to be empty.")
            return

        # 3. Column mapping
        col_dlg = ColumnMappingDialog(headers, parent=self)
        if col_dlg.exec() != QDialog.DialogCode.Accepted:
            return

        # 4. Statement period & balances
        period_dlg = StatementPeriodDialog(parent=self)
        if period_dlg.exec() != QDialog.DialogCode.Accepted:
            return

        # 5. Import
        result = self._db.import_csv(
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

        QMessageBox.information(
            self,
            "Import Complete",
            f"Imported {result['inserted']} new transaction(s).\n"
            f"Skipped {result['skipped']} duplicate(s).",
        )
        self._refresh_batches(self._current_account_id)

    # -----------------------------------------------------------------------
    # Manage accounts
    # -----------------------------------------------------------------------

    def _on_manage_accounts(self):
        dlg = ManageAccountsDialog(self._db, parent=self)
        dlg.accountsChanged.connect(self._refresh_accounts)
        dlg.exec()
        self._refresh_accounts()

    # -----------------------------------------------------------------------
    # Reconcile
    # -----------------------------------------------------------------------

    def _on_reconcile(self):
        if self._current_batch_id is None:
            return
        result = self._db.reconcile_batch(self._current_batch_id)
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
                "Reconciliation is only allowed when the difference is $0.00."
            )
