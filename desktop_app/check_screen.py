"""Write Checks screen — create, browse, and edit bank payments in a check-style UI.

Each check maps to one ``bank_transactions`` row.  Saving here writes through
``BankDatabase.update_transaction`` / ``insert_manual_transaction``, so the Bank
Register automatically reflects every change when it next refreshes.

Navigation browses ALL transactions for the selected bank account (deposits AND
payments) so the screen doubles as a full-register viewer with a check-form UI.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from functools import partial
from typing import Optional

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop_app.flexible_date import configure_qdate_edit_us, format_iso_to_us_display
from desktop_app.qt_combo_ids import coerce_combo_int_id, combo_index_for_int_user_data
from desktop_app.qt_mnemonic import (
    escape_ampersand_for_qt,
    message_box_information_ok,
    message_box_question_yes_no,
    message_box_warning_ok,
)
from desktop_app.table_clipboard import plain_display_table_item
from desktop_app.theme import (
    WORKFLOW_ALT_ROW,
    WORKFLOW_CAPTION,
    WORKFLOW_GRID,
    WORKFLOW_HEADER_BG,
    WORKFLOW_INPUT_BG,
    WORKFLOW_PAGE_BG,
    WORKFLOW_PANEL_BG,
    WORKFLOW_TEXT,
)

# ── Amount → words ────────────────────────────────────────────────────────────
_ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _int_to_words(n: int) -> str:
    if n == 0:
        return "Zero"
    if n < 0:
        return "Negative " + _int_to_words(-n)
    parts = []
    if n >= 1_000_000:
        parts.append(_int_to_words(n // 1_000_000) + " Million")
        n %= 1_000_000
    if n >= 1_000:
        parts.append(_int_to_words(n // 1_000) + " Thousand")
        n %= 1_000
    if n >= 100:
        parts.append(_ONES[n // 100] + " Hundred")
        n %= 100
    if n >= 20:
        word = _TENS[n // 10]
        if n % 10:
            word += "-" + _ONES[n % 10]
        parts.append(word)
    elif n > 0:
        parts.append(_ONES[n])
    return " ".join(parts)


def _amount_to_words(amount: float) -> str:
    """Convert *amount* to written-check English, e.g. 1234.56 → 'One Thousand Two Hundred Thirty-Four and 56/100'."""
    amount = abs(round(amount, 2))
    dollars = int(amount)
    cents = round((amount - dollars) * 100)
    words = _int_to_words(dollars) if dollars else "Zero"
    return f"{words} and {cents:02d}/100"


# ── Check paper widget ────────────────────────────────────────────────────────

_CHECK_BG = "#1B3A2A"        # dark green tint — evokes paper checks
_CHECK_BORDER = "#2E6B45"
_CHECK_LINE = "#3A7A52"
_CHECK_LABEL = "#8FC9A5"
_CHECK_INPUT_BG = "#0F2018"


class CheckScreen(QWidget):
    """A QuickBooks-style Write Checks / transaction viewer for one bank account."""

    #: Emitted after any save or delete so the Bank Register can refresh.
    transactionSaved = Signal()

    def __init__(self, bank_db, coa_list: list | None = None, parent=None):
        """
        *bank_db* — ``BankDatabase`` instance.
        *coa_list* — list of COA display strings for the expense account dropdown.
        """
        super().__init__(parent)
        self._db = bank_db
        self._coa_list: list[str] = coa_list or []
        self._current_account_id: Optional[int] = None
        self._browse_ids: list[int] = []      # txn ids for current account
        self._browse_index: Optional[int] = None  # index into _browse_ids; None = blank draft
        self._loading = False
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.setStyleSheet(
            f"CheckScreen {{ background-color: {WORKFLOW_PAGE_BG}; }}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top toolbar ───────────────────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setStyleSheet(f"background-color: {WORKFLOW_HEADER_BG};")
        tb_lay = QHBoxLayout(toolbar)
        tb_lay.setContentsMargins(8, 6, 8, 6)
        tb_lay.setSpacing(6)

        self._btn_prev = QPushButton("◄  Prev")
        self._btn_prev.setToolTip("Go to the previous transaction for this bank account.")
        self._btn_prev.clicked.connect(self._on_prev)
        tb_lay.addWidget(self._btn_prev)

        self._btn_next = QPushButton("Next  ►")
        self._btn_next.setToolTip("Go to the next transaction, or start a new blank check.")
        self._btn_next.clicked.connect(self._on_next)
        tb_lay.addWidget(self._btn_next)

        tb_lay.addSpacing(12)

        self._btn_new = QPushButton("✚  New")
        self._btn_new.setToolTip("Start a new blank check / payment entry.")
        self._btn_new.clicked.connect(self._on_new)
        tb_lay.addWidget(self._btn_new)

        self._btn_save = QPushButton("💾  Save")
        self._btn_save.setToolTip("Save this check / transaction to the Bank Register.")
        self._btn_save.clicked.connect(self._on_save)
        tb_lay.addWidget(self._btn_save)

        self._btn_delete = QPushButton("🗑  Delete")
        self._btn_delete.setToolTip("Delete this transaction from the register.")
        self._btn_delete.clicked.connect(self._on_delete)
        tb_lay.addWidget(self._btn_delete)

        tb_lay.addSpacing(20)

        lbl_acct = QLabel("Bank Account:")
        lbl_acct.setStyleSheet(f"color: {WORKFLOW_CAPTION};")
        tb_lay.addWidget(lbl_acct)

        self._acct_combo = QComboBox()
        self._acct_combo.setMinimumWidth(220)
        self._acct_combo.setToolTip("Bank account to write checks against.")
        self._acct_combo.currentIndexChanged.connect(self._on_account_changed)
        tb_lay.addWidget(self._acct_combo)

        tb_lay.addSpacing(16)
        lbl_bal = QLabel("Ending Balance:")
        lbl_bal.setStyleSheet(f"color: {WORKFLOW_CAPTION};")
        tb_lay.addWidget(lbl_bal)
        self._lbl_balance = QLabel("—")
        self._lbl_balance.setStyleSheet(f"color: {WORKFLOW_TEXT}; font-weight: bold;")
        tb_lay.addWidget(self._lbl_balance)

        tb_lay.addStretch()

        self._lbl_position = QLabel("")
        self._lbl_position.setStyleSheet(f"color: {WORKFLOW_CAPTION};")
        tb_lay.addWidget(self._lbl_position)

        root.addWidget(toolbar)

        # ── Main content (splitter: check paper + expense list) ───────────────
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setStyleSheet(f"background-color: {WORKFLOW_PAGE_BG};")

        # Check paper area
        check_frame = self._build_check_paper()
        splitter.addWidget(check_frame)

        # Expense / splits table
        expense_area = self._build_expense_area()
        splitter.addWidget(expense_area)

        splitter.setSizes([320, 220])
        root.addWidget(splitter, 1)

        self._refresh_accounts()

    def _build_check_paper(self) -> QFrame:
        """Build the green check-paper UI."""
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background-color: {_CHECK_BG}; border: 2px solid {_CHECK_BORDER}; "
            f"border-radius: 6px; margin: 8px; }}"
        )
        frame.setMinimumHeight(240)

        g = QGridLayout(frame)
        g.setContentsMargins(16, 12, 16, 12)
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(8)

        def _lbl(text: str) -> QLabel:
            w = QLabel(text)
            w.setStyleSheet(
                f"color: {_CHECK_LABEL}; font-size: 10px; font-weight: bold; "
                f"background: transparent; border: none;"
            )
            return w

        def _field(min_width: int = 120, read_only: bool = False) -> QLineEdit:
            w = QLineEdit()
            w.setMinimumWidth(min_width)
            w.setStyleSheet(
                f"QLineEdit {{ background-color: {_CHECK_INPUT_BG}; color: {WORKFLOW_TEXT}; "
                f"border: 1px solid {_CHECK_LINE}; border-radius: 3px; padding: 2px 5px; }}"
            )
            if read_only:
                w.setReadOnly(True)
                w.setStyleSheet(
                    f"QLineEdit {{ background-color: transparent; color: {_CHECK_LABEL}; "
                    f"border: none; border-bottom: 1px solid {_CHECK_LINE}; padding: 2px 0; }}"
                )
            return w

        # Row 0: PAY TO THE ORDER OF + $ amount + NO. + DATE
        g.addWidget(_lbl("PAY TO THE ORDER OF"), 0, 0)
        self._fld_payee = _field(300)
        self._fld_payee.setToolTip("Payee / vendor name stored as the transaction description.")
        g.addWidget(self._fld_payee, 0, 1, 1, 3)

        g.addWidget(_lbl("$"), 0, 4, Qt.AlignmentFlag.AlignRight)
        self._spin_amount = QDoubleSpinBox()
        self._spin_amount.setRange(0, 99_999_999.99)
        self._spin_amount.setDecimals(2)
        self._spin_amount.setMinimumWidth(110)
        self._spin_amount.setPrefix("$ ")
        self._spin_amount.setToolTip(
            "Check amount. Stored as negative (payment) in the register; "
            "deposits are created as positive via the New Deposit button."
        )
        self._spin_amount.setStyleSheet(
            f"QDoubleSpinBox {{ background-color: {_CHECK_INPUT_BG}; color: {WORKFLOW_TEXT}; "
            f"border: 1px solid {_CHECK_LINE}; border-radius: 3px; padding: 2px 5px; }}"
        )
        self._spin_amount.valueChanged.connect(self._on_amount_changed)
        g.addWidget(self._spin_amount, 0, 5)

        g.addWidget(_lbl("NO."), 0, 6, Qt.AlignmentFlag.AlignRight)
        self._fld_number = _field(80)
        self._fld_number.setToolTip("Check number / reference (stored as ref_number).")
        g.addWidget(self._fld_number, 0, 7)

        g.addWidget(_lbl("DATE"), 0, 8, Qt.AlignmentFlag.AlignRight)
        self._date_edit = QDateEdit()
        configure_qdate_edit_us(self._date_edit)
        self._date_edit.setToolTip("Transaction date.")
        self._date_edit.setStyleSheet(
            f"QDateEdit {{ background-color: {_CHECK_INPUT_BG}; color: {WORKFLOW_TEXT}; "
            f"border: 1px solid {_CHECK_LINE}; border-radius: 3px; padding: 2px 5px; }}"
        )
        g.addWidget(self._date_edit, 0, 9)

        # Row 1: DOLLARS (written amount)
        g.addWidget(_lbl("DOLLARS"), 1, 0)
        self._fld_dollars = _field(500, read_only=True)
        self._fld_dollars.setToolTip("Amount in words — updates automatically.")
        g.addWidget(self._fld_dollars, 1, 1, 1, 9)

        # Row 2: TYPE selector + MEMO
        g.addWidget(_lbl("TYPE"), 2, 0)
        self._type_combo = QComboBox()
        self._type_combo.addItem("💳  Payment / Check", "payment")
        self._type_combo.addItem("⬆  Deposit / Credit", "deposit")
        self._type_combo.setToolTip(
            "Payment = money leaving (stored negative). "
            "Deposit = money arriving (stored positive)."
        )
        self._type_combo.setStyleSheet(
            f"QComboBox {{ background-color: {_CHECK_INPUT_BG}; color: {WORKFLOW_TEXT}; "
            f"border: 1px solid {_CHECK_LINE}; border-radius: 3px; padding: 2px 5px; }}"
        )
        g.addWidget(self._type_combo, 2, 1)

        g.addWidget(_lbl("MEMO"), 2, 2)
        self._fld_memo = _field(400)
        self._fld_memo.setToolTip("Internal memo for this transaction.")
        g.addWidget(self._fld_memo, 2, 3, 1, 7)

        g.setColumnStretch(3, 1)
        return frame

    def _build_expense_area(self) -> QWidget:
        """Build the Expenses / account-coding table below the check."""
        w = QWidget()
        w.setStyleSheet(f"background-color: {WORKFLOW_PANEL_BG};")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(4)

        hdr_lay = QHBoxLayout()
        lbl_exp = QLabel("Expense Account Coding")
        lbl_exp.setStyleSheet(
            f"color: {WORKFLOW_CAPTION}; font-weight: bold; font-size: 11px;"
        )
        hdr_lay.addWidget(lbl_exp)
        hdr_lay.addStretch()
        lay.addLayout(hdr_lay)

        self._exp_table = QTableWidget(8, 3)
        self._exp_table.setHorizontalHeaderLabels(["Account (COA)", "Amount", "Memo"])
        self._exp_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._exp_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self._exp_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._exp_table.setColumnWidth(1, 110)
        self._exp_table.verticalHeader().setVisible(False)
        self._exp_table.setAlternatingRowColors(True)
        self._exp_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._exp_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self._exp_table.setStyleSheet(
            f"QTableWidget {{ background-color: {WORKFLOW_PAGE_BG}; "
            f"color: {WORKFLOW_TEXT}; gridline-color: {WORKFLOW_GRID}; "
            f"alternate-background-color: {WORKFLOW_ALT_ROW}; }}"
            f"QHeaderView::section {{ background-color: {WORKFLOW_HEADER_BG}; "
            f"color: {WORKFLOW_CAPTION}; border: 1px solid {WORKFLOW_GRID}; padding: 3px; }}"
        )
        self._exp_table.setToolTip(
            "Account coding: enter one or more COA accounts with amounts. "
            "The first non-empty row is saved as the transaction's primary COA category."
        )
        self._populate_expense_rows()
        self._exp_table.cellChanged.connect(self._on_exp_cell_changed)
        lay.addWidget(self._exp_table)
        return w

    def _populate_expense_rows(self) -> None:
        """Fill expense table with COA combo boxes in the Account column."""
        self._exp_table.blockSignals(True)
        for r in range(self._exp_table.rowCount()):
            # Account column — QComboBox
            coa_combo = QComboBox()
            coa_combo.addItem("(select account)", "")
            for c in self._coa_list:
                coa_combo.addItem(escape_ampersand_for_qt(c), c)
            coa_combo.setEditable(True)
            coa_combo.setToolTip("Chart-of-accounts category for this expense line.")
            self._exp_table.setCellWidget(r, 0, coa_combo)

            # Amount column
            amt_item = QTableWidgetItem("")
            amt_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._exp_table.setItem(r, 1, amt_item)

            # Memo column
            self._exp_table.setItem(r, 2, QTableWidgetItem(""))
        self._exp_table.blockSignals(False)

    # ── Account combo ─────────────────────────────────────────────────────────

    def _refresh_accounts(self) -> None:
        self._acct_combo.blockSignals(True)
        prev_id = self._current_account_id
        self._acct_combo.clear()
        accounts = self._db.list_bank_accounts()
        self._accounts = accounts
        if not accounts:
            self._acct_combo.addItem("(no accounts)", None)
        else:
            for acct in accounts:
                aid = coerce_combo_int_id(acct["id"])
                if aid is None:
                    continue
                label = f"{acct['name']} – {acct['bank_name'] or 'Bank'}"
                self._acct_combo.addItem(escape_ampersand_for_qt(label), aid)
        self._acct_combo.blockSignals(False)

        if prev_id is not None:
            ix = combo_index_for_int_user_data(self._acct_combo, prev_id)
            self._acct_combo.setCurrentIndex(ix if ix is not None else 0)
        else:
            self._acct_combo.setCurrentIndex(0)
        self._on_account_changed()

    def _on_account_changed(self) -> None:
        aid = coerce_combo_int_id(self._acct_combo.currentData())
        self._current_account_id = aid
        self._browse_ids = []
        self._browse_index = None
        if aid is not None:
            self._reload_browse_list()
        self._update_balance_label()
        self._load_current()

    def _reload_browse_list(self) -> None:
        if self._current_account_id is None:
            self._browse_ids = []
            return
        txns = self._db.list_transactions(self._current_account_id)
        self._browse_ids = [int(t["id"]) for t in txns]

    # ── Navigation ────────────────────────────────────────────────────────────

    def _on_prev(self) -> None:
        if not self._browse_ids:
            return
        if self._browse_index is None:
            # Was on blank draft → go to last saved
            self._browse_index = len(self._browse_ids) - 1
        elif self._browse_index > 0:
            self._browse_index -= 1
        self._load_current()

    def _on_next(self) -> None:
        if not self._browse_ids:
            # No saved transactions → blank draft
            self._browse_index = None
            self._load_current()
            return
        if self._browse_index is None:
            # Already on blank
            return
        if self._browse_index < len(self._browse_ids) - 1:
            self._browse_index += 1
        else:
            # Past last → blank new
            self._browse_index = None
        self._load_current()

    def _on_new(self) -> None:
        self._browse_index = None
        self._load_current()

    def _update_nav_buttons(self) -> None:
        n = len(self._browse_ids)
        has_any = n > 0
        is_draft = self._browse_index is None
        self._btn_prev.setEnabled(has_any and not (is_draft is False and self._browse_index == 0)
                                  and not (is_draft and not has_any))
        can_prev = has_any and (is_draft or self._browse_index > 0)
        can_next = has_any  # can always go forward if there's anything saved
        self._btn_prev.setEnabled(can_prev)
        self._btn_next.setEnabled(can_next)
        self._btn_delete.setEnabled(not is_draft)

        if is_draft:
            self._lbl_position.setText("New")
        else:
            idx = self._browse_index
            self._lbl_position.setText(f"{idx + 1} / {n}")

    # ── Load / save ───────────────────────────────────────────────────────────

    def _load_current(self) -> None:
        self._loading = True
        try:
            if self._browse_index is None or not self._browse_ids:
                self._load_blank()
            else:
                tid = self._browse_ids[self._browse_index]
                txn = self._db.get_transaction(tid)
                if txn is None:
                    self._load_blank()
                else:
                    self._load_txn(dict(txn))
        finally:
            self._loading = False
        self._update_nav_buttons()

    def _load_blank(self) -> None:
        today = date.today()
        self._date_edit.setDate(QDate(today.year, today.month, today.day))
        self._fld_payee.clear()
        self._fld_number.clear()
        self._fld_memo.clear()
        self._spin_amount.setValue(0.0)
        self._fld_dollars.setText("")
        self._type_combo.setCurrentIndex(0)  # Payment
        self._clear_expense_rows()

    def _load_txn(self, d: dict) -> None:
        # Date
        raw_date = (d.get("txn_date") or "").strip()
        if raw_date:
            parts = raw_date.split("-")
            if len(parts) == 3:
                try:
                    self._date_edit.setDate(QDate(int(parts[0]), int(parts[1]), int(parts[2])))
                except Exception:
                    pass

        # Payee
        self._fld_payee.setText(d.get("description") or "")

        # Number
        self._fld_number.setText(d.get("ref_number") or "")

        # Memo
        self._fld_memo.setText(d.get("memo") or "")

        # Amount + type
        amt = float(d.get("amount") or 0)
        self._spin_amount.setValue(abs(amt))
        self._fld_dollars.setText(_amount_to_words(abs(amt)))
        if amt >= 0:
            self._type_combo.setCurrentIndex(1)  # Deposit
        else:
            self._type_combo.setCurrentIndex(0)  # Payment

        # Expense row — populate first line with saved COA
        coa = (d.get("coa_account") or "").strip()
        self._clear_expense_rows()
        if coa:
            coa_combo = self._exp_table.cellWidget(0, 0)
            if coa_combo:
                ix = coa_combo.findData(coa)
                if ix >= 0:
                    coa_combo.setCurrentIndex(ix)
                else:
                    coa_combo.setCurrentText(escape_ampersand_for_qt(coa))
            amt_item = self._exp_table.item(0, 1)
            if amt_item:
                amt_item.setText(f"{abs(amt):.2f}")

    def _clear_expense_rows(self) -> None:
        self._exp_table.blockSignals(True)
        for r in range(self._exp_table.rowCount()):
            coa_combo = self._exp_table.cellWidget(r, 0)
            if coa_combo:
                coa_combo.setCurrentIndex(0)
            amt_item = self._exp_table.item(r, 1)
            if amt_item:
                amt_item.setText("")
            memo_item = self._exp_table.item(r, 2)
            if memo_item:
                memo_item.setText("")
        self._exp_table.blockSignals(False)

    def _on_amount_changed(self, val: float) -> None:
        if not self._loading:
            self._fld_dollars.setText(_amount_to_words(val) if val else "")

    def _on_exp_cell_changed(self, row: int, col: int) -> None:
        pass  # future: auto-fill amount from check total for split lines

    def _collect_form(self) -> dict:
        """Return form values as a dict ready for insert/update."""
        qd = self._date_edit.date()
        txn_date = f"{qd.year():04d}-{qd.month():02d}-{qd.day():02d}"
        payee = self._fld_payee.text().strip()
        ref = self._fld_number.text().strip()
        memo = self._fld_memo.text().strip()
        raw_amt = self._spin_amount.value()
        is_payment = self._type_combo.currentData() == "payment"
        amount = -raw_amt if is_payment else raw_amt

        # COA from first non-empty expense row
        coa = ""
        for r in range(self._exp_table.rowCount()):
            combo = self._exp_table.cellWidget(r, 0)
            if combo:
                val = combo.currentData() or combo.currentText().strip()
                if val and val != "(select account)":
                    coa = val
                    break

        return dict(
            txn_date=txn_date,
            description=payee,
            ref_number=ref,
            memo=memo,
            amount=amount,
            coa_account=coa,
        )

    def _on_save(self) -> None:
        if self._current_account_id is None:
            message_box_warning_ok(
                self, "No account", "Select a bank account first.",
                ok_tip="Close; choose a bank account from the combo at the top."
            )
            return
        data = self._collect_form()
        is_draft = self._browse_index is None

        try:
            if is_draft:
                # Create new
                new_id = self._db.insert_manual_transaction(
                    self._current_account_id,
                    data["txn_date"],
                    data["amount"],
                    description=data["description"],
                    ref_number=data["ref_number"],
                    memo=data["memo"],
                    coa_account=data["coa_account"],
                )
                self._reload_browse_list()
                try:
                    self._browse_index = self._browse_ids.index(new_id)
                except ValueError:
                    self._browse_index = len(self._browse_ids) - 1
            else:
                tid = self._browse_ids[self._browse_index]
                self._db.update_transaction(
                    tid,
                    description=data["description"],
                    txn_date=data["txn_date"],
                    amount=data["amount"],
                    memo=data["memo"],
                    ref_number=data["ref_number"],
                    coa_account=data["coa_account"],
                )
        except ValueError as exc:
            message_box_warning_ok(
                self, "Cannot save",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; fix the value and try again."
            )
            return

        self._update_balance_label()
        self._update_nav_buttons()
        self.transactionSaved.emit()

    def _on_delete(self) -> None:
        if self._browse_index is None or not self._browse_ids:
            return
        tid = self._browse_ids[self._browse_index]
        txn = self._db.get_transaction(tid)
        if txn is None:
            return
        d = dict(txn)
        amt = float(d.get("amount") or 0)
        label = "payment" if amt < 0 else "deposit"
        desc = (d.get("description") or "").strip() or f"#{tid}"
        date_s = (d.get("txn_date") or "").strip()
        ans = message_box_question_yes_no(
            self,
            f"Delete {label}?",
            f"Permanently delete this {label}?\n\n"
            f"  Date: {date_s}\n"
            f"  Payee: {escape_ampersand_for_qt(desc)}\n"
            f"  Amount: ${abs(amt):,.2f}\n\n"
            "This cannot be undone.",
            yes_tip=f"Delete this {label} permanently.",
            no_tip="Cancel.",
        )
        if not ans:
            return
        try:
            self._db.delete_transaction(tid)
        except ValueError as exc:
            message_box_warning_ok(
                self, "Cannot delete",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; void the GL posting first if posted."
            )
            return
        # Move to adjacent transaction
        prev_idx = self._browse_index
        self._reload_browse_list()
        if self._browse_ids:
            self._browse_index = min(prev_idx, len(self._browse_ids) - 1)
        else:
            self._browse_index = None
        self._load_current()
        self._update_balance_label()
        self.transactionSaved.emit()

    # ── Balance label ─────────────────────────────────────────────────────────

    def _update_balance_label(self) -> None:
        if self._current_account_id is None:
            self._lbl_balance.setText("—")
            return
        try:
            txns = self._db.list_transactions(self._current_account_id)
            bal = sum(float(t["amount"] or 0) for t in txns)
            self._lbl_balance.setText(f"${bal:,.2f}")
            self._lbl_balance.setStyleSheet(
                f"color: {'#E06C75' if bal < 0 else '#98C379'}; font-weight: bold;"
            )
        except Exception:
            self._lbl_balance.setText("—")

    # ── Public API ────────────────────────────────────────────────────────────

    def reload(self) -> None:
        """Called by main window after external changes (e.g. CSV import)."""
        self._reload_browse_list()
        self._update_balance_label()
        self._update_nav_buttons()

    def refresh_accounts(self) -> None:
        """Rebuild the bank account combo (e.g. after Manage Accounts)."""
        self._refresh_accounts()

    def refresh_coa(self, coa_list: list[str]) -> None:
        """Update the COA dropdown options in all expense rows."""
        self._coa_list = coa_list
        self._populate_expense_rows()

    def navigate_to_transaction(self, txn_id: int) -> None:
        """Jump directly to *txn_id* — called from the Bank Register 'Open in Checks' context menu."""
        self._reload_browse_list()
        if txn_id in self._browse_ids:
            self._browse_index = self._browse_ids.index(txn_id)
            self._load_current()
