"""
Line-level statement vs register matching (AI reconciliation workflow).

Compares *extracted* statement rows to *register* ``bank_transactions``-shaped dicts
(description / ref_number / memo).
Used by the Bank Import tab; does not modify the database or the register grid.

Amounts are compared after coercion so string values with ``$``/commas/whitespace (typical of
extracts) still match SQLite float/int register values; accounting-style parentheses
``(12.34)`` denote negatives.

``txn_date`` strings accept ISO ``YYYY-MM-DD`` (including an ISO prefix before ``T``), US
``MM/DD/YYYY`` and ``MM-DD-YYYY``, ``YYYY/MM/DD``, then ``DD/MM/YYYY`` / ``DD-MM-YYYY`` when
US month/day order does not parse (e.g. day > 12).

Description similarity joins **description**, **ref_number**, and **memo** (non-empty parts,
normalized spacing) on each side so register fields split across columns still match a single
statement line (including extracts that carry check or confirmation numbers).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Any, Optional

STATUS_MATCHED = "Matched"
STATUS_MISSING = "Missing"
STATUS_EXTRA = "Extra"


def _parse_iso_date(s: str) -> Optional[datetime]:
    if not s or not str(s).strip():
        return None
    raw = str(s).strip()[:10]
    try:
        return datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        return None


def _coerce_date_to_iso(raw: str) -> Optional[str]:
    """
    Normalize a transaction date string to ``YYYY-MM-DD`` for comparison.

    Uses the first whitespace-separated token (so ``2024-01-15T12:00`` and ``1/15/2024 posted``
    both work). Returns ``None`` when no format matches.
    """
    s = str(raw or "").strip()
    if not s:
        return None
    head = s.split()[0]
    if len(head) >= 10:
        prefix = head[:10]
        if _parse_iso_date(prefix):
            return prefix
    for fmt in ("%m/%d/%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(head, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(head, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    for fmt in ("%Y/%m/%d",):
        try:
            return datetime.strptime(head, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def dates_within_days(d1: str, d2: str, days: int = 2) -> bool:
    """True when both dates coerce to ISO and |delta| <= *days*."""
    iso1 = _coerce_date_to_iso(d1)
    iso2 = _coerce_date_to_iso(d2)
    if not iso1 or not iso2:
        return False
    a, b = _parse_iso_date(iso1), _parse_iso_date(iso2)
    if a is None or b is None:
        return False
    return abs((a - b).days) <= days


def _coerce_amount(raw: Any) -> Optional[float]:
    """
    Parse a statement or register *amount* for comparison.

    Accepts numeric types and strings with optional ``$``, commas, and surrounding whitespace
    (common in CSV/PDF extract text). Returns ``None`` when missing or not parseable.
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip()
    if not s:
        return None
    if s.startswith("(") and s.endswith(")"):
        s = f"-{s[1:-1].strip()}"
    s = s.replace("$", "").replace("\u00a0", "").replace(",", "").strip()
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def amounts_equal(a: Any, b: Any) -> bool:
    """True when both sides coerce to the same cent-rounded float."""
    fa, fb = _coerce_amount(a), _coerce_amount(b)
    if fa is None or fb is None:
        return False
    return round(fa, 2) == round(fb, 2)


def descriptions_match(desc_stmt: str, desc_reg: str) -> bool:
    """
    Basic similarity: substring either way, or SequenceMatcher ratio >= 0.35.
    """
    na = (desc_stmt or "").strip().lower()
    nb = (desc_reg or "").strip().lower()
    if not na and not nb:
        return True
    if not na or not nb:
        return False
    if na in nb or nb in na:
        return True
    return SequenceMatcher(None, na, nb).ratio() >= 0.35


def _combined_description_for_match(row: dict[str, Any]) -> str:
    """Join non-empty *description*, *ref_number*, and *memo* (``bank_transactions`` shape)."""
    parts: list[str] = []
    for key in ("description", "ref_number", "memo"):
        t = str(row.get(key) or "").strip()
        if t:
            parts.append(t)
    joined = " ".join(parts).strip()
    return " ".join(joined.split())


def transaction_pair_matches(stmt: dict[str, Any], reg: dict[str, Any]) -> bool:
    """A row is a candidate MATCH when amount, date (±2d), and description rules pass."""
    d_stmt = str(stmt.get("txn_date") or "")
    d_reg = str(reg.get("txn_date") or "")
    return (
        amounts_equal(stmt.get("amount"), reg.get("amount"))
        and dates_within_days(d_stmt, d_reg, 2)
        and descriptions_match(
            _combined_description_for_match(stmt),
            _combined_description_for_match(reg),
        )
    )


def _description_match_score(stmt: dict[str, Any], reg: dict[str, Any]) -> float:
    na = _combined_description_for_match(stmt).lower()
    nb = _combined_description_for_match(reg).lower()
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def _date_distance_days(stmt: dict[str, Any], reg: dict[str, Any]) -> int:
    ia = _coerce_date_to_iso(str(stmt.get("txn_date") or ""))
    ib = _coerce_date_to_iso(str(reg.get("txn_date") or ""))
    if not ia or not ib:
        return 9999
    a, b = _parse_iso_date(ia), _parse_iso_date(ib)
    if a is None or b is None:
        return 9999
    return abs((a - b).days)


def compare_statement_to_register(
    statement_rows: list[dict[str, Any]],
    register_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Classify each statement line and unmatched register lines.

    Returns dicts with keys:
      status, stmt_date, stmt_amount, stmt_description,
      register_id, reg_date, reg_amount, reg_description

    ``stmt_description`` / ``reg_description`` use the same join as matching
    (non-empty *description*, *ref_number*, *memo*, normalized spacing) so the Bank Import
    reconciliation grid shows the full text that was compared.
    """
    stmt_list = [dict(r) for r in statement_rows]
    reg_list = [dict(r) for r in register_rows]
    used_reg: set[int] = set()
    out: list[dict[str, Any]] = []

    def pick_best_reg(stmt: dict[str, Any]) -> Optional[int]:
        best_j: Optional[int] = None
        best_score = -1.0
        best_dd = 9999
        for j, reg in enumerate(reg_list):
            if j in used_reg:
                continue
            if not transaction_pair_matches(stmt, reg):
                continue
            score = _description_match_score(stmt, reg)
            dd = _date_distance_days(stmt, reg)
            if score > best_score or (score == best_score and dd < best_dd):
                best_score = score
                best_dd = dd
                best_j = j
        return best_j

    def _row_amount_rounded(row: dict[str, Any]) -> float:
        v = _coerce_amount(row.get("amount"))
        if v is not None:
            return round(v, 2)
        return 0.0

    for stmt in stmt_list:
        j = pick_best_reg(stmt)
        if j is not None:
            used_reg.add(j)
            reg = reg_list[j]
            rid = reg.get("id")
            try:
                reg_id = int(rid) if rid is not None else None
            except (TypeError, ValueError):
                reg_id = None
            out.append(
                {
                    "status": STATUS_MATCHED,
                    "stmt_date": str(stmt.get("txn_date") or ""),
                    "stmt_amount": _row_amount_rounded(stmt),
                    "stmt_description": _combined_description_for_match(stmt),
                    "register_id": reg_id,
                    "reg_date": str(reg.get("txn_date") or ""),
                    "reg_amount": _row_amount_rounded(reg),
                    "reg_description": _combined_description_for_match(reg),
                }
            )
        else:
            out.append(
                {
                    "status": STATUS_MISSING,
                    "stmt_date": str(stmt.get("txn_date") or ""),
                    "stmt_amount": _row_amount_rounded(stmt),
                    "stmt_description": _combined_description_for_match(stmt),
                    "register_id": None,
                    "reg_date": "",
                    "reg_amount": 0.0,
                    "reg_description": "",
                }
            )

    for j, reg in enumerate(reg_list):
        if j in used_reg:
            continue
        rid = reg.get("id")
        try:
            reg_id = int(rid) if rid is not None else None
        except (TypeError, ValueError):
            reg_id = None
        out.append(
            {
                "status": STATUS_EXTRA,
                "stmt_date": "",
                "stmt_amount": 0.0,
                "stmt_description": "",
                "register_id": reg_id,
                "reg_date": str(reg.get("txn_date") or ""),
                "reg_amount": _row_amount_rounded(reg),
                "reg_description": _combined_description_for_match(reg),
            }
        )

    return out


def mock_statement_lines_for_comparison(register_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Deterministic mock “PDF extract” from register rows for UI demos and tests.

    Omits every 5th register row (so it appears as Extra on the register side),
    shifts date by +1 day on every 7th kept row (still within ±2d match rule),
    and appends one synthetic statement-only line (Missing in register).
    """
    if not register_rows:
        return [
            {
                "txn_date": "2024-01-15",
                "amount": -50.0,
                "description": "MOCK statement line (no register rows loaded)",
            }
        ]

    out: list[dict[str, Any]] = []
    for i, r in enumerate(register_rows):
        if i % 5 == 4:
            continue
        raw_amt = _coerce_amount(r.get("amount"))
        amt = round(raw_amt, 2) if raw_amt is not None else 0.0
        d = str(r.get("txn_date") or "").strip()[:10]
        desc = _combined_description_for_match(r)
        if i % 7 == 0 and d:
            dt = _parse_iso_date(d)
            if dt is not None:
                d = (dt + timedelta(days=1)).strftime("%Y-%m-%d")
        out.append({"txn_date": d, "amount": amt, "description": desc})

    first = register_rows[0]
    fd = str(first.get("txn_date") or "").strip()[:10] or "2024-01-01"
    out.append(
        {
            "txn_date": fd,
            "amount": -99.99,
            "description": "MOCK STATEMENT ONLY — not in register",
        }
    )
    return out
