"""Invoice Intake panel — queue structure (foundation)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QApplication,
    QDoubleSpinBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
)

from desktop_app.enter_bills_screen import EnterBillsScreen
from desktop_app.invoice_intake_panel import InvoiceIntakePanel, _INTAKE_COLS
from desktop_app.invoice_screen import InvoiceScreen
from probooksai import business
from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import apply_extensions

SAMPLE_DISPATCH_CSV = Path(__file__).resolve().parent / "fixtures" / "dispatch_intake_sample.csv"


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
    assert "Import dispatch CSV…" in texts
    assert "Load Google Sheet…" in texts
    assert "Remove selected" in texts
    assert "Send to Manual Invoice" in texts
    assert "Send to Enter Bills" in texts


def test_invoice_intake_send_draft_disabled_without_invoice_screen(qapp: QApplication) -> None:
    w = InvoiceIntakePanel()
    assert not w._btn_send_draft.isEnabled()
    assert not w._btn_send_bill.isEnabled()


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


def test_invoice_intake_pdf_review_uses_extracted_text_for_fields(
    qapp: QApplication, tmp_path, monkeypatch
) -> None:
    """After PDF text extraction, review panel runs the same labeled-field pass as pasted text."""
    db_path = tmp_path / "intake_pdf_review.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    def fake_extract(kind: str, path: str) -> tuple[str, str | None]:
        return (
            "Invoice Date: 2025-06-15\nTicket # T-99\nCustomer: Acme Corp\n",
            None,
        )

    monkeypatch.setattr(
        "desktop_app.invoice_intake_panel.extract_text_for_intake_kind",
        fake_extract,
    )
    screen = InvoiceScreen(ap_conn=db._conn)
    intake = screen._invoice_intake
    intake._append_row(source_display="doc.pdf", kind="PDF", path=str(pdf))
    qapp.processEvents()
    review = intake._txt_extracted.toPlainText()
    assert "T-99" in review
    assert "Acme Corp" in review
    att = intake._txt_attachment.toPlainText()
    assert "Extracted text length:" in att
    assert "Raw extracted text" in att
    db.close()


def test_dispatch_csv_three_3235_loads_one_invoice_skips_blank_rate(
    qapp: QApplication, tmp_path
) -> None:
    db_path = tmp_path / "dispatch_inv.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "Sample Materials Co")
    screen = InvoiceScreen(ap_conn=db._conn)
    bills = EnterBillsScreen(ap_conn=db._conn)
    screen.set_enter_bills_screen(bills)
    intake = screen._invoice_intake
    n = intake.load_dispatch_csv_path(str(SAMPLE_DISPATCH_CSV), notify=False)
    assert n == 5
    statuses = [intake._table.item(r, 3).text() for r in range(intake._table.rowCount())]
    assert statuses[0] == "Staged"
    assert statuses[3] == "needs rate"
    review = intake._txt_extracted.toPlainText()
    assert "INVOICE (customer/job)" in review
    assert "SSN" not in review
    intake._table.selectRow(0)
    intake._on_send_to_manual_invoice()
    assert screen._invoice_tabs.currentIndex() == 0
    assert screen._job.text() == "3235"
    assert screen._po.text() == "PO-3235-A"
    assert screen._date.date() == QDate(2026, 8, 1)
    assert screen.selected_bill_to_customer_id() == cid
    desc0 = screen._table.cellWidget(0, 2)
    bol0 = screen._table.cellWidget(0, 3)
    rate0 = screen._table.cellWidget(0, 4)
    qty0 = screen._table.cellWidget(0, 5)
    amt0 = screen._table.cellWidget(0, 6)
    assert isinstance(desc0, QLineEdit)
    assert desc0.text() == "Plant A to Site North"
    assert isinstance(bol0, QLineEdit)
    assert bol0.text() == "BOL-101"
    assert isinstance(rate0, QDoubleSpinBox) and rate0.value() == 150.0
    assert isinstance(qty0, QDoubleSpinBox) and qty0.value() == 1.0
    assert isinstance(amt0, QDoubleSpinBox) and amt0.value() == 150.0
    rate2 = screen._table.cellWidget(2, 4)
    qty2 = screen._table.cellWidget(2, 5)
    amt2 = screen._table.cellWidget(2, 6)
    desc2 = screen._table.cellWidget(2, 2)
    bol2 = screen._table.cellWidget(2, 3)
    assert isinstance(desc2, QLineEdit)
    assert "160X7" in desc2.text() or "Site West" in desc2.text()
    assert isinstance(bol2, QLineEdit) and bol2.text() == "BOL-103"
    assert isinstance(rate2, QDoubleSpinBox) and rate2.value() == 160.0
    assert isinstance(qty2, QDoubleSpinBox) and qty2.value() == 7.0
    assert isinstance(amt2, QDoubleSpinBox) and amt2.value() == 1120.0
    desc3 = screen._table.cellWidget(3, 2)
    assert isinstance(desc3, QLineEdit)
    assert desc3.text() == ""
    assert intake._table.item(0, 3).text() == "Sent to draft"
    assert intake._table.item(1, 3).text() == "Sent to draft"
    assert intake._table.item(2, 3).text() == "Sent to draft"
    assert intake._table.item(3, 3).text() == "needs rate"
    screen.show()
    qapp.processEvents()
    assert screen._invoice_intake_handoff_banner.isVisible()
    db.close()


def test_dispatch_csv_send_to_enter_bills_zero_pay_allowed(
    qapp: QApplication, tmp_path
) -> None:
    db_path = tmp_path / "dispatch_bill.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    vid = business.add_vendor(db._conn, "Sample Hauling LLC")
    screen = InvoiceScreen(ap_conn=db._conn)
    bills = EnterBillsScreen(ap_conn=db._conn)
    screen.set_enter_bills_screen(bills)
    intake = screen._invoice_intake
    intake.load_dispatch_csv_path(str(SAMPLE_DISPATCH_CSV), notify=False)
    # Last sample row: BST / Sample Hauling LLC / PAY RATE 0
    last = intake._table.rowCount() - 1
    intake._table.selectRow(last)
    intake._on_send_to_enter_bills()
    assert bills._selected_vendor_id() == vid
    amt = bills._table.cellWidget(0, 1)
    assert isinstance(amt, QDoubleSpinBox)
    assert amt.value() == 0.0
    memo = bills._table.cellWidget(0, 2)
    assert isinstance(memo, QLineEdit)
    assert "BST yard" in memo.text()
    assert "BOL-201" in memo.text()
    job = bills._table.cellWidget(0, 3)
    assert isinstance(job, QLineEdit)
    assert job.text() == "BST"
    assert "Sent to bill" in (intake._table.item(last, 3).text() or "")
    db.close()


def test_dispatch_google_stub_does_not_require_token(qapp: QApplication) -> None:
    w = InvoiceIntakePanel()
    with patch("desktop_app.invoice_intake_panel.message_box_information_ok") as m:
        w._on_load_google_sheet()
    m.assert_called_once()
    args = m.call_args[0]
    assert "1 CHAVAN DISPATCH" in args[2]
    assert "CSV" in args[2]


def test_dispatch_intake_screenshot_after_csv_load(qapp: QApplication, tmp_path) -> None:
    db_path = tmp_path / "dispatch_shot.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    screen = InvoiceScreen(ap_conn=db._conn)
    intake = screen._invoice_intake
    intake.load_dispatch_csv_path(str(SAMPLE_DISPATCH_CSV), notify=False)
    screen._invoice_tabs.setCurrentWidget(intake)
    screen.resize(1200, 800)
    screen.show()
    qapp.processEvents()
    pix = intake.grab()
    out = Path("artifacts") / "ui" / "invoice_intake_dispatch.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    assert not pix.isNull()
    saved = pix.save(str(out), "PNG")
    assert saved
    assert out.is_file() and out.stat().st_size > 0
    db.close()

