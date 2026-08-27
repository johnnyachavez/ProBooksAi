"""Company Snapshot helpers — live invoices, bills, bank, and GL (no UI).

QuickBooks Pro Desktop Company Snapshot charts and tables read the open company
file. This module never seeds demo customers, accounts, or prior-year revenue.
Empty history stays empty (zeros for months in the selected period; years with
no activity are omitted rather than invented).
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Optional

from probooksai import business
from probooksai.coa_db import coa_type_report_bucket

PERIOD_YTD = "This year-to-date"
PERIOD_YEAR = "This year"
PERIOD_LAST_YEAR = "Last year"

PERIOD_CHOICES: tuple[str, ...] = (PERIOD_YTD, PERIOD_YEAR, PERIOD_LAST_YEAR)

MONTH_LABELS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)

_OPEN_BALANCE = 0.005
_VOID = {"void", "cancelled", "canceled", "deleted"}


def _as_date(raw: str) -> Optional[date]:
    s = (raw or "").strip()[:10]
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def period_bounds(period: str, today: date) -> tuple[str, str]:
    """Inclusive ISO start/end for a Snapshot period dropdown."""
    label = (period or PERIOD_YTD).strip() or PERIOD_YTD
    y = int(today.year)
    if label == PERIOD_LAST_YEAR:
        return f"{y - 1}-01-01", f"{y - 1}-12-31"
    if label == PERIOD_YEAR:
        return f"{y}-01-01", f"{y}-12-31"
    return f"{y}-01-01", today.isoformat()


def months_in_period(start: str, end: str) -> list[tuple[str, str]]:
    """Return ``(YYYY-MM, month_label)`` from *start* through *end* inclusive."""
    a = _as_date(start)
    b = _as_date(end)
    if a is None or b is None or a > b:
        return []
    out: list[tuple[str, str]] = []
    y, m = a.year, a.month
    while (y, m) <= (b.year, b.month):
        out.append((f"{y:04d}-{m:02d}", MONTH_LABELS[m - 1]))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def _not_void_sql(alias: str) -> str:
    return f"lower(COALESCE({alias}.status, '')) NOT IN ('void', 'cancelled', 'canceled', 'deleted')"


def _sum_invoices_by_month(
    conn: sqlite3.Connection, start: str, end: str
) -> dict[str, float]:
    try:
        rows = conn.execute(
            f"""
            SELECT substr(invoice_date, 1, 7) AS ym, COALESCE(SUM(total), 0)
            FROM invoices
            WHERE invoice_date >= ? AND invoice_date <= ?
              AND {_not_void_sql('invoices')}
            GROUP BY ym
            """,
            (start, end),
        ).fetchall()
    except sqlite3.Error:
        return {}
    return {str(r[0]): float(r[1] or 0) for r in rows if r[0]}


def _sum_bills_by_month(
    conn: sqlite3.Connection, start: str, end: str
) -> dict[str, float]:
    try:
        rows = conn.execute(
            f"""
            SELECT substr(bill_date, 1, 7) AS ym, COALESCE(SUM(total), 0)
            FROM bills
            WHERE bill_date >= ? AND bill_date <= ?
              AND {_not_void_sql('bills')}
            GROUP BY ym
            """,
            (start, end),
        ).fetchall()
    except sqlite3.Error:
        return {}
    return {str(r[0]): float(r[1] or 0) for r in rows if r[0]}


def monthly_income_expense(
    conn: sqlite3.Connection,
    *,
    today: date,
    period: str = PERIOD_YTD,
) -> list[dict]:
    """Income (invoice totals) vs expense (bill totals) by month in *period*."""
    start, end = period_bounds(period, today)
    income = _sum_invoices_by_month(conn, start, end)
    expense = _sum_bills_by_month(conn, start, end)
    out: list[dict] = []
    for ym, label in months_in_period(start, end):
        out.append(
            {
                "year_month": ym,
                "label": label,
                "income": round(float(income.get(ym) or 0), 2),
                "expense": round(float(expense.get(ym) or 0), 2),
            }
        )
    return out


def _years_with_activity(conn: sqlite3.Connection, column_sql: str) -> set[int]:
    years: set[int] = set()
    try:
        rows = conn.execute(column_sql).fetchall()
    except sqlite3.Error:
        return years
    for row in rows:
        raw = str(row[0] or "")[:4]
        if raw.isdigit():
            years.add(int(raw))
    return years


def yearly_income(
    conn: sqlite3.Connection, *, today: date
) -> list[dict]:
    """Invoice totals by calendar year. Omits years with no invoices except *today*'s year."""
    years = _years_with_activity(
        conn,
        f"""
        SELECT DISTINCT substr(invoice_date, 1, 4)
        FROM invoices
        WHERE invoice_date != '' AND {_not_void_sql('invoices')}
        """,
    )
    years.add(int(today.year))
    ordered = sorted(y for y in years if y <= int(today.year))
    out: list[dict] = []
    for y in ordered:
        start, end = f"{y:04d}-01-01", f"{y:04d}-12-31"
        if y == int(today.year):
            end = today.isoformat()
        month_map = _sum_invoices_by_month(conn, start, end)
        total = round(sum(month_map.values()), 2)
        out.append({"year": y, "amount": total, "is_current": y == int(today.year)})
    return out


def yearly_expense(
    conn: sqlite3.Connection, *, today: date
) -> list[dict]:
    """Bill totals by calendar year. Omits years with no bills except *today*'s year."""
    years = _years_with_activity(
        conn,
        f"""
        SELECT DISTINCT substr(bill_date, 1, 4)
        FROM bills
        WHERE bill_date != '' AND {_not_void_sql('bills')}
        """,
    )
    years.add(int(today.year))
    ordered = sorted(y for y in years if y <= int(today.year))
    out: list[dict] = []
    for y in ordered:
        start, end = f"{y:04d}-01-01", f"{y:04d}-12-31"
        if y == int(today.year):
            end = today.isoformat()
        month_map = _sum_bills_by_month(conn, start, end)
        total = round(sum(month_map.values()), 2)
        out.append({"year": y, "amount": total, "is_current": y == int(today.year)})
    return out


def customers_who_owe(
    conn: sqlite3.Connection, *, today: date
) -> list[dict]:
    """Open invoice balances grouped by customer, earliest due date first."""
    try:
        rows = conn.execute(
            f"""
            SELECT i.customer_id AS customer_id,
                   c.name AS name,
                   MIN(COALESCE(NULLIF(TRIM(i.due_date), ''), i.invoice_date)) AS due_date,
                   COALESCE(SUM(i.balance_due), 0) AS amount_due
            FROM invoices i
            JOIN customers c ON c.id = i.customer_id
            WHERE COALESCE(i.balance_due, 0) > ?
              AND {_not_void_sql('i')}
            GROUP BY i.customer_id
            ORDER BY due_date ASC, c.name COLLATE NOCASE ASC
            """,
            (_OPEN_BALANCE,),
        ).fetchall()
    except sqlite3.Error:
        return []
    out: list[dict] = []
    for row in rows:
        d = dict(row)
        due = str(d.get("due_date") or "")[:10]
        due_d = _as_date(due)
        out.append(
            {
                "customer_id": int(d.get("customer_id") or 0),
                "name": str(d.get("name") or "").strip() or "Customer",
                "due_date": due,
                "amount_due": round(float(d.get("amount_due") or 0), 2),
                "is_overdue": bool(due_d is not None and due_d < today),
            }
        )
    return out


def vendors_to_pay(
    conn: sqlite3.Connection, *, today: date
) -> list[dict]:
    """Open bill balances grouped by vendor, earliest due date first."""
    try:
        rows = conn.execute(
            f"""
            SELECT b.vendor_id AS vendor_id,
                   v.name AS name,
                   MIN(COALESCE(NULLIF(TRIM(b.due_date), ''), b.bill_date)) AS due_date,
                   COALESCE(SUM(b.balance_due), 0) AS amount_due
            FROM bills b
            JOIN vendors v ON v.id = b.vendor_id
            WHERE COALESCE(b.balance_due, 0) > ?
              AND {_not_void_sql('b')}
            GROUP BY b.vendor_id
            ORDER BY due_date ASC, v.name COLLATE NOCASE ASC
            """,
            (_OPEN_BALANCE,),
        ).fetchall()
    except sqlite3.Error:
        return []
    out: list[dict] = []
    for row in rows:
        d = dict(row)
        due = str(d.get("due_date") or "")[:10]
        due_d = _as_date(due)
        out.append(
            {
                "vendor_id": int(d.get("vendor_id") or 0),
                "name": str(d.get("name") or "").strip() or "Vendor",
                "due_date": due,
                "amount_due": round(float(d.get("amount_due") or 0), 2),
                "is_overdue": bool(due_d is not None and due_d < today),
            }
        )
    return out


def account_balances(conn: sqlite3.Connection) -> list[dict]:
    """AR, AP, then active bank accounts with signed running totals."""
    out: list[dict] = []
    try:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(balance_due), 0) FROM invoices
            WHERE COALESCE(balance_due, 0) > 0.005
            """
        ).fetchone()
        out.append(
            {
                "key": "ar",
                "kind": "ar",
                "id": 0,
                "name": "Accounts Receivable",
                "balance": round(float(row[0] or 0), 2),
            }
        )
    except sqlite3.Error:
        out.append(
            {"key": "ar", "kind": "ar", "id": 0, "name": "Accounts Receivable", "balance": 0.0}
        )
    try:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(balance_due), 0) FROM bills
            WHERE COALESCE(balance_due, 0) > 0.005
            """
        ).fetchone()
        out.append(
            {
                "key": "ap",
                "kind": "ap",
                "id": 0,
                "name": "Accounts Payable",
                "balance": round(float(row[0] or 0), 2),
            }
        )
    except sqlite3.Error:
        out.append(
            {"key": "ap", "kind": "ap", "id": 0, "name": "Accounts Payable", "balance": 0.0}
        )
    try:
        rows = conn.execute(
            """
            SELECT ba.id, ba.name, COALESCE(SUM(bt.amount), 0) AS balance
            FROM bank_accounts ba
            LEFT JOIN bank_transactions bt ON bt.bank_account_id = ba.id
            WHERE ba.is_active = 1
            GROUP BY ba.id
            ORDER BY ba.name COLLATE NOCASE
            """
        ).fetchall()
        for r in rows:
            d = dict(r)
            aid = int(d.get("id") or 0)
            out.append(
                {
                    "key": f"bank:{aid}",
                    "kind": "bank",
                    "id": aid,
                    "name": str(d.get("name") or "Bank").strip() or "Bank",
                    "balance": round(float(d.get("balance") or 0), 2),
                }
            )
    except sqlite3.Error:
        pass
    return out


def top_customers_by_sales(
    conn: sqlite3.Connection,
    *,
    today: date,
    period: str = PERIOD_YTD,
    limit: int = 8,
) -> list[dict]:
    """Invoice totals by customer for *period*, largest first."""
    start, end = period_bounds(period, today)
    try:
        rows = conn.execute(
            f"""
            SELECT i.customer_id AS customer_id,
                   c.name AS name,
                   COALESCE(SUM(i.total), 0) AS sales
            FROM invoices i
            JOIN customers c ON c.id = i.customer_id
            WHERE i.invoice_date >= ? AND i.invoice_date <= ?
              AND {_not_void_sql('i')}
            GROUP BY i.customer_id
            HAVING COALESCE(SUM(i.total), 0) > 0.005
            ORDER BY sales DESC, c.name COLLATE NOCASE ASC
            LIMIT ?
            """,
            (start, end, int(limit)),
        ).fetchall()
    except sqlite3.Error:
        return []
    return [
        {
            "customer_id": int(d.get("customer_id") or 0),
            "name": str(d.get("name") or "").strip() or "Customer",
            "sales": round(float(d.get("sales") or 0), 2),
        }
        for d in (dict(r) for r in rows)
    ]


def _expense_from_gl(
    conn: sqlite3.Connection, start: str, end: str
) -> list[tuple[str, float]]:
    try:
        from probooksai.financial_reports import income_statement

        pl = income_statement(conn, start_date=start, end_date=end)
    except Exception:
        return []
    buckets: dict[str, float] = {}
    for line in pl.get("lines") or []:
        if not isinstance(line, dict):
            continue
        at = str(line.get("account_type") or "")
        if coa_type_report_bucket(at) != "expense":
            continue
        net = float(line.get("net") or 0)
        # Expense accounts are debit-normal; TB net is debit - credit.
        amt = net if net > 0 else 0.0
        if amt <= 0.005:
            continue
        label = str(line.get("account") or "Expense").strip() or "Expense"
        buckets[label] = buckets.get(label, 0.0) + amt
    return sorted(buckets.items(), key=lambda kv: kv[1], reverse=True)


def _expense_from_bank(
    conn: sqlite3.Connection, start: str, end: str
) -> list[tuple[str, float]]:
    try:
        rows = conn.execute(
            """
            SELECT TRIM(COALESCE(coa_account, '')) AS acct,
                   COALESCE(SUM(ABS(amount)), 0) AS total
            FROM bank_transactions
            WHERE amount < -0.005
              AND txn_date >= ? AND txn_date <= ?
              AND TRIM(COALESCE(coa_account, '')) != ''
            GROUP BY acct
            HAVING total > 0.005
            ORDER BY total DESC
            """,
            (start, end),
        ).fetchall()
    except sqlite3.Error:
        return []
    return [(str(r[0]), float(r[1] or 0)) for r in rows]


def _expense_from_bills(
    conn: sqlite3.Connection, start: str, end: str
) -> list[tuple[str, float]]:
    try:
        rows = conn.execute(
            f"""
            SELECT COALESCE(NULLIF(TRIM(v.name), ''), 'Vendor bills') AS label,
                   COALESCE(SUM(b.total), 0) AS total
            FROM bills b
            LEFT JOIN vendors v ON v.id = b.vendor_id
            WHERE b.bill_date >= ? AND b.bill_date <= ?
              AND {_not_void_sql('b')}
            GROUP BY label
            HAVING total > 0.005
            ORDER BY total DESC
            """,
            (start, end),
        ).fetchall()
    except sqlite3.Error:
        return []
    return [(str(r[0]), float(r[1] or 0)) for r in rows]


def expense_breakdown(
    conn: sqlite3.Connection,
    *,
    today: date,
    period: str = PERIOD_YTD,
    limit: int = 6,
) -> list[dict]:
    """Expense slices for a pie: GL accounts, else bank COA, else vendor bills.

    Remainder above *limit* is lumped as **Other Accounts**.
    """
    start, end = period_bounds(period, today)
    pairs = _expense_from_gl(conn, start, end)
    if not pairs:
        pairs = _expense_from_bank(conn, start, end)
    if not pairs:
        pairs = _expense_from_bills(conn, start, end)
    if not pairs:
        return []
    top = pairs[: max(1, int(limit))]
    rest = pairs[max(1, int(limit)) :]
    out = [
        {"label": label, "amount": round(amount, 2)} for label, amount in top
    ]
    other = round(sum(a for _l, a in rest), 2)
    if other > 0.005:
        out.append({"label": "Other Accounts", "amount": other})
    return out


def customer_label(conn: sqlite3.Connection, customer_id: int) -> str:
    try:
        row = business.get_customer(conn, int(customer_id))
    except Exception:
        return ""
    if row is None:
        return ""
    return str(dict(row).get("name") or "").strip()
