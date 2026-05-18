"""
ai.extractor
============
Cloud-API-driven document extraction for ProBooks+ai.

Environment variables
---------------------
AI_PROVIDER         – Cloud provider to use.  Default: ``openai``
                      Supported: ``openai``, ``anthropic``
OPENAI_API_KEY      – API key for the OpenAI (or compatible) provider.
OPENAI_MODEL        – Model name.  Default: ``gpt-4o``
AI_BASE_URL         – Optional: override the OpenAI base URL (e.g. Azure, Ollama).
ANTHROPIC_API_KEY   – API key for the Anthropic (Claude) provider.
ANTHROPIC_MODEL     – Claude model name.  Default: ``claude-sonnet-4-6``

Usage
-----
::

    from ai.extractor import extract_document

    result = extract_document("invoice.pdf", "application/pdf")
    print(result.vendor, result.total)
"""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Optional

from ai import ExtractionResult

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_EXTRACTION_SCHEMA = {
    "vendor": "string or null",
    "doc_type": "one of: invoice, bill, receipt, credit_note, other",
    "invoice_number": "string or null",
    "doc_date": "ISO date YYYY-MM-DD or null",
    "due_date": "ISO date YYYY-MM-DD or null",
    "subtotal": "number or null",
    "tax": "number or null",
    "total": "number or null",
    "currency": "3-letter ISO currency code, default USD",
    "notes": "any additional remarks or null",
    "line_items": [
        {
            "description": "string",
            "qty": "number or null",
            "unit_price": "number or null",
            "amount": "number or null",
        }
    ],
    "confidence": "float 0.0–1.0 indicating extraction confidence",
}

_SYSTEM_PROMPT = (
    "You are a professional accounting assistant. "
    "Extract structured data from the provided document and return ONLY valid JSON "
    "matching the schema below. Do not include markdown fences or explanations.\n\n"
    f"Schema:\n{json.dumps(_EXTRACTION_SCHEMA, indent=2)}"
)


def _pdf_to_text(path: str) -> str:
    """Extract plain text from a PDF using pypdf."""
    from pypdf import PdfReader

    reader = PdfReader(path)
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text)
    return "\n\n--- Page Break ---\n\n".join(pages)


def _image_to_data_url(path: str) -> str:
    """Encode an image file as a base64 data URL."""
    ext = Path(path).suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    mime = mime_map.get(ext, "image/jpeg")
    with open(path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode()
    return f"data:{mime};base64,{b64}"


def _parse_response(raw: str) -> dict:
    """Parse the raw JSON string from the AI response."""
    raw = raw.strip()
    # Strip markdown fences if the model added them despite instructions
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(raw)


def _call_openai(messages: list[dict]) -> str:
    """Call the OpenAI (or compatible) chat completion API and return the content string."""
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "The 'openai' package is required for AI extraction. "
            "Install it with: pip install openai"
        ) from exc

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY environment variable is not set. "
            "Set it to your OpenAI API key before using AI extraction."
        )

    base_url: Optional[str] = os.environ.get("AI_BASE_URL")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o")

    kwargs: dict = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url

    client = OpenAI(**kwargs)
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0,
        max_tokens=2048,
    )
    return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Anthropic (Claude) caller
# ---------------------------------------------------------------------------

_ANTHROPIC_IMAGE_MIMES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def _call_anthropic(path: str, mimetype: str) -> str:
    """Call the Anthropic Claude API for document extraction and return the JSON string.

    Uses native PDF vision for PDFs (no text pre-extraction needed) and standard
    image vision for JPG/PNG/WEBP. Requires ANTHROPIC_API_KEY in the environment.
    """
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError(
            "The 'anthropic' package is required for Claude extraction. "
            "Install it with: pip install anthropic"
        ) from exc

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY environment variable is not set. "
            "Get a key at console.anthropic.com, then set ANTHROPIC_API_KEY."
        )

    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    client = anthropic.Anthropic(api_key=api_key)

    with open(path, "rb") as fh:
        raw = fh.read()
    b64 = base64.b64encode(raw).decode()

    user_text = (
        f"Extract structured accounting data from this document. "
        f"Return ONLY valid JSON matching this schema:\n\n{json.dumps(_EXTRACTION_SCHEMA, indent=2)}"
    )

    if mimetype == "application/pdf":
        content: list = [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": b64,
                },
            },
            {"type": "text", "text": user_text},
        ]
        msg = client.beta.messages.create(
            model=model,
            max_tokens=2048,
            betas=["pdfs-2024-09-25"],
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
    else:
        ext = Path(path).suffix.lower()
        actual_mime = _ANTHROPIC_IMAGE_MIMES.get(ext, "image/jpeg")
        content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": actual_mime,
                    "data": b64,
                },
            },
            {"type": "text", "text": user_text},
        ]
        msg = client.messages.create(
            model=model,
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )

    return msg.content[0].text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_document(path: str, mimetype: str) -> ExtractionResult:
    """
    Extract structured accounting fields from a document using a cloud AI.

    Parameters
    ----------
    path:
        Absolute path to the document file.
    mimetype:
        MIME type, e.g. ``'application/pdf'``, ``'image/jpeg'``.

    Returns
    -------
    ExtractionResult
        Populated dataclass; ``error`` is set (and other fields may be None)
        if the extraction fails.
    """
    provider = os.environ.get("AI_PROVIDER", "openai").lower()

    try:
        if provider == "anthropic":
            if mimetype != "application/pdf" and not mimetype.startswith("image/"):
                return ExtractionResult(error=f"Unsupported MIME type: {mimetype!r}")
            raw = _call_anthropic(path, mimetype)
        elif provider == "openai":
            if mimetype == "application/pdf":
                text = _pdf_to_text(path)
                if text.strip():
                    messages = [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": f"Extract data from this document:\n\n{text}"},
                    ]
                else:
                    messages = _messages_for_scanned_pdf(path)
            elif mimetype.startswith("image/"):
                data_url = _image_to_data_url(path)
                messages = [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Extract data from this document image:"},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    },
                ]
            else:
                return ExtractionResult(error=f"Unsupported MIME type: {mimetype!r}")
            raw = _call_openai(messages)
        else:
            return ExtractionResult(
                error=f"Unsupported AI_PROVIDER: {provider!r}. Set AI_PROVIDER to 'anthropic' or 'openai'."
            )

        data = _parse_response(raw)

        return ExtractionResult(
            vendor=data.get("vendor"),
            doc_type=data.get("doc_type"),
            invoice_number=data.get("invoice_number"),
            doc_date=data.get("doc_date"),
            due_date=data.get("due_date"),
            subtotal=_to_float(data.get("subtotal")),
            tax=_to_float(data.get("tax")),
            total=_to_float(data.get("total")),
            currency=data.get("currency") or "USD",
            notes=data.get("notes"),
            line_items=data.get("line_items") or [],
            confidence=_to_float(data.get("confidence")) or 0.0,
            raw_response=raw,
        )

    except Exception as exc:  # noqa: BLE001
        log.debug("extract_document failed: %s", exc, exc_info=True)
        return ExtractionResult(error=str(exc))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _messages_for_scanned_pdf(path: str) -> list[dict]:
    """
    For scanned PDFs, attempt to render the first page as an image using
    Pillow + pypdf's page-rendering (if available), falling back to a text
    prompt asking the user to provide a text copy.
    """
    # Try rendering page 0 with pypdf (requires pypdf[image] optional dep)
    try:
        from pypdf import PdfReader

        reader = PdfReader(path)
        page = reader.pages[0]
        # pypdf can extract images embedded in a page
        images = page.images
        if images:
            img_data = images[0].data
            b64 = base64.b64encode(img_data).decode()
            # Detect image type from SOI (Start of Image) marker: JPEG is \xff\xd8, else assume PNG
            mime = "image/jpeg" if img_data[:2] == b"\xff\xd8" else "image/png"
            data_url = f"data:{mime};base64,{b64}"
            return [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract data from this scanned document image:"},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ]
    except Exception:
        pass

    # Fallback: inform the model it's a scanned PDF with no extractable text
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "This is a scanned PDF document with no extractable text. "
                "Please return a JSON object with all fields set to null and "
                "confidence set to 0.0, and include a note explaining that "
                "the document appears to be a scanned image without OCR text."
            ),
        },
    ]
