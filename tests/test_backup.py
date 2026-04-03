"""Backup / restore tests."""

from pathlib import Path

import pytest

from probooks.backup import backup_database, is_sqlite_file, restore_database
from probooks.cli import cmd_backup, cmd_restore
from probooks.database import connect, migration_files, run_migrations

from tests.repo_paths import PROBOOKS_MIGRATIONS_DIR


def test_cli_backup_rejects_non_sqlite_source(tmp_path: Path) -> None:
    bad = tmp_path / "src.db"
    bad.write_text("not sqlite", encoding="utf-8")
    out = tmp_path / "out.db"
    assert cmd_backup(bad, out) == 1
    assert not out.exists()


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
