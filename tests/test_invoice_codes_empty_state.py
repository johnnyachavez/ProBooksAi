"""Regression: Codes tab shows an empty-state card + Add button when there are no items."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton, QTableWidget

from desktop_app.invoice_codes_screen import InvoiceCodesScreen
from probooksai import business
from probooksai.bank_import import BankDatabase
from probooksai.coa_db import COADatabase
from probooksai.extensions_schema import apply_extensions


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def env(tmp_path: Path):
    b = BankDatabase(str(tmp_path / "co.db"))
    apply_extensions(b._conn)
    coa = COADatabase(b._conn)
    return b, coa


def test_codes_screen_shows_empty_state_when_no_items(qapp, env) -> None:
    b, coa = env
    w = InvoiceCodesScreen(ap_conn=b._conn, coa_db=coa)
    try:
        empty = w.findChild(QFrame, "itemListEmptyState")
        assert empty is not None
        assert not empty.isHidden()
        headline = w.findChild(QLabel, "itemListEmptyHeadline")
        assert headline is not None
        assert "No items" in headline.text()
        add_btn = w.findChild(QPushButton, "itemListEmptyAdd")
        assert add_btn is not None
        assert add_btn.isEnabled()
        table = w.findChild(QTableWidget, "itemListTable")
        assert table is not None
        assert table.isHidden()
    finally:
        w.deleteLater()
        b.close()


def test_codes_screen_hides_empty_state_after_items_added(qapp, env) -> None:
    b, coa = env
    business.replace_invoice_item_codes(
        b._conn,
        [
            {
                "code": "Labor",
                "description": "Hourly service",
                "item_type": "Service",
                "coa_account": "4000 – Sales",
                "rate_value": 85.0,
                "rate_kind": "amount",
                "sort_order": 0,
            }
        ],
    )
    w = InvoiceCodesScreen(ap_conn=b._conn, coa_db=coa)
    try:
        empty = w.findChild(QFrame, "itemListEmptyState")
        assert empty is not None
        assert empty.isHidden()
        table = w.findChild(QTableWidget, "itemListTable")
        assert table is not None
        assert not table.isHidden()
        assert table.rowCount() == 1
    finally:
        w.deleteLater()
        b.close()


def test_empty_state_add_button_opens_edit_item_via_slot(qapp, env, monkeypatch) -> None:
    b, coa = env
    w = InvoiceCodesScreen(ap_conn=b._conn, coa_db=coa)
    try:
        add_btn = w.findChild(QPushButton, "itemListEmptyAdd")
        assert add_btn is not None
        opened: list[bool] = []
        monkeypatch.setattr(w, "_run_edit_dialog", lambda item_id=None: opened.append(True))
        add_btn.click()
        qapp.processEvents()
        assert opened == [True]
    finally:
        w.deleteLater()
        b.close()
