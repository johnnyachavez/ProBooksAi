"""Extract plain text from PDF/image paths for Invoice Intake (review + memo handoff).

- **PDF:** reuses :func:`probooksai.statement_pdf.extract_text_from_pdf` (text layer only).
- **Image:** optional ``pytesseract`` + system Tesseract when available; otherwise no text (no guess).

Returns raw strings only; structured fields use :func:`desktop_app.invoice_intake_text_extract.extract_text_intake_fields`.
"""

from __future__ import annotations

import os


def extract_text_from_intake_pdf(path: str) -> tuple[str, str | None]:
    """Return ``(raw_text, note)``. *note* is user-facing when text is empty or partial."""
    try:
        from probooksai.statement_pdf import extract_text_from_pdf
    except ImportError:
        return (
            "",
            "PDF text extraction unavailable (pypdf not installed in this environment).",
        )
    if not path or not os.path.isfile(path):
        return "", "File not found or not readable."
    try:
        text = extract_text_from_pdf(path)
    except OSError as exc:
        return "", f"Could not read PDF: {exc}"
    except Exception as exc:  # noqa: BLE001 — show short message in review panel
        return "", f"PDF extraction failed: {exc}"
    raw = (text or "").strip()
    if not raw:
        return (
            "",
            "No text layer in this PDF (likely scanned). Text not extracted — use a text-based PDF or OCR elsewhere.",
        )
    return text, None


def extract_text_from_intake_image(path: str) -> tuple[str, str | None]:
    """Return ``(raw_text, note)``. Without Tesseract/pytesseract, text is empty with an explanatory *note*."""
    if not path or not os.path.isfile(path):
        return "", "File not found or not readable."
    try:
        import pytesseract  # type: ignore[import-untyped]
    except ImportError:
        return (
            "",
            "Image text not extracted: pytesseract is not installed. "
            "Install pytesseract and Tesseract OCR, or paste text manually.",
        )
    try:
        from PIL import Image
    except ImportError:
        return "", "Image text not extracted: Pillow is not available."

    try:
        with Image.open(path) as img:
            text = pytesseract.image_to_string(img)
    except Exception as exc:  # noqa: BLE001
        return "", f"Image OCR failed: {exc}"
    raw = (text or "").strip()
    if not raw:
        return (
            "",
            "OCR returned no text (image may be blank or unreadable).",
        )
    return text, None


def extract_text_for_intake_kind(kind: str, path: str) -> tuple[str, str | None]:
    """Dispatch by intake *kind* (``PDF`` / ``Image``)."""
    k = (kind or "").strip().lower()
    if k == "pdf":
        return extract_text_from_intake_pdf(path)
    if k == "image":
        return extract_text_from_intake_image(path)
    return "", None
