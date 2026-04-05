"""desktop_app.version — no PySide6 import required."""

from __future__ import annotations

import importlib.metadata
import re
from pathlib import Path

import probooks

from desktop_app import version as version_mod
from desktop_app.version import application_version

from tests.repo_paths import SCRIPTS_BUILD_DESKTOP_PS1, SCRIPTS_BUILD_DESKTOP_SH

_REPO_ROOT = Path(__file__).resolve().parent.parent

_PYINSTALLER_BLOCK_END = "desktop_app/main.py"
_COLLECT_SUBMODULES_RE = re.compile(r"--collect-submodules\s+(\S+)")
_HIDDEN_IMPORT_RE = re.compile(r"--hidden-import\s+(\S+)")
_ADD_DATA_PS1_RE = re.compile(r'"--add-data=([^;]+);([^"]+)"')
_ADD_DATA_SH_RE = re.compile(r'--add-data "([^:]+):([^"]+)"')


def _pyinstaller_argv_block(text: str) -> str:
    start = text.index("python -m PyInstaller")
    end = text.index(_PYINSTALLER_BLOCK_END, start)
    return text[start:end]


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
    b_ps1 = _pyinstaller_argv_block(ps1)
    b_sh = _pyinstaller_argv_block(sh)
    coll_ps1 = _COLLECT_SUBMODULES_RE.findall(b_ps1)
    coll_sh = _COLLECT_SUBMODULES_RE.findall(b_sh)
    assert coll_ps1 == coll_sh == [
        "openai",
        "pydantic",
        "httpx",
        "httpcore",
        "h11",
        "anyio",
    ]
    hid_ps1 = _HIDDEN_IMPORT_RE.findall(b_ps1)
    hid_sh = _HIDDEN_IMPORT_RE.findall(b_sh)
    assert hid_ps1 == hid_sh == ["generate_workbook", "pypdf"]
    needle = "python -m PyInstaller"
    assert ps1.index("application_version") < ps1.index(needle)
    assert sh.index("application_version") < sh.index(needle)


def test_build_desktop_scripts_pyinstaller_core_options_match() -> None:
    ps1 = SCRIPTS_BUILD_DESKTOP_PS1.read_text(encoding="utf-8")
    sh = SCRIPTS_BUILD_DESKTOP_SH.read_text(encoding="utf-8")
    b_ps1 = _pyinstaller_argv_block(ps1)
    b_sh = _pyinstaller_argv_block(sh)
    for b in (b_ps1, b_sh):
        assert b.count("--noconfirm") == 1
        assert b.count("--clean") == 1
        assert b.count("--onefile") == 1
        assert b.count("--windowed") == 1
        assert "--name ProBooksPlusAi" in b
    assert '"--paths=$RepoRoot"' in b_ps1
    assert '--paths "$REPO_ROOT"' in b_sh


def test_build_desktop_scripts_add_data_pairs_match() -> None:
    ps1 = SCRIPTS_BUILD_DESKTOP_PS1.read_text(encoding="utf-8")
    sh = SCRIPTS_BUILD_DESKTOP_SH.read_text(encoding="utf-8")
    b_ps1 = _pyinstaller_argv_block(ps1)
    b_sh = _pyinstaller_argv_block(sh)
    pairs_ps1 = _ADD_DATA_PS1_RE.findall(b_ps1)
    pairs_sh = _ADD_DATA_SH_RE.findall(b_sh)
    assert pairs_ps1 == pairs_sh == [
        ("ai", "ai"),
        ("probooks", "probooks"),
        ("probooksai", "probooksai"),
        ("desktop_app", "desktop_app"),
        ("docs", "docs"),
        ("pyproject.toml", "."),
    ]
