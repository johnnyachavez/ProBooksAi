"""Item List — QB Pro search row, columns, Edit Item dialog, invoice-line hook."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
)

from desktop_app.invoice_codes_screen import (
    EditItemDialog,
    InvoiceCodesScreen,
    _COL_NAME,
    _COL_PRICE,
    _COL_TYPE,
    _TYPE_HELP,
    format_rate_display,
    ordered_item_rows,
    parse_rate_input,
)
from probooksai import business
from probooksai.bank_import import BankDatabase
from probooksai.coa_db import COADatabase
from probooksai.extensions_schema import apply_extensions

_FORBIDDEN_QB = (
    "FS-1 LINX",
    "FS-EXT2",
    "WEIGHT",
    "BROKER",
    "PERMITS",
    "Trucking Income",
    "115.00",
)


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def db(tmp_path: Path) -> BankDatabase:
    b = BankDatabase(db_path=str(tmp_path / "items.db"))
    apply_extensions(b._conn)
    yield b
    b.close()


def _seed_generic(conn) -> None:
    business.replace_invoice_item_codes(
        conn,
        [
            {
                "code": "Hourly Labor",
                "description": "Standard hourly service",
                "item_type": "Service",
                "coa_account": "4000 – Sales Revenue",
                "rate_value": 85.0,
                "rate_kind": "amount",
                "sort_order": 0,
            },
            {
                "code": "Fuel Surcharge",
                "description": "Fuel surcharge",
                "item_type": "Other Charge",
                "coa_account": "4000 – Sales Revenue",
                "rate_value": 3.0,
                "rate_kind": "percent",
                "sort_order": 1,
            },
            {
                "code": "Early Pay Discount",
                "description": "Prompt-pay discount",
                "item_type": "Discount",
                "coa_account": "4000 – Sales Revenue",
                "rate_value": -10.0,
                "rate_kind": "percent",
                "sort_order": 2,
            },
            {
                "code": "Line Subtotal",
                "description": "Subtotal of items above",
                "item_type": "Subtotal",
                "coa_account": "",
                "rate_value": 0.0,
                "rate_kind": "amount",
                "sort_order": 3,
            },
        ],
    )


def test_parse_rate_amount_and_percent() -> None:
    assert parse_rate_input("85.00") == (85.0, "amount")
    assert parse_rate_input("3.0%") == (3.0, "percent")
    assert parse_rate_input("-10%")[0] == pytest.approx(-10.0)
    assert format_rate_display(-10.0, "percent") == "-10.0%"
    assert format_rate_display(85.0, "amount") == "85.00"


def test_item_list_qb_chrome(qapp: QApplication, db: BankDatabase) -> None:
    _seed_generic(db._conn)
    w = InvoiceCodesScreen(ap_conn=db._conn, coa_db=None)
    labels = [lb.text() for lb in w.findChildren(QLabel)]
    assert "Look for" in labels
    assert "Item List" in labels
    btns = [b.text() for b in w.findChildren(QPushButton)]
    assert "Search" in btns
    assert "Reset" in btns
    boxes = [cb.text() for cb in w.findChildren(QCheckBox)]
    assert "Search within results" in boxes
    field = w.findChild(QComboBox, "itemListSearchField")
    assert field is not None
    assert field.currentText() == "All fields"
    tbl = w.findChild(QTableWidget, "itemListTable")
    assert tbl is not None
    headers = [tbl.horizontalHeaderItem(i).text() for i in range(tbl.columnCount())]
    assert "NAME" in headers
    assert "DESCRIPTION" in headers
    assert "TYPE" in headers
    assert "ACCOUNT" in headers
    assert "PRICE" in headers
    assert "ATTACH" in headers
    types = {
        tbl.item(r, _COL_TYPE).text()
        for r in range(tbl.rowCount())
        if tbl.item(r, _COL_TYPE) is not None
    }
    assert "Service" in types
    assert "Discount" in types
    assert "Other Charge" in types
    assert "Subtotal" in types
    prices = {
        tbl.item(r, _COL_PRICE).text()
        for r in range(tbl.rowCount())
        if tbl.item(r, _COL_PRICE) is not None
    }
    assert "3.0%" in prices
    assert "-10.0%" in prices
    assert "85.00" in prices


def test_item_list_search_and_within_results(qapp: QApplication, db: BankDatabase) -> None:
    _seed_generic(db._conn)
    w = InvoiceCodesScreen(ap_conn=db._conn, coa_db=None)
    w._search.setText("Labor")
    w._on_search()
    assert w._table.rowCount() == 1
    assert "Labor" in w._table.item(0, _COL_NAME).text()
    w._chk_within.setChecked(True)
    w._search.setText("Hourly")
    w._on_search()
    assert w._table.rowCount() == 1
    w._search.setText("Discount")
    w._on_search()
    assert w._table.rowCount() == 0
    w._on_reset_search()
    assert w._table.rowCount() == 4


def test_item_list_search_field_type(qapp: QApplication, db: BankDatabase) -> None:
    _seed_generic(db._conn)
    w = InvoiceCodesScreen(ap_conn=db._conn, coa_db=None)
    w._field.setCurrentText("Type")
    w._search.setText("Discount")
    w._on_search()
    assert w._table.rowCount() == 1
    assert w._table.item(0, _COL_TYPE).text() == "Discount"


def test_double_click_opens_edit_item_dialog(qapp: QApplication, db: BankDatabase) -> None:
    _seed_generic(db._conn)
    w = InvoiceCodesScreen(ap_conn=db._conn, coa_db=None)
    w._table.selectRow(0)
    seen: list[str] = []

    def _fake_exec(self: EditItemDialog) -> int:
        seen.append(self.windowTitle())
        assert self.findChild(QComboBox, "editItemType") is not None
        return int(QDialog.DialogCode.Rejected)

    with patch.object(EditItemDialog, "exec", _fake_exec):
        w._on_row_double_clicked()
    assert seen
    assert seen[0] == "Edit Item"


def test_edit_item_dialog_service_layout(qapp: QApplication, db: BankDatabase) -> None:
    _seed_generic(db._conn)
    row = business.get_invoice_item_code_by_code(db._conn, "Hourly Labor")
    assert row is not None
    dlg = EditItemDialog(db._conn, item_id=int(row["id"]), coa_db=None)
    assert dlg.windowTitle() == "Edit Item"
    assert dlg._type.currentText() == "Service"
    assert _TYPE_HELP["Service"] in dlg._type_help.text()
    assert "subcontractor or partner" in dlg._chk_assemblies.text()
    assert dlg._chk_subitem.text() == "Subitem of"
    assert dlg._chk_inactive.text() == "Item is inactive"
    btns = [b.text() for b in dlg.findChildren(QPushButton)]
    for label in ("OK", "Cancel", "Notes", "Custom Fields", "Spelling"):
        assert label in btns
    assert dlg._name.text() == "Hourly Labor"
    assert dlg._rate.text() == "85.00"


def test_edit_item_save_updates_list_and_invoice_codes(
    qapp: QApplication, db: BankDatabase
) -> None:
    _seed_generic(db._conn)
    w = InvoiceCodesScreen(ap_conn=db._conn, coa_db=None)
    dlg = w._make_edit_dialog(None)
    assert dlg is not None
    dlg._name.setText("Weekend Labor")
    dlg._description.setPlainText("After-hours service")
    dlg._type.setCurrentText("Service")
    dlg._rate.setText("125.00")
    dlg._on_ok()
    w._load_from_db()
    names = [
        w._table.item(r, _COL_NAME).text().strip()
        for r in range(w._table.rowCount())
        if w._table.item(r, _COL_NAME) is not None
    ]
    assert "Weekend Labor" in names
    assert "Weekend Labor" in business.list_invoice_item_code_strings(db._conn)
    row = business.get_invoice_item_code_by_code(db._conn, "Weekend Labor")
    assert row is not None
    assert float(row["rate_value"]) == pytest.approx(125.0)
    assert (row["description"] or "").strip() == "After-hours service"


def test_edit_item_percent_rate_and_account_combo(
    qapp: QApplication, db: BankDatabase
) -> None:
    coa = COADatabase(db._conn)
    coa.add_account("4000", "Sales Revenue", "income")
    coa.add_account("1000", "Cash – Checking", "bank")
    dlg = EditItemDialog(db._conn, item_id=None, coa_db=coa)
    dlg._name.setText("Fuel Surcharge")
    dlg._type.setCurrentText("Other Charge")
    dlg._rate.setText("3.0%")
    labels = [dlg._account.itemText(i) for i in range(dlg._account.count())]
    assert any("Sales Revenue" in x for x in labels)
    assert not any("Cash" in x and "Checking" in x for x in labels)
    dlg._account.setCurrentIndex(
        next(i for i, t in enumerate(labels) if "Sales Revenue" in t)
    )
    dlg._on_ok()
    row = business.get_invoice_item_code_by_code(db._conn, "Fuel Surcharge")
    assert row is not None
    assert (row["rate_kind"] or "") == "percent"
    assert float(row["rate_value"]) == pytest.approx(3.0)


def test_ordered_item_rows_indents_children(db: BankDatabase) -> None:
    parent = business.upsert_invoice_item_code(
        db._conn, {"code": "Labor", "item_type": "Service"}
    )
    business.upsert_invoice_item_code(
        db._conn,
        {"code": "Weekend Labor", "item_type": "Service", "parent_id": parent},
    )
    packed = ordered_item_rows(business.list_invoice_item_codes(db._conn))
    names = [(dict(r)["code"], d) for r, d in packed]
    assert ("Labor", 0) in names
    assert ("Weekend Labor", 1) in names
    assert names.index(("Weekend Labor", 1)) == names.index(("Labor", 0)) + 1


def test_make_inactive_hides_from_invoice_picker(
    qapp: QApplication, db: BankDatabase
) -> None:
    _seed_generic(db._conn)
    w = InvoiceCodesScreen(ap_conn=db._conn, coa_db=None)
    labor = business.get_invoice_item_code_by_code(db._conn, "Hourly Labor")
    assert labor is not None
    w._select_item_id(int(labor["id"]))
    w._on_make_inactive()
    assert "Hourly Labor" not in business.list_invoice_item_code_strings(db._conn)
    names = [
        w._table.item(r, _COL_NAME).text()
        for r in range(w._table.rowCount())
        if w._table.item(r, _COL_NAME) is not None
    ]
    assert not any("Hourly Labor" in n for n in names)


def test_capture_script_has_item_list_tabs() -> None:
    text = Path("scripts/capture_ui_screenshot.py").read_text(encoding="utf-8")
    assert "--tab items" in text
    assert "--tab edit-item" in text
    yml = Path(".github/workflows/ui-screenshot.yml").read_text(encoding="utf-8")
    assert "--tab items" in yml
    assert "--tab edit-item" in yml


def test_item_list_does_not_copy_real_qb_catalog() -> None:
    roots = [
        Path("desktop_app/invoice_codes_screen.py"),
        Path("scripts/capture_ui_screenshot.py"),
        Path("desktop_app/main.py"),
        Path("desktop_app/dashboard_tab.py"),
    ]
    for path in roots:
        text = path.read_text(encoding="utf-8")
        for name in _FORBIDDEN_QB:
            assert name not in text, f"{name!r} must not appear in {path}"
