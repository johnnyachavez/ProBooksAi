# scripts/ci_validate_layout.ps1
# ProBooks+ai — same path checks as scripts/ci_validate_layout.sh and CI validate (Linux runs the .sh).
# When bash is not on PATH (e.g. plain Windows PowerShell), run from repo root: .\scripts\ci_validate_layout.ps1
# Pytest: tests/test_ci_validate_layout_sync.py::test_ci_validate_layout_sh_require_paths_exist (each Require-File path must exist).

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
Set-Location $Root

function Require-File {
    param([Parameter(Mandatory)][string] $RelPath)
    $full = Join-Path $Root $RelPath
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
        Write-Error "ci_validate_layout: missing required file: $RelPath"
    }
}

Require-File "README.md"
Require-File "pyproject.toml"
Require-File "requirements.txt"

Require-File "docs/ROADMAP.md"
Require-File "docs/CONTRIBUTING.md"
Require-File "docs/BACKLOG.md"
Require-File "docs/issues-backlog.md"

Require-File "probooks/__main__.py"
Require-File "probooks/cli.py"
Require-File "probooks/help_epilog.py"
Require-File "desktop_app/main.py"

Require-File "scripts/capture_ui_screenshot.py"
Require-File "scripts/build_desktop.ps1"
Require-File "scripts/build_desktop.sh"
Require-File "scripts/sync-workspace.ps1"
Require-File "scripts/ci_validate_layout.sh"
Require-File "scripts/ci_validate_layout.ps1"

Require-File ".github/workflows/ci.yml"
Require-File ".github/workflows/ui-screenshot.yml"
Require-File ".gitattributes"
Require-File ".github/PULL_REQUEST_TEMPLATE.md"
Require-File ".github/ISSUE_TEMPLATE/config.yml"
Require-File ".github/ISSUE_TEMPLATE/bug_report.md"
Require-File ".github/ISSUE_TEMPLATE/feature_request.md"

Require-File "integrations/work-context.example.json"
Require-File ".cursor/rules/github-work-context.mdc"

Require-File "index.html"
Require-File "invoice.html"
Require-File "review.html"

Require-File "examples/sample_bank.csv"
Require-File "generate_workbook.py"

Require-File "tests/test_ci_validate_layout_sync.py"
Require-File "tests/conftest.py"
Require-File "tests/test_pyproject_contract.py"
Require-File "tests/test_requirements_contract.py"
Require-File "tests/test_repo_paths_contract.py"
Require-File "tests/test_package_name_contract.py"
Require-File "tests/test_integrations_example_contract.py"
Require-File "tests/test_generate_workbook_contract.py"
Require-File "tests/test_desktop_main_contract.py"
Require-File "tests/test_probooks_backup_contract.py"
Require-File "tests/test_probooks_cli_contract.py"
Require-File "tests/test_probooks_paths_contract.py"
Require-File "tests/test_probooksai_database_contract.py"
Require-File "tests/test_local_docs_contract.py"

Write-Host "ci_validate_layout: OK ($Root)"
