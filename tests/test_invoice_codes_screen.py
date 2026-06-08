"""Invoice Codes tab: default row canvas, alphabetical load order, Rate column width."""

from __future__ import annotations

import sys

import pytest
from unittest.mock import patch

from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox

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


def test_invoice_codes_save_button_renamed_to_save(qapp: QApplication, tmp_path) -> None:
    """Save button now reads 'Save' (was 'Save to company file')."""
    db_path = str(tmp_path / "codes_btn.db")
    db = BankDatabase(db_path)
    apply_extensions(db._conn)
    w = InvoiceCodesScreen(ap_conn=db._conn, coa_db=None)
    assert w._btn_save.text() == "Save"
    db.close()


def test_invoice_codes_initial_state_is_clean(qapp: QApplication, tmp_path) -> None:
    """A freshly loaded grid has no unsaved edits (Reload should not warn)."""
    db_path = str(tmp_path / "codes_clean.db")
    db = BankDatabase(db_path)
    apply_extensions(db._conn)
    w = InvoiceCodesScreen(ap_conn=db._conn, coa_db=None)
    assert w.has_unsaved_edits() is False
    db.close()


def test_invoice_codes_user_edit_marks_dirty(qapp: QApplication, tmp_path) -> None:
    """Typing into a Code cell flips the screen to 'unsaved edits'."""
    db_path = str(tmp_path / "codes_dirty.db")
    db = BankDatabase(db_path)
    apply_extensions(db._conn)
    w = InvoiceCodesScreen(ap_conn=db._conn, coa_db=None)
    assert w.has_unsaved_edits() is False
    code_cell = w._table.cellWidget(0, 0)
    assert isinstance(code_cell, QLineEdit)
    code_cell.setFocus()
    code_cell.insert("ABC")
    assert w.has_unsaved_edits() is True
    db.close()


def test_invoice_codes_reload_with_no_edits_does_not_prompt(
    qapp: QApplication, tmp_path
) -> None:
    """Reload on a clean grid skips the discard-confirmation prompt entirely."""
    db_path = str(tmp_path / "codes_reload_clean.db")
    db = BankDatabase(db_path)
    apply_extensions(db._conn)
    w = InvoiceCodesScreen(ap_conn=db._conn, coa_db=None)
    with patch.object(w, "_confirm_discard_unsaved_edits") as confirm:
        w._on_reload_clicked()
        confirm.assert_not_called()
    db.close()


def test_invoice_codes_reload_with_unsaved_edits_prompts_and_can_cancel(
    qapp: QApplication, tmp_path
) -> None:
    """Reload with unsaved edits asks first; **No** keeps the typed-in text on screen."""
    db_path = str(tmp_path / "codes_reload_cancel.db")
    db = BankDatabase(db_path)
    apply_extensions(db._conn)
    w = InvoiceCodesScreen(ap_conn=db._conn, coa_db=None)
    code_cell = w._table.cellWidget(0, 0)
    assert isinstance(code_cell, QLineEdit)
    code_cell.setFocus()
    code_cell.insert("KEEPME")
    assert w.has_unsaved_edits() is True
    with patch.object(w, "_confirm_discard_unsaved_edits", return_value=False) as confirm:
        w._on_reload_clicked()
        confirm.assert_called_once()
    cell_after = w._table.cellWidget(0, 0)
    assert isinstance(cell_after, QLineEdit)
    assert cell_after.text() == "KEEPME", (
        "Cancelling the discard prompt must leave unsaved edits intact on screen."
    )
    assert w.has_unsaved_edits() is True
    db.close()


def test_invoice_codes_reload_with_unsaved_edits_yes_discards_and_reloads(
    qapp: QApplication, tmp_path
) -> None:
    """Reload with unsaved edits → confirm Yes → grid is reloaded from DB and dirty clears."""
    db_path = str(tmp_path / "codes_reload_yes.db")
    db = BankDatabase(db_path)
    apply_extensions(db._conn)
    business.replace_invoice_item_codes(
        db._conn,
        [
            {
                "code": "SAVED-1",
                "description": "saved one",
                "item_type": "Service",
                "coa_account": "",
                "rate_value": 5.0,
                "rate_kind": "amount",
                "sort_order": 0,
            }
        ],
    )
    w = InvoiceCodesScreen(ap_conn=db._conn, coa_db=None)
    assert w.has_unsaved_edits() is False
    blank_cell = w._table.cellWidget(1, 0)
    assert isinstance(blank_cell, QLineEdit)
    blank_cell.setFocus()
    blank_cell.insert("DISCARD-ME")
    assert w.has_unsaved_edits() is True
    with patch.object(w, "_confirm_discard_unsaved_edits", return_value=True):
        w._on_reload_clicked()
    assert w.has_unsaved_edits() is False
    first = w._table.cellWidget(0, 0)
    assert isinstance(first, QLineEdit)
    assert first.text() == "SAVED-1", "Reload must show the saved row from the DB."
    second = w._table.cellWidget(1, 0)
    assert isinstance(second, QLineEdit)
    assert second.text() == "", "Reload must replace the unsaved typed-in text with a blank canvas row."
    db.close()


def test_invoice_codes_save_persists_all_fields_and_reload_restores_them(
    qapp: QApplication, tmp_path
) -> None:
    """All five fields per saved row round-trip through Save + Reload (master-table behavior)."""
    db_path = str(tmp_path / "codes_persist.db")
    db = BankDatabase(db_path)
    apply_extensions(db._conn)
    w = InvoiceCodesScreen(ap_conn=db._conn, coa_db=None)
    code_cell = w._table.cellWidget(0, 0)
    desc_cell = w._table.cellWidget(0, 1)
    type_cb = w._table.cellWidget(0, 2)
    rate_cell = w._table.cellWidget(0, 4)
    assert isinstance(code_cell, QLineEdit)
    assert isinstance(desc_cell, QLineEdit)
    assert isinstance(rate_cell, QLineEdit)
    code_cell.setText("FS-1")
    desc_cell.setText("Flat service one")
    type_cb.setCurrentIndex(type_cb.findText("Service"))
    rate_cell.setText("164.00")
    with patch("desktop_app.invoice_codes_screen.message_box_information_ok"):
        w._on_save()
    assert w.has_unsaved_edits() is False, "Save must clear the unsaved-edits flag."
    rows = list(business.list_invoice_item_codes(db._conn))
    assert any(
        dict(r)["code"] == "FS-1"
        and dict(r)["description"] == "Flat service one"
        and dict(r)["item_type"] == "Service"
        and float(dict(r)["rate_value"]) == 164.00
        and (dict(r)["rate_kind"] or "amount").lower() == "amount"
        for r in rows
    )
    w2 = InvoiceCodesScreen(ap_conn=db._conn, coa_db=None)
    first = w2._table.cellWidget(0, 0)
    assert isinstance(first, QLineEdit)
    assert first.text() == "FS-1", "Saved row must reappear on reopen/reload."
    db.close()


def test_invoice_codes_screen_collect_rows_save_does_not_raise_typeerror(
    qapp: QApplication, tmp_path
) -> None:
    """Regression: ``_collect_rows`` previously wrapped a chained ``and`` with ``all(...)``
    which raised ``TypeError: 'bool' object is not iterable`` on every Save click."""
    db_path = str(tmp_path / "codes_save.db")
    db = BankDatabase(db_path)
    apply_extensions(db._conn)
    w = InvoiceCodesScreen(ap_conn=db._conn, coa_db=None)
    code_cell = w._table.cellWidget(0, 0)
    desc_cell = w._table.cellWidget(0, 1)
    rate_cell = w._table.cellWidget(0, 4)
    assert isinstance(code_cell, QLineEdit)
    assert isinstance(desc_cell, QLineEdit)
    assert isinstance(rate_cell, QLineEdit)
    code_cell.setText("SVC-1")
    desc_cell.setText("Service one")
    rate_cell.setText("100")
    rows = w._collect_rows()
    assert any(r["code"] == "SVC-1" for r in rows), (
        "_collect_rows must yield typed-in rows without raising."
    )
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
