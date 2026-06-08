"""Tests for the OpenAI-backed default AI provider for bank intake.

These tests pin:

* The provider stays silent (returns ``None``) when no API key,
  no COAs, or no description is available.
* The HTTP request shape (method, headers, JSON body, model, prompt
  containing the COA list) is correct.
* Responses are snapped against the company's chart of accounts:
  exact match wins, account-number-prefix is the secondary match,
  off-list answers are rejected, and ``"coa": null`` is honored.
* The provider is robust to malformed JSON, missing fields, network
  errors, and HTTP failures (always returning ``None`` rather than
  raising into the panel).
* Settings (model, endpoint, timeout, key) are re-read on every call
  so the AI Settings tab can change them without an app restart.
* The ``OPENAI_API_KEY`` env var is honored as a dev/CI fallback.
* :func:`build_default_ai_provider` returns ``None`` only when there's
  no DB at all — gating on the key/flag is left to the panel and the
  provider's own short-circuit.
"""

from __future__ import annotations

import json
import urllib.error
from typing import Any

import pytest

from probooksai import business
from probooksai.bank_import import BankDatabase
from probooksai.bank_statement_intake_ai_provider import (
    AI_MATCHED_PATTERN_LABEL,
    DEFAULT_ENDPOINT,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SEC,
    SETTING_API_KEY,
    SETTING_ENDPOINT,
    SETTING_MODEL,
    SETTING_TIMEOUT,
    OpenAIProvider,
    _parse_response,
    _snap_to_option,
    build_default_ai_provider,
)
from probooksai.bank_statement_intake_categorize import CategorySuggestion
from probooksai.coa_db import COADatabase
from probooksai.extensions_schema import apply_extensions


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _open_db(tmp_path) -> BankDatabase:
    db = BankDatabase(str(tmp_path / "ai.db"))
    apply_extensions(db._conn)
    return db


def _seed_coa(conn) -> list[str]:
    coa = COADatabase(conn)
    coa.add_account("5400", "Office Supplies", "expense")
    coa.add_account("5500", "Meals & Entertainment", "expense")
    coa.add_account("5800", "Bank Fees", "expense")
    return coa.display_list()


class _RecordingPoster:
    """Tiny recording HTTP poster for prompt-shape assertions."""

    def __init__(self, response: str | Exception):
        self._response = response
        self.calls: list[dict[str, Any]] = []

    def __call__(self, url, headers, body, timeout):
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "body": body,
                "timeout": timeout,
            }
        )
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _envelope(content: str) -> str:
    """OpenAI chat-completions response envelope wrapping *content*."""
    return json.dumps(
        {"choices": [{"message": {"content": content}}]}
    )


# ---------------------------------------------------------------------------
# silent-when-unconfigured
# ---------------------------------------------------------------------------


def test_provider_returns_none_when_no_api_key_anywhere(tmp_path, monkeypatch) -> None:
    """No company setting + no env var → no HTTP call, no suggestion."""
    db = _open_db(tmp_path)
    try:
        _seed_coa(db._conn)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        poster = _RecordingPoster(_envelope('{"coa": "5400 \u2013 Office Supplies"}'))
        prov = OpenAIProvider(db._conn, http_poster=poster)
        assert prov("staples #1234 ny", "staples") is None
        assert poster.calls == []  # never tried to hit the network
    finally:
        db.close()


def test_provider_returns_none_when_no_coa_options(tmp_path, monkeypatch) -> None:
    """API key present but no COAs in the company file → silent."""
    db = _open_db(tmp_path)
    try:
        business.set_setting(db._conn, SETTING_API_KEY, "sk-test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        poster = _RecordingPoster(_envelope('{"coa": null}'))
        prov = OpenAIProvider(db._conn, http_poster=poster)
        assert prov("staples", "staples") is None
        assert poster.calls == []
    finally:
        db.close()


def test_provider_returns_none_when_description_blank(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        _seed_coa(db._conn)
        business.set_setting(db._conn, SETTING_API_KEY, "sk-test")
        poster = _RecordingPoster(_envelope('{"coa": "5400 \u2013 Office Supplies"}'))
        prov = OpenAIProvider(db._conn, http_poster=poster)
        assert prov("", "") is None
        assert prov("   ", "   ") is None
        assert poster.calls == []
    finally:
        db.close()


def test_provider_uses_env_var_when_company_setting_unset(tmp_path, monkeypatch) -> None:
    db = _open_db(tmp_path)
    try:
        _seed_coa(db._conn)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
        poster = _RecordingPoster(_envelope('{"coa": "5400 \u2013 Office Supplies", "confidence": 0.7}'))
        prov = OpenAIProvider(db._conn, http_poster=poster)
        out = prov("staples", "staples")
        assert out is not None
        assert out.coa_account == "5400 \u2013 Office Supplies"
        assert poster.calls and poster.calls[0]["headers"]["Authorization"] == "Bearer sk-env"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# request shape
# ---------------------------------------------------------------------------


def test_request_uses_default_endpoint_model_and_bearer(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        _seed_coa(db._conn)
        business.set_setting(db._conn, SETTING_API_KEY, "sk-abc")
        poster = _RecordingPoster(_envelope('{"coa": null}'))
        prov = OpenAIProvider(db._conn, http_poster=poster)
        prov("walmart store", "walmart")
        assert len(poster.calls) == 1
        call = poster.calls[0]
        assert call["url"] == DEFAULT_ENDPOINT
        assert call["headers"]["Authorization"] == "Bearer sk-abc"
        assert call["headers"]["Content-Type"] == "application/json"
        assert call["timeout"] == DEFAULT_TIMEOUT_SEC
        body = json.loads(call["body"].decode("utf-8"))
        assert body["model"] == DEFAULT_MODEL
        # JSON-only and deterministic for stable suggestions.
        assert body["temperature"] == 0.0
        assert body["response_format"] == {"type": "json_object"}
        msgs = body["messages"]
        assert len(msgs) == 2 and msgs[0]["role"] == "system" and msgs[1]["role"] == "user"
        # Prompt must list the company's COAs verbatim so the model can't
        # invent off-chart accounts.
        user = msgs[1]["content"]
        assert "5400 \u2013 Office Supplies" in user
        assert "5500 \u2013 Meals & Entertainment" in user
        assert "5800 \u2013 Bank Fees" in user
        assert "walmart store" in user
    finally:
        db.close()


def test_request_honors_custom_endpoint_model_and_timeout(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        _seed_coa(db._conn)
        business.set_setting(db._conn, SETTING_API_KEY, "sk-abc")
        business.set_setting(db._conn, SETTING_MODEL, "gpt-4.1-mini")
        business.set_setting(db._conn, SETTING_ENDPOINT, "https://example.test/v1/chat")
        business.set_setting(db._conn, SETTING_TIMEOUT, "12")
        poster = _RecordingPoster(_envelope('{"coa": null}'))
        prov = OpenAIProvider(db._conn, http_poster=poster)
        prov("anything", "anything")
        call = poster.calls[0]
        assert call["url"] == "https://example.test/v1/chat"
        assert call["timeout"] == 12.0
        body = json.loads(call["body"].decode("utf-8"))
        assert body["model"] == "gpt-4.1-mini"
    finally:
        db.close()


def test_settings_changes_take_effect_without_rebuilding_provider(tmp_path) -> None:
    """Settings are re-read on each call so the AI Settings tab can update
    the model/key/timeout while the panel is open."""
    db = _open_db(tmp_path)
    try:
        _seed_coa(db._conn)
        business.set_setting(db._conn, SETTING_API_KEY, "sk-old")
        poster = _RecordingPoster(_envelope('{"coa": null}'))
        prov = OpenAIProvider(db._conn, http_poster=poster)
        prov("desc", "desc")
        business.set_setting(db._conn, SETTING_API_KEY, "sk-new")
        prov("desc", "desc")
        assert poster.calls[0]["headers"]["Authorization"] == "Bearer sk-old"
        assert poster.calls[1]["headers"]["Authorization"] == "Bearer sk-new"
    finally:
        db.close()


def test_timeout_setting_clamps_out_of_range_values(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        _seed_coa(db._conn)
        business.set_setting(db._conn, SETTING_API_KEY, "sk-abc")
        # too small
        business.set_setting(db._conn, SETTING_TIMEOUT, "0")
        p = _RecordingPoster(_envelope('{"coa": null}'))
        OpenAIProvider(db._conn, http_poster=p)("x", "x")
        assert p.calls[0]["timeout"] == 1.0
        # too large
        business.set_setting(db._conn, SETTING_TIMEOUT, "9999")
        p = _RecordingPoster(_envelope('{"coa": null}'))
        OpenAIProvider(db._conn, http_poster=p)("x", "x")
        assert p.calls[0]["timeout"] == 60.0
        # not a number → default
        business.set_setting(db._conn, SETTING_TIMEOUT, "not-a-number")
        p = _RecordingPoster(_envelope('{"coa": null}'))
        OpenAIProvider(db._conn, http_poster=p)("x", "x")
        assert p.calls[0]["timeout"] == DEFAULT_TIMEOUT_SEC
    finally:
        db.close()


# ---------------------------------------------------------------------------
# response handling
# ---------------------------------------------------------------------------


def test_exact_coa_match_returns_suggestion_with_ai_label(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        _seed_coa(db._conn)
        business.set_setting(db._conn, SETTING_API_KEY, "sk-abc")
        poster = _RecordingPoster(
            _envelope('{"coa": "5500 \u2013 Meals & Entertainment", "confidence": 0.82}')
        )
        prov = OpenAIProvider(db._conn, http_poster=poster)
        out = prov("starbucks 4567 ny", "starbucks")
        assert isinstance(out, CategorySuggestion)
        assert out.coa_account == "5500 \u2013 Meals & Entertainment"
        # AI suggestions are always tagged so the panel and any future
        # telemetry can distinguish them from rule hits.
        assert out.matched_pattern == AI_MATCHED_PATTERN_LABEL
        assert 0.0 <= out.confidence <= 1.0
        assert out.confidence == pytest.approx(0.82)
    finally:
        db.close()


def test_account_number_prefix_match_is_accepted_when_full_string_missing(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        _seed_coa(db._conn)
        business.set_setting(db._conn, SETTING_API_KEY, "sk-abc")
        # Model returned only the account number; provider snaps it
        # back to the full canonical "NNNN \u2013 Name" string.
        poster = _RecordingPoster(_envelope('{"coa": "5400", "confidence": 0.6}'))
        prov = OpenAIProvider(db._conn, http_poster=poster)
        out = prov("staples", "staples")
        assert out is not None
        assert out.coa_account == "5400 \u2013 Office Supplies"
    finally:
        db.close()


def test_off_list_coa_is_rejected_silently(tmp_path) -> None:
    """Anything the model invents that isn't in the chart of accounts
    is dropped — the register never sees an unknown COA from AI."""
    db = _open_db(tmp_path)
    try:
        _seed_coa(db._conn)
        business.set_setting(db._conn, SETTING_API_KEY, "sk-abc")
        poster = _RecordingPoster(
            _envelope('{"coa": "9999 \u2013 Made Up Account", "confidence": 0.9}')
        )
        prov = OpenAIProvider(db._conn, http_poster=poster)
        assert prov("nothing matches", "nothing") is None
    finally:
        db.close()


def test_explicit_null_coa_returns_none(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        _seed_coa(db._conn)
        business.set_setting(db._conn, SETTING_API_KEY, "sk-abc")
        poster = _RecordingPoster(_envelope('{"coa": null}'))
        prov = OpenAIProvider(db._conn, http_poster=poster)
        assert prov("ambiguous", "ambiguous") is None
    finally:
        db.close()


def test_confidence_clamped_into_unit_interval(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        _seed_coa(db._conn)
        business.set_setting(db._conn, SETTING_API_KEY, "sk-abc")
        poster = _RecordingPoster(
            _envelope('{"coa": "5400 \u2013 Office Supplies", "confidence": 7.5}')
        )
        prov = OpenAIProvider(db._conn, http_poster=poster)
        out = prov("staples", "staples")
        assert out is not None
        assert out.confidence == 1.0
    finally:
        db.close()


def test_missing_confidence_defaults_to_midrange(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        _seed_coa(db._conn)
        business.set_setting(db._conn, SETTING_API_KEY, "sk-abc")
        poster = _RecordingPoster(_envelope('{"coa": "5400 \u2013 Office Supplies"}'))
        prov = OpenAIProvider(db._conn, http_poster=poster)
        out = prov("staples", "staples")
        assert out is not None and out.confidence == 0.5
    finally:
        db.close()


def test_garbage_response_returns_none(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        _seed_coa(db._conn)
        business.set_setting(db._conn, SETTING_API_KEY, "sk-abc")
        for resp in ("not json at all", "{not even close", _envelope("also not json")):
            poster = _RecordingPoster(resp)
            prov = OpenAIProvider(db._conn, http_poster=poster)
            assert prov("staples", "staples") is None
    finally:
        db.close()


def test_network_errors_are_swallowed(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        _seed_coa(db._conn)
        business.set_setting(db._conn, SETTING_API_KEY, "sk-abc")
        for exc in (
            urllib.error.URLError("dns fail"),
            urllib.error.HTTPError("u", 500, "boom", hdrs=None, fp=None),
            TimeoutError("slow"),
            OSError("disk"),
            RuntimeError("other"),
        ):
            poster = _RecordingPoster(exc)
            prov = OpenAIProvider(db._conn, http_poster=poster)
            assert prov("staples", "staples") is None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# parsing helpers (pure, no DB)
# ---------------------------------------------------------------------------


def test_snap_to_option_is_case_insensitive() -> None:
    opts = ["5400 \u2013 Office Supplies"]
    assert _snap_to_option("5400 \u2013 office supplies", opts) == "5400 \u2013 Office Supplies"


def test_snap_to_option_returns_none_for_off_list_account_number() -> None:
    opts = ["5400 \u2013 Office Supplies"]
    assert _snap_to_option("9999", opts) is None


def test_parse_response_handles_prose_wrapped_json() -> None:
    """Some models add a sentence around the JSON. Parser should still cope."""
    opts = ["5400 \u2013 Office Supplies"]
    raw = _envelope(
        "Here is the answer:\n"
        "{\"coa\": \"5400 \u2013 Office Supplies\", \"confidence\": 0.6}"
    )
    sug = _parse_response(raw, opts)
    assert sug is not None
    assert sug.coa_account == "5400 \u2013 Office Supplies"


# ---------------------------------------------------------------------------
# build_default_ai_provider
# ---------------------------------------------------------------------------


def test_build_default_ai_provider_returns_none_for_no_conn() -> None:
    assert build_default_ai_provider(None) is None


def test_build_default_ai_provider_returns_provider_even_without_key(
    tmp_path, monkeypatch
) -> None:
    """Factory returns the provider whenever a DB is open. The provider
    itself short-circuits to ``None`` when no key is configured — that
    keeps the gating decisions in two clear places (panel flag +
    in-call key check) instead of three."""
    db = _open_db(tmp_path)
    try:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        prov = build_default_ai_provider(db._conn)
        assert prov is not None
        # And it's silent without a key:
        _seed_coa(db._conn)
        # Replace the http_poster so any accidental network call would fail loudly.
        prov._http_poster = lambda *a, **k: pytest.fail(  # type: ignore[attr-defined]
            "Provider should not call HTTP without a configured key"
        )
        assert prov("staples", "staples") is None
    finally:
        db.close()
