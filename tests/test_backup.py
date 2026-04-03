"""Backup / restore tests."""

from pathlib import Path

from probooks.backup import backup_database, is_sqlite_file, restore_database
from probooks.database import connect, migration_files, run_migrations

from tests.repo_paths import PROBOOKS_MIGRATIONS_DIR


def test_backup_roundtrip(tmp_path: Path) -> None:
    mdir = PROBOOKS_MIGRATIONS_DIR
    src = tmp_path / "live.db"
    conn = connect(src)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    assert is_sqlite_file(src)

    bak = tmp_path / "copy.db"
    backup_database(src, bak)
    assert is_sqlite_file(bak)

    dest = tmp_path / "restored.db"
    restore_database(bak, dest, overwrite=True)
    assert is_sqlite_file(dest)
    conn = connect(dest)
    assert conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0] >= 1
    conn.close()
