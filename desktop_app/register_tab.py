"""
desktop_app.register_tab
========================
Phase 3 – Bank register: chronological transactions for one bank account with
debit/credit columns, running balance, memo and COA inline edits, sortable columns
(txn id on Date ``UserRole``; balance stays chronological), and footer totals.
Payee column uses a two-line layout (description, then COA or memo sub-line).
Number column shows reference on the first line and a short type tag (DEP / PMT /
XFER / TXN) on the second. **Clr** shows **C** when the row is marked cleared on the register, else **R** when the
CSV import batch is marked reconciled in Bank Import. Rows without a COA category are highlighted.
The filter choice, last selected bank account, and register table **column header widths**
persist in ``QSettings``, scoped by company SQLite path (same app profile as the main window).
**Ctrl+Shift+C** / **Ctrl+Shift+U** mark cleared / clear cleared; **Ctrl+Shift+E** runs **Export CSV…**;
**Ctrl+Shift+G** runs **Post selected to GL**; **F5** refreshes the grid when the Register tab (or its
controls) has keyboard focus. **Help** → **Bank register keyboard shortcuts…** (dialog also points at **Bank import shortcuts…**) or
**right-click** the grid (including empty area) for **Keyboard shortcuts…** and row actions with **QAction** **setToolTip**; the register grid has a hover **tooltip**
(shortcuts summary). **Link payment…** dialog: **Current link** (when present), **Suggested matches** / **Manual link**
headings, and the suggestions list have hover **tooltips**. **Right-click** the list (empty area OK) for
**Keyboard shortcuts…** (same **Help** dialog as the register grid).
The tools row, **Refresh** / **Post** / **Export**, **Mark cleared** / **Clear cleared**, and **Link payment…** /
**Transfer** / **Splits** / **Link payment** modal **windows** and buttons use **setToolTip** for hover hints.
Footer **debit** / **credit** / **net** totals and the long gray **help** paragraph also have tooltips.
The tab **root** **QWidget** has a hover hint. **Bank account** and **Filter** combos (and their **QLabel** prompts) use **setToolTip**.
"""

from __future__ import annotations

import csv
import hashlib
import sqlite3
from functools import partial
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QBrush, QColor, QHideEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from probooksai import business
from probooksai.coa_ai_suggest import coa_hints
from probooksai.bank_import import BankDatabase
from probooksai.coa_db import COADatabase
from probooksai.gl import GLDatabase

from desktop_app.audit_dialog import show_entity_audit_history
from desktop_app.open_attachment import open_local_attachment
from desktop_app.qt_mnemonic import (
    escape_ampersand_for_qt,
    message_box_information_ok,
    message_box_warning_ok,
    tip_qdialog_button_box,
)
from desktop_app.table_clipboard import (
    CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX,
    QLIST_PLAIN_TEXT_ROLE,
    QTABLE_PLAIN_TEXT_ROLE,
    NumericAmountTableItem,
    copy_qlistwidget_row_text,
    copy_table_row_as_tsv,
    plain_display_table_item,
)
from desktop_app.theme import (
    AMOUNT_NEGATIVE,
    AMOUNT_POSITIVE,
    BG_PRIMARY,
    register_table_style_sheet,
)

_COL_DATE = 0
_COL_REF = 1
_COL_PAYEE = 2
_COL_MEMO = 3
_COL_DEBIT = 4
_COL_CREDIT = 5
_COL_CLR = 6
_COL_BAL = 7
_COL_COA = 8
_COL_LINK = 9

_HEADERS = [
    "Date",
    "Number",
    "Payee / Description",
    "Memo",
    "Debit",
    "Credit",
    "Clr",
    "Balance",
    "COA Account",
    "Match",
]

_MISSING_COA_BG = QColor("#3D3319")
_NORMAL_BG = QColor(BG_PRIMARY)


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
    return f"{lt}:{lid}"


def _txn_posted(row) -> bool:
    keys = row.keys()
    return "is_posted" in keys and int(row["is_posted"] or 0) == 1


def _register_payee_two_line_plain(txn: dict) -> str:
    """Payee cell: line 1 = description; line 2 = COA, else memo, else placeholder."""
    line1 = (txn.get("description") or "").strip() or "—"
    coa = (txn.get("coa_account") or "").strip()
    memo = (txn.get("memo") or "").strip()
    if coa:
        line2 = coa
    elif memo:
        line2 = memo
    else:
        line2 = "— Assign COA —"
    return f"{line1}\n{line2}"


def _register_number_type_tag(txn: dict) -> str:
    """Second line of Number column: inferred register type (QuickBooks-style hint)."""
    xfer = txn.get("transfer_to_bank_account_id")
    try:
        has_xfer = xfer is not None and int(xfer) > 0
    except (TypeError, ValueError):
        has_xfer = False
    if has_xfer:
        return "XFER"
    try:
        amt = float(txn.get("amount") or 0.0)
    except (TypeError, ValueError):
        amt = 0.0
    if amt > 0:
        return "DEP"
    if amt < 0:
        return "PMT"
    return "TXN"


def _register_number_two_line_plain(txn: dict) -> str:
    """Number cell: line 1 = ref #; line 2 = DEP / PMT / XFER / TXN."""
    ref = (txn.get("ref_number") or "").strip()
    line1 = ref if ref else "—"
    line2 = _register_number_type_tag(txn)
    return f"{line1}\n{line2}"


def _batch_reconciled_map(conn: sqlite3.Connection, txns: list) -> dict[int, bool]:
    """Map import *batch_id* -> True when ``bank_import_batches.is_reconciled`` is set."""
    ids: set[int] = set()
    for txn in txns:
        d = dict(txn)
        bid = d.get("batch_id")
        if bid is None:
            continue
        try:
            ids.add(int(bid))
        except (TypeError, ValueError):
            continue
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
        out[int(r["id"])] = int(r.get("is_reconciled") or 0) == 1
    return out


def _register_keyboard_shortcuts_help_text() -> str:
    """Plain text for Register shortcuts (keep aligned with ``QShortcut`` wiring)."""
    return (
        "These shortcuts apply when the Register tab or its controls have focus:\n\n"
        "Link payment… — suggested-matches list: right-click (including empty area) for "
        "Keyboard shortcuts… (same as this dialog).\n\n"
        "F5 — Refresh\n"
        "Ctrl+Shift+G — Post selected to GL\n"
        "Ctrl+Shift+E — Export CSV…\n"
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
        "Company .db: File → Backup / Restore (probooks.backup).",
    )


class RegisterTab(QWidget):
    """
    Check-register style view for all transactions on a selected bank account.
    """

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
        self._build_ui()

    def _build_ui(self):
        self.setToolTip(
            "Bank register for one account: categorize, splits, transfer links, cleared flags, attachments, and post to GL "
            "(F5 refreshes when Register has focus). "
            "Same company SQLite database as other main tabs; File → Backup / Restore (probooks.backup)."
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        row = QHBoxLayout()
        lbl_bank_acct = QLabel("Bank account:")
        lbl_bank_acct.setToolTip(
            "Prompt for the register account picker; use the combo to switch which bank you are viewing."
        )
        row.addWidget(lbl_bank_acct)
        self._acct_combo = QComboBox()
        self._acct_combo.setMinimumWidth(240)
        self._acct_combo.setToolTip(
            "Choose which bank account register to view and edit."
        )
        self._acct_combo.currentIndexChanged.connect(self._on_account_changed)
        row.addWidget(self._acct_combo)
        btn_refresh = QPushButton("Refresh")
        btn_refresh.setToolTip(
            "Reload transactions for the selected bank account from the database. "
            "Shortcut: F5 (when Register has focus)."
        )
        btn_refresh.clicked.connect(self._reload_current)
        row.addWidget(btn_refresh)
        self._btn_post = QPushButton("Post selected to GL")
        self._btn_post.setToolTip(
            "Post selected unposted rows to the general ledger (requires COA and mapped cash accounts). "
            "Shortcut: Ctrl+Shift+G (when Register has focus). "
            "GL posts write to the company SQLite file (File → Backup / probooks backup before big runs)."
        )
        self._btn_post.clicked.connect(self._post_selected)
        row.addWidget(self._btn_post)
        self._btn_export = QPushButton("Export CSV…")
        self._btn_export.setToolTip(
            "Export the current grid to CSV (respects the active filter and column order). "
            "Shortcut: Ctrl+Shift+E (when Register has focus)."
        )
        self._btn_export.clicked.connect(self._export_csv)
        row.addWidget(self._btn_export)
        row.addStretch()
        layout.addLayout(row)

        filt = QHBoxLayout()
        lbl_register_filter = QLabel("Filter:")
        lbl_register_filter.setToolTip(
            "Prompt for the row filter; the combo limits visible transactions without changing accounts."
        )
        filt.addWidget(lbl_register_filter)
        self._filter_combo = QComboBox()
        self._filter_combo.addItem("All transactions", "all")
        self._filter_combo.addItem("Flagged: needs receipt", "needs_receipt")
        self._filter_combo.addItem("Has attachment", "has_attachment")
        self._filter_combo.addItem("Needs receipt, no file", "missing_attachment")
        self._filter_combo.addItem("Has payment / payroll link", "has_bank_match")
        self._filter_combo.addItem("No payment link", "no_bank_match")
        self._filter_combo.addItem("Cleared (register)", "cleared")
        self._filter_combo.addItem("Not cleared", "not_cleared")
        self._filter_combo.addItem("Batch reconciled (import)", "batch_reconciled")
        self._filter_combo.addItem("Batch not reconciled", "batch_not_reconciled")
        self._filter_combo.setToolTip(
            "Narrow rows by receipt flag, attachment, payment link, cleared state, "
            "or CSV batch reconciliation."
        )
        self._restore_register_filter_from_settings()
        self._filter_combo.currentIndexChanged.connect(self._on_register_filter_changed)
        filt.addWidget(self._filter_combo)
        filt.addStretch()
        layout.addLayout(filt)

        tools = QHBoxLayout()
        reg_flag_rcpt = QPushButton("Flag needs receipt")
        reg_flag_rcpt.setToolTip(
            "Set the needs-receipt flag on selected rows (posted rows may not allow changes)."
        )
        reg_flag_rcpt.clicked.connect(self._mark_needs_receipt)
        tools.addWidget(reg_flag_rcpt)
        reg_clear_rcpt = QPushButton("Clear needs receipt")
        reg_clear_rcpt.setToolTip("Clear the needs-receipt flag on selected rows.")
        reg_clear_rcpt.clicked.connect(self._clear_needs_receipt)
        tools.addWidget(reg_clear_rcpt)
        reg_attach = QPushButton("Attach file…")
        reg_attach.setToolTip(
            "Choose a file and store its path on all selected rows as the attachment."
        )
        reg_attach.clicked.connect(self._attach_file)
        tools.addWidget(reg_attach)
        reg_clear_att = QPushButton("Clear attachment")
        reg_clear_att.setToolTip("Clear the attachment path on selected rows.")
        reg_clear_att.clicked.connect(self._clear_attachment)
        tools.addWidget(reg_clear_att)
        reg_transfer = QPushButton("Transfer to…")
        reg_transfer.setToolTip(
            "Mark selected rows as transfers, choosing the other bank account (counterparty)."
        )
        reg_transfer.clicked.connect(self._transfer_dialog)
        tools.addWidget(reg_transfer)
        reg_splits = QPushButton("Splits…")
        reg_splits.setToolTip(
            "Split one unposted transaction into two COA lines (amounts must sum to the bank amount)."
        )
        reg_splits.clicked.connect(self._splits_dialog)
        tools.addWidget(reg_splits)
        reg_link_pay = QPushButton("Link payment…")
        reg_link_pay.setToolTip(
            "Link one selected row to an AR payment, AP payment, or payroll run (or clear an existing link)."
        )
        reg_link_pay.clicked.connect(self._link_payment_dialog)
        tools.addWidget(reg_link_pay)
        self._btn_mark_cleared = QPushButton("Mark cleared", clicked=self._mark_cleared)
        self._btn_mark_cleared.setToolTip(
            "Set cleared on selected rows. Shortcut: Ctrl+Shift+C (when Register has focus)."
        )
        tools.addWidget(self._btn_mark_cleared)
        self._btn_clear_cleared = QPushButton("Clear cleared", clicked=self._clear_cleared)
        self._btn_clear_cleared.setToolTip(
            "Clear cleared on selected rows. Shortcut: Ctrl+Shift+U (when Register has focus)."
        )
        tools.addWidget(self._btn_clear_cleared)
        tools.addStretch()
        layout.addLayout(tools)

        self._table = QTableWidget()
        self._table.setObjectName("bankRegisterTable")
        self._table.setStyleSheet(register_table_style_sheet())
        self._table.setColumnCount(len(_HEADERS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        clr_header = self._table.horizontalHeaderItem(_COL_CLR)
        if clr_header is not None:
            clr_header.setToolTip(
                "C: cleared on this register. R: CSV import batch is reconciled in Bank Import. "
                "Double-click a cell here to toggle cleared when the row allows it."
            )
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        # Native grid is unreliable once app-level QTable styles apply; cell borders come from the stylesheet.
        self._table.setShowGrid(False)
        self._table.setWordWrap(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(_COL_COA, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(_COL_CLR, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(_COL_LINK, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setSortingEnabled(True)
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.cellDoubleClicked.connect(self._on_register_cell_double_clicked)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_register_context_menu)
        self._table.setToolTip(
            "Transactions for the selected bank account and filter; edit memo/COA inline where allowed. "
            "Right-click for Keyboard shortcuts… (empty area OK). F5 refresh; Ctrl+Shift+G post; "
            "Ctrl+Shift+C / Ctrl+Shift+U cleared; Ctrl+Shift+E export. "
            "Same company .db as other tabs (File → Backup / Restore, probooks.backup)."
        )
        layout.addWidget(self._table)

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

        foot = QHBoxLayout()
        self._lbl_debits = QLabel("Total debits: —")
        self._lbl_debits.setToolTip(
            "Sum of debit amounts for rows currently visible in the grid (respects the filter)."
        )
        self._lbl_credits = QLabel("Total credits: —")
        self._lbl_credits.setToolTip(
            "Sum of credit amounts for rows currently visible in the grid (respects the filter)."
        )
        self._lbl_net = QLabel("Net: —")
        self._lbl_net.setToolTip(
            "Debits minus credits for visible rows (running balance order may differ when sorted)."
        )
        for w in (self._lbl_debits, self._lbl_credits, self._lbl_net):
            w.setStyleSheet("font-weight: bold;")
        foot.addWidget(self._lbl_debits)
        foot.addSpacing(24)
        foot.addWidget(self._lbl_credits)
        foot.addSpacing(24)
        foot.addWidget(self._lbl_net)
        foot.addStretch()
        layout.addLayout(foot)

        tip = QLabel(
            "Deposits show in Debit; payments in Credit (cash-basis register). "
            "Payee shows description then COA or memo; Number shows reference then type (DEP / PMT / XFER). "
            "Clr shows C when marked cleared here, else R when the CSV batch was reconciled in Bank Import "
            "(double-click Clr to toggle cleared). "
            "Assign a COA account to clear the highlight. "
            "Starred (★) items at the top of the COA list are hints from your rules "
            "and, when OPENAI_API_KEY is set, optional AI picks. "
            "Balance is the running total in date order (not recalculated for other sorts). "
            "Filter, last bank account, and column widths are remembered per company file for the next session. "
            "With focus on this tab: F5 refreshes, Ctrl+Shift+G posts selected to GL, Ctrl+Shift+C marks cleared, "
            "Ctrl+Shift+U clears cleared, Ctrl+Shift+E exports CSV. "
            "Help → Bank register keyboard shortcuts… (includes Bank import shortcuts pointer), "
            "Help → Bank import shortcuts…, or right-click the grid (even on empty area)."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #A0A0B0; font-size: 11px;")
        tip.setToolTip(
            "Register layout, debits/credits, Clr column, COA hints (★), shortcuts (F5, Ctrl+Shift+…), "
            "and Help / right-click for Keyboard shortcuts…."
        )
        layout.addWidget(tip)

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_account_combo()
        raw = QSettings().value(self._register_table_header_state_key())
        if raw:
            self._table.horizontalHeader().restoreState(raw)

    def hideEvent(self, event: QHideEvent) -> None:
        self._persist_register_table_header_state()
        super().hideEvent(event)

    def refresh_coa_choices(self):
        """Call when the chart of accounts changes (same DB connection)."""
        self._coa_choices = self._coa_db.display_list()
        self._reload_current()

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
        return f"register/table_header_state_{self._register_prefs_id()}"

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

    def _refresh_account_combo(self):
        self._acct_combo.blockSignals(True)
        prev = self._current_account_id
        self._acct_combo.clear()
        accounts = self._db.list_bank_accounts()
        if not accounts:
            self._acct_combo.addItem("(no bank accounts)", None)
        else:
            for acct in accounts:
                label = f"{acct['name']} – {acct['bank_name'] or 'Bank'}"
                self._acct_combo.addItem(
                    escape_ampersand_for_qt(label), acct["id"]
                )
        self._acct_combo.blockSignals(False)
        picked = False
        if prev is not None:
            for i in range(self._acct_combo.count()):
                if self._acct_combo.itemData(i) == prev:
                    self._acct_combo.setCurrentIndex(i)
                    picked = True
                    break
        if not picked and accounts:
            sid_raw = QSettings().value(self._register_bank_account_settings_key(), -1)
            try:
                sid = int(sid_raw) if sid_raw is not None else -1
            except (TypeError, ValueError):
                sid = -1
            if sid > 0:
                for i in range(self._acct_combo.count()):
                    if self._acct_combo.itemData(i) == sid:
                        self._acct_combo.setCurrentIndex(i)
                        picked = True
                        break
        self._on_account_changed()

    def _on_account_changed(self):
        aid = self._acct_combo.currentData()
        self._current_account_id = aid
        s = QSettings()
        if aid is None:
            s.remove(self._register_bank_account_settings_key())
            self._clear_table()
            return
        s.setValue(self._register_bank_account_settings_key(), int(aid))
        self._load_transactions(int(aid))

    def _reload_current(self):
        if self._current_account_id is not None:
            self._load_transactions(self._current_account_id)
        else:
            self._clear_table()

    def _clear_table(self):
        self._populating = True
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        self._table.setSortingEnabled(True)
        self._populating = False
        self._set_footer(0.0, 0.0, 0.0)

    def _apply_payee_two_line_to_item(self, it: QTableWidgetItem, txn: dict) -> None:
        raw = _register_payee_two_line_plain(txn)
        it.setText(escape_ampersand_for_qt(raw))
        it.setData(QTABLE_PLAIN_TEXT_ROLE, raw)

    def _resize_register_row(self, row: int) -> None:
        self._table.resizeRowToContents(row)
        if self._table.rowHeight(row) < 40:
            self._table.setRowHeight(row, 40)

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
            tid = it.data(Qt.ItemDataRole.UserRole)
            if tid is not None:
                ids.append(tid)
        return ids

    def _on_register_cell_double_clicked(self, row: int, col: int) -> None:
        """Toggle per-row *cleared* when the user double-clicks the Clr column."""
        if col != _COL_CLR:
            return
        id_item = self._table.item(row, _COL_DATE)
        if id_item is None:
            return
        tid = id_item.data(Qt.ItemDataRole.UserRole)
        if tid is None:
            return
        txn = self._db.get_transaction(int(tid))
        if txn is None:
            return
        cur = int(dict(txn).get("cleared") or 0) == 1
        try:
            self._db.update_transaction(int(tid), cleared=0 if cur else 1)
        except ValueError as exc:
            message_box_warning_ok(
                self,
                "Cannot update",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; cleared state may be blocked for posted or reconciled rows.",
            )
            return
        self._reload_current()

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
            "(F5, export, post, cleared chords). "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        if not idx.isValid():
            menu.exec(self._table.viewport().mapToGlobal(pos))
            return
        row = idx.row()
        it = self._table.item(row, _COL_DATE)
        if it is None or it.data(Qt.ItemDataRole.UserRole) is None:
            menu.exec(self._table.viewport().mapToGlobal(pos))
            return
        tid = it.data(Qt.ItemDataRole.UserRole)
        menu.addSeparator()
        act_att = menu.addAction(
            "Open attachment…",
            partial(self._open_register_attachment, int(tid)),
        )
        act_att.setToolTip("Open the linked file for this register row if a path is set.")
        tid_int = int(tid)
        act_clr = menu.addAction(
            "Mark cleared",
            partial(self._set_cleared_on_ids, [tid_int], 1),
        )
        act_clr.setToolTip("Set the cleared flag on this row (register cleared column).")
        act_uclr = menu.addAction(
            "Clear cleared",
            partial(self._set_cleared_on_ids, [tid_int], 0),
        )
        act_uclr.setToolTip("Clear the cleared flag on this row.")
        act_copy = menu.addAction("Copy row", partial(copy_table_row_as_tsv, self._table, row))
        act_copy.setToolTip(
            "Copy this register row as tab-separated text for pasting into a spreadsheet or editor. "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        act_history = menu.addAction("View change history…")
        act_history.setToolTip(
            "Open field-level audit history for this bank transaction."
        )
        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))
        if chosen == act_history:
            show_entity_audit_history(
                self,
                self._db._conn,
                "bank_transaction",
                int(tid),
                window_title=f"Change history — transaction #{tid}",
                empty_message="No audit entries recorded for this transaction yet.",
            )

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
        rows = self._db.list_transactions(
            bank_account_id, register_filter=self._register_filter_param()
        )
        rec_map = _batch_reconciled_map(self._db._conn, rows)
        self._populating = True
        self._table.setSortingEnabled(False)
        self._table.blockSignals(True)
        self._table.setRowCount(len(rows))

        running = 0.0
        total_debits = 0.0
        total_credits = 0.0

        pos_color = QColor(AMOUNT_POSITIVE)
        neg_color = QColor(AMOUNT_NEGATIVE)

        for r, txn in enumerate(rows):
            txn = dict(txn)
            tid = txn["id"]
            amt = float(txn["amount"])
            posted = _txn_posted(txn)

            if amt > 0:
                total_debits += amt
            elif amt < 0:
                total_credits += abs(amt)

            running += amt

            missing_coa = not (txn.get("coa_account") or "").strip()
            row_bg = _MISSING_COA_BG if missing_coa else _NORMAL_BG
            brush = QBrush(row_bg) if missing_coa else QBrush()

            d_item = plain_display_table_item(txn["txn_date"] or "")
            d_item.setData(Qt.ItemDataRole.UserRole, tid)
            d_item.setFlags(d_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            d_item.setTextAlignment(
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
            )
            if missing_coa:
                d_item.setBackground(brush)

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
            if missing_coa:
                ref_item.setBackground(brush)

            payee_item = plain_display_table_item(_register_payee_two_line_plain(txn))
            payee_item.setFlags(payee_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            payee_item.setTextAlignment(
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
            )
            if missing_coa:
                payee_item.setBackground(brush)

            memo_raw = txn.get("memo") or ""
            if posted:
                memo_item = plain_display_table_item(memo_raw)
                memo_item.setFlags(memo_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            else:
                memo_item = QTableWidgetItem(memo_raw)
                memo_item.setFlags(memo_item.flags() | Qt.ItemFlag.ItemIsEditable)
            memo_item.setTextAlignment(
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
            )
            if missing_coa:
                memo_item.setBackground(brush)

            debit_item = QTableWidgetItem()
            debit_item.setFlags(debit_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            credit_item = QTableWidgetItem()
            credit_item.setFlags(credit_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            bal_item = NumericAmountTableItem(running)
            bal_item.setFlags(bal_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            if amt > 0:
                debit_item = NumericAmountTableItem(amt)
                debit_item.setFlags(debit_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                debit_item.setForeground(pos_color)
            elif amt < 0:
                credit_item = NumericAmountTableItem(abs(amt))
                credit_item.setFlags(credit_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                credit_item.setForeground(neg_color)

            if running < 0:
                bal_item.setForeground(neg_color)
            elif running > 0:
                bal_item.setForeground(pos_color)

            for it in (debit_item, credit_item, bal_item):
                it.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
                )
            if missing_coa:
                for it in (debit_item, credit_item, bal_item):
                    it.setBackground(brush)

            bid = txn.get("batch_id")
            try:
                b_key = int(bid) if bid is not None else None
            except (TypeError, ValueError):
                b_key = None
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
            if missing_coa:
                clr_item.setBackground(brush)

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
            combo.setToolTip(
                "Chart-of-accounts line for this row. Starred (★) items are suggested from "
                "your categorization rules."
            )
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
            current = (txn.get("coa_account") or "").strip()
            idx = combo.findData(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            elif current:
                combo.addItem(escape_ampersand_for_qt(current), current)
                combo.setCurrentIndex(combo.count() - 1)
            if posted:
                combo.setEnabled(False)
            if missing_coa:
                combo.setStyleSheet(
                    f"QComboBox {{ background-color: {_MISSING_COA_BG.name()}; }}"
                )
            combo.currentIndexChanged.connect(
                partial(self._on_coa_changed, tid, combo)
            )
            self._table.setCellWidget(r, _COL_COA, combo)

            try:
                bm = business.get_bank_match(self._db._conn, tid)
            except sqlite3.OperationalError:
                bm = None
            link_item = plain_display_table_item(_bank_match_label(bm))
            link_item.setFlags(link_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            link_item.setToolTip(
                "Linked AR, AP, or payroll record. Use Link payment… to set or clear."
            )
            if missing_coa:
                link_item.setBackground(brush)
            link_item.setTextAlignment(
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
            )
            self._table.setItem(r, _COL_LINK, link_item)

            self._resize_register_row(r)

        self._table.blockSignals(False)
        self._populating = False
        self._table.setSortingEnabled(True)
        net = total_debits - total_credits
        self._set_footer(total_debits, total_credits, net)

    def _set_footer(self, debits: float, credits: float, net: float):
        self._lbl_debits.setText(f"Total debits: ${debits:,.2f}")
        self._lbl_credits.setText(f"Total credits: ${credits:,.2f}")
        self._lbl_net.setText(f"Net: ${net:,.2f}")

    def _on_item_changed(self, item: QTableWidgetItem):
        if self._populating:
            return
        col = item.column()
        if col not in (_COL_MEMO, _COL_REF):
            return
        row = item.row()
        id_item = self._table.item(row, _COL_DATE)
        if id_item is None:
            return
        txn_id = id_item.data(Qt.ItemDataRole.UserRole)
        if txn_id is None:
            return
        try:
            if col == _COL_MEMO:
                self._db.update_transaction(txn_id, memo=item.text())
                fresh = self._db.get_transaction(txn_id)
                if fresh is not None:
                    pay_it = self._table.item(row, _COL_PAYEE)
                    if pay_it is not None:
                        self._apply_payee_two_line_to_item(pay_it, dict(fresh))
                self._resize_register_row(row)
            else:
                ref_first = item.text().split("\n", 1)[0].strip()
                self._db.update_transaction(txn_id, ref_number=ref_first)
                self._populating = True
                fresh = self._db.get_transaction(txn_id)
                if fresh is not None:
                    num_plain = _register_number_two_line_plain(dict(fresh))
                    item.setText(escape_ampersand_for_qt(num_plain))
                    item.setData(QTABLE_PLAIN_TEXT_ROLE, num_plain)
                self._populating = False
                self._resize_register_row(row)
        except ValueError as exc:
            message_box_warning_ok(
                self,
                "Cannot save",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; fix the value and try again.",
            )

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
            tid = id_item.data(Qt.ItemDataRole.UserRole)
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
        with open(path, "w", newline="", encoding="utf-8") as fp:
            w = csv.writer(fp)
            w.writerow(hdr)
            for txn in rows:
                t = dict(txn)
                tid = t.get("id")
                match_txt = ""
                if tid is not None:
                    try:
                        bm = business.get_bank_match(self._db._conn, int(tid))
                        match_txt = _bank_match_label(bm)
                    except sqlite3.OperationalError:
                        pass
                bid = t.get("batch_id")
                try:
                    b_key = int(bid) if bid is not None else None
                except (TypeError, ValueError):
                    b_key = None
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
            ok_tip="Close; open the CSV from the path you chose.",
        )

    def _on_coa_changed(self, txn_id: int, combo: QComboBox, _index: int):
        if self._populating:
            return
        val = combo.currentData()
        if val is None:
            val = ""
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
            if w is combo:
                row = r
                break
        if row < 0:
            return
        missing = not (coa_value or "").strip()
        brush = QBrush(_MISSING_COA_BG) if missing else QBrush()
        for c in range(_COL_COA):
            it = self._table.item(row, c)
            if it is None:
                continue
            if missing:
                it.setBackground(brush)
            else:
                it.setBackground(QBrush())
        if missing:
            combo.setStyleSheet(f"QComboBox {{ background-color: {_MISSING_COA_BG.name()}; }}")
        else:
            combo.setStyleSheet("")

        id_it = self._table.item(row, _COL_DATE)
        if id_it is not None:
            tid = id_it.data(Qt.ItemDataRole.UserRole)
            if tid is not None:
                fresh = self._db.get_transaction(int(tid))
                if fresh is not None:
                    pay_it = self._table.item(row, _COL_PAYEE)
                    if pay_it is not None:
                        self._apply_payee_two_line_to_item(pay_it, dict(fresh))
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
                self._db.update_transaction(int(tid), cleared=value)
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
            if acct["id"] == self._current_account_id:
                continue
            cb.addItem(
                escape_ampersand_for_qt(acct["name"] or ""), acct["id"]
            )
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
        target = cb.currentData()
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
            "Link this bank row to AR, AP, or payroll; clear an existing link or pick from suggestions."
        )
        d.setMinimumWidth(520)
        outer = QVBoxLayout(d)

        try:
            existing = business.get_bank_match(self._db._conn, tid)
        except sqlite3.OperationalError:
            existing = None
        state = {"handled": False}

        if existing:
            lbl_current_link = QLabel(
                "Current link: "
                f"{escape_ampersand_for_qt(_bank_match_label(existing))}"
            )
            lbl_current_link.setToolTip(
                "AR, AP, or payroll record already linked to this bank transaction; use Clear link to remove."
            )
            outer.addWidget(lbl_current_link)
            reg_link_btn_clear = QPushButton("Clear link")
            reg_link_btn_clear.setToolTip(
                "Remove the existing AR/AP/payroll link for this bank transaction."
            )
            outer.addWidget(reg_link_btn_clear)

            def clear_link():
                business.unlink_bank_transaction(self._db._conn, tid)
                state["handled"] = True
                d.accept()
                self._reload_current()
                message_box_information_ok(
                    self,
                    "Link",
                    "Link cleared.",
                    ok_tip="Close; the bank row no longer points at AR/AP/payroll.",
                )

            reg_link_btn_clear.clicked.connect(clear_link)

        lbl_link_suggestions = QLabel("Suggested matches (by amount and date):")
        lbl_link_suggestions.setToolTip(
            "Auto-suggested AR/AP/payroll records by amount and date; pick one or use Manual link below."
        )
        outer.addWidget(lbl_link_suggestions)
        sug_list = QListWidget()
        sug_list.setMinimumHeight(140)
        sug_list.setToolTip(
            "Candidates by amount and near-date; double-click a row or use Link selected suggestion. "
            "Right-click for Keyboard shortcuts… (empty area OK)."
        )
        suggestions: list = []
        try:
            suggestions = business.suggest_bank_match_candidates(self._db._conn, tid)
        except sqlite3.OperationalError:
            pass
        for s in suggestions:
            raw_lbl = s["label"] or ""
            it = QListWidgetItem(escape_ampersand_for_qt(raw_lbl))
            it.setData(Qt.ItemDataRole.UserRole, (s["link_type"], s["link_id"]))
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
                "Same summary as Help → Bank register keyboard shortcuts… (grid and link dialog). "
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
            lt, lid = data
            business.link_bank_transaction(self._db._conn, tid, str(lt), int(lid))
            state["handled"] = True
            d.accept()
            self._reload_current()
            message_box_information_ok(
                self,
                "Link",
                "Link saved.",
                ok_tip="Close; this bank line now matches the chosen record.",
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
        kind.setToolTip(
            "Kind of business record to link: customer payment, vendor payment, or payroll run."
        )
        pay = QComboBox()
        pay.setMinimumWidth(360)
        pay.setToolTip("Specific payment or payroll run to link this bank transaction to.")
        f.addRow("Type", kind)
        f.addRow("Record", pay)
        outer.addLayout(f)

        def refill():
            pay.clear()
            k = kind.currentData()
            if k == "ar_payment":
                rows = business.list_ar_payment_choices(self._db._conn)
                for r in rows:
                    line = (
                        f"#{r['id']} {r['payment_date']} ${r['amount']:.2f} "
                        f"— {r['party_name']}"
                    )
                    pay.addItem(escape_ampersand_for_qt(line), r["id"])
            elif k == "ap_payment":
                rows = business.list_ap_payment_choices(self._db._conn)
                for r in rows:
                    line = (
                        f"#{r['id']} {r['payment_date']} ${r['amount']:.2f} "
                        f"— {r['party_name']}"
                    )
                    pay.addItem(escape_ampersand_for_qt(line), r["id"])
            else:
                rows = business.list_payroll_run_choices(self._db._conn)
                for r in rows:
                    line = (
                        f"#{r['id']} {r['pay_date']} net ${r['net_pay']:.2f} "
                        f"— {r['party_name']}"
                    )
                    pay.addItem(escape_ampersand_for_qt(line), r["id"])

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
        pid = pay.currentData()
        if pid is None:
            return
        business.link_bank_transaction(
            self._db._conn, tid, str(kind.currentData()), int(pid)
        )
        message_box_information_ok(
            self,
            "Link",
            "Link saved.",
            ok_tip="Close; manual link is stored on this bank transaction.",
        )
        self._reload_current()
