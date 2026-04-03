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
    """Dirs not covered as standalone ``require`` lines in ``ci_validate_layout.sh``."""
    assert repo_paths.REPO_ROOT.is_dir()
    assert repo_paths.DESKTOP_APP_DIR.is_dir()
    assert repo_paths.PROBOOKS_MIGRATIONS_DIR.is_dir()
