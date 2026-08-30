"""My Company screen — live company identity, no app-store upsell."""

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
    company_file_display_name,
    load_my_company_fields,
    save_my_company_fields,
)
from probooksai.company_identity import get_company_identity, save_company_identity
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


def test_my_company_layout_loads_filename_when_identity_empty(
    qapp: QApplication, db: BankDatabase
) -> None:
    w = MyCompanyScreen(ap_conn=db._conn)
    qapp.processEvents()
    labels = _labels(w)
    expected_name = company_file_display_name(db._conn)
    assert expected_name
    assert expected_name in labels
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
    assert PRODUCT_DISPLAY_NAME in labels
    assert PRODUCT_LICENSE in labels
    assert PRODUCT_NUMBER in labels
    assert "ACTIVATED" in labels
    assert w.findChild(QLabel, "myCompanyHeaderName").text() == expected_name
    assert w.findChild(QLabel, "myCompanyEin").text() == ""
    assert w.findChild(QLabel, "myCompanySsn").text() == SSN_PLACEHOLDER
    assert w.findChild(QToolButton, "myCompanyEditButton") is not None
    blob = " ".join(labels)
    assert "MANAGE YOUR APPS, SERVICES & SUBSCRIPTIONS" not in blob
    assert "APPS, SERVICES & SUBSCRIPTIONS RECOMMENDED FOR YOU" not in blob
    assert "Get E-commerce Integration" not in blob
    assert "Turn On Payroll" not in blob
    assert "Accept Credit Cards" not in blob
    assert "Advanced Inventory" not in blob
    assert w.findChild(QPushButton, "myCompanySignIn") is None
    assert w.findChild(QToolButton, "myCompanyCarouselNext") is None
    w.close()


def test_my_company_loads_identity_keys(qapp: QApplication, db: BankDatabase) -> None:
    save_company_identity(
        db._conn,
        name="Harbor Co",
        address="1 Example Way\nAustin, TX 00000",
        phone="555-0142",
        email="office@harbor.example",
        tax_id="12-3456789",
    )
    data = load_my_company_fields(db._conn)
    assert data["name"] == "Harbor Co"
    assert "1 Example Way" in data["contact_address"]
    assert data["phone"] == "555-0142"
    assert data["email"] == "office@harbor.example"
    assert data["ein"] == "12-3456789"
    w = MyCompanyScreen(ap_conn=db._conn)
    qapp.processEvents()
    assert w.findChild(QLabel, "myCompanyHeaderName").text() == "Harbor Co"
    assert w.findChild(QLabel, "myCompanyPhone").text() == "555-0142"
    assert w.findChild(QLabel, "myCompanyEmail").text() == "office@harbor.example"
    assert w.findChild(QLabel, "myCompanyEin").text() == "12-3456789"
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
    ident = get_company_identity(db._conn)
    assert ident["name"] == "Acme Haul LLC"
    assert ident["phone"] == "555-0100"
    assert ident["email"] == "billing@acme.example"
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
        assert company_file_display_name(w._bank_db._conn) in titles
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
    assert "get e-commerce integration" not in lowered
    assert "turn on payroll" not in lowered
    assert "accept credit cards" not in lowered
    assert "advanced inventory" not in lowered
    assert "manage your apps, services" not in lowered


def test_capture_script_has_my_company_tab() -> None:
    text = Path("scripts/capture_ui_screenshot.py").read_text(encoding="utf-8")
    assert "--tab my-company" in text
    yml = Path(".github/workflows/ui-screenshot.yml").read_text(encoding="utf-8")
    assert "--tab my-company" in yml
