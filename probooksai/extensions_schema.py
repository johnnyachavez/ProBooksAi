"""
probooksai.extensions_schema
============================
Additional SQLite tables for roadmap phases 6+ (rules, AR/AP, payroll, splits,
matching, company settings). Applied to the same DB file as bank + documents.

Call :func:`apply_extensions` once after :class:`~probooksai.bank_import.BankDatabase`
initializes the connection.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

EXTENSION_SCHEMA_VERSION = 9

_DDL_VERSION = """
CREATE TABLE IF NOT EXISTS extension_schema_version (
    id      INTEGER PRIMARY KEY CHECK (id = 1),
    version INTEGER NOT NULL DEFAULT 0
);
"""

# v1 – rules, audit, AR/AP, payroll, splits, matching, settings
_DDL_V1 = """
CREATE TABLE IF NOT EXISTS categorization_rules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern     TEXT    NOT NULL,
    coa_account TEXT    NOT NULL,
    priority    INTEGER NOT NULL DEFAULT 0,
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type  TEXT    NOT NULL,
    entity_id    INTEGER NOT NULL,
    field        TEXT    NOT NULL,
    old_value    TEXT,
    new_value    TEXT,
    changed_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    email      TEXT,
    phone      TEXT,
    address    TEXT,
    notes      TEXT,
    created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS invoices (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id    INTEGER NOT NULL REFERENCES customers(id),
    invoice_number TEXT    NOT NULL UNIQUE,
    invoice_date   TEXT    NOT NULL,
    due_date       TEXT,
    memo           TEXT,
    subtotal       REAL    NOT NULL DEFAULT 0,
    tax_total      REAL    NOT NULL DEFAULT 0,
    total          REAL    NOT NULL DEFAULT 0,
    balance_due    REAL    NOT NULL DEFAULT 0,
    status         TEXT    NOT NULL DEFAULT 'Unpaid',
    created_at     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS invoice_lines (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id  INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    description TEXT,
    qty         REAL    NOT NULL DEFAULT 1,
    rate        REAL    NOT NULL DEFAULT 0,
    line_total  REAL    NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ar_payments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id  INTEGER NOT NULL REFERENCES customers(id),
    payment_date TEXT    NOT NULL,
    amount       REAL    NOT NULL,
    method       TEXT,
    reference    TEXT,
    memo         TEXT,
    created_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS ar_payment_allocations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id INTEGER NOT NULL REFERENCES ar_payments(id) ON DELETE CASCADE,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    amount     REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS vendors (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    email      TEXT,
    phone      TEXT,
    address    TEXT,
    notes      TEXT,
    is_1099    INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS bills (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor_id             INTEGER NOT NULL REFERENCES vendors(id),
    vendor_invoice_number TEXT,
    bill_date             TEXT    NOT NULL,
    due_date              TEXT,
    memo                  TEXT,
    total                 REAL    NOT NULL DEFAULT 0,
    balance_due           REAL    NOT NULL DEFAULT 0,
    status                TEXT    NOT NULL DEFAULT 'Unpaid',
    attachment_path       TEXT,
    created_at            TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS ap_payments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor_id       INTEGER NOT NULL REFERENCES vendors(id),
    payment_date    TEXT    NOT NULL,
    amount          REAL    NOT NULL,
    method          TEXT,
    reference       TEXT,
    memo            TEXT,
    bank_account_id INTEGER REFERENCES bank_accounts(id),
    created_at      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS ap_payment_allocations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id INTEGER NOT NULL REFERENCES ap_payments(id) ON DELETE CASCADE,
    bill_id    INTEGER NOT NULL REFERENCES bills(id),
    amount     REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS employees (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    address    TEXT,
    pay_type   TEXT    NOT NULL DEFAULT 'salary',
    rate       REAL    NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS payroll_runs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id       INTEGER NOT NULL REFERENCES employees(id),
    period_start      TEXT    NOT NULL,
    period_end        TEXT    NOT NULL,
    pay_date          TEXT    NOT NULL,
    gross             REAL    NOT NULL DEFAULT 0,
    deductions        REAL    NOT NULL DEFAULT 0,
    net_pay           REAL    NOT NULL DEFAULT 0,
    journal_entry_id  INTEGER,
    created_at        TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS company_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bank_txn_splits (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_txn_id INTEGER NOT NULL REFERENCES bank_transactions(id) ON DELETE CASCADE,
    amount        REAL    NOT NULL,
    coa_account   TEXT    NOT NULL,
    memo          TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS bank_match_links (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_transaction_id INTEGER NOT NULL REFERENCES bank_transactions(id) ON DELETE CASCADE,
    link_type           TEXT    NOT NULL,
    link_id             INTEGER NOT NULL,
    created_at          TEXT    NOT NULL,
    UNIQUE (bank_transaction_id)
);
"""

# v2 – Phase 16 payroll tax placeholders (manual amounts per run)
_MIGRATION_V2 = """
CREATE TABLE IF NOT EXISTS payroll_tax_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT    NOT NULL UNIQUE,
    name          TEXT    NOT NULL,
    jurisdiction  TEXT    NOT NULL DEFAULT '',
    is_active     INTEGER NOT NULL DEFAULT 1,
    sort_order    INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS payroll_run_tax_lines (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    payroll_run_id    INTEGER NOT NULL REFERENCES payroll_runs(id) ON DELETE CASCADE,
    tax_item_id       INTEGER NOT NULL REFERENCES payroll_tax_items(id),
    employee_amount   REAL    NOT NULL DEFAULT 0,
    employer_amount   REAL    NOT NULL DEFAULT 0,
    notes             TEXT    NOT NULL DEFAULT '',
    UNIQUE (payroll_run_id, tax_item_id)
);
"""

# v3 – AR payment deposit bank (parity with ap_payments.bank_account_id)
_MIGRATION_V3 = """
ALTER TABLE ar_payments ADD COLUMN bank_account_id INTEGER REFERENCES bank_accounts(id);
"""

# v4 – Enter Bills expense grid (A/P line detail)
_MIGRATION_V4 = """
CREATE TABLE IF NOT EXISTS bill_expense_lines (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id        INTEGER NOT NULL REFERENCES bills(id) ON DELETE CASCADE,
    line_date      TEXT,
    ticket_ref     TEXT,
    amount         REAL    NOT NULL DEFAULT 0,
    memo           TEXT,
    customer_job   TEXT,
    sort_order     INTEGER NOT NULL DEFAULT 0
);
"""

# v5 – Customer / job hierarchy (job rows point to a root “mother ship” customer)
_MIGRATION_V5 = """
ALTER TABLE customers ADD COLUMN parent_customer_id INTEGER REFERENCES customers(id);
"""

# v6 – Invoice item / service codes (master list for Manual Invoice line Code column)
_MIGRATION_V6 = """
CREATE TABLE IF NOT EXISTS invoice_item_codes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    code           TEXT    NOT NULL COLLATE NOCASE,
    description    TEXT    NOT NULL DEFAULT '',
    item_type      TEXT    NOT NULL DEFAULT 'Service',
    coa_account    TEXT    NOT NULL DEFAULT '',
    rate_value     REAL    NOT NULL DEFAULT 0,
    rate_kind      TEXT    NOT NULL DEFAULT 'amount',
    sort_order     INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT    NOT NULL,
    UNIQUE (code)
);
"""

# v7 – Bank Statement Intake review queue (Phase 2; persisted across sessions).
# Mirrors :class:`probooksai.bank_statement_intake.BankStatementIntakeRow` so
# the review panel can hydrate after restart. This queue is staging only —
# rows here have NOT been posted to bank_transactions; the panel's explicit
# "Send to Bank Register" hand-off is what posts to the register.
_MIGRATION_V7 = """
CREATE TABLE IF NOT EXISTS bank_statement_intake_queue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT    NOT NULL,
    txn_date        TEXT    NOT NULL DEFAULT '',
    description_raw TEXT    NOT NULL DEFAULT '',
    debit           REAL,
    credit          REAL,
    amount_signed   REAL,
    running_balance REAL,
    source_type     TEXT    NOT NULL DEFAULT '',
    source_ref      TEXT    NOT NULL DEFAULT '',
    confidence      REAL    NOT NULL DEFAULT 0,
    needs_review    INTEGER NOT NULL DEFAULT 1,
    sort_order      INTEGER NOT NULL DEFAULT 0
);
"""

# v8 — Phase 3 step 2: persist the COA suggestion / chosen category
# alongside each staged review row so it survives panel reload and is
# carried into ``bank_transactions`` by the Phase-2 hand-off.
_MIGRATION_V8 = """
ALTER TABLE bank_statement_intake_queue
ADD COLUMN coa_account TEXT NOT NULL DEFAULT '';
"""

# v9 — Create Invoices header: Ship To snapshot + payment terms (QB Pro).
# ``due_date`` already exists on ``invoices``; terms drive it in the desktop form.
_MIGRATION_V9 = """
ALTER TABLE invoices ADD COLUMN ship_to TEXT NOT NULL DEFAULT '';
ALTER TABLE invoices ADD COLUMN terms TEXT NOT NULL DEFAULT '';
"""


def _seed_payroll_tax_items(conn: sqlite3.Connection) -> None:
    """Default federal/state placeholder codes (amounts entered manually per run)."""
    now = datetime.now(timezone.utc).isoformat()
    items = [
        ("FED_WH", "Federal income tax withheld", "Federal", 10),
        ("FICA_EE", "Social Security — employee", "Federal", 20),
        ("FICA_ER", "Social Security — employer", "Federal", 30),
        ("MED_EE", "Medicare — employee", "Federal", 40),
        ("MED_ER", "Medicare — employer", "Federal", 50),
        ("STATE_WH", "State income tax withheld", "State", 60),
    ]
    for code, name, jur, so in items:
        conn.execute(
            """
            INSERT OR IGNORE INTO payroll_tax_items
                (code, name, jurisdiction, sort_order, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (code, name, jur, so, now),
        )


def apply_extensions(conn: sqlite3.Connection) -> None:
    """Create extension tables; bump extension_schema_version to EXTENSION_SCHEMA_VERSION."""
    conn.executescript(_DDL_VERSION)
    conn.commit()
    row = conn.execute(
        "SELECT version FROM extension_schema_version WHERE id = 1"
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO extension_schema_version (id, version) VALUES (1, 0)"
        )
        conn.commit()
        current = 0
    else:
        current = row["version"]

    if current >= EXTENSION_SCHEMA_VERSION:
        return

    if current < 1:
        for stmt in _DDL_V1.strip().split(";"):
            s = stmt.strip()
            if s:
                conn.execute(s)
        current = 1

    if current < 2:
        for stmt in _MIGRATION_V2.strip().split(";"):
            s = stmt.strip()
            if s:
                conn.execute(s)
        _seed_payroll_tax_items(conn)
        current = 2

    if current < 3:
        for stmt in _MIGRATION_V3.strip().split(";"):
            s = stmt.strip()
            if s:
                conn.execute(s)
        current = 3

    if current < 4:
        for stmt in _MIGRATION_V4.strip().split(";"):
            s = stmt.strip()
            if s:
                conn.execute(s)
        current = 4

    if current < 5:
        for stmt in _MIGRATION_V5.strip().split(";"):
            s = stmt.strip()
            if s:
                conn.execute(s)
        current = 5

    if current < 6:
        for stmt in _MIGRATION_V6.strip().split(";"):
            s = stmt.strip()
            if s:
                conn.execute(s)
        current = 6

    if current < 7:
        for stmt in _MIGRATION_V7.strip().split(";"):
            s = stmt.strip()
            if s:
                conn.execute(s)
        current = 7

    if current < 8:
        for stmt in _MIGRATION_V8.strip().split(";"):
            s = stmt.strip()
            if s:
                conn.execute(s)
        current = 8

    if current < 9:
        for stmt in _MIGRATION_V9.strip().split(";"):
            s = stmt.strip()
            if s:
                conn.execute(s)
        current = 9

    conn.execute(
        "UPDATE extension_schema_version SET version = ? WHERE id = 1",
        (EXTENSION_SCHEMA_VERSION,),
    )
    conn.commit()
