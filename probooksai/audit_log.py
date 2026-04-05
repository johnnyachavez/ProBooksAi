"""
Append-only audit trail for bank transactions and related entities (Phase 23).
"""

from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timezone
from typing import Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_audit(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: int,
    field: str,
    old_value: Optional[str],
    new_value: Optional[str],
) -> None:
    """Best-effort insert; no-op if extension tables are missing."""
    try:
        conn.execute(
            """
            INSERT INTO audit_log (entity_type, entity_id, field, old_value, new_value, changed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (entity_type, entity_id, field, old_value, new_value, _now()),
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass


def list_recent(conn: sqlite3.Connection, limit: int = 500) -> list:
    try:
        return conn.execute(
            """
            SELECT * FROM audit_log
            ORDER BY changed_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []


def list_for_entity(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: int,
    *,
    limit: int = 500,
) -> list:
    """Audit rows for a single entity (e.g. one bank transaction)."""
    try:
        return conn.execute(
            """
            SELECT * FROM audit_log
            WHERE entity_type = ? AND entity_id = ?
            ORDER BY changed_at DESC, id DESC
            LIMIT ?
            """,
            (entity_type, entity_id, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []


def list_filtered(
    conn: sqlite3.Connection,
    *,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    limit: int = 500,
) -> list:
    """
    Filter audit log. If *entity_type* and *entity_id* are set, scope to that row.
    If only *entity_type* is set, filter by type. Otherwise recent entries.
    """
    et = (entity_type or "").strip()
    try:
        if et and entity_id is not None:
            return list_for_entity(conn, et, int(entity_id), limit=limit)
        if et:
            return conn.execute(
                """
                SELECT * FROM audit_log
                WHERE entity_type = ?
                ORDER BY changed_at DESC, id DESC
                LIMIT ?
                """,
                (et, limit),
            ).fetchall()
    except sqlite3.OperationalError:
        return []
    return list_recent(conn, limit=limit)


# UI labels for audit ``field`` keys (CSV export and DB keep raw names).
_AUDIT_FIELD_LABELS: dict[str, str] = {
    "bank_match_link": "Payment / document link",
    "memo": "Memo",
    "ref_number": "Number / ref",
    "coa_account": "Category (COA)",
    "attachment_path": "Attachment path",
    "needs_receipt": "Needs receipt",
    "transfer_to_bank_account_id": "Transfer to bank account",
    "cleared": "Cleared (register)",
    "is_reconciled": "Batch reconciled",
    "account_number": "Account #",
    "account_name": "Account name",
    "account_type": "Account type",
    "sub_type": "Sub-type",
    "normal_balance": "Normal balance",
    "description": "Description",
    "parent_id": "Parent account id",
    "is_active": "Active",
    "created": "Created",
    "deleted": "Deleted",
}


def audit_field_display_label(field: str | None) -> str:
    """User-facing label for audit *field* names (DB and CSV export keep raw keys)."""
    f = (field or "").strip()
    return _AUDIT_FIELD_LABELS.get(f, f)


def write_audit_csv(path: str, rows: list) -> int:
    """
    Write *rows* (sqlite3.Row or dict-like audit_log columns) to UTF-8 CSV with BOM for Excel.
    Returns the number of data rows written (excluding the header).
    """
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "changed_at",
                "entity_type",
                "entity_id",
                "field",
                "old_value",
                "new_value",
            ]
        )
        n = 0
        for r in rows:
            d = dict(r)
            w.writerow(
                [
                    (d.get("changed_at") or "")[:19],
                    d.get("entity_type") or "",
                    d.get("entity_id"),
                    d.get("field") or "",
                    d.get("old_value") or "",
                    d.get("new_value") or "",
                ]
            )
            n += 1
    return n
