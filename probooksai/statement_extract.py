"""
Phase 7 – Heuristic extraction of bank-like lines from plain text (e.g. PDF text layers).

This does not OCR scanned images. Pair with :mod:`probooksai.statement_pdf` for
digital PDFs. Output rows match CSV import row shape.

Handles the following common bank-statement date / amount layouts:

  • ISO / slash dates at line start:  ``2022-01-15``, ``01/15/22``, ``01/15/2022``
  • Month-name dates at line start:   ``Jan 15``, ``Jan 15,``, ``January 15,``
    (year inferred from context / left blank for ``parse_date`` normalisation)
  • Running-balance column after amount:
      ``01/15  AMAZON PURCHASE   42.99  1,234.56``
      The parser finds all amounts on the rest of the line and picks the
      right-most *non-balance* one (second-to-last when two amounts trail the
      description, last when only one).
  • Signed amounts: ``-42.99`` or ``(42.99)`` are treated as debits.
  • Unsigned amounts: positive-only lines are kept (the caller decides whether
    to filter deposits; see ``filter_deposits`` parameter).
"""

from __future__ import annotations

import re
from typing import Optional

from probooksai.bank_import import parse_date

# ---------------------------------------------------------------------------
# Date patterns
# ---------------------------------------------------------------------------

# ISO / slash: 2022-01-15 | 01/15/2022 | 1/5/22
_DATE_ISO_SLASH = r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})"

# Month-name: Jan 15 | Jan 15, | Jan 15, 2022 | January 15 | January 15, 2022
_MONTHS = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?"
    r"|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
_DATE_MONTH_NAME = rf"({_MONTHS}\s+\d{{1,2}}(?:,?\s*\d{{4}})?)"

# Combined: date at start of line (with optional leading whitespace)
_DATE_HEAD = re.compile(
    rf"^\s*(?:{_DATE_ISO_SLASH}|{_DATE_MONTH_NAME})\s+",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Amount patterns
# ---------------------------------------------------------------------------

# Any decimal amount, optionally negative or in parens
_AMT_PAT = re.compile(r"(\(?-?[\d,]+\.\d{2}\)?)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MONTH_MAP = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}


def _normalise_month_name_date(raw: str) -> Optional[str]:
    """Turn ``Jan 15`` / ``January 15, 2022`` → ``YYYY-MM-DD`` or ``MM/DD`` for parse_date."""
    raw = raw.strip().rstrip(",")
    parts = re.split(r"[\s,]+", raw)
    if not parts:
        return None
    month_key = parts[0][:3].lower()
    month = _MONTH_MAP.get(month_key)
    if not month:
        return None
    if len(parts) >= 3:
        # Month Day Year
        day = parts[1].zfill(2)
        year = parts[2] if len(parts[2]) == 4 else None
        if year:
            return f"{year}-{month}-{day}"
        return f"{month}/{day}/{parts[2]}"
    if len(parts) == 2:
        # Month Day — no year; return MM/DD so parse_date can try
        day = parts[1].zfill(2)
        return f"{month}/{day}"
    return None


def _parse_line_amount(raw: str) -> Optional[float]:
    s = raw.strip()
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    s = re.sub(r"[,\s]", "", s)
    try:
        v = float(s)
    except ValueError:
        return None
    return -abs(v) if neg else v


def _date_from_match(m: re.Match) -> Optional[str]:
    """Return a normalised date string from a _DATE_HEAD match (either group)."""
    iso_slash = m.group(1)   # e.g. "01/15/2022" or "2022-01-15"
    month_name = m.group(2)  # e.g. "Jan 15" or "January 15, 2022"
    if iso_slash:
        return parse_date(iso_slash)
    if month_name:
        normalised = _normalise_month_name_date(month_name)
        if normalised:
            return parse_date(normalised)
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_statement_text(text: str, *, filter_deposits: bool = False) -> list[dict]:
    """
    Parse *text* line-by-line into transaction dicts:
    ``txn_date``, ``description``, ``amount``, ``ref_number`` (empty).

    Strategy
    --------
    1. Detect a date at the start of the line (ISO, slash, or month-name).
    2. Find all decimal amounts in the remainder.
    3. If exactly one amount → use it.
       If two or more amounts → assume the *last* is a running balance; use
       the second-to-last as the transaction amount.
    4. Description = text between the date and the chosen amount field.

    Parameters
    ----------
    filter_deposits:
        When ``True``, rows with a positive amount (deposits / credits) are
        silently dropped.  Debits are stored as negative values; unsigned
        positive amounts are kept unless *filter_deposits* is set.
    """
    rows: list[dict] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if len(line) < 10:
            continue

        m_date = _DATE_HEAD.match(line)
        if not m_date:
            continue

        date_norm = _date_from_match(m_date)
        if not date_norm:
            continue

        rest = line[m_date.end():]
        amounts = list(_AMT_PAT.finditer(rest))
        if not amounts:
            continue

        # Pick transaction amount:
        #   • 1 amount  → that one
        #   • 2 amounts → first is transaction, last is running balance
        #   • 3+        → second-to-last is transaction, last is balance
        if len(amounts) == 1:
            amt_match = amounts[0]
        elif len(amounts) == 2:
            amt_match = amounts[0]   # amount | balance
        else:
            amt_match = amounts[-2]  # ... | amount | balance

        amt = _parse_line_amount(amt_match.group(1))
        if amt is None:
            continue

        if filter_deposits and amt > 0:
            continue

        # Description: text before the chosen amount field
        desc = rest[: amt_match.start()].strip()
        # Strip any trailing numbers that leaked into desc (prev balance columns)
        desc = re.sub(r"\s+[\d,]+\.\d{2}\s*$", "", desc).strip()
        if not desc:
            desc = "Transaction"

        rows.append(
            {
                "txn_date": date_norm,
                "description": desc,
                "amount": round(amt, 2),
                "ref_number": "",
            }
        )
    return rows
