"""Receive Checks (customer payment) workflow screen — UI only (no database or A/R logic).

Navy-cool form theme matches Invoices, Enter Bills, and Pay Bills (Receive Payments tab).
"""

from __future__ import annotations

import random
import sqlite3
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop_app.ar_customer_actions import (
    export_ar_payment_allocations_csv,
    export_ar_payments_csv,
    open_record_ar_payment_dialog,
)
from desktop_app.flexible_date import configure_qdate_edit_us

_RC_BG = "#e4e9f0"
_RC_PANEL = "#f7f9fc"
_RC_STRIPE = "#e4ebf4"
_RC_GRID = "#9eb0c8"
_RC_HEADER = "#c4d2e4"
_RC_TEXT = "#1a1a2e"
_RC_CAPTION = "#4a5568"


def _readonly_item(text: str) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    it.setForeground(QColor(_RC_TEXT))
    return it


def _receive_caption_label(text: str) -> QLabel:
    lb = QLabel(text)
    lb.setStyleSheet(
        f"color: {_RC_CAPTION}; font-size: 11px; font-weight: 600; "
        "letter-spacing: 0.03em; background: transparent;"
    )
    return lb


def _payment_spin() -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(0.0, 999_999_999.99)
    s.setDecimals(2)
    s.setPrefix("$ ")
    s.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
    s.setStyleSheet(
        f"QDoubleSpinBox {{ background: {_RC_PANEL}; border: 1px solid {_RC_GRID}; "
        f"padding: 2px 6px; color: {_RC_TEXT}; }}"
    )
    return s


class ReceiveChecksScreen(QWidget):
    """Customer payment header, open invoices grid, totals and credits panel (A/R draft)."""

    _COLS = (
        "",  # checkbox
        "Date",
        "Number",
        "Original Amount",
        "Amount Due",
        "Payment",
    )
    _N_ROWS = 15

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        ap_conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        super().__init__(parent)
        self._ap_conn = ap_conn
        self.setToolTip(
            "Receive Checks: record customer payments against open invoices when connected. "
            "Same company .db (File → Backup / Restore, probooks.backup)."
        )
        self._payment_edits: list[QDoubleSpinBox] = []
        self._row_checks: list[QCheckBox] = []
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        ar_row = QHBoxLayout()
        ar_row.setSpacing(8)
        self._btn_record_ar = QPushButton("Record customer payment…")
        self._btn_record_ar.setToolTip(
            "Record a payment and allocate amounts to open invoices (moved from the Customers tab)."
        )
        self._btn_record_ar.clicked.connect(self._on_record_ar_payment)
        self._btn_export_ar_pay = QPushButton("Export AR payments CSV…")
        self._btn_export_ar_pay.setToolTip("Export customer payment records to CSV (UTF-8 BOM for Excel).")
        self._btn_export_ar_pay.clicked.connect(self._on_export_ar_payments)
        self._btn_export_ar_alloc = QPushButton("Export AR payment allocations CSV…")
        self._btn_export_ar_alloc.setToolTip("Export how payments were applied to invoices.")
        self._btn_export_ar_alloc.clicked.connect(self._on_export_ar_allocations)
        for b in (self._btn_record_ar, self._btn_export_ar_pay, self._btn_export_ar_alloc):
            b.setAutoDefault(False)
            b.setDefault(False)
            ar_row.addWidget(b)
        ar_row.addStretch(1)
        outer.addLayout(ar_row)
        self._sync_ar_toolbar()

        page = QFrame()
        page.setObjectName("receiveChecksLightPanel")
        page.setStyleSheet(
            f"QFrame#receiveChecksLightPanel {{ background-color: {_RC_BG}; border: 1px solid {_RC_GRID}; "
            "border-radius: 8px; }}"
        )
        play = QVBoxLayout(page)
        play.setContentsMargins(16, 16, 16, 16)
        play.setSpacing(12)

        title_row = QHBoxLayout()
        title = QLabel("Receive Payments")
        title.setStyleSheet(
            f"font-size: 20px; font-weight: 600; color: {_RC_TEXT}; background: transparent;"
        )
        title_row.addWidget(title)
        title_row.addStretch(1)
        play.addLayout(title_row)

        sec_pay = _receive_caption_label("Payment details")
        sec_pay.setToolTip("Customer, amount, method, date, and deposit account (placeholder).")
        play.addWidget(sec_pay)

        # ── Header form ──
        form_frame = QFrame()
        form_frame.setObjectName("receiveChecksHeaderBand")
        form_frame.setStyleSheet(
            f"QFrame#receiveChecksHeaderBand {{ background-color: {_RC_PANEL}; "
            f"border: 1px solid {_RC_GRID}; border-radius: 8px; }}"
        )
        form_outer = QHBoxLayout(form_frame)
        form_outer.setContentsMargins(14, 12, 14, 12)
        form_outer.setSpacing(24)

        _combo_ss = (
            f"QComboBox {{ background: {_RC_PANEL}; border: 1px solid {_RC_GRID}; "
            f"padding: 4px 8px; color: {_RC_TEXT}; }}"
        )
        _line_ss = (
            f"QLineEdit {{ background: {_RC_PANEL}; border: 1px solid {_RC_GRID}; "
            f"padding: 4px 8px; color: {_RC_TEXT}; }}"
        )
        _date_ss = (
            f"QDateEdit {{ background: {_RC_PANEL}; border: 1px solid {_RC_GRID}; "
            f"padding: 2px 6px; color: {_RC_TEXT}; }}"
        )

        left = QGridLayout()
        left.setHorizontalSpacing(12)
        left.setVerticalSpacing(10)
        left.setColumnStretch(1, 1)

        self._customer = QComboBox()
        self._customer.addItem("")
        for name in (
            "Fabrikam Retail",
            "Adventure Works",
            "Northwind Traders",
            "Contoso Ltd.",
            "Wide World Importers",
        ):
            self._customer.addItem(name)
        self._customer.setMinimumWidth(220)
        self._customer.setStyleSheet(_combo_ss)

        self._payment_amount = _payment_spin()
        self._payment_amount.setToolTip("Total payment amount (UI only).")

        self._pay_method = QComboBox()
        self._pay_method.addItems(("Check", "Cash", "Credit Card", "ACH", "Other"))
        self._pay_method.setStyleSheet(_combo_ss)

        self._cust_balance = QLabel("Customer balance: $2,450.00")
        self._cust_balance.setStyleSheet(f"color: {_RC_CAPTION}; font-size: 12px;")
        self._cust_balance.setToolTip("Display only (placeholder).")

        left.addWidget(_receive_caption_label("Received From"), 0, 0, Qt.AlignmentFlag.AlignRight)
        left.addWidget(self._customer, 0, 1)
        left.addWidget(_receive_caption_label("Payment Amount"), 1, 0, Qt.AlignmentFlag.AlignRight)
        left.addWidget(self._payment_amount, 1, 1)
        left.addWidget(_receive_caption_label("Payment Method"), 2, 0, Qt.AlignmentFlag.AlignRight)
        left.addWidget(self._pay_method, 2, 1)
        left.addWidget(self._cust_balance, 3, 0, 1, 2)

        right = QGridLayout()
        right.setHorizontalSpacing(12)
        right.setVerticalSpacing(10)
        right.setColumnStretch(1, 1)

        self._pay_date = QDateEdit()
        configure_qdate_edit_us(self._pay_date)
        self._pay_date.setStyleSheet(_date_ss)

        self._check_num = QLineEdit()
        self._check_num.setPlaceholderText("Check #")
        self._check_num.setStyleSheet(_line_ss)

        self._deposit_to = QComboBox()
        self._deposit_to.addItems(
            ("Operating — ****1234", "Payroll — ****5678", "Savings — ****9012")
        )
        self._deposit_to.setMinimumWidth(200)
        self._deposit_to.setStyleSheet(_combo_ss)

        right.addWidget(_receive_caption_label("Date"), 0, 0, Qt.AlignmentFlag.AlignRight)
        right.addWidget(self._pay_date, 0, 1)
        right.addWidget(_receive_caption_label("Check #"), 1, 0, Qt.AlignmentFlag.AlignRight)
        right.addWidget(self._check_num, 1, 1)
        right.addWidget(_receive_caption_label("Deposit To"), 2, 0, Qt.AlignmentFlag.AlignRight)
        right.addWidget(self._deposit_to, 2, 1)

        form_outer.addLayout(left, 1)
        form_outer.addLayout(right, 1)
        play.addWidget(form_frame)

        sec_inv = _receive_caption_label("Open invoices")
        sec_inv.setToolTip("Allocate payment across invoice lines (placeholder).")
        play.addWidget(sec_inv)

        # ── Invoices table ──
        self._table = QTableWidget(self._N_ROWS, len(self._COLS))
        self._table.setObjectName("receiveChecksTable")
        self._table.setHorizontalHeaderLabels(self._COLS)
        self._table.verticalHeader().setVisible(True)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for col in (0, 1, 3, 4, 5):
            self._table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )

        self._table.setStyleSheet(
            f"QTableWidget#receiveChecksTable {{"
            f" background-color: {_RC_PANEL};"
            f" alternate-background-color: {_RC_STRIPE};"
            f" color: {_RC_TEXT};"
            f" gridline-color: {_RC_GRID};"
            f" border: 1px solid {_RC_GRID};"
            " }"
            f"QHeaderView::section {{"
            f" background-color: {_RC_HEADER};"
            f" color: {_RC_TEXT};"
            f" padding: 6px; border: 1px solid {_RC_GRID};"
            " font-weight: 600;"
            " }}"
        )

        rng = random.Random(17)
        for row in range(self._N_ROWS):
            cb = QCheckBox()
            cb.setStyleSheet("background: transparent; margin-left: 8px;")
            self._table.setCellWidget(row, 0, cb)
            self._row_checks.append(cb)

            inv_date = f"2025-{1 + (row % 11):02d}-{(row % 27) + 1:02d}"
            inv_no = f"INV-{1200 + row}"
            orig = 200.0 + rng.randint(0, 4000) + rng.random()
            due = orig * (0.2 + 0.7 * rng.random())
            orig_s = f"{orig:,.2f}"
            due_s = f"{due:,.2f}"

            self._table.setItem(row, 1, _readonly_item(inv_date))
            self._table.setItem(row, 2, _readonly_item(inv_no))
            self._table.setItem(row, 3, _readonly_item(orig_s))
            self._table.setItem(row, 4, _readonly_item(due_s))

            pay_spin = _payment_spin()
            pay_spin.setValue(0.0)
            pay_spin.setToolTip("Payment to apply to this invoice (UI only).")
            self._table.setCellWidget(row, 5, pay_spin)
            self._payment_edits.append(pay_spin)

            cb.stateChanged.connect(lambda *_: self._refresh_totals())
            pay_spin.valueChanged.connect(lambda *_: self._refresh_totals())

        play.addWidget(self._table, 1)

        sec_sum = _receive_caption_label("Summary")
        sec_sum.setToolTip("Totals for the current selection and credit placeholders.")
        play.addWidget(sec_sum)

        # ── Bottom: totals + credits panel ──
        bot = QHBoxLayout()
        bot.setSpacing(16)

        tot_frame = QFrame()
        tot_frame.setObjectName("receiveChecksTotalsBand")
        tot_frame.setStyleSheet(
            f"QFrame#receiveChecksTotalsBand {{ background-color: {_RC_PANEL}; "
            f"border: 1px solid {_RC_GRID}; border-radius: 8px; }}"
        )
        tot_col = QVBoxLayout(tot_frame)
        tot_col.setContentsMargins(14, 12, 14, 12)
        tot_col.setSpacing(8)
        self._lbl_total_selected = QLabel("Total selected: 0")
        self._lbl_total_payment = QLabel("Total payment applied: $0.00")
        for lb in (self._lbl_total_selected, self._lbl_total_payment):
            lb.setStyleSheet(f"color: {_RC_TEXT}; font-size: 13px;")
        tot_col.addWidget(self._lbl_total_selected)
        tot_col.addWidget(self._lbl_total_payment)
        tot_col.addStretch(1)
        bot.addWidget(tot_frame, 0)

        bot.addStretch(1)

        credits = QFrame()
        credits.setObjectName("receiveChecksCreditsBand")
        credits.setStyleSheet(
            f"QFrame#receiveChecksCreditsBand {{ background-color: {_RC_PANEL}; "
            f"border: 1px solid {_RC_GRID}; border-radius: 8px; }}"
        )
        cr = QVBoxLayout(credits)
        cr.setContentsMargins(14, 12, 14, 12)
        cr.setSpacing(8)

        cr.addWidget(_receive_caption_label("Unused credits"))
        self._lbl_unused_credits = QLabel("$125.00")
        self._lbl_unused_credits.setStyleSheet(
            f"color: {_RC_TEXT}; font-size: 14px; font-weight: 600;"
        )
        self._lbl_unused_credits.setToolTip("Placeholder — not wired to A/R credits yet.")
        cr.addWidget(self._lbl_unused_credits)

        self._btn_apply_credits = QPushButton("Apply Credits")
        self._btn_apply_credits.setToolTip("Placeholder — no credit application yet.")
        self._btn_apply_credits.clicked.connect(self._on_apply_credits_placeholder)
        self._btn_apply_credits.setAutoDefault(False)
        self._btn_apply_credits.setDefault(False)
        cr.addWidget(self._btn_apply_credits)

        cr.addSpacing(4)
        cr.addWidget(_receive_caption_label("Amount for selected invoices"))
        self._lbl_amount_selected = QLabel("$0.00")
        self._lbl_amount_selected.setStyleSheet(f"color: {_RC_TEXT}; font-size: 13px;")
        cr.addWidget(self._lbl_amount_selected)

        self._lbl_discount_credits = QLabel("Discount and Credits applied: $0.00")
        self._lbl_discount_credits.setStyleSheet(f"color: {_RC_CAPTION}; font-size: 12px;")
        self._lbl_discount_credits.setToolTip("Placeholder totals.")
        cr.addWidget(self._lbl_discount_credits)

        bot.addWidget(credits, 0)
        play.addLayout(bot)

        outer.addWidget(page, 1)
        self._refresh_totals()

    def _sync_ar_toolbar(self) -> None:
        on = self._ap_conn is not None
        self._btn_record_ar.setEnabled(on)
        self._btn_export_ar_pay.setEnabled(on)
        self._btn_export_ar_alloc.setEnabled(on)

    def _on_record_ar_payment(self) -> None:
        if self._ap_conn is None:
            return
        open_record_ar_payment_dialog(self, self._ap_conn, after_save=None)

    def _on_export_ar_payments(self) -> None:
        if self._ap_conn is None:
            return
        export_ar_payments_csv(self, self._ap_conn)

    def _on_export_ar_allocations(self) -> None:
        if self._ap_conn is None:
            return
        export_ar_payment_allocations_csv(self, self._ap_conn)

    def _selected_payment_sum(self) -> tuple[int, float]:
        n = 0
        total = 0.0
        for cb, sp in zip(self._row_checks, self._payment_edits):
            if cb.isChecked():
                n += 1
                total += sp.value()
        return n, total

    def _refresh_totals(self) -> None:
        n, total = self._selected_payment_sum()
        self._lbl_total_selected.setText(f"Total selected: {n}")
        self._lbl_total_payment.setText(f"Total payment applied: ${total:,.2f}")
        self._lbl_amount_selected.setText(f"${total:,.2f}")

    def _on_apply_credits_placeholder(self) -> None:
        print("[Receive Checks] Apply Credits (placeholder)")
