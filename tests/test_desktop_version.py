"""desktop_app.version — no PySide6 import required."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path

import probooks

from desktop_app import version as version_mod
from desktop_app.version import application_version

from tests.repo_paths import SCRIPTS_BUILD_DESKTOP_PS1, SCRIPTS_BUILD_DESKTOP_SH

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_application_version_is_non_empty():
    v = application_version()
    assert isinstance(v, str)
    assert len(v) >= 3


def test_probooks_version_matches_application_version():
    assert probooks.__version__ == application_version()


def test_version_from_pyproject_reads_project_section():
    v = version_mod._version_from_pyproject_toml()
    assert v is not None
    assert v == probooks.__version__


def test_application_version_falls_back_to_pyproject_when_metadata_missing(monkeypatch):
    parsed = version_mod._version_from_pyproject_toml()
    assert parsed is not None

    def _raise(_name: str) -> str:
        raise importlib.metadata.PackageNotFoundError

    monkeypatch.setattr(importlib.metadata, "version", _raise)
    assert version_mod.application_version() == parsed


def test_fallback_version_literal_matches_pyproject_toml() -> None:
    """``_FALLBACK`` and ``probooks`` metadata-less ``__version__`` match ``[project].version``."""
    parsed = version_mod._version_from_pyproject_toml()
    assert parsed is not None
    assert version_mod._FALLBACK == parsed
    init_text = (_REPO_ROOT / "probooks" / "__init__.py").read_text(encoding="utf-8")
    assert f'return "{parsed}"' in init_text


def test_build_desktop_scripts_echo_application_version_before_pyinstaller() -> None:
    ps1 = SCRIPTS_BUILD_DESKTOP_PS1.read_text(encoding="utf-8")
    sh = SCRIPTS_BUILD_DESKTOP_SH.read_text(encoding="utf-8")
    assert "application_version" in ps1
    assert "application_version" in sh
    assert "--copy-metadata probooks-ai" in ps1
    assert "--copy-metadata probooks-ai" in sh
    assert "pyproject.toml" in ps1
    assert "pyproject.toml" in sh
    assert '"--add-data=ai;ai"' in ps1
    assert '--add-data "ai:ai"' in sh
    assert '"--add-data=probooks;probooks"' in ps1
    assert '--add-data "probooks:probooks"' in sh
    ps_add = ps1.count('"--add-data=')
    sh_add = sh.count('--add-data "')
    assert ps_add == sh_add == 6
    assert ps1.count("--copy-metadata probooks-ai") == 1
    assert sh.count("--copy-metadata probooks-ai") == 1
    assert ps1.count("--hidden-import generate_workbook") == 1
    assert sh.count("--hidden-import generate_workbook") == 1
    assert ps1.count("--collect-submodules openai") == 1
    assert sh.count("--collect-submodules openai") == 1
    assert ps1.count("--collect-submodules pydantic") == 1
    assert sh.count("--collect-submodules pydantic") == 1
    assert ps1.count("--collect-submodules httpx") == 1
    assert sh.count("--collect-submodules httpx") == 1
    assert ps1.count("--collect-submodules httpcore") == 1
    assert sh.count("--collect-submodules httpcore") == 1
    assert ps1.count("--hidden-import pypdf") == 1
    assert sh.count("--hidden-import pypdf") == 1
    needle = "python -m PyInstaller"
    assert ps1.index("application_version") < ps1.index(needle)
    assert sh.index("application_version") < sh.index(needle)
