"""Enter Bills screen — QB Pro layout, vendor autofill, and A/P bill persistence."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt, QDate, QSettings
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QTabWidget,
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


def _fill_first_expense(w: EnterBillsScreen, *, account: str, amount: float, memo: str, job: str) -> None:
    acct = w._table.cellWidget(0, 0)
    assert isinstance(acct, QComboBox)
    acct.setEditText(account)
    amt = w._table.cellWidget(0, 1)
    assert isinstance(amt, QDoubleSpinBox)
    amt.setValue(amount)
    memo_w = w._table.cellWidget(0, 2)
    assert isinstance(memo_w, QLineEdit)
    memo_w.setText(memo)
    job_w = w._table.cellWidget(0, 3)
    assert isinstance(job_w, QLineEdit)
    job_w.setText(job)


def test_enter_bills_screen_header_and_line_grid(qapp: QApplication) -> None:
    w = EnterBillsScreen()
    t = w.findChild(QTableWidget, "enterBillsExpensesTable")
    assert t is not None
    assert t.columnCount() == 5
    assert t.rowCount() == EnterBillsScreen._N_EXPENSE_ROWS
    assert t.horizontalHeaderItem(0).text() == "ACCOUNT"
    assert t.horizontalHeaderItem(1).text() == "AMOUNT"
    assert t.horizontalHeaderItem(2).text() == "MEMO"
    assert t.horizontalHeaderItem(3).text() == "CUSTOMER:JOB"
    assert t.horizontalHeaderItem(4).text() == "BILLABLE?"
    assert isinstance(t.cellWidget(0, 0), QComboBox)
    assert isinstance(t.cellWidget(0, 1), QDoubleSpinBox)
    assert isinstance(t.cellWidget(0, 2), QLineEdit)
    assert isinstance(t.cellWidget(0, 3), QLineEdit)
    assert isinstance(t.cellWidget(0, 4), QCheckBox)
    memo = t.cellWidget(0, 2)
    job = t.cellWidget(0, 3)
    assert isinstance(memo, QLineEdit) and isinstance(job, QLineEdit)
    assert (memo.placeholderText() or "").strip() == ""
    assert (job.placeholderText() or "").strip() == ""
    amt = t.cellWidget(0, 1)
    assert isinstance(amt, QDoubleSpinBox)
    assert amt.value() == 0.0
    assert (amt.specialValueText() or "").strip() == ""
    acct = t.cellWidget(0, 0)
    assert isinstance(acct, QComboBox)
    assert (acct.currentText() or "").strip() == ""
    assert "(select" not in (acct.itemText(0) or "").lower()

    items = w.findChild(QTableWidget, "enterBillsItemsTable")
    assert items is not None
    assert items.horizontalHeaderItem(0).text() == "ITEM"
    assert items.horizontalHeaderItem(6).text() == "BILLABLE?"
    item_desc = items.cellWidget(0, 1)
    item_job = items.cellWidget(0, 5)
    assert isinstance(item_desc, QLineEdit) and isinstance(item_job, QLineEdit)
    assert (item_desc.placeholderText() or "").strip() == ""
    assert (item_job.placeholderText() or "").strip() == ""
    item_cb = items.cellWidget(0, 0)
    assert isinstance(item_cb, QComboBox)
    assert (item_cb.currentText() or "").strip() == ""
    assert "(select" not in (item_cb.itemText(0) or "").lower()
    for col in (2, 3, 4):
        spin = items.cellWidget(0, col)
        assert isinstance(spin, QDoubleSpinBox)
        assert spin.value() == 0.0
        assert (spin.specialValueText() or "").strip() == ""

    labels = [lb.text() for lb in w.findChildren(QLabel)]
    assert "Bill" in labels
    assert "VENDOR" in labels
    assert "ADDRESS" in labels
    assert "DATE" in labels
    assert "REF. NO." in labels
    assert "AMOUNT DUE" in labels
    assert "BILL DUE" in labels
    assert "TERMS" in labels
    assert "MEMO" in labels

    radios = [r.text() for r in w.findChildren(QRadioButton)]
    assert "Bill" in radios
    assert "Credit" in radios
    assert w._radio_bill.isChecked()
    assert w._chk_received.isChecked()

    btns = [b.text() for b in w.findChildren(QPushButton)]
    assert any("Save" in b and "Close" in b for b in btns)
    assert any("Save" in b and "New" in b for b in btns)
    assert "Clear" in btns
    assert "Export PDF…" in btns
    assert "Print" in btns
    assert "Find" in btns
    assert "New" in btns
    assert "Pay Bill" in btns

    ribbon = w.findChild(QTabWidget, "enterBillsRibbonTabs")
    assert ribbon is not None
    assert [ribbon.tabText(i) for i in range(ribbon.count())] == ["Main", "Reports"]
    lines = w.findChild(QTabWidget, "enterBillsLineTabs")
    assert lines is not None
    assert lines.tabText(0).startswith("Expenses")
    assert lines.tabText(1).startswith("Items")
    assert t.rowCount() >= 18


def test_enter_bills_empty_line_cells_are_blank(qapp: QApplication) -> None:
    """Expenses/Items headers name the columns; empty cells have no hint text and no $0.00 filler."""
    w = EnterBillsScreen()
    w.show()
    qapp.processEvents()
    title = w.findChild(QLabel, "enterBillsTitle")
    assert title is not None
    assert "#1e4a78" not in title.styleSheet().lower()
    header = w.findChild(QFrame, "enterBillsHeaderBand")
    assert header is not None
    assert "#1e4a78" not in header.styleSheet().lower()
    t = w.findChild(QTableWidget, "enterBillsExpensesTable")
    assert t is not None
    amt = t.cellWidget(0, 1)
    assert isinstance(amt, QDoubleSpinBox)
    shown = (amt.lineEdit().text() if amt.lineEdit() is not None else amt.text()) or ""
    assert shown.strip() == ""
    assert "0.00" not in shown
    amt.setValue(9.5)
    qapp.processEvents()
    filled = (amt.lineEdit().text() if amt.lineEdit() is not None else amt.text()) or ""
    assert "9.50" in filled.replace(",", "")
    items = w.findChild(QTableWidget, "enterBillsItemsTable")
    assert items is not None
    qty = items.cellWidget(0, 2)
    cost = items.cellWidget(0, 3)
    item_amt = items.cellWidget(0, 4)
    assert isinstance(qty, QDoubleSpinBox)
    assert isinstance(cost, QDoubleSpinBox)
    assert isinstance(item_amt, QDoubleSpinBox)
    for spin in (qty, cost, item_amt):
        raw = (spin.lineEdit().text() if spin.lineEdit() is not None else spin.text()) or ""
        assert raw.strip() == ""
    w.close()


def test_enter_bills_grid_dominates_window_height(qapp: QApplication) -> None:
    """QB Pro proportions: header stays in the top third; Expenses grid fills the rest."""
    w = EnterBillsScreen()
    w.resize(1280, 860)
    w.show()
    qapp.processEvents()
    header = w.findChild(QFrame, "enterBillsHeaderBand")
    ribbon = w.findChild(QTabWidget, "enterBillsRibbonTabs")
    footer = w.findChild(QFrame, "enterBillsActionsBar")
    assert header is not None and ribbon is not None and footer is not None
    assert w._line_tabs.height() >= int(w.height() * 0.58)
    assert header.height() <= int(w.height() / 3)
    top_chrome = ribbon.height() + header.height()
    assert top_chrome <= int(w.height() / 3) + 36  # type-row + small gaps
    assert w._table.rowCount() == EnterBillsScreen._N_EXPENSE_ROWS
    assert w._table.alternatingRowColors() is True
    assert w._table.verticalHeader().isVisible() is False
    viewport_h = w._table.viewport().height()
    visible_rows = viewport_h // max(1, w._table.rowHeight(0))
    assert visible_rows >= 15
    w.close()


def test_enter_bills_clear_resets_rows(qapp: QApplication) -> None:
    w = EnterBillsScreen()
    _fill_first_expense(w, account="6100 Fuel", amount=9.99, memo="x", job="C:J")
    w._expense_billable[0].setChecked(True)
    w._radio_credit.setChecked(True)
    w._on_clear()
    acct = w._table.cellWidget(0, 0)
    assert isinstance(acct, QComboBox)
    assert (acct.currentText() or "").strip() == ""
    amt = w._table.cellWidget(0, 1)
    assert isinstance(amt, QDoubleSpinBox)
    assert amt.value() == 0.0
    memo = w._table.cellWidget(0, 2)
    assert isinstance(memo, QLineEdit)
    assert memo.text() == ""
    job = w._table.cellWidget(0, 3)
    assert isinstance(job, QLineEdit)
    assert job.text() == ""
    assert w._expense_billable[0].isChecked() is False
    assert w._radio_bill.isChecked()
    assert w._title.text() == "Bill"


def test_enter_bills_header_dates_use_us_qdate_edit(qapp: QApplication) -> None:
    """Bill date and due date are the same US QDateEdit as Create Invoices."""
    w = EnterBillsScreen()
    assert isinstance(w._bill_date, QDateEdit)
    assert w._bill_date.displayFormat() == "MM/dd/yyyy"
    assert w._bill_date.calendarPopup() is False
    w._bill_date.setDate(QDate(2026, 5, 21))
    assert w._bill_date.date() == QDate(2026, 5, 21)
    w._due_date.setDate(QDate(2027, 12, 3))
    assert w._due_date.date() == QDate(2027, 12, 3)


def test_enter_bills_terms_fill_bill_due(qapp: QApplication) -> None:
    w = EnterBillsScreen()
    w._bill_date.setDate(QDate(2026, 8, 26))
    idx = w._terms.findText("Net 30")
    assert idx >= 0
    w._terms.setCurrentIndex(idx)
    assert w._due_date.date() == QDate(2026, 9, 25)


def test_enter_bills_credit_radio_retitles_form(qapp: QApplication) -> None:
    w = EnterBillsScreen()
    assert w._title.text() == "Bill"
    w._radio_credit.setChecked(True)
    assert w._title.text() == "Credit"
    w._radio_bill.setChecked(True)
    assert w._title.text() == "Bill"


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
    business.add_vendor(db._conn, "SuppCo")
    w = EnterBillsScreen(ap_conn=db._conn)
    w._vendor.setCurrentIndex(1)
    w._vendor_inv.setText("INV-900")
    _fill_first_expense(w, account="6100 Fuel", amount=42.5, memo="Fuel", job="Job:A")
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
    assert (el[0]["ticket_ref"] or "").strip() == "6100 Fuel"
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
    acct = w._table.cellWidget(0, 0)
    assert isinstance(acct, QComboBox)
    assert (acct.currentText() or "").strip() == "R1"
    amt = w._table.cellWidget(0, 1)
    assert isinstance(amt, QDoubleSpinBox)
    assert abs(amt.value() - 10.0) < 0.01
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
    amt = w._table.cellWidget(0, 1)
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
    assert w._current_bill_id == bid
    db.close()


def test_enter_bills_no_hardcoded_live_vendor_or_ein(qapp: QApplication) -> None:
    """Defaults stay generic — no live company / vendor / EIN baked into the form."""
    from pathlib import Path

    w = EnterBillsScreen()
    assert w._vendor.currentData() is None
    assert w._vendor.currentText() == ""
    assert w._vendor_inv.text() == ""
    assert w._address.toPlainText().strip() == ""
    text = Path("desktop_app/enter_bills_screen.py").read_text(encoding="utf-8")
    lowered = text.lower()
    assert "chavan" not in lowered
    assert "xx-xxxxxxx" not in lowered

