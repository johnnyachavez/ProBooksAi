# ProBooksAi – AI-Powered Accounting Software

> **A complete, double-entry accounting framework delivered as a richly formatted Excel workbook.**  
> Available as a **native desktop app (PySide6/Qt)** and as a **CLI script**, both generating a ready-to-use `.xlsx` file compatible with **Microsoft Excel**, **Google Sheets**, and **LibreOffice Calc**.

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
│   └── generator.py          ← Workbook generation logic
├── desktop_app/              ← PySide6 desktop GUI
│   ├── __init__.py
│   └── main.py
├── scripts/                  ← PyInstaller build helpers
│   ├── build_desktop.sh      ← macOS / Linux
│   └── build_desktop.ps1     ← Windows PowerShell
├── generate_workbook.py      ← CLI entry-point (thin wrapper)
├── test_workbook.py          ← pytest test suite
├── requirements.txt
└── ProBooksAi_Accounting.xlsx ← Sample generated workbook
```

---

## 🚀 Quick Start

### Prerequisites

```bash
pip install -r requirements.txt
```

### Run the Desktop App

```bash
python -m desktop_app.main
```

A window will open.  
1. Choose an output path with **Browse…** (defaults to `ProBooksAi_Accounting.xlsx` in the current directory).  
2. Click **Generate Workbook**.  
3. The status log will confirm the file location when complete.

### Run the CLI Generator

```bash
python generate_workbook.py
```

This creates **`ProBooksAi_Accounting.xlsx`** in the current directory.  
Open it with Excel, Google Sheets *(File → Import)*, or LibreOffice Calc.

### Run Tests

```bash
python -m pytest test_workbook.py -v
```

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

- [ ] Google Apps Script version (native Google Sheets integration)
- [ ] Payroll module (payroll journal entries, tax calculations)
- [ ] Fixed asset depreciation schedule
- [ ] Bank reconciliation worksheet
- [ ] Multi-currency support
- [ ] Budget vs. Actual comparison report

---

*ProBooksAi – An accounting system for the future* 🚀
