"""Phase 7 – digital PDF text-layer extraction (``pypdf``; no OCR)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pypdf")

from pypdf import PdfWriter

from probooksai.statement_extract import parse_statement_text
from probooksai.statement_pdf import extract_text_from_pdf

# Synthetic text-layer PDF (regenerate via ``scripts/generate_issue_11_fixture_pdf.py``).
_ISSUE_11_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "issue_11_chase_statement.pdf"
)


def test_extract_text_from_pdf_blank_page_returns_empty_string(tmp_path: Path) -> None:
    """Blank pages yield no extractable text (regression for :func:`extract_text_from_pdf`)."""
    path = tmp_path / "blank.pdf"
    w = PdfWriter()
    w.add_blank_page(width=72, height=72)
    with path.open("wb") as f:
        w.write(f)
    assert extract_text_from_pdf(str(path)) == ""


def test_extract_text_from_pdf_multi_blank_pages_joins_with_newlines(tmp_path: Path) -> None:
    """Multiple blank pages concatenate (still no text); guards the page loop in ``extract_text_from_pdf``."""
    path = tmp_path / "blank2.pdf"
    w = PdfWriter()
    w.add_blank_page(width=72, height=72)
    w.add_blank_page(width=72, height=72)
    with path.open("wb") as f:
        w.write(f)
    assert extract_text_from_pdf(str(path)) == ""


def test_phase7_issue_11_fixture_when_present_has_extractable_text() -> None:
    """Fixture PDF (synthetic stand-in for Issue #11) must extract and parse at least one row."""
    if not _ISSUE_11_FIXTURE.is_file():
        pytest.skip(
            "Add tests/fixtures/issue_11_chase_statement.pdf "
            "(run scripts/generate_issue_11_fixture_pdf.py, or add a redacted digital PDF; "
            "GitHub Issue #11 / ROADMAP Phase 7)."
        )
    text = extract_text_from_pdf(str(_ISSUE_11_FIXTURE))
    assert text.strip(), "Fixture PDF should include a text layer for this assertion"
    rows = parse_statement_text(text)
    assert len(rows) >= 1
    assert rows[0]["txn_date"] == "2024-01-05"
    assert rows[0]["amount"] == -4.5


@pytest.mark.skip(
    reason=(
        "Phase 7 OCR/vision: enable when pipeline exists; Chase reference is GitHub Issue #11 "
        "(ROADMAP Phase 7 definition of done)."
    ),
)
def test_phase7_issue_11_ocr_end_to_end_placeholder() -> None:
    """Reserved for parse rows from vision output on the Issue #11 reference (not text-layer PDF)."""
