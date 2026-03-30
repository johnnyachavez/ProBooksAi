"""
Documents router — upload, list, approve/reject uploaded documents.

Storage layout
--------------
uploads/
    <doc_id>/
        original.<ext>        ← the uploaded file
metadata.json                 ← list of DocumentRecord dicts

Document states
---------------
pending   — uploaded, awaiting approval before sending/processing
approved  — approved by a user; ready to process / send
rejected  — rejected; will not be processed further
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.ai_extraction import extract as ai_extract
from app.bundle import build_zip

UPLOADS_DIR = Path("uploads")
METADATA_FILE = UPLOADS_DIR / "metadata.json"

DocumentStatus = Literal["pending", "approved", "rejected"]

router = APIRouter(prefix="/documents", tags=["documents"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_dirs() -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def _load_metadata() -> list[dict]:
    _ensure_dirs()
    if not METADATA_FILE.exists():
        return []
    with METADATA_FILE.open() as f:
        return json.load(f)


def _save_metadata(records: list[dict]) -> None:
    _ensure_dirs()
    with METADATA_FILE.open("w") as f:
        json.dump(records, f, indent=2, default=str)


def _find_record(records: list[dict], doc_id: str) -> dict | None:
    return next((r for r in records if r["id"] == doc_id), None)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/", status_code=201)
async def upload_document(file: UploadFile):
    """Upload a document (PDF or any file) and queue it for approval.

    The document is stored locally under ``uploads/<doc_id>/``.
    Its initial status is ``pending``.
    """
    _ensure_dirs()
    doc_id = str(uuid.uuid4())
    suffix = Path(file.filename or "upload").suffix or ".bin"
    dest_dir = UPLOADS_DIR / doc_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / f"original{suffix}"

    with dest_file.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    # Run AI extraction (placeholder — returns stub data for now)
    extracted = ai_extract(dest_file)

    record: dict = {
        "id": doc_id,
        "filename": file.filename,
        "content_type": file.content_type,
        "status": "pending",
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "reviewed_at": None,
        "path": str(dest_file),
        "extracted": extracted,
    }

    records = _load_metadata()
    records.append(record)
    _save_metadata(records)
    return record


@router.get("/")
def list_documents(status: DocumentStatus | None = None):
    """List all uploaded documents, optionally filtered by *status*.

    Query params
    ------------
    status : pending | approved | rejected  (optional)
    """
    records = _load_metadata()
    if status:
        records = [r for r in records if r["status"] == status]
    return records


@router.get("/{doc_id}")
def get_document(doc_id: str):
    """Get metadata for a single document by ID."""
    records = _load_metadata()
    record = _find_record(records, doc_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return record


@router.post("/{doc_id}/approve", status_code=200)
def approve_document(doc_id: str):
    """Approve a pending document, marking it ready for processing / sending."""
    return _set_status(doc_id, "approved")


@router.post("/{doc_id}/reject", status_code=200)
def reject_document(doc_id: str):
    """Reject a document so it will not be processed further."""
    return _set_status(doc_id, "rejected")


def _set_status(doc_id: str, new_status: DocumentStatus) -> dict:
    records = _load_metadata()
    record = _find_record(records, doc_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Document not found")
    record["status"] = new_status
    record["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    _save_metadata(records)
    return record


@router.get("/{doc_id}/bundle")
def download_bundle(doc_id: str):
    """Download a ZIP archive containing the document and any attachments.

    This endpoint demonstrates the bundling capability described in Issue #2.
    For the initial slice only the uploaded file itself is included; future
    iterations will attach generated invoice PDFs alongside it.
    """
    records = _load_metadata()
    record = _find_record(records, doc_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = Path(record["path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Uploaded file not found on disk")

    zip_bytes = build_zip(doc_id, [file_path])
    filename = record.get("filename") or "document"
    zip_name = f"{Path(filename).stem}_bundle.zip"

    return StreamingResponse(
        iter([zip_bytes]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_name}"'},
    )
