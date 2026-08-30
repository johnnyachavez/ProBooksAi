"""Invoice screen — structure; Bill To uses customers when DB connected."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt, QSettings, QDate, QEvent
from PySide6.QtTest import QTest
from PySide6.QtGui import QPalette, QTextDocument
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFrame,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTabWidget,
    QTableWidget,
)

from desktop_app.customer_bill_to_panel import CustomerBillToPanel
from desktop_app.invoice_intake_text_extract import extract_text_intake_fields
from desktop_app import invoice_screen as invoice_screen_module
from desktop_app.invoice_screen import (
    InvoiceScreen,
    _DEFAULT_INVOICE_TEMPLATE,
    _DEFAULT_AR_ACCOUNT,
    _INVOICE_LINE_ROW_MIN_HEIGHT_PX,
    _InvoiceCodeLineEdit,
    _invoice_line_table_qsettings,
    invoice_pdf_basename,
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
    assert "0.00" in w._lbl_payments.text().replace(",", "")
    assert "220.00" in w._lbl_balance.text().replace(",", "")
    tot = w._table.cellWidget(0, 6)
    assert isinstance(tot, QDoubleSpinBox)
    assert abs(tot.value() - 200.0) < 0.01
    db.close()


def test_invoice_screen_line_grid_and_headers(qapp: QApplication) -> None:
    w = InvoiceScreen()
    assert isinstance(w._date, QDateEdit)
    assert isinstance(w._due_date, QDateEdit)
    assert isinstance(w._terms, QComboBox)
    assert isinstance(w._inv_number, QLineEdit)
    assert w._inv_number.placeholderText() == "Invoice #"
    assert w._inv_number.text() == "1"
    labels = [lb.text() for lb in w.findChildren(QLabel)]
    assert "Invoice Number" not in labels
    assert "DATE" in labels
    assert "DUE DATE" in labels
    assert "TERMS" in labels
    assert "INVOICE #" in labels
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
    assert t.horizontalHeaderItem(0).text() == "SERVICED ON"
    assert t.horizontalHeaderItem(1).text() == "JL #"
    assert t.horizontalHeaderItem(2).text() == "DESCRIPTION"
    assert t.horizontalHeaderItem(3).text() == "BOL#"
    assert t.horizontalHeaderItem(4).text() == "RATE"
    assert t.horizontalHeaderItem(5).text() == "QUANTITY"
    assert t.horizontalHeaderItem(6).text() == "AMOUNT"
    assert isinstance(t.cellWidget(0, 0), QLineEdit)
    assert isinstance(t.cellWidget(0, 1), QLineEdit)
    assert isinstance(t.cellWidget(0, 2), QLineEdit)
    assert isinstance(t.cellWidget(0, 3), QLineEdit)
    assert isinstance(t.cellWidget(0, 4), QDoubleSpinBox)
    assert isinstance(t.cellWidget(0, 5), QDoubleSpinBox)
    assert isinstance(t.cellWidget(0, 6), QDoubleSpinBox)
    for col in range(4):
        cell = t.cellWidget(0, col)
        assert isinstance(cell, QLineEdit)
        assert (cell.placeholderText() or "").strip() == ""
        assert (cell.text() or "").strip() == ""
    for col in (4, 5, 6):
        spin = t.cellWidget(0, col)
        assert isinstance(spin, QDoubleSpinBox)
        assert spin.value() == 0.0
        assert (spin.specialValueText() or "").strip() == ""


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
    desc = InvoiceScreen._LINE_DESC_COL
    for c in range(7):
        if c == desc:
            continue
        assert t2.columnWidth(c) == max(mins[c], want[c])
    vw = t2.viewport().width()
    sum_others = sum(t2.columnWidth(c) for c in range(7) if c != desc)
    assert t2.columnWidth(desc) == max(mins[desc], vw - sum_others)
    db.close()


def test_invoice_screen_address_boxes_exist(qapp: QApplication) -> None:
    w = InvoiceScreen()
    assert isinstance(w._bill_to[0], CustomerBillToPanel)
    assert w._bill_to[1].placeholderText() == "Bill To"
    assert w._ship_to is not None
    assert isinstance(w._ship_to[1], QPlainTextEdit)
    assert w._ship_to[1].placeholderText() == "Ship To"


def test_customer_job_combo_event_filter_survives_deleted_combo(
    qapp: QApplication,
) -> None:
    """Customer:Job combo is reparented onto the header bar; filters must not crash on teardown."""
    w = InvoiceScreen()
    panel = w._bill_customer_panel
    combo = panel.customer_combo()
    assert combo.parent() is not panel
    combo.deleteLater()
    qapp.processEvents()
    ev = QEvent(QEvent.Type.FocusIn)
    assert panel.eventFilter(combo, ev) in (True, False)
    panel._bill_to_show_popup_deferred()
    w.close()
    w.deleteLater()
    qapp.processEvents()


def test_invoice_screen_print_and_nav_buttons_exist(qapp: QApplication) -> None:
    w = InvoiceScreen()
    assert w._btn_clear_fields.text() == "Clear"
    assert "Save" in w._btn_save.text() and "New" in w._btn_save.text()
    assert "Save" in w._btn_save_close.text() and "Close" in w._btn_save_close.text()
    assert w._btn_export_pdf.text() == "Save As"
    assert w._btn_print.text() == "Print"
    assert w._btn_new_customer.text() == "New Customer"
    assert w._btn_reverse.text() == "Previous"
    assert w._btn_forward.text() == "Next"
    assert w._btn_find.text() == "Find"
    assert w._btn_new_invoice.text() == "New"
    assert w._btn_email.text() == "Email"
    # Email is now wired to a real mailto handler with a customer-email check.
    assert w._btn_email.isEnabled()
    assert w._btn_intake.text() == "Intake"


def test_invoice_screen_export_pdf_saves_to_chosen_path(
    qapp: QApplication, tmp_path
) -> None:
    """Save As persists, then writes ``<invoice#>.pdf`` into the chosen folder."""
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
    out_dir = tmp_path / "save_as_out"
    out_dir.mkdir()
    out = out_dir / "93001.pdf"
    with patch(
        "desktop_app.invoice_screen.prompt_invoice_save_as_path",
        return_value=str(out),
    ):
        QTest.mouseClick(w._btn_export_pdf, Qt.MouseButton.LeftButton)
        qapp.processEvents()
    assert out.is_file()
    invs = business.list_invoices(db._conn)
    assert any((r["invoice_number"] or "").strip() == "93001" for r in invs)
    assert w._inv_number.text() == "93001"
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
    assert (pdf_dir / "91001.pdf").is_file()
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
    assert (pdf_dir / "UP-001.pdf").is_file()
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
    with patch("desktop_app.invoice_screen.message_box_information_ok"):
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
        w._on_save_close_invoice()
        m_persist.assert_not_called()
    with patch.object(w, "_try_persist_invoice") as m_persist:
        w._on_ribbon_save_invoice()
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
    with patch("desktop_app.invoice_screen.message_box_question_yes_no_cancel", return_value="no"):
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
    assert w._date.date() == QDate(2025, 4, 1)
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


def test_manual_invoice_save_persists_without_pdf_folder(
    qapp: QApplication, tmp_path
) -> None:
    """Save writes to ``invoices`` / ``invoice_lines`` even when no invoice PDF folder is set."""
    db_path = tmp_path / "manual_save_no_pdf.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "SaveCo")
    w = InvoiceScreen(ap_conn=db._conn)
    w._bill_customer_panel.select_customer_by_id(cid)
    w._inv_number.setText("91001")
    desc = w._table.cellWidget(0, 2)
    assert isinstance(desc, QLineEdit)
    desc.setText("Consulting")
    rate = w._table.cellWidget(0, 4)
    qty = w._table.cellWidget(0, 5)
    assert isinstance(rate, QDoubleSpinBox) and isinstance(qty, QDoubleSpinBox)
    rate.setValue(100.0)
    qty.setValue(1.0)
    w.show()
    qapp.processEvents()
    with patch("desktop_app.invoice_screen.ensure_invoice_output_folder", return_value=None):
        QTest.mouseClick(w._btn_save, Qt.MouseButton.LeftButton)
        qapp.processEvents()
    rows = business.list_invoices(db._conn)
    assert len(rows) == 1
    d = dict(rows[0])
    assert (d.get("invoice_number") or "").strip() == "91001"
    assert abs(float(d.get("total") or 0) - 100.0) < 0.02
    db.close()


def test_manual_invoice_save_edit_resave_round_trip(
    qapp: QApplication, tmp_path
) -> None:
    """Load saved invoice, edit line, re-save updates the same DB row."""
    db_path = tmp_path / "manual_edit.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "EditCo")
    w = InvoiceScreen(ap_conn=db._conn)
    w._bill_customer_panel.select_customer_by_id(cid)
    w._inv_number.setText("92001")
    desc = w._table.cellWidget(0, 2)
    assert isinstance(desc, QLineEdit)
    desc.setText("First")
    rate = w._table.cellWidget(0, 4)
    qty = w._table.cellWidget(0, 5)
    assert isinstance(rate, QDoubleSpinBox) and isinstance(qty, QDoubleSpinBox)
    rate.setValue(50.0)
    qty.setValue(1.0)
    w.show()
    qapp.processEvents()
    with patch("desktop_app.invoice_screen.ensure_invoice_output_folder", return_value=None):
        QTest.mouseClick(w._btn_save, Qt.MouseButton.LeftButton)
        qapp.processEvents()
    rows = business.list_invoices(db._conn)
    iid = int(dict(rows[0])["id"])
    assert w.open_invoice_by_id(iid) is True
    qapp.processEvents()
    desc2 = w._table.cellWidget(0, 2)
    assert isinstance(desc2, QLineEdit)
    desc2.setText("Updated work")
    with patch("desktop_app.invoice_screen.ensure_invoice_output_folder", return_value=None):
        QTest.mouseClick(w._btn_save, Qt.MouseButton.LeftButton)
        qapp.processEvents()
    inv, lines = business.get_invoice_detail(db._conn, iid)
    assert inv is not None
    assert len(lines) >= 1
    assert "Updated work" in (dict(lines[0]).get("description") or "")
    db.close()


def test_invoice_save_duplicate_invoice_number_shows_modal_warning(
    qapp: QApplication, tmp_path, monkeypatch
) -> None:
    """Duplicate invoice # on save shows a clear modal warning (SQLite UNIQUE on ``invoice_number``)."""
    warnings: list[tuple[str, str]] = []

    def _warn(parent, title, text, *, ok_tip: str = "") -> None:
        warnings.append((title, text))

    monkeypatch.setattr(invoice_screen_module, "message_box_warning_ok", _warn)

    db_path = tmp_path / "inv_dup_warn.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    c1 = business.add_customer(db._conn, "CustA")
    c2 = business.add_customer(db._conn, "CustB")
    business.create_invoice(
        db._conn,
        c1,
        "100",
        "2024-01-01",
        lines=[{"description": "existing", "qty": 1, "rate": 1.0}],
    )
    w = InvoiceScreen(ap_conn=db._conn)
    w.show()
    qapp.processEvents()
    w._bill_customer_panel.select_customer_by_id(c2)
    w._inv_number.setText("100")
    w._date.setDate(QDate(2024, 2, 1))
    ok, msg, iid = w._try_persist_invoice()
    assert ok is False
    assert iid is None
    assert msg == ""
    assert len(warnings) == 1
    assert warnings[0][0] == "Duplicate invoice number"
    assert "already used" in warnings[0][1]
    db.close()


def test_invoice_line_code_applies_rate_from_invoice_item_codes(
    qapp: QApplication, tmp_path
) -> None:
    """Code column uses ``invoice_item_codes``; matching code fills Rate; unknown code leaves Rate."""
    db_path = tmp_path / "inv_codes_wire.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    business.replace_invoice_item_codes(
        db._conn,
        [
            {
                "code": "SRV-A",
                "description": "Service A",
                "item_type": "Service",
                "coa_account": "",
                "rate_value": 75.5,
                "rate_kind": "amount",
                "sort_order": 0,
            },
            {
                "code": "SRV-B",
                "description": "Service B",
                "item_type": "Service",
                "coa_account": "",
                "rate_value": 20.0,
                "rate_kind": "amount",
                "sort_order": 1,
            },
        ],
    )
    w = InvoiceScreen(ap_conn=db._conn)
    w.show()
    qapp.processEvents()
    w.refresh_invoice_item_codes()
    code_w = w._table.cellWidget(0, 1)
    rate_w = w._table.cellWidget(0, 4)
    assert isinstance(code_w, QLineEdit) and isinstance(rate_w, QDoubleSpinBox)
    code_w.setText("SRV-A")
    w._on_invoice_line_code_committed(0)
    assert abs(rate_w.value() - 75.5) < 0.01
    rate_w.setValue(12.0)
    w._on_invoice_line_code_committed(0)
    assert abs(rate_w.value() - 12.0) < 0.01
    code_w.setText("SRV-B")
    w._on_invoice_line_code_committed(0)
    assert abs(rate_w.value() - 20.0) < 0.01
    rate_w.setValue(99.0)
    code_w.setText("NOPE")
    w._on_invoice_line_code_committed(0)
    assert abs(rate_w.value() - 99.0) < 0.01
    db.close()


def test_invoice_line_code_widget_is_dropdown_typeahead_backed_by_codes_table(
    qapp: QApplication, tmp_path
) -> None:
    """Code column widget is the dropdown/type-ahead :class:`_InvoiceCodeLineEdit` with a populated completer."""
    db_path = tmp_path / "inv_code_dropdown.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    business.replace_invoice_item_codes(
        db._conn,
        [
            {
                "code": "SRV-A",
                "description": "Service A",
                "item_type": "Service",
                "coa_account": "",
                "rate_value": 10.0,
                "rate_kind": "amount",
                "sort_order": 0,
            },
            {
                "code": "SRV-B",
                "description": "Service B",
                "item_type": "Service",
                "coa_account": "",
                "rate_value": 20.0,
                "rate_kind": "amount",
                "sort_order": 1,
            },
            {
                "code": "MISC",
                "description": "Misc",
                "item_type": "Service",
                "coa_account": "",
                "rate_value": 5.0,
                "rate_kind": "amount",
                "sort_order": 2,
            },
        ],
    )
    w = InvoiceScreen(ap_conn=db._conn)
    w.show()
    qapp.processEvents()
    w.refresh_invoice_item_codes()

    code_w = w._table.cellWidget(0, 1)
    assert isinstance(code_w, _InvoiceCodeLineEdit), (
        "Manual Invoice Code column must use _InvoiceCodeLineEdit (dropdown + type-ahead)."
    )
    assert isinstance(code_w, QLineEdit), (
        "_InvoiceCodeLineEdit must remain a QLineEdit so save/load paths keep using .text()."
    )

    comp = code_w.completer()
    assert comp is not None, "Code cell must have a QCompleter attached."
    assert comp.caseSensitivity() == Qt.CaseSensitivity.CaseInsensitive
    model = comp.model()
    assert model is not None
    saved_codes = {model.data(model.index(r, 0)) for r in range(model.rowCount())}
    assert {"SRV-A", "SRV-B", "MISC"} <= saved_codes

    code_w.clear()
    code_w._show_invoice_code_completer_popup()
    qapp.processEvents()
    popup = comp.popup()
    assert popup is not None and popup.isVisible(), (
        "Empty Code field must open the saved-Codes dropdown when focused/clicked."
    )
    assert comp.completionCount() == len(saved_codes), (
        "Empty completion prefix should list every saved Code."
    )
    popup.hide()

    code_w.setText("SRV")
    code_w._show_invoice_code_completer_popup()
    qapp.processEvents()
    assert comp.completionPrefix() == "SRV"
    assert comp.completionCount() == 2, (
        "Typing 'SRV' must narrow the dropdown to the two SRV-* codes."
    )
    popup = comp.popup()
    assert popup is not None and popup.isVisible()
    popup.hide()

    db.close()


def test_invoice_line_code_cell_tooltip_documents_dropdown_typeahead(
    qapp: QApplication, tmp_path
) -> None:
    """Code cell tooltip documents dropdown + type-ahead; empty cell has no hint text."""
    db_path = tmp_path / "inv_code_tooltip.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    w = InvoiceScreen(ap_conn=db._conn)
    w.show()
    qapp.processEvents()
    code_w = w._table.cellWidget(0, 1)
    assert isinstance(code_w, _InvoiceCodeLineEdit)
    assert (code_w.placeholderText() or "").strip() == ""
    assert "click" not in (code_w.text() or "").lower()
    tip = code_w.toolTip()
    assert "saved Codes" in tip
    assert "type to filter" in tip or "narrows" in tip
    assert "auto-fill" in tip.lower() or "auto fills" in tip.lower()
    db.close()


def test_refresh_loaded_invoice_payment_status_updates_paid_badge_for_open_invoice(
    qapp: QApplication, tmp_path
) -> None:
    """After AR payment posts to the loaded invoice, badge flips to PAID without form reload."""
    db_path = tmp_path / "inv_pay_refresh.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "PayRefreshCo")
    inv_id = business.create_invoice(
        db._conn,
        cid,
        "PR-1",
        "2025-03-01",
        lines=[{"description": "Svc", "qty": 1.0, "rate": 50.0}],
    )
    w = InvoiceScreen(ap_conn=db._conn)
    assert w.open_invoice_by_id(inv_id) is True
    assert w._current_invoice_id == inv_id
    assert w._invoice_status_badge.isHidden() is True, (
        "Open invoice (balance > 0) must not show PAID badge."
    )
    assert w._invoice_status_badge.text() == ""

    business.record_ar_payment(
        db._conn,
        cid,
        "2025-03-02",
        50.0,
        [(inv_id, 50.0)],
        bank_account_id=None,
        method="Check",
        reference="",
        memo="",
    )

    refreshed = w.refresh_loaded_invoice_payment_status([inv_id])
    assert refreshed is True
    assert w._invoice_status_badge.isHidden() is False, (
        "Badge must become visible (PAID) when balance hits zero via Receive Payments."
    )
    assert w._invoice_status_badge.text() == "PAID"
    assert w._current_invoice_id == inv_id, (
        "Refresh must NOT clobber the loaded invoice id (Save/Print still target the same row)."
    )
    db.close()


def test_refresh_loaded_invoice_payment_status_ignores_other_invoice_ids(
    qapp: QApplication, tmp_path
) -> None:
    """Posting against an unrelated invoice must not refresh the currently loaded invoice."""
    db_path = tmp_path / "inv_pay_refresh_ignore.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "OtherCo")
    open_id = business.create_invoice(
        db._conn,
        cid,
        "OPEN-1",
        "2025-04-01",
        lines=[{"description": "A", "qty": 1.0, "rate": 10.0}],
    )
    other_id = business.create_invoice(
        db._conn,
        cid,
        "OTHER-1",
        "2025-04-02",
        lines=[{"description": "B", "qty": 1.0, "rate": 20.0}],
    )
    w = InvoiceScreen(ap_conn=db._conn)
    assert w.open_invoice_by_id(open_id) is True
    refreshed = w.refresh_loaded_invoice_payment_status([other_id])
    assert refreshed is False, (
        "Refresh must early-return when the posted invoice ids do not include the loaded invoice."
    )
    db.close()


def test_refresh_loaded_invoice_payment_status_no_op_when_no_invoice_loaded(
    qapp: QApplication, tmp_path
) -> None:
    """No invoice loaded → refresh is a clean no-op (no exception, returns False)."""
    db_path = tmp_path / "inv_pay_refresh_noop.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    w = InvoiceScreen(ap_conn=db._conn)
    assert w._current_invoice_id is None
    assert w.refresh_loaded_invoice_payment_status([1, 2, 3]) is False
    assert w.refresh_loaded_invoice_payment_status(None) is False
    db.close()


def test_invoice_screen_ship_to_defaults_from_bill_to_on_customer_select(
    qapp: QApplication, tmp_path
) -> None:
    """QB Pro: no separate customer ship-to → Ship To copies the Bill To block."""
    db_path = tmp_path / "inv_ship_default.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(
        db._conn,
        "Acme Rentals",
        address="200 Oak Ave\nPortland, OR 97201",
    )
    w = InvoiceScreen(ap_conn=db._conn)
    w.bill_to_customer_panel().select_customer_by_id(cid)
    qapp.processEvents()
    bill = w._bill_to[1].toPlainText()
    ship = w._ship_to[1].toPlainText()
    assert "Acme Rentals" in bill
    assert "200 Oak Ave" in bill
    assert ship == bill
    db.close()


def test_invoice_screen_terms_drive_due_date(qapp: QApplication, tmp_path) -> None:
    """Changing Terms or Invoice Date fills Due Date (QuickBooks Pro)."""
    db_path = tmp_path / "inv_terms_due.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    w = InvoiceScreen(ap_conn=db._conn)
    w._date.setDate(QDate(2026, 1, 1))
    w._terms.setCurrentText("Net 30")
    qapp.processEvents()
    assert w._due_date.date() == QDate(2026, 1, 31)
    w._terms.setCurrentText("Due on receipt")
    qapp.processEvents()
    assert w._due_date.date() == QDate(2026, 1, 1)
    w._terms.setCurrentText("Net 15")
    w._date.setDate(QDate(2026, 3, 1))
    qapp.processEvents()
    assert w._due_date.date() == QDate(2026, 3, 16)
    db.close()


def test_invoice_screen_save_persists_ship_to_terms_and_due_date(
    qapp: QApplication, tmp_path
) -> None:
    """Ship To, terms, and computed due date round-trip on Save / reload."""
    db_path = tmp_path / "inv_ship_save.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "ShipCo", address="1 Main St")
    w = InvoiceScreen(ap_conn=db._conn)
    w._bill_customer_panel.select_customer_by_id(cid)
    w._inv_number.setText("88001")
    w._date.setDate(QDate(2026, 3, 1))
    w._terms.setCurrentText("Net 15")
    qapp.processEvents()
    w._ship_to[1].setPlainText("Warehouse 9\nDock B")
    desc = w._table.cellWidget(0, 2)
    assert isinstance(desc, QLineEdit)
    desc.setText("Haul")
    rate = w._table.cellWidget(0, 4)
    qty = w._table.cellWidget(0, 5)
    assert isinstance(rate, QDoubleSpinBox) and isinstance(qty, QDoubleSpinBox)
    rate.setValue(40.0)
    qty.setValue(3.0)
    amt = w._table.cellWidget(0, 6)
    assert isinstance(amt, QDoubleSpinBox)
    assert abs(amt.value() - 120.0) < 0.01
    w.show()
    qapp.processEvents()
    with patch("desktop_app.invoice_screen.ensure_invoice_output_folder", return_value=None):
        QTest.mouseClick(w._btn_save, Qt.MouseButton.LeftButton)
        qapp.processEvents()
    rows = business.list_invoices(db._conn)
    assert len(rows) == 1
    iid = int(dict(rows[0])["id"])
    inv, lines = business.get_invoice_detail(db._conn, iid)
    d = dict(inv)
    assert (d.get("ship_to") or "").strip() == "Warehouse 9\nDock B"
    assert (d.get("terms") or "").strip() == "Net 15"
    assert (d.get("due_date") or "").strip()[:10] == "2026-03-16"
    assert abs(float(dict(lines[0]).get("line_total") or 0) - 120.0) < 0.02
    assert w.open_invoice_by_id(iid) is True
    qapp.processEvents()
    assert w._ship_to[1].toPlainText().strip() == "Warehouse 9\nDock B"
    assert w._terms.currentText() == "Net 15"
    assert w._due_date.date() == QDate(2026, 3, 16)
    db.close()


def test_invoice_screen_suggested_number_increments_prefix_from_last_saved(
    qapp: QApplication, tmp_path
) -> None:
    """Next invoice # follows the last saved number, including a prefix (QB Pro)."""
    db_path = tmp_path / "inv_prefix_num.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "PrefCo")
    business.create_invoice(
        db._conn,
        cid,
        "INV-100",
        "2026-01-01",
        lines=[{"description": "A", "qty": 1.0, "rate": 1.0}],
    )
    w = InvoiceScreen(ap_conn=db._conn)
    assert w._inv_number.text() == "INV-101"
    db.close()


def test_create_invoices_qb_header_layout(qapp: QApplication) -> None:
    """Create Invoices matches the QB Pro (Rightworks) field set and column order."""
    w = InvoiceScreen()
    assert w.windowTitle() == "Create Invoices"
    labels = [lb.text() for lb in w.findChildren(QLabel)]
    assert "Invoice" in labels
    assert "CUSTOMER:JOB" in labels
    assert "ACCOUNT" in labels
    assert "TEMPLATE" in labels
    assert "DATE" in labels
    assert "INVOICE #" in labels
    assert "PO/CONTRACT#" in labels
    assert "NAME/JOB#" in labels
    assert "CUSTOMER MESSAGE" in labels
    assert "MEMO" in labels
    assert "Bill To" in labels
    assert "Ship To" in labels
    assert w._ar_account.currentText() == _DEFAULT_AR_ACCOUNT
    assert w._invoice_template.currentText() == _DEFAULT_INVOICE_TEMPLATE
    tmpl_items = [w._invoice_template.itemText(i) for i in range(w._invoice_template.count())]
    assert all("CHAVAN" not in t.upper() for t in tmpl_items)
    ribbon = w.findChild(QTabWidget, "invoiceRibbonTabs")
    assert ribbon is not None
    ribbon_tabs = [ribbon.tabText(i) for i in range(ribbon.count())]
    assert ribbon_tabs == ["Main", "Formatting", "Send/Ship", "Reports"]
    assert w._invoice_tabs.tabText(0) == "Create Invoices"
    t = w.findChild(QTableWidget, "invoiceLinesTable")
    assert t is not None
    assert [t.horizontalHeaderItem(i).text() for i in range(7)] == [
        "SERVICED ON",
        "JL #",
        "DESCRIPTION",
        "BOL#",
        "RATE",
        "QUANTITY",
        "AMOUNT",
    ]
    assert "Total: $0.00" in w._lbl_total.text()
    assert "Payments Applied: $0.00" in w._lbl_payments.text()
    assert "Balance Due: $0.00" in w._lbl_balance.text()
    job_bar = w.findChild(QFrame, "invoiceCustomerJobBar")
    assert job_bar is not None
    bar_ss = job_bar.styleSheet().lower()
    assert "#1e4a78" not in bar_ss
    assert "#ffffff" in bar_ss
    cj = w.findChild(QLabel, "invoiceCustomerJobCaption")
    assert cj is not None
    cap_ss = cj.styleSheet().lower()
    assert "#f3f6fa" not in cap_ss
    assert "#4a5560" in cap_ss or "#1a1a1a" in cap_ss
    title = w.findChild(QLabel, "createInvoicesTitle")
    assert title is not None
    title_ss = title.styleSheet().lower()
    assert "#1e4a78" not in title_ss
    assert "transparent" in title_ss or "#ffffff" in title_ss
    assert "#3d4a54" in title_ss
    for editor in (w._po, w._job, w._inv_number, w._date, w._terms, w._due_date):
        wrap = editor.parentWidget()
        assert wrap is not None
        assert wrap.objectName() == "invoiceCompactMetaField"
        fill = wrap.palette().color(QPalette.ColorRole.Window).name().lower()
        assert fill in ("#ffffff", "#f4f7fa")
        assert "#1a1a2e" not in wrap.styleSheet().lower()
        assert "#ffffff" in wrap.styleSheet().lower()


def test_create_invoices_meta_captions_stay_light_under_app_dark_theme(
    qapp: QApplication,
) -> None:
    """App dark theme must not paint navy redaction bars behind PO / DATE / TERMS captions."""
    from desktop_app.theme import BG_PRIMARY, apply_dark_theme

    old_ss = qapp.styleSheet()
    old_pal = QPalette(qapp.palette())
    try:
        apply_dark_theme(qapp)
        w = InvoiceScreen()
        w.show()
        qapp.processEvents()
        navy = BG_PRIMARY.lower()
        for editor in (w._po, w._job, w._inv_number, w._date, w._terms, w._due_date):
            wrap = editor.parentWidget()
            assert wrap is not None
            assert wrap.objectName() == "invoiceCompactMetaField"
            fill = wrap.palette().color(QPalette.ColorRole.Window).name().lower()
            assert fill != navy
            assert fill in ("#ffffff", "#f4f7fa")
            cap = wrap.findChild(QLabel)
            assert cap is not None
            cap_ss = cap.styleSheet().lower()
            assert "transparent" in cap_ss
            assert "#4a5560" in cap_ss or "#1a1a1a" in cap_ss
        w.close()
    finally:
        qapp.setStyleSheet(old_ss)
        qapp.setPalette(old_pal)


def test_create_invoices_empty_line_cells_are_blank(qapp: QApplication) -> None:
    """Column headers name the fields; empty line cells have no gray hint and no $0.00 filler."""
    w = InvoiceScreen()
    w.show()
    qapp.processEvents()
    t = w.findChild(QTableWidget, "invoiceLinesTable")
    assert t is not None
    assert t.horizontalHeaderItem(0).text() == "SERVICED ON"
    assert t.horizontalHeaderItem(1).text() == "JL #"
    for col in range(4):
        cell = t.cellWidget(0, col)
        assert isinstance(cell, QLineEdit)
        assert (cell.placeholderText() or "").strip() == ""
        assert (cell.text() or "").strip() == ""
        assert "click" not in (cell.placeholderText() or "").lower()
    rate = t.cellWidget(0, 4)
    qty = t.cellWidget(0, 5)
    amt = t.cellWidget(0, 6)
    assert isinstance(rate, QDoubleSpinBox)
    assert isinstance(qty, QDoubleSpinBox)
    assert isinstance(amt, QDoubleSpinBox)
    for spin in (rate, qty, amt):
        assert spin.value() == 0.0
        shown = (spin.lineEdit().text() if spin.lineEdit() is not None else spin.text()) or ""
        assert shown.strip() == ""
        assert "0.00" not in shown
    rate.setValue(12.5)
    qty.setValue(2.0)
    qapp.processEvents()
    rate_shown = (rate.lineEdit().text() if rate.lineEdit() is not None else rate.text()) or ""
    amt_shown = (amt.lineEdit().text() if amt.lineEdit() is not None else amt.text()) or ""
    assert "12.50" in rate_shown.replace(",", "")
    assert "25.00" in amt_shown.replace(",", "")


def test_create_invoices_line_grid_dominates_window_height(qapp: QApplication) -> None:
    """QB Pro proportions: the line grid is the tallest region, many blank rows visible."""
    w = InvoiceScreen()
    w.resize(1200, 800)
    w.show()
    qapp.processEvents()
    t = w.findChild(QTableWidget, "invoiceLinesTable")
    assert t is not None
    row_h = max(1, t.rowHeight(0))
    visible_rows = t.viewport().height() // row_h
    assert visible_rows >= 8
    assert t.height() >= int(w.height() * 0.40)
    widths = [t.columnWidth(i) for i in range(t.columnCount())]
    desc_w = widths[InvoiceScreen._LINE_DESC_COL]
    assert desc_w == max(widths)
    assert desc_w >= int(sum(widths) * 0.32)
    assert t.horizontalScrollBar().maximum() == 0
    assert not w._invoice_tabs.tabBar().isVisible()
    ribbon = w.findChild(QTabWidget, "invoiceRibbonTabs")
    assert ribbon is not None
    assert ribbon.height() <= 56
    header = w.findChild(QFrame, "invoiceHeaderBand")
    assert header is not None
    assert t.height() > header.height()
    w._btn_intake.click()
    qapp.processEvents()
    assert w._invoice_tabs.currentIndex() == 1
    assert w._invoice_tabs.tabBar().isVisible()


def test_create_invoices_save_close_stays_on_saved_invoice(
    qapp: QApplication, tmp_path
) -> None:
    """Save & Close persists and keeps the saved invoice on the form (does not advance)."""
    db_path = tmp_path / "inv_save_close.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "CloseCo")
    w = InvoiceScreen(ap_conn=db._conn)
    w._bill_customer_panel.select_customer_by_id(cid)
    w._inv_number.setText("77001")
    desc = w._table.cellWidget(0, 2)
    assert isinstance(desc, QLineEdit)
    desc.setText("Haul")
    rate = w._table.cellWidget(0, 4)
    qty = w._table.cellWidget(0, 5)
    assert isinstance(rate, QDoubleSpinBox) and isinstance(qty, QDoubleSpinBox)
    rate.setValue(10.0)
    qty.setValue(1.0)
    w._customer_message.setCurrentText("Thank you for your business.")
    w._memo_edit.setText("Dock notes")
    w.show()
    qapp.processEvents()
    with patch("desktop_app.invoice_screen.ensure_invoice_output_folder", return_value=None):
        QTest.mouseClick(w._btn_save_close, Qt.MouseButton.LeftButton)
        qapp.processEvents()
    invs = business.list_invoices(db._conn)
    assert any((r["invoice_number"] or "").strip() == "77001" for r in invs)
    assert w._inv_number.text() == "77001"
    assert w._current_invoice_id is not None
    assert "Thank you for your business." in (w._customer_message.currentText() or "")
    assert w._memo_edit.text() == "Dock notes"
    db.close()


def test_create_invoices_company_template_from_settings_not_hardcoded_chavan(
    qapp: QApplication, tmp_path
) -> None:
    """Live company template names come from company_settings, never a hardcoded corp name."""
    db_path = tmp_path / "inv_tmpl.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    business.set_setting(db._conn, "invoice_template_name", "Custom Truck Invoice")
    w = InvoiceScreen(ap_conn=db._conn)
    items = [w._invoice_template.itemText(i) for i in range(w._invoice_template.count())]
    assert _DEFAULT_INVOICE_TEMPLATE in items
    assert "Custom Truck Invoice" in items
    assert all("CHAVAN" not in t.upper() for t in items)
    db.close()


def test_invoice_pdf_basename_is_invoice_number() -> None:
    assert invoice_pdf_basename("8114") == "8114.pdf"
    assert invoice_pdf_basename(" 8114 ") == "8114.pdf"


def test_invoice_form_dirty_and_leave_prompt_saves_without_folder_or_company_dialog(
    qapp: QApplication, tmp_path
) -> None:
    db_path = tmp_path / "inv_leave.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "LeaveCo")
    w = InvoiceScreen(ap_conn=db._conn)
    assert w._is_form_dirty() is False
    w._bill_customer_panel.select_customer_by_id(cid)
    w._inv_number.setText("8114")
    desc = w._table.cellWidget(0, 2)
    assert isinstance(desc, QLineEdit)
    desc.setText("Haul")
    rate = w._table.cellWidget(0, 4)
    qty = w._table.cellWidget(0, 5)
    assert isinstance(rate, QDoubleSpinBox) and isinstance(qty, QDoubleSpinBox)
    rate.setValue(10.0)
    qty.setValue(1.0)
    assert w._is_form_dirty() is True
    with (
        patch(
            "desktop_app.invoice_screen.message_box_question_yes_no_cancel",
            return_value="yes",
        ) as m_ask,
        patch(
            "desktop_app.invoice_screen.ensure_invoice_output_folder"
        ) as m_folder,
        patch(
            "desktop_app.invoice_screen.message_box_information_ok"
        ) as m_info,
    ):
        assert w._confirm_leave_loaded_invoice() is True
    m_ask.assert_called_once()
    assert "8114" in str(m_ask.call_args)
    m_folder.assert_not_called()
    m_info.assert_not_called()
    rows = business.list_invoices(db._conn)
    assert any((r["invoice_number"] or "").strip() == "8114" for r in rows)
    assert w._is_form_dirty() is False
    db.close()


def test_invoice_leave_prompt_no_does_not_save(qapp: QApplication, tmp_path) -> None:
    db_path = tmp_path / "inv_leave_no.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "NoSaveCo")
    w = InvoiceScreen(ap_conn=db._conn)
    w._bill_customer_panel.select_customer_by_id(cid)
    w._inv_number.setText("8115")
    desc = w._table.cellWidget(0, 2)
    assert isinstance(desc, QLineEdit)
    desc.setText("Haul")
    with patch(
        "desktop_app.invoice_screen.message_box_question_yes_no_cancel",
        return_value="no",
    ):
        assert w._confirm_leave_loaded_invoice() is True
    assert business.list_invoices(db._conn) == []
    assert w._is_form_dirty() is False
    assert w.selected_bill_to_customer_id() is None
    db.close()


def test_invoice_leave_prompt_cancel_keeps_form(qapp: QApplication, tmp_path) -> None:
    db_path = tmp_path / "inv_leave_cancel.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "CancelCo")
    w = InvoiceScreen(ap_conn=db._conn)
    w._bill_customer_panel.select_customer_by_id(cid)
    w._inv_number.setText("8116")
    desc = w._table.cellWidget(0, 2)
    assert isinstance(desc, QLineEdit)
    desc.setText("Haul")
    with patch(
        "desktop_app.invoice_screen.message_box_question_yes_no_cancel",
        return_value="cancel",
    ):
        assert w._confirm_leave_loaded_invoice() is False
    assert business.list_invoices(db._conn) == []
    assert w._is_form_dirty() is True
    assert w.selected_bill_to_customer_id() == cid
    assert w._inv_number.text() == "8116"
    assert desc.text() == "Haul"
    db.close()


def test_invoice_save_asks_before_overwrite_pdf(
    qapp: QApplication, tmp_path
) -> None:
    db_path = tmp_path / "inv_ow.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    pdf_dir = tmp_path / "ow_pdf"
    pdf_dir.mkdir()
    existing = pdf_dir / "8114.pdf"
    existing.write_bytes(b"old")
    _INV_PREFS_QS.setValue("invoice_prefs/output_folder", str(pdf_dir))
    _INV_PREFS_QS.sync()
    cid = business.add_customer(db._conn, "OwCo")
    w = InvoiceScreen(ap_conn=db._conn)
    w._bill_customer_panel.select_customer_by_id(cid)
    w._inv_number.setText("8114")
    desc = w._table.cellWidget(0, 2)
    assert isinstance(desc, QLineEdit)
    desc.setText("Haul")
    rate = w._table.cellWidget(0, 4)
    qty = w._table.cellWidget(0, 5)
    assert isinstance(rate, QDoubleSpinBox) and isinstance(qty, QDoubleSpinBox)
    rate.setValue(5.0)
    qty.setValue(1.0)
    with patch(
        "desktop_app.invoice_screen.message_box_question_yes_no",
        return_value=False,
    ):
        QTest.mouseClick(w._btn_ribbon_save, Qt.MouseButton.LeftButton)
        qapp.processEvents()
    assert existing.read_bytes() == b"old"
    assert business.list_invoices(db._conn)
    db.close()


def test_invoice_save_as_remembers_folder_per_company(tmp_path) -> None:
    from desktop_app.invoice_preferences import (
        get_invoice_save_as_folder,
        set_invoice_save_as_folder,
    )

    a = tmp_path / "co_a"
    b = tmp_path / "co_b"
    a.mkdir()
    b.mkdir()
    set_invoice_save_as_folder("sid-a", str(a))
    set_invoice_save_as_folder("sid-b", str(b))
    assert os.path.normpath(get_invoice_save_as_folder("sid-a")) == os.path.normpath(str(a))
    assert os.path.normpath(get_invoice_save_as_folder("sid-b")) == os.path.normpath(str(b))


def test_prompt_invoice_save_as_path_puts_basename_in_name_box() -> None:
    import inspect

    from desktop_app.invoice_preferences import prompt_invoice_save_as_path

    src = inspect.getsource(prompt_invoice_save_as_path)
    assert "selectFile(name)" in src
    assert "os.path.basename" in src
    assert "setDirectory(start)" in src
    assert "DontConfirmOverwrite" in src


def test_invoice_previous_asks_before_replacing_dirty_draft(
    qapp: QApplication, tmp_path
) -> None:
    db_path = tmp_path / "inv_prev_dirty.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "PrevCo")
    business.create_invoice(
        db._conn,
        cid,
        "8100",
        "2026-01-01",
        lines=[{"description": "Old", "qty": 1.0, "rate": 1.0}],
    )
    w = InvoiceScreen(ap_conn=db._conn)
    w._bill_customer_panel.select_customer_by_id(cid)
    w._inv_number.setText("8114")
    desc = w._table.cellWidget(0, 2)
    assert isinstance(desc, QLineEdit)
    desc.setText("New haul")
    assert w._is_form_dirty() is True
    with patch(
        "desktop_app.invoice_screen.message_box_question_yes_no_cancel",
        return_value="no",
    ) as m_ask:
        w._on_reverse_invoice()
    m_ask.assert_called()
    assert "8114" in str(m_ask.call_args)
    assert business.get_invoice_id_by_number(db._conn, "8114") is None
    assert w._inv_number.text() == "8100"
    db.close()


def test_invoice_previous_cancel_keeps_dirty_draft(
    qapp: QApplication, tmp_path
) -> None:
    db_path = tmp_path / "inv_prev_cancel.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "PrevCancelCo")
    business.create_invoice(
        db._conn,
        cid,
        "8100",
        "2026-01-01",
        lines=[{"description": "Old", "qty": 1.0, "rate": 1.0}],
    )
    w = InvoiceScreen(ap_conn=db._conn)
    w._bill_customer_panel.select_customer_by_id(cid)
    w._inv_number.setText("8114")
    desc = w._table.cellWidget(0, 2)
    assert isinstance(desc, QLineEdit)
    desc.setText("New haul")
    with patch(
        "desktop_app.invoice_screen.message_box_question_yes_no_cancel",
        return_value="cancel",
    ):
        w._on_reverse_invoice()
    assert w._inv_number.text() == "8114"
    assert desc.text() == "New haul"
    assert w._is_form_dirty() is True
    assert business.get_invoice_id_by_number(db._conn, "8114") is None
    db.close()
