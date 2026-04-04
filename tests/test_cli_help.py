"""probooks CLI --help (epilog and exit code)."""

from __future__ import annotations

import io
import sys
from unittest.mock import patch

import pytest


def test_probooks_backup_help_mentions_sqlite_and_distinct_paths() -> None:
    from probooks.cli import main

    buf = io.StringIO()
    with patch.object(sys, "stdout", buf):
        with pytest.raises(SystemExit) as exc:
            main(["backup", "--help"])
    assert exc.value.code == 0
    text = buf.getvalue()
    assert "SQLite" in text
    assert "different path" in text
    assert "online backup" in text.lower()


def test_probooks_restore_help_mentions_sqlite_and_distinct_paths() -> None:
    from probooks.cli import main

    buf = io.StringIO()
    with patch.object(sys, "stdout", buf):
        with pytest.raises(SystemExit) as exc:
            main(["restore", "--help"])
    assert exc.value.code == 0
    text = buf.getvalue()
    assert "SQLite" in text
    assert "different path" in text
    assert "online backup" in text.lower()


def test_probooks_help_epilog_and_exit_zero() -> None:
    from probooks.cli import main

    buf = io.StringIO()
    with patch.object(sys, "stdout", buf):
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
    assert exc.value.code == 0
    text = buf.getvalue()
    assert "python -m probooks" in text
    assert "README" in text
    assert "Default database" in text
    assert "generate_workbook.py" in text
    assert "Excel COA workbook" in text
    assert "probooks.backup" in text
    assert "File → Backup" in text
    assert "UTF-8 BOM for Excel" in text
    assert "import csv --errors-out" in text


def test_probooks_import_csv_help_mentions_utf8_optional_bom_input() -> None:
    from probooks.cli import main

    buf = io.StringIO()
    with patch.object(sys, "stdout", buf):
        with pytest.raises(SystemExit) as exc:
            main(["import", "csv", "--help"])
    assert exc.value.code == 0
    text = buf.getvalue()
    assert "UTF-8" in text and "optional BOM" in text
    assert "import_batch" in text and "bank_transactions" in text
