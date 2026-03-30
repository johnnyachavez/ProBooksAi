"""
desktop_app.bank_import_tab
============================
PySide6 widgets that implement the "Bank Import" feature (Issue #9 Phase 1
+ Issue #12 bank-account setup and reconciliation).

Public classes:
- ManageAccountsDialog – CRUD dialog for bank accounts.
- StatementPeriodDialog – captures statement start/end dates and balances.
- ColumnMappingDialog   – shown before importing, lets user map CSV columns.
- BankImportTab         – main tab widget: account selector, table, filters,
                          reconciliation panel.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from probooksai.bank_import import (
    ColumnMapping,
    ParsedTransaction,
    ReconciliationResult,
    compute_reconciliation,
    flag_duplicates,
    parse_csv,
    read_csv_preview,
)
from probooksai.coa import coa_display_list, load_coa
from probooksai.database import DocumentDatabase

# ---------------------------------------------------------------------------
# Status colour palette
# ---------------------------------------------------------------------------

TXN_STATUS_COLORS = {
    "Imported": "#2196F3",   # blue
    "Reviewed": "#4CAF50",   # green
    "Posted":   "#607D8B",   # blue-grey
}

DUPLICATE_COLOR = QColor("#FF9800")    # amber
MISSING_COA_COLOR = QColor("#F44336")  # red


# ---------------------------------------------------------------------------
# Background import worker
# ---------------------------------------------------------------------------

class ImportWorker(QThread):
    """Parse CSV and persist rows off the UI thread."""

    progress = Signal(int, int)          # (current, total)
    finished = Signal(int, int, int)     # (batch_id, inserted, skipped_dupes)
    error    = Signal(str)

    def __init__(
        self,
        db: DocumentDatabase,
        path: str,
        mapping: ColumnMapping,
        bank_account_id: Optional[int] = None,
        statement_start_date: Optional[str] = None,
        statement_end_date: Optional[str] = None,
        beginning_balance: Optional[float] = None,
        ending_balance: Optional[float] = None,
    ):
        super().__init__()
        self._db = db
        self._path = path
        self._mapping = mapping
        self._bank_account_id = bank_account_id
        self._statement_start_date = statement_start_date
        self._statement_end_date = statement_end_date
        self._beginning_balance = beginning_balance
        self._ending_balance = ending_balance

    def run(self):
        try:
            source_filename = Path(self._path).name
            transactions = parse_csv(self._path, self._mapping, source_filename)
            duplicates_map = flag_duplicates(transactions)
            # Fingerprints that appear > once within this file
            intra_file_dupes: set[str] = set(duplicates_map.keys())

            batch_id = self._db.create_batch(
                source_filename,
                bank_account_id=self._bank_account_id,
                statement_start_date=self._statement_start_date,
                statement_end_date=self._statement_end_date,
                beginning_balance=self._beginning_balance,
                ending_balance=self._ending_balance,
            )

            inserted = 0
            skipped_dupes = 0
            total = len(transactions)

            for i, txn in enumerate(transactions):
                # Cross-file duplicate check (already in DB)
                cross_file_dupe = self._db.fingerprint_exists(
                    txn.fingerprint, exclude_batch_id=batch_id
                )
                is_dupe = txn.fingerprint in intra_file_dupes or cross_file_dupe

                parse_errors_json = (
                    json.dumps(txn.parse_errors) if txn.parse_errors else None
                )

                self._db.insert_transaction(
                    batch_id=batch_id,
                    posted_date=txn.posted_date.isoformat() if txn.posted_date else None,
                    description=txn.description,
                    amount=txn.amount,
                    currency=txn.currency,
                    source_row=txn.source_row,
                    fingerprint=txn.fingerprint,
                    status="Imported",
                    is_duplicate=is_dupe,
                    parse_errors=parse_errors_json,
                )
                if is_dupe:
                    skipped_dupes += 1
                inserted += 1
                self.progress.emit(i + 1, total)

            self.finished.emit(batch_id, inserted, skipped_dupes)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Manage Accounts Dialog
# ---------------------------------------------------------------------------

class ManageAccountsDialog(QDialog):
    """
    Simple CRUD dialog for bank accounts.
    """

    def __init__(self, db: DocumentDatabase, parent=None):
        super().__init__(parent)
        self._db = db
        self.setWindowTitle("Manage Bank Accounts")
        self.resize(480, 380)
        self._build_ui()
        self._refresh_list()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Account list
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_selection_changed)
        layout.addWidget(self._list)

        # Form
        form_group = QGroupBox("Account Details")
        form = QFormLayout(form_group)
        self._le_name = QLineEdit()
        self._le_name.setPlaceholderText("e.g. Business Checking")
        self._le_institution = QLineEdit()
        self._le_institution.setPlaceholderText("e.g. Chase")
        self._le_last4 = QLineEdit()
        self._le_last4.setPlaceholderText("e.g. 2443")
        self._le_last4.setMaxLength(10)
        form.addRow("Name *:", self._le_name)
        form.addRow("Institution:", self._le_institution)
        form.addRow("Last 4 digits:", self._le_last4)
        layout.addWidget(form_group)

        # Buttons
        btn_row = QHBoxLayout()
        self._btn_add = QPushButton("➕ Add")
        self._btn_add.clicked.connect(self._on_add)
        self._btn_update = QPushButton("✏️ Update")
        self._btn_update.clicked.connect(self._on_update)
        self._btn_update.setEnabled(False)
        self._btn_delete = QPushButton("🗑 Delete")
        self._btn_delete.clicked.connect(self._on_delete)
        self._btn_delete.setEnabled(False)
        btn_row.addWidget(self._btn_add)
        btn_row.addWidget(self._btn_update)
        btn_row.addWidget(self._btn_delete)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        close_row = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_row.rejected.connect(self.accept)
        layout.addWidget(close_row)

    def _refresh_list(self):
        self._list.clear()
        self._accounts = self._db.list_bank_accounts()
        for acc in self._accounts:
            parts = [acc["name"]]
            if acc["institution"]:
                parts.append(acc["institution"])
            if acc["last4"]:
                parts.append(f"…{acc['last4']}")
            self._list.addItem(" | ".join(parts))

    def _on_selection_changed(self, row: int):
        has = 0 <= row < len(self._accounts)
        self._btn_update.setEnabled(has)
        self._btn_delete.setEnabled(has)
        if has:
            acc = self._accounts[row]
            self._le_name.setText(acc["name"] or "")
            self._le_institution.setText(acc["institution"] or "")
            self._le_last4.setText(acc["last4"] or "")

    def _on_add(self):
        name = self._le_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Account name is required.")
            return
        self._db.create_bank_account(
            name=name,
            institution=self._le_institution.text().strip() or None,
            last4=self._le_last4.text().strip() or None,
        )
        self._refresh_list()
        self._le_name.clear()
        self._le_institution.clear()
        self._le_last4.clear()

    def _on_update(self):
        row = self._list.currentRow()
        if not (0 <= row < len(self._accounts)):
            return
        name = self._le_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Account name is required.")
            return
        acc = self._accounts[row]
        self._db.update_bank_account(
            acc["id"],
            name=name,
            institution=self._le_institution.text().strip() or None,
            last4=self._le_last4.text().strip() or None,
        )
        self._refresh_list()

    def _on_delete(self):
        row = self._list.currentRow()
        if not (0 <= row < len(self._accounts)):
            return
        acc = self._accounts[row]
        reply = QMessageBox.question(
            self,
            "Delete Account",
            f"Delete account '{acc['name']}'?\n"
            "Existing import batches will become unlinked (not deleted).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._db.delete_bank_account(acc["id"])
            self._refresh_list()


# ---------------------------------------------------------------------------
# Statement Period Dialog
# ---------------------------------------------------------------------------

class StatementPeriodDialog(QDialog):
    """
    Captures statement start/end dates and beginning/ending balances
    for an import batch.  Shown after the CSV has been parsed.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Statement Period & Balances")
        self.resize(360, 240)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self._le_start = QLineEdit()
        self._le_start.setPlaceholderText("YYYY-MM-DD  e.g. 2024-03-01")
        self._le_end = QLineEdit()
        self._le_end.setPlaceholderText("YYYY-MM-DD  e.g. 2024-03-29")

        self._sb_begin = QDoubleSpinBox()
        self._sb_begin.setRange(-999_999_999, 999_999_999)
        self._sb_begin.setDecimals(2)
        self._sb_begin.setSingleStep(1.0)
        self._sb_begin.setPrefix("$")

        self._sb_end = QDoubleSpinBox()
        self._sb_end.setRange(-999_999_999, 999_999_999)
        self._sb_end.setDecimals(2)
        self._sb_end.setSingleStep(1.0)
        self._sb_end.setPrefix("$")

        form.addRow("Statement start date:", self._le_start)
        form.addRow("Statement end date:", self._le_end)
        form.addRow("Beginning balance:", self._sb_begin)
        form.addRow("Ending balance:", self._sb_end)
        layout.addLayout(form)

        note = QLabel("Dates accept any range (e.g. Mar 01 – Mar 29).  Leave blank to skip.")
        note.setWordWrap(True)
        layout.addWidget(note)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    # -- accessors -----------------------------------------------------------

    def statement_start_date(self) -> Optional[str]:
        v = self._le_start.text().strip()
        return v or None

    def statement_end_date(self) -> Optional[str]:
        v = self._le_end.text().strip()
        return v or None

    def beginning_balance(self) -> float:
        return self._sb_begin.value()

    def ending_balance(self) -> float:
        return self._sb_end.value()


# ---------------------------------------------------------------------------
# Column Mapping Dialog
# ---------------------------------------------------------------------------

class ColumnMappingDialog(QDialog):
    """
    Modal dialog that lets the user map CSV columns to transaction fields
    and previews the first ~10 rows.
    """

    def __init__(self, headers: list[str], preview_rows: list[list[str]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Map CSV Columns")
        self.resize(760, 560)
        self._headers = headers
        self._mapping: Optional[ColumnMapping] = None

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # -- Mapping form ----------------------------------------------------
        form_group = QGroupBox("Column Mapping")
        form = QFormLayout(form_group)

        choices = ["(not mapped)"] + headers
        auto = ColumnMapping.auto_detect(headers)

        self._cb_date        = self._make_combo(choices, auto.date)
        self._cb_description = self._make_combo(choices, auto.description)
        self._cb_amount      = self._make_combo(choices, auto.amount)
        self._cb_debit       = self._make_combo(choices, auto.debit)
        self._cb_credit      = self._make_combo(choices, auto.credit)
        self._cb_balance     = self._make_combo(choices, auto.balance)
        self._cb_currency    = self._make_combo(choices, auto.currency)
        self._cb_reference   = self._make_combo(choices, auto.reference)

        form.addRow("Date *:", self._cb_date)
        form.addRow("Description *:", self._cb_description)
        form.addRow("Amount (signed):", self._cb_amount)
        form.addRow("Debit:", self._cb_debit)
        form.addRow("Credit:", self._cb_credit)
        form.addRow("Balance:", self._cb_balance)
        form.addRow("Currency:", self._cb_currency)
        form.addRow("Reference:", self._cb_reference)

        layout.addWidget(form_group)

        note = QLabel(
            "* Required.  Use either <b>Amount</b> (signed) "
            "<i>or</i> both <b>Debit</b> and <b>Credit</b> columns."
        )
        note.setWordWrap(True)
        note.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(note)

        # -- Preview table ---------------------------------------------------
        preview_group = QGroupBox(f"Preview (first {len(preview_rows)} data rows)")
        preview_layout = QVBoxLayout(preview_group)
        self._preview = QTableWidget()
        self._preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._preview.setAlternatingRowColors(True)
        self._preview.setColumnCount(len(headers))
        self._preview.setHorizontalHeaderLabels(headers)
        self._preview.setRowCount(len(preview_rows))
        self._preview.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        for r, row in enumerate(preview_rows):
            for c, val in enumerate(row):
                self._preview.setItem(r, c, QTableWidgetItem(val))
        preview_layout.addWidget(self._preview)
        layout.addWidget(preview_group)

        # -- Buttons ---------------------------------------------------------
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    # -- helpers -------------------------------------------------------------

    def _make_combo(self, choices: list[str], default: Optional[str]) -> QComboBox:
        cb = QComboBox()
        cb.addItems(choices)
        if default and default in choices:
            cb.setCurrentText(default)
        return cb

    def _selected(self, cb: QComboBox) -> Optional[str]:
        val = cb.currentText()
        return None if val == "(not mapped)" else val

    def _on_accept(self):
        m = ColumnMapping(
            date=self._selected(self._cb_date),
            description=self._selected(self._cb_description),
            amount=self._selected(self._cb_amount),
            debit=self._selected(self._cb_debit),
            credit=self._selected(self._cb_credit),
            balance=self._selected(self._cb_balance),
            currency=self._selected(self._cb_currency),
            reference=self._selected(self._cb_reference),
        )
        errors = m.validate()
        if errors:
            QMessageBox.warning(self, "Mapping Incomplete", "\n".join(errors))
            return
        self._mapping = m
        self.accept()

    def get_mapping(self) -> Optional[ColumnMapping]:
        return self._mapping


# ---------------------------------------------------------------------------
# Transactions table
# ---------------------------------------------------------------------------

class TransactionsTable(QTableWidget):
    """
    Editable table showing imported bank transactions.

    Columns: #, Date, Description, Amount, COA Account, Status, Flags
    """

    COLUMNS = ["ID", "Date", "Description", "Amount", "COA Account", "Status", "⚑"]
    COL_ID   = 0
    COL_DATE = 1
    COL_DESC = 2
    COL_AMT  = 3
    COL_COA  = 4
    COL_STAT = 5
    COL_FLAG = 6

    def __init__(self, coa_list: list[str], parent=None):
        super().__init__(parent)
        self._coa_list = coa_list
        self.setColumnCount(len(self.COLUMNS))
        self.setHorizontalHeaderLabels(self.COLUMNS)
        self.horizontalHeader().setStretchLastSection(False)
        hh = self.horizontalHeader()
        hh.setSectionResizeMode(self.COL_ID,   QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(self.COL_DATE, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(self.COL_DESC, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(self.COL_AMT,  QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(self.COL_COA,  QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(self.COL_STAT, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(self.COL_FLAG, QHeaderView.ResizeMode.ResizeToContents)
        self.setColumnWidth(self.COL_COA, 200)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.setSortingEnabled(True)

    def populate(self, rows: list):
        """Fill the table from a list of sqlite3.Row objects."""
        self.setSortingEnabled(False)
        self.setRowCount(0)
        for row in rows:
            r = self.rowCount()
            self.insertRow(r)

            # ID (hidden col – keeps stable row identity)
            id_item = QTableWidgetItem(str(row["id"]))
            id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.setItem(r, self.COL_ID, id_item)

            # Date
            date_item = QTableWidgetItem(row["posted_date"] or "")
            self.setItem(r, self.COL_DATE, date_item)

            # Description
            desc_item = QTableWidgetItem(row["description"] or "")
            self.setItem(r, self.COL_DESC, desc_item)

            # Amount
            amt = row["amount"]
            amt_item = QTableWidgetItem(
                f"{amt:,.2f}" if amt is not None else ""
            )
            amt_item.setTextAlignment(
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            )
            if amt is not None and amt < 0:
                amt_item.setForeground(QBrush(QColor("#D32F2F")))
            self.setItem(r, self.COL_AMT, amt_item)

            # COA – editable ComboBox
            coa_cb = QComboBox()
            coa_cb.addItem("– select –")
            coa_cb.addItems(self._coa_list)
            current_coa = row["coa_account"] or ""
            idx = coa_cb.findText(current_coa)
            if idx >= 0:
                coa_cb.setCurrentIndex(idx)
            self.setCellWidget(r, self.COL_COA, coa_cb)

            # Status
            status = row["status"] or "Imported"
            status_item = QTableWidgetItem(status)
            status_item.setForeground(
                QBrush(QColor(TXN_STATUS_COLORS.get(status, "#000")))
            )
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.setItem(r, self.COL_STAT, status_item)

            # Flag column
            flags: list[str] = []
            if not (row["coa_account"] or "").strip():
                flags.append("missing COA")
            if row["is_duplicate"]:
                flags.append("duplicate")
            flag_text = ", ".join(flags)
            flag_item = QTableWidgetItem(flag_text)
            flag_item.setFlags(flag_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if "duplicate" in flag_text:
                flag_item.setForeground(QBrush(DUPLICATE_COLOR))
            elif "missing COA" in flag_text:
                flag_item.setForeground(QBrush(MISSING_COA_COLOR))
            self.setItem(r, self.COL_FLAG, flag_item)

        self.setSortingEnabled(True)

    def selected_ids(self) -> list[int]:
        """Return the transaction IDs of all selected rows."""
        ids: list[int] = []
        seen: set[int] = set()
        for item in self.selectedItems():
            r = item.row()
            if r in seen:
                continue
            seen.add(r)
            id_item = self.item(r, self.COL_ID)
            if id_item:
                ids.append(int(id_item.text()))
        return ids

    def coa_for_row(self, row: int) -> str:
        """Return the currently selected COA text for the given row index."""
        cb = self.cellWidget(row, self.COL_COA)
        if isinstance(cb, QComboBox):
            val = cb.currentText()
            return "" if val == "– select –" else val
        return ""


# ---------------------------------------------------------------------------
# Bank Import Tab
# ---------------------------------------------------------------------------

class BankImportTab(QWidget):
    """
    Full Bank Import screen – lives as a tab in the main window.
    """

    def __init__(self, db: DocumentDatabase, parent=None):
        super().__init__(parent)
        self._db = db
        self._coa_list = coa_display_list(load_coa())
        self._current_batch_id: Optional[int] = None
        self._worker: Optional[ImportWorker] = None

        self._build_ui()

    # -- UI construction -----------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── Row 1: Account selector ─────────────────────────────────────────
        account_row = QHBoxLayout()
        account_row.addWidget(QLabel("Bank Account:"))
        self._cb_account = QComboBox()
        self._cb_account.setMinimumWidth(240)
        self._cb_account.currentIndexChanged.connect(self._on_account_changed)
        account_row.addWidget(self._cb_account)

        self._btn_manage_accounts = QPushButton("⚙ Manage Accounts")
        self._btn_manage_accounts.clicked.connect(self._on_manage_accounts)
        account_row.addWidget(self._btn_manage_accounts)

        account_row.addStretch()
        root.addLayout(account_row)

        # ── Row 2: Toolbar ──────────────────────────────────────────────────
        toolbar = QHBoxLayout()

        self._btn_import = QPushButton("📂  Import Statement…")
        self._btn_import.setMinimumHeight(32)
        self._btn_import.setStyleSheet(
            "background: #1565C0; color: white; font-weight: bold; padding: 4px 12px;"
        )
        self._btn_import.clicked.connect(self._on_import)
        toolbar.addWidget(self._btn_import)

        toolbar.addSpacing(12)

        # Batch selector
        lbl_batch = QLabel("Batch:")
        toolbar.addWidget(lbl_batch)
        self._cb_batch = QComboBox()
        self._cb_batch.setMinimumWidth(260)
        self._cb_batch.currentIndexChanged.connect(self._on_batch_changed)
        toolbar.addWidget(self._cb_batch)

        toolbar.addStretch()

        # Search
        lbl_search = QLabel("Search:")
        toolbar.addWidget(lbl_search)
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Filter by description…")
        self._search_box.setMinimumWidth(180)
        self._search_box.textChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self._search_box)

        # Status filter
        lbl_status = QLabel("Status:")
        toolbar.addWidget(lbl_status)
        self._cb_status = QComboBox()
        self._cb_status.addItems(["All", "Imported", "Reviewed", "Posted"])
        self._cb_status.currentIndexChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self._cb_status)

        # Needs-review toggle
        self._btn_needs_review = QPushButton("⚑ Needs Review Only")
        self._btn_needs_review.setCheckable(True)
        self._btn_needs_review.toggled.connect(self._on_filter_changed)
        toolbar.addWidget(self._btn_needs_review)

        root.addLayout(toolbar)

        # ── Transactions table ──────────────────────────────────────────────
        self._table = TransactionsTable(self._coa_list)
        root.addWidget(self._table, stretch=1)

        # ── Action row ──────────────────────────────────────────────────────
        action_row = QHBoxLayout()

        self._btn_mark_reviewed = QPushButton("✅  Mark Reviewed")
        self._btn_mark_reviewed.setMinimumHeight(30)
        self._btn_mark_reviewed.setStyleSheet(
            "background: #388E3C; color: white; font-weight: bold;"
        )
        self._btn_mark_reviewed.clicked.connect(self._on_mark_reviewed)
        action_row.addWidget(self._btn_mark_reviewed)

        self._btn_apply_coa = QPushButton("🏷  Apply Category to Selected")
        self._btn_apply_coa.setMinimumHeight(30)
        self._btn_apply_coa.setStyleSheet(
            "background: #6A1B9A; color: white; font-weight: bold;"
        )
        self._btn_apply_coa.clicked.connect(self._on_apply_coa)
        action_row.addWidget(self._btn_apply_coa)

        action_row.addStretch()

        self._lbl_status = QLabel("Import a CSV bank statement to get started.")
        action_row.addWidget(self._lbl_status)

        root.addLayout(action_row)

        # ── Reconciliation panel ────────────────────────────────────────────
        recon_group = QGroupBox("Reconciliation")
        recon_layout = QHBoxLayout(recon_group)
        recon_layout.setSpacing(20)

        self._lbl_recon_period   = QLabel("Period: —")
        self._lbl_recon_begin    = QLabel("Beginning: —")
        self._lbl_recon_sum      = QLabel("Transactions: —")
        self._lbl_recon_expected = QLabel("Expected ending: —")
        self._lbl_recon_ending   = QLabel("Statement ending: —")
        self._lbl_recon_diff     = QLabel("Difference: —")

        for lbl in (
            self._lbl_recon_period,
            self._lbl_recon_begin,
            self._lbl_recon_sum,
            self._lbl_recon_expected,
            self._lbl_recon_ending,
            self._lbl_recon_diff,
        ):
            recon_layout.addWidget(lbl)

        recon_layout.addStretch()

        self._btn_reconcile = QPushButton("🔒  Mark Reconciled")
        self._btn_reconcile.setMinimumHeight(30)
        self._btn_reconcile.setStyleSheet(
            "background: #F57F17; color: white; font-weight: bold;"
        )
        self._btn_reconcile.setEnabled(False)
        self._btn_reconcile.clicked.connect(self._on_mark_reconciled)
        recon_layout.addWidget(self._btn_reconcile)

        self._btn_set_statement = QPushButton("📋  Set Statement Dates/Balances")
        self._btn_set_statement.clicked.connect(self._on_set_statement)
        self._btn_set_statement.setEnabled(False)
        recon_layout.addWidget(self._btn_set_statement)

        root.addWidget(recon_group)

        # Initial load
        self._refresh_account_list()

    # -- account management --------------------------------------------------

    def _refresh_account_list(self):
        """Reload the account dropdown from the database."""
        self._cb_account.blockSignals(True)
        self._cb_account.clear()
        self._cb_account.addItem("(all accounts)", None)
        accounts = self._db.list_bank_accounts()
        for acc in accounts:
            label = acc["name"]
            if acc["institution"]:
                label += f" — {acc['institution']}"
            if acc["last4"]:
                label += f" …{acc['last4']}"
            self._cb_account.addItem(label, acc["id"])
        self._cb_account.blockSignals(False)
        self._refresh_batch_list()

    def _current_account_id(self) -> Optional[int]:
        return self._cb_account.currentData()

    def _on_account_changed(self, _index: int):
        self._refresh_batch_list()

    def _on_manage_accounts(self):
        dlg = ManageAccountsDialog(self._db, parent=self)
        dlg.exec()
        self._refresh_account_list()

    # -- batch management ----------------------------------------------------

    def _refresh_batch_list(self):
        """Reload the batch dropdown from the database."""
        self._cb_batch.blockSignals(True)
        self._cb_batch.clear()
        account_id = self._current_account_id()
        batches = self._db.list_batches(bank_account_id=account_id)
        if not batches:
            self._cb_batch.addItem("(no imports yet)", None)
        else:
            for b in batches:
                period = ""
                if b["statement_start_date"] and b["statement_end_date"]:
                    period = f"  {b['statement_start_date']} → {b['statement_end_date']}"
                recon = " ✓" if b["is_reconciled"] else ""
                label = f"{b['source_filename']}  [{b['imported_at'][:10]}]{period}{recon}"
                self._cb_batch.addItem(label, b["id"])
        self._cb_batch.blockSignals(False)
        # Auto-select the first (most recent)
        if batches:
            self._current_batch_id = self._cb_batch.itemData(0)
            self._refresh_table()
            self._refresh_reconciliation()
        else:
            self._current_batch_id = None
            self._table.setRowCount(0)
            self._clear_reconciliation()

    def _on_batch_changed(self, index: int):
        batch_id = self._cb_batch.itemData(index)
        self._current_batch_id = batch_id
        self._refresh_table()
        self._refresh_reconciliation()

    # -- table refresh -------------------------------------------------------

    def _refresh_table(self):
        if self._current_batch_id is None:
            self._table.setRowCount(0)
            return

        status_filter = self._cb_status.currentText()
        search_text   = self._search_box.text().strip()
        needs_review  = self._btn_needs_review.isChecked()

        rows = self._db.list_transactions(
            batch_id=self._current_batch_id,
            status=None if status_filter == "All" else status_filter,
            search=search_text or None,
            needs_review_only=needs_review,
        )
        self._table.populate(rows)
        self._lbl_status.setText(f"{len(rows)} transaction(s) displayed.")

    def _on_filter_changed(self):
        self._refresh_table()

    # -- reconciliation panel ------------------------------------------------

    def _clear_reconciliation(self):
        self._lbl_recon_period.setText("Period: —")
        self._lbl_recon_begin.setText("Beginning: —")
        self._lbl_recon_sum.setText("Transactions: —")
        self._lbl_recon_expected.setText("Expected ending: —")
        self._lbl_recon_ending.setText("Statement ending: —")
        self._lbl_recon_diff.setText("Difference: —")
        self._btn_reconcile.setEnabled(False)
        self._btn_set_statement.setEnabled(False)

    def _refresh_reconciliation(self):
        if self._current_batch_id is None:
            self._clear_reconciliation()
            return

        batch = self._db.get_batch(self._current_batch_id)
        if batch is None:
            self._clear_reconciliation()
            return

        self._btn_set_statement.setEnabled(True)

        # Period label
        start = batch["statement_start_date"] or "?"
        end   = batch["statement_end_date"] or "?"
        if start != "?" or end != "?":
            self._lbl_recon_period.setText(f"Period: {start} → {end}")
        else:
            self._lbl_recon_period.setText("Period: (not set)")

        begin_bal = batch["beginning_balance"]
        end_bal   = batch["ending_balance"]

        if begin_bal is None or end_bal is None:
            self._lbl_recon_begin.setText("Beginning: (not set)")
            self._lbl_recon_sum.setText("Transactions: —")
            self._lbl_recon_expected.setText("Expected ending: —")
            self._lbl_recon_ending.setText("Statement ending: (not set)")
            self._lbl_recon_diff.setText("Difference: —")
            self._btn_reconcile.setEnabled(False)
            return

        # Compute reconciliation from all transactions in the batch
        all_txns = self._db.list_transactions(batch_id=self._current_batch_id)
        amounts = [row["amount"] for row in all_txns]
        result = compute_reconciliation(begin_bal, end_bal, amounts)

        self._lbl_recon_begin.setText(f"Beginning: ${begin_bal:,.2f}")
        self._lbl_recon_sum.setText(f"Transactions: ${result.sum_transactions:,.2f}")
        self._lbl_recon_expected.setText(f"Expected ending: ${result.expected_ending:,.2f}")
        self._lbl_recon_ending.setText(f"Statement ending: ${end_bal:,.2f}")

        diff_text = f"${result.difference:,.2f}"
        diff_icon = "✓" if result.is_balanced else "⚠"
        diff_color = "green" if result.is_balanced else "red"
        self._lbl_recon_diff.setText(
            f'<b><span style="color:{diff_color}">{diff_icon} Difference: {diff_text}</span></b>'
        )
        self._lbl_recon_diff.setTextFormat(Qt.TextFormat.RichText)

        # Mark Reconciled only enabled when balanced and not already reconciled
        already_reconciled = bool(batch["is_reconciled"])
        self._btn_reconcile.setEnabled(result.is_balanced and not already_reconciled)
        if already_reconciled:
            self._btn_reconcile.setText("✓ Reconciled")
        else:
            self._btn_reconcile.setText("🔒  Mark Reconciled")

    def _on_set_statement(self):
        """Show the statement period/balance dialog and update the batch."""
        if self._current_batch_id is None:
            return
        batch = self._db.get_batch(self._current_batch_id)
        dlg = StatementPeriodDialog(parent=self)
        # Pre-fill if already set
        if batch and batch["statement_start_date"]:
            dlg._le_start.setText(batch["statement_start_date"])
        if batch and batch["statement_end_date"]:
            dlg._le_end.setText(batch["statement_end_date"])
        if batch and batch["beginning_balance"] is not None:
            dlg._sb_begin.setValue(batch["beginning_balance"])
        if batch and batch["ending_balance"] is not None:
            dlg._sb_end.setValue(batch["ending_balance"])

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        # Update account link too if an account is selected
        account_id = self._current_account_id()
        self._db.update_batch_statement(
            self._current_batch_id,
            bank_account_id=account_id,
            statement_start_date=dlg.statement_start_date(),
            statement_end_date=dlg.statement_end_date(),
            beginning_balance=dlg.beginning_balance(),
            ending_balance=dlg.ending_balance(),
        )
        self._refresh_batch_list()
        self._refresh_reconciliation()

    def _on_mark_reconciled(self):
        if self._current_batch_id is None:
            return
        batch = self._db.get_batch(self._current_batch_id)
        begin_bal = batch["beginning_balance"]
        end_bal   = batch["ending_balance"]
        if begin_bal is None or end_bal is None:
            QMessageBox.warning(self, "Missing Data", "Set beginning and ending balances first.")
            return
        all_txns = self._db.list_transactions(batch_id=self._current_batch_id)
        amounts = [row["amount"] for row in all_txns]
        result = compute_reconciliation(begin_bal, end_bal, amounts)
        if not result.is_balanced:
            QMessageBox.warning(
                self,
                "Not Balanced",
                f"Cannot reconcile: difference is ${result.difference:,.2f}.\n"
                "Resolve all discrepancies before marking reconciled.",
            )
            return
        self._db.mark_batch_reconciled(self._current_batch_id, result.difference)
        self._refresh_batch_list()
        self._refresh_reconciliation()
        self._lbl_status.setText("Batch marked as reconciled.")

    # -- import --------------------------------------------------------------

    def _on_import(self):
        # Require an account to be selected
        account_id = self._current_account_id()
        if account_id is None:
            reply = QMessageBox.question(
                self,
                "No Account Selected",
                "No specific bank account is selected.\n"
                "Import will not be linked to an account.\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Bank Statement",
            "",
            "CSV Files (*.csv);;All Files (*.*)",
        )
        if not path:
            return

        try:
            headers, preview = read_csv_preview(path, max_rows=10)
        except (OSError, UnicodeDecodeError, csv.Error) as exc:
            QMessageBox.critical(self, "Read Error", f"Could not read file:\n{exc}")
            return

        if not headers:
            QMessageBox.warning(
                self, "Empty File",
                "The selected CSV file appears to have no columns."
            )
            return

        # Column mapping
        dlg = ColumnMappingDialog(headers, preview, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        mapping = dlg.get_mapping()
        if mapping is None:
            return

        # Statement period / balances
        stmt_dlg = StatementPeriodDialog(parent=self)
        if stmt_dlg.exec() != QDialog.DialogCode.Accepted:
            return

        self._btn_import.setEnabled(False)
        self._lbl_status.setText("Importing…")

        self._worker = ImportWorker(
            self._db,
            path,
            mapping,
            bank_account_id=account_id,
            statement_start_date=stmt_dlg.statement_start_date(),
            statement_end_date=stmt_dlg.statement_end_date(),
            beginning_balance=stmt_dlg.beginning_balance(),
            ending_balance=stmt_dlg.ending_balance(),
        )
        self._worker.progress.connect(self._on_import_progress)
        self._worker.finished.connect(self._on_import_finished)
        self._worker.error.connect(self._on_import_error)
        self._worker.start()

    def _on_import_progress(self, current: int, total: int):
        self._lbl_status.setText(f"Importing… {current}/{total}")

    def _on_import_finished(self, batch_id: int, inserted: int, dupes: int):
        self._btn_import.setEnabled(True)
        self._refresh_batch_list()
        # Select the newly created batch
        for i in range(self._cb_batch.count()):
            if self._cb_batch.itemData(i) == batch_id:
                self._cb_batch.setCurrentIndex(i)
                break
        msg = f"Import complete: {inserted} row(s) inserted."
        if dupes:
            msg += f"  {dupes} flagged as potential duplicate(s)."
        self._lbl_status.setText(msg)

    def _on_import_error(self, error: str):
        self._btn_import.setEnabled(True)
        self._lbl_status.setText("Import failed.")
        QMessageBox.critical(self, "Import Error", f"An error occurred:\n{error}")

    # -- actions -------------------------------------------------------------

    def _on_mark_reviewed(self):
        ids = self._table.selected_ids()
        if not ids:
            QMessageBox.information(self, "No Selection", "Select rows to mark as Reviewed.")
            return
        self._db.mark_transactions_reviewed(ids)
        # Also persist any COA edits made in the same action
        self._save_coa_edits(ids)
        self._refresh_table()
        self._lbl_status.setText(f"Marked {len(ids)} row(s) as Reviewed.")

    def _on_apply_coa(self):
        """
        Apply the COA from the *first* selected row to all selected rows.
        """
        ids = self._table.selected_ids()
        if not ids:
            QMessageBox.information(self, "No Selection", "Select rows to apply a category.")
            return

        # Find the COA from the first selected row
        selected_rows = [
            r for r in range(self._table.rowCount())
            if self._table.item(r, TransactionsTable.COL_ID) is not None
            and int(self._table.item(r, TransactionsTable.COL_ID).text()) in ids
        ]
        if not selected_rows:
            return

        coa = self._table.coa_for_row(selected_rows[0])
        if not coa:
            QMessageBox.warning(
                self, "No Category",
                "Please select a COA category in one of the selected rows first."
            )
            return

        for txn_id in ids:
            self._db.update_transaction(txn_id, coa_account=coa)

        self._refresh_table()
        self._lbl_status.setText(
            f"Applied '{coa}' to {len(ids)} row(s)."
        )

    def _save_coa_edits(self, txn_ids: list[int]):
        """
        Persist any COA dropdown changes for the given transaction IDs.
        """
        id_to_row: dict[int, int] = {}
        for r in range(self._table.rowCount()):
            id_item = self._table.item(r, TransactionsTable.COL_ID)
            if id_item:
                id_to_row[int(id_item.text())] = r

        for txn_id in txn_ids:
            row = id_to_row.get(txn_id)
            if row is None:
                continue
            coa = self._table.coa_for_row(row)
            if coa:
                self._db.update_transaction(txn_id, coa_account=coa)
