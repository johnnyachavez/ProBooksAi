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
| Other | `~/.ProBooksAi\` |

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

## 🚀 Quick Start (Workbook Generator)

### Prerequisites

```bash
pip install openpyxl
```

### Generate the workbook

```bash
python generate_workbook.py
```

This creates **`ProBooksAi_Accounting.xlsx`** in the current directory.  
Open it with Excel, Google Sheets *(File → Import)*, or LibreOffice Calc.

### Run tests

```bash
pip install -r requirements.txt
python -m pytest -v
```

All tests should pass.

---

## 🔧 Customisation Guide

### 1. Change your company name
Open `generate_workbook.py` and update the `build_settings()` function, or simply edit the **Settings** sheet in the generated workbook.

### 2. Add / modify Chart of Accounts
Edit the `COA_DATA` list in `generate_workbook.py`.  
All report sheets (Trial Balance, P&L, Balance Sheet, Cash Flow) automatically pick up new accounts on the next generation.

### 3. Add real transactions
- **Invoices** → add rows to the `Invoices` sheet; fill the `Invoice_Lines` sheet for line detail.
- **AR Payments** → add rows to `AR_Payments`; update the invoice `Payments Applied` and `Balance Due` columns.
- **Bills** → add rows to the `Bills` sheet.
- **AP Payments** → add rows to `AP_Payments`; update the bill `Payments Applied` and `Balance Due` columns.
- **Journal Entries** → add the corresponding double-entry rows. All financial reports will update automatically via SUMIF formulas.

### 4. Switch accounting method
In the **Settings** sheet, change `Accounting Basis` from `Accrual` to `Cash` using the dropdown.  
Each invoice and bill also carries its own `Accounting Basis` field so you can tag entries individually.

---

## 📊 Financial Formula Overview

| Report | Formula Logic |
|--------|--------------|
| **P&L Revenue** | `=SUMIF(Journal_Entries[Account #], acct, Journal_Entries[Credit]) – SUMIF(…, Debit)` |
| **Balance Sheet Assets** | Net Debit balance per account from Journal Entries |
| **Balance Sheet Liabilities/Equity** | Net Credit balance per account from Journal Entries |
| **Trial Balance** | SUMIF aggregation of all Journal Entry debits and credits by account |
| **Cash Flow – Operating** | Net income ± changes in AR, AP, and accrued liabilities |
| **AR Aging** | Days overdue = `TODAY() – Due Date`; bucketed into 0-30/31-60/61-90/91+ columns |
| **Dashboard KPIs** | SUMIF on Invoice/Bill `Status = "Open"` for AR/AP; SUM of payment sheets for cash |

---

## 📁 File Reference

| File / Directory | Purpose |
|-----------------|---------|
| `generate_workbook.py` | Main script – generates the entire Excel workbook |
| `test_workbook.py` | pytest test suite validating all sheets and data integrity |
| `ProBooksAi_Accounting.xlsx` | Generated workbook (re-created each run) |
| `requirements.txt` | Python dependencies |
| `desktop_app/main.py` | PySide6 desktop application entry point |
| `probooksai/database.py` | SQLite database module for document intake |
| `probooksai/coa.py` | Chart of Accounts loading helpers |
| `ai/extractor.py` | Cloud AI document extraction (`extract_document()`) |
| `ai/categorizer.py` | Cloud AI COA categorisation (`suggest_categories()`) |
| `tests/` | Unit tests for database, AI extraction, and categorisation |

---

## 🗺️ Roadmap

- [ ] Google Apps Script version (native Google Sheets integration)
- [ ] Payroll module (payroll journal entries, tax calculations)
- [ ] Fixed asset depreciation schedule
- [ ] Bank reconciliation worksheet
- [ ] Multi-currency support
- [ ] Budget vs. Actual comparison report
- [ ] 1099 vendor report
- [ ] PyInstaller packaging for Windows (.exe)
- [ ] PDF export of combined invoice + attachments

---

*ProBooksAi – An accounting system for the future* 🚀
