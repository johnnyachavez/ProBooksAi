"""
desktop_app.register_tab
=========================
PySide6 widget that renders the Bank Account Register tab.

Layout
------
  ┌─────────────────────────────────────────────────────────────────┐
  │  Account: [──────────────────────────────────▼]  [+ New Acct]  │
  │  From: [__________]  To: [__________]  Search: [____________]  │
  ├─────────────────────────────────────────────────────────────────┤
  │  Date | # | Payee/Description | Memo | Debit | Credit | COA    │
  │  ─────┼───┼───────────────────┼──────┼───────┼────────┼──────  │
  │  …rows…                                                         │
  ├─────────────────────────────────────────────────────────────────┤
  │  Totals:  Debits: $X,XXX.XX   Credits: $X,XXX.XX  Net: $X,XXX  │
  └─────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from probooksai.bank_register import BankRegisterDatabase
from probooksai.coa import coa_display_list, load_coa


# ---------------------------------------------------------------------------
# Column indices
# ---------------------------------------------------------------------------

COL_DATE   = 0
COL_NUM    = 1
COL_PAYEE  = 2
COL_MEMO   = 3
COL_DEBIT  = 4
COL_CREDIT = 5
COL_COA    = 6
COL_COUNT  = 7

HEADERS = ["Date", "#", "Payee / Description", "Memo", "Debit", "Credit", "COA Account"]

EDITABLE_COLS = {COL_NUM, COL_MEMO, COL_PAYEE, COL_COA}


# ---------------------------------------------------------------------------
# New Account dialog
# ---------------------------------------------------------------------------

class NewAccountDialog(QDialog):
    """Simple dialog to create a new bank account."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Bank Account")
        self.setMinimumWidth(340)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._name   = QLineEdit()
        self._number = QLineEdit()
        self._inst   = QLineEdit()

        form.addRow("Account Name *:", self._name)
        form.addRow("Account Number:", self._number)
        form.addRow("Institution:",    self._inst)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate(self):
        if not self._name.text().strip():
            QMessageBox.warning(self, "Required", "Account Name is required.")
            return
        self.accept()

    @property
    def account_name(self) -> str:
        return self._name.text().strip()

    @property
    def account_number(self) -> str:
        return self._number.text().strip()

    @property
    def institution(self) -> str:
        return self._inst.text().strip()


# ---------------------------------------------------------------------------
# Register table
# ---------------------------------------------------------------------------

class RegisterTable(QTableWidget):
    """
    Displays bank transactions in a register-style grid.

    Inline editing is supported for columns: #, Payee/Description, Memo,
    COA Account.  Changes are persisted via ``cellChanged`` → ``rowEdited``
    signal.
    """

    rowEdited = Signal(int, int, str)  # (txn_id, column_index, new_value)

    def __init__(self, coa_list: list[str], parent=None):
        super().__init__(parent)
        self._coa_list = coa_list
        self._loading  = False   # suppress cellChanged during population
        self._row_ids: list[int] = []

        self.setColumnCount(COL_COUNT)
        self.setHorizontalHeaderLabels(HEADERS)

        hh = self.horizontalHeader()
        hh.setSectionResizeMode(COL_DATE,   QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(COL_NUM,    QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(COL_PAYEE,  QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(COL_MEMO,   QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(COL_DEBIT,  QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(COL_CREDIT, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(COL_COA,    QHeaderView.ResizeMode.Stretch)

        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.setSortingEnabled(False)

        self.cellChanged.connect(self._on_cell_changed)

    # -- public ---------------------------------------------------------------

    def populate(self, rows: list) -> None:
        """Load transaction rows into the table."""
        self._loading = True
        self.setRowCount(0)
        self._row_ids = []

        for txn in rows:
            r = self.rowCount()
            self.insertRow(r)
            self._row_ids.append(txn["id"])

            amount = float(txn["amount"] or 0)
            debit  = abs(amount) if amount < 0 else 0.0
            credit = amount      if amount > 0 else 0.0

            items = {
                COL_DATE:   _ro_item(txn["date"] or ""),
                COL_NUM:    _edit_item(txn["reference_number"] or ""),
                COL_PAYEE:  _edit_item(txn["description"] or ""),
                COL_MEMO:   _edit_item(txn["memo"] or ""),
                COL_DEBIT:  _ro_item(f"{debit:,.2f}" if debit else ""),
                COL_CREDIT: _ro_item(f"{credit:,.2f}" if credit else ""),
                COL_COA:    _edit_item(txn["coa_account"] or ""),
            }

            # Colour rows: debits light red, credits light green
            row_color: Optional[QColor] = None
            if amount < 0:
                row_color = QColor(255, 235, 235)
            elif amount > 0:
                row_color = QColor(235, 255, 235)

            for col, item in items.items():
                if row_color and not item.background().color().isValid():
                    item.setBackground(row_color)
                self.setItem(r, col, item)

        self._loading = False

    def txn_id_for_row(self, row: int) -> Optional[int]:
        if 0 <= row < len(self._row_ids):
            return self._row_ids[row]
        return None

    # -- slots ----------------------------------------------------------------

    def _on_cell_changed(self, row: int, col: int):
        if self._loading or col not in EDITABLE_COLS:
            return
        txn_id = self.txn_id_for_row(row)
        if txn_id is None:
            return
        item = self.item(row, col)
        self.rowEdited.emit(txn_id, col, item.text() if item else "")


# ---------------------------------------------------------------------------
# Register tab
# ---------------------------------------------------------------------------

class RegisterTab(QWidget):
    """Top-level widget for the Bank Account Register tab."""

    def __init__(self, db: BankRegisterDatabase, parent=None):
        super().__init__(parent)
        self._db  = db
        self._coa = coa_display_list(load_coa())

        self._build_ui()
        self._refresh_accounts()

    # -- UI construction ------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # ── Account selector row ─────────────────────────────────────────────
        acct_row = QHBoxLayout()

        acct_row.addWidget(QLabel("Bank Account:"))
        self._acct_combo = QComboBox()
        self._acct_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._acct_combo.currentIndexChanged.connect(self._on_account_changed)
        acct_row.addWidget(self._acct_combo, 1)

        btn_new_acct = QPushButton("+ New Account")
        btn_new_acct.clicked.connect(self._on_new_account)
        acct_row.addWidget(btn_new_acct)

        root.addLayout(acct_row)

        # ── Filter row ───────────────────────────────────────────────────────
        filter_row = QHBoxLayout()

        filter_row.addWidget(QLabel("From:"))
        self._start_date = QLineEdit()
        self._start_date.setPlaceholderText("YYYY-MM-DD")
        self._start_date.setFixedWidth(100)
        filter_row.addWidget(self._start_date)

        filter_row.addWidget(QLabel("To:"))
        self._end_date = QLineEdit()
        self._end_date.setPlaceholderText("YYYY-MM-DD")
        self._end_date.setFixedWidth(100)
        filter_row.addWidget(self._end_date)

        filter_row.addWidget(QLabel("Search:"))
        self._search = QLineEdit()
        self._search.setPlaceholderText("description or memo…")
        self._search.setFixedWidth(200)
        filter_row.addWidget(self._search)

        btn_apply = QPushButton("Apply")
        btn_apply.clicked.connect(self._refresh_register)
        filter_row.addWidget(btn_apply)

        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self._clear_filters)
        filter_row.addWidget(btn_clear)

        filter_row.addStretch()
        root.addLayout(filter_row)

        # ── Register table ───────────────────────────────────────────────────
        self._table = RegisterTable(self._coa)
        self._table.rowEdited.connect(self._on_row_edited)
        root.addWidget(self._table, 1)

        # ── Footer / totals ──────────────────────────────────────────────────
        footer = QHBoxLayout()
        self._lbl_debits  = QLabel("Total Debits: —")
        self._lbl_credits = QLabel("Total Credits: —")
        self._lbl_net     = QLabel("Net: —")

        for lbl in (self._lbl_debits, self._lbl_credits, self._lbl_net):
            lbl.setStyleSheet("font-weight: bold; padding: 4px 12px;")
            footer.addWidget(lbl)

        footer.addStretch()

        # Empty-state label (shown when no account selected)
        self._empty_label = QLabel(
            "Select a bank account above to view transactions.\n"
            "Use '+ New Account' to create a new bank account."
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #888; font-size: 14px;")

        root.addWidget(self._empty_label)
        root.addLayout(footer)

        self._update_empty_state()

    # -- account management ---------------------------------------------------

    def _refresh_accounts(self):
        """Reload the account dropdown from the database."""
        self._acct_combo.blockSignals(True)
        prev_id = self._current_account_id()
        self._acct_combo.clear()
        self._acct_combo.addItem("— select account —", userData=None)

        for acct in self._db.list_accounts():
            label = acct["name"]
            if acct["account_number"]:
                label += f"  ({acct['account_number']})"
            self._acct_combo.addItem(label, userData=acct["id"])

        # Restore previous selection if still present
        if prev_id is not None:
            for i in range(self._acct_combo.count()):
                if self._acct_combo.itemData(i) == prev_id:
                    self._acct_combo.setCurrentIndex(i)
                    break

        self._acct_combo.blockSignals(False)
        self._refresh_register()

    def _current_account_id(self) -> Optional[int]:
        return self._acct_combo.currentData()

    def _on_account_changed(self, _index: int):
        self._refresh_register()

    def _on_new_account(self):
        dlg = NewAccountDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._db.add_account(
            name=dlg.account_name,
            account_number=dlg.account_number,
            institution=dlg.institution,
        )
        self._refresh_accounts()

    # -- register data --------------------------------------------------------

    def _refresh_register(self):
        """Reload transactions from DB and repopulate the table."""
        account_id = self._current_account_id()
        self._update_empty_state(account_id)

        start  = self._start_date.text().strip() or None
        end    = self._end_date.text().strip()   or None
        search = self._search.text().strip()      or None

        rows = self._db.list_transactions(
            bank_account_id=account_id,
            start_date=start,
            end_date=end,
            search=search,
        )
        self._table.populate(rows)
        self._update_totals(rows)

    def _update_totals(self, rows: list):
        total_debit  = 0.0
        total_credit = 0.0
        for row in rows:
            amount = float(row["amount"] or 0)
            if amount < 0:
                total_debit += abs(amount)
            else:
                total_credit += amount

        net = total_credit - total_debit
        self._lbl_debits.setText(f"Total Debits: ${total_debit:,.2f}")
        self._lbl_credits.setText(f"Total Credits: ${total_credit:,.2f}")
        sign = "+" if net >= 0 else ""
        self._lbl_net.setText(f"Net: {sign}${net:,.2f}")

    def _update_empty_state(self, account_id: Optional[int] = None):
        has_account = account_id is not None
        self._table.setVisible(has_account)
        self._empty_label.setVisible(not has_account)

    def _clear_filters(self):
        self._start_date.clear()
        self._end_date.clear()
        self._search.clear()
        self._refresh_register()

    # -- inline editing -------------------------------------------------------

    def _on_row_edited(self, txn_id: int, col: int, value: str):
        """Persist an inline edit to the database."""
        kwargs: dict = {}
        if col == COL_NUM:
            kwargs["reference_number"] = value
        elif col == COL_MEMO:
            kwargs["memo"] = value
        elif col == COL_COA:
            kwargs["coa_account"] = value
        elif col == COL_PAYEE:
            kwargs["description"] = value
        else:
            return
        self._db.update_transaction(txn_id, **kwargs)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ro_item(text: str) -> QTableWidgetItem:
    """Create a read-only table cell."""
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


def _edit_item(text: str) -> QTableWidgetItem:
    """Create an editable table cell."""
    return QTableWidgetItem(text)
