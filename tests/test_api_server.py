"""
Tests for api.server — FastAPI endpoints.

Uses httpx.AsyncClient + fastapi.testclient.TestClient (sync) against
an in-memory SQLite DB injected via monkeypatching _db_path().
No network calls; no AI calls.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Skip entire module if FastAPI / httpx are not installed
# ---------------------------------------------------------------------------
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from api.server import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path):
    """Create a real SQLite DB with all required tables seeded."""
    db_file = str(tmp_path / "test_company.db")

    from probooksai.bank_import import BankDatabase
    from probooksai.extensions_schema import apply_extensions
    from probooksai.database import DocumentDatabase
    from probooksai.coa_db import COADatabase
    from probooksai.gl import GLDatabase

    bdb = BankDatabase(db_file)
    apply_extensions(bdb._conn)
    COADatabase(bdb._conn).seed_from_workbook()  # seeds coa_accounts needed by reports
    GLDatabase(bdb._conn)                         # seeds gl tables
    bdb.close()

    DocumentDatabase(db_file)  # seeds doc tables

    return db_file


@pytest.fixture()
def client(tmp_db, monkeypatch):
    """TestClient with DB path patched and no auth secret (dev mode)."""
    monkeypatch.setenv("PROBOOKS_DB_PATH", tmp_db)
    monkeypatch.delenv("API_SECRET_KEY", raising=False)
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture()
def authed_client(tmp_db, monkeypatch):
    """TestClient with bearer token auth enabled."""
    monkeypatch.setenv("PROBOOKS_DB_PATH", tmp_db)
    monkeypatch.setenv("API_SECRET_KEY", "test-secret")
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

def test_health_no_auth(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Auth enforcement
# ---------------------------------------------------------------------------

def test_auth_rejects_missing_token(authed_client):
    r = authed_client.get("/invoices")
    assert r.status_code == 401


def test_auth_rejects_wrong_token(authed_client):
    r = authed_client.get("/invoices", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_auth_accepts_correct_token(authed_client):
    r = authed_client.get("/invoices", headers={"Authorization": "Bearer test-secret"})
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# /invoices
# ---------------------------------------------------------------------------

def test_list_invoices_empty(client):
    r = client.get("/invoices")
    assert r.status_code == 200
    assert r.json()["count"] == 0
    assert r.json()["invoices"] == []


def test_create_invoice_and_list(client):
    payload = {
        "customer_name": "Acme Corp",
        "invoice_number": "INV-001",
        "invoice_date": "2025-01-15",
        "due_date": "2025-02-15",
        "memo": "Test invoice",
        "lines": [{"description": "Consulting", "quantity": 2, "unit_price": 500.0}],
    }
    r = client.post("/invoices", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["id"] is not None
    assert "Acme Corp" in body["message"]

    r2 = client.get("/invoices")
    assert r2.json()["count"] == 1


def test_create_invoice_creates_customer_if_missing(client):
    payload = {"customer_name": "New Customer LLC"}
    r = client.post("/invoices", json=payload)
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_get_invoice_detail(client):
    payload = {"customer_name": "Detail Co", "invoice_number": "INV-D1"}
    r = client.post("/invoices", json=payload)
    inv_id = r.json()["id"]

    r2 = client.get(f"/invoices/{inv_id}")
    assert r2.status_code == 200
    body = r2.json()
    assert "invoice" in body
    assert "lines" in body


def test_get_invoice_not_found(client):
    r = client.get("/invoices/9999")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# /bills
# ---------------------------------------------------------------------------

def test_list_bills_empty(client):
    r = client.get("/bills")
    assert r.status_code == 200
    assert r.json()["count"] == 0


def test_create_bill_and_list(client):
    payload = {
        "vendor_name": "Office Depot",
        "vendor_invoice_number": "OD-88",
        "bill_date": "2025-03-01",
        "due_date": "2025-03-31",
        "total": 250.0,
        "memo": "Office supplies",
    }
    r = client.post("/bills", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["id"] is not None

    r2 = client.get("/bills")
    assert r2.json()["count"] == 1


def test_create_bill_creates_vendor_if_missing(client):
    payload = {"vendor_name": "New Vendor Inc", "total": 100.0}
    r = client.post("/bills", json=payload)
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_get_bill_not_found(client):
    r = client.get("/bills/9999")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# /documents
# ---------------------------------------------------------------------------

def test_list_documents_empty(client):
    r = client.get("/documents")
    assert r.status_code == 200
    assert r.json()["count"] == 0


def test_get_document_not_found(client):
    r = client.get("/documents/9999")
    assert r.status_code == 404


def test_set_document_status_invalid(client):
    r = client.patch("/documents/1/status", params={"new_status": "garbage"})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# /reports/pl and /reports/balance
# ---------------------------------------------------------------------------

def test_pl_report_returns_dict(client):
    r = client.get("/reports/pl")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


def test_pl_report_with_dates(client):
    r = client.get("/reports/pl", params={"start_date": "2025-01-01", "end_date": "2025-12-31"})
    assert r.status_code == 200


def test_balance_sheet_returns_dict(client):
    r = client.get("/reports/balance")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


def test_balance_sheet_with_date(client):
    r = client.get("/reports/balance", params={"as_of_date": "2025-12-31"})
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# /reports/aging
# ---------------------------------------------------------------------------

def test_ar_aging(client):
    r = client.get("/reports/aging/ar")
    assert r.status_code == 200


def test_ap_aging(client):
    r = client.get("/reports/aging/ap")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# /intake/document (mock AI)
# ---------------------------------------------------------------------------

def test_intake_document_mocked(client, tmp_path):
    """Upload a fake PDF — mock extract_document so no real AI call is made."""
    from ai.extractor import ExtractionResult

    fake_result = ExtractionResult(
        vendor="Fake Vendor",
        doc_type="invoice",
        invoice_number="FV-001",
        doc_date="2025-06-01",
        due_date="2025-07-01",
        subtotal=100.0,
        tax=8.0,
        total=108.0,
        currency="USD",
        confidence=0.95,
    )

    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    with patch("ai.extractor.extract_document", return_value=fake_result):
        with open(pdf, "rb") as fh:
            r = client.post(
                "/intake/document",
                files={"file": ("test.pdf", fh, "application/pdf")},
            )

    assert r.status_code == 200
    body = r.json()
    assert body["vendor"] == "Fake Vendor"
    assert body["total"] == 108.0
    assert body["doc_id"] is not None
