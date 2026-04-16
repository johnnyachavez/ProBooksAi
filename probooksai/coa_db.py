"""
probooksai.coa_db
=================
SQLite-backed Chart of Accounts (COA) store and editor helpers.

Issue #41 – COA editor (minimal): UI to view/add/edit COA accounts stored
in SQLite. COA entries populate category dropdowns throughout the app and
can be seeded from the existing workbook-based COA data.

Schema
------
  coa_accounts – editable chart of accounts rows
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from probooksai.audit_log import append_audit

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COA_ACCOUNT_TYPES = ("asset", "liability", "equity", "income", "expense")

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_DDL_COA = """
CREATE TABLE IF NOT EXISTS coa_accounts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    account_number TEXT    NOT NULL,
    account_name   TEXT    NOT NULL,
    account_type   TEXT    NOT NULL,    -- asset/liability/equity/income/expense
    sub_type       TEXT    NOT NULL DEFAULT '',
    normal_balance TEXT    NOT NULL DEFAULT 'debit',   -- debit / credit
    description    TEXT    NOT NULL DEFAULT '',
    parent_id      INTEGER REFERENCES coa_accounts(id) ON DELETE SET NULL,
    is_active      INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT    NOT NULL,
    updated_at     TEXT,
    UNIQUE (account_number)
);
"""

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# COADatabase
# ---------------------------------------------------------------------------

class COADatabase:
    """
    Manages the SQLite-backed Chart of Accounts.

    Accepts an open :class:`sqlite3.Connection` (or a file path) so it can
    share the same file as :class:`~probooksai.bank_import.BankDatabase`.
    """

    def __init__(self, conn_or_path):
        if isinstance(conn_or_path, sqlite3.Connection):
            self._conn = conn_or_path
            self._owns_conn = False
        else:
            self._conn = sqlite3.connect(conn_or_path)
            self._conn.row_factory = sqlite3.Row
            self._owns_conn = True

        self._ensure_schema()

    # -- lifecycle -----------------------------------------------------------

    def close(self):
        if self._owns_conn:
            self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    # -- schema setup --------------------------------------------------------

    def _ensure_schema(self):
        self._conn.executescript(_DDL_COA)
        self._conn.commit()

    # -----------------------------------------------------------------------
    # Seed from generate_workbook COA_DATA
    # -----------------------------------------------------------------------

    def seed_from_workbook(self, skip_if_populated: bool = True) -> int:
        """
        Populate ``coa_accounts`` from the workbook's ``COA_DATA``.

        If *skip_if_populated* is True and rows already exist the seed is skipped.
        Returns the number of rows inserted.
        """
        if skip_if_populated:
            count = self._conn.execute(
                "SELECT COUNT(*) FROM coa_accounts"
            ).fetchone()[0]
            if count > 0:
                return 0

        try:
            from generate_workbook import COA_DATA  # type: ignore[import]
        except ImportError:
            return 0

        inserted = 0
        now = _now()
        for row in COA_DATA:
            acct_no, name, acct_type, sub_type, normal_bal, description = row[:6]
            acct_type_norm = acct_type.lower().split()[0]
            if acct_type_norm not in COA_ACCOUNT_TYPES:
                acct_type_norm = "expense"
            try:
                self._conn.execute(
                    """
                    INSERT OR IGNORE INTO coa_accounts
                        (account_number, account_name, account_type,
                         sub_type, normal_balance, description,
                         is_active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (acct_no, name, acct_type_norm, sub_type or "",
                     (normal_bal or "debit").lower(),
                     description or "", now, now),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                pass
        self._conn.commit()
        return inserted

    # -----------------------------------------------------------------------
    # CRUD
    # -----------------------------------------------------------------------

    def add_account(
        self,
        account_number: str,
        account_name: str,
        account_type: str,
        sub_type: str = "",
        normal_balance: str = "debit",
        description: str = "",
        parent_id: Optional[int] = None,
        is_active: bool = True,
    ) -> int:
        """Add a new COA account. Returns the new row id."""
        _validate_type(account_type)
        now = _now()
        cur = self._conn.execute(
            """
            INSERT INTO coa_accounts
                (account_number, account_name, account_type,
                 sub_type, normal_balance, description,
                 parent_id, is_active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (account_number, account_name, account_type,
             sub_type, normal_balance.lower(), description,
             parent_id, 1 if is_active else 0, now, now),
        )
        self._conn.commit()
        acct_id = cur.lastrowid
        append_audit(
            self._conn,
            "coa_account",
            acct_id,
            "created",
            None,
            f"{account_number} {account_name}",
        )
        return acct_id

    def get_account(self, account_id: int) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM coa_accounts WHERE id = ?", (account_id,)
        ).fetchone()

    def get_account_by_number(self, account_number: str) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM coa_accounts WHERE account_number = ?",
            (account_number,),
        ).fetchone()

    def list_accounts(self, include_inactive: bool = False) -> list:
        """Return all active (or all) COA accounts ordered by account_number."""
        if include_inactive:
            return self._conn.execute(
                "SELECT * FROM coa_accounts ORDER BY account_number"
            ).fetchall()
        return self._conn.execute(
            "SELECT * FROM coa_accounts WHERE is_active = 1 ORDER BY account_number"
        ).fetchall()

    def update_account(
        self,
        account_id: int,
        account_number: str,
        account_name: str,
        account_type: str,
        sub_type: str = "",
        normal_balance: str = "debit",
        description: str = "",
        parent_id: Optional[int] = None,
        is_active: bool = True,
    ):
        """Update an existing COA account."""
        _validate_type(account_type)
        old = self.get_account(account_id)
        if old is None:
            raise ValueError(f"No COA account with id={account_id}")
        old_d = dict(old)
        self._conn.execute(
            """
            UPDATE coa_accounts
            SET account_number = ?, account_name = ?, account_type = ?,
                sub_type = ?, normal_balance = ?, description = ?,
                parent_id = ?, is_active = ?, updated_at = ?
            WHERE id = ?
            """,
            (account_number, account_name, account_type,
             sub_type, normal_balance.lower(), description,
             parent_id, 1 if is_active else 0, _now(), account_id),
        )
        self._conn.commit()
        new_vals = {
            "account_number": account_number,
            "account_name": account_name,
            "account_type": account_type,
            "sub_type": sub_type or "",
            "normal_balance": normal_balance.lower(),
            "description": description or "",
            "parent_id": parent_id,
            "is_active": 1 if is_active else 0,
        }
        for field, nv in new_vals.items():
            ov = old_d[field]
            osv = "" if ov is None else str(ov)
            nsv = "" if nv is None else str(nv)
            if osv != nsv:
                append_audit(
                    self._conn,
                    "coa_account",
                    account_id,
                    field,
                    osv or None,
                    nsv or None,
                )

    def delete_account(self, account_id: int):
        """Hard-delete a COA account (use only if it has no references)."""
        old = self.get_account(account_id)
        if old is not None:
            d = dict(old)
            append_audit(
                self._conn,
                "coa_account",
                account_id,
                "deleted",
                f"{d.get('account_number')} {d.get('account_name')}",
                None,
            )
        self._conn.execute(
            "DELETE FROM coa_accounts WHERE id = ?", (account_id,)
        )
        self._conn.commit()

    # -----------------------------------------------------------------------
    # Display helpers (for UI dropdowns)
    # -----------------------------------------------------------------------

    def display_list(self, include_inactive: bool = False) -> list[str]:
        """Return ``'NNNN – Account Name'`` strings for use in UI dropdowns."""
        rows = self.list_accounts(include_inactive=include_inactive)
        return [f"{r['account_number']} – {r['account_name']}" for r in rows]

    def find_account_id_by_display_line(self, line: str) -> Optional[int]:
        """Resolve a register/transaction COA label to ``coa_accounts.id``, or ``None`` if unknown."""
        target = (line or "").strip()
        if not target:
            return None
        tlow = target.lower()
        for row in self.list_accounts(include_inactive=True):
            disp = f"{row['account_number']} – {row['account_name']}"
            if disp == target or disp.lower() == tlow:
                try:
                    return int(row["id"])
                except (TypeError, ValueError):
                    return None
        return None


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_type(account_type: str):
    if account_type.lower() not in COA_ACCOUNT_TYPES:
        raise ValueError(
            f"Invalid account_type {account_type!r}. "
            f"Must be one of {COA_ACCOUNT_TYPES}"
        )
