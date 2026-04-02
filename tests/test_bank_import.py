"""
Tests for probooksai.bank_import – CSV parsing, deduplication, and database operations.
"""

from __future__ import annotations

import pytest

from probooksai.bank_import import (
    BankDatabase,
    ACCOUNT_TYPES,
    parse_date,
    parse_amount,
    parse_csv,
    make_fingerprint,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    """Isolated BankDatabase backed by a temp SQLite file."""
    bdb = BankDatabase(db_path=str(tmp_path / "bank_test.db"))
    yield bdb
    bdb.close()


CSV_SIMPLE = """\
Date,Description,Amount
2024-01-05,Coffee Shop,-4.50
2024-01-10,Paycheck,2500.00
2024-01-15,Grocery Store,-85.00
2024-01-20,Electric Bill,-120.00
"""

CSV_ALTERNATE_FORMAT = """\
TXN_DATE,MEMO,DEBIT,CREDIT
01/05/2024,Coffee Shop,4.50,
01/10/2024,Paycheck,,2500.00
"""


# ===========================================================================
# parse_date
# ===========================================================================

class TestParseDate:
    @pytest.mark.parametrize("raw,expected", [
        ("2024-01-05",    "2024-01-05"),
        ("01/05/2024",    "2024-01-05"),
        ("01/05/24",      "2024-01-05"),
        ("05/01/2024",    "2024-05-01"),   # d/m/y
        ("January 5, 2024", "2024-01-05"),
        ("Jan 5, 2024",   "2024-01-05"),
        ("20240105",      "2024-01-05"),
    ])
    def test_valid_formats(self, raw, expected):
        assert parse_date(raw) == expected

    def test_whitespace_stripped(self):
        assert parse_date("  2024-01-05  ") == "2024-01-05"

    def test_invalid_returns_none(self):
        assert parse_date("not-a-date") is None

    def test_empty_returns_none(self):
        assert parse_date("") is None


# ===========================================================================
# parse_amount
# ===========================================================================

class TestParseAmount:
    @pytest.mark.parametrize("raw,expected", [
        ("4.50",       4.50),
        ("-4.50",      -4.50),
        ("$1,234.56",  1234.56),
        ("(1,234.56)", -1234.56),
        (" 100 ",      100.0),
        ("£50.00",     50.0),
        ("€200.00",    200.0),
        ("0",          0.0),
    ])
    def test_valid_amounts(self, raw, expected):
        assert parse_amount(raw) == pytest.approx(expected)

    def test_invalid_returns_none(self):
        assert parse_amount("N/A") is None

    def test_empty_returns_none(self):
        assert parse_amount("") is None


# ===========================================================================
# parse_csv
# ===========================================================================

class TestParseCsv:
    def test_basic_parse(self):
        rows = parse_csv(CSV_SIMPLE, date_col="Date", amount_col="Amount", description_col="Description")
        assert len(rows) == 4

    def test_date_parsed(self):
        rows = parse_csv(CSV_SIMPLE, date_col="Date", amount_col="Amount")
        assert rows[0]["txn_date"] == "2024-01-05"

    def test_amount_parsed(self):
        rows = parse_csv(CSV_SIMPLE, date_col="Date", amount_col="Amount", description_col="Description")
        assert rows[0]["amount"] == pytest.approx(-4.50)
        assert rows[1]["amount"] == pytest.approx(2500.00)

    def test_description_captured(self):
        rows = parse_csv(CSV_SIMPLE, date_col="Date", amount_col="Amount", description_col="Description")
        assert rows[0]["description"] == "Coffee Shop"

    def test_missing_date_col_skips_row(self):
        # Wrong column name → all rows skipped
        rows = parse_csv(CSV_SIMPLE, date_col="WrongCol", amount_col="Amount")
        assert len(rows) == 0

    def test_unparseable_date_skips_row(self):
        csv_bad = "Date,Amount\nnot-a-date,10.00\n2024-01-01,5.00\n"
        rows = parse_csv(csv_bad, date_col="Date", amount_col="Amount")
        assert len(rows) == 1

    def test_unparseable_amount_skips_row(self):
        csv_bad = "Date,Amount\n2024-01-01,N/A\n2024-01-02,5.00\n"
        rows = parse_csv(csv_bad, date_col="Date", amount_col="Amount")
        assert len(rows) == 1

    def test_no_description_col_defaults_empty(self):
        rows = parse_csv(CSV_SIMPLE, date_col="Date", amount_col="Amount")
        assert rows[0]["description"] == ""

    def test_ref_col_captured(self):
        csv_ref = "Date,Amount,Ref\n2024-01-01,100.00,CHK123\n"
        rows = parse_csv(csv_ref, date_col="Date", amount_col="Amount", ref_col="Ref")
        assert rows[0]["ref_number"] == "CHK123"


# ===========================================================================
# make_fingerprint
# ===========================================================================

class TestMakeFingerprint:
    def test_deterministic(self):
        fp1 = make_fingerprint(1, "2024-01-05", "Coffee", -4.50, "")
        fp2 = make_fingerprint(1, "2024-01-05", "Coffee", -4.50, "")
        assert fp1 == fp2

    def test_different_accounts_differ(self):
        fp1 = make_fingerprint(1, "2024-01-05", "Coffee", -4.50)
        fp2 = make_fingerprint(2, "2024-01-05", "Coffee", -4.50)
        assert fp1 != fp2

    def test_different_amounts_differ(self):
        fp1 = make_fingerprint(1, "2024-01-05", "Coffee", -4.50)
        fp2 = make_fingerprint(1, "2024-01-05", "Coffee", -5.00)
        assert fp1 != fp2

    def test_returns_hex_string(self):
        fp = make_fingerprint(1, "2024-01-05", "Coffee", -4.50)
        assert len(fp) == 64
        int(fp, 16)   # no exception → valid hex


# ===========================================================================
# BankDatabase – bank_accounts
# ===========================================================================

class TestBankAccounts:
    def test_add_returns_id(self, db):
        aid = db.add_bank_account("Chase Checking")
        assert isinstance(aid, int) and aid > 0

    def test_get_returns_row(self, db):
        aid = db.add_bank_account("Chase Checking", account_number="1234",
                                  bank_name="Chase", account_type="checking")
        row = db.get_bank_account(aid)
        assert row["name"] == "Chase Checking"
        assert row["account_number"] == "1234"
        assert row["bank_name"] == "Chase"
        assert row["account_type"] == "checking"

    def test_list_empty(self, db):
        assert db.list_bank_accounts() == []

    def test_list_returns_all(self, db):
        db.add_bank_account("Account A")
        db.add_bank_account("Account B")
        assert len(db.list_bank_accounts()) == 2

    def test_list_ordered_by_name(self, db):
        db.add_bank_account("Zebra")
        db.add_bank_account("Apple")
        names = [r["name"] for r in db.list_bank_accounts()]
        assert names == sorted(names)

    def test_update_changes_fields(self, db):
        aid = db.add_bank_account("Old Name")
        db.update_bank_account(aid, "New Name", "9999", "Wells Fargo", "savings")
        row = db.get_bank_account(aid)
        assert row["name"] == "New Name"
        assert row["account_type"] == "savings"

    def test_delete_removes_account(self, db):
        aid = db.add_bank_account("Temp Account")
        db.delete_bank_account(aid)
        assert db.get_bank_account(aid) is None

    def test_invalid_account_type_raises(self, db):
        with pytest.raises(ValueError):
            db.add_bank_account("Bad", account_type="invalid_type")

    @pytest.mark.parametrize("atype", ACCOUNT_TYPES)
    def test_all_account_types_accepted(self, db, atype):
        aid = db.add_bank_account(f"Account {atype}", account_type=atype)
        row = db.get_bank_account(aid)
        assert row["account_type"] == atype

    def test_get_nonexistent_returns_none(self, db):
        assert db.get_bank_account(9999) is None


# ===========================================================================
# BankDatabase – batches
# ===========================================================================

class TestImportBatches:
    def _account(self, db):
        return db.add_bank_account("Test Account")

    def test_create_batch_returns_id(self, db):
        aid = self._account(db)
        bid = db.create_batch(aid)
        assert isinstance(bid, int) and bid > 0

    def test_get_batch_fields(self, db):
        aid = self._account(db)
        bid = db.create_batch(
            aid,
            filename="jan.csv",
            statement_start="2024-01-01",
            statement_end="2024-01-31",
            beginning_balance=1000.0,
            ending_balance=1500.0,
        )
        batch = db.get_batch(bid)
        assert batch["bank_account_id"] == aid
        assert batch["filename"] == "jan.csv"
        assert batch["statement_start"] == "2024-01-01"
        assert batch["statement_end"] == "2024-01-31"
        assert batch["beginning_balance"] == pytest.approx(1000.0)
        assert batch["ending_balance"] == pytest.approx(1500.0)
        assert batch["is_reconciled"] == 0

    def test_list_batches_for_account(self, db):
        aid1 = self._account(db)
        aid2 = db.add_bank_account("Another")
        db.create_batch(aid1)
        db.create_batch(aid1)
        db.create_batch(aid2)
        assert len(db.list_batches(aid1)) == 2
        assert len(db.list_batches(aid2)) == 1

    def test_list_all_batches(self, db):
        aid = self._account(db)
        db.create_batch(aid)
        db.create_batch(aid)
        assert len(db.list_batches()) == 2

    def test_update_batch_statement(self, db):
        aid = self._account(db)
        bid = db.create_batch(aid)
        db.update_batch_statement(bid, "2024-02-01", "2024-02-29", 500.0, 750.0)
        batch = db.get_batch(bid)
        assert batch["statement_start"] == "2024-02-01"
        assert batch["beginning_balance"] == pytest.approx(500.0)

    def test_mark_reconciled(self, db):
        aid = self._account(db)
        bid = db.create_batch(aid)
        db.mark_batch_reconciled(bid, True)
        assert db.get_batch(bid)["is_reconciled"] == 1

    def test_mark_unreconciled(self, db):
        aid = self._account(db)
        bid = db.create_batch(aid)
        db.mark_batch_reconciled(bid, True)
        db.mark_batch_reconciled(bid, False)
        assert db.get_batch(bid)["is_reconciled"] == 0

    def test_delete_account_cascades_to_batches(self, db):
        aid = self._account(db)
        bid = db.create_batch(aid)
        db.delete_bank_account(aid)
        assert db.get_batch(bid) is None


# ===========================================================================
# BankDatabase – transactions
# ===========================================================================

class TestTransactions:
    def _setup(self, db):
        aid = db.add_bank_account("Main Checking")
        bid = db.create_batch(aid, statement_start="2024-01-01", statement_end="2024-01-31")
        return aid, bid

    def test_import_inserts_rows(self, db):
        aid, bid = self._setup(db)
        rows = parse_csv(CSV_SIMPLE, "Date", "Amount", "Description")
        counts = db.import_transactions(bid, aid, rows)
        assert counts["inserted"] == 4
        assert counts["skipped"] == 0

    def test_duplicate_skipped(self, db):
        aid, bid = self._setup(db)
        rows = parse_csv(CSV_SIMPLE, "Date", "Amount", "Description")
        db.import_transactions(bid, aid, rows)
        counts = db.import_transactions(bid, aid, rows)
        assert counts["skipped"] == 4
        assert counts["inserted"] == 0

    def test_list_transactions_all(self, db):
        aid, bid = self._setup(db)
        rows = parse_csv(CSV_SIMPLE, "Date", "Amount", "Description")
        db.import_transactions(bid, aid, rows)
        txns = db.list_transactions(aid)
        assert len(txns) == 4

    def test_list_transactions_date_filter(self, db):
        aid, bid = self._setup(db)
        rows = parse_csv(CSV_SIMPLE, "Date", "Amount", "Description")
        db.import_transactions(bid, aid, rows)
        txns = db.list_transactions(aid, statement_start="2024-01-10", statement_end="2024-01-15")
        # 01-10 paycheck and 01-15 grocery store
        assert len(txns) == 2

    def test_list_transactions_start_only(self, db):
        aid, bid = self._setup(db)
        rows = parse_csv(CSV_SIMPLE, "Date", "Amount", "Description")
        db.import_transactions(bid, aid, rows)
        txns = db.list_transactions(aid, statement_start="2024-01-15")
        assert len(txns) == 2  # 01-15 and 01-20

    def test_list_transactions_end_only(self, db):
        aid, bid = self._setup(db)
        rows = parse_csv(CSV_SIMPLE, "Date", "Amount", "Description")
        db.import_transactions(bid, aid, rows)
        txns = db.list_transactions(aid, statement_end="2024-01-10")
        assert len(txns) == 2  # 01-05 and 01-10

    def test_amount_sign_preserved(self, db):
        aid, bid = self._setup(db)
        rows = parse_csv(CSV_SIMPLE, "Date", "Amount", "Description")
        db.import_transactions(bid, aid, rows)
        txns = db.list_transactions(aid)
        amounts = {t["description"]: t["amount"] for t in txns}
        assert amounts["Coffee Shop"] == pytest.approx(-4.50)
        assert amounts["Paycheck"] == pytest.approx(2500.00)

    def test_get_transaction(self, db):
        aid, bid = self._setup(db)
        rows = parse_csv(CSV_SIMPLE, "Date", "Amount", "Description")
        db.import_transactions(bid, aid, rows)
        txns = db.list_transactions(aid)
        txn = db.get_transaction(txns[0]["id"])
        assert txn is not None
        assert txn["bank_account_id"] == aid


# ===========================================================================
# BankDatabase – import_csv pipeline
# ===========================================================================

class TestImportCsvPipeline:
    def test_import_csv_creates_batch_and_transactions(self, db):
        aid = db.add_bank_account("Pipeline Account")
        result = db.import_csv(
            bank_account_id=aid,
            csv_content=CSV_SIMPLE,
            date_col="Date",
            amount_col="Amount",
            description_col="Description",
            filename="simple.csv",
            statement_start="2024-01-01",
            statement_end="2024-01-31",
            beginning_balance=1000.0,
            ending_balance=3290.50,
        )
        assert result["batch_id"] > 0
        assert result["inserted"] == 4
        assert result["skipped"] == 0

    def test_import_csv_second_pass_deduplicates(self, db):
        aid = db.add_bank_account("Dedup Account")
        db.import_csv(aid, CSV_SIMPLE, "Date", "Amount", "Description")
        result = db.import_csv(aid, CSV_SIMPLE, "Date", "Amount", "Description")
        assert result["skipped"] == 4

    def test_context_manager(self, tmp_path):
        with BankDatabase(db_path=str(tmp_path / "cm.db")) as bdb:
            aid = bdb.add_bank_account("CM Account")
            assert aid > 0
