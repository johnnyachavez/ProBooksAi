"""desktop_app.local_docs"""

from __future__ import annotations

from desktop_app.local_docs import resolve_local_roadmap_path


def test_resolve_local_roadmap_path_finds_repo_file():
    p = resolve_local_roadmap_path()
    assert p is not None
    assert p.name == "ROADMAP.md"
    assert "docs" in p.parts


def test_resolve_local_roadmap_path_points_to_product_roadmap_markdown():
    p = resolve_local_roadmap_path()
    assert p is not None
    text = p.read_text(encoding="utf-8")
    assert "ProBooks+ai" in text
    assert "Implementation Roadmap" in text
