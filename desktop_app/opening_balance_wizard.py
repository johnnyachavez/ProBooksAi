"""
desktop_app.opening_balance_wizard
====================================
Opening Balance Wizard — set a historical cut-off date and enter opening
balances for each COA account.  Posts a single balanced journal entry
(debits on asset/expense accounts, credits on liability/equity/income)
so the balance sheet reflects the correct starting position.

Typical use:
  - User has 3 years of old data they don't want to import line-by-line.
  - They pick a cut-off date (e.g. Jan 1 of current year).
  - They enter each account's balance as of that date.
  - A single "Opening Balance" journal entry is posted.
  - The register starts fresh from that date with correct account balances.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QDate

from probooksai.asset_register import AssetRegister
from probooksai.gl import GLDatabase
from desktop_app.qt_mnemonic import message_box_information_ok, message_box_warning_ok
from desktop_app.theme import (
    WORKFLOW_ALT_ROW,
    WORKFLOW_CAPTION,
    WORKFLOW_GRID,
    WORKFLOW_HEADER_BG,
    WORKFLOW_INPUT_BG,
    WORKFLOW_PAGE_BG,
    WORKFLOW_PANEL_BG,
    WORKFLOW_TEXT,
)

_ACCOUNT_TYPE_NORMAL_BALANCE = {
    # Assets and expenses have a debit normal balance (opening balance → debit)
    "Asset": "debit",
    "Current Asset": "debit",
    "Fixed Asset": "debit",
    "Other Asset": "debit",
    "Expense": "debit",
    "Cost of Goods Sold": "debit",
    # Liabilities, equity, income have a credit normal balance
    "Liability": "credit",
    "Current Liability": "credit",
    "Long-term Liability": "credit",
    "Equity": "credit",
    "Income": "credit",
    "Revenue": "credit",
    "Other Income": "credit",
}

_RETAINED_EARNINGS = "Retained Earnings / Opening Balance Equity"


def _normal_balance(account_type: str) -> str:
    """Return 'debit' or 'credit' for the given account type string."""
    for key, side in _ACCOUNT_TYPE_NORMAL_BALANCE.items():
        if key.lower() in (account_type or "").lower():
            return side
    return "debit"  # default to debit (asset) when type is unknown


# ---------------------------------------------------------------------------
# Opening Balance Wizard Dialog
# ---------------------------------------------------------------------------

class OpeningBalanceWizard(QDialog):
    """
    Two-step wizard:
      Step 1 — Choose cut-off date
      Step 2 — Enter opening balance for each COA account, review & post
    """

    def __init__(self, conn, coa_entries: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Opening Balance Wizard")
        self.setMinimumSize(640, 480)
        self._conn = conn
        self._coa_entries = coa_entries  # list of COAEntry or dicts with name/account_type
        self._gl = GLDatabase(conn)
        self._settings = AssetRegister(conn)  # re-use company_settings table
        self._build_ui()

    def _fresh_coa_entries(self) -> list:
        """Query COA accounts fresh from the DB (always up to date, bypasses stale passed-in list)."""
        try:
            from probooksai.coa_db import COADatabase
            coa_db = COADatabase(self._conn)
            rows = coa_db.list_accounts()
            if rows:
                return rows
        except Exception:
            pass
        return self._coa_entries  # fall back to whatever was passed in

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Title
        self._lbl_title = QLabel("Step 1 of 2 — Choose a cut-off date")
        self._lbl_title.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {WORKFLOW_TEXT};"
        )
        layout.addWidget(self._lbl_title)

        self._lbl_sub = QLabel(
            "The cut-off date is the point where this register begins. "
            "Balances as of this date are entered as opening entries; "
            "you don't need historical transaction lines before it."
        )
        self._lbl_sub.setWordWrap(True)
        self._lbl_sub.setStyleSheet(f"color: {WORKFLOW_CAPTION}; font-size: 11px;")
        layout.addWidget(self._lbl_sub)

        # Stacked pages
        self._stack = QStackedWidget()
        layout.addWidget(self._stack, 1)

        # Page 1 — date picker
        p1 = QWidget()
        p1_lay = QVBoxLayout(p1)
        p1_lay.setContentsMargins(20, 20, 20, 20)
        p1_date_row = QHBoxLayout()
        p1_date_row.addWidget(QLabel("Cut-off date:"))
        self._date_edit = QDateEdit()
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDate(QDate(date.today().year, 1, 1))
        self._date_edit.setDisplayFormat("MM/dd/yyyy")
        self._date_edit.setToolTip(
            "All opening balances will be posted as of this date. "
            "The register history starts here."
        )
        p1_date_row.addWidget(self._date_edit)
        p1_date_row.addStretch(1)
        p1_lay.addLayout(p1_date_row)
        p1_lay.addStretch(1)
        self._stack.addWidget(p1)

        # Page 2 — account balances table
        p2 = QWidget()
        p2_lay = QVBoxLayout(p2)
        p2_lay.setContentsMargins(0, 0, 0, 0)
        p2_lay.addWidget(
            QLabel("Enter the balance for each account as of the cut-off date. "
                   "Leave blank / zero if not applicable.")
        )
        self._tbl = QTableWidget(0, 3)
        self._tbl.setHorizontalHeaderLabels(["Account", "Type", "Opening Balance ($)"])
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setAlternatingRowColors(True)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hh = self._tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._tbl.setStyleSheet(
            f"QTableWidget {{ background: {WORKFLOW_PANEL_BG}; "
            f"alternate-background-color: {WORKFLOW_ALT_ROW}; color: {WORKFLOW_TEXT}; "
            f"gridline-color: {WORKFLOW_GRID}; border: 1px solid {WORKFLOW_GRID}; }}"
            f"QHeaderView::section {{ background: {WORKFLOW_HEADER_BG}; color: {WORKFLOW_TEXT}; "
            f"padding: 6px; border: 1px solid {WORKFLOW_GRID}; font-weight: 600; }}"
        )
        p2_lay.addWidget(self._tbl, 1)

        self._lbl_equity_note = QLabel("")
        self._lbl_equity_note.setStyleSheet(f"color: {WORKFLOW_CAPTION}; font-size: 11px;")
        self._lbl_equity_note.setWordWrap(True)
        p2_lay.addWidget(self._lbl_equity_note)
        self._stack.addWidget(p2)

        # Plain QPushButton nav row — avoids QDialogButtonBox AcceptRole auto-connecting
        # to QDialog.accept() which swallowed Next → clicks in PySide6.
        btn_row = QHBoxLayout()
        self._btn_back = QPushButton("← Back")
        self._btn_back.setVisible(False)
        self._btn_next = QPushButton("Next →")
        self._btn_post = QPushButton("Post Opening Balances")
        self._btn_post.setVisible(False)
        btn_cancel = QPushButton("Cancel")

        btn_row.addWidget(self._btn_back)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(self._btn_post)
        btn_row.addWidget(self._btn_next)
        layout.addLayout(btn_row)

        self._btn_back.clicked.connect(self._go_back)
        self._btn_next.clicked.connect(self._go_next)
        self._btn_post.clicked.connect(self._post)
        btn_cancel.clicked.connect(self.reject)

    # -- navigation ----------------------------------------------------------

    def _go_next(self) -> None:
        # Always pull fresh COA rows from the DB so we don't depend on stale passed-in list
        self._coa_entries = self._fresh_coa_entries()
        try:
            self._populate_accounts_table()
        except Exception as exc:
            message_box_warning_ok(self, "Could not load accounts", str(exc))
            return
        if not self._spins:
            message_box_warning_ok(
                self, "No accounts found",
                "No Chart of Accounts entries were found.\n\n"
                "Make sure your company file is set up and COA is seeded (More → Chart of Accounts)."
            )
            return
        self._stack.setCurrentIndex(1)
        self._lbl_title.setText("Step 2 of 2 — Enter opening balances")
        self._lbl_sub.setText(
            "Enter each account's balance as of the cut-off date. "
            f"The difference will be posted to '{_RETAINED_EARNINGS}' automatically."
        )
        self._btn_next.setVisible(False)
        self._btn_back.setVisible(True)
        self._btn_post.setVisible(True)

    def _go_back(self) -> None:
        self._stack.setCurrentIndex(0)
        self._lbl_title.setText("Step 1 of 2 — Choose a cut-off date")
        self._lbl_sub.setText(
            "The cut-off date is the point where this register begins. "
            "Balances as of this date are entered as opening entries; "
            "you don't need historical transaction lines before it."
        )
        self._btn_next.setVisible(True)
        self._btn_back.setVisible(False)
        self._btn_post.setVisible(False)

    # -- account table -------------------------------------------------------

    @staticmethod
    def _entry_name_type(entry) -> tuple[str, str]:
        """Extract (display_name, account_type) from any entry format.

        Handles:
        - sqlite3.Row  → columns account_name / account_number / account_type
        - COAEntry namedtuple → .display property, .account_type attr
        - plain dict   → 'display' or 'account_name' key, 'account_type' key
        """
        # sqlite3.Row — has keys() method and subscript access
        try:
            keys = entry.keys()
            acct_name = entry["account_name"] if "account_name" in keys else ""
            acct_num  = entry["account_number"] if "account_number" in keys else ""
            display   = f"{acct_num} {acct_name}".strip() if acct_num else acct_name
            atype     = entry["account_type"] if "account_type" in keys else ""
            return str(display), str(atype)
        except (TypeError, AttributeError):
            pass
        # COAEntry namedtuple / object with .display
        display = getattr(entry, "display", None)
        atype   = getattr(entry, "account_type", None)
        if display is not None:
            return str(display), str(atype or "")
        # Plain dict fallback
        try:
            display = entry.get("display") or entry.get("account_name") or ""
            atype   = entry.get("account_type") or ""
            return str(display), str(atype)
        except AttributeError:
            return str(entry), ""

    def _populate_accounts_table(self) -> None:
        self._tbl.setRowCount(0)
        self._spins: list[QDoubleSpinBox] = []

        # Pre-load existing GL balances so the user sees current figures
        raw_balances: dict[str, tuple[float, float]] = {}
        try:
            for row in self._gl.trial_balance():
                acct = row.get("account", "")
                td   = float(row.get("total_debit", 0.0) or 0.0)
                tc   = float(row.get("total_credit", 0.0) or 0.0)
                raw_balances[acct] = (td, tc)
        except Exception:
            pass  # if GL is empty or unavailable, just leave spinners at 0

        for entry in self._coa_entries:
            name, atype = self._entry_name_type(entry)
            if not name:
                continue
            r = self._tbl.rowCount()
            self._tbl.insertRow(r)
            n_it = QTableWidgetItem(name)
            n_it.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            t_it = QTableWidgetItem(atype)
            t_it.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            spin = QDoubleSpinBox()
            spin.setMaximum(999_999_999.0)
            spin.setDecimals(2)

            # Pre-fill from GL if a balance exists for this account
            prefill = 0.0
            if name in raw_balances:
                td, tc = raw_balances[name]
                if _normal_balance(atype) == "debit":
                    prefill = max(0.0, round(td - tc, 2))
                else:
                    prefill = max(0.0, round(tc - td, 2))
            spin.setValue(prefill)

            spin.setStyleSheet(f"QDoubleSpinBox {{ background: {WORKFLOW_INPUT_BG}; color: {WORKFLOW_TEXT}; }}")
            self._tbl.setItem(r, 0, n_it)
            self._tbl.setItem(r, 1, t_it)
            self._tbl.setCellWidget(r, 2, spin)
            self._spins.append(spin)
        self._update_equity_note()
        for spin in self._spins:
            spin.valueChanged.connect(self._update_equity_note)

    def _update_equity_note(self) -> None:
        total_debit = 0.0
        total_credit = 0.0
        for i, spin in enumerate(self._spins):
            val = spin.value()
            if val == 0:
                continue
            it = self._tbl.item(i, 1)
            atype = it.text() if it else ""
            if _normal_balance(atype) == "debit":
                total_debit += val
            else:
                total_credit += val
        diff = total_debit - total_credit
        if abs(diff) < 0.01:
            self._lbl_equity_note.setText("Entry is balanced. Ready to post.")
        elif diff > 0:
            self._lbl_equity_note.setText(
                f"Debit total exceeds credits by ${diff:,.2f}. "
                f"A credit of ${diff:,.2f} will be added to '{_RETAINED_EARNINGS}'."
            )
        else:
            self._lbl_equity_note.setText(
                f"Credit total exceeds debits by ${abs(diff):,.2f}. "
                f"A debit of ${abs(diff):,.2f} will be added to '{_RETAINED_EARNINGS}'."
            )

    # -- post ----------------------------------------------------------------

    def _post(self) -> None:
        qd = self._date_edit.date()
        cut_off = f"{qd.year():04d}-{qd.month():02d}-{qd.day():02d}"

        lines: list[dict] = []
        for i, spin in enumerate(self._spins):
            val = round(spin.value(), 2)
            if val == 0:
                continue
            it_name = self._tbl.item(i, 0)
            it_type = self._tbl.item(i, 1)
            account = it_name.text() if it_name else ""
            atype = it_type.text() if it_type else ""
            side = _normal_balance(atype)
            lines.append({
                "account": account,
                "debit": val if side == "debit" else 0.0,
                "credit": val if side == "credit" else 0.0,
                "description": f"Opening balance as of {cut_off}",
            })

        if not lines:
            message_box_warning_ok(
                self, "No balances", "Enter at least one non-zero opening balance."
            )
            return

        # Balance with Retained Earnings
        total_debit = sum(ln["debit"] for ln in lines)
        total_credit = sum(ln["credit"] for ln in lines)
        diff = round(total_debit - total_credit, 2)
        if abs(diff) >= 0.01:
            if diff > 0:
                lines.append({"account": _RETAINED_EARNINGS, "debit": 0.0,
                               "credit": diff, "description": "Balancing equity offset"})
            else:
                lines.append({"account": _RETAINED_EARNINGS, "debit": abs(diff),
                               "credit": 0.0, "description": "Balancing equity offset"})

        try:
            entry_id = self._gl.create_journal_entry(
                entry_date=cut_off,
                lines=lines,
                memo=f"Opening balances as of {cut_off}",
                source="opening_balance",
            )
            self._settings.set_setting("cutoff_date", cut_off)
            self._settings.set_setting("opening_balance_entry_id", str(entry_id))
        except Exception as exc:
            message_box_warning_ok(self, "Post failed", str(exc))
            return

        message_box_information_ok(
            self,
            "Opening Balances Posted",
            f"Journal entry #{entry_id} posted as of {cut_off}.\n"
            f"{len(lines)} lines including the equity offset.\n\n"
            f"Cut-off date saved. The register history starts from {cut_off}.",
            ok_tip="Close; review the entry in the Journal tab.",
        )
        self.accept()
