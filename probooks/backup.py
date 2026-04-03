"""Backup / restore SQLite database files (issue #28).

Writes to a temporary file in the destination directory, then ``os.replace`` onto the
final path so an interrupted copy does not truncate the target database.

For a stable snapshot, avoid copying *source_db* while your process still has it open
via ``sqlite3`` (close connections first, as the desktop app does before **File → Backup**).
The CLI typically runs when no other handle holds the default ``--db`` file.
"""

from __future__ import annotations

import os
import shutil
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
        shutil.copy2(source_db, tmp_path)
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
        shutil.copy2(backup_file, tmp_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    try:
        os.replace(tmp_path, target_db)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
