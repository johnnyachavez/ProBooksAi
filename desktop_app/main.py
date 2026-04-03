"""
ProBooks+ai desktop application
===============================
Run with:
    python -m desktop_app.main

Or directly:
    python desktop_app/main.py

Requires PySide6:
    pip install PySide6

``--help`` prints the shared Excel COA workbook line from ``probooks/help_epilog.py`` (see README Desktop + Excel template).

The **central** **QWidget** (banner + tab widget) has a margin hover hint. The main **QToolBar** has a hover hint for Document Intake import/refresh. Document Intake: **F5** refreshes the inbox; **Help → Document intake shortcuts…** (``message_box_information_ok`` **Ok** tooltip) and inbox **right-click**
**Keyboard shortcuts…** (including empty area) match that dialog. The **InboxWidget** grid has a hover **tooltip**
(import, drag-and-drop, F5, shortcuts). The intake **QSplitter** has a resize hint on hover. **DetailPane** (**QScrollArea**) has a window-level hover hint; its inner **QWidget** has a content-area hint; preview, extracted **LineEdit** / spin fields, **Doc Type**,
**COA Account**, **AI confidence** / **rationale** labels, and action buttons use **tooltips**.
**Preview** / **Extracted Fields** / **Categorisation** group boxes and the **filename** / **status** labels
also have hover hints. The banner **QFrame** and its **ProBooks+ai** / company **QLabel**s have tooltips.
**Help → About** uses ``message_box_about_ok`` (rich text + **Ok** hover hint). The main **QTabWidget** sets a **setToolTip** on the tab strip area; its tab bar sets **setTabToolTip** on each top-level tab (Intake through Audit log). **Document Intake**’s root **QWidget** has a hover hint for the whole tab; the inbox **column** **QWidget** (left splitter pane) has a short margin hint.
Destructive **Yes**/**No** prompts (new company file exists, database restore) use **tip_message_box_buttons** for button hover hints and **QMessageBox.setToolTip** for the dialog window.

Main window **menu bar**: each ``QAction`` uses ``setStatusTip`` for the **status bar** and the same text via ``setToolTip`` for hover (``_menu_action_tip`` helper).
"""

from __future__ import annotations

import argparse
import mimetypes
import os
import sqlite3
import sys
from functools import partial
from pathlib import Path

from PySide6.QtCore import (
    Qt, QThread, Signal, QMimeData, QSettings, QUrl, qInstallMessageHandler,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QIcon,
    QKeySequence,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QSizePolicy, QSplitter,
    QStatusBar, QTabWidget, QTableWidget, QToolBar,
    QVBoxLayout, QWidget,
)

from probooks.backup import backup_database, restore_database
from probooks.help_epilog import EXCEL_COA_WORKBOOK_ARGPARSE_EPILOG
from probooks.paths import default_intake_db_path
from probooksai.database import DocumentDatabase
from probooksai.html_escape import escape_html_text
from probooksai.coa import coa_display_list, load_coa
from probooksai.bank_import import BankDatabase
from probooksai.coa_db import COADatabase
from probooksai.extensions_schema import apply_extensions
from probooksai.gl import GLDatabase
from desktop_app.bank_import_tab import (
    BankImportTab,
    show_bank_import_keyboard_shortcuts_dialog,
)
from desktop_app.coa_tab import COATab
from desktop_app.register_tab import RegisterTab, show_register_keyboard_shortcuts_dialog
from desktop_app.reports_tab import ReportsTab
from desktop_app.journal_tab import JournalTab
from desktop_app.extra_tabs import BusinessHub, show_business_keyboard_shortcuts_dialog
from desktop_app.audit_tab import AuditTab
from desktop_app.theme import apply_dark_theme, STATUS_COLORS as THEME_STATUS_COLORS
from desktop_app.version import application_version
from desktop_app.local_docs import resolve_local_roadmap_path
from desktop_app.more_main_tabs_shortcuts import (
    show_more_main_tabs_keyboard_shortcuts_dialog,
)
from desktop_app.table_clipboard import (
    IntSortTableItem,
    copy_table_row_as_tsv,
    plain_display_table_item,
    table_cell_clipboard_text,
)
from desktop_app.qt_mnemonic import (
    escape_ampersand_for_qt,
    message_box_about_ok,
    message_box_critical_ok,
    message_box_information_ok,
    message_box_warning_ok,
    tip_message_box_buttons,
)


def _document_intake_keyboard_shortcuts_help_text() -> str:
    """Plain text for **Help → Document intake shortcuts…** (aligned with **F5** / **InboxWidget**)."""
    return (
        "These shortcuts apply when Document Intake or its controls have focus:\n\n"
        "Menu bar: hover File, View, Edit, Help, or Tools to see shortcut and action hints "
        "in the status bar and on hover for each menu item.\n\n"
        "F5 — Refresh the document list (same as toolbar Refresh).\n\n"
        "Detail pane: Run AI, Approve, Mark Posted, and Reject have short descriptions on hover.\n\n"
        "File menu:\n"
        "Ctrl+O — Import documents… (toolbar Import Documents is the same command).\n"
        "Backup company file… / Restore from backup… — SQLite online backup (probooks.backup), "
        "same path as the CLI; no default shortcuts — hover each action for status-bar tips.\n\n"
        "View menu:\n"
        "Ctrl+1 Document Intake, Ctrl+2 Bank Import, Ctrl+3 Register, Ctrl+4 Chart of Accounts, "
        "Ctrl+5 Reports, Ctrl+6 Journal, Ctrl+7 Business, Ctrl+8 Audit log.\n\n"
        "Right-click the inbox grid (including empty area) for Keyboard shortcuts… "
        "(same as this dialog).\n\n"
        "COA, Journal, Reports, Audit:\n"
        "Help → More tab shortcuts (F5)…\n\n"
        "Business:\n"
        "Help → Business shortcuts…\n\n"
        "Bank workflows:\n"
        "Help → Bank import shortcuts…\n"
        "Help → Bank register keyboard shortcuts…\n"
    )


def show_document_intake_keyboard_shortcuts_dialog(parent: QWidget) -> None:
    message_box_information_ok(
        parent,
        "Document intake shortcuts",
        _document_intake_keyboard_shortcuts_help_text(),
        ok_tip="Close this help summary; shortcuts apply when Document Intake has focus.",
    )


# Accepted MIME types / file extensions
ACCEPTED_MIMES = {"application/pdf", "image/jpeg", "image/png"}
ACCEPTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}

STATUS_COLORS = THEME_STATUS_COLORS

INBOX_HEADER_COLOR = "#1F3864"  # dark navy – matches ProBooks+ai branding

COMPANY_NAME = "CHAVAN TRUCKING CORPORATION"  # placeholder – replace with real company/file name


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
    """Displays imported documents with their statuses.

    Context menu actions set **setToolTip** for **Keyboard shortcuts…** and **Copy row**.
    """

    COLUMNS = ["#", "Filename", "Type", "Status", "Date"]

    filesDropped = Signal(list)

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
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.setSortingEnabled(True)
        self.setToolTip(
            "Imported documents: click a row to open it in the detail pane. "
            "Drag PDF or image files here to import. F5 refreshes the list. "
            "Right-click for Keyboard shortcuts… (including on empty area)."
        )

    def _on_context_menu(self, pos):
        idx = self.indexAt(pos)
        m = QMenu(self)
        act_keys = m.addAction(
            "Keyboard shortcuts…",
            lambda: show_document_intake_keyboard_shortcuts_dialog(self),
        )
        act_keys.setToolTip(
            "Same summary as Help → Document intake shortcuts… "
            "(F5, Ctrl+O, File → Backup/Restore, View chords, links to other Help topics)."
        )
        if not idx.isValid():
            m.exec(self.viewport().mapToGlobal(pos))
            return
        row = idx.row()
        m.addSeparator()
        act_copy = m.addAction("Copy row", partial(copy_table_row_as_tsv, self, row))
        act_copy.setToolTip(
            "Copy this inbox row as tab-separated text for pasting into a spreadsheet or editor."
        )
        m.exec(self.viewport().mapToGlobal(pos))

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

    # -- population ----------------------------------------------------------

    def populate(self, rows: list):
        self.setSortingEnabled(False)
        self.setRowCount(len(rows))
        for r, row in enumerate(rows):
            did = int(row["id"])
            id_cell = IntSortTableItem(str(did), did)
            id_cell.setData(Qt.ItemDataRole.UserRole, did)
            self.setItem(r, 0, id_cell)
            fn = row["filename"] or ""
            self.setItem(r, 1, plain_display_table_item(fn))
            mime = row["mimetype"] or ""
            doc_type = "PDF" if "pdf" in mime else "Image"
            self.setItem(r, 2, plain_display_table_item(doc_type))
            status = row["status"]
            status_item = plain_display_table_item(str(status or ""))
            color = STATUS_COLORS.get(status, "#000000")
            status_item.setForeground(QColor(color))
            self.setItem(r, 3, status_item)
            date_str = (row["import_date"] or "")[:10]
            self.setItem(r, 4, plain_display_table_item(date_str))
        self.setSortingEnabled(True)

    def selected_doc_id(self) -> int | None:
        rows = self.selectedItems()
        if not rows:
            return None
        r = self.currentRow()
        it = self.item(r, 0)
        if it is not None:
            eid = it.data(Qt.ItemDataRole.UserRole)
            if eid is not None:
                try:
                    return int(eid)
                except (TypeError, ValueError):
                    pass
        raw = table_cell_clipboard_text(self, r, 0).strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None


# ---------------------------------------------------------------------------
# Detail pane (right panel)
# ---------------------------------------------------------------------------

_COA_SELECT_LABEL = "– select –"


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
        inner.setToolTip(
            "Preview, extracted fields, categorization, and action buttons for the selected inbox row (scroll when content is tall)."
        )
        self.setWidget(inner)
        self.setWidgetResizable(True)
        self.setToolTip(
            "Scroll the detail pane: preview, extracted fields, categorization, and workflow actions for the selected inbox row."
        )

        layout = QVBoxLayout(inner)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # -- Document info ---------------------------------------------------
        self._lbl_filename = QLabel("No document selected")
        self._lbl_filename.setTextFormat(Qt.TextFormat.PlainText)
        self._lbl_filename.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._lbl_filename.setToolTip(
            "File name of the document selected in the inbox (left list)."
        )
        layout.addWidget(self._lbl_filename)

        self._lbl_status = QLabel("")
        self._lbl_status.setToolTip(
            "Workflow status for the selected document (e.g. new, approved, posted)."
        )
        layout.addWidget(self._lbl_status)

        # -- Preview ---------------------------------------------------------
        preview_group = QGroupBox("Preview")
        preview_group.setToolTip(
            "Visual preview of the selected document (first page or image) when available."
        )
        preview_layout = QVBoxLayout(preview_group)
        self._preview_label = QLabel("(Select a document to preview)")
        self._preview_label.setTextFormat(Qt.TextFormat.PlainText)
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setMinimumHeight(180)
        self._preview_label.setStyleSheet("background: #f0f0f0; border: 1px solid #ccc;")
        self._preview_label.setToolTip(
            "First-page or image preview for the selected document when available."
        )
        preview_layout.addWidget(self._preview_label)
        layout.addWidget(preview_group)

        # -- Extracted fields ------------------------------------------------
        fields_group = QGroupBox("Extracted Fields")
        fields_group.setToolTip(
            "Values from AI extraction or prior approval; edit before Approve or Run AI again."
        )
        form = QFormLayout(fields_group)

        self._f_vendor   = QLineEdit()
        self._f_vendor.setToolTip(
            "Counterparty name from the document (editable; Approve saves with other fields)."
        )
        self._f_doctype  = QComboBox()
        self._f_doctype.addItems(["invoice", "bill", "receipt", "credit_note", "other"])
        self._f_doctype.setToolTip(
            "Document kind for workflow and fields (invoice, bill, receipt, etc.)."
        )
        self._f_inv_num  = QLineEdit()
        self._f_inv_num.setToolTip("Invoice, bill, or reference number from extraction.")
        self._f_date     = QLineEdit()
        self._f_date.setToolTip("Document date (often yyyy-mm-dd; match what appears on the source).")
        self._f_due_date = QLineEdit()
        self._f_due_date.setToolTip("Due or pay-by date if present on the document.")
        self._f_subtotal = QDoubleSpinBox()
        self._f_subtotal.setMaximum(9_999_999)
        self._f_subtotal.setDecimals(2)
        self._f_subtotal.setToolTip("Amount before tax.")
        self._f_tax      = QDoubleSpinBox()
        self._f_tax.setMaximum(9_999_999)
        self._f_tax.setDecimals(2)
        self._f_tax.setToolTip("Tax amount for this document (not the percentage rate).")
        self._f_total    = QDoubleSpinBox()
        self._f_total.setMaximum(9_999_999)
        self._f_total.setDecimals(2)
        self._f_total.setToolTip("Grand total including tax.")
        self._f_currency = QLineEdit()
        self._f_currency.setMaxLength(3)
        self._f_currency.setFixedWidth(55)
        self._f_currency.setToolTip("ISO-style three-letter code (e.g. USD).")
        self._f_notes    = QPlainTextEdit()
        self._f_notes.setFixedHeight(60)
        self._f_notes.setToolTip("Memo or notes from extraction; editable before Approve.")

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
        cat_group.setToolTip(
            "Suggested chart-of-accounts line and tax label from Run AI; confidence and rationale update here."
        )
        cat_layout = QFormLayout(cat_group)

        self._f_coa      = QComboBox()
        self._fill_coa_combo(coa_list)
        self._f_coa.setEditable(True)
        self._f_coa.setToolTip(
            "Chart of accounts line for this document; choose from the list or type to match."
        )
        self._f_tax_cat  = QLineEdit()
        self._f_tax_cat.setToolTip("Optional tax bucket or category label when your workflow uses it.")
        self._f_confidence = QLabel("–")
        self._f_confidence.setToolTip(
            "Model-reported confidence for the suggested COA and tax category (after Run AI)."
        )

        cat_layout.addRow("COA Account:", self._f_coa)
        cat_layout.addRow("Tax Category:", self._f_tax_cat)
        cat_layout.addRow("AI Confidence:", self._f_confidence)

        self._lbl_rationale = QLabel("")
        self._lbl_rationale.setTextFormat(Qt.TextFormat.PlainText)
        self._lbl_rationale.setWordWrap(True)
        self._lbl_rationale.setStyleSheet("color: #555; font-style: italic;")
        self._lbl_rationale.setToolTip(
            "Short explanation from the categorization model for the suggested accounts."
        )
        cat_layout.addRow("Rationale:", self._lbl_rationale)

        layout.addWidget(cat_group)

        # -- Action buttons --------------------------------------------------
        btn_layout = QHBoxLayout()
        self._btn_run     = QPushButton("\u26a1 Run AI")
        self._btn_approve = QPushButton("\u2705 Approve")
        self._btn_post    = QPushButton("\U0001f4e4 Mark Posted")
        self._btn_reject  = QPushButton("\u274c Reject")

        self._btn_run.setToolTip(
            "Run AI extraction and categorisation for the selected document."
        )
        self._btn_approve.setToolTip(
            "Save the current fields and COA account as approved values."
        )
        self._btn_post.setToolTip("Mark this document as posted in the workflow.")
        self._btn_reject.setToolTip("Mark this document as needing review.")

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
        self._lbl_filename.setText(escape_ampersand_for_qt(row["filename"]))
        status = row["status"]
        color  = STATUS_COLORS.get(status, "#000")
        safe_status = escape_html_text(status)
        self._lbl_status.setTextFormat(Qt.TextFormat.RichText)
        self._lbl_status.setText(f"Status: <b style='color:{color}'>{safe_status}</b>")

        self._show_preview(row["stored_path"], row["mimetype"], row["page_count"])

        # Fill from approved values if present, else from extraction
        approved = db.get_approved(doc_id)
        extraction = db.get_latest_extraction(doc_id)
        src = approved or extraction
        self._populate_fields(src)

        # Categorisation
        if approved:
            self._set_coa_combo_raw(approved["coa_account"])
            self._f_tax_cat.setText(approved["tax_category"] or "")

        self._set_buttons_enabled(True)

    def populate_ai_result(self, result, suggestions=None):
        """Fill the form with AI extraction + categorisation results."""
        self._populate_fields_from_extraction(result)
        if suggestions and not suggestions.error:
            s_coa = (suggestions.coa_account or "").strip()
            if s_coa:
                idx = self._f_coa.findData(s_coa, Qt.ItemDataRole.UserRole)
                if idx >= 0:
                    self._f_coa.setCurrentIndex(idx)
                else:
                    self._f_coa.setCurrentIndex(-1)
                    self._f_coa.setEditText(s_coa)
            else:
                self._f_coa.setCurrentIndex(0)
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
            "coa_account":    self._coa_combo_raw_value(),
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
                "\U0001f4c4 PDF document\n"
                f"{escape_ampersand_for_qt(Path(stored_path).name)}\n{pages} page(s)"
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

    def update_coa(self, coa_list: list[str]):
        """Refresh the COA dropdown with an updated list."""
        current = self._coa_combo_raw_value()
        self._fill_coa_combo(coa_list)
        self._set_coa_combo_raw(current)

    def _fill_coa_combo(self, coa_list: list[str]) -> None:
        self._f_coa.clear()
        self._f_coa.addItem(
            escape_ampersand_for_qt(_COA_SELECT_LABEL), ""
        )
        for coa in coa_list:
            c = (coa or "").strip()
            if not c:
                continue
            self._f_coa.addItem(escape_ampersand_for_qt(c), c)

    def _coa_combo_raw_value(self) -> str | None:
        i = self._f_coa.currentIndex()
        if i == 0:
            return None
        if i > 0:
            data = self._f_coa.itemData(i, Qt.ItemDataRole.UserRole)
            if data is not None and str(data).strip():
                return str(data).strip()
        t = self._f_coa.currentText().strip()
        if not t or t == _COA_SELECT_LABEL:
            return None
        return t

    def _set_coa_combo_raw(self, raw: str | None) -> None:
        if self._f_coa.count() == 0:
            return
        if not (raw or "").strip():
            self._f_coa.setCurrentIndex(0)
            return
        r = raw.strip()
        idx = self._f_coa.findData(r, Qt.ItemDataRole.UserRole)
        if idx >= 0:
            self._f_coa.setCurrentIndex(idx)
        else:
            self._f_coa.setCurrentIndex(-1)
            self._f_coa.setEditText(r)

    def clear_view(self):
        """Reset the detail pane when switching company database."""
        self._doc_id = None
        self._lbl_filename.setText("No document selected")
        self._lbl_status.setTextFormat(Qt.TextFormat.PlainText)
        self._lbl_status.setText("")
        self._preview_label.setPixmap(QPixmap())
        self._preview_label.setText("(Select a document to preview)")
        self._f_vendor.clear()
        if self._f_doctype.count() > 0:
            self._f_doctype.setCurrentIndex(0)
        self._f_inv_num.clear()
        self._f_date.clear()
        self._f_due_date.clear()
        self._f_subtotal.setValue(0.0)
        self._f_tax.setValue(0.0)
        self._f_total.setValue(0.0)
        self._f_currency.setText("USD")
        self._f_notes.clear()
        self._f_tax_cat.clear()
        self._f_confidence.setText("\u2013")
        self._lbl_rationale.clear()
        if self._f_coa.count() > 0:
            self._f_coa.setCurrentIndex(0)
        self._set_buttons_enabled(False)


# ---------------------------------------------------------------------------
# App header / banner
# ---------------------------------------------------------------------------

class AppHeaderWidget(QFrame):
    """Top banner showing the app name and current company/file name."""

    def __init__(self, company_name: str = COMPANY_NAME, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"background: {INBOX_HEADER_COLOR}; border-bottom: 2px solid #4a6fa8;"
        )
        self.setFixedHeight(44)
        self.setToolTip(
            "App banner; company name is the open SQLite file (switch via File → Open company database)."
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(0)

        lbl_app = QLabel("ProBooks+ai")
        lbl_app.setStyleSheet(
            "color: white; font-weight: bold; font-size: 16px; background: transparent;"
        )
        lbl_app.setToolTip(
            "ProBooks+ai — document intake, bank workflows, ledger, and business tools."
        )
        layout.addWidget(lbl_app)

        layout.addStretch()

        self._lbl_company = QLabel(escape_ampersand_for_qt(company_name))
        self._lbl_company.setTextFormat(Qt.TextFormat.PlainText)
        self._lbl_company.setStyleSheet(
            "color: #c8d8f0; font-size: 12px; background: transparent;"
        )
        self._lbl_company.setToolTip(
            "Current company database or file name (updates when you open another company)."
        )
        layout.addWidget(self._lbl_company)

    def set_company_name(self, name: str):
        """Update the displayed company/file name at runtime."""
        self._lbl_company.setText(escape_ampersand_for_qt(name))


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


def _menu_action_tip(act: QAction, tip: str) -> None:
    """Set status-bar hint and matching hover tooltip for main-window menu actions."""
    act.setStatusTip(tip)
    act.setToolTip(tip)


class MainWindow(QMainWindow):
    def __init__(self, db_path: str | None = None):
        super().__init__()
        self.resize(1100, 700)

        self._db_path = db_path
        self._db = DocumentDatabase(db_path)
        self._bank_db = BankDatabase(db_path)
        apply_extensions(self._bank_db._conn)
        self._gl_db = GLDatabase(self._bank_db._conn)
        self._coa_db = COADatabase(self._bank_db._conn)
        self._coa_db.seed_from_workbook()
        self._coa = load_coa()
        self._worker: AIWorker | None = None

        self._build_ui()
        self._refresh_inbox()
        self._update_company_status()

    # -- UI construction -----------------------------------------------------

    def _build_ui(self):
        self._build_menu_bar()

        # Toolbar
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        toolbar.setToolTip(
            "Document Intake toolbar: import documents and refresh the inbox (File menu and F5 when Intake has focus)."
        )
        self.addToolBar(toolbar)

        act_import = QAction("\U0001f4c2  Import Documents\u2026", self)
        act_import.setToolTip(
            "Import documents (same as File → Import documents…, Ctrl+O)."
        )
        act_import.triggered.connect(self._on_import)
        toolbar.addAction(act_import)

        toolbar.addSeparator()

        act_refresh = QAction("\U0001f504  Refresh", self)
        act_refresh.setToolTip("Refresh document list (F5 when Document Intake has focus).")
        act_refresh.triggered.connect(self._refresh_inbox)
        toolbar.addAction(act_refresh)

        # Container: header banner + tab widget
        container = QWidget()
        container.setToolTip(
            "Main workspace: company banner and tabbed areas (Document Intake through Audit log)."
        )
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        self._header = AppHeaderWidget()
        container_layout.addWidget(self._header)

        # Tab widget
        self._tabs = QTabWidget()
        self._tabs.setToolTip(
            "Main workspace: switch between Document Intake, Bank Import, Register, "
            "Chart of Accounts, Reports, Journal, Business, and Audit log (hover each tab for a short summary)."
        )

        # ── Tab 1: Document Intake ──────────────────────────────────────────
        intake_widget = QWidget()
        intake_widget.setToolTip(
            "Document Intake: import files, pick an inbox row, then review extraction and categorization on the right. "
            "F5 refreshes the list when this tab has focus."
        )
        intake_layout = QVBoxLayout(intake_widget)
        intake_layout.setContentsMargins(0, 0, 0, 0)
        intake_layout.setSpacing(0)

        # Splitter (original central layout)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: inbox
        left = QWidget()
        left.setToolTip(
            "Document inbox column: header and file list for the selected company; drag the splitter to resize against the detail pane."
        )
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        lbl_inbox = QLabel("  Document Inbox")
        lbl_inbox.setStyleSheet(
            f"background: {INBOX_HEADER_COLOR}; color: white; font-weight: bold; "
            "font-size: 13px; padding: 6px;"
        )
        lbl_inbox.setToolTip(
            "Imported documents: pick a row to load extraction and categorization in the detail pane."
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
        splitter.setToolTip(
            "Drag the handle to resize the document inbox and the extraction detail pane."
        )
        intake_layout.addWidget(splitter)

        sc_intake_f5 = QShortcut(QKeySequence("F5"), intake_widget)
        sc_intake_f5.setContext(Qt.WidgetWithChildrenShortcut)
        sc_intake_f5.activated.connect(self._refresh_inbox)

        self._tabs.addTab(intake_widget, "📄  Document Intake")

        # ── Tab 2: Bank Import & Reconciliation ─────────────────────────────
        self._bank_tab = BankImportTab(self._bank_db, self._coa_db)
        self._tabs.addTab(self._bank_tab, "🏦  Bank Import")

        # ── Tab 3: Bank register (Phase 3) ──────────────────────────────────
        self._register_tab = RegisterTab(self._bank_db, self._coa_db, self._gl_db)
        self._tabs.addTab(self._register_tab, "📒  Bank register")

        # ── Tab 4: Chart of Accounts Editor ─────────────────────────────────
        self._coa_tab = COATab(self._coa_db)
        self._coa_tab.coaChanged.connect(self._on_coa_changed)
        self._tabs.addTab(self._coa_tab, "📊  Chart of Accounts")

        # ── Tabs 5–7: GL reports & business (roadmap phases 5–16) ─────────
        self._tabs.addTab(ReportsTab(self._bank_db._conn), "📈  Reports")
        self._tabs.addTab(JournalTab(self._bank_db._conn), "📗  Journal")
        self._tabs.addTab(BusinessHub(self._bank_db._conn), "🧾  Business")
        self._tabs.addTab(AuditTab(self._bank_db._conn), "📜  Audit log")

        main_tab_bar = self._tabs.tabBar()
        main_tab_bar.setTabToolTip(
            0,
            "Import PDFs and images, run AI extraction, approve fields, and categorize to COA.",
        )
        main_tab_bar.setTabToolTip(
            1,
            "Bank CSV/PDF import, batches, transactions, and statement reconciliation.",
        )
        main_tab_bar.setTabToolTip(
            2,
            "Check-register view: categorize, splits, transfer links, cleared flags, post to GL.",
        )
        main_tab_bar.setTabToolTip(
            3,
            "Chart of accounts: add, edit, deactivate; used in journal, reports, and pickers.",
        )
        main_tab_bar.setTabToolTip(
            4,
            "Financial reports: trial balance, income statement, balance sheet, CSV export.",
        )
        main_tab_bar.setTabToolTip(
            5,
            "General journal: browse entries and lines by date (export CSV).",
        )
        main_tab_bar.setTabToolTip(
            6,
            "Business hub: rules, AR, AP, payroll runs, and default sales tax settings.",
        )
        main_tab_bar.setTabToolTip(
            7,
            "Audit trail: recent field-level changes (filter by entity type and id).",
        )

        container_layout.addWidget(self._tabs)
        self.setCentralWidget(container)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage(
            escape_ampersand_for_qt(
                "Ready \u2013 drag & drop documents or use Import."
            )
        )

        # Drag & drop on the main window itself
        self.setAcceptDrops(True)

    # -- menu bar ------------------------------------------------------------

    def _build_menu_bar(self):
        mb = self.menuBar()

        # File menu
        file_menu = mb.addMenu("&File")

        act_import_docs = QAction("&Import documents\u2026", self)
        act_import_docs.setShortcut("Ctrl+O")
        _menu_action_tip(
            act_import_docs,
            "Import PDF or images into the document inbox (Ctrl+O).",
        )
        act_import_docs.triggered.connect(self._on_import)
        file_menu.addAction(act_import_docs)

        act_open_company = QAction("Open &company database\u2026", self)
        act_open_company.setShortcut("Ctrl+Shift+O")
        _menu_action_tip(
            act_open_company,
            "Open a different company SQLite database (Ctrl+Shift+O).",
        )
        act_open_company.triggered.connect(self._on_open_company_database)
        file_menu.addAction(act_open_company)

        act_new_company = QAction("&New company database\u2026", self)
        _menu_action_tip(
            act_new_company,
            "Create a new empty company SQLite database at a path you choose.",
        )
        act_new_company.triggered.connect(self._on_new_company_database)
        file_menu.addAction(act_new_company)

        act_backup = QAction("&Backup company file\u2026", self)
        _menu_action_tip(
            act_backup,
            "Back up the company database to a file you choose (SQLite online backup via probooks.backup; "
            "same engine as probooks backup; safe while the app is open).",
        )
        act_backup.triggered.connect(self._on_backup_company)
        file_menu.addAction(act_backup)

        act_restore = QAction("&Restore from backup\u2026", self)
        _menu_action_tip(
            act_restore,
            "Replace the company database from a backup .db file (probooks.backup / probooks restore; "
            "SQLite backup API; brief disconnect; reloads when done).",
        )
        act_restore.triggered.connect(self._on_restore_company)
        file_menu.addAction(act_restore)

        act_copy_db_path = QAction("Copy company database &path", self)
        act_copy_db_path.setShortcut("Ctrl+Alt+P")
        act_copy_db_path.setShortcutContext(Qt.ApplicationShortcut)
        _menu_action_tip(
            act_copy_db_path,
            "Copy the resolved company .db path to the clipboard (Ctrl+Alt+P).",
        )
        act_copy_db_path.triggered.connect(self._on_copy_company_database_path)
        file_menu.addAction(act_copy_db_path)

        act_save = QAction("&Save", self)
        act_save.setShortcut("Ctrl+S")
        _menu_action_tip(
            act_save, "Save is not used in this desktop shell yet (Ctrl+S)."
        )
        act_save.setEnabled(False)
        file_menu.addAction(act_save)

        act_save_as = QAction("Save &As \u2026", self)
        _menu_action_tip(
            act_save_as, "Save As is not used in this desktop shell yet."
        )
        act_save_as.setEnabled(False)
        file_menu.addAction(act_save_as)

        file_menu.addSeparator()

        act_exit = QAction("E&xit", self)
        act_exit.setShortcut("Ctrl+Q")
        _menu_action_tip(act_exit, "Exit ProBooks+ai (Ctrl+Q).")
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        # View menu — tab shortcuts (tabs are created later; shortcuts fire after UI exists)
        view_menu = mb.addMenu("&View")
        for idx, (sc, label) in enumerate(
            [
                ("Ctrl+1", "Document &Intake"),
                ("Ctrl+2", "&Bank Import"),
                ("Ctrl+3", "&Register"),
                ("Ctrl+4", "Chart of &Accounts"),
                ("Ctrl+5", "&Reports"),
                ("Ctrl+6", "&Journal"),
                ("Ctrl+7", "&Business"),
                ("Ctrl+8", "A&udit log"),
            ]
        ):
            act = QAction(label, self)
            act.setShortcut(sc)
            act.setShortcutContext(Qt.ApplicationShortcut)
            _menu_action_tip(act, f"Show this main tab ({sc}).")
            act.triggered.connect(
                lambda checked=False, i=idx: self._set_main_tab_index(i)
            )
            view_menu.addAction(act)

        # Edit menu
        edit_menu = mb.addMenu("&Edit")

        act_undo = QAction("&Undo", self)
        act_undo.setShortcut("Ctrl+Z")
        _menu_action_tip(
            act_undo, "Undo is not available in this version (Ctrl+Z)."
        )
        act_undo.setEnabled(False)
        edit_menu.addAction(act_undo)

        act_redo = QAction("&Redo", self)
        act_redo.setShortcut("Ctrl+Y")
        _menu_action_tip(
            act_redo, "Redo is not available in this version (Ctrl+Y)."
        )
        act_redo.setEnabled(False)
        edit_menu.addAction(act_redo)

        edit_menu.addSeparator()

        act_prefs = QAction("&Preferences \u2026", self)
        _menu_action_tip(
            act_prefs, "Application preferences are not available yet."
        )
        act_prefs.setEnabled(False)
        edit_menu.addAction(act_prefs)

        # Tools menu
        tools_menu = mb.addMenu("&Tools")
        act_tools = QAction("(Coming soon)", self)
        _menu_action_tip(
            act_tools, "Additional tools are not available yet."
        )
        act_tools.setEnabled(False)
        tools_menu.addAction(act_tools)

        # Help menu
        help_menu = mb.addMenu("&Help")
        act_roadmap = QAction("Product &roadmap (local file)\u2026", self)
        _menu_action_tip(
            act_roadmap, "Open docs/ROADMAP.md with the default application."
        )
        act_roadmap.triggered.connect(self._on_help_roadmap)
        help_menu.addAction(act_roadmap)
        act_intake_keys = QAction("Document &intake shortcuts…", self)
        _menu_action_tip(
            act_intake_keys,
            "F5 refresh, Ctrl+O import, File → Backup/Restore (probooks.backup), "
            "View chords, and links to other Help topics.",
        )
        act_intake_keys.triggered.connect(
            lambda: show_document_intake_keyboard_shortcuts_dialog(self)
        )
        help_menu.addAction(act_intake_keys)
        act_bank_import_keys = QAction("Bank &import shortcuts…", self)
        _menu_action_tip(
            act_bank_import_keys,
            "F5 refresh and context-menu shortcuts for Bank Import; Document intake help lists File backup/restore.",
        )
        act_bank_import_keys.triggered.connect(
            lambda: show_bank_import_keyboard_shortcuts_dialog(self)
        )
        help_menu.addAction(act_bank_import_keys)
        act_register_keys = QAction("Bank &register keyboard shortcuts…", self)
        _menu_action_tip(
            act_register_keys,
            "F5, Ctrl+Shift+G/E/C/U, and register grid shortcuts; Document intake help lists File backup/restore.",
        )
        act_register_keys.triggered.connect(
            lambda: show_register_keyboard_shortcuts_dialog(self)
        )
        help_menu.addAction(act_register_keys)
        act_business_keys = QAction("&Business shortcuts…", self)
        _menu_action_tip(
            act_business_keys,
            "F5, Tax % Ctrl+S, and Business tab context menus; Document intake help lists File backup/restore.",
        )
        act_business_keys.triggered.connect(
            lambda: show_business_keyboard_shortcuts_dialog(self)
        )
        help_menu.addAction(act_business_keys)
        act_more_tab_keys = QAction("&More tab shortcuts (F5)…", self)
        _menu_action_tip(
            act_more_tab_keys,
            "F5 refresh and View chords for COA, Journal, Reports, and Audit; "
            "Document intake shortcuts summarizes File → Backup/Restore.",
        )
        act_more_tab_keys.triggered.connect(
            lambda: show_more_main_tabs_keyboard_shortcuts_dialog(self)
        )
        help_menu.addAction(act_more_tab_keys)
        help_menu.addSeparator()
        act_about = QAction("&About ProBooks+ai", self)
        _menu_action_tip(
            act_about,
            "Application name and version; Ok also notes Help shortcuts and File backup (probooks.backup).",
        )
        act_about.triggered.connect(self._on_about)
        help_menu.addAction(act_about)

    # -- drag & drop on window -----------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self._import_files(paths)

    # -- slots ---------------------------------------------------------------

    def _on_copy_company_database_path(self) -> None:
        raw = getattr(self._bank_db, "_db_path", None) or self._db_path or ""
        if not raw:
            message_box_information_ok(
                self,
                "Copy path",
                "No company database path is available.",
                ok_tip="Open or create a company database first (File menu).",
            )
            return
        resolved = str(Path(raw).resolve())
        QApplication.clipboard().setText(resolved)
        self._status_bar.showMessage(
            f"Copied path: {escape_ampersand_for_qt(resolved)}", 6000
        )

    def _on_help_roadmap(self):
        path = resolve_local_roadmap_path()
        if path is None:
            message_box_information_ok(
                self,
                "Product roadmap",
                "Could not find docs/ROADMAP.md.\n\n"
                "In development, it lives in the repository docs folder.\n"
                "Reinstall or rebuild the desktop app if you expected a bundled copy.",
                ok_tip="Close; open ROADMAP.md from the repo in your editor if you are developing.",
            )
            return
        url = QUrl.fromLocalFile(str(path))
        if not QDesktopServices.openUrl(url):
            message_box_warning_ok(
                self,
                "Product roadmap",
                f"Unable to open the file (no default app for .md?):\n"
                f"{escape_ampersand_for_qt(str(path))}",
                ok_tip="Close; open the path in Explorer or associate a Markdown viewer.",
            )

    def _on_about(self):
        ver = application_version()
        message_box_about_ok(
            self,
            "About ProBooks+ai",
            f"<b>ProBooks+ai</b><br>"
            f"Version {ver} \u2014 AI-powered bookkeeping for small business.<br><br>"
            f"Keyboard shortcuts are summarized under <b>Help</b>.<br><br>"
            f"\u00a9 2026 ProBooks+ai",
            ok_tip="Close; Help lists shortcuts; File → Backup/Restore uses probooks.backup (same as CLI).",
        )

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
                self._status_bar.showMessage(
                    f"Error importing {escape_ampersand_for_qt(Path(path).name)}: "
                    f"{escape_ampersand_for_qt(str(exc))}"
                )

        self._refresh_inbox()
        if skipped:
            message_box_warning_ok(
                self,
                "Skipped Files",
                "The following files were skipped (unsupported type):\n"
                + "\n".join(escape_ampersand_for_qt(s) for s in skipped),
                ok_tip="Close; use PDF or supported images only for Intake import.",
            )
        if imported:
            self._status_bar.showMessage(f"Imported {imported} document(s).")

    def _on_selection_changed(self):
        doc_id = self._inbox.selected_doc_id()
        if doc_id is not None:
            self._detail.load_document(doc_id, self._db)

    def _on_run_ai(self, doc_id: int):
        if self._worker and self._worker.isRunning():
            message_box_information_ok(
                self,
                "AI Running",
                "Please wait \u2013 AI extraction is already in progress.",
                ok_tip="Close; wait for the current extraction to finish before running again.",
            )
            return

        row = self._db.get_document(doc_id)
        if not row:
            return

        # Check API key
        if not os.environ.get("OPENAI_API_KEY"):
            message_box_warning_ok(
                self,
                "API Key Missing",
                "OPENAI_API_KEY is not set.\n\n"
                "Set the environment variable before starting the application:\n"
                "  set OPENAI_API_KEY=sk-...",
                ok_tip="Close; set the key, restart the app, then run AI again.",
            )
            return

        self._status_bar.showMessage(
            f"Running AI extraction on {escape_ampersand_for_qt(row['filename'])}\u2026"
        )
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
        self._status_bar.showMessage(
            f"AI extraction complete for {escape_ampersand_for_qt(name)}."
        )

    def _on_ai_error(self, doc_id: int, error: str):
        self._db.set_status(doc_id, "Error")
        self._refresh_inbox()
        message_box_critical_ok(
            self,
            "AI Extraction Failed",
            f"Error:\n{escape_ampersand_for_qt(error)}",
            ok_tip="Close; check network, API key, and document format, then retry.",
        )
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
            message_box_warning_ok(
                self,
                "Not Yet Approved",
                "Please approve the document before marking it as Posted.",
                ok_tip="Close; use Approve in the detail pane first.",
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
        self._status_bar.showMessage("Document flagged \u2013 Needs Review.")

    # -- helpers -------------------------------------------------------------

    def _refresh_inbox(self):
        docs = self._db.list_documents()
        self._inbox.populate(docs)

    def _on_coa_changed(self):
        """Called when the COA editor modifies the chart of accounts."""
        # Refresh the dropdown list used in the document intake detail pane
        self._coa = load_coa()
        coa_display = self._coa_db.display_list()
        self._detail.update_coa(coa_display)
        self._register_tab.refresh_coa_choices()

    def _set_main_tab_index(self, index: int) -> None:
        if not hasattr(self, "_tabs"):
            return
        if index < 0 or index >= self._tabs.count():
            return
        self._tabs.setCurrentIndex(index)

    def _sync_window_title(self) -> None:
        ver = application_version()
        p = getattr(self._bank_db, "_db_path", None) or self._db_path or ""
        if p:
            self.setWindowTitle(
                f"ProBooks+ai – {escape_ampersand_for_qt(Path(p).name)} – Desktop v{ver}"
            )
        else:
            self.setWindowTitle(f"ProBooks+ai – Desktop v{ver}")

    def _update_company_status(self) -> None:
        p = getattr(self._bank_db, "_db_path", None) or self._db_path or ""
        self._status_bar.showMessage(
            escape_ampersand_for_qt(
                f"Company: {p}  \u2013  drag & drop documents or use Import."
            )
        )
        if p:
            self._header.set_company_name(Path(p).name)
        else:
            self._header.set_company_name("No company file")
        self._sync_window_title()

    def _rebuild_bank_related_tabs(self):
        """Replace bank/GL/COA-related tabs after switching SQLite company file."""
        for i in range(7, 0, -1):
            w = self._tabs.widget(i)
            self._tabs.removeTab(i)
            if w is not None:
                w.deleteLater()
        tab_specs = [
            ("🏦  Bank Import", BankImportTab(self._bank_db, self._coa_db)),
            ("📒  Bank register", RegisterTab(self._bank_db, self._coa_db, self._gl_db)),
            ("📊  Chart of Accounts", COATab(self._coa_db)),
            ("📈  Reports", ReportsTab(self._bank_db._conn)),
            ("📗  Journal", JournalTab(self._bank_db._conn)),
            ("🧾  Business", BusinessHub(self._bank_db._conn)),
            ("📜  Audit log", AuditTab(self._bank_db._conn)),
        ]
        for i, (title, widget) in enumerate(tab_specs, start=1):
            self._tabs.insertTab(i, widget, title)
        self._bank_tab = self._tabs.widget(1)
        self._register_tab = self._tabs.widget(2)
        self._coa_tab = self._tabs.widget(3)
        self._coa_tab.coaChanged.connect(self._on_coa_changed)

    def _load_company_at_path(self, resolved: str) -> None:
        """Open SQLite at *resolved* and rebuild bank-side tabs + intake COA."""
        self._db_path = resolved
        QSettings().setValue("company_database_path", resolved)
        self._db = DocumentDatabase(resolved)
        self._bank_db = BankDatabase(resolved)
        apply_extensions(self._bank_db._conn)
        self._gl_db = GLDatabase(self._bank_db._conn)
        self._coa_db = COADatabase(self._bank_db._conn)
        self._coa_db.seed_from_workbook()
        self._coa = load_coa()
        self._rebuild_bank_related_tabs()
        self._detail.clear_view()
        self._detail.update_coa(self._coa_db.display_list())
        self._refresh_inbox()
        self._update_company_status()

    def _switch_company_database(self, path: str, *, create_new: bool = False) -> None:
        if self._worker and self._worker.isRunning():
            message_box_warning_ok(
                self,
                "Busy",
                "Wait for AI extraction to finish before switching company files.",
                ok_tip="Close; wait for AI to finish, then switch company files.",
            )
            return

        p = Path(path)
        if create_new:
            p.parent.mkdir(parents=True, exist_ok=True)
            if p.exists():
                box = QMessageBox(self)
                box.setIcon(QMessageBox.Icon.Question)
                box.setWindowTitle("File exists")
                box.setText(
                    "Open this existing file as the company database?\n\n"
                    f"{escape_ampersand_for_qt(str(p))}"
                )
                box.setStandardButtons(
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                box.setDefaultButton(QMessageBox.StandardButton.No)
                box.setToolTip(
                    "This path already exists; Yes opens it as the company database (reload from disk), No cancels."
                )
                tip_message_box_buttons(
                    box,
                    yes="Switch to this database file (reload from disk).",
                    no="Do not switch; cancel opening this path.",
                )
                reply = box.exec()
                if reply != QMessageBox.StandardButton.Yes:
                    return
        elif not p.exists():
            message_box_warning_ok(
                self,
                "Not found",
                f"File does not exist:\n{escape_ampersand_for_qt(str(p))}",
                ok_tip="Close; pick an existing .db file or create a new one.",
            )
            return

        resolved = str(p.resolve())
        self._db.close()
        self._bank_db.close()
        self._load_company_at_path(resolved)

    def _on_backup_company(self):
        if self._worker and self._worker.isRunning():
            message_box_warning_ok(
                self,
                "Busy",
                "Wait for AI extraction to finish before backing up.",
                ok_tip="Close; wait for AI, then File → Backup again (same engine as probooks backup).",
            )
            return
        src = Path(self._bank_db._db_path).resolve()
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Backup company database (probooks backup)",
            str(src.parent / f"{src.stem}-backup.db"),
            "SQLite Database (*.db);;All Files (*.*)",
        )
        if not path:
            return
        if not path.lower().endswith(".db"):
            path += ".db"
        try:
            backup_database(src, Path(path))
        except ValueError as exc:
            message_box_critical_ok(
                self,
                "Backup failed",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; open a valid company .db or repair it; File → Backup and probooks backup share probooks.backup.",
            )
            return
        except (OSError, sqlite3.Error) as exc:
            message_box_critical_ok(
                self,
                "Backup failed",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; check disk space, permissions, and locks; probooks backup uses the same engine (probooks.backup).",
            )
            return
        message_box_information_ok(
            self,
            "Backup complete",
            f"Backup saved to:\n{escape_ampersand_for_qt(path)}\n\n"
            "Same engine as probooks backup (probooks.backup).",
            ok_tip="Close; the backup file is ready at the path shown.",
        )

    def _on_restore_company(self):
        if self._worker and self._worker.isRunning():
            message_box_warning_ok(
                self,
                "Busy",
                "Wait for AI extraction to finish before restoring.",
                ok_tip="Close; wait for AI, then File → Restore again (same engine as probooks restore).",
            )
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Restore company database")
        box.setText(
            "The selected backup will overwrite your current company database file on disk. "
            "Unsaved work in memory is discarded. This cannot be undone.\n\n"
            "Same engine as probooks restore (probooks.backup).\n\n"
            "Continue?"
        )
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        box.setDefaultButton(QMessageBox.StandardButton.No)
        box.setToolTip(
            "Restore overwrites the active company database on disk via probooks.backup; "
            "unsaved in-memory work is discarded."
        )
        tip_message_box_buttons(
            box,
            yes="Overwrite the company file with the selected backup.",
            no="Cancel restore; keep the current file.",
        )
        reply = box.exec()
        if reply != QMessageBox.StandardButton.Yes:
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select backup to restore (probooks restore)",
            "",
            "SQLite Database (*.db);;All Files (*.*)",
        )
        if not path:
            return
        target = Path(self._bank_db._db_path).resolve()
        if Path(path).resolve() == target:
            message_box_information_ok(
                self,
                "Restore",
                "Choose a different file than the active company database.",
                ok_tip="Close; pick a backup copy, not the live .db (same rules as probooks restore / probooks.backup).",
            )
            return
        self._db.close()
        self._bank_db.close()
        try:
            restore_database(Path(path), target, overwrite=True)
        except ValueError as exc:
            message_box_critical_ok(
                self,
                "Restore failed",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; pick a valid SQLite backup .db; probooks restore matches File → Restore (probooks.backup).",
            )
            try:
                self._load_company_at_path(str(target))
            except Exception:
                pass
            return
        except (OSError, sqlite3.Error) as exc:
            message_box_critical_ok(
                self,
                "Restore failed",
                f"{escape_ampersand_for_qt(str(exc))}\n\n"
                "Try closing other apps using the database, then restart ProBooks+ai.",
                ok_tip="Close; release locks and retry; probooks restore uses the same engine (probooks.backup).",
            )
            try:
                self._load_company_at_path(str(target))
            except Exception:
                pass
            return
        self._load_company_at_path(str(target))
        message_box_information_ok(
            self,
            "Restore complete",
            "Company data was reloaded from the backup.\n\n"
            "Same engine as probooks restore (probooks.backup).",
            ok_tip="Close; you are now on the restored company database.",
        )

    def _on_open_company_database(self):
        prev = QSettings().value("company_database_path", "", type=str) or ""
        start_dir = str(Path(prev).parent) if prev else ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open company database",
            start_dir,
            "SQLite Database (*.db);;All Files (*.*)",
        )
        if path:
            self._switch_company_database(path, create_new=False)

    def _on_new_company_database(self):
        prev = QSettings().value("company_database_path", "", type=str) or ""
        start_dir = str(Path(prev).parent) if prev else ""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "New company database",
            start_dir,
            "SQLite Database (*.db);;All Files (*.*)",
        )
        if path:
            if not path.lower().endswith(".db"):
                path += ".db"
            self._switch_company_database(path, create_new=True)

    def closeEvent(self, event):
        self._db.close()
        self._bank_db.close()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _suppress_qt_font_pointsize_stderr_spam() -> None:
    """Drop known-harmless Qt warning when default GUI font meets global QSS (often Windows)."""

    def _handler(msg_type, context, message) -> None:
        text = (
            message.decode("utf-8", errors="replace")
            if isinstance(message, (bytes, bytearray))
            else str(message)
        )
        if "QFont::setPointSize" in text and (
            "Point size <= 0" in text or "must be greater than 0" in text
        ):
            return
        prev = getattr(_handler, "_prev", None)
        if prev is not None:
            prev(msg_type, context, message)

    _handler._prev = qInstallMessageHandler(_handler)


def main():
    _suppress_qt_font_pointsize_stderr_spam()
    ver = application_version()
    parser = argparse.ArgumentParser(
        description="ProBooks+ai desktop application",
        epilog=EXCEL_COA_WORKBOOK_ARGPARSE_EPILOG,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"ProBooks+ai {ver}",
    )
    parser.add_argument(
        "--database",
        metavar="PATH",
        default=None,
        help=(
            "SQLite database path; if omitted, uses the last company file from settings "
            "when it still exists, otherwise the default "
            f"{default_intake_db_path().name!r} from probooksai.database.get_data_dir() "
            "(see README: Default database paths)."
        ),
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName("ProBooks+ai")
    app.setOrganizationName("ProBooks+ai")
    apply_dark_theme(app)
    db_path = args.database
    if db_path is None:
        last = QSettings().value("company_database_path", "", type=str) or ""
        if last and Path(last).is_file():
            db_path = last
    window = MainWindow(db_path=db_path)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
