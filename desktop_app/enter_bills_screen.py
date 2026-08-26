"""Enter Bills — QuickBooks Desktop-style vendor bill form.

Header, Expenses/Items grid, and ribbon chrome follow Johnny's QB Pro Enter Bills
screenshots (slightly cleaner spacing/buttons than a gray Win32 photocopy). Persist
path is unchanged: ``bills`` / ``bill_expense_lines``, plus Save PDF / Print / Export PDF.

**Print / PDF:** ``Save && Close`` / ``Save && New`` write ``Bill-<ref>.pdf`` to the folder from
**Edit → Preferences** (``bill_prefs/output_folder`` in ``QSettings``, first-time folder picker
via :func:`desktop_app.invoice_preferences.ensure_bill_output_folder`).
**Export PDF…** uses a Save file dialog; **Print** uses the same HTML as PDF and
:func:`desktop_app.invoice_preferences.configure_printer_for_bill_print`.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from typing import Optional

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QShowEvent, QTextDocument
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
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from desktop_app.bill_pdf import bill_html_string, save_bill_pdf
from desktop_app.flexible_date import configure_qdate_edit_us, parse_flexible_date_to_ymd
from desktop_app.invoice_preferences import (
    configure_printer_for_bill_print,
    ensure_bill_output_folder,
)
from desktop_app.qt_mnemonic import escape_ampersand_for_qt, message_box_information_ok
from desktop_app.theme import DISABLED_FG
from probooksai import business

_LOG = logging.getLogger(__name__)

# Match Create Invoices chrome (PR 97): light canvas, cleaner blue primary — not QBO, not a gray photocopy.
_BILL_CANVAS = "#E8ECF1"
_BILL_PAPER = "#E4EEF8"  # pale blue "Bill" form like QB Enter Bills
_BILL_PANEL = "#F4F7FA"
_BILL_STRIPE = "#D0E6F4"
_BILL_CAPTION = "#4A5560"
_BILL_GRID = "#C0C8D0"
_BILL_HEADER = "#D8DEE6"
_BILL_TEXT = "#1A1A1A"
_BILL_ACCENT = "#2563A8"
_BILL_TITLE = "#5B6770"
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
_N_EXPENSE_ROWS = 20
_N_ITEM_ROWS = 20
_LINE_ROW_HEIGHT_PX = 22
_RIBBON_BTN_HEIGHT_PX = 24
_SIDE_CAPTION_W = 86
_ACCOUNT_PLACEHOLDER = "(select account)"
_ITEM_PLACEHOLDER = "(select item)"


def _safe_bill_pdf_stem(vendor_invoice_number: str, bill_id: int) -> str:
    raw = (vendor_invoice_number or "").strip()
    if not raw:
        raw = f"bill-{bill_id}"
    forbidden = '<>:"/\\|?*\x00'
    cleaned = "".join(ch if ch not in forbidden and ord(ch) >= 32 else "_" for ch in raw)
    cleaned = cleaned.strip(" .") or f"bill-{bill_id}"
    return cleaned[:120]


def _format_vendor_address_row(row: dict) -> str:
    """Build a multi-line address block from a ``vendors`` row."""
    lines: list[str] = []
    addr = (row.get("address") or "").strip()
    if addr:
        lines.append(addr)
    email = (row.get("email") or "").strip()
    if email:
        lines.append(email)
    phone = (row.get("phone") or "").strip()
    if phone:
        lines.append(phone)
    return "\n".join(lines)


def _action_button_qss(*, primary: bool = False) -> str:
    r = _TOP_STRIP_RADIUS_PX
    if primary:
        return (
            f"QPushButton {{ background-color: {_BILL_ACCENT}; border: 1px solid {_BILL_ACCENT}; "
            f"border-radius: {r}px; color: #FFFFFF; "
            f"font-size: {_TOP_STRIP_BODY_FONT_PX}px; padding: 0 14px; font-weight: 600; }}"
            f"QPushButton:hover {{ background-color: #1D4F8C; border: 1px solid #1D4F8C; }}"
            f"QPushButton:pressed {{ background-color: #163E6E; }}"
            f"QPushButton:disabled {{ color: #D7E3F0; background-color: #8AA7C7; "
            f"border: 1px solid #8AA7C7; }}"
        )
    return (
        f"QPushButton {{ background-color: {WORKFLOW_CONTROL_FACE}; border: 1px solid {_STRIP_BTN_OUTLINE}; "
        f"border-radius: {r}px; color: {_BILL_TEXT}; "
        f"font-size: {_TOP_STRIP_BODY_FONT_PX}px; padding: 0 12px; }}"
        f"QPushButton:hover {{ background-color: {WORKFLOW_CONTROL_HOVER}; }}"
        f"QPushButton:pressed {{ background-color: {WORKFLOW_CONTROL_PRESSED}; }}"
        f"QPushButton:disabled {{ color: {DISABLED_FG}; background-color: {WORKFLOW_CONTROL_FACE}; }}"
    )


def _input_qss(widget: str = "QLineEdit") -> str:
    return (
        f"{widget} {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_BILL_GRID}; "
        f"padding: 2px 6px; color: {_BILL_TEXT}; font-size: {_TOP_STRIP_BODY_FONT_PX}px; }}"
    )


def _zebra_cell_qss(widget: str, row: int) -> str:
    """Transparent-border editors so QB white / light-blue row stripes stay visible."""
    bg = _BILL_STRIPE if row % 2 else WORKFLOW_INPUT_BG
    return (
        f"{widget} {{ background-color: {bg}; border: none; "
        f"padding: 1px 4px; color: {_BILL_TEXT}; font-size: {_TOP_STRIP_BODY_FONT_PX}px; }}"
        f"{widget}:focus {{ background-color: {WORKFLOW_INPUT_BG}; }}"
    )


def _money_spin(*, prefix: str = "", row: int | None = None) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(0.0, 999_999_999.99)
    s.setDecimals(2)
    if prefix:
        s.setPrefix(prefix)
    s.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
    s.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    if row is None:
        s.setStyleSheet(_input_qss("QDoubleSpinBox"))
    else:
        s.setStyleSheet(_zebra_cell_qss("QDoubleSpinBox", row))
    return s


def _qty_spin(*, row: int = 0) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(0.0, 999_999.99)
    s.setDecimals(2)
    s.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
    s.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    s.setStyleSheet(_zebra_cell_qss("QDoubleSpinBox", row))
    return s


def _cell_line(*, row: int = 0) -> QLineEdit:
    le = QLineEdit()
    le.setStyleSheet(_zebra_cell_qss("QLineEdit", row))
    return le


def _combo_text(cb: QComboBox, *, placeholders: tuple[str, ...] = ()) -> str:
    raw = (cb.currentText() or "").strip()
    if raw in placeholders:
        return ""
    return raw


def _set_combo_text(cb: QComboBox, text: str) -> None:
    t = (text or "").strip()
    if not t:
        cb.setCurrentIndex(0)
        return
    idx = cb.findText(t, Qt.MatchFlag.MatchFixedString)
    if idx < 0:
        cb.addItem(escape_ampersand_for_qt(t), t)
        idx = cb.count() - 1
    cb.setCurrentIndex(idx)


class EnterBillsScreen(QWidget):
    """QB Pro Enter Bills: vendor header, Expenses/Items, persist to ``bills`` / ``bill_expense_lines``."""

    payBillsRequested = Signal()

    _EXPENSE_COLS = ("ACCOUNT", "AMOUNT", "MEMO", "CUSTOMER:JOB", "BILLABLE?")
    _ITEM_COLS = (
        "ITEM",
        "DESCRIPTION",
        "QTY",
        "COST",
        "AMOUNT",
        "CUSTOMER:JOB",
        "BILLABLE?",
    )
    _N_EXPENSE_ROWS = _N_EXPENSE_ROWS
    _LINE_COLS = _EXPENSE_COLS  # tests / callers that inspect the expenses grid

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        ap_conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        super().__init__(parent)
        self._ap_conn = ap_conn
        self._current_bill_id: int | None = None
        self._attachment_path: str = ""
        self._suppress_line_recalc: bool = False
        self._suppress_header_autofill: bool = False
        self._bill_print_dialog_armed: bool = False
        self._coa_labels: list[str] = []
        self._item_codes: list[str] = []
        self._amount_spins: list[QDoubleSpinBox] = []
        self._expense_billable: list[QCheckBox] = []
        self._item_qty_spins: list[QDoubleSpinBox] = []
        self._item_cost_spins: list[QDoubleSpinBox] = []
        self._item_amount_spins: list[QDoubleSpinBox] = []
        self._item_billable: list[QCheckBox] = []
        self.setWindowTitle("Enter Bills")
        self.setToolTip(
            "Enter Bills: vendor bill header and expense lines; Save writes to your company file. "
            "Same company .db (File → Backup / Restore, probooks.backup)."
        )
        self._reload_lookups()
        self._build_ui()
        self._populate_vendor_combo()
        self._update_save_enabled()

    def _reload_lookups(self) -> None:
        self._coa_labels = self._load_coa_labels()
        self._item_codes = self._load_item_codes()

    def _load_coa_labels(self) -> list[str]:
        if self._ap_conn is None:
            return []
        try:
            rows = self._ap_conn.execute(
                "SELECT account_number, account_name FROM coa_accounts "
                "WHERE COALESCE(is_active, 1) = 1 ORDER BY account_number"
            ).fetchall()
        except sqlite3.Error:
            return []
        out: list[str] = []
        for row in rows:
            d = dict(row)
            num = str(d.get("account_number") or "").strip()
            nam = str(d.get("account_name") or "").strip()
            if num and nam:
                out.append(f"{num} – {nam}")
            elif nam or num:
                out.append(nam or num)
        return out

    def _load_item_codes(self) -> list[str]:
        if self._ap_conn is None:
            return []
        try:
            return list(business.list_invoice_item_code_strings(self._ap_conn))
        except sqlite3.Error:
            return []

    def _style_button(self, b: QPushButton, *, primary: bool = False, height: int = _RIBBON_BTN_HEIGHT_PX) -> None:
        b.setStyleSheet(_action_button_qss(primary=primary))
        b.setFixedHeight(height)
        b.setAutoDefault(False)
        b.setDefault(False)

    def _caption(self, text: str) -> QLabel:
        cap = QLabel(text)
        cap.setStyleSheet(
            f"color: {_BILL_CAPTION}; font-size: {_TOP_STRIP_CAPTION_FONT_PX}px; "
            "font-weight: bold; letter-spacing: 0.04em; background: transparent;"
        )
        return cap

    def _hfield(self, caption: str, editor: QWidget, *, cap_w: int = _SIDE_CAPTION_W) -> QWidget:
        """QB-style: caption to the left of the control (compact, not stacked)."""
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        cap = self._caption(caption)
        cap.setFixedWidth(cap_w)
        cap.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if isinstance(editor, (QLineEdit, QDateEdit, QComboBox, QDoubleSpinBox)):
            editor.setFixedHeight(_FIELD_HEIGHT_PX)
        if isinstance(editor, (QLineEdit, QComboBox, QDoubleSpinBox)):
            editor.setStyleSheet(_input_qss(editor.metaObject().className()))
        elif isinstance(editor, QDateEdit):
            editor.setStyleSheet(_input_qss("QDateEdit"))
        lay.addWidget(cap)
        lay.addWidget(editor, 1)
        return wrap

    def _make_account_combo(self, *, row: int = 0) -> QComboBox:
        cb = QComboBox()
        cb.setEditable(True)
        cb.addItem(_ACCOUNT_PLACEHOLDER, "")
        for label in self._coa_labels:
            cb.addItem(escape_ampersand_for_qt(label), label)
        cb.setStyleSheet(_zebra_cell_qss("QComboBox", row))
        cb.setToolTip("Expense account for this line (chart of accounts when a company file is open).")
        return cb

    def _make_item_combo(self, *, row: int = 0) -> QComboBox:
        cb = QComboBox()
        cb.setEditable(True)
        cb.addItem(_ITEM_PLACEHOLDER, "")
        for code in self._item_codes:
            cb.addItem(escape_ampersand_for_qt(code), code)
        cb.setStyleSheet(_zebra_cell_qss("QComboBox", row))
        cb.setToolTip("Item / service code (from Codes when a company file is open).")
        return cb

    def _make_billable_check(self) -> QCheckBox:
        cb = QCheckBox()
        cb.setToolTip("Mark this line billable to a customer:job.")
        cb.setStyleSheet("QCheckBox { background: transparent; }")
        return cb

    def _table_qss(self, object_name: str) -> str:
        return (
            f"QTableWidget#{object_name} {{"
            f" background-color: {WORKFLOW_INPUT_BG};"
            f" alternate-background-color: {_BILL_STRIPE};"
            f" color: {_BILL_TEXT};"
            f" gridline-color: {_BILL_GRID};"
            f" border: 1px solid {_BILL_GRID};"
            " }"
            f"QHeaderView::section {{"
            f" background-color: {_BILL_HEADER};"
            f" color: {_BILL_CAPTION};"
            f" padding: 4px; border: 1px solid {_BILL_GRID};"
            " font-weight: bold; font-size: 11px;"
            " }"
        )

    def _build_ui(self) -> None:
        self.setStyleSheet(f"EnterBillsScreen {{ background: {_BILL_CANVAS}; }}")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 4, 6, 4)
        outer.setSpacing(4)

        self._build_ribbon(outer)
        self._build_type_row(outer)
        self._build_header_form(outer)
        self._build_line_tabs(outer)
        self._build_footer_actions(outer)

    def _build_ribbon(self, play: QVBoxLayout) -> None:
        self._bill_ribbon = QTabWidget()
        self._bill_ribbon.setObjectName("enterBillsRibbonTabs")
        self._bill_ribbon.setDocumentMode(True)
        self._bill_ribbon.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._bill_ribbon.setStyleSheet(
            f"QTabWidget#enterBillsRibbonTabs::pane {{ border: 1px solid {_BILL_GRID}; "
            f"background: {_BILL_PANEL}; top: -1px; }}"
            f"QTabWidget#enterBillsRibbonTabs QTabBar::tab {{ padding: 2px 10px; min-height: 16px; }}"
        )

        main_rib = QWidget()
        main_lay = QHBoxLayout(main_rib)
        main_lay.setContentsMargins(4, 2, 4, 2)
        main_lay.setSpacing(4)

        self._btn_find = QPushButton("Find")
        self._btn_find.setToolTip("Open the previous saved bill (QuickBooks Find / Previous on this form).")
        self._btn_new_bill = QPushButton("New")
        self._btn_new_bill.setToolTip("Start a blank bill (does not save the current form).")
        self._btn_ribbon_save = QPushButton("Save")
        self._btn_ribbon_save.setToolTip(
            "Save this bill to the company file and keep it open (QuickBooks ribbon Save)."
        )
        self._btn_print = QPushButton("Print")
        self._btn_print.setToolTip(
            "Save this bill to the company file, then print (same layout as PDF)."
        )
        self._btn_export_pdf = QPushButton("Export PDF…")
        self._btn_export_pdf.setToolTip(
            "Save this bill to the company file, then pick a .pdf path "
            "(does not change the bills folder in preferences)."
        )
        self._btn_attach = QPushButton("Attach File")
        self._btn_attach.setToolTip("Attach a file path stored with this bill.")
        self._btn_clear_splits = QPushButton("Clear Splits")
        self._btn_clear_splits.setToolTip("Clear Expenses and Items lines without changing the header.")
        self._btn_recalc = QPushButton("Recalculate")
        self._btn_recalc.setToolTip("Set Amount Due from Expenses + Items.")
        self._btn_pay_bill = QPushButton("Pay Bill")
        self._btn_pay_bill.setToolTip("Open the Pay Bills tab.")

        for b in (
            self._btn_find,
            self._btn_new_bill,
            self._btn_ribbon_save,
            self._btn_print,
            self._btn_export_pdf,
            self._btn_attach,
            self._btn_clear_splits,
            self._btn_recalc,
            self._btn_pay_bill,
        ):
            self._style_button(b)
            main_lay.addWidget(b)
        main_lay.addStretch(1)
        self._bill_ribbon.addTab(main_rib, "Main")

        later = QWidget()
        later_lay = QHBoxLayout(later)
        later_lay.setContentsMargins(8, 4, 8, 4)
        later_lbl = QLabel("Bill reports follow later QuickBooks screens.")
        later_lbl.setStyleSheet(f"color: {_BILL_CAPTION}; font-size: 11px; background: transparent;")
        later_lay.addWidget(later_lbl)
        self._bill_ribbon.addTab(later, "Reports")
        play.addWidget(self._bill_ribbon)

        _uc = Qt.ConnectionType.UniqueConnection
        self._btn_find.clicked.connect(self._on_find_bill, _uc)
        self._btn_new_bill.clicked.connect(self._on_clear, _uc)
        self._btn_ribbon_save.clicked.connect(self._on_ribbon_save, _uc)
        self._btn_print.clicked.connect(self._on_print_bill, _uc)
        self._btn_export_pdf.clicked.connect(self._on_export_bill_pdf, _uc)
        self._btn_attach.clicked.connect(self._on_attach_file, _uc)
        self._btn_clear_splits.clicked.connect(self._on_clear_splits, _uc)
        self._btn_recalc.clicked.connect(self._on_recalculate, _uc)
        self._btn_pay_bill.clicked.connect(self._on_pay_bill, _uc)

    def _build_type_row(self, play: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setContentsMargins(2, 0, 2, 0)
        row.setSpacing(12)
        self._radio_bill = QRadioButton("Bill")
        self._radio_credit = QRadioButton("Credit")
        self._radio_bill.setObjectName("enterBillsTypeBill")
        self._radio_credit.setObjectName("enterBillsTypeCredit")
        self._radio_bill.setChecked(True)
        self._type_group = QButtonGroup(self)
        self._type_group.addButton(self._radio_bill, 0)
        self._type_group.addButton(self._radio_credit, 1)
        radio_qss = (
            f"QRadioButton {{ color: {_BILL_TEXT}; background: transparent; "
            f"font-size: 12px; }}"
        )
        self._radio_bill.setStyleSheet(radio_qss)
        self._radio_credit.setStyleSheet(radio_qss)
        self._radio_bill.setToolTip("Vendor bill (increases accounts payable).")
        self._radio_credit.setToolTip(
            "Vendor credit layout (same save path as a bill for now — AP still uses bills)."
        )
        self._chk_received = QCheckBox("Bill Received")
        self._chk_received.setObjectName("enterBillsReceived")
        self._chk_received.setChecked(True)
        self._chk_received.setStyleSheet(
            f"QCheckBox {{ color: {_BILL_TEXT}; background: transparent; font-size: 12px; }}"
        )
        self._chk_received.setToolTip("QuickBooks Bill Received — the vendor invoice is in hand.")
        row.addWidget(self._radio_bill)
        row.addWidget(self._radio_credit)
        row.addSpacing(8)
        row.addWidget(self._chk_received)
        row.addStretch(1)
        play.addLayout(row)
        self._radio_bill.toggled.connect(self._on_doc_kind_changed)

    def _build_header_form(self, play: QVBoxLayout) -> None:
        form = QFrame()
        form.setObjectName("enterBillsHeaderBand")
        form.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        form.setStyleSheet(
            f"QFrame#enterBillsHeaderBand {{ background-color: {_BILL_PAPER}; "
            f"border: 1px solid #B7C9DE; border-radius: 6px; }}"
        )
        hb = QVBoxLayout(form)
        hb.setContentsMargins(10, 6, 10, 8)
        hb.setSpacing(4)

        self._title = QLabel("Bill")
        self._title.setObjectName("enterBillsTitle")
        self._title.setStyleSheet(
            f"font-size: {_TITLE_FONT_PX}px; font-weight: bold; color: {_BILL_TITLE}; "
            "background: transparent;"
        )

        self._vendor = QComboBox()
        self._vendor.setObjectName("enterBillsVendor")
        self._vendor.setEditable(False)
        self._vendor.setMinimumWidth(220)
        self._vendor.setStyleSheet(_input_qss("QComboBox"))

        self._address = QPlainTextEdit()
        self._address.setObjectName("enterBillsAddress")
        self._address.setPlaceholderText("Address")
        # Compact: header must stay in the top third so the expenses grid can dominate.
        self._address.setMaximumHeight(64)
        self._address.setMinimumHeight(44)
        self._address.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self._address.setStyleSheet(
            f"QPlainTextEdit {{ background: {WORKFLOW_INPUT_BG}; color: {_BILL_TEXT}; "
            f"border: 1px solid {_BILL_GRID}; border-radius: 3px; padding: 2px 4px; }}"
        )

        self._bill_date = QDateEdit()
        configure_qdate_edit_us(self._bill_date)
        self._bill_date.setDate(QDate.currentDate())
        self._bill_date.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._bill_date.setToolTip(
            "Bill date: type flexibly (e.g. 5/21/26, 05.21.26, 052126); stored as YYYY-MM-DD."
        )

        self._vendor_inv = QLineEdit()
        self._vendor_inv.setObjectName("enterBillsRefNo")
        self._vendor_inv.setPlaceholderText("Ref. No.")
        self._vendor_inv.setToolTip("Vendor invoice / reference number.")

        self._amount_due = _money_spin()
        self._amount_due.setObjectName("enterBillsAmountDue")
        self._amount_due.setToolTip(
            "Amount due. Recalculate fills this from Expenses + Items; Save uses the line total."
        )

        self._due_date = QDateEdit()
        configure_qdate_edit_us(self._due_date)
        self._due_date.setDate(QDate.currentDate())
        self._due_date.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._due_date.setToolTip(
            "Bill due date. Filled from Terms when you change Date or Terms; you can still edit it."
        )

        self._terms = QComboBox()
        self._terms.setObjectName("enterBillsTerms")
        self._terms.setEditable(False)
        self._terms.addItems(list(business.INVOICE_TERMS_CHOICES))
        self._terms.setToolTip("Payment terms. Changing terms (or the bill date) fills Bill Due.")

        self._header_memo = QLineEdit()
        self._header_memo.setObjectName("enterBillsMemo")
        self._header_memo.setPlaceholderText("Memo")

        body = QHBoxLayout()
        body.setSpacing(12)
        left = QVBoxLayout()
        left.setSpacing(4)
        left.addWidget(self._title)
        left.addWidget(self._hfield("VENDOR", self._vendor))
        addr_row = QHBoxLayout()
        addr_row.setSpacing(6)
        addr_cap = self._caption("ADDRESS")
        addr_cap.setFixedWidth(_SIDE_CAPTION_W)
        addr_cap.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        addr_row.addWidget(addr_cap)
        addr_row.addWidget(self._address, 1)
        left.addLayout(addr_row, 1)
        left.addWidget(self._hfield("TERMS", self._terms))

        right = QVBoxLayout()
        right.setSpacing(4)
        right.addWidget(self._hfield("DATE", self._bill_date, cap_w=92))
        right.addWidget(self._hfield("REF. NO.", self._vendor_inv, cap_w=92))
        right.addWidget(self._hfield("AMOUNT DUE", self._amount_due, cap_w=92))
        right.addWidget(self._hfield("BILL DUE", self._due_date, cap_w=92))
        right.addStretch(1)

        body.addLayout(left, 3)
        body.addLayout(right, 2)
        hb.addLayout(body)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        bottom.addWidget(self._hfield("MEMO", self._header_memo), 1)
        hb.addLayout(bottom)

        play.addWidget(form)

        self._vendor.currentIndexChanged.connect(self._on_vendor_changed)
        self._bill_date.dateChanged.connect(self._on_date_or_terms_changed)
        self._terms.currentIndexChanged.connect(self._on_date_or_terms_changed)

    def _build_line_tabs(self, play: QVBoxLayout) -> None:
        self._line_tabs = QTabWidget()
        self._line_tabs.setObjectName("enterBillsLineTabs")
        self._line_tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._line_tabs.setStyleSheet(
            f"QTabWidget#enterBillsLineTabs::pane {{ border: 1px solid {_BILL_GRID}; "
            f"background: {WORKFLOW_INPUT_BG}; }}"
            f"QTabWidget#enterBillsLineTabs QTabBar::tab {{ background: {_BILL_HEADER}; color: {_BILL_CAPTION}; "
            "padding: 4px 14px; border: 1px solid #C8C8C8; border-bottom: none; margin-right: 2px; }"
            f"QTabWidget#enterBillsLineTabs QTabBar::tab:selected {{ background: {WORKFLOW_INPUT_BG}; "
            f"color: #1A5276; font-weight: bold; border-bottom: 2px solid {_BILL_ACCENT}; }}"
        )
        self._table = QTableWidget(self._N_EXPENSE_ROWS, len(self._EXPENSE_COLS))
        self._table.setObjectName("enterBillsExpensesTable")
        self._table.setHorizontalHeaderLabels(self._EXPENSE_COLS)
        self._configure_grid(self._table)
        self._table.setStyleSheet(self._table_qss("enterBillsExpensesTable"))
        self._fill_expense_rows()
        self._line_tabs.addTab(self._table, "Expenses  $0.00")

        self._items_table = QTableWidget(_N_ITEM_ROWS, len(self._ITEM_COLS))
        self._items_table.setObjectName("enterBillsItemsTable")
        self._items_table.setHorizontalHeaderLabels(self._ITEM_COLS)
        self._configure_grid(self._items_table)
        self._items_table.setStyleSheet(self._table_qss("enterBillsItemsTable"))
        self._fill_item_rows()
        self._line_tabs.addTab(self._items_table, "Items  $0.00")
        play.addWidget(self._line_tabs, 1)

    def _configure_grid(self, table: QTableWidget) -> None:
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(_LINE_ROW_HEIGHT_PX)
        table.verticalHeader().setMinimumSectionSize(18)
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        table.setAlternatingRowColors(True)
        table.setShowGrid(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        hdr = table.horizontalHeader()
        hdr.setStretchLastSection(False)
        last = table.columnCount() - 1
        for col in range(table.columnCount()):
            if col == last:
                hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            elif col in (1, 2, 3, 4) and table is getattr(self, "_items_table", None):
                hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
            elif col == 1 and table is getattr(self, "_table", None):
                hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            else:
                hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        if table is getattr(self, "_table", None):
            table.setColumnWidth(1, 110)
            table.setColumnWidth(last, 78)
        else:
            table.setColumnWidth(last, 78)
        for r in range(table.rowCount()):
            table.setRowHeight(r, _LINE_ROW_HEIGHT_PX)

    def _fill_expense_rows(self) -> None:
        self._amount_spins = []
        self._expense_billable = []
        for row in range(self._N_EXPENSE_ROWS):
            acct = self._make_account_combo(row=row)
            self._table.setCellWidget(row, 0, acct)
            amt = _money_spin(prefix="$ ", row=row)
            amt.setValue(0.0)
            amt.valueChanged.connect(self._on_line_amount_changed)
            self._table.setCellWidget(row, 1, amt)
            self._amount_spins.append(amt)
            memo = _cell_line(row=row)
            memo.setPlaceholderText("Memo")
            memo.textChanged.connect(lambda _t: self._on_line_amount_changed(0.0))
            self._table.setCellWidget(row, 2, memo)
            job = _cell_line(row=row)
            job.setPlaceholderText("Customer:Job")
            self._table.setCellWidget(row, 3, job)
            billable = self._make_billable_check()
            self._table.setCellWidget(row, 4, billable)
            self._expense_billable.append(billable)

    def _fill_item_rows(self) -> None:
        self._item_qty_spins = []
        self._item_cost_spins = []
        self._item_amount_spins = []
        self._item_billable = []
        for row in range(_N_ITEM_ROWS):
            self._items_table.setCellWidget(row, 0, self._make_item_combo(row=row))
            desc = _cell_line(row=row)
            desc.setPlaceholderText("Description")
            self._items_table.setCellWidget(row, 1, desc)
            qty = _qty_spin(row=row)
            cost = _money_spin(prefix="$ ", row=row)
            amt = _money_spin(prefix="$ ", row=row)
            qty.valueChanged.connect(lambda _v, r=row: self._on_item_qty_cost_changed(r))
            cost.valueChanged.connect(lambda _v, r=row: self._on_item_qty_cost_changed(r))
            amt.valueChanged.connect(self._on_line_amount_changed)
            self._items_table.setCellWidget(row, 2, qty)
            self._items_table.setCellWidget(row, 3, cost)
            self._items_table.setCellWidget(row, 4, amt)
            self._item_qty_spins.append(qty)
            self._item_cost_spins.append(cost)
            self._item_amount_spins.append(amt)
            job = _cell_line(row=row)
            job.setPlaceholderText("Customer:Job")
            self._items_table.setCellWidget(row, 5, job)
            billable = self._make_billable_check()
            self._items_table.setCellWidget(row, 6, billable)
            self._item_billable.append(billable)

    def _build_footer_actions(self, play: QVBoxLayout) -> None:
        actions = QFrame()
        actions.setObjectName("enterBillsActionsBar")
        actions.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        actions.setStyleSheet(
            f"QFrame#enterBillsActionsBar {{ background-color: {_BILL_PANEL}; "
            f"border: 1px solid {_BILL_GRID}; border-radius: 4px; }}"
        )
        bot = QHBoxLayout(actions)
        bot.setContentsMargins(8, 4, 8, 4)
        self._lbl_bill_total = QLabel("Total: $0.00")
        self._lbl_bill_total.setObjectName("enterBillsTotalLabel")
        self._lbl_bill_total.hide()
        bot.addStretch(1)
        self._btn_save_close = QPushButton("Save && Close")
        self._btn_save_new = QPushButton("Save && New")
        self._btn_clear = QPushButton("Clear")
        self._btn_save_close.setToolTip(
            "Save this bill to the company file and keep it on the form "
            "(tab analog of QuickBooks Save & Close)."
        )
        self._btn_save_new.setToolTip(
            "Save this bill to the company file, then clear the form for a new bill."
        )
        self._btn_clear.setToolTip("Clear the form without saving (new draft).")
        self._style_button(self._btn_save_close, height=28)
        self._style_button(self._btn_save_new, primary=True, height=28)
        self._style_button(self._btn_clear, height=28)
        bot.addWidget(self._btn_save_close)
        bot.addWidget(self._btn_save_new)
        bot.addWidget(self._btn_clear)
        play.addWidget(actions)

        _uc = Qt.ConnectionType.UniqueConnection
        self._btn_save_close.clicked.connect(self._on_save_close, _uc)
        self._btn_save_new.clicked.connect(self._on_save_new, _uc)
        self._btn_clear.clicked.connect(self._on_clear, _uc)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._update_save_enabled()

    def _update_save_enabled(self) -> None:
        on = self._ap_conn is not None
        for b in (
            self._btn_save_close,
            self._btn_save_new,
            self._btn_export_pdf,
            self._btn_print,
            self._btn_ribbon_save,
            self._btn_attach,
            self._btn_pay_bill,
            self._btn_find,
        ):
            b.setEnabled(on)
        self._btn_new_bill.setEnabled(True)
        self._btn_clear.setEnabled(True)
        self._btn_clear_splits.setEnabled(True)
        self._btn_recalc.setEnabled(True)

    def _on_doc_kind_changed(self, _checked: bool = False) -> None:
        if self._radio_credit.isChecked():
            self._title.setText("Credit")
        else:
            self._title.setText("Bill")

    def _on_date_or_terms_changed(self, *_args) -> None:
        if self._suppress_header_autofill:
            return
        qd = self._bill_date.date()
        iso = f"{qd.year():04d}-{qd.month():02d}-{qd.day():02d}"
        due_iso = business.due_date_iso_from_terms(iso, self._terms.currentText())
        ymd = parse_flexible_date_to_ymd(due_iso)
        if ymd:
            y, m, d = ymd
            self._due_date.blockSignals(True)
            self._due_date.setDate(QDate(y, m, d))
            self._due_date.blockSignals(False)

    def _on_item_qty_cost_changed(self, row: int) -> None:
        if self._suppress_line_recalc:
            return
        if 0 <= row < len(self._item_qty_spins):
            qty = float(self._item_qty_spins[row].value())
            cost = float(self._item_cost_spins[row].value())
            self._item_amount_spins[row].blockSignals(True)
            self._item_amount_spins[row].setValue(round(qty * cost, 2))
            self._item_amount_spins[row].blockSignals(False)
        self._on_line_amount_changed(0.0)

    def prefill_from_document(self, data: dict) -> None:
        """Pre-fill header fields from AI-extracted document data (skips blank values)."""
        self._suppress_header_autofill = True
        try:
            ref = (data.get("invoice_number") or "").strip()
            if ref:
                self._vendor_inv.setText(ref)
            iso_date = (data.get("doc_date") or "").strip()
            if iso_date:
                ymd = parse_flexible_date_to_ymd(iso_date)
                if ymd:
                    y, m, d = ymd
                    self._bill_date.setDate(QDate(y, m, d))
            iso_due = (data.get("due_date") or "").strip()
            if iso_due:
                ymd = parse_flexible_date_to_ymd(iso_due)
                if ymd:
                    y, m, d = ymd
                    self._due_date.setDate(QDate(y, m, d))
            memo = (data.get("notes") or "").strip()
            if memo:
                self._header_memo.setText(memo)
        finally:
            self._suppress_header_autofill = False

    def _feedback(self, msg: str) -> None:
        if not (msg or "").strip():
            return
        _LOG.info("Enter Bills: %s", msg.strip())
        w: QWidget | None = self
        while w is not None:
            if isinstance(w, QMainWindow):
                sb = w.statusBar()
                if sb is not None:
                    sb.showMessage(msg.strip(), 8000)
                    return
            w = w.parentWidget()

    def _populate_vendor_combo(self) -> None:
        self._vendor.blockSignals(True)
        self._vendor.clear()
        self._vendor.addItem("", None)
        if self._ap_conn is not None:
            try:
                for row in business.list_vendors(self._ap_conn):
                    d = dict(row)
                    vid = int(d["id"])
                    name = (d.get("name") or "").strip()
                    self._vendor.addItem(escape_ampersand_for_qt(name or f"Vendor #{vid}"), vid)
            except (sqlite3.Error, KeyError, TypeError, ValueError):
                pass
        self._vendor.blockSignals(False)
        self._on_vendor_changed(self._vendor.currentIndex())
        self._update_save_enabled()

    def refresh_vendors(self) -> None:
        """Reload vendor names from the company connection (e.g. after Business hub edits)."""
        self._populate_vendor_combo()

    def refresh_lookups(self) -> None:
        """Reload COA / item lists (e.g. after the chart of accounts changes)."""
        self._reload_lookups()
        current_accts = [
            _combo_text(self._table.cellWidget(r, 0), placeholders=(_ACCOUNT_PLACEHOLDER,))
            if isinstance(self._table.cellWidget(r, 0), QComboBox)
            else ""
            for r in range(self._N_EXPENSE_ROWS)
        ]
        for r in range(self._N_EXPENSE_ROWS):
            w = self._table.cellWidget(r, 0)
            if not isinstance(w, QComboBox):
                continue
            w.blockSignals(True)
            w.clear()
            w.addItem(_ACCOUNT_PLACEHOLDER, "")
            for label in self._coa_labels:
                w.addItem(escape_ampersand_for_qt(label), label)
            _set_combo_text(w, current_accts[r])
            w.blockSignals(False)

    def open_bill_by_id(self, bill_id: int) -> bool:
        """Load a bill into this tab (bank register / in-app navigation)."""
        if self._ap_conn is None:
            message_box_information_ok(
                self,
                "Bill",
                "Open a company file to edit bills.",
                ok_tip="Close; use File → Open company… then try the link again.",
            )
            return False
        bid = int(bill_id)
        b, _lines = business.get_bill_detail(self._ap_conn, bid)
        if b is None:
            message_box_information_ok(
                self,
                "Bill",
                f"Bill #{bid} was not found.",
                ok_tip="Close; refresh the register or company data and try again.",
            )
            return False
        self.refresh_vendors()
        self._load_bill_into_form(bid)
        return True

    def open_bill_by_vendor_invoice_number(
        self,
        vendor_invoice_number: str,
        *,
        vendor_id: int | None = None,
    ) -> bool:
        """Load a bill by ``bills.vendor_invoice_number`` (optional *vendor_id* disambiguates)."""
        if self._ap_conn is None:
            message_box_information_ok(
                self,
                "Bill",
                "Open a company file to edit bills.",
                ok_tip="Close; use File → Open company… then try again.",
            )
            return False
        bid = business.get_bill_id_by_vendor_invoice_number(
            self._ap_conn,
            vendor_invoice_number,
            vendor_id=vendor_id,
        )
        if bid is None:
            ref = (vendor_invoice_number or "").strip()
            message_box_information_ok(
                self,
                "Bill",
                f"No unique bill with vendor invoice / reference {ref!r} was found.",
                ok_tip="Close; use Enter Bills after picking the vendor, or open the bill from the Bank register link.",
            )
            return False
        return self.open_bill_by_id(bid)

    def _selected_vendor_id(self) -> int | None:
        raw = self._vendor.currentData()
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    def _select_vendor_id(self, vid: int) -> None:
        for i in range(self._vendor.count()):
            data = self._vendor.itemData(i)
            if data is not None and int(data) == int(vid):
                self._vendor.setCurrentIndex(i)
                return

    def _on_vendor_changed(self, _index: int) -> None:
        raw = self._vendor.currentData()
        if raw is None or self._ap_conn is None:
            self._address.clear()
            return
        try:
            vid = int(raw)
        except (TypeError, ValueError):
            self._address.clear()
            return
        row = business.get_vendor(self._ap_conn, vid)
        if row is None:
            self._address.clear()
            return
        self._address.setPlainText(_format_vendor_address_row(dict(row)))

    def _on_line_amount_changed(self, _v: float) -> None:
        if self._suppress_line_recalc:
            return
        self._recalc_total_label()

    def _expense_subtotal(self) -> float:
        return round(sum(float(sp.value()) for sp in self._amount_spins), 2)

    def _item_subtotal(self) -> float:
        return round(sum(float(sp.value()) for sp in self._item_amount_spins), 2)

    def _recalc_total_label(self) -> None:
        exp = self._expense_subtotal()
        items = self._item_subtotal()
        total = round(exp + items, 2)
        self._lbl_bill_total.setText(f"Total: ${total:,.2f}")
        self._line_tabs.setTabText(0, f"Expenses  ${exp:,.2f}")
        self._line_tabs.setTabText(1, f"Items  ${items:,.2f}")
        self._amount_due.blockSignals(True)
        self._amount_due.setValue(total)
        self._amount_due.blockSignals(False)

    def _collect_expense_lines(self) -> list[dict]:
        rows: list[dict] = []
        qd = self._bill_date.date()
        bill_iso = f"{qd.year():04d}-{qd.month():02d}-{qd.day():02d}"
        for r in range(self._N_EXPENSE_ROWS):
            acct_w = self._table.cellWidget(r, 0)
            amt_w = self._table.cellWidget(r, 1)
            memo_w = self._table.cellWidget(r, 2)
            job_w = self._table.cellWidget(r, 3)
            account = (
                _combo_text(acct_w, placeholders=(_ACCOUNT_PLACEHOLDER,))
                if isinstance(acct_w, QComboBox)
                else ""
            )
            amt = float(amt_w.value()) if isinstance(amt_w, QDoubleSpinBox) else 0.0
            memo = memo_w.text().strip() if isinstance(memo_w, QLineEdit) else ""
            job = job_w.text().strip() if isinstance(job_w, QLineEdit) else ""
            if amt == 0.0 and not account and not memo and not job:
                continue
            rows.append(
                {
                    "line_date": bill_iso,
                    "ticket_ref": account,
                    "amount": amt,
                    "memo": memo,
                    "customer_job": job,
                }
            )
        for r in range(_N_ITEM_ROWS):
            item_w = self._items_table.cellWidget(r, 0)
            desc_w = self._items_table.cellWidget(r, 1)
            amt_w = self._items_table.cellWidget(r, 4)
            job_w = self._items_table.cellWidget(r, 5)
            item = (
                _combo_text(item_w, placeholders=(_ITEM_PLACEHOLDER,))
                if isinstance(item_w, QComboBox)
                else ""
            )
            desc = desc_w.text().strip() if isinstance(desc_w, QLineEdit) else ""
            amt = float(amt_w.value()) if isinstance(amt_w, QDoubleSpinBox) else 0.0
            job = job_w.text().strip() if isinstance(job_w, QLineEdit) else ""
            if amt == 0.0 and not item and not desc and not job:
                continue
            rows.append(
                {
                    "line_date": bill_iso,
                    "ticket_ref": item,
                    "amount": amt,
                    "memo": desc if desc else item,
                    "customer_job": job,
                }
            )
        return rows

    def _clear_expense_grid(self) -> None:
        self._suppress_line_recalc = True
        try:
            for r in range(self._N_EXPENSE_ROWS):
                acct = self._table.cellWidget(r, 0)
                if isinstance(acct, QComboBox):
                    acct.setCurrentIndex(0)
                amt = self._table.cellWidget(r, 1)
                if isinstance(amt, QDoubleSpinBox):
                    amt.setValue(0.0)
                memo = self._table.cellWidget(r, 2)
                if isinstance(memo, QLineEdit):
                    memo.clear()
                job = self._table.cellWidget(r, 3)
                if isinstance(job, QLineEdit):
                    job.clear()
                if r < len(self._expense_billable):
                    self._expense_billable[r].setChecked(False)
            for r in range(_N_ITEM_ROWS):
                item = self._items_table.cellWidget(r, 0)
                if isinstance(item, QComboBox):
                    item.setCurrentIndex(0)
                desc = self._items_table.cellWidget(r, 1)
                if isinstance(desc, QLineEdit):
                    desc.clear()
                if r < len(self._item_qty_spins):
                    self._item_qty_spins[r].setValue(0.0)
                    self._item_cost_spins[r].setValue(0.0)
                    self._item_amount_spins[r].setValue(0.0)
                    self._item_billable[r].setChecked(False)
                job = self._items_table.cellWidget(r, 5)
                if isinstance(job, QLineEdit):
                    job.clear()
        finally:
            self._suppress_line_recalc = False
        self._recalc_total_label()

    def _reset_form_new_draft(self) -> None:
        self._current_bill_id = None
        self._attachment_path = ""
        self._suppress_header_autofill = True
        try:
            self._radio_bill.setChecked(True)
            self._chk_received.setChecked(True)
            self._vendor.blockSignals(True)
            self._vendor.setCurrentIndex(0)
            self._vendor.blockSignals(False)
            self._address.clear()
            today = QDate.currentDate()
            self._bill_date.setDate(today)
            self._due_date.setDate(today)
            self._terms.setCurrentIndex(0)
            self._vendor_inv.clear()
            self._header_memo.clear()
            self._amount_due.setValue(0.0)
            self._title.setText("Bill")
        finally:
            self._suppress_header_autofill = False
        self._clear_expense_grid()

    def _try_persist_bill(self) -> tuple[bool, str, int | None]:
        if self._ap_conn is None:
            return False, "Open a company database to save bills.", None
        vid = self._selected_vendor_id()
        if vid is None:
            return False, "Select a vendor.", None
        qd = self._bill_date.date()
        if not qd.isValid():
            return False, "Enter a valid bill date.", None
        bill_date_iso = f"{qd.year():04d}-{qd.month():02d}-{qd.day():02d}"
        lines = self._collect_expense_lines()
        if not lines:
            due_amt = round(float(self._amount_due.value()), 2)
            if due_amt > 0:
                lines = [
                    {
                        "line_date": bill_date_iso,
                        "ticket_ref": "",
                        "amount": due_amt,
                        "memo": "",
                        "customer_job": "",
                    }
                ]
            else:
                return False, "Enter at least one expense line (amount or detail).", None
        total_sum = sum(round(float(x["amount"]), 2) for x in lines)
        if total_sum <= 0:
            return False, "Bill total must be greater than zero.", None
        due_d = self._due_date.date()
        due_iso = f"{due_d.year():04d}-{due_d.month():02d}-{due_d.day():02d}" if due_d.isValid() else ""
        memo_h = self._header_memo.text().strip()
        vinv = self._vendor_inv.text().strip()
        conn = self._ap_conn
        edit_id = self._current_bill_id
        try:
            if edit_id is not None:
                business.update_bill(
                    conn,
                    edit_id,
                    vid,
                    bill_date_iso,
                    0.0,
                    vendor_invoice_number=vinv,
                    due_date=due_iso,
                    memo=memo_h,
                    attachment_path=self._attachment_path,
                    expense_lines=lines,
                )
                return True, "", edit_id
            bid = business.create_bill(
                conn,
                vid,
                bill_date_iso,
                0.0,
                vendor_invoice_number=vinv,
                due_date=due_iso,
                memo=memo_h,
                attachment_path=self._attachment_path,
                expense_lines=lines,
            )
            return True, "", bid
        except ValueError as exc:
            return False, str(exc), None
        except sqlite3.Error as exc:
            return False, str(exc), None

    def _set_date_edit(self, w: QDateEdit, raw: str) -> None:
        s = (raw or "").strip()
        ymd = parse_flexible_date_to_ymd(s) if s else None
        if ymd:
            y, m, d = ymd
            w.setDate(QDate(y, m, d))
        else:
            w.setDate(QDate.currentDate())

    def _load_bill_into_form(self, bill_id: int) -> None:
        if self._ap_conn is None:
            return
        b, lines = business.get_bill_detail(self._ap_conn, bill_id)
        if b is None:
            return
        d = dict(b)
        self._suppress_line_recalc = True
        self._suppress_header_autofill = True
        try:
            self._current_bill_id = bill_id
            self._attachment_path = (d.get("attachment_path") or "").strip()
            iso = (d.get("bill_date") or "").strip()
            self._set_date_edit(self._bill_date, iso[:10] if len(iso) >= 10 else iso)
            self._vendor_inv.setText((d.get("vendor_invoice_number") or "").strip())
            due = (d.get("due_date") or "").strip()
            self._set_date_edit(self._due_date, due[:10] if due and len(due) >= 10 and due[4] == "-" else due)
            self._header_memo.setText((d.get("memo") or "").strip())
            self._vendor.blockSignals(True)
            self._select_vendor_id(int(d["vendor_id"]))
            self._vendor.blockSignals(False)
            self._on_vendor_changed(self._vendor.currentIndex())
            self._clear_expense_grid()
            self._suppress_line_recalc = True
            if lines:
                for i, ln in enumerate(lines):
                    if i >= self._N_EXPENSE_ROWS:
                        break
                    row = dict(ln)
                    acct_w = self._table.cellWidget(i, 0)
                    amt_w = self._table.cellWidget(i, 1)
                    memo_w = self._table.cellWidget(i, 2)
                    job_w = self._table.cellWidget(i, 3)
                    if isinstance(acct_w, QComboBox):
                        _set_combo_text(acct_w, (row.get("ticket_ref") or "").strip())
                    if isinstance(amt_w, QDoubleSpinBox):
                        amt_w.setValue(float(row.get("amount") or 0.0))
                    if isinstance(memo_w, QLineEdit):
                        memo_w.setText((row.get("memo") or "").strip())
                    if isinstance(job_w, QLineEdit):
                        job_w.setText((row.get("customer_job") or "").strip())
            else:
                amt0 = self._table.cellWidget(0, 1)
                if isinstance(amt0, QDoubleSpinBox):
                    amt0.setValue(float(d.get("total") or 0.0))
        finally:
            self._suppress_line_recalc = False
            self._suppress_header_autofill = False
        self._recalc_total_label()

    def _write_bill_pdf_to_prefs_folder(self, bill_id: int) -> None:
        if self._ap_conn is None:
            return
        folder = ensure_bill_output_folder(self)
        if folder is None:
            return
        vinv = self._vendor_inv.text().strip()
        name = f"Bill-{_safe_bill_pdf_stem(vinv, bill_id)}.pdf"
        path = os.path.join(folder, name)
        try:
            save_bill_pdf(self._ap_conn, bill_id, path)
        except OSError as exc:
            self._feedback(f"Bill saved, but the PDF could not be written: {exc}")
        except Exception as exc:  # noqa: BLE001
            self._feedback(f"Bill saved, but PDF export failed: {exc}")

    def _on_export_bill_pdf(self) -> None:
        if self.sender() is not self._btn_export_pdf:
            return
        if self._ap_conn is None:
            self._feedback("Open a company file to export a PDF.")
            return
        was_new = self._current_bill_id is None
        ok, msg, bid = self._try_persist_bill()
        if not ok:
            self._feedback(msg)
            return
        assert bid is not None
        vinv = self._vendor_inv.text().strip()
        default_name = f"Bill-{_safe_bill_pdf_stem(vinv, bid)}.pdf"
        path, _filt = QFileDialog.getSaveFileName(
            self,
            "Export bill as PDF",
            default_name,
            "PDF files (*.pdf);;All files (*.*)",
        )
        if not path:
            if was_new:
                self._load_bill_into_form(bid)
            return
        if not path.lower().endswith(".pdf"):
            path = f"{path}.pdf"
        try:
            save_bill_pdf(self._ap_conn, bid, path)
        except OSError as exc:
            self._feedback(f"Bill saved, but the PDF could not be written: {exc}")
            return
        except Exception as exc:  # noqa: BLE001
            self._feedback(f"Bill saved, but PDF export failed: {exc}")
            return
        self._feedback("Bill saved.")
        if was_new:
            self._reset_form_new_draft()
        else:
            self._load_bill_into_form(bid)

    def _run_bill_print_dialog(self, bill_id: int, *, reset_after: bool) -> None:
        if not self._bill_print_dialog_armed:
            return
        if self._ap_conn is None:
            return
        doc = QTextDocument()
        try:
            doc.setHtml(bill_html_string(self._ap_conn, bill_id))
        except Exception as exc:  # noqa: BLE001
            self._feedback(f"Could not prepare the bill for printing: {exc}")
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        if not configure_printer_for_bill_print(self, printer):
            return
        doc.print_(printer)
        self._feedback("Bill saved.")
        if reset_after:
            self._reset_form_new_draft()
        else:
            self._load_bill_into_form(bill_id)

    def _on_print_bill(self) -> None:
        if self.sender() is not self._btn_print:
            return
        if self._ap_conn is None:
            self._feedback("Open a company file to print bills.")
            return
        was_new = self._current_bill_id is None
        self._bill_print_dialog_armed = True
        try:
            ok, msg, bid = self._try_persist_bill()
            if not ok:
                self._feedback(msg)
                return
            assert bid is not None
            self._run_bill_print_dialog(bid, reset_after=was_new)
        finally:
            self._bill_print_dialog_armed = False

    def _persist_and_maybe_reset(self, *, reset: bool, stay: bool) -> None:
        ok, msg, bid = self._try_persist_bill()
        if not ok:
            self._feedback(msg)
            return
        assert bid is not None
        self._write_bill_pdf_to_prefs_folder(bid)
        self._feedback("Bill saved.")
        if reset:
            self._reset_form_new_draft()
        elif stay:
            self._load_bill_into_form(bid)

    def _on_save_close(self) -> None:
        if self.sender() is not self._btn_save_close:
            return
        self._persist_and_maybe_reset(reset=False, stay=True)

    def _on_save_new(self) -> None:
        if self.sender() is not self._btn_save_new:
            return
        self._persist_and_maybe_reset(reset=True, stay=False)

    def _on_ribbon_save(self) -> None:
        if self.sender() is not self._btn_ribbon_save:
            return
        self._persist_and_maybe_reset(reset=False, stay=True)

    def _on_clear(self) -> None:
        self._reset_form_new_draft()

    def _on_clear_splits(self) -> None:
        self._clear_expense_grid()

    def _on_recalculate(self) -> None:
        self._recalc_total_label()

    def _on_pay_bill(self) -> None:
        self.payBillsRequested.emit()

    def _on_attach_file(self) -> None:
        path, _filt = QFileDialog.getOpenFileName(
            self,
            "Attach file to bill",
            "",
            "All files (*.*)",
        )
        if path:
            self._attachment_path = path
            self._feedback("Attachment path saved with the next Save.")

    def _on_find_bill(self) -> None:
        if self._ap_conn is None:
            self._feedback("Open a company file to find bills.")
            return
        try:
            rows = business.list_bills(self._ap_conn)
        except sqlite3.Error as exc:
            self._feedback(str(exc))
            return
        ids = [int(r["id"]) for r in rows]
        if not ids:
            self._feedback("No saved bills yet.")
            return
        if self._current_bill_id is None:
            self._load_bill_into_form(ids[0])
            return
        try:
            pos = ids.index(int(self._current_bill_id))
        except ValueError:
            self._load_bill_into_form(ids[0])
            return
        nxt = pos + 1
        if nxt >= len(ids):
            self._feedback("Already at the oldest saved bill.")
            return
        self._load_bill_into_form(ids[nxt])
