"""Tests for probooksai.asset_accounts helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from probooksai.asset_accounts import (
    ASSET_ACCOUNT_TYPES,
    account_activity,
    account_ending_balance,
    list_asset_accounts,
)
from probooksai.bank_import import BankDatabase
from probooksai.coa_db import COADatabase
from probooksai.extensions_schema import apply_extensions
from probooksai.gl import GLDatabase


@pytest.fixture
def dbs(tmp_path: Path) -> tuple[COADatabase, sqlite3.Connection]:
    """Full company DB: bank + extensions + CoA + GL (mirrors business fixtures)."""
    b = BankDatabase(db_path=str(tmp_path / "co.db"))
    apply_extensions(b._conn)
    coa = COADatabase(b._conn)
    GLDatabase(b._conn)
    return coa, b._conn


def _seed_coa(coa: COADatabase) -> dict[str, int]:
    ids: dict[str, int] = {}
    ids["cash"] = coa.add_account("1000", "Cash – Checking", "bank")
    ids["ar"] = coa.add_account("1100", "Accounts receivable", "current_asset")
    ids["prepaid"] = coa.add_account("1200", "Prepaid insurance", "current_asset")
    ids["truck"] = coa.add_account("1500", "Trucks", "fixed_asset", sub_type="Vehicles")
    ids["computer"] = coa.add_account(
        "1510", "Computer & tech", "fixed_asset", sub_type="Computer & Technology"
    )
    ids["deposit"] = coa.add_account("1600", "Security deposit", "other_asset")
    ids["ap"] = coa.add_account("2000", "Accounts payable", "current_liability")
    ids["sales"] = coa.add_account("4000", "Sales", "income")
    ids["office"] = coa.add_account("6000", "Office supplies", "expense")
    return ids


def test_asset_account_types_are_non_bank_debit_normal() -> None:
    assert ASSET_ACCOUNT_TYPES == ("asset", "current_asset", "fixed_asset", "other_asset")
    assert "bank" not in ASSET_ACCOUNT_TYPES


def test_list_asset_accounts_excludes_bank_liability_income_expense(dbs) -> None:
    coa, _ = dbs
    _seed_coa(coa)
    rows = list_asset_accounts(coa._conn)
    numbers = [r["account_number"] for r in rows]
    assert numbers == ["1100", "1200", "1500", "1510", "1600"]
    assert all(r["display"].startswith(r["account_number"] + " – ") for r in rows)


def test_list_asset_accounts_orders_by_number(dbs) -> None:
    coa, _ = dbs
    _seed_coa(coa)
    rows = list_asset_accounts(coa._conn)
    nums = [r["account_number"] for r in rows]
    assert nums == sorted(nums)


def test_list_asset_accounts_hides_inactive_by_default(dbs) -> None:
    coa, _ = dbs
    ids = _seed_coa(coa)
    coa.update_account(ids["prepaid"], "1200", "Prepaid insurance", "current_asset", is_active=False)
    active = [r["account_number"] for r in list_asset_accounts(coa._conn)]
    assert "1200" not in active
    all_incl = [r["account_number"] for r in list_asset_accounts(coa._conn, include_inactive=True)]
    assert "1200" in all_incl


def test_list_asset_accounts_empty_when_no_asset_rows(tmp_path: Path) -> None:
    b = BankDatabase(db_path=str(tmp_path / "empty.db"))
    apply_extensions(b._conn)
    coa = COADatabase(b._conn)
    GLDatabase(b._conn)
    coa.add_account("2000", "Loan", "long_term_liability")
    coa.add_account("4000", "Sales", "income")
    assert list_asset_accounts(coa._conn) == []


def test_account_activity_empty_when_no_matching_lines(dbs) -> None:
    coa, conn = dbs
    _seed_coa(coa)
    gl = GLDatabase(conn)
    assert account_activity(gl._conn, "1500 – Trucks") == []
    assert account_ending_balance([]) == 0.0


def test_account_activity_runs_balance_and_orders_oldest_first(dbs) -> None:
    coa, conn = dbs
    _seed_coa(coa)
    gl = GLDatabase(conn)
    truck_disp = "1500 – Trucks"
    ap_disp = "2000 – Accounts payable"

    gl.create_journal_entry(
        entry_date="2024-03-01",
        memo="Buy truck",
        lines=[
            {"account": truck_disp, "debit": 12000.00, "credit": 0.0, "description": "F-150"},
            {"account": ap_disp, "debit": 0.0, "credit": 12000.00, "description": ""},
        ],
    )
    gl.create_journal_entry(
        entry_date="2024-06-15",
        memo="Sell trailer",
        lines=[
            {"account": ap_disp, "debit": 500.00, "credit": 0.0, "description": ""},
            {"account": truck_disp, "debit": 0.0, "credit": 500.00, "description": "Trailer disposal"},
        ],
    )

    rows = account_activity(gl._conn, truck_disp)
    assert [r["entry_date"] for r in rows] == ["2024-03-01", "2024-06-15"]
    assert [r["debit"] for r in rows] == [12000.00, 0.0]
    assert [r["credit"] for r in rows] == [0.0, 500.00]
    assert [r["running_balance"] for r in rows] == [12000.00, 11500.00]
    assert account_ending_balance(rows) == 11500.00


def test_account_activity_respects_date_range(dbs) -> None:
    coa, conn = dbs
    _seed_coa(coa)
    gl = GLDatabase(conn)
    truck_disp = "1500 – Trucks"
    ap_disp = "2000 – Accounts payable"
    for iso, amt in (("2024-01-15", 100.0), ("2024-04-20", 200.0), ("2024-09-10", 300.0)):
        gl.create_journal_entry(
            entry_date=iso,
            memo="",
            lines=[
                {"account": truck_disp, "debit": amt, "credit": 0.0, "description": ""},
                {"account": ap_disp, "debit": 0.0, "credit": amt, "description": ""},
            ],
        )
    rows = account_activity(gl._conn, truck_disp, start_iso="2024-04-01", end_iso="2024-06-30")
    assert len(rows) == 1
    assert rows[0]["debit"] == 200.0


def test_account_activity_returns_empty_for_blank_or_unknown_account(dbs) -> None:
    coa, conn = dbs
    _seed_coa(coa)
    gl = GLDatabase(conn)
    gl.create_journal_entry(
        entry_date="2024-01-01",
        memo="",
        lines=[
            {"account": "1500 – Trucks", "debit": 1.0, "credit": 0.0, "description": ""},
            {"account": "2000 – Accounts payable", "debit": 0.0, "credit": 1.0, "description": ""},
        ],
    )
    assert account_activity(gl._conn, "") == []
    assert account_activity(gl._conn, "   ") == []
    assert account_activity(gl._conn, "9999 – Missing") == []
