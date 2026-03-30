"""
desktop_app.bank_import_tab
============================
PySide6 widgets that implement the "Bank Import" feature (Issue #9, Phase 1).

Public classes:
- ColumnMappingDialog  – shown before importing, lets user map CSV columns.
- BankImportTab        – main tab widget: table, filters, import button.
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
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
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
    ):
        super().__init__()
        self._db = db
        self._path = path
        self._mapping = mapping

    def run(self):
        try:
            source_filename = Path(self._path).name
            transactions = parse_csv(self._path, self._mapping, source_filename)
            duplicates_map = flag_duplicates(transactions)
            # Fingerprints that appear > once within this file
            intra_file_dupes: set[str] = set(duplicates_map.keys())

            batch_id = self._db.create_batch(source_filename)

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

        # Toolbar row
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

        # Transactions table
        self._table = TransactionsTable(self._coa_list)
        root.addWidget(self._table, stretch=1)

        # Action row
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

        # Initial load
        self._refresh_batch_list()

    # -- batch management ----------------------------------------------------

    def _refresh_batch_list(self):
        """Reload the batch dropdown from the database."""
        self._cb_batch.blockSignals(True)
        self._cb_batch.clear()
        batches = self._db.list_batches()
        if not batches:
            self._cb_batch.addItem("(no imports yet)", None)
        else:
            for b in batches:
                label = f"{b['source_filename']}  [{b['imported_at'][:10]}]"
                self._cb_batch.addItem(label, b["id"])
        self._cb_batch.blockSignals(False)
        # Auto-select the first (most recent)
        if batches:
            self._current_batch_id = self._cb_batch.itemData(0)
            self._refresh_table()
        else:
            self._current_batch_id = None
            self._table.setRowCount(0)

    def _on_batch_changed(self, index: int):
        batch_id = self._cb_batch.itemData(index)
        self._current_batch_id = batch_id
        self._refresh_table()

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

    # -- import --------------------------------------------------------------

    def _on_import(self):
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

        dlg = ColumnMappingDialog(headers, preview, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        mapping = dlg.get_mapping()
        if mapping is None:
            return

        self._btn_import.setEnabled(False)
        self._lbl_status.setText("Importing…")

        self._worker = ImportWorker(self._db, path, mapping)
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
