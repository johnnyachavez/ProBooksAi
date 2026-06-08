"""Bank Statement Intake — phase 2 persisted review queue.

Stores the in-flight review rows from the Bank Statement Intake panel into
the company DB so the user can close the app, reopen it, and resume review
from exactly where they left off.

This module is intentionally narrow:

* It owns one table only — ``bank_statement_intake_queue`` (created by
  :mod:`probooksai.extensions_schema` v7).
* It never touches ``bank_transactions`` — that hand-off lives in
  :mod:`probooksai.bank_statement_intake_handoff` and the Bank Register
  remains the source of truth.
* It is dependency-free at the panel level: if the panel is built without
  a DB connection (Phase-1 standalone use, tests, etc.) none of these
  helpers are called.

The public API mirrors what the review panel needs in two operations:
fully replace the queue (``replace_intake_queue``) and load it back
(``load_intake_queue``). A delete-by-id helper is exposed for the
hand-off path so successfully-posted rows can be evicted without
re-saving the whole queue.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Iterable, Optional, Sequence

from probooksai.bank_statement_intake import BankStatementIntakeRow

QUEUE_TABLE = "bank_statement_intake_queue"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_db_tuple(row: BankStatementIntakeRow, *, sort_order: int) -> tuple:
    return (
        _now_iso(),
        row.txn_date or "",
        row.description_raw or "",
        row.debit,
        row.credit,
        row.amount_signed,
        row.running_balance,
        row.source_type or "",
        row.source_ref or "",
        float(row.confidence or 0.0),
        1 if row.needs_review else 0,
        sort_order,
        row.coa_account or "",
    )


def _db_row_to_dataclass(db_row: sqlite3.Row) -> BankStatementIntakeRow:
    # ``coa_account`` was added in extensions_schema v8; tolerate older
    # rows / older callers that don't supply the column by treating
    # ``KeyError`` as an empty string.
    try:
        coa = db_row["coa_account"] or ""
    except (KeyError, IndexError):
        coa = ""
    return BankStatementIntakeRow(
        txn_date=db_row["txn_date"] or "",
        description_raw=db_row["description_raw"] or "",
        debit=db_row["debit"],
        credit=db_row["credit"],
        amount_signed=db_row["amount_signed"],
        running_balance=db_row["running_balance"],
        source_type=db_row["source_type"] or "",
        source_ref=db_row["source_ref"] or "",
        confidence=float(db_row["confidence"] or 0.0),
        needs_review=bool(db_row["needs_review"]),
        coa_account=coa,
    )


def replace_intake_queue(
    conn: sqlite3.Connection, rows: Iterable[BankStatementIntakeRow]
) -> int:
    """Atomically replace the persisted intake queue with *rows*.

    The full-replace strategy (rather than per-cell update) matches how the
    review panel actually behaves: every edit re-snapshots the whole table,
    and there is no concept of a stable user-visible row id across edits.

    Returns the number of rows written.
    """
    rows_list = list(rows)
    with conn:
        conn.execute(f"DELETE FROM {QUEUE_TABLE}")
        if not rows_list:
            return 0
        payload = [
            _row_to_db_tuple(r, sort_order=i) for i, r in enumerate(rows_list)
        ]
        conn.executemany(
            f"""
            INSERT INTO {QUEUE_TABLE}
                (created_at, txn_date, description_raw,
                 debit, credit, amount_signed, running_balance,
                 source_type, source_ref, confidence, needs_review,
                 sort_order, coa_account)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            payload,
        )
    return len(rows_list)


def load_intake_queue(
    conn: sqlite3.Connection,
) -> list[BankStatementIntakeRow]:
    """Return the persisted intake queue in original insertion order."""
    cur = conn.execute(
        f"""
        SELECT id, created_at, txn_date, description_raw,
               debit, credit, amount_signed, running_balance,
               source_type, source_ref, confidence, needs_review,
               sort_order, coa_account
        FROM {QUEUE_TABLE}
        ORDER BY sort_order, id
        """
    )
    return [_db_row_to_dataclass(r) for r in cur.fetchall()]


def load_intake_queue_with_ids(
    conn: sqlite3.Connection,
) -> list[tuple[int, BankStatementIntakeRow]]:
    """Return the persisted intake queue paired with each row's primary key."""
    cur = conn.execute(
        f"""
        SELECT id, created_at, txn_date, description_raw,
               debit, credit, amount_signed, running_balance,
               source_type, source_ref, confidence, needs_review,
               sort_order, coa_account
        FROM {QUEUE_TABLE}
        ORDER BY sort_order, id
        """
    )
    return [(int(r["id"]), _db_row_to_dataclass(r)) for r in cur.fetchall()]


def delete_intake_queue_rows(
    conn: sqlite3.Connection, row_ids: Sequence[int]
) -> int:
    """Delete *row_ids* from the queue. Returns rows actually deleted."""
    ids = [int(i) for i in row_ids if i is not None]
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    with conn:
        cur = conn.execute(
            f"DELETE FROM {QUEUE_TABLE} WHERE id IN ({placeholders})", ids
        )
    return int(cur.rowcount or 0)


def clear_intake_queue(conn: sqlite3.Connection) -> int:
    """Wipe every row in the queue. Returns the count deleted."""
    with conn:
        cur = conn.execute(f"DELETE FROM {QUEUE_TABLE}")
    return int(cur.rowcount or 0)


def count_intake_queue(conn: sqlite3.Connection) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS n FROM {QUEUE_TABLE}").fetchone()
    if row is None:
        return 0
    return int(row["n"] if isinstance(row, sqlite3.Row) else row[0])


__all__ = [
    "QUEUE_TABLE",
    "replace_intake_queue",
    "load_intake_queue",
    "load_intake_queue_with_ids",
    "delete_intake_queue_rows",
    "clear_intake_queue",
    "count_intake_queue",
]


# Re-export for callers that prefer not to import Optional just to type-hint
# the common "queue may not exist yet" case.
_OptionalConn = Optional[sqlite3.Connection]  # noqa: F841 (kept for docs)
