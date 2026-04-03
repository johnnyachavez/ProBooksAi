"""Shared pytest fixtures.

``isolated_branded_app_data_env`` points Windows ``LOCALAPPDATA`` / ``APPDATA`` (or Unix
``HOME``) at a temp tree so ``probooks.paths`` and ``probooksai.database.get_data_dir``
tests do not touch the developer's real app data.

Repository path constants for source-only contract tests live in ``tests/repo_paths.py``.
"""

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
