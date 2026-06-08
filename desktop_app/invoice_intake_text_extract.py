"""Conservative pattern-based extraction for Invoice Intake pasted text (no AI/OCR).

Only labeled or unambiguous single-value lines qualify for **high** confidence.
Everything else is labeled *Needs review*, *Unclear*, or *Not extracted* in the review text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from desktop_app.flexible_date import format_ymd_as_us, parse_flexible_date_to_ymd

Confidence = Literal["none", "low", "high"]


def _clean_token(s: str) -> str:
    t = (s or "").strip()
    return t.rstrip(".,;:")


def _valid_ticket_ref(s: str) -> bool:
    t = _clean_token(s)
    if len(t) < 1 or len(t) > 64:
        return False
    if re.match(r"^\d+$", t):
        return 3 <= len(t) <= 16
    if re.match(r"^[\d\s.$,]+$", t):  # punctuation-heavy money line — skip
        return False
    return bool(re.search(r"[A-Za-z0-9]", t))


def _valid_customer_guess(s: str) -> bool:
    t = _clean_token(s)
    if len(t) < 2 or len(t) > 120:
        return False
    if not re.search(r"[A-Za-z]", t):
        return False
    if t.startswith("http://") or t.startswith("https://"):
        return False
    return True


@dataclass
class TextIntakeExtraction:
    """Structured guesses from pasted ticket/text; use :meth:`review_panel_text` for UI."""

    date_display: str | None = None
    """US ``MM/DD/YYYY`` when high confidence."""

    date_source: str | None = None
    """Raw substring that produced the date (for review)."""

    date_confidence: Confidence = "none"

    ticket_ref: str | None = None
    ticket_confidence: Confidence = "none"

    customer_name: str | None = None
    customer_confidence: Confidence = "none"

    hours_qty_note: str | None = None
    hours_qty_confidence: Confidence = "none"

    notes_from_label: str | None = None
    notes_confidence: Confidence = "none"

    def review_panel_text(self) -> str:
        """Multi-line summary for Invoice Intake review (extracted fields)."""
        lines: list[str] = [
            "Basic extraction (conservative). Uncertain items stay marked — verify before Save.",
            "",
        ]
        high: list[str] = []
        low: list[str] = []
        missing: list[str] = []

        if self.date_confidence == "high" and self.date_display:
            high.append(f"Date: {self.date_display}" + (f"  (from: {self.date_source})" if self.date_source else ""))
        elif self.date_confidence == "low":
            low.append(f"Date: unclear — {self.date_source or 'unparsed'}")
        else:
            missing.append("Date")

        if self.ticket_confidence == "high" and self.ticket_ref:
            high.append(f"Ticket / BOL / Ref: {self.ticket_ref}")
        elif self.ticket_confidence == "low":
            low.append(f"Ticket / BOL / Ref: needs review — {self.ticket_ref!r}")
        else:
            missing.append("Ticket / BOL / Reference")

        if self.customer_confidence == "high" and self.customer_name:
            high.append(f"Customer: {self.customer_name}")
        elif self.customer_confidence == "low" and self.customer_name:
            low.append(f"Customer: unclear — {self.customer_name!r} (verify)")
        else:
            missing.append("Customer name")

        if self.hours_qty_confidence == "high" and self.hours_qty_note:
            high.append(f"Hours / Qty: {self.hours_qty_note}")
        elif self.hours_qty_confidence == "low":
            low.append(f"Hours / Qty: needs review — {self.hours_qty_note!r}")
        else:
            missing.append("Hours / Qty")

        if self.notes_confidence == "high" and self.notes_from_label:
            high.append(f"Notes: {self.notes_from_label}")
        elif self.notes_confidence == "low" and self.notes_from_label:
            low.append(f"Notes: unclear — {self.notes_from_label[:200]!r}")
        else:
            missing.append("Labeled notes")

        lines.append("— Likely (high confidence) —")
        lines.extend(high if high else ["(none)"])
        lines.append("")
        lines.append("— Needs review / unclear —")
        lines.extend(low if low else ["(none)"])
        lines.append("")
        lines.append("— Not extracted —")
        lines.append(", ".join(missing) if missing else "(all categories attempted)")
        return "\n".join(lines)

    def memo_lines_for_handoff(self) -> list[str]:
        """Lines to append to invoice memo for high-confidence fields (non-form)."""
        out: list[str] = []
        if self.customer_confidence == "high" and self.customer_name:
            out.append(f"Customer (intake): {self.customer_name}")
        if self.hours_qty_confidence == "high" and self.hours_qty_note:
            out.append(f"Hours / Qty (intake): {self.hours_qty_note}")
        if self.notes_confidence == "high" and self.notes_from_label:
            out.append(f"Notes (intake): {self.notes_from_label}")
        return out


_RE_LABELED_DATE = re.compile(
    r"^\s*(?:Invoice\s+)?Date\s*[:#]\s*(.+?)\s*$",
    re.I,
)
_RE_SERVICE_DATE = re.compile(
    r"^\s*Service\s+Date\s*[:#]\s*(.+?)\s*$",
    re.I,
)
_RE_TICKET = re.compile(
    r"^\s*(?:Ticket|BOL)\s*#?\s*(.+?)\s*$",
    re.I,
)
_RE_REF = re.compile(
    r"^\s*(?:Reference|Ref\.?)\s*[:#]\s*(.+?)\s*$",
    re.I,
)
_RE_CUSTOMER = re.compile(
    r"^\s*(?:Customer|Client|Bill\s*To)\s*[:#]\s*(.+?)\s*$",
    re.I,
)
_RE_HOURS = re.compile(
    r"^\s*Hours?\s*[:#]\s*([\d.]+)\s*(?:hrs?|hours?)?\s*$",
    re.I,
)
_RE_QTY = re.compile(
    r"^\s*(?:Qty|Quantity)\s*[:#]\s*([\d.]+)\s*$",
    re.I,
)
_RE_NOTES_START = re.compile(
    r"^\s*(?:Notes?|Memo)\s*[:#]\s*(.*)\s*$",
    re.I,
)
_RE_LINE_ISO = re.compile(r"^\s*(\d{4}-\d{1,2}-\d{1,2})\s*$")
_RE_LINE_SOLO_DATE = re.compile(
    r"^\s*(\d{1,2}/\d{1,2}/\d{2,4})\s*$"
)


def _parse_date_high(raw: str) -> tuple[str | None, Confidence]:
    s = _clean_token(raw)
    if not s:
        return None, "none"
    ymd = parse_flexible_date_to_ymd(s)
    if ymd is None:
        return None, "low"
    y, m, d = ymd
    return format_ymd_as_us(m, d, y), "high"


def extract_text_intake_fields(text: str) -> TextIntakeExtraction:
    """Run a single conservative pass over pasted *text*."""
    raw = text or ""
    lines = raw.splitlines()
    ex = TextIntakeExtraction()

    # --- Date: labeled lines first ---
    for line in lines:
        for cre in (_RE_LABELED_DATE, _RE_SERVICE_DATE):
            m = cre.match(line)
            if m:
                disp, conf = _parse_date_high(m.group(1))
                if conf == "high" and disp:
                    ex.date_display = disp
                    ex.date_source = _clean_token(m.group(1))
                    ex.date_confidence = "high"
                else:
                    ex.date_confidence = "low"
                    ex.date_source = _clean_token(m.group(1))
                break
        if ex.date_confidence != "none":
            break

    if ex.date_confidence == "none" and len(lines) == 1:
        lone = lines[0].strip()
        m = _RE_LINE_ISO.match(lone)
        if m:
            disp, conf = _parse_date_high(m.group(1))
            if conf == "high" and disp:
                ex.date_display = disp
                ex.date_source = m.group(1)
                ex.date_confidence = "high"
        else:
            m2 = _RE_LINE_SOLO_DATE.match(lone)
            if m2:
                disp, conf = _parse_date_high(m2.group(1))
                if conf == "high" and disp:
                    ex.date_display = disp
                    ex.date_source = m2.group(1)
                    ex.date_confidence = "high"

    # --- Ticket / BOL / Ref (first strong match) ---
    for line in lines:
        for cre in (_RE_TICKET, _RE_REF):
            m = cre.match(line)
            if m:
                cand = _clean_token(m.group(1))
                if _valid_ticket_ref(cand):
                    ex.ticket_ref = cand
                    ex.ticket_confidence = "high"
                else:
                    ex.ticket_ref = cand
                    ex.ticket_confidence = "low"
                break
        if ex.ticket_confidence != "none":
            break

    # --- Customer ---
    for line in lines:
        m = _RE_CUSTOMER.match(line)
        if m:
            cand = _clean_token(m.group(1))
            if _valid_customer_guess(cand):
                ex.customer_name = cand
                ex.customer_confidence = "high"
            elif cand:
                ex.customer_name = cand
                ex.customer_confidence = "low"
            break

    # --- Hours / Qty (one field: prefer hours if both present) ---
    for line in lines:
        m = _RE_HOURS.match(line)
        if m:
            ex.hours_qty_note = f"{m.group(1)} hrs"
            ex.hours_qty_confidence = "high"
            break
    if ex.hours_qty_confidence == "none":
        for line in lines:
            m = _RE_QTY.match(line)
            if m:
                ex.hours_qty_note = f"Qty {m.group(1)}"
                ex.hours_qty_confidence = "high"
                break

    # --- Notes / Memo: labeled block (until blank line) ---
    in_notes = False
    note_parts: list[str] = []
    for line in lines:
        m = _RE_NOTES_START.match(line)
        if m is not None:
            in_notes = True
            first = (m.group(1) or "").strip()
            if first:
                note_parts.append(first)
            continue
        if in_notes:
            if not line.strip():
                break
            note_parts.append(line.rstrip())
    if note_parts:
        joined = "\n".join(note_parts).strip()
        if len(joined) > 2000:
            joined = joined[:2000] + "\n… (truncated)"
        ex.notes_from_label = joined
        ex.notes_confidence = "high" if len(joined) >= 1 else "none"

    return ex
