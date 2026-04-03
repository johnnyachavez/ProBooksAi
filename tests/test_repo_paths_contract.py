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
    assert repo_paths.GITATTRIBUTES.is_file()
    assert repo_paths.PYPROJECT_TOML.is_file()
    assert repo_paths.DESKTOP_APP_DIR.is_dir()
    assert repo_paths.PROBOOKS_MIGRATIONS_DIR.is_dir()
    assert repo_paths.GITHUB_WORKFLOW_CI_YML.is_file()
    assert repo_paths.CI_VALIDATE_LAYOUT_SH.is_file()
    assert repo_paths.INTEGRATIONS_WORK_CONTEXT_EXAMPLE.is_file()
