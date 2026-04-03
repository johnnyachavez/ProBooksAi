"""Command-line interface for ProBooks+ai.

``--help`` appends a shared Excel COA workbook line from ``probooks.help_epilog`` (see README *Excel workbook template*).
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from probooks import __version__
from probooks.accounts import add_account, list_accounts
from probooks.help_epilog import EXCEL_COA_WORKBOOK_ARGPARSE_EPILOG
from probooks.backup import backup_database, is_sqlite_file, restore_database
from probooks.database import connect, migration_files, run_migrations
from probooks.import_csv import ColumnMap, import_bank_csv
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
        n_acct = conn.execute("SELECT COUNT(*) FROM bank_accounts").fetchone()[0]
        print(f"Bank accounts: {n_acct}")
        try:
            n_txn = conn.execute("SELECT COUNT(*) FROM bank_transactions").fetchone()[0]
            print(f"Bank transactions: {n_txn}")
        except sqlite3.OperationalError:
            print("Bank transactions: (pending migration)")
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
    try:
        backup_database(db, output)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    except (OSError, sqlite3.Error) as e:
        print(e, file=sys.stderr)
        return 1
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
    except (OSError, sqlite3.Error) as e:
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


def cmd_import_csv(db: Path, args: argparse.Namespace) -> int:
    conn = connect(db)
    try:
        run_migrations(conn, migration_files(_migrations_dir()))
        acc = conn.execute(
            "SELECT id FROM bank_accounts WHERE id = ?",
            (args.account,),
        ).fetchone()
        if acc is None:
            print(f"No bank account with id={args.account}", file=sys.stderr)
            return 1
        cmap = ColumnMap(
            date=args.date_col,
            amount=args.amount_col,
            payee=args.payee_col,
            memo=args.memo_col,
            reference=args.reference_col,
        )
        result = import_bank_csv(
            conn,
            bank_account_id=args.account,
            csv_path=args.file,
            columns=cmap,
            skip_rows=args.skip_rows,
            invert_amounts=args.invert_amounts,
            errors_file=args.errors_out,
        )
        print(
            f"Import batch id={result.batch_id}: "
            f"{result.rows_imported} rows imported, {result.rows_skipped} skipped."
        )
        if result.skip_reasons and not args.errors_out:
            print("Skipped row samples (row_index: reason):", file=sys.stderr)
            for r, msg in result.skip_reasons[:10]:
                print(f"  line {r}: {msg}", file=sys.stderr)
            if len(result.skip_reasons) > 10:
                print(f"  ... and {len(result.skip_reasons) - 10} more", file=sys.stderr)
        if args.errors_out and result.rows_skipped:
            print(f"Wrote errors to {args.errors_out}")
    finally:
        conn.close()
    return 0


def cmd_transactions_list(db: Path, args: argparse.Namespace) -> int:
    conn = connect(db)
    try:
        run_migrations(conn, migration_files(_migrations_dir()))
        q = """
        SELECT id, txn_date, amount, payee, memo, reference_number
        FROM bank_transactions
        """
        params: tuple = ()
        if args.account is not None:
            q += " WHERE bank_account_id = ?"
            params = (args.account,)
        q += " ORDER BY txn_date DESC, id DESC LIMIT ?"
        params = (*params, args.limit)
        rows = conn.execute(q, params).fetchall()
        if not rows:
            print("(no transactions)")
            return 0
        for r in rows:
            p = (r["payee"] or "").strip()
            m = (r["memo"] or "").strip()
            extra = f"  {p}" if p else ""
            if m:
                extra += f"  | {m}"
            print(f"  {r['id']}\t{r['txn_date']}\t{r['amount']:.2f}{extra}")
    finally:
        conn.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="probooks",
        description="ProBooks+ai SQLite CLI",
        epilog=(
            "Same interface: python -m probooks … "
            "The desktop app may use a different default SQLite file than this CLI; "
            "see the repository README (Default database paths). "
            + EXCEL_COA_WORKBOOK_ARGPARSE_EPILOG
        ),
    )
    p.add_argument(
        "--db",
        type=Path,
        default=None,
        help=(
            "Database file (default: %%LOCALAPPDATA%%/ProBooks+ai/"
            f"{default_db_path().name} on Windows)"
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("migrate", help="Apply pending SQL migrations")

    sub.add_parser("status", help="Show database path and row counts")

    bp = sub.add_parser(
        "backup",
        help="Copy the SQLite database to a backup file",
        description=(
            "Copies only if --db is a SQLite file and --output resolves to a different path than --db."
        ),
    )
    bp.add_argument(
        "--output",
        "-o",
        type=Path,
        required=True,
        help="Destination path for the copied .db (must not be the same file as --db).",
    )

    rp = sub.add_parser(
        "restore",
        help="Replace the SQLite database from a backup file",
        description=(
            "Copies only if --input is a SQLite file and resolves to a different path than --db."
        ),
    )
    rp.add_argument(
        "--input",
        "-i",
        type=Path,
        required=True,
        help="Backup .db to copy from (must not be the same file as --db).",
    )
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

    imp = sub.add_parser("import", help="Import data")
    imp_sub = imp.add_subparsers(dest="import_cmd", required=True)
    ic = imp_sub.add_parser("csv", help="Import bank transactions from CSV")
    ic.add_argument("--account", "-a", type=int, required=True, help="bank_accounts.id")
    ic.add_argument("--file", "-f", type=Path, required=True)
    ic.add_argument("--skip-rows", type=int, default=0, help="leading rows to skip (e.g. header = 1)")
    ic.add_argument("--date-col", type=int, required=True, help="0-based date column index")
    ic.add_argument("--amount-col", type=int, required=True, help="0-based amount column index")
    ic.add_argument("--payee-col", type=int, default=-1)
    ic.add_argument("--memo-col", type=int, default=-1)
    ic.add_argument("--reference-col", type=int, default=-1)
    ic.add_argument(
        "--invert-amounts",
        action="store_true",
        help="Negate parsed amounts (some exports use opposite sign)",
    )
    ic.add_argument(
        "--errors-out",
        type=Path,
        default=None,
        help="Write skipped rows to CSV (issue #33)",
    )

    tx = sub.add_parser("transactions", help="Bank transactions")
    tx.add_argument("--account", "-a", type=int, default=None, help="Filter by bank_accounts.id")
    tx.add_argument("--limit", "-n", type=int, default=50)

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
    if args.command == "import":
        if args.import_cmd == "csv":
            return cmd_import_csv(db, args)
    if args.command == "transactions":
        return cmd_transactions_list(db, args)
    parser.error("unknown command")
    return 1
