#!/usr/bin/env bash
# ProBooks+ai — same path checks as .github/workflows/ci.yml validate job.
# Twin: scripts/ci_validate_layout.ps1 (Windows). Keep both lists identical.
# Run from anywhere: bash scripts/ci_validate_layout.sh (repo root is next to scripts/).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

die() {
  echo >&2 "ci_validate_layout: $1"
  exit 1
}

require() {
  test -f "$1" || die "missing required file: $1"
}

require README.md
require pyproject.toml
require requirements.txt

require docs/ROADMAP.md
require docs/CONTRIBUTING.md
require docs/BACKLOG.md
require docs/issues-backlog.md

require probooks/__main__.py
require probooks/cli.py
require probooks/help_epilog.py
require desktop_app/main.py

require scripts/capture_ui_screenshot.py
require scripts/build_desktop.ps1
require scripts/build_desktop.sh
require scripts/sync-workspace.ps1
require scripts/ci_validate_layout.sh
require scripts/ci_validate_layout.ps1

require .github/workflows/ci.yml
require .github/workflows/ui-screenshot.yml
require .github/PULL_REQUEST_TEMPLATE.md
require .github/ISSUE_TEMPLATE/config.yml
require .github/ISSUE_TEMPLATE/bug_report.md
require .github/ISSUE_TEMPLATE/feature_request.md

require integrations/work-context.example.json
require .cursor/rules/github-work-context.mdc

require index.html
require invoice.html
require review.html

require examples/sample_bank.csv
require generate_workbook.py

require tests/test_ci_validate_layout_sync.py
require tests/test_pyproject_contract.py
require tests/test_requirements_contract.py
require tests/test_package_name_contract.py
require tests/test_integrations_example_contract.py
require tests/test_generate_workbook_contract.py
require tests/test_desktop_main_contract.py
require tests/test_probooks_cli_contract.py
require tests/test_probooks_paths_contract.py
require tests/test_probooksai_database_contract.py
require tests/test_local_docs_contract.py

echo "ci_validate_layout: OK ($ROOT)"
