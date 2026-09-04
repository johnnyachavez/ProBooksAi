"""
Tests for probooksai.invoice_pdf — the headless (API / bot) wrapper around the desktop
Print / Save As PDF path. Skipped if Qt print support is not installed.
"""

from __future__ import annotations

import os
import sqlite3
import sys

import pytest

pytest.importorskip("PySide6.QtPrintSupport", reason="PySide6 not installed")

from probooksai.invoice_pdf import render_invoice_pdf

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="QPrinter PDF can abort the Qt process on some Windows builds (0xC0000409); Linux CI runs this.",
)


@pytest.fixture()
def company_db(tmp_path):
    """Minimal company DB with one invoice."""
    db_file = str(tmp_path / "company.db")
    from probooksai.bank_import import BankDatabase
    from probooksai.extensions_schema import apply_extensions
    from probooksai.coa_db import COADatabase
    from probooksai.business import add_customer, create_invoice

    bdb = BankDatabase(db_file)
    apply_extensions(bdb._conn)
    COADatabase(bdb._conn).seed_from_workbook()

    conn = bdb._conn
    # Seed company settings
    conn.execute(
        "INSERT OR REPLACE INTO company_settings(key, value) VALUES (?, ?)",
        ("company_name", "Test Co LLC"),
    )
    conn.execute(
        "INSERT OR REPLACE INTO company_settings(key, value) VALUES (?, ?)",
        ("company_address", "123 Main St\nSpringfield, IL 62701"),
    )
    conn.commit()

    cust_id = add_customer(conn, name="Acme Corp")
    inv_id = create_invoice(
        conn,
        customer_id=cust_id,
        invoice_number="INV-001",
        invoice_date="2025-06-01",
        due_date="2025-07-01",
        memo="Thank you for your business.",
        lines=[
            {"description": "Web design", "quantity": 10, "unit_price": 150.0, "amount": 1500.0},
            {"description": "Hosting (1 yr)", "quantity": 1, "unit_price": 240.0, "amount": 240.0},
        ],
        tax_rate_pct=8.0,
    )
    bdb.close()
    return db_file, inv_id


def test_render_creates_pdf_file(company_db, tmp_path):
    db_file, inv_id = company_db
    import sqlite3
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    out = str(tmp_path / "test_invoice.pdf")
    result_path = render_invoice_pdf(conn, inv_id, output_path=out)
    conn.close()

    assert result_path == out
    assert os.path.isfile(out)
    assert os.path.getsize(out) > 2000  # non-trivial PDF


def test_render_to_temp_file(company_db):
    db_file, inv_id = company_db
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    result_path = render_invoice_pdf(conn, inv_id)
    conn.close()

    assert result_path.endswith(".pdf")
    assert os.path.isfile(result_path)
    # PDF magic bytes
    with open(result_path, "rb") as f:
        assert f.read(4) == b"%PDF"
    os.unlink(result_path)


def test_render_uses_shared_print_template(company_db, monkeypatch, tmp_path):
    """The API/bot renderer must go through the desktop Print/Save-As-PDF path."""
    db_file, inv_id = company_db
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    calls: list[tuple[int, str]] = []

    import desktop_app.invoice_pdf as desktop_invoice_pdf

    def _fake_save(_conn, invoice_id, file_path):
        calls.append((invoice_id, file_path))
        with open(file_path, "wb") as fh:
            fh.write(b"%PDF-1.4 stub")

    monkeypatch.setattr(desktop_invoice_pdf, "save_invoice_pdf", _fake_save)
    out = str(tmp_path / "shared.pdf")
    render_invoice_pdf(conn, inv_id, output_path=out)
    conn.close()

    assert calls == [(inv_id, out)]


def test_render_invalid_invoice_id(company_db):
    db_file, _ = company_db
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    with pytest.raises(ValueError, match="not found"):
        render_invoice_pdf(conn, 9999)
    conn.close()


def test_api_invoice_pdf_route(tmp_path):
    """Test the /invoices/{id}/pdf FastAPI route returns a PDF."""
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")

    from fastapi.testclient import TestClient
    from api.server import app
    from probooksai.bank_import import BankDatabase
    from probooksai.extensions_schema import apply_extensions
    from probooksai.coa_db import COADatabase
    from probooksai.database import DocumentDatabase
    from probooksai.business import add_customer, create_invoice

    db_file = str(tmp_path / "api_test.db")
    bdb = BankDatabase(db_file)
    apply_extensions(bdb._conn)
    COADatabase(bdb._conn).seed_from_workbook()
    DocumentDatabase(db_file)

    conn = bdb._conn
    conn.execute(
        "INSERT OR REPLACE INTO company_settings(key, value) VALUES (?, ?)",
        ("company_name", "API Test Co"),
    )
    conn.commit()
    cust_id = add_customer(conn, name="Test Client")
    inv_id = create_invoice(
        conn,
        customer_id=cust_id,
        invoice_number="API-001",
        invoice_date="2025-06-15",
        lines=[{"description": "Services", "quantity": 1, "unit_price": 500.0, "amount": 500.0}],
    )
    bdb.close()

    import os
    os.environ["PROBOOKS_DB_PATH"] = db_file
    os.environ.pop("API_SECRET_KEY", None)

    with TestClient(app) as client:
        r = client.get(f"/invoices/{inv_id}/pdf")

    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"

    # Bot / API downloads come off the same paper template as desktop Print.
    pypdf = pytest.importorskip("pypdf")
    import io

    reader = pypdf.PdfReader(io.BytesIO(r.content))
    text = " ".join(" ".join((page.extract_text() or "").split()) for page in reader.pages)
    assert "INVOICE" in text
    assert "SERVICED ON" in text
    assert "JL#" in text
    assert "BOL#" in text
    assert "QTY RATE AMOUNT" in text
    assert "Terms: NET 30" in text
