"""
Tests for Issue #12: Bank reconciliation per statement period + per-account setup.

Covers:
- CRUD for bank accounts
- Bank import batch with statement fields (bank_account_id, dates, balances)
- Reconciliation math (compute_reconciliation / ReconciliationResult)
- Mark-reconciled / unmark-reconciled persistence
- Odd statement ranges
- Additive migration (bank_import_batches columns)
- Sign convention: money-out negative, money-in positive
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from probooksai.bank_import import (
    RECONCILE_TOLERANCE,
    ReconciliationResult,
    compute_reconciliation,
)
from probooksai.database import DocumentDatabase


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path):
    """Return a DocumentDatabase backed by a temp SQLite file."""
    db = DocumentDatabase(db_path=str(tmp_path / "test.db"))
    yield db
    db.close()


# ---------------------------------------------------------------------------
# Bank Account CRUD
# ---------------------------------------------------------------------------


class TestBankAccountCRUD:
    def test_create_and_get(self, tmp_db):
        acc_id = tmp_db.create_bank_account(
            name="Business Checking",
            institution="Chase",
            last4="2443",
        )
        assert isinstance(acc_id, int)
        acc = tmp_db.get_bank_account(acc_id)
        assert acc["name"] == "Business Checking"
        assert acc["institution"] == "Chase"
        assert acc["last4"] == "2443"
        assert acc["external_id"] is None
        assert acc["created_at"] is not None

    def test_list_accounts_empty(self, tmp_db):
        assert tmp_db.list_bank_accounts() == []

    def test_list_accounts_ordered_by_name(self, tmp_db):
        tmp_db.create_bank_account(name="Savings")
        tmp_db.create_bank_account(name="Checking")
        tmp_db.create_bank_account(name="Credit Card")
        names = [a["name"] for a in tmp_db.list_bank_accounts()]
        assert names == sorted(names)

    def test_create_minimal(self, tmp_db):
        acc_id = tmp_db.create_bank_account(name="Minimal")
        acc = tmp_db.get_bank_account(acc_id)
        assert acc["name"] == "Minimal"
        assert acc["institution"] is None
        assert acc["last4"] is None

    def test_create_with_external_id(self, tmp_db):
        acc_id = tmp_db.create_bank_account(name="Biz", external_id="EXT-001")
        acc = tmp_db.get_bank_account(acc_id)
        assert acc["external_id"] == "EXT-001"

    def test_update_name(self, tmp_db):
        acc_id = tmp_db.create_bank_account(name="Old Name")
        tmp_db.update_bank_account(acc_id, name="New Name")
        acc = tmp_db.get_bank_account(acc_id)
        assert acc["name"] == "New Name"

    def test_update_institution_and_last4(self, tmp_db):
        acc_id = tmp_db.create_bank_account(name="Checking")
        tmp_db.update_bank_account(acc_id, institution="Wells Fargo", last4="9999")
        acc = tmp_db.get_bank_account(acc_id)
        assert acc["institution"] == "Wells Fargo"
        assert acc["last4"] == "9999"

    def test_update_noop(self, tmp_db):
        """Calling update with no kwargs should not raise."""
        acc_id = tmp_db.create_bank_account(name="Stable")
        tmp_db.update_bank_account(acc_id)
        assert tmp_db.get_bank_account(acc_id)["name"] == "Stable"

    def test_delete_account(self, tmp_db):
        acc_id = tmp_db.create_bank_account(name="Temp")
        tmp_db.delete_bank_account(acc_id)
        assert tmp_db.get_bank_account(acc_id) is None

    def test_delete_unlinks_batches(self, tmp_db):
        """Deleting an account sets bank_account_id = NULL on batches (no cascade delete)."""
        acc_id = tmp_db.create_bank_account(name="Checking")
        batch_id = tmp_db.create_batch("stmt.csv", bank_account_id=acc_id)
        tmp_db.delete_bank_account(acc_id)
        batch = tmp_db.get_batch(batch_id)
        assert batch is not None          # batch still exists
        assert batch["bank_account_id"] is None

    def test_multiple_accounts(self, tmp_db):
        ids = [tmp_db.create_bank_account(name=f"Account {i}") for i in range(5)]
        assert len(ids) == 5
        assert len(set(ids)) == 5         # all unique
        assert len(tmp_db.list_bank_accounts()) == 5


# ---------------------------------------------------------------------------
# Batch statement fields persistence
# ---------------------------------------------------------------------------


class TestBatchStatementFields:
    def test_create_batch_with_statement_fields(self, tmp_db):
        acc_id = tmp_db.create_bank_account(name="Checking")
        batch_id = tmp_db.create_batch(
            "march.csv",
            bank_account_id=acc_id,
            statement_start_date="2024-03-01",
            statement_end_date="2024-03-29",
            beginning_balance=14261.82,
            ending_balance=4073.02,
        )
        batch = tmp_db.get_batch(batch_id)
        assert batch["bank_account_id"] == acc_id
        assert batch["statement_start_date"] == "2024-03-01"
        assert batch["statement_end_date"] == "2024-03-29"
        assert batch["beginning_balance"] == pytest.approx(14261.82)
        assert batch["ending_balance"] == pytest.approx(4073.02)
        assert batch["is_reconciled"] == 0
        assert batch["reconciled_at"] is None
        assert batch["reconciled_difference"] is None

    def test_create_batch_without_optional_fields(self, tmp_db):
        batch_id = tmp_db.create_batch("simple.csv")
        batch = tmp_db.get_batch(batch_id)
        assert batch["bank_account_id"] is None
        assert batch["statement_start_date"] is None
        assert batch["ending_balance"] is None

    def test_update_batch_statement(self, tmp_db):
        batch_id = tmp_db.create_batch("stmt.csv")
        acc_id = tmp_db.create_bank_account(name="Savings")
        tmp_db.update_batch_statement(
            batch_id,
            bank_account_id=acc_id,
            statement_start_date="2024-01-01",
            statement_end_date="2024-01-31",
            beginning_balance=1000.00,
            ending_balance=1200.00,
        )
        batch = tmp_db.get_batch(batch_id)
        assert batch["bank_account_id"] == acc_id
        assert batch["statement_start_date"] == "2024-01-01"
        assert batch["statement_end_date"] == "2024-01-31"
        assert batch["beginning_balance"] == pytest.approx(1000.00)
        assert batch["ending_balance"] == pytest.approx(1200.00)

    def test_list_batches_filtered_by_account(self, tmp_db):
        acc1 = tmp_db.create_bank_account(name="Checking")
        acc2 = tmp_db.create_bank_account(name="Savings")
        b1 = tmp_db.create_batch("a.csv", bank_account_id=acc1)
        b2 = tmp_db.create_batch("b.csv", bank_account_id=acc2)
        b3 = tmp_db.create_batch("c.csv", bank_account_id=acc1)

        acc1_batches = [b["id"] for b in tmp_db.list_batches(bank_account_id=acc1)]
        assert set(acc1_batches) == {b1, b3}

        acc2_batches = [b["id"] for b in tmp_db.list_batches(bank_account_id=acc2)]
        assert acc2_batches == [b2]

    def test_list_batches_all_when_no_filter(self, tmp_db):
        acc = tmp_db.create_bank_account(name="Checking")
        b1 = tmp_db.create_batch("a.csv", bank_account_id=acc)
        b2 = tmp_db.create_batch("b.csv")
        all_ids = [b["id"] for b in tmp_db.list_batches()]
        assert set(all_ids) == {b1, b2}

    def test_odd_statement_range_persisted(self, tmp_db):
        """Odd ranges like Mar 01 – Mar 29 (not a full calendar month) are supported."""
        batch_id = tmp_db.create_batch(
            "chase_march.csv",
            statement_start_date="2024-03-01",
            statement_end_date="2024-03-29",  # not March 31
        )
        batch = tmp_db.get_batch(batch_id)
        assert batch["statement_start_date"] == "2024-03-01"
        assert batch["statement_end_date"] == "2024-03-29"


# ---------------------------------------------------------------------------
# Reconciliation math
# ---------------------------------------------------------------------------


class TestReconciliationMath:
    def test_balanced_zero_difference(self):
        """Beginning + transactions == ending → difference is 0."""
        result = compute_reconciliation(
            beginning_balance=1000.00,
            ending_balance=1200.00,
            amounts=[500.00, -300.00],  # net +200
        )
        assert result.sum_transactions == pytest.approx(200.00)
        assert result.expected_ending == pytest.approx(1200.00)
        assert result.difference == pytest.approx(0.00)
        assert result.is_balanced is True

    def test_unbalanced_positive_difference(self):
        result = compute_reconciliation(
            beginning_balance=1000.00,
            ending_balance=1250.00,
            amounts=[200.00],           # expected_ending = 1200, but statement says 1250
        )
        assert result.difference == pytest.approx(50.00)
        assert result.is_balanced is False

    def test_unbalanced_negative_difference(self):
        result = compute_reconciliation(
            beginning_balance=1000.00,
            ending_balance=1150.00,
            amounts=[200.00],           # expected 1200, statement 1150
        )
        assert result.difference == pytest.approx(-50.00)
        assert result.is_balanced is False

    def test_money_out_negative(self):
        """Money-out (withdrawals) should be stored/passed as negative amounts."""
        result = compute_reconciliation(
            beginning_balance=14261.82,
            ending_balance=4073.02,
            amounts=[
                103606.63,    # deposits (positive)
                -10.00,       # check (negative)
                -2630.63,     # ATM/debit (negative)
                -111063.80,   # electronic withdrawals (negative)
                -91.00,       # fees (negative)
            ],
        )
        assert result.sum_transactions == pytest.approx(-10188.80, abs=0.01)
        assert result.expected_ending == pytest.approx(4073.02, abs=0.01)
        assert result.difference == pytest.approx(0.00, abs=0.01)
        assert result.is_balanced is True

    def test_none_amounts_treated_as_zero(self):
        """Transactions with no parsed amount (None) are ignored."""
        result = compute_reconciliation(
            beginning_balance=1000.00,
            ending_balance=1100.00,
            amounts=[100.00, None, None],
        )
        assert result.sum_transactions == pytest.approx(100.00)
        assert result.is_balanced is True

    def test_empty_amounts(self):
        """No transactions: expected_ending == beginning_balance."""
        result = compute_reconciliation(
            beginning_balance=500.00,
            ending_balance=500.00,
            amounts=[],
        )
        assert result.sum_transactions == pytest.approx(0.00)
        assert result.expected_ending == pytest.approx(500.00)
        assert result.is_balanced is True

    def test_large_odd_range(self):
        """Test with an odd date range (Mar 1 – Mar 29) using real Chase numbers."""
        # Deposits and Additions: +103,606.63
        # Checks Paid: -10.00
        # ATM & Debit Card Withdrawals: -2,630.63
        # Electronic Withdrawals: -111,063.80
        # Fees: -91.00
        amounts = [103606.63, -10.00, -2630.63, -111063.80, -91.00]
        result = compute_reconciliation(
            beginning_balance=14261.82,
            ending_balance=4073.02,
            amounts=amounts,
        )
        assert result.is_balanced is True
        assert abs(result.difference) <= RECONCILE_TOLERANCE + 0.01

    def test_reconciliation_result_fields(self):
        result = compute_reconciliation(500.0, 700.0, [300.0, -100.0])
        assert result.beginning_balance == 500.0
        assert result.ending_balance == 700.0
        assert result.sum_transactions == pytest.approx(200.0)
        assert result.expected_ending == pytest.approx(700.0)
        assert result.difference == pytest.approx(0.0)

    def test_tolerance_constant_is_zero(self):
        """Default tolerance should be 0.00 (strict mode)."""
        assert RECONCILE_TOLERANCE == 0.00

    def test_small_imbalance_not_balanced(self):
        """Even $0.01 off is unbalanced at tolerance=0."""
        result = compute_reconciliation(1000.00, 1100.01, [100.00])
        assert result.difference == pytest.approx(0.01)
        assert result.is_balanced is False


# ---------------------------------------------------------------------------
# Mark reconciled / unmark
# ---------------------------------------------------------------------------


class TestMarkReconciled:
    def _setup_batch(self, tmp_db, beginning=1000.0, ending=1100.0):
        batch_id = tmp_db.create_batch(
            "stmt.csv",
            beginning_balance=beginning,
            ending_balance=ending,
        )
        tmp_db.insert_transaction(
            batch_id=batch_id,
            posted_date="2024-03-01",
            description="Deposit",
            amount=100.0,
            fingerprint="fp-1",
        )
        return batch_id

    def test_mark_reconciled_persists(self, tmp_db):
        batch_id = self._setup_batch(tmp_db)
        tmp_db.mark_batch_reconciled(batch_id, reconciled_difference=0.00)
        batch = tmp_db.get_batch(batch_id)
        assert batch["is_reconciled"] == 1
        assert batch["reconciled_at"] is not None
        assert batch["reconciled_difference"] == pytest.approx(0.00)

    def test_unmark_reconciled(self, tmp_db):
        batch_id = self._setup_batch(tmp_db)
        tmp_db.mark_batch_reconciled(batch_id, reconciled_difference=0.00)
        tmp_db.unmark_batch_reconciled(batch_id)
        batch = tmp_db.get_batch(batch_id)
        assert batch["is_reconciled"] == 0
        assert batch["reconciled_at"] is None
        assert batch["reconciled_difference"] is None

    def test_mark_reconciled_preserves_other_fields(self, tmp_db):
        acc_id = tmp_db.create_bank_account(name="Checking")
        batch_id = tmp_db.create_batch(
            "stmt.csv",
            bank_account_id=acc_id,
            statement_start_date="2024-03-01",
            statement_end_date="2024-03-29",
            beginning_balance=14261.82,
            ending_balance=4073.02,
        )
        tmp_db.mark_batch_reconciled(batch_id, reconciled_difference=0.00)
        batch = tmp_db.get_batch(batch_id)
        assert batch["bank_account_id"] == acc_id
        assert batch["statement_start_date"] == "2024-03-01"
        assert batch["beginning_balance"] == pytest.approx(14261.82)


# ---------------------------------------------------------------------------
# Schema verification (Issue #12 additions)
# ---------------------------------------------------------------------------


class TestIssue12Schema:
    def test_bank_accounts_table_exists(self, tmp_db):
        cur = tmp_db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bank_accounts'"
        )
        assert cur.fetchone() is not None

    def test_bank_accounts_has_expected_columns(self, tmp_db):
        cur = tmp_db._conn.execute("PRAGMA table_info(bank_accounts)")
        col_names = {row[1] for row in cur.fetchall()}
        expected = {"id", "name", "institution", "last4", "external_id", "created_at"}
        assert expected.issubset(col_names)

    def test_bank_import_batches_has_reconciliation_columns(self, tmp_db):
        cur = tmp_db._conn.execute("PRAGMA table_info(bank_import_batches)")
        col_names = {row[1] for row in cur.fetchall()}
        expected = {
            "bank_account_id",
            "statement_start_date",
            "statement_end_date",
            "beginning_balance",
            "ending_balance",
            "is_reconciled",
            "reconciled_at",
            "reconciled_difference",
        }
        assert expected.issubset(col_names)

    def test_bank_account_id_index_exists(self, tmp_db):
        cur = tmp_db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_batch_account'"
        )
        assert cur.fetchone() is not None

    def test_additive_migration_on_existing_db(self, tmp_path):
        """
        Simulate a DB that was created with the old schema (no reconciliation
        columns) and verify that _migrate() adds the missing columns without
        breaking anything.
        """
        db_path = str(tmp_path / "old_schema.db")
        # Create old schema manually (as PR #10 had it)
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS bank_import_batches (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                source_filename TEXT    NOT NULL,
                imported_at     TEXT    NOT NULL,
                format_meta     TEXT
            );
            CREATE TABLE IF NOT EXISTS bank_transactions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id        INTEGER NOT NULL,
                posted_date     TEXT,
                description     TEXT    NOT NULL DEFAULT '',
                amount          REAL,
                currency        TEXT    NOT NULL DEFAULT 'USD',
                source_row      INTEGER,
                fingerprint     TEXT    NOT NULL DEFAULT '',
                coa_account     TEXT,
                status          TEXT    NOT NULL DEFAULT 'Imported',
                is_duplicate    INTEGER NOT NULL DEFAULT 0,
                parse_errors    TEXT,
                created_at      TEXT    NOT NULL,
                updated_at      TEXT    NOT NULL
            );
        """)
        conn.commit()
        conn.close()

        # Now open it with DocumentDatabase (should trigger migration)
        db = DocumentDatabase(db_path=db_path)
        # Verify new columns are now present
        cur = db._conn.execute("PRAGMA table_info(bank_import_batches)")
        col_names = {row[1] for row in cur.fetchall()}
        assert "bank_account_id" in col_names
        assert "statement_start_date" in col_names
        assert "is_reconciled" in col_names
        db.close()


# ---------------------------------------------------------------------------
# Sign convention safety
# ---------------------------------------------------------------------------


class TestSignConventions:
    def test_money_in_positive(self, tmp_db):
        """Deposits (money in) should be stored as positive values."""
        batch_id = tmp_db.create_batch("deposits.csv")
        txn_id = tmp_db.insert_transaction(
            batch_id=batch_id,
            posted_date="2024-03-11",
            description="Deposit",
            amount=47971.30,  # positive
            fingerprint="deposit-fp",
        )
        txn = tmp_db.get_transaction(txn_id)
        assert txn["amount"] > 0

    def test_money_out_negative(self, tmp_db):
        """Withdrawals/payments (money out) should be stored as negative values."""
        batch_id = tmp_db.create_batch("withdrawals.csv")
        txn_id = tmp_db.insert_transaction(
            batch_id=batch_id,
            posted_date="2024-03-04",
            description="ATM Withdrawal",
            amount=-1000.00,  # negative
            fingerprint="atm-fp",
        )
        txn = tmp_db.get_transaction(txn_id)
        assert txn["amount"] < 0

    def test_reconciliation_sum_uses_signed_amounts(self):
        """Reconciliation math uses signed amounts; outflows reduce the balance."""
        result = compute_reconciliation(
            beginning_balance=14261.82,
            ending_balance=14261.82,  # same – means no net change
            amounts=[1000.00, -500.00, -500.00],  # net = 0
        )
        assert result.sum_transactions == pytest.approx(0.00)
        assert result.is_balanced is True
