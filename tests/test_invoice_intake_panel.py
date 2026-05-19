"""Invoice Intake panel — queue structure (foundation)."""

from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QTableWidget

from desktop_app.invoice_intake_panel import InvoiceIntakePanel, _INTAKE_COLS


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_invoice_intake_queue_table_columns(qapp: QApplication) -> None:
    w = InvoiceIntakePanel()
    t = w.findChild(QTableWidget, "invoiceIntakeQueueTable")
    assert t is not None
    assert t.columnCount() == len(_INTAKE_COLS)
    for i, name in enumerate(_INTAKE_COLS):
        assert t.horizontalHeaderItem(i).text() == name


def test_invoice_intake_has_import_actions(qapp: QApplication) -> None:
    w = InvoiceIntakePanel()
    texts = [b.text() for b in w.findChildren(QPushButton)]
    assert "Import PDF…" in texts
    assert "Import image…" in texts
    assert "Paste text from clipboard" in texts
    assert "Remove selected" in texts


def test_invoice_intake_shows_title_and_flow(qapp: QApplication) -> None:
    w = InvoiceIntakePanel()
    labels = [lb.text() for lb in w.findChildren(QLabel)]
    assert any("Invoice Intake" in x for x in labels)
    assert any("source document in" in x or "Stage PDFs" in x or "Extract" in x for x in labels)
