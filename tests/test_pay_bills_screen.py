"""Pay Bills screen — QB Pro Pay Bills layout and AP + BILLPMT posting."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QTableWidget,
)

from desktop_app.pay_bills_screen import (
    PayBillsScreen,
    REGISTER_BILLPMT_MEMO,
    discount_date_iso,
)
from desktop_app.qt_combo_ids import coerce_combo_int_id
from desktop_app.register_tab import _register_number_two_line_plain
from desktop_app.theme import BG_PRIMARY
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
def db(tmp_path: Path) -> BankDatabase:
    b = BankDatabase(db_path=str(tmp_path / "pay_bills_t.db"))
    apply_extensions(b._conn)
    yield b
    b.close()


def _select_bank(w: PayBillsScreen, bank_id: int) -> None:
    combo = w._account
    idx = next(
        (
            i
            for i in range(combo.count())
            if coerce_combo_int_id(combo.itemData(i)) == bank_id
        ),
        -1,
    )
    assert idx >= 0, f"bank {bank_id} not in Pay From"
    combo.setCurrentIndex(idx)


def test_discount_date_iso_ten_day_window() -> None:
    assert discount_date_iso("2026-08-01", "2026-08-31") == "2026-08-11"
    assert discount_date_iso("2026-08-01", "2026-08-05") == "2026-08-05"
    assert discount_date_iso("", "2026-08-20") == "2026-08-20"


def test_pay_bills_qb_header_grid_and_footer(qapp: QApplication) -> None:
    w = PayBillsScreen()
    labels = [lb.text() for lb in w.findChildren(QLabel)]
    assert "Pay Bills" in labels
    assert "SELECT BILLS TO BE PAID" in labels
    assert "FILTER BY VENDOR" in labels
    assert "SORT BILLS BY" in labels
    assert "A/P ACCOUNT" in labels
    assert "PAYMENT" in labels
    assert "PAY FROM" in labels
    assert "DATE" in labels
    assert "METHOD" in labels
    assert "ENDING BALANCE" in labels
    assert "CHECK NO." in labels
    assert "TOTALS FOR SELECTED BILLS" in labels

    btns = [b.text() for b in w.findChildren(QPushButton)]
    assert "Find" in btns
    assert "Clear Payments" in btns
    assert "Select All Bills" in btns
    assert "Pay Selected Bills" in btns
    assert "Print" in btns

    ribbon = w.findChild(QTabWidget, "payBillsRibbonTabs")
    assert ribbon is not None
    assert [ribbon.tabText(i) for i in range(ribbon.count())] == [
        "Main",
        "Reports",
        "Discounts",
    ]
    select_box = w.findChild(QFrame, "payBillsSelectBox")
    pay_box = w.findChild(QFrame, "payBillsPaymentBox")
    assert select_box is not None
    assert pay_box is not None
    assert "#1a1a2e" not in select_box.styleSheet().lower()
    assert "#1a1a2e" not in pay_box.styleSheet().lower()

    t = w.findChild(QTableWidget, "payBillsTable")
    assert t is not None
    assert t.columnCount() == 8
    assert t.horizontalHeaderItem(0).text() == "✓"
    assert t.horizontalHeaderItem(1).text() == "DATE"
    assert t.horizontalHeaderItem(2).text() == "REF. NO."
    assert t.horizontalHeaderItem(3).text() == "VENDOR"
    assert t.horizontalHeaderItem(4).text() == "DUE DATE"
    assert t.horizontalHeaderItem(5).text() == "DISC. DATE"
    assert t.horizontalHeaderItem(6).text() == "AMT. DUE"
    assert t.horizontalHeaderItem(7).text() == "AMT. TO PAY"
    assert t.rowCount() == 0

    wrap = w._account.parentWidget()
    assert wrap is not None
    assert wrap.objectName() == "payBillsMetaField"
    assert "#1a1a2e" not in wrap.styleSheet().lower()
    assert w._method.currentText() == "Check"
    assert w._chk_show_all.isChecked()
    assert w._ap_account.text() == "Accounts Payable"

    pal = w.palette()
    assert pal.color(QPalette.ColorRole.Window).name().lower() != BG_PRIMARY.lower()


def test_pay_bills_screen_table_columns_empty_without_db(qapp: QApplication) -> None:
    w = PayBillsScreen()
    t = w.findChild(QTableWidget, "payBillsTable")
    assert t is not None
    assert t.columnCount() == 8
    assert t.rowCount() == 0
    assert t.horizontalHeaderItem(3).text() == "VENDOR"
    assert t.horizontalHeaderItem(7).text() == "AMT. TO PAY"


def test_pay_bills_loads_open_bills(qapp: QApplication, db: BankDatabase) -> None:
    vid = business.add_vendor(db._conn, "Office Supplies Co")
    business.create_bill(
        db._conn,
        vid,
        "2024-06-15",
        100.0,
        vendor_invoice_number="INV-9",
        due_date="2024-07-01",
    )
    w = PayBillsScreen(ap_conn=db._conn, bank_db=db)
    t = w.findChild(QTableWidget, "payBillsTable")
    assert t is not None
    assert t.rowCount() == 1
    assert isinstance(t.cellWidget(0, 0), QCheckBox)
    assert isinstance(t.cellWidget(0, 7), QDoubleSpinBox)
    spin = t.cellWidget(0, 7)
    assert isinstance(spin, QDoubleSpinBox)
    assert spin.maximum() == pytest.approx(100.0)
    assert t.item(0, 2).text() == "INV-9"
    assert t.item(0, 3).text() == "Office Supplies Co"
    assert t.item(0, 5).text()  # discount date filled


def test_pay_bills_check_row_fills_amount_to_pay(qapp: QApplication, db: BankDatabase) -> None:
    vid = business.add_vendor(db._conn, "Fuel Vendor")
    business.create_bill(db._conn, vid, "2024-01-01", 40.0)
    w = PayBillsScreen(ap_conn=db._conn, bank_db=db)
    t = w.findChild(QTableWidget, "payBillsTable")
    assert t is not None
    cb = t.cellWidget(0, 0)
    spin = t.cellWidget(0, 7)
    assert isinstance(cb, QCheckBox)
    assert isinstance(spin, QDoubleSpinBox)
    cb.setChecked(True)
    assert spin.value() == pytest.approx(40.0)
    w._on_clear_selection()
    assert not cb.isChecked()
    assert spin.value() == 0.0


def test_pay_bills_clear_selection_resets(qapp: QApplication, db: BankDatabase) -> None:
    vid = business.add_vendor(db._conn, "Parts Co")
    business.create_bill(db._conn, vid, "2024-01-01", 25.0)
    w = PayBillsScreen(ap_conn=db._conn, bank_db=db)
    t = w.findChild(QTableWidget, "payBillsTable")
    assert t is not None
    cb = t.cellWidget(0, 0)
    spin = t.cellWidget(0, 7)
    assert isinstance(cb, QCheckBox)
    assert isinstance(spin, QDoubleSpinBox)
    cb.setChecked(True)
    spin.setValue(12.34)
    w._on_clear_selection()
    assert not cb.isChecked()
    assert spin.value() == 0.0


def test_pay_bills_post_updates_bill_balance_and_register_billpmt(
    qapp: QApplication, db: BankDatabase
) -> None:
    vid = business.add_vendor(db._conn, "Warehouse Supply")
    bid = business.create_bill(
        db._conn, vid, "2024-03-01", 80.0, vendor_invoice_number="B-1"
    )
    bank_id = db.add_bank_account("Checking")
    w = PayBillsScreen(ap_conn=db._conn, bank_db=db)
    t = w.findChild(QTableWidget, "payBillsTable")
    assert t is not None and t.rowCount() == 1
    cb = t.cellWidget(0, 0)
    spin = t.cellWidget(0, 7)
    assert isinstance(cb, QCheckBox) and isinstance(spin, QDoubleSpinBox)
    cb.setChecked(True)
    spin.setValue(80.0)
    _select_bank(w, bank_id)
    w._reference.setText("CHK-100")
    with patch("desktop_app.pay_bills_screen.message_box_information_ok"):
        w._on_pay_selected()
    row = db._conn.execute(
        "SELECT balance_due, status FROM bills WHERE id = ?", (bid,)
    ).fetchone()
    assert row is not None
    assert float(row["balance_due"]) <= 0.005
    assert (row["status"] or "") == "Paid"
    assert t.rowCount() == 0
    pay = db._conn.execute(
        "SELECT id, amount, reference, method, memo FROM ap_payments ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert pay is not None
    assert float(pay["amount"]) == pytest.approx(80.0)
    assert "CHK-100" in (pay["reference"] or "")
    assert (pay["method"] or "") == "Check"
    assert (pay["memo"] or "") == REGISTER_BILLPMT_MEMO
    txn = db._conn.execute(
        "SELECT amount, ref_number, memo, description FROM bank_transactions ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert txn is not None
    assert float(txn["amount"]) == pytest.approx(-80.0)
    assert (txn["ref_number"] or "") == "CHK-100"
    assert (txn["memo"] or "") == REGISTER_BILLPMT_MEMO
    assert (txn["description"] or "") == "Warehouse Supply"
    assert _register_number_two_line_plain(dict(txn)) == "CHK-100\nBILLPMT"
    assert w._btn_export_ap_pdf.isEnabled()
    assert w._btn_print_ap.isEnabled()
    assert len(w._last_ap_payment_ids) == 1


def test_pay_bills_partial_payment_keeps_bill_open(
    qapp: QApplication, db: BankDatabase
) -> None:
    vid = business.add_vendor(db._conn, "Repair Shop")
    bid = business.create_bill(db._conn, vid, "2024-04-01", 100.0)
    bank_id = db.add_bank_account("Checking")
    w = PayBillsScreen(ap_conn=db._conn, bank_db=db)
    t = w.findChild(QTableWidget, "payBillsTable")
    assert t is not None and t.rowCount() == 1
    cb = t.cellWidget(0, 0)
    spin = t.cellWidget(0, 7)
    assert isinstance(cb, QCheckBox) and isinstance(spin, QDoubleSpinBox)
    cb.setChecked(True)
    spin.setValue(40.0)
    _select_bank(w, bank_id)
    with patch("desktop_app.pay_bills_screen.message_box_information_ok"):
        w._on_pay_selected()
    row = db._conn.execute(
        "SELECT balance_due, status FROM bills WHERE id = ?", (bid,)
    ).fetchone()
    assert row is not None
    assert float(row["balance_due"]) == pytest.approx(60.0)
    assert (row["status"] or "") == "Partially Paid"
    assert t.rowCount() == 1
    assert t.item(0, 6).text() == "60.00"


def test_pay_bills_requires_pay_from_account(qapp: QApplication, db: BankDatabase) -> None:
    vid = business.add_vendor(db._conn, "No Bank Vendor")
    business.create_bill(db._conn, vid, "2024-03-01", 10.0)
    w = PayBillsScreen(ap_conn=db._conn, bank_db=db)
    t = w.findChild(QTableWidget, "payBillsTable")
    assert t is not None and t.rowCount() == 1
    cb = t.cellWidget(0, 0)
    assert isinstance(cb, QCheckBox)
    cb.setChecked(True)
    with patch("desktop_app.pay_bills_screen.message_box_warning_ok") as warn:
        w._on_pay_selected()
    warn.assert_called_once()
    still = db._conn.execute("SELECT COUNT(*) AS n FROM ap_payments").fetchone()
    assert int(still["n"]) == 0


def test_pay_bills_to_be_printed_sets_check_no(qapp: QApplication, db: BankDatabase) -> None:
    db.add_bank_account("Operating")
    w = PayBillsScreen(ap_conn=db._conn, bank_db=db)
    w._chk_to_print.setChecked(True)
    assert w._reference.text() == "To Print"
    assert w._reference.isReadOnly()
    w._chk_to_print.setChecked(False)
    assert w._reference.text() != "To Print"
    assert not w._reference.isReadOnly()
    assert isinstance(w._method, QComboBox)
    assert isinstance(w._reference, QLineEdit)


def test_pay_bills_filter_to_vendor(qapp: QApplication, db: BankDatabase) -> None:
    v1 = business.add_vendor(db._conn, "Office Supplies Co")
    v2 = business.add_vendor(db._conn, "Fuel Vendor")
    business.create_bill(db._conn, v1, "2024-06-01", 50.0, vendor_invoice_number="A")
    business.create_bill(db._conn, v2, "2024-06-02", 75.0, vendor_invoice_number="B")
    w = PayBillsScreen(ap_conn=db._conn, bank_db=db)
    t = w.findChild(QTableWidget, "payBillsTable")
    assert t is not None
    assert t.rowCount() == 2
    w.filter_to_vendor(v2)
    assert t.rowCount() == 1
    assert t.item(0, 3).text() == "Fuel Vendor"
    assert coerce_combo_int_id(w._vendor_filter.currentData()) == v2
