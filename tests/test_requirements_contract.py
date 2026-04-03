"""requirements.txt stays aligned with documented optional installs (README / CONTRIBUTING)."""

from __future__ import annotations

from tests.repo_paths import REQUIREMENTS_TXT as _REQ


def test_requirements_txt_lists_core_runtime_and_test_stack() -> None:
    text = _REQ.read_text(encoding="utf-8")
    assert "openpyxl" in text
    assert "PySide6" in text
    assert "pypdf" in text
    assert "pytest" in text
