"""Customer Center — QB Pro layout, live customer/job list, invoices / payments grid."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
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

from desktop_app.customer_center_screen import (
    CustomerCenterScreen,
    customer_center_empty_sentence,
    customer_center_job_display_name,
)
from desktop_app.extra_tabs import ARTab
from desktop_app.theme import BG_PRIMARY
from probooksai import business
from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import apply_extensions

_FORBIDDEN_QB_NAMES = ("ANVIL STEEL", "FLATIRON CORP BENECIA", "12588")


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def db(tmp_path: Path) -> BankDatabase:
    b = BankDatabase(db_path=str(tmp_path / "customer_center_t.db"))
    apply_extensions(b._conn)
    yield b
    b.close()


def test_customer_center_empty_sentence() -> None:
    assert customer_center_empty_sentence("Invoices", "All Invoices", "All") == (
        "There are no transactions of type 'Invoices', "
        "filtered by 'All Invoices', in date range 'All'."
    )


def test_customer_center_job_display_name() -> None:
    assert customer_center_job_display_name("Site A").startswith("    :")
    assert customer_center_job_display_name("Site A").endswith("Site A")


def test_customer_center_qb_chrome(qapp: QApplication) -> None:
    w = CustomerCenterScreen(conn=None)  # type: ignore[arg-type]
    w._conn = None
    labels = [lb.text() for lb in w.findChildren(QLabel)]
    assert "Customer Information" in labels
    assert "NOTE" in labels
    assert "REPORTS FOR THIS CUSTOMER" in labels

    tools = [b.text() for b in w.findChildren(QToolButton)]
    assert "New Customer & Job" in tools
    assert "New Transactions" in tools
    assert "Print" in tools
    assert "Excel" in tools
    assert "Word" in tools
    assert "Manage Transactions" in tools
    assert "Run Reports" in tools

    btns = [b.text() for b in w.findChildren(QPushButton)]
    assert "Income Tracker" in btns
    assert "QuickReport" in btns
    assert "Open Balance" in btns

    left = w.findChild(QTabWidget, "customerCenterLeftTabs")
    assert left is not None
    assert [left.tabText(i) for i in range(left.count())] == [
        "Customers & Jobs",
        "Transactions",
    ]

    right = w.findChild(QTabWidget, "customerCenterRightTabs")
    assert right is not None
    assert [right.tabText(i) for i in range(right.count())] == [
        "Transactions",
        "Contacts",
        "To Do's",
        "Notes",
        "Sent Email",
    ]

    show = w.findChild(QComboBox, "customerCenterShow")
    filt = w.findChild(QComboBox, "customerCenterFilterBy")
    date_cb = w.findChild(QComboBox, "customerCenterDate")
    assert show is not None and show.currentText() == "Invoices"
    assert filt is not None and filt.currentText() == "All Invoices"
    assert date_cb is not None and date_cb.currentText() == "All"
    assert "Invoices" in [show.itemText(i) for i in range(show.count())]

    list_filter = w.findChild(QComboBox, "customerCenterListFilter")
    assert list_filter is not None
    assert list_filter.currentText() == "Active Customers"
    assert w.findChild(QLineEdit, "customerCenterSearch") is not None

    ctbl = w.findChild(QTableWidget, "customerCenterCustomerTable")
    assert ctbl is not None
    assert ctbl.columnCount() == 3
    assert ctbl.horizontalHeaderItem(0).text() == "NAME"
    assert ctbl.horizontalHeaderItem(1).text() == "BALANCE TOTAL"

    ttbl = w.findChild(QTableWidget, "customerCenterTxnTable")
    assert ttbl is not None
    assert [ttbl.horizontalHeaderItem(i).text() for i in range(ttbl.columnCount())] == [
        "NUM",
        "DATE",
        "DUE DATE",
        "AGING",
        "AMOUNT",
        "OPEN BALANCE",
    ]

    empty = w.findChild(QLabel, "customerCenterEmpty")
    assert empty is not None
    assert "There are no transactions of type 'Invoices'" in empty.text()

    pal = w.palette()
    assert pal.color(QPalette.ColorRole.Window).name().lower() != BG_PRIMARY.lower()


def test_artab_is_customer_center(qapp: QApplication, db: BankDatabase) -> None:
    w = ARTab(db._conn)
    assert isinstance(w, CustomerCenterScreen)
    assert w.findChild(QTableWidget, "customerCenterCustomerTable") is not None


def test_customer_center_lists_live_customers_and_invoices(
    qapp: QApplication, db: BankDatabase
) -> None:
    c1 = business.add_customer(db._conn, "Harbor Logistics")
    c2 = business.add_customer(db._conn, "Westside Hauling")
    job = business.add_customer(db._conn, "Site A", parent_customer_id=c1)
    business.create_invoice(
        db._conn,
        c1,
        "INV-2101",
        "2026-08-01",
        due_date="2026-08-31",
        lines=[{"description": "Haul", "qty": 1, "rate": 450.00}],
    )
    iid = business.create_invoice(
        db._conn,
        c2,
        "WH-88",
        "2026-07-15",
        due_date="2026-08-14",
        lines=[{"description": "Haul", "qty": 1, "rate": 1280.50}],
    )
    business.record_ar_payment(
        db._conn,
        c2,
        "2026-08-10",
        500.00,
        [(iid, 500.00)],
        method="Check",
        reference="1008",
    )
    business.create_invoice(
        db._conn,
        job,
        "JOB-12",
        "2026-08-05",
        due_date="2026-09-04",
        lines=[{"description": "Site work", "qty": 1, "rate": 200.00}],
    )
    w = CustomerCenterScreen(db._conn)
    ctbl = w.findChild(QTableWidget, "customerCenterCustomerTable")
    assert ctbl is not None
    names = [ctbl.item(r, 0).text() for r in range(ctbl.rowCount())]
    assert "Harbor Logistics" in names
    assert "Westside Hauling" in names
    assert any(n.strip().startswith(":") and "Site A" in n for n in names)
    for forbidden in _FORBIDDEN_QB_NAMES:
        assert forbidden not in names
        assert not any(forbidden in n for n in names)

    w._focused_customer_id = c2
    w._select_customer_row(c2)
    w._apply_detail_from_focus()
    w._show.setCurrentText("All")
    w._reload_txn_table()
    assert w._d_company.text() == "Westside Hauling"
    ttbl = w.findChild(QTableWidget, "customerCenterTxnTable")
    assert ttbl is not None
    nums = [ttbl.item(r, 0).text() for r in range(ttbl.rowCount())]
    assert "WH-88" in nums
    assert "1008" in nums
    amt = w.findChild(QLabel, "customerCenterAmountTotal")
    assert amt is not None
    assert "1,780.50" in amt.text() or "1780.50" in amt.text().replace(",", "")


def test_customer_center_parent_balance_rolls_up_jobs(
    qapp: QApplication, db: BankDatabase
) -> None:
    parent = business.add_customer(db._conn, "Harbor Logistics")
    job = business.add_customer(db._conn, "Site A", parent_customer_id=parent)
    business.create_invoice(
        db._conn,
        parent,
        "INV-P",
        "2026-08-01",
        lines=[{"description": "x", "qty": 1, "rate": 100.0}],
    )
    business.create_invoice(
        db._conn,
        job,
        "INV-J",
        "2026-08-02",
        lines=[{"description": "x", "qty": 1, "rate": 50.0}],
    )
    w = CustomerCenterScreen(db._conn)
    names_bals = {
        w._customer_tbl.item(r, 0).text(): w._customer_tbl.item(r, 1).text()
        for r in range(w._customer_tbl.rowCount())
    }
    assert names_bals["Harbor Logistics"] == "150.00"
    job_key = next(k for k in names_bals if "Site A" in k)
    assert names_bals[job_key] == "50.00"


def test_customer_center_empty_state_for_invoices_filter(
    qapp: QApplication, db: BankDatabase
) -> None:
    business.add_customer(db._conn, "Harbor Logistics")
    w = CustomerCenterScreen(db._conn)
    empty = w.findChild(QLabel, "customerCenterEmpty")
    assert empty is not None
    assert empty.text() == customer_center_empty_sentence("Invoices", "All Invoices", "All")
    assert w._txn_stack.currentIndex() == 1


def test_customer_center_search_filters_list(qapp: QApplication, db: BankDatabase) -> None:
    business.add_customer(db._conn, "Harbor Logistics")
    business.add_customer(db._conn, "Westside Hauling")
    w = CustomerCenterScreen(db._conn)
    w._search.setText("Westside")
    ctbl = w._customer_tbl
    assert ctbl.rowCount() == 1
    assert ctbl.item(0, 0).text() == "Westside Hauling"


def test_customer_center_open_balance_filter(qapp: QApplication, db: BankDatabase) -> None:
    c1 = business.add_customer(db._conn, "Harbor Logistics")
    business.add_customer(db._conn, "Westside Hauling")
    business.create_invoice(
        db._conn,
        c1,
        "INV-1",
        "2026-08-01",
        lines=[{"description": "x", "qty": 1, "rate": 10.0}],
    )
    w = CustomerCenterScreen(db._conn)
    w._list_filter.setCurrentText("Customers with Open Balances")
    assert w._customer_tbl.rowCount() == 1
    assert w._customer_tbl.item(0, 0).text() == "Harbor Logistics"


def test_customer_center_double_click_invoice_emits(
    qapp: QApplication, db: BankDatabase
) -> None:
    cid = business.add_customer(db._conn, "Harbor Logistics")
    iid = business.create_invoice(
        db._conn,
        cid,
        "INV-1",
        "2026-08-01",
        lines=[{"description": "x", "qty": 1, "rate": 12.0}],
    )
    w = CustomerCenterScreen(db._conn)
    w._focused_customer_id = cid
    w._reload_txn_table()
    seen: list[int] = []
    w.openInvoiceRequested.connect(seen.append)
    w._on_txn_double_clicked(0, 0)
    assert seen == [iid]


def test_customer_center_double_click_payment_emits(
    qapp: QApplication, db: BankDatabase
) -> None:
    cid = business.add_customer(db._conn, "Harbor Logistics")
    iid = business.create_invoice(
        db._conn,
        cid,
        "INV-1",
        "2026-08-01",
        lines=[{"description": "x", "qty": 1, "rate": 12.0}],
    )
    pid = business.record_ar_payment(
        db._conn, cid, "2026-08-05", 12.0, [(iid, 12.0)], method="Check", reference="9"
    )
    w = CustomerCenterScreen(db._conn)
    w._focused_customer_id = cid
    w._show.setCurrentText("Payments")
    w._reload_txn_table()
    assert w._txn_tbl.rowCount() == 1
    seen: list[int] = []
    w.openPaymentRequested.connect(seen.append)
    w._on_txn_double_clicked(0, 0)
    assert seen == [pid]


def test_customer_center_new_transactions_emit_customer_id(
    qapp: QApplication, db: BankDatabase
) -> None:
    cid = business.add_customer(db._conn, "Harbor Logistics")
    w = CustomerCenterScreen(db._conn)
    w._focused_customer_id = cid
    invoices: list[int] = []
    pays: list[int] = []
    w.createInvoicesRequested.connect(invoices.append)
    w.receivePaymentsRequested.connect(pays.append)
    w._on_new_create_invoices()
    w._on_new_receive_payments()
    assert invoices == [cid]
    assert pays == [cid]


def test_customer_center_quickreport_shows_all(qapp: QApplication, db: BankDatabase) -> None:
    cid = business.add_customer(db._conn, "Harbor Logistics")
    iid = business.create_invoice(
        db._conn,
        cid,
        "INV-1",
        "2026-08-01",
        lines=[{"description": "x", "qty": 1, "rate": 12.0}],
    )
    business.record_ar_payment(
        db._conn, cid, "2026-08-05", 5.0, [(iid, 5.0)], method="Check"
    )
    w = CustomerCenterScreen(db._conn)
    w._focused_customer_id = cid
    w._on_quickreport()
    assert w._show.currentText() == "All"
    assert w._txn_tbl.rowCount() == 2


def test_customer_center_does_not_copy_real_qb_customer_names() -> None:
    roots = [
        Path("desktop_app/customer_center_screen.py"),
        Path("desktop_app/extra_tabs.py"),
        Path("scripts/capture_ui_screenshot.py"),
        Path("probooksai/business.py"),
    ]
    for path in roots:
        text = path.read_text(encoding="utf-8")
        for name in _FORBIDDEN_QB_NAMES:
            assert name not in text, f"{name!r} must not appear in {path}"


def test_customer_center_main_window_wires_signals(qapp: QApplication, tmp_path: Path) -> None:
    from desktop_app.main import MainWindow

    db_path = tmp_path / "cc_main.db"
    BankDatabase(str(db_path)).close()
    w = MainWindow(db_path=str(db_path))
    try:
        assert isinstance(w._customers_tab, ARTab)
        conn = w._bank_db._conn
        cid = business.add_customer(conn, "Harbor Logistics")
        iid = business.create_invoice(
            conn,
            cid,
            "X-1",
            "2026-08-01",
            lines=[{"description": "x", "qty": 1, "rate": 25.0}],
        )
        w._customers_tab._refresh()
        w._on_customer_center_create_invoices(cid)
        assert w._tabs.currentWidget() is w._invoice_screen
        assert w._invoice_screen.selected_bill_to_customer_id() == cid
        w._on_customer_center_open_invoice(iid)
        assert w._invoice_screen._current_invoice_id == iid
        w._on_customer_center_receive_payments(cid)
        assert w._tabs.currentWidget() is w._receive_payments_screen
        assert w._receive_payments_screen._selected_customer_id() == cid
    finally:
        w.close()
