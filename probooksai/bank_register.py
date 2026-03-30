"""
probooksai.bank_register
========================
SQLite-backed storage for the Bank Account Register feature.

Tables
------
  bank_accounts      – named bank accounts (e.g. "Chase Checking")
  bank_transactions  – individual bank transactions tied to an account
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from probooksai.database import _connect


# ---------------------------------------------------------------------------
# DDL – tables are created / migrated on first connect
# ---------------------------------------------------------------------------

_BANK_DDL = """
CREATE TABLE IF NOT EXISTS bank_accounts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    account_number  TEXT,
    institution     TEXT,
    created_at      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS bank_transactions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_account_id  INTEGER REFERENCES bank_accounts(id) ON DELETE CASCADE,
    date             TEXT    NOT NULL,
    description      TEXT,
    amount           REAL    NOT NULL DEFAULT 0,
    reference_number TEXT,
    memo             TEXT,
    coa_account      TEXT,
    import_batch_id  INTEGER,
    fingerprint      TEXT,
    created_at       TEXT    NOT NULL
);
"""

# Columns added in later iterations – added via ALTER TABLE if absent
_EXTRA_COLUMNS: list[tuple[str, str, str]] = [
    # (table, column, definition)
    ("bank_transactions", "reference_number", "TEXT"),
    ("bank_transactions", "memo",             "TEXT"),
    ("bank_transactions", "coa_account",      "TEXT"),
    ("bank_transactions", "import_batch_id",  "INTEGER"),
    ("bank_transactions", "fingerprint",      "TEXT"),
    ("bank_transactions", "bank_account_id",  "INTEGER"),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Add any missing columns to existing tables (idempotent)."""
    cursor = conn.execute("PRAGMA table_info(bank_transactions)")
    existing = {row[1] for row in cursor.fetchall()}
    for table, col, defn in _EXTRA_COLUMNS:
        if col not in existing:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {defn}")
            except sqlite3.OperationalError:
                pass  # column already exists in a concurrent scenario
    conn.commit()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class BankRegisterDatabase:
    """Manages bank accounts and bank transactions in the shared SQLite DB."""

    def __init__(self, db_path: Optional[str] = None):
        self._conn = _connect(db_path)
        self._conn.executescript(_BANK_DDL)
        self._conn.commit()
        _apply_migrations(self._conn)

    # -- context manager -----------------------------------------------------

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    # -- bank accounts -------------------------------------------------------

    def add_account(
        self,
        name: str,
        account_number: str = "",
        institution: str = "",
    ) -> int:
        """Insert a new bank account and return its id."""
        cur = self._conn.execute(
            """
            INSERT INTO bank_accounts (name, account_number, institution, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (name, account_number or None, institution or None, _now()),
        )
        self._conn.commit()
        return cur.lastrowid

    def list_accounts(self) -> list[sqlite3.Row]:
        """Return all bank accounts ordered by name."""
        return self._conn.execute(
            "SELECT * FROM bank_accounts ORDER BY name COLLATE NOCASE"
        ).fetchall()

    def get_account(self, account_id: int) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM bank_accounts WHERE id = ?", (account_id,)
        ).fetchone()

    # -- bank transactions ---------------------------------------------------

    def add_transaction(
        self,
        date: str,
        description: str,
        amount: float,
        bank_account_id: Optional[int] = None,
        reference_number: str = "",
        memo: str = "",
        coa_account: str = "",
        import_batch_id: Optional[int] = None,
        fingerprint: str = "",
    ) -> int:
        """Insert a bank transaction and return its id."""
        cur = self._conn.execute(
            """
            INSERT INTO bank_transactions
                (bank_account_id, date, description, amount,
                 reference_number, memo, coa_account,
                 import_batch_id, fingerprint, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bank_account_id,
                date,
                description or None,
                amount,
                reference_number or None,
                memo or None,
                coa_account or None,
                import_batch_id,
                fingerprint or None,
                _now(),
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def list_transactions(
        self,
        bank_account_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[sqlite3.Row]:
        """
        Return transactions, optionally filtered.

        Parameters
        ----------
        bank_account_id:
            When provided, only return transactions for this account.
            Pass ``None`` to return transactions for all accounts.
        start_date / end_date:
            ISO-format date strings (``"YYYY-MM-DD"``).  Inclusive on both ends.
        search:
            Case-insensitive substring match against description or memo.
        """
        clauses: list[str] = []
        params: list = []

        if bank_account_id is not None:
            clauses.append("bank_account_id = ?")
            params.append(bank_account_id)

        if start_date:
            clauses.append("date >= ?")
            params.append(start_date)

        if end_date:
            clauses.append("date <= ?")
            params.append(end_date)

        if search:
            clauses.append("(description LIKE ? OR memo LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like])

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM bank_transactions {where} ORDER BY date, id"
        return self._conn.execute(sql, params).fetchall()

    def get_transaction(self, txn_id: int) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM bank_transactions WHERE id = ?", (txn_id,)
        ).fetchone()

    def update_transaction(
        self,
        txn_id: int,
        reference_number: Optional[str] = None,
        memo: Optional[str] = None,
        coa_account: Optional[str] = None,
        description: Optional[str] = None,
    ) -> None:
        """
        Update editable fields on a bank transaction.

        Only fields that are not ``None`` are written; pass an empty string
        ``""`` to clear a field.
        """
        updates: list[str] = []
        params: list = []

        if reference_number is not None:
            updates.append("reference_number = ?")
            params.append(reference_number or None)

        if memo is not None:
            updates.append("memo = ?")
            params.append(memo or None)

        if coa_account is not None:
            updates.append("coa_account = ?")
            params.append(coa_account or None)

        if description is not None:
            updates.append("description = ?")
            params.append(description or None)

        if not updates:
            return

        params.append(txn_id)
        sql = f"UPDATE bank_transactions SET {', '.join(updates)} WHERE id = ?"
        self._conn.execute(sql, params)
        self._conn.commit()
