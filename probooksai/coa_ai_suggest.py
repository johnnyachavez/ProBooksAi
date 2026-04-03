"""
Phase 6 – optional cloud AI hints for COA categorisation.

When ``OPENAI_API_KEY`` is not set, all functions return empty lists so the UI
can rely on rules-only hints. Vision / full OCR for bank statements lives in
Phase 7 (see ``statement_pdf`` / future vision integration).
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Optional


def ai_top_coa_suggestions(
    description: str,
    coa_labels: list[str],
    *,
    max_n: int = 3,
    model: str = "gpt-4o-mini",
) -> list[str]:
    """
    Ask the OpenAI API for up to *max_n* COA labels from *coa_labels* that best
    match *description*. Returns ``[]`` if the key is missing, labels are empty,
    or the request fails.
    """
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key or not (description or "").strip() or not coa_labels or max_n < 1:
        return []

    labels = [x.strip() for x in coa_labels if x and str(x).strip()]
    if not labels:
        return []

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You help bookkeepers pick a chart-of-accounts label. "
                    "Reply with JSON only: {\"picks\": [\"exact label 1\", ...]} "
                    "using only strings from the provided list, best match first, "
                    f"at most {max_n} items."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"transaction_description": description.strip(), "coa_labels": labels},
                    ensure_ascii=False,
                ),
            },
        ],
        "temperature": 0.2,
        "max_tokens": 200,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError):
        return []

    try:
        text = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return []

    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
        picks = data.get("picks") if isinstance(data, dict) else None
        if not isinstance(picks, list):
            return []
        label_set = set(labels)
        out: list[str] = []
        for p in picks:
            if not isinstance(p, str):
                continue
            s = p.strip()
            if s in label_set and s not in out:
                out.append(s)
            if len(out) >= max_n:
                break
        return out
    except json.JSONDecodeError:
        return []


def coa_hints(
    conn,
    description: str,
    coa_labels: list[str],
    *,
    limit: int = 3,
) -> list[str]:
    """Combine rule-based matches (Phase 6) with optional AI picks."""
    from probooksai.rules_engine import suggest_coa_matches

    out: list[str] = []
    seen: set[str] = set()
    for s in suggest_coa_matches(conn, description, limit=limit):
        if s not in seen:
            seen.add(s)
            out.append(s)
    if len(out) < limit:
        need = limit - len(out)
        for s in ai_top_coa_suggestions(description, coa_labels, max_n=need):
            if s not in seen:
                seen.add(s)
                out.append(s)
    return out[:limit]
