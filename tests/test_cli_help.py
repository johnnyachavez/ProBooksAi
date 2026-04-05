"""probooks CLI --help (epilog and exit code)."""

from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.repo_paths import PROBOOKS_MIGRATIONS_DIR


def test_probooks_backup_help_mentions_sqlite_and_distinct_paths() -> None:
    from probooks.cli import main

    buf = io.StringIO()
    with patch.object(sys, "stdout", buf):
        with pytest.raises(SystemExit) as exc:
            main(["backup", "--help"])
    assert exc.value.code == 0
    text = buf.getvalue()
    assert "SQLite" in text
    assert "different path" in text
    assert "online backup" in text.lower()


def test_probooks_restore_help_mentions_sqlite_and_distinct_paths() -> None:
    from probooks.cli import main

    buf = io.StringIO()
    with patch.object(sys, "stdout", buf):
        with pytest.raises(SystemExit) as exc:
            main(["restore", "--help"])
    assert exc.value.code == 0
    text = buf.getvalue()
    assert "SQLite" in text
    assert "different path" in text
    assert "online backup" in text.lower()


def test_probooks_help_epilog_and_exit_zero() -> None:
    from probooks.cli import main

    buf = io.StringIO()
    with patch.object(sys, "stdout", buf):
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
    assert exc.value.code == 0
    text = buf.getvalue()
    assert "python -m probooks" in text
    assert "README" in text
    assert "Default database" in text
    assert "generate_workbook.py" in text
    assert "Excel COA workbook" in text
    assert "probooks.backup" in text
    assert "File → Backup" in text
    assert "UTF-8 BOM for Excel" in text
    assert "import csv --errors-out" in text
    assert "Bank CSV import" in text
    assert "reads UTF-8 with optional BOM" in text


def test_probooks_import_csv_help_mentions_utf8_optional_bom_input() -> None:
    from probooks.cli import main

    buf = io.StringIO()
    with patch.object(sys, "stdout", buf):
        with pytest.raises(SystemExit) as exc:
            main(["import", "csv", "--help"])
    assert exc.value.code == 0
    text = buf.getvalue()
    assert "UTF-8" in text and "optional BOM" in text
    assert "import_batch" in text and "bank_transactions" in text
    assert "parse_date" in text
    assert "parse_amount" in text


def test_probooks_import_csv_stderr_shows_errors_out_tip_when_rows_skipped(
    tmp_path: Path,
) -> None:
    from probooks.accounts import add_account
    from probooks.cli import main
    from probooks.database import connect, migration_files, run_migrations

    db = tmp_path / "cli_tip.db"
    conn = connect(db)
    run_migrations(conn, migration_files(PROBOOKS_MIGRATIONS_DIR))
    aid = add_account(conn, name="Checking", account_type="checking")
    conn.close()

    csv_path = tmp_path / "mixed.csv"
    csv_path.write_text(
        "d,a\n"
        "2026-01-01,10\n"
        "not-a-date,20\n"
        "2026-01-02,notnum\n"
        "bad,bad\n",
        encoding="utf-8",
    )

    stdout, stderr = io.StringIO(), io.StringIO()
    with patch.object(sys, "stdout", stdout), patch.object(sys, "stderr", stderr):
        rc = main(
            [
                "--db",
                str(db),
                "import",
                "csv",
                "-a",
                str(aid),
                "-f",
                str(csv_path),
                "--skip-rows",
                "1",
                "--date-col",
                "0",
                "--amount-col",
                "1",
            ]
        )

    assert rc == 0
    err = stderr.getvalue()
    assert "Skip summary: 1 bad date only; 1 bad amount only; 1 bad date and amount." in err
    assert "Skipped row samples" in err
    assert "bad_date" in err
    assert "Tip: re-run with --errors-out" in err


def test_probooks_import_csv_stderr_has_no_rerun_tip_when_errors_out_set(
    tmp_path: Path,
) -> None:
    from probooks.accounts import add_account
    from probooks.cli import main
    from probooks.database import connect, migration_files, run_migrations

    db = tmp_path / "cli_errout.db"
    conn = connect(db)
    run_migrations(conn, migration_files(PROBOOKS_MIGRATIONS_DIR))
    aid = add_account(conn, name="Checking", account_type="checking")
    conn.close()

    csv_path = tmp_path / "mixed.csv"
    csv_path.write_text(
        "d,a\n"
        "2026-01-01,10\n"
        "not-a-date,20\n"
        "2026-01-02,notnum\n"
        "bad,bad\n",
        encoding="utf-8",
    )
    err_csv = tmp_path / "skipped.csv"

    stdout, stderr = io.StringIO(), io.StringIO()
    with patch.object(sys, "stdout", stdout), patch.object(sys, "stderr", stderr):
        rc = main(
            [
                "--db",
                str(db),
                "import",
                "csv",
                "-a",
                str(aid),
                "-f",
                str(csv_path),
                "--skip-rows",
                "1",
                "--date-col",
                "0",
                "--amount-col",
                "1",
                "--errors-out",
                str(err_csv),
            ]
        )

    assert rc == 0
    err = stderr.getvalue()
    assert "Skip summary: 1 bad date only; 1 bad amount only; 1 bad date and amount." in err
    assert "Tip: re-run with --errors-out" not in err
    assert "Skipped row samples" not in err
    out = stdout.getvalue()
    assert "Wrote errors to" in out
    assert str(err_csv) in out
    assert err_csv.is_file()
    assert err_csv.read_bytes().startswith(b"\xef\xbb\xbf")


def test_probooks_import_csv_returns_one_when_csv_file_missing(
    tmp_path: Path,
) -> None:
    from probooks.accounts import add_account
    from probooks.cli import main
    from probooks.database import connect, migration_files, run_migrations

    db = tmp_path / "csv_missing.db"
    conn = connect(db)
    run_migrations(conn, migration_files(PROBOOKS_MIGRATIONS_DIR))
    aid = add_account(conn, name="Checking", account_type="checking")
    conn.close()

    missing = tmp_path / "not_there.csv"
    stdout, stderr = io.StringIO(), io.StringIO()
    with patch.object(sys, "stdout", stdout), patch.object(sys, "stderr", stderr):
        rc = main(
            [
                "--db",
                str(db),
                "import",
                "csv",
                "-a",
                str(aid),
                "-f",
                str(missing),
                "--date-col",
                "0",
                "--amount-col",
                "1",
            ]
        )

    assert rc == 1
    err = stderr.getvalue()
    assert "Could not read CSV file" in err
    assert str(missing) in err


def test_probooks_import_csv_returns_one_when_bank_account_missing(
    tmp_path: Path,
) -> None:
    from probooks.cli import main
    from probooks.database import connect, migration_files, run_migrations

    db = tmp_path / "no_bank_acct.db"
    conn = connect(db)
    run_migrations(conn, migration_files(PROBOOKS_MIGRATIONS_DIR))
    conn.close()

    csv_path = tmp_path / "only.csv"
    csv_path.write_text("d,a\n2026-01-01,1.00\n", encoding="utf-8")

    stdout, stderr = io.StringIO(), io.StringIO()
    with patch.object(sys, "stdout", stdout), patch.object(sys, "stderr", stderr):
        rc = main(
            [
                "--db",
                str(db),
                "import",
                "csv",
                "-a",
                "404",
                "-f",
                str(csv_path),
                "--skip-rows",
                "1",
                "--date-col",
                "0",
                "--amount-col",
                "1",
            ]
        )

    assert rc == 1
    err = stderr.getvalue()
    assert "No bank account" in err
    assert "404" in err


def test_import_csv_skip_summary_bits_empty() -> None:
    from probooks.cli import _import_csv_skip_summary_bits

    assert _import_csv_skip_summary_bits([]) == []


def test_import_csv_skip_summary_bits_one_of_each_bucket() -> None:
    from probooks.cli import _import_csv_skip_summary_bits

    bits = _import_csv_skip_summary_bits(
        [
            (2, "bad_date"),
            (3, "bad_amount"),
            (4, "bad_date,bad_amount"),
        ]
    )
    assert bits == ["1 bad date only", "1 bad amount only", "1 bad date and amount"]


def test_import_csv_skip_summary_bits_aggregates_same_bucket() -> None:
    from probooks.cli import _import_csv_skip_summary_bits

    bits = _import_csv_skip_summary_bits(
        [
            (1, "bad_date"),
            (2, "bad_date"),
            (3, "bad_amount"),
            (4, "bad_amount"),
        ]
    )
    assert bits == ["2 bad date only", "2 bad amount only"]


def test_import_csv_skip_summary_bits_ignores_unknown_reason_tokens() -> None:
    from probooks.cli import _import_csv_skip_summary_bits

    assert _import_csv_skip_summary_bits([(1, ""), (2, "other")]) == []
