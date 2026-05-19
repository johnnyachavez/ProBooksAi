"""
Bank statement PDF AI extraction.

- **Digital PDFs (text layer):** :func:`probooksai.statement_pdf.extract_text_from_pdf`
  + :func:`probooksai.statement_extract.parse_statement_text` (regex, no API cost).
- **Scanned PDFs / image-only PDFs:** :func:`extract_rows_from_statement_scan` sends the
  PDF to Claude via the Anthropic PDF-vision beta API.  Requires ``ANTHROPIC_API_KEY`` in
  the environment (set in your ``.env`` file).  Falls back to OpenAI vision if
  ``OPENAI_API_KEY`` is set instead.

The returned rows match the CSV import row shape so the same import path handles both.
"""

from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass

# Re-export for callers that still import this module
from probooksai.statement_extract import parse_statement_text
from probooksai.statement_pdf import extract_text_from_pdf

# Machine-readable code when ``status`` is :attr:`StatementScanStatus.NOT_IMPLEMENTED`.
OCR_NOT_IMPLEMENTED = "ocr_not_implemented"

_EXTRACT_PROMPT = """You are a bank statement parser.  Extract ONLY debit/withdrawal/payment transactions from this bank statement PDF.
DO NOT include deposits, credits, or incoming transfers — those are entered manually in this system.

Return ONLY a valid JSON array — no markdown fences, no commentary, no extra keys.

Each element must have exactly these fields:
  "txn_date"   – transaction date in YYYY-MM-DD format (use the transaction date, not posting date)
  "description"– payee name or transaction description (string, never empty)
  "amount"     – NEGATIVE number for every debit/withdrawal/payment/fee/check
  "ref_number" – check number or reference if shown, else ""

Rules:
- Include ONLY withdrawals, payments, debits, fees, and checks (outgoing money).
- SKIP all deposits, credits, and incoming transfers.
- Do NOT include header rows, running-balance lines, or opening/closing-balance summary rows.
- If the statement has separate Debit and Credit columns, only include rows that have a Debit amount.
- Strip trailing/leading whitespace from description.
- Use standard YYYY-MM-DD dates — convert MM/DD/YYYY or MM-DD-YYYY automatically.

Output example (do not copy this; extract the real transactions):
[
  {"txn_date":"2024-03-01","description":"WALMART SUPERCENTER","amount":-87.34,"ref_number":""},
  {"txn_date":"2024-03-05","description":"ACH PAYMENT VENDOR NAME","amount":-1250.00,"ref_number":"1042"}
]"""


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_fences(text: str) -> str:
    """Remove markdown ``` fences Claude sometimes wraps around JSON."""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t)
    return t.strip()


def _parse_ai_json(raw: str) -> list[dict]:
    """Parse Claude/OpenAI JSON response into validated row dicts.

    Deposits (amount >= 0) are silently dropped — they must be entered
    manually so they can be matched to invoices / received payments.
    """
    parsed = json.loads(_strip_fences(raw))
    if not isinstance(parsed, list):
        raise ValueError("AI response is not a JSON array")
    rows: list[dict] = []
    for item in parsed:
        date_val = str(item.get("txn_date", "")).strip()
        if not date_val:
            continue
        # Normalise MM/DD/YYYY or MM-DD-YYYY → YYYY-MM-DD
        m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", date_val)
        if m:
            date_val = f"{m.group(3)}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"
        amount = float(item.get("amount", 0.0))
        if amount >= 0:
            continue  # skip deposits / credits — entered manually
        rows.append({
            "txn_date":    date_val,
            "description": str(item.get("description", "Transaction")).strip() or "Transaction",
            "amount":      amount,
            "ref_number":  str(item.get("ref_number", "") or ""),
        })
    return rows


# ---------------------------------------------------------------------------
# Anthropic (Claude) extraction
# ---------------------------------------------------------------------------

def _extract_anthropic(path: str) -> list[dict]:
    """Send the PDF to Claude using the native PDF-vision beta and return parsed rows."""
    import anthropic  # type: ignore[import]

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    with open(path, "rb") as fh:
        pdf_data = base64.standard_b64encode(fh.read()).decode()

    client = anthropic.Anthropic(api_key=api_key)
    response = client.beta.messages.create(
        model=model,
        max_tokens=8192,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_data,
                        },
                    },
                    {"type": "text", "text": _EXTRACT_PROMPT},
                ],
            }
        ],
        betas=["pdfs-2024-09-25"],
    )
    raw = response.content[0].text
    return _parse_ai_json(raw)


# ---------------------------------------------------------------------------
# OpenAI fallback (text-layer only — OpenAI doesn't support PDF natively)
# ---------------------------------------------------------------------------

def _extract_openai_text(path: str) -> list[dict]:
    """Extract text from PDF then ask GPT to parse it (digital PDFs only)."""
    import openai  # type: ignore[import]

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    text = extract_text_from_pdf(path)
    if not text.strip():
        raise RuntimeError("No text layer found in PDF — use Claude (ANTHROPIC_API_KEY) for scanned statements")

    model = os.environ.get("OPENAI_MODEL", "gpt-4o")
    client = openai.OpenAI(api_key=api_key, base_url=os.environ.get("AI_BASE_URL") or None)
    resp = client.chat.completions.create(
        model=model,
        max_tokens=8192,
        messages=[
            {"role": "system", "content": _EXTRACT_PROMPT},
            {"role": "user", "content": text[:60_000]},  # stay within context
        ],
    )
    raw = resp.choices[0].message.content or ""
    return _parse_ai_json(raw)


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def extract_rows_from_statement_scan(
    path: str,
    *,
    mime_type: str | None = None,
) -> StatementScanExtractionResult:
    """AI-powered extraction for PDFs (scanned or digital) and images.

    Tries Anthropic Claude first (native PDF vision), then OpenAI (text-layer only).
    Returns :attr:`StatementScanStatus.NOT_IMPLEMENTED` when no API key is configured,
    or :attr:`StatementScanStatus.FAILED` on any extraction error.
    """
    _ = mime_type

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    openai_key    = os.environ.get("OPENAI_API_KEY", "")

    if not anthropic_key and not openai_key:
        return StatementScanExtractionResult(
            status=StatementScanStatus.NOT_IMPLEMENTED,
            rows=[],
            error=OCR_NOT_IMPLEMENTED,
            detail=(
                "No AI API key found.  Add ANTHROPIC_API_KEY (recommended) or "
                "OPENAI_API_KEY to your .env file to enable AI PDF extraction."
            ),
        )

    try:
        if anthropic_key:
            rows = _extract_anthropic(path)
        else:
            rows = _extract_openai_text(path)

        return StatementScanExtractionResult(
            status=StatementScanStatus.OK,
            rows=rows,
        )

    except Exception as exc:
        return StatementScanExtractionResult(
            status=StatementScanStatus.FAILED,
            rows=[],
            error="ai_extraction_failed",
            detail=str(exc),
        )


__all__ = [
    "OCR_NOT_IMPLEMENTED",
    "StatementScanExtractionResult",
    "StatementScanStatus",
    "extract_rows_from_statement_scan",
    "extract_text_from_pdf",
    "parse_statement_text",
]
