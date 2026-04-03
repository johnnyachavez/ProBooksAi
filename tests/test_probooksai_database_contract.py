"""probooksai.database canonical data dir vs legacy ProBooksAi migration (README default paths)."""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_DBMOD = _REPO / "probooksai" / "database.py"


def test_probooksai_database_uses_paths_app_dir_with_legacy_migration() -> None:
    text = _DBMOD.read_text(encoding="utf-8")
    assert "ProBooks+ai" in text
    assert "def _legacy_data_dir()" in text
    assert 'return base / "ProBooksAi"' in text
    assert "app_data_dir" in text
    assert "ensure_app_dirs" in text
    assert "shutil.copy2" in text
    assert "INTAKE_DB_NAME" in text
    assert "def default_intake_sqlite_path()" in text
    assert "default_intake_sqlite_path()" in text
    assert "default_intake_db_path" in text, (
        "database.py should cross-link probooks.paths.default_intake_db_path from default_intake_sqlite_path"
    )
