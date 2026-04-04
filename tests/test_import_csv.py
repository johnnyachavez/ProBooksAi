"""CSV import tests (#31, #33, #34)."""

from pathlib import Path

from probooks.accounts import add_account
from probooks.database import connect, migration_files, run_migrations
from probooks.import_csv import ColumnMap, count_transactions, import_bank_csv

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
    assert "utf-8-sig" in doc
    assert "BOM" in doc
