"""SQLite DDL inventory (user table names) for issue #21 (single file + merged migrations).

The ``probooks`` CLI applies SQL files under ``probooks/migrations/`` (ledger:
``schema_migrations``). The desktop :class:`~probooksai.bank_import.BankDatabase`
uses ``schema_version`` plus embedded DDL. Both live in the same branded data
folder today as separate files (``probooks.db`` vs ``probooksai.db``).

When you add CLI migrations or desktop bank migrations, update the expected sets
below so merge work stays explicit.
"""

from __future__ import annotations

from pathlib import Path

from probooks.database import connect, migration_files, run_migrations
from probooksai.bank_import import BankDatabase


def _migration_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "probooks" / "migrations"


def _user_table_names(conn) -> frozenset[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return frozenset(str(r[0]) for r in rows)


# After 001_initial.sql + 002_import_and_transactions.sql
_CLI_BANK_TABLES = frozenset(
    {
        "bank_accounts",
        "bank_transactions",
        "companies",
        "import_batches",
        "schema_migrations",
    }
)

# After BankDatabase migrations (no intake / extensions / GL / COA)
_DESKTOP_BANK_CORE_TABLES = frozenset(
    {
        "bank_accounts",
        "bank_import_batches",
        "bank_transactions",
        "schema_version",
    }
)

# Same identifier, different columns / constraints — merge must reconcile DDL.
_SHARED_BANK_TABLE_NAMES = frozenset({"bank_accounts", "bank_transactions"})


def test_cli_migrations_user_tables_match_expected(tmp_path: Path) -> None:
    db = tmp_path / "cli.db"
    conn = connect(db)
    run_migrations(conn, migration_files(_migration_dir()))
    names = _user_table_names(conn)
    conn.close()
    assert names == _CLI_BANK_TABLES, (
        "Update _CLI_BANK_TABLES when probooks/migrations changes (issue #21)."
    )


def test_desktop_bank_database_user_tables_match_expected(tmp_path: Path) -> None:
    path = str(tmp_path / "desktop_bank.db")
    with BankDatabase(db_path=path) as bdb:
        names = _user_table_names(bdb._conn)
    assert names == _DESKTOP_BANK_CORE_TABLES, (
        "Update _DESKTOP_BANK_CORE_TABLES when bank_import schema changes (issue #21)."
    )


def test_cli_and_desktop_bank_share_only_expected_table_names() -> None:
    overlap = _CLI_BANK_TABLES & _DESKTOP_BANK_CORE_TABLES
    assert overlap == _SHARED_BANK_TABLE_NAMES, (
        "CLI and desktop bank schemas share these table names today; issue #21 merge "
        f"must account for overlap (expected {_SHARED_BANK_TABLE_NAMES}, got {overlap})."
    )
