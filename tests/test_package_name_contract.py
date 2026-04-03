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
    assert "help_epilog" in init_py


def test_help_epilog_module_docstring_mentions_generator() -> None:
    text = (_REPO / "probooks" / "help_epilog.py").read_text(encoding="utf-8")
    doc_end = text.index('"""', 3)
    doc = text[: doc_end + 3]
    assert "probooksai.generator" in doc
    assert "generate_workbook" in doc
    assert "desktop_app" in doc


def test_probooksai_init_mentions_help_epilog_pointer() -> None:
    """probooksai package doc stays aligned with probooks.help_epilog for --help copy."""
    text = (_REPO / "probooksai" / "__init__.py").read_text(encoding="utf-8")
    assert "help_epilog" in text
    assert "probooks" in text
