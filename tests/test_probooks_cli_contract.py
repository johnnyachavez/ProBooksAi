"""probooks CLI argparse strings (import-free)."""

from __future__ import annotations

from tests.repo_paths import PROBOOKS_CLI, PROBOOKS_HELP_EPILOG


def test_probooks_cli_description_epilog_and_default_db_help() -> None:
    cli = PROBOOKS_CLI.read_text(encoding="utf-8")
    mod_doc_end = cli.index('"""', 3)
    mod_doc = cli[: mod_doc_end + 3]
    assert "help_epilog" in mod_doc
    hel = PROBOOKS_HELP_EPILOG.read_text(encoding="utf-8")
    assert 'description="ProBooks+ai SQLite CLI"' in cli
    assert "python -m probooks" in cli
    assert "Default database" in cli
    assert "default_db_path().name" in cli, (
        "CLI --db help should derive the default filename from probooks.paths.default_db_path()"
    )
    assert "ProBooks+ai" in cli
    assert "EXCEL_COA_WORKBOOK_ARGPARSE_EPILOG" in cli
    assert "generate_workbook.py" in hel
    assert "Excel COA workbook" in hel


def test_probooks_cli_wires_backup_restore_subcommands() -> None:
    """Keep backup/restore subcommands bound to probooks.backup and argparse dests."""
    cli = PROBOOKS_CLI.read_text(encoding="utf-8")
    assert "from probooks.backup import backup_database, is_sqlite_file, restore_database" in cli
    assert 'sub.add_parser(\n        "backup",' in cli
    assert 'sub.add_parser(\n        "restore",' in cli
    assert "return cmd_backup(db, args.output)" in cli
    assert "return cmd_restore(db, args.input, args.yes)" in cli
