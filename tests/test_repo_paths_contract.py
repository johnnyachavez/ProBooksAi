"""Smoke tests for ``tests.repo_paths`` (layout sanity, no Qt)."""

from __future__ import annotations

from pathlib import Path

from tests import repo_paths


def test_repo_paths_path_constants_live_under_repo_root() -> None:
    """Catch accidental ``REPO_ROOT / ".."`` or absolute paths in ``repo_paths``."""
    root = repo_paths.REPO_ROOT.resolve()
    for name, val in vars(repo_paths).items():
        if name.startswith("_") or not isinstance(val, Path):
            continue
        resolved = val.resolve()
        if resolved == root:
            continue
        assert root in resolved.parents, (
            f"{name} must live under REPO_ROOT ({root}), got {resolved}"
        )


def test_repo_paths_pin_essential_repo_files() -> None:
    """High-traffic paths used by contract tests should exist on disk."""
    assert repo_paths.REPO_ROOT.is_dir()
    assert repo_paths.README_MD.is_file()
    assert repo_paths.DOCS_CONTRIBUTING_MD.is_file()
    assert repo_paths.GITATTRIBUTES.is_file()
    assert repo_paths.PYPROJECT_TOML.is_file()
    assert repo_paths.REQUIREMENTS_TXT.is_file()
    assert repo_paths.GENERATE_WORKBOOK_PY.is_file()
    assert repo_paths.EXAMPLES_DIR.is_dir()
    assert repo_paths.EXAMPLES_SAMPLE_BANK_CSV.is_file()
    assert repo_paths.DESKTOP_APP_DIR.is_dir()
    assert repo_paths.DESKTOP_APP_MAIN_PY.is_file()
    assert repo_paths.PROBOOKS_MIGRATIONS_DIR.is_dir()
    assert repo_paths.PROBOOKS_MAIN_PY.is_file()
    assert repo_paths.PROBOOKS_CLI.is_file()
    assert repo_paths.PROBOOKS_HELP_EPILOG.is_file()
    assert repo_paths.GITHUB_WORKFLOW_CI_YML.is_file()
    assert repo_paths.GITHUB_WORKFLOW_UI_SCREENSHOT_YML.is_file()
    assert repo_paths.GITHUB_ISSUE_TEMPLATE_CONFIG_YML.is_file()
    assert repo_paths.GITHUB_ISSUE_TEMPLATE_BUG_REPORT_MD.is_file()
    assert repo_paths.GITHUB_ISSUE_TEMPLATE_FEATURE_REQUEST_MD.is_file()
    assert repo_paths.CI_VALIDATE_LAYOUT_SH.is_file()
    assert repo_paths.CI_VALIDATE_LAYOUT_PS1.is_file()
    assert repo_paths.SYNC_WORKSPACE_PS1.is_file()
    assert repo_paths.SCRIPTS_CAPTURE_UI_SCREENSHOT_PY.is_file()
    assert repo_paths.SCRIPTS_BUILD_DESKTOP_PS1.is_file()
    assert repo_paths.SCRIPTS_BUILD_DESKTOP_SH.is_file()
    assert repo_paths.INTEGRATIONS_WORK_CONTEXT_EXAMPLE.is_file()
    assert repo_paths.INDEX_HTML.is_file()
    assert repo_paths.INVOICE_HTML.is_file()
    assert repo_paths.REVIEW_HTML.is_file()
    assert repo_paths.DOCS_ROADMAP_MD.is_file()
    assert repo_paths.DOCS_BACKLOG_MD.is_file()
    assert repo_paths.DOCS_ISSUES_BACKLOG_MD.is_file()
    assert repo_paths.TESTS_CONFTEST.is_file()
    assert repo_paths.CURSOR_RULE_GITHUB_WORK_CONTEXT_MDC.is_file()
    assert repo_paths.GITHUB_PULL_REQUEST_TEMPLATE_MD.is_file()
    assert repo_paths.TESTS_CI_VALIDATE_LAYOUT_SYNC_PY.is_file()
