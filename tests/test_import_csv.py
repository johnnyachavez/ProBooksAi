"""CSV import tests (#31, #33, #34)."""

import inspect
from pathlib import Path

import pytest

from probooks.accounts import add_account
from probooks.database import connect, migration_files, run_migrations
from probooks.import_csv import ColumnMap, count_transactions, import_bank_csv
from probooksai.bank_import import BANK_CSV_READ_ENCODING

from tests.repo_paths import EXAMPLES_DIR, PROBOOKS_MIGRATIONS_DIR, PROBOOKS_PACKAGE_DIR


def _db_with_account(tmp_path: Path) -> tuple[Path, int]:
    db = tmp_path / "i.db"
    mdir = PROBOOKS_MIGRATIONS_DIR
    conn = connect(db)
    run_migrations(conn, migration_files(mdir))
    aid = add_account(conn, name="Checking", account_type="checking")
    conn.close()
    return db, aid


def test_import_csv_basic(tmp_path: Path) -> None:
    db, aid = _db_with_account(tmp_path)
    csv_path = tmp_path / "t.csv"
    csv_path.write_text(
        "Date,Amount,Name\n"
        "2026-01-15,-12.34,COFFEE\n"
        "2026-01-16,100.00,DEPOSIT\n",
        encoding="utf-8",
    )
    conn = connect(db)
    r = import_bank_csv(
        conn,
        bank_account_id=aid,
        csv_path=csv_path,
        columns=ColumnMap(date=0, amount=1, payee=2),
        skip_rows=1,
    )
    assert r.rows_imported == 2
    assert r.rows_skipped == 0
    assert count_transactions(conn) == 2
    conn.close()


def test_import_examples_sample_bank_csv_matches_readme_recipe(tmp_path: Path) -> None:
    """README CSV example uses this file and column indices; keep them aligned."""
    csv_path = EXAMPLES_DIR / "sample_bank.csv"
    assert csv_path.is_file()
    db, aid = _db_with_account(tmp_path)
    conn = connect(db)
    r = import_bank_csv(
        conn,
        bank_account_id=aid,
        csv_path=csv_path,
        columns=ColumnMap(date=0, amount=1, payee=2),
        skip_rows=1,
    )
    assert r.rows_imported == 3
    assert r.rows_skipped == 0
    assert count_transactions(conn) == 3
    conn.close()


def test_import_csv_skips_bad_row_and_errors_out(tmp_path: Path) -> None:
    db, aid = _db_with_account(tmp_path)
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text(
        "d,a\n"
        "2026-01-01,10\n"
        "not-a-date,20\n",
        encoding="utf-8",
    )
    err = tmp_path / "err.csv"
    conn = connect(db)
    r = import_bank_csv(
        conn,
        bank_account_id=aid,
        csv_path=csv_path,
        columns=ColumnMap(date=0, amount=1),
        skip_rows=1,
        errors_file=err,
    )
    assert r.rows_imported == 1
    assert r.rows_skipped == 1
    assert err.is_file()
    assert err.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "bad_date" in err.read_text(encoding="utf-8-sig")
    conn.close()


def test_import_csv_module_docstring_documents_utf8_encodings() -> None:
    text = (PROBOOKS_PACKAGE_DIR / "import_csv.py").read_text(encoding="utf-8")
    doc_end = text.index('"""', 3)
    doc = text[: doc_end + 3]
    assert "BANK_CSV_READ_ENCODING" in doc
    assert "parse_amount" in doc
    assert "parse_date" in doc
    assert "strip_csv_cell_paste_noise" in doc
    assert "BOM" in doc


def test_import_csv_accepts_bank_parse_date_formats(tmp_path: Path) -> None:
    """Long month names and Y/m/d match desktop :func:`parse_date` behavior."""
    db, aid = _db_with_account(tmp_path)
    csv_path = tmp_path / "dates.csv"
    csv_path.write_text(
        'Date,Amount\n'
        '"March 2, 2026",10.00\n'
        "2026/04/05,-2.50\n",
        encoding="utf-8",
    )
    conn = connect(db)
    r = import_bank_csv(
        conn,
        bank_account_id=aid,
        csv_path=csv_path,
        columns=ColumnMap(date=0, amount=1),
        skip_rows=1,
    )
    assert r.rows_imported == 2
    dates = sorted(
        row[0]
        for row in conn.execute(
            "SELECT txn_date FROM bank_transactions WHERE bank_account_id = ? ORDER BY id",
            (aid,),
        ).fetchall()
    )
    assert dates == ["2026-03-02", "2026-04-05"]
    conn.close()


def test_import_csv_fromisoformat_datetime_still_parses_date(tmp_path: Path) -> None:
    db, aid = _db_with_account(tmp_path)
    csv_path = tmp_path / "iso.csv"
    csv_path.write_text(
        "Date,Amount\n"
        "2026-05-10T08:30:00,-1.00\n",
        encoding="utf-8",
    )
    conn = connect(db)
    r = import_bank_csv(
        conn,
        bank_account_id=aid,
        csv_path=csv_path,
        columns=ColumnMap(date=0, amount=1),
        skip_rows=1,
    )
    assert r.rows_imported == 1
    d = conn.execute(
        "SELECT txn_date FROM bank_transactions WHERE bank_account_id = ?",
        (aid,),
    ).fetchone()[0]
    assert d == "2026-05-10"
    conn.close()


def test_import_csv_accepts_bom_on_date_and_unicode_minus_on_amount(tmp_path: Path) -> None:
    db, aid = _db_with_account(tmp_path)
    csv_path = tmp_path / "paste.csv"
    csv_path.write_text(
        "Date,Amount,Name\n"
        "\ufeff2026-02-01,\u22125.00,CAFE\n",
        encoding="utf-8",
    )
    conn = connect(db)
    r = import_bank_csv(
        conn,
        bank_account_id=aid,
        csv_path=csv_path,
        columns=ColumnMap(date=0, amount=1, payee=2),
        skip_rows=1,
    )
    assert r.rows_imported == 1
    assert r.rows_skipped == 0
    row = conn.execute(
        "SELECT txn_date, amount, payee FROM bank_transactions WHERE bank_account_id = ?",
        (aid,),
    ).fetchone()
    assert row is not None
    assert row[0] == "2026-02-01"
    assert row[1] == pytest.approx(-5.0)
    assert row[2] == "CAFE"
    conn.close()


def test_import_bank_csv_raises_file_not_found_before_batch(tmp_path: Path) -> None:
    db, aid = _db_with_account(tmp_path)
    missing = tmp_path / "does-not-exist.csv"
    conn = connect(db)
    with pytest.raises(FileNotFoundError):
        import_bank_csv(
            conn,
            bank_account_id=aid,
            csv_path=missing,
            columns=ColumnMap(date=0, amount=1),
            skip_rows=0,
        )
    n_batches = conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0]
    assert n_batches == 0
    conn.close()


def test_import_bank_csv_default_encoding_matches_bank_csv_read_constant() -> None:
    sig = inspect.signature(import_bank_csv)
    assert sig.parameters["encoding"].default == BANK_CSV_READ_ENCODING
