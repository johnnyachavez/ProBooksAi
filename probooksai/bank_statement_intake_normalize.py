"""Bank Statement Intake — phase 3 step 3: description normalization.

Banks ship transaction descriptions with a lot of noise: POS terminal
ids, store numbers, dates, city/state codes, transaction reference
ids, card-ending digits, and assorted punctuation. That noise prevents
substring rules ("starbucks") from matching real-world memos like
``STARBUCKS COFFEE #1234 NYC 02/14``.

This module provides one pure function — :func:`normalize_description`
— that strips that noise and emits a stable, lower-cased token
sequence suitable for the rules-engine fallback path. It never touches
the original description on the staged row; the panel keeps the raw
text editable and just runs both forms through the rules engine.

Design rules:

* Pure / no I/O. Same input → same output.
* Idempotent: ``normalize(normalize(x)) == normalize(x)``.
* Conservative: when in doubt we **keep** a token. Aggressive stripping
  would cause silent miscategorizations.
* Never empties a non-empty input — the worst case is that we just
  return a lower-cased / collapsed copy of what we got.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

# Common bank/POS prefixes we strip up front. These are noise that
# almost never carries categorization signal.
_BOILERPLATE_PREFIXES: tuple[str, ...] = (
    "purchase ",
    "purchase  ",
    "pos purchase ",
    "debit card purchase ",
    "card purchase ",
    "checkcard ",
    "check card ",
    "ach debit ",
    "ach credit ",
    "deposit ",
    "withdrawal ",
)

# Patterns for tokens that carry no categorization signal. Order
# matters — earlier regexes run first.
_NOISE_REGEXES: tuple[re.Pattern, ...] = (
    # Card-ending markers like "xxxxxxxx1234" or "x1234".
    re.compile(r"\bx{2,}\d{2,}\b", re.IGNORECASE),
    # POS terminal / store numbers like "#1234" or "store 1234".
    re.compile(r"#\s*\d{2,}\b"),
    re.compile(r"\bstore\s+\d{2,}\b", re.IGNORECASE),
    # Reference / transaction IDs like "ref 123456" or "txn123456".
    re.compile(r"\b(?:ref|txn|trans|trn|auth)\s*[:#]?\s*[a-z0-9]{4,}\b", re.IGNORECASE),
    # Dates inside the description: 01/02, 1/2/26, 2026-01-02.
    re.compile(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b"),
    re.compile(r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b"),
    # Times like 12:34 or 12:34:56.
    re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b"),
    # Trailing two-letter US state codes preceded by whitespace, when
    # they sit at the end of the line. We keep the city name itself —
    # only the dangling state code is stripped.
    re.compile(r"\s+(?:[A-Z]{2})$"),
)

# Two-letter state codes that bank descriptions often dangle. Used by
# a second pass that strips them when they appear after a city token.
_US_STATE_CODES: frozenset[str] = frozenset(
    {
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    }
)


def _strip_boilerplate_prefix(text: str) -> str:
    lowered = text.lower()
    for prefix in _BOILERPLATE_PREFIXES:
        if lowered.startswith(prefix):
            return text[len(prefix):]
    return text


def _strip_trailing_state_codes(text: str) -> str:
    """Drop dangling 2-letter state codes at the end of the description."""
    parts = text.split()
    while parts and parts[-1].upper() in _US_STATE_CODES:
        parts.pop()
    return " ".join(parts)


def _strip_pure_number_tokens(text: str) -> str:
    """Drop standalone all-digit tokens longer than 3 chars (store numbers, etc).

    Short numbers like "5" or "20" are preserved because they may be
    meaningful in a category name. Card-ending markers and date-like
    tokens are stripped earlier by the regex pass.
    """
    keep: list[str] = []
    for tok in text.split():
        bare = tok.strip(".,#-")
        if bare.isdigit() and len(bare) >= 4:
            continue
        keep.append(tok)
    return " ".join(keep)


def normalize_description(raw: Optional[str]) -> str:
    """Return a normalized, lower-cased form of *raw* suitable for rule matching.

    Empty / whitespace-only input returns ``""``.
    """
    if not raw:
        return ""
    text = str(raw).strip()
    if not text:
        return ""

    # Step 1: strip common bank/POS boilerplate prefixes (case-insensitive).
    text = _strip_boilerplate_prefix(text)

    # Step 2: run the noise regexes.
    for rx in _NOISE_REGEXES:
        text = rx.sub(" ", text)

    # Step 3: drop dangling US state codes (e.g., "starbucks nyc NY").
    text = _strip_trailing_state_codes(text)

    # Step 4: drop standalone long numeric tokens.
    text = _strip_pure_number_tokens(text)

    # Step 5: collapse non-alphanumeric runs to single spaces, lower-case.
    text = re.sub(r"[^\w\s]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip().lower()

    return text


def normalized_descriptions(raws: Iterable[str]) -> list[str]:
    """Bulk helper: normalize every input string in order."""
    return [normalize_description(r) for r in raws]


__all__ = ["normalize_description", "normalized_descriptions"]
