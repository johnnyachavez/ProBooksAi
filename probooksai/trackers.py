"""Income Tracker and Bill Tracker row/summary helpers (no UI).

QuickBooks Pro Desktop trackers list live invoices, payments, and bills from the
open company file. This module does not seed demo customers, vendors, or totals.
Unbilled time & expenses are not a data type in the app yet, so that tile is
always zero until a time/expense table exists.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Optional

from probooksai import business

STATUS_OPEN = "Open"
STATUS_OVERDUE = "Overdue"
STATUS_PAID = "Paid"

TYPE_INVOICE = "Invoice"
TYPE_PAYMENT = "Payment"
TYPE_BILL = "Bill"
TYPE_BILL_PAYMENT = "Bill Payment"

DATE_ALL = "All"
DATE_TODAY = "Today"
DATE_THIS_WEEK = "This Week"
DATE_THIS_MONTH = "This Month"
DATE_LAST_30 = "Last 30 Days"
DATE_LAST_90 = "Last 90 Days"
DATE_THIS_YEAR = "This Year"

DATE_CHOICES: tuple[str, ...] = (
    DATE_ALL,
    DATE_TODAY,
    DATE_THIS_WEEK,
    DATE_THIS_MONTH,
    DATE_LAST_30,
    DATE_LAST_90,
    DATE_THIS_YEAR,
)

TILE_ALL = "all"
TILE_UNBILLED = "unbilled"
TILE_OPEN = "open"
TILE_OVERDUE = "overdue"
TILE_PAID_30 = "paid_30"


def _as_date(raw: str) -> Optional[date]:
    s = (raw or "").strip()[:10]
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def tracker_status(
    *,
    open_balance: float,
    due_date: str,
    today: date,
) -> str:
    """QB-style Open / Overdue / Paid from remaining balance and due date."""
    if float(open_balance or 0) <= 0.005:
        return STATUS_PAID
    due = _as_date(due_date)
    if due is not None and due < today:
        return STATUS_OVERDUE
    return STATUS_OPEN


def days_range(preset: str, today: date) -> Optional[tuple[date, date]]:
    """Inclusive ``(start, end)`` for a DATE filter, or ``None`` for All."""
    label = (preset or DATE_ALL).strip() or DATE_ALL
    if label == DATE_ALL:
        return None
    if label == DATE_TODAY:
        return today, today
    if label == DATE_THIS_WEEK:
        start = today - timedelta(days=today.weekday())
        return start, today
    if label == DATE_THIS_MONTH:
        return date(today.year, today.month, 1), today
    if label == DATE_LAST_30:
        return today - timedelta(days=30), today
    if label == DATE_LAST_90:
        return today - timedelta(days=90), today
    if label == DATE_THIS_YEAR:
        return date(today.year, 1, 1), today
    return None


def date_in_preset(iso: str, preset: str, today: date) -> bool:
    window = days_range(preset, today)
    if window is None:
        return True
    d = _as_date(iso)
    if d is None:
        return False
    start, end = window
    return start <= d <= end


def _customer_job_labels(conn: sqlite3.Connection) -> dict[int, str]:
    return {cid: label for cid, label in business.list_bill_to_customer_choices(conn)}


def _paid_invoice_ids_last_30(conn: sqlite3.Connection, start_iso: str) -> set[int]:
    rows = conn.execute(
        """
        SELECT DISTINCT a.invoice_id
        FROM ar_payment_allocations a
        JOIN ar_payments p ON p.id = a.payment_id
        JOIN invoices i ON i.id = a.invoice_id
        WHERE p.payment_date >= ?
          AND COALESCE(i.balance_due, 0) <= 0.005
        """,
        (start_iso,),
    ).fetchall()
    return {int(r[0]) for r in rows}


def _paid_bill_ids_last_30(conn: sqlite3.Connection, start_iso: str) -> set[int]:
    rows = conn.execute(
        """
        SELECT DISTINCT a.bill_id
        FROM ap_payment_allocations a
        JOIN ap_payments p ON p.id = a.payment_id
        JOIN bills b ON b.id = a.bill_id
        WHERE p.payment_date >= ?
          AND COALESCE(b.balance_due, 0) <= 0.005
        """,
        (start_iso,),
    ).fetchall()
    return {int(r[0]) for r in rows}


def list_income_tracker_rows(
    conn: sqlite3.Connection,
    *,
    today: Optional[date] = None,
    since_iso: Optional[str] = None,
) -> list[dict]:
    """Invoice and payment rows for Income Tracker (newest date first).

    *since_iso* (YYYY-MM-DD) limits both invoices and payments to that date or later.
    """
    day = today or date.today()
    labels = _customer_job_labels(conn)
    out: list[dict] = []
    inv_sql = """
        SELECT i.id, i.customer_id, i.invoice_number, i.invoice_date, i.due_date,
               i.total, i.balance_due, i.status
        FROM invoices i
    """
    inv_params: list = []
    if since_iso:
        inv_sql += " WHERE i.invoice_date >= ?"
        inv_params.append(since_iso)
    inv_sql += " ORDER BY i.invoice_date DESC, i.id DESC"
    for r in conn.execute(inv_sql, inv_params).fetchall():
        d = dict(r)
        cid = int(d["customer_id"])
        bal = float(d.get("balance_due") or 0)
        due = (d.get("due_date") or "").strip()
        out.append(
            {
                "kind": "invoice",
                "record_id": int(d["id"]),
                "party_id": cid,
                "party_name": labels.get(cid, f"Customer #{cid}"),
                "type": TYPE_INVOICE,
                "number": (d.get("invoice_number") or "").strip(),
                "date": (d.get("invoice_date") or "").strip(),
                "due_date": due,
                "amount": round(float(d.get("total") or 0), 2),
                "open_balance": round(bal, 2),
                "last_sent_date": "",
                "status": tracker_status(open_balance=bal, due_date=due, today=day),
            }
        )
    pay_sql = """
        SELECT p.id, p.customer_id, p.payment_date, p.amount, p.reference
        FROM ar_payments p
    """
    pay_params: list = []
    if since_iso:
        pay_sql += " WHERE p.payment_date >= ?"
        pay_params.append(since_iso)
    pay_sql += " ORDER BY p.payment_date DESC, p.id DESC"
    for r in conn.execute(pay_sql, pay_params).fetchall():
        d = dict(r)
        cid = int(d["customer_id"])
        out.append(
            {
                "kind": "payment",
                "record_id": int(d["id"]),
                "party_id": cid,
                "party_name": labels.get(cid, f"Customer #{cid}"),
                "type": TYPE_PAYMENT,
                "number": (d.get("reference") or "").strip(),
                "date": (d.get("payment_date") or "").strip(),
                "due_date": "",
                "amount": round(float(d.get("amount") or 0), 2),
                "open_balance": 0.0,
                "last_sent_date": "",
                "status": STATUS_PAID,
            }
        )
    out.sort(key=lambda row: ((row.get("date") or ""), int(row["record_id"])), reverse=True)
    return out


def list_bill_tracker_rows(
    conn: sqlite3.Connection,
    *,
    today: Optional[date] = None,
) -> list[dict]:
    """Vendor bill rows for Bill Tracker (due date ascending, like QB Pro)."""
    day = today or date.today()
    out: list[dict] = []
    for r in conn.execute(
        """
        SELECT b.id, b.vendor_id, v.name AS vendor_name,
               b.vendor_invoice_number, b.bill_date, b.due_date,
               b.total, b.balance_due, b.status
        FROM bills b
        JOIN vendors v ON v.id = b.vendor_id
        ORDER BY b.due_date ASC, b.id ASC
        """
    ).fetchall():
        d = dict(r)
        vid = int(d["vendor_id"])
        bal = float(d.get("balance_due") or 0)
        due = (d.get("due_date") or "").strip()
        out.append(
            {
                "kind": "bill",
                "record_id": int(d["id"]),
                "party_id": vid,
                "party_name": (d.get("vendor_name") or "").strip() or f"Vendor #{vid}",
                "type": TYPE_BILL,
                "number": (d.get("vendor_invoice_number") or "").strip(),
                "date": (d.get("bill_date") or "").strip(),
                "due_date": due,
                "amount": round(float(d.get("total") or 0), 2),
                "open_balance": round(bal, 2),
                "status": tracker_status(open_balance=bal, due_date=due, today=day),
            }
        )
    return out


def income_tracker_summary(
    conn: sqlite3.Connection,
    *,
    today: Optional[date] = None,
) -> dict:
    """Live tile totals. Unbilled time/expenses stay zero (no T&E table)."""
    day = today or date.today()
    start_30 = (day - timedelta(days=30)).isoformat()
    open_row = conn.execute(
        """
        SELECT COUNT(*), COALESCE(SUM(balance_due), 0)
        FROM invoices WHERE COALESCE(balance_due, 0) > 0.005
        """
    ).fetchone()
    overdue_row = conn.execute(
        """
        SELECT COUNT(*), COALESCE(SUM(balance_due), 0)
        FROM invoices
        WHERE COALESCE(balance_due, 0) > 0.005
          AND due_date IS NOT NULL AND TRIM(due_date) != ''
          AND due_date < ?
        """,
        (day.isoformat(),),
    ).fetchone()
    paid_ids = _paid_invoice_ids_last_30(conn, start_30)
    paid_total = 0.0
    paid_count = 0
    if paid_ids:
        placeholders = ",".join("?" * len(paid_ids))
        paid_invoices = conn.execute(
            f"SELECT total FROM invoices WHERE id IN ({placeholders})",
            tuple(paid_ids),
        ).fetchall()
        paid_count = len(paid_invoices)
        paid_total = round(sum(float(r[0] or 0) for r in paid_invoices), 2)
    else:
        pay_rows = conn.execute(
            "SELECT amount FROM ar_payments WHERE payment_date >= ?",
            (start_30,),
        ).fetchall()
        paid_count = len(pay_rows)
        paid_total = round(sum(float(r[0] or 0) for r in pay_rows), 2)
    return {
        "unbilled_total": 0.0,
        "unbilled_count": 0,
        "open_total": round(float(open_row[1] or 0), 2),
        "open_count": int(open_row[0] or 0),
        "overdue_total": round(float(overdue_row[1] or 0), 2),
        "overdue_count": int(overdue_row[0] or 0),
        "paid_30_total": paid_total,
        "paid_30_count": paid_count,
        "paid_invoice_ids": paid_ids,
    }


def bill_tracker_summary(
    conn: sqlite3.Connection,
    *,
    today: Optional[date] = None,
) -> dict:
    day = today or date.today()
    start_30 = (day - timedelta(days=30)).isoformat()
    rows = list_bill_tracker_rows(conn, today=day)
    open_rows = [r for r in rows if r["open_balance"] > 0.005]
    overdue = [r for r in open_rows if r["status"] == STATUS_OVERDUE]
    paid_ids = _paid_bill_ids_last_30(conn, start_30)
    paid_bills = [r for r in rows if int(r["record_id"]) in paid_ids]
    pay_total = 0.0
    pay_count = 0
    try:
        pay_rows = conn.execute(
            """
            SELECT amount FROM ap_payments
            WHERE payment_date >= ?
            """,
            (start_30,),
        ).fetchall()
        pay_count = len(pay_rows)
        pay_total = round(sum(float(r[0] or 0) for r in pay_rows), 2)
    except sqlite3.Error:
        pay_rows = []
    paid_count = len(paid_bills) if paid_bills else pay_count
    paid_total = (
        round(sum(r["amount"] for r in paid_bills), 2) if paid_bills else pay_total
    )
    return {
        "open_total": round(sum(r["open_balance"] for r in open_rows), 2),
        "open_count": len(open_rows),
        "overdue_total": round(sum(r["open_balance"] for r in overdue), 2),
        "overdue_count": len(overdue),
        "paid_30_total": paid_total,
        "paid_30_count": paid_count,
        "paid_bill_ids": paid_ids,
    }


def filter_tracker_rows(
    rows: list[dict],
    *,
    party_id: Optional[int] = None,
    type_name: str = "All",
    status_name: str = "All",
    date_preset: str = DATE_ALL,
    tile: str = TILE_ALL,
    today: Optional[date] = None,
    paid_ids: Optional[set[int]] = None,
) -> list[dict]:
    """Apply CUSTOMER/VENDOR, TYPE, STATUS, DATE, and tile filters."""
    day = today or date.today()
    want_type = (type_name or "All").strip() or "All"
    want_status = (status_name or "All").strip() or "All"
    paid_ids = paid_ids or set()
    out: list[dict] = []
    for row in rows:
        if party_id is not None and int(row.get("party_id") or 0) != int(party_id):
            continue
        if want_type != "All" and (row.get("type") or "") != want_type:
            continue
        if want_status != "All" and (row.get("status") or "") != want_status:
            continue
        if not date_in_preset(row.get("date") or "", date_preset, day):
            continue
        kind = row.get("kind") or ""
        rec = int(row.get("record_id") or 0)
        if tile == TILE_UNBILLED:
            continue
        if tile == TILE_OPEN:
            if kind not in {"invoice", "bill"} or float(row.get("open_balance") or 0) <= 0.005:
                continue
        if tile == TILE_OVERDUE:
            if row.get("status") != STATUS_OVERDUE:
                continue
        if tile == TILE_PAID_30:
            if kind in {"invoice", "bill"}:
                if rec not in paid_ids:
                    continue
            elif kind == "payment":
                if not date_in_preset(row.get("date") or "", DATE_LAST_30, day):
                    continue
            else:
                continue
        out.append(row)
    return out
