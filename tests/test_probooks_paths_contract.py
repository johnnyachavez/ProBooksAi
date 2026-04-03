"""probooks.paths default data dir name (documented in README vs desktop get_data_dir)."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_PATHS = _REPO / "probooks" / "paths.py"


def test_probooks_paths_use_branded_app_dir_and_cli_db_name() -> None:
    text = _PATHS.read_text(encoding="utf-8")
    assert '_APP_DIR_NAME = "ProBooks+ai"' in text
    assert '_DB_NAME = "probooks.db"' in text
    assert 'INTAKE_DB_NAME = "probooksai.db"' in text
    assert "def default_intake_db_path()" in text
    assert "ProBooks+ai" in text


def test_default_intake_db_path_matches_app_dir_and_intake_name(tmp_path, monkeypatch) -> None:
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

    from probooks.paths import INTAKE_DB_NAME, app_data_dir, default_intake_db_path

    assert default_intake_db_path() == app_data_dir() / INTAKE_DB_NAME
