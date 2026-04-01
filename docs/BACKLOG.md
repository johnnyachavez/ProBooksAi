# ProBooks+ai — GitHub issue backlog (ordered)

Repository: [johnnyachavez/ProBooksAi](https://github.com/johnnyachavez/ProBooksAi)

This file orders **open** work so implementation can proceed top-to-bottom. “Completed” for housekeeping means **triaged, deduplicated, and sequenced**; most items are multi-week epics, not single commits.

## Principles

1. **Foundations before features** — SQLite location, migrations, backup/restore, then banking core, then AR/AP, then payroll, then polish.
2. **One canonical issue per topic** — duplicate GitHub issues are closed in favor of the earliest tracked number (or the clearest description); see [Duplicate matrix](#duplicate-matrix).
3. **Desktop app vs static shell** — Issues assume a **Python/desktop + SQLite** product. The current static `index.html` / `invoice.html` shell only satisfies a thin slice of UI shell / dark theme experiments.

---

## Phase 0 — Product intake & UX guardrails

| Priority | Issue | Notes |
|----------|-------|------|
| P0 | [#17](https://github.com/johnnyachavez/ProBooksAi/issues/17) | Base color / dark look (partially aligned with current web shell) |
| P0 | [#20](https://github.com/johnnyachavez/ProBooksAi/issues/20) | Dark theme + global styling (app shell) |
| P0 | [#29](https://github.com/johnnyachavez/ProBooksAi/issues/29) | Dark theme across entire app (tables, dialogs) |

## Phase 1 — Data storage & safety

| Priority | Issue | Notes |
|----------|-------|------|
| P1 | [#21](https://github.com/johnnyachavez/ProBooksAi/issues/21) | Single SQLite DB + versioned migrations |
| P1 | [#27](https://github.com/johnnyachavez/ProBooksAi/issues/27) | Schema versioning + safe migrations (detailed) |
| P1 | [#28](https://github.com/johnnyachavez/ProBooksAi/issues/28) | Backup / restore DB from UI |

## Phase 2 — Banking: accounts, import, register, reconciliation

| Priority | Issue | Notes |
|----------|-------|------|
| P2 | [#22](https://github.com/johnnyachavez/ProBooksAi/issues/22) | Bank account management (meta-epic in body) |
| P2 | [#30](https://github.com/johnnyachavez/ProBooksAi/issues/30) | Bank Accounts CRUD |
| P2 | [#31](https://github.com/johnnyachavez/ProBooksAi/issues/31) | CSV import flow (keep **one** of #31/#32 — duplicate titles) |
| P2 | [#33](https://github.com/johnnyachavez/ProBooksAi/issues/33) | Import validation + error export |
| P2 | [#34](https://github.com/johnnyachavez/ProBooksAi/issues/34) | Transaction model (payee, memo, ref, categories) |
| P2 | [#35](https://github.com/johnnyachavez/ProBooksAi/issues/35) | Duplicate detection workflow |
| P2 | [#36](https://github.com/johnnyachavez/ProBooksAi/issues/36) | Register running balance + footer totals |
| P2 | [#37](https://github.com/johnnyachavez/ProBooksAi/issues/37) | Statement period per batch |
| P2 | [#38](https://github.com/johnnyachavez/ProBooksAi/issues/38) | Reconciliation panel (expected ending, difference) |
| P2 | [#39](https://github.com/johnnyachavez/ProBooksAi/issues/39) | Mark reconciled gating + persistence |
| P2 | [#45](https://github.com/johnnyachavez/ProBooksAi/issues/45) | Attachments for bank transactions |
| P2 | [#48](https://github.com/johnnyachavez/ProBooksAi/issues/48) | Large CSV performance (worker + progress) |
| P2 | [#52](https://github.com/johnnyachavez/ProBooksAi/issues/52) | Bank txn matching to documents / receipts |
| P2 | [#53](https://github.com/johnnyachavez/ProBooksAi/issues/53) | Audit log (who/when/what) |
| P2 | [#54](https://github.com/johnnyachavez/ProBooksAi/issues/54) | Export tools (CSV / reconciliation batches) |
| P2 | [#55](https://github.com/johnnyachavez/ProBooksAi/issues/55) | Multi-company / multiple books (optional, late) |

## Phase 3 — COA, GL, posting

| Priority | Issue | Notes |
|----------|-------|------|
| P3 | [#23](https://github.com/johnnyachavez/ProBooksAi/issues/23) | COA editor UI |
| P3 | [#41](https://github.com/johnnyachavez/ProBooksAi/issues/41) | COA editor (minimal) — merge planning with #23 |
| P3 | [#42](https://github.com/johnnyachavez/ProBooksAi/issues/42) | Bank ↔ GL mapping |
| P3 | [#40](https://github.com/johnnyachavez/ProBooksAi/issues/40) | Posting engine MVP |
| P3 | [#24](https://github.com/johnnyachavez/ProBooksAi/issues/24) | Post bank txns to GL (meta) |
| P3 | [#43](https://github.com/johnnyachavez/ProBooksAi/issues/43) | GL register / JE drill-down |
| P3 | [#44](https://github.com/johnnyachavez/ProBooksAi/issues/44) | Reports: TB, P&L, BS |

## Phase 4 — AR / AP / invoicing

| Priority | Issue | Notes |
|----------|-------|------|
| P4 | [#56](https://github.com/johnnyachavez/ProBooksAi/issues/56) | Invoicing MVP + PDF |
| P4 | [#57](https://github.com/johnnyachavez/ProBooksAi/issues/57) | Receive payments (AR) — fix title typo in #67 on GitHub |
| P4 | [#58](https://github.com/johnnyachavez/ProBooksAi/issues/58) | AR aging |
| P4 | [#59](https://github.com/johnnyachavez/ProBooksAi/issues/59) | Bills (AP MVP) |
| P4 | [#60](https://github.com/johnnyachavez/ProBooksAi/issues/60) | Pay bills (AP) |
| P4 | [#61](https://github.com/johnnyachavez/ProBooksAi/issues/61) | AP aging |
| P4 | [#62](https://github.com/johnnyachavez/ProBooksAi/issues/62) | Sales tax on invoices |
| P4 | [#65](https://github.com/johnnyachavez/ProBooksAi/issues/65) | Bank matching to invoice/bill/payroll |

## Phase 5 — Payroll & taxes

| Priority | Issue | Notes |
|----------|-------|------|
| P5 | [#63](https://github.com/johnnyachavez/ProBooksAi/issues/63) | Payroll MVP |
| P5 | [#64](https://github.com/johnnyachavez/ProBooksAi/issues/64) | Payroll taxes framework |

## Phase 6 — Rules, splits, transfers, polish

| Priority | Issue | Notes |
|----------|-------|------|
| P6 | [#49](https://github.com/johnnyachavez/ProBooksAi/issues/49) | Transaction splits |
| P6 | [#50](https://github.com/johnnyachavez/ProBooksAi/issues/50) | Bank-to-bank transfers |
| P6 | [#51](https://github.com/johnnyachavez/ProBooksAi/issues/51) | Rule-based auto-categorization |
| P6 | [#80](https://github.com/johnnyachavez/ProBooksAi/issues/80) | Receipt/document workflow |

## Phase 7 — CI, packaging, optional AI

| Priority | Issue | Notes |
|----------|-------|------|
| P7 | [#47](https://github.com/johnnyachavez/ProBooksAi/issues/47) | CI tests for banking + posting |
| P7 | [#26](https://github.com/johnnyachavez/ProBooksAi/issues/26) | Windows packaging + version |
| P7 | [#46](https://github.com/johnnyachavez/ProBooksAi/issues/46) | Release packaging (dup of #26 — consolidate) |
| P7 | [#25](https://github.com/johnnyachavez/ProBooksAi/issues/25) | Document attachments + optional AI extraction |

## Intake / migration (parallel or later)

| Issue | Notes |
|-------|------|
| [#9](https://github.com/johnnyachavez/ProBooksAi/issues/9) | Historical banking intake routes |
| [#11](https://github.com/johnnyachavez/ProBooksAi/issues/11) | Reference image — convert to requirements or close |

---

## Duplicate matrix

Batch **2026-04-01** duplicates (same titles): **#66–#75** track the same work as **#56–#65**. Keep **#56–#65**; **#66–#75** should be closed as duplicates.

Similarly **#76–#79**, **#81–#83** overlap **#48–#51**, **#53–#55** (same epic titles). **#80** is related but not identical to **#52**.

**#31** vs **#32** — duplicate title; keep **#31**, close **#32**.

**#26** vs **#46** — both packaging; merge under one issue.

---

## “Completed” definition for this pass

- [x] Full open issue list fetched from GitHub  
- [x] Phased ordering documented here  
- [x] Duplicate issues identified  
- [x] Duplicates closed on GitHub (2026-04-01): **#66–#75** → **#56–#65**; **#76–#79**, **#81–#83** → **#48–#51**, **#53–#55**; **#32** → **#31**; **#46** → **#26**  
- [ ] Optional: GitHub **labels** `phase-1` … `phase-7` applied via `gh label` + `gh issue edit`  

After pushing this file to `main`, duplicate-close comments link here: `https://github.com/johnnyachavez/ProBooksAi/blob/main/docs/BACKLOG.md`

Refresh local export (optional):

```powershell
gh issue list --repo johnnyachavez/ProBooksAi --state open --limit 200 --json number,title,url
```

As of the last backlog pass, about **48** issues stayed open after duplicate closure (run `gh issue list --state open` for the current count).

---

## Next five to implement (suggested)

When starting the desktop + SQLite app:

1. **#21** / **#27** — migrations + DB path  
2. **#28** — backup / restore  
3. **#30** — bank accounts CRUD  
4. **#31** — CSV import per account  
5. **#34** — transaction model  

The static web prototype in this repo does not close these; it only prototypes shell UX.
