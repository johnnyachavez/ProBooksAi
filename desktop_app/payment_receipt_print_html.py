"""HTML for AR / AP payment receipt PDF and printing."""

from __future__ import annotations

from probooksai.html_escape import escape_html_text as _he


def _block_html(plain: str) -> str:
    t = (plain or "").strip()
    if not t:
        return "&#160;"
    return _he(t).replace("\n", "<br/>")


def build_ar_payment_receipt_html(
    *,
    company_block_plain: str = "",
    title: str = "Receive payment",
    payment_date: str = "",
    customer_name: str = "",
    amount_plain: str = "",
    method: str = "",
    reference: str = "",
    bank_name: str = "",
    memo: str = "",
    allocation_rows: list[tuple[str, str, str]] | None = None,
) -> str:
    """``allocation_rows``: ``(invoice_number, invoice_date, apply_amount)`` display strings."""
    rows = list(allocation_rows or [])
    body_html: list[str] = []
    for inv_num, inv_dt, amt in rows:
        body_html.append(
            "<tr>"
            f'<td style="text-align:left; border:1px solid #000; padding:4px;">{_he(inv_num.strip())}</td>'
            f'<td style="text-align:left; border:1px solid #000; padding:4px;">{_he(inv_dt.strip())}</td>'
            f'<td style="text-align:right; border:1px solid #000; padding:4px;">{_he(amt.strip())}</td>'
            "</tr>"
        )
    if not body_html:
        body_html.append(
            "<tr>"
            '<td colspan="3" style="text-align:center; border:1px solid #000; padding:8px;">'
            "&#160;</td>"
            "</tr>"
        )

    pd = _he((payment_date or "").strip()) or "&#160;"
    cn = _he((customer_name or "").strip()) or "&#160;"
    ap = _he((amount_plain or "").strip()) or "&#160;"
    mt = _he((method or "").strip()) or "&#160;"
    rf = _he((reference or "").strip()) or "&#160;"
    bk = _he((bank_name or "").strip()) or "&#160;"
    tt = _he((title or "").strip()) or "Receive payment"

    parts = [
        '<html><head><meta charset="utf-8"/></head><body '
        'style="margin:0.4in; font-family: Arial, Helvetica, sans-serif; '
        'font-size:10pt; color:#000;">',
        '<table width="100%" cellspacing="0" cellpadding="0" style="border:none;">',
        "<tr>",
        '<td width="55%" valign="top">',
        '<table width="100%" cellspacing="0" cellpadding="8" '
        'style="border:1px solid #000; border-collapse:collapse;">',
        f'<tr><td valign="top">{_block_html(company_block_plain)}</td></tr>',
        "</table>",
        "</td>",
        '<td width="45%" valign="top" style="padding-left:12px;">',
        f'<div style="font-size:18pt; font-weight:bold; text-align:right;">{tt}</div>',
        '<table width="100%" cellspacing="0" cellpadding="6" '
        'style="border:2px solid #000; border-collapse:collapse; margin-top:8px;">',
        "<tr><th style='border:1px solid #000;'>Payment date</th>"
        "<th style='border:1px solid #000;'>Amount</th></tr>",
        "<tr>",
        f'<td style="text-align:center; border:1px solid #000;">{pd}</td>',
        f'<td style="text-align:right; border:1px solid #000;">{ap}</td>',
        "</tr>",
        "</table>",
        "</td>",
        "</tr>",
        "</table>",
        '<table width="100%" cellspacing="0" cellpadding="6" style="margin-top:14px; border:1px solid #000;">',
        "<tr>",
        f'<td width="25%"><b>Customer</b><br/>{cn}</td>',
        f'<td width="25%"><b>Method</b><br/>{mt}</td>',
        f'<td width="25%"><b>Reference</b><br/>{rf}</td>',
        f'<td width="25%"><b>Deposit to</b><br/>{bk}</td>',
        "</tr>",
        "</table>",
        '<table width="100%" cellspacing="0" cellpadding="0" style="margin-top:10px;">',
        f'<tr><td>{_block_html(memo)}</td></tr>',
        "</table>",
        '<table width="100%" cellspacing="0" cellpadding="4" '
        'style="border-collapse:collapse; margin-top:14px; border:1px solid #000;">',
        "<thead><tr>",
        '<th style="border:1px solid #000;">Invoice #</th>',
        '<th style="border:1px solid #000;">Invoice date</th>',
        '<th style="border:1px solid #000;">Amount applied</th>',
        "</tr></thead><tbody>",
        *body_html,
        "</tbody></table>",
        "</body></html>",
    ]
    return "".join(parts)


def build_ap_payment_receipt_html(
    *,
    company_block_plain: str = "",
    title: str = "Pay bills payment",
    payment_date: str = "",
    vendor_name: str = "",
    amount_plain: str = "",
    reference: str = "",
    bank_name: str = "",
    memo: str = "",
    allocation_rows: list[tuple[str, str, str]] | None = None,
) -> str:
    """``allocation_rows``: ``(vendor_invoice_ref, bill_date, apply_amount)``."""
    rows = list(allocation_rows or [])
    body_html: list[str] = []
    for inv_num, inv_dt, amt in rows:
        body_html.append(
            "<tr>"
            f'<td style="text-align:left; border:1px solid #000; padding:4px;">{_he(inv_num.strip())}</td>'
            f'<td style="text-align:left; border:1px solid #000; padding:4px;">{_he(inv_dt.strip())}</td>'
            f'<td style="text-align:right; border:1px solid #000; padding:4px;">{_he(amt.strip())}</td>'
            "</tr>"
        )
    if not body_html:
        body_html.append(
            "<tr>"
            '<td colspan="3" style="text-align:center; border:1px solid #000; padding:8px;">'
            "&#160;</td>"
            "</tr>"
        )

    pd = _he((payment_date or "").strip()) or "&#160;"
    vn = _he((vendor_name or "").strip()) or "&#160;"
    ap = _he((amount_plain or "").strip()) or "&#160;"
    rf = _he((reference or "").strip()) or "&#160;"
    bk = _he((bank_name or "").strip()) or "&#160;"
    tt = _he((title or "").strip()) or "Pay bills payment"

    parts = [
        '<html><head><meta charset="utf-8"/></head><body '
        'style="margin:0.4in; font-family: Arial, Helvetica, sans-serif; '
        'font-size:10pt; color:#000;">',
        '<table width="100%" cellspacing="0" cellpadding="0" style="border:none;">',
        "<tr>",
        '<td width="55%" valign="top">',
        '<table width="100%" cellspacing="0" cellpadding="8" '
        'style="border:1px solid #000; border-collapse:collapse;">',
        f'<tr><td valign="top">{_block_html(company_block_plain)}</td></tr>',
        "</table>",
        "</td>",
        '<td width="45%" valign="top" style="padding-left:12px;">',
        f'<div style="font-size:18pt; font-weight:bold; text-align:right;">{tt}</div>',
        '<table width="100%" cellspacing="0" cellpadding="6" '
        'style="border:2px solid #000; border-collapse:collapse; margin-top:8px;">',
        "<tr><th style='border:1px solid #000;'>Payment date</th>"
        "<th style='border:1px solid #000;'>Amount</th></tr>",
        "<tr>",
        f'<td style="text-align:center; border:1px solid #000;">{pd}</td>',
        f'<td style="text-align:right; border:1px solid #000;">{ap}</td>',
        "</tr>",
        "</table>",
        "</td>",
        "</tr>",
        "</table>",
        '<table width="100%" cellspacing="0" cellpadding="6" style="margin-top:14px; border:1px solid #000;">',
        "<tr>",
        f'<td width="33%"><b>Vendor</b><br/>{vn}</td>',
        f'<td width="33%"><b>Reference</b><br/>{rf}</td>',
        f'<td width="34%"><b>Pay from bank</b><br/>{bk}</td>',
        "</tr>",
        "</table>",
        '<table width="100%" cellspacing="0" cellpadding="0" style="margin-top:10px;">',
        f'<tr><td>{_block_html(memo)}</td></tr>',
        "</table>",
        '<table width="100%" cellspacing="0" cellpadding="4" '
        'style="border-collapse:collapse; margin-top:14px; border:1px solid #000;">',
        "<thead><tr>",
        '<th style="border:1px solid #000;">Bill #</th>',
        '<th style="border:1px solid #000;">Bill date</th>',
        '<th style="border:1px solid #000;">Amount applied</th>',
        "</tr></thead><tbody>",
        *body_html,
        "</tbody></table>",
        "</body></html>",
    ]
    return "".join(parts)
