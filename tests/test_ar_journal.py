"""Tests for AR journal-entry wiring in probooksai.business."""

from __future__ import annotations

import sqlite3

import pytest

from probooksai.bank_import import BankDatabase
from probooksai.coa_db import COADatabase
from probooksai.extensions_schema import apply_extensions
from probooksai.gl import GLDatabase
from probooksai import business


# ---------------------------------------------------------------------------
# Fixture: full-schema DB (bank + extensions + GL + COA stub)
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    b = BankDatabase(db_path=str(tmp_path / "t.db"))
    apply_extensions(b._conn)
    COADatabase(b._conn)  # creates coa_accounts table
    GLDatabase(b._conn)   # creates journal_entries / journal_entry_lines
    # Minimal COA rows for AR wiring
    _ts = "2025-01-01T00:00:00+00:00"
    for acct in [
        ("1100", "Accounts Receivable", "asset",     "debit"),
        ("4100", "Service Revenue",     "revenue",   "credit"),
        ("2110", "Sales Tax Payable",   "liability", "credit"),
    ]:
        b._conn.execute(
            "INSERT OR IGNORE INTO coa_accounts "
            "(account_number, account_name, account_type, normal_balance, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (*acct, _ts),
        )
    b._conn.commit()
    yield b
    b.close()


def _journal_lines(conn: sqlite3.Connection, source: str) -> list[dict]:
    entry = conn.execute(
        "SELECT id FROM journal_entries WHERE source = ?", (source,)
    ).fetchone()
    if entry is None:
        return []
    rows = conn.execute(
        "SELECT account, debit, credit FROM journal_entry_lines WHERE entry_id = ? ORDER BY id",
        (entry["id"],),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_create_invoice_posts_ar_journal(db):
    cid = business.add_customer(db._conn, "Acme Corp")
    inv_id = business.create_invoice(
        db._conn, cid, "INV-001", "2025-01-15",
        lines=[{"description": "Trucking", "qty": 1, "rate": 1000.0}],
        tax_rate_pct=0.0,
    )
    lines = _journal_lines(db._conn, f"ar_invoice:{inv_id}")
    assert len(lines) == 2, f"Expected 2 lines, got {lines}"
    dr_line = next(l for l in lines if l["debit"] > 0)
    cr_line = next(l for l in lines if l["credit"] > 0)
    assert "1100" in dr_line["account"]
    assert dr_line["debit"] == pytest.approx(1000.0)
    assert "4100" in cr_line["account"]
    assert cr_line["credit"] == pytest.approx(1000.0)


def test_create_invoice_with_tax_posts_three_lines(db):
    cid = business.add_customer(db._conn, "Taxable Co")
    inv_id = business.create_invoice(
        db._conn, cid, "INV-002", "2025-02-01",
        lines=[{"description": "Service", "qty": 1, "rate": 500.0}],
        tax_rate_pct=10.0,
    )
    lines = _journal_lines(db._conn, f"ar_invoice:{inv_id}")
    assert len(lines) == 3, f"Expected 3 lines, got {lines}"
    accounts = {l["account"] for l in lines}
    assert any("1100" in a for a in accounts)  # AR
    assert any("4100" in a for a in accounts)  # Revenue
    assert any("2110" in a for a in accounts)  # Tax payable

    dr_total = sum(l["debit"] for l in lines)
    cr_total = sum(l["credit"] for l in lines)
    assert dr_total == pytest.approx(cr_total)
    assert dr_total == pytest.approx(550.0)  # 500 + 10%


def test_update_invoice_replaces_journal(db):
    cid = business.add_customer(db._conn, "Edit Corp")
    inv_id = business.create_invoice(
        db._conn, cid, "INV-003", "2025-03-01",
        lines=[{"description": "Old", "qty": 1, "rate": 200.0}],
    )
    source = f"ar_invoice:{inv_id}"
    old_lines = _journal_lines(db._conn, source)
    assert old_lines[0]["debit"] == pytest.approx(200.0)

    business.update_invoice(
        db._conn, inv_id, cid, "INV-003", "2025-03-01",
        lines=[{"description": "New", "qty": 1, "rate": 300.0}],
    )
    new_lines = _journal_lines(db._conn, source)
    assert len(new_lines) == 2
    dr_line = next(l for l in new_lines if l["debit"] > 0)
    assert dr_line["debit"] == pytest.approx(300.0)


def test_backfill_ar_invoice_journals(db):
    """backfill_ar_invoice_journals posts entries only for invoices missing one."""
    cid = business.add_customer(db._conn, "Backfill Co")
    # Create two invoices — they auto-post on create
    i1 = business.create_invoice(db._conn, cid, "B1", "2025-04-01",
                                  lines=[{"description": "x", "qty": 1, "rate": 100.0}])
    i2 = business.create_invoice(db._conn, cid, "B2", "2025-04-02",
                                  lines=[{"description": "y", "qty": 1, "rate": 200.0}])

    # Manually delete the entry for i2 to simulate a legacy invoice
    old = db._conn.execute(
        "SELECT id FROM journal_entries WHERE source = ?", (f"ar_invoice:{i2}",)
    ).fetchone()
    db._conn.execute("DELETE FROM journal_entry_lines WHERE entry_id = ?", (old["id"],))
    db._conn.execute("DELETE FROM journal_entries WHERE id = ?", (old["id"],))
    db._conn.commit()

    created = business.backfill_ar_invoice_journals(db._conn)
    assert created == 1  # only i2 was missing

    lines = _journal_lines(db._conn, f"ar_invoice:{i2}")
    assert len(lines) == 2


def test_fix_revenue_account_types(db):
    """_fix_revenue_account_types corrects expense-typed 4xxx accounts."""
    db._conn.execute(
        "INSERT OR IGNORE INTO coa_accounts "
        "(account_number, account_name, account_type, normal_balance, created_at) "
        "VALUES ('4200', 'Other Revenue', 'expense', 'credit', '2025-01-01T00:00:00+00:00')"
    )
    db._conn.commit()
    business._fix_revenue_account_types(db._conn)
    row = db._conn.execute(
        "SELECT account_type FROM coa_accounts WHERE account_number = '4200'"
    ).fetchone()
    assert row["account_type"] == "revenue"


def test_ar_payment_posts_journal(db):
    """record_ar_payment posts DR cash / CR AR journal entry."""
    cid = business.add_customer(db._conn, "Payer Inc")
    inv_id = business.create_invoice(
        db._conn, cid, "PAY-001", "2025-05-01",
        lines=[{"description": "Svc", "qty": 1, "rate": 400.0}],
    )
    pid = business.record_ar_payment(
        db._conn, cid, "2025-05-10", 400.0,
        allocations=[(inv_id, 400.0)],
        bank_account_id=None,
        reference="CHK-9001",
    )
    lines = _journal_lines(db._conn, f"ar_payment:{pid}")
    assert len(lines) == 2
    dr_line = next(l for l in lines if l["debit"] > 0)
    cr_line = next(l for l in lines if l["credit"] > 0)
    assert dr_line["debit"] == pytest.approx(400.0)
    assert "Undeposited Funds" in (dr_line["account"] or "")
    assert "1100" in cr_line["account"]
    assert cr_line["credit"] == pytest.approx(400.0)
