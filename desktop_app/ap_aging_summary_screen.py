"""A/P Aging Summary — QuickBooks Pro Desktop-style vendor aging report.

Report action bar, Today / interval / through filters, COMPANY NAME header,
and a roomy vendor grid. Live open bills only; empty company = zeros.
Slightly cleaner spacing than a gray Win32 photocopy — not QuickBooks Online.

Double-click a vendor row → Vendor Center. Vendors have no "jobs" in QB Pro
Desktop, so the grid is a flat list. Layout designer stays parked.
"""

from __future__ import annotations

import csv
import sqlite3
from datetime import date, datetime

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QPalette, QShortcut, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop_app.qt_mnemonic import (
    CSV_EXPORT_OK_TIP_SUFFIX,
    escape_ampersand_for_qt,
    message_box_critical_ok,
    message_box_information_ok,
)
from desktop_app.theme import DISABLED_FG
from probooksai import qb_ap_aging as aging

PLACEHOLDER_COMPANY_NAME = "COMPANY NAME"

_AP_CANVAS = "#E8ECF1"
_AP_PAPER = "#FFFFFF"
_AP_PANEL = "#F4F7FA"
_AP_STRIP = "#E4E8EC"
_AP_GRID = "#C0C8D0"
_AP_HEADER = "#D8DEE6"
_AP_TEXT = "#1A1A1A"
_AP_TITLE = "#1E3A5F"
_AP_CAPTION = "#4A5560"
_AP_ACCENT = "#2563A8"
_AP_LINK = "#1565C0"
_AP_SELECT = "#C8E6C9"
_AP_TOTAL_BG = "#F3F6F9"
_STRIP_BTN = "#B4BCC6"
WORKFLOW_CONTROL_FACE = "#F7F8FA"
WORKFLOW_CONTROL_HOVER = "#E4EEF7"
WORKFLOW_CONTROL_PRESSED = "#C9D8EC"

_ROLE_KIND = Qt.ItemDataRole.UserRole
_ROLE_VENDOR_ID = Qt.ItemDataRole.UserRole + 1

_DATES_TODAY = "Today"
_DATES_CUSTOM = "Custom Date"
_SORT_DEFAULT = "Default"
_SORT_NAME = "Name"
_SORT_TOTAL = "Total"


def _light_palette() -> QPalette:
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(_AP_CANVAS))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(_AP_TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(_AP_PAPER))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(_AP_PANEL))
    pal.setColor(QPalette.ColorRole.Text, QColor(_AP_TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(WORKFLOW_CONTROL_FACE))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(_AP_TEXT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(_AP_SELECT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(_AP_TEXT))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(_AP_CAPTION))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(_AP_PANEL))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(_AP_TEXT))
    return pal


def _btn_qss() -> str:
    return (
        f"QPushButton, QToolButton {{ background-color: {WORKFLOW_CONTROL_FACE}; "
        f"border: 1px solid {_STRIP_BTN}; border-radius: 3px; color: {_AP_TEXT}; "
        "font-size: 11px; padding: 3px 10px; min-height: 22px; }"
        f"QPushButton:hover, QToolButton:hover {{ background-color: {WORKFLOW_CONTROL_HOVER}; }}"
        f"QPushButton:pressed, QToolButton:pressed {{ background-color: {WORKFLOW_CONTROL_PRESSED}; }}"
        f"QPushButton:disabled, QToolButton:disabled {{ color: {DISABLED_FG}; }}"
        "QToolButton::menu-indicator { width: 10px; }"
    )


def _combo_qss() -> str:
    return (
        f"QComboBox, QDateEdit, QSpinBox, QLineEdit {{ background: {_AP_PAPER}; "
        f"border: 1px solid {_AP_GRID}; padding: 1px 6px; color: {_AP_TEXT}; "
        "min-height: 20px; font-size: 11px; }"
    )


def _link_qss() -> str:
    return (
        f"QPushButton {{ background: transparent; border: none; color: {_AP_LINK}; "
        "font-size: 11px; padding: 0px; text-align: left; }"
        f"QPushButton:hover {{ color: {_AP_ACCENT}; text-decoration: underline; }}"
    )


def _fmt_money(value: float) -> str:
    return f"{float(value or 0):,.2f}"


def _as_of_long(d: date) -> str:
    return f"As of {d.strftime('%B')} {d.day}, {d.year}"


class APAgingSummaryScreen(QWidget):
    """QB Pro A/P Aging Summary filling most of the window under the icon bar."""

    openVendorRequested = Signal(int)

    def __init__(self, ap_conn: sqlite3.Connection | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("apAgingPage")
        self._conn = ap_conn
        self._header_hidden = False
        self._extra_filters_visible = False
        self.setAutoFillBackground(True)
        self.setPalette(_light_palette())
        self.setStyleSheet(
            f"QWidget#apAgingPage {{ background: {_AP_CANVAS}; color: {_AP_TEXT}; }}"
        )
        self.setToolTip(
            "A/P Aging Summary: live open bill balances by vendor. "
            "F5 refreshes. Reports menu and Vendor Center Open Balance open this report. "
            "Same company SQLite file (File → Backup / Restore, probooks.backup)."
        )
        self._build_ui()
        sc = QShortcut(QKeySequence("F5"), self)
        sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc.activated.connect(self.reload)
        self.reload()

    def _style_tool(self, b: QToolButton) -> None:
        b.setStyleSheet(_btn_qss())
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

    def _style_push(self, b: QPushButton) -> None:
        b.setStyleSheet(_btn_qss())
        b.setAutoDefault(False)
        b.setDefault(False)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_action_bar())
        root.addWidget(self._build_filter_bar())
        root.addWidget(self._build_extra_filters())

        paper = QFrame()
        paper.setObjectName("apAgingPaper")
        paper.setStyleSheet(
            f"QFrame#apAgingPaper {{ background: {_AP_PAPER}; border: none; }}"
        )
        paper.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        play = QVBoxLayout(paper)
        play.setContentsMargins(12, 8, 12, 8)
        play.setSpacing(4)

        stamp_row = QHBoxLayout()
        stamp_row.setContentsMargins(0, 0, 0, 0)
        self._timestamp = QLabel("")
        self._timestamp.setObjectName("apAgingTimestamp")
        self._timestamp.setStyleSheet(
            f"color: {_AP_TEXT}; font-size: 10px; background: transparent;"
        )
        stamp_row.addWidget(self._timestamp, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        stamp_row.addStretch(1)
        play.addLayout(stamp_row)

        self._header_wrap = QWidget()
        self._header_wrap.setObjectName("apAgingHeader")
        hlay = QVBoxLayout(self._header_wrap)
        hlay.setContentsMargins(0, 0, 0, 6)
        hlay.setSpacing(2)
        self._company = QLabel(PLACEHOLDER_COMPANY_NAME)
        self._company.setObjectName("apAgingCompanyName")
        self._company.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._company.setStyleSheet(
            f"color: {_AP_TITLE}; font-size: 15px; font-weight: 700; background: transparent;"
        )
        hlay.addWidget(self._company)
        self._title = QLabel("A/P Aging Summary")
        self._title.setObjectName("apAgingTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._title.setStyleSheet(
            f"color: {_AP_TITLE}; font-size: 18px; font-weight: 700; background: transparent;"
        )
        hlay.addWidget(self._title)
        self._as_of = QLabel("")
        self._as_of.setObjectName("apAgingAsOf")
        self._as_of.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._as_of.setStyleSheet(
            f"color: {_AP_TITLE}; font-size: 12px; font-weight: 600; background: transparent;"
        )
        hlay.addWidget(self._as_of)
        play.addWidget(self._header_wrap)

        self._tree = QTreeWidget()
        self._tree.setObjectName("apAgingTree")
        self._tree.setAlternatingRowColors(False)
        # Vendors have no jobs — a flat list looks cleanest without the disclosure gutter.
        self._tree.setRootIsDecorated(False)
        self._tree.setUniformRowHeights(True)
        self._tree.setIndentation(0)
        self._tree.setSortingEnabled(False)
        self._tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._tree.itemDoubleClicked.connect(self._on_row_double_clicked)
        self._tree.setStyleSheet(
            f"QTreeWidget {{ background: {_AP_PAPER}; color: {_AP_TEXT}; border: none; "
            "font-size: 12px; outline: none; }"
            f"QHeaderView::section {{ background: {_AP_HEADER}; color: {_AP_TEXT}; "
            f"border: 1px solid {_AP_GRID}; border-left: none; padding: 4px 8px; "
            "font-size: 11px; font-weight: 600; }"
            f"QTreeWidget::item {{ border-bottom: 1px solid #EEF1F4; min-height: 22px; }}"
            f"QTreeWidget::item:selected {{ background: {_AP_SELECT}; color: {_AP_TEXT}; }}"
        )
        play.addWidget(self._tree, 1)
        root.addWidget(paper, 1)

    def _build_action_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("apAgingActionBar")
        bar.setStyleSheet(
            f"QFrame#apAgingActionBar {{ background: {_AP_STRIP}; border-bottom: 1px solid {_AP_GRID}; }}"
        )
        row = QHBoxLayout(bar)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(4)

        for label, slot, name in (
            ("Customize Report", self._on_customize, "apAgingCustomize"),
            ("Comment on Report", self._on_comment, "apAgingComment"),
            ("Share Template", self._on_share, "apAgingShare"),
            ("Memorize", self._on_memorize, "apAgingMemorize"),
        ):
            b = QPushButton(label)
            b.setObjectName(name)
            self._style_push(b)
            b.clicked.connect(slot)
            row.addWidget(b)

        self._btn_print = QToolButton()
        self._btn_print.setObjectName("apAgingPrint")
        self._btn_print.setText("Print")
        self._style_tool(self._btn_print)
        pm = QMenu(self._btn_print)
        pm.addAction("Print report…", self._on_print)
        self._btn_print.setMenu(pm)
        self._btn_print.setToolTip("Print the A/P Aging Summary.")
        row.addWidget(self._btn_print)

        self._btn_email = QToolButton()
        self._btn_email.setObjectName("apAgingEmail")
        self._btn_email.setText("E-mail")
        self._style_tool(self._btn_email)
        em = QMenu(self._btn_email)
        em.addAction("E-mail report…", self._on_email)
        self._btn_email.setMenu(em)
        self._btn_email.setToolTip("E-mail this report (not wired yet).")
        row.addWidget(self._btn_email)

        self._btn_excel = QToolButton()
        self._btn_excel.setObjectName("apAgingExcel")
        self._btn_excel.setText("Excel")
        self._style_tool(self._btn_excel)
        xm = QMenu(self._btn_excel)
        xm.addAction("Export CSV…", self._on_export_csv)
        self._btn_excel.setMenu(xm)
        self._btn_excel.setToolTip("Export this summary to CSV (UTF-8 BOM for Excel).")
        row.addWidget(self._btn_excel)

        row.addSpacing(12)
        self._btn_hide_header = QPushButton("Hide Header")
        self._btn_hide_header.setObjectName("apAgingHideHeader")
        self._style_push(self._btn_hide_header)
        self._btn_hide_header.clicked.connect(self._on_toggle_header)
        self._btn_hide_header.setToolTip("Hide or show the COMPANY NAME / title / As of header.")
        row.addWidget(self._btn_hide_header)

        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.setObjectName("apAgingRefresh")
        self._style_push(self._btn_refresh)
        self._btn_refresh.clicked.connect(self.reload)
        self._btn_refresh.setToolTip("Reload live open bills (F5).")
        row.addWidget(self._btn_refresh)
        row.addStretch(1)
        bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        return bar

    def _build_filter_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("apAgingFilterBar")
        bar.setStyleSheet(
            f"QFrame#apAgingFilterBar {{ background: {_AP_PANEL}; border-bottom: 1px solid {_AP_GRID}; }}"
        )
        row = QHBoxLayout(bar)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(8)

        self._btn_show_filters = QPushButton("Show Filters")
        self._btn_show_filters.setObjectName("apAgingShowFilters")
        self._btn_show_filters.setStyleSheet(_link_qss())
        self._btn_show_filters.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_show_filters.clicked.connect(self._on_toggle_extra_filters)
        self._btn_show_filters.setToolTip("Show or hide extra report filters.")
        row.addWidget(self._btn_show_filters)

        row.addWidget(self._caption("Dates"))
        self._dates = QComboBox()
        self._dates.setObjectName("apAgingDates")
        self._dates.setStyleSheet(_combo_qss())
        self._dates.addItems((_DATES_TODAY, _DATES_CUSTOM))
        self._dates.setCurrentText(_DATES_TODAY)
        self._dates.currentTextChanged.connect(self._on_dates_changed)
        row.addWidget(self._dates)

        self._as_of_edit = QDateEdit()
        self._as_of_edit.setObjectName("apAgingDate")
        self._as_of_edit.setCalendarPopup(True)
        self._as_of_edit.setDisplayFormat("MM/dd/yyyy")
        self._as_of_edit.setDate(QDate.currentDate())
        self._as_of_edit.setStyleSheet(_combo_qss())
        self._as_of_edit.dateChanged.connect(self._on_as_of_changed)
        row.addWidget(self._as_of_edit)

        row.addWidget(self._caption("Interval (days)"))
        self._interval = QSpinBox()
        self._interval.setObjectName("apAgingInterval")
        self._interval.setRange(1, 365)
        self._interval.setValue(30)
        self._interval.setStyleSheet(_combo_qss())
        self._interval.valueChanged.connect(self.reload)
        row.addWidget(self._interval)

        row.addWidget(self._caption("Through (days past due)"))
        self._through = QSpinBox()
        self._through.setObjectName("apAgingThrough")
        self._through.setRange(1, 3650)
        self._through.setValue(90)
        self._through.setStyleSheet(_combo_qss())
        self._through.valueChanged.connect(self.reload)
        row.addWidget(self._through)

        row.addWidget(self._caption("Sort By"))
        self._sort = QComboBox()
        self._sort.setObjectName("apAgingSort")
        self._sort.setStyleSheet(_combo_qss())
        self._sort.addItems((_SORT_DEFAULT, _SORT_NAME, _SORT_TOTAL))
        self._sort.currentTextChanged.connect(self.reload)
        row.addWidget(self._sort)
        row.addStretch(1)
        bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        return bar

    def _build_extra_filters(self) -> QWidget:
        self._extra_filters = QFrame()
        self._extra_filters.setObjectName("apAgingExtraFilters")
        self._extra_filters.setStyleSheet(
            f"QFrame#apAgingExtraFilters {{ background: {_AP_PANEL}; "
            f"border-bottom: 1px solid {_AP_GRID}; }}"
        )
        row = QHBoxLayout(self._extra_filters)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(8)
        row.addWidget(self._caption("Name contains"))
        self._name_contains = QLineEdit()
        self._name_contains.setObjectName("apAgingNameContains")
        self._name_contains.setStyleSheet(_combo_qss())
        self._name_contains.setPlaceholderText("Filter vendors")
        self._name_contains.setClearButtonEnabled(True)
        self._name_contains.textChanged.connect(self.reload)
        row.addWidget(self._name_contains, 1)
        self._extra_filters.setVisible(False)
        return self._extra_filters

    def _caption(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {_AP_CAPTION}; font-size: 11px; font-weight: 600; background: transparent;"
        )
        return lbl

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.reload()

    def _as_of_date(self) -> date:
        qd = self._as_of_edit.date()
        return date(qd.year(), qd.month(), qd.day())

    def _sort_key(self) -> str:
        text = self._sort.currentText()
        if text == _SORT_TOTAL:
            return "total"
        return "default"

    def _name_filter(self) -> str:
        return (self._name_contains.text() or "").strip().lower()

    def reload(self) -> None:
        as_of = self._as_of_date()
        if self._dates.currentText() == _DATES_TODAY:
            today = date.today()
            if as_of != today:
                self._as_of_edit.blockSignals(True)
                self._as_of_edit.setDate(QDate(today.year, today.month, today.day))
                self._as_of_edit.blockSignals(False)
                as_of = today
        self._company.setText(PLACEHOLDER_COMPANY_NAME)
        self._as_of.setText(_as_of_long(as_of))
        now = datetime.now()
        hour12 = now.hour % 12 or 12
        ampm = "AM" if now.hour < 12 else "PM"
        self._timestamp.setText(f"{hour12}:{now.strftime('%M')} {ampm}\n{now.strftime('%m/%d/%y')}")
        interval = int(self._interval.value())
        through = int(self._through.value())
        if self._conn is None:
            cols = aging.bucket_columns(interval, through)
            data = {
                "as_of": as_of.isoformat(),
                "interval": interval,
                "through": through,
                "bucket_keys": [c[0] for c in cols],
                "bucket_labels": [c[1] for c in cols],
                "groups": [],
                "grand_total": aging.empty_amounts(cols),
            }
        else:
            data = aging.ap_aging_summary(
                self._conn,
                as_of.isoformat(),
                interval=interval,
                through=through,
                sort_by=self._sort_key(),
            )
        self._fill_tree(data)

    def _fill_tree(self, data: dict) -> None:
        keys: list[str] = list(data.get("bucket_keys") or [])
        labels: list[str] = list(data.get("bucket_labels") or [])
        headers = ["Vendor", *labels, "TOTAL"]
        needle = self._name_filter()
        self._tree.clear()
        self._tree.setColumnCount(len(headers))
        self._tree.setHeaderLabels(headers)
        hdr = self._tree.header()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, len(headers)):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
            hdr.setDefaultAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        groups = list(data.get("groups") or [])
        if needle:
            groups = [g for g in groups if needle in (g.get("name") or "").lower()]

        for group in groups:
            row = self._make_row(
                group["name"],
                group["amounts"],
                keys,
                kind=str(group.get("kind") or "vendor"),
                vendor_id=int(group.get("vendor_id") or 0),
                bold=False,
            )
            self._tree.addTopLevelItem(row)

        grand = data.get("grand_total") or aging.empty_amounts(
            aging.bucket_columns(int(data.get("interval") or 30), int(data.get("through") or 90))
        )
        total_item = self._make_row(
            "TOTAL",
            grand,
            keys,
            kind="grand",
            vendor_id=0,
            bold=True,
            total_bg=True,
        )
        self._tree.addTopLevelItem(total_item)

    def _make_row(
        self,
        name: str,
        amounts: dict,
        keys: list[str],
        *,
        kind: str,
        vendor_id: int,
        bold: bool,
        total_bg: bool = False,
    ) -> QTreeWidgetItem:
        item = QTreeWidgetItem()
        item.setText(0, name)
        item.setData(0, _ROLE_KIND, kind)
        item.setData(0, _ROLE_VENDOR_ID, int(vendor_id or 0))
        align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        for i, key in enumerate(keys, start=1):
            item.setText(i, _fmt_money(amounts.get(key) or 0))
            item.setTextAlignment(i, align)
        item.setText(len(keys) + 1, _fmt_money(amounts.get("total") or 0))
        item.setTextAlignment(len(keys) + 1, align)
        font = QFont(item.font(0))
        font.setBold(bold)
        for col in range(len(keys) + 2):
            item.setFont(col, font)
            item.setForeground(col, QColor(_AP_TITLE if bold else _AP_TEXT))
            if total_bg:
                item.setBackground(col, QColor(_AP_TOTAL_BG))
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        item.setFlags(flags)
        return item

    def _on_row_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        kind = str(item.data(0, _ROLE_KIND) or "")
        if kind == "grand":
            return
        vid = int(item.data(0, _ROLE_VENDOR_ID) or 0)
        if vid <= 0:
            return
        self.openVendorRequested.emit(vid)

    def _on_dates_changed(self, text: str) -> None:
        if text == _DATES_TODAY:
            today = date.today()
            self._as_of_edit.blockSignals(True)
            self._as_of_edit.setDate(QDate(today.year, today.month, today.day))
            self._as_of_edit.blockSignals(False)
        self.reload()

    def _on_as_of_changed(self, _qd: QDate) -> None:
        if self._dates.currentText() != _DATES_CUSTOM:
            self._dates.blockSignals(True)
            self._dates.setCurrentText(_DATES_CUSTOM)
            self._dates.blockSignals(False)
        self.reload()

    def _on_toggle_header(self) -> None:
        self._header_hidden = not self._header_hidden
        self._header_wrap.setVisible(not self._header_hidden)
        self._timestamp.setVisible(not self._header_hidden)
        self._btn_hide_header.setText("Show Header" if self._header_hidden else "Hide Header")

    def _on_toggle_extra_filters(self) -> None:
        self._extra_filters_visible = not self._extra_filters_visible
        self._extra_filters.setVisible(self._extra_filters_visible)
        self._btn_show_filters.setText(
            "Hide Filters" if self._extra_filters_visible else "Show Filters"
        )
        if not self._extra_filters_visible and self._name_contains.text():
            self._name_contains.clear()

    def _on_customize(self) -> None:
        message_box_information_ok(
            self,
            "Customize Report",
            "Layout designer stays parked. Interval, Through, Sort By, and Show Filters "
            "on this A/P Aging Summary change the live report.",
            ok_tip="Close; use Interval / Through / Sort By on the filter bar.",
        )

    def _on_comment(self) -> None:
        message_box_information_ok(
            self,
            "Comment on Report",
            "Report comments are not stored yet.",
            ok_tip="Close; use Excel to export a CSV of this summary.",
        )

    def _on_share(self) -> None:
        message_box_information_ok(
            self,
            "Share Template",
            "Sharing report templates is not wired yet.",
            ok_tip="Close; Memorize is also parked for now.",
        )

    def _on_memorize(self) -> None:
        message_box_information_ok(
            self,
            "Memorize",
            "Memorized reports are not stored yet. Dates, Interval, and Through stay on this screen.",
            ok_tip="Close; Refresh reloads live open bills.",
        )

    def _on_email(self) -> None:
        message_box_information_ok(
            self,
            "E-mail",
            "E-mailing this report is not wired yet. Use Excel to export a CSV.",
            ok_tip="Close; Excel exports UTF-8 with BOM." + CSV_EXPORT_OK_TIP_SUFFIX,
        )

    def _on_print(self) -> None:
        lines = [PLACEHOLDER_COMPANY_NAME, "A/P Aging Summary", self._as_of.text(), ""]
        headers = [self._tree.headerItem().text(c) for c in range(self._tree.columnCount())]
        lines.append("\t".join(headers))

        def walk(item: QTreeWidgetItem, depth: int) -> None:
            indent = "  " * depth
            cells = [indent + item.text(0)]
            for c in range(1, self._tree.columnCount()):
                cells.append(item.text(c))
            lines.append("\t".join(cells))
            for i in range(item.childCount()):
                child = item.child(i)
                if child is not None:
                    walk(child, depth + 1)

        for i in range(self._tree.topLevelItemCount()):
            top = self._tree.topLevelItem(i)
            if top is not None:
                walk(top, 0)
        message_box_information_ok(
            self,
            "Print A/P Aging Summary",
            escape_ampersand_for_qt("\n".join(lines)),
            ok_tip="Close; use Excel to save a CSV for a spreadsheet.",
        )

    def _on_export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export A/P Aging Summary",
            "ap_aging_summary.csv",
            "CSV (*.csv);;All Files (*.*)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        headers = [self._tree.headerItem().text(c) for c in range(self._tree.columnCount())]
        rows: list[list[str]] = []

        def walk(item: QTreeWidgetItem, depth: int) -> None:
            indent = "  " * depth
            row = [indent + item.text(0)]
            for c in range(1, self._tree.columnCount()):
                row.append(item.text(c))
            rows.append(row)
            for i in range(item.childCount()):
                child = item.child(i)
                if child is not None:
                    walk(child, depth + 1)

        for i in range(self._tree.topLevelItemCount()):
            top = self._tree.topLevelItem(i)
            if top is not None:
                walk(top, 0)
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as fp:
                w = csv.writer(fp)
                w.writerow([PLACEHOLDER_COMPANY_NAME])
                w.writerow(["A/P Aging Summary"])
                w.writerow([self._as_of.text()])
                w.writerow([])
                w.writerow(headers)
                w.writerows(rows)
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
            f"Exported {len(rows)} row(s) to:\n{escape_ampersand_for_qt(path)}",
            ok_tip="Close; open the CSV from the path shown." + CSV_EXPORT_OK_TIP_SUFFIX,
        )
