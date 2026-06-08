"""SQLite DDL inventory (user table + column names) for issue #21 (single file + merged migrations).

The ``probooks`` CLI applies SQL files under ``probooks/migrations/`` (ledger:
``schema_migrations``). The desktop :class:`~probooksai.bank_import.BankDatabase`
uses ``schema_version`` plus embedded DDL. Both live in the same branded data
folder today as separate files (``probooks.db`` vs ``probooksai.db``).

``BankDatabase(db_path=None)`` resolves the file via
``probooksai.database.default_intake_sqlite_path`` (runs ``get_data_dir`` / legacy copy),
not ``probooks.paths.default_intake_db_path`` alone — see ``probooks/paths.py`` module doc.

When you add CLI migrations or desktop bank migrations, update the expected frozensets
below (tables, columns on ``bank_accounts`` / ``bank_transactions``, and shared column
name intersections) so merge work stays explicit.
"""

from __future__ import annotations

from pathlib import Path

from probooks.database import connect, migration_files, run_migrations
from probooksai.bank_import import BankDatabase

from tests.repo_paths import PROBOOKS_MIGRATIONS_DIR


def _migration_dir() -> Path:
    return PROBOOKS_MIGRATIONS_DIR


def _user_table_names(conn) -> frozenset[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return frozenset(str(r[0]) for r in rows)


def _pragma_column_names(conn, table: str) -> frozenset[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return frozenset(str(r[1]) for r in rows)


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
        "bank_import_line_reconcile_review",
        "bank_transactions",
        "schema_version",
    }
)

# Same identifier, different columns / constraints — merge must reconcile DDL.
_SHARED_BANK_TABLE_NAMES = frozenset({"bank_accounts", "bank_transactions"})

# Column names on overlapping tables (PRAGMA table_info "name"); issue #21 merge must reconcile.
_CLI_BANK_ACCOUNTS_COLUMNS = frozenset(
    {
        "id",
        "company_id",
        "name",
        "institution",
        "account_type",
        "last4",
        "notes",
        "created_at",
    }
)
_CLI_BANK_TRANSACTIONS_COLUMNS = frozenset(
    {
        "id",
        "bank_account_id",
        "import_batch_id",
        "txn_date",
        "amount",
        "payee",
        "memo",
        "reference_number",
        "raw_description",
        "created_at",
    }
)
_DESKTOP_BANK_ACCOUNTS_COLUMNS = frozenset(
    {
        "id",
        "name",
        "account_number",
        "bank_name",
        "account_type",
        "created_at",
        "institution",
        "last4",
        "notes",
        "is_active",
        "updated_at",
        "gl_display_account",
        "imp_csv_date_col",
        "imp_csv_amount_col",
        "imp_csv_desc_col",
        "imp_csv_ref_col",
    }
)
_DESKTOP_BANK_TRANSACTIONS_COLUMNS = frozenset(
    {
        "id",
        "batch_id",
        "bank_account_id",
        "txn_date",
        "description",
        "amount",
        "ref_number",
        "fingerprint",
        "memo",
        "coa_account",
        "attachment_path",
        "needs_receipt",
        "transfer_to_bank_account_id",
        "cleared",
    }
)

# Identical column *names* on both sides today (still different types / FK targets in places).
_SHARED_BANK_ACCOUNTS_COLUMN_NAMES = frozenset(
    {"id", "name", "institution", "account_type", "last4", "notes", "created_at"}
)
_SHARED_BANK_TRANSACTIONS_COLUMN_NAMES = frozenset(
    {"id", "bank_account_id", "txn_date", "amount", "memo"}
)


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


def test_issue_21_bank_table_columns_match_inventory(tmp_path: Path) -> None:
    """PRAGMA column names on shared bank tables match frozen issue #21 inventory."""
    cli_db = tmp_path / "cli_cols.db"
    conn = connect(cli_db)
    run_migrations(conn, migration_files(_migration_dir()))
    try:
        assert _pragma_column_names(conn, "bank_accounts") == _CLI_BANK_ACCOUNTS_COLUMNS, (
            "Update _CLI_BANK_ACCOUNTS_COLUMNS when probooks/migrations changes (issue #21)."
        )
        assert _pragma_column_names(conn, "bank_transactions") == _CLI_BANK_TRANSACTIONS_COLUMNS, (
            "Update _CLI_BANK_TRANSACTIONS_COLUMNS when probooks/migrations changes (issue #21)."
        )
    finally:
        conn.close()

    desk_path = str(tmp_path / "desktop_cols.db")
    with BankDatabase(db_path=desk_path) as bdb:
        dc = bdb._conn
        assert _pragma_column_names(dc, "bank_accounts") == _DESKTOP_BANK_ACCOUNTS_COLUMNS, (
            "Update _DESKTOP_BANK_ACCOUNTS_COLUMNS when bank_import schema changes (issue #21)."
        )
        assert _pragma_column_names(dc, "bank_transactions") == _DESKTOP_BANK_TRANSACTIONS_COLUMNS, (
            "Update _DESKTOP_BANK_TRANSACTIONS_COLUMNS when bank_import schema changes (issue #21)."
        )

    assert (
        _CLI_BANK_ACCOUNTS_COLUMNS & _DESKTOP_BANK_ACCOUNTS_COLUMNS
        == _SHARED_BANK_ACCOUNTS_COLUMN_NAMES
    ), (
        "Document CLI/desktop shared bank_accounts column *names* for issue #21; "
        f"expected {_SHARED_BANK_ACCOUNTS_COLUMN_NAMES}, got "
        f"{_CLI_BANK_ACCOUNTS_COLUMNS & _DESKTOP_BANK_ACCOUNTS_COLUMNS}."
    )
    assert (
        _CLI_BANK_TRANSACTIONS_COLUMNS & _DESKTOP_BANK_TRANSACTIONS_COLUMNS
        == _SHARED_BANK_TRANSACTIONS_COLUMN_NAMES
    ), (
        "Document CLI/desktop shared bank_transactions column *names* for issue #21; "
        f"expected {_SHARED_BANK_TRANSACTIONS_COLUMN_NAMES}, got "
        f"{_CLI_BANK_TRANSACTIONS_COLUMNS & _DESKTOP_BANK_TRANSACTIONS_COLUMNS}."
    )
