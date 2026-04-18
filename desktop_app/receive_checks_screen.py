"""Receive Payments workflow — open A/R invoices from the company file; post via :func:`probooksai.business.record_ar_payment`.

Optional bank line: when a bank account is chosen, inserts a matching register deposit and links it to each AR payment.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QColor, QTextDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFileDialog,
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

from desktop_app.flexible_date import configure_qdate_edit_us, format_iso_to_us_display
from desktop_app.qt_combo_ids import coerce_combo_int_id
from desktop_app.qt_mnemonic import (
    message_box_critical_ok,
    message_box_information_ok,
    message_box_warning_ok,
)
from probooksai import business

from desktop_app.ar_customer_actions import (
    export_ar_payment_allocations_csv,
    export_ar_payments_csv,
    open_record_ar_payment_dialog,
)
from desktop_app.invoice_preferences import configure_printer_for_payment_print
from desktop_app.payment_receipt_pdf import ar_payment_html_string, save_ar_payment_pdf
from desktop_app.theme import (
    WORKFLOW_ALT_ROW as _RC_STRIPE,
    WORKFLOW_CAPTION as _RC_CAPTION,
    WORKFLOW_GRID as _RC_GRID,
    WORKFLOW_HEADER_BG as _RC_HEADER,
    WORKFLOW_INPUT_BG,
    WORKFLOW_PAGE_BG as _RC_BG,
    WORKFLOW_PANEL_BG as _RC_PANEL,
    WORKFLOW_TEXT as _RC_TEXT,
)

if TYPE_CHECKING:
    from probooksai.bank_import import BankDatabase

_ROLE_INVOICE_ID = Qt.ItemDataRole.UserRole
_ROLE_CUSTOMER_ID = Qt.ItemDataRole.UserRole + 1


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
        f"QDoubleSpinBox {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_RC_GRID}; "
        f"padding: 2px 6px; color: {_RC_TEXT}; }}"
    )
    return s


class ReceiveChecksScreen(QWidget):
    """Customer payment header, open invoices from the company DB, post AR + optional bank deposit.

    Signals
    -------
    arPaymentPosted(list[int])
        Emitted after :meth:`_on_post_payment` successfully records one or more AR payments.
        Carries the **invoice ids** (``invoice_lines.invoice_id``) that received an allocation in
        the just-posted batch, so other screens (notably **Manual Invoice**) can refresh PAID
        badge / balance state for an invoice they currently have open without polling.
    """

    arPaymentPosted = Signal(list)

    _COLS = (
        "",  # checkbox
        "Customer",
        "Invoice Date",
        "Due Date",
        "Invoice #",
        "Open Balance",
        "Amount to Apply",
    )

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        ap_conn: Optional[sqlite3.Connection] = None,
        bank_db: Optional["BankDatabase"] = None,
    ) -> None:
        super().__init__(parent)
        self._ap_conn = ap_conn
        self._bank_db = bank_db
        self._cached_invoices: list = []
        self._row_checks: list[QCheckBox] = []
        self._payment_edits: list[QDoubleSpinBox] = []
        self._last_ar_payment_ids: list[int] = []
        self.setToolTip(
            "Receive Payments: record customer payments against open invoices from your company file. "
            "Same company .db (File → Backup / Restore, probooks.backup)."
        )
        self._build_ui()
        self._load_bank_accounts_combo()
        self._load_invoices_from_db()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        ar_row = QHBoxLayout()
        ar_row.setSpacing(8)
        self._btn_record_ar = QPushButton("Record customer payment…")
        self._btn_record_ar.setToolTip(
            "Open the AR payment dialog (alternative to posting from the grid below)."
        )
        self._btn_record_ar.clicked.connect(self._on_record_ar_payment)
        self._btn_export_ar_pay = QPushButton("Export AR payments CSV…")
        self._btn_export_ar_pay.setToolTip("Export customer payment records to CSV (UTF-8 BOM for Excel).")
        self._btn_export_ar_pay.clicked.connect(self._on_export_ar_payments)
        self._btn_export_ar_alloc = QPushButton("Export AR payment allocations CSV…")
        self._btn_export_ar_alloc.setToolTip("Export how payments were applied to invoices.")
        self._btn_export_ar_alloc.clicked.connect(self._on_export_ar_allocations)
        self._btn_export_ar_pdf = QPushButton("Export last payment PDF…")
        self._btn_export_ar_pdf.setToolTip(
            "Save the most recently posted customer payment from this session as a PDF (pick path)."
        )
        self._btn_export_ar_pdf.clicked.connect(self._on_export_last_ar_payment_pdf)
        self._btn_print_ar = QPushButton("Print last payment…")
        self._btn_print_ar.setToolTip("Print the most recently posted payment (same layout as PDF).")
        self._btn_print_ar.clicked.connect(self._on_print_last_ar_payment)
        for b in (
            self._btn_record_ar,
            self._btn_export_ar_pay,
            self._btn_export_ar_alloc,
            self._btn_export_ar_pdf,
            self._btn_print_ar,
        ):
            b.setAutoDefault(False)
            b.setDefault(False)
        self._btn_export_ar_pdf.setEnabled(False)
        self._btn_print_ar.setEnabled(False)
        ar_row.addWidget(self._btn_record_ar)
        ar_row.addWidget(self._btn_export_ar_pay)
        ar_row.addWidget(self._btn_export_ar_alloc)
        ar_row.addWidget(self._btn_export_ar_pdf)
        ar_row.addWidget(self._btn_print_ar)
        ar_row.addStretch(1)
        outer.addLayout(ar_row)

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
        self._btn_post = QPushButton("Post payment")
        self._btn_post.setToolTip(
            "Record AR payment(s) for checked rows with amounts; optional bank deposit when an account is selected."
        )
        self._btn_post.clicked.connect(self._on_post_payment)
        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.setToolTip("Reload open invoices from the company database.")
        self._btn_refresh.clicked.connect(self._load_invoices_from_db)
        for b in (self._btn_post, self._btn_refresh):
            b.setAutoDefault(False)
            b.setDefault(False)
        title_row.addWidget(self._btn_post)
        title_row.addWidget(self._btn_refresh)
        play.addLayout(title_row)

        sec_pay = _receive_caption_label("Payment details")
        sec_pay.setToolTip(
            "Payment date, deposit account, method, and reference for posting. "
            "When Deposit to selects a bank, posting adds a deposit on the Bank Register for that account "
            "and invoice balances update (Paid when fully applied)."
        )
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
            f"QComboBox {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_RC_GRID}; "
            f"padding: 4px 8px; color: {_RC_TEXT}; }}"
        )
        _line_ss = (
            f"QLineEdit {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_RC_GRID}; "
            f"padding: 4px 8px; color: {_RC_TEXT}; }}"
        )
        _date_ss = (
            f"QDateEdit {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_RC_GRID}; "
            f"padding: 2px 6px; color: {_RC_TEXT}; }}"
        )

        left = QGridLayout()
        left.setHorizontalSpacing(12)
        left.setVerticalSpacing(10)
        left.setColumnStretch(1, 1)

        self._customer_filter = QComboBox()
        self._customer_filter.setMinimumWidth(220)
        self._customer_filter.setStyleSheet(_combo_ss)
        self._customer_filter.setToolTip(
            "Limit the invoice list to one customer, or show all open invoices. "
            "For a parent (mother ship) customer, includes invoices for all jobs under that account."
        )
        self._customer_filter.currentIndexChanged.connect(self._rebuild_table)

        self._pay_method = QComboBox()
        self._pay_method.addItems(("Check", "Cash", "Credit Card", "ACH", "Other"))
        self._pay_method.setStyleSheet(_combo_ss)

        self._cust_balance = QLabel("Customer open balance: —")
        self._cust_balance.setStyleSheet(f"color: {_RC_CAPTION}; font-size: 12px;")
        self._cust_balance.setToolTip("Sum of open balance for the invoices shown in the table (after filter).")

        left.addWidget(_receive_caption_label("Show customer"), 0, 0, Qt.AlignmentFlag.AlignRight)
        left.addWidget(self._customer_filter, 0, 1)
        left.addWidget(_receive_caption_label("Payment Method"), 1, 0, Qt.AlignmentFlag.AlignRight)
        left.addWidget(self._pay_method, 1, 1)
        left.addWidget(self._cust_balance, 2, 0, 1, 2)

        right = QGridLayout()
        right.setHorizontalSpacing(12)
        right.setVerticalSpacing(10)
        right.setColumnStretch(1, 1)

        self._pay_date = QDateEdit()
        configure_qdate_edit_us(self._pay_date)
        self._pay_date.setDate(QDate.currentDate())
        self._pay_date.setStyleSheet(_date_ss)

        self._check_num = QLineEdit()
        self._check_num.setPlaceholderText("Check # / reference")
        self._check_num.setStyleSheet(_line_ss)

        self._deposit_to = QComboBox()
        self._deposit_to.setMinimumWidth(200)
        self._deposit_to.setStyleSheet(_combo_ss)
        self._deposit_to.setToolTip(
            "Bank account for the deposit line on the register (optional). Choose “(None)” for AR only."
        )

        right.addWidget(_receive_caption_label("Payment date"), 0, 0, Qt.AlignmentFlag.AlignRight)
        right.addWidget(self._pay_date, 0, 1)
        right.addWidget(_receive_caption_label("Reference #"), 1, 0, Qt.AlignmentFlag.AlignRight)
        right.addWidget(self._check_num, 1, 1)
        right.addWidget(_receive_caption_label("Deposit to"), 2, 0, Qt.AlignmentFlag.AlignRight)
        right.addWidget(self._deposit_to, 2, 1)

        form_outer.addLayout(left, 1)
        form_outer.addLayout(right, 1)
        play.addWidget(form_frame)

        sec_inv = _receive_caption_label("Open invoices")
        sec_inv.setToolTip("Check invoices and enter amounts to apply; post records payment and updates balances.")
        play.addWidget(sec_inv)

        # ── Invoices table ──
        self._table = QTableWidget(0, len(self._COLS))
        self._table.setObjectName("receiveChecksTable")
        self._table.setHorizontalHeaderLabels(self._COLS)
        self._table.verticalHeader().setVisible(True)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hh = self._table.horizontalHeader()
        hh.setStretchLastSection(True)
        for col in range(1, len(self._COLS) - 1):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

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

        play.addWidget(self._table, 1)

        sec_sum = _receive_caption_label("Summary")
        sec_sum.setToolTip("Totals for checked rows with apply amounts.")
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
        self._lbl_total_selected = QLabel("Invoices with payment: 0")
        self._lbl_total_payment = QLabel("Total amount to apply: $0.00")
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
        self._lbl_unused_credits = QLabel("—")
        self._lbl_unused_credits.setStyleSheet(
            f"color: {_RC_TEXT}; font-size: 14px; font-weight: 600;"
        )
        self._lbl_unused_credits.setToolTip("Not wired to A/R credits in this release.")
        cr.addWidget(self._lbl_unused_credits)

        self._btn_apply_credits = QPushButton("Apply Credits")
        self._btn_apply_credits.setToolTip("Not implemented yet.")
        self._btn_apply_credits.clicked.connect(self._on_apply_credits_placeholder)
        self._btn_apply_credits.setAutoDefault(False)
        self._btn_apply_credits.setDefault(False)
        self._btn_apply_credits.setEnabled(False)
        cr.addWidget(self._btn_apply_credits)

        cr.addSpacing(4)
        cr.addWidget(_receive_caption_label("Amount for selected invoices"))
        self._lbl_amount_selected = QLabel("$0.00")
        self._lbl_amount_selected.setStyleSheet(f"color: {_RC_TEXT}; font-size: 13px;")
        cr.addWidget(self._lbl_amount_selected)

        self._lbl_discount_credits = QLabel("Discount and credits applied: $0.00")
        self._lbl_discount_credits.setStyleSheet(f"color: {_RC_CAPTION}; font-size: 12px;")
        self._lbl_discount_credits.setToolTip("Placeholder — not wired.")
        cr.addWidget(self._lbl_discount_credits)

        bot.addWidget(credits, 0)
        play.addLayout(bot)

        outer.addWidget(page, 1)
        self._sync_ar_toolbar()
        self._refresh_totals()

    def _load_bank_accounts_combo(self) -> None:
        self._deposit_to.blockSignals(True)
        self._deposit_to.clear()
        self._deposit_to.addItem("(None)", None)
        if self._ap_conn is not None:
            try:
                rows = self._ap_conn.execute(
                    "SELECT id, name FROM bank_accounts WHERE is_active = 1 ORDER BY name"
                ).fetchall()
            except sqlite3.Error:
                rows = []
            for r in rows:
                bid = coerce_combo_int_id(r["id"])
                if bid is None:
                    continue
                name = (r["name"] or "").strip() or f"Account #{bid}"
                self._deposit_to.addItem(name, bid)
        self._deposit_to.blockSignals(False)

    def _populate_customer_filter(self) -> None:
        prev = coerce_combo_int_id(self._customer_filter.currentData())
        self._customer_filter.blockSignals(True)
        self._customer_filter.clear()
        self._customer_filter.addItem("All customers", None)
        if self._ap_conn is not None:
            try:
                for cid, label in business.list_bill_to_customer_choices(self._ap_conn):
                    self._customer_filter.addItem(label, cid)
            except sqlite3.Error:
                pass
        self._customer_filter.blockSignals(False)
        if prev is not None:
            for i in range(self._customer_filter.count()):
                if coerce_combo_int_id(self._customer_filter.itemData(i)) == prev:
                    self._customer_filter.setCurrentIndex(i)
                    break

    def _invoice_passes_filter(self, d: dict) -> bool:
        fcid = coerce_combo_int_id(self._customer_filter.currentData())
        if fcid is None:
            return True
        if self._ap_conn is None:
            return False
        try:
            ids = business.customer_ids_for_receive_payments_filter(self._ap_conn, fcid)
        except (sqlite3.Error, ValueError):
            ids = [fcid]
        return int(d.get("customer_id") or 0) in set(ids)

    def _update_cust_balance_label(self, visible_rows: list[dict]) -> None:
        s = sum(float(r.get("balance_due") or 0.0) for r in visible_rows)
        self._cust_balance.setText(f"Customer open balance (shown): ${s:,.2f}")

    def _load_invoices_from_db(self) -> None:
        self._cached_invoices = []
        self._populate_customer_filter()
        if self._ap_conn is None:
            self._rebuild_table()
            return
        try:
            self._cached_invoices = list(
                business.list_open_invoices_for_receive_payments(self._ap_conn)
            )
        except sqlite3.Error:
            self._cached_invoices = []
        self._rebuild_table()

    def _rebuild_table(self) -> None:
        self._row_checks.clear()
        self._payment_edits.clear()
        self._table.setRowCount(0)
        if self._ap_conn is None:
            self._cust_balance.setText("Customer open balance: —")
            self._refresh_totals()
            return
        id_to_label: dict[int, str] = {}
        if self._ap_conn is not None:
            try:
                id_to_label = dict(business.list_bill_to_customer_choices(self._ap_conn))
            except sqlite3.Error:
                id_to_label = {}

        visible: list[dict] = []
        for r in self._cached_invoices:
            d = dict(r)
            if self._invoice_passes_filter(d):
                visible.append(d)
        self._update_cust_balance_label(visible)
        self._table.setRowCount(len(visible))
        for i, d in enumerate(visible):
            iid = int(d["invoice_id"])
            cid = int(d["customer_id"])
            bal = float(d["balance_due"] or 0.0)

            cb = QCheckBox()
            cb.setStyleSheet("background: transparent; margin-left: 8px;")
            self._table.setCellWidget(i, 0, cb)
            self._row_checks.append(cb)

            disp = (id_to_label.get(cid) or (d.get("customer_name") or "").strip()).strip()
            cust_it = _readonly_item(disp or "—")
            cust_it.setData(_ROLE_CUSTOMER_ID, cid)
            self._table.setItem(i, 1, cust_it)

            inv_dt = (d.get("invoice_date") or "").strip()
            self._table.setItem(
                i,
                2,
                _readonly_item(format_iso_to_us_display(inv_dt) if inv_dt else "—"),
            )
            due_raw = (d.get("due_date") or "").strip()
            self._table.setItem(
                i,
                3,
                _readonly_item(format_iso_to_us_display(due_raw) if due_raw else "—"),
            )

            num_it = _readonly_item((d.get("invoice_number") or "").strip() or "—")
            num_it.setData(_ROLE_INVOICE_ID, iid)
            self._table.setItem(i, 4, num_it)

            self._table.setItem(i, 5, _readonly_item(f"{bal:,.2f}"))

            pay_spin = _payment_spin()
            pay_spin.setRange(0.0, max(0.0, bal))
            pay_spin.setValue(0.0)
            pay_spin.setToolTip("Amount to apply to this invoice on this payment.")
            self._table.setCellWidget(i, 6, pay_spin)
            self._payment_edits.append(pay_spin)

            cb.stateChanged.connect(lambda *_: self._refresh_totals())
            pay_spin.valueChanged.connect(lambda *_: self._refresh_totals())

        self._refresh_totals()

    def _sync_ar_toolbar(self) -> None:
        on = self._ap_conn is not None
        self._btn_record_ar.setEnabled(on)
        self._btn_export_ar_pay.setEnabled(on)
        self._btn_export_ar_alloc.setEnabled(on)
        self._btn_export_ar_pdf.setEnabled(on and bool(self._last_ar_payment_ids))
        self._btn_print_ar.setEnabled(on and bool(self._last_ar_payment_ids))
        self._btn_post.setEnabled(on)
        self._btn_refresh.setEnabled(on)

    def _on_record_ar_payment(self) -> None:
        if self._ap_conn is None:
            return
        open_record_ar_payment_dialog(self, self._ap_conn, after_save=self._load_invoices_from_db)

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
        self._lbl_total_selected.setText(f"Invoices with payment: {n}")
        self._lbl_total_payment.setText(f"Total amount to apply: ${total:,.2f}")
        self._lbl_amount_selected.setText(f"${total:,.2f}")

    def _on_apply_credits_placeholder(self) -> None:
        pass

    def _on_post_payment(self) -> None:
        if self._ap_conn is None:
            message_box_information_ok(
                self,
                "Receive Payments",
                "Open a company database to post payments.",
                ok_tip="Close; use File → Open company… then try again.",
            )
            return
        payment_date = self._pay_date.date().toString("yyyy-MM-dd")
        ref = self._check_num.text().strip()
        method = self._pay_method.currentText().strip()
        bidx = self._deposit_to.currentIndex()
        bank_account_id: Optional[int] = None
        if bidx > 0:
            bank_account_id = coerce_combo_int_id(self._deposit_to.itemData(bidx))

        by_customer: dict[int, list[tuple[int, float]]] = defaultdict(list)
        for row, (cb, sp) in enumerate(zip(self._row_checks, self._payment_edits)):
            if not cb.isChecked():
                continue
            amt = round(sp.value(), 2)
            if amt <= 0.005:
                continue
            num_it = self._table.item(row, 4)
            cust_it = self._table.item(row, 1)
            if num_it is None or cust_it is None:
                continue
            iid = coerce_combo_int_id(num_it.data(_ROLE_INVOICE_ID))
            cid = coerce_combo_int_id(cust_it.data(_ROLE_CUSTOMER_ID))
            if iid is None or cid is None:
                continue
            by_customer[cid].append((iid, amt))

        if not by_customer:
            message_box_warning_ok(
                self,
                "Receive Payments",
                "Select at least one invoice and enter an amount to apply.",
                ok_tip="Check a row and set Amount to apply, then try again.",
            )
            return

        conn = self._ap_conn
        for cid, allocs in by_customer.items():
            for iid, amt in allocs:
                row = conn.execute(
                    "SELECT balance_due FROM invoices WHERE id = ?", (iid,)
                ).fetchone()
                if row is None:
                    message_box_warning_ok(
                        self,
                        "Receive Payments",
                        f"Invoice #{iid} is no longer in the database. Refresh and try again.",
                        ok_tip="Use Refresh, then re-enter amounts.",
                    )
                    return
                bal = float(row["balance_due"] or 0.0)
                if amt > bal + 0.02:
                    message_box_warning_ok(
                        self,
                        "Receive Payments",
                        f"Apply amount for invoice #{iid} exceeds open balance ({bal:,.2f}).",
                        ok_tip="Lower the amount or refresh the list.",
                    )
                    return

        bank_db = self._bank_db
        posted = 0
        bank_errors: list[str] = []
        self._last_ar_payment_ids.clear()

        for cid, allocs in sorted(by_customer.items()):
            total = round(sum(a for _, a in allocs), 2)
            if total <= 0.005:
                continue
            crow = conn.execute(
                "SELECT name FROM customers WHERE id = ?", (cid,)
            ).fetchone()
            cname = (crow["name"] if crow else "").strip() or f"Customer #{cid}"
            try:
                pid = business.record_ar_payment(
                    conn,
                    cid,
                    payment_date,
                    total,
                    allocs,
                    bank_account_id=bank_account_id,
                    method=method,
                    reference=ref,
                    memo="",
                )
                self._last_ar_payment_ids.append(int(pid))
            except (sqlite3.Error, ValueError, TypeError) as exc:
                message_box_critical_ok(
                    self,
                    "Receive Payments",
                    f"Could not record payment for {cname}: {exc}",
                    ok_tip="Close; check amounts and try again.",
                )
                return
            posted += 1

            if bank_account_id is not None and bank_db is not None:
                try:
                    tid = bank_db.insert_manual_transaction(
                        bank_account_id,
                        payment_date,
                        total,
                        description=f"AR payment #{pid} — {cname}",
                        ref_number=ref,
                        memo="Receive Payments",
                    )
                    business.link_bank_transaction(conn, tid, "ar_payment", int(pid))
                except (sqlite3.Error, OSError, ValueError, TypeError) as exc:
                    bank_errors.append(f"{cname}: {exc}")

        self._load_invoices_from_db()
        self._sync_ar_toolbar()

        # Notify peer screens (Manual Invoice) so an open invoice that just got paid
        # refreshes its PAID badge / balance without the user navigating away.
        if posted:
            posted_invoice_ids = sorted({iid for allocs in by_customer.values() for iid, _ in allocs})
            if posted_invoice_ids:
                self.arPaymentPosted.emit(posted_invoice_ids)

        if bank_errors:
            message_box_warning_ok(
                self,
                "Receive Payments",
                "AR payment(s) saved, but the bank register line failed for: "
                + "; ".join(bank_errors),
                ok_tip="Add a matching bank transaction manually or fix the error and retry.",
            )
        else:
            message_box_information_ok(
                self,
                "Receive Payments",
                f"Posted {posted} payment(s). Open balances were updated.",
                ok_tip="Close; use Refresh or revisit the tab to reload invoices.",
            )

    def _on_export_last_ar_payment_pdf(self) -> None:
        if self._ap_conn is None or not self._last_ar_payment_ids:
            return
        pid = self._last_ar_payment_ids[-1]
        default_name = f"AR-Payment-{pid}.pdf"
        path, _filt = QFileDialog.getSaveFileName(
            self,
            "Export AR payment as PDF",
            default_name,
            "PDF files (*.pdf);;All files (*.*)",
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path = f"{path}.pdf"
        try:
            save_ar_payment_pdf(self._ap_conn, pid, path)
        except OSError as exc:
            message_box_warning_ok(
                self,
                "Receive Payments",
                f"Could not write PDF: {exc}",
                ok_tip="Choose a writable folder and try again.",
            )
        except Exception as exc:  # noqa: BLE001
            message_box_warning_ok(
                self,
                "Receive Payments",
                f"PDF export failed: {exc}",
                ok_tip="Close and try again.",
            )

    def _on_print_last_ar_payment(self) -> None:
        if self._ap_conn is None or not self._last_ar_payment_ids:
            return
        pid = self._last_ar_payment_ids[-1]
        doc = QTextDocument()
        try:
            doc.setHtml(ar_payment_html_string(self._ap_conn, pid))
        except Exception as exc:  # noqa: BLE001
            message_box_warning_ok(
                self,
                "Receive Payments",
                f"Could not prepare payment for printing: {exc}",
                ok_tip="Close and try again.",
            )
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        if not configure_printer_for_payment_print(self, printer):
            return
        doc.print_(printer)
