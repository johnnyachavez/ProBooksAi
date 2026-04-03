"""Root generate_workbook.py stays a thin wrapper over probooksai.generator."""

from __future__ import annotations

from tests.repo_paths import GENERATE_WORKBOOK_PY, PROBOOKSAI_PACKAGE_DIR
_WRAPPER = GENERATE_WORKBOOK_PY
_GENERATOR = PROBOOKSAI_PACKAGE_DIR / "generator.py"


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
