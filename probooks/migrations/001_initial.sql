-- Foundation schema: migrations ledger, default company, bank accounts (issue #21, #27, #30).

CREATE TABLE IF NOT EXISTS schema_migrations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS companies (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO companies (name) VALUES ('Default');

CREATE TABLE IF NOT EXISTS bank_accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_id INTEGER NOT NULL DEFAULT 1 REFERENCES companies(id),
  name TEXT NOT NULL,
  institution TEXT,
  account_type TEXT CHECK (account_type IN ('checking', 'savings', 'credit', 'other')),
  last4 TEXT,
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_bank_accounts_company ON bank_accounts(company_id);
