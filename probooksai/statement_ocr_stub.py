"""
Phase 7 – Bank statement PDF / image intake.

- **Digital PDFs (text layer):** use :func:`probooksai.statement_pdf.extract_text_from_pdf`
  and :func:`probooksai.statement_extract.parse_statement_text`.
- **Scanned PDFs / photos:** still need a vision model, credentials, and the Chase
  sample from GitHub Issue #11 for an acceptance test.
"""

from __future__ import annotations

from dataclasses import dataclass

# Re-export for callers that still import this module
from probooksai.statement_extract import parse_statement_text
from probooksai.statement_pdf import extract_text_from_pdf

# Machine-readable code when ``status`` is :attr:`StatementScanStatus.NOT_IMPLEMENTED`.
OCR_NOT_IMPLEMENTED = "ocr_not_implemented"


class StatementScanStatus:
    """Stable ``status`` strings for :class:`StatementScanExtractionResult` (API contract)."""

    OK: str = "ok"
    NOT_IMPLEMENTED: str = "not_implemented"
    FAILED: str = "failed"


@dataclass(frozen=True)
class StatementScanExtractionResult:
    """Structured result from :func:`extract_rows_from_statement_scan`.

    ``status`` is one of :class:`StatementScanStatus` attributes.
    Row dicts match :func:`probooksai.statement_extract.parse_statement_text` outputs:
    ``txn_date``, ``description``, ``amount``, ``ref_number``.

    When ``status`` is ``NOT_IMPLEMENTED`` or ``FAILED``, ``rows`` is typically empty.
    ``error`` holds a short machine-oriented code; ``detail`` is optional UI copy.
    """

    status: str
    rows: list[dict[str, object]]
    error: str | None = None
    detail: str | None = None


def extract_rows_from_statement_scan(
    path: str,
    *,
    mime_type: str | None = None,
) -> StatementScanExtractionResult:
    """Stable OCR/vision entrypoint for scanned statements (PDF image pages or photos).

    *mime_type* is reserved for routing (e.g. ``image/jpeg``).

    **Current behavior:** returns a structured :attr:`StatementScanStatus.NOT_IMPLEMENTED`
    result—no network calls and no OCR engine. A future implementation will set
    ``status=StatementScanStatus.OK``, fill ``rows``, and leave ``error``/``detail`` clear
    on success.
    """
    _ = path, mime_type
    return StatementScanExtractionResult(
        status=StatementScanStatus.NOT_IMPLEMENTED,
        rows=[],
        error=OCR_NOT_IMPLEMENTED,
        detail="Vision/OCR extraction is not enabled in this build (Phase 7).",
    )


__all__ = [
    "OCR_NOT_IMPLEMENTED",
    "StatementScanExtractionResult",
    "StatementScanStatus",
    "extract_rows_from_statement_scan",
    "extract_text_from_pdf",
    "parse_statement_text",
]
