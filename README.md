# ProBooksAi – AI-Powered Accounting Software

> **A complete, double-entry accounting framework delivered as a richly formatted Excel workbook,  
> plus a native Windows desktop application for AI-assisted document intake (PDF & images).**

---

## ✨ Features

| # | Module | Description |
|---|--------|-------------|
| 1 | **Invoicing / Accounts Receivable** | Full AR register – create invoices, track open balances, record payments, auto-calculate tax |
| 2 | **Bill Pay / Accounts Payable** | Complete AP system – enter vendor bills, track due dates, record payments, aging analysis |
| 3 | **Vendor Database** | Master vendor template with contact info, payment terms, 1099 flag, and expense account mapping |
| 4 | **Customer Database** | Master customer template with credit limits, payment terms, tax-exempt flag, and AR account |
| 5 | **Reports System** | AR Aging (0-30 / 31-60 / 61-90 / 90+ days) and AP Aging, both auto-calculated |
| 6 | **Financial Reporting** | P&L Statement, Balance Sheet, and Cash Flow Statement – all formula-driven from journal entries |
| 7 | **Cash or Accrual** | Accounting method toggle in Settings; each invoice/bill carries its own basis flag |
| 8 | **Chart of Accounts** | 48-account COA covering Assets, Liabilities, Equity, Revenue, COGS, and Expenses |
| 9 | **General Ledger** | Double-entry Journal Entries with automatic debit = credit balance check |
| 10 | **Trial Balance** | SUMIF-powered aggregation of every account's debit and credit totals |
| 11 | **Dashboard** | KPI cards (AR, AP, Cash, Net Income) and a full sheet navigator |
| 12 | **Document Intake Desktop App** | Drag-and-drop PDF/image import → AI extraction → human review → approve & post |

---

## 🖥️ Desktop Application (Document Intake)

### Prerequisites

```bash
pip install -r requirements.txt
```

### Set AI API keys via environment variables

The application uses OpenAI (or any OpenAI-compatible provider) for document extraction.
**Never hard-code secrets** – set them via environment variables before launching the app:

**Windows (Command Prompt):**
```cmd
set OPENAI_API_KEY=sk-your-key-here
```

**Windows (PowerShell):**
```powershell
$env:OPENAI_API_KEY = "sk-your-key-here"
```

Optional environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | *(required)* | Your OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o` | Model to use (must support vision for images) |
| `AI_BASE_URL` | *(OpenAI default)* | Override for Azure OpenAI, Ollama, or other compatible endpoints |
| `AI_PROVIDER` | `openai` | Provider name (currently only `openai` is supported) |

### Run the desktop app

```bash
python -m desktop_app.main
```

### Where local data is stored

All imported documents and the SQLite database are stored in:

| Platform | Location |
|----------|----------|
| **Windows** | `%APPDATA%\ProBooksAi\` |
| Other | `~\ProBooksAi\` |

The database file is `probooksai.db` inside that directory.  
Imported document copies are stored in the `documents/` subdirectory.

These paths are excluded from git via `.gitignore`.

### Basic workflow

1. **Import** – Click "📂 Import Documents…" or drag & drop PDF/image files onto the inbox.
2. **Run AI** – Select a document and click "⚡ Run AI" to extract fields via the cloud AI.
3. **Review** – Check the extracted fields (vendor, total, date, etc.) and edit as needed.
4. **Categorise** – Confirm or adjust the suggested Chart of Accounts mapping.
5. **Approve** – Click "✅ Approve" to save the reviewed values.
6. **Post** – Click "📤 Mark Posted" to finalise the document.

Document statuses: `New → Extracted → Needs Review → Approved → Posted` (or `Error`)

---

## 📂 Workbook Structure (17 sheets)

```
ProBooksAi_Accounting.xlsx
├── Dashboard          ← KPIs & navigator
├── Settings           ← Company info, accounting method (Cash/Accrual), tax rate
├── COA                ← Chart of Accounts (48 accounts)
├── Customers          ← Customer master database
├── Vendors            ← Vendor master database
├── Invoices           ← AR invoice register
├── Invoice_Lines      ← Line-item detail per invoice
├── AR_Payments        ← Cash receipts journal
├── Bills              ← AP bill register
├── AP_Payments        ← Cash disbursements journal
├── Journal_Entries    ← General ledger (double-entry)
├── Trial_Balance      ← SUMIF-aggregated debit/credit by account
├── P&L                ← Profit & Loss Statement
├── Balance_Sheet      ← Balance Sheet (Assets = Liabilities + Equity)
├── Cash_Flow          ← Operating / Investing / Financing activities
├── AR_Aging           ← AR aging buckets (0-30 / 31-60 / 61-90 / 91+)
└── AP_Aging           ← AP aging buckets (0-30 / 31-60 / 61-90 / 91+)
```

---

## 📁 Repository Structure

```
ProBooksAi/
├── probooksai/               ← Core library (importable)
│   ├── __init__.py
│   ├── generator.py          ← Workbook generation logic
│   ├── database.py           ← SQLite document intake storage
│   └── coa.py                ← Chart of Accounts loading helpers
├── ai/                       ← Cloud AI modules
│   ├── __init__.py           ← ExtractionResult, CategorySuggestions
│   ├── extractor.py          ← extract_document() via cloud AI
│   └── categorizer.py        ← suggest_categories() via cloud AI
├── desktop_app/              ← PySide6 desktop GUI
│   ├── __init__.py
│   └── main.py               ← Document intake / review UI
├── tests/                    ← Unit tests (database, AI, categorisation)
├── scripts/                  ← PyInstaller build helpers
│   ├── build_desktop.sh      ← macOS / Linux
│   └── build_desktop.ps1     ← Windows PowerShell
├── generate_workbook.py      ← CLI entry-point (thin wrapper)
├── test_workbook.py          ← Workbook pytest test suite
├── requirements.txt
└── ProBooksAi_Accounting.xlsx ← Sample generated workbook
```

---

## 🚀 Quick Start (Workbook Generator)

### Prerequisites

```bash
pip install -r requirements.txt
```

### Run the Desktop App (Document Intake)

```bash
python -m desktop_app.main
```

See the **Desktop Application** section above for AI key setup and workflow.

### Run the CLI Generator

```bash
python generate_workbook.py
```

This creates **`ProBooksAi_Accounting.xlsx`** in the current directory.  
Open it with Excel, Google Sheets *(File → Import)*, or LibreOffice Calc.

### Run Tests

```bash
pip install -r requirements.txt
python -m pytest -v
```

All tests should pass.

---

## 📦 Building a Standalone Desktop Installer

Use [PyInstaller](https://pyinstaller.org/) to package the app as a single executable.

### macOS / Linux

```bash
chmod +x scripts/build_desktop.sh
./scripts/build_desktop.sh
# Executable written to: dist/ProBooksAi
```

### Windows (PowerShell)

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\build_desktop.ps1
# Executable written to: dist\ProBooksAi.exe
```

> **Note:** The `dist/` and `build/` directories are git-ignored; do not commit generated binaries.

---

## 🔧 Customisation Guide

### 1. Change your company name
Edit the **Settings** sheet in the generated workbook, or modify `build_settings()` inside `probooksai/generator.py`.

### 2. Add / modify Chart of Accounts
Edit the `COA_DATA` list in `probooksai/generator.py`.

### 3. Add real transactions
- **Invoices** → add rows to the `Invoices` sheet.
- **AR Payments** → add rows to `AR_Payments`.
- **Bills** → add rows to the `Bills` sheet.
- **AP Payments** → add rows to `AP_Payments`.
- **Journal Entries** → add the corresponding double-entry rows.

### 4. Switch accounting method
In the **Settings** sheet, change `Accounting Basis` from `Accrual` to `Cash`.

---

## 📊 Financial Formula Overview

| Report | Formula Logic |
|--------|--------------|
| **P&L Revenue** | `=SUMIF(Journal_Entries[Account #], acct, Journal_Entries[Credit]) – SUMIF(…, Debit)` |
| **Balance Sheet Assets** | Net Debit balance per account from Journal Entries |
| **Trial Balance** | SUMIF aggregation of all Journal Entry debits and credits by account |
| **AR Aging** | Days overdue = `TODAY() – Due Date`; bucketed into 0-30/31-60/61-90/91+ columns |
| **Dashboard KPIs** | SUMIF on Invoice/Bill `Status = "Open"` for AR/AP |

---

## 🗺️ Roadmap

The full, ordered implementation plan lives in **[docs/ROADMAP.md](docs/ROADMAP.md)**.

Phases at a glance:

| Phase | Focus | Key references |
|---|---|---|
| 1 | Data foundations (COA, bank accounts, bank txns) | baseline |
| 2 | CSV import with column mapping & dedupe | [PR #10](https://github.com/johnnyachavez/ProBooksAi/pull/10) |
| 3 | Bank register UI (date, #, payee, debit, credit, balance) | [PR #14](https://github.com/johnnyachavez/ProBooksAi/pull/14) |
| 4 | Reconciliation (statement periods + begin/end + diff + mark reconciled) | [Issue #12](https://github.com/johnnyachavez/ProBooksAi/issues/12), [PR #13](https://github.com/johnnyachavez/ProBooksAi/pull/13) |
| 5 | Posting bank transactions to the General Ledger | — |
| 6 | Rules engine & AI category hints | — |
| 7 | PDF / OCR intake from bank statement images | [Issue #9](https://github.com/johnnyachavez/ProBooksAi/issues/9), [Issue #11](https://github.com/johnnyachavez/ProBooksAi/issues/11) |

---

## 🏦 Banking Workflow (current)

The intended end-to-end flow for managing bank transactions in ProBooksAi:

1. **Select bank account** – choose or create the bank account (e.g., "Chase Checking 4521") in the account manager.
2. **Import CSV** – export a CSV from your bank's website and drag it into the "Bank Import" tab.
3. **Map columns** – a one-time column-mapping dialog lets you specify which column is Date, Description, Amount, etc.; the mapping is saved per account.
4. **Review transactions** – the imported transactions appear in an editable table; assign a COA category to each row; duplicates are automatically flagged and skipped.
5. **Open the Register** – switch to the "Register" tab to see all transactions for the selected account in a check-register layout (Date, #, Payee, Memo, Debit, Credit, Running Balance).
6. **Reconcile** – open the reconciliation panel, enter the statement's start/end dates and beginning/ending balances; the system computes the difference and enables "Mark Reconciled" when it reaches zero.
7. **Post to GL** – once reconciled, post transactions to the General Ledger to keep double-entry books in sync.

---

*ProBooksAi – An accounting system for the future* 🚀
