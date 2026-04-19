"""Bank Statement Intake — phase 1 (review-first).

Normalizes bank statement rows out of three input shapes — **CSV upload**,
**PDF upload** (text layer only; no image OCR in this phase), and **pasted
statement text** — into a single ``BankStatementIntakeRow`` schema designed
for a review table.

This module **never** writes to the database, never auto-classifies to COA,
and never creates Bank Register transactions. Bank Register remains the
source of truth — extracted rows are intentionally staged for human review.

The 10-field normalized schema per row
--------------------------------------

* ``txn_date``         – ISO ``YYYY-MM-DD`` if confidently parsed, else ``""``.
* ``description_raw``  – Best-effort raw description (whitespace collapsed,
  no semantic editing).
* ``debit``            – Outflow magnitude as ``float`` (always ``>= 0``) or
  ``None`` when the row is a credit / unknown side.
* ``credit``           – Inflow magnitude as ``float`` (always ``>= 0``) or
  ``None`` when the row is a debit / unknown side.
* ``amount_signed``    – Signed amount with the project sign convention
  (outflows negative, inflows positive). ``None`` when no amount could be
  parsed at all.
* ``running_balance``  – Statement running balance for that row when present
  in the source, otherwise ``None``.
* ``source_type``      – ``"csv"`` | ``"pdf"`` | ``"text"``.
* ``source_ref``       – Caller-supplied origin hint (filename, page number,
  paste label, etc.). Free-text; never parsed.
* ``confidence``       – ``0.0``..``1.0`` extractor self-rating. ``1.0`` is
  "all required fields parsed cleanly".
* ``needs_review``     – ``True`` when the row should not be trusted without
  human eyes (missing date / amount, ambiguous columns, etc.).

Sign convention (matches :mod:`probooksai.bank_import`)
--------------------------------------------------------

* Outflows / withdrawals / payments / debits → negative ``amount_signed``.
* Inflows  / deposits / credits             → positive ``amount_signed``.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import asdict, dataclass, field
from typing import Iterable, Optional

from probooksai.bank_import import parse_amount, parse_date

SOURCE_TYPE_CSV = "csv"
SOURCE_TYPE_PDF = "pdf"
SOURCE_TYPE_TEXT = "text"

VALID_SOURCE_TYPES = (SOURCE_TYPE_CSV, SOURCE_TYPE_PDF, SOURCE_TYPE_TEXT)

# Confidence floor at or above which a row is **not** flagged needs_review.
# Any extractor that drops below this should also set ``needs_review=True``.
CONFIDENCE_REVIEW_THRESHOLD = 0.80


@dataclass
class BankStatementIntakeRow:
    """One staged statement row for the review table (mutable; user edits).

    All fields are independent so the review-table UI can patch any one of
    them in place. ``needs_review`` is a hint for sorting/filtering — it does
    **not** block downstream steps; nothing in this module auto-posts.
    """

    txn_date: str = ""
    description_raw: str = ""
    debit: Optional[float] = None
    credit: Optional[float] = None
    amount_signed: Optional[float] = None
    running_balance: Optional[float] = None
    source_type: str = ""
    source_ref: str = ""
    confidence: float = 0.0
    needs_review: bool = True

    def to_dict(self) -> dict:
        """Plain-dict copy (handy for table population, JSON dumps, tests)."""
        return asdict(self)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _round_amount(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), 2)


def _split_signed_to_debit_credit(
    amount_signed: Optional[float],
) -> tuple[Optional[float], Optional[float]]:
    """Mirror the sign convention into the two-sided ``debit`` / ``credit`` view."""
    if amount_signed is None:
        return None, None
    if amount_signed < 0:
        return abs(round(amount_signed, 2)), None
    if amount_signed > 0:
        return None, round(amount_signed, 2)
    return 0.0, 0.0


def _combine_debit_credit_to_signed(
    debit: Optional[float], credit: Optional[float]
) -> Optional[float]:
    """``debit`` and ``credit`` magnitudes → signed amount (outflows negative)."""
    d = abs(round(debit, 2)) if debit not in (None, "") else None
    c = abs(round(credit, 2)) if credit not in (None, "") else None
    if d is None and c is None:
        return None
    if d and c and d > 0 and c > 0:
        # Both filled — caller will flag needs_review; choose the larger
        # magnitude so the sign reflects the dominant side rather than zero.
        if d >= c:
            return -d
        return c
    if d:
        return -d
    return c


def _collapse_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _confidence_for(
    *, has_date: bool, has_amount: bool, has_description: bool
) -> float:
    """Simple monotonic confidence — required fields drive the score."""
    if has_date and has_amount and has_description:
        return 1.0
    if has_date and has_amount:
        return 0.85
    if has_amount and has_description:
        return 0.55
    if has_amount:
        return 0.45
    if has_date and has_description:
        return 0.30
    return 0.10


def _needs_review(confidence: float, *, ambiguous: bool = False) -> bool:
    if ambiguous:
        return True
    return confidence < CONFIDENCE_REVIEW_THRESHOLD


# ---------------------------------------------------------------------------
# CSV intake
# ---------------------------------------------------------------------------

# Header keyword groups — case-insensitive substring match against the trimmed
# header label. Order matters: more specific keywords come first.
_CSV_DATE_KEYWORDS = (
    "transaction date",
    "posted date",
    "post date",
    "txn date",
    "date posted",
    "date",
    "posted",
)
_CSV_DESCRIPTION_KEYWORDS = (
    "description",
    "details",
    "memo",
    "payee",
    "narrative",
    "transaction",
    "name",
)
_CSV_AMOUNT_KEYWORDS = (
    "amount",
    "amt",
    "transaction amount",
)
_CSV_DEBIT_KEYWORDS = (
    "debit",
    "withdrawal",
    "withdrawals",
    "payment",
    "outflow",
    "money out",
)
_CSV_CREDIT_KEYWORDS = (
    "credit",
    "deposit",
    "deposits",
    "inflow",
    "money in",
)
_CSV_BALANCE_KEYWORDS = (
    "running balance",
    "balance",
    "bal",
)


def _normalize_header(s: str) -> str:
    return (s or "").strip().lower()


def _pick_column(
    headers: list[str], keywords: tuple[str, ...]
) -> Optional[str]:
    """First header whose normalized form contains any keyword (longest first)."""
    norm = [(_normalize_header(h), h) for h in headers if h]
    sorted_kws = sorted(keywords, key=len, reverse=True)
    for kw in sorted_kws:
        for n, original in norm:
            if kw in n:
                return original
    return None


@dataclass(frozen=True)
class _CsvColumnPlan:
    """Detected column roles for a CSV statement (None = column not present)."""

    date_col: Optional[str]
    description_col: Optional[str]
    amount_col: Optional[str]
    debit_col: Optional[str]
    credit_col: Optional[str]
    balance_col: Optional[str]


def detect_csv_column_plan(headers: Iterable[str]) -> _CsvColumnPlan:
    """Heuristic CSV column-role detection (case-insensitive substring match).

    Returns a plan with ``None`` for any column that is not confidently
    detected. Either ``amount_col`` (single signed column) **or** the
    ``debit_col`` / ``credit_col`` pair is expected on a normal statement;
    the extractor handles either shape.
    """
    hdrs = [h for h in headers]
    return _CsvColumnPlan(
        date_col=_pick_column(hdrs, _CSV_DATE_KEYWORDS),
        description_col=_pick_column(hdrs, _CSV_DESCRIPTION_KEYWORDS),
        amount_col=_pick_column(hdrs, _CSV_AMOUNT_KEYWORDS),
        debit_col=_pick_column(hdrs, _CSV_DEBIT_KEYWORDS),
        credit_col=_pick_column(hdrs, _CSV_CREDIT_KEYWORDS),
        balance_col=_pick_column(hdrs, _CSV_BALANCE_KEYWORDS),
    )


def extract_csv_statement(
    content: str, *, source_ref: str = ""
) -> list[BankStatementIntakeRow]:
    """Parse statement CSV text into normalized review rows.

    * Auto-detects date / description / amount (or debit+credit pair) /
      running-balance columns by header keyword match (case-insensitive).
    * Never raises on bad rows — they come back as ``needs_review=True`` with
      ``confidence`` reflecting how much could be parsed.
    * Caller passes a free-text ``source_ref`` (typically the filename).

    No DB writes; no COA classification; no register posting.
    """
    text = content or ""
    if not text.strip():
        return []
    reader = csv.DictReader(io.StringIO(text))
    headers = list(reader.fieldnames or [])
    plan = detect_csv_column_plan(headers)

    rows: list[BankStatementIntakeRow] = []
    for line_no, raw_row in enumerate(reader, start=2):  # row 1 = header
        row = _csv_row_from_dict(
            raw_row,
            plan=plan,
            source_ref=source_ref,
            line_no=line_no,
        )
        rows.append(row)
    return rows


def _csv_row_from_dict(
    raw_row: dict,
    *,
    plan: _CsvColumnPlan,
    source_ref: str,
    line_no: int,
) -> BankStatementIntakeRow:
    raw_date = (raw_row.get(plan.date_col) or "").strip() if plan.date_col else ""
    txn_date = parse_date(raw_date) if raw_date else None

    raw_desc = (
        (raw_row.get(plan.description_col) or "").strip()
        if plan.description_col
        else ""
    )
    description_raw = _collapse_whitespace(raw_desc)

    debit_val: Optional[float] = None
    credit_val: Optional[float] = None
    amount_signed: Optional[float] = None
    ambiguous_amount = False

    if plan.debit_col or plan.credit_col:
        if plan.debit_col:
            d_raw = (raw_row.get(plan.debit_col) or "").strip()
            if d_raw:
                d_parsed = parse_amount(d_raw)
                if d_parsed is not None:
                    debit_val = abs(round(d_parsed, 2))
        if plan.credit_col:
            c_raw = (raw_row.get(plan.credit_col) or "").strip()
            if c_raw:
                c_parsed = parse_amount(c_raw)
                if c_parsed is not None:
                    credit_val = abs(round(c_parsed, 2))
        if debit_val is not None and credit_val is not None and debit_val > 0 and credit_val > 0:
            ambiguous_amount = True
        amount_signed = _combine_debit_credit_to_signed(debit_val, credit_val)
    elif plan.amount_col:
        a_raw = (raw_row.get(plan.amount_col) or "").strip()
        if a_raw:
            amount_signed = parse_amount(a_raw)
            if amount_signed is not None:
                debit_val, credit_val = _split_signed_to_debit_credit(amount_signed)

    running_balance: Optional[float] = None
    if plan.balance_col:
        b_raw = (raw_row.get(plan.balance_col) or "").strip()
        if b_raw:
            b_parsed = parse_amount(b_raw)
            if b_parsed is not None:
                running_balance = round(b_parsed, 2)

    confidence = _confidence_for(
        has_date=bool(txn_date),
        has_amount=amount_signed is not None,
        has_description=bool(description_raw),
    )
    needs_review = _needs_review(confidence, ambiguous=ambiguous_amount)

    ref = source_ref.strip() if source_ref else ""
    full_ref = f"{ref}#L{line_no}" if ref else f"L{line_no}"

    return BankStatementIntakeRow(
        txn_date=txn_date or "",
        description_raw=description_raw,
        debit=_round_amount(debit_val),
        credit=_round_amount(credit_val),
        amount_signed=_round_amount(amount_signed),
        running_balance=_round_amount(running_balance),
        source_type=SOURCE_TYPE_CSV,
        source_ref=full_ref,
        confidence=round(confidence, 2),
        needs_review=needs_review,
    )


# ---------------------------------------------------------------------------
# Pasted-text intake
# ---------------------------------------------------------------------------

# A line shaped like a statement row: starts with a date, has at least one
# decimal money value somewhere afterward (cents required so we don't match
# stray dates / phone numbers).
_TEXT_DATE_HEAD = re.compile(
    r"^\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b"
)
_TEXT_MONEY = re.compile(
    r"(?<![\d.])(\(?-?\$?\s*\d{1,3}(?:,\d{3})*\.\d{2}\)?|"
    r"\(?-?\$?\s*\d+\.\d{2}\)?)(?:\s*(CR|DR))?(?![\d.])",
    re.IGNORECASE,
)


def _parse_text_money_token(token: str, suffix: str = "") -> Optional[float]:
    """Parse a money token like ``-$1,234.56`` / ``(50.00)`` / ``75.00 CR``."""
    t = token.strip()
    suffix = (suffix or "").strip().upper()
    parsed = parse_amount(t)
    if parsed is None:
        return None
    if suffix == "DR":
        parsed = -abs(parsed)
    elif suffix == "CR":
        parsed = abs(parsed)
    return round(parsed, 2)


def _scan_text_money(line: str) -> list[tuple[float, tuple[int, int]]]:
    """All (value, span) money tokens in a line, in left-to-right order."""
    out: list[tuple[float, tuple[int, int]]] = []
    for m in _TEXT_MONEY.finditer(line):
        token = m.group(1)
        suffix = m.group(2) or ""
        val = _parse_text_money_token(token, suffix)
        if val is None:
            continue
        out.append((val, m.span()))
    return out


def _strip_spans(line: str, spans: list[tuple[int, int]]) -> str:
    if not spans:
        return line
    chars = list(line)
    for start, end in spans:
        for i in range(start, min(end, len(chars))):
            chars[i] = " "
    return "".join(chars)


def extract_pasted_text_statement(
    text: str, *, source_ref: str = ""
) -> list[BankStatementIntakeRow]:
    """Parse pasted statement text into normalized review rows.

    Strategy: each non-empty line must start with a parseable date and
    contain at least one money value (with cents). The **last** money value
    on the line is treated as the running balance when two or more values
    are present; the **first** money value is the transaction amount. Lines
    that don't fit are dropped (not staged) — that's safer than guessing
    and creating noise in the review table.
    """
    if not text:
        return []
    rows: list[BankStatementIntakeRow] = []
    src = (source_ref or "").strip()
    for raw_line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip()
        if not line.strip():
            continue
        m_date = _TEXT_DATE_HEAD.match(line)
        if not m_date:
            continue
        date_token = m_date.group(1)
        date_iso = parse_date(date_token)
        if not date_iso:
            continue

        money = _scan_text_money(line)
        if not money:
            continue
        amount_signed = money[0][0]
        running_balance: Optional[float] = None
        if len(money) >= 2:
            # Conservative: last money value = balance only when it's clearly
            # to the right of the amount.
            running_balance = money[-1][0]

        # Strip date and money spans to get a description.
        date_span = m_date.span(1)
        spans = [date_span] + [span for _, span in money]
        desc = _strip_spans(line, spans)
        description_raw = _collapse_whitespace(desc)

        debit_val, credit_val = _split_signed_to_debit_credit(amount_signed)

        confidence = _confidence_for(
            has_date=True,
            has_amount=True,
            has_description=bool(description_raw),
        )
        needs_review = _needs_review(confidence)

        full_ref = f"{src}#L{raw_line_no}" if src else f"L{raw_line_no}"

        rows.append(
            BankStatementIntakeRow(
                txn_date=date_iso,
                description_raw=description_raw,
                debit=_round_amount(debit_val),
                credit=_round_amount(credit_val),
                amount_signed=_round_amount(amount_signed),
                running_balance=_round_amount(running_balance),
                source_type=SOURCE_TYPE_TEXT,
                source_ref=full_ref,
                confidence=round(confidence, 2),
                needs_review=needs_review,
            )
        )
    return rows


# ---------------------------------------------------------------------------
# PDF intake (text layer only)
# ---------------------------------------------------------------------------


def extract_pdf_statement(
    pdf_path: str, *, source_ref: str = ""
) -> list[BankStatementIntakeRow]:
    """Extract a PDF bank statement's **text layer** and parse via the text path.

    Image-only / scanned PDFs aren't handled in phase 1 — they'll come back
    as an empty list (the file has no extractable text layer). OCR is an
    explicit follow-up.

    ``source_ref`` defaults to the file's basename so review rows carry a
    useful origin label even when the caller passes nothing.
    """
    from probooksai.statement_pdf import extract_text_from_pdf

    text = extract_text_from_pdf(pdf_path)
    ref = source_ref.strip() if source_ref else ""
    if not ref:
        # Best-effort label so review rows aren't anonymous.
        try:
            from pathlib import Path as _Path

            ref = _Path(pdf_path).name
        except Exception:  # pragma: no cover - defensive
            ref = "pdf"
    rows = extract_pasted_text_statement(text, source_ref=ref)
    # Override source_type so the review table can show "PDF" for these.
    upgraded: list[BankStatementIntakeRow] = []
    for r in rows:
        upgraded.append(
            BankStatementIntakeRow(
                txn_date=r.txn_date,
                description_raw=r.description_raw,
                debit=r.debit,
                credit=r.credit,
                amount_signed=r.amount_signed,
                running_balance=r.running_balance,
                source_type=SOURCE_TYPE_PDF,
                source_ref=r.source_ref,
                confidence=r.confidence,
                needs_review=r.needs_review,
            )
        )
    return upgraded


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------


def normalized_field_names() -> tuple[str, ...]:
    """Stable field-name tuple in display order (used by the review table)."""
    return (
        "txn_date",
        "description_raw",
        "debit",
        "credit",
        "amount_signed",
        "running_balance",
        "source_type",
        "source_ref",
        "confidence",
        "needs_review",
    )
