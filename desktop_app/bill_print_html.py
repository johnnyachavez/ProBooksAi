"""HTML layout for vendor bill print / PDF (matches Enter Bills expense grid, black & white)."""

from __future__ import annotations

from probooksai.html_escape import escape_html_text as _he

DEFAULT_MIN_LINE_ROWS = 12


def _block_html(plain: str) -> str:
    t = (plain or "").strip()
    if not t:
        return "&#160;"
    return _he(t).replace("\n", "<br/>")


def build_bill_print_html(
    *,
    company_block_plain: str = "",
    bill_date: str = "",
    due_date: str = "",
    vendor_invoice_number: str = "",
    vendor_name: str = "",
    vendor_block_plain: str = "",
    memo_plain: str = "",
    line_rows: list[tuple[str, str, str, str, str]] | None = None,
    total_plain: str = "",
    min_body_rows: int = DEFAULT_MIN_LINE_ROWS,
) -> str:
    """
    ``line_rows`` tuples are
    ``(line_date, ticket_ref, amount, memo, customer_job)`` — display strings.
    """
    rows = list(line_rows or [])
    n = max(len(rows), max(0, min_body_rows))
    body_html: list[str] = []
    for i in range(n):
        if i < len(rows):
            dt, tk, amt, memo, job = rows[i]
            cells = [
                _he((dt or "").strip()),
                _he((tk or "").strip()),
                _he((amt or "").strip()),
                _he((memo or "").strip()),
                _he((job or "").strip()),
            ]
        else:
            cells = ["&#160;"] * 5
        body_html.append(
            "<tr>"
            + "".join(
                f'<td style="text-align:{"right" if j == 2 else "left"}; vertical-align:top;">{c}</td>'
                for j, c in enumerate(cells)
            )
            + "</tr>"
        )

    bd = _he((bill_date or "").strip()) or "&#160;"
    dd = _he((due_date or "").strip()) or "&#160;"
    vin = _he((vendor_invoice_number or "").strip()) or "&#160;"
    vn = _he((vendor_name or "").strip()) or "&#160;"
    tot = _he((total_plain or "").strip()) or "&#160;"

    parts = [
        '<html><head><meta charset="utf-8"/></head><body '
        'style="margin:0.4in; font-family: Arial, Helvetica, sans-serif; '
        'font-size:10pt; color:#000;">',
        '<table width="100%" cellspacing="0" cellpadding="0" style="border:none;">',
        "<tr>",
        '<td width="58%" valign="top" style="border:none; padding:0 10px 0 0;">',
        '<table width="100%" cellspacing="0" cellpadding="8" '
        'style="border:1px solid #000; border-collapse:collapse;">',
        f'<tr><td valign="top" style="min-height:80px;">{_block_html(company_block_plain)}</td></tr>',
        "</table>",
        "</td>",
        '<td width="42%" valign="top" style="border:none; padding:0;">',
        '<div style="font-size:20pt; font-weight:bold; text-align:right; letter-spacing:0.02em;">'
        "Bill</div>",
        '<table width="100%" cellspacing="0" cellpadding="5" '
        'style="border:2px solid #000; border-collapse:collapse; margin-top:6px;">',
        "<tr>",
        '<th style="text-align:center; font-weight:bold; border:1px solid #000;">Bill date</th>',
        '<th style="text-align:center; font-weight:bold; border:1px solid #000;">Due date</th>',
        "</tr>",
        "<tr>",
        f'<td style="text-align:center; border:1px solid #000;">{bd}</td>',
        f'<td style="text-align:center; border:1px solid #000;">{dd}</td>',
        "</tr>",
        "</table>",
        '<table width="100%" cellspacing="0" cellpadding="5" '
        'style="border:2px solid #000; border-collapse:collapse; margin-top:8px;">',
        "<tr>",
        '<th style="text-align:center; font-weight:bold; border:1px solid #000;">Vendor</th>',
        '<th style="text-align:center; font-weight:bold; border:1px solid #000;">Vendor invoice #</th>',
        "</tr>",
        "<tr>",
        f'<td style="text-align:center; border:1px solid #000;">{vn}</td>',
        f'<td style="text-align:center; border:1px solid #000;">{vin}</td>',
        "</tr>",
        "</table>",
        "</td>",
        "</tr>",
        "</table>",
        '<table width="100%" cellspacing="0" cellpadding="0" style="border:none; margin-top:12px;">',
        "<tr>",
        '<td width="100%" valign="top" style="border:none; padding:0;">',
        '<table width="100%" cellspacing="0" cellpadding="0" '
        'style="border:1px solid #000; border-collapse:collapse;">',
        '<tr><th style="text-align:left; padding:5px 8px; font-weight:bold; border-bottom:1px solid #000;">'
        "VENDOR</th></tr>",
        '<tr><td valign="top" style="padding:8px; min-height:48px;">'
        f"{_block_html(vendor_block_plain)}</td></tr>",
        "</table>",
        "</td>",
        "</tr>",
        "</table>",
        '<table width="100%" cellspacing="0" cellpadding="4" '
        'style="border-collapse:collapse; margin-top:12px; border:1px solid #000;">',
        "<thead><tr>",
        '<th style="text-align:center; font-weight:bold; border:1px solid #000;">Date</th>',
        '<th style="text-align:center; font-weight:bold; border:1px solid #000;">Ticket #</th>',
        '<th style="text-align:center; font-weight:bold; border:1px solid #000;">Amount</th>',
        '<th style="text-align:center; font-weight:bold; border:1px solid #000;">Memo</th>',
        '<th style="text-align:center; font-weight:bold; border:1px solid #000;">Customer:Job</th>',
        "</tr></thead><tbody>",
        *body_html,
        "<tr>",
        '<td colspan="3" style="border:1px solid #000; border-top:2px solid #000;">&#160;</td>',
        '<td colspan="2" style="border:2px solid #000; padding:10px 12px; '
        'border-top:2px solid #000; vertical-align:middle;">',
        '<table width="100%" cellspacing="0" cellpadding="0" style="border:none;">',
        "<tr>",
        '<td style="border:none; font-size:13pt; font-weight:bold;">Total</td>',
        f'<td style="border:none; font-size:13pt; font-weight:bold; text-align:right;">{tot}</td>',
        "</tr>",
        "</table>",
        "</td>",
        "</tr>",
        "</tbody></table>",
        '<table width="100%" cellspacing="0" cellpadding="0" style="border:none; margin-top:12px;">',
        '<tr><td valign="top" style="border:none; min-height:28px; padding:4px 0;">'
        f"{_block_html(memo_plain)}</td></tr>",
        "</table>",
        "</body></html>",
    ]
    return "".join(parts)
