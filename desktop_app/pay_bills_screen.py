"""Pay Bills — QuickBooks Pro Desktop Pay Bills window.

Select-bills box, Payment box (Pay From / date / method / check no.), unpaid-bills
grid, and Pay Selected Bills follow classic QB Pro Pay Bills (slightly cleaner
spacing/buttons than a gray Win32 photocopy — not QBO).

Posting writes ``ap_payments`` via :func:`probooksai.business.record_ap_payment`
and a bank register outflow tagged ``BILLPMT`` (memo) so the Number column shows
that type next to CHK/PMT/DEP.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date, timedelta
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QColor, QPalette, QShowEvent, QTextDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from desktop_app.flexible_date import configure_qdate_edit_us, format_iso_to_us_display
from desktop_app.invoice_preferences import configure_printer_for_payment_print
from desktop_app.payment_receipt_pdf import ap_payment_html_string, save_ap_payment_pdf
from desktop_app.qt_combo_ids import coerce_combo_int_id
from desktop_app.qt_mnemonic import (
    escape_ampersand_for_qt,
    message_box_critical_ok,
    message_box_information_ok,
    message_box_warning_ok,
)
from desktop_app.theme import DISABLED_FG
from probooksai import business

if TYPE_CHECKING:
    from probooksai.bank_import import BankDatabase

# Match Create Invoices / Enter Bills / Write Checks: light canvas, dark captions.
_PAY_CANVAS = "#E8ECF1"
_PAY_PAPER = "#FFFFFF"
_PAY_PANEL = "#F4F7FA"
_PAY_STRIPE = "#D0E6F4"
_PAY_CAPTION = "#4A5560"
_PAY_GRID = "#C0C8D0"
_PAY_HEADER = "#D8DEE6"
_PAY_TEXT = "#1A1A1A"
_PAY_TITLE = "#5B6770"
_PAY_ACCENT = "#2563A8"
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
_RIBBON_BTN_HEIGHT_PX = 24
_FOOTER_BTN_HEIGHT_PX = 26
_RIBBON_MAX_HEIGHT_PX = 50
_LINE_ROW_HEIGHT_PX = 22
_DISC_WINDOW_DAYS = 10
_AP_ACCOUNT_LABEL = "Accounts Payable"
REGISTER_BILLPMT_MEMO = "BILLPMT"
_TO_PRINT_REF = "To Print"

_METHOD_CHECK = "Check"
_METHOD_CARD = "Credit Card"
_METHOD_ECHECK = "e-Check"
_METHOD_ONLINE = "Online Bank Pmt"

_SORT_DUE = "Due Date"
_SORT_DISC = "Discount Date"
_SORT_VENDOR = "Vendor"
_SORT_AMT = "Amount Due"

_ROLE_BILL_ID = Qt.ItemDataRole.UserRole
_ROLE_VENDOR_ID = Qt.ItemDataRole.UserRole + 1
_ROLE_AMT_DUE = Qt.ItemDataRole.UserRole + 2

_COL_CHECK = 0
_COL_DATE = 1
_COL_REF = 2
_COL_VENDOR = 3
_COL_DUE = 4
_COL_DISC = 5
_COL_AMT_DUE = 6
_COL_AMT_PAY = 7


def _parse_iso_date(s: str) -> Optional[date]:
    raw = (s or "").strip()[:10]
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def discount_date_iso(bill_date: str, due_date: str = "") -> str:
    """Classic 2/10 window: ten days after the bill date, not later than the due date."""
    bd = _parse_iso_date(bill_date)
    if bd is None:
        return (due_date or "").strip()[:10]
    disc = bd + timedelta(days=_DISC_WINDOW_DAYS)
    dd = _parse_iso_date(due_date)
    if dd is not None and dd < disc:
        disc = dd
    return disc.isoformat()


def _action_button_qss(*, primary: bool = False) -> str:
    r = _TOP_STRIP_RADIUS_PX
    if primary:
        return (
            f"QPushButton {{ background-color: {_PAY_ACCENT}; border: 1px solid {_PAY_ACCENT}; "
            f"border-radius: {r}px; color: #FFFFFF; "
            f"font-size: {_TOP_STRIP_BODY_FONT_PX}px; padding: 0 14px; font-weight: 600; }}"
            f"QPushButton:hover {{ background-color: #1D4F8C; border: 1px solid #1D4F8C; }}"
            f"QPushButton:pressed {{ background-color: #163E6E; }}"
            f"QPushButton:disabled {{ color: #D7E3F0; background-color: #8AA7C7; "
            f"border: 1px solid #8AA7C7; }}"
        )
    return (
        f"QPushButton {{ background-color: {WORKFLOW_CONTROL_FACE}; border: 1px solid {_STRIP_BTN_OUTLINE}; "
        f"border-radius: {r}px; color: {_PAY_TEXT}; "
        f"font-size: {_TOP_STRIP_BODY_FONT_PX}px; padding: 0 12px; }}"
        f"QPushButton:hover {{ background-color: {WORKFLOW_CONTROL_HOVER}; }}"
        f"QPushButton:pressed {{ background-color: {WORKFLOW_CONTROL_PRESSED}; }}"
        f"QPushButton:disabled {{ color: {DISABLED_FG}; background-color: {WORKFLOW_CONTROL_FACE}; }}"
    )


def _input_qss(widget: str = "QLineEdit") -> str:
    return (
        f"{widget} {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_PAY_GRID}; "
        f"padding: 2px 6px; color: {_PAY_TEXT}; font-size: {_TOP_STRIP_BODY_FONT_PX}px; }}"
    )


def _zebra_cell_qss(widget: str, row: int) -> str:
    bg = _PAY_STRIPE if row % 2 else WORKFLOW_INPUT_BG
    return (
        f"{widget} {{ background-color: {bg}; border: none; "
        f"padding: 1px 4px; color: {_PAY_TEXT}; font-size: {_TOP_STRIP_BODY_FONT_PX}px; }}"
        f"{widget}:focus {{ background-color: {WORKFLOW_INPUT_BG}; }}"
    )


def _blank_zero_spin(s: QDoubleSpinBox) -> QDoubleSpinBox:
    s.setSpecialValueText(" ")
    return s


def _money_spin(*, row: int | None = None, blank_zero: bool = False) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(0.0, 999_999_999.99)
    s.setDecimals(2)
    s.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
    s.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    if row is None:
        s.setStyleSheet(_input_qss("QDoubleSpinBox"))
    else:
        s.setStyleSheet(_zebra_cell_qss("QDoubleSpinBox", row))
    if blank_zero:
        _blank_zero_spin(s)
    return s


def _light_form_palette() -> QPalette:
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(_PAY_PAPER))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(_PAY_TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(WORKFLOW_INPUT_BG))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(_PAY_STRIPE))
    pal.setColor(QPalette.ColorRole.Text, QColor(_PAY_TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(WORKFLOW_CONTROL_FACE))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(_PAY_TEXT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(_PAY_ACCENT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(_PAY_CAPTION))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(_PAY_PANEL))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(_PAY_TEXT))
    return pal


def _readonly_item(text: str, *, align_right: bool = False) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    it.setForeground(QColor(_PAY_TEXT))
    if align_right:
        it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return it


def _fmt_money(value: float) -> str:
    return f"{value:,.2f}"


def _box_frame_qss(object_name: str) -> str:
    return (
        f"QFrame#{object_name} {{ background-color: {_PAY_PAPER}; "
        f"border: 1px solid #B7C9DE; border-radius: 6px; }}"
    )


class PayBillsScreen(QWidget):
    """Unpaid vendor bills from the company file; pay selected rows and post AP + BILLPMT register line.

    Signals
    -------
    apPaymentPosted
        Emitted after a successful Pay Selected Bills so Bank Register / Write Checks can refresh.
    """

    apPaymentPosted = Signal()

    _COLS = (
        "✓",
        "DATE",
        "REF. NO.",
        "VENDOR",
        "DUE DATE",
        "DISC. DATE",
        "AMT. DUE",
        "AMT. TO PAY",
    )

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        ap_conn: Optional[sqlite3.Connection] = None,
        bank_db: Optional["BankDatabase"] = None,
    ) -> None:
        super().__init__(parent)
        self._ap_conn = ap_conn
        self._bank_db = bank_db
        self._cached_bills: list = []
        self._row_checks: list[QCheckBox] = []
        self._payment_edits: list[QDoubleSpinBox] = []
        self._row_due: list[float] = []
        self._last_ap_payment_ids: list[int] = []
        self._suppress = False
        self.setWindowTitle("Pay Bills")
        self.setMinimumSize(960, 640)
        self.setToolTip(
            "Pay Bills: select unpaid vendor bills, set amounts, and Pay Selected Bills. "
            "Creates a BILLPMT register line from the Pay From account. "
            "Same company .db (File → Backup / Restore, probooks.backup)."
        )
        self._build_ui()
        self._load_bank_accounts_combo()
        self._load_bills_from_db()
        self._sync_check_number_field()
        self._update_ending_balance()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.reload()

    def reload(self) -> None:
        """Reload open bills and bank accounts (tab switch / after Enter Bills)."""
        self._load_bank_accounts_combo()
        self._load_bills_from_db()
        self._sync_check_number_field()
        self._update_ending_balance()

    def _style_button(self, b: QPushButton, *, primary: bool = False, height: int = _RIBBON_BTN_HEIGHT_PX) -> None:
        b.setStyleSheet(_action_button_qss(primary=primary))
        b.setFixedHeight(height)
        b.setAutoDefault(False)
        b.setDefault(False)

    def _caption(self, text: str) -> QLabel:
        cap = QLabel(text)
        cap.setStyleSheet(
            f"color: {_PAY_CAPTION}; font-size: {_TOP_STRIP_CAPTION_FONT_PX}px; "
            "font-weight: bold; letter-spacing: 0.04em; background: transparent; border: none;"
        )
        return cap

    def _stacked_field(self, caption: str, editor: QWidget) -> QWidget:
        wrap = QWidget()
        wrap.setObjectName("payBillsMetaField")
        wrap.setAutoFillBackground(True)
        pal = wrap.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(_PAY_PAPER))
        pal.setColor(QPalette.ColorRole.WindowText, QColor(_PAY_CAPTION))
        wrap.setPalette(pal)
        wrap.setStyleSheet(
            f"QWidget#payBillsMetaField {{ background-color: {_PAY_PAPER}; border: none; }}"
        )
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)
        lay.addWidget(self._caption(caption))
        if isinstance(editor, (QLineEdit, QDateEdit, QComboBox, QDoubleSpinBox)):
            editor.setFixedHeight(_FIELD_HEIGHT_PX)
        if isinstance(editor, (QLineEdit, QComboBox, QDoubleSpinBox)):
            editor.setStyleSheet(_input_qss(editor.metaObject().className()))
        elif isinstance(editor, QDateEdit):
            editor.setStyleSheet(_input_qss("QDateEdit"))
        lay.addWidget(editor)
        wrap.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        return wrap

    def _build_ui(self) -> None:
        self.setPalette(_light_form_palette())
        self.setAutoFillBackground(True)
        self.setStyleSheet(
            f"PayBillsScreen {{ background-color: {_PAY_CANVAS}; color: {_PAY_TEXT}; }}"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 4, 6, 4)
        outer.setSpacing(4)
        self._build_ribbon(outer)
        self._build_header_boxes(outer)
        self._build_bills_grid(outer)
        self._build_footer(outer)
        self._refresh_summary()

    def _build_ribbon(self, play: QVBoxLayout) -> None:
        self._pay_ribbon = QTabWidget()
        self._pay_ribbon.setObjectName("payBillsRibbonTabs")
        self._pay_ribbon.setDocumentMode(True)
        self._pay_ribbon.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._pay_ribbon.setFixedHeight(_RIBBON_MAX_HEIGHT_PX)
        self._pay_ribbon.setStyleSheet(
            f"QTabWidget#payBillsRibbonTabs::pane {{ border: 1px solid {_PAY_GRID}; "
            f"background: {_PAY_PANEL}; top: -1px; }}"
            f"QTabWidget#payBillsRibbonTabs QTabBar::tab {{ padding: 2px 10px; min-height: 16px; }}"
        )

        main_rib = QWidget()
        main_lay = QHBoxLayout(main_rib)
        main_lay.setContentsMargins(4, 2, 4, 2)
        main_lay.setSpacing(4)

        self._btn_find = QPushButton("Find")
        self._btn_find.setToolTip("Cycle to the next vendor that has open bills.")
        self._btn_new = QPushButton("Clear Payments")
        self._btn_new.setToolTip("Uncheck all bills and clear amounts to pay.")
        self._btn_select_all = QPushButton("Select All Bills")
        self._btn_select_all.setToolTip("Check every visible bill and fill Amt. To Pay with Amt. Due.")
        self._btn_print = QPushButton("Print")
        self._btn_print.setToolTip("Print the most recently posted bill payment from this session.")
        self._btn_attach = QPushButton("Attach File")
        self._btn_attach.setToolTip("Attachments on bill payments are not wired yet.")
        self._btn_attach.setEnabled(False)
        self._btn_pay = QPushButton("Pay Selected Bills")
        self._btn_pay.setToolTip(
            "Post AP payments for checked rows and write a BILLPMT line on the Pay From register."
        )
        for b in (
            self._btn_find,
            self._btn_new,
            self._btn_select_all,
            self._btn_print,
            self._btn_attach,
        ):
            self._style_button(b)
            main_lay.addWidget(b)
        self._style_button(self._btn_pay, primary=True)
        main_lay.addWidget(self._btn_pay)
        main_lay.addStretch(1)
        self._pay_ribbon.addTab(main_rib, "Main")

        def _later_tab(body: str) -> QWidget:
            w = QWidget()
            lay = QHBoxLayout(w)
            lay.setContentsMargins(8, 4, 8, 4)
            lb = QLabel(body)
            lb.setStyleSheet(f"color: {_PAY_CAPTION}; font-size: 11px; background: transparent;")
            lay.addWidget(lb)
            return w

        reports = QWidget()
        reports_lay = QHBoxLayout(reports)
        reports_lay.setContentsMargins(4, 2, 4, 2)
        reports_lay.setSpacing(4)
        self._btn_export_ap_pdf = QPushButton("Export last AP payment PDF…")
        self._btn_export_ap_pdf.setToolTip(
            "Save the most recently posted AP payment from this session as a PDF."
        )
        self._btn_print_ap = QPushButton("Print last AP payment…")
        self._btn_print_ap.setToolTip("Print the most recently posted AP payment (same layout as PDF).")
        for b in (self._btn_export_ap_pdf, self._btn_print_ap):
            self._style_button(b)
            b.setEnabled(False)
            reports_lay.addWidget(b)
        reports_lay.addStretch(1)
        self._pay_ribbon.addTab(reports, "Reports")
        self._pay_ribbon.addTab(
            _later_tab("Set Discount / Set Credits follow later QuickBooks screens."),
            "Discounts",
        )
        play.addWidget(self._pay_ribbon)

        _uc = Qt.ConnectionType.UniqueConnection
        self._btn_find.clicked.connect(self._on_find_vendor, _uc)
        self._btn_new.clicked.connect(self._on_clear_selection, _uc)
        self._btn_select_all.clicked.connect(self._on_select_all, _uc)
        self._btn_print.clicked.connect(self._on_print_last_ap_payment, _uc)
        self._btn_pay.clicked.connect(self._on_pay_selected, _uc)
        self._btn_export_ap_pdf.clicked.connect(self._on_export_last_ap_payment_pdf, _uc)
        self._btn_print_ap.clicked.connect(self._on_print_last_ap_payment, _uc)

    def _build_header_boxes(self, play: QVBoxLayout) -> None:
        title_row = QHBoxLayout()
        title_row.setContentsMargins(2, 0, 2, 0)
        self._title = QLabel("Pay Bills")
        self._title.setObjectName("payBillsTitle")
        self._title.setStyleSheet(
            f"font-size: {_TITLE_FONT_PX}px; font-weight: bold; color: {_PAY_TITLE}; "
            "background: transparent;"
        )
        title_row.addWidget(self._title)
        title_row.addStretch(1)
        play.addLayout(title_row)

        boxes = QHBoxLayout()
        boxes.setSpacing(8)
        boxes.addWidget(self._build_select_bills_box(), 3)
        boxes.addWidget(self._build_payment_box(), 2)
        play.addLayout(boxes)

    def _build_select_bills_box(self) -> QFrame:
        box = QFrame()
        box.setObjectName("payBillsSelectBox")
        box.setStyleSheet(_box_frame_qss("payBillsSelectBox"))
        lay = QVBoxLayout(box)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(8)
        lay.addWidget(self._caption("SELECT BILLS TO BE PAID"))

        due_row = QHBoxLayout()
        due_row.setSpacing(8)
        self._chk_due_on_or_before = QCheckBox("Due on or before")
        self._chk_due_on_or_before.setObjectName("payBillsDueOnOrBefore")
        self._chk_due_on_or_before.setToolTip(
            "When on (and Show all bills is off), only bills due on or before this date."
        )
        self._chk_due_on_or_before.setStyleSheet("background: transparent;")
        self._due_cutoff = QDateEdit()
        configure_qdate_edit_us(self._due_cutoff)
        self._due_cutoff.setDate(QDate.currentDate())
        self._due_cutoff.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._due_cutoff.setFixedHeight(_FIELD_HEIGHT_PX)
        self._due_cutoff.setStyleSheet(_input_qss("QDateEdit"))
        self._due_cutoff.setToolTip("Due-on-or-before cutoff used with the checkbox to the left.")
        due_row.addWidget(self._chk_due_on_or_before)
        due_row.addWidget(self._due_cutoff, 0)
        due_row.addStretch(1)
        lay.addLayout(due_row)

        self._chk_show_all = QCheckBox("Show all bills")
        self._chk_show_all.setObjectName("payBillsShowAll")
        self._chk_show_all.setChecked(True)
        self._chk_show_all.setToolTip("Show every unpaid bill, ignoring the due-on-or-before date.")
        self._chk_show_all.setStyleSheet("background: transparent;")
        lay.addWidget(self._chk_show_all)

        self._vendor_filter = QComboBox()
        self._vendor_filter.setObjectName("payBillsVendorFilter")
        self._vendor_filter.setMinimumWidth(200)
        self._vendor_filter.setToolTip("Show unpaid bills for all vendors or one vendor.")
        lay.addWidget(self._stacked_field("FILTER BY VENDOR", self._vendor_filter))

        self._sort_by = QComboBox()
        self._sort_by.setObjectName("payBillsSortBy")
        self._sort_by.addItems([_SORT_DUE, _SORT_DISC, _SORT_VENDOR, _SORT_AMT])
        self._sort_by.setToolTip("Sort the unpaid-bills list.")
        lay.addWidget(self._stacked_field("SORT BILLS BY", self._sort_by))

        self._ap_account = QLineEdit(_AP_ACCOUNT_LABEL)
        self._ap_account.setObjectName("payBillsApAccount")
        self._ap_account.setReadOnly(True)
        self._ap_account.setToolTip("A/P account these bills post against.")
        lay.addWidget(self._stacked_field("A/P ACCOUNT", self._ap_account))

        self._chk_due_on_or_before.toggled.connect(self._rebuild_table)
        self._chk_show_all.toggled.connect(self._rebuild_table)
        self._due_cutoff.dateChanged.connect(self._rebuild_table)
        self._vendor_filter.currentIndexChanged.connect(self._rebuild_table)
        self._sort_by.currentIndexChanged.connect(self._rebuild_table)
        return box

    def _build_payment_box(self) -> QFrame:
        box = QFrame()
        box.setObjectName("payBillsPaymentBox")
        box.setStyleSheet(_box_frame_qss("payBillsPaymentBox"))
        lay = QGridLayout(box)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setHorizontalSpacing(10)
        lay.setVerticalSpacing(6)
        lay.addWidget(self._caption("PAYMENT"), 0, 0, 1, 2)

        self._pay_date = QDateEdit()
        configure_qdate_edit_us(self._pay_date)
        self._pay_date.setDate(QDate.currentDate())
        self._pay_date.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._pay_date.setToolTip("Payment date stored on the AP payment and BILLPMT register line.")
        lay.addWidget(self._stacked_field("DATE", self._pay_date), 1, 0, 1, 2)

        self._method = QComboBox()
        self._method.setObjectName("payBillsMethod")
        self._method.addItems([_METHOD_CHECK, _METHOD_CARD, _METHOD_ECHECK, _METHOD_ONLINE])
        self._method.setToolTip("How this bill payment is made. Check is the usual Pay Bills method.")
        self._method.currentIndexChanged.connect(self._on_method_changed)
        lay.addWidget(self._stacked_field("METHOD", self._method), 2, 0, 1, 2)

        self._account = QComboBox()
        self._account.setObjectName("payBillsPayFrom")
        self._account.setMinimumWidth(180)
        self._account.setToolTip("Pay From bank account. Required — writes the BILLPMT register line.")
        self._account.currentIndexChanged.connect(self._on_pay_from_changed)
        lay.addWidget(self._stacked_field("PAY FROM", self._account), 3, 0, 1, 2)

        self._lbl_ending = QLabel("0.00")
        self._lbl_ending.setObjectName("payBillsEndingBalance")
        self._lbl_ending.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._lbl_ending.setStyleSheet(
            f"color: {_PAY_TEXT}; font-size: 14px; font-weight: 700; background: transparent;"
        )
        self._lbl_ending.setToolTip("Current register balance of the Pay From account.")
        lay.addWidget(self._stacked_field("ENDING BALANCE", self._lbl_ending), 4, 0, 1, 2)

        self._chk_to_print = QCheckBox("To be printed")
        self._chk_to_print.setObjectName("payBillsToBePrinted")
        self._chk_to_print.setToolTip(
            "When on, Check No. is stored as To Print (classic QuickBooks print-later checks)."
        )
        self._chk_to_print.setStyleSheet("background: transparent;")
        self._chk_to_print.toggled.connect(self._sync_check_number_field)
        lay.addWidget(self._chk_to_print, 5, 0, 1, 2)

        self._reference = QLineEdit()
        self._reference.setObjectName("payBillsCheckNumber")
        self._reference.setToolTip("Check number or payment reference written to the register.")
        lay.addWidget(self._stacked_field("CHECK NO.", self._reference), 6, 0, 1, 2)
        return box

    def _build_bills_grid(self, play: QVBoxLayout) -> None:
        wrap = QFrame()
        wrap.setObjectName("payBillsGridWrap")
        wrap.setStyleSheet(
            f"QFrame#payBillsGridWrap {{ background: {_PAY_PAPER}; border: none; }}"
        )
        gl = QVBoxLayout(wrap)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(0)

        self._table = QTableWidget(0, len(self._COLS))
        self._table.setObjectName("payBillsTable")
        self._table.setHorizontalHeaderLabels(self._COLS)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hh = self._table.horizontalHeader()
        hh.setStretchLastSection(True)
        hh.setSectionResizeMode(_COL_CHECK, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(_COL_CHECK, 36)
        hh.setSectionResizeMode(_COL_VENDOR, QHeaderView.ResizeMode.Stretch)
        for col in (_COL_DATE, _COL_REF, _COL_DUE, _COL_DISC, _COL_AMT_DUE, _COL_AMT_PAY):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setStyleSheet(
            f"QTableWidget#payBillsTable {{"
            f" background-color: {_PAY_PAPER};"
            f" alternate-background-color: {_PAY_STRIPE};"
            f" color: {_PAY_TEXT};"
            f" gridline-color: {_PAY_GRID};"
            f" border: 1px solid {_PAY_GRID};"
            " }"
            f"QHeaderView::section {{"
            f" background-color: {_PAY_HEADER};"
            f" color: {_PAY_CAPTION};"
            f" padding: 4px; border: 1px solid {_PAY_GRID};"
            " font-weight: 600;"
            " }}"
        )
        gl.addWidget(self._table, 1)
        play.addWidget(wrap, 1)

    def _build_footer(self, play: QVBoxLayout) -> None:
        footer = QFrame()
        footer.setObjectName("payBillsFooterBand")
        footer.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        footer.setStyleSheet(
            f"QFrame#payBillsFooterBand {{ background-color: {_PAY_PANEL}; "
            f"border: 1px solid {_PAY_GRID}; border-radius: 4px; }}"
        )
        bot = QHBoxLayout(footer)
        bot.setContentsMargins(8, 6, 8, 6)
        bot.setSpacing(10)

        self._btn_clear_bot = QPushButton("Clear Payments")
        self._btn_clear_bot.setToolTip("Uncheck all bills and clear amounts to pay.")
        self._btn_select_all_bot = QPushButton("Select All Bills")
        self._btn_select_all_bot.setToolTip("Check every visible bill and fill Amt. To Pay.")
        self._style_button(self._btn_clear_bot, height=_FOOTER_BTN_HEIGHT_PX)
        self._style_button(self._btn_select_all_bot, height=_FOOTER_BTN_HEIGHT_PX)
        bot.addWidget(self._btn_clear_bot)
        bot.addWidget(self._btn_select_all_bot)
        bot.addStretch(1)

        summary = QVBoxLayout()
        summary.setContentsMargins(0, 0, 0, 0)
        summary.setSpacing(2)
        summary.addWidget(self._caption("TOTALS FOR SELECTED BILLS"))
        self._lbl_selected = QLabel("BILLS:  0")
        self._lbl_amt_due = QLabel("AMT. DUE:  0.00")
        self._lbl_payment_sum = QLabel("AMT. TO PAY:  0.00")
        for lb in (self._lbl_selected, self._lbl_amt_due, self._lbl_payment_sum):
            lb.setStyleSheet(f"color: {_PAY_TEXT}; font-size: 12px; background: transparent;")
            lb.setAlignment(Qt.AlignmentFlag.AlignRight)
            summary.addWidget(lb)
        bot.addLayout(summary)

        self._btn_pay_bot = QPushButton("Pay Selected Bills")
        self._btn_pay_bot.setToolTip(
            "Post AP payments for checked rows and write a BILLPMT line on the Pay From register."
        )
        self._style_button(self._btn_pay_bot, primary=True, height=_FOOTER_BTN_HEIGHT_PX)
        bot.addWidget(self._btn_pay_bot)
        play.addWidget(footer)

        _uc = Qt.ConnectionType.UniqueConnection
        self._btn_clear_bot.clicked.connect(self._on_clear_selection, _uc)
        self._btn_select_all_bot.clicked.connect(self._on_select_all, _uc)
        self._btn_pay_bot.clicked.connect(self._on_pay_selected, _uc)

    def _selected_vendor_id(self) -> Optional[int]:
        return coerce_combo_int_id(self._vendor_filter.currentData())

    def _selected_bank_id(self) -> Optional[int]:
        return coerce_combo_int_id(self._account.currentData())

    def _pay_method(self) -> str:
        return (self._method.currentText() or _METHOD_CHECK).strip() or _METHOD_CHECK

    def _on_method_changed(self, _index: int = 0) -> None:
        is_check = self._pay_method() == _METHOD_CHECK
        self._chk_to_print.setEnabled(is_check)
        if not is_check:
            self._chk_to_print.setChecked(False)
        self._sync_check_number_field()

    def _on_pay_from_changed(self, _index: int = 0) -> None:
        self._sync_check_number_field()
        self._update_ending_balance()

    def _next_check_number(self) -> str:
        bank_id = self._selected_bank_id()
        if self._bank_db is None or bank_id is None:
            return "1"
        try:
            txns = self._bank_db.list_transactions(bank_id)
        except (sqlite3.Error, TypeError, ValueError):
            return "1"
        max_n = 0
        for t in txns:
            ref = str(t["ref_number"] or "").strip()
            if ref.isdigit():
                max_n = max(max_n, int(ref))
        return str(max_n + 1)

    def _sync_check_number_field(self) -> None:
        if self._chk_to_print.isChecked() and self._pay_method() == _METHOD_CHECK:
            self._reference.setText(_TO_PRINT_REF)
            self._reference.setReadOnly(True)
            return
        self._reference.setReadOnly(False)
        if (self._reference.text() or "").strip() in ("", _TO_PRINT_REF):
            self._reference.setText(self._next_check_number())

    def _update_ending_balance(self) -> None:
        bank_id = self._selected_bank_id()
        if self._bank_db is None or bank_id is None:
            self._lbl_ending.setText("0.00")
            return
        try:
            txns = self._bank_db.list_transactions(bank_id)
            bal = sum(float(t["amount"] or 0) for t in txns)
        except (sqlite3.Error, TypeError, ValueError):
            self._lbl_ending.setText("0.00")
            return
        self._lbl_ending.setText(_fmt_money(bal))
        color = "#C0392B" if bal < 0 else _PAY_TEXT
        self._lbl_ending.setStyleSheet(
            f"color: {color}; font-size: 14px; font-weight: 700; background: transparent;"
        )

    def _load_bank_accounts_combo(self) -> None:
        prev = self._selected_bank_id()
        self._account.blockSignals(True)
        self._account.clear()
        rows: list = []
        if self._ap_conn is not None:
            try:
                rows = self._ap_conn.execute(
                    "SELECT id, name FROM bank_accounts WHERE is_active = 1 ORDER BY name"
                ).fetchall()
            except sqlite3.Error:
                rows = []
        for r in rows:
            bid = coerce_combo_int_id(r["id"])
            if bid is None:
                continue
            name = (r["name"] or "").strip() or f"Account #{bid}"
            self._account.addItem(escape_ampersand_for_qt(name), bid)
        self._account.blockSignals(False)
        if prev is not None:
            for i in range(self._account.count()):
                if coerce_combo_int_id(self._account.itemData(i)) == prev:
                    self._account.setCurrentIndex(i)
                    return
        if self._account.count() > 0:
            self._account.setCurrentIndex(0)

    def _populate_vendor_filter(self) -> None:
        prev = self._selected_vendor_id()
        self._vendor_filter.blockSignals(True)
        self._vendor_filter.clear()
        self._vendor_filter.addItem("All vendors", None)
        seen: set[int] = set()
        for r in self._cached_bills:
            d = dict(r)
            vid = coerce_combo_int_id(d.get("vendor_id"))
            if vid is None or vid in seen:
                continue
            seen.add(vid)
            name = (d.get("vendor_name") or "").strip() or f"Vendor #{vid}"
            self._vendor_filter.addItem(escape_ampersand_for_qt(name), vid)
        self._vendor_filter.blockSignals(False)
        if prev is not None:
            for i in range(self._vendor_filter.count()):
                if coerce_combo_int_id(self._vendor_filter.itemData(i)) == prev:
                    self._vendor_filter.setCurrentIndex(i)
                    return
        self._vendor_filter.setCurrentIndex(0)

    def _bill_passes_filter(self, row: sqlite3.Row) -> bool:
        d = dict(row)
        vid = coerce_combo_int_id(d.get("vendor_id"))
        want = self._selected_vendor_id()
        if want is not None and vid != want:
            return False
        if self._chk_show_all.isChecked():
            return True
        if not self._chk_due_on_or_before.isChecked():
            return True
        due_dt = _parse_iso_date((d.get("due_date") or "").strip())
        if due_dt is None:
            due_dt = _parse_iso_date((d.get("bill_date") or "").strip())
        if due_dt is None:
            return True
        cutoff = self._due_cutoff.date()
        cut = date(cutoff.year(), cutoff.month(), cutoff.day())
        return due_dt <= cut

    def _sort_key(self, row: sqlite3.Row):
        d = dict(row)
        mode = self._sort_by.currentText()
        due = (d.get("due_date") or d.get("bill_date") or "")
        disc = discount_date_iso(d.get("bill_date") or "", d.get("due_date") or "")
        vendor = (d.get("vendor_name") or "").lower()
        amt = float(d.get("balance_due") or 0.0)
        bid = int(d.get("bill_id") or 0)
        if mode == _SORT_VENDOR:
            return (vendor, due, bid)
        if mode == _SORT_AMT:
            return (-amt, due, bid)
        if mode == _SORT_DISC:
            return (disc, vendor, bid)
        return (due, vendor, bid)

    def _load_bills_from_db(self) -> None:
        self._cached_bills = []
        if self._ap_conn is None:
            self._populate_vendor_filter()
            self._rebuild_table()
            return
        try:
            self._cached_bills = list(business.list_open_bills_for_pay_bills(self._ap_conn))
        except sqlite3.Error:
            self._cached_bills = []
        self._populate_vendor_filter()
        self._rebuild_table()

    def _rebuild_table(self) -> None:
        self._row_checks.clear()
        self._payment_edits.clear()
        self._row_due.clear()
        self._table.setRowCount(0)
        visible = [r for r in self._cached_bills if self._bill_passes_filter(r)]
        visible.sort(key=self._sort_key)
        self._table.setRowCount(len(visible))
        for i, r in enumerate(visible):
            d = dict(r)
            bid = int(d["bill_id"])
            vid = int(d["vendor_id"])
            bal = float(d["balance_due"] or 0.0)
            self._row_due.append(bal)

            cb = QCheckBox()
            cb.setStyleSheet("background: transparent; margin-left: 8px;")
            cb.setToolTip("Select this bill to pay. Fills Amt. To Pay with Amt. Due.")
            self._table.setCellWidget(i, _COL_CHECK, cb)
            self._row_checks.append(cb)

            bd = (d.get("bill_date") or "").strip()
            date_it = _readonly_item(format_iso_to_us_display(bd) if bd else "")
            date_it.setData(_ROLE_BILL_ID, bid)
            date_it.setData(_ROLE_VENDOR_ID, vid)
            date_it.setData(_ROLE_AMT_DUE, bal)
            self._table.setItem(i, _COL_DATE, date_it)

            ref = (d.get("vendor_invoice_number") or "").strip()
            self._table.setItem(i, _COL_REF, _readonly_item(ref))

            v_it = _readonly_item((d.get("vendor_name") or "").strip() or "—")
            v_it.setData(_ROLE_BILL_ID, bid)
            v_it.setData(_ROLE_VENDOR_ID, vid)
            self._table.setItem(i, _COL_VENDOR, v_it)

            dd = (d.get("due_date") or "").strip()
            self._table.setItem(
                i, _COL_DUE, _readonly_item(format_iso_to_us_display(dd) if dd else "")
            )

            disc = discount_date_iso(bd, dd)
            self._table.setItem(
                i, _COL_DISC, _readonly_item(format_iso_to_us_display(disc) if disc else "")
            )
            self._table.setItem(i, _COL_AMT_DUE, _readonly_item(_fmt_money(bal), align_right=True))

            pay_spin = _money_spin(row=i, blank_zero=True)
            pay_spin.setRange(0.0, max(0.0, bal))
            pay_spin.setToolTip("Amount to apply to this bill on this payment.")
            self._table.setCellWidget(i, _COL_AMT_PAY, pay_spin)
            self._payment_edits.append(pay_spin)
            self._table.setRowHeight(i, _LINE_ROW_HEIGHT_PX)

            cb.stateChanged.connect(lambda _s, row=i: self._on_row_checked(row))
            pay_spin.valueChanged.connect(lambda _v, row=i: self._on_amt_edited(row))

        self._refresh_summary()

    def _on_row_checked(self, row: int) -> None:
        if self._suppress or row >= len(self._row_checks):
            self._refresh_summary()
            return
        cb = self._row_checks[row]
        spin = self._payment_edits[row]
        due = self._row_due[row] if row < len(self._row_due) else 0.0
        self._suppress = True
        if cb.isChecked() and spin.value() <= 0.005:
            spin.setValue(due)
        elif not cb.isChecked():
            spin.setValue(0.0)
        self._suppress = False
        self._refresh_summary()

    def _on_amt_edited(self, row: int) -> None:
        if self._suppress or row >= len(self._row_checks):
            self._refresh_summary()
            return
        cb = self._row_checks[row]
        spin = self._payment_edits[row]
        self._suppress = True
        cb.setChecked(spin.value() > 0.005)
        self._suppress = False
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        n = 0
        total_pay = 0.0
        total_due = 0.0
        for i, (cb, sp) in enumerate(zip(self._row_checks, self._payment_edits)):
            if cb.isChecked():
                n += 1
                total_pay += sp.value()
                if i < len(self._row_due):
                    total_due += self._row_due[i]
        self._lbl_selected.setText(f"BILLS:  {n}")
        self._lbl_amt_due.setText(f"AMT. DUE:  {_fmt_money(total_due)}")
        self._lbl_payment_sum.setText(f"AMT. TO PAY:  {_fmt_money(total_pay)}")

    def _on_clear_selection(self) -> None:
        self._suppress = True
        for c in self._row_checks:
            c.setChecked(False)
        for s in self._payment_edits:
            s.setValue(0.0)
        self._suppress = False
        self._refresh_summary()

    def _on_select_all(self) -> None:
        self._suppress = True
        for i, (cb, sp) in enumerate(zip(self._row_checks, self._payment_edits)):
            cb.setChecked(True)
            if i < len(self._row_due):
                sp.setValue(self._row_due[i])
        self._suppress = False
        self._refresh_summary()

    def _on_find_vendor(self) -> None:
        combo = self._vendor_filter
        if combo.count() <= 1:
            return
        idx = combo.currentIndex()
        combo.setCurrentIndex(1 if idx <= 0 else (idx + 1) % combo.count() or 1)

    def _on_pay_selected(self) -> None:
        if self._ap_conn is None:
            message_box_information_ok(
                self,
                "Pay Bills",
                "Open a company database to pay bills.",
                ok_tip="Close; use File → Open company… then try again.",
            )
            return
        bank_account_id = self._selected_bank_id()
        if bank_account_id is None:
            message_box_warning_ok(
                self,
                "Pay Bills",
                "Choose a Pay From bank account. Bill payments write a BILLPMT line on that register.",
                ok_tip="Close; pick an account in Pay From.",
            )
            return
        payment_date = self._pay_date.date().toString("yyyy-MM-dd")
        ref = self._reference.text().strip()
        method = self._pay_method()

        by_vendor: dict[int, list[tuple[int, float]]] = defaultdict(list)
        for row, (cb, sp) in enumerate(zip(self._row_checks, self._payment_edits)):
            if not cb.isChecked():
                continue
            amt = round(sp.value(), 2)
            if amt <= 0.005:
                continue
            it = self._table.item(row, _COL_VENDOR) or self._table.item(row, _COL_DATE)
            if it is None:
                continue
            bid = coerce_combo_int_id(it.data(_ROLE_BILL_ID))
            vid = coerce_combo_int_id(it.data(_ROLE_VENDOR_ID))
            if bid is None or vid is None:
                continue
            by_vendor[vid].append((bid, amt))

        if not by_vendor:
            message_box_warning_ok(
                self,
                "Pay Bills",
                "Select at least one bill and enter an amount to pay.",
                ok_tip="Check a row (Amt. To Pay fills from Amt. Due), then try again.",
            )
            return

        conn = self._ap_conn
        for vid, allocs in by_vendor.items():
            for bid, amt in allocs:
                row = conn.execute(
                    "SELECT balance_due FROM bills WHERE id = ?", (bid,)
                ).fetchone()
                if row is None:
                    message_box_warning_ok(
                        self,
                        "Pay Bills",
                        f"Bill #{bid} is no longer in the database. Refresh and try again.",
                        ok_tip="Switch away and back to Pay Bills, then re-select bills.",
                    )
                    return
                bal = float(row["balance_due"] or 0.0)
                if amt > bal + 0.02:
                    message_box_warning_ok(
                        self,
                        "Pay Bills",
                        f"Payment amount for bill #{bid} exceeds open balance ({bal:,.2f}).",
                        ok_tip="Lower Amt. To Pay or reload the list.",
                    )
                    return

        bank_db = self._bank_db
        posted = 0
        bank_errors: list[str] = []
        self._last_ap_payment_ids.clear()

        for vid, allocs in sorted(by_vendor.items()):
            total = round(sum(a for _, a in allocs), 2)
            if total <= 0.005:
                continue
            vrow = conn.execute(
                "SELECT name FROM vendors WHERE id = ?", (vid,)
            ).fetchone()
            vname = (vrow["name"] if vrow else "").strip() or f"Vendor #{vid}"
            try:
                pid = business.record_ap_payment(
                    conn,
                    vid,
                    payment_date,
                    total,
                    allocs,
                    bank_account_id=bank_account_id,
                    method=method,
                    reference=ref,
                    memo=REGISTER_BILLPMT_MEMO,
                )
            except (sqlite3.Error, ValueError, TypeError) as exc:
                message_box_critical_ok(
                    self,
                    "Pay Bills",
                    f"Could not record payment for {vname}: {exc}",
                    ok_tip="Close; check amounts and try again.",
                )
                return
            posted += 1
            self._last_ap_payment_ids.append(int(pid))

            if bank_db is not None:
                try:
                    tid = bank_db.insert_manual_transaction(
                        bank_account_id,
                        payment_date,
                        -total,
                        description=vname,
                        ref_number=ref,
                        memo=REGISTER_BILLPMT_MEMO,
                        coa_account=_AP_ACCOUNT_LABEL,
                    )
                    business.link_bank_transaction(conn, tid, "ap_payment", int(pid))
                except (sqlite3.Error, OSError, ValueError, TypeError) as exc:
                    bank_errors.append(f"{vname}: {exc}")

        self._cached_bills = list(business.list_open_bills_for_pay_bills(conn))
        self._populate_vendor_filter()
        self._rebuild_table()
        self._sync_check_number_field()
        self._update_ending_balance()

        on = bool(self._last_ap_payment_ids)
        self._btn_export_ap_pdf.setEnabled(on)
        self._btn_print_ap.setEnabled(on)
        self.apPaymentPosted.emit()

        if bank_errors:
            message_box_warning_ok(
                self,
                "Pay Bills",
                "AP payment(s) saved, but the bank register line failed for: "
                + "; ".join(bank_errors),
                ok_tip="Add a matching bank transaction manually or fix the error and retry.",
            )
        else:
            message_box_information_ok(
                self,
                "Pay Bills",
                f"Posted {posted} bill payment(s). Paid bills are no longer open; "
                "the register shows BILLPMT.",
                ok_tip="Close; unpaid bills remain in the list.",
            )

    def _on_export_last_ap_payment_pdf(self) -> None:
        if self._ap_conn is None or not self._last_ap_payment_ids:
            return
        pid = self._last_ap_payment_ids[-1]
        default_name = f"AP-Payment-{pid}.pdf"
        path, _filt = QFileDialog.getSaveFileName(
            self,
            "Export AP payment as PDF",
            default_name,
            "PDF files (*.pdf);;All files (*.*)",
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path = f"{path}.pdf"
        try:
            save_ap_payment_pdf(self._ap_conn, pid, path)
        except OSError as exc:
            message_box_warning_ok(
                self,
                "Pay Bills",
                f"Could not write PDF: {exc}",
                ok_tip="Choose a writable folder and try again.",
            )
        except Exception as exc:  # noqa: BLE001
            message_box_warning_ok(
                self,
                "Pay Bills",
                f"PDF export failed: {exc}",
                ok_tip="Close and try again.",
            )

    def _on_print_last_ap_payment(self) -> None:
        if self._ap_conn is None or not self._last_ap_payment_ids:
            return
        pid = self._last_ap_payment_ids[-1]
        doc = QTextDocument()
        try:
            doc.setHtml(ap_payment_html_string(self._ap_conn, pid))
        except Exception as exc:  # noqa: BLE001
            message_box_warning_ok(
                self,
                "Pay Bills",
                f"Could not prepare payment for printing: {exc}",
                ok_tip="Close and try again.",
            )
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        if not configure_printer_for_payment_print(self, printer):
            return
        doc.print_(printer)
