"""End-to-end New Company setup flow: identity save + backups folder + first-run gate."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDialog

from probooksai.bank_import import BankDatabase
from probooksai.company_identity import (
    get_company_identity,
    is_company_setup_complete,
    save_company_identity,
)
from probooksai.extensions_schema import apply_extensions


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _wizard_payload() -> dict[str, str]:
    return {
        "name": "Wizard Co",
        "address": "10 Setup Way",
        "phone": "555-7777",
        "email": "wizard@setup.example",
        "tax_id": "11-2222222",
        "business_type": "LLC",
        "tax_structure": "LLC – Multi-member (1065)",
    }


def _make_main_window(qapp: QApplication, db_path: Path):
    """Build a MainWindow against a pre-created blank company .db."""
    db = BankDatabase(str(db_path))
    db.close()
    QSettings().setValue("company_file_setup_prompted", True)
    from desktop_app.main import MainWindow

    return MainWindow(db_path=str(db_path))


def test_on_create_company_file_writes_full_identity_and_backup_folder(
    qapp: QApplication, tmp_path: Path
) -> None:
    """``_on_create_company_file`` saves all 7 fields and creates ``backups/<stem>-initial.db``."""
    seed = tmp_path / "seed.db"
    target = tmp_path / "wizard_root" / "wizard_co.db"
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
            w._on_create_company_file()
        assert target.is_file(), "Working company .db must be created at the chosen path."
        backups_dir = target.parent / "backups"
        assert backups_dir.is_dir(), "Wizard must create a sibling backups/ folder."
        initial = backups_dir / f"{target.stem}-initial.db"
        assert initial.is_file(), "Wizard must write <stem>-initial.db on first save."
        identity = get_company_identity(w._bank_db._conn)
        assert identity["name"] == "Wizard Co"
        assert identity["business_type"] == "LLC"
        assert identity["tax_structure"] == "LLC – Multi-member (1065)"
        assert identity["tax_id"] == "11-2222222"
        assert is_company_setup_complete(w._bank_db._conn) is True
    finally:
        w._bank_db.close()
        w._db.close()


def test_route_into_setup_when_company_incomplete_does_not_open_wizard(
    qapp: QApplication, tmp_path: Path
) -> None:
    """A loaded company with missing identity must never auto-open New Company."""
    seed = tmp_path / "incomplete.db"
    w = _make_main_window(qapp, seed)
    try:
        assert is_company_setup_complete(w._bank_db._conn) is False, (
            "Bare BankDatabase must report setup-incomplete (no business_type / tax_structure)."
        )
        with patch.object(w, "_on_create_company_file") as mocked:
            w._route_into_setup_if_company_incomplete()
            w._maybe_prompt_first_company_file_setup()
            mocked.assert_not_called()
    finally:
        w._bank_db.close()
        w._db.close()


def test_route_into_setup_skips_when_company_complete(
    qapp: QApplication, tmp_path: Path
) -> None:
    """A fully set-up file does NOT re-trigger the wizard on every launch."""
    seed = tmp_path / "complete.db"
    db = BankDatabase(str(seed))
    apply_extensions(db._conn)
    save_company_identity(
        db._conn,
        name="Already Done LLC",
        business_type="LLC",
        tax_structure="LLC – Single-member (disregarded)",
    )
    db.close()
    QSettings().setValue("company_file_setup_prompted", True)
    from desktop_app.main import MainWindow

    w = MainWindow(db_path=str(seed))
    try:
        with patch.object(w, "_on_create_company_file") as mocked:
            w._route_into_setup_if_company_incomplete()
            mocked.assert_not_called()
    finally:
        w._bank_db.close()
        w._db.close()


def test_create_company_file_cancel_does_not_switch_or_create(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Cancel / X on New Company must not create a .db or change the open company."""
    seed = tmp_path / "open.db"
    w = _make_main_window(qapp, seed)
    try:
        before = w._db_path
        with patch(
            "desktop_app.main.CreateCompanyFileDialog"
        ) as MockDlgCls, patch.object(w, "_switch_company_database") as switch:
            instance = MockDlgCls.return_value
            instance.exec.return_value = QDialog.DialogCode.Rejected
            w._on_create_company_file()
            instance.identity_values.assert_not_called()
            switch.assert_not_called()
        assert w._db_path == before
    finally:
        w._bank_db.close()
        w._db.close()


def test_file_menu_action_text_says_new_company(
    qapp: QApplication, tmp_path: Path
) -> None:
    """File menu surfaces the New Company entry point (renamed from Create Company File)."""
    seed = tmp_path / "menu.db"
    w = _make_main_window(qapp, seed)
    try:
        file_menu = None
        for menu_action in w.menuBar().actions():
            if (menu_action.text() or "").replace("&", "").strip().lower() == "file":
                file_menu = menu_action.menu()
                break
        assert file_menu is not None, "MainWindow must expose a File menu."
        labels = [a.text().replace("&", "") for a in file_menu.actions()]
        assert any(label.startswith("New Company") for label in labels), (
            f"Expected 'New Company…' under File, got: {labels!r}"
        )
        assert not any(label.startswith("Create Company File") for label in labels), (
            f"Old label 'Create Company File…' must be gone, got: {labels!r}"
        )
        assert any(label.startswith("Company Setup") for label in labels), (
            f"Expected 'Company Setup…' under File, got: {labels!r}"
        )
    finally:
        w._bank_db.close()
        w._db.close()
