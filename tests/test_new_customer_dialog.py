"""New customer dialog — one-column form, save on OK, cancel does nothing."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
)

from desktop_app.new_customer_dialog import NewCustomerDialog
from probooksai import business
from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import apply_extensions


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def db(tmp_path: Path) -> BankDatabase:
    b = BankDatabase(db_path=str(tmp_path / "new_customer_ui.db"))
    apply_extensions(b._conn)
    yield b
    b.close()


def test_new_customer_dialog_one_column_field_order(qapp: QApplication, db: BankDatabase) -> None:
    dlg = NewCustomerDialog(db._conn)
    labels = [
        lb.text()
        for lb in dlg.findChildren(QLabel)
        if lb.objectName() != "newCustomerParentLabel"
        and lb.text()
        in {"Name", "Email", "Phone", "Address", "Notes", "Customer type"}
    ]
    assert labels == ["Name", "Email", "Phone", "Address", "Notes", "Customer type"]
    assert dlg.findChild(QLineEdit, "newCustomerName") is not None
    assert dlg.findChild(QLineEdit, "newCustomerEmail") is not None
    assert dlg.findChild(QLineEdit, "newCustomerPhone") is not None
    assert dlg.findChild(QPlainTextEdit, "newCustomerAddress") is not None
    assert dlg.findChild(QPlainTextEdit, "newCustomerNotes") is not None
    type_cb = dlg.findChild(QComboBox, "newCustomerType")
    assert type_cb is not None
    assert type_cb.currentData() == "standalone"
    assert not dlg.findChild(QLabel, "newCustomerParentLabel").isVisible()
    assert dlg.windowTitle() == "New customer"
    dlg.close()


def test_new_customer_ok_saves_and_cancel_does_nothing(
    qapp: QApplication, db: BankDatabase
) -> None:
    before = list(business.list_customers(db._conn))
    cancel = NewCustomerDialog(db._conn)
    cancel.findChild(QLineEdit, "newCustomerName").setText("Skipped Co")
    cancel.reject()
    assert cancel.saved_customer_id is None
    assert list(business.list_customers(db._conn)) == before
    cancel.close()

    dlg = NewCustomerDialog(db._conn)
    dlg.findChild(QLineEdit, "newCustomerName").setText("Harbor Logistics")
    dlg.findChild(QLineEdit, "newCustomerEmail").setText("ap@harbor.example")
    dlg.findChild(QLineEdit, "newCustomerPhone").setText("555-0199")
    dlg.findChild(QPlainTextEdit, "newCustomerAddress").setPlainText("10 Pier Rd")
    dlg.findChild(QPlainTextEdit, "newCustomerNotes").setPlainText("Net 15")
    cid = dlg._try_save()
    assert cid is not None
    row = business.get_customer(db._conn, cid)
    assert row is not None
    assert row["name"] == "Harbor Logistics"
    assert row["email"] == "ap@harbor.example"
    assert row["phone"] == "555-0199"
    assert "10 Pier Rd" in (row["address"] or "")
    dlg.close()


def test_new_customer_dialog_is_not_company_wizard() -> None:
    text = Path("desktop_app/new_customer_dialog.py").read_text(encoding="utf-8")
    assert "CreateCompanyFileDialog" not in text
    assert "FirstRunWizard" not in text
    assert "business_type" not in text
    assert "tax_structure" not in text
    assert "save_company_identity" not in text
