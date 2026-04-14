"""Customer Corral placeholder dialog (File → Customers)."""

from __future__ import annotations

import sys

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton

from desktop_app.customer_corral_dialog import CustomerCorralDialog


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_customer_corral_dialog_fields_and_buttons(qapp: QApplication) -> None:
    d = CustomerCorralDialog()
    assert d.windowTitle() == "Customer Corral"
    edits = d.findChildren(QLineEdit)
    assert len(edits) >= 10
    labels = [b.text() for b in d.findChildren(QPushButton)]
    assert "Save" in labels
    assert any("Save" in x and "New" in x for x in labels)
    assert "Clear" in labels
    d._clear_form()
    assert d._customer_name.text() == ""
    d.close()


def test_customer_corral_dialog_exec_closes(qapp: QApplication) -> None:
    d = CustomerCorralDialog()
    QTimer.singleShot(0, d.reject)
    rc = d.exec()
    assert rc == int(d.DialogCode.Rejected)
