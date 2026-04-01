-- CSV import batches + bank transactions (issues #31, #34; validation hooks for #33).

CREATE TABLE IF NOT EXISTS import_batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bank_account_id INTEGER NOT NULL REFERENCES bank_accounts(id),
  source_filename TEXT NOT NULL,
  imported_at TEXT NOT NULL DEFAULT (datetime('now')),
  rows_imported INTEGER NOT NULL DEFAULT 0,
  rows_skipped INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bank_transactions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bank_account_id INTEGER NOT NULL REFERENCES bank_accounts(id),
  import_batch_id INTEGER REFERENCES import_batches(id),
  txn_date TEXT NOT NULL,
  amount REAL NOT NULL,
  payee TEXT,
  memo TEXT,
  reference_number TEXT,
  raw_description TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_bt_account_date ON bank_transactions(bank_account_id, txn_date);
CREATE INDEX IF NOT EXISTS idx_bt_batch ON bank_transactions(import_batch_id);
