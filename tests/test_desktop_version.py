"""desktop_app.version — no PySide6 import required."""

from __future__ import annotations

import functools
import importlib.metadata
import re
from pathlib import Path

import probooks

import desktop_app.version as desktop_version_mod
from desktop_app import version as version_mod
from desktop_app.version import application_version

from tests.repo_paths import (
    PYPROJECT_TOML,
    SCRIPTS_BUILD_DESKTOP_PS1,
    SCRIPTS_BUILD_DESKTOP_SH,
    SCRIPTS_DIR,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent

_VERSION_PY_SNIPPET = (
    "from desktop_app.version import application_version; print(application_version())"
)

_BUNDLES_DOC_LINES = (
    "# Bundles ai/ (Document Intake Run AI), probooks/, probooksai/, desktop_app/, docs/ (ROADMAP.md),",
    "# pyproject.toml; hidden-import generate_workbook (COA seed); openai + pydantic + httpx stack (httpx/httpcore/h11/anyio); hidden-import pypdf (ai.extractor).",
)

_ORDERED_STEP_COMMENT_LINES = (
    "# 1. Ensure PyInstaller is installed; have openai + pypdf installed (e.g. pip install -r requirements.txt or .[ci])",
    '#    so analysis can bundle them. Editable desktop: pip install -e ".[desktop]"',
    "# 1b. Resolved app version (same helper as the desktop UI / --version; pyproject.toml when not installed)",
    '# 2. Build (paths + bundled packages for frozen runtime; copy-metadata needs pip install -e ".[desktop]" first)',
)

_PYINSTALLER_BLOCK_END = "desktop_app/main.py"
_COLLECT_SUBMODULES_RE = re.compile(r"--collect-submodules\s+(\S+)")
_HIDDEN_IMPORT_RE = re.compile(r"--hidden-import\s+(\S+)")
_ADD_DATA_PS1_RE = re.compile(r'"--add-data=([^;]+);([^"]+)"')
_ADD_DATA_SH_RE = re.compile(r'--add-data "([^:]+):([^"]+)"')


@functools.lru_cache(maxsize=1)
def _build_desktop_script_texts() -> tuple[str, str]:
    return (
        SCRIPTS_BUILD_DESKTOP_PS1.read_text(encoding="utf-8"),
        SCRIPTS_BUILD_DESKTOP_SH.read_text(encoding="utf-8"),
    )


def _project_distribution_name_from_pyproject(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    in_project = False
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped == "[project]":
            in_project = True
            continue
        if in_project:
            if stripped.startswith("[") and stripped != "[project]":
                break
            line = stripped.split("#", 1)[0].strip()
            m = re.match(r'^name\s*=\s*["\']([^"\']+)["\']', line)
            if m:
                return m.group(1)
    raise AssertionError("pyproject.toml has no [project] name")


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
    ps1, sh = _build_desktop_script_texts()
    assert "application_version" in ps1
    assert "application_version" in sh
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


def test_build_desktop_scripts_header_comment_paths() -> None:
    ps1, sh = _build_desktop_script_texts()
    assert ps1.splitlines()[0] == "# scripts/build_desktop.ps1"
    assert sh.splitlines()[1] == "# scripts/build_desktop.sh"


def test_build_desktop_script_files_exist() -> None:
    assert SCRIPTS_BUILD_DESKTOP_PS1.is_file()
    assert SCRIPTS_BUILD_DESKTOP_SH.is_file()


def test_build_desktop_script_paths_under_scripts_dir() -> None:
    assert SCRIPTS_BUILD_DESKTOP_PS1.parent == SCRIPTS_DIR
    assert SCRIPTS_BUILD_DESKTOP_SH.parent == SCRIPTS_DIR
    assert SCRIPTS_BUILD_DESKTOP_PS1.name == "build_desktop.ps1"
    assert SCRIPTS_BUILD_DESKTOP_SH.name == "build_desktop.sh"


def test_build_desktop_sh_env_bash_shebang() -> None:
    _, sh = _build_desktop_script_texts()
    assert sh.splitlines()[0] == "#!/usr/bin/env bash"


def test_build_desktop_scripts_ordered_step_comments_match() -> None:
    ps1, sh = _build_desktop_script_texts()
    for line in _ORDERED_STEP_COMMENT_LINES:
        assert ps1.count(line) == sh.count(line) == 1


def test_build_desktop_scripts_shared_doc_comments_match() -> None:
    ps1, sh = _build_desktop_script_texts()
    for line in _BUNDLES_DOC_LINES:
        assert ps1.count(line) == sh.count(line) == 1
    editable = 'pip install -e ".[desktop]"'
    assert ps1.count(editable) == sh.count(editable) == 2


def test_build_desktop_scripts_tagline_and_frozen_base_name() -> None:
    ps1, sh = _build_desktop_script_texts()
    tag = "Build a standalone ProBooks+ai desktop executable"
    assert ps1.count(tag) == sh.count(tag) == 1
    assert ps1.count("(output: ProBooksPlusAi.exe).") == 1
    assert sh.count("(output: ProBooksPlusAi).") == 1
    assert ps1.count("ProBooksPlusAi") == sh.count("ProBooksPlusAi") == 2


def test_build_desktop_scripts_cd_to_repo_root_once() -> None:
    ps1, sh = _build_desktop_script_texts()
    assert ps1.count("Set-Location $RepoRoot") == 1
    assert sh.count('cd "$REPO_ROOT"') == 1


def test_build_desktop_scripts_repo_parent_trailing_blank_entry_once() -> None:
    ps1, sh = _build_desktop_script_texts()
    assert ps1.count("Split-Path -Parent $ScriptDir") == 1
    assert sh.count('cd "$SCRIPT_DIR/.." && pwd') == 1
    assert ps1.count('Write-Host ""') == sh.count('echo ""') == 1
    assert ps1.count("desktop_app/main.py") == sh.count("desktop_app/main.py") == 1


def test_build_desktop_scripts_fail_fast_and_script_location() -> None:
    ps1, sh = _build_desktop_script_texts()
    assert ps1.count('$ErrorActionPreference = "Stop"') == 1
    assert sh.count("set -euo pipefail") == 1
    assert ps1.count("$MyInvocation.MyCommand.Definition") == 1
    assert sh.count("${BASH_SOURCE[0]}") == 1


def test_build_desktop_scripts_packaging_echo_and_version_snippet_match() -> None:
    ps1, sh = _build_desktop_script_texts()
    label = "Packaging ProBooks+ai version"
    assert ps1.count(label) == sh.count(label) == 1
    assert ps1.count(_VERSION_PY_SNIPPET) == sh.count(_VERSION_PY_SNIPPET) == 1
    done = "Build complete. Executable is in:"
    assert ps1.count(done) == sh.count(done) == 1


def test_build_desktop_scripts_done_line_dist_paths() -> None:
    ps1, sh = _build_desktop_script_texts()
    assert 'Executable is in: $RepoRoot\\dist\\"' in ps1
    assert 'Executable is in: $REPO_ROOT/dist/"' in sh


def test_build_desktop_scripts_pip_and_pyinstaller_entry_match() -> None:
    ps1, sh = _build_desktop_script_texts()
    pip_line = "python -m pip install --quiet pyinstaller"
    assert ps1.count(pip_line) == sh.count(pip_line) == 1
    inv = "python -m PyInstaller"
    assert ps1.count(inv) == sh.count(inv) == 1
    assert re.search(
        r"--hidden-import pypdf `\s*\r?\n\s*desktop_app/main\.py",
        ps1,
    )
    assert re.search(
        r"--hidden-import pypdf \\\s*\r?\n\s*desktop_app/main\.py",
        sh,
    )


def test_build_desktop_scripts_pyinstaller_core_options_match() -> None:
    ps1, sh = _build_desktop_script_texts()
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


def test_build_desktop_pyinstaller_argv_single_python_dash_m() -> None:
    ps1, sh = _build_desktop_script_texts()
    for b in (_pyinstaller_argv_block(ps1), _pyinstaller_argv_block(sh)):
        assert b.count("python -m") == 1


def test_build_desktop_scripts_add_data_pairs_match() -> None:
    ps1, sh = _build_desktop_script_texts()
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


def test_build_desktop_copy_metadata_matches_pyproject_and_version_module() -> None:
    dist_name = _project_distribution_name_from_pyproject(PYPROJECT_TOML)
    assert dist_name == desktop_version_mod._PACKAGE
    flag = f"--copy-metadata {dist_name}"
    ps1, sh = _build_desktop_script_texts()
    for b in (_pyinstaller_argv_block(ps1), _pyinstaller_argv_block(sh)):
        assert b.count(flag) == 1
