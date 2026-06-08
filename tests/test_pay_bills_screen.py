"""Pay Bills screen — open bills from company DB and AP posting."""

from __future__ import annotations

import sys

import pytest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QCheckBox, QDoubleSpinBox, QTableWidget

from desktop_app.pay_bills_screen import PayBillsScreen
from probooksai import business
from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import apply_extensions


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def db(tmp_path):
    b = BankDatabase(db_path=str(tmp_path / "pay_bills_t.db"))
    apply_extensions(b._conn)
    yield b
    b.close()


def test_pay_bills_screen_table_columns_empty_without_db(qapp: QApplication) -> None:
    w = PayBillsScreen()
    t = w.findChild(QTableWidget)
    assert t is not None
    assert t.columnCount() == 7
    assert t.rowCount() == 0
    assert t.horizontalHeaderItem(1).text() == "Vendor"
    assert t.horizontalHeaderItem(6).text() == "Amount to Pay"


def test_pay_bills_loads_open_bills(qapp: QApplication, db: BankDatabase) -> None:
    vid = business.add_vendor(db._conn, "Acme Supply")
    business.create_bill(
        db._conn,
        vid,
        "2024-06-15",
        100.0,
        vendor_invoice_number="INV-9",
        due_date="2024-07-01",
    )
    w = PayBillsScreen(ap_conn=db._conn, bank_db=db)
    t = w.findChild(QTableWidget)
    assert t is not None
    assert t.rowCount() == 1
    assert isinstance(t.cellWidget(0, 0), QCheckBox)
    assert isinstance(t.cellWidget(0, 6), QDoubleSpinBox)
    spin = t.cellWidget(0, 6)
    assert isinstance(spin, QDoubleSpinBox)
    assert spin.maximum() == pytest.approx(100.0)


def test_pay_bills_clear_selection_resets(qapp: QApplication, db: BankDatabase) -> None:
    vid = business.add_vendor(db._conn, "V")
    business.create_bill(db._conn, vid, "2024-01-01", 25.0)
    w = PayBillsScreen(ap_conn=db._conn, bank_db=db)
    t = w.findChild(QTableWidget)
    assert t is not None
    cb = t.cellWidget(0, 0)
    spin = t.cellWidget(0, 6)
    assert isinstance(cb, QCheckBox)
    assert isinstance(spin, QDoubleSpinBox)
    cb.setChecked(True)
    spin.setValue(12.34)
    w._on_clear_selection()
    assert not cb.isChecked()
    assert spin.value() == 0.0


def test_pay_bills_post_updates_bill_balance(qapp: QApplication, db: BankDatabase) -> None:
    vid = business.add_vendor(db._conn, "Payee")
    bid = business.create_bill(db._conn, vid, "2024-03-01", 80.0, vendor_invoice_number="B-1")
    bank_id = db.add_bank_account("Checking")
    w = PayBillsScreen(ap_conn=db._conn, bank_db=db)
    t = w.findChild(QTableWidget)
    assert t is not None and t.rowCount() == 1
    cb = t.cellWidget(0, 0)
    spin = t.cellWidget(0, 6)
    assert isinstance(cb, QCheckBox) and isinstance(spin, QDoubleSpinBox)
    cb.setChecked(True)
    spin.setValue(80.0)
    idx = w._account.findData(bank_id)
    assert idx >= 0
    w._account.setCurrentIndex(idx)
    w._reference.setText("CHK-100")
    with patch("desktop_app.pay_bills_screen.message_box_information_ok"):
        w._on_pay_selected()
    row = db._conn.execute(
        "SELECT balance_due, status FROM bills WHERE id = ?", (bid,)
    ).fetchone()
    assert row is not None
    assert float(row["balance_due"]) <= 0.005
    assert (row["status"] or "") == "Paid"
    pay = db._conn.execute(
        "SELECT id, amount, reference FROM ap_payments ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert pay is not None
    assert float(pay["amount"]) == pytest.approx(80.0)
    assert "CHK-100" in (pay["reference"] or "")
    txn = db._conn.execute(
        "SELECT amount, ref_number FROM bank_transactions ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert txn is not None
    assert float(txn["amount"]) == pytest.approx(-80.0)
    assert w._btn_export_ap_pdf.isEnabled()
    assert w._btn_print_ap.isEnabled()
    assert len(w._last_ap_payment_ids) == 1
