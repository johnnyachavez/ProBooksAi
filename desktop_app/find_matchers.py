"""Shared "Find" search helpers for Invoice / Register / Write Checks.

QuickBooks Pro Desktop Find on these forms accepts flexible input and matches
by document number, party name (customer / payee / vendor), amount, or date.
Each screen keeps its own load-into-form logic; this module only decides
whether a candidate row is a hit for the user's needle.

All predicates are pure and easy to test — the UI code just iterates its own
rows and calls :func:`row_matches_find`.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from desktop_app.flexible_date import parse_flexible_date_to_ymd


def parse_amount_needle(text: str) -> Optional[float]:
    """Return the numeric magnitude of *text*, or ``None`` if not amount-like.

    Accepts ``"1,280.50"``, ``"$1280.5"``, ``"-500"``. Matches use absolute
    value so a check for $500 finds a ``-500.00`` register row.
    """
    s = (text or "").strip()
    if not s:
        return None
    cleaned = s.replace(",", "").replace("$", "").strip()
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    try:
        return abs(float(cleaned))
    except (TypeError, ValueError):
        return None


def parse_date_needle(text: str) -> Optional[str]:
    """Return ISO ``yyyy-mm-dd`` if *text* parses as a date, else ``None``."""
    ymd = parse_flexible_date_to_ymd(text or "")
    if ymd is None:
        return None
    y, m, d = ymd
    return f"{y:04d}-{m:02d}-{d:02d}"


def _substring_match(needle: str, haystack: Any) -> bool:
    if haystack is None:
        return False
    n = (needle or "").strip().lower()
    if not n:
        return False
    return n in str(haystack).strip().lower()


def _amount_match(target: Optional[float], value: Any) -> bool:
    if target is None or value is None:
        return False
    try:
        return abs(abs(float(value)) - float(target)) < 0.005
    except (TypeError, ValueError):
        return False


def _date_match(target_iso: Optional[str], value: Any) -> bool:
    if not target_iso or value is None:
        return False
    s = str(value).strip()
    if not s:
        return False
    if s == target_iso:
        return True
    ymd = parse_flexible_date_to_ymd(s)
    if ymd is None:
        return False
    y, m, d = ymd
    return f"{y:04d}-{m:02d}-{d:02d}" == target_iso


def row_matches_find(
    row: Any,
    needle: str,
    *,
    number_fields: Iterable[str] = (),
    name_fields: Iterable[str] = (),
    amount_fields: Iterable[str] = (),
    date_fields: Iterable[str] = (),
) -> bool:
    """Return ``True`` if *row* matches the QB Pro-style Find *needle*.

    A row is a match when the needle matches (case-insensitive substring) any
    ``number_fields`` or ``name_fields`` value, OR the needle parses as an
    amount and matches (abs, penny tolerance) any ``amount_fields`` value, OR
    the needle parses as a date and matches any ``date_fields`` value.

    *row* may be a ``sqlite3.Row``, a dict, or any object with ``__getitem__``
    and ``get``; missing fields are treated as empty.
    """
    n = (needle or "").strip()
    if not n:
        return False
    if hasattr(row, "keys"):
        get = lambda k: row[k] if k in row.keys() else None  # noqa: E731
    else:
        get = lambda k: getattr(row, k, None)  # noqa: E731

    for field in number_fields:
        if _substring_match(n, get(field)):
            return True
    for field in name_fields:
        if _substring_match(n, get(field)):
            return True
    amt = parse_amount_needle(n)
    if amt is not None:
        for field in amount_fields:
            if _amount_match(amt, get(field)):
                return True
    iso = parse_date_needle(n)
    if iso is not None:
        for field in date_fields:
            if _date_match(iso, get(field)):
                return True
    return False


def first_matching_row(
    rows: Iterable[Any],
    needle: str,
    *,
    number_fields: Iterable[str] = (),
    name_fields: Iterable[str] = (),
    amount_fields: Iterable[str] = (),
    date_fields: Iterable[str] = (),
) -> Optional[Any]:
    """Return the first row in *rows* that matches, or ``None``."""
    nf = tuple(number_fields)
    namef = tuple(name_fields)
    af = tuple(amount_fields)
    df = tuple(date_fields)
    for r in rows:
        if row_matches_find(
            r,
            needle,
            number_fields=nf,
            name_fields=namef,
            amount_fields=af,
            date_fields=df,
        ):
            return r
    return None
