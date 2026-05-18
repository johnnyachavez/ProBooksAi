"""
Tests for bot.telegram_bot — formatting helpers and import guard.
No real Telegram or API calls are made.
"""

from __future__ import annotations

import pytest

from bot.telegram_bot import (
    _fmt_currency,
    _fmt_extraction,
    _fmt_invoices,
    _fmt_bills,
    _fmt_aging,
    _api_base,
)


def test_fmt_currency_basic():
    assert _fmt_currency(1000) == "$1,000.00"
    assert _fmt_currency(0) == "$0.00"
    assert _fmt_currency(None) == "—"
    assert _fmt_currency("bad") == "bad"  # non-numeric strings returned as-is


def test_fmt_extraction_full():
    data = {
        "vendor": "ACME Corp",
        "doc_type": "invoice",
        "invoice_number": "INV-42",
        "doc_date": "2025-06-01",
        "due_date": "2025-07-01",
        "subtotal": 100.0,
        "tax": 8.0,
        "total": 108.0,
        "confidence": 0.95,
    }
    text = _fmt_extraction(data)
    assert "ACME Corp" in text
    assert "INV-42" in text
    assert "$108.00" in text
    assert "95%" in text


def test_fmt_extraction_with_error():
    data = {"error": "AI_PROVIDER not set", "confidence": 0.0}
    text = _fmt_extraction(data)
    assert "Error" in text


def test_fmt_invoices_empty():
    text = _fmt_invoices([])
    assert "None" in text


def test_fmt_invoices_with_rows():
    rows = [
        {"invoice_number": "INV-1", "customer_name": "Bob", "total": 500.0},
        {"invoice_number": "INV-2", "customer_name": "Alice", "total": 250.0},
    ]
    text = _fmt_invoices(rows)
    assert "Bob" in text
    assert "$500.00" in text
    assert "Alice" in text


def test_fmt_bills_empty():
    text = _fmt_bills([])
    assert "None" in text


def test_fmt_bills_with_rows():
    rows = [{"vendor_name": "Office Depot", "total": 99.99, "due_date": "2025-08-01"}]
    text = _fmt_bills(rows)
    assert "Office Depot" in text
    assert "$99.99" in text
    assert "2025-08-01" in text


def test_fmt_aging_empty():
    text = _fmt_aging([], "AR")
    assert "No open items" in text


def test_fmt_aging_with_rows():
    rows = [{"name": "BigCo", "total": 3500.0}]
    text = _fmt_aging(rows, "AR")
    assert "BigCo" in text
    assert "$3,500.00" in text


def test_api_base_default(monkeypatch):
    monkeypatch.delenv("API_BASE_URL", raising=False)
    assert _api_base() == "http://127.0.0.1:8000"


def test_api_base_custom(monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "https://myserver.example.com/")
    assert _api_base() == "https://myserver.example.com"


def test_run_bot_missing_token(monkeypatch):
    """run_bot() raises RuntimeError when TELEGRAM_BOT_TOKEN is missing."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    # Mock the telegram package so _require_telegram() passes
    import sys
    from unittest.mock import MagicMock
    stub = MagicMock()
    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        with pytest.MonkeyPatch().context() as m:
            m.setitem(sys.modules, "telegram", stub)
            m.setitem(sys.modules, "telegram.ext", stub)
            from bot.telegram_bot import run_bot
            run_bot()
