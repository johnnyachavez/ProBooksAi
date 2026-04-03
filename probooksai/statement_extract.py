"""
Phase 7 – Heuristic extraction of bank-like lines from plain text (e.g. PDF text layers).

This does not OCR scanned images. Pair with :mod:`probooksai.statement_pdf` for
digital PDFs. Output rows match CSV import row shape.
"""

from __future__ import annotations

import re
from typing import Optional

from probooksai.bank_import import parse_date

_DATE_HEAD = re.compile(r"^(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})\s+")
_AMT_TAIL = re.compile(r"(\(?-?[\d,]+\.\d{2}\)?)\s*$")


def _parse_line_amount(raw: str) -> Optional[float]:
    s = raw.strip()
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    s = re.sub(r"[,\s]", "", s)
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def parse_statement_text(text: str) -> list[dict]:
    """
    Parse *text* line-by-line into transaction dicts:
    ``txn_date``, ``description``, ``amount``, ``ref_number`` (empty).

    Each line must start with a parseable date, end with a decimal amount
    (commas allowed; parentheses mean negative), and have description between.
    """
    rows: list[dict] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if len(line) < 12:
            continue
        m_date = _DATE_HEAD.match(line)
        m_amt = _AMT_TAIL.search(line)
        if not m_date or not m_amt:
            continue
        if m_amt.start() <= m_date.end():
            continue
        date_norm = parse_date(m_date.group(1))
        if not date_norm:
            continue
        amt = _parse_line_amount(m_amt.group(1))
        if amt is None:
            continue
        desc = line[m_date.end() : m_amt.start()].strip()
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
