"""
Tests for AI extraction result parsing and validation.
Cloud API calls are mocked; no real network requests are made.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from ai import ExtractionResult


# ---------------------------------------------------------------------------
# ExtractionResult dataclass
# ---------------------------------------------------------------------------

class TestExtractionResult:
    def test_default_currency_is_usd(self):
        r = ExtractionResult()
        assert r.currency == "USD"

    def test_default_confidence_is_zero(self):
        r = ExtractionResult()
        assert r.confidence == 0.0

    def test_default_line_items_is_empty_list(self):
        r = ExtractionResult()
        assert r.line_items == []

    def test_fields_set_correctly(self):
        r = ExtractionResult(
            vendor="ACME",
            doc_type="invoice",
            invoice_number="INV-100",
            doc_date="2025-01-01",
            due_date="2025-02-01",
            subtotal=1000.0,
            tax=80.0,
            total=1080.0,
            currency="USD",
            confidence=0.95,
        )
        assert r.vendor == "ACME"
        assert r.total == 1080.0
        assert r.confidence == 0.95

    def test_error_field(self):
        r = ExtractionResult(error="API key missing")
        assert r.error == "API key missing"
        assert r.vendor is None


# ---------------------------------------------------------------------------
# _parse_response helper
# ---------------------------------------------------------------------------

class TestParseResponse:
    def test_parse_clean_json(self):
        from ai.extractor import _parse_response
        raw = '{"vendor": "ACME", "total": 500.0}'
        data = _parse_response(raw)
        assert data["vendor"] == "ACME"
        assert data["total"] == 500.0

    def test_parse_strips_markdown_fences(self):
        from ai.extractor import _parse_response
        raw = '```json\n{"vendor": "Test"}\n```'
        data = _parse_response(raw)
        assert data["vendor"] == "Test"

    def test_parse_strips_markdown_without_language_tag(self):
        from ai.extractor import _parse_response
        raw = '```\n{"vendor": "Test2"}\n```'
        data = _parse_response(raw)
        assert data["vendor"] == "Test2"

    def test_parse_invalid_json_raises(self):
        from ai.extractor import _parse_response
        with pytest.raises(json.JSONDecodeError):
            _parse_response("not valid json")


# ---------------------------------------------------------------------------
# _to_float helper
# ---------------------------------------------------------------------------

class TestToFloat:
    def test_none_returns_none(self):
        from ai.extractor import _to_float
        assert _to_float(None) is None

    def test_int_converts(self):
        from ai.extractor import _to_float
        assert _to_float(42) == pytest.approx(42.0)

    def test_string_converts(self):
        from ai.extractor import _to_float
        assert _to_float("3.14") == pytest.approx(3.14)

    def test_invalid_string_returns_none(self):
        from ai.extractor import _to_float
        assert _to_float("not-a-number") is None


# ---------------------------------------------------------------------------
# extract_document – mocked API calls
# ---------------------------------------------------------------------------

_GOOD_RESPONSE = json.dumps({
    "vendor": "Office Depot",
    "doc_type": "invoice",
    "invoice_number": "OD-12345",
    "doc_date": "2025-03-01",
    "due_date": "2025-03-31",
    "subtotal": 250.00,
    "tax": 20.00,
    "total": 270.00,
    "currency": "USD",
    "notes": "Net 30",
    "line_items": [
        {"description": "Office Supplies", "qty": 5, "unit_price": 50.0, "amount": 250.0}
    ],
    "confidence": 0.93,
})


class TestExtractDocument:
    def _mock_openai_response(self, content: str):
        """Build a mock OpenAI-style response object."""
        choice = MagicMock()
        choice.message.content = content
        response = MagicMock()
        response.choices = [choice]
        return response

    @patch("ai.extractor._call_openai")
    def test_extract_text_pdf(self, mock_call, tmp_path):
        """PDF with extractable text – sends text content to AI."""
        mock_call.return_value = _GOOD_RESPONSE

        # Create a minimal text-based PDF (we mock the text extraction too)
        pdf_path = str(tmp_path / "invoice.pdf")
        Path = __import__("pathlib").Path
        Path(pdf_path).write_bytes(b"%PDF-1.4\n")

        with patch("ai.extractor._pdf_to_text", return_value="Invoice text content"):
            from ai.extractor import extract_document
            result = extract_document(pdf_path, "application/pdf")

        assert result.vendor == "Office Depot"
        assert result.total == pytest.approx(270.0)
        assert result.confidence == pytest.approx(0.93)
        assert result.error is None

    @patch("ai.extractor._call_openai")
    def test_extract_image(self, mock_call, tmp_path):
        """Image file – encodes to data URL and sends to vision model."""
        import struct, zlib
        mock_call.return_value = _GOOD_RESPONSE

        def png_chunk(name, data):
            crc = zlib.crc32(name + data) & 0xFFFFFFFF
            return struct.pack(">I", len(data)) + name + data + struct.pack(">I", crc)

        header = b"\x89PNG\r\n\x1a\n"
        ihdr   = png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        raw    = b"\x00\xff\xff\xff"
        idat   = png_chunk(b"IDAT", zlib.compress(raw))
        iend   = png_chunk(b"IEND", b"")
        img_path = str(tmp_path / "receipt.png")
        __import__("pathlib").Path(img_path).write_bytes(header + ihdr + idat + iend)

        from ai.extractor import extract_document
        result = extract_document(img_path, "image/png")

        assert result.vendor == "Office Depot"
        assert result.error is None

    @patch("ai.extractor._call_openai")
    def test_extract_sets_line_items(self, mock_call, tmp_path):
        mock_call.return_value = _GOOD_RESPONSE
        pdf_path = str(tmp_path / "inv.pdf")
        __import__("pathlib").Path(pdf_path).write_bytes(b"%PDF-1.4\n")
        with patch("ai.extractor._pdf_to_text", return_value="text"):
            from ai.extractor import extract_document
            result = extract_document(pdf_path, "application/pdf")
        assert len(result.line_items) == 1
        assert result.line_items[0]["description"] == "Office Supplies"

    def test_unsupported_mimetype_returns_error(self, tmp_path):
        f = tmp_path / "doc.docx"
        f.write_bytes(b"fake docx")
        from ai.extractor import extract_document
        result = extract_document(str(f), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        assert result.error is not None

    @patch("ai.extractor._call_openai")
    def test_api_error_captured_in_result(self, mock_call, tmp_path):
        mock_call.side_effect = RuntimeError("API rate limit exceeded")
        pdf_path = str(tmp_path / "inv.pdf")
        __import__("pathlib").Path(pdf_path).write_bytes(b"%PDF-1.4\n")
        with patch("ai.extractor._pdf_to_text", return_value="text"):
            from ai.extractor import extract_document
            result = extract_document(pdf_path, "application/pdf")
        assert result.error is not None
        assert "rate limit" in result.error.lower()

    @patch("ai.extractor._call_openai")
    def test_malformed_json_captured_in_result(self, mock_call, tmp_path):
        mock_call.return_value = "This is not JSON at all"
        pdf_path = str(tmp_path / "inv.pdf")
        __import__("pathlib").Path(pdf_path).write_bytes(b"%PDF-1.4\n")
        with patch("ai.extractor._pdf_to_text", return_value="text"):
            from ai.extractor import extract_document
            result = extract_document(pdf_path, "application/pdf")
        assert result.error is not None


# ---------------------------------------------------------------------------
# Missing API key
# ---------------------------------------------------------------------------

class TestMissingAPIKey:
    def test_missing_key_returns_error(self, tmp_path, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        pdf_path = str(tmp_path / "inv.pdf")
        __import__("pathlib").Path(pdf_path).write_bytes(b"%PDF-1.4\n")
        with patch("ai.extractor._pdf_to_text", return_value="text"):
            from ai.extractor import extract_document
            result = extract_document(pdf_path, "application/pdf")
        assert result.error is not None
