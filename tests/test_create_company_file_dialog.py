"""New Company setup wizard: required fields, validation, full identity payload."""

from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QApplication, QDialog

from desktop_app.create_company_file_dialog import CreateCompanyFileDialog


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_dialog_window_title_says_new_company(qapp: QApplication) -> None:
    dlg = CreateCompanyFileDialog()
    assert "new company" in dlg.windowTitle().lower()


def test_dialog_exposes_all_required_input_widgets(qapp: QApplication) -> None:
    """Wizard must capture Name, Address, Phone, Email, Business Type, Tax Structure, Tax ID."""
    dlg = CreateCompanyFileDialog()
    for attr in (
        "_name",
        "_address",
        "_phone",
        "_email",
        "_business_type",
        "_tax_structure",
        "_tax_id",
    ):
        assert hasattr(dlg, attr), f"Wizard is missing field widget {attr!r}"


def test_dialog_validation_rejects_empty_name(qapp: QApplication) -> None:
    """Submitting with no Company Name keeps the dialog open and surfaces an error."""
    dlg = CreateCompanyFileDialog()
    dlg._business_type.setCurrentIndex(dlg._business_type.findText("LLC"))
    dlg._tax_structure.setCurrentIndex(
        dlg._tax_structure.findText("LLC – Multi-member (1065)")
    )
    dlg._validate_and_accept()
    assert dlg.result() != QDialog.DialogCode.Accepted
    assert dlg._error.isHidden() is False
    assert "name" in dlg._error.text().lower()


def test_dialog_validation_rejects_empty_business_type(qapp: QApplication) -> None:
    dlg = CreateCompanyFileDialog()
    dlg._name.setText("Acme LLC")
    dlg._tax_structure.setCurrentIndex(
        dlg._tax_structure.findText("LLC – Multi-member (1065)")
    )
    dlg._validate_and_accept()
    assert dlg.result() != QDialog.DialogCode.Accepted
    assert dlg._error.isHidden() is False
    assert "business" in dlg._error.text().lower()


def test_dialog_validation_rejects_empty_tax_structure(qapp: QApplication) -> None:
    dlg = CreateCompanyFileDialog()
    dlg._name.setText("Acme LLC")
    dlg._business_type.setCurrentIndex(dlg._business_type.findText("LLC"))
    dlg._validate_and_accept()
    assert dlg.result() != QDialog.DialogCode.Accepted
    assert dlg._error.isHidden() is False
    assert "tax" in dlg._error.text().lower()


def test_dialog_identity_values_returns_full_payload(qapp: QApplication) -> None:
    """All seven fields surface in :meth:`identity_values` and match what the user typed."""
    dlg = CreateCompanyFileDialog()
    dlg._name.setText("Acme LLC")
    dlg._address.setPlainText("1 Main St\nSpringfield, ST 00001")
    dlg._phone.setText("555-0100")
    dlg._email.setText("billing@acme.example")
    dlg._business_type.setCurrentIndex(dlg._business_type.findText("LLC"))
    dlg._tax_structure.setCurrentIndex(
        dlg._tax_structure.findText("LLC – Multi-member (1065)")
    )
    dlg._tax_id.setText("12-3456789")
    dlg._validate_and_accept()
    v = dlg.identity_values()
    assert v == {
        "name": "Acme LLC",
        "address": "1 Main St\nSpringfield, ST 00001",
        "phone": "555-0100",
        "email": "billing@acme.example",
        "business_type": "LLC",
        "tax_structure": "LLC – Multi-member (1065)",
        "tax_id": "12-3456789",
    }
    assert dlg.result() == QDialog.DialogCode.Accepted
