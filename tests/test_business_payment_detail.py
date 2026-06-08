"""business.get_ar_payment_detail / get_ap_payment_detail."""

from __future__ import annotations

import pytest

from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import apply_extensions
from probooksai import business


def test_get_ar_payment_detail(tmp_path) -> None:
    db_path = tmp_path / "g_ar.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "C")
    inv = business.create_invoice(
        db._conn,
        cid,
        "N1",
        "2025-01-01",
        lines=[{"description": "x", "qty": 1, "rate": 10.0}],
    )
    pid = business.record_ar_payment(
        db._conn,
        cid,
        "2025-01-05",
        10.0,
        [(inv, 10.0)],
    )
    row, allocs = business.get_ar_payment_detail(db._conn, pid)
    assert row is not None
    assert dict(row)["customer_name"] == "C"
    assert len(allocs) == 1
    assert int(dict(allocs[0])["invoice_id"]) == inv
    db.close()


def test_get_ap_payment_detail(tmp_path) -> None:
    db_path = tmp_path / "g_ap.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    vid = business.add_vendor(db._conn, "V")
    bid = business.create_bill(
        db._conn,
        vid,
        "2025-01-01",
        0.0,
        vendor_invoice_number="X1",
        expense_lines=[
            {
                "line_date": "",
                "ticket_ref": "",
                "amount": 7.0,
                "memo": "",
                "customer_job": "",
            }
        ],
    )
    pid = business.record_ap_payment(
        db._conn,
        vid,
        "2025-01-10",
        7.0,
        [(bid, 7.0)],
    )
    row, allocs = business.get_ap_payment_detail(db._conn, pid)
    assert row is not None
    assert dict(row)["vendor_name"] == "V"
    assert len(allocs) == 1
    assert int(dict(allocs[0])["bill_id"]) == bid
    db.close()
