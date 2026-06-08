"""Bank Statement Intake — phase 3 step 2: categorize-module tests.

Locks:

* Suggestions come from active ``categorization_rules`` ranked by priority.
* Pattern matching is case-insensitive; longer patterns produce higher
  confidence.
* The ``apply_top_suggestions`` writer respects existing user-typed COA
  unless ``overwrite=True`` is passed.
* Disabled rules are ignored.
* Empty / very-short descriptions never produce suggestions.
"""

from __future__ import annotations

from probooksai.bank_import import BankDatabase
from probooksai.bank_statement_intake import (
    SOURCE_TYPE_CSV,
    BankStatementIntakeRow,
)
from probooksai.bank_statement_intake_categorize import (
    CategorySuggestion,
    apply_top_suggestions,
    suggest_categories_for_description,
    suggest_categories_for_rows,
)
from probooksai.extensions_schema import apply_extensions
from probooksai.rules_engine import add_rule


def _open_db(tmp_path) -> BankDatabase:
    db = BankDatabase(str(tmp_path / "categorize.db"))
    apply_extensions(db._conn)
    return db


def _row(desc: str, *, coa: str = "") -> BankStatementIntakeRow:
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
        coa_account=coa,
    )


# ---------------------------------------------------------------------------
# suggest_categories_for_description
# ---------------------------------------------------------------------------


def test_active_rule_with_substring_returns_suggestion(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        add_rule(db._conn, "starbucks", "5010 — Meals & Coffee", priority=10)
        out = suggest_categories_for_description(
            db._conn, "STARBUCKS COFFEE 1234"
        )
        assert len(out) == 1
        assert out[0].coa_account == "5010 — Meals & Coffee"
        assert out[0].matched_pattern == "starbucks"
        assert 0.40 <= out[0].confidence <= 0.95
    finally:
        db.close()


def test_inactive_rule_is_ignored(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        add_rule(
            db._conn, "starbucks", "5010 — Meals & Coffee",
            priority=10, is_active=False,
        )
        out = suggest_categories_for_description(
            db._conn, "STARBUCKS COFFEE 1234"
        )
        assert out == []
    finally:
        db.close()


def test_higher_priority_rule_wins_among_overlapping_matches(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        add_rule(db._conn, "uber", "6020 — Travel", priority=5)
        add_rule(db._conn, "uber eats", "5010 — Meals", priority=20)
        out = suggest_categories_for_description(db._conn, "UBER EATS NYC")
        assert out, "expected at least one suggestion"
        assert out[0].coa_account == "5010 — Meals"
        assert out[0].matched_pattern == "uber eats"
    finally:
        db.close()


def test_dedup_keeps_only_one_per_coa(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        add_rule(db._conn, "uber eats", "5010 — Meals", priority=10)
        add_rule(db._conn, "uber", "5010 — Meals", priority=5)
        out = suggest_categories_for_description(db._conn, "UBER EATS NYC")
        coas = [s.coa_account for s in out]
        assert coas.count("5010 — Meals") == 1
    finally:
        db.close()


def test_empty_description_returns_nothing(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        add_rule(db._conn, "x", "Y", priority=10)
        assert suggest_categories_for_description(db._conn, "") == []
        assert suggest_categories_for_description(db._conn, "   ") == []
    finally:
        db.close()


def test_short_description_returns_nothing(tmp_path) -> None:
    """Single-character descriptions never produce a suggestion."""
    db = _open_db(tmp_path)
    try:
        add_rule(db._conn, "x", "Y", priority=10)
        assert suggest_categories_for_description(db._conn, "x") == []
    finally:
        db.close()


def test_limit_caps_suggestion_count(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        add_rule(db._conn, "shop", "A", priority=10)
        add_rule(db._conn, "coffee", "B", priority=9)
        add_rule(db._conn, "small", "C", priority=8)
        out = suggest_categories_for_description(
            db._conn, "Coffee Shop Small Order", limit=2
        )
        assert len(out) == 2
    finally:
        db.close()


def test_longer_pattern_yields_higher_confidence(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        add_rule(db._conn, "u", "U", priority=10)
        add_rule(db._conn, "uber eats", "UE", priority=10)
        out = suggest_categories_for_description(db._conn, "uber eats")
        coa_to_conf = {s.coa_account: s.confidence for s in out}
        assert coa_to_conf["UE"] > coa_to_conf["U"]
    finally:
        db.close()


# ---------------------------------------------------------------------------
# suggest_categories_for_rows
# ---------------------------------------------------------------------------


def test_for_rows_keys_only_matched_indexes(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        add_rule(db._conn, "starbucks", "5010 — Meals", priority=10)
        rows = [_row("STARBUCKS NYC"), _row("Some Random Vendor")]
        out = suggest_categories_for_rows(db, rows)
        assert 0 in out and 1 not in out
    finally:
        db.close()


def test_for_rows_with_no_db_returns_empty(tmp_path) -> None:
    out = suggest_categories_for_rows(None, [_row("Anything")])
    assert out == {}


def test_for_rows_with_empty_input_returns_empty(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        assert suggest_categories_for_rows(db, []) == {}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# apply_top_suggestions
# ---------------------------------------------------------------------------


def test_apply_writes_top_suggestion_into_empty_coa(tmp_path) -> None:
    rows = [_row("STARBUCKS NYC"), _row("UBER EATS")]
    suggestions = {
        0: [CategorySuggestion("5010 — Meals", "starbucks", 0.8)],
        1: [CategorySuggestion("5010 — Meals", "uber eats", 0.9)],
    }
    n = apply_top_suggestions(rows, suggestions)
    assert n == 2
    assert rows[0].coa_account == "5010 — Meals"
    assert rows[1].coa_account == "5010 — Meals"


def test_apply_skips_rows_with_existing_coa_unless_overwrite(tmp_path) -> None:
    rows = [_row("STARBUCKS NYC", coa="9999 — User Choice")]
    suggestions = {
        0: [CategorySuggestion("5010 — Meals", "starbucks", 0.8)],
    }
    n = apply_top_suggestions(rows, suggestions)
    assert n == 0
    assert rows[0].coa_account == "9999 — User Choice"

    n = apply_top_suggestions(rows, suggestions, overwrite=True)
    assert n == 1
    assert rows[0].coa_account == "5010 — Meals"


def test_apply_returns_zero_when_no_suggestions(tmp_path) -> None:
    rows = [_row("STARBUCKS NYC")]
    n = apply_top_suggestions(rows, {})
    assert n == 0
    assert rows[0].coa_account == ""


def test_display_label_includes_coa_and_pattern() -> None:
    s = CategorySuggestion("5010 — Meals", "starbucks", 0.8)
    label = s.display_label()
    assert "5010 — Meals" in label
    assert "starbucks" in label
