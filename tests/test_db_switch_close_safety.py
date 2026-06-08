"""Regression tests for the ``_switch_company_database`` crash where an old
``RegisterTab`` queried a closed SQLite connection during tab teardown.

Origin
------
Creating a New Company ran ``MainWindow._switch_company_database`` which
closed both DB handles, then called ``_load_company_at_path`` →
``_rebuild_bank_related_tabs`` → ``_teardown_main_tabs_for_rebuild``. Each
``self._tabs.removeTab(0)`` made a sibling tab become current and fired its
``showEvent``; the old ``RegisterTab.showEvent`` then called
``self._db.list_bank_accounts()`` against the just-closed BankDatabase and
raised ``sqlite3.ProgrammingError: Cannot operate on a closed database``.

These tests cover:

1. ``BankDatabase.is_closed`` flips on ``close()`` and stays idempotent.
2. ``RegisterTab.showEvent`` is a no-op when its bank DB has been closed.
3. ``RegisterTab._refresh_account_combo`` is a no-op when its bank DB has
   been closed (defence in depth — does not raise).
4. ``MainWindow._switch_company_database`` (driven via the New Company wizard
   path) survives a full rebuild without raising ``sqlite3.ProgrammingError``,
   and the ``_switching_database`` flag is cleared on completion.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QEvent, QSettings
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QApplication, QDialog

from probooksai.bank_import import BankDatabase
from probooksai.coa_db import COADatabase
from probooksai.extensions_schema import apply_extensions
from probooksai.gl import GLDatabase


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


# ---------------------------------------------------------------------------
# 1. BankDatabase.is_closed
# ---------------------------------------------------------------------------

def test_bank_database_is_closed_flag_starts_false_and_flips_on_close(tmp_path: Path) -> None:
    db = BankDatabase(str(tmp_path / "ic.db"))
    assert db.is_closed is False
    db.close()
    assert db.is_closed is True


def test_bank_database_close_is_idempotent(tmp_path: Path) -> None:
    """Second ``close()`` is a no-op so ``MainWindow`` close paths can call it freely."""
    db = BankDatabase(str(tmp_path / "ic2.db"))
    db.close()
    db.close()
    assert db.is_closed is True


def test_bank_database_is_closed_blocks_list_bank_accounts_via_guard(tmp_path: Path) -> None:
    """After close the guard sees ``is_closed`` and the underlying call would raise."""
    db = BankDatabase(str(tmp_path / "ic3.db"))
    db.close()
    assert db.is_closed is True
    with pytest.raises(sqlite3.ProgrammingError):
        db.list_bank_accounts()


# ---------------------------------------------------------------------------
# 2 + 3. RegisterTab guards
# ---------------------------------------------------------------------------

def _make_register_tab(qapp: QApplication, tmp_path: Path):
    """Build a real ``RegisterTab`` against an isolated BankDatabase + COADatabase."""
    from desktop_app.register_tab import RegisterTab

    db_path = tmp_path / "reg.db"
    bank_db = BankDatabase(str(db_path))
    apply_extensions(bank_db._conn)
    coa_db = COADatabase(bank_db._conn)
    coa_db.seed_from_workbook()
    gl_db = GLDatabase(bank_db._conn)
    tab = RegisterTab(bank_db, coa_db, gl_db)
    return tab, bank_db


def test_register_tab_show_event_is_safe_after_db_close(qapp: QApplication, tmp_path: Path) -> None:
    """``showEvent`` must not raise ``sqlite3.ProgrammingError`` against a closed bank DB."""
    tab, bank_db = _make_register_tab(qapp, tmp_path)
    try:
        bank_db.close()
        assert tab._is_db_alive() is False
        ev = QShowEvent()
        # If the guard is missing this raises ``sqlite3.ProgrammingError``.
        tab.showEvent(ev)
    finally:
        tab.deleteLater()


def test_register_tab_refresh_account_combo_is_safe_after_db_close(
    qapp: QApplication, tmp_path: Path
) -> None:
    """``_refresh_account_combo`` short-circuits cleanly when the bank DB is closed."""
    tab, bank_db = _make_register_tab(qapp, tmp_path)
    try:
        bank_db.close()
        tab._refresh_account_combo()
    finally:
        tab.deleteLater()


def test_register_tab_reload_current_is_safe_after_db_close(
    qapp: QApplication, tmp_path: Path
) -> None:
    """``_reload_current`` short-circuits cleanly when the bank DB is closed."""
    tab, bank_db = _make_register_tab(qapp, tmp_path)
    try:
        bank_db.close()
        tab._reload_current()
    finally:
        tab.deleteLater()


def test_register_tab_is_db_alive_false_when_db_attribute_missing(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Defensive: ``_is_db_alive`` returns False if ``_db`` is missing or None."""
    tab, bank_db = _make_register_tab(qapp, tmp_path)
    try:
        tab._db = None
        assert tab._is_db_alive() is False
    finally:
        bank_db.close()
        tab.deleteLater()


# ---------------------------------------------------------------------------
# 4. End-to-end MainWindow._switch_company_database does not crash
# ---------------------------------------------------------------------------

def _wizard_payload() -> dict[str, str]:
    return {
        "name": "Switch Co",
        "address": "1 Switch Way",
        "phone": "555-3333",
        "email": "switch@example.com",
        "tax_id": "22-3333333",
        "business_type": "LLC",
        "tax_structure": "LLC – Multi-member (1065)",
    }


def _make_main_window(qapp: QApplication, db_path: Path):
    """Build a MainWindow against a pre-created blank company .db (welcome card suppressed)."""
    db = BankDatabase(str(db_path))
    db.close()
    QSettings().setValue("company_file_setup_prompted", True)
    from desktop_app.main import MainWindow

    return MainWindow(db_path=str(db_path))


def test_new_company_creation_does_not_raise_closed_db_error(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Driving ``_on_create_company_file`` end-to-end must not raise the crash from the bug report.

    Before the fix this raised ``sqlite3.ProgrammingError: Cannot operate on a closed
    database`` from the old ``RegisterTab.showEvent`` during tab teardown.
    """
    seed = tmp_path / "seed_switch.db"
    target = tmp_path / "switched_root" / "switched.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    w = _make_main_window(qapp, seed)
    try:
        with patch(
            "desktop_app.main.CreateCompanyFileDialog"
        ) as MockDlgCls, patch(
            "desktop_app.main.QFileDialog.getSaveFileName",
            return_value=(str(target), "SQLite Database (*.db)"),
        ):
            instance = MockDlgCls.return_value
            instance.exec.return_value = QDialog.DialogCode.Accepted
            instance.identity_values.return_value = _wizard_payload()
            # Must not raise sqlite3.ProgrammingError
            w._on_create_company_file()
        assert target.is_file()
        assert (target.parent / "backups" / f"{target.stem}-initial.db").is_file()
        # New bank_db must be a fresh, open handle (not the closed one held by the
        # torn-down RegisterTab).
        assert w._bank_db.is_closed is False
        # Switch flag must be cleared even though the rebuild succeeded.
        assert w._switching_database is False
        # The new RegisterTab is bound to the new BankDatabase, not the old.
        assert w._register_tab._db is w._bank_db
        assert w._register_tab._is_db_alive() is True
    finally:
        w._bank_db.close()
        w._db.close()


def test_switching_database_flag_reset_even_if_load_raises(
    qapp: QApplication, tmp_path: Path
) -> None:
    """``_switch_company_database`` must clear ``_switching_database`` via ``finally`` on errors."""
    seed = tmp_path / "seed_flag.db"
    target = tmp_path / "switched_flag" / "switched_flag.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    w = _make_main_window(qapp, seed)
    try:
        with patch.object(
            w, "_load_company_at_path", side_effect=RuntimeError("boom")
        ):
            with pytest.raises(RuntimeError):
                w._switch_company_database(str(target), create_new=True)
        assert w._switching_database is False
    finally:
        # Replace the destroyed handles with a fresh one so finally cleanup works.
        try:
            w._bank_db.close()
        except Exception:
            pass
        try:
            w._db.close()
        except Exception:
            pass
