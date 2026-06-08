"""Conservative text extraction for Invoice Intake."""

from __future__ import annotations

from desktop_app.invoice_intake_text_extract import extract_text_intake_fields


def test_extract_labeled_date_ticket_customer_hours_notes() -> None:
    text = """
Date: 3/15/2025
Ticket # ABC-99
Customer: Acme Trucking LLC
Hours: 8.5
Notes: Delivered to gate B. Call if issues.
""".strip()
    ex = extract_text_intake_fields(text)
    assert ex.date_confidence == "high"
    assert ex.date_display == "03/15/2025"
    assert ex.ticket_confidence == "high"
    assert ex.ticket_ref == "ABC-99"
    assert ex.customer_confidence == "high"
    assert "Acme Trucking" in (ex.customer_name or "")
    assert ex.hours_qty_confidence == "high"
    assert "8.5" in (ex.hours_qty_note or "")
    assert ex.notes_confidence == "high"
    assert "gate B" in (ex.notes_from_label or "")
    rt = ex.review_panel_text()
    assert "Likely (high confidence)" in rt
    assert "Not extracted" in rt


def test_extract_invoice_date_label() -> None:
    ex = extract_text_intake_fields("Invoice Date: 2025-01-20\n")
    assert ex.date_confidence == "high"
    assert ex.date_display == "01/20/2025"


def test_extract_solo_iso_line() -> None:
    ex = extract_text_intake_fields("2025-06-01")
    assert ex.date_confidence == "high"


def test_extract_bol_and_ref() -> None:
    ex = extract_text_intake_fields("BOL # 77821\n")
    assert ex.ticket_confidence == "high"
    assert ex.ticket_ref == "77821"
    ex2 = extract_text_intake_fields("Reference: PO-1002\n")
    assert ex2.ticket_confidence == "high"
    assert "PO-1002" in (ex2.ticket_ref or "")


def test_extract_qty_instead_of_hours() -> None:
    ex = extract_text_intake_fields("Qty: 12\n")
    assert ex.hours_qty_confidence == "high"
    assert "12" in (ex.hours_qty_note or "")


def test_extract_does_not_pick_random_numbers_as_ticket() -> None:
    ex = extract_text_intake_fields("Total amount $1,234.56 for services\n")
    assert ex.ticket_confidence == "none"


def test_memo_lines_for_handoff_only_high() -> None:
    text = """
Customer: Zeta Corp
Hours: 2
""".strip()
    ex = extract_text_intake_fields(text)
    ml = ex.memo_lines_for_handoff()
    assert any("Zeta" in m for m in ml)
    assert any("2" in m or "hrs" in m for m in ml)
