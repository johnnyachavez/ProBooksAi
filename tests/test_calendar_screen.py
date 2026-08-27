"""Calendar screen — QB Pro chrome, live counts, navigation hooks."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QLabel,
    QListWidget,
    QPushButton,
    QTableWidget,
    QToolButton,
)

from desktop_app.calendar_screen import CalendarScreen
from desktop_app.enter_bills_screen import EnterBillsScreen
from desktop_app.invoice_screen import InvoiceScreen
from desktop_app.pay_bills_screen import PayBillsScreen
from probooksai import business
from probooksai import qb_calendar as cal
from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import apply_extensions

_TODAY = date(2026, 8, 27)
_FORBIDDEN = (
    "AR TRUCKING",
    "ORDAZ FREIGHT",
    "RAYA'S TRUCKING",
    "ROBERTO REOS",
    "-1,000.00",
)


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def db(tmp_path: Path) -> BankDatabase:
    b = BankDatabase(db_path=str(tmp_path / "calendar_ui.db"))
    apply_extensions(b._conn)
    yield b
    b.close()


def _seed(conn) -> dict[str, int]:
    cid = business.add_customer(conn, "Harbor Logistics")
    inv = business.create_invoice(
        conn,
        cid,
        "INV-2101",
        "2026-08-10",
        due_date="2026-08-10",
        lines=[{"description": "Haul", "qty": 1, "rate": 400.00}],
    )
    overdue_inv = business.create_invoice(
        conn,
        cid,
        "INV-0400",
        "2026-06-01",
        due_date="2026-07-15",
        lines=[{"description": "Haul", "qty": 1, "rate": 90.00}],
    )
    vid = business.add_vendor(conn, "Office Supplies Co")
    vid2 = business.add_vendor(conn, "Warehouse Supply")
    bill = business.create_bill(
        conn, vid, "2026-08-10", 450.00, vendor_invoice_number="OS-1042", due_date="2026-08-30"
    )
    overdue_bill = business.create_bill(
        conn, vid2, "2026-06-20", 96.40, vendor_invoice_number="WS-12", due_date="2026-07-20"
    )
    return {
        "inv": inv,
        "overdue_inv": overdue_inv,
        "bill": bill,
        "overdue_bill": overdue_bill,
    }


def test_calendar_chrome_and_live_counts(qapp: QApplication, db: BankDatabase) -> None:
    _seed(db._conn)
    w = CalendarScreen(ap_conn=db._conn, today=_TODAY)
    labels = [lb.text() for lb in w.findChildren(QLabel)]
    assert "Calendar" in labels
    assert "Select a date" in labels
    assert "SHOW" in labels
    assert any("Upcoming: Next 7 days" in t for t in labels)
    assert any("Due: Past 60 days" in t for t in labels)
    assert any(t.startswith("TO DO") for t in labels)
    assert any(t.startswith("TRANSACTIONS") for t in labels)
    assert any(t.startswith("BILLS") for t in labels)
    assert w.findChild(QLabel, "calendarMonthLabel").text() == "August 2026"
    assert w.findChild(QComboBox, "calendarShowFilter").currentText() == cal.SHOW_ALL
    assert w.findChild(QToolButton, "calendarMonthView").isChecked()
    assert not w.findChild(QToolButton, "calendarListView").isChecked()
    assert w.findChild(QPushButton, "calendarAddToDo") is not None
    empty = w.findChild(QLabel, "calendarDetailEmpty")
    assert empty is not None
    assert empty.text() == "There are no To Do's or Transactions on this date."

    due_labels = [
        lb.text()
        for lb in w.findChildren(QLabel)
        if lb.objectName() == "calendarDayDue" and lb.text()
    ]
    entered_labels = [
        lb.text()
        for lb in w.findChildren(QLabel)
        if lb.objectName() == "calendarDayEntered" and lb.text()
    ]
    assert any(t.startswith("Due (") for t in due_labels)
    assert any(t.startswith("Entered (") for t in entered_labels)
    past_hdr = w.findChild(QLabel, "calendarPastDueHeaderLabel")
    assert past_hdr is not None
    assert "Past 60 days" in past_hdr.text()
    assert "(0)" not in past_hdr.text()
    w.close()


def test_calendar_select_day_empty_and_populated(qapp: QApplication, db: BankDatabase) -> None:
    _seed(db._conn)
    w = CalendarScreen(ap_conn=db._conn, today=_TODAY)
    w._on_select_day(date(2026, 8, 27))
    qapp.processEvents()
    empty = w.findChild(QLabel, "calendarDetailEmpty")
    assert not empty.isHidden()
    assert empty.text() == "There are no To Do's or Transactions on this date."
    w._on_select_day(date(2026, 8, 10))
    qapp.processEvents()
    assert w.findChild(QLabel, "calendarDetailDate").text() == "August 10, 2026"
    assert empty.isHidden()
    lst = w.findChild(QListWidget, "calendarDetailList")
    assert lst is not None
    assert not lst.isHidden()
    assert lst.count() >= 2
    w.close()


def test_calendar_sidebar_opens_invoice_and_overdue_bill(
    qapp: QApplication, db: BankDatabase
) -> None:
    ids = _seed(db._conn)
    w = CalendarScreen(ap_conn=db._conn, today=_TODAY)
    opened_inv: list[int] = []
    opened_bill: list[int] = []
    paid_bill: list[int] = []
    w.openInvoiceRequested.connect(opened_inv.append)
    w.openBillRequested.connect(opened_bill.append)
    w.payBillRequested.connect(paid_bill.append)

    due = cal.list_due_for_date(db._conn, date(2026, 8, 10))
    inv_event = next(e for e in due if e["kind"] == cal.KIND_INVOICE)
    w._open_event(inv_event, from_past_bills=False)
    assert opened_inv == [ids["inv"]]

    past = cal.due_past_60(db._conn, today=_TODAY)
    bill_event = next(e for e in past["bills"] if e["record_id"] == ids["overdue_bill"])
    w._open_event(bill_event, from_past_bills=True)
    assert paid_bill == [ids["overdue_bill"]]

    upcoming = cal.upcoming_next_7(db._conn, today=_TODAY)
    open_bill = next(e for e in upcoming["bills"] if e["record_id"] == ids["bill"])
    w._open_event(open_bill, from_past_bills=False)
    assert opened_bill == [ids["bill"]]
    w.close()


def test_calendar_list_toggle_and_add_todo(qapp: QApplication, db: BankDatabase) -> None:
    _seed(db._conn)
    w = CalendarScreen(ap_conn=db._conn, today=_TODAY)
    w._set_view("list")
    qapp.processEvents()
    assert w.findChild(QToolButton, "calendarListView").isChecked()
    tbl = w.findChild(QTableWidget, "calendarListTable")
    assert tbl is not None
    assert tbl.columnCount() == 6
    assert tbl.rowCount() >= 2
    w.add_todo_for_tests("Follow up", "2026-08-27")
    qapp.processEvents()
    w._on_select_day(date(2026, 8, 27))
    qapp.processEvents()
    lst = w.findChild(QListWidget, "calendarDetailList")
    assert lst.count() >= 1
    texts = [lst.item(i).text() for i in range(lst.count())]
    assert any("Follow up" in t for t in texts)
    w.close()


def test_calendar_main_window_tab_and_home_shortcut(
    qapp: QApplication, tmp_path: Path
) -> None:
    from desktop_app.main import MainWindow

    db_path = tmp_path / "calendar_nav.db"
    BankDatabase(str(db_path)).close()
    w = MainWindow(db_path=str(db_path))
    try:
        tabs = w._tabs
        assert "Calendar" in tabs.tabText(3)
        assert isinstance(tabs.widget(3), CalendarScreen)
        tabs.setCurrentIndex(0)
        qapp.processEvents()
        btn = w._dashboard_tab.findChild(QToolButton, "homeShortcut_calendar")
        assert btn is not None
        btn.click()
        qapp.processEvents()
        assert tabs.currentWidget() is w._calendar_screen
        assert isinstance(tabs.currentWidget(), CalendarScreen)
        titles = [lb.text() for lb in tabs.currentWidget().findChildren(QLabel)]
        assert "Calendar" in titles
        assert isinstance(w._invoice_screen, InvoiceScreen)
        assert isinstance(w._enter_bills_screen, EnterBillsScreen)
        assert isinstance(w._pay_bills_screen, PayBillsScreen)
    finally:
        w.close()


def test_calendar_ui_has_no_live_company_identity() -> None:
    text = Path("desktop_app/calendar_screen.py").read_text(encoding="utf-8")
    lowered = text.lower()
    for needle in _FORBIDDEN:
        assert needle.lower() not in lowered
    assert "COMPANY NAME" not in text
