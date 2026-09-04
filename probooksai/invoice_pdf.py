"""
probooksai.invoice_pdf
=======================
Render an invoice PDF for headless callers (FastAPI ``GET /invoices/{id}/pdf``, the
Telegram bot, scripts).

Usage
-----
    from probooksai.invoice_pdf import render_invoice_pdf
    path = render_invoice_pdf(conn, invoice_id, output_path="/tmp/INV-001.pdf")

This is a thin wrapper around the desktop **Print / Save As PDF** path
(:func:`desktop_app.invoice_pdf.save_invoice_pdf` → the Chavan layout in
:mod:`desktop_app.invoice_print_html`), so a PDF downloaded from the API or sent by the
bot is byte-for-byte the same paper template the desktop prints:

  • Company letterhead from My Company / Company setup (name, address, phone, email,
    MC #, DOT #) — never hardcoded
  • INVOICE title with invoice number and date
  • BILL TO, PO / CONTRACT #, NAME / JOB #
  • Grid: Serviced On, JL #, Description, BOL#, Qty, Rate, Amount
  • Subtotal, CO / compliance-fee line, Total
  • Terms (NET 30) and the thank-you footer
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Optional


def _db_file_path(conn: sqlite3.Connection) -> str:
    """Filesystem path behind *conn*, or '' for in-memory / URI databases."""
    try:
        rows = conn.execute("PRAGMA database_list").fetchall()
    except sqlite3.Error:
        return ""
    for row in rows:
        name = str(row[1] if not isinstance(row, sqlite3.Row) else row["name"])
        file = str(row[2] if not isinstance(row, sqlite3.Row) else row["file"])
        if name == "main":
            return (file or "").strip()
    return ""


def _render_in_child_process(db_path: str, invoice_id: int, output_path: str) -> None:
    """Run the Qt render in a child process (Qt refuses to start off the main thread)."""
    import os
    import subprocess
    import sys

    env = os.environ.copy()
    if not (env.get("DISPLAY") or env.get("WAYLAND_DISPLAY")):
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
    repo_root = str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"] = os.pathsep.join(p for p in (repo_root, env.get("PYTHONPATH", "")) if p)
    code = (
        "import sqlite3\n"
        "from desktop_app.invoice_pdf import save_invoice_pdf\n"
        f"c = sqlite3.connect({db_path!r})\n"
        "c.row_factory = sqlite3.Row\n"
        f"save_invoice_pdf(c, {invoice_id}, {output_path!r})\n"
        "c.close()\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Invoice PDF render failed: {(proc.stderr or proc.stdout).strip()}"
        )


def render_invoice_pdf(
    conn: sqlite3.Connection,
    invoice_id: int,
    output_path: Optional[str] = None,
) -> str:
    """
    Render invoice *invoice_id* to a PDF file using the shared print/PDF template.

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
    ImportError if PySide6 (Qt print support) is not installed
    RuntimeError if the child-process render fails

    Server requests are handled on worker threads, where Qt cannot be started, so a
    file-backed company DB is rendered in a child process instead.
    """
    from probooksai.business import get_invoice_detail

    header, _lines = get_invoice_detail(conn, invoice_id)
    if not header:
        raise ValueError(f"Invoice {invoice_id} not found.")

    if not output_path:
        import tempfile

        inv_num = (dict(header).get("invoice_number") or str(invoice_id)).replace("/", "-")
        tmp = tempfile.NamedTemporaryFile(
            suffix=".pdf", prefix=f"invoice_{inv_num}_", delete=False
        )
        tmp.close()
        output_path = tmp.name

    output_path = str(Path(output_path).resolve())

    db_path = _db_file_path(conn)
    if db_path and threading.current_thread() is not threading.main_thread():
        _render_in_child_process(db_path, invoice_id, output_path)
        return output_path

    try:
        from desktop_app.invoice_pdf import save_invoice_pdf

        save_invoice_pdf(conn, invoice_id, output_path)
    except ImportError as err:  # pragma: no cover - depends on install extras
        raise ImportError(
            "PySide6 is required for PDF invoice generation. "
            "Install with: pip install PySide6"
        ) from err
    return output_path
