"""
probooksai.database
===================
SQLite-backed local storage for ProBooks+ai document intake.

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
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from probooks.paths import INTAKE_DB_NAME, app_data_dir, ensure_app_dirs


# ---------------------------------------------------------------------------
# Application data directory (Windows-friendly)
# ---------------------------------------------------------------------------

def _legacy_data_dir() -> Path:
    """Former default directory (``APPDATA/ProBooksAi`` on Windows, ``~/ProBooksAi`` otherwise)."""
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home()
    return base / "ProBooksAi"


def get_data_dir() -> Path:
    """Return (and create) the per-user data directory for intake + desktop default DB.

    Uses :func:`probooks.paths.app_data_dir` (same branded folder as the ``probooks`` CLI).
    If the intake DB (``INTAKE_DB_NAME`` / ``probooksai.db``) exists only under the
    legacy ``ProBooksAi`` folder, it is copied here once (along with ``documents/``
    when present).
    """
    ensure_app_dirs()
    dest = app_data_dir()
    dest.mkdir(parents=True, exist_ok=True)

    dest_db = dest / INTAKE_DB_NAME
    legacy_root = _legacy_data_dir()
    legacy_db = legacy_root / INTAKE_DB_NAME

    if not dest_db.is_file() and legacy_db.is_file():
        shutil.copy2(legacy_db, dest_db)
        legacy_docs = legacy_root / "documents"
        dest_docs = dest / "documents"
        if legacy_docs.is_dir() and not dest_docs.exists():
            shutil.copytree(legacy_docs, dest_docs)

    return dest


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
        db_path = str(get_data_dir() / INTAKE_DB_NAME)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    conn.commit()
    return conn


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

        If *store* is True the file is copied into the per-user ``ProBooksAi``
        data folder; otherwise the original path is recorded as-is.

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
