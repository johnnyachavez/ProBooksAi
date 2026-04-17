"""Invoice screen — structure; Bill To uses customers when DB connected."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt, QSettings
from PySide6.QtTest import QTest
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import (
    QApplication,
    QDoubleSpinBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
)

from desktop_app.customer_bill_to_panel import CustomerBillToPanel
from desktop_app.invoice_intake_text_extract import extract_text_intake_fields
from desktop_app.invoice_screen import (
    InvoiceScreen,
    _INVOICE_LINE_ROW_MIN_HEIGHT_PX,
    _invoice_line_table_qsettings,
)
from probooksai import business
from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import apply_extensions

_INV_PREFS_QS = QSettings("ProBooks+ai", "ProBooks+ai")


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_invoice_screen_footer_recalcs_from_rate_qty(qapp: QApplication, tmp_path) -> None:
    """Subtotal/tax/total labels follow Rate×Qty and default tax % (live, before Save)."""
    db_path = tmp_path / "invoice_footer.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    business.set_setting(db._conn, "default_tax_rate_pct", "10")
    w = InvoiceScreen(ap_conn=db._conn)
    desc = w._table.cellWidget(0, 2)
    assert isinstance(desc, QLineEdit)
    desc.setText("Work")
    rate = w._table.cellWidget(0, 4)
    assert isinstance(rate, QDoubleSpinBox)
    qty = w._table.cellWidget(0, 5)
    assert isinstance(qty, QDoubleSpinBox)
    rate.setValue(100.0)
    qty.setValue(2.0)
    qapp.processEvents()
    assert "200.00" in w._lbl_sub.text().replace(",", "")
    assert "20.00" in w._lbl_tax.text().replace(",", "")
    assert "220.00" in w._lbl_total.text().replace(",", "")
    tot = w._table.cellWidget(0, 6)
    assert isinstance(tot, QDoubleSpinBox)
    assert abs(tot.value() - 200.0) < 0.01
    db.close()


def test_invoice_screen_line_grid_and_headers(qapp: QApplication) -> None:
    w = InvoiceScreen()
    assert isinstance(w._date, QLineEdit)
    assert isinstance(w._inv_number, QLineEdit)
    assert w._inv_number.placeholderText() == "INVOICE #"
    assert w._inv_number.text() == "13001"
    labels = [lb.text() for lb in w.findChildren(QLabel)]
    assert "Invoice Number" not in labels
    assert "Invoice Date" in labels
    t = w.findChild(QTableWidget, "invoiceLinesTable")
    assert t is not None
    assert t.objectName() == "invoiceLinesTable"
    vh = t.verticalHeader()
    assert t.verticalHeaderItem(0) is not None
    assert (t.verticalHeaderItem(0).text() or "") == ""
    w.show()
    qapp.processEvents()
    assert vh.isVisible()
    assert vh.sectionResizeMode(0) == QHeaderView.ResizeMode.Interactive
    assert vh.minimumSectionSize() == _INVOICE_LINE_ROW_MIN_HEIGHT_PX
    hh = t.horizontalHeader()
    for c in range(7):
        assert hh.sectionResizeMode(c) == QHeaderView.ResizeMode.Interactive
    assert t.columnCount() == 7
    assert t.rowCount() == InvoiceScreen._N_LINE_ROWS
    assert t.horizontalHeaderItem(0).text() == "Date"
    assert t.horizontalHeaderItem(2).text() == "Description"
    assert t.horizontalHeaderItem(3).text() == "BOL#"
    assert t.horizontalHeaderItem(6).text() == "Total"
    assert isinstance(t.cellWidget(0, 0), QLineEdit)
    assert isinstance(t.cellWidget(0, 1), QLineEdit)
    assert isinstance(t.cellWidget(0, 2), QLineEdit)
    assert isinstance(t.cellWidget(0, 3), QLineEdit)
    assert isinstance(t.cellWidget(0, 4), QDoubleSpinBox)
    assert isinstance(t.cellWidget(0, 5), QDoubleSpinBox)
    assert isinstance(t.cellWidget(0, 6), QDoubleSpinBox)


def test_invoice_line_table_column_widths_persist_in_qsettings(
    qapp: QApplication, tmp_path
) -> None:
    """Saved line-grid column widths restore on a new InvoiceScreen (same company path)."""
    db_path = str(tmp_path / "inv_col_widths.db")
    QSettings().setValue("company_database_path", db_path)
    db = BankDatabase(db_path)
    apply_extensions(db._conn)
    w1 = InvoiceScreen(ap_conn=db._conn)
    t1 = w1.findChild(QTableWidget, "invoiceLinesTable")
    assert t1 is not None
    want = [90, 100, 220, 100, 88, 77, 120]
    mins = list(w1._invoice_col_mins)
    hh1 = t1.horizontalHeader()
    hh1.blockSignals(True)
    for c, wpx in enumerate(want):
        t1.setColumnWidth(c, max(mins[c], wpx))
    hh1.blockSignals(False)
    w1._persist_invoice_line_column_widths()
    _invoice_line_table_qsettings().sync()
    w2 = InvoiceScreen(ap_conn=db._conn)
    t2 = w2.findChild(QTableWidget, "invoiceLinesTable")
    assert t2 is not None
    w2.show()
    qapp.processEvents()
    for c in range(6):
        assert t2.columnWidth(c) == max(mins[c], want[c])
    vw = t2.viewport().width()
    sum_first = sum(t2.columnWidth(c) for c in range(6))
    assert t2.columnWidth(6) == max(mins[6], vw - sum_first)
    db.close()


def test_invoice_screen_address_boxes_exist(qapp: QApplication) -> None:
    w = InvoiceScreen()
    assert isinstance(w._bill_to[0], CustomerBillToPanel)
    assert w._bill_to[1].placeholderText() == "Bill To"
    assert w._ship_to is None


def test_invoice_screen_print_and_nav_buttons_exist(qapp: QApplication) -> None:
    w = InvoiceScreen()
    assert w._btn_clear_fields.text() == "Clear Fields"
    assert w._btn_save.text() == "Save"
    assert w._btn_export_pdf.text() == "Export PDF…"
    assert w._btn_print.text() == "Print…"
    assert w._btn_new_customer.text() == "New Customer"
    assert w._btn_reverse.text() == "Reverse"
    assert w._btn_forward.text() == "Forward"


def test_invoice_screen_export_pdf_saves_to_chosen_path(
    qapp: QApplication, tmp_path
) -> None:
    """Export PDF… persists, then writes to the path from Save file (mocked)."""
    db_path = tmp_path / "invoice_export.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "ExportCo")
    w = InvoiceScreen(ap_conn=db._conn)
    w._bill_customer_panel.select_customer_by_id(cid)
    w._inv_number.setText("93001")
    desc = w._table.cellWidget(0, 2)
    assert isinstance(desc, QLineEdit)
    desc.setText("Export line")
    rate = w._table.cellWidget(0, 4)
    assert isinstance(rate, QDoubleSpinBox)
    rate.setValue(50.0)
    qty = w._table.cellWidget(0, 5)
    assert isinstance(qty, QDoubleSpinBox)
    qty.setValue(1.0)
    out = tmp_path / "MyInvoice.pdf"
    with patch(
        "desktop_app.invoice_screen.QFileDialog.getSaveFileName",
        return_value=(str(out), "PDF files (*.pdf)"),
    ):
        QTest.mouseClick(w._btn_export_pdf, Qt.MouseButton.LeftButton)
        qapp.processEvents()
    assert out.is_file()
    invs = business.list_invoices(db._conn)
    assert any((r["invoice_number"] or "").strip() == "93001" for r in invs)
    assert w._inv_number.text() == "93002"
    db.close()


def test_invoice_screen_save_persists_and_advances_form(qapp: QApplication, tmp_path) -> None:
    db_path = tmp_path / "invoice_save.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    pdf_dir = tmp_path / "invoice_pdf_out"
    pdf_dir.mkdir()
    _INV_PREFS_QS.setValue("invoice_prefs/output_folder", str(pdf_dir))
    _INV_PREFS_QS.sync()
    cid = business.add_customer(db._conn, "SaveCo")
    w = InvoiceScreen(ap_conn=db._conn)
    w._bill_customer_panel.select_customer_by_id(cid)
    w._inv_number.setText("91001")
    desc = w._table.cellWidget(0, 2)
    assert isinstance(desc, QLineEdit)
    desc.setText("Consulting")
    rate = w._table.cellWidget(0, 4)
    assert isinstance(rate, QDoubleSpinBox)
    rate.setValue(100.0)
    qty = w._table.cellWidget(0, 5)
    assert isinstance(qty, QDoubleSpinBox)
    qty.setValue(2.0)
    QTest.mouseClick(w._btn_save, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    invs = business.list_invoices(db._conn)
    assert any((r["invoice_number"] or "").strip() == "91001" for r in invs)
    assert w._inv_number.text() == "91002"
    assert not w._bill_to[1].toPlainText().strip()
    assert (pdf_dir / "Invoice-91001.pdf").is_file()
    db.close()


def test_invoice_screen_print_after_accept_resets_when_connected(
    qapp: QApplication, tmp_path
) -> None:
    db_path = tmp_path / "invoice_print_reset.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "PrintCo")
    w = InvoiceScreen(ap_conn=db._conn)
    w._bill_customer_panel.select_customer_by_id(cid)
    w._inv_number.setText("92001")
    desc = w._table.cellWidget(0, 2)
    assert isinstance(desc, QLineEdit)
    desc.setText("Line for print")
    rate = w._table.cellWidget(0, 4)
    assert isinstance(rate, QDoubleSpinBox)
    rate.setValue(1.0)
    qty = w._table.cellWidget(0, 5)
    assert isinstance(qty, QDoubleSpinBox)
    qty.setValue(1.0)
    pdf_dir = tmp_path / "invoice_print_pdf_out"
    pdf_dir.mkdir()
    _INV_PREFS_QS.setValue("invoice_prefs/output_folder", str(pdf_dir))
    _INV_PREFS_QS.sync()
    with patch(
        "desktop_app.invoice_screen.configure_printer_for_invoice_print",
        return_value=True,
    ):
        with patch.object(QTextDocument, "print_", lambda self, p: None):
            QTest.mouseClick(w._btn_print, Qt.MouseButton.LeftButton)
            qapp.processEvents()
    invs = business.list_invoices(db._conn)
    assert any((r["invoice_number"] or "").strip() == "92001" for r in invs)
    assert w._inv_number.text() == "92002"
    db.close()


def test_invoice_screen_nav_stops_without_cycling_unpositioned_draft(qapp: QApplication, tmp_path) -> None:
    """Forward from an unpositioned draft does not jump to the first saved invoice; Reverse opens last by #."""
    db_path = tmp_path / "invoice_nav.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "NavCo")
    business.create_invoice(
        db._conn,
        cid,
        "14001",
        "2024-07-01",
        lines=[{"description": "Line A", "qty": 2.0, "rate": 15.0}],
    )
    w = InvoiceScreen(ap_conn=db._conn)
    assert w._browse_ids
    before = w._inv_number.text()
    w._on_forward_invoice()
    assert w._inv_number.text() == before
    w._on_reverse_invoice()
    assert w._inv_number.text() == "14001"
    assert "Line A" in (w._table.cellWidget(0, 2).text() or "")
    w._on_forward_invoice()
    assert w._current_invoice_id is None
    assert w._browse_slot == 1
    w._on_forward_invoice()
    assert w._current_invoice_id is None
    db.close()


def test_invoice_screen_clear_fields_resets_invoice_number_to_next_suggestion(
    qapp: QApplication, tmp_path
) -> None:
    """Clear Fields starts a new draft: lines/header clear and invoice # follows next company default."""
    db_path = tmp_path / "invoice_clear.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "C")
    business.create_invoice(
        db._conn,
        cid,
        "15001",
        "2024-08-01",
        lines=[{"description": "X", "qty": 1.0, "rate": 1.0}],
    )
    w = InvoiceScreen(ap_conn=db._conn)
    w._on_reverse_invoice()
    assert w._inv_number.text() == "15001"
    w._on_forward_invoice()
    assert w._inv_number.text() == "15002"
    w._on_clear_fields()
    assert w._inv_number.text() == "15002"
    assert w._current_invoice_id is None
    assert not (w._table.cellWidget(0, 2).text() or "").strip()
    db.close()


def test_invoice_screen_suggested_invoice_number_from_company_file(
    qapp: QApplication, tmp_path
) -> None:
    db_path = tmp_path / "invoice_invno.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "Cust")
    business.create_invoice(
        db._conn,
        cid,
        "13001",
        "2024-06-01",
        lines=[{"description": "Work", "qty": 1, "rate": 10.0}],
    )
    w = InvoiceScreen(ap_conn=db._conn)
    assert w._inv_number.text() == "13002"
    db.close()


def test_invoice_screen_update_existing_does_not_duplicate_row(
    qapp: QApplication, tmp_path
) -> None:
    """Editing a loaded invoice updates the same row instead of inserting another."""
    db_path = tmp_path / "invoice_update.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "EditCo")
    inv_id = business.create_invoice(
        db._conn,
        cid,
        "UP-001",
        "2024-09-01",
        lines=[{"description": "A", "qty": 1.0, "rate": 10.0}],
    )
    pdf_dir = tmp_path / "invoice_upd_pdf"
    pdf_dir.mkdir()
    _INV_PREFS_QS.setValue("invoice_prefs/output_folder", str(pdf_dir))
    _INV_PREFS_QS.sync()
    w = InvoiceScreen(ap_conn=db._conn)
    w._load_invoice_into_form(inv_id)
    assert w._current_invoice_id == inv_id
    assert w._inv_number.text() == "UP-001"
    desc = w._table.cellWidget(0, 2)
    assert isinstance(desc, QLineEdit)
    desc.setText("Updated line")
    QTest.mouseClick(w._btn_save, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    rows = business.list_invoices(db._conn)
    assert len(rows) == 1
    assert int(rows[0]["id"]) == inv_id
    assert w._inv_number.text() == "UP-001"
    assert (pdf_dir / "Invoice-UP-001.pdf").is_file()
    db.close()


def test_get_invoice_id_by_number_matches_db(qapp: QApplication, tmp_path) -> None:
    db_path = tmp_path / "inv_by_num.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "NumCo")
    inv_id = business.create_invoice(
        db._conn,
        cid,
        "INV-XYZ-9",
        "2024-11-15",
        lines=[{"description": "Line", "qty": 1.0, "rate": 1.0}],
    )
    assert business.get_invoice_id_by_number(db._conn, "INV-XYZ-9") == inv_id
    assert business.get_invoice_id_by_number(db._conn, "  INV-XYZ-9  ") == inv_id
    assert business.get_invoice_id_by_number(db._conn, "missing") is None
    db.close()


def test_invoice_screen_open_invoice_by_number(qapp: QApplication, tmp_path) -> None:
    db_path = tmp_path / "inv_open_num.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "RouteCo")
    inv_id = business.create_invoice(
        db._conn,
        cid,
        "RT-500",
        "2024-12-01",
        lines=[{"description": "Svc", "qty": 1.0, "rate": 25.0}],
    )
    w = InvoiceScreen(ap_conn=db._conn)
    assert w.open_invoice_by_number("RT-500") is True
    assert w._current_invoice_id == inv_id
    assert w._inv_number.text() == "RT-500"
    assert w.open_invoice_by_number("nope") is False
    db.close()


def test_invoice_screen_open_invoice_by_id_loads_manual_invoice(qapp: QApplication, tmp_path) -> None:
    db_path = tmp_path / "invoice_open_id.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "LinkCo")
    inv_id = business.create_invoice(
        db._conn,
        cid,
        "LK-100",
        "2024-10-01",
        memo="PO: P1\nJob: J1",
        lines=[{"description": "Item", "qty": 2.0, "rate": 5.0}],
    )
    w = InvoiceScreen(ap_conn=db._conn)
    w._invoice_tabs.setCurrentIndex(1)
    assert w._invoice_tabs.currentIndex() == 1
    ok = w.open_invoice_by_id(inv_id)
    assert ok is True
    assert w._invoice_tabs.currentIndex() == 0
    assert w._current_invoice_id == inv_id
    assert w._inv_number.text() == "LK-100"
    assert w._po.text() == "P1"
    assert w._job.text() == "J1"
    db.close()


def test_invoice_screen_bill_to_selects_customer(qapp: QApplication, tmp_path) -> None:
    db_path = tmp_path / "invoice_bill_to.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    business.add_customer(
        db._conn,
        "Acme Rentals",
        email="billing@acme.test",
        phone="555-0199",
        address="200 Oak Ave\nPortland, OR 97201",
        notes="Contact: Dana Lee",
    )
    w = InvoiceScreen(ap_conn=db._conn)
    panel = w.bill_to_customer_panel()
    assert panel._combo.count() >= 1
    panel._combo.setCurrentIndex(0)
    body = w._bill_to[1].toPlainText()
    assert "Acme Rentals" in body
    assert "200 Oak Ave" in body
    assert "Dana Lee" in body or "Contact: Dana Lee" in body
    assert "billing@acme.test" in body
    assert "555-0199" in body
    assert w.selected_bill_to_customer_id() is not None
    db.close()


def test_invoice_screen_customer_records_changed_emitted_from_bill_to_panel(
    qapp: QApplication, tmp_path
) -> None:
    db_path = tmp_path / "invoice_cust_signal.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    w = InvoiceScreen(ap_conn=db._conn)
    seen: list[bool] = []
    w.customerRecordsChanged.connect(lambda: seen.append(True))
    w.bill_to_customer_panel().customerCreated.emit(1)
    assert seen == [True]


def test_invoice_screen_bill_to_combo_shows_job_hierarchy(
    qapp: QApplication, tmp_path
) -> None:
    db_path = tmp_path / "invoice_bill_hier.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    parent = business.add_customer(db._conn, "Parent Corp")
    job = business.add_customer(db._conn, "Job Z", parent_customer_id=parent)
    w = InvoiceScreen(ap_conn=db._conn)
    panel = w.bill_to_customer_panel()
    combo = panel._combo
    texts = [combo.itemText(i) for i in range(combo.count())]
    assert "Parent Corp" in texts
    assert "Parent Corp > Job Z" in texts
    jidx = combo.findText("Parent Corp > Job Z")
    assert jidx >= 0
    combo.setCurrentIndex(jidx)
    assert w.selected_bill_to_customer_id() == job
    pidx = combo.findText("Parent Corp")
    assert pidx >= 0
    combo.setCurrentIndex(pidx)
    assert w.selected_bill_to_customer_id() == parent
    db.close()


def test_invoice_save_and_print_handlers_require_real_button_sender(
    qapp: QApplication, tmp_path
) -> None:
    """Direct slot calls without a QPushButton sender must not persist or open print (phantom dialog guard)."""
    db_path = tmp_path / "invoice_phantom.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "PhantomCo")
    w = InvoiceScreen(ap_conn=db._conn)
    w._bill_customer_panel.select_customer_by_id(cid)
    w._inv_number.setText("77701")
    desc = w._table.cellWidget(0, 2)
    assert isinstance(desc, QLineEdit)
    desc.setText("Svc")
    rate = w._table.cellWidget(0, 4)
    assert isinstance(rate, QDoubleSpinBox)
    rate.setValue(10.0)
    qty = w._table.cellWidget(0, 5)
    assert isinstance(qty, QDoubleSpinBox)
    qty.setValue(1.0)
    with patch.object(w, "_try_persist_invoice") as m_persist:
        w._on_save_invoice()
        m_persist.assert_not_called()
    with patch.object(w, "_try_persist_invoice") as m_persist:
        w._on_export_pdf_as()
        m_persist.assert_not_called()
    with patch(
        "desktop_app.invoice_screen.configure_printer_for_invoice_print"
    ) as m_cp:
        w._on_print_invoice()
        m_cp.assert_not_called()
    assert business.list_invoices(db._conn) == []
    db.close()


def test_apply_intake_item_to_draft_pdf_memo_and_banner(
    qapp: QApplication, tmp_path
) -> None:
    db_path = tmp_path / "apply_intake.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    w = InvoiceScreen(ap_conn=db._conn)
    ok = w.apply_intake_item_to_draft(
        source_display="source.pdf",
        kind="PDF",
        path=str(pdf),
        queue_notes="Check rates",
    )
    assert ok is True
    assert w._invoice_tabs.currentIndex() == 0
    assert w._current_invoice_id is None
    assert "source.pdf" in w._invoice_memo_notes
    assert os.path.normpath(str(pdf)) in w._invoice_memo_notes
    assert "Queue notes: Check rates" in w._invoice_memo_notes
    w.show()
    qapp.processEvents()
    assert w._invoice_intake_handoff_banner.isVisible()
    assert "source.pdf" in w._invoice_intake_handoff_banner.text()
    db.close()


def test_apply_intake_item_to_draft_staged_text_in_memo(
    qapp: QApplication, tmp_path
) -> None:
    db_path = tmp_path / "apply_intake_text.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    w = InvoiceScreen(ap_conn=db._conn)
    ok = w.apply_intake_item_to_draft(
        source_display="Pasted text (9 chars)",
        kind="Text",
        text_payload="Line one\n",
        queue_notes="",
    )
    assert ok is True
    assert "Line one" in w._invoice_memo_notes
    assert "--- Staged text" in w._invoice_memo_notes
    w.show()
    qapp.processEvents()
    assert w._invoice_intake_handoff_banner.isVisible()
    db.close()


def test_apply_intake_item_to_draft_hidden_after_opening_saved_invoice(
    qapp: QApplication, tmp_path
) -> None:
    db_path = tmp_path / "apply_intake_hide.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "Co")
    inv_id = business.create_invoice(
        db._conn,
        cid,
        "Z-9",
        "2025-01-01",
        memo="x",
        lines=[{"description": "A", "qty": 1.0, "rate": 1.0}],
    )
    doc = tmp_path / "doc.pdf"
    doc.write_bytes(b"%PDF-1.4")
    w = InvoiceScreen(ap_conn=db._conn)
    w.apply_intake_item_to_draft(
        source_display="doc.pdf",
        kind="PDF",
        path=str(doc),
        queue_notes="",
    )
    w.show()
    qapp.processEvents()
    assert w._invoice_intake_handoff_banner.isVisible()
    assert w.open_invoice_by_id(inv_id) is True
    qapp.processEvents()
    assert not w._invoice_intake_handoff_banner.isVisible()
    db.close()


def test_apply_intake_item_to_draft_applies_high_confidence_text_extraction(
    qapp: QApplication, tmp_path
) -> None:
    db_path = tmp_path / "apply_intake_ex.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    w = InvoiceScreen(ap_conn=db._conn)
    body = """Date: 2025-04-01
Ticket # ZZ-1
Customer: Beta LLC
Notes: Rush job.
Extra line in body not labeled.
"""
    ex = extract_text_intake_fields(body)
    ok = w.apply_intake_item_to_draft(
        source_display="Pasted",
        kind="Text",
        text_payload=body,
        queue_notes="",
        text_extraction=ex,
    )
    assert ok is True
    assert w._date.text().strip() == "04/01/2025"
    bol = w._table.cellWidget(0, 3)
    assert isinstance(bol, QLineEdit)
    assert bol.text().strip() == "ZZ-1"
    assert "Beta" in w._invoice_memo_notes
    assert "Rush job" in w._invoice_memo_notes
    assert "Extra line" in w._invoice_memo_notes
    w.show()
    qapp.processEvents()
    assert w._invoice_intake_handoff_banner.isVisible()
    db.close()


def test_apply_intake_item_to_draft_requires_company_file(qapp: QApplication) -> None:
    w = InvoiceScreen(ap_conn=None)
    with patch("desktop_app.invoice_screen.message_box_information_ok") as m:
        ok = w.apply_intake_item_to_draft(
            source_display="a",
            kind="PDF",
            path="/tmp/x.pdf",
            queue_notes="",
        )
    assert ok is False
    m.assert_called_once()
