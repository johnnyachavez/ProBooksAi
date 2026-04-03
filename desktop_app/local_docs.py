"""Resolve bundled or repo-local documentation paths (desktop app)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional


def resolve_local_roadmap_path() -> Optional[Path]:
    """
    Return ``docs/ROADMAP.md`` if found: PyInstaller extract dir, next to exe, or repo root.
    """
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "docs" / "ROADMAP.md")
        candidates.append(Path(sys.executable).resolve().parent / "docs" / "ROADMAP.md")
    repo_root = Path(__file__).resolve().parent.parent
    candidates.append(repo_root / "docs" / "ROADMAP.md")
    for p in candidates:
        if p.is_file():
            return p.resolve()
    return None
