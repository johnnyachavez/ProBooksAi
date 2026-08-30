"""Customer Center — QuickBooks Pro Desktop customer/job list + activity.

Master-detail layout from Johnny's QB Pro Customer Center (slightly cleaner spacing
than a gray Win32 photocopy — not QBO). Lists live customers from the company file;
does not seed screenshot names, invoice numbers, or EINs.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Optional

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QPalette, QShortcut, QShowEvent
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
    message_box_warning_ok,
)
from desktop_app.table_clipboard import (
    CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX,
    FloatSortTableItem,
    copy_table_row_as_tsv,
)
from desktop_app.theme import DISABLED_FG
from probooksai import business

_CC_CANVAS = "#E8ECF1"
_CC_PAPER = "#FFFFFF"
_CC_PANEL = "#F4F7FA"
_CC_STRIPE = "#D0E6F4"
_CC_CAPTION = "#4A5560"
_CC_GRID = "#C0C8D0"
_CC_HEADER = "#D8DEE6"
_CC_TEXT = "#1A1A1A"
_CC_TITLE = "#5B6770"
_CC_ACCENT = "#2563A8"
_CC_LINK = "#1A5FA8"
_CC_SELECT = "#C8E6C9"
_CC_EMPTY = "#8A94A0"
WORKFLOW_INPUT_BG = "#FFFFFF"
WORKFLOW_CONTROL_FACE = "#F7F8FA"
WORKFLOW_CONTROL_HOVER = "#E4EEF7"
WORKFLOW_CONTROL_PRESSED = "#C9D8EC"
_STRIP_BTN_OUTLINE = "#B4BCC6"
_TOP_STRIP_RADIUS_PX = 4
_TOP_STRIP_CAPTION_FONT_PX = 10
_TOP_STRIP_BODY_FONT_PX = 12
_TITLE_FONT_PX = 20
_RIBBON_BTN_HEIGHT_PX = 26
_LINE_ROW_HEIGHT_PX = 22
_CUSTOMER_HEADER_STATE_KEY = "business/ar_customer_table_header_state"

_SHOW_ALL = "All"
_SHOW_INVOICES = "Invoices"
_SHOW_PAYMENTS = "Payments"

_FILTER_ALL = "All Invoices"
_FILTER_OPEN = "Open Invoices"
_FILTER_OVERDUE = "Overdue Invoices"
_FILTER_PAID = "Paid Invoices"

_DATE_ALL = "All"
_DATE_MONTH = "This Month"
_DATE_YEAR = "This Year"
_DATE_30 = "Last 30 Days"
_DATE_60 = "Last 60 Days"
_DATE_90 = "Last 90 Days"

_LIST_ACTIVE = "Active Customers"
_LIST_ALL = "All Customers"
_LIST_OPEN = "Customers with Open Balances"

_ROLE_CUSTOMER_ID = Qt.ItemDataRole.UserRole
_ROLE_KIND = Qt.ItemDataRole.UserRole + 1
_ROLE_RECORD_ID = Qt.ItemDataRole.UserRole + 2
_ROLE_IS_TOTAL = Qt.ItemDataRole.UserRole + 3

_COL_NAME = 0
_COL_BAL = 1
_COL_ATTACH = 2


def _action_button_qss(*, primary: bool = False) -> str:
    r = _TOP_STRIP_RADIUS_PX
    if primary:
        return (
            f"QPushButton {{ background-color: {_CC_ACCENT}; border: 1px solid {_CC_ACCENT}; "
            f"border-radius: {r}px; color: #FFFFFF; "
            f"font-size: {_TOP_STRIP_BODY_FONT_PX}px; padding: 0 14px; font-weight: 600; }}"
            f"QPushButton:hover {{ background-color: #1D4F8C; border: 1px solid #1D4F8C; }}"
            f"QPushButton:pressed {{ background-color: #163E6E; }}"
            f"QPushButton:disabled {{ color: #D7E3F0; background-color: #8AA7C7; "
            f"border: 1px solid #8AA7C7; }}"
        )
    return (
        f"QPushButton {{ background-color: {WORKFLOW_CONTROL_FACE}; border: 1px solid {_STRIP_BTN_OUTLINE}; "
        f"border-radius: {r}px; color: {_CC_TEXT}; "
        f"font-size: {_TOP_STRIP_BODY_FONT_PX}px; padding: 0 12px; }}"
        f"QPushButton:hover {{ background-color: {WORKFLOW_CONTROL_HOVER}; }}"
        f"QPushButton:pressed {{ background-color: {WORKFLOW_CONTROL_PRESSED}; }}"
        f"QPushButton:disabled {{ color: {DISABLED_FG}; background-color: {WORKFLOW_CONTROL_FACE}; }}"
    )


def _tool_button_qss() -> str:
    r = _TOP_STRIP_RADIUS_PX
    return (
        f"QToolButton {{ background-color: {WORKFLOW_CONTROL_FACE}; border: 1px solid {_STRIP_BTN_OUTLINE}; "
        f"border-radius: {r}px; color: {_CC_TEXT}; "
        f"font-size: {_TOP_STRIP_BODY_FONT_PX}px; padding: 0 12px; }}"
        f"QToolButton:hover {{ background-color: {WORKFLOW_CONTROL_HOVER}; }}"
        f"QToolButton:pressed {{ background-color: {WORKFLOW_CONTROL_PRESSED}; }}"
        f"QToolButton::menu-indicator {{ width: 10px; }}"
    )


def _input_qss(widget: str = "QLineEdit") -> str:
    return (
        f"{widget} {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_CC_GRID}; "
        f"padding: 2px 6px; color: {_CC_TEXT}; font-size: {_TOP_STRIP_BODY_FONT_PX}px; }}"
    )


def _link_qss() -> str:
    return (
        f"QPushButton {{ background: transparent; border: none; color: {_CC_LINK}; "
        f"font-size: {_TOP_STRIP_BODY_FONT_PX}px; text-align: left; padding: 0; }}"
        f"QPushButton:hover {{ text-decoration: underline; color: #144A86; }}"
    )


def _light_form_palette() -> QPalette:
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(_CC_PAPER))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(_CC_TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(WORKFLOW_INPUT_BG))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(_CC_STRIPE))
    pal.setColor(QPalette.ColorRole.Text, QColor(_CC_TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(WORKFLOW_CONTROL_FACE))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(_CC_TEXT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(_CC_SELECT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(_CC_TEXT))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(_CC_CAPTION))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(_CC_PANEL))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(_CC_TEXT))
    return pal


def _readonly_item(text: str, *, align_right: bool = False) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    it.setForeground(QColor(_CC_TEXT))
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


def customer_center_empty_sentence(show: str, filter_by: str, date_range: str) -> str:
    """QB-style empty grid copy for the current SHOW / FILTER BY / DATE combos."""
    return (
        f"There are no transactions of type '{show}', "
        f"filtered by '{filter_by}', in date range '{date_range}'."
    )


def customer_center_job_display_name(name: str) -> str:
    """QB-style job row: colon prefix, indented under the parent customer."""
    raw = (name or "").strip()
    return f"    :{raw}" if raw else "    :"


class CustomerCenterScreen(QWidget):
    """QB Pro Customer Center: customer/job list, information card, and invoice grid.

    Signals
    -------
    createInvoicesRequested
        Open Create Invoices (arg is customer id, or 0 if none selected).
    receivePaymentsRequested
        Open Receive Payments for the customer (id or 0).
    incomeTrackerRequested
        Open Income Tracker, optionally filtered to the selected customer.
    openInvoiceRequested
        Double-click an Invoice row → Create Invoices for that invoice id.
    openPaymentRequested
        Double-click a Payment row → Receive Payments for that customer.
    customerRecordsChanged
        New / edited customer — Create Invoices and Receive Payments should reload.
    arAgingSummaryRequested
        Open Balance / Run Reports → A/R Aging Summary (live open invoices).
    """

    createInvoicesRequested = Signal(int)
    receivePaymentsRequested = Signal(int)
    incomeTrackerRequested = Signal(int)
    openInvoiceRequested = Signal(int)
    openPaymentRequested = Signal(int)
    customerRecordsChanged = Signal()
    arAgingSummaryRequested = Signal()

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.setObjectName("customerCenterPage")
        self._conn = conn
        self._customer_summary_by_id: dict[int, dict] = {}
        self._focused_customer_id: int | None = None
        self._txn_rows: list[dict] = []
        self.setAutoFillBackground(True)
        self.setPalette(_light_form_palette())
        self.setStyleSheet(
            f"QWidget#customerCenterPage {{ background: {_CC_CANVAS}; color: {_CC_TEXT}; }}"
        )
        self.setToolTip(
            "Customer Center: customer list, jobs, balances, and invoices / payments. "
            "F5 refreshes when this tab has focus. "
            "CSV exports (toolbar) use UTF-8 BOM for Excel."
        )
        self._build_ui()
        sc = QShortcut(QKeySequence("F5"), self)
        sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc.activated.connect(self._refresh)
        self._refresh()

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
        wrap.setObjectName("customerCenterMetaField")
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)
        lbl = QLabel(caption)
        lbl.setStyleSheet(
            f"color: {_CC_CAPTION}; font-size: {_TOP_STRIP_CAPTION_FONT_PX}px; "
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
            f"color: {_CC_CAPTION}; font-size: {_TOP_STRIP_BODY_FONT_PX}px; "
            "background: transparent; border: none;"
        )
        value.setStyleSheet(
            f"color: {_CC_TEXT}; font-size: {_TOP_STRIP_BODY_FONT_PX}px; "
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
        split.setObjectName("customerCenterSplit")
        split.setChildrenCollapsible(False)
        split.setToolTip("Drag to resize the customer list versus Customer Information.")
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

        self._btn_new_customer = QToolButton()
        self._btn_new_customer.setObjectName("customerCenterNewCustomer")
        self._btn_new_customer.setText("New Customer & Job")
        self._style_tool(self._btn_new_customer)
        nv_menu = QMenu(self._btn_new_customer)
        act_nc = nv_menu.addAction("New Customer...")
        act_nc.setToolTip("Create a standalone customer (or future parent for jobs).")
        act_nc.triggered.connect(self._new_c)
        act_job = nv_menu.addAction("Add Job...")
        act_job.setToolTip("Create a job under the selected customer.")
        act_job.triggered.connect(self._new_job)
        self._btn_new_customer.setMenu(nv_menu)
        self._btn_new_customer.setToolTip("Create a new customer or a job under a customer.")
        row.addWidget(self._btn_new_customer)

        self._btn_new_txn = QToolButton()
        self._btn_new_txn.setObjectName("customerCenterNewTransactions")
        self._btn_new_txn.setText("New Transactions")
        self._style_tool(self._btn_new_txn)
        txn_menu = QMenu(self._btn_new_txn)
        txn_menu.addAction("Create Invoices", self._on_new_create_invoices)
        txn_menu.addAction("Receive Payments", self._on_new_receive_payments)
        self._btn_new_txn.setMenu(txn_menu)
        self._btn_new_txn.setToolTip(
            "Create Invoices or Receive Payments for the selected customer."
        )
        row.addWidget(self._btn_new_txn)

        self._btn_print = QToolButton()
        self._btn_print.setObjectName("customerCenterPrint")
        self._btn_print.setText("Print")
        self._style_tool(self._btn_print)
        print_menu = QMenu(self._btn_print)
        print_menu.addAction("Print customer list…", self._on_print_customer_list)
        print_menu.addAction("Print transactions…", self._on_print_transactions)
        self._btn_print.setMenu(print_menu)
        self._btn_print.setToolTip("Print the customer list or the current transaction grid.")
        row.addWidget(self._btn_print)

        self._btn_excel = QToolButton()
        self._btn_excel.setObjectName("customerCenterExcel")
        self._btn_excel.setText("Excel")
        self._style_tool(self._btn_excel)
        excel_menu = QMenu(self._btn_excel)
        excel_menu.addAction("Export Customers CSV…", self._export_customers)
        self._btn_excel.setMenu(excel_menu)
        self._btn_excel.setToolTip("Export customers to CSV (UTF-8 BOM for Excel).")
        row.addWidget(self._btn_excel)

        self._btn_word = QToolButton()
        self._btn_word.setObjectName("customerCenterWord")
        self._btn_word.setText("Word")
        self._style_tool(self._btn_word)
        word_menu = QMenu(self._btn_word)
        word_menu.addAction("Letters…", self._on_word_letters)
        self._btn_word.setMenu(word_menu)
        self._btn_word.setToolTip("Letters for this customer (not wired yet).")
        row.addWidget(self._btn_word)

        self._btn_income_tracker = QPushButton("Income Tracker")
        self._btn_income_tracker.setObjectName("customerCenterIncomeTracker")
        self._style_push(self._btn_income_tracker)
        self._btn_income_tracker.setToolTip("Open Income Tracker for this customer.")
        self._btn_income_tracker.clicked.connect(self._on_income_tracker)
        row.addWidget(self._btn_income_tracker)

        row.addStretch(1)
        return row

    def _build_left_pane(self) -> QWidget:
        pane = QFrame()
        pane.setObjectName("customerCenterLeft")
        pane.setStyleSheet(
            f"QFrame#customerCenterLeft {{ background: {_CC_PAPER}; "
            f"border: 1px solid #B7C9DE; border-radius: 6px; }}"
        )
        lay = QVBoxLayout(pane)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)

        self._left_tabs = QTabWidget()
        self._left_tabs.setObjectName("customerCenterLeftTabs")
        self._left_tabs.setDocumentMode(True)
        self._left_tabs.setToolTip("Customers & Jobs list or all-customer transactions.")
        self._left_tabs.addTab(QWidget(), "Customers & Jobs")
        self._left_tabs.addTab(QWidget(), "Transactions")
        self._left_tabs.currentChanged.connect(self._on_left_tab_changed)
        lay.addWidget(self._left_tabs)

        filt_row = QHBoxLayout()
        filt_row.setSpacing(6)
        self._list_filter = QComboBox()
        self._list_filter.setObjectName("customerCenterListFilter")
        self._list_filter.addItems((_LIST_ACTIVE, _LIST_ALL, _LIST_OPEN))
        self._list_filter.setStyleSheet(_input_qss("QComboBox"))
        self._list_filter.setToolTip(
            "Show active customers, all customers, or customers with an open balance."
        )
        self._list_filter.currentIndexChanged.connect(self._reload_customer_table)
        filt_row.addWidget(self._list_filter, 1)
        self._search = QLineEdit()
        self._search.setObjectName("customerCenterSearch")
        self._search.setPlaceholderText("Search")
        self._search.setClearButtonEnabled(True)
        self._search.setStyleSheet(_input_qss())
        self._search.setToolTip("Filter the customer list by name.")
        self._search.textChanged.connect(self._reload_customer_table)
        filt_row.addWidget(self._search, 1)
        lay.addLayout(filt_row)

        self._left_stack = QStackedWidget()
        self._customer_tbl = QTableWidget()
        self._customer_tbl.setObjectName("customerCenterCustomerTable")
        self._customer_tbl.setColumnCount(3)
        self._customer_tbl.setHorizontalHeaderLabels(["NAME", "BALANCE TOTAL", "📎"])
        self._customer_tbl.verticalHeader().setVisible(False)
        self._customer_tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._customer_tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._customer_tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._customer_tbl.setAlternatingRowColors(True)
        self._customer_tbl.setSortingEnabled(False)
        hdr = self._customer_tbl.horizontalHeader()
        hdr.setSectionResizeMode(_COL_NAME, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(_COL_BAL, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_ATTACH, QHeaderView.ResizeMode.Fixed)
        hdr.resizeSection(_COL_ATTACH, 28)
        self._customer_tbl.setStyleSheet(self._table_qss("customerCenterCustomerTable", selected_green=True))
        self._customer_tbl.itemSelectionChanged.connect(self._on_customer_selection_changed)
        self._customer_tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._customer_tbl.customContextMenuRequested.connect(self._on_customer_context_menu)
        self._customer_tbl.setToolTip(
            "Click a customer or job to fill Customer Information and the transaction grid. "
            "Jobs indent under the parent. F5 refreshes. CSV exports (toolbar) use UTF-8 BOM for Excel."
        )
        self._customer_tbl.verticalHeader().setDefaultSectionSize(_LINE_ROW_HEIGHT_PX)

        self._left_txn_tbl = QTableWidget()
        self._left_txn_tbl.setObjectName("customerCenterLeftTxnTable")
        self._left_txn_tbl.setColumnCount(4)
        self._left_txn_tbl.setHorizontalHeaderLabels(["TYPE", "DATE", "NAME", "AMOUNT"])
        self._left_txn_tbl.verticalHeader().setVisible(False)
        self._left_txn_tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._left_txn_tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._left_txn_tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._left_txn_tbl.setAlternatingRowColors(True)
        self._left_txn_tbl.setStyleSheet(self._table_qss("customerCenterLeftTxnTable"))
        self._left_txn_tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._left_txn_tbl.itemSelectionChanged.connect(self._on_left_txn_selection_changed)
        self._left_txn_tbl.setToolTip(
            "All customer invoices and payments. Click a row to select that customer."
        )
        self._left_txn_tbl.verticalHeader().setDefaultSectionSize(_LINE_ROW_HEIGHT_PX)

        self._left_stack.addWidget(self._customer_tbl)
        self._left_stack.addWidget(self._left_txn_tbl)
        lay.addWidget(self._left_stack, 1)
        return pane

    def _table_qss(self, object_name: str, *, selected_green: bool = False) -> str:
        sel_bg = _CC_SELECT if selected_green else _CC_ACCENT
        sel_fg = _CC_TEXT if selected_green else "#FFFFFF"
        return f"""
QTableWidget#{object_name} {{
    background: {_CC_PAPER};
    alternate-background-color: {_CC_STRIPE};
    color: {_CC_TEXT};
    gridline-color: {_CC_GRID};
    border: 1px solid {_CC_GRID};
}}
QTableWidget#{object_name}::item:selected {{
    background-color: {sel_bg};
    color: {sel_fg};
}}
QHeaderView::section {{
    background-color: {_CC_HEADER};
    color: {_CC_TEXT};
    padding: 4px 6px;
    border: none;
    border-right: 1px solid {_CC_GRID};
    border-bottom: 1px solid {_CC_GRID};
    font-weight: 700;
    font-size: 11px;
}}
"""

    def _build_right_pane(self) -> QWidget:
        pane = QWidget()
        pane.setObjectName("customerCenterRight")
        lay = QVBoxLayout(pane)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        vsplit = QSplitter(Qt.Orientation.Vertical)
        vsplit.setChildrenCollapsible(False)
        vsplit.setToolTip("Drag to resize Customer Information versus the transaction grid.")
        vsplit.addWidget(self._build_info_header())
        vsplit.addWidget(self._build_activity_block())
        vsplit.setStretchFactor(0, 1)
        vsplit.setStretchFactor(1, 3)
        vsplit.setSizes([200, 540])
        lay.addWidget(vsplit, 1)
        lay.addLayout(self._build_footer())
        return pane

    def _build_info_header(self) -> QWidget:
        box = QFrame()
        box.setObjectName("customerCenterInfo")
        box.setStyleSheet(
            f"QFrame#customerCenterInfo {{ background: {_CC_PAPER}; "
            f"border: 1px solid #B7C9DE; border-radius: 6px; }}"
        )
        box.setToolTip("Contact fields from the customer master; balances from open invoices and payments.")
        grid = QGridLayout(box)
        grid.setContentsMargins(12, 8, 12, 8)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(4)

        title_row = QHBoxLayout()
        title = QLabel("Customer Information")
        title.setObjectName("customerCenterInfoTitle")
        title.setStyleSheet(
            f"color: {_CC_TITLE}; font-size: {_TITLE_FONT_PX}px; font-weight: 600; "
            "background: transparent; border: none;"
        )
        title_row.addWidget(title)
        title_row.addStretch(1)
        self._btn_attach = QPushButton("📎")
        self._btn_attach.setObjectName("customerCenterAttach")
        self._btn_attach.setFixedSize(28, 24)
        self._btn_attach.setStyleSheet(_action_button_qss())
        self._btn_attach.setToolTip("Attachments for this customer (not stored on the customer record yet).")
        self._btn_attach.clicked.connect(self._on_attach_hint)
        title_row.addWidget(self._btn_attach)
        self._btn_edit = QPushButton("✎")
        self._btn_edit.setObjectName("customerCenterEdit")
        self._btn_edit.setFixedSize(28, 24)
        self._btn_edit.setStyleSheet(_action_button_qss())
        self._btn_edit.setToolTip("Edit name, contact, job parent, and notes for this customer.")
        self._btn_edit.clicked.connect(self._edit_c)
        title_row.addWidget(self._btn_edit)
        grid.addLayout(title_row, 0, 0, 1, 2)

        details = QVBoxLayout()
        details.setSpacing(4)
        self._d_company = QLabel("—")
        self._d_full_name = QLabel("—")
        self._d_bill_to = QLabel("—")
        self._d_bill_to.setWordWrap(True)
        details.addLayout(self._info_row("Company Name", self._d_company))
        details.addLayout(self._info_row("Full Name", self._d_full_name))
        details.addLayout(self._info_row("Bill To", self._d_bill_to))
        details.addStretch(1)
        details_w = QWidget()
        details_w.setLayout(details)
        grid.addWidget(details_w, 1, 0)

        side = QVBoxLayout()
        side.setSpacing(6)
        note_cap = QLabel("NOTE")
        note_cap.setStyleSheet(
            f"color: {_CC_CAPTION}; font-size: {_TOP_STRIP_CAPTION_FONT_PX}px; "
            "font-weight: 700; background: transparent;"
        )
        side.addWidget(note_cap)
        self._d_note = QLabel("No note available")
        self._d_note.setObjectName("customerCenterNote")
        self._d_note.setWordWrap(True)
        self._d_note.setMinimumHeight(48)
        self._d_note.setStyleSheet(
            f"color: {_CC_TEXT}; font-size: {_TOP_STRIP_BODY_FONT_PX}px; "
            f"background: {_CC_PANEL}; border: 1px solid {_CC_GRID}; padding: 6px;"
        )
        self._d_note.setToolTip("Internal notes from the customer record.")
        side.addWidget(self._d_note)
        rpt = QLabel("REPORTS FOR THIS CUSTOMER")
        rpt.setStyleSheet(
            f"color: {_CC_CAPTION}; font-size: {_TOP_STRIP_CAPTION_FONT_PX}px; "
            "font-weight: 700; background: transparent;"
        )
        side.addWidget(rpt)
        rpt_row = QHBoxLayout()
        self._btn_quickreport = QPushButton("QuickReport")
        self._btn_quickreport.setObjectName("customerCenterQuickReport")
        self._btn_quickreport.setStyleSheet(_link_qss())
        self._btn_quickreport.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_quickreport.setToolTip("Show all invoices and payments for this customer.")
        self._btn_quickreport.clicked.connect(self._on_quickreport)
        self._btn_open_bal = QPushButton("Open Balance")
        self._btn_open_bal.setObjectName("customerCenterOpenBalance")
        self._btn_open_bal.setStyleSheet(_link_qss())
        self._btn_open_bal.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_open_bal.setToolTip(
            "Open A/R Aging Summary (live open invoices). Also filters this customer to Open Invoices."
        )
        self._btn_open_bal.clicked.connect(self._on_open_balance_report)
        rpt_row.addWidget(self._btn_quickreport)
        rpt_row.addSpacing(12)
        rpt_row.addWidget(self._btn_open_bal)
        rpt_row.addStretch(1)
        side.addLayout(rpt_row)
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
        wrap.setObjectName("customerCenterActivity")
        wrap.setStyleSheet(
            f"QFrame#customerCenterActivity {{ background: {_CC_PAPER}; "
            f"border: 1px solid #B7C9DE; border-radius: 6px; }}"
        )
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(8, 4, 8, 8)
        lay.setSpacing(6)

        self._right_tabs = QTabWidget()
        self._right_tabs.setObjectName("customerCenterRightTabs")
        self._right_tabs.setDocumentMode(True)
        self._right_tabs.setToolTip(
            "Transactions, contacts, to do's, notes, and sent email for this customer."
        )

        txn_page = QWidget()
        txn_lay = QVBoxLayout(txn_page)
        txn_lay.setContentsMargins(0, 6, 0, 0)
        txn_lay.setSpacing(6)
        filt = QHBoxLayout()
        filt.setSpacing(12)
        self._show = QComboBox()
        self._show.setObjectName("customerCenterShow")
        self._show.addItems((_SHOW_INVOICES, _SHOW_PAYMENTS, _SHOW_ALL))
        self._show.setStyleSheet(_input_qss("QComboBox"))
        self._show.setToolTip("Which transaction types to list.")
        self._show.currentIndexChanged.connect(self._reload_txn_table)
        filt.addWidget(self._caption_field("SHOW", self._show))
        self._filter_by = QComboBox()
        self._filter_by.setObjectName("customerCenterFilterBy")
        self._filter_by.addItems((_FILTER_ALL, _FILTER_OPEN, _FILTER_OVERDUE, _FILTER_PAID))
        self._filter_by.setStyleSheet(_input_qss("QComboBox"))
        self._filter_by.setToolTip("Open, overdue, paid, or all invoices.")
        self._filter_by.currentIndexChanged.connect(self._reload_txn_table)
        filt.addWidget(self._caption_field("FILTER BY", self._filter_by))
        self._date_range = QComboBox()
        self._date_range.setObjectName("customerCenterDate")
        self._date_range.addItems((_DATE_ALL, _DATE_MONTH, _DATE_YEAR, _DATE_30, _DATE_60, _DATE_90))
        self._date_range.setStyleSheet(_input_qss("QComboBox"))
        self._date_range.setToolTip("Limit the grid to a date range.")
        self._date_range.currentIndexChanged.connect(self._reload_txn_table)
        filt.addWidget(self._caption_field("DATE", self._date_range))
        filt.addStretch(1)
        txn_lay.addLayout(filt)

        self._txn_stack = QStackedWidget()
        txn_table_page = QWidget()
        txn_table_lay = QVBoxLayout(txn_table_page)
        txn_table_lay.setContentsMargins(0, 0, 0, 0)
        txn_table_lay.setSpacing(0)
        self._txn_tbl = QTableWidget()
        self._txn_tbl.setObjectName("customerCenterTxnTable")
        self._txn_tbl.setColumnCount(6)
        self._txn_tbl.setHorizontalHeaderLabels(
            ["NUM", "DATE", "DUE DATE", "AGING", "AMOUNT", "OPEN BALANCE"]
        )
        self._txn_tbl.verticalHeader().setVisible(False)
        self._txn_tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._txn_tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._txn_tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._txn_tbl.setAlternatingRowColors(True)
        self._txn_tbl.setSortingEnabled(False)
        self._txn_tbl.setStyleSheet(self._table_qss("customerCenterTxnTable"))
        th = self._txn_tbl.horizontalHeader()
        th.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        th.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        th.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        th.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        th.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        th.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self._txn_tbl.cellDoubleClicked.connect(self._on_txn_double_clicked)
        self._txn_tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._txn_tbl.customContextMenuRequested.connect(self._on_txn_context_menu)
        self._txn_tbl.setToolTip(
            "Invoices and payments for the selected customer. Double-click an invoice to open "
            "Create Invoices. F5 refreshes."
        )
        self._txn_tbl.verticalHeader().setDefaultSectionSize(_LINE_ROW_HEIGHT_PX)
        self._txn_tbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        txn_table_lay.addWidget(self._txn_tbl, 1)

        totals = QHBoxLayout()
        totals.setContentsMargins(8, 4, 8, 2)
        totals.addStretch(1)
        self._txn_amount_total = QLabel("0.00")
        self._txn_amount_total.setObjectName("customerCenterAmountTotal")
        self._txn_open_total = QLabel("0.00")
        self._txn_open_total.setObjectName("customerCenterOpenBalanceTotal")
        for lbl in (self._txn_amount_total, self._txn_open_total):
            lbl.setStyleSheet(
                f"color: {_CC_TEXT}; font-size: {_TOP_STRIP_BODY_FONT_PX}px; "
                "font-weight: 700; background: transparent;"
            )
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lbl.setMinimumWidth(110)
        amt_cap = QLabel("AMOUNT")
        ob_cap = QLabel("OPEN BALANCE")
        for cap in (amt_cap, ob_cap):
            cap.setStyleSheet(
                f"color: {_CC_CAPTION}; font-size: 10px; font-weight: 700; background: transparent;"
            )
        totals.addWidget(amt_cap)
        totals.addWidget(self._txn_amount_total)
        totals.addSpacing(16)
        totals.addWidget(ob_cap)
        totals.addWidget(self._txn_open_total)
        txn_table_lay.addLayout(totals)

        empty_page = QWidget()
        empty_page.setStyleSheet(f"background: {_CC_PAPER};")
        empty_lay = QVBoxLayout(empty_page)
        self._txn_empty = QLabel("")
        self._txn_empty.setObjectName("customerCenterEmpty")
        self._txn_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._txn_empty.setWordWrap(True)
        self._txn_empty.setStyleSheet(
            f"color: {_CC_EMPTY}; font-size: 13px; background: transparent;"
        )
        empty_lay.addStretch(1)
        empty_lay.addWidget(self._txn_empty)
        empty_lay.addStretch(1)
        self._txn_stack.addWidget(txn_table_page)
        self._txn_stack.addWidget(empty_page)
        txn_lay.addWidget(self._txn_stack, 1)
        self._right_tabs.addTab(txn_page, "Transactions")

        self._contacts_page = self._placeholder_page(
            "contacts",
            "Contacts for this customer (name, email, phone from the customer record).",
        )
        self._right_tabs.addTab(self._contacts_page, "Contacts")
        self._todos_page = self._placeholder_page(
            "todos",
            "No to do's for this customer.",
        )
        self._right_tabs.addTab(self._todos_page, "To Do's")
        notes_page = QWidget()
        notes_lay = QVBoxLayout(notes_page)
        notes_lay.setContentsMargins(8, 8, 8, 8)
        self._notes_body = QPlainTextEdit()
        self._notes_body.setObjectName("customerCenterNotesBody")
        self._notes_body.setReadOnly(True)
        self._notes_body.setStyleSheet(_input_qss("QPlainTextEdit"))
        self._notes_body.setToolTip("Internal notes. Use the pencil to edit the customer record.")
        notes_lay.addWidget(self._notes_body)
        self._right_tabs.addTab(notes_page, "Notes")
        self._email_page = self._placeholder_page(
            "email",
            "No sent email for this customer.",
        )
        self._right_tabs.addTab(self._email_page, "Sent Email")
        lay.addWidget(self._right_tabs, 1)
        return wrap

    def _placeholder_page(self, name: str, message: str) -> QWidget:
        w = QWidget()
        w.setObjectName(f"customerCenterTab_{name}")
        lay = QVBoxLayout(w)
        lbl = QLabel(message)
        lbl.setObjectName(f"customerCenterTabLabel_{name}")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {_CC_EMPTY}; font-size: 13px; background: transparent;")
        lay.addStretch(1)
        lay.addWidget(lbl)
        lay.addStretch(1)
        return w

    def _build_footer(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        self._btn_manage = QToolButton()
        self._btn_manage.setObjectName("customerCenterManage")
        self._btn_manage.setText("Manage Transactions")
        self._style_tool(self._btn_manage)
        m = QMenu(self._btn_manage)
        m.addAction("Edit Transaction", self._on_edit_selected_txn)
        m.addAction("Create Invoices", self._on_new_create_invoices)
        m.addAction("Receive Payments", self._on_new_receive_payments)
        self._btn_manage.setMenu(m)
        self._btn_manage.setToolTip(
            "Edit the selected row or create invoices / receive payments for this customer."
        )
        row.addWidget(self._btn_manage)

        self._btn_run_reports = QToolButton()
        self._btn_run_reports.setObjectName("customerCenterRunReports")
        self._btn_run_reports.setText("Run Reports")
        self._style_tool(self._btn_run_reports)
        rm = QMenu(self._btn_run_reports)
        rm.addAction("QuickReport", self._on_quickreport)
        rm.addAction("Open Balance", self._on_open_balance_report)
        rm.addAction("A/R Aging Summary", self._on_open_balance_report)
        self._btn_run_reports.setMenu(rm)
        self._btn_run_reports.setToolTip(
            "QuickReport, Open Balance, and A/R Aging Summary for this customer."
        )
        row.addWidget(self._btn_run_reports)

        row.addStretch(1)
        return row

    def persist_header_state(self) -> None:
        QSettings().setValue(
            _CUSTOMER_HEADER_STATE_KEY,
            self._customer_tbl.horizontalHeader().saveState(),
        )

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        raw = QSettings().value(_CUSTOMER_HEADER_STATE_KEY)
        if raw:
            self._customer_tbl.horizontalHeader().restoreState(raw)
        self._refresh()

    def _focused_id(self) -> int:
        return int(self._focused_customer_id or 0)

    def focus_customer(self, customer_id: int) -> None:
        """Tiny Company Snapshot hook: select this customer in Customer Center."""
        cid = int(customer_id or 0)
        if cid <= 0:
            return
        self._focused_customer_id = cid
        self._refresh()
        self._select_customer_row(cid)
        self._apply_detail_from_focus()

    def focus_open_invoices(self, customer_id: int) -> None:
        """Tiny A/R Aging Summary hook: this customer/job's open invoices."""
        if customer_id:
            self.focus_customer(int(customer_id))
        self._right_tabs.setCurrentIndex(0)
        self._show.setCurrentText(_SHOW_INVOICES)
        self._filter_by.setCurrentText(_FILTER_OPEN)
        self._date_range.setCurrentText(_DATE_ALL)
        self._reload_txn_table()

    def _on_left_tab_changed(self, index: int) -> None:
        self._left_stack.setCurrentIndex(0 if index <= 0 else 1)
        if index == 1:
            self._reload_left_txn_table()

    def _on_customer_selection_changed(self) -> None:
        rows = self._customer_tbl.selectionModel().selectedRows() if self._customer_tbl.selectionModel() else []
        if not rows:
            return
        it = self._customer_tbl.item(rows[0].row(), _COL_NAME)
        if it is None:
            return
        cid = coerce_combo_int_id(it.data(_ROLE_CUSTOMER_ID))
        if cid is None:
            return
        self._focused_customer_id = cid
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
        cid = coerce_combo_int_id(it.data(_ROLE_CUSTOMER_ID))
        if cid is None:
            return
        self._focused_customer_id = cid
        self._select_customer_row(cid)
        self._apply_detail_from_focus()
        self._reload_txn_table()

    def _on_customer_context_menu(self, pos) -> None:
        from desktop_app.extra_tabs import show_business_keyboard_shortcuts_dialog
        from desktop_app.table_clipboard import VIEW_BANK_REGISTER_KEYS_TOOLTIP

        idx = self._customer_tbl.indexAt(pos)
        m = QMenu(self)
        act_keys = m.addAction(
            "Keyboard shortcuts…",
            lambda: show_business_keyboard_shortcuts_dialog(self),
        )
        act_keys.setToolTip(
            "Same summary as Help → Business shortcuts… (F5, Customers grid). "
            + VIEW_BANK_REGISTER_KEYS_TOOLTIP
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        if idx.isValid():
            m.addSeparator()
            act = m.addAction("Copy row", lambda r=idx.row(): copy_table_row_as_tsv(self._customer_tbl, r))
            act.setToolTip(
                "Copy this customer row as tab-separated text. " + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
            )
            m.addSeparator()
        m.addAction("New Customer...", self._new_c)
        m.addAction("Add Job...", self._new_job)
        m.addAction("Edit Customer...", self._edit_c)
        m.exec(self._customer_tbl.viewport().mapToGlobal(pos))

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
        m.addAction("Create Invoices", self._on_new_create_invoices)
        m.addAction("Receive Payments", self._on_new_receive_payments)
        m.exec(self._txn_tbl.viewport().mapToGlobal(pos))

    def _refresh(self) -> None:
        if self._conn is None:
            self._customer_summary_by_id = {}
            self._reload_customer_table()
            return
        try:
            rows = business.list_customer_ar_summaries(self._conn)
        except sqlite3.Error:
            rows = []
        self._customer_summary_by_id = {int(r["customer_id"]): r for r in rows}
        self._reload_customer_table()
        if self._left_tabs.currentIndex() == 1:
            self._reload_left_txn_table()

    def _balance_total_for(self, customer_id: int) -> float:
        row = self._customer_summary_by_id.get(customer_id)
        if row is None:
            return 0.0
        own = float(row.get("open_balance") or 0)
        if row.get("parent_customer_id") is not None:
            return own
        rolled = own
        for r in self._customer_summary_by_id.values():
            pid = r.get("parent_customer_id")
            if pid is not None and int(pid) == customer_id:
                rolled += float(r.get("open_balance") or 0)
        return round(rolled, 2)

    def _ordered_customer_rows(self, rows: list[dict]) -> list[dict]:
        jobs_by_parent: dict[int, list[dict]] = {}
        parents: list[dict] = []
        orphans: list[dict] = []
        for r in rows:
            pid = r.get("parent_customer_id")
            if pid is None:
                parents.append(r)
            else:
                jobs_by_parent.setdefault(int(pid), []).append(r)
        parents.sort(key=lambda r: (r.get("customer_name") or "").lower())
        out: list[dict] = []
        shown_jobs: set[int] = set()
        for p in parents:
            out.append(p)
            kids = jobs_by_parent.get(int(p["customer_id"]), [])
            kids.sort(key=lambda r: (r.get("customer_name") or "").lower())
            for k in kids:
                out.append(k)
                shown_jobs.add(int(k["customer_id"]))
        for r in rows:
            if r.get("parent_customer_id") is not None and int(r["customer_id"]) not in shown_jobs:
                orphans.append(r)
        orphans.sort(key=lambda r: (r.get("customer_name") or "").lower())
        out.extend(orphans)
        return out

    def _filtered_customer_rows(self) -> list[dict]:
        q = (self._search.text() or "").strip().lower()
        mode = self._list_filter.currentText()
        all_rows = list(self._customer_summary_by_id.values())
        keep: set[int] = set()
        for r in all_rows:
            cid = int(r["customer_id"])
            name = (r.get("customer_name") or "").lower()
            if q and q not in name:
                continue
            keep.add(cid)
        if q:
            extra: set[int] = set()
            for cid in keep:
                r = self._customer_summary_by_id.get(cid)
                if r is None:
                    continue
                pid = r.get("parent_customer_id")
                if pid is not None:
                    extra.add(int(pid))
                else:
                    for child in all_rows:
                        if child.get("parent_customer_id") is not None and int(child["parent_customer_id"]) == cid:
                            extra.add(int(child["customer_id"]))
            keep |= extra
        if mode == _LIST_OPEN:
            open_ids: set[int] = set()
            for r in all_rows:
                cid = int(r["customer_id"])
                if self._balance_total_for(cid) > 0.005 or float(r.get("open_balance") or 0) > 0.005:
                    open_ids.add(cid)
                    pid = r.get("parent_customer_id")
                    if pid is not None:
                        open_ids.add(int(pid))
            for r in all_rows:
                pid = r.get("parent_customer_id")
                if pid is not None and int(pid) in open_ids:
                    open_ids.add(int(r["customer_id"]))
            keep &= open_ids
        rows = [r for r in all_rows if int(r["customer_id"]) in keep]
        return self._ordered_customer_rows(rows)

    def _reload_customer_table(self) -> None:
        rows = self._filtered_customer_rows()
        self._customer_tbl.setRowCount(len(rows))
        for i, r in enumerate(rows):
            cid = int(r["customer_id"])
            nm = r.get("customer_name") or ""
            is_job = r.get("parent_customer_id") is not None
            shown = customer_center_job_display_name(nm) if is_job else nm
            it1 = _readonly_item(escape_ampersand_for_qt(shown))
            it1.setData(_ROLE_CUSTOMER_ID, cid)
            self._customer_tbl.setItem(i, _COL_NAME, it1)
            bal = self._balance_total_for(cid)
            it2 = FloatSortTableItem(_fmt_money(bal), bal)
            it2.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            it2.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            it2.setData(_ROLE_CUSTOMER_ID, cid)
            self._customer_tbl.setItem(i, _COL_BAL, it2)
            it3 = _readonly_item("")
            it3.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it3.setData(_ROLE_CUSTOMER_ID, cid)
            self._customer_tbl.setItem(i, _COL_ATTACH, it3)
        ids = {int(r["customer_id"]) for r in rows}
        if self._focused_customer_id is not None and self._focused_customer_id not in ids:
            self._focused_customer_id = None
        if self._focused_customer_id is None and rows:
            self._focused_customer_id = int(rows[0]["customer_id"])
        if self._focused_customer_id is not None:
            self._select_customer_row(self._focused_customer_id)
        else:
            self._customer_tbl.clearSelection()
        self._apply_detail_from_focus()
        self._reload_txn_table()

    def _select_customer_row(self, customer_id: int) -> None:
        self._customer_tbl.blockSignals(True)
        try:
            for row in range(self._customer_tbl.rowCount()):
                it = self._customer_tbl.item(row, _COL_NAME)
                if it is None:
                    continue
                if coerce_combo_int_id(it.data(_ROLE_CUSTOMER_ID)) == customer_id:
                    self._customer_tbl.selectRow(row)
                    break
        finally:
            self._customer_tbl.blockSignals(False)

    def _apply_detail_from_focus(self) -> None:
        if self._focused_customer_id is None or self._conn is None:
            self._clear_detail_card()
            return
        v = business.get_customer(self._conn, self._focused_customer_id)
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
        self._d_bill_to.setText(escape_ampersand_for_qt("\n".join(billed_lines)))
        self._d_note.setText(escape_ampersand_for_qt(notes) if notes else "No note available")
        contact_bits = [name]
        if email:
            contact_bits.append(email)
        if phone:
            contact_bits.append(phone)
        if addr:
            contact_bits.append(addr)
        contacts_lbl = self._contacts_page.findChild(QLabel, "customerCenterTabLabel_contacts")
        if contacts_lbl is not None:
            contacts_lbl.setText("\n".join(contact_bits) if name != "—" else "No contacts for this customer.")
        self._notes_body.setPlainText(notes)

    def _clear_detail_card(self) -> None:
        self._d_company.setText("—")
        self._d_full_name.setText("—")
        self._d_bill_to.setText("—")
        self._d_note.setText("No note available")
        self._notes_body.setPlainText("")
        contacts_lbl = self._contacts_page.findChild(QLabel, "customerCenterTabLabel_contacts")
        if contacts_lbl is not None:
            contacts_lbl.setText("Contacts for this customer (name, email, phone from the customer record).")

    def _passes_txn_filters(self, row: dict) -> bool:
        kind = row.get("kind") or ""
        show = self._show.currentText()
        if show == _SHOW_INVOICES and kind != "invoice":
            return False
        if show == _SHOW_PAYMENTS and kind != "payment":
            return False
        filt = self._filter_by.currentText()
        if kind == "invoice":
            bal = float(row.get("open_balance") or 0)
            aging = (row.get("aging") or "").strip()
            if filt == _FILTER_OPEN and bal <= 0.005:
                return False
            if filt == _FILTER_OVERDUE and not aging:
                return False
            if filt == _FILTER_PAID and bal > 0.005:
                return False
        elif filt in (_FILTER_OPEN, _FILTER_OVERDUE, _FILTER_PAID) and kind == "payment":
            if filt != _FILTER_PAID:
                return False
        if not _in_date_range(row.get("date") or "", self._date_range.currentText(), date.today()):
            return False
        return True

    def _reload_txn_table(self) -> None:
        if self._focused_customer_id is None:
            self._txn_rows = []
            visible: list[dict] = []
        elif self._conn is None:
            self._txn_rows = []
            visible = []
        else:
            try:
                self._txn_rows = business.list_customer_center_transactions(
                    self._conn, self._focused_customer_id
                )
            except sqlite3.Error:
                self._txn_rows = []
            visible = [r for r in self._txn_rows if self._passes_txn_filters(r)]
        self._fill_txn_table(self._txn_tbl, visible, include_customer=False)
        amt_total = sum(float(r.get("amount") or 0) for r in visible)
        ob_total = sum(float(r.get("open_balance") or 0) for r in visible)
        self._txn_amount_total.setText(_fmt_money(amt_total))
        self._txn_open_total.setText(_fmt_money(ob_total))
        empty = customer_center_empty_sentence(
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
                rows = business.list_customer_center_transactions(self._conn, None)
            except sqlite3.Error:
                rows = []
        self._fill_txn_table(self._left_txn_tbl, rows, include_customer=True)

    def _fill_txn_table(
        self, tbl: QTableWidget, rows: list[dict], *, include_customer: bool
    ) -> None:
        tbl.setSortingEnabled(False)
        if include_customer:
            tbl.setRowCount(len(rows))
            for i, r in enumerate(rows):
                it0 = _readonly_item(r.get("type") or "")
                it0.setData(_ROLE_CUSTOMER_ID, int(r["customer_id"]))
                it0.setData(_ROLE_KIND, r.get("kind") or "")
                it0.setData(_ROLE_RECORD_ID, int(r["record_id"]))
                tbl.setItem(i, 0, it0)
                tbl.setItem(i, 1, _readonly_item(_display_date(r.get("date") or "")))
                tbl.setItem(i, 2, _readonly_item(escape_ampersand_for_qt(r.get("customer_name") or "")))
                amt = float(r.get("amount") or 0)
                amt_it = FloatSortTableItem(_fmt_money(amt), amt)
                amt_it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                amt_it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                tbl.setItem(i, 3, amt_it)
        else:
            tbl.setRowCount(len(rows))
            for i, r in enumerate(rows):
                it0 = _readonly_item(r.get("num") or "")
                it0.setData(_ROLE_CUSTOMER_ID, int(r["customer_id"]))
                it0.setData(_ROLE_KIND, r.get("kind") or "")
                it0.setData(_ROLE_RECORD_ID, int(r["record_id"]))
                tbl.setItem(i, 0, it0)
                tbl.setItem(i, 1, _readonly_item(_display_date(r.get("date") or "")))
                tbl.setItem(i, 2, _readonly_item(_display_date(r.get("due_date") or "")))
                tbl.setItem(i, 3, _readonly_item(r.get("aging") or ""))
                amt = float(r.get("amount") or 0)
                ob = float(r.get("open_balance") or 0)
                amt_it = FloatSortTableItem(_fmt_money(amt), amt)
                amt_it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                amt_it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                tbl.setItem(i, 4, amt_it)
                ob_it = FloatSortTableItem(_fmt_money(ob), ob)
                ob_it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                ob_it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                tbl.setItem(i, 5, ob_it)

    def _selected_txn(self) -> Optional[tuple[str, int]]:
        row = self._txn_tbl.currentRow()
        if row < 0:
            return None
        it = self._txn_tbl.item(row, 0)
        if it is None:
            return None
        if it.data(_ROLE_IS_TOTAL):
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
        if kind == "invoice":
            self.openInvoiceRequested.emit(rid)
        elif kind == "payment":
            self.openPaymentRequested.emit(rid)

    def _on_edit_selected_txn(self) -> None:
        picked = self._selected_txn()
        if picked is None:
            message_box_information_ok(
                self,
                "Manage Transactions",
                "Select an invoice or payment row first.",
                ok_tip="Close; click a row in the transaction grid.",
            )
            return
        kind, rid = picked
        if kind == "invoice":
            self.openInvoiceRequested.emit(rid)
        else:
            self.openPaymentRequested.emit(rid)

    def _on_new_create_invoices(self) -> None:
        self.createInvoicesRequested.emit(self._focused_id())

    def _on_income_tracker(self) -> None:
        self.incomeTrackerRequested.emit(self._focused_id())

    def _on_new_receive_payments(self) -> None:
        self.receivePaymentsRequested.emit(self._focused_id())

    def _on_quickreport(self) -> None:
        self._right_tabs.setCurrentIndex(0)
        self._show.setCurrentText(_SHOW_ALL)
        self._filter_by.setCurrentText(_FILTER_ALL)
        self._date_range.setCurrentText(_DATE_ALL)

    def _on_open_balance_report(self) -> None:
        self._right_tabs.setCurrentIndex(0)
        self._show.setCurrentText(_SHOW_INVOICES)
        self._filter_by.setCurrentText(_FILTER_OPEN)
        self._date_range.setCurrentText(_DATE_ALL)
        self.arAgingSummaryRequested.emit()

    def _on_attach_hint(self) -> None:
        message_box_information_ok(
            self,
            "Attachments",
            "Customer attachments are not stored on the customer record yet. "
            "Use Create Invoices to work the selected customer's invoices.",
            ok_tip="Close; double-click an invoice row to open Create Invoices.",
        )

    def _on_word_letters(self) -> None:
        message_box_information_ok(
            self,
            "Word",
            "Customer letters (Word) are not wired yet.",
            ok_tip="Close; use Print for a customer list or transaction grid.",
        )

    def _on_print_customer_list(self) -> None:
        names = []
        for row in range(self._customer_tbl.rowCount()):
            it = self._customer_tbl.item(row, _COL_NAME)
            bal = self._customer_tbl.item(row, _COL_BAL)
            if it is None:
                continue
            names.append(f"{it.text()}\t{bal.text() if bal is not None else ''}")
        body = "\n".join(names) if names else "(no customers)"
        message_box_information_ok(
            self,
            "Print customer list",
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
            ok_tip="Close; double-click an invoice row to open Create Invoices.",
        )

    def _job_parent_id(self) -> int | None:
        if self._focused_customer_id is None:
            return None
        row = self._customer_summary_by_id.get(self._focused_customer_id)
        if row is None:
            return self._focused_customer_id
        pid = row.get("parent_customer_id")
        if pid is not None:
            return int(pid)
        return int(self._focused_customer_id)

    def _new_c(self) -> None:
        from desktop_app.new_customer_dialog import run_new_customer_dialog

        cid = run_new_customer_dialog(self, self._conn)
        if not cid:
            return
        self._focused_customer_id = int(cid)
        self.customerRecordsChanged.emit()
        self._refresh()

    def _new_job(self) -> None:
        from desktop_app.new_customer_dialog import run_new_customer_dialog

        parent_id = self._job_parent_id()
        if parent_id is None:
            message_box_warning_ok(
                self,
                "Add Job",
                "Create a customer first, then add a job under that customer.",
                ok_tip="Close; use New Customer & Job → New Customer… first.",
            )
            return
        cid = run_new_customer_dialog(
            self,
            self._conn,
            initial_as_job=True,
            initial_parent_customer_id=parent_id,
        )
        if not cid:
            return
        self._focused_customer_id = int(cid)
        self.customerRecordsChanged.emit()
        self._refresh()

    def _edit_c(self) -> None:
        from desktop_app.extra_tabs import run_edit_customer_dialog

        if run_edit_customer_dialog(self, self._conn, self._focused_customer_id):
            self.customerRecordsChanged.emit()
            self._refresh()

    def _export_customers(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export customers", "customers.csv", "CSV (*.csv)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            n = business.write_customers_csv(self._conn, path)
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
            f"Exported {n} customer(s) to {escape_ampersand_for_qt(path)}",
            ok_tip="Close; open the CSV from the path shown." + CSV_EXPORT_OK_TIP_SUFFIX,
        )
