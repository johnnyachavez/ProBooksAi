"""probooks CLI argparse strings (import-free)."""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_CLI = _REPO / "probooks" / "cli.py"


def test_probooks_cli_description_epilog_and_default_db_help() -> None:
    text = _CLI.read_text(encoding="utf-8")
    assert 'description="ProBooks+ai SQLite CLI"' in text
    assert "python -m probooks" in text
    assert "Default database" in text
    assert "ProBooks+ai" in text
    assert "generate_workbook.py" in text
    assert "Excel COA workbook" in text
