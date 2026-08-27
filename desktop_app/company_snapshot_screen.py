"""Company Snapshot — QuickBooks Pro Desktop-style widget dashboard.

Company / Payments / Customer views. Charts and tables use live company-file
data (invoices, bills, bank, GL). Slightly cleaner spacing than a gray Win32
photocopy; not QuickBooks Online.

Home → Company Snapshot opens this screen. Click a customer in Who Owe Money
to open Customer Center; Receive Payments and Chart of Accounts links jump to
those existing screens.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import date
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, QSettings, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPalette, QPen, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from desktop_app.flexible_date import format_iso_to_us_display
from desktop_app.qt_mnemonic import (
    escape_ampersand_for_qt,
    message_box_information_ok,
    tip_qdialog_button_box,
)
from desktop_app.table_clipboard import FloatSortTableItem, plain_display_table_item
from probooksai import qb_snapshot as snap

_SNAP_CANVAS = "#E8ECF1"
_SNAP_PAPER = "#FFFFFF"
_SNAP_PANEL = "#F4F7FA"
_SNAP_GRID = "#C5CDD6"
_SNAP_TEXT = "#1A1A1A"
_SNAP_CAPTION = "#4A5560"
_SNAP_TITLE = "#5B6770"
_SNAP_ACCENT = "#2563A8"
_SNAP_HEADER = "#5B7394"
_SNAP_LINK = "#1565C0"
_SNAP_OVERDUE = "#C62828"
_SNAP_INCOME = "#43A047"
_SNAP_EXPENSE = "#D2693A"
_SNAP_PRIOR_INCOME = "#5B8DB8"
_SNAP_CUR_INCOME = "#43A047"
_SNAP_PRIOR_EXPENSE = "#E0A040"
_SNAP_CUR_EXPENSE = "#B42318"
_STRIP_BTN = "#B4BCC6"
_ROLE_ID = Qt.ItemDataRole.UserRole

_PIE_COLORS = ("#C62828", "#EF6C00", "#F9A825", "#F5D0A9", "#8D6E63", "#78909C", "#6D4C41")

_DEFAULT_WIDGETS = (
    "income_expense",
    "prev_income",
    "customers_owe",
    "account_balances",
    "top_customers",
    "prev_expense",
    "expense_pie",
)

_WIDGET_TITLES = {
    "income_expense": "Income and Expense Trend",
    "prev_income": "Prev Year Income Comparison",
    "customers_owe": "Customers Who Owe Money",
    "account_balances": "Account Balances",
    "top_customers": "Top Customers by Sales",
    "prev_expense": "Prev Year Expense Comparison",
    "expense_pie": "Expense Breakdown",
}

_HIDDEN_SETTINGS_KEY = "company_snapshot/hidden_widgets"
_ACCOUNTS_SETTINGS_KEY = "company_snapshot/selected_accounts"


def _light_palette() -> QPalette:
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(_SNAP_CANVAS))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(_SNAP_TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(_SNAP_PAPER))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(_SNAP_PANEL))
    pal.setColor(QPalette.ColorRole.Text, QColor(_SNAP_TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(_SNAP_PAPER))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(_SNAP_TEXT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(_SNAP_ACCENT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(_SNAP_CAPTION))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(_SNAP_PANEL))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(_SNAP_TEXT))
    return pal


def _combo_qss() -> str:
    return (
        f"QComboBox {{ background: {_SNAP_PAPER}; border: 1px solid {_SNAP_GRID}; "
        f"padding: 1px 6px; color: {_SNAP_TEXT}; min-height: 20px; font-size: 11px; }}"
    )


def _link_qss() -> str:
    return (
        f"QPushButton {{ background: transparent; border: none; color: {_SNAP_LINK}; "
        "font-size: 11px; text-decoration: underline; padding: 0px; }}"
        f"QPushButton:hover {{ color: {_SNAP_ACCENT}; }}"
    )


def _fmt_money(value: float) -> str:
    return f"${float(value or 0):,.2f}"


def _nice_max(value: float) -> float:
    v = max(0.0, float(value or 0))
    if v <= 0:
        return 1.0
    import math

    exp = math.floor(math.log10(v))
    base = 10 ** exp
    for m in (1, 2, 5, 10):
        if v <= m * base:
            return float(m * base)
    return float(10 * base)


# ---------------------------------------------------------------------------
# Charts (QPainter — no QtCharts dependency)
# ---------------------------------------------------------------------------


class _BarChart(QWidget):
    """Vertical bars. *series* is a list of (label, color, values aligned to categories)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._categories: list[str] = []
        self._series: list[tuple[str, str, list[float]]] = []
        self._y_caption = "$"
        self.setMinimumHeight(140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(
        self,
        categories: list[str],
        series: list[tuple[str, str, list[float]]],
        *,
        y_caption: str = "$",
    ) -> None:
        self._categories = list(categories)
        self._series = list(series)
        self._y_caption = y_caption
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ARG002
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(_SNAP_PAPER))
        left, top, right, bottom = 44, 8, 10, 36
        plot = QRectF(left, top, max(10, w - left - right), max(10, h - top - bottom))
        p.setPen(QPen(QColor(_SNAP_CAPTION), 1))
        p.drawLine(plot.bottomLeft(), plot.bottomRight())
        p.drawLine(plot.bottomLeft(), plot.topLeft())
        vals: list[float] = []
        for _lab, _col, numbers in self._series:
            vals.extend(float(n or 0) for n in numbers)
        peak = _nice_max(max(vals) if vals else 0.0)
        scale_div = 1000.0 if peak >= 1000 else 1.0
        unit = "$ in 1000s" if scale_div == 1000.0 else (self._y_caption or "$")
        p.setPen(QColor(_SNAP_CAPTION))
        font = p.font()
        font.setPointSize(8)
        p.setFont(font)
        p.drawText(QRectF(2, 2, 42, 16), int(Qt.AlignmentFlag.AlignLeft), unit)
        for frac in (0.0, 0.5, 1.0):
            y = plot.bottom() - frac * plot.height()
            label = f"{int(round(peak * frac / scale_div))}"
            p.setPen(QPen(QColor("#E2E8EE"), 1))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor(_SNAP_CAPTION))
            p.drawText(
                QRectF(2, y - 8, 40, 16),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                label,
            )
        cats = self._categories
        n = max(1, len(cats))
        group_w = plot.width() / n
        series_n = max(1, len(self._series))
        bar_w = max(4.0, (group_w * 0.7) / series_n)
        if not vals or max(vals) <= 0.005:
            p.setPen(QColor(_SNAP_CAPTION))
            p.drawText(plot, int(Qt.AlignmentFlag.AlignCenter), "No activity in this period")
        else:
            for si, (_lab, color, numbers) in enumerate(self._series):
                for ci, cat in enumerate(cats):
                    amt = float(numbers[ci] if ci < len(numbers) else 0)
                    bh = 0.0 if peak <= 0 else (amt / peak) * (plot.height() - 2)
                    x = plot.left() + ci * group_w + (group_w - series_n * bar_w) / 2 + si * bar_w
                    y = plot.bottom() - bh
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor(color))
                    p.drawRect(QRectF(x, y, bar_w - 1.5, max(0.0, bh)))
        p.setPen(QColor(_SNAP_CAPTION))
        for ci, cat in enumerate(cats):
            p.drawText(
                QRectF(plot.left() + ci * group_w, plot.bottom() + 2, group_w, 16),
                int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                cat,
            )
        legend_y = h - 16
        lx = left
        p.setFont(font)
        for lab, color, _nums in self._series:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            p.drawRect(QRectF(lx, legend_y, 10, 10))
            p.setPen(QColor(_SNAP_TEXT))
            p.drawText(QRectF(lx + 14, legend_y - 3, 90, 16), int(Qt.AlignmentFlag.AlignLeft), lab)
            lx += 110
        p.end()


class _HBarChart(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._rows: list[tuple[str, float]] = []
        self._color = _SNAP_PRIOR_INCOME
        self.setMinimumHeight(140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, rows: list[tuple[str, float]], *, color: str = _SNAP_PRIOR_INCOME) -> None:
        self._rows = list(rows)
        self._color = color
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ARG002
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(_SNAP_PAPER))
        left, top, right, bottom = 108, 8, 12, 22
        plot = QRectF(left, top, max(10, w - left - right), max(10, h - top - bottom))
        font = p.font()
        font.setPointSize(8)
        p.setFont(font)
        if not self._rows:
            p.setPen(QColor(_SNAP_CAPTION))
            p.drawText(plot, int(Qt.AlignmentFlag.AlignCenter), "No sales in this period")
            p.end()
            return
        peak = _nice_max(max(v for _n, v in self._rows))
        scale_div = 1000.0 if peak >= 1000 else 1.0
        n = len(self._rows)
        row_h = plot.height() / max(1, n)
        bar_h = max(8.0, min(18.0, row_h * 0.55))
        for i, (name, amt) in enumerate(self._rows):
            y = plot.top() + i * row_h + (row_h - bar_h) / 2
            bw = 0.0 if peak <= 0 else (amt / peak) * plot.width()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(self._color))
            p.drawRect(QRectF(plot.left(), y, max(0.0, bw), bar_h))
            p.setPen(QColor(_SNAP_TEXT))
            label = name if len(name) <= 16 else name[:15] + "…"
            p.drawText(
                QRectF(4, y - 2, left - 8, bar_h + 4),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                label,
            )
        p.setPen(QColor(_SNAP_CAPTION))
        unit = "Sales Volume ($ in 1000s)" if scale_div == 1000.0 else "Sales Volume"
        p.drawText(
            QRectF(left, h - 18, plot.width(), 16),
            int(Qt.AlignmentFlag.AlignHCenter),
            unit,
        )
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self._color))
        p.drawRect(QRectF(left, h - 16, 10, 10))
        p.setPen(QColor(_SNAP_TEXT))
        p.drawText(QRectF(left + 14, h - 19, 80, 16), int(Qt.AlignmentFlag.AlignLeft), "Sales Volume")
        p.end()


class _PieChart(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._slices: list[tuple[str, float]] = []
        self.setMinimumHeight(140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, slices: list[tuple[str, float]]) -> None:
        self._slices = list(slices)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ARG002
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor(_SNAP_PAPER))
        total = sum(v for _l, v in self._slices)
        legend_w = min(180, max(110, int(w * 0.38)))
        size = max(20, min(h - 16, w - legend_w - 20))
        pie = QRectF(12, (h - size) / 2, size, size)
        font = p.font()
        font.setPointSize(8)
        p.setFont(font)
        if total <= 0.005 or not self._slices:
            p.setPen(QColor(_SNAP_CAPTION))
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), "No expenses in this period")
            p.end()
            return
        start = 90.0 * 16
        for i, (_lab, amt) in enumerate(self._slices):
            span = int(round((amt / total) * 360 * 16))
            p.setPen(QPen(QColor(_SNAP_PAPER), 1.5))
            p.setBrush(QColor(_PIE_COLORS[i % len(_PIE_COLORS)]))
            p.drawPie(pie, int(start), span)
            start -= span
        lx = pie.right() + 12
        ly = 10
        for i, (lab, amt) in enumerate(self._slices):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(_PIE_COLORS[i % len(_PIE_COLORS)]))
            p.drawRect(QRectF(lx, ly + 2, 10, 10))
            p.setPen(QColor(_SNAP_TEXT))
            name = lab if len(lab) <= 22 else lab[:21] + "…"
            p.drawText(
                QRectF(lx + 16, ly, legend_w - 20, 16),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                name,
            )
            ly += 18
        p.end()


# ---------------------------------------------------------------------------
# Widget chrome
# ---------------------------------------------------------------------------


class _SnapshotWidget(QFrame):
    closed = Signal(str)
    toggled = Signal(str, bool)

    def __init__(self, key: str, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.widget_key = key
        self.setObjectName(f"snapshotWidget_{key}")
        self.setStyleSheet(
            f"QFrame#snapshotWidget_{key} {{ background: {_SNAP_PAPER}; "
            f"border: 1px solid {_SNAP_GRID}; border-radius: 3px; }}"
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        header = QFrame()
        header.setObjectName(f"snapshotHeader_{key}")
        header.setFixedHeight(26)
        header.setStyleSheet(
            f"QFrame#snapshotHeader_{key} {{ background: {_SNAP_HEADER}; border: none; "
            "border-top-left-radius: 3px; border-top-right-radius: 3px; }"
        )
        h = QHBoxLayout(header)
        h.setContentsMargins(8, 0, 4, 0)
        h.setSpacing(4)
        self._title = QLabel(title)
        self._title.setObjectName(f"snapshotTitle_{key}")
        self._title.setStyleSheet(
            "color: #FFFFFF; font-size: 12px; font-weight: 700; background: transparent;"
        )
        h.addWidget(self._title, 1)
        self.period = QComboBox()
        self.period.setObjectName(f"snapshotPeriod_{key}")
        self.period.addItems(list(snap.PERIOD_CHOICES))
        self.period.setCurrentText(snap.PERIOD_YTD)
        self.period.setStyleSheet(_combo_qss())
        self.period.setVisible(False)
        h.addWidget(self.period)
        self._extra_host = QHBoxLayout()
        self._extra_host.setContentsMargins(0, 0, 0, 0)
        h.addLayout(self._extra_host)
        self._collapse = QToolButton()
        self._collapse.setObjectName(f"snapshotCollapse_{key}")
        self._collapse.setText("▾")
        self._collapse.setAutoRaise(True)
        self._collapse.setCursor(Qt.CursorShape.PointingHandCursor)
        self._collapse.setStyleSheet(
            "QToolButton { color: #FFFFFF; background: transparent; border: none; font-size: 12px; }"
        )
        self._collapse.setToolTip("Collapse or expand this content.")
        self._collapse.clicked.connect(self._toggle)
        h.addWidget(self._collapse)
        close_btn = QToolButton()
        close_btn.setObjectName(f"snapshotClose_{key}")
        close_btn.setText("×")
        close_btn.setAutoRaise(True)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            "QToolButton { color: #FFFFFF; background: transparent; border: none; font-size: 14px; }"
        )
        close_btn.setToolTip("Remove this content from the page. Use Add Content to bring it back.")
        close_btn.clicked.connect(lambda: self.closed.emit(self.widget_key))
        h.addWidget(close_btn)
        lay.addWidget(header)

        self.body = QWidget()
        self.body.setObjectName(f"snapshotBody_{key}")
        self.body.setStyleSheet(f"background: {_SNAP_PAPER};")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(8, 6, 8, 6)
        self.body_layout.setSpacing(4)
        lay.addWidget(self.body, 1)
        self._collapsed = False

    def add_header_widget(self, widget: QWidget) -> None:
        self._extra_host.addWidget(widget)

    def _toggle(self) -> None:
        self._collapsed = not self._collapsed
        self.body.setVisible(not self._collapsed)
        self._collapse.setText("▸" if self._collapsed else "▾")
        self.toggled.emit(self.widget_key, self._collapsed)

    def set_collapsed(self, collapsed: bool) -> None:
        if bool(collapsed) != self._collapsed:
            self._toggle()


class _MoneyTable(QTableWidget):
    def __init__(self, headers: tuple[str, ...], parent: Optional[QWidget] = None) -> None:
        super().__init__(0, len(headers), parent)
        self.setHorizontalHeaderLabels(list(headers))
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)
        hdr = self.horizontalHeader()
        hdr.setStretchLastSection(True)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.setStyleSheet(
            f"QTableWidget {{ background: {_SNAP_PAPER}; color: {_SNAP_TEXT}; "
            f"alternate-background-color: {_SNAP_PANEL}; border: none; font-size: 11px; }}"
            "QHeaderView::section { background: #EEF2F6; color: #4A5560; font-size: 10px; "
            "font-weight: 700; border: none; padding: 3px 6px; }"
        )


# ---------------------------------------------------------------------------
# Screen
# ---------------------------------------------------------------------------


class CompanySnapshotScreen(QWidget):
    """QB Pro Company Snapshot: widget grid over live company-file totals."""

    navigateRequested = Signal(str)
    openCustomerRequested = Signal(int)
    receivePaymentsRequested = Signal(int)

    def __init__(
        self,
        ap_conn: Optional[sqlite3.Connection] = None,
        parent: Optional[QWidget] = None,
        *,
        today: Optional[date] = None,
    ) -> None:
        super().__init__(parent)
        self._conn = ap_conn
        self._today = today or date.today()
        self._hidden: set[str] = set()
        self._selected_accounts: Optional[set[str]] = None
        self._last_owe_customer_id = 0
        self.setObjectName("companySnapshotPage")
        self.setAutoFillBackground(True)
        self.setPalette(_light_palette())
        self.setStyleSheet(f"QWidget#companySnapshotPage {{ background: {_SNAP_CANVAS}; }}")
        self.setToolTip(
            "Company Snapshot: income, expenses, customers who owe money, and account balances "
            "from the open company file. Same company .db (File → Backup / Restore, probooks.backup)."
        )
        self._load_settings()
        self._build_ui()
        self.reload()

    def set_connection(self, conn: Optional[sqlite3.Connection]) -> None:
        self._conn = conn
        self.reload()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self.reload()

    def _load_settings(self) -> None:
        raw = QSettings().value(_HIDDEN_SETTINGS_KEY, [])
        if isinstance(raw, str):
            raw = [raw] if raw else []
        self._hidden = {str(x) for x in (raw or []) if str(x) in _WIDGET_TITLES}
        acc = QSettings().value(_ACCOUNTS_SETTINGS_KEY, None)
        if acc is None:
            self._selected_accounts = None
        else:
            if isinstance(acc, str):
                acc = [acc] if acc else []
            self._selected_accounts = {str(x) for x in (acc or [])}

    def _save_hidden(self) -> None:
        QSettings().setValue(_HIDDEN_SETTINGS_KEY, sorted(self._hidden))

    def _save_accounts(self) -> None:
        if self._selected_accounts is None:
            QSettings().remove(_ACCOUNTS_SETTINGS_KEY)
        else:
            QSettings().setValue(_ACCOUNTS_SETTINGS_KEY, sorted(self._selected_accounts))

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(4)

        title = QLabel("Company Snapshot")
        title.setObjectName("snapshotPageTitle")
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {_SNAP_TITLE}; background: transparent;"
        )
        outer.addWidget(title)
        outer.addWidget(self._build_toolbar())

        self._stack = QStackedWidget()
        self._stack.setObjectName("snapshotViewStack")
        self._stack.addWidget(self._build_company_page())
        self._stack.addWidget(self._build_payments_page())
        self._stack.addWidget(self._build_customer_page())
        self._view_group.idClicked.connect(self._stack.setCurrentIndex)
        outer.addWidget(self._stack, 1)

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("snapshotToolbar")
        bar.setStyleSheet(
            f"QFrame#snapshotToolbar {{ background: {_SNAP_PANEL}; border: 1px solid {_SNAP_GRID}; "
            "border-radius: 3px; }"
        )
        lay = QVBoxLayout(bar)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(4)

        tabs = QHBoxLayout()
        tabs.setSpacing(0)
        self._view_group = QButtonGroup(self)
        self._view_group.setExclusive(True)
        for i, name in enumerate(("Company", "Payments", "Customer")):
            btn = QToolButton()
            btn.setObjectName(f"snapshotView{name}")
            btn.setText(name)
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.setAutoRaise(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                f"QToolButton {{ background: transparent; border: none; border-bottom: 2px solid transparent; "
                f"color: {_SNAP_TEXT}; padding: 4px 14px; font-size: 12px; }}"
                "QToolButton:checked { border-bottom: 2px solid #2563A8; font-weight: 700; color: #2563A8; }"
                "QToolButton:hover { background: #E8F1FA; }"
            )
            self._view_group.addButton(btn, i)
            tabs.addWidget(btn)
        tabs.addStretch(1)
        lay.addLayout(tabs)

        actions = QHBoxLayout()
        actions.setSpacing(12)
        self._btn_add = QPushButton("Add Content >")
        self._btn_add.setObjectName("snapshotAddContent")
        self._btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_add.setStyleSheet(_link_qss())
        self._btn_add.setToolTip("Bring back content you closed on this page.")
        self._btn_add.clicked.connect(self._on_add_content)
        self._btn_restore = QPushButton("Restore Default")
        self._btn_restore.setObjectName("snapshotRestoreDefault")
        self._btn_restore.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_restore.setStyleSheet(_link_qss())
        self._btn_restore.setToolTip("Show every default widget and reset period filters.")
        self._btn_restore.clicked.connect(self.restore_default)
        actions.addWidget(self._btn_add)
        actions.addWidget(self._btn_restore)
        actions.addStretch(1)
        self._search = QLineEdit()
        self._search.setObjectName("snapshotSearch")
        self._search.setPlaceholderText("Search")
        self._search.setFixedWidth(160)
        self._search.setStyleSheet(
            f"QLineEdit {{ background: {_SNAP_PAPER}; border: 1px solid {_SNAP_GRID}; "
            f"padding: 2px 8px; color: {_SNAP_TEXT}; }}"
        )
        self._search.setToolTip("Filter customer names on this page.")
        self._search.textChanged.connect(self._apply_search)
        actions.addWidget(self._search)
        self._btn_how = QPushButton("How do I customize this page?")
        self._btn_how.setObjectName("snapshotCustomizeHelp")
        self._btn_how.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_how.setStyleSheet(_link_qss())
        self._btn_how.clicked.connect(self._on_customize_help)
        self._btn_print = QPushButton("Print")
        self._btn_print.setObjectName("snapshotPrint")
        self._btn_print.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_print.setStyleSheet(_link_qss())
        self._btn_print.setToolTip("Print the current Snapshot view.")
        self._btn_print.clicked.connect(self._on_print)
        actions.addWidget(self._btn_how)
        actions.addWidget(self._btn_print)
        lay.addLayout(actions)
        return bar

    def _wrap_scroll(self, inner: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: {_SNAP_CANVAS}; border: none; }}")
        inner.setAutoFillBackground(True)
        pal = inner.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(_SNAP_CANVAS))
        inner.setPalette(pal)
        scroll.setWidget(inner)
        return scroll

    def _make_widget(self, key: str, *, period: bool = False) -> _SnapshotWidget:
        w = _SnapshotWidget(key, _WIDGET_TITLES[key], self)
        w.period.setVisible(period)
        if period:
            w.period.currentTextChanged.connect(lambda _t: self.reload())
        w.closed.connect(self._on_close_widget)
        return w

    def _build_company_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("snapshotCompanyPage")
        grid = QGridLayout(page)
        grid.setContentsMargins(0, 6, 0, 0)
        grid.setSpacing(8)
        for c in range(3):
            grid.setColumnStretch(c, 1)
        for r in range(3):
            grid.setRowStretch(r, 1)

        self._w_income = self._make_widget("income_expense", period=True)
        self._chart_income = _BarChart()
        self._chart_income.setObjectName("snapshotChartIncomeExpense")
        self._w_income.body_layout.addWidget(self._chart_income, 1)
        grid.addWidget(self._w_income, 0, 0)

        self._w_prev_inc = self._make_widget("prev_income")
        all_combo = QComboBox()
        all_combo.setObjectName("snapshotPrevIncomeScope")
        all_combo.addItems(("All",))
        all_combo.setStyleSheet(_combo_qss())
        yearly = QComboBox()
        yearly.setObjectName("snapshotPrevIncomeGrain")
        yearly.addItems(("Yearly",))
        yearly.setStyleSheet(_combo_qss())
        self._w_prev_inc.add_header_widget(all_combo)
        self._w_prev_inc.add_header_widget(yearly)
        self._chart_prev_inc = _BarChart()
        self._chart_prev_inc.setObjectName("snapshotChartPrevIncome")
        self._w_prev_inc.body_layout.addWidget(self._chart_prev_inc, 1)
        grid.addWidget(self._w_prev_inc, 0, 1)

        self._w_owe = self._make_widget("customers_owe")
        self._tbl_owe = _MoneyTable(("CUSTOMER", "DUE DATE", "AMT DUE"))
        self._tbl_owe.setObjectName("snapshotCustomersOweTable")
        self._tbl_owe.cellDoubleClicked.connect(self._on_owe_activated)
        self._tbl_owe.itemSelectionChanged.connect(self._on_owe_selected)
        self._w_owe.body_layout.addWidget(self._tbl_owe, 1)
        owe_links = QHBoxLayout()
        owe_links.addStretch(1)
        self._btn_recv = QPushButton("Receive Payments")
        self._btn_recv.setObjectName("snapshotReceivePaymentsLink")
        self._btn_recv.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_recv.setStyleSheet(_link_qss())
        self._btn_recv.setToolTip("Open Receive Payments.")
        self._btn_recv.clicked.connect(self._on_receive_payments)
        owe_links.addWidget(self._btn_recv)
        self._w_owe.body_layout.addLayout(owe_links)
        grid.addWidget(self._w_owe, 0, 2)

        self._w_balances = self._make_widget("account_balances")
        self._tbl_bal = _MoneyTable(("ACCOUNT", "BALANCE"))
        self._tbl_bal.setObjectName("snapshotAccountBalancesTable")
        self._w_balances.body_layout.addWidget(self._tbl_bal, 1)
        bal_links = QHBoxLayout()
        self._btn_select_acct = QPushButton("Select Accounts")
        self._btn_select_acct.setObjectName("snapshotSelectAccountsLink")
        self._btn_select_acct.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_select_acct.setStyleSheet(_link_qss())
        self._btn_select_acct.clicked.connect(self._on_select_accounts)
        self._btn_coa = QPushButton("Go to Chart of Accounts")
        self._btn_coa.setObjectName("snapshotGoToCoaLink")
        self._btn_coa.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_coa.setStyleSheet(_link_qss())
        self._btn_coa.setToolTip("Open Chart of Accounts.")
        self._btn_coa.clicked.connect(lambda: self.navigateRequested.emit("coa"))
        bal_links.addWidget(self._btn_select_acct)
        bal_links.addStretch(1)
        bal_links.addWidget(self._btn_coa)
        self._w_balances.body_layout.addLayout(bal_links)
        grid.addWidget(self._w_balances, 1, 0)

        self._w_top = self._make_widget("top_customers", period=True)
        self._chart_top = _HBarChart()
        self._chart_top.setObjectName("snapshotChartTopCustomers")
        self._w_top.body_layout.addWidget(self._chart_top, 1)
        grid.addWidget(self._w_top, 1, 1)

        self._w_prev_exp = self._make_widget("prev_expense")
        all2 = QComboBox()
        all2.setObjectName("snapshotPrevExpenseScope")
        all2.addItems(("All",))
        all2.setStyleSheet(_combo_qss())
        yearly2 = QComboBox()
        yearly2.setObjectName("snapshotPrevExpenseGrain")
        yearly2.addItems(("Yearly",))
        yearly2.setStyleSheet(_combo_qss())
        self._w_prev_exp.add_header_widget(all2)
        self._w_prev_exp.add_header_widget(yearly2)
        self._chart_prev_exp = _BarChart()
        self._chart_prev_exp.setObjectName("snapshotChartPrevExpense")
        self._w_prev_exp.body_layout.addWidget(self._chart_prev_exp, 1)
        grid.addWidget(self._w_prev_exp, 1, 2)

        self._w_pie = self._make_widget("expense_pie", period=True)
        self._chart_pie = _PieChart()
        self._chart_pie.setObjectName("snapshotChartExpensePie")
        self._w_pie.body_layout.addWidget(self._chart_pie, 1)
        grid.addWidget(self._w_pie, 2, 0)

        self._company_widgets = {
            "income_expense": self._w_income,
            "prev_income": self._w_prev_inc,
            "customers_owe": self._w_owe,
            "account_balances": self._w_balances,
            "top_customers": self._w_top,
            "prev_expense": self._w_prev_exp,
            "expense_pie": self._w_pie,
        }
        self._apply_hidden()
        return self._wrap_scroll(page)

    def _build_payments_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("snapshotPaymentsPage")
        grid = QGridLayout(page)
        grid.setContentsMargins(0, 6, 0, 0)
        grid.setSpacing(8)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(0, 1)

        owe = _SnapshotWidget("pay_customers_owe", "Customers Who Owe Money", self)
        self._tbl_pay_owe = _MoneyTable(("CUSTOMER", "DUE DATE", "AMT DUE"))
        self._tbl_pay_owe.setObjectName("snapshotPaymentsOweTable")
        self._tbl_pay_owe.cellDoubleClicked.connect(self._on_owe_activated)
        owe.body_layout.addWidget(self._tbl_pay_owe, 1)
        recv = QPushButton("Receive Payments")
        recv.setObjectName("snapshotPaymentsReceiveLink")
        recv.setCursor(Qt.CursorShape.PointingHandCursor)
        recv.setStyleSheet(_link_qss())
        recv.clicked.connect(self._on_receive_payments)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(recv)
        owe.body_layout.addLayout(row)
        grid.addWidget(owe, 0, 0)

        vend = _SnapshotWidget("pay_vendors", "Vendors to Pay", self)
        self._tbl_vendors = _MoneyTable(("VENDOR", "DUE DATE", "AMT DUE"))
        self._tbl_vendors.setObjectName("snapshotVendorsToPayTable")
        vend.body_layout.addWidget(self._tbl_vendors, 1)
        pay = QPushButton("Pay Bills")
        pay.setObjectName("snapshotPayBillsLink")
        pay.setCursor(Qt.CursorShape.PointingHandCursor)
        pay.setStyleSheet(_link_qss())
        pay.clicked.connect(lambda: self.navigateRequested.emit("pay_bills"))
        row2 = QHBoxLayout()
        row2.addStretch(1)
        row2.addWidget(pay)
        vend.body_layout.addLayout(row2)
        grid.addWidget(vend, 0, 1)
        return self._wrap_scroll(page)

    def _build_customer_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("snapshotCustomerPage")
        grid = QGridLayout(page)
        grid.setContentsMargins(0, 6, 0, 0)
        grid.setSpacing(8)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(0, 1)

        top = _SnapshotWidget("cust_top", "Top Customers by Sales", self)
        self._chart_cust_top = _HBarChart()
        self._chart_cust_top.setObjectName("snapshotCustomerTopChart")
        top.body_layout.addWidget(self._chart_cust_top, 1)
        grid.addWidget(top, 0, 0)

        owe = _SnapshotWidget("cust_owe", "Customers Who Owe Money", self)
        self._tbl_cust_owe = _MoneyTable(("CUSTOMER", "DUE DATE", "AMT DUE"))
        self._tbl_cust_owe.setObjectName("snapshotCustomerOweTable")
        self._tbl_cust_owe.cellDoubleClicked.connect(self._on_owe_activated)
        owe.body_layout.addWidget(self._tbl_cust_owe, 1)
        recv = QPushButton("Receive Payments")
        recv.setObjectName("snapshotCustomerReceiveLink")
        recv.setCursor(Qt.CursorShape.PointingHandCursor)
        recv.setStyleSheet(_link_qss())
        recv.clicked.connect(self._on_receive_payments)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(recv)
        owe.body_layout.addLayout(row)
        grid.addWidget(owe, 0, 1)
        return self._wrap_scroll(page)

    def _apply_hidden(self) -> None:
        for key, widget in self._company_widgets.items():
            widget.setVisible(key not in self._hidden)

    def _on_close_widget(self, key: str) -> None:
        self._hidden.add(key)
        self._save_hidden()
        self._apply_hidden()

    def _on_add_content(self) -> None:
        menu = QMenu(self)
        hidden = [k for k in _DEFAULT_WIDGETS if k in self._hidden]
        if not hidden:
            act = menu.addAction("All default content is already on this page")
            act.setEnabled(False)
        else:
            for key in hidden:
                act = menu.addAction(_WIDGET_TITLES[key])
                act.triggered.connect(lambda _c=False, k=key: self._restore_widget(k))
        menu.exec(self._btn_add.mapToGlobal(self._btn_add.rect().bottomLeft()))

    def _restore_widget(self, key: str) -> None:
        self._hidden.discard(key)
        self._save_hidden()
        self._apply_hidden()

    def restore_default(self) -> None:
        self._hidden.clear()
        self._save_hidden()
        self._selected_accounts = None
        self._save_accounts()
        self._search.clear()
        for key, widget in self._company_widgets.items():
            widget.set_collapsed(False)
            if widget.period.isVisible():
                widget.period.setCurrentText(snap.PERIOD_YTD)
        self._view_group.button(0).setChecked(True)
        self._stack.setCurrentIndex(0)
        self._apply_hidden()
        self.reload()

    def _on_customize_help(self) -> None:
        message_box_information_ok(
            self,
            "Customize this page",
            "Company Snapshot shows live totals from your company file.\n\n"
            "• Close a widget with ×, then use Add Content to bring it back.\n"
            "• Restore Default puts every widget back and resets This year-to-date.\n"
            "• Search filters customer names on this page.\n"
            "• Company / Payments / Customer switch which content you see.\n\n"
            "A full layout designer is not part of this page.",
            ok_tip="Close; keep using Snapshot with live company-file totals.",
        )

    def _on_print(self) -> None:
        if os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
            message_box_information_ok(
                self,
                "Print",
                "Print is not available in this display mode.",
                ok_tip="Close; print from a normal desktop session.",
            )
            return
        try:
            from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        except Exception:
            message_box_information_ok(
                self,
                "Print",
                "Printing is not available in this build.",
                ok_tip="Close.",
            )
            return
        printer = QPrinter(QPrinter.PrinterMode.ScreenResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        pix = self._stack.currentWidget().grab()
        painter = QPainter(printer)
        rect = painter.viewport()
        scaled = pix.scaled(rect.size(), Qt.AspectRatioMode.KeepAspectRatio)
        painter.drawPixmap(0, 0, scaled)
        painter.end()

    def _on_receive_payments(self) -> None:
        self.receivePaymentsRequested.emit(int(self._last_owe_customer_id or 0))

    def _on_owe_selected(self) -> None:
        rows = self._tbl_owe.selectionModel().selectedRows() if self._tbl_owe.selectionModel() else []
        if not rows:
            return
        it = self._tbl_owe.item(rows[0].row(), 0)
        if it is None:
            return
        cid = int(it.data(_ROLE_ID) or 0)
        if cid:
            self._last_owe_customer_id = cid

    def _on_owe_activated(self, row: int, _col: int = 0) -> None:
        table = self.sender()
        if not isinstance(table, QTableWidget):
            table = self._tbl_owe
        it = table.item(row, 0)
        if it is None:
            return
        cid = int(it.data(_ROLE_ID) or 0)
        if cid:
            self._last_owe_customer_id = cid
            self.openCustomerRequested.emit(cid)

    def _on_select_accounts(self) -> None:
        rows = snap.account_balances(self._conn) if self._conn is not None else []
        dlg = QDialog(self)
        dlg.setWindowTitle("Select Accounts")
        dlg.setModal(True)
        lay = QVBoxLayout(dlg)
        intro = QLabel("Choose which balances appear on Company Snapshot.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        boxes: list[tuple[str, QCheckBox]] = []
        selected = self._selected_accounts
        for row in rows:
            cb = QCheckBox(escape_ampersand_for_qt(str(row["name"])))
            key = str(row["key"])
            cb.setChecked(selected is None or key in selected)
            lay.addWidget(cb)
            boxes.append((key, cb))
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        tip_qdialog_button_box(
            buttons,
            ok="Save the selected accounts on this Snapshot.",
            cancel="Close without changing Account Balances.",
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        chosen = {k for k, cb in boxes if cb.isChecked()}
        self._selected_accounts = chosen
        self._save_accounts()
        self.reload()

    def _name_ok(self, name: str) -> bool:
        q = (self._search.text() or "").strip().lower()
        if not q:
            return True
        return q in (name or "").lower()

    def _apply_search(self, _text: str = "") -> None:
        self.reload()

    def _fill_owe_table(self, table: QTableWidget, rows: list[dict]) -> None:
        filtered = [r for r in rows if self._name_ok(str(r.get("name") or ""))]
        table.setRowCount(len(filtered))
        for i, r in enumerate(filtered):
            name_it = plain_display_table_item(str(r.get("name") or ""))
            name_it.setData(_ROLE_ID, int(r.get("customer_id") or 0))
            due = format_iso_to_us_display(str(r.get("due_date") or ""))
            due_it = plain_display_table_item(due)
            if r.get("is_overdue"):
                due_it.setForeground(QColor(_SNAP_OVERDUE))
            amt = FloatSortTableItem(_fmt_money(float(r.get("amount_due") or 0)), float(r.get("amount_due") or 0))
            amt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(i, 0, name_it)
            table.setItem(i, 1, due_it)
            table.setItem(i, 2, amt)

    def reload(self) -> None:
        conn = self._conn
        today = self._today
        if conn is None:
            return
        period_ie = self._w_income.period.currentText()
        months = snap.monthly_income_expense(conn, today=today, period=period_ie)
        self._chart_income.set_data(
            [m["label"] for m in months],
            [
                ("Income", _SNAP_INCOME, [float(m["income"]) for m in months]),
                ("Expense", _SNAP_EXPENSE, [float(m["expense"]) for m in months]),
            ],
        )
        years_i = snap.yearly_income(conn, today=today)
        self._chart_prev_inc.set_data(
            [str(y["year"]) for y in years_i],
            [
                (
                    "Prior Year(s)",
                    _SNAP_PRIOR_INCOME,
                    [0.0 if y["is_current"] else float(y["amount"]) for y in years_i],
                ),
                (
                    "Current Year",
                    _SNAP_CUR_INCOME,
                    [float(y["amount"]) if y["is_current"] else 0.0 for y in years_i],
                ),
            ],
        )
        years_e = snap.yearly_expense(conn, today=today)
        self._chart_prev_exp.set_data(
            [str(y["year"]) for y in years_e],
            [
                (
                    "Prior Year(s)",
                    _SNAP_PRIOR_EXPENSE,
                    [0.0 if y["is_current"] else float(y["amount"]) for y in years_e],
                ),
                (
                    "Current Year",
                    _SNAP_CUR_EXPENSE,
                    [float(y["amount"]) if y["is_current"] else 0.0 for y in years_e],
                ),
            ],
        )
        owe = snap.customers_who_owe(conn, today=today)
        self._fill_owe_table(self._tbl_owe, owe)
        self._fill_owe_table(self._tbl_pay_owe, owe)
        self._fill_owe_table(self._tbl_cust_owe, owe)

        vendors = snap.vendors_to_pay(conn, today=today)
        self._tbl_vendors.setRowCount(len(vendors))
        for i, r in enumerate(vendors):
            name_it = plain_display_table_item(str(r.get("name") or ""))
            due = format_iso_to_us_display(str(r.get("due_date") or ""))
            due_it = plain_display_table_item(due)
            if r.get("is_overdue"):
                due_it.setForeground(QColor(_SNAP_OVERDUE))
            amt = FloatSortTableItem(_fmt_money(float(r.get("amount_due") or 0)), float(r.get("amount_due") or 0))
            amt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._tbl_vendors.setItem(i, 0, name_it)
            self._tbl_vendors.setItem(i, 1, due_it)
            self._tbl_vendors.setItem(i, 2, amt)

        balances = snap.account_balances(conn)
        if self._selected_accounts is not None:
            balances = [b for b in balances if str(b["key"]) in self._selected_accounts]
        self._tbl_bal.setRowCount(len(balances))
        for i, r in enumerate(balances):
            name_it = plain_display_table_item(str(r.get("name") or ""))
            amt_val = float(r.get("balance") or 0)
            amt = FloatSortTableItem(_fmt_money(amt_val), amt_val)
            amt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if amt_val < -0.005:
                amt.setForeground(QColor(_SNAP_OVERDUE))
            self._tbl_bal.setItem(i, 0, name_it)
            self._tbl_bal.setItem(i, 1, amt)

        period_top = self._w_top.period.currentText()
        top = [
            r
            for r in snap.top_customers_by_sales(conn, today=today, period=period_top)
            if self._name_ok(str(r.get("name") or ""))
        ]
        bars = [(str(r["name"]), float(r["sales"])) for r in top]
        self._chart_top.set_data(bars)
        self._chart_cust_top.set_data(bars)

        period_pie = self._w_pie.period.currentText()
        pie = snap.expense_breakdown(conn, today=today, period=period_pie)
        self._chart_pie.set_data([(str(r["label"]), float(r["amount"])) for r in pie])
