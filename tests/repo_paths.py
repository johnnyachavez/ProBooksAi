"""Shared ``Path`` roots for tests that read repo files (contract tests, migrations, CI layout).

Use ``REPO_ROOT / "relative/path"`` when no named constant exists yet.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# --- Root metadata & tooling -------------------------------------------------
PYPROJECT_TOML = REPO_ROOT / "pyproject.toml"
REQUIREMENTS_TXT = REPO_ROOT / "requirements.txt"
GENERATE_WORKBOOK_PY = REPO_ROOT / "generate_workbook.py"
README_MD = REPO_ROOT / "README.md"
GITATTRIBUTES = REPO_ROOT / ".gitattributes"
REVIEW_HTML = REPO_ROOT / "review.html"

# --- integrations/ (work-context sync sample) -------------------------------
INTEGRATIONS_DIR = REPO_ROOT / "integrations"
INTEGRATIONS_WORK_CONTEXT_EXAMPLE = INTEGRATIONS_DIR / "work-context.example.json"

# --- Application packages ----------------------------------------------------
DESKTOP_APP_DIR = REPO_ROOT / "desktop_app"
EXAMPLES_DIR = REPO_ROOT / "examples"
PROBOOKS_PACKAGE_DIR = REPO_ROOT / "probooks"
PROBOOKS_MIGRATIONS_DIR = PROBOOKS_PACKAGE_DIR / "migrations"
PROBOOKS_CLI = PROBOOKS_PACKAGE_DIR / "cli.py"
PROBOOKS_HELP_EPILOG = PROBOOKS_PACKAGE_DIR / "help_epilog.py"
PROBOOKSAI_PACKAGE_DIR = REPO_ROOT / "probooksai"

# --- scripts/, tests/, docs/, GitHub, Cursor rules ----------------------------
SCRIPTS_DIR = REPO_ROOT / "scripts"
CI_VALIDATE_LAYOUT_SH = SCRIPTS_DIR / "ci_validate_layout.sh"
CI_VALIDATE_LAYOUT_PS1 = SCRIPTS_DIR / "ci_validate_layout.ps1"
TESTS_DIR = REPO_ROOT / "tests"
DOCS_DIR = REPO_ROOT / "docs"
DOCS_CONTRIBUTING_MD = DOCS_DIR / "CONTRIBUTING.md"
DOCS_ROADMAP_MD = DOCS_DIR / "ROADMAP.md"
DOCS_BACKLOG_MD = DOCS_DIR / "BACKLOG.md"
DOCS_ISSUES_BACKLOG_MD = DOCS_DIR / "issues-backlog.md"
GITHUB_DIR = REPO_ROOT / ".github"
GITHUB_WORKFLOWS_DIR = GITHUB_DIR / "workflows"
GITHUB_WORKFLOW_CI_YML = GITHUB_WORKFLOWS_DIR / "ci.yml"
GITHUB_WORKFLOW_UI_SCREENSHOT_YML = GITHUB_WORKFLOWS_DIR / "ui-screenshot.yml"
GITHUB_PULL_REQUEST_TEMPLATE_MD = GITHUB_DIR / "PULL_REQUEST_TEMPLATE.md"
GITHUB_ISSUE_TEMPLATE_DIR = GITHUB_DIR / "ISSUE_TEMPLATE"
GITHUB_ISSUE_TEMPLATE_CONFIG_YML = GITHUB_ISSUE_TEMPLATE_DIR / "config.yml"
GITHUB_ISSUE_TEMPLATE_BUG_REPORT_MD = GITHUB_ISSUE_TEMPLATE_DIR / "bug_report.md"
GITHUB_ISSUE_TEMPLATE_FEATURE_REQUEST_MD = (
    GITHUB_ISSUE_TEMPLATE_DIR / "feature_request.md"
)
CURSOR_RULES_DIR = REPO_ROOT / ".cursor" / "rules"
CURSOR_RULE_GITHUB_WORK_CONTEXT_MDC = CURSOR_RULES_DIR / "github-work-context.mdc"
