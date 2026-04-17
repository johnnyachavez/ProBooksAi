"""Invoice Intake panel — queue structure (foundation)."""

from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QTableWidget

from desktop_app.invoice_intake_panel import InvoiceIntakePanel, _INTAKE_COLS
from desktop_app.invoice_screen import InvoiceScreen
from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import apply_extensions


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
    assert "Send to Manual Invoice" in texts


def test_invoice_intake_send_draft_disabled_without_invoice_screen(qapp: QApplication) -> None:
    w = InvoiceIntakePanel()
    assert not w._btn_send_draft.isEnabled()


def test_invoice_intake_send_to_manual_invoice_updates_queue_and_memo(
    qapp: QApplication, tmp_path
) -> None:
    db_path = tmp_path / "intake_send.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    pdf = tmp_path / "ticket.pdf"
    pdf.write_bytes(b"%PDF-1.4 minimal")
    screen = InvoiceScreen(ap_conn=db._conn)
    intake = screen._invoice_intake
    intake._append_row(
        source_display="ticket.pdf",
        kind="PDF",
        path=str(pdf),
        notes="Verify totals",
    )
    intake._on_send_to_manual_invoice()
    assert screen._invoice_tabs.currentIndex() == 0
    assert "ticket.pdf" in screen._invoice_memo_notes
    assert "Verify totals" in screen._invoice_memo_notes
    screen.show()
    qapp.processEvents()
    assert screen._invoice_intake_handoff_banner.isVisible()
    st = intake._table.item(0, 3)
    assert st is not None
    assert st.text() == "Sent to draft"
    db.close()


def test_invoice_intake_shows_title_and_flow(qapp: QApplication) -> None:
    w = InvoiceIntakePanel()
    labels = [lb.text() for lb in w.findChildren(QLabel)]
    assert any("Invoice Intake" in x for x in labels)
    assert any("Send to Manual Invoice" in x for x in labels)
