"""Render bill HTML to PDF (Qt); no dialogs here."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtGui import QTextDocument
from PySide6.QtPrintSupport import QPrinter

from desktop_app.bill_print_html import build_bill_print_html
from desktop_app.flexible_date import format_iso_to_us_display
from probooksai.company_identity import company_identity_plain_block


def bill_html_string(conn: sqlite3.Connection, bill_id: int) -> str:
    """Same HTML as Enter Bills PDF export and printing."""
    from probooksai import business

    b, lines = business.get_bill_detail(conn, bill_id)
    if b is None:
        raise ValueError("Bill not found")
    d = dict(b)
    vrow = conn.execute(
        "SELECT name, address, email, phone FROM vendors WHERE id = ?",
        (int(d["vendor_id"]),),
    ).fetchone()
    vendor_name = ""
    vendor_block = ""
    if vrow is not None:
        vr = dict(vrow)
        vendor_name = (vr.get("name") or "").strip()
        parts: list[str] = []
        addr = (vr.get("address") or "").strip()
        if addr:
            parts.append(addr)
        em = (vr.get("email") or "").strip()
        if em:
            parts.append(em)
        ph = (vr.get("phone") or "").strip()
        if ph:
            parts.append(ph)
        vendor_block = "\n".join(parts)

    bd_raw = (d.get("bill_date") or "").strip()
    bill_date = format_iso_to_us_display(bd_raw) if bd_raw and len(bd_raw) >= 10 else (bd_raw or "")
    due_raw = (d.get("due_date") or "").strip()
    due_date = ""
    if due_raw and len(due_raw) >= 10 and due_raw[4] == "-":
        due_date = format_iso_to_us_display(due_raw[:10])
    elif due_raw:
        due_date = due_raw

    line_rows: list[tuple[str, str, str, str, str]] = []
    for ln in lines:
        ld = dict(ln)
        ldt = (ld.get("line_date") or "").strip()
        if ldt and len(ldt) >= 10 and ldt[4] == "-":
            ldt_disp = format_iso_to_us_display(ldt[:10])
        else:
            ldt_disp = ldt
        amt = float(ld.get("amount") or 0.0)
        line_rows.append(
            (
                ldt_disp,
                (ld.get("ticket_ref") or "").strip(),
                f"${amt:,.2f}",
                (ld.get("memo") or "").strip(),
                (ld.get("customer_job") or "").strip(),
            )
        )
    if not line_rows:
        amt0 = float(d.get("total") or 0.0)
        line_rows.append(("", "", f"${amt0:,.2f}", "", ""))

    total = float(d.get("total") or 0)
    company_plain = company_identity_plain_block(conn)

    return build_bill_print_html(
        company_block_plain=company_plain,
        bill_date=bill_date,
        due_date=due_date or "—",
        vendor_invoice_number=(d.get("vendor_invoice_number") or "").strip(),
        vendor_name=vendor_name,
        vendor_block_plain=vendor_block,
        memo_plain=(d.get("memo") or "").strip(),
        line_rows=line_rows,
        total_plain=f"${total:,.2f}",
    )


def save_bill_pdf(conn: sqlite3.Connection, bill_id: int, file_path: str) -> None:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    html = bill_html_string(conn, bill_id)
    doc = QTextDocument()
    doc.setHtml(html)

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(Path(file_path)))
    doc.print_(printer)
