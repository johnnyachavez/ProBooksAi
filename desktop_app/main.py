"""
ProBooksAi Desktop Application
================================
Run with:
    python -m desktop_app.main

Or directly:
    python desktop_app/main.py

Requires PySide6:
    pip install PySide6
"""

from __future__ import annotations

import mimetypes
import os
import sys
from pathlib import Path

from PySide6.QtCore import (
    Qt, QThread, Signal, QMimeData,
)
from PySide6.QtGui import (
    QAction, QColor, QDragEnterEvent, QDropEvent,
    QIcon, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QSizePolicy, QSplitter,
    QStatusBar, QTableWidget, QTableWidgetItem, QToolBar,
    QVBoxLayout, QWidget,
)

from probooksai.database import DocumentDatabase
from probooksai.coa import coa_display_list, load_coa

# Accepted MIME types / file extensions
ACCEPTED_MIMES = {"application/pdf", "image/jpeg", "image/png"}
ACCEPTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}

STATUS_COLORS = {
    "New":          "#2196F3",   # blue
    "Extracted":    "#9C27B0",   # purple
    "Needs Review": "#FF9800",   # amber
    "Approved":     "#4CAF50",   # green
    "Posted":       "#607D8B",   # blue-grey
    "Error":        "#F44336",   # red
}


# ---------------------------------------------------------------------------
# Background worker – runs AI extraction off the UI thread
# ---------------------------------------------------------------------------

class AIWorker(QThread):
    finished = Signal(object, object)   # (ExtractionResult, CategorySuggestions | None)
    error    = Signal(str)

    def __init__(self, doc_id: int, path: str, mimetype: str, coa: list):
        super().__init__()
        self._doc_id  = doc_id
        self._path    = path
        self._mimetype = mimetype
        self._coa     = coa

    def run(self):
        try:
            from ai.extractor import extract_document
            from ai.categorizer import suggest_categories

            result = extract_document(self._path, self._mimetype)
            if result.error:
                self.error.emit(result.error)
                return

            suggestions = suggest_categories(result, self._coa)
            self.finished.emit(result, suggestions)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Inbox list (left panel)
# ---------------------------------------------------------------------------

class InboxWidget(QTableWidget):
    """Displays imported documents with their statuses."""

    COLUMNS = ["#", "Filename", "Type", "Status", "Date"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(len(self.COLUMNS))
        self.setHorizontalHeaderLabels(self.COLUMNS)
        self.horizontalHeader().setStretchLastSection(False)
        self.horizontalHeader().setDefaultSectionSize(110)
        self.setColumnWidth(0, 40)
        self.setColumnWidth(1, 220)
        self.setColumnWidth(2, 80)
        self.setColumnWidth(3, 110)
        self.setColumnWidth(4, 120)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.setAcceptDrops(True)

    # -- drag & drop ---------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
        if paths:
            self.filesDropped.emit(paths)

    filesDropped = Signal(list)

    # -- population ----------------------------------------------------------

    def populate(self, rows: list):
        self.setRowCount(0)
        for row in rows:
            r = self.rowCount()
            self.insertRow(r)
            self.setItem(r, 0, QTableWidgetItem(str(row["id"])))
            self.setItem(r, 1, QTableWidgetItem(row["filename"]))
            mime = row["mimetype"] or ""
            doc_type = "PDF" if "pdf" in mime else "Image"
            self.setItem(r, 2, QTableWidgetItem(doc_type))
            status = row["status"]
            status_item = QTableWidgetItem(status)
            color = STATUS_COLORS.get(status, "#000000")
            status_item.setForeground(QColor(color))
            self.setItem(r, 3, status_item)
            date_str = (row["import_date"] or "")[:10]
            self.setItem(r, 4, QTableWidgetItem(date_str))

    def selected_doc_id(self) -> int | None:
        rows = self.selectedItems()
        if not rows:
            return None
        r = self.currentRow()
        id_item = self.item(r, 0)
        return int(id_item.text()) if id_item else None


# ---------------------------------------------------------------------------
# Detail pane (right panel)
# ---------------------------------------------------------------------------

class DetailPane(QScrollArea):
    """Shows document preview + extracted fields + action buttons."""

    runAI      = Signal(int)    # doc_id
    approve    = Signal(int)
    markPosted = Signal(int)
    reject     = Signal(int)

    def __init__(self, coa_list: list[str], parent=None):
        super().__init__(parent)
        self._doc_id: int | None = None
        self._coa_list = coa_list

        inner = QWidget()
        self.setWidget(inner)
        self.setWidgetResizable(True)

        layout = QVBoxLayout(inner)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # -- Document info ---------------------------------------------------
        self._lbl_filename = QLabel("No document selected")
        self._lbl_filename.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self._lbl_filename)

        self._lbl_status = QLabel("")
        layout.addWidget(self._lbl_status)

        # -- Preview ---------------------------------------------------------
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout(preview_group)
        self._preview_label = QLabel("(Select a document to preview)")
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setMinimumHeight(180)
        self._preview_label.setStyleSheet("background: #f0f0f0; border: 1px solid #ccc;")
        preview_layout.addWidget(self._preview_label)
        layout.addWidget(preview_group)

        # -- Extracted fields ------------------------------------------------
        fields_group = QGroupBox("Extracted Fields")
        form = QFormLayout(fields_group)

        self._f_vendor   = QLineEdit()
        self._f_doctype  = QComboBox()
        self._f_doctype.addItems(["invoice", "bill", "receipt", "credit_note", "other"])
        self._f_inv_num  = QLineEdit()
        self._f_date     = QLineEdit()
        self._f_due_date = QLineEdit()
        self._f_subtotal = QDoubleSpinBox(); self._f_subtotal.setMaximum(9_999_999); self._f_subtotal.setDecimals(2)
        self._f_tax      = QDoubleSpinBox(); self._f_tax.setMaximum(9_999_999); self._f_tax.setDecimals(2)
        self._f_total    = QDoubleSpinBox(); self._f_total.setMaximum(9_999_999); self._f_total.setDecimals(2)
        self._f_currency = QLineEdit(); self._f_currency.setMaxLength(3); self._f_currency.setFixedWidth(55)
        self._f_notes    = QPlainTextEdit(); self._f_notes.setFixedHeight(60)

        form.addRow("Vendor / Customer:", self._f_vendor)
        form.addRow("Doc Type:", self._f_doctype)
        form.addRow("Invoice #:", self._f_inv_num)
        form.addRow("Date:", self._f_date)
        form.addRow("Due Date:", self._f_due_date)
        form.addRow("Subtotal:", self._f_subtotal)
        form.addRow("Tax:", self._f_tax)
        form.addRow("Total:", self._f_total)
        form.addRow("Currency:", self._f_currency)
        form.addRow("Notes:", self._f_notes)

        layout.addWidget(fields_group)

        # -- Categorisation --------------------------------------------------
        cat_group = QGroupBox("Categorisation Suggestions")
        cat_layout = QFormLayout(cat_group)

        self._f_coa      = QComboBox()
        self._f_coa.addItems(["– select –"] + coa_list)
        self._f_coa.setEditable(True)
        self._f_tax_cat  = QLineEdit()
        self._f_confidence = QLabel("–")

        cat_layout.addRow("COA Account:", self._f_coa)
        cat_layout.addRow("Tax Category:", self._f_tax_cat)
        cat_layout.addRow("AI Confidence:", self._f_confidence)

        self._lbl_rationale = QLabel("")
        self._lbl_rationale.setWordWrap(True)
        self._lbl_rationale.setStyleSheet("color: #555; font-style: italic;")
        cat_layout.addRow("Rationale:", self._lbl_rationale)

        layout.addWidget(cat_group)

        # -- Action buttons --------------------------------------------------
        btn_layout = QHBoxLayout()
        self._btn_run     = QPushButton("⚡ Run AI")
        self._btn_approve = QPushButton("✅ Approve")
        self._btn_post    = QPushButton("📤 Mark Posted")
        self._btn_reject  = QPushButton("❌ Reject")

        for btn in (self._btn_run, self._btn_approve, self._btn_post, self._btn_reject):
            btn.setMinimumHeight(32)
            btn_layout.addWidget(btn)

        self._btn_run.setStyleSheet("background: #2196F3; color: white; font-weight: bold;")
        self._btn_approve.setStyleSheet("background: #4CAF50; color: white; font-weight: bold;")
        self._btn_post.setStyleSheet("background: #607D8B; color: white; font-weight: bold;")
        self._btn_reject.setStyleSheet("background: #F44336; color: white; font-weight: bold;")

        self._btn_run.clicked.connect(self._on_run_ai)
        self._btn_approve.clicked.connect(self._on_approve)
        self._btn_post.clicked.connect(self._on_post)
        self._btn_reject.clicked.connect(self._on_reject)

        layout.addLayout(btn_layout)
        layout.addStretch()

        self._set_buttons_enabled(False)

    # -- public interface ----------------------------------------------------

    def load_document(self, doc_id: int, db: DocumentDatabase):
        self._doc_id = doc_id
        row = db.get_document(doc_id)
        if not row:
            return
        self._lbl_filename.setText(row["filename"])
        status = row["status"]
        color  = STATUS_COLORS.get(status, "#000")
        self._lbl_status.setText(f"Status: <b style='color:{color}'>{status}</b>")
        self._lbl_status.setTextFormat(Qt.TextFormat.RichText)

        self._show_preview(row["stored_path"], row["mimetype"], row["page_count"])

        # Fill from approved values if present, else from extraction
        approved = db.get_approved(doc_id)
        extraction = db.get_latest_extraction(doc_id)
        src = approved or extraction
        self._populate_fields(src)

        # Categorisation
        if approved:
            self._f_coa.setCurrentText(approved["coa_account"] or "")
            self._f_tax_cat.setText(approved["tax_category"] or "")

        self._set_buttons_enabled(True)

    def populate_ai_result(self, result, suggestions=None):
        """Fill the form with AI extraction + categorisation results."""
        self._populate_fields_from_extraction(result)
        if suggestions and not suggestions.error:
            idx = self._f_coa.findText(suggestions.coa_account or "")
            if idx >= 0:
                self._f_coa.setCurrentIndex(idx)
            else:
                self._f_coa.setEditText(suggestions.coa_account or "")
            self._f_tax_cat.setText(suggestions.tax_category or "")
            conf = suggestions.confidence
            self._f_confidence.setText(f"{conf:.0%}")
            self._lbl_rationale.setText(suggestions.rationale or "")

    def collect_approved_values(self) -> dict:
        """Return the current form values as a dict for saving."""
        return {
            "vendor":         self._f_vendor.text().strip() or None,
            "doc_type":       self._f_doctype.currentText(),
            "invoice_number": self._f_inv_num.text().strip() or None,
            "doc_date":       self._f_date.text().strip() or None,
            "due_date":       self._f_due_date.text().strip() or None,
            "subtotal":       self._f_subtotal.value() or None,
            "tax":            self._f_tax.value() or None,
            "total":          self._f_total.value() or None,
            "currency":       self._f_currency.text().strip() or "USD",
            "notes":          self._f_notes.toPlainText().strip() or None,
            "coa_account":    self._f_coa.currentText().strip() or None,
            "tax_category":   self._f_tax_cat.text().strip() or None,
        }

    # -- private helpers -----------------------------------------------------

    def _show_preview(self, stored_path: str, mimetype: str, page_count):
        if mimetype and mimetype.startswith("image/"):
            pix = QPixmap(stored_path)
            if not pix.isNull():
                pix = pix.scaled(
                    400, 300,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._preview_label.setPixmap(pix)
                self._preview_label.setText("")
                return
        elif mimetype == "application/pdf":
            pages = page_count or "?"
            self._preview_label.setPixmap(QPixmap())
            self._preview_label.setText(
                f"📄 PDF document\n{Path(stored_path).name}\n{pages} page(s)"
            )
            return
        self._preview_label.setPixmap(QPixmap())
        self._preview_label.setText("(No preview available)")

    def _populate_fields(self, row):
        if not row:
            return
        self._f_vendor.setText(row["vendor"] or "")
        idx = self._f_doctype.findText(row["doc_type"] or "")
        if idx >= 0:
            self._f_doctype.setCurrentIndex(idx)
        self._f_inv_num.setText(row["invoice_number"] or "")
        self._f_date.setText(row["doc_date"] or "")
        self._f_due_date.setText(row["due_date"] or "")
        self._f_subtotal.setValue(float(row["subtotal"] or 0))
        self._f_tax.setValue(float(row["tax"] or 0))
        self._f_total.setValue(float(row["total"] or 0))
        self._f_currency.setText(row["currency"] or "USD")
        self._f_notes.setPlainText(row["notes"] or "")

    def _populate_fields_from_extraction(self, result):
        self._f_vendor.setText(result.vendor or "")
        idx = self._f_doctype.findText(result.doc_type or "")
        if idx >= 0:
            self._f_doctype.setCurrentIndex(idx)
        self._f_inv_num.setText(result.invoice_number or "")
        self._f_date.setText(result.doc_date or "")
        self._f_due_date.setText(result.due_date or "")
        self._f_subtotal.setValue(float(result.subtotal or 0))
        self._f_tax.setValue(float(result.tax or 0))
        self._f_total.setValue(float(result.total or 0))
        self._f_currency.setText(result.currency or "USD")
        self._f_notes.setPlainText(result.notes or "")
        self._f_confidence.setText(f"{result.confidence:.0%}")

    def _set_buttons_enabled(self, enabled: bool):
        for btn in (self._btn_run, self._btn_approve, self._btn_post, self._btn_reject):
            btn.setEnabled(enabled)

    # -- button slots --------------------------------------------------------

    def _on_run_ai(self):
        if self._doc_id is not None:
            self.runAI.emit(self._doc_id)

    def _on_approve(self):
        if self._doc_id is not None:
            self.approve.emit(self._doc_id)

    def _on_post(self):
        if self._doc_id is not None:
            self.markPosted.emit(self._doc_id)

    def _on_reject(self):
        if self._doc_id is not None:
            self.reject.emit(self._doc_id)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ProBooksAi – Document Intake")
        self.resize(1100, 700)

        self._db   = DocumentDatabase()
        self._coa  = load_coa()
        self._worker: AIWorker | None = None

        self._build_ui()
        self._refresh_inbox()

    # -- UI construction -----------------------------------------------------

    def _build_ui(self):
        # Toolbar
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        act_import = QAction("📂  Import Documents…", self)
        act_import.setShortcut("Ctrl+O")
        act_import.triggered.connect(self._on_import)
        toolbar.addAction(act_import)

        toolbar.addSeparator()

        act_refresh = QAction("🔄  Refresh", self)
        act_refresh.triggered.connect(self._refresh_inbox)
        toolbar.addAction(act_refresh)

        # Central splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(splitter)

        # Left: inbox
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        lbl_inbox = QLabel("  Document Inbox")
        lbl_inbox.setStyleSheet(
            "background: #1F3864; color: white; font-weight: bold; "
            "font-size: 13px; padding: 6px;"
        )
        left_layout.addWidget(lbl_inbox)

        self._inbox = InboxWidget()
        self._inbox.filesDropped.connect(self._on_files_dropped)
        self._inbox.itemSelectionChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self._inbox)

        splitter.addWidget(left)

        # Right: detail pane
        coa_display = coa_display_list(self._coa)
        self._detail = DetailPane(coa_display)
        self._detail.runAI.connect(self._on_run_ai)
        self._detail.approve.connect(self._on_approve)
        self._detail.markPosted.connect(self._on_mark_posted)
        self._detail.reject.connect(self._on_reject)
        splitter.addWidget(self._detail)

        splitter.setSizes([380, 720])

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready – drag & drop documents or use Import.")

        # Drag & drop on the main window itself
        self.setAcceptDrops(True)

    # -- drag & drop on window -----------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self._import_files(paths)

    # -- slots ---------------------------------------------------------------

    def _on_import(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Import Documents",
            "",
            "Documents (*.pdf *.jpg *.jpeg *.png);;All Files (*.*)",
        )
        if paths:
            self._import_files(paths)

    def _on_files_dropped(self, paths: list[str]):
        self._import_files(paths)

    def _import_files(self, paths: list[str]):
        imported = 0
        skipped  = []
        for path in paths:
            ext = Path(path).suffix.lower()
            if ext not in ACCEPTED_EXTENSIONS:
                skipped.append(Path(path).name)
                continue
            mime, _ = mimetypes.guess_type(path)
            mime = mime or ("application/pdf" if ext == ".pdf" else "image/jpeg")
            try:
                self._db.add_document(path, mime, store=True)
                imported += 1
            except Exception as exc:
                self._status_bar.showMessage(f"Error importing {Path(path).name}: {exc}")

        self._refresh_inbox()
        if skipped:
            QMessageBox.warning(
                self, "Skipped Files",
                f"The following files were skipped (unsupported type):\n"
                + "\n".join(skipped),
            )
        if imported:
            self._status_bar.showMessage(f"Imported {imported} document(s).")

    def _on_selection_changed(self):
        doc_id = self._inbox.selected_doc_id()
        if doc_id is not None:
            self._detail.load_document(doc_id, self._db)

    def _on_run_ai(self, doc_id: int):
        if self._worker and self._worker.isRunning():
            QMessageBox.information(self, "AI Running", "Please wait – AI extraction is already in progress.")
            return

        row = self._db.get_document(doc_id)
        if not row:
            return

        # Check API key
        if not os.environ.get("OPENAI_API_KEY"):
            QMessageBox.warning(
                self, "API Key Missing",
                "OPENAI_API_KEY is not set.\n\n"
                "Set the environment variable before starting the application:\n"
                "  set OPENAI_API_KEY=sk-...",
            )
            return

        self._status_bar.showMessage(f"Running AI extraction on {row['filename']}…")
        self._db.set_status(doc_id, "Extracted")

        self._worker = AIWorker(doc_id, row["stored_path"], row["mimetype"], self._coa)
        self._worker.finished.connect(lambda res, sug: self._on_ai_done(doc_id, res, sug))
        self._worker.error.connect(lambda err: self._on_ai_error(doc_id, err))
        self._worker.start()

    def _on_ai_done(self, doc_id: int, result, suggestions):
        self._db.save_extraction(doc_id, result)
        self._db.set_status(doc_id, "Needs Review")
        self._detail.populate_ai_result(result, suggestions)
        self._refresh_inbox()
        doc = self._db.get_document(doc_id)
        name = doc["filename"] if doc else str(doc_id)
        self._status_bar.showMessage(f"AI extraction complete for {name}.")

    def _on_ai_error(self, doc_id: int, error: str):
        self._db.set_status(doc_id, "Error")
        self._refresh_inbox()
        QMessageBox.critical(self, "AI Extraction Failed", f"Error:\n{error}")
        self._status_bar.showMessage("AI extraction failed.")

    def _on_approve(self, doc_id: int):
        values = self._detail.collect_approved_values()
        self._db.save_approved(doc_id, values)
        self._db.set_status(doc_id, "Approved")
        self._refresh_inbox()
        self._detail.load_document(doc_id, self._db)
        self._status_bar.showMessage("Document approved and values saved.")

    def _on_mark_posted(self, doc_id: int):
        row = self._db.get_document(doc_id)
        if row and row["status"] != "Approved":
            QMessageBox.warning(
                self, "Not Yet Approved",
                "Please approve the document before marking it as Posted.",
            )
            return
        self._db.set_status(doc_id, "Posted")
        self._refresh_inbox()
        self._detail.load_document(doc_id, self._db)
        self._status_bar.showMessage("Document marked as Posted.")

    def _on_reject(self, doc_id: int):
        self._db.set_status(doc_id, "Needs Review")
        self._refresh_inbox()
        self._detail.load_document(doc_id, self._db)
        self._status_bar.showMessage("Document flagged – Needs Review.")

    # -- helpers -------------------------------------------------------------

    def _refresh_inbox(self):
        docs = self._db.list_documents()
        self._inbox.populate(docs)

    def closeEvent(self, event):
        self._db.close()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ProBooksAi")
    app.setOrganizationName("ProBooksAi")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
