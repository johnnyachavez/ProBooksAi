"""Reports tab: AR/AP receivables & payables views (More → Reports)."""

from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QApplication

from desktop_app.reports_tab import ReportsTab
from probooksai import business
from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import apply_extensions


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_reports_tab_ar_ap_buttons_fill_tables(qapp: QApplication, tmp_path) -> None:
    db_path = tmp_path / "reports_ar_ap.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "RepCust")
    business.create_invoice(
        db._conn,
        cid,
        "R-100",
        "2025-01-15",
        due_date="2025-02-01",
        lines=[{"description": "Work", "qty": 1.0, "rate": 100.0}],
    )
    vid = business.add_vendor(db._conn, "RepVend")
    business.create_bill(
        db._conn,
        vid,
        "2025-01-10",
        50.0,
        vendor_invoice_number="V-900",
        due_date="2025-02-15",
    )
    tab = ReportsTab(db._conn)
    tab._show_ar_aging()
    assert tab._table.rowCount() >= 1
    tab._show_ap_aging()
    assert tab._table.rowCount() >= 1
    tab._show_open_invoices()
    assert tab._table.rowCount() >= 1
    tab._show_open_bills()
    assert tab._table.rowCount() >= 1
    tab._show_recent_ar_payments()
    assert tab._table.rowCount() == 0
    tab._show_recent_ap_payments()
    assert tab._table.rowCount() == 0
    assert tab._last_export is not None
    tab.activate_report("open_inv")
    assert tab._table.columnCount() == 8
    assert "Invoice id" in [
        tab._table.horizontalHeaderItem(c).text() for c in range(tab._table.columnCount())
    ]
    db.close()


def test_reports_tab_activate_report(qapp: QApplication, tmp_path) -> None:
    db_path = tmp_path / "reports_activate.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "ActCo")
    business.create_invoice(
        db._conn,
        cid,
        "A-1",
        "2025-03-01",
        lines=[{"description": "x", "qty": 1.0, "rate": 10.0}],
    )
    tab = ReportsTab(db._conn)
    tab.activate_report("ar_aging")
    assert tab._last_report_kind == "ar_aging"
    tab.activate_report("open_invoices")
    assert tab._last_report_kind == "open_inv"
    db.close()
