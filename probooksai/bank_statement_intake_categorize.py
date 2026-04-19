"""Bank Statement Intake — phase 3 step 2: rules-based categorization.

Wraps :mod:`probooksai.rules_engine` for the review panel:

* Returns *suggestions only* — never mutates the staged rows or the
  register. The panel is responsible for displaying suggestions and
  applying them on explicit user action.
* Suggestions are bound to the staged row's *current* description, so
  re-running the scan after a description edit can produce a different
  match.
* A suggestion carries ``matched_pattern`` + ``confidence`` so the panel
  can show *why* (and so future Phase-3 telemetry can rank patterns).

Confidence is a coarse heuristic: longer patterns are more specific and
score higher. We deliberately keep this simple — Phase 3 step 3
introduces description normalization and an optional AI fallback for
the "no rule fired" tail.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from probooksai.bank_import import BankDatabase
from probooksai.bank_statement_intake import BankStatementIntakeRow

DEFAULT_SUGGESTION_LIMIT = 3
# Minimum description length we'll bother scanning. Avoids matching a
# one-letter pattern against a one-letter description.
_MIN_DESC_LEN = 2


@dataclass(frozen=True)
class CategorySuggestion:
    """One rule-based COA suggestion for a single staged row."""

    coa_account: str
    matched_pattern: str
    confidence: float

    def display_label(self) -> str:
        return f"{self.coa_account}  \u2190  '{self.matched_pattern}'"


def _confidence_for_pattern(pattern: str, description: str) -> float:
    """Coarse 0.40–0.95 confidence based on pattern specificity.

    A longer pattern that covers more of the description is treated as a
    more specific (and so more confident) match. This is deliberately
    not learned — Phase 3 step 3 can layer normalization on top.
    """
    if not pattern or not description:
        return 0.40
    p_len = len(pattern.strip())
    d_len = max(len(description.strip()), 1)
    coverage = min(p_len / d_len, 1.0)
    base = 0.40 + 0.55 * coverage
    return max(0.40, min(0.95, round(base, 3)))


def suggest_categories_for_description(
    conn: sqlite3.Connection,
    description: str,
    *,
    limit: int = DEFAULT_SUGGESTION_LIMIT,
) -> list[CategorySuggestion]:
    """Return up to *limit* :class:`CategorySuggestion` for *description*.

    Walks ``categorization_rules`` in priority order and emits one
    suggestion per active pattern that occurs (case-insensitive) in
    *description*. Duplicate COAs are deduped, keeping the highest-priority
    pattern. Returns ``[]`` for empty / too-short descriptions.
    """
    if conn is None or limit < 1:
        return []
    desc = (description or "").strip()
    if len(desc) < _MIN_DESC_LEN:
        return []
    desc_l = desc.lower()
    rows = conn.execute(
        """
        SELECT pattern, coa_account, priority
        FROM categorization_rules
        WHERE is_active = 1
        ORDER BY priority DESC, id ASC
        """
    ).fetchall()
    out: list[CategorySuggestion] = []
    seen_coa: set[str] = set()
    for r in rows:
        pat = (r["pattern"] or "").strip()
        coa = (r["coa_account"] or "").strip()
        if not pat or not coa:
            continue
        if pat.lower() not in desc_l:
            continue
        if coa in seen_coa:
            continue
        seen_coa.add(coa)
        out.append(
            CategorySuggestion(
                coa_account=coa,
                matched_pattern=pat,
                confidence=_confidence_for_pattern(pat, desc),
            )
        )
        if len(out) >= limit:
            break
    return out


def suggest_categories_for_rows(
    bank_db: BankDatabase,
    rows: Sequence[BankStatementIntakeRow],
    *,
    limit: int = DEFAULT_SUGGESTION_LIMIT,
) -> dict[int, list[CategorySuggestion]]:
    """Return ``{row_index: [CategorySuggestion, ...]}`` for *rows*.

    Rows whose description produces zero suggestions are absent from the
    result. Never mutates *rows*.
    """
    if bank_db is None:
        return {}
    rows_list = list(rows or [])
    if not rows_list:
        return {}
    conn: sqlite3.Connection = bank_db._conn
    out: dict[int, list[CategorySuggestion]] = {}
    for i, row in enumerate(rows_list):
        suggestions = suggest_categories_for_description(
            conn, row.description_raw or "", limit=limit
        )
        if suggestions:
            out[i] = suggestions
    return out


def apply_top_suggestions(
    rows: Sequence[BankStatementIntakeRow],
    suggestions: dict[int, list[CategorySuggestion]],
    *,
    overwrite: bool = False,
) -> int:
    """Set ``row.coa_account`` from the top suggestion for each row.

    By default skips any row whose ``coa_account`` is already non-empty
    (preserves user-typed overrides). Pass ``overwrite=True`` to force
    re-application. Returns the number of rows updated.
    """
    n = 0
    for i, row in enumerate(rows):
        sug_list = suggestions.get(i)
        if not sug_list:
            continue
        if not overwrite and (row.coa_account or "").strip():
            continue
        row.coa_account = sug_list[0].coa_account
        n += 1
    return n


__all__ = [
    "CategorySuggestion",
    "DEFAULT_SUGGESTION_LIMIT",
    "apply_top_suggestions",
    "suggest_categories_for_description",
    "suggest_categories_for_rows",
]


_IterableHint = Iterable[BankStatementIntakeRow]  # noqa: F841
_OptionalConn = Optional[sqlite3.Connection]  # noqa: F841
