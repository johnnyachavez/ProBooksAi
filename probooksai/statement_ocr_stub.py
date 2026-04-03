"""
Phase 7 – Bank statement PDF / image intake.

- **Digital PDFs (text layer):** use :func:`probooksai.statement_pdf.extract_text_from_pdf`
  and :func:`probooksai.statement_extract.parse_statement_text`.
- **Scanned PDFs / photos:** still need a vision model, credentials, and the Chase
  sample from GitHub Issue #11 for an acceptance test.
"""

from __future__ import annotations

# Re-export for callers that still import this module
from probooksai.statement_extract import parse_statement_text
from probooksai.statement_pdf import extract_text_from_pdf

__all__ = ["extract_text_from_pdf", "parse_statement_text"]
