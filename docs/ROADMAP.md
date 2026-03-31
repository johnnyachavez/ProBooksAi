# ProBooksAi – Implementation Roadmap

> **Last updated:** 2026-03-31  
> This roadmap reflects the MVP-first, bank-centric build order for ProBooksAi.  
> Each phase maps to one or more focused pull requests.

---

## Guiding Principles

- **MVP slices first** – ship the smallest thing that is immediately useful before moving to the next phase.
- **Mergeable PRs** – every PR should stand alone and not block others. Aim for < 400 lines of change.
- **Avoid big-bang refactors** – extend existing tables and modules rather than rewriting them.
- **Bank data is the source of truth** – for small businesses, the bank statement is what actually happened; the GL is derived from it.
- **Sign convention** – money-out is always negative, money-in is always positive; never change this once data is in the DB.

---

## Current Status

| GitHub Object | Title | Status |
|---|---|---|
| [Issue #9](https://github.com/johnnyachavez/ProBooksAi/issues/9) | Intake PDF or photo of bank statements | Open |
| [Issue #11](https://github.com/johnnyachavez/ProBooksAi/issues/11) | Chase Bank Statement image (sample input) | Open |
| [Issue #12](https://github.com/johnnyachavez/ProBooksAi/issues/12) | Bank reconciliation per statement period + per-account setup | Open |
| [PR #10](https://github.com/johnnyachavez/ProBooksAi/pull/10) | CSV bank statement import – Phase 1 | Open |
| [PR #13](https://github.com/johnnyachavez/ProBooksAi/pull/13) | Per-account setup, statement periods, and reconciliation (Issue #12) | Open |
| [PR #14](https://github.com/johnnyachavez/ProBooksAi/pull/14) | Bank Account Register UI tab | Open |

---

## Phased Roadmap

### Phase 1 – Data Foundations ✅ (baseline)

Establish the core data model so every subsequent phase has a stable place to write.

- `chart_of_accounts` table (48 accounts, COA helpers in `probooksai/coa.py`)
- `bank_accounts` table – one row per real bank account with name, type, and currency
- `bank_transactions` table – signed amounts (negative = debit/out, positive = credit/in)
- `bank_import_batches` table – tracks each import session (file name, account, timestamps)

**Definition of done**
- All four tables created via `probooksai/database.py` on first launch.
- `python -m pytest tests/` passes.
- No UI required for this phase.

---

### Phase 2 – Import (CSV Mapping & Dedupe)

Reference: [PR #10](https://github.com/johnnyachavez/ProBooksAi/pull/10)

Allow users to bring in historical and ongoing bank transactions from a CSV export.

- **Column mapping dialog** – user maps CSV columns to `date`, `description`, `amount` (or debit/credit split).
- **Deduplification** – fingerprint each row (date + amount + description hash); skip exact duplicates.
- **Editable transactions table** – after import, user can correct category/COA and add memo.
- **Missing COA flag** – highlight rows that have no account mapping.

**Definition of done**
- User can import a CSV, map columns, and see transactions in the DB.
- Duplicate rows are skipped on re-import of the same file.
- Each import batch is tied to a specific Bank Account.

---

### Phase 3 – Register (Bank Register UI)

Reference: [PR #14](https://github.com/johnnyachavez/ProBooksAi/pull/14)

Give users a familiar check-register view for any bank account.

- **Register tab** next to "Bank Import" in the desktop app.
- **Columns:** Date | Number (ref/check #) | Payee / Description | Memo | Debit | Credit | Balance (running) | COA Account
- **Account selector** – filter the register to one bank account.
- **Footer totals** – Total Debits, Total Credits, Net.
- Inline edits for Memo, Number, and COA Account saved immediately to SQLite.

**Definition of done**
- Register tab visible and functional for any imported bank account.
- Running balance updates correctly when rows are filtered or sorted by date.
- Inline edits persist across app restarts.

---

### Phase 4 – Reconciliation (Statement Periods)

Reference: [Issue #12](https://github.com/johnnyachavez/ProBooksAi/issues/12), [PR #13](https://github.com/johnnyachavez/ProBooksAi/pull/13)

Tie each import batch to a formal statement period so the user can verify the bank's math.

- **Statement period dialog** – capture start date, end date (odd ranges allowed, e.g., Mar 1–Mar 29), beginning balance, and ending balance.
- **Per-account import profile** – save column mapping and date-format preference per bank account so re-imports are one click.
- **Reconciliation calculation** – `begin_balance + SUM(txns in range) = expected_end`; show the difference.
- **Mark Reconciled** – enabled only when `|difference| ≤ tolerance` (default 0.00).
- **Sign convention enforcement** – outflows stored negative; no interaction with invoicing sign.

**Definition of done**
- User can open a reconciliation panel, enter statement period, and see computed difference.
- "Mark Reconciled" button is disabled until difference is within tolerance.
- Reconciled batches shown with a ✓ badge in the import history list.

---

### Phase 5 – Posting to General Ledger

Move from bank-only view to full double-entry accounting.

- Each bank transaction gets a "Post to GL" action that creates a matching `Journal_Entry` pair.
- Debit/credit side auto-suggested from the COA mapping on the transaction.
- Prevents double-posting (posted flag on `bank_transactions`).

**Definition of done**
- Posting a bank transaction creates a balanced journal entry (debit = credit).
- Trial Balance reflects newly posted amounts.
- Already-posted transactions are visually locked.

---

### Phase 6 – Rules & AI Hints

Reduce manual work for repeat vendors and common categories.

- **Memorised rules** – if Description contains "AMAZON" → COA 5010 (Office Supplies), auto-applied on import.
- **AI category suggestions** – send description to cloud AI and return top-3 COA matches.
- **Vendor matching** – link payee string to Vendor master for 1099 and AP reporting.

**Definition of done**
- Rules engine applies saved rules during import (no UI interaction needed).
- AI suggestions shown as a dropdown in the COA column when no rule matches.
- Rules can be created, edited, and deleted from Settings.

---

### Phase 7 – PDF / OCR Intake

Reference: [Issue #9](https://github.com/johnnyachavez/ProBooksAi/issues/9), [Issue #11](https://github.com/johnnyachavez/ProBooksAi/issues/11) (Chase statement image as sample input)

Parse bank statements directly from PDF or photo uploads—no CSV export needed.

- Feed PDF/image through cloud AI (vision model) to extract transaction rows.
- Map extracted rows into the same `bank_transactions` table as CSV import.
- Human review step to correct OCR errors before committing.
- Use [Issue #11](https://github.com/johnnyachavez/ProBooksAi/issues/11) (Chase statement image) as the canonical acceptance test.

**Definition of done**
- User can drag-and-drop a bank statement PDF and see transactions pre-populated in the mapping dialog.
- OCR confidence score flagged on rows that need review.
- End-to-end test passing against the Chase statement image from Issue #11.

---

## Out of Scope (for now)

The following items are deliberately deferred to avoid scope creep:

| Feature | Reason deferred |
|---|---|
| Multi-currency | Complex FX logic; not needed for MVP |
| Payroll module | Separate compliance domain |
| Fixed-asset depreciation | Requires amortisation schedules |
| Google Apps Script version | Different runtime; separate project |
| Budget vs. Actual | Reporting layer; needs GL data first |
| PyInstaller packaging | Build tooling; can add after core is stable |
| PDF export of invoices | Nice-to-have; not blocking bank workflow |

---

*See [CONTRIBUTING.md](./CONTRIBUTING.md) for PR conventions and labeling guidelines.*
