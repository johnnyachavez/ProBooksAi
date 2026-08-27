"""
desktop_app.coa_tab
====================
PySide6 widget for viewing and editing the Chart of Accounts.

Issue #41 – COA editor (minimal): UI to view/add/edit/deactivate COA accounts.
COA entries populate category dropdowns throughout the app.

QuickBooks Pro Desktop Chart of Accounts layout (search row, Name / TYPE /
BALANCE TOTAL / ATTACH, sub-account indent, inactive X and diamond markers).
Double-click a row opens that account's two-line register (same checkbook as
Use Register). Edit remains on the toolbar / context menu.

**F5** (when this tab or its children have focus) reloads the grid from the database (same as after
add/edit/deactivate; respects **Show inactive**). **Help → More tab shortcuts (F5)…**; grid **right-click**
**Keyboard shortcuts…** / **Copy** / **View change history** use **QAction** **setToolTip** (including empty area). The grid has a hover **tooltip**.
The **COATab** root **QWidget** has a hover hint. The account **count** line and footer **F5** hint use **setToolTip** on hover.
Deactivate confirm **Yes**/**No** use **tip_message_box_buttons**.

Widgets
-------
  COATab          – top-level QWidget (intended as a tab in MainWindow)
  AddEditCOADialog – dialog for creating or editing a single COA account (window + field + **Save**/**Cancel** via ``tip_qdialog_button_box``)
"""

from __future__ import annotations

import sqlite3
from functools import partial
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QPalette, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from probooksai.coa_db import (
    COADatabase,
    COA_TYPE_UI_LABELS,
    infer_coa_normal_balance,
)
from probooksai.gl import GLDatabase

from desktop_app.audit_dialog import show_entity_audit_history
from desktop_app.qt_combo_ids import coerce_combo_int_id
from desktop_app.more_main_tabs_shortcuts import (
    show_more_main_tabs_keyboard_shortcuts_dialog,
)
from desktop_app.qt_mnemonic import (
    escape_ampersand_for_qt,
    message_box_critical_ok,
    message_box_warning_ok,
    tip_message_box_buttons,
    tip_qdialog_button_box,
)
from desktop_app.table_clipboard import (
    CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX,
    QTABLE_PLAIN_TEXT_ROLE,
    VIEW_BANK_REGISTER_KEYS_TOOLTIP,
    copy_table_row_as_tsv,
    plain_display_table_item,
)


# Light canvas like Create Invoices / Vendor Center — not a navy photocopy, not QBO.
_COA_CANVAS = "#E8ECF1"
_COA_PAPER = "#FFFFFF"
_COA_PANEL = "#F4F7FA"
_COA_STRIPE = "#D0E6F4"
_COA_CAPTION = "#4A5560"
_COA_GRID = "#C0C8D0"
_COA_HEADER = "#D8DEE6"
_COA_TEXT = "#1A1A1A"
_COA_ACCENT = "#2563A8"
_COA_SELECT = "#2E7D32"
_COA_SELECT_FG = "#FFFFFF"
_STRIP_BTN_OUTLINE = "#B4BCC6"
_TOP_STRIP_RADIUS_PX = 4
_TOP_STRIP_BODY_FONT_PX = 12
_NAME_INDENT_PX = 18

_COL_MARK_X = 0
_COL_MARK_SUB = 1
_COL_NAME = 2
_COL_TYPE = 3
_COL_BAL = 4
_COL_ATTACH = 5

_ROLE_ACCOUNT_ID = Qt.ItemDataRole.UserRole
_ROLE_DEPTH = Qt.ItemDataRole.UserRole + 1
_ROLE_NUMBER = Qt.ItemDataRole.UserRole + 2
_ROLE_ACTIVE = Qt.ItemDataRole.UserRole + 3

_TYPE_LABELS = dict(COA_TYPE_UI_LABELS)


def qb_coa_type_label(row) -> str:
    """QuickBooks Pro-style TYPE column from stored type / sub-type / name."""
    name = str(row["account_name"] or "").strip()
    nlow = name.lower()
    sub = str(row["sub_type"] or "").strip().lower()
    atype = str(row["account_type"] or "").strip().lower()
    if "accounts receivable" in nlow:
        return "Accounts Receivable"
    if "accounts payable" in nlow:
        return "Accounts Payable"
    if "undeposited" in nlow:
        return "Other Current Asset"
    if atype == "bank" or "checking" in nlow or "savings" in nlow or nlow.startswith("cash"):
        return "Bank"
    if atype == "credit_card" or "credit card" in sub:
        return "Credit Card"
    if atype == "fixed_asset" or "fixed" in sub:
        return "Fixed Asset"
    if atype == "other_asset" or "other asset" in sub:
        return "Other Asset"
    if atype in ("current_asset", "asset") or "current asset" in sub:
        return "Other Current Asset"
    if atype in ("long_term_liability",) or "long-term" in sub or "long term" in sub:
        return "Long Term Liability"
    if atype in ("current_liability", "liability", "loan") or "current liability" in sub:
        return "Other Current Liability"
    if atype in ("income", "operating_revenue") or "revenue" in sub:
        return "Income"
    if atype == "expense" or "expense" in sub or "cogs" in sub:
        return "Expense"
    if atype in ("equity", "paid_in_capital", "retained_earnings", "owners_draw"):
        return "Equity"
    return _TYPE_LABELS.get(atype, atype.replace("_", " ").title() or "Other")


def is_bank_like_coa(row) -> bool:
    """True when this chart row should open a bank (checkbook) register."""
    return qb_coa_type_label(row) in {"Bank", "Credit Card"}


def ordered_coa_rows(rows: list) -> list[tuple[object, int]]:
    """Return ``(row, depth)`` with children indented under their parent."""
    by_id: dict[int, object] = {}
    for row in rows:
        aid = coerce_combo_int_id(row["id"])
        if aid is not None:
            by_id[aid] = row
    children: dict[int, list] = {}
    roots: list = []
    for row in rows:
        aid = coerce_combo_int_id(row["id"])
        if aid is None:
            continue
        pid = coerce_combo_int_id(row["parent_id"]) if "parent_id" in row.keys() else None
        if pid is not None and pid in by_id and pid != aid:
            children.setdefault(pid, []).append(row)
        else:
            roots.append(row)

    def _key(r) -> tuple:
        return (
            str(r["account_number"] or "").strip(),
            str(r["account_name"] or "").strip().lower(),
        )

    out: list[tuple[object, int]] = []

    def _walk(nodes: list, depth: int) -> None:
        for node in sorted(nodes, key=_key):
            out.append((node, depth))
            nid = coerce_combo_int_id(node["id"])
            if nid is not None:
                _walk(children.get(nid, []), depth + 1)

    _walk(roots, 0)
    return out


def _action_button_qss(*, primary: bool = False) -> str:
    r = _TOP_STRIP_RADIUS_PX
    if primary:
        return (
            f"QPushButton {{ background-color: {_COA_ACCENT}; border: 1px solid {_COA_ACCENT}; "
            f"border-radius: {r}px; color: #FFFFFF; "
            f"font-size: {_TOP_STRIP_BODY_FONT_PX}px; padding: 0 14px; font-weight: 600; }}"
            f"QPushButton:hover {{ background-color: #1D4F8C; }}"
            f"QPushButton:pressed {{ background-color: #163E6E; }}"
            f"QPushButton:disabled {{ color: #D7E3F0; background-color: #8AA7C7; }}"
        )
    return (
        f"QPushButton {{ background-color: #F7F8FA; border: 1px solid {_STRIP_BTN_OUTLINE}; "
        f"border-radius: {r}px; color: {_COA_TEXT}; "
        f"font-size: {_TOP_STRIP_BODY_FONT_PX}px; padding: 0 12px; }}"
        f"QPushButton:hover {{ background-color: #E4EEF7; }}"
        f"QPushButton:pressed {{ background-color: #C9D8EC; }}"
        f"QPushButton:disabled {{ color: #8A94A0; }}"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _CoaAccountNumberTableItem(QTableWidgetItem):
    """# column: escaped display, plain copy role, numeric sort when number is all digits."""

    def __init__(self, account_number: str, account_id: int) -> None:
        raw = str(account_number or "")
        super().__init__(escape_ampersand_for_qt(raw))
        self.setData(Qt.ItemDataRole.UserRole, int(account_id))
        self.setData(QTABLE_PLAIN_TEXT_ROLE, raw)
        sk = raw.strip()
        self._int_key: int | None = int(sk) if sk.isdigit() else None

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, _CoaAccountNumberTableItem):
            if self._int_key is not None and other._int_key is not None:
                return self._int_key < other._int_key
            a = (self.data(QTABLE_PLAIN_TEXT_ROLE) or "").strip().lower()
            b = (other.data(QTABLE_PLAIN_TEXT_ROLE) or "").strip().lower()
            return a < b
        return super().__lt__(other)


# ===========================================================================
# AddEditCOADialog
# ===========================================================================

class AddEditCOADialog(QDialog):
    """Dialog for adding or editing a single COA account."""

    def __init__(self, db: COADatabase, account_id: Optional[int] = None, parent=None):
        super().__init__(parent)
        self._db = db
        self._account_id = account_id
        self.setWindowTitle("Edit Account" if account_id else "Add Account")
        self.resize(460, 420)
        self.setToolTip(
            "Add or edit one chart-of-accounts row: number, name, type, optional sub-type and description."
        )
        self._build_ui()
        if account_id is not None:
            self._load(account_id)

    # -- UI ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._f_number = QLineEdit()
        self._f_number.setMaxLength(20)
        self._f_number.setPlaceholderText("e.g. 1010")
        self._f_number.setToolTip(
            "Unique account number or code used in reports and journal entries (required)."
        )

        self._f_name = QLineEdit()
        self._f_name.setPlaceholderText("e.g. Checking Account")
        self._f_name.setMinimumWidth(200)
        self._f_name.setToolTip("Display name for this account in lists and reports (required).")

        self._f_type = QComboBox()
        for key, label in COA_TYPE_UI_LABELS:
            self._f_type.addItem(label, userData=key)
        self._f_type.setToolTip(
            "Account type (income, expenses, assets, liabilities, equity, bank, loan, credit card, "
            "current/fixed/other asset, etc.). Determines normal debit/credit balance and report grouping."
        )

        self._f_subtype = QLineEdit()
        self._f_subtype.setPlaceholderText("e.g. Cash and Cash Equivalents")
        self._f_subtype.setToolTip(
            "Optional finer grouping (e.g. current asset, operating expense) for your own organization."
        )

        self._f_parent = QComboBox()
        self._f_parent.setToolTip(
            "Optional parent account. Sub-accounts indent under the parent on Chart of Accounts."
        )
        self._f_parent.addItem("(none)", None)
        for row in self._db.list_accounts(include_inactive=True):
            aid = coerce_combo_int_id(row["id"])
            if aid is None:
                continue
            if self._account_id is not None and aid == int(self._account_id):
                continue
            label = f"{row['account_number']} – {row['account_name']}"
            self._f_parent.addItem(escape_ampersand_for_qt(label), aid)

        self._f_description = QLineEdit()
        self._f_description.setPlaceholderText("Optional description")
        self._f_description.setToolTip("Optional longer notes shown when editing this account.")

        self._f_active = QCheckBox("Active")
        self._f_active.setChecked(True)
        self._f_active.setToolTip(
            "Inactive accounts are hidden from pickers unless you choose to show them elsewhere."
        )

        form.addRow("Account #:", self._f_number)
        form.addRow("Name:",      self._f_name)
        form.addRow("Type:",      self._f_type)
        form.addRow("Sub-type:",  self._f_subtype)
        form.addRow("Sub-account of:", self._f_parent)
        form.addRow("Description:", self._f_description)
        form.addRow("",           self._f_active)

        layout.addLayout(form)
        layout.addStretch()

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        tip_qdialog_button_box(
            btns,
            save="Save this COA account and close the dialog.",
            cancel="Close without saving changes to this account.",
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    # -- load ----------------------------------------------------------------

    def _load(self, account_id: int):
        row = self._db.get_account(account_id)
        if row is None:
            return
        self._f_number.setText(row["account_number"] or "")
        self._f_name.setText(row["account_name"] or "")
        # Set type combo
        idx = self._f_type.findData(row["account_type"])
        if idx >= 0:
            self._f_type.setCurrentIndex(idx)
        self._f_subtype.setText(row["sub_type"] or "")
        self._f_description.setText(row["description"] or "")
        self._f_active.setChecked(bool(row["is_active"]))
        pid = coerce_combo_int_id(row["parent_id"]) if "parent_id" in row.keys() else None
        if pid is not None:
            for i in range(self._f_parent.count()):
                if coerce_combo_int_id(self._f_parent.itemData(i)) == pid:
                    self._f_parent.setCurrentIndex(i)
                    break

    def _parent_id_value(self) -> Optional[int]:
        return coerce_combo_int_id(self._f_parent.currentData())

    # -- save ----------------------------------------------------------------

    def _save(self):
        number = self._f_number.text().strip()
        name   = self._f_name.text().strip()
        if not number:
            message_box_warning_ok(
                self,
                "Validation",
                "Account number is required.",
                ok_tip="Close; enter an account number before saving.",
            )
            return
        if not name:
            message_box_warning_ok(
                self,
                "Validation",
                "Account name is required.",
                ok_tip="Close; enter an account name before saving.",
            )
            return

        acct_type   = self._f_type.currentData()
        sub_type    = self._f_subtype.text().strip()
        description = self._f_description.text().strip()
        is_active   = self._f_active.isChecked()
        parent_id   = self._parent_id_value()

        normal_balance = infer_coa_normal_balance(acct_type)

        try:
            if self._account_id is None:
                self._db.add_account(
                    account_number=number,
                    account_name=name,
                    account_type=acct_type,
                    sub_type=sub_type,
                    normal_balance=normal_balance,
                    description=description,
                    parent_id=parent_id,
                    is_active=is_active,
                )
            else:
                self._db.update_account(
                    account_id=self._account_id,
                    account_number=number,
                    account_name=name,
                    account_type=acct_type,
                    sub_type=sub_type,
                    normal_balance=normal_balance,
                    description=description,
                    parent_id=parent_id,
                    is_active=is_active,
                )
        except (ValueError, sqlite3.IntegrityError) as exc:
            message_box_critical_ok(
                self,
                "Error",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; fix duplicates or invalid values and try again.",
            )
            return

        self.accept()


# ===========================================================================
# COATab
# ===========================================================================

class COATab(QWidget):
    """
    Tab widget for viewing and managing the Chart of Accounts.

    Emits ``coaChanged`` whenever the COA is modified so other widgets
    (e.g. bank import transaction table) can refresh their dropdowns.
    Emits ``openRegisterRequested`` with the selected COA account id when
    the user double-clicks a row (Chart of Accounts → that account's register).
    """

    coaChanged = Signal()
    openRegisterRequested = Signal(int)

    def __init__(self, db: COADatabase, gl_db: Optional[GLDatabase] = None, parent=None):
        super().__init__(parent)
        self._db = db
        self._gl_db = gl_db  # optional — used to show current account balance
        self._search_term = ""
        self._build_ui()
        self._refresh()

    # -- UI ------------------------------------------------------------------

    def _build_ui(self):
        self.setObjectName("chartOfAccountsTab")
        self.setToolTip(
            "Chart of accounts: add, edit, or deactivate rows; grid and shortcuts (F5 reloads when this tab has focus). "
            "Same company SQLite database as other main tabs; File → Backup / Restore (probooks.backup)."
        )
        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window, QColor(_COA_CANVAS))
        pal.setColor(QPalette.ColorRole.WindowText, QColor(_COA_TEXT))
        pal.setColor(QPalette.ColorRole.Base, QColor(_COA_PAPER))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor(_COA_STRIPE))
        pal.setColor(QPalette.ColorRole.Text, QColor(_COA_TEXT))
        pal.setColor(QPalette.ColorRole.Button, QColor(_COA_PAPER))
        pal.setColor(QPalette.ColorRole.ButtonText, QColor(_COA_TEXT))
        pal.setColor(QPalette.ColorRole.Highlight, QColor(_COA_SELECT))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor(_COA_SELECT_FG))
        pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(_COA_CAPTION))
        self.setPalette(pal)
        self.setAutoFillBackground(True)
        self.setStyleSheet(
            f"COATab {{ background-color: {_COA_CANVAS}; color: {_COA_TEXT}; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        # Compact editor toolbar (not a photocopy of the QB icon bar — app chrome stays).
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        self._btn_add = QPushButton("Account")
        self._btn_add.setObjectName("chartOfAccountsAdd")
        self._btn_add.setStyleSheet(_action_button_qss(primary=True))
        self._btn_add.setFixedHeight(26)
        self._btn_add.setToolTip("Create a new chart-of-accounts entry.")
        self._btn_edit = QPushButton("Edit")
        self._btn_edit.setStyleSheet(_action_button_qss())
        self._btn_edit.setFixedHeight(26)
        self._btn_edit.setEnabled(False)
        self._btn_edit.setToolTip(
            "Edit the selected account (toolbar Edit or right-click Edit Account…)."
        )
        self._btn_deactivate = QPushButton("Make Inactive")
        self._btn_deactivate.setStyleSheet(_action_button_qss())
        self._btn_deactivate.setFixedHeight(26)
        self._btn_deactivate.setEnabled(False)
        self._btn_deactivate.setToolTip(
            "Deactivate the selected account (show it again with Show inactive)."
        )
        self._chk_inactive = QCheckBox("Show inactive")
        self._chk_inactive.setStyleSheet(
            f"QCheckBox {{ color: {_COA_TEXT}; background: transparent; font-size: 12px; }}"
        )
        self._chk_inactive.setToolTip(
            "Include inactive accounts. F5 reloads the grid from the database."
        )

        self._btn_add.clicked.connect(self._on_add)
        self._btn_edit.clicked.connect(self._on_edit)
        self._btn_deactivate.clicked.connect(self._on_deactivate)
        self._chk_inactive.toggled.connect(self._refresh)

        toolbar.addWidget(self._btn_add)
        toolbar.addWidget(self._btn_edit)
        toolbar.addWidget(self._btn_deactivate)
        toolbar.addStretch()
        toolbar.addWidget(self._chk_inactive)
        layout.addLayout(toolbar)

        # Search row — Johnny's QB Pro Chart of Accounts.
        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        look = QLabel("Look for account name or number")
        look.setObjectName("chartOfAccountsLookLabel")
        look.setStyleSheet(
            f"color: {_COA_CAPTION}; font-size: 12px; background: transparent; border: none;"
        )
        search_row.addWidget(look)
        self._search = QLineEdit()
        self._search.setObjectName("chartOfAccountsSearch")
        self._search.setPlaceholderText("Account name or number")
        self._search.setFixedHeight(26)
        self._search.setMinimumWidth(260)
        self._search.setStyleSheet(
            f"QLineEdit {{ background: {_COA_PAPER}; border: 1px solid {_COA_GRID}; "
            f"border-radius: 3px; padding: 2px 8px; color: {_COA_TEXT}; }}"
        )
        self._search.setToolTip("Filter the list by account name or number.")
        self._search.returnPressed.connect(self._on_search)
        search_row.addWidget(self._search, 1)
        self._btn_search = QPushButton("Search")
        self._btn_search.setObjectName("chartOfAccountsSearchBtn")
        self._btn_search.setStyleSheet(_action_button_qss(primary=True))
        self._btn_search.setFixedHeight(26)
        self._btn_search.setToolTip("Apply the account name or number filter.")
        self._btn_search.clicked.connect(self._on_search)
        search_row.addWidget(self._btn_search)
        self._btn_reset = QPushButton("Reset")
        self._btn_reset.setObjectName("chartOfAccountsResetBtn")
        self._btn_reset.setStyleSheet(_action_button_qss())
        self._btn_reset.setFixedHeight(26)
        self._btn_reset.setToolTip("Clear the search filter and show all accounts.")
        self._btn_reset.clicked.connect(self._on_reset_search)
        search_row.addWidget(self._btn_reset)
        layout.addLayout(search_row)

        # Table — body takes most of the window.
        self._table = QTableWidget()
        self._table.setObjectName("chartOfAccountsTable")
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(
            ["", "", "NAME", "TYPE", "BALANCE TOTAL", "ATTACH"]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(True)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(_COL_MARK_X, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(_COL_MARK_SUB, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(_COL_NAME, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(_COL_TYPE, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_BAL, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_ATTACH, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(_COL_MARK_X, 22)
        self._table.setColumnWidth(_COL_MARK_SUB, 22)
        self._table.setColumnWidth(_COL_ATTACH, 56)
        self._table.verticalHeader().setDefaultSectionSize(24)
        self._table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._table.setStyleSheet(
            f"QTableWidget#chartOfAccountsTable {{"
            f" background-color: {_COA_PAPER};"
            f" alternate-background-color: {_COA_STRIPE};"
            f" color: {_COA_TEXT};"
            f" gridline-color: {_COA_GRID};"
            f" border: 1px solid {_COA_GRID};"
            f"}}"
            f"QTableWidget#chartOfAccountsTable::item:selected {{"
            f" background-color: {_COA_SELECT}; color: {_COA_SELECT_FG};"
            f"}}"
            f"QHeaderView::section {{"
            f" background-color: {_COA_HEADER}; color: {_COA_ACCENT};"
            f" font-weight: 700; font-size: 11px; padding: 4px 6px;"
            f" border: 1px solid {_COA_GRID};"
            f"}}"
        )
        self._table.itemSelectionChanged.connect(self._on_selection)
        self._table.doubleClicked.connect(self._on_row_double_clicked)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_coa_context_menu)
        self._table.setSortingEnabled(False)
        self._table.setToolTip(
            "Chart of accounts: double-click to open that account's register; right-click for "
            "Keyboard shortcuts…, Use Register…, Edit Account…, and change history (empty area OK). "
            "F5 reloads when this tab has focus. "
            "COA rows live in the company .db (File → Backup / Restore, probooks.backup)."
        )
        layout.addWidget(self._table, stretch=1)

        # Footer
        self._lbl_count = QLabel("")
        self._lbl_count.setStyleSheet(
            f"color: {_COA_CAPTION}; font-size: 11px; background: transparent;"
        )
        self._lbl_count.setToolTip(
            "Number of accounts shown and inactive count when Show inactive is on."
        )
        layout.addWidget(self._lbl_count)

        tip = QLabel(
            "F5 reloads the chart from the database (respects Show inactive). "
            "Journal and Bank import tabs also use F5 to refresh. "
            "Company SQLite: File → Backup / Restore (probooks.backup, CLI probooks backup/restore)."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #A0A0B0; font-size: 11px;")
        tip.setToolTip(
            "F5 refreshes this grid; double-click a row to open its register; "
            "right-click for shortcuts, Use Register…, Edit Account…, and change history. "
            "Back up the company .db from File → Backup / probooks backup before bulk COA edits."
        )
        layout.addWidget(tip)

        sc_refresh = QShortcut(QKeySequence("F5"), self)
        sc_refresh.setContext(Qt.WidgetWithChildrenShortcut)
        sc_refresh.activated.connect(self._refresh)

    def _on_search(self) -> None:
        self._search_term = (self._search.text() or "").strip()
        self._refresh()

    def _on_reset_search(self) -> None:
        self._search.clear()
        self._search_term = ""
        self._refresh()

    # -- data ----------------------------------------------------------------

    def _refresh(self):
        include_inactive = self._chk_inactive.isChecked()
        rows = self._db.list_accounts(include_inactive=include_inactive)
        needle = self._search_term.lower()
        if needle:
            filtered = []
            for row in rows:
                num = str(row["account_number"] or "").lower()
                name = str(row["account_name"] or "").lower()
                if needle in num or needle in name:
                    filtered.append(row)
            rows = filtered

        packed = ordered_coa_rows(rows)

        # Build balance lookup from GL trial balance (account display name → balance)
        # display name = "<number> <name>" (same format used when posting journal lines)
        gl_balances: dict[str, float] = {}
        if self._gl_db is not None:
            try:
                for tb_row in self._gl_db.trial_balance():
                    acct_key = tb_row.get("account", "")
                    td = float(tb_row.get("total_debit", 0.0) or 0.0)
                    tc = float(tb_row.get("total_credit", 0.0) or 0.0)
                    gl_balances[acct_key] = (td, tc)  # type: ignore[assignment]
            except Exception:
                pass  # GL unavailable — leave balances blank

        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(packed))
        inactive_n = 0
        for r, (row, depth) in enumerate(packed):
            aid = coerce_combo_int_id(row["id"])
            if aid is None:
                continue
            active = bool(row["is_active"])
            if not active:
                inactive_n += 1

            x_it = plain_display_table_item("✕" if not active else "")
            x_it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            x_it.setData(_ROLE_ACCOUNT_ID, aid)
            x_it.setToolTip("Inactive account" if not active else "")
            self._table.setItem(r, _COL_MARK_X, x_it)

            diamond = "◆" if depth > 0 else ""
            d_it = plain_display_table_item(diamond)
            d_it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            d_it.setData(_ROLE_DEPTH, depth)
            d_it.setToolTip("Sub-account" if depth > 0 else "")
            self._table.setItem(r, _COL_MARK_SUB, d_it)

            name_raw = str(row["account_name"] or "")
            indent = "    " * depth
            name_it = plain_display_table_item(indent + name_raw)
            name_it.setData(_ROLE_ACCOUNT_ID, aid)
            name_it.setData(_ROLE_NUMBER, str(row["account_number"] or ""))
            name_it.setData(_ROLE_ACTIVE, 1 if active else 0)
            name_it.setData(_ROLE_DEPTH, depth)
            if depth > 0:
                font = QFont(name_it.font())
                font.setItalic(True)
                name_it.setFont(font)
            self._table.setItem(r, _COL_NAME, name_it)

            type_lbl = qb_coa_type_label(row)
            self._table.setItem(r, _COL_TYPE, plain_display_table_item(str(type_lbl)))

            acct_num  = str(row["account_number"] or "").strip()
            acct_name = str(row["account_name"] or "").strip()
            display_key = f"{acct_num} {acct_name}".strip() if acct_num else acct_name
            bal_text = ""
            if display_key in gl_balances:
                td, tc = gl_balances[display_key]  # type: ignore[misc]
                normal = (row["normal_balance"] or "debit").lower()
                balance = round(td - tc, 2) if normal == "debit" else round(tc - td, 2)
                bal_text = f"{balance:,.2f}"
            elif self._gl_db is None:
                bal_text = "0.00"
            bal_item = plain_display_table_item(bal_text)
            bal_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(r, _COL_BAL, bal_item)

            clip = "📎" if (row["description"] or "").strip() else ""
            att = plain_display_table_item(clip)
            att.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            att.setToolTip("Notes on this account" if clip else "")
            self._table.setItem(r, _COL_ATTACH, att)

        count = len(packed)
        extra = f"  ({inactive_n} inactive)" if include_inactive and inactive_n else ""
        self._lbl_count.setText(f"{count} account{'s' if count != 1 else ''}{extra}")

    def navigate_to_account_id(self, account_id: int) -> bool:
        """Select and scroll to *account_id* in the grid; refresh with inactive rows if needed."""
        aid = coerce_combo_int_id(account_id)
        if aid is None:
            return False

        def _row_for_id() -> int:
            for r in range(self._table.rowCount()):
                it = self._table.item(r, _COL_NAME)
                if it is None:
                    continue
                if coerce_combo_int_id(it.data(_ROLE_ACCOUNT_ID)) == aid:
                    return r
            return -1

        row = _row_for_id()
        if row < 0:
            acct = self._db.get_account(aid)
            if acct is not None and not bool(acct["is_active"]) and not self._chk_inactive.isChecked():
                self._chk_inactive.setChecked(True)
                self._refresh()
                row = _row_for_id()
        if row < 0:
            return False
        item0 = self._table.item(row, _COL_NAME)
        self._table.clearSelection()
        self._table.selectRow(row)
        if item0 is not None:
            self._table.scrollToItem(
                item0,
                QAbstractItemView.ScrollHint.PositionAtCenter,
            )
        self._on_selection()
        return True

    def _selected_id(self) -> Optional[int]:
        r = self._table.currentRow()
        if r < 0:
            return None
        item = self._table.item(r, _COL_NAME)
        if item is None:
            return None
        return coerce_combo_int_id(item.data(_ROLE_ACCOUNT_ID))

    def _on_coa_context_menu(self, pos):
        idx = self._table.indexAt(pos)
        menu = QMenu(self)
        act_keys = menu.addAction(
            "Keyboard shortcuts…",
            lambda: show_more_main_tabs_keyboard_shortcuts_dialog(self),
        )
        act_keys.setToolTip(
            "Same summary as Help → More tab shortcuts (F5)… "
            "(COA, Journal, Reports, Audit chords). "
            + VIEW_BANK_REGISTER_KEYS_TOOLTIP
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        if not idx.isValid():
            menu.exec(self._table.viewport().mapToGlobal(pos))
            return
        row = idx.row()
        item = self._table.item(row, _COL_NAME)
        aid = (
            coerce_combo_int_id(item.data(_ROLE_ACCOUNT_ID))
            if item is not None
            else None
        )
        if aid is None:
            menu.exec(self._table.viewport().mapToGlobal(pos))
            return
        menu.addSeparator()
        act_reg = menu.addAction(
            "Use Register…",
            partial(self.openRegisterRequested.emit, aid),
        )
        act_reg.setToolTip(
            "Open this account's two-line register (same checkbook as Banking → Use Register)."
        )
        act_copy = menu.addAction("Copy row", partial(copy_table_row_as_tsv, self._table, row))
        act_copy.setToolTip(
            "Copy this COA row as tab-separated text for pasting into a spreadsheet or editor. "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        act_edit = menu.addAction("Edit Account…", self._on_edit)
        act_edit.setToolTip("Edit number, name, type, and sub-account of this chart row.")
        act_history = menu.addAction("View change history…")
        act_history.setToolTip(
            "Open field-level audit history for this chart-of-accounts account."
        )
        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))
        if chosen == act_history:
            show_entity_audit_history(
                self,
                self._db._conn,
                "coa_account",
                aid,
                window_title=f"Change history — COA account #{aid}",
                empty_message="No audit entries recorded for this account yet.",
            )

    # -- actions -------------------------------------------------------------

    def _on_selection(self):
        has_sel = self._selected_id() is not None
        self._btn_edit.setEnabled(has_sel)
        self._btn_deactivate.setEnabled(has_sel)

    def _on_row_double_clicked(self) -> None:
        acct_id = self._selected_id()
        if acct_id is None:
            return
        self.openRegisterRequested.emit(acct_id)

    def _on_add(self):
        dlg = AddEditCOADialog(self._db, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh()
            self.coaChanged.emit()

    def _on_edit(self):
        acct_id = self._selected_id()
        if acct_id is None:
            return
        dlg = AddEditCOADialog(self._db, account_id=acct_id, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh()
            self.coaChanged.emit()

    def _on_deactivate(self):
        acct_id = self._selected_id()
        if acct_id is None:
            return
        row = self._db.get_account(acct_id)
        if row is None:
            return
        name = row["account_name"]
        currently_active = bool(row["is_active"])
        if currently_active:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Question)
            box.setWindowTitle("Deactivate Account")
            box.setText(
                "Deactivate '"
                f"{escape_ampersand_for_qt(name or '')}"
                "'? It will no longer appear in dropdowns."
            )
            box.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            box.setToolTip(
                "Deactivated accounts stay in the database but are hidden from COA pickers until shown again. "
                "Consider File → Backup / probooks backup before bulk COA changes."
            )
            tip_message_box_buttons(
                box,
                yes="Deactivate this account; it hides from pick lists (data stays in the company .db — File → Backup before wide COA changes).",
                no="Keep the account active (cancel deactivation).",
            )
            confirm = box.exec()
            if confirm != QMessageBox.StandardButton.Yes:
                return
        self._set_account_active(row, acct_id, not currently_active)
        self._refresh()
        self.coaChanged.emit()

    def _set_account_active(self, row, account_id: int, is_active: bool):
        """Toggle the is_active flag on an account row, preserving all other fields."""
        pid = coerce_combo_int_id(row["parent_id"]) if "parent_id" in row.keys() else None
        self._db.update_account(
            account_id=account_id,
            account_number=row["account_number"],
            account_name=row["account_name"],
            account_type=row["account_type"],
            sub_type=row["sub_type"] or "",
            normal_balance=row["normal_balance"] or "debit",
            description=row["description"] or "",
            parent_id=pid,
            is_active=is_active,
        )
