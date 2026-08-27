"""Vendor Center — QuickBooks Pro Desktop vendor list + activity.

Master-detail layout from Johnny's QB Pro Vendor Center (slightly cleaner spacing
than a gray Win32 photocopy — not QBO). Lists live vendors from the company file;
does not seed screenshot names or EINs.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Optional
from urllib.parse import quote

from PySide6.QtCore import QSettings, QUrl, Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices, QKeySequence, QPalette, QShortcut, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from desktop_app.flexible_date import format_iso_to_us_display
from desktop_app.qt_combo_ids import coerce_combo_int_id
from desktop_app.qt_mnemonic import (
    CSV_EXPORT_OK_TIP_SUFFIX,
    escape_ampersand_for_qt,
    message_box_critical_ok,
    message_box_information_ok,
)
from desktop_app.table_clipboard import (
    CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX,
    FloatSortTableItem,
    copy_table_row_as_tsv,
)
from desktop_app.theme import DISABLED_FG
from probooksai import business

_VC_CANVAS = "#E8ECF1"
_VC_PAPER = "#FFFFFF"
_VC_PANEL = "#F4F7FA"
_VC_STRIPE = "#D0E6F4"
_VC_CAPTION = "#4A5560"
_VC_GRID = "#C0C8D0"
_VC_HEADER = "#D8DEE6"
_VC_TEXT = "#1A1A1A"
_VC_TITLE = "#5B6770"
_VC_ACCENT = "#2563A8"
_VC_LINK = "#1A5FA8"
_VC_SELECT = "#C8E6C9"
_VC_EMPTY = "#8A94A0"
WORKFLOW_INPUT_BG = "#FFFFFF"
WORKFLOW_CONTROL_FACE = "#F7F8FA"
WORKFLOW_CONTROL_HOVER = "#E4EEF7"
WORKFLOW_CONTROL_PRESSED = "#C9D8EC"
_STRIP_BTN_OUTLINE = "#B4BCC6"
_TOP_STRIP_RADIUS_PX = 4
_TOP_STRIP_CAPTION_FONT_PX = 10
_TOP_STRIP_BODY_FONT_PX = 12
_FIELD_HEIGHT_PX = 22
_TITLE_FONT_PX = 20
_RIBBON_BTN_HEIGHT_PX = 26
_LINE_ROW_HEIGHT_PX = 22
_VENDOR_HEADER_STATE_KEY = "business/ap_vendor_table_header_state"

_SHOW_ALL = "All"
_SHOW_BILLS = "Bills"
_SHOW_PAYMENTS = "Bill Payments"
_SHOW_CHECKS = "Checks"

_FILTER_ALL = "All Bills"
_FILTER_OPEN = "Open Bills"
_FILTER_OVERDUE = "Overdue Bills"
_FILTER_PAID = "Paid Bills"

_DATE_ALL = "All"
_DATE_MONTH = "This Month"
_DATE_YEAR = "This Year"
_DATE_30 = "Last 30 Days"
_DATE_60 = "Last 60 Days"
_DATE_90 = "Last 90 Days"

_LIST_ACTIVE = "Active Vendors"
_LIST_ALL = "All Vendors"
_LIST_OPEN = "Vendors with Open Balances"

_ROLE_VENDOR_ID = Qt.ItemDataRole.UserRole
_ROLE_KIND = Qt.ItemDataRole.UserRole + 1
_ROLE_RECORD_ID = Qt.ItemDataRole.UserRole + 2

_COL_MARK = 0
_COL_NAME = 1
_COL_BAL = 2
_COL_ATTACH = 3


def _action_button_qss(*, primary: bool = False) -> str:
    r = _TOP_STRIP_RADIUS_PX
    if primary:
        return (
            f"QPushButton {{ background-color: {_VC_ACCENT}; border: 1px solid {_VC_ACCENT}; "
            f"border-radius: {r}px; color: #FFFFFF; "
            f"font-size: {_TOP_STRIP_BODY_FONT_PX}px; padding: 0 14px; font-weight: 600; }}"
            f"QPushButton:hover {{ background-color: #1D4F8C; border: 1px solid #1D4F8C; }}"
            f"QPushButton:pressed {{ background-color: #163E6E; }}"
            f"QPushButton:disabled {{ color: #D7E3F0; background-color: #8AA7C7; "
            f"border: 1px solid #8AA7C7; }}"
        )
    return (
        f"QPushButton {{ background-color: {WORKFLOW_CONTROL_FACE}; border: 1px solid {_STRIP_BTN_OUTLINE}; "
        f"border-radius: {r}px; color: {_VC_TEXT}; "
        f"font-size: {_TOP_STRIP_BODY_FONT_PX}px; padding: 0 12px; }}"
        f"QPushButton:hover {{ background-color: {WORKFLOW_CONTROL_HOVER}; }}"
        f"QPushButton:pressed {{ background-color: {WORKFLOW_CONTROL_PRESSED}; }}"
        f"QPushButton:disabled {{ color: {DISABLED_FG}; background-color: {WORKFLOW_CONTROL_FACE}; }}"
    )


def _tool_button_qss() -> str:
    r = _TOP_STRIP_RADIUS_PX
    return (
        f"QToolButton {{ background-color: {WORKFLOW_CONTROL_FACE}; border: 1px solid {_STRIP_BTN_OUTLINE}; "
        f"border-radius: {r}px; color: {_VC_TEXT}; "
        f"font-size: {_TOP_STRIP_BODY_FONT_PX}px; padding: 0 12px; }}"
        f"QToolButton:hover {{ background-color: {WORKFLOW_CONTROL_HOVER}; }}"
        f"QToolButton:pressed {{ background-color: {WORKFLOW_CONTROL_PRESSED}; }}"
        f"QToolButton::menu-indicator {{ width: 10px; }}"
    )


def _input_qss(widget: str = "QLineEdit") -> str:
    return (
        f"{widget} {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_VC_GRID}; "
        f"padding: 2px 6px; color: {_VC_TEXT}; font-size: {_TOP_STRIP_BODY_FONT_PX}px; }}"
    )


def _link_qss() -> str:
    return (
        f"QPushButton {{ background: transparent; border: none; color: {_VC_LINK}; "
        f"font-size: {_TOP_STRIP_BODY_FONT_PX}px; text-align: left; padding: 0; }}"
        f"QPushButton:hover {{ text-decoration: underline; color: #144A86; }}"
    )


def _light_form_palette() -> QPalette:
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(_VC_PAPER))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(_VC_TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(WORKFLOW_INPUT_BG))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(_VC_STRIPE))
    pal.setColor(QPalette.ColorRole.Text, QColor(_VC_TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(WORKFLOW_CONTROL_FACE))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(_VC_TEXT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(_VC_SELECT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(_VC_TEXT))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(_VC_CAPTION))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(_VC_PANEL))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(_VC_TEXT))
    return pal


def _readonly_item(text: str, *, align_right: bool = False) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    it.setForeground(QColor(_VC_TEXT))
    if align_right:
        it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return it


def _fmt_money(value: float) -> str:
    return f"{value:,.2f}"


def _display_date(iso: str) -> str:
    raw = (iso or "").strip()
    if not raw:
        return ""
    shown = format_iso_to_us_display(raw)
    return shown or raw


def _in_date_range(iso: str, preset: str, today: date) -> bool:
    if preset == _DATE_ALL:
        return True
    raw = (iso or "").strip()[:10]
    if not raw:
        return False
    try:
        d = date.fromisoformat(raw)
    except ValueError:
        return False
    if preset == _DATE_MONTH:
        return d.year == today.year and d.month == today.month
    if preset == _DATE_YEAR:
        return d.year == today.year
    if preset == _DATE_30:
        return d >= today - timedelta(days=30)
    if preset == _DATE_60:
        return d >= today - timedelta(days=60)
    if preset == _DATE_90:
        return d >= today - timedelta(days=90)
    return True


def vendor_center_empty_sentence(show: str, filter_by: str, date_range: str) -> str:
    """QB-style empty grid copy for the current SHOW / FILTER BY / DATE combos."""
    return (
        f"There are no transactions of type '{show}', "
        f"filtered by '{filter_by}', in date range '{date_range}'."
    )


class VendorCenterScreen(QWidget):
    """QB Pro Vendor Center: vendor list, information card, and bill / BILLPMT grid.

    Signals
    -------
    enterBillsRequested
        Open Enter Bills (arg is vendor id, or 0 if none selected).
    payBillsRequested
        Open Pay Bills for the vendor (id or 0).
    billTrackerRequested
        Open Bill Tracker, optionally filtered to the selected vendor.
    writeChecksRequested
        Open Write Checks for the vendor (id or 0).
    openBillRequested
        Double-click a Bill row → Enter Bills for that bill id.
    openPaymentRequested
        Double-click a BILLPMT row → AP payment hook (Pay Bills summary).
    vendorRecordsChanged
        New / edited vendor — Enter Bills and Write Checks should reload payees.
    """

    enterBillsRequested = Signal(int)
    payBillsRequested = Signal(int)
    billTrackerRequested = Signal(int)
    writeChecksRequested = Signal(int)
    openBillRequested = Signal(int)
    openPaymentRequested = Signal(int)
    vendorRecordsChanged = Signal()

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.setObjectName("vendorCenterPage")
        self._conn = conn
        self._vendor_summary_by_id: dict[int, dict] = {}
        self._focused_vendor_id: int | None = None
        self._txn_rows: list[dict] = []
        self.setAutoFillBackground(True)
        self.setPalette(_light_form_palette())
        self.setStyleSheet(
            f"QWidget#vendorCenterPage {{ background: {_VC_CANVAS}; color: {_VC_TEXT}; }}"
        )
        self.setToolTip(
            "Vendor Center: vendor list, balances, and bills / payments. "
            "F5 refreshes when this tab has focus. "
            "CSV exports (toolbar) use UTF-8 BOM for Excel."
        )
        self._build_ui()
        sc = QShortcut(QKeySequence("F5"), self)
        sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc.activated.connect(self._refresh)
        self._refresh()

    # -- chrome --------------------------------------------------------------

    def _style_push(self, b: QPushButton, *, primary: bool = False, height: int = _RIBBON_BTN_HEIGHT_PX) -> None:
        b.setStyleSheet(_action_button_qss(primary=primary))
        b.setFixedHeight(height)
        b.setAutoDefault(False)
        b.setDefault(False)

    def _style_tool(self, b: QToolButton, height: int = _RIBBON_BTN_HEIGHT_PX) -> None:
        b.setStyleSheet(_tool_button_qss())
        b.setFixedHeight(height)
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

    def _caption_field(self, caption: str, widget: QWidget) -> QWidget:
        wrap = QWidget()
        wrap.setObjectName("vendorCenterMetaField")
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)
        lbl = QLabel(caption)
        lbl.setStyleSheet(
            f"color: {_VC_CAPTION}; font-size: {_TOP_STRIP_CAPTION_FONT_PX}px; "
            "font-weight: 700; background: transparent; border: none;"
        )
        lay.addWidget(lbl)
        lay.addWidget(widget)
        return wrap

    def _info_row(self, caption: str, value: QLabel) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        cap = QLabel(caption)
        cap.setFixedWidth(110)
        cap.setStyleSheet(
            f"color: {_VC_CAPTION}; font-size: {_TOP_STRIP_BODY_FONT_PX}px; "
            "background: transparent; border: none;"
        )
        value.setStyleSheet(
            f"color: {_VC_TEXT}; font-size: {_TOP_STRIP_BODY_FONT_PX}px; "
            "background: transparent; border: none;"
        )
        value.setWordWrap(True)
        row.addWidget(cap, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(value, 1)
        return row

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 8)
        outer.setSpacing(6)

        outer.addLayout(self._build_toolbar())

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setObjectName("vendorCenterSplit")
        split.setChildrenCollapsible(False)
        split.setToolTip("Drag to resize the vendor list versus Vendor Information.")
        split.addWidget(self._build_left_pane())
        split.addWidget(self._build_right_pane())
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 5)
        split.setSizes([320, 900])
        outer.addWidget(split, 1)

    def _build_toolbar(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        row.setContentsMargins(0, 0, 0, 2)

        self._btn_new_vendor = QToolButton()
        self._btn_new_vendor.setObjectName("vendorCenterNewVendor")
        self._btn_new_vendor.setText("New Vendor...")
        self._style_tool(self._btn_new_vendor)
        nv_menu = QMenu(self._btn_new_vendor)
        act_nv = nv_menu.addAction("New Vendor...")
        act_nv.setToolTip("Create a vendor record used for AP bills, payments, and 1099-style flags.")
        act_nv.triggered.connect(self._new_v)
        self._btn_new_vendor.setMenu(nv_menu)
        self._btn_new_vendor.setToolTip("Create a new vendor.")
        row.addWidget(self._btn_new_vendor)

        self._btn_new_txn = QToolButton()
        self._btn_new_txn.setObjectName("vendorCenterNewTransactions")
        self._btn_new_txn.setText("New Transactions")
        self._style_tool(self._btn_new_txn)
        txn_menu = QMenu(self._btn_new_txn)
        txn_menu.addAction("Enter Bills", self._on_new_enter_bills)
        txn_menu.addAction("Pay Bills", self._on_new_pay_bills)
        txn_menu.addAction("Write Checks", self._on_new_write_checks)
        self._btn_new_txn.setMenu(txn_menu)
        self._btn_new_txn.setToolTip(
            "Enter Bills, Pay Bills, or Write Checks for the selected vendor."
        )
        row.addWidget(self._btn_new_txn)

        self._btn_print = QToolButton()
        self._btn_print.setObjectName("vendorCenterPrint")
        self._btn_print.setText("Print")
        self._style_tool(self._btn_print)
        print_menu = QMenu(self._btn_print)
        print_menu.addAction("Print vendor list…", self._on_print_vendor_list)
        print_menu.addAction("Print transactions…", self._on_print_transactions)
        self._btn_print.setMenu(print_menu)
        self._btn_print.setToolTip("Print the vendor list or the current transaction grid.")
        row.addWidget(self._btn_print)

        self._btn_excel = QToolButton()
        self._btn_excel.setObjectName("vendorCenterExcel")
        self._btn_excel.setText("Excel")
        self._style_tool(self._btn_excel)
        excel_menu = QMenu(self._btn_excel)
        excel_menu.addAction("Export Vendors CSV…", self._export_vendors)
        self._btn_excel.setMenu(excel_menu)
        self._btn_excel.setToolTip("Export vendors to CSV (UTF-8 BOM for Excel).")
        row.addWidget(self._btn_excel)

        self._btn_word = QToolButton()
        self._btn_word.setObjectName("vendorCenterWord")
        self._btn_word.setText("Word")
        self._style_tool(self._btn_word)
        word_menu = QMenu(self._btn_word)
        word_menu.addAction("Letters…", self._on_word_letters)
        self._btn_word.setMenu(word_menu)
        self._btn_word.setToolTip("Letters for this vendor (not wired yet).")
        row.addWidget(self._btn_word)

        self._btn_bill_tracker = QPushButton("Bill Tracker")
        self._btn_bill_tracker.setObjectName("vendorCenterBillTracker")
        self._style_push(self._btn_bill_tracker)
        self._btn_bill_tracker.setToolTip("Open Bill Tracker for unpaid vendor bills.")
        self._btn_bill_tracker.clicked.connect(self._on_bill_tracker)
        row.addWidget(self._btn_bill_tracker)

        row.addStretch(1)
        return row

    def _build_left_pane(self) -> QWidget:
        pane = QFrame()
        pane.setObjectName("vendorCenterLeft")
        pane.setStyleSheet(
            f"QFrame#vendorCenterLeft {{ background: {_VC_PAPER}; "
            f"border: 1px solid #B7C9DE; border-radius: 6px; }}"
        )
        lay = QVBoxLayout(pane)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        self._left_tabs = QTabWidget()
        self._left_tabs.setObjectName("vendorCenterLeftTabs")
        self._left_tabs.setDocumentMode(True)
        self._left_tabs.setToolTip("Vendors list or all-vendor transactions.")
        # Dummy pages — stacked tables live below; tabs only switch the stack.
        self._left_tabs.addTab(QWidget(), "Vendors")
        self._left_tabs.addTab(QWidget(), "Transactions")
        self._left_tabs.currentChanged.connect(self._on_left_tab_changed)
        lay.addWidget(self._left_tabs)

        filt_row = QHBoxLayout()
        filt_row.setSpacing(6)
        self._list_filter = QComboBox()
        self._list_filter.setObjectName("vendorCenterListFilter")
        self._list_filter.addItems((_LIST_ACTIVE, _LIST_ALL, _LIST_OPEN))
        self._list_filter.setStyleSheet(_input_qss("QComboBox"))
        self._list_filter.setToolTip("Show active vendors, all vendors, or vendors with an open balance.")
        self._list_filter.currentIndexChanged.connect(self._reload_vendor_table)
        filt_row.addWidget(self._list_filter, 1)
        self._search = QLineEdit()
        self._search.setObjectName("vendorCenterSearch")
        self._search.setPlaceholderText("Search")
        self._search.setClearButtonEnabled(True)
        self._search.setStyleSheet(_input_qss())
        self._search.setToolTip("Filter the vendor list by name.")
        self._search.textChanged.connect(self._reload_vendor_table)
        filt_row.addWidget(self._search, 1)
        lay.addLayout(filt_row)

        self._left_stack = QStackedWidget()
        self._vendor_tbl = QTableWidget()
        self._vendor_tbl.setObjectName("vendorCenterVendorTable")
        self._vendor_tbl.setColumnCount(4)
        self._vendor_tbl.setHorizontalHeaderLabels(["", "NAME", "BALANCE TOTAL", "Att"])
        self._vendor_tbl.verticalHeader().setVisible(False)
        self._vendor_tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._vendor_tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._vendor_tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._vendor_tbl.setAlternatingRowColors(True)
        self._vendor_tbl.setSortingEnabled(True)
        hdr = self._vendor_tbl.horizontalHeader()
        hdr.setSectionResizeMode(_COL_MARK, QHeaderView.ResizeMode.Fixed)
        hdr.resizeSection(_COL_MARK, 22)
        hdr.setSectionResizeMode(_COL_NAME, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(_COL_BAL, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_ATTACH, QHeaderView.ResizeMode.Fixed)
        hdr.resizeSection(_COL_ATTACH, 28)
        self._vendor_tbl.setStyleSheet(self._table_qss("vendorCenterVendorTable", selected_green=True))
        self._vendor_tbl.itemSelectionChanged.connect(self._on_vendor_selection_changed)
        self._vendor_tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._vendor_tbl.customContextMenuRequested.connect(self._on_vendor_context_menu)
        self._vendor_tbl.setToolTip(
            "Click a vendor to fill Vendor Information and the transaction grid. "
            "F5 refreshes. CSV exports (toolbar) use UTF-8 BOM for Excel."
        )
        self._vendor_tbl.verticalHeader().setDefaultSectionSize(_LINE_ROW_HEIGHT_PX)

        self._left_txn_tbl = QTableWidget()
        self._left_txn_tbl.setObjectName("vendorCenterLeftTxnTable")
        self._left_txn_tbl.setColumnCount(4)
        self._left_txn_tbl.setHorizontalHeaderLabels(["TYPE", "DATE", "NAME", "AMOUNT"])
        self._left_txn_tbl.verticalHeader().setVisible(False)
        self._left_txn_tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._left_txn_tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._left_txn_tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._left_txn_tbl.setAlternatingRowColors(True)
        self._left_txn_tbl.setStyleSheet(self._table_qss("vendorCenterLeftTxnTable"))
        self._left_txn_tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._left_txn_tbl.itemSelectionChanged.connect(self._on_left_txn_selection_changed)
        self._left_txn_tbl.setToolTip("All vendor bills and payments. Click a row to select that vendor.")
        self._left_txn_tbl.verticalHeader().setDefaultSectionSize(_LINE_ROW_HEIGHT_PX)

        self._left_stack.addWidget(self._vendor_tbl)
        self._left_stack.addWidget(self._left_txn_tbl)
        lay.addWidget(self._left_stack, 1)
        return pane

    def _table_qss(self, object_name: str, *, selected_green: bool = False) -> str:
        sel_bg = _VC_SELECT if selected_green else _VC_ACCENT
        sel_fg = _VC_TEXT if selected_green else "#FFFFFF"
        return f"""
QTableWidget#{object_name} {{
    background: {_VC_PAPER};
    alternate-background-color: {_VC_STRIPE};
    color: {_VC_TEXT};
    gridline-color: {_VC_GRID};
    border: 1px solid {_VC_GRID};
}}
QTableWidget#{object_name}::item:selected {{
    background-color: {sel_bg};
    color: {sel_fg};
}}
QHeaderView::section {{
    background-color: {_VC_HEADER};
    color: {_VC_TEXT};
    padding: 4px 6px;
    border: none;
    border-right: 1px solid {_VC_GRID};
    border-bottom: 1px solid {_VC_GRID};
    font-weight: 700;
    font-size: 11px;
}}
"""

    def _build_right_pane(self) -> QWidget:
        pane = QWidget()
        pane.setObjectName("vendorCenterRight")
        lay = QVBoxLayout(pane)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        vsplit = QSplitter(Qt.Orientation.Vertical)
        vsplit.setChildrenCollapsible(False)
        vsplit.setToolTip("Drag to resize Vendor Information versus the transaction grid.")
        vsplit.addWidget(self._build_info_header())
        vsplit.addWidget(self._build_activity_block())
        vsplit.setStretchFactor(0, 1)
        vsplit.setStretchFactor(1, 3)
        vsplit.setSizes([220, 520])
        lay.addWidget(vsplit, 1)
        lay.addLayout(self._build_footer())
        return pane

    def _build_info_header(self) -> QWidget:
        box = QFrame()
        box.setObjectName("vendorCenterInfo")
        box.setStyleSheet(
            f"QFrame#vendorCenterInfo {{ background: {_VC_PAPER}; "
            f"border: 1px solid #B7C9DE; border-radius: 6px; }}"
        )
        box.setToolTip("Contact fields from the vendor master; balances from open bills and payments.")
        grid = QGridLayout(box)
        grid.setContentsMargins(12, 8, 12, 8)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(4)

        title_row = QHBoxLayout()
        title = QLabel("Vendor Information")
        title.setObjectName("vendorCenterInfoTitle")
        title.setStyleSheet(
            f"color: {_VC_TITLE}; font-size: {_TITLE_FONT_PX}px; font-weight: 600; "
            "background: transparent; border: none;"
        )
        title_row.addWidget(title)
        title_row.addStretch(1)
        self._btn_attach = QPushButton("Attach")
        self._btn_attach.setObjectName("vendorCenterAttach")
        self._btn_attach.setFixedHeight(24)
        self._btn_attach.setStyleSheet(_action_button_qss())
        self._btn_attach.setToolTip("Attachments for this vendor (stored on bills when present).")
        self._btn_attach.clicked.connect(self._on_attach_hint)
        title_row.addWidget(self._btn_attach)
        self._btn_edit = QPushButton("Edit")
        self._btn_edit.setObjectName("vendorCenterEdit")
        self._btn_edit.setFixedHeight(24)
        self._btn_edit.setStyleSheet(_action_button_qss())
        self._btn_edit.setToolTip("Edit name, contact, 1099 flag, and notes for this vendor.")
        self._btn_edit.clicked.connect(self._edit_v)
        title_row.addWidget(self._btn_edit)
        grid.addLayout(title_row, 0, 0, 1, 2)

        details = QVBoxLayout()
        details.setSpacing(4)
        self._d_company = QLabel("—")
        self._d_full_name = QLabel("—")
        self._d_billed = QLabel("—")
        self._d_billed.setWordWrap(True)
        details.addLayout(self._info_row("Company Name", self._d_company))
        details.addLayout(self._info_row("Full Name", self._d_full_name))
        details.addLayout(self._info_row("Billed From", self._d_billed))
        map_row = QHBoxLayout()
        map_row.addSpacing(118)
        self._btn_map = QPushButton("Map")
        self._btn_map.setObjectName("vendorCenterMap")
        self._btn_map.setStyleSheet(_link_qss())
        self._btn_map.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_map.setToolTip("Open a map search for the billed-from address.")
        self._btn_map.clicked.connect(self._on_map)
        self._btn_directions = QPushButton("Directions")
        self._btn_directions.setObjectName("vendorCenterDirections")
        self._btn_directions.setStyleSheet(_link_qss())
        self._btn_directions.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_directions.setToolTip("Open directions to the billed-from address.")
        self._btn_directions.clicked.connect(self._on_directions)
        map_row.addWidget(self._btn_map)
        map_row.addSpacing(12)
        map_row.addWidget(self._btn_directions)
        map_row.addStretch(1)
        details.addLayout(map_row)
        details.addStretch(1)
        details_w = QWidget()
        details_w.setLayout(details)
        grid.addWidget(details_w, 1, 0)

        side = QVBoxLayout()
        side.setSpacing(6)
        note_cap = QLabel("NOTE")
        note_cap.setStyleSheet(
            f"color: {_VC_CAPTION}; font-size: {_TOP_STRIP_CAPTION_FONT_PX}px; "
            "font-weight: 700; background: transparent;"
        )
        side.addWidget(note_cap)
        self._d_note = QLabel("No note available")
        self._d_note.setObjectName("vendorCenterNote")
        self._d_note.setWordWrap(True)
        self._d_note.setMinimumHeight(48)
        self._d_note.setStyleSheet(
            f"color: {_VC_TEXT}; font-size: {_TOP_STRIP_BODY_FONT_PX}px; "
            f"background: {_VC_PANEL}; border: 1px solid {_VC_GRID}; padding: 6px;"
        )
        self._d_note.setToolTip("Internal notes from the vendor record.")
        side.addWidget(self._d_note)
        rpt = QLabel("REPORTS FOR THIS VENDOR")
        rpt.setStyleSheet(
            f"color: {_VC_CAPTION}; font-size: {_TOP_STRIP_CAPTION_FONT_PX}px; "
            "font-weight: 700; background: transparent;"
        )
        side.addWidget(rpt)
        rpt_row = QHBoxLayout()
        self._btn_quickreport = QPushButton("QuickReport")
        self._btn_quickreport.setObjectName("vendorCenterQuickReport")
        self._btn_quickreport.setStyleSheet(_link_qss())
        self._btn_quickreport.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_quickreport.setToolTip("Show all bills and payments for this vendor.")
        self._btn_quickreport.clicked.connect(self._on_quickreport)
        self._btn_open_bal = QPushButton("Open Balance")
        self._btn_open_bal.setObjectName("vendorCenterOpenBalance")
        self._btn_open_bal.setStyleSheet(_link_qss())
        self._btn_open_bal.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_open_bal.setToolTip("Show open bills for this vendor.")
        self._btn_open_bal.clicked.connect(self._on_open_balance_report)
        rpt_row.addWidget(self._btn_quickreport)
        rpt_row.addSpacing(12)
        rpt_row.addWidget(self._btn_open_bal)
        rpt_row.addStretch(1)
        side.addLayout(rpt_row)
        self._btn_1099 = QPushButton("Order 1099 Forms")
        self._btn_1099.setObjectName("vendorCenterOrder1099")
        self._style_push(self._btn_1099, height=24)
        self._btn_1099.setToolTip("1099 form ordering is not wired yet.")
        self._btn_1099.clicked.connect(self._on_order_1099)
        side.addWidget(self._btn_1099)
        self._btn_order_checks = QPushButton("Order Checks")
        self._btn_order_checks.setObjectName("vendorCenterOrderChecks")
        self._style_push(self._btn_order_checks, height=24)
        self._btn_order_checks.setToolTip("Check ordering is not wired yet.")
        self._btn_order_checks.clicked.connect(self._on_order_checks)
        side.addWidget(self._btn_order_checks)
        side.addStretch(1)
        side_w = QWidget()
        side_w.setLayout(side)
        side_w.setMinimumWidth(220)
        grid.addWidget(side_w, 1, 1)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)
        return box

    def _build_activity_block(self) -> QWidget:
        wrap = QFrame()
        wrap.setObjectName("vendorCenterActivity")
        wrap.setStyleSheet(
            f"QFrame#vendorCenterActivity {{ background: {_VC_PAPER}; "
            f"border: 1px solid #B7C9DE; border-radius: 6px; }}"
        )
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(8, 4, 8, 8)
        lay.setSpacing(6)

        self._right_tabs = QTabWidget()
        self._right_tabs.setObjectName("vendorCenterRightTabs")
        self._right_tabs.setDocumentMode(True)
        self._right_tabs.setToolTip("Transactions, contacts, to do's, notes, and sent email for this vendor.")

        txn_page = QWidget()
        txn_lay = QVBoxLayout(txn_page)
        txn_lay.setContentsMargins(0, 6, 0, 0)
        txn_lay.setSpacing(6)
        filt = QHBoxLayout()
        filt.setSpacing(12)
        self._show = QComboBox()
        self._show.setObjectName("vendorCenterShow")
        self._show.addItems((_SHOW_BILLS, _SHOW_PAYMENTS, _SHOW_CHECKS, _SHOW_ALL))
        self._show.setStyleSheet(_input_qss("QComboBox"))
        self._show.setToolTip("Which transaction types to list.")
        self._show.currentIndexChanged.connect(self._reload_txn_table)
        filt.addWidget(self._caption_field("SHOW", self._show))
        self._filter_by = QComboBox()
        self._filter_by.setObjectName("vendorCenterFilterBy")
        self._filter_by.addItems((_FILTER_ALL, _FILTER_OPEN, _FILTER_OVERDUE, _FILTER_PAID))
        self._filter_by.setStyleSheet(_input_qss("QComboBox"))
        self._filter_by.setToolTip("Open, overdue, paid, or all bills.")
        self._filter_by.currentIndexChanged.connect(self._reload_txn_table)
        filt.addWidget(self._caption_field("FILTER BY", self._filter_by))
        self._date_range = QComboBox()
        self._date_range.setObjectName("vendorCenterDate")
        self._date_range.addItems((_DATE_ALL, _DATE_MONTH, _DATE_YEAR, _DATE_30, _DATE_60, _DATE_90))
        self._date_range.setStyleSheet(_input_qss("QComboBox"))
        self._date_range.setToolTip("Limit the grid to a date range.")
        self._date_range.currentIndexChanged.connect(self._reload_txn_table)
        filt.addWidget(self._caption_field("DATE", self._date_range))
        filt.addStretch(1)
        txn_lay.addLayout(filt)

        self._txn_stack = QStackedWidget()
        self._txn_tbl = QTableWidget()
        self._txn_tbl.setObjectName("vendorCenterTxnTable")
        self._txn_tbl.setColumnCount(7)
        self._txn_tbl.setHorizontalHeaderLabels(
            ["TYPE", "NUM", "DATE", "DUE DATE", "AGING", "AMOUNT", "OPEN BALANCE"]
        )
        self._txn_tbl.verticalHeader().setVisible(False)
        self._txn_tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._txn_tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._txn_tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._txn_tbl.setAlternatingRowColors(True)
        self._txn_tbl.setSortingEnabled(True)
        self._txn_tbl.setStyleSheet(self._table_qss("vendorCenterTxnTable"))
        th = self._txn_tbl.horizontalHeader()
        th.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        th.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        th.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        th.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        th.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        th.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        th.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self._txn_tbl.cellDoubleClicked.connect(self._on_txn_double_clicked)
        self._txn_tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._txn_tbl.customContextMenuRequested.connect(self._on_txn_context_menu)
        self._txn_tbl.setToolTip(
            "Bills and bill payments for the selected vendor. Double-click a Bill to open Enter Bills; "
            "double-click BILLPMT to open the payment hook. F5 refreshes."
        )
        self._txn_tbl.verticalHeader().setDefaultSectionSize(_LINE_ROW_HEIGHT_PX)
        self._txn_tbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        empty_page = QWidget()
        empty_page.setStyleSheet(f"background: {_VC_PAPER};")
        empty_lay = QVBoxLayout(empty_page)
        self._txn_empty = QLabel("")
        self._txn_empty.setObjectName("vendorCenterEmpty")
        self._txn_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._txn_empty.setWordWrap(True)
        self._txn_empty.setStyleSheet(
            f"color: {_VC_EMPTY}; font-size: 13px; background: transparent;"
        )
        empty_lay.addStretch(1)
        empty_lay.addWidget(self._txn_empty)
        empty_lay.addStretch(1)
        self._txn_stack.addWidget(self._txn_tbl)
        self._txn_stack.addWidget(empty_page)
        txn_lay.addWidget(self._txn_stack, 1)
        self._right_tabs.addTab(txn_page, "Transactions")

        self._contacts_page = self._placeholder_page(
            "contacts",
            "Contacts for this vendor (name, email, phone from the vendor record).",
        )
        self._right_tabs.addTab(self._contacts_page, "Contacts")
        self._todos_page = self._placeholder_page(
            "todos",
            "No to do's for this vendor.",
        )
        self._right_tabs.addTab(self._todos_page, "To Do's")
        notes_page = QWidget()
        notes_lay = QVBoxLayout(notes_page)
        notes_lay.setContentsMargins(8, 8, 8, 8)
        self._notes_body = QPlainTextEdit()
        self._notes_body.setObjectName("vendorCenterNotesBody")
        self._notes_body.setReadOnly(True)
        self._notes_body.setStyleSheet(_input_qss("QPlainTextEdit"))
        self._notes_body.setToolTip("Internal notes. Use the pencil to edit the vendor record.")
        notes_lay.addWidget(self._notes_body)
        self._right_tabs.addTab(notes_page, "Notes")
        self._email_page = self._placeholder_page(
            "email",
            "No sent email for this vendor.",
        )
        self._right_tabs.addTab(self._email_page, "Sent Email")
        lay.addWidget(self._right_tabs, 1)
        return wrap

    def _placeholder_page(self, name: str, message: str) -> QWidget:
        w = QWidget()
        w.setObjectName(f"vendorCenterTab_{name}")
        lay = QVBoxLayout(w)
        lbl = QLabel(message)
        lbl.setObjectName(f"vendorCenterTabLabel_{name}")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {_VC_EMPTY}; font-size: 13px; background: transparent;")
        lay.addStretch(1)
        lay.addWidget(lbl)
        lay.addStretch(1)
        return w

    def _build_footer(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        self._btn_manage = QToolButton()
        self._btn_manage.setObjectName("vendorCenterManage")
        self._btn_manage.setText("Manage Transactions")
        self._style_tool(self._btn_manage)
        m = QMenu(self._btn_manage)
        m.addAction("Edit Transaction", self._on_edit_selected_txn)
        m.addAction("Enter Bills", self._on_new_enter_bills)
        m.addAction("Pay Bills", self._on_new_pay_bills)
        self._btn_manage.setMenu(m)
        self._btn_manage.setToolTip("Edit the selected row or enter / pay bills for this vendor.")
        row.addWidget(self._btn_manage)

        self._btn_run_reports = QToolButton()
        self._btn_run_reports.setObjectName("vendorCenterRunReports")
        self._btn_run_reports.setText("Run Reports")
        self._style_tool(self._btn_run_reports)
        rm = QMenu(self._btn_run_reports)
        rm.addAction("QuickReport", self._on_quickreport)
        rm.addAction("Open Balance", self._on_open_balance_report)
        self._btn_run_reports.setMenu(rm)
        self._btn_run_reports.setToolTip("QuickReport and Open Balance for this vendor.")
        row.addWidget(self._btn_run_reports)

        self._btn_online = QPushButton("Schedule Online Payment")
        self._btn_online.setObjectName("vendorCenterOnlinePay")
        self._style_push(self._btn_online)
        self._btn_online.setToolTip("Opens Pay Bills for this vendor (online bill pay is not a separate screen).")
        self._btn_online.clicked.connect(self._on_new_pay_bills)
        row.addWidget(self._btn_online)
        row.addStretch(1)
        return row

    # -- data ----------------------------------------------------------------

    def persist_header_state(self) -> None:
        QSettings().setValue(
            _VENDOR_HEADER_STATE_KEY,
            self._vendor_tbl.horizontalHeader().saveState(),
        )

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        raw = QSettings().value(_VENDOR_HEADER_STATE_KEY)
        if raw:
            self._vendor_tbl.horizontalHeader().restoreState(raw)
        self._refresh()

    def _focused_id(self) -> int:
        return int(self._focused_vendor_id or 0)

    def _on_left_tab_changed(self, index: int) -> None:
        self._left_stack.setCurrentIndex(0 if index <= 0 else 1)
        if index == 1:
            self._reload_left_txn_table()

    def _on_vendor_selection_changed(self) -> None:
        rows = self._vendor_tbl.selectionModel().selectedRows() if self._vendor_tbl.selectionModel() else []
        if not rows:
            return
        it = self._vendor_tbl.item(rows[0].row(), _COL_NAME)
        if it is None:
            return
        vid = coerce_combo_int_id(it.data(_ROLE_VENDOR_ID))
        if vid is None:
            return
        self._focused_vendor_id = vid
        self._apply_detail_from_focus()
        self._reload_txn_table()

    def _on_left_txn_selection_changed(self) -> None:
        rows = (
            self._left_txn_tbl.selectionModel().selectedRows()
            if self._left_txn_tbl.selectionModel()
            else []
        )
        if not rows:
            return
        it = self._left_txn_tbl.item(rows[0].row(), 0)
        if it is None:
            return
        vid = coerce_combo_int_id(it.data(_ROLE_VENDOR_ID))
        if vid is None:
            return
        self._focused_vendor_id = vid
        self._select_vendor_row(vid)
        self._apply_detail_from_focus()
        self._reload_txn_table()

    def _on_vendor_context_menu(self, pos) -> None:
        idx = self._vendor_tbl.indexAt(pos)
        m = QMenu(self)
        if idx.isValid():
            act = m.addAction("Copy row", lambda r=idx.row(): copy_table_row_as_tsv(self._vendor_tbl, r))
            act.setToolTip(
                "Copy this vendor row as tab-separated text. " + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
            )
            m.addSeparator()
        m.addAction("New Vendor...", self._new_v)
        m.addAction("Edit Vendor...", self._edit_v)
        m.exec(self._vendor_tbl.viewport().mapToGlobal(pos))

    def _on_txn_context_menu(self, pos) -> None:
        idx = self._txn_tbl.indexAt(pos)
        m = QMenu(self)
        if idx.isValid():
            act = m.addAction("Copy row", lambda r=idx.row(): copy_table_row_as_tsv(self._txn_tbl, r))
            act.setToolTip(
                "Copy this transaction row as tab-separated text. " + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
            )
            m.addAction("Edit Transaction", self._on_edit_selected_txn)
            m.addSeparator()
        m.addAction("Enter Bills", self._on_new_enter_bills)
        m.addAction("Pay Bills", self._on_new_pay_bills)
        m.exec(self._txn_tbl.viewport().mapToGlobal(pos))

    def _refresh(self) -> None:
        if self._conn is None:
            self._vendor_summary_by_id = {}
            self._reload_vendor_table()
            return
        try:
            rows = business.list_vendor_ap_summaries(self._conn)
        except sqlite3.Error:
            rows = []
        self._vendor_summary_by_id = {int(r["vendor_id"]): r for r in rows}
        self._reload_vendor_table()
        if self._left_tabs.currentIndex() == 1:
            self._reload_left_txn_table()

    def _vendor_has_attachment(self, vendor_id: int) -> bool:
        try:
            row = self._conn.execute(
                """
                SELECT 1 FROM bills
                WHERE vendor_id = ? AND TRIM(COALESCE(attachment_path, '')) != ''
                LIMIT 1
                """,
                (vendor_id,),
            ).fetchone()
        except sqlite3.Error:
            return False
        return row is not None

    def _reload_vendor_table(self) -> None:
        q = (self._search.text() or "").strip().lower()
        mode = self._list_filter.currentText()
        rows = list(self._vendor_summary_by_id.values())
        if q:
            rows = [r for r in rows if q in (r.get("vendor_name") or "").lower()]
        if mode == _LIST_OPEN:
            rows = [r for r in rows if float(r.get("open_balance") or 0) > 0.005]
        rows.sort(key=lambda r: (r.get("vendor_name") or "").lower())
        self._vendor_tbl.setSortingEnabled(False)
        self._vendor_tbl.setRowCount(len(rows))
        for i, r in enumerate(rows):
            vid = int(r["vendor_id"])
            nm = r.get("vendor_name") or ""
            ob = float(r.get("open_balance") or 0)
            mark = "◆" if ob > 0.005 else ""
            it0 = _readonly_item(mark)
            it0.setData(_ROLE_VENDOR_ID, vid)
            self._vendor_tbl.setItem(i, _COL_MARK, it0)
            it1 = _readonly_item(escape_ampersand_for_qt(nm))
            it1.setData(_ROLE_VENDOR_ID, vid)
            self._vendor_tbl.setItem(i, _COL_NAME, it1)
            it2 = FloatSortTableItem(_fmt_money(ob), ob)
            it2.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            it2.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            it2.setData(_ROLE_VENDOR_ID, vid)
            self._vendor_tbl.setItem(i, _COL_BAL, it2)
            clip = "•" if self._vendor_has_attachment(vid) else ""
            it3 = _readonly_item(clip)
            it3.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it3.setData(_ROLE_VENDOR_ID, vid)
            self._vendor_tbl.setItem(i, _COL_ATTACH, it3)
        self._vendor_tbl.setSortingEnabled(True)
        ids = {int(r["vendor_id"]) for r in rows}
        if self._focused_vendor_id is not None and self._focused_vendor_id not in ids:
            self._focused_vendor_id = None
        if self._focused_vendor_id is None and rows:
            self._focused_vendor_id = int(rows[0]["vendor_id"])
        if self._focused_vendor_id is not None:
            self._select_vendor_row(self._focused_vendor_id)
        else:
            self._vendor_tbl.clearSelection()
        self._apply_detail_from_focus()
        self._reload_txn_table()

    def _select_vendor_row(self, vendor_id: int) -> None:
        self._vendor_tbl.blockSignals(True)
        try:
            for row in range(self._vendor_tbl.rowCount()):
                it = self._vendor_tbl.item(row, _COL_NAME)
                if it is None:
                    continue
                if coerce_combo_int_id(it.data(_ROLE_VENDOR_ID)) == vendor_id:
                    self._vendor_tbl.selectRow(row)
                    break
        finally:
            self._vendor_tbl.blockSignals(False)

    def _apply_detail_from_focus(self) -> None:
        if self._focused_vendor_id is None or self._conn is None:
            self._clear_detail_card()
            return
        v = business.get_vendor(self._conn, self._focused_vendor_id)
        if v is None:
            self._clear_detail_card()
            return
        d = dict(v)
        name = (d.get("name") or "").strip() or "—"
        addr = (d.get("address") or "").strip()
        email = (d.get("email") or "").strip()
        phone = (d.get("phone") or "").strip()
        notes = (d.get("notes") or "").strip()
        billed_lines = [name]
        if addr:
            billed_lines.append(addr)
        self._d_company.setText(escape_ampersand_for_qt(name))
        self._d_full_name.setText(escape_ampersand_for_qt(name))
        self._d_billed.setText(escape_ampersand_for_qt("\n".join(billed_lines)))
        self._d_note.setText(escape_ampersand_for_qt(notes) if notes else "No note available")
        contact_bits = [name]
        if email:
            contact_bits.append(email)
        if phone:
            contact_bits.append(phone)
        if addr:
            contact_bits.append(addr)
        contacts_lbl = self._contacts_page.findChild(QLabel, "vendorCenterTabLabel_contacts")
        if contacts_lbl is not None:
            contacts_lbl.setText("\n".join(contact_bits) if name != "—" else "No contacts for this vendor.")
        self._notes_body.setPlainText(notes)

    def _clear_detail_card(self) -> None:
        self._d_company.setText("—")
        self._d_full_name.setText("—")
        self._d_billed.setText("—")
        self._d_note.setText("No note available")
        self._notes_body.setPlainText("")
        contacts_lbl = self._contacts_page.findChild(QLabel, "vendorCenterTabLabel_contacts")
        if contacts_lbl is not None:
            contacts_lbl.setText("Contacts for this vendor (name, email, phone from the vendor record).")

    def _passes_txn_filters(self, row: dict) -> bool:
        kind = row.get("kind") or ""
        show = self._show.currentText()
        if show == _SHOW_BILLS and kind != "bill":
            return False
        if show == _SHOW_PAYMENTS and kind != "billpmt":
            return False
        if show == _SHOW_CHECKS:
            return False
        filt = self._filter_by.currentText()
        if kind == "bill":
            bal = float(row.get("open_balance") or 0)
            aging = (row.get("aging") or "").strip()
            if filt == _FILTER_OPEN and bal <= 0.005:
                return False
            if filt == _FILTER_OVERDUE and not aging:
                return False
            if filt == _FILTER_PAID and bal > 0.005:
                return False
        elif filt in (_FILTER_OPEN, _FILTER_OVERDUE, _FILTER_PAID) and kind == "billpmt":
            if filt != _FILTER_PAID:
                return False
        if not _in_date_range(row.get("date") or "", self._date_range.currentText(), date.today()):
            return False
        return True

    def _reload_txn_table(self) -> None:
        if self._focused_vendor_id is None:
            self._txn_rows = []
            visible: list[dict] = []
        elif self._conn is None:
            self._txn_rows = []
            visible = []
        else:
            try:
                self._txn_rows = business.list_vendor_center_transactions(
                    self._conn, self._focused_vendor_id
                )
            except sqlite3.Error:
                self._txn_rows = []
            visible = [r for r in self._txn_rows if self._passes_txn_filters(r)]
        self._fill_txn_table(self._txn_tbl, visible, include_vendor=False)
        empty = vendor_center_empty_sentence(
            self._show.currentText(),
            self._filter_by.currentText(),
            self._date_range.currentText(),
        )
        self._txn_empty.setText(empty)
        self._txn_stack.setCurrentIndex(1 if not visible else 0)

    def _reload_left_txn_table(self) -> None:
        if self._conn is None:
            rows: list[dict] = []
        else:
            try:
                rows = business.list_vendor_center_transactions(self._conn, None)
            except sqlite3.Error:
                rows = []
        self._fill_txn_table(self._left_txn_tbl, rows, include_vendor=True)

    def _fill_txn_table(
        self, tbl: QTableWidget, rows: list[dict], *, include_vendor: bool
    ) -> None:
        tbl.setSortingEnabled(False)
        if include_vendor:
            tbl.setRowCount(len(rows))
            for i, r in enumerate(rows):
                it0 = _readonly_item(r.get("type") or "")
                it0.setData(_ROLE_VENDOR_ID, int(r["vendor_id"]))
                it0.setData(_ROLE_KIND, r.get("kind") or "")
                it0.setData(_ROLE_RECORD_ID, int(r["record_id"]))
                tbl.setItem(i, 0, it0)
                tbl.setItem(i, 1, _readonly_item(_display_date(r.get("date") or "")))
                tbl.setItem(i, 2, _readonly_item(escape_ampersand_for_qt(r.get("vendor_name") or "")))
                amt = float(r.get("amount") or 0)
                amt_it = FloatSortTableItem(_fmt_money(amt), amt)
                amt_it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                amt_it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                tbl.setItem(i, 3, amt_it)
        else:
            tbl.setRowCount(len(rows))
            for i, r in enumerate(rows):
                it0 = _readonly_item(r.get("type") or "")
                it0.setData(_ROLE_VENDOR_ID, int(r["vendor_id"]))
                it0.setData(_ROLE_KIND, r.get("kind") or "")
                it0.setData(_ROLE_RECORD_ID, int(r["record_id"]))
                tbl.setItem(i, 0, it0)
                tbl.setItem(i, 1, _readonly_item(r.get("num") or ""))
                tbl.setItem(i, 2, _readonly_item(_display_date(r.get("date") or "")))
                tbl.setItem(i, 3, _readonly_item(_display_date(r.get("due_date") or "")))
                tbl.setItem(i, 4, _readonly_item(r.get("aging") or ""))
                amt = float(r.get("amount") or 0)
                ob = float(r.get("open_balance") or 0)
                amt_it = FloatSortTableItem(_fmt_money(amt), amt)
                amt_it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                amt_it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                tbl.setItem(i, 5, amt_it)
                ob_it = FloatSortTableItem(_fmt_money(ob), ob)
                ob_it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                ob_it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                tbl.setItem(i, 6, ob_it)
        tbl.setSortingEnabled(True)

    def _selected_txn(self) -> Optional[tuple[str, int]]:
        row = self._txn_tbl.currentRow()
        if row < 0:
            return None
        it = self._txn_tbl.item(row, 0)
        if it is None:
            return None
        kind = it.data(_ROLE_KIND)
        rid = coerce_combo_int_id(it.data(_ROLE_RECORD_ID))
        if not isinstance(kind, str) or rid is None:
            return None
        return kind, rid

    def _on_txn_double_clicked(self, row: int, _col: int) -> None:
        it = self._txn_tbl.item(row, 0)
        if it is None:
            return
        kind = it.data(_ROLE_KIND)
        rid = coerce_combo_int_id(it.data(_ROLE_RECORD_ID))
        if rid is None:
            return
        if kind == "bill":
            self.openBillRequested.emit(rid)
        elif kind == "billpmt":
            self.openPaymentRequested.emit(rid)

    def _on_edit_selected_txn(self) -> None:
        picked = self._selected_txn()
        if picked is None:
            message_box_information_ok(
                self,
                "Manage Transactions",
                "Select a bill or bill payment row first.",
                ok_tip="Close; click a row in the transaction grid.",
            )
            return
        kind, rid = picked
        if kind == "bill":
            self.openBillRequested.emit(rid)
        else:
            self.openPaymentRequested.emit(rid)

    def _on_new_enter_bills(self) -> None:
        self.enterBillsRequested.emit(self._focused_id())

    def _on_new_pay_bills(self) -> None:
        self.payBillsRequested.emit(self._focused_id())

    def _on_bill_tracker(self) -> None:
        self.billTrackerRequested.emit(self._focused_id())

    def _on_new_write_checks(self) -> None:
        self.writeChecksRequested.emit(self._focused_id())

    def _on_quickreport(self) -> None:
        self._right_tabs.setCurrentIndex(0)
        self._show.setCurrentText(_SHOW_ALL)
        self._filter_by.setCurrentText(_FILTER_ALL)
        self._date_range.setCurrentText(_DATE_ALL)

    def _on_open_balance_report(self) -> None:
        self._right_tabs.setCurrentIndex(0)
        self._show.setCurrentText(_SHOW_BILLS)
        self._filter_by.setCurrentText(_FILTER_OPEN)
        self._date_range.setCurrentText(_DATE_ALL)

    def _vendor_address(self) -> str:
        if self._focused_vendor_id is None:
            return ""
        v = business.get_vendor(self._conn, self._focused_vendor_id)
        if v is None:
            return ""
        return (dict(v).get("address") or "").strip()

    def _open_maps(self, *, directions: bool) -> None:
        addr = self._vendor_address()
        if not addr:
            message_box_information_ok(
                self,
                "Map",
                "Add an address on this vendor to use Map / Directions.",
                ok_tip="Close; use the pencil to edit the vendor address.",
            )
            return
        q = quote(addr)
        url = (
            f"https://www.google.com/maps/dir/?api=1&destination={q}"
            if directions
            else f"https://www.google.com/maps/search/?api=1&query={q}"
        )
        QDesktopServices.openUrl(QUrl(url))

    def _on_map(self) -> None:
        self._open_maps(directions=False)

    def _on_directions(self) -> None:
        self._open_maps(directions=True)

    def _on_attach_hint(self) -> None:
        message_box_information_ok(
            self,
            "Attachments",
            "Vendor attachments are stored on individual bills (Enter Bills). "
            "A paperclip on the vendor list means at least one bill has a file.",
            ok_tip="Close; open a bill from the transaction grid to see its attachment.",
        )

    def _on_order_1099(self) -> None:
        message_box_information_ok(
            self,
            "Order 1099 Forms",
            "Ordering 1099 forms is not wired yet. Mark 1099 vendors with the edit pencil.",
            ok_tip="Close; 1099 filing remains on the vendor record.",
        )

    def _on_order_checks(self) -> None:
        message_box_information_ok(
            self,
            "Order Checks",
            "Ordering checks is not wired yet. Use Write Checks to record a payment.",
            ok_tip="Close; New Transactions → Write Checks opens the check form.",
        )

    def _on_word_letters(self) -> None:
        message_box_information_ok(
            self,
            "Word",
            "Vendor letters (Word) are not wired yet.",
            ok_tip="Close; use Print for a vendor list or transaction grid.",
        )

    def _on_print_vendor_list(self) -> None:
        names = []
        for row in range(self._vendor_tbl.rowCount()):
            it = self._vendor_tbl.item(row, _COL_NAME)
            bal = self._vendor_tbl.item(row, _COL_BAL)
            if it is None:
                continue
            names.append(f"{it.text()}\t{bal.text() if bal is not None else ''}")
        body = "\n".join(names) if names else "(no vendors)"
        message_box_information_ok(
            self,
            "Print vendor list",
            escape_ampersand_for_qt(body),
            ok_tip="Close; use Excel to export a CSV for a spreadsheet.",
        )

    def _on_print_transactions(self) -> None:
        lines = []
        for row in range(self._txn_tbl.rowCount()):
            cells = []
            for col in range(self._txn_tbl.columnCount()):
                it = self._txn_tbl.item(row, col)
                cells.append(it.text() if it is not None else "")
            lines.append("\t".join(cells))
        body = "\n".join(lines) if lines else self._txn_empty.text() or "(no transactions)"
        message_box_information_ok(
            self,
            "Print transactions",
            escape_ampersand_for_qt(body),
            ok_tip="Close; double-click a Bill row to open Enter Bills.",
        )

    def _new_v(self) -> None:
        from desktop_app.extra_tabs import run_new_vendor_dialog

        vid = run_new_vendor_dialog(self, self._conn)
        if not vid:
            return
        self._focused_vendor_id = int(vid)
        self.vendorRecordsChanged.emit()
        self._refresh()

    def _edit_v(self) -> None:
        from desktop_app.extra_tabs import run_edit_vendor_dialog

        if run_edit_vendor_dialog(self, self._conn, self._focused_vendor_id):
            self.vendorRecordsChanged.emit()
            self._refresh()

    def _export_vendors(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export vendors", "vendors.csv", "CSV (*.csv)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            n = business.write_vendors_csv(self._conn, path)
        except OSError as exc:
            message_box_critical_ok(
                self,
                "Export failed",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; check path, permissions, and disk space.",
            )
            return
        message_box_information_ok(
            self,
            "Export",
            f"Exported {n} vendor(s) to {escape_ampersand_for_qt(path)}",
            ok_tip="Close; open the CSV from the path shown." + CSV_EXPORT_OK_TIP_SUFFIX,
        )
