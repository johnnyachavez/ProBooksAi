"""
probooksai.bank_import
======================
Bank-account setup, CSV transaction import, and statement reconciliation.

Schema
------
  bank_accounts        – per-account configuration (name, number, bank, type)
  bank_import_batches  – one row per imported CSV file, with statement dates
                         and balances for reconciliation
  bank_transactions    – individual transaction rows (outflows negative)

Reconciliation
--------------
  computed_ending = beginning_balance + sum(amounts in [start, end])
  difference      = computed_ending - ending_balance

  When |difference| <= RECONCILE_TOLERANCE the batch may be marked reconciled.

Sign convention
---------------
  Outflows (payments, withdrawals) are stored as **negative** amounts.
  Inflows (deposits, credits)      are stored as **positive** amounts.
"""

from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RECONCILE_TOLERANCE = 0.00   # cents-exact reconciliation
ACCOUNT_TYPES = ("checking", "savings", "credit_card", "other")

# ---------------------------------------------------------------------------
# Schema versioning (Issue #21)
# ---------------------------------------------------------------------------

# Bump this number whenever you add a migration below.
SCHEMA_VERSION = 2

_DDL_SCHEMA_VERSION = """
CREATE TABLE IF NOT EXISTS schema_version (
    id      INTEGER PRIMARY KEY CHECK (id = 1),
    version INTEGER NOT NULL DEFAULT 0
);
"""

# Ordered list of (version, sql) migration tuples.
# Each entry upgrades the DB from (version-1) to version.
_MIGRATIONS: list[tuple[int, str]] = [
    # v1 – initial schema (bank_accounts, batches, transactions)
    (1, """
CREATE TABLE IF NOT EXISTS bank_accounts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    account_number  TEXT,
    bank_name       TEXT,
    account_type    TEXT    NOT NULL DEFAULT 'checking',
    created_at      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS bank_import_batches (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_account_id     INTEGER NOT NULL
                            REFERENCES bank_accounts(id) ON DELETE CASCADE,
    filename            TEXT,
    imported_at         TEXT    NOT NULL,
    statement_start     TEXT,
    statement_end       TEXT,
    beginning_balance   REAL,
    ending_balance      REAL,
    is_reconciled       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bank_transactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id        INTEGER NOT NULL
                        REFERENCES bank_import_batches(id) ON DELETE CASCADE,
    bank_account_id INTEGER NOT NULL
                        REFERENCES bank_accounts(id) ON DELETE CASCADE,
    txn_date        TEXT    NOT NULL,
    description     TEXT,
    amount          REAL    NOT NULL,
    ref_number      TEXT,
    fingerprint     TEXT    NOT NULL,
    UNIQUE (bank_account_id, fingerprint)
);
"""),
    # v2 – extend bank_accounts with institution, last4, notes, is_active,
    #       updated_at (Issue #30)
    (2, """
ALTER TABLE bank_accounts ADD COLUMN institution  TEXT    NOT NULL DEFAULT '';
ALTER TABLE bank_accounts ADD COLUMN last4        TEXT    NOT NULL DEFAULT '';
ALTER TABLE bank_accounts ADD COLUMN notes        TEXT    NOT NULL DEFAULT '';
ALTER TABLE bank_accounts ADD COLUMN is_active    INTEGER NOT NULL DEFAULT 1;
ALTER TABLE bank_accounts ADD COLUMN updated_at   TEXT;
"""),
]


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Bring the DB schema up to SCHEMA_VERSION, running any pending migrations."""
    conn.executescript(_DDL_SCHEMA_VERSION)
    conn.commit()

    row = conn.execute("SELECT version FROM schema_version WHERE id = 1").fetchone()
    current = row["version"] if row else 0

    if current == 0:
        conn.execute(
            "INSERT OR REPLACE INTO schema_version (id, version) VALUES (1, 0)"
        )
        conn.commit()

    for version, sql in _MIGRATIONS:
        if version <= current:
            continue
        # Run each ALTER TABLE statement individually so SQLite doesn't choke
        for statement in sql.strip().split(";"):
            s = statement.strip()
            if s:
                try:
                    conn.execute(s)
                except sqlite3.OperationalError as exc:
                    # Ignore "duplicate column name" – column already exists from
                    # a previous partial migration attempt.
                    if "duplicate column name" not in str(exc).lower():
                        raise
        conn.execute(
            "UPDATE schema_version SET version = ? WHERE id = 1", (version,)
        )
        conn.commit()
        current = version


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

_DDL_PRAGMA = "PRAGMA foreign_keys = ON;"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(_DDL_PRAGMA)
    conn.commit()
    _apply_migrations(conn)
    return conn


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_DATE_FORMATS = [
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%m-%d-%Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%Y%m%d",
]


def parse_date(raw: str) -> Optional[str]:
    """Parse a raw date string → ISO-8601 'YYYY-MM-DD', or None on failure."""
    raw = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def parse_amount(raw: str) -> Optional[float]:
    """
    Parse a monetary string to a float.

    Handles:
      - Leading/trailing whitespace
      - Currency symbols ($, £, €)
      - Parentheses for negatives: (1,234.56) → -1234.56
      - Comma thousands separators
    """
    raw = raw.strip()
    negative = raw.startswith("(") and raw.endswith(")")
    raw = raw.strip("()")
    raw = re.sub(r"[£$€\s,]", "", raw)
    try:
        value = float(raw)
    except ValueError:
        return None
    return -abs(value) if negative else value


def make_fingerprint(bank_account_id: int, txn_date: str, description: str, amount: float, ref_number: str = "") -> str:
    """Return a stable hex fingerprint for deduplication."""
    key = f"{bank_account_id}|{txn_date}|{description}|{round(amount, 2):.2f}|{ref_number}"
    return hashlib.sha256(key.encode()).hexdigest()


# ---------------------------------------------------------------------------
# CSV import
# ---------------------------------------------------------------------------

def parse_csv(
    content: str,
    date_col: str,
    amount_col: str,
    description_col: str = "",
    ref_col: str = "",
    encoding: str = "utf-8",
) -> list[dict]:
    """
    Parse *content* (CSV text) using the supplied column-name mapping.

    Returns a list of dicts with keys:
        txn_date, description, amount, ref_number

    Rows where date or amount cannot be parsed are silently skipped.
    """
    rows = []
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        # --- date ---
        raw_date = row.get(date_col, "").strip()
        txn_date = parse_date(raw_date)
        if not txn_date:
            continue

        # --- amount ---
        raw_amt = row.get(amount_col, "").strip()
        amount = parse_amount(raw_amt)
        if amount is None:
            continue

        description = row.get(description_col, "").strip() if description_col else ""
        ref_number = row.get(ref_col, "").strip() if ref_col else ""

        rows.append(
            dict(
                txn_date=txn_date,
                description=description,
                amount=amount,
                ref_number=ref_number,
            )
        )
    return rows


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------

def compute_reconciliation(
    transactions: list[dict],
    beginning_balance: float,
    ending_balance: float,
    statement_start: Optional[str] = None,
    statement_end: Optional[str] = None,
) -> dict:
    """
    Compute reconciliation for a list of transaction dicts.

    Each dict must have at minimum a ``txn_date`` (ISO-8601) and ``amount``
    (float, outflows negative).

    Args:
        transactions:      All transactions for the account.
        beginning_balance: Statement opening balance.
        ending_balance:    Statement closing balance per the bank.
        statement_start:   ISO-8601 date (inclusive).  None = no lower bound.
        statement_end:     ISO-8601 date (inclusive).  None = no upper bound.

    Returns a dict with:
        transaction_count  – number of transactions in range
        sum_of_amounts     – algebraic sum (outflows negative)
        computed_ending    – beginning_balance + sum_of_amounts
        difference         – computed_ending − ending_balance
        can_reconcile      – True when |difference| <= RECONCILE_TOLERANCE
    """
    in_range = []
    for txn in transactions:
        d = txn.get("txn_date", "")
        if statement_start and d < statement_start:
            continue
        if statement_end and d > statement_end:
            continue
        in_range.append(txn)

    total = round(sum(t["amount"] for t in in_range), 2)
    computed_ending = round(beginning_balance + total, 2)
    difference = round(computed_ending - ending_balance, 2)
    can_reconcile = abs(difference) <= RECONCILE_TOLERANCE

    return dict(
        transaction_count=len(in_range),
        sum_of_amounts=total,
        computed_ending=computed_ending,
        difference=difference,
        can_reconcile=can_reconcile,
    )


# ---------------------------------------------------------------------------
# BankDatabase
# ---------------------------------------------------------------------------

class BankDatabase:
    """
    SQLite-backed store for bank accounts, import batches, and transactions.

    Supports an arbitrary *db_path* so tests can use isolated temp files.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            from probooksai.database import get_data_dir
            db_path = str(get_data_dir() / "probooksai.db")
        self._db_path = db_path
        self._conn = _connect(db_path)

    # -- context manager -----------------------------------------------------

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    # -----------------------------------------------------------------------
    # Bank accounts
    # -----------------------------------------------------------------------

    def add_bank_account(
        self,
        name: str,
        account_number: str = "",
        bank_name: str = "",
        account_type: str = "checking",
        institution: str = "",
        last4: str = "",
        notes: str = "",
        is_active: bool = True,
    ) -> int:
        """Create a new bank account record.  Returns new row id."""
        if account_type not in ACCOUNT_TYPES:
            raise ValueError(f"Invalid account_type {account_type!r}. Must be one of {ACCOUNT_TYPES}")
        now = _now()
        cur = self._conn.execute(
            """
            INSERT INTO bank_accounts
                (name, account_number, bank_name, account_type,
                 institution, last4, notes, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (name, account_number, bank_name, account_type,
             institution, last4, notes, 1 if is_active else 0, now, now),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_bank_account(self, account_id: int) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM bank_accounts WHERE id = ?", (account_id,)
        ).fetchone()

    def list_bank_accounts(self, include_inactive: bool = False) -> list:
        if include_inactive:
            return self._conn.execute(
                "SELECT * FROM bank_accounts ORDER BY name"
            ).fetchall()
        return self._conn.execute(
            "SELECT * FROM bank_accounts WHERE is_active = 1 ORDER BY name"
        ).fetchall()

    def update_bank_account(
        self,
        account_id: int,
        name: str,
        account_number: str = "",
        bank_name: str = "",
        account_type: str = "checking",
        institution: str = "",
        last4: str = "",
        notes: str = "",
        is_active: bool = True,
    ):
        """Update an existing bank account record."""
        if account_type not in ACCOUNT_TYPES:
            raise ValueError(f"Invalid account_type {account_type!r}.")
        self._conn.execute(
            """
            UPDATE bank_accounts
            SET name = ?, account_number = ?, bank_name = ?, account_type = ?,
                institution = ?, last4 = ?, notes = ?, is_active = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (name, account_number, bank_name, account_type,
             institution, last4, notes, 1 if is_active else 0,
             _now(), account_id),
        )
        self._conn.commit()

    def archive_bank_account(self, account_id: int):
        """
        Archive (soft-delete) a bank account by setting is_active = 0.

        Prefer archive over delete when the account has transactions/batches.
        """
        self._conn.execute(
            "UPDATE bank_accounts SET is_active = 0, updated_at = ? WHERE id = ?",
            (_now(), account_id),
        )
        self._conn.commit()

    def delete_bank_account(self, account_id: int):
        """Delete a bank account and all associated data (cascade)."""
        self._conn.execute("DELETE FROM bank_accounts WHERE id = ?", (account_id,))
        self._conn.commit()

    # -----------------------------------------------------------------------
    # Import batches
    # -----------------------------------------------------------------------

    def create_batch(
        self,
        bank_account_id: int,
        filename: str = "",
        statement_start: Optional[str] = None,
        statement_end: Optional[str] = None,
        beginning_balance: Optional[float] = None,
        ending_balance: Optional[float] = None,
    ) -> int:
        """Create an import batch (one per CSV import).  Returns new row id."""
        cur = self._conn.execute(
            """
            INSERT INTO bank_import_batches
                (bank_account_id, filename, imported_at,
                 statement_start, statement_end,
                 beginning_balance, ending_balance)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bank_account_id,
                filename,
                _now(),
                statement_start,
                statement_end,
                beginning_balance,
                ending_balance,
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_batch(self, batch_id: int) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM bank_import_batches WHERE id = ?", (batch_id,)
        ).fetchone()

    def list_batches(self, bank_account_id: Optional[int] = None) -> list:
        if bank_account_id is not None:
            return self._conn.execute(
                "SELECT * FROM bank_import_batches WHERE bank_account_id = ? ORDER BY imported_at DESC",
                (bank_account_id,),
            ).fetchall()
        return self._conn.execute(
            "SELECT * FROM bank_import_batches ORDER BY imported_at DESC"
        ).fetchall()

    def update_batch_statement(
        self,
        batch_id: int,
        statement_start: Optional[str],
        statement_end: Optional[str],
        beginning_balance: Optional[float],
        ending_balance: Optional[float],
    ):
        """Update statement period and balances on an existing batch."""
        self._conn.execute(
            """
            UPDATE bank_import_batches
            SET statement_start = ?, statement_end = ?,
                beginning_balance = ?, ending_balance = ?
            WHERE id = ?
            """,
            (statement_start, statement_end, beginning_balance, ending_balance, batch_id),
        )
        self._conn.commit()

    def mark_batch_reconciled(self, batch_id: int, reconciled: bool = True):
        """Set the is_reconciled flag on a batch."""
        self._conn.execute(
            "UPDATE bank_import_batches SET is_reconciled = ? WHERE id = ?",
            (1 if reconciled else 0, batch_id),
        )
        self._conn.commit()

    # -----------------------------------------------------------------------
    # Transactions
    # -----------------------------------------------------------------------

    def import_transactions(
        self,
        batch_id: int,
        bank_account_id: int,
        rows: list[dict],
    ) -> dict:
        """
        Insert *rows* into bank_transactions, skipping duplicates by fingerprint.

        Args:
            batch_id:        The import batch these rows belong to.
            bank_account_id: The owning bank account.
            rows:            List of dicts with txn_date, description,
                             amount, ref_number.

        Returns:
            dict with keys: inserted, skipped (duplicate count)
        """
        inserted = 0
        skipped = 0
        for row in rows:
            fp = make_fingerprint(
                bank_account_id,
                row["txn_date"],
                row.get("description", ""),
                row["amount"],
                row.get("ref_number", ""),
            )
            try:
                self._conn.execute(
                    """
                    INSERT INTO bank_transactions
                        (batch_id, bank_account_id, txn_date,
                         description, amount, ref_number, fingerprint)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        batch_id,
                        bank_account_id,
                        row["txn_date"],
                        row.get("description", ""),
                        row["amount"],
                        row.get("ref_number", ""),
                        fp,
                    ),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                skipped += 1
        self._conn.commit()
        return dict(inserted=inserted, skipped=skipped)

    def list_transactions(
        self,
        bank_account_id: int,
        statement_start: Optional[str] = None,
        statement_end: Optional[str] = None,
    ) -> list:
        """
        Return transactions for *bank_account_id*, optionally filtered by date.

        Dates are ISO-8601 strings (YYYY-MM-DD), inclusive on both ends.
        """
        params: list = [bank_account_id]
        where = "bank_account_id = ?"
        if statement_start:
            where += " AND txn_date >= ?"
            params.append(statement_start)
        if statement_end:
            where += " AND txn_date <= ?"
            params.append(statement_end)
        return self._conn.execute(
            f"SELECT * FROM bank_transactions WHERE {where} ORDER BY txn_date, id",
            params,
        ).fetchall()

    def get_transaction(self, txn_id: int) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM bank_transactions WHERE id = ?", (txn_id,)
        ).fetchone()

    # -----------------------------------------------------------------------
    # Reconciliation helpers
    # -----------------------------------------------------------------------

    def reconcile_batch(self, batch_id: int) -> dict:
        """
        Compute reconciliation for a batch and, if it can reconcile,
        mark it reconciled.

        Returns the same dict as :func:`compute_reconciliation` plus
        ``batch_id`` and ``reconciled`` (bool indicating whether the batch
        was actually marked reconciled).
        """
        batch = self.get_batch(batch_id)
        if batch is None:
            raise ValueError(f"No batch with id={batch_id}")

        txns = self.list_transactions(
            bank_account_id=batch["bank_account_id"],
            statement_start=batch["statement_start"],
            statement_end=batch["statement_end"],
        )

        result = compute_reconciliation(
            transactions=[dict(t) for t in txns],
            beginning_balance=batch["beginning_balance"] or 0.0,
            ending_balance=batch["ending_balance"] or 0.0,
            statement_start=batch["statement_start"],
            statement_end=batch["statement_end"],
        )

        reconciled = False
        if result["can_reconcile"]:
            self.mark_batch_reconciled(batch_id, True)
            reconciled = True

        result.update(batch_id=batch_id, reconciled=reconciled)
        return result

    # -----------------------------------------------------------------------
    # Full CSV import pipeline
    # -----------------------------------------------------------------------

    def import_csv(
        self,
        bank_account_id: int,
        csv_content: str,
        date_col: str,
        amount_col: str,
        description_col: str = "",
        ref_col: str = "",
        filename: str = "",
        statement_start: Optional[str] = None,
        statement_end: Optional[str] = None,
        beginning_balance: Optional[float] = None,
        ending_balance: Optional[float] = None,
    ) -> dict:
        """
        High-level helper: parse CSV → create batch → import transactions.

        Returns dict with keys:
            batch_id, inserted, skipped, parse_errors
        """
        rows = parse_csv(
            csv_content,
            date_col=date_col,
            amount_col=amount_col,
            description_col=description_col,
            ref_col=ref_col,
        )

        batch_id = self.create_batch(
            bank_account_id=bank_account_id,
            filename=filename,
            statement_start=statement_start,
            statement_end=statement_end,
            beginning_balance=beginning_balance,
            ending_balance=ending_balance,
        )

        counts = self.import_transactions(batch_id, bank_account_id, rows)
        return dict(batch_id=batch_id, **counts, parse_errors=0)
