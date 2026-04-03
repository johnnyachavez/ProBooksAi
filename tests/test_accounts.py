"""Bank account CRUD tests."""

from pathlib import Path

from probooks.accounts import add_account, list_accounts
from probooks.database import connect, migration_files, run_migrations

from tests.repo_paths import PROBOOKS_MIGRATIONS_DIR


def _fresh(tmp_path: Path) -> Path:
    db = tmp_path / "a.db"
    mdir = PROBOOKS_MIGRATIONS_DIR
    conn = connect(db)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    return db


def test_add_and_list(tmp_path: Path) -> None:
    db = _fresh(tmp_path)
    conn = connect(db)
    aid = add_account(conn, name="Checking", institution="Test Bank", account_type="checking", last4="4242")
    assert aid >= 1
    rows = list_accounts(conn)
    conn.close()
    assert len(rows) == 1
    assert rows[0].name == "Checking"
    assert rows[0].last4 == "4242"
