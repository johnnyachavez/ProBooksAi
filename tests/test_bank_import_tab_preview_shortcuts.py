"""Tests for Bank Import batch preview keyboard shortcuts (desktop_app.bank_import_tab)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTableWidgetItem

from probooksai.bank_import import BankDatabase


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_import_preview_ctrl_shift_b_without_register_tab_shows_tip(
    qapp: QApplication, tmp_path: Path
) -> None:
    from desktop_app.bank_import_tab import BankImportTab

    db_path = tmp_path / "bit_preview_b.db"
    db = BankDatabase(str(db_path))
    try:
        with patch.object(BankImportTab, "_refresh_accounts", lambda self: None):
            tab = BankImportTab(db, register_tab=None)
        tab._txn_table.setRowCount(1)
        date_it = QTableWidgetItem("2024-01-01")
        date_it.setData(Qt.ItemDataRole.UserRole, 100)
        tab._txn_table.setItem(0, 0, date_it)
        tab._txn_table.setCurrentCell(0, 0)
        with patch("desktop_app.bank_import_tab.message_box_information_ok") as m:
            tab._import_preview_ctrl_shift_b_open_linked_business()
        m.assert_called_once()
        assert m.call_args[0][1] == "Business link"
    finally:
        db.close()


def test_import_preview_ctrl_shift_b_no_current_row_shows_tip(
    qapp: QApplication, tmp_path: Path
) -> None:
    from desktop_app.bank_import_tab import BankImportTab

    class _Reg:
        def __init__(self) -> None:
            self.tids: list[int] = []

        def open_linked_business_record_for_transaction_id(self, tid: int) -> None:
            self.tids.append(int(tid))

    db_path = tmp_path / "bit_preview_b_row.db"
    db = BankDatabase(str(db_path))
    try:
        reg = _Reg()
        with patch.object(BankImportTab, "_refresh_accounts", lambda self: None):
            tab = BankImportTab(db, register_tab=reg)
        tab._txn_table.setRowCount(1)
        date_it = QTableWidgetItem("2024-01-01")
        date_it.setData(Qt.ItemDataRole.UserRole, 7)
        tab._txn_table.setItem(0, 0, date_it)
        tab._txn_table.selectionModel().clearCurrentIndex()
        with patch("desktop_app.bank_import_tab.message_box_information_ok") as m:
            tab._import_preview_ctrl_shift_b_open_linked_business()
        m.assert_called_once()
        assert reg.tids == []
    finally:
        db.close()


def test_import_preview_ctrl_shift_b_no_txn_id_shows_tip(
    qapp: QApplication, tmp_path: Path
) -> None:
    from desktop_app.bank_import_tab import BankImportTab

    class _Reg:
        def __init__(self) -> None:
            self.tids: list[int] = []

        def open_linked_business_record_for_transaction_id(self, tid: int) -> None:
            self.tids.append(int(tid))

    db_path = tmp_path / "bit_preview_b_tid.db"
    db = BankDatabase(str(db_path))
    try:
        reg = _Reg()
        with patch.object(BankImportTab, "_refresh_accounts", lambda self: None):
            tab = BankImportTab(db, register_tab=reg)
        tab._txn_table.setRowCount(1)
        date_it = QTableWidgetItem("practice")
        tab._txn_table.setItem(0, 0, date_it)
        tab._txn_table.setCurrentCell(0, 0)
        with patch("desktop_app.bank_import_tab.message_box_information_ok") as m:
            tab._import_preview_ctrl_shift_b_open_linked_business()
        m.assert_called_once()
        assert reg.tids == []
    finally:
        db.close()


def test_import_preview_ctrl_shift_b_delegates_to_register_tab(
    qapp: QApplication, tmp_path: Path
) -> None:
    from desktop_app.bank_import_tab import BankImportTab

    class _Reg:
        def __init__(self) -> None:
            self.tids: list[int] = []

        def open_linked_business_record_for_transaction_id(self, tid: int) -> None:
            self.tids.append(int(tid))

    db_path = tmp_path / "bit_preview_b_ok.db"
    db = BankDatabase(str(db_path))
    try:
        reg = _Reg()
        with patch.object(BankImportTab, "_refresh_accounts", lambda self: None):
            tab = BankImportTab(db, register_tab=reg)
        tab._txn_table.setRowCount(1)
        date_it = QTableWidgetItem("2024-01-01")
        date_it.setData(Qt.ItemDataRole.UserRole, 42)
        tab._txn_table.setItem(0, 0, date_it)
        tab._txn_table.setCurrentCell(0, 0)
        tab._import_preview_ctrl_shift_b_open_linked_business()
        assert reg.tids == [42]
    finally:
        db.close()


def test_import_preview_double_click_delegates_without_navigable_match(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Double-click always forwards to the register tab (same prompts as Match column)."""
    from desktop_app.bank_import_tab import BankImportTab

    class _Reg:
        def __init__(self) -> None:
            self.tids: list[int] = []

        def open_linked_business_record_for_transaction_id(self, tid: int) -> None:
            self.tids.append(int(tid))

    db_path = tmp_path / "bit_preview_dbl_none.db"
    db = BankDatabase(str(db_path))
    try:
        reg = _Reg()
        with patch.object(BankImportTab, "_refresh_accounts", lambda self: None):
            tab = BankImportTab(db, register_tab=reg)
        tab._txn_table.setRowCount(1)
        date_it = QTableWidgetItem("2024-01-01")
        date_it.setData(Qt.ItemDataRole.UserRole, 99)
        tab._txn_table.setItem(0, 0, date_it)
        with patch("desktop_app.bank_import_tab.business.get_bank_match", return_value=None):
            tab._on_import_preview_cell_double_clicked(0, 1)
        assert reg.tids == [99]
    finally:
        db.close()


def test_import_preview_double_click_with_match_delegates(
    qapp: QApplication, tmp_path: Path
) -> None:
    from desktop_app.bank_import_tab import BankImportTab

    class _Reg:
        def __init__(self) -> None:
            self.tids: list[int] = []

        def open_linked_business_record_for_transaction_id(self, tid: int) -> None:
            self.tids.append(int(tid))

    db_path = tmp_path / "bit_preview_dbl_ok.db"
    db = BankDatabase(str(db_path))
    try:
        reg = _Reg()
        with patch.object(BankImportTab, "_refresh_accounts", lambda self: None):
            tab = BankImportTab(db, register_tab=reg)
        tab._txn_table.setRowCount(1)
        date_it = QTableWidgetItem("2024-01-01")
        date_it.setData(Qt.ItemDataRole.UserRole, 42)
        tab._txn_table.setItem(0, 0, date_it)
        fake_bm = {"link_type": "ar_payment", "link_id": 9}
        with patch(
            "desktop_app.bank_import_tab.business.get_bank_match",
            return_value=fake_bm,
        ):
            tab._on_import_preview_cell_double_clicked(0, 2)
        assert reg.tids == [42]
    finally:
        db.close()
