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


def _company_identity_print_html(
    *,
    company_name: str,
    company_address: str,
    company_phone: str,
    company_email: str,
) -> str:
    """Compact public-facing company block for print/PDF.

    Mirrors :func:`probooksai.company_identity.company_identity_plain_block`:
    name on the first line, address (multi-line preserved), then ``Phone:`` and
    ``Email:`` lines. **Tax ID is intentionally excluded** from the printed/PDF
    output — it remains stored on the company file for internal banking, 1099,
    and tax/reporting workflows but never appears on customer-facing invoices.

    Empty fields are dropped (no em-dash placeholder) so the box stays clean
    when the company file is partially filled in.
    """
    lines: list[str] = []
    name = (company_name or "").strip()
    if name:
        lines.append(_he(name))
    addr = (company_address or "").strip()
    if addr:
        for ln in addr.splitlines():
            ln_stripped = ln.strip()
            if ln_stripped:
                lines.append(_he(ln_stripped))
    phone = (company_phone or "").strip()
    if phone:
        lines.append(f"Phone: {_he(phone)}")
    email = (company_email or "").strip()
    if email:
        lines.append(f"Email: {_he(email)}")
    if not lines:
        return "&#160;"
    return "<br/>".join(lines)


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

    **Header (above the line grid):**

    * **Left** — invoice title at the top; the four boxes
      ``Date`` / ``Invoice #`` / ``PO/CONTRACT#`` / ``NAME/JOB#`` are uniform in
      size and bottom-aligned within the header band so they line up with the
      bottom of the right column.
    * **Right** — Company and Bill To boxes, both rendered with the same width
      and the same height (no visible container titles; borders preserved).
      The Company box uses the compact public-facing block from
      :func:`_company_identity_print_html` — Tax ID is **never** printed.

    ``company_tax_id`` is accepted for source/API compatibility with callers
    that still pass the full identity dict but is intentionally ignored when
    generating the printed output.

    ``line_rows`` tuples are
    ``(serviced_on, jl_num, description, bol, rate, qty, amount)`` — caller supplies
    display strings (already formatted numbers where needed).
    """
    # Tax ID is deliberately unused on customer-facing print/PDF output.
    del company_tax_id
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

    # Header-band box dimensions (px). Picked so that:
    # * Each of the four upper-left boxes (Date / Invoice # / PO/CONTRACT# /
    #   NAME/JOB#) is uniform: same header height, same body height, same width.
    # * Company and Bill To boxes share the same width (each side of the page
    #   table is 50%) and the same body height — together they keep the same
    #   combined footprint the previous layout used.
    # * The four-box block is bottom-aligned within the header band by a top
    #   spacer so its bottom edge meets the bottom of the right-column boxes.
    _BOX_HEADER_H = 22
    _BOX_BODY_H = 50
    _SIDE_BOX_BODY_H = 110
    _SIDE_BOX_GAP = 10
    _LEFT_TOP_SPACER_H = 6

    parts = [
        "<html><head><meta charset=\"utf-8\"/></head><body "
        "style=\"margin:0.4in; font-family: Arial, Helvetica, sans-serif; "
        "font-size:10pt; color:#000;\">",
        # Top: LEFT = invoice title + (spacer) + four uniform boxes (bottom-aligned);
        # RIGHT = Company and Bill To, both same width and same height, no titles.
        "<table width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" style=\"border:none;\">",
        "<tr>",
        '<td width="50%" valign="top" style="border:none; padding:0 12px 0 0;">',
        '<div style="font-size:20pt; font-weight:bold; text-align:left; letter-spacing:0.02em; margin-bottom:8px;">'
        "Invoice</div>",
        # Top spacer pushes the four-box group down so it bottom-aligns with
        # the right column. The four boxes themselves are uniform in size.
        f'<div style="height:{_LEFT_TOP_SPACER_H}px; line-height:{_LEFT_TOP_SPACER_H}px;">&#160;</div>',
        '<table width="100%" cellspacing="0" cellpadding="4" '
        'style="border:2px solid #000; border-collapse:collapse;">',
        "<tr>",
        f'<th style="text-align:center; font-weight:bold; border:1px solid #000; '
        f'width:50%; height:{_BOX_HEADER_H}px;">Date</th>',
        f'<th style="text-align:center; font-weight:bold; border:1px solid #000; '
        f'width:50%; height:{_BOX_HEADER_H}px;">Invoice #</th>',
        "</tr>",
        "<tr>",
        f'<td style="text-align:center; vertical-align:middle; border:1px solid #000; '
        f'height:{_BOX_BODY_H}px;">{inv_d}</td>',
        f'<td style="text-align:center; vertical-align:middle; border:1px solid #000; '
        f'height:{_BOX_BODY_H}px;">{inv_n}</td>',
        "</tr>",
        "</table>",
        '<table width="100%" cellspacing="0" cellpadding="4" '
        'style="border:2px solid #000; border-collapse:collapse; margin-top:10px;">',
        "<tr>",
        f'<th style="text-align:center; font-weight:bold; border:1px solid #000; '
        f'width:50%; height:{_BOX_HEADER_H}px;">PO/CONTRACT#</th>',
        f'<th style="text-align:center; font-weight:bold; border:1px solid #000; '
        f'width:50%; height:{_BOX_HEADER_H}px;">NAME/JOB#</th>',
        "</tr>",
        "<tr>",
        f'<td style="text-align:center; vertical-align:middle; border:1px solid #000; '
        f'height:{_BOX_BODY_H}px;">{po}</td>',
        f'<td style="text-align:center; vertical-align:middle; border:1px solid #000; '
        f'height:{_BOX_BODY_H}px;">{nj}</td>',
        "</tr>",
        "</table>",
        "</td>",
        '<td width="50%" valign="top" style="border:none; padding:0 0 0 4px;">',
        # Company box — no title bar, fixed body height (matches Bill To height
        # exactly so both containers occupy the same footprint).
        '<table width="100%" cellspacing="0" cellpadding="0" '
        'style="border:1px solid #000; border-collapse:collapse;">',
        "<tr>"
        f'<td valign="top" style="padding:10px 12px; height:{_SIDE_BOX_BODY_H}px;">'
        + _company_identity_print_html(
            company_name=company_name,
            company_address=company_address,
            company_phone=company_phone,
            company_email=company_email,
        )
        + "</td></tr>",
        "</table>",
        # Bill To box — no title bar, identical body height to the Company box.
        '<table width="100%" cellspacing="0" cellpadding="0" '
        f'style="border:1px solid #000; border-collapse:collapse; margin-top:{_SIDE_BOX_GAP}px;">',
        "<tr>"
        f'<td valign="top" style="padding:10px 12px; height:{_SIDE_BOX_BODY_H}px;">'
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
