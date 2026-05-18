"""
ProBooks+ai desktop application
===============================
Run with:
    python -m desktop_app.main

Or directly:
    python desktop_app/main.py

Requires PySide6:
    pip install PySide6

``--help`` prints the shared epilog from ``probooks/help_epilog.py`` (Excel COA workbook, backup parity, UTF-8 BOM CSV exports, bank CSV UTF-8 optional BOM read, ``probooks import csv``; see README Desktop + Excel template).

The **central** **QWidget** (banner + tab widget) has a margin hover hint. Document Intake uses **File → Import documents…** (Ctrl+O) and **F5** (when the tab has focus) instead of a main toolbar. Document Intake: **F5** refreshes the inbox; **Help → Document intake shortcuts…** (``message_box_information_ok`` **Ok** tooltip) and inbox **right-click**
**Keyboard shortcuts…** (including empty area) match that dialog. The **InboxWidget** grid has a hover **tooltip**
(import, drag-and-drop, F5, shortcuts). The intake **QSplitter** has a resize hint on hover. **DetailPane** (**QScrollArea**) has a window-level hover hint; its inner **QWidget** has a content-area hint; preview, extracted **LineEdit** / spin fields, **Doc Type**,
**COA Account**, **AI confidence** / **rationale** labels, and action buttons use **tooltips**.
**Preview** / **Extracted Fields** / **Categorisation** group boxes and the **filename** / **status** labels
also have hover hints. The banner **AppHeaderWidget** (**QFrame**) right-aligns **ProBooks+ai** and the company **QLabel**s with tooltips; the **ProBooks+ai** label tooltip includes the installed package **version** (matches the window title and **Help → About**).
**Help → About** uses ``message_box_about_ok`` (rich text + **Ok** hover hint). The **status bar** opens with a **Ready** line (drag/drop, Bank Import pointer, **File → Backup**) plus **ProBooks+ai** and the installed package **version**; **Company:** updates replace that line when a database path exists. The main **QTabWidget** sets a **setToolTip** on the tab strip area; its tab bar sets **setTabToolTip** on each top-level tab (Intake through Audit log). **Document Intake**’s root **QWidget** has a hover hint for the whole tab; the inbox **column** **QWidget** (left splitter pane) has a short margin hint.
Destructive **Yes**/**No** prompts (new company file exists, database restore) use **tip_message_box_buttons** for button hover hints and **QMessageBox.setToolTip** for the dialog window.

Main window **menu bar**: each ``QAction`` uses ``setStatusTip`` for the **status bar** and the same text via ``setToolTip`` for hover (``_menu_action_tip`` helper).
Top-level menus: **File**, **View**, **Edit**, **Tools** (e.g. **Invoice…** Ctrl+Shift+I to the **Invoices** tab), **Recon** (bank register bulk actions in submenus), **Help**.
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
    Qt,
    QEvent,
    QMimeData,
    QObject,
    QSettings,
    QThread,
    QTimer,
    QUrl,
    Signal,
    qInstallMessageHandler,
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
    QStatusBar, QTabWidget, QTableWidget,
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
from desktop_app.extra_tabs import (
    APTab,
    ARTab,
    BusinessHub,
    show_business_keyboard_shortcuts_dialog,
)
from desktop_app.audit_tab import AuditTab
from desktop_app.asset_register_tab import AssetRegisterTab
from desktop_app.dashboard_tab import DashboardTab
from desktop_app.first_run_wizard import FirstRunWizard, apply_wizard_results
from desktop_app.enter_bills_screen import EnterBillsScreen
from desktop_app.invoice_screen import InvoiceScreen
from desktop_app.pay_bills_screen import PayBillsScreen
from desktop_app.receive_checks_screen import ReceiveChecksScreen
from desktop_app.theme import apply_dark_theme, STATUS_COLORS as THEME_STATUS_COLORS
from desktop_app.version import application_version
from desktop_app.local_docs import resolve_local_roadmap_path
from desktop_app.more_main_tabs_shortcuts import (
    show_more_main_tabs_keyboard_shortcuts_dialog,
)
from desktop_app.qt_combo_ids import coerce_combo_int_id
from desktop_app.table_clipboard import (
    CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX,
    IntSortTableItem,
    VIEW_BANK_REGISTER_KEYS_TOOLTIP,
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
        "Menu bar: hover File, View, Edit, Tools, Recon, Help to see shortcut and action hints "
        "in the status bar and on hover for each menu item.\n\n"
        "F5 — Refresh the document list when Document Intake has focus.\n\n"
        "Detail pane: Run AI, Approve, Mark Posted, and Reject have short descriptions on hover.\n\n"
        "File menu:\n"
        "Ctrl+O — Import documents… (PDF/images; same command as File menu).\n"
        "Backup company file… / Restore from backup… — SQLite online backup (probooks.backup), "
        "same path as the CLI; no default shortcuts — hover each action for status-bar tips.\n\n"
        "View menu:\n"
        "Ctrl+1 Invoices … Ctrl+9 Reconcile, Ctrl+0 More (Reports, Journal, Business, Audit log) — all tabs share the open "
        "company SQLite file (File → Backup / Restore, probooks.backup). "
        "Use **Reconcile** (Ctrl+9) → **Bank statements** for statement import and **Bank Register** (Ctrl+5) for the Match overlay.\n\n"
        "**Recon** menu — **Bank register** bulk row actions (add transaction, post to GL, export CSV, cleared, "
        "attachments, splits, transfer, link payment, open linked Business record, receipt flags) when you use Bank Register (Ctrl+5). "
        "**Tools** menu — open **Invoice…** (Ctrl+Shift+I; top-level Invoices tab).\n\n"
        "CSV exports on Bank Import (reconciliation report and line-compare), Register, Reports, Journal, Business, "
        "and Audit use UTF-8 with BOM for Excel.\n"
        "Bank Import Import CSV… reads bank statement CSV as UTF-8 with optional BOM.\n\n"
        "Right-click the inbox grid (including empty area) for Keyboard shortcuts… "
        "(same as this dialog).\n\n"
        "COA, Journal, Reports, Audit:\n"
        "Help → More tab shortcuts (F5)…\n\n"
        "Business:\n"
        "Help → Business shortcuts…\n\n"
        "Bank workflows:\n"
        "Help → Bank import shortcuts… (batch preview, AI line reconciliation).\n"
        "Help → Bank register keyboard shortcuts…\n"
    )


def show_document_intake_keyboard_shortcuts_dialog(parent: QWidget) -> None:
    message_box_information_ok(
        parent,
        "Document intake shortcuts",
        _document_intake_keyboard_shortcuts_help_text(),
        ok_tip="Close; shortcuts apply when Document Intake has focus. "
        "Bank CSV/PDF and AI line reconciliation: Ctrl+9 Reconcile → Bank statements; "
        "Register Match overlay: Ctrl+5 Bank Register; register bulk actions: Recon menu. "
        "Company .db: File → Backup / Restore (probooks.backup).",
    )


# Accepted MIME types / file extensions
ACCEPTED_MIMES = {"application/pdf", "image/jpeg", "image/png"}
ACCEPTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}

STATUS_COLORS = THEME_STATUS_COLORS

INBOX_HEADER_COLOR = "#1F3864"  # dark navy – matches ProBooks+ai branding

# Intake-adjacent tooltips: bank import lives under the Reconcile top-level tab (View Ctrl+9).
_BANK_IMPORT_VIEW_POINTER = (
    "Bank CSV/PDF and AI line reconciliation: Reconcile tab → Bank statements (View → Reconcile, Ctrl+9). "
)

# Temporary status bar duration after Bank Import → Register **Match overlay** sync.
_STMT_MATCH_SYNC_STATUS_MS = 8000

COMPANY_NAME = ""  # blank-safe placeholder until a company database is opened


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
            + _BANK_IMPORT_VIEW_POINTER
            + "Right-click for Keyboard shortcuts… (including on empty area). "
            "Rows live in the company SQLite file (File → Backup / probooks backup)."
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
            "(F5, Ctrl+O, View chords, UTF-8 BOM CSV notes, Bank import pointers in Help). "
            + VIEW_BANK_REGISTER_KEYS_TOOLTIP
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        if not idx.isValid():
            m.exec(self.viewport().mapToGlobal(pos))
            return
        row = idx.row()
        m.addSeparator()
        act_copy = m.addAction("Copy row", partial(copy_table_row_as_tsv, self, row))
        act_copy.setToolTip(
            "Copy this inbox row as tab-separated text for pasting into a spreadsheet or editor. "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
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
        packed = [
            (did, row)
            for row in rows
            if (did := coerce_combo_int_id(row["id"])) is not None
        ]
        self.setSortingEnabled(False)
        self.setRowCount(len(packed))
        for r, (did, row) in enumerate(packed):
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
            eid = coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole))
            if eid is not None:
                return eid
        raw = table_cell_clipboard_text(self, r, 0).strip()
        if not raw:
            return None
        return coerce_combo_int_id(raw)


# ---------------------------------------------------------------------------
# Detail pane (right panel)
# ---------------------------------------------------------------------------

_COA_SELECT_LABEL = "– select –"


class DetailPane(QScrollArea):
    """Shows document preview + extracted fields + action buttons."""

    runAI         = Signal(int)    # doc_id
    approve       = Signal(int)
    markPosted    = Signal(int)
    reject        = Signal(int)
    routeToInvoice = Signal(dict)  # extracted field values
    routeToBill    = Signal(dict)

    def __init__(self, coa_list: list[str], parent=None):
        super().__init__(parent)
        self._doc_id: int | None = None
        self._coa_list = coa_list

        inner = QWidget()
        inner.setToolTip(
            "Preview, extracted fields, categorization, and action buttons for the selected inbox row (scroll when content is tall). "
            "Bank statement CSV/PDF import is on Bank Import (View menu). "
            "Approve/Posted values write to the company SQLite file (File → Backup / probooks backup)."
        )
        self.setWidget(inner)
        self.setWidgetResizable(True)
        self.setToolTip(
            "Scroll the detail pane: preview, extracted fields, categorization, and workflow actions for the selected inbox row. "
            "Bank statement CSV/PDF import is on Bank Import (View menu). "
            "Same company .db as the rest of the app (File → Backup / Restore)."
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

        # Route buttons \u2014 push extracted fields directly to Invoice or Bills screen
        route_layout = QHBoxLayout()
        self._btn_route_invoice = QPushButton("\U0001f4c4 Create Invoice")
        self._btn_route_invoice.setMinimumHeight(32)
        self._btn_route_invoice.setToolTip(
            "Pre-fill the Invoices tab with extracted fields and switch to it."
        )
        self._btn_route_invoice.setStyleSheet(
            "background: #1565C0; color: white; font-weight: bold;"
        )
        self._btn_route_invoice.clicked.connect(self._on_route_invoice)

        self._btn_route_bill = QPushButton("\U0001f4e5 Enter as Bill")
        self._btn_route_bill.setMinimumHeight(32)
        self._btn_route_bill.setToolTip(
            "Pre-fill the Enter Bills tab with extracted fields and switch to it."
        )
        self._btn_route_bill.setStyleSheet(
            "background: #6A1B9A; color: white; font-weight: bold;"
        )
        self._btn_route_bill.clicked.connect(self._on_route_bill)

        route_layout.addWidget(self._btn_route_invoice)
        route_layout.addWidget(self._btn_route_bill)
        layout.addLayout(route_layout)
        layout.addStretch()

        self._set_buttons_enabled(False)

    # -- public interface ----------------------------------------------------

    def load_document(self, doc_id: int, db: DocumentDatabase):
        did = coerce_combo_int_id(doc_id)
        if did is None:
            self.clear_view()
            return
        self._doc_id = did
        row = db.get_document(did)
        if not row:
            self.clear_view()
            return
        self._lbl_filename.setText(escape_ampersand_for_qt(row["filename"]))
        status = row["status"]
        color  = STATUS_COLORS.get(status, "#000")
        safe_status = escape_html_text(status)
        self._lbl_status.setTextFormat(Qt.TextFormat.RichText)
        self._lbl_status.setText(f"Status: <b style='color:{color}'>{safe_status}</b>")

        self._show_preview(row["stored_path"], row["mimetype"], row["page_count"])

        # Fill from approved values if present, else from extraction
        approved = db.get_approved(did)
        extraction = db.get_latest_extraction(did)
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
        for btn in (
            self._btn_run, self._btn_approve, self._btn_post, self._btn_reject,
            self._btn_route_invoice, self._btn_route_bill,
        ):
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

    def _on_route_invoice(self):
        if self._doc_id is not None:
            self.routeToInvoice.emit(self.collect_approved_values())

    def _on_route_bill(self):
        if self._doc_id is not None:
            self.routeToBill.emit(self.collect_approved_values())

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
    """Top banner: **ProBooks+ai** and company/file name, right-aligned."""

    def __init__(self, company_name: str = COMPANY_NAME, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"background: {INBOX_HEADER_COLOR}; border-bottom: 2px solid #4a6fa8;"
        )
        self.setFixedHeight(52)
        self.setToolTip(
            "App banner; company name is the open SQLite file (File → Open company database; "
            "File → Backup saves a copy via probooks.backup). "
            "Bank Import and Register host statement reconciliation, AI line reconciliation, and Register Match overlay."
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 6, 14, 6)
        layout.setSpacing(0)
        layout.addStretch(1)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(2)

        lbl_app = QLabel("ProBooks+ai")
        lbl_app.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        lbl_app.setStyleSheet(
            "color: white; font-weight: bold; font-size: 16px; background: transparent;"
        )
        _ver = application_version()
        lbl_app.setToolTip(
            "ProBooks+ai — document intake, bank workflows (Bank Import: AI line reconciliation, "
            "Match overlay sync to Register), ledger, and business tools. "
            f"Version {_ver} (window title and Help → About). "
            "File → Backup copies the open company .db (probooks.backup / probooks backup)."
        )
        right.addWidget(lbl_app, alignment=Qt.AlignmentFlag.AlignRight)

        self._lbl_company = QLabel(escape_ampersand_for_qt(company_name))
        self._lbl_company.setTextFormat(Qt.TextFormat.PlainText)
        self._lbl_company.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._lbl_company.setStyleSheet(
            "color: #c8d8f0; font-size: 12px; background: transparent;"
        )
        self._lbl_company.setToolTip(
            "Current company database or file name (updates when you open another company). "
            "File → Backup / probooks backup copies this path."
        )
        right.addWidget(self._lbl_company, alignment=Qt.AlignmentFlag.AlignRight)

        layout.addLayout(right)

    def set_company_name(self, name: str):
        """Update the displayed company/file name at runtime."""
        self._lbl_company.setText(escape_ampersand_for_qt(name))


# ---------------------------------------------------------------------------
# Global tooltip toggle
# ---------------------------------------------------------------------------

_TIPS_QSETTINGS_KEY = "ui/show_hover_tips"


class _TipFilter(QObject):
    """App-level event filter that suppresses all QToolTip popups when tips are disabled.

    Install once on QApplication; toggle ``enabled`` at runtime — no widget code changes needed.
    """

    def __init__(self, enabled: bool, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.enabled = enabled

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if not self.enabled and event.type() == QEvent.Type.ToolTip:
            return True   # consume — tooltip never shows
        return super().eventFilter(watched, event)


_tip_filter: _TipFilter | None = None   # set once in main()


def _tips_enabled() -> bool:
    return QSettings().value(_TIPS_QSETTINGS_KEY, False, type=bool)  # type: ignore[return-value]


def _set_tips_enabled(on: bool) -> None:
    QSettings().setValue(_TIPS_QSETTINGS_KEY, on)
    if _tip_filter is not None:
        _tip_filter.enabled = on


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
        # Ensure COA asset accounts exist in bank_accounts before tabs are built
        self._sync_coa_assets_to_bank_accounts()
        # Seed bank_transactions for any existing GL opening-balance entries
        self._migrate_opening_balances_to_bank_register()

        self._build_ui()
        self._refresh_inbox()
        self._update_company_status()

    def _make_placeholder_shell_tab(self, title: str, body: str) -> QWidget:
        """Step-1 shell for a top-level tab whose full workflow is not migrated yet."""
        w = QWidget()
        w.setToolTip(
            f"{title}: placeholder shell (fixed top-level tab order). {body} "
            "Same company .db (File → Backup / Restore, probooks.backup)."
        )
        outer = QVBoxLayout(w)
        lbl = QLabel(body)
        lbl.setWordWrap(True)
        outer.addWidget(lbl)
        return w

    def _build_document_intake_widget(self) -> None:
        """Build the Document Intake UI (hosted under Reconcile → Documents)."""
        intake_widget = QWidget()
        intake_widget.setToolTip(
            "Document Intake: import files, pick an inbox row, then review extraction and categorization on the right. "
            "F5 refreshes the list when this tab has focus. "
            "Bank CSV/PDF and AI line reconciliation: Reconcile → Bank statements. "
            "Help → Document intake shortcuts lists File → Backup/Restore (probooks.backup)."
        )
        intake_layout = QVBoxLayout(intake_widget)
        intake_layout.setContentsMargins(0, 0, 0, 0)
        intake_layout.setSpacing(0)

        doc_guidance = QLabel(
            "<b>Documents</b> — import PDFs or images (File → Import or drag-and-drop), then review extraction on the right. "
            "For <b>bank CSV/PDF statements</b> and register reconciliation, use the <b>Bank statements</b> subtab."
        )
        doc_guidance.setTextFormat(Qt.TextFormat.RichText)
        doc_guidance.setWordWrap(True)
        doc_guidance.setStyleSheet("color: #A0A0B0; font-size: 12px; padding: 0 0 8px 0;")
        doc_guidance.setToolTip(
            "Same document pipeline as before; statement workflows stay on Bank statements so intake feels unified."
        )

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left.setToolTip(
            "Document inbox column: header and file list for the selected company; drag the splitter to resize against the detail pane. "
            + _BANK_IMPORT_VIEW_POINTER
            + "Same company .db as other tabs; File → Backup / Restore (probooks.backup)."
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
            "Imported documents: pick a row to load extraction and categorization in the detail pane. "
            "Bank statement files: Reconcile → Bank statements (View → Reconcile, Ctrl+9). "
            "Back up the company file from File → Backup / probooks backup before bulk deletes or experiments."
        )
        left_layout.addWidget(lbl_inbox)

        self._inbox = InboxWidget()
        self._inbox.filesDropped.connect(self._on_files_dropped)
        self._inbox.itemSelectionChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self._inbox)

        splitter.addWidget(left)

        coa_display = coa_display_list(self._coa)
        self._detail = DetailPane(coa_display)
        self._detail.runAI.connect(self._on_run_ai)
        self._detail.approve.connect(self._on_approve)
        self._detail.markPosted.connect(self._on_mark_posted)
        self._detail.reject.connect(self._on_reject)
        self._detail.routeToInvoice.connect(self._on_route_to_invoice)
        self._detail.routeToBill.connect(self._on_route_to_bill)
        splitter.addWidget(self._detail)

        splitter.setSizes([380, 720])
        splitter.setToolTip(
            "Drag the handle to resize the document inbox and the extraction detail pane. "
            "Bank workflows (CSV/PDF, AI line reconciliation) use Reconcile → Bank statements. "
            "Both sides use the same company SQLite file (File → Backup / probooks backup)."
        )
        intake_layout.addWidget(doc_guidance)
        intake_layout.addWidget(splitter)

        sc_intake_f5 = QShortcut(QKeySequence("F5"), intake_widget)
        sc_intake_f5.setContext(Qt.WidgetWithChildrenShortcut)
        sc_intake_f5.activated.connect(self._refresh_inbox)

        self._intake_widget = intake_widget

    def _assemble_main_tabs(self) -> None:
        """Fixed-order top-level strip + More hub (Reports, Journal, Business, Audit)."""
        conn = self._bank_db._conn
        self._invoice_screen = InvoiceScreen(ap_conn=conn)
        self._enter_bills_screen = EnterBillsScreen(ap_conn=conn)
        self._pay_bills_screen = PayBillsScreen(
            ap_conn=conn, bank_db=self._bank_db
        )
        self._receive_payments_screen = ReceiveChecksScreen(
            ap_conn=conn, bank_db=self._bank_db
        )

        self._register_tab = RegisterTab(self._bank_db, self._coa_db, self._gl_db)
        self._bank_tab = BankImportTab(
            self._bank_db,
            self._coa_db,
            register_tab=self._register_tab,
            after_stmt_match_sync=self._focus_bank_register_tab,
        )
        self._coa_tab = COATab(self._coa_db, gl_db=self._gl_db)
        self._coa_tab.coaChanged.connect(self._on_coa_changed)

        # AR/AP primary UI: top-level Customers / Vendors (Business hub keeps Rules, Payroll, Tax %).
        self._customers_tab = ARTab(conn)
        self._vendors_tab = APTab(conn)

        self._reconcile_hub = QTabWidget()
        self._reconcile_hub.setToolTip(
            "Reconcile: bank statement import, AI line reconciliation, and document intake. "
            "Same company .db (File → Backup / Restore, probooks.backup)."
        )
        self._reconcile_hub.addTab(self._bank_tab, "Bank statements")
        self._reconcile_hub.addTab(self._intake_widget, "Documents")

        self._reconcile_root = QWidget()
        self._reconcile_root.setToolTip(
            "Reconcile: intake (statements or documents), then review and match against Bank Register. "
            "Same company .db (File → Backup / Restore, probooks.backup)."
        )
        reconcile_root_layout = QVBoxLayout(self._reconcile_root)
        reconcile_root_layout.setContentsMargins(8, 8, 8, 0)
        reconcile_root_layout.setSpacing(6)
        reconcile_banner = QLabel(
            "<b>Reconcile</b> — intake on the subtabs below, then review and match against <b>Bank Register</b> "
            "(Ctrl+5; source of truth for posted activity)."
        )
        reconcile_banner.setTextFormat(Qt.TextFormat.RichText)
        reconcile_banner.setWordWrap(True)
        reconcile_banner.setStyleSheet("color: #A0A0B0; font-size: 12px;")
        reconcile_banner.setToolTip(
            "Bank statements: CSV/PDF/paste and AI line reconciliation. Documents: inbox and extraction. "
            "No change to import or reconciliation logic."
        )
        reconcile_root_layout.addWidget(reconcile_banner)
        reconcile_root_layout.addWidget(self._reconcile_hub, stretch=1)

        self._dashboard_tab = DashboardTab(conn)
        self._dashboard_tab.navigateRequested.connect(self._on_dashboard_navigate)

        self._reports_tab = ReportsTab(conn)
        self._journal_tab = JournalTab(conn)
        self._business_hub = BusinessHub(conn)
        self._audit_tab = AuditTab(conn)
        self._asset_register_tab = AssetRegisterTab(conn, coa_list=self._coa_db.display_list() if hasattr(self, "_coa_db") else None)

        self._more_hub = QTabWidget()
        self._more_hub.setToolTip(
            "More: Reports, Journal, Business, Asset Register, and Audit log. "
            "Same company .db (File → Backup / Restore, probooks.backup)."
        )
        self._more_hub.addTab(self._reports_tab, "Reports")
        self._more_hub.addTab(self._journal_tab, "Journal")
        self._more_hub.addTab(self._business_hub, "Business")
        self._more_hub.addTab(self._asset_register_tab, "Assets")
        self._more_hub.addTab(self._audit_tab, "Audit log")

        self._tabs.addTab(self._dashboard_tab, "Dashboard")
        self._tabs.addTab(self._invoice_screen, "Invoices")
        self._tabs.addTab(self._enter_bills_screen, "Enter Bills")
        self._tabs.addTab(self._pay_bills_screen, "Pay Bills")
        self._tabs.addTab(self._receive_payments_screen, "Receive Payments")
        self._tabs.addTab(self._register_tab, "Bank Register")
        self._tabs.addTab(self._coa_tab, "Chart of Accounts")
        self._tabs.addTab(self._customers_tab, "Customers")
        self._tabs.addTab(self._vendors_tab, "Vendors")
        self._tabs.addTab(self._reconcile_root, "Reconcile")
        self._tabs.addTab(self._more_hub, "More")

    def _apply_main_tab_bar_tooltips(self) -> None:
        main_tab_bar = self._tabs.tabBar()
        _main_tab_bar_db_hint = " Same company .db (File → Backup / Restore, probooks.backup)."
        _tab_bar_csv_excel_hint = " CSV: UTF-8 with BOM for Excel."
        tips = [
            (
                "Invoices: invoice entry workflow (line items, Bill To, print/PDF when connected). "
                + _main_tab_bar_db_hint
            ),
            (
                "Enter Bills: bill header and expense lines (vendor-backed when connected)."
                + _main_tab_bar_db_hint
            ),
            (
                "Pay Bills: payables grid (visual foundation; full A/P posting pending)."
                + _main_tab_bar_db_hint
            ),
            (
                "Receive Payments: customer payments against open invoices (visual foundation)."
                + _main_tab_bar_db_hint
            ),
            (
                "Bank Register: check-register grid for one bank account; inline edits where allowed; F5 refresh. "
                "Reconciliation mode + Match overlay (Bank Import AI line reconciliation can populate it). "
                "Bulk actions: Recon menu."
                + _tab_bar_csv_excel_hint
                + _main_tab_bar_db_hint
            ),
            (
                "Chart of accounts: add, edit, deactivate; used in journal, reports, and pickers."
                + _main_tab_bar_db_hint
            ),
            (
                "Customers: customer master (detail + list), balances and activity; export customers CSV (F5). "
                "Invoices, payments, and AR exports use Invoices, Receive Payments, and Reports (Business hub holds Rules, Payroll, Tax % only)."
                + _tab_bar_csv_excel_hint
                + _main_tab_bar_db_hint
            ),
            (
                "Vendors: vendor master (detail + list), balances and activity; export vendors CSV (F5). "
                "Bills and payments use Enter Bills, Pay Bills, and Reports (Business hub holds Rules, Payroll, Tax % only)."
                + _tab_bar_csv_excel_hint
                + _main_tab_bar_db_hint
            ),
            (
                "Reconcile: Bank statements (CSV/PDF, AI line reconciliation, Match overlay sync) and Documents."
                + _tab_bar_csv_excel_hint
                + _main_tab_bar_db_hint
            ),
            (
                "More: Reports, Journal, Business hub, and Audit log."
                + _tab_bar_csv_excel_hint
                + _main_tab_bar_db_hint
            ),
        ]
        for i, tip in enumerate(tips):
            main_tab_bar.setTabToolTip(i, tip)

    def _teardown_main_tabs_for_rebuild(self) -> None:
        """Remove main tabs and dispose widgets except the shared Document Intake root widget."""
        old_reg = getattr(self, "_register_tab", None)
        if old_reg is not None:
            try:
                old_reg.reconciliationModeChanged.disconnect()
            except TypeError:
                pass
        rh = getattr(self, "_reconcile_hub", None)
        iw = getattr(self, "_intake_widget", None)
        if rh is not None and iw is not None:
            ix = rh.indexOf(iw)
            if ix >= 0:
                rh.removeTab(ix)
            iw.setParent(None)
        while self._tabs.count() > 0:
            w = self._tabs.widget(0)
            self._tabs.removeTab(0)
            if w is not None and w is not iw:
                w.deleteLater()

    # -- UI construction -----------------------------------------------------

    def _build_ui(self):
        self._build_menu_bar()

        # Container: header banner + tab widget
        container = QWidget()
        container.setToolTip(
            "Main workspace: fixed-order tabs (Invoices through More). "
            "Bank Import and Register host statement reconciliation, AI line reconciliation, and Register Match overlay. "
            "All tabs share the open SQLite company file (File → Backup / Restore, probooks.backup)."
        )
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        self._header = AppHeaderWidget()
        container_layout.addWidget(self._header)

        self._tabs = QTabWidget()
        self._tabs.setToolTip(
            "Main workspace: Invoices, Enter Bills, Pay Bills, Receive Payments, Bank Register, "
            "Chart of Accounts, Customers, Vendors, Reconcile, and More (hover each tab). "
            "File → Backup / Restore applies to the whole company database (CLI: probooks backup / restore)."
        )

        self._build_document_intake_widget()
        self._assemble_main_tabs()
        self._apply_main_tab_bar_tooltips()
        self._wire_register_bank_match_navigation()

        container_layout.addWidget(self._tabs)
        self.setCentralWidget(container)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        _boot_ver = application_version()
        self._status_bar.showMessage(
            escape_ampersand_for_qt(
                "Ready \u2013 drag & drop or use Import; bank CSV/PDF and AI line reconciliation: "
                "Reconcile → Bank statements (Ctrl+9); File → Backup saves the company .db."
            )
            + f" ProBooks+ai v{_boot_ver}."
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
            "Import PDF or images into the document inbox (Ctrl+O). "
            + _BANK_IMPORT_VIEW_POINTER
            + "Back up the company .db from File → Backup / probooks backup before risky changes.",
        )
        act_import_docs.triggered.connect(self._on_import)
        file_menu.addAction(act_import_docs)

        file_menu.addSeparator()

        act_create_company = QAction("Create &New Company…", self)
        _menu_action_tip(
            act_create_company,
            "Launch the setup wizard to create a new company database.",
        )
        act_create_company.triggered.connect(self._on_create_new_company)
        file_menu.addAction(act_create_company)

        self._switch_company_menu = file_menu.addMenu("S&witch Company →")
        self._rebuild_switch_company_menu()

        file_menu.addSeparator()

        act_backup = QAction("&Backup company file…", self)
        _menu_action_tip(
            act_backup,
            "Back up the company database to a file you choose (SQLite online backup via probooks.backup; "
            "same engine as probooks backup; safe while the app is open).",
        )
        act_backup.triggered.connect(self._on_backup_company)
        file_menu.addAction(act_backup)

        act_restore = QAction("&Restore from backup…", self)
        _menu_action_tip(
            act_restore,
            "Replace the company database from a backup .db file (probooks.backup / probooks restore; "
            "SQLite backup API; brief disconnect; reloads when done).",
        )
        act_restore.triggered.connect(self._on_restore_company)
        file_menu.addAction(act_restore)

        file_menu.addSeparator()

        act_exit = QAction("E&xit", self)
        act_exit.setShortcut("Ctrl+Q")
        _menu_action_tip(
            act_exit,
            "Exit ProBooks+ai (Ctrl+Q). Consider File → Backup if you want an extra copy of the open .db.",
        )
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        # View menu — tab shortcuts (tabs are created later; shortcuts fire after UI exists)
        view_menu = mb.addMenu("&View")
        _view_tab_tip_suffix = (
            " Same company SQLite file (File → Backup / Restore, probooks.backup)."
        )
        # Tab indices: 0=Dashboard, 1=Invoices, 2=Enter Bills, 3=Pay Bills,
        #              4=Receive Payments, 5=Bank Register, 6=Chart of Accounts,
        #              7=Customers, 8=Vendors, 9=Reconcile, 10=More
        _view_tab_tip_extra = {
            1: " Invoice entry workflow.",
            2: " Enter Bills screen.",
            3: " Pay Bills screen.",
            4: " Receive Payments screen.",
            5: " Bank Register: Match overlay (Bank Import can populate).",
            6: " Chart of Accounts editor.",
            7: " AR: customers, invoices, payments (primary route; Business hub is Rules/Payroll/Tax %).",
            8: " AP: vendors, bills, payments (primary route; Business hub is Rules/Payroll/Tax %).",
            9: " Reconcile: Bank statements + Documents (intake → review/match).",
        }
        for tab_idx, (sc, label) in zip(
            range(1, 11),  # skip Dashboard (index 0); Invoices=1 … More=10
            [
                ("Ctrl+1", "&Invoices"),
                ("Ctrl+2", "&Enter Bills"),
                ("Ctrl+3", "&Pay Bills"),
                ("Ctrl+4", "&Receive Payments"),
                ("Ctrl+5", "&Bank Register"),
                ("Ctrl+6", "Chart of &Accounts"),
                ("Ctrl+7", "&Customers"),
                ("Ctrl+8", "&Vendors"),
                ("Ctrl+9", "&Reconcile"),
                ("Ctrl+0", "&More"),
            ]
        ):
            act = QAction(label, self)
            act.setShortcut(sc)
            act.setShortcutContext(Qt.ApplicationShortcut)
            extra = _view_tab_tip_extra.get(tab_idx, " Reports, Journal, Business, Audit log.")
            _menu_action_tip(
                act, f"Show this main tab ({sc}).{extra}{_view_tab_tip_suffix}"
            )
            act.triggered.connect(
                lambda checked=False, i=tab_idx: self._set_main_tab_index(i)
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

        # Tools menu — general utilities (invoice entry on top-level Invoices tab)
        tools_menu = mb.addMenu("&Tools")
        act_tools_invoice = QAction("&Invoice\u2026", self)
        act_tools_invoice.setShortcut("Ctrl+Shift+I")
        act_tools_invoice.setShortcutContext(Qt.ApplicationShortcut)
        _menu_action_tip(
            act_tools_invoice,
            "Open the **Invoices** main tab (Ctrl+Shift+I). "
            "Full AR lists and payments: **Customers** tab. "
            "Same company .db (File → Backup / Restore, probooks.backup).",
        )
        act_tools_invoice.triggered.connect(self._on_tools_invoice)
        tools_menu.addAction(act_tools_invoice)

        tools_menu.addSeparator()

        act_opening_balance = QAction("&Opening Balance Wizard…", self)
        _menu_action_tip(
            act_opening_balance,
            "Open the Opening Balance Wizard to set a historical cut-off date and enter "
            "per-account opening balances. Posts one balanced GL journal entry. "
            "More → Assets for the fixed asset register.",
        )
        act_opening_balance.triggered.connect(self._on_tools_opening_balance)
        tools_menu.addAction(act_opening_balance)

        act_payee_categ = QAction("&Bulk Categorize Payees…", self)
        _menu_action_tip(
            act_payee_categ,
            "Assign COA accounts to uncategorized payees in one pass. "
            "Updates all matching bank transactions and saves categorization rules for future imports.",
        )
        act_payee_categ.triggered.connect(self._on_tools_payee_categorize)
        tools_menu.addAction(act_payee_categ)

        # Recon menu — bank register bulk actions (moved from the register tab for a table-focused UI)
        recon_menu = mb.addMenu("&Recon")

        m_reg_actions = recon_menu.addMenu("Register &Actions")
        act_reg_add = QAction("&Add Transaction\u2026", self)
        _menu_action_tip(
            act_reg_add,
            "Insert one bank transaction for the selected account (persisted; optional COA; "
            "date prefills to the latest register date when any exist). "
            "Back up the company .db before bulk entry (File → Backup / probooks backup).",
        )
        act_reg_add.triggered.connect(
            lambda: self._register_tab.tools_register_add_transaction()
        )
        m_reg_actions.addAction(act_reg_add)
        act_reg_post = QAction("&Post Selected to GL", self)
        _menu_action_tip(
            act_reg_post,
            "Post selected unposted rows to the general ledger. "
            "Shortcut: Ctrl+Shift+G when Register has focus. "
            "File → Backup / probooks backup before big runs.",
        )
        act_reg_post.triggered.connect(
            lambda: self._register_tab.tools_register_post_selected()
        )
        m_reg_actions.addAction(act_reg_post)
        act_reg_export = QAction("&Export CSV\u2026", self)
        _menu_action_tip(
            act_reg_export,
            "Export the current register grid to CSV (active filter and column order). "
            "UTF-8 with BOM for Excel. Shortcut: Ctrl+Shift+E when Register has focus.",
        )
        act_reg_export.triggered.connect(
            lambda: self._register_tab.tools_register_export_csv()
        )
        m_reg_actions.addAction(act_reg_export)

        m_reg_recon = recon_menu.addMenu("&Reconciliation")
        act_reg_mark_clr = QAction("&Mark Cleared", self)
        _menu_action_tip(
            act_reg_mark_clr,
            "Set cleared on selected rows. Shortcut: Ctrl+Shift+C when Register has focus.",
        )
        act_reg_mark_clr.triggered.connect(
            lambda: self._register_tab.tools_register_mark_cleared()
        )
        m_reg_recon.addAction(act_reg_mark_clr)
        act_reg_clear_clr = QAction("&Clear Cleared", self)
        _menu_action_tip(
            act_reg_clear_clr,
            "Clear cleared on selected rows. Shortcut: Ctrl+Shift+U when Register has focus.",
        )
        act_reg_clear_clr.triggered.connect(
            lambda: self._register_tab.tools_register_clear_cleared()
        )
        m_reg_recon.addAction(act_reg_clear_clr)

        m_reg_attach = recon_menu.addMenu("&Attachments")
        act_reg_attach = QAction("&Attach File\u2026", self)
        _menu_action_tip(
            act_reg_attach,
            "Choose a file and store its path on all selected rows as the attachment.",
        )
        act_reg_attach.triggered.connect(
            lambda: self._register_tab.tools_register_attach_file()
        )
        m_reg_attach.addAction(act_reg_attach)
        act_reg_clear_att = QAction("&Clear Attachment", self)
        _menu_action_tip(
            act_reg_clear_att,
            "Clear the attachment path on selected rows.",
        )
        act_reg_clear_att.triggered.connect(
            lambda: self._register_tab.tools_register_clear_attachment()
        )
        m_reg_attach.addAction(act_reg_clear_att)

        m_reg_txn = recon_menu.addMenu("&Transaction Tools")
        act_reg_splits = QAction("&Splits\u2026", self)
        _menu_action_tip(
            act_reg_splits,
            "Split one unposted transaction into two COA lines (amounts must sum to the bank amount).",
        )
        act_reg_splits.triggered.connect(
            lambda: self._register_tab.tools_register_splits_dialog()
        )
        m_reg_txn.addAction(act_reg_splits)
        act_reg_transfer = QAction("&Transfer To\u2026", self)
        _menu_action_tip(
            act_reg_transfer,
            "Mark selected rows as transfers, choosing the other bank account (counterparty).",
        )
        act_reg_transfer.triggered.connect(
            lambda: self._register_tab.tools_register_transfer_dialog()
        )
        m_reg_txn.addAction(act_reg_transfer)
        act_reg_link = QAction("&Link Payment\u2026", self)
        _menu_action_tip(
            act_reg_link,
            "Link one selected row to an AR payment, AP payment, payroll run, or open invoice/bill (or clear an existing link). "
            "When the stored link is complete, the dialog includes Open linked Business record…. ",
        )
        act_reg_link.triggered.connect(
            lambda: self._register_tab.tools_register_link_payment_dialog()
        )
        m_reg_txn.addAction(act_reg_link)
        act_reg_open_biz = QAction("Open &linked Business record", self)
        _menu_action_tip(
            act_reg_open_biz,
            "Switch to the Business tab for the current row’s match: edit invoice or bill, payroll tax lines, "
            "or a short AR/AP payment summary. Shortcut: Ctrl+Shift+B when Register has focus. "
            "Same as right-click → Open linked Business record… (when shown) or double-click the Match column; "
            "opens Business when the link is complete, else the usual Business link message.",
        )
        act_reg_open_biz.triggered.connect(
            lambda: self._register_tab.tools_register_open_linked_business_record()
        )
        m_reg_txn.addAction(act_reg_open_biz)

        m_reg_flags = recon_menu.addMenu("&Flags")
        act_reg_flag_rcpt = QAction("&Flag Needs Receipt", self)
        _menu_action_tip(
            act_reg_flag_rcpt,
            "Set the needs-receipt flag on selected rows (posted rows may not allow changes).",
        )
        act_reg_flag_rcpt.triggered.connect(
            lambda: self._register_tab.tools_register_flag_needs_receipt()
        )
        m_reg_flags.addAction(act_reg_flag_rcpt)
        act_reg_clear_rcpt = QAction("&Clear Needs Receipt", self)
        _menu_action_tip(
            act_reg_clear_rcpt,
            "Clear the needs-receipt flag on selected rows.",
        )
        act_reg_clear_rcpt.triggered.connect(
            lambda: self._register_tab.tools_register_clear_needs_receipt()
        )
        m_reg_flags.addAction(act_reg_clear_rcpt)

        # Help menu
        help_menu = mb.addMenu("&Help")
        act_roadmap = QAction("Product &roadmap (local file)\u2026", self)
        _menu_action_tip(
            act_roadmap,
            "Open docs/ROADMAP.md; implementation snapshot notes backup / CLI parity (probooks.backup).",
        )
        act_roadmap.triggered.connect(self._on_help_roadmap)
        help_menu.addAction(act_roadmap)
        act_intake_keys = QAction("Document &intake shortcuts…", self)
        _menu_action_tip(
            act_intake_keys,
            "F5 refresh, Ctrl+O import, File → Backup/Restore (probooks.backup), View chords; "
            "the dialog summarizes UTF-8 BOM CSV exports on Bank Import (batch preview + AI line reconciliation), "
            "Register, Reports, Journal, Business, and Audit; "
            "Bank Import Import CSV… reads UTF-8 optional BOM; links to other Help topics. "
            "View → Bank Import and Register status tips mention AI line reconciliation and Match overlay.",
        )
        act_intake_keys.triggered.connect(
            lambda: show_document_intake_keyboard_shortcuts_dialog(self)
        )
        help_menu.addAction(act_intake_keys)
        act_bank_import_keys = QAction("Bank &import shortcuts…", self)
        _menu_action_tip(
            act_bank_import_keys,
            "F5 refresh and context-menu shortcuts for Bank Import (batch preview: copy row, txn id, date, amount, payee, memo, ref, COA, open linked Business when the row has a complete bank link, double-click for the same Business link prompts as Register; "
            "line-reconciliation grid: statement/register date, amount, description, register txn id, open linked Business when Reg # has a complete bank link, double-click when Reg # is set for the same prompts; "
            "Ctrl+Shift+B on preview or line grid when focused); "
            "Import CSV reads UTF-8 with optional BOM; reconciliation / line-compare CSV uses UTF-8 BOM for Excel. "
            "Document intake help lists File backup/restore.",
        )
        act_bank_import_keys.triggered.connect(
            lambda: show_bank_import_keyboard_shortcuts_dialog(self)
        )
        help_menu.addAction(act_bank_import_keys)
        act_register_keys = QAction("Bank &register keyboard shortcuts…", self)
        _menu_action_tip(
            act_register_keys,
            "F5, Ctrl+Shift+G/E/B/C/U, and register grid shortcuts (row menu: copy row, txn id, date, amount, payee, memo, ref, COA, open linked Business); "
            "Ctrl+Shift+E export CSV uses UTF-8 BOM for Excel. "
            "Recon menu lists Register Actions, Reconciliation, Attachments, Transaction Tools, and Flags (same handlers as the old register buttons). "
            "Link payment dialog includes Open linked Business when the stored link is complete. "
            "Help dialog links to Bank import for AI line-reconciliation field copies. "
            "Document intake help lists File backup/restore.",
        )
        act_register_keys.triggered.connect(
            lambda: show_register_keyboard_shortcuts_dialog(self)
        )
        help_menu.addAction(act_register_keys)
        act_business_keys = QAction("&Business shortcuts…", self)
        _menu_action_tip(
            act_business_keys,
            "F5, Tax % Ctrl+S, and Business tab context menus; CSV exports use UTF-8 BOM for Excel. "
            "Document intake help lists File backup/restore.",
        )
        act_business_keys.triggered.connect(
            lambda: show_business_keyboard_shortcuts_dialog(self)
        )
        help_menu.addAction(act_business_keys)
        act_more_tab_keys = QAction("&More tab shortcuts (F5)…", self)
        _menu_action_tip(
            act_more_tab_keys,
            "F5 refresh and View chords for COA, Journal, Reports, and Audit; "
            "the dialog summarizes UTF-8 BOM CSV exports, row copy menus on Bank register / Import preview "
            "and the Bank Import line-reconciliation grid, and cross-links Register, Business, and Bank Import. "
            "Document intake shortcuts summarizes File → Backup/Restore.",
        )
        act_more_tab_keys.triggered.connect(
            lambda: show_more_main_tabs_keyboard_shortcuts_dialog(self)
        )
        help_menu.addAction(act_more_tab_keys)
        help_menu.addSeparator()
        act_tips = QAction("Show &hover tips", self)
        act_tips.setCheckable(True)
        act_tips.setChecked(_tips_enabled())
        _menu_action_tip(
            act_tips,
            "Toggle verbose hover tooltips on/off — takes effect immediately, saved across sessions.",
        )
        act_tips.triggered.connect(lambda checked: _set_tips_enabled(checked))
        help_menu.addAction(act_tips)

        help_menu.addSeparator()
        act_about = QAction("&About ProBooks+ai", self)
        _menu_action_tip(
            act_about,
            "Version in the dialog; status bar and banner ProBooks+ai tooltip echo the same package version. "
            "Ok notes Help shortcuts (UTF-8 BOM CSV) and File backup (probooks.backup).",
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
            ok_tip="Close; Help lists shortcuts (including UTF-8 BOM CSV for Excel); "
            "Bank Import covers AI line reconciliation and Match overlay sync; "
            "status bar lists ProBooks+ai with the package version (banner name tooltip matches); "
            "File → Backup/Restore uses probooks.backup (same as CLI).",
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
        else:
            self._detail.clear_view()

    def _on_run_ai(self, doc_id: int):
        did = coerce_combo_int_id(doc_id)
        if did is None:
            return
        if self._worker and self._worker.isRunning():
            message_box_information_ok(
                self,
                "AI Running",
                "Please wait \u2013 AI extraction is already in progress.",
                ok_tip="Close; wait for the current extraction to finish before running again.",
            )
            return

        row = self._db.get_document(did)
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
        self._db.set_status(did, "Extracted")

        self._worker = AIWorker(did, row["stored_path"], row["mimetype"], self._coa)
        self._worker.finished.connect(lambda res, sug: self._on_ai_done(did, res, sug))
        self._worker.error.connect(lambda err: self._on_ai_error(did, err))
        self._worker.start()

    def _on_ai_done(self, doc_id: int, result, suggestions):
        did = coerce_combo_int_id(doc_id)
        if did is None:
            return
        self._db.save_extraction(did, result)
        self._db.set_status(did, "Needs Review")
        self._refresh_inbox()
        self._detail.populate_ai_result(result, suggestions)
        doc = self._db.get_document(did)
        name = doc["filename"] if doc else str(did)
        self._status_bar.showMessage(
            f"AI extraction complete for {escape_ampersand_for_qt(name)}."
        )

    def _on_ai_error(self, doc_id: int, error: str):
        did = coerce_combo_int_id(doc_id)
        if did is None:
            return
        self._db.set_status(did, "Error")
        self._refresh_inbox()
        message_box_critical_ok(
            self,
            "AI Extraction Failed",
            f"Error:\n{escape_ampersand_for_qt(error)}",
            ok_tip="Close; check network, API key, and document format, then retry.",
        )
        self._status_bar.showMessage("AI extraction failed.")

    def _on_approve(self, doc_id: int):
        did = coerce_combo_int_id(doc_id)
        if did is None:
            return
        values = self._detail.collect_approved_values()
        self._db.save_approved(did, values)
        self._db.set_status(did, "Approved")
        self._refresh_inbox()
        self._status_bar.showMessage("Document approved and values saved.")

    def _on_mark_posted(self, doc_id: int):
        did = coerce_combo_int_id(doc_id)
        if did is None:
            return
        row = self._db.get_document(did)
        if row and row["status"] != "Approved":
            message_box_warning_ok(
                self,
                "Not Yet Approved",
                "Please approve the document before marking it as Posted.",
                ok_tip="Close; use Approve in the detail pane first.",
            )
            return
        self._db.set_status(did, "Posted")
        self._refresh_inbox()
        self._status_bar.showMessage("Document marked as Posted.")

    def _on_reject(self, doc_id: int):
        did = coerce_combo_int_id(doc_id)
        if did is None:
            return
        self._db.set_status(did, "Needs Review")
        self._refresh_inbox()
        self._status_bar.showMessage("Document flagged \u2013 Needs Review.")

    def _on_route_to_invoice(self, values: dict) -> None:
        """Switch to Invoices tab and pre-fill header fields from extracted document."""
        self._invoice_screen.prefill_from_document(values)
        idx = self._tabs.indexOf(self._invoice_screen)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)
        vendor = (values.get("vendor") or "").strip()
        total = values.get("total")
        hint = f"Routed to Invoices"
        if vendor:
            hint += f" \u2014 {vendor}"
        if total is not None:
            hint += f", total ${total:,.2f}"
        self._status_bar.showMessage(hint)

    def _on_route_to_bill(self, values: dict) -> None:
        """Switch to Enter Bills tab and pre-fill header fields from extracted document."""
        self._enter_bills_screen.prefill_from_document(values)
        idx = self._tabs.indexOf(self._enter_bills_screen)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)
        vendor = (values.get("vendor") or "").strip()
        total = values.get("total")
        hint = f"Routed to Enter Bills"
        if vendor:
            hint += f" \u2014 {vendor}"
        if total is not None:
            hint += f", total ${total:,.2f}"
        self._status_bar.showMessage(hint)

    # -- helpers -------------------------------------------------------------

    def _refresh_inbox(self):
        docs = self._db.list_documents()
        self._inbox.populate(docs)
        self._on_selection_changed()

    def _sync_coa_assets_to_bank_accounts(self) -> None:
        """
        Ensure every active COA Asset account has a matching row in bank_accounts.

        This lets users create accounts via Chart of Accounts (e.g. "Cash – Checking")
        and immediately see them in the Bank Register account picker — without having to
        go through a separate bank account creation flow.

        Matching is done by gl_display_account (e.g. "1000 Cash – Checking").
        Existing bank_accounts rows are never deleted or renamed here.
        """
        try:
            coa_rows = self._coa_db.list_accounts(include_inactive=False)
            # Build set of gl_display_account keys already in bank_accounts
            existing_keys: set[str] = set()
            for ba in self._bank_db.list_bank_accounts(include_inactive=True):
                key = (ba["gl_display_account"] or "").strip()
                if key:
                    existing_keys.add(key)
                else:
                    # Fallback: match by name
                    existing_keys.add((ba["name"] or "").strip())

            for row in coa_rows:
                atype = (row["account_type"] or "").lower()
                if atype != "asset":
                    continue  # only Asset accounts become bank accounts
                num  = str(row["account_number"] or "").strip()
                name = str(row["account_name"] or "").strip()
                if not name:
                    continue
                display_key = f"{num} {name}".strip() if num else name
                if display_key in existing_keys or name in existing_keys:
                    continue  # already present
                sub = str(row["sub_type"] or "").strip()
                self._bank_db.add_bank_account(
                    name=name,
                    account_number=num,
                    bank_name=sub or "",
                    account_type="checking",  # sensible default; user can edit later
                    gl_display_account=display_key,
                )
                existing_keys.add(display_key)
        except Exception as _sync_err:
            import traceback
            traceback.print_exc()  # visible in console; never blocks a COA save

    def _migrate_opening_balances_to_bank_register(self) -> None:
        """
        One-time migration: for every GL journal entry with source='opening_balance'
        find lines whose account name matches a bank_accounts row and create a
        bank_transaction so the balance appears in the register.

        Safe to run on every startup — skips lines that already have a transaction
        (matched by description + date + bank_account_id).
        """
        try:
            from probooksai.bank_import import make_manual_entry_fingerprint
            conn = self._bank_db._conn

            # GL opening-balance lines (exclude the Retained Earnings offset)
            gl_rows = conn.execute("""
                SELECT jel.account, jel.debit, jel.credit, je.entry_date
                FROM journal_entry_lines jel
                JOIN journal_entries je ON jel.entry_id = je.id
                WHERE je.source = 'opening_balance'
            """).fetchall()
            if not gl_rows:
                return

            # Build account-name → bank_account_id lookup
            bank_rows = conn.execute(
                "SELECT id, name, gl_display_account FROM bank_accounts"
            ).fetchall()
            acct_map: dict[str, int] = {}
            for ba in bank_rows:
                k = (ba["gl_display_account"] or "").strip()
                if k:
                    acct_map[k] = int(ba["id"])
                n = (ba["name"] or "").strip()
                if n and n not in acct_map:
                    acct_map[n] = int(ba["id"])

            OB_BATCH_NAME = "(Opening Balance)"
            for gl in gl_rows:
                acct_key = (gl["account"] or "").strip()
                bank_id = acct_map.get(acct_key)
                if bank_id is None:
                    continue
                debit  = float(gl["debit"]  or 0.0)
                credit = float(gl["credit"] or 0.0)
                amount = round(debit - credit, 2)   # positive = asset increase
                if abs(amount) < 0.005:
                    continue
                txn_date = gl["entry_date"]
                desc = f"Opening balance as of {txn_date}"

                # Skip if already migrated
                exists = conn.execute(
                    """SELECT id FROM bank_transactions
                       WHERE bank_account_id=? AND description=? AND txn_date=?
                       LIMIT 1""",
                    (bank_id, desc, txn_date),
                ).fetchone()
                if exists:
                    continue

                # Get or create opening-balance batch for this account
                batch_row = conn.execute(
                    "SELECT id FROM bank_import_batches WHERE bank_account_id=? AND filename=? LIMIT 1",
                    (bank_id, OB_BATCH_NAME),
                ).fetchone()
                if batch_row:
                    batch_id = int(batch_row["id"])
                else:
                    from probooksai.bank_import import _now as _bi_now
                    cur = conn.execute(
                        """INSERT INTO bank_import_batches
                               (bank_account_id, filename, imported_at)
                           VALUES (?, ?, ?)""",
                        (bank_id, OB_BATCH_NAME, _bi_now()),
                    )
                    conn.commit()
                    batch_id = int(cur.lastrowid)

                fp = make_manual_entry_fingerprint()
                conn.execute(
                    """INSERT INTO bank_transactions
                           (batch_id, bank_account_id, txn_date,
                            description, amount, ref_number, fingerprint,
                            memo, coa_account)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (batch_id, bank_id, txn_date, desc, amount,
                     "OB", fp, "Opening balance", acct_key),
                )
                conn.commit()
        except Exception:
            import traceback
            traceback.print_exc()

    def _on_coa_changed(self):
        """Called when the COA editor modifies the chart of accounts."""
        # Sync any new COA asset accounts into bank_accounts so the register sees them
        self._sync_coa_assets_to_bank_accounts()
        # Refresh the dropdown list used in the document intake detail pane
        self._coa = load_coa()
        coa_display = self._coa_db.display_list()
        self._detail.update_coa(coa_display)
        self._register_tab.refresh_coa_choices()
        self._register_tab.refresh_bank_accounts()
        if hasattr(self, "_asset_register_tab"):
            self._asset_register_tab.update_coa_list(coa_display)

    def _on_dashboard_navigate(self, target: str) -> None:
        """Dashboard quick-action buttons → jump to the requested tab."""
        if not hasattr(self, "_tabs"):
            return
        target_map = {
            "invoices": getattr(self, "_invoice_screen", None),
            "bills": getattr(self, "_enter_bills_screen", None),
            "register": getattr(self, "_register_tab", None),
        }
        widget = target_map.get(target)
        if widget is not None:
            idx = self._tabs.indexOf(widget)
            if idx >= 0:
                self._tabs.setCurrentIndex(idx)

    def _on_tools_invoice(self) -> None:
        """Tools → Invoice: top-level Invoices tab."""
        if not hasattr(self, "_tabs") or not hasattr(self, "_invoice_screen"):
            return
        idx = self._tabs.indexOf(self._invoice_screen)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)

    def _on_tools_opening_balance(self) -> None:
        """Tools → Opening Balance Wizard."""
        if not hasattr(self, "_bank_db"):
            message_box_warning_ok(self, "No company file", "Open a company file first.")
            return
        from desktop_app.opening_balance_wizard import OpeningBalanceWizard
        coa_entries = self._coa_db.list_accounts() if hasattr(self, "_coa_db") else []
        dlg = OpeningBalanceWizard(self._bank_db._conn, coa_entries, parent=self)
        dlg.exec()

    def _on_tools_payee_categorize(self) -> None:
        """Tools → Bulk Categorize Payees."""
        if not hasattr(self, "_bank_db"):
            message_box_warning_ok(self, "No company file", "Open a company file first.")
            return
        from desktop_app.payee_categorize_dialog import PayeeCategorizeDialog
        coa_list = self._coa_db.display_list() if hasattr(self, "_coa_db") else []
        dlg = PayeeCategorizeDialog(self._bank_db._conn, coa_list, parent=self)
        dlg.exec()

    def _set_main_tab_index(self, index: int) -> None:
        if not hasattr(self, "_tabs"):
            return
        if index < 0 or index >= self._tabs.count():
            return
        self._tabs.setCurrentIndex(index)

    def _focus_bank_register_tab(self) -> None:
        """Focus **Bank register** after Bank Import syncs line-match results to the Match overlay.

        Shows a temporary **status bar** message, then schedules :meth:`_update_company_status`
        so the default company line returns when the message clears.
        """
        if not hasattr(self, "_tabs") or not hasattr(self, "_register_tab"):
            return
        idx = self._tabs.indexOf(self._register_tab)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)
            if hasattr(self, "_status_bar"):
                self._status_bar.showMessage(
                    "Match overlay updated on Bank register. Reconciliation mode is on. "
                    "Row field copies: Bank Import line-reconciliation grid (Help → Bank import shortcuts…).",
                    _STMT_MATCH_SYNC_STATUS_MS,
                )
                QTimer.singleShot(
                    _STMT_MATCH_SYNC_STATUS_MS,
                    self._update_company_status,
                )

    def _navigate_register_bank_match_link(self, link_type: str, link_id: int) -> None:
        """Bank register Match link: AR/AP go to Customers/Vendors; payroll opens More → Business → Payroll."""
        if not hasattr(self, "_customers_tab") or not hasattr(self, "_vendors_tab"):
            return
        lt = (link_type or "").strip()
        try:
            lid = int(link_id)
        except (TypeError, ValueError):
            message_box_information_ok(
                self,
                "Business link",
                "Invalid link id.",
                ok_tip="Close; clear the bank link and set it again if needed.",
            )
            return
        conn = self._bank_db._conn
        if lt == "ar_invoice":
            idx = self._tabs.indexOf(self._invoice_screen)
            if idx >= 0:
                self._tabs.setCurrentIndex(idx)
            self._invoice_screen.open_invoice_by_id(lid)
            return
        if lt == "ap_bill":
            idx = self._tabs.indexOf(self._enter_bills_screen)
            if idx >= 0:
                self._tabs.setCurrentIndex(idx)
            self._enter_bills_screen.open_bill_by_id(lid)
            return
        if lt == "ar_payment":
            idx = self._tabs.indexOf(self._receive_payments_screen)
            if idx >= 0:
                self._tabs.setCurrentIndex(idx)
            row = conn.execute(
                """
                SELECT p.payment_date, p.amount, p.reference, c.name AS party_name
                FROM ar_payments p
                JOIN customers c ON c.id = p.customer_id
                WHERE p.id = ?
                """,
                (lid,),
            ).fetchone()
            if row is None:
                message_box_information_ok(
                    self,
                    "AR payment",
                    f"No AR payment #{lid} in this company file.",
                    ok_tip="Close; the link may point at removed data.",
                )
                return
            r = dict(row)
            ref = (r.get("reference") or "").strip() or "—"
            message_box_information_ok(
                self,
                "AR payment",
                f"AR payment #{lid}: {r['payment_date']}  ${float(r['amount']):.2f}  — {r['party_name']}\n"
                f"Reference: {ref}\n\n"
                "Export AR payments CSV from More → Reports or Receive Payments as needed; record new payments via Record customer payment… on Receive Payments.",
                ok_tip="Close; you are on the Receive Payments tab.",
            )
            return
        if lt == "ap_payment":
            idx = self._tabs.indexOf(self._pay_bills_screen)
            if idx >= 0:
                self._tabs.setCurrentIndex(idx)
            row = conn.execute(
                """
                SELECT p.payment_date, p.amount, p.reference, v.name AS party_name
                FROM ap_payments p
                JOIN vendors v ON v.id = p.vendor_id
                WHERE p.id = ?
                """,
                (lid,),
            ).fetchone()
            if row is None:
                message_box_information_ok(
                    self,
                    "AP payment",
                    f"No AP payment #{lid} in this company file.",
                    ok_tip="Close; the link may point at removed data.",
                )
                return
            r = dict(row)
            ref = (r.get("reference") or "").strip() or "—"
            message_box_information_ok(
                self,
                "AP payment",
                f"AP payment #{lid}: {r['payment_date']}  ${float(r['amount']):.2f}  — {r['party_name']}\n"
                f"Reference: {ref}\n\n"
                "Export AP payments CSV from More → Reports or Pay Bills as needed; record new payments on Pay Bills.",
                ok_tip="Close; you are on the Pay Bills tab.",
            )
            return
        if lt == "payroll_run":
            if not hasattr(self, "_business_hub") or not hasattr(self, "_more_hub"):
                return
            idx = self._tabs.indexOf(self._more_hub)
            if idx >= 0:
                self._tabs.setCurrentIndex(idx)
            self._more_hub.setCurrentWidget(self._business_hub)
            self._business_hub.navigate_bank_match_link(self, link_type, link_id)
            return
        message_box_information_ok(
            self,
            "Business link",
            f"Unsupported link type: {lt or '(empty)'}",
            ok_tip="Close; clear the link or pick a supported AR/AP/payroll target.",
        )

    def _wire_register_bank_match_navigation(self) -> None:
        if not hasattr(self, "_register_tab"):
            return
        self._register_tab.openBankMatchNavigationRequested.connect(
            self._navigate_register_bank_match_link
        )

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
        _sv = application_version()
        self._status_bar.showMessage(
            escape_ampersand_for_qt(
                f"Company: {p}  \u2013  drag & drop or Import; bank CSV/PDF and AI line reconciliation: "
                f"Reconcile → Bank statements (Ctrl+9); File → Backup copies this .db."
            )
            + f" ProBooks+ai v{_sv}."
        )
        if p:
            self._header.set_company_name(Path(p).name)
        else:
            self._header.set_company_name("No company file")
        self._sync_window_title()

    def _rebuild_bank_related_tabs(self):
        """Replace main tabs after switching SQLite company file (reuses Document Intake widget)."""
        self._teardown_main_tabs_for_rebuild()
        self._assemble_main_tabs()
        self._apply_main_tab_bar_tooltips()
        self._wire_register_bank_match_navigation()

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
        # Ensure any COA asset accounts are represented in bank_accounts before building tabs
        self._sync_coa_assets_to_bank_accounts()
        # Seed bank_transactions for any existing GL opening-balance entries
        self._migrate_opening_balances_to_bank_register()
        self._rebuild_bank_related_tabs()
        self._detail.clear_view()
        self._detail.update_coa(self._coa_db.display_list())
        self._refresh_inbox()
        self._update_company_status()
        if hasattr(self, "_dashboard_tab"):
            self._dashboard_tab.set_connection(self._bank_db._conn)
        # Track in recent companies
        try:
            row = self._bank_db._conn.execute(
                "SELECT value FROM company_settings WHERE key='company_name'"
            ).fetchone()
            _co_name = row[0] if row else Path(resolved).stem
        except Exception:
            _co_name = Path(resolved).stem
        self._add_to_recent_companies(resolved, _co_name)

    def _switch_company_database(self, path: str, *, create_new: bool = False) -> None:
        if self._worker and self._worker.isRunning():
            message_box_warning_ok(
                self,
                "Busy",
                "Wait for AI extraction to finish before switching company files.",
                ok_tip="Close; wait for AI, then switch; consider File → Backup / probooks backup before replacing the .db.",
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
                    "This path already exists; Yes opens it as the company database (reload from disk), No cancels. "
                    "File → Backup / probooks backup can copy your current .db before switching."
                )
                tip_message_box_buttons(
                    box,
                    yes="Switch to this .db (reload from disk); use File → Backup / probooks backup on the current file first if needed.",
                    no="Cancel; keep the current company file (back it up with File → Backup before switching if unsure).",
                )
                reply = box.exec()
                if reply != QMessageBox.StandardButton.Yes:
                    return
        elif not p.exists():
            message_box_warning_ok(
                self,
                "Not found",
                f"File does not exist:\n{escape_ampersand_for_qt(str(p))}",
                ok_tip="Close; pick an existing .db or use File → New company; back up live data with File → Backup (probooks.backup).",
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
        box.setWindowTitle("Restore company database (probooks restore)")
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
            yes="Overwrite the live company .db with the backup (probooks restore / File → Restore; probooks.backup).",
            no="Cancel restore; keep the current file (File → Backup first if you want a copy).",
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

    def _on_create_new_company(self) -> None:
        """File → Create New Company: launch the setup wizard."""
        from desktop_app.first_run_wizard import FirstRunWizard, apply_wizard_results
        wiz = FirstRunWizard(parent=self)
        if wiz.exec() != FirstRunWizard.DialogCode.Accepted or not wiz.db_path:
            return
        self._switch_company_database(wiz.db_path, create_new=True)
        apply_wizard_results(wiz, self._bank_db)
        # Rebuild bank-related tabs now that the wizard has written the bank account
        self._rebuild_bank_related_tabs()
        if hasattr(self, "_dashboard_tab"):
            self._dashboard_tab.refresh()

    def _add_to_recent_companies(self, path: str, name: str) -> None:
        """Prepend path|name to the QSettings recent-companies list (max 10, deduplicated)."""
        settings = QSettings()
        raw: list = settings.value("recent_companies", [], type=list)  # type: ignore[assignment]
        entry = f"{name}|{path}"
        # Remove any existing entry for this path
        raw = [r for r in raw if not r.endswith(f"|{path}") and not r == entry]
        raw.insert(0, entry)
        settings.setValue("recent_companies", raw[:10])
        self._rebuild_switch_company_menu()

    def _rebuild_switch_company_menu(self) -> None:
        """Repopulate the Switch Company submenu from QSettings."""
        if not hasattr(self, "_switch_company_menu"):
            return
        menu = self._switch_company_menu
        menu.clear()
        settings = QSettings()
        raw: list = settings.value("recent_companies", [], type=list)  # type: ignore[assignment]
        if not raw:
            placeholder = menu.addAction("(no recent companies)")
            placeholder.setEnabled(False)
            return
        for entry in raw:
            parts = entry.split("|", 1)
            if len(parts) != 2:
                continue
            display_name, db_path = parts
            action = menu.addAction(f"{display_name}  —  {db_path}")
            action.setData(db_path)
            action.triggered.connect(lambda checked=False, p=db_path: self._switch_company_database(p, create_new=False))

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
            "(see README: Default database paths). "
            "Back up this file from the app (File → Backup) or CLI (probooks backup; probooks.backup)."
        ),
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName("ProBooks+ai")
    app.setOrganizationName("ProBooks+ai")
    apply_dark_theme(app)

    # Install global tooltip filter (default: tips off; user can enable in Help menu)
    global _tip_filter
    _tip_filter = _TipFilter(enabled=_tips_enabled(), parent=app)
    app.installEventFilter(_tip_filter)
    db_path = args.database
    if db_path is None:
        last = QSettings().value("company_database_path", "", type=str) or ""
        if last and Path(last).is_file():
            db_path = last

    # First run: no company file configured → launch setup wizard
    _wizard_results: FirstRunWizard | None = None
    if db_path is None:
        wiz = FirstRunWizard()
        if wiz.exec() != FirstRunWizard.DialogCode.Accepted or not wiz.db_path:
            sys.exit(0)  # user cancelled — exit cleanly
        db_path = wiz.db_path
        _wizard_results = wiz

    window = MainWindow(db_path=db_path)

    # Apply company info + bank account saved in the wizard, then refresh UI
    if _wizard_results is not None:
        apply_wizard_results(_wizard_results, window._bank_db)
        # Bank account was just written — rebuild register/import tabs so they see it
        window._rebuild_bank_related_tabs()
        if hasattr(window, "_dashboard_tab"):
            window._dashboard_tab.refresh()

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
