"""Shared pytest fixtures."""

from __future__ import annotations

import sys

import pytest


@pytest.fixture
def isolated_branded_app_data_env(tmp_path, monkeypatch) -> None:
    """Isolate ProBooks+ai dirs under tmp_path (Windows LOCALAPPDATA + APPDATA, else HOME)."""
    if sys.platform == "win32":
        local = tmp_path / "Local"
        roaming = tmp_path / "Roaming"
        local.mkdir()
        roaming.mkdir()
        monkeypatch.setenv("LOCALAPPDATA", str(local))
        monkeypatch.setenv("APPDATA", str(roaming))
    else:
        monkeypatch.delenv("APPDATA", raising=False)
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
