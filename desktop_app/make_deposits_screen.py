"""Make Deposits — QuickBooks Pro Desktop deposit form + Payments to Deposit picker.

Undeposited customer payments (Receive Payments → ``ar_payments.bank_account_id`` empty)
are listed in the Payments to Deposit popup. Selected rows plus optional extra lines post
into the chosen bank account (for example CHASE BANK).
"""

from __future__ import annotations

import os
import sqlite3
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
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
    QVBoxLayout,
    QWidget,
)

from desktop_app.flexible_date import configure_qdate_edit_us, format_iso_to_us_display
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

_DEP_CANVAS = "#E8ECF1"
_DEP_PAPER = "#FFFFFF"
_DEP_PANEL = "#F4F7FA"
_DEP_STRIPE = "#D0E6F4"
_DEP_CAPTION = "#4A5560"
_DEP_GRID = "#C0C8D0"
_DEP_HEADER = "#D8DEE6"
_DEP_TEXT = "#1A1A1A"
_DEP_TITLE = "#5B6770"
_DEP_ACCENT = "#2563A8"
WORKFLOW_INPUT_BG = "#FFFFFF"
WORKFLOW_CONTROL_FACE = "#F7F8FA"
WORKFLOW_CONTROL_HOVER = "#E4EEF7"
WORKFLOW_CONTROL_PRESSED = "#C9D8EC"
_STRIP_BTN_OUTLINE = "#B4BCC6"
_TOP_STRIP_RADIUS_PX = 4
_TOP_STRIP_CAPTION_FONT_PX = 10
_TOP_STRIP_BODY_FONT_PX = 12
_FIELD_HEIGHT_PX = 22
_TOOLBAR_BTN_HEIGHT_PX = 24
_FOOTER_BTN_HEIGHT_PX = 26
_LINE_ROW_HEIGHT_PX = 22
_N_BLANK_ROWS = 8
_UNDEPOSITED_FUNDS_LABEL = business.UNDEPOSITED_FUNDS_LABEL
_PMT_TYPE = "PMT"

_ROLE_PAYMENT_ID = Qt.ItemDataRole.UserRole

_COL_RECEIVED = 0
_COL_FROM = 1
_COL_MEMO = 2
_COL_CHK = 3
_COL_METH = 4
_COL_AMT = 5

_PICK_CHECK = 0
_PICK_DATE = 1
_PICK_TIME = 2
_PICK_TYPE = 3
_PICK_NO = 4
_PICK_METH = 5
_PICK_NAME = 6
_PICK_AMT = 7


def _use_modal_dialogs() -> bool:
    return os.environ.get("QT_QPA_PLATFORM", "").lower() != "offscreen"


def _action_button_qss(*, primary: bool = False) -> str:
    r = _TOP_STRIP_RADIUS_PX
    if primary:
        return (
            f"QPushButton {{ background-color: {_DEP_ACCENT}; border: 1px solid {_DEP_ACCENT}; "
            f"border-radius: {r}px; color: #FFFFFF; "
            f"font-size: {_TOP_STRIP_BODY_FONT_PX}px; padding: 0 14px; font-weight: 600; }}"
            f"QPushButton:hover {{ background-color: #1D4F8C; border: 1px solid #1D4F8C; }}"
            f"QPushButton:pressed {{ background-color: #163E6E; }}"
            f"QPushButton:disabled {{ color: #D7E3F0; background-color: #8AA7C7; "
            f"border: 1px solid #8AA7C7; }}"
        )
    return (
        f"QPushButton {{ background-color: {WORKFLOW_CONTROL_FACE}; border: 1px solid {_STRIP_BTN_OUTLINE}; "
        f"border-radius: {r}px; color: {_DEP_TEXT}; "
        f"font-size: {_TOP_STRIP_BODY_FONT_PX}px; padding: 0 12px; }}"
        f"QPushButton:hover {{ background-color: {WORKFLOW_CONTROL_HOVER}; }}"
        f"QPushButton:pressed {{ background-color: {WORKFLOW_CONTROL_PRESSED}; }}"
        f"QPushButton:disabled {{ color: {DISABLED_FG}; background-color: {WORKFLOW_CONTROL_FACE}; }}"
    )


def _input_qss(widget: str = "QLineEdit") -> str:
    return (
        f"{widget} {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_DEP_GRID}; "
        f"padding: 2px 6px; color: {_DEP_TEXT}; font-size: {_TOP_STRIP_BODY_FONT_PX}px; }}"
    )


def _zebra_cell_qss(widget: str, row: int) -> str:
    bg = _DEP_STRIPE if row % 2 else WORKFLOW_INPUT_BG
    return (
        f"{widget} {{ background-color: {bg}; border: none; "
        f"padding: 1px 4px; color: {_DEP_TEXT}; font-size: {_TOP_STRIP_BODY_FONT_PX}px; }}"
        f"{widget}:focus {{ background-color: {WORKFLOW_INPUT_BG}; }}"
    )


def _blank_zero_spin(s: QDoubleSpinBox) -> QDoubleSpinBox:
    """Empty line cells stay blank at 0. Qt ignores an empty specialValueText, so a space stands in."""
    s.setSpecialValueText(" ")
    return s


def _money_spin(*, row: int, blank_zero: bool = True) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(0.0, 999_999_999.99)
    s.setDecimals(2)
    s.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
    s.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    s.setStyleSheet(_zebra_cell_qss("QDoubleSpinBox", row))
    if blank_zero:
        _blank_zero_spin(s)
    return s


def _light_form_palette() -> QPalette:
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(_DEP_PAPER))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(_DEP_TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(WORKFLOW_INPUT_BG))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(_DEP_STRIPE))
    pal.setColor(QPalette.ColorRole.Text, QColor(_DEP_TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(WORKFLOW_CONTROL_FACE))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(_DEP_TEXT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(_DEP_ACCENT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(_DEP_CAPTION))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(_DEP_PANEL))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(_DEP_TEXT))
    return pal


def _readonly_item(text: str, *, align_right: bool = False) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    it.setForeground(QColor(_DEP_TEXT))
    if align_right:
        it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return it


def _fmt_money(value: float) -> str:
    return f"{value:,.2f}"


def _payment_as_dict(row) -> dict:
    d = dict(row)
    return {
        "id": int(d["id"]),
        "payment_date": (d.get("payment_date") or "").strip(),
        "method": (d.get("method") or "").strip(),
        "reference": (d.get("reference") or "").strip(),
        "memo": (d.get("memo") or "").strip(),
        "amount": float(d.get("amount") or 0.0),
        "customer_name": (d.get("customer_name") or "").strip(),
        "customer_id": d.get("customer_id"),
    }


class PaymentsToDepositDialog(QDialog):
    """QB Pro Payments to Deposit picker: undeposited AR payments only."""

    _COLS = ("✓", "DATE", "TIME", "TYPE", "NO.", "PAYMENT METHOD", "NAME", "AMOUNT")

    def __init__(
        self,
        payments: list,
        parent: Optional[QWidget] = None,
        *,
        selected_ids: Optional[set[int]] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Payments to Deposit")
        self.setObjectName("paymentsToDepositDialog")
        self.setModal(True)
        self.setMinimumSize(820, 480)
        self._all_payments = [_payment_as_dict(r) for r in payments]
        self._selected_ids: set[int] = set(selected_ids or ())
        self._row_checks: list[QCheckBox] = []
        self._visible: list[dict] = []
        self.setPalette(_light_form_palette())
        self.setAutoFillBackground(True)
        self.setStyleSheet(
            f"PaymentsToDepositDialog {{ background-color: {_DEP_CANVAS}; color: {_DEP_TEXT}; }}"
        )
        self._build_ui()
        self._rebuild_table()

    def _style_button(self, b: QPushButton, *, primary: bool = False) -> None:
        b.setStyleSheet(_action_button_qss(primary=primary))
        b.setFixedHeight(_FOOTER_BTN_HEIGHT_PX)
        b.setAutoDefault(False)
        b.setDefault(False)

    def _caption(self, text: str) -> QLabel:
        cap = QLabel(text)
        cap.setStyleSheet(
            f"color: {_DEP_CAPTION}; font-size: {_TOP_STRIP_CAPTION_FONT_PX}px; "
            "font-weight: bold; letter-spacing: 0.04em; background: transparent; border: none;"
        )
        return cap

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        view = QFrame()
        view.setObjectName("paymentsToDepositViewBand")
        view.setStyleSheet(
            f"QFrame#paymentsToDepositViewBand {{ background-color: {_DEP_PAPER}; "
            f"border: 1px solid {_DEP_GRID}; border-radius: 6px; }}"
        )
        vl = QHBoxLayout(view)
        vl.setContentsMargins(10, 8, 10, 8)
        vl.setSpacing(16)

        self._method_view = QComboBox()
        self._method_view.setObjectName("paymentsToDepositMethodView")
        self._method_view.setMinimumWidth(140)
        methods = ["All types"]
        seen: set[str] = set()
        for p in self._all_payments:
            m = p["method"] or "Other"
            if m not in seen:
                seen.add(m)
                methods.append(m)
        self._method_view.addItems(methods)
        self._method_view.setToolTip("Show payments of one payment method, or all types.")

        self._sort_by = QComboBox()
        self._sort_by.setObjectName("paymentsToDepositSortBy")
        self._sort_by.addItems(["Payment Method", "Date", "Amount", "Name"])
        self._sort_by.setCurrentText("Payment Method")
        self._sort_by.setToolTip("Sort the undeposited payments list.")

        method_wrap = QWidget()
        method_wrap.setObjectName("makeDepositsMetaField")
        ml = QVBoxLayout(method_wrap)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(1)
        ml.addWidget(self._caption("VIEW PAYMENT METHOD TYPE"))
        self._method_view.setFixedHeight(_FIELD_HEIGHT_PX)
        self._method_view.setStyleSheet(_input_qss("QComboBox"))
        ml.addWidget(self._method_view)

        sort_wrap = QWidget()
        sort_wrap.setObjectName("makeDepositsMetaField")
        sl = QVBoxLayout(sort_wrap)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(1)
        sl.addWidget(self._caption("SORT PAYMENTS BY"))
        self._sort_by.setFixedHeight(_FIELD_HEIGHT_PX)
        self._sort_by.setStyleSheet(_input_qss("QComboBox"))
        sl.addWidget(self._sort_by)

        self._views_link = QLabel('<a href="#views">What are payment method views?</a>')
        self._views_link.setObjectName("paymentsToDepositViewsLink")
        self._views_link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self._views_link.setOpenExternalLinks(False)
        self._views_link.setStyleSheet(
            f"color: {_DEP_ACCENT}; font-size: 11px; background: transparent;"
        )
        self._views_link.linkActivated.connect(self._on_views_help)

        vl.addWidget(method_wrap)
        vl.addWidget(sort_wrap)
        vl.addWidget(self._views_link, 0, Qt.AlignmentFlag.AlignBottom)
        vl.addStretch(1)
        outer.addWidget(view)

        sel_cap = self._caption("SELECT PAYMENTS TO DEPOSIT")
        outer.addWidget(sel_cap)

        self._table = QTableWidget(0, len(self._COLS))
        self._table.setObjectName("paymentsToDepositTable")
        self._table.setHorizontalHeaderLabels(self._COLS)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hh = self._table.horizontalHeader()
        hh.setStretchLastSection(True)
        hh.setSectionResizeMode(_PICK_CHECK, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(_PICK_CHECK, 36)
        self._table.setStyleSheet(
            f"QTableWidget#paymentsToDepositTable {{"
            f" background-color: {WORKFLOW_INPUT_BG};"
            f" alternate-background-color: {_DEP_STRIPE};"
            f" color: {_DEP_TEXT};"
            f" gridline-color: {_DEP_GRID};"
            f" border: 1px solid {_DEP_GRID};"
            " }"
            f"QHeaderView::section {{"
            f" background-color: {_DEP_HEADER};"
            f" color: {_DEP_CAPTION};"
            f" padding: 4px; border: 1px solid {_DEP_GRID};"
            " font-weight: bold; font-size: 11px;"
            " }"
        )
        outer.addWidget(self._table, 1)

        foot = QHBoxLayout()
        foot.setSpacing(10)
        self._lbl_status = QLabel("0 of 0 payments selected for deposit")
        self._lbl_status.setObjectName("paymentsToDepositStatus")
        self._lbl_status.setStyleSheet(
            f"color: {_DEP_TEXT}; font-size: 12px; background: transparent;"
        )
        self._btn_select_all = QPushButton("Select All")
        self._btn_select_none = QPushButton("Select None")
        for b in (self._btn_select_all, self._btn_select_none):
            self._style_button(b)
        foot.addWidget(self._lbl_status)
        foot.addWidget(self._btn_select_all)
        foot.addWidget(self._btn_select_none)
        foot.addStretch(1)
        sub_col = QVBoxLayout()
        sub_col.setContentsMargins(0, 0, 0, 0)
        sub_col.setSpacing(0)
        sub_cap = self._caption("PAYMENTS SUBTOTAL")
        sub_cap.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._lbl_subtotal = QLabel("0.00")
        self._lbl_subtotal.setObjectName("paymentsToDepositSubtotal")
        self._lbl_subtotal.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._lbl_subtotal.setStyleSheet(
            f"color: {_DEP_TEXT}; font-size: 16px; font-weight: 700; background: transparent;"
        )
        sub_col.addWidget(sub_cap)
        sub_col.addWidget(self._lbl_subtotal)
        foot.addLayout(sub_col)
        outer.addLayout(foot)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self._btn_ok = QPushButton("OK")
        self._btn_ok.setObjectName("paymentsToDepositOk")
        self._btn_cancel = QPushButton("Cancel")
        self._btn_help = QPushButton("Help")
        self._style_button(self._btn_ok, primary=True)
        self._style_button(self._btn_cancel)
        self._style_button(self._btn_help)
        self._btn_ok.setDefault(True)
        btns.addWidget(self._btn_ok)
        btns.addWidget(self._btn_cancel)
        btns.addWidget(self._btn_help)
        btns.addStretch(1)
        outer.addLayout(btns)

        self._method_view.currentIndexChanged.connect(self._rebuild_table)
        self._sort_by.currentIndexChanged.connect(self._rebuild_table)
        self._btn_select_all.clicked.connect(self._on_select_all)
        self._btn_select_none.clicked.connect(self._on_select_none)
        self._btn_ok.clicked.connect(self.accept)
        self._btn_cancel.clicked.connect(self.reject)
        self._btn_help.clicked.connect(self._on_help)

    def _on_views_help(self, _href: str = "") -> None:
        message_box_information_ok(
            self,
            "Payment method views",
            "View payment method type shows undeposited payments of one method (Check, Cash, "
            "Credit Card, and so on) or all types. Sort payments by changes the order in the list. "
            "These filters do not post a deposit.",
            ok_tip="Close; pick payments, then OK.",
        )

    def _on_help(self) -> None:
        message_box_information_ok(
            self,
            "Payments to Deposit",
            "Select the customer payments sitting in Undeposited Funds to include in this bank "
            "deposit. OK returns them to Make Deposits. They do not hit the bank until you save "
            "the deposit.",
            ok_tip="Close; check the payments to include, then OK.",
        )

    def _filtered_sorted(self) -> list[dict]:
        view = self._method_view.currentText()
        rows = list(self._all_payments)
        if view and view != "All types":
            rows = [p for p in rows if (p["method"] or "Other") == view]
        key = self._sort_by.currentText()
        if key == "Date":
            rows.sort(key=lambda p: (p["payment_date"], p["id"]))
        elif key == "Amount":
            rows.sort(key=lambda p: (p["amount"], p["id"]))
        elif key == "Name":
            rows.sort(key=lambda p: ((p["customer_name"] or "").lower(), p["id"]))
        else:
            rows.sort(key=lambda p: ((p["method"] or "").lower(), p["payment_date"], p["id"]))
        return rows

    def _rebuild_table(self) -> None:
        self._visible = self._filtered_sorted()
        self._row_checks = []
        self._table.setRowCount(len(self._visible))
        for i, p in enumerate(self._visible):
            self._table.setRowHeight(i, _LINE_ROW_HEIGHT_PX)
            cb = QCheckBox()
            cb.setChecked(int(p["id"]) in self._selected_ids)
            cb.stateChanged.connect(self._on_check_changed)
            self._row_checks.append(cb)
            wrap = QWidget()
            lay = QHBoxLayout(wrap)
            lay.setContentsMargins(8, 0, 0, 0)
            lay.addWidget(cb)
            self._table.setCellWidget(i, _PICK_CHECK, wrap)
            date_s = format_iso_to_us_display(p["payment_date"]) or p["payment_date"]
            self._table.setItem(i, _PICK_DATE, _readonly_item(date_s))
            self._table.setItem(i, _PICK_TIME, _readonly_item(""))
            self._table.setItem(i, _PICK_TYPE, _readonly_item(_PMT_TYPE))
            self._table.setItem(i, _PICK_NO, _readonly_item(p["reference"]))
            self._table.setItem(i, _PICK_METH, _readonly_item(p["method"]))
            name_it = _readonly_item(p["customer_name"])
            name_it.setData(_ROLE_PAYMENT_ID, int(p["id"]))
            self._table.setItem(i, _PICK_NAME, name_it)
            self._table.setItem(
                i, _PICK_AMT, _readonly_item(_fmt_money(p["amount"]), align_right=True)
            )
        self._sync_status()

    def _on_check_changed(self, _state: int = 0) -> None:
        visible_ids = {int(p["id"]) for p in self._visible}
        self._selected_ids -= visible_ids
        for cb, p in zip(self._row_checks, self._visible):
            if cb.isChecked():
                self._selected_ids.add(int(p["id"]))
        self._sync_status()

    def _on_select_all(self) -> None:
        for cb in self._row_checks:
            cb.setChecked(True)
        self._on_check_changed()

    def _on_select_none(self) -> None:
        for cb in self._row_checks:
            cb.setChecked(False)
        self._on_check_changed()

    def _sync_status(self) -> None:
        n = len(self._selected_ids)
        total = len(self._all_payments)
        self._lbl_status.setText(f"{n} of {total} payments selected for deposit")
        sub = sum(p["amount"] for p in self._all_payments if int(p["id"]) in self._selected_ids)
        self._lbl_subtotal.setText(_fmt_money(sub))

    def selected_rows(self) -> list[dict]:
        wanted = self._selected_ids
        return [p for p in self._all_payments if int(p["id"]) in wanted]


class MakeDepositsScreen(QWidget):
    """Make Deposits header, payment lines, cash back, post into a bank account."""

    depositPosted = Signal()

    _COLS = ("RECEIVED FROM", "FROM ACCOUNT", "MEMO", "CHK NO.", "PMT METH.", "AMOUNT")

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
        self._payments_dialog: Optional[PaymentsToDepositDialog] = None
        self._last_deposit_txn_id: Optional[int] = None
        self.setWindowTitle("Make Deposits")
        self.setMinimumSize(960, 640)
        self.setToolTip(
            "Make Deposits: pick undeposited customer payments and put them in a bank account. "
            "Same company .db (File → Backup / Restore, probooks.backup)."
        )
        self._build_ui()
        self._load_bank_accounts_combo()
        self._rebuild_grid([])

    def _style_button(self, b: QPushButton, *, primary: bool = False, height: int = _TOOLBAR_BTN_HEIGHT_PX) -> None:
        b.setStyleSheet(_action_button_qss(primary=primary))
        b.setFixedHeight(height)
        b.setAutoDefault(False)
        b.setDefault(False)

    def _caption(self, text: str) -> QLabel:
        cap = QLabel(text)
        cap.setStyleSheet(
            f"color: {_DEP_CAPTION}; font-size: {_TOP_STRIP_CAPTION_FONT_PX}px; "
            "font-weight: bold; letter-spacing: 0.04em; background: transparent; border: none;"
        )
        return cap

    def _stacked_field(self, caption: str, editor: QWidget) -> QWidget:
        wrap = QWidget()
        wrap.setObjectName("makeDepositsMetaField")
        wrap.setAutoFillBackground(True)
        pal = wrap.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(_DEP_PAPER))
        pal.setColor(QPalette.ColorRole.WindowText, QColor(_DEP_CAPTION))
        wrap.setPalette(pal)
        wrap.setStyleSheet(
            f"QWidget#makeDepositsMetaField {{ background-color: {_DEP_PAPER}; border: none; }}"
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
            f"MakeDepositsScreen {{ background-color: {_DEP_CANVAS}; color: {_DEP_TEXT}; }}"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 4, 6, 4)
        outer.setSpacing(4)
        self._build_toolbar(outer)
        self._build_header(outer)
        self._build_grid(outer)
        self._build_footer(outer)

    def _build_toolbar(self, play: QVBoxLayout) -> None:
        bar = QFrame()
        bar.setObjectName("makeDepositsToolbar")
        bar.setStyleSheet(
            f"QFrame#makeDepositsToolbar {{ background-color: {_DEP_PANEL}; "
            f"border: 1px solid {_DEP_GRID}; border-radius: 4px; }}"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(4)
        self._btn_prev = QPushButton("Previous")
        self._btn_next = QPushButton("Next")
        self._btn_save = QPushButton("Save")
        self._btn_print = QPushButton("Print")
        self._btn_payments = QPushButton("Payments")
        self._btn_payments.setObjectName("makeDepositsPaymentsButton")
        self._btn_history = QPushButton("History")
        self._btn_attach = QPushButton("Attach")
        self._btn_prev.setToolTip("Browse saved deposits is not wired yet.")
        self._btn_next.setToolTip("Browse saved deposits is not wired yet.")
        self._btn_save.setToolTip("Save this deposit to the selected bank account.")
        self._btn_print.setToolTip("Print this deposit is not wired yet. Save writes the bank deposit.")
        self._btn_payments.setToolTip(
            "Open Payments to Deposit and pick undeposited customer payments."
        )
        self._btn_history.setToolTip("Deposit history is not wired yet.")
        self._btn_attach.setToolTip("Attachments on deposits are not wired yet.")
        self._btn_prev.setEnabled(False)
        self._btn_next.setEnabled(False)
        self._btn_print.setEnabled(False)
        self._btn_history.setEnabled(False)
        self._btn_attach.setEnabled(False)
        print_menu = QMenu(self._btn_print)
        act_print = print_menu.addAction("Print")
        act_print.setEnabled(False)
        act_preview = print_menu.addAction("Print Preview")
        act_preview.setEnabled(False)
        self._btn_print.setMenu(print_menu)
        for b in (
            self._btn_prev,
            self._btn_next,
            self._btn_save,
            self._btn_print,
            self._btn_payments,
            self._btn_history,
            self._btn_attach,
        ):
            self._style_button(b)
            lay.addWidget(b)
        lay.addStretch(1)
        play.addWidget(bar)
        self._btn_save.clicked.connect(self._on_save_close)
        self._btn_payments.clicked.connect(self._on_payments_clicked)

    def _build_header(self, play: QVBoxLayout) -> None:
        form = QFrame()
        form.setObjectName("makeDepositsHeaderBand")
        form.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        form.setStyleSheet(
            f"QFrame#makeDepositsHeaderBand {{ background-color: {_DEP_PAPER}; "
            f"border: 1px solid #B7C9DE; border-radius: 6px; }}"
        )
        hb = QVBoxLayout(form)
        hb.setContentsMargins(10, 6, 10, 8)
        hb.setSpacing(6)

        title = QLabel("Make Deposits")
        title.setObjectName("makeDepositsTitle")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: bold; color: {_DEP_TITLE}; background: transparent;"
        )
        hb.addWidget(title)

        self._deposit_to = QComboBox()
        self._deposit_to.setObjectName("makeDepositsDepositTo")
        self._deposit_to.setMinimumWidth(220)
        self._deposit_to.setToolTip("Bank account this deposit goes to (for example CHASE BANK).")

        self._dep_date = QDateEdit()
        self._dep_date.setObjectName("makeDepositsDate")
        configure_qdate_edit_us(self._dep_date)
        self._dep_date.setDate(QDate.currentDate())
        self._dep_date.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._dep_date.setToolTip("Deposit date.")

        self._dep_memo = QLineEdit()
        self._dep_memo.setObjectName("makeDepositsMemo")
        self._dep_memo.setToolTip("Memo stored with this bank deposit.")

        fields = QHBoxLayout()
        fields.setSpacing(10)
        fields.addWidget(self._stacked_field("DEPOSIT TO", self._deposit_to), 2)
        fields.addWidget(self._stacked_field("DATE", self._dep_date), 1)
        fields.addWidget(self._stacked_field("MEMO", self._dep_memo), 3)
        hb.addLayout(fields)
        play.addWidget(form)

    def _build_grid(self, play: QVBoxLayout) -> None:
        wrap = QFrame()
        wrap.setObjectName("makeDepositsGridWrap")
        wrap.setStyleSheet(
            f"QFrame#makeDepositsGridWrap {{ background: {_DEP_PAPER}; border: none; }}"
        )
        gl = QVBoxLayout(wrap)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(0)
        self._table = QTableWidget(_N_BLANK_ROWS, len(self._COLS))
        self._table.setObjectName("makeDepositsTable")
        self._table.setHorizontalHeaderLabels(self._COLS)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        hh = self._table.horizontalHeader()
        hh.setStretchLastSection(False)
        for col in range(len(self._COLS)):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(_COL_AMT, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setStyleSheet(
            f"QTableWidget#makeDepositsTable {{"
            f" background-color: {WORKFLOW_INPUT_BG};"
            f" alternate-background-color: {_DEP_STRIPE};"
            f" color: {_DEP_TEXT};"
            f" gridline-color: {_DEP_GRID};"
            f" border: 1px solid {_DEP_GRID};"
            " }"
            f"QHeaderView::section {{"
            f" background-color: {_DEP_HEADER};"
            f" color: {_DEP_CAPTION};"
            f" padding: 4px; border: 1px solid {_DEP_GRID};"
            " font-weight: bold; font-size: 11px;"
            " }"
        )
        gl.addWidget(self._table, 1)
        play.addWidget(wrap, 1)

    def _build_footer(self, play: QVBoxLayout) -> None:
        footer = QFrame()
        footer.setObjectName("makeDepositsFooterBand")
        footer.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        footer.setStyleSheet(
            f"QFrame#makeDepositsFooterBand {{ background-color: {_DEP_PANEL}; "
            f"border: 1px solid {_DEP_GRID}; border-radius: 4px; }}"
        )
        bot = QHBoxLayout(footer)
        bot.setContentsMargins(8, 6, 8, 6)
        bot.setSpacing(16)

        cash = QFrame()
        cash.setObjectName("makeDepositsCashBack")
        cash.setStyleSheet(
            f"QFrame#makeDepositsCashBack {{ background: {_DEP_PAPER}; "
            f"border: 1px solid {_DEP_GRID}; border-radius: 4px; }}"
        )
        cl = QVBoxLayout(cash)
        cl.setContentsMargins(8, 6, 8, 6)
        cl.setSpacing(4)
        hint = QLabel(
            "To get cash back from this deposit, enter the amount below. Indicate the account "
            "where you want this money to go, such as your Petty Cash account."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color: {_DEP_CAPTION}; font-size: 11px; background: transparent;"
        )
        cl.addWidget(hint)
        cash_row = QHBoxLayout()
        cash_row.setSpacing(8)
        self._cash_account = QComboBox()
        self._cash_account.setObjectName("makeDepositsCashBackAccount")
        self._cash_account.setMinimumWidth(160)
        self._cash_account.setToolTip("Account that receives cash back from this deposit.")
        self._cash_memo = QLineEdit()
        self._cash_memo.setObjectName("makeDepositsCashBackMemo")
        self._cash_memo.setToolTip("Memo for the cash-back line.")
        self._cash_amount = QDoubleSpinBox()
        self._cash_amount.setObjectName("makeDepositsCashBackAmount")
        self._cash_amount.setRange(0.0, 999_999_999.99)
        self._cash_amount.setDecimals(2)
        self._cash_amount.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self._cash_amount.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._cash_amount.setStyleSheet(_input_qss("QDoubleSpinBox"))
        _blank_zero_spin(self._cash_amount)
        self._cash_amount.valueChanged.connect(self._refresh_totals)
        cash_row.addWidget(self._stacked_field("CASH BACK GOES TO", self._cash_account), 2)
        cash_row.addWidget(self._stacked_field("CASH BACK MEMO", self._cash_memo), 2)
        cash_row.addWidget(self._stacked_field("CASH BACK AMOUNT", self._cash_amount), 1)
        cl.addLayout(cash_row)
        bot.addWidget(cash, 3)

        totals = QVBoxLayout()
        totals.setSpacing(2)
        self._lbl_subtotal = QLabel("0.00")
        self._lbl_subtotal.setObjectName("makeDepositsSubtotal")
        self._lbl_total = QLabel("0.00")
        self._lbl_total.setObjectName("makeDepositsTotal")
        for cap, lab in (
            ("DEPOSIT SUBTOTAL", self._lbl_subtotal),
            ("DEPOSIT TOTAL", self._lbl_total),
        ):
            row = QHBoxLayout()
            c = self._caption(cap)
            lab.setAlignment(Qt.AlignmentFlag.AlignRight)
            lab.setStyleSheet(
                f"color: {_DEP_TEXT}; font-size: 14px; font-weight: 700; background: transparent;"
            )
            lab.setMinimumWidth(100)
            row.addWidget(c)
            row.addStretch(1)
            row.addWidget(lab)
            totals.addLayout(row)
        bot.addLayout(totals)

        self._btn_save_close = QPushButton("Save && Close")
        self._btn_save_new = QPushButton("Save && New")
        self._btn_clear = QPushButton("Clear")
        self._btn_save_close.setToolTip(
            "Save this deposit to the selected bank and clear the form (tab analog of QuickBooks Save & Close)."
        )
        self._btn_save_new.setToolTip("Save this deposit, then clear the form for a new deposit.")
        self._btn_clear.setToolTip("Clear the form without saving.")
        self._style_button(self._btn_save_close, height=_FOOTER_BTN_HEIGHT_PX)
        self._style_button(self._btn_save_new, primary=True, height=_FOOTER_BTN_HEIGHT_PX)
        self._style_button(self._btn_clear, height=_FOOTER_BTN_HEIGHT_PX)
        bot.addWidget(self._btn_save_close)
        bot.addWidget(self._btn_save_new)
        bot.addWidget(self._btn_clear)
        play.addWidget(footer)

        self._btn_save_close.clicked.connect(self._on_save_close)
        self._btn_save_new.clicked.connect(self._on_save_new)
        self._btn_clear.clicked.connect(self._on_clear)
        self._fill_cash_back_accounts()

    def _cell_line(self, row: int) -> QLineEdit:
        le = QLineEdit()
        le.setPlaceholderText("")
        le.setStyleSheet(_zebra_cell_qss("QLineEdit", row))
        return le

    def _fill_row(self, row: int, payment: Optional[dict] = None) -> None:
        self._table.setRowHeight(row, _LINE_ROW_HEIGHT_PX)
        received = self._cell_line(row)
        from_acct = self._cell_line(row)
        memo = self._cell_line(row)
        chk = self._cell_line(row)
        meth = self._cell_line(row)
        amt = _money_spin(row=row, blank_zero=True)
        amt.valueChanged.connect(self._refresh_totals)
        if payment is not None:
            received.setText(payment.get("customer_name") or "")
            from_acct.setText(_UNDEPOSITED_FUNDS_LABEL)
            memo.setText(payment.get("memo") or "")
            chk.setText(payment.get("reference") or "")
            meth.setText(payment.get("method") or "")
            amt.setValue(float(payment.get("amount") or 0.0))
            received.setReadOnly(True)
            from_acct.setReadOnly(True)
            pid = int(payment["id"])
            received.setProperty("paymentId", pid)
        else:
            received.setProperty("paymentId", None)
        self._table.setCellWidget(row, _COL_RECEIVED, received)
        self._table.setCellWidget(row, _COL_FROM, from_acct)
        self._table.setCellWidget(row, _COL_MEMO, memo)
        self._table.setCellWidget(row, _COL_CHK, chk)
        self._table.setCellWidget(row, _COL_METH, meth)
        self._table.setCellWidget(row, _COL_AMT, amt)

    def _rebuild_grid(self, payments: list[dict]) -> None:
        n = max(len(payments) + _N_BLANK_ROWS, _N_BLANK_ROWS)
        self._table.setRowCount(n)
        for i in range(n):
            pay = payments[i] if i < len(payments) else None
            self._fill_row(i, pay)
        self._refresh_totals()

    def _load_bank_accounts_combo(self) -> None:
        current = coerce_combo_int_id(self._deposit_to.currentData())
        self._deposit_to.blockSignals(True)
        self._deposit_to.clear()
        self._deposit_to.addItem("", None)
        conn = self._ap_conn
        if conn is not None:
            try:
                rows = conn.execute(
                    "SELECT id, name FROM bank_accounts WHERE is_active = 1 ORDER BY name"
                ).fetchall()
            except sqlite3.Error:
                rows = []
            for r in rows:
                bid = coerce_combo_int_id(r["id"])
                if bid is None:
                    continue
                name = (r["name"] or "").strip() or f"Account #{bid}"
                self._deposit_to.addItem(name, bid)
        if current is not None:
            idx = self._deposit_to.findData(current)
            if idx >= 0:
                self._deposit_to.setCurrentIndex(idx)
        self._deposit_to.blockSignals(False)

    def _fill_cash_back_accounts(self) -> None:
        self._cash_account.blockSignals(True)
        self._cash_account.clear()
        self._cash_account.addItem("", "")
        names: list[str] = []
        conn = self._ap_conn
        if conn is not None:
            try:
                rows = conn.execute(
                    "SELECT account_number, account_name FROM coa_accounts "
                    "ORDER BY account_number"
                ).fetchall()
            except sqlite3.Error:
                rows = []
            for r in rows:
                label = f"{r['account_number']} {r['account_name']}".strip()
                if label:
                    names.append(label)
        if "Petty Cash" not in " ".join(names):
            names.insert(0, "Petty Cash")
        for n in names:
            self._cash_account.addItem(n, n)
        self._cash_account.blockSignals(False)

    def _undeposited(self) -> list:
        if self._ap_conn is None:
            return []
        try:
            return list(business.list_undeposited_ar_payments(self._ap_conn))
        except sqlite3.Error:
            return []

    def reload_undeposited(self) -> None:
        """Refresh bank list; leave the current deposit lines as-is."""
        self._load_bank_accounts_combo()
        self._fill_cash_back_accounts()

    def on_activated(self) -> None:
        """Called when the Make Deposits tab is shown."""
        self.reload_undeposited()
        if self._payment_ids_on_grid():
            return
        if not self._undeposited():
            return
        if _use_modal_dialogs():
            self._open_payments_dialog(modal=True)

    def _payment_ids_on_grid(self) -> set[int]:
        ids: set[int] = set()
        for row in range(self._table.rowCount()):
            w = self._table.cellWidget(row, _COL_RECEIVED)
            if w is None:
                continue
            raw = w.property("paymentId")
            pid = coerce_combo_int_id(raw)
            if pid is not None:
                ids.add(pid)
        return ids

    def _on_payments_clicked(self) -> None:
        self._open_payments_dialog(modal=True)

    def _open_payments_dialog(self, *, modal: bool = True) -> PaymentsToDepositDialog:
        dlg = PaymentsToDepositDialog(
            self._undeposited(),
            parent=self,
            selected_ids=self._payment_ids_on_grid(),
        )
        self._payments_dialog = dlg
        dlg.accepted.connect(lambda: self._apply_dialog_selection(dlg))
        if modal and _use_modal_dialogs():
            dlg.exec()
        return dlg

    def _apply_dialog_selection(self, dlg: PaymentsToDepositDialog) -> None:
        extras = self._collect_extra_lines()
        selected = dlg.selected_rows()
        self._rebuild_grid(selected)
        start = len(selected)
        for i, line in enumerate(extras):
            row = start + i
            if row >= self._table.rowCount():
                self._table.setRowCount(row + 1)
                self._fill_row(row, None)
            received = self._table.cellWidget(row, _COL_RECEIVED)
            from_acct = self._table.cellWidget(row, _COL_FROM)
            memo = self._table.cellWidget(row, _COL_MEMO)
            chk = self._table.cellWidget(row, _COL_CHK)
            meth = self._table.cellWidget(row, _COL_METH)
            amt = self._table.cellWidget(row, _COL_AMT)
            if isinstance(received, QLineEdit):
                received.setText(line.get("received_from") or "")
            if isinstance(from_acct, QLineEdit):
                from_acct.setText(line.get("from_account") or "")
            if isinstance(memo, QLineEdit):
                memo.setText(line.get("memo") or "")
            if isinstance(chk, QLineEdit):
                chk.setText(line.get("chk_no") or "")
            if isinstance(meth, QLineEdit):
                meth.setText(line.get("pmt_meth") or "")
            if isinstance(amt, QDoubleSpinBox):
                amt.setValue(float(line.get("amount") or 0.0))
        self._refresh_totals()

    def _line_amount(self, row: int) -> float:
        w = self._table.cellWidget(row, _COL_AMT)
        if isinstance(w, QDoubleSpinBox):
            return round(w.value(), 2)
        return 0.0

    def _line_text(self, row: int, col: int) -> str:
        w = self._table.cellWidget(row, col)
        if isinstance(w, QLineEdit):
            return w.text().strip()
        return ""

    def _collect_payment_ids(self) -> list[int]:
        ids: list[int] = []
        for row in range(self._table.rowCount()):
            if self._line_amount(row) <= 0.005:
                continue
            w = self._table.cellWidget(row, _COL_RECEIVED)
            if w is None:
                continue
            pid = coerce_combo_int_id(w.property("paymentId"))
            if pid is not None:
                ids.append(pid)
        return ids

    def _collect_extra_lines(self) -> list[dict]:
        lines: list[dict] = []
        for row in range(self._table.rowCount()):
            w = self._table.cellWidget(row, _COL_RECEIVED)
            pid = coerce_combo_int_id(w.property("paymentId")) if w is not None else None
            if pid is not None:
                continue
            amt = self._line_amount(row)
            received = self._line_text(row, _COL_RECEIVED)
            from_acct = self._line_text(row, _COL_FROM)
            memo = self._line_text(row, _COL_MEMO)
            chk = self._line_text(row, _COL_CHK)
            meth = self._line_text(row, _COL_METH)
            if amt <= 0.005 and not (received or from_acct or memo or chk or meth):
                continue
            if amt <= 0.005:
                continue
            lines.append(
                {
                    "received_from": received,
                    "from_account": from_acct,
                    "memo": memo,
                    "chk_no": chk,
                    "pmt_meth": meth,
                    "amount": amt,
                }
            )
        return lines

    def _refresh_totals(self, *_args) -> None:
        sub = 0.0
        for row in range(self._table.rowCount()):
            sub = round(sub + self._line_amount(row), 2)
        cash = round(self._cash_amount.value(), 2)
        self._lbl_subtotal.setText(_fmt_money(sub))
        self._lbl_total.setText(_fmt_money(round(sub - cash, 2)))

    def _selected_bank_id(self) -> Optional[int]:
        return coerce_combo_int_id(self._deposit_to.currentData())

    def _on_save_close(self) -> None:
        if self.sender() not in (self._btn_save_close, self._btn_save):
            return
        self._persist_deposit(reset=True)

    def _on_save_new(self) -> None:
        if self.sender() is not self._btn_save_new:
            return
        self._persist_deposit(reset=True)

    def _on_clear(self) -> None:
        self._reset_form()

    def _reset_form(self) -> None:
        self._dep_date.setDate(QDate.currentDate())
        self._dep_memo.clear()
        self._cash_amount.setValue(0.0)
        self._cash_memo.clear()
        self._cash_account.setCurrentIndex(0)
        self._rebuild_grid([])
        self._load_bank_accounts_combo()

    def _persist_deposit(self, *, reset: bool) -> bool:
        if self._ap_conn is None:
            message_box_information_ok(
                self,
                "Make Deposits",
                "Open a company database to post deposits.",
                ok_tip="Close; use File → Open company… then try again.",
            )
            return False
        bank_id = self._selected_bank_id()
        if bank_id is None:
            message_box_warning_ok(
                self,
                "Make Deposits",
                "Choose a Deposit To bank account.",
                ok_tip="Pick the bank (for example CHASE BANK), then save.",
            )
            return False
        payment_ids = self._collect_payment_ids()
        extra = self._collect_extra_lines()
        deposit_date = self._dep_date.date().toString("yyyy-MM-dd")
        memo = self._dep_memo.text().strip()
        cash_acct = (self._cash_account.currentText() or "").strip()
        cash_amt = round(self._cash_amount.value(), 2)
        cash_memo = self._cash_memo.text().strip()
        try:
            result = business.deposit_ar_payments(
                self._ap_conn,
                payment_ids,
                bank_id,
                deposit_date,
                memo=memo,
                extra_lines=extra,
                cash_back_account=cash_acct,
                cash_back_amount=cash_amt,
                cash_back_memo=cash_memo,
            )
        except (sqlite3.Error, ValueError, TypeError) as exc:
            message_box_critical_ok(
                self,
                "Make Deposits",
                str(exc),
                ok_tip="Close; fix the deposit and try again.",
            )
            return False

        bank_db = self._bank_db
        if bank_db is not None:
            try:
                n_pay = len(result["payment_ids"])
                desc = f"Deposit — {n_pay} payment(s)" if n_pay else "Deposit"
                tid = bank_db.insert_manual_transaction(
                    bank_id,
                    deposit_date,
                    float(result["deposit_total"]),
                    description=desc,
                    ref_number="",
                    memo=memo or "Make Deposits",
                    coa_account=_UNDEPOSITED_FUNDS_LABEL,
                )
                self._last_deposit_txn_id = int(tid)
            except (sqlite3.Error, OSError, ValueError, TypeError) as exc:
                message_box_warning_ok(
                    self,
                    "Make Deposits",
                    "Payments were marked deposited, but the bank register line failed: "
                    + str(exc),
                    ok_tip="Add a matching bank deposit manually or fix the error and retry.",
                )
        bank_name = result.get("bank_name") or "the selected bank"
        message_box_information_ok(
            self,
            "Make Deposits",
            f"Deposited {_fmt_money(float(result['deposit_total']))} to {bank_name}.",
            ok_tip="Close; the payments are no longer in Undeposited Funds.",
        )
        self.depositPosted.emit()
        if reset:
            self._reset_form()
        return True
