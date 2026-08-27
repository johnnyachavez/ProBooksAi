"""Write Checks — QuickBooks Pro Desktop check form.

Toolbar, mint check face, Expenses/Items grid, and footer follow Johnny's QB Pro
Write Checks screenshot (slightly cleaner spacing/buttons than a gray Win32 photocopy).

Saving writes a bank payment (negative ``bank_transactions`` amount) from the selected
bank account — for example Checking — with optional expense splits.
"""

from __future__ import annotations

import math
import sqlite3
from datetime import date
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
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
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from desktop_app.flexible_date import configure_qdate_edit_us
from desktop_app.qt_combo_ids import coerce_combo_int_id, combo_index_for_int_user_data
from desktop_app.qt_mnemonic import (
    escape_ampersand_for_qt,
    message_box_information_ok,
    message_box_question_yes_no,
    message_box_warning_ok,
)
from desktop_app.theme import DISABLED_FG
from probooksai import business

if TYPE_CHECKING:
    from probooksai.bank_import import BankDatabase

# Match Create Invoices / Enter Bills / Receive Payments: light canvas, dark captions,
# not a navy redaction bar. Check face stays mint like Johnny's QB Pro screen.
_CHK_CANVAS = "#E8ECF1"
_CHK_PAPER = "#E3F2E9"
_CHK_PAPER_BORDER = "#8BB89A"
_CHK_PANEL = "#F4F7FA"
_CHK_STRIPE = "#D0E6F4"
_CHK_CAPTION = "#4A5560"
_CHK_GRID = "#C0C8D0"
_CHK_HEADER = "#D8DEE6"
_CHK_TEXT = "#1A1A1A"
_CHK_TITLE = "#5B6770"
_CHK_ACCENT = "#2563A8"
_CHK_WAVE = "#C5DCCE"
WORKFLOW_INPUT_BG = "#FFFFFF"
WORKFLOW_CONTROL_FACE = "#F7F8FA"
WORKFLOW_CONTROL_HOVER = "#E4EEF7"
WORKFLOW_CONTROL_PRESSED = "#C9D8EC"
_STRIP_BTN_OUTLINE = "#B4BCC6"
_TOP_STRIP_RADIUS_PX = 4
_TOP_STRIP_CAPTION_FONT_PX = 10
_TOP_STRIP_BODY_FONT_PX = 12
_FIELD_HEIGHT_PX = 22
_RIBBON_BTN_HEIGHT_PX = 24
_FOOTER_BTN_HEIGHT_PX = 26
_LINE_ROW_HEIGHT_PX = 22
_N_EXPENSE_ROWS = 16
_N_ITEM_ROWS = 12
_ACCOUNT_PLACEHOLDER = ""
_ITEM_PLACEHOLDER = ""
_PAYEE_PLACEHOLDER = ""

_COL_ACCOUNT = 0
_COL_AMOUNT = 1
_COL_MEMO = 2
_COL_JOB = 3
_COL_BILLABLE = 4

_ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _int_to_words(n: int) -> str:
    if n == 0:
        return "Zero"
    if n < 0:
        return "Negative " + _int_to_words(-n)
    parts = []
    if n >= 1_000_000:
        parts.append(_int_to_words(n // 1_000_000) + " Million")
        n %= 1_000_000
    if n >= 1_000:
        parts.append(_int_to_words(n // 1_000) + " Thousand")
        n %= 1_000
    if n >= 100:
        parts.append(_ONES[n // 100] + " Hundred")
        n %= 100
    if n >= 20:
        word = _TENS[n // 10]
        if n % 10:
            word += "-" + _ONES[n % 10]
        parts.append(word)
    elif n > 0:
        parts.append(_ONES[n])
    return " ".join(parts)


def amount_to_words(amount: float) -> str:
    """Convert *amount* to written-check English, e.g. 1234.56 → 'One Thousand Two Hundred Thirty-Four and 56/100'."""
    amount = abs(round(amount, 2))
    dollars = int(amount)
    cents = round((amount - dollars) * 100)
    words = _int_to_words(dollars) if dollars else "Zero"
    return f"{words} and {cents:02d}/100"


# Back-compat alias used by older call sites / tests.
_amount_to_words = amount_to_words


def _format_vendor_address_row(row: dict) -> str:
    """Build a multi-line address block from a ``vendors`` row (no tax ids)."""
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
            f"QPushButton {{ background-color: {_CHK_ACCENT}; border: 1px solid {_CHK_ACCENT}; "
            f"border-radius: {r}px; color: #FFFFFF; "
            f"font-size: {_TOP_STRIP_BODY_FONT_PX}px; padding: 0 14px; font-weight: 600; }}"
            f"QPushButton:hover {{ background-color: #1D4F8C; border: 1px solid #1D4F8C; }}"
            f"QPushButton:pressed {{ background-color: #163E6E; }}"
            f"QPushButton:disabled {{ color: #D7E3F0; background-color: #8AA7C7; "
            f"border: 1px solid #8AA7C7; }}"
        )
    return (
        f"QPushButton {{ background-color: {WORKFLOW_CONTROL_FACE}; border: 1px solid {_STRIP_BTN_OUTLINE}; "
        f"border-radius: {r}px; color: {_CHK_TEXT}; "
        f"font-size: {_TOP_STRIP_BODY_FONT_PX}px; padding: 0 12px; }}"
        f"QPushButton:hover {{ background-color: {WORKFLOW_CONTROL_HOVER}; }}"
        f"QPushButton:pressed {{ background-color: {WORKFLOW_CONTROL_PRESSED}; }}"
        f"QPushButton:disabled {{ color: {DISABLED_FG}; background-color: {WORKFLOW_CONTROL_FACE}; }}"
    )


def _input_qss(widget: str = "QLineEdit") -> str:
    return (
        f"{widget} {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_CHK_GRID}; "
        f"padding: 2px 6px; color: {_CHK_TEXT}; font-size: {_TOP_STRIP_BODY_FONT_PX}px; }}"
    )


def _zebra_cell_qss(widget: str, row: int) -> str:
    bg = _CHK_STRIPE if row % 2 else WORKFLOW_INPUT_BG
    return (
        f"{widget} {{ background-color: {bg}; border: none; "
        f"padding: 1px 4px; color: {_CHK_TEXT}; font-size: {_TOP_STRIP_BODY_FONT_PX}px; }}"
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


def _qty_spin(*, row: int = 0) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(0.0, 999_999.99)
    s.setDecimals(2)
    s.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
    s.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    s.setStyleSheet(_zebra_cell_qss("QDoubleSpinBox", row))
    return _blank_zero_spin(s)


def _light_form_palette() -> QPalette:
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(WORKFLOW_INPUT_BG))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(_CHK_TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(WORKFLOW_INPUT_BG))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(_CHK_STRIPE))
    pal.setColor(QPalette.ColorRole.Text, QColor(_CHK_TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(WORKFLOW_CONTROL_FACE))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(_CHK_TEXT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(_CHK_ACCENT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(_CHK_CAPTION))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(_CHK_PANEL))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(_CHK_TEXT))
    return pal


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
    idx = cb.findData(t)
    if idx < 0:
        idx = cb.findText(t, Qt.MatchFlag.MatchFixedString)
    if idx < 0:
        idx = cb.findText(escape_ampersand_for_qt(t), Qt.MatchFlag.MatchFixedString)
    if idx < 0:
        for i in range(cb.count()):
            label = (cb.itemText(i) or "").replace("&&", "&").strip()
            if label == t:
                idx = i
                break
    if idx >= 0:
        cb.setCurrentIndex(idx)
        return
    if cb.isEditable() and cb.lineEdit() is not None:
        cb.setCurrentIndex(0)
        cb.setEditText(t)
        return
    cb.addItem(escape_ampersand_for_qt(t), t)
    cb.setCurrentIndex(cb.count() - 1)


class _CheckPaperFrame(QFrame):
    """Mint check face with a light wavy security tint (not a photocopy of QB stock)."""

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        p.fillRect(rect, QColor(_CHK_PAPER))
        pen = QPen(QColor(_CHK_WAVE))
        pen.setWidth(1)
        p.setPen(pen)
        w = max(1, rect.width())
        h = rect.height()
        for row in range(6, h, 11):
            path = QPainterPath()
            path.moveTo(rect.left(), rect.top() + row)
            amp = 3.0
            step = 14
            x = 0
            while x <= w:
                y = rect.top() + row + amp * math.sin((x + row) / 18.0)
                path.lineTo(rect.left() + x, y)
                x += step
            p.drawPath(path)
        p.end()


class CheckScreen(QWidget):
    """QuickBooks-style Write Checks form for one bank account."""

    #: Emitted after any save or delete so the Bank Register can refresh.
    transactionSaved = Signal()

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

    def __init__(
        self,
        bank_db=None,
        coa_list: list | None = None,
        parent=None,
        *,
        ap_conn: Optional[sqlite3.Connection] = None,
    ):
        """
        *bank_db* — ``BankDatabase`` instance.
        *coa_list* — list of COA display strings for the expense account dropdown.
        *ap_conn* — company SQLite connection (vendors / COA); defaults to ``bank_db._conn``.
        """
        super().__init__(parent)
        self._db: Optional["BankDatabase"] = bank_db
        self._ap_conn = ap_conn
        if self._ap_conn is None and bank_db is not None:
            self._ap_conn = getattr(bank_db, "_conn", None)
        self._coa_list: list[str] = list(coa_list or [])
        self._item_codes: list[str] = []
        self._current_account_id: Optional[int] = None
        self._browse_ids: list[int] = []
        self._browse_index: Optional[int] = None
        self._loading = False
        self._suppress_line_recalc = False
        self._attachment_path = ""
        self._amount_spins: list[QDoubleSpinBox] = []
        self._expense_billable: list[QCheckBox] = []
        self._item_qty_spins: list[QDoubleSpinBox] = []
        self._item_cost_spins: list[QDoubleSpinBox] = []
        self._item_amount_spins: list[QDoubleSpinBox] = []
        self._item_billable: list[QCheckBox] = []
        self._accounts: list = []
        self.setWindowTitle("Write Checks")
        self.setToolTip(
            "Write Checks: pay a vendor or payee from a bank account. "
            "Save writes a register payment (File → Backup / Restore, probooks.backup)."
        )
        if not self._coa_list:
            self._coa_list = self._load_coa_labels()
        self._item_codes = self._load_item_codes()
        self._build_ui()
        self._populate_payee_combo()
        self._refresh_accounts()
        self._update_save_enabled()

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
            f"color: {_CHK_CAPTION}; font-size: {_TOP_STRIP_CAPTION_FONT_PX}px; "
            "font-weight: bold; letter-spacing: 0.04em; background: transparent; border: none;"
        )
        return cap

    def _meta_field(self, caption: str, editor: QWidget) -> QWidget:
        wrap = QWidget()
        wrap.setObjectName("writeChecksMetaField")
        wrap.setAutoFillBackground(True)
        pal = wrap.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(WORKFLOW_INPUT_BG))
        pal.setColor(QPalette.ColorRole.WindowText, QColor(_CHK_CAPTION))
        wrap.setPalette(pal)
        wrap.setStyleSheet(
            "QWidget#writeChecksMetaField { background-color: #FFFFFF; border: none; }"
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

    def _check_caption_field(self, caption: str, editor: QWidget, *, cap_w: int = 0) -> QWidget:
        wrap = QWidget()
        wrap.setObjectName("writeChecksCaptionField")
        wrap.setAutoFillBackground(True)
        pal = wrap.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(_CHK_PAPER))
        pal.setColor(QPalette.ColorRole.WindowText, QColor(_CHK_CAPTION))
        wrap.setPalette(pal)
        wrap.setStyleSheet(
            f"QWidget#writeChecksCaptionField {{ background-color: {_CHK_PAPER}; border: none; }}"
        )
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        cap = self._caption(caption)
        if cap_w:
            cap.setFixedWidth(cap_w)
            cap.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if isinstance(editor, (QLineEdit, QDateEdit, QComboBox, QDoubleSpinBox)):
            editor.setFixedHeight(_FIELD_HEIGHT_PX)
        lay.addWidget(cap)
        lay.addWidget(editor, 1)
        return wrap

    def _make_account_combo(self, *, row: int = 0) -> QComboBox:
        cb = QComboBox()
        cb.setEditable(True)
        cb.addItem(_ACCOUNT_PLACEHOLDER, "")
        for label in self._coa_list:
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
            f" alternate-background-color: {_CHK_STRIPE};"
            f" color: {_CHK_TEXT};"
            f" gridline-color: {_CHK_GRID};"
            f" border: 1px solid {_CHK_GRID};"
            " }"
            f"QHeaderView::section {{"
            f" background-color: {_CHK_HEADER};"
            f" color: {_CHK_CAPTION};"
            f" padding: 4px; border: 1px solid {_CHK_GRID};"
            " font-weight: bold; font-size: 11px;"
            " }"
        )

    def _build_ui(self) -> None:
        self.setPalette(_light_form_palette())
        self.setAutoFillBackground(True)
        self.setStyleSheet(
            f"CheckScreen {{ background-color: {_CHK_CANVAS}; color: {_CHK_TEXT}; }}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 4, 6, 4)
        root.setSpacing(4)
        self._build_toolbar(root)
        self._build_account_bar(root)
        self._build_check_paper(root)
        self._build_line_tabs(root)
        self._build_footer_actions(root)

    def _build_toolbar(self, play: QVBoxLayout) -> None:
        toolbar = QWidget()
        toolbar.setObjectName("writeChecksToolbar")
        toolbar.setStyleSheet(
            f"QWidget#writeChecksToolbar {{ background: {WORKFLOW_INPUT_BG}; "
            f"border: 1px solid {_CHK_GRID}; border-radius: 4px; }}"
        )
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(6, 3, 6, 3)
        tb.setSpacing(4)

        def _sep() -> QFrame:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.VLine)
            sep.setStyleSheet(f"color: {_CHK_GRID};")
            sep.setFixedWidth(8)
            return sep

        self._btn_find = QPushButton("Find")
        self._btn_find.setToolTip("Go to the previous check for this bank account.")
        self._btn_new = QPushButton("New")
        self._btn_new.setToolTip("Start a new blank check (does not save the current form).")
        self._btn_save = QPushButton("Save")
        self._btn_save.setToolTip("Save this check to the register and keep it open.")
        self._btn_delete = QPushButton("Delete")
        self._btn_delete.setToolTip("Delete this check from the register.")
        self._btn_memorize = QPushButton("Memorize")
        self._btn_memorize.setToolTip("Memorize this check (layout control; saved checks stay in the register).")
        self._btn_copy = QPushButton("Create a Copy")
        self._btn_copy.setToolTip("Copy this check onto a new blank form.")
        self._btn_print = QPushButton("Print")
        self._btn_print.setToolTip("Print this check (layout control for now).")
        self._chk_print_later = QCheckBox("Print Later")
        self._chk_print_later.setStyleSheet(
            f"QCheckBox {{ color: {_CHK_TEXT}; background: transparent; font-size: 12px; }}"
        )
        self._chk_pay_online = QCheckBox("Pay Online")
        self._chk_pay_online.setStyleSheet(
            f"QCheckBox {{ color: {_CHK_TEXT}; background: transparent; font-size: 12px; }}"
        )
        self._btn_attach = QPushButton("Attach File")
        self._btn_attach.setToolTip("Attach a file path stored with this check.")
        self._btn_clear_splits = QPushButton("Clear Splits")
        self._btn_clear_splits.setToolTip("Clear Expenses and Items lines without changing the check header.")
        self._btn_recalc = QPushButton("Recalculate")
        self._btn_recalc.setToolTip("Set the check amount from Expenses + Items.")
        self._btn_reorder = QPushButton("Reorder Reminder")
        self._btn_reorder.setToolTip("Check reorder reminder (layout control).")
        self._btn_order_checks = QPushButton("Order Checks")
        self._btn_order_checks.setToolTip("Order checks (layout control).")

        for b in (
            self._btn_find,
            self._btn_new,
            self._btn_save,
            self._btn_delete,
            self._btn_memorize,
            self._btn_copy,
            self._btn_print,
            self._btn_attach,
            self._btn_clear_splits,
            self._btn_recalc,
            self._btn_reorder,
            self._btn_order_checks,
        ):
            self._style_button(b)
            tb.addWidget(b)
            if b is self._btn_delete:
                tb.addWidget(_sep())
            elif b is self._btn_print:
                tb.addWidget(self._chk_print_later)
                tb.addWidget(self._chk_pay_online)
                tb.addWidget(_sep())
            elif b is self._btn_recalc:
                tb.addWidget(_sep())

        tb.addStretch(1)
        self._lbl_position = QLabel("")
        self._lbl_position.setStyleSheet(
            f"color: {_CHK_CAPTION}; font-size: 11px; background: transparent;"
        )
        tb.addWidget(self._lbl_position)
        play.addWidget(toolbar)

        _uc = Qt.ConnectionType.UniqueConnection
        self._btn_find.clicked.connect(self._on_prev, _uc)
        self._btn_new.clicked.connect(self._on_new, _uc)
        self._btn_save.clicked.connect(self._on_ribbon_save, _uc)
        self._btn_delete.clicked.connect(self._on_delete, _uc)
        self._btn_copy.clicked.connect(self._on_create_copy, _uc)
        self._btn_print.clicked.connect(self._on_print, _uc)
        self._btn_attach.clicked.connect(self._on_attach_file, _uc)
        self._btn_clear_splits.clicked.connect(self._clear_expense_rows, _uc)
        self._btn_recalc.clicked.connect(self._on_recalculate, _uc)

    def _build_account_bar(self, play: QVBoxLayout) -> None:
        bar = QWidget()
        bar.setObjectName("writeChecksAccountBar")
        bar.setStyleSheet(
            f"QWidget#writeChecksAccountBar {{ background: {_CHK_PANEL}; "
            f"border: 1px solid {_CHK_GRID}; border-radius: 4px; }}"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(12)

        self._acct_combo = QComboBox()
        self._acct_combo.setObjectName("writeChecksBankAccount")
        self._acct_combo.setMinimumWidth(240)
        self._acct_combo.setToolTip("Bank account to write checks against.")
        self._acct_combo.currentIndexChanged.connect(self._on_account_changed)
        lay.addWidget(self._meta_field("BANK ACCOUNT", self._acct_combo), 0)
        lay.addStretch(1)

        end_wrap = QWidget()
        end_wrap.setObjectName("writeChecksMetaField")
        end_wrap.setAutoFillBackground(True)
        pal = end_wrap.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(WORKFLOW_INPUT_BG))
        end_wrap.setPalette(pal)
        end_wrap.setStyleSheet(
            "QWidget#writeChecksMetaField { background-color: #FFFFFF; border: none; }"
        )
        end_lay = QVBoxLayout(end_wrap)
        end_lay.setContentsMargins(0, 0, 0, 0)
        end_lay.setSpacing(1)
        end_lay.addWidget(self._caption("ENDING BALANCE"))
        self._lbl_balance = QLabel("")
        self._lbl_balance.setObjectName("writeChecksEndingBalance")
        self._lbl_balance.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {_CHK_TEXT}; "
            "background: transparent; border: none;"
        )
        end_lay.addWidget(self._lbl_balance)
        lay.addWidget(end_wrap, 0)
        play.addWidget(bar)

    def _build_check_paper(self, play: QVBoxLayout) -> None:
        frame = _CheckPaperFrame()
        frame.setObjectName("writeChecksPaper")
        frame.setStyleSheet(
            f"QFrame#writeChecksPaper {{ background-color: {_CHK_PAPER}; "
            f"border: 1px solid {_CHK_PAPER_BORDER}; border-radius: 6px; }}"
        )
        frame.setMinimumHeight(210)
        frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        vbox = QVBoxLayout(frame)
        vbox.setContentsMargins(16, 10, 16, 10)
        vbox.setSpacing(6)

        row0 = QHBoxLayout()
        row0.addStretch(1)
        self._fld_number = QLineEdit()
        self._fld_number.setObjectName("writeChecksNumber")
        self._fld_number.setMaximumWidth(90)
        self._fld_number.setStyleSheet(_input_qss("QLineEdit"))
        self._fld_number.setToolTip("Check number / reference (stored as ref_number).")
        row0.addWidget(self._check_caption_field("NO.", self._fld_number))
        row0.addSpacing(16)
        self._date_edit = QDateEdit()
        configure_qdate_edit_us(self._date_edit)
        self._date_edit.setDate(QDate.currentDate())
        self._date_edit.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._date_edit.setMinimumWidth(120)
        self._date_edit.setStyleSheet(_input_qss("QDateEdit"))
        self._date_edit.setToolTip("Check date.")
        row0.addWidget(self._check_caption_field("DATE", self._date_edit))
        vbox.addLayout(row0)

        row1 = QHBoxLayout()
        self._fld_payee = QComboBox()
        self._fld_payee.setObjectName("writeChecksPayee")
        self._fld_payee.setEditable(True)
        self._fld_payee.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._fld_payee.setMinimumWidth(280)
        self._fld_payee.setStyleSheet(_input_qss("QComboBox"))
        self._fld_payee.setToolTip("Payee / vendor. Typed names are stored as the register description.")
        self._fld_payee.currentIndexChanged.connect(self._on_payee_changed)
        row1.addWidget(self._check_caption_field("PAY TO THE ORDER OF", self._fld_payee), 1)
        row1.addSpacing(8)
        self._spin_amount = _money_spin()
        self._spin_amount.setObjectName("writeChecksAmount")
        self._spin_amount.setMinimumWidth(110)
        self._spin_amount.setMaximumWidth(140)
        self._spin_amount.setToolTip("Check amount. Stored as a negative payment in the register.")
        self._spin_amount.valueChanged.connect(self._on_amount_changed)
        dollar = self._caption("$")
        dollar.setStyleSheet(
            f"color: {_CHK_TEXT}; font-size: 16px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        row1.addWidget(dollar)
        row1.addWidget(self._spin_amount)
        vbox.addLayout(row1)

        row2 = QHBoxLayout()
        self._fld_dollars = QLineEdit()
        self._fld_dollars.setObjectName("writeChecksAmountWords")
        self._fld_dollars.setReadOnly(True)
        self._fld_dollars.setToolTip("Amount in words — updates automatically.")
        self._fld_dollars.setStyleSheet(
            f"QLineEdit {{ border: none; border-bottom: 1px solid {_CHK_PAPER_BORDER}; "
            f"background: transparent; color: {_CHK_TEXT}; padding: 2px 0; }}"
        )
        row2.addWidget(self._fld_dollars, 1)
        dollars_lbl = self._caption("DOLLARS")
        row2.addWidget(dollars_lbl)
        vbox.addLayout(row2)

        addr_row = QHBoxLayout()
        addr_cap = self._caption("ADDRESS")
        addr_cap.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        addr_cap.setFixedWidth(72)
        self._address_edit = QPlainTextEdit()
        self._address_edit.setObjectName("writeChecksAddress")
        self._address_edit.setMaximumHeight(64)
        self._address_edit.setMinimumHeight(48)
        self._address_edit.setStyleSheet(
            f"QPlainTextEdit {{ background: {WORKFLOW_INPUT_BG}; color: {_CHK_TEXT}; "
            f"border: 1px solid {_CHK_GRID}; border-radius: 3px; padding: 2px 4px; }}"
        )
        addr_row.addWidget(addr_cap)
        addr_row.addWidget(self._address_edit, 0)
        addr_row.addStretch(1)
        vbox.addLayout(addr_row)

        self._fld_memo = QLineEdit()
        self._fld_memo.setObjectName("writeChecksMemo")
        self._fld_memo.setStyleSheet(_input_qss("QLineEdit"))
        self._fld_memo.setToolTip("Memo printed on the check and stored on the register line.")
        vbox.addWidget(self._check_caption_field("MEMO", self._fld_memo))
        play.addWidget(frame)

    def _build_line_tabs(self, play: QVBoxLayout) -> None:
        self._expense_tab = QTabWidget()
        self._expense_tab.setObjectName("writeChecksLineTabs")
        self._expense_tab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._expense_tab.setStyleSheet(
            f"QTabWidget#writeChecksLineTabs::pane {{ border: 1px solid {_CHK_GRID}; "
            f"background: {WORKFLOW_INPUT_BG}; }}"
            f"QTabWidget#writeChecksLineTabs QTabBar::tab {{ background: {_CHK_HEADER}; color: {_CHK_CAPTION}; "
            "padding: 4px 14px; border: 1px solid #C8C8C8; border-bottom: none; margin-right: 2px; }"
            f"QTabWidget#writeChecksLineTabs QTabBar::tab:selected {{ background: {WORKFLOW_INPUT_BG}; "
            f"color: #1A5276; font-weight: bold; border-bottom: 2px solid {_CHK_ACCENT}; }}"
        )

        self._exp_table = QTableWidget(self._N_EXPENSE_ROWS, len(self._EXPENSE_COLS))
        self._exp_table.setObjectName("writeChecksExpensesTable")
        self._exp_table.setHorizontalHeaderLabels(self._EXPENSE_COLS)
        self._configure_grid(self._exp_table, amount_col=1, billable_col=4)
        self._exp_table.setStyleSheet(self._table_qss("writeChecksExpensesTable"))
        self._fill_expense_rows()
        self._expense_tab.addTab(self._exp_table, "Expenses  $0.00")

        self._items_table = QTableWidget(_N_ITEM_ROWS, len(self._ITEM_COLS))
        self._items_table.setObjectName("writeChecksItemsTable")
        self._items_table.setHorizontalHeaderLabels(self._ITEM_COLS)
        self._configure_grid(self._items_table, amount_col=4, billable_col=6)
        self._items_table.setStyleSheet(self._table_qss("writeChecksItemsTable"))
        self._fill_item_rows()
        self._expense_tab.addTab(self._items_table, "Items  $0.00")
        play.addWidget(self._expense_tab, 1)

    def _configure_grid(self, table: QTableWidget, *, amount_col: int, billable_col: int) -> None:
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
        for col in range(table.columnCount()):
            if col == billable_col:
                hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            elif col == amount_col:
                hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            else:
                hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        table.setColumnWidth(amount_col, 110)
        table.setColumnWidth(billable_col, 78)
        for r in range(table.rowCount()):
            table.setRowHeight(r, _LINE_ROW_HEIGHT_PX)

    def _fill_expense_rows(self) -> None:
        self._amount_spins = []
        self._expense_billable = []
        for row in range(self._N_EXPENSE_ROWS):
            self._exp_table.setCellWidget(row, _COL_ACCOUNT, self._make_account_combo(row=row))
            amt = _money_spin(row=row, blank_zero=True)
            amt.setValue(0.0)
            amt.valueChanged.connect(self._on_line_amount_changed)
            self._exp_table.setCellWidget(row, _COL_AMOUNT, amt)
            self._amount_spins.append(amt)
            memo = _cell_line(row=row)
            self._exp_table.setCellWidget(row, _COL_MEMO, memo)
            job = _cell_line(row=row)
            self._exp_table.setCellWidget(row, _COL_JOB, job)
            billable = self._make_billable_check()
            self._exp_table.setCellWidget(row, _COL_BILLABLE, billable)
            self._expense_billable.append(billable)

    def _fill_item_rows(self) -> None:
        self._item_qty_spins = []
        self._item_cost_spins = []
        self._item_amount_spins = []
        self._item_billable = []
        for row in range(_N_ITEM_ROWS):
            self._items_table.setCellWidget(row, 0, self._make_item_combo(row=row))
            self._items_table.setCellWidget(row, 1, _cell_line(row=row))
            qty = _qty_spin(row=row)
            cost = _money_spin(row=row, blank_zero=True)
            amt = _money_spin(row=row, blank_zero=True)
            qty.valueChanged.connect(lambda _v, r=row: self._on_item_qty_cost_changed(r))
            cost.valueChanged.connect(lambda _v, r=row: self._on_item_qty_cost_changed(r))
            amt.valueChanged.connect(self._on_line_amount_changed)
            self._items_table.setCellWidget(row, 2, qty)
            self._items_table.setCellWidget(row, 3, cost)
            self._items_table.setCellWidget(row, 4, amt)
            self._item_qty_spins.append(qty)
            self._item_cost_spins.append(cost)
            self._item_amount_spins.append(amt)
            self._items_table.setCellWidget(row, 5, _cell_line(row=row))
            billable = self._make_billable_check()
            self._items_table.setCellWidget(row, 6, billable)
            self._item_billable.append(billable)

    def _build_footer_actions(self, play: QVBoxLayout) -> None:
        actions = QFrame()
        actions.setObjectName("writeChecksActionsBar")
        actions.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        actions.setStyleSheet(
            f"QFrame#writeChecksActionsBar {{ background-color: {_CHK_PANEL}; "
            f"border: 1px solid {_CHK_GRID}; border-radius: 4px; }}"
        )
        bot = QHBoxLayout(actions)
        bot.setContentsMargins(8, 4, 8, 4)
        bot.addStretch(1)
        self._btn_save_close = QPushButton("Save && Close")
        self._btn_save_new = QPushButton("Save && New")
        self._btn_clear = QPushButton("Clear")
        self._btn_save_close.setToolTip(
            "Save this check to the register and keep it on the form "
            "(tab analog of QuickBooks Save & Close)."
        )
        self._btn_save_new.setToolTip("Save this check, then start a new blank check.")
        self._btn_clear.setToolTip("Clear the form without saving (new draft).")
        self._style_button(self._btn_save_close, height=_FOOTER_BTN_HEIGHT_PX)
        self._style_button(self._btn_save_new, primary=True, height=_FOOTER_BTN_HEIGHT_PX)
        self._style_button(self._btn_clear, height=_FOOTER_BTN_HEIGHT_PX)
        bot.addWidget(self._btn_save_close)
        bot.addWidget(self._btn_save_new)
        bot.addWidget(self._btn_clear)
        play.addWidget(actions)

        _uc = Qt.ConnectionType.UniqueConnection
        self._btn_save_close.clicked.connect(self._on_save_close, _uc)
        self._btn_save_new.clicked.connect(self._on_save_new, _uc)
        self._btn_clear.clicked.connect(self._on_clear, _uc)

    def _update_save_enabled(self) -> None:
        on = self._db is not None
        for b in (
            self._btn_save,
            self._btn_save_close,
            self._btn_save_new,
            self._btn_attach,
        ):
            b.setEnabled(on)
        self._btn_new.setEnabled(True)
        self._btn_clear.setEnabled(True)
        self._btn_clear_splits.setEnabled(True)
        self._btn_recalc.setEnabled(True)
        self._update_nav_buttons()

    def _populate_payee_combo(self) -> None:
        prev = _combo_text(self._fld_payee, placeholders=(_PAYEE_PLACEHOLDER,)) if hasattr(self, "_fld_payee") else ""
        self._fld_payee.blockSignals(True)
        self._fld_payee.clear()
        self._fld_payee.addItem(_PAYEE_PLACEHOLDER, None)
        if self._ap_conn is not None:
            try:
                for row in business.list_vendors(self._ap_conn):
                    d = dict(row)
                    vid = int(d["id"])
                    name = (d.get("name") or "").strip()
                    self._fld_payee.addItem(escape_ampersand_for_qt(name or f"Vendor #{vid}"), vid)
            except (sqlite3.Error, KeyError, TypeError, ValueError):
                pass
        if prev:
            _set_combo_text(self._fld_payee, prev)
        self._fld_payee.blockSignals(False)

    def refresh_payees(self) -> None:
        """Reload vendor names after Business / Vendors edits."""
        self._populate_payee_combo()

    def select_payee_vendor(self, vendor_id: int) -> None:
        """Tiny Vendor Center hook: Pay to the Order of *vendor_id*."""
        self.refresh_payees()
        vid = int(vendor_id)
        for i in range(self._fld_payee.count()):
            if coerce_combo_int_id(self._fld_payee.itemData(i)) == vid:
                self._fld_payee.setCurrentIndex(i)
                return

    def _on_payee_changed(self, _index: int = 0) -> None:
        if self._loading:
            return
        vid = coerce_combo_int_id(self._fld_payee.currentData())
        if vid is None or self._ap_conn is None:
            if not _combo_text(self._fld_payee, placeholders=(_PAYEE_PLACEHOLDER,)):
                self._address_edit.setPlainText("")
            return
        try:
            row = business.get_vendor(self._ap_conn, vid)
        except (sqlite3.Error, TypeError, ValueError):
            row = None
        if row is None:
            return
        self._address_edit.setPlainText(_format_vendor_address_row(dict(row)))

    def _refresh_accounts(self) -> None:
        self._acct_combo.blockSignals(True)
        prev_id = self._current_account_id
        self._acct_combo.clear()
        self._accounts = []
        if self._db is not None:
            try:
                self._accounts = list(self._db.list_bank_accounts())
            except Exception:
                self._accounts = []
        if not self._accounts:
            self._acct_combo.addItem("", None)
        else:
            for acct in self._accounts:
                d = dict(acct)
                aid = coerce_combo_int_id(d.get("id"))
                if aid is None:
                    continue
                label = (d.get("name") or "").strip() or f"Account #{aid}"
                self._acct_combo.addItem(escape_ampersand_for_qt(label), aid)
        self._acct_combo.blockSignals(False)
        if prev_id is not None:
            ix = combo_index_for_int_user_data(self._acct_combo, prev_id)
            self._acct_combo.setCurrentIndex(ix if ix is not None else 0)
        else:
            self._acct_combo.setCurrentIndex(0)
        self._on_account_changed()

    def _on_account_changed(self) -> None:
        aid = coerce_combo_int_id(self._acct_combo.currentData())
        self._current_account_id = aid
        self._browse_ids = []
        self._browse_index = None
        if aid is not None:
            self._reload_browse_list()
        self._update_balance_label()
        self._load_current()

    def _reload_browse_list(self) -> None:
        if self._db is None or self._current_account_id is None:
            self._browse_ids = []
            return
        txns = self._db.list_transactions(self._current_account_id)
        self._browse_ids = [int(t["id"]) for t in txns if float(t["amount"] or 0) < 0]

    def _next_check_number(self) -> str:
        if self._db is None or self._current_account_id is None:
            return "1"
        try:
            txns = self._db.list_transactions(self._current_account_id)
        except Exception:
            return "1"
        max_n = 0
        for t in txns:
            ref = str(t["ref_number"] or "").strip()
            if ref.isdigit():
                max_n = max(max_n, int(ref))
        return str(max_n + 1)

    def _on_prev(self) -> None:
        if not self._browse_ids:
            return
        if self._browse_index is None:
            self._browse_index = len(self._browse_ids) - 1
        elif self._browse_index > 0:
            self._browse_index -= 1
        self._load_current()

    def _on_new(self) -> None:
        self._browse_index = None
        self._load_current()

    def _on_ribbon_save(self) -> None:
        self._persist_check(reset=False)

    def _on_save_close(self) -> None:
        self._persist_check(reset=False)

    def _on_save_new(self) -> None:
        self._persist_check(reset=True)

    def _on_clear(self) -> None:
        self._browse_index = None
        self._load_blank()
        self._update_nav_buttons()

    def _on_create_copy(self) -> None:
        self._browse_index = None
        self._fld_number.setText(self._next_check_number())
        self._update_nav_buttons()

    def _on_print(self) -> None:
        message_box_information_ok(
            self,
            "Print",
            "Check printing uses the company printer in a later release. Save still writes the register.",
            ok_tip="Close.",
        )

    def _on_attach_file(self) -> None:
        path, _flt = QFileDialog.getOpenFileName(self, "Attach File", "", "All files (*)")
        if path:
            self._attachment_path = path

    def _update_nav_buttons(self) -> None:
        n = len(self._browse_ids)
        has_any = n > 0
        is_draft = self._browse_index is None
        can_prev = has_any and (is_draft or (self._browse_index or 0) > 0)
        self._btn_find.setEnabled(self._db is not None and can_prev)
        self._btn_delete.setEnabled(self._db is not None and not is_draft)
        if is_draft:
            self._lbl_position.setText("New")
        else:
            idx = self._browse_index or 0
            self._lbl_position.setText(f"{idx + 1} / {n}")

    def _load_current(self) -> None:
        self._loading = True
        try:
            if self._browse_index is None or not self._browse_ids:
                self._load_blank()
            else:
                tid = self._browse_ids[self._browse_index]
                txn = self._db.get_transaction(tid) if self._db is not None else None
                if txn is None:
                    self._load_blank()
                else:
                    self._load_txn(dict(txn))
        finally:
            self._loading = False
        self._update_nav_buttons()
        self._update_save_enabled()

    def _load_blank(self) -> None:
        today = date.today()
        self._date_edit.setDate(QDate(today.year, today.month, today.day))
        self._fld_payee.setCurrentIndex(0)
        if self._fld_payee.isEditable() and self._fld_payee.lineEdit() is not None:
            self._fld_payee.lineEdit().clear()
        self._fld_number.setText(self._next_check_number())
        self._fld_memo.clear()
        self._address_edit.setPlainText("")
        self._spin_amount.setValue(0.0)
        self._fld_dollars.setText("")
        self._attachment_path = ""
        self._chk_print_later.setChecked(False)
        self._chk_pay_online.setChecked(False)
        self._clear_expense_rows()

    def _load_txn(self, d: dict) -> None:
        raw_date = (d.get("txn_date") or "").strip()
        if raw_date:
            parts = raw_date.split("-")
            if len(parts) == 3:
                try:
                    self._date_edit.setDate(QDate(int(parts[0]), int(parts[1]), int(parts[2])))
                except Exception:
                    pass
        payee = (d.get("description") or "").strip()
        _set_combo_text(self._fld_payee, payee)
        self._fld_number.setText(d.get("ref_number") or "")
        self._fld_memo.setText(d.get("memo") or "")
        amt = abs(float(d.get("amount") or 0))
        self._spin_amount.setValue(amt)
        self._fld_dollars.setText(amount_to_words(amt) if amt else "")
        self._attachment_path = (d.get("attachment_path") or "") if "attachment_path" in d else ""
        self._clear_expense_rows()
        splits = []
        if self._ap_conn is not None and d.get("id") is not None:
            try:
                splits = [dict(r) for r in business.list_splits(self._ap_conn, int(d["id"]))]
            except (sqlite3.Error, TypeError, ValueError):
                splits = []
        if splits:
            self._suppress_line_recalc = True
            try:
                for i, sp in enumerate(splits[: self._N_EXPENSE_ROWS]):
                    acct = self._exp_table.cellWidget(i, _COL_ACCOUNT)
                    if isinstance(acct, QComboBox):
                        _set_combo_text(acct, sp.get("coa_account") or "")
                    if i < len(self._amount_spins):
                        self._amount_spins[i].setValue(abs(float(sp.get("amount") or 0)))
                    memo_w = self._exp_table.cellWidget(i, _COL_MEMO)
                    if isinstance(memo_w, QLineEdit):
                        memo_w.setText(sp.get("memo") or "")
            finally:
                self._suppress_line_recalc = False
        else:
            coa = (d.get("coa_account") or "").strip()
            if coa:
                acct = self._exp_table.cellWidget(0, _COL_ACCOUNT)
                if isinstance(acct, QComboBox):
                    _set_combo_text(acct, coa)
                if self._amount_spins:
                    self._amount_spins[0].setValue(amt)
        self._update_expense_total()

    def _clear_expense_rows(self) -> None:
        self._suppress_line_recalc = True
        try:
            for r in range(self._N_EXPENSE_ROWS):
                acct = self._exp_table.cellWidget(r, _COL_ACCOUNT)
                if isinstance(acct, QComboBox):
                    acct.setCurrentIndex(0)
                    if acct.lineEdit() is not None:
                        acct.lineEdit().clear()
                if r < len(self._amount_spins):
                    self._amount_spins[r].setValue(0.0)
                memo_w = self._exp_table.cellWidget(r, _COL_MEMO)
                if isinstance(memo_w, QLineEdit):
                    memo_w.clear()
                job_w = self._exp_table.cellWidget(r, _COL_JOB)
                if isinstance(job_w, QLineEdit):
                    job_w.clear()
                if r < len(self._expense_billable):
                    self._expense_billable[r].setChecked(False)
            for r in range(_N_ITEM_ROWS):
                item = self._items_table.cellWidget(r, 0)
                if isinstance(item, QComboBox):
                    item.setCurrentIndex(0)
                    if item.lineEdit() is not None:
                        item.lineEdit().clear()
                desc = self._items_table.cellWidget(r, 1)
                if isinstance(desc, QLineEdit):
                    desc.clear()
                if r < len(self._item_qty_spins):
                    self._item_qty_spins[r].setValue(0.0)
                if r < len(self._item_cost_spins):
                    self._item_cost_spins[r].setValue(0.0)
                if r < len(self._item_amount_spins):
                    self._item_amount_spins[r].setValue(0.0)
                job_w = self._items_table.cellWidget(r, 5)
                if isinstance(job_w, QLineEdit):
                    job_w.clear()
                if r < len(self._item_billable):
                    self._item_billable[r].setChecked(False)
        finally:
            self._suppress_line_recalc = False
        self._update_expense_total()

    def _on_amount_changed(self, val: float) -> None:
        if self._loading:
            return
        self._fld_dollars.setText(amount_to_words(val) if val else "")

    def _on_item_qty_cost_changed(self, row: int) -> None:
        if self._suppress_line_recalc:
            return
        if 0 <= row < len(self._item_qty_spins):
            qty = float(self._item_qty_spins[row].value())
            cost = float(self._item_cost_spins[row].value())
            self._item_amount_spins[row].blockSignals(True)
            self._item_amount_spins[row].setValue(round(qty * cost, 2))
            self._item_amount_spins[row].blockSignals(False)
        self._on_line_amount_changed()

    def _on_line_amount_changed(self, *_args) -> None:
        if self._suppress_line_recalc:
            return
        self._update_expense_total()

    def _expense_total(self) -> float:
        total = 0.0
        for spin in self._amount_spins:
            total += float(spin.value() or 0.0)
        return round(total, 2)

    def _items_total(self) -> float:
        total = 0.0
        for spin in self._item_amount_spins:
            total += float(spin.value() or 0.0)
        return round(total, 2)

    def _update_expense_total(self) -> None:
        exp = self._expense_total()
        items = self._items_total()
        self._expense_tab.setTabText(0, f"Expenses  ${exp:,.2f}")
        self._expense_tab.setTabText(1, f"Items  ${items:,.2f}")

    def _on_recalculate(self) -> None:
        total = round(self._expense_total() + self._items_total(), 2)
        self._spin_amount.setValue(total)
        self._fld_dollars.setText(amount_to_words(total) if total else "")

    def _collect_expense_splits(self) -> list[tuple[float, str, str]]:
        rows: list[tuple[float, str, str]] = []
        for r in range(self._N_EXPENSE_ROWS):
            acct_w = self._exp_table.cellWidget(r, _COL_ACCOUNT)
            acct = _combo_text(acct_w, placeholders=(_ACCOUNT_PLACEHOLDER,)) if isinstance(acct_w, QComboBox) else ""
            amt = float(self._amount_spins[r].value() or 0.0) if r < len(self._amount_spins) else 0.0
            memo_w = self._exp_table.cellWidget(r, _COL_MEMO)
            memo = (memo_w.text() or "").strip() if isinstance(memo_w, QLineEdit) else ""
            job_w = self._exp_table.cellWidget(r, _COL_JOB)
            job = (job_w.text() or "").strip() if isinstance(job_w, QLineEdit) else ""
            if job:
                memo = f"{memo} [{job}]".strip() if memo else job
            if amt <= 0 and not acct:
                continue
            if amt <= 0:
                continue
            rows.append((-round(amt, 2), acct, memo))
        for r in range(_N_ITEM_ROWS):
            item_w = self._items_table.cellWidget(r, 0)
            item = _combo_text(item_w, placeholders=(_ITEM_PLACEHOLDER,)) if isinstance(item_w, QComboBox) else ""
            desc_w = self._items_table.cellWidget(r, 1)
            desc = (desc_w.text() or "").strip() if isinstance(desc_w, QLineEdit) else ""
            amt = float(self._item_amount_spins[r].value() or 0.0) if r < len(self._item_amount_spins) else 0.0
            if amt <= 0:
                continue
            rows.append((-round(amt, 2), item or desc, desc or item))
        return rows

    def _payee_text(self) -> str:
        return _combo_text(self._fld_payee, placeholders=(_PAYEE_PLACEHOLDER,))

    def _persist_check(self, *, reset: bool) -> bool:
        if self._db is None or self._current_account_id is None:
            message_box_warning_ok(
                self,
                "No account",
                "Select a bank account first.",
                ok_tip="Close; choose a bank account from BANK ACCOUNT.",
            )
            return False
        payee = self._payee_text()
        if not payee:
            message_box_warning_ok(
                self,
                "Payee required",
                "Enter who to pay in PAY TO THE ORDER OF.",
                ok_tip="Close; choose a vendor or type a payee name.",
            )
            return False
        splits = self._collect_expense_splits()
        line_total = round(sum(abs(s[0]) for s in splits), 2)
        raw_amt = round(float(self._spin_amount.value() or 0.0), 2)
        if raw_amt <= 0 and line_total > 0:
            raw_amt = line_total
            self._spin_amount.setValue(raw_amt)
        if raw_amt <= 0:
            message_box_warning_ok(
                self,
                "Amount required",
                "Enter a check amount or expense line amounts.",
                ok_tip="Close; fill the $ box or an Expenses amount.",
            )
            return False
        if line_total > 0 and abs(line_total - raw_amt) > 0.02:
            raw_amt = line_total
            self._spin_amount.setValue(raw_amt)
        qd = self._date_edit.date()
        txn_date = f"{qd.year():04d}-{qd.month():02d}-{qd.day():02d}"
        ref = self._fld_number.text().strip()
        memo = self._fld_memo.text().strip() or "CHK"
        amount = -raw_amt
        coa = splits[0][1] if splits else ""
        is_draft = self._browse_index is None
        try:
            if is_draft:
                new_id = self._db.insert_manual_transaction(
                    self._current_account_id,
                    txn_date,
                    amount,
                    description=payee,
                    ref_number=ref,
                    memo=memo,
                    coa_account=coa,
                )
                if self._attachment_path:
                    self._db.update_transaction(new_id, attachment_path=self._attachment_path)
                if splits and self._ap_conn is not None:
                    business.replace_splits(self._ap_conn, new_id, splits)
                self._reload_browse_list()
                try:
                    self._browse_index = self._browse_ids.index(new_id)
                except ValueError:
                    self._browse_index = len(self._browse_ids) - 1 if self._browse_ids else None
            else:
                tid = self._browse_ids[self._browse_index]
                self._db.update_transaction(
                    tid,
                    description=payee,
                    txn_date=txn_date,
                    amount=amount,
                    memo=memo,
                    ref_number=ref,
                    coa_account=coa,
                    attachment_path=self._attachment_path or ...,
                )
                if splits and self._ap_conn is not None:
                    business.replace_splits(self._ap_conn, tid, splits)
        except ValueError as exc:
            message_box_warning_ok(
                self,
                "Cannot save",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; fix the value and try again.",
            )
            return False
        self._update_balance_label()
        self._update_nav_buttons()
        self.transactionSaved.emit()
        if reset:
            self._browse_index = None
            self._load_blank()
            self._update_nav_buttons()
        return True

    def _on_delete(self) -> None:
        if self._db is None or self._browse_index is None or not self._browse_ids:
            return
        tid = self._browse_ids[self._browse_index]
        txn = self._db.get_transaction(tid)
        if txn is None:
            return
        d = dict(txn)
        amt = float(d.get("amount") or 0)
        desc = (d.get("description") or "").strip() or f"#{tid}"
        date_s = (d.get("txn_date") or "").strip()
        ans = message_box_question_yes_no(
            self,
            "Delete check?",
            f"Permanently delete this check?\n\n"
            f"  Date: {date_s}\n"
            f"  Payee: {escape_ampersand_for_qt(desc)}\n"
            f"  Amount: ${abs(amt):,.2f}\n\n"
            "This cannot be undone.",
            yes_tip="Delete this check permanently.",
            no_tip="Cancel.",
        )
        if not ans:
            return
        try:
            self._db.delete_transaction(tid)
        except ValueError as exc:
            message_box_warning_ok(
                self,
                "Cannot delete",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; void the GL posting first if posted.",
            )
            return
        prev_idx = self._browse_index
        self._reload_browse_list()
        if self._browse_ids:
            self._browse_index = min(prev_idx, len(self._browse_ids) - 1)
        else:
            self._browse_index = None
        self._load_current()
        self._update_balance_label()
        self.transactionSaved.emit()

    def _update_balance_label(self) -> None:
        if self._db is None or self._current_account_id is None:
            self._lbl_balance.setText("")
            return
        try:
            txns = self._db.list_transactions(self._current_account_id)
            bal = sum(float(t["amount"] or 0) for t in txns)
            self._lbl_balance.setText(f"{bal:,.2f}")
            color = "#C0392B" if bal < 0 else _CHK_TEXT
            self._lbl_balance.setStyleSheet(
                f"font-size: 16px; font-weight: bold; color: {color}; "
                "background: transparent; border: none;"
            )
        except Exception:
            self._lbl_balance.setText("")

    def reload(self) -> None:
        """Called by main window after external changes (e.g. CSV import)."""
        self._reload_browse_list()
        self._update_balance_label()
        self._update_nav_buttons()

    def refresh_accounts(self) -> None:
        """Rebuild the bank account combo (e.g. after Manage Accounts)."""
        self._refresh_accounts()

    def refresh_coa(self, coa_list: list[str]) -> None:
        """Update the COA dropdown options in all expense rows."""
        self._coa_list = list(coa_list or [])
        if not self._coa_list:
            self._coa_list = self._load_coa_labels()
        current_accts = [
            _combo_text(self._exp_table.cellWidget(r, _COL_ACCOUNT), placeholders=(_ACCOUNT_PLACEHOLDER,))
            if isinstance(self._exp_table.cellWidget(r, _COL_ACCOUNT), QComboBox)
            else ""
            for r in range(self._N_EXPENSE_ROWS)
        ]
        for r in range(self._N_EXPENSE_ROWS):
            w = self._exp_table.cellWidget(r, _COL_ACCOUNT)
            if not isinstance(w, QComboBox):
                continue
            w.blockSignals(True)
            w.clear()
            w.addItem(_ACCOUNT_PLACEHOLDER, "")
            for label in self._coa_list:
                w.addItem(escape_ampersand_for_qt(label), label)
            _set_combo_text(w, current_accts[r])
            w.blockSignals(False)

    def navigate_to_transaction(self, txn_id: int) -> None:
        """Jump directly to *txn_id* — called from the Bank Register 'Open in Checks' context menu."""
        if self._db is None:
            return
        txn = self._db.get_transaction(txn_id)
        if txn is not None:
            aid = coerce_combo_int_id(dict(txn).get("bank_account_id"))
            if aid is not None and aid != self._current_account_id:
                ix = combo_index_for_int_user_data(self._acct_combo, aid)
                if ix is not None:
                    self._acct_combo.setCurrentIndex(ix)
        self._reload_browse_list()
        if txn_id in self._browse_ids:
            self._browse_index = self._browse_ids.index(txn_id)
            self._load_current()
            return
        # Deposits / other signs are not in the check browse list; still show the row.
        if txn is not None:
            self._browse_index = None
            self._loading = True
            try:
                self._load_txn(dict(txn))
            finally:
                self._loading = False
            self._update_nav_buttons()
