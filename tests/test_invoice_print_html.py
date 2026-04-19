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
        company_name="Widget LLC",
        company_address="1 Main St",
        company_phone="555-0100",
        company_email="a@b.co",
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
    assert "Date" in html
    assert "Invoice #" in html
    assert "PO/CONTRACT#" in html
    assert "NAME/JOB#" in html
    assert "Balance Due" in html
    # The Company and Bill To container titles ("COMPANY" / "BILL TO") and the
    # per-field labels ("Company Name", "Address", "Phone", "Email") are no
    # longer rendered — values still appear inline (compact public block).
    assert "BILL TO" not in html
    assert "COMPANY" not in html
    assert "Company Name" not in html
    assert "<th" not in html or "Address</" not in html
    assert "Widget LLC" in html
    assert "1 Main St" in html
    assert "Phone: 555-0100" in html
    assert "Email: a@b.co" in html
    assert "A &amp; B" in html
    assert "Note &lt;tag&gt;" in html
    assert "desc &amp; co" in html
    assert "<tag>" not in html
    # Padded blank row when min_body_rows > data rows
    assert html.count("<tr>") >= 4


def test_build_invoice_print_html_omits_tax_id_from_customer_facing_output() -> None:
    """Tax ID stays on the company file but must NEVER print on invoices.

    Verifies the Tax ID label and the literal value are absent from the
    customer-facing print/PDF HTML even when callers pass it through (the
    parameter is preserved for source/API compatibility but ignored on render).
    """
    sentinel_tax_id = "EIN-99-7777777"
    html = build_invoice_print_html(
        company_name="Widget LLC",
        company_address="1 Main St",
        company_phone="555-0100",
        company_email="a@b.co",
        company_tax_id=sentinel_tax_id,
        invoice_date="01/02/2026",
        invoice_number="42",
        bill_to_plain="Customer Co",
        po_contract="",
        name_job="",
        footer_plain="",
        line_rows=[],
        balance_due_plain="$0.00",
        min_body_rows=1,
    )
    assert sentinel_tax_id not in html
    assert "Tax ID" not in html
    assert "tax_id" not in html
    # Other identity fields still render so the company block isn't empty.
    assert "Widget LLC" in html
    assert "Phone: 555-0100" in html


def test_build_invoice_print_html_company_and_bill_to_have_matching_height() -> None:
    """Company and Bill To boxes must share the same width and same height.

    Both containers are rendered with explicit equal pixel heights so they
    occupy identical footprints regardless of how much identity / customer
    text is present.
    """
    html = build_invoice_print_html(
        company_name="Widget LLC",
        company_address="1 Main St\nCity, ST 00000",
        company_phone="555-0100",
        company_email="a@b.co",
        invoice_date="01/02/2026",
        invoice_number="42",
        bill_to_plain="Customer Co",
        po_contract="",
        name_job="",
        footer_plain="",
        line_rows=[],
        balance_due_plain="$0.00",
        min_body_rows=1,
    )
    # The two right-column container body cells share the same explicit height.
    assert html.count('height:110px') >= 2
    # Each of the four upper-left boxes (Date / Invoice # / PO/CONTRACT# /
    # NAME/JOB#) shares the same body height — uniform sizing.
    assert html.count('height:50px') >= 4


def test_build_invoice_print_html_has_no_container_titles() -> None:
    """Company and Bill To container titles are removed; borders remain."""
    html = build_invoice_print_html(
        company_name="Widget LLC",
        company_address="1 Main St",
        company_phone="555-0100",
        company_email="a@b.co",
        invoice_date="01/02/2026",
        invoice_number="42",
        bill_to_plain="Customer Co",
        po_contract="",
        name_job="",
        footer_plain="",
        line_rows=[],
        balance_due_plain="$0.00",
        min_body_rows=1,
    )
    assert "COMPANY</" not in html
    assert "BILL TO</" not in html
    assert "border:1px solid #000" in html
