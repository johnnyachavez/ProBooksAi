"""Income Tracker / Bill Tracker data helpers — live invoices and bills, no QB names."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from probooksai import business
from probooksai import trackers as tr
from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import apply_extensions

_TODAY = date(2026, 8, 27)
_FORBIDDEN = (
    "BST LINEHAUL",
    "ANVIL STEEL",
    "JUNIOR STEEL",
    "Hofer Corporation",
    "AR TRUCKING",
    "947,161.35",
    "345,655.57",
    "76,119.50",
)


def _db(tmp_path: Path) -> BankDatabase:
    b = BankDatabase(db_path=str(tmp_path / "trackers.db"))
    apply_extensions(b._conn)
    return b


def _seed(conn) -> dict[str, int]:
    cid = business.add_customer(conn, "Harbor Logistics")
    job = business.add_customer(conn, "Site A", parent_customer_id=cid)
    open_inv = business.create_invoice(
        conn,
        cid,
        "INV-2101",
        "2026-08-10",
        due_date="2026-09-10",
        lines=[{"description": "Haul", "qty": 1, "rate": 400.00}],
    )
    overdue_inv = business.create_invoice(
        conn,
        job,
        "JOB-12",
        "2026-06-01",
        due_date="2026-07-01",
        lines=[{"description": "Haul", "qty": 1, "rate": 150.00}],
    )
    paid_inv = business.create_invoice(
        conn,
        cid,
        "INV-1999",
        "2026-08-01",
        due_date="2026-08-15",
        lines=[{"description": "Haul", "qty": 1, "rate": 80.00}],
    )
    business.record_ar_payment(
        conn, cid, "2026-08-20", 80.00, [(paid_inv, 80.00)], method="Check", reference="1008"
    )
    vid = business.add_vendor(conn, "Office Supplies Co")
    vid2 = business.add_vendor(conn, "Warehouse Supply")
    open_bill = business.create_bill(
        conn, vid, "2026-08-01", 450.00, vendor_invoice_number="OS-1042", due_date="2026-09-01"
    )
    overdue_bill = business.create_bill(
        conn, vid2, "2026-06-15", 96.40, vendor_invoice_number="WS-12", due_date="2026-07-15"
    )
    paid_bill = business.create_bill(
        conn, vid, "2026-08-05", 50.00, vendor_invoice_number="OS-88", due_date="2026-08-20"
    )
    business.record_ap_payment(
        conn, vid, "2026-08-18", 50.00, [(paid_bill, 50.00)], method="Check", reference="1001"
    )
    return {
        "open_inv": open_inv,
        "overdue_inv": overdue_inv,
        "paid_inv": paid_inv,
        "open_bill": open_bill,
        "overdue_bill": overdue_bill,
        "paid_bill": paid_bill,
        "customer": cid,
        "job": job,
        "vendor": vid,
    }


def test_days_range_last_90() -> None:
    start, end = tr.days_range(tr.DATE_LAST_90, _TODAY)
    assert end == _TODAY
    assert start == date(2026, 5, 29)


def test_tracker_status_open_overdue_paid() -> None:
    assert tr.tracker_status(open_balance=10, due_date="2026-09-01", today=_TODAY) == tr.STATUS_OPEN
    assert tr.tracker_status(open_balance=10, due_date="2026-07-01", today=_TODAY) == tr.STATUS_OVERDUE
    assert tr.tracker_status(open_balance=0, due_date="2026-07-01", today=_TODAY) == tr.STATUS_PAID


def test_income_tracker_live_rows_and_summary(tmp_path: Path) -> None:
    db = _db(tmp_path)
    try:
        ids = _seed(db._conn)
        rows = tr.list_income_tracker_rows(db._conn, today=_TODAY)
        types = {r["type"] for r in rows}
        assert tr.TYPE_INVOICE in types
        assert tr.TYPE_PAYMENT in types
        overdue = [r for r in rows if r["record_id"] == ids["overdue_inv"]][0]
        assert overdue["status"] == tr.STATUS_OVERDUE
        assert "Harbor Logistics" in overdue["party_name"] or "Site A" in overdue["party_name"]
        summary = tr.income_tracker_summary(db._conn, today=_TODAY)
        assert summary["unbilled_count"] == 0
        assert summary["unbilled_total"] == 0.0
        assert summary["open_count"] == 2
        assert summary["open_total"] == 550.00
        assert summary["overdue_count"] == 1
        assert summary["overdue_total"] == 150.00
        assert summary["paid_30_count"] >= 1
        assert ids["paid_inv"] in summary["paid_invoice_ids"]
        filtered = tr.filter_tracker_rows(
            rows, tile=tr.TILE_OVERDUE, today=_TODAY, paid_ids=summary["paid_invoice_ids"]
        )
        assert [r["record_id"] for r in filtered] == [ids["overdue_inv"]]
        by_cust = tr.filter_tracker_rows(rows, party_id=ids["customer"], today=_TODAY)
        assert all(r["party_id"] == ids["customer"] for r in by_cust)
    finally:
        db.close()


def test_bill_tracker_live_rows_and_summary(tmp_path: Path) -> None:
    db = _db(tmp_path)
    try:
        ids = _seed(db._conn)
        rows = tr.list_bill_tracker_rows(db._conn, today=_TODAY)
        assert all(r["type"] == tr.TYPE_BILL for r in rows)
        overdue = [r for r in rows if r["record_id"] == ids["overdue_bill"]][0]
        assert overdue["status"] == tr.STATUS_OVERDUE
        assert overdue["party_name"] == "Warehouse Supply"
        summary = tr.bill_tracker_summary(db._conn, today=_TODAY)
        assert summary["open_count"] == 2
        assert summary["open_total"] == 546.40
        assert summary["overdue_count"] == 1
        assert summary["paid_30_count"] >= 1
        assert ids["paid_bill"] in summary["paid_bill_ids"]
    finally:
        db.close()


def test_tracker_modules_have_no_screenshot_company_data() -> None:
    from pathlib import Path as P

    text = (P("probooksai/trackers.py").read_text(encoding="utf-8")
            + P("desktop_app/tracker_screens.py").read_text(encoding="utf-8"))
    lowered = text.lower()
    for needle in _FORBIDDEN:
        assert needle.lower() not in lowered
