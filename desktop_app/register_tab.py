
"""
desktop_app.register_tab
========================
Architecture note
-----------------
This tab is the **primary** day-to-day **bank account register** for ``bank_transactions``
(categorization, cleared flags, GL posting, payment links, running balance). **Bank Import**
owns batch CSV/PDF intake and statement reconciliation; the **R** in **Clr** is a
reconciled-batch indicator on register rows, not a dedicated reconciliation screen by itself.
**Add transaction…** saves manual lines into ``bank_transactions`` via a per-account sentinel batch.
A **separate** general register detached from imports would be new product scope if the app
later splits those views.

Phase 3 – Bank register: chronological transactions for one bank account with
debit/credit columns, running balance, COA inline edits, and memo via the row menu
(txn id on Date ``UserRole``; balance stays chronological). The footer keeps the same height in normal and **Reconciliation mode**; debit/credit/net totals show only when reconciliation is on, while the gray help paragraph stays visible.
**Add transaction…** persists new lines via a per-account sentinel import batch (``(Manual entry)``); same ``bank_transactions`` rows as CSV imports, with an optional **Category (COA)** picker in the dialog (last non-empty choice per bank account is remembered for the next add, scoped by company file). **Date** defaults to the latest register transaction on that account when any exist, else today. **Amount** receives initial keyboard focus when the dialog opens.
The grid always shows at least **20** rows (practice lines when short on data; UI-only, not saved).
**Reconciliation mode** shows a banner; statement line-match status (**Matched** / **Missing** / **Extra**) appears on the second line of the **Match** column (demo from mock extract). Bank Import **Run extract & compare** can populate that overlay for the same account.
Payee column uses a two-band row: description on the lighter upper panel, COA account on the darker lower panel (full row width uses the same upper/lower band colors; other columns show values in the upper band).
**Memo** is not shown as a grid column (edit via row context menu). Hover **tooltips** on Payee, Number, Date, Debit/Credit, Balance, and Match show full values or helpful detail when the grid elides text.
**Match** (reconciliation mode): double-click **Match** or use row context **Open linked Business record…** (when the menu shows it) to open **Customers** / **Vendors** for AR/AP invoice or bill links, **More → Business → Payroll** for payroll, when the **complete bank link** allows; otherwise the same **Business link** message as **Ctrl+Shift+B** (invoice/bill editor, payroll tax lines, or AR/AP payment summary).
The **COA Account** combo tooltip states the saved category and whether the row is posted (read-only).
Number column keeps reference plus type tag (DEP / PMT / BILLPMT / CHK / XFER / TXN) in the cell data for copy/edit;
on screen they appear on two lines (number then type) like QuickBooks Pro Use Register. **Clr** shows **C** when the row is marked cleared on the register, else **R** when the
CSV import batch is marked reconciled in Bank Import. Rows without a COA category use a warmer two-band tint.
The filter choice, last selected bank account, and register table **column header widths**
persist in ``QSettings``, scoped by company SQLite path (same app profile as the main window).
**Ctrl+Shift+C** / **Ctrl+Shift+U** mark cleared / clear cleared; **Ctrl+Shift+E** runs **Export CSV…**;
**Ctrl+Shift+G** runs **Post selected to GL**; **Ctrl+Shift+B** runs the same **Business link** flow as double-click **Match** (navigates to **Customers** / **Vendors** / **Business → Payroll** when the row has a **complete bank link**); **F5** refreshes the grid when the Register tab (or its
controls) has keyboard focus. The same actions are on **Recon** → **Register Actions** / **Reconciliation** / **Attachments** / **Transaction Tools** / **Flags**. **Help** → **Bank register keyboard shortcuts…** (dialog also points at **Bank import shortcuts…**) or
**right-click** the grid (including empty area) for **Keyboard shortcuts…** and row actions with **QAction** **setToolTip**
(**Copy row** as TSV; **Copy transaction id**; **Copy date**; **Copy amount**; **Copy payee / description**; **Copy memo**; **Copy number / ref**; **Copy category (COA)** as plain saved COA); the register grid has a hover **tooltip**
(shortcuts summary). **Link payment…** dialog: **Current link** (when present) with **Clear link** and **Open linked Business record…**,
**Suggested matches** / **Manual link** headings, and the suggestions list have hover **tooltips**. **Right-click** the list (empty area OK) for
**Keyboard shortcuts…** (same **Help** dialog as the register grid).
Modal **Transfer** / **Splits** / **Link payment** dialogs and their buttons use **setToolTip** for hover hints; register actions on the main **Recon** menu use **QAction** tips there.
Footer **debit** / **credit** / **net** totals (reconciliation mode only) and the gray **help** paragraph have tooltips; the help block is always shown so the footer height matches reconciliation mode.
The tab **root** **QWidget** has a hover hint. **Bank account** and **Filter** combos (and their **QLabel** prompts) use **setToolTip**.
"""

from __future__ import annotations

import csv
import hashlib
import warnings
import sqlite3
from datetime import date, timedelta
from functools import partial
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import (
    QByteArray,
    QDate,
    QPoint,
    QRect,
    Qt,
    QSettings,
    QStringListModel,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QGuiApplication,
    QHideEvent,
    QKeySequence,
    QPainter,
    QPen,
    QPalette,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from probooksai import business
from probooksai.coa_ai_suggest import coa_hints
from probooksai.bank_import import BankDatabase, parse_amount
from probooksai.statement_line_match import (
    STATUS_EXTRA,
    STATUS_LIKELY_MATCH,
    STATUS_MATCHED,
    STATUS_NEEDS_REVIEW,
    compare_statement_to_register,
    mock_statement_lines_for_comparison,
)
from probooksai.coa_db import COADatabase
from probooksai.gl import GLDatabase

from desktop_app.audit_dialog import show_entity_audit_history
from desktop_app.open_attachment import open_local_attachment
from desktop_app.qt_combo_ids import (
    coerce_combo_int_id,
    combo_index_for_int_user_data,
    combo_int_ids_equal,
)
from desktop_app.flexible_date import (
    configure_qdate_edit_us,
    format_iso_to_us_display,
    format_ymd_as_us,
    parse_flexible_date_to_ymd,
)
from desktop_app.qt_mnemonic import (
    CSV_EXPORT_OK_TIP_SUFFIX,
    escape_ampersand_for_qt,
    message_box_information_ok,
    message_box_question_yes_no,
    message_box_warning_ok,
    qdialog_ok_button,
    tip_qdialog_button_box,
)
from desktop_app.table_clipboard import (
    CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX,
    QLIST_PLAIN_TEXT_ROLE,
    QTABLE_PLAIN_TEXT_ROLE,
    VIEW_BANK_REGISTER_KEYS_TOOLTIP,
    IntSortTableItem,
    NumericAmountTableItem,
    copy_qlistwidget_row_text,
    copy_table_row_as_tsv,
    plain_display_table_item,
)
from desktop_app.register_band_delegate import (
    REGISTER_LINK_BASE_TOOLTIP,
    REGISTER_LINK_LOWER_PLAIN,
    REGISTER_LINK_UPPER_PLAIN,
    REGISTER_MISSING_COA_ROLE,
    REGISTER_PAYEE_LOWER_PLAIN,
    REGISTER_PAYEE_UPPER_PLAIN,
    REGISTER_REF_LOWER_PLAIN,
    REGISTER_REF_UPPER_PLAIN,
    RegisterBandDelegate,
)
from desktop_app.theme import (
    AMOUNT_NEGATIVE,
    AMOUNT_POSITIVE,
    FG_PRIMARY,
    REGISTER_BAND_DIVIDER,
    REGISTER_ROW_HEIGHT_MIN_FULL,
    register_row_band_colors_hex,
    register_table_style_sheet,
)

_COL_DATE = 0
_COL_REF = 1
_COL_PAYEE = 2
_COL_MEMO = 3
_COL_DEBIT = 4  # PAYMENT (outflow)
_COL_CLR = 5
_COL_CREDIT = 6  # DEPOSIT (inflow)
_COL_BAL = 7
_COL_COA = 8
_COL_LINK = 9
_COL_SPACER = 10

_HEADERS = [
    "DATE",
    "NUMBER / TYPE",
    "PAYEE / ACCOUNT",
    "MEMO",
    "PAYMENT",
    "✓",
    "DEPOSIT",
    "BALANCE",
    "COA Account",
    "Match",
]

# Visible grid rows when there are fewer saved transactions (editable practice rows, UI-only).
_REGISTER_MIN_VISIBLE_ROWS = 20
REGISTER_DEFAULT_RANGE_DAYS = 90
_REGISTER_HEADERS_FULL = _HEADERS + [""]

# Payee and COA each use this fraction of the viewport slack left after other visible columns
# (excluding Payee, COA, and the unnamed spacer); the spacer column is Stretch and absorbs the rest.
_REGISTER_PAYEE_COA_SLACK_FRACTION_EACH = 0.25
_REGISTER_PAYEE_COLUMN_MIN_WIDTH_PX = 96

_MISSING_COA_BG = QColor("#3D3319")

_COA_COMBO_TIP_BODY = (
    "Chart-of-accounts line for this row. Starred (★) items are suggested from "
    "your categorization rules."
)


def _register_coa_combo_tooltip(*, posted: bool, saved_coa_display: str) -> str:
    disp = (saved_coa_display or "").strip() or "(Uncategorized)"
    if posted:
        return (
            f"Posted to GL — category is read-only (saved as: {disp}). "
            f"{_COA_COMBO_TIP_BODY}"
        )
    return f"Saved category: {disp}. {_COA_COMBO_TIP_BODY}"


def _manual_add_coa_combo_tooltip(current_selection: str) -> str:
    """Hover text for **Add transaction…** COA combo (unsaved line)."""
    disp = (current_selection or "").strip() or "(Uncategorized)"
    return (
        f"Category to save with this line: {disp}. "
        f"{_COA_COMBO_TIP_BODY} "
        "Hints refresh when Payee / description changes. "
        "Your last choice for this bank account is pre-selected the next time you open Add transaction…."
    )


def _bank_match_label(m) -> str:
    if m is None:
        return ""
    d = dict(m)
    lt = d.get("link_type") or ""
    lid = d.get("link_id")
    if lt == "ar_payment":
        return f"AR #{lid}"
    if lt == "ap_payment":
        return f"AP #{lid}"
    if lt == "payroll_run":
        return f"PR #{lid}"
    if lt == "ar_invoice":
        return f"INV #{lid}"
    if lt == "ap_bill":
        return f"BILL #{lid}"
    return f"{lt}:{lid}"


def _txn_posted(row) -> bool:
    keys = row.keys()
    return "is_posted" in keys and int(row["is_posted"] or 0) == 1


def _payee_line1_plain(txn: dict) -> str:
    return (txn.get("description") or "").strip() or "—"


def _payee_line2_account_plain(txn: dict) -> str:
    """Second line of Payee / Description: linked GL / COA account (memo is edited from the row menu)."""
    coa = (txn.get("coa_account") or "").strip()
    return coa if coa else "— Assign COA —"


def _register_payee_two_line_plain(txn: dict) -> str:
    """Payee cell clipboard / plain text: description then COA account line."""
    return f"{_payee_line1_plain(txn)}\n{_payee_line2_account_plain(txn)}"


def _register_number_type_tag(txn: dict) -> str:
    """Second line of Number column: inferred register type (QuickBooks-style hint)."""
    xfer_id = coerce_combo_int_id(txn.get("transfer_to_bank_account_id"))
    has_xfer = xfer_id is not None and xfer_id > 0
    if has_xfer:
        return "XFER"
    memo = (txn.get("memo") or "").strip().upper().replace(" ", "").replace("-", "")
    if memo in {"BILLPMT", "PAYBILLS"}:
        return "BILLPMT"
    if memo in {"CHK", "CHECK"}:
        return "CHK"
    if memo in {"DEP", "DEPOSIT", "MAKEDEPOSITS"} or memo.startswith("MAKEDEPOSIT"):
        return "DEP"
    try:
        amt = float(txn.get("amount") or 0.0)
    except (TypeError, ValueError):
        amt = 0.0
    ref = (txn.get("ref_number") or "").strip()
    if amt < 0 and ref.isdigit():
        return "CHK"
    if amt > 0:
        return "DEP"
    if amt < 0:
        return "PMT"
    return "TXN"


def _register_num_upper_plain(txn: dict) -> str:
    ref = (txn.get("ref_number") or "").strip()
    return ref if ref else "—"


def _register_num_lower_plain(txn: dict) -> str:
    return _register_number_type_tag(txn)


def _register_number_two_line_plain(txn: dict) -> str:
    """Number cell: line 1 = ref #; line 2 = DEP / PMT / BILLPMT / XFER / TXN."""
    return f"{_register_num_upper_plain(txn)}\n{_register_num_lower_plain(txn)}"


class CoaBandFrame(QFrame):
    """COA combo on a two-band background matching :class:`RegisterBandDelegate` rows (see ``register_band_delegate``)."""

    def __init__(self, combo: QComboBox, table: QTableWidget, logical_row: int):
        super().__init__()
        self._table = table
        self._logical_row = logical_row
        self._combo = combo
        self._open_coa_cb: Optional[Callable[["CoaBandFrame"], None]] = None
        combo.setParent(self)
        self._upper = _CoaUpperBand(self)
        self._upper.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(1, 1, 1, 1)
        lay.setSpacing(0)
        lay.addWidget(self._upper, 1)
        lay.addWidget(combo, 1)
        combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

    def combo(self) -> QComboBox:
        return self._combo

    def set_open_coa_callback(
        self, cb: Optional[Callable[["CoaBandFrame"], None]]
    ) -> None:
        self._open_coa_cb = cb

    def set_logical_row(self, row: int) -> None:
        self._logical_row = row

    def _visual_row(self) -> int:
        pos = self.mapTo(self._table, QPoint(self.rect().center()))
        idx = self._table.indexAt(pos)
        if idx.isValid():
            return idx.row()
        return self._logical_row

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        r = self.rect()
        mid = max(r.height() // 2, 1)
        top_r = QRect(0, 0, r.width(), mid)
        bot_r = QRect(0, mid, r.width(), r.height() - mid)
        row = self._visual_row()
        missing = False
        it = self._table.item(row, _COL_DATE)
        if it is not None:
            missing = bool(it.data(REGISTER_MISSING_COA_ROLE))
        uh, lh = register_row_band_colors_hex(row % 2 == 1, missing, light=True)
        p.fillRect(top_r, QColor(uh))
        p.fillRect(bot_r, QColor(lh))
        p.setPen(QPen(QColor(REGISTER_BAND_DIVIDER), 1))
        p.drawLine(0, mid, r.width(), mid)

    def apply_combo_missing_style(self, missing: bool) -> None:
        if missing:
            self._combo.setStyleSheet(
                f"QComboBox {{ background-color: {_MISSING_COA_BG.name()}; color: {FG_PRIMARY}; }}"
            )
        else:
            self._combo.setStyleSheet(
                "QComboBox { background-color: transparent; color: inherit; }"
            )


def _batch_reconciled_map(conn: sqlite3.Connection, txns: list) -> dict[int, bool]:
    """Map import *batch_id* -> True when ``bank_import_batches.is_reconciled`` is set."""
    ids: set[int] = set()
    for txn in txns:
        d = dict(txn)
        bid = coerce_combo_int_id(d.get("batch_id"))
        if bid is None:
            continue
        ids.add(bid)
    if not ids:
        return {}
    qmarks = ",".join("?" * len(ids))
    cur = conn.execute(
        f"SELECT id, is_reconciled FROM bank_import_batches WHERE id IN ({qmarks})",
        list(ids),
    )
    out: dict[int, bool] = {}
    for row in cur.fetchall():
        r = dict(row)
        bid = coerce_combo_int_id(r["id"])
        if bid is None:
            continue
        out[bid] = int(r.get("is_reconciled") or 0) == 1
    return out


def _coerce_register_account_id(raw: object) -> int | None:
    return coerce_combo_int_id(raw)


def _register_account_ids_equal(a: object, b: object) -> bool:
    """True when both are missing or represent the same bank account id (after int coercion)."""
    return combo_int_ids_equal(a, b)


def _register_row_coa_user_data(table: QTableWidget, row: int) -> str:
    """Raw COA line from the row's category combo (``userData``), or empty when uncategorized."""
    w = table.cellWidget(row, _COL_COA)
    if isinstance(w, CoaBandFrame):
        return register_coa_combo_resolve_user_data(w.combo())
    elif isinstance(w, QComboBox):
        return register_coa_combo_resolve_user_data(w)
    else:
        return ""


_UNCATEGORIZED_COMBO_LABEL = "(Uncategorized)"


def register_coa_combo_resolve_user_data(combo: QComboBox) -> str:
    """Canonical ``coa_account`` string for the combo (editable-aware)."""
    if not combo.isEditable():
        raw = combo.currentData()
        return raw.strip() if isinstance(raw, str) else ""
    le = combo.lineEdit()
    if le is None:
        raw = combo.currentData()
        return raw.strip() if isinstance(raw, str) else ""
    text = le.text().strip()
    if not text or text.lower() in ("(uncategorized)", "uncategorized"):
        return ""
    if text.startswith("★ "):
        text = text[2:].strip()
    idx = combo.findData(text)
    if idx >= 0 and isinstance(combo.itemData(idx), str):
        return combo.itemData(idx).strip()
    tlow = text.lower()
    for i in range(combo.count()):
        data = combo.itemData(i)
        if isinstance(data, str) and data.strip().lower() == tlow:
            return data.strip()
    for i in range(combo.count()):
        data = combo.itemData(i)
        disp = combo.itemText(i).replace("&&", "&")
        if disp.strip().lower() == tlow and isinstance(data, str):
            return data.strip()
    return text


def _configure_interactive_register_coa_combo(
    combo: QComboBox,
    coa_choices: list[str],
    txn_id: int,
    tab: "RegisterTab",
) -> None:
    """Editable combo, substring completer over COA list, commit normalization on focus out."""
    if not combo.isEnabled():
        return
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    strings = [_UNCATEGORIZED_COMBO_LABEL] + list(coa_choices)
    comp = QCompleter(QStringListModel(strings), combo)
    comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    comp.setFilterMode(Qt.MatchFlag.MatchContains)
    comp.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
    comp.activated[str].connect(
        lambda _t: QTimer.singleShot(
            0, partial(tab._finish_register_coa_line_edit, txn_id, combo)
        )
    )
    combo.setCompleter(comp)
    le = combo.lineEdit()
    if le is not None:
        le.editingFinished.connect(
            partial(tab._finish_register_coa_line_edit, txn_id, combo)
        )


class _CoaUpperBand(QWidget):
    """Upper half of the COA cell: click opens the category dropdown; double-click opens Chart of Accounts."""

    def __init__(self, band_frame: "CoaBandFrame"):
        super().__init__(band_frame)
        self._band_frame = band_frame

    def mousePressEvent(self, ev):
        c = self._band_frame._combo
        if not c.isEnabled():
            super().mousePressEvent(ev)
            return
        c.setFocus()
        QTimer.singleShot(0, c.showPopup)
        ev.accept()

    def mouseDoubleClickEvent(self, ev):
        cb = self._band_frame._open_coa_cb
        if cb:
            cb(self._band_frame)
        ev.accept()


def _register_date_cell_item(txn_date_iso: str) -> IntSortTableItem:
    """Register Date column: US display (MM/DD/YYYY), chronological sort, TSV copy matches display."""
    raw = (txn_date_iso or "").strip()
    disp = format_iso_to_us_display(raw) if raw else ""
    qd = QDate.fromString(raw[:10], "yyyy-MM-dd")
    sk = (
        qd.year() * 10000 + qd.month() * 100 + qd.day()
        if qd.isValid()
        else 0
    )
    return IntSortTableItem(disp, sk)


class ManualTransactionDialog(QDialog):
    """One manual bank line for :meth:`BankDatabase.insert_manual_transaction`."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        coa_choices: list[str],
        conn: sqlite3.Connection,
        initial_coa: str = "",
        initial_txn_date: Optional[str] = None,
        initial_amount: Optional[float] = None,
        initial_description: str = "",
        initial_ref_number: str = "",
        initial_memo: str = "",
    ):
        super().__init__(parent)
        self.setWindowTitle("Add bank transaction")
        self.setMinimumWidth(420)
        self._conn = conn
        self._coa_choice_list = list(coa_choices)
        self._initial_coa = (initial_coa or "").strip()
        form = QFormLayout(self)
        self._date = QDateEdit()
        configure_qdate_edit_us(self._date)
        self._date.setDate(QDate.currentDate())
        raw_d = (initial_txn_date or "").strip()[:10]
        if raw_d:
            qd = QDate.fromString(raw_d, "yyyy-MM-dd")
            if qd.isValid():
                self._date.setDate(qd)
        self._date.setToolTip(
            "Transaction date: type flexibly (e.g. 5/21/26 or 05-21-2026); shown as MM/DD/YYYY; "
            "stored as YYYY-MM-DD in the company database. "
            "When this account already has register rows, the dialog opens on the latest of those dates; "
            "otherwise today."
        )
        form.addRow("Date", self._date)
        self._amount = QLineEdit()
        self._amount.setPlaceholderText("e.g. 100.00 or -25.50")
        self._amount.setToolTip(
            "Signed amount: positive = deposit / inflow, negative = payment / outflow "
            "(same convention as CSV import). "
            "Keyboard focus starts here when the dialog opens."
        )
        if initial_amount is not None:
            self._amount.setText(f"{float(initial_amount):.2f}")
        form.addRow("Amount", self._amount)
        self._desc = QLineEdit()
        self._desc.setToolTip("Payee or description (first line of the Payee column).")
        idesc = (initial_description or "").strip()
        if idesc:
            self._desc.setText(idesc)
        form.addRow("Payee / description", self._desc)
        self._coa = QComboBox()
        self._rebuild_coa_combo()
        if self._initial_coa:
            idx = self._coa.findData(self._initial_coa)
            if idx >= 0:
                self._coa.setCurrentIndex(idx)
        self._coa.currentIndexChanged.connect(self._sync_coa_combo_tooltip)
        self._sync_coa_combo_tooltip()
        self._desc.textChanged.connect(self._rebuild_coa_combo)
        form.addRow("Category (COA)", self._coa)
        self._ref = QLineEdit()
        self._ref.setToolTip("Optional check number or bank reference.")
        ir = (initial_ref_number or "").strip()
        if ir:
            self._ref.setText(ir)
        form.addRow("Number / ref", self._ref)
        self._memo = QLineEdit()
        self._memo.setToolTip("Optional memo (editable later in the register grid).")
        im = (initial_memo or "").strip()
        if im:
            self._memo.setText(im)
        form.addRow("Memo", self._memo)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        tip_qdialog_button_box(
            bb,
            ok="Insert this row into bank_transactions (manual-entry batch). "
            "Ctrl+Enter or Ctrl+Return runs the same check as OK (valid non-zero amount). "
            "Company .db: File → Backup / Restore (probooks.backup).",
            cancel="Close without adding a transaction.",
            ok_default=True,
        )
        bb.accepted.connect(self._try_accept)
        bb.rejected.connect(self.reject)
        for seq in ("Ctrl+Return", "Ctrl+Enter"):
            QShortcut(QKeySequence(seq), self, activated=self._try_accept)
        form.addRow(bb)
        QTimer.singleShot(0, self._amount.setFocus)

    def _rebuild_coa_combo(self) -> None:
        prev = self._coa.currentData()
        self._coa.blockSignals(True)
        self._coa.clear()
        self._coa.addItem("(Uncategorized)", "")
        insert_at = 1
        desc = self._desc.text().strip()
        try:
            for h in coa_hints(
                self._conn,
                desc,
                self._coa_choice_list,
                limit=3,
            ):
                if self._coa.findData(h) < 0:
                    self._coa.insertItem(
                        insert_at,
                        escape_ampersand_for_qt(f"★ {h}"),
                        h,
                    )
                    insert_at += 1
        except sqlite3.OperationalError:
            pass
        for label in self._coa_choice_list:
            self._coa.addItem(escape_ampersand_for_qt(label), label)
        idx = self._coa.findData(prev if prev else "")
        if idx >= 0:
            self._coa.setCurrentIndex(idx)
        elif prev:
            self._coa.addItem(escape_ampersand_for_qt(str(prev)), prev)
            self._coa.setCurrentIndex(self._coa.count() - 1)
        self._coa.blockSignals(False)
        self._sync_coa_combo_tooltip()

    def _sync_coa_combo_tooltip(self) -> None:
        raw = self._coa.currentData()
        sel = raw if isinstance(raw, str) else (str(raw) if raw is not None else "")
        self._coa.setToolTip(
            escape_ampersand_for_qt(_manual_add_coa_combo_tooltip(sel))
        )

    def _try_accept(self) -> None:
        amt = parse_amount(self._amount.text().strip())
        if amt is None:
            message_box_warning_ok(
                self,
                "Amount",
                "Enter a valid amount (e.g. 50 or -12.50).",
                ok_tip="Close; use a number. Positive = deposit, negative = payment.",
            )
            return
        if amt == 0:
            message_box_warning_ok(
                self,
                "Amount",
                "Amount cannot be zero.",
                ok_tip="Close; enter a non-zero amount.",
            )
            return
        self.accept()

    def values(self) -> dict:
        raw_coa = self._coa.currentData()
        coa = (raw_coa if isinstance(raw_coa, str) else "") or ""
        return {
            "txn_date": self._date.date().toString("yyyy-MM-dd"),
            "amount": parse_amount(self._amount.text().strip()) or 0.0,
            "description": self._desc.text().strip(),
            "ref_number": self._ref.text().strip(),
            "memo": self._memo.text().strip(),
            "coa_account": coa.strip(),
        }


def _register_keyboard_shortcuts_help_text() -> str:
    """Plain text for Register shortcuts (keep aligned with ``QShortcut`` wiring)."""
    return (
        "These shortcuts apply when the Register tab or its controls have focus:\n\n"
        "Recon menu — Register Actions / Reconciliation / Attachments / Transaction Tools / Flags "
        "mirror the former register buttons (add, post, export, cleared, attachments, splits, transfer, link, receipt flags); "
        "F5 still refreshes the grid.\n\n"
        "Add transaction… — opens a dialog to save a new line to the register "
        "(same bank_transactions table as imports; manual-entry batch; optional Category / COA, "
        "remembered per bank account until you choose Uncategorized; date defaults to the latest "
        "saved row on that account when present). In that dialog: focus starts in **Amount**; "
        "Ctrl+Enter or Ctrl+Return accepts when the amount is valid (same as OK).\n\n"
        "Reconciliation mode — checkbox next to Filter: banner + statement line-match status on the **Match** column (demo); "
        "register grid stays visible underneath. "
        "Bank Import **Run extract & compare** can populate that overlay for the same account "
        "and switch the main window here; the main **status bar** may show a short confirmation, "
        "then restore the usual company line.\n\n"
        "View menu tab focus: Ctrl+1 Invoices, Ctrl+2 Codes, Ctrl+3 Write Checks, Ctrl+4 Enter Bills, Ctrl+5 Pay Bills, Ctrl+6 Receive Payments, "
        "Ctrl+7 Bank Register, Ctrl+8 Chart of Accounts, Ctrl+9 Customers, Ctrl+0 Vendors, Ctrl+Shift+R Reconcile, "
        "Ctrl+Shift+M More (Reports, Journal, Business, Audit log).\n\n"
        "Tools menu: Ctrl+Shift+I — Invoice… (top-level Invoices tab); full AR list and payments: **Customers** tab.\n\n"
        "Practice rows — blank rows pad the grid to ~20 lines; editable for layout only (not saved).\n\n"
        "Register grid — checkbook-style two-band rows; arrow keys move the cell focus. "
        "Double-click or type to edit Number when the row allows it; memo: right-click the row → **Edit memo…**; COA uses the category dropdown. "
        "Right-click a row: Copy row (TSV); Copy transaction id (bank_transactions.id, same as line-reconciliation **Reg #**); "
        "Copy date (YYYY-MM-DD); Copy amount (signed, two decimals, same convention as CSV import); "
        "Copy payee / description; Copy memo; Copy number / ref; Copy category (COA) (plain saved category). "
        "Bank Import batch preview rows offer the same field copies from the database; "
        "its **Matched / Missing / Extra** line-reconciliation grid adds statement/register copies—see **Help → Bank import shortcuts….**\n\n"
        "Link payment… (Recon → Transaction Tools) — when the **current link** can open in Business, use **Open linked Business record…** "
        "in that dialog (closes it first); suggested-matches list: right-click (including empty area) for "
        "Keyboard shortcuts… (same as this dialog).\n"
        "Open linked Business record… — Recon → Transaction Tools, right-click when that action is in the menu, or double-click **Match**: "
        "opens **Customers** / **Vendors** for AR/AP invoice or bill links, **More → Business → Payroll** for payroll, "
        "when the **complete bank link** allows; otherwise the same **Business link** message as **Ctrl+Shift+B** "
        "(invoice, bill, payroll tax lines, or AR/AP payment summary).\n\n"
        "F5 — Refresh\n"
        "Ctrl+Shift+G — Post selected to GL\n"
        "Ctrl+Shift+E — Export CSV… (UTF-8 with BOM for Excel)\n"
        "Ctrl+Shift+B — same **Business link** flow as **Open linked Business** / double-click **Match** "
        "(**Business** when the link is complete; message otherwise). "
        "The same chord on **Bank Import** batch preview or line-reconciliation grid applies when that table has focus.\n"
        "Ctrl+Shift+C — Mark cleared (selected rows)\n"
        "Ctrl+Shift+U — Clear cleared (selected rows)\n"
        "\n"
        "Document Intake:\n"
        "Help → Document intake shortcuts… (includes File → Backup / Restore via probooks.backup).\n"
        "\n"
        "COA, Journal, Reports, Audit:\n"
        "Help → More tab shortcuts (F5)…\n"
        "\n"
        "Business tab:\n"
        "Help → Business shortcuts…\n"
        "\n"
        "Bank import tab:\n"
        "Help → Bank import shortcuts…\n"
    )


def show_register_keyboard_shortcuts_dialog(parent: QWidget) -> None:
    """Same content as the grid context menu **Keyboard shortcuts…** (shared with **Help** menu)."""
    message_box_information_ok(
        parent,
        "Register keyboard shortcuts",
        _register_keyboard_shortcuts_help_text(),
        ok_tip="Close; shortcuts apply when Bank register has focus. "
        "Recon menu — Register Actions and related groups for add/post/export, attachments, splits, transfer, link, open linked Business, and receipt flags. "
        "**Link payment…** also shows **Open linked Business record…** when the stored link is complete (can open in Business). "
        "View → Reconcile (Ctrl+Shift+R) → Bank statements for AI line reconciliation / Match-column overlay sync. "
        "Company .db: File → Backup / Restore (probooks.backup).",
    )


# Sentinel stored as QComboBox item data to trigger the Quick-Add COA dialog
_NEW_COA_SENTINEL = "__new_coa__"


# ---------------------------------------------------------------------------
# Quick-add COA dialog (inline account creation from the register)
# ---------------------------------------------------------------------------

class QuickAddCoaDialog(QDialog):
    """Minimal dialog to create a new COA account without leaving the register.

    Parameters
    ----------
    coa_db:
        :class:`~probooksai.coa_db.COADatabase` instance.
    prefill_name:
        Optional suggested account name (e.g. the payee from the transaction).
    parent:
        Parent widget.

    After ``exec()`` returns ``Accepted``, read :attr:`created_display_key` for
    the ``"NNNN Account Name"`` string that was inserted into the COA.
    """

    def __init__(
        self,
        coa_db: "COADatabase",
        *,
        prefill_name: str = "",
        parent: "QWidget | None" = None,
    ) -> None:
        super().__init__(parent)
        self._coa_db = coa_db
        self.created_display_key: str = ""

        self.setWindowTitle("New COA Account")
        self.setMinimumWidth(380)
        self.setToolTip(
            "Create a new Chart of Accounts entry and immediately assign it "
            "to this transaction. The account is saved permanently to the COA."
        )

        form = QFormLayout(self)
        form.setSpacing(8)

        self._num = QLineEdit()
        self._num.setPlaceholderText("e.g. 6200")
        self._num.setToolTip(
            "Account number — must be unique in the chart of accounts. "
            "Use your numbering convention (e.g. 6xxx for operating expenses)."
        )
        form.addRow("Account &Number:", self._num)

        self._name = QLineEdit()
        self._name.setPlaceholderText("e.g. Fuel &amp; Oil")
        self._name.setText(prefill_name)
        self._name.setToolTip("Short descriptive name shown throughout the app.")
        form.addRow("Account &Name:", self._name)

        self._type = QComboBox()
        for t in ("expense", "asset", "liability", "equity", "income"):
            self._type.addItem(t.capitalize(), t)
        self._type.setToolTip(
            "Account type: Expense for operating costs, Asset for cash/receivables, "
            "Liability for payables/loans, Equity for owner accounts, Income for revenue."
        )
        form.addRow("Account &Type:", self._type)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = qdialog_ok_button(buttons)
        if ok_btn is not None:
            ok_btn.setText("Create && Assign")
        tip_qdialog_button_box(
            buttons,
            ok="Create this COA account and assign it to the selected transaction.",
            cancel="Cancel — leave the transaction uncategorized.",
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        self._name.setFocus()

    def _on_accept(self) -> None:
        num  = self._num.text().strip()
        name = self._name.text().strip()
        if not name:
            message_box_warning_ok(
                self, "Validation",
                "Account Name is required.",
                ok_tip="Close; enter a name for the new account.",
            )
            return
        account_type = self._type.currentData()
        try:
            self._coa_db.add_account(
                account_number=num,
                account_name=name,
                account_type=account_type,
            )
        except Exception as exc:
            message_box_warning_ok(
                self, "Cannot create account",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; fix the error (duplicate number?) and try again.",
            )
            return
        self.created_display_key = f"{num} {name}".strip() if num else name
        self.accept()


class RegisterTab(QWidget):
    """Check-register for one bank account; emits :attr:`reconciliationModeChanged` when reconciliation UI toggles."""

    reconciliationModeChanged = Signal(bool)
    openBankMatchNavigationRequested = Signal(str, int)
    openCoaEditorRequested = Signal(str)
    openInCheckScreenRequested = Signal(int)  # txn_id
    openInDepositScreenRequested = Signal(int)  # txn_id
    openBankFeedsRequested = Signal()

    def __init__(
        self,
        bank_db: BankDatabase,
        coa_db: COADatabase,
        gl_db: Optional[GLDatabase] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._db = bank_db
        self._coa_db = coa_db
        self._gl = gl_db
        self._coa_choices: list[str] = self._coa_db.display_list()
        self._current_account_id: Optional[int] = None
        self._populating = False
        self._reconciliation_mode = False
        self._recon_txn_status: dict[int, str] = {}
        self._recon_overlay_bank_import_mode = False
        self._recon_header_snapshot: QByteArray | None = None
        self._cached_register_footer_totals_height = 0
        self._register_ending_balance: float | None = None
        self._one_line = False
        self._sort_mode = "date_type_ref"
        self._draft_snapshot: dict | None = None
        self._range_extend_days = 0
        self._build_ui()

    def _build_ui(self):
        self.setToolTip(
            "Bank register for one account: bank account picker, filter, reconciliation mode, and the transaction grid. "
            "F5 refreshes when Register has focus. "
            "Bulk row actions (add transaction, post to GL, and export CSV (UTF-8 BOM for Excel), cleared, attachments, splits, transfer, link payment, open linked Business, receipt flags): Recon menu. "
            "Reconciliation mode (toggle on the main tab bar when this tab is active) adds the Match overlay; "
            "Bank Import AI line reconciliation can populate it (Help → Bank import shortcuts…). "
            "View → Reconcile (Ctrl+Shift+R) → Bank statements; Bank Register (Ctrl+7). "
            "Same company SQLite database as other main tabs; File → Backup / Restore (probooks.backup)."
        )
        from desktop_app.theme import CHECKBOOK_TEXT
        from PySide6.QtGui import QColor, QPalette

        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window, QColor("#E8ECF1"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor(CHECKBOOK_TEXT))
        pal.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#E7F4EA"))
        pal.setColor(QPalette.ColorRole.Text, QColor(CHECKBOOK_TEXT))
        pal.setColor(QPalette.ColorRole.Button, QColor("#F7F8FA"))
        pal.setColor(QPalette.ColorRole.ButtonText, QColor(CHECKBOOK_TEXT))
        pal.setColor(QPalette.ColorRole.Highlight, QColor("#2E7D32"))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
        pal.setColor(QPalette.ColorRole.PlaceholderText, QColor("#5B6770"))
        self.setPalette(pal)
        self.setAutoFillBackground(True)
        self.setStyleSheet(
            f"RegisterTab {{ background-color: #E8ECF1; color: {CHECKBOOK_TEXT}; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── QB Pro register toolbar ─────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setObjectName("bankRegisterToolbar")
        toolbar.setStyleSheet(
            "QWidget#bankRegisterToolbar { background: #F4F7FA; "
            "border-bottom: 1px solid #C0C8D0; }"
        )
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(8, 4, 8, 4)
        tb.setSpacing(6)

        def _tb_btn(text: str, tip: str) -> QPushButton:
            b = QPushButton(text)
            b.setFixedHeight(26)
            b.setStyleSheet(
                "QPushButton { background: #F7F8FA; border: 1px solid #B4BCC6; "
                "border-radius: 4px; padding: 0 10px; color: #1A1A1A; font-size: 12px; }"
                "QPushButton:hover { background: #E4EEF7; }"
            )
            b.setToolTip(tip)
            return b

        self._btn_goto = _tb_btn(
            "Go to...",
            "Find a register line by date (MM/DD/YYYY), check / reference number, payee, "
            "or amount, then select and scroll to the first match. Not a filter — other rows stay visible.",
        )
        self._btn_print = _tb_btn("Print...", "Print this register (layout control).")
        self._btn_edit_txn = _tb_btn(
            "Edit Transaction",
            "Open the source form for the selected row (bill payment, deposit, or check).",
        )
        self._btn_quickreport = _tb_btn(
            "QuickReport",
            "Show a QuickReport of this account's register lines.",
        )
        self._btn_bank_feeds = _tb_btn(
            "Setup Bank Feeds",
            "Open Reconcile → Bank statements for feeds and statement import.",
        )
        self._btn_goto.clicked.connect(self._on_goto)
        self._btn_print.clicked.connect(self._on_print_register)
        self._btn_edit_txn.clicked.connect(self._on_edit_selected_transaction)
        self._btn_quickreport.clicked.connect(self._on_quickreport)
        self._btn_bank_feeds.clicked.connect(self._on_setup_bank_feeds)
        for b in (
            self._btn_goto,
            self._btn_print,
            self._btn_edit_txn,
            self._btn_quickreport,
            self._btn_bank_feeds,
        ):
            tb.addWidget(b)
        tb.addStretch(1)
        self._hdr_acct_lbl = QLabel("")
        self._hdr_acct_lbl.setStyleSheet(
            "background: transparent; border: none; "
            "color: #2563A8; font-size: 12px; font-weight: 600;"
        )
        tb.addWidget(self._hdr_acct_lbl)
        layout.addWidget(toolbar)

        # Keep a hidden brand label so existing tests/docs that mention BANK REGISTER stay accurate.
        _lbl_brand = QLabel("BANK REGISTER")
        _lbl_brand.setObjectName("bankRegisterBrand")
        _lbl_brand.hide()
        layout.addWidget(_lbl_brand)

        # ── Controls row ─────────────────────────────────────────────────────
        _controls_wrap = QWidget()
        _controls_wrap.setStyleSheet("QWidget { border: none; }")
        _cw_lay = QVBoxLayout(_controls_wrap)
        _cw_lay.setContentsMargins(8, 6, 8, 4)
        _cw_lay.setSpacing(6)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        lbl_bank_acct = QLabel("Bank account:")
        lbl_bank_acct.setToolTip(
            "Prompt for the register account picker; use the combo to switch which bank you are viewing."
        )
        controls.addWidget(lbl_bank_acct)
        self._acct_combo = QComboBox()
        self._acct_combo.setMinimumWidth(240)
        self._acct_combo.setToolTip(
            "Choose which bank account register to view and edit."
        )
        self._acct_combo.currentIndexChanged.connect(self._on_account_changed)
        controls.addWidget(self._acct_combo)
        controls.addSpacing(12)
        lbl_register_filter = QLabel("Filter:")
        lbl_register_filter.setToolTip(
            "Prompt for the row filter; the combo limits visible transactions without changing accounts."
        )
        controls.addWidget(lbl_register_filter)
        self._filter_combo = QComboBox()
        self._filter_combo.addItem("All transactions", "all")
        self._filter_combo.addItem("Flagged: needs receipt", "needs_receipt")
        self._filter_combo.addItem("Has attachment", "has_attachment")
        self._filter_combo.addItem("Needs receipt, no file", "missing_attachment")
        self._filter_combo.addItem("Has payment / document link", "has_bank_match")
        self._filter_combo.addItem("No payment or document link", "no_bank_match")
        self._filter_combo.addItem("Cleared (register)", "cleared")
        self._filter_combo.addItem("Not cleared", "not_cleared")
        self._filter_combo.addItem("Batch reconciled (import)", "batch_reconciled")
        self._filter_combo.addItem("Batch not reconciled", "batch_not_reconciled")
        self._filter_combo.setToolTip(
            "Narrow rows by receipt flag, attachment, payment or open invoice/bill link, cleared state, "
            "or CSV batch reconciliation."
        )
        self._restore_register_filter_from_settings()
        self._filter_combo.currentIndexChanged.connect(self._on_register_filter_changed)
        controls.addWidget(self._filter_combo)
        controls.addSpacing(12)
        lbl_range = QLabel("Dates:")
        lbl_range.setToolTip("Default is the last 90 days so this tab opens quickly.")
        controls.addWidget(lbl_range)
        self._range_combo = QComboBox()
        self._range_combo.setObjectName("bankRegisterDateRange")
        self._range_combo.addItem("Last 90 days", REGISTER_DEFAULT_RANGE_DAYS)
        self._range_combo.addItem("Last 30 days", 30)
        self._range_combo.addItem("This year", -1)
        self._range_combo.addItem("All dates", 0)
        self._range_combo.setToolTip(
            "Default last 90 days. Older loads the previous 90 days. All dates loads the full register."
        )
        self._range_combo.currentIndexChanged.connect(self._on_register_range_changed)
        controls.addWidget(self._range_combo)
        self._btn_older = QPushButton("Older")
        self._btn_older.setObjectName("bankRegisterOlder")
        self._btn_older.setToolTip("Load the previous 90 days into this register.")
        self._btn_older.clicked.connect(self._on_register_older)
        controls.addWidget(self._btn_older)
        controls.addStretch(1)
        _cw_lay.addLayout(controls)
        layout.addWidget(_controls_wrap)

        # Reconciliation toggle is hosted on the main window tab bar (corner widget); keep a
        # hidden checkbox for unit tests and until MainWindow.bind_reconciliation_toggle runs.
        self._recon_checkbox = QCheckBox("Reconciliation mode", self)
        self._recon_checkbox.hide()
        self._recon_checkbox.toggled.connect(self._on_reconciliation_mode_toggled)

        self._recon_banner = QLabel("Reconciliation Mode Active")
        self._recon_banner.setVisible(False)
        self._recon_banner.setWordWrap(True)
        self._recon_banner.setStyleSheet(
            "background-color: #3a3518; color: #f5e6a2; padding: 8px 12px; "
            "font-weight: bold; border-radius: 4px;"
        )
        self._recon_banner.setToolTip(
            "Statement line-match overlay is on: second line of **Match** shows Matched / Missing / Extra (demo). "
            "Use **Bank Import** (View menu) for compare / line reconciliation; **Document Intake** and **Bank Import** tabs appear while this mode is on. "
            "Turn recon mode off with the **Reconciliation mode** checkbox on the main tab bar (when Bank register is active). "
            "View → Bank Register (Ctrl+7); run/compare from Reconcile → Bank import (Ctrl+Shift+R)."
        )
        layout.addWidget(self._recon_banner)

        self._table = QTableWidget()
        self._table.setObjectName("bankRegisterTable")
        self._table.setStyleSheet(register_table_style_sheet(light=True))
        self._table.setColumnCount(len(_REGISTER_HEADERS_FULL))
        self._table.setHorizontalHeaderLabels(_REGISTER_HEADERS_FULL)
        clr_header = self._table.horizontalHeaderItem(_COL_CLR)
        if clr_header is not None:
            clr_header.setToolTip(
                "C: cleared on this register. R: CSV import batch is reconciled in Bank Import. "
                "Double-click a cell here to toggle cleared when the row allows it."
            )
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self._table.setAlternatingRowColors(False)
        self._table.setItemDelegate(
            RegisterBandDelegate(
                self._table,
                link_col=_COL_LINK,
                light_theme=True,
                center_col=_COL_CLR,
                right_aligned_cols=frozenset({_COL_DEBIT, _COL_CREDIT, _COL_BAL}),
            )
        )
        self._table.verticalHeader().setDefaultSectionSize(REGISTER_ROW_HEIGHT_MIN_FULL)
        self._table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        # Native grid off; RegisterBandDelegate draws full cell borders (classic register lines).
        self._table.setShowGrid(False)
        self._table.setWordWrap(False)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(
            _COL_PAYEE, QHeaderView.ResizeMode.Interactive
        )
        self._table.horizontalHeader().setSectionResizeMode(
            _COL_COA, QHeaderView.ResizeMode.Interactive
        )
        self._table.horizontalHeader().setSectionResizeMode(
            _COL_SPACER, QHeaderView.ResizeMode.Stretch
        )
        # Interactive avoids ResizeToContents jumping when cell text or editors change (inline edit stability).
        self._table.horizontalHeader().setSectionResizeMode(_COL_CLR, QHeaderView.ResizeMode.Interactive)
        self._table.horizontalHeader().setSectionResizeMode(_COL_LINK, QHeaderView.ResizeMode.Interactive)
        self._table.setSortingEnabled(False)
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.cellDoubleClicked.connect(self._on_register_cell_double_clicked)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_register_context_menu)
        self._table.setToolTip(
            "Transactions for the selected bank account and filter; edit COA inline where allowed; memo via row menu. "
            "The grid keeps ~20 visible rows (practice lines when you have fewer saved transactions). "
            "Use Recon → Register Actions for add transaction, post, and export; "
            "other groups under Recon for attachments, splits, cleared, and flags. "
            "Right-click for Keyboard shortcuts… (empty area OK); on a saved row, also "
            "**Copy row**, **Copy transaction id**, **Copy date**, **Copy amount**, **Copy payee / description**, **Copy memo** (stored text), **Copy number / ref**, or **Copy category (COA)**. "
            "Statement vs register field copies for AI line reconciliation live on Bank Import (Help → Bank import shortcuts…). "
            "F5 refresh; Ctrl+Shift+G post; Ctrl+Shift+B same **Business link** flow as double-click **Match**; "
            "Ctrl+Shift+C / Ctrl+Shift+U cleared; Ctrl+Shift+E export (UTF-8 BOM for Excel). "
            "Same company .db as other tabs (File → Backup / Restore, probooks.backup)."
        )
        layout.addWidget(self._table, stretch=1)

        sc_cleared = QShortcut(QKeySequence("Ctrl+Shift+C"), self)
        sc_cleared.setContext(Qt.WidgetWithChildrenShortcut)
        sc_cleared.activated.connect(self._mark_cleared)
        sc_uncleared = QShortcut(QKeySequence("Ctrl+Shift+U"), self)
        sc_uncleared.setContext(Qt.WidgetWithChildrenShortcut)
        sc_uncleared.activated.connect(self._clear_cleared)
        sc_export = QShortcut(QKeySequence("Ctrl+Shift+E"), self)
        sc_export.setContext(Qt.WidgetWithChildrenShortcut)
        sc_export.activated.connect(self._export_csv)
        sc_refresh = QShortcut(QKeySequence("F5"), self)
        sc_refresh.setContext(Qt.WidgetWithChildrenShortcut)
        sc_refresh.activated.connect(self._reload_current)
        sc_post = QShortcut(QKeySequence("Ctrl+Shift+G"), self)
        sc_post.setContext(Qt.WidgetWithChildrenShortcut)
        sc_post.activated.connect(self._post_selected)
        sc_open_biz = QShortcut(QKeySequence("Ctrl+Shift+B"), self)
        sc_open_biz.setContext(Qt.WidgetWithChildrenShortcut)
        sc_open_biz.activated.connect(self.tools_register_open_linked_business_record)

        # ── Bottom status bar ────────────────────────────────────────────────
        # Strong top border separates the grid from the status bar.
        # Left side: quick Splits button + recon totals (recon mode only).
        # Right side: ENDING BALANCE — always visible and prominent.
        from desktop_app.theme import AMOUNT_POSITIVE, CHECKBOOK_GRID_LINE, CHECKBOOK_TEXT

        self._register_info_footer = QWidget()
        self._register_info_footer.setStyleSheet(
            f"QWidget {{ background: #F4F7FA; "
            f"border-top: 2px solid {CHECKBOOK_GRID_LINE}; }}"
        )
        footer_row = QHBoxLayout(self._register_info_footer)
        footer_row.setContentsMargins(10, 6, 14, 6)
        footer_row.setSpacing(16)

        # Quick-access Splits button
        self._footer_splits_btn = QPushButton("Splits")
        self._footer_splits_btn.setFixedWidth(72)
        self._footer_splits_btn.setStyleSheet(
            "QPushButton { background: #F7F8FA; border: 1px solid #B4BCC6; "
            "border-radius: 4px; color: #1A1A1A; padding: 4px 8px; }"
        )
        self._footer_splits_btn.clicked.connect(self._splits_dialog)
        footer_row.addWidget(self._footer_splits_btn)

        self._chk_one_line = QCheckBox("1-Line")
        self._chk_one_line.setObjectName("bankRegisterOneLine")
        self._chk_one_line.setChecked(False)
        self._chk_one_line.setStyleSheet(
            f"QCheckBox {{ color: {CHECKBOOK_TEXT}; background: transparent; font-size: 12px; }}"
        )
        self._chk_one_line.setToolTip(
            "Unchecked (default) is the two-line checkbook. Checked collapses each transaction to one line."
        )
        self._chk_one_line.toggled.connect(self._on_one_line_toggled)
        footer_row.addWidget(self._chk_one_line)

        self._sort_combo = QComboBox()
        self._sort_combo.setObjectName("bankRegisterSortBy")
        self._sort_combo.addItem("Date, Type, Number/Ref", "date_type_ref")
        self._sort_combo.addItem("Date", "date")
        self._sort_combo.addItem("Number/Ref", "ref")
        self._sort_combo.setToolTip("Sort this register. Default matches QuickBooks: Date, Type, Number/Ref.")
        self._sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        sort_lbl = QLabel("Sort by")
        sort_lbl.setStyleSheet(
            f"color: {CHECKBOOK_TEXT}; background: transparent; border: none; font-size: 12px;"
        )
        footer_row.addWidget(sort_lbl)
        footer_row.addWidget(self._sort_combo)

        # Recon totals (only visible in reconciliation mode)
        self._register_footer_totals_wrap = QWidget()
        self._register_footer_totals_wrap.setStyleSheet("QWidget { background: transparent; border: none; }")
        foot = QHBoxLayout(self._register_footer_totals_wrap)
        foot.setContentsMargins(0, 0, 0, 0)
        foot.setSpacing(20)
        self._lbl_debits = QLabel("Debits: —")
        self._lbl_debits.setStyleSheet("background: transparent; border: none; font-weight: bold;")
        self._lbl_credits = QLabel("Credits: —")
        self._lbl_credits.setStyleSheet("background: transparent; border: none; font-weight: bold;")
        self._lbl_net = QLabel("Net: —")
        self._lbl_net.setStyleSheet("background: transparent; border: none; font-weight: bold;")
        foot.addWidget(self._lbl_debits)
        foot.addWidget(self._lbl_credits)
        foot.addWidget(self._lbl_net)
        footer_row.addWidget(self._register_footer_totals_wrap)

        # Spacer to push ENDING BALANCE to the right
        footer_row.addStretch(1)

        # ENDING BALANCE — right-aligned, always shown
        lbl_eb_caption = QLabel("ENDING BALANCE")
        lbl_eb_caption.setStyleSheet(
            "background: transparent; border: none; "
            "color: #4A5560; font-size: 10px; letter-spacing: 1px; font-weight: 700;"
        )
        footer_row.addWidget(lbl_eb_caption)

        self._lbl_ending_balance = QLabel("—")
        self._lbl_ending_balance.setStyleSheet(
            f"background: transparent; border: none; "
            f"color: {AMOUNT_POSITIVE}; font-size: 17px; font-weight: 700;"
        )
        self._lbl_ending_balance.setMinimumWidth(130)
        self._lbl_ending_balance.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        footer_row.addWidget(self._lbl_ending_balance)

        self._btn_record = QPushButton("Record")
        self._btn_record.setObjectName("bankRegisterRecord")
        self._btn_record.setFixedHeight(28)
        self._btn_record.setStyleSheet(
            "QPushButton { background: #2563A8; color: #FFFFFF; border: 1px solid #2563A8; "
            "border-radius: 4px; padding: 0 14px; font-weight: 600; }"
        )
        self._btn_record.setToolTip("Save the blank entry row at the bottom of this register.")
        self._btn_record.clicked.connect(self._on_record_entry)
        footer_row.addWidget(self._btn_record)

        self._btn_restore = QPushButton("Restore")
        self._btn_restore.setObjectName("bankRegisterRestore")
        self._btn_restore.setFixedHeight(28)
        self._btn_restore.setStyleSheet(
            "QPushButton { background: #F7F8FA; border: 1px solid #B4BCC6; "
            "border-radius: 4px; color: #1A1A1A; padding: 0 14px; }"
        )
        self._btn_restore.setToolTip("Clear unsaved entry-row edits and reload this register.")
        self._btn_restore.clicked.connect(self._on_restore_entry)
        footer_row.addWidget(self._btn_restore)

        layout.addWidget(self._register_info_footer)

        self._clear_table()
        self._apply_register_column_layout()
        self._sync_register_info_footer_visibility()

    def _is_db_alive(self) -> bool:
        """``True`` when ``self._db`` still has a usable SQLite connection.

        Returns ``False`` if the bank database is missing or has been closed
        (e.g. while the parent ``MainWindow`` is mid-``_switch_company_database``
        and the old ``RegisterTab`` is still receiving Qt show events as the
        tab strip rebuilds). This lets ``showEvent`` and ``_refresh_account_combo``
        no-op instead of raising ``sqlite3.ProgrammingError`` against the closed
        connection — the new ``RegisterTab`` built by ``_assemble_main_tabs``
        owns the next refresh against the freshly opened DB.
        """
        db = getattr(self, "_db", None)
        if db is None:
            return False
        if getattr(db, "is_closed", False):
            return False
        return getattr(db, "_conn", None) is not None

    def showEvent(self, event):
        super().showEvent(event)
        if not self._is_db_alive():
            # Old register tab being torn down by ``MainWindow._teardown_main_tabs_for_rebuild``
            # while a sibling tab becomes current; ``self._db`` already points at a closed
            # ``BankDatabase``. The new tab built by ``_assemble_main_tabs`` will refresh.
            return
        if self._current_account_id is None:
            try:
                self._refresh_account_combo()
            except sqlite3.ProgrammingError:
                return
        raw = QSettings().value(self._register_table_header_state_key())
        if raw:
            self._table.horizontalHeader().restoreState(raw)
        self._apply_register_column_layout()
        self._sync_payee_coa_spacer_widths()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_payee_coa_spacer_widths()
        pass  # footer bar is fixed-height; no height caching needed

    def hideEvent(self, event: QHideEvent) -> None:
        self._persist_register_table_header_state()
        super().hideEvent(event)

    def refresh_coa_choices(self):
        """Call when the chart of accounts changes (same DB connection)."""
        self._coa_choices = self._coa_db.display_list()
        self._reload_current()

    def refresh_bank_accounts(self):
        """Call after the bank_accounts table changes so the account combo updates."""
        self._refresh_account_combo()

    # --- Recon menu (MainWindow): same handlers as the former on-tab register action buttons ---------
    def tools_register_add_transaction(self) -> None:
        self._on_add_manual_transaction()

    def tools_register_post_selected(self) -> None:
        self._post_selected()

    def tools_register_export_csv(self) -> None:
        self._export_csv()

    def tools_register_mark_cleared(self) -> None:
        self._mark_cleared()

    def tools_register_clear_cleared(self) -> None:
        self._clear_cleared()

    def tools_register_attach_file(self) -> None:
        self._attach_file()

    def tools_register_clear_attachment(self) -> None:
        self._clear_attachment()

    def tools_register_transfer_dialog(self) -> None:
        self._transfer_dialog()

    def tools_register_splits_dialog(self) -> None:
        self._splits_dialog()

    def tools_register_link_payment_dialog(self) -> None:
        self._link_payment_dialog()

    def open_linked_business_record_for_transaction_id(self, txn_id: int) -> None:
        """Open the Business hub target for *txn_id*'s **complete bank link**, or show the same prompts as Recon / Ctrl+Shift+B."""
        tid = coerce_combo_int_id(txn_id)
        if tid is None:
            message_box_information_ok(
                self,
                "Business link",
                "Invalid transaction id.",
                ok_tip="Close; pick a saved import or register row.",
            )
            return
        try:
            bm = business.get_bank_match(self._db._conn, tid)
        except sqlite3.OperationalError:
            message_box_information_ok(
                self,
                "Business link",
                "Bank match data is not available in this database.",
                ok_tip="Close; open a company file with Business extensions enabled.",
            )
            return
        nav = business.bank_match_link_tuple_from_row(bm)
        if nav is None:
            msg = (
                "This row has no payment or open invoice/bill link. Use Link payment… first."
            )
            ok_tip = "Close; Recon → Transaction Tools → Link payment…"
            if bm is not None:
                msg = (
                    "This row has a bank link row, but type or id is incomplete so Business cannot open it. "
                    "Use Link payment… to clear or re-link."
                )
            message_box_information_ok(
                self,
                "Business link",
                msg,
                ok_tip=ok_tip,
            )
            return
        lt, lid = nav
        self.openBankMatchNavigationRequested.emit(lt, int(lid))

    def tools_register_open_linked_business_record(self) -> None:
        """Recon menu / Ctrl+Shift+B: same **Business link** flow as double-click **Match** for the current row."""
        row = self._table.currentRow()
        if row < 0:
            message_box_information_ok(
                self,
                "Business link",
                "Select a register row first.",
                ok_tip="Close; click a row, then Recon → Transaction Tools → Open linked Business record or Ctrl+Shift+B.",
            )
            return
        id_item = self._table.item(row, _COL_DATE)
        tid = (
            coerce_combo_int_id(id_item.data(Qt.ItemDataRole.UserRole))
            if id_item is not None
            else None
        )
        if tid is None:
            message_box_information_ok(
                self,
                "Business link",
                "This row is a practice line (not a saved transaction).",
                ok_tip="Close; pick a saved register line (not a practice row).",
            )
            return
        self.open_linked_business_record_for_transaction_id(tid)

    def tools_register_flag_needs_receipt(self) -> None:
        self._mark_needs_receipt()

    def tools_register_clear_needs_receipt(self) -> None:
        self._clear_needs_receipt()

    def _register_prefs_id(self) -> str:
        p = getattr(self._db, "_db_path", None)
        if not p:
            return "default"
        return hashlib.sha256(
            str(p).encode("utf-8", errors="replace")
        ).hexdigest()[:16]

    def _register_filter_settings_key(self) -> str:
        return f"register/last_filter_{self._register_prefs_id()}"

    def _register_bank_account_settings_key(self) -> str:
        return f"register/last_bank_account_id_{self._register_prefs_id()}"

    def _register_table_header_state_key(self) -> str:
        # v3: Payee uses a fixed fraction of Payee+COA slack (narrower than dual-Stretch 50/50).
        return f"register/table_header_state_v4_{self._register_prefs_id()}"

    def _register_manual_entry_last_coa_key(self, bank_account_id: int) -> str:
        return (
            f"register/manual_entry_last_coa_{self._register_prefs_id()}_{int(bank_account_id)}"
        )

    def _persist_register_table_header_state(self) -> None:
        QSettings().setValue(
            self._register_table_header_state_key(),
            self._table.horizontalHeader().saveState(),
        )

    def _restore_register_filter_from_settings(self) -> None:
        raw = QSettings().value(self._register_filter_settings_key(), "all")
        want = str(raw) if raw is not None else "all"
        self._filter_combo.blockSignals(True)
        for i in range(self._filter_combo.count()):
            d = self._filter_combo.itemData(i)
            if d is not None and str(d) == want:
                self._filter_combo.setCurrentIndex(i)
                break
        self._filter_combo.blockSignals(False)

    def _on_register_filter_changed(self) -> None:
        d = self._filter_combo.currentData()
        QSettings().setValue(
            self._register_filter_settings_key(),
            str(d if d is not None else "all"),
        )
        self._reload_current()

    def _on_register_range_changed(self) -> None:
        self._range_extend_days = 0
        self._reload_current()

    def _on_register_older(self) -> None:
        data = self._range_combo.currentData()
        if data == 0:
            return
        self._range_extend_days += REGISTER_DEFAULT_RANGE_DAYS
        self._reload_current()

    def _register_statement_start(self) -> Optional[str]:
        data = self._range_combo.currentData()
        extra = int(getattr(self, "_range_extend_days", 0) or 0)
        today = date.today()
        if data == 0:
            return None
        if data == -1:
            start = date(today.year, 1, 1) - timedelta(days=extra)
            return start.isoformat()
        try:
            days = int(data)
        except (TypeError, ValueError):
            days = REGISTER_DEFAULT_RANGE_DAYS
        return (today - timedelta(days=days + extra)).isoformat()

    def _refresh_account_combo(self):
        if not self._is_db_alive():
            return
        self._acct_combo.blockSignals(True)
        prev = self._current_account_id
        self._acct_combo.clear()
        accounts = self._db.list_bank_accounts()
        if not accounts:
            self._acct_combo.addItem("(no bank accounts)", None)
        else:
            for acct in accounts:
                aid = coerce_combo_int_id(acct["id"])
                if aid is None:
                    continue
                label = f"{acct['name']} – {acct['bank_name'] or 'Bank'}"
                self._acct_combo.addItem(escape_ampersand_for_qt(label), aid)
        self._acct_combo.blockSignals(False)
        picked = False
        if prev is not None:
            ix = combo_index_for_int_user_data(self._acct_combo, prev)
            if ix is not None:
                self._acct_combo.setCurrentIndex(ix)
                picked = True
        if not picked and accounts:
            sid_raw = QSettings().value(self._register_bank_account_settings_key(), -1)
            sid = coerce_combo_int_id(sid_raw)
            if sid is None:
                sid = -1
            if sid > 0:
                ix = combo_index_for_int_user_data(self._acct_combo, sid)
                if ix is not None:
                    self._acct_combo.setCurrentIndex(ix)
                    picked = True
        if not picked and accounts:
            # Always default to the first account when nothing is saved
            self._acct_combo.setCurrentIndex(0)
        self._on_account_changed()

    def _on_account_changed(self):
        aid = _coerce_register_account_id(self._acct_combo.currentData())
        prev_id = self._current_account_id
        if (
            not _register_account_ids_equal(prev_id, aid)
            and prev_id is not None
        ):
            self._recon_overlay_bank_import_mode = False
            self._recon_txn_status.clear()
        self._current_account_id = aid
        # Update header badge with current account name
        acct_text = self._acct_combo.currentText() if aid is not None else ""
        if hasattr(self, "_hdr_acct_lbl"):
            self._hdr_acct_lbl.setText(acct_text)
        s = QSettings()
        if aid is None:
            s.remove(self._register_bank_account_settings_key())
            self._clear_table()
            return
        s.setValue(self._register_bank_account_settings_key(), aid)
        self._load_transactions(aid)

    def _reload_current(self):
        if not self._is_db_alive():
            return
        if self._current_account_id is not None:
            self._load_transactions(self._current_account_id)
        else:
            self._clear_table()

    def is_reconciliation_mode(self) -> bool:
        return self._reconciliation_mode

    def bind_reconciliation_toggle(self, checkbox: QCheckBox) -> None:
        """Main window: use *checkbox* (tab bar corner widget) as the recon toggle; replaces any prior binding."""
        if checkbox is self._recon_checkbox:
            return
        try:
            self._recon_checkbox.toggled.disconnect(self._on_reconciliation_mode_toggled)
        except TypeError:
            pass
        if self._recon_checkbox.parent() is self:
            self._recon_checkbox.deleteLater()
        self._recon_checkbox = checkbox
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                checkbox.toggled.disconnect()
            except TypeError:
                pass
        checkbox.toggled.connect(self._on_reconciliation_mode_toggled)
        checkbox.blockSignals(True)
        checkbox.setChecked(self._reconciliation_mode)
        checkbox.blockSignals(False)

    def _sync_register_info_footer_visibility(self) -> None:
        """Recon totals only visible in reconciliation mode; ENDING BALANCE always shown."""
        recon = self._reconciliation_mode
        self._register_footer_totals_wrap.setVisible(recon)

    def _ensure_payee_column_resize_policy(self) -> None:
        """Payee + COA are fixed-width (synced from slack); unnamed spacer column stretches."""
        hdr = self._table.horizontalHeader()
        if not hdr.isSectionHidden(_COL_PAYEE):
            hdr.setSectionResizeMode(_COL_PAYEE, QHeaderView.ResizeMode.Interactive)
        if not hdr.isSectionHidden(_COL_COA):
            hdr.setSectionResizeMode(_COL_COA, QHeaderView.ResizeMode.Interactive)
        if not hdr.isSectionHidden(_COL_SPACER):
            hdr.setSectionResizeMode(_COL_SPACER, QHeaderView.ResizeMode.Stretch)

    def _sync_payee_coa_spacer_widths(self) -> None:
        """Give Payee and COA equal widths (~25% of viewport slack each); spacer absorbs the remainder."""
        hdr = self._table.horizontalHeader()
        if hdr.isSectionHidden(_COL_PAYEE) or hdr.isSectionHidden(_COL_COA):
            return
        if hdr.sectionResizeMode(_COL_PAYEE) != QHeaderView.ResizeMode.Interactive:
            return
        if hdr.sectionResizeMode(_COL_COA) != QHeaderView.ResizeMode.Interactive:
            return
        vp_w = int(self._table.viewport().width())
        if vp_w < 120:
            return
        s_other = 0
        for c in range(self._table.columnCount()):
            if c in (_COL_PAYEE, _COL_COA, _COL_SPACER):
                continue
            if hdr.isSectionHidden(c):
                continue
            s_other += hdr.sectionSize(c)
        flex = vp_w - s_other
        min_pair = 2 * _REGISTER_PAYEE_COLUMN_MIN_WIDTH_PX + 32
        if flex < min_pair:
            return
        each = max(
            _REGISTER_PAYEE_COLUMN_MIN_WIDTH_PX,
            int(flex * _REGISTER_PAYEE_COA_SLACK_FRACTION_EACH),
        )
        hdr.blockSignals(True)
        try:
            hdr.resizeSection(_COL_PAYEE, each)
            hdr.resizeSection(_COL_COA, each)
        finally:
            hdr.blockSignals(False)

    def _restore_default_reconciliation_header_geometry(self) -> None:
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(_COL_DATE, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(_COL_REF, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(_COL_PAYEE, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(_COL_MEMO, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(_COL_DEBIT, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(_COL_CREDIT, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(_COL_CLR, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(_COL_BAL, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(_COL_COA, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(_COL_LINK, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(_COL_SPACER, QHeaderView.ResizeMode.Stretch)

    def _apply_normal_register_header_resize_modes(self) -> None:
        """Non-reconciliation: Interactive Payee + COA; spacer Stretch (widths synced via _sync_payee_coa_spacer_widths)."""
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(_COL_DATE, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(_COL_REF, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(_COL_PAYEE, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(_COL_MEMO, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(_COL_DEBIT, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(_COL_CREDIT, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(_COL_CLR, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(_COL_BAL, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(_COL_COA, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(_COL_SPACER, QHeaderView.ResizeMode.Stretch)

    def _apply_register_column_layout(self) -> None:
        """Show full register columns in reconciliation mode; slim visible columns when off (UI only)."""
        hdr = self._table.horizontalHeader()
        hdr.blockSignals(True)
        try:
            if self._reconciliation_mode:
                if self._recon_header_snapshot is not None:
                    snap = self._recon_header_snapshot
                    self._recon_header_snapshot = None
                    hdr.restoreState(snap)
                else:
                    self._restore_default_reconciliation_header_geometry()
                hdr.setSectionHidden(_COL_MEMO, True)
                hdr.setSectionHidden(_COL_CLR, False)
                hdr.setSectionHidden(_COL_LINK, False)
                hdr.setSectionHidden(_COL_COA, False)
                hdr.setSectionHidden(_COL_SPACER, False)
            else:
                hdr.setSectionHidden(_COL_MEMO, False)
                hdr.setSectionHidden(_COL_CLR, False)
                hdr.setSectionHidden(_COL_LINK, True)
                hdr.setSectionHidden(_COL_COA, True)
                hdr.setSectionHidden(_COL_SPACER, False)
                self._apply_normal_register_header_resize_modes()
        finally:
            hdr.blockSignals(False)
        self._ensure_payee_column_resize_policy()
        self._sync_payee_coa_spacer_widths()

    def _clear_table(self):
        self._recon_txn_status.clear()
        self._recon_overlay_bank_import_mode = False
        self._populating = True
        self._table.setSortingEnabled(False)
        self._table.blockSignals(True)
        self._table.setRowCount(_REGISTER_MIN_VISIBLE_ROWS)
        for r in range(_REGISTER_MIN_VISIBLE_ROWS):
            self._fill_pad_row(r)
        self._table.blockSignals(False)
        self._populating = False
        self._register_ending_balance = None
        self._set_footer(0.0, 0.0, 0.0)
        self._refresh_all_recon_cells()

    def _on_reconciliation_mode_toggled(self, checked: bool) -> None:
        was_recon = self._reconciliation_mode
        self._reconciliation_mode = bool(checked)
        self._recon_banner.setVisible(self._reconciliation_mode)
        if was_recon and not self._reconciliation_mode:
            self._recon_header_snapshot = self._table.horizontalHeader().saveState()
        self._apply_register_column_layout()
        if not self._reconciliation_mode:
            self._recon_txn_status.clear()
            self._recon_overlay_bank_import_mode = False
        self._reload_current()
        self._sync_register_info_footer_visibility()
        self.reconciliationModeChanged.emit(self._reconciliation_mode)

    def apply_line_match_results_from_import(
        self, bank_account_id: int, results: list[dict]
    ) -> bool:
        """
        Apply Bank Import **Run extract & compare** results to the **Match** column statement overlay.

        Enables reconciliation mode, selects the same bank account when possible, and preserves
        statuses across F5 / filter reloads until the user turns reconciliation off or switches account.

        Returns False if *bank_account_id* is not in the register account list; reconciliation
        mode is left off in that case (after a combo refresh).
        """
        self._refresh_account_combo()
        self._recon_overlay_bank_import_mode = True
        self._recon_txn_status.clear()
        for res in results:
            rid = res.get("register_id")
            rk = coerce_combo_int_id(rid)
            if rk is None:
                continue
            self._recon_txn_status[rk] = str(res.get("status") or "")
        self._recon_checkbox.blockSignals(True)
        self._recon_checkbox.setChecked(True)
        self._recon_checkbox.blockSignals(False)
        self._reconciliation_mode = True
        self._recon_banner.setVisible(True)
        self._apply_register_column_layout()
        want_acct = coerce_combo_int_id(bank_account_id)
        if want_acct is None or not self._select_bank_account_for_overlay(want_acct):
            self._recon_checkbox.blockSignals(True)
            self._recon_checkbox.setChecked(False)
            self._recon_checkbox.blockSignals(False)
            self._on_reconciliation_mode_toggled(False)
            return False
        self._sync_register_info_footer_visibility()
        self.reconciliationModeChanged.emit(True)
        return True

    def _select_bank_account_for_overlay(self, bank_account_id: int) -> bool:
        """Align combo + settings with *bank_account_id* without clearing Bank Import overlay state."""
        want = coerce_combo_int_id(bank_account_id)
        if want is None:
            return False
        self._acct_combo.blockSignals(True)
        ix = combo_index_for_int_user_data(self._acct_combo, want)
        if ix is not None:
            self._acct_combo.setCurrentIndex(ix)
        self._acct_combo.blockSignals(False)
        if ix is None:
            return False
        self._current_account_id = want
        QSettings().setValue(
            self._register_bank_account_settings_key(), want
        )
        self._load_transactions(want)
        return True

    def select_bank_account(self, bank_account_id: int) -> bool:
        """Select *bank_account_id* (Chart of Accounts double-click / Use Register OK)."""
        self._refresh_account_combo()
        want = coerce_combo_int_id(bank_account_id)
        if want is None:
            return False
        return self._select_bank_account_for_overlay(want)

    def _on_one_line_toggled(self, checked: bool) -> None:
        self._one_line = bool(checked)
        delg = self._table.itemDelegate()
        if isinstance(delg, RegisterBandDelegate):
            delg._simple = self._one_line
        h = 24 if self._one_line else REGISTER_ROW_HEIGHT_MIN_FULL
        self._table.verticalHeader().setDefaultSectionSize(h)
        self._reload_current()

    def _on_sort_changed(self) -> None:
        data = self._sort_combo.currentData()
        self._sort_mode = str(data or "date_type_ref")
        self._reload_current()

    def _on_goto(self) -> None:
        text, ok = QInputDialog.getText(
            self,
            "Go to...",
            "Date, Number / Ref, Payee, or Amount:",
        )
        if not ok:
            return
        needle_raw = (text or "").strip()
        if not needle_raw:
            return
        from desktop_app.find_matchers import (
            parse_amount_needle,
            parse_date_needle,
        )

        needle = needle_raw.lower()
        amt_target = parse_amount_needle(needle_raw)
        iso_target = parse_date_needle(needle_raw)

        for r in range(self._table.rowCount()):
            d_it = self._table.item(r, _COL_DATE)
            n_it = self._table.item(r, _COL_REF)
            p_it = self._table.item(r, _COL_PAYEE)
            deb_it = self._table.item(r, _COL_DEBIT)
            cred_it = self._table.item(r, _COL_CREDIT)
            dtxt = (d_it.text() if d_it else "").strip()
            ntxt = (n_it.text() if n_it else "").replace("\n", " ").lower()
            ptxt = (p_it.text() if p_it else "").replace("\n", " ").lower()
            hit = False
            if needle in dtxt.lower() or needle in ntxt or needle in ptxt:
                hit = True
            if not hit and iso_target is not None:
                # Table date column may render "MM/DD/YYYY"; parse it back for comparison.
                if parse_date_needle(dtxt) == iso_target:
                    hit = True
            if not hit and amt_target is not None:
                for txt_item in (deb_it, cred_it):
                    if txt_item is None:
                        continue
                    cell = parse_amount_needle(txt_item.text())
                    if cell is not None and abs(cell - amt_target) < 0.005:
                        hit = True
                        break
            if hit:
                self._table.selectRow(r)
                if d_it is not None:
                    self._table.scrollToItem(d_it)
                return
        message_box_information_ok(
            self,
            "Go to...",
            f"No register line matches “{needle_raw}”.",
            ok_tip="Close; try another date, number, payee, or amount.",
        )

    def _on_print_register(self) -> None:
        message_box_information_ok(
            self,
            "Print...",
            "Register printing uses the company printer in a later release. "
            "Export CSV from Recon → Register Actions in the meantime.",
            ok_tip="Close.",
        )

    def _on_quickreport(self) -> None:
        name = self._acct_combo.currentText() if hasattr(self, "_acct_combo") else "Account"
        n = 0
        for r in range(self._table.rowCount()):
            it = self._table.item(r, _COL_DATE)
            if it is not None and coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole)) is not None:
                n += 1
        message_box_information_ok(
            self,
            "QuickReport",
            f"{name}\n\n{n} transaction(s) in this register.",
            ok_tip="Close.",
        )

    def _on_setup_bank_feeds(self) -> None:
        self.openBankFeedsRequested.emit()

    def _selected_txn_id(self) -> Optional[int]:
        ids = self._selected_txn_ids()
        return ids[0] if ids else None

    def _on_edit_selected_transaction(self) -> None:
        tid = self._selected_txn_id()
        if tid is None:
            return
        txn = self._db.get_transaction(tid)
        if txn is None:
            return
        d = dict(txn)
        tag = _register_number_type_tag(d)
        if tag == "BILLPMT":
            try:
                from probooksai import business

                link = business.bank_match_link_for_navigation(self._db._conn, tid)
            except Exception:
                link = None
            if link is not None:
                self.openBankMatchNavigationRequested.emit(str(link[0]), int(link[1]))
                return
            self.openBankMatchNavigationRequested.emit("ap_payment", 0)
            return
        if tag == "DEP":
            self.openInDepositScreenRequested.emit(int(tid))
            return
        self.openInCheckScreenRequested.emit(int(tid))

    def _on_record_entry(self) -> None:
        """Save the first blank (pad) row that has a date and amount."""
        if self._current_account_id is None:
            return
        for r in range(self._table.rowCount()):
            d_it = self._table.item(r, _COL_DATE)
            if d_it is None:
                continue
            if coerce_combo_int_id(d_it.data(Qt.ItemDataRole.UserRole)) is not None:
                continue
            date_s = (d_it.text() or "").strip()
            pay = (self._table.item(r, _COL_PAYEE).text() if self._table.item(r, _COL_PAYEE) else "").strip()
            if pay in {"Payee", "Account"}:
                pay = ""
            ref_it = self._table.item(r, _COL_REF)
            ref = (ref_it.text() or "").strip() if ref_it else ""
            if ref in {"Number", "TYPE"}:
                ref = ""
            memo_it = self._table.item(r, _COL_MEMO)
            memo = (memo_it.text() or "").strip() if memo_it else ""
            pay_amt = (self._table.item(r, _COL_DEBIT).text() if self._table.item(r, _COL_DEBIT) else "").strip()
            dep_amt = (self._table.item(r, _COL_CREDIT).text() if self._table.item(r, _COL_CREDIT) else "").strip()
            amt = 0.0
            try:
                if dep_amt:
                    amt = abs(parse_amount(dep_amt))
                elif pay_amt:
                    amt = -abs(parse_amount(pay_amt))
            except (TypeError, ValueError):
                amt = 0.0
            if not date_s or abs(amt) < 0.005:
                continue
            ymd = parse_flexible_date_to_ymd(date_s)
            if not ymd:
                message_box_warning_ok(
                    self,
                    "Record",
                    "Enter a valid date on the blank entry row.",
                    ok_tip="Close; use a US date such as 8/27/2026.",
                )
                return
            try:
                self._db.insert_manual_transaction(
                    self._current_account_id,
                    ymd,
                    amt,
                    description=pay,
                    ref_number=ref.split("\n", 1)[0],
                    memo=memo,
                )
            except ValueError as exc:
                message_box_warning_ok(
                    self,
                    "Record",
                    escape_ampersand_for_qt(str(exc)),
                    ok_tip="Close; fix the entry row and try again.",
                )
                return
            self._reload_current()
            return
        self.tools_register_add_transaction()

    def _on_restore_entry(self) -> None:
        self._reload_current()

    def handoff_line_reconciliation_row(
        self,
        *,
        bank_account_id: int,
        row: dict,
        focus_bank_register_tab: Optional[Callable[[], None]] = None,
    ) -> bool:
        """Switch to Bank Register for this account, then select a register line or open **Add transaction** with drafts.

        Does not post except when the user accepts **Add transaction** (same as Recon → Add transaction…).
        """
        want = coerce_combo_int_id(bank_account_id)
        if want is None or not self._select_bank_account_for_overlay(want):
            return False
        if focus_bank_register_tab is not None:
            focus_bank_register_tab()
        status = str(row.get("status") or "")
        rid = coerce_combo_int_id(row.get("register_id"))
        if status == STATUS_NEEDS_REVIEW:
            self._open_add_transaction_prefilled_from_reconcile(row)
            return True
        if rid is not None:
            if not self._focus_transaction_by_id(rid):
                message_box_warning_ok(
                    self,
                    "Open in Bank Register",
                    "That register transaction is not on the grid in the current view. "
                    "The filter was set to **All transactions** once; if it still does not appear, "
                    "refresh (F5) or check that the line exists for this account.",
                    ok_tip="Close; set Filter to All transactions and try again.",
                )
            return True
        return False

    def send_line_reconciliation_to_register_draft(
        self,
        *,
        bank_account_id: int,
        row: dict,
        focus_bank_register_tab: Optional[Callable[[], None]] = None,
    ) -> str:
        """Open an **Add transaction** draft prefilled from Reconcile, or focus a register line for review.

        Does not post except when the user saves **Add transaction**. Returns a short result code for UI state.

        Returns:
            ``"posted"`` — New manual transaction was saved from **Add transaction**.
            ``"cancelled"`` — **Add transaction** was dismissed without saving.
            ``"focused"`` — An existing register line was selected (e.g. **Extra**).
            ``"failed"`` — Account selection failed, or no register line to focus.
        """
        want = coerce_combo_int_id(bank_account_id)
        if want is None or not self._select_bank_account_for_overlay(want):
            return "failed"
        if focus_bank_register_tab is not None:
            focus_bank_register_tab()
        status = str(row.get("status") or "")
        rid = coerce_combo_int_id(row.get("register_id"))

        if status in (STATUS_NEEDS_REVIEW, STATUS_LIKELY_MATCH):
            if self._open_add_transaction_prefilled_from_reconcile(row):
                return "posted"
            return "cancelled"

        if status == STATUS_EXTRA:
            if rid is None:
                return "failed"
            if self._focus_transaction_by_id(rid):
                return "focused"
            message_box_warning_ok(
                self,
                "Send to Register Draft",
                "That register transaction is not on the grid in the current view. "
                "The filter was set to **All transactions** once; if it still does not appear, "
                "refresh (F5) or check that the line exists for this account.",
                ok_tip="Close; set Filter to All transactions and try again.",
            )
            return "failed"

        return "failed"

    def _focus_transaction_by_id(self, txn_id: int) -> bool:
        tid = coerce_combo_int_id(txn_id)
        if tid is None:
            return False

        def scan() -> int:
            for r in range(self._table.rowCount()):
                id_it = self._table.item(r, _COL_DATE)
                if id_it is None:
                    continue
                row_tid = coerce_combo_int_id(id_it.data(Qt.ItemDataRole.UserRole))
                if row_tid == tid:
                    return r
            return -1

        row = scan()
        if row < 0 and self._filter_combo.currentIndex() != 0:
            self._filter_combo.blockSignals(True)
            self._filter_combo.setCurrentIndex(0)
            self._filter_combo.blockSignals(False)
            self._reload_current()
            row = scan()
        if row < 0:
            return False
        id_it = self._table.item(row, _COL_DATE)
        if id_it is None:
            return False
        self._table.setCurrentCell(row, _COL_DATE)
        self._table.scrollToItem(id_it, QAbstractItemView.ScrollHint.PositionAtCenter)
        return True

    def _open_add_transaction_prefilled_from_reconcile(self, row: dict) -> bool:
        """**Add transaction** with Reconcile drafts (date, amount, payee, COA, notes, hint). Returns True if saved."""
        if self._current_account_id is None:
            return False
        aid = self._current_account_id
        coa_key = self._register_manual_entry_last_coa_key(aid)
        raw_saved = QSettings().value(coa_key, "")
        saved_coa = str(raw_saved or "").strip()
        draft_coa = str(row.get("draft_coa_account") or "").strip()
        suggested_coa = str(row.get("suggested_coa") or "").strip()
        initial_coa = draft_coa or suggested_coa or saved_coa
        stmt_date = str(row.get("stmt_date") or "").strip()[:10]
        latest_date = self._db.latest_txn_date_for_account(aid)
        initial_txn_date = stmt_date if stmt_date else latest_date
        sa = row.get("stmt_amount")
        try:
            initial_amt = float(sa) if sa is not None else None
        except (TypeError, ValueError):
            initial_amt = None
        desc = str(row.get("stmt_description") or "").strip()
        suggested_payee = str(row.get("suggested_payee") or "").strip()
        if not desc and suggested_payee:
            desc = suggested_payee
        notes = str(row.get("review_notes") or "").strip()
        memo_parts: list[str] = []
        if notes:
            memo_parts.append(notes)
        hint = str(row.get("suggestion_source") or "").strip()
        if hint:
            memo_parts.append(f"Reconcile hint: {hint}")
        if suggested_payee and suggested_payee.casefold() != desc.casefold():
            memo_parts.append(f"Suggested payee (reconcile): {suggested_payee}")
        initial_memo = "\n".join(memo_parts)
        dlg = ManualTransactionDialog(
            self,
            coa_choices=self._coa_choices,
            conn=self._db._conn,
            initial_coa=initial_coa,
            initial_txn_date=initial_txn_date or None,
            initial_amount=initial_amt,
            initial_description=desc,
            initial_memo=initial_memo,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return False
        v = dlg.values()
        try:
            self._db.insert_manual_transaction(
                aid,
                v["txn_date"],
                float(v["amount"]),
                description=v["description"],
                ref_number=v["ref_number"],
                memo=v["memo"],
                coa_account=v.get("coa_account") or "",
            )
        except sqlite3.IntegrityError as exc:
            message_box_warning_ok(
                self,
                "Cannot save",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; this row collided with an existing fingerprint (rare). Try again.",
            )
            return False
        picked = (v.get("coa_account") or "").strip()
        s = QSettings()
        if picked:
            s.setValue(coa_key, picked)
        else:
            s.remove(coa_key)
        self._reload_current()
        return True

    def _maybe_fill_demo_reconciliation_overlay(self, register_dicts: list[dict]) -> None:
        """Demo Matched / Missing / Extra from mock statement extract (no separate view)."""
        if not self._reconciliation_mode:
            self._recon_txn_status.clear()
            self._recon_overlay_bank_import_mode = False
            return
        if self._recon_overlay_bank_import_mode:
            return
        self._recon_txn_status.clear()
        if not register_dicts:
            return
        stmt = mock_statement_lines_for_comparison(register_dicts)
        for res in compare_statement_to_register(stmt, register_dicts):
            rk = coerce_combo_int_id(res.get("register_id"))
            if rk is None:
                continue
            self._recon_txn_status[rk] = str(res.get("status") or "")

    def _refresh_all_recon_cells(self) -> None:
        ro_flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        recon = self._reconciliation_mode
        src = (
            "Bank Import line match"
            if self._recon_overlay_bank_import_mode
            else "Mock statement line"
        )
        for r in range(self._table.rowCount()):
            id_it = self._table.item(r, _COL_DATE)
            tid = None
            if id_it is not None:
                tid = coerce_combo_int_id(id_it.data(Qt.ItemDataRole.UserRole))
            link_it = self._table.item(r, _COL_LINK)
            if link_it is None:
                continue
            link_it.setFlags(ro_flags)
            link_it.setBackground(QBrush())
            memo_plain = ""
            memo_it = self._table.item(r, _COL_MEMO)
            if memo_it is not None:
                raw_m = memo_it.data(QTABLE_PLAIN_TEXT_ROLE)
                if isinstance(raw_m, str):
                    memo_plain = raw_m.strip()
                else:
                    memo_plain = (memo_it.text() or "").strip()
            base_tip = link_it.data(REGISTER_LINK_BASE_TOOLTIP)
            if not isinstance(base_tip, str):
                base_tip = link_it.toolTip() or ""
            up = link_it.data(REGISTER_LINK_UPPER_PLAIN)
            if not isinstance(up, str):
                up = (link_it.text() or "").split("\n", 1)[0]
            up = (up or "").strip()
            if tid is None:
                link_it.setData(REGISTER_LINK_UPPER_PLAIN, "")
                link_it.setData(REGISTER_LINK_LOWER_PLAIN, "")
                link_it.setText("")
                link_it.setData(QTABLE_PLAIN_TEXT_ROLE, "")
                link_it.setToolTip(
                    "Practice row — not in the database. Statement line-match status is blank."
                )
                continue
            st = ""
            stmt_tip = ""
            if recon:
                st = (self._recon_txn_status.get(tid, "") or "").strip()
                if st == STATUS_MATCHED:
                    stmt_tip = f"{src}: matched this register transaction."
                elif st == STATUS_LIKELY_MATCH:
                    stmt_tip = (
                        f"{src}: likely match — review the pair in Reconcile → Bank statements."
                    )
                elif st == STATUS_NEEDS_REVIEW:
                    stmt_tip = f"{src}: needs review — no confident register match."
                elif st == STATUS_EXTRA:
                    stmt_tip = (
                        f"{src}: register line with no statement counterpart (demo)."
                    )
            link_it.setData(REGISTER_LINK_UPPER_PLAIN, up)
            link_it.setData(REGISTER_LINK_LOWER_PLAIN, st if recon else "")
            if recon and st:
                combined_raw = f"{up}\n{st}" if up else st
            else:
                combined_raw = up
            link_it.setText(escape_ampersand_for_qt(combined_raw))
            link_it.setData(QTABLE_PLAIN_TEXT_ROLE, combined_raw)
            blocks: list[str] = []
            if base_tip.strip():
                blocks.append(base_tip.strip())
            if memo_plain:
                blocks.append(escape_ampersand_for_qt(f"Memo: {memo_plain}"))
            if stmt_tip:
                blocks.append(stmt_tip)
            link_it.setToolTip("\n\n".join(blocks) if blocks else "")

    def _apply_payee_two_line_to_item(self, it: QTableWidgetItem, txn: dict) -> None:
        raw = _register_payee_two_line_plain(txn)
        it.setText(escape_ampersand_for_qt(raw))
        it.setData(QTABLE_PLAIN_TEXT_ROLE, raw)
        it.setData(REGISTER_PAYEE_UPPER_PLAIN, _payee_line1_plain(txn))
        it.setData(REGISTER_PAYEE_LOWER_PLAIN, _payee_line2_account_plain(txn))
        it.setToolTip(escape_ampersand_for_qt(raw))

    def _resize_register_row(self, row: int) -> None:
        self._table.resizeRowToContents(row)
        if self._table.rowHeight(row) < REGISTER_ROW_HEIGHT_MIN_FULL:
            self._table.setRowHeight(row, REGISTER_ROW_HEIGHT_MIN_FULL)

    def _fill_pad_row(self, row: int, *, entry_placeholders: bool = False) -> None:
        """Editable practice row (no txn id); not persisted. Keeps the register grid visibly filled."""
        edit_flags = (
            Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsEditable
        )
        ro_flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        top_left = Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        right_top = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop

        d_it = QTableWidgetItem("")
        d_it.setFlags(edit_flags)
        d_it.setTextAlignment(top_left)
        d_it.setToolTip(
            "Practice row: date is not saved until you use Add transaction…. "
            "You can type dates in common US forms; valid entries normalize to MM/DD/YYYY."
        )
        d_it.setData(REGISTER_MISSING_COA_ROLE, False)
        self._table.setItem(row, _COL_DATE, d_it)

        ref_it = QTableWidgetItem("Number" if entry_placeholders else "")
        ref_it.setFlags(edit_flags)
        ref_it.setTextAlignment(top_left)
        ref_it.setToolTip("Practice row: not saved to the database.")
        ref_it.setData(REGISTER_REF_UPPER_PLAIN, "Number" if entry_placeholders else "")
        ref_it.setData(REGISTER_REF_LOWER_PLAIN, "" if not entry_placeholders else "")
        self._table.setItem(row, _COL_REF, ref_it)

        pay_it = QTableWidgetItem("Payee" if entry_placeholders else "")
        pay_it.setFlags(edit_flags)
        pay_it.setTextAlignment(top_left)
        pay_it.setToolTip("Practice row: not saved to the database.")
        pay_it.setData(REGISTER_PAYEE_UPPER_PLAIN, "Payee" if entry_placeholders else "")
        pay_it.setData(REGISTER_PAYEE_LOWER_PLAIN, "Account" if entry_placeholders else "")
        self._table.setItem(row, _COL_PAYEE, pay_it)

        memo_it = plain_display_table_item("")
        memo_it.setFlags(ro_flags)
        memo_it.setTextAlignment(top_left)
        memo_it.setToolTip("Practice row: not saved to the database.")
        self._table.setItem(row, _COL_MEMO, memo_it)

        deb_it = QTableWidgetItem("")
        deb_it.setFlags(edit_flags)
        deb_it.setTextAlignment(right_top)
        deb_it.setToolTip("Practice row: debit amount is UI-only here.")
        self._table.setItem(row, _COL_DEBIT, deb_it)

        cred_it = QTableWidgetItem("")
        cred_it.setFlags(edit_flags)
        cred_it.setTextAlignment(right_top)
        cred_it.setToolTip("Practice row: credit amount is UI-only here.")
        self._table.setItem(row, _COL_CREDIT, cred_it)

        clr_it = plain_display_table_item("")
        clr_it.setFlags(ro_flags)
        clr_it.setTextAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
        )
        clr_it.setToolTip("Practice row: Clr applies to saved transactions only.")
        self._table.setItem(row, _COL_CLR, clr_it)

        bal_it = QTableWidgetItem("")
        bal_it.setFlags(ro_flags)
        bal_it.setTextAlignment(right_top)
        bal_it.setToolTip("Practice row: balance is shown for saved rows above.")
        self._table.setItem(row, _COL_BAL, bal_it)

        coa_it = plain_display_table_item("—")
        coa_it.setFlags(ro_flags)
        coa_it.setTextAlignment(top_left)
        coa_it.setToolTip("Practice row: use Add transaction… to save a line, then pick COA.")
        self._table.setItem(row, _COL_COA, coa_it)

        link_it = plain_display_table_item("")
        link_it.setFlags(ro_flags)
        link_it.setTextAlignment(top_left)
        link_it.setToolTip("Practice row: Match applies to saved rows.")
        link_it.setData(REGISTER_LINK_UPPER_PLAIN, "")
        link_it.setData(REGISTER_LINK_LOWER_PLAIN, "")
        link_it.setData(REGISTER_LINK_BASE_TOOLTIP, link_it.toolTip() or "")
        self._table.setItem(row, _COL_LINK, link_it)

        self._resize_register_row(row)

    def _on_add_manual_transaction(self) -> None:
        if self._current_account_id is None:
            message_box_information_ok(
                self,
                "No account",
                "Select a bank account before adding a transaction.",
                ok_tip="Close; choose an account in the Bank account combo, then try again.",
            )
            return
        aid = self._current_account_id
        coa_key = self._register_manual_entry_last_coa_key(aid)
        raw_saved = QSettings().value(coa_key, "")
        saved_coa = str(raw_saved or "").strip()
        latest_date = self._db.latest_txn_date_for_account(aid)
        dlg = ManualTransactionDialog(
            self,
            coa_choices=self._coa_choices,
            conn=self._db._conn,
            initial_coa=saved_coa,
            initial_txn_date=latest_date,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        v = dlg.values()
        try:
            self._db.insert_manual_transaction(
                aid,
                v["txn_date"],
                float(v["amount"]),
                description=v["description"],
                ref_number=v["ref_number"],
                memo=v["memo"],
                coa_account=v.get("coa_account") or "",
            )
        except sqlite3.IntegrityError as exc:
            message_box_warning_ok(
                self,
                "Cannot save",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; this row collided with an existing fingerprint (rare). Try again.",
            )
            return
        picked = (v.get("coa_account") or "").strip()
        s = QSettings()
        if picked:
            s.setValue(coa_key, picked)
        else:
            s.remove(coa_key)
        self._reload_current()

    def _register_filter_param(self) -> Optional[str]:
        data = self._filter_combo.currentData()
        if data in (None, "all"):
            return None
        return str(data)

    def _selected_txn_ids(self) -> list:
        sel_rows = sorted({i.row() for i in self._table.selectedIndexes()})
        ids: list = []
        for r in sel_rows:
            it = self._table.item(r, _COL_DATE)
            if it is None:
                continue
            tid = coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole))
            if tid is not None:
                ids.append(tid)
        return ids

    def _on_register_cell_double_clicked(self, row: int, col: int) -> None:
        """Double-click **Clr** toggles cleared; double-click **Match** opens the linked Business record."""
        if col == _COL_LINK:
            id_item = self._table.item(row, _COL_DATE)
            if id_item is None:
                return
            tid = coerce_combo_int_id(id_item.data(Qt.ItemDataRole.UserRole))
            if tid is None:
                return
            self.open_linked_business_record_for_transaction_id(tid)
            return
        if col == _COL_COA:
            coa = _register_row_coa_user_data(self._table, row).strip()
            if coa:
                self.openCoaEditorRequested.emit(coa)
            return
        if col == _COL_CLR:
            id_item = self._table.item(row, _COL_DATE)
            if id_item is None:
                return
            tid = coerce_combo_int_id(id_item.data(Qt.ItemDataRole.UserRole))
            if tid is None:
                return
            txn = self._db.get_transaction(tid)
            if txn is None:
                return
            cur = int(dict(txn).get("cleared") or 0) == 1
            try:
                self._db.update_transaction(tid, cleared=0 if cur else 1)
            except ValueError as exc:
                message_box_warning_ok(
                    self,
                    "Cannot update",
                    escape_ampersand_for_qt(str(exc)),
                    ok_tip="Close; cleared state may be blocked for posted or reconciled rows.",
                )
                return
            self._reload_current()
            return
        self._on_edit_selected_transaction()

    def _show_register_keyboard_shortcuts_help(self) -> None:
        show_register_keyboard_shortcuts_dialog(self)

    def _on_register_context_menu(self, pos):
        idx = self._table.indexAt(pos)
        menu = QMenu(self)
        act_keys = menu.addAction(
            "Keyboard shortcuts…", self._show_register_keyboard_shortcuts_help
        )
        act_keys.setToolTip(
            "Same summary as Help → Bank register keyboard shortcuts… "
            "(F5, export, post, cleared chords; AI line-reconciliation field copies: use the Bank import link "
            "in that Help dialog). "
            + VIEW_BANK_REGISTER_KEYS_TOOLTIP
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        if not idx.isValid():
            menu.exec(self._table.viewport().mapToGlobal(pos))
            return
        row = idx.row()
        it = self._table.item(row, _COL_DATE)
        tid = (
            coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole)) if it is not None else None
        )
        if tid is None:
            menu.exec(self._table.viewport().mapToGlobal(pos))
            return
        nav_ok = business.bank_match_is_navigable(self._db._conn, tid)
        menu.addSeparator()
        if nav_ok:
            act_open_biz = menu.addAction(
                "Open linked Business record…",
                partial(self.open_linked_business_record_for_transaction_id, tid),
            )
            act_open_biz.setToolTip(
                "Switch to the Business tab: open the invoice or bill editor, payroll tax lines, "
                "or a short summary for AR/AP payments."
            )
        act_att = menu.addAction(
            "Open attachment…",
            partial(self._open_register_attachment, tid),
        )
        act_att.setToolTip("Open the linked file for this register row if a path is set.")
        act_clr = menu.addAction(
            "Mark cleared",
            partial(self._set_cleared_on_ids, [tid], 1),
        )
        act_clr.setToolTip("Set the cleared flag on this row (register cleared column).")
        act_uclr = menu.addAction(
            "Clear cleared",
            partial(self._set_cleared_on_ids, [tid], 0),
        )
        act_uclr.setToolTip("Clear the cleared flag on this row.")
        act_copy = menu.addAction("Copy row", partial(copy_table_row_as_tsv, self._table, row))
        act_copy.setToolTip(
            "Copy this register row as tab-separated text for pasting into a spreadsheet or editor. "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        act_copy_tid = menu.addAction(
            "Copy transaction id", partial(self._copy_register_txn_id, tid)
        )
        act_copy_tid.setToolTip(
            "Copy the internal database id for this row (bank_transactions.id); matches **Reg #** in Bank Import line reconciliation. "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        act_copy_date = menu.addAction("Copy date", partial(self._copy_register_row_txn_date, row))
        act_copy_date.setToolTip(
            "Copy the transaction date stored on this row (typically YYYY-MM-DD). "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        act_copy_amt = menu.addAction("Copy amount", partial(self._copy_register_row_amount, row))
        act_copy_amt.setToolTip(
            "Copy the signed amount (two decimals): positive = deposit / inflow, negative = payment / outflow—same as CSV import. "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        act_copy_desc = menu.addAction(
            "Copy payee / description", partial(self._copy_register_row_payee_description, row)
        )
        act_copy_desc.setToolTip(
            "Copy the payee or description text stored on this transaction (same field as the Payee column’s upper line). "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        act_edit_memo = menu.addAction(
            "Edit memo…", partial(self._edit_register_memo, tid)
        )
        act_edit_memo.setToolTip(
            "Edit the memo stored on this transaction (the Memo grid column is hidden). "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        act_copy_memo = menu.addAction("Copy memo", partial(self._copy_register_row_memo, row))
        act_copy_memo.setToolTip(
            "Copy the memo text stored on this transaction. "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        act_copy_ref = menu.addAction(
            "Copy number / ref", partial(self._copy_register_row_ref_number, row)
        )
        act_copy_ref.setToolTip(
            "Copy the check number or bank reference stored on this transaction (Number column). "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        act_copy_coa = menu.addAction(
            "Copy category (COA)", partial(self._copy_register_row_coa, row)
        )
        act_copy_coa.setToolTip(
            "Copy the saved category line (plain COA string from the dropdown) for rules, COA search, or notes. "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        coa_disp = _register_row_coa_user_data(self._table, row).strip()
        act_open_coa = menu.addAction(
            "Open category in Chart of Accounts…",
            partial(self._open_register_row_coa_in_chart_tab, row),
        )
        act_open_coa.setToolTip(
            "Switch to the Chart of Accounts tab and select this category when it exists in the chart. "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        act_open_coa.setEnabled(bool(coa_disp))
        act_history = menu.addAction("View change history…")
        act_history.setToolTip(
            "Open field-level audit history for this bank transaction."
        )

        act_open_checks = menu.addAction(
            "Open in Write Checks…",
            partial(self.openInCheckScreenRequested.emit, tid),
        )
        act_open_checks.setToolTip(
            "Jump to the Write Checks tab and display this transaction in the check form."
        )

        # ── Destructive actions ────────────────────────────────────────────
        menu.addSeparator()
        # Label context-aware: deposit vs payment
        it_date = self._table.item(row, _COL_DATE)
        it_debit = self._table.item(row, _COL_DEBIT)
        it_credit = self._table.item(row, _COL_CREDIT)
        _debit_text = (it_debit.text().strip() if it_debit else "")
        _credit_text = (it_credit.text().strip() if it_credit else "")
        _is_credit = bool(_credit_text and _credit_text not in ("", "$0.00", "0.00"))
        _txn_label = "payment" if _is_credit else "deposit"
        act_delete = menu.addAction(f"🗑  Delete {_txn_label}…")
        act_delete.setToolTip(
            f"Permanently delete this {_txn_label} from the register. "
            "Posted GL transactions cannot be deleted — void the GL entry first. "
            "Back up with File → Backup before bulk deletions."
        )

        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))
        if chosen == act_history:
            show_entity_audit_history(
                self,
                self._db._conn,
                "bank_transaction",
                tid,
                window_title=f"Change history — transaction #{tid}",
                empty_message="No audit entries recorded for this transaction yet.",
            )
        elif chosen == act_delete:
            self._delete_register_transaction(tid)

    def _delete_register_transaction(self, txn_id: int) -> None:
        """Confirm and delete a bank transaction row; reload the register."""
        txn = self._db.get_transaction(txn_id)
        if txn is None:
            return
        d = dict(txn)
        amt = float(d.get("amount") or 0)
        label = "payment" if amt < 0 else "deposit"
        desc = (d.get("description") or "").strip() or f"#{txn_id}"
        date_s = (d.get("txn_date") or "").strip()
        ans = message_box_question_yes_no(
            self,
            f"Delete {label}?",
            f"Permanently delete this {label}?\n\n"
            f"  Date: {date_s}\n"
            f"  Payee: {desc}\n"
            f"  Amount: ${abs(amt):,.2f}\n\n"
            "This cannot be undone. Back up with File → Backup first.",
            yes_tip=f"Delete this {label} permanently.",
            no_tip="Cancel — keep the transaction.",
        )
        if not ans:
            return
        try:
            self._db.delete_transaction(txn_id)
        except ValueError as exc:
            message_box_warning_ok(
                self,
                "Cannot delete",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; void the GL posting first if posted.",
            )
            return
        self._reload_current()

    def _open_register_row_coa_in_chart_tab(self, row: int) -> None:
        coa = _register_row_coa_user_data(self._table, row).strip()
        if coa:
            self.openCoaEditorRequested.emit(coa)

    def _copy_register_row_coa(self, row: int) -> None:
        QGuiApplication.clipboard().setText(_register_row_coa_user_data(self._table, row))

    def _copy_register_txn_id(self, txn_id: int) -> None:
        QGuiApplication.clipboard().setText(str(int(txn_id)))

    def _register_clip_txn_string_field(self, row: int, key: str) -> None:
        id_item = self._table.item(row, _COL_DATE)
        if id_item is None:
            QGuiApplication.clipboard().setText("")
            return
        tid = coerce_combo_int_id(id_item.data(Qt.ItemDataRole.UserRole))
        if tid is None:
            QGuiApplication.clipboard().setText("")
            return
        txn = self._db.get_transaction(tid)
        if txn is None:
            QGuiApplication.clipboard().setText("")
            return
        text = (dict(txn).get(key) or "").strip()
        QGuiApplication.clipboard().setText(text)

    def _copy_register_row_payee_description(self, row: int) -> None:
        self._register_clip_txn_string_field(row, "description")

    def _edit_register_memo(self, txn_id: int) -> None:
        rec = self._db.get_transaction(txn_id)
        if rec is None:
            return
        cur = dict(rec).get("memo")
        cur_s = cur if isinstance(cur, str) else ""
        text, ok = QInputDialog.getMultiLineText(
            self,
            "Memo",
            "Memo for this register row:",
            text=cur_s,
        )
        if not ok:
            return
        try:
            self._db.update_transaction(txn_id, memo=text)
        except ValueError as exc:
            message_box_warning_ok(
                self,
                "Cannot save",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; fix the value and try again.",
            )
            return
        self._reload_current()

    def _copy_register_row_memo(self, row: int) -> None:
        self._register_clip_txn_string_field(row, "memo")

    def _copy_register_row_ref_number(self, row: int) -> None:
        self._register_clip_txn_string_field(row, "ref_number")

    def _copy_register_row_txn_date(self, row: int) -> None:
        self._register_clip_txn_string_field(row, "txn_date")

    def _copy_register_row_amount(self, row: int) -> None:
        id_item = self._table.item(row, _COL_DATE)
        if id_item is None:
            QGuiApplication.clipboard().setText("")
            return
        tid = coerce_combo_int_id(id_item.data(Qt.ItemDataRole.UserRole))
        if tid is None:
            QGuiApplication.clipboard().setText("")
            return
        txn = self._db.get_transaction(tid)
        if txn is None:
            QGuiApplication.clipboard().setText("")
            return
        amt = float(dict(txn).get("amount") or 0.0)
        QGuiApplication.clipboard().setText(f"{amt:.2f}")

    def _open_register_attachment(self, txn_id: int) -> None:
        row = self._db.get_transaction(txn_id)
        if row is None:
            return
        apath = (dict(row).get("attachment_path") or "").strip()
        open_local_attachment(
            self,
            apath,
            empty_message="No attachment path is set for this transaction.",
        )

    def _load_transactions(self, bank_account_id: int):
        start = self._register_statement_start()
        rows = self._db.list_transactions(
            bank_account_id,
            statement_start=start,
            register_filter=self._register_filter_param(),
        )
        rec_map = _batch_reconciled_map(self._db._conn, rows)
        self._populating = True
        self._table.setSortingEnabled(False)
        self._table.blockSignals(True)
        n_data = len(rows)
        reg_dicts = [dict(t) for t in rows]
        mode = getattr(self, "_sort_mode", "date_type_ref")
        if mode == "ref":
            reg_dicts.sort(
                key=lambda t: (
                    str(t.get("ref_number") or ""),
                    str(t.get("txn_date") or ""),
                    int(t.get("id") or 0),
                )
            )
        elif mode == "date_type_ref":
            reg_dicts.sort(
                key=lambda t: (
                    str(t.get("txn_date") or ""),
                    _register_number_type_tag(t),
                    str(t.get("ref_number") or ""),
                    int(t.get("id") or 0),
                )
            )
        n_vis = max(n_data, _REGISTER_MIN_VISIBLE_ROWS)
        self._table.setRowCount(n_vis)

        running = 0.0
        if start:
            running = self._db.sum_amount_before(bank_account_id, start)
        total_debits = 0.0
        total_credits = 0.0

        pos_color = QColor(AMOUNT_POSITIVE)
        neg_color = QColor(AMOUNT_NEGATIVE)

        for r, txn in enumerate(reg_dicts):
            tid = coerce_combo_int_id(txn.get("id"))
            amt = float(txn["amount"])
            posted = _txn_posted(txn)

            if amt > 0:
                total_debits += amt
            elif amt < 0:
                total_credits += abs(amt)

            running += amt

            missing_coa = not (txn.get("coa_account") or "").strip()

            d_item = _register_date_cell_item(txn.get("txn_date") or "")
            if tid is not None:
                d_item.setData(Qt.ItemDataRole.UserRole, tid)
            if posted:
                d_item.setFlags(d_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            else:
                d_item.setFlags(d_item.flags() | Qt.ItemFlag.ItemIsEditable)
            d_item.setTextAlignment(
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
            )
            d_item.setData(REGISTER_MISSING_COA_ROLE, missing_coa)
            d_date_raw = (txn.get("txn_date") or "").strip()
            d_item.setToolTip(escape_ampersand_for_qt(d_date_raw if d_date_raw else "—"))

            num_plain = _register_number_two_line_plain(txn)
            if posted:
                ref_item = plain_display_table_item(num_plain)
                ref_item.setFlags(ref_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            else:
                ref_item = QTableWidgetItem(escape_ampersand_for_qt(num_plain))
                ref_item.setData(QTABLE_PLAIN_TEXT_ROLE, num_plain)
                ref_item.setFlags(ref_item.flags() | Qt.ItemFlag.ItemIsEditable)
            ref_item.setTextAlignment(
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
            )
            ref_item.setData(REGISTER_REF_UPPER_PLAIN, _register_num_upper_plain(txn))
            ref_item.setData(REGISTER_REF_LOWER_PLAIN, _register_num_lower_plain(txn))
            ref_item.setToolTip(escape_ampersand_for_qt(num_plain))

            payee_plain = _register_payee_two_line_plain(txn)
            payee_item = plain_display_table_item(payee_plain)
            if posted:
                payee_item.setFlags(payee_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            else:
                payee_item.setFlags(payee_item.flags() | Qt.ItemFlag.ItemIsEditable)
            payee_item.setTextAlignment(
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
            )
            payee_item.setData(REGISTER_PAYEE_UPPER_PLAIN, _payee_line1_plain(txn))
            payee_item.setData(REGISTER_PAYEE_LOWER_PLAIN, _payee_line2_account_plain(txn))
            payee_item.setToolTip(escape_ampersand_for_qt(payee_plain))

            memo_raw = txn.get("memo") or ""
            memo_item = plain_display_table_item(memo_raw)
            if posted:
                memo_item.setFlags(memo_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            else:
                memo_item.setFlags(memo_item.flags() | Qt.ItemFlag.ItemIsEditable)
            memo_item.setTextAlignment(
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
            )
            memo_stripped = memo_raw.strip()
            if memo_stripped:
                memo_item.setToolTip(escape_ampersand_for_qt(memo_stripped))
            else:
                memo_item.setToolTip("")

            debit_item = QTableWidgetItem()
            debit_item.setFlags(debit_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            credit_item = QTableWidgetItem()
            credit_item.setFlags(credit_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            bal_item = NumericAmountTableItem(running)
            bal_item.setFlags(bal_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            if amt < 0:
                debit_item = NumericAmountTableItem(abs(amt))
                debit_item.setFlags(debit_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                debit_item.setForeground(neg_color)
            elif amt > 0:
                credit_item = NumericAmountTableItem(amt)
                credit_item.setFlags(credit_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                credit_item.setForeground(pos_color)

            if not posted:
                debit_item.setFlags(debit_item.flags() | Qt.ItemFlag.ItemIsEditable)
                credit_item.setFlags(credit_item.flags() | Qt.ItemFlag.ItemIsEditable)

            if running < 0:
                bal_item.setForeground(neg_color)
            elif running > 0:
                bal_item.setForeground(pos_color)

            for it in (debit_item, credit_item, bal_item):
                it.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
                )

            bal_item.setToolTip(
                escape_ampersand_for_qt(f"Running balance: ${running:,.2f}")
            )
            if amt < 0:
                debit_item.setToolTip(
                    escape_ampersand_for_qt(f"Payment: ${abs(amt):,.2f}")
                )
                credit_item.setToolTip("")
            elif amt > 0:
                credit_item.setToolTip(
                    escape_ampersand_for_qt(f"Deposit: ${amt:,.2f}")
                )
                debit_item.setToolTip("")
            else:
                debit_item.setToolTip("")
                credit_item.setToolTip("")
            # Debit: / Credit: labels kept for contract tests; columns display PAYMENT / DEPOSIT.

            b_key = coerce_combo_int_id(txn.get("batch_id"))
            batch_rec = b_key is not None and rec_map.get(b_key, False)
            txn_cleared = int(txn.get("cleared") or 0) == 1
            if txn_cleared:
                clr_disp = "C"
                clr_tip = "Marked cleared on this register (per transaction)."
                if batch_rec:
                    clr_tip += " Import batch is also marked reconciled."
            elif batch_rec:
                clr_disp = "R"
                clr_tip = "Statement batch reconciled (Bank Import)."
            else:
                clr_disp = ""
                clr_tip = (
                    "Not cleared. Use Mark cleared, or reconcile the CSV batch in Bank Import."
                )
            clr_item = plain_display_table_item(clr_disp)
            clr_item.setFlags(clr_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            clr_item.setTextAlignment(
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
            )
            clr_item.setToolTip(clr_tip)

            self._table.setItem(r, _COL_DATE, d_item)
            self._table.setItem(r, _COL_REF, ref_item)
            self._table.setItem(r, _COL_PAYEE, payee_item)
            self._table.setItem(r, _COL_MEMO, memo_item)
            self._table.setItem(r, _COL_DEBIT, debit_item)
            self._table.setItem(r, _COL_CREDIT, credit_item)
            self._table.setItem(r, _COL_CLR, clr_item)
            self._table.setItem(r, _COL_BAL, bal_item)

            combo = QComboBox()
            combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            combo.addItem("(Uncategorized)", "")
            insert_at = 1
            try:
                for h in coa_hints(
                    self._db._conn,
                    txn.get("description") or "",
                    self._coa_choices,
                    limit=3,
                ):
                    if combo.findData(h) < 0:
                        combo.insertItem(
                            insert_at,
                            escape_ampersand_for_qt(f"★ {h}"),
                            h,
                        )
                        insert_at += 1
            except sqlite3.OperationalError:
                pass
            for label in self._coa_choices:
                combo.addItem(escape_ampersand_for_qt(label), label)
            # Sentinel — opens QuickAddCoaDialog when selected
            combo.addItem("➕  New account…", _NEW_COA_SENTINEL)
            current = (txn.get("coa_account") or "").strip()
            idx = combo.findData(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            elif current:
                combo.addItem(escape_ampersand_for_qt(current), current)
                combo.setCurrentIndex(combo.count() - 1)
            if posted:
                combo.setEnabled(False)
            base_tip = _register_coa_combo_tooltip(
                posted=posted, saved_coa_display=current
            )
            if posted:
                extra = (
                    " Double-click the upper category band or use **Open category in Chart of Accounts…** "
                    "in the row menu to view it in the chart (posted rows are read-only here)."
                )
            else:
                extra = (
                    " Click the upper band to open the list; type to filter by name or number. "
                    "Double-click the upper band or use the row menu to open this category in Chart of Accounts."
                )
            combo.setToolTip(escape_ampersand_for_qt(base_tip + extra))
            if tid is not None:
                combo.currentIndexChanged.connect(
                    partial(self._on_coa_changed, tid, combo)
                )
                _configure_interactive_register_coa_combo(
                    combo, self._coa_choices, tid, self
                )
            coa_frame = CoaBandFrame(combo, self._table, r)
            coa_frame.set_open_coa_callback(self._on_coa_frame_request_open_editor)
            coa_frame.apply_combo_missing_style(missing_coa)
            self._table.setCellWidget(r, _COL_COA, coa_frame)

            bm = None
            if tid is not None:
                try:
                    bm = business.get_bank_match(self._db._conn, tid)
                except sqlite3.OperationalError:
                    bm = None
            link_nav = business.bank_match_link_tuple_from_row(bm)
            link_lbl = _bank_match_label(bm)
            link_item = plain_display_table_item(link_lbl)
            link_item.setFlags(link_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if link_nav is not None and (link_lbl or "").strip():
                tip = escape_ampersand_for_qt(
                    f"Linked AR/AP/payroll or open invoice/bill: {link_lbl}. "
                    "Double-click here or right-click the row → Open linked Business record…. "
                    "Use Link payment… to set or clear."
                )
                link_item.setToolTip(tip)
                link_item.setData(REGISTER_LINK_BASE_TOOLTIP, tip)
            elif (link_lbl or "").strip():
                tip = escape_ampersand_for_qt(
                    f"Link row present ({link_lbl}) but Business navigation is unavailable "
                    "(incomplete type or id). Use Link payment… to clear or re-link."
                )
                link_item.setToolTip(tip)
                link_item.setData(REGISTER_LINK_BASE_TOOLTIP, tip)
            else:
                tip = (
                    "No payment or open invoice/bill link on this row. "
                    "Use Link payment… to add or change one."
                )
                link_item.setToolTip(tip)
                link_item.setData(REGISTER_LINK_BASE_TOOLTIP, tip)
            link_item.setData(REGISTER_LINK_UPPER_PLAIN, link_lbl or "")
            link_item.setData(REGISTER_LINK_LOWER_PLAIN, "")
            link_item.setTextAlignment(
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
            )
            self._table.setItem(r, _COL_LINK, link_item)

            self._resize_register_row(r)

        for r in range(n_data, n_vis):
            self._fill_pad_row(r, entry_placeholders=(r == n_data))

        self._maybe_fill_demo_reconciliation_overlay(reg_dicts)
        self._refresh_all_recon_cells()

        self._table.blockSignals(False)
        self._populating = False
        self._table.setSortingEnabled(True)
        net = total_debits - total_credits
        try:
            ending = self._db.sum_amount_for_account(bank_account_id)
        except sqlite3.Error:
            ending = running if rows else None
        self._set_footer(total_debits, total_credits, net, ending_balance=ending)
        all_dates = self._range_combo.currentData() == 0
        self._btn_older.setEnabled(not all_dates)

    def _set_footer(self, debits: float, credits: float, net: float,
                    ending_balance: float | None = None) -> None:
        self._lbl_debits.setText(f"Debits: ${debits:,.2f}")
        self._lbl_credits.setText(f"Credits: ${credits:,.2f}")
        self._lbl_net.setText(f"Net: ${net:,.2f}")
        if ending_balance is not None:
            self._register_ending_balance = ending_balance
        bal = self._register_ending_balance
        if bal is None:
            self._lbl_ending_balance.setText("—")
            self._lbl_ending_balance.setStyleSheet(
                "background: transparent; border: none; "
                "color: #A0A0B0; font-size: 17px; font-weight: 700;"
            )
        else:
            from desktop_app.theme import AMOUNT_POSITIVE, AMOUNT_NEGATIVE
            color = AMOUNT_NEGATIVE if bal < 0 else AMOUNT_POSITIVE
            self._lbl_ending_balance.setText(f"${bal:,.2f}")
            self._lbl_ending_balance.setStyleSheet(
                f"background: transparent; border: none; "
                f"color: {color}; font-size: 17px; font-weight: 700;"
            )

    def _on_item_changed(self, item: QTableWidgetItem):  # noqa: C901
        if self._populating:
            return
        col = item.column()
        row = item.row()

        # ── Resolve txn_id from the date cell's UserRole ──────────────────────
        id_item = self._table.item(row, _COL_DATE)
        txn_id = coerce_combo_int_id(
            id_item.data(Qt.ItemDataRole.UserRole) if id_item else None
        )

        # ── DATE column ────────────────────────────────────────────────────────
        if col == _COL_DATE:
            raw = item.text().strip()
            if not raw:
                return
            ymd = parse_flexible_date_to_ymd(raw)
            if ymd is None:
                return
            y, m, d = ymd
            disp = format_ymd_as_us(m, d, y)
            self._populating = True
            item.setText(escape_ampersand_for_qt(disp))
            item.setData(QTABLE_PLAIN_TEXT_ROLE, disp)
            self._populating = False
            self._resize_register_row(row)
            if txn_id is not None:
                # Save to DB and reload so running balances recalculate
                try:
                    self._db.update_transaction(
                        txn_id, txn_date=f"{y:04d}-{m:02d}-{d:02d}"
                    )
                except ValueError as exc:
                    message_box_warning_ok(
                        self, "Cannot save date",
                        escape_ampersand_for_qt(str(exc)),
                        ok_tip="Close; fix the date and try again.",
                    )
                    return
                QTimer.singleShot(0, self._reload_current)
            return

        # ── REF column ─────────────────────────────────────────────────────────
        if col == _COL_REF:
            if txn_id is None:
                return
            try:
                ref_first = item.text().split("\n", 1)[0].strip()
                self._db.update_transaction(txn_id, ref_number=ref_first)
                self._populating = True
                fresh = self._db.get_transaction(txn_id)
                if fresh is not None:
                    fd = dict(fresh)
                    num_plain = _register_number_two_line_plain(fd)
                    item.setText(escape_ampersand_for_qt(num_plain))
                    item.setData(QTABLE_PLAIN_TEXT_ROLE, num_plain)
                    item.setData(REGISTER_REF_UPPER_PLAIN, _register_num_upper_plain(fd))
                    item.setData(REGISTER_REF_LOWER_PLAIN, _register_num_lower_plain(fd))
                    item.setToolTip(escape_ampersand_for_qt(num_plain))
                self._populating = False
                self._resize_register_row(row)
            except ValueError as exc:
                message_box_warning_ok(
                    self, "Cannot save",
                    escape_ampersand_for_qt(str(exc)),
                    ok_tip="Close; fix the value and try again.",
                )
            return

        # ── Remaining columns only apply to existing (saved) rows ──────────────
        if txn_id is None:
            return

        # ── PAYEE column ───────────────────────────────────────────────────────
        if col == _COL_PAYEE:
            try:
                payee_text = item.text().split("\n", 1)[0].strip()
                self._db.update_transaction(txn_id, description=payee_text)
                self._populating = True
                item.setData(QTABLE_PLAIN_TEXT_ROLE, payee_text)
                item.setData(REGISTER_PAYEE_UPPER_PLAIN, payee_text)
                item.setToolTip(escape_ampersand_for_qt(payee_text))
                self._populating = False
                self._resize_register_row(row)
            except ValueError as exc:
                message_box_warning_ok(
                    self, "Cannot save payee",
                    escape_ampersand_for_qt(str(exc)),
                    ok_tip="Close; fix the value and try again.",
                )
            return

        # ── MEMO column ────────────────────────────────────────────────────────
        if col == _COL_MEMO:
            try:
                memo_text = item.text().strip()
                self._db.update_transaction(txn_id, memo=memo_text)
                self._populating = True
                item.setData(QTABLE_PLAIN_TEXT_ROLE, memo_text)
                item.setToolTip(escape_ampersand_for_qt(memo_text))
                self._populating = False
                self._resize_register_row(row)
            except ValueError as exc:
                message_box_warning_ok(
                    self, "Cannot save memo",
                    escape_ampersand_for_qt(str(exc)),
                    ok_tip="Close; fix the value and try again.",
                )
            return

        # ── DEBIT column ───────────────────────────────────────────────────────
        if col == _COL_DEBIT:
            raw = item.text().strip().lstrip("$").replace(",", "")
            if not raw:
                raw = "0"
            try:
                val = float(raw)
            except ValueError:
                return
            try:
                # Debit = positive amount
                self._db.update_transaction(txn_id, amount=val if val != 0 else 0.0)
            except ValueError as exc:
                message_box_warning_ok(
                    self, "Cannot save debit",
                    escape_ampersand_for_qt(str(exc)),
                    ok_tip="Close; fix the value and try again.",
                )
                return
            QTimer.singleShot(0, self._reload_current)
            return

        # ── CREDIT column ──────────────────────────────────────────────────────
        if col == _COL_CREDIT:
            raw = item.text().strip().lstrip("$").replace(",", "")
            if not raw:
                raw = "0"
            try:
                val = float(raw)
            except ValueError:
                return
            try:
                # Credit = negative amount (stored as negative in DB)
                self._db.update_transaction(txn_id, amount=-val if val != 0 else 0.0)
            except ValueError as exc:
                message_box_warning_ok(
                    self, "Cannot save credit",
                    escape_ampersand_for_qt(str(exc)),
                    ok_tip="Close; fix the value and try again.",
                )
                return
            QTimer.singleShot(0, self._reload_current)

    def _post_selected(self):
        if self._gl is None or self._current_account_id is None:
            message_box_information_ok(
                self,
                "Posting",
                "GL is not available for this session.",
                ok_tip="Close; open a company .db that includes GL support; back it up with File → Backup / probooks backup.",
            )
            return
        acct = self._db.get_bank_account(self._current_account_id)
        bank_gl = (dict(acct).get("gl_display_account") or "").strip()
        if not bank_gl:
            message_box_warning_ok(
                self,
                "GL mapping",
                "Set the GL cash account on this bank account (Manage Accounts in Bank Import).",
                ok_tip="Close; Bank Import → Manage Accounts → edit this account → map GL cash.",
            )
            return
        sel = sorted({i.row() for i in self._table.selectedIndexes()})
        if not sel:
            message_box_information_ok(
                self,
                "Posting",
                "Select one or more rows.",
                ok_tip="Close; click rows in the register grid, then Post again.",
            )
            return
        posted = 0
        errors: list[str] = []
        for r in sel:
            id_item = self._table.item(r, _COL_DATE)
            if id_item is None:
                continue
            tid = coerce_combo_int_id(id_item.data(Qt.ItemDataRole.UserRole))
            if tid is None:
                continue
            txn = self._db.get_transaction(tid)
            if txn is None:
                continue
            td = dict(txn)
            splits = business.list_splits(self._db._conn, tid)
            if splits:
                missing = [s for s in splits if not (s["coa_account"] or "").strip()]
                if missing:
                    errors.append(f"Txn {tid}: split line(s) missing COA account")
                    continue
                coa_for_post = ""
            elif td.get("transfer_to_bank_account_id") is not None:
                coa_for_post = ""
            else:
                coa_for_post = (td.get("coa_account") or "").strip()
                if not coa_for_post:
                    errors.append(f"Txn {tid}: no COA category")
                    continue
            try:
                self._gl.post_transaction(tid, bank_gl, coa_for_post)
                posted += 1
            except ValueError as exc:
                errors.append(f"Txn {tid}: {exc}")
        self._reload_current()
        msg = f"Posted {posted} transaction(s)."
        if errors:
            msg += "\n\n" + "\n".join(errors[:8])
            if len(errors) > 8:
                msg += "\n…"
        message_box_information_ok(
            self,
            "Posting",
            escape_ampersand_for_qt(msg),
            ok_tip="Close; fix any errors listed, then post remaining rows.",
        )

    def _export_csv(self):
        if self._current_account_id is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export register", "", "CSV (*.csv)"
        )
        if not path:
            return
        rows = self._db.list_transactions(
            self._current_account_id, register_filter=self._register_filter_param()
        )
        rec_map = _batch_reconciled_map(self._db._conn, rows)
        hdr = [
            "Date",
            "Ref",
            "Description",
            "Memo",
            "Amount",
            "COA",
            "Posted",
            "Register_cleared",
            "Batch_reconciled",
            "Match",
        ]
        with open(path, "w", newline="", encoding="utf-8-sig") as fp:
            w = csv.writer(fp)
            w.writerow(hdr)
            for txn in rows:
                t = dict(txn)
                tid = coerce_combo_int_id(t.get("id"))
                match_txt = ""
                if tid is not None:
                    try:
                        bm = business.get_bank_match(self._db._conn, tid)
                        match_txt = _bank_match_label(bm)
                    except sqlite3.OperationalError:
                        pass
                b_key = coerce_combo_int_id(t.get("batch_id"))
                batch_rec = (
                    b_key is not None and rec_map.get(b_key, False)
                )
                reg_cleared = int(t.get("cleared") or 0) == 1
                w.writerow(
                    [
                        t.get("txn_date", ""),
                        t.get("ref_number", ""),
                        t.get("description", ""),
                        t.get("memo", ""),
                        t.get("amount", ""),
                        t.get("coa_account", ""),
                        int(t["is_posted"] or 0) if "is_posted" in t else 0,
                        "yes" if reg_cleared else "no",
                        "yes" if batch_rec else "no",
                        match_txt,
                    ]
                )
        message_box_information_ok(
            self,
            "Export",
            f"Saved {escape_ampersand_for_qt(Path(path).name)}",
            ok_tip="Close; open the CSV from the path you chose." + CSV_EXPORT_OK_TIP_SUFFIX,
        )

    def _on_coa_frame_request_open_editor(self, frame: CoaBandFrame) -> None:
        row = frame._visual_row()
        coa = _register_row_coa_user_data(self._table, row).strip()
        if coa:
            self.openCoaEditorRequested.emit(coa)

    def _finish_register_coa_line_edit(self, txn_id: int, combo: QComboBox) -> None:
        if self._populating or not combo.isEnabled():
            return
        resolved = register_coa_combo_resolve_user_data(combo)
        # Never save the sentinel value from a line-edit finish
        if resolved == _NEW_COA_SENTINEL:
            return
        prev_idx = combo.currentIndex()
        if not (resolved or "").strip():
            target_idx = 0
        else:
            found = combo.findData(resolved)
            target_idx = found if found >= 0 else prev_idx
        combo.blockSignals(True)
        combo.setCurrentIndex(max(0, target_idx))
        le = combo.lineEdit()
        if le is not None:
            le.setText(combo.itemText(combo.currentIndex()))
        combo.blockSignals(False)
        if combo.currentIndex() != prev_idx:
            self._on_coa_changed(txn_id, combo, combo.currentIndex())

    def _on_coa_changed(self, txn_id: int, combo: QComboBox, _index: int):
        if self._populating:
            return
        # Use item data from the index directly — more reliable than reading the
        # line edit text, which may not yet be updated when currentIndexChanged fires.
        raw = combo.itemData(_index)
        val = raw.strip() if isinstance(raw, str) else ""

        # ── "➕ New account…" sentinel ──────────────────────────────────────
        if val == _NEW_COA_SENTINEL:
            # Revert combo back to the previous saved value while the dialog is open
            saved_val = ""
            try:
                row_data = self._db._conn.execute(
                    "SELECT coa_account FROM bank_transactions WHERE id = ?", (txn_id,)
                ).fetchone()
                if row_data:
                    saved_val = (row_data[0] or "").strip()
            except Exception:
                pass
            combo.blockSignals(True)
            prev_idx = combo.findData(saved_val)
            combo.setCurrentIndex(prev_idx if prev_idx >= 0 else 0)
            combo.blockSignals(False)

            # Look up payee description to pre-fill the account name
            payee = ""
            try:
                row_data = self._db._conn.execute(
                    "SELECT description FROM bank_transactions WHERE id = ?", (txn_id,)
                ).fetchone()
                if row_data:
                    payee = (row_data[0] or "").strip()
            except Exception:
                pass

            dlg = QuickAddCoaDialog(self._coa_db, prefill_name=payee, parent=self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            new_key = dlg.created_display_key
            if not new_key:
                return

            # Refresh choices and add new entry to this combo
            self._coa_choices = self._coa_db.display_list()
            # Rebuild sentinel position: remove old sentinel, add new entry, re-add sentinel
            sentinel_idx = combo.findData(_NEW_COA_SENTINEL)
            if sentinel_idx >= 0:
                combo.removeItem(sentinel_idx)
            if combo.findData(new_key) < 0:
                combo.addItem(escape_ampersand_for_qt(new_key), new_key)
            combo.addItem("➕  New account…", _NEW_COA_SENTINEL)

            # Select and save the new account
            new_idx = combo.findData(new_key)
            combo.blockSignals(True)
            if new_idx >= 0:
                combo.setCurrentIndex(new_idx)
            combo.blockSignals(False)
            val = new_key
            # Emit coaChanged so main window can sync the COA tab
            self.openCoaEditorRequested.emit(new_key)

        # ── Normal save ──────────────────────────────────────────────────────
        try:
            self._db.update_transaction(txn_id, coa_account=val)
        except ValueError as exc:
            message_box_warning_ok(
                self,
                "Cannot save",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; pick a valid COA line or leave uncategorized.",
            )
            return
        self._restyle_row_for_coa(combo, val)

    def _restyle_row_for_coa(self, combo: QComboBox, coa_value: str):
        row = -1
        for r in range(self._table.rowCount()):
            w = self._table.cellWidget(r, _COL_COA)
            if isinstance(w, CoaBandFrame):
                if w.combo() is combo:
                    row = r
                    break
            elif w is combo:
                row = r
                break
        if row < 0:
            return
        missing = not (coa_value or "").strip()
        for c in range(_COL_COA):
            it = self._table.item(row, c)
            if it is None:
                continue
            it.setBackground(QBrush())

        id_it = self._table.item(row, _COL_DATE)
        if id_it is not None:
            id_it.setData(REGISTER_MISSING_COA_ROLE, missing)

        coa_cell = self._table.cellWidget(row, _COL_COA)
        if isinstance(coa_cell, CoaBandFrame):
            cmb = coa_cell.combo()
            coa_cell.apply_combo_missing_style(missing)
            tip = _register_coa_combo_tooltip(
                posted=not cmb.isEnabled(),
                saved_coa_display=(coa_value or "").strip(),
            )
            cmb.setToolTip(escape_ampersand_for_qt(tip))
            coa_cell.update()

        if id_it is not None:
            tid = coerce_combo_int_id(id_it.data(Qt.ItemDataRole.UserRole))
            if tid is not None:
                fresh = self._db.get_transaction(tid)
                if fresh is not None:
                    pay_it = self._table.item(row, _COL_PAYEE)
                    if pay_it is not None:
                        self._apply_payee_two_line_to_item(pay_it, dict(fresh))
                    ref_it = self._table.item(row, _COL_REF)
                    if ref_it is not None:
                        fd = dict(fresh)
                        num_plain = _register_number_two_line_plain(fd)
                        ref_it.setData(REGISTER_REF_UPPER_PLAIN, _register_num_upper_plain(fd))
                        ref_it.setData(REGISTER_REF_LOWER_PLAIN, _register_num_lower_plain(fd))
                        ref_it.setToolTip(escape_ampersand_for_qt(num_plain))
                        if ref_it.flags() & Qt.ItemFlag.ItemIsEditable:
                            ref_it.setText(escape_ampersand_for_qt(num_plain))
                            ref_it.setData(QTABLE_PLAIN_TEXT_ROLE, num_plain)
                self._resize_register_row(row)

    def _mark_needs_receipt(self):
        for tid in self._selected_txn_ids():
            try:
                self._db.update_transaction(tid, needs_receipt=1)
            except ValueError as exc:
                message_box_warning_ok(
                    self,
                    "Cannot update",
                    escape_ampersand_for_qt(str(exc)),
                    ok_tip="Close; this flag may be blocked for some rows.",
                )
        self._reload_current()

    def _set_cleared_on_ids(self, ids: list, value: int) -> None:
        for tid in ids:
            try:
                self._db.update_transaction(tid, cleared=value)
            except ValueError as exc:
                message_box_warning_ok(
                    self,
                    "Cannot update",
                    escape_ampersand_for_qt(str(exc)),
                    ok_tip="Close; cleared state may be blocked for posted rows.",
                )
        self._reload_current()

    def _mark_cleared(self):
        ids = self._selected_txn_ids()
        if not ids:
            message_box_information_ok(
                self,
                "Cleared",
                "Select one or more rows.",
                ok_tip="Close; select register rows, then Mark cleared again.",
            )
            return
        self._set_cleared_on_ids(ids, 1)

    def _clear_cleared(self):
        ids = self._selected_txn_ids()
        if not ids:
            message_box_information_ok(
                self,
                "Cleared",
                "Select one or more rows.",
                ok_tip="Close; select register rows, then Clear cleared again.",
            )
            return
        self._set_cleared_on_ids(ids, 0)

    def _clear_needs_receipt(self):
        for tid in self._selected_txn_ids():
            try:
                self._db.update_transaction(tid, needs_receipt=0)
            except ValueError as exc:
                message_box_warning_ok(
                    self,
                    "Cannot update",
                    escape_ampersand_for_qt(str(exc)),
                    ok_tip="Close; needs-receipt flag may be blocked for some rows.",
                )
        self._reload_current()

    def _attach_file(self):
        ids = self._selected_txn_ids()
        if not ids:
            message_box_information_ok(
                self,
                "Attachment",
                "Select one or more rows.",
                ok_tip="Close; select rows, then attach again.",
            )
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Attachment", "", "All files (*.*)"
        )
        if not path:
            return
        for tid in ids:
            try:
                self._db.update_transaction(tid, attachment_path=path)
            except ValueError as exc:
                message_box_warning_ok(
                    self,
                    "Cannot update",
                    escape_ampersand_for_qt(str(exc)),
                    ok_tip="Close; attachment path may be invalid or row locked.",
                )
        self._reload_current()

    def _clear_attachment(self):
        for tid in self._selected_txn_ids():
            try:
                self._db.update_transaction(tid, attachment_path="")
            except ValueError as exc:
                message_box_warning_ok(
                    self,
                    "Cannot update",
                    escape_ampersand_for_qt(str(exc)),
                    ok_tip="Close; clearing attachment may be blocked for some rows.",
                )
        self._reload_current()

    def _transfer_dialog(self):
        ids = self._selected_txn_ids()
        if not ids:
            message_box_information_ok(
                self,
                "Transfer",
                "Select at least one row.",
                ok_tip="Close; select rows, then open Transfer again.",
            )
            return
        if self._current_account_id is None:
            return
        d = QDialog(self)
        d.setWindowTitle("Transfer to bank account")
        d.setToolTip(
            "Set or clear a transfer link to another bank account for all selected register rows."
        )
        f = QFormLayout(d)
        cb = QComboBox()
        cb.setToolTip(
            "Other bank account for a transfer between your accounts. "
            "Choose “not a transfer” to clear an existing link."
        )
        cb.addItem("(not a transfer)", None)
        for acct in self._db.list_bank_accounts():
            aid = coerce_combo_int_id(acct["id"])
            if aid is None:
                continue
            if _register_account_ids_equal(aid, self._current_account_id):
                continue
            cb.addItem(escape_ampersand_for_qt(acct["name"] or ""), aid)
        f.addRow("Counterparty account", cb)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        tip_qdialog_button_box(
            bb,
            ok="Apply this counterparty bank account as the transfer link on all selected rows.",
            cancel="Close without updating transfer links.",
        )
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        target = coerce_combo_int_id(cb.currentData())
        for tid in ids:
            try:
                self._db.update_transaction(
                    tid, transfer_to_bank_account_id=target
                )
            except ValueError as exc:
                message_box_warning_ok(
                    self,
                    "Cannot update",
                    escape_ampersand_for_qt(str(exc)),
                    ok_tip="Close; transfer link rules may reject this combination.",
                )
        self._reload_current()

    def _splits_dialog(self):
        ids = self._selected_txn_ids()
        if len(ids) != 1:
            message_box_information_ok(
                self,
                "Splits",
                "Select exactly one transaction to split.",
                ok_tip="Close; select a single row, then Splits again.",
            )
            return
        tid = ids[0]
        txn = self._db.get_transaction(tid)
        if txn is None or _txn_posted(dict(txn)):
            message_box_information_ok(
                self,
                "Splits",
                "Unposted transactions only.",
                ok_tip="Close; pick an unposted row or reverse the GL post first.",
            )
            return
        amt = float(txn["amount"])
        d = QDialog(self)
        d.setWindowTitle("Split amounts (must sum to bank amount)")
        d.setToolTip(
            "Split one unposted bank transaction into two COA lines; split amounts must sum to the bank amount."
        )
        f = QFormLayout(d)
        a1 = QDoubleSpinBox()
        a1.setRange(-9_999_999, 9_999_999)
        a1.setDecimals(2)
        a1.setValue(round(amt / 2.0, 2))
        a1.setToolTip("First split amount; with Amount 2 must sum to the bank transaction amount.")
        c1 = QLineEdit()
        c1.setPlaceholderText("COA line 1")
        c1.setToolTip("Chart-of-accounts display text for the first split (required).")
        a2 = QDoubleSpinBox()
        a2.setRange(-9_999_999, 9_999_999)
        a2.setDecimals(2)
        a2.setValue(round(amt - a1.value(), 2))
        a2.setToolTip("Second split amount; with Amount 1 must sum to the bank transaction amount.")
        c2 = QLineEdit()
        c2.setPlaceholderText("COA line 2")
        c2.setToolTip("Chart-of-accounts display text for the second split (required).")
        f.addRow("Amount 1", a1)
        f.addRow("COA 1", c1)
        f.addRow("Amount 2", a2)
        f.addRow("COA 2", c2)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        tip_qdialog_button_box(
            bb,
            ok="Save two split lines; amounts must sum to the bank transaction amount.",
            cancel="Close without saving split lines.",
        )
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        s1 = (c1.text() or "").strip()
        s2 = (c2.text() or "").strip()
        if not s1 or not s2:
            message_box_warning_ok(
                self,
                "Splits",
                "Both COA lines are required.",
                ok_tip="Close; enter COA text for both split lines.",
            )
            return
        try:
            business.replace_splits(
                self._db._conn,
                tid,
                [
                    (a1.value(), s1, ""),
                    (a2.value(), s2, ""),
                ],
            )
        except ValueError as exc:
            message_box_warning_ok(
                self,
                "Splits",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; amounts must sum to the bank transaction amount.",
            )
            return
        message_box_information_ok(
            self,
            "Splits",
            "Split lines saved.",
            ok_tip="Close; splits are stored for this transaction.",
        )
        self._reload_current()

    def _link_payment_dialog(self):
        ids = self._selected_txn_ids()
        if len(ids) != 1:
            message_box_information_ok(
                self,
                "Link",
                "Select exactly one bank transaction.",
                ok_tip="Close; select one row, then Link payment again.",
            )
            return
        tid = ids[0]
        d = QDialog(self)
        d.setWindowTitle("Link bank transaction")
        d.setToolTip(
            "Link this bank row to AR/AP/payroll or an open invoice/bill; clear an existing link, open the linked Business record, "
            "or pick from suggestions / manual type."
        )
        d.setMinimumWidth(520)
        outer = QVBoxLayout(d)

        try:
            existing = business.get_bank_match(self._db._conn, tid)
        except sqlite3.OperationalError:
            existing = None
        existing_nav = business.bank_match_link_tuple_from_row(existing)
        state = {"handled": False}

        if existing:
            lbl_current_link = QLabel(
                "Current link: "
                f"{escape_ampersand_for_qt(_bank_match_label(existing))}"
            )
            if existing_nav is not None:
                lbl_current_link.setToolTip(
                    "AR/AP/payroll or open invoice/bill already linked; use Clear link to remove."
                )
            else:
                lbl_current_link.setToolTip(
                    "A bank link row exists but type/id are incomplete—Business cannot open it. "
                    "Clear link and choose a suggestion or manual link, or fix data in the database."
                )
            outer.addWidget(lbl_current_link)
            reg_link_btn_clear = QPushButton("Clear link")
            reg_link_btn_clear.setToolTip(
                "Remove the existing payment / document link for this bank transaction."
            )
            row_cur_link = QHBoxLayout()
            row_cur_link.addWidget(reg_link_btn_clear)
            if existing_nav is not None:
                reg_link_btn_open = QPushButton("Open linked Business record…")
                reg_link_btn_open.setToolTip(
                    "Switch to the Business tab for this **complete** link (same as Recon → Transaction Tools, "
                    "Ctrl+Shift+B, or double-click **Match**). Closes this dialog first."
                )
                row_cur_link.addWidget(reg_link_btn_open)

            outer.addLayout(row_cur_link)

            def clear_link():
                business.unlink_bank_transaction(self._db._conn, tid)
                state["handled"] = True
                d.accept()
                self._reload_current()
                message_box_information_ok(
                    self,
                    "Link",
                    "Link cleared.",
                    ok_tip="Close; the bank row no longer points at a linked business record.",
                )

            reg_link_btn_clear.clicked.connect(clear_link)
            if existing_nav is not None:

                def open_linked_from_link_dialog():
                    state["handled"] = True
                    d.accept()
                    self._reload_current()
                    self.open_linked_business_record_for_transaction_id(tid)

                reg_link_btn_open.clicked.connect(open_linked_from_link_dialog)

        lbl_link_suggestions = QLabel("Suggested matches (by amount and date):")
        lbl_link_suggestions.setToolTip(
            "Auto-suggested AR/AP/payroll records and open invoices (deposits) or bills (withdrawals) by amount and date; pick one or use Manual link below."
        )
        outer.addWidget(lbl_link_suggestions)
        sug_list = QListWidget()
        sug_list.setMinimumHeight(140)
        sug_list.setToolTip(
            "Candidates by amount and near-date (including open invoices/bills when relevant); double-click a row or use Link selected suggestion. "
            "Right-click for Keyboard shortcuts… (empty area OK)."
        )
        suggestions: list = []
        try:
            suggestions = business.suggest_bank_match_candidates(self._db._conn, tid)
        except sqlite3.OperationalError:
            pass
        for s in suggestions:
            lid_int = coerce_combo_int_id(s.get("link_id"))
            if lid_int is None:
                continue
            raw_lbl = s["label"] or ""
            it = QListWidgetItem(escape_ampersand_for_qt(raw_lbl))
            it.setData(Qt.ItemDataRole.UserRole, (s["link_type"], lid_int))
            it.setData(QLIST_PLAIN_TEXT_ROLE, raw_lbl)
            sug_list.addItem(it)

        def on_sug_context_menu(pos):
            idx = sug_list.indexAt(pos)
            m = QMenu(d)
            act_keys = m.addAction(
                "Keyboard shortcuts…",
                lambda: show_register_keyboard_shortcuts_dialog(self),
            )
            act_keys.setToolTip(
                "Same summary as Help → Bank register keyboard shortcuts… "
                "(grid and link dialog; AI line-reconciliation field copies: Bank import link in that Help dialog). "
                + VIEW_BANK_REGISTER_KEYS_TOOLTIP
                + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
            )
            if not idx.isValid():
                m.exec(sug_list.viewport().mapToGlobal(pos))
                return
            row = idx.row()
            m.addSeparator()
            act_copy = m.addAction(
                "Copy suggestion line",
                partial(copy_qlistwidget_row_text, sug_list, row),
            )
            act_copy.setToolTip(
                "Copy this suggestion line as plain text for pasting elsewhere. "
                + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
            )
            m.exec(sug_list.viewport().mapToGlobal(pos))

        sug_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        sug_list.customContextMenuRequested.connect(on_sug_context_menu)
        outer.addWidget(sug_list)

        def apply_suggestion():
            cur = sug_list.currentItem()
            if cur is None:
                message_box_information_ok(
                    self,
                    "Link",
                    "Select a suggestion.",
                    ok_tip="Close; click a row in the list or use Manual link.",
                )
                return
            data = cur.data(Qt.ItemDataRole.UserRole)
            if not data:
                return
            lt, lid_int = data
            if lid_int is None:
                return
            business.link_bank_transaction(self._db._conn, tid, str(lt), lid_int)
            state["handled"] = True
            d.accept()
            self._reload_current()
            message_box_information_ok(
                self,
                "Link",
                "Link saved.",
                ok_tip="Close; this bank line now matches the chosen record. "
                "Recon → Open linked Business, Ctrl+Shift+B, or double-click **Match** opens **Business** when the link is complete.",
            )

        sug_list.itemDoubleClicked.connect(lambda _item: apply_suggestion())
        row_sug = QHBoxLayout()
        reg_link_suggestion = QPushButton("Link selected suggestion")
        reg_link_suggestion.setToolTip(
            "Apply the highlighted suggestion (double-click a row for the same)."
        )
        reg_link_suggestion.clicked.connect(apply_suggestion)
        row_sug.addWidget(reg_link_suggestion)
        outer.addLayout(row_sug)

        lbl_link_manual = QLabel("Manual link")
        lbl_link_manual.setToolTip(
            "Choose payment type and record when no suggestion fits, or to override the list."
        )
        outer.addWidget(lbl_link_manual)
        f = QFormLayout()
        kind = QComboBox()
        kind.addItem("AR payment", "ar_payment")
        kind.addItem("AP payment", "ap_payment")
        kind.addItem("Payroll run", "payroll_run")
        kind.addItem("AR invoice (open balance)", "ar_invoice")
        kind.addItem("AP bill (open balance)", "ap_bill")
        kind.setToolTip(
            "Kind of record to link: payment, payroll run, or open invoice/bill with balance due."
        )
        pay = QComboBox()
        pay.setMinimumWidth(360)
        pay.setToolTip("Specific payment, payroll run, or open invoice/bill to link this bank transaction to.")
        f.addRow("Type", kind)
        f.addRow("Record", pay)
        outer.addLayout(f)

        def refill():
            pay.clear()
            k = kind.currentData()
            if k == "ar_payment":
                rows = business.list_ar_payment_choices(self._db._conn)
                for r in rows:
                    pid = coerce_combo_int_id(r["id"])
                    if pid is None:
                        continue
                    line = (
                        f"#{pid} {r['payment_date']} ${r['amount']:.2f} "
                        f"— {r['party_name']}"
                    )
                    pay.addItem(escape_ampersand_for_qt(line), pid)
            elif k == "ap_payment":
                rows = business.list_ap_payment_choices(self._db._conn)
                for r in rows:
                    pid = coerce_combo_int_id(r["id"])
                    if pid is None:
                        continue
                    line = (
                        f"#{pid} {r['payment_date']} ${r['amount']:.2f} "
                        f"— {r['party_name']}"
                    )
                    pay.addItem(escape_ampersand_for_qt(line), pid)
            elif k == "ar_invoice":
                rows = business.list_ar_invoice_link_choices(self._db._conn)
                for r in rows:
                    iid = coerce_combo_int_id(r["id"])
                    if iid is None:
                        continue
                    inv_no = (r["invoice_number"] or "").strip() or str(iid)
                    line = (
                        f"{inv_no} #{iid} {r['invoice_date']} ${float(r['balance_due']):.2f} open "
                        f"— {r['party_name']}"
                    )
                    pay.addItem(escape_ampersand_for_qt(line), iid)
            elif k == "ap_bill":
                rows = business.list_ap_bill_link_choices(self._db._conn)
                for r in rows:
                    bid = coerce_combo_int_id(r["id"])
                    if bid is None:
                        continue
                    vin = (r["vendor_invoice_number"] or "").strip()
                    vin_bit = f" ({vin})" if vin else ""
                    line = (
                        f"#{bid}{vin_bit} {r['bill_date']} ${float(r['balance_due']):.2f} open "
                        f"— {r['party_name']}"
                    )
                    pay.addItem(escape_ampersand_for_qt(line), bid)
            else:
                rows = business.list_payroll_run_choices(self._db._conn)
                for r in rows:
                    pid = coerce_combo_int_id(r["id"])
                    if pid is None:
                        continue
                    line = (
                        f"#{pid} {r['pay_date']} net ${r['net_pay']:.2f} "
                        f"— {r['party_name']}"
                    )
                    pay.addItem(escape_ampersand_for_qt(line), pid)

        kind.currentIndexChanged.connect(lambda _=0: refill())
        refill()
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        tip_qdialog_button_box(
            bb,
            ok="Save a manual link using Type and Record below (ignored if you already linked or cleared).",
            cancel="Close without applying a manual link.",
        )
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        outer.addWidget(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        if state["handled"]:
            return
        pid = coerce_combo_int_id(pay.currentData())
        if pid is None:
            return
        business.link_bank_transaction(
            self._db._conn, tid, str(kind.currentData()), pid
        )
        message_box_information_ok(
            self,
            "Link",
            "Link saved.",
            ok_tip="Close; manual link is stored on this bank transaction. "
            "Recon → Open linked Business, Ctrl+Shift+B, or double-click **Match** opens **Business** when the link is complete.",
        )
        self._reload_current()
