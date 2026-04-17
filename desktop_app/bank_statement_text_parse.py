"""Parse messy pasted bank statement text into normalized review rows (staging only; no DB writes).

Heuristics favor recall over precision: unclear lines are marked **Needs Review** rather than
inventing amounts or dates. Intended for the **Reconcile → Bank statements** intake path
alongside unchanged CSV/PDF import.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ParsedStatementRow:
    """One staged review row for the raw-text paste grid."""

    date_iso: str
    date_display: str
    description: str
    amount: Optional[float]
    type_status: str
    notes: str


_RE_LINE_SPLIT = re.compile(r"[\r\n]+")
_RE_DATE_LEAD = re.compile(
    r"^\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b"
)
_RE_DATE_ANY = re.compile(
    r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b"
)
_RE_SKIP_LINE = re.compile(r"^[\s\-_=.*#|]+$")
_RE_HEADERISH = re.compile(
    r"^(date|posted|trans|description|memo|amount|balance|withdrawal|deposit|debit|credit)\b",
    re.IGNORECASE,
)
# Money with cents (avoid matching dates: require .XX)
_RE_MONEY_PLAIN = re.compile(
    r"(?<![\d.])(-\s*)?\$?\s*([\d]{1,3}(?:,\d{3})*\.\d{2}|\d+\.\d{2})\s*(?:CR|DR)?(?![\d.])",
    re.IGNORECASE,
)
_RE_PAREN_MONEY = re.compile(r"\(\s*\$?\s*([\d,]+\.\d{2})\s*\)")


def _expand_two_digit_year(y: int) -> int:
    if y < 0 or y > 99:
        return y
    return 2000 + y if y <= 69 else 1900 + y


def _parse_date_token(tok: str) -> Optional[tuple[int, int, int]]:
    t = tok.strip()
    if not t:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t):
        y, m, d = int(t[0:4]), int(t[5:7]), int(t[8:10])
        if 1 <= m <= 12 and 1 <= d <= 31:
            return y, m, d
        return None
    m2 = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", t)
    if not m2:
        return None
    mm, dd, yy = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
    if yy < 100:
        yy = _expand_two_digit_year(yy)
    if 1 <= mm <= 12 and 1 <= dd <= 31:
        return yy, mm, dd
    return None


def _date_to_iso(tok: str) -> tuple[str, str]:
    p = _parse_date_token(tok)
    if p is None:
        return "", tok.strip()
    y, m, d = p
    iso = f"{y:04d}-{m:02d}-{d:02d}"
    disp = f"{m:02d}/{d:02d}/{y:04d}"
    return iso, disp


def _parse_money(s: str) -> Optional[float]:
    s = s.strip().replace(",", "")
    if not s:
        return None
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def _extract_amounts(line: str) -> list[tuple[float, str]]:
    """Extract signed amounts and the exact fragments matched (for description stripping)."""
    frags: list[tuple[float, str]] = []
    s = line
    # Parentheses → negative (bank convention); remove so plain regex does not double-match
    for m in list(_RE_PAREN_MONEY.finditer(line)):
        v = _parse_money(m.group(1))
        if v is not None:
            frags.append((-abs(v), m.group(0)))
            s = s.replace(m.group(0), " ", 1)
    for m in _RE_MONEY_PLAIN.finditer(s):
        neg = m.group(1)
        num = m.group(2)
        raw = m.group(0).strip().upper()
        v = _parse_money(num)
        if v is None:
            continue
        if neg:
            v = -abs(v)
        elif raw.endswith("DR"):
            v = -abs(v)
        elif raw.endswith("CR"):
            v = abs(v)
        frags.append((v, m.group(0)))
    return frags


def _pick_amount(amounts: list[tuple[float, str]]) -> tuple[Optional[float], str]:
    if not amounts:
        return None, ""
    if len(amounts) == 1:
        return amounts[0][0], ""
    nz = [a for a in amounts if abs(a[0]) > 1e-9]
    if len(nz) == 1:
        return nz[0][0], "Multiple amounts; used the only non-zero."
    if len(nz) > 1:
        nz.sort(key=lambda x: abs(x[0]), reverse=True)
        return nz[0][0], "Multiple amounts; used largest magnitude."
    return amounts[-1][0], "Multiple zero amounts; used last."


def _strip_for_description(line: str, date_tok: str) -> str:
    s = line
    if date_tok:
        s = s.replace(date_tok, " ", 1)
    s = _RE_PAREN_MONEY.sub(" ", s)
    s = _RE_MONEY_PLAIN.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_statement_line(line: str) -> Optional[ParsedStatementRow]:
    """Parse a single non-empty line; return ``None`` to skip (blank / decorative)."""
    raw = line.strip()
    if not raw:
        return None
    if _RE_SKIP_LINE.match(raw):
        return None
    if _RE_HEADERISH.match(raw) and not _RE_MONEY_PLAIN.search(raw) and not _RE_PAREN_MONEY.search(
        raw
    ):
        return ParsedStatementRow(
            date_iso="",
            date_display="",
            description=raw[:500],
            amount=None,
            type_status="Needs Review",
            notes="Possible header row — verify.",
        )

    date_iso, date_disp = "", ""
    date_tok = ""
    m_lead = _RE_DATE_LEAD.match(raw)
    if m_lead:
        date_tok = m_lead.group(1)
        date_iso, date_disp = _date_to_iso(date_tok)
    else:
        m_any = _RE_DATE_ANY.search(raw)
        if m_any:
            date_tok = m_any.group(1)
            date_iso, date_disp = _date_to_iso(date_tok)

    am_entries = _extract_amounts(raw)
    amount, amt_note = _pick_amount(am_entries)

    desc = _strip_for_description(raw, date_tok)
    if not desc:
        desc = raw

    notes_parts: list[str] = []
    if amt_note:
        notes_parts.append(amt_note)

    if amount is None:
        return ParsedStatementRow(
            date_iso=date_iso,
            date_display=date_disp if date_iso else "—",
            description=desc[:2000] if desc else raw[:2000],
            amount=None,
            type_status="Needs Review",
            notes="; ".join(notes_parts + ["No amount detected."])
            if notes_parts
            else "No amount detected.",
        )

    if not date_iso:
        notes_parts.append("Date unclear or missing.")

    if abs(amount) < 1e-9:
        return ParsedStatementRow(
            date_iso=date_iso,
            date_display=date_disp if date_iso else "—",
            description=desc[:2000],
            amount=amount,
            type_status="Needs Review",
            notes="; ".join(notes_parts + ["Zero amount."]),
        )

    dc = "Credit" if amount > 0 else "Debit"
    if not date_iso:
        return ParsedStatementRow(
            date_iso="",
            date_display="—",
            description=desc[:2000],
            amount=amount,
            type_status="Needs Review",
            notes="; ".join(notes_parts) if notes_parts else "Date unclear or missing.",
        )

    note_final = "; ".join(notes_parts) if notes_parts else ""
    return ParsedStatementRow(
        date_iso=date_iso,
        date_display=date_disp,
        description=desc[:2000],
        amount=amount,
        type_status=f"{dc} / OK",
        notes=note_final or "—",
    )


def parse_bank_statement_text(text: str) -> list[ParsedStatementRow]:
    """Split pasted text into lines and return parsed rows (skips empty / decorative lines)."""
    lines = _RE_LINE_SPLIT.split(text or "")
    out: list[ParsedStatementRow] = []
    for line in lines:
        pr = parse_statement_line(line)
        if pr is not None:
            out.append(pr)
    return out


def format_amount_cell(amount: Optional[float]) -> str:
    if amount is None:
        return "—"
    return f"${amount:,.2f}"
