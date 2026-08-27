"""Company Snapshot data helpers — live invoices/bills, honest empty years."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from probooksai import business
from probooksai import qb_snapshot as snap
from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import apply_extensions

_TODAY = date(2026, 8, 27)
_FORBIDDEN = (
    "BST LINEHAUL",
    "FLATIRON",
    "CHASE BANK",
    "1099 SUBHAULERS",
    "126,845",
    "656,881",
)


@pytest.fixture
def db(tmp_path: Path) -> BankDatabase:
    b = BankDatabase(db_path=str(tmp_path / "snapshot.db"))
    apply_extensions(b._conn)
    yield b
    b.close()


def test_empty_file_has_no_invented_prior_years(db: BankDatabase) -> None:
    income = snap.yearly_income(db._conn, today=_TODAY)
    expense = snap.yearly_expense(db._conn, today=_TODAY)
    assert [r["year"] for r in income] == [2026]
    assert [r["year"] for r in expense] == [2026]
    assert income[0]["amount"] == 0.0
    assert expense[0]["amount"] == 0.0
    assert income[0]["is_current"] is True
    months = snap.monthly_income_expense(db._conn, today=_TODAY)
    assert [m["label"] for m in months] == [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
    ]
    assert all(m["income"] == 0.0 and m["expense"] == 0.0 for m in months)
    assert snap.customers_who_owe(db._conn, today=_TODAY) == []
    assert snap.top_customers_by_sales(db._conn, today=_TODAY) == []
    assert snap.expense_breakdown(db._conn, today=_TODAY) == []


def test_prior_year_gap_is_not_filled_with_fake_revenue(db: BankDatabase) -> None:
    cid = business.add_customer(db._conn, "Harbor Logistics")
    business.create_invoice(
        db._conn,
        cid,
        "INV-24",
        "2024-03-15",
        due_date="2024-04-15",
        lines=[{"description": "Haul", "qty": 1, "rate": 200.0}],
    )
    business.create_invoice(
        db._conn,
        cid,
        "INV-26",
        "2026-02-10",
        due_date="2026-03-10",
        lines=[{"description": "Haul", "qty": 1, "rate": 80.0}],
    )
    years = snap.yearly_income(db._conn, today=_TODAY)
    assert [r["year"] for r in years] == [2024, 2026]
    by_year = {r["year"]: r["amount"] for r in years}
    assert by_year[2024] == pytest.approx(200.0)
    assert by_year[2026] == pytest.approx(80.0)
    assert 2021 not in by_year
    assert 2025 not in by_year


def test_owe_overdue_top_customers_and_balances(db: BankDatabase) -> None:
    aid = db.add_bank_account("Operating", "1111", "Bank")
    db.insert_manual_transaction(aid, "2026-08-01", 250.00, description="Opening")
    c1 = business.add_customer(db._conn, "Harbor Logistics")
    c2 = business.add_customer(db._conn, "Westside Hauling")
    business.create_invoice(
        db._conn,
        c1,
        "INV-1",
        "2026-01-15",
        due_date="2026-02-01",
        lines=[{"description": "Haul", "qty": 1, "rate": 400.0}],
    )
    business.create_invoice(
        db._conn,
        c2,
        "INV-2",
        "2026-08-01",
        due_date="2026-09-01",
        lines=[{"description": "Haul", "qty": 1, "rate": 90.0}],
    )
    vid = business.add_vendor(db._conn, "Office Supplies Co")
    business.create_bill(
        db._conn, vid, "2026-03-01", 50.0, vendor_invoice_number="OS-1", due_date="2026-03-15"
    )
    owe = snap.customers_who_owe(db._conn, today=_TODAY)
    names = [r["name"] for r in owe]
    assert names[0] == "Harbor Logistics"
    harbor = next(r for r in owe if r["name"] == "Harbor Logistics")
    assert harbor["is_overdue"] is True
    assert harbor["amount_due"] == pytest.approx(400.0)
    west = next(r for r in owe if r["name"] == "Westside Hauling")
    assert west["is_overdue"] is False
    top = snap.top_customers_by_sales(db._conn, today=_TODAY)
    assert top[0]["name"] == "Harbor Logistics"
    assert top[0]["sales"] == pytest.approx(400.0)
    months = snap.monthly_income_expense(db._conn, today=_TODAY)
    by_m = {m["label"]: m for m in months}
    assert by_m["Jan"]["income"] == pytest.approx(400.0)
    assert by_m["Mar"]["expense"] == pytest.approx(50.0)
    bals = {r["name"]: r["balance"] for r in snap.account_balances(db._conn)}
    assert bals["Accounts Receivable"] == pytest.approx(490.0)
    assert bals["Accounts Payable"] == pytest.approx(50.0)
    assert bals["Operating"] == pytest.approx(250.0)


def test_expense_breakdown_uses_bank_coa_when_gl_empty(db: BankDatabase) -> None:
    aid = db.add_bank_account("Checking", "1000", "Bank")
    db.insert_manual_transaction(
        aid,
        "2026-06-02",
        -80.00,
        description="Fuel Vendor",
        coa_account="6310 Vehicle Expense",
    )
    db.insert_manual_transaction(
        aid,
        "2026-06-03",
        -20.00,
        description="Office Supplies Co",
        coa_account="6220 Office Supplies",
    )
    pie = snap.expense_breakdown(db._conn, today=_TODAY)
    labels = [r["label"] for r in pie]
    assert "6310 Vehicle Expense" in labels
    assert "6220 Office Supplies" in labels
    assert pie[0]["amount"] == pytest.approx(80.0)


def test_snapshot_helpers_have_no_live_company_identity() -> None:
    text = Path("probooksai/qb_snapshot.py").read_text(encoding="utf-8")
    lowered = text.lower()
    for needle in _FORBIDDEN:
        assert needle.lower() not in lowered
