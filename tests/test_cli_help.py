"""probooks CLI --help (epilog and exit code)."""

from __future__ import annotations

import io
import sys
from unittest.mock import patch

import pytest


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
