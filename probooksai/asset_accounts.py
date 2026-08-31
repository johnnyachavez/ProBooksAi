"""Asset accounts helpers — asset-list + per-account activity from the GL.

Scope for the QB Pro Desktop-style "Assets" tab: non-bank asset accounts
(``current_asset``, ``fixed_asset``, ``other_asset``, and the generic
``asset`` bucket) plus a read-only register of the GL journal lines posted
to the selected account. Bank accounts stay on the Bank Register tab so
they aren't listed twice with slightly different rules for what's posted.

The GL stores each journal line with ``account`` set to the CoA display
string (``"NNNN – Account Name"`` — en-dash by convention), so filtering
by account is a single string match.
"""

from __future__ import annotations

import sqlite3
from typing import Iterable, Optional

ASSET_ACCOUNT_TYPES: tuple[str, ...] = (
    "asset",
    "current_asset",
    "fixed_asset",
    "other_asset",
)


def _display(account_number: str, account_name: str) -> str:
    return f"{(account_number or '').strip()} – {(account_name or '').strip()}"


def list_asset_accounts(
    coa_conn: sqlite3.Connection,
    *,
    include_inactive: bool = False,
    types: Iterable[str] = ASSET_ACCOUNT_TYPES,
) -> list[dict]:
    """Return non-bank asset CoA rows ordered by ``account_number``.

    Each row: ``{id, account_number, account_name, account_type, sub_type,
    is_active, display}``. Bank accounts are intentionally excluded — the
    Bank Register tab is authoritative for bank activity.
    """
    type_list = tuple(dict.fromkeys((t or "").strip().lower() for t in types if t))
    if not type_list:
        return []
    placeholders = ",".join("?" for _ in type_list)
    active_clause = "" if include_inactive else " AND is_active = 1"
    rows = coa_conn.execute(
        f"""
        SELECT id, account_number, account_name, account_type, sub_type, is_active
        FROM coa_accounts
        WHERE lower(account_type) IN ({placeholders}){active_clause}
        ORDER BY account_number
        """,
        type_list,
    ).fetchall()
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        d["display"] = _display(d.get("account_number") or "", d.get("account_name") or "")
        out.append(d)
    return out


def account_activity(
    gl_conn: sqlite3.Connection,
    account_display: str,
    *,
    start_iso: Optional[str] = None,
    end_iso: Optional[str] = None,
) -> list[dict]:
    """Return GL journal lines posted to *account_display*, oldest first.

    Rows include an accumulated debit-normal ``running_balance`` (debits add,
    credits subtract), matching how asset accounts read on a QB Pro-style
    register. Empty account or unknown display → empty list.
    """
    disp = (account_display or "").strip()
    if not disp:
        return []
    where = ["l.account = ?"]
    params: list[object] = [disp]
    if start_iso:
        where.append("e.entry_date >= ?")
        params.append(start_iso)
    if end_iso:
        where.append("e.entry_date <= ?")
        params.append(end_iso)
    where_sql = " AND ".join(where)
    rows = gl_conn.execute(
        f"""
        SELECT e.id AS entry_id, e.entry_date, e.source, e.memo AS entry_memo,
               l.id AS line_id, l.debit, l.credit, l.description
        FROM journal_entry_lines l
        JOIN journal_entries e ON e.id = l.entry_id
        WHERE {where_sql}
        ORDER BY e.entry_date ASC, e.id ASC, l.id ASC
        """,
        params,
    ).fetchall()
    running = 0.0
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        debit = round(float(d.get("debit") or 0), 2)
        credit = round(float(d.get("credit") or 0), 2)
        running = round(running + debit - credit, 2)
        out.append(
            {
                "entry_id": int(d["entry_id"]),
                "entry_date": d["entry_date"] or "",
                "source": (d.get("source") or "").strip(),
                "entry_memo": d.get("entry_memo") or "",
                "line_id": int(d["line_id"]),
                "debit": debit,
                "credit": credit,
                "description": d.get("description") or "",
                "running_balance": running,
            }
        )
    return out


def account_ending_balance(rows: list[dict]) -> float:
    """Ending balance = last row's ``running_balance`` (or 0.0 for empty)."""
    if not rows:
        return 0.0
    return round(float(rows[-1].get("running_balance") or 0), 2)
