"""invoice_intake_file_extract — PDF text layer and image OCR entrypoints."""

from __future__ import annotations

from unittest.mock import patch

from desktop_app.invoice_intake_file_extract import (
    extract_text_for_intake_kind,
    extract_text_from_intake_pdf,
)


def test_extract_text_from_intake_pdf_missing_file(tmp_path) -> None:
    missing = tmp_path / "nope.pdf"
    text, note = extract_text_from_intake_pdf(str(missing))
    assert text == ""
    assert note is not None and "not found" in note.lower()


def test_extract_text_for_intake_kind_dispatches_pdf(tmp_path) -> None:
    p = tmp_path / "a.pdf"
    p.write_bytes(b"%PDF-1.4")
    with patch("desktop_app.invoice_intake_file_extract.extract_text_from_intake_pdf") as m:
        m.return_value = ("hello", None)
        t, n = extract_text_for_intake_kind("PDF", str(p))
        assert t == "hello" and n is None
        m.assert_called_once_with(str(p))


def test_extract_text_for_intake_kind_unknown_kind(tmp_path) -> None:
    t, n = extract_text_for_intake_kind("Other", str(tmp_path / "x"))
    assert t == "" and n is None
