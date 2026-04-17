"""Financial reports: GL trial balance, P&L, balance sheet; AR/AP lists and aging (More → Reports).

**F5** re-runs the last report you opened (financial or AR/AP).

**Help → More tab shortcuts (F5)…**; results grid **right-click** sets **QAction** tooltips for **Keyboard shortcuts…** and **Copy row** (including empty area).
The tab **root** **QWidget** has a hover hint. **Start** / **End** date fields use **setToolTip** (flexible entry, MM/DD/YYYY display); the date-range **QGroupBox** has a hover hint.
The results table, **summary** line, and footer **F5** hint label have hover tooltips.

**As-of date for AR/AP aging:** uses the **End** field when set; otherwise today (local date). Bank register remains the system of record for posted bank activity; these reports read AR/AP tables in the company file.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from functools import partial
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from desktop_app.more_main_tabs_shortcuts import (
    show_more_main_tabs_keyboard_shortcuts_dialog,
)
from desktop_app.qt_mnemonic import (
    CSV_EXPORT_OK_TIP_SUFFIX,
    escape_ampersand_for_qt,
    message_box_critical_ok,
    message_box_information_ok,
)
from desktop_app.flexible_date import (
    attach_line_edit_us_date_normalization,
    line_edit_to_iso_or_raw,
)
from desktop_app.table_clipboard import (
    CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX,
    VIEW_BANK_REGISTER_KEYS_TOOLTIP,
    FloatSortTableItem,
    copy_table_row_as_tsv,
    plain_display_table_item,
)
from probooksai import business, financial_reports

_AGING_BUCKET_LABELS = {
    "current": "Current",
    "1_30": "1–30 days",
    "31_60": "31–60 days",
    "61_90": "61–90 days",
    "91_plus": "91+ days",
}


class ReportsTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._last_export: dict | None = None
        self._last_report_kind: Optional[str] = None
        self._build_ui()

    def _build_ui(self):
        self.setToolTip(
            "Financial reports (trial balance, P&L, balance sheet) and receivables/payables lists (aging, open invoices/bills, recent payments) "
            "with CSV export (UTF-8 BOM for Excel). "
            "F5 re-runs the last report you opened when this tab has focus. "
            "Same company SQLite database as other main tabs; File → Backup / Restore (probooks.backup)."
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        filt = QGroupBox("Date range / as-of (optional)")
        filt.setToolTip(
            "Financial reports: optional inclusive start/end (blank means open on that side). "
            "AR/AP aging: **End** is the as-of date when set; otherwise today is used. "
            "Type dates in common US forms; valid values normalize to MM/DD/YYYY."
        )
        fl = QFormLayout(filt)
        self._start = QLineEdit()
        self._start.setToolTip(
            "Report start date, optional; leave blank for no start cutoff. "
            "Flexible US-style entry; normalized on commit when valid."
        )
        attach_line_edit_us_date_normalization(self._start)
        self._end = QLineEdit()
        self._end.setToolTip(
            "Report end date, optional. Flexible US-style entry; normalized on commit when valid."
        )
        attach_line_edit_us_date_normalization(self._end)
        fl.addRow("Start", self._start)
        fl.addRow("End", self._end)
        layout.addWidget(filt)

        row = QHBoxLayout()
        for label, fn, tip in (
            (
                "Trial Balance",
                self._show_tb,
                "Run trial balance. F5 re-runs whichever report you opened last "
                "(financial or AR/AP).",
            ),
            (
                "Income Statement",
                self._show_pl,
                "Run income statement (P&L). F5 re-runs the last report you opened.",
            ),
            (
                "Balance Sheet",
                self._show_bs,
                "Run balance sheet. F5 re-runs the last report you opened.",
            ),
        ):
            b = QPushButton(label)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            row.addWidget(b)
        btn_export = QPushButton("Export CSV…")
        btn_export.setToolTip(
            "Save the **last report table** you ran (trial balance, P&L, or any Receivables & payables button). "
            "UTF-8 BOM for Excel. You can also use **View → More reports** to jump here and run a report first."
        )
        btn_export.clicked.connect(self._export_csv)
        row.addWidget(btn_export)
        row.addStretch()
        layout.addLayout(row)

        self._report_heading = QLabel("Current report: — (run a report below)")
        self._report_heading.setWordWrap(True)
        self._report_heading.setStyleSheet("color: #C8C8D8; font-size: 13px; font-weight: 600;")
        self._report_heading.setToolTip(
            "Shows which receivables/payables or financial report is in the grid. "
            "Bank Register stays the source of truth for bank activity; these read AR/AP tables in the company file."
        )
        layout.addWidget(self._report_heading)

        ar_ap = QGroupBox("Receivables & payables (A/R & A/P)")
        ar_ap.setToolTip(
            "Open-item and aging views from the company AR/AP tables (not the Bank Register grid). "
            "Toolbar **Export CSV…** saves the last table you ran. UTF-8 BOM for Excel."
        )
        ar_ap_lay = QVBoxLayout(ar_ap)
        ar_buttons = (
            (
                "A/R aging",
                self._show_ar_aging,
                "Open balances by aging bucket as of the End date (or today).",
            ),
            (
                "A/P aging",
                self._show_ap_aging,
                "Open vendor balances by aging bucket as of the End date (or today).",
            ),
            (
                "Open invoices",
                self._show_open_invoices,
                "Invoices with balance due (same source as AR workflows).",
            ),
            (
                "Open bills",
                self._show_open_bills,
                "Bills with balance due (same source as AP workflows).",
            ),
            (
                "Recent customer payments",
                self._show_recent_ar_payments,
                "AR payment records, newest first (limited to 100 rows).",
            ),
            (
                "Recent vendor payments",
                self._show_recent_ap_payments,
                "AP payment records, newest first (limited to 100 rows).",
            ),
        )
        for row_start in (0, 3):
            h = QHBoxLayout()
            for label, fn, tip in ar_buttons[row_start : row_start + 3]:
                b = QPushButton(label)
                b.setToolTip(tip)
                b.clicked.connect(fn)
                h.addWidget(b)
            ar_ap_lay.addLayout(h)
        layout.addWidget(ar_ap)

        self._table = QTableWidget()
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_report_context_menu)
        self._table.setSortingEnabled(True)
        self._table.setToolTip(
            "Report results after you run a report from the toolbar or Receivables & payables. "
            "Export CSV… uses UTF-8 BOM for Excel. "
            "Right-click for Keyboard shortcuts… (including on empty area)."
        )
        layout.addWidget(self._table)

        self._summary = QLabel("")
        self._summary.setWordWrap(True)
        self._summary.setToolTip(
            "Summary line after you run a report (totals, row count, or validation notes)."
        )
        layout.addWidget(self._summary)

        tip = QLabel(
            "F5 re-runs the last report you opened (financial or AR/AP). "
            "Export CSV… saves the current table (UTF-8 with BOM for Excel)."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #A0A0B0; font-size: 11px;")
        tip.setToolTip(
            "Shortcut reminder: F5 repeats the last report you opened."
        )
        layout.addWidget(tip)

        sc_f5 = QShortcut(QKeySequence("F5"), self)
        sc_f5.setContext(Qt.WidgetWithChildrenShortcut)
        sc_f5.activated.connect(self._rerun_last_report)

    def activate_report(self, kind: str) -> None:
        """Run a report by kind string (used from **View → More reports**)."""
        k = (kind or "").strip().lower().replace("-", "_")
        dispatch = {
            "ar_aging": self._show_ar_aging,
            "ap_aging": self._show_ap_aging,
            "open_inv": self._show_open_invoices,
            "open_bill": self._show_open_bills,
            "open_invoices": self._show_open_invoices,
            "open_bills": self._show_open_bills,
            "ar_pay": self._show_recent_ar_payments,
            "ap_pay": self._show_recent_ap_payments,
        }
        fn = dispatch.get(k)
        if fn is not None:
            fn()

    def _set_report_heading(self, text: str) -> None:
        self._report_heading.setText(text)

    def _rerun_last_report(self) -> None:
        if self._last_report_kind == "tb":
            self._show_tb()
        elif self._last_report_kind == "pl":
            self._show_pl()
        elif self._last_report_kind == "bs":
            self._show_bs()
        elif self._last_report_kind == "ar_aging":
            self._show_ar_aging()
        elif self._last_report_kind == "ap_aging":
            self._show_ap_aging()
        elif self._last_report_kind == "open_inv":
            self._show_open_invoices()
        elif self._last_report_kind == "open_bill":
            self._show_open_bills()
        elif self._last_report_kind == "ar_pay":
            self._show_recent_ar_payments()
        elif self._last_report_kind == "ap_pay":
            self._show_recent_ap_payments()

    def _as_of_iso(self) -> str:
        end = line_edit_to_iso_or_raw(self._end)
        if end:
            return end
        return date.today().isoformat()

    def _on_report_context_menu(self, pos):
        idx = self._table.indexAt(pos)
        m = QMenu(self)
        act_keys = m.addAction(
            "Keyboard shortcuts…",
            lambda: show_more_main_tabs_keyboard_shortcuts_dialog(self),
        )
        act_keys.setToolTip(
            "Same summary as Help → More tab shortcuts (F5)… (Reports, F5 re-run last report). "
            + VIEW_BANK_REGISTER_KEYS_TOOLTIP
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        if not idx.isValid():
            m.exec(self._table.viewport().mapToGlobal(pos))
            return
        row = idx.row()
        m.addSeparator()
        act_copy = m.addAction(
            "Copy row", partial(copy_table_row_as_tsv, self._table, row)
        )
        act_copy.setToolTip(
            "Copy this report row as tab-separated text for pasting into a spreadsheet or editor. "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        m.exec(self._table.viewport().mapToGlobal(pos))

    def _fill_table(
        self,
        headers: list[str],
        rows: list[list],
        *,
        numeric_columns: frozenset[int] = frozenset(),
    ) -> None:
        align_rc = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        self._table.setSortingEnabled(False)
        self._table.clear()
        self._table.setColumnCount(len(headers))
        self._table.setHorizontalHeaderLabels(headers)
        self._table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                if c in numeric_columns:
                    x = float(val)
                    disp = f"{x:,.2f}"
                    it = FloatSortTableItem(disp, x)
                    it.setTextAlignment(align_rc)
                    self._table.setItem(r, c, it)
                else:
                    self._table.setItem(r, c, plain_display_table_item(str(val)))
        self._table.setSortingEnabled(True)

    def _show_tb(self):
        start = line_edit_to_iso_or_raw(self._start)
        end = line_edit_to_iso_or_raw(self._end)
        data = financial_reports.trial_balance_report(self._conn, start, end)
        rows = [
            [d["account"], d["total_debit"], d["total_credit"], d["net"]] for d in data
        ]
        headers = ["Account", "Debit", "Credit", "Net (D−C)"]
        self._fill_table(headers, rows, numeric_columns=frozenset({1, 2, 3}))
        self._summary.setText(f"{len(data)} account(s) with activity.")
        self._set_report_heading("Current report: Trial balance")
        dr = f"{start or '—'} to {end or '—'}"
        self._last_export = {
            "preamble": [
                "ProBooks+ai – Trial balance",
                f"Date range: {dr}",
            ],
            "headers": headers,
            "rows": rows,
        }
        self._last_report_kind = "tb"

    def _show_pl(self):
        if not self._start.text().strip() or not self._end.text().strip():
            self._last_export = None
            self._last_report_kind = None
            self._set_report_heading("Current report: —")
            self._summary.setText(
                escape_ampersand_for_qt("Enter start and end dates for P&L.")
            )
            return
        start = line_edit_to_iso_or_raw(self._start)
        end = line_edit_to_iso_or_raw(self._end)
        pl = financial_reports.income_statement(self._conn, start, end)
        headers = ["Metric", "Amount"]
        table_rows = [
            ["Revenue (credit-normal)", pl["revenue"]],
            ["Expenses (debit-normal)", pl["expenses"]],
            ["Net income", pl["net_income"]],
        ]
        self._fill_table(headers, table_rows, numeric_columns=frozenset({1}))
        self._summary.setText(
            escape_ampersand_for_qt(
                "P&L uses posted journal lines and coa_accounts types (income / expense)."
            )
        )
        self._set_report_heading("Current report: Income statement (P&L)")
        self._last_export = {
            "preamble": [
                "ProBooks+ai – Income statement (P&L)",
                f"Period: {start} to {end}",
            ],
            "headers": headers,
            "rows": table_rows,
        }
        self._last_report_kind = "pl"

    def _show_bs(self):
        if self._end.text().strip():
            end = line_edit_to_iso_or_raw(self._end)
        elif self._start.text().strip():
            end = line_edit_to_iso_or_raw(self._start)
        else:
            end = None
        bs = financial_reports.balance_sheet_summary(self._conn, as_of_date=end)
        headers = ["Section", "Amount"]
        table_rows = [
            ["Assets", bs["assets"]],
            ["Liabilities", bs["liabilities"]],
            ["Equity", bs["equity"]],
            ["Liabilities + Equity", bs["liabilities_plus_equity"]],
        ]
        self._fill_table(headers, table_rows, numeric_columns=frozenset({1}))
        self._summary.setText(
            "Balance sheet aggregates by COA account type through the as-of date (end field)."
        )
        self._set_report_heading("Current report: Balance sheet summary")
        self._last_export = {
            "preamble": [
                "ProBooks+ai – Balance sheet summary",
                f"As of: {end or '(all posted activity)'}",
            ],
            "headers": headers,
            "rows": table_rows,
        }
        self._last_report_kind = "bs"

    def _show_ar_aging(self) -> None:
        as_of = self._as_of_iso()
        data = business.ar_aging_buckets(self._conn, as_of)[0]
        lines = data["lines"]
        buckets = data["buckets"]
        headers = ["Invoice id", "Customer", "Balance", "Aging bucket", "Days past due"]
        rows: list[list] = []
        for ln in lines:
            bk = ln["bucket"]
            rows.append(
                [
                    ln["invoice_id"],
                    ln["customer"],
                    ln["balance"],
                    _AGING_BUCKET_LABELS.get(bk, bk),
                    ln.get("days_past_due", ""),
                ]
            )
        self._fill_table(headers, rows, numeric_columns=frozenset({2, 4}))
        tot = sum(float(ln["balance"]) for ln in lines)
        buck_txt = ", ".join(
            f"{_AGING_BUCKET_LABELS.get(k, k)}={v:,.2f}" for k, v in buckets.items()
        )
        self._summary.setText(
            f"A/R aging as of {as_of}: {len(lines)} open line(s), total {tot:,.2f}. Buckets: {buck_txt}."
        )
        self._set_report_heading(f"Current report: A/R aging (as of {as_of})")
        self._last_export = {
            "preamble": [
                "ProBooks+ai – A/R aging",
                f"As of: {as_of}",
                f"Bucket totals: {buck_txt}",
            ],
            "headers": headers,
            "rows": rows,
        }
        self._last_report_kind = "ar_aging"

    def _show_ap_aging(self) -> None:
        as_of = self._as_of_iso()
        data = business.ap_aging_buckets(self._conn, as_of)[0]
        lines = data["lines"]
        buckets = data["buckets"]
        headers = ["Bill id", "Vendor", "Balance", "Aging bucket", "Days past due"]
        rows = []
        for ln in lines:
            bk = ln["bucket"]
            rows.append(
                [
                    ln["bill_id"],
                    ln["vendor"],
                    ln["balance"],
                    _AGING_BUCKET_LABELS.get(bk, bk),
                    ln.get("days_past_due", ""),
                ]
            )
        self._fill_table(headers, rows, numeric_columns=frozenset({2, 4}))
        tot = sum(float(ln["balance"]) for ln in lines)
        buck_txt = ", ".join(
            f"{_AGING_BUCKET_LABELS.get(k, k)}={v:,.2f}" for k, v in buckets.items()
        )
        self._summary.setText(
            f"A/P aging as of {as_of}: {len(lines)} open line(s), total {tot:,.2f}. Buckets: {buck_txt}."
        )
        self._set_report_heading(f"Current report: A/P aging (as of {as_of})")
        self._last_export = {
            "preamble": [
                "ProBooks+ai – A/P aging",
                f"As of: {as_of}",
                f"Bucket totals: {buck_txt}",
            ],
            "headers": headers,
            "rows": rows,
        }
        self._last_report_kind = "ap_aging"

    def _show_open_invoices(self) -> None:
        """Invoices with balance_due > 0."""
        rows_raw = business.list_invoices(self._conn)
        open_rows = [dict(r) for r in rows_raw if float(r["balance_due"] or 0) > 0.005]
        open_rows.sort(
            key=lambda d: (d.get("due_date") or "", d.get("invoice_number") or "")
        )
        headers = [
            "Invoice id",
            "Invoice #",
            "Customer",
            "Invoice date",
            "Due date",
            "Total",
            "Balance due",
            "Status",
        ]
        rows: list[list] = []
        tot_bal = 0.0
        for d in open_rows:
            bd = float(d.get("balance_due") or 0)
            tot_bal += bd
            rows.append(
                [
                    d.get("id"),
                    d.get("invoice_number") or "",
                    d.get("customer_name") or "",
                    d.get("invoice_date") or "",
                    d.get("due_date") or "",
                    float(d.get("total") or 0),
                    bd,
                    d.get("status") or "",
                ]
            )
        self._fill_table(headers, rows, numeric_columns=frozenset({5, 6}))
        self._summary.setText(
            f"Open invoices: {len(rows)} row(s), total balance due {tot_bal:,.2f}."
        )
        self._set_report_heading("Current report: Open invoices")
        self._last_export = {
            "preamble": ["ProBooks+ai – Open invoices (balance due > 0)"],
            "headers": headers,
            "rows": rows,
        }
        self._last_report_kind = "open_inv"

    def _show_open_bills(self) -> None:
        rows_raw = business.list_bills(self._conn)
        open_rows = [dict(r) for r in rows_raw if float(r["balance_due"] or 0) > 0.005]
        open_rows.sort(
            key=lambda d: (d.get("due_date") or "", d.get("vendor_invoice_number") or "")
        )
        headers = [
            "Bill id",
            "Vendor inv. #",
            "Vendor",
            "Bill date",
            "Due date",
            "Total",
            "Balance due",
            "Status",
        ]
        rows = []
        tot_bal = 0.0
        for d in open_rows:
            bd = float(d.get("balance_due") or 0)
            tot_bal += bd
            rows.append(
                [
                    d.get("id"),
                    d.get("vendor_invoice_number") or "",
                    d.get("vendor_name") or "",
                    d.get("bill_date") or "",
                    d.get("due_date") or "",
                    float(d.get("total") or 0),
                    bd,
                    d.get("status") or "",
                ]
            )
        self._fill_table(headers, rows, numeric_columns=frozenset({5, 6}))
        self._summary.setText(
            f"Open bills: {len(rows)} row(s), total balance due {tot_bal:,.2f}."
        )
        self._set_report_heading("Current report: Open bills")
        self._last_export = {
            "preamble": ["ProBooks+ai – Open bills (balance due > 0)"],
            "headers": headers,
            "rows": rows,
        }
        self._last_report_kind = "open_bill"

    def _show_recent_ar_payments(self) -> None:
        rows_raw = business.list_ar_payments(self._conn)[:100]
        headers = [
            "Payment id",
            "Payment date",
            "Customer",
            "Amount",
            "Method",
            "Reference",
            "Memo",
            "Bank account",
        ]
        rows = []
        for r in rows_raw:
            d = dict(r)
            rows.append(
                [
                    d.get("id"),
                    d.get("payment_date") or "",
                    d.get("customer_name") or "",
                    float(d.get("amount") or 0),
                    d.get("method") or "",
                    d.get("reference") or "",
                    d.get("memo") or "",
                    d.get("bank_account_name") or "",
                ]
            )
        self._fill_table(headers, rows, numeric_columns=frozenset({3}))
        self._summary.setText(f"Recent customer (AR) payments: {len(rows)} row(s), newest first.")
        self._set_report_heading("Current report: Recent customer payments")
        self._last_export = {
            "preamble": ["ProBooks+ai – Recent customer payments (newest first, up to 100)"],
            "headers": headers,
            "rows": rows,
        }
        self._last_report_kind = "ar_pay"

    def _show_recent_ap_payments(self) -> None:
        rows_raw = business.list_ap_payments(self._conn)[:100]
        headers = [
            "Payment id",
            "Payment date",
            "Vendor",
            "Amount",
            "Method",
            "Reference",
            "Memo",
            "Bank account",
        ]
        rows = []
        for r in rows_raw:
            d = dict(r)
            rows.append(
                [
                    d.get("id"),
                    d.get("payment_date") or "",
                    d.get("vendor_name") or "",
                    float(d.get("amount") or 0),
                    d.get("method") or "",
                    d.get("reference") or "",
                    d.get("memo") or "",
                    d.get("bank_account_name") or "",
                ]
            )
        self._fill_table(headers, rows, numeric_columns=frozenset({3}))
        self._summary.setText(f"Recent vendor (AP) payments: {len(rows)} row(s), newest first.")
        self._set_report_heading("Current report: Recent vendor payments")
        self._last_export = {
            "preamble": ["ProBooks+ai – Recent vendor payments (newest first, up to 100)"],
            "headers": headers,
            "rows": rows,
        }
        self._last_report_kind = "ap_pay"

    def _export_csv(self):
        if not self._last_export:
            message_box_information_ok(
                self,
                "Reports",
                "Run a report first (financial toolbar or Receivables & payables), then export.",
                ok_tip="Close; open a report, then use Export CSV again.",
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export report",
            "report.csv",
            "CSV (*.csv);;All Files (*.*)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            n = financial_reports.write_report_csv(
                path,
                self._last_export["headers"],
                self._last_export["rows"],
                preamble=self._last_export["preamble"],
            )
        except OSError as exc:
            message_box_critical_ok(
                self,
                "Export failed",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; check the path, permissions, and disk space.",
            )
            return
        message_box_information_ok(
            self,
            "Export complete",
            f"Exported {n} row(s) to:\n{escape_ampersand_for_qt(path)}",
            ok_tip="Close; open the CSV from the path shown." + CSV_EXPORT_OK_TIP_SUFFIX,
        )
