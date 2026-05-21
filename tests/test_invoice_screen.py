"""Invoice screen — structure; Bill To uses customers when DB connected."""

from __future__ import annotations

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
    assert t.horizontalHeaderItem(0).text() == "Serviced On"
    assert t.horizontalHeaderItem(2).text() == "Description"
    assert t.horizontalHeaderItem(3).text() == "BOL#"
    assert t.horizontalHeaderItem(6).text() == "Amount"
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
    assert w._btn_new_invoice.text() == "New Invoice"
    assert w._btn_clear_fields.text() == "Clear Fields"
    assert w._btn_save.text() == "Save"
    assert w._btn_print.text() == "Print…"
    assert "Prev" in w._btn_reverse.text()
    assert "Next" in w._btn_forward.text()
    # Removed buttons
    assert not hasattr(w, "_btn_import_pdf")
    assert not hasattr(w, "_btn_new_customer")
    assert not hasattr(w, "_btn_export_pdf")
    assert not hasattr(w, "_btn_ar_new_inv")
    assert not hasattr(w, "_btn_ar_export_inv")
    assert not hasattr(w, "_status_badge")


def test_invoice_screen_save_creates_invoice_and_advances(
    qapp: QApplication, tmp_path
) -> None:
    """Save persists to DB and advances to next invoice number."""
    db_path = tmp_path / "invoice_save_adv.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "SaveAdvCo")
    w = InvoiceScreen(ap_conn=db._conn)
    w._bill_customer_panel.select_customer_by_id(cid)
    w._inv_number.setText("93001")
    desc = w._table.cellWidget(0, 2)
    assert isinstance(desc, QLineEdit)
    desc.setText("Save line")
    rate = w._table.cellWidget(0, 4)
    assert isinstance(rate, QDoubleSpinBox)
    rate.setValue(50.0)
    qty = w._table.cellWidget(0, 5)
    assert isinstance(qty, QDoubleSpinBox)
    qty.setValue(1.0)
    QTest.mouseClick(w._btn_save, Qt.MouseButton.LeftButton)
    qapp.processEvents()
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
    with patch("desktop_app.invoice_screen.QPrintDialog") as mock_dlg:
        mock_dlg.return_value.exec.return_value = True
        with patch.object(QTextDocument, "print_", lambda self, p: None):
            QTest.mouseClick(w._btn_print, Qt.MouseButton.LeftButton)
            qapp.processEvents()
    invs = business.list_invoices(db._conn)
    assert any((r["invoice_number"] or "").strip() == "92001" for r in invs)
    assert w._inv_number.text() == "92002"
    db.close()


def test_invoice_screen_forward_loads_first_invoice(qapp: QApplication, tmp_path) -> None:
    """Prev from blank draft loads the last (only) saved invoice; Next on blank draft is a no-op."""
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
    # Next on blank draft (end of queue) is a no-op — stays on blank draft.
    w._on_forward_invoice()
    assert w._current_invoice_id is None
    # Prev from blank draft navigates back to the last saved invoice.
    w._on_reverse_invoice()
    assert w._inv_number.text() == "14001"
    assert "Line A" in (w._table.cellWidget(0, 2).text() or "")
    db.close()


def test_invoice_screen_clear_fields_keeps_invoice_number(qapp: QApplication, tmp_path) -> None:
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
    # Start is blank draft (idx=None); Prev navigates to last (only) saved invoice.
    w._on_reverse_invoice()
    assert w._inv_number.text() == "15001"
    # Auto-confirm the "leave loaded invoice" dialog in tests.
    with patch.object(w, "_confirm_leave_loaded_invoice", return_value=True):
        w._on_clear_fields()
    assert w._inv_number.text() == "15001"
    assert not (w._table.cellWidget(0, 2).text() or "").strip()
    db.close()


def test_invoice_screen_leave_confirmation_blocks_nav(qapp: QApplication, tmp_path) -> None:
    """When a saved invoice is loaded, navigation/clear is blocked when user says No."""
    db_path = tmp_path / "invoice_confirm.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "ConfirmCo")
    business.create_invoice(
        db._conn, cid, "C001", "2025-06-01",
        lines=[{"description": "Svc", "qty": 1.0, "rate": 100.0}],
    )
    w = InvoiceScreen(ap_conn=db._conn)
    # Navigate to the loaded invoice
    w._on_reverse_invoice()
    assert w._current_invoice_id is not None
    loaded_id = w._current_invoice_id

    # User clicks No → navigation is blocked
    with patch.object(w, "_confirm_leave_loaded_invoice", return_value=False):
        w._on_clear_fields()
    assert w._current_invoice_id == loaded_id, "Clear Fields must be blocked when user says No"

    with patch.object(w, "_confirm_leave_loaded_invoice", return_value=False):
        w._go_to_new_invoice_draft()
    assert w._current_invoice_id == loaded_id, "New Invoice must be blocked when user says No"

    with patch.object(w, "_confirm_leave_loaded_invoice", return_value=False):
        w._on_reverse_invoice()
    assert w._current_invoice_id == loaded_id, "Prev must be blocked when user says No"

    with patch.object(w, "_confirm_leave_loaded_invoice", return_value=False):
        w._on_forward_invoice()
    assert w._current_invoice_id == loaded_id, "Next must be blocked when user says No"

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


def test_invoice_validation_rejects_empty_and_zero_amount_lines(
    qapp: QApplication, tmp_path
) -> None:
    """Pilot: cannot save without at least one line with non-zero rate×qty."""
    db_path = tmp_path / "invoice_val_lines.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "ValCo")
    w = InvoiceScreen(ap_conn=db._conn)
    w._bill_customer_panel.select_customer_by_id(cid)
    w._inv_number.setText("88001")
    ok, msg, iid = w._try_persist_invoice()
    assert ok is False
    assert iid is None
    assert "line" in msg.lower() and ("amount" in msg.lower() or "non-zero" in msg.lower())

    desc = w._table.cellWidget(0, 2)
    assert isinstance(desc, QLineEdit)
    desc.setText("Description only")
    ok2, msg2, _ = w._try_persist_invoice()
    assert ok2 is False
    assert "non-zero" in msg2.lower()
    db.close()


def test_invoice_pilot_smoke_save_reload_nav_open_by_id(
    qapp: QApplication, tmp_path
) -> None:
    """Create → save → reload → forward → open_invoice_by_id still works after validation rules."""
    db_path = tmp_path / "invoice_pilot_smoke.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    pdf_dir = tmp_path / "invoice_pilot_pdf"
    pdf_dir.mkdir()
    _INV_PREFS_QS.setValue("invoice_prefs/output_folder", str(pdf_dir))
    _INV_PREFS_QS.sync()
    cid = business.add_customer(db._conn, "PilotCo")
    w = InvoiceScreen(ap_conn=db._conn)
    w._bill_customer_panel.select_customer_by_id(cid)
    w._inv_number.setText("91050")
    desc = w._table.cellWidget(0, 2)
    assert isinstance(desc, QLineEdit)
    desc.setText("Pilot line")
    rate = w._table.cellWidget(0, 4)
    assert isinstance(rate, QDoubleSpinBox)
    rate.setValue(25.0)
    qty = w._table.cellWidget(0, 5)
    assert isinstance(qty, QDoubleSpinBox)
    qty.setValue(1.0)
    QTest.mouseClick(w._btn_save, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    invs = business.list_invoices(db._conn)
    assert len(invs) == 1
    inv_id = int(invs[0]["id"])
    # Auto-confirm "leave loaded invoice" dialogs throughout this navigation test.
    with patch.object(w, "_confirm_leave_loaded_invoice", return_value=True):
        w._go_to_new_invoice_draft()
        # Next on blank draft now does nothing (end of queue); use Prev to go back.
        w._on_forward_invoice()
        assert w._current_invoice_id is None  # still on blank draft
        w._on_reverse_invoice()
        assert w._current_invoice_id == inv_id
        assert w._inv_number.text() == "91050"
        w._go_to_new_invoice_draft()
    assert w.open_invoice_by_id(inv_id) is True
    assert w._current_invoice_id == inv_id
    with patch("desktop_app.invoice_screen.QPrintDialog") as mock_dlg:
        mock_dlg.return_value.exec.return_value = True
        with patch.object(QTextDocument, "print_", lambda self, p: None):
            QTest.mouseClick(w._btn_print, Qt.MouseButton.LeftButton)
            qapp.processEvents()
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
    with patch("desktop_app.invoice_screen.QPrintDialog") as m_dlg:
        w._on_print_invoice()
        m_dlg.assert_not_called()
    assert business.list_invoices(db._conn) == []
    db.close()


def test_invoice_dirty_tracking_no_dialog_when_unchanged(
    qapp: QApplication, tmp_path
) -> None:
    """No confirmation dialog fires when navigating away from an unmodified loaded invoice."""
    db_path = tmp_path / "invoice_dirty_clean.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "CleanCo")
    business.create_invoice(
        db._conn, cid, "D001", "2025-01-01",
        lines=[{"description": "Svc", "qty": 1.0, "rate": 50.0}],
    )
    w = InvoiceScreen(ap_conn=db._conn)
    # Load the invoice
    w._on_reverse_invoice()
    assert w._current_invoice_id is not None
    # Form is clean (just loaded, nothing changed) — dirty check should be False
    assert not w._is_form_dirty(), "Form should be clean right after load"
    # Navigation should proceed without any dialog (no patching needed)
    w._on_forward_invoice()
    assert w._current_invoice_id is None, "Should have navigated to blank draft"
    db.close()


def test_invoice_dirty_tracking_dialog_fires_after_edit(
    qapp: QApplication, tmp_path
) -> None:
    """Confirmation dialog fires when the form has been edited since last load."""
    db_path = tmp_path / "invoice_dirty_edit.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    cid = business.add_customer(db._conn, "DirtyCo")
    business.create_invoice(
        db._conn, cid, "D002", "2025-02-01",
        lines=[{"description": "Original", "qty": 1.0, "rate": 100.0}],
    )
    w = InvoiceScreen(ap_conn=db._conn)
    # Load the invoice
    w._on_reverse_invoice()
    assert w._current_invoice_id is not None
    assert not w._is_form_dirty(), "Should be clean after load"
    # Make a change
    desc = w._table.cellWidget(0, 2)
    assert isinstance(desc, QLineEdit)
    original_text = desc.text()
    desc.setText(original_text + " EDITED")
    assert w._is_form_dirty(), "Should be dirty after editing description"
    # Navigation must call the dialog; patch it to return False (Stay)
    with patch.object(w, "_confirm_leave_loaded_invoice", return_value=False) as mock_confirm:
        w._on_forward_invoice()
        mock_confirm.assert_called_once()
    assert w._current_invoice_id is not None, "Should stay on invoice after user chose Stay"
    db.close()
