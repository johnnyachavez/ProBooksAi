"""Company Snapshot screen — QB Pro chrome, live widgets, navigation hooks."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QToolButton,
)

from desktop_app.coa_tab import COATab
from desktop_app.company_snapshot_screen import CompanySnapshotScreen
from desktop_app.customer_center_screen import CustomerCenterScreen
from desktop_app.extra_tabs import ARTab
from desktop_app.receive_checks_screen import ReceiveChecksScreen
from probooksai import business
from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import apply_extensions

_TODAY = date(2026, 8, 27)
_FORBIDDEN = (
    "BST LINEHAUL",
    "FLATIRON",
    "CHASE BANK",
    "1099 SUBHAULERS",
    "$126,845",
    "$656,881",
    "ANVIL STEEL",
)


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def db(tmp_path: Path) -> BankDatabase:
    b = BankDatabase(db_path=str(tmp_path / "snapshot_ui.db"))
    apply_extensions(b._conn)
    yield b
    b.close()


def _seed(conn) -> dict[str, int]:
    c1 = business.add_customer(conn, "Harbor Logistics")
    c2 = business.add_customer(conn, "Westside Hauling")
    inv_overdue = business.create_invoice(
        conn,
        c1,
        "INV-2101",
        "2026-01-10",
        due_date="2026-02-01",
        lines=[{"description": "Haul", "qty": 1, "rate": 400.00}],
    )
    inv_open = business.create_invoice(
        conn,
        c2,
        "INV-0888",
        "2026-08-01",
        due_date="2026-09-15",
        lines=[{"description": "Haul", "qty": 1, "rate": 90.00}],
    )
    vid = business.add_vendor(conn, "Office Supplies Co")
    business.create_bill(
        conn, vid, "2026-03-04", 50.00, vendor_invoice_number="OS-1", due_date="2026-03-20"
    )
    return {"c1": c1, "c2": c2, "inv_overdue": inv_overdue, "inv_open": inv_open}


def test_snapshot_chrome_and_live_owe_table(qapp: QApplication, db: BankDatabase) -> None:
    _seed(db._conn)
    w = CompanySnapshotScreen(ap_conn=db._conn, today=_TODAY)
    w.restore_default()
    qapp.processEvents()
    labels = [lb.text() for lb in w.findChildren(QLabel)]
    assert "Company Snapshot" in labels
    assert "Income and Expense Trend" in labels
    assert "Prev Year Income Comparison" in labels
    assert "Customers Who Owe Money" in labels
    assert "Account Balances" in labels
    assert "Top Customers by Sales" in labels
    assert "Prev Year Expense Comparison" in labels
    assert "Expense Breakdown" in labels
    assert w.findChild(QToolButton, "snapshotViewCompany").isChecked()
    assert w.findChild(QPushButton, "snapshotAddContent") is not None
    assert w.findChild(QPushButton, "snapshotRestoreDefault") is not None
    assert w.findChild(QLineEdit, "snapshotSearch") is not None
    assert w.findChild(QPushButton, "snapshotCustomizeHelp") is not None
    assert w.findChild(QPushButton, "snapshotPrint") is not None
    assert w.findChild(QPushButton, "snapshotReceivePaymentsLink") is not None
    assert w.findChild(QPushButton, "snapshotGoToCoaLink") is not None
    tbl = w.findChild(QTableWidget, "snapshotCustomersOweTable")
    assert tbl is not None
    assert tbl.columnCount() == 3
    assert tbl.horizontalHeaderItem(0).text() == "CUSTOMER"
    assert tbl.rowCount() >= 2
    names = [tbl.item(r, 0).text() for r in range(tbl.rowCount())]
    assert "Harbor Logistics" in names
    harbor_row = names.index("Harbor Logistics")
    due_item = tbl.item(harbor_row, 1)
    assert due_item.foreground().color().name().lower() == QColor("#c62828").name().lower()
    bals = w.findChild(QTableWidget, "snapshotAccountBalancesTable")
    bal_names = [bals.item(r, 0).text() for r in range(bals.rowCount())]
    assert "Accounts Receivable" in bal_names
    w.close()


def test_snapshot_empty_file_does_not_invent_years(
    qapp: QApplication, db: BankDatabase
) -> None:
    w = CompanySnapshotScreen(ap_conn=db._conn, today=_TODAY)
    qapp.processEvents()
    years = w._chart_prev_inc._categories
    assert years == ["2026"]
    assert max(w._chart_prev_inc._series[1][2] or [0]) == 0.0
    w.close()


def test_snapshot_links_emit_navigation(
    qapp: QApplication, db: BankDatabase
) -> None:
    ids = _seed(db._conn)
    w = CompanySnapshotScreen(ap_conn=db._conn, today=_TODAY)
    nav: list[str] = []
    customers: list[int] = []
    payments: list[int] = []
    w.navigateRequested.connect(nav.append)
    w.openCustomerRequested.connect(customers.append)
    w.receivePaymentsRequested.connect(payments.append)
    w.findChild(QPushButton, "snapshotGoToCoaLink").click()
    qapp.processEvents()
    assert nav == ["coa"]
    w._on_owe_activated(0)
    qapp.processEvents()
    assert customers and customers[0] in {ids["c1"], ids["c2"]}
    w.findChild(QPushButton, "snapshotReceivePaymentsLink").click()
    qapp.processEvents()
    assert payments
    w.close()


def test_snapshot_main_window_tab_and_home_shortcut(
    qapp: QApplication, tmp_path: Path
) -> None:
    from desktop_app.main import MainWindow

    db_path = tmp_path / "snapshot_nav.db"
    BankDatabase(str(db_path)).close()
    w = MainWindow(db_path=str(db_path))
    try:
        tabs = w._tabs
        assert "Company Snapshot" in tabs.tabText(4)
        assert isinstance(tabs.widget(4), CompanySnapshotScreen)
        tabs.setCurrentIndex(0)
        qapp.processEvents()
        btn = w._dashboard_tab.findChild(QToolButton, "homeShortcut_snapshot")
        assert btn is not None
        btn.click()
        qapp.processEvents()
        assert tabs.currentWidget() is w._snapshot_screen
        titles = [lb.text() for lb in tabs.currentWidget().findChildren(QLabel)]
        assert "Company Snapshot" in titles
        assert isinstance(w._customers_tab, ARTab)
        assert isinstance(w._receive_payments_screen, ReceiveChecksScreen)
        assert isinstance(w._coa_tab, COATab)
    finally:
        w.close()


def test_snapshot_row_opens_customer_center_and_receive_payments(
    qapp: QApplication, tmp_path: Path
) -> None:
    from desktop_app.main import MainWindow

    db_path = tmp_path / "snapshot_open.db"
    b = BankDatabase(str(db_path))
    apply_extensions(b._conn)
    ids = _seed(b._conn)
    b.close()
    w = MainWindow(db_path=str(db_path))
    try:
        snap = w._snapshot_screen
        snap._today = _TODAY
        snap.reload()
        qapp.processEvents()
        tbl = snap.findChild(QTableWidget, "snapshotCustomersOweTable")
        assert tbl.rowCount() >= 1
        harbor = None
        for r in range(tbl.rowCount()):
            if tbl.item(r, 0).text() == "Harbor Logistics":
                harbor = r
                break
        assert harbor is not None
        snap._on_owe_activated(harbor)
        qapp.processEvents()
        assert w._tabs.currentWidget() is w._customers_tab
        assert isinstance(w._customers_tab, CustomerCenterScreen)
        assert int(w._customers_tab._focused_customer_id or 0) == ids["c1"]
        w._tabs.setCurrentIndex(4)
        qapp.processEvents()
        snap.findChild(QPushButton, "snapshotReceivePaymentsLink").click()
        qapp.processEvents()
        assert w._tabs.currentWidget() is w._receive_payments_screen
        snap.findChild(QPushButton, "snapshotGoToCoaLink").click()
        qapp.processEvents()
        assert w._tabs.currentWidget() is w._coa_tab
    finally:
        w.close()


def test_snapshot_ui_has_no_live_company_identity() -> None:
    text = Path("desktop_app/company_snapshot_screen.py").read_text(encoding="utf-8")
    lowered = text.lower()
    for needle in _FORBIDDEN:
        assert needle.lower() not in lowered
    assert "COMPANY NAME" not in text


def test_capture_script_has_snapshot_tab() -> None:
    text = Path("scripts/capture_ui_screenshot.py").read_text(encoding="utf-8")
    assert "--tab snapshot" in text or "--tab company-snapshot" in text
    yml = Path(".github/workflows/ui-screenshot.yml").read_text(encoding="utf-8")
    assert "--tab snapshot" in yml or "--tab company-snapshot" in yml
