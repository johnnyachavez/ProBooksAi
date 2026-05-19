"""
desktop_app.bank_statement_review_dialog
==========================================
Review-and-filter dialog for importing a bank statement PDF.

Workflow
--------
1. The caller parses the PDF with :func:`probooksai.statement_section_parser.parse_section_statement`
   and runs :func:`~probooksai.statement_section_parser.mark_duplicates`.
2. Open :class:`BankStatementReviewDialog` with the entry list.
3. The user adjusts which transaction types to include, unchecks specific rows,
   then clicks **Import Selected**.
4. The dialog returns ``QDialog.Accepted``; the caller reads ``.selected_entries``
   for the final list to import.

Filter defaults (per the business rule: deposits and manual-post items stay out)
-------
  ✓  ATM / Debit Card   — recurring, CC, misc debits
  ✓  Electronic (non-ACH)
  ✓  Fees / Service Charges
  ✗  Deposits           — must be entered manually (matched to invoices)
  ✗  Checks             — must be manually posted against AP
  ✗  ACH / Online Payments — matched to bills / vendor payments manually
  ✗  Already in Register  — deduplication
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from probooksai.statement_section_parser import StatementEntry, TXN_TYPE_LABELS
from desktop_app.qt_mnemonic import qdialog_ok_button, tip_qdialog_button_box

# ---------------------------------------------------------------------------
# Row colour scheme
# ---------------------------------------------------------------------------
_COL_NEW        = QColor("#1B3A2A")   # dark green — will be imported
_COL_DUPLICATE  = QColor("#2A2A1B")   # dark yellow — already in register
_COL_FILTERED   = QColor("#1E1E2A")   # dark blue-grey — excluded by filter
_COL_ACH        = QColor("#2A1B1B")   # dark red — ACH/online excluded

_FG_NEW         = QColor("#98C379")
_FG_DUPLICATE   = QColor("#E5C07B")
_FG_FILTERED    = QColor("#5C6370")
_FG_ACH         = QColor("#E06C75")

_COL_HDR = {
    "atm_debit":   QColor("#1B3A2A"),
    "electronic":  QColor("#1B2A3A"),
    "fee":         QColor("#2A1B3A"),
    "deposit":     QColor("#2A2A2A"),
    "check":       QColor("#2A2A2A"),
}

# Table columns
_C_CHK  = 0
_C_DATE = 1
_C_TYPE = 2
_C_DESC = 3
_C_AMT  = 4
_C_STAT = 5
_HEADERS = ["✓", "Date", "Type", "Description", "Amount", "Status"]


class BankStatementReviewDialog(QDialog):
    """
    Show parsed bank statement entries and let the user pick what to import.

    Parameters
    ----------
    entries:
        Parsed :class:`~probooksai.statement_section_parser.StatementEntry` list.
        ``is_duplicate`` must already be set by the caller.
    statement_label:
        Short description shown in the title, e.g. ``"January 2022 – CHASE BANK"``.
    parent:
        Parent widget.
    """

    def __init__(
        self,
        entries: list[StatementEntry],
        *,
        statement_label: str = "Bank Statement",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._all_entries = entries
        self._statement_label = statement_label
        self.selected_entries: list[StatementEntry] = []

        self.setWindowTitle(f"Import Review — {statement_label}")
        self.setMinimumSize(1000, 640)
        self._build_ui()
        self._apply_filters()

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ── Header ───────────────────────────────────────────────────────
        hdr = QLabel(
            f"<b>Bank Statement Import Review</b> &nbsp;·&nbsp; {self._statement_label}"
        )
        hdr.setTextFormat(Qt.TextFormat.RichText)
        hdr.setStyleSheet("font-size: 13px; padding: 4px 0;")
        root.addWidget(hdr)

        rule = QFrame()
        rule.setFrameShape(QFrame.Shape.HLine)
        rule.setStyleSheet("color: #3A3A4A;")
        root.addWidget(rule)

        # ── Filter bar ───────────────────────────────────────────────────
        filter_group = QGroupBox("Include in import")
        filter_group.setToolTip(
            "Check the transaction types you want to import. "
            "Deposits and checks are off by default — enter those manually so they can be "
            "matched to invoices and accounts payable."
        )
        filter_row = QHBoxLayout(filter_group)
        filter_row.setSpacing(20)

        self._cb_atm      = self._filter_cb("ATM / Debit Card",     True,  "Recurring charges, point-of-sale, fuel, subscriptions.")
        self._cb_elec     = self._filter_cb("Electronic (non-ACH)", True,  "Wire transfers and electronic debits that are NOT online bill-pay or ACH.")
        self._cb_fee      = self._filter_cb("Fees & Charges",       True,  "Bank service fees, monthly charges, wire fees.")
        self._cb_deposit  = self._filter_cb("Deposits",             False, "Deposits are entered manually and matched to invoices / received payments.")
        self._cb_check    = self._filter_cb("Checks",               False, "Checks are posted manually against accounts payable.")
        self._cb_ach      = self._filter_cb("ACH / Online Payments",False, "Online bill-pay and ACH transfers — post manually against vendor bills.")
        self._cb_dupes    = self._filter_cb("Already in Register",  False, "Entries that appear to already be in the bank register (duplicates).")

        for cb in (self._cb_atm, self._cb_elec, self._cb_fee,
                   self._cb_deposit, self._cb_check, self._cb_ach, self._cb_dupes):
            filter_row.addWidget(cb)
            cb.stateChanged.connect(self._apply_filters)

        filter_row.addStretch()
        root.addWidget(filter_group)

        # ── Quick-action buttons ─────────────────────────────────────────
        qa_row = QHBoxLayout()
        btn_all  = QPushButton("☑ Select all visible")
        btn_none = QPushButton("☐ Deselect all")
        btn_all.setToolTip("Check every currently visible (non-grey) row.")
        btn_none.setToolTip("Uncheck all rows.")
        btn_all.clicked.connect(self._select_all_visible)
        btn_none.clicked.connect(self._deselect_all)
        qa_row.addWidget(btn_all)
        qa_row.addWidget(btn_none)
        qa_row.addStretch()
        self._lbl_summary = QLabel()
        self._lbl_summary.setStyleSheet("color: #A0A0B0; font-size: 11px;")
        qa_row.addWidget(self._lbl_summary)
        root.addLayout(qa_row)

        # ── Transaction table ────────────────────────────────────────────
        self._table = QTableWidget(0, len(_HEADERS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        hdr_view = self._table.horizontalHeader()
        hdr_view.setSectionResizeMode(_C_CHK,  QHeaderView.ResizeMode.Fixed)
        hdr_view.setSectionResizeMode(_C_DATE, QHeaderView.ResizeMode.Fixed)
        hdr_view.setSectionResizeMode(_C_TYPE, QHeaderView.ResizeMode.Fixed)
        hdr_view.setSectionResizeMode(_C_DESC, QHeaderView.ResizeMode.Stretch)
        hdr_view.setSectionResizeMode(_C_AMT,  QHeaderView.ResizeMode.Fixed)
        hdr_view.setSectionResizeMode(_C_STAT, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(_C_CHK,  36)
        self._table.setColumnWidth(_C_DATE, 90)
        self._table.setColumnWidth(_C_TYPE, 140)
        self._table.setColumnWidth(_C_AMT,  90)
        self._table.setColumnWidth(_C_STAT, 120)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(False)
        self._table.setToolTip(
            "Rows highlighted green will be imported. "
            "Click the ✓ column or double-click a row to toggle. "
            "Greyed rows are filtered out by the checkboxes above."
        )
        self._table.itemDoubleClicked.connect(self._toggle_row)
        self._table.cellClicked.connect(self._on_cell_click)
        root.addWidget(self._table, stretch=1)

        # ── Legend ───────────────────────────────────────────────────────
        leg_row = QHBoxLayout()
        for colour, label in (
            (_FG_NEW,       "✓ Will import"),
            (_FG_DUPLICATE, "⚠ Duplicate (already in register)"),
            (_FG_ACH,       "✗ ACH / Online (filtered)"),
            (_FG_FILTERED,  "— Filtered out"),
        ):
            dot = QLabel("⬤")
            dot.setStyleSheet(f"color: {colour.name()}; font-size: 10px;")
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #808090; font-size: 10px;")
            leg_row.addWidget(dot)
            leg_row.addWidget(lbl)
            leg_row.addSpacing(12)
        leg_row.addStretch()
        root.addLayout(leg_row)

        # ── Dialog buttons ───────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._btn_ok = qdialog_ok_button(buttons)
        if self._btn_ok is not None:
            self._btn_ok.setText("Import Selected")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        tip_qdialog_button_box(
            buttons,
            ok="Import the checked transactions into the bank register.",
            cancel="Close without importing anything.",
        )
        root.addWidget(buttons)

    def _filter_cb(self, label: str, default: bool, tip: str) -> QCheckBox:
        cb = QCheckBox(label)
        cb.setChecked(default)
        cb.setToolTip(tip)
        return cb

    # ── Filter logic ───────────────────────────────────────────────────────

    def _type_visible(self, entry: StatementEntry) -> bool:
        """Return True if this entry passes the current filter settings."""
        if entry.is_duplicate and not self._cb_dupes.isChecked():
            return False
        t = entry.txn_type
        if t == "atm_debit"  and not self._cb_atm.isChecked():
            return False
        if t == "electronic":
            if entry.is_ach and not self._cb_ach.isChecked():
                return False
            if not entry.is_ach and not self._cb_elec.isChecked():
                return False
        if t == "fee"        and not self._cb_fee.isChecked():
            return False
        if t == "deposit"    and not self._cb_deposit.isChecked():
            return False
        if t == "check"      and not self._cb_check.isChecked():
            return False
        return True

    def _apply_filters(self) -> None:
        """Rebuild the table according to the current filter settings."""
        self._table.blockSignals(True)
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        for entry in self._all_entries:
            visible = self._type_visible(entry)
            self._add_row(entry, visible)

        self._table.setSortingEnabled(True)
        self._table.blockSignals(False)
        self._update_summary()

    def _add_row(self, entry: StatementEntry, visible: bool) -> None:
        r = self._table.rowCount()
        self._table.insertRow(r)

        # Checkbox column
        chk = QTableWidgetItem()
        chk.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
        # Check only if visible AND included by default (not duplicate, not ACH filtered)
        will_import = visible and entry.include and not entry.is_duplicate
        chk.setCheckState(Qt.CheckState.Checked if will_import else Qt.CheckState.Unchecked)
        chk.setData(Qt.ItemDataRole.UserRole, id(entry))   # link to entry object
        self._table.setItem(r, _C_CHK, chk)

        date_item  = QTableWidgetItem(entry.txn_date[5:] + "/" + entry.txn_date[:4] if entry.txn_date else "—")
        type_item  = QTableWidgetItem(entry.type_label)
        desc_item  = QTableWidgetItem(entry.description)
        amt_item   = QTableWidgetItem(entry.amount_display)
        amt_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        if entry.is_duplicate:
            status = "Duplicate"
        elif not visible:
            status = "Filtered"
        elif entry.is_ach:
            status = "ACH (filtered)"
        elif entry.txn_type == "deposit":
            status = "Deposit (filtered)"
        elif entry.txn_type == "check":
            status = "Check (filtered)"
        else:
            status = "New ✓" if will_import else "Unchecked"

        stat_item  = QTableWidgetItem(status)

        for item in (date_item, type_item, desc_item, amt_item, stat_item):
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

        # Colour coding
        if not visible or (not will_import and not entry.is_duplicate):
            bg = _COL_FILTERED
            fg = _FG_FILTERED
        elif entry.is_duplicate:
            bg = _COL_DUPLICATE
            fg = _FG_DUPLICATE
        elif entry.is_ach:
            bg = _COL_ACH
            fg = _FG_ACH
        elif will_import:
            bg = _COL_NEW
            fg = _FG_NEW
        else:
            bg = _COL_FILTERED
            fg = _FG_FILTERED

        for item in (chk, date_item, type_item, desc_item, amt_item, stat_item):
            item.setBackground(bg)
            item.setForeground(fg)

        self._table.setItem(r, _C_DATE, date_item)
        self._table.setItem(r, _C_TYPE, type_item)
        self._table.setItem(r, _C_DESC, desc_item)
        self._table.setItem(r, _C_AMT,  amt_item)
        self._table.setItem(r, _C_STAT, stat_item)
        self._table.setRowHeight(r, 24)

    # ── Row toggle ─────────────────────────────────────────────────────────

    def _on_cell_click(self, row: int, col: int) -> None:
        if col == _C_CHK:
            self._toggle_row_at(row)

    def _toggle_row(self, item: QTableWidgetItem) -> None:
        self._toggle_row_at(item.row())

    def _toggle_row_at(self, row: int) -> None:
        chk = self._table.item(row, _C_CHK)
        if chk is None:
            return
        new_state = (Qt.CheckState.Unchecked
                     if chk.checkState() == Qt.CheckState.Checked
                     else Qt.CheckState.Checked)
        chk.setCheckState(new_state)
        # Update status cell text
        stat = self._table.item(row, _C_STAT)
        if stat:
            stat.setText("New ✓" if new_state == Qt.CheckState.Checked else "Unchecked")
        self._update_summary()

    def _select_all_visible(self) -> None:
        for r in range(self._table.rowCount()):
            chk = self._table.item(r, _C_CHK)
            stat = self._table.item(r, _C_STAT)
            if chk and stat and "Filtered" not in stat.text() and "Duplicate" not in stat.text():
                chk.setCheckState(Qt.CheckState.Checked)
                stat.setText("New ✓")
        self._update_summary()

    def _deselect_all(self) -> None:
        for r in range(self._table.rowCount()):
            chk = self._table.item(r, _C_CHK)
            stat = self._table.item(r, _C_STAT)
            if chk:
                chk.setCheckState(Qt.CheckState.Unchecked)
            if stat and stat.text() == "New ✓":
                stat.setText("Unchecked")
        self._update_summary()

    # ── Summary ────────────────────────────────────────────────────────────

    def _update_summary(self) -> None:
        total = self._table.rowCount()
        checked = sum(
            1 for r in range(total)
            if (it := self._table.item(r, _C_CHK)) and it.checkState() == Qt.CheckState.Checked
        )
        dupes = sum(
            1 for e in self._all_entries if e.is_duplicate
        )
        filtered = sum(
            1 for e in self._all_entries if not self._type_visible(e)
        )
        self._lbl_summary.setText(
            f"{checked} selected to import  •  {dupes} duplicate(s)  •  {filtered} filtered out  •  {total} shown"
        )
        if self._btn_ok is not None:
            self._btn_ok.setText(f"Import Selected ({checked})")
            self._btn_ok.setEnabled(checked > 0)

    # ── Accept / collect ───────────────────────────────────────────────────

    def _on_accept(self) -> None:
        """Collect checked entries, map back to StatementEntry objects."""
        entry_index = {id(e): e for e in self._all_entries}
        result: list[StatementEntry] = []
        for r in range(self._table.rowCount()):
            chk = self._table.item(r, _C_CHK)
            if chk and chk.checkState() == Qt.CheckState.Checked:
                eid = chk.data(Qt.ItemDataRole.UserRole)
                entry = entry_index.get(eid)
                if entry:
                    result.append(entry)
        self.selected_entries = result
        self.accept()


# ---------------------------------------------------------------------------
# Convenience launcher
# ---------------------------------------------------------------------------

def run_statement_review(
    pdf_path: str,
    db,               # BankDatabase
    account_id: int,
    *,
    default_year: Optional[int] = None,
    parent: Optional[QWidget] = None,
) -> list[StatementEntry]:
    """
    Full pipeline: extract PDF text → parse sections → mark duplicates → show dialog.

    Returns the list of :class:`StatementEntry` objects the user selected,
    or an empty list if cancelled.

    Parameters
    ----------
    pdf_path:
        Path to the bank statement PDF.
    db:
        :class:`~probooksai.bank_import.BankDatabase` instance.
    account_id:
        Bank account id to check for duplicates and import into.
    default_year:
        Year override; if *None*, inferred from the filename (``YYYYMMDD…``)
        then from the PDF text, then defaults to the current year.
    parent:
        Parent widget for the dialog.
    """
    import os, re as _re
    from probooksai.statement_pdf import extract_text_from_pdf
    from probooksai.statement_section_parser import (
        parse_section_statement,
        mark_duplicates,
    )

    # ── Year inference ────────────────────────────────────────────────────
    if default_year is None:
        fname = os.path.basename(pdf_path)
        m = _re.match(r"(\d{4})", fname)
        default_year = int(m.group(1)) if m else __import__("datetime").date.today().year

    # ── Extract + parse ───────────────────────────────────────────────────
    text = extract_text_from_pdf(pdf_path)
    entries = parse_section_statement(text, default_year=default_year)
    mark_duplicates(entries, db._conn, account_id)

    # ── Build label from PDF name / statement period ──────────────────────
    fname_base = os.path.splitext(os.path.basename(pdf_path))[0]
    # Try to extract readable label from filename like 20220131-statements-8252-
    m_date = _re.match(r"(\d{4})(\d{2})(\d{2})", fname_base)
    if m_date:
        import calendar
        y, mo = int(m_date.group(1)), int(m_date.group(2))
        label = f"{calendar.month_name[mo]} {y}"
    else:
        label = fname_base[:40]

    acct_row = db.get_bank_account(account_id)
    if acct_row:
        label = f"{label} — {dict(acct_row).get('name', '')}"

    # ── Show dialog ───────────────────────────────────────────────────────
    dlg = BankStatementReviewDialog(entries, statement_label=label, parent=parent)
    if dlg.exec() != dlg.DialogCode.Accepted:
        return []
    return dlg.selected_entries
