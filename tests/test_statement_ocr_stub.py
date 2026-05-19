"""AI PDF extraction – contract tests (no external API calls needed)."""

from __future__ import annotations

import dataclasses

import pytest

from probooksai.statement_ocr_stub import (
    OCR_NOT_IMPLEMENTED,
    StatementScanExtractionResult,
    StatementScanStatus,
    extract_rows_from_statement_scan,
)


def test_extract_rows_from_statement_scan_not_implemented_contract() -> None:
    """When no API key is set, returns NOT_IMPLEMENTED with a helpful detail message."""
    r = extract_rows_from_statement_scan("/nonexistent/for_api_shape_only.pdf")
    assert isinstance(r, StatementScanExtractionResult)
    assert r.status == StatementScanStatus.NOT_IMPLEMENTED
    assert r.rows == []
    assert r.error == OCR_NOT_IMPLEMENTED
    assert r.detail
    # Detail should tell the user how to configure an API key
    assert "ANTHROPIC_API_KEY" in (r.detail or "") or "OPENAI_API_KEY" in (r.detail or "")


def test_statement_scan_extraction_result_is_frozen() -> None:
    """Results are immutable so callers treat them as values (future vision backends)."""
    r = extract_rows_from_statement_scan("x.pdf")
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.status = StatementScanStatus.OK  # type: ignore[misc]
