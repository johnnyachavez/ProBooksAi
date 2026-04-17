"""AR / AP payment receipt PDF and HTML strings (Qt)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtGui import QTextDocument
from PySide6.QtPrintSupport import QPrinter

from desktop_app.flexible_date import format_iso_to_us_display
from desktop_app.payment_receipt_print_html import (
    build_ap_payment_receipt_html,
    build_ar_payment_receipt_html,
)
from probooksai.company_identity import company_identity_plain_block


def ar_payment_html_string(conn: sqlite3.Connection, payment_id: int) -> str:
    from probooksai import business

    row, allocs = business.get_ar_payment_detail(conn, payment_id)
    if row is None:
        raise ValueError("AR payment not found")
    d = dict(row)
    pd_raw = (d.get("payment_date") or "").strip()
    pay_date = format_iso_to_us_display(pd_raw[:10]) if len(pd_raw) >= 10 else pd_raw
    amt = float(d.get("amount") or 0.0)
    alloc_rows: list[tuple[str, str, str]] = []
    for a in allocs:
        ad = dict(a)
        idt = (ad.get("invoice_date") or "").strip()
        id_disp = format_iso_to_us_display(idt[:10]) if len(idt) >= 10 else idt
        ap_amt = float(ad.get("apply_amount") or 0.0)
        alloc_rows.append(
            (
                (ad.get("invoice_number") or "").strip(),
                id_disp,
                f"${ap_amt:,.2f}",
            )
        )
    company_plain = company_identity_plain_block(conn)
    bank_name = (d.get("bank_account_name") or "").strip() or "—"
    return build_ar_payment_receipt_html(
        company_block_plain=company_plain,
        payment_date=pay_date,
        customer_name=(d.get("customer_name") or "").strip(),
        amount_plain=f"${amt:,.2f}",
        method=(d.get("method") or "").strip() or "—",
        reference=(d.get("reference") or "").strip() or "—",
        bank_name=bank_name,
        memo=(d.get("memo") or "").strip(),
        allocation_rows=alloc_rows,
    )


def ap_payment_html_string(conn: sqlite3.Connection, payment_id: int) -> str:
    from probooksai import business

    row, allocs = business.get_ap_payment_detail(conn, payment_id)
    if row is None:
        raise ValueError("AP payment not found")
    d = dict(row)
    pd_raw = (d.get("payment_date") or "").strip()
    pay_date = format_iso_to_us_display(pd_raw[:10]) if len(pd_raw) >= 10 else pd_raw
    amt = float(d.get("amount") or 0.0)
    alloc_rows: list[tuple[str, str, str]] = []
    for a in allocs:
        ad = dict(a)
        bdt = (ad.get("bill_date") or "").strip()
        bd_disp = format_iso_to_us_display(bdt[:10]) if len(bdt) >= 10 else bdt
        ap_amt = float(ad.get("apply_amount") or 0.0)
        alloc_rows.append(
            (
                (ad.get("vendor_invoice_number") or "").strip() or f"#{ad.get('bill_id')}",
                bd_disp,
                f"${ap_amt:,.2f}",
            )
        )
    company_plain = company_identity_plain_block(conn)
    bank_name = (d.get("bank_account_name") or "").strip() or "—"
    return build_ap_payment_receipt_html(
        company_block_plain=company_plain,
        payment_date=pay_date,
        vendor_name=(d.get("vendor_name") or "").strip(),
        amount_plain=f"${amt:,.2f}",
        reference=(d.get("reference") or "").strip() or "—",
        bank_name=bank_name,
        memo=(d.get("memo") or "").strip(),
        allocation_rows=alloc_rows,
    )


def save_ar_payment_pdf(conn: sqlite3.Connection, payment_id: int, file_path: str) -> None:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    html = ar_payment_html_string(conn, payment_id)
    doc = QTextDocument()
    doc.setHtml(html)
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(Path(file_path)))
    doc.print_(printer)


def save_ap_payment_pdf(conn: sqlite3.Connection, payment_id: int, file_path: str) -> None:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    html = ap_payment_html_string(conn, payment_id)
    doc = QTextDocument()
    doc.setHtml(html)
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(Path(file_path)))
    doc.print_(printer)
