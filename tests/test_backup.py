"""Backup / restore tests."""

import io
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from probooks.backup import SQLITE_MAGIC, backup_database, is_sqlite_file, restore_database
from probooks.cli import cmd_backup, cmd_restore
from probooks.database import connect, migration_files, run_migrations

from tests.repo_paths import PROBOOKS_MIGRATIONS_DIR


def test_is_sqlite_file_false_when_missing(tmp_path: Path) -> None:
    assert not is_sqlite_file(tmp_path / "missing.db")


def test_is_sqlite_file_false_when_too_small(tmp_path: Path) -> None:
    p = tmp_path / "tiny.db"
    p.write_bytes(SQLITE_MAGIC[:8])
    assert p.stat().st_size < 16
    assert not is_sqlite_file(p)


def test_is_sqlite_file_false_when_wrong_header(tmp_path: Path) -> None:
    p = tmp_path / "wrong.db"
    p.write_bytes(b"not sqlite data!")
    assert p.stat().st_size >= 16
    assert not is_sqlite_file(p)


def test_is_sqlite_file_true_at_minimum_size(tmp_path: Path) -> None:
    p = tmp_path / "header_only.db"
    p.write_bytes(SQLITE_MAGIC)
    assert p.stat().st_size == 16
    assert is_sqlite_file(p)


def test_is_sqlite_file_false_when_path_is_directory(tmp_path: Path) -> None:
    d = tmp_path / "fake.db"
    d.mkdir()
    assert d.is_dir()
    assert not is_sqlite_file(d)


def test_cli_backup_returns_one_when_source_db_missing(tmp_path: Path) -> None:
    missing = tmp_path / "nope.db"
    out = tmp_path / "out.db"
    assert cmd_backup(missing, out) == 1
    assert not out.exists()


def test_main_backup_prints_error_when_db_missing(tmp_path: Path) -> None:
    from probooks.cli import main

    missing = tmp_path / "nope.db"
    out = tmp_path / "out.db"
    err = io.StringIO()
    with patch.object(sys, "stderr", err):
        code = main(["--db", str(missing), "backup", "-o", str(out)])
    assert code == 1
    assert not out.exists()
    assert "No database at" in err.getvalue()


def test_main_backup_and_restore_roundtrip(tmp_path: Path) -> None:
    from probooks.cli import main

    mdir = PROBOOKS_MIGRATIONS_DIR
    db = tmp_path / "company.db"
    conn = connect(db)
    run_migrations(conn, migration_files(mdir))
    conn.close()

    snap = tmp_path / "snap.db"
    stdout_bak = io.StringIO()
    with patch.object(sys, "stdout", stdout_bak):
        assert main(["--db", str(db), "backup", "--output", str(snap)]) == 0
    assert is_sqlite_file(snap)
    assert "Backed up to" in stdout_bak.getvalue()

    restored = tmp_path / "restored.db"
    stdout_restore = io.StringIO()
    with patch.object(sys, "stdout", stdout_restore):
        assert main(["--db", str(restored), "restore", "-i", str(snap), "--yes"]) == 0
    assert is_sqlite_file(restored)
    assert "Restored database from" in stdout_restore.getvalue()
    conn = connect(restored)
    assert conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0] >= 1
    conn.close()


def test_main_restore_without_yes_returns_two(tmp_path: Path) -> None:
    from probooks.cli import main

    target = tmp_path / "live.db"
    bak = tmp_path / "bak.db"
    err = io.StringIO()
    with patch.object(sys, "stderr", err):
        code = main(["--db", str(target), "restore", "-i", str(bak)])
    assert code == 2
    assert "--yes" in err.getvalue()
    assert "confirm" in err.getvalue().lower()


def test_main_restore_prints_error_when_input_missing(tmp_path: Path) -> None:
    from probooks.cli import main

    target = tmp_path / "live.db"
    missing = tmp_path / "gone.db"
    err = io.StringIO()
    with patch.object(sys, "stderr", err):
        code = main(["--db", str(target), "restore", "-i", str(missing), "--yes"])
    assert code == 1
    assert "Backup file not found" in err.getvalue()


def test_main_backup_stderr_when_db_not_sqlite(tmp_path: Path) -> None:
    from probooks.cli import main

    db = tmp_path / "bad.db"
    db.write_text("not sqlite", encoding="utf-8")
    out = tmp_path / "out.db"
    err = io.StringIO()
    with patch.object(sys, "stderr", err):
        code = main(["--db", str(db), "backup", "-o", str(out)])
    assert code == 1
    assert not out.exists()
    assert "Not a SQLite" in err.getvalue()


def test_main_restore_stderr_when_input_not_sqlite(tmp_path: Path) -> None:
    from probooks.cli import main

    target = tmp_path / "live.db"
    bad_bak = tmp_path / "fake.bak"
    bad_bak.write_text("plain", encoding="utf-8")
    err = io.StringIO()
    with patch.object(sys, "stderr", err):
        code = main(["--db", str(target), "restore", "-i", str(bad_bak), "--yes"])
    assert code == 1
    assert "Not a SQLite" in err.getvalue()


def test_main_backup_stderr_when_output_same_path_as_db(tmp_path: Path) -> None:
    from probooks.cli import main

    mdir = PROBOOKS_MIGRATIONS_DIR
    db = tmp_path / "live.db"
    conn = connect(db)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    err = io.StringIO()
    with patch.object(sys, "stderr", err):
        code = main(["--db", str(db), "backup", "-o", str(db)])
    assert code == 1
    assert "must differ" in err.getvalue()


def test_main_restore_stderr_when_input_same_path_as_db(tmp_path: Path) -> None:
    from probooks.cli import main

    mdir = PROBOOKS_MIGRATIONS_DIR
    db = tmp_path / "live.db"
    conn = connect(db)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    err = io.StringIO()
    with patch.object(sys, "stderr", err):
        code = main(["--db", str(db), "restore", "-i", str(db), "--yes"])
    assert code == 1
    assert "must differ" in err.getvalue()


def test_main_backup_accepts_short_output_flag(tmp_path: Path) -> None:
    from probooks.cli import main

    mdir = PROBOOKS_MIGRATIONS_DIR
    db = tmp_path / "company.db"
    conn = connect(db)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    out = tmp_path / "snap.db"
    stdout = io.StringIO()
    with patch.object(sys, "stdout", stdout):
        assert main(["--db", str(db), "backup", "-o", str(out)]) == 0
    assert is_sqlite_file(out)
    assert "Backed up to" in stdout.getvalue()


def test_main_backup_replaces_existing_destination_file(tmp_path: Path) -> None:
    from probooks.cli import main

    mdir = PROBOOKS_MIGRATIONS_DIR
    db = tmp_path / "live.db"
    conn = connect(db)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    out = tmp_path / "out.db"
    out.write_bytes(b"pre-existing non-sqlite payload")
    assert not is_sqlite_file(out)
    stdout = io.StringIO()
    with patch.object(sys, "stdout", stdout):
        assert main(["--db", str(db), "backup", "-o", str(out)]) == 0
    assert is_sqlite_file(out)
    assert "Backed up to" in stdout.getvalue()
    conn = connect(out)
    assert conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0] >= 1
    conn.close()


def test_main_restore_replaces_existing_target_file(tmp_path: Path) -> None:
    from probooks.cli import main

    mdir = PROBOOKS_MIGRATIONS_DIR
    live = tmp_path / "live.db"
    conn = connect(live)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    bak = tmp_path / "bak.db"
    backup_database(live, bak)
    target = tmp_path / "target.db"
    target.write_bytes(b"old non-sqlite contents")
    assert not is_sqlite_file(target)
    stdout = io.StringIO()
    with patch.object(sys, "stdout", stdout):
        assert main(["--db", str(target), "restore", "-i", str(bak), "--yes"]) == 0
    assert is_sqlite_file(target)
    assert "Restored database from" in stdout.getvalue()
    conn = connect(target)
    assert conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0] >= 1
    conn.close()


def test_cli_restore_returns_one_when_backup_file_missing(tmp_path: Path) -> None:
    target = tmp_path / "live.db"
    missing_bak = tmp_path / "missing.db"
    assert cmd_restore(target, missing_bak, yes=True) == 1


def test_cli_backup_creates_nested_destination_parent(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    mdir = PROBOOKS_MIGRATIONS_DIR
    src = tmp_path / "live.db"
    conn = connect(src)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    nested = tmp_path / "exports" / "nested" / "out.db"
    assert not nested.parent.exists()
    assert cmd_backup(src, nested) == 0
    assert is_sqlite_file(nested)
    out = capsys.readouterr().out
    assert "Backed up to" in out
    assert str(nested) in out


def test_cli_restore_creates_nested_target_parent(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    mdir = PROBOOKS_MIGRATIONS_DIR
    live = tmp_path / "live.db"
    conn = connect(live)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    bak = tmp_path / "bak.db"
    backup_database(live, bak)
    nested_target = tmp_path / "restored" / "dir" / "company.db"
    assert not nested_target.parent.exists()
    assert cmd_restore(nested_target, bak, yes=True) == 0
    assert is_sqlite_file(nested_target)
    out = capsys.readouterr().out
    assert "Restored database from" in out
    assert str(bak) in out
    assert str(nested_target) in out


def test_cli_backup_rejects_non_sqlite_source(tmp_path: Path) -> None:
    bad = tmp_path / "src.db"
    bad.write_text("not sqlite", encoding="utf-8")
    out = tmp_path / "out.db"
    assert cmd_backup(bad, out) == 1
    assert not out.exists()


def test_cli_restore_without_yes_returns_two(tmp_path: Path) -> None:
    mdir = PROBOOKS_MIGRATIONS_DIR
    db = tmp_path / "live.db"
    bak = tmp_path / "bak.db"
    conn = connect(db)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    backup_database(db, bak)
    assert cmd_restore(db, bak, yes=False) == 2


def test_restore_refuses_overwrite_false_when_target_exists(tmp_path: Path) -> None:
    mdir = PROBOOKS_MIGRATIONS_DIR
    target = tmp_path / "live.db"
    bak = tmp_path / "bak.db"
    conn = connect(target)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    backup_database(target, bak)
    with pytest.raises(FileExistsError, match="overwrite"):
        restore_database(bak, target, overwrite=False)


def test_restore_overwrite_false_creates_target_when_missing(tmp_path: Path) -> None:
    """overwrite=False only blocks replacing an existing file."""
    mdir = PROBOOKS_MIGRATIONS_DIR
    live = tmp_path / "live.db"
    conn = connect(live)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    bak = tmp_path / "bak.db"
    backup_database(live, bak)
    new_target = tmp_path / "new_company.db"
    assert not new_target.exists()
    restore_database(bak, new_target, overwrite=False)
    assert is_sqlite_file(new_target)
    conn = connect(new_target)
    assert conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0] >= 1
    conn.close()


def test_backup_database_replaces_existing_destination_file(tmp_path: Path) -> None:
    """Destination path may already exist; online backup replaces it atomically."""
    mdir = PROBOOKS_MIGRATIONS_DIR
    src = tmp_path / "live.db"
    conn = connect(src)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    dest = tmp_path / "out.db"
    dest.write_bytes(b"previous junk not sqlite")
    assert not is_sqlite_file(dest)
    backup_database(src, dest)
    assert is_sqlite_file(dest)
    conn = connect(dest)
    assert conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0] >= 1
    conn.close()


def test_restore_database_replaces_existing_target_when_overwrite_true(tmp_path: Path) -> None:
    mdir = PROBOOKS_MIGRATIONS_DIR
    live = tmp_path / "live.db"
    conn = connect(live)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    bak = tmp_path / "bak.db"
    backup_database(live, bak)
    target = tmp_path / "target.db"
    target.write_bytes(b"trash" * 10)
    assert not is_sqlite_file(target)
    restore_database(bak, target, overwrite=True)
    assert is_sqlite_file(target)
    conn = connect(target)
    assert conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0] >= 1
    conn.close()


def test_backup_database_unlinks_temp_file_when_backup_raises(tmp_path: Path) -> None:
    mdir = PROBOOKS_MIGRATIONS_DIR
    src = tmp_path / "live.db"
    conn = connect(src)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    dest = tmp_path / "out.db"

    with patch(
        "probooks.backup._backup_sqlite_file_to_path",
        side_effect=sqlite3.OperationalError("forced backup failure"),
    ):
        with pytest.raises(sqlite3.OperationalError, match="forced backup failure"):
            backup_database(src, dest)
    assert not dest.exists()
    assert not list(tmp_path.glob(".probooks-backup-*.tmp"))


def test_restore_database_unlinks_temp_file_when_backup_raises(tmp_path: Path) -> None:
    mdir = PROBOOKS_MIGRATIONS_DIR
    live = tmp_path / "live.db"
    conn = connect(live)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    bak = tmp_path / "bak.db"
    backup_database(live, bak)
    target = tmp_path / "target.db"
    assert not target.exists()

    with patch(
        "probooks.backup._backup_sqlite_file_to_path",
        side_effect=sqlite3.OperationalError("forced restore copy failure"),
    ):
        with pytest.raises(sqlite3.OperationalError, match="forced restore copy failure"):
            restore_database(bak, target, overwrite=True)
    assert not target.exists()
    assert not list(tmp_path.glob(".probooks-restore-*.tmp"))


def test_backup_database_unlinks_temp_when_os_replace_fails(tmp_path: Path) -> None:
    mdir = PROBOOKS_MIGRATIONS_DIR
    src = tmp_path / "live.db"
    conn = connect(src)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    dest = tmp_path / "out.db"
    with patch("probooks.backup.os.replace", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            backup_database(src, dest)
    assert not dest.exists()
    assert not list(tmp_path.glob(".probooks-backup-*.tmp"))


def test_restore_database_unlinks_temp_when_os_replace_fails(tmp_path: Path) -> None:
    mdir = PROBOOKS_MIGRATIONS_DIR
    live = tmp_path / "live.db"
    conn = connect(live)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    bak = tmp_path / "bak.db"
    backup_database(live, bak)
    target = tmp_path / "target.db"
    assert not target.exists()
    with patch("probooks.backup.os.replace", side_effect=OSError("replace denied")):
        with pytest.raises(OSError, match="replace denied"):
            restore_database(bak, target, overwrite=True)
    assert not target.exists()
    assert not list(tmp_path.glob(".probooks-restore-*.tmp"))


def test_cmd_backup_returns_one_when_backup_api_raises(tmp_path: Path) -> None:
    mdir = PROBOOKS_MIGRATIONS_DIR
    src = tmp_path / "live.db"
    conn = connect(src)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    out = tmp_path / "out.db"
    err = io.StringIO()
    with patch(
        "probooks.backup._backup_sqlite_file_to_path",
        side_effect=sqlite3.OperationalError("backup api"),
    ):
        with patch.object(sys, "stderr", err):
            assert cmd_backup(src, out) == 1
    assert not out.exists()
    assert "backup api" in err.getvalue()


def test_cmd_restore_returns_one_when_restore_api_raises(tmp_path: Path) -> None:
    mdir = PROBOOKS_MIGRATIONS_DIR
    live = tmp_path / "live.db"
    conn = connect(live)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    bak = tmp_path / "bak.db"
    backup_database(live, bak)
    target = tmp_path / "t.db"
    err = io.StringIO()
    with patch(
        "probooks.backup._backup_sqlite_file_to_path",
        side_effect=sqlite3.OperationalError("restore api"),
    ):
        with patch.object(sys, "stderr", err):
            assert cmd_restore(target, bak, yes=True) == 1
    assert not target.exists()
    assert "restore api" in err.getvalue()


def test_cli_restore_rejects_non_sqlite_backup(tmp_path: Path) -> None:
    bad = tmp_path / "bak.db"
    bad.write_text("not sqlite", encoding="utf-8")
    target = tmp_path / "company.db"
    target.write_text("anything", encoding="utf-8")
    assert cmd_restore(target, bad, yes=True) == 1


def test_backup_rejects_non_sqlite_source(tmp_path: Path) -> None:
    bad = tmp_path / "fake.db"
    bad.write_text("not sqlite", encoding="utf-8")
    out = tmp_path / "out.db"
    with pytest.raises(ValueError, match="Not a SQLite"):
        backup_database(bad, out)
    assert not out.exists()


def test_restore_rejects_non_sqlite_backup(tmp_path: Path) -> None:
    bad = tmp_path / "not.db"
    bad.write_text("plain text", encoding="utf-8")
    target = tmp_path / "company.db"
    target.write_bytes(b"x" * 20)
    with pytest.raises(ValueError, match="Not a SQLite"):
        restore_database(bad, target, overwrite=True)


def test_backup_rejects_same_destination(tmp_path: Path) -> None:
    mdir = PROBOOKS_MIGRATIONS_DIR
    src = tmp_path / "live.db"
    conn = connect(src)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    with pytest.raises(ValueError, match="must differ"):
        backup_database(src, src)


def test_restore_rejects_same_path(tmp_path: Path) -> None:
    mdir = PROBOOKS_MIGRATIONS_DIR
    db = tmp_path / "live.db"
    conn = connect(db)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    with pytest.raises(ValueError, match="must differ"):
        restore_database(db, db, overwrite=True)


def test_backup_rejects_equivalent_relative_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    mdir = PROBOOKS_MIGRATIONS_DIR
    rel = Path("company.db")
    conn = connect(rel)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    with pytest.raises(ValueError, match="must differ"):
        backup_database(Path("company.db"), Path("./company.db"))


def test_restore_rejects_equivalent_relative_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    mdir = PROBOOKS_MIGRATIONS_DIR
    rel = Path("company.db")
    conn = connect(rel)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    with pytest.raises(ValueError, match="must differ"):
        restore_database(Path("company.db"), Path("./company.db"), overwrite=True)


def test_cli_backup_and_restore_reject_same_path(tmp_path: Path) -> None:
    mdir = PROBOOKS_MIGRATIONS_DIR
    db = tmp_path / "live.db"
    conn = connect(db)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    assert cmd_backup(db, db) == 1
    assert cmd_restore(db, db, yes=True) == 1


def test_backup_roundtrip_while_other_connection_open(tmp_path: Path) -> None:
    """Online backup stays consistent when another handle keeps the source DB open."""
    mdir = PROBOOKS_MIGRATIONS_DIR
    src = tmp_path / "live.db"
    conn = connect(src)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    holder = sqlite3.connect(src)
    try:
        bak = tmp_path / "out.db"
        backup_database(src, bak)
        assert is_sqlite_file(bak)
        dest = tmp_path / "restored.db"
        restore_database(bak, dest, overwrite=True)
        assert is_sqlite_file(dest)
        r = sqlite3.connect(dest)
        try:
            assert r.execute("SELECT COUNT(*) FROM companies").fetchone()[0] >= 1
        finally:
            r.close()
    finally:
        holder.close()


def test_backup_database_creates_parent_directories_for_destination(tmp_path: Path) -> None:
    mdir = PROBOOKS_MIGRATIONS_DIR
    src = tmp_path / "live.db"
    conn = connect(src)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    nested = tmp_path / "snapshots" / "2026" / "copy.db"
    assert not nested.parent.exists()
    backup_database(src, nested)
    assert is_sqlite_file(nested)


def test_restore_database_creates_parent_directories_for_target(tmp_path: Path) -> None:
    mdir = PROBOOKS_MIGRATIONS_DIR
    live = tmp_path / "live.db"
    conn = connect(live)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    bak = tmp_path / "bak.db"
    backup_database(live, bak)
    nested_target = tmp_path / "restore" / "here" / "company.db"
    assert not nested_target.parent.exists()
    restore_database(bak, nested_target, overwrite=True)
    assert is_sqlite_file(nested_target)
    conn = connect(nested_target)
    assert conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0] >= 1
    conn.close()


def test_backup_roundtrip(tmp_path: Path) -> None:
    mdir = PROBOOKS_MIGRATIONS_DIR
    src = tmp_path / "live.db"
    conn = connect(src)
    run_migrations(conn, migration_files(mdir))
    conn.close()
    assert is_sqlite_file(src)

    bak = tmp_path / "copy.db"
    backup_database(src, bak)
    assert is_sqlite_file(bak)

    dest = tmp_path / "restored.db"
    restore_database(bak, dest, overwrite=True)
    assert is_sqlite_file(dest)
    conn = connect(dest)
    assert conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0] >= 1
    conn.close()

    assert not list(tmp_path.glob(".probooks-backup-*.tmp"))
    assert not list(tmp_path.glob(".probooks-restore-*.tmp"))
