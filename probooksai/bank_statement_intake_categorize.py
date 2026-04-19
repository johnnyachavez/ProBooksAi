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
from typing import Callable, Iterable, Optional, Sequence

from probooksai.bank_import import BankDatabase
from probooksai.bank_statement_intake import BankStatementIntakeRow
from probooksai.bank_statement_intake_normalize import normalize_description

DEFAULT_SUGGESTION_LIMIT = 3
# Minimum description length we'll bother scanning. Avoids matching a
# one-letter pattern against a one-letter description.
_MIN_DESC_LEN = 2

# Phase-3 step 3: opt-in AI fallback. When ``ai_provider`` is supplied
# and the rules+normalize path produces zero suggestions for a row, the
# provider is consulted. The default provider returns ``None`` (no
# suggestion), so even with the feature flag on the system is silent
# until a real provider is wired up. AI suggestions are clearly tagged
# in :class:`CategorySuggestion.matched_pattern` (``"<ai>"``) so the
# panel UI and downstream logging can distinguish them from rule hits.
AI_MATCHED_PATTERN_LABEL = "<ai>"

# Type alias: ``ai_provider(description, normalized) -> CategorySuggestion | None``
AIProvider = Callable[[str, str], Optional["CategorySuggestion"]]


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


def _scan_rules_for_text(
    conn: sqlite3.Connection,
    text: str,
    *,
    limit: int,
) -> list[CategorySuggestion]:
    """Single-pass rule scan against *text* (no normalize / no AI)."""
    text_l = text.lower()
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
        if pat.lower() not in text_l:
            continue
        if coa in seen_coa:
            continue
        seen_coa.add(coa)
        out.append(
            CategorySuggestion(
                coa_account=coa,
                matched_pattern=pat,
                confidence=_confidence_for_pattern(pat, text),
            )
        )
        if len(out) >= limit:
            break
    return out


def suggest_categories_for_description(
    conn: sqlite3.Connection,
    description: str,
    *,
    limit: int = DEFAULT_SUGGESTION_LIMIT,
    use_normalized_fallback: bool = False,
    ai_provider: Optional[AIProvider] = None,
) -> list[CategorySuggestion]:
    """Return up to *limit* :class:`CategorySuggestion` for *description*.

    Resolution order:

    1. Run the rules engine against the **raw** description.
    2. If empty AND ``use_normalized_fallback=True``, re-run against the
       :func:`normalize_description` form (cleaner for noisy bank memos).
    3. If still empty AND ``ai_provider`` is supplied, ask the provider
       for a suggestion. Returned AI suggestions are tagged with
       :data:`AI_MATCHED_PATTERN_LABEL` so the UI and audit trail can
       distinguish them from rule hits.

    Returns ``[]`` for empty / too-short descriptions.
    """
    if conn is None or limit < 1:
        return []
    desc = (description or "").strip()
    if len(desc) < _MIN_DESC_LEN:
        return []

    rule_hits = _scan_rules_for_text(conn, desc, limit=limit)
    if rule_hits:
        return rule_hits

    if use_normalized_fallback:
        normalized = normalize_description(desc)
        if normalized and normalized.lower() != desc.lower():
            normalized_hits = _scan_rules_for_text(conn, normalized, limit=limit)
            if normalized_hits:
                return normalized_hits

    if ai_provider is not None:
        try:
            normalized = normalize_description(desc)
            ai_suggestion = ai_provider(desc, normalized)
        except Exception:
            ai_suggestion = None
        if ai_suggestion is not None:
            # Force the AI tag so callers can filter by it.
            tagged = CategorySuggestion(
                coa_account=ai_suggestion.coa_account,
                matched_pattern=AI_MATCHED_PATTERN_LABEL,
                confidence=ai_suggestion.confidence,
            )
            return [tagged]

    return []


def suggest_categories_for_rows(
    bank_db: BankDatabase,
    rows: Sequence[BankStatementIntakeRow],
    *,
    limit: int = DEFAULT_SUGGESTION_LIMIT,
    use_normalized_fallback: bool = False,
    ai_provider: Optional[AIProvider] = None,
) -> dict[int, list[CategorySuggestion]]:
    """Return ``{row_index: [CategorySuggestion, ...]}`` for *rows*.

    Rows whose description produces zero suggestions are absent from
    the result. Never mutates *rows*. ``use_normalized_fallback`` and
    ``ai_provider`` are forwarded to
    :func:`suggest_categories_for_description` per row.
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
            conn,
            row.description_raw or "",
            limit=limit,
            use_normalized_fallback=use_normalized_fallback,
            ai_provider=ai_provider,
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
    "AIProvider",
    "AI_MATCHED_PATTERN_LABEL",
    "CategorySuggestion",
    "DEFAULT_SUGGESTION_LIMIT",
    "apply_top_suggestions",
    "suggest_categories_for_description",
    "suggest_categories_for_rows",
]


_IterableHint = Iterable[BankStatementIntakeRow]  # noqa: F841
_OptionalConn = Optional[sqlite3.Connection]  # noqa: F841
