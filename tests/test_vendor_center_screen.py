"""Vendor Center — QB Pro layout, live vendor list, bills / BILLPMT grid."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QToolButton,
)

from desktop_app.extra_tabs import APTab
from desktop_app.theme import BG_PRIMARY
from desktop_app.vendor_center_screen import (
    VendorCenterScreen,
    vendor_center_empty_sentence,
)
from probooksai import business
from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import apply_extensions

_FORBIDDEN_QB_NAMES = ("2290 TAX", "ABA TRUCKING", "BANDERAS", "AR TRUCKING")


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def db(tmp_path: Path) -> BankDatabase:
    b = BankDatabase(db_path=str(tmp_path / "vendor_center_t.db"))
    apply_extensions(b._conn)
    yield b
    b.close()


def test_vendor_center_empty_sentence() -> None:
    assert vendor_center_empty_sentence("Bills", "All Bills", "All") == (
        "There are no transactions of type 'Bills', filtered by 'All Bills', in date range 'All'."
    )


def test_vendor_center_qb_chrome(qapp: QApplication) -> None:
    w = VendorCenterScreen(conn=None)  # type: ignore[arg-type]
    w._conn = None  # constructed without db for chrome-only
    labels = [lb.text() for lb in w.findChildren(QLabel)]
    assert "Vendor Information" in labels
    assert "NOTE" in labels
    assert "REPORTS FOR THIS VENDOR" in labels

    tools = [b.text() for b in w.findChildren(QToolButton)]
    assert "New Vendor..." in tools
    assert "New Transactions" in tools
    assert "Print" in tools
    assert "Excel" in tools
    assert "Word" in tools
    assert "Manage Transactions" in tools
    assert "Run Reports" in tools

    btns = [b.text() for b in w.findChildren(QPushButton)]
    assert "Bill Tracker" in btns
    assert "Order 1099 Forms" in btns
    assert "Order Checks" in btns
    assert "Schedule Online Payment" in btns
    assert "Map" in btns
    assert "Directions" in btns
    assert "QuickReport" in btns
    assert "Open Balance" in btns

    left = w.findChild(QTabWidget, "vendorCenterLeftTabs")
    assert left is not None
    assert [left.tabText(i) for i in range(left.count())] == ["Vendors", "Transactions"]

    right = w.findChild(QTabWidget, "vendorCenterRightTabs")
    assert right is not None
    assert [right.tabText(i) for i in range(right.count())] == [
        "Transactions",
        "Contacts",
        "Notes",
    ]

    show = w.findChild(QComboBox, "vendorCenterShow")
    filt = w.findChild(QComboBox, "vendorCenterFilterBy")
    date_cb = w.findChild(QComboBox, "vendorCenterDate")
    assert show is not None and show.currentText() == "Bills"
    assert filt is not None and filt.currentText() == "All Bills"
    assert date_cb is not None and date_cb.currentText() == "All"
    assert "Bills" in [show.itemText(i) for i in range(show.count())]

    list_filter = w.findChild(QComboBox, "vendorCenterListFilter")
    assert list_filter is not None
    assert list_filter.currentText() == "Active Vendors"
    assert w.findChild(QLineEdit, "vendorCenterSearch") is not None

    vtbl = w.findChild(QTableWidget, "vendorCenterVendorTable")
    assert vtbl is not None
    assert vtbl.columnCount() == 3
    assert vtbl.horizontalHeaderItem(1).text() == "NAME"
    assert vtbl.horizontalHeaderItem(2).text() == "BALANCE TOTAL"
    assert w.findChild(QPushButton, "vendorCenterMakeInactive") is not None

    ttbl = w.findChild(QTableWidget, "vendorCenterTxnTable")
    assert ttbl is not None
    assert [ttbl.horizontalHeaderItem(i).text() for i in range(ttbl.columnCount())] == [
        "TYPE",
        "NUM",
        "DATE",
        "DUE DATE",
        "AGING",
        "AMOUNT",
        "OPEN BALANCE",
    ]

    empty = w.findChild(QLabel, "vendorCenterEmpty")
    assert empty is not None
    assert "There are no transactions of type 'Bills'" in empty.text()

    pal = w.palette()
    assert pal.color(QPalette.ColorRole.Window).name().lower() != BG_PRIMARY.lower()


def test_aptab_is_vendor_center(qapp: QApplication, db: BankDatabase) -> None:
    w = APTab(db._conn)
    assert isinstance(w, VendorCenterScreen)
    assert w.findChild(QTableWidget, "vendorCenterVendorTable") is not None


def test_vendor_center_lists_live_vendors_and_bills(
    qapp: QApplication, db: BankDatabase
) -> None:
    v1 = business.add_vendor(db._conn, "Office Supplies Co")
    v2 = business.add_vendor(db._conn, "Warehouse Supply")
    business.create_bill(
        db._conn,
        v1,
        "2026-08-01",
        450.00,
        vendor_invoice_number="INV-1042",
        due_date="2026-08-31",
    )
    bid = business.create_bill(
        db._conn,
        v2,
        "2026-07-15",
        1280.50,
        vendor_invoice_number="WS-88",
        due_date="2026-08-14",
    )
    business.record_ap_payment(
        db._conn,
        v2,
        "2026-08-10",
        500.00,
        [(bid, 500.00)],
        method="Check",
        reference="1008",
    )
    w = VendorCenterScreen(db._conn)
    vtbl = w.findChild(QTableWidget, "vendorCenterVendorTable")
    assert vtbl is not None
    names = [vtbl.item(r, 1).text() for r in range(vtbl.rowCount())]
    assert "Office Supplies Co" in names
    assert "Warehouse Supply" in names
    for forbidden in _FORBIDDEN_QB_NAMES:
        assert forbidden not in names

    # Select warehouse: bills + payment
    w._focused_vendor_id = v2
    w._select_vendor_row(v2)
    w._apply_detail_from_focus()
    w._show.setCurrentText("All")
    w._reload_txn_table()
    assert w._d_company.text() == "Warehouse Supply"
    ttbl = w.findChild(QTableWidget, "vendorCenterTxnTable")
    assert ttbl is not None
    types = [ttbl.item(r, 0).text() for r in range(ttbl.rowCount())]
    assert "Bill" in types
    assert any("BILLPMT" in t or "Bill Pmt" in t for t in types)
    nums = [ttbl.item(r, 1).text() for r in range(ttbl.rowCount())]
    assert "WS-88" in nums
    assert "1008" in nums


def test_vendor_center_empty_state_for_bills_filter(
    qapp: QApplication, db: BankDatabase
) -> None:
    business.add_vendor(db._conn, "Office Supplies Co")
    w = VendorCenterScreen(db._conn)
    empty = w.findChild(QLabel, "vendorCenterEmpty")
    assert empty is not None
    assert empty.text() == vendor_center_empty_sentence("Bills", "All Bills", "All")
    assert w._txn_stack.currentIndex() == 1


def test_vendor_center_search_filters_list(qapp: QApplication, db: BankDatabase) -> None:
    business.add_vendor(db._conn, "Office Supplies Co")
    business.add_vendor(db._conn, "Fuel Vendor")
    w = VendorCenterScreen(db._conn)
    w._search.setText("Fuel")
    vtbl = w._vendor_tbl
    assert vtbl.rowCount() == 1
    assert vtbl.item(0, 1).text() == "Fuel Vendor"


def test_vendor_center_open_balance_filter(qapp: QApplication, db: BankDatabase) -> None:
    v1 = business.add_vendor(db._conn, "Office Supplies Co")
    business.add_vendor(db._conn, "Fuel Vendor")
    business.create_bill(db._conn, v1, "2026-08-01", 10.0)
    w = VendorCenterScreen(db._conn)
    w._list_filter.setCurrentText("Vendors with Open Balances")
    assert w._vendor_tbl.rowCount() == 1
    assert w._vendor_tbl.item(0, 1).text() == "Office Supplies Co"


def test_vendor_center_double_click_bill_emits(
    qapp: QApplication, db: BankDatabase
) -> None:
    vid = business.add_vendor(db._conn, "Office Supplies Co")
    bid = business.create_bill(
        db._conn, vid, "2026-08-01", 12.0, vendor_invoice_number="INV-1"
    )
    w = VendorCenterScreen(db._conn)
    w._focused_vendor_id = vid
    w._reload_txn_table()
    seen: list[int] = []
    w.openBillRequested.connect(seen.append)
    w._on_txn_double_clicked(0, 0)
    assert seen == [bid]


def test_vendor_center_double_click_billpmt_emits(
    qapp: QApplication, db: BankDatabase
) -> None:
    vid = business.add_vendor(db._conn, "Office Supplies Co")
    bid = business.create_bill(db._conn, vid, "2026-08-01", 12.0)
    pid = business.record_ap_payment(
        db._conn, vid, "2026-08-05", 12.0, [(bid, 12.0)], method="Check", reference="9"
    )
    w = VendorCenterScreen(db._conn)
    w._focused_vendor_id = vid
    w._show.setCurrentText("Bill Payments")
    w._reload_txn_table()
    assert w._txn_tbl.rowCount() == 1
    seen: list[int] = []
    w.openPaymentRequested.connect(seen.append)
    w._on_txn_double_clicked(0, 0)
    assert seen == [pid]


def test_vendor_center_new_transactions_emit_vendor_id(
    qapp: QApplication, db: BankDatabase
) -> None:
    vid = business.add_vendor(db._conn, "Office Supplies Co")
    w = VendorCenterScreen(db._conn)
    w._focused_vendor_id = vid
    bills: list[int] = []
    pays: list[int] = []
    checks: list[int] = []
    w.enterBillsRequested.connect(bills.append)
    w.payBillsRequested.connect(pays.append)
    w.writeChecksRequested.connect(checks.append)
    w._on_new_enter_bills()
    w._on_new_pay_bills()
    w._on_new_write_checks()
    assert bills == [vid]
    assert pays == [vid]
    assert checks == [vid]


def test_vendor_center_quickreport_shows_all(qapp: QApplication, db: BankDatabase) -> None:
    vid = business.add_vendor(db._conn, "Office Supplies Co")
    bid = business.create_bill(db._conn, vid, "2026-08-01", 12.0)
    business.record_ap_payment(
        db._conn, vid, "2026-08-05", 5.0, [(bid, 5.0)], method="Check"
    )
    w = VendorCenterScreen(db._conn)
    w._focused_vendor_id = vid
    w._on_quickreport()
    assert w._show.currentText() == "All"
    assert w._txn_tbl.rowCount() == 2


def test_vendor_center_does_not_copy_real_qb_vendor_names() -> None:
    roots = [
        Path("desktop_app/vendor_center_screen.py"),
        Path("desktop_app/extra_tabs.py"),
        Path("scripts/capture_ui_screenshot.py"),
        Path("probooksai/business.py"),
    ]
    for path in roots:
        text = path.read_text(encoding="utf-8")
        for name in _FORBIDDEN_QB_NAMES:
            assert name not in text, f"{name!r} must not appear in {path}"


def test_vendor_center_main_window_wires_signals(qapp: QApplication, tmp_path: Path) -> None:
    from desktop_app.main import MainWindow

    db_path = tmp_path / "vc_main.db"
    BankDatabase(str(db_path)).close()
    w = MainWindow(db_path=str(db_path))
    try:
        assert isinstance(w._vendors_tab, APTab)
        conn = w._bank_db._conn
        vid = business.add_vendor(conn, "Office Supplies Co")
        bid = business.create_bill(conn, vid, "2026-08-01", 25.0, vendor_invoice_number="X")
        w._vendors_tab._refresh()
        w._on_vendor_center_enter_bills(vid)
        assert w._tabs.currentWidget() is w._enter_bills_screen
        assert w._enter_bills_screen._selected_vendor_id() == vid
        w._on_vendor_center_open_bill(bid)
        assert w._enter_bills_screen._current_bill_id == bid
        w._on_vendor_center_write_checks(vid)
        assert w._tabs.currentWidget() is w._check_screen
        assert w._check_screen._fld_payee.currentData() == vid
    finally:
        w.close()


def test_vendor_center_active_hides_inactive_search_finds_them(
    qapp: QApplication, db: BankDatabase
) -> None:
    v1 = business.add_vendor(db._conn, "Office Supplies Co")
    v2 = business.add_vendor(db._conn, "Warehouse Supply")
    business.set_vendor_inactive(db._conn, v2, inactive=True)
    w = VendorCenterScreen(db._conn)
    names = [w._vendor_tbl.item(r, 1).text() for r in range(w._vendor_tbl.rowCount())]
    assert "Office Supplies Co" in names
    assert "Warehouse Supply" not in names
    w._search.setText("Warehouse")
    names2 = [w._vendor_tbl.item(r, 1).text() for r in range(w._vendor_tbl.rowCount())]
    assert any("Warehouse Supply" in n for n in names2)
    w._search.clear()
    w._list_filter.setCurrentText("All Vendors")
    names3 = [w._vendor_tbl.item(r, 1).text() for r in range(w._vendor_tbl.rowCount())]
    assert any("Warehouse Supply (Inactive)" in n for n in names3)
    assert business.get_vendor(db._conn, v1) is not None
