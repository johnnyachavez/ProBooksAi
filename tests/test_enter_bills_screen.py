"""Enter Bills screen — structure, vendor autofill, and A/P bill persistence."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import (
    QApplication,
    QDoubleSpinBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
)

from desktop_app.enter_bills_screen import EnterBillsScreen
from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import apply_extensions
from probooksai import business


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_enter_bills_screen_header_and_line_grid(qapp: QApplication) -> None:
    w = EnterBillsScreen()
    t = w.findChild(QTableWidget)
    assert t is not None
    assert t.objectName() == "enterBillsExpensesTable"
    assert t.columnCount() == 5
    assert t.rowCount() == EnterBillsScreen._N_EXPENSE_ROWS
    assert t.horizontalHeaderItem(0).text() == "Date"
    assert t.horizontalHeaderItem(1).text() == "Ticket Number"
    assert t.horizontalHeaderItem(2).text() == "Dollar Amount"
    assert t.horizontalHeaderItem(3).text() == "Memo"
    assert t.horizontalHeaderItem(4).text() == "Customer:Job"
    assert isinstance(t.cellWidget(0, 0), QLineEdit)
    assert isinstance(t.cellWidget(0, 1), QLineEdit)
    assert isinstance(t.cellWidget(0, 2), QDoubleSpinBox)
    assert isinstance(t.cellWidget(0, 4), QLineEdit)

    labels = [lb.text() for lb in w.findChildren(QLabel)]
    assert "Enter Bills" in labels
    assert "Vendor" in labels
    assert "Vendor Address" in labels
    assert "Bill date" in labels
    assert "Vendor invoice #" in labels
    assert "Expenses" not in labels

    btns = [b.text() for b in w.findChildren(QPushButton)]
    assert any("Save" in b and "Close" in b for b in btns)
    assert any("Save" in b and "New" in b for b in btns)
    assert "Clear" in btns
    assert "Export PDF…" in btns
    assert "Print…" in btns


def test_enter_bills_clear_resets_rows(qapp: QApplication) -> None:
    w = EnterBillsScreen()
    t = w.findChild(QTableWidget)
    assert t is not None
    memo = t.item(0, 3)
    assert memo is not None
    memo.setText("x")
    dt = t.cellWidget(0, 0)
    assert isinstance(dt, QLineEdit)
    dt.setText("1/1/26")
    ticket = t.cellWidget(0, 1)
    assert isinstance(ticket, QLineEdit)
    ticket.setText("T-9")
    amt = t.cellWidget(0, 2)
    assert isinstance(amt, QDoubleSpinBox)
    amt.setValue(9.99)
    job = t.cellWidget(0, 4)
    assert isinstance(job, QLineEdit)
    job.setText("C:J")
    w._on_clear()
    assert memo.text() == ""
    assert dt.text() == ""
    assert ticket.text() == ""
    assert amt.value() == 0.0
    assert job.text() == ""


def test_enter_bills_vendor_selection_fills_address(qapp: QApplication, tmp_path) -> None:
    db_path = tmp_path / "enter_bills_vendors.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    business.add_vendor(
        db._conn,
        "Acme Supply",
        email="ap@acme.test",
        phone="555-0100",
        address="100 Main St\nSpringfield",
    )
    w = EnterBillsScreen(ap_conn=db._conn)
    assert w._vendor.count() >= 2
    w._vendor.setCurrentIndex(1)
    text = w._address.toPlainText()
    assert "100 Main St" in text
    assert "ap@acme.test" in text
    assert "555-0100" in text
    w._vendor.setCurrentIndex(0)
    assert w._address.toPlainText().strip() == ""
    db.close()


def test_enter_bills_save_persists_bill_and_expense_lines(
    qapp: QApplication, tmp_path
) -> None:
    db_path = tmp_path / "enter_bills_save.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    pdf_dir = tmp_path / "bill_pdf_out"
    pdf_dir.mkdir()
    QSettings("ProBooks+ai", "ProBooks+ai").setValue(
        "bill_prefs/output_folder", str(pdf_dir)
    )
    vid = business.add_vendor(db._conn, "SuppCo")
    w = EnterBillsScreen(ap_conn=db._conn)
    w._vendor.setCurrentIndex(1)
    w._vendor_inv.setText("INV-900")
    dt = w._table.cellWidget(0, 0)
    assert isinstance(dt, QLineEdit)
    dt.setText("01/15/2025")
    tk = w._table.cellWidget(0, 1)
    assert isinstance(tk, QLineEdit)
    tk.setText("TK-1")
    amt = w._table.cellWidget(0, 2)
    assert isinstance(amt, QDoubleSpinBox)
    amt.setValue(42.5)
    memo = w._table.item(0, 3)
    assert memo is not None
    memo.setText("Fuel")
    job = w._table.cellWidget(0, 4)
    assert isinstance(job, QLineEdit)
    job.setText("Job:A")
    QTest.mouseClick(w._btn_save_new, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    rows = business.list_bills(db._conn)
    assert len(rows) == 1
    bid = int(rows[0]["id"])
    assert float(rows[0]["total"]) == 42.5
    assert (rows[0]["vendor_invoice_number"] or "").strip() == "INV-900"
    el = business.list_bill_expense_lines(db._conn, bid)
    assert len(el) == 1
    assert abs(float(el[0]["amount"]) - 42.5) < 0.01
    assert "Fuel" in (el[0]["memo"] or "")
    assert w._current_bill_id is None
    assert (pdf_dir / "Bill-INV-900.pdf").is_file()
    db.close()


def test_enter_bills_open_bill_by_id_loads_form(qapp: QApplication, tmp_path) -> None:
    db_path = tmp_path / "enter_bills_open.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    vid = business.add_vendor(db._conn, "VOpen")
    lines = [
        {
            "line_date": "2025-02-01",
            "ticket_ref": "R1",
            "amount": 10.0,
            "memo": "m1",
            "customer_job": "C:J",
        }
    ]
    bid = business.create_bill(
        db._conn,
        vid,
        "2025-02-01",
        0.0,
        vendor_invoice_number="B-REF",
        memo="hdr",
        expense_lines=lines,
    )
    w = EnterBillsScreen(ap_conn=db._conn)
    ok = w.open_bill_by_id(bid)
    assert ok is True
    assert w._current_bill_id == bid
    assert w._vendor_inv.text() == "B-REF"
    assert w._header_memo.text() == "hdr"
    assert (w._table.cellWidget(0, 1).text() or "").strip() == "R1"
    assert abs(w._table.cellWidget(0, 2).value() - 10.0) < 0.01
    db.close()


def test_get_bill_id_by_vendor_invoice_number(qapp: QApplication, tmp_path) -> None:
    db_path = tmp_path / "bill_by_vin.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    v1 = business.add_vendor(db._conn, "V1")
    v2 = business.add_vendor(db._conn, "V2")
    b1 = business.create_bill(
        db._conn,
        v1,
        "2025-01-01",
        0.0,
        vendor_invoice_number="PO-77",
        expense_lines=[
            {
                "line_date": "",
                "ticket_ref": "",
                "amount": 5.0,
                "memo": "a",
                "customer_job": "",
            }
        ],
    )
    b2 = business.create_bill(
        db._conn,
        v2,
        "2025-01-02",
        0.0,
        vendor_invoice_number="PO-77",
        expense_lines=[
            {
                "line_date": "",
                "ticket_ref": "",
                "amount": 6.0,
                "memo": "b",
                "customer_job": "",
            }
        ],
    )
    assert business.get_bill_id_by_vendor_invoice_number(db._conn, "PO-77") is None
    assert business.get_bill_id_by_vendor_invoice_number(
        db._conn, "PO-77", vendor_id=v1
    ) == b1
    assert (
        business.get_bill_id_by_vendor_invoice_number(db._conn, "  PO-77  ", vendor_id=v2)
        == b2
    )
    db.close()


def test_get_bill_id_by_vendor_invoice_number_unique_globally(qapp: QApplication, tmp_path) -> None:
    db_path = tmp_path / "bill_vin_unique.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    v = business.add_vendor(db._conn, "OnlyV")
    sole = business.create_bill(
        db._conn,
        v,
        "2025-01-01",
        0.0,
        vendor_invoice_number="UNIQUE-REF",
        expense_lines=[
            {
                "line_date": "",
                "ticket_ref": "",
                "amount": 1.0,
                "memo": "",
                "customer_job": "",
            }
        ],
    )
    assert business.get_bill_id_by_vendor_invoice_number(db._conn, "UNIQUE-REF") == sole
    db.close()


def test_enter_bills_open_bill_by_vendor_invoice_number(qapp: QApplication, tmp_path) -> None:
    db_path = tmp_path / "enter_bills_open_vin.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    vid = business.add_vendor(db._conn, "VOpen2")
    bid = business.create_bill(
        db._conn,
        vid,
        "2025-04-01",
        0.0,
        vendor_invoice_number="REF-ZZ",
        expense_lines=[
            {
                "line_date": "",
                "ticket_ref": "",
                "amount": 12.0,
                "memo": "z",
                "customer_job": "",
            }
        ],
    )
    w = EnterBillsScreen(ap_conn=db._conn)
    assert w.open_bill_by_vendor_invoice_number("REF-ZZ", vendor_id=vid) is True
    assert w._current_bill_id == bid
    assert w._vendor_inv.text() == "REF-ZZ"
    with patch("desktop_app.enter_bills_screen.message_box_information_ok"):
        assert w.open_bill_by_vendor_invoice_number("missing", vendor_id=vid) is False
    db.close()


def test_enter_bills_edit_resaves_same_bill(qapp: QApplication, tmp_path) -> None:
    db_path = tmp_path / "enter_bills_edit.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    pdf_dir = tmp_path / "bill_pdf_edit"
    pdf_dir.mkdir()
    QSettings("ProBooks+ai", "ProBooks+ai").setValue(
        "bill_prefs/output_folder", str(pdf_dir)
    )
    vid = business.add_vendor(db._conn, "VEdit")
    bid = business.create_bill(
        db._conn,
        vid,
        "2025-03-01",
        0.0,
        vendor_invoice_number="E-1",
        expense_lines=[
            {
                "line_date": "",
                "ticket_ref": "",
                "amount": 25.0,
                "memo": "Line",
                "customer_job": "",
            }
        ],
    )
    w = EnterBillsScreen(ap_conn=db._conn)
    assert w.open_bill_by_id(bid)
    amt = w._table.cellWidget(0, 2)
    assert isinstance(amt, QDoubleSpinBox)
    amt.setValue(99.0)
    QTest.mouseClick(w._btn_save_close, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert len(business.list_bills(db._conn)) == 1
    b = business.get_bill(db._conn, bid)
    assert b is not None
    assert float(b["total"]) == 99.0
    el = business.list_bill_expense_lines(db._conn, bid)
    assert len(el) == 1
    assert float(el[0]["amount"]) == 99.0
    assert (pdf_dir / "Bill-E-1.pdf").is_file()
    db.close()
