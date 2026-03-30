"""
Tests for the Bank Import feature (Issue #9, Phase 1 – CSV-first).

Covers:
- CSV parsing + column mapping
- Date parsing for common formats including DD/MM/YYYY
- Amount parsing
- Duplicate detection logic
- DB persistence (insert / update / status changes)
"""

from __future__ import annotations

import csv
import textwrap
from datetime import date
from pathlib import Path

import pytest

from probooksai.bank_import import (
    ColumnMapping,
    ParsedTransaction,
    compute_fingerprint,
    flag_duplicates,
    parse_amount,
    parse_csv,
    parse_date,
    read_csv_preview,
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


def _write_csv(tmp_path: Path, name: str, content: str) -> str:
    """Write *content* to a CSV file inside *tmp_path* and return the path."""
    p = tmp_path / name
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------


class TestParseDate:
    def test_ddmmyyyy_slash(self):
        """Default format: DD/MM/YYYY."""
        assert parse_date("15/01/2025") == date(2025, 1, 15)

    def test_ddmmyyyy_dash(self):
        assert parse_date("15-01-2025") == date(2025, 1, 15)

    def test_ddmmyyyy_dot(self):
        assert parse_date("15.01.2025") == date(2025, 1, 15)

    def test_iso_8601(self):
        assert parse_date("2025-01-15") == date(2025, 1, 15)

    def test_us_format_mmddyyyy(self):
        assert parse_date("01/15/2025") == date(2025, 1, 15)

    def test_two_digit_year(self):
        assert parse_date("15/01/25") == date(2025, 1, 15)

    def test_text_month_short(self):
        assert parse_date("15 Jan 2025") == date(2025, 1, 15)

    def test_text_month_long(self):
        assert parse_date("15 January 2025") == date(2025, 1, 15)

    def test_us_text_month(self):
        assert parse_date("Jan 15, 2025") == date(2025, 1, 15)

    def test_whitespace_stripped(self):
        assert parse_date("  15/01/2025  ") == date(2025, 1, 15)

    def test_invalid_returns_none(self):
        assert parse_date("not-a-date") is None

    def test_empty_string_returns_none(self):
        assert parse_date("") is None


# ---------------------------------------------------------------------------
# Amount parsing
# ---------------------------------------------------------------------------


class TestParseAmount:
    def test_simple_positive(self):
        assert parse_amount("123.45") == pytest.approx(123.45)

    def test_negative_dash(self):
        assert parse_amount("-50.00") == pytest.approx(-50.0)

    def test_parenthesised_negative(self):
        assert parse_amount("(75.50)") == pytest.approx(-75.50)

    def test_currency_symbol_stripped(self):
        assert parse_amount("$1,234.56") == pytest.approx(1234.56)

    def test_pound_symbol(self):
        assert parse_amount("£99.99") == pytest.approx(99.99)

    def test_thousands_separator(self):
        assert parse_amount("1,234.56") == pytest.approx(1234.56)

    def test_european_decimal_comma(self):
        assert parse_amount("1.234,56") == pytest.approx(1234.56)

    def test_zero(self):
        assert parse_amount("0.00") == pytest.approx(0.0)

    def test_empty_returns_none(self):
        assert parse_amount("") is None

    def test_invalid_returns_none(self):
        assert parse_amount("N/A") is None


# ---------------------------------------------------------------------------
# ColumnMapping auto-detection
# ---------------------------------------------------------------------------


class TestColumnMappingAutoDetect:
    def test_detects_date(self):
        m = ColumnMapping.auto_detect(["Date", "Description", "Amount"])
        assert m.date == "Date"

    def test_detects_posted_date(self):
        m = ColumnMapping.auto_detect(["Posted Date", "Narrative", "Amount"])
        assert m.date == "Posted Date"

    def test_detects_description_as_memo(self):
        m = ColumnMapping.auto_detect(["Date", "Memo", "Amount"])
        assert m.description == "Memo"

    def test_detects_debit_credit(self):
        m = ColumnMapping.auto_detect(["Date", "Description", "Debit", "Credit"])
        assert m.debit == "Debit"
        assert m.credit == "Credit"

    def test_case_insensitive(self):
        m = ColumnMapping.auto_detect(["DATE", "DESCRIPTION", "AMOUNT"])
        assert m.date == "DATE"
        assert m.description == "DESCRIPTION"
        assert m.amount == "AMOUNT"


class TestColumnMappingValidation:
    def test_valid_with_amount(self):
        m = ColumnMapping(date="Date", description="Desc", amount="Amount")
        assert m.validate() == []

    def test_valid_with_debit_credit(self):
        m = ColumnMapping(date="Date", description="Desc", debit="Debit", credit="Credit")
        assert m.validate() == []

    def test_missing_date(self):
        m = ColumnMapping(description="Desc", amount="Amount")
        errors = m.validate()
        assert any("date" in e.lower() for e in errors)

    def test_missing_description(self):
        m = ColumnMapping(date="Date", amount="Amount")
        errors = m.validate()
        assert any("description" in e.lower() for e in errors)

    def test_missing_amount_columns(self):
        m = ColumnMapping(date="Date", description="Desc")
        errors = m.validate()
        assert any("amount" in e.lower() or "debit" in e.lower() for e in errors)

    def test_only_one_of_debit_credit_is_invalid(self):
        m = ColumnMapping(date="Date", description="Desc", debit="Debit")
        errors = m.validate()
        assert errors  # must have an error: credit is missing


# ---------------------------------------------------------------------------
# read_csv_preview
# ---------------------------------------------------------------------------


class TestReadCsvPreview:
    def test_returns_headers_and_rows(self, tmp_path):
        path = _write_csv(
            tmp_path,
            "bank.csv",
            """\
            Date,Description,Amount
            15/01/2025,Grocery Store,-45.00
            16/01/2025,Salary,3000.00
            """,
        )
        headers, rows = read_csv_preview(path)
        assert headers == ["Date", "Description", "Amount"]
        assert len(rows) == 2

    def test_preview_limited_to_max_rows(self, tmp_path):
        lines = "Date,Description,Amount\n"
        for i in range(20):
            lines += f"{i+1:02d}/01/2025,Item {i},-{i}.00\n"
        path = str(tmp_path / "big.csv")
        Path(path).write_text(lines, encoding="utf-8")
        _, rows = read_csv_preview(path, max_rows=10)
        assert len(rows) == 10

    def test_handles_utf8_bom(self, tmp_path):
        """CSV files exported from Excel often have a BOM."""
        p = tmp_path / "bom.csv"
        p.write_bytes(
            "Date,Description,Amount\n15/01/2025,Test,-10.00\n".encode("utf-8-sig")
        )
        headers, _ = read_csv_preview(str(p))
        assert headers[0] == "Date"


# ---------------------------------------------------------------------------
# parse_csv
# ---------------------------------------------------------------------------


class TestParseCsv:
    def _make_mapping(self):
        return ColumnMapping(date="Date", description="Description", amount="Amount")

    def test_basic_parse(self, tmp_path):
        path = _write_csv(
            tmp_path,
            "basic.csv",
            """\
            Date,Description,Amount
            15/01/2025,Coffee,-4.50
            16/01/2025,Salary,3000.00
            """,
        )
        txns = parse_csv(path, self._make_mapping())
        assert len(txns) == 2
        assert txns[0].posted_date == date(2025, 1, 15)
        assert txns[0].description == "Coffee"
        assert txns[0].amount == pytest.approx(-4.50)
        assert txns[1].amount == pytest.approx(3000.0)

    def test_debit_credit_columns(self, tmp_path):
        path = _write_csv(
            tmp_path,
            "dc.csv",
            """\
            Date,Description,Debit,Credit
            15/01/2025,Shop,45.00,
            16/01/2025,Salary,,3000.00
            """,
        )
        mapping = ColumnMapping(
            date="Date", description="Description",
            debit="Debit", credit="Credit"
        )
        txns = parse_csv(path, mapping)
        assert txns[0].amount == pytest.approx(-45.0)   # debit → negative
        assert txns[1].amount == pytest.approx(3000.0)  # credit → positive

    def test_parse_errors_recorded(self, tmp_path):
        path = _write_csv(
            tmp_path,
            "err.csv",
            """\
            Date,Description,Amount
            NOT-A-DATE,Broken row,abc
            """,
        )
        txns = parse_csv(path, self._make_mapping())
        assert len(txns) == 1
        assert txns[0].posted_date is None
        assert txns[0].amount is None
        assert txns[0].parse_errors  # should have at least one error

    def test_fingerprint_is_set(self, tmp_path):
        path = _write_csv(
            tmp_path,
            "fp.csv",
            """\
            Date,Description,Amount
            15/01/2025,Coffee,-4.50
            """,
        )
        txns = parse_csv(path, self._make_mapping(), source_filename="fp.csv")
        assert txns[0].fingerprint != ""

    def test_source_row_index(self, tmp_path):
        path = _write_csv(
            tmp_path,
            "rows.csv",
            """\
            Date,Description,Amount
            15/01/2025,First,-1.00
            16/01/2025,Second,-2.00
            """,
        )
        txns = parse_csv(path, self._make_mapping())
        assert txns[0].source_row == 2  # row 1 = header, data starts at 2
        assert txns[1].source_row == 3

    def test_currency_column(self, tmp_path):
        path = _write_csv(
            tmp_path,
            "cur.csv",
            """\
            Date,Description,Amount,Currency
            15/01/2025,Shop,-10.00,GBP
            """,
        )
        mapping = ColumnMapping(
            date="Date", description="Description",
            amount="Amount", currency="Currency"
        )
        txns = parse_csv(path, mapping)
        assert txns[0].currency == "GBP"

    def test_whitespace_stripped_from_headers(self, tmp_path):
        """CSV exported with space-padded headers should still parse."""
        p = tmp_path / "spaces.csv"
        p.write_text(" Date , Description , Amount \n15/01/2025,Test,-1.00\n")
        txns = parse_csv(str(p), self._make_mapping())
        assert len(txns) == 1


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------


class TestFingerprintAndDuplicates:
    def test_same_input_same_fingerprint(self):
        d = date(2025, 1, 15)
        fp1 = compute_fingerprint(d, -4.5, "Coffee", "bank.csv")
        fp2 = compute_fingerprint(d, -4.5, "Coffee", "bank.csv")
        assert fp1 == fp2

    def test_different_amount_different_fingerprint(self):
        d = date(2025, 1, 15)
        fp1 = compute_fingerprint(d, -4.5, "Coffee", "bank.csv")
        fp2 = compute_fingerprint(d, -5.0, "Coffee", "bank.csv")
        assert fp1 != fp2

    def test_different_description_different_fingerprint(self):
        d = date(2025, 1, 15)
        fp1 = compute_fingerprint(d, -4.5, "Coffee", "bank.csv")
        fp2 = compute_fingerprint(d, -4.5, "Tea", "bank.csv")
        assert fp1 != fp2

    def test_description_normalised_case(self):
        d = date(2025, 1, 15)
        fp1 = compute_fingerprint(d, -4.5, "COFFEE SHOP", "bank.csv")
        fp2 = compute_fingerprint(d, -4.5, "coffee shop", "bank.csv")
        assert fp1 == fp2

    def test_description_normalised_whitespace(self):
        d = date(2025, 1, 15)
        fp1 = compute_fingerprint(d, -4.5, "Coffee  Shop", "bank.csv")
        fp2 = compute_fingerprint(d, -4.5, "Coffee Shop", "bank.csv")
        assert fp1 == fp2

    def test_flag_duplicates_detects_dupes(self):
        d = date(2025, 1, 15)
        fp = compute_fingerprint(d, -4.5, "Coffee", "bank.csv")
        t1 = ParsedTransaction(2, d, "Coffee", -4.5)
        t1.fingerprint = fp
        t2 = ParsedTransaction(3, d, "Coffee", -4.5)
        t2.fingerprint = fp
        result = flag_duplicates([t1, t2])
        assert fp in result
        assert set(result[fp]) == {2, 3}

    def test_flag_duplicates_no_dupes(self):
        d = date(2025, 1, 15)
        t1 = ParsedTransaction(2, d, "Coffee", -4.5)
        t1.fingerprint = compute_fingerprint(d, -4.5, "Coffee", "bank.csv")
        t2 = ParsedTransaction(3, d, "Tea", -2.0)
        t2.fingerprint = compute_fingerprint(d, -2.0, "Tea", "bank.csv")
        result = flag_duplicates([t1, t2])
        assert result == {}

    def test_flag_duplicates_three_copies(self):
        d = date(2025, 1, 15)
        fp = compute_fingerprint(d, -4.5, "X", "f.csv")
        txns = []
        for row in [2, 3, 4]:
            t = ParsedTransaction(row, d, "X", -4.5)
            t.fingerprint = fp
            txns.append(t)
        result = flag_duplicates(txns)
        assert len(result[fp]) == 3


# ---------------------------------------------------------------------------
# Database – bank import tables
# ---------------------------------------------------------------------------


class TestBankImportBatches:
    def test_create_batch_returns_id(self, tmp_db):
        batch_id = tmp_db.create_batch("statement.csv")
        assert isinstance(batch_id, int) and batch_id > 0

    def test_get_batch(self, tmp_db):
        batch_id = tmp_db.create_batch("statement.csv", format_meta="csv")
        row = tmp_db.get_batch(batch_id)
        assert row["source_filename"] == "statement.csv"
        assert row["format_meta"] == "csv"

    def test_list_batches_empty(self, tmp_db):
        assert tmp_db.list_batches() == []

    def test_list_batches_returns_all(self, tmp_db):
        tmp_db.create_batch("a.csv")
        tmp_db.create_batch("b.csv")
        batches = tmp_db.list_batches()
        assert len(batches) == 2


class TestBankTransactions:
    def _insert(self, tmp_db, batch_id, **kwargs):
        defaults = dict(
            posted_date="2025-01-15",
            description="Coffee",
            amount=-4.50,
            fingerprint="fp-abc",
        )
        defaults.update(kwargs)
        return tmp_db.insert_transaction(batch_id=batch_id, **defaults)

    def test_insert_returns_id(self, tmp_db):
        bid = tmp_db.create_batch("s.csv")
        txn_id = self._insert(tmp_db, bid)
        assert isinstance(txn_id, int) and txn_id > 0

    def test_get_transaction(self, tmp_db):
        bid = tmp_db.create_batch("s.csv")
        txn_id = self._insert(tmp_db, bid, description="Salary", amount=3000.0)
        row = tmp_db.get_transaction(txn_id)
        assert row["description"] == "Salary"
        assert row["amount"] == pytest.approx(3000.0)
        assert row["status"] == "Imported"

    def test_default_status_is_imported(self, tmp_db):
        bid = tmp_db.create_batch("s.csv")
        txn_id = self._insert(tmp_db, bid)
        row = tmp_db.get_transaction(txn_id)
        assert row["status"] == "Imported"

    def test_is_duplicate_flag(self, tmp_db):
        bid = tmp_db.create_batch("s.csv")
        txn_id = self._insert(tmp_db, bid, is_duplicate=True)
        row = tmp_db.get_transaction(txn_id)
        assert row["is_duplicate"] == 1

    def test_list_transactions_by_batch(self, tmp_db):
        bid1 = tmp_db.create_batch("s1.csv")
        bid2 = tmp_db.create_batch("s2.csv")
        self._insert(tmp_db, bid1, fingerprint="fp1")
        self._insert(tmp_db, bid2, fingerprint="fp2")
        rows = tmp_db.list_transactions(batch_id=bid1)
        assert len(rows) == 1
        assert rows[0]["fingerprint"] == "fp1"

    def test_list_transactions_status_filter(self, tmp_db):
        bid = tmp_db.create_batch("s.csv")
        t1 = self._insert(tmp_db, bid, fingerprint="fp1", status="Imported")
        t2 = self._insert(tmp_db, bid, fingerprint="fp2", status="Reviewed")
        rows = tmp_db.list_transactions(batch_id=bid, status="Reviewed")
        assert len(rows) == 1
        assert rows[0]["status"] == "Reviewed"

    def test_list_transactions_search_filter(self, tmp_db):
        bid = tmp_db.create_batch("s.csv")
        self._insert(tmp_db, bid, fingerprint="fp1", description="Coffee Shop")
        self._insert(tmp_db, bid, fingerprint="fp2", description="Salary")
        rows = tmp_db.list_transactions(batch_id=bid, search="Coffee")
        assert len(rows) == 1
        assert "Coffee" in rows[0]["description"]

    def test_list_transactions_needs_review_only(self, tmp_db):
        bid = tmp_db.create_batch("s.csv")
        # No COA → needs review
        self._insert(tmp_db, bid, fingerprint="fp1", coa_account=None)
        # Has COA → not flagged
        self._insert(tmp_db, bid, fingerprint="fp2", coa_account="6100 – Rent")
        rows = tmp_db.list_transactions(batch_id=bid, needs_review_only=True)
        assert len(rows) == 1
        assert rows[0]["coa_account"] is None


class TestUpdateTransaction:
    def _insert(self, db, batch_id, **kwargs):
        defaults = dict(
            posted_date="2025-01-15",
            description="Test",
            amount=-1.0,
            fingerprint="fp-x",
        )
        defaults.update(kwargs)
        return db.insert_transaction(batch_id=batch_id, **defaults)

    def test_update_description(self, tmp_db):
        bid = tmp_db.create_batch("s.csv")
        txn_id = self._insert(tmp_db, bid)
        tmp_db.update_transaction(txn_id, description="Updated Description")
        row = tmp_db.get_transaction(txn_id)
        assert row["description"] == "Updated Description"

    def test_update_coa_account(self, tmp_db):
        bid = tmp_db.create_batch("s.csv")
        txn_id = self._insert(tmp_db, bid)
        tmp_db.update_transaction(txn_id, coa_account="1000 – Cash")
        row = tmp_db.get_transaction(txn_id)
        assert row["coa_account"] == "1000 – Cash"

    def test_update_status_to_reviewed(self, tmp_db):
        bid = tmp_db.create_batch("s.csv")
        txn_id = self._insert(tmp_db, bid)
        tmp_db.update_transaction(txn_id, status="Reviewed")
        row = tmp_db.get_transaction(txn_id)
        assert row["status"] == "Reviewed"

    def test_update_invalid_status_raises(self, tmp_db):
        bid = tmp_db.create_batch("s.csv")
        txn_id = self._insert(tmp_db, bid)
        with pytest.raises(ValueError):
            tmp_db.update_transaction(txn_id, status="NotAStatus")

    def test_update_amount(self, tmp_db):
        bid = tmp_db.create_batch("s.csv")
        txn_id = self._insert(tmp_db, bid)
        tmp_db.update_transaction(txn_id, amount=-99.99)
        row = tmp_db.get_transaction(txn_id)
        assert row["amount"] == pytest.approx(-99.99)


class TestMarkTransactionsReviewed:
    def _insert(self, db, batch_id, fp):
        return db.insert_transaction(
            batch_id=batch_id,
            posted_date="2025-01-15",
            description="Item",
            amount=-1.0,
            fingerprint=fp,
        )

    def test_mark_single_reviewed(self, tmp_db):
        bid = tmp_db.create_batch("s.csv")
        t = self._insert(tmp_db, bid, "fp1")
        tmp_db.mark_transactions_reviewed([t])
        row = tmp_db.get_transaction(t)
        assert row["status"] == "Reviewed"

    def test_mark_multiple_reviewed(self, tmp_db):
        bid = tmp_db.create_batch("s.csv")
        ids = [self._insert(tmp_db, bid, f"fp{i}") for i in range(3)]
        tmp_db.mark_transactions_reviewed(ids)
        for txn_id in ids:
            assert tmp_db.get_transaction(txn_id)["status"] == "Reviewed"

    def test_mark_empty_list_no_error(self, tmp_db):
        tmp_db.mark_transactions_reviewed([])  # should not raise


class TestFingerprintExists:
    def test_exists_after_insert(self, tmp_db):
        bid = tmp_db.create_batch("s.csv")
        tmp_db.insert_transaction(
            batch_id=bid,
            posted_date="2025-01-15",
            description="Test",
            amount=-1.0,
            fingerprint="unique-fp",
        )
        assert tmp_db.fingerprint_exists("unique-fp") is True

    def test_does_not_exist(self, tmp_db):
        assert tmp_db.fingerprint_exists("nonexistent-fp") is False

    def test_exclude_batch_id(self, tmp_db):
        bid = tmp_db.create_batch("s.csv")
        tmp_db.insert_transaction(
            batch_id=bid,
            posted_date="2025-01-15",
            description="Test",
            amount=-1.0,
            fingerprint="fp-dup",
        )
        # When excluding the same batch, it should NOT appear as a cross-file dupe
        assert tmp_db.fingerprint_exists("fp-dup", exclude_batch_id=bid) is False
        # From a different batch perspective, it SHOULD appear
        assert tmp_db.fingerprint_exists("fp-dup", exclude_batch_id=999) is True


# ---------------------------------------------------------------------------
# Schema tests – new tables
# ---------------------------------------------------------------------------


class TestBankImportSchema:
    def test_bank_import_batches_table_exists(self, tmp_db):
        cur = tmp_db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bank_import_batches'"
        )
        assert cur.fetchone() is not None

    def test_bank_transactions_table_exists(self, tmp_db):
        cur = tmp_db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='bank_transactions'"
        )
        assert cur.fetchone() is not None

    def test_bank_transactions_has_expected_columns(self, tmp_db):
        cur = tmp_db._conn.execute("PRAGMA table_info(bank_transactions)")
        col_names = {row[1] for row in cur.fetchall()}
        expected = {
            "id", "batch_id", "posted_date", "description", "amount",
            "currency", "source_row", "fingerprint", "coa_account",
            "status", "is_duplicate", "parse_errors", "created_at", "updated_at",
        }
        assert expected.issubset(col_names)
