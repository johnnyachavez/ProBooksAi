"""
ai.categorizer
==============
Cloud-API-driven COA categorisation for ProBooks+ai.

Takes an :class:`ai.ExtractionResult` and a list of COA entries and asks the
cloud AI to suggest the best matching General Ledger account(s) and a tax
category.

Environment variables
---------------------
Same as ``ai.extractor``:  AI_PROVIDER, OPENAI_API_KEY, OPENAI_MODEL, AI_BASE_URL
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from ai import CategorySuggestions, ExtractionResult

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

_CATEGORY_SCHEMA = {
    "coa_account": "account number string (e.g. '6100') or null",
    "tax_category": "short description of the applicable tax category or null",
    "confidence": "float 0.0–1.0",
    "rationale": "brief explanation of why this account was chosen",
    "alternatives": [
        {"account": "account number string", "confidence": "float 0.0–1.0"}
    ],
}

_SYSTEM_PROMPT = (
    "You are a professional accountant. "
    "Given the extracted document fields and the company's Chart of Accounts, "
    "suggest the most appropriate General Ledger account for the document and "
    "an applicable tax category. "
    "Return ONLY valid JSON matching the schema below. No markdown, no explanation.\n\n"
    f"Schema:\n{json.dumps(_CATEGORY_SCHEMA, indent=2)}"
)


def _build_coa_summary(chart_of_accounts: list) -> str:
    """Produce a compact text representation of the COA for the prompt."""
    lines = []
    for entry in chart_of_accounts:
        if hasattr(entry, "display"):
            lines.append(f"  {entry.display} [{entry.account_type}]")
        elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
            lines.append(f"  {entry[0]} – {entry[1]}")
        else:
            lines.append(f"  {entry}")
    return "\n".join(lines)


def _extraction_summary(result: ExtractionResult) -> str:
    return (
        f"Vendor: {result.vendor}\n"
        f"Document type: {result.doc_type}\n"
        f"Invoice #: {result.invoice_number}\n"
        f"Date: {result.doc_date}\n"
        f"Total: {result.total} {result.currency}\n"
        f"Notes: {result.notes}"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def suggest_categories(
    extracted: ExtractionResult,
    chart_of_accounts: list,
) -> CategorySuggestions:
    """
    Suggest COA account and tax category for an extracted document.

    Parameters
    ----------
    extracted:
        The :class:`ai.ExtractionResult` from ``extract_document()``.
    chart_of_accounts:
        A list of COA entries.  Each item may be a :class:`probooksai.coa.COAEntry`
        or any tuple/list of ``(account_number, account_name, …)``.

    Returns
    -------
    CategorySuggestions
        Populated dataclass; ``error`` is set if the call fails.
    """
    provider = os.environ.get("AI_PROVIDER", "openai").lower()
    if provider != "openai":
        return CategorySuggestions(
            error=f"Unsupported AI_PROVIDER: {provider!r}. Only 'openai' is currently supported."
        )

    coa_text = _build_coa_summary(chart_of_accounts)
    doc_text = _extraction_summary(extracted)

    user_message = (
        f"Document fields:\n{doc_text}\n\n"
        f"Chart of Accounts:\n{coa_text}\n\n"
        "Which account best fits this document? Return JSON."
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    try:
        from ai.extractor import _call_openai, _parse_response

        raw = _call_openai(messages)
        data = _parse_response(raw)

        acct_num = data.get("coa_account")
        acct_name = _lookup_account_name(acct_num, chart_of_accounts)
        display = f"{acct_num} – {acct_name}" if acct_name else acct_num

        return CategorySuggestions(
            coa_account=display,
            coa_account_number=acct_num,
            tax_category=data.get("tax_category"),
            confidence=_to_float(data.get("confidence")) or 0.0,
            rationale=data.get("rationale"),
            alternatives=data.get("alternatives") or [],
        )

    except Exception as exc:  # noqa: BLE001
        log.debug("suggest_categories failed: %s", exc, exc_info=True)
        return CategorySuggestions(error=str(exc))


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


def _lookup_account_name(account_number: Optional[str], coa: list) -> Optional[str]:
    if not account_number:
        return None
    for entry in coa:
        if hasattr(entry, "account_number"):
            if entry.account_number == account_number:
                return entry.account_name
        elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
            if str(entry[0]) == str(account_number):
                return str(entry[1])
    return None
