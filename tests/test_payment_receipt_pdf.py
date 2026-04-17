"""AR / AP payment receipt PDF helpers."""

from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QApplication

from desktop_app.payment_receipt_pdf import (
    ap_payment_html_string,
    ar_payment_html_string,
    save_ap_payment_pdf,
    save_ar_payment_pdf,
)
from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import apply_extensions
from probooksai import business


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_ar_payment_html_string(qapp: QApplication, tmp_path) -> None:
    db_path = tmp_path / "ar_pay.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    aid = db.add_bank_account("Checking")
    cid = business.add_customer(db._conn, "CustA")
    inv = business.create_invoice(
        db._conn,
        cid,
        "I-1",
        "2025-03-01",
        lines=[{"description": "w", "qty": 1, "rate": 50.0}],
    )
    pid = business.record_ar_payment(
        db._conn,
        cid,
        "2025-03-15",
        50.0,
        [(inv, 50.0)],
        bank_account_id=aid,
        method="Check",
        reference="R1",
        memo="",
    )
    html = ar_payment_html_string(db._conn, pid)
    assert "Receive payment" in html
    assert "CustA" in html
    assert "I-1" in html
    out = tmp_path / "ar.pdf"
    save_ar_payment_pdf(db._conn, pid, str(out))
    assert out.is_file() and out.stat().st_size > 80
    db.close()


def test_ap_payment_html_string(qapp: QApplication, tmp_path) -> None:
    db_path = tmp_path / "ap_pay.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    aid = db.add_bank_account("Checking")
    vid = business.add_vendor(db._conn, "VendZ")
    bid = business.create_bill(
        db._conn,
        vid,
        "2025-04-01",
        0.0,
        vendor_invoice_number="VB-2",
        expense_lines=[
            {
                "line_date": "",
                "ticket_ref": "",
                "amount": 30.0,
                "memo": "",
                "customer_job": "",
            }
        ],
    )
    pid = business.record_ap_payment(
        db._conn,
        vid,
        "2025-04-10",
        30.0,
        [(bid, 30.0)],
        bank_account_id=aid,
        reference="REFZ",
        memo="",
    )
    html = ap_payment_html_string(db._conn, pid)
    assert "Pay bills payment" in html
    assert "VendZ" in html
    out = tmp_path / "ap.pdf"
    save_ap_payment_pdf(db._conn, pid, str(out))
    assert out.is_file() and out.stat().st_size > 80
    db.close()
