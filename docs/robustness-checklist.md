# Project Robustness Checklist (Backend + US Accounting Engine)

This is a living “definition of done” for reliability, security, maintainability, and accounting correctness.

Tag items as:
- **MVP** = required before first usable backend release
- **Pre-Prod** = required before real customer data / production
- **Later** = explicitly deferred

---

## How to use this checklist (phased gates)

### Gate 0 — Design Gate (do BEFORE building a feature) (**MVP**)
- [ ] Data model reviewed for double-entry + audit trail requirements
- [ ] Reporting impact identified (which statements/accounts change?)
- [ ] Idempotency strategy defined for imports and integrations
- [ ] Period close/lock implications documented
- [ ] Security/permissions model defined for the feature
- [ ] “Delete vs reverse” policy defined (accounting systems typically reverse, not delete)

### Gate 1 — MVP Gate (before calling backend “usable”) (**MVP**)
- [ ] Double-entry enforcement is a hard constraint (no imbalanced posting)
- [ ] Journal is immutable once posted (corrections via adjusting entries)
- [ ] Audit trail exists for all financial-impacting changes
- [ ] Period open/close exists (minimal is fine)
- [ ] Balance Sheet + P&L generated from the ledger
- [ ] Export capability exists (CSV at minimum) for transactions and reports

### Gate 2 — Pre-Production Gate (before real customers / money) (**Pre-Prod**)
- [ ] Backups configured AND restore test completed
- [ ] Monitoring + alerting covers key failure modes
- [ ] Bank reconciliation workflow and controls in place (or explicitly out of scope)
- [ ] Performance validated at expected volumes
- [ ] Security review for authz, rate limits, and data exposure completed
- [ ] Incident runbooks exist for top outages (DB down, queue jam, integrations)

---

## 1) Core Accounting Framework (US, single currency)

### 1A. Accounting rules / standards
- [ ] GAAP-aligned policies documented for supported workflows (**MVP**)
- [ ] Double-entry system enforced (every posting balanced) (**MVP**)
- [ ] Accounting equation holds: **Assets = Liabilities + Equity** (**MVP**)
- [ ] Accrual basis supported for core statements (at least via journal entries) (**MVP**)
- [ ] Cash basis reporting either supported or explicitly out of scope for MVP (**MVP**)
- [ ] Revenue recognition approach documented (ASC 606 concepts) (**Later unless required**)
- [ ] Matching principle supported via accrual/adjusting entries (**MVP**)

### 1B. US tax & compliance logic (scope + guardrails)
- [ ] Tax handling scope documented (what is supported vs not) (**MVP**)
- [ ] Sales/use tax approach documented (even if deferred) (**MVP/Later**)
- [ ] Payroll taxes explicitly out of scope unless you’re implementing payroll (**MVP**)
- [ ] Depreciation/MACRS explicitly out of scope unless you’re implementing fixed assets (**MVP**)
- [ ] Audit trails + record retention policy documented and implemented (**MVP**)

**Record retention (US rule-of-thumb; confirm with your accountant/attorney):**
- [ ] 3 years: commonly cited general IRS retention guidance
- [ ] 6 years: commonly cited if substantial underreporting (>25% gross income)
- [ ] 7 years: commonly cited for certain loss-related claims (e.g., bad debt)
- [ ] 4 years: commonly cited minimum for employment tax records

### 1C. Industry-specific workflows (Trucking example — only if in scope)
- [ ] Load-based revenue tracking (**Later**)
- [ ] Fuel expense + IFTA reporting support (**Later**)
- [ ] Equipment depreciation tied to fixed assets (trucks/trailers) (**Later**)
- [ ] Maintenance logs tied to assets (**Later**)
- [ ] Driver payroll vs contractor payments supported (**Later**)
- [ ] Job costing per project/load (**Later**)

### 1D. Data integrity standards (financial-grade) (**MVP unless noted**)
- [ ] Immutable transaction/journal logs once posted
- [ ] Audit trail: who/when/what changed (and why, if captured)
- [ ] Referential integrity across: source docs → journal → ledger → reports
- [ ] Duplicate detection / idempotency keys for imports + integrations
- [ ] Period locking after close (no edits; only adjusting entries)
- [ ] Backups + recovery procedure documented (**Pre-Prod**)
- [ ] Restore test performed (**Pre-Prod**)

---

## 2) Accounting System Structure (Minimum Viable Accounting Engine)

### 2A. Chart of Accounts (COA)
Core categories supported (**MVP**):
- [ ] Assets (cash, A/R, equipment)
- [ ] Liabilities (A/P, loans)
- [ ] Equity (owner capital, retained earnings)
- [ ] Revenue
- [ ] Expenses

COA requirements:
- [ ] Hierarchical structure (parent/child accounts) (**MVP**)
- [ ] Account types and normal balance defined (debit/credit behavior) (**MVP**)
- [ ] Ability to deactivate accounts without breaking history (**MVP**)
- [ ] Account numbering system optional (**Later**)

### 2B. Double-entry rules (hard enforcement) (**MVP**)
- [ ] Each posting affects ≥ 2 accounts
- [ ] Total debits == total credits (hard constraint)
- [ ] Normal-balance behavior enforced:
  - [ ] Assets/Expenses increase with debit
  - [ ] Liabilities/Equity/Revenue increase with credit
- [ ] No posting if imbalance detected
- [ ] Posting is atomic (all-or-nothing transaction)

### 2C. Transaction flow architecture (**MVP**)
Flow:
- [ ] Source transaction (invoice/bill/payment/etc.)
- [ ] Journal entry creation (journal header + journal lines)
- [ ] Posting to general ledger
- [ ] Trial balance generated per period
- [ ] Financial statements output from ledger/trial balance

Key components:
- [ ] Journal (raw entries; append-only after posting)
- [ ] Ledger balances (derived query or materialized with reconciliation strategy)
- [ ] Sub-ledgers (A/R, A/P) either implemented or explicitly deferred

### 2D. Reporting logic
Core reports (**MVP**):
- [ ] Profit & Loss (Income Statement)
- [ ] Balance Sheet

Rules:
- [ ] Period-based reporting (monthly/quarterly/yearly) (**MVP**)
- [ ] Drill-down: report → account → journal lines → source transaction (**MVP**)
- [ ] Closing entries / retained earnings handling defined (**Later/MVP depending on scope**)
- [ ] Cash Flow statement (**Later**)

### 2E. Data validation rules (**MVP**)
- [ ] Required fields (date, amount, currency=USD, accounts, description/reference)
- [ ] Date must be in an open period
- [ ] Only valid accounts selectable (scoped to the company/ledger)
- [ ] Duplicate prevention for imports (idempotency key, file hash, external ID)
- [ ] Reconciliation checks (bank vs books) (**Pre-Prod if in scope**)

---

## 3) System-level requirements (critical backend)

### 3A. Multi-user controls + permissions
- [ ] Authentication implemented (**MVP**)
- [ ] Authorization (roles/permissions; least privilege) (**MVP**)
- [ ] Sensitive actions require elevated permission (period close, admin changes) (**Pre-Prod**)
- [ ] Admin actions audited (**MVP**)

### 3B. Import/export + integrations
- [ ] Import/export (CSV) (**MVP**)
- [ ] Integration interfaces designed to be replay-safe (idempotent) (**MVP**)
- [ ] Background jobs (if used) are retry-safe and idempotent (**MVP**)

### 3C. Performance & scalability
- [ ] Indexing strategy defined for large transaction volumes (**Pre-Prod**)
- [ ] Pagination on list endpoints (**MVP**)
- [ ] Reporting performance considered (pre-aggregation/materialization if needed) (**Pre-Prod**)

---

## 4) Engineering robustness (non-domain)

### 4A. Error handling & resilience (**MVP**)
- [ ] Centralized error handling (API + workers)
- [ ] Timeouts on outbound calls
- [ ] Retries with exponential backoff for transient failures
- [ ] No “partial write” failures (atomic transactions)

### 4B. Observability
- [ ] Structured logs (**MVP**)
- [ ] Correlation/request IDs (**MVP**)
- [ ] Metrics (latency, error rate, throughput) (**Pre-Prod**)
- [ ] Alerts for critical failures (**Pre-Prod**)

### 4C. Testing
- [ ] Unit tests for accounting invariants (balanced postings, period lock) (**MVP**)
- [ ] Integration tests for DB transaction behavior (**MVP**)
- [ ] Regression tests for report outputs (**MVP**)
- [ ] CI runs tests on every PR (**MVP**)

### 4D. Security
- [ ] Input validation for all endpoints (**MVP**)
- [ ] Secrets management (no secrets in repo; env/secret store) (**MVP**)
- [ ] Rate limiting / abuse prevention (**Pre-Prod**)
- [ ] Principle of least privilege enforced (**MVP**)

### 4E. Operations
- [ ] Backups configured (**Pre-Prod**)
- [ ] Restore procedure documented (**MVP**) and tested (**Pre-Prod**)
- [ ] Runbook for top incidents (**Pre-Prod**)
