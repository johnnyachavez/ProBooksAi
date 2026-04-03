---
name: Bug report
about: Report a defect
title: "[Bug] "
labels: bug
---

**Triaging:** [ROADMAP.md — Implementation snapshot](https://github.com/johnnyachavez/ProBooksAi/blob/main/docs/ROADMAP.md#implementation-snapshot-repository-2026-04) (phased scope + what ships in-repo) · [ROADMAP.md — Supporting / cross-cutting](https://github.com/johnnyachavez/ProBooksAi/blob/main/docs/ROADMAP.md#supporting-cross-cutting-issues) (**#21**, packaging, backup UI, theme, CI tests) · [BACKLOG.md](https://github.com/johnnyachavez/ProBooksAi/blob/main/docs/BACKLOG.md) (issue order / duplicates) · [issues-backlog.md](https://github.com/johnnyachavez/ProBooksAi/blob/main/docs/issues-backlog.md) (short doc index) · [README — Web shell](https://github.com/johnnyachavez/ProBooksAi/blob/main/README.md#web-shell-review) (`review.html`, static UI hub) · [README — Python CLI](https://github.com/johnnyachavez/ProBooksAi/blob/main/README.md#python-cli) (**`probooks.backup`**, SQLite online backup; **#28** **`tests/test_backup.py`**, **`tests/test_probooks_backup_contract.py`**) · [README — Desktop app](https://github.com/johnnyachavez/ProBooksAi/blob/main/README.md#desktop-app-pyside6) (PySide6 run + theme; **File → Backup** / **Restore**) · [README — Default database paths](https://github.com/johnnyachavez/ProBooksAi/blob/main/README.md#default-database-paths-windows) (CLI **`probooks.db`** vs desktop **`probooksai.db`**, **#21**) · [README — Excel workbook template](https://github.com/johnnyachavez/ProBooksAi/blob/main/README.md#excel-workbook-template-openpyxl) (**generate_workbook.py**, **openpyxl**; CLI/desktop **`--help`**: **`probooks/help_epilog.py`**) · [CONTRIBUTING — Running Tests](https://github.com/johnnyachavez/ProBooksAi/blob/main/docs/CONTRIBUTING.md#running-tests) (**pytest**, **`sync-workspace.ps1`**, **`work-context.example.json`**; **`gh auth login`**, **`gh repo set-default`**) · [CONTRIBUTING — Naming](https://github.com/johnnyachavez/ProBooksAi/blob/main/docs/CONTRIBUTING.md#naming-conventions) (issue titles, **ProBooks+ai** spelling).

## What happened

## Expected behavior

## Steps to reproduce

1.
2.

## Environment

- OS (e.g. Windows 11, Ubuntu 24.04)
- **Surface:** ProBooks+ai **desktop** (`python -m desktop_app.main`) and/or **`probooks` CLI** — which one?
- **Python** version (`python --version`)
- If UI/Qt: PySide6 version or note if headless (`QT_QPA_PLATFORM=offscreen`)
