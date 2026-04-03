"""Smoke tests for ``tests.repo_paths`` (layout sanity, no Qt)."""

from __future__ import annotations

import re
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


def test_ci_validate_layout_sh_require_paths_exist() -> None:
    """Every ``require`` path in ``ci_validate_layout.sh`` must exist (twin .ps1 uses the same list)."""
    text = repo_paths.CI_VALIDATE_LAYOUT_SH.read_text(encoding="utf-8")
    root = repo_paths.REPO_ROOT
    rels: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^require\s+(\S+)\s*$", line.strip())
        if m:
            rels.append(m.group(1))
    assert rels, "expected at least one require line in ci_validate_layout.sh"
    for rel in rels:
        path = root / rel
        assert path.is_file(), (
            f"ci_validate_layout.sh lists require {rel!r} but {path} is not a file"
        )
