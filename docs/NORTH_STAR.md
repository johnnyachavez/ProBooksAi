# ProBooks+ai Desktop App (PySide6) — NORTH STAR

## Project
ProBooks+ai Desktop App (PySide6)

## Goal
Build a clean, QuickBooks-style bookkeeping app with:
- **Bank Register as source of truth**
- Separate **AI-powered reconciliation workflow**
- Structured accounting modules (Invoice, Bills, etc.)
- Clean, predictable UI (**no popups**, no confusion)

---

## Core Architecture

### 1) Bank Register (Core)
**Source of truth**:
- Holds ALL transactions (manual + imported)
- Continuous running balance
- **Inline editing ONLY** (no popups)

**Columns**:
- Date
- Number
- Payee/Description
- Debit
- Credit
- Balance
- COA

### 2) Reconciliation (Tool, Not Core)
- Activated via **toggle** (NOT separate navigation system)
- Reads CSV/PDF (AI later)
- Compares against register
- Classifies: **Matched / Missing / Extra**
- **Does NOT auto-post**

---

## Navigation Structure

### Main Tabs (Static, Always Same Order)
1. HOME
2. INVOICE
3. ENTER BILLS
4. PAY BILLS
5. RECEIVE CHECKS
6. Bank register
7. Chart of Accounts
8. Reports
9. Journal
10. Business
11. Audit log

**Rules**
- Tabs **NEVER** change based on recon mode
- No duplicate “Bank register” tab
- **HOME must exist and be first**

---

## Home Screen
- Full-screen background image (truck image)
- Scales to fit window
- Optional overlay text
- **No margins**

---

## Recon Mode

### Toggle Placement
- Toggle located at **FAR RIGHT of the tab bar**
- **ONLY visible when Bank Register tab is active**
- Toggle **NEVER disappears** (when Bank Register is active)

### Behavior
- **ON** → overlay recon tools **inside** register
- **OFF** → normal register

**Do NOT**
- Add/remove main tabs
- Require navigation to exit recon

---

## Recon-only Tabs
- Bank Import (CSV / PDF / paste statements under **Reconcile → Bank statements**)
- Statement intake (review)

**Rules**
- MUST NOT appear as a document-AI invoice inbox
- Bank statement import stays on the Reconcile hub
- Invoice documents use **Create Invoices** / **Invoice Intake** (dispatch spreadsheet), not Document Intake

---

## Register UI Rules
- **Inline editing ONLY** (no pop-out editors)
- No custom delegates expanding cells
- Editor must stay inside cell bounds
- No word wrap expansion

---

## Date Input (Global Rule)
All date fields:
- Normalize to **MM/DD/YYYY**
- Accept inputs like:
  - `5/21/26`
  - `05.21.26`
  - `052126`
- Convert automatically to:
  - `05/21/2026`

Applies globally across app.

---

## COA Column
- Linked to Chart of Accounts
- Click = dropdown selection
- Supports typing + autocomplete
- Optional: double-click → open COA tab

---

## Accounting Modules (UI Only For Now)
- INVOICE
- ENTER BILLS
- PAY BILLS
- RECEIVE CHECKS

Current state:
- Landing pages only
- No backend logic yet

Later behavior:
- Invoice → A/R
- Receive Checks → reduce A/R + create bank entry
- Enter Bills → A/P
- Pay Bills → reduce A/P + create bank entry

---

## UI Standards
- Clean, QuickBooks-style layout
- No overlapping text
- No oversized editors
- Alternating row shading in tables
- Grid lines visible

---

## Menu Updates

### View Menu
- Toggle Hover Messages (tooltips ON/OFF)
- Persist using QSettings

### Tools Menu
Navigation links to:
- Invoice
- Enter Bills
- Pay Bills
- Receive Checks
- Bank Register
- Chart of Accounts

---

## Known Fixes Required
1. Remove pop-out editors in register (force inline editing)
2. Ensure HOME tab exists and is first
3. Document Intake (invoice AI inbox) is removed from the desktop; Bank Import stays under Reconcile
4. Keep recon toggle always visible (register only)
5. Fix overlapping text in Bank Import UI
6. Maintain static tab structure (no dynamic tab swapping)
7. Ensure background image fills HOME screen

---

## Dev Note
- App must be restarted to see code changes
- Refresh button = UI refresh only (NOT code reload)

---

## Current Priority
1. Clean register behavior (inline editing, layout)
2. Stabilize navigation (tabs + recon toggle)
3. Finalize UI structure before adding logic
4. Keep reconciliation as overlay system

---

## Decision Log / Notes (Authoritative Direction)
There was prior discussion/notes that conflict with this spec (e.g., “no HOME tab” and “Reconcile as a dedicated top-level tab”).  
**This document is the current source of truth.** In particular:
- **HOME tab exists and is first**
- Reconciliation is an **overlay** on the Bank Register via a toggle
- Recon hub tabs (**Bank Import**, **Statement intake (review)**) stay on **Reconcile**; invoice documents use **Create Invoices** / **Invoice Intake**, not Document Intake
