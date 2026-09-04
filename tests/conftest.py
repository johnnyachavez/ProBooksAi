"""Shared pytest fixtures.

``isolated_branded_app_data_env`` points Windows ``LOCALAPPDATA`` / ``APPDATA`` (or Unix
``HOME``) at a temp tree so ``probooks.paths`` and ``probooksai.database.get_data_dir``
tests do not touch the developer's real app data.

``_destroy_leftover_qt_widgets`` runs after every test and keeps the shared
``QApplication`` from accumulating every widget the suite has ever built.

Repository path constants for source-only contract tests live in ``tests/repo_paths.py``.
"""

from __future__ import annotations

import sys

import pytest


@pytest.fixture
def isolated_branded_app_data_env(tmp_path, monkeypatch) -> None:
    """Isolate ProBooks+ai dirs under tmp_path (Windows LOCALAPPDATA + APPDATA, else HOME)."""
    if sys.platform == "win32":
        local = tmp_path / "Local"
        roaming = tmp_path / "Roaming"
        local.mkdir()
        roaming.mkdir()
        monkeypatch.setenv("LOCALAPPDATA", str(local))
        monkeypatch.setenv("APPDATA", str(roaming))
    else:
        monkeypatch.delenv("APPDATA", raising=False)
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))


@pytest.fixture(autouse=True)
def _destroy_leftover_qt_widgets():
    """Delete widgets a test leaves behind.

    A Qt widget built in a test outlives it unless something deletes it, and the shared
    QApplication keeps every one alive for the rest of the session. Anything that walks
    the whole widget tree then gets slower with each test that has already run — applying
    the app stylesheet in the dark-theme tests reached tens of seconds apiece that way,
    and the full suite stopped finishing in a sane amount of time.
    """
    yield
    if "PySide6.QtWidgets" not in sys.modules:
        return
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        try:
            widget.close()
            widget.deleteLater()
        except RuntimeError:
            pass  # already deleted on the C++ side
    # deleteLater only takes effect when a running event loop unwinds, which never
    # happens here, so drain the DeferredDelete queue by hand.
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    app.processEvents()
