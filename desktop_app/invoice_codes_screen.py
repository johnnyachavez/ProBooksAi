"""Invoice item / service **Codes** master list — feeds the Manual Invoice line **Code** column.

Same dark workflow styling as Invoices / Enter Bills. Columns: Code, Description, Type,
Account (Chart of Accounts label), Rate (amount or %). Saving replaces rows in ``invoice_item_codes``.
"""

from __future__ import annotations

import sqlite3
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from probooksai import business
from probooksai.coa_db import COADatabase

from desktop_app.qt_mnemonic import message_box_information_ok, message_box_warning_ok
from desktop_app.theme import (
    WORKFLOW_ALT_ROW as _CODE_STRIPE,
    WORKFLOW_CAPTION as _CODE_CAPTION,
    WORKFLOW_GRID as _CODE_GRID,
    WORKFLOW_HEADER_BG as _CODE_HEADER,
    WORKFLOW_INPUT_BG,
    WORKFLOW_PAGE_BG as _CODE_BG,
    WORKFLOW_PANEL_BG as _CODE_PANEL,
    WORKFLOW_TEXT as _CODE_TEXT,
)

_ITEM_TYPES = ("Service", "Discount", "Other Charge")

# Default working grid: at least this many rows (empty tail unless DB has more codes).
_DEFAULT_CODES_GRID_ROWS = 50
# Rate column: never narrower than this many "0" digits at the table font (pins visually on the right).
_RATE_COLUMN_MIN_CHARS = 8


def parse_rate_input(raw: str) -> tuple[float, str]:
    """Return ``(rate_value, rate_kind)`` where kind is ``amount`` or ``percent``."""
    s = (raw or "").strip().replace(",", "")
    if not s:
        return 0.0, "amount"
    if s.endswith("%"):
        try:
            return float(s[:-1].strip()), "percent"
        except ValueError:
            return 0.0, "percent"
    try:
        return float(s), "amount"
    except ValueError:
        return 0.0, "amount"


def format_rate_display(rate_value: float, rate_kind: str) -> str:
    if (rate_kind or "").lower() == "percent":
        return f"{rate_value:.1f}%"
    return f"{rate_value:.2f}"


def invoice_code_db_row_sort_key(row: object) -> tuple:
    """Sort saved codes alphabetically by Code (case-insensitive), then ``sort_order`` for stability."""
    d = dict(row)
    return (
        (d.get("code") or "").strip().lower(),
        int(d.get("sort_order") or 0),
    )


class InvoiceCodesScreen(QWidget):
    """Editable grid of invoice line codes (company file)."""

    codesChanged = Signal()

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        ap_conn: Optional[sqlite3.Connection] = None,
        coa_db: Optional[COADatabase] = None,
    ) -> None:
        super().__init__(parent)
        self._ap_conn = ap_conn
        self._coa_db = coa_db
        self.setToolTip(
            "Codes: default line items for invoices (Code, description, income account, rate). "
            "Same company .db as Invoices."
        )
        self._build_ui()
        self._load_from_db()

    def set_connections(
        self,
        ap_conn: Optional[sqlite3.Connection],
        coa_db: Optional[COADatabase],
    ) -> None:
        self._ap_conn = ap_conn
        self._coa_db = coa_db
        self._load_from_db()
        self.refresh_coa_combos()

    def refresh_coa_combos(self) -> None:
        """Refresh Account combos when the Chart of Accounts changes."""
        accounts = self._coa_account_strings()
        for r in range(self._table.rowCount()):
            w = self._table.cellWidget(r, 3)
            if isinstance(w, QComboBox):
                cur = w.currentText()
                w.blockSignals(True)
                w.clear()
                w.addItem("")
                for a in accounts:
                    w.addItem(a)
                idx = w.findText(cur)
                w.setCurrentIndex(idx if idx >= 0 else 0)
                w.blockSignals(False)

    def _coa_account_strings(self) -> list[str]:
        if self._coa_db is None:
            return []
        try:
            return self._coa_db.display_list(include_inactive=False)
        except (sqlite3.Error, OSError, TypeError, ValueError):
            return []

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        title_row = QHBoxLayout()
        title = QLabel("Codes")
        title.setStyleSheet(
            f"font-size: 20px; font-weight: 600; color: {_CODE_TEXT}; background: transparent;"
        )
        title_row.addWidget(title)
        title_row.addStretch(1)
        self._btn_add = QPushButton("Add row")
        self._btn_add.clicked.connect(self._on_add_row)
        self._btn_del = QPushButton("Delete selected")
        self._btn_del.clicked.connect(self._on_delete_rows)
        self._btn_save = QPushButton("Save to company file")
        self._btn_save.setToolTip("Persist all rows to this company database (replaces the saved list).")
        self._btn_save.clicked.connect(self._on_save)
        self._btn_reload = QPushButton("Reload")
        self._btn_reload.setToolTip("Discard unsaved edits and reload from the database.")
        self._btn_reload.clicked.connect(self._load_from_db)
        for b in (self._btn_add, self._btn_del, self._btn_save, self._btn_reload):
            b.setAutoDefault(False)
            b.setDefault(False)
        title_row.addWidget(self._btn_add)
        title_row.addWidget(self._btn_del)
        title_row.addWidget(self._btn_save)
        title_row.addWidget(self._btn_reload)
        outer.addLayout(title_row)

        hint = QLabel(
            "Maintain service items, discounts, and other charges. "
            "Rate: enter an amount (e.g. 164.00) or a percent (e.g. 3% or -10%). "
            "On an invoice line, type the Code (or pick from suggestions) to fill description and rate."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {_CODE_CAPTION}; font-size: 12px;")
        outer.addWidget(hint)

        page = QFrame()
        page.setObjectName("invoiceCodesPanel")
        page.setStyleSheet(
            f"QFrame#invoiceCodesPanel {{ background-color: {_CODE_BG}; border: 1px solid {_CODE_GRID}; "
            "border-radius: 8px; }}"
        )
        play = QVBoxLayout(page)
        play.setContentsMargins(12, 12, 12, 12)
        play.setSpacing(8)

        self._table = QTableWidget(0, 5)
        self._table.setObjectName("invoiceCodesTable")
        self._table.setHorizontalHeaderLabels(
            ["Code", "Description", "Type", "Account", "Rate"]
        )
        hh = self._table.horizontalHeader()
        # Code–Account stretch; Rate fixed width at the right (min ~8 chars), not absorbing extra width.
        hh.setStretchLastSection(False)
        for c in range(4):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        self._table.setStyleSheet(
            f"QTableWidget#invoiceCodesTable {{"
            f" background-color: {_CODE_PANEL};"
            f" alternate-background-color: {_CODE_STRIPE};"
            f" color: {_CODE_TEXT};"
            f" gridline-color: {_CODE_GRID};"
            f" border: 1px solid {_CODE_GRID};"
            " }"
            f"QHeaderView::section {{"
            f" background-color: {_CODE_HEADER};"
            f" color: {_CODE_TEXT};"
            f" padding: 6px; border: 1px solid {_CODE_GRID};"
            " font-weight: 600;"
            " }}"
        )
        play.addWidget(self._table, 1)
        outer.addWidget(page, 1)

    def _rate_column_min_width_px(self) -> int:
        """Minimum Rate column width: at least eight typical digit widths + cell padding."""
        fm = QFontMetrics(self._table.font())
        return fm.horizontalAdvance("0" * _RATE_COLUMN_MIN_CHARS) + 28

    def _apply_rate_column_width(self) -> None:
        w = max(self._rate_column_min_width_px(), self._table.columnWidth(4))
        self._table.setColumnWidth(4, w)

    def _style_line_edit(self, le: QLineEdit) -> None:
        le.setStyleSheet(
            f"QLineEdit {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_CODE_GRID}; "
            f"padding: 4px 6px; color: {_CODE_TEXT}; }}"
        )

    def _style_combo(self, cb: QComboBox) -> None:
        cb.setStyleSheet(
            f"QComboBox {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_CODE_GRID}; "
            f"padding: 4px 8px; color: {_CODE_TEXT}; }}"
        )

    def _append_row(self, *, data: Optional[dict] = None) -> None:
        r = self._table.rowCount()
        self._table.insertRow(r)

        code = QLineEdit()
        code.setPlaceholderText("e.g. FS-1")
        self._style_line_edit(code)
        if data:
            code.setText((data.get("code") or "").strip())

        desc = QLineEdit()
        desc.setPlaceholderText("Description")
        self._style_line_edit(desc)
        if data:
            desc.setText((data.get("description") or "").strip())

        typ = QComboBox()
        self._style_combo(typ)
        for t in _ITEM_TYPES:
            typ.addItem(t)
        if data:
            it = (data.get("item_type") or "Service").strip()
            idx = typ.findText(it)
            typ.setCurrentIndex(idx if idx >= 0 else 0)

        acct = QComboBox()
        self._style_combo(acct)
        acct.addItem("")
        for a in self._coa_account_strings():
            acct.addItem(a)
        if data:
            ca = (data.get("coa_account") or "").strip()
            idx = acct.findText(ca)
            if idx >= 0:
                acct.setCurrentIndex(idx)

        rate = QLineEdit()
        rate.setPlaceholderText("164.00 or 10%")
        self._style_line_edit(rate)
        if data:
            rv = float(data.get("rate_value") or 0.0)
            rk = (data.get("rate_kind") or "amount").strip().lower()
            rate.setText(format_rate_display(rv, rk))

        self._table.setCellWidget(r, 0, code)
        self._table.setCellWidget(r, 1, desc)
        self._table.setCellWidget(r, 2, typ)
        self._table.setCellWidget(r, 3, acct)
        self._table.setCellWidget(r, 4, rate)

    def _on_add_row(self) -> None:
        self._append_row(data=None)

    def _on_delete_rows(self) -> None:
        rows = sorted({i.row() for i in self._table.selectedIndexes()}, reverse=True)
        for r in rows:
            self._table.removeRow(r)

    def _collect_rows(self) -> list[dict]:
        rows: list[dict] = []
        for r in range(self._table.rowCount()):
            c0 = self._table.cellWidget(r, 0)
            c1 = self._table.cellWidget(r, 1)
            c2 = self._table.cellWidget(r, 2)
            c3 = self._table.cellWidget(r, 3)
            c4 = self._table.cellWidget(r, 4)
            if not all(
                isinstance(c0, QLineEdit)
                and isinstance(c1, QLineEdit)
                and isinstance(c2, QComboBox)
                and isinstance(c3, QComboBox)
                and isinstance(c4, QLineEdit)
            ):
                continue
            code = c0.text().strip()
            if not code:
                continue
            rv, rk = parse_rate_input(c4.text())
            rows.append(
                {
                    "code": code,
                    "description": c1.text().strip(),
                    "item_type": c2.currentText().strip(),
                    "coa_account": c3.currentText().strip(),
                    "rate_value": rv,
                    "rate_kind": rk,
                    "sort_order": len(rows),
                }
            )
        return rows

    def _on_save(self) -> None:
        if self._ap_conn is None:
            message_box_warning_ok(
                self,
                "Codes",
                "Open a company file before saving codes.",
                ok_tip="Use File → Open company…",
            )
            return
        rows = self._collect_rows()
        codes_seen: set[str] = set()
        for row in rows:
            key = row["code"].lower()
            if key in codes_seen:
                message_box_warning_ok(
                    self,
                    "Codes",
                    f"Duplicate code: {row['code']!r}. Each code must be unique.",
                    ok_tip="Remove or rename the duplicate row.",
                )
                return
            codes_seen.add(key)
        try:
            business.replace_invoice_item_codes(self._ap_conn, rows)
        except sqlite3.Error as exc:
            message_box_warning_ok(
                self,
                "Codes",
                f"Could not save: {exc}",
                ok_tip="Close and try again.",
            )
            return
        message_box_information_ok(
            self,
            "Codes",
            f"Saved {len(rows)} code(s).",
            ok_tip="Use the Invoices tab and enter a code on a line to apply it.",
        )
        self.codesChanged.emit()

    def _load_from_db(self) -> None:
        self._table.setRowCount(0)
        db_rows: list = []
        if self._ap_conn is not None:
            try:
                db_rows = list(business.list_invoice_item_codes(self._ap_conn))
            except sqlite3.Error:
                db_rows = []
        db_rows.sort(key=invoice_code_db_row_sort_key)
        for row in db_rows:
            self._append_row(data=dict(row))
        target_rows = max(_DEFAULT_CODES_GRID_ROWS, len(db_rows))
        while self._table.rowCount() < target_rows:
            self._append_row(data=None)
        self._apply_rate_column_width()
