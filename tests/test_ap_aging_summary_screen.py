"""A/P Aging Summary screen — QB Pro chrome, live bills, COMPANY NAME header."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest
from PySide6.QtCore import QDate
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QLabel,
    QPushButton,
    QSpinBox,
    QToolButton,
    QTreeWidget,
)

from desktop_app.ap_aging_summary_screen import (
    PLACEHOLDER_COMPANY_NAME,
    APAgingSummaryScreen,
)
from desktop_app.theme import BG_PRIMARY
from probooksai import business
from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import apply_extensions

_FORBIDDEN = (
    "ANVIL STEEL",
    "FLATIRON",
    "BST LINEHAUL",
    "CHAVAN TRUCKING",
    "126,845",
    "335,036.07",
    "12588",
)


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def db(tmp_path: Path) -> BankDatabase:
    b = BankDatabase(db_path=str(tmp_path / "ap_aging_ui.db"))
    apply_extensions(b._conn)
    yield b
    b.close()


def _labels(w: APAgingSummaryScreen) -> list[str]:
    return [lb.text() for lb in w.findChildren(QLabel)]


def _set_as_of(w: APAgingSummaryScreen, d: date) -> None:
    w._dates.blockSignals(True)
    w._dates.setCurrentText("Custom Date")
    w._dates.blockSignals(False)
    w._as_of_edit.blockSignals(True)
    w._as_of_edit.setDate(QDate(d.year, d.month, d.day))
    w._as_of_edit.blockSignals(False)
    w.reload()


def test_ap_aging_chrome(qapp: QApplication, db: BankDatabase) -> None:
    w = APAgingSummaryScreen(ap_conn=db._conn)
    labels = _labels(w)
    assert PLACEHOLDER_COMPANY_NAME in labels
    assert "A/P Aging Summary" in labels
    assert any(t.startswith("As of ") for t in labels)
    assert "CHAVAN TRUCKING CORP" not in labels

    btns = [b.text() for b in w.findChildren(QPushButton)]
    for needle in (
        "Customize Report",
        "Comment on Report",
        "Share Template",
        "Memorize",
        "Hide Header",
        "Refresh",
        "Show Filters",
    ):
        assert needle in btns

    tools = [b.text() for b in w.findChildren(QToolButton)]
    assert "Print" in tools
    assert "E-mail" in tools
    assert "Excel" in tools

    dates = w.findChild(QComboBox, "apAgingDates")
    assert dates is not None and dates.currentText() == "Today"
    assert w.findChild(QDateEdit, "apAgingDate") is not None
    assert w.findChild(QSpinBox, "apAgingInterval").value() == 30
    assert w.findChild(QSpinBox, "apAgingThrough").value() == 90
    sort = w.findChild(QComboBox, "apAgingSort")
    assert sort is not None and sort.currentText() == "Default"

    tree = w.findChild(QTreeWidget, "apAgingTree")
    assert tree is not None
    headers = [tree.headerItem().text(i) for i in range(tree.columnCount())]
    assert headers == [
        "Vendor",
        "Current",
        "1 - 30",
        "31 - 60",
        "61 - 90",
        "> 90",
        "TOTAL",
    ]
    assert tree.topLevelItemCount() == 1
    total = tree.topLevelItem(0)
    assert total.text(0) == "TOTAL"
    assert total.text(tree.columnCount() - 1) == "0.00"

    pal = w.palette()
    assert pal.color(QPalette.ColorRole.Window).name().lower() != BG_PRIMARY.lower()


def test_ap_aging_empty_has_no_fake_vendors(qapp: QApplication, db: BankDatabase) -> None:
    w = APAgingSummaryScreen(ap_conn=db._conn)
    tree = w._tree
    names = []
    for i in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(i)
        names.append(item.text(0))
        for j in range(item.childCount()):
            names.append(item.child(j).text(0))
    assert names == ["TOTAL"]
    blob = " ".join(_labels(w) + names)
    for forbidden in _FORBIDDEN:
        assert forbidden not in blob


def test_ap_aging_live_bills_and_buckets(qapp: QApplication, db: BankDatabase) -> None:
    supply = business.add_vendor(db._conn, "Harbor Supply Co")
    business.create_bill(
        db._conn,
        supply,
        "2026-08-01",
        100.0,
        vendor_invoice_number="HSC-9",
        due_date="2026-08-20",
    )
    business.create_bill(
        db._conn,
        supply,
        "2026-07-01",
        50.0,
        vendor_invoice_number="HSC-10",
        due_date="2026-07-10",
    )
    fuel = business.add_vendor(db._conn, "Westside Fuel")
    business.create_bill(
        db._conn,
        fuel,
        "2026-01-01",
        25.0,
        vendor_invoice_number="WF-1",
        due_date="2026-01-15",
    )
    w = APAgingSummaryScreen(ap_conn=db._conn)
    _set_as_of(w, date(2026, 8, 27))
    tree = w._tree
    top = [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]
    assert "Harbor Supply Co" in top
    assert "Westside Fuel" in top
    assert "TOTAL" in top
    grand = tree.topLevelItem(tree.topLevelItemCount() - 1)
    assert grand.text(0) == "TOTAL"
    assert grand.text(tree.columnCount() - 1) == "175.00"
    for forbidden in _FORBIDDEN:
        assert forbidden not in " ".join(top)


def test_ap_aging_hide_header(qapp: QApplication, db: BankDatabase) -> None:
    vid = business.add_vendor(db._conn, "Harbor Supply Co")
    business.create_bill(
        db._conn,
        vid,
        "2026-08-01",
        10.0,
        vendor_invoice_number="X-1",
        due_date="2026-09-01",
    )
    w = APAgingSummaryScreen(ap_conn=db._conn)
    _set_as_of(w, date(2026, 8, 27))
    assert not w._header_wrap.isHidden()
    w._on_toggle_header()
    assert w._header_wrap.isHidden()
    assert w._btn_hide_header.text() == "Show Header"


def test_ap_aging_double_click_emits_vendor(qapp: QApplication, db: BankDatabase) -> None:
    vid = business.add_vendor(db._conn, "Metro Fleet Parts")
    business.create_bill(
        db._conn,
        vid,
        "2026-08-01",
        12.0,
        vendor_invoice_number="MF-1",
        due_date="2026-08-15",
    )
    w = APAgingSummaryScreen(ap_conn=db._conn)
    _set_as_of(w, date(2026, 8, 27))
    seen: list[int] = []
    w.openVendorRequested.connect(seen.append)
    item = next(
        w._tree.topLevelItem(i)
        for i in range(w._tree.topLevelItemCount())
        if w._tree.topLevelItem(i).text(0) == "Metro Fleet Parts"
    )
    w._on_row_double_clicked(item, 0)
    assert seen == [vid]


def test_ap_aging_source_has_no_real_qb_names() -> None:
    for path in (
        Path("desktop_app/ap_aging_summary_screen.py"),
        Path("probooksai/qb_ap_aging.py"),
    ):
        text = path.read_text(encoding="utf-8")
        for name in _FORBIDDEN:
            assert name not in text, f"{name!r} must not appear in {path}"
        assert "COMPANY NAME" in text or path.name == "qb_ap_aging.py"
        assert "CHAVAN TRUCKING CORP" not in text
