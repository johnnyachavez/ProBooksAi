"""Packaging metadata used by CI, the desktop app, and install docs."""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_TOML = _REPO / "pyproject.toml"


def test_pyproject_wheel_name_scripts_and_packages() -> None:
    text = _TOML.read_text(encoding="utf-8")
    assert 'name = "probooks-ai"' in text
    assert "ProBooks+ai" in text
    assert "PySide6 desktop" in text
    assert "openpyxl" in text
    assert "Excel COA workbook template" in text
    assert 'probooks = "probooks.cli:main"' in text
    assert 'packages = ["probooks", "probooksai"]' in text
    assert "README.md#web-shell-review" in text
    assert '"desktop"' in text and '"pyside6"' in text


def test_pyproject_ci_extra_includes_pytest_pypdf_and_pyside6() -> None:
    """Matches .github/workflows/ci.yml: pip install -e ".[ci]"."""
    text = _TOML.read_text(encoding="utf-8")
    start = text.index("ci = [")
    end = text.index("]", start)
    block = text[start:end]
    assert "pytest" in block
    assert "pypdf" in block
    assert "PySide6" in block


def test_pyproject_build_system_hatchling_and_requires_python() -> None:
    text = _TOML.read_text(encoding="utf-8")
    assert 'requires = ["hatchling"]' in text
    assert 'build-backend = "hatchling.build"' in text
    assert 'requires-python = ">=3.10"' in text


def test_pyproject_pytest_ini_options_point_at_tests() -> None:
    text = _TOML.read_text(encoding="utf-8")
    assert 'testpaths = ["tests"]' in text
    assert 'python_files = ["test_*.py"]' in text
