"""Backup / restore SQLite database files (issue #28)."""

from __future__ import annotations

import shutil
from pathlib import Path

SQLITE_MAGIC = b"SQLite format 3\x00"


def is_sqlite_file(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 16:
        return False
    with path.open("rb") as f:
        return f.read(16) == SQLITE_MAGIC


def backup_database(source_db: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_db, destination)


def restore_database(backup_file: Path, target_db: Path, *, overwrite: bool) -> None:
    if not is_sqlite_file(backup_file):
        raise ValueError(f"Not a SQLite database file: {backup_file}")
    if target_db.exists() and not overwrite:
        raise FileExistsError(f"Refuse to overwrite without overwrite=True: {target_db}")
    target_db.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup_file, target_db)
