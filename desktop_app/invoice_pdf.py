"""Render invoice HTML to a PDF file path via Qt (no ``QFileDialog`` / ``QPrintDialog`` here).

**Desktop UI**

- **Invoices** tab uses ``invoice_html_string`` for print preview HTML and ``save_invoice_pdf`` for
  PDF files; **Print…** opens ``QPrintDialog`` (user may pick a physical printer or a “Print to PDF” driver).
- ``save_invoice_pdf`` / ``invoice_html_string`` are also used from tests and CLI helpers.

``save_invoice_pdf`` creates ``QPrinter`` in PDF mode and calls ``QTextDocument.print_``.

Company letterhead comes from **More → Business → Company** (``company_setup_*`` keys in
``company_settings``), with optional ``invoice_company_block`` override and legacy
``invoice_company_*`` fallback.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from desktop_app.flexible_date import format_iso_to_us_display
from desktop_app.invoice_print_html import (
    build_invoice_print_html,
    parse_invoice_line_description,
    parse_invoice_memo_po_job_footer,
)


def _format_city_state_zip_line(city: str, state: str, zip_code: str) -> str:
    city = (city or "").strip()
    state = (state or "").strip()
    zip_code = (zip_code or "").strip()
    if not (city or state or zip_code):
        return ""
    if city and state:
        return f"{city}, {state} {zip_code}".strip()
    if city:
        return f"{city} {zip_code}".strip() if zip_code else city
    return f"{state} {zip_code}".strip() if state or zip_code else ""


def _letterhead_plain_from_company_settings(conn: sqlite3.Connection) -> str:
    """Sender block for the PDF from ``company_settings`` (no hardcoded business identity)."""
    from probooksai import business

    block = (business.get_setting(conn, "invoice_company_block", "") or "").strip()
    if block:
        return block
    name = (business.get_setting(conn, "company_setup_name", "") or "").strip()
    addr1 = (business.get_setting(conn, "company_setup_addr1", "") or "").strip()
    addr2 = (business.get_setting(conn, "company_setup_addr2", "") or "").strip()
    csz = _format_city_state_zip_line(
        business.get_setting(conn, "company_setup_city", ""),
        business.get_setting(conn, "company_setup_state", ""),
        business.get_setting(conn, "company_setup_zip", ""),
    )
    phone = (business.get_setting(conn, "company_setup_phone", "") or "").strip()
    email = (business.get_setting(conn, "company_setup_email", "") or "").strip()
    parts: list[str] = []
    if name:
        parts.append(name)
    if addr1:
        parts.append(addr1)
    if addr2:
        parts.append(addr2)
    if csz:
        parts.append(csz)
    if phone:
        parts.append(phone)
    if email:
        parts.append(email)
    if parts:
        return "\n".join(parts)
    # Legacy keys (older builds or manual SQL)
    leg_name = (business.get_setting(conn, "invoice_company_name", "") or "").strip()
    leg_addr = (business.get_setting(conn, "invoice_company_address", "") or "").strip()
    leg_phone = (business.get_setting(conn, "invoice_company_phone", "") or "").strip()
    legacy = [p for p in (leg_name, leg_addr, leg_phone) if p]
    return "\n".join(legacy)


def _logo_display_dimensions(logo_path: str, max_w: int = 220, max_h: int = 80) -> tuple[int, int]:
    """Return (display_w, display_h) scaled to fit within max_w×max_h, preserving aspect ratio.

    Reads only the image header — no PIL/Qt dependency.  Falls back to (max_w, max_h) on
    any parse error so the caller always gets usable integers.
    """
    import struct

    try:
        with open(logo_path, "rb") as fh:
            header = fh.read(26)
        w: int = 0
        h: int = 0
        # PNG: 8-byte signature + IHDR chunk (4 len + 4 "IHDR" + 4 width + 4 height)
        if header[:8] == b"\x89PNG\r\n\x1a\n" and len(header) >= 24:
            w, h = struct.unpack(">II", header[16:24])
        # JPEG: scan for SOF0/SOF1/SOF2 markers (0xFF C0/C1/C2)
        elif header[:2] == b"\xff\xd8":
            with open(logo_path, "rb") as fh:
                data = fh.read()
            i = 2
            while i + 8 < len(data):
                if data[i] != 0xFF:
                    break
                marker = data[i + 1]
                seg_len = struct.unpack(">H", data[i + 2 : i + 4])[0]
                if marker in (0xC0, 0xC1, 0xC2):
                    h, w = struct.unpack(">HH", data[i + 5 : i + 9])
                    break
                i += 2 + seg_len
        if w > 0 and h > 0:
            scale = min(max_w / w, max_h / h, 1.0)
            return max(1, int(w * scale)), max(1, int(h * scale))
    except Exception:
        pass
    return max_w, max_h


def _logo_data_uri_from_settings(conn: sqlite3.Connection) -> str:
    """Return a base64 data URI for the company logo, or '' if not configured / file missing."""
    import base64
    import os
    from probooksai import business

    logo_path = (business.get_setting(conn, "company_logo_path", "") or "").strip()
    if not logo_path or not os.path.isfile(logo_path):
        return ""
    try:
        with open(logo_path, "rb") as fh:
            raw = fh.read()
        lower = logo_path.lower()
        if lower.endswith(".png"):
            mime = "image/png"
        elif lower.endswith((".jpg", ".jpeg")):
            mime = "image/jpeg"
        elif lower.endswith(".gif"):
            mime = "image/gif"
        elif lower.endswith(".svg"):
            mime = "image/svg+xml"
        else:
            mime = "image/png"
        b64 = base64.b64encode(raw).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception:
        return ""


def _logo_dimensions_from_settings(conn: sqlite3.Connection) -> tuple[int, int]:
    """Return (display_w, display_h) for the configured logo, or (220, 80) if not set."""
    import os
    from probooksai import business

    logo_path = (business.get_setting(conn, "company_logo_path", "") or "").strip()
    if not logo_path or not os.path.isfile(logo_path):
        return 220, 80
    return _logo_display_dimensions(logo_path)


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

    logo_uri = _logo_data_uri_from_settings(conn)
    logo_w, logo_h = _logo_dimensions_from_settings(conn) if logo_uri else (220, 80)

    return build_invoice_print_html(
        company_block_plain=_letterhead_plain_from_company_settings(conn),
        logo_data_uri=logo_uri,
        logo_display_w=logo_w,
        logo_display_h=logo_h,
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
    from PySide6.QtGui import QTextDocument
    from PySide6.QtPrintSupport import QPrinter
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
