"""Invoice print HTML layout helpers."""

from __future__ import annotations

from desktop_app.invoice_print_html import (
    build_invoice_print_html,
    parse_invoice_line_description,
    parse_invoice_memo_po_job_footer,
)


def test_parse_invoice_line_description_segments() -> None:
    assert parse_invoice_line_description("") == ("", "", "", "")
    assert parse_invoice_line_description("  ") == ("", "", "", "")
    assert parse_invoice_line_description("Widget only") == ("", "", "Widget only", "")
    assert parse_invoice_line_description("1/1/26 — ABC") == ("1/1/26", "ABC", "", "")
    assert parse_invoice_line_description("d — c — x") == ("d", "c", "x", "")
    assert parse_invoice_line_description("d — c — x — BOL1") == ("d", "c", "x", "BOL1")


def test_parse_invoice_memo_po_job_footer() -> None:
    assert parse_invoice_memo_po_job_footer("") == ("", "", "")
    po, job, foot = parse_invoice_memo_po_job_footer("PO: P1\nJob: J1\nThanks")
    assert po == "P1" and job == "J1" and foot == "Thanks"


def test_build_invoice_print_html_structure_and_escaping() -> None:
    html = build_invoice_print_html(
        company_block_plain="Widget LLC\n1 Main St\nPhone: 555-0100\nEmail: a@b.co",
        invoice_date="01/02/2026",
        invoice_number="99",
        bill_to_plain="A & B\nLine",
        po_contract="PO1",
        name_job="J1",
        footer_plain="Note <tag>",
        line_rows=[("d", "jl", "desc & co", "b", "1.00", "2.00", "2.00")],
        balance_due_plain="$3.00",
        min_body_rows=2,
    )
    assert "Serviced On" in html
    assert "JL #" in html
    assert "BOL#" in html
    assert "PO/CONTRACT#" in html
    assert "NAME/JOB#" in html
    assert "Balance Due" in html
    assert "BILL TO" in html
    assert "COMPANY" in html
    assert "Widget LLC" in html
    assert "A &amp; B" in html
    assert "Note &lt;tag&gt;" in html
    assert "desc &amp; co" in html
    assert "<tag>" not in html
    # Padded blank row when min_body_rows > data rows
    assert html.count("<tr>") >= 4
