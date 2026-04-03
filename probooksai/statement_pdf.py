"""
Phase 7 – Extract text from digital PDF bank statements (text layer only).

Requires ``pypdf``. Scanned PDFs still need a vision/OCR pipeline (Issue #9 / #11).
"""

from __future__ import annotations


def extract_text_from_pdf(path: str) -> str:
    """
    Return concatenated page text from *path*.

    Raises ``ImportError`` if ``pypdf`` is not installed.
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ImportError(
            "PDF text extraction needs pypdf. Install with: pip install pypdf"
        ) from exc

    reader = PdfReader(path)
    parts: list[str] = []
    for page in reader.pages:
        t = page.extract_text()
        if t:
            parts.append(t)
    return "\n".join(parts)
