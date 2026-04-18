"""Shared HTML layout for invoice print / PDF (trucking-style grid, black & white).

Plain-text inputs are escaped. Used by :class:`desktop_app.invoice_screen.InvoiceScreen` (Print)
and :func:`desktop_app.invoice_pdf.save_invoice_pdf` (programmatic PDF to a known path).
This module does not open dialogs.
"""

from __future__ import annotations

from probooksai.html_escape import escape_html_text as _he

# Body rows (excluding header): at least this many for a printable blank grid.
DEFAULT_MIN_LINE_ROWS = 18


def parse_invoice_line_description(raw: str) -> tuple[str, str, str, str]:
    """Split stored ``invoice_lines.description`` (em-dash joined segments) into grid fields."""
    raw = (raw or "").strip()
    if not raw:
        return "", "", "", ""
    if " — " not in raw:
        return "", "", raw, ""
    parts = [p.strip() for p in raw.split(" — ")]
    if len(parts) == 2:
        return parts[0], parts[1], "", ""
    if len(parts) == 3:
        return parts[0], parts[1], parts[2], ""
    return parts[0], parts[1], parts[2], parts[3]


def parse_invoice_memo_po_job_footer(memo: str) -> tuple[str, str, str]:
    """Extract PO, Job, and remaining memo lines (footer notes) from stored invoice memo."""
    po, job = "", ""
    extras: list[str] = []
    for line in (memo or "").splitlines():
        if line.startswith("PO: "):
            po = line[4:].strip()
        elif line.startswith("Job: "):
            job = line[5:].strip()
        elif line.strip():
            extras.append(line.rstrip())
    return po, job, "\n".join(extras)


def _bill_to_html(plain: str) -> str:
    t = (plain or "").strip()
    if not t:
        return "&#160;"
    return _he(t).replace("\n", "<br/>")


def _company_html(plain: str) -> str:
    t = (plain or "").strip()
    if not t:
        return "&#160;"
    return _he(t).replace("\n", "<br/>")


def _company_identity_labeled_html(
    *,
    company_name: str,
    company_address: str,
    company_phone: str,
    company_email: str,
    company_tax_id: str = "",
) -> str:
    """Labeled company file block for print/PDF (empty fields show an em dash, not a blank box)."""

    def _field_label(text: str, *, first: bool = False) -> str:
        mt = "0" if first else "10px"
        return (
            f'<div style="font-weight:bold; font-size:9pt; margin-top:{mt}; '
            f'color:#000;">{_he(text)}</div>'
        )

    def _field_value_plain(single: str) -> str:
        t = (single or "").strip()
        if not t:
            return '<span style="color:#555;">—</span>'
        return _he(t)

    def _field_value_multiline(block: str) -> str:
        t = (block or "").strip()
        if not t:
            return '<span style="color:#555;">—</span>'
        return _he(t).replace("\n", "<br/>")

    parts: list[str] = [
        _field_label("Company Name", first=True),
        f'<div style="padding:2px 0 0 0;">{_field_value_plain(company_name)}</div>',
        _field_label("Address"),
        f'<div style="padding:2px 0 0 0;">{_field_value_multiline(company_address)}</div>',
        _field_label("Phone"),
        f'<div style="padding:2px 0 0 0;">{_field_value_plain(company_phone)}</div>',
        _field_label("Email"),
        f'<div style="padding:2px 0 0 0;">{_field_value_plain(company_email)}</div>',
    ]
    if (company_tax_id or "").strip():
        parts.extend(
            [
                _field_label("Tax ID"),
                f'<div style="padding:2px 0 0 0;">{_field_value_plain(company_tax_id)}</div>',
            ]
        )
    return "".join(parts)


def _footer_html(plain: str) -> str:
    t = (plain or "").strip()
    if not t:
        return "&#160;"
    return _he(t).replace("\n", "<br/>")


def build_invoice_print_html(
    *,
    company_name: str = "",
    company_address: str = "",
    company_phone: str = "",
    company_email: str = "",
    company_tax_id: str = "",
    invoice_date: str = "",
    invoice_number: str = "",
    bill_to_plain: str = "",
    po_contract: str = "",
    name_job: str = "",
    footer_plain: str = "",
    line_rows: list[tuple[str, str, str, str, str, str, str]] | None = None,
    balance_due_plain: str = "",
    min_body_rows: int = DEFAULT_MIN_LINE_ROWS,
) -> str:
    """
    Trucking-style invoice layout for QTextDocument print/PDF.

    **Header (above the line grid):** **Left** — invoice title, date, invoice #, PO/contract, name/job.
    **Right** — company file identity (labeled: name, address, phone, email) and Bill To.

    ``line_rows`` tuples are
    ``(serviced_on, jl_num, description, bol, rate, qty, amount)`` — caller supplies
    display strings (already formatted numbers where needed).
    """
    rows = list(line_rows or [])
    n = max(len(rows), max(0, min_body_rows))
    body_html: list[str] = []
    for i in range(n):
        if i < len(rows):
            so, jl, desc, bol, rate, qty, amt = rows[i]
            cells = [
                _he(so.strip()),
                _he(jl.strip()),
                _he(desc.strip()),
                _he(bol.strip()),
                _he(rate.strip()),
                _he(qty.strip()),
                _he(amt.strip()),
            ]
        else:
            cells = ["&#160;"] * 7
        body_html.append(
            "<tr>"
            + "".join(
                f'<td style="text-align:left; vertical-align:top;">{c}</td>'
                if j < 4
                else f'<td style="text-align:right; vertical-align:top;">{c}</td>'
                for j, c in enumerate(cells)
            )
            + "</tr>"
        )

    inv_d = _he((invoice_date or "").strip()) or "&#160;"
    inv_n = _he((invoice_number or "").strip()) or "&#160;"
    po = _he((po_contract or "").strip()) or "&#160;"
    nj = _he((name_job or "").strip()) or "&#160;"
    bal = _he((balance_due_plain or "").strip()) or "&#160;"

    parts = [
        "<html><head><meta charset=\"utf-8\"/></head><body "
        "style=\"margin:0.4in; font-family: Arial, Helvetica, sans-serif; "
        "font-size:10pt; color:#000;\">",
        # Top: LEFT = invoice title / date / # / PO / job; RIGHT = company file identity + Bill To
        "<table width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" style=\"border:none;\">",
        "<tr>",
        '<td width="50%" valign="top" style="border:none; padding:0 12px 0 0;">',
        '<div style="font-size:20pt; font-weight:bold; text-align:left; letter-spacing:0.02em; margin-bottom:8px;">'
        "Invoice</div>",
        '<table width="100%" cellspacing="0" cellpadding="5" '
        'style="border:2px solid #000; border-collapse:collapse;">',
        "<tr>",
        '<th style="text-align:center; font-weight:bold; border:1px solid #000; width:50%;">Date</th>',
        '<th style="text-align:center; font-weight:bold; border:1px solid #000; width:50%;">'
        "Invoice #</th>",
        "</tr>",
        "<tr>",
        f'<td style="text-align:center; border:1px solid #000;">{inv_d}</td>',
        f'<td style="text-align:center; border:1px solid #000;">{inv_n}</td>',
        "</tr>",
        "</table>",
        '<table width="100%" cellspacing="0" cellpadding="0" '
        'style="border:2px solid #000; border-collapse:collapse; margin-top:10px;">',
        "<tr>",
        '<th style="text-align:center; font-weight:bold; padding:5px; border:1px solid #000; width:50%;">'
        "PO/CONTRACT#</th>",
        '<th style="text-align:center; font-weight:bold; padding:5px; border:1px solid #000; width:50%;">'
        "NAME/JOB#</th>",
        "</tr>",
        "<tr>",
        f'<td valign="top" style="padding:8px; border:1px solid #000;">{po}</td>',
        f'<td valign="top" style="padding:8px; border:1px solid #000;">{nj}</td>',
        "</tr>",
        "</table>",
        "</td>",
        '<td width="50%" valign="top" style="border:none; padding:0 0 0 4px;">',
        '<table width="100%" cellspacing="0" cellpadding="8" '
        'style="border:1px solid #000; border-collapse:collapse;">',
        '<tr><th style="text-align:left; padding:5px 8px; font-weight:bold; border-bottom:1px solid #000;">'
        "COMPANY</th></tr>",
        "<tr><td valign=\"top\" style=\"min-height:72px; padding:8px;\">"
        + _company_identity_labeled_html(
            company_name=company_name,
            company_address=company_address,
            company_phone=company_phone,
            company_email=company_email,
            company_tax_id=company_tax_id,
        )
        + "</td></tr>",
        "</table>",
        '<table width="100%" cellspacing="0" cellpadding="0" '
        'style="border:1px solid #000; border-collapse:collapse; margin-top:10px;">',
        '<tr><th style="text-align:left; padding:5px 8px; font-weight:bold; border-bottom:1px solid #000;">'
        "BILL TO</th></tr>",
        '<tr><td valign="top" style="padding:8px; min-height:64px;">'
        f"{_bill_to_html(bill_to_plain)}</td></tr>",
        "</table>",
        "</td>",
        "</tr>",
        "</table>",
        # Line grid
        '<table width="100%" cellspacing="0" cellpadding="4" '
        'style="border-collapse:collapse; margin-top:12px; border:1px solid #000;">',
        "<thead><tr>",
        '<th style="text-align:center; font-weight:bold; border:1px solid #000;">Serviced On</th>',
        '<th style="text-align:center; font-weight:bold; border:1px solid #000;">JL #</th>',
        '<th style="text-align:center; font-weight:bold; border:1px solid #000;">Description</th>',
        '<th style="text-align:center; font-weight:bold; border:1px solid #000;">BOL#</th>',
        '<th style="text-align:center; font-weight:bold; border:1px solid #000;">Rate</th>',
        '<th style="text-align:center; font-weight:bold; border:1px solid #000;">Quantity</th>',
        '<th style="text-align:center; font-weight:bold; border:1px solid #000;">Amount</th>',
        "</tr></thead><tbody>",
        *body_html,
        # Balance due (right block under numeric columns)
        "<tr>",
        '<td colspan="4" style="border:1px solid #000; border-top:2px solid #000;">&#160;</td>',
        '<td colspan="3" style="border:2px solid #000; padding:10px 12px; '
        'border-top:2px solid #000; vertical-align:middle;">',
        '<table width="100%" cellspacing="0" cellpadding="0" style="border:none;">',
        "<tr>",
        '<td style="border:none; font-size:13pt; font-weight:bold;">Balance Due</td>',
        f'<td style="border:none; font-size:13pt; font-weight:bold; text-align:right;">{bal}</td>',
        "</tr>",
        "</table>",
        "</td>",
        "</tr>",
        "</tbody></table>",
        # Footer
        '<table width="100%" cellspacing="0" cellpadding="0" style="border:none; margin-top:16px;">',
        '<tr><td valign="top" style="border:none; min-height:36px; padding:4px 0;">'
        f"{_footer_html(footer_plain)}</td></tr>",
        "</table>",
        "</body></html>",
    ]
    return "".join(parts)
