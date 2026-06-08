"""
ProBooks+ai remote API server
==============================
Thin FastAPI layer over the existing probooks/probooksai SQLite backend.
Enables remote document intake, invoice/bill creation, and reporting
from the road (mobile browser, Telegram bot, email automation, etc.).

Run with:
    pip install fastapi uvicorn python-multipart
    uvicorn api.server:app --host 0.0.0.0 --port 8000

Environment variables (same as desktop app — see .env.example):
    ANTHROPIC_API_KEY   – Claude API key for document extraction
    AI_PROVIDER         – "anthropic" (default) or "openai"
    PROBOOKS_DB_PATH    – Path to the company SQLite file
                          (defaults to the standard probooks path)
    API_SECRET_KEY      – Bearer token for authentication
                          (REQUIRED before exposing to the internet)
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Optional

try:
    from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
    from pydantic import BaseModel, Field
except ImportError as _err:
    raise ImportError(
        "FastAPI is required for the remote API server. "
        "Install with: pip install fastapi uvicorn python-multipart"
    ) from _err

from probooks.paths import default_intake_db_path
from probooksai.database import DocumentDatabase

app = FastAPI(
    title="ProBooks+ai API",
    description="Remote accounting API: document intake, invoices, bills, reports.",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_bearer = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _check_auth(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> None:
    secret = os.environ.get("API_SECRET_KEY", "").strip()
    if not secret:
        return  # dev mode — no key configured
    if creds is None or creds.credentials != secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API_SECRET_KEY bearer token.",
        )


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _db_path() -> str:
    return os.environ.get("PROBOOKS_DB_PATH") or str(default_intake_db_path())


def _get_doc_db() -> DocumentDatabase:
    return DocumentDatabase(_db_path())


@contextmanager
def _bank_conn():
    """Yield a raw sqlite3 connection to the company DB; close on exit."""
    from probooksai.extensions_schema import apply_extensions
    from probooksai.bank_import import BankDatabase
    bdb = BankDatabase(_db_path())
    apply_extensions(bdb._conn)
    try:
        yield bdb._conn
    finally:
        bdb.close()


def _today() -> str:
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class LineItemIn(BaseModel):
    description: str = ""
    quantity: float = 1.0
    unit_price: float = 0.0
    amount: Optional[float] = None
    coa_account: Optional[str] = None


class InvoiceCreateRequest(BaseModel):
    customer_name: str
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = ""
    memo: Optional[str] = ""
    tax_rate_pct: float = 0.0
    lines: list[LineItemIn] = Field(default_factory=list)


class InvoiceResponse(BaseModel):
    invoice_id: int
    customer_name: str
    invoice_number: str
    invoice_date: str
    due_date: str
    status: str
    total: float


class BillCreateRequest(BaseModel):
    vendor_name: str
    vendor_invoice_number: Optional[str] = ""
    bill_date: Optional[str] = None
    due_date: Optional[str] = ""
    total: float = 0.0
    memo: Optional[str] = ""
    expense_lines: list[LineItemIn] = Field(default_factory=list)


class BillResponse(BaseModel):
    bill_id: int
    vendor_name: str
    vendor_invoice_number: str
    bill_date: str
    due_date: str
    status: str
    total: float


class ExtractionResponse(BaseModel):
    doc_id: int
    vendor: Optional[str] = None
    doc_type: Optional[str] = None
    invoice_number: Optional[str] = None
    doc_date: Optional[str] = None
    due_date: Optional[str] = None
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None
    currency: str = "USD"
    notes: Optional[str] = None
    line_items: list = Field(default_factory=list)
    confidence: float = 0.0
    error: Optional[str] = None


class StatusResponse(BaseModel):
    ok: bool
    message: str
    id: Optional[int] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_or_create_customer(conn: sqlite3.Connection, name: str) -> int:
    """Return existing customer id by name or create a new one."""
    from probooksai.business import list_customers, add_customer
    for c in list_customers(conn):
        if (c["name"] if isinstance(c, dict) else c[1]).lower() == name.lower():
            return c["id"] if isinstance(c, dict) else c[0]
    return add_customer(conn, name=name)


def _get_or_create_vendor(conn: sqlite3.Connection, name: str) -> int:
    """Return existing vendor id by name or create a new one."""
    from probooksai.business import list_vendors, add_vendor
    for v in list_vendors(conn):
        if (v["name"] if isinstance(v, dict) else v[1]).lower() == name.lower():
            return v["id"] if isinstance(v, dict) else v[0]
    return add_vendor(conn, name=name)


def _row_to_dict(row) -> dict:
    if row is None:
        return {}
    if isinstance(row, dict):
        return row
    return dict(row)


# ---------------------------------------------------------------------------
# Endpoints — System
# ---------------------------------------------------------------------------

@app.get("/health", tags=["System"])
def health():
    """Liveness check — no authentication required."""
    return {"status": "ok", "service": "ProBooks+ai API", "version": "0.2.0"}


# ---------------------------------------------------------------------------
# Endpoints — Document Intake
# ---------------------------------------------------------------------------

@app.post(
    "/intake/document",
    response_model=ExtractionResponse,
    tags=["Document Intake"],
    dependencies=[Depends(_check_auth)],
)
async def intake_document(file: UploadFile = File(...)):
    """
    Upload a PDF or image — Claude extracts structured accounting fields.
    The document is stored in the intake DB with status 'new' for later review.
    """
    from ai.extractor import extract_document

    suffix = Path(file.filename or "upload").suffix.lower() or ".bin"
    mime = file.content_type or "application/octet-stream"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        db = _get_doc_db()
        doc_id = db.add_document(source_path=tmp_path, mimetype=mime, store=False)
        result = extract_document(tmp_path, mime)
        if not result.error:
            db.save_extraction(doc_id, result)
        return ExtractionResponse(
            doc_id=doc_id,
            vendor=result.vendor,
            doc_type=result.doc_type,
            invoice_number=result.invoice_number,
            doc_date=result.doc_date,
            due_date=result.due_date,
            subtotal=result.subtotal,
            tax=result.tax,
            total=result.total,
            currency=result.currency or "USD",
            notes=result.notes,
            line_items=result.line_items or [],
            confidence=result.confidence,
            error=result.error,
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@app.get("/documents", tags=["Document Intake"], dependencies=[Depends(_check_auth)])
def list_documents(status_filter: Optional[str] = None):
    """List documents in the intake inbox, optionally filtered by status."""
    db = _get_doc_db()
    docs = db.list_documents()
    if status_filter:
        docs = [d for d in docs if (d.get("status") or "").lower() == status_filter.lower()]
    return {"documents": [_row_to_dict(d) for d in docs], "count": len(docs)}


@app.get("/documents/{doc_id}", tags=["Document Intake"], dependencies=[Depends(_check_auth)])
def get_document(doc_id: int):
    """Get a single document and its extracted fields."""
    db = _get_doc_db()
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found.")
    extraction = db.get_latest_extraction(doc_id)
    return {
        "document": _row_to_dict(doc),
        "extraction": _row_to_dict(extraction) if extraction else None,
    }


@app.patch(
    "/documents/{doc_id}/status",
    response_model=StatusResponse,
    tags=["Document Intake"],
    dependencies=[Depends(_check_auth)],
)
def set_document_status(doc_id: int, new_status: str):
    """Set a document's status (new → approved / rejected / posted)."""
    valid = {"new", "approved", "rejected", "posted"}
    if new_status.lower() not in valid:
        raise HTTPException(status_code=400, detail=f"status must be one of {valid}")
    db = _get_doc_db()
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found.")
    db.set_status(doc_id, new_status.lower())
    return StatusResponse(ok=True, message=f"Document {doc_id} status set to '{new_status}'.", id=doc_id)


# ---------------------------------------------------------------------------
# Endpoints — AR Invoices
# ---------------------------------------------------------------------------

@app.get("/invoices", tags=["AR — Invoices"], dependencies=[Depends(_check_auth)])
def list_invoices():
    """List all invoices with customer name, date, and total."""
    from probooksai.business import list_invoices as _list
    with _bank_conn() as conn:
        rows = _list(conn)
    return {"invoices": [_row_to_dict(r) for r in rows], "count": len(rows)}


@app.get("/invoices/{invoice_id}", tags=["AR — Invoices"], dependencies=[Depends(_check_auth)])
def get_invoice(invoice_id: int):
    """Get full invoice detail including line items."""
    from probooksai.business import get_invoice_detail
    with _bank_conn() as conn:
        header, lines = get_invoice_detail(conn, invoice_id)
    if not header:
        raise HTTPException(status_code=404, detail=f"Invoice {invoice_id} not found.")
    return {
        "invoice": _row_to_dict(header),
        "lines": [_row_to_dict(ln) for ln in lines],
    }


@app.get(
    "/invoices/{invoice_id}/pdf",
    tags=["AR — Invoices"],
    dependencies=[Depends(_check_auth)],
    response_class=__import__("fastapi.responses", fromlist=["FileResponse"]).FileResponse,
)
def download_invoice_pdf(invoice_id: int):
    """
    Generate and download a professional PDF for the given invoice.
    Requires reportlab: pip install reportlab
    """
    from fastapi.responses import FileResponse
    from probooksai.invoice_pdf import render_invoice_pdf
    from probooksai.business import get_invoice_detail
    with _bank_conn() as conn:
        header, _ = get_invoice_detail(conn, invoice_id)
        if not header:
            raise HTTPException(status_code=404, detail=f"Invoice {invoice_id} not found.")
        try:
            pdf_path = render_invoice_pdf(conn, invoice_id)
        except ImportError as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    inv_num = (dict(header).get("invoice_number") or str(invoice_id)).replace("/", "-")
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"Invoice-{inv_num}.pdf",
    )


@app.post(
    "/invoices",
    response_model=StatusResponse,
    tags=["AR — Invoices"],
    dependencies=[Depends(_check_auth)],
)
def create_invoice(req: InvoiceCreateRequest):
    """
    Create a draft invoice. Customer is looked up by name; created if not found.
    Returns the new invoice_id.
    """
    from probooksai.business import create_invoice as _create, next_default_invoice_number
    with _bank_conn() as conn:
        customer_id = _get_or_create_customer(conn, req.customer_name)
        inv_number = req.invoice_number or next_default_invoice_number(conn)
        inv_date = req.invoice_date or _today()
        lines = [
            {
                "description": ln.description,
                "quantity": ln.quantity,
                "unit_price": ln.unit_price,
                "amount": ln.amount if ln.amount is not None else round(ln.quantity * ln.unit_price, 2),
            }
            for ln in req.lines
        ]
        invoice_id = _create(
            conn,
            customer_id=customer_id,
            invoice_number=inv_number,
            invoice_date=inv_date,
            due_date=req.due_date or "",
            memo=req.memo or "",
            lines=lines or None,
            tax_rate_pct=req.tax_rate_pct,
        )
    return StatusResponse(
        ok=True,
        message=f"Invoice #{inv_number} created for {req.customer_name}.",
        id=invoice_id,
    )


# ---------------------------------------------------------------------------
# Endpoints — AP Bills
# ---------------------------------------------------------------------------

@app.get("/bills", tags=["AP — Bills"], dependencies=[Depends(_check_auth)])
def list_bills():
    """List all bills with vendor name, date, and total."""
    from probooksai.business import list_bills as _list
    with _bank_conn() as conn:
        rows = _list(conn)
    return {"bills": [_row_to_dict(r) for r in rows], "count": len(rows)}


@app.get("/bills/{bill_id}", tags=["AP — Bills"], dependencies=[Depends(_check_auth)])
def get_bill(bill_id: int):
    """Get full bill detail including expense lines."""
    from probooksai.business import get_bill_detail
    with _bank_conn() as conn:
        header, lines = get_bill_detail(conn, bill_id)
    if not header:
        raise HTTPException(status_code=404, detail=f"Bill {bill_id} not found.")
    return {
        "bill": _row_to_dict(header),
        "lines": [_row_to_dict(ln) for ln in lines],
    }


@app.post(
    "/bills",
    response_model=StatusResponse,
    tags=["AP — Bills"],
    dependencies=[Depends(_check_auth)],
)
def create_bill(req: BillCreateRequest):
    """
    Create a bill/payable. Vendor is looked up by name; created if not found.
    Returns the new bill_id.
    """
    from probooksai.business import create_bill as _create
    with _bank_conn() as conn:
        vendor_id = _get_or_create_vendor(conn, req.vendor_name)
        bill_date = req.bill_date or _today()
        expense_lines = [
            {
                "description": ln.description,
                "amount": ln.amount if ln.amount is not None else round(ln.quantity * ln.unit_price, 2),
                "coa_account": ln.coa_account or "",
            }
            for ln in req.expense_lines
        ]
        bill_id = _create(
            conn,
            vendor_id=vendor_id,
            bill_date=bill_date,
            total=req.total,
            vendor_invoice_number=req.vendor_invoice_number or "",
            due_date=req.due_date or "",
            memo=req.memo or "",
            expense_lines=expense_lines or None,
        )
    return StatusResponse(
        ok=True,
        message=f"Bill created for {req.vendor_name} (total ${req.total:,.2f}).",
        id=bill_id,
    )


# ---------------------------------------------------------------------------
# Endpoints — Reports
# ---------------------------------------------------------------------------

@app.get("/reports/pl", tags=["Reports"], dependencies=[Depends(_check_auth)])
def profit_and_loss(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """
    Return a Profit & Loss (income statement) summary as JSON.
    Defaults: start_date = first day of current year, end_date = today.
    """
    from probooksai.financial_reports import income_statement
    today = _today()
    sd = start_date or f"{today[:4]}-01-01"
    ed = end_date or today
    with _bank_conn() as conn:
        try:
            return income_statement(conn, start_date=sd, end_date=ed)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/reports/balance", tags=["Reports"], dependencies=[Depends(_check_auth)])
def balance_sheet(as_of_date: Optional[str] = None):
    """
    Return a Balance Sheet summary as JSON.
    Defaults to today if as_of_date is omitted.
    """
    from probooksai.financial_reports import balance_sheet_summary
    with _bank_conn() as conn:
        try:
            return balance_sheet_summary(conn, as_of_date=as_of_date or _today())
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/reports/aging/ar", tags=["Reports"], dependencies=[Depends(_check_auth)])
def ar_aging(as_of_date: Optional[str] = None):
    """Return AR aging buckets (current / 30 / 60 / 90+ days)."""
    from probooksai.business import ar_aging_buckets
    with _bank_conn() as conn:
        try:
            return ar_aging_buckets(conn, as_of=as_of_date or _today())
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/reports/aging/ap", tags=["Reports"], dependencies=[Depends(_check_auth)])
def ap_aging(as_of_date: Optional[str] = None):
    """Return AP aging buckets (current / 30 / 60 / 90+ days)."""
    from probooksai.business import ap_aging_buckets
    with _bank_conn() as conn:
        try:
            return ap_aging_buckets(conn, as_of=as_of_date or _today())
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("API_HOST", "127.0.0.1")
    port = int(os.environ.get("API_PORT", "8000"))
    uvicorn.run("api.server:app", host=host, port=port, reload=True)
