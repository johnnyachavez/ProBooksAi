"""desktop_app/local_docs roadmap path resolution (Help menu)."""

from __future__ import annotations

from tests.repo_paths import DESKTOP_APP_DIR

_LOCAL_DOCS = DESKTOP_APP_DIR / "local_docs.py"


def test_local_docs_targets_docs_roadmap_md() -> None:
    text = _LOCAL_DOCS.read_text(encoding="utf-8")
    assert "docs" in text and "ROADMAP.md" in text
    assert "resolve_local_roadmap_path" in text
