"""
probooksai.bank_import
======================
CSV parsing, column mapping, date normalisation, and duplicate detection
for the Bank Import feature (Issue #9, Phase 1 – CSV-first).

OFX/QFX parsing is explicitly deferred to a future phase.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import unicodedata
from datetime import date, datetime
from typing import Optional

# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

# Ordered list of format strings to try.  The *first* match wins.
# Default expectation is DD/MM/YYYY (per user preference), so that appears
# at the top of the list.
_DATE_FORMATS = [
    "%d/%m/%Y",   # DD/MM/YYYY  ← default / most common in UK/AU banking
    "%d-%m-%Y",   # DD-MM-YYYY
    "%d.%m.%Y",   # DD.MM.YYYY
    "%Y-%m-%d",   # ISO 8601
    "%m/%d/%Y",   # US MM/DD/YYYY
    "%m-%d-%Y",
    "%d/%m/%y",   # DD/MM/YY  (2-digit year)
    "%m/%d/%y",   # US MM/DD/YY
    "%Y%m%d",     # OFX compact
    "%d %b %Y",   # 01 Jan 2025
    "%d %B %Y",   # 01 January 2025
    "%b %d, %Y",  # Jan 01, 2025
    "%B %d, %Y",  # January 01, 2025
]


def parse_date(value: str) -> Optional[date]:
    """
    Try every known format and return the first successful parse as a
    ``datetime.date``.  Returns *None* when the value cannot be parsed.
    """
    value = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Amount parsing
# ---------------------------------------------------------------------------

def parse_amount(value: str) -> Optional[float]:
    """
    Convert a bank-statement amount string to a signed float.

    Handles:
    - Parenthesised negatives: (123.45) → -123.45
    - Currency symbols: $, £, €, etc.
    - Thousands separators: 1,234.56
    """
    value = value.strip()
    negative = False
    if value.startswith("(") and value.endswith(")"):
        negative = True
        value = value[1:-1].strip()
    if value.startswith("-"):
        negative = True
        value = value[1:].strip()
    # Strip currency symbols and whitespace
    value = re.sub(r"[^\d.,]", "", value)
    if not value:
        return None
    # Handle comma-as-decimal vs thousands separator:
    # If there's both a comma and a dot, the last one is the decimal
    if "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            # European: 1.234,56
            value = value.replace(".", "").replace(",", ".")
        else:
            # US: 1,234.56
            value = value.replace(",", "")
    elif "," in value and "." not in value:
        # Could be European decimal or just thousands – check position
        parts = value.split(",")
        if len(parts) == 2 and len(parts[1]) == 2:
            # Looks like a decimal comma: 123,45
            value = value.replace(",", ".")
        else:
            # Thousands separator: 1,234
            value = value.replace(",", "")
    try:
        result = float(value)
        return -result if negative else result
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# CSV sniffing & reading
# ---------------------------------------------------------------------------

def read_csv_preview(path: str, max_rows: int = 10) -> tuple[list[str], list[list[str]]]:
    """
    Open a CSV file and return ``(headers, preview_rows)``.

    *headers* is a list of column-name strings (first row).
    *preview_rows* is a list of up to *max_rows* raw string rows (not including
    the header).
    """
    with open(path, newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(8192)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(fh, dialect=dialect)
        headers = next(reader, [])
        rows = []
        for i, row in enumerate(reader):
            if i >= max_rows:
                break
            rows.append(row)
    return [h.strip() for h in headers], rows


def _count_csv_rows(path: str) -> int:
    """Return the number of data rows (excluding header) in a CSV file."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(8192)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(fh, dialect=dialect)
        next(reader, None)  # skip header
        return sum(1 for _ in reader)


# ---------------------------------------------------------------------------
# Column mapping
# ---------------------------------------------------------------------------

class ColumnMapping:
    """
    Describes how CSV columns map to the normalised transaction fields.

    Required fields: ``date``, ``description``, and either ``amount`` or both
    ``debit`` / ``credit``.

    Optional fields: ``balance``, ``currency``, ``reference``.
    """

    REQUIRED_FIELDS = ("date", "description")
    AMOUNT_FIELDS = ("amount", "debit", "credit")

    def __init__(
        self,
        date: Optional[str] = None,
        description: Optional[str] = None,
        amount: Optional[str] = None,
        debit: Optional[str] = None,
        credit: Optional[str] = None,
        balance: Optional[str] = None,
        currency: Optional[str] = None,
        reference: Optional[str] = None,
    ):
        self.date = date
        self.description = description
        self.amount = amount
        self.debit = debit
        self.credit = credit
        self.balance = balance
        self.currency = currency
        self.reference = reference

    def validate(self) -> list[str]:
        """Return a list of human-readable error strings (empty = valid)."""
        errors: list[str] = []
        if not self.date:
            errors.append("'date' column is required.")
        if not self.description:
            errors.append("'description' column is required.")
        has_amount = bool(self.amount)
        has_debit_credit = bool(self.debit) and bool(self.credit)
        if not has_amount and not has_debit_credit:
            errors.append(
                "Either 'amount' OR both 'debit' and 'credit' columns are required."
            )
        return errors

    @classmethod
    def auto_detect(cls, headers: list[str]) -> "ColumnMapping":
        """
        Heuristically detect column mappings from a list of CSV header names.

        Matching is case-insensitive and ignores leading/trailing whitespace.
        """
        normalised = {h.lower().strip(): h for h in headers}

        def pick(*candidates) -> Optional[str]:
            for c in candidates:
                if c in normalised:
                    return normalised[c]
            return None

        return cls(
            date=pick("date", "posted date", "transaction date", "value date", "trans date", "txn date"),
            description=pick("description", "memo", "narrative", "details", "transaction details", "payee", "merchant"),
            amount=pick("amount", "transaction amount", "txn amount"),
            debit=pick("debit", "debit amount", "withdrawals", "withdrawal"),
            credit=pick("credit", "credit amount", "deposits", "deposit"),
            balance=pick("balance", "running balance", "available balance"),
            currency=pick("currency", "ccy"),
            reference=pick("reference", "ref", "cheque no", "check no"),
        )


# ---------------------------------------------------------------------------
# Transaction parsing
# ---------------------------------------------------------------------------

class ParsedTransaction:
    """One normalised transaction from a CSV row."""

    __slots__ = (
        "source_row",
        "posted_date",
        "description",
        "amount",
        "currency",
        "reference",
        "parse_errors",
        "fingerprint",
    )

    def __init__(
        self,
        source_row: int,
        posted_date: Optional[date],
        description: str,
        amount: Optional[float],
        currency: str = "USD",
        reference: str = "",
        parse_errors: Optional[list[str]] = None,
    ):
        self.source_row = source_row
        self.posted_date = posted_date
        self.description = description
        self.amount = amount
        self.currency = currency
        self.reference = reference
        self.parse_errors = parse_errors or []
        self.fingerprint = ""  # computed separately


def _normalise_description(text: str) -> str:
    """Collapse whitespace and remove diacritics for consistent matching."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.lower().split())


def compute_fingerprint(
    posted_date: Optional[date],
    amount: Optional[float],
    description: str,
    batch_source: str = "",
) -> str:
    """
    Return a SHA-256 hex fingerprint for duplicate detection.

    Uses ``(date_iso, amount_rounded, normalised_description, batch_source)``
    as the composite key.  The *batch_source* is typically the source filename,
    making cross-file deduplication explicit.
    """
    date_str = posted_date.isoformat() if posted_date else ""
    amount_str = f"{amount:.2f}" if amount is not None else ""
    desc_str = _normalise_description(description)
    raw = f"{date_str}|{amount_str}|{desc_str}|{batch_source}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_csv(
    path: str,
    mapping: ColumnMapping,
    source_filename: str = "",
) -> list[ParsedTransaction]:
    """
    Parse a CSV file using *mapping* and return a list of
    :class:`ParsedTransaction` objects.

    *source_filename* is used in the duplicate-detection fingerprint; pass the
    base filename of the file (not the full path) for stable fingerprints.
    """
    transactions: list[ParsedTransaction] = []

    with open(path, newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(8192)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(fh, dialect=dialect)
        # Strip whitespace from header keys
        reader.fieldnames = [h.strip() for h in (reader.fieldnames or [])]

        for row_idx, raw_row in enumerate(reader, start=2):  # 1-based, row 1 = header
            errors: list[str] = []

            # Date
            date_raw = (raw_row.get(mapping.date) or "").strip()
            posted_date = parse_date(date_raw) if date_raw else None
            if not posted_date and date_raw:
                errors.append(f"Cannot parse date: {date_raw!r}")

            # Description
            description = (raw_row.get(mapping.description) or "").strip()

            # Amount (single column) or debit/credit pair
            amount: Optional[float] = None
            if mapping.amount:
                amount_raw = (raw_row.get(mapping.amount) or "").strip()
                if amount_raw:
                    amount = parse_amount(amount_raw)
                    if amount is None:
                        errors.append(f"Cannot parse amount: {amount_raw!r}")
            elif mapping.debit and mapping.credit:
                debit_raw  = (raw_row.get(mapping.debit)  or "").strip()
                credit_raw = (raw_row.get(mapping.credit) or "").strip()
                debit  = parse_amount(debit_raw)  if debit_raw  else None
                credit = parse_amount(credit_raw) if credit_raw else None
                if debit is not None:
                    amount = -(abs(debit))   # debits are negative
                elif credit is not None:
                    amount = abs(credit)     # credits are positive

            # Currency
            currency = "USD"
            if mapping.currency:
                currency = (raw_row.get(mapping.currency) or "USD").strip() or "USD"

            # Reference
            reference = ""
            if mapping.reference:
                reference = (raw_row.get(mapping.reference) or "").strip()

            txn = ParsedTransaction(
                source_row=row_idx,
                posted_date=posted_date,
                description=description,
                amount=amount,
                currency=currency,
                reference=reference,
                parse_errors=errors,
            )
            txn.fingerprint = compute_fingerprint(
                posted_date, amount, description, source_filename
            )
            transactions.append(txn)

    return transactions


# ---------------------------------------------------------------------------
# Duplicate detection (in-memory, across a list of transactions)
# ---------------------------------------------------------------------------

def flag_duplicates(transactions: list[ParsedTransaction]) -> dict[str, list[int]]:
    """
    Detect duplicate transactions within the provided list.

    Returns a dict mapping fingerprint → list of ``source_row`` values where
    that fingerprint appears more than once.  Single-occurrence fingerprints
    are omitted.
    """
    seen: dict[str, list[int]] = {}
    for txn in transactions:
        seen.setdefault(txn.fingerprint, []).append(txn.source_row)
    return {fp: rows for fp, rows in seen.items() if len(rows) > 1}
