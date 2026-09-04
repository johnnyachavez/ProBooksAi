"""Invoice print HTML layout helpers."""

from __future__ import annotations

from desktop_app.invoice_print_html import (
    DEFAULT_TERMS,
    DEFAULT_THANK_YOU,
    build_invoice_print_html,
    compliance_fee_display_fields,
    is_compliance_fee_line,
    parse_invoice_line_description,
    parse_invoice_memo_fields,
    parse_invoice_memo_po_job_footer,
)


def test_parse_invoice_line_description_segments() -> None:
    assert parse_invoice_line_description("") == ("", "", "", "")
    assert parse_invoice_line_description("  ") == ("", "", "", "")
    assert parse_invoice_line_description("Widget only") == ("", "", "Widget only", "")
    assert parse_invoice_line_description("1/1/26 — ABC") == ("1/1/26", "ABC", "", "")
    assert parse_invoice_line_description("FS-1 — FLATBED TRUCKING") == (
        "",
        "FS-1",
        "FLATBED TRUCKING",
        "",
    )
    assert parse_invoice_line_description("CO — Compliance fee") == (
        "",
        "CO",
        "Compliance fee",
        "",
    )
    assert parse_invoice_line_description("d — c — x") == ("d", "c", "x", "")
    assert parse_invoice_line_description("d — c — x — BOL1") == ("d", "c", "x", "BOL1")
    assert parse_invoice_line_description(" — FS-2 — FLATBED LOAD") == (
        "",
        "FS-2",
        "FLATBED LOAD",
        "",
    )


def test_parse_invoice_memo_po_job_footer() -> None:
    assert parse_invoice_memo_po_job_footer("") == ("", "", "")
    po, job, foot = parse_invoice_memo_po_job_footer("PO: P1\nJob: J1\nThanks")
    assert po == "P1" and job == "J1" and foot == "Thanks"


def test_parse_invoice_memo_fields_strips_message() -> None:
    po, job, message, extras = parse_invoice_memo_fields(
        "PO: P1\nJob: J1\nMessage: Thank you for your business.\nInternal"
    )
    assert po == "P1"
    assert job == "J1"
    assert message == "Thank you for your business."
    assert extras == "Internal"
    _po, _job, foot = parse_invoice_memo_po_job_footer(
        "PO: P1\nMessage: Thank you for your business.\nNote"
    )
    assert foot == "Note"


def test_is_compliance_fee_line() -> None:
    assert is_compliance_fee_line("CO", "Compliance fee", "", "")
    assert is_compliance_fee_line("", "CO", "Compliance fee", "")
    assert is_compliance_fee_line("", "FEE", "CA compliance", "")
    assert not is_compliance_fee_line("1/1/26", "4412", "desc & co", "BOL")
    assert not is_compliance_fee_line("", "", "Sand haul", "")
    jl, desc = compliance_fee_display_fields("CO", "Compliance fee", "", "")
    assert jl == "CO" and desc == "Compliance fee"


def test_build_invoice_print_html_structure_and_escaping() -> None:
    html = build_invoice_print_html(
        company_block_plain="Sender & Co.\n123 Road",
        invoice_date="01/02/2026",
        invoice_number="99",
        bill_to_plain="A & B\nLine",
        ship_to_plain="Yard <site>",
        po_contract="PO1",
        name_job="J1",
        footer_plain="Note <tag>",
        line_rows=[("d", "jl", "desc & co", "b", "2.00", "1.00", "2.00")],
        fee_row=("CO", "Compliance fee", "", "3%", "0.06"),
        subtotal_plain="2.00",
        total_plain="$2.06",
        min_body_rows=2,
    )
    assert "Serviced On" in html
    assert "JL#" in html
    assert "BOL#" in html
    so = html.find("Serviced On")
    assert so < html.find(">JL#<") < html.find("Description") < html.find("BOL#")
    assert html.find(">Qty<") < html.find(">Rate<") < html.find("Amount")
    assert "PO" in html
    assert "Job" in html
    assert "CONTRACT" not in html
    assert "Subtotal" in html
    assert ">Total<" in html
    assert "Balance Due" not in html
    assert "Terms:" in html
    assert "NET 30" in html
    assert "INVOICE" in html
    assert "BILL TO" in html
    assert "<img" not in html
    assert "SHIP TO" not in html
    assert "Yard" not in html
    assert "Sender &amp; Co." in html
    assert "123 Road" in html
    assert "A &amp; B" in html
    assert "Note &lt;tag&gt;" in html
    assert "desc &amp; co" in html
    assert "3%" in html
    assert "Compliance fee" in html
    assert "<tag>" not in html
    assert "colgroup" in html
    # Padded blank row when min_body_rows > data rows
    assert html.count("<tr>") >= 4


def test_build_invoice_print_html_default_thank_you_and_phone() -> None:
    html = build_invoice_print_html(
        footer_phone="555-0199",
        min_body_rows=0,
    )
    assert DEFAULT_THANK_YOU in html
    assert "555-0199" in html


def test_build_invoice_print_html_fee_amount_mode() -> None:
    html = build_invoice_print_html(
        fee_row=("CO", "Compliance fee", "1.00", "25.00", "25.00"),
        min_body_rows=0,
    )
    assert "25.00" in html
    assert "Compliance fee" in html


def test_build_invoice_print_html_column_order_qty_before_rate() -> None:
    """Paper template order: Serviced On, JL#, Description, BOL#, Qty, Rate, Amount."""
    html = build_invoice_print_html(min_body_rows=0)
    order = [
        html.index("Serviced On"),
        html.index("JL#"),
        html.index("Description"),
        html.index("BOL#"),
        html.index(">Qty<"),
        html.index(">Rate<"),
        html.index(">Amount<"),
    ]
    assert order == sorted(order)
    assert "Quantity" not in html


def test_build_invoice_print_html_title_terms_and_totals() -> None:
    html = build_invoice_print_html(
        subtotal_plain="100.00",
        total_plain="$103.00",
        min_body_rows=0,
    )
    assert ">INVOICE<" in html
    assert DEFAULT_TERMS == "NET 30"
    assert "Terms: NET 30" in html
    assert "Subtotal" in html
    assert ">Total<" in html
    assert "$103.00" in html
    assert "Balance Due" not in html


def test_build_invoice_print_html_terms_override() -> None:
    html = build_invoice_print_html(terms_plain="DUE ON RECEIPT", min_body_rows=0)
    assert "Terms: DUE ON RECEIPT" in html
    assert "NET 30" not in html
