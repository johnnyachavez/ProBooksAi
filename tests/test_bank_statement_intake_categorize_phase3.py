"""Bank Statement Intake — phase 3 step 3 categorize-module integration tests.

Locks the normalize-fallback and AI-fallback opt-ins on top of the
Phase-3 step 2 rules-engine wrapper:

* Default behavior is unchanged: rule scan against raw description.
* ``use_normalized_fallback=True`` retries with the normalized form when
  the raw scan finds nothing.
* ``ai_provider=...`` is consulted only after rules + normalize fail.
* AI suggestions are tagged with ``AI_MATCHED_PATTERN_LABEL`` regardless
  of what the provider returns in ``matched_pattern``.
* A raising provider does not crash the call — falls through to ``[]``.
"""

from __future__ import annotations

from typing import Optional

from probooksai.bank_import import BankDatabase
from probooksai.bank_statement_intake_categorize import (
    AI_MATCHED_PATTERN_LABEL,
    CategorySuggestion,
    suggest_categories_for_description,
    suggest_categories_for_rows,
)
from probooksai.bank_statement_intake import (
    SOURCE_TYPE_CSV,
    BankStatementIntakeRow,
)
from probooksai.extensions_schema import apply_extensions
from probooksai.rules_engine import add_rule


def _open_db(tmp_path) -> BankDatabase:
    db = BankDatabase(str(tmp_path / "categorize-phase3.db"))
    apply_extensions(db._conn)
    return db


def _row(desc: str) -> BankStatementIntakeRow:
    return BankStatementIntakeRow(
        txn_date="2026-03-10",
        description_raw=desc,
        debit=4.50,
        credit=None,
        amount_signed=-4.50,
        running_balance=None,
        source_type=SOURCE_TYPE_CSV,
        source_ref="x.csv#L1",
        confidence=1.0,
        needs_review=False,
    )


# ---------------------------------------------------------------------------
# Normalize fallback
# ---------------------------------------------------------------------------


def test_normalize_fallback_off_misses_noisy_description(tmp_path) -> None:
    """Without the fallback, a noisy 'STARBUCKS #1234 02/14' misses a pattern
    that only matches the clean form 'starbucks coffee'."""
    db = _open_db(tmp_path)
    try:
        add_rule(db._conn, "starbucks coffee", "5010 — Meals", priority=10)
        out = suggest_categories_for_description(
            db._conn, "POS PURCHASE STARBUCKS #1234 02/14"
        )
        # Rule pattern is "starbucks coffee" — substring of raw is just
        # "STARBUCKS", so without normalization no match.
        assert out == []
    finally:
        db.close()


def test_normalize_fallback_on_recovers_match(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        add_rule(db._conn, "starbucks", "5010 — Meals", priority=10)
        out = suggest_categories_for_description(
            db._conn,
            "POS PURCHASE STARBUCKS #1234 NYC NY 02/14",
            use_normalized_fallback=True,
        )
        assert len(out) == 1
        assert out[0].coa_account == "5010 — Meals"
    finally:
        db.close()


def test_normalize_fallback_does_not_run_when_raw_already_matches(tmp_path) -> None:
    """When the raw description already matches a rule we keep the raw
    confidence (longer raw text doesn't necessarily out-score normalized)."""
    db = _open_db(tmp_path)
    try:
        add_rule(db._conn, "STARBUCKS", "5010 — Meals", priority=10)
        raw_only = suggest_categories_for_description(
            db._conn, "STARBUCKS COFFEE"
        )
        with_fallback = suggest_categories_for_description(
            db._conn, "STARBUCKS COFFEE",
            use_normalized_fallback=True,
        )
        assert raw_only == with_fallback
    finally:
        db.close()


# ---------------------------------------------------------------------------
# AI fallback
# ---------------------------------------------------------------------------


def _fixed_provider(coa: str, conf: float = 0.55):
    def _provider(desc: str, normalized: str) -> Optional[CategorySuggestion]:
        return CategorySuggestion(
            coa_account=coa,
            matched_pattern=f"raw='{desc}' norm='{normalized}'",
            confidence=conf,
        )
    return _provider


def test_ai_provider_consulted_when_rules_and_normalize_miss(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        out = suggest_categories_for_description(
            db._conn,
            "Mystery Vendor 9999",
            use_normalized_fallback=True,
            ai_provider=_fixed_provider("8000 — AI Suggested"),
        )
        assert len(out) == 1
        assert out[0].coa_account == "8000 — AI Suggested"
        assert out[0].matched_pattern == AI_MATCHED_PATTERN_LABEL
    finally:
        db.close()


def test_ai_provider_skipped_when_rules_already_match(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        add_rule(db._conn, "starbucks", "5010 — Meals", priority=10)
        out = suggest_categories_for_description(
            db._conn,
            "STARBUCKS NYC",
            ai_provider=_fixed_provider("8000 — AI"),
        )
        assert len(out) == 1
        assert out[0].coa_account == "5010 — Meals"
        assert out[0].matched_pattern == "starbucks"
    finally:
        db.close()


def test_ai_provider_returning_none_yields_empty(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        out = suggest_categories_for_description(
            db._conn,
            "Mystery Vendor 9999",
            use_normalized_fallback=True,
            ai_provider=lambda desc, norm: None,
        )
        assert out == []
    finally:
        db.close()


def test_ai_provider_raising_does_not_crash_call(tmp_path) -> None:
    db = _open_db(tmp_path)

    def boom(desc: str, norm: str):
        raise RuntimeError("provider exploded")

    try:
        out = suggest_categories_for_description(
            db._conn, "Mystery Vendor", ai_provider=boom
        )
        assert out == []
    finally:
        db.close()


def test_for_rows_forwards_normalize_and_ai_options(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        add_rule(db._conn, "starbucks", "5010 — Meals", priority=10)
        rows = [
            _row("POS PURCHASE STARBUCKS #1234"),
            _row("Mystery Vendor 9999"),
        ]
        out = suggest_categories_for_rows(
            db,
            rows,
            use_normalized_fallback=True,
            ai_provider=_fixed_provider("8000 — AI"),
        )
        assert 0 in out and out[0][0].coa_account == "5010 — Meals"
        assert 1 in out and out[1][0].matched_pattern == AI_MATCHED_PATTERN_LABEL
    finally:
        db.close()


def test_for_rows_default_ignores_ai_and_normalize(tmp_path) -> None:
    """Defaults are unchanged from Phase-3 step 2: no normalize, no AI."""
    db = _open_db(tmp_path)
    try:
        add_rule(db._conn, "starbucks coffee", "5010 — Meals", priority=10)
        rows = [_row("POS PURCHASE STARBUCKS #1234")]
        out = suggest_categories_for_rows(db, rows)
        assert out == {}
    finally:
        db.close()
