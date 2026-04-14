"""Pay Bills screen — structure only (no DB)."""

from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QApplication, QCheckBox, QDoubleSpinBox, QTableWidget

from desktop_app.pay_bills_screen import PayBillsScreen


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_pay_bills_screen_table_columns_and_rows(qapp: QApplication) -> None:
    w = PayBillsScreen()
    t = w.findChild(QTableWidget)
    assert t is not None
    assert t.columnCount() == 10
    assert t.rowCount() == PayBillsScreen._N_ROWS
    assert t.horizontalHeaderItem(1).text() == "Payee / Vendor"
    assert t.horizontalHeaderItem(8).text() == "Payment"


def test_pay_bills_screen_payment_cells_and_checkboxes(qapp: QApplication) -> None:
    w = PayBillsScreen()
    t = w.findChild(QTableWidget)
    assert t is not None
    assert isinstance(t.cellWidget(0, 0), QCheckBox)
    assert isinstance(t.cellWidget(0, 8), QDoubleSpinBox)


def test_pay_bills_clear_selection_resets(qapp: QApplication) -> None:
    w = PayBillsScreen()
    t = w.findChild(QTableWidget)
    cb = t.cellWidget(0, 0)
    assert isinstance(cb, QCheckBox)
    spin = t.cellWidget(0, 8)
    assert isinstance(spin, QDoubleSpinBox)
    cb.setChecked(True)
    spin.setValue(12.34)
    w._on_clear_selection()
    assert not cb.isChecked()
    assert spin.value() == 0.0
