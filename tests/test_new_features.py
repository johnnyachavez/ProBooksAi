"""
Tests for Issue #21 (schema versioning), Issue #30 (bank accounts extended schema),
Issue #40 (GL posting engine), and Issue #41 (COA editor/database).
"""

from __future__ import annotations

import sqlite3
import tempfile
import os
import pytest

from probooksai.bank_import import BankDatabase, SCHEMA_VERSION
from probooksai.gl import GLDatabase, write_journal_export_csv
from probooksai.coa_db import COADatabase, COA_ACCOUNT_TYPES


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    """Return a path to a temporary SQLite database file."""
    return str(tmp_path / "test.db")


@pytest.fixture
def bank_db(tmp_db):
    db = BankDatabase(tmp_db)
    yield db
    db.close()


@pytest.fixture
def gl_db(tmp_db):
    # Share the same connection as bank_db so bank_transactions exist
    bdb = BankDatabase(tmp_db)
    gdb = GLDatabase(bdb._conn)
    yield gdb, bdb
    bdb.close()


@pytest.fixture
def coa_db(tmp_db):
    # Share the same connection as bank_db
    bdb = BankDatabase(tmp_db)
    cdb = COADatabase(bdb._conn)
    yield cdb, bdb
    bdb.close()


# ===========================================================================
# Issue #21 – Schema versioning
# ===========================================================================

class TestSchemaVersioning:
    def test_schema_version_table_created(self, bank_db):
        row = bank_db._conn.execute(
            "SELECT version FROM schema_version WHERE id = 1"
        ).fetchone()
        assert row is not None

    def test_schema_version_matches_constant(self, bank_db):
        row = bank_db._conn.execute(
            "SELECT version FROM schema_version WHERE id = 1"
        ).fetchone()
        assert row["version"] == SCHEMA_VERSION

    def test_migration_is_idempotent(self, tmp_db):
        """Opening the same DB twice must not raise or re-run migrations."""
        db1 = BankDatabase(tmp_db)
        db1.close()
        db2 = BankDatabase(tmp_db)
        row = db2._conn.execute(
            "SELECT version FROM schema_version WHERE id = 1"
        ).fetchone()
        assert row["version"] == SCHEMA_VERSION
        db2.close()

    def test_migration_from_old_schema(self, tmp_db):
        """A DB created without the schema_version table migrates cleanly."""
        # Simulate a v0 DB that has bank_accounts with old columns only
        conn = sqlite3.connect(tmp_db)
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            PRAGMA foreign_keys = ON;
            CREATE TABLE bank_accounts (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT NOT NULL,
                account_number TEXT,
                bank_name    TEXT,
                account_type TEXT NOT NULL DEFAULT 'checking',
                created_at   TEXT NOT NULL
            );
            CREATE TABLE bank_import_batches (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                bank_account_id INTEGER NOT NULL,
                filename        TEXT,
                imported_at     TEXT NOT NULL,
                statement_start TEXT,
                statement_end   TEXT,
                beginning_balance REAL,
                ending_balance  REAL,
                is_reconciled   INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE bank_transactions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id        INTEGER NOT NULL,
                bank_account_id INTEGER NOT NULL,
                txn_date        TEXT NOT NULL,
                description     TEXT,
                amount          REAL NOT NULL,
                ref_number      TEXT,
                fingerprint     TEXT NOT NULL,
                UNIQUE (bank_account_id, fingerprint)
            );
        """)
        conn.commit()
        conn.close()

        # Now open with BankDatabase – should migrate to current version
        db = BankDatabase(tmp_db)
        # The new columns from v2 must exist
        row = db._conn.execute(
            "SELECT institution, last4, notes, is_active, updated_at "
            "FROM bank_accounts LIMIT 0"
        ).fetchone()
        # If no rows, fetchone returns None but no OperationalError means columns exist
        ver_row = db._conn.execute(
            "SELECT version FROM schema_version WHERE id = 1"
        ).fetchone()
        assert ver_row["version"] == SCHEMA_VERSION
        db.close()


# ===========================================================================
# Issue #30 – Bank accounts extended schema
# ===========================================================================

class TestBankAccountsExtended:
    def test_add_account_with_extended_fields(self, bank_db):
        acct_id = bank_db.add_bank_account(
            name="Main Checking",
            account_number="1234",
            bank_name="Chase",
            account_type="checking",
            institution="JP Morgan Chase",
            last4="5678",
            notes="Primary operating account",
            is_active=True,
        )
        assert acct_id > 0
        row = bank_db.get_bank_account(acct_id)
        assert row["institution"] == "JP Morgan Chase"
        assert row["last4"] == "5678"
        assert row["notes"] == "Primary operating account"
        assert row["is_active"] == 1

    def test_add_account_defaults(self, bank_db):
        acct_id = bank_db.add_bank_account(name="Simple Account")
        row = bank_db.get_bank_account(acct_id)
        assert row["institution"] == ""
        assert row["last4"] == ""
        assert row["notes"] == ""
        assert row["is_active"] == 1

    def test_update_account_extended_fields(self, bank_db):
        acct_id = bank_db.add_bank_account(name="Old Name")
        bank_db.update_bank_account(
            acct_id,
            name="New Name",
            institution="Wells Fargo",
            last4="9999",
            notes="Updated note",
            is_active=True,
        )
        row = bank_db.get_bank_account(acct_id)
        assert row["name"] == "New Name"
        assert row["institution"] == "Wells Fargo"
        assert row["last4"] == "9999"
        assert row["notes"] == "Updated note"
        assert row["updated_at"] is not None

    def test_archive_account(self, bank_db):
        acct_id = bank_db.add_bank_account(name="To Archive")
        bank_db.archive_bank_account(acct_id)
        row = bank_db.get_bank_account(acct_id)
        assert row["is_active"] == 0

    def test_list_active_accounts_only(self, bank_db):
        a1 = bank_db.add_bank_account(name="Active")
        a2 = bank_db.add_bank_account(name="Archived")
        bank_db.archive_bank_account(a2)
        active = bank_db.list_bank_accounts(include_inactive=False)
        ids = [r["id"] for r in active]
        assert a1 in ids
        assert a2 not in ids

    def test_list_all_accounts_including_inactive(self, bank_db):
        a1 = bank_db.add_bank_account(name="Active")
        a2 = bank_db.add_bank_account(name="Archived")
        bank_db.archive_bank_account(a2)
        all_accts = bank_db.list_bank_accounts(include_inactive=True)
        ids = [r["id"] for r in all_accts]
        assert a1 in ids
        assert a2 in ids

    def test_updated_at_set_on_create(self, bank_db):
        acct_id = bank_db.add_bank_account(name="Timestamped")
        row = bank_db.get_bank_account(acct_id)
        assert row["updated_at"] is not None

    def test_updated_at_changes_on_update(self, bank_db):
        import time
        acct_id = bank_db.add_bank_account(name="A")
        row_before = bank_db.get_bank_account(acct_id)
        time.sleep(0.01)
        bank_db.update_bank_account(acct_id, name="B")
        row_after = bank_db.get_bank_account(acct_id)
        assert row_after["updated_at"] >= row_before["updated_at"]


# ===========================================================================
# Issue #40 – GL posting engine
# ===========================================================================

class TestGLDatabase:
    def test_journal_entry_tables_created(self, gl_db):
        gdb, bdb = gl_db
        # If tables exist, these queries run without error
        gdb._conn.execute("SELECT * FROM journal_entries LIMIT 0")
        gdb._conn.execute("SELECT * FROM journal_entry_lines LIMIT 0")

    def test_create_balanced_entry(self, gl_db):
        gdb, _ = gl_db
        entry_id = gdb.create_journal_entry(
            entry_date="2026-01-15",
            lines=[
                {"account": "Cash", "debit": 100.0, "credit": 0.0},
                {"account": "Revenue", "debit": 0.0, "credit": 100.0},
            ],
            memo="Test entry",
        )
        assert entry_id > 0

    def test_unbalanced_entry_raises(self, gl_db):
        gdb, _ = gl_db
        with pytest.raises(ValueError, match="not balanced"):
            gdb.create_journal_entry(
                entry_date="2026-01-15",
                lines=[
                    {"account": "Cash", "debit": 100.0, "credit": 0.0},
                    {"account": "Revenue", "debit": 0.0, "credit": 90.0},
                ],
            )

    def test_get_entry_lines(self, gl_db):
        gdb, _ = gl_db
        entry_id = gdb.create_journal_entry(
            entry_date="2026-01-15",
            lines=[
                {"account": "Cash", "debit": 50.0, "credit": 0.0, "description": "inflow"},
                {"account": "Revenue", "debit": 0.0, "credit": 50.0, "description": "inflow"},
            ],
        )
        lines = gdb.get_entry_lines(entry_id)
        assert len(lines) == 2
        accounts = {ln["account"] for ln in lines}
        assert "Cash" in accounts
        assert "Revenue" in accounts

    def test_post_inflow_transaction(self, gl_db):
        gdb, bdb = gl_db
        acct_id = bdb.add_bank_account(name="Checking")
        batch_id = bdb.create_batch(acct_id, filename="test.csv")
        rows = [{"txn_date": "2026-01-10", "description": "Deposit", "amount": 500.0, "ref_number": ""}]
        bdb.import_transactions(batch_id, acct_id, rows)
        txn = bdb.list_transactions(acct_id)[0]

        entry_id = gdb.post_transaction(
            txn_id=txn["id"],
            bank_gl_account="1010 Checking",
            category_account="4000 Revenue",
        )
        assert entry_id > 0

        lines = gdb.get_entry_lines(entry_id)
        assert len(lines) == 2
        bank_line = next(ln for ln in lines if ln["account"] == "1010 Checking")
        rev_line  = next(ln for ln in lines if ln["account"] == "4000 Revenue")
        assert bank_line["debit"] == 500.0
        assert bank_line["credit"] == 0.0
        assert rev_line["credit"] == 500.0

    def test_post_outflow_transaction(self, gl_db):
        gdb, bdb = gl_db
        acct_id = bdb.add_bank_account(name="Checking")
        batch_id = bdb.create_batch(acct_id)
        rows = [{"txn_date": "2026-01-11", "description": "Rent", "amount": -1200.0, "ref_number": ""}]
        bdb.import_transactions(batch_id, acct_id, rows)
        txn = bdb.list_transactions(acct_id)[0]

        entry_id = gdb.post_transaction(
            txn_id=txn["id"],
            bank_gl_account="1010 Checking",
            category_account="5100 Rent Expense",
        )
        lines = gdb.get_entry_lines(entry_id)
        bank_line = next(ln for ln in lines if ln["account"] == "1010 Checking")
        exp_line  = next(ln for ln in lines if ln["account"] == "5100 Rent Expense")
        assert bank_line["credit"] == 1200.0
        assert exp_line["debit"] == 1200.0

    def test_double_posting_raises(self, gl_db):
        gdb, bdb = gl_db
        acct_id = bdb.add_bank_account(name="Checking")
        batch_id = bdb.create_batch(acct_id)
        rows = [{"txn_date": "2026-01-12", "description": "Sale", "amount": 200.0, "ref_number": ""}]
        bdb.import_transactions(batch_id, acct_id, rows)
        txn = bdb.list_transactions(acct_id)[0]

        gdb.post_transaction(txn["id"], "1010 Checking", "4000 Revenue")
        with pytest.raises(ValueError, match="already posted"):
            gdb.post_transaction(txn["id"], "1010 Checking", "4000 Revenue")

    def test_trial_balance_totals(self, gl_db):
        gdb, _ = gl_db
        gdb.create_journal_entry(
            entry_date="2026-01-15",
            lines=[
                {"account": "Cash", "debit": 1000.0, "credit": 0.0},
                {"account": "Revenue", "debit": 0.0, "credit": 1000.0},
            ],
        )
        tb = gdb.trial_balance()
        assert len(tb) == 2
        total_debit  = sum(row["total_debit"] for row in tb)
        total_credit = sum(row["total_credit"] for row in tb)
        assert total_debit == total_credit

    def test_list_journal_entries_date_filter(self, gl_db):
        gdb, _ = gl_db
        gdb.create_journal_entry(
            "2026-01-01",
            [{"account": "A", "debit": 10.0, "credit": 0.0},
             {"account": "B", "debit": 0.0, "credit": 10.0}],
        )
        gdb.create_journal_entry(
            "2026-02-01",
            [{"account": "A", "debit": 20.0, "credit": 0.0},
             {"account": "B", "debit": 0.0, "credit": 20.0}],
        )
        jan = gdb.list_journal_entries(start_date="2026-01-01", end_date="2026-01-31")
        assert len(jan) == 1

    def test_journal_export_rows_and_write_csv(self, gl_db, tmp_path):
        gdb, _ = gl_db
        gdb.create_journal_entry(
            "2026-03-10",
            [
                {
                    "account": "1000 – Cash",
                    "debit": 50.0,
                    "credit": 0.0,
                    "description": "in",
                },
                {
                    "account": "4000 – Sales",
                    "debit": 0.0,
                    "credit": 50.0,
                    "description": "sale",
                },
            ],
            memo="day total",
        )
        rows = gdb.journal_export_rows("2026-03-01", "2026-03-31")
        assert len(rows) == 2
        assert rows[0]["entry_memo"] == "day total"
        p = tmp_path / "je.csv"
        n = write_journal_export_csv(str(p), rows)
        assert n == 2
        text = p.read_text(encoding="utf-8")
        assert "1000" in text
        assert "day total" in text

    def test_post_transactions_bulk(self, gl_db):
        gdb, bdb = gl_db
        acct_id = bdb.add_bank_account(name="Checking")
        batch_id = bdb.create_batch(acct_id)
        rows = [
            {"txn_date": "2026-01-01", "description": "T1", "amount": 100.0, "ref_number": ""},
            {"txn_date": "2026-01-02", "description": "T2", "amount": -50.0, "ref_number": ""},
        ]
        bdb.import_transactions(batch_id, acct_id, rows)
        txns = bdb.list_transactions(acct_id)
        assert len(txns) == 2

        result = gdb.post_transactions_bulk(
            txn_ids=[txns[0]["id"], txns[1]["id"]],
            bank_gl_account="1010 Checking",
            category_account_map={
                txns[0]["id"]: "4000 Revenue",
                txns[1]["id"]: "5100 Expense",
            },
        )
        assert len(result["posted"]) == 2
        assert len(result["skipped"]) == 0
        assert len(result["errors"]) == 0


# ===========================================================================
# Issue #41 – COA Database (editor backend)
# ===========================================================================

class TestCOADatabase:
    def test_coa_table_created(self, coa_db):
        cdb, _ = coa_db
        cdb._conn.execute("SELECT * FROM coa_accounts LIMIT 0")

    def test_add_account(self, coa_db):
        cdb, _ = coa_db
        acct_id = cdb.add_account(
            account_number="1010",
            account_name="Checking Account",
            account_type="asset",
            sub_type="Cash",
        )
        assert acct_id > 0
        row = cdb.get_account(acct_id)
        assert row["account_number"] == "1010"
        assert row["account_name"] == "Checking Account"
        assert row["account_type"] == "asset"

    def test_invalid_type_raises(self, coa_db):
        cdb, _ = coa_db
        with pytest.raises(ValueError, match="Invalid account_type"):
            cdb.add_account("9999", "Bad", account_type="nonsense")

    def test_update_account(self, coa_db):
        cdb, _ = coa_db
        acct_id = cdb.add_account("1010", "Old Name", "asset")
        cdb.update_account(acct_id, "1010", "New Name", "asset")
        row = cdb.get_account(acct_id)
        assert row["account_name"] == "New Name"

    def test_deactivate_account(self, coa_db):
        cdb, _ = coa_db
        acct_id = cdb.add_account("1010", "Test", "asset")
        cdb.update_account(acct_id, "1010", "Test", "asset", is_active=False)
        row = cdb.get_account(acct_id)
        assert row["is_active"] == 0

    def test_list_active_only(self, coa_db):
        cdb, _ = coa_db
        a1 = cdb.add_account("1000", "Active", "asset")
        a2 = cdb.add_account("2000", "Inactive", "liability")
        cdb.update_account(a2, "2000", "Inactive", "liability", is_active=False)
        active = cdb.list_accounts(include_inactive=False)
        ids = [r["id"] for r in active]
        assert a1 in ids
        assert a2 not in ids

    def test_list_all_including_inactive(self, coa_db):
        cdb, _ = coa_db
        a1 = cdb.add_account("1000", "Active", "asset")
        a2 = cdb.add_account("2000", "Inactive", "liability")
        cdb.update_account(a2, "2000", "Inactive", "liability", is_active=False)
        all_accts = cdb.list_accounts(include_inactive=True)
        ids = [r["id"] for r in all_accts]
        assert a1 in ids
        assert a2 in ids

    def test_display_list(self, coa_db):
        cdb, _ = coa_db
        cdb.add_account("1010", "Checking", "asset")
        cdb.add_account("4000", "Revenue", "income")
        disp = cdb.display_list()
        assert any("1010" in s and "Checking" in s for s in disp)
        assert any("4000" in s and "Revenue" in s for s in disp)

    def test_get_account_by_number(self, coa_db):
        cdb, _ = coa_db
        cdb.add_account("5100", "Rent Expense", "expense")
        row = cdb.get_account_by_number("5100")
        assert row is not None
        assert row["account_name"] == "Rent Expense"

    def test_duplicate_account_number_raises(self, coa_db):
        cdb, _ = coa_db
        cdb.add_account("1010", "First", "asset")
        with pytest.raises(sqlite3.IntegrityError):
            cdb.add_account("1010", "Duplicate", "asset")

    def test_delete_account(self, coa_db):
        cdb, _ = coa_db
        acct_id = cdb.add_account("9999", "Temp", "expense")
        cdb.delete_account(acct_id)
        assert cdb.get_account(acct_id) is None

    def test_all_account_types_accepted(self, coa_db):
        cdb, _ = coa_db
        for i, acct_type in enumerate(COA_ACCOUNT_TYPES):
            acct_id = cdb.add_account(str(1000 + i), f"Account {i}", acct_type)
            assert acct_id > 0
