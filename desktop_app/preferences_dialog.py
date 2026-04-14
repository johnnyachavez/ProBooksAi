"""Edit → Preferences (minimal: Invoice Options)."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtPrintSupport import QPrinterInfo
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop_app.qt_mnemonic import message_box_warning_ok

from desktop_app.invoice_preferences import (
    get_invoice_output_folder,
    get_invoice_printer_name,
    invoice_preferences_qsettings,
    set_invoice_output_folder,
    set_invoice_printer_name,
)


class PreferencesDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setModal(True)
        root = QVBoxLayout(self)
        inv_box = QGroupBox("Invoice Options")
        inv_box.setToolTip(
            "Default folder for invoice PDFs when you click Save on the Invoice tab, "
            "and default printer for Print."
        )
        form = QFormLayout(inv_box)
        self._folder_edit = QLineEdit()
        self._folder_edit.setReadOnly(True)
        self._folder_edit.setPlaceholderText("No folder selected — you will be prompted on first Save")
        self._folder_edit.setText(get_invoice_output_folder())
        browse = QPushButton("Browse…")
        browse.setToolTip("Choose the folder where invoice PDF files are saved.")
        browse.clicked.connect(self._on_browse_folder)
        row_f = QHBoxLayout()
        row_f.addWidget(self._folder_edit, 1)
        row_f.addWidget(browse)
        wrap_f = QWidget()
        wrap_f.setLayout(row_f)
        form.addRow("Save location", wrap_f)

        self._printer_combo = QComboBox()
        self._printer_combo.setToolTip(
            "Default printer for the Invoice tab Print button. "
            "Choose a physical printer or a PDF/virtual printer if your system provides one."
        )
        self._refresh_printers()
        saved_pr = get_invoice_printer_name()
        if saved_pr:
            ix = self._printer_combo.findText(saved_pr)
            if ix >= 0:
                self._printer_combo.setCurrentIndex(ix)
            else:
                self._printer_combo.insertItem(0, saved_pr)
                self._printer_combo.setCurrentIndex(0)
        ref_btn = QPushButton("Refresh list")
        ref_btn.setToolTip("Reload the list of printers from the system.")
        ref_btn.clicked.connect(self._on_refresh_printers)
        row_p = QHBoxLayout()
        row_p.addWidget(self._printer_combo, 1)
        row_p.addWidget(ref_btn)
        wrap_p = QWidget()
        wrap_p.setLayout(row_p)
        form.addRow("Print destination", wrap_p)

        root.addWidget(inv_box)
        hint = QLabel(
            "If either choice is unset, the Invoice tab will ask once when you use Save or Print, "
            "then remember it here."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666; font-size: 11px;")
        root.addWidget(hint)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def _refresh_printers(self) -> None:
        cur = self._printer_combo.currentText() if self._printer_combo.count() else ""
        self._printer_combo.clear()
        for name in QPrinterInfo.availablePrinterNames():
            self._printer_combo.addItem(name)
        if cur:
            ix = self._printer_combo.findText(cur)
            if ix >= 0:
                self._printer_combo.setCurrentIndex(ix)

    def _on_refresh_printers(self) -> None:
        self._refresh_printers()

    def _on_browse_folder(self) -> None:
        start = self._folder_edit.text().strip() or str(Path.home())
        d = QFileDialog.getExistingDirectory(self, "Choose invoice save folder", start)
        if d:
            self._folder_edit.setText(os.path.normpath(d))

    def _on_accept(self) -> None:
        folder = self._folder_edit.text().strip()
        if folder and not os.path.isdir(folder):
            message_box_warning_ok(
                self,
                "Preferences",
                "The invoice save folder does not exist or is not accessible.",
                ok_tip="Close; pick an existing folder or clear the path.",
            )
            return
        set_invoice_output_folder(folder)

        pr = self._printer_combo.currentText().strip()
        set_invoice_printer_name(pr)

        invoice_preferences_qsettings().sync()
        self.accept()
