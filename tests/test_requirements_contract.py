"""requirements.txt stays aligned with documented optional installs (README / CONTRIBUTING)."""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_REQ = _REPO / "requirements.txt"


def test_requirements_txt_lists_core_runtime_and_test_stack() -> None:
    text = _REQ.read_text(encoding="utf-8")
    assert "openpyxl" in text
    assert "PySide6" in text
    assert "pypdf" in text
    assert "pytest" in text
