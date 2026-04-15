"""Pay Bills workflow — open A/P bills, allocate payment amounts, post via :func:`probooksai.business.record_ap_payment`.

Optional bank line: when a bank account is chosen, inserts a matching register outflow and links it to the AP payment.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QDate, Qt
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

from desktop_app.flexible_date import configure_qdate_edit_us, format_iso_to_us_display
from desktop_app.qt_combo_ids import coerce_combo_int_id
from desktop_app.qt_mnemonic import (
    message_box_critical_ok,
    message_box_information_ok,
    message_box_warning_ok,
)
from probooksai import business

from desktop_app.theme import (
    WORKFLOW_ALT_ROW as _PAY_STRIPE,
    WORKFLOW_CAPTION as _PAY_CAPTION,
    WORKFLOW_GRID as _PAY_GRID,
    WORKFLOW_HEADER_BG as _PAY_HEADER,
    WORKFLOW_INPUT_BG,
    WORKFLOW_PAGE_BG as _PAY_BG,
    WORKFLOW_PANEL_BG as _PAY_PANEL,
    WORKFLOW_TEXT as _PAY_TEXT,
)

if TYPE_CHECKING:
    from probooksai.bank_import import BankDatabase

_ROLE_BILL_ID = Qt.ItemDataRole.UserRole
_ROLE_VENDOR_ID = Qt.ItemDataRole.UserRole + 1


def _readonly_item(text: str) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    it.setForeground(QColor(_PAY_TEXT))
    return it


def _pay_bills_caption_label(text: str) -> QLabel:
    lb = QLabel(text)
    lb.setStyleSheet(
        f"color: {_PAY_CAPTION}; font-size: 11px; font-weight: 600; "
        "letter-spacing: 0.03em; background: transparent;"
    )
    return lb


def _parse_iso_date(s: str) -> Optional[date]:
    raw = (s or "").strip()[:10]
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


class PayBillsScreen(QWidget):
    """Open bills from the company file; pay against selected rows and post AP + optional bank register line."""

    _COLS = (
        "",  # checkbox
        "Vendor",
        "Bill Date",
        "Due Date",
        "Bill #",
        "Open Balance",
        "Amount to Pay",
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
        self._cached_bills: list = []
        self._row_checks: list[QCheckBox] = []
        self._payment_edits: list[QDoubleSpinBox] = []
        self.setToolTip(
            "Pay Bills: open vendor bills from your company file; enter amounts to pay and post. "
            "Same company .db (File → Backup / Restore, probooks.backup)."
        )
        self._build_ui()
        self._load_bank_accounts_combo()
        self._load_bills_from_db()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        page = QFrame()
        page.setObjectName("payBillsLightPanel")
        page.setStyleSheet(
            f"QFrame#payBillsLightPanel {{ background-color: {_PAY_BG}; border: 1px solid {_PAY_GRID}; "
            "border-radius: 8px; }}"
        )
        play = QVBoxLayout(page)
        play.setContentsMargins(16, 16, 16, 16)
        play.setSpacing(12)

        title_row = QHBoxLayout()
        title = QLabel("Pay Bills")
        title.setStyleSheet(
            f"font-size: 20px; font-weight: 600; color: {_PAY_TEXT}; background: transparent;"
        )
        title_row.addWidget(title)
        title_row.addStretch(1)
        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.setToolTip("Reload open bills from the company database.")
        self._btn_refresh.clicked.connect(self._load_bills_from_db)
        self._btn_pay = QPushButton("Pay Selected Bills")
        self._btn_pay.setToolTip(
            "Post AP payments for checked rows with amounts; optional bank outflow when an account is selected."
        )
        self._btn_pay.clicked.connect(self._on_pay_selected)
        self._btn_clear_top = QPushButton("Clear Selection")
        self._btn_clear_top.setToolTip("Uncheck all rows and clear payment amounts.")
        self._btn_clear_top.clicked.connect(self._on_clear_selection)
        for b in (self._btn_refresh, self._btn_pay, self._btn_clear_top):
            b.setAutoDefault(False)
            b.setDefault(False)
        title_row.addWidget(self._btn_refresh)
        title_row.addWidget(self._btn_pay)
        title_row.addWidget(self._btn_clear_top)
        play.addLayout(title_row)

        sec_filters = _pay_bills_caption_label("Filters & payment")
        sec_filters.setToolTip("Filter the list; set payment date, bank account, and reference for posting.")
        play.addWidget(sec_filters)

        filters_frame = QFrame()
        filters_frame.setObjectName("payBillsFiltersBand")
        filters_frame.setStyleSheet(
            f"QFrame#payBillsFiltersBand {{ background-color: {_PAY_PANEL}; "
            f"border: 1px solid {_PAY_GRID}; border-radius: 8px; }}"
        )
        ctrl = QGridLayout(filters_frame)
        ctrl.setContentsMargins(14, 12, 14, 12)
        ctrl.setHorizontalSpacing(16)
        ctrl.setVerticalSpacing(10)

        _combo_ss = (
            f"QComboBox {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_PAY_GRID}; "
            f"padding: 4px 8px; color: {_PAY_TEXT}; }}"
        )
        _line_ss = (
            f"QLineEdit {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_PAY_GRID}; "
            f"padding: 4px 8px; color: {_PAY_TEXT}; }}"
        )
        _date_ss = (
            f"QDateEdit {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_PAY_GRID}; "
            f"padding: 2px 6px; color: {_PAY_TEXT}; }}"
        )

        self._filter = QComboBox()
        self._filter.addItems(["All", "Open", "Overdue"])
        self._filter.setToolTip(
            "All: every open bill. Open: not past due. Overdue: due date before today."
        )
        self._filter.setStyleSheet(_combo_ss)
        self._filter.currentIndexChanged.connect(self._rebuild_table)

        self._vendor_filter = QLineEdit()
        self._vendor_filter.setPlaceholderText("Vendor filter…")
        self._vendor_filter.setMinimumWidth(180)
        self._vendor_filter.setToolTip("Show rows whose vendor name contains this text.")
        self._vendor_filter.setStyleSheet(_line_ss)
        self._vendor_filter.textChanged.connect(self._rebuild_table)

        self._pay_date = QDateEdit()
        configure_qdate_edit_us(self._pay_date)
        self._pay_date.setDate(QDate.currentDate())
        self._pay_date.setToolTip("Date recorded on the AP payment (and bank line, if any).")
        self._pay_date.setStyleSheet(_date_ss)

        self._account = QComboBox()
        self._account.setMinimumWidth(220)
        self._account.setToolTip(
            "Bank account for the cash-out line on the register (optional). "
            "Choose “(None)” to record AP only."
        )
        self._account.setStyleSheet(_combo_ss)

        self._reference = QLineEdit()
        self._reference.setPlaceholderText("Check # / reference")
        self._reference.setToolTip("Stored on the AP payment and copied to the bank line reference when posted.")
        self._reference.setStyleSheet(_line_ss)

        ctrl.addWidget(_pay_bills_caption_label("Filter"), 0, 0)
        ctrl.addWidget(self._filter, 0, 1)
        ctrl.addWidget(_pay_bills_caption_label("Vendor"), 0, 2)
        ctrl.addWidget(self._vendor_filter, 0, 3)
        ctrl.addWidget(_pay_bills_caption_label("Payment date"), 0, 4)
        ctrl.addWidget(self._pay_date, 0, 5)
        ctrl.addWidget(_pay_bills_caption_label("Pay from bank"), 0, 6)
        ctrl.addWidget(self._account, 0, 7)
        ctrl.addWidget(_pay_bills_caption_label("Reference"), 1, 0)
        ctrl.addWidget(self._reference, 1, 1, 1, 7)
        for c in range(8):
            ctrl.setColumnStretch(c, 0)
        ctrl.setColumnStretch(7, 1)
        play.addWidget(filters_frame)

        sec_table = _pay_bills_caption_label("Bills to pay")
        sec_table.setToolTip("Check rows, enter amounts (not more than open balance), then Pay Selected Bills.")
        play.addWidget(sec_table)

        self._table = QTableWidget(0, len(self._COLS))
        self._table.setObjectName("payBillsTable")
        self._table.setHorizontalHeaderLabels(self._COLS)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for col in (0, 2, 3, 4, 5, 6):
            self._table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )

        self._table.setStyleSheet(
            f"QTableWidget#payBillsTable {{"
            f" background-color: {_PAY_PANEL};"
            f" alternate-background-color: {_PAY_STRIPE};"
            f" color: {_PAY_TEXT};"
            f" gridline-color: {_PAY_GRID};"
            f" border: 1px solid {_PAY_GRID};"
            " }"
            f"QHeaderView::section {{"
            f" background-color: {_PAY_HEADER};"
            f" color: {_PAY_TEXT};"
            f" padding: 6px; border: 1px solid {_PAY_GRID};"
            " font-weight: 600;"
            " }}"
        )

        play.addWidget(self._table, 1)

        sec_sum = _pay_bills_caption_label("Totals")
        sec_sum.setToolTip("Count of checked rows and sum of payment amounts.")
        play.addWidget(sec_sum)

        sum_frame = QFrame()
        sum_frame.setObjectName("payBillsSummaryBand")
        sum_frame.setStyleSheet(
            f"QFrame#payBillsSummaryBand {{ background-color: {_PAY_PANEL}; "
            f"border: 1px solid {_PAY_GRID}; border-radius: 8px; }}"
        )
        sum_lay = QHBoxLayout(sum_frame)
        sum_lay.setContentsMargins(14, 12, 14, 12)
        self._lbl_selected = QLabel("Total selected: 0")
        self._lbl_payment_sum = QLabel("Total payment amount: $0.00")
        for lb in (self._lbl_selected, self._lbl_payment_sum):
            lb.setStyleSheet(f"color: {_PAY_TEXT}; font-size: 13px;")
        sum_lay.addWidget(self._lbl_selected)
        sum_lay.addSpacing(32)
        sum_lay.addWidget(self._lbl_payment_sum)
        sum_lay.addStretch(1)
        play.addWidget(sum_frame)

        actions_frame = QFrame()
        actions_frame.setObjectName("payBillsActionsBar")
        actions_frame.setStyleSheet(
            f"QFrame#payBillsActionsBar {{ background-color: {_PAY_PANEL}; "
            f"border: 1px solid {_PAY_GRID}; border-radius: 6px; }}"
        )
        bot = QHBoxLayout(actions_frame)
        bot.setContentsMargins(12, 10, 12, 10)
        bot.addStretch(1)
        self._btn_pay_bot = QPushButton("Pay Selected Bills")
        self._btn_pay_bot.clicked.connect(self._on_pay_selected)
        self._btn_clear_bot = QPushButton("Clear Selection")
        self._btn_clear_bot.clicked.connect(self._on_clear_selection)
        for b in (self._btn_pay_bot, self._btn_clear_bot):
            b.setAutoDefault(False)
            b.setDefault(False)
        bot.addWidget(self._btn_pay_bot)
        bot.addWidget(self._btn_clear_bot)
        play.addWidget(actions_frame)

        outer.addWidget(page, 1)
        self._refresh_summary()

    def _load_bank_accounts_combo(self) -> None:
        self._account.blockSignals(True)
        self._account.clear()
        self._account.addItem("(None)", None)
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
                self._account.addItem(name, bid)
        self._account.blockSignals(False)

    def _bill_passes_filter(self, row: sqlite3.Row) -> bool:
        d = dict(row)
        vf = self._vendor_filter.text().strip().lower()
        vname = (d.get("vendor_name") or "").strip().lower()
        if vf and vf not in vname:
            return False
        mode = self._filter.currentText()
        due_s = (d.get("due_date") or "").strip()
        due_dt = _parse_iso_date(due_s)
        today = date.today()
        overdue = due_dt is not None and due_dt < today
        if mode == "Overdue":
            return overdue
        if mode == "Open":
            return not overdue
        return True

    def _load_bills_from_db(self) -> None:
        self._cached_bills = []
        if self._ap_conn is None:
            self._rebuild_table()
            return
        try:
            self._cached_bills = list(business.list_open_bills_for_pay_bills(self._ap_conn))
        except sqlite3.Error:
            self._cached_bills = []
        self._rebuild_table()

    def _rebuild_table(self) -> None:
        self._row_checks.clear()
        self._payment_edits.clear()
        self._table.setRowCount(0)
        if self._ap_conn is None:
            self._refresh_summary()
            return
        visible = [r for r in self._cached_bills if self._bill_passes_filter(r)]
        self._table.setRowCount(len(visible))
        for i, r in enumerate(visible):
            d = dict(r)
            bid = int(d["bill_id"])
            vid = int(d["vendor_id"])
            bal = float(d["balance_due"] or 0.0)

            cb = QCheckBox()
            cb.setStyleSheet("background: transparent; margin-left: 8px;")
            self._table.setCellWidget(i, 0, cb)
            self._row_checks.append(cb)

            v_it = _readonly_item((d.get("vendor_name") or "").strip() or "—")
            v_it.setData(_ROLE_BILL_ID, bid)
            v_it.setData(_ROLE_VENDOR_ID, vid)
            self._table.setItem(i, 1, v_it)

            bd = (d.get("bill_date") or "").strip()
            self._table.setItem(i, 2, _readonly_item(format_iso_to_us_display(bd) if bd else "—"))

            dd = (d.get("due_date") or "").strip()
            self._table.setItem(i, 3, _readonly_item(format_iso_to_us_display(dd) if dd else "—"))

            self._table.setItem(
                i, 4, _readonly_item((d.get("vendor_invoice_number") or "").strip() or "—")
            )
            self._table.setItem(i, 5, _readonly_item(f"{bal:,.2f}"))

            pay_spin = QDoubleSpinBox()
            pay_spin.setRange(0.0, max(0.0, bal))
            pay_spin.setDecimals(2)
            pay_spin.setPrefix("$ ")
            pay_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
            pay_spin.setStyleSheet(
                f"QDoubleSpinBox {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_PAY_GRID}; "
                f"padding: 2px 6px; color: {_PAY_TEXT}; }}"
            )
            pay_spin.setToolTip("Amount to apply to this bill on this payment.")
            self._table.setCellWidget(i, 6, pay_spin)
            self._payment_edits.append(pay_spin)

            cb.stateChanged.connect(lambda *_: self._refresh_summary())
            pay_spin.valueChanged.connect(lambda *_: self._refresh_summary())

        self._refresh_summary()

    def _refresh_summary(self) -> None:
        n = 0
        total = 0.0
        for cb, sp in zip(self._row_checks, self._payment_edits):
            if cb.isChecked():
                n += 1
                total += sp.value()
        self._lbl_selected.setText(f"Bills with payment: {n}")
        self._lbl_payment_sum.setText(f"Total payment amount: ${total:,.2f}")

    def _on_clear_selection(self) -> None:
        for c in self._row_checks:
            c.setChecked(False)
        for s in self._payment_edits:
            s.setValue(0.0)
        self._refresh_summary()

    def _on_pay_selected(self) -> None:
        if self._ap_conn is None:
            message_box_information_ok(
                self,
                "Pay Bills",
                "Open a company database to pay bills.",
                ok_tip="Close; use File → Open company… then try again.",
            )
            return
        payment_date = self._pay_date.date().toString("yyyy-MM-dd")
        ref = self._reference.text().strip()
        bidx = self._account.currentIndex()
        bank_account_id: Optional[int] = None
        if bidx > 0:
            bank_account_id = coerce_combo_int_id(self._account.itemData(bidx))

        by_vendor: dict[int, list[tuple[int, float]]] = defaultdict(list)
        for row, (cb, sp) in enumerate(zip(self._row_checks, self._payment_edits)):
            if not cb.isChecked():
                continue
            amt = round(sp.value(), 2)
            if amt <= 0.005:
                continue
            it = self._table.item(row, 1)
            if it is None:
                continue
            bid = coerce_combo_int_id(it.data(_ROLE_BILL_ID))
            vid = coerce_combo_int_id(it.data(_ROLE_VENDOR_ID))
            if bid is None or vid is None:
                continue
            by_vendor[vid].append((bid, amt))

        if not by_vendor:
            message_box_warning_ok(
                self,
                "Pay Bills",
                "Select at least one bill and enter an amount to pay.",
                ok_tip="Check a row and set Amount to pay, then try again.",
            )
            return

        conn = self._ap_conn
        for vid, allocs in by_vendor.items():
            for bid, amt in allocs:
                row = conn.execute(
                    "SELECT balance_due FROM bills WHERE id = ?", (bid,)
                ).fetchone()
                if row is None:
                    message_box_warning_ok(
                        self,
                        "Pay Bills",
                        f"Bill #{bid} is no longer in the database. Refresh and try again.",
                        ok_tip="Use Refresh, then re-enter amounts.",
                    )
                    return
                bal = float(row["balance_due"] or 0.0)
                if amt > bal + 0.02:
                    message_box_warning_ok(
                        self,
                        "Pay Bills",
                        f"Payment amount for bill #{bid} exceeds open balance ({bal:,.2f}).",
                        ok_tip="Lower the amount or refresh the list.",
                    )
                    return

        bank_db = self._bank_db
        posted = 0
        bank_errors: list[str] = []

        for vid, allocs in sorted(by_vendor.items()):
            total = round(sum(a for _, a in allocs), 2)
            if total <= 0.005:
                continue
            vrow = conn.execute(
                "SELECT name FROM vendors WHERE id = ?", (vid,)
            ).fetchone()
            vname = (vrow["name"] if vrow else "").strip() or f"Vendor #{vid}"
            try:
                pid = business.record_ap_payment(
                    conn,
                    vid,
                    payment_date,
                    total,
                    allocs,
                    bank_account_id=bank_account_id,
                    method="",
                    reference=ref,
                    memo="",
                )
            except (sqlite3.Error, ValueError, TypeError) as exc:
                message_box_critical_ok(
                    self,
                    "Pay Bills",
                    f"Could not record payment for {vname}: {exc}",
                    ok_tip="Close; check amounts and try again.",
                )
                return
            posted += 1

            if bank_account_id is not None and bank_db is not None:
                try:
                    tid = bank_db.insert_manual_transaction(
                        bank_account_id,
                        payment_date,
                        -total,
                        description=f"AP payment #{pid} — {vname}",
                        ref_number=ref,
                        memo="Pay Bills",
                    )
                    business.link_bank_transaction(conn, tid, "ap_payment", int(pid))
                except (sqlite3.Error, OSError, ValueError, TypeError) as exc:
                    bank_errors.append(f"{vname}: {exc}")

        self._cached_bills = list(business.list_open_bills_for_pay_bills(conn))
        self._rebuild_table()

        if bank_errors:
            message_box_warning_ok(
                self,
                "Pay Bills",
                "AP payment(s) saved, but the bank register line failed for: "
                + "; ".join(bank_errors),
                ok_tip="Add a matching bank transaction manually or fix the error and retry.",
            )
        else:
            message_box_information_ok(
                self,
                "Pay Bills",
                f"Posted {posted} payment(s). Open balances were updated.",
                ok_tip="Close; use Refresh or reopen the tab to reload bills.",
            )
