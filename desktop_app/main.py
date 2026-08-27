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
Top-level menus: **File** (includes **New Company…** — the guided setup wizard that captures identity + new ``.db`` + sibling backup folder; on first launch with no saved company path, a welcome prompt routes here), **View**, **Edit**, **Tools** (e.g. **Invoice…** Ctrl+Shift+I to the **Invoices** tab), **Recon** (bank register bulk actions in submenus), **Help**.
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
    QApplication, QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
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
from probooksai.business import backfill_ar_invoice_journals
from probooksai.company_identity import (
    get_company_identity,
    is_company_setup_complete,
    save_company_identity,
)
from desktop_app.bank_import_tab import (
    BankImportTab,
    show_bank_import_keyboard_shortcuts_dialog,
)
from desktop_app.bank_statement_intake_panel import BankStatementIntakePanel
from probooksai.bank_statement_intake_ai_provider import build_default_ai_provider
from desktop_app.coa_tab import COATab, is_bank_like_coa
from desktop_app.use_register_dialog import UseRegisterDialog
from desktop_app.flexible_date import (
    attach_line_edit_us_date_normalization,
    format_iso_to_us_display,
    line_edit_to_iso_or_raw,
)
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
from desktop_app.check_screen import CheckScreen
from desktop_app.enter_bills_screen import EnterBillsScreen
from desktop_app.invoice_codes_screen import InvoiceCodesScreen
from desktop_app.invoice_screen import InvoiceScreen
from desktop_app.pay_bills_screen import PayBillsScreen
from desktop_app.receive_checks_screen import ReceiveChecksScreen
from desktop_app.make_deposits_screen import MakeDepositsScreen
from desktop_app.tracker_screens import BillTrackerScreen, IncomeTrackerScreen
from desktop_app.create_company_file_dialog import CreateCompanyFileDialog
from desktop_app.hover_messages import install_global_hover_message_suppression
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
    message_box_question_yes_no,
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
        "Ctrl+1 Invoices, Ctrl+2 Codes, Ctrl+3 Write Checks, Ctrl+4–Ctrl+0 other main tabs, Ctrl+Shift+R Reconcile, Ctrl+Shift+M More "
        "(Reports, Journal, Business, Audit log) — all tabs share the open "
        "company SQLite file (File → Backup / Restore, probooks.backup). "
        "Use **Reconcile** (Ctrl+Shift+R) → **Bank statements** for statement import and **Bank Register** (Ctrl+7) for the Match overlay.\n\n"
        "**Recon** menu — **Bank register** bulk row actions (add transaction, post to GL, export CSV, cleared, "
        "attachments, splits, transfer, link payment, open linked Business record, receipt flags) when you use Bank Register (Ctrl+7). "
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
        "Bank CSV/PDF and AI line reconciliation: Ctrl+Shift+R Reconcile → Bank statements; "
        "Register Match overlay: Ctrl+7 Bank Register; register bulk actions: Recon menu. "
        "Company .db: File → Backup / Restore (probooks.backup).",
    )


# Accepted MIME types / file extensions
ACCEPTED_MIMES = {"application/pdf", "image/jpeg", "image/png"}
ACCEPTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}

STATUS_COLORS = THEME_STATUS_COLORS

INBOX_HEADER_COLOR = "#1F3864"  # dark navy – matches ProBooks+ai branding

# Intake-adjacent tooltips: bank import lives under the Reconcile top-level tab (View Ctrl+Shift+R).
_BANK_IMPORT_VIEW_POINTER = (
    "Bank CSV/PDF and AI line reconciliation: Reconcile tab → Bank statements (View → Reconcile, Ctrl+Shift+R). "
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
    deleteRequested = Signal(int)   # emitted with doc_id when user confirms delete

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
        it = self.item(row, 0)
        doc_id = (
            coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole)) if it is not None else None
        )
        m.addSeparator()
        act_copy = m.addAction("Copy row", partial(copy_table_row_as_tsv, self, row))
        act_copy.setToolTip(
            "Copy this inbox row as tab-separated text for pasting into a spreadsheet or editor. "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        m.addSeparator()
        act_delete = m.addAction("🗑  Delete document…")
        act_delete.setToolTip(
            "Permanently delete this document and its extraction data from the company file. "
            "The original file on disk is NOT removed. Use File → Backup first if unsure."
        )
        if doc_id is None:
            act_delete.setEnabled(False)
        chosen = m.exec(self.viewport().mapToGlobal(pos))
        if chosen == act_delete and doc_id is not None:
            self.deleteRequested.emit(doc_id)

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
        self._f_date.setPlaceholderText("MM/DD/YYYY")
        self._f_date.setToolTip(
            "Document date: type flexibly (e.g. 5/21/26, 05.21.26, 052126); "
            "normalized to MM/DD/YYYY on commit. Stored as YYYY-MM-DD."
        )
        attach_line_edit_us_date_normalization(self._f_date)
        self._f_due_date = QLineEdit()
        self._f_due_date.setPlaceholderText("MM/DD/YYYY (optional)")
        self._f_due_date.setToolTip(
            "Due or pay-by date if present on the document: type flexibly "
            "(e.g. 5/21/26, 05.21.26, 052126); normalized to MM/DD/YYYY on commit."
        )
        attach_line_edit_us_date_normalization(self._f_due_date)
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
            "doc_date":       (line_edit_to_iso_or_raw(self._f_date) or None),
            "due_date":       (line_edit_to_iso_or_raw(self._f_due_date) or None),
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
        self._f_date.setText(format_iso_to_us_display(row["doc_date"] or ""))
        self._f_due_date.setText(format_iso_to_us_display(row["due_date"] or ""))
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
        self._f_date.setText(format_iso_to_us_display(result.doc_date or ""))
        self._f_due_date.setText(format_iso_to_us_display(result.due_date or ""))
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
    _SETTINGS_ORG = "ProBooksAI"
    _SETTINGS_APP = "ProBooksAI"
    _GEOMETRY_KEY = "mainwindow/geometry"
    _MAXIMIZED_KEY = "mainwindow/maximized"
    _DEFAULT_WIDTH = 1100
    _DEFAULT_HEIGHT = 700

    def __init__(self, db_path: str | None = None):
        super().__init__()
        # Restore last window size/position; default to maximised on first run
        _win_settings = QSettings(self._SETTINGS_ORG, self._SETTINGS_APP)
        _saved_geom = _win_settings.value(self._GEOMETRY_KEY)
        if _saved_geom:
            self.restoreGeometry(_saved_geom)
        else:
            self.showMaximized()

        self._db_path = db_path
        self._db = DocumentDatabase(db_path)
        self._bank_db = BankDatabase(db_path)
        apply_extensions(self._bank_db._conn)
        self._gl_db = GLDatabase(self._bank_db._conn)
        self._coa_db = COADatabase(self._bank_db._conn)
        self._coa_db.seed_from_workbook()
        self._coa = load_coa()
        self._worker: AIWorker | None = None
        # Set True for the duration of ``_switch_company_database`` so any
        # ``showEvent`` fired on an old tab during ``_teardown_main_tabs_for_rebuild``
        # can short-circuit before querying the just-closed ``BankDatabase``.
        self._switching_database = False
        # Ensure COA asset accounts exist in bank_accounts before tabs are built.
        # Heal duplicates first (e.g. phantom account from a COA rename), then sync.
        self._sync_coa_assets_to_bank_accounts()
        self._heal_duplicate_bank_accounts()
        self._deactivate_coa_noise_bank_accounts()
        self._heal_duplicate_opening_balance_entries()
        # Seed bank_transactions for any existing GL opening-balance entries
        self._migrate_opening_balances_to_bank_register()
        # Back-fill AR journal entries for any invoices that don't have one yet
        try:
            backfill_ar_invoice_journals(self._bank_db._conn)
        except Exception:
            pass  # non-fatal — journal entries will be created on next save

        self._build_ui()
        self._refresh_inbox()
        self._update_company_status()
        QTimer.singleShot(0, self._maybe_prompt_first_company_file_setup)

    def _restore_main_window_geometry(self) -> None:
        """Restore size (and position) from last session, or use defaults."""
        settings = QSettings()
        geo = settings.value("main_window/geometry")
        ok = False
        if geo is not None:
            try:
                ok = bool(self.restoreGeometry(geo))
            except (TypeError, AttributeError):
                ok = False
        if not ok:
            self.resize(self._DEFAULT_WIDTH, self._DEFAULT_HEIGHT)

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

    def _build_ar_recon_panel(self, conn) -> "QWidget":
        """AR / Invoices subtab in the Reconcile hub — view Open/Sent invoices, receive payment."""
        from PySide6.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
            QHeaderView, QPushButton, QLabel, QAbstractItemView,
        )
        from PySide6.QtCore import Qt

        outer = QWidget()
        outer.setToolTip("Open and Sent invoices; receive payment here. Status updates automatically when paid.")
        lay = QVBoxLayout(outer)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        banner = QLabel("<b>AR / Invoices</b> — Open and Sent invoices awaiting payment.")
        banner.setTextFormat(Qt.TextFormat.RichText)
        banner.setWordWrap(True)
        banner.setStyleSheet("color:#A0A0B0; font-size:12px;")
        lay.addWidget(banner)

        btn_row = QHBoxLayout()
        btn_refresh = QPushButton("↻ Refresh")
        btn_refresh.setToolTip("Reload the invoice list from the company file.")
        btn_receive = QPushButton("Receive Payment…")
        btn_receive.setToolTip("Go to Customers tab → Receive Payments to post a customer payment against open invoices.")
        btn_row.addWidget(btn_refresh)
        btn_row.addWidget(btn_receive)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        cols = ["Invoice #", "Date", "Customer", "Total", "Balance Due", "Status"]
        tbl = QTableWidget(0, len(cols))
        tbl.setHorizontalHeaderLabels(cols)
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tbl.setAlternatingRowColors(True)
        tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        tbl.setToolTip("Double-click an invoice to open it in the Invoices tab.")
        lay.addWidget(tbl, stretch=1)

        def _reload():
            tbl.setRowCount(0)
            if conn is None:
                return
            try:
                rows = conn.execute(
                    """SELECT i.invoice_number, i.invoice_date, c.name, i.total, i.balance_due, i.status, i.id
                       FROM invoices i
                       LEFT JOIN customers c ON c.id = i.customer_id
                       WHERE i.status IN ('Open','Sent','Unpaid')
                       ORDER BY i.invoice_date DESC, i.id DESC"""
                ).fetchall()
            except Exception:
                return
            for row in rows:
                r = tbl.rowCount()
                tbl.insertRow(r)
                for c_idx, val in enumerate(row[:6]):
                    item = QTableWidgetItem(str(val or ""))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | (
                        Qt.AlignmentFlag.AlignRight if c_idx in (3, 4) else Qt.AlignmentFlag.AlignLeft
                    ))
                    if c_idx == 0:
                        item.setData(Qt.ItemDataRole.UserRole, row[6])  # invoice id
                    tbl.setItem(r, c_idx, item)

        btn_refresh.clicked.connect(_reload)

        def _go_receive():
            try:
                for i in range(self._tabs.count()):
                    if "Customer" in (self._tabs.tabText(i) or ""):
                        self._tabs.setCurrentIndex(i)
                        break
            except Exception:
                pass

        btn_receive.clicked.connect(_go_receive)

        _reload()
        outer._reload_ar = _reload  # attach for external refresh calls
        return outer

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
            "Bank statement files: Reconcile → Bank statements (View → Reconcile, Ctrl+Shift+R). "
            "Back up the company file from File → Backup / probooks backup before bulk deletes or experiments."
        )
        left_layout.addWidget(lbl_inbox)

        self._inbox = InboxWidget()
        self._inbox.filesDropped.connect(self._on_files_dropped)
        self._inbox.itemSelectionChanged.connect(self._on_selection_changed)
        self._inbox.deleteRequested.connect(self._on_delete_document)
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
        self._income_tracker_screen = IncomeTrackerScreen(ap_conn=conn)
        self._bill_tracker_screen = BillTrackerScreen(ap_conn=conn)
        self._invoice_codes_screen = InvoiceCodesScreen(ap_conn=conn, coa_db=self._coa_db)
        self._enter_bills_screen = EnterBillsScreen(ap_conn=conn)
        self._enter_bills_screen.payBillsRequested.connect(self._on_enter_bills_pay_bill)
        self._invoice_screen.set_enter_bills_screen(self._enter_bills_screen)
        self._pay_bills_screen = PayBillsScreen(
            ap_conn=conn, bank_db=self._bank_db
        )
        self._receive_payments_screen = ReceiveChecksScreen(
            ap_conn=conn, bank_db=self._bank_db
        )
        self._make_deposits_screen = MakeDepositsScreen(
            ap_conn=conn, bank_db=self._bank_db
        )
        self._check_screen = CheckScreen(
            bank_db=self._bank_db,
            coa_list=self._coa_db.display_list() if self._coa_db is not None else [],
            ap_conn=conn,
        )
        self._check_screen.transactionSaved.connect(self._on_check_screen_saved)

        self._register_tab = RegisterTab(self._bank_db, self._coa_db, self._gl_db)
        self._bank_tab = BankImportTab(
            self._bank_db,
            self._coa_db,
            register_tab=self._register_tab,
            after_stmt_match_sync=self._focus_bank_register_tab,
            focus_bank_register_tab=self._focus_bank_register_tab_for_handoff,
        )
        self._coa_tab = COATab(self._coa_db, gl_db=self._gl_db)
        self._coa_tab.coaChanged.connect(self._on_coa_changed)
        self._coa_tab.openRegisterRequested.connect(self._on_coa_open_register)

        # AR/AP primary UI: top-level Customers / Vendors (Business hub keeps Rules, Payroll, Tax %).
        self._customers_tab = ARTab(conn)
        self._vendors_tab = APTab(conn)

        # Bank Statement Intake — phase 2: review-first staging plus an
        # explicit "Send to Bank Register" hand-off bound to the chosen bank
        # account. The panel never writes to ``bank_transactions`` on its own;
        # the user confirms a per-send batch first. Persisted queue (table
        # ``bank_statement_intake_queue``) survives restart so review can resume.
        self._statement_intake_panel = BankStatementIntakePanel(
            bank_db=self._bank_db,
        )
        self._statement_intake_panel.rowsSentToRegister.connect(
            self._on_statement_intake_rows_sent
        )
        # Wire the default OpenAI-backed AI provider for bank statement
        # intake categorization. The provider stays silent until both
        # ``ai_intake_enabled`` is on (gated inside the panel) AND an
        # ``openai_api_key`` is configured (gated inside the provider),
        # so this call is safe even on a brand-new company file. When
        # the user switches companies, ``_attach_panel_after_db_switch``
        # re-runs this so the new ``conn`` is what the provider reads.
        self._statement_intake_panel.set_ai_provider(
            build_default_ai_provider(self._bank_db._conn)
        )

        self._reconcile_hub = QTabWidget()
        self._reconcile_hub.setToolTip(
            "Reconcile: bank statement import, AI line reconciliation, and document intake. "
            "Same company .db (File → Backup / Restore, probooks.backup)."
        )
        self._reconcile_hub.addTab(self._bank_tab, "Bank statements")
        self._reconcile_hub.addTab(self._intake_widget, "Documents")
        self._ar_recon_widget = self._build_ar_recon_panel(conn)
        self._reconcile_hub.addTab(self._ar_recon_widget, "AR / Invoices")
        self._reconcile_hub.addTab(
            self._statement_intake_panel, "Statement intake (review)"
        )

        self._reconcile_root = QWidget()
        self._reconcile_root.setToolTip(
            "Reconcile: intake (statements or documents), then review and match against Bank Register. "
            "Same company .db (File → Backup / Restore, probooks.backup)."
        )
        reconcile_root_layout = QVBoxLayout(self._reconcile_root)
        reconcile_root_layout.setContentsMargins(8, 8, 8, 0)
        reconcile_root_layout.setSpacing(6)
        reconcile_banner = QLabel(
            "<b>Reconcile</b> — Bank statements (import/match), Documents (intake), and <b>AR / Invoices</b> (receive payment)."
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
        self._journal_tab = JournalTab(
            conn,
            coa_list=self._coa_db.display_list() if hasattr(self, "_coa_db") else None,
        )
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

        self._tabs.addTab(self._dashboard_tab, "Home")
        self._tabs.addTab(self._income_tracker_screen, "Income Tracker")
        self._tabs.addTab(self._bill_tracker_screen, "Bill Tracker")
        self._tabs.addTab(self._invoice_screen, "Invoices")
        self._tabs.addTab(self._invoice_codes_screen, "Codes")
        self._tabs.addTab(self._check_screen, "Write Checks")
        self._tabs.addTab(self._enter_bills_screen, "Enter Bills")
        self._tabs.addTab(self._pay_bills_screen, "Pay Bills")
        self._tabs.addTab(self._receive_payments_screen, "Receive Payments")
        self._tabs.addTab(self._make_deposits_screen, "Make Deposits")
        self._tabs.addTab(self._register_tab, "Bank Register")
        self._tabs.addTab(self._coa_tab, "Chart of Accounts")
        self._tabs.addTab(self._customers_tab, "Customers")
        self._tabs.addTab(self._vendors_tab, "Vendors")
        self._tabs.addTab(self._reconcile_root, "Reconcile")
        self._tabs.addTab(self._more_hub, "More")
        self._tabs.currentChanged.connect(self._on_main_tab_changing)
        self._prev_main_tab_index: int = 0
        self._make_deposits_screen.depositPosted.connect(self._on_make_deposit_posted)
        self._receive_payments_screen.arPaymentPosted.connect(
            self._on_ar_payment_posted_for_deposits
        )
        self._pay_bills_screen.apPaymentPosted.connect(self._on_pay_bills_posted)
        self._vendors_tab.enterBillsRequested.connect(self._on_vendor_center_enter_bills)
        self._vendors_tab.payBillsRequested.connect(self._on_vendor_center_pay_bills)
        self._vendors_tab.billTrackerRequested.connect(self._on_vendor_center_bill_tracker)
        self._vendors_tab.writeChecksRequested.connect(self._on_vendor_center_write_checks)
        self._vendors_tab.openBillRequested.connect(self._on_vendor_center_open_bill)
        self._vendors_tab.openPaymentRequested.connect(self._on_vendor_center_open_payment)
        self._vendors_tab.vendorRecordsChanged.connect(self._on_vendor_center_records_changed)
        self._customers_tab.createInvoicesRequested.connect(self._on_customer_center_create_invoices)
        self._customers_tab.receivePaymentsRequested.connect(self._on_customer_center_receive_payments)
        self._customers_tab.incomeTrackerRequested.connect(self._on_customer_center_income_tracker)
        self._customers_tab.openInvoiceRequested.connect(self._on_customer_center_open_invoice)
        self._customers_tab.openPaymentRequested.connect(self._on_customer_center_open_payment)
        self._customers_tab.customerRecordsChanged.connect(self._on_customer_center_records_changed)
        self._income_tracker_screen.openInvoiceRequested.connect(
            self._on_customer_center_open_invoice
        )
        self._income_tracker_screen.receivePaymentRequested.connect(
            self._on_income_tracker_receive_payment
        )
        self._income_tracker_screen.openArPaymentRequested.connect(
            self._on_customer_center_open_payment
        )
        self._bill_tracker_screen.openBillRequested.connect(self._on_vendor_center_open_bill)
        self._bill_tracker_screen.payBillRequested.connect(self._on_bill_tracker_pay_bill)
        self._invoice_screen.openInvoicesChanged.connect(self._income_tracker_screen.reload)
        self._receive_payments_screen.arPaymentPosted.connect(
            lambda *_a: self._income_tracker_screen.reload()
        )
        self._pay_bills_screen.apPaymentPosted.connect(
            lambda *_a: self._bill_tracker_screen.reload()
        )

    def _on_main_tab_changing(self, new_index: int) -> None:
        """Guard switching away from a screen that has unsaved invoice changes."""
        old_index = self._prev_main_tab_index
        if old_index == new_index:
            return
        old_widget = self._tabs.widget(old_index)
        is_dirty = getattr(old_widget, "_is_form_dirty", None)
        confirm_leave = getattr(old_widget, "_confirm_leave_loaded_invoice", None)
        if (
            isinstance(old_widget, InvoiceScreen)
            and callable(is_dirty)
            and callable(confirm_leave)
            and is_dirty()
        ):
            # Switch back before showing the dialog so the form is visible
            self._tabs.blockSignals(True)
            self._tabs.setCurrentIndex(old_index)
            self._tabs.blockSignals(False)
            if not confirm_leave():
                # User chose Stay — stay on the invoice screen
                return
            # User saved or discarded — proceed to the requested tab
            self._tabs.blockSignals(True)
            self._tabs.setCurrentIndex(new_index)
            self._tabs.blockSignals(False)
        self._prev_main_tab_index = new_index
        md = getattr(self, "_make_deposits_screen", None)
        if md is not None and self._tabs.widget(new_index) is md:
            md.on_activated()

        self._invoice_screen.customerRecordsChanged.connect(self._customers_tab._refresh)
        self._invoice_screen.customerRecordsChanged.connect(
            self._receive_payments_screen._load_invoices_from_db
        )
        self._invoice_screen.openInvoicesChanged.connect(
            self._receive_payments_screen._load_invoices_from_db
        )
        self._invoice_screen.openInvoicesChanged.connect(self._customers_tab._refresh)
        self._receive_payments_screen.arPaymentPosted.connect(self._customers_tab._refresh)
        self._invoice_codes_screen.codesChanged.connect(
            self._invoice_screen.refresh_invoice_item_codes
        )
        # Receive Payments → Manual Invoice: live PAID badge / balance refresh for the
        # currently open invoice when its row id is in the just-posted batch.
        self._receive_payments_screen.arPaymentPosted.connect(
            self._invoice_screen.refresh_loaded_invoice_payment_status
        )

    def _apply_main_tab_bar_tooltips(self) -> None:
        main_tab_bar = self._tabs.tabBar()
        _main_tab_bar_db_hint = " Same company .db (File → Backup / Restore, probooks.backup)."
        _tab_bar_csv_excel_hint = " CSV: UTF-8 with BOM for Excel."
        tips = [
            (
                "Home: company overview with money-in / money-out shortcuts "
                "(Create Invoices, Receive Payments, Income Tracker, Enter Bills, Pay Bills, Bill Tracker, Write Checks, Make Deposits)."
                + _main_tab_bar_db_hint
            ),
            (
                "Income Tracker: unbilled time & expenses, open and overdue invoices, "
                "and payments in the last 30 days. Double-click an invoice to open Create Invoices."
                + _main_tab_bar_db_hint
            ),
            (
                "Bill Tracker: open bills, overdue bills, and vendor payments in the last 30 days. "
                "Double-click a bill to open Enter Bills; Pay Bill opens Pay Bills."
                + _main_tab_bar_db_hint
            ),
            (
                "Invoices: invoice entry workflow (line items, Bill To, print/PDF when connected). "
                + _main_tab_bar_db_hint
            ),
            (
                "Codes: Item List of services, discounts, other charges, and subtotals. "
                "Double-click a row to Edit Item. Saved items fill Create Invoices line Codes."
                + _main_tab_bar_db_hint
            ),
            (
                "Write Checks: record and print checks against a bank account."
                + _main_tab_bar_db_hint
            ),
            (
                "Enter Bills: bill header and expense lines (vendor-backed when connected)."
                + _main_tab_bar_db_hint
            ),
            (
                "Pay Bills: unpaid vendor bills, Pay From account, Pay Selected Bills (BILLPMT register)."
                + _main_tab_bar_db_hint
            ),
            (
                "Receive Payments: customer payments against open invoices (Undeposited Funds)."
                + _main_tab_bar_db_hint
            ),
            (
                "Make Deposits: pick undeposited payments and post them into a bank account "
                "(Payments to Deposit popup)."
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
                "Customers: Customer Center — list, jobs, Customer Information, invoices and payments (F5). "
                "New Customer & Job, New Transactions (Create Invoices / Receive Payments), Excel CSV. "
                "Invoices and payments use Invoices, Receive Payments, and Reports (Business hub holds Rules, Payroll, Tax % only)."
                + _tab_bar_csv_excel_hint
                + _main_tab_bar_db_hint
            ),
            (
                "Vendors: Vendor Center — list, Vendor Information, bills and payments (F5). "
                "New Vendor, New Transactions (Enter Bills / Pay Bills / Write Checks), Excel CSV. "
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
        """Remove main tabs and dispose widgets except the shared Document Intake root widget.

        No explicit signal disconnect is needed: ``RegisterTab`` is destroyed
        below via ``deleteLater`` and Qt drops its signal connections on
        destruction. A previous defensive ``reconciliationModeChanged.disconnect()``
        call was removed because the signal has no external slots wired in
        ``main.py`` — calling ``disconnect()`` with nothing connected produces
        a ``RuntimeWarning`` in PySide6, which only added noise.
        """
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
                # Detach from the QTabWidget hierarchy *before* deleteLater so
                # the next ``removeTab(0)`` cannot mark this widget visible and
                # fire a stray ``showEvent`` against a now-closed DB connection
                # (see ``RegisterTab._is_db_alive``).
                w.setParent(None)
                w.deleteLater()

    # -- UI construction -----------------------------------------------------

    def _build_ui(self):
        self._build_menu_bar()

        # Container: header banner + tab widget
        container = QWidget()
        container.setToolTip(
            "Main workspace: fixed-order tabs (Home, Income Tracker, Bill Tracker, Invoices through More). "
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
            "Main workspace: Home, Income Tracker, Bill Tracker, Invoices, Codes, Write Checks, Enter Bills, Pay Bills, Receive Payments, "
            "Make Deposits, Bank Register, Chart of Accounts, Customers, Vendors, Reconcile, and More "
            "(hover each tab). File → Backup / Restore applies to the whole company database "
            "(CLI: probooks backup / restore)."
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
                "Reconcile → Bank statements (Ctrl+Shift+R); File → Backup saves the company .db."
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

        act_create_company_file = QAction("&New Company\u2026", self)
        _menu_action_tip(
            act_create_company_file,
            "New Company: guided setup wizard. Captures company name, address, phone, email, "
            "business type, tax structure, and tax ID; then creates the working .db plus a "
            "backup folder next to it. Each company is fully isolated in its own SQLite file. "
            "Use File → Backup before replacing data you care about.",
        )
        act_create_company_file.triggered.connect(self._on_create_company_file)
        file_menu.addAction(act_create_company_file)

        act_open_company = QAction("&Switch company\u2026", self)
        act_open_company.setShortcut("Ctrl+Shift+O")
        _menu_action_tip(
            act_open_company,
            "Switch to a different company file (Ctrl+Shift+O). "
            "Each company is its own SQLite database; data does not cross between companies. "
            "File → Backup copies the active .db first (same engine as probooks backup).",
        )
        act_open_company.triggered.connect(self._on_open_company_database)
        file_menu.addAction(act_open_company)

        act_company_info = QAction("Compan&y info\u2026", self)
        _menu_action_tip(
            act_company_info,
            "Edit identity for the open company: name, address, phone, email, business type, "
            "tax structure, and tax ID. Saves into the same fields the New Company wizard captures; "
            "values feed invoices and reports. Use File → Backup first if you want a snapshot.",
        )
        act_company_info.triggered.connect(self._on_company_info)
        file_menu.addAction(act_company_info)

        file_menu.addSeparator()

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
        # Tab indices: 0=Home, 1=Income Tracker, 2=Bill Tracker, 3=Invoices, 4=Codes,
        #              5=Write Checks, 6=Enter Bills, 7=Pay Bills, 8=Receive Payments,
        #              9=Make Deposits, 10=Bank Register, 11=Chart of Accounts,
        #              12=Customers, 13=Vendors, 14=Reconcile, 15=More
        _view_tab_tip_extra = {
            1: " Income Tracker: open/overdue invoices and recent payments.",
            2: " Bill Tracker: open/overdue bills and recent vendor payments.",
            3: " Invoice entry workflow.",
            4: " Item List: service/discount/other charge items for invoice lines (double-click to Edit Item).",
            5: " Write Checks: record and print checks against a bank account.",
            6: " Enter Bills screen.",
            7: " Pay Bills screen.",
            8: " Receive Payments screen.",
            9: " Make Deposits: undeposited payments into a bank account.",
            10: " Bank Register: Match overlay (Bank Import can populate).",
            11: " Chart of Accounts editor.",
            12: " AR: customers, invoices, payments (primary route; Business hub is Rules/Payroll/Tax %).",
            13: " AP: vendors, bills, payments (primary route; Business hub is Rules/Payroll/Tax %).",
            14: " Reconcile: Bank statements + Documents (intake → review/match).",
            15: " Reports, Journal, Business, Audit log.",
        }
        for tab_idx, (sc, label) in [
            (3, ("Ctrl+1", "&Invoices")),
            (4, ("Ctrl+2", "&Codes")),
            (5, ("Ctrl+3", "&Write Checks")),
            (6, ("Ctrl+4", "&Enter Bills")),
            (7, ("Ctrl+5", "&Pay Bills")),
            (8, ("Ctrl+6", "&Receive Payments")),
            (9, ("Ctrl+Shift+D", "Make &Deposits")),
            (10, ("Ctrl+7", "&Bank Register")),
            (11, ("Ctrl+8", "Chart of &Accounts")),
            (12, ("Ctrl+9", "&Customers")),
            (13, ("Ctrl+0", "&Vendors")),
            (14, ("Ctrl+Shift+R", "&Reconcile")),
            (15, ("Ctrl+Shift+M", "&More")),
            (1, ("Ctrl+Shift+T", "Income &Tracker")),
            (2, ("Ctrl+Alt+B", "&Bill Tracker")),
        ]:
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

        view_menu.addSeparator()
        m_more_reports = view_menu.addMenu("More &reports")
        _menu_action_tip(
            m_more_reports,
            "Jump to **More** → **Reports** and run receivables/payables views. "
            "Same data as the Reports tab; **Export CSV…** there saves the last grid you ran. "
            "Bank Register stays the source of truth for bank activity; these read AR/AP tables in the company file."
            + _view_tab_tip_suffix,
        )
        for label, kind, tip in (
            ("&A/R aging", "ar_aging", "Open invoice balances by aging bucket (as-of: End date or today)."),
            ("A/&P aging", "ap_aging", "Open bill balances by aging bucket."),
            ("&Open invoices", "open_inv", "Invoices with balance due."),
            ("Open &bills", "open_bill", "Bills with balance due."),
            ("Recent &customer payments", "ar_pay", "Customer payment records (newest 100)."),
            ("Recent &vendor payments", "ap_pay", "Vendor payment records (newest 100)."),
        ):
            act_mr = QAction(label, self)
            _menu_action_tip(act_mr, tip + _view_tab_tip_suffix)
            act_mr.triggered.connect(partial(self._focus_more_report, kind))
            m_more_reports.addAction(act_mr)

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

        act_set_logo = QAction("Set Company &Logo\u2026", self)
        _menu_action_tip(
            act_set_logo,
            "Choose a PNG or JPEG logo image to display on printed and saved invoices. "
            "The path is stored in the open company file.",
        )
        act_set_logo.triggered.connect(self._on_set_company_logo)
        edit_menu.addAction(act_set_logo)

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

    def _on_delete_document(self, doc_id: int) -> None:
        """Confirm and permanently delete a document from the inbox."""
        if not hasattr(self, "_db") or self._db is None:
            return
        row = self._db.get_document(doc_id)
        if row is None:
            return
        filename = (dict(row).get("filename") or f"document #{doc_id}")
        confirmed = message_box_question_yes_no(
            self,
            "Delete Document",
            f"Permanently delete <b>{escape_ampersand_for_qt(filename)}</b> and all its "
            f"extraction data from the company file?<br><br>"
            "The original file on disk is <b>not</b> removed. "
            "Use <b>File → Backup</b> first if unsure.",
            yes_tip="Delete this document and its extraction data permanently.",
            no_tip="Cancel — keep the document.",
        )
        if not confirmed:
            return
        try:
            self._db.delete_document(doc_id)
        except Exception as exc:
            message_box_critical_ok(
                self, "Delete failed",
                f"Could not delete document: {exc}",
                ok_tip="Close; try File → Backup then retry.",
            )
            return
        self._detail.clear_view()
        self._refresh_inbox()
        self._status_bar.showMessage(f"Deleted document: {filename}")

    def _sync_coa_assets_to_bank_accounts(self) -> None:
        """
        Keep existing bank_accounts rows in sync with the COA when accounts are renamed.

        Matching priority (prevents phantom duplicate accounts on rename):
          1. gl_display_account exact match — already in sync, skip.
          2. account_number match — COA was renamed; UPDATE the existing bank_account
             name + gl_display_account in place so all transactions remain attached.
          3. name match — manually-created bank account, skip.
          4. No match — intentionally not auto-creating.  Bank accounts are created
             explicitly by the user via Manage Accounts.  Auto-creating entries for
             every COA asset (Equipment, Receivables, etc.) pollutes the dropdown.

        This means renaming "1000 Cash – Checking" to "Operating Checking" updates the single
        existing bank_accounts row rather than creating an empty duplicate.
        """
        try:
            coa_rows = self._coa_db.list_accounts(include_inactive=False)
            conn = self._bank_db._conn

            # Build lookup structures — all keyed to bank_account_id
            by_gl_key: dict[str, int] = {}   # gl_display_account → bank_account_id
            by_acct_num: dict[str, int] = {} # account_number     → bank_account_id
            by_name: dict[str, int] = {}     # name               → bank_account_id

            for ba in self._bank_db.list_bank_accounts(include_inactive=True):
                ba_id = int(ba["id"])
                gl = (ba["gl_display_account"] or "").strip()
                if gl:
                    by_gl_key[gl] = ba_id
                num = (ba["account_number"] or "").strip()
                if num:
                    by_acct_num.setdefault(num, ba_id)  # first match wins
                nm = (ba["name"] or "").strip()
                if nm:
                    by_name.setdefault(nm, ba_id)

            for row in coa_rows:
                atype = (row["account_type"] or "").lower()
                if atype != "asset":
                    continue
                num  = str(row["account_number"] or "").strip()
                name = str(row["account_name"] or "").strip()
                if not name:
                    continue
                display_key = f"{num} {name}".strip() if num else name
                sub = str(row["sub_type"] if "sub_type" in row.keys() else "").strip()

                # 1. Already perfectly in sync
                if display_key in by_gl_key:
                    continue

                # 2. Same account number → COA was renamed; UPDATE the existing row
                if num and num in by_acct_num:
                    ba_id = by_acct_num[num]
                    conn.execute(
                        "UPDATE bank_accounts SET name = ?, gl_display_account = ?, "
                        "updated_at = datetime('now') WHERE id = ?",
                        (name, display_key, ba_id),
                    )
                    conn.commit()
                    by_gl_key[display_key] = ba_id   # keep lookup fresh
                    continue

                # 3. Name match — manually-created bank account, leave it alone
                if name in by_name or display_key in by_name:
                    continue

                # 4. No match — do NOT auto-create a bank_account row for every
                #    COA asset.  Equipment, Receivables, Fixed Assets etc. are not
                #    bank accounts.  The user creates bank accounts explicitly via
                #    Manage Accounts.  (This case intentionally left empty.)

        except Exception:
            import traceback
            traceback.print_exc()  # visible in console; never blocks a COA save

    def _heal_duplicate_bank_accounts(self) -> None:
        """
        One-time (and idempotent) cleanup: when a COA rename previously created a
        phantom empty bank_account alongside the original, consolidate them.

        Heuristic: for each account_number that appears on multiple bank_accounts rows,
        the row with the most transactions is the "canonical" one.  All transactions
        on the others are re-pointed to the canonical row, the duplicates are then
        deactivated (not deleted, to preserve audit trail), and the canonical row's
        name/gl_display_account are updated to match the current COA account name.
        """
        try:
            conn = self._bank_db._conn

            # Find account_numbers that appear on more than one bank_accounts row
            dupes = conn.execute("""
                SELECT account_number, COUNT(*) AS cnt
                FROM bank_accounts
                WHERE account_number != '' AND account_number IS NOT NULL
                GROUP BY account_number
                HAVING cnt > 1
            """).fetchall()

            if not dupes:
                return

            # Build current COA display_key map: account_number → display_key, name
            coa_map: dict[str, tuple[str, str]] = {}
            for row in self._coa_db.list_accounts(include_inactive=False):
                num = str(row["account_number"] or "").strip()
                nm  = str(row["account_name"] or "").strip()
                if num and nm:
                    coa_map[num] = (f"{num} {nm}".strip(), nm)

            for dupe_row in dupes:
                acct_num = str(dupe_row["account_number"] or "").strip()
                if not acct_num:
                    continue

                # All bank_accounts rows for this number, sorted: most transactions first
                rows = conn.execute("""
                    SELECT ba.id,
                           ba.name,
                           ba.gl_display_account,
                           ba.is_active,
                           COUNT(bt.id) AS txn_count
                    FROM bank_accounts ba
                    LEFT JOIN bank_transactions bt ON bt.bank_account_id = ba.id
                    WHERE ba.account_number = ?
                    GROUP BY ba.id
                    ORDER BY txn_count DESC, ba.id ASC
                """, (acct_num,)).fetchall()

                if len(rows) < 2:
                    continue

                canonical_id = int(rows[0]["id"])

                # Point every transaction from the duplicate rows to the canonical row
                for dup in rows[1:]:
                    dup_id = int(dup["id"])
                    # Re-point transactions (fingerprint may clash — skip on conflict)
                    conn.execute("""
                        UPDATE OR IGNORE bank_transactions
                        SET bank_account_id = ?
                        WHERE bank_account_id = ?
                    """, (canonical_id, dup_id))
                    # Re-point import batches
                    conn.execute("""
                        UPDATE bank_import_batches
                        SET bank_account_id = ?
                        WHERE bank_account_id = ?
                    """, (canonical_id, dup_id))
                    # Deactivate (not delete) the empty duplicate
                    conn.execute(
                        "UPDATE bank_accounts SET is_active = 0, updated_at = datetime('now') "
                        "WHERE id = ?",
                        (dup_id,),
                    )

                # Update the canonical row to reflect the current COA name and
                # always reactivate it — it is the surviving account and must be
                # visible in dropdowns even if it was previously soft-deactivated.
                if acct_num in coa_map:
                    new_display, new_name = coa_map[acct_num]
                    conn.execute(
                        "UPDATE bank_accounts SET name = ?, gl_display_account = ?, "
                        "is_active = 1, updated_at = datetime('now') WHERE id = ?",
                        (new_name, new_display, canonical_id),
                    )
                else:
                    # No COA entry — still reactivate so it isn't lost
                    conn.execute(
                        "UPDATE bank_accounts SET is_active = 1, "
                        "updated_at = datetime('now') WHERE id = ?",
                        (canonical_id,),
                    )

                conn.commit()

        except Exception:
            import traceback
            traceback.print_exc()

    def _deactivate_coa_noise_bank_accounts(self) -> None:
        """
        Deactivate bank_account rows that were created by a previous version of
        ``_sync_coa_assets_to_bank_accounts`` for non-bank GL accounts (Equipment,
        Accounts Receivable, Fixed Assets, etc.) that have zero transactions and
        zero import batches.

        Safe to call multiple times; idempotent.  Leaves any account with even one
        transaction or batch intact regardless of type.
        """
        try:
            conn = self._bank_db._conn
            # Find accounts with no transactions and no batches whose account_number
            # suggests a non-cash GL account (numbers >= 1100 are generally not banks)
            noise = conn.execute("""
                SELECT ba.id
                FROM bank_accounts ba
                WHERE ba.is_active = 1
                  AND (ba.account_number IS NOT NULL AND ba.account_number != '')
                  AND CAST(ba.account_number AS INTEGER) >= 1100
                  AND NOT EXISTS (
                      SELECT 1 FROM bank_transactions bt WHERE bt.bank_account_id = ba.id
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM bank_import_batches bib WHERE bib.bank_account_id = ba.id
                  )
            """).fetchall()
            if not noise:
                return
            ids = [int(r["id"]) for r in noise]
            conn.execute(
                "UPDATE bank_accounts SET is_active = 0, updated_at = datetime('now') "
                f"WHERE id IN ({','.join('?' * len(ids))})",
                ids,
            )
            conn.commit()
        except Exception:
            import traceback
            traceback.print_exc()

    def _heal_duplicate_opening_balance_entries(self) -> None:
        """
        If the Opening Balance Wizard was run more than once before the dedup fix,
        multiple journal_entries rows with source='opening_balance' may exist.
        Keep only the most recent one (highest id) and delete the rest, including
        any bank_transactions that were seeded for the discarded entries.
        """
        try:
            conn = self._bank_db._conn
            rows = conn.execute(
                "SELECT id FROM journal_entries WHERE source = 'opening_balance' ORDER BY id DESC"
            ).fetchall()
            if len(rows) <= 1:
                return  # nothing to heal
            # Keep the latest; delete the rest
            keep_id = int(rows[0]["id"])
            stale_ids = [int(r["id"]) for r in rows[1:]]
            # Wipe ALL opening-balance bank transactions — migrate re-seeds from the
            # surviving entry, so no data is permanently lost.
            conn.execute(
                "DELETE FROM bank_transactions "
                "WHERE description LIKE 'Opening balance as of %' "
                "AND batch_id IN ("
                "  SELECT id FROM bank_import_batches "
                "  WHERE filename = '(Opening Balance)'"
                ")"
            )
            # Delete stale journal entries (lines cascade-delete)
            for stale_id in stale_ids:
                conn.execute("DELETE FROM journal_entries WHERE id = ?", (stale_id,))
            conn.commit()
        except Exception:
            import traceback
            traceback.print_exc()

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
        # Sync COA asset accounts → bank_accounts; heal any duplicates from a rename
        self._sync_coa_assets_to_bank_accounts()
        self._heal_duplicate_bank_accounts()
        # Refresh the dropdown list used in the document intake detail pane
        self._coa = load_coa()
        coa_display = self._coa_db.display_list()
        self._detail.update_coa(coa_display)
        self._register_tab.refresh_coa_choices()
        self._register_tab.refresh_bank_accounts()
        if hasattr(self, "_asset_register_tab"):
            self._asset_register_tab.update_coa_list(coa_display)
        if hasattr(self, "_check_screen"):
            self._check_screen.refresh_coa(coa_display)
            self._check_screen.refresh_payees()
        if hasattr(self, "_journal_tab"):
            self._journal_tab.refresh_coa(self._coa_db.display_list())
        if hasattr(self, "_invoice_codes_screen"):
            self._invoice_codes_screen.refresh_coa_combos()
        if hasattr(self, "_enter_bills_screen"):
            self._enter_bills_screen.refresh_lookups()

    def _on_dashboard_navigate(self, target: str) -> None:
        """Home workflow shortcuts → jump to the requested existing screen."""
        if not hasattr(self, "_tabs"):
            return
        if target == "register":
            self._open_use_register_dialog()
            return
        target_map = {
            "invoices": getattr(self, "_invoice_screen", None),
            "income_tracker": getattr(self, "_income_tracker_screen", None),
            "bill_tracker": getattr(self, "_bill_tracker_screen", None),
            "bills": getattr(self, "_enter_bills_screen", None),
            "pay_bills": getattr(self, "_pay_bills_screen", None),
            "payments": getattr(self, "_receive_payments_screen", None),
            "deposits": getattr(self, "_make_deposits_screen", None),
            "checks": getattr(self, "_check_screen", None),
            "register": getattr(self, "_register_tab", None),
            "reconcile": getattr(self, "_reconcile_root", None),
            "coa": getattr(self, "_coa_tab", None),
            "codes": getattr(self, "_invoice_codes_screen", None),
        }
        widget = target_map.get(target)
        if widget is not None:
            idx = self._tabs.indexOf(widget)
            if idx >= 0:
                self._tabs.setCurrentIndex(idx)

    def _on_enter_bills_pay_bill(self) -> None:
        """Enter Bills ribbon **Pay Bill** → Pay Bills tab."""
        if not hasattr(self, "_tabs") or not hasattr(self, "_pay_bills_screen"):
            return
        self._pay_bills_screen.reload()
        idx = self._tabs.indexOf(self._pay_bills_screen)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)

    def _on_vendor_center_enter_bills(self, vendor_id: int) -> None:
        if not hasattr(self, "_tabs") or not hasattr(self, "_enter_bills_screen"):
            return
        if vendor_id:
            self._enter_bills_screen.prepare_new_bill_for_vendor(int(vendor_id))
        idx = self._tabs.indexOf(self._enter_bills_screen)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)

    def _on_vendor_center_pay_bills(self, vendor_id: int) -> None:
        if not hasattr(self, "_tabs") or not hasattr(self, "_pay_bills_screen"):
            return
        self._pay_bills_screen.reload()
        if vendor_id:
            self._pay_bills_screen.filter_to_vendor(int(vendor_id))
        idx = self._tabs.indexOf(self._pay_bills_screen)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)

    def _on_vendor_center_bill_tracker(self, vendor_id: int) -> None:
        if not hasattr(self, "_tabs") or not hasattr(self, "_bill_tracker_screen"):
            return
        self._bill_tracker_screen.reload()
        if vendor_id:
            self._bill_tracker_screen.filter_to_vendor(int(vendor_id))
        idx = self._tabs.indexOf(self._bill_tracker_screen)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)

    def _on_bill_tracker_pay_bill(self, bill_id: int) -> None:
        if not hasattr(self, "_tabs") or not hasattr(self, "_pay_bills_screen"):
            return
        self._pay_bills_screen.reload()
        if bill_id:
            self._pay_bills_screen.select_bill_by_id(int(bill_id))
        idx = self._tabs.indexOf(self._pay_bills_screen)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)

    def _on_vendor_center_write_checks(self, vendor_id: int) -> None:
        if not hasattr(self, "_tabs") or not hasattr(self, "_check_screen"):
            return
        if vendor_id:
            self._check_screen.select_payee_vendor(int(vendor_id))
        idx = self._tabs.indexOf(self._check_screen)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)

    def _on_vendor_center_open_bill(self, bill_id: int) -> None:
        if not hasattr(self, "_tabs") or not hasattr(self, "_enter_bills_screen"):
            return
        idx = self._tabs.indexOf(self._enter_bills_screen)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)
        self._enter_bills_screen.open_bill_by_id(int(bill_id))

    def _on_vendor_center_open_payment(self, payment_id: int) -> None:
        """BILLPMT row → same AP payment summary hook as the bank register Match link."""
        self._navigate_register_bank_match_link("ap_payment", int(payment_id))

    def _on_vendor_center_records_changed(self) -> None:
        if hasattr(self, "_enter_bills_screen"):
            try:
                self._enter_bills_screen.refresh_vendors()
            except Exception:
                pass
        chk = getattr(self, "_check_screen", None)
        if chk is not None:
            try:
                chk.refresh_payees()
            except Exception:
                pass
        if hasattr(self, "_pay_bills_screen"):
            try:
                self._pay_bills_screen.reload()
            except Exception:
                pass
        if hasattr(self, "_bill_tracker_screen"):
            try:
                self._bill_tracker_screen.reload()
            except Exception:
                pass

    def _on_customer_center_create_invoices(self, customer_id: int) -> None:
        if not hasattr(self, "_tabs") or not hasattr(self, "_invoice_screen"):
            return
        if customer_id:
            self._invoice_screen.prepare_new_invoice_for_customer(int(customer_id))
        idx = self._tabs.indexOf(self._invoice_screen)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)

    def _on_customer_center_receive_payments(self, customer_id: int) -> None:
        if not hasattr(self, "_tabs") or not hasattr(self, "_receive_payments_screen"):
            return
        try:
            self._receive_payments_screen._load_invoices_from_db()
        except Exception:
            pass
        if customer_id:
            self._receive_payments_screen.select_customer_by_id(int(customer_id))
        idx = self._tabs.indexOf(self._receive_payments_screen)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)

    def _on_customer_center_income_tracker(self, customer_id: int) -> None:
        if not hasattr(self, "_tabs") or not hasattr(self, "_income_tracker_screen"):
            return
        self._income_tracker_screen.reload()
        if customer_id:
            self._income_tracker_screen.filter_to_customer(int(customer_id))
        idx = self._tabs.indexOf(self._income_tracker_screen)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)

    def _on_income_tracker_receive_payment(self, invoice_id: int) -> None:
        """Invoice ACTION Receive Payment → Receive Payments with that invoice checked."""
        if not hasattr(self, "_tabs") or not hasattr(self, "_receive_payments_screen"):
            return
        try:
            self._receive_payments_screen.select_invoice_for_payment(int(invoice_id))
        except Exception:
            pass
        idx = self._tabs.indexOf(self._receive_payments_screen)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)

    def _on_customer_center_open_invoice(self, invoice_id: int) -> None:
        if not hasattr(self, "_tabs") or not hasattr(self, "_invoice_screen"):
            return
        idx = self._tabs.indexOf(self._invoice_screen)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)
        self._invoice_screen.open_invoice_by_id(int(invoice_id))

    def _on_customer_center_open_payment(self, payment_id: int) -> None:
        """Payment row → Receive Payments for that customer (same company file)."""
        if not hasattr(self, "_tabs") or not hasattr(self, "_receive_payments_screen"):
            return
        conn = getattr(getattr(self, "_bank_db", None), "_conn", None)
        cid = 0
        if conn is not None:
            try:
                row = conn.execute(
                    "SELECT customer_id FROM ar_payments WHERE id = ?",
                    (int(payment_id),),
                ).fetchone()
            except Exception:
                row = None
            if row is not None:
                cid = int(row["customer_id"] or 0)
        try:
            self._receive_payments_screen._load_invoices_from_db()
        except Exception:
            pass
        if cid:
            self._receive_payments_screen.select_customer_by_id(cid)
        idx = self._tabs.indexOf(self._receive_payments_screen)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)

    def _on_customer_center_records_changed(self) -> None:
        inv = getattr(self, "_invoice_screen", None)
        if inv is not None:
            try:
                inv._bill_customer_panel.reload_customers()
            except Exception:
                pass
        pay = getattr(self, "_receive_payments_screen", None)
        if pay is not None:
            try:
                pay._load_invoices_from_db()
            except Exception:
                pass
        if hasattr(self, "_income_tracker_screen"):
            try:
                self._income_tracker_screen.reload()
            except Exception:
                pass

    def _on_pay_bills_posted(self) -> None:
        """Pay Bills posted: refresh Bank Register and Write Checks balances."""
        if hasattr(self, "_register_tab"):
            try:
                self._register_tab._reload_current()
            except Exception:
                pass
        chk = getattr(self, "_check_screen", None)
        if chk is not None:
            try:
                chk.reload()
            except Exception:
                pass
        vt = getattr(self, "_vendors_tab", None)
        if vt is not None:
            try:
                vt._refresh()
            except Exception:
                pass
        if hasattr(self, "_bill_tracker_screen"):
            try:
                self._bill_tracker_screen.reload()
            except Exception:
                pass

    def _on_ar_payment_posted_for_deposits(self, _invoice_ids=None) -> None:
        """Receive Payments posted: refresh Make Deposits bank list / undeposited picker."""
        screen = getattr(self, "_make_deposits_screen", None)
        if screen is not None:
            screen.reload_undeposited()

    def _on_make_deposit_posted(self) -> None:
        """Make Deposits posted: refresh Bank Register if it is built."""
        if hasattr(self, "_register_tab"):
            try:
                self._register_tab._reload_current()
            except Exception:
                pass

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

    def open_invoice_by_number(self, invoice_number: str) -> bool:
        """Focus the Invoices tab and load Manual Invoice for *invoice_number* (live company DB)."""
        if not hasattr(self, "_tabs") or not hasattr(self, "_invoice_screen"):
            return False
        idx = self._tabs.indexOf(self._invoice_screen)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)
        return self._invoice_screen.open_invoice_by_number(invoice_number)

    def open_bill_by_vendor_invoice_number(
        self,
        vendor_invoice_number: str,
        *,
        vendor_id: int | None = None,
    ) -> bool:
        """Focus Enter Bills and load a bill by vendor invoice / reference (live company DB)."""
        if not hasattr(self, "_tabs") or not hasattr(self, "_enter_bills_screen"):
            return False
        idx = self._tabs.indexOf(self._enter_bills_screen)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)
        return self._enter_bills_screen.open_bill_by_vendor_invoice_number(
            vendor_invoice_number,
            vendor_id=vendor_id,
        )

    def _set_main_tab_index(self, index: int) -> None:
        if not hasattr(self, "_tabs"):
            return
        if index < 0 or index >= self._tabs.count():
            return
        self._tabs.setCurrentIndex(index)

    def _on_check_screen_saved(self) -> None:
        """Called when CheckScreen saves or deletes a transaction; reload the Bank Register."""
        if hasattr(self, "_register_tab"):
            self._register_tab._reload_current()

    def _focus_more_report(self, kind: str) -> None:
        """View → More reports: show **More** → **Reports** and run an A/R or A/P report."""
        tabs = getattr(self, "_tabs", None)
        hub = getattr(self, "_more_hub", None)
        rt = getattr(self, "_reports_tab", None)
        if tabs is None or hub is None or rt is None:
            return
        idx = tabs.indexOf(hub)
        if idx >= 0:
            tabs.setCurrentIndex(idx)
        hub.setCurrentWidget(rt)
        rt.activate_report(kind)

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

    def _focus_bank_register_tab_for_handoff(self) -> None:
        """Switch to **Bank Register** for Reconcile → Open in Bank Register (no Match-overlay status message)."""
        if not hasattr(self, "_tabs") or not hasattr(self, "_register_tab"):
            return
        idx = self._tabs.indexOf(self._register_tab)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)

    def _on_statement_intake_rows_sent(self, inserted: int) -> None:
        """Phase-2 hand-off: refresh Bank Register so newly-posted rows appear immediately.

        Triggered by :attr:`BankStatementIntakePanel.rowsSentToRegister` after
        the user confirms a send. We ask the register tab to reload the current
        account view so the user can see the new rows without flipping tabs.
        Status bar notes the count so the action is auditable in passing.
        """
        if not hasattr(self, "_register_tab"):
            return
        try:
            self._register_tab._reload_current()
        except Exception:
            pass
        if hasattr(self, "_status_bar"):
            self._status_bar.showMessage(
                f"Statement intake \u2192 Bank Register: posted {inserted} "
                f"row{'s' if inserted != 1 else ''}.",
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
        if hasattr(self, "_check_screen"):
            self._register_tab.openInCheckScreenRequested.connect(
                self._open_txn_in_check_screen
            )
        self._register_tab.openInDepositScreenRequested.connect(
            self._open_txn_in_deposit_screen
        )
        self._register_tab.openBankFeedsRequested.connect(self._open_bank_feeds_from_register)
        if hasattr(self, "_coa_tab"):
            self._register_tab.openCoaEditorRequested.connect(
                self._open_coa_from_register_category
            )

    def _open_txn_in_check_screen(self, txn_id: int) -> None:
        """Switch to Write Checks tab and navigate to *txn_id*."""
        if not hasattr(self, "_check_screen") or not hasattr(self, "_tabs"):
            return
        self._check_screen.navigate_to_transaction(txn_id)
        idx = self._tabs.indexOf(self._check_screen)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)

    def _open_txn_in_deposit_screen(self, txn_id: int) -> None:
        """Switch to Make Deposits when a register DEP line is opened."""
        if not hasattr(self, "_make_deposits_screen") or not hasattr(self, "_tabs"):
            return
        idx = self._tabs.indexOf(self._make_deposits_screen)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)

    def _open_bank_feeds_from_register(self) -> None:
        if not hasattr(self, "_reconcile_root") or not hasattr(self, "_tabs"):
            return
        idx = self._tabs.indexOf(self._reconcile_root)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)

    def _open_coa_from_register_category(self, coa_line: str) -> None:
        if not hasattr(self, "_coa_tab") or not hasattr(self, "_tabs"):
            return
        aid = None
        if self._coa_db is not None:
            aid = self._coa_db.find_account_id_by_display_line(coa_line)
        idx = self._tabs.indexOf(self._coa_tab)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)
        if aid is not None:
            self._coa_tab.navigate_to_account_id(int(aid))

    def _bank_account_id_for_coa(self, coa_id: int) -> int | None:
        row = self._coa_db.get_account(int(coa_id)) if self._coa_db is not None else None
        if row is None:
            return None
        num = str(row["account_number"] or "").strip()
        name = str(row["account_name"] or "").strip()
        display = f"{num} {name}".strip()
        dash = f"{num} – {name}".strip()
        for ba in self._bank_db.list_bank_accounts(include_inactive=True):
            aid = int(ba["id"])
            if num and str(ba["account_number"] or "").strip() == num:
                return aid
            gl = str(ba["gl_display_account"] or "").strip()
            if gl in {display, dash, name}:
                return aid
            if str(ba["name"] or "").strip() == name:
                return aid
        if is_bank_like_coa(row):
            try:
                return int(
                    self._bank_db.add_bank_account(
                        name or "Checking",
                        account_number=num,
                        gl_display_account=display,
                    )
                )
            except (ValueError, TypeError):
                return None
        return None

    def _focus_register_for_bank_account(self, bank_account_id: int) -> None:
        if not hasattr(self, "_register_tab") or not hasattr(self, "_tabs"):
            return
        self._register_tab.select_bank_account(int(bank_account_id))
        idx = self._tabs.indexOf(self._register_tab)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)

    def _open_use_register_dialog(self, *, initial_account_id: int | None = None) -> None:
        if not self._bank_db.list_bank_accounts():
            try:
                self._bank_db.add_bank_account("Checking")
            except (ValueError, TypeError):
                pass
            if hasattr(self, "_register_tab"):
                self._register_tab.refresh_bank_accounts()
        dlg = UseRegisterDialog(
            self._bank_db, initial_account_id=initial_account_id, parent=self
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        aid = dlg.selected_bank_account_id()
        if aid is None:
            return
        self._focus_register_for_bank_account(aid)

    def _on_coa_open_register(self, coa_id: int) -> None:
        bank_id = self._bank_account_id_for_coa(int(coa_id))
        if bank_id is not None:
            self._focus_register_for_bank_account(bank_id)
            return
        self._open_use_register_dialog()

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
        from probooksai import business

        p = getattr(self._bank_db, "_db_path", None) or self._db_path or ""
        _sv = application_version()
        self._status_bar.showMessage(
            escape_ampersand_for_qt(
                f"Company: {p}  \u2013  drag & drop or Import; bank CSV/PDF and AI line reconciliation: "
                f"Reconcile → Bank statements (Ctrl+Shift+R); File → Backup copies this .db."
            )
            + f" ProBooks+ai v{_sv}."
        )
        if p:
            display = Path(p).name
            try:
                cn = business.get_setting(self._bank_db._conn, "company_name", "").strip()
                if cn:
                    display = cn
            except (sqlite3.Error, AttributeError, TypeError):
                pass
            self._header.set_company_name(display)
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
        self._heal_duplicate_bank_accounts()
        self._deactivate_coa_noise_bank_accounts()
        self._heal_duplicate_opening_balance_entries()
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
        # Block any showEvent-driven refresh on widgets that still hold a
        # reference to the about-to-close ``BankDatabase`` (the old
        # ``RegisterTab`` is removed inside ``_teardown_main_tabs_for_rebuild``,
        # which is reached via ``_load_company_at_path`` below).
        self._switching_database = True
        try:
            self._db.close()
            self._bank_db.close()
            self._load_company_at_path(resolved)
        finally:
            self._switching_database = False

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

    def _on_set_company_logo(self) -> None:
        """Edit → Set Company Logo: browse for a PNG/JPEG and save its path in company settings."""
        from PySide6.QtWidgets import QFileDialog
        from probooksai import business
        from desktop_app.qt_mnemonic import message_box_information_ok, message_box_warning_ok

        if not hasattr(self, "_bank_db") or self._bank_db is None:
            message_box_warning_ok(self, "No Company Open",
                "Open a company file first (File → Switch company) before setting a logo.")
            return
        conn = self._bank_db._conn
        current = (business.get_setting(conn, "company_logo_path", "") or "").strip()
        start_dir = str(Path(current).parent) if current else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Company Logo Image", start_dir,
            "Image files (*.png *.jpg *.jpeg *.gif *.svg);;All files (*.*)"
        )
        if not path:
            return
        business.set_setting(conn, "company_logo_path", path)
        conn.commit()
        message_box_information_ok(
            self, "Logo Saved",
            f"Company logo set to:\n{path}\n\nIt will appear on the next printed or saved invoice.",
            ok_tip="Close — the logo is now saved in this company file.",
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

    def _maybe_prompt_first_company_file_setup(self) -> None:
        """First-run welcome → routes into **File → New Company…** setup wizard.

        Shows a one-shot welcome card the first time the app is launched without
        any saved company database path. Accepting opens the New Company setup
        wizard via :meth:`_on_create_company_file`; the wizard itself is what
        enforces the required identity fields (Name, Business Type, Tax
        Structure). Returning users (``db_path`` already set, prompt already
        shown) are *not* re-prompted here — they can revisit the wizard from
        File → New Company… at any time, or use
        :meth:`_route_into_setup_if_company_incomplete` directly.
        """
        if self._db_path is not None:
            return
        settings = QSettings()
        if settings.value("company_file_setup_prompted", False, type=bool):
            return
        prev = (settings.value("company_database_path", "", type=str) or "").strip()
        if prev:
            settings.setValue("company_file_setup_prompted", True)
            return
        box = QMessageBox(self)
        box.setWindowTitle("Welcome to ProBooks+ai")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(
            "Let's set up your company. The New Company wizard captures your business name, address, "
            "phone, email, business type, tax structure, and tax ID, then creates the working "
            "company file and a matching backup folder."
        )
        box.setInformativeText(
            "Setup is required before invoices and reports can use your company identity. "
            "You can revisit it anytime from File → New Company…"
        )
        create_btn = box.addButton(
            "New Company…", QMessageBox.ButtonRole.AcceptRole
        )
        box.addButton("Not now", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(create_btn)
        box.exec()
        if box.clickedButton() == create_btn:
            self._on_create_company_file()
        settings.setValue("company_file_setup_prompted", True)

    def _is_current_company_setup_complete(self) -> bool:
        """Return ``True`` when the active company file has identity + business + tax structure saved."""
        conn = getattr(self._bank_db, "_conn", None)
        if conn is None:
            return False
        try:
            return is_company_setup_complete(conn)
        except sqlite3.Error:
            return False

    def _route_into_setup_if_company_incomplete(self) -> None:
        """Open the New Company wizard when the loaded file is missing required identity.

        Public entry point intended for callers (e.g. CLI ``--database`` flow,
        File → Open Company Database) that load a company file outside the
        first-run welcome card. Not auto-invoked from ``__init__`` to keep
        construction safe for headless tests; production triggers it from the
        ``main()`` entry point after the application event loop is ready.
        """
        if self._db_path is None:
            return
        if self._is_current_company_setup_complete():
            return
        self._on_create_company_file()

    def _on_open_company_database(self):
        prev = QSettings().value("company_database_path", "", type=str) or ""
        start_dir = str(Path(prev).parent) if prev else ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open company database (File → Backup copies the current .db first)",
            start_dir,
            "SQLite Database (*.db);;All Files (*.*)",
        )
        if path:
            self._switch_company_database(path, create_new=False)

    def _on_create_company_file(self) -> None:
        if self._worker and self._worker.isRunning():
            message_box_warning_ok(
                self,
                "Busy",
                "Wait for AI extraction to finish before creating a company file.",
                ok_tip="Close; wait for AI, then try again.",
            )
            return
        dlg = CreateCompanyFileDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        v = dlg.identity_values()
        prev = QSettings().value("company_database_path", "", type=str) or ""
        start_dir = str(Path(prev).parent) if prev else ""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save new company file (SQLite)",
            start_dir,
            "SQLite Database (*.db);;All Files (*.*)",
        )
        if not path:
            return
        if not path.lower().endswith(".db"):
            path += ".db"
        self._switch_company_database(path, create_new=True)
        save_company_identity(
            self._bank_db._conn,
            name=v["name"],
            address=v["address"],
            phone=v["phone"],
            email=v["email"],
            tax_id=v["tax_id"],
            business_type=v.get("business_type", ""),
            tax_structure=v.get("tax_structure", ""),
        )
        self._update_company_status()
        self._create_company_backup_structure(path)

    def _create_company_backup_structure(self, db_path: str) -> None:
        """Create ``<db parent>/backups/`` and write an initial named backup of *db_path*.

        The New Company wizard guarantees on-disk safety on day one by:

        * creating a sibling ``backups/`` folder next to the working ``.db``, and
        * writing ``<stem>-initial.db`` into that folder via :func:`backup_database`
          (same engine as ``probooks backup`` / File → Backup).

        Failures are surfaced via :func:`message_box_warning_ok` but never raise —
        the working company file is already created and saved at this point, so
        the user can still proceed and run File → Backup manually.
        """
        try:
            src = Path(db_path).resolve()
            backups_dir = src.parent / "backups"
            backups_dir.mkdir(parents=True, exist_ok=True)
            initial = backups_dir / f"{src.stem}-initial.db"
            backup_database(src, initial)
        except (OSError, sqlite3.Error, ValueError) as exc:
            message_box_warning_ok(
                self,
                "Backup folder",
                "Company file was created but the initial backup could not be written: "
                f"{escape_ampersand_for_qt(str(exc))}",
                ok_tip="Close; use File → Backup to write a backup manually.",
            )

    def _on_company_info(self) -> None:
        """Edit identity for the open company file (no .db creation/switching)."""
        if self._worker and self._worker.isRunning():
            message_box_warning_ok(
                self,
                "Busy",
                "Wait for AI extraction to finish before editing company info.",
                ok_tip="Close; wait for AI, then try again.",
            )
            return
        conn = getattr(self._bank_db, "_conn", None)
        if conn is None:
            message_box_information_ok(
                self,
                "Company info",
                "No company file is open.",
                ok_tip="Open or create a company first (File → New company / Switch company).",
            )
            return
        try:
            current = get_company_identity(conn)
        except sqlite3.Error as exc:
            message_box_critical_ok(
                self,
                "Company info",
                f"Could not read company identity:\n{escape_ampersand_for_qt(str(exc))}",
                ok_tip="Close; verify the company .db is healthy (File → Backup before retrying).",
            )
            return
        dlg = CreateCompanyFileDialog(self)
        dlg.set_initial_values(current)
        dlg.set_edit_mode(
            title="Company info",
            intro=(
                "Edit your company details. These values are saved inside this company "
                "database and become the source of truth for printed invoices, PDFs, and "
                "reports. Each company file is fully isolated."
            ),
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        v = dlg.identity_values()
        try:
            save_company_identity(
                conn,
                name=v["name"],
                address=v["address"],
                phone=v["phone"],
                email=v["email"],
                tax_id=v["tax_id"],
                business_type=v.get("business_type", ""),
                tax_structure=v.get("tax_structure", ""),
            )
        except sqlite3.Error as exc:
            message_box_critical_ok(
                self,
                "Company info",
                f"Could not save company identity:\n{escape_ampersand_for_qt(str(exc))}",
                ok_tip="Close; verify the company .db is writable (File → Backup before retrying).",
            )
            return
        self._update_company_status()

    def closeEvent(self, event):
        # Persist window geometry so next launch restores the same size/position
        _win_settings = QSettings(self._SETTINGS_ORG, self._SETTINGS_APP)
        _win_settings.setValue(self._GEOMETRY_KEY, self.saveGeometry())
        _win_settings.setValue(self._MAXIMIZED_KEY, self.isMaximized())
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
    # Load .env — walk up from this file's location until we find one (handles worktrees)
    _env_file = ""
    _search = os.path.abspath(__file__)
    for _ in range(8):
        _search = os.path.dirname(_search)
        _candidate = os.path.join(_search, ".env")
        if os.path.isfile(_candidate):
            _env_file = _candidate
            break
    if _env_file and os.path.isfile(_env_file):
        try:
            with open(_env_file) as _f:
                for _line in _f:
                    _line = _line.strip()
                    if _line and not _line.startswith("#") and "=" in _line:
                        _k, _v = _line.split("=", 1)
                        _k = _k.strip()
                        _v = _v.strip().strip('"').strip("'")
                        if _k and _k not in os.environ:
                            os.environ[_k] = _v
        except Exception:
            pass
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
    install_global_hover_message_suppression(app)
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
    QTimer.singleShot(0, window._route_into_setup_if_company_incomplete)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
