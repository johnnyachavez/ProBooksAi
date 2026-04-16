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
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    if not lines:
        return "&#160;"
    first = _he(lines[0])
    if len(lines) == 1:
        return (
            '<div style="font-weight:700;font-size:11pt;letter-spacing:0.02em;line-height:1.25;">'
            f"{first}</div>"
        )
    rest = "<br/>".join(_he(x) for x in lines[1:])
    return (
        '<div style="font-weight:700;font-size:11pt;letter-spacing:0.02em;line-height:1.25;">'
        f"{first}</div>"
        '<div style="font-size:10pt;line-height:1.35;margin-top:3px;">'
        f"{rest}</div>"
    )


def _footer_html(plain: str) -> str:
    t = (plain or "").strip()
    if not t:
        return "&#160;"
    return _he(t).replace("\n", "<br/>")


def build_invoice_print_html(
    *,
    company_block_plain: str = "",
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
                f'<td style="text-align:left;vertical-align:top;padding:3px 4px;">{c}</td>'
                if j < 4
                else f'<td style="text-align:right;vertical-align:top;padding:3px 4px;'
                f'font-variant-numeric:tabular-nums;">{c}</td>'
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
        "style=\"margin:0.5in; font-family: Arial, Helvetica, sans-serif; "
        "font-size:10pt; color:#000;\">",
        # Top: company (left) + Invoice title / date / number (right)
        "<table width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" style=\"border:none;\">",
        "<tr>",
        '<td width="55%" valign="top" style="border:none; padding:0 12px 0 0;">',
        '<table width="100%" cellspacing="0" cellpadding="8" '
        'style="border:1px solid #000; border-collapse:collapse;">',
        f'<tr><td valign="top" style="min-height:88px;">{_company_html(company_block_plain)}</td></tr>',
        "</table>",
        "</td>",
        '<td width="45%" valign="top" style="border:none; padding:0;">',
        '<div style="font-size:20pt; font-weight:bold; text-align:right; letter-spacing:0.02em; '
        'line-height:1.1;margin-bottom:6px;">Invoice</div>',
        '<table width="100%" cellspacing="0" cellpadding="0" '
        'style="border:2px solid #000; border-collapse:collapse; margin-top:2px;">',
        "<tr>",
        '<th style="text-align:center; font-weight:bold; border:1px solid #000; width:50%; '
        'background:#f0f0f0; font-size:8pt; padding:4px 6px;">DATE</th>',
        '<th style="text-align:center; font-weight:bold; border:1px solid #000; width:50%; '
        'background:#f0f0f0; font-size:8pt; padding:4px 6px;">INVOICE #</th>',
        "</tr>",
        "<tr>",
        f'<td style="text-align:center; border:1px solid #000; padding:5px 8px;">{inv_d}</td>',
        f'<td style="text-align:center; border:1px solid #000; padding:5px 8px;">{inv_n}</td>',
        "</tr>",
        "</table>",
        "</td>",
        "</tr>",
        "</table>",
        # Bill To + PO / Job
        '<table width="100%" cellspacing="0" cellpadding="0" style="border:none; margin-top:14px;">',
        "<tr>",
        '<td width="50%" valign="top" style="border:none; padding:0;">',
        '<table width="100%" cellspacing="0" cellpadding="0" '
        'style="border:1px solid #000; border-collapse:collapse;">',
        '<tr><th style="text-align:left; padding:5px 8px; font-weight:bold; border-bottom:1px solid #000; '
        'background:#f0f0f0; font-size:8pt;">BILL TO</th></tr>',
        '<tr><td valign="top" style="padding:8px; min-height:72px;line-height:1.35;">'
        f"{_bill_to_html(bill_to_plain)}</td></tr>",
        "</table>",
        "</td>",
        '<td width="2%" style="border:none;">&#160;</td>',
        '<td width="48%" valign="top" style="border:none; padding:0;">',
        '<table width="100%" cellspacing="0" cellpadding="0" '
        'style="border:1px solid #000; border-collapse:collapse;">',
        "<tr>",
        '<th style="text-align:center; font-weight:bold; padding:4px 6px; border:1px solid #000; '
        'width:50%; background:#f0f0f0; font-size:8pt;">PO/CONTRACT#</th>',
        '<th style="text-align:center; font-weight:bold; padding:4px 6px; border:1px solid #000; '
        'width:50%; background:#f0f0f0; font-size:8pt;">NAME/JOB#</th>',
        "</tr>",
        "<tr>",
        f'<td valign="top" style="padding:8px; border:1px solid #000; min-height:44px;">{po}</td>',
        f'<td valign="top" style="padding:8px; border:1px solid #000; min-height:44px;">{nj}</td>',
        "</tr>",
        "</table>",
        "</td>",
        "</tr>",
        "</table>",
        # Line grid (column widths aligned with static invoice.html template)
        '<table width="100%" cellspacing="0" cellpadding="0" '
        'style="border-collapse:collapse; margin-top:14px; border:1px solid #000; '
        'table-layout:fixed;">',
        "<colgroup>",
        '<col style="width:11%;"/><col style="width:9%;"/><col style="width:28%;"/>',
        '<col style="width:11%;"/><col style="width:12%;"/><col style="width:9%;"/>',
        '<col style="width:12%;"/>',
        "</colgroup>",
        "<thead><tr>",
        '<th style="text-align:center; font-weight:bold; border:1px solid #000; background:#f0f0f0; '
        'font-size:8pt; text-transform:uppercase; padding:5px 3px;">Serviced On</th>',
        '<th style="text-align:center; font-weight:bold; border:1px solid #000; background:#f0f0f0; '
        'font-size:8pt; text-transform:uppercase; padding:5px 3px;">JL #</th>',
        '<th style="text-align:center; font-weight:bold; border:1px solid #000; background:#f0f0f0; '
        'font-size:8pt; text-transform:uppercase; padding:5px 3px;">Description</th>',
        '<th style="text-align:center; font-weight:bold; border:1px solid #000; background:#f0f0f0; '
        'font-size:8pt; text-transform:uppercase; padding:5px 3px;">BOL#</th>',
        '<th style="text-align:center; font-weight:bold; border:1px solid #000; background:#f0f0f0; '
        'font-size:8pt; text-transform:uppercase; padding:5px 3px;">Rate</th>',
        '<th style="text-align:center; font-weight:bold; border:1px solid #000; background:#f0f0f0; '
        'font-size:8pt; text-transform:uppercase; padding:5px 3px;">Quantity</th>',
        '<th style="text-align:center; font-weight:bold; border:1px solid #000; background:#f0f0f0; '
        'font-size:8pt; text-transform:uppercase; padding:5px 3px;">Amount</th>',
        "</tr></thead><tbody>",
        *body_html,
        # Balance due — label in column 6, amount in column 7 (matches static template)
        "<tr>",
        '<td colspan="5" style="border:1px solid #000; border-top:2px solid #000;">&#160;</td>',
        '<td style="border:2px solid #000; border-top:2px solid #000; font-weight:700; '
        'text-align:right; text-transform:uppercase; font-size:9pt; padding:8px 6px; '
        'vertical-align:middle;">Balance Due</td>',
        f'<td style="border:2px solid #000; border-top:2px solid #000; font-weight:700; '
        f'text-align:right; font-size:12pt; padding:8px 6px; vertical-align:middle; '
        f'font-variant-numeric:tabular-nums;">{bal}</td>',
        "</tr>",
        "</tbody></table>",
        # Footer
        '<table width="100%" cellspacing="0" cellpadding="0" style="border:none; margin-top:18px;">',
        '<tr><td valign="top" style="border:none; border-top:1px solid #ccc; min-height:32px; '
        'padding:8px 0 4px 0; font-size:9.5pt; line-height:1.35; color:#222;">'
        f"{_footer_html(footer_plain)}</td></tr>",
        "</table>",
        "</body></html>",
    ]
    return "".join(parts)
