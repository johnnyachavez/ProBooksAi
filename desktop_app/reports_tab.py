"""Financial reports: trial balance, P&L, balance sheet (Phase 5).

**F5** (when this tab or its children have focus) re-runs the last report you opened
(Trial Balance, Income Statement, or Balance Sheet), if any.
"""

from __future__ import annotations

import sqlite3
from functools import partial
from typing import Literal, Optional

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
    QMessageBox,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from desktop_app.qt_mnemonic import escape_ampersand_for_qt
from desktop_app.table_clipboard import (
    FloatSortTableItem,
    copy_table_row_as_tsv,
    plain_display_table_item,
)
from probooksai import financial_reports


class ReportsTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._last_export: dict | None = None
        self._last_report_kind: Optional[Literal["tb", "pl", "bs"]] = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        filt = QGroupBox("Date range (ISO yyyy-mm-dd, optional)")
        fl = QFormLayout(filt)
        self._start = QLineEdit()
        self._end = QLineEdit()
        fl.addRow("Start", self._start)
        fl.addRow("End", self._end)
        layout.addWidget(filt)

        row = QHBoxLayout()
        for label, fn in (
            ("Trial Balance", self._show_tb),
            ("Income Statement", self._show_pl),
            ("Balance Sheet", self._show_bs),
        ):
            b = QPushButton(label)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addWidget(QPushButton("Export CSV…", clicked=self._export_csv))
        row.addStretch()
        layout.addLayout(row)

        self._table = QTableWidget()
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_report_context_menu)
        self._table.setSortingEnabled(True)
        layout.addWidget(self._table)

        self._summary = QLabel("")
        self._summary.setWordWrap(True)
        layout.addWidget(self._summary)

        tip = QLabel(
            "F5 re-runs the last Trial Balance, Income Statement, or Balance Sheet you ran (if any)."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #A0A0B0; font-size: 11px;")
        layout.addWidget(tip)

        sc_f5 = QShortcut(QKeySequence("F5"), self)
        sc_f5.setContext(Qt.WidgetWithChildrenShortcut)
        sc_f5.activated.connect(self._rerun_last_report)

    def _rerun_last_report(self) -> None:
        if self._last_report_kind == "tb":
            self._show_tb()
        elif self._last_report_kind == "pl":
            self._show_pl()
        elif self._last_report_kind == "bs":
            self._show_bs()

    def _on_report_context_menu(self, pos):
        idx = self._table.indexAt(pos)
        if not idx.isValid():
            return
        row = idx.row()
        m = QMenu(self)
        m.addAction("Copy row", partial(copy_table_row_as_tsv, self._table, row))
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
        start = self._start.text().strip() or None
        end = self._end.text().strip() or None
        data = financial_reports.trial_balance_report(self._conn, start, end)
        rows = [[d["account"], d["total_debit"], d["total_credit"], d["net"]] for d in data]
        headers = ["Account", "Debit", "Credit", "Net (D−C)"]
        self._fill_table(headers, rows, numeric_columns=frozenset({1, 2, 3}))
        self._summary.setText(f"{len(data)} account(s) with activity.")
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
        start = self._start.text().strip()
        end = self._end.text().strip()
        if not start or not end:
            self._last_export = None
            self._last_report_kind = None
            self._summary.setText(
                escape_ampersand_for_qt("Enter start and end dates for P&L.")
            )
            return
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
        end = self._end.text().strip() or self._start.text().strip() or None
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
        self._last_export = {
            "preamble": [
                "ProBooks+ai – Balance sheet summary",
                f"As of: {end or '(all posted activity)'}",
            ],
            "headers": headers,
            "rows": table_rows,
        }
        self._last_report_kind = "bs"

    def _export_csv(self):
        if not self._last_export:
            QMessageBox.information(
                self,
                "Reports",
                "Run Trial Balance, Income Statement, or Balance Sheet first, then export.",
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
            QMessageBox.critical(
                self, "Export failed", escape_ampersand_for_qt(str(exc))
            )
            return
        QMessageBox.information(
            self,
            "Export complete",
            f"Exported {n} row(s) to:\n{escape_ampersand_for_qt(path)}",
        )
