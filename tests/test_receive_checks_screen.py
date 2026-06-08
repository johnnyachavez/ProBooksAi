"""Receive Payments screen — structure and A/R data wiring."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication, QCheckBox, QDoubleSpinBox, QPushButton, QTableWidget

from desktop_app.receive_checks_screen import ReceiveChecksScreen
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
    b = BankDatabase(db_path=str(tmp_path / "rcv.db"))
    apply_extensions(b._conn)
    yield b
    b.close()


def test_receive_checks_screen_table_headers(qapp: QApplication) -> None:
    w = ReceiveChecksScreen()
    t = w.findChild(QTableWidget, "receiveChecksTable")
    assert t is not None
    assert t.columnCount() == 7
    assert t.horizontalHeaderItem(1).text() == "Customer"
    assert t.horizontalHeaderItem(2).text() == "Invoice Date"
    assert t.horizontalHeaderItem(3).text() == "Due Date"
    assert t.horizontalHeaderItem(4).text() == "Invoice #"
    assert t.horizontalHeaderItem(5).text() == "Open Balance"
    assert t.horizontalHeaderItem(6).text() == "Amount to Apply"


def test_receive_checks_parent_vs_job_customer_filter(
    qapp: QApplication, db: BankDatabase
) -> None:
    """Mother ship lists all job open invoices; selecting a job lists only that job."""
    p = business.add_customer(db._conn, "ParentCo")
    j = business.add_customer(db._conn, "JobA", parent_customer_id=p)
    business.create_invoice(
        db._conn,
        p,
        "INV-P",
        "2024-05-01",
        lines=[{"description": "a", "qty": 1, "rate": 30.0}],
    )
    business.create_invoice(
        db._conn,
        j,
        "INV-J",
        "2024-05-02",
        lines=[{"description": "b", "qty": 1, "rate": 20.0}],
    )
    w = ReceiveChecksScreen(ap_conn=db._conn, bank_db=db)
    t = w.findChild(QTableWidget, "receiveChecksTable")
    assert t is not None
    assert t.rowCount() == 2
    combo = w._customer_filter
    idx_p = next(
        i
        for i in range(combo.count())
        if combo.itemData(i) is not None and int(combo.itemData(i)) == p
    )
    idx_j = next(
        i
        for i in range(combo.count())
        if combo.itemData(i) is not None and int(combo.itemData(i)) == j
    )
    combo.setCurrentIndex(idx_j)
    w._rebuild_table()
    assert t.rowCount() == 1
    assert "INV-J" in (t.item(0, 4).text() or "")
    combo.setCurrentIndex(idx_p)
    w._rebuild_table()
    assert t.rowCount() == 2
    nums = sorted((t.item(i, 4).text() or "") for i in range(t.rowCount()))
    assert "INV-J" in nums and "INV-P" in nums


def test_receive_checks_loads_open_invoice_row(
    qapp: QApplication, db: BankDatabase
) -> None:
    cid = business.add_customer(db._conn, "PayCo")
    business.create_invoice(
        db._conn,
        cid,
        "INV-R1",
        "2024-06-01",
        due_date="2024-06-15",
        lines=[{"description": "Work", "qty": 1, "rate": 100.0}],
    )
    w = ReceiveChecksScreen(ap_conn=db._conn, bank_db=db)
    t = w.findChild(QTableWidget, "receiveChecksTable")
    assert t is not None
    assert t.rowCount() == 1
    assert t.item(0, 1).text() == "PayCo"
    assert "INV-R1" in (t.item(0, 4).text() or "")
    spin = t.cellWidget(0, 6)
    assert isinstance(spin, QDoubleSpinBox)
    assert spin.maximum() == pytest.approx(100.0)


def test_receive_checks_shows_hierarchical_customer_label_for_job(
    qapp: QApplication, db: BankDatabase
) -> None:
    p = business.add_customer(db._conn, "ShipCo")
    j = business.add_customer(db._conn, "Berth1", parent_customer_id=p)
    business.create_invoice(
        db._conn,
        j,
        "INV-H",
        "2024-09-01",
        lines=[{"description": "x", "qty": 1, "rate": 15.0}],
    )
    w = ReceiveChecksScreen(ap_conn=db._conn, bank_db=db)
    t = w.findChild(QTableWidget, "receiveChecksTable")
    assert t is not None
    assert t.rowCount() == 1
    assert t.item(0, 1).text() == "ShipCo > Berth1"
    assert "INV-H" in (t.item(0, 4).text() or "")
    spin = t.cellWidget(0, 6)
    assert isinstance(spin, QDoubleSpinBox)
    assert spin.maximum() == pytest.approx(15.0)


def test_receive_checks_totals_update_when_checked(
    qapp: QApplication, db: BankDatabase
) -> None:
    cid = business.add_customer(db._conn, "PayCo2")
    business.create_invoice(
        db._conn,
        cid,
        "INV-R2",
        "2024-06-01",
        lines=[{"description": "Work", "qty": 1, "rate": 50.0}],
    )
    w = ReceiveChecksScreen(ap_conn=db._conn, bank_db=db)
    t = w.findChild(QTableWidget, "receiveChecksTable")
    assert t is not None
    cb = t.cellWidget(0, 0)
    spin = t.cellWidget(0, 6)
    assert isinstance(cb, QCheckBox)
    assert isinstance(spin, QDoubleSpinBox)
    cb.setChecked(True)
    spin.setValue(25.0)
    assert "1" in w._lbl_total_selected.text()
    assert "25" in w._lbl_total_payment.text().replace(",", "")


def test_receive_checks_apply_credits_button_present(qapp: QApplication) -> None:
    w = ReceiveChecksScreen()
    texts = [b.text() for b in w.findChildren(QPushButton)]
    assert "Apply Credits" in texts


def test_list_open_invoices_for_receive_payments(db: BankDatabase) -> None:
    cid = business.add_customer(db._conn, "ListCo")
    business.create_invoice(
        db._conn,
        cid,
        "INV-L",
        "2024-07-01",
        lines=[{"description": "x", "qty": 1, "rate": 10.0}],
    )
    rows = business.list_open_invoices_for_receive_payments(db._conn)
    assert len(rows) == 1
    assert rows[0]["customer_name"] == "ListCo"
    assert int(rows[0]["invoice_id"]) >= 1


def test_receive_payment_post_reduces_balance(qapp: QApplication, db: BankDatabase) -> None:
    aid = db.add_bank_account("Checking")
    cid = business.add_customer(db._conn, "PostCo")
    inv_id = business.create_invoice(
        db._conn,
        cid,
        "INV-P",
        "2024-08-01",
        lines=[{"description": "Work", "qty": 1, "rate": 40.0}],
    )
    w = ReceiveChecksScreen(ap_conn=db._conn, bank_db=db)
    t = w.findChild(QTableWidget, "receiveChecksTable")
    assert t is not None
    assert t.rowCount() == 1
    cb = t.cellWidget(0, 0)
    spin = t.cellWidget(0, 6)
    assert isinstance(cb, QCheckBox)
    assert isinstance(spin, QDoubleSpinBox)
    cb.setChecked(True)
    spin.setValue(40.0)
    assert w._deposit_to.count() >= 2
    w._deposit_to.setCurrentIndex(1)
    with patch("desktop_app.receive_checks_screen.message_box_information_ok"):
        w._on_post_payment()
    row = db._conn.execute(
        "SELECT balance_due, status FROM invoices WHERE id = ?", (inv_id,)
    ).fetchone()
    assert float(row["balance_due"]) == pytest.approx(0.0)
    pid = int(
        db._conn.execute("SELECT id FROM ar_payments ORDER BY id DESC LIMIT 1").fetchone()["id"]
    )
    tid = int(
        db._conn.execute(
            "SELECT id FROM bank_transactions WHERE bank_account_id = ? ORDER BY id DESC LIMIT 1",
            (aid,),
        ).fetchone()["id"]
    )
    bt = db._conn.execute(
        "SELECT amount FROM bank_transactions WHERE id = ?", (tid,)
    ).fetchone()
    assert float(bt["amount"]) == pytest.approx(40.0)
    assert business.bank_match_link_for_navigation(db._conn, tid) == ("ar_payment", pid)
    assert w._btn_export_ar_pdf.isEnabled()
    assert w._btn_print_ar.isEnabled()
    assert w._last_ar_payment_ids[-1] == pid


def test_receive_payment_post_emits_ar_payment_posted_with_invoice_ids(
    qapp: QApplication, db: BankDatabase
) -> None:
    """``arPaymentPosted`` carries the invoice ids that just received an allocation.

    Other screens (Manual Invoice) wire to this signal to refresh the PAID badge /
    balance for an invoice they currently have open without polling.
    """
    db.add_bank_account("Checking")
    cid = business.add_customer(db._conn, "EmitCo")
    inv_id = business.create_invoice(
        db._conn,
        cid,
        "INV-EMIT",
        "2024-08-01",
        lines=[{"description": "Work", "qty": 1, "rate": 25.0}],
    )
    w = ReceiveChecksScreen(ap_conn=db._conn, bank_db=db)
    received: list[list[int]] = []
    w.arPaymentPosted.connect(lambda ids: received.append(list(ids)))
    t = w.findChild(QTableWidget, "receiveChecksTable")
    assert t is not None
    cb = t.cellWidget(0, 0)
    spin = t.cellWidget(0, 6)
    assert isinstance(cb, QCheckBox)
    assert isinstance(spin, QDoubleSpinBox)
    cb.setChecked(True)
    spin.setValue(25.0)
    w._deposit_to.setCurrentIndex(1)
    with patch("desktop_app.receive_checks_screen.message_box_information_ok"):
        w._on_post_payment()
    assert received, "arPaymentPosted should fire after a successful post"
    assert inv_id in received[-1]
