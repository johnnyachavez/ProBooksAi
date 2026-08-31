"""Shared HTML layout for invoice print / PDF (Chavan-style grid, black & white).

Plain-text inputs are escaped. Used by :class:`desktop_app.invoice_screen.InvoiceScreen` (Print)
and :func:`desktop_app.invoice_pdf.save_invoice_pdf` (programmatic PDF to a known path).
This module does not open dialogs.

Print and Save PDF share this layout. Ticket images are optional extra pages later
and are not rendered or OCR'd here.

Layout (top → bottom)
----------------------
1. Header: company from My Company (logo or text) | "Invoice" + Date + Invoice #
2. BILL TO (left) | PO/CONTRACT# and NAME/JOB# (right)
3. Line-items grid: Serviced On, JL #, Description, BOL#, Rate, Quantity, Amount
4. Subtotal, then a CO / compliance-fee line (percent or amount)
5. Balance Due
6. Footer: THANK YOU FOR YOUR BUSINESS - JOHNNY and the company phone
"""

from __future__ import annotations

from probooksai.html_escape import escape_html_text as _he

# Body rows (excluding header / totals): at least this many for a printable blank grid.
DEFAULT_MIN_LINE_ROWS = 16

DEFAULT_THANK_YOU = "THANK YOU FOR YOUR BUSINESS - JOHNNY"

_FEE_TOKENS = frozenset({"CO", "C.O.", "C.O", "C/O", "CO."})

_TH = (
    "text-align:center; font-weight:bold; padding:4px 6px; "
    "border:1px solid #000; background:#f0f0f0; font-size:8pt; "
    "text-transform:uppercase;"
)
_META_LABEL = (
    "text-align:left; font-weight:bold; padding:6px 8px; "
    "border:1px solid #000; background:#f0f0f0; font-size:8pt; "
    "text-transform:uppercase; width:48%;"
)
_META_VAL = (
    "text-align:left; border:1px solid #000; padding:6px 8px; "
    "vertical-align:middle;"
)
_GRID_TH = (
    "text-align:center; font-weight:bold; border:1px solid #000; background:#f0f0f0; "
    "font-size:8pt; text-transform:uppercase; padding:5px 3px;"
)
_GRID_TD_L = (
    "text-align:left; vertical-align:top; padding:3px 4px; border:1px solid #000;"
)
_GRID_TD_R = (
    "text-align:right; vertical-align:top; padding:3px 4px; border:1px solid #000; "
    "font-variant-numeric:tabular-nums;"
)


def parse_invoice_line_description(raw: str) -> tuple[str, str, str, str]:
    """Split stored ``invoice_lines.description`` (em-dash joined segments) into grid fields.

    Do not strip the whole string before splitting: a leading ``" — code — desc"``
    (empty Serviced On) would otherwise collapse to two parts and put the code in Date.
    """
    raw = raw or ""
    if " — " not in raw:
        raw = raw.strip()
        if not raw:
            return "", "", "", ""
        return "", "", raw, ""
    parts = [p.strip() for p in raw.split(" — ")]
    if len(parts) == 2:
        return parts[0], parts[1], "", ""
    if len(parts) == 3:
        return parts[0], parts[1], parts[2], ""
    return parts[0], parts[1], parts[2], parts[3]


def parse_invoice_memo_fields(memo: str) -> tuple[str, str, str, str]:
    """Extract PO, Job, customer Message, and remaining memo lines from stored invoice memo."""
    po, job, message = "", "", ""
    extras: list[str] = []
    for line in (memo or "").splitlines():
        if line.startswith("PO: "):
            po = line[4:].strip()
        elif line.startswith("Job: "):
            job = line[5:].strip()
        elif line.startswith("Message: "):
            message = line[9:].strip()
        elif line.strip():
            extras.append(line.rstrip())
    return po, job, message, "\n".join(extras)


def parse_invoice_memo_po_job_footer(memo: str) -> tuple[str, str, str]:
    """Extract PO, Job, and remaining memo lines (not printed as the Chavan footer)."""
    po, job, _message, extras = parse_invoice_memo_fields(memo)
    return po, job, extras


def is_compliance_fee_line(
    serviced_on: str,
    jl_num: str,
    description: str,
    bol: str = "",
) -> bool:
    """True when a line is the CO / compliance-fee row (not a haul line)."""
    parts = (serviced_on, jl_num, description, bol)
    blob = " ".join(parts).upper()
    if "COMPLIANCE" in blob:
        return True
    for p in parts:
        if (p or "").strip().upper() in _FEE_TOKENS:
            return True
    return False


def compliance_fee_display_fields(
    serviced_on: str,
    jl_num: str,
    description: str,
    bol: str = "",
) -> tuple[str, str]:
    """Return ``(jl, description)`` for the fee row, correcting 2-segment parse of ``CO — …``."""
    so = (serviced_on or "").strip()
    jl = (jl_num or "").strip()
    desc = (description or "").strip()
    if so.upper() in _FEE_TOKENS and not desc:
        return so, jl
    if jl.upper() in _FEE_TOKENS:
        return jl, desc or so
    if so.upper() in _FEE_TOKENS:
        return so, desc or jl
    return jl or so, desc or jl or so


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


def _footer_html(plain: str, phone: str = "") -> str:
    lines: list[str] = []
    t = (plain or "").strip()
    if t:
        lines.append(_he(t).replace("\n", "<br/>"))
    ph = (phone or "").strip()
    if ph:
        lines.append(_he(ph))
    if not lines:
        return "&#160;"
    return "<br/>".join(lines)


def _esc_cell(raw: str) -> str:
    t = (raw or "").strip()
    if not t:
        return "&#160;"
    return _he(t).replace("\n", "<br/>")


def _logo_block_html(
    logo_data_uri: str,
    company_block_plain: str,
    logo_display_w: int = 400,
    logo_display_h: int = 180,
) -> str:
    """Return the top-left cell content: logo image (no border) or fallback company text.

    ``logo_display_w`` / ``logo_display_h`` must be explicit pixel integers because
    Qt's QTextDocument HTML renderer does not honour CSS ``max-width`` / ``max-height``
    on ``<img>`` tags — only literal ``width``/``height`` attributes work.
    """
    if logo_data_uri:
        logo_img = (
            f'<img src="{logo_data_uri}" '
            f'width="{logo_display_w}" height="{logo_display_h}" '
            'style="border:none; display:block;" />'
        )
        contact = ""
        if company_block_plain:
            lines = [ln.strip() for ln in company_block_plain.splitlines() if ln.strip()]
            if len(lines) > 1:
                contact_text = "<br/>".join(_he(x) for x in lines[1:])
                contact = (
                    f'<div style="font-size:8.5pt;color:#333;line-height:1.35;margin-top:5px;">'
                    f"{contact_text}</div>"
                )
        return logo_img + contact
    return (
        '<table width="100%" cellspacing="0" cellpadding="8" '
        'style="border:none; border-collapse:collapse;">'
        f'<tr><td valign="top" style="min-height:88px;">{_company_html(company_block_plain)}</td></tr>'
        "</table>"
    )


def _line_tr(cells: list[str]) -> str:
    bits: list[str] = []
    for j, c in enumerate(cells):
        style = _GRID_TD_L if j < 4 else _GRID_TD_R
        bits.append(f'<td style="{style}">{c}</td>')
    return "<tr>" + "".join(bits) + "</tr>"


def build_invoice_print_html(
    *,
    company_block_plain: str = "",
    invoice_date: str = "",
    invoice_number: str = "",
    bill_to_plain: str = "",
    ship_to_plain: str = "",
    po_contract: str = "",
    name_job: str = "",
    footer_plain: str = DEFAULT_THANK_YOU,
    footer_phone: str = "",
    line_rows: list[tuple[str, str, str, str, str, str, str]] | None = None,
    fee_row: tuple[str, str, str, str, str] | None = None,
    subtotal_plain: str = "",
    balance_due_plain: str = "",
    min_body_rows: int = DEFAULT_MIN_LINE_ROWS,
    logo_data_uri: str = "",
    logo_display_w: int = 400,
    logo_display_h: int = 180,
) -> str:
    """
    Chavan-style invoice layout for QTextDocument print/PDF.

    ``line_rows`` tuples are
    ``(serviced_on, jl_num, description, bol, rate, qty, amount)`` — caller supplies
    display strings (already formatted numbers where needed).

    ``fee_row`` is ``(jl, description, rate, qty, amount)`` for the CO / compliance-fee
    line. Rate may be a percent (``3%``) or an amount. Omit or pass empty strings for
    a blank fee row (still printed so the sheet matches the paper form).

    ``ship_to_plain`` is accepted but not printed (Chavan invoices have BILL TO only).

    ``logo_data_uri`` — base64 data URI (``data:image/png;base64,...``) for the company
    logo.  When supplied the logo is rendered top-left with no border; the company block
    text is shown below it as contact details.  When omitted the company text block from
    My Company is used instead.

    Ticket images are not included; extra pages for them can be appended later.
    """
    del ship_to_plain  # printed invoices are BILL TO only
    rows = list(line_rows or [])
    n = max(len(rows), max(0, min_body_rows))
    body_html: list[str] = []
    for i in range(n):
        if i < len(rows):
            so, jl, desc, bol, rate, qty, amt = rows[i]
            cells = [
                _esc_cell(so),
                _esc_cell(jl),
                _esc_cell(desc),
                _esc_cell(bol),
                _esc_cell(rate),
                _esc_cell(qty),
                _esc_cell(amt),
            ]
        else:
            cells = ["&#160;"] * 7
        body_html.append(_line_tr(cells))

    inv_d = _esc_cell(invoice_date)
    inv_n = _esc_cell(invoice_number)
    po = _esc_cell(po_contract)
    nj = _esc_cell(name_job)
    sub = _esc_cell(subtotal_plain)
    bal = _esc_cell(balance_due_plain)

    if fee_row:
        fee_jl, fee_desc, fee_rate, fee_qty, fee_amt = fee_row
    else:
        fee_jl = fee_desc = fee_rate = fee_qty = fee_amt = ""
    fee_cells = [
        "&#160;",
        _esc_cell(fee_jl),
        _esc_cell(fee_desc),
        "&#160;",
        _esc_cell(fee_rate),
        _esc_cell(fee_qty),
        _esc_cell(fee_amt),
    ]

    top_left = _logo_block_html(logo_data_uri, company_block_plain, logo_display_w, logo_display_h)

    parts = [
        "<html><head><meta charset=\"utf-8\"/></head><body "
        "style=\"margin:0.5in; font-family: Arial, Helvetica, sans-serif; "
        "font-size:10pt; color:#000;\">",

        # ── Row 1: Company (left) + Invoice title / Date / Invoice # (right) ──
        "<table width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" style=\"border:none;\">",
        "<tr>",
        '<td width="55%" valign="top" style="border:none; padding:0 16px 0 0;">',
        top_left,
        "</td>",
        '<td width="45%" valign="top" style="border:none; padding:0;">',
        '<div style="font-size:22pt; font-weight:bold; text-align:right; '
        'letter-spacing:0.02em; line-height:1.1; margin-bottom:8px;">Invoice</div>',
        '<table width="100%" cellspacing="0" cellpadding="0" '
        'style="border-collapse:collapse; margin-left:auto;">',
        "<tr>",
        f'<th style="{_TH}">Date</th>',
        f'<th style="{_TH}">Invoice #</th>',
        "</tr>",
        "<tr>",
        f'<td style="text-align:center; border:1px solid #000; padding:8px 6px;">{inv_d}</td>',
        f'<td style="text-align:center; border:1px solid #000; padding:8px 6px;">{inv_n}</td>',
        "</tr>",
        "</table>",
        "</td>",
        "</tr>",
        "</table>",

        # ── Row 2: BILL TO + PO/CONTRACT# / NAME/JOB# ──
        '<table width="100%" cellspacing="0" cellpadding="0" '
        'style="border:none; margin-top:14px;">',
        "<tr>",
        '<td width="48%" valign="top" style="border:none; padding:0;">',
        '<table width="100%" cellspacing="0" cellpadding="0" height="120" '
        'style="border:1px solid #000; border-collapse:collapse;">',
        '<tr><th style="text-align:left; padding:5px 8px; font-weight:bold; '
        'border-bottom:1px solid #000; background:#f0f0f0; font-size:8pt; '
        'text-transform:uppercase;">BILL TO</th></tr>',
        '<tr><td valign="top" style="padding:8px; height:96px; line-height:1.35;">'
        f"{_bill_to_html(bill_to_plain)}</td></tr>",
        "</table>",
        "</td>",
        '<td width="4%" style="border:none;">&#160;</td>',
        '<td width="48%" valign="top" style="border:none; padding:0;">',
        '<table width="100%" cellspacing="0" cellpadding="0" '
        'style="border-collapse:collapse;">',
        "<tr>",
        f'<th style="{_META_LABEL}">PO / CONTRACT #</th>',
        f'<td style="{_META_VAL}">{po}</td>',
        "</tr>",
        "<tr>",
        f'<th style="{_META_LABEL}">NAME / JOB #</th>',
        f'<td style="{_META_VAL}">{nj}</td>',
        "</tr>",
        "</table>",
        "</td>",
        "</tr>",
        "</table>",

        # ── Line-items grid ───────────────────────────────────────────────────
        '<table width="100%" cellspacing="0" cellpadding="0" '
        'style="border-collapse:collapse; margin-top:14px; border:1px solid #000; '
        'table-layout:fixed;">',
        "<colgroup>",
        '<col style="width:11%;"/><col style="width:9%;"/><col style="width:28%;"/>',
        '<col style="width:11%;"/><col style="width:12%;"/><col style="width:13%;"/>',
        '<col style="width:16%;"/>',
        "</colgroup>",
        "<thead><tr>",
        f'<th style="{_GRID_TH}">Serviced On</th>',
        f'<th style="{_GRID_TH}">JL #</th>',
        f'<th style="{_GRID_TH}">Description</th>',
        f'<th style="{_GRID_TH}">BOL#</th>',
        f'<th style="{_GRID_TH}">Rate</th>',
        f'<th style="{_GRID_TH}">Quantity</th>',
        f'<th style="{_GRID_TH}">Amount</th>',
        "</tr></thead><tbody>",
        *body_html,
        # Subtotal
        "<tr>",
        '<td colspan="2" style="border:1px solid #000;">&#160;</td>',
        '<td style="border:1px solid #000; font-weight:700; padding:6px 4px;">Subtotal</td>',
        '<td colspan="3" style="border:1px solid #000;">&#160;</td>',
        f'<td style="border:1px solid #000; font-weight:700; text-align:right; '
        f'padding:6px 4px; font-variant-numeric:tabular-nums;">{sub}</td>',
        "</tr>",
        # CO / compliance-fee line
        _line_tr(fee_cells),
        # Balance Due
        "<tr>",
        '<td colspan="5" style="border:1px solid #000; border-top:2px solid #000;">&#160;</td>',
        '<td style="border:2px solid #000; font-weight:700; '
        'text-align:right; text-transform:uppercase; font-size:9pt; padding:8px 6px; '
        'vertical-align:middle;">Balance Due</td>',
        f'<td style="border:2px solid #000; font-weight:700; '
        f'text-align:right; font-size:12pt; padding:8px 6px; vertical-align:middle; '
        f'font-variant-numeric:tabular-nums;">{bal}</td>',
        "</tr>",
        "</tbody></table>",

        # ── Footer ────────────────────────────────────────────────────────────
        '<table width="100%" cellspacing="0" cellpadding="0" style="border:none; margin-top:18px;">',
        '<tr><td valign="top" style="border:none; padding:4px 0; font-size:9.5pt; '
        'line-height:1.45; color:#222;">'
        f"{_footer_html(footer_plain, footer_phone)}</td></tr>",
        "</table>",
        "</body></html>",
    ]
    return "".join(parts)
