"""probooks.paths default data dir name (documented in README vs desktop get_data_dir)."""

from __future__ import annotations

from tests.repo_paths import PROBOOKS_PACKAGE_DIR
_PATHS = PROBOOKS_PACKAGE_DIR / "paths.py"


def test_probooks_paths_use_branded_app_dir_and_cli_db_name() -> None:
    text = _PATHS.read_text(encoding="utf-8")
    assert '_APP_DIR_NAME = "ProBooks+ai"' in text
    assert '_DB_NAME = "probooks.db"' in text
    assert 'INTAKE_DB_NAME = "probooksai.db"' in text
    assert "def default_db_path()" in text
    assert "def default_intake_db_path()" in text
    assert "default_intake_sqlite_path" in text, (
        "paths.py should point runtime default DB resolution at probooksai.database"
    )
    assert "ProBooks+ai" in text


def test_default_intake_db_path_matches_app_dir_and_intake_name(
    isolated_branded_app_data_env,
) -> None:
    from probooks.paths import INTAKE_DB_NAME, app_data_dir, default_intake_db_path

    assert default_intake_db_path() == app_data_dir() / INTAKE_DB_NAME


def test_default_db_path_matches_app_dir_and_cli_name(isolated_branded_app_data_env) -> None:
    from probooks.paths import app_data_dir, default_db_path

    assert default_db_path() == app_data_dir() / "probooks.db"
