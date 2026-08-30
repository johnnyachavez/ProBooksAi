"""A/R Aging Summary screen — QB Pro chrome, live invoices, COMPANY NAME header."""

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

from desktop_app.ar_aging_summary_screen import (
    PLACEHOLDER_COMPANY_NAME,
    ARAgingSummaryScreen,
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
    b = BankDatabase(db_path=str(tmp_path / "ar_aging_ui.db"))
    apply_extensions(b._conn)
    yield b
    b.close()


def _labels(w: ARAgingSummaryScreen) -> list[str]:
    return [lb.text() for lb in w.findChildren(QLabel)]


def _set_as_of(w: ARAgingSummaryScreen, d: date) -> None:
    w._dates.blockSignals(True)
    w._dates.setCurrentText("Custom Date")
    w._dates.blockSignals(False)
    w._as_of_edit.blockSignals(True)
    w._as_of_edit.setDate(QDate(d.year, d.month, d.day))
    w._as_of_edit.blockSignals(False)
    w.reload()


def test_ar_aging_chrome(qapp: QApplication, db: BankDatabase) -> None:
    w = ARAgingSummaryScreen(ap_conn=db._conn)
    labels = _labels(w)
    assert PLACEHOLDER_COMPANY_NAME in labels
    assert "A/R Aging Summary" in labels
    assert any(t.startswith("As of ") for t in labels)
    assert "CHAVAN TRUCKING CORP" not in labels

    btns = [b.text() for b in w.findChildren(QPushButton)]
    for needle in (
        "Customize Report",
        "Comment on Report",
        "Share Template",
        "Memorize",
        "Hide Header",
        "Collapse Rows",
        "Refresh",
        "Show Filters",
    ):
        assert needle in btns

    tools = [b.text() for b in w.findChildren(QToolButton)]
    assert "Print" in tools
    assert "E-mail" in tools
    assert "Excel" in tools

    dates = w.findChild(QComboBox, "arAgingDates")
    assert dates is not None and dates.currentText() == "Today"
    assert w.findChild(QDateEdit, "arAgingDate") is not None
    assert w.findChild(QSpinBox, "arAgingInterval").value() == 30
    assert w.findChild(QSpinBox, "arAgingThrough").value() == 90
    sort = w.findChild(QComboBox, "arAgingSort")
    assert sort is not None and sort.currentText() == "Default"

    tree = w.findChild(QTreeWidget, "arAgingTree")
    assert tree is not None
    headers = [tree.headerItem().text(i) for i in range(tree.columnCount())]
    assert headers == [
        "Customer",
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


def test_ar_aging_empty_has_no_fake_customers(qapp: QApplication, db: BankDatabase) -> None:
    w = ARAgingSummaryScreen(ap_conn=db._conn)
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


def test_ar_aging_live_jobs_and_buckets(qapp: QApplication, db: BankDatabase) -> None:
    parent = business.add_customer(db._conn, "Harbor Logistics")
    job = business.add_customer(db._conn, "Site A", parent_customer_id=parent)
    business.create_invoice(
        db._conn,
        parent,
        "HL-1",
        "2026-08-01",
        due_date="2026-08-20",
        lines=[{"description": "Haul", "qty": 1, "rate": 100.0}],
    )
    business.create_invoice(
        db._conn,
        job,
        "JOB-12",
        "2026-07-01",
        due_date="2026-07-10",
        lines=[{"description": "Site", "qty": 1, "rate": 50.0}],
    )
    solo = business.add_customer(db._conn, "Westside Hauling")
    business.create_invoice(
        db._conn,
        solo,
        "WH-1",
        "2026-01-01",
        due_date="2026-01-15",
        lines=[{"description": "Haul", "qty": 1, "rate": 25.0}],
    )
    w = ARAgingSummaryScreen(ap_conn=db._conn)
    _set_as_of(w, date(2026, 8, 27))
    tree = w._tree
    top = [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]
    assert "Harbor Logistics" in top
    assert "Westside Hauling" in top
    assert "TOTAL" in top
    harbor = next(
        tree.topLevelItem(i)
        for i in range(tree.topLevelItemCount())
        if tree.topLevelItem(i).text(0) == "Harbor Logistics"
    )
    kids = [harbor.child(i).text(0) for i in range(harbor.childCount())]
    assert "Site A" in kids
    assert "Harbor Logistics - Other" in kids
    assert "Total Harbor Logistics" in kids
    assert harbor.isExpanded()
    grand = tree.topLevelItem(tree.topLevelItemCount() - 1)
    assert grand.text(0) == "TOTAL"
    assert grand.text(tree.columnCount() - 1) == "175.00"
    for forbidden in _FORBIDDEN:
        assert forbidden not in " ".join(top + kids)


def test_ar_aging_hide_header_and_collapse(qapp: QApplication, db: BankDatabase) -> None:
    parent = business.add_customer(db._conn, "Harbor Logistics")
    job = business.add_customer(db._conn, "Site A", parent_customer_id=parent)
    business.create_invoice(
        db._conn,
        job,
        "JOB-1",
        "2026-08-01",
        due_date="2026-09-01",
        lines=[{"description": "x", "qty": 1, "rate": 10.0}],
    )
    w = ARAgingSummaryScreen(ap_conn=db._conn)
    _set_as_of(w, date(2026, 8, 27))
    assert not w._header_wrap.isHidden()
    w._on_toggle_header()
    assert w._header_wrap.isHidden()
    assert w._btn_hide_header.text() == "Show Header"
    harbor = next(
        w._tree.topLevelItem(i)
        for i in range(w._tree.topLevelItemCount())
        if w._tree.topLevelItem(i).text(0) == "Harbor Logistics"
    )
    assert harbor.isExpanded()
    w._on_collapse_rows()
    assert not harbor.isExpanded()
    assert w._btn_collapse.text() == "Expand Rows"


def test_ar_aging_double_click_emits_customer(
    qapp: QApplication, db: BankDatabase
) -> None:
    cid = business.add_customer(db._conn, "Metro Freight")
    business.create_invoice(
        db._conn,
        cid,
        "MF-1",
        "2026-08-01",
        due_date="2026-08-15",
        lines=[{"description": "x", "qty": 1, "rate": 12.0}],
    )
    w = ARAgingSummaryScreen(ap_conn=db._conn)
    _set_as_of(w, date(2026, 8, 27))
    seen: list[int] = []
    w.openCustomerRequested.connect(seen.append)
    item = next(
        w._tree.topLevelItem(i)
        for i in range(w._tree.topLevelItemCount())
        if w._tree.topLevelItem(i).text(0) == "Metro Freight"
    )
    w._on_row_double_clicked(item, 0)
    assert seen == [cid]


def test_ar_aging_source_has_no_real_qb_names() -> None:
    for path in (
        Path("desktop_app/ar_aging_summary_screen.py"),
        Path("probooksai/qb_ar_aging.py"),
    ):
        text = path.read_text(encoding="utf-8")
        for name in _FORBIDDEN:
            assert name not in text, f"{name!r} must not appear in {path}"
        assert "COMPANY NAME" in text or path.name == "qb_ar_aging.py"
        assert "CHAVAN TRUCKING CORP" not in text
