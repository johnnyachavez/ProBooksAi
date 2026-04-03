"""
probooksai.gl
=============
General Ledger posting engine for ProBooks+ai.

Issue #40 – Posting engine (MVP): post bank transactions to GL journal entries.

Schema
------
  journal_entries      – one row per balanced posting event
  journal_entry_lines  – two or more debit/credit lines per entry (always balanced)

Posting rules (MVP)
-------------------
  For each bank transaction with a selected COA category:
    Line 1 – the bank/cash GL account (debit if inflow, credit if outflow)
    Line 2 – the COA category account  (credit if inflow, debit if outflow)

  Always balanced: SUM(debit) == SUM(credit) for each entry.

Sign convention
---------------
  Positive transaction amount  → inflow  → debit bank,  credit income/revenue
  Negative transaction amount  → outflow → credit bank, debit expense/liability
"""

from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_DDL_GL = """
CREATE TABLE IF NOT EXISTS journal_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date  TEXT    NOT NULL,
    memo        TEXT,
    source      TEXT,           -- e.g. 'bank_import', 'manual'
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS journal_entry_lines (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id    INTEGER NOT NULL
                    REFERENCES journal_entries(id) ON DELETE CASCADE,
    account     TEXT    NOT NULL,   -- COA account name or code
    debit       REAL    NOT NULL DEFAULT 0.0,
    credit      REAL    NOT NULL DEFAULT 0.0,
    description TEXT
);
"""

# Column added to bank_transactions to track posting status
_DDL_POSTED_FLAG = """
ALTER TABLE bank_transactions ADD COLUMN is_posted     INTEGER NOT NULL DEFAULT 0;
ALTER TABLE bank_transactions ADD COLUMN journal_entry_id INTEGER
    REFERENCES journal_entries(id) ON DELETE SET NULL;
"""


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# GLDatabase
# ---------------------------------------------------------------------------

class GLDatabase:
    """
    GL posting engine backed by the shared ProBooks+ai SQLite database.

    Accepts an open :class:`sqlite3.Connection` (or a path) so it can share
    the same file as :class:`~probooksai.bank_import.BankDatabase`.
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
        """Create GL tables if absent; add posted flag columns if needed."""
        self._conn.executescript(_DDL_GL)
        self._conn.commit()

        # Add is_posted / journal_entry_id columns to bank_transactions
        # if they don't exist yet (safe to run repeatedly).
        for stmt in _DDL_POSTED_FLAG.strip().split(";"):
            s = stmt.strip()
            if s:
                try:
                    self._conn.execute(s)
                    self._conn.commit()
                except sqlite3.OperationalError as exc:
                    if "duplicate column name" not in str(exc).lower():
                        raise

    # -----------------------------------------------------------------------
    # Journal entries
    # -----------------------------------------------------------------------

    def create_journal_entry(
        self,
        entry_date: str,
        lines: list[dict],
        memo: str = "",
        source: str = "manual",
    ) -> int:
        """
        Create a balanced journal entry.

        *lines* is a list of dicts with keys:
            account (str), debit (float), credit (float), description (str, optional)

        Raises ``ValueError`` if the entry is not balanced
        (total debits != total credits, within 0.005 rounding tolerance).

        Returns the new ``journal_entries.id``.
        """
        total_debit  = round(sum(ln.get("debit",  0.0) for ln in lines), 2)
        total_credit = round(sum(ln.get("credit", 0.0) for ln in lines), 2)
        if abs(total_debit - total_credit) > 0.005:
            raise ValueError(
                f"Journal entry is not balanced: "
                f"debit={total_debit:.2f}, credit={total_credit:.2f}"
            )

        cur = self._conn.execute(
            """
            INSERT INTO journal_entries (entry_date, memo, source, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (entry_date, memo, source, _now()),
        )
        entry_id = cur.lastrowid

        for ln in lines:
            self._conn.execute(
                """
                INSERT INTO journal_entry_lines
                    (entry_id, account, debit, credit, description)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    ln["account"],
                    round(ln.get("debit", 0.0), 2),
                    round(ln.get("credit", 0.0), 2),
                    ln.get("description", ""),
                ),
            )

        self._conn.commit()
        return entry_id

    def get_journal_entry(self, entry_id: int) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM journal_entries WHERE id = ?", (entry_id,)
        ).fetchone()

    def get_entry_lines(self, entry_id: int) -> list:
        return self._conn.execute(
            "SELECT * FROM journal_entry_lines WHERE entry_id = ? ORDER BY id",
            (entry_id,),
        ).fetchall()

    def list_journal_entries(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list:
        """List journal entries, optionally filtered by entry_date range."""
        params: list = []
        where_parts: list[str] = []
        if start_date:
            where_parts.append("entry_date >= ?")
            params.append(start_date)
        if end_date:
            where_parts.append("entry_date <= ?")
            params.append(end_date)
        where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
        return self._conn.execute(
            f"SELECT * FROM journal_entries {where} ORDER BY entry_date, id",
            params,
        ).fetchall()

    def journal_export_rows(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[dict]:
        """
        Flatten journal entries in the date range to one dict per GL line
        (for CSV export).
        """
        entries = self.list_journal_entries(start_date, end_date)
        out: list[dict] = []
        for e in entries:
            eid = e["id"]
            entry = self.get_journal_entry(eid)
            if entry is None:
                continue
            lines = self.get_entry_lines(eid)
            edate = entry["entry_date"]
            ememo = entry["memo"] or ""
            for ln in lines:
                d = dict(ln)
                out.append(
                    {
                        "entry_id": eid,
                        "entry_date": edate,
                        "entry_memo": ememo,
                        "account": d.get("account") or "",
                        "debit": round(float(d.get("debit") or 0.0), 2),
                        "credit": round(float(d.get("credit") or 0.0), 2),
                        "line_description": d.get("description") or "",
                    }
                )
        return out

    # -----------------------------------------------------------------------
    # Posting bank transactions
    # -----------------------------------------------------------------------

    def _fetch_txn_splits(self, txn_id: int) -> list:
        try:
            return self._conn.execute(
                """
                SELECT amount, coa_account, memo FROM bank_txn_splits
                WHERE parent_txn_id = ? ORDER BY id
                """,
                (txn_id,),
            ).fetchall()
        except sqlite3.OperationalError:
            return []

    def _bank_gl_display(self, bank_account_id: int) -> str:
        row = self._conn.execute(
            "SELECT gl_display_account FROM bank_accounts WHERE id = ?",
            (bank_account_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Bank account id={bank_account_id} not found")
        g = (row["gl_display_account"] or "").strip()
        if not g:
            raise ValueError(
                f"Bank account id={bank_account_id} has no GL cash account mapping"
            )
        return g

    def _post_transfer_transaction(
        self,
        txn_id: int,
        txn: sqlite3.Row,
        source_bank_gl: str,
        dest_bank_account_id: int,
        memo: str,
    ) -> int:
        """Bank-to-bank move: only cash GL accounts; no income/expense."""
        dest_gl = self._bank_gl_display(dest_bank_account_id)
        description = txn["description"] or "Transfer"
        amount = round(float(txn["amount"]), 2)
        abs_amount = abs(amount)
        if amount >= 0:
            lines = [
                {
                    "account": source_bank_gl,
                    "debit": abs_amount,
                    "credit": 0.0,
                    "description": description,
                },
                {
                    "account": dest_gl,
                    "debit": 0.0,
                    "credit": abs_amount,
                    "description": description,
                },
            ]
        else:
            lines = [
                {
                    "account": source_bank_gl,
                    "debit": 0.0,
                    "credit": abs_amount,
                    "description": description,
                },
                {
                    "account": dest_gl,
                    "debit": abs_amount,
                    "credit": 0.0,
                    "description": description,
                },
            ]
        entry_id = self.create_journal_entry(
            entry_date=txn["txn_date"],
            lines=lines,
            memo=memo or description,
            source="bank_transfer",
        )
        self._conn.execute(
            """
            UPDATE bank_transactions
            SET is_posted = 1, journal_entry_id = ?
            WHERE id = ?
            """,
            (entry_id, txn_id),
        )
        self._conn.commit()
        return entry_id

    def _post_transaction_with_splits(
        self,
        txn_id: int,
        bank_gl_account: str,
        txn: sqlite3.Row,
        splits: list,
        memo: str,
    ) -> int:
        amount = round(float(txn["amount"]), 2)
        split_total = round(sum(float(s["amount"]) for s in splits), 2)
        if abs(split_total - amount) > 0.02:
            raise ValueError("Split amounts do not match transaction amount")
        abs_amount = abs(amount)
        sum_abs_parts = round(
            sum(abs(round(float(s["amount"]), 2)) for s in splits), 2
        )
        if abs(sum_abs_parts - abs_amount) > 0.02:
            raise ValueError("Split amounts do not match transaction amount")
        description = txn["description"] or ""
        lines: list[dict] = []
        if amount >= 0:
            lines.append(
                {
                    "account": bank_gl_account,
                    "debit": abs_amount,
                    "credit": 0.0,
                    "description": description,
                }
            )
            for s in splits:
                coa = (s["coa_account"] or "").strip()
                if not coa:
                    raise ValueError("Each split line must have a COA account")
                part = abs(round(float(s["amount"]), 2))
                line_desc = (s["memo"] or "").strip() or description
                lines.append(
                    {
                        "account": coa,
                        "debit": 0.0,
                        "credit": part,
                        "description": line_desc,
                    }
                )
        else:
            lines.append(
                {
                    "account": bank_gl_account,
                    "debit": 0.0,
                    "credit": abs_amount,
                    "description": description,
                }
            )
            for s in splits:
                coa = (s["coa_account"] or "").strip()
                if not coa:
                    raise ValueError("Each split line must have a COA account")
                part = abs(round(float(s["amount"]), 2))
                line_desc = (s["memo"] or "").strip() or description
                lines.append(
                    {
                        "account": coa,
                        "debit": part,
                        "credit": 0.0,
                        "description": line_desc,
                    }
                )

        entry_id = self.create_journal_entry(
            entry_date=txn["txn_date"],
            lines=lines,
            memo=memo or description,
            source="bank_import",
        )
        self._conn.execute(
            """
            UPDATE bank_transactions
            SET is_posted = 1, journal_entry_id = ?
            WHERE id = ?
            """,
            (entry_id, txn_id),
        )
        self._conn.commit()
        return entry_id

    def post_transaction(
        self,
        txn_id: int,
        bank_gl_account: str,
        category_account: str,
        memo: str = "",
    ) -> int:
        """
        Post a single bank transaction to the GL.

        When ``bank_txn_splits`` rows exist for this transaction, posts one bank
        line and one line per split (``category_account`` is ignored).

        Otherwise creates a two-line balanced journal entry:
          - Positive amount (inflow):  debit bank GL,  credit category account
          - Negative amount (outflow): credit bank GL, debit category account

        Raises ``ValueError`` if the transaction is already posted or not found.

        Returns the new ``journal_entries.id``.
        """
        txn = self._conn.execute(
            "SELECT * FROM bank_transactions WHERE id = ?", (txn_id,)
        ).fetchone()
        if txn is None:
            raise ValueError(f"Transaction id={txn_id} not found")
        posted = int(dict(txn).get("is_posted") or 0)
        if posted:
            raise ValueError(f"Transaction id={txn_id} is already posted")

        td = dict(txn)
        transfer_to = td.get("transfer_to_bank_account_id")
        splits = self._fetch_txn_splits(txn_id)
        if transfer_to is not None:
            if splits:
                raise ValueError(
                    "Remove split lines before posting a bank-to-bank transfer"
                )
            return self._post_transfer_transaction(
                txn_id,
                txn,
                bank_gl_account,
                int(transfer_to),
                memo,
            )
        if splits:
            return self._post_transaction_with_splits(
                txn_id, bank_gl_account, txn, splits, memo
            )

        category_account = (category_account or "").strip()
        if not category_account:
            raise ValueError("No COA category selected for posting")

        amount = round(txn["amount"], 2)
        abs_amount = abs(amount)
        description = txn["description"] or ""

        if amount >= 0:
            # Inflow: debit bank, credit category
            lines = [
                {"account": bank_gl_account,   "debit": abs_amount, "credit": 0.0, "description": description},
                {"account": category_account,   "debit": 0.0, "credit": abs_amount, "description": description},
            ]
        else:
            # Outflow: credit bank, debit category
            lines = [
                {"account": bank_gl_account,   "debit": 0.0, "credit": abs_amount, "description": description},
                {"account": category_account,   "debit": abs_amount, "credit": 0.0, "description": description},
            ]

        entry_id = self.create_journal_entry(
            entry_date=txn["txn_date"],
            lines=lines,
            memo=memo or description,
            source="bank_import",
        )

        self._conn.execute(
            """
            UPDATE bank_transactions
            SET is_posted = 1, journal_entry_id = ?
            WHERE id = ?
            """,
            (entry_id, txn_id),
        )
        self._conn.commit()
        return entry_id

    def post_transactions_bulk(
        self,
        txn_ids: list[int],
        bank_gl_account: str,
        category_account_map: dict[int, str],
        memo: str = "",
    ) -> dict:
        """
        Post multiple transactions in a single operation.

        *category_account_map* maps txn_id → COA account name.
        Transactions without a mapping in the dict are skipped.

        Returns a dict:
            posted  – list of (txn_id, entry_id) pairs
            skipped – list of txn_ids that were skipped (already posted / no mapping)
            errors  – list of (txn_id, error_message) pairs
        """
        posted = []
        skipped = []
        errors = []
        for txn_id in txn_ids:
            has_splits = bool(self._fetch_txn_splits(txn_id))
            row = self._conn.execute(
                "SELECT transfer_to_bank_account_id FROM bank_transactions WHERE id = ?",
                (txn_id,),
            ).fetchone()
            has_transfer = row is not None and row["transfer_to_bank_account_id"] is not None
            if (
                not has_splits
                and not has_transfer
                and txn_id not in category_account_map
            ):
                skipped.append(txn_id)
                continue
            cat = category_account_map.get(txn_id, "")
            try:
                entry_id = self.post_transaction(
                    txn_id=txn_id,
                    bank_gl_account=bank_gl_account,
                    category_account=cat,
                    memo=memo,
                )
                posted.append((txn_id, entry_id))
            except ValueError as exc:
                if "already posted" in str(exc):
                    skipped.append(txn_id)
                else:
                    errors.append((txn_id, str(exc)))
        return dict(posted=posted, skipped=skipped, errors=errors)

    # -----------------------------------------------------------------------
    # Trial balance (simple)
    # -----------------------------------------------------------------------

    def trial_balance(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[dict]:
        """
        Return a simple trial balance as a list of dicts:
            account, total_debit, total_credit, net

        Optionally filtered by journal entry date range.
        """
        entries = self.list_journal_entries(start_date, end_date)
        entry_ids = [e["id"] for e in entries]
        if not entry_ids:
            return []

        placeholders = ",".join("?" * len(entry_ids))
        rows = self._conn.execute(
            f"""
            SELECT account,
                   SUM(debit)  AS total_debit,
                   SUM(credit) AS total_credit
            FROM journal_entry_lines
            WHERE entry_id IN ({placeholders})
            GROUP BY account
            ORDER BY account
            """,
            entry_ids,
        ).fetchall()

        return [
            {
                "account":      row["account"],
                "total_debit":  round(row["total_debit"] or 0.0, 2),
                "total_credit": round(row["total_credit"] or 0.0, 2),
                "net":          round((row["total_debit"] or 0.0) - (row["total_credit"] or 0.0), 2),
            }
            for row in rows
        ]


def write_journal_export_csv(path: str, rows: list[dict]) -> int:
    """
    Write *rows* from :meth:`GLDatabase.journal_export_rows` to UTF-8 CSV.
    Returns the number of data lines (excluding the header).
    """
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "entry_id",
                "entry_date",
                "entry_memo",
                "account",
                "debit",
                "credit",
                "line_description",
            ]
        )
        n = 0
        for r in rows:
            w.writerow(
                [
                    r["entry_id"],
                    r["entry_date"],
                    r["entry_memo"],
                    r["account"],
                    f"{r['debit']:.2f}",
                    f"{r['credit']:.2f}",
                    r["line_description"],
                ]
            )
            n += 1
    return n
