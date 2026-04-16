"""Tests for messy bank statement text parsing (staging / review rows)."""

from __future__ import annotations

from desktop_app.bank_statement_text_parse import (
    format_amount_cell,
    parse_bank_statement_text,
    parse_statement_line,
)


def test_parse_simple_dollar_amount() -> None:
    rows = parse_bank_statement_text(
        "01/15/2025  AMAZON MKTPLACE   $12.34\n"
    )
    assert len(rows) == 1
    r = rows[0]
    assert r.date_iso == "2025-01-15"
    assert r.amount == 12.34
    assert "AMAZON" in r.description.upper()
    assert "OK" in r.type_status


def test_parse_paren_negative() -> None:
    rows = parse_bank_statement_text("01/16/2025  CHECK 123  ($50.00)\n")
    assert len(rows) == 1
    assert rows[0].amount == -50.0
    assert "CHECK" in rows[0].description.upper()


def test_parse_needs_review_no_amount() -> None:
    rows = parse_bank_statement_text("02/01/2025  Something happened\n")
    assert len(rows) == 1
    assert rows[0].type_status == "Needs Review"
    assert rows[0].amount is None


def test_parse_skips_blank_and_rules() -> None:
    assert parse_statement_line("") is None
    assert parse_statement_line("   ---   ") is None


def test_format_amount_cell() -> None:
    assert format_amount_cell(None) == "—"
    assert "$1.00" in format_amount_cell(1.0)
