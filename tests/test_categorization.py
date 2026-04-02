"""
Tests for AI categorisation and COA mapping.
Cloud API calls are mocked; no real network requests are made.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from ai import CategorySuggestions, ExtractionResult
from probooksai.coa import COAEntry, coa_display_list, load_coa


# ---------------------------------------------------------------------------
# CategorySuggestions dataclass
# ---------------------------------------------------------------------------

class TestCategorySuggestions:
    def test_default_confidence_zero(self):
        s = CategorySuggestions()
        assert s.confidence == 0.0

    def test_default_alternatives_empty(self):
        s = CategorySuggestions()
        assert s.alternatives == []

    def test_fields_set(self):
        s = CategorySuggestions(
            coa_account="6100 – Rent Expense",
            coa_account_number="6100",
            tax_category="Business Expense",
            confidence=0.88,
            rationale="Document is a rent invoice",
        )
        assert s.coa_account_number == "6100"
        assert s.confidence == pytest.approx(0.88)


# ---------------------------------------------------------------------------
# COA loading helpers
# ---------------------------------------------------------------------------

class TestCOALoading:
    def test_load_coa_returns_list(self):
        coa = load_coa()
        assert isinstance(coa, list)
        assert len(coa) > 0

    def test_coa_entries_are_namedtuples(self):
        coa = load_coa()
        for entry in coa:
            assert isinstance(entry, COAEntry)

    def test_coa_sorted_by_account_number(self):
        coa = load_coa()
        numbers = [e.account_number for e in coa]
        assert numbers == sorted(numbers)

    def test_coa_display_contains_account_numbers(self):
        display = coa_display_list()
        # Should include e.g. "1000 – Cash – Checking"
        assert any("1000" in d for d in display)

    def test_coa_display_format(self):
        display = coa_display_list()
        for item in display:
            assert "–" in item or "-" in item, f"Unexpected display format: {item!r}"

    def test_coa_has_expense_accounts(self):
        coa = load_coa()
        expenses = [e for e in coa if e.account_type == "Expense"]
        assert len(expenses) >= 10

    def test_coa_has_revenue_accounts(self):
        coa = load_coa()
        revenues = [e for e in coa if e.account_type == "Revenue"]
        assert len(revenues) >= 3

    def test_coa_entry_display_property(self):
        entry = COAEntry("6100", "Rent Expense", "Expense", "Operating Expense", "Debit", "Office rent")
        assert entry.display == "6100 – Rent Expense"


# ---------------------------------------------------------------------------
# _build_coa_summary helper
# ---------------------------------------------------------------------------

class TestCOASummary:
    def test_summary_contains_account_numbers(self):
        from ai.categorizer import _build_coa_summary
        coa = load_coa()
        summary = _build_coa_summary(coa)
        assert "6100" in summary

    def test_summary_works_with_tuple_coa(self):
        from ai.categorizer import _build_coa_summary
        coa = [("6100", "Rent Expense"), ("6200", "Marketing")]
        summary = _build_coa_summary(coa)
        assert "Rent Expense" in summary

    def test_summary_contains_all_entries(self):
        from ai.categorizer import _build_coa_summary
        coa = load_coa()
        summary = _build_coa_summary(coa)
        # Every account number should appear
        for entry in coa:
            assert entry.account_number in summary


# ---------------------------------------------------------------------------
# suggest_categories – mocked API calls
# ---------------------------------------------------------------------------

_CATEGORY_RESPONSE = json.dumps({
    "coa_account": "6100",
    "tax_category": "Business Expense",
    "confidence": 0.88,
    "rationale": "Rent invoice maps to Rent Expense account.",
    "alternatives": [
        {"account": "6900", "confidence": 0.15}
    ],
})


class TestSuggestCategories:
    def _rent_extraction(self):
        return ExtractionResult(
            vendor="Landlord LLC",
            doc_type="invoice",
            invoice_number="RENT-2025-01",
            doc_date="2025-01-01",
            total=2500.0,
            currency="USD",
            notes="Monthly office rent",
        )

    @patch("ai.extractor._call_openai")
    def test_suggest_returns_coa_account(self, mock_call):
        mock_call.return_value = _CATEGORY_RESPONSE
        coa = load_coa()
        result = self._rent_extraction()
        from ai.categorizer import suggest_categories
        sugg = suggest_categories(result, coa)
        assert sugg.coa_account_number == "6100"
        assert "Rent" in sugg.coa_account

    @patch("ai.extractor._call_openai")
    def test_suggest_returns_tax_category(self, mock_call):
        mock_call.return_value = _CATEGORY_RESPONSE
        from ai.categorizer import suggest_categories
        sugg = suggest_categories(self._rent_extraction(), load_coa())
        assert sugg.tax_category == "Business Expense"

    @patch("ai.extractor._call_openai")
    def test_suggest_confidence_in_range(self, mock_call):
        mock_call.return_value = _CATEGORY_RESPONSE
        from ai.categorizer import suggest_categories
        sugg = suggest_categories(self._rent_extraction(), load_coa())
        assert 0.0 <= sugg.confidence <= 1.0

    @patch("ai.extractor._call_openai")
    def test_suggest_includes_rationale(self, mock_call):
        mock_call.return_value = _CATEGORY_RESPONSE
        from ai.categorizer import suggest_categories
        sugg = suggest_categories(self._rent_extraction(), load_coa())
        assert sugg.rationale is not None
        assert len(sugg.rationale) > 0

    @patch("ai.extractor._call_openai")
    def test_suggest_includes_alternatives(self, mock_call):
        mock_call.return_value = _CATEGORY_RESPONSE
        from ai.categorizer import suggest_categories
        sugg = suggest_categories(self._rent_extraction(), load_coa())
        assert isinstance(sugg.alternatives, list)
        assert len(sugg.alternatives) > 0

    @patch("ai.extractor._call_openai")
    def test_api_error_captured(self, mock_call):
        mock_call.side_effect = RuntimeError("Network error")
        from ai.categorizer import suggest_categories
        sugg = suggest_categories(self._rent_extraction(), load_coa())
        assert sugg.error is not None

    def test_unsupported_provider_returns_error(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "anthropic")
        from ai.categorizer import suggest_categories
        sugg = suggest_categories(self._rent_extraction(), load_coa())
        assert sugg.error is not None
        assert "anthropic" in sugg.error.lower()

    @patch("ai.extractor._call_openai")
    def test_lookup_account_name(self, mock_call):
        mock_call.return_value = _CATEGORY_RESPONSE
        from ai.categorizer import suggest_categories
        sugg = suggest_categories(self._rent_extraction(), load_coa())
        # The full display should include both number and name
        assert sugg.coa_account is not None
        assert "6100" in sugg.coa_account


# ---------------------------------------------------------------------------
# _lookup_account_name helper
# ---------------------------------------------------------------------------

class TestLookupAccountName:
    def test_lookup_by_number(self):
        from ai.categorizer import _lookup_account_name
        coa = load_coa()
        name = _lookup_account_name("6100", coa)
        assert name == "Rent Expense"

    def test_lookup_missing_returns_none(self):
        from ai.categorizer import _lookup_account_name
        coa = load_coa()
        assert _lookup_account_name("9999", coa) is None

    def test_lookup_none_returns_none(self):
        from ai.categorizer import _lookup_account_name
        coa = load_coa()
        assert _lookup_account_name(None, coa) is None

    def test_lookup_tuple_coa(self):
        from ai.categorizer import _lookup_account_name
        coa = [("6100", "Rent Expense"), ("6200", "Marketing")]
        assert _lookup_account_name("6200", coa) == "Marketing"
