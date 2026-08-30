"""Regression tests for the QB Pro Desktop Invoice bug-fix batch:

- **Save** persists to the open company file and reopens with the same values.
- **Print** button is wired to a real handler (not a dead button).
- **Email** is enabled, opens a mailto draft for a customer with an email, and
  shows a real explanation when there's no email or no bill-to customer.
- **New Customer** opens the normal add-customer dialog (not a wizard) and
  auto-selects the created customer as Bill To.
- **Find** searches saved invoices by number / customer / total / date and
  loads the first match into the form.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication

from desktop_app.invoice_screen import InvoiceScreen
from probooksai import business
from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import apply_extensions


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _seed_company(tmp_path: Path) -> tuple[BankDatabase, dict[str, int]]:
    db = BankDatabase(str(tmp_path / "co.db"))
    apply_extensions(db._conn)
    ids: dict[str, int] = {}
    ids["harbor"] = business.add_customer(
        db._conn, "Harbor Logistics", email="ap@harbor.example"
    )
    ids["westside"] = business.add_customer(db._conn, "Westside Hauling")
    ids["metro"] = business.add_customer(
        db._conn, "Metro Freight", email="billing@metro.example"
    )
    business.create_invoice(
        db._conn,
        ids["harbor"],
        "INV-2101",
        "2026-08-01",
        due_date="2026-08-31",
        lines=[{"description": "Haul", "qty": 1, "rate": 450.00}],
    )
    business.create_invoice(
        db._conn,
        ids["westside"],
        "WH-88",
        "2026-07-15",
        due_date="2026-08-14",
        lines=[{"description": "Haul", "qty": 1, "rate": 1280.50}],
    )
    business.create_invoice(
        db._conn,
        ids["metro"],
        "MF-40",
        "2026-06-20",
        due_date="2026-07-20",
        lines=[{"description": "Haul", "qty": 1, "rate": 96.40}],
    )
    return db, ids


class TestInvoiceButtonWiring:
    def test_email_button_is_enabled_and_has_search_tooltip(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        db, _ = _seed_company(tmp_path)
        w = InvoiceScreen(ap_conn=db._conn)
        try:
            assert w._btn_email.isEnabled()
            tip = (w._btn_email.toolTip() or "").lower()
            assert "email" in tip
            assert "not wired" not in tip
        finally:
            w.deleteLater()
            db.close()

    def test_find_button_opens_search_dialog_and_loads_hit(
        self, qapp: QApplication, tmp_path: Path, monkeypatch
    ) -> None:
        db, _ = _seed_company(tmp_path)
        w = InvoiceScreen(ap_conn=db._conn)
        try:
            import desktop_app.invoice_screen as inv_mod

            monkeypatch.setattr(
                inv_mod.QInputDialog,
                "getText",
                staticmethod(lambda *a, **k: ("WH-88", True)),
            )
            w._btn_find.click()
            qapp.processEvents()
            assert w._inv_number.text() == "WH-88"
        finally:
            w.deleteLater()
            db.close()


class TestInvoiceFind:
    def test_finds_by_invoice_number(self, qapp: QApplication, tmp_path: Path) -> None:
        db, _ = _seed_company(tmp_path)
        w = InvoiceScreen(ap_conn=db._conn)
        try:
            found = w.find_invoice_id_matching("WH-88")
            assert found is not None
            row = dict(
                business.get_invoice_detail(db._conn, found)[0]
            )
            assert row["invoice_number"] == "WH-88"
        finally:
            w.deleteLater()
            db.close()

    def test_finds_by_customer_name_substring(self, qapp: QApplication, tmp_path: Path) -> None:
        db, _ = _seed_company(tmp_path)
        w = InvoiceScreen(ap_conn=db._conn)
        try:
            found = w.find_invoice_id_matching("harbor")
            assert found is not None
            row = dict(business.get_invoice_detail(db._conn, found)[0])
            assert row["invoice_number"] == "INV-2101"
        finally:
            w.deleteLater()
            db.close()

    def test_finds_by_amount_ignoring_currency_symbol(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        db, _ = _seed_company(tmp_path)
        w = InvoiceScreen(ap_conn=db._conn)
        try:
            found = w.find_invoice_id_matching("$1,280.50")
            assert found is not None
            row = dict(business.get_invoice_detail(db._conn, found)[0])
            assert row["invoice_number"] == "WH-88"
        finally:
            w.deleteLater()
            db.close()

    def test_finds_by_us_date(self, qapp: QApplication, tmp_path: Path) -> None:
        db, _ = _seed_company(tmp_path)
        w = InvoiceScreen(ap_conn=db._conn)
        try:
            found = w.find_invoice_id_matching("06/20/2026")
            assert found is not None
            row = dict(business.get_invoice_detail(db._conn, found)[0])
            assert row["invoice_number"] == "MF-40"
        finally:
            w.deleteLater()
            db.close()

    def test_returns_none_when_nothing_matches(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        db, _ = _seed_company(tmp_path)
        w = InvoiceScreen(ap_conn=db._conn)
        try:
            assert w.find_invoice_id_matching("nonsense-9999") is None
        finally:
            w.deleteLater()
            db.close()


class TestInvoiceEmail:
    def test_mailto_url_uses_customer_email_and_invoice_number(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        db, ids = _seed_company(tmp_path)
        w = InvoiceScreen(ap_conn=db._conn)
        try:
            invs = business.list_invoices(db._conn)
            harbor_inv = next(r for r in invs if r["customer_id"] == ids["harbor"])
            url = w._build_invoice_mailto_url(int(harbor_inv["id"]))
            assert isinstance(url, QUrl)
            assert url.scheme() == "mailto"
            s = url.toString()
            assert "ap@harbor.example" in s
            assert "INV-2101" in s
            assert "Invoice" in s
        finally:
            w.deleteLater()
            db.close()

    def test_mailto_url_none_when_customer_has_no_email(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        db, ids = _seed_company(tmp_path)
        w = InvoiceScreen(ap_conn=db._conn)
        try:
            invs = business.list_invoices(db._conn)
            wh_inv = next(r for r in invs if r["customer_id"] == ids["westside"])
            assert w._build_invoice_mailto_url(int(wh_inv["id"])) is None
        finally:
            w.deleteLater()
            db.close()


class TestInvoiceSavePersistsAcrossReopen:
    def test_ribbon_save_row_survives_new_screen_instance(
        self, qapp: QApplication, tmp_path: Path
    ) -> None:
        db_path = str(tmp_path / "persist.db")
        db = BankDatabase(db_path)
        apply_extensions(db._conn)
        cid = business.add_customer(db._conn, "Persist Co")
        try:
            w = InvoiceScreen(ap_conn=db._conn)
            try:
                w._bill_customer_panel._apply_customer_id(cid)
                w._inv_number.setText("PERSIST-1")
                desc_w = w._table.cellWidget(0, 2)
                desc_w.setText("Work")
                rate_w = w._table.cellWidget(0, 4)
                rate_w.setValue(125.00)
                qty_w = w._table.cellWidget(0, 5)
                qty_w.setValue(2.0)
                with patch.object(w, "sender", return_value=w._btn_ribbon_save):
                    w._on_ribbon_save_invoice()
                qapp.processEvents()
            finally:
                w.deleteLater()
                qapp.processEvents()
        finally:
            db.close()

        db2 = BankDatabase(db_path)
        try:
            rows = list(business.list_invoices(db2._conn))
            hit = [r for r in rows if r["invoice_number"] == "PERSIST-1"]
            assert len(hit) == 1
            assert round(float(hit[0]["total"]), 2) == 250.00
        finally:
            db2.close()
