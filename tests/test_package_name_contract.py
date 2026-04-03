"""Installed distribution name ``probooks-ai`` must stay consistent across metadata lookups."""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]


def test_desktop_version_module_uses_pyproject_distribution_name() -> None:
    ver_py = (_REPO / "desktop_app" / "version.py").read_text(encoding="utf-8")
    assert '_PACKAGE = "probooks-ai"' in ver_py


def test_probooks_init_looks_up_same_distribution_name() -> None:
    init_py = (_REPO / "probooks" / "__init__.py").read_text(encoding="utf-8")
    assert 'importlib.metadata.version("probooks-ai")' in init_py
