"""
AI extraction placeholder module.

This module provides an interface for future AI-powered extraction of
structured data (invoices, payables) from uploaded documents such as PDFs.

No external AI service is integrated yet. Replace the stub below with a
real implementation once an AI provider is chosen (e.g. OpenAI, Google
Document AI, AWS Textract).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def extract(file_path: str | Path) -> dict[str, Any]:
    """Extract structured accounting data from an uploaded document.

    Args:
        file_path: Absolute or relative path to the uploaded file (PDF, etc.)

    Returns:
        A dictionary with extracted fields.  Currently returns a placeholder
        result; replace the body of this function with a real AI call.

    Example return value::

        {
            "vendor": "Acme Corp",
            "invoice_number": "INV-001",
            "date": "2026-03-30",
            "total": 1250.00,
            "line_items": [
                {"description": "Consulting", "amount": 1250.00}
            ],
            "confidence": 0.0,   # 0.0 = not extracted; 1.0 = fully extracted
        }
    """
    return {
        "vendor": None,
        "invoice_number": None,
        "date": None,
        "total": None,
        "line_items": [],
        "confidence": 0.0,
        "note": "AI extraction not yet implemented. Replace this stub.",
    }
