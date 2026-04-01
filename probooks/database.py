"""SQLite connection helpers and migration runner."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migration_files(migrations_dir: Path) -> list[Path]:
    if not migrations_dir.is_dir():
        return []
    return sorted(migrations_dir.glob("*.sql"))


def applied_migration_names(conn: sqlite3.Connection) -> set[str]:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    )
    if cur.fetchone() is None:
        return set()
    rows = conn.execute("SELECT name FROM schema_migrations").fetchall()
    return {r[0] for r in rows}


def run_migrations(conn: sqlite3.Connection, sql_files: Iterable[Path]) -> list[str]:
    """Apply pending .sql migrations in order. Returns names applied."""
    applied = applied_migration_names(conn)
    newly: list[str] = []
    for path in sql_files:
        name = path.name
        if name in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations (name) VALUES (?)",
            (name,),
        )
        newly.append(name)
    conn.commit()
    return newly
