"""UI-shell tests for the QB Pro-style Asset Accounts tab."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QLabel,
    QPushButton,
    QTableWidget,
)

from desktop_app.asset_accounts_tab import AssetAccountsTab
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


@pytest.fixture
def env(tmp_path: Path):
    """Full company DB: bank + extensions + CoA + GL."""
    b = BankDatabase(db_path=str(tmp_path / "co.db"))
    apply_extensions(b._conn)
    coa = COADatabase(b._conn)
    GLDatabase(b._conn)
    return coa, b._conn


def _seed_two_asset_accounts(coa: COADatabase) -> dict[str, int]:
    ids = {
        "truck": coa.add_account("1500", "Trucks", "fixed_asset", sub_type="Vehicles"),
        "deposit": coa.add_account("1600", "Security deposit", "other_asset"),
        "cash": coa.add_account("1000", "Cash – Checking", "bank"),
        "ap": coa.add_account("2000", "Accounts payable", "current_liability"),
    }
    return ids


def test_asset_tab_chrome_widgets_are_present(qapp, env) -> None:
    coa, conn = env
    tab = AssetAccountsTab(coa_db=coa, gl_conn=conn)
    try:
        assert tab.findChild(QPushButton, "assetsGoto") is not None
        assert tab.findChild(QPushButton, "assetsRefresh") is not None
        combo = tab.findChild(QComboBox, "assetsAccountCombo")
        assert combo is not None
        table = tab.findChild(QTableWidget, "assetsRegisterTable")
        assert table is not None
        assert table.columnCount() == 7
        headers = [table.horizontalHeaderItem(i).text() for i in range(7)]
        assert headers == ["Date", "Type", "Ref", "Description", "Debit", "Credit", "Balance"]
        assert tab.findChild(QLabel, "assetsRowCount") is not None
        assert tab.findChild(QLabel, "assetsEndingBalance") is not None
    finally:
        tab.deleteLater()


def test_asset_tab_shows_placeholder_when_no_accounts(qapp, env) -> None:
    coa, conn = env
    tab = AssetAccountsTab(coa_db=coa, gl_conn=conn)
    try:
        combo = tab.findChild(QComboBox, "assetsAccountCombo")
        assert combo is not None
        assert combo.count() == 1
        assert combo.itemText(0) == "(no asset accounts)"
        assert not combo.isEnabled()
        table = tab.findChild(QTableWidget, "assetsRegisterTable")
        assert table.rowCount() == 0
        ending = tab.findChild(QLabel, "assetsEndingBalance").text()
        assert "0.00" in ending
    finally:
        tab.deleteLater()


def test_asset_tab_lists_non_bank_asset_accounts_only(qapp, env) -> None:
    coa, conn = env
    _seed_two_asset_accounts(coa)
    tab = AssetAccountsTab(coa_db=coa, gl_conn=conn)
    try:
        combo = tab.findChild(QComboBox, "assetsAccountCombo")
        assert combo.count() == 2
        labels = [combo.itemText(i) for i in range(2)]
        assert any("1500" in lab and "Trucks" in lab for lab in labels)
        assert any("1600" in lab and "Security deposit" in lab for lab in labels)
        assert not any("Cash" in lab for lab in labels)
    finally:
        tab.deleteLater()


def test_asset_tab_shows_gl_activity_for_selected_account(qapp, env) -> None:
    coa, conn = env
    _seed_two_asset_accounts(coa)
    gl = GLDatabase(conn)
    gl.create_journal_entry(
        entry_date="2024-05-01",
        memo="Buy truck",
        lines=[
            {"account": "1500 – Trucks", "debit": 25000.0, "credit": 0.0, "description": "F-250"},
            {"account": "2000 – Accounts payable", "debit": 0.0, "credit": 25000.0, "description": ""},
        ],
    )
    tab = AssetAccountsTab(coa_db=coa, gl_conn=conn)
    try:
        combo = tab.findChild(QComboBox, "assetsAccountCombo")
        for i in range(combo.count()):
            if "1500" in combo.itemText(i):
                combo.setCurrentIndex(i)
                break
        tab.reload()
        table = tab.findChild(QTableWidget, "assetsRegisterTable")
        assert table.rowCount() == 1
        assert table.item(0, 0).text() == "2024-05-01"
        assert "25,000" in table.item(0, 4).text()
        assert table.item(0, 5).text() == ""
        assert "25,000.00" in table.item(0, 6).text()
        ending = tab.findChild(QLabel, "assetsEndingBalance").text()
        assert "25,000.00" in ending
    finally:
        tab.deleteLater()


def test_asset_tab_switching_account_reloads_the_grid(qapp, env) -> None:
    coa, conn = env
    _seed_two_asset_accounts(coa)
    gl = GLDatabase(conn)
    gl.create_journal_entry(
        entry_date="2024-01-01",
        memo="",
        lines=[
            {"account": "1500 – Trucks", "debit": 100.0, "credit": 0.0, "description": ""},
            {"account": "2000 – Accounts payable", "debit": 0.0, "credit": 100.0, "description": ""},
        ],
    )
    tab = AssetAccountsTab(coa_db=coa, gl_conn=conn)
    try:
        combo = tab.findChild(QComboBox, "assetsAccountCombo")
        for i in range(combo.count()):
            if "1600" in combo.itemText(i):
                combo.setCurrentIndex(i)
                break
        table = tab.findChild(QTableWidget, "assetsRegisterTable")
        assert table.rowCount() == 0
        ending = tab.findChild(QLabel, "assetsEndingBalance").text()
        assert "0.00" in ending
        for i in range(combo.count()):
            if "1500" in combo.itemText(i):
                combo.setCurrentIndex(i)
                break
        assert table.rowCount() == 1
    finally:
        tab.deleteLater()
