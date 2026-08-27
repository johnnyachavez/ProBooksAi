"""
desktop_app.dashboard_tab
==========================
Company Home — QuickBooks Pro Desktop-style overview (money-in / money-out).

Four workflow panels (Vendors, Customers, Company, Banking) plus an account-balances
sidebar. Shortcuts open existing screens; this module does not rebuild invoices,
bills, payments, deposits, or checks.

Refreshes automatically every 60 seconds, or when the tab is shown.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from desktop_app.qt_mnemonic import escape_ampersand_for_qt
from probooksai import business

# Light canvas like Create Invoices / Enter Bills — captions sit on white, not a navy bar.
_HOME_CANVAS = "#E8ECF1"
_HOME_PAPER = "#FFFFFF"
_HOME_PANEL = "#F4F7FA"
_HOME_BORDER = "#C5CDD6"
_HOME_LINE = "#B8C0C8"
_HOME_CAPTION = "#4A5560"
_HOME_TEXT = "#1A1A1A"
_HOME_ACCENT = "#2563A8"
_HOME_TITLE = "#5B6770"
_HOME_HIGHLIGHT = "#C8E6C9"
_BADGE_RED = "#D32F2F"

_ICON_PX = 48


def _today() -> str:
    return date.today().isoformat()


def _year_start() -> str:
    return f"{date.today().year}-01-01"


def _light_home_palette() -> QPalette:
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(_HOME_CANVAS))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(_HOME_TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(_HOME_PAPER))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(_HOME_PANEL))
    pal.setColor(QPalette.ColorRole.Text, QColor(_HOME_TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(_HOME_PAPER))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(_HOME_TEXT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(_HOME_ACCENT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(_HOME_CAPTION))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(_HOME_PANEL))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(_HOME_TEXT))
    return pal


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _fetch_kpis(conn: sqlite3.Connection) -> dict:
    """Return Home sidebar figures. Never raises — returns 0 on any error."""
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
        "undeposited_count": 0,
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
            "WHERE lower(status) IN ('open', 'unpaid', 'partial', 'partially paid') "
            "AND COALESCE(balance_due, 0) > 0.005"
        ).fetchone()
        result["ar_outstanding"] = float(row[0] or 0)
        result["open_invoice_count"] = int(row[1] or 0)
    except Exception:
        pass

    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM invoices "
            "WHERE lower(status) IN ('open', 'unpaid', 'partial', 'partially paid') "
            "AND COALESCE(balance_due, 0) > 0.005 "
            "AND due_date != '' AND due_date < ?",
            (today,),
        ).fetchone()
        result["overdue_invoice_count"] = int(row[0] or 0)
    except Exception:
        pass

    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(balance_due), 0), COUNT(*) FROM bills "
            "WHERE lower(status) IN ('open', 'unpaid', 'partial', 'partially paid') "
            "AND COALESCE(balance_due, 0) > 0.005"
        ).fetchone()
        result["ap_outstanding"] = float(row[0] or 0)
        result["open_bill_count"] = int(row[1] or 0)
    except Exception:
        pass

    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM bills "
            "WHERE lower(status) IN ('open', 'unpaid', 'partial', 'partially paid') "
            "AND COALESCE(balance_due, 0) > 0.005 "
            "AND due_date != '' AND due_date < ?",
            (today,),
        ).fetchone()
        result["overdue_bill_count"] = int(row[0] or 0)
    except Exception:
        pass

    try:
        result["undeposited_count"] = len(business.list_undeposited_ar_payments(conn))
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


def _fetch_account_balances(conn: sqlite3.Connection) -> list[dict]:
    """Active bank accounts with running signed totals (empty list on error)."""
    try:
        rows = conn.execute(
            """
            SELECT ba.id, ba.name,
                   COALESCE(SUM(bt.amount), 0) AS balance
            FROM bank_accounts ba
            LEFT JOIN bank_transactions bt ON bt.bank_account_id = ba.id
            WHERE ba.is_active = 1
            GROUP BY ba.id
            ORDER BY ba.name COLLATE NOCASE
            """
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Icons + chrome
# ---------------------------------------------------------------------------

def _home_icon_pixmap(kind: str, size: int = _ICON_PX) -> QPixmap:
    """Simple colored pictogram — QB Home flavor, not a screenshot photocopy."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    m = size * 0.08
    box = QRectF(m, m, size - 2 * m, size - 2 * m)

    def _doc(fill: str, accent: str) -> None:
        p.setPen(QPen(QColor(accent), 1.4))
        p.setBrush(QColor(fill))
        path_r = QRectF(box.left() + 6, box.top() + 2, box.width() - 12, box.height() - 6)
        p.drawRoundedRect(path_r, 3, 3)
        p.setPen(QPen(QColor(accent), 1.2))
        y0 = path_r.top() + 8
        for i in range(3):
            y = y0 + i * 7
            p.drawLine(QPointF(path_r.left() + 6, y), QPointF(path_r.right() - 6, y))

    if kind == "invoice":
        _doc("#E8F1FA", "#2F6FAE")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#2F6FAE"))
        p.drawEllipse(QRectF(box.right() - 18, box.bottom() - 18, 14, 14))
    elif kind == "bills":
        p.setPen(QPen(QColor("#C49214"), 1.4))
        p.setBrush(QColor("#F6E7A8"))
        p.drawRoundedRect(box.adjusted(8, 4, -8, -4), 3, 3)
        p.setBrush(QColor("#E8B931"))
        p.drawRoundedRect(box.adjusted(4, 10, -12, -2), 3, 3)
        p.setPen(QPen(QColor("#8A6A10"), 1.2))
        y = box.center().y()
        p.drawLine(QPointF(box.left() + 10, y), QPointF(box.right() - 16, y))
    elif kind == "pay_bills":
        p.setPen(QPen(QColor("#2E7D32"), 1.4))
        p.setBrush(QColor("#C8E6C9"))
        p.drawEllipse(box.adjusted(4, 4, -4, -4))
        p.setPen(QPen(QColor("#1B5E20"), 2.0))
        p.drawText(box, int(Qt.AlignmentFlag.AlignCenter), "$")
    elif kind == "payments":
        p.setPen(QPen(QColor("#2E7D32"), 1.4))
        p.setBrush(QColor("#E8F5E9"))
        p.drawRoundedRect(box.adjusted(2, 10, -2, -10), 4, 4)
        p.setPen(QPen(QColor("#2E7D32"), 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        cx, cy = box.center().x(), box.center().y()
        p.drawLine(QPointF(cx - 10, cy), QPointF(cx - 2, cy + 7))
        p.drawLine(QPointF(cx - 2, cy + 7), QPointF(cx + 12, cy - 8))
    elif kind == "deposits":
        p.setPen(QPen(QColor("#8A6A10"), 1.4))
        p.setBrush(QColor("#F3D77A"))
        bag = QPolygonF(
            [
                QPointF(box.center().x() - 4, box.top() + 4),
                QPointF(box.center().x() + 4, box.top() + 4),
                QPointF(box.right() - 6, box.bottom() - 4),
                QPointF(box.left() + 6, box.bottom() - 4),
            ]
        )
        p.drawPolygon(bag)
        p.setPen(QPen(QColor("#8A6A10"), 1.6))
        p.drawLine(
            QPointF(box.center().x(), box.top() + 6),
            QPointF(box.center().x(), box.top() + 14),
        )
    elif kind == "checks":
        p.setPen(QPen(QColor("#5BA37A"), 1.4))
        p.setBrush(QColor("#E3F2E9"))
        p.drawRoundedRect(box.adjusted(0, 8, 0, -8), 4, 4)
        p.setPen(QPen(QColor("#3D8B4A"), 1.2))
        p.drawLine(
            QPointF(box.left() + 8, box.center().y() - 4),
            QPointF(box.right() - 8, box.center().y() - 4),
        )
        p.drawLine(
            QPointF(box.left() + 8, box.center().y() + 4),
            QPointF(box.center().x() + 4, box.center().y() + 4),
        )
    elif kind == "register":
        p.setPen(QPen(QColor("#2E7D32"), 1.4))
        p.setBrush(QColor("#E8F5E9"))
        p.drawRoundedRect(box.adjusted(4, 2, -4, -2), 3, 3)
        p.setPen(QPen(QColor("#2E7D32"), 1.1))
        for i in range(4):
            y = box.top() + 10 + i * 8
            p.drawLine(QPointF(box.left() + 10, y), QPointF(box.right() - 10, y))
    elif kind == "reconcile":
        p.setPen(QPen(QColor("#2563A8"), 1.4))
        p.setBrush(QColor("#E3EEF8"))
        p.drawRoundedRect(box.adjusted(6, 2, -6, -2), 3, 3)
        p.setPen(QPen(QColor("#2E7D32"), 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        cx, cy = box.center().x(), box.center().y() + 2
        p.drawLine(QPointF(cx - 8, cy), QPointF(cx - 2, cy + 6))
        p.drawLine(QPointF(cx - 2, cy + 6), QPointF(cx + 10, cy - 8))
    elif kind == "coa":
        p.setPen(QPen(QColor("#2563A8"), 1.4))
        p.setBrush(QColor("#E8F1FA"))
        p.drawRoundedRect(box.adjusted(4, 2, -4, -2), 3, 3)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#2563A8"))
        for i in range(3):
            y = box.top() + 10 + i * 11
            p.drawRect(QRectF(box.left() + 10, y, 6, 6))
            p.setPen(QPen(QColor("#2563A8"), 1.3))
            p.drawLine(QPointF(box.left() + 20, y + 3), QPointF(box.right() - 12, y + 3))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#2563A8"))
    else:  # items / codes
        p.setPen(QPen(QColor("#6A4C9A"), 1.4))
        p.setBrush(QColor("#EDE4F5"))
        p.drawRoundedRect(box.adjusted(8, 6, -8, -6), 4, 4)
        p.setPen(QPen(QColor("#6A4C9A"), 1.2))
        p.drawLine(
            QPointF(box.left() + 14, box.center().y()),
            QPointF(box.right() - 14, box.center().y()),
        )

    p.end()
    return pm


def _home_icon(kind: str) -> QIcon:
    return QIcon(_home_icon_pixmap(kind))


class _FlowArrow(QWidget):
    """Grey process arrow between Home shortcuts."""

    def __init__(self, direction: str = "right", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._direction = direction
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        if direction == "down":
            self.setFixedSize(18, 28)
        else:
            self.setFixedSize(40, 18)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event) -> None:  # noqa: ARG002
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(_HOME_LINE), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(QColor(_HOME_LINE))
        w, h = self.width(), self.height()
        if self._direction == "down":
            x = w / 2
            p.drawLine(QPointF(x, 1), QPointF(x, h - 9))
            tip = QPolygonF(
                [QPointF(x - 5, h - 10), QPointF(x, h - 1), QPointF(x + 5, h - 10)]
            )
            p.drawPolygon(tip)
        else:
            y = h / 2
            p.drawLine(QPointF(1, y), QPointF(w - 9, y))
            tip = QPolygonF(
                [QPointF(w - 10, y - 5), QPointF(w - 1, y), QPointF(w - 10, y + 5)]
            )
            p.drawPolygon(tip)
        p.end()


class _HomeShortcut(QToolButton):
    """Icon + caption tile. Caption is dark text on a light face (no navy redaction bar)."""

    def __init__(
        self,
        key: str,
        caption: str,
        kind: str,
        tooltip: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.nav_key = key
        self._badge = 0
        self.setObjectName(f"homeShortcut_{key}")
        self.setText(escape_ampersand_for_qt(caption))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setIcon(_home_icon(kind))
        self.setIconSize(QSize(_ICON_PX, _ICON_PX))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoRaise(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip(tooltip)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedWidth(122)
        self.setMinimumHeight(102)
        self.setStyleSheet(
            f"QToolButton {{ background: transparent; border: none; color: {_HOME_TEXT}; "
            f"font-size: 11px; padding: 4px 2px 6px 2px; }}"
            f"QToolButton:hover {{ background: #E8F1FA; border-radius: 6px; }}"
            f"QToolButton:pressed {{ background: #D0E6F4; border-radius: 6px; }}"
        )

    def set_badge(self, count: int) -> None:
        self._badge = max(0, int(count or 0))
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._badge <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        text = "99+" if self._badge > 99 else str(self._badge)
        br = QRectF(self.width() - 28, 4, 24, 16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(_BADGE_RED))
        p.drawRoundedRect(br, 8, 8)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(br, int(Qt.AlignmentFlag.AlignCenter), text)
        p.end()


class _HomeSection(QFrame):
    """White workflow box with a centered blue section title."""

    def __init__(self, title: str, object_name: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(_HOME_PAPER))
        pal.setColor(QPalette.ColorRole.WindowText, QColor(_HOME_TEXT))
        self.setPalette(pal)
        self.setStyleSheet(
            f"QFrame#{object_name} {{ background-color: {_HOME_PAPER}; "
            f"border: 1px solid {_HOME_BORDER}; border-radius: 4px; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 14)
        lay.setSpacing(8)

        badge = QLabel(title)
        badge.setObjectName("homeSectionBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedHeight(22)
        badge.setStyleSheet(
            f"QLabel#homeSectionBadge {{ color: {_HOME_ACCENT}; background: {_HOME_PAPER}; "
            f"border: 1px solid {_HOME_ACCENT}; border-radius: 2px; font-size: 11px; "
            f"font-weight: 700; letter-spacing: 0.14em; padding: 0 12px; }}"
        )
        badge.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        badge_row = QHBoxLayout()
        badge_row.setContentsMargins(0, 0, 0, 0)
        badge_row.addStretch(1)
        badge_row.addWidget(badge)
        badge_row.addStretch(1)
        lay.addLayout(badge_row)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 4, 0, 0)
        self.body.setSpacing(8)
        lay.addLayout(self.body, 1)


class _BalanceRow(QFrame):
    def __init__(self, name: str, amount: str, *, highlight: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("homeBalanceRow")
        bg = _HOME_HIGHLIGHT if highlight else _HOME_PAPER
        self.setStyleSheet(
            f"QFrame#homeBalanceRow {{ background: {bg}; border: none; border-radius: 2px; }}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(8)
        nm = QLabel(name)
        nm.setObjectName("homeBalanceName")
        nm.setStyleSheet(
            f"color: {_HOME_TEXT}; font-size: 11px; background: transparent; border: none;"
        )
        nm.setWordWrap(True)
        amt = QLabel(amount)
        amt.setObjectName("homeBalanceAmount")
        amt.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        amt.setStyleSheet(
            f"color: {_HOME_TEXT}; font-size: 11px; font-weight: 600; "
            "background: transparent; border: none;"
        )
        lay.addWidget(nm, 1)
        lay.addWidget(amt)


# ---------------------------------------------------------------------------
# Dashboard / Home tab
# ---------------------------------------------------------------------------

class DashboardTab(QWidget):
    """QB Pro-style Home: workflow shortcuts that open existing screens."""

    navigateRequested = Signal(str)

    _AUTO_REFRESH_MS = 60_000

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self.setObjectName("qbHomePage")
        self.setAutoFillBackground(True)
        self.setPalette(_light_home_palette())
        self.setStyleSheet(f"QWidget#qbHomePage {{ background: {_HOME_CANVAS}; }}")
        self.setToolTip(
            "Home: company overview with Create Invoices, Receive Payments, Enter Bills, "
            "Pay Bills, Write Checks, and Make Deposits. Same company .db as other tabs "
            "(File → Backup / Restore, probooks.backup)."
        )
        self._build_ui()
        self.refresh()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(self._AUTO_REFRESH_MS)

    def set_connection(self, conn: sqlite3.Connection) -> None:
        """Replace the DB connection (called when a new company file is opened)."""
        self._conn = conn
        self.refresh()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()

    def _shortcut(
        self, key: str, caption: str, kind: str, tooltip: str
    ) -> _HomeShortcut:
        btn = _HomeShortcut(key, caption, kind, tooltip, self)
        btn.clicked.connect(lambda checked=False, k=key: self.navigateRequested.emit(k))
        return btn

    def _build_ui(self) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: {_HOME_CANVAS}; border: none; }}"
        )
        outer.addWidget(scroll, 1)

        content = QWidget()
        content.setObjectName("qbHomeCanvas")
        content.setAutoFillBackground(True)
        pal = content.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(_HOME_CANVAS))
        content.setPalette(pal)
        content.setStyleSheet(f"QWidget#qbHomeCanvas {{ background: {_HOME_CANVAS}; }}")
        scroll.setWidget(content)

        board = QVBoxLayout(content)
        board.setContentsMargins(16, 14, 12, 16)
        board.setSpacing(12)

        title = QLabel("Home")
        title.setObjectName("homePageTitle")
        title.setStyleSheet(
            f"color: {_HOME_TITLE}; font-size: 16px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        board.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(12)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 3)

        vendors = _HomeSection("VENDORS", "homeSectionVendors")
        v_row = QHBoxLayout()
        v_row.setSpacing(4)
        v_row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._btn_bills = self._shortcut(
            "bills",
            "Enter Bills",
            "bills",
            "Open Enter Bills to record a vendor bill.",
        )
        self._btn_pay_bills = self._shortcut(
            "pay_bills",
            "Pay Bills",
            "pay_bills",
            "Open Pay Bills to pay open vendor bills.",
        )
        v_row.addWidget(self._btn_bills)
        v_row.addWidget(_FlowArrow("right"))
        v_row.addWidget(self._btn_pay_bills)
        v_row.addStretch(1)
        vendors.body.addLayout(v_row)
        down_wrap = QHBoxLayout()
        down_wrap.addSpacing(46)
        down_wrap.addWidget(_FlowArrow("down"))
        down_wrap.addStretch(1)
        vendors.body.addLayout(down_wrap)
        vendors.body.addStretch(1)
        grid.addWidget(vendors, 0, 0)

        company = _HomeSection("COMPANY", "homeSectionCompany")
        c_row = QHBoxLayout()
        c_row.setSpacing(8)
        c_row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._btn_coa = self._shortcut(
            "coa",
            "Chart of\nAccounts",
            "coa",
            "Open Chart of Accounts.",
        )
        self._btn_codes = self._shortcut(
            "codes",
            "Items &\nServices",
            "items",
            "Open Item List (invoice items and services).",
        )
        c_row.addWidget(self._btn_coa)
        c_row.addWidget(self._btn_codes)
        c_row.addStretch(1)
        company.body.addLayout(c_row)
        company.body.addStretch(1)
        grid.addWidget(company, 0, 1)

        customers = _HomeSection("CUSTOMERS", "homeSectionCustomers")
        cust_row = QHBoxLayout()
        cust_row.setSpacing(4)
        cust_row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._btn_invoices = self._shortcut(
            "invoices",
            "Create\nInvoices",
            "invoice",
            "Open Create Invoices.",
        )
        self._btn_payments = self._shortcut(
            "payments",
            "Receive\nPayments",
            "payments",
            "Open Receive Payments (Customer Payment).",
        )
        cust_row.addWidget(self._btn_invoices)
        cust_row.addWidget(_FlowArrow("right"))
        cust_row.addWidget(self._btn_payments)
        cust_row.addWidget(_FlowArrow("right"))
        cust_row.addStretch(1)
        customers.body.addLayout(cust_row)
        customers.body.addStretch(1)
        grid.addWidget(customers, 1, 0)

        banking = _HomeSection("BANKING", "homeSectionBanking")
        b_grid = QGridLayout()
        b_grid.setHorizontalSpacing(8)
        b_grid.setVerticalSpacing(8)
        self._btn_deposits = self._shortcut(
            "deposits",
            "Record\nDeposits",
            "deposits",
            "Open Make Deposits (Payments to Deposit).",
        )
        self._btn_reconcile = self._shortcut(
            "reconcile",
            "Reconcile",
            "reconcile",
            "Open Reconcile (bank statements).",
        )
        self._btn_checks = self._shortcut(
            "checks",
            "Write\nChecks",
            "checks",
            "Open Write Checks.",
        )
        self._btn_register = self._shortcut(
            "register",
            "Check\nRegister",
            "register",
            "Open Bank Register.",
        )
        b_grid.addWidget(self._btn_deposits, 0, 0)
        b_grid.addWidget(self._btn_reconcile, 0, 1)
        b_grid.addWidget(self._btn_checks, 1, 0)
        b_grid.addWidget(self._btn_register, 1, 1)
        banking.body.addLayout(b_grid)
        banking.body.addStretch(1)
        grid.addWidget(banking, 1, 1)

        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 2)
        board.addLayout(grid, 1)

        outer.addWidget(self._build_sidebar())

    def _build_sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("homeSidebar")
        side.setFixedWidth(240)
        side.setAutoFillBackground(True)
        pal = side.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(_HOME_PANEL))
        side.setPalette(pal)
        side.setStyleSheet(
            f"QFrame#homeSidebar {{ background: {_HOME_PANEL}; border: none; "
            f"border-left: 1px solid {_HOME_BORDER}; }}"
        )
        lay = QVBoxLayout(side)
        lay.setContentsMargins(12, 14, 12, 14)
        lay.setSpacing(10)

        company_lbl = QLabel("COMPANY NAME")
        company_lbl.setObjectName("homeCompanyPlaceholder")
        company_lbl.setStyleSheet(
            f"color: {_HOME_CAPTION}; font-size: 10px; font-weight: 700; "
            "letter-spacing: 0.08em; background: transparent; border: none;"
        )
        lay.addWidget(company_lbl)

        bal_box = QFrame()
        bal_box.setObjectName("homeBalancesPanel")
        bal_box.setStyleSheet(
            f"QFrame#homeBalancesPanel {{ background: {_HOME_PAPER}; "
            f"border: 1px solid {_HOME_BORDER}; border-radius: 4px; }}"
        )
        bal_lay = QVBoxLayout(bal_box)
        bal_lay.setContentsMargins(8, 8, 8, 8)
        bal_lay.setSpacing(4)
        hdr = QLabel("Account Balances")
        hdr.setObjectName("homeBalancesHeader")
        hdr.setStyleSheet(
            f"color: {_HOME_ACCENT}; font-size: 12px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        bal_lay.addWidget(hdr)
        self._balances_host = QVBoxLayout()
        self._balances_host.setContentsMargins(0, 4, 0, 0)
        self._balances_host.setSpacing(2)
        bal_lay.addLayout(self._balances_host)
        lay.addWidget(bal_box)

        backup_box = QFrame()
        backup_box.setObjectName("homeBackupPanel")
        backup_box.setStyleSheet(
            f"QFrame#homeBackupPanel {{ background: {_HOME_PAPER}; "
            f"border: 1px solid {_HOME_BORDER}; border-radius: 4px; }}"
        )
        bk = QVBoxLayout(backup_box)
        bk.setContentsMargins(8, 8, 8, 8)
        bk.setSpacing(4)
        bk_hdr = QLabel("Backup Status")
        bk_hdr.setObjectName("homeBackupHeader")
        bk_hdr.setStyleSheet(
            f"color: {_HOME_ACCENT}; font-size: 12px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        bk.addWidget(bk_hdr)
        bk_body = QLabel("Local  File → Backup\nOnline  not configured")
        bk_body.setObjectName("homeBackupBody")
        bk_body.setWordWrap(True)
        bk_body.setStyleSheet(
            f"color: {_HOME_CAPTION}; font-size: 11px; background: transparent; border: none;"
        )
        bk.addWidget(bk_body)
        lay.addWidget(backup_box)

        self._lbl_updated = QLabel("")
        self._lbl_updated.setObjectName("homeUpdatedLabel")
        self._lbl_updated.setStyleSheet(
            f"color: {_HOME_CAPTION}; font-size: 10px; background: transparent; border: none;"
        )
        lay.addWidget(self._lbl_updated)
        lay.addStretch(1)
        return side

    def refresh(self) -> None:
        """Reload sidebar balances and the undeposited badge from the DB."""
        kpis = _fetch_kpis(self._conn)
        accounts = _fetch_account_balances(self._conn)
        self._update_sidebar(kpis, accounts)
        if hasattr(self, "_btn_deposits"):
            self._btn_deposits.set_badge(int(kpis.get("undeposited_count") or 0))
        self._lbl_updated.setText(f"Updated {_today()}")

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _update_sidebar(self, kpis: dict, accounts: list[dict]) -> None:
        self._clear_layout(self._balances_host)
        ar = float(kpis.get("ar_outstanding") or 0)
        ap = float(kpis.get("ap_outstanding") or 0)
        undeposited = int(kpis.get("undeposited_count") or 0)
        self._balances_host.addWidget(
            _BalanceRow("Accounts Receivable", f"${ar:,.2f}")
        )
        self._balances_host.addWidget(
            _BalanceRow("Accounts Payable", f"${ap:,.2f}")
        )
        if undeposited:
            self._balances_host.addWidget(
                _BalanceRow("Undeposited Funds", f"{undeposited} payment(s)")
            )
        first_bank = True
        for acct in accounts:
            name = str(acct.get("name") or "Bank").strip() or "Bank"
            bal = float(acct.get("balance") or 0)
            self._balances_host.addWidget(
                _BalanceRow(name, f"${bal:,.2f}", highlight=first_bank)
            )
            first_bank = False
        if not accounts:
            empty = QLabel("No bank accounts yet")
            empty.setStyleSheet(
                f"color: {_HOME_CAPTION}; font-size: 11px; background: transparent; border: none;"
            )
            self._balances_host.addWidget(empty)
