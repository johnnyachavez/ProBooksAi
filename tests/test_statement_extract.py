"""Phase 7 – heuristic statement text parsing (no OCR)."""

from __future__ import annotations

from probooksai.statement_extract import parse_statement_text


def test_parse_statement_text_basic():
    text = """
Header junk
2024-01-05  COFFEE SHOP   -4.50
2024-01-10  PAYROLL DEPOSIT  1,250.00
01/15/2024  UTILITIES  (120.00)
"""
    rows = parse_statement_text(text)
    assert len(rows) == 3
    assert rows[0]["txn_date"] == "2024-01-05"
    assert rows[0]["amount"] == -4.5
    assert "COFFEE" in rows[0]["description"]
    assert rows[1]["amount"] == 1250.0
    assert rows[2]["amount"] == -120.0


def test_parse_statement_text_skips_garbage():
    assert parse_statement_text("no dates here\nfoo bar\n") == []
