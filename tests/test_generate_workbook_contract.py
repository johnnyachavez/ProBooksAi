"""Root generate_workbook.py stays a thin wrapper over probooksai.generator."""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_WRAPPER = _REPO / "generate_workbook.py"


def test_generate_workbook_delegates_to_probooksai_generator() -> None:
    text = _WRAPPER.read_text(encoding="utf-8")
    assert "from probooksai.generator import" in text
    assert "build_workbook" in text
    assert "if __name__" in text
    assert "build_workbook()" in text
    assert "probooks/help_epilog.py" in text
