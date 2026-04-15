"""Render invoice HTML to a PDF file path via Qt (no ``QFileDialog`` / ``QPrintDialog`` here).

**Desktop UI**

- **Invoices** tab uses ``invoice_html_string`` for print preview HTML and ``save_invoice_pdf`` for
  PDF files; **Print…** opens ``QPrintDialog`` (user may pick a physical printer or a “Print to PDF” driver).
- ``save_invoice_pdf`` / ``invoice_html_string`` are also used from tests and CLI helpers.

``save_invoice_pdf`` creates ``QPrinter`` in PDF mode and calls ``QTextDocument.print_``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtGui import QTextDocument
from PySide6.QtPrintSupport import QPrinter

from desktop_app.flexible_date import format_iso_to_us_display
from desktop_app.invoice_print_html import (
    build_invoice_print_html,
    parse_invoice_line_description,
    parse_invoice_memo_po_job_footer,
)


def invoice_html_string(conn: sqlite3.Connection, invoice_id: int) -> str:
    """Build the same HTML used for PDF export and **Invoices** tab printing (saved invoice row)."""
    from probooksai import business

    inv, lines = business.get_invoice_detail(conn, invoice_id)
    if inv is None:
        raise ValueError("Invoice not found")

    inv_d = dict(inv)
    memo = (inv_d.get("memo") or "").strip()
    po, job, footer = parse_invoice_memo_po_job_footer(memo)
    inv_date_raw = (inv_d.get("invoice_date") or "").strip()
    inv_date = format_iso_to_us_display(inv_date_raw) if inv_date_raw else ""

    name = (inv_d.get("customer_name") or "").strip()
    addr = (inv_d.get("customer_address") or "").strip()
    bill_parts = [name] if name else []
    if addr:
        bill_parts.append(addr)
    bill_to_plain = "\n".join(bill_parts)

    line_rows: list[tuple[str, str, str, str, str, str, str]] = []
    for ln in lines:
        d = dict(ln)
        so, jl, desc, bol = parse_invoice_line_description(d.get("description") or "")
        qty = float(d.get("qty") or 0)
        rate = float(d.get("rate") or 0)
        lt = float(d.get("line_total") or 0)
        line_rows.append(
            (so, jl, desc, bol, f"{rate:,.2f}", f"{qty:.2f}", f"{lt:,.2f}")
        )

    total = float(inv_d.get("total") or 0)
    balance_plain = f"${total:,.2f}"

    return build_invoice_print_html(
        company_block_plain="",
        invoice_date=inv_date,
        invoice_number=(inv_d.get("invoice_number") or "").strip(),
        bill_to_plain=bill_to_plain,
        po_contract=po,
        name_job=job,
        footer_plain=footer,
        line_rows=line_rows,
        balance_due_plain=balance_plain,
    )


def save_invoice_pdf(conn: sqlite3.Connection, invoice_id: int, file_path: str) -> None:
    """
    Render an invoice as HTML and print it to a PDF file using Qt.

    IMPORTANT: Qt requires an application instance (Q(Core/Gui)Application)
    to exist before constructing QPrinter. In CLI/subprocess contexts (like pytest),
    there usually isn't one yet, so we create it if needed.
    """
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    html = invoice_html_string(conn, invoice_id)
    doc = QTextDocument()
    doc.setHtml(html)

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(Path(file_path)))
    doc.print_(printer)
