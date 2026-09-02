# ProBooks+ai vs QuickBooks Desktop Pro — cutover analysis (Chavan Trucking)

> **Date:** 2026-09-02  
> **Repo:** [johnnyachavez/ProBooksAi](https://github.com/johnnyachavez/ProBooksAi) (`main` at analysis time)  
> **Scope:** Analyze only. No product features, no refactor, no “kill QuickBooks” code.  
> **Live books:** Johnny’s company SQLite (`CHAVAN_TRUCKING_CORPORATION.db`) is on his Windows PC, not in git. This report does **not** invent customer counts, invoice numbers, balances, or open AR/AP.  
> **Product name:** ProBooks+ai (repo slug `ProBooksAi`).

This answers: can Chavan Trucking stop using QuickBooks Desktop Pro *sooner* (he refuses QuickBooks Online and Enterprise) and run invoicing + bills in ProBooks+ai **as the repo sits today**.

**COS / Grok Bot limits (given, not a code finding):** cannot print checks, cannot originate ACH, cannot scrape Chase. Those jobs stay with Johnny, the bank website, or a later human-tested feature.

---

## Go / no-go

**Not a go as a full QuickBooks Desktop Pro replacement today.**

**Conditional go for day-forward invoicing + bills** if Johnny accepts a short operating gap list (below) and does a one-time books cutover on *his* PC. The desktop app already has working Create Invoices, Enter Bills, Receive Payments, Pay Bills, lists, aging, P&L/balance sheet from posted journals, and bank import/reconciliation *without* a bank login.

The blocking difference vs “close QuickBooks and never open it again” is not the invoice form. It is cutover of **open balances + lists on the live file**, **no check printing / ACH / Chase login**, **dispatch still uses a “QB Inv No.” column the app does not write back**, and **AP bills do not post to the general ledger** (so accountant P&L/BS from ProBooks+ai journals will miss AP accruals unless expenses are posted some other way).

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

Payroll tax engine, IFTA, 1099 e-file, QBO, Enterprise, bank login, Chase scrape, live Google API, dark-theme polish, CLI/desktop schema merge.

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
