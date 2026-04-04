"""Phase 7 – OCR/vision stub contract (no external APIs)."""

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
    """Stub returns structured NOT_IMPLEMENTED (status, code, detail); no rows."""
    r = extract_rows_from_statement_scan("/nonexistent/for_api_shape_only.pdf")
    assert isinstance(r, StatementScanExtractionResult)
    assert r.status == StatementScanStatus.NOT_IMPLEMENTED
    assert r.rows == []
    assert r.error == OCR_NOT_IMPLEMENTED
    assert r.detail
    assert "Phase 7" in (r.detail or "")


def test_statement_scan_extraction_result_is_frozen() -> None:
    """Results are immutable so callers treat them as values (future vision backends)."""
    r = extract_rows_from_statement_scan("x.pdf")
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.status = StatementScanStatus.OK  # type: ignore[misc]
