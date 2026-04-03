"""
probooksai.rules_engine
=======================
Phase 6 – substring categorization rules applied during CSV import.
"""

from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_rules(conn: sqlite3.Connection) -> list:
    return conn.execute(
        """
        SELECT * FROM categorization_rules
        ORDER BY priority DESC, id ASC
        """
    ).fetchall()


def add_rule(
    conn: sqlite3.Connection,
    pattern: str,
    coa_account: str,
    priority: int = 0,
    is_active: bool = True,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO categorization_rules (pattern, coa_account, priority, is_active, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (pattern.strip(), coa_account.strip(), priority, 1 if is_active else 0, _now()),
    )
    conn.commit()
    return cur.lastrowid


def update_rule(
    conn: sqlite3.Connection,
    rule_id: int,
    pattern: str,
    coa_account: str,
    priority: int,
    is_active: bool,
) -> None:
    conn.execute(
        """
        UPDATE categorization_rules
        SET pattern = ?, coa_account = ?, priority = ?, is_active = ?
        WHERE id = ?
        """,
        (pattern.strip(), coa_account.strip(), priority, 1 if is_active else 0, rule_id),
    )
    conn.commit()


def delete_rule(conn: sqlite3.Connection, rule_id: int) -> None:
    conn.execute("DELETE FROM categorization_rules WHERE id = ?", (rule_id,))
    conn.commit()


def write_rules_csv(path: str, rows: list) -> int:
    """
    Write categorization rules to UTF-8 CSV (pattern, coa_account, priority, is_active).

    *rows* are sqlite3.Row or dict-like rows from :func:`list_rules`.
    Returns the number of data rows written (excluding the header).
    """
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["pattern", "coa_account", "priority", "is_active"])
        n = 0
        for r in rows:
            d = dict(r)
            w.writerow(
                [
                    d.get("pattern") or "",
                    d.get("coa_account") or "",
                    d.get("priority"),
                    1 if int(d.get("is_active") or 0) else 0,
                ]
            )
            n += 1
    return n


def read_rules_csv(path: str) -> list[dict[str, Any]]:
    """
    Parse a rules CSV (UTF-8 with optional BOM). Expected columns (case-insensitive):
    ``pattern``, ``coa_account`` (or ``coa``), ``priority``, ``is_active`` (optional).
    Extra columns are ignored. Returns one dict per data row.
    """
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rdr = csv.DictReader(f)
        if not rdr.fieldnames:
            return []
        fn = {(n or "").strip().lower(): n for n in rdr.fieldnames}

        def _cell(row: dict, *names: str) -> Any:
            for name in names:
                key = fn.get(name.lower())
                if key is not None and key in row:
                    return row.get(key)
            return None

        out: list[dict[str, Any]] = []
        for row in rdr:
            out.append(
                {
                    "pattern": _cell(row, "pattern"),
                    "coa_account": _cell(row, "coa_account", "coa"),
                    "priority": _cell(row, "priority"),
                    "is_active": _cell(row, "is_active", "active"),
                }
            )
        return out


def _parse_rule_priority(value: Any) -> int:
    if value is None or str(value).strip() == "":
        return 0
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return 0


def _parse_rule_active(value: Any, default: bool = True) -> bool:
    if value is None or str(value).strip() == "":
        return default
    s = str(value).strip().lower()
    if s in ("0", "false", "no", "n", "off"):
        return False
    if s in ("1", "true", "yes", "y", "on"):
        return True
    try:
        return int(float(s)) != 0
    except (TypeError, ValueError):
        return default


def validated_rule_tuples(rows: list[dict[str, Any]]) -> list[tuple[str, str, int, bool]]:
    """Build (pattern, coa_account, priority, is_active) tuples; skip invalid rows."""
    valid: list[tuple[str, str, int, bool]] = []
    for row in rows:
        pat = (row.get("pattern") or "").strip()
        coa = (row.get("coa_account") or "").strip()
        if not pat or not coa:
            continue
        valid.append(
            (
                pat,
                coa,
                _parse_rule_priority(row.get("priority")),
                _parse_rule_active(row.get("is_active"), True),
            )
        )
    return valid


def import_rules_replace(conn: sqlite3.Connection, path: str) -> int:
    """
    Replace all categorization rules with rows from *path* (same shape as export).

    Runs in a single transaction. Raises ``ValueError`` if the file has no valid rows
    (non-empty pattern and coa_account); in that case existing rules are unchanged.
    """
    raw = read_rules_csv(path)
    valid = validated_rule_tuples(raw)
    if not valid:
        raise ValueError(
            "No valid rules in file (each row needs non-empty pattern and coa_account)."
        )
    try:
        conn.execute("DELETE FROM categorization_rules")
        for pat, coa, pr, active in valid:
            conn.execute(
                """
                INSERT INTO categorization_rules
                    (pattern, coa_account, priority, is_active, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (pat, coa, pr, 1 if active else 0, _now()),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(valid)


def match_coa_for_description(conn: sqlite3.Connection, description: str) -> Optional[str]:
    """Return first matching COA display string, or None."""
    matches = suggest_coa_matches(conn, description, limit=1)
    return matches[0] if matches else None


def suggest_coa_matches(
    conn: sqlite3.Connection, description: str, limit: int = 3
) -> list[str]:
    """
    Return up to *limit* distinct COA strings from active rules whose pattern
    appears in *description* (case-insensitive), in priority order.
    """
    if limit < 1:
        return []
    desc_l = (description or "").lower()
    if not desc_l:
        return []
    rows = conn.execute(
        """
        SELECT pattern, coa_account FROM categorization_rules
        WHERE is_active = 1
        ORDER BY priority DESC, id ASC
        """
    ).fetchall()
    out: list[str] = []
    seen: set[str] = set()
    for r in rows:
        pat = (r["pattern"] or "").lower()
        if not pat or pat not in desc_l:
            continue
        coa = (r["coa_account"] or "").strip()
        if not coa or coa in seen:
            continue
        seen.add(coa)
        out.append(coa)
        if len(out) >= limit:
            break
    return out


def apply_rules_to_parsed_rows(conn: sqlite3.Connection, rows: list[dict]) -> None:
    """Mutates *rows* in place: sets coa_account when empty and a rule matches."""
    for row in rows:
        if (row.get("coa_account") or "").strip():
            continue
        coa = match_coa_for_description(conn, row.get("description", ""))
        if coa:
            row["coa_account"] = coa
