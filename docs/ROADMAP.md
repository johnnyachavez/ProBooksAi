# ProBooksAi – Implementation Roadmap

> **Last updated:** 2026-04-01  
> This roadmap reflects the MVP-first, bank-centric build order for ProBooksAi.  
> Each phase maps to one or more focused pull requests.

---

## Issue Consolidation

The following duplicate issues have been superseded. Only the **canonical** issues listed in the roadmap below should be used for tracking work.

| Superseded (close) | Canonical (keep) | Feature |
|---|---|---|
| [#17](https://github.com/johnnyachavez/ProBooksAi/issues/17), [#20](https://github.com/johnnyachavez/ProBooksAi/issues/20) | [**#29**](https://github.com/johnnyachavez/ProBooksAi/issues/29) | Dark theme across the entire app |
| [#27](https://github.com/johnnyachavez/ProBooksAi/issues/27) | [**#21**](https://github.com/johnnyachavez/ProBooksAi/issues/21) | Single SQLite DB location + versioned migrations |
| [#22](https://github.com/johnnyachavez/ProBooksAi/issues/22) | [**#30**](https://github.com/johnnyachavez/ProBooksAi/issues/30) | Bank Accounts — CRUD + account types + UI management |
| [#32](https://github.com/johnnyachavez/ProBooksAi/issues/32) | [**#31**](https://github.com/johnnyachavez/ProBooksAi/issues/31) | Bank Import — per-account CSV import flow |
| [#23](https://github.com/johnnyachavez/ProBooksAi/issues/23) | [**#41**](https://github.com/johnnyachavez/ProBooksAi/issues/41) | Chart of Accounts (COA) editor |
| [#24](https://github.com/johnnyachavez/ProBooksAi/issues/24) | [**#40**](https://github.com/johnnyachavez/ProBooksAi/issues/40) | Posting engine — post bank transactions to GL |
| [#25](https://github.com/johnnyachavez/ProBooksAi/issues/25) | [**#45**](https://github.com/johnnyachavez/ProBooksAi/issues/45) | Attachments for bank transactions |
| [#26](https://github.com/johnnyachavez/ProBooksAi/issues/26) | [**#46**](https://github.com/johnnyachavez/ProBooksAi/issues/46) | Release packaging (Windows) + version display |
| [#48](https://github.com/johnnyachavez/ProBooksAi/issues/48) | [**#76**](https://github.com/johnnyachavez/ProBooksAi/issues/76) | Performance: large CSV imports (worker thread + progress) |
| [#49](https://github.com/johnnyachavez/ProBooksAi/issues/49) | [**#77**](https://github.com/johnnyachavez/ProBooksAi/issues/77) | Transaction splits (one bank txn → multiple categories) |
| [#50](https://github.com/johnnyachavez/ProBooksAi/issues/50) | [**#78**](https://github.com/johnnyachavez/ProBooksAi/issues/78) | Transfers (bank-to-bank moves) |
| [#51](https://github.com/johnnyachavez/ProBooksAi/issues/51) | [**#79**](https://github.com/johnnyachavez/ProBooksAi/issues/79) | Rule-based auto-categorization (no AI) |
| [#52](https://github.com/johnnyachavez/ProBooksAi/issues/52) | [**#80**](https://github.com/johnnyachavez/ProBooksAi/issues/80) | Receipt/document workflow improvements |
| [#53](https://github.com/johnnyachavez/ProBooksAi/issues/53) | [**#81**](https://github.com/johnnyachavez/ProBooksAi/issues/81) | Audit log of edits (change history) |
| [#54](https://github.com/johnnyachavez/ProBooksAi/issues/54) | [**#82**](https://github.com/johnnyachavez/ProBooksAi/issues/82) | Export tools (CSV export + reconciliation report) |
| [#55](https://github.com/johnnyachavez/ProBooksAi/issues/55) | [**#83**](https://github.com/johnnyachavez/ProBooksAi/issues/83) | Multi-company / multiple books support |
| [#56](https://github.com/johnnyachavez/ProBooksAi/issues/56) | [**#66**](https://github.com/johnnyachavez/ProBooksAi/issues/66) | Invoicing (MVP) — create invoice + line items + PDF export |
| [#57](https://github.com/johnnyachavez/ProBooksAi/issues/57) | [**#67**](https://github.com/johnnyachavez/ProBooksAi/issues/67) | Receive payments (AR) — apply payment to invoice(s) |
| [#58](https://github.com/johnnyachavez/ProBooksAi/issues/58) | [**#68**](https://github.com/johnnyachavez/ProBooksAi/issues/68) | AR aging report |
| [#59](https://github.com/johnnyachavez/ProBooksAi/issues/59) | [**#69**](https://github.com/johnnyachavez/ProBooksAi/issues/69) | Bills (AP MVP) — enter vendor bills + attachments |
| [#60](https://github.com/johnnyachavez/ProBooksAi/issues/60) | [**#70**](https://github.com/johnnyachavez/ProBooksAi/issues/70) | Pay bills (AP) — record payments + apply to bills |
| [#61](https://github.com/johnnyachavez/ProBooksAi/issues/61) | [**#71**](https://github.com/johnnyachavez/ProBooksAi/issues/71) | AP aging report |
| [#62](https://github.com/johnnyachavez/ProBooksAi/issues/62) | [**#72**](https://github.com/johnnyachavez/ProBooksAi/issues/72) | Sales tax settings + sales tax on invoices |
| [#63](https://github.com/johnnyachavez/ProBooksAi/issues/63) | [**#73**](https://github.com/johnnyachavez/ProBooksAi/issues/73) | Payroll (MVP) — employees + pay runs + payroll journal posting |
| [#64](https://github.com/johnnyachavez/ProBooksAi/issues/64) | [**#74**](https://github.com/johnnyachavez/ProBooksAi/issues/74) | Payroll taxes (placeholder framework) |
| [#65](https://github.com/johnnyachavez/ProBooksAi/issues/65) | [**#75**](https://github.com/johnnyachavez/ProBooksAi/issues/75) | Bank matching (link bank txns to invoices/bills/payroll) |

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

### Phase 5 – Foundations: Dark Theme + DB Migrations + Bank Accounts

Reference: [Issue #29](https://github.com/johnnyachavez/ProBooksAi/issues/29), [Issue #21](https://github.com/johnnyachavez/ProBooksAi/issues/21), [Issue #30](https://github.com/johnnyachavez/ProBooksAi/issues/30)

Infrastructure improvements before expanding features.

- **Dark theme** ([#29](https://github.com/johnnyachavez/ProBooksAi/issues/29)) – global dark palette applied to all screens; theme constants in `desktop_app/theme.py`.
- **Schema versioning** ([#21](https://github.com/johnnyachavez/ProBooksAi/issues/21)) – `schema_version` table + migration runner; existing installs migrate safely.
- **Bank accounts CRUD** ([#30](https://github.com/johnnyachavez/ProBooksAi/issues/30)) – extend `bank_accounts` with `institution`, `last4`, `notes`, `is_active`, `updated_at`; update Manage Accounts dialog.

**Definition of done**
- No bright/white panels; all text readable with good contrast.
- Schema version increments safely on upgrade; new installs start clean.
- User can add/edit/archive bank accounts with all fields.

---

### Phase 6 – COA Editor + Posting to General Ledger

Reference: [Issue #41](https://github.com/johnnyachavez/ProBooksAi/issues/41), [Issue #40](https://github.com/johnnyachavez/ProBooksAi/issues/40)

Move from bank-only view to full double-entry accounting.

- **COA editor** ([#41](https://github.com/johnnyachavez/ProBooksAi/issues/41)) – UI tab to view/add/edit COA accounts (name, type, parent, is_active); stored in SQLite; populates category dropdowns.
- **Posting engine** ([#40](https://github.com/johnnyachavez/ProBooksAi/issues/40)) – `journal_entries` + `journal_entry_lines` tables; post bank transactions to balanced GL entries; prevent double-posting.

**Definition of done**
- User can edit COA and immediately see changes in category dropdowns.
- Posting a bank transaction creates a balanced journal entry (debit = credit).
- Already-posted transactions are visually locked.

---

### Phase 7 – Attachments + Import Performance

Reference: [Issue #45](https://github.com/johnnyachavez/ProBooksAi/issues/45), [Issue #76](https://github.com/johnnyachavez/ProBooksAi/issues/76)

- **Attachments** ([#45](https://github.com/johnnyachavez/ProBooksAi/issues/45)) – attach receipts/invoices to bank transactions; store in app data directory; `transaction_attachments` DB table.
- **Large CSV performance** ([#76](https://github.com/johnnyachavez/ProBooksAi/issues/76)) – move CSV parsing + DB writes off UI thread; progress bar; cancel support; chunked inserts.

**Definition of done**
- Attachments persist and open after app restart.
- Large imports keep UI responsive with visible progress.

---

### Phase 8 – Transaction Enhancements

Reference: [Issue #77](https://github.com/johnnyachavez/ProBooksAi/issues/77), [Issue #78](https://github.com/johnnyachavez/ProBooksAi/issues/78), [Issue #79](https://github.com/johnnyachavez/ProBooksAi/issues/79), [Issue #80](https://github.com/johnnyachavez/ProBooksAi/issues/80)

- **Transaction splits** ([#77](https://github.com/johnnyachavez/ProBooksAi/issues/77)) – split one bank transaction into multiple categories; posting reflects splits.
- **Transfers** ([#78](https://github.com/johnnyachavez/ProBooksAi/issues/78)) – mark transactions as bank-to-bank transfers; GL posts correctly without hitting income/expense.
- **Auto-categorization rules** ([#79](https://github.com/johnnyachavez/ProBooksAi/issues/79)) – rule engine (contains/starts-with/exact); auto-assigns COA on import; user overrides persist.
- **Receipt workflow** ([#80](https://github.com/johnnyachavez/ProBooksAi/issues/80)) – "needs receipt" flag; register filter for missing receipts; attachment indicator per row.

**Definition of done**
- Splits post balanced GL entries.
- Transfer transactions affect only two bank GL accounts.
- Rules auto-assign at import; user can override.

---

### Phase 9 – Audit Log + Export Tools

Reference: [Issue #81](https://github.com/johnnyachavez/ProBooksAi/issues/81), [Issue #82](https://github.com/johnnyachavez/ProBooksAi/issues/82)

- **Audit log** ([#81](https://github.com/johnnyachavez/ProBooksAi/issues/81)) – record change history for transactions, batches, GL, COA; `entity_type/entity_id/field/old/new/changed_at`; "View history" dialog.
- **Export tools** ([#82](https://github.com/johnnyachavez/ProBooksAi/issues/82)) – CSV export of register view (respects filters); reconciliation report per batch.

**Definition of done**
- User can view full change history for any transaction.
- Exported CSV matches on-screen data.

---

### Phase 10 – Invoicing + AR

Reference: [Issue #66](https://github.com/johnnyachavez/ProBooksAi/issues/66), [Issue #67](https://github.com/johnnyachavez/ProBooksAi/issues/67), [Issue #68](https://github.com/johnnyachavez/ProBooksAi/issues/68), [Issue #72](https://github.com/johnnyachavez/ProBooksAi/issues/72)

- **Invoicing MVP** ([#66](https://github.com/johnnyachavez/ProBooksAi/issues/66)) – customers, invoices with line items, subtotal/tax/total, PDF export.
- **Receive payments** ([#67](https://github.com/johnnyachavez/ProBooksAi/issues/67)) – apply payment to invoice(s); update balance_due and status.
- **AR aging** ([#68](https://github.com/johnnyachavez/ProBooksAi/issues/68)) – aging buckets by due date; group by customer; CSV export.
- **Sales tax** ([#72](https://github.com/johnnyachavez/ProBooksAi/issues/72)) – configurable tax rate; per-invoice tax computation; sales tax summary report.

**Definition of done**
- User can create invoices, record payments, and see AR aging.
- Invoice totals and tax calculations are correct.

---

### Phase 11 – Bills + AP

Reference: [Issue #69](https://github.com/johnnyachavez/ProBooksAi/issues/69), [Issue #70](https://github.com/johnnyachavez/ProBooksAi/issues/70), [Issue #71](https://github.com/johnnyachavez/ProBooksAi/issues/71)

- **Bills MVP** ([#69](https://github.com/johnnyachavez/ProBooksAi/issues/69)) – vendors, bills with line items or total, attachments, stored in SQLite.
- **Pay bills** ([#70](https://github.com/johnnyachavez/ProBooksAi/issues/70)) – record payments against bills; partial/full pay; bank account selection.
- **AP aging** ([#71](https://github.com/johnnyachavez/ProBooksAi/issues/71)) – aging buckets by due date; group by vendor; CSV export.

**Definition of done**
- User can enter bills, record payments, and see AP aging.
- Bill balances and statuses update correctly.

---

### Phase 12 – Payroll + Bank Matching

Reference: [Issue #73](https://github.com/johnnyachavez/ProBooksAi/issues/73), [Issue #74](https://github.com/johnnyachavez/ProBooksAi/issues/74), [Issue #75](https://github.com/johnnyachavez/ProBooksAi/issues/75)

- **Payroll MVP** ([#73](https://github.com/johnnyachavez/ProBooksAi/issues/73)) – employees, pay runs, net pay computation, GL journal posting.
- **Payroll taxes** ([#74](https://github.com/johnnyachavez/ProBooksAi/issues/74)) – configurable tax items; employer/employee portions; totals per pay run.
- **Bank matching** ([#75](https://github.com/johnnyachavez/ProBooksAi/issues/75)) – link bank transactions to invoice/bill/payroll payments; match suggestions by amount/date.

**Definition of done**
- Pay run creates balanced GL entry.
- Bank transaction can be matched to a recorded payment.

---

### Phase 13 – Release Packaging + Multi-Company

Reference: [Issue #46](https://github.com/johnnyachavez/ProBooksAi/issues/46), [Issue #83](https://github.com/johnnyachavez/ProBooksAi/issues/83)

- **Windows packaging** ([#46](https://github.com/johnnyachavez/ProBooksAi/issues/46)) – PyInstaller build script; version display in About dialog; documented build steps.
- **Multi-company** ([#83](https://github.com/johnnyachavez/ProBooksAi/issues/83)) – File → New/Open Company; separate DBs per company; no data leakage.

**Definition of done**
- Build produces a runnable `.exe` with version shown.
- Switching companies fully switches data context.

---

### Phase 14 – PDF / OCR Intake

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

### Phase 6b – Rules & AI Hints

Reduce manual work for repeat vendors and common categories.

- **Memorised rules** – if Description contains "AMAZON" → COA 5010 (Office Supplies), auto-applied on import.
- **AI category suggestions** – send description to cloud AI and return top-3 COA matches.
- **Vendor matching** – link payee string to Vendor master for 1099 and AP reporting.

**Definition of done**
- Rules engine applies saved rules during import (no UI interaction needed).
- AI suggestions shown as a dropdown in the COA column when no rule matches.
- Rules can be created, edited, and deleted from Settings.

---

## Out of Scope (for now)

The following items are deliberately deferred to avoid scope creep:

| Feature | Reason deferred |
|---|---|
| Multi-currency | Complex FX logic; not needed for MVP |
| Fixed-asset depreciation | Requires amortisation schedules |
| Google Apps Script version | Different runtime; separate project |
| Budget vs. Actual | Reporting layer; needs GL data first |

---

*See [CONTRIBUTING.md](./CONTRIBUTING.md) for PR conventions and labeling guidelines.*
