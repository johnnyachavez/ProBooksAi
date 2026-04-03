"""probooksai.database legacy on-disk folder vs product name (README dual default paths)."""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_DBMOD = _REPO / "probooksai" / "database.py"


def test_probooksai_database_keeps_legacy_appdata_folder_name() -> None:
    text = _DBMOD.read_text(encoding="utf-8")
    assert "ProBooks+ai" in text
    assert 'data_dir = base / "ProBooksAi"' in text
    assert "ProBooksAi" in text
