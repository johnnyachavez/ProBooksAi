"""Company Home (DashboardTab) — QB Pro overview shortcuts open existing screens."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QLabel, QToolButton

from desktop_app.calendar_screen import CalendarScreen
from desktop_app.check_screen import CheckScreen
from desktop_app.coa_tab import COATab
from desktop_app.dashboard_tab import DashboardTab
from desktop_app.enter_bills_screen import EnterBillsScreen
from desktop_app.invoice_codes_screen import InvoiceCodesScreen
from desktop_app.invoice_screen import InvoiceScreen
from desktop_app.make_deposits_screen import MakeDepositsScreen
from desktop_app.pay_bills_screen import PayBillsScreen
from desktop_app.receive_checks_screen import ReceiveChecksScreen
from desktop_app.register_tab import RegisterTab
from desktop_app.theme import BG_PRIMARY, apply_dark_theme
from desktop_app.tracker_screens import BillTrackerScreen, IncomeTrackerScreen
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
    b = BankDatabase(db_path=str(tmp_path / "home.db"))
    apply_extensions(b._conn)
    yield b
    b.close()


def _caption_plain(btn: QToolButton) -> str:
    return (btn.text() or "").replace("\n", " ").replace("&&", "&")


_DAILY_LOOP = (
    ("homeShortcut_invoices", "Create Invoices"),
    ("homeShortcut_payments", "Receive Payments"),
    ("homeShortcut_bills", "Enter Bills"),
    ("homeShortcut_pay_bills", "Pay Bills"),
    ("homeShortcut_checks", "Write Checks"),
    ("homeShortcut_deposits", "Record Deposits"),
)

_OTHER_EXISTING = (
    ("homeShortcut_register", "Check Register"),
    ("homeShortcut_reconcile", "Reconcile"),
    ("homeShortcut_coa", "Chart of Accounts"),
    ("homeShortcut_codes", "Items & Services"),
)


def test_home_layout_has_qb_boxes_and_daily_loop_captions(
    qapp: QApplication, db: BankDatabase
) -> None:
    w = DashboardTab(db._conn)
    labels = [lb.text() for lb in w.findChildren(QLabel)]
    assert "VENDORS" in labels
    assert "CUSTOMERS" in labels
    assert "COMPANY" in labels
    assert "BANKING" in labels
    assert "Account Balances" in labels
    assert "COMPANY NAME" in labels
    btns = {b.objectName(): _caption_plain(b) for b in w.findChildren(QToolButton)}
    for name, caption in _DAILY_LOOP + _OTHER_EXISTING:
        assert btns[name] == caption
    assert btns["homeShortcut_income_tracker"] == "Income Tracker"
    assert btns["homeShortcut_bill_tracker"] == "Bill Tracker"
    assert btns["homeShortcut_calendar"] == "Calendar"
    codes = w.findChild(QToolButton, "homeShortcut_codes")
    assert codes is not None
    assert "&&" in codes.text()
    w.close()


def test_home_captions_stay_light_under_app_dark_theme(
    qapp: QApplication, db: BankDatabase
) -> None:
    """App dark theme must not paint navy redaction bars behind Home captions."""
    old_ss = qapp.styleSheet()
    old_pal = QPalette(qapp.palette())
    try:
        apply_dark_theme(qapp)
        w = DashboardTab(db._conn)
        w.show()
        qapp.processEvents()
        navy = BG_PRIMARY.lower()
        page_fill = w.palette().color(QPalette.ColorRole.Window).name().lower()
        assert page_fill != navy
        assert page_fill in ("#e8ecf1", "#ffffff", "#f4f7fa")
        assert navy not in w.styleSheet().lower()
        for badge in w.findChildren(QLabel, "homeSectionBadge"):
            cap_ss = badge.styleSheet().lower()
            assert navy not in cap_ss
            assert "#1a1a2e" not in cap_ss
            assert "#2563a8" in cap_ss
            fill = badge.palette().color(QPalette.ColorRole.Window).name().lower()
            assert fill != navy
        for btn in w.findChildren(QToolButton):
            if not btn.objectName().startswith("homeShortcut_"):
                continue
            ss = btn.styleSheet().lower()
            assert navy not in ss
            assert "#1a1a1a" in ss
            assert "transparent" in ss
        placeholder = w.findChild(QLabel, "homeCompanyPlaceholder")
        assert placeholder is not None
        ph_ss = placeholder.styleSheet().lower()
        assert navy not in ph_ss
        assert "#4a5560" in ph_ss
        w.close()
    finally:
        qapp.setStyleSheet(old_ss)
        qapp.setPalette(old_pal)


def test_home_defaults_have_no_live_company_identity(qapp: QApplication) -> None:
    text = Path("desktop_app/dashboard_tab.py").read_text(encoding="utf-8")
    lowered = text.lower()
    assert "chavan" not in lowered
    assert "xx-xxxxxxx" not in lowered
    assert "ssn" not in lowered
    assert "tax id" not in lowered
    assert "COMPANY NAME" in text


def test_home_shortcuts_emit_navigation_keys(qapp: QApplication, db: BankDatabase) -> None:
    w = DashboardTab(db._conn)
    received: list[str] = []
    w.navigateRequested.connect(received.append)
    expected = {
        "homeShortcut_invoices": "invoices",
        "homeShortcut_payments": "payments",
        "homeShortcut_bills": "bills",
        "homeShortcut_pay_bills": "pay_bills",
        "homeShortcut_checks": "checks",
        "homeShortcut_deposits": "deposits",
        "homeShortcut_register": "register",
        "homeShortcut_reconcile": "reconcile",
        "homeShortcut_coa": "coa",
        "homeShortcut_codes": "codes",
        "homeShortcut_income_tracker": "income_tracker",
        "homeShortcut_bill_tracker": "bill_tracker",
        "homeShortcut_calendar": "calendar",
    }
    for name, key in expected.items():
        btn = w.findChild(QToolButton, name)
        assert btn is not None, name
        received.clear()
        btn.click()
        qapp.processEvents()
        assert received == [key], (name, received)
    w.close()


def test_home_opens_existing_daily_loop_screens(qapp: QApplication, tmp_path: Path) -> None:
    from desktop_app.main import MainWindow

    db_path = tmp_path / "home_nav.db"
    BankDatabase(str(db_path)).close()
    w = MainWindow(db_path=str(db_path))
    try:
        tabs = w._tabs
        assert tabs.tabText(0) == "Home"
        assert tabs.currentWidget() is w._dashboard_tab
        mapping = (
            ("homeShortcut_invoices", w._invoice_screen, InvoiceScreen),
            ("homeShortcut_payments", w._receive_payments_screen, ReceiveChecksScreen),
            ("homeShortcut_bills", w._enter_bills_screen, EnterBillsScreen),
            ("homeShortcut_pay_bills", w._pay_bills_screen, PayBillsScreen),
            ("homeShortcut_checks", w._check_screen, CheckScreen),
            ("homeShortcut_deposits", w._make_deposits_screen, MakeDepositsScreen),
            ("homeShortcut_coa", w._coa_tab, COATab),
            ("homeShortcut_codes", w._invoice_codes_screen, InvoiceCodesScreen),
            ("homeShortcut_income_tracker", w._income_tracker_screen, IncomeTrackerScreen),
            ("homeShortcut_bill_tracker", w._bill_tracker_screen, BillTrackerScreen),
            ("homeShortcut_calendar", w._calendar_screen, CalendarScreen),
        )
        for name, screen, spec in mapping:
            tabs.setCurrentIndex(0)
            qapp.processEvents()
            btn = w._dashboard_tab.findChild(QToolButton, name)
            assert btn is not None, name
            btn.click()
            qapp.processEvents()
            assert tabs.currentWidget() is screen, name
            assert isinstance(tabs.currentWidget(), spec)
        tabs.setCurrentIndex(0)
        rec = w._dashboard_tab.findChild(QToolButton, "homeShortcut_reconcile")
        assert rec is not None
        rec.click()
        qapp.processEvents()
        assert tabs.currentWidget() is w._reconcile_root

        from unittest.mock import patch

        from PySide6.QtWidgets import QDialog

        from desktop_app.use_register_dialog import UseRegisterDialog

        try:
            w._bank_db.add_bank_account("Checking")
        except (ValueError, TypeError):
            pass
        w._register_tab.refresh_bank_accounts()
        tabs.setCurrentIndex(0)
        qapp.processEvents()
        btn_reg = w._dashboard_tab.findChild(QToolButton, "homeShortcut_register")
        assert btn_reg is not None
        with patch.object(
            UseRegisterDialog, "exec", return_value=int(QDialog.DialogCode.Accepted)
        ):
            btn_reg.click()
            qapp.processEvents()
        assert tabs.currentWidget() is w._register_tab
        assert isinstance(tabs.currentWidget(), RegisterTab)
    finally:
        w.close()


def test_home_undeposited_badge_and_balances(qapp: QApplication, db: BankDatabase) -> None:
    from probooksai import business

    aid = db.add_bank_account("Operating", "1111", "Bank")
    db.insert_manual_transaction(
        aid, "2026-08-01", 250.00, description="Opening"
    )
    cid = business.add_customer(db._conn, "Acme Haul")
    iid = business.create_invoice(
        db._conn,
        cid,
        "HOME-1",
        "2026-08-10",
        lines=[{"description": "Haul", "qty": 1, "rate": 40.0}],
    )
    business.record_ar_payment(
        db._conn,
        cid,
        "2026-08-11",
        40.0,
        [(iid, 40.0)],
        bank_account_id=None,
        method="Check",
        reference="1001",
    )

    w = DashboardTab(db._conn)
    w.refresh()
    qapp.processEvents()
    assert w._btn_deposits._badge == 1
    names = [
        lb.text()
        for lb in w.findChildren(QLabel)
        if lb.objectName() == "homeBalanceName"
    ]
    assert "Accounts Receivable" in names
    assert "Undeposited Funds" in names
    assert "Operating" in names
    w.close()
