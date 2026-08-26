"""Headless capture of Create Invoices — helpers used by scripts/capture_ui_screenshot.py."""

from __future__ import annotations

import importlib.util
import sys

import pytest
from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QFrame

from tests.repo_paths import SCRIPTS_CAPTURE_UI_SCREENSHOT_PY

_spec = importlib.util.spec_from_file_location(
    "capture_ui_screenshot",
    SCRIPTS_CAPTURE_UI_SCREENSHOT_PY,
)
assert _spec is not None and _spec.loader is not None
_capture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_capture)

fill_create_invoice_form_for_capture = _capture.fill_create_invoice_form_for_capture
grab_widget_png = _capture.grab_widget_png
seed_capture_company_db = _capture.seed_capture_company_db


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_capture_script_documents_invoice_create_png() -> None:
    text = SCRIPTS_CAPTURE_UI_SCREENSHOT_PY.read_text(encoding="utf-8")
    assert "invoice_create.png" in text
    assert "invoice_create_header.png" in text
    assert "main_window.png" in text
    assert "fill_create_invoice_form_for_capture" in text


def test_fill_create_invoice_form_shows_qb_header_fields(
    tmp_path, qapp: QApplication, isolated_branded_app_data_env
) -> None:
    from desktop_app.main import MainWindow
    from probooksai.business import due_date_iso_from_terms

    assert QApplication.instance() is qapp

    db_path = tmp_path / "capture.db"
    customer_id = seed_capture_company_db(db_path)
    window = MainWindow(db_path=str(db_path))
    try:
        window.showNormal()
        window.resize(1440, 960)
        qapp.processEvents()
        fill_create_invoice_form_for_capture(window, customer_id)
        inv = window._invoice_screen
        assert "Acme Logistics LLC" in inv._bill_to[1].toPlainText()
        assert "Acme Warehouse" in inv._ship_to[1].toPlainText()
        assert inv._inv_number.text() == "1"
        assert inv._date.date() == QDate.currentDate()
        assert inv._terms.currentText() == "Net 30"
        due_iso = due_date_iso_from_terms(
            inv._date.date().toString("yyyy-MM-dd"),
            "Net 30",
        )
        assert inv._due_date.date().toString("yyyy-MM-dd") == due_iso
        assert inv._table.horizontalHeaderItem(6).text() == "Amount"
        amt = inv._table.cellWidget(0, 6)
        assert isinstance(amt, QDoubleSpinBox)
        assert abs(amt.value() - 500.0) < 0.01
        out = tmp_path / "invoice_create.png"
        grab_widget_png(window, out)
        form = inv.findChild(QFrame, "invoiceLightPanel")
        if form is not None:
            grab_widget_png(form, tmp_path / "invoice_create_header.png", max_height=560)
        assert out.is_file()
        assert out.stat().st_size > 2000
    finally:
        window.close()
        window.deleteLater()
        qapp.processEvents()
