# ProBooks+ai

Accounting app foundation: **dark UI shell** (static HTML), **`probooks` CLI**, **PySide6 desktop**, and **Excel COA workbook** (**`openpyxl`**) — **Python + SQLite** with migrations.

**Docs:** [Issue backlog](docs/BACKLOG.md) · [Short index](docs/issues-backlog.md) · [Roadmap / snapshot](docs/ROADMAP.md#implementation-snapshot-repository-2026-04) · [Cross-phase (#21)](docs/ROADMAP.md#supporting-cross-cutting-issues) · [Contributing](docs/CONTRIBUTING.md#continuous-integration) · [Running Tests](docs/CONTRIBUTING.md#running-tests) · [Default DB paths](#default-database-paths-windows) · [Desktop app](#desktop-app-pyside6) · [Excel workbook](#excel-workbook-template-openpyxl)

## Web shell (review)

```bash
python -m http.server 8765
```

Open [http://127.0.0.1:8765/review.html](http://127.0.0.1:8765/review.html) — hub to **`index.html`**, **`invoice.html`**, raw **BACKLOG** / **issues-backlog** / **ROADMAP** (**implementation snapshot** and **Supporting / cross-cutting** anchors), and GitHub shortcuts (rendered docs on **github.com** after you push).

## Python CLI

You can run **`python -m probooks`** instead of **`probooks`** if the console script is not on your `PATH`. Use **`python -m probooks --help`** (or **`probooks --help`**) for subcommands and the note on default database paths.

```bash
pip install -e ".[dev]"
probooks status
probooks migrate
probooks accounts list
probooks accounts add --name "Checking" --type checking --institution "Chase" --last4 1234
probooks backup --output ./backups/demo-backup.db
probooks restore --input ./backups/demo-backup.db --yes
```

### CSV import (issues #31, #33, #34)

Prepare a CSV with at least **date** and **amount** columns (0-based indices). A small demo file lives at **`examples/sample_bank.csv`** (CI asserts it is present; **pytest** imports it with the same column map as the example below). Example:

```bash
probooks import csv --account 1 --file examples/sample_bank.csv --skip-rows 1 --date-col 0 --amount-col 1 --payee-col 2 --errors-out import-errors.csv
python -m probooks transactions --account 1 --limit 20
```

Skipped rows (bad date/amount) go to `--errors-out` when set; amounts support `$`, commas, and `(123.45)` as negative.

### Excel workbook template (openpyxl)

```bash
pip install -e .
python generate_workbook.py
```

Writes `ProBooksAi_Accounting.xlsx` in the working directory (legacy default filename; see `probooksai.generator`). CI asserts **`generate_workbook.py`** is present in the repo root.

**`--help`** on **`python -m probooks`** or **`python -m desktop_app.main`** prints the same **Excel COA workbook** sentence from **`probooks/help_epilog.py`**; see [Desktop app](#desktop-app-pyside6) for the PySide6 run line and **Qt** notes.

### Default database paths (Windows)

- **`probooks` CLI** (`probooks.paths`): `%LOCALAPPDATA%\ProBooks+ai\probooks.db`
- **Document intake / desktop default file** when no path is passed (`probooksai.database.get_data_dir`): `%LOCALAPPDATA%\ProBooks+ai\probooksai.db` (same per-user folder as the CLI; if you already had data under `%APPDATA%\ProBooksAi\`, it is copied here once on first access)
- **Two files, two schemas:** `probooks.db` and `probooksai.db` are not interchangeable — the CLI and desktop use different migration layouts until [issue #21](https://github.com/johnnyachavez/ProBooksAi/issues/21). See **Why not one `.db` yet** in [docs/ROADMAP.md — Implementation snapshot](docs/ROADMAP.md#implementation-snapshot-repository-2026-04).
- **Bank DDL inventory (tests):** `tests/test_issue_21_schema_inventory.py` lists user SQLite tables for the CLI migrations vs desktop `BankDatabase` today; update it when editing `probooks/migrations/` or `probooksai/bank_import.py` ([CONTRIBUTING — Continuous integration](docs/CONTRIBUTING.md#continuous-integration), **SQLite issue #21** bullet).

## Desktop app (PySide6)

```bash
pip install -e ".[desktop]"
python -m desktop_app.main
```

Optional: `python -m desktop_app.main --database PATH` (otherwise last company path from settings, then the default file from `get_data_dir`; see **Default database paths** above). For headless tests or CI parity, use **`.[ci]`** and set **`QT_QPA_PLATFORM=offscreen`** (see **Tests** below).

**`--help`** on **`python -m probooks`** and **`python -m desktop_app.main`** prints the same **Excel COA workbook** line (string in **`probooks/help_epilog.py`**; points at **`generate_workbook.py`** and the [Excel workbook template](#excel-workbook-template-openpyxl) section below).

The app uses a **Fusion**-based dark theme (`desktop_app/theme.py`). Main areas include **Document intake**, **Bank import** (CSV + reconciliation; **F5** reload when that tab has focus), and **Bank register** (grid-style table, chronological transactions per account, debit/credit, running balance, **Clr** column **C**/batch-**R** with header and row **tooltips**, filters including cleared and batch reconciliation, double-click **Clr** to toggle cleared, **F5** refresh, **Ctrl+Shift+G** post selected to GL, **Ctrl+Shift+C** / **Ctrl+Shift+U** mark cleared / clear cleared, **Ctrl+Shift+E** export CSV with Register focus, **tooltips** on **Refresh** / **Post** / **Export** / cleared actions, **Help** → **Bank register keyboard shortcuts…** / **right-click** grid **Keyboard shortcuts…**, COA assignment, post-to-GL; **filter, last bank account, and column widths persist per company SQLite file** via `QSettings`) — see `desktop_app/bank_import_tab.py` and `desktop_app/register_tab.py`. On some **Windows** builds **Qt** may log a harmless **`QFont::setPointSize`** line at startup; `desktop_app/main.py` installs a narrow **Qt** message filter for that text before **`QApplication`** is constructed. Contract coverage: `tests/test_desktop_main_contract.py` and **CONTRIBUTING.md** (contract tests table).

## Issue-driven build order

See [docs/BACKLOG.md](docs/BACKLOG.md) for phased GitHub issues and [docs/ROADMAP.md — implementation snapshot](docs/ROADMAP.md#implementation-snapshot-repository-2026-04) for the phased roadmap and what the repo ships today in **`desktop_app/`**, the **`probooks`** CLI, and root **`generate_workbook.py`** ([Excel COA workbook template](#excel-workbook-template-openpyxl)). [Supporting / cross-cutting issues](docs/ROADMAP.md#supporting-cross-cutting-issues) (**#21**, packaging, backup UI, theme, CI tests) tracks cross-phase work in the same file. **#21 / #27 / #28** (storage + migrations + backup) and **#30** (bank accounts) are part of that foundation, not the whole surface.

## Tests

```bash
pip install -e ".[ci]"
pytest
```

The **`.[ci]`** extra (see `pyproject.toml`) matches the GitHub Actions **python** job: **pytest**, **pypdf**, and **PySide6** so the full suite runs, including `tests/test_table_clipboard.py` and the invoice PDF smoke test in `tests/test_extensions_business.py` (PDF export runs in a **subprocess** on non-Windows so a Qt crash cannot kill pytest; on **Windows** that test is **skipped** because some Qt builds abort with `0xC0000409`—Linux CI still exercises it). Equivalent to **`.[dev,desktop]`** for those dependencies. CI sets **`QT_QPA_PLATFORM=offscreen`** for headless Qt; use the same on Linux without a display if you see platform plugin errors. For workflow filenames and the optional UI screenshot job, see [Continuous integration](docs/CONTRIBUTING.md#continuous-integration) in **CONTRIBUTING.md**.

## Scripts (`scripts/`)

- **`ci_validate_layout.sh`** / **`ci_validate_layout.ps1`** — Same required-path checks as the CI **validate** job. From the repo root: `bash scripts/ci_validate_layout.sh` (Git Bash / WSL / Unix) or **`.\scripts\ci_validate_layout.ps1`** (Windows PowerShell). Keep **both** files in sync when you add or reorder **`require`** paths (hub HTML, contract tests, **`tests/conftest.py`**, **README**, …); **`.github/workflows/ci.yml`** invokes the **`.sh`** script on Linux runners.
- **`build_desktop.ps1`** / **`build_desktop.sh`** — PyInstaller build for the desktop app (output name **ProBooksPlusAi**).
- **`sync-workspace.ps1`** — Optional local snapshot of repo + GitHub issues/PRs into **`integrations/work-context.json`** (requires [GitHub CLI](https://cli.github.com/) and `gh auth login`). The committed **`integrations/work-context.example.json`** documents the minimal shape: exactly four **`localWorkFiles`** paths — **`index.html`**, **`invoice.html`**, **`review.html`**, **`docs/ROADMAP.md`** — enforced by **`tests/test_integrations_example_contract.py`**. Generated JSON lists every repo file and may add extra PR/issue fields from **`gh`** (see script **`.DESCRIPTION`**).
- **`capture_ui_screenshot.py`** — Headless main-window capture (see script docstring); writes under **`artifacts/`** (gitignored). Pull requests also trigger **`.github/workflows/ui-screenshot.yml`** (non-blocking; posts a comment with the artifact link).

## Contributing

Conventions, labels, CI, the **contract-test** table, and shared pytest fixtures (**`tests/conftest.py`**): [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) — [Continuous integration](docs/CONTRIBUTING.md#continuous-integration).
