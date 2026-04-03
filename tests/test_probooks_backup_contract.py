"""probooks.backup module contract (import-free text checks)."""

from __future__ import annotations

from tests.repo_paths import PROBOOKS_PACKAGE_DIR

PROBOOKS_BACKUP_PY = PROBOOKS_PACKAGE_DIR / "backup.py"


def test_probooks_backup_module_doc_and_online_backup_flow() -> None:
    text = PROBOOKS_BACKUP_PY.read_text(encoding="utf-8")
    assert "issue #28" in text
    assert "sqlite3.Connection.backup" in text
    assert "os.replace" in text


def test_probooks_backup_sqlite_magic_and_public_api() -> None:
    text = PROBOOKS_BACKUP_PY.read_text(encoding="utf-8")
    assert 'SQLITE_MAGIC = b"SQLite format 3\\x00"' in text
    assert "def is_sqlite_file(path: Path) -> bool:" in text
    assert "def backup_database(source_db: Path, destination: Path) -> None:" in text
    assert (
        "def restore_database(backup_file: Path, target_db: Path, *, overwrite: bool) -> None:"
        in text
    )


def test_probooks_backup_temp_prefixes_and_mkstemp() -> None:
    text = PROBOOKS_BACKUP_PY.read_text(encoding="utf-8")
    assert "tempfile.mkstemp" in text
    assert 'prefix=".probooks-backup-"' in text
    assert 'prefix=".probooks-restore-"' in text
