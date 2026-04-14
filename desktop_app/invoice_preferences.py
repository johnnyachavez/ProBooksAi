"""Persistent invoice output settings (folder for Save, default printer for Print).

Stored in the same ``QSettings`` scope as other ProBooks+ai desktop prefs
(``ProBooks+ai`` / ``ProBooks+ai``).
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo
from PySide6.QtWidgets import QDialog, QFileDialog, QWidget


def invoice_preferences_qsettings() -> QSettings:
    return QSettings("ProBooks+ai", "ProBooks+ai")


_INVOICE_OUTPUT_FOLDER_KEY = "invoice_prefs/output_folder"
_INVOICE_PRINTER_NAME_KEY = "invoice_prefs/printer_name"


def get_invoice_output_folder() -> str:
    raw = invoice_preferences_qsettings().value(_INVOICE_OUTPUT_FOLDER_KEY, "", type=str) or ""
    p = os.path.normpath(raw.strip()) if raw.strip() else ""
    if p and os.path.isdir(p):
        return p
    return ""


def set_invoice_output_folder(path: str) -> None:
    qs = invoice_preferences_qsettings()
    st = path.strip()
    if st:
        qs.setValue(_INVOICE_OUTPUT_FOLDER_KEY, os.path.normpath(st))
    else:
        qs.remove(_INVOICE_OUTPUT_FOLDER_KEY)


def get_invoice_printer_name() -> str:
    return (invoice_preferences_qsettings().value(_INVOICE_PRINTER_NAME_KEY, "", type=str) or "").strip()


def set_invoice_printer_name(name: str) -> None:
    qs = invoice_preferences_qsettings()
    st = (name or "").strip()
    if st:
        qs.setValue(_INVOICE_PRINTER_NAME_KEY, st)
    else:
        qs.remove(_INVOICE_PRINTER_NAME_KEY)


def ensure_invoice_output_folder(parent: QWidget | None) -> str | None:
    """Return a writable folder path, prompting once if unset or missing on disk."""
    cur = get_invoice_output_folder()
    if cur and os.path.isdir(cur):
        return cur
    start = cur if cur else str(Path.home())
    chosen = QFileDialog.getExistingDirectory(
        parent,
        "Choose folder for invoice PDF files",
        start,
    )
    if not chosen:
        return None
    norm = os.path.normpath(chosen)
    set_invoice_output_folder(norm)
    return norm


def configure_printer_for_invoice_print(parent: QWidget | None, printer: QPrinter) -> bool:
    """Apply saved printer name if still available; otherwise show ``QPrintDialog`` once and save choice.

    Returns ``True`` if *printer* is ready to print; ``False`` if the user cancelled the dialog.
    """
    names = list(QPrinterInfo.availablePrinterNames())
    saved = get_invoice_printer_name()
    if saved and saved in names:
        printer.setPrinterName(saved)
        return True
    from PySide6.QtPrintSupport import QPrintDialog

    dlg = QPrintDialog(printer, parent)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return False
    chosen = (printer.printerName() or "").strip()
    if chosen:
        set_invoice_printer_name(chosen)
    return True
