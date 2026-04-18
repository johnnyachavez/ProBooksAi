"""Enter Bill workflow screen — vendor-backed header and expense lines persisted to ``bills`` / ``bill_expense_lines``.

Dark navy styling matches :class:`PayBillsScreen` / :class:`InvoiceScreen` workflow theme (Customers / Vendors AR/AP body).

**Print / PDF:** ``Save && Close`` / ``Save && New`` write ``Bill-<ref>.pdf`` to the folder from **Edit → Preferences**
(``bill_prefs/output_folder`` in ``QSettings``, first-time folder picker via :func:`desktop_app.invoice_preferences.ensure_bill_output_folder`).
**Export PDF…** uses a Save file dialog; **Print…** uses the same HTML as PDF and :func:`desktop_app.invoice_preferences.configure_printer_for_bill_print`.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from typing import Optional

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QShowEvent, QTextDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QFileDialog,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop_app.bill_pdf import bill_html_string, save_bill_pdf
from desktop_app.flexible_date import (
    attach_line_edit_us_date_normalization,
    format_iso_to_us_display,
    format_ymd_as_us,
    line_edit_to_iso_or_raw,
    parse_flexible_date_to_ymd,
)
from desktop_app.invoice_preferences import (
    configure_printer_for_bill_print,
    ensure_bill_output_folder,
)
from desktop_app.qt_mnemonic import message_box_information_ok
from probooksai import business

_LOG = logging.getLogger(__name__)


def _safe_bill_pdf_stem(vendor_invoice_number: str, bill_id: int) -> str:
    raw = (vendor_invoice_number or "").strip()
    if not raw:
        raw = f"bill-{bill_id}"
    forbidden = '<>:"/\\|?*\x00'
    cleaned = "".join(ch if ch not in forbidden and ord(ch) >= 32 else "_" for ch in raw)
    cleaned = cleaned.strip(" .") or f"bill-{bill_id}"
    return cleaned[:120]


from desktop_app.theme import (
    WORKFLOW_ALT_ROW as _BILL_STRIPE,
    WORKFLOW_CAPTION as _BILL_CAPTION,
    WORKFLOW_GRID as _BILL_GRID,
    WORKFLOW_HEADER_BG as _BILL_HEADER,
    WORKFLOW_INPUT_BG,
    WORKFLOW_PAGE_BG as _BILL_BG,
    WORKFLOW_PANEL_BG as _BILL_PANEL,
    WORKFLOW_TEXT as _BILL_TEXT,
)


def _amount_spin() -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(0.0, 999_999_999.99)
    s.setDecimals(2)
    s.setPrefix("$ ")
    s.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
    s.setStyleSheet(
        f"QDoubleSpinBox {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_BILL_GRID}; "
        f"padding: 2px 6px; color: {_BILL_TEXT}; }}"
    )
    return s


def _table_line_edit() -> QLineEdit:
    le = QLineEdit()
    le.setStyleSheet(
        f"QLineEdit {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_BILL_GRID}; "
        f"padding: 2px 6px; color: {_BILL_TEXT}; }}"
    )
    return le


def _table_line_date_edit() -> QLineEdit:
    """Line **Date** column: same flexible-typed US-date normalization as the Invoice screen."""
    le = _table_line_edit()
    attach_line_edit_us_date_normalization(le)
    return le


def _format_vendor_address_row(row: dict) -> str:
    """Build a multi-line address block from a ``vendors`` row."""
    lines: list[str] = []
    addr = (row.get("address") or "").strip()
    if addr:
        lines.append(addr)
    email = (row.get("email") or "").strip()
    if email:
        lines.append(email)
    phone = (row.get("phone") or "").strip()
    if phone:
        lines.append(phone)
    return "\n".join(lines)


class EnterBillsScreen(QWidget):
    """Bill header (vendor, dates, vendor invoice #, memo) and expense lines persisted to ``bills`` / ``bill_expense_lines``."""

    _LINE_COLS = ("Date", "Ticket Number", "Dollar Amount", "Memo", "Customer:Job")
    _N_EXPENSE_ROWS = 12

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        ap_conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        super().__init__(parent)
        self._ap_conn = ap_conn
        self._current_bill_id: int | None = None
        self._attachment_path: str = ""
        self._suppress_line_recalc: bool = False
        self._bill_print_dialog_armed: bool = False
        self.setToolTip(
            "Enter Bills: vendor bill header and expense lines; Save writes to your company file. "
            "Same company .db (File → Backup / Restore, probooks.backup)."
        )
        self._amount_spins: list[QDoubleSpinBox] = []
        self._build_ui()
        self._populate_vendor_combo()
        self._update_save_enabled()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        page = QFrame()
        page.setObjectName("enterBillsLightPanel")
        page.setStyleSheet(
            f"QFrame#enterBillsLightPanel {{ background-color: {_BILL_BG}; border: 1px solid {_BILL_GRID}; "
            "border-radius: 8px; }}"
        )
        play = QVBoxLayout(page)
        play.setContentsMargins(16, 16, 16, 16)
        play.setSpacing(12)

        title_row = QHBoxLayout()
        title = QLabel("Enter Bills")
        title.setStyleSheet(
            f"font-size: 20px; font-weight: 600; color: {_BILL_TEXT}; background: transparent;"
        )
        title_row.addWidget(title)
        title_row.addStretch(1)
        play.addLayout(title_row)

        sec_vendor = QLabel("Vendor & bill header")
        sec_vendor.setStyleSheet(
            f"color: {_BILL_CAPTION}; font-size: 11px; font-weight: 600; "
            "letter-spacing: 0.03em; background: transparent;"
        )
        sec_vendor.setToolTip("Select a vendor; address fills from your company file when available.")
        play.addWidget(sec_vendor)

        # ── Header: Vendor + Vendor Address only (full width) ──
        form_frame = QFrame()
        form_frame.setObjectName("enterBillsHeaderBand")
        form_frame.setStyleSheet(
            f"QFrame#enterBillsHeaderBand {{ background-color: {_BILL_PANEL}; "
            f"border: 1px solid {_BILL_GRID}; border-radius: 8px; }}"
        )
        form_lay = QGridLayout(form_frame)
        form_lay.setContentsMargins(14, 12, 14, 12)
        form_lay.setHorizontalSpacing(12)
        form_lay.setVerticalSpacing(10)
        form_lay.setColumnStretch(1, 1)

        self._vendor = QComboBox()
        self._vendor.setEditable(False)
        self._vendor.setMinimumWidth(280)
        self._vendor.setStyleSheet(
            f"QComboBox {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_BILL_GRID}; "
            f"padding: 4px 8px; color: {_BILL_TEXT}; }}"
        )

        self._address = QPlainTextEdit()
        self._address.setPlaceholderText("Vendor Address")
        self._address.setFixedHeight(72)
        self._address.setStyleSheet(
            f"QPlainTextEdit {{ background: {WORKFLOW_INPUT_BG}; color: {_BILL_TEXT}; "
            f"border: 1px solid {_BILL_GRID}; border-radius: 4px; padding: 4px; }}"
        )

        _vl = QLabel("Vendor")
        _vl.setStyleSheet(
            f"color: {_BILL_CAPTION}; font-size: 11px; font-weight: 600; background: transparent;"
        )
        form_lay.addWidget(_vl, 0, 0, Qt.AlignmentFlag.AlignRight)
        form_lay.addWidget(self._vendor, 0, 1)
        _al = QLabel("Vendor Address")
        _al.setStyleSheet(
            f"color: {_BILL_CAPTION}; font-size: 11px; font-weight: 600; background: transparent;"
        )
        form_lay.addWidget(
            _al,
            1,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
        )
        form_lay.addWidget(self._address, 1, 1)

        _hdr_le_style = (
            f"QLineEdit {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_BILL_GRID}; "
            f"padding: 4px 8px; color: {_BILL_TEXT}; }}"
        )
        self._bill_date = QLineEdit()
        qd = QDate.currentDate()
        self._bill_date.setText(format_ymd_as_us(qd.month(), qd.day(), qd.year()))
        self._bill_date.setPlaceholderText("MM/DD/YYYY")
        self._bill_date.setStyleSheet(_hdr_le_style)
        self._bill_date.setToolTip(
            "Bill date: type flexibly (e.g. 5/21/26, 05.21.26, 052126); "
            "normalized to MM/DD/YYYY on commit. Stored as YYYY-MM-DD."
        )
        attach_line_edit_us_date_normalization(self._bill_date)

        self._vendor_inv = QLineEdit()
        self._vendor_inv.setPlaceholderText("Vendor invoice / reference #")
        self._vendor_inv.setStyleSheet(_hdr_le_style)

        self._due_date = QLineEdit()
        self._due_date.setPlaceholderText("MM/DD/YYYY (optional)")
        self._due_date.setStyleSheet(_hdr_le_style)
        self._due_date.setToolTip(
            "Due date (optional): type flexibly (e.g. 5/21/26, 05.21.26, 052126); "
            "normalized to MM/DD/YYYY on commit."
        )
        attach_line_edit_us_date_normalization(self._due_date)

        self._header_memo = QLineEdit()
        self._header_memo.setPlaceholderText("Memo (optional)")
        self._header_memo.setStyleSheet(_hdr_le_style)

        _bdl = QLabel("Bill date")
        _bdl.setStyleSheet(
            f"color: {_BILL_CAPTION}; font-size: 11px; font-weight: 600; background: transparent;"
        )
        form_lay.addWidget(_bdl, 2, 0, Qt.AlignmentFlag.AlignRight)
        form_lay.addWidget(self._bill_date, 2, 1)

        _vil = QLabel("Vendor invoice #")
        _vil.setStyleSheet(
            f"color: {_BILL_CAPTION}; font-size: 11px; font-weight: 600; background: transparent;"
        )
        form_lay.addWidget(_vil, 3, 0, Qt.AlignmentFlag.AlignRight)
        form_lay.addWidget(self._vendor_inv, 3, 1)

        _due_l = QLabel("Due date")
        _due_l.setStyleSheet(
            f"color: {_BILL_CAPTION}; font-size: 11px; font-weight: 600; background: transparent;"
        )
        form_lay.addWidget(_due_l, 4, 0, Qt.AlignmentFlag.AlignRight)
        form_lay.addWidget(self._due_date, 4, 1)

        _mem_l = QLabel("Memo")
        _mem_l.setStyleSheet(
            f"color: {_BILL_CAPTION}; font-size: 11px; font-weight: 600; background: transparent;"
        )
        form_lay.addWidget(_mem_l, 5, 0, Qt.AlignmentFlag.AlignRight)
        form_lay.addWidget(self._header_memo, 5, 1)

        play.addWidget(form_frame)

        self._vendor.currentIndexChanged.connect(self._on_vendor_changed)

        line_sec = QLabel("Expense lines")
        line_sec.setStyleSheet(
            f"color: {_BILL_CAPTION}; font-size: 11px; font-weight: 600; "
            "letter-spacing: 0.03em; background: transparent;"
        )
        line_sec.setToolTip(
            "Line-by-line expenses; amounts sum to the bill total saved with Save && Close / Save && New."
        )
        play.addWidget(line_sec)

        # ── Line grid (no separate expenses subtotal row) ──
        self._table = QTableWidget(self._N_EXPENSE_ROWS, len(self._LINE_COLS))
        self._table.setObjectName("enterBillsExpensesTable")
        self._table.setHorizontalHeaderLabels(self._LINE_COLS)
        self._table.verticalHeader().setVisible(True)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self._table.horizontalHeader().setStretchLastSection(False)
        for col in (0, 1, 2):
            self._table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )
        for col in (3, 4):
            self._table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.Stretch
            )

        self._table.setStyleSheet(
            f"QTableWidget#enterBillsExpensesTable {{"
            f" background-color: {_BILL_PANEL};"
            f" alternate-background-color: {_BILL_STRIPE};"
            f" color: {_BILL_TEXT};"
            f" gridline-color: {_BILL_GRID};"
            f" border: 1px solid {_BILL_GRID};"
            " }"
            f"QHeaderView::section {{"
            f" background-color: {_BILL_HEADER};"
            f" color: {_BILL_TEXT};"
            f" padding: 6px; border: 1px solid {_BILL_GRID};"
            " font-weight: 600;"
            " }}"
        )

        edit_flags = (
            Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsEditable
        )
        for row in range(self._N_EXPENSE_ROWS):
            dt = _table_line_date_edit()
            dt.setPlaceholderText("MM/DD/YYYY")
            dt.setToolTip(
                "Line date: type flexibly (e.g. 5/21/26, 05.21.26, 052126); "
                "normalized to MM/DD/YYYY on commit."
            )
            self._table.setCellWidget(row, 0, dt)

            ticket = _table_line_edit()
            ticket.setPlaceholderText("Ticket Number")
            self._table.setCellWidget(row, 1, ticket)

            amt = _amount_spin()
            amt.setValue(0.0)
            self._table.setCellWidget(row, 2, amt)
            self._amount_spins.append(amt)

            memo_it = QTableWidgetItem("")
            memo_it.setFlags(edit_flags)
            self._table.setItem(row, 3, memo_it)

            job_edit = QLineEdit()
            job_edit.setPlaceholderText("Customer:Job")
            job_edit.setStyleSheet(
                f"QLineEdit {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_BILL_GRID}; "
                f"padding: 2px 4px; color: {_BILL_TEXT}; }}"
            )
            self._table.setCellWidget(row, 4, job_edit)

        for sp in self._amount_spins:
            sp.valueChanged.connect(self._on_line_amount_changed)
        self._table.itemChanged.connect(self._on_table_item_changed)

        play.addWidget(self._table, 1)

        tot_row = QHBoxLayout()
        tot_row.addStretch(1)
        self._lbl_bill_total = QLabel("Total: $0.00")
        self._lbl_bill_total.setStyleSheet(
            f"color: {_BILL_TEXT}; font-size: 14px; font-weight: 600; background: transparent;"
        )
        tot_row.addWidget(self._lbl_bill_total)
        play.addLayout(tot_row)

        # ── Bottom actions ──
        actions_frame = QFrame()
        actions_frame.setObjectName("enterBillsActionsBar")
        actions_frame.setStyleSheet(
            f"QFrame#enterBillsActionsBar {{ background-color: {_BILL_PANEL}; "
            f"border: 1px solid {_BILL_GRID}; border-radius: 6px; }}"
        )
        bot = QHBoxLayout(actions_frame)
        bot.setContentsMargins(12, 10, 12, 10)
        bot.addStretch(1)
        self._btn_export_pdf = QPushButton("Export PDF…")
        self._btn_export_pdf.setToolTip(
            "Save this bill to the company file, then pick a .pdf path (does not change the bills folder in preferences)."
        )
        self._btn_print = QPushButton("Print…")
        self._btn_print.setToolTip(
            "Save this bill to the company file, then print (same layout as PDF). "
            "Uses the printer from the print dialog, saved for next time."
        )
        self._btn_save_close = QPushButton("Save && Close")
        self._btn_save_new = QPushButton("Save && New")
        self._btn_clear = QPushButton("Clear")
        self._btn_save_close.setToolTip(
            "Save this bill to the company file, then clear the form for the next entry."
        )
        self._btn_save_new.setToolTip(
            "Save this bill to the company file, then clear the form for a new bill."
        )
        self._btn_clear.setToolTip("Clear the form without saving (new draft).")
        self._btn_export_pdf.clicked.connect(self._on_export_bill_pdf)
        self._btn_print.clicked.connect(self._on_print_bill)
        self._btn_save_close.clicked.connect(self._on_save_close)
        self._btn_save_new.clicked.connect(self._on_save_new)
        self._btn_clear.clicked.connect(self._on_clear)
        for _b in (
            self._btn_export_pdf,
            self._btn_print,
            self._btn_save_close,
            self._btn_save_new,
            self._btn_clear,
        ):
            _b.setAutoDefault(False)
            _b.setDefault(False)
        bot.addWidget(self._btn_export_pdf)
        bot.addWidget(self._btn_print)
        bot.addWidget(self._btn_save_close)
        bot.addWidget(self._btn_save_new)
        bot.addWidget(self._btn_clear)
        play.addWidget(actions_frame)

        outer.addWidget(page, 1)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._update_save_enabled()

    def _update_save_enabled(self) -> None:
        on = self._ap_conn is not None
        self._btn_save_close.setEnabled(on)
        self._btn_save_new.setEnabled(on)
        self._btn_export_pdf.setEnabled(on)
        self._btn_print.setEnabled(on)

    def _feedback(self, msg: str) -> None:
        if not (msg or "").strip():
            return
        _LOG.info("Enter Bills: %s", msg.strip())
        w: QWidget | None = self
        while w is not None:
            if isinstance(w, QMainWindow):
                sb = w.statusBar()
                if sb is not None:
                    sb.showMessage(msg.strip(), 8000)
                    return
            w = w.parentWidget()

    def _populate_vendor_combo(self) -> None:
        self._vendor.blockSignals(True)
        self._vendor.clear()
        self._vendor.addItem("", None)
        if self._ap_conn is not None:
            try:
                for row in business.list_vendors(self._ap_conn):
                    d = dict(row)
                    vid = int(d["id"])
                    name = (d.get("name") or "").strip()
                    self._vendor.addItem(name or f"Vendor #{vid}", vid)
            except (sqlite3.Error, KeyError, TypeError, ValueError):
                pass
        self._vendor.blockSignals(False)
        self._on_vendor_changed(self._vendor.currentIndex())
        self._update_save_enabled()

    def refresh_vendors(self) -> None:
        """Reload vendor names from the company connection (e.g. after Business hub edits)."""
        self._populate_vendor_combo()

    def open_bill_by_id(self, bill_id: int) -> bool:
        """Load a bill into this tab (bank register / in-app navigation)."""
        if self._ap_conn is None:
            message_box_information_ok(
                self,
                "Bill",
                "Open a company file to edit bills.",
                ok_tip="Close; use File → Open company… then try the link again.",
            )
            return False
        bid = int(bill_id)
        b, _lines = business.get_bill_detail(self._ap_conn, bid)
        if b is None:
            message_box_information_ok(
                self,
                "Bill",
                f"Bill #{bid} was not found.",
                ok_tip="Close; refresh the register or company data and try again.",
            )
            return False
        self.refresh_vendors()
        self._load_bill_into_form(bid)
        return True

    def open_bill_by_vendor_invoice_number(
        self,
        vendor_invoice_number: str,
        *,
        vendor_id: int | None = None,
    ) -> bool:
        """Load a bill by ``bills.vendor_invoice_number`` (optional *vendor_id* disambiguates)."""
        if self._ap_conn is None:
            message_box_information_ok(
                self,
                "Bill",
                "Open a company file to edit bills.",
                ok_tip="Close; use File → Open company… then try again.",
            )
            return False
        bid = business.get_bill_id_by_vendor_invoice_number(
            self._ap_conn,
            vendor_invoice_number,
            vendor_id=vendor_id,
        )
        if bid is None:
            ref = (vendor_invoice_number or "").strip()
            message_box_information_ok(
                self,
                "Bill",
                f"No unique bill with vendor invoice / reference {ref!r} was found.",
                ok_tip="Close; use Enter Bills after picking the vendor, or open the bill from the Bank register link.",
            )
            return False
        return self.open_bill_by_id(bid)

    def _selected_vendor_id(self) -> int | None:
        raw = self._vendor.currentData()
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    def _select_vendor_id(self, vid: int) -> None:
        for i in range(self._vendor.count()):
            data = self._vendor.itemData(i)
            if data is not None and int(data) == int(vid):
                self._vendor.setCurrentIndex(i)
                return

    def _on_vendor_changed(self, _index: int) -> None:
        raw = self._vendor.currentData()
        if raw is None or self._ap_conn is None:
            self._address.clear()
            return
        try:
            vid = int(raw)
        except (TypeError, ValueError):
            self._address.clear()
            return
        row = business.get_vendor(self._ap_conn, vid)
        if row is None:
            self._address.clear()
            return
        self._address.setPlainText(_format_vendor_address_row(dict(row)))

    def _on_line_amount_changed(self, _v: float) -> None:
        if self._suppress_line_recalc:
            return
        self._recalc_total_label()

    def _on_table_item_changed(self, _item: QTableWidgetItem) -> None:
        if self._suppress_line_recalc:
            return
        self._recalc_total_label()

    def _recalc_total_label(self) -> None:
        lines = self._collect_expense_lines()
        t = sum(round(float(x["amount"]), 2) for x in lines)
        self._lbl_bill_total.setText(f"Total: ${t:,.2f}")

    def _collect_expense_lines(self) -> list[dict]:
        rows: list[dict] = []
        for r in range(self._N_EXPENSE_ROWS):
            dt_w = self._table.cellWidget(r, 0)
            tk_w = self._table.cellWidget(r, 1)
            amt_w = self._table.cellWidget(r, 2)
            memo_it = self._table.item(r, 3)
            job_w = self._table.cellWidget(r, 4)
            line_date = dt_w.text().strip() if isinstance(dt_w, QLineEdit) else ""
            ticket = tk_w.text().strip() if isinstance(tk_w, QLineEdit) else ""
            amt = float(amt_w.value()) if isinstance(amt_w, QDoubleSpinBox) else 0.0
            memo = (memo_it.text() or "").strip() if memo_it is not None else ""
            job = job_w.text().strip() if isinstance(job_w, QLineEdit) else ""
            if (
                amt == 0.0
                and not line_date
                and not ticket
                and not memo
                and not job
            ):
                continue
            ld = line_date
            if line_date:
                ymd = parse_flexible_date_to_ymd(line_date)
                if ymd:
                    y, m, d = ymd
                    ld = f"{y:04d}-{m:02d}-{d:02d}"
            rows.append(
                {
                    "line_date": ld,
                    "ticket_ref": ticket,
                    "amount": amt,
                    "memo": memo,
                    "customer_job": job,
                }
            )
        return rows

    def _clear_expense_grid(self) -> None:
        self._suppress_line_recalc = True
        try:
            for sp in self._amount_spins:
                sp.setValue(0.0)
            for r in range(self._N_EXPENSE_ROWS):
                dt = self._table.cellWidget(r, 0)
                if isinstance(dt, QLineEdit):
                    dt.clear()
                ticket = self._table.cellWidget(r, 1)
                if isinstance(ticket, QLineEdit):
                    ticket.clear()
                memo = self._table.item(r, 3)
                if memo is not None:
                    memo.setText("")
                job = self._table.cellWidget(r, 4)
                if isinstance(job, QLineEdit):
                    job.clear()
        finally:
            self._suppress_line_recalc = False
        self._recalc_total_label()

    def _reset_form_new_draft(self) -> None:
        self._current_bill_id = None
        self._attachment_path = ""
        self._vendor.blockSignals(True)
        self._vendor.setCurrentIndex(0)
        self._vendor.blockSignals(False)
        self._address.clear()
        qd = QDate.currentDate()
        self._bill_date.setText(format_ymd_as_us(qd.month(), qd.day(), qd.year()))
        self._vendor_inv.clear()
        self._due_date.clear()
        self._header_memo.clear()
        self._clear_expense_grid()

    def _try_persist_bill(self) -> tuple[bool, str, int | None]:
        if self._ap_conn is None:
            return False, "Open a company database to save bills.", None
        vid = self._selected_vendor_id()
        if vid is None:
            return False, "Select a vendor.", None
        ymd = parse_flexible_date_to_ymd(self._bill_date.text().strip())
        if ymd is None:
            return False, "Enter a valid bill date.", None
        y, m, d = ymd
        bill_date_iso = f"{y:04d}-{m:02d}-{d:02d}"
        lines = self._collect_expense_lines()
        if not lines:
            return False, "Enter at least one expense line (amount or detail).", None
        total_sum = sum(round(float(x["amount"]), 2) for x in lines)
        if total_sum <= 0:
            return False, "Bill total must be greater than zero.", None
        due_iso = (line_edit_to_iso_or_raw(self._due_date) or "").strip()
        memo_h = self._header_memo.text().strip()
        vinv = self._vendor_inv.text().strip()
        conn = self._ap_conn
        edit_id = self._current_bill_id
        try:
            if edit_id is not None:
                business.update_bill(
                    conn,
                    edit_id,
                    vid,
                    bill_date_iso,
                    0.0,
                    vendor_invoice_number=vinv,
                    due_date=due_iso,
                    memo=memo_h,
                    attachment_path=self._attachment_path,
                    expense_lines=lines,
                )
                return True, "", edit_id
            bid = business.create_bill(
                conn,
                vid,
                bill_date_iso,
                0.0,
                vendor_invoice_number=vinv,
                due_date=due_iso,
                memo=memo_h,
                attachment_path=self._attachment_path,
                expense_lines=lines,
            )
            return True, "", bid
        except ValueError as exc:
            return False, str(exc), None
        except sqlite3.Error as exc:
            return False, str(exc), None

    def _load_bill_into_form(self, bill_id: int) -> None:
        if self._ap_conn is None:
            return
        b, lines = business.get_bill_detail(self._ap_conn, bill_id)
        if b is None:
            return
        d = dict(b)
        self._suppress_line_recalc = True
        try:
            self._current_bill_id = bill_id
            self._attachment_path = (d.get("attachment_path") or "").strip()
            iso = (d.get("bill_date") or "").strip()
            self._bill_date.setText(
                format_iso_to_us_display(iso[:10]) if len(iso) >= 10 else ""
            )
            self._vendor_inv.setText((d.get("vendor_invoice_number") or "").strip())
            due = (d.get("due_date") or "").strip()
            if due and len(due) >= 10 and due[4] == "-":
                self._due_date.setText(format_iso_to_us_display(due[:10]))
            else:
                self._due_date.setText(due)
            self._header_memo.setText((d.get("memo") or "").strip())
            self._vendor.blockSignals(True)
            self._select_vendor_id(int(d["vendor_id"]))
            self._vendor.blockSignals(False)
            self._on_vendor_changed(self._vendor.currentIndex())

            for sp in self._amount_spins:
                sp.setValue(0.0)
            for r in range(self._N_EXPENSE_ROWS):
                dt = self._table.cellWidget(r, 0)
                if isinstance(dt, QLineEdit):
                    dt.clear()
                ticket = self._table.cellWidget(r, 1)
                if isinstance(ticket, QLineEdit):
                    ticket.clear()
                memo = self._table.item(r, 3)
                if memo is not None:
                    memo.setText("")
                job = self._table.cellWidget(r, 4)
                if isinstance(job, QLineEdit):
                    job.clear()
            if lines:
                for i, ln in enumerate(lines):
                    if i >= self._N_EXPENSE_ROWS:
                        break
                    row = dict(ln)
                    dt_w = self._table.cellWidget(i, 0)
                    tk_w = self._table.cellWidget(i, 1)
                    amt_w = self._table.cellWidget(i, 2)
                    memo_it = self._table.item(i, 3)
                    job_w = self._table.cellWidget(i, 4)
                    ld = (row.get("line_date") or "").strip()
                    if isinstance(dt_w, QLineEdit):
                        if ld and len(ld) >= 10 and ld[4] == "-":
                            dt_w.setText(format_iso_to_us_display(ld[:10]))
                        else:
                            dt_w.setText(ld)
                    if isinstance(tk_w, QLineEdit):
                        tk_w.setText((row.get("ticket_ref") or "").strip())
                    if isinstance(amt_w, QDoubleSpinBox):
                        amt_w.setValue(float(row.get("amount") or 0.0))
                    if memo_it is not None:
                        memo_it.setText((row.get("memo") or "").strip())
                    if isinstance(job_w, QLineEdit):
                        job_w.setText((row.get("customer_job") or "").strip())
            else:
                amt0 = self._table.cellWidget(0, 2)
                if isinstance(amt0, QDoubleSpinBox):
                    amt0.setValue(float(d.get("total") or 0.0))
        finally:
            self._suppress_line_recalc = False
        self._recalc_total_label()

    def _write_bill_pdf_to_prefs_folder(self, bill_id: int) -> None:
        if self._ap_conn is None:
            return
        folder = ensure_bill_output_folder(self)
        if folder is None:
            return
        vinv = self._vendor_inv.text().strip()
        name = f"Bill-{_safe_bill_pdf_stem(vinv, bill_id)}.pdf"
        path = os.path.join(folder, name)
        try:
            save_bill_pdf(self._ap_conn, bill_id, path)
        except OSError as exc:
            self._feedback(f"Bill saved, but the PDF could not be written: {exc}")
        except Exception as exc:  # noqa: BLE001
            self._feedback(f"Bill saved, but PDF export failed: {exc}")

    def _on_export_bill_pdf(self) -> None:
        if self.sender() is not self._btn_export_pdf:
            return
        if self._ap_conn is None:
            self._feedback("Open a company file to export a PDF.")
            return
        was_new = self._current_bill_id is None
        ok, msg, bid = self._try_persist_bill()
        if not ok:
            self._feedback(msg)
            return
        assert bid is not None
        vinv = self._vendor_inv.text().strip()
        default_name = f"Bill-{_safe_bill_pdf_stem(vinv, bid)}.pdf"
        path, _filt = QFileDialog.getSaveFileName(
            self,
            "Export bill as PDF",
            default_name,
            "PDF files (*.pdf);;All files (*.*)",
        )
        if not path:
            if was_new:
                self._load_bill_into_form(bid)
            return
        if not path.lower().endswith(".pdf"):
            path = f"{path}.pdf"
        try:
            save_bill_pdf(self._ap_conn, bid, path)
        except OSError as exc:
            self._feedback(f"Bill saved, but the PDF could not be written: {exc}")
            return
        except Exception as exc:  # noqa: BLE001
            self._feedback(f"Bill saved, but PDF export failed: {exc}")
            return
        self._feedback("Bill saved.")
        if was_new:
            self._reset_form_new_draft()
        else:
            self._load_bill_into_form(bid)

    def _run_bill_print_dialog(self, bill_id: int, *, reset_after: bool) -> None:
        if not self._bill_print_dialog_armed:
            return
        if self._ap_conn is None:
            return
        doc = QTextDocument()
        try:
            doc.setHtml(bill_html_string(self._ap_conn, bill_id))
        except Exception as exc:  # noqa: BLE001
            self._feedback(f"Could not prepare the bill for printing: {exc}")
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        if not configure_printer_for_bill_print(self, printer):
            return
        doc.print_(printer)
        self._feedback("Bill saved.")
        if reset_after:
            self._reset_form_new_draft()
        else:
            self._load_bill_into_form(bill_id)

    def _on_print_bill(self) -> None:
        if self.sender() is not self._btn_print:
            return
        if self._ap_conn is None:
            self._feedback("Open a company file to print bills.")
            return
        was_new = self._current_bill_id is None
        self._bill_print_dialog_armed = True
        try:
            ok, msg, bid = self._try_persist_bill()
            if not ok:
                self._feedback(msg)
                return
            assert bid is not None
            self._run_bill_print_dialog(bid, reset_after=was_new)
        finally:
            self._bill_print_dialog_armed = False

    def _on_save_close(self) -> None:
        if self.sender() is not self._btn_save_close:
            return
        ok, msg, bid = self._try_persist_bill()
        if not ok:
            self._feedback(msg)
            return
        assert bid is not None
        self._write_bill_pdf_to_prefs_folder(bid)
        self._feedback("Bill saved.")
        self._reset_form_new_draft()

    def _on_save_new(self) -> None:
        if self.sender() is not self._btn_save_new:
            return
        ok, msg, bid = self._try_persist_bill()
        if not ok:
            self._feedback(msg)
            return
        assert bid is not None
        self._write_bill_pdf_to_prefs_folder(bid)
        self._feedback("Bill saved.")
        self._reset_form_new_draft()

    def _on_clear(self) -> None:
        self._reset_form_new_draft()
