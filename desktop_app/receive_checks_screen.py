"""Receive Payments — QuickBooks Pro Desktop Customer Payment form.

Header, payment-method buttons, open-invoice grid, and footer follow Johnny's QB Pro
Receive Payments screenshot (slightly cleaner spacing/buttons than a gray Win32 photocopy).

Payments post to **Undeposited Funds** (``ar_payments.bank_account_id`` stays empty). Make
Deposits picks those into a bank account; this screen does not write a register deposit.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QDate, QEvent, Qt, Signal
from PySide6.QtGui import QColor, QPalette, QTextDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from desktop_app.ar_customer_actions import (
    export_ar_payment_allocations_csv,
    export_ar_payments_csv,
    open_record_ar_payment_dialog,
)
from desktop_app.flexible_date import configure_qdate_edit_us, format_iso_to_us_display
from desktop_app.invoice_preferences import configure_printer_for_payment_print
from desktop_app.payment_receipt_pdf import ar_payment_html_string, save_ar_payment_pdf
from desktop_app.qt_combo_ids import coerce_combo_int_id
from desktop_app.qt_mnemonic import (
    message_box_critical_ok,
    message_box_information_ok,
    message_box_warning_ok,
)
from desktop_app.theme import DISABLED_FG
from probooksai import business

if TYPE_CHECKING:
    from probooksai.bank_import import BankDatabase

# Match Create Invoices / Enter Bills chrome: light canvas, dark captions, not a navy redaction bar.
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
_PAY_WATERMARK = "#9AA8B8"
WORKFLOW_INPUT_BG = "#FFFFFF"
WORKFLOW_CONTROL_FACE = "#F7F8FA"
WORKFLOW_CONTROL_HOVER = "#E4EEF7"
WORKFLOW_CONTROL_PRESSED = "#C9D8EC"
_STRIP_BTN_OUTLINE = "#B4BCC6"
_TOP_STRIP_RADIUS_PX = 4
_TOP_STRIP_CAPTION_FONT_PX = 10
_TOP_STRIP_BODY_FONT_PX = 12
_FIELD_HEIGHT_PX = 22
_TITLE_FONT_PX = 22
_RIBBON_BTN_HEIGHT_PX = 24
_FOOTER_BTN_HEIGHT_PX = 26
_RIBBON_MAX_HEIGHT_PX = 50
_METHOD_BTN_HEIGHT_PX = 52
_LINE_ROW_HEIGHT_PX = 22
_DEFAULT_AR_ACCOUNT = "Accounts Receivable"
_UNDEPOSITED_FUNDS_LABEL = "Undeposited Funds"
_EMPTY_HINT = "Select the customer or job in the Received From field."

_ROLE_INVOICE_ID = Qt.ItemDataRole.UserRole
_ROLE_CUSTOMER_ID = Qt.ItemDataRole.UserRole + 1
_ROLE_ORIG_AMT = Qt.ItemDataRole.UserRole + 2
_ROLE_AMT_DUE = Qt.ItemDataRole.UserRole + 3

_COL_CHECK = 0
_COL_DATE = 1
_COL_NUMBER = 2
_COL_ORIG = 3
_COL_DUE = 4
_COL_PAYMENT = 5

_METHOD_CASH = "Cash"
_METHOD_CHECK = "Check"
_METHOD_CARD = "Credit Card"
_METHOD_ECHECK = "e-Check"


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
    """Empty line cells stay blank at 0. Qt ignores an empty specialValueText, so a space stands in."""
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
    """Light QB-style palette so unnamed QWidget wraps are not navy slabs from the app theme."""
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


class ReceiveChecksScreen(QWidget):
    """Customer Payment header, open invoices from the company DB, post AR to Undeposited Funds.

    Signals
    -------
    arPaymentPosted(list[int])
        Emitted after a successful save. Carries the **invoice ids** that received an allocation
        so other screens (notably **Create Invoices**) can refresh PAID badge / balance state.
    """

    arPaymentPosted = Signal(list)

    _COLS = ("✓", "DATE", "NUMBER", "ORIG. AMT.", "AMT. DUE", "PAYMENT")

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
        self._cached_invoices: list = []
        self._row_checks: list[QCheckBox] = []
        self._payment_edits: list[QDoubleSpinBox] = []
        self._row_due: list[float] = []
        self._last_ar_payment_ids: list[int] = []
        self._suppress_apply = False
        self._pay_method = _METHOD_CHECK
        self.setWindowTitle("Receive Payments")
        self.setMinimumSize(960, 640)
        self.setToolTip(
            "Receive Payments: record customer payments against open invoices. "
            "Payments go to Undeposited Funds until Make Deposits. "
            "Same company .db (File → Backup / Restore, probooks.backup)."
        )
        self._build_ui()
        self._load_invoices_from_db()

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
        """Caption above the control on a white wrap (not a navy redaction bar)."""
        wrap = QWidget()
        wrap.setObjectName("receivePaymentsMetaField")
        wrap.setAutoFillBackground(True)
        pal = wrap.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(_PAY_PAPER))
        pal.setColor(QPalette.ColorRole.WindowText, QColor(_PAY_CAPTION))
        wrap.setPalette(pal)
        wrap.setStyleSheet(
            f"QWidget#receivePaymentsMetaField {{ background-color: {_PAY_PAPER}; border: none; }}"
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

    def _ar_account_choices(self) -> list[str]:
        names = [_DEFAULT_AR_ACCOUNT]
        if self._ap_conn is not None:
            try:
                label = business._get_coa_account_label(self._ap_conn, "1100")
            except (sqlite3.Error, TypeError, ValueError, AttributeError):
                label = ""
            if label and label != "1100" and label not in names:
                names.insert(0, label)
        return names

    def _build_ui(self) -> None:
        self.setPalette(_light_form_palette())
        self.setAutoFillBackground(True)
        self.setStyleSheet(
            f"ReceiveChecksScreen {{ background-color: {_PAY_CANVAS}; color: {_PAY_TEXT}; }}"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 4, 6, 4)
        outer.setSpacing(4)
        self._build_ribbon(outer)
        self._build_header_form(outer)
        self._build_invoice_grid(outer)
        self._build_footer(outer)
        self._sync_ar_toolbar()
        self._refresh_totals()

    def _build_ribbon(self, play: QVBoxLayout) -> None:
        self._pay_ribbon = QTabWidget()
        self._pay_ribbon.setObjectName("receivePaymentsRibbonTabs")
        self._pay_ribbon.setDocumentMode(True)
        self._pay_ribbon.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._pay_ribbon.setFixedHeight(_RIBBON_MAX_HEIGHT_PX)
        self._pay_ribbon.setStyleSheet(
            f"QTabWidget#receivePaymentsRibbonTabs::pane {{ border: 1px solid {_PAY_GRID}; "
            f"background: {_PAY_PANEL}; top: -1px; }}"
            f"QTabWidget#receivePaymentsRibbonTabs QTabBar::tab {{ padding: 2px 10px; min-height: 16px; }}"
        )

        main_rib = QWidget()
        main_lay = QHBoxLayout(main_rib)
        main_lay.setContentsMargins(4, 2, 4, 2)
        main_lay.setSpacing(4)

        self._btn_find = QPushButton("Find")
        self._btn_find.setToolTip("Select the previous customer with open invoices.")
        self._btn_new = QPushButton("New")
        self._btn_new.setToolTip("Start a blank customer payment (does not save).")
        self._btn_delete = QPushButton("Delete")
        self._btn_delete.setToolTip("Deleting a saved payment is not available yet.")
        self._btn_delete.setEnabled(False)
        self._btn_print = QPushButton("Print")
        self._btn_print.setToolTip("Print the most recently posted payment from this session.")
        self._btn_email = QPushButton("Email")
        self._btn_email.setToolTip("Email from Receive Payments is not wired yet. Use Print.")
        self._btn_email.setEnabled(False)
        self._btn_attach = QPushButton("Attach File")
        self._btn_attach.setToolTip("Attachments on customer payments are not wired yet.")
        self._btn_attach.setEnabled(False)
        self._btn_auto_apply = QPushButton("Auto Apply Payment")
        self._btn_auto_apply.setObjectName("receivePaymentsAutoApply")
        self._btn_auto_apply.setCheckable(True)
        self._btn_auto_apply.setChecked(True)
        self._btn_auto_apply.setToolTip(
            "When on, the payment amount fills the PAYMENT column from oldest invoice to newest."
        )
        self._btn_apply_credits = QPushButton("Discounts And Credits")
        self._btn_apply_credits.setToolTip("Discounts and unused credits are not wired yet.")
        self._btn_apply_credits.setEnabled(False)
        self._btn_apply_credits.clicked.connect(self._on_apply_credits_placeholder)

        for b in (
            self._btn_find,
            self._btn_new,
            self._btn_delete,
            self._btn_print,
            self._btn_email,
            self._btn_attach,
            self._btn_auto_apply,
            self._btn_apply_credits,
        ):
            self._style_button(b)
            main_lay.addWidget(b)
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

        self._pay_ribbon.addTab(
            _later_tab("Formatting follows later QuickBooks screens."),
            "Formatting",
        )

        reports = QWidget()
        reports_lay = QHBoxLayout(reports)
        reports_lay.setContentsMargins(4, 2, 4, 2)
        reports_lay.setSpacing(4)
        self._btn_record_ar = QPushButton("Record customer payment…")
        self._btn_record_ar.setToolTip("Open the AR payment dialog (alternative to this form).")
        self._btn_export_ar_pay = QPushButton("Export AR payments CSV…")
        self._btn_export_ar_pay.setToolTip("Export customer payment records to CSV (UTF-8 BOM for Excel).")
        self._btn_export_ar_alloc = QPushButton("Export AR payment allocations CSV…")
        self._btn_export_ar_alloc.setToolTip("Export how payments were applied to invoices.")
        self._btn_export_ar_pdf = QPushButton("Export last payment PDF…")
        self._btn_export_ar_pdf.setToolTip(
            "Save the most recently posted customer payment from this session as a PDF."
        )
        self._btn_print_ar = QPushButton("Print last payment…")
        self._btn_print_ar.setToolTip("Print the most recently posted payment (same layout as PDF).")
        for b in (
            self._btn_record_ar,
            self._btn_export_ar_pay,
            self._btn_export_ar_alloc,
            self._btn_export_ar_pdf,
            self._btn_print_ar,
        ):
            self._style_button(b)
            reports_lay.addWidget(b)
        reports_lay.addStretch(1)
        self._pay_ribbon.addTab(reports, "Reports")
        self._pay_ribbon.addTab(
            _later_tab("Card processing follows later QuickBooks screens."),
            "Payments",
        )
        play.addWidget(self._pay_ribbon)

        _uc = Qt.ConnectionType.UniqueConnection
        self._btn_find.clicked.connect(self._on_find_customer, _uc)
        self._btn_new.clicked.connect(self._on_clear, _uc)
        self._btn_print.clicked.connect(self._on_print_last_ar_payment, _uc)
        self._btn_auto_apply.toggled.connect(self._on_auto_apply_toggled, _uc)
        self._btn_record_ar.clicked.connect(self._on_record_ar_payment, _uc)
        self._btn_export_ar_pay.clicked.connect(self._on_export_ar_payments, _uc)
        self._btn_export_ar_alloc.clicked.connect(self._on_export_ar_allocations, _uc)
        self._btn_export_ar_pdf.clicked.connect(self._on_export_last_ar_payment_pdf, _uc)
        self._btn_print_ar.clicked.connect(self._on_print_last_ar_payment, _uc)

    def _method_button(self, label: str, method: str) -> QPushButton:
        b = QPushButton(label)
        b.setCheckable(True)
        b.setFixedHeight(_METHOD_BTN_HEIGHT_PX)
        b.setMinimumWidth(108)
        b.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        b.setProperty("payMethod", method)
        b.setStyleSheet(
            f"QPushButton {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_PAY_GRID}; "
            f"border-radius: 4px; color: {_PAY_TEXT}; font-size: 11px; font-weight: 700; "
            "padding: 6px 10px; }"
            f"QPushButton:checked {{ border: 2px solid {_PAY_ACCENT}; background: #E8F1FA; }}"
            f"QPushButton:hover {{ background: {WORKFLOW_CONTROL_HOVER}; }}"
        )
        b.setToolTip(f"Payment method: {method}.")
        return b

    def _build_header_form(self, play: QVBoxLayout) -> None:
        form = QFrame()
        form.setObjectName("receivePaymentsHeaderBand")
        form.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        form.setStyleSheet(
            f"QFrame#receivePaymentsHeaderBand {{ background-color: {_PAY_PAPER}; "
            f"border: 1px solid #B7C9DE; border-radius: 6px; }}"
        )
        hb = QVBoxLayout(form)
        hb.setContentsMargins(10, 6, 10, 8)
        hb.setSpacing(6)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        self._title = QLabel("Customer Payment")
        self._title.setObjectName("receivePaymentsTitle")
        self._title.setStyleSheet(
            f"font-size: {_TITLE_FONT_PX}px; font-weight: bold; color: {_PAY_TITLE}; "
            "background: transparent;"
        )
        title_row.addWidget(self._title)
        title_row.addStretch(1)
        bal_col = QVBoxLayout()
        bal_col.setContentsMargins(0, 0, 0, 0)
        bal_col.setSpacing(0)
        bal_cap = self._caption("CUSTOMER BALANCE")
        bal_cap.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._cust_balance = QLabel("0.00")
        self._cust_balance.setObjectName("receivePaymentsCustomerBalance")
        self._cust_balance.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._cust_balance.setStyleSheet(
            f"color: {_PAY_TEXT}; font-size: 18px; font-weight: 700; background: transparent;"
        )
        self._cust_balance.setToolTip("Open balance for the customer or job in Received From.")
        bal_col.addWidget(bal_cap)
        bal_col.addWidget(self._cust_balance)
        title_row.addLayout(bal_col)
        hb.addLayout(title_row)

        self._customer_filter = QComboBox()
        self._customer_filter.setObjectName("receivePaymentsReceivedFrom")
        self._customer_filter.setMinimumWidth(220)
        self._customer_filter.setToolTip(
            "Customer or job this payment is received from. A parent account includes open "
            "invoices for jobs under that account."
        )
        self._customer_filter.currentIndexChanged.connect(self._on_received_from_changed)

        self._pay_amount = _money_spin()
        self._pay_amount.setObjectName("receivePaymentsAmount")
        self._pay_amount.setToolTip(
            "Payment amount to apply. Auto Apply Payment fills the invoice PAYMENT column oldest first."
        )
        self._pay_amount.valueChanged.connect(self._on_pay_amount_changed)

        self._pay_date = QDateEdit()
        configure_qdate_edit_us(self._pay_date)
        self._pay_date.setDate(QDate.currentDate())
        self._pay_date.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._pay_date.setToolTip("Payment date.")

        self._check_num = QLineEdit()
        self._check_num.setObjectName("receivePaymentsCheckNumber")
        self._check_num.setToolTip("Check number or payment reference.")

        self._where_link = QLabel('<a href="#undeposited">Where does this payment go?</a>')
        self._where_link.setObjectName("receivePaymentsWhereLink")
        self._where_link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self._where_link.setOpenExternalLinks(False)
        self._where_link.setStyleSheet(
            f"color: {_PAY_ACCENT}; font-size: 11px; background: transparent;"
        )
        self._where_link.linkActivated.connect(self._on_where_payment_goes)

        received_col = QVBoxLayout()
        received_col.setContentsMargins(0, 0, 0, 0)
        received_col.setSpacing(2)
        received_col.addWidget(self._stacked_field("RECEIVED FROM", self._customer_filter))
        received_col.addWidget(self._where_link, 0, Qt.AlignmentFlag.AlignLeft)

        fields = QHBoxLayout()
        fields.setSpacing(10)
        fields.addLayout(received_col, 3)
        fields.addWidget(self._stacked_field("PAYMENT AMOUNT", self._pay_amount), 1)
        fields.addWidget(self._stacked_field("DATE", self._pay_date), 1)
        fields.addWidget(self._stacked_field("CHECK #", self._check_num), 1)
        hb.addLayout(fields)

        methods = QHBoxLayout()
        methods.setSpacing(6)
        self._method_group = QButtonGroup(self)
        self._method_group.setExclusive(True)
        self._btn_method_cash = self._method_button("CASH", _METHOD_CASH)
        self._btn_method_check = self._method_button("CHECK", _METHOD_CHECK)
        self._btn_method_card = self._method_button("CREDIT/DEBIT", _METHOD_CARD)
        self._btn_method_echeck = self._method_button("e-CHECK", _METHOD_ECHECK)
        self._btn_method_check.setChecked(True)
        for b in (
            self._btn_method_cash,
            self._btn_method_check,
            self._btn_method_card,
            self._btn_method_echeck,
        ):
            self._method_group.addButton(b)
            methods.addWidget(b)
        self._method_group.buttonClicked.connect(self._on_method_button)
        self._btn_method_more = QPushButton("MORE ▾")
        self._btn_method_more.setFixedHeight(_METHOD_BTN_HEIGHT_PX)
        self._btn_method_more.setMinimumWidth(80)
        self._btn_method_more.setStyleSheet(
            f"QPushButton {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_PAY_GRID}; "
            f"border-radius: 4px; color: {_PAY_TEXT}; font-size: 11px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: {WORKFLOW_CONTROL_HOVER}; }}"
        )
        self._btn_method_more.setToolTip("More payment methods (ACH, Other).")
        more_menu = QMenu(self._btn_method_more)
        more_menu.addAction("ACH", lambda: self._set_pay_method("ACH"))
        more_menu.addAction("Other", lambda: self._set_pay_method("Other"))
        self._btn_method_more.setMenu(more_menu)
        methods.addWidget(self._btn_method_more)
        methods.addStretch(1)

        self._ar_account = QComboBox()
        self._ar_account.setObjectName("receivePaymentsArAccount")
        self._ar_account.setEditable(False)
        self._ar_account.addItems(self._ar_account_choices())
        self._ar_account.setMinimumWidth(180)
        self._ar_account.setToolTip("Accounts Receivable account this payment applies against.")
        methods.addWidget(self._stacked_field("A/R ACCOUNT", self._ar_account), 0)
        hb.addLayout(methods)

        play.addWidget(form)

    def _build_invoice_grid(self, play: QVBoxLayout) -> None:
        wrap = QFrame()
        wrap.setObjectName("receivePaymentsGridWrap")
        wrap.setStyleSheet(
            f"QFrame#receivePaymentsGridWrap {{ background: {_PAY_PAPER}; border: none; }}"
        )
        gl = QVBoxLayout(wrap)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(0)

        self._table = QTableWidget(0, len(self._COLS))
        self._table.setObjectName("receiveChecksTable")
        self._table.setHorizontalHeaderLabels(self._COLS)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hh = self._table.horizontalHeader()
        hh.setStretchLastSection(True)
        hh.setSectionResizeMode(_COL_CHECK, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(_COL_CHECK, 36)
        for col in (_COL_DATE, _COL_NUMBER, _COL_ORIG, _COL_DUE):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        self._table.setStyleSheet(
            f"QTableWidget#receiveChecksTable {{"
            f" background-color: {WORKFLOW_INPUT_BG};"
            f" alternate-background-color: {_PAY_STRIPE};"
            f" color: {_PAY_TEXT};"
            f" gridline-color: {_PAY_GRID};"
            f" border: 1px solid {_PAY_GRID};"
            " }"
            f"QHeaderView::section {{"
            f" background-color: {_PAY_HEADER};"
            f" color: {_PAY_CAPTION};"
            f" padding: 4px; border: 1px solid {_PAY_GRID};"
            " font-weight: bold; font-size: 11px;"
            " }"
        )
        self._table.viewport().installEventFilter(self)
        gl.addWidget(self._table, 1)

        self._empty_hint = QLabel(_EMPTY_HINT)
        self._empty_hint.setObjectName("receivePaymentsEmptyHint")
        self._empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_hint.setStyleSheet(
            f"color: {_PAY_WATERMARK}; font-size: 16px; background: transparent; border: none;"
        )
        self._empty_hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._empty_hint.setParent(self._table.viewport())

        tot = QFrame()
        tot.setObjectName("receivePaymentsTotalsRow")
        tot.setStyleSheet(
            f"QFrame#receivePaymentsTotalsRow {{ background-color: {_PAY_HEADER}; "
            f"border: 1px solid {_PAY_GRID}; border-top: none; }}"
        )
        tot.setFixedHeight(26)
        tr = QHBoxLayout(tot)
        tr.setContentsMargins(8, 2, 10, 2)
        tr.setSpacing(12)
        self._lbl_grid_totals = QLabel("Totals")
        self._lbl_grid_totals.setStyleSheet(
            f"color: {_PAY_TEXT}; font-size: 12px; font-weight: 600; background: transparent;"
        )
        tr.addWidget(self._lbl_grid_totals)
        tr.addStretch(1)
        self._lbl_tot_orig = QLabel("0.00")
        self._lbl_tot_due = QLabel("0.00")
        self._lbl_tot_pay = QLabel("0.00")
        for lb in (self._lbl_tot_orig, self._lbl_tot_due, self._lbl_tot_pay):
            lb.setStyleSheet(f"color: {_PAY_TEXT}; font-size: 12px; background: transparent;")
            lb.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lb.setMinimumWidth(88)
            tr.addWidget(lb)
        gl.addWidget(tot)
        play.addWidget(wrap, 1)

    def _build_footer(self, play: QVBoxLayout) -> None:
        footer = QFrame()
        footer.setObjectName("receivePaymentsFooterBand")
        footer.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        footer.setStyleSheet(
            f"QFrame#receivePaymentsFooterBand {{ background-color: {_PAY_PANEL}; "
            f"border: 1px solid {_PAY_GRID}; border-radius: 4px; }}"
        )
        bot = QHBoxLayout(footer)
        bot.setContentsMargins(8, 6, 8, 6)
        bot.setSpacing(16)

        memo_col = QVBoxLayout()
        memo_col.setContentsMargins(0, 0, 0, 0)
        memo_col.setSpacing(1)
        memo_col.addWidget(self._caption("MEMO"))
        self._memo_edit = QLineEdit()
        self._memo_edit.setObjectName("receivePaymentsMemo")
        self._memo_edit.setFixedHeight(_FIELD_HEIGHT_PX)
        self._memo_edit.setStyleSheet(_input_qss("QLineEdit"))
        self._memo_edit.setToolTip("Internal memo stored with this payment.")
        memo_col.addWidget(self._memo_edit)
        bot.addLayout(memo_col, 1)

        bot.addStretch(1)

        summary = QVBoxLayout()
        summary.setContentsMargins(0, 0, 0, 0)
        summary.setSpacing(2)
        summary.addWidget(self._caption("AMOUNTS FOR SELECTED INVOICES"))
        self._lbl_amount_due = QLabel("AMOUNT DUE:  0.00")
        self._lbl_applied = QLabel("APPLIED:  0.00")
        self._lbl_discount_credits = QLabel("DISCOUNT AND CREDITS APPLIED:  0.00")
        self._lbl_total_selected = self._lbl_applied
        self._lbl_total_payment = self._lbl_applied
        self._lbl_amount_selected = self._lbl_applied
        for lb in (self._lbl_amount_due, self._lbl_applied, self._lbl_discount_credits):
            lb.setStyleSheet(f"color: {_PAY_TEXT}; font-size: 12px; background: transparent;")
            lb.setAlignment(Qt.AlignmentFlag.AlignRight)
            summary.addWidget(lb)
        bot.addLayout(summary)

        self._btn_save_close = QPushButton("Save && Close")
        self._btn_save_new = QPushButton("Save && New")
        self._btn_clear = QPushButton("Clear")
        self._btn_save_close.setToolTip(
            "Save this payment to Undeposited Funds and keep the form on this customer "
            "(tab analog of QuickBooks Save & Close)."
        )
        self._btn_save_new.setToolTip(
            "Save this payment to Undeposited Funds, then clear the form for a new payment."
        )
        self._btn_clear.setToolTip("Clear the form without saving.")
        self._btn_post = self._btn_save_new
        self._style_button(self._btn_save_close, height=_FOOTER_BTN_HEIGHT_PX)
        self._style_button(self._btn_save_new, primary=True, height=_FOOTER_BTN_HEIGHT_PX)
        self._style_button(self._btn_clear, height=_FOOTER_BTN_HEIGHT_PX)
        bot.addWidget(self._btn_save_close)
        bot.addWidget(self._btn_save_new)
        bot.addWidget(self._btn_clear)
        play.addWidget(footer)

        _uc = Qt.ConnectionType.UniqueConnection
        self._btn_save_close.clicked.connect(self._on_save_close, _uc)
        self._btn_save_new.clicked.connect(self._on_save_new, _uc)
        self._btn_clear.clicked.connect(self._on_clear, _uc)

    def eventFilter(self, obj, event):  # noqa: ANN001
        if obj is self._table.viewport() and event.type() == QEvent.Type.Resize:
            self._position_empty_hint()
        return super().eventFilter(obj, event)

    def _position_empty_hint(self) -> None:
        hint = getattr(self, "_empty_hint", None)
        table = getattr(self, "_table", None)
        if hint is None or table is None:
            return
        vp = table.viewport()
        hint.setGeometry(0, 0, vp.width(), vp.height())
        hint.raise_()

    def _set_empty_hint_visible(self, visible: bool) -> None:
        self._empty_hint.setVisible(visible)
        if visible:
            self._position_empty_hint()

    def _selected_customer_id(self) -> Optional[int]:
        return coerce_combo_int_id(self._customer_filter.currentData())

    def select_customer_by_id(self, customer_id: int) -> None:
        """Tiny Customer Center hook: Received From = *customer_id*."""
        self._populate_customer_filter()
        want = int(customer_id)
        for i in range(self._customer_filter.count()):
            if coerce_combo_int_id(self._customer_filter.itemData(i)) == want:
                self._customer_filter.setCurrentIndex(i)
                return

    def _on_received_from_changed(self, _index: int = 0) -> None:
        self._rebuild_table()
        if self._btn_auto_apply.isChecked() and self._pay_amount.value() > 0.005:
            self._auto_apply_fifo()
        self._refresh_totals()

    def _on_pay_amount_changed(self, _value: float = 0.0) -> None:
        if self._suppress_apply:
            return
        if self._btn_auto_apply.isChecked():
            self._auto_apply_fifo()
        self._refresh_totals()

    def _on_auto_apply_toggled(self, checked: bool) -> None:
        if checked and self._pay_amount.value() > 0.005:
            self._auto_apply_fifo()
            self._refresh_totals()

    def _on_method_button(self, button: QPushButton) -> None:
        method = button.property("payMethod")
        if method:
            self._pay_method = str(method)

    def _set_pay_method(self, method: str) -> None:
        self._pay_method = method
        for b in self._method_group.buttons():
            b.setChecked(False)

    def _on_where_payment_goes(self, _href: str = "") -> None:
        message_box_information_ok(
            self,
            "Where does this payment go?",
            "This payment is recorded to Undeposited Funds and applied to the invoices you select. "
            "It does not go straight into a bank account. Make Deposits picks undeposited "
            "payments into the bank — for example your checking account.",
            ok_tip="Close; continue recording the customer payment.",
        )

    def _on_find_customer(self) -> None:
        combo = self._customer_filter
        if combo.count() <= 1:
            return
        idx = combo.currentIndex()
        if idx <= 1:
            combo.setCurrentIndex(combo.count() - 1)
        else:
            combo.setCurrentIndex(idx - 1)

    def _populate_customer_filter(self) -> None:
        prev = coerce_combo_int_id(self._customer_filter.currentData())
        self._customer_filter.blockSignals(True)
        self._customer_filter.clear()
        self._customer_filter.addItem("", None)
        if self._ap_conn is not None:
            try:
                for cid, label in business.list_bill_to_customer_choices(self._ap_conn):
                    self._customer_filter.addItem(label, cid)
            except sqlite3.Error:
                pass
        self._customer_filter.blockSignals(False)
        if prev is not None:
            for i in range(self._customer_filter.count()):
                if coerce_combo_int_id(self._customer_filter.itemData(i)) == prev:
                    self._customer_filter.setCurrentIndex(i)
                    break

    def _invoice_passes_filter(self, d: dict) -> bool:
        fcid = self._selected_customer_id()
        if fcid is None:
            return False
        if self._ap_conn is None:
            return False
        try:
            ids = business.customer_ids_for_receive_payments_filter(self._ap_conn, fcid)
        except (sqlite3.Error, ValueError):
            ids = [fcid]
        return int(d.get("customer_id") or 0) in set(ids)

    def _update_cust_balance_label(self, visible_rows: list[dict]) -> None:
        s = sum(float(r.get("balance_due") or 0.0) for r in visible_rows)
        self._cust_balance.setText(_fmt_money(s) if self._selected_customer_id() is not None else "0.00")

    def _load_invoices_from_db(self) -> None:
        self._cached_invoices = []
        self._populate_customer_filter()
        if self._ap_conn is None:
            self._rebuild_table()
            return
        try:
            self._cached_invoices = list(
                business.list_open_invoices_for_receive_payments(self._ap_conn)
            )
        except sqlite3.Error:
            self._cached_invoices = []
        self._ar_account.blockSignals(True)
        self._ar_account.clear()
        self._ar_account.addItems(self._ar_account_choices())
        self._ar_account.blockSignals(False)
        self._rebuild_table()

    def _rebuild_table(self) -> None:
        self._row_checks.clear()
        self._payment_edits.clear()
        self._row_due.clear()
        self._table.setRowCount(0)
        if self._ap_conn is None or self._selected_customer_id() is None:
            self._update_cust_balance_label([])
            self._set_empty_hint_visible(True)
            self._refresh_totals()
            return
        visible: list[dict] = []
        for r in self._cached_invoices:
            d = dict(r)
            if self._invoice_passes_filter(d):
                visible.append(d)
        self._update_cust_balance_label(visible)
        self._set_empty_hint_visible(False)
        self._table.setRowCount(len(visible))
        for i, d in enumerate(visible):
            iid = int(d["invoice_id"])
            cid = int(d["customer_id"])
            bal = float(d["balance_due"] or 0.0)
            orig = float(d.get("total") or 0.0)
            self._row_due.append(bal)

            cb = QCheckBox()
            cb.setStyleSheet("background: transparent; margin-left: 8px;")
            self._table.setCellWidget(i, _COL_CHECK, cb)
            self._row_checks.append(cb)

            inv_dt = (d.get("invoice_date") or "").strip()
            date_it = _readonly_item(format_iso_to_us_display(inv_dt) if inv_dt else "")
            date_it.setData(_ROLE_CUSTOMER_ID, cid)
            self._table.setItem(i, _COL_DATE, date_it)

            num_it = _readonly_item((d.get("invoice_number") or "").strip())
            num_it.setData(_ROLE_INVOICE_ID, iid)
            num_it.setData(_ROLE_CUSTOMER_ID, cid)
            self._table.setItem(i, _COL_NUMBER, num_it)

            orig_it = _readonly_item(_fmt_money(orig), align_right=True)
            orig_it.setData(_ROLE_ORIG_AMT, orig)
            self._table.setItem(i, _COL_ORIG, orig_it)

            due_it = _readonly_item(_fmt_money(bal), align_right=True)
            due_it.setData(_ROLE_AMT_DUE, bal)
            self._table.setItem(i, _COL_DUE, due_it)

            pay_spin = _money_spin(row=i, blank_zero=True)
            pay_spin.setRange(0.0, max(0.0, bal))
            pay_spin.setValue(0.0)
            pay_spin.setToolTip("Amount to apply to this invoice.")
            self._table.setCellWidget(i, _COL_PAYMENT, pay_spin)
            self._payment_edits.append(pay_spin)
            self._table.setRowHeight(i, _LINE_ROW_HEIGHT_PX)

            cb.stateChanged.connect(lambda state, row=i: self._on_row_checked(row, state))
            pay_spin.valueChanged.connect(lambda *_a, row=i: self._on_row_payment_edited(row))
        self._refresh_totals()

    def _on_row_checked(self, row: int, state: int) -> None:
        if self._suppress_apply:
            return
        if row < 0 or row >= len(self._payment_edits):
            return
        spin = self._payment_edits[row]
        due = self._row_due[row] if row < len(self._row_due) else 0.0
        if int(state) == int(Qt.CheckState.Checked):
            if spin.value() <= 0.005:
                remaining = round(max(0.0, self._pay_amount.value() - self._applied_sum()), 2)
                apply = min(due, remaining) if remaining > 0.005 else due
                self._suppress_apply = True
                try:
                    spin.setValue(apply)
                    if remaining <= 0.005 and apply > 0.005:
                        self._pay_amount.blockSignals(True)
                        self._pay_amount.setValue(round(self._applied_sum(), 2))
                        self._pay_amount.blockSignals(False)
                finally:
                    self._suppress_apply = False
        else:
            self._suppress_apply = True
            try:
                spin.setValue(0.0)
            finally:
                self._suppress_apply = False
        self._refresh_totals()

    def _on_row_payment_edited(self, row: int) -> None:
        if self._suppress_apply:
            return
        if row < 0 or row >= len(self._row_checks):
            return
        spin = self._payment_edits[row]
        self._suppress_apply = True
        try:
            self._row_checks[row].setChecked(spin.value() > 0.005)
        finally:
            self._suppress_apply = False
        self._refresh_totals()

    def _auto_apply_fifo(self) -> None:
        remaining = round(float(self._pay_amount.value()), 2)
        self._suppress_apply = True
        try:
            for i, spin in enumerate(self._payment_edits):
                due = self._row_due[i] if i < len(self._row_due) else 0.0
                apply = min(due, remaining) if remaining > 0.005 else 0.0
                spin.setValue(apply)
                self._row_checks[i].setChecked(apply > 0.005)
                remaining = round(remaining - apply, 2)
        finally:
            self._suppress_apply = False

    def _applied_sum(self) -> float:
        return round(sum(sp.value() for sp in self._payment_edits), 2)

    def _orig_sum(self) -> float:
        total = 0.0
        for row in range(self._table.rowCount()):
            it = self._table.item(row, _COL_ORIG)
            if it is not None:
                try:
                    total += float(it.data(_ROLE_ORIG_AMT) or 0.0)
                except (TypeError, ValueError):
                    pass
        return round(total, 2)

    def _due_sum(self) -> float:
        return round(sum(self._row_due), 2)

    def _sync_ar_toolbar(self) -> None:
        on = self._ap_conn is not None
        has_last = on and bool(self._last_ar_payment_ids)
        self._btn_record_ar.setEnabled(on)
        self._btn_export_ar_pay.setEnabled(on)
        self._btn_export_ar_alloc.setEnabled(on)
        self._btn_export_ar_pdf.setEnabled(has_last)
        self._btn_print_ar.setEnabled(has_last)
        self._btn_print.setEnabled(has_last)
        self._btn_find.setEnabled(on)
        self._btn_save_close.setEnabled(on)
        self._btn_save_new.setEnabled(on)

    def _on_record_ar_payment(self) -> None:
        if self._ap_conn is None:
            return
        open_record_ar_payment_dialog(self, self._ap_conn, after_save=self._load_invoices_from_db)

    def _on_export_ar_payments(self) -> None:
        if self._ap_conn is None:
            return
        export_ar_payments_csv(self, self._ap_conn)

    def _on_export_ar_allocations(self) -> None:
        if self._ap_conn is None:
            return
        export_ar_payment_allocations_csv(self, self._ap_conn)

    def _selected_payment_sum(self) -> tuple[int, float]:
        n = 0
        total = 0.0
        for cb, sp in zip(self._row_checks, self._payment_edits):
            if cb.isChecked() or sp.value() > 0.005:
                n += 1
                total += sp.value()
        return n, round(total, 2)

    def _refresh_totals(self) -> None:
        _n, applied = self._selected_payment_sum()
        due = self._due_sum()
        orig = self._orig_sum()
        self._lbl_tot_orig.setText(_fmt_money(orig))
        self._lbl_tot_due.setText(_fmt_money(due))
        self._lbl_tot_pay.setText(_fmt_money(applied))
        self._lbl_amount_due.setText(f"AMOUNT DUE:  {_fmt_money(due)}")
        self._lbl_applied.setText(f"APPLIED:  {_fmt_money(applied)}")
        self._lbl_discount_credits.setText("DISCOUNT AND CREDITS APPLIED:  0.00")

    def _on_apply_credits_placeholder(self) -> None:
        pass

    def _collect_allocations(self) -> dict[int, list[tuple[int, float]]]:
        by_customer: dict[int, list[tuple[int, float]]] = {}
        for row, (cb, sp) in enumerate(zip(self._row_checks, self._payment_edits)):
            amt = round(sp.value(), 2)
            if amt <= 0.005:
                continue
            if not cb.isChecked() and amt <= 0.005:
                continue
            num_it = self._table.item(row, _COL_NUMBER)
            if num_it is None:
                continue
            iid = coerce_combo_int_id(num_it.data(_ROLE_INVOICE_ID))
            cid = coerce_combo_int_id(num_it.data(_ROLE_CUSTOMER_ID))
            if iid is None or cid is None:
                continue
            by_customer.setdefault(cid, []).append((iid, amt))
        return by_customer

    def _on_save_close(self) -> None:
        if self.sender() is not self._btn_save_close:
            return
        self._persist_payment(reset=False)

    def _on_save_new(self) -> None:
        if self.sender() is not self._btn_save_new:
            return
        self._persist_payment(reset=True)

    def _on_clear(self) -> None:
        self._reset_form()

    def _reset_form(self) -> None:
        self._suppress_apply = True
        try:
            self._customer_filter.setCurrentIndex(0)
            self._pay_amount.setValue(0.0)
            self._pay_date.setDate(QDate.currentDate())
            self._check_num.clear()
            self._memo_edit.clear()
            self._set_pay_method(_METHOD_CHECK)
            self._btn_method_check.setChecked(True)
            self._btn_auto_apply.setChecked(True)
        finally:
            self._suppress_apply = False
        self._rebuild_table()
        self._refresh_totals()

    def _on_post_payment(self) -> bool:
        """Persist the current payment (used by Save buttons and tests)."""
        return self._persist_payment(reset=False)

    def _persist_payment(self, *, reset: bool) -> bool:
        if self._ap_conn is None:
            message_box_information_ok(
                self,
                "Receive Payments",
                "Open a company database to post payments.",
                ok_tip="Close; use File → Open company… then try again.",
            )
            return False
        cid_header = self._selected_customer_id()
        if cid_header is None:
            message_box_warning_ok(
                self,
                "Receive Payments",
                "Select a customer or job in Received From.",
                ok_tip="Choose Received From, then try again.",
            )
            return False
        payment_date = self._pay_date.date().toString("yyyy-MM-dd")
        ref = self._check_num.text().strip()
        method = (self._pay_method or _METHOD_CHECK).strip()
        memo = self._memo_edit.text().strip()
        by_customer = self._collect_allocations()
        if not by_customer:
            message_box_warning_ok(
                self,
                "Receive Payments",
                "Select at least one invoice and enter an amount to apply.",
                ok_tip="Check a row or enter a payment amount, then try again.",
            )
            return False

        conn = self._ap_conn
        for cid, allocs in by_customer.items():
            for iid, amt in allocs:
                row = conn.execute(
                    "SELECT balance_due FROM invoices WHERE id = ?", (iid,)
                ).fetchone()
                if row is None:
                    message_box_warning_ok(
                        self,
                        "Receive Payments",
                        f"Invoice #{iid} is no longer in the database. Refresh and try again.",
                        ok_tip="Reload the customer, then re-enter amounts.",
                    )
                    return False
                bal = float(row["balance_due"] or 0.0)
                if amt > bal + 0.02:
                    message_box_warning_ok(
                        self,
                        "Receive Payments",
                        f"Apply amount for invoice #{iid} exceeds open balance ({bal:,.2f}).",
                        ok_tip="Lower the amount or refresh the list.",
                    )
                    return False

        posted = 0
        posted_invoice_ids: list[int] = []
        self._last_ar_payment_ids.clear()

        for cid, allocs in sorted(by_customer.items()):
            total = round(sum(a for _, a in allocs), 2)
            if total <= 0.005:
                continue
            crow = conn.execute(
                "SELECT name FROM customers WHERE id = ?", (cid,)
            ).fetchone()
            cname = (crow["name"] if crow else "").strip() or f"Customer #{cid}"
            try:
                pid = business.record_ar_payment(
                    conn,
                    cid,
                    payment_date,
                    total,
                    allocs,
                    bank_account_id=None,
                    method=method,
                    reference=ref,
                    memo=memo,
                )
                self._last_ar_payment_ids.append(int(pid))
            except (sqlite3.Error, ValueError, TypeError) as exc:
                message_box_critical_ok(
                    self,
                    "Receive Payments",
                    f"Could not record payment for {cname}: {exc}",
                    ok_tip="Close; check amounts and try again.",
                )
                return False
            posted += 1
            posted_invoice_ids.extend(iid for iid, _amt in allocs)

        self._load_invoices_from_db()
        self._sync_ar_toolbar()

        if posted:
            uniq = sorted(set(posted_invoice_ids))
            if uniq:
                self.arPaymentPosted.emit(uniq)

        message_box_information_ok(
            self,
            "Receive Payments",
            f"Posted {posted} payment(s) to Undeposited Funds. "
            "Open balances were updated. Use Make Deposits to put them in the bank.",
            ok_tip="Close; the invoices list refreshed.",
        )
        if reset:
            self._reset_form()
        return True

    def _on_export_last_ar_payment_pdf(self) -> None:
        if self._ap_conn is None or not self._last_ar_payment_ids:
            return
        pid = self._last_ar_payment_ids[-1]
        default_name = f"AR-Payment-{pid}.pdf"
        path, _filt = QFileDialog.getSaveFileName(
            self,
            "Export AR payment as PDF",
            default_name,
            "PDF files (*.pdf);;All files (*.*)",
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path = f"{path}.pdf"
        try:
            save_ar_payment_pdf(self._ap_conn, pid, path)
        except OSError as exc:
            message_box_warning_ok(
                self,
                "Receive Payments",
                f"Could not write PDF: {exc}",
                ok_tip="Choose a writable folder and try again.",
            )
        except Exception as exc:  # noqa: BLE001
            message_box_warning_ok(
                self,
                "Receive Payments",
                f"PDF export failed: {exc}",
                ok_tip="Close and try again.",
            )

    def _on_print_last_ar_payment(self) -> None:
        if self._ap_conn is None or not self._last_ar_payment_ids:
            return
        pid = self._last_ar_payment_ids[-1]
        doc = QTextDocument()
        try:
            doc.setHtml(ar_payment_html_string(self._ap_conn, pid))
        except Exception as ext:  # noqa: BLE001
            message_box_warning_ok(
                self,
                "Receive Payments",
                f"Could not prepare payment for printing: {ext}",
                ok_tip="Close and try again.",
            )
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        if not configure_printer_for_payment_print(self, printer):
            return
        doc.print_(printer)
