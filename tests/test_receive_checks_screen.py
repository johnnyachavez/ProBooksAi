"""Receive Checks screen — structure only (no DB)."""

from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QApplication, QCheckBox, QDoubleSpinBox, QPushButton, QTableWidget

from desktop_app.receive_checks_screen import ReceiveChecksScreen


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_receive_checks_screen_table_and_header(qapp: QApplication) -> None:
    w = ReceiveChecksScreen()
    t = w.findChild(QTableWidget)
    assert t is not None
    assert t.objectName() == "receiveChecksTable"
    assert t.columnCount() == 6
    assert t.rowCount() == ReceiveChecksScreen._N_ROWS
    assert t.horizontalHeaderItem(1).text() == "Date"
    assert t.horizontalHeaderItem(2).text() == "Number"
    assert t.horizontalHeaderItem(5).text() == "Payment"
    assert isinstance(t.cellWidget(0, 0), QCheckBox)
    assert isinstance(t.cellWidget(0, 5), QDoubleSpinBox)


def test_receive_checks_totals_update_when_checked(qapp: QApplication) -> None:
    w = ReceiveChecksScreen()
    t = w.findChild(QTableWidget)
    assert t is not None
    cb = t.cellWidget(0, 0)
    spin = t.cellWidget(0, 5)
    assert isinstance(cb, QCheckBox)
    assert isinstance(spin, QDoubleSpinBox)
    cb.setChecked(True)
    spin.setValue(100.0)
    assert "1" in w._lbl_total_selected.text()
    assert "100" in w._lbl_total_payment.text().replace(",", "")


def test_receive_checks_apply_credits_button_present(qapp: QApplication) -> None:
    w = ReceiveChecksScreen()
    texts = [b.text() for b in w.findChildren(QPushButton)]
    assert "Apply Credits" in texts
