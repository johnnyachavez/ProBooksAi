"""probooks.paths default data dir name (documented in README vs desktop get_data_dir)."""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_PATHS = _REPO / "probooks" / "paths.py"


def test_probooks_paths_use_branded_app_dir_and_cli_db_name() -> None:
    text = _PATHS.read_text(encoding="utf-8")
    assert '_APP_DIR_NAME = "ProBooks+ai"' in text
    assert '_DB_NAME = "probooks.db"' in text
    assert "ProBooks+ai" in text
