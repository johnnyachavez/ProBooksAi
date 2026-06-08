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
        assert tabs.count() == 13
        order = (
            (0, "Dashboard"),
            (1, "Invoices"),
            (2, "Codes"),
            (3, "Write Checks"),
            (4, "Enter Bills"),
            (5, "Pay Bills"),
            (6, "Receive Payments"),
            (7, "Bank Register"),
            (8, "Chart of Accounts"),
            (9, "Customers"),
            (10, "Vendors"),
            (11, "Reconcile"),
            (12, "More"),
        )
        for idx, needle in order:
            assert needle in tabs.tabText(idx)
        tb = tabs.tabBar()
        for i in range(13):
            assert tb.isTabVisible(i)
            tabs.setCurrentIndex(i)
            assert tabs.currentIndex() == i
    finally:
        w.close()


def test_accounting_landing_tabs_show_page_titles(qapp: QApplication, tmp_path: Path) -> None:
    """Tabs 1–4: Invoice, Enter Bills, Pay Bills, Receive Payments use structured screens (tab 0 is Dashboard)."""
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
            (1, InvoiceScreen),
            (4, EnterBillsScreen),
            (5, PayBillsScreen),
            (6, ReceiveChecksScreen),
        )
        for idx, spec in expected:
            tabs.setCurrentIndex(idx)
            cw = tabs.currentWidget()
            assert isinstance(cw, spec)
            titles = [lb.text() for lb in cw.findChildren(QLabel)]
            if spec is InvoiceScreen:
                tbl = cw.findChild(QTableWidget, "invoiceLinesTable")
                assert tbl is not None
                assert tbl.columnCount() == 7
                assert tbl.objectName() == "invoiceLinesTable"
                assert "Invoice" in titles
                assert any("Subtotal" in t for t in titles)
                continue
            tbl = cw.findChild(QTableWidget)
            assert tbl is not None
            if spec is EnterBillsScreen:
                assert tbl.columnCount() == 5
                assert "Enter Bills" in titles
                assert "Vendor" in titles
            elif spec is PayBillsScreen:
                assert tbl.columnCount() == 7
                assert "Pay Bills" in titles
            else:
                assert tbl.columnCount() == 7
                assert "Receive Payments" in titles
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
        assert isinstance(tabs.widget(9), ARTab)
        assert isinstance(tabs.widget(10), APTab)
        assert tabs.widget(9) is w._customers_tab
        assert tabs.widget(10) is w._vendors_tab
        bh = w._business_hub._business_subtabs
        # Merged Business hub: Rules, Payroll, Tax %, Company (HEAD), AI (dev).
        # Top-level Customers/Vendors are still the primary AR/AP entry points.
        assert bh.count() == 5
        assert "Rules" in bh.tabText(0) and "Payroll" in bh.tabText(1) and "Tax" in bh.tabText(2)
        assert bh.tabText(3) == "Company"
        assert bh.tabText(4) == "AI"
    finally:
        w.close()


def test_reconcile_hub_hosts_bank_import_document_intake_and_statement_intake(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Reconcile hub hosts the existing Bank statements + Documents tabs and the
    new phase-1 Bank Statement Intake (review-first) sub-tab as the rightmost
    option. Top-level tabs are unaffected (still eleven, locked elsewhere)."""
    from desktop_app.main import MainWindow

    db_path = tmp_path / "reconcile_hub.db"
    BankDatabase(str(db_path)).close()
    w = MainWindow(db_path=str(db_path))
    try:
        rh = w._reconcile_hub
        # Merged Reconcile hub: Bank statements, Documents, AR / Invoices (HEAD),
        # Statement intake (review) (dev).
        assert rh.count() == 4
        assert rh.widget(0) is w._bank_tab
        assert rh.widget(1) is w._intake_widget
        assert rh.tabText(0) == "Bank statements"
        assert rh.tabText(1) == "Documents"
        assert rh.tabText(2) == "AR / Invoices"
        assert rh.widget(2) is w._ar_recon_widget
        assert rh.widget(3) is w._statement_intake_panel
        assert rh.tabText(3) == "Statement intake (review)"
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
