"""Application version from installed package metadata (pyproject)."""

from __future__ import annotations

import importlib.metadata

_PACKAGE = "probooks-ai"
_FALLBACK = "0.1.0"


def application_version() -> str:
    try:
        return importlib.metadata.version(_PACKAGE)
    except importlib.metadata.PackageNotFoundError:
        return _FALLBACK
