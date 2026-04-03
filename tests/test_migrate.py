"""Migration runner tests."""

from pathlib import Path

import pytest

from tests.repo_paths import PROBOOKS_MIGRATIONS_DIR

from probooks.database import connect, migration_files, run_migrations


def test_migrations_apply_once(tmp_path: Path) -> None:
    mdir = PROBOOKS_MIGRATIONS_DIR
    db = tmp_path / "t.db"
    conn = connect(db)
    applied = run_migrations(conn, migration_files(mdir))
    conn.close()
    assert "001_initial.sql" in applied
    assert "002_import_and_transactions.sql" in applied
    conn = connect(db)
    applied2 = run_migrations(conn, migration_files(mdir))
    conn.close()
    assert applied2 == []


def test_schema_has_bank_accounts(tmp_path: Path) -> None:
    mdir = PROBOOKS_MIGRATIONS_DIR
    db = tmp_path / "t.db"
    conn = connect(db)
    run_migrations(conn, migration_files(mdir))
    n = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='bank_accounts'").fetchone()[0]
    assert n == 1
    conn.close()
