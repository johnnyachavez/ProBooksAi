"""Enter Bill workflow screen — UI-focused; vendor list/address from company DB when connected.

Dark navy styling matches :class:`PayBillsScreen` / :class:`InvoiceScreen` workflow theme (Customers / Vendors AR/AP body).
"""

from __future__ import annotations

import sqlite3
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop_app.extra_tabs import open_ap_bill_edit_dialog
from desktop_app.qt_mnemonic import message_box_information_ok
from probooksai import business

from desktop_app.theme import (
    WORKFLOW_ALT_ROW as _BILL_STRIPE,
    WORKFLOW_CAPTION as _BILL_CAPTION,
    WORKFLOW_GRID as _BILL_GRID,
    WORKFLOW_HEADER_BG as _BILL_HEADER,
    WORKFLOW_INPUT_BG,
    WORKFLOW_PAGE_BG as _BILL_BG,
    WORKFLOW_PANEL_BG as _BILL_PANEL,
    WORKFLOW_TEXT as _BILL_TEXT,
)


def _amount_spin() -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(0.0, 999_999_999.99)
    s.setDecimals(2)
    s.setPrefix("$ ")
    s.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
    s.setStyleSheet(
        f"QDoubleSpinBox {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_BILL_GRID}; "
        f"padding: 2px 6px; color: {_BILL_TEXT}; }}"
    )
    return s


def _table_line_edit() -> QLineEdit:
    le = QLineEdit()
    le.setStyleSheet(
        f"QLineEdit {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_BILL_GRID}; "
        f"padding: 2px 6px; color: {_BILL_TEXT}; }}"
    )
    return le


def _format_vendor_address_row(row: dict) -> str:
    """Build a multi-line address block from a ``vendors`` row."""
    lines: list[str] = []
    addr = (row.get("address") or "").strip()
    if addr:
        lines.append(addr)
    email = (row.get("email") or "").strip()
    if email:
        lines.append(email)
    phone = (row.get("phone") or "").strip()
    if phone:
        lines.append(phone)
    return "\n".join(lines)


class EnterBillsScreen(QWidget):
    """Bill header (vendor + address) and expense-style line grid (visual foundation for A/P entry)."""

    _LINE_COLS = ("Date", "Ticket Number", "Dollar Amount", "Memo", "Customer:Job")
    _N_EXPENSE_ROWS = 12

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        ap_conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        super().__init__(parent)
        self._ap_conn = ap_conn
        self.setToolTip(
            "Enter Bills: vendor bill header and line grid. "
            "Vendor list uses your company file when available. "
            "Same company .db (File → Backup / Restore, probooks.backup)."
        )
        self._amount_spins: list[QDoubleSpinBox] = []
        self._build_ui()
        self._populate_vendor_combo()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        page = QFrame()
        page.setObjectName("enterBillsLightPanel")
        page.setStyleSheet(
            f"QFrame#enterBillsLightPanel {{ background-color: {_BILL_BG}; border: 1px solid {_BILL_GRID}; "
            "border-radius: 8px; }}"
        )
        play = QVBoxLayout(page)
        play.setContentsMargins(16, 16, 16, 16)
        play.setSpacing(12)

        title_row = QHBoxLayout()
        title = QLabel("Enter Bills")
        title.setStyleSheet(
            f"font-size: 20px; font-weight: 600; color: {_BILL_TEXT}; background: transparent;"
        )
        title_row.addWidget(title)
        title_row.addStretch(1)
        play.addLayout(title_row)

        sec_vendor = QLabel("Vendor & bill header")
        sec_vendor.setStyleSheet(
            f"color: {_BILL_CAPTION}; font-size: 11px; font-weight: 600; "
            "letter-spacing: 0.03em; background: transparent;"
        )
        sec_vendor.setToolTip("Select a vendor; address fills from your company file when available.")
        play.addWidget(sec_vendor)

        # ── Header: Vendor + Vendor Address only (full width) ──
        form_frame = QFrame()
        form_frame.setObjectName("enterBillsHeaderBand")
        form_frame.setStyleSheet(
            f"QFrame#enterBillsHeaderBand {{ background-color: {_BILL_PANEL}; "
            f"border: 1px solid {_BILL_GRID}; border-radius: 8px; }}"
        )
        form_lay = QGridLayout(form_frame)
        form_lay.setContentsMargins(14, 12, 14, 12)
        form_lay.setHorizontalSpacing(12)
        form_lay.setVerticalSpacing(10)
        form_lay.setColumnStretch(1, 1)

        self._vendor = QComboBox()
        self._vendor.setEditable(False)
        self._vendor.setMinimumWidth(280)
        self._vendor.setStyleSheet(
            f"QComboBox {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_BILL_GRID}; "
            f"padding: 4px 8px; color: {_BILL_TEXT}; }}"
        )

        self._address = QPlainTextEdit()
        self._address.setPlaceholderText("Vendor Address")
        self._address.setFixedHeight(72)
        self._address.setStyleSheet(
            f"QPlainTextEdit {{ background: {WORKFLOW_INPUT_BG}; color: {_BILL_TEXT}; "
            f"border: 1px solid {_BILL_GRID}; border-radius: 4px; padding: 4px; }}"
        )

        _vl = QLabel("Vendor")
        _vl.setStyleSheet(
            f"color: {_BILL_CAPTION}; font-size: 11px; font-weight: 600; background: transparent;"
        )
        form_lay.addWidget(_vl, 0, 0, Qt.AlignmentFlag.AlignRight)
        form_lay.addWidget(self._vendor, 0, 1)
        _al = QLabel("Vendor Address")
        _al.setStyleSheet(
            f"color: {_BILL_CAPTION}; font-size: 11px; font-weight: 600; background: transparent;"
        )
        form_lay.addWidget(
            _al,
            1,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
        )
        form_lay.addWidget(self._address, 1, 1)

        play.addWidget(form_frame)

        self._vendor.currentIndexChanged.connect(self._on_vendor_changed)

        line_sec = QLabel("Expense lines")
        line_sec.setStyleSheet(
            f"color: {_BILL_CAPTION}; font-size: 11px; font-weight: 600; "
            "letter-spacing: 0.03em; background: transparent;"
        )
        line_sec.setToolTip("Line-by-line expense detail; placeholder save actions below.")
        play.addWidget(line_sec)

        # ── Line grid (no separate expenses subtotal row) ──
        self._table = QTableWidget(self._N_EXPENSE_ROWS, len(self._LINE_COLS))
        self._table.setObjectName("enterBillsExpensesTable")
        self._table.setHorizontalHeaderLabels(self._LINE_COLS)
        self._table.verticalHeader().setVisible(True)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self._table.horizontalHeader().setStretchLastSection(False)
        for col in (0, 1, 2):
            self._table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )
        for col in (3, 4):
            self._table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.Stretch
            )

        self._table.setStyleSheet(
            f"QTableWidget#enterBillsExpensesTable {{"
            f" background-color: {_BILL_PANEL};"
            f" alternate-background-color: {_BILL_STRIPE};"
            f" color: {_BILL_TEXT};"
            f" gridline-color: {_BILL_GRID};"
            f" border: 1px solid {_BILL_GRID};"
            " }"
            f"QHeaderView::section {{"
            f" background-color: {_BILL_HEADER};"
            f" color: {_BILL_TEXT};"
            f" padding: 6px; border: 1px solid {_BILL_GRID};"
            " font-weight: 600;"
            " }}"
        )

        edit_flags = (
            Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsEditable
        )
        for row in range(self._N_EXPENSE_ROWS):
            dt = _table_line_edit()
            dt.setPlaceholderText("Date")
            self._table.setCellWidget(row, 0, dt)

            ticket = _table_line_edit()
            ticket.setPlaceholderText("Ticket Number")
            self._table.setCellWidget(row, 1, ticket)

            amt = _amount_spin()
            amt.setValue(0.0)
            self._table.setCellWidget(row, 2, amt)
            self._amount_spins.append(amt)

            memo_it = QTableWidgetItem("")
            memo_it.setFlags(edit_flags)
            self._table.setItem(row, 3, memo_it)

            job_edit = QLineEdit()
            job_edit.setPlaceholderText("Customer:Job")
            job_edit.setStyleSheet(
                f"QLineEdit {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_BILL_GRID}; "
                f"padding: 2px 4px; color: {_BILL_TEXT}; }}"
            )
            self._table.setCellWidget(row, 4, job_edit)

        play.addWidget(self._table, 1)

        # ── Bottom actions ──
        actions_frame = QFrame()
        actions_frame.setObjectName("enterBillsActionsBar")
        actions_frame.setStyleSheet(
            f"QFrame#enterBillsActionsBar {{ background-color: {_BILL_PANEL}; "
            f"border: 1px solid {_BILL_GRID}; border-radius: 6px; }}"
        )
        bot = QHBoxLayout(actions_frame)
        bot.setContentsMargins(12, 10, 12, 10)
        bot.addStretch(1)
        self._btn_save_close = QPushButton("Save && Close")
        self._btn_save_new = QPushButton("Save && New")
        self._btn_clear = QPushButton("Clear")
        self._btn_save_close.setToolTip("Placeholder — no save yet.")
        self._btn_save_new.setToolTip("Placeholder — no save yet.")
        self._btn_clear.setToolTip("Reset this form (UI only).")
        self._btn_save_close.clicked.connect(self._on_save_close)
        self._btn_save_new.clicked.connect(self._on_save_new)
        self._btn_clear.clicked.connect(self._on_clear)
        for _b in (self._btn_save_close, self._btn_save_new, self._btn_clear):
            _b.setAutoDefault(False)
            _b.setDefault(False)
        bot.addWidget(self._btn_save_close)
        bot.addWidget(self._btn_save_new)
        bot.addWidget(self._btn_clear)
        play.addWidget(actions_frame)

        outer.addWidget(page, 1)

    def _populate_vendor_combo(self) -> None:
        self._vendor.blockSignals(True)
        self._vendor.clear()
        self._vendor.addItem("", None)
        if self._ap_conn is not None:
            try:
                for row in business.list_vendors(self._ap_conn):
                    d = dict(row)
                    vid = int(d["id"])
                    name = (d.get("name") or "").strip()
                    self._vendor.addItem(name or f"Vendor #{vid}", vid)
            except (sqlite3.Error, KeyError, TypeError, ValueError):
                pass
        self._vendor.blockSignals(False)
        self._on_vendor_changed(self._vendor.currentIndex())

    def refresh_vendors(self) -> None:
        """Reload vendor names from the company connection (e.g. after Business hub edits)."""
        self._populate_vendor_combo()

    def open_bill_by_id(self, bill_id: int) -> bool:
        """Open **Edit bill** for a bank/register link (this tab is the bill workspace)."""
        if self._ap_conn is None:
            message_box_information_ok(
                self,
                "Bill",
                "Open a company file to edit bills.",
                ok_tip="Close; use File → Open company… then try the link again.",
            )
            return False

        def _after_save() -> None:
            self.refresh_vendors()

        return open_ap_bill_edit_dialog(
            self, self._ap_conn, int(bill_id), after_save=_after_save
        )

    def _on_vendor_changed(self, _index: int) -> None:
        raw = self._vendor.currentData()
        if raw is None or self._ap_conn is None:
            self._address.clear()
            return
        try:
            vid = int(raw)
        except (TypeError, ValueError):
            self._address.clear()
            return
        row = business.get_vendor(self._ap_conn, vid)
        if row is None:
            self._address.clear()
            return
        self._address.setPlainText(_format_vendor_address_row(dict(row)))

    def _on_save_close(self) -> None:
        print("[Enter Bills] Save & Close (placeholder)")

    def _on_save_new(self) -> None:
        print("[Enter Bills] Save & New (placeholder)")

    def _on_clear(self) -> None:
        self._vendor.blockSignals(True)
        self._vendor.setCurrentIndex(0)
        self._vendor.blockSignals(False)
        self._address.clear()
        for sp in self._amount_spins:
            sp.setValue(0.0)
        for r in range(self._N_EXPENSE_ROWS):
            dt = self._table.cellWidget(r, 0)
            if isinstance(dt, QLineEdit):
                dt.clear()
            ticket = self._table.cellWidget(r, 1)
            if isinstance(ticket, QLineEdit):
                ticket.clear()
            memo = self._table.item(r, 3)
            if memo is not None:
                memo.setText("")
            job = self._table.cellWidget(r, 4)
            if isinstance(job, QLineEdit):
                job.clear()
        print("[Enter Bills] Clear (placeholder)")
