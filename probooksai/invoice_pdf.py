"""
probooksai.invoice_pdf
=======================
Generate a professional PDF invoice using reportlab.

Usage
-----
    from probooksai.invoice_pdf import render_invoice_pdf
    path = render_invoice_pdf(conn, invoice_id, output_path="/tmp/INV-001.pdf")

The PDF includes:
  • Company letterhead (name, address, phone, email from company_settings)
  • "INVOICE" header with invoice number, date, due date
  • Bill-to customer block
  • Line items table with qty, description, unit price, amount
  • Subtotal / tax / total footer
  • Memo / payment terms note
  • Page number footer
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

_BRAND_BLUE = (0.08, 0.32, 0.56)     # #154F8E-ish
_BRAND_LIGHT = (0.93, 0.96, 1.0)     # column header tint
_GREY = (0.45, 0.45, 0.45)
_BLACK = (0, 0, 0)
_WHITE = (1, 1, 1)
_ROW_ALT = (0.97, 0.97, 0.97)


def render_invoice_pdf(
    conn: sqlite3.Connection,
    invoice_id: int,
    output_path: Optional[str] = None,
) -> str:
    """
    Render invoice *invoice_id* to a PDF file.

    Parameters
    ----------
    conn         : open sqlite3.Connection to the company DB
    invoice_id   : primary key of the invoice row
    output_path  : where to write the PDF (default: temp file)

    Returns
    -------
    str — absolute path to the generated PDF file.

    Raises
    ------
    ValueError  if the invoice is not found
    ImportError if reportlab is not installed
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            BaseDocTemplate,
            Frame,
            PageTemplate,
            Paragraph,
            Spacer,
            Table,
            TableStyle,
        )
        from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT
    except ImportError as err:
        raise ImportError(
            "reportlab is required for PDF invoice generation. "
            "Install with: pip install reportlab"
        ) from err

    from probooksai.business import get_invoice_detail, get_setting

    # ------------------------------------------------------------------
    # 1. Fetch data
    # ------------------------------------------------------------------
    header, lines = get_invoice_detail(conn, invoice_id)
    if not header:
        raise ValueError(f"Invoice {invoice_id} not found.")

    header = dict(header)
    lines = [dict(ln) for ln in lines]

    # Company settings
    company_name = get_setting(conn, "company_name", "Your Company")
    company_address = get_setting(conn, "company_address", "")
    company_phone = get_setting(conn, "company_phone", "")
    company_email = get_setting(conn, "company_email", "")
    payment_terms = get_setting(conn, "payment_terms", "")

    # Customer name — join via customers table
    customer_name = ""
    try:
        row = conn.execute(
            "SELECT name FROM customers WHERE id = ?", (header.get("customer_id"),)
        ).fetchone()
        if row:
            customer_name = row[0]
    except Exception:
        pass

    # ------------------------------------------------------------------
    # 2. Output path
    # ------------------------------------------------------------------
    if not output_path:
        import tempfile
        inv_num = (header.get("invoice_number") or str(invoice_id)).replace("/", "-")
        tmp = tempfile.NamedTemporaryFile(
            suffix=".pdf", prefix=f"invoice_{inv_num}_", delete=False
        )
        tmp.close()
        output_path = tmp.name

    output_path = str(Path(output_path).resolve())

    # ------------------------------------------------------------------
    # 3. Styles
    # ------------------------------------------------------------------
    styles = getSampleStyleSheet()
    brand_rgb = colors.Color(*_BRAND_BLUE)
    grey_rgb = colors.Color(*_GREY)

    style_h1 = ParagraphStyle(
        "H1", fontName="Helvetica-Bold", fontSize=22,
        textColor=brand_rgb, leading=26,
    )
    style_company = ParagraphStyle(
        "Company", fontName="Helvetica-Bold", fontSize=13,
        textColor=brand_rgb, leading=16,
    )
    style_body = ParagraphStyle(
        "Body", fontName="Helvetica", fontSize=9,
        textColor=colors.Color(*_BLACK), leading=13,
    )
    style_small = ParagraphStyle(
        "Small", fontName="Helvetica", fontSize=8,
        textColor=grey_rgb, leading=11,
    )
    style_label = ParagraphStyle(
        "Label", fontName="Helvetica-Bold", fontSize=8,
        textColor=grey_rgb, leading=11, spaceAfter=2,
    )
    style_right = ParagraphStyle(
        "Right", fontName="Helvetica", fontSize=9,
        textColor=colors.Color(*_BLACK), leading=13, alignment=TA_RIGHT,
    )
    style_right_bold = ParagraphStyle(
        "RightBold", fontName="Helvetica-Bold", fontSize=10,
        textColor=brand_rgb, leading=14, alignment=TA_RIGHT,
    )

    # ------------------------------------------------------------------
    # 4. Build content
    # ------------------------------------------------------------------
    story = []
    W = LETTER[0] - 1.2 * inch  # usable width

    # ---- Header: company left, INVOICE right ----
    company_block = [
        Paragraph(company_name, style_company),
    ]
    if company_address:
        for ln in company_address.split("\n"):
            company_block.append(Paragraph(ln.strip(), style_small))
    if company_phone:
        company_block.append(Paragraph(f"Tel: {company_phone}", style_small))
    if company_email:
        company_block.append(Paragraph(f"Email: {company_email}", style_small))

    invoice_block = [
        Paragraph("INVOICE", style_h1),
    ]

    hdr_table = Table(
        [[company_block, invoice_block]],
        colWidths=[W * 0.55, W * 0.45],
    )
    hdr_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(hdr_table)

    # ---- Divider ----
    from reportlab.platypus import HRFlowable
    story.append(HRFlowable(width="100%", thickness=2, color=brand_rgb, spaceAfter=10))

    # ---- Meta: invoice details left, bill-to right ----
    inv_number = header.get("invoice_number") or str(invoice_id)
    inv_date = header.get("invoice_date") or ""
    due_date = header.get("due_date") or ""

    meta_left = [
        Paragraph("INVOICE #", style_label),
        Paragraph(inv_number, style_body),
        Spacer(1, 6),
        Paragraph("DATE", style_label),
        Paragraph(inv_date, style_body),
    ]
    if due_date:
        meta_left += [
            Spacer(1, 6),
            Paragraph("DUE DATE", style_label),
            Paragraph(due_date, style_body),
        ]

    meta_right = [
        Paragraph("BILL TO", style_label),
        Paragraph(customer_name or "—", style_body),
    ]

    meta_table = Table(
        [[meta_left, meta_right]],
        colWidths=[W * 0.5, W * 0.5],
    )
    meta_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
    ]))
    story.append(meta_table)

    # ---- Line items table ----
    tbl_header = ["#", "Description", "Qty", "Unit Price", "Amount"]
    tbl_data = [tbl_header]

    subtotal = float(header.get("subtotal") or 0)
    tax_total = float(header.get("tax_total") or 0)
    total = float(header.get("total") or 0)

    for i, ln in enumerate(lines, 1):
        qty = ln.get("quantity") or 1
        unit = ln.get("unit_price") or 0
        amt = ln.get("amount") or ln.get("line_total") or (qty * unit)
        tbl_data.append([
            str(i),
            Paragraph(ln.get("description") or "", style_body),
            str(qty),
            f"${float(unit):,.2f}",
            f"${float(amt):,.2f}",
        ])

    col_widths = [
        W * 0.05,   # #
        W * 0.50,   # description
        W * 0.08,   # qty
        W * 0.18,   # unit price
        W * 0.19,   # amount
    ]

    hdr_bg = colors.Color(*_BRAND_BLUE)
    alt_bg = colors.Color(*_ROW_ALT)

    items_table = Table(tbl_data, colWidths=col_widths, repeatRows=1)
    ts = TableStyle([
        # Header row
        ("BACKGROUND", (0, 0), (-1, 0), hdr_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
        ("TOPPADDING", (0, 0), (-1, 0), 7),
        # Data rows
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
        # Alignment
        ("ALIGN", (0, 0), (0, -1), "CENTER"),   # #
        ("ALIGN", (2, 0), (2, -1), "CENTER"),   # qty
        ("ALIGN", (3, 0), (4, -1), "RIGHT"),    # price / amount
        # Grid
        ("GRID", (0, 0), (-1, -1), 0.4, colors.Color(0.8, 0.8, 0.8)),
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, hdr_bg),
    ])
    # Alternate row shading
    for row_i in range(1, len(tbl_data)):
        if row_i % 2 == 0:
            ts.add("BACKGROUND", (0, row_i), (-1, row_i), alt_bg)
    items_table.setStyle(ts)
    story.append(items_table)
    story.append(Spacer(1, 8))

    # ---- Totals block (right-aligned) ----
    totals_data = []
    if lines:
        totals_data.append(["Subtotal", f"${subtotal:,.2f}"])
    if tax_total:
        totals_data.append(["Tax", f"${tax_total:,.2f}"])
    totals_data.append(["TOTAL DUE", f"${total:,.2f}"])

    balance_due = float(header.get("balance_due") or total)
    if abs(balance_due - total) > 0.005:
        totals_data.append(["Balance Due", f"${balance_due:,.2f}"])

    if totals_data:
        tot_styles_list = [
            ("FONTNAME", (0, 0), (-1, -2), "Helvetica"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -2), 9),
            ("FONTSIZE", (0, -1), (-1, -1), 11),
            ("TEXTCOLOR", (0, -1), (-1, -1), brand_rgb),
            ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LINEABOVE", (0, -1), (-1, -1), 1.0, brand_rgb),
        ]
        tot_col = [W * 0.72, W * 0.28]
        tot_table = Table(totals_data, colWidths=tot_col)
        tot_table.setStyle(TableStyle(tot_styles_list))
        story.append(tot_table)

    # ---- Memo / payment terms ----
    memo = (header.get("memo") or "").strip()
    if memo or payment_terms:
        story.append(Spacer(1, 14))
        story.append(HRFlowable(width="100%", thickness=0.5,
                                color=colors.Color(0.8, 0.8, 0.8), spaceAfter=8))
        if payment_terms:
            story.append(Paragraph(f"Payment Terms: {payment_terms}", style_small))
        if memo:
            story.append(Paragraph(f"Note: {memo}", style_small))

    # ------------------------------------------------------------------
    # 5. Build PDF with page numbers
    # ------------------------------------------------------------------
    def _on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(grey_rgb)
        canvas.drawRightString(
            LETTER[0] - 0.6 * inch,
            0.4 * inch,
            f"Page {doc.page}",
        )
        canvas.drawString(
            0.6 * inch,
            0.4 * inch,
            f"Invoice #{inv_number}  ·  {company_name}",
        )
        canvas.restoreState()

    doc = BaseDocTemplate(
        output_path,
        pagesize=LETTER,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.7 * inch,
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        id="normal",
    )
    doc.addPageTemplates([PageTemplate(id="main", frames=frame, onPage=_on_page)])
    doc.build(story)

    return output_path
