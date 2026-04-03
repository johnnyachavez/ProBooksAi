"""Print invoice to PDF via Qt (Phase 8)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtGui import QTextDocument
from PySide6.QtPrintSupport import QPrinter

from probooksai.html_escape import escape_html_text as _he


def save_invoice_pdf(conn: sqlite3.Connection, invoice_id: int, file_path: str) -> None:
    from probooksai import business

    inv, lines = business.get_invoice_detail(conn, invoice_id)
    if inv is None:
        raise ValueError("Invoice not found")

    inv_d = dict(inv)
    memo = (inv_d.get("memo") or "").strip()
    memo_row = (
        f"<tr><th>Memo</th><td colspan='3'>{_he(memo) if memo else '—'}</td></tr>"
    )
    html_parts = [
        "<html><body style='font-family: sans-serif;'>",
        "<h1>Invoice</h1>",
        "<p><b>ProBooks+ai</b></p>",
        "<p>Bill to: <b>"
        + _he(inv_d["customer_name"])
        + "</b><br/>"
        + _he(inv_d.get("customer_address") or "")
        + "</p>",
        "<table width='100%' cellspacing='0' cellpadding='6' border='1'>",
        "<tr><th>Invoice #</th><td>"
        + _he(inv_d["invoice_number"])
        + "</td><th>Date</th><td>"
        + _he(inv_d["invoice_date"])
        + "</td></tr>",
        "<tr><th>Due</th><td>"
        + (_he(inv_d.get("due_date")) if inv_d.get("due_date") else "—")
        + "</td><th>Status</th><td>"
        + _he(inv_d.get("status"))
        + "</td></tr>",
        memo_row,
        "</table>",
        "<h3>Line items</h3>",
        "<table width='100%' cellspacing='0' cellpadding='4' border='1'>",
        "<tr><th>Description</th><th>Qty</th><th>Rate</th><th>Total</th></tr>",
    ]
    for ln in lines:
        d = dict(ln)
        html_parts.append(
            "<tr><td>"
            + _he(d.get("description"))
            + "</td><td>"
            + _he(d.get("qty"))
            + "</td><td>"
            + f"{float(d.get('rate') or 0):,.2f}"
            + "</td><td>"
            + f"{float(d.get('line_total') or 0):,.2f}"
            + "</td></tr>"
        )
    html_parts.extend(
        [
            "</table>",
            f"<p><b>Subtotal:</b> ${float(inv_d['subtotal']):,.2f}<br/>",
            f"<b>Tax:</b> ${float(inv_d['tax_total']):,.2f}<br/>",
            f"<b>Total:</b> ${float(inv_d['total']):,.2f}<br/>",
            f"<b>Balance due:</b> ${float(inv_d['balance_due']):,.2f}</p>",
            "</body></html>",
        ]
    )
    html = "".join(html_parts)

    doc = QTextDocument()
    doc.setHtml(html)

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(Path(file_path)))
    doc.print_(printer)
