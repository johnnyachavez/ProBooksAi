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
import tempfile
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# FastAPI is optional — only needed when running the API server.
# The desktop app imports nothing from this module.
# ---------------------------------------------------------------------------
try:
    from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
    from pydantic import BaseModel
except ImportError as _err:
    raise ImportError(
        "FastAPI is required for the remote API server. "
        "Install with: pip install fastapi uvicorn python-multipart"
    ) from _err

from probooks.paths import default_intake_db_path
from probooksai.database import DocumentDatabase
from probooksai.financial_reports import FinancialReports

app = FastAPI(
    title="ProBooks+ai API",
    description="Remote accounting API: document intake, invoices, bills, reports.",
    version="0.1.0",
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
# Auth (simple bearer token — swap for OAuth in production)
# ---------------------------------------------------------------------------

def _check_auth(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> None:
    secret = os.environ.get("API_SECRET_KEY", "").strip()
    if not secret:
        return  # no key configured → open (dev mode only — warn in logs)
    if creds is None or creds.credentials != secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API_SECRET_KEY bearer token.",
        )


# ---------------------------------------------------------------------------
# Database helper
# ---------------------------------------------------------------------------

def _get_db() -> DocumentDatabase:
    db_path = os.environ.get("PROBOOKS_DB_PATH") or str(default_intake_db_path())
    return DocumentDatabase(db_path)


def _get_conn():
    from probooksai.bank_import import BankDatabase
    db_path = os.environ.get("PROBOOKS_DB_PATH") or str(default_intake_db_path())
    return BankDatabase(db_path)._conn


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

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
    line_items: list = []
    confidence: float = 0.0
    error: Optional[str] = None


class InvoiceCreateRequest(BaseModel):
    customer_name: str
    invoice_number: Optional[str] = None
    doc_date: Optional[str] = None
    due_date: Optional[str] = None
    total: Optional[float] = None
    notes: Optional[str] = None
    line_items: list = []


class BillCreateRequest(BaseModel):
    vendor_name: str
    vendor_invoice: Optional[str] = None
    bill_date: Optional[str] = None
    due_date: Optional[str] = None
    total: Optional[float] = None
    notes: Optional[str] = None
    line_items: list = []


class StatusResponse(BaseModel):
    ok: bool
    message: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", tags=["System"])
def health():
    """Liveness check — returns ok without authentication."""
    return {"status": "ok", "service": "ProBooks+ai API"}


@app.post(
    "/intake/document",
    response_model=ExtractionResponse,
    tags=["Document Intake"],
    dependencies=[Depends(_check_auth)],
)
async def intake_document(file: UploadFile = File(...)):
    """
    Upload a PDF or image — Claude extracts structured accounting fields.

    Returns extracted fields immediately. The document is stored in the
    intake database with status "new" for later review and approval.
    """
    from ai.extractor import extract_document

    suffix = Path(file.filename or "upload").suffix.lower() or ".bin"
    mime = file.content_type or "application/octet-stream"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        db = _get_db()
        doc_id = db.add_document(
            filename=file.filename or "upload",
            stored_path=tmp_path,
            mimetype=mime,
        )
        result = extract_document(tmp_path, mime)
        if not result.error:
            db.save_extraction(doc_id, {
                "vendor": result.vendor,
                "doc_type": result.doc_type,
                "invoice_number": result.invoice_number,
                "doc_date": result.doc_date,
                "due_date": result.due_date,
                "subtotal": result.subtotal,
                "tax": result.tax,
                "total": result.total,
                "currency": result.currency,
                "notes": result.notes,
            })
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
            currency=result.currency,
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


@app.post(
    "/invoices",
    response_model=StatusResponse,
    tags=["AR — Invoices"],
    dependencies=[Depends(_check_auth)],
)
def create_invoice(req: InvoiceCreateRequest):
    """
    Create a draft invoice from structured data (e.g. forwarded from document intake).
    The invoice is written to the AR tables in the company SQLite file.
    """
    from probooksai import business
    conn = _get_conn()
    try:
        business.create_invoice(
            conn,
            customer_name=req.customer_name,
            invoice_number=req.invoice_number,
            doc_date=req.doc_date,
            due_date=req.due_date,
            total=req.total,
            notes=req.notes,
            line_items=req.line_items,
        )
        return StatusResponse(ok=True, message=f"Invoice created for {req.customer_name}.")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post(
    "/bills",
    response_model=StatusResponse,
    tags=["AP — Bills"],
    dependencies=[Depends(_check_auth)],
)
def create_bill(req: BillCreateRequest):
    """
    Create a bill/payable from structured data.
    Written to the AP tables in the company SQLite file.
    """
    from probooksai import business
    conn = _get_conn()
    try:
        business.create_bill(
            conn,
            vendor_name=req.vendor_name,
            vendor_invoice=req.vendor_invoice,
            bill_date=req.bill_date,
            due_date=req.due_date,
            total=req.total,
            notes=req.notes,
            line_items=req.line_items,
        )
        return StatusResponse(ok=True, message=f"Bill created for {req.vendor_name}.")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get(
    "/reports/pl",
    tags=["Reports"],
    dependencies=[Depends(_check_auth)],
)
def profit_and_loss(start_date: Optional[str] = None, end_date: Optional[str] = None):
    """Return a Profit & Loss summary as JSON."""
    try:
        conn = _get_conn()
        rpt = FinancialReports(conn)
        return rpt.profit_and_loss(start_date=start_date, end_date=end_date)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get(
    "/reports/balance",
    tags=["Reports"],
    dependencies=[Depends(_check_auth)],
)
def balance_sheet(as_of_date: Optional[str] = None):
    """Return a Balance Sheet as JSON."""
    try:
        conn = _get_conn()
        rpt = FinancialReports(conn)
        return rpt.balance_sheet(as_of_date=as_of_date)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get(
    "/documents",
    tags=["Document Intake"],
    dependencies=[Depends(_check_auth)],
)
def list_documents(status_filter: Optional[str] = None):
    """List documents in the intake inbox, optionally filtered by status."""
    db = _get_db()
    docs = db.list_documents()
    if status_filter:
        docs = [d for d in docs if (d.get("status") or "").lower() == status_filter.lower()]
    return {"documents": docs, "count": len(docs)}


@app.get(
    "/documents/{doc_id}",
    tags=["Document Intake"],
    dependencies=[Depends(_check_auth)],
)
def get_document(doc_id: int):
    """Get a single document and its extracted fields."""
    db = _get_db()
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found.")
    extraction = db.get_latest_extraction(doc_id)
    return {"document": dict(doc), "extraction": dict(extraction) if extraction else None}


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("API_HOST", "127.0.0.1")
    port = int(os.environ.get("API_PORT", "8000"))
    uvicorn.run("api.server:app", host=host, port=port, reload=True)
