"""Income Tracker and Bill Tracker screens — QB Pro chrome, live data, navigation hooks."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QLabel,
    QTableWidget,
    QToolButton,
)

from desktop_app.enter_bills_screen import EnterBillsScreen
from desktop_app.invoice_screen import InvoiceScreen
from desktop_app.pay_bills_screen import PayBillsScreen
from desktop_app.receive_checks_screen import ReceiveChecksScreen
from desktop_app.tracker_screens import BillTrackerScreen, IncomeTrackerScreen
from probooksai import business
from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import apply_extensions

_FORBIDDEN = (
    "BST LINEHAUL",
    "ANVIL STEEL",
    "Hofer Corporation",
    "AR TRUCKING",
    "947161.35",
    "947,161.35",
)


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def db(tmp_path: Path) -> BankDatabase:
    b = BankDatabase(db_path=str(tmp_path / "tracker_ui.db"))
    apply_extensions(b._conn)
    yield b
    b.close()


def _seed(conn) -> dict[str, int]:
    cid = business.add_customer(conn, "Harbor Logistics")
    open_inv = business.create_invoice(
        conn,
        cid,
        "INV-2101",
        "2026-08-10",
        due_date="2026-09-10",
        lines=[{"description": "Haul", "qty": 1, "rate": 400.00}],
    )
    overdue_inv = business.create_invoice(
        conn,
        cid,
        "INV-0888",
        "2026-06-01",
        due_date="2026-07-01",
        lines=[{"description": "Haul", "qty": 1, "rate": 150.00}],
    )
    vid = business.add_vendor(conn, "Office Supplies Co")
    open_bill = business.create_bill(
        conn, vid, "2026-08-01", 450.00, vendor_invoice_number="OS-1042", due_date="2026-09-01"
    )
    overdue_bill = business.create_bill(
        conn, vid, "2026-06-15", 96.40, vendor_invoice_number="OS-12", due_date="2026-07-15"
    )
    return {
        "customer": cid,
        "open_inv": open_inv,
        "overdue_inv": overdue_inv,
        "vendor": vid,
        "open_bill": open_bill,
        "overdue_bill": overdue_bill,
    }


def test_income_tracker_qb_chrome_and_live_totals(qapp: QApplication, db: BankDatabase) -> None:
    ids = _seed(db._conn)
    w = IncomeTrackerScreen(ap_conn=db._conn)
    labels = [lb.text() for lb in w.findChildren(QLabel)]
    assert "Income Tracker" in labels
    assert "UNBILLED" in labels
    assert "UNPAID" in labels
    assert "PAID" in labels
    assert "CUSTOMER:JOB" in labels
    assert "TYPE" in labels
    assert "STATUS" in labels
    assert "DATE" in labels
    assert any("TIME & EXPENSES" in t for t in labels)
    assert any("OPEN INVOICES" in t for t in labels)
    assert any("OVERDUE" in t for t in labels)
    assert any("PAID LAST 30 DAYS" in t for t in labels)

    tbl = w.findChild(QTableWidget, "incomeTrackerTable")
    assert tbl is not None
    assert tbl.columnCount() == 11
    assert tbl.horizontalHeaderItem(1).text() == "CUSTOMER"
    assert tbl.horizontalHeaderItem(2).text() == "TYPE"
    assert tbl.horizontalHeaderItem(8).text() == "LAST SENT DATE"
    assert tbl.horizontalHeaderItem(10).text() == "ACTION"
    assert tbl.rowCount() >= 2
    types = {tbl.item(i, 2).text() for i in range(tbl.rowCount()) if tbl.item(i, 2)}
    assert "Invoice" in types
    statuses = {tbl.item(i, 9).text() for i in range(tbl.rowCount()) if tbl.item(i, 9)}
    assert "Overdue" in statuses
    assert "Open" in statuses

    assert w.findChild(QComboBox, "incomeTrackerCustomer") is not None
    assert w.findChild(QToolButton, "trackerBatchActions") is not None
    assert w.findChild(QToolButton, "trackerManageTransactions") is not None
    showing = w.findChild(QLabel, "trackerShowingCount")
    assert showing is not None
    assert "Showing" in showing.text()

    opened: list[int] = []
    w.openInvoiceRequested.connect(opened.append)
    w._open_row({"kind": "invoice", "record_id": ids["open_inv"]})
    assert opened == [ids["open_inv"]]
    w.close()


def test_income_tracker_filters_and_overdue_tile(qapp: QApplication, db: BankDatabase) -> None:
    _seed(db._conn)
    w = IncomeTrackerScreen(ap_conn=db._conn)
    tbl = w.findChild(QTableWidget, "incomeTrackerTable")
    assert tbl is not None
    before = tbl.rowCount()
    w._tile_overdue.clicked.emit("overdue")
    qapp.processEvents()
    assert tbl.rowCount() >= 1
    assert tbl.rowCount() <= before
    for i in range(tbl.rowCount()):
        assert tbl.item(i, 9).text() == "Overdue"
    type_cb = w.findChild(QComboBox, "incomeTrackerType")
    type_cb.setCurrentText("Payment")
    qapp.processEvents()
    w.close()


def test_income_tracker_double_click_follows_sorted_row(qapp: QApplication, db: BankDatabase) -> None:
    """Column sort must not open the wrong invoice (visual row != insert order)."""
    from PySide6.QtCore import Qt

    ids = _seed(db._conn)
    w = IncomeTrackerScreen(ap_conn=db._conn)
    tbl = w.findChild(QTableWidget, "incomeTrackerTable")
    assert tbl is not None
    tbl.sortItems(4, Qt.SortOrder.AscendingOrder)
    qapp.processEvents()
    opened: list[int] = []
    w.openInvoiceRequested.connect(opened.append)
    target = None
    for i in range(tbl.rowCount()):
        num = tbl.item(i, 3)
        if num is not None and num.text() == "INV-0888":
            target = i
            break
    assert target is not None
    w._on_row_double_clicked(tbl.model().index(target, 1))
    qapp.processEvents()
    assert opened == [ids["overdue_inv"]]
    w.close()


def test_bill_tracker_qb_chrome_and_pay_bill_action(qapp: QApplication, db: BankDatabase) -> None:
    ids = _seed(db._conn)
    w = BillTrackerScreen(ap_conn=db._conn)
    labels = [lb.text() for lb in w.findChildren(QLabel)]
    assert "Bill Tracker" in labels
    assert "UNPAID" in labels
    assert "PAID" in labels
    assert "VENDOR" in labels
    assert "GROUP BY" in labels
    assert any("OPEN BILLS" in t for t in labels)
    assert any("PAID IN LAST 30 DAYS" in t for t in labels)

    tbl = w.findChild(QTableWidget, "billTrackerTable")
    assert tbl is not None
    assert tbl.columnCount() == 10
    assert tbl.horizontalHeaderItem(1).text() == "VENDOR"
    assert tbl.horizontalHeaderItem(6).text() == "STATUS"
    assert tbl.horizontalHeaderItem(9).text() == "ACTION"
    assert tbl.rowCount() >= 2
    types = {tbl.item(i, 2).text() for i in range(tbl.rowCount()) if tbl.item(i, 2)}
    assert "Bill" in types

    pay_btns = [
        b for b in w.findChildren(QToolButton) if b.text() == "Pay Bill"
    ]
    assert pay_btns

    paid: list[int] = []
    opened: list[int] = []
    w.payBillRequested.connect(paid.append)
    w.openBillRequested.connect(opened.append)
    w._open_row({"kind": "bill", "record_id": ids["open_bill"]})
    assert opened == [ids["open_bill"]]
    pay_btns[0].click()
    qapp.processEvents()
    assert paid
    w.close()


def test_bill_tracker_group_by_vendor(qapp: QApplication, db: BankDatabase) -> None:
    business.add_vendor(db._conn, "Office Supplies Co")
    v2 = business.add_vendor(db._conn, "Warehouse Supply")
    business.create_bill(db._conn, v2, "2026-08-01", 10.0, vendor_invoice_number="W-1")
    _seed(db._conn)
    w = BillTrackerScreen(ap_conn=db._conn)
    group = w.findChild(QComboBox, "billTrackerGroupBy")
    assert group is not None
    group.setCurrentText("Vendor")
    qapp.processEvents()
    tbl = w.findChild(QTableWidget, "billTrackerTable")
    assert tbl is not None
    assert tbl.rowCount() >= 2
    w.close()


def test_empty_trackers_show_zero_tiles(qapp: QApplication, db: BankDatabase) -> None:
    inc = IncomeTrackerScreen(ap_conn=db._conn)
    assert inc._tile_unbilled._amount.text() == "0.00"
    assert inc._tile_open._amount.text() == "0.00"
    tbl = inc.findChild(QTableWidget, "incomeTrackerTable")
    assert tbl is not None
    assert tbl.rowCount() == 0
    bills = BillTrackerScreen(ap_conn=db._conn)
    assert bills._tile_open._amount.text() == "0.00"
    assert bills._tile_overdue._amount.text() == "0.00"
    assert bills._tile_paid._amount.text() == "0.00"
    empty = bills.findChild(QLabel, "billTrackerEmptyHeadline")
    assert empty is not None
    assert empty.text() == "No bills"
    assert not bills.findChild(QFrame, "billTrackerEmptyState").isHidden()
    grid = bills.findChild(QTableWidget, "billTrackerTable")
    assert grid is not None
    assert grid.rowCount() == 0
    assert grid.isHidden()
    inc.close()
    bills.close()


def test_bill_tracker_filters_vendor_type_status_date(
    qapp: QApplication, db: BankDatabase
) -> None:
    ids = _seed(db._conn)
    v2 = business.add_vendor(db._conn, "Warehouse Supply")
    business.create_bill(
        db._conn, v2, "2026-08-02", 25.00, vendor_invoice_number="W-9", due_date="2026-09-02"
    )
    w = BillTrackerScreen(ap_conn=db._conn)
    tbl = w.findChild(QTableWidget, "billTrackerTable")
    assert tbl is not None
    assert not tbl.isHidden()
    assert w.findChild(QFrame, "billTrackerEmptyState").isHidden()
    all_count = tbl.rowCount()
    assert all_count >= 3

    vendor_cb = w.findChild(QComboBox, "billTrackerVendor")
    vendor_cb.setCurrentIndex(1)
    qapp.processEvents()
    vendor_rows = {
        tbl.item(i, 1).text()
        for i in range(tbl.rowCount())
        if tbl.item(i, 1) is not None
    }
    assert len(vendor_rows) == 1
    assert tbl.rowCount() < all_count

    vendor_cb.setCurrentIndex(0)
    status_cb = w.findChild(QComboBox, "billTrackerStatus")
    status_cb.setCurrentText("Overdue")
    qapp.processEvents()
    assert tbl.rowCount() >= 1
    for i in range(tbl.rowCount()):
        assert tbl.item(i, 6).text() == "Overdue"

    status_cb.setCurrentText("All")
    type_cb = w.findChild(QComboBox, "billTrackerType")
    type_cb.setCurrentText("Bill")
    qapp.processEvents()
    assert tbl.rowCount() >= 2
    for i in range(tbl.rowCount()):
        assert tbl.item(i, 2).text() == "Bill"

    date_cb = w.findChild(QComboBox, "billTrackerDate")
    date_cb.setCurrentText("This Month")
    qapp.processEvents()
    month_count = tbl.rowCount()
    date_cb.setCurrentText("Today")
    qapp.processEvents()
    assert tbl.rowCount() <= month_count
    if tbl.rowCount() == 0:
        assert w.findChild(QLabel, "billTrackerEmptyHeadline").text() == "No bills"
        assert not w.findChild(QFrame, "billTrackerEmptyState").isHidden()
    w.close()
    assert ids["open_bill"] > 0


def test_tracker_screens_have_no_screenshot_company_data() -> None:
    text = Path("desktop_app/tracker_screens.py").read_text(encoding="utf-8")
    lowered = text.lower()
    for needle in _FORBIDDEN:
        assert needle.lower() not in lowered
    assert "COMPANY NAME" not in text


def test_main_window_trackers_open_existing_screens(
    qapp: QApplication, tmp_path: Path
) -> None:
    from desktop_app.main import MainWindow

    db_path = tmp_path / "tracker_nav.db"
    b = BankDatabase(str(db_path))
    apply_extensions(b._conn)
    ids = _seed(b._conn)
    b.close()
    w = MainWindow(db_path=str(db_path))
    try:
        tabs = w._tabs
        assert isinstance(tabs.widget(1), IncomeTrackerScreen)
        assert isinstance(tabs.widget(2), BillTrackerScreen)
        inc = w._income_tracker_screen
        bills = w._bill_tracker_screen
        inc.openInvoiceRequested.emit(ids["open_inv"])
        qapp.processEvents()
        assert isinstance(tabs.currentWidget(), InvoiceScreen)
        bills.openBillRequested.emit(ids["open_bill"])
        qapp.processEvents()
        assert isinstance(tabs.currentWidget(), EnterBillsScreen)
        bills.payBillRequested.emit(ids["open_bill"])
        qapp.processEvents()
        assert isinstance(tabs.currentWidget(), PayBillsScreen)
        inc.receivePaymentRequested.emit(ids["open_inv"])
        qapp.processEvents()
        assert isinstance(tabs.currentWidget(), ReceiveChecksScreen)
    finally:
        w.close()


def test_pay_bills_select_bill_by_id_hook(qapp: QApplication, db: BankDatabase) -> None:
    ids = _seed(db._conn)
    w = PayBillsScreen(ap_conn=db._conn, bank_db=db)
    assert w.select_bill_by_id(ids["open_bill"]) is True
    from PySide6.QtWidgets import QCheckBox

    tbl = w.findChild(QTableWidget, "payBillsTable")
    assert tbl is not None
    checked = [
        tbl.cellWidget(i, 0)
        for i in range(tbl.rowCount())
        if isinstance(tbl.cellWidget(i, 0), QCheckBox) and tbl.cellWidget(i, 0).isChecked()
    ]
    assert checked
    w.close()
