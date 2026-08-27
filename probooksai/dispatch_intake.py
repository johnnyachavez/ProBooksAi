"""Dispatch sheet intake — CSV v1 for Invoice Intake → Create Invoices / Enter Bills.

Parses the Chavan dispatch loads table (headers: DATE, INVOICE, DISPATCH, DRIVER,
INVOICE RATE, PAY RATE, PO / LOAD#, BOL#, QB Inv No.) into staged rows, then groups
invoice-ready loads and pay-ready loads for the desktop forms.

v1 is **offline CSV**. Live Google Sheet pull is stubbed (no API token in-repo).
Tax IDs, SSNs, EINs, DIR numbers, and bank account numbers are never imported.
"""

from __future__ import annotations

import csv
import io
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Sequence, TextIO, Union

from probooksai.bank_import import parse_amount, parse_date, strip_csv_cell_paste_noise

# Display name of Johnny's live workbook (CSV export). Not an API credential.
GOOGLE_DISPATCH_SHEET_TITLE = "1 CHAVAN DISPATCH"

# Env var a future live pull may read; never commit a value. v1 ignores any token.
GOOGLE_DISPATCH_TOKEN_ENV = "PROBOOKS_GOOGLE_SHEETS_TOKEN"

SOURCE_TYPE_CSV = "csv"
SOURCE_TYPE_GOOGLE_STUB = "google_stub"

PathOrText = Union[str, Path, TextIO]

# Canonical loads-table headers (normalized). Extra columns are ignored or skipped.
LOAD_FIELD_ALIASES: dict[str, str] = {
    "date": "date",
    "invoice": "invoice_code",
    "dispatch": "dispatch",
    "driver": "driver",
    "invoice rate": "invoice_rate",
    "pay rate": "pay_rate",
    "po load": "po_load",
    "po": "po_load",
    "load": "po_load",
    "bol": "bol",
    "qb inv no": "qb_inv_no",
    "qb inv": "qb_inv_no",
    "qb invoice": "qb_inv_no",
    "qb invoice no": "qb_inv_no",
}

# Lookup-table allowlist (job billing rules / trucker pay). Never tax or bank fields.
LOOKUP_FIELD_ALIASES: dict[str, str] = {
    "job": "job_code",
    "job code": "job_code",
    "invoice": "job_code",
    "customer": "customer_name",
    "customer name": "customer_name",
    "name": "name",
    "trucker": "name",
    "vendor": "name",
    "driver": "name",
    "email": "email",
    "pay email": "email",
    "ap email": "email",
    "how to bill": "how_to_bill",
    "billing": "how_to_bill",
    "billing notes": "how_to_bill",
}

# Sample job → customer billing hints (fictional). Not copied from live sheet PII.
SAMPLE_JOB_BILLING_RULES: tuple[dict[str, str], ...] = (
    {
        "job_code": "3235",
        "customer_name": "Sample Materials Co",
        "how_to_bill": "Invoice off the ticket to the customer AP email.",
    },
    {
        "job_code": "BST",
        "customer_name": "BST Sample Logistics",
        "how_to_bill": "Invoice each load with their BOL.",
    },
    {
        "job_code": "T1",
        "customer_name": "Sample Plant T1",
        "how_to_bill": "Invoice each load.",
    },
)

# Sample trucker pay names/emails only (no tax ID / DIR / SSN).
SAMPLE_TRUCKER_PAY: tuple[dict[str, str], ...] = (
    {"name": "Sample Hauling LLC", "email": "ap@example.invalid"},
    {"name": "JC", "email": ""},
)

_X_QTY_RATE = re.compile(
    r"^\s*\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*[xX×]\s*"
    r"(\d+(?:\.\d+)?)\s*$"
)
_MISSING_RATE = re.compile(r"^(?:n/?a|none|null|-|—|–|\.)?$", re.IGNORECASE)

# Header fragments that must never be stored from a dispatch CSV.
_SENSITIVE_HEADER_NEEDLES = (
    "ssn",
    "social security",
    "tax id",
    "taxid",
    "ein",
    "fein",
    "itin",
    "tin",
    "dir no",
    "dir number",
    "dir #",
    "bank account",
    "account number",
    "routing",
    "aba ",
    "iban",
    "swift",
    "federal id",
    "employer id",
    "employer identification",
)


class DispatchGoogleNotConfigured(RuntimeError):
    """Live Google Sheet pull is not configured; CSV import is the v1 path."""


@dataclass
class DispatchLoadRow:
    """One dispatch loads-table row after CSV parse (no sensitive columns)."""

    source_row: int
    date_iso: str = ""
    date_raw: str = ""
    invoice_code: str = ""
    dispatch: str = ""
    driver: str = ""
    invoice_rate: Optional[float] = None
    invoice_qty: float = 1.0
    invoice_rate_raw: str = ""
    invoice_rate_missing: bool = True
    pay_rate: Optional[float] = None
    pay_rate_raw: str = ""
    pay_rate_missing: bool = True
    po_load: str = ""
    bol: str = ""
    qb_inv_no: str = ""
    source_ref: str = ""

    def invoice_amount(self) -> Optional[float]:
        if self.invoice_rate_missing or self.invoice_rate is None:
            return None
        return round(float(self.invoice_rate) * float(self.invoice_qty or 0.0), 2)

    def source_label(self) -> str:
        job = (self.invoice_code or "").strip() or "—"
        day = (self.date_iso or self.date_raw or "").strip() or "—"
        bol = (self.bol or "").strip()
        if bol:
            return f"{job} · {day} · BOL {bol}"
        return f"{job} · {day}"

    def review_text(self) -> str:
        rate_s = "—"
        if not self.invoice_rate_missing and self.invoice_rate is not None:
            amt = self.invoice_amount()
            rate_s = (
                f"{self.invoice_rate:.2f} × {self.invoice_qty:g} = {amt:.2f}"
                if amt is not None
                else f"{self.invoice_rate:.2f}"
            )
        pay_s = "—"
        if not self.pay_rate_missing and self.pay_rate is not None:
            pay_s = f"{self.pay_rate:.2f}"
        lines = [
            "Dispatch load (CSV)",
            f"Date: {self.date_iso or self.date_raw or '—'}",
            f"INVOICE (customer/job): {self.invoice_code or '—'}",
            f"DISPATCH: {self.dispatch or '—'}",
            f"DRIVER: {self.driver or '—'}",
            f"INVOICE RATE: {rate_s}",
            f"PAY RATE: {pay_s}",
            f"PO / LOAD#: {self.po_load or '—'}",
            f"BOL#: {self.bol or '—'}",
            f"QB Inv No.: {self.qb_inv_no or '—'}",
        ]
        return "\n".join(lines)

    def queue_status(self) -> str:
        bits: list[str] = []
        if self.invoice_rate_missing:
            bits.append("needs rate")
        if self.pay_rate_missing:
            bits.append("needs pay")
        return " / ".join(bits) if bits else "Staged"

    def notes_summary(self) -> str:
        parts: list[str] = []
        if self.dispatch:
            parts.append(self.dispatch)
        if self.driver:
            parts.append(f"Driver: {self.driver}")
        if self.po_load:
            parts.append(f"PO {self.po_load}")
        return " · ".join(parts)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class DispatchInvoiceLine:
    date_iso: str
    description: str
    bol: str
    rate: float
    qty: float
    amount: float
    source_row: int
    po_load: str = ""


@dataclass
class DispatchInvoiceDraft:
    """Grouped Create Invoices draft (one invoice, many load lines)."""

    group_key: tuple
    invoice_code: str
    date_iso: str
    qb_inv_no: str
    po_load: str
    lines: list[DispatchInvoiceLine]
    source_rows: list[int] = field(default_factory=list)

    def billing_rule(self) -> Optional[dict[str, str]]:
        return job_billing_rule(self.invoice_code)


@dataclass
class DispatchBillLine:
    date_iso: str
    ticket_ref: str
    amount: float
    memo: str
    customer_job: str
    source_row: int


@dataclass
class DispatchBillDraft:
    """Enter Bills draft from driver + pay rate (amount 0 allowed for owner-operator JC)."""

    group_key: tuple
    vendor_name: str
    date_iso: str
    lines: list[DispatchBillLine]
    source_rows: list[int] = field(default_factory=list)
    header_memo: str = ""


@dataclass
class DispatchImportResult:
    rows: list[DispatchLoadRow]
    skipped_sensitive_headers: tuple[str, ...] = ()
    ignored_headers: tuple[str, ...] = ()
    source_ref: str = ""
    source_type: str = SOURCE_TYPE_CSV


def normalize_dispatch_header(raw: str) -> str:
    s = strip_csv_cell_paste_noise(raw).replace("\u00a0", " ").lower()
    s = s.replace("#", " ")
    s = re.sub(r"[._/\\]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def is_sensitive_dispatch_header(raw: str) -> bool:
    """True for tax ID / SSN / EIN / DIR / bank-number columns — never import these."""
    n = normalize_dispatch_header(raw)
    if not n:
        return False
    compact = n.replace(" ", "")
    if n in {"ssn", "ein", "fein", "itin", "tin", "dir"} or compact in {
        "ssn",
        "ein",
        "fein",
        "itin",
        "taxid",
        "dir",
    }:
        return True
    padded = f" {n} "
    if " dir " in padded and n != "dispatch":
        return True
    for needle in _SENSITIVE_HEADER_NEEDLES:
        if needle in n or needle.replace(" ", "") in compact:
            return True
    return False


def parse_qty_rate_cell(raw: str) -> tuple[Optional[float], float, bool]:
    """Parse INVOICE RATE. ``160X7`` → rate 160, qty 7. Blank is missing (not zero).

    Returns ``(rate, qty, missing)``. *missing* is True when the cell is empty / N/A.
    A literal ``0`` is present (owner-operator / $0 rate) and *missing* is False.
    """
    s = strip_csv_cell_paste_noise(raw)
    if not s or _MISSING_RATE.match(s):
        return None, 1.0, True
    m = _X_QTY_RATE.match(s)
    if m:
        rate = float(m.group(1).replace(",", ""))
        qty = float(m.group(2))
        return rate, qty, False
    amt = parse_amount(s)
    if amt is None:
        return None, 1.0, True
    return float(amt), 1.0, False


def parse_pay_rate_cell(raw: str) -> tuple[Optional[float], bool]:
    """Parse PAY RATE as a bill amount. Blank is missing; ``0`` is allowed.

    ``160X7`` becomes ``160 * 7`` (same split as invoice rate, stored as one amount).
    """
    rate, qty, missing = parse_qty_rate_cell(raw)
    if missing or rate is None:
        return None, True
    return round(float(rate) * float(qty or 0.0), 2), False


def parse_dispatch_date(raw: str) -> Optional[str]:
    s = strip_csv_cell_paste_noise(raw)
    if not s:
        return None
    iso = parse_date(s)
    if iso:
        return iso
    if " " in s or "T" in s:
        head = re.split(r"[ T]", s, maxsplit=1)[0]
        return parse_date(head)
    return None


def match_named_entity_id(
    choices: Sequence[tuple[int, str]],
    needle: str,
) -> Optional[int]:
    """Match a customer/vendor combo id by name, job code, or ``Parent > Job`` label."""
    want = (needle or "").strip().lower()
    if not want:
        return None
    exact: list[int] = []
    partial: list[int] = []
    for eid, label in choices:
        lab = (label or "").strip()
        low = lab.lower()
        parts = [p.strip().lower() for p in re.split(r"\s*[>:,]\s*", lab) if p.strip()]
        if low == want or want in parts:
            exact.append(int(eid))
        elif want in low:
            partial.append(int(eid))
    if len(exact) == 1:
        return exact[0]
    if not exact and len(partial) == 1:
        return partial[0]
    return exact[0] if exact else None


def job_billing_rule(job_code: str) -> Optional[dict[str, str]]:
    code = (job_code or "").strip().lower()
    if not code:
        return None
    for row in SAMPLE_JOB_BILLING_RULES:
        if (row.get("job_code") or "").strip().lower() == code:
            return dict(row)
    return None


def invoice_group_key(row: DispatchLoadRow) -> Optional[tuple]:
    """Same QB Inv No. if present; else same INVOICE customer/job + DATE."""
    qb = (row.qb_inv_no or "").strip()
    if qb:
        return ("qb", qb.lower())
    code = (row.invoice_code or "").strip()
    if code and row.date_iso:
        return ("job_date", code.lower(), row.date_iso)
    return None


def bill_group_key(row: DispatchLoadRow) -> Optional[tuple]:
    driver = (row.driver or "").strip()
    if driver and row.date_iso:
        return ("driver_date", driver.lower(), row.date_iso)
    if driver:
        return ("driver", driver.lower())
    return None


def _map_load_headers(fieldnames: Sequence[str]) -> tuple[dict[int, str], list[str], list[str]]:
    """Return ``(index → field, skipped_sensitive, ignored)``."""
    index_to_field: dict[int, str] = {}
    skipped: list[str] = []
    ignored: list[str] = []
    used_fields: set[str] = set()
    for i, raw in enumerate(fieldnames):
        label = (raw or "").strip()
        if not label:
            continue
        if is_sensitive_dispatch_header(label):
            skipped.append(label)
            continue
        n = normalize_dispatch_header(label)
        field = LOAD_FIELD_ALIASES.get(n)
        if field is None:
            ignored.append(label)
            continue
        if field in used_fields:
            ignored.append(label)
            continue
        used_fields.add(field)
        index_to_field[i] = field
    return index_to_field, skipped, ignored


def _cell(row: Sequence[str], idx: int) -> str:
    if idx < 0 or idx >= len(row):
        return ""
    return strip_csv_cell_paste_noise(row[idx])


def parse_dispatch_csv(
    source: PathOrText,
    *,
    source_ref: str = "",
) -> DispatchImportResult:
    """Parse a dispatch loads CSV. Sensitive columns are dropped, not stored."""
    close = False
    name = source_ref
    if isinstance(source, (str, Path)):
        path = Path(source)
        fh: TextIO = path.open("r", encoding="utf-8-sig", newline="")
        close = True
        name = name or path.name
    else:
        fh = source
        name = name or getattr(source, "name", "") or "csv"

    try:
        sample = fh.read(4096)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(fh, dialect)
        try:
            header_row = next(reader)
        except StopIteration:
            return DispatchImportResult(rows=[], source_ref=name)
        index_to_field, skipped, ignored = _map_load_headers(header_row)
        rows: list[DispatchLoadRow] = []
        for data_i, cells in enumerate(reader, start=2):
            if not any(strip_csv_cell_paste_noise(c) for c in cells):
                continue
            values: dict[str, str] = {}
            for idx, field in index_to_field.items():
                values[field] = _cell(cells, idx)
            date_raw = values.get("date") or ""
            rate_raw = values.get("invoice_rate") or ""
            pay_raw = values.get("pay_rate") or ""
            inv_rate, inv_qty, inv_missing = parse_qty_rate_cell(rate_raw)
            pay_amt, pay_missing = parse_pay_rate_cell(pay_raw)
            rows.append(
                DispatchLoadRow(
                    source_row=data_i,
                    date_iso=parse_dispatch_date(date_raw) or "",
                    date_raw=date_raw,
                    invoice_code=values.get("invoice_code") or "",
                    dispatch=values.get("dispatch") or "",
                    driver=values.get("driver") or "",
                    invoice_rate=inv_rate,
                    invoice_qty=inv_qty,
                    invoice_rate_raw=rate_raw,
                    invoice_rate_missing=inv_missing,
                    pay_rate=pay_amt,
                    pay_rate_raw=pay_raw,
                    pay_rate_missing=pay_missing,
                    po_load=values.get("po_load") or "",
                    bol=values.get("bol") or "",
                    qb_inv_no=values.get("qb_inv_no") or "",
                    source_ref=name,
                )
            )
        return DispatchImportResult(
            rows=rows,
            skipped_sensitive_headers=tuple(skipped),
            ignored_headers=tuple(ignored),
            source_ref=name,
            source_type=SOURCE_TYPE_CSV,
        )
    finally:
        if close:
            fh.close()


def parse_dispatch_csv_text(text: str, *, source_ref: str = "pasted.csv") -> DispatchImportResult:
    return parse_dispatch_csv(io.StringIO(text), source_ref=source_ref)


def _invoice_draft_from_rows(key: tuple, group: list[DispatchLoadRow]) -> DispatchInvoiceDraft:
    first = group[0]
    pos = []
    for r in group:
        p = (r.po_load or "").strip()
        if p and p not in pos:
            pos.append(p)
    lines: list[DispatchInvoiceLine] = []
    for r in group:
        rate = float(r.invoice_rate or 0.0)
        qty = float(r.invoice_qty or 1.0)
        lines.append(
            DispatchInvoiceLine(
                date_iso=r.date_iso,
                description=(r.dispatch or "").strip(),
                bol=(r.bol or "").strip(),
                rate=rate,
                qty=qty,
                amount=round(rate * qty, 2),
                source_row=r.source_row,
                po_load=(r.po_load or "").strip(),
            )
        )
    qb = ""
    for r in group:
        if (r.qb_inv_no or "").strip():
            qb = r.qb_inv_no.strip()
            break
    return DispatchInvoiceDraft(
        group_key=key,
        invoice_code=(first.invoice_code or "").strip(),
        date_iso=first.date_iso,
        qb_inv_no=qb,
        po_load=pos[0] if pos else "",
        lines=lines,
        source_rows=[r.source_row for r in group],
    )


def group_invoice_drafts(
    rows: Iterable[DispatchLoadRow],
) -> tuple[list[DispatchInvoiceDraft], list[DispatchLoadRow]]:
    """Group invoice-ready rows; skip blank INVOICE RATE (needs rate)."""
    skipped: list[DispatchLoadRow] = []
    buckets: dict[tuple, list[DispatchLoadRow]] = {}
    order: list[tuple] = []
    for row in rows:
        if row.invoice_rate_missing or row.invoice_rate is None:
            skipped.append(row)
            continue
        key = invoice_group_key(row)
        if key is None:
            skipped.append(row)
            continue
        if key not in buckets:
            order.append(key)
            buckets[key] = []
        buckets[key].append(row)
    drafts = [_invoice_draft_from_rows(k, buckets[k]) for k in order]
    return drafts, skipped


def _bill_memo(row: DispatchLoadRow) -> str:
    bits: list[str] = []
    if (row.dispatch or "").strip():
        bits.append(row.dispatch.strip())
    if (row.bol or "").strip():
        bits.append(f"BOL {row.bol.strip()}")
    return " · ".join(bits)


def _bill_draft_from_rows(key: tuple, group: list[DispatchLoadRow]) -> DispatchBillDraft:
    first = group[0]
    lines: list[DispatchBillLine] = []
    for r in group:
        amt = float(r.pay_rate or 0.0)
        lines.append(
            DispatchBillLine(
                date_iso=r.date_iso,
                ticket_ref=(r.bol or "").strip(),
                amount=amt,
                memo=_bill_memo(r),
                customer_job=(r.invoice_code or "").strip(),
                source_row=r.source_row,
            )
        )
    vendor = (first.driver or "").strip()
    header = f"Dispatch pay · {first.date_iso or first.date_raw} · {vendor}".strip(" ·")
    return DispatchBillDraft(
        group_key=key,
        vendor_name=vendor,
        date_iso=first.date_iso,
        lines=lines,
        source_rows=[r.source_row for r in group],
        header_memo=header,
    )


def group_bill_drafts(
    rows: Iterable[DispatchLoadRow],
) -> tuple[list[DispatchBillDraft], list[DispatchLoadRow]]:
    """Group pay-ready rows by DRIVER + DATE. Blank PAY RATE is skipped (needs pay).

    ``PAY RATE`` of ``0`` is included (owner-operator JC).
    """
    skipped: list[DispatchLoadRow] = []
    buckets: dict[tuple, list[DispatchLoadRow]] = {}
    order: list[tuple] = []
    for row in rows:
        if row.pay_rate_missing or row.pay_rate is None:
            skipped.append(row)
            continue
        key = bill_group_key(row)
        if key is None:
            skipped.append(row)
            continue
        if key not in buckets:
            order.append(key)
            buckets[key] = []
        buckets[key].append(row)
    drafts = [_bill_draft_from_rows(k, buckets[k]) for k in order]
    return drafts, skipped


def drafts_for_invoice_row(
    rows: Sequence[DispatchLoadRow],
    target: DispatchLoadRow,
) -> Optional[DispatchInvoiceDraft]:
    """Invoice draft containing *target* if that load has a rate and a group key."""
    if target.invoice_rate_missing or target.invoice_rate is None:
        return None
    key = invoice_group_key(target)
    if key is None:
        return None
    members = [
        r
        for r in rows
        if not r.invoice_rate_missing
        and r.invoice_rate is not None
        and invoice_group_key(r) == key
    ]
    if not members:
        return None
    return _invoice_draft_from_rows(key, members)


def drafts_for_bill_row(
    rows: Sequence[DispatchLoadRow],
    target: DispatchLoadRow,
) -> Optional[DispatchBillDraft]:
    if target.pay_rate_missing or target.pay_rate is None:
        return None
    key = bill_group_key(target)
    if key is None:
        return None
    members = [
        r
        for r in rows
        if not r.pay_rate_missing
        and r.pay_rate is not None
        and bill_group_key(r) == key
    ]
    if not members:
        return None
    return _bill_draft_from_rows(key, members)


def row_from_payload(data: dict) -> DispatchLoadRow:
    known = {f.name for f in DispatchLoadRow.__dataclass_fields__.values()}
    kwargs = {k: v for k, v in data.items() if k in known}
    return DispatchLoadRow(**kwargs)


def fetch_google_dispatch_rows(
    *,
    api_token: Optional[str] = None,
    credentials: Optional[str] = None,
) -> DispatchImportResult:
    """Stub for a later live Google pull. v1 never calls the Sheets API.

    Does not persist *api_token* / *credentials*. A present env token still does
    not enable a live pull in this version.
    """
    _ = api_token or credentials or os.environ.get(GOOGLE_DISPATCH_TOKEN_ENV)
    raise DispatchGoogleNotConfigured(
        f"Live Google pull is not configured in v1. Export {GOOGLE_DISPATCH_SHEET_TITLE!r} "
        "as CSV (File → Download) and use Import dispatch CSV on Invoice Intake. "
        "Do not paste API tokens into the app."
    )


def parse_lookup_csv(source: PathOrText) -> tuple[list[dict[str, str]], tuple[str, ...]]:
    """Parse a job-rules or trucker-pay CSV, dropping tax-id / bank columns."""
    close = False
    if isinstance(source, (str, Path)):
        fh: TextIO = Path(source).open("r", encoding="utf-8-sig", newline="")
        close = True
    else:
        fh = source
    try:
        reader = csv.reader(fh)
        try:
            header_row = next(reader)
        except StopIteration:
            return [], ()
        skipped: list[str] = []
        index_to_field: dict[int, str] = {}
        used: set[str] = set()
        for i, raw in enumerate(header_row):
            label = (raw or "").strip()
            if not label:
                continue
            if is_sensitive_dispatch_header(label):
                skipped.append(label)
                continue
            n = normalize_dispatch_header(label)
            field = LOOKUP_FIELD_ALIASES.get(n)
            if field is None or field in used:
                continue
            used.add(field)
            index_to_field[i] = field
        out: list[dict[str, str]] = []
        for cells in reader:
            if not any(strip_csv_cell_paste_noise(c) for c in cells):
                continue
            rec = {field: _cell(cells, idx) for idx, field in index_to_field.items()}
            if any(rec.values()):
                out.append(rec)
        return out, tuple(skipped)
    finally:
        if close:
            fh.close()
