"""Persistent invoice and related workflow output settings (folders, printers).

Stored in the same ``QSettings`` scope as other ProBooks+ai desktop prefs
(``ProBooks+ai`` / ``ProBooks+ai``).

Includes **Enter Bills** PDF folder, **AR/AP payment receipt** PDF folder, and printers for
bill / payment print dialogs (separate from invoice printer name).
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
_INVOICE_SAVE_AS_FOLDER_PREFIX = "invoice_prefs/save_as_folder/"
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


def _save_as_folder_key(company_sid: str) -> str:
    sid = (company_sid or "").strip() or "default"
    return f"{_INVOICE_SAVE_AS_FOLDER_PREFIX}{sid}"


def get_invoice_save_as_folder(company_sid: str) -> str:
    """Last Save As folder for this PC and company file; empty if unset or missing on disk."""
    raw = (
        invoice_preferences_qsettings().value(
            _save_as_folder_key(company_sid), "", type=str
        )
        or ""
    )
    p = os.path.normpath(raw.strip()) if raw.strip() else ""
    if p and os.path.isdir(p):
        return p
    return ""


def set_invoice_save_as_folder(company_sid: str, path: str) -> None:
    qs = invoice_preferences_qsettings()
    key = _save_as_folder_key(company_sid)
    st = (path or "").strip()
    if st:
        qs.setValue(key, os.path.normpath(st))
    else:
        qs.remove(key)


def prompt_invoice_save_as_path(
    parent: QWidget | None,
    company_sid: str,
    default_basename: str,
) -> str | None:
    """Save As file dialog: editable name, default ``8114.pdf``, folder from last use.

    The name box gets the basename only (not the folder path). Remembers the
    chosen folder for this company on this PC. Caller asks before overwrite.
    """
    cur = get_invoice_save_as_folder(company_sid)
    if not cur:
        cur = get_invoice_output_folder()
    start = cur if cur else str(Path.home())
    name = (default_basename or "").strip() or "invoice.pdf"
    if not name.lower().endswith(".pdf"):
        name = f"{name}.pdf"
    name = os.path.basename(name)

    dlg = QFileDialog(parent, "Save invoice PDF")
    dlg.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
    dlg.setFileMode(QFileDialog.FileMode.AnyFile)
    dlg.setNameFilter("PDF files (*.pdf);;All files (*.*)")
    dlg.setDefaultSuffix("pdf")
    dlg.setDirectory(start)
    dlg.selectFile(name)
    dlg.setOption(QFileDialog.Option.DontConfirmOverwrite, True)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None
    files = dlg.selectedFiles()
    if not files:
        return None
    path = os.path.normpath(str(files[0]))
    if not path.lower().endswith(".pdf"):
        path = f"{path}.pdf"
    folder = os.path.dirname(path)
    if folder:
        set_invoice_save_as_folder(company_sid, folder)
    return path


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


_BILL_OUTPUT_FOLDER_KEY = "bill_prefs/output_folder"
_BILL_PRINTER_NAME_KEY = "bill_prefs/printer_name"

_PAYMENT_OUTPUT_FOLDER_KEY = "payment_prefs/output_folder"
_PAYMENT_PRINTER_NAME_KEY = "payment_prefs/printer_name"


def get_bill_output_folder() -> str:
    raw = invoice_preferences_qsettings().value(_BILL_OUTPUT_FOLDER_KEY, "", type=str) or ""
    p = os.path.normpath(raw.strip()) if raw.strip() else ""
    if p and os.path.isdir(p):
        return p
    return ""


def set_bill_output_folder(path: str) -> None:
    qs = invoice_preferences_qsettings()
    st = path.strip()
    if st:
        qs.setValue(_BILL_OUTPUT_FOLDER_KEY, os.path.normpath(st))
    else:
        qs.remove(_BILL_OUTPUT_FOLDER_KEY)


def get_bill_printer_name() -> str:
    return (invoice_preferences_qsettings().value(_BILL_PRINTER_NAME_KEY, "", type=str) or "").strip()


def set_bill_printer_name(name: str) -> None:
    qs = invoice_preferences_qsettings()
    st = (name or "").strip()
    if st:
        qs.setValue(_BILL_PRINTER_NAME_KEY, st)
    else:
        qs.remove(_BILL_PRINTER_NAME_KEY)


def ensure_bill_output_folder(parent: QWidget | None) -> str | None:
    """Writable folder for Enter Bills **Save** PDF copies; prompts once if unset."""
    cur = get_bill_output_folder()
    if cur and os.path.isdir(cur):
        return cur
    start = cur if cur else str(Path.home())
    chosen = QFileDialog.getExistingDirectory(
        parent,
        "Choose folder for bill PDF files",
        start,
    )
    if not chosen:
        return None
    norm = os.path.normpath(chosen)
    set_bill_output_folder(norm)
    return norm


def configure_printer_for_bill_print(parent: QWidget | None, printer: QPrinter) -> bool:
    names = list(QPrinterInfo.availablePrinterNames())
    saved = get_bill_printer_name()
    if saved and saved in names:
        printer.setPrinterName(saved)
        return True
    from PySide6.QtPrintSupport import QPrintDialog

    dlg = QPrintDialog(printer, parent)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return False
    chosen = (printer.printerName() or "").strip()
    if chosen:
        set_bill_printer_name(chosen)
    return True


def get_payment_output_folder() -> str:
    raw = invoice_preferences_qsettings().value(_PAYMENT_OUTPUT_FOLDER_KEY, "", type=str) or ""
    p = os.path.normpath(raw.strip()) if raw.strip() else ""
    if p and os.path.isdir(p):
        return p
    return ""


def set_payment_output_folder(path: str) -> None:
    qs = invoice_preferences_qsettings()
    st = path.strip()
    if st:
        qs.setValue(_PAYMENT_OUTPUT_FOLDER_KEY, os.path.normpath(st))
    else:
        qs.remove(_PAYMENT_OUTPUT_FOLDER_KEY)


def get_payment_printer_name() -> str:
    return (invoice_preferences_qsettings().value(_PAYMENT_PRINTER_NAME_KEY, "", type=str) or "").strip()


def set_payment_printer_name(name: str) -> None:
    qs = invoice_preferences_qsettings()
    st = (name or "").strip()
    if st:
        qs.setValue(_PAYMENT_PRINTER_NAME_KEY, st)
    else:
        qs.remove(_PAYMENT_PRINTER_NAME_KEY)


def ensure_payment_output_folder(parent: QWidget | None) -> str | None:
    """Folder for AR/AP payment receipt PDFs from **Save** / batch export paths."""
    cur = get_payment_output_folder()
    if cur and os.path.isdir(cur):
        return cur
    start = cur if cur else str(Path.home())
    chosen = QFileDialog.getExistingDirectory(
        parent,
        "Choose folder for payment receipt PDF files",
        start,
    )
    if not chosen:
        return None
    norm = os.path.normpath(chosen)
    set_payment_output_folder(norm)
    return norm


def configure_printer_for_payment_print(parent: QWidget | None, printer: QPrinter) -> bool:
    names = list(QPrinterInfo.availablePrinterNames())
    saved = get_payment_printer_name()
    if saved and saved in names:
        printer.setPrinterName(saved)
        return True
    from PySide6.QtPrintSupport import QPrintDialog

    dlg = QPrintDialog(printer, parent)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return False
    chosen = (printer.printerName() or "").strip()
    if chosen:
        set_payment_printer_name(chosen)
    return True


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
