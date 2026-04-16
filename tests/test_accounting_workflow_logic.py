"""AR/AP workflow data paths mirrored by accounting workflow tabs (no Qt).

Invoices and bills live in extension tables; customer/vendor payments that hit the bank
use :meth:`probooksai.bank_import.BankDatabase.insert_manual_transaction`.
"""

from __future__ import annotations

import pytest

from probooksai import business
from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import apply_extensions


@pytest.fixture
def db(tmp_path):
    b = BankDatabase(db_path=str(tmp_path / "t.db"))
    apply_extensions(b._conn)
    yield b
    b.close()


def test_create_invoice_appears_in_list_no_bank_row_yet(db: BankDatabase) -> None:
    aid = db.add_bank_account("Checking")
    cid = business.add_customer(db._conn, "Acme")
    inv_id = business.create_invoice(
        db._conn,
        cid,
        "INV-1",
        "2024-06-01",
        lines=[{"description": "Work", "qty": 1, "rate": 50.0}],
    )
    rows = business.list_invoices(db._conn)
    assert any(int(r["id"]) == inv_id for r in rows)
    n = db._conn.execute(
        "SELECT COUNT(*) AS c FROM bank_transactions WHERE bank_account_id = ?",
        (aid,),
    ).fetchone()["c"]
    assert int(n) == 0


def test_receive_payment_reduces_ar_and_creates_register_deposit(db: BankDatabase) -> None:
    aid = db.add_bank_account("Checking")
    cid = business.add_customer(db._conn, "Acme")
    inv_id = business.create_invoice(
        db._conn,
        cid,
        "INV-1",
        "2024-06-01",
        lines=[{"description": "Work", "qty": 1, "rate": 50.0}],
    )
    pid = business.record_ar_payment(
        db._conn,
        cid,
        "2024-06-09",
        50.0,
        [(inv_id, 50.0)],
        bank_account_id=aid,
        method="Check",
        memo="Invoice INV-1",
    )
    tid = db.insert_manual_transaction(
        aid,
        "2024-06-09",
        50.0,
        description="Customer payment — Inv. INV-1",
        memo=f"ar_payment:{pid}",
    )
    inv = db._conn.execute(
        "SELECT balance_due, status FROM invoices WHERE id = ?", (inv_id,)
    ).fetchone()
    assert float(inv["balance_due"]) == pytest.approx(0.0)
    row = db._conn.execute(
        "SELECT amount, memo FROM bank_transactions WHERE id = ?", (tid,)
    ).fetchone()
    assert float(row["amount"]) == pytest.approx(50.0)
    assert f"ar_payment:{pid}" in (row["memo"] or "")


def test_create_bill_appears_in_list_no_bank_row_yet(db: BankDatabase) -> None:
    aid = db.add_bank_account("Checking")
    vid = business.add_vendor(db._conn, "VendorCo")
    bill_id = business.create_bill(db._conn, vid, "2024-07-01", 120.0)
    rows = business.list_bills(db._conn)
    assert any(int(r["id"]) == bill_id for r in rows)
    n = db._conn.execute(
        "SELECT COUNT(*) AS c FROM bank_transactions WHERE bank_account_id = ?",
        (aid,),
    ).fetchone()["c"]
    assert int(n) == 0


def test_pay_bill_reduces_ap_and_creates_register_outflow(db: BankDatabase) -> None:
    aid = db.add_bank_account("Checking")
    vid = business.add_vendor(db._conn, "VendorCo")
    bill_id = business.create_bill(db._conn, vid, "2024-07-01", 120.0)
    pid = business.record_ap_payment(
        db._conn,
        vid,
        "2024-07-15",
        120.0,
        [(bill_id, 120.0)],
        bank_account_id=aid,
        method="Check",
        memo=f"Bill #{bill_id}",
    )
    tid = db.insert_manual_transaction(
        aid,
        "2024-07-15",
        -120.0,
        description=f"Vendor payment — Bill #{bill_id}",
        memo=f"ap_payment:{pid}",
    )
    bill = db._conn.execute(
        "SELECT balance_due, status FROM bills WHERE id = ?", (bill_id,)
    ).fetchone()
    assert float(bill["balance_due"]) == pytest.approx(0.0)
    row = db._conn.execute(
        "SELECT amount, memo FROM bank_transactions WHERE id = ?", (tid,)
    ).fetchone()
    assert float(row["amount"]) == pytest.approx(-120.0)
    assert f"ap_payment:{pid}" in (row["memo"] or "")
