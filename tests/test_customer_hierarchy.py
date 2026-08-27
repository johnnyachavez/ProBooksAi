"""Customer / job parent hierarchy (mother ship + jobs)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QComboBox, QTableWidget

from desktop_app.qt_combo_ids import coerce_combo_int_id
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
    b = BankDatabase(db_path=str(tmp_path / "cust_hier.db"))
    apply_extensions(b._conn)
    yield b
    b.close()


def test_list_bill_to_customer_choices_labels(db: BankDatabase) -> None:
    parent = business.add_customer(db._conn, "Mother Ship")
    job = business.add_customer(db._conn, "Site A", parent_customer_id=parent)
    solo = business.add_customer(db._conn, "Solo Co")
    choices = business.list_bill_to_customer_choices(db._conn)
    by_id = dict(choices)
    assert by_id[parent] == "Mother Ship"
    assert by_id[job] == "Mother Ship > Site A"
    assert by_id[solo] == "Solo Co"


def test_parent_customer_and_job_row(db: BankDatabase) -> None:
    parent = business.add_customer(db._conn, "Mother Ship LLC")
    job = business.add_customer(
        db._conn, "Job Alpha", parent_customer_id=parent
    )
    row = business.get_customer(db._conn, job)
    assert int(row["parent_customer_id"]) == parent
    assert business.customer_relationship_label(db._conn, parent) == "Parent"
    assert business.customer_relationship_label(db._conn, job) == "Job: Mother Ship LLC"


def test_cannot_assign_parent_if_customer_has_jobs(db: BankDatabase) -> None:
    p1 = business.add_customer(db._conn, "P1")
    p2 = business.add_customer(db._conn, "P2")
    j = business.add_customer(db._conn, "J1", parent_customer_id=p1)
    with pytest.raises(ValueError, match="job accounts"):
        business.update_customer(
            db._conn, p1, "P1b", parent_customer_id=p2
        )
    # clear job first, then P1 can become a job under P2
    business.update_customer(db._conn, j, "J1b", parent_customer_id=None)
    business.update_customer(db._conn, p1, "P1b", parent_customer_id=p2)
    r = business.get_customer(db._conn, p1)
    assert int(r["parent_customer_id"]) == p2


def test_receive_payments_parent_filter_shows_child_invoices(
    qapp: QApplication, db: BankDatabase
) -> None:
    parent = business.add_customer(db._conn, "Rollup Co")
    job = business.add_customer(db._conn, "Job Site A", parent_customer_id=parent)
    business.create_invoice(
        db._conn,
        job,
        "INV-J1",
        "2024-06-01",
        lines=[{"description": "Work", "qty": 1, "rate": 100.0}],
    )
    w = ReceiveChecksScreen(ap_conn=db._conn, bank_db=db)
    cb = w.findChild(QComboBox, "receivePaymentsReceivedFrom")
    assert cb is not None
    idx = next(
        (
            i
            for i in range(cb.count())
            if coerce_combo_int_id(cb.itemData(i)) == parent
        ),
        -1,
    )
    assert idx >= 0
    cb.setCurrentIndex(idx)
    t = w.findChild(QTableWidget, "receiveChecksTable")
    assert t is not None
    assert t.rowCount() == 1
    assert "INV-J1" in (t.item(0, 2).text() or "")


def test_list_open_invoices_for_ar_payment_customer_parent_includes_jobs(
    db: BankDatabase,
) -> None:
    p = business.add_customer(db._conn, "P")
    j = business.add_customer(db._conn, "J", parent_customer_id=p)
    business.create_invoice(
        db._conn,
        j,
        "INV-F",
        "2024-03-01",
        lines=[{"description": "x", "qty": 1, "rate": 10.0}],
    )
    rows = business.list_open_invoices_for_ar_payment_customer(db._conn, p)
    assert len(rows) == 1
    assert (rows[0]["invoice_number"] or "") == "INV-F"


def test_customer_ids_for_receive_payments_filter_job_is_single(db: BankDatabase) -> None:
    p = business.add_customer(db._conn, "P")
    j = business.add_customer(db._conn, "J", parent_customer_id=p)
    ids_p = business.customer_ids_for_receive_payments_filter(db._conn, p)
    assert ids_p == [p, j]
    ids_j = business.customer_ids_for_receive_payments_filter(db._conn, j)
    assert ids_j == [j]
