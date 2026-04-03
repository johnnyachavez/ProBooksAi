"""
desktop_app.register_tab
========================
Phase 3 – Bank register: chronological transactions for one bank account with
debit/credit columns, running balance, memo and COA inline edits, sortable columns
(txn id on Date ``UserRole``; balance stays chronological), and footer totals.
Payee column uses a two-line layout (description, then COA or memo sub-line).
Number column shows reference on the first line and a short type tag (DEP / PMT /
XFER / TXN) on the second. Rows without a COA category are highlighted.
"""

from __future__ import annotations

import csv
import sqlite3
from functools import partial
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush
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
    QMessageBox,
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
from desktop_app.qt_mnemonic import escape_ampersand_for_qt
from desktop_app.table_clipboard import (
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
_COL_BAL = 6
_COL_COA = 7
_COL_LINK = 8

_HEADERS = [
    "Date",
    "Number",
    "Payee / Description",
    "Memo",
    "Debit",
    "Credit",
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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        row = QHBoxLayout()
        row.addWidget(QLabel("Bank account:"))
        self._acct_combo = QComboBox()
        self._acct_combo.setMinimumWidth(240)
        self._acct_combo.currentIndexChanged.connect(self._on_account_changed)
        row.addWidget(self._acct_combo)
        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self._reload_current)
        row.addWidget(btn_refresh)
        self._btn_post = QPushButton("Post selected to GL")
        self._btn_post.clicked.connect(self._post_selected)
        row.addWidget(self._btn_post)
        self._btn_export = QPushButton("Export CSV…")
        self._btn_export.clicked.connect(self._export_csv)
        row.addWidget(self._btn_export)
        row.addStretch()
        layout.addLayout(row)

        filt = QHBoxLayout()
        filt.addWidget(QLabel("Filter:"))
        self._filter_combo = QComboBox()
        self._filter_combo.addItem("All transactions", "all")
        self._filter_combo.addItem("Flagged: needs receipt", "needs_receipt")
        self._filter_combo.addItem("Has attachment", "has_attachment")
        self._filter_combo.addItem("Needs receipt, no file", "missing_attachment")
        self._filter_combo.addItem("Has payment / payroll link", "has_bank_match")
        self._filter_combo.addItem("No payment link", "no_bank_match")
        self._filter_combo.currentIndexChanged.connect(self._reload_current)
        filt.addWidget(self._filter_combo)
        filt.addStretch()
        layout.addLayout(filt)

        tools = QHBoxLayout()
        tools.addWidget(
            QPushButton("Flag needs receipt", clicked=self._mark_needs_receipt)
        )
        tools.addWidget(
            QPushButton("Clear needs receipt", clicked=self._clear_needs_receipt)
        )
        tools.addWidget(QPushButton("Attach file…", clicked=self._attach_file))
        tools.addWidget(QPushButton("Clear attachment", clicked=self._clear_attachment))
        tools.addWidget(QPushButton("Transfer to…", clicked=self._transfer_dialog))
        tools.addWidget(QPushButton("Splits…", clicked=self._splits_dialog))
        tools.addWidget(QPushButton("Link payment…", clicked=self._link_payment_dialog))
        tools.addStretch()
        layout.addLayout(tools)

        self._table = QTableWidget()
        self._table.setObjectName("bankRegisterTable")
        self._table.setStyleSheet(register_table_style_sheet())
        self._table.setColumnCount(len(_HEADERS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        # Native grid is unreliable once app-level QTable styles apply; cell borders come from the stylesheet.
        self._table.setShowGrid(False)
        self._table.setWordWrap(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(_COL_LINK, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setSortingEnabled(True)
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_register_context_menu)
        layout.addWidget(self._table)

        foot = QHBoxLayout()
        self._lbl_debits = QLabel("Total debits: —")
        self._lbl_credits = QLabel("Total credits: —")
        self._lbl_net = QLabel("Net: —")
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
            "Assign a COA account to clear the highlight. "
            "Starred (★) items at the top of the COA list are hints from your rules "
            "and, when OPENAI_API_KEY is set, optional AI picks. "
            "Balance is the running total in date order (not recalculated for other sorts)."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #A0A0B0; font-size: 11px;")
        layout.addWidget(tip)

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_account_combo()

    def refresh_coa_choices(self):
        """Call when the chart of accounts changes (same DB connection)."""
        self._coa_choices = self._coa_db.display_list()
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
        if prev is not None:
            for i in range(self._acct_combo.count()):
                if self._acct_combo.itemData(i) == prev:
                    self._acct_combo.setCurrentIndex(i)
                    break
        self._on_account_changed()

    def _on_account_changed(self):
        aid = self._acct_combo.currentData()
        self._current_account_id = aid
        if aid is None:
            self._clear_table()
            return
        self._load_transactions(aid)

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

    def _on_register_context_menu(self, pos):
        idx = self._table.indexAt(pos)
        if not idx.isValid():
            return
        row = idx.row()
        it = self._table.item(row, _COL_DATE)
        if it is None:
            return
        tid = it.data(Qt.ItemDataRole.UserRole)
        if tid is None:
            return
        menu = QMenu(self)
        menu.addAction(
            "Open attachment…",
            partial(self._open_register_attachment, int(tid)),
        )
        menu.addAction("Copy row", partial(copy_table_row_as_tsv, self._table, row))
        act_history = menu.addAction("View change history…")
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

            self._table.setItem(r, _COL_DATE, d_item)
            self._table.setItem(r, _COL_REF, ref_item)
            self._table.setItem(r, _COL_PAYEE, payee_item)
            self._table.setItem(r, _COL_MEMO, memo_item)
            self._table.setItem(r, _COL_DEBIT, debit_item)
            self._table.setItem(r, _COL_CREDIT, credit_item)
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
            QMessageBox.warning(
                self, "Cannot save", escape_ampersand_for_qt(str(exc))
            )

    def _post_selected(self):
        if self._gl is None or self._current_account_id is None:
            QMessageBox.information(
                self, "Posting", "GL is not available for this session."
            )
            return
        acct = self._db.get_bank_account(self._current_account_id)
        bank_gl = (dict(acct).get("gl_display_account") or "").strip()
        if not bank_gl:
            QMessageBox.warning(
                self,
                "GL mapping",
                "Set the GL cash account on this bank account (Manage Accounts in Bank Import).",
            )
            return
        sel = sorted({i.row() for i in self._table.selectedIndexes()})
        if not sel:
            QMessageBox.information(self, "Posting", "Select one or more rows.")
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
        QMessageBox.information(
            self, "Posting", escape_ampersand_for_qt(msg)
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
        hdr = [
            "Date",
            "Ref",
            "Description",
            "Memo",
            "Amount",
            "COA",
            "Posted",
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
                w.writerow(
                    [
                        t.get("txn_date", ""),
                        t.get("ref_number", ""),
                        t.get("description", ""),
                        t.get("memo", ""),
                        t.get("amount", ""),
                        t.get("coa_account", ""),
                        int(t["is_posted"] or 0) if "is_posted" in t else 0,
                        match_txt,
                    ]
                )
        QMessageBox.information(
            self,
            "Export",
            f"Saved {escape_ampersand_for_qt(Path(path).name)}",
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
            QMessageBox.warning(
                self, "Cannot save", escape_ampersand_for_qt(str(exc))
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
                QMessageBox.warning(
                    self, "Cannot update", escape_ampersand_for_qt(str(exc))
                )
        self._reload_current()

    def _clear_needs_receipt(self):
        for tid in self._selected_txn_ids():
            try:
                self._db.update_transaction(tid, needs_receipt=0)
            except ValueError as exc:
                QMessageBox.warning(
                    self, "Cannot update", escape_ampersand_for_qt(str(exc))
                )
        self._reload_current()

    def _attach_file(self):
        ids = self._selected_txn_ids()
        if not ids:
            QMessageBox.information(self, "Attachment", "Select one or more rows.")
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
                QMessageBox.warning(
                    self, "Cannot update", escape_ampersand_for_qt(str(exc))
                )
        self._reload_current()

    def _clear_attachment(self):
        for tid in self._selected_txn_ids():
            try:
                self._db.update_transaction(tid, attachment_path="")
            except ValueError as exc:
                QMessageBox.warning(
                    self, "Cannot update", escape_ampersand_for_qt(str(exc))
                )
        self._reload_current()

    def _transfer_dialog(self):
        ids = self._selected_txn_ids()
        if not ids:
            QMessageBox.information(self, "Transfer", "Select at least one row.")
            return
        if self._current_account_id is None:
            return
        d = QDialog(self)
        d.setWindowTitle("Transfer to bank account")
        f = QFormLayout(d)
        cb = QComboBox()
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
                QMessageBox.warning(
                    self, "Cannot update", escape_ampersand_for_qt(str(exc))
                )
        self._reload_current()

    def _splits_dialog(self):
        ids = self._selected_txn_ids()
        if len(ids) != 1:
            QMessageBox.information(
                self, "Splits", "Select exactly one transaction to split."
            )
            return
        tid = ids[0]
        txn = self._db.get_transaction(tid)
        if txn is None or _txn_posted(dict(txn)):
            QMessageBox.information(
                self, "Splits", "Unposted transactions only."
            )
            return
        amt = float(txn["amount"])
        d = QDialog(self)
        d.setWindowTitle("Split amounts (must sum to bank amount)")
        f = QFormLayout(d)
        a1 = QDoubleSpinBox()
        a1.setRange(-9_999_999, 9_999_999)
        a1.setDecimals(2)
        a1.setValue(round(amt / 2.0, 2))
        c1 = QLineEdit()
        c1.setPlaceholderText("COA line 1")
        a2 = QDoubleSpinBox()
        a2.setRange(-9_999_999, 9_999_999)
        a2.setDecimals(2)
        a2.setValue(round(amt - a1.value(), 2))
        c2 = QLineEdit()
        c2.setPlaceholderText("COA line 2")
        f.addRow("Amount 1", a1)
        f.addRow("COA 1", c1)
        f.addRow("Amount 2", a2)
        f.addRow("COA 2", c2)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        s1 = (c1.text() or "").strip()
        s2 = (c2.text() or "").strip()
        if not s1 or not s2:
            QMessageBox.warning(self, "Splits", "Both COA lines are required.")
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
            QMessageBox.warning(
                self, "Splits", escape_ampersand_for_qt(str(exc))
            )
            return
        QMessageBox.information(self, "Splits", "Split lines saved.")
        self._reload_current()

    def _link_payment_dialog(self):
        ids = self._selected_txn_ids()
        if len(ids) != 1:
            QMessageBox.information(
                self, "Link", "Select exactly one bank transaction."
            )
            return
        tid = ids[0]
        d = QDialog(self)
        d.setWindowTitle("Link bank transaction")
        d.setMinimumWidth(520)
        outer = QVBoxLayout(d)

        try:
            existing = business.get_bank_match(self._db._conn, tid)
        except sqlite3.OperationalError:
            existing = None
        state = {"handled": False}

        if existing:
            lbl = QLabel(
                "Current link: "
                f"{escape_ampersand_for_qt(_bank_match_label(existing))}"
            )
            outer.addWidget(lbl)
            btn_clear = QPushButton("Clear link")
            outer.addWidget(btn_clear)

            def clear_link():
                business.unlink_bank_transaction(self._db._conn, tid)
                state["handled"] = True
                d.accept()
                self._reload_current()
                QMessageBox.information(self, "Link", "Link cleared.")

            btn_clear.clicked.connect(clear_link)

        outer.addWidget(QLabel("Suggested matches (by amount and date):"))
        sug_list = QListWidget()
        sug_list.setMinimumHeight(140)
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
            if not idx.isValid():
                return
            row = idx.row()
            m = QMenu(d)
            m.addAction(
                "Copy suggestion line",
                partial(copy_qlistwidget_row_text, sug_list, row),
            )
            m.exec(sug_list.viewport().mapToGlobal(pos))

        sug_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        sug_list.customContextMenuRequested.connect(on_sug_context_menu)
        outer.addWidget(sug_list)

        def apply_suggestion():
            cur = sug_list.currentItem()
            if cur is None:
                QMessageBox.information(self, "Link", "Select a suggestion.")
                return
            data = cur.data(Qt.ItemDataRole.UserRole)
            if not data:
                return
            lt, lid = data
            business.link_bank_transaction(self._db._conn, tid, str(lt), int(lid))
            state["handled"] = True
            d.accept()
            self._reload_current()
            QMessageBox.information(self, "Link", "Link saved.")

        sug_list.itemDoubleClicked.connect(lambda _item: apply_suggestion())
        row_sug = QHBoxLayout()
        row_sug.addWidget(QPushButton("Link selected suggestion", clicked=apply_suggestion))
        outer.addLayout(row_sug)

        outer.addWidget(QLabel("Manual link"))
        f = QFormLayout()
        kind = QComboBox()
        kind.addItem("AR payment", "ar_payment")
        kind.addItem("AP payment", "ap_payment")
        kind.addItem("Payroll run", "payroll_run")
        pay = QComboBox()
        pay.setMinimumWidth(360)
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
        QMessageBox.information(self, "Link", "Link saved.")
        self._reload_current()
