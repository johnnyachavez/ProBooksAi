# ProBooks+ai – Implementation Roadmap

> **Last updated:** 2026-04-02  
> This roadmap reflects the MVP-first, bank-centric build order for ProBooks+ai.  
> Each phase maps to one or more focused pull requests.
>
> **Related docs:** [BACKLOG.md](BACKLOG.md) (issue order) · [issues-backlog.md](issues-backlog.md) (short index; **config.yml** chooser + **`review.html`** Issues cards) · [README — Web shell](../README.md#web-shell-review) (install, CLI; **`review.html`** hub) · [README — Desktop app](../README.md#desktop-app-pyside6) (PySide6 theme + Qt notes) · [CONTRIBUTING.md](CONTRIBUTING.md#continuous-integration) (CI, **contract-test** table, PRs, naming) · [CONTRIBUTING — Running Tests](CONTRIBUTING.md#running-tests) (**`sync-workspace.ps1`**, **`work-context.example.json`**) · [In-repo snapshot ↓](#implementation-snapshot-repository-2026-04)
>
> **Note on duplicate issues:** Several features were filed more than once as the backlog grew.
> Where duplicates exist both issue numbers are listed; the higher-numbered one is canonical.
> Older duplicates should be closed with a reference to the canonical issue.

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
- **Always include tests** – add or update tests for any logic change. All tests must pass before requesting a review.
- **Reference the issue** – include `Closes #<n>` or `Refs #<n>` in the PR description.

---

## Implementation snapshot (repository, 2026-04)

The phases below are still the **product roadmap**; this table summarizes what exists **in this repo today** (`probooksai/`, `desktop_app/`).

**Default database paths (Windows):** The `probooks` CLI (`probooks.paths`) and the desktop/intake stack (`probooksai.database.get_data_dir`) still use **two different** per-user locations (`%LOCALAPPDATA%\ProBooks+ai\probooks.db` vs `%APPDATA%\ProBooksAi\probooksai.db`). That split is intentional until a single location is chosen (see [#21](https://github.com/johnnyachavez/ProBooksAi/issues/21)); the repository [README](../README.md#default-database-paths-windows) documents both.

| Roadmap phases | In-repo status |
|---|---|
| 1–5 | SQLite bank + batches + transactions; CSV import with dedupe; reconciliation panel (**Match within** ± tolerance, `QSettings`, drives **Mark Reconciled** + export); Register tab; saved per-account CSV column mapping; bank↔GL cash mapping; **Post selected to GL** (including **split lines → multi-line journal** and **bank-to-bank transfers → two cash GL lines**); **Reports** (trial balance, P&L, balance sheet + **Export CSV…** / `financial_reports.write_report_csv`; **sortable** results grid; amount columns via `FloatSortTableItem` / `table_clipboard` (comma decimals, numeric sort, right-aligned); label columns `plain_display_table_item`; **right-click Copy row** / `table_clipboard`); **Journal** viewer (**Export CSV…** / `GLDatabase.journal_export_rows` + `write_journal_export_csv`; **right-click Copy entry line** on the entry list (`table_clipboard.QLIST_PLAIN_TEXT_ROLE` for verbatim text when the list label is Qt-escaped) + **Copy row** on the **sortable** line-detail table (`plain_display_table_item` for account/description/memo; **Debit**/**Credit** via `NumericAmountTableItem` + right align) / `table_clipboard`); COA editor (**sortable** grid; account **#** via `_CoaAccountNumberTableItem` in `coa_tab.py` — numeric sort when the number is digits-only, else lexicographic; `UserRole` holds account id; `QTABLE_PLAIN_TEXT_ROLE` for **Copy row**; other read-only cells `plain_display_table_item`; **right-click Copy row** as TSV via `desktop_app/table_clipboard`) |
| 6 | **Rules** tab (add / **edit** / delete **with confirmation** / **Export CSV…** / **Import CSV…** replace-all) + `write_rules_csv` / `read_rules_csv` / `import_rules_replace`; rules grid: **sortable** columns (numeric **Priority** via `IntSortTableItem` / `table_clipboard` + plain copy role), **double-click** / **Return**/**Enter** → edit, **right-click** (**Edit**, **Delete**, **Copy row**), rule id on row `UserRole` (edit/delete correct when sorted); **header widths** in `QSettings` (show/hide + nested Business sub-tab switch); rules on CSV/PDF import; **Register COA dropdown hints** (★ rule matches + optional **OpenAI** top picks when `OPENAI_API_KEY` is set, `probooksai/coa_ai_suggest.py`) |
| 7 | **Digital PDF** (text layer): **Import PDF…** on Bank Import + `statement_pdf` / `statement_extract` + `pypdf` (dev/optional extra). **Not implemented:** scanned PDF / photo **OCR/vision**, Issue #11 fixture, end-to-end vision test |
| 8–13 | **Business** tab: nested **Rules / AR / AP / Payroll / Tax %** bar remembers **last selected** sub-tab (`QSettings`); **New customer** / **New vendor** (full contact + notes, vendor **1099**); **New invoice** (optional due + memo; last **customer** remembered); **New bill** (vendor inv. #, due, memo, attachment **Browse…**; last **vendor** remembered); **Edit** customer/vendor/invoice (no payments on inv.) / bill (no payments); **Edit invoice** line-items grid (**Rate** `_FloatSortTableItem`, right-aligned; not sortable to preserve line order) + **Record** AR/AP payment **Apply** tables **sortable** (**Balance** column `_FloatSortTableItem` / `table_clipboard`, comma decimals, right-aligned); **right-click Copy row** (TSV; **Apply** amounts via `table_clipboard` cell-widget text; invoice/bill list + rules + non-balance apply columns use `plain_display_table_item` where text may contain `&`); **Copy invoice #** uses `table_cell_clipboard_text`; invoice/bill **#** column sets ``UserRole`` to DB id (alongside ``IntSortTableItem`` / ``table_clipboard``) so **Edit** / PDF / context actions resolve the correct row when the grid is sorted; double-click invoice/bill row opens **Edit**; **Return**/**Enter** on the focused grid does the same; **Right-click** context menu (**Edit**, **Copy row** as TSV; AR also **Save invoice PDF**, **Copy invoice #**; AP also **Open attachment…** when a bill has a stored path, via OS default app); **Record** payments (`record_ar_payment`, `record_ap_payment`, `list_open_invoices_for_customer`, `list_open_bills_for_vendor`, optional **Deposit to bank** on AR / **Paid from bank** on AP; last **customer**/**vendor**/**bank** per flow via `QSettings`); **Save invoice PDF** (memo, status, due in layout; HTML via `probooksai/html_escape.escape_html_text`); list CSV exports + **AR / AP payments** (`write_ar_payments_csv`, `write_ap_payments_csv`) + **payment allocation lines** (`write_ar_payment_allocations_csv`, `write_ap_payment_allocations_csv`); **Export invoices / bills CSV** asks **visible only** vs **all** when a grid filter is active (`write_invoices_csv` / `write_bills_csv` optional id lists); invoice/bill grids: **Filter** line (multi-token match on id + key columns including **memo**; AR also **subtotal** / **tax_total**; AP also **attachment_path** (filename/path); text **remembered** via `QSettings` per sub-tab; **Find** / Ctrl+F focuses filter while on that AR or AP sub-tab), **click column headers to sort** (numeric-aware **#** / **Total** / **Balance** via `IntSortTableItem` / `FloatSortTableItem` (`table_clipboard`), escaped display + `QTABLE_PLAIN_TEXT_ROLE` for **Copy row**), **column widths** restored on show / saved on hide or when switching nested **Business** sub-tabs (`QHeaderView` state in `QSettings`), **Due** + **Status**, footer **totals on visible rows** (count, sum of totals, sum of balance due, “hidden by filter” hint); **customer/vendor pickers** in **Edit** / **New invoice**/**bill** / **Record payment** dialogs: **Filter list** field + `probooksai/business_list_filter.filter_entity_rows` (vendors: **1099** token matches 1099 vendors; edit invoice/bill keeps current entity visible when filtered out); aging CSV (**As of** date picker + **As of** column; **AP** includes **Days past due**; **bucket total** summary rows at end) |
| 14–16 | **Tax %** tab: default rate + **tax name** setting; standard **Save** shortcut (e.g. **Ctrl+S**) saves settings when that sub-tab has focus; **Export sales tax summary CSV** (invoice-date range, total collected + line detail); **Payroll** sub-tab: pay run grid **sortable** (numeric **Run #**, **Gross**/**Ded**/**Net**, **JE #**; sort item types set `QTABLE_PLAIN_TEXT_ROLE`), **double-click** / **Return**/**Enter** → **Tax lines for run**, **right-click** (**Tax lines**, **Post to GL**, **Copy row**), run id on row `UserRole` + **header widths** in `QSettings`; payroll runs + **Post selected run to GL**; **Phase 16 payroll tax** items, per-run lines, **Export tax report CSV**; **Payroll tax codes** dialog (**sortable**; **Sort** column `_IntSortTableItem`) + **Tax lines for run** dialog (**sortable** table; **Copy row** TSV via `_attach_table_copy_row_menu` / `table_clipboard`, including **QDoubleSpinBox** amounts; code/name via `plain_display_table_item`) |
| 17–20 | Register: **filters** (needs receipt / has attachment / missing file / **has or no payment link**), receipt flags, **attach path**, **transfer to** account (with **GL posting** between mapped cash accounts), **Splits** editor, **Link payment** (AR/AP/**payroll run**): **suggested matches** by amount+date, **clear link**, **Match** column + export; **Link** dialog suggested-match list **right-click Copy suggestion line** (`copy_qlistwidget_row_text` + `QLIST_PLAIN_TEXT_ROLE` verbatim label); excludes already-linked records (`suggest_bank_match_candidates`, `unlink_bank_transaction`); **right-click** row **Open attachment…** (`desktop_app/open_attachment.open_local_attachment` + `BankDatabase.get_transaction`), **Copy row** (TSV via `table_clipboard`; **COA** column uses embedded combo ``userData`` when set so copied TSV has the raw account string, not Qt-escaped label text; **date** / **payee** / **posted** ref+memo use `plain_display_table_item`; **sortable** grid (reload toggles sorting; txn id on **Date** ``UserRole``); **debit** / **credit** / **balance** via `NumericAmountTableItem` (comma + `QTABLE_PLAIN_TEXT_ROLE`; **balance** stays chronological, not by column sort); **unposted** ref+memo stay raw `QTableWidgetItem` for inline edit) |
| 21 | CSV import on **worker thread** with **progress dialog + cancel** (`desktop_app/csv_import_worker.py`) |
| 22 | Register **Export CSV** (respects active filter); Bank Import **Export reconciliation report CSV** per batch; **Journal** / **Reports** export CSV; **Business** AR/AP **customers / invoices / vendors / bills** + **payments** + **payment→invoice/bill allocation** CSV (invoice/bill list export: **visible vs all** when grid filter is set); **Excel COA workbook** via **`generate_workbook.py`** / **`probooksai/generator.py`** (**`openpyxl`** in **`pyproject.toml`**; **README** **Excel workbook template**) |
| 23–24 | **Audit log** tab (filter by entity type + id; **Export CSV…** via `probooksai/audit_log.write_audit_csv`; **sortable** log grid (**Entity ID** via `table_clipboard.IntSortTableItem`); **right-click Copy row** (TSV) on the log grid / `table_clipboard`; types include **bank_import_batch** after **Mark reconciled**); **View change history…** context menu on **Register**, **Bank Import** (batch list + **imported transactions**), and **COA** rows (`desktop_app/audit_dialog.py`; **sortable** history grid + **Copy row** (TSV)); **Register** / **Bank Import** (**batch list** + imported txns + **Manage Accounts** list) / **COA** row menus also **Copy row** (TSV); **Bank Import** imported-transaction rows also **Open attachment…** (same helper as Register/AP bill); bank txn + **COA** CRUD; **`--database PATH`** / **`--version`**; **Open/New company**; **Backup** / **Restore** (Issue #28); **File → Copy company database path** (**Ctrl+Alt+P**) copies resolved **`.db`** path to clipboard; **window title** + top **banner** show active company file name on switch; ``&`` escaped via `qt_mnemonic.escape_ampersand_for_qt` in title/banner, **status bar** (ready + company lines with literal “drag & drop”, company path, copied path, import/AI filenames/errors), Intake filename + PDF preview basename, skipped-import and roadmap-open warnings, **Open/New company** / **backup** / **restore** path dialogs and OS errors, and **Business** tab (`desktop_app/extra_tabs.py`) rules delete confirmation, rules import/export, invoice PDF save, AR/AP/Payroll/Tax **QMessageBox** paths and exception text, **Tax %** “tax name” row label, filtered entity/bank + payroll GL/employee **QComboBox** labels; **Register** (`register_tab.py`: export basename, posting summary, memo/COA/splits/transfer errors, **Link** dialog “Current link” label, bank-account + per-row **COA** + transfer + **Link payment** combo/list **display** text + **Match** column), **Journal** (`journal_tab.py`: entry-list line text + journal line-detail **Copy row** via `plain_display_table_item`) / **Audit** / **Reports** export paths + **OSError** text + **Reports** tab P&L summary **QLabel** hints, **Bank Import** (`bank_import_tab.py`: **Map CSV Columns** escaped header labels + raw `userData`, **Statement Period & Balances** window title, account picker + **Manage Accounts** GL cash combo **display** vs `userData` + **Manage Accounts** type column / import **batch list** / **TransactionsTable** date/description/ref via `plain_display_table_item`, **Amount** via `NumericAmountTableItem` (numeric sort + `QTABLE_PLAIN_TEXT_ROLE` for copy), PDF/CSV read + PDF error + worker **Import failed** + reconciliation export + **Manage Accounts** delete confirm; **Manage Accounts** + import **batch** lists are **sortable** (row selection uses account/batch id, not row index)), **COA** add/edit **Error** + deactivate **question** (`coa_tab.py`), **`open_attachment`** dialog title + empty message + “file not found” path; **`audit_dialog`** window title + empty-state label; **Intake** tab **sortable** document list **Copy row** (TSV; **#** via `IntSortTableItem` + ``UserRole`` for numeric sort and **selected** row id; other cells `plain_display_table_item`; ``table_cell_clipboard_text`` fallback for id); detail pane filename / preview placeholder / AI **rationale** as **PlainText**; **COA Account** combo (`DetailPane` in `main.py`): escaped row labels + raw `userData`, **Approve** saves via `currentData` or typed line-edit text; status line **RichText** with **escaped** status (`escape_html_text`); **View** menu **Ctrl+1–8** switch main tabs (Intake → Audit); **Help → Product roadmap (local file)** opens `docs/ROADMAP.md` (`desktop_app/local_docs.py` + `QDesktopServices`); desktop **About** + **`probooks.__version__`** track `probooks-ai` metadata (`desktop_app/version.py`); PyInstaller scripts output **ProBooksPlusAi** with **`--paths`** + **probooksai** + **desktop_app** + **`docs`** bundle; **`pyproject.toml`** wheel includes **`probooksai`** + **`probooks`**; CI **wheel build** check; GitHub Actions pytest installs **`.[ci]`** (`pyproject.toml`: pytest + pypdf + PySide6) and sets **`QT_QPA_PLATFORM=offscreen`** so **PySide6** tests run headless (`tests/test_table_clipboard.py`; invoice PDF smoke runs in a **subprocess** on non-Windows so a Qt crash cannot abort pytest, **skipped on Windows** where some Qt builds abort with `0xC0000409`) |

---

## Current Status

Open issues and pull requests change on GitHub continuously. Use **[Issues](https://github.com/johnnyachavez/ProBooksAi/issues)** and **[Pull requests](https://github.com/johnnyachavez/ProBooksAi/pulls)** for live state. **[BACKLOG.md](BACKLOG.md)** orders planned epics; the **[implementation snapshot](#implementation-snapshot-repository-2026-04)** (above) describes what is already in this repository.

---

## Phased Roadmap

### Phase 1 – Data Foundations ✅ (baseline)

Establish the core data model so every subsequent phase has a stable place to write.

- `chart_of_accounts` table (48 accounts, COA helpers in `probooksai/coa.py`)
- `bank_accounts` table – one row per real bank account with name, type, and currency
- `bank_transactions` table – signed amounts (negative = debit/out, positive = credit/in)
- `bank_import_batches` table – tracks each import session (file name, account, timestamps)

**Related issues:** [#30](https://github.com/johnnyachavez/ProBooksAi/issues/30) (Bank Accounts CRUD), [#27](https://github.com/johnnyachavez/ProBooksAi/issues/27) (Schema versioning)

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

**Related issues:** [#31](https://github.com/johnnyachavez/ProBooksAi/issues/31) / [#32](https://github.com/johnnyachavez/ProBooksAi/issues/32) (per-account import flow), [#33](https://github.com/johnnyachavez/ProBooksAi/issues/33) (import validation), [#34](https://github.com/johnnyachavez/ProBooksAi/issues/34) (transaction model improvements), [#35](https://github.com/johnnyachavez/ProBooksAi/issues/35) (duplicate detection)

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

**Related issues:** [#36](https://github.com/johnnyachavez/ProBooksAi/issues/36) (running balance + footer totals)

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

**Related issues:** [#37](https://github.com/johnnyachavez/ProBooksAi/issues/37) (statement period capture), [#38](https://github.com/johnnyachavez/ProBooksAi/issues/38) (reconciliation computation), [#39](https://github.com/johnnyachavez/ProBooksAi/issues/39) (mark-reconciled gating)

**Definition of done**
- User can open a reconciliation panel, enter statement period, and see computed difference.
- "Mark Reconciled" button is disabled until difference is within tolerance.
- Reconciled batches shown with a ✓ badge in the import history list.

---

### Phase 5 – Posting to General Ledger

Move from bank-only view to full double-entry accounting.

- **Bank account ↔ GL account mapping** – link each bank account to a cash/control GL account.
- Each bank transaction gets a "Post to GL" action that creates a matching `Journal_Entry` pair.
- Debit/credit side auto-suggested from the COA mapping on the transaction.
- Prevents double-posting (posted flag on `bank_transactions`).
- **COA editor** – minimal UI to view and rename chart-of-accounts entries.
- **GL register viewer** – drill-down into posted journal entries from the register.
- **Reports (MVP)** – Trial Balance, simple P&L, Balance Sheet.

**Related issues:** [#24](https://github.com/johnnyachavez/ProBooksAi/issues/24) (posting engine), [#40](https://github.com/johnnyachavez/ProBooksAi/issues/40) (posting engine MVP), [#41](https://github.com/johnnyachavez/ProBooksAi/issues/41) (COA editor), [#42](https://github.com/johnnyachavez/ProBooksAi/issues/42) (bank↔GL mapping), [#43](https://github.com/johnnyachavez/ProBooksAi/issues/43) (GL register viewer), [#44](https://github.com/johnnyachavez/ProBooksAi/issues/44) (reports MVP)

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

**Related issues:** [#51](https://github.com/johnnyachavez/ProBooksAi/issues/51) / [#79](https://github.com/johnnyachavez/ProBooksAi/issues/79) (rule-based auto-categorization — #79 is canonical)

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

### Phase 8 – Invoicing / AR (MVP)

Create and manage customer invoices (Accounts Receivable).

- **Customer list** – name, email, phone, billing address, notes.
- **Invoice** – invoice number, date, due date/terms, customer, memo, line items (description, qty, rate, line total).
- **Computed totals** – subtotal, tax placeholder, total, balance due.
- **PDF export** – clean, printable invoice layout.
- Store invoices and customers in SQLite.

**Related issues:** [#56](https://github.com/johnnyachavez/ProBooksAi/issues/56) / [#66](https://github.com/johnnyachavez/ProBooksAi/issues/66) (Invoicing MVP — #66 is canonical)

**Definition of done**
- User can create an invoice with 1–10 line items; totals calculate correctly.
- Invoice persists and can be reopened/edited.
- User can export the invoice to PDF.

---

### Phase 9 – Receive Payments (AR)

Apply customer payments against open invoices.

- **Payment entry** – date, amount, method, reference #, memo.
- Select customer and apply payment to one or more open invoices.
- Update `balance_due` and status (`Unpaid` / `Partially Paid` / `Paid`) on each invoice.
- Optional: deposit-to account selection (bank/cash GL account) for later bank matching.

**Related issues:** [#57](https://github.com/johnnyachavez/ProBooksAi/issues/57) / [#67](https://github.com/johnnyachavez/ProBooksAi/issues/67) (Receive Payments — #67 is canonical)

**Definition of done**
- Partial and full payments work; invoice balances update correctly and persist.

---

### Phase 10 – AR Aging Report

Show outstanding receivables bucketed by age.

- Compute aging by invoice due date vs "as of" date.
- Buckets: Current / 1–30 / 31–60 / 61–90 / 91+.
- Group by customer; show totals per bucket.
- Allow CSV export.

**Related issues:** [#58](https://github.com/johnnyachavez/ProBooksAi/issues/58) / [#68](https://github.com/johnnyachavez/ProBooksAi/issues/68) (AR Aging — #68 is canonical)

**Definition of done**
- Buckets calculate correctly for test data; matches manual aging check.

---

### Phase 11 – Bills / AP (MVP)

Enter and track vendor bills (Accounts Payable).

- **Vendor list** – name, email, phone, mailing address, notes, 1099 flag.
- **Bill** – vendor invoice number, bill date, due date/terms, memo, total (line items optional in MVP).
- Attach vendor invoice PDF/image to each bill.
- Store bills and vendors in SQLite.

**Related issues:** [#59](https://github.com/johnnyachavez/ProBooksAi/issues/59) / [#69](https://github.com/johnnyachavez/ProBooksAi/issues/69) (Bills AP MVP — #69 is canonical)

**Definition of done**
- User can enter a bill and attach the vendor invoice; bill persists and can be reopened/edited.

---

### Phase 12 – Pay Bills (AP)

Record payments against open vendor bills.

- **Payment entry** – date, amount, method, reference #, memo.
- Select vendor and apply payment across one or many bills.
- Update bill balance and status (`Unpaid` / `Partially Paid` / `Paid`).
- Choose bank account (paid-from) for later bank matching/posting.

**Related issues:** [#60](https://github.com/johnnyachavez/ProBooksAi/issues/60) / [#70](https://github.com/johnnyachavez/ProBooksAi/issues/70) (Pay Bills AP — #70 is canonical)

**Definition of done**
- Partial and full bill payments work; bill balances and statuses update correctly.

---

### Phase 13 – AP Aging Report

Show outstanding payables bucketed by age.

- Compute aging by bill due date vs "as of" date.
- Buckets: Current / 1–30 / 31–60 / 61–90 / 91+.
- Group by vendor; show totals per bucket.
- Allow CSV export.

**Related issues:** [#61](https://github.com/johnnyachavez/ProBooksAi/issues/61) / [#71](https://github.com/johnnyachavez/ProBooksAi/issues/71) (AP Aging — #71 is canonical)

**Definition of done**
- Buckets calculate correctly for test data; matches manual aging check.

---

### Phase 14 – Sales Tax Settings & Invoice Tax

Add sales tax to invoices.

- **Tax settings** – default tax rate (single rate MVP), tax name (e.g., "CA Sales Tax").
- **Invoice tax** – taxable flag per invoice (MVP) or per line; compute `tax_total` and `total`.
- **Sales tax summary report** – tax collected for a date range.

**Related issues:** [#62](https://github.com/johnnyachavez/ProBooksAi/issues/62) / [#72](https://github.com/johnnyachavez/ProBooksAi/issues/72) (Sales Tax — #72 is canonical)

**Definition of done**
- Invoice tax calculation is correct and consistent.
- Sales tax summary matches sum of invoice tax totals for range.

---

### Phase 15 – Payroll (MVP)

Record employee pay runs and post wages to GL.

- **Employees** – name, address, pay type (hourly/salary), rate, withholdings placeholders.
- **Pay run** – pay period start/end, pay date, gross pay (MVP), basic deductions placeholders, net pay computed.
- **GL posting** – create journal entries for wages expense and bank/cash payment (MVP); hold tax/withholding liabilities as placeholder accounts.

**Related issues:** [#63](https://github.com/johnnyachavez/ProBooksAi/issues/63) / [#73](https://github.com/johnnyachavez/ProBooksAi/issues/73) (Payroll MVP — #73 is canonical)

**Definition of done**
- User can create an employee and a pay run; net pay computes and posts to GL (balanced entry).

---

### Phase 16 – Payroll Taxes (Placeholder Framework)

Track payroll tax obligations at a framework level.

- Configurable payroll tax items (federal/state placeholders).
- Track employer vs employee portions per pay run.
- Report totals owed for a date range.

**Related issues:** [#64](https://github.com/johnnyachavez/ProBooksAi/issues/64) / [#74](https://github.com/johnnyachavez/ProBooksAi/issues/74) (Payroll Taxes — #74 is canonical)

**Definition of done**
- System can store and report payroll tax totals even if calculations are manual initially.

---

### Phase 17 – Bank Matching (Link Bank Transactions to AR/AP/Payroll)

Connect reconciled bank transactions to recorded payments.

- Allow linking a bank transaction to: invoice payment, bill payment, or payroll payment.
- Matching UI: suggestions by amount/date (MVP).
- Mark matched items; prevent double-linking.
- Matched items show linked references and are filterable.

**Related issues:** [#52](https://github.com/johnnyachavez/ProBooksAi/issues/52) / [#65](https://github.com/johnnyachavez/ProBooksAi/issues/65) / [#75](https://github.com/johnnyachavez/ProBooksAi/issues/75) (Bank Matching — #75 is canonical)

**Definition of done**
- User can match a bank transaction to a recorded payment; matched items show linked references.

---

### Phase 18 – Transaction Splits

Split one bank transaction across multiple categories.

- Split lines store: `transaction_id`, `amount`, `category (COA)`, optional memo.
- Parent transaction amount must equal `SUM(split amounts)`.
- Posting engine posts split lines to produce balanced GL entries.

**Related issues:** [#49](https://github.com/johnnyachavez/ProBooksAi/issues/49) / [#77](https://github.com/johnnyachavez/ProBooksAi/issues/77) (Transaction Splits — #77 is canonical)

**Definition of done**
- User can split a transaction into multiple categories; posting produces balanced GL entries.

---

### Phase 19 – Transfer Transactions (Bank-to-Bank Moves)

Handle internal transfers between bank accounts.

- UI to mark a transaction as "Transfer to/from" another bank account.
- Accounting rule: transfers do not hit income/expense accounts.
- Posting debits one bank GL account and credits the other.

**Related issues:** [#50](https://github.com/johnnyachavez/ProBooksAi/issues/50) / [#78](https://github.com/johnnyachavez/ProBooksAi/issues/78) (Transfers — #78 is canonical)

**Definition of done**
- Transfer transactions affect only the two bank accounts; GL entries remain balanced.

---

### Phase 20 – Receipt / Document Workflow

Attach receipts and source documents to bank transactions.

- **"Needs receipt" flag** on bank transactions.
- Register filters: needs-receipt, has-attachment.
- Attachment indicator/icon visible in the register row.
- Quick-attach action from the register row.

**Related issues:** [#45](https://github.com/johnnyachavez/ProBooksAi/issues/45) (attachments for bank transactions), [#80](https://github.com/johnnyachavez/ProBooksAi/issues/80) (receipt workflow improvements)

**Definition of done**
- User can filter to missing receipts quickly; attachments are obvious and easy to add.

---

### Phase 21 – Performance: Large CSV Imports

Keep the UI responsive for large files.

- Move CSV parsing and DB writes off the UI thread (worker/background task).
- Progress UI: rows processed / total rows; optional time estimate.
- Allow cancel (best-effort; stop after current chunk).
- Use chunked inserts/transactions for speed.

**Related issues:** [#48](https://github.com/johnnyachavez/ProBooksAi/issues/48) / [#76](https://github.com/johnnyachavez/ProBooksAi/issues/76) (Large CSV imports — #76 is canonical)

**Definition of done**
- Large imports keep the UI responsive; user sees progress and can cancel.

---

### Phase 22 – Export Tools

Export data to CSV and generate reconciliation reports.

- Export the current register view to CSV (respects active filters and selected account).
- Reconciliation report per batch: statement period, beginning/ending balances, expected ending, difference, included transaction list.
- Exports include totals and consistent date/amount formatting.

**Related issues:** [#54](https://github.com/johnnyachavez/ProBooksAi/issues/54) / [#82](https://github.com/johnnyachavez/ProBooksAi/issues/82) (Export Tools — #82 is canonical)

**Definition of done**
- Exported CSV matches what's on screen; reconciliation report matches the computed reconciliation panel.

---

### Phase 23 – Audit Log (Change History)

Record who changed what and when.

- Track changes for: bank transactions, batches, reconciliations, postings, COA changes.
- Store: `entity_type`, `entity_id`, `field`, `old_value`, `new_value`, `changed_at`.
- UI: "View history" on a transaction and/or batch.

**Related issues:** [#53](https://github.com/johnnyachavez/ProBooksAi/issues/53) / [#81](https://github.com/johnnyachavez/ProBooksAi/issues/81) (Audit Log — #81 is canonical)

**Definition of done**
- User can see what changed and when for a transaction; changes persist and are queryable.

---

### Phase 24 – Multi-company / Multiple Books

Support more than one set of books in the same installation.

- Multiple "company files" stored as separate SQLite DBs.
- UI: `File → New Company…` / `File → Open Company…`; show current company in the window header.
- Each company has its own bank accounts, transactions, COA, GL, invoices, and bills.
- Switching company fully reloads data without data leakage between companies.

**Related issues:** [#55](https://github.com/johnnyachavez/ProBooksAi/issues/55) / [#83](https://github.com/johnnyachavez/ProBooksAi/issues/83) (Multi-company — #83 is canonical)

**Definition of done**
- Switching company fully switches data (with or without a controlled restart); no data leakage.

---

## Supporting / Cross-cutting Issues

The following issues are not tied to a single phase but must be addressed alongside the main phases:

| Issue | Title | Phase dependency |
|---|---|---|
| [#26](https://github.com/johnnyachavez/ProBooksAi/issues/26) / [#46](https://github.com/johnnyachavez/ProBooksAi/issues/46) | Release packaging (Windows installer + versioning) | After Phase 5 (GL posting complete) |
| [#28](https://github.com/johnnyachavez/ProBooksAi/issues/28) | Backup / restore database from the UI | After Phase 1 |
| [#29](https://github.com/johnnyachavez/ProBooksAi/issues/29) | Dark theme (global palette + tables) | Any phase |
| [#47](https://github.com/johnnyachavez/ProBooksAi/issues/47) | CI tests for banking + posting | Alongside each phase |

---

## Out of Scope (for now)

| Feature | Reason deferred |
|---|---|
| Multi-currency / FX | Complex FX logic; not needed for MVP |
| Fixed-asset depreciation | Requires amortisation schedules |
| Google Apps Script version | Different runtime; separate project |
| Budget vs. Actual | Reporting layer; needs full GL data first |

---

*Setup and contribution links are listed in the introduction above.*
