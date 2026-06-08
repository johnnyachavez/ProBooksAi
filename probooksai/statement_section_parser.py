"""
probooksai.statement_section_parser
=====================================
Section-aware parser for Chase-style bank statement PDFs.

Chase (and most JPMorgan-format) statements organise transactions into clearly
labelled sections rather than using a signed amount column.  Each section
determines whether a row is a debit, credit, or check.

Sections recognised
-------------------
  DEPOSITS AND ADDITIONS       → type ``deposit``  (skip by default)
  CHECKS PAID                  → type ``check``    (skip by default)
  ATM & DEBIT CARD WITHDRAWALS → type ``atm_debit`` (include)
  ATM & DEBIT CARD SUMMARY     → summary – skipped
  ELECTRONIC WITHDRAWALS       → type ``electronic`` (include; ACH/Online skipped)
  FEES                         → type ``fee``      (include)
  SERVICE CHARGES              → type ``fee``      (include)

Date format: ``MM/DD`` with no year — the year is inferred from the statement
period header embedded in the extracted text, or supplied via *default_year*.

Multi-line electronic entries (ACH wires with trace numbers, etc.) are
accumulated until a standalone amount line is seen, then emitted as a single
entry with a joined description.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Section catalogue
# ---------------------------------------------------------------------------

SECTION_DEPOSITS  = "DEPOSITS AND ADDITIONS"
SECTION_CHECKS    = "CHECKS PAID"
SECTION_ATM       = "ATM & DEBIT CARD WITHDRAWALS"
SECTION_ATM_SUM   = "ATM & DEBIT CARD SUMMARY"
SECTION_ELECTRONIC = "ELECTRONIC WITHDRAWALS"
SECTION_FEES      = "FEES"
SECTION_FEES2     = "SERVICE CHARGES"

# (txn_type, include_by_default)
_SECTION_META: dict[str, tuple[str, bool]] = {
    SECTION_DEPOSITS:    ("deposit",    False),
    SECTION_CHECKS:      ("check",      False),
    SECTION_ATM:         ("atm_debit",  True),
    SECTION_ATM_SUM:     ("_summary",   False),
    SECTION_ELECTRONIC:  ("electronic", True),
    SECTION_FEES:        ("fee",        True),
    SECTION_FEES2:       ("fee",        True),
}

# Pretty labels shown in the review dialog
TXN_TYPE_LABELS: dict[str, str] = {
    "deposit":    "Deposit",
    "check":      "Check",
    "atm_debit":  "ATM / Debit Card",
    "electronic": "Electronic",
    "fee":        "Fee / Service Charge",
}

# Patterns in ELECTRONIC WITHDRAWALS that are ACH / online payments
# (skipped by default — need manual matching to bills/invoices)
_ACH_RE = re.compile(
    r"(online\s+ach\s+payment|online\s+ach|ach\s+payment|ach\s+transfer|"
    r"online\s+payment|online\s+transfer|online\s+banking|"
    r"zelle\s+payment|zelle|bill\s+pay\b)",
    re.IGNORECASE,
)

# Section header line — exact match (stripped)
_SECTION_RE = re.compile(
    r"^(DEPOSITS AND ADDITIONS|CHECKS PAID|"
    r"ATM & DEBIT CARD WITHDRAWALS|ATM & DEBIT CARD SUMMARY|"
    r"ELECTRONIC WITHDRAWALS|FEES|SERVICE CHARGES)\s*$"
)

# Statement period line, e.g. "January 01, 2022 through January 31, 2022"
_PERIOD_RE = re.compile(
    r"(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+\d{1,2},\s+(\d{4})\s+through",
    re.IGNORECASE,
)

# Single-line transaction: MM/DD  description  amount
_TX_LINE_RE = re.compile(
    r"^\s*(\d{1,2}/\d{2})\s+(.+?)\s+([\d,]+\.\d{2})\s*$"
)

# Standalone amount line (continuation of multi-line entry)
_AMT_ONLY_RE = re.compile(r"^\s*([\d,]+\.\d{2})\s*$")

# Lines to skip
_SKIP_RE = re.compile(
    r"^(total|subtotal|beginning balance|ending balance|"
    r"account number|page \d|member fdic|jpmorgan chase)",
    re.IGNORECASE,
)
_BLANK_OR_RULE_RE = re.compile(r"^[\s\-_=.*|]*$")

# Check line: CHECK_NO [^*] MM/DD [$]AMOUNT
_CHECK_RE = re.compile(
    r"^\s*(\d+)\s*[\^*]?\s*(\d{1,2}/\d{2})\s+\$?([\d,]+\.\d{2})\s*$"
)

# Date-at-start for multi-line entries
_DATE_START_RE = re.compile(r"^\s*(\d{1,2}/\d{2})\s+(.*)")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class StatementEntry:
    """One parsed transaction from a section-structured bank statement."""

    txn_date:    str            # YYYY-MM-DD
    description: str
    amount:      float          # negative = debit, positive = deposit
    txn_type:    str            # see TXN_TYPE_LABELS
    section:     str            # raw section header
    raw_lines:   list[str] = field(default_factory=list)

    # Classification flags
    is_ach:       bool = False   # Online ACH / Zelle / bill-pay
    is_duplicate: bool = False   # already in bank_transactions for this account
    include:      bool = True    # default include/exclude based on section rules

    @property
    def type_label(self) -> str:
        return TXN_TYPE_LABELS.get(self.txn_type, self.txn_type)

    @property
    def amount_display(self) -> str:
        return f"${abs(self.amount):,.2f}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _amt(s: str) -> float:
    return float(s.replace(",", ""))


def _norm_date(mm_dd: str, year: int) -> str:
    parts = mm_dd.strip().split("/")
    m, d = int(parts[0]), int(parts[1])
    return f"{year}-{m:02d}-{d:02d}"


def _extract_year(text: str, default: int) -> int:
    """Pull the statement year from the period line, e.g. '…January 01, 2022 through…'."""
    m = _PERIOD_RE.search(text)
    if m:
        return int(m.group(1))
    return default


# ---------------------------------------------------------------------------
# Public parser
# ---------------------------------------------------------------------------

def parse_section_statement(
    text: str,
    *,
    default_year: int = 2022,
) -> list[StatementEntry]:
    """
    Parse a Chase-style bank statement into :class:`StatementEntry` objects.

    Parameters
    ----------
    text:
        Raw text from ``extract_text_from_pdf()``.
    default_year:
        Year used when the statement period line cannot be found in *text*.
        Typically inferred from the PDF filename (e.g. ``20220131`` → 2022).

    Returns
    -------
    list[StatementEntry]
        All entries including filtered ones (``include=False``).
        Callers apply their own include/filter logic on top.
    """
    year = _extract_year(text, default_year)
    entries: list[StatementEntry] = []
    lines = text.splitlines()

    cur_section: Optional[str] = None
    cur_type:    Optional[str] = None
    cur_include: bool = False

    # Multi-line accumulation (ELECTRONIC WITHDRAWALS)
    pend_date:  Optional[str] = None
    pend_lines: list[str] = []

    def _flush_pending() -> None:
        nonlocal pend_date, pend_lines
        if not pend_date or not pend_lines:
            pend_date = None
            pend_lines = []
            return
        # Check if last accumulated line was just an amount
        amt_val: Optional[float] = None
        desc_lines = pend_lines[:]
        m_amt = _AMT_ONLY_RE.match(pend_lines[-1]) if pend_lines else None
        if m_amt:
            amt_val = _amt(m_amt.group(1))
            desc_lines = pend_lines[:-1]
        else:
            # Try inline amount on last desc line
            m_tx = _TX_LINE_RE.match(f"00/00 " + pend_lines[-1]) if pend_lines else None
            if m_tx:
                pass  # handled in main loop
        if amt_val is None:
            pend_date = None
            pend_lines = []
            return

        desc = " ".join(l.strip() for l in desc_lines if l.strip())
        is_ach = bool(_ACH_RE.search(desc))
        entries.append(StatementEntry(
            txn_date    = _norm_date(pend_date, year),
            description = desc[:300] or "Electronic Withdrawal",
            amount      = -abs(amt_val),
            txn_type    = cur_type or "electronic",
            section     = cur_section or "",
            raw_lines   = list(pend_lines),
            is_ach      = is_ach,
            include     = cur_include and not is_ach,
        ))
        pend_date = None
        pend_lines = []

    for raw_line in lines:
        stripped = raw_line.strip()

        # ── Section header ───────────────────────────────────────────────
        m_sec = _SECTION_RE.match(stripped)
        if m_sec:
            _flush_pending()
            cur_section = m_sec.group(1)
            meta = _SECTION_META.get(cur_section)
            if meta:
                cur_type, cur_include = meta
            else:
                cur_type, cur_include = None, False
            continue

        if cur_section is None or cur_type is None or cur_type == "_summary":
            continue
        if _BLANK_OR_RULE_RE.match(stripped) or not stripped:
            continue
        if _SKIP_RE.match(stripped):
            _flush_pending()
            continue

        # ── CHECKS PAID ─────────────────────────────────────────────────
        if cur_section == SECTION_CHECKS:
            mc = _CHECK_RE.match(stripped)
            if mc:
                entries.append(StatementEntry(
                    txn_date    = _norm_date(mc.group(2), year),
                    description = f"Check #{mc.group(1)}",
                    amount      = -_amt(mc.group(3)),
                    txn_type    = "check",
                    section     = cur_section,
                    raw_lines   = [stripped],
                    include     = False,   # checks must be manually posted
                ))
            continue

        # ── Normal single-line: MM/DD  description  amount ──────────────
        m_tx = _TX_LINE_RE.match(stripped)
        if m_tx:
            _flush_pending()
            date_s, desc, amt_s = m_tx.group(1), m_tx.group(2).strip(), m_tx.group(3)
            is_ach = (cur_section == SECTION_ELECTRONIC and bool(_ACH_RE.search(desc)))
            sign = +1 if cur_section == SECTION_DEPOSITS else -1
            entries.append(StatementEntry(
                txn_date    = _norm_date(date_s, year),
                description = desc[:300],
                amount      = round(sign * _amt(amt_s), 2),
                txn_type    = cur_type,
                section     = cur_section,
                raw_lines   = [stripped],
                is_ach      = is_ach,
                include     = cur_include and not is_ach,
            ))
            continue

        # ── Multi-line ELECTRONIC entry ──────────────────────────────────
        if cur_section == SECTION_ELECTRONIC:
            m_ds = _DATE_START_RE.match(stripped)
            if m_ds:
                _flush_pending()
                pend_date  = m_ds.group(1)
                pend_lines = [m_ds.group(2)] if m_ds.group(2).strip() else []
                continue
            if pend_date is not None:
                m_ao = _AMT_ONLY_RE.match(stripped)
                if m_ao:
                    # Standalone amount terminates the multi-line entry
                    pend_lines.append(stripped)
                    _flush_pending()
                else:
                    pend_lines.append(stripped)
                continue

    _flush_pending()
    return entries


# ---------------------------------------------------------------------------
# Dedup helper
# ---------------------------------------------------------------------------

def mark_duplicates(
    entries: list[StatementEntry],
    conn,
    account_id: int,
    *,
    tolerance_days: int = 1,
    amount_tolerance: float = 0.01,
) -> None:
    """
    Set ``entry.is_duplicate = True`` for rows already present in
    ``bank_transactions`` for *account_id*.

    Matching criteria: same amount (within *amount_tolerance*) **and**
    date within *tolerance_days*.  Does NOT modify ``entry.include``.
    """
    try:
        rows = conn.execute(
            """
            SELECT txn_date, amount
            FROM bank_transactions
            WHERE bank_account_id = ?
            """,
            (account_id,),
        ).fetchall()
    except Exception:
        return

    # Build lookup: (date_str, rounded_amount) → True
    from datetime import date, timedelta

    existing: set[tuple[str, float]] = set()
    for r in rows:
        d_str = str(r["txn_date"] or "").strip()[:10]
        try:
            d = date.fromisoformat(d_str)
        except ValueError:
            continue
        amt = round(float(r["amount"] or 0), 2)
        for delta in range(-tolerance_days, tolerance_days + 1):
            day = d + timedelta(days=delta)
            existing.add((day.isoformat(), amt))

    for entry in entries:
        amt_r = round(entry.amount, 2)
        if (entry.txn_date, amt_r) in existing:
            entry.is_duplicate = True
