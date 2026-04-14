"""Enter Bills screen — structure and vendor autofill (when DB connected)."""

from __future__ import annotations

import sys

import pytest
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
    assert "Bill" in labels
    assert "Vendor" in labels
    assert "Vendor Address" in labels
    assert "Expenses" not in labels

    btns = [b.text() for b in w.findChildren(QPushButton)]
    assert any("Save" in b and "Close" in b for b in btns)
    assert any("Save" in b and "New" in b for b in btns)
    assert "Clear" in btns


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
