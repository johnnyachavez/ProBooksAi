"""Application version: wheel metadata via ``importlib.metadata``, else ``pyproject.toml`` (dev tree or PyInstaller extract)."""

from __future__ import annotations

import importlib.metadata
import re
from pathlib import Path

_PACKAGE = "probooks-ai"
_FALLBACK = "0.1.0"
_VERSION_RE = re.compile(r'^version\s*=\s*["\']([^"\']+)["\']')


def _version_from_pyproject_toml() -> str | None:
    """Read ``[project].version`` from a repo-layout or PyInstaller extract tree (``pyproject.toml`` beside ``desktop_app/``)."""
    path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    in_project = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "[project]":
            in_project = True
            continue
        if in_project:
            if stripped.startswith("[") and stripped != "[project]":
                break
            line = stripped.split("#", 1)[0].strip()
            m = _VERSION_RE.match(line)
            if m:
                return m.group(1).strip()
    return None


def application_version() -> str:
    try:
        return importlib.metadata.version(_PACKAGE)
    except importlib.metadata.PackageNotFoundError:
        pass
    v = _version_from_pyproject_toml()
    if v:
        return v
    return _FALLBACK
