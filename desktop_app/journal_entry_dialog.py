"""Journal Entry Edit / New dialog.

Lets the user create a new manual journal entry or edit an existing one.
Balancing is enforced on save (total debits must equal total credits).
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from desktop_app.flexible_date import configure_qdate_edit_us
from desktop_app.qt_mnemonic import (
    escape_ampersand_for_qt,
    message_box_warning_ok,
    tip_qdialog_button_box,
)

_MIN_LINES = 8   # blank rows shown so the user can add splits


class JournalEntryDialog(QDialog):
    """
    Edit an existing journal entry or compose a new one.

    Pass *entry_id=None* to create; pass an existing id to edit.
    *gl* must be a ``GLDatabase`` instance.
    *coa_list* is a list of COA display strings (``'NNNN – Name'``) for the account dropdown.
    """

    def __init__(
        self,
        gl,
        *,
        entry_id: Optional[int] = None,
        coa_list: list[str] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._gl = gl
        self._entry_id = entry_id
        self._coa_list = coa_list or []
        self._is_new = entry_id is None

        title = "New Journal Entry" if self._is_new else f"Edit Journal Entry #{entry_id}"
        self.setWindowTitle(title)
        self.setMinimumSize(760, 520)
        self._build_ui()

        if not self._is_new:
            self._load_entry(entry_id)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(10)

        # Header fields
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._date_edit = QDateEdit()
        configure_qdate_edit_us(self._date_edit)
        today = date.today()
        self._date_edit.setDate(QDate(today.year, today.month, today.day))
        self._date_edit.setToolTip("Entry date (MM/DD/YYYY). Type compactly, e.g. 010126 → 01/01/2026.")
        form.addRow("Date", self._date_edit)

        self._memo_edit = QLineEdit()
        self._memo_edit.setToolTip("Short description of this journal entry (stored as memo).")
        self._memo_edit.setPlaceholderText("e.g. Depreciation — Jan 2026")
        form.addRow("Memo", self._memo_edit)

        root.addLayout(form)

        # Balance indicator
        bal_row = QHBoxLayout()
        bal_row.addStretch()
        self._lbl_balance = QLabel("Debits: $0.00   Credits: $0.00   Difference: $0.00")
        self._lbl_balance.setStyleSheet("color: #A8B4C9; font-size: 11px;")
        bal_row.addWidget(self._lbl_balance)
        root.addLayout(bal_row)

        # Lines table
        lbl_lines = QLabel("Journal Lines  (Debits = Credits to save)")
        lbl_lines.setStyleSheet("font-weight: bold;")
        root.addWidget(lbl_lines)

        self._tbl = QTableWidget(0, 4)
        self._tbl.setHorizontalHeaderLabels(["Account (COA)", "Debit", "Credit", "Description / Memo"])
        hdr = self._tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._tbl.setColumnWidth(1, 110)
        self._tbl.setColumnWidth(2, 110)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tbl.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self._tbl.setToolTip(
            "One line per account. Enter Debit OR Credit for each line. "
            "Total debits must equal total credits to save."
        )
        self._ensure_blank_rows(_MIN_LINES)
        self._tbl.cellChanged.connect(self._on_cell_changed)
        root.addWidget(self._tbl, 1)

        # Add-row button
        add_row = QHBoxLayout()
        btn_add = QPushButton("+ Add line")
        btn_add.setToolTip("Append a blank line to the journal entry.")
        btn_add.clicked.connect(self._add_blank_row)
        add_row.addWidget(btn_add)
        add_row.addStretch()
        root.addLayout(add_row)

        # OK / Cancel
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        tip_qdialog_button_box(
            buttons,
            ok="Save the journal entry (debits must equal credits).",
            cancel="Discard changes and close.",
        )
        root.addWidget(buttons)

    # ── Row helpers ───────────────────────────────────────────────────────────

    def _ensure_blank_rows(self, minimum: int) -> None:
        """Guarantee at least *minimum* rows exist in the table."""
        while self._tbl.rowCount() < minimum:
            self._add_blank_row()

    def _add_blank_row(self) -> None:
        self._tbl.blockSignals(True)
        r = self._tbl.rowCount()
        self._tbl.insertRow(r)

        # Column 0 — account combo
        combo = QComboBox()
        combo.addItem("(select account)", "")
        for c in self._coa_list:
            combo.addItem(escape_ampersand_for_qt(c), c)
        combo.setEditable(True)
        combo.setToolTip("Chart-of-accounts category for this line.")
        combo.currentIndexChanged.connect(self._update_balance)
        self._tbl.setCellWidget(r, 0, combo)

        # Column 1 — Debit spin
        debit_spin = QDoubleSpinBox()
        debit_spin.setRange(0, 99_999_999.99)
        debit_spin.setDecimals(2)
        debit_spin.setSpecialValueText(" ")   # show blank when 0
        debit_spin.setToolTip("Debit amount for this line (0 = leave blank).")
        debit_spin.valueChanged.connect(self._update_balance)
        self._tbl.setCellWidget(r, 1, debit_spin)

        # Column 2 — Credit spin
        credit_spin = QDoubleSpinBox()
        credit_spin.setRange(0, 99_999_999.99)
        credit_spin.setDecimals(2)
        credit_spin.setSpecialValueText(" ")
        credit_spin.setToolTip("Credit amount for this line (0 = leave blank).")
        credit_spin.valueChanged.connect(self._update_balance)
        self._tbl.setCellWidget(r, 2, credit_spin)

        # Column 3 — Description
        self._tbl.setItem(r, 3, QTableWidgetItem(""))

        self._tbl.blockSignals(False)

    def _on_cell_changed(self, row: int, col: int) -> None:
        self._update_balance()

    def _update_balance(self) -> None:
        total_d = 0.0
        total_c = 0.0
        for r in range(self._tbl.rowCount()):
            d_w = self._tbl.cellWidget(r, 1)
            c_w = self._tbl.cellWidget(r, 2)
            if d_w:
                total_d += d_w.value()
            if c_w:
                total_c += c_w.value()
        diff = round(total_d - total_c, 2)
        color = "#98C379" if abs(diff) < 0.005 else "#E06C75"
        self._lbl_balance.setText(
            f"Debits: ${total_d:,.2f}   Credits: ${total_c:,.2f}   "
            f"Difference: ${diff:,.2f}"
        )
        self._lbl_balance.setStyleSheet(f"color: {color}; font-size: 11px;")

    # ── Load existing entry ───────────────────────────────────────────────────

    def _load_entry(self, entry_id: int) -> None:
        entry = self._gl.get_journal_entry(entry_id)
        if entry is None:
            return
        d = dict(entry)

        # Date
        raw = (d.get("entry_date") or "").strip()
        if raw:
            parts = raw.split("-")
            if len(parts) == 3:
                try:
                    self._date_edit.setDate(QDate(int(parts[0]), int(parts[1]), int(parts[2])))
                except Exception:
                    pass

        # Memo
        self._memo_edit.setText(d.get("memo") or "")

        # Lines
        lines = self._gl.get_entry_lines(entry_id)
        needed = max(len(lines), _MIN_LINES)
        while self._tbl.rowCount() < needed:
            self._add_blank_row()

        self._tbl.blockSignals(True)
        for r, ln in enumerate(lines):
            ln = dict(ln)
            # Account
            combo = self._tbl.cellWidget(r, 0)
            if combo:
                acct = (ln.get("account") or "").strip()
                ix = combo.findData(acct)
                if ix >= 0:
                    combo.setCurrentIndex(ix)
                elif acct:
                    combo.setCurrentText(escape_ampersand_for_qt(acct))
            # Debit
            d_w = self._tbl.cellWidget(r, 1)
            if d_w:
                d_w.setValue(float(ln.get("debit") or 0))
            # Credit
            c_w = self._tbl.cellWidget(r, 2)
            if c_w:
                c_w.setValue(float(ln.get("credit") or 0))
            # Description
            desc_item = self._tbl.item(r, 3)
            if desc_item:
                desc_item.setText(ln.get("description") or "")
        self._tbl.blockSignals(False)
        self._update_balance()

    # ── Collect & save ────────────────────────────────────────────────────────

    def _collect_lines(self) -> list[dict]:
        """Return non-empty lines from the table."""
        result = []
        for r in range(self._tbl.rowCount()):
            combo = self._tbl.cellWidget(r, 0)
            d_w   = self._tbl.cellWidget(r, 1)
            c_w   = self._tbl.cellWidget(r, 2)
            desc_item = self._tbl.item(r, 3)

            acct   = (combo.currentData() or combo.currentText()).strip() if combo else ""
            debit  = d_w.value() if d_w else 0.0
            credit = c_w.value() if c_w else 0.0
            desc   = desc_item.text().strip() if desc_item else ""

            if not acct or acct == "(select account)":
                continue
            if debit == 0.0 and credit == 0.0:
                continue
            result.append(dict(account=acct, debit=debit, credit=credit, description=desc))
        return result

    def _on_accept(self) -> None:
        qd = self._date_edit.date()
        entry_date = f"{qd.year():04d}-{qd.month():02d}-{qd.day():02d}"
        memo = self._memo_edit.text().strip()
        lines = self._collect_lines()

        if not lines:
            message_box_warning_ok(
                self, "No lines",
                "Enter at least one account line with a non-zero amount.",
                ok_tip="Close; fill in account, debit or credit.",
            )
            return

        try:
            if self._is_new:
                self._gl.create_journal_entry(
                    entry_date=entry_date,
                    lines=lines,
                    memo=memo,
                    source="manual",
                )
            else:
                self._gl.update_journal_entry(
                    self._entry_id,
                    entry_date=entry_date,
                    memo=memo,
                    lines=lines,
                )
        except ValueError as exc:
            message_box_warning_ok(
                self, "Cannot save",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; adjust amounts until Debits = Credits.",
            )
            return

        self.accept()
