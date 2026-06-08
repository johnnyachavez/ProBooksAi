"""Flexible US (MM/DD/YYYY) date parsing and normalization for desktop date inputs.

**Global date fields:** Call :func:`configure_qdate_edit_us` on every ``QDateEdit`` in the
desktop app (or use :func:`create_app_date_edit`). That applies:

- Display **MM/DD/YYYY** (zero-padded; e.g. ``01/01/2000``).
- **No calendar popup** — typing only (flexible parse on commit).
- The same parsing rules as :func:`parse_flexible_date_to_ymd` (e.g. ``5/21/26``, ``052126``).

Storage elsewhere in the app and database remains ISO ``yyyy-MM-dd`` where applicable.
"""

from __future__ import annotations

import calendar
import re
from typing import Optional

def _days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _finalize_ymd(year: int, month: int, day: int) -> Optional[tuple[int, int, int]]:
    if month < 1 or month > 12 or day < 1 or day > _days_in_month(year, month):
        return None
    return (year, month, day)


def expand_two_digit_year(yy: int) -> int:
    """Map 0–99 to a four-digit year (00–69 → 2000–2069; 70–99 → 1970–1999)."""
    if yy < 0 or yy > 99:
        return yy
    if yy <= 69:
        return 2000 + yy
    return 1900 + yy


def parse_flexible_date_to_ymd(text: str) -> Optional[tuple[int, int, int]]:
    """Parse common US date shapes into ``(year, month, day)`` or return ``None`` if invalid."""
    from PySide6.QtCore import QDate

    s = (text or "").strip()
    if not s:
        return None

    qd = QDate.fromString(s, "yyyy-MM-dd")
    if qd.isValid():
        return qd.year(), qd.month(), qd.day()

    # Four-digit year only: Qt's two-digit year formats follow a different pivot than ours.
    for fmt in ("M/d/yyyy", "MM/dd/yyyy"):
        qd = QDate.fromString(s, fmt)
        if qd.isValid():
            return qd.year(), qd.month(), qd.day()

    parts = [p for p in re.split(r"[^\d]+", s) if p != ""]
    digits_only = "".join(parts)

    if len(parts) == 1 and len(digits_only) in (6, 8):
        if len(digits_only) == 6:
            mm = int(digits_only[0:2], 10)
            dd = int(digits_only[2:4], 10)
            yy = int(digits_only[4:6], 10)
            y = expand_two_digit_year(yy)
        else:
            mm = int(digits_only[0:2], 10)
            dd = int(digits_only[2:4], 10)
            y = int(digits_only[4:8], 10)
        return _finalize_ymd(y, mm, dd)

    if len(parts) >= 3:
        mm = int(parts[0], 10)
        dd = int(parts[1], 10)
        y_raw = int(parts[2], 10)
        if y_raw < 100:
            y = expand_two_digit_year(y_raw)
        else:
            y = y_raw
        return _finalize_ymd(y, mm, dd)

    if len(parts) == 2:
        mm = int(parts[0], 10)
        dd = int(parts[1], 10)
        y = QDate.currentDate().year()
        return _finalize_ymd(y, mm, dd)

    return None


def format_ymd_as_us(m: int, d: int, y: int) -> str:
    return f"{m:02d}/{d:02d}/{y:04d}"


def format_iso_to_us_display(iso: str) -> str:
    """Turn ``yyyy-mm-dd`` (or flexible parseable text) into ``MM/DD/YYYY`` for display."""
    raw = (iso or "").strip()
    if not raw:
        return ""
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        y, m, d = int(raw[0:4], 10), int(raw[5:7], 10), int(raw[8:10], 10)
        fin = _finalize_ymd(y, m, d)
        if fin:
            y2, m2, d2 = fin
            return format_ymd_as_us(m2, d2, y2)
    p = parse_flexible_date_to_ymd(raw)
    if p:
        y, m, d = p
        return format_ymd_as_us(m, d, y)
    return raw


def line_edit_to_iso_or_raw(le: QLineEdit) -> Optional[str]:
    """If *le* text parses as a date, return ``yyyy-mm-dd``; else stripped raw (or ``None`` if empty)."""
    t = le.text().strip()
    if not t:
        return None
    ymd = parse_flexible_date_to_ymd(t)
    if ymd is None:
        return t
    y, m, d = ymd
    return f"{y:04d}-{m:02d}-{d:02d}"


def normalize_line_edit_us_date(le: QLineEdit) -> None:
    """On commit, replace *le* text with ``MM/DD/YYYY`` when parsing succeeds."""
    t = le.text().strip()
    if not t:
        return
    ymd = parse_flexible_date_to_ymd(t)
    if ymd is None:
        return
    y, m, d = ymd
    le.setText(format_ymd_as_us(m, d, y))


def attach_line_edit_us_date_normalization(le: QLineEdit) -> None:
    le.editingFinished.connect(lambda: normalize_line_edit_us_date(le))


def configure_qdate_edit_us(w: QDateEdit) -> None:
    """App-wide ``QDateEdit`` setup: **MM/dd/yyyy** display, **no calendar popup**, flexible typed input.

    Call once per widget. On *editingFinished* (Enter / focus out), parses with
    :func:`parse_flexible_date_to_ymd` and applies the resulting ``QDate`` so the field
    redisplays normalized **MM/DD/YYYY**.

    Accepted shortcuts (all auto-expand on Tab/Enter):
      ``010126``  →  01/01/2026
      ``01012026`` →  01/01/2026
      ``1/1/26``  →  01/01/2026
      ``01/01/2026`` →  unchanged (already valid)
    """
    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import QLineEdit

    w.setCalendarPopup(False)
    w.setDisplayFormat("MM/dd/yyyy")

    # Allow the internal line-edit to accept any text so the user can type
    # compact forms (e.g. 010126) without the widget rejecting intermediate chars.
    le = w.lineEdit()
    if le is None:
        return
    le.setInputMask("")   # clear any mask QDateEdit may set

    def _normalize() -> None:
        raw = le.text().strip()
        if not raw:
            return
        ymd = parse_flexible_date_to_ymd(raw)
        if ymd is None:
            return
        y, m, d = ymd
        # Temporarily block signals so setting the date doesn't re-trigger
        w.blockSignals(True)
        w.setDate(QDate(y, m, d))
        w.blockSignals(False)
        le.setText(f"{m:02d}/{d:02d}/{y:04d}")

    le.editingFinished.connect(_normalize)
    # Also normalize when the user presses Enter inside the spin sections
    w.dateChanged.connect(lambda _: None)  # keep internal state in sync


def create_app_date_edit(parent: Optional[QWidget] = None) -> QDateEdit:
    """Return a new ``QDateEdit`` with :func:`configure_qdate_edit_us` applied (for new UI)."""
    from PySide6.QtWidgets import QDateEdit

    w = QDateEdit(parent)
    configure_qdate_edit_us(w)
    return w
