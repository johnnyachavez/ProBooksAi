"""
Tests for probooksai.database
"""

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from probooksai.database import DocumentDatabase, get_data_dir, get_docs_dir, _file_hash


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    """Return a DocumentDatabase backed by a temp file."""
    db_path = str(tmp_path / "test.db")
    db = DocumentDatabase(db_path=db_path)
    yield db
    db.close()


@pytest.fixture
def sample_pdf(tmp_path):
    """Create a minimal PDF-like file for import testing."""
    p = tmp_path / "invoice.pdf"
    # Minimal valid PDF header (not a real PDF but enough for path testing)
    p.write_bytes(b"%PDF-1.4\n")
    return str(p)


@pytest.fixture
def sample_image(tmp_path):
    """Create a minimal PNG file (1×1 pixel) for import testing."""
    p = tmp_path / "receipt.png"
    # Minimal 1x1 white PNG
    import struct
    import zlib

    def png_chunk(name, data):
        crc = zlib.crc32(name + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", crc)

    header = b"\x89PNG\r\n\x1a\n"
    ihdr   = png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw    = b"\x00\xff\xff\xff"
    idat   = png_chunk(b"IDAT", zlib.compress(raw))
    iend   = png_chunk(b"IEND", b"")
    p.write_bytes(header + ihdr + idat + iend)
    return str(p)


# ---------------------------------------------------------------------------
# Schema / connection
# ---------------------------------------------------------------------------

class TestSchema:
    def test_creates_documents_table(self, tmp_db):
        cur = tmp_db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='documents'"
        )
        assert cur.fetchone() is not None

    def test_creates_extractions_table(self, tmp_db):
        cur = tmp_db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='extractions'"
        )
        assert cur.fetchone() is not None

    def test_creates_approved_values_table(self, tmp_db):
        cur = tmp_db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='approved_values'"
        )
        assert cur.fetchone() is not None

    def test_creates_status_log_table(self, tmp_db):
        cur = tmp_db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='status_log'"
        )
        assert cur.fetchone() is not None


# ---------------------------------------------------------------------------
# Document import
# ---------------------------------------------------------------------------

class TestAddDocument:
    def test_add_pdf_returns_id(self, tmp_db, sample_pdf):
        doc_id = tmp_db.add_document(sample_pdf, "application/pdf", store=False)
        assert isinstance(doc_id, int)
        assert doc_id > 0

    def test_add_image_returns_id(self, tmp_db, sample_image):
        doc_id = tmp_db.add_document(sample_image, "image/png", store=False)
        assert isinstance(doc_id, int)
        assert doc_id > 0

    def test_new_document_status_is_new(self, tmp_db, sample_pdf):
        doc_id = tmp_db.add_document(sample_pdf, "application/pdf", store=False)
        row = tmp_db.get_document(doc_id)
        assert row["status"] == "New"

    def test_document_filename_stored(self, tmp_db, sample_pdf):
        doc_id = tmp_db.add_document(sample_pdf, "application/pdf", store=False)
        row = tmp_db.get_document(doc_id)
        assert row["filename"] == "invoice.pdf"

    def test_document_mimetype_stored(self, tmp_db, sample_pdf):
        doc_id = tmp_db.add_document(sample_pdf, "application/pdf", store=False)
        row = tmp_db.get_document(doc_id)
        assert row["mimetype"] == "application/pdf"

    def test_file_hash_stored(self, tmp_db, sample_pdf):
        doc_id = tmp_db.add_document(sample_pdf, "application/pdf", store=False)
        row = tmp_db.get_document(doc_id)
        assert len(row["file_hash"]) == 64  # SHA-256 hex

    def test_import_creates_status_log_entry(self, tmp_db, sample_pdf):
        doc_id = tmp_db.add_document(sample_pdf, "application/pdf", store=False)
        log = tmp_db.get_status_log(doc_id)
        assert len(log) >= 1
        assert log[0]["new_status"] == "New"

    def test_image_page_count_is_one(self, tmp_db, sample_image):
        doc_id = tmp_db.add_document(sample_image, "image/png", store=False)
        row = tmp_db.get_document(doc_id)
        assert row["page_count"] == 1


# ---------------------------------------------------------------------------
# List documents
# ---------------------------------------------------------------------------

class TestListDocuments:
    def test_list_empty(self, tmp_db):
        assert tmp_db.list_documents() == []

    def test_list_returns_all(self, tmp_db, sample_pdf, sample_image):
        tmp_db.add_document(sample_pdf, "application/pdf", store=False)
        tmp_db.add_document(sample_image, "image/png", store=False)
        docs = tmp_db.list_documents()
        assert len(docs) == 2

    def test_list_ordered_newest_first(self, tmp_db, sample_pdf, sample_image):
        id1 = tmp_db.add_document(sample_pdf, "application/pdf", store=False)
        id2 = tmp_db.add_document(sample_image, "image/png", store=False)
        docs = tmp_db.list_documents()
        # Newest (id2) should appear first
        assert docs[0]["id"] == id2


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------

class TestStatusTransitions:
    def test_set_valid_status(self, tmp_db, sample_pdf):
        doc_id = tmp_db.add_document(sample_pdf, "application/pdf", store=False)
        tmp_db.set_status(doc_id, "Extracted")
        row = tmp_db.get_document(doc_id)
        assert row["status"] == "Extracted"

    def test_set_invalid_status_raises(self, tmp_db, sample_pdf):
        doc_id = tmp_db.add_document(sample_pdf, "application/pdf", store=False)
        with pytest.raises(ValueError):
            tmp_db.set_status(doc_id, "Unknown")

    def test_status_log_records_transition(self, tmp_db, sample_pdf):
        doc_id = tmp_db.add_document(sample_pdf, "application/pdf", store=False)
        tmp_db.set_status(doc_id, "Extracted")
        tmp_db.set_status(doc_id, "Needs Review")
        log = tmp_db.get_status_log(doc_id)
        statuses = [entry["new_status"] for entry in log]
        assert "New" in statuses
        assert "Extracted" in statuses
        assert "Needs Review" in statuses

    @pytest.mark.parametrize("status", [
        "New", "Extracted", "Needs Review", "Approved", "Posted", "Error"
    ])
    def test_all_valid_statuses_accepted(self, tmp_db, sample_pdf, status):
        doc_id = tmp_db.add_document(sample_pdf, "application/pdf", store=False)
        tmp_db.set_status(doc_id, status)
        row = tmp_db.get_document(doc_id)
        assert row["status"] == status


# ---------------------------------------------------------------------------
# Extractions
# ---------------------------------------------------------------------------

class TestExtractions:
    def _make_result(self):
        from ai import ExtractionResult
        return ExtractionResult(
            vendor="ACME Corp",
            doc_type="invoice",
            invoice_number="INV-001",
            doc_date="2025-01-15",
            due_date="2025-02-15",
            subtotal=1000.0,
            tax=80.0,
            total=1080.0,
            currency="USD",
            notes="Net 30",
            line_items=[{"description": "Consulting", "qty": 10, "unit_price": 100.0, "amount": 1000.0}],
            confidence=0.92,
            raw_response='{"vendor": "ACME Corp"}',
        )

    def test_save_extraction_returns_id(self, tmp_db, sample_pdf):
        doc_id = tmp_db.add_document(sample_pdf, "application/pdf", store=False)
        result = self._make_result()
        ex_id = tmp_db.save_extraction(doc_id, result)
        assert isinstance(ex_id, int) and ex_id > 0

    def test_get_latest_extraction_fields(self, tmp_db, sample_pdf):
        doc_id = tmp_db.add_document(sample_pdf, "application/pdf", store=False)
        result = self._make_result()
        tmp_db.save_extraction(doc_id, result)
        row = tmp_db.get_latest_extraction(doc_id)
        assert row["vendor"] == "ACME Corp"
        assert row["total"] == pytest.approx(1080.0)
        assert row["confidence"] == pytest.approx(0.92)

    def test_latest_extraction_returns_most_recent(self, tmp_db, sample_pdf):
        doc_id = tmp_db.add_document(sample_pdf, "application/pdf", store=False)
        r1 = self._make_result()
        r2 = self._make_result()
        r2.vendor = "Newer Corp"
        tmp_db.save_extraction(doc_id, r1)
        tmp_db.save_extraction(doc_id, r2)
        row = tmp_db.get_latest_extraction(doc_id)
        assert row["vendor"] == "Newer Corp"

    def test_no_extraction_returns_none(self, tmp_db, sample_pdf):
        doc_id = tmp_db.add_document(sample_pdf, "application/pdf", store=False)
        assert tmp_db.get_latest_extraction(doc_id) is None


# ---------------------------------------------------------------------------
# Approved values
# ---------------------------------------------------------------------------

class TestApprovedValues:
    def test_save_approved_values(self, tmp_db, sample_pdf):
        doc_id = tmp_db.add_document(sample_pdf, "application/pdf", store=False)
        values = {
            "vendor": "ACME",
            "doc_type": "invoice",
            "invoice_number": "INV-1",
            "doc_date": "2025-01-01",
            "due_date": "2025-02-01",
            "subtotal": 500.0,
            "tax": 40.0,
            "total": 540.0,
            "currency": "USD",
            "notes": "Approved",
            "coa_account": "6100 – Rent Expense",
            "tax_category": "Business Expense",
        }
        tmp_db.save_approved(doc_id, values)
        row = tmp_db.get_approved(doc_id)
        assert row["vendor"] == "ACME"
        assert row["total"] == pytest.approx(540.0)
        assert row["coa_account"] == "6100 – Rent Expense"

    def test_upsert_approved_updates_existing(self, tmp_db, sample_pdf):
        doc_id = tmp_db.add_document(sample_pdf, "application/pdf", store=False)
        tmp_db.save_approved(doc_id, {"vendor": "Old Corp", "total": 100.0})
        tmp_db.save_approved(doc_id, {"vendor": "New Corp", "total": 200.0})
        row = tmp_db.get_approved(doc_id)
        assert row["vendor"] == "New Corp"

    def test_no_approved_returns_none(self, tmp_db, sample_pdf):
        doc_id = tmp_db.add_document(sample_pdf, "application/pdf", store=False)
        assert tmp_db.get_approved(doc_id) is None


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

class TestContextManager:
    def test_context_manager(self, tmp_path):
        db_path = str(tmp_path / "cm.db")
        with DocumentDatabase(db_path=db_path) as db:
            assert db._conn is not None

    def test_file_hash_is_deterministic(self, tmp_path):
        f = tmp_path / "sample.txt"
        f.write_bytes(b"hello world")
        h1 = _file_hash(f)
        h2 = _file_hash(f)
        assert h1 == h2
        assert len(h1) == 64
