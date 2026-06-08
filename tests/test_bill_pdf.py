"""Bill PDF / HTML string from saved bill rows."""

from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QApplication

from desktop_app.bill_pdf import bill_html_string, save_bill_pdf
from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import apply_extensions
from probooksai import business


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_bill_html_string_contains_vendor_and_total(qapp: QApplication, tmp_path) -> None:
    db_path = tmp_path / "bill_pdf.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    vid = business.add_vendor(db._conn, "VendCo", address="1 Road")
    bid = business.create_bill(
        db._conn,
        vid,
        "2025-01-10",
        0.0,
        vendor_invoice_number="B-88",
        memo="hdr",
        expense_lines=[
            {
                "line_date": "2025-01-10",
                "ticket_ref": "T1",
                "amount": 100.0,
                "memo": "Fuel",
                "customer_job": "C:J",
            }
        ],
    )
    html = bill_html_string(db._conn, bid)
    assert "Bill</div>" in html or "Bill" in html
    assert "VendCo" in html
    assert "100.00" in html.replace(",", "") or "$100.00" in html
    db.close()


def test_save_bill_pdf_writes_file(qapp: QApplication, tmp_path) -> None:
    db_path = tmp_path / "bill_save_pdf.db"
    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    vid = business.add_vendor(db._conn, "X")
    bid = business.create_bill(
        db._conn,
        vid,
        "2025-02-01",
        0.0,
        vendor_invoice_number="Z9",
        expense_lines=[
            {
                "line_date": "",
                "ticket_ref": "",
                "amount": 5.0,
                "memo": "",
                "customer_job": "",
            }
        ],
    )
    out = tmp_path / "out.pdf"
    save_bill_pdf(db._conn, bid, str(out))
    assert out.is_file() and out.stat().st_size > 100
    db.close()
