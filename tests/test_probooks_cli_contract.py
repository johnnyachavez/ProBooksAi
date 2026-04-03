"""probooks CLI argparse strings (import-free)."""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_CLI = _REPO / "probooks" / "cli.py"
_HELP_EPILOG = _REPO / "probooks" / "help_epilog.py"


def test_probooks_cli_description_epilog_and_default_db_help() -> None:
    cli = _CLI.read_text(encoding="utf-8")
    mod_doc_end = cli.index('"""', 3)
    mod_doc = cli[: mod_doc_end + 3]
    assert "help_epilog" in mod_doc
    hel = _HELP_EPILOG.read_text(encoding="utf-8")
    assert 'description="ProBooks+ai SQLite CLI"' in cli
    assert "python -m probooks" in cli
    assert "Default database" in cli
    assert "ProBooks+ai" in cli
    assert "EXCEL_COA_WORKBOOK_ARGPARSE_EPILOG" in cli
    assert "generate_workbook.py" in hel
    assert "Excel COA workbook" in hel
