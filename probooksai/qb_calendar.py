"""Calendar helpers — live invoices, bills, payments, and To Dos (no UI).

QuickBooks Pro Desktop Calendar shows **Entered** (recorded that day) and **Due**
(items due that day) from the open company file. This module does not seed demo
vendors, customers, or overdue counts.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from probooksai import business

KIND_INVOICE = "invoice"
KIND_BILL = "bill"
KIND_AR_PAYMENT = "ar_payment"
KIND_AP_PAYMENT = "ap_payment"
KIND_TODO = "todo"

SHOW_ALL = "All Transactions"
SHOW_INVOICES = "Invoices"
SHOW_BILLS = "Bills"
SHOW_PAYMENTS = "Payments"
SHOW_TODOS = "To Do's"

SHOW_CHOICES: tuple[str, ...] = (
    SHOW_ALL,
    SHOW_INVOICES,
    SHOW_BILLS,
    SHOW_PAYMENTS,
    SHOW_TODOS,
)

TYPE_INVOICE = "Invoice"
TYPE_BILL = "Bill"
TYPE_PAYMENT = "Payment"
TYPE_TODO = "To Do"

_OPEN_BALANCE = 0.005


def _as_date(raw: str) -> Optional[date]:
    s = (raw or "").strip()[:10]
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _customer_labels(conn: sqlite3.Connection) -> dict[int, str]:
    try:
        return {cid: label for cid, label in business.list_bill_to_customer_choices(conn)}
    except sqlite3.Error:
        return {}


def matches_show(kind: str, show: str) -> bool:
    label = (show or SHOW_ALL).strip() or SHOW_ALL
    if label == SHOW_ALL:
        return True
    if label == SHOW_INVOICES:
        return kind == KIND_INVOICE
    if label == SHOW_BILLS:
        return kind == KIND_BILL
    if label == SHOW_PAYMENTS:
        return kind in {KIND_AR_PAYMENT, KIND_AP_PAYMENT}
    if label == SHOW_TODOS:
        return kind == KIND_TODO
    return True


def month_grid_dates(year: int, month: int) -> list[date]:
    """42 Sunday-first cells covering *year*/*month* (QB Pro month grid)."""
    first = date(int(year), int(month), 1)
    start = first - timedelta(days=(first.weekday() + 1) % 7)
    return [start + timedelta(days=i) for i in range(42)]


def _event(
    *,
    kind: str,
    record_id: int,
    party_name: str,
    type_name: str,
    number: str,
    amount: float,
    open_balance: float,
    entered_date: str,
    due_date: str,
) -> dict:
    return {
        "kind": kind,
        "record_id": int(record_id),
        "party_name": (party_name or "").strip(),
        "type": type_name,
        "number": (number or "").strip(),
        "amount": round(float(amount or 0), 2),
        "open_balance": round(float(open_balance or 0), 2),
        "entered_date": (entered_date or "").strip()[:10],
        "due_date": (due_date or "").strip()[:10],
    }


def _load_raw_events(conn: sqlite3.Connection) -> list[dict]:
    """All calendar source rows. Missing tables yield an empty list."""
    labels = _customer_labels(conn)
    out: list[dict] = []
    try:
        for r in conn.execute(
            """
            SELECT i.id, i.customer_id, i.invoice_number, i.invoice_date, i.due_date,
                   i.total, i.balance_due
            FROM invoices i
            """
        ).fetchall():
            d = dict(r)
            cid = int(d["customer_id"])
            out.append(
                _event(
                    kind=KIND_INVOICE,
                    record_id=int(d["id"]),
                    party_name=labels.get(cid, f"Customer #{cid}"),
                    type_name=TYPE_INVOICE,
                    number=d.get("invoice_number") or "",
                    amount=float(d.get("total") or 0),
                    open_balance=float(d.get("balance_due") or 0),
                    entered_date=d.get("invoice_date") or "",
                    due_date=d.get("due_date") or "",
                )
            )
    except sqlite3.Error:
        pass
    try:
        for r in conn.execute(
            """
            SELECT b.id, b.vendor_id, v.name AS vendor_name,
                   b.vendor_invoice_number, b.bill_date, b.due_date,
                   b.total, b.balance_due
            FROM bills b
            JOIN vendors v ON v.id = b.vendor_id
            """
        ).fetchall():
            d = dict(r)
            vid = int(d["vendor_id"])
            out.append(
                _event(
                    kind=KIND_BILL,
                    record_id=int(d["id"]),
                    party_name=(d.get("vendor_name") or "").strip() or f"Vendor #{vid}",
                    type_name=TYPE_BILL,
                    number=d.get("vendor_invoice_number") or "",
                    amount=float(d.get("total") or 0),
                    open_balance=float(d.get("balance_due") or 0),
                    entered_date=d.get("bill_date") or "",
                    due_date=d.get("due_date") or "",
                )
            )
    except sqlite3.Error:
        pass
    try:
        for r in conn.execute(
            """
            SELECT p.id, p.customer_id, p.payment_date, p.amount, p.reference
            FROM ar_payments p
            """
        ).fetchall():
            d = dict(r)
            cid = int(d["customer_id"])
            out.append(
                _event(
                    kind=KIND_AR_PAYMENT,
                    record_id=int(d["id"]),
                    party_name=labels.get(cid, f"Customer #{cid}"),
                    type_name=TYPE_PAYMENT,
                    number=d.get("reference") or "",
                    amount=float(d.get("amount") or 0),
                    open_balance=0.0,
                    entered_date=d.get("payment_date") or "",
                    due_date="",
                )
            )
    except sqlite3.Error:
        pass
    try:
        for r in conn.execute(
            """
            SELECT p.id, p.vendor_id, v.name AS vendor_name,
                   p.payment_date, p.amount, p.reference
            FROM ap_payments p
            JOIN vendors v ON v.id = p.vendor_id
            """
        ).fetchall():
            d = dict(r)
            vid = int(d["vendor_id"])
            out.append(
                _event(
                    kind=KIND_AP_PAYMENT,
                    record_id=int(d["id"]),
                    party_name=(d.get("vendor_name") or "").strip() or f"Vendor #{vid}",
                    type_name=TYPE_PAYMENT,
                    number=d.get("reference") or "",
                    amount=float(d.get("amount") or 0),
                    open_balance=0.0,
                    entered_date=d.get("payment_date") or "",
                    due_date="",
                )
            )
    except sqlite3.Error:
        pass
    try:
        for r in conn.execute(
            """
            SELECT id, title, notes, due_date, is_done
            FROM calendar_todos
            WHERE COALESCE(is_done, 0) = 0
            """
        ).fetchall():
            d = dict(r)
            title = (d.get("title") or "").strip() or "To Do"
            out.append(
                _event(
                    kind=KIND_TODO,
                    record_id=int(d["id"]),
                    party_name=title,
                    type_name=TYPE_TODO,
                    number="",
                    amount=0.0,
                    open_balance=0.0,
                    entered_date=d.get("due_date") or "",
                    due_date=d.get("due_date") or "",
                )
            )
    except sqlite3.Error:
        pass
    return out


def list_entered_for_date(
    conn: sqlite3.Connection,
    day: date,
    *,
    show: str = SHOW_ALL,
) -> list[dict]:
    iso = day.isoformat()
    rows = [
        e
        for e in _load_raw_events(conn)
        if e["entered_date"] == iso and matches_show(e["kind"], show)
    ]
    rows.sort(key=lambda e: (e["type"], e["party_name"], e["record_id"]))
    return rows


def list_due_for_date(
    conn: sqlite3.Connection,
    day: date,
    *,
    show: str = SHOW_ALL,
) -> list[dict]:
    iso = day.isoformat()
    rows = [
        e
        for e in _load_raw_events(conn)
        if e["due_date"] == iso and matches_show(e["kind"], show)
    ]
    rows.sort(key=lambda e: (e["type"], e["party_name"], e["record_id"]))
    return rows


def day_detail(
    conn: sqlite3.Connection,
    day: date,
    *,
    show: str = SHOW_ALL,
) -> dict:
    entered = list_entered_for_date(conn, day, show=show)
    due = list_due_for_date(conn, day, show=show)
    return {
        "entered": entered,
        "due": due,
        "todos": [e for e in due + entered if e["kind"] == KIND_TODO],
        "transactions": [
            e for e in due + entered if e["kind"] != KIND_TODO
        ],
    }


def month_cell_counts(
    conn: sqlite3.Connection,
    year: int,
    month: int,
    *,
    show: str = SHOW_ALL,
) -> dict[str, dict[str, int]]:
    """``{iso: {'entered': n, 'due': n}}`` for every cell in the month grid."""
    days = month_grid_dates(year, month)
    start, end = days[0].isoformat(), days[-1].isoformat()
    counts: dict[str, dict[str, int]] = {
        d.isoformat(): {"entered": 0, "due": 0} for d in days
    }
    for e in _load_raw_events(conn):
        if not matches_show(e["kind"], show):
            continue
        entered = e["entered_date"]
        due = e["due_date"]
        if entered and start <= entered <= end:
            counts.setdefault(entered, {"entered": 0, "due": 0})
            counts[entered]["entered"] += 1
        if due and start <= due <= end:
            counts.setdefault(due, {"entered": 0, "due": 0})
            counts[due]["due"] += 1
    return counts


def month_list_rows(
    conn: sqlite3.Connection,
    year: int,
    month: int,
    *,
    show: str = SHOW_ALL,
) -> list[dict]:
    """Entered + due rows that fall in *year*/*month* (list view)."""
    start = date(int(year), int(month), 1)
    if month == 12:
        end = date(int(year) + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(int(year), int(month) + 1, 1) - timedelta(days=1)
    start_iso, end_iso = start.isoformat(), end.isoformat()
    seen: set[tuple[str, int, str]] = set()
    out: list[dict] = []
    for e in _load_raw_events(conn):
        if not matches_show(e["kind"], show):
            continue
        for bucket, field in (("Entered", "entered_date"), ("Due", "due_date")):
            iso = e.get(field) or ""
            if not iso or iso < start_iso or iso > end_iso:
                continue
            key = (e["kind"], int(e["record_id"]), bucket)
            if key in seen:
                continue
            seen.add(key)
            row = dict(e)
            row["bucket"] = bucket
            row["sort_date"] = iso
            out.append(row)
    out.sort(key=lambda r: (r["sort_date"], r["bucket"], r["party_name"], r["record_id"]))
    return out


def _open_due_item(event: dict, today: date) -> bool:
    kind = event.get("kind") or ""
    if kind == KIND_TODO:
        due = _as_date(event.get("due_date") or "")
        return due is not None
    if kind in {KIND_INVOICE, KIND_BILL}:
        return float(event.get("open_balance") or 0) > _OPEN_BALANCE
    return False


def upcoming_next_7(
    conn: sqlite3.Connection,
    *,
    today: Optional[date] = None,
    show: str = SHOW_ALL,
) -> dict:
    """Items due from *today* through *today+7* that still need attention."""
    day = today or date.today()
    start, end = day, day + timedelta(days=7)
    todos: list[dict] = []
    transactions: list[dict] = []
    bills: list[dict] = []
    for e in _load_raw_events(conn):
        if not matches_show(e["kind"], show):
            continue
        due = _as_date(e.get("due_date") or "")
        if due is None or due < start or due > end:
            continue
        if not _open_due_item(e, day):
            continue
        row = dict(e)
        row["days_until"] = (due - day).days
        if e["kind"] == KIND_TODO:
            todos.append(row)
        elif e["kind"] == KIND_BILL:
            bills.append(row)
        elif e["kind"] == KIND_INVOICE:
            transactions.append(row)
    for group in (todos, transactions, bills):
        group.sort(key=lambda r: (r["due_date"], r["party_name"], r["record_id"]))
    total = len(todos) + len(transactions) + len(bills)
    return {
        "todos": todos,
        "transactions": transactions,
        "bills": bills,
        "count": total,
    }


def due_past_60(
    conn: sqlite3.Connection,
    *,
    today: Optional[date] = None,
    show: str = SHOW_ALL,
) -> dict:
    """Open items whose due date is in the past 60 days (overdue as of *today*)."""
    day = today or date.today()
    start = day - timedelta(days=60)
    todos: list[dict] = []
    transactions: list[dict] = []
    bills: list[dict] = []
    for e in _load_raw_events(conn):
        if not matches_show(e["kind"], show):
            continue
        due = _as_date(e.get("due_date") or "")
        if due is None or due >= day or due < start:
            continue
        if not _open_due_item(e, day):
            continue
        row = dict(e)
        row["days_overdue"] = (day - due).days
        if e["kind"] == KIND_TODO:
            todos.append(row)
        elif e["kind"] == KIND_BILL:
            bills.append(row)
        elif e["kind"] == KIND_INVOICE:
            transactions.append(row)
    for group in (todos, transactions, bills):
        group.sort(
            key=lambda r: (-int(r.get("days_overdue") or 0), r["party_name"], r["record_id"])
        )
    total = len(todos) + len(transactions) + len(bills)
    return {
        "todos": todos,
        "transactions": transactions,
        "bills": bills,
        "count": total,
    }


def add_todo(
    conn: sqlite3.Connection,
    *,
    title: str,
    due_date: str,
    notes: str = "",
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """
        INSERT INTO calendar_todos (title, notes, due_date, is_done, created_at)
        VALUES (?, ?, ?, 0, ?)
        """,
        ((title or "").strip() or "To Do", (notes or "").strip(), (due_date or "").strip()[:10], now),
    )
    conn.commit()
    return int(cur.lastrowid)


def mark_todo_done(conn: sqlite3.Connection, todo_id: int) -> None:
    conn.execute(
        "UPDATE calendar_todos SET is_done = 1 WHERE id = ?",
        (int(todo_id),),
    )
    conn.commit()
