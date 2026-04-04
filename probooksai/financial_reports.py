"""
probooksai.financial_reports
============================
Phase 5 – Trial balance (via GL), simple income statement, and balance sheet
totals using ``coa_accounts.account_type`` and posted journal lines.
"""

from __future__ import annotations

import csv
import sqlite3
from typing import Optional

from probooksai.gl import GLDatabase


def _account_number_from_gl_label(account_label: str) -> str:
    if "–" in account_label:
        return account_label.split("–", 1)[0].strip()
    return account_label.strip()


def _coa_type_map(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute(
        "SELECT account_number, account_type FROM coa_accounts WHERE is_active = 1"
    ).fetchall()
    return {r["account_number"]: r["account_type"] for r in rows}


def trial_balance_report(
    conn: sqlite3.Connection,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict]:
    gdb = GLDatabase(conn)
    return gdb.trial_balance(start_date, end_date)


def income_statement(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str,
) -> dict:
    """
    Simple P&L: sum revenue (credit-normal) and expenses (debit-normal) from TB.

    Returns dict keys: revenue, expenses, net_income, lines (detail by account).
    """
    tb = trial_balance_report(conn, start_date, end_date)
    types = _coa_type_map(conn)
    revenue = 0.0
    expenses = 0.0
    detail: list[dict] = []

    for row in tb:
        acct = row["account"]
        num = _account_number_from_gl_label(acct)
        at = types.get(num)
        net = row["net"]
        detail.append({"account": acct, "account_type": at or "unknown", "net": net})
        if at == "income":
            revenue += row["total_credit"] - row["total_debit"]
        elif at == "expense":
            expenses += row["total_debit"] - row["total_credit"]

    revenue = round(revenue, 2)
    expenses = round(expenses, 2)
    return {
        "revenue": revenue,
        "expenses": expenses,
        "net_income": round(revenue - expenses, 2),
        "lines": detail,
    }


def balance_sheet_summary(
    conn: sqlite3.Connection,
    as_of_date: Optional[str] = None,
) -> dict:
    """
    Aggregate trial balance by account_type: assets vs liabilities+equity.

    *as_of_date* filters journal entries with entry_date <= as_of_date (inclusive).
    """
    tb = trial_balance_report(conn, end_date=as_of_date)
    types = _coa_type_map(conn)
    assets = 0.0
    liabilities = 0.0
    equity = 0.0

    for row in tb:
        num = _account_number_from_gl_label(row["account"])
        at = types.get(num)
        td = row["total_debit"]
        tc = row["total_credit"]
        if at == "asset":
            assets += td - tc
        elif at == "liability":
            liabilities += tc - td
        elif at == "equity":
            equity += tc - td

    return {
        "assets": round(assets, 2),
        "liabilities": round(liabilities, 2),
        "equity": round(equity, 2),
        "liabilities_plus_equity": round(liabilities + equity, 2),
    }


def write_report_csv(
    path: str,
    headers: list[str],
    rows: list[list],
    *,
    preamble: Optional[list[str]] = None,
) -> int:
    """
    Write a UTF-8 CSV with BOM for Excel for a report table.

    *preamble* lines are written as single-column rows, then a blank row, then the table.
    Returns the number of data rows (excluding preamble and header).
    """
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if preamble:
            for line in preamble:
                w.writerow([line])
            w.writerow([])
        w.writerow(headers)
        n = 0
        for row in rows:
            w.writerow(row)
            n += 1
    return n
