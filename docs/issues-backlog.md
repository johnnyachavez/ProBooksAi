# Issue backlog

> Minimal index — the phased issue table lives in **[BACKLOG.md](BACKLOG.md)**. This file is also **Short index** in the root **[README](../README.md)** **Docs** line and **Doc index (issues-backlog)** in the GitHub **New issue** chooser (**`.github/ISSUE_TEMPLATE/config.yml`**: Contributing guide, **Continuous integration**, Local preview, Desktop app, Default database paths (Windows), Excel workbook template (openpyxl), Running Tests, **Doc index (issues-backlog)**).

The **Doc index (issues-backlog)** contact **`about`** text in **`.github/ISSUE_TEMPLATE/config.yml`** (shown in the GitHub **New issue** chooser) and both **Issues backlog** cards on **`review.html`** should stay aligned with each other and with **ROADMAP** / **BACKLOG** / **CONTRIBUTING** hub lines ([CONTRIBUTING.md — Continuous integration](CONTRIBUTING.md#continuous-integration)).

The **Related docs** / **Other docs** lines on **[ROADMAP.md](ROADMAP.md)**, **[BACKLOG.md](BACKLOG.md)**, and **[CONTRIBUTING.md](CONTRIBUTING.md)** repeat the same **[issues-backlog.md](issues-backlog.md)** hub blurb; keep them verbatim-aligned ([CONTRIBUTING.md — Continuous integration](CONTRIBUTING.md#continuous-integration), **Hub docs — issues-backlog link text**).

The same three hub lines also repeat the same **README — Default database paths** segment (link + CLI vs desktop parenthetical); keep them verbatim-aligned ([CONTRIBUTING.md — Continuous integration](CONTRIBUTING.md#continuous-integration), **Hub docs — README default database paths segment**).

The same three hub lines also repeat the same **README — Python CLI** segment (**`probooks.backup`**, SQLite online backup); keep them verbatim-aligned ([CONTRIBUTING.md — Continuous integration](CONTRIBUTING.md#continuous-integration), **Hub docs — README Python CLI segment**).

**SQLite issue #21** (CLI vs desktop bank DDL): changing **`probooks/migrations/`** or **`probooksai/bank_import.py`** requires updating **`tests/test_issue_21_schema_inventory.py`** per [CONTRIBUTING.md — Continuous integration](CONTRIBUTING.md#continuous-integration) (**SQLite issue #21** bullet).

**SQLite online backup (#28)** / **`probooks.backup`**: changing **`probooks/backup.py`** or CLI/desktop backup wiring should keep **`tests/test_backup.py`**, **`tests/test_probooks_backup_contract.py`**, and the [ROADMAP.md — Implementation snapshot](ROADMAP.md#implementation-snapshot-repository-2026-04) **SQLite online backup (regression)** blurb aligned when behavior or documented guarantees change — [CONTRIBUTING.md — Continuous integration](CONTRIBUTING.md#continuous-integration) (**Module contracts**).

Canonical ordering and GitHub links: **[BACKLOG.md](BACKLOG.md)**.

Install, CLI, desktop, **`review.html`** hub: **[README.md](../README.md#web-shell-review)**.

PySide6 run, **Fusion** dark theme, and **Qt** font stderr note: **[README.md — Desktop app](../README.md#desktop-app-pyside6)**.

**Default database paths** (CLI **`probooks.db`** vs desktop **`probooksai.db`**, **#21**): **[README.md — Default database paths](../README.md#default-database-paths-windows)**.

**Excel COA workbook** (**`generate_workbook.py`**, **openpyxl**): **[README.md — Excel workbook template](../README.md#excel-workbook-template-openpyxl)**.

Shared **Excel** **`--help`** line (**`probooks/help_epilog.py`**; **`python -m probooks`**, **`python -m desktop_app.main`**): **[README.md — Desktop app](../README.md#desktop-app-pyside6)**.

**Backup / restore** (SQLite online backup, **`probooks.backup`**; CLI and desktop **File** menu): **[README.md — Python CLI](../README.md#python-cli)**.

Phased roadmap and in-repo implementation snapshot: **[ROADMAP.md — Implementation snapshot](ROADMAP.md#implementation-snapshot-repository-2026-04)**.

Cross-phase issues (**#21**, packaging, backup UI, theme, CI tests): **[ROADMAP.md — Supporting / cross-cutting](ROADMAP.md#supporting-cross-cutting-issues)**.

Contributing (CI, **contract-test** table, PRs, naming): **[CONTRIBUTING.md](CONTRIBUTING.md#continuous-integration)**.

Optional **GitHub CLI** workspace snapshot (**`integrations/work-context.example.json`**, **`scripts/sync-workspace.ps1`**): **[CONTRIBUTING.md — Running Tests](CONTRIBUTING.md#running-tests)** (**`gh auth login`**, **`gh repo set-default`**).
