"""Tests for the **AI** sub-tab on the Business hub.

The AI Settings tab is the only user-facing place to:

* Toggle ``ai_intake_enabled`` (off by default).
* Provide an OpenAI API key + optional model / endpoint / timeout
  overrides — all stored in the open company .db.

Locks:

* The Business hub exposes the tab as the rightmost sub-tab titled
  ``"AI"``.
* Initial widget values are loaded from existing settings.
* ``Save AI settings`` persists every field to ``company_settings``.
* The toggle is stored as ``"1"`` / ``"0"`` (matches the panel-side
  ``_effective_ai_provider`` boolean coercion).
* Empty model / endpoint / timeout fields are saved as empty strings
  so the provider falls back to its built-in defaults.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication, QCheckBox, QLineEdit, QPushButton

from probooksai import business
from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import apply_extensions

from desktop_app.extra_tabs import AISettingsTab, BusinessHub


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _open_db(tmp_path) -> BankDatabase:
    db = BankDatabase(str(tmp_path / "ai_settings.db"))
    apply_extensions(db._conn)
    return db


# ---------------------------------------------------------------------------
# Hub wiring
# ---------------------------------------------------------------------------


def test_business_hub_includes_ai_subtab(qapp: QApplication, tmp_path: Path) -> None:
    db = _open_db(tmp_path)
    try:
        hub = BusinessHub(db._conn)
        bar = hub._business_subtabs
        # "AI" must be the last sub-tab so existing saved-index
        # behaviour (Rules=0, Payroll=1, Tax=2) is unaffected.
        assert bar.count() == 4
        assert bar.tabText(3) == "AI"
        assert isinstance(bar.widget(3), AISettingsTab)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Initial values
# ---------------------------------------------------------------------------


def test_initial_values_load_from_company_settings(qapp: QApplication, tmp_path: Path) -> None:
    db = _open_db(tmp_path)
    try:
        business.set_setting(db._conn, "ai_intake_enabled", "1")
        business.set_setting(db._conn, "openai_api_key", "sk-existing")
        business.set_setting(db._conn, "openai_ai_model", "gpt-4o")
        business.set_setting(db._conn, "openai_ai_endpoint", "https://example.test/v1/chat")
        business.set_setting(db._conn, "openai_ai_timeout_sec", "15")
        tab = AISettingsTab(db._conn)
        assert tab._enabled_chk.isChecked() is True
        assert tab._key_edit.text() == "sk-existing"
        assert tab._model_edit.text() == "gpt-4o"
        assert tab._endpoint_edit.text() == "https://example.test/v1/chat"
        assert tab._timeout_edit.text() == "15"
    finally:
        db.close()


def test_initial_values_default_to_unchecked_and_empty(qapp: QApplication, tmp_path: Path) -> None:
    db = _open_db(tmp_path)
    try:
        tab = AISettingsTab(db._conn)
        assert tab._enabled_chk.isChecked() is False
        assert tab._key_edit.text() == ""
        assert tab._model_edit.text() == ""
        assert tab._endpoint_edit.text() == ""
        assert tab._timeout_edit.text() == ""
    finally:
        db.close()


def test_api_key_input_uses_password_echo(qapp: QApplication, tmp_path: Path) -> None:
    """API key field must mask input so the key isn't shoulder-surfed."""
    db = _open_db(tmp_path)
    try:
        tab = AISettingsTab(db._conn)
        assert tab._key_edit.echoMode() == QLineEdit.EchoMode.Password
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Save behavior
# ---------------------------------------------------------------------------


def test_save_persists_all_fields_to_company_settings(qapp: QApplication, tmp_path: Path) -> None:
    db = _open_db(tmp_path)
    try:
        tab = AISettingsTab(db._conn)
        tab._enabled_chk.setChecked(True)
        tab._key_edit.setText("  sk-new  ")
        tab._model_edit.setText("gpt-4.1-mini")
        tab._endpoint_edit.setText("https://gateway.local/chat")
        tab._timeout_edit.setText("12")
        with patch("desktop_app.extra_tabs.message_box_information_ok") as mock_box:
            tab._save()
        # Whitespace is trimmed on save so an accidental trailing space
        # in the key doesn't break the Authorization header.
        assert business.get_setting(db._conn, "openai_api_key") == "sk-new"
        assert business.get_setting(db._conn, "openai_ai_model") == "gpt-4.1-mini"
        assert business.get_setting(db._conn, "openai_ai_endpoint") == "https://gateway.local/chat"
        assert business.get_setting(db._conn, "openai_ai_timeout_sec") == "12"
        assert business.get_setting(db._conn, "ai_intake_enabled") == "1"
        mock_box.assert_called_once()
    finally:
        db.close()


def test_save_with_unchecked_toggle_writes_zero(qapp: QApplication, tmp_path: Path) -> None:
    db = _open_db(tmp_path)
    try:
        # Pre-existing on-state so we prove the save *clears* it.
        business.set_setting(db._conn, "ai_intake_enabled", "1")
        tab = AISettingsTab(db._conn)
        tab._enabled_chk.setChecked(False)
        with patch("desktop_app.extra_tabs.message_box_information_ok"):
            tab._save()
        assert business.get_setting(db._conn, "ai_intake_enabled") == "0"
    finally:
        db.close()


def test_blank_model_endpoint_and_timeout_are_saved_as_empty(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Blank fields mean "use built-in default" — the provider already
    falls back to ``DEFAULT_MODEL`` / ``DEFAULT_ENDPOINT`` /
    ``DEFAULT_TIMEOUT_SEC`` when reading an empty setting, so saving
    blanks is the way to *clear* a previous override."""
    db = _open_db(tmp_path)
    try:
        business.set_setting(db._conn, "openai_ai_model", "old-model")
        business.set_setting(db._conn, "openai_ai_endpoint", "https://old.test/v1")
        business.set_setting(db._conn, "openai_ai_timeout_sec", "30")
        tab = AISettingsTab(db._conn)
        # Verify they loaded so the test exercises the "clear" path.
        assert tab._model_edit.text() == "old-model"
        tab._model_edit.setText("")
        tab._endpoint_edit.setText("")
        tab._timeout_edit.setText("")
        with patch("desktop_app.extra_tabs.message_box_information_ok"):
            tab._save()
        assert business.get_setting(db._conn, "openai_ai_model") == ""
        assert business.get_setting(db._conn, "openai_ai_endpoint") == ""
        assert business.get_setting(db._conn, "openai_ai_timeout_sec") == ""
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Settings keys agree with provider
# ---------------------------------------------------------------------------


def test_setting_keys_match_provider_module_constants() -> None:
    """The tab and the provider must spell setting keys the same way."""
    from probooksai.bank_statement_intake_ai_provider import (
        SETTING_API_KEY,
        SETTING_ENABLED,
        SETTING_ENDPOINT,
        SETTING_MODEL,
        SETTING_TIMEOUT,
    )

    assert AISettingsTab.SETTING_API_KEY == SETTING_API_KEY
    assert AISettingsTab.SETTING_MODEL == SETTING_MODEL
    assert AISettingsTab.SETTING_ENDPOINT == SETTING_ENDPOINT
    assert AISettingsTab.SETTING_TIMEOUT == SETTING_TIMEOUT
    assert AISettingsTab.SETTING_ENABLED == SETTING_ENABLED


# ---------------------------------------------------------------------------
# End-to-end: setting saved here flows into the OpenAI provider
# ---------------------------------------------------------------------------


def test_saved_settings_drive_openai_provider_request(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Round-trip: a key entered in the UI ends up on the next
    request the OpenAIProvider makes for this company connection."""
    from probooksai.bank_statement_intake_ai_provider import OpenAIProvider
    from probooksai.coa_db import COADatabase

    db = _open_db(tmp_path)
    try:
        COADatabase(db._conn).add_account("5400", "Office Supplies", "expense")

        tab = AISettingsTab(db._conn)
        tab._enabled_chk.setChecked(True)
        tab._key_edit.setText("sk-from-ui")
        with patch("desktop_app.extra_tabs.message_box_information_ok"):
            tab._save()

        recorded: dict = {}

        def fake_post(url, headers, body, timeout):
            recorded["headers"] = dict(headers)
            return (
                '{"choices": [{"message": {"content": '
                '"{\\"coa\\": null}"}}]}'
            )

        prov = OpenAIProvider(db._conn, http_poster=fake_post)
        prov("anything", "anything")
        assert recorded["headers"]["Authorization"] == "Bearer sk-from-ui"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Polished UI bits
# ---------------------------------------------------------------------------


def test_save_button_exists_and_has_tooltip(qapp: QApplication, tmp_path: Path) -> None:
    db = _open_db(tmp_path)
    try:
        tab = AISettingsTab(db._conn)
        # Find the "Save AI settings" button.
        buttons = tab.findChildren(QPushButton)
        save_btn = next(
            (b for b in buttons if b.text() == "Save AI settings"), None
        )
        assert save_btn is not None
        assert save_btn.toolTip()
    finally:
        db.close()


def test_enabled_checkbox_has_tooltip(qapp: QApplication, tmp_path: Path) -> None:
    db = _open_db(tmp_path)
    try:
        tab = AISettingsTab(db._conn)
        chk = tab.findChild(QCheckBox)
        assert chk is not None
        assert chk.toolTip()
    finally:
        db.close()
