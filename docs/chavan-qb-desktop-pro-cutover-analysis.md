# ProBooks+ai vs QuickBooks Desktop Pro — cutover analysis (Chavan Trucking)

> **Date:** 2026-09-02 (expanded same day: usability roadmap + deprioritize AI document intake)  
> **Repo:** [johnnyachavez/ProBooksAi](https://github.com/johnnyachavez/ProBooksAi) (`main` at first-pass analysis; this file lives on the analysis branch)  
> **Scope:** Analyze only. No product features, no refactor, no “kill QuickBooks” code.  
> **Live books:** Johnny’s company SQLite (`CHAVAN_TRUCKING_CORPORATION.db`) is on his Windows PC, not in git. This report does **not** invent customer counts, invoice numbers, balances, or open AR/AP.  
> **Product name:** ProBooks+ai (repo slug `ProBooksAi`).

This answers: can Chavan Trucking stop using QuickBooks Desktop Pro *sooner* (he refuses QuickBooks Online and Enterprise) and run invoicing + bills in ProBooks+ai **as the repo sits today**.

**Follow-up (Johnny):** He is still building ProBooks+ai himself and wants a **sequenced usability roadmap**. He was working on AI-assisted document intake (send docs into the app for invoicing). He does **not** think he needs that now: **Grok Bot / COS** will put invoice and bill info into ProBooks from the dispatch spreadsheet, Drive files, and Gmail. He looks at the ProBooks UI to review/correct.

**COS / Grok Bot limits (given, not a code finding):** cannot print checks, cannot originate ACH, cannot scrape Chase. Those jobs stay with Johnny, the bank website, or a later human-tested feature.

---

## Go / no-go

**Not a go as a full QuickBooks Desktop Pro replacement today.**

**Conditional go for day-forward invoicing + bills** if Johnny accepts a short operating gap list (below) and does a one-time books cutover on *his* PC. The desktop app already has working Create Invoices, Enter Bills, Receive Payments, Pay Bills, lists, aging, P&L/balance sheet from posted journals, and bank import/reconciliation *without* a bank login.

The blocking difference vs “close QuickBooks and never open it again” is not the invoice form. It is cutover of **open balances + lists on the live file**, **no check printing / ACH / Chase login**, **dispatch still uses a “QB Inv No.” column the app does not write back**, and **AP bills do not post to the general ledger** (so accountant P&L/BS from ProBooks+ai journals will miss AP accruals unless expenses are posted some other way).

**Usability bar for this expansion:** invoicing + AP + P&L/BS + rec from dropped statements — not a full Intuit clone. AI document intake is **off that critical path** (see §4–§6).

---

## How this was sourced

| Kind | What |
|---|---|
| Code | `desktop_app/` PySide6 app, `probooksai/business.py`, `dispatch_intake.py`, bank/statement modules, `financial_reports.py` |
| Tests | `tests/test_extensions_business.py` (invoice numbers), `tests/test_ar_journal.py`, `tests/test_dispatch_intake.py`, `tests/test_invoice_screen.py`, bank/statement tests |
| Docs | `docs/ROADMAP.md` implementation snapshot, `README.md`, `docs/robustness-checklist.md` |
| GitHub | Open-issue list empty at analysis time; Phase 4–5 AR/AP/payroll issues (#56–#75 and duplicates) are **CLOSED**. Closed ≠ QB-Pro parity. |
| **Not used** | Johnny’s live `.db`. `docs/NORTH_STAR.md` (stale: still says Invoice/Bills are “landing pages only / no backend”). |

**Hunch (must verify on his PC):** lists and historical invoices may already live in `CHAVAN_TRUCKING_CORPORATION.db` from a past import. This repo has **CSV export** for customers/vendors, not a QuickBooks IIF/CSV **list importer**.

---

## 1) What already works in this repo (for those jobs)

### Sequential invoices from dispatch / customer data

- **Create Invoices** (`desktop_app/invoice_screen.py`) saves to `invoices` / `invoice_lines` via `probooksai.business.create_invoice` / `update_invoice`.
- **Invoice number:** `invoice_number TEXT NOT NULL UNIQUE` (`probooksai/extensions_schema.py`). Duplicate save is blocked in the UI (`tests/test_invoice_screen.py`).
- **Next number:** `business.next_default_invoice_number` increments trailing digits of the last saved invoice (`INV-009` → `INV-010`), skips collisions (`tests/test_extensions_business.py`). Suggestion is editable.
- **Dispatch → invoice:** Invoice Intake **Import dispatch CSV** parses the **1 CHAVAN DISPATCH** year-tab shape (`DATE | INVOICE | DISPATCH | DRIVER | INVOICE RATE | PAY RATE | PO / LOAD# | BOL# | QB Inv No.`). Groups unbilled loads (blank QB Inv No., live year tab) into drafts and **pre-fills Create Invoices**. User must review and Save. Live Google Sheets pull is **stubbed** (`DispatchGoogleNotConfigured` in `probooksai/dispatch_intake.py`). Tests: `tests/test_dispatch_intake.py`, `tests/test_invoice_intake_panel.py`.
- **PDF / Print:** invoice HTML/PDF path is wired (`desktop_app/invoice_pdf.py`, `invoice_print_html.py`, QPrinter). Email is **mailto** to the customer email, not SMTP.
- **Line grid:** 22 rows (`_N_LINE_ROWS`). Overflow dispatch lines are truncated in the form. Item **Code** / date / BOL are stored by joining into `invoice_lines.description` (em dash), not separate columns (`_collect_invoice_lines` + `parse_invoice_line_description`).
- **GL:** saving an invoice posts DR 1100 AR / CR 4100 revenue (and 2110 tax if tax_total > 0) (`_post_ar_invoice_journal`; `tests/test_ar_journal.py`).

### AR

- Receive Payments (`desktop_app/receive_checks_screen.py`) → `record_ar_payment`. Payments land in **Undeposited Funds** (`bank_account_id` empty). **Make Deposits** (`make_deposits_screen.py`) moves them to a bank register deposit.
- Open-invoice apply grid, payment PDF/print receipt, AR aging (`probooksai/qb_ar_aging.py`, `desktop_app/ar_aging_summary_screen.py`, Reports tab).
- Customer:Job parent (`parent_customer_id` on `customers`).
- Register **Link payment** can suggest AR invoices by amount/date (`suggest_bank_match_candidates`).

### AP / bills

- Enter Bills (`desktop_app/enter_bills_screen.py`) → `create_bill` / expense lines (`bill_expense_lines`). Attachment path, vendor invoice #, due, memo. Dispatch CSV can pre-fill **Enter Bills** (driver + pay rate, including pay rate `0` for owner-operator JC per `group_bill_drafts`).
- Pay Bills (`desktop_app/pay_bills_screen.py`) → `record_ap_payment` + bank register outflow tagged **BILLPMT**.
- Write Checks (`desktop_app/check_screen.py`) **Save** writes a negative `bank_transactions` row with optional expense splits. **Print** is a stub dialog: *“Check printing uses the company printer in a later release. Save still writes the register.”*
- AP aging (`probooksai/qb_ap_aging.py`, `ap_aging_summary_screen.py`).
- **Fact:** `create_bill` and `record_ap_payment` **do not** insert `journal_entries`. There is no `_post_ap_*` in `probooksai/business.py`. No test asserts an AP journal. Accrual AP does not hit P&L/BS until something else posts (e.g. bank txn **Post selected to GL**).

### Customer / vendor / item lists

- Customer Center, Vendor Center, Item List (`invoice_item_codes`; types: Service, Discount, Other Charge, Subtotal — **not** QB inventory/assembly/non-inventory SKU types).
- New/edit customer and vendor (vendor **1099 flag**). Inactive flags (schema v12).
- **Export** customers/vendors CSV (`write_customers_csv` / `write_vendors_csv`). **No** matching import function in `probooksai` or `desktop_app`.
- Item catalog does not seed Johnny’s live names (`invoice_codes_screen.py` docstring).

### P&L and balance sheet

- Reports tab: trial balance, income statement, balance sheet from **posted journal lines** (`probooksai/financial_reports.py`). CSV export.
- Opening Balance Wizard posts a single cut-off JE (`desktop_app/opening_balance_wizard.py`).
- Telegram bot `/pl` `/balance` (`bot/telegram_bot.py`) hits the local API — not required for desktop cutover.

### Bank rec from dropped statements (no bank login)

- **No Plaid / OFX / Chase login / scrape** in this repo (search: no bank-login client).
- **Bank Import:** Import CSV…, Import PDF…, paste CSV, statement period, **Mark Reconciled** when difference is within tolerance, mock line compare (Matched / Missing / Extra).
- **Statement Intake:** CSV / PDF (text layer) / pasted text → review table → explicit **Send to Bank Register**. No auto-post. Image OCR on this panel is documented out of scope.
- **Scanned PDF:** `statement_ocr_stub.extract_rows_from_statement_scan` can call Anthropic/OpenAI **if** API keys are set; without keys, status is `NOT_IMPLEMENTED` (`tests/test_statement_ocr_stub.py`). ROADMAP snapshot still says scanned OCR is not implemented — **hunch:** snapshot lags this module; verify against how Johnny actually imports Chase PDFs.
- **Main-window drag-and-drop** (`MainWindow.dropEvent`) only accepts `.pdf` / `.jpg` / `.jpeg` / `.png` into **Document Intake**, not bank CSV (`ACCEPTED_EXTENSIONS`). Bank files go through Bank Import / Statement Intake file dialogs.
- **PDF review filter:** Import PDF (Review) **excludes deposits, checks, and ACH/online bill-pay by default** so those are entered/matched manually (`bank_import_tab.py` tooltip; `bank_statement_review_dialog.py`). That is a product rule, not Chase access.

### Other desktop surfaces that exist

Home, Income/Bill Trackers, Calendar, Company Snapshot, My Company, Chart of Accounts, Bank Register, Reconcile hub, More (Business rules/payroll/tax, Journal, Audit), File Open/New company, Backup/Restore (`probooks.backup`). Version in `pyproject.toml`: **0.1.0**. Windows onefile script: `scripts/build_desktop.ps1` → `ProBooksPlusAi.exe` (not a signed installer).

---

## 2) Missing or incomplete vs QuickBooks Desktop Pro (small trucking company)

Compared to what Desktop Pro typically does for a hauler (invoices, bills, lists, reports, bank rec, year-end). Not a full Intuit feature matrix.

| Job | Gap (fact unless marked hunch) |
|---|---|
| Dispatch loop | No live Google token. No write-back of ProBooks invoice # into the sheet’s **QB Inv No.** column. Re-import safety still means “human filled that column.” |
| Historical QB lists | No IIF / QB Customer-Vendor-Item CSV importer in repo. Export only. |
| Historical QB transactions | No company-file converter. Opening Balance Wizard is a cut-off JE, not a line-by-line QB history. |
| Two SQLite files | Desktop default `probooksai.db` vs CLI `probooks.db` in the same `%LOCALAPPDATA%\ProBooks+ai\` folder (`README.md`, `tests/test_issue_21_schema_inventory.py`). GitHub **#21 is CLOSED**; docs still describe two schemas. **Hunch:** Johnny already opens a named company file; confirm path on his PC. |
| AP → GL | Bills/payments update `bills` / `ap_payments` only. P&L/BS from journals miss AP accruals. |
| Invoice line items | Code/date/BOL packed into `description`. No inventory items. 22-line cap on the form. |
| Check print | Write Checks Print is not wired. Vendor **Order Checks** / **Order 1099 Forms** are info dialogs. |
| ACH / bill-pay origination | Method can be *labeled* ACH on Receive Payments. App does not send ACH. Statement import *filters ACH out* of auto-import. |
| Bank rec vs QB Reconcile | Period math + Mark Reconciled + line match. Not QB’s locked recon with beginning balance, checkmarks, and statement ending as a hard close. No period lock (`docs/robustness-checklist.md` still unchecked). |
| 1099 | Flag + filter only. No 1099-NEC form, e-file, or totals report. |
| Payroll / IFTA | Payroll tab is an MVP (employees, pay runs, placeholder tax codes, optional GL post). Robustness checklist lists IFTA / load costing / fuel as **Later**. |
| Customer statements, estimates, credit memos, POs, sales orders, recurring/memorized txns | Not found as working documents. Aging **Memorize** / **E-mail report** are stubs. Check **Memorize** is layout-only. |
| Multi-user / Intuit hosting | One SQLite file on one PC. Backup/Restore exists. |
| Windows “install like QB” | PyInstaller script exists; packaging issues were closed as duplicates. Not verified as a Store/MSI install on Johnny’s machine. |

Trucking-specific (checklist, not implemented as first-class): load-based revenue beyond dispatch CSV, fuel/IFTA, equipment depreciation, driver vs contractor payroll split.

---

## 3) Smallest gap list to run invoicing + bills in ProBooks+ai and leave QB

Do these on **his Windows PC** with the live company file. This analysis cannot tick them.

### Must do at cutover (process + data, not new app features)

1. **Open the live file** (`File → Open company…` or `--database`) and confirm customers, vendors, items, COA, and bank accounts are present. If lists are empty, re-key or add a list importer — **none ships today**.
2. **Enter or import open AR and open AP** (or Opening Balance Wizard + open invoices/bills) so aging and Receive/Pay Bills match reality. Do not assume git has this.
3. **Bank starting point:** last reconciled balances in the register (CSV/PDF import going forward). COS will not scrape Chase.
4. **Dispatch control:** after each ProBooks Save, copy the invoice number into the Google Sheet **QB Inv No.** column (or equivalent). Until that happens, CSV intake can stage the same load twice.
5. **Payments he still makes outside the app:** printed checks, bank ACH, Chase bill-pay. Record them in Pay Bills / Write Checks / register after the bank shows them. Do not expect the bot or the app to print or originate them.

### Smallest *product* gaps if day-forward invoicing+bills is the bar

1. **AP journal posting** (mirror AR) — only if the accountant needs accrual P&L/BS from ProBooks+ai, not just invoice/bill lists + bank register.
2. **Check printing** — only if he still mails paper checks from QB. Otherwise bank bill-pay + register entry is enough.
3. **List CSV import** — only if the live `.db` does not already hold QB-exported names.
4. **Write invoice # back to dispatch** — only if he will not update the sheet by hand.

### Not required to *leave QB for invoicing+bills*

Payroll tax engine, IFTA, 1099 e-file, QBO, Enterprise, bank login, Chase scrape, live Google API **in the desktop app**, dark-theme polish, CLI/desktop schema merge, **AI document intake / Run AI / Telegram extract** (see §4–§6). Sequenced build order is **§6**.

---

## Operating model if he goes (day-forward)

| Need | In ProBooks+ai today | Still outside the app |
|---|---|---|
| Numbered customer invoices + PDF | Yes | — |
| Stage loads from dispatch CSV | Yes (export sheet, not live) | Fill QB Inv No. after billing |
| Enter vendor bills / pay them | Yes | Paper check print, ACH send |
| See who owes / whom we owe | AR/AP aging + trackers | — |
| Bank activity | Drop/import CSV or text-layer PDF | Chase website download |
| Tax-basis P&L | From **posted** journals | Accountant review; AP not auto-posted |

---

## Explicit non-findings

- No balances, invoice sequences, or list sizes from `CHAVAN_TRUCKING_CORPORATION.db`.
- Closed GitHub issues (#56 invoicing, #59 bills, etc.) mean those **MVP tickets** were closed, not that Desktop Pro parity is done.
- `docs/NORTH_STAR.md` “landing pages only” is **false** relative to current `main` (Invoice/Bills/Pay Bills/Receive Payments are real forms). Trust the screens and tests, not that file.
- This report does not recommend deleting QuickBooks company files or changing Intuit license timing.

---

## 4) Two “intake” stacks in this repo (do not mix them)

Johnny’s “send docs into the app for invoicing” work maps to **in-app extractors**. COS-fed entry is a **different** path. Facts:

| Stack | Where | What it does today | Creates an invoice/bill? |
|---|---|---|---|
| **Document Intake** (Reconcile hub) | `desktop_app/main.py` inbox + `ai.extractor` **Run AI** | Drop PDF/image (window drop: `.pdf` `.jpg` `.jpeg` `.png` only). Extract fields, **Approve** stores values, **Mark Posted** only changes document **status**. | **No.** Approve/Posted do not call `create_invoice` / `create_bill`. **Route to Invoice** calls `InvoiceScreen.prefill_from_document` — **that method is not defined** on `invoice_screen.py` (only `EnterBillsScreen.prefill_from_document` exists). **Hunch:** Route to Invoice would `AttributeError` if used; verify by clicking it on his build. |
| **Invoice Intake** (Invoices tab) | `desktop_app/invoice_intake_panel.py` | Dispatch **CSV**, pasted text, PDF/image **text** extract (`invoice_intake_file_extract` / optional Tesseract). **Send to Manual Invoice** uses `apply_dispatch_invoice_draft` / `apply_intake_item_to_draft` — draft only; user **Save**s. | Draft only until Save. |
| **Remote API** | `api/server.py` | `POST /intake/document` (same `ai.extractor`), **and** `POST /invoices` / `POST /bills`. Telegram bot (`bot/telegram_bot.py`) uploads to `/intake/document` then prompts route. | Invoice/bill POST can insert rows. **Fact:** `POST /invoices` sends line keys `quantity` / `unit_price`; `business.create_invoice` reads `qty` / `rate` (defaults 1 × 0). `tests/test_api_server.py` asserts `ok` and count, **not** invoice `total`. **Hunch:** API-created invoices with only quantity/unit_price save **$0** lines — verify with one POST before COS relies on it. Bill POST uses `amount` on expense lines, which `create_bill` **does** sum. |
| **COS / Grok Bot** (operator) | Not a package in this repo | Johnny’s intent: read dispatch sheet, Drive, Gmail → put invoice/bill info into ProBooks; he reviews the UI. | **No Gmail or Google Drive client in `desktop_app/` / `probooksai/`** (repo search: no matches). COS reading Drive/Gmail is **outside the PySide6 app** (Cursor tools / browser / his own scripts). Writing the **Windows** company `.db` still needs a local app, local API (`PROBOOKS_DB_PATH`), or him typing on the forms. |

**Product roadmap Phase 7** (`docs/ROADMAP.md`) is **bank statement** PDF/OCR (Issue #11 Chase image), not customer-invoice document intake. Snapshot still says scanned statement OCR is not implemented; `statement_ocr_stub.py` has an optional Anthropic/OpenAI path. That is bank rec tooling, not “email me a ticket and invoice it.”

---

## 5) Deprioritize AI document intake vs COS-fed entry

**Recommendation (analysis, not a code change):** stop spending build time on in-app **Run AI** / `/intake/document` / Telegram photo extraction **for invoicing**. Johnny has already decided COS will pull dispatch + Drive + Gmail.

Keep using:

- **Create Invoices** and **Enter Bills** as the review/correct surface (already the daily forms).
- **Dispatch CSV → Send to Manual Invoice / Enter Bills** as a **fallback** if COS is down (already works; no live Google token required).
- **Bank Import / Statement Intake** for Chase files he **downloads** (COS cannot scrape Chase).

Park / do not grow:

- Document Intake **Run AI** (`ai.extractor`, `ai.categorizer`) as the invoicing pipeline.
- Invoice Intake **PDF/image OCR** as the primary billing path (`invoice_intake_file_extract`, Tesseract).
- Wiring **Route to Invoice** / Telegram “Route to Invoice?” until COS-fed Save on the real forms is the habit.
- Desktop Gmail/Drive connectors, live Google Sheets token (`DispatchGoogleNotConfigured` is explicit).
- Phase 7 Chase **vision** OCR as a prerequisite to leave QB (text-layer PDF + CSV already exist).

**Why this matches the code:** Document Intake never posts AR/AP; Invoice routing to Create Invoices looks unfinished; COS-fed work should land on `create_invoice` / `create_bill` **or** the same forms Johnny already corrects. Building a second extractor does not close AP→GL or cutover.

**COS-fed entry — what is actually wired vs intended**

| Step | Wired in ProBooks+ai? |
|---|---|
| COS reads **1 CHAVAN DISPATCH** / Drive / Gmail | Not in the desktop app. Possible only as an **agent/operator** using Google UIs or Cursor MCP, not `python -m desktop_app.main`. |
| COS fills Create Invoices / Enter Bills | No UI-automation API in-repo. Practical path: COS drafts fields → Johnny (or a local agent) types/saves, **or** local `POST /invoices` / `POST /bills` if `uvicorn api.server` points at **his** company file. |
| Johnny reviews/corrects in the UI | Yes — that is what the forms are for (`update_invoice` blocked if payments exist). |
| COS prints checks / ACH / scrapes Chase | No (given). Record after the bank file is imported. |

---

## 6) Sequenced usability roadmap (smallest path to leave QB Desktop Pro)

Goal: **invoicing + AP + P&L/BS + rec from dropped statements.** Each step is something Johnny can build or **practice** himself. Do not start a later step to avoid an earlier one. AI document intake is **not** on this list.

### Step 0 — Freeze the operating model (this week, no new features)

1. Daily books live in **one** company SQLite opened in the desktop app (`File → Open company…` / `--database`). Confirm it is the Chavan file on his PC, not a second `probooksai.db` leftover (`README.md` two-filename note).
2. **COS** (or Johnny) sources loads from the dispatch spreadsheet / Drive / Gmail. **Johnny** (or COS via a **verified** write path) enters Create Invoices / Enter Bills. He **Save**s after looking at the form.
3. After Save, copy the new invoice number into the sheet **QB Inv No.** column (COS can do that in Drive; the app will not).
4. Download Chase CSV or text-layer PDF → Bank Import or Statement Intake → review → Send/import → **Mark Reconciled** when the difference is within tolerance.
5. Pay vendors in Chase (ACH/bill-pay/check). Then Pay Bills or Write Checks **Save** (or link the register row). Do not wait for check printing.

**Already enough for this step:** the forms, unique invoice numbers, PDF, aging, backup/restore, bank CSV/PDF import.

### Step 1 — Cutover data on the live file (process; blocks “kill QB”)

Do on **his** PC. This analysis cannot tick these.

1. Confirm customers, vendors, items, COA, bank accounts exist (or re-key; no list importer in repo).
2. Enter **open invoices** and **open bills** (or Opening Balance Wizard + open documents) so AR/AP aging matches QB at cutover.
3. Register **beginning** balances match the last QB reconcile. Going forward, only dropped/imported statements.

Without this, P&L/BS and aging are a new set of books, not a replacement.

### Step 2 — AP into the general ledger (smallest *product* gap for P&L/BS)

**Fact:** invoices post `ar_invoice:<id>` journals; bills/payments do not.

Until AP posts (mirror `_post_ar_invoice_journal` / payment journals), Reports **P&L and balance sheet omit accrued bills**. Bank **Post selected to GL** can still put cash expenses on the P&L if he posts register lines — that is cash-ish, not QB-style AP accrual.

**Build this before** more Invoice Intake OCR, more QB-lookalike chrome, or Gmail connectors.

**Hunch:** Pay Bills already writes a bank outflow; an AP JE plus that bank post can double-count expense if both hit the P&L. Design the JE (DR expense / CR AP on bill; DR AP / CR cash on pay) and test with one bill before cutover. Verify in `tests/` the way `tests/test_ar_journal.py` does for AR.

### Step 3 — Prove the bank rec loop on *his* Chase files

Use existing Bank Import + Mark Reconciled + optional mock line compare. If **his** PDF is image-only, either export CSV from Chase or turn on statement vision **for statements only** (`statement_ocr_stub`) — still **not** invoice document intake.

Do not block cutover on Issue #11 / Phase 7 “drag a photo of the statement.”

### Step 4 — Only if COS will `POST` instead of typing the forms

If COS is supposed to insert invoices via `api/server.py`:

1. Run API against **`PROBOOKS_DB_PATH` = the same file the desktop opens**.
2. **Verify line totals** (qty/rate vs quantity/unit_price — see §4). Treat a failing total as a **small contract fix**, not a new product.
3. He still opens the invoice in the UI and corrects.

If COS types into the desktop (or he types from a COS draft), **skip this step.**

### Step 5 — Optional polish after he has billed a week in ProBooks+ai only

Only if the daily loop hurts:

- Dispatch write-back of invoice # (or keep COS updating Drive).
- List CSV import (only if lists were empty at Step 1).
- Check printing (only if he still mails paper checks from QB).
- Rec locking / beginning-balance UI closer to QB Reconcile.

### Explicitly later / not on the kill-QB path

Payroll tax engine, IFTA, 1099 e-file, estimates, credit memos, memorized reports, live Google token **in the app**, Document Intake AI, CLI/desktop single-`.db` merge, signed Windows installer, QBO.

---

## 7) Keep building vs already enough

| Area | Already enough to operate | Keep building (himself, in this order) | Stop / deprioritize |
|---|---|---|---|
| Invoices | Create Invoices, sequential #, UNIQUE, PDF/print, terms/due, 22-line grid, AR JE | Bugs he hits on Save/Find/PDF; optional API qty/rate if COS posts | AI Document Intake, Invoice Intake OCR as the billing engine, Route-to-Invoice from Run AI |
| Dispatch | CSV import → draft (fallback) | Process: COS or he fills **QB Inv No.** after Save | Live Sheets token in the desktop app |
| AP | Enter Bills, Pay Bills, Write Checks **save**, AP aging | **AP journal posting** (Step 2) | Check print, Order 1099/Checks buttons, ACH origination |
| AR cash | Receive Payments → Make Deposits, link payment on register | Practice the undeposited → deposit loop once | — |
| P&L / BS | Reports from **posted** journals; Opening Balance Wizard | Step 1 cutover + Step 2 AP JE; then **Post selected to GL** on bank lines he wants on the books | Fancy report memorize/email (stubs) |
| Bank rec | CSV, text PDF, paste, Mark Reconciled, statement intake hand-off | Reliability on **his** statement layout; rules for repeat payees | Chase login/scrape; scanned-statement OCR as a gate |
| Lists | Customer/Vendor/Item CRUD, 1099 flag, CSV export | Re-key or import only if live DB is empty | Full QB IIF converter |
| Intake AI | — | — | `ai.extractor` invoicing pipeline, `POST /intake/document`, Telegram extract-and-route |
| Packaging / schema | Backup/Restore; PyInstaller script | Only if he cannot run `python -m desktop_app.main` on that PC | #21 merge, MSI/store as a cutover blocker |

**What “keep making updates himself” should mean:** one vertical at a time (AP GL, then rec on real Chase files, then API contract if used). Do not parallelize QB-lookalike screens (Calendar, Snapshot, Item List polish) with the kill-QB bar — those already exist well enough to review COS-fed invoices.

---

## 8) Suggested build tickets (for him; not implemented here)

Small enough to merge alone; order matches §6.

1. **AP bill + AP payment journal entries** + tests cloned from `tests/test_ar_journal.py`. Watch double-count vs bank posting.
2. **(Only if COS uses API)** Map `POST /invoices` lines to `qty`/`rate` and assert `total` in `tests/test_api_server.py`.
3. **Cutover checklist** on the live file (not code): lists, open AR/AP, bank beginning balance, first Mark Reconciled.
4. Leave Document Intake as-is (or hide later). Do not add Gmail/Drive to the desktop for this cutover.

---

*Setup and contribution links stay in `docs/ROADMAP.md`; this file is the Chavan cutover / usability sequence, not a replacement for the phased GitHub issue table.*
