"""My Company screen — QB Pro chrome, placeholder identity, Home open-hook."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QPushButton,
    QToolButton,
)

from desktop_app.my_company_screen import (
    PLACEHOLDER_COMPANY_NAME,
    PRODUCT_DISPLAY_NAME,
    PRODUCT_LICENSE,
    PRODUCT_NUMBER,
    SSN_PLACEHOLDER,
    MyCompanyEditDialog,
    MyCompanyScreen,
    load_my_company_fields,
    save_my_company_fields,
)
from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import apply_extensions

_FORBIDDEN = (
    "CHAVAN",
    "TRUCKING CORP",
    "9489-0911",
    "9499-0911",
    "401-228",
    "QuickBooks Desktop Pro Plus",
    "QuickBooks Enterprise",
)


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def db(tmp_path: Path) -> BankDatabase:
    b = BankDatabase(db_path=str(tmp_path / "my_company_ui.db"))
    apply_extensions(b._conn)
    yield b
    b.close()


def _labels(w) -> list[str]:
    return [lb.text() for lb in w.findChildren(QLabel)]


def test_my_company_layout_uses_placeholder_identity(qapp: QApplication, db: BankDatabase) -> None:
    w = MyCompanyScreen(ap_conn=db._conn)
    qapp.processEvents()
    labels = _labels(w)
    assert PLACEHOLDER_COMPANY_NAME in labels
    assert "COMPANY INFORMATION" in labels
    assert "Contact Name & Address" in labels
    assert "Main Phone" in labels
    assert "Fax" in labels
    assert "Email" in labels
    assert "Website" in labels
    assert "Legal Name & Address" in labels
    assert "EIN" in labels
    assert "SSN" in labels
    assert "Income Tax Form" in labels
    assert "Payroll Contact" in labels
    assert "Product Information" in labels
    assert "MANAGE YOUR APPS, SERVICES & SUBSCRIPTIONS" in labels
    assert "APPS, SERVICES & SUBSCRIPTIONS RECOMMENDED FOR YOU" in labels
    assert PRODUCT_DISPLAY_NAME in labels
    assert PRODUCT_LICENSE in labels
    assert PRODUCT_NUMBER in labels
    assert "ACTIVATED" in labels
    assert w.findChild(QLabel, "myCompanyHeaderName").text() == PLACEHOLDER_COMPANY_NAME
    assert w.findChild(QLabel, "myCompanyEin").text() == ""
    assert w.findChild(QLabel, "myCompanySsn").text() == SSN_PLACEHOLDER
    assert w.findChild(QToolButton, "myCompanyEditButton") is not None
    assert w.findChild(QPushButton, "myCompanyManageAccount") is not None
    assert w.findChild(QPushButton, "myCompanyQuickLink_history") is not None
    assert w.findChild(QPushButton, "myCompanyQuickLink_users") is not None
    assert w.findChild(QPushButton, "myCompanyQuickLink_methods") is not None
    assert w.findChild(QPushButton, "myCompanyQuickLink_details") is not None
    assert w.findChild(QPushButton, "myCompanySignIn") is not None
    blob = " ".join(labels)
    assert "Get E-commerce Integration" in blob
    assert "Turn On Payroll" in blob
    assert "Accept Credit Cards" in blob
    assert "Order Checks" in blob
    assert "ProBooks+ai Desktop Plus" in blob
    assert "Advanced Inventory" in blob
    assert w.findChild(QToolButton, "myCompanyCarouselNext") is not None
    w.close()


def test_my_company_fields_round_trip_generic_placeholders(
    qapp: QApplication, db: BankDatabase
) -> None:
    save_my_company_fields(
        db._conn,
        {
            "name": "Acme Haul LLC",
            "contact_address": "100 Example Ave\nAustin, TX 00000",
            "phone": "555-0100",
            "fax": "",
            "email": "billing@acme.example",
            "website": "https://acme.example",
            "legal_address": "",
            "ein": "",
            "ssn": SSN_PLACEHOLDER,
            "tax_form": "1120-S",
            "payroll_contact": "",
        },
    )
    data = load_my_company_fields(db._conn)
    assert data["name"] == "Acme Haul LLC"
    assert "100 Example Ave" in data["contact_address"]
    assert data["ein"] == ""
    assert data["ssn"] == SSN_PLACEHOLDER
    w = MyCompanyScreen(ap_conn=db._conn)
    qapp.processEvents()
    assert w.findChild(QLabel, "myCompanyHeaderName").text() == "Acme Haul LLC"
    assert w.findChild(QLabel, "myCompanyPhone").text() == "555-0100"
    assert w.findChild(QLabel, "myCompanyEin").text() == ""
    w.close()


def test_my_company_edit_dialog_defaults_to_placeholder(qapp: QApplication) -> None:
    dlg = MyCompanyEditDialog(load_my_company_fields(None))
    assert dlg._name.text() == ""
    assert dlg._ein.text() == ""
    assert dlg._ssn.text() == ""
    vals = dlg.values()
    assert vals["name"] == PLACEHOLDER_COMPANY_NAME
    assert vals["ein"] == ""
    dlg.close()


def test_my_company_main_window_tab_and_home_shortcut(
    qapp: QApplication, tmp_path: Path
) -> None:
    from desktop_app.main import MainWindow

    db_path = tmp_path / "my_company_nav.db"
    BankDatabase(str(db_path)).close()
    w = MainWindow(db_path=str(db_path))
    try:
        tabs = w._tabs
        assert "My Company" in tabs.tabText(5)
        assert isinstance(tabs.widget(5), MyCompanyScreen)
        tabs.setCurrentIndex(0)
        qapp.processEvents()
        btn = w._dashboard_tab.findChild(QToolButton, "homeShortcut_my_company")
        assert btn is not None
        btn.click()
        qapp.processEvents()
        assert tabs.currentWidget() is w._my_company_screen
        titles = _labels(tabs.currentWidget())
        assert PLACEHOLDER_COMPANY_NAME in titles
        assert "COMPANY INFORMATION" in titles
        assert PRODUCT_DISPLAY_NAME in titles
    finally:
        w.close()


def test_my_company_source_has_no_live_company_identity() -> None:
    text = Path("desktop_app/my_company_screen.py").read_text(encoding="utf-8")
    lowered = text.lower()
    for needle in _FORBIDDEN:
        assert needle.lower() not in lowered
    assert PLACEHOLDER_COMPANY_NAME in text
    assert PRODUCT_DISPLAY_NAME in text
    assert PRODUCT_LICENSE in text
    assert "layout designer" not in lowered


def test_capture_script_has_my_company_tab() -> None:
    text = Path("scripts/capture_ui_screenshot.py").read_text(encoding="utf-8")
    assert "--tab my-company" in text
    yml = Path(".github/workflows/ui-screenshot.yml").read_text(encoding="utf-8")
    assert "--tab my-company" in yml
