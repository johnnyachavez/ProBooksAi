"""Default AI provider for the Bank Statement Intake panel.

Phase 3 step 3 of bank statement intake added an opt-in AI fallback
hook on :class:`desktop_app.bank_statement_intake_panel.BankStatementIntakePanel`
via :py:meth:`~desktop_app.bank_statement_intake_panel.BankStatementIntakePanel.set_ai_provider`.
This module supplies the *default* provider implementation: a thin
OpenAI Chat-Completions client that consults the company's chart of
accounts and returns a single best-fit COA suggestion.

Design constraints (matched to the existing intake contract):

* **Review-first** — the provider returns a :class:`CategorySuggestion`
  (or ``None``); it never writes to the register, never edits a row,
  and is only ever consulted *after* the rules-engine and normalized
  rules-engine paths both miss.
* **Snap to known COAs** — the model is constrained to choose from the
  company's current chart-of-accounts via the prompt and then the
  response is *snapped* against that list (case-insensitive, with an
  account-number prefix fallback). Anything off-list is rejected
  rather than silently invented.
* **No new third-party dependency** — uses :mod:`urllib` from the
  stdlib so the desktop app doesn't pull in ``openai`` / ``requests``.
* **Test-injectable** — :class:`OpenAIProvider` accepts an
  ``http_poster`` callable so tests can simulate any HTTP outcome
  without touching the network.
* **Settings-driven** — API key, model, endpoint, and timeout are read
  from ``company_settings`` via :mod:`probooksai.business` on every
  call. This means the AI Settings tab can change them at runtime
  without rebuilding the provider. ``OPENAI_API_KEY`` is honored as a
  fallback for dev / CI smoke tests.
* **Silent on failure** — any HTTP, JSON, or schema error returns
  ``None`` so the panel falls back to "no AI suggestion" instead of
  surfacing an exception inside the review table.

The panel separately gates this provider behind the
``ai_intake_enabled`` company setting (see
``BankStatementIntakePanel._effective_ai_provider``); this module is
the *implementation* used when that flag is on.
"""

from __future__ import annotations

import json
import os
import sqlite3
import urllib.error
import urllib.request
from typing import Callable, Optional, Sequence

from probooksai import business
from probooksai.bank_statement_intake_categorize import (
    AI_MATCHED_PATTERN_LABEL,
    AIProvider,
    CategorySuggestion,
)
from probooksai.coa_db import COADatabase

# ---------------------------------------------------------------------------
# Settings keys + defaults
# ---------------------------------------------------------------------------

# Kept in a single namespace so the AI Settings tab and the provider
# never drift apart on key spelling.
SETTING_API_KEY = "openai_api_key"
SETTING_MODEL = "openai_ai_model"
SETTING_ENDPOINT = "openai_ai_endpoint"
SETTING_TIMEOUT = "openai_ai_timeout_sec"
SETTING_ENABLED = "ai_intake_enabled"

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_ENDPOINT = "https://api.openai.com/v1/chat/completions"
DEFAULT_TIMEOUT_SEC = 8.0

# Cap how many COA lines we list in the prompt so the request stays
# cheap and predictable for typical small-business charts (which top
# out around 100-200 accounts). Active accounts are favored.
_MAX_COA_OPTIONS = 200


# ---------------------------------------------------------------------------
# HTTP seam (stdlib by default; tests inject a fake)
# ---------------------------------------------------------------------------

# A poster takes (url, headers, body_bytes, timeout_sec) and returns
# the response body as text. Implementations should raise on transport
# failure; the provider wraps the call so callers see ``None`` not a
# stack trace.
HttpPoster = Callable[[str, dict, bytes, float], str]


def _default_http_poster(
    url: str,
    headers: dict,
    body: bytes,
    timeout: float,
) -> str:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    return data.decode("utf-8")


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class OpenAIProvider:
    """OpenAI Chat-Completions backed :data:`AIProvider`.

    Construct with the *open* company sqlite connection (so the
    provider can read settings + the chart of accounts). The provider
    is itself stateless beyond that connection — re-reading settings
    on every call lets the AI Settings tab change the key/model
    without an app restart.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        http_poster: Optional[HttpPoster] = None,
    ):
        self._conn = conn
        self._http_poster = http_poster or _default_http_poster

    # -- AIProvider interface -------------------------------------------------

    def __call__(
        self, description: str, normalized: str
    ) -> Optional[CategorySuggestion]:
        """Suggest a COA for *description*.

        Returns ``None`` (no suggestion) for any of:

        * No API key configured (neither company setting nor env var).
        * No COAs available in the company file.
        * Both inputs are empty/whitespace.
        * Network error, timeout, malformed JSON, or off-list answer.
        """
        api_key = self._resolve_api_key()
        if not api_key:
            return None

        coa_options = self._fetch_coa_options()
        if not coa_options:
            return None

        text = (description or "").strip() or (normalized or "").strip()
        if not text:
            return None

        model = self._resolve_setting(SETTING_MODEL, DEFAULT_MODEL)
        endpoint = self._resolve_setting(SETTING_ENDPOINT, DEFAULT_ENDPOINT)
        timeout = self._resolve_timeout()

        prompt = _build_prompt(
            description=description,
            normalized=normalized,
            coa_options=coa_options,
        )
        body = json.dumps(
            {
                "model": model,
                "temperature": 0.0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a bookkeeping classifier. Pick exactly one "
                            "chart-of-accounts entry from the supplied list. "
                            "If nothing is a clear fit, return null."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            }
        ).encode("utf-8")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            raw = self._http_poster(endpoint, headers, body, timeout)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
            return None
        except Exception:
            # Defensive: never let an exception out of the AI fallback —
            # it would surface as a row-level red banner in the panel.
            return None

        return _parse_response(raw, coa_options)

    # -- internals ------------------------------------------------------------

    def _resolve_api_key(self) -> str:
        try:
            stored = (business.get_setting(self._conn, SETTING_API_KEY, "") or "").strip()
        except sqlite3.Error:
            stored = ""
        if stored:
            return stored
        return os.environ.get("OPENAI_API_KEY", "").strip()

    def _resolve_setting(self, key: str, default: str) -> str:
        try:
            v = (business.get_setting(self._conn, key, "") or "").strip()
        except sqlite3.Error:
            v = ""
        return v or default

    def _resolve_timeout(self) -> float:
        raw = self._resolve_setting(SETTING_TIMEOUT, "")
        if not raw:
            return DEFAULT_TIMEOUT_SEC
        try:
            v = float(raw)
        except ValueError:
            return DEFAULT_TIMEOUT_SEC
        # Clamp to keep the panel responsive even on misconfiguration.
        return max(1.0, min(60.0, v))

    def _fetch_coa_options(self) -> list[str]:
        """Active COAs as ``"NNNN \u2013 Name"`` strings, capped."""
        try:
            with COADatabase(self._conn) as db:
                opts = db.display_list(include_inactive=False)
        except (sqlite3.Error, AttributeError):
            return []
        # Stable cap: keep the first N to avoid over-long prompts on
        # unusually large charts. Active list is already filtered.
        return [s for s in opts if (s or "").strip()][:_MAX_COA_OPTIONS]


# ---------------------------------------------------------------------------
# Prompt + parsing helpers
# ---------------------------------------------------------------------------


def _build_prompt(
    *,
    description: str,
    normalized: str,
    coa_options: Sequence[str],
) -> str:
    options_block = "\n".join(f"- {c}" for c in coa_options)
    desc = (description or "").strip()
    norm = (normalized or "").strip()
    return (
        "Pick the SINGLE best chart-of-accounts (COA) line for the bank "
        "transaction below. You MUST choose from the provided list "
        "verbatim. If nothing is a clear fit, set \"coa\" to null.\n\n"
        f"Transaction description: {desc!r}\n"
        f"Normalized description : {norm!r}\n\n"
        "Allowed COA options:\n"
        f"{options_block}\n\n"
        "Reply with a single JSON object on one line and nothing else:\n"
        '{"coa": "<one of the options or null>", "confidence": <0..1>}'
    )


def _parse_response(
    raw_response: str,
    coa_options: Sequence[str],
) -> Optional[CategorySuggestion]:
    """Decode an OpenAI chat-completions response into a suggestion.

    Robust against minor format drift: the outer envelope is OpenAI's
    standard ``{"choices": [{"message": {"content": ...}}]}`` shape,
    and the inner ``content`` is itself a JSON object with ``coa`` and
    ``confidence`` fields. We fish the JSON out of any prose wrapping
    by taking the first ``{`` to last ``}``.
    """
    try:
        envelope = json.loads(raw_response)
    except (json.JSONDecodeError, TypeError):
        return None
    try:
        content = envelope["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(content, str):
        return None

    payload = _extract_first_json_object(content)
    if payload is None:
        return None

    coa_raw = payload.get("coa")
    if coa_raw is None or not isinstance(coa_raw, str):
        return None
    coa_clean = coa_raw.strip()
    if not coa_clean:
        return None

    matched = _snap_to_option(coa_clean, coa_options)
    if matched is None:
        return None

    conf_raw = payload.get("confidence", 0.5)
    try:
        conf = float(conf_raw)
    except (TypeError, ValueError):
        conf = 0.5
    conf = max(0.0, min(1.0, conf))

    return CategorySuggestion(
        coa_account=matched,
        matched_pattern=AI_MATCHED_PATTERN_LABEL,
        confidence=conf,
    )


def _extract_first_json_object(text: str) -> Optional[dict]:
    s = text.find("{")
    e = text.rfind("}")
    if s == -1 or e == -1 or e < s:
        return None
    try:
        obj = json.loads(text[s : e + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _snap_to_option(candidate: str, options: Sequence[str]) -> Optional[str]:
    """Return the verbatim option string the model picked, or ``None``.

    Matching is case-insensitive on the full ``"NNNN \u2013 Name"``
    form. If the model returned only the leading account number we
    accept that too (covers terse responses) — but anything that isn't
    in *options* is rejected, which keeps invented COAs out of the
    register.
    """
    cand = (candidate or "").strip()
    if not cand:
        return None
    cl = cand.casefold()
    for o in options:
        if (o or "").casefold() == cl:
            return o
    head = cand.split()[0] if cand.split() else ""
    if head:
        for o in options:
            o_head = (o or "").split()[0] if (o or "").split() else ""
            if o_head and o_head == head:
                return o
    return None


# ---------------------------------------------------------------------------
# Public factory used by the desktop wiring
# ---------------------------------------------------------------------------


def build_default_ai_provider(
    conn: Optional[sqlite3.Connection],
    *,
    http_poster: Optional[HttpPoster] = None,
) -> Optional[AIProvider]:
    """Build the default AI provider for the open company file.

    Returns ``None`` only when there's no DB connection at all. When
    a connection is supplied we *always* return a provider — the
    provider itself short-circuits to ``None`` if no API key is
    configured, so the panel and the user-facing setting toggle can
    decide independently when AI suggestions actually appear.

    Tests can pass an ``http_poster`` callable to bypass real HTTPS.
    """
    if conn is None:
        return None
    return OpenAIProvider(conn, http_poster=http_poster)
