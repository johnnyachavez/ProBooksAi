"""
Tests for the documents upload / approval feature.

Run with:  python -m pytest test_documents.py -v
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Redirect uploads to a temporary directory before importing the app so
# the tests don't pollute (or require) a real 'uploads/' directory.
import app.documents as docs_module


@pytest.fixture(autouse=True)
def _tmp_uploads(tmp_path, monkeypatch):
    """Override UPLOADS_DIR and METADATA_FILE to use a temp directory."""
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(docs_module, "UPLOADS_DIR", uploads)
    monkeypatch.setattr(docs_module, "METADATA_FILE", uploads / "metadata.json")
    yield uploads


@pytest.fixture()
def client():
    from app.main import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

class TestUpload:
    def test_upload_returns_201(self, client):
        data = io.BytesIO(b"%PDF-1.4 fake pdf content")
        resp = client.post(
            "/documents/",
            files={"file": ("invoice.pdf", data, "application/pdf")},
        )
        assert resp.status_code == 201

    def test_upload_sets_pending_status(self, client):
        data = io.BytesIO(b"content")
        resp = client.post(
            "/documents/",
            files={"file": ("doc.txt", data, "text/plain")},
        )
        assert resp.json()["status"] == "pending"

    def test_upload_returns_id_and_filename(self, client):
        data = io.BytesIO(b"content")
        resp = client.post(
            "/documents/",
            files={"file": ("receipt.pdf", data, "application/pdf")},
        )
        body = resp.json()
        assert "id" in body
        assert body["filename"] == "receipt.pdf"

    def test_upload_persists_to_disk(self, client, _tmp_uploads):
        data = io.BytesIO(b"hello")
        resp = client.post(
            "/documents/",
            files={"file": ("a.txt", data, "text/plain")},
        )
        doc_id = resp.json()["id"]
        assert (_tmp_uploads / doc_id).is_dir()

    def test_upload_includes_ai_extraction_stub(self, client):
        data = io.BytesIO(b"content")
        resp = client.post(
            "/documents/",
            files={"file": ("bill.pdf", data, "application/pdf")},
        )
        extracted = resp.json().get("extracted", {})
        assert "confidence" in extracted
        assert extracted["confidence"] == 0.0


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

class TestList:
    def test_list_empty_initially(self, client):
        resp = client.get("/documents/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_shows_uploaded_doc(self, client):
        client.post(
            "/documents/",
            files={"file": ("x.pdf", io.BytesIO(b"x"), "application/pdf")},
        )
        resp = client.get("/documents/")
        assert len(resp.json()) == 1

    def test_list_filter_by_status(self, client):
        # Upload two docs, approve one
        r1 = client.post(
            "/documents/",
            files={"file": ("a.pdf", io.BytesIO(b"a"), "application/pdf")},
        )
        r2 = client.post(
            "/documents/",
            files={"file": ("b.pdf", io.BytesIO(b"b"), "application/pdf")},
        )
        client.post(f"/documents/{r1.json()['id']}/approve")

        pending = client.get("/documents/?status=pending").json()
        approved = client.get("/documents/?status=approved").json()
        assert len(pending) == 1
        assert len(approved) == 1
        assert approved[0]["id"] == r1.json()["id"]


# ---------------------------------------------------------------------------
# Get single
# ---------------------------------------------------------------------------

class TestGetDocument:
    def test_get_existing(self, client):
        r = client.post(
            "/documents/",
            files={"file": ("f.pdf", io.BytesIO(b"f"), "application/pdf")},
        )
        doc_id = r.json()["id"]
        resp = client.get(f"/documents/{doc_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == doc_id

    def test_get_missing_returns_404(self, client):
        resp = client.get("/documents/nonexistent-id")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Approve / Reject
# ---------------------------------------------------------------------------

class TestApproveReject:
    def _upload(self, client):
        r = client.post(
            "/documents/",
            files={"file": ("doc.pdf", io.BytesIO(b"d"), "application/pdf")},
        )
        return r.json()["id"]

    def test_approve_changes_status(self, client):
        doc_id = self._upload(client)
        resp = client.post(f"/documents/{doc_id}/approve")
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    def test_reject_changes_status(self, client):
        doc_id = self._upload(client)
        resp = client.post(f"/documents/{doc_id}/reject")
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    def test_approve_sets_reviewed_at(self, client):
        doc_id = self._upload(client)
        resp = client.post(f"/documents/{doc_id}/approve")
        assert resp.json()["reviewed_at"] is not None

    def test_approve_missing_doc_returns_404(self, client):
        resp = client.post("/documents/missing/approve")
        assert resp.status_code == 404

    def test_reject_missing_doc_returns_404(self, client):
        resp = client.post("/documents/missing/reject")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Bundle (ZIP download)
# ---------------------------------------------------------------------------

class TestBundle:
    def test_bundle_returns_zip(self, client):
        r = client.post(
            "/documents/",
            files={"file": ("inv.pdf", io.BytesIO(b"pdf-bytes"), "application/pdf")},
        )
        doc_id = r.json()["id"]
        resp = client.get(f"/documents/{doc_id}/bundle")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"

    def test_bundle_zip_contains_file(self, client):
        r = client.post(
            "/documents/",
            files={"file": ("receipt.pdf", io.BytesIO(b"data"), "application/pdf")},
        )
        doc_id = r.json()["id"]
        resp = client.get(f"/documents/{doc_id}/bundle")
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        names = zf.namelist()
        assert len(names) == 1
        assert names[0].startswith(doc_id)

    def test_bundle_missing_doc_returns_404(self, client):
        resp = client.get("/documents/missing-id/bundle")
        assert resp.status_code == 404
