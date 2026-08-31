"""Asset Accounts — QuickBooks Pro Desktop-style asset list + per-account register.

Non-bank asset accounts (``current_asset`` / ``fixed_asset`` / ``other_asset`` /
generic ``asset``) come from the runtime CoA. Bank accounts stay on the
Bank Register tab so we don't list cash accounts twice with slightly
different rules for what shows.

The register grid is **read-only**: it reflects GL journal lines posted to
the selected account. Empty accounts show zero rows and a ``$0.00`` ending
balance — never seed demo data here.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QPalette, QShortcut, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop_app.theme import DISABLED_FG
from probooksai import asset_accounts as aa
from probooksai.coa_db import COADatabase
from probooksai.gl import GLDatabase

_PAGE_BG = "#E8ECF1"
_PAPER = "#FFFFFF"
_PANEL = "#F4F7FA"
_STRIP = "#E4E8EC"
_GRID = "#C0C8D0"
_HEADER = "#D8DEE6"
_TEXT = "#1A1A1A"
_TITLE = "#1E3A5F"
_CAPTION = "#4A5560"
_LINK = "#1565C0"
_SELECT = "#C8E6C9"
_TOTAL_BG = "#F3F6F9"
_STRIP_BTN = "#B4BCC6"
_CONTROL_FACE = "#F7F8FA"
_CONTROL_HOVER = "#E4EEF7"
_CONTROL_PRESSED = "#C9D8EC"

_COL_DATE = 0
_COL_TYPE = 1
_COL_REF = 2
_COL_DESC = 3
_COL_DEBIT = 4
_COL_CREDIT = 5
_COL_BAL = 6
_HEADERS = ("Date", "Type", "Ref", "Description", "Debit", "Credit", "Balance")

_ROLE_ACCOUNT_ID = Qt.ItemDataRole.UserRole
_ROLE_ENTRY_ID = Qt.ItemDataRole.UserRole + 1


def _light_palette() -> QPalette:
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(_PAGE_BG))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(_TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(_PAPER))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(_PANEL))
    pal.setColor(QPalette.ColorRole.Text, QColor(_TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(_CONTROL_FACE))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(_TEXT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(_SELECT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(_TEXT))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(_CAPTION))
    return pal


def _btn_qss() -> str:
    return (
        f"QPushButton {{ background-color: {_CONTROL_FACE}; "
        f"border: 1px solid {_STRIP_BTN}; border-radius: 3px; color: {_TEXT}; "
        "font-size: 11px; padding: 3px 10px; min-height: 22px; }"
        f"QPushButton:hover {{ background-color: {_CONTROL_HOVER}; }}"
        f"QPushButton:pressed {{ background-color: {_CONTROL_PRESSED}; }}"
        f"QPushButton:disabled {{ color: {DISABLED_FG}; }}"
    )


def _combo_qss() -> str:
    return (
        f"QComboBox {{ background: {_PAPER}; border: 1px solid {_GRID}; "
        f"padding: 1px 6px; color: {_TEXT}; min-height: 20px; font-size: 12px; }}"
    )


def _fmt_money(value: float) -> str:
    return f"{float(value or 0):,.2f}"


def _fmt_signed_balance(value: float) -> str:
    v = float(value or 0)
    if abs(v) < 0.005:
        return "0.00"
    return f"{v:,.2f}"


class AssetAccountsTab(QWidget):
    """QB Pro-style Assets tab: asset-account picker + read-only per-account register."""

    openAccountRequested = Signal(int)

    def __init__(
        self,
        coa_db: Optional[COADatabase] = None,
        gl_conn: Optional[sqlite3.Connection] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("assetAccountsPage")
        self._coa_db = coa_db
        self._gl_conn = gl_conn
        self._gl = GLDatabase(gl_conn) if gl_conn is not None else None
        self._accounts: list[dict] = []
        self._current_account_id: Optional[int] = None
        self._populating = False
        self.setAutoFillBackground(True)
        self.setPalette(_light_palette())
        self.setStyleSheet(
            f"QWidget#assetAccountsPage {{ background: {_PAGE_BG}; color: {_TEXT}; }}"
        )
        self.setToolTip(
            "Assets: non-bank asset accounts from the Chart of Accounts and a read-only "
            "register of the GL activity posted to the selected account. "
            "F5 refreshes. Bank accounts stay on the Bank Register tab. "
            "Same company SQLite file (File → Backup / Restore, probooks.backup)."
        )
        self._build_ui()
        sc = QShortcut(QKeySequence("F5"), self)
        sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc.activated.connect(self.reload)
        self.reload()

    # -- UI ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_action_bar())
        root.addWidget(self._build_picker_row())
        root.addWidget(self._build_paper(), 1)
        root.addWidget(self._build_footer())

    def _build_action_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("assetsActionBar")
        bar.setStyleSheet(
            f"QFrame#assetsActionBar {{ background: {_STRIP}; "
            f"border-bottom: 1px solid {_GRID}; }}"
        )
        row = QHBoxLayout(bar)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(4)

        self._btn_goto = QPushButton("Go to Today")
        self._btn_goto.setObjectName("assetsGoto")
        self._btn_goto.setStyleSheet(_btn_qss())
        self._btn_goto.setToolTip("Scroll the register to today's date (if present).")
        self._btn_goto.clicked.connect(self._on_goto_today)
        row.addWidget(self._btn_goto)

        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.setObjectName("assetsRefresh")
        self._btn_refresh.setStyleSheet(_btn_qss())
        self._btn_refresh.setToolTip("Reload the account list and register grid (F5).")
        self._btn_refresh.clicked.connect(self.reload)
        row.addWidget(self._btn_refresh)

        row.addStretch(1)

        self._hdr_acct_lbl = QLabel("")
        self._hdr_acct_lbl.setObjectName("assetsHeaderLabel")
        self._hdr_acct_lbl.setStyleSheet(
            f"background: transparent; border: none; color: {_LINK}; "
            "font-size: 12px; font-weight: 600;"
        )
        row.addWidget(self._hdr_acct_lbl)

        bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        return bar

    def _build_picker_row(self) -> QWidget:
        wrap = QFrame()
        wrap.setObjectName("assetsPickerRow")
        wrap.setStyleSheet(
            f"QFrame#assetsPickerRow {{ background: {_PANEL}; "
            f"border-bottom: 1px solid {_GRID}; }}"
        )
        row = QHBoxLayout(wrap)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(8)

        lbl = QLabel("Asset account:")
        lbl.setStyleSheet(f"color: {_CAPTION}; font-size: 12px; font-weight: 600;")
        row.addWidget(lbl)

        self._acct_combo = QComboBox()
        self._acct_combo.setObjectName("assetsAccountCombo")
        self._acct_combo.setStyleSheet(_combo_qss())
        self._acct_combo.setMinimumWidth(320)
        self._acct_combo.setToolTip(
            "Choose an asset account (non-bank) to view its GL register."
        )
        self._acct_combo.currentIndexChanged.connect(self._on_account_changed)
        row.addWidget(self._acct_combo)
        row.addStretch(1)

        self._stamp = QLabel("")
        self._stamp.setObjectName("assetsTimestamp")
        self._stamp.setStyleSheet(f"color: {_CAPTION}; font-size: 11px;")
        row.addWidget(self._stamp)

        wrap.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        return wrap

    def _build_paper(self) -> QWidget:
        paper = QFrame()
        paper.setObjectName("assetsPaper")
        paper.setStyleSheet(f"QFrame#assetsPaper {{ background: {_PAPER}; border: none; }}")
        paper.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay = QVBoxLayout(paper)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(4)

        self._table = QTableWidget(0, len(_HEADERS))
        self._table.setObjectName("assetsRegisterTable")
        self._table.setHorizontalHeaderLabels(list(_HEADERS))
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(False)
        self._table.setShowGrid(True)
        self._table.setStyleSheet(
            f"QTableWidget {{ background: {_PAPER}; alternate-background-color: #F7F9FC; "
            f"color: {_TEXT}; gridline-color: {_GRID}; border: 1px solid {_GRID}; "
            "font-size: 12px; }}"
            f"QHeaderView::section {{ background: {_HEADER}; color: {_TEXT}; "
            f"border: 1px solid {_GRID}; border-left: none; padding: 4px 8px; "
            "font-size: 11px; font-weight: 600; }}"
            f"QTableWidget::item:selected {{ background: {_SELECT}; color: {_TEXT}; }}"
        )
        hh = self._table.horizontalHeader()
        hh.setStretchLastSection(False)
        hh.setSectionResizeMode(_COL_DATE, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(_COL_TYPE, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(_COL_REF, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(_COL_DESC, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(_COL_DEBIT, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(_COL_CREDIT, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(_COL_BAL, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setToolTip(
            "Read-only register: GL journal lines posted to the selected asset account, "
            "oldest first, with a running debit-normal balance. "
            "Empty account = zero rows and $0.00. Post activity from Bank Register / Enter Bills "
            "/ Write Checks / Journal to see it here."
        )
        lay.addWidget(self._table, 1)
        return paper

    def _build_footer(self) -> QWidget:
        f = QFrame()
        f.setObjectName("assetsFooter")
        f.setStyleSheet(
            f"QFrame#assetsFooter {{ background: {_PANEL}; "
            f"border-top: 2px solid {_GRID}; }}"
        )
        row = QHBoxLayout(f)
        row.setContentsMargins(12, 6, 14, 6)
        row.setSpacing(12)

        self._lbl_rowcount = QLabel("0 rows")
        self._lbl_rowcount.setObjectName("assetsRowCount")
        self._lbl_rowcount.setStyleSheet(f"color: {_CAPTION}; font-size: 11px;")
        row.addWidget(self._lbl_rowcount)
        row.addStretch(1)

        self._lbl_ending = QLabel("ENDING BALANCE  0.00")
        self._lbl_ending.setObjectName("assetsEndingBalance")
        self._lbl_ending.setStyleSheet(
            f"color: {_TITLE}; font-size: 13px; font-weight: 700; "
            f"background: {_TOTAL_BG}; padding: 3px 10px; "
            f"border: 1px solid {_GRID}; border-radius: 3px;"
        )
        row.addWidget(self._lbl_ending)

        f.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        return f

    # -- data flow -----------------------------------------------------------

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.reload()

    def set_coa_db(self, coa_db: Optional[COADatabase]) -> None:
        """Point the tab at a new CoA database (used on company switch)."""
        self._coa_db = coa_db
        self.reload()

    def set_gl_conn(self, gl_conn: Optional[sqlite3.Connection]) -> None:
        """Point the tab at a new GL connection (used on company switch)."""
        self._gl_conn = gl_conn
        self._gl = GLDatabase(gl_conn) if gl_conn is not None else None
        self.reload()

    def reload(self) -> None:
        self._reload_account_combo()
        self._reload_register()
        self._touch_stamp()

    def _touch_stamp(self) -> None:
        now = datetime.now()
        hour12 = now.hour % 12 or 12
        ampm = "AM" if now.hour < 12 else "PM"
        self._stamp.setText(f"{hour12}:{now.strftime('%M')} {ampm} · {now.strftime('%m/%d/%y')}")

    def _reload_account_combo(self) -> None:
        self._populating = True
        try:
            self._acct_combo.clear()
            if self._coa_db is None or self._coa_db._conn is None:
                self._accounts = []
            else:
                self._accounts = aa.list_asset_accounts(self._coa_db._conn)
            if not self._accounts:
                self._acct_combo.addItem("(no asset accounts)", -1)
                self._acct_combo.setEnabled(False)
                self._current_account_id = None
                return
            self._acct_combo.setEnabled(True)
            for row in self._accounts:
                display = row["display"]
                sub = (row.get("sub_type") or "").strip()
                label = f"{display} — {sub}" if sub else display
                self._acct_combo.addItem(label, int(row["id"]))
            # Preserve prior selection when possible.
            want = self._current_account_id
            if want is not None:
                for i in range(self._acct_combo.count()):
                    if int(self._acct_combo.itemData(i) or -1) == int(want):
                        self._acct_combo.setCurrentIndex(i)
                        break
            self._current_account_id = int(
                self._acct_combo.itemData(self._acct_combo.currentIndex()) or -1
            )
        finally:
            self._populating = False

    def _selected_account(self) -> Optional[dict]:
        if self._current_account_id is None or self._current_account_id < 0:
            return None
        for row in self._accounts:
            if int(row["id"]) == int(self._current_account_id):
                return row
        return None

    def _reload_register(self) -> None:
        acct = self._selected_account()
        self._table.setRowCount(0)
        self._lbl_rowcount.setText("0 rows")
        self._lbl_ending.setText("ENDING BALANCE  0.00")
        if acct is None:
            self._hdr_acct_lbl.setText("")
            return
        display = acct["display"]
        sub = (acct.get("sub_type") or "").strip()
        self._hdr_acct_lbl.setText(f"{display}" + (f"  ·  {sub}" if sub else ""))
        if self._gl_conn is None:
            return
        rows = aa.account_activity(self._gl_conn, display)
        self._table.setRowCount(len(rows))
        align_right = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        align_left = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        for r, row in enumerate(rows):
            date_item = self._make_item(row["entry_date"], align_left)
            date_item.setData(_ROLE_ACCOUNT_ID, int(acct["id"]))
            date_item.setData(_ROLE_ENTRY_ID, int(row["entry_id"]))
            self._table.setItem(r, _COL_DATE, date_item)
            self._table.setItem(r, _COL_TYPE, self._make_item(row["source"] or "manual", align_left))
            self._table.setItem(r, _COL_REF, self._make_item(str(row["entry_id"]), align_left))
            desc = (row["description"] or row["entry_memo"] or "").strip()
            self._table.setItem(r, _COL_DESC, self._make_item(desc, align_left))
            self._table.setItem(
                r, _COL_DEBIT, self._make_item(_fmt_money(row["debit"]) if row["debit"] else "", align_right)
            )
            self._table.setItem(
                r,
                _COL_CREDIT,
                self._make_item(_fmt_money(row["credit"]) if row["credit"] else "", align_right),
            )
            bal_item = self._make_item(_fmt_signed_balance(row["running_balance"]), align_right)
            font = QFont(bal_item.font())
            font.setBold(True)
            bal_item.setFont(font)
            bal_item.setForeground(QColor(_TITLE))
            self._table.setItem(r, _COL_BAL, bal_item)
        self._lbl_rowcount.setText(f"{len(rows)} row(s)")
        ending = aa.account_ending_balance(rows)
        self._lbl_ending.setText(f"ENDING BALANCE  {_fmt_signed_balance(ending)}")

    def _make_item(self, text: str, alignment) -> QTableWidgetItem:
        it = QTableWidgetItem(text)
        it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        it.setTextAlignment(alignment)
        return it

    # -- signals -------------------------------------------------------------

    def _on_account_changed(self, _idx: int) -> None:
        if self._populating:
            return
        aid = int(self._acct_combo.itemData(self._acct_combo.currentIndex()) or -1)
        self._current_account_id = aid if aid >= 0 else None
        self._reload_register()
        if self._current_account_id is not None:
            self.openAccountRequested.emit(int(self._current_account_id))

    def _on_goto_today(self) -> None:
        today = date.today().isoformat()
        for r in range(self._table.rowCount()):
            it = self._table.item(r, _COL_DATE)
            if it is not None and it.text() == today:
                self._table.selectRow(r)
                self._table.scrollToItem(it, QAbstractItemView.ScrollHint.PositionAtCenter)
                return
        # No exact match — scroll to the last row so the user sees "now".
        if self._table.rowCount() > 0:
            self._table.selectRow(self._table.rowCount() - 1)
            self._table.scrollToBottom()
