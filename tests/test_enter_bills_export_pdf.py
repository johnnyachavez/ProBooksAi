"""Enter Bills — Export PDF persists bill and writes chosen path."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from desktop_app.enter_bills_screen import EnterBillsScreen
from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import apply_extensions
from probooksai import business


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_enter_bills_export_pdf_saves_to_chosen_path(
    qapp: QApplication, tmp_path
) -> None:
    db_path = tmp_path / "eb_exp.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    business.add_vendor(db._conn, "Supp")
    w = EnterBillsScreen(ap_conn=db._conn)
    w._vendor.setCurrentIndex(1)
    w._vendor_inv.setText("INV-EXP")
    amt = w._table.cellWidget(0, 1)
    assert amt is not None
    amt.setValue(20.0)
    out = tmp_path / "MyBill.pdf"
    with patch(
        "desktop_app.enter_bills_screen.QFileDialog.getSaveFileName",
        return_value=(str(out), "PDF files (*.pdf)"),
    ):
        QTest.mouseClick(w._btn_export_pdf, Qt.MouseButton.LeftButton)
        qapp.processEvents()
    assert out.is_file()
    rows = business.list_bills(db._conn)
    assert len(rows) == 1
    db.close()
