"""Invoice Codes tab: default row canvas, alphabetical load order, Rate column width."""

from __future__ import annotations

import sys

import pytest
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QApplication, QLineEdit

from desktop_app.invoice_codes_screen import (
    InvoiceCodesScreen,
    _DEFAULT_CODES_GRID_ROWS,
    _RATE_COLUMN_MIN_CHARS,
    invoice_code_db_row_sort_key,
)
from probooksai import business
from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import apply_extensions


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_invoice_code_db_row_sort_key_alphabetical_case_insensitive() -> None:
    rows = [
        {"code": "zebra", "sort_order": 0},
        {"code": "Alpha", "sort_order": 99},
        {"code": "Beta", "sort_order": 1},
    ]
    rows.sort(key=invoice_code_db_row_sort_key)
    assert [r["code"] for r in rows] == ["Alpha", "Beta", "zebra"]


def test_invoice_codes_screen_empty_db_shows_default_row_count(
    qapp: QApplication, tmp_path
) -> None:
    db_path = str(tmp_path / "codes_empty.db")
    db = BankDatabase(db_path)
    apply_extensions(db._conn)
    w = InvoiceCodesScreen(ap_conn=db._conn, coa_db=None)
    assert w._table.rowCount() == _DEFAULT_CODES_GRID_ROWS
    first = w._table.cellWidget(0, 0)
    assert isinstance(first, QLineEdit)
    assert first.text() == ""
    db.close()


def test_invoice_codes_screen_sorts_saved_rows_and_pads_to_fifty(
    qapp: QApplication, tmp_path
) -> None:
    db_path = str(tmp_path / "codes_two.db")
    db = BankDatabase(db_path)
    apply_extensions(db._conn)
    business.replace_invoice_item_codes(
        db._conn,
        [
            {
                "code": "ZZ-TOP",
                "description": "z",
                "item_type": "Service",
                "coa_account": "",
                "rate_value": 1.0,
                "rate_kind": "amount",
                "sort_order": 0,
            },
            {
                "code": "AA-FIRST",
                "description": "a",
                "item_type": "Service",
                "coa_account": "",
                "rate_value": 2.0,
                "rate_kind": "amount",
                "sort_order": 1,
            },
        ],
    )
    w = InvoiceCodesScreen(ap_conn=db._conn, coa_db=None)
    assert w._table.rowCount() == _DEFAULT_CODES_GRID_ROWS
    c0 = w._table.cellWidget(0, 0)
    assert isinstance(c0, QLineEdit)
    assert c0.text() == "AA-FIRST"
    c1 = w._table.cellWidget(1, 0)
    assert isinstance(c1, QLineEdit)
    assert c1.text() == "ZZ-TOP"
    last_filled = w._table.cellWidget(1, 4)
    assert isinstance(last_filled, QLineEdit)
    assert last_filled.text() != ""
    blank = w._table.cellWidget(2, 0)
    assert isinstance(blank, QLineEdit)
    assert blank.text() == ""
    db.close()


def test_invoice_codes_screen_more_than_fifty_saved_no_extra_padding(
    qapp: QApplication, tmp_path
) -> None:
    db_path = str(tmp_path / "codes_many.db")
    db = BankDatabase(db_path)
    apply_extensions(db._conn)
    rows_in = []
    for i in range(55):
        rows_in.append(
            {
                "code": f"C{i:02d}",
                "description": "x",
                "item_type": "Service",
                "coa_account": "",
                "rate_value": 1.0,
                "rate_kind": "amount",
                "sort_order": i,
            }
        )
    business.replace_invoice_item_codes(db._conn, rows_in)
    w = InvoiceCodesScreen(ap_conn=db._conn, coa_db=None)
    assert w._table.rowCount() == 55
    db.close()


def test_invoice_codes_rate_column_at_least_eight_chars_wide(
    qapp: QApplication, tmp_path
) -> None:
    db_path = str(tmp_path / "codes_width.db")
    db = BankDatabase(db_path)
    apply_extensions(db._conn)
    w = InvoiceCodesScreen(ap_conn=db._conn, coa_db=None)
    fm = QFontMetrics(w._table.font())
    need = fm.horizontalAdvance("0" * _RATE_COLUMN_MIN_CHARS) + 28
    assert w._table.columnWidth(4) >= need
    db.close()
