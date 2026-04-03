"""Root generate_workbook.py stays a thin wrapper over probooksai.generator."""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_WRAPPER = _REPO / "generate_workbook.py"
_GENERATOR = _REPO / "probooksai" / "generator.py"


def test_generate_workbook_delegates_to_probooksai_generator() -> None:
    text = _WRAPPER.read_text(encoding="utf-8")
    assert "from probooksai.generator import" in text
    assert "build_workbook" in text
    assert "if __name__" in text
    assert "build_workbook()" in text
    assert "probooks/help_epilog.py" in text


def test_probooksai_generator_docstring_mentions_help_epilog() -> None:
    """probooksai.generator module doc stays aligned with CLI/desktop --help epilog."""
    text = _GENERATOR.read_text(encoding="utf-8")
    assert '"""' in text
    end = text.index('"""', text.index('"""') + 3)
    doc = text[: end + 3]
    assert "probooks/help_epilog.py" in doc
    assert "python -m probooks" in doc
    assert "desktop_app.main" in doc
