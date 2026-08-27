"""Calendar data helpers — live invoices and bills, no QB vendor names."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from probooksai import business
from probooksai import qb_calendar as cal
from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import apply_extensions

_TODAY = date(2026, 8, 27)
_FORBIDDEN = (
    "AR TRUCKING",
    "ORDAZ",
    "RAYA'S",
    "ROBERTO REOS",
    "-1,000.00",
    "124",
)


def _db(tmp_path: Path) -> BankDatabase:
    b = BankDatabase(db_path=str(tmp_path / "calendar.db"))
    apply_extensions(b._conn)
    return b


def _seed(conn) -> dict[str, int]:
    cid = business.add_customer(conn, "Harbor Logistics")
    entered_inv = business.create_invoice(
        conn,
        cid,
        "INV-2101",
        "2026-08-10",
        due_date="2026-09-10",
        lines=[{"description": "Haul", "qty": 1, "rate": 400.00}],
    )
    due_inv = business.create_invoice(
        conn,
        cid,
        "INV-0888",
        "2026-07-01",
        due_date="2026-08-10",
        lines=[{"description": "Haul", "qty": 1, "rate": 150.00}],
    )
    overdue_inv = business.create_invoice(
        conn,
        cid,
        "INV-0400",
        "2026-06-01",
        due_date="2026-07-15",
        lines=[{"description": "Haul", "qty": 1, "rate": 90.00}],
    )
    vid = business.add_vendor(conn, "Office Supplies Co")
    vid2 = business.add_vendor(conn, "Warehouse Supply")
    entered_bill = business.create_bill(
        conn, vid, "2026-08-10", 450.00, vendor_invoice_number="OS-1042", due_date="2026-09-01"
    )
    overdue_bill = business.create_bill(
        conn, vid2, "2026-06-20", 96.40, vendor_invoice_number="WS-12", due_date="2026-07-20"
    )
    upcoming_bill = business.create_bill(
        conn, vid, "2026-08-20", 75.00, vendor_invoice_number="OS-88", due_date="2026-08-30"
    )
    return {
        "entered_inv": entered_inv,
        "due_inv": due_inv,
        "overdue_inv": overdue_inv,
        "entered_bill": entered_bill,
        "overdue_bill": overdue_bill,
        "upcoming_bill": upcoming_bill,
    }


def test_month_grid_starts_sunday() -> None:
    days = cal.month_grid_dates(2026, 8)
    assert len(days) == 42
    assert days[0].isoformat() == "2026-07-26"
    assert days[0].weekday() == 6  # Sunday
    assert days[31].isoformat() == "2026-08-26"


def test_entered_and_due_counts_use_live_invoices_and_bills(tmp_path: Path) -> None:
    db = _db(tmp_path)
    try:
        ids = _seed(db._conn)
        counts = cal.month_cell_counts(db._conn, 2026, 8, show=cal.SHOW_ALL)
        assert counts["2026-08-10"]["entered"] >= 2
        assert counts["2026-08-10"]["due"] >= 1
        entered = cal.list_entered_for_date(db._conn, date(2026, 8, 10))
        kinds = {e["kind"] for e in entered}
        assert cal.KIND_INVOICE in kinds
        assert cal.KIND_BILL in kinds
        assert ids["entered_inv"] in {e["record_id"] for e in entered if e["kind"] == cal.KIND_INVOICE}
        due = cal.list_due_for_date(db._conn, date(2026, 8, 10))
        assert any(e["record_id"] == ids["due_inv"] for e in due)
        invoices_only = cal.month_cell_counts(db._conn, 2026, 8, show=cal.SHOW_INVOICES)
        assert invoices_only["2026-08-10"]["entered"] == 1
        assert invoices_only["2026-08-10"]["due"] == 1
    finally:
        db.close()


def test_upcoming_and_past_due_sidebar_buckets(tmp_path: Path) -> None:
    db = _db(tmp_path)
    try:
        ids = _seed(db._conn)
        upcoming = cal.upcoming_next_7(db._conn, today=_TODAY)
        assert upcoming["count"] >= 1
        assert any(e["record_id"] == ids["upcoming_bill"] for e in upcoming["bills"])
        past = cal.due_past_60(db._conn, today=_TODAY)
        assert past["count"] >= 2
        bill_ids = {e["record_id"] for e in past["bills"]}
        inv_ids = {e["record_id"] for e in past["transactions"]}
        assert ids["overdue_bill"] in bill_ids
        assert ids["overdue_inv"] in inv_ids
        overdue = [e for e in past["bills"] if e["record_id"] == ids["overdue_bill"]][0]
        assert overdue["days_overdue"] == 38
    finally:
        db.close()


def test_todos_round_trip_and_show_filter(tmp_path: Path) -> None:
    db = _db(tmp_path)
    try:
        tid = cal.add_todo(db._conn, title="Call broker", due_date="2026-08-27", notes="follow up")
        due = cal.list_due_for_date(db._conn, _TODAY, show=cal.SHOW_TODOS)
        assert len(due) == 1
        assert due[0]["record_id"] == tid
        assert due[0]["party_name"] == "Call broker"
        hidden = cal.list_due_for_date(db._conn, _TODAY, show=cal.SHOW_INVOICES)
        assert hidden == []
        cal.mark_todo_done(db._conn, tid)
        after = cal.list_due_for_date(db._conn, _TODAY, show=cal.SHOW_TODOS)
        assert after == []
    finally:
        db.close()


def test_calendar_modules_have_no_screenshot_company_data() -> None:
    text = (
        Path("probooksai/qb_calendar.py").read_text(encoding="utf-8")
        + Path("desktop_app/calendar_screen.py").read_text(encoding="utf-8")
    )
    lowered = text.lower()
    for needle in _FORBIDDEN:
        assert needle.lower() not in lowered
