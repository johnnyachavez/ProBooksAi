"""
probooksai.business
===================
AR, AP, payroll, aging, tax settings, and bank matching MVP operations.
"""

from __future__ import annotations

import csv
import sqlite3
from datetime import date, datetime, timezone
from typing import Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Company settings (Phase 14 – single default tax rate)
# ---------------------------------------------------------------------------

def get_setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute(
        "SELECT value FROM company_settings WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO company_settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Sales tax reporting (Phase 14)
# ---------------------------------------------------------------------------


def sales_tax_invoices_in_range(
    conn: sqlite3.Connection, start_date: str, end_date: str
) -> list:
    """Invoices with *invoice_date* in [*start_date*, *end_date*], ordered by date."""
    return conn.execute(
        """
        SELECT i.id, i.invoice_number, i.invoice_date, c.name AS customer_name,
               i.subtotal, i.tax_total, i.total
        FROM invoices i
        JOIN customers c ON c.id = i.customer_id
        WHERE i.invoice_date >= ? AND i.invoice_date <= ?
        ORDER BY i.invoice_date, i.id
        """,
        (start_date, end_date),
    ).fetchall()


def sales_tax_collected_sum(
    conn: sqlite3.Connection, start_date: str, end_date: str
) -> float:
    """Sum of ``tax_total`` for invoices in the invoice-date range."""
    row = conn.execute(
        """
        SELECT COALESCE(SUM(tax_total), 0) AS s
        FROM invoices
        WHERE invoice_date >= ? AND invoice_date <= ?
        """,
        (start_date, end_date),
    ).fetchone()
    return round(float(row["s"] or 0), 2)


# ---------------------------------------------------------------------------
# Customers & invoices (Phase 8)
# ---------------------------------------------------------------------------

def _count_customer_children(conn: sqlite3.Connection, customer_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM customers WHERE parent_customer_id = ?",
        (customer_id,),
    ).fetchone()
    return int(row["n"] or 0) if row else 0


def _validate_customer_parent(
    conn: sqlite3.Connection,
    *,
    customer_id: int | None,
    parent_customer_id: int | None,
) -> None:
    if parent_customer_id is None:
        return
    if customer_id is not None and int(parent_customer_id) == int(customer_id):
        raise ValueError("A customer cannot be its own parent.")
    parent = get_customer(conn, int(parent_customer_id))
    if parent is None:
        raise ValueError("Parent customer not found.")
    pd = dict(parent).get("parent_customer_id")
    if pd is not None:
        raise ValueError("Parent must be a top-level customer (not a job).")
    if customer_id is not None and _count_customer_children(conn, int(customer_id)) > 0:
        raise ValueError(
            "This customer has job accounts; reassign or remove those jobs before assigning a parent."
        )


def list_parent_customer_choices(conn: sqlite3.Connection) -> list:
    """Customers that may be selected as a job parent (standalone / mother-ship rows only)."""
    return conn.execute(
        """
        SELECT * FROM customers
        WHERE parent_customer_id IS NULL
        ORDER BY name
        """
    ).fetchall()


def customer_relationship_label(conn: sqlite3.Connection, customer_id: int) -> str:
    """Short label for grids: Parent, Standalone, or Job: <parent name>."""
    row = get_customer(conn, customer_id)
    if row is None:
        return ""
    d = dict(row)
    pid = d.get("parent_customer_id")
    if pid is not None:
        prow = get_customer(conn, int(pid))
        pname = (prow["name"] or "").strip() if prow else ""
        return f"Job: {pname}" if pname else "Job"
    if _count_customer_children(conn, customer_id) > 0:
        return "Parent"
    return "Standalone"


def customer_ids_for_receive_payments_filter(
    conn: sqlite3.Connection, customer_id: int
) -> list[int]:
    """Invoice filter: one job’s invoices only; for a parent / mother ship, include all child jobs."""
    row = get_customer(conn, customer_id)
    if row is None:
        return [customer_id]
    d = dict(row)
    if d.get("parent_customer_id") is not None:
        return [customer_id]
    out = [customer_id]
    for r in conn.execute(
        """
        SELECT id FROM customers
        WHERE parent_customer_id = ?
        ORDER BY name
        """,
        (customer_id,),
    ).fetchall():
        out.append(int(r["id"]))
    return out


def add_customer(
    conn: sqlite3.Connection,
    name: str,
    email: str = "",
    phone: str = "",
    address: str = "",
    notes: str = "",
    parent_customer_id: int | None = None,
) -> int:
    _validate_customer_parent(conn, customer_id=None, parent_customer_id=parent_customer_id)
    cur = conn.execute(
        """
        INSERT INTO customers (name, email, phone, address, notes, parent_customer_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (name, email, phone, address, notes, parent_customer_id, _now()),
    )
    conn.commit()
    return cur.lastrowid


def list_customers(conn: sqlite3.Connection) -> list:
    return conn.execute(
        "SELECT * FROM customers ORDER BY name"
    ).fetchall()


def get_customer(conn: sqlite3.Connection, customer_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()


def update_customer(
    conn: sqlite3.Connection,
    customer_id: int,
    name: str,
    email: str = "",
    phone: str = "",
    address: str = "",
    notes: str = "",
    parent_customer_id: int | None = None,
) -> None:
    if get_customer(conn, customer_id) is None:
        raise ValueError("Customer not found.")
    _validate_customer_parent(
        conn, customer_id=customer_id, parent_customer_id=parent_customer_id
    )
    conn.execute(
        """
        UPDATE customers SET name = ?, email = ?, phone = ?, address = ?, notes = ?, parent_customer_id = ?
        WHERE id = ?
        """,
        (name, email, phone, address, notes, parent_customer_id, customer_id),
    )
    conn.commit()


def write_customers_csv(conn: sqlite3.Connection, path: str) -> int:
    """Export all customers to UTF-8 CSV with BOM for Excel. Returns row count (excluding header)."""
    rows = list_customers(conn)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(
            ["id", "name", "email", "phone", "address", "notes", "parent_customer_id"]
        )
        n = 0
        for r in rows:
            d = dict(r)
            w.writerow(
                [
                    d.get("id"),
                    d.get("name") or "",
                    d.get("email") or "",
                    d.get("phone") or "",
                    d.get("address") or "",
                    d.get("notes") or "",
                    d.get("parent_customer_id"),
                ]
            )
            n += 1
    return n


def create_invoice(
    conn: sqlite3.Connection,
    customer_id: int,
    invoice_number: str,
    invoice_date: str,
    due_date: str = "",
    memo: str = "",
    lines: Optional[list[dict]] = None,
    tax_rate_pct: float = 0.0,
) -> int:
    lines = lines or [{"description": "Service", "qty": 1.0, "rate": 0.0}]
    subtotal = 0.0
    for ln in lines:
        lt = round(float(ln.get("qty", 1)) * float(ln.get("rate", 0)), 2)
        subtotal += lt
    tax_total = round(subtotal * (tax_rate_pct / 100.0), 2) if tax_rate_pct else 0.0
    total = round(subtotal + tax_total, 2)
    cur = conn.execute(
        """
        INSERT INTO invoices (
            customer_id, invoice_number, invoice_date, due_date, memo,
            subtotal, tax_total, total, balance_due, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Unpaid', ?)
        """,
        (
            customer_id,
            invoice_number,
            invoice_date,
            due_date,
            memo,
            subtotal,
            tax_total,
            total,
            total,
            _now(),
        ),
    )
    inv_id = cur.lastrowid
    for ln in lines:
        qty = float(ln.get("qty", 1))
        rate = float(ln.get("rate", 0))
        lt = round(qty * rate, 2)
        conn.execute(
            """
            INSERT INTO invoice_lines (invoice_id, description, qty, rate, line_total)
            VALUES (?, ?, ?, ?, ?)
            """,
            (inv_id, ln.get("description", ""), qty, rate, lt),
        )
    conn.commit()
    return inv_id


def invoice_has_payment_allocations(conn: sqlite3.Connection, invoice_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM ar_payment_allocations WHERE invoice_id = ? LIMIT 1",
        (invoice_id,),
    ).fetchone()
    return row is not None


def update_invoice(
    conn: sqlite3.Connection,
    invoice_id: int,
    customer_id: int,
    invoice_number: str,
    invoice_date: str,
    due_date: str = "",
    memo: str = "",
    lines: Optional[list[dict]] = None,
    tax_rate_pct: float = 0.0,
) -> None:
    """Replace invoice header and lines. Raises ``ValueError`` if any AR payment applies."""
    if invoice_has_payment_allocations(conn, invoice_id):
        raise ValueError("Cannot edit an invoice that has payments applied.")
    exists = conn.execute("SELECT id FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    if exists is None:
        raise ValueError("Invoice not found.")
    lines = lines or [{"description": "Service", "qty": 1.0, "rate": 0.0}]
    subtotal = 0.0
    for ln in lines:
        lt = round(float(ln.get("qty", 1)) * float(ln.get("rate", 0)), 2)
        subtotal += lt
    tax_total = round(subtotal * (tax_rate_pct / 100.0), 2) if tax_rate_pct else 0.0
    total = round(subtotal + tax_total, 2)
    conn.execute("DELETE FROM invoice_lines WHERE invoice_id = ?", (invoice_id,))
    conn.execute(
        """
        UPDATE invoices SET
            customer_id = ?, invoice_number = ?, invoice_date = ?, due_date = ?,
            memo = ?, subtotal = ?, tax_total = ?, total = ?, balance_due = ?,
            status = 'Unpaid'
        WHERE id = ?
        """,
        (
            customer_id,
            invoice_number,
            invoice_date,
            due_date,
            memo,
            subtotal,
            tax_total,
            total,
            total,
            invoice_id,
        ),
    )
    for ln in lines:
        qty = float(ln.get("qty", 1))
        rate = float(ln.get("rate", 0))
        lt = round(qty * rate, 2)
        conn.execute(
            """
            INSERT INTO invoice_lines (invoice_id, description, qty, rate, line_total)
            VALUES (?, ?, ?, ?, ?)
            """,
            (invoice_id, ln.get("description", ""), qty, rate, lt),
        )
    conn.commit()


def list_invoices(conn: sqlite3.Connection) -> list:
    return conn.execute(
        """
        SELECT i.*, c.name AS customer_name
        FROM invoices i
        JOIN customers c ON c.id = i.customer_id
        ORDER BY i.invoice_date DESC, i.id DESC
        """
    ).fetchall()


_DEFAULT_FIRST_INVOICE_NUMBER = "13001"


def next_default_invoice_number(conn: sqlite3.Connection | None) -> str:
    """Suggested next *invoice_number* for a new invoice (desktop default).

    Uses the maximum existing *invoice_number* whose trimmed value is all digits,
    plus one. Non-numeric values are ignored for sequencing. If none qualify,
    returns ``13001``. With *conn* ``None`` (no company file), returns ``13001``.
    """
    if conn is None:
        return _DEFAULT_FIRST_INVOICE_NUMBER
    try:
        rows = conn.execute("SELECT invoice_number FROM invoices").fetchall()
    except sqlite3.Error:
        return _DEFAULT_FIRST_INVOICE_NUMBER
    best: int | None = None
    for r in rows:
        s = (r["invoice_number"] or "").strip()
        if s.isdigit():
            v = int(s)
            if best is None or v > best:
                best = v
    if best is None:
        return _DEFAULT_FIRST_INVOICE_NUMBER
    return str(best + 1)


def write_invoices_csv(
    conn: sqlite3.Connection,
    path: str,
    *,
    invoice_ids: Optional[list[int]] = None,
) -> int:
    """Export invoice header list (same join as :func:`list_invoices`) to UTF-8 CSV with BOM for Excel.

    If *invoice_ids* is set, only those ids are written, in that order (skips unknown ids).
    """
    rows = list_invoices(conn)
    if invoice_ids is not None:
        by_id = {dict(r)["id"]: r for r in rows}
        rows = [by_id[i] for i in invoice_ids if i in by_id]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "id",
                "customer_id",
                "customer_name",
                "invoice_number",
                "invoice_date",
                "due_date",
                "memo",
                "subtotal",
                "tax_total",
                "total",
                "balance_due",
                "status",
            ]
        )
        n = 0
        for r in rows:
            d = dict(r)
            w.writerow(
                [
                    d.get("id"),
                    d.get("customer_id"),
                    d.get("customer_name") or "",
                    d.get("invoice_number") or "",
                    d.get("invoice_date") or "",
                    d.get("due_date") or "",
                    d.get("memo") or "",
                    f"{float(d.get('subtotal') or 0):.2f}",
                    f"{float(d.get('tax_total') or 0):.2f}",
                    f"{float(d.get('total') or 0):.2f}",
                    f"{float(d.get('balance_due') or 0):.2f}",
                    d.get("status") or "",
                ]
            )
            n += 1
    return n


def list_invoice_ids_chronological(conn: sqlite3.Connection) -> list[int]:
    """Invoice primary keys ordered by ``id`` ascending (oldest created first)."""
    try:
        rows = conn.execute("SELECT id FROM invoices ORDER BY id ASC").fetchall()
    except sqlite3.Error:
        return []
    out: list[int] = []
    for r in rows:
        try:
            out.append(int(r["id"]))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def list_invoice_ids_by_invoice_number(conn: sqlite3.Connection) -> list[int]:
    """Invoice primary keys ordered by *invoice_number* for Manual Invoice navigation.

    All-digit numbers sort numerically ascending (matches :func:`next_default_invoice_number`).
    Other values sort after digits, case-insensitive by string, then by ``id`` for stability.
    """
    try:
        rows = conn.execute("SELECT id, invoice_number FROM invoices").fetchall()
    except sqlite3.Error:
        return []

    def sort_key(r: sqlite3.Row) -> tuple:
        try:
            sid = int(r["id"])
        except (KeyError, TypeError, ValueError):
            sid = 0
        s = (r["invoice_number"] or "").strip()
        if s.isdigit():
            return (0, int(s), sid)
        return (1, s.lower(), sid)

    rows = sorted(rows, key=sort_key)
    out: list[int] = []
    for r in rows:
        try:
            out.append(int(r["id"]))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def get_invoice_id_by_number(
    conn: sqlite3.Connection, invoice_number: str
) -> int | None:
    """Return the invoice primary key for *invoice_number* (exact match after strip), or ``None``."""
    s = (invoice_number or "").strip()
    if not s:
        return None
    row = conn.execute(
        "SELECT id FROM invoices WHERE invoice_number = ? LIMIT 1",
        (s,),
    ).fetchone()
    if row is None:
        return None
    try:
        return int(row["id"])
    except (KeyError, TypeError, ValueError):
        return None


def get_invoice_detail(
    conn: sqlite3.Connection, invoice_id: int
) -> tuple[Optional[sqlite3.Row], list]:
    """Return invoice row (with customer_name, customer_address) and line rows."""
    inv = conn.execute(
        """
        SELECT i.*, c.name AS customer_name, c.address AS customer_address
        FROM invoices i
        JOIN customers c ON c.id = i.customer_id
        WHERE i.id = ?
        """,
        (invoice_id,),
    ).fetchone()
    if inv is None:
        return None, []
    lines = conn.execute(
        "SELECT * FROM invoice_lines WHERE invoice_id = ? ORDER BY id",
        (invoice_id,),
    ).fetchall()
    return inv, list(lines)


def list_ar_payment_choices(conn: sqlite3.Connection) -> list:
    return conn.execute(
        """
        SELECT p.id, p.payment_date, p.amount, p.reference, c.name AS party_name
        FROM ar_payments p
        JOIN customers c ON c.id = p.customer_id
        ORDER BY p.payment_date DESC
        LIMIT 150
        """
    ).fetchall()


def list_ap_payment_choices(conn: sqlite3.Connection) -> list:
    return conn.execute(
        """
        SELECT p.id, p.payment_date, p.amount, p.reference, v.name AS party_name
        FROM ap_payments p
        JOIN vendors v ON v.id = p.vendor_id
        ORDER BY p.payment_date DESC
        LIMIT 150
        """
    ).fetchall()


def list_ar_payments(conn: sqlite3.Connection) -> list:
    """All AR payments, newest first (for CSV export)."""
    return conn.execute(
        """
        SELECT p.id, p.customer_id, c.name AS customer_name, p.payment_date, p.amount,
               p.method, p.reference, p.memo, p.bank_account_id, b.name AS bank_account_name
        FROM ar_payments p
        JOIN customers c ON c.id = p.customer_id
        LEFT JOIN bank_accounts b ON b.id = p.bank_account_id
        ORDER BY p.payment_date DESC, p.id DESC
        """
    ).fetchall()


def write_ar_payments_csv(conn: sqlite3.Connection, path: str) -> int:
    """Export AR payments to UTF-8 CSV with BOM for Excel. Returns row count (excluding header)."""
    rows = list_ar_payments(conn)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "id",
                "customer_id",
                "customer_name",
                "payment_date",
                "amount",
                "method",
                "reference",
                "memo",
                "bank_account_id",
                "bank_account_name",
            ]
        )
        n = 0
        for r in rows:
            d = dict(r)
            w.writerow(
                [
                    d.get("id"),
                    d.get("customer_id"),
                    d.get("customer_name") or "",
                    d.get("payment_date") or "",
                    f"{float(d.get('amount') or 0):.2f}",
                    d.get("method") or "",
                    d.get("reference") or "",
                    d.get("memo") or "",
                    d.get("bank_account_id") if d.get("bank_account_id") is not None else "",
                    d.get("bank_account_name") or "",
                ]
            )
            n += 1
    return n


def list_ap_payments(conn: sqlite3.Connection) -> list:
    """All AP payments, newest first (for CSV export)."""
    return conn.execute(
        """
        SELECT p.id, p.vendor_id, v.name AS vendor_name, p.payment_date, p.amount,
               p.method, p.reference, p.memo, p.bank_account_id, b.name AS bank_account_name
        FROM ap_payments p
        JOIN vendors v ON v.id = p.vendor_id
        LEFT JOIN bank_accounts b ON b.id = p.bank_account_id
        ORDER BY p.payment_date DESC, p.id DESC
        """
    ).fetchall()


def write_ap_payments_csv(conn: sqlite3.Connection, path: str) -> int:
    """Export AP payments to UTF-8 CSV with BOM for Excel. Returns row count (excluding header)."""
    rows = list_ap_payments(conn)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "id",
                "vendor_id",
                "vendor_name",
                "payment_date",
                "amount",
                "method",
                "reference",
                "memo",
                "bank_account_id",
                "bank_account_name",
            ]
        )
        n = 0
        for r in rows:
            d = dict(r)
            w.writerow(
                [
                    d.get("id"),
                    d.get("vendor_id"),
                    d.get("vendor_name") or "",
                    d.get("payment_date") or "",
                    f"{float(d.get('amount') or 0):.2f}",
                    d.get("method") or "",
                    d.get("reference") or "",
                    d.get("memo") or "",
                    d.get("bank_account_id") if d.get("bank_account_id") is not None else "",
                    d.get("bank_account_name") or "",
                ]
            )
            n += 1
    return n


def list_ar_payment_allocations(conn: sqlite3.Connection) -> list:
    """Each AR cash receipt line applied to an invoice (for CSV export)."""
    return conn.execute(
        """
        SELECT a.id AS allocation_id, a.payment_id, a.invoice_id, a.amount AS apply_amount,
               p.payment_date, p.amount AS payment_total, p.customer_id, c.name AS customer_name,
               p.reference AS payment_reference, i.invoice_number, i.invoice_date
        FROM ar_payment_allocations a
        JOIN ar_payments p ON p.id = a.payment_id
        JOIN customers c ON c.id = p.customer_id
        JOIN invoices i ON i.id = a.invoice_id
        ORDER BY p.payment_date DESC, a.payment_id, a.id
        """
    ).fetchall()


def write_ar_payment_allocations_csv(conn: sqlite3.Connection, path: str) -> int:
    """Export AR payment allocation lines to UTF-8 CSV with BOM for Excel. Returns row count (excluding header)."""
    rows = list_ar_payment_allocations(conn)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "allocation_id",
                "payment_id",
                "payment_date",
                "payment_total",
                "customer_id",
                "customer_name",
                "payment_reference",
                "invoice_id",
                "invoice_number",
                "invoice_date",
                "apply_amount",
            ]
        )
        n = 0
        for r in rows:
            d = dict(r)
            w.writerow(
                [
                    d.get("allocation_id"),
                    d.get("payment_id"),
                    d.get("payment_date") or "",
                    f"{float(d.get('payment_total') or 0):.2f}",
                    d.get("customer_id"),
                    d.get("customer_name") or "",
                    d.get("payment_reference") or "",
                    d.get("invoice_id"),
                    d.get("invoice_number") or "",
                    d.get("invoice_date") or "",
                    f"{float(d.get('apply_amount') or 0):.2f}",
                ]
            )
            n += 1
    return n


def list_ap_payment_allocations(conn: sqlite3.Connection) -> list:
    """Each AP payment line applied to a bill (for CSV export)."""
    return conn.execute(
        """
        SELECT a.id AS allocation_id, a.payment_id, a.bill_id, a.amount AS apply_amount,
               p.payment_date, p.amount AS payment_total, p.vendor_id, v.name AS vendor_name,
               p.reference AS payment_reference, b.vendor_invoice_number, b.bill_date
        FROM ap_payment_allocations a
        JOIN ap_payments p ON p.id = a.payment_id
        JOIN vendors v ON v.id = p.vendor_id
        JOIN bills b ON b.id = a.bill_id
        ORDER BY p.payment_date DESC, a.payment_id, a.id
        """
    ).fetchall()


def write_ap_payment_allocations_csv(conn: sqlite3.Connection, path: str) -> int:
    """Export AP payment allocation lines to UTF-8 CSV with BOM for Excel. Returns row count (excluding header)."""
    rows = list_ap_payment_allocations(conn)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "allocation_id",
                "payment_id",
                "payment_date",
                "payment_total",
                "vendor_id",
                "vendor_name",
                "payment_reference",
                "bill_id",
                "vendor_invoice_number",
                "bill_date",
                "apply_amount",
            ]
        )
        n = 0
        for r in rows:
            d = dict(r)
            w.writerow(
                [
                    d.get("allocation_id"),
                    d.get("payment_id"),
                    d.get("payment_date") or "",
                    f"{float(d.get('payment_total') or 0):.2f}",
                    d.get("vendor_id"),
                    d.get("vendor_name") or "",
                    d.get("payment_reference") or "",
                    d.get("bill_id"),
                    d.get("vendor_invoice_number") or "",
                    d.get("bill_date") or "",
                    f"{float(d.get('apply_amount') or 0):.2f}",
                ]
            )
            n += 1
    return n


def list_payroll_run_choices(conn: sqlite3.Connection) -> list:
    return conn.execute(
        """
        SELECT p.id, p.pay_date, p.net_pay, e.name AS party_name
        FROM payroll_runs p
        JOIN employees e ON e.id = p.employee_id
        ORDER BY p.pay_date DESC, p.id DESC
        LIMIT 150
        """
    ).fetchall()


def list_ar_invoice_link_choices(conn: sqlite3.Connection) -> list:
    """Open invoices (balance due) for manual bank link suggestions."""
    return conn.execute(
        """
        SELECT i.id, i.invoice_number, i.invoice_date, i.balance_due, c.name AS party_name
        FROM invoices i
        JOIN customers c ON c.id = i.customer_id
        WHERE i.balance_due > 0.005
        ORDER BY i.invoice_date DESC, i.id DESC
        LIMIT 150
        """
    ).fetchall()


def list_ap_bill_link_choices(conn: sqlite3.Connection) -> list:
    """Open bills (balance due) for manual bank link suggestions."""
    return conn.execute(
        """
        SELECT b.id, b.vendor_invoice_number, b.bill_date, b.balance_due, v.name AS party_name
        FROM bills b
        JOIN vendors v ON v.id = b.vendor_id
        WHERE b.balance_due > 0.005
        ORDER BY b.bill_date DESC, b.id DESC
        LIMIT 150
        """
    ).fetchall()


def record_ar_payment(
    conn: sqlite3.Connection,
    customer_id: int,
    payment_date: str,
    amount: float,
    allocations: list[tuple[int, float]],
    bank_account_id: Optional[int] = None,
    method: str = "",
    reference: str = "",
    memo: str = "",
) -> int:
    """*allocations* is list of (invoice_id, apply_amount)."""
    cur = conn.execute(
        """
        INSERT INTO ar_payments (
            customer_id, payment_date, amount, method, reference, memo, bank_account_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            customer_id,
            payment_date,
            amount,
            method,
            reference,
            memo,
            bank_account_id,
            _now(),
        ),
    )
    pid = cur.lastrowid
    for inv_id, amt in allocations:
        conn.execute(
            """
            INSERT INTO ar_payment_allocations (payment_id, invoice_id, amount)
            VALUES (?, ?, ?)
            """,
            (pid, inv_id, amt),
        )
        inv = conn.execute(
            "SELECT balance_due, total, status FROM invoices WHERE id = ?", (inv_id,)
        ).fetchone()
        if inv is None:
            continue
        new_bal = round(inv["balance_due"] - amt, 2)
        st = "Paid" if new_bal <= 0.005 else ("Partially Paid" if new_bal < inv["total"] else "Unpaid")
        conn.execute(
            "UPDATE invoices SET balance_due = ?, status = ? WHERE id = ?",
            (max(0.0, new_bal), st, inv_id),
        )
    conn.commit()
    return pid


def list_open_invoices_for_customer(
    conn: sqlite3.Connection, customer_id: int
) -> list:
    """Invoices with balance due for one customer (oldest by date first)."""
    return conn.execute(
        """
        SELECT id, invoice_number, invoice_date, balance_due, total
        FROM invoices
        WHERE customer_id = ? AND balance_due > 0.005
        ORDER BY invoice_date, id
        """,
        (customer_id,),
    ).fetchall()


def list_open_invoices_for_ar_payment_customer(
    conn: sqlite3.Connection, customer_id: int
) -> list:
    """Like :func:`list_open_invoices_for_customer`, but for a parent (mother ship) includes all job invoices."""
    ids = customer_ids_for_receive_payments_filter(conn, customer_id)
    if not ids:
        return []
    ph = ",".join("?" * len(ids))
    return conn.execute(
        f"""
        SELECT id, invoice_number, invoice_date, balance_due, total
        FROM invoices
        WHERE customer_id IN ({ph}) AND balance_due > 0.005
        ORDER BY invoice_date, id
        """,
        tuple(ids),
    ).fetchall()


def list_open_invoices_for_receive_payments(conn: sqlite3.Connection) -> list:
    """Open AR invoices with customer columns for the Receive Payments tab (``balance_due`` > 0)."""
    return conn.execute(
        """
        SELECT i.id AS invoice_id, i.customer_id, c.name AS customer_name,
               i.invoice_number, i.invoice_date, i.due_date,
               i.balance_due, i.total, i.status
        FROM invoices i
        JOIN customers c ON c.id = i.customer_id
        WHERE i.balance_due > 0.005
        ORDER BY c.name, COALESCE(NULLIF(TRIM(i.due_date), ''), i.invoice_date), i.id
        """
    ).fetchall()


# ---------------------------------------------------------------------------
# Vendors & bills (Phase 11)
# ---------------------------------------------------------------------------

def add_vendor(
    conn: sqlite3.Connection,
    name: str,
    email: str = "",
    phone: str = "",
    address: str = "",
    notes: str = "",
    is_1099: bool = False,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO vendors (name, email, phone, address, notes, is_1099, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (name, email, phone, address, notes, 1 if is_1099 else 0, _now()),
    )
    conn.commit()
    return cur.lastrowid


def list_vendors(conn: sqlite3.Connection) -> list:
    return conn.execute("SELECT * FROM vendors ORDER BY name").fetchall()


def get_vendor(conn: sqlite3.Connection, vendor_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM vendors WHERE id = ?", (vendor_id,)).fetchone()


def update_vendor(
    conn: sqlite3.Connection,
    vendor_id: int,
    name: str,
    email: str = "",
    phone: str = "",
    address: str = "",
    notes: str = "",
    is_1099: bool = False,
) -> None:
    if get_vendor(conn, vendor_id) is None:
        raise ValueError("Vendor not found.")
    conn.execute(
        """
        UPDATE vendors SET name = ?, email = ?, phone = ?, address = ?, notes = ?, is_1099 = ?
        WHERE id = ?
        """,
        (name, email, phone, address, notes, 1 if is_1099 else 0, vendor_id),
    )
    conn.commit()


def write_vendors_csv(conn: sqlite3.Connection, path: str) -> int:
    """Export all vendors to UTF-8 CSV with BOM for Excel. Returns row count (excluding header)."""
    rows = list_vendors(conn)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "email", "phone", "address", "notes", "is_1099"])
        n = 0
        for r in rows:
            d = dict(r)
            w.writerow(
                [
                    d.get("id"),
                    d.get("name") or "",
                    d.get("email") or "",
                    d.get("phone") or "",
                    d.get("address") or "",
                    d.get("notes") or "",
                    1 if int(d.get("is_1099") or 0) else 0,
                ]
            )
            n += 1
    return n


def _sum_bill_expense_line_amounts(lines: list[dict]) -> float:
    s = 0.0
    for ln in lines:
        s += round(float(ln.get("amount", 0) or 0), 2)
    return round(s, 2)


def _replace_bill_expense_lines(
    conn: sqlite3.Connection, bill_id: int, lines: list[dict]
) -> None:
    """Replace expense lines for a bill (caller commits)."""
    conn.execute("DELETE FROM bill_expense_lines WHERE bill_id = ?", (bill_id,))
    for i, ln in enumerate(lines):
        conn.execute(
            """
            INSERT INTO bill_expense_lines (
                bill_id, line_date, ticket_ref, amount, memo, customer_job, sort_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bill_id,
                (ln.get("line_date") or "").strip(),
                (ln.get("ticket_ref") or "").strip(),
                round(float(ln.get("amount", 0) or 0), 2),
                (ln.get("memo") or "").strip(),
                (ln.get("customer_job") or "").strip(),
                i,
            ),
        )


def list_bill_expense_lines(conn: sqlite3.Connection, bill_id: int) -> list:
    return conn.execute(
        """
        SELECT * FROM bill_expense_lines
        WHERE bill_id = ?
        ORDER BY sort_order, id
        """,
        (bill_id,),
    ).fetchall()


def get_bill_id_by_vendor_invoice_number(
    conn: sqlite3.Connection,
    vendor_invoice_number: str,
    *,
    vendor_id: Optional[int] = None,
) -> Optional[int]:
    """Return bill id for *vendor_invoice_number* (trimmed).

    With *vendor_id*, matches that vendor only. Without *vendor_id*, returns an id only when
    exactly one bill in the file has that reference (otherwise ``None`` — ambiguous).
    """
    s = (vendor_invoice_number or "").strip()
    if not s:
        return None
    if vendor_id is not None:
        row = conn.execute(
            """
            SELECT id FROM bills
            WHERE vendor_id = ? AND TRIM(COALESCE(vendor_invoice_number, '')) = ?
            LIMIT 1
            """,
            (int(vendor_id), s),
        ).fetchone()
    else:
        rows = conn.execute(
            """
            SELECT id FROM bills
            WHERE TRIM(COALESCE(vendor_invoice_number, '')) = ?
            """,
            (s,),
        ).fetchall()
        if len(rows) != 1:
            return None
        row = rows[0]
    if row is None:
        return None
    try:
        return int(row["id"])
    except (KeyError, TypeError, ValueError):
        return None


def get_bill_detail(
    conn: sqlite3.Connection, bill_id: int
) -> tuple[Optional[sqlite3.Row], list]:
    """Bill header row and expense lines (may be empty for legacy header-only bills)."""
    b = get_bill(conn, bill_id)
    if b is None:
        return None, []
    lines = list_bill_expense_lines(conn, bill_id)
    return b, list(lines)


def create_bill(
    conn: sqlite3.Connection,
    vendor_id: int,
    bill_date: str,
    total: float,
    vendor_invoice_number: str = "",
    due_date: str = "",
    memo: str = "",
    attachment_path: str = "",
    expense_lines: Optional[list[dict]] = None,
) -> int:
    if expense_lines is not None:
        total = _sum_bill_expense_line_amounts(expense_lines)
    else:
        total = round(float(total), 2)
    cur = conn.execute(
        """
        INSERT INTO bills (
            vendor_id, vendor_invoice_number, bill_date, due_date, memo,
            total, balance_due, status, attachment_path, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'Unpaid', ?, ?)
        """,
        (
            vendor_id,
            vendor_invoice_number,
            bill_date,
            due_date,
            memo,
            total,
            total,
            attachment_path,
            _now(),
        ),
    )
    bid = cur.lastrowid
    if expense_lines is not None:
        _replace_bill_expense_lines(conn, bid, expense_lines)
    conn.commit()
    return bid


def get_bill(conn: sqlite3.Connection, bill_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM bills WHERE id = ?", (bill_id,)).fetchone()


def bill_has_payment_allocations(conn: sqlite3.Connection, bill_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM ap_payment_allocations WHERE bill_id = ? LIMIT 1",
        (bill_id,),
    ).fetchone()
    return row is not None


def update_bill(
    conn: sqlite3.Connection,
    bill_id: int,
    vendor_id: int,
    bill_date: str,
    total: float,
    vendor_invoice_number: str = "",
    due_date: str = "",
    memo: str = "",
    attachment_path: str = "",
    expense_lines: Optional[list[dict]] = None,
) -> None:
    """Update bill header amounts. Raises ``ValueError`` if any AP payment applies.

    When *expense_lines* is not ``None``, *total* is derived from line amounts and lines are replaced.
    """
    if bill_has_payment_allocations(conn, bill_id):
        raise ValueError("Cannot edit a bill that has payments applied.")
    if get_bill(conn, bill_id) is None:
        raise ValueError("Bill not found.")
    if expense_lines is not None:
        total = _sum_bill_expense_line_amounts(expense_lines)
    else:
        total = round(float(total), 2)
    conn.execute(
        """
        UPDATE bills SET
            vendor_id = ?, vendor_invoice_number = ?, bill_date = ?, due_date = ?,
            memo = ?, total = ?, balance_due = ?, status = 'Unpaid', attachment_path = ?
        WHERE id = ?
        """,
        (
            vendor_id,
            vendor_invoice_number,
            bill_date,
            due_date,
            memo,
            total,
            total,
            attachment_path,
            bill_id,
        ),
    )
    if expense_lines is not None:
        _replace_bill_expense_lines(conn, bill_id, expense_lines)
    conn.commit()


def list_bills(conn: sqlite3.Connection) -> list:
    return conn.execute(
        """
        SELECT b.*, v.name AS vendor_name
        FROM bills b JOIN vendors v ON v.id = b.vendor_id
        ORDER BY b.bill_date DESC
        """
    ).fetchall()


def write_bills_csv(
    conn: sqlite3.Connection,
    path: str,
    *,
    bill_ids: Optional[list[int]] = None,
) -> int:
    """Export bill header list (same join as :func:`list_bills`) to UTF-8 CSV with BOM for Excel.

    If *bill_ids* is set, only those ids are written, in that order (skips unknown ids).
    """
    rows = list_bills(conn)
    if bill_ids is not None:
        by_id = {dict(r)["id"]: r for r in rows}
        rows = [by_id[i] for i in bill_ids if i in by_id]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "id",
                "vendor_id",
                "vendor_name",
                "vendor_invoice_number",
                "bill_date",
                "due_date",
                "memo",
                "total",
                "balance_due",
                "status",
                "attachment_path",
            ]
        )
        n = 0
        for r in rows:
            d = dict(r)
            w.writerow(
                [
                    d.get("id"),
                    d.get("vendor_id"),
                    d.get("vendor_name") or "",
                    d.get("vendor_invoice_number") or "",
                    d.get("bill_date") or "",
                    d.get("due_date") or "",
                    d.get("memo") or "",
                    f"{float(d.get('total') or 0):.2f}",
                    f"{float(d.get('balance_due') or 0):.2f}",
                    d.get("status") or "",
                    d.get("attachment_path") or "",
                ]
            )
            n += 1
    return n


def record_ap_payment(
    conn: sqlite3.Connection,
    vendor_id: int,
    payment_date: str,
    amount: float,
    allocations: list[tuple[int, float]],
    bank_account_id: Optional[int] = None,
    method: str = "",
    reference: str = "",
    memo: str = "",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO ap_payments (
            vendor_id, payment_date, amount, method, reference, memo, bank_account_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (vendor_id, payment_date, amount, method, reference, memo, bank_account_id, _now()),
    )
    pid = cur.lastrowid
    for bill_id, amt in allocations:
        conn.execute(
            """
            INSERT INTO ap_payment_allocations (payment_id, bill_id, amount)
            VALUES (?, ?, ?)
            """,
            (pid, bill_id, amt),
        )
        bill = conn.execute(
            "SELECT balance_due, total, status FROM bills WHERE id = ?", (bill_id,)
        ).fetchone()
        if bill is None:
            continue
        new_bal = round(bill["balance_due"] - amt, 2)
        st = "Paid" if new_bal <= 0.005 else (
            "Partially Paid" if new_bal < bill["total"] else "Unpaid"
        )
        conn.execute(
            "UPDATE bills SET balance_due = ?, status = ? WHERE id = ?",
            (max(0.0, new_bal), st, bill_id),
        )
    conn.commit()
    return pid


def list_open_bills_for_vendor(conn: sqlite3.Connection, vendor_id: int) -> list:
    """Bills with balance due for one vendor (oldest by date first)."""
    return conn.execute(
        """
        SELECT id, vendor_invoice_number, bill_date, balance_due, total
        FROM bills
        WHERE vendor_id = ? AND balance_due > 0.005
        ORDER BY bill_date, id
        """,
        (vendor_id,),
    ).fetchall()


def list_open_bills_for_pay_bills(conn: sqlite3.Connection) -> list:
    """Open AP bills with vendor columns for the Pay Bills tab (``balance_due`` > 0)."""
    return conn.execute(
        """
        SELECT b.id AS bill_id, b.vendor_id, v.name AS vendor_name,
               b.bill_date, b.due_date, b.vendor_invoice_number,
               b.balance_due, b.total, b.status
        FROM bills b
        JOIN vendors v ON v.id = b.vendor_id
        WHERE b.balance_due > 0.005
        ORDER BY COALESCE(NULLIF(TRIM(b.due_date), ''), b.bill_date), b.id
        """
    ).fetchall()


def list_vendor_ap_summaries(conn: sqlite3.Connection) -> list[dict]:
    """One row per vendor: open AP balance, current vs overdue (by due date), last bill and payment dates.

    *current_due* sums open balances whose due date is empty or not before today; *overdue* sums
    balances past due. Uses *today* in local calendar sense (``date.today()`` ISO compare to ``due_date``).
    """
    from datetime import date

    today = date.today()
    vendors = list_vendors(conn)
    out: list[dict] = []
    for v in vendors:
        vid = int(v["id"])
        name = (v["name"] or "").strip()
        bill_rows = conn.execute(
            "SELECT balance_due, due_date FROM bills WHERE vendor_id = ?",
            (vid,),
        ).fetchall()
        open_bal = 0.0
        current_due = 0.0
        overdue = 0.0
        for b in bill_rows:
            bal = float(b["balance_due"] or 0)
            if bal <= 0.005:
                continue
            open_bal += bal
            due_s = (b["due_date"] or "").strip()
            days_past = 0
            if due_s:
                try:
                    dd = date.fromisoformat(due_s)
                    days_past = (today - dd).days
                except ValueError:
                    days_past = 0
            if days_past <= 0:
                current_due += bal
            else:
                overdue += bal
        last_bill_row = conn.execute(
            "SELECT MAX(bill_date) FROM bills WHERE vendor_id = ?", (vid,)
        ).fetchone()
        last_bill_date = (last_bill_row[0] or "").strip() if last_bill_row else ""
        pay_row = conn.execute(
            "SELECT MAX(payment_date) FROM ap_payments WHERE vendor_id = ?", (vid,)
        ).fetchone()
        last_pay = (pay_row[0] or "").strip() if pay_row and pay_row[0] else ""
        if open_bal <= 0.005:
            ap_status = "Current"
        elif overdue > 0.005:
            ap_status = "Overdue"
        else:
            ap_status = "Open"
        out.append(
            {
                "vendor_id": vid,
                "vendor_name": name,
                "open_balance": round(open_bal, 2),
                "current_due": round(current_due, 2),
                "overdue": round(overdue, 2),
                "last_bill_date": last_bill_date,
                "last_payment_date": last_pay,
                "ap_status": ap_status,
            }
        )
    out.sort(key=lambda x: (x["vendor_name"] or "").lower())
    return out


def list_customer_ar_summaries(conn: sqlite3.Connection) -> list[dict]:
    """One row per customer: open AR balance, current vs overdue (by due date), last invoice and payment dates.

    Mirrors :func:`list_vendor_ap_summaries` for invoices / ``ar_payments``.
    """
    from datetime import date

    today = date.today()
    customers = list_customers(conn)
    out: list[dict] = []
    for c in customers:
        cid = int(c["id"])
        name = (c["name"] or "").strip()
        inv_rows = conn.execute(
            "SELECT balance_due, due_date FROM invoices WHERE customer_id = ?",
            (cid,),
        ).fetchall()
        open_bal = 0.0
        current_due = 0.0
        overdue = 0.0
        for inv in inv_rows:
            bal = float(inv["balance_due"] or 0)
            if bal <= 0.005:
                continue
            open_bal += bal
            due_s = (inv["due_date"] or "").strip()
            days_past = 0
            if due_s:
                try:
                    dd = date.fromisoformat(due_s)
                    days_past = (today - dd).days
                except ValueError:
                    days_past = 0
            if days_past <= 0:
                current_due += bal
            else:
                overdue += bal
        last_inv_row = conn.execute(
            "SELECT MAX(invoice_date) FROM invoices WHERE customer_id = ?", (cid,)
        ).fetchone()
        last_inv_date = (last_inv_row[0] or "").strip() if last_inv_row else ""
        pay_row = conn.execute(
            "SELECT MAX(payment_date) FROM ar_payments WHERE customer_id = ?", (cid,)
        ).fetchone()
        last_pay = (pay_row[0] or "").strip() if pay_row and pay_row[0] else ""
        if open_bal <= 0.005:
            ar_status = "Current"
        elif overdue > 0.005:
            ar_status = "Overdue"
        else:
            ar_status = "Open"
        out.append(
            {
                "customer_id": cid,
                "customer_name": name,
                "relationship": customer_relationship_label(conn, cid),
                "open_balance": round(open_bal, 2),
                "current_due": round(current_due, 2),
                "overdue": round(overdue, 2),
                "last_invoice_date": last_inv_date,
                "last_payment_date": last_pay,
                "ar_status": ar_status,
            }
        )
    out.sort(key=lambda x: (x["customer_name"] or "").lower())
    return out


# ---------------------------------------------------------------------------
# Aging (Phases 10 & 13)
# ---------------------------------------------------------------------------

def ar_aging_buckets(conn: sqlite3.Connection, as_of: str) -> list[dict]:
    """Bucket open invoice balance_due by days past due date vs *as_of*."""
    rows = conn.execute(
        """
        SELECT i.id, i.balance_due, i.due_date, c.name AS customer_name
        FROM invoices i
        JOIN customers c ON c.id = i.customer_id
        WHERE i.balance_due > 0.005
        """
    ).fetchall()
    from datetime import date

    as_of_d = date.fromisoformat(as_of)
    buckets = {"current": 0.0, "1_30": 0.0, "31_60": 0.0, "61_90": 0.0, "91_plus": 0.0}
    detail: list[dict] = []
    for r in rows:
        due = r["due_date"]
        days_past = 0
        if due:
            try:
                dd = date.fromisoformat(due)
                days_past = (as_of_d - dd).days
            except ValueError:
                days_past = 0
        bal = float(r["balance_due"])
        if days_past <= 0:
            key = "current"
        elif days_past <= 30:
            key = "1_30"
        elif days_past <= 60:
            key = "31_60"
        elif days_past <= 90:
            key = "61_90"
        else:
            key = "91_plus"
        buckets[key] += bal
        detail.append(
            {
                "invoice_id": r["id"],
                "customer": r["customer_name"],
                "balance": bal,
                "bucket": key,
                "days_past_due": days_past,
            }
        )
    return [{"buckets": {k: round(v, 2) for k, v in buckets.items()}, "lines": detail}]


def ap_aging_buckets(conn: sqlite3.Connection, as_of: str) -> list[dict]:
    from datetime import date

    as_of_d = date.fromisoformat(as_of)
    rows = conn.execute(
        """
        SELECT b.id, b.balance_due, b.due_date, v.name AS vendor_name
        FROM bills b
        JOIN vendors v ON v.id = b.vendor_id
        WHERE b.balance_due > 0.005
        """
    ).fetchall()
    buckets = {"current": 0.0, "1_30": 0.0, "31_60": 0.0, "61_90": 0.0, "91_plus": 0.0}
    detail: list[dict] = []
    for r in rows:
        due = r["due_date"]
        days_past = 0
        if due:
            try:
                dd = date.fromisoformat(due)
                days_past = (as_of_d - dd).days
            except ValueError:
                days_past = 0
        bal = float(r["balance_due"])
        if days_past <= 0:
            key = "current"
        elif days_past <= 30:
            key = "1_30"
        elif days_past <= 60:
            key = "31_60"
        elif days_past <= 90:
            key = "61_90"
        else:
            key = "91_plus"
        buckets[key] += bal
        detail.append(
            {
                "bill_id": r["id"],
                "vendor": r["vendor_name"],
                "balance": bal,
                "bucket": key,
                "days_past_due": days_past,
            }
        )
    return [{"buckets": {k: round(v, 2) for k, v in buckets.items()}, "lines": detail}]


# ---------------------------------------------------------------------------
# Payroll MVP (Phase 15)
# ---------------------------------------------------------------------------

def add_employee(
    conn: sqlite3.Connection,
    name: str,
    address: str = "",
    pay_type: str = "salary",
    rate: float = 0.0,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO employees (name, address, pay_type, rate, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (name, address, pay_type, rate, _now()),
    )
    conn.commit()
    return cur.lastrowid


def list_employees(conn: sqlite3.Connection) -> list:
    return conn.execute("SELECT * FROM employees ORDER BY name").fetchall()


def create_payroll_run(
    conn: sqlite3.Connection,
    employee_id: int,
    period_start: str,
    period_end: str,
    pay_date: str,
    gross: float,
    deductions: float = 0.0,
) -> int:
    net = round(float(gross) - float(deductions), 2)
    cur = conn.execute(
        """
        INSERT INTO payroll_runs (
            employee_id, period_start, period_end, pay_date,
            gross, deductions, net_pay, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (employee_id, period_start, period_end, pay_date, gross, deductions, net, _now()),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Payroll taxes — Phase 16 (manual amounts per run, report by date range)
# ---------------------------------------------------------------------------


def list_payroll_tax_items(
    conn: sqlite3.Connection, *, active_only: bool = True
) -> list:
    q = "SELECT * FROM payroll_tax_items"
    if active_only:
        q += " WHERE is_active = 1"
    q += " ORDER BY sort_order, name"
    return conn.execute(q).fetchall()


def add_payroll_tax_item(
    conn: sqlite3.Connection,
    code: str,
    name: str,
    jurisdiction: str = "",
    sort_order: int = 0,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO payroll_tax_items (code, name, jurisdiction, sort_order, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (code.strip(), name.strip(), (jurisdiction or "").strip(), sort_order, _now()),
    )
    conn.commit()
    return cur.lastrowid


def upsert_payroll_run_tax_line(
    conn: sqlite3.Connection,
    payroll_run_id: int,
    tax_item_id: int,
    employee_amount: float,
    employer_amount: float,
    notes: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO payroll_run_tax_lines
            (payroll_run_id, tax_item_id, employee_amount, employer_amount, notes)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(payroll_run_id, tax_item_id) DO UPDATE SET
            employee_amount = excluded.employee_amount,
            employer_amount = excluded.employer_amount,
            notes = excluded.notes
        """,
        (
            payroll_run_id,
            tax_item_id,
            round(float(employee_amount), 2),
            round(float(employer_amount), 2),
            notes or "",
        ),
    )
    conn.commit()


def list_payroll_run_tax_lines(conn: sqlite3.Connection, payroll_run_id: int) -> list:
    return conn.execute(
        """
        SELECT l.*, t.code, t.name, t.jurisdiction
        FROM payroll_run_tax_lines l
        JOIN payroll_tax_items t ON t.id = l.tax_item_id
        WHERE l.payroll_run_id = ?
        ORDER BY t.sort_order, t.name
        """,
        (payroll_run_id,),
    ).fetchall()


def payroll_tax_totals_by_range(
    conn: sqlite3.Connection, start_date: str, end_date: str
) -> list:
    """Sum employee / employer tax lines for pay runs in [start_date, end_date]."""
    return conn.execute(
        """
        SELECT t.id AS tax_item_id, t.code, t.name, t.jurisdiction,
               SUM(l.employee_amount) AS employee_total,
               SUM(l.employer_amount) AS employer_total
        FROM payroll_run_tax_lines l
        JOIN payroll_tax_items t ON t.id = l.tax_item_id
        JOIN payroll_runs p ON p.id = l.payroll_run_id
        WHERE p.pay_date >= ? AND p.pay_date <= ?
        GROUP BY t.id
        ORDER BY t.sort_order, t.name
        """,
        (start_date, end_date),
    ).fetchall()


# ---------------------------------------------------------------------------
# Bank matching (Phase 17)
# ---------------------------------------------------------------------------

def link_bank_transaction(
    conn: sqlite3.Connection,
    bank_transaction_id: int,
    link_type: str,
    link_id: int,
) -> None:
    prev = get_bank_match(conn, bank_transaction_id)
    old_s = ""
    if prev is not None:
        old_s = f"{prev['link_type']}:{int(prev['link_id'])}"
    new_s = f"{link_type}:{int(link_id)}"
    conn.execute(
        """
        INSERT INTO bank_match_links (bank_transaction_id, link_type, link_id, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(bank_transaction_id) DO UPDATE SET
            link_type = excluded.link_type,
            link_id = excluded.link_id,
            created_at = excluded.created_at
        """,
        (bank_transaction_id, link_type, link_id, _now()),
    )
    conn.commit()
    if old_s != new_s:
        try:
            from probooksai.audit_log import append_audit

            append_audit(
                conn,
                "bank_transaction",
                bank_transaction_id,
                "bank_match_link",
                old_s if old_s else None,
                new_s,
            )
        except Exception:
            pass


def get_bank_match(conn: sqlite3.Connection, bank_transaction_id: int) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM bank_match_links WHERE bank_transaction_id = ?",
        (bank_transaction_id,),
    ).fetchone()


def bank_match_link_tuple_from_row(bm: Optional[sqlite3.Row]) -> Optional[tuple[str, int]]:
    """
    Parse a ``bank_match_links`` row from :func:`get_bank_match`.

    Returns ``(link_type, link_id)`` when both are usable for Business hub navigation,
    else ``None``. Does not touch the database.
    """
    if bm is None:
        return None
    try:
        lt_raw = bm["link_type"]
    except (TypeError, KeyError, IndexError):
        return None
    lt = (str(lt_raw) if lt_raw is not None else "").strip()
    if not lt:
        return None
    try:
        lid = int(bm["link_id"])
    except (TypeError, ValueError, KeyError):
        return None
    return (lt, lid)


def bank_match_link_for_navigation(
    conn: sqlite3.Connection, bank_transaction_id: int
) -> Optional[tuple[str, int]]:
    """
    When *bank_transaction_id* has a ``bank_match_links`` row with a non-empty ``link_type``
    and numeric ``link_id``, return ``(link_type, link_id)`` for Business hub navigation.

    Returns ``None`` when there is no row or the link is incomplete.
    May raise ``sqlite3.OperationalError`` if the table is missing (callers show a DB message).

    For context menus that should hide **Open linked Business** without an error dialog, use
    :func:`bank_match_is_navigable` instead.
    """
    return bank_match_link_tuple_from_row(get_bank_match(conn, bank_transaction_id))


def bank_match_is_navigable(conn: sqlite3.Connection, bank_transaction_id: int) -> bool:
    """
    True when :func:`bank_match_link_for_navigation` would return a tuple.

    Returns ``False`` when navigation would return ``None``, or when ``bank_match_link_for_navigation``
    raises ``sqlite3.OperationalError`` (e.g. missing table)—typical for hiding **Open linked Business**
    in context menus without surfacing an error dialog.
    """
    try:
        return bank_match_link_for_navigation(conn, bank_transaction_id) is not None
    except sqlite3.OperationalError:
        return False


def unlink_bank_transaction(conn: sqlite3.Connection, bank_transaction_id: int) -> None:
    prev = get_bank_match(conn, bank_transaction_id)
    old_s = ""
    if prev is not None:
        old_s = f"{prev['link_type']}:{int(prev['link_id'])}"
    conn.execute(
        "DELETE FROM bank_match_links WHERE bank_transaction_id = ?",
        (bank_transaction_id,),
    )
    conn.commit()
    if old_s:
        try:
            from probooksai.audit_log import append_audit

            append_audit(
                conn,
                "bank_transaction",
                bank_transaction_id,
                "bank_match_link",
                old_s,
                "",
            )
        except Exception:
            pass


def _linked_ids_for_type(conn: sqlite3.Connection, link_type: str) -> set[int]:
    rows = conn.execute(
        "SELECT link_id FROM bank_match_links WHERE link_type = ?",
        (link_type,),
    ).fetchall()
    return {int(r["link_id"]) for r in rows}


# When the bank txn has a parseable date, only consider payments/runs within this window
# so older matches are not dropped by ORDER BY pay_date DESC LIMIT 200.
_BANK_MATCH_DATE_WINDOW_DAYS = 730
# Subtracted from score when customer/vendor/employee name appears in description or ref (lower score ranks higher).
_BANK_MATCH_NAME_IN_TEXT_BONUS = 25.0


def _bank_match_party_name_bonus(haystack: str, party_name: Optional[str]) -> float:
    """Bonus to subtract from match score when *party_name* appears in bank text (lower is better)."""
    if not party_name:
        return 0.0
    pn = str(party_name).strip().lower()
    if len(pn) < 4:
        return 0.0
    h = " ".join(str(haystack).lower().split())
    return _BANK_MATCH_NAME_IN_TEXT_BONUS if pn in h else 0.0


def suggest_bank_match_candidates(
    conn: sqlite3.Connection,
    bank_transaction_id: int,
    *,
    max_results: int = 15,
) -> list[dict]:
    """
    Phase 17 – score AR/AP payments, payroll runs, and open AR invoices / AP bills by amount and date vs bank txn.
    Excludes records already linked to *some* bank transaction.
    When the bank row's description or ref contains the party name (4+ chars), score improves.
    Deposits (positive amount) also consider open invoices; withdrawals (negative) consider open bills.
    """
    txn = conn.execute(
        """
        SELECT id, txn_date, amount, description, ref_number
        FROM bank_transactions WHERE id = ?
        """,
        (bank_transaction_id,),
    ).fetchone()
    if txn is None:
        return []
    raw_amt = round(float(txn["amount"]), 2)
    abs_amt = abs(raw_amt)
    txn_date = (txn["txn_date"] or "")[:10]
    try:
        tdt = date.fromisoformat(txn_date)
    except ValueError:
        tdt = None

    date_window_center = txn_date if tdt is not None else None
    win_lo = f"-{_BANK_MATCH_DATE_WINDOW_DAYS} days"
    win_hi = f"+{_BANK_MATCH_DATE_WINDOW_DAYS} days"

    linked_ar = _linked_ids_for_type(conn, "ar_payment")
    linked_ap = _linked_ids_for_type(conn, "ap_payment")
    linked_pr = _linked_ids_for_type(conn, "payroll_run")
    linked_ar_inv = _linked_ids_for_type(conn, "ar_invoice")
    linked_ap_bill = _linked_ids_for_type(conn, "ap_bill")

    candidates: list[dict] = []

    _hay = f"{txn['description'] or ''} {txn['ref_number'] or ''}"

    def push(
        link_type: str,
        link_id: int,
        label: str,
        pay_date: str,
        pay_amount: float,
        *,
        party_name: str = "",
    ) -> None:
        pay_amount = abs(round(float(pay_amount), 2))
        amt_diff = abs(pay_amount - abs_amt)
        amt_pen = 0.0 if amt_diff < 0.02 else amt_diff * 50.0
        if tdt is not None and pay_date:
            try:
                pdt = date.fromisoformat(str(pay_date)[:10])
                day_pen = float(abs((pdt - tdt).days))
            except ValueError:
                day_pen = 60.0
        else:
            day_pen = 30.0
        score = amt_pen + day_pen - _bank_match_party_name_bonus(_hay, party_name)
        candidates.append(
            {
                "link_type": link_type,
                "link_id": int(link_id),
                "label": label,
                "score": score,
            }
        )

    if date_window_center:
        ar_sql = """
        SELECT p.id, p.payment_date, p.amount, c.name AS party_name
        FROM ar_payments p
        JOIN customers c ON c.id = p.customer_id
        WHERE date(p.payment_date) >= date(?, ?)
          AND date(p.payment_date) <= date(?, ?)
        ORDER BY p.payment_date DESC
        LIMIT 500
        """
        ar_params = (date_window_center, win_lo, date_window_center, win_hi)
    else:
        ar_sql = """
        SELECT p.id, p.payment_date, p.amount, c.name AS party_name
        FROM ar_payments p
        JOIN customers c ON c.id = p.customer_id
        ORDER BY p.payment_date DESC
        LIMIT 200
        """
        ar_params = ()

    for r in conn.execute(ar_sql, ar_params):
        if int(r["id"]) in linked_ar:
            continue
        amt = float(r["amount"])
        push(
            "ar_payment",
            r["id"],
            f"AR pay #{r['id']} {r['payment_date']} ${amt:.2f} — {r['party_name']}",
            r["payment_date"],
            amt,
            party_name=r["party_name"],
        )

    if date_window_center:
        ap_sql = """
        SELECT p.id, p.payment_date, p.amount, v.name AS party_name
        FROM ap_payments p
        JOIN vendors v ON v.id = p.vendor_id
        WHERE date(p.payment_date) >= date(?, ?)
          AND date(p.payment_date) <= date(?, ?)
        ORDER BY p.payment_date DESC
        LIMIT 500
        """
        ap_params = (date_window_center, win_lo, date_window_center, win_hi)
    else:
        ap_sql = """
        SELECT p.id, p.payment_date, p.amount, v.name AS party_name
        FROM ap_payments p
        JOIN vendors v ON v.id = p.vendor_id
        ORDER BY p.payment_date DESC
        LIMIT 200
        """
        ap_params = ()

    for r in conn.execute(ap_sql, ap_params):
        if int(r["id"]) in linked_ap:
            continue
        amt = float(r["amount"])
        push(
            "ap_payment",
            r["id"],
            f"AP pay #{r['id']} {r['payment_date']} ${amt:.2f} — {r['party_name']}",
            r["payment_date"],
            amt,
            party_name=r["party_name"],
        )

    if date_window_center:
        pr_sql = """
        SELECT p.id, p.pay_date, p.net_pay, e.name AS party_name
        FROM payroll_runs p
        JOIN employees e ON e.id = p.employee_id
        WHERE date(p.pay_date) >= date(?, ?)
          AND date(p.pay_date) <= date(?, ?)
        ORDER BY p.pay_date DESC
        LIMIT 500
        """
        pr_params = (date_window_center, win_lo, date_window_center, win_hi)
    else:
        pr_sql = """
        SELECT p.id, p.pay_date, p.net_pay, e.name AS party_name
        FROM payroll_runs p
        JOIN employees e ON e.id = p.employee_id
        ORDER BY p.pay_date DESC
        LIMIT 200
        """
        pr_params = ()

    for r in conn.execute(pr_sql, pr_params):
        if int(r["id"]) in linked_pr:
            continue
        net = float(r["net_pay"])
        push(
            "payroll_run",
            r["id"],
            f"Payroll #{r['id']} {r['pay_date']} net ${net:.2f} — {r['party_name']}",
            r["pay_date"],
            net,
            party_name=r["party_name"],
        )

    if raw_amt > 0.005:
        if date_window_center:
            inv_sql = """
            SELECT i.id, i.invoice_number, i.invoice_date, i.balance_due, c.name AS party_name
            FROM invoices i
            JOIN customers c ON c.id = i.customer_id
            WHERE i.balance_due > 0.005
              AND date(i.invoice_date) >= date(?, ?)
              AND date(i.invoice_date) <= date(?, ?)
            ORDER BY i.invoice_date DESC
            LIMIT 500
            """
            inv_params = (date_window_center, win_lo, date_window_center, win_hi)
        else:
            inv_sql = """
            SELECT i.id, i.invoice_number, i.invoice_date, i.balance_due, c.name AS party_name
            FROM invoices i
            JOIN customers c ON c.id = i.customer_id
            WHERE i.balance_due > 0.005
            ORDER BY i.invoice_date DESC
            LIMIT 200
            """
            inv_params = ()
        for r in conn.execute(inv_sql, inv_params):
            if int(r["id"]) in linked_ar_inv:
                continue
            bal = float(r["balance_due"])
            inv_no = (r["invoice_number"] or "").strip() or str(r["id"])
            push(
                "ar_invoice",
                r["id"],
                f"AR invoice {inv_no} #{r['id']} {r['invoice_date']} ${bal:.2f} open — {r['party_name']}",
                r["invoice_date"],
                bal,
                party_name=r["party_name"],
            )

    if raw_amt < -0.005:
        if date_window_center:
            bill_sql = """
            SELECT b.id, b.vendor_invoice_number, b.bill_date, b.balance_due, v.name AS party_name
            FROM bills b
            JOIN vendors v ON v.id = b.vendor_id
            WHERE b.balance_due > 0.005
              AND date(b.bill_date) >= date(?, ?)
              AND date(b.bill_date) <= date(?, ?)
            ORDER BY b.bill_date DESC
            LIMIT 500
            """
            bill_params = (date_window_center, win_lo, date_window_center, win_hi)
        else:
            bill_sql = """
            SELECT b.id, b.vendor_invoice_number, b.bill_date, b.balance_due, v.name AS party_name
            FROM bills b
            JOIN vendors v ON v.id = b.vendor_id
            WHERE b.balance_due > 0.005
            ORDER BY b.bill_date DESC
            LIMIT 200
            """
            bill_params = ()
        for r in conn.execute(bill_sql, bill_params):
            if int(r["id"]) in linked_ap_bill:
                continue
            bal = float(r["balance_due"])
            vin = (r["vendor_invoice_number"] or "").strip()
            vin_bit = f" ({vin})" if vin else ""
            push(
                "ap_bill",
                r["id"],
                f"AP bill #{r['id']}{vin_bit} {r['bill_date']} ${bal:.2f} open — {r['party_name']}",
                r["bill_date"],
                bal,
                party_name=r["party_name"],
            )

    candidates.sort(key=lambda x: (x["score"], x["link_type"], x["link_id"]))
    return candidates[:max_results]


# ---------------------------------------------------------------------------
# Transaction splits (Phase 18)
# ---------------------------------------------------------------------------

def replace_splits(
    conn: sqlite3.Connection,
    parent_txn_id: int,
    splits: list[tuple[float, str, str]],
) -> None:
    """Each split is (amount, coa_account, memo). Sum of amounts must match parent txn amount."""
    parent = conn.execute(
        "SELECT amount FROM bank_transactions WHERE id = ?", (parent_txn_id,)
    ).fetchone()
    if parent is None:
        raise ValueError("Parent transaction not found")
    total = round(sum(s[0] for s in splits), 2)
    if abs(total - round(parent["amount"], 2)) > 0.02:
        raise ValueError("Split amounts must sum to transaction amount")
    conn.execute("DELETE FROM bank_txn_splits WHERE parent_txn_id = ?", (parent_txn_id,))
    for amt, coa, memo in splits:
        conn.execute(
            """
            INSERT INTO bank_txn_splits (parent_txn_id, amount, coa_account, memo)
            VALUES (?, ?, ?, ?)
            """,
            (parent_txn_id, amt, coa, memo),
        )
    conn.commit()


def list_splits(conn: sqlite3.Connection, parent_txn_id: int) -> list:
    return conn.execute(
        "SELECT * FROM bank_txn_splits WHERE parent_txn_id = ? ORDER BY id",
        (parent_txn_id,),
    ).fetchall()
