"""Runtime checks for main window tab strip order (Step 1 fixed top-level architecture)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QTableWidget

from probooksai.bank_import import BankDatabase

from desktop_app.extra_tabs import APTab, ARTab


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_main_window_tab_count_and_fixed_top_level_order(qapp: QApplication, tmp_path: Path) -> None:
    from desktop_app.main import MainWindow

    db_path = tmp_path / "main_tabs_strip.db"
    db = BankDatabase(str(db_path))
    db.close()
    w = MainWindow(db_path=str(db_path))
    try:
        tabs = w._tabs
        assert tabs.count() == 10
        order = (
            (0, "Invoices"),
            (1, "Enter Bills"),
            (2, "Pay Bills"),
            (3, "Receive Payments"),
            (4, "Bank Register"),
            (5, "Chart of Accounts"),
            (6, "Customers"),
            (7, "Vendors"),
            (8, "Reconcile"),
            (9, "More"),
        )
        for idx, needle in order:
            assert needle in tabs.tabText(idx)
        tb = tabs.tabBar()
        for i in range(10):
            assert tb.isTabVisible(i)
            tabs.setCurrentIndex(i)
            assert tabs.currentIndex() == i
    finally:
        w.close()


def test_accounting_landing_tabs_show_page_titles(qapp: QApplication, tmp_path: Path) -> None:
    """Tabs 0–3: Invoice, Enter Bills, Pay Bills, Receive Payments use structured screens."""
    from desktop_app.enter_bills_screen import EnterBillsScreen
    from desktop_app.invoice_screen import InvoiceScreen
    from desktop_app.main import MainWindow
    from desktop_app.pay_bills_screen import PayBillsScreen
    from desktop_app.receive_checks_screen import ReceiveChecksScreen

    db_path = tmp_path / "landing_titles.db"
    db = BankDatabase(str(db_path))
    db.close()
    w = MainWindow(db_path=str(db_path))
    try:
        tabs = w._tabs
        expected = (
            InvoiceScreen,
            EnterBillsScreen,
            PayBillsScreen,
            ReceiveChecksScreen,
        )
        for idx, spec in enumerate(expected):
            tabs.setCurrentIndex(idx)
            cw = tabs.currentWidget()
            assert isinstance(cw, spec)
            tbl = cw.findChild(QTableWidget)
            assert tbl is not None
            titles = [lb.text() for lb in cw.findChildren(QLabel)]
            if spec is InvoiceScreen:
                assert tbl.columnCount() == 7
                assert tbl.objectName() == "invoiceLinesTable"
                assert "Invoice" in titles
                assert any("Subtotal" in t for t in titles)
            elif spec is EnterBillsScreen:
                assert tbl.columnCount() == 5
                assert "Bill" in titles
                assert "Vendor" in titles
            elif spec is PayBillsScreen:
                assert tbl.columnCount() == 10
                assert "Pay Bills" in titles
            else:
                assert tbl.columnCount() == 6
                assert "Customer Payment" in titles
    finally:
        w.close()


def test_more_hub_contains_reports_journal_business_audit(qapp: QApplication, tmp_path: Path) -> None:
    from desktop_app.main import MainWindow

    db_path = tmp_path / "more_hub.db"
    BankDatabase(str(db_path)).close()
    w = MainWindow(db_path=str(db_path))
    try:
        mh = w._more_hub
        assert mh.count() == 4
        assert mh.widget(0) is w._reports_tab
        assert mh.widget(1) is w._journal_tab
        assert mh.widget(2) is w._business_hub
        assert mh.widget(3) is w._audit_tab
    finally:
        w.close()


def test_customers_and_vendors_tabs_use_live_ar_ap_workflows(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Step 3: primary AR/AP is top-level Customers/Vendors; Business hub no longer duplicates those subtabs."""
    from desktop_app.main import MainWindow

    db_path = tmp_path / "customers_vendors.db"
    BankDatabase(str(db_path)).close()
    w = MainWindow(db_path=str(db_path))
    try:
        tabs = w._tabs
        assert isinstance(tabs.widget(6), ARTab)
        assert isinstance(tabs.widget(7), APTab)
        assert tabs.widget(6) is w._customers_tab
        assert tabs.widget(7) is w._vendors_tab
        bh = w._business_hub._business_subtabs
        assert bh.count() == 3
        assert "Rules" in bh.tabText(0) and "Payroll" in bh.tabText(1) and "Tax" in bh.tabText(2)
    finally:
        w.close()


def test_reconcile_hub_hosts_bank_import_and_document_intake(qapp: QApplication, tmp_path: Path) -> None:
    from desktop_app.main import MainWindow

    db_path = tmp_path / "reconcile_hub.db"
    BankDatabase(str(db_path)).close()
    w = MainWindow(db_path=str(db_path))
    try:
        rh = w._reconcile_hub
        assert rh.count() == 2
        assert rh.widget(0) is w._bank_tab
        assert rh.widget(1) is w._intake_widget
    finally:
        w.close()
