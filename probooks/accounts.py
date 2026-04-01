"""Bank account CRUD (issue #30)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any


VALID_TYPES = frozenset({"checking", "savings", "credit", "other"})


@dataclass
class BankAccount:
    id: int
    company_id: int
    name: str
    institution: str | None
    account_type: str | None
    last4: str | None
    notes: str | None
    created_at: str


def list_accounts(conn: sqlite3.Connection) -> list[BankAccount]:
    rows = conn.execute(
        """
        SELECT id, company_id, name, institution, account_type, last4, notes, created_at
        FROM bank_accounts
        ORDER BY name COLLATE NOCASE
        """
    ).fetchall()
    return [
        BankAccount(
            id=r[0],
            company_id=r[1],
            name=r[2],
            institution=r[3],
            account_type=r[4],
            last4=r[5],
            notes=r[6],
            created_at=r[7],
        )
        for r in rows
    ]


def add_account(
    conn: sqlite3.Connection,
    *,
    name: str,
    company_id: int = 1,
    institution: str | None = None,
    account_type: str | None = None,
    last4: str | None = None,
    notes: str | None = None,
) -> int:
    if not name.strip():
        raise ValueError("name is required")
    if account_type is not None and account_type not in VALID_TYPES:
        raise ValueError(f"account_type must be one of {sorted(VALID_TYPES)}")
    cur = conn.execute(
        """
        INSERT INTO bank_accounts (company_id, name, institution, account_type, last4, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (company_id, name.strip(), institution, account_type, last4, notes),
    )
    conn.commit()
    return int(cur.lastrowid)


def row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}
