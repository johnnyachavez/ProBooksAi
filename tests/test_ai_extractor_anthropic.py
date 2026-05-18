"""
Tests for the Anthropic (Claude) extraction path in ai.extractor.
All Anthropic API calls are mocked — no network requests are made.
The 'anthropic' package need not be installed; tests inject a stub module.
"""

from __future__ import annotations

import json
import struct
import sys
import zlib
from pathlib import Path
from unittest.mock import MagicMock, patch


def _stub_anthropic_module() -> MagicMock:
    """Return a minimal MagicMock that stands in for the anthropic package."""
    stub = MagicMock()
    stub.__name__ = "anthropic"
    return stub

import pytest

from ai import ExtractionResult

_GOOD_RESPONSE = json.dumps({
    "vendor": "Acme Corp",
    "doc_type": "bill",
    "invoice_number": "BILL-9001",
    "doc_date": "2025-04-15",
    "due_date": "2025-05-15",
    "subtotal": 500.00,
    "tax": 40.00,
    "total": 540.00,
    "currency": "USD",
    "notes": "Net 30",
    "line_items": [
        {"description": "Consulting", "qty": 5, "unit_price": 100.0, "amount": 500.0}
    ],
    "confidence": 0.97,
})


def _make_png(tmp_path) -> str:
    """Write a minimal valid PNG and return its path."""
    def chunk(name, data):
        crc = zlib.crc32(name + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", crc)

    header = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    idat = chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff"))
    iend = chunk(b"IEND", b"")
    p = tmp_path / "receipt.png"
    p.write_bytes(header + ihdr + idat + iend)
    return str(p)


def _make_pdf(tmp_path) -> str:
    p = tmp_path / "invoice.pdf"
    p.write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n")
    return str(p)


def _mock_anthropic_message(text: str):
    """Return a mock Anthropic messages response."""
    content_block = MagicMock()
    content_block.text = text
    msg = MagicMock()
    msg.content = [content_block]
    return msg


# ---------------------------------------------------------------------------
# Provider routing
# ---------------------------------------------------------------------------

class TestProviderRouting:
    def test_unsupported_provider_returns_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "gemini")
        p = _make_pdf(tmp_path)
        from ai.extractor import extract_document
        result = extract_document(p, "application/pdf")
        assert result.error is not None
        assert "AI_PROVIDER" in result.error

    def test_openai_provider_still_works(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "openai")
        p = _make_pdf(tmp_path)
        with patch("ai.extractor._call_openai", return_value=_GOOD_RESPONSE), \
             patch("ai.extractor._pdf_to_text", return_value="invoice text"):
            from ai.extractor import extract_document
            result = extract_document(p, "application/pdf")
        assert result.error is None
        assert result.vendor == "Acme Corp"


# ---------------------------------------------------------------------------
# Anthropic – missing key
# ---------------------------------------------------------------------------

class TestAnthropicMissingKey:
    def test_missing_anthropic_key_returns_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "anthropic")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        p = _make_pdf(tmp_path)
        with patch.dict(sys.modules, {"anthropic": _stub_anthropic_module()}):
            from ai.extractor import extract_document
            result = extract_document(p, "application/pdf")
        assert result.error is not None

    def test_missing_anthropic_key_image_returns_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "anthropic")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        p = _make_png(tmp_path)
        with patch.dict(sys.modules, {"anthropic": _stub_anthropic_module()}):
            from ai.extractor import extract_document
            result = extract_document(p, "image/png")
        assert result.error is not None


# ---------------------------------------------------------------------------
# Anthropic – PDF extraction
# ---------------------------------------------------------------------------

class TestAnthropicPDFExtraction:
    @patch("ai.extractor._call_anthropic", return_value=_GOOD_RESPONSE)
    def test_extract_pdf_returns_correct_fields(self, mock_call, tmp_path, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        p = _make_pdf(tmp_path)
        from ai.extractor import extract_document
        result = extract_document(p, "application/pdf")
        assert result.error is None
        assert result.vendor == "Acme Corp"
        assert result.doc_type == "bill"
        assert result.invoice_number == "BILL-9001"
        assert result.total == pytest.approx(540.0)
        assert result.confidence == pytest.approx(0.97)
        assert len(result.line_items) == 1

    @patch("ai.extractor._call_anthropic", return_value=_GOOD_RESPONSE)
    def test_extract_pdf_calls_anthropic_not_openai(self, mock_call, tmp_path, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        p = _make_pdf(tmp_path)
        with patch("ai.extractor._call_openai") as mock_openai:
            from ai.extractor import extract_document
            extract_document(p, "application/pdf")
        mock_openai.assert_not_called()
        mock_call.assert_called_once()


# ---------------------------------------------------------------------------
# Anthropic – image extraction
# ---------------------------------------------------------------------------

class TestAnthropicImageExtraction:
    @patch("ai.extractor._call_anthropic", return_value=_GOOD_RESPONSE)
    def test_extract_png_returns_correct_fields(self, mock_call, tmp_path, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        p = _make_png(tmp_path)
        from ai.extractor import extract_document
        result = extract_document(p, "image/png")
        assert result.error is None
        assert result.vendor == "Acme Corp"
        assert result.total == pytest.approx(540.0)

    def test_unsupported_mime_returns_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        f = tmp_path / "doc.docx"
        f.write_bytes(b"fake docx")
        from ai.extractor import extract_document
        result = extract_document(str(f), "application/vnd.openxmlformats")
        assert result.error is not None


# ---------------------------------------------------------------------------
# Anthropic – _call_anthropic unit tests (real SDK call mocked)
# ---------------------------------------------------------------------------

class TestCallAnthropicUnit:
    """Unit tests for _call_anthropic — inject stub anthropic module so these
    run whether or not the anthropic package is installed."""

    def _make_stub(self, client: MagicMock) -> MagicMock:
        stub = _stub_anthropic_module()
        stub.Anthropic.return_value = client
        return stub

    def test_pdf_uses_beta_client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        p = _make_pdf(tmp_path)

        mock_client = MagicMock()
        mock_client.beta.messages.create.return_value = _mock_anthropic_message(_GOOD_RESPONSE)
        stub = self._make_stub(mock_client)

        with patch.dict(sys.modules, {"anthropic": stub}):
            from ai.extractor import _call_anthropic
            result = _call_anthropic(str(p), "application/pdf")

        mock_client.beta.messages.create.assert_called_once()
        call_kwargs = mock_client.beta.messages.create.call_args
        assert "pdfs-2024-09-25" in call_kwargs.kwargs.get("betas", [])
        assert result == _GOOD_RESPONSE

    def test_image_uses_standard_client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        p = _make_png(tmp_path)

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_message(_GOOD_RESPONSE)
        stub = self._make_stub(mock_client)

        with patch.dict(sys.modules, {"anthropic": stub}):
            from ai.extractor import _call_anthropic
            result = _call_anthropic(str(p), "image/png")

        mock_client.messages.create.assert_called_once()
        assert result == _GOOD_RESPONSE

    def test_uses_anthropic_model_env_var(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-opus-4-7")
        p = _make_png(tmp_path)

        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_message(_GOOD_RESPONSE)
        stub = self._make_stub(mock_client)

        with patch.dict(sys.modules, {"anthropic": stub}):
            from ai.extractor import _call_anthropic
            _call_anthropic(str(p), "image/png")

        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs.get("model") == "claude-opus-4-7"

    def test_missing_package_raises_runtime_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        p = _make_png(tmp_path)
        # Remove anthropic from sys.modules so the import inside _call_anthropic fails.
        with patch.dict(sys.modules, {"anthropic": None}):
            from ai.extractor import _call_anthropic
            with pytest.raises((RuntimeError, ImportError)):
                _call_anthropic(str(p), "image/png")


# ---------------------------------------------------------------------------
# Anthropic categorizer
# ---------------------------------------------------------------------------

class TestAnthropicCategorizer:
    def test_categorizer_uses_anthropic_text(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

        cat_response = json.dumps({
            "coa_account": "6200",
            "tax_category": "Business Expense",
            "confidence": 0.88,
            "rationale": "Consulting services map to professional fees.",
            "alternatives": [],
        })

        from ai import ExtractionResult
        extracted = ExtractionResult(
            vendor="Acme Corp", doc_type="bill", total=540.0, currency="USD"
        )

        with patch("ai.categorizer._call_anthropic_text", return_value=cat_response):
            from ai.categorizer import suggest_categories
            result = suggest_categories(extracted, [])

        assert result.error is None
        assert result.confidence == pytest.approx(0.88)
        assert result.tax_category == "Business Expense"

    def test_categorizer_unsupported_provider_returns_error(self, monkeypatch):
        monkeypatch.setenv("AI_PROVIDER", "gemini")
        from ai import ExtractionResult
        extracted = ExtractionResult(vendor="X", doc_type="bill", total=1.0)
        from ai.categorizer import suggest_categories
        result = suggest_categories(extracted, [])
        assert result.error is not None
