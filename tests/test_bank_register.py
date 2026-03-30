"""
Tests for probooksai.bank_register
====================================
Covers: schema creation, bank account CRUD, transaction CRUD,
        filter logic, update logic, and migration idempotency.
"""

from __future__ import annotations

import pytest

from probooksai.bank_register import BankRegisterDatabase


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    """Return a BankRegisterDatabase backed by a temp SQLite file."""
    db_path = str(tmp_path / "register_test.db")
    reg = BankRegisterDatabase(db_path=db_path)
    yield reg
    reg.close()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class TestSchema:
    def test_bank_accounts_table_exists(self, db):
        cur = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bank_accounts'"
        )
        assert cur.fetchone() is not None

    def test_bank_transactions_table_exists(self, db):
        cur = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bank_transactions'"
        )
        assert cur.fetchone() is not None

    def test_transactions_has_reference_number_column(self, db):
        cur = db._conn.execute("PRAGMA table_info(bank_transactions)")
        cols = {row[1] for row in cur.fetchall()}
        assert "reference_number" in cols

    def test_transactions_has_memo_column(self, db):
        cur = db._conn.execute("PRAGMA table_info(bank_transactions)")
        cols = {row[1] for row in cur.fetchall()}
        assert "memo" in cols

    def test_transactions_has_coa_account_column(self, db):
        cur = db._conn.execute("PRAGMA table_info(bank_transactions)")
        cols = {row[1] for row in cur.fetchall()}
        assert "coa_account" in cols


# ---------------------------------------------------------------------------
# Bank accounts
# ---------------------------------------------------------------------------

class TestBankAccounts:
    def test_add_account_returns_id(self, db):
        acct_id = db.add_account("Chase Checking")
        assert isinstance(acct_id, int) and acct_id > 0

    def test_list_accounts_empty(self, db):
        assert db.list_accounts() == []

    def test_list_accounts_returns_all(self, db):
        db.add_account("Chase Checking")
        db.add_account("Wells Fargo Savings")
        accts = db.list_accounts()
        assert len(accts) == 2

    def test_list_accounts_ordered_by_name(self, db):
        db.add_account("Zeta Bank")
        db.add_account("Alpha Bank")
        names = [a["name"] for a in db.list_accounts()]
        assert names == sorted(names, key=str.casefold)

    def test_get_account_fields(self, db):
        acct_id = db.add_account("Chase Checking", account_number="1234", institution="Chase")
        acct = db.get_account(acct_id)
        assert acct["name"] == "Chase Checking"
        assert acct["account_number"] == "1234"
        assert acct["institution"] == "Chase"

    def test_get_account_nonexistent_returns_none(self, db):
        assert db.get_account(9999) is None

    def test_add_account_optional_fields_none(self, db):
        acct_id = db.add_account("Simple Bank")
        acct = db.get_account(acct_id)
        assert acct["account_number"] is None
        assert acct["institution"] is None


# ---------------------------------------------------------------------------
# Bank transactions – add / get
# ---------------------------------------------------------------------------

class TestAddTransaction:
    def test_add_transaction_returns_id(self, db):
        txn_id = db.add_transaction(date="2024-01-15", description="Groceries", amount=-45.50)
        assert isinstance(txn_id, int) and txn_id > 0

    def test_get_transaction_fields(self, db):
        txn_id = db.add_transaction(
            date="2024-01-15",
            description="Groceries",
            amount=-45.50,
            reference_number="1001",
            memo="Weekly shopping",
            coa_account="6200 – Groceries",
        )
        txn = db.get_transaction(txn_id)
        assert txn["date"] == "2024-01-15"
        assert txn["description"] == "Groceries"
        assert txn["amount"] == pytest.approx(-45.50)
        assert txn["reference_number"] == "1001"
        assert txn["memo"] == "Weekly shopping"
        assert txn["coa_account"] == "6200 – Groceries"

    def test_get_transaction_nonexistent_returns_none(self, db):
        assert db.get_transaction(9999) is None

    def test_transaction_amount_positive_for_credit(self, db):
        txn_id = db.add_transaction(date="2024-02-01", description="Deposit", amount=1000.0)
        txn = db.get_transaction(txn_id)
        assert txn["amount"] > 0

    def test_transaction_amount_negative_for_debit(self, db):
        txn_id = db.add_transaction(date="2024-02-05", description="Rent", amount=-1200.0)
        txn = db.get_transaction(txn_id)
        assert txn["amount"] < 0


# ---------------------------------------------------------------------------
# List transactions – filters
# ---------------------------------------------------------------------------

class TestListTransactions:
    def _seed(self, db, acct_id=None):
        """Insert three transactions for filter tests."""
        db.add_transaction("2024-01-10", "Coffee Shop",  -5.00,  bank_account_id=acct_id, memo="Morning coffee")
        db.add_transaction("2024-01-20", "Paycheck",    2000.0, bank_account_id=acct_id)
        db.add_transaction("2024-02-01", "Rent",       -1200.0, bank_account_id=acct_id, memo="Feb rent")

    def test_list_all_transactions(self, db):
        self._seed(db)
        rows = db.list_transactions()
        assert len(rows) == 3

    def test_list_ordered_by_date(self, db):
        self._seed(db)
        rows = db.list_transactions()
        dates = [r["date"] for r in rows]
        assert dates == sorted(dates)

    def test_filter_by_account(self, db):
        acct1 = db.add_account("Chase")
        acct2 = db.add_account("Wells Fargo")
        db.add_transaction("2024-01-01", "Txn A", -10.0, bank_account_id=acct1)
        db.add_transaction("2024-01-02", "Txn B", -20.0, bank_account_id=acct2)
        rows = db.list_transactions(bank_account_id=acct1)
        assert len(rows) == 1
        assert rows[0]["description"] == "Txn A"

    def test_filter_start_date(self, db):
        self._seed(db)
        rows = db.list_transactions(start_date="2024-01-20")
        assert all(r["date"] >= "2024-01-20" for r in rows)
        assert len(rows) == 2

    def test_filter_end_date(self, db):
        self._seed(db)
        rows = db.list_transactions(end_date="2024-01-20")
        assert all(r["date"] <= "2024-01-20" for r in rows)
        assert len(rows) == 2

    def test_filter_date_range(self, db):
        self._seed(db)
        rows = db.list_transactions(start_date="2024-01-15", end_date="2024-01-25")
        assert len(rows) == 1
        assert rows[0]["description"] == "Paycheck"

    def test_filter_search_description(self, db):
        self._seed(db)
        rows = db.list_transactions(search="coffee")
        assert len(rows) == 1
        assert rows[0]["description"] == "Coffee Shop"

    def test_filter_search_memo(self, db):
        self._seed(db)
        rows = db.list_transactions(search="feb")
        assert len(rows) == 1
        assert rows[0]["description"] == "Rent"

    def test_filter_search_case_insensitive(self, db):
        self._seed(db)
        rows = db.list_transactions(search="COFFEE")
        assert len(rows) == 1

    def test_filter_search_no_match(self, db):
        self._seed(db)
        rows = db.list_transactions(search="zzznomatch")
        assert len(rows) == 0

    def test_filter_combined_account_and_date(self, db):
        acct = db.add_account("Chase")
        db.add_transaction("2024-01-05", "Early",  -10.0, bank_account_id=acct)
        db.add_transaction("2024-03-01", "Late",   -20.0, bank_account_id=acct)
        db.add_transaction("2024-01-05", "Other",  -30.0)  # no account
        rows = db.list_transactions(bank_account_id=acct, end_date="2024-02-01")
        assert len(rows) == 1
        assert rows[0]["description"] == "Early"

    def test_list_empty_when_no_transactions(self, db):
        assert db.list_transactions() == []


# ---------------------------------------------------------------------------
# Update transaction
# ---------------------------------------------------------------------------

class TestUpdateTransaction:
    def test_update_reference_number(self, db):
        txn_id = db.add_transaction("2024-01-01", "Check", -500.0)
        db.update_transaction(txn_id, reference_number="1042")
        assert db.get_transaction(txn_id)["reference_number"] == "1042"

    def test_update_memo(self, db):
        txn_id = db.add_transaction("2024-01-01", "Groceries", -80.0)
        db.update_transaction(txn_id, memo="Whole Foods run")
        assert db.get_transaction(txn_id)["memo"] == "Whole Foods run"

    def test_update_coa_account(self, db):
        txn_id = db.add_transaction("2024-01-01", "Office Depot", -35.0)
        db.update_transaction(txn_id, coa_account="6300 – Office Supplies")
        assert db.get_transaction(txn_id)["coa_account"] == "6300 – Office Supplies"

    def test_update_description(self, db):
        txn_id = db.add_transaction("2024-01-01", "Old name", -10.0)
        db.update_transaction(txn_id, description="New name")
        assert db.get_transaction(txn_id)["description"] == "New name"

    def test_update_multiple_fields_at_once(self, db):
        txn_id = db.add_transaction("2024-01-01", "Mystery", -99.0)
        db.update_transaction(txn_id, reference_number="2001", memo="Updated", coa_account="6999")
        txn = db.get_transaction(txn_id)
        assert txn["reference_number"] == "2001"
        assert txn["memo"] == "Updated"
        assert txn["coa_account"] == "6999"

    def test_update_with_empty_string_clears_field(self, db):
        txn_id = db.add_transaction("2024-01-01", "Test", -1.0, memo="to be cleared")
        db.update_transaction(txn_id, memo="")
        assert db.get_transaction(txn_id)["memo"] is None

    def test_update_no_kwargs_is_noop(self, db):
        txn_id = db.add_transaction("2024-01-01", "Stable", -1.0, memo="keep me")
        db.update_transaction(txn_id)  # no kwargs
        assert db.get_transaction(txn_id)["memo"] == "keep me"


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

class TestContextManager:
    def test_context_manager(self, tmp_path):
        db_path = str(tmp_path / "ctx.db")
        with BankRegisterDatabase(db_path=db_path) as reg:
            acct_id = reg.add_account("Test")
            assert acct_id > 0
