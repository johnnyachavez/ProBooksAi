"""Runtime checks for main window tab strip (default order, drag-reorder, hidden aging tabs)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QTableWidget, QTabWidget, QWidget

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
        assert tabs.count() == 21
        titles = [tabs.tabText(i) for i in range(tabs.count())]
        expected = [
            "Home",
            "Income Tracker",
            "Bill Tracker",
            "Calendar",
            "Company Snapshot",
            "My Company",
            "Invoices",
            "Codes",
            "Write Checks",
            "Enter Bills",
            "Pay Bills",
            "Receive Payments",
            "Make Deposits",
            "Bank Register",
            "Chart of Accounts",
            "Customers",
            "Vendors",
            "Reconcile",
            "More",
            "A/R Aging",
            "A/P Aging",
        ]
        assert titles == expected or set(titles) == set(expected)
        assert "A/R Aging" in titles[-2:] and "A/P Aging" in titles[-2:]
        tb = tabs.tabBar()
        assert tb.isMovable()
        assert tb.objectName() == "mainWorkspaceTabBar"
        ar_idx = tabs.indexOf(w._ar_aging_screen)
        ap_idx = tabs.indexOf(w._ap_aging_screen)
        assert ar_idx >= 0 and not tb.isTabVisible(ar_idx)
        assert ap_idx >= 0 and not tb.isTabVisible(ap_idx)
        for i in range(tabs.count()):
            if i not in (ar_idx, ap_idx):
                assert tb.isTabVisible(i)
                tabs.setCurrentIndex(i)
                assert tabs.currentIndex() == i
        w._focus_ar_aging_summary()
        assert tabs.currentWidget() is w._ar_aging_screen
        w._focus_ap_aging_summary()
        assert tabs.currentWidget() is w._ap_aging_screen
    finally:
        w.close()


def test_accounting_landing_tabs_show_page_titles(qapp: QApplication, tmp_path: Path) -> None:
    """Invoice / Write Checks / Enter Bills / Pay Bills / Receive Payments / Make Deposits landing screens."""
    from desktop_app.calendar_screen import CalendarScreen
    from desktop_app.check_screen import CheckScreen
    from desktop_app.company_snapshot_screen import CompanySnapshotScreen
    from desktop_app.enter_bills_screen import EnterBillsScreen
    from desktop_app.invoice_screen import InvoiceScreen
    from desktop_app.main import MainWindow
    from desktop_app.make_deposits_screen import MakeDepositsScreen
    from desktop_app.my_company_screen import MyCompanyScreen
    from desktop_app.pay_bills_screen import PayBillsScreen
    from desktop_app.receive_checks_screen import ReceiveChecksScreen
    from desktop_app.tracker_screens import BillTrackerScreen, IncomeTrackerScreen

    db_path = tmp_path / "landing_titles.db"
    db = BankDatabase(str(db_path))
    db.close()
    w = MainWindow(db_path=str(db_path))
    try:
        tabs = w._tabs
        expected = (
            IncomeTrackerScreen,
            BillTrackerScreen,
            CalendarScreen,
            CompanySnapshotScreen,
            MyCompanyScreen,
            InvoiceScreen,
            CheckScreen,
            EnterBillsScreen,
            PayBillsScreen,
            ReceiveChecksScreen,
            MakeDepositsScreen,
        )
        for spec in expected:
            idx = next(i for i in range(tabs.count()) if isinstance(tabs.widget(i), spec))
            tabs.setCurrentIndex(idx)
            cw = tabs.currentWidget()
            assert isinstance(cw, spec)
            titles = [lb.text() for lb in cw.findChildren(QLabel)]
            if spec is IncomeTrackerScreen:
                tbl = cw.findChild(QTableWidget, "incomeTrackerTable")
                assert tbl is not None
                assert tbl.columnCount() == 11
                assert "Income Tracker" in titles
                assert "UNBILLED" in titles
                assert "UNPAID" in titles
                continue
            if spec is BillTrackerScreen:
                tbl = cw.findChild(QTableWidget, "billTrackerTable")
                assert tbl is not None
                assert tbl.columnCount() == 10
                assert "Bill Tracker" in titles
                assert "UNPAID" in titles
                continue
            if spec is CalendarScreen:
                assert "Calendar" in titles
                assert "Select a date" in titles
                assert "SHOW" in titles
                assert any("Upcoming: Next 7 days" in t for t in titles)
                continue
            if spec is CompanySnapshotScreen:
                assert "Company Snapshot" in titles
                assert "Income and Expense Trend" in titles
                assert "Customers Who Owe Money" in titles
                assert "Account Balances" in titles
                continue
            if spec is MyCompanyScreen:
                from desktop_app.my_company_screen import company_file_display_name

                assert company_file_display_name(w._bank_db._conn) in titles
                assert "COMPANY INFORMATION" in titles
                assert "Product Information" in titles
                assert "MANAGE YOUR APPS, SERVICES & SUBSCRIPTIONS" not in titles
                continue
            if spec is InvoiceScreen:
                tbl = cw.findChild(QTableWidget, "invoiceLinesTable")
                assert tbl is not None
                assert tbl.columnCount() == 7
                assert tbl.objectName() == "invoiceLinesTable"
                assert "Invoice" in titles
                assert any("Subtotal" in t for t in titles)
                continue
            if spec is CheckScreen:
                tbl = cw.findChild(QTableWidget, "writeChecksExpensesTable")
                assert tbl is not None
                assert tbl.columnCount() == 5
                assert tbl.horizontalHeaderItem(0).text() == "ACCOUNT"
                assert "BANK ACCOUNT" in titles
                assert "PAY TO THE ORDER OF" in titles
                continue
            if spec is EnterBillsScreen:
                tbl = cw.findChild(QTableWidget, "enterBillsExpensesTable")
                assert tbl is not None
                assert tbl.columnCount() == 5
                items = cw.findChild(QTableWidget, "enterBillsItemsTable")
                assert items is not None
                assert items.columnCount() == 7
                assert "Bill" in titles
                assert "VENDOR" in titles
                continue
            tbl = cw.findChild(QTableWidget)
            assert tbl is not None
            if spec is PayBillsScreen:
                assert tbl.columnCount() == 8
                assert tbl.horizontalHeaderItem(3).text() == "VENDOR"
                assert tbl.horizontalHeaderItem(7).text() == "AMT. TO PAY"
                assert "Pay Bills" in titles
                assert "SELECT BILLS TO BE PAID" in titles
                assert "PAY FROM" in titles
                assert "CHECK NO." in titles
            elif spec is MakeDepositsScreen:
                dep = cw.findChild(QTableWidget, "makeDepositsTable")
                assert dep is not None
                assert dep.columnCount() == 6
                assert dep.horizontalHeaderItem(0).text() == "RECEIVED FROM"
                assert "Make Deposits" in titles
                assert "DEPOSIT TO" in titles
            else:
                assert tbl.columnCount() == 6
                assert "Customer Payment" in titles
                assert "RECEIVED FROM" in titles
    finally:
        w.close()


def test_more_hub_contains_reports_journal_business_audit(qapp: QApplication, tmp_path: Path) -> None:
    from desktop_app.main import MainWindow

    db_path = tmp_path / "more_hub.db"
    BankDatabase(str(db_path)).close()
    w = MainWindow(db_path=str(db_path))
    try:
        mh = w._more_hub
        assert mh.count() == 5
        assert mh.widget(0) is w._reports_tab
        assert mh.widget(1) is w._journal_tab
        assert mh.widget(2) is w._business_hub
        assert mh.widget(3) is w._asset_register_tab
        assert mh.widget(4) is w._audit_tab
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
        assert tabs.widget(tabs.indexOf(w._customers_tab)) is w._customers_tab
        assert tabs.widget(tabs.indexOf(w._vendors_tab)) is w._vendors_tab
        assert isinstance(w._customers_tab, ARTab)
        assert isinstance(w._vendors_tab, APTab)
        bh = w._business_hub._business_subtabs
        # Merged Business hub: Rules, Payroll, Tax %, Company (HEAD), AI (dev).
        # Top-level Customers/Vendors are still the primary AR/AP entry points.
        assert bh.count() == 5
        assert "Rules" in bh.tabText(0) and "Payroll" in bh.tabText(1) and "Tax" in bh.tabText(2)
        assert bh.tabText(3) == "Company"
        assert bh.tabText(4) == "AI"
    finally:
        w.close()


def test_reconcile_hub_hosts_bank_import_ar_and_statement_intake(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Reconcile hub hosts Bank statements, AR / Invoices, and Statement intake
    (review). Document Intake is not a hub tab. Top-level tabs stay locked
    elsewhere."""
    from desktop_app.main import MainWindow

    db_path = tmp_path / "reconcile_hub.db"
    BankDatabase(str(db_path)).close()
    w = MainWindow(db_path=str(db_path))
    try:
        rh = w._reconcile_hub
        assert rh.count() == 3
        assert rh.widget(0) is w._bank_tab
        assert rh.tabText(0) == "Bank statements"
        assert rh.tabText(1) == "AR / Invoices"
        assert rh.widget(1) is w._ar_recon_widget
        assert rh.widget(2) is w._statement_intake_panel
        assert rh.tabText(2) == "Statement intake (review)"
        assert not hasattr(w, "_intake_widget")
        titles = [rh.tabText(i) for i in range(rh.count())]
        assert "Documents" not in titles
    finally:
        w.close()


def test_main_window_wires_default_ai_provider_into_statement_intake_panel(
    qapp: QApplication, tmp_path: Path
) -> None:
    """``MainWindow._assemble_main_tabs`` must call ``set_ai_provider`` with
    the default OpenAI-backed provider so the panel's AI fallback is hot
    as soon as the user enables it (no app restart required). The
    provider stays silent until both ``ai_intake_enabled`` AND a key
    are configured, which is gated by the panel and provider — but the
    pipe must be plumbed at construction time."""
    from desktop_app.main import MainWindow
    from probooksai.bank_statement_intake_ai_provider import OpenAIProvider

    db_path = tmp_path / "ai_wire.db"
    BankDatabase(str(db_path)).close()
    w = MainWindow(db_path=str(db_path))
    try:
        panel = w._statement_intake_panel
        assert panel._ai_provider is not None
        assert isinstance(panel._ai_provider, OpenAIProvider)
        # Provider reads the *current* company conn; sanity-check it
        # points at the open window's bank_db.
        assert panel._ai_provider._conn is w._bank_db._conn
    finally:
        w.close()


def test_apply_saved_main_tab_order_moves_widgets(qapp: QApplication) -> None:
    from desktop_app.main import apply_saved_main_tab_order

    tabs = QTabWidget()
    a, b, c = QWidget(), QWidget(), QWidget()
    a.setProperty("mainTabId", "home")
    b.setProperty("mainTabId", "invoices")
    c.setProperty("mainTabId", "customers")
    tabs.addTab(a, "Home")
    tabs.addTab(b, "Invoices")
    tabs.addTab(c, "Customers")
    apply_saved_main_tab_order(tabs, ["customers", "home", "invoices"])
    assert [tabs.widget(i).property("mainTabId") for i in range(3)] == [
        "customers",
        "home",
        "invoices",
    ]
    apply_saved_main_tab_order(tabs, ["home"])
    assert tabs.widget(0).property("mainTabId") == "home"
    assert set(tabs.widget(i).property("mainTabId") for i in range(3)) == {
        "home",
        "invoices",
        "customers",
    }


def test_theme_main_workspace_tab_bar_is_outlined_selected_lighter() -> None:
    from desktop_app.theme import STYLESHEET

    assert "QTabBar#mainWorkspaceTabBar::tab" in STYLESHEET
    assert "QTabBar#mainWorkspaceTabBar::tab:selected" in STYLESHEET
    selected_block = STYLESHEET.split("QTabBar#mainWorkspaceTabBar::tab:selected")[1].split("QTabBar#")[0]
    assert "border: 1px solid" in selected_block
    assert "#E4EBF5" in selected_block
    bar_block = STYLESHEET.split("QTabBar#mainWorkspaceTabBar {")[1].split("QTabBar#")[0]
    assert "#121A2C" in bar_block

