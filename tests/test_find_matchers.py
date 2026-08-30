"""Unit tests for desktop_app.find_matchers (Invoice / Register / Write Checks Find)."""

from __future__ import annotations

import pytest

from desktop_app.find_matchers import (
    first_matching_row,
    parse_amount_needle,
    parse_date_needle,
    row_matches_find,
)


class TestParseAmountNeedle:
    def test_returns_none_for_blank_or_non_numeric(self) -> None:
        assert parse_amount_needle("") is None
        assert parse_amount_needle("   ") is None
        assert parse_amount_needle("abc") is None

    def test_absolute_value_from_signed_or_currency(self) -> None:
        assert parse_amount_needle("500") == 500.0
        assert parse_amount_needle("-500") == 500.0
        assert parse_amount_needle("$1,280.50") == 1280.5
        assert parse_amount_needle("(96.40)") == 96.4


class TestParseDateNeedle:
    def test_none_for_blank_or_bad_shape(self) -> None:
        assert parse_date_needle("") is None
        assert parse_date_needle("not a date") is None

    def test_us_and_iso_and_shorthand(self) -> None:
        assert parse_date_needle("08/01/2026") == "2026-08-01"
        assert parse_date_needle("2026-08-01") == "2026-08-01"
        assert parse_date_needle("8/1/26") == "2026-08-01"


class TestRowMatchesFind:
    def _inv_row(self, **overrides) -> dict:
        base = {
            "invoice_number": "INV-2101",
            "customer_name": "Harbor Logistics",
            "invoice_date": "2026-08-01",
            "total": 450.0,
        }
        base.update(overrides)
        return base

    def test_matches_invoice_number_substring(self) -> None:
        row = self._inv_row()
        assert row_matches_find(row, "2101", number_fields=("invoice_number",))
        assert row_matches_find(row, "inv-21", number_fields=("invoice_number",))
        assert not row_matches_find(row, "9999", number_fields=("invoice_number",))

    def test_matches_customer_name_case_insensitive(self) -> None:
        row = self._inv_row()
        assert row_matches_find(row, "harbor", name_fields=("customer_name",))
        assert row_matches_find(row, "LOGISTICS", name_fields=("customer_name",))
        assert not row_matches_find(row, "westside", name_fields=("customer_name",))

    def test_matches_amount_with_penny_tolerance_and_abs(self) -> None:
        row = self._inv_row(total=-450.005)
        assert row_matches_find(row, "450", amount_fields=("total",))
        assert row_matches_find(row, "$450.00", amount_fields=("total",))
        assert not row_matches_find(row, "451", amount_fields=("total",))

    def test_matches_date_via_iso_or_us_form(self) -> None:
        row = self._inv_row()
        assert row_matches_find(row, "08/01/2026", date_fields=("invoice_date",))
        assert row_matches_find(row, "2026-08-01", date_fields=("invoice_date",))
        assert row_matches_find(row, "8/1/26", date_fields=("invoice_date",))
        assert not row_matches_find(row, "08/02/2026", date_fields=("invoice_date",))

    def test_empty_or_bad_needle_never_matches(self) -> None:
        row = self._inv_row()
        assert not row_matches_find(row, "", number_fields=("invoice_number",))
        assert not row_matches_find(row, "   ", name_fields=("customer_name",))

    def test_handles_missing_fields_gracefully(self) -> None:
        row = {"invoice_number": "INV-9"}
        assert row_matches_find(
            row,
            "inv-9",
            number_fields=("invoice_number",),
            name_fields=("customer_name",),
            amount_fields=("total",),
            date_fields=("invoice_date",),
        )


class TestFirstMatchingRow:
    def test_returns_first_hit_in_iteration_order(self) -> None:
        rows = [
            {"invoice_number": "A", "customer_name": "Alpha", "total": 10.0, "invoice_date": "2026-01-01"},
            {"invoice_number": "B", "customer_name": "Bravo", "total": 20.0, "invoice_date": "2026-02-01"},
            {"invoice_number": "C", "customer_name": "Bravo", "total": 30.0, "invoice_date": "2026-03-01"},
        ]
        hit = first_matching_row(rows, "bravo", name_fields=("customer_name",))
        assert hit is not None
        assert hit["invoice_number"] == "B"

    def test_none_when_no_match(self) -> None:
        assert first_matching_row(
            [{"invoice_number": "A"}], "zzz", number_fields=("invoice_number",)
        ) is None
