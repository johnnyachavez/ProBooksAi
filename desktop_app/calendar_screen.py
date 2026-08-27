"""Calendar — QuickBooks Pro Desktop-style month grid with live invoices and bills.

Month cells show Entered (n) and Due (n). A detail pane lists the selected day.
The right sidebar summarizes Upcoming (next 7 days) and Due (past 60 days).
Slightly cleaner spacing than a gray Win32 photocopy; not QuickBooks Online.

Click a due invoice → Create Invoices; a due bill → Enter Bills; an overdue
bill in the Past 60 days BILLS list → Pay Bills.
"""

from __future__ import annotations

import calendar
import sqlite3
from datetime import date
from typing import Optional

from PySide6.QtCore import QDate, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
    QPolygonF,
    QShortcut,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from desktop_app.flexible_date import format_iso_to_us_display
from desktop_app.qt_mnemonic import escape_ampersand_for_qt, tip_qdialog_button_box
from desktop_app.table_clipboard import FloatSortTableItem, plain_display_table_item
from probooksai import qb_calendar as cal

_CAL_CANVAS = "#E8ECF1"
_CAL_PAPER = "#FFFFFF"
_CAL_PANEL = "#F4F7FA"
_CAL_STRIPE = "#E8F1FA"
_CAL_CAPTION = "#4A5560"
_CAL_GRID = "#C0C8D0"
_CAL_HEADER = "#D8DEE6"
_CAL_TEXT = "#1A1A1A"
_CAL_TITLE = "#5B6770"
_CAL_ACCENT = "#2563A8"
_CAL_SELECT = "#2E7D32"
_CAL_SELECT_FG = "#FFFFFF"
_CAL_LINK = "#1565C0"
_CAL_MUTED = "#8A94A0"
_CAL_DUE = "#C62828"
_CAL_ENTERED = "#1A1A1A"
_CAL_TODAY_RING = "#2563A8"
_CAL_UPCOMING = "#43A047"
_CAL_PAST_DUE = "#EF6C00"
_STRIP_BTN = "#B4BCC6"

_WEEKDAYS = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")
_ROLE_EVENT = Qt.ItemDataRole.UserRole
_LIST_HEADERS = ("DATE", "TYPE", "NAME", "NUMBER", "AMOUNT", "BUCKET")


def _fmt_money(value: float, *, signed_bills: bool = False, kind: str = "") -> str:
    amt = float(value or 0)
    if signed_bills and kind == cal.KIND_BILL:
        amt = -abs(amt)
    return f"{amt:,.2f}"


def _light_palette() -> QPalette:
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(_CAL_CANVAS))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(_CAL_TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(_CAL_PAPER))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(_CAL_STRIPE))
    pal.setColor(QPalette.ColorRole.Text, QColor(_CAL_TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(_CAL_PAPER))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(_CAL_TEXT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(_CAL_SELECT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(_CAL_SELECT_FG))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(_CAL_CAPTION))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(_CAL_PANEL))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(_CAL_TEXT))
    return pal


def _combo_qss() -> str:
    return (
        f"QComboBox {{ background: {_CAL_PAPER}; border: 1px solid {_CAL_GRID}; "
        f"padding: 2px 8px; color: {_CAL_TEXT}; min-height: 22px; }}"
    )


def _nav_button_qss() -> str:
    return (
        f"QPushButton {{ background-color: {_CAL_ACCENT}; border: 1px solid {_CAL_ACCENT}; "
        "border-radius: 3px; color: #FFFFFF; font-size: 13px; font-weight: 700; }"
        "QPushButton:hover { background-color: #1D4F8C; }"
        "QPushButton:pressed { background-color: #163E6E; }"
    )


def _tool_button_qss(*, checked: bool = False) -> str:
    bg = "#D0E6F4" if checked else "#F7F8FA"
    return (
        f"QToolButton {{ background-color: {bg}; border: 1px solid {_STRIP_BTN}; "
        f"border-radius: 4px; color: {_CAL_TEXT}; padding: 2px 6px; }}"
        "QToolButton:hover { background-color: #E4EEF7; }"
        "QToolButton:checked { background-color: #D0E6F4; border: 1px solid #2563A8; }"
    )


def _view_icon(kind: str, size: int = 18) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(_CAL_ACCENT), 1.3))
    p.setBrush(QColor("#E8F1FA"))
    if kind == "list":
        p.drawRoundedRect(QRectF(1, 1, size - 2, size - 2), 2, 2)
        p.setPen(QPen(QColor(_CAL_ACCENT), 1.2))
        for i in range(3):
            y = 4.5 + i * 4.5
            p.drawLine(QPointF(4, y), QPointF(size - 4, y))
    else:
        p.drawRoundedRect(QRectF(1, 1, size - 2, size - 2), 2, 2)
        p.setBrush(QColor(_CAL_ACCENT))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(QRectF(1, 1, size - 2, 4))
        p.setPen(QPen(QColor(_CAL_ACCENT), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(size / 3, 5), QPointF(size / 3, size - 2))
        p.drawLine(QPointF(2 * size / 3, 5), QPointF(2 * size / 3, size - 2))
        p.drawLine(QPointF(1, size / 2 + 1), QPointF(size - 1, size / 2 + 1))
    p.end()
    return QIcon(pm)


def _flag_pixmap(color: str, size: int = 16) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor("#4A5560"), 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(3.5, 1.5), QPointF(3.5, size - 1.5))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    flag = QPolygonF(
        [
            QPointF(4.5, 2),
            QPointF(size - 1.5, 5),
            QPointF(size - 3, 8),
            QPointF(4.5, 11),
        ]
    )
    p.drawPolygon(flag)
    p.end()
    return pm


class _DayCell(QFrame):
    """One month-grid cell: date number, Due (n), Entered (n)."""

    clicked = Signal(object)
    doubleClicked = Signal(object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._day: Optional[date] = None
        self._in_month = True
        self._selected = False
        self._is_today = False
        self.setObjectName("calendarDayCell")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(72)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(1)
        num_row = QHBoxLayout()
        num_row.setContentsMargins(0, 0, 0, 0)
        num_row.addStretch(1)
        self._num = QLabel("")
        self._num.setObjectName("calendarDayNumber")
        self._num.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        num_row.addWidget(self._num)
        lay.addLayout(num_row)
        self._due = QLabel("")
        self._due.setObjectName("calendarDayDue")
        self._entered = QLabel("")
        self._entered.setObjectName("calendarDayEntered")
        lay.addWidget(self._due)
        lay.addWidget(self._entered)
        lay.addStretch(1)
        self._apply_style()

    def set_cell(
        self,
        day: date,
        *,
        in_month: bool,
        selected: bool,
        is_today: bool,
        entered: int,
        due: int,
    ) -> None:
        self._day = day
        self._in_month = in_month
        self._selected = selected
        self._is_today = is_today
        self._num.setText(str(day.day))
        self._due.setText(f"Due ({due})" if due else "")
        self._entered.setText(f"Entered ({entered})" if entered else "")
        self.setToolTip(
            f"{day.isoformat()}: Due ({due}), Entered ({entered}). Click to select; "
            "double-click opens the single item when only one is on this date."
        )
        self._apply_style()

    def _apply_style(self) -> None:
        if self._selected:
            bg, fg, border = _CAL_SELECT, _CAL_SELECT_FG, _CAL_SELECT
            due_fg = "#FFCDD2"
            entered_fg = _CAL_SELECT_FG
            num_weight = "700"
        else:
            bg = _CAL_PAPER
            fg = _CAL_TEXT if self._in_month else _CAL_MUTED
            border = _CAL_TODAY_RING if self._is_today else _CAL_GRID
            due_fg = _CAL_DUE if self._in_month else _CAL_MUTED
            entered_fg = _CAL_ENTERED if self._in_month else _CAL_MUTED
            num_weight = "700"
        width = "2px" if self._is_today and not self._selected else "1px"
        self.setStyleSheet(
            f"QFrame#calendarDayCell {{ background: {bg}; border: {width} solid {border}; }}"
        )
        self._num.setStyleSheet(
            f"color: {fg}; font-size: 13px; font-weight: {num_weight}; "
            "background: transparent; border: none;"
        )
        self._due.setStyleSheet(
            f"color: {due_fg}; font-size: 11px; background: transparent; border: none;"
        )
        self._entered.setStyleSheet(
            f"color: {entered_fg}; font-size: 11px; background: transparent; border: none;"
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._day is not None:
            self.clicked.emit(self._day)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._day is not None:
            self.doubleClicked.emit(self._day)
        super().mouseDoubleClickEvent(event)


class AddToDoDialog(QDialog):
    """Title + due date + notes. Saved into ``calendar_todos``."""

    def __init__(self, default_date: date, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("addToDoDialog")
        self.setWindowTitle("Add To Do")
        self.setModal(True)
        self.resize(380, 220)
        self.setToolTip("Add a To Do on the selected calendar date.")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        self._title = QLineEdit()
        self._title.setObjectName("addToDoTitle")
        self._title.setPlaceholderText("To Do")
        self._date = QDateEdit()
        self._date.setObjectName("addToDoDate")
        self._date.setDisplayFormat("MM/dd/yyyy")
        self._date.setCalendarPopup(True)
        self._date.setDate(QDate(default_date.year, default_date.month, default_date.day))
        self._notes = QPlainTextEdit()
        self._notes.setObjectName("addToDoNotes")
        self._notes.setPlaceholderText("Notes (optional)")
        self._notes.setFixedHeight(72)
        lay.addWidget(QLabel("Title"))
        lay.addWidget(self._title)
        lay.addWidget(QLabel("Date"))
        lay.addWidget(self._date)
        lay.addWidget(QLabel("Notes"))
        lay.addWidget(self._notes)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        tip_qdialog_button_box(
            buttons,
            ok="Save this To Do on the calendar.",
            cancel="Close without adding a To Do.",
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def values(self) -> tuple[str, str, str]:
        qd = self._date.date()
        iso = date(qd.year(), qd.month(), qd.day()).isoformat()
        return (
            (self._title.text() or "").strip() or "To Do",
            iso,
            (self._notes.toPlainText() or "").strip(),
        )


class CalendarScreen(QWidget):
    """QB Pro Calendar: month grid, day detail, Upcoming / Past Due sidebar."""

    openInvoiceRequested = Signal(int)
    openBillRequested = Signal(int)
    payBillRequested = Signal(int)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        ap_conn: Optional[sqlite3.Connection] = None,
        today: Optional[date] = None,
    ) -> None:
        super().__init__(parent)
        self._conn = ap_conn
        self._today = today or date.today()
        self._month = date(self._today.year, self._today.month, 1)
        self._selected = self._today
        self._show = cal.SHOW_ALL
        self._view = "month"
        self.setObjectName("calendarScreen")
        self.setAutoFillBackground(True)
        self.setPalette(_light_palette())
        self.setToolTip(
            "Calendar: month grid of Entered and Due invoices and bills from the open "
            "company file. Click a day for details; click a due bill or invoice to open "
            "Enter Bills, Create Invoices, or Pay Bills. "
            "Same company .db as other tabs (File → Backup / Restore, probooks.backup)."
        )
        self.setStyleSheet(
            f"CalendarScreen {{ background-color: {_CAL_CANVAS}; color: {_CAL_TEXT}; }}"
        )
        self._build_ui()
        sc = QShortcut(QKeySequence("F5"), self)
        sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc.activated.connect(self.reload)
        self.reload()

    def set_connection(self, conn: Optional[sqlite3.Connection]) -> None:
        self._conn = conn
        self.reload()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self.reload()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(6)

        title = QLabel("Calendar")
        title.setObjectName("calendarTitle")
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {_CAL_TITLE}; background: transparent;"
        )
        outer.addWidget(title)
        outer.addWidget(self._build_toolbar())

        body = QSplitter(Qt.Orientation.Horizontal)
        body.setObjectName("calendarBodySplitter")
        body.setChildrenCollapsible(False)

        left = QSplitter(Qt.Orientation.Vertical)
        left.setObjectName("calendarLeftSplitter")
        left.setChildrenCollapsible(False)
        self._stack = QStackedWidget()
        self._stack.setObjectName("calendarViewStack")
        self._stack.addWidget(self._build_month_grid())
        self._stack.addWidget(self._build_list_view())
        left.addWidget(self._stack)
        left.addWidget(self._build_detail())
        left.setStretchFactor(0, 4)
        left.setStretchFactor(1, 1)
        body.addWidget(left)
        body.addWidget(self._build_sidebar())
        body.setStretchFactor(0, 5)
        body.setStretchFactor(1, 0)
        body.setSizes([900, 280])
        outer.addWidget(body, 1)

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("calendarToolbar")
        bar.setStyleSheet(
            f"QFrame#calendarToolbar {{ background: #D5DCE4; border: 1px solid {_CAL_GRID}; }}"
        )
        row = QHBoxLayout(bar)
        row.setContentsMargins(10, 6, 10, 6)
        row.setSpacing(8)

        self._btn_prev = QPushButton("‹")
        self._btn_prev.setObjectName("calendarPrevMonth")
        self._btn_prev.setFixedSize(28, 26)
        self._btn_prev.setStyleSheet(_nav_button_qss())
        self._btn_prev.setToolTip("Previous month.")
        self._btn_prev.clicked.connect(self._on_prev_month)
        self._lbl_month = QLabel("")
        self._lbl_month.setObjectName("calendarMonthLabel")
        self._lbl_month.setStyleSheet(
            f"color: {_CAL_TEXT}; font-size: 15px; font-weight: 700; "
            "background: transparent; border: none; min-width: 140px;"
        )
        self._btn_next = QPushButton("›")
        self._btn_next.setObjectName("calendarNextMonth")
        self._btn_next.setFixedSize(28, 26)
        self._btn_next.setStyleSheet(_nav_button_qss())
        self._btn_next.setToolTip("Next month.")
        self._btn_next.clicked.connect(self._on_next_month)
        self._btn_today = QPushButton("Today")
        self._btn_today.setObjectName("calendarToday")
        self._btn_today.setFixedHeight(26)
        self._btn_today.setStyleSheet(
            f"QPushButton {{ background: #F7F8FA; border: 1px solid {_STRIP_BTN}; "
            f"border-radius: 4px; color: {_CAL_TEXT}; padding: 0 12px; }}"
            "QPushButton:hover { background: #E4EEF7; }"
        )
        self._btn_today.setToolTip("Jump to today.")
        self._btn_today.clicked.connect(self._on_today)

        self._btn_list = QToolButton()
        self._btn_list.setObjectName("calendarListView")
        self._btn_list.setIcon(_view_icon("list"))
        self._btn_list.setIconSize(QSize(18, 18))
        self._btn_list.setCheckable(True)
        self._btn_list.setToolTip("List view of this month.")
        self._btn_list.setStyleSheet(_tool_button_qss())
        self._btn_month = QToolButton()
        self._btn_month.setObjectName("calendarMonthView")
        self._btn_month.setIcon(_view_icon("month"))
        self._btn_month.setIconSize(QSize(18, 18))
        self._btn_month.setCheckable(True)
        self._btn_month.setChecked(True)
        self._btn_month.setToolTip("Month grid view (default).")
        self._btn_month.setStyleSheet(_tool_button_qss())
        group = QButtonGroup(self)
        group.setExclusive(True)
        group.addButton(self._btn_list)
        group.addButton(self._btn_month)
        self._btn_list.clicked.connect(lambda: self._set_view("list"))
        self._btn_month.clicked.connect(lambda: self._set_view("month"))

        date_wrap = QWidget()
        date_lay = QVBoxLayout(date_wrap)
        date_lay.setContentsMargins(0, 0, 0, 0)
        date_lay.setSpacing(1)
        date_lbl = QLabel("Select a date")
        date_lbl.setStyleSheet(
            f"color: {_CAL_CAPTION}; font-size: 10px; font-weight: 700; "
            "letter-spacing: 0.04em; background: transparent; border: none;"
        )
        self._pick_date = QDateEdit()
        self._pick_date.setObjectName("calendarSelectDate")
        self._pick_date.setDisplayFormat("MM/dd/yyyy")
        self._pick_date.setCalendarPopup(True)
        self._pick_date.setStyleSheet(
            f"QDateEdit {{ background: {_CAL_PAPER}; border: 1px solid {_CAL_GRID}; "
            f"padding: 2px 8px; color: {_CAL_TEXT}; min-height: 22px; }}"
        )
        self._pick_date.dateChanged.connect(self._on_pick_date)
        date_lay.addWidget(date_lbl)
        date_lay.addWidget(self._pick_date)

        show_wrap = QWidget()
        show_lay = QVBoxLayout(show_wrap)
        show_lay.setContentsMargins(0, 0, 0, 0)
        show_lay.setSpacing(1)
        show_lbl = QLabel("SHOW")
        show_lbl.setStyleSheet(
            f"color: {_CAL_CAPTION}; font-size: 10px; font-weight: 700; "
            "letter-spacing: 0.04em; background: transparent; border: none;"
        )
        self._show_combo = QComboBox()
        self._show_combo.setObjectName("calendarShowFilter")
        self._show_combo.setStyleSheet(_combo_qss())
        self._show_combo.addItems(list(cal.SHOW_CHOICES))
        self._show_combo.setCurrentText(cal.SHOW_ALL)
        self._show_combo.currentTextChanged.connect(self._on_show_changed)
        show_lay.addWidget(show_lbl)
        show_lay.addWidget(self._show_combo)

        row.addWidget(self._btn_prev)
        row.addWidget(self._lbl_month)
        row.addWidget(self._btn_next)
        row.addWidget(self._btn_today)
        row.addSpacing(8)
        row.addWidget(self._btn_list)
        row.addWidget(self._btn_month)
        row.addSpacing(12)
        row.addWidget(date_wrap)
        row.addSpacing(12)
        row.addWidget(show_wrap)
        row.addStretch(1)
        return bar

    def _build_month_grid(self) -> QWidget:
        wrap = QFrame()
        wrap.setObjectName("calendarMonthGrid")
        wrap.setStyleSheet(
            f"QFrame#calendarMonthGrid {{ background: {_CAL_PAPER}; border: 1px solid {_CAL_GRID}; }}"
        )
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        header = QWidget()
        header.setObjectName("calendarWeekHeader")
        header.setStyleSheet(
            f"QWidget#calendarWeekHeader {{ background: {_CAL_HEADER}; }}"
        )
        hrow = QHBoxLayout(header)
        hrow.setContentsMargins(0, 0, 0, 0)
        hrow.setSpacing(0)
        for name in _WEEKDAYS:
            lbl = QLabel(name)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(
                f"color: {_CAL_ACCENT}; font-size: 11px; font-weight: 700; "
                f"padding: 6px 0; border-bottom: 1px solid {_CAL_GRID}; "
                f"border-right: 1px solid {_CAL_GRID}; background: transparent;"
            )
            hrow.addWidget(lbl, 1)
        lay.addWidget(header)
        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        self._cells: list[_DayCell] = []
        for i in range(42):
            cell = _DayCell()
            cell.clicked.connect(self._on_select_day)
            cell.doubleClicked.connect(self._on_double_day)
            self._cells.append(cell)
            grid.addWidget(cell, i // 7, i % 7)
            grid.setRowStretch(i // 7, 1)
            grid.setColumnStretch(i % 7, 1)
        lay.addWidget(grid_host, 1)
        return wrap

    def _build_list_view(self) -> QTableWidget:
        table = QTableWidget()
        table.setObjectName("calendarListTable")
        table.setColumnCount(len(_LIST_HEADERS))
        table.setHorizontalHeaderLabels(list(_LIST_HEADERS))
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(True)
        table.verticalHeader().setDefaultSectionSize(26)
        table.setStyleSheet(
            f"QTableWidget#calendarListTable {{"
            f" background-color: {_CAL_PAPER};"
            f" alternate-background-color: {_CAL_STRIPE};"
            f" color: {_CAL_TEXT};"
            f" gridline-color: {_CAL_GRID};"
            f" border: 1px solid {_CAL_GRID};"
            "}"
            "QTableWidget#calendarListTable::item:selected {"
            f" background-color: {_CAL_SELECT}; color: {_CAL_SELECT_FG};"
            "}"
            "QHeaderView::section {"
            f" background-color: {_CAL_HEADER}; color: {_CAL_ACCENT};"
            " font-weight: 700; font-size: 11px; padding: 4px 6px;"
            f" border: 1px solid {_CAL_GRID};"
            "}"
        )
        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.doubleClicked.connect(self._on_list_double_clicked)
        self._list_table = table
        return table

    def _build_detail(self) -> QFrame:
        pane = QFrame()
        pane.setObjectName("calendarDetailPane")
        pane.setMinimumHeight(120)
        pane.setStyleSheet(
            f"QFrame#calendarDetailPane {{ background: {_CAL_PAPER}; "
            f"border: 1px solid {_CAL_GRID}; }}"
        )
        lay = QVBoxLayout(pane)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)
        self._detail_date = QLabel("")
        self._detail_date.setObjectName("calendarDetailDate")
        self._detail_date.setStyleSheet(
            f"color: {_CAL_CAPTION}; font-size: 11px; background: transparent; border: none;"
        )
        lay.addWidget(self._detail_date)
        self._detail_empty = QLabel("There are no To Do's or Transactions on this date.")
        self._detail_empty.setObjectName("calendarDetailEmpty")
        self._detail_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._detail_empty.setStyleSheet(
            f"color: {_CAL_MUTED}; font-size: 13px; background: transparent; border: none;"
        )
        lay.addWidget(self._detail_empty, 1)
        self._detail_list = QListWidget()
        self._detail_list.setObjectName("calendarDetailList")
        self._detail_list.setStyleSheet(
            f"QListWidget {{ background: {_CAL_PAPER}; border: none; color: {_CAL_TEXT}; }}"
            f"QListWidget::item:selected {{ background: {_CAL_SELECT}; color: {_CAL_SELECT_FG}; }}"
        )
        self._detail_list.itemDoubleClicked.connect(self._on_detail_item)
        self._detail_list.hide()
        lay.addWidget(self._detail_list, 1)
        link_row = QHBoxLayout()
        link_row.addStretch(1)
        self._btn_add_todo = QPushButton("Add To Do")
        self._btn_add_todo.setObjectName("calendarAddToDo")
        self._btn_add_todo.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_add_todo.setFlat(True)
        self._btn_add_todo.setStyleSheet(
            f"QPushButton {{ color: {_CAL_LINK}; background: transparent; border: none; "
            "font-size: 12px; text-decoration: underline; padding: 2px 4px; }"
            f"QPushButton:hover {{ color: #0D47A1; }}"
        )
        self._btn_add_todo.setToolTip("Add a To Do on the selected date.")
        self._btn_add_todo.clicked.connect(self._on_add_todo)
        link_row.addWidget(self._btn_add_todo)
        lay.addLayout(link_row)
        return pane

    def _build_sidebar(self) -> QFrame:
        side = QFrame()
        side.setObjectName("calendarSidebar")
        side.setMinimumWidth(250)
        side.setMaximumWidth(320)
        side.setStyleSheet(
            f"QFrame#calendarSidebar {{ background: {_CAL_PANEL}; "
            f"border: 1px solid {_CAL_GRID}; }}"
        )
        lay = QVBoxLayout(side)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)
        self._upcoming_header = self._section_header(
            "calendarUpcomingHeader", "Upcoming: Next 7 days (0)", _CAL_UPCOMING
        )
        lay.addWidget(self._upcoming_header)
        self._upcoming_todo = self._count_label("calendarUpcomingTodo", "TO DO (0)")
        self._upcoming_txn = self._count_label("calendarUpcomingTxn", "TRANSACTIONS (0)")
        self._upcoming_bills = self._count_label("calendarUpcomingBills", "BILLS (0)")
        self._upcoming_list = self._side_list("calendarUpcomingList")
        lay.addWidget(self._upcoming_todo)
        lay.addWidget(self._upcoming_txn)
        lay.addWidget(self._upcoming_bills)
        lay.addWidget(self._upcoming_list, 1)

        self._past_header = self._section_header(
            "calendarPastDueHeader", "Due: Past 60 days (0)", _CAL_PAST_DUE
        )
        lay.addWidget(self._past_header)
        self._past_todo = self._count_label("calendarPastDueTodo", "TO DO (0)")
        self._past_txn = self._count_label("calendarPastDueTxn", "TRANSACTIONS (0)")
        self._past_bills = self._count_label("calendarPastDueBills", "BILLS (0)")
        self._past_list = self._side_list("calendarPastDueList")
        lay.addWidget(self._past_todo)
        lay.addWidget(self._past_txn)
        lay.addWidget(self._past_bills)
        lay.addWidget(self._past_list, 2)
        return side

    def _section_header(self, object_name: str, text: str, flag_color: str) -> QWidget:
        wrap = QWidget()
        wrap.setObjectName(object_name)
        row = QHBoxLayout(wrap)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(6)
        flag = QLabel()
        flag.setPixmap(_flag_pixmap(flag_color))
        flag.setFixedSize(16, 16)
        lbl = QLabel(text)
        lbl.setObjectName(f"{object_name}Label")
        font = QFont()
        font.setBold(True)
        lbl.setFont(font)
        lbl.setStyleSheet(
            f"color: {_CAL_TEXT}; font-size: 12px; background: transparent; border: none;"
        )
        row.addWidget(flag)
        row.addWidget(lbl, 1)
        wrap._label = lbl  # type: ignore[attr-defined]
        return wrap

    def _count_label(self, object_name: str, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName(object_name)
        lbl.setStyleSheet(
            f"color: {_CAL_CAPTION}; font-size: 11px; font-weight: 700; "
            "letter-spacing: 0.04em; background: transparent; border: none; padding: 2px 4px;"
        )
        return lbl

    def _side_list(self, object_name: str) -> QListWidget:
        lst = QListWidget()
        lst.setObjectName(object_name)
        lst.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        lst.setStyleSheet(
            f"QListWidget {{ background: {_CAL_PAPER}; border: 1px solid {_CAL_GRID}; "
            f"color: {_CAL_TEXT}; font-size: 11px; }}"
            f"QListWidget::item:selected {{ background: {_CAL_SELECT}; color: {_CAL_SELECT_FG}; }}"
        )
        lst.itemClicked.connect(self._on_sidebar_item)
        lst.itemDoubleClicked.connect(self._on_sidebar_item)
        return lst

    def reload(self) -> None:
        self._lbl_month.setText(f"{calendar.month_name[self._month.month]} {self._month.year}")
        self._pick_date.blockSignals(True)
        self._pick_date.setDate(
            QDate(self._selected.year, self._selected.month, self._selected.day)
        )
        self._pick_date.blockSignals(False)
        self._refresh_month_cells()
        self._refresh_list()
        self._refresh_detail()
        self._refresh_sidebar()

    def _refresh_month_cells(self) -> None:
        counts: dict[str, dict[str, int]] = {}
        if self._conn is not None:
            counts = cal.month_cell_counts(
                self._conn, self._month.year, self._month.month, show=self._show
            )
        days = cal.month_grid_dates(self._month.year, self._month.month)
        for cell, day in zip(self._cells, days):
            c = counts.get(day.isoformat(), {"entered": 0, "due": 0})
            cell.set_cell(
                day,
                in_month=day.month == self._month.month,
                selected=day == self._selected,
                is_today=day == self._today,
                entered=int(c.get("entered") or 0),
                due=int(c.get("due") or 0),
            )

    def _refresh_list(self) -> None:
        rows: list[dict] = []
        if self._conn is not None:
            rows = cal.month_list_rows(
                self._conn, self._month.year, self._month.month, show=self._show
            )
        self._list_table.setSortingEnabled(False)
        self._list_table.setRowCount(len(rows))
        for i, event in enumerate(rows):
            date_item = plain_display_table_item(format_iso_to_us_display(event.get("sort_date") or ""))
            date_item.setData(_ROLE_EVENT, event)
            self._list_table.setItem(i, 0, date_item)
            self._list_table.setItem(i, 1, plain_display_table_item(event.get("type") or ""))
            self._list_table.setItem(i, 2, plain_display_table_item(event.get("party_name") or ""))
            self._list_table.setItem(i, 3, plain_display_table_item(event.get("number") or ""))
            raw_amt = float(event.get("amount") or 0)
            amt = FloatSortTableItem(_fmt_money(raw_amt), raw_amt)
            amt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._list_table.setItem(i, 4, amt)
            self._list_table.setItem(i, 5, plain_display_table_item(event.get("bucket") or ""))
        self._list_table.setSortingEnabled(True)

    def _refresh_detail(self) -> None:
        label = self._selected.strftime("%B ") + f"{self._selected.day}, {self._selected.year}"
        self._detail_date.setText(label)
        entered: list[dict] = []
        due: list[dict] = []
        if self._conn is not None:
            entered = cal.list_entered_for_date(self._conn, self._selected, show=self._show)
            due = cal.list_due_for_date(self._conn, self._selected, show=self._show)
        seen: set[tuple[str, int, str]] = set()
        items: list[tuple[str, dict]] = []
        for event in due:
            key = (event["kind"], int(event["record_id"]), "due")
            if key in seen:
                continue
            seen.add(key)
            items.append(("Due", event))
        for event in entered:
            key = (event["kind"], int(event["record_id"]), "entered")
            if key in seen:
                continue
            seen.add(key)
            items.append(("Entered", event))
        if not items:
            self._detail_empty.show()
            self._detail_list.hide()
            self._detail_list.clear()
            return
        self._detail_empty.hide()
        self._detail_list.show()
        self._detail_list.clear()
        for bucket, event in items:
            amt = ""
            if event["kind"] != cal.KIND_TODO:
                amt = f"  {_fmt_money(event.get('amount') or 0)}"
            text = f"{bucket}  {event.get('type')}  {event.get('party_name')}{amt}"
            if event.get("number"):
                text += f"  #{event['number']}"
            item = QListWidgetItem(escape_ampersand_for_qt(text))
            item.setData(_ROLE_EVENT, event)
            self._detail_list.addItem(item)

    def _refresh_sidebar(self) -> None:
        upcoming = {
            "todos": [],
            "transactions": [],
            "bills": [],
            "count": 0,
        }
        past = dict(upcoming)
        if self._conn is not None:
            upcoming = cal.upcoming_next_7(self._conn, today=self._today, show=self._show)
            past = cal.due_past_60(self._conn, today=self._today, show=self._show)
        self._upcoming_header._label.setText(  # type: ignore[attr-defined]
            f"Upcoming: Next 7 days ({upcoming['count']})"
        )
        self._upcoming_todo.setText(f"TO DO ({len(upcoming['todos'])})")
        self._upcoming_txn.setText(f"TRANSACTIONS ({len(upcoming['transactions'])})")
        self._upcoming_bills.setText(f"BILLS ({len(upcoming['bills'])})")
        self._fill_side_list(self._upcoming_list, upcoming, overdue=False)

        self._past_header._label.setText(  # type: ignore[attr-defined]
            f"Due: Past 60 days ({past['count']})"
        )
        self._past_todo.setText(f"TO DO ({len(past['todos'])})")
        self._past_txn.setText(f"TRANSACTIONS ({len(past['transactions'])})")
        self._past_bills.setText(f"BILLS ({len(past['bills'])})")
        self._fill_side_list(self._past_list, past, overdue=True)

    def _fill_side_list(self, lst: QListWidget, groups: dict, *, overdue: bool) -> None:
        lst.clear()
        # Prefer bills in the overdue list (QB expands BILLS there).
        order = ("bills", "transactions", "todos") if overdue else ("todos", "transactions", "bills")
        for key in order:
            for event in groups.get(key) or []:
                days = (
                    event.get("days_overdue")
                    if overdue
                    else event.get("days_until")
                )
                amt = ""
                if event["kind"] != cal.KIND_TODO:
                    amt = _fmt_money(
                        event.get("open_balance") or event.get("amount") or 0,
                        signed_bills=overdue,
                        kind=event["kind"],
                    )
                name = event.get("party_name") or ""
                if len(name) > 22:
                    name = name[:20] + "…"
                text = f"{name}    {amt}    {days}"
                item = QListWidgetItem(escape_ampersand_for_qt(text))
                payload = dict(event)
                payload["_from_past_bills"] = bool(overdue and event["kind"] == cal.KIND_BILL)
                item.setData(_ROLE_EVENT, payload)
                lst.addItem(item)

    def _set_view(self, view: str) -> None:
        self._view = view
        self._stack.setCurrentIndex(0 if view == "month" else 1)
        self._btn_month.setChecked(view == "month")
        self._btn_list.setChecked(view == "list")

    def _on_prev_month(self) -> None:
        y, m = self._month.year, self._month.month
        if m == 1:
            self._month = date(y - 1, 12, 1)
        else:
            self._month = date(y, m - 1, 1)
        self.reload()

    def _on_next_month(self) -> None:
        y, m = self._month.year, self._month.month
        if m == 12:
            self._month = date(y + 1, 1, 1)
        else:
            self._month = date(y, m + 1, 1)
        self.reload()

    def _on_today(self) -> None:
        self._month = date(self._today.year, self._today.month, 1)
        self._selected = self._today
        self.reload()

    def _on_pick_date(self, qd: QDate) -> None:
        if not qd.isValid():
            return
        day = date(qd.year(), qd.month(), qd.day())
        self._month = date(day.year, day.month, 1)
        self._selected = day
        self.reload()

    def _on_show_changed(self, text: str) -> None:
        self._show = text or cal.SHOW_ALL
        self.reload()

    def _on_select_day(self, day: date) -> None:
        self._selected = day
        if day.month != self._month.month or day.year != self._month.year:
            self._month = date(day.year, day.month, 1)
        self.reload()

    def _on_double_day(self, day: date) -> None:
        self._on_select_day(day)
        if self._conn is None:
            return
        due = cal.list_due_for_date(self._conn, day, show=self._show)
        entered = cal.list_entered_for_date(self._conn, day, show=self._show)
        candidates = due or entered
        if len(candidates) == 1:
            self._open_event(candidates[0], from_past_bills=False)

    def _on_list_double_clicked(self, index) -> None:  # noqa: ANN001
        row = index.row()
        item = self._list_table.item(row, 0)
        if item is None:
            return
        event = item.data(_ROLE_EVENT)
        if isinstance(event, dict):
            iso = event.get("sort_date") or ""
            parsed = date.fromisoformat(iso) if iso else None
            if parsed is not None:
                self._selected = parsed
            self._open_event(event, from_past_bills=False)

    def _on_detail_item(self, item: QListWidgetItem) -> None:
        event = item.data(_ROLE_EVENT)
        if isinstance(event, dict):
            self._open_event(event, from_past_bills=False)

    def _on_sidebar_item(self, item: QListWidgetItem) -> None:
        event = item.data(_ROLE_EVENT)
        if isinstance(event, dict):
            iso = event.get("due_date") or ""
            parsed = date.fromisoformat(iso) if iso else None
            if parsed is not None:
                self._selected = parsed
                self._month = date(parsed.year, parsed.month, 1)
                self.reload()
            self._open_event(event, from_past_bills=bool(event.get("_from_past_bills")))

    def _open_event(self, event: dict, *, from_past_bills: bool) -> None:
        kind = event.get("kind") or ""
        rid = int(event.get("record_id") or 0)
        if rid <= 0:
            return
        if kind == cal.KIND_INVOICE:
            self.openInvoiceRequested.emit(rid)
        elif kind == cal.KIND_BILL:
            overdue = int(event.get("days_overdue") or 0) > 0 or from_past_bills
            if overdue:
                self.payBillRequested.emit(rid)
            else:
                self.openBillRequested.emit(rid)

    def _on_add_todo(self) -> None:
        if self._conn is None:
            return
        dlg = AddToDoDialog(self._selected, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        title, iso, notes = dlg.values()
        cal.add_todo(self._conn, title=title, due_date=iso, notes=notes)
        self.reload()

    def add_todo_for_tests(self, title: str, due_date: str, notes: str = "") -> int:
        """Test helper: insert a To Do without a modal loop."""
        if self._conn is None:
            return 0
        tid = cal.add_todo(self._conn, title=title, due_date=due_date, notes=notes)
        self.reload()
        return tid
