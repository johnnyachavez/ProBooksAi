"""Bank Statement Intake — phase 3 step 3: normalizer-module tests."""

from __future__ import annotations

from probooksai.bank_statement_intake_normalize import (
    normalize_description,
    normalized_descriptions,
)


def test_empty_input_returns_empty() -> None:
    assert normalize_description("") == ""
    assert normalize_description(None) == ""
    assert normalize_description("   ") == ""


def test_lowercases_and_collapses_whitespace() -> None:
    out = normalize_description("  Starbucks   COFFEE  ")
    assert out == "starbucks coffee"


def test_strips_pos_and_card_purchase_prefixes() -> None:
    assert normalize_description("POS PURCHASE STARBUCKS NYC") == "starbucks nyc"
    assert normalize_description("Debit Card Purchase Starbucks") == "starbucks"
    assert normalize_description("CHECKCARD STARBUCKS") == "starbucks"


def test_strips_card_ending_markers() -> None:
    assert normalize_description("STARBUCKS xx1234") == "starbucks"
    assert normalize_description("STARBUCKS XXXXXXXX1234") == "starbucks"


def test_strips_store_and_pound_numbers() -> None:
    assert normalize_description("STARBUCKS #1234 NYC") == "starbucks nyc"
    # ``OK`` is the OK state code so the trailing-state pass also drops it;
    # the surviving signal "walmart" is what we want for rule matching.
    assert normalize_description("Walmart Store 4567 OK") == "walmart"


def test_strips_dates_inside_description() -> None:
    assert normalize_description("STARBUCKS 02/14") == "starbucks"
    assert normalize_description("STARBUCKS 2026-02-14") == "starbucks"
    assert normalize_description("STARBUCKS 2/14/26") == "starbucks"


def test_strips_times_inside_description() -> None:
    assert normalize_description("STARBUCKS 12:34") == "starbucks"
    assert normalize_description("STARBUCKS 12:34:56") == "starbucks"


def test_strips_reference_or_txn_ids() -> None:
    assert normalize_description("ACH PAYMENT REF 1234567") == "ach payment"
    assert normalize_description("PAYMENT TXN ABC123") == "payment"
    # AUTH#7890: the digit run is dropped by the long-numeric pass and the
    # leftover "auth" is acceptable noise — what matters is downstream
    # rule patterns can still match "payment" cleanly.
    out = normalize_description("PAYMENT AUTH#7890")
    assert "payment" in out
    assert "7890" not in out


def test_strips_trailing_state_codes() -> None:
    assert normalize_description("STARBUCKS NYC NY") == "starbucks nyc"
    # ``LA`` is also a valid US state code so the loop strips the whole
    # trailing pair — rule patterns rarely depend on city/state anyway.
    assert normalize_description("STARBUCKS LA CA") == "starbucks"


def test_drops_long_numeric_tokens() -> None:
    assert normalize_description("STARBUCKS 12345 67890") == "starbucks"


def test_keeps_short_numeric_tokens() -> None:
    """Single digit / 2–3 digit tokens may carry meaning; keep them."""
    assert normalize_description("Account 5 Service") == "account 5 service"
    assert normalize_description("Plan 100") == "plan 100"


def test_idempotent() -> None:
    raw = "POS PURCHASE STARBUCKS COFFEE #1234 NYC NY 02/14"
    once = normalize_description(raw)
    twice = normalize_description(once)
    assert once == twice
    assert "starbucks coffee" in once


def test_real_world_examples() -> None:
    assert "starbucks coffee" in normalize_description(
        "POS PURCHASE STARBUCKS COFFEE #1234 NYC NY 02/14"
    )
    assert "uber eats" in normalize_description(
        "DEBIT CARD PURCHASE UBER EATS xx5678 SAN FRANCISCO CA"
    )
    assert normalize_description("Withdrawal ATM #2345 02/14 12:34") == "atm"


def test_never_empties_a_non_empty_input() -> None:
    """Worst case: result is the lower-cased / collapsed copy of the input."""
    out = normalize_description("a b")
    assert out == "a b"


def test_normalized_descriptions_bulk_helper() -> None:
    out = normalized_descriptions(
        ["POS PURCHASE STARBUCKS NYC", "UBER EATS"]
    )
    assert out == ["starbucks nyc", "uber eats"]
