"""desktop_app.version — no PySide6 import required."""

from __future__ import annotations

import probooks

from desktop_app.version import application_version


def test_application_version_is_non_empty():
    v = application_version()
    assert isinstance(v, str)
    assert len(v) >= 3


def test_probooks_version_matches_application_version():
    assert probooks.__version__ == application_version()
