"""Command-line interface for ProBooks+ai."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from probooks import __version__
from probooks.accounts import add_account, list_accounts
from probooks.backup import backup_database, is_sqlite_file, restore_database
from probooks.database import connect, migration_files, run_migrations
from probooks.paths import default_db_path, ensure_app_dirs


def _migrations_dir() -> Path:
    return Path(__file__).resolve().parent / "migrations"


def cmd_migrate(db: Path) -> int:
    conn = connect(db)
    try:
        applied = run_migrations(conn, migration_files(_migrations_dir()))
        if applied:
            print("Applied migrations:", ", ".join(applied))
        else:
            print("Database is up to date.")
    finally:
        conn.close()
    return 0


def cmd_status(db: Path) -> int:
    ensure_app_dirs()
    print(f"ProBooks+ai {__version__}")
    print(f"Database path: {db}")
    print(f"Exists: {db.is_file()}")
    if not db.is_file():
        print('Run "probooks migrate" to create the database.')
        return 0
    if not is_sqlite_file(db):
        print("Warning: file does not look like a SQLite database.")
        return 1
    conn = connect(db)
    try:
        applied = run_migrations(conn, migration_files(_migrations_dir()))
        if applied:
            print("Applied migrations:", ", ".join(applied))
        n = conn.execute("SELECT COUNT(*) FROM bank_accounts").fetchone()[0]
        print(f"Bank accounts: {n}")
    except Exception as e:
        print(f"Error reading database: {e}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    return 0


def cmd_backup(db: Path, output: Path) -> int:
    if not db.is_file():
        print(f"No database at {db}", file=sys.stderr)
        return 1
    backup_database(db, output)
    print(f"Backed up to {output}")
    return 0


def cmd_restore(db: Path, source: Path, yes: bool) -> int:
    if not yes:
        print("Restore will replace the active database. Re-run with --yes to confirm.", file=sys.stderr)
        return 2
    if not source.is_file():
        print(f"Backup file not found: {source}", file=sys.stderr)
        return 1
    try:
        restore_database(source, db, overwrite=True)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    print(f"Restored database from {source} to {db}")
    return 0


def cmd_accounts_list(db: Path) -> int:
    conn = connect(db)
    try:
        run_migrations(conn, migration_files(_migrations_dir()))
        accounts = list_accounts(conn)
        if not accounts:
            print("(no bank accounts yet; use: probooks accounts add --name \"...\")")
        for a in accounts:
            tail = f" ({a.institution})" if a.institution else ""
            t = a.account_type or "?"
            last = a.last4 or "----"
            print(f"  [{a.id}] {a.name}{tail}  {t}  ...{last}")
    finally:
        conn.close()
    return 0


def cmd_accounts_add(db: Path, args: argparse.Namespace) -> int:
    conn = connect(db)
    try:
        run_migrations(conn, migration_files(_migrations_dir()))
        aid = add_account(
            conn,
            name=args.name,
            institution=args.institution,
            account_type=args.type,
            last4=args.last4,
            notes=args.notes,
        )
        print(f"Created bank account id={aid}")
    finally:
        conn.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="probooks", description="ProBooks+ai SQLite CLI")
    p.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Database file (default: %%LOCALAPPDATA%%/ProBooks+ai/probooks.db on Windows)",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("migrate", help="Apply pending SQL migrations")

    sub.add_parser("status", help="Show database path and row counts")

    bp = sub.add_parser("backup", help="Copy database to a backup file")
    bp.add_argument("--output", "-o", type=Path, required=True)

    rp = sub.add_parser("restore", help="Replace database from a backup file")
    rp.add_argument("--input", "-i", type=Path, required=True)
    rp.add_argument("--yes", action="store_true", help="Confirm overwrite")

    al = sub.add_parser("accounts", help="Bank accounts")
    al_sub = al.add_subparsers(dest="accounts_cmd", required=True)
    al_sub.add_parser("list", help="List accounts")
    aa = al_sub.add_parser("add", help="Add an account")
    aa.add_argument("--name", required=True)
    aa.add_argument("--institution", default=None)
    aa.add_argument("--type", dest="type", choices=["checking", "savings", "credit", "other"], default=None)
    aa.add_argument("--last4", default=None)
    aa.add_argument("--notes", default=None)

    return p


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(argv)
    db = args.db if args.db is not None else default_db_path()

    if args.command == "migrate":
        return cmd_migrate(db)
    if args.command == "status":
        return cmd_status(db)
    if args.command == "backup":
        return cmd_backup(db, args.output)
    if args.command == "restore":
        return cmd_restore(db, args.input, args.yes)
    if args.command == "accounts":
        if args.accounts_cmd == "list":
            return cmd_accounts_list(db)
        if args.accounts_cmd == "add":
            return cmd_accounts_add(db, args)
    parser.error("unknown command")
    return 1
