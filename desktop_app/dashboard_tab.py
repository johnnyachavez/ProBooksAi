"""
desktop_app.dashboard_tab
==========================
Home dashboard — live KPI cards showing the business health at a glance.

Cards
-----
  • Cash balance        – sum of all bank transaction amounts
  • AR Outstanding      – total balance_due on open/partial invoices
  • AP Outstanding      – total balance_due on open/partial bills
  • YTD Revenue         – income_statement revenue, Jan 1 → today
  • YTD Expenses        – income_statement expenses, Jan 1 → today
  • YTD Net Income      – revenue − expenses

Recent activity section: last 8 bank transactions.

Refreshes automatically every 60 seconds, or manually via the Refresh button.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop_app.theme import (
    WORKFLOW_ALT_ROW,
    WORKFLOW_CAPTION,
    WORKFLOW_GRID,
    WORKFLOW_HEADER_BG,
    WORKFLOW_PAGE_BG,
    WORKFLOW_PANEL_BG,
    WORKFLOW_TEXT,
)

# ---------------------------------------------------------------------------
# Colours for KPI cards
# ---------------------------------------------------------------------------
_GREEN = "#2E7D32"
_RED = "#C62828"
_BLUE = "#1565C0"
_AMBER = "#E65100"
_PURPLE = "#6A1B9A"
_TEAL = "#00695C"
_CARD_BG = "#1E2A3A"
_CARD_BORDER = "#2C3E55"


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _today() -> str:
    return date.today().isoformat()


def _year_start() -> str:
    return f"{date.today().year}-01-01"


def _fetch_kpis(conn: sqlite3.Connection) -> dict:
    """Return a dict of dashboard KPI values. Never raises — returns 0 on any error."""
    result = {
        "cash_balance": 0.0,
        "ar_outstanding": 0.0,
        "ap_outstanding": 0.0,
        "ytd_revenue": 0.0,
        "ytd_expenses": 0.0,
        "ytd_net": 0.0,
        "open_invoice_count": 0,
        "open_bill_count": 0,
        "overdue_invoice_count": 0,
        "overdue_bill_count": 0,
    }
    today = _today()
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM bank_transactions"
        ).fetchone()
        result["cash_balance"] = float(row[0] or 0)
    except Exception:
        pass

    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(balance_due), 0), COUNT(*) FROM invoices "
            "WHERE status IN ('open', 'partial')"
        ).fetchone()
        result["ar_outstanding"] = float(row[0] or 0)
        result["open_invoice_count"] = int(row[1] or 0)
    except Exception:
        pass

    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM invoices "
            "WHERE status IN ('open', 'partial') AND due_date != '' AND due_date < ?",
            (today,),
        ).fetchone()
        result["overdue_invoice_count"] = int(row[0] or 0)
    except Exception:
        pass

    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(balance_due), 0), COUNT(*) FROM bills "
            "WHERE status IN ('open', 'partial')"
        ).fetchone()
        result["ap_outstanding"] = float(row[0] or 0)
        result["open_bill_count"] = int(row[1] or 0)
    except Exception:
        pass

    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM bills "
            "WHERE status IN ('open', 'partial') AND due_date != '' AND due_date < ?",
            (today,),
        ).fetchone()
        result["overdue_bill_count"] = int(row[0] or 0)
    except Exception:
        pass

    try:
        from probooksai.financial_reports import income_statement
        pl = income_statement(conn, start_date=_year_start(), end_date=today)
        result["ytd_revenue"] = float(pl.get("revenue") or 0)
        result["ytd_expenses"] = float(pl.get("expenses") or 0)
        result["ytd_net"] = float(pl.get("net_income") or 0)
    except Exception:
        pass

    return result


def _fetch_recent_transactions(conn: sqlite3.Connection, limit: int = 8) -> list[dict]:
    """Return the most recent bank transactions across all accounts."""
    try:
        rows = conn.execute(
            """
            SELECT bt.txn_date, bt.description, bt.amount, bt.coa_account,
                   ba.name AS account_name
            FROM bank_transactions bt
            LEFT JOIN bank_accounts ba ON ba.id = bt.bank_account_id
            ORDER BY bt.txn_date DESC, bt.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# KPI Card widget
# ---------------------------------------------------------------------------

class _KPICard(QFrame):
    """A single KPI metric card with a label, big value, and optional sub-label."""

    def __init__(self, title: str, accent: str = _BLUE, parent=None):
        super().__init__(parent)
        self._accent = accent
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            f"QFrame {{ background: {_CARD_BG}; border: 1px solid {_CARD_BORDER}; "
            f"border-left: 4px solid {accent}; border-radius: 6px; }}"
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(100)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        self._lbl_title = QLabel(title)
        self._lbl_title.setStyleSheet(
            f"color: {WORKFLOW_CAPTION}; font-size: 11px; font-weight: 600; "
            "text-transform: uppercase; letter-spacing: 1px; border: none;"
        )
        layout.addWidget(self._lbl_title)

        self._lbl_value = QLabel("—")
        self._lbl_value.setStyleSheet(
            f"color: {WORKFLOW_TEXT}; font-size: 22px; font-weight: 700; border: none;"
        )
        layout.addWidget(self._lbl_value)

        self._lbl_sub = QLabel("")
        self._lbl_sub.setStyleSheet(
            f"color: {WORKFLOW_CAPTION}; font-size: 10px; border: none;"
        )
        layout.addWidget(self._lbl_sub)

    def set_value(self, value: str, sub: str = "", value_color: Optional[str] = None) -> None:
        self._lbl_value.setText(value)
        self._lbl_value.setStyleSheet(
            f"color: {value_color or WORKFLOW_TEXT}; font-size: 22px; "
            "font-weight: 700; border: none;"
        )
        self._lbl_sub.setText(sub)
        self._lbl_sub.setVisible(bool(sub))


# ---------------------------------------------------------------------------
# Dashboard tab
# ---------------------------------------------------------------------------

class DashboardTab(QWidget):
    """Home dashboard: KPI cards + recent transactions table."""

    # Emitted when the user wants to jump to the Invoices or Bills tab
    navigateRequested = Signal(str)  # "invoices" | "bills" | "register"

    _AUTO_REFRESH_MS = 60_000  # 1 minute

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._build_ui()
        self.refresh()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(self._AUTO_REFRESH_MS)

    def set_connection(self, conn: sqlite3.Connection) -> None:
        """Replace the DB connection (called when a new company file is opened)."""
        self._conn = conn
        self.refresh()

    # -- UI ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Scrollable content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: {WORKFLOW_PAGE_BG}; }}")
        outer.addWidget(scroll)

        content = QWidget()
        content.setStyleSheet(f"background: {WORKFLOW_PAGE_BG};")
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(16)

        # Header row
        hdr_row = QHBoxLayout()
        title_lbl = QLabel("Business Dashboard")
        title_lbl.setStyleSheet(
            f"font-size: 18px; font-weight: 700; color: {WORKFLOW_TEXT};"
        )
        hdr_row.addWidget(title_lbl)
        hdr_row.addStretch(1)

        self._lbl_updated = QLabel("")
        self._lbl_updated.setStyleSheet(f"color: {WORKFLOW_CAPTION}; font-size: 10px;")
        hdr_row.addWidget(self._lbl_updated)

        btn_refresh = QPushButton("↻ Refresh")
        btn_refresh.setToolTip("Reload all KPIs from the database now.")
        btn_refresh.clicked.connect(self.refresh)
        btn_refresh.setFixedWidth(90)
        hdr_row.addWidget(btn_refresh)
        layout.addLayout(hdr_row)

        # KPI grid — 3 columns
        grid = QGridLayout()
        grid.setSpacing(12)

        self._card_cash = _KPICard("Cash Balance", _TEAL)
        self._card_ar = _KPICard("AR Outstanding", _BLUE)
        self._card_ap = _KPICard("AP Outstanding", _AMBER)
        self._card_revenue = _KPICard("YTD Revenue", _GREEN)
        self._card_expenses = _KPICard("YTD Expenses", _RED)
        self._card_net = _KPICard("YTD Net Income", _PURPLE)

        grid.addWidget(self._card_cash, 0, 0)
        grid.addWidget(self._card_ar, 0, 1)
        grid.addWidget(self._card_ap, 0, 2)
        grid.addWidget(self._card_revenue, 1, 0)
        grid.addWidget(self._card_expenses, 1, 1)
        grid.addWidget(self._card_net, 1, 2)
        layout.addLayout(grid)

        # Quick-action row
        qa_row = QHBoxLayout()
        qa_row.setSpacing(10)
        for label, tip, signal_val in [
            ("View Invoices →", "Jump to the Invoices tab", "invoices"),
            ("View Bills →", "Jump to the Enter Bills tab", "bills"),
            ("Bank Register →", "Jump to the Bank Register tab", "register"),
        ]:
            btn = QPushButton(label)
            btn.setToolTip(tip)
            btn.setStyleSheet(
                f"QPushButton {{ background: {_CARD_BG}; color: {WORKFLOW_TEXT}; "
                f"border: 1px solid {_CARD_BORDER}; border-radius: 4px; padding: 6px 12px; }}"
                f"QPushButton:hover {{ border-color: #4A90D9; }}"
            )
            _sv = signal_val  # capture for lambda
            btn.clicked.connect(lambda checked=False, sv=_sv: self.navigateRequested.emit(sv))
            qa_row.addWidget(btn)
        qa_row.addStretch(1)
        layout.addLayout(qa_row)

        # Recent transactions
        recent_lbl = QLabel("Recent Transactions")
        recent_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {WORKFLOW_TEXT};"
        )
        layout.addWidget(recent_lbl)

        self._txn_table = QTableWidget(0, 5)
        self._txn_table.setHorizontalHeaderLabels(
            ["Date", "Account", "Description", "COA", "Amount"]
        )
        self._txn_table.verticalHeader().setVisible(False)
        self._txn_table.setAlternatingRowColors(True)
        self._txn_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._txn_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._txn_table.horizontalHeader().setStretchLastSection(False)
        self._txn_table.setColumnWidth(0, 90)
        self._txn_table.setColumnWidth(1, 130)
        self._txn_table.setColumnWidth(4, 100)
        self._txn_table.horizontalHeader().setSectionResizeMode(
            2, self._txn_table.horizontalHeader().ResizeMode.Stretch
        )
        self._txn_table.horizontalHeader().setSectionResizeMode(
            3, self._txn_table.horizontalHeader().ResizeMode.ResizeToContents
        )
        self._txn_table.setMaximumHeight(260)
        self._txn_table.setStyleSheet(
            f"QTableWidget {{ background: {WORKFLOW_PANEL_BG}; "
            f"alternate-background-color: {WORKFLOW_ALT_ROW}; color: {WORKFLOW_TEXT}; "
            f"gridline-color: {WORKFLOW_GRID}; border: 1px solid {WORKFLOW_GRID}; }}"
            f"QHeaderView::section {{ background: {WORKFLOW_HEADER_BG}; color: {WORKFLOW_TEXT}; "
            f"padding: 4px 6px; border: 1px solid {WORKFLOW_GRID}; font-weight: 600; }}"
        )
        layout.addWidget(self._txn_table)
        layout.addStretch(1)

    # -- Refresh -------------------------------------------------------------

    def refresh(self) -> None:
        """Reload all KPIs and the recent transactions table from the DB."""
        kpis = _fetch_kpis(self._conn)
        txns = _fetch_recent_transactions(self._conn)
        self._update_cards(kpis)
        self._update_txn_table(txns)
        self._lbl_updated.setText(f"Updated {date.today().isoformat()}")

    def _update_cards(self, kpis: dict) -> None:
        cash = kpis["cash_balance"]
        self._card_cash.set_value(
            f"${cash:,.2f}",
            sub="Total across all accounts",
            value_color=_GREEN if cash >= 0 else _RED,
        )

        ar = kpis["ar_outstanding"]
        n_inv = kpis["open_invoice_count"]
        overdue_inv = kpis["overdue_invoice_count"]
        sub_ar = f"{n_inv} open invoice(s)"
        if overdue_inv:
            sub_ar += f" · {overdue_inv} overdue"
        self._card_ar.set_value(
            f"${ar:,.2f}",
            sub=sub_ar,
            value_color=_RED if overdue_inv else WORKFLOW_TEXT,
        )

        ap = kpis["ap_outstanding"]
        n_bill = kpis["open_bill_count"]
        overdue_bill = kpis["overdue_bill_count"]
        sub_ap = f"{n_bill} open bill(s)"
        if overdue_bill:
            sub_ap += f" · {overdue_bill} overdue"
        self._card_ap.set_value(
            f"${ap:,.2f}",
            sub=sub_ap,
            value_color=_RED if overdue_bill else WORKFLOW_TEXT,
        )

        self._card_revenue.set_value(
            f"${kpis['ytd_revenue']:,.2f}",
            sub=f"Jan 1 – {_today()}",
        )
        self._card_expenses.set_value(
            f"${kpis['ytd_expenses']:,.2f}",
            sub=f"Jan 1 – {_today()}",
        )
        net = kpis["ytd_net"]
        self._card_net.set_value(
            f"${net:,.2f}",
            sub="Revenue − Expenses",
            value_color=_GREEN if net >= 0 else _RED,
        )

    def _update_txn_table(self, txns: list[dict]) -> None:
        self._txn_table.setRowCount(len(txns))
        for r, txn in enumerate(txns):
            amt = float(txn.get("amount") or 0)
            amt_str = f"${amt:,.2f}" if amt >= 0 else f"-${abs(amt):,.2f}"

            cells = [
                txn.get("txn_date") or "",
                txn.get("account_name") or "",
                txn.get("description") or "",
                txn.get("coa_account") or "",
                amt_str,
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if c == 4:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                    if amt < 0:
                        item.setForeground(
                            __import__("PySide6.QtGui", fromlist=["QColor"]).QColor(_RED)
                        )
                self._txn_table.setItem(r, c, item)
