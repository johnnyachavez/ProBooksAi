"""
probooksai.database
===================
SQLite-backed local storage for ProBooksAi document intake.

Schema
------
  documents       – imported files (path, hash, status, …)
  extractions     – AI-extracted fields (raw JSON + parsed)
  approved_values – human-reviewed / approved field values
  status_log      – audit trail of every status change
"""

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Application data directory (Windows-friendly)
# ---------------------------------------------------------------------------

def get_data_dir() -> Path:
    """Return (and create) the per-user ProBooksAi data directory."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        base = Path(appdata)
    else:
        base = Path.home()
    data_dir = base / "ProBooksAi"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_docs_dir() -> Path:
    """Return (and create) the directory where imported originals are stored."""
    docs = get_data_dir() / "documents"
    docs.mkdir(parents=True, exist_ok=True)
    return docs


# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

_DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS bank_accounts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    institution TEXT,
    last4       TEXT,
    external_id TEXT,
    created_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bank_accounts_name ON bank_accounts (name);

CREATE TABLE IF NOT EXISTS bank_import_batches (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source_filename     TEXT    NOT NULL,
    imported_at         TEXT    NOT NULL,
    format_meta         TEXT,
    bank_account_id     INTEGER REFERENCES bank_accounts(id) ON DELETE SET NULL,
    statement_start_date TEXT,
    statement_end_date   TEXT,
    beginning_balance    REAL,
    ending_balance       REAL,
    is_reconciled        INTEGER NOT NULL DEFAULT 0,
    reconciled_at        TEXT,
    reconciled_difference REAL
);

CREATE TABLE IF NOT EXISTS bank_transactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id        INTEGER NOT NULL REFERENCES bank_import_batches(id) ON DELETE CASCADE,
    posted_date     TEXT,
    description     TEXT    NOT NULL DEFAULT '',
    amount          REAL,
    currency        TEXT    NOT NULL DEFAULT 'USD',
    source_row      INTEGER,
    fingerprint     TEXT    NOT NULL DEFAULT '',
    coa_account     TEXT,
    status          TEXT    NOT NULL DEFAULT 'Imported',
    is_duplicate    INTEGER NOT NULL DEFAULT 0,
    parse_errors    TEXT,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bank_txn_batch  ON bank_transactions (batch_id);
CREATE INDEX IF NOT EXISTS idx_bank_txn_finger ON bank_transactions (fingerprint);

CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    filename    TEXT    NOT NULL,
    stored_path TEXT    NOT NULL,
    file_hash   TEXT    NOT NULL,
    mimetype    TEXT    NOT NULL,
    import_date TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'New',
    page_count  INTEGER,
    notes       TEXT
);

CREATE TABLE IF NOT EXISTS extractions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id     INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    raw_json        TEXT,
    vendor          TEXT,
    doc_type        TEXT,
    invoice_number  TEXT,
    doc_date        TEXT,
    due_date        TEXT,
    subtotal        REAL,
    tax             REAL,
    total           REAL,
    currency        TEXT DEFAULT 'USD',
    line_items_json TEXT,
    notes           TEXT,
    confidence      REAL,
    extracted_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approved_values (
    document_id     INTEGER PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    vendor          TEXT,
    doc_type        TEXT,
    invoice_number  TEXT,
    doc_date        TEXT,
    due_date        TEXT,
    subtotal        REAL,
    tax             REAL,
    total           REAL,
    currency        TEXT,
    notes           TEXT,
    coa_account     TEXT,
    tax_category    TEXT,
    approved_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS status_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    old_status  TEXT,
    new_status  TEXT NOT NULL,
    changed_at  TEXT NOT NULL
);
"""

_VALID_STATUSES = {"New", "Extracted", "Needs Review", "Approved", "Posted", "Error"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Open (or create) the SQLite database and return a connection."""
    if db_path is None:
        db_path = str(get_data_dir() / "probooksai.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    _migrate(conn)
    conn.commit()
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply additive migrations for databases created before Issue #12."""
    # Add new columns to bank_import_batches if they are missing (SQLite
    # does not support IF NOT EXISTS for ALTER TABLE ADD COLUMN, so we check
    # the column list first).
    existing = {
        row[1]
        for row in conn.execute("PRAGMA table_info(bank_import_batches)").fetchall()
    }
    _add_column_if_missing = [
        ("bank_account_id",      "INTEGER REFERENCES bank_accounts(id) ON DELETE SET NULL"),
        ("statement_start_date", "TEXT"),
        ("statement_end_date",   "TEXT"),
        ("beginning_balance",    "REAL"),
        ("ending_balance",       "REAL"),
        ("is_reconciled",        "INTEGER NOT NULL DEFAULT 0"),
        ("reconciled_at",        "TEXT"),
        ("reconciled_difference","REAL"),
    ]
    for col, col_def in _add_column_if_missing:
        if col not in existing:
            conn.execute(
                f"ALTER TABLE bank_import_batches ADD COLUMN {col} {col_def}"
            )

    # Indexes that reference new columns must be created after migration
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_batch_account ON bank_import_batches (bank_account_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_batch_dates ON bank_import_batches "
        "(statement_start_date, statement_end_date)"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class DocumentDatabase:
    """Thin wrapper around the SQLite database for document intake."""

    def __init__(self, db_path: Optional[str] = None):
        self._conn = _connect(db_path)

    # -- helpers -------------------------------------------------------------

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    # -- documents -----------------------------------------------------------

    def add_document(
        self,
        source_path: str,
        mimetype: str,
        store: bool = True,
    ) -> int:
        """
        Import a document.

        If *store* is True the file is copied into the ProBooksAi data
        directory; otherwise the original path is recorded as-is.

        Returns the new document ``id``.
        """
        src = Path(source_path)
        file_hash = _file_hash(src)
        filename = src.name

        if store:
            dest_dir = get_docs_dir()
            stored_path = _unique_path(dest_dir, filename)
            import shutil
            shutil.copy2(src, stored_path)
        else:
            stored_path = src

        page_count = _count_pages(str(stored_path), mimetype)

        cur = self._conn.execute(
            """
            INSERT INTO documents (filename, stored_path, file_hash, mimetype,
                                   import_date, status, page_count)
            VALUES (?, ?, ?, ?, ?, 'New', ?)
            """,
            (filename, str(stored_path), file_hash, mimetype, _now(), page_count),
        )
        doc_id = cur.lastrowid
        self._log_status(doc_id, None, "New")
        self._conn.commit()
        return doc_id

    def get_document(self, doc_id: int) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()

    def list_documents(self) -> list:
        return self._conn.execute(
            "SELECT * FROM documents ORDER BY import_date DESC"
        ).fetchall()

    def set_status(self, doc_id: int, new_status: str):
        if new_status not in _VALID_STATUSES:
            raise ValueError(f"Unknown status: {new_status!r}")
        row = self.get_document(doc_id)
        old_status = row["status"] if row else None
        self._conn.execute(
            "UPDATE documents SET status = ? WHERE id = ?",
            (new_status, doc_id),
        )
        self._log_status(doc_id, old_status, new_status)
        self._conn.commit()

    # -- extractions ---------------------------------------------------------

    def save_extraction(self, doc_id: int, result) -> int:
        """
        Persist an :class:`ai.ExtractionResult` for *doc_id*.

        Returns the extraction row ``id``.
        """
        line_items_json = json.dumps(getattr(result, "line_items", []))
        cur = self._conn.execute(
            """
            INSERT INTO extractions
                (document_id, raw_json, vendor, doc_type, invoice_number,
                 doc_date, due_date, subtotal, tax, total, currency,
                 line_items_json, notes, confidence, extracted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id,
                result.raw_response,
                result.vendor,
                result.doc_type,
                result.invoice_number,
                result.doc_date,
                result.due_date,
                result.subtotal,
                result.tax,
                result.total,
                result.currency,
                line_items_json,
                result.notes,
                result.confidence,
                _now(),
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_latest_extraction(self, doc_id: int) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            """
            SELECT * FROM extractions
            WHERE document_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (doc_id,),
        ).fetchone()

    # -- approved values -----------------------------------------------------

    def save_approved(self, doc_id: int, values: dict):
        """
        Upsert approved field values for *doc_id*.

        *values* is a plain dict with keys matching the column names of the
        ``approved_values`` table (e.g. ``vendor``, ``total``, …).
        """
        values = dict(values)
        values["document_id"] = doc_id
        values["approved_at"] = _now()

        cols = ", ".join(values.keys())
        placeholders = ", ".join("?" * len(values))
        self._conn.execute(
            f"""
            INSERT INTO approved_values ({cols}) VALUES ({placeholders})
            ON CONFLICT(document_id) DO UPDATE SET
                vendor        = excluded.vendor,
                doc_type      = excluded.doc_type,
                invoice_number= excluded.invoice_number,
                doc_date      = excluded.doc_date,
                due_date      = excluded.due_date,
                subtotal      = excluded.subtotal,
                tax           = excluded.tax,
                total         = excluded.total,
                currency      = excluded.currency,
                notes         = excluded.notes,
                coa_account   = excluded.coa_account,
                tax_category  = excluded.tax_category,
                approved_at   = excluded.approved_at
            """,
            list(values.values()),
        )
        self._conn.commit()

    def get_approved(self, doc_id: int) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM approved_values WHERE document_id = ?", (doc_id,)
        ).fetchone()

    # -- status log ----------------------------------------------------------

    def get_status_log(self, doc_id: int) -> list:
        return self._conn.execute(
            "SELECT * FROM status_log WHERE document_id = ? ORDER BY id",
            (doc_id,),
        ).fetchall()

    def _log_status(self, doc_id: int, old_status, new_status: str):
        self._conn.execute(
            "INSERT INTO status_log (document_id, old_status, new_status, changed_at) VALUES (?, ?, ?, ?)",
            (doc_id, old_status, new_status, _now()),
        )

    # -- bank accounts -------------------------------------------------------

    def create_bank_account(
        self,
        name: str,
        institution: Optional[str] = None,
        last4: Optional[str] = None,
        external_id: Optional[str] = None,
    ) -> int:
        """Create a new bank account and return its ``id``."""
        cur = self._conn.execute(
            """
            INSERT INTO bank_accounts (name, institution, last4, external_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, institution, last4, external_id, _now()),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_bank_account(self, account_id: int) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM bank_accounts WHERE id = ?", (account_id,)
        ).fetchone()

    def list_bank_accounts(self) -> list:
        return self._conn.execute(
            "SELECT * FROM bank_accounts ORDER BY name ASC"
        ).fetchall()

    def update_bank_account(
        self,
        account_id: int,
        name: Optional[str] = None,
        institution: Optional[str] = None,
        last4: Optional[str] = None,
        external_id: Optional[str] = None,
    ):
        """Patch one or more fields on a bank account row."""
        updates: list[str] = []
        params: list = []
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if institution is not None:
            updates.append("institution = ?")
            params.append(institution)
        if last4 is not None:
            updates.append("last4 = ?")
            params.append(last4)
        if external_id is not None:
            updates.append("external_id = ?")
            params.append(external_id)
        if not updates:
            return
        params.append(account_id)
        self._conn.execute(
            f"UPDATE bank_accounts SET {', '.join(updates)} WHERE id = ?", params
        )
        self._conn.commit()

    def delete_bank_account(self, account_id: int):
        """Delete a bank account (batches become unlinked via SET NULL)."""
        self._conn.execute("DELETE FROM bank_accounts WHERE id = ?", (account_id,))
        self._conn.commit()

    # -- bank import batches -------------------------------------------------

    def create_batch(
        self,
        source_filename: str,
        format_meta: str = "",
        bank_account_id: Optional[int] = None,
        statement_start_date: Optional[str] = None,
        statement_end_date: Optional[str] = None,
        beginning_balance: Optional[float] = None,
        ending_balance: Optional[float] = None,
    ) -> int:
        """Create a new import batch and return its ``id``."""
        cur = self._conn.execute(
            """
            INSERT INTO bank_import_batches
                (source_filename, imported_at, format_meta, bank_account_id,
                 statement_start_date, statement_end_date,
                 beginning_balance, ending_balance)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_filename,
                _now(),
                format_meta or None,
                bank_account_id,
                statement_start_date,
                statement_end_date,
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
        bank_account_id: Optional[int] = None,
        statement_start_date: Optional[str] = None,
        statement_end_date: Optional[str] = None,
        beginning_balance: Optional[float] = None,
        ending_balance: Optional[float] = None,
    ):
        """Update statement period and balance fields for a batch."""
        updates: list[str] = []
        params: list = []
        if bank_account_id is not None:
            updates.append("bank_account_id = ?")
            params.append(bank_account_id)
        if statement_start_date is not None:
            updates.append("statement_start_date = ?")
            params.append(statement_start_date)
        if statement_end_date is not None:
            updates.append("statement_end_date = ?")
            params.append(statement_end_date)
        if beginning_balance is not None:
            updates.append("beginning_balance = ?")
            params.append(beginning_balance)
        if ending_balance is not None:
            updates.append("ending_balance = ?")
            params.append(ending_balance)
        if not updates:
            return
        params.append(batch_id)
        self._conn.execute(
            f"UPDATE bank_import_batches SET {', '.join(updates)} WHERE id = ?", params
        )
        self._conn.commit()

    def mark_batch_reconciled(
        self,
        batch_id: int,
        reconciled_difference: float,
    ):
        """Mark a batch as reconciled and persist the difference."""
        self._conn.execute(
            """
            UPDATE bank_import_batches
            SET is_reconciled = 1, reconciled_at = ?, reconciled_difference = ?
            WHERE id = ?
            """,
            (_now(), reconciled_difference, batch_id),
        )
        self._conn.commit()

    def unmark_batch_reconciled(self, batch_id: int):
        """Remove reconciliation status from a batch."""
        self._conn.execute(
            """
            UPDATE bank_import_batches
            SET is_reconciled = 0, reconciled_at = NULL, reconciled_difference = NULL
            WHERE id = ?
            """,
            (batch_id,),
        )
        self._conn.commit()

    # -- bank transactions ---------------------------------------------------

    _VALID_TXN_STATUSES = {"Imported", "Reviewed", "Posted"}

    def insert_transaction(
        self,
        batch_id: int,
        posted_date: Optional[str],
        description: str,
        amount: Optional[float],
        currency: str = "USD",
        source_row: Optional[int] = None,
        fingerprint: str = "",
        coa_account: Optional[str] = None,
        status: str = "Imported",
        is_duplicate: bool = False,
        parse_errors: Optional[str] = None,
    ) -> int:
        """Insert one bank transaction row and return its ``id``."""
        now = _now()
        cur = self._conn.execute(
            """
            INSERT INTO bank_transactions
                (batch_id, posted_date, description, amount, currency,
                 source_row, fingerprint, coa_account, status,
                 is_duplicate, parse_errors, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id,
                posted_date,
                description,
                amount,
                currency,
                source_row,
                fingerprint,
                coa_account,
                status,
                1 if is_duplicate else 0,
                parse_errors,
                now,
                now,
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_transaction(self, txn_id: int) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM bank_transactions WHERE id = ?", (txn_id,)
        ).fetchone()

    def list_transactions(
        self,
        batch_id: Optional[int] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        needs_review_only: bool = False,
    ) -> list:
        """
        Return bank transactions, optionally filtered.

        *needs_review_only* selects rows that are missing a COA account OR are
        flagged as duplicates.
        """
        clauses: list[str] = []
        params: list = []

        if batch_id is not None:
            clauses.append("batch_id = ?")
            params.append(batch_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if search:
            clauses.append("description LIKE ?")
            params.append(f"%{search}%")
        if needs_review_only:
            clauses.append("(coa_account IS NULL OR coa_account = '' OR is_duplicate = 1)")

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        return self._conn.execute(
            f"SELECT * FROM bank_transactions {where} ORDER BY posted_date ASC, id ASC",
            params,
        ).fetchall()

    def update_transaction(
        self,
        txn_id: int,
        posted_date: Optional[str] = None,
        description: Optional[str] = None,
        amount: Optional[float] = None,
        coa_account: Optional[str] = None,
        status: Optional[str] = None,
    ):
        """Patch one or more fields on a bank transaction row."""
        updates: list[str] = []
        params: list = []

        if posted_date is not None:
            updates.append("posted_date = ?")
            params.append(posted_date)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if amount is not None:
            updates.append("amount = ?")
            params.append(amount)
        if coa_account is not None:
            updates.append("coa_account = ?")
            params.append(coa_account)
        if status is not None:
            if status not in self._VALID_TXN_STATUSES:
                raise ValueError(f"Unknown transaction status: {status!r}")
            updates.append("status = ?")
            params.append(status)

        if not updates:
            return

        updates.append("updated_at = ?")
        params.append(_now())
        params.append(txn_id)

        self._conn.execute(
            f"UPDATE bank_transactions SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        self._conn.commit()

    def mark_transactions_reviewed(self, txn_ids: list[int]):
        """Bulk-set status = 'Reviewed' for the given transaction IDs."""
        if not txn_ids:
            return
        now = _now()
        placeholders = ",".join("?" * len(txn_ids))
        self._conn.execute(
            f"UPDATE bank_transactions SET status = 'Reviewed', updated_at = ? WHERE id IN ({placeholders})",
            [now, *txn_ids],
        )
        self._conn.commit()

    def fingerprint_exists(self, fingerprint: str, exclude_batch_id: Optional[int] = None) -> bool:
        """Return True if *fingerprint* already exists in bank_transactions."""
        if exclude_batch_id is not None:
            row = self._conn.execute(
                "SELECT 1 FROM bank_transactions WHERE fingerprint = ? AND batch_id != ? LIMIT 1",
                (fingerprint, exclude_batch_id),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT 1 FROM bank_transactions WHERE fingerprint = ? LIMIT 1",
                (fingerprint,),
            ).fetchone()
        return row is not None


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _file_hash(path: Path) -> str:
    """Return the SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _unique_path(directory: Path, filename: str) -> Path:
    """Return a path that does not already exist, appending _1, _2, … if needed."""
    dest = directory / filename
    if not dest.exists():
        return dest
    stem, suffix = Path(filename).stem, Path(filename).suffix
    n = 1
    while True:
        dest = directory / f"{stem}_{n}{suffix}"
        if not dest.exists():
            return dest
        n += 1


def _count_pages(path: str, mimetype: str) -> Optional[int]:
    """Return the page count for PDFs; 1 for images; None on error."""
    try:
        if mimetype == "application/pdf":
            from pypdf import PdfReader
            return len(PdfReader(path).pages)
        if mimetype.startswith("image/"):
            return 1
    except Exception:
        pass
    return None
