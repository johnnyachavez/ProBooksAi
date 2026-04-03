"""Backup / restore SQLite database files (issue #28).

Uses ``sqlite3.Connection.backup`` (online backup) into a temp file, then
``os.replace`` onto the final path so the destination is not left truncated on failure.
That yields a consistent snapshot even when another connection (e.g. the desktop app)
still has the source database open.

Restore copies the backup file the same way so static ``.db`` backups round-trip reliably.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

SQLITE_MAGIC = b"SQLite format 3\x00"


def is_sqlite_file(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 16:
        return False
    with path.open("rb") as f:
        return f.read(16) == SQLITE_MAGIC


def _same_resolved_path(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False


def _sqlite_uri_readonly(path: Path) -> str:
    return path.expanduser().resolve().as_uri() + "?mode=ro"


def _backup_sqlite_file_to_path(source: Path, dest_sqlite_path: Path) -> None:
    """Stream *source* into *dest_sqlite_path* using SQLite's backup API."""
    uri = _sqlite_uri_readonly(source)
    src_conn = sqlite3.connect(uri, uri=True, timeout=120.0)
    try:
        dst_conn = sqlite3.connect(dest_sqlite_path)
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()


def backup_database(source_db: Path, destination: Path) -> None:
    if not is_sqlite_file(source_db):
        raise ValueError(f"Not a SQLite database file: {source_db}")
    if _same_resolved_path(source_db, destination):
        raise ValueError(
            "Backup destination must differ from the source database path "
            f"(got {source_db!s} -> {destination!s})"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=".probooks-backup-",
        suffix=".tmp",
        dir=str(destination.parent),
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        _backup_sqlite_file_to_path(source_db, tmp_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    try:
        os.replace(tmp_path, destination)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def restore_database(backup_file: Path, target_db: Path, *, overwrite: bool) -> None:
    if not is_sqlite_file(backup_file):
        raise ValueError(f"Not a SQLite database file: {backup_file}")
    if _same_resolved_path(backup_file, target_db):
        raise ValueError(
            "Restore backup file must differ from the target database path "
            f"(got {backup_file!s} -> {target_db!s})"
        )
    if target_db.exists() and not overwrite:
        raise FileExistsError(f"Refuse to overwrite without overwrite=True: {target_db}")
    target_db.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=".probooks-restore-",
        suffix=".tmp",
        dir=str(target_db.parent),
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        _backup_sqlite_file_to_path(backup_file, tmp_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    try:
        os.replace(tmp_path, target_db)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
