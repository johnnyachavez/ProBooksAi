"""Invoice Intake — stage delivery tickets, PDFs, images, and pasted text for draft invoicing.

Foundation only: queue + review placeholders. Source → review → invoice draft is the intended flow;
full extraction and draft creation are not implemented yet.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class _ExtractWorker(QThread):
    """Background thread: calls invoice_screen.import_pdf_paths() without blocking the UI."""

    row_done = Signal(str, str, str)   # path, outcome ("ok"|"skip"|"error"), message
    all_done = Signal(int, int, list)  # imported, skipped, errors[]

    def __init__(self, invoice_screen, paths: list[str], parent=None):
        super().__init__(parent)
        self._invoice_screen = invoice_screen
        self._paths = paths

    def run(self) -> None:
        results: list[tuple[str, str, str]] = []

        def _cb(path, outcome, msg):
            results.append((path, outcome, msg))
            self.row_done.emit(path, outcome, msg)

        result = self._invoice_screen.import_pdf_paths(self._paths, on_row_done=_cb)
        self.all_done.emit(result["imported"], result["skipped"], result["errors"])

from desktop_app.qt_mnemonic import message_box_information_ok
from desktop_app.theme import (
    WORKFLOW_ALT_ROW as _INV_STRIPE,
    WORKFLOW_CAPTION as _INV_CAPTION,
    WORKFLOW_CONTROL_FACE,
    WORKFLOW_CONTROL_HOVER,
    WORKFLOW_CONTROL_PRESSED,
    WORKFLOW_GRID as _INV_GRID,
    WORKFLOW_HEADER_BG as _INV_HEADER,
    WORKFLOW_INPUT_BG,
    WORKFLOW_PAGE_BG as _INV_BG,
    WORKFLOW_PANEL_BG as _INV_PANEL,
    WORKFLOW_STRIP_BTN_OUTLINE,
    WORKFLOW_TEXT as _INV_TEXT,
)

_INTAKE_COLS = (
    "Source",
    "Type",
    "Date Added",
    "Status",
    "Notes / Needs Review",
)

_ROLE_PATH = Qt.ItemDataRole.UserRole
_ROLE_TEXT_PAYLOAD = Qt.ItemDataRole.UserRole + 1

_IMAGE_FILTER = (
    "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.tif *.tiff);;All files (*.*)"
)


def _now_display() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _readonly_item(text: str) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
    return it


def _editable_item(text: str) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setFlags(
        Qt.ItemFlag.ItemIsSelectable
        | Qt.ItemFlag.ItemIsEnabled
        | Qt.ItemFlag.ItemIsEditable
    )
    return it


class InvoiceIntakePanel(QWidget):
    """Queue of staged sources and a review placeholder for the future draft-invoice flow."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        invoice_screen: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._invoice_screen = invoice_screen
        self._extract_worker: Optional[_ExtractWorker] = None
        self.setObjectName("invoiceIntakePanel")
        self.setMinimumHeight(200)
        self.setToolTip(
            "Invoice Intake: drop in tickets, PDFs, images, or pasted text. "
            "Review here, then a future step will map lines to the invoice grid below."
        )
        self._build_ui()
        if self._invoice_screen is not None and hasattr(self._invoice_screen, "_inv_number"):
            invn = getattr(self._invoice_screen, "_inv_number", None)
            if invn is not None:
                invn.textChanged.connect(self._sync_draft_target_hint)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        band = QFrame()
        band.setObjectName("invoiceIntakeBand")
        band.setStyleSheet(
            f"QFrame#invoiceIntakeBand {{ background-color: {_INV_BG}; "
            f"border: 1px solid {_INV_GRID}; border-radius: 8px; }}"
            f"QFrame#invoiceIntakeBand QPushButton {{ background-color: {WORKFLOW_CONTROL_FACE}; "
            f"color: {_INV_TEXT}; border: 1px solid {WORKFLOW_STRIP_BTN_OUTLINE}; "
            f"border-radius: 4px; padding: 4px 12px; }}"
            f"QFrame#invoiceIntakeBand QPushButton:hover {{ background-color: {WORKFLOW_CONTROL_HOVER}; }}"
            f"QFrame#invoiceIntakeBand QPushButton:pressed {{ background-color: {WORKFLOW_CONTROL_PRESSED}; }}"
        )
        lay = QVBoxLayout(band)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel("Invoice Intake")
        title.setStyleSheet(
            f"font-size: 15px; font-weight: 600; color: {_INV_TEXT}; background: transparent;"
        )
        head.addWidget(title)
        head.addStretch(1)
        lay.addLayout(head)

        flow = QLabel(
            "Stage PDFs here, then click <b>Extract &amp; Create Invoice</b> to import via Claude AI."
        )
        flow.setWordWrap(True)
        flow.setTextFormat(Qt.TextFormat.RichText)
        flow.setStyleSheet(f"color: {_INV_CAPTION}; font-size: 11px; background: transparent;")
        lay.addWidget(flow)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._btn_pdf = QPushButton("Import PDF…")
        self._btn_pdf.setToolTip("Add one or more PDFs to the intake queue.")
        self._btn_pdf.clicked.connect(self._on_import_pdf)
        self._btn_img = QPushButton("Import image…")
        self._btn_img.setToolTip("Add an image (PNG, JPG, …) to the intake queue.")
        self._btn_img.clicked.connect(self._on_import_image)
        self._btn_paste = QPushButton("Paste text from clipboard")
        self._btn_paste.setToolTip("Create a text intake row from the current clipboard contents.")
        self._btn_paste.clicked.connect(self._on_paste_text)
        self._btn_remove = QPushButton("Remove selected")
        self._btn_remove.setToolTip("Remove the selected queue row.")
        self._btn_remove.clicked.connect(self._on_remove_selected)

        self._btn_extract_selected = QPushButton("⚡ Extract & Create Invoice")
        self._btn_extract_selected.setToolTip(
            "Send the selected staged PDF to Claude AI, extract invoice data, "
            "and create the invoice record (status: Sent)."
        )
        self._btn_extract_selected.clicked.connect(self._on_extract_selected)
        self._btn_extract_selected.setStyleSheet(
            f"QPushButton {{ background-color: #1a4b8b; color: #fff; "
            f"border: 1px solid #2a6bd0; border-radius: 4px; padding: 4px 14px; font-weight: 700; }}"
            f"QPushButton:hover {{ background-color: #2255a0; }}"
            f"QPushButton:pressed {{ background-color: #143870; }}"
            f"QPushButton:disabled {{ background-color: #333; color: #666; border-color: #444; }}"
        )

        self._btn_extract_all = QPushButton("Extract All Staged")
        self._btn_extract_all.setToolTip(
            "Process every Staged PDF in the queue through Claude AI and create invoice records."
        )
        self._btn_extract_all.clicked.connect(self._on_extract_all)

        for b in (
            self._btn_pdf,
            self._btn_img,
            self._btn_paste,
            self._btn_remove,
            self._btn_extract_selected,
            self._btn_extract_all,
        ):
            b.setAutoDefault(False)
            b.setDefault(False)

        actions.addWidget(self._btn_pdf)
        actions.addWidget(self._btn_img)
        actions.addWidget(self._btn_paste)
        actions.addWidget(self._btn_remove)
        actions.addStretch(1)
        actions.addWidget(self._btn_extract_all)
        actions.addWidget(self._btn_extract_selected)
        lay.addLayout(actions)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setObjectName("invoiceIntakeSplit")

        self._table = QTableWidget(0, len(_INTAKE_COLS))
        self._table.setObjectName("invoiceIntakeQueueTable")
        self._table.setHorizontalHeaderLabels(list(_INTAKE_COLS))
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        hh = self._table.horizontalHeader()
        hh.setStretchLastSection(True)
        for c in range(len(_INTAKE_COLS) - 1):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(len(_INTAKE_COLS) - 1, QHeaderView.ResizeMode.Stretch)
        self._table.setStyleSheet(
            f"QTableWidget#invoiceIntakeQueueTable {{"
            f" background-color: {_INV_PANEL};"
            f" alternate-background-color: {_INV_STRIPE};"
            f" color: {_INV_TEXT};"
            f" gridline-color: {_INV_GRID};"
            f" border: 1px solid {_INV_GRID};"
            " }"
            f"QHeaderView::section {{"
            f" background-color: {_INV_HEADER};"
            f" color: {_INV_TEXT};"
            f" padding: 6px; border: 1px solid {_INV_GRID};"
            " font-weight: 600;"
            " }}"
        )
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.itemSelectionChanged.connect(self._update_extract_button_state)

        review = QFrame()
        review.setObjectName("invoiceIntakeReviewPanel")
        review.setMinimumWidth(240)
        review.setStyleSheet(
            f"QFrame#invoiceIntakeReviewPanel {{ background-color: {_INV_PANEL}; "
            f"border: 1px solid {_INV_GRID}; border-radius: 8px; }}"
        )
        rv = QVBoxLayout(review)
        rv.setContentsMargins(10, 10, 10, 10)
        rv.setSpacing(6)

        rv_cap = QLabel("Review (next)")
        rv_cap.setStyleSheet(
            f"color: {_INV_CAPTION}; font-size: 11px; font-weight: 600; "
            "letter-spacing: 0.03em; background: transparent;"
        )
        rv.addWidget(rv_cap)

        self._lbl_extracted = QLabel("Extracted fields (preview)")
        self._lbl_extracted.setStyleSheet(
            f"color: {_INV_CAPTION}; font-size: 11px; background: transparent;"
        )
        rv.addWidget(self._lbl_extracted)

        self._txt_extracted = QPlainTextEdit()
        self._txt_extracted.setReadOnly(True)
        self._txt_extracted.setPlaceholderText(
            "No automated extraction yet — future pass will fill customer, lines, and amounts."
        )
        self._txt_extracted.setMinimumHeight(100)
        self._txt_extracted.setStyleSheet(
            f"QPlainTextEdit {{ background: {WORKFLOW_INPUT_BG}; color: {_INV_TEXT}; "
            f"border: 1px solid {_INV_GRID}; border-radius: 4px; padding: 6px; }}"
        )
        rv.addWidget(self._txt_extracted, 1)

        self._lbl_attachment = QLabel("Attachment / source reference")
        self._lbl_attachment.setStyleSheet(
            f"color: {_INV_CAPTION}; font-size: 11px; background: transparent;"
        )
        rv.addWidget(self._lbl_attachment)

        self._txt_attachment = QPlainTextEdit()
        self._txt_attachment.setReadOnly(True)
        self._txt_attachment.setPlaceholderText("File path or clipboard reference will appear here.")
        self._txt_attachment.setFixedHeight(72)
        self._txt_attachment.setStyleSheet(
            f"QPlainTextEdit {{ background: {WORKFLOW_INPUT_BG}; color: {_INV_TEXT}; "
            f"border: 1px solid {_INV_GRID}; border-radius: 4px; padding: 6px; }}"
        )
        rv.addWidget(self._txt_attachment)

        self._lbl_draft = QLabel("Invoice draft target")
        self._lbl_draft.setStyleSheet(
            f"color: {_INV_CAPTION}; font-size: 11px; background: transparent;"
        )
        rv.addWidget(self._lbl_draft)

        self._txt_draft = QPlainTextEdit()
        self._txt_draft.setReadOnly(True)
        self._txt_draft.setFixedHeight(56)
        self._txt_draft.setStyleSheet(
            f"QPlainTextEdit {{ background: {WORKFLOW_INPUT_BG}; color: {_INV_TEXT}; "
            f"border: 1px solid {_INV_GRID}; border-radius: 4px; padding: 6px; }}"
        )
        rv.addWidget(self._txt_draft)

        split.addWidget(self._table)
        split.addWidget(review)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 1)
        lay.addWidget(split, 1)

        outer.addWidget(band, 1)
        self._on_selection_changed()
        self._sync_draft_target_hint()
        self._update_extract_button_state()

    def _sync_draft_target_hint(self) -> None:
        inv = self._invoice_screen
        num = ""
        if inv is not None and hasattr(inv, "_inv_number"):
            le = getattr(inv, "_inv_number", None)
            if le is not None:
                num = (le.text() or "").strip()
        body = (
            "Future: create or update a draft invoice from the selected intake row.\n"
            f"Suggested invoice # (current form): {num or '—'}"
        )
        self._txt_draft.setPlainText(body)

    def _update_extract_button_state(self) -> None:
        r = self._table.currentRow()
        enabled = False
        if r >= 0:
            src_it = self._table.item(r, 0)
            if src_it is not None:
                path = src_it.data(_ROLE_PATH)
                enabled = isinstance(path, str) and bool(path.strip())
        self._btn_extract_selected.setEnabled(enabled)

    def _on_selection_changed(self) -> None:
        r = self._table.currentRow()
        if r < 0:
            self._txt_extracted.setPlainText("")
            self._txt_attachment.setPlainText("")
            self._sync_draft_target_hint()
            return

        kind = ""
        it_k = self._table.item(r, 1)
        if it_k is not None:
            kind = it_k.text()

        src_it = self._table.item(r, 0)
        path: Optional[str] = None
        payload: Optional[str] = None
        if src_it is not None:
            v = src_it.data(_ROLE_PATH)
            if isinstance(v, str) and v.strip():
                path = v
            t = src_it.data(_ROLE_TEXT_PAYLOAD)
            if isinstance(t, str):
                payload = t

        if kind == "Text" and payload:
            preview = payload.strip()
            if len(preview) > 4000:
                preview = preview[:4000] + "\n… (truncated)"
            self._txt_extracted.setPlainText(
                "Staged text (no AI extraction yet):\n\n" + preview
            )
            self._txt_attachment.setPlainText("Clipboard / pasted text")
        elif path:
            self._txt_extracted.setPlainText(
                "Preview for PDF/image files is not available yet — file is staged on disk."
            )
            self._txt_attachment.setPlainText(os.path.normpath(path))
        else:
            self._txt_extracted.setPlainText("")
            self._txt_attachment.setPlainText("—")

        self._sync_draft_target_hint()

    def _append_row(
        self,
        *,
        source_display: str,
        kind: str,
        path: Optional[str] = None,
        text_payload: Optional[str] = None,
        notes: str = "",
    ) -> None:
        r = self._table.rowCount()
        self._table.insertRow(r)
        s0 = _readonly_item(source_display)
        if path:
            s0.setData(_ROLE_PATH, path)
        if text_payload is not None:
            s0.setData(_ROLE_TEXT_PAYLOAD, text_payload)
        self._table.setItem(r, 0, s0)
        self._table.setItem(r, 1, _readonly_item(kind))
        self._table.setItem(r, 2, _readonly_item(_now_display()))
        self._table.setItem(r, 3, _editable_item("Staged"))
        self._table.setItem(r, 4, _editable_item(notes))
        self._table.selectRow(r)
        self._on_selection_changed()

    def _on_import_pdf(self) -> None:
        paths, _filt = QFileDialog.getOpenFileNames(
            self,
            "Import PDFs",
            "",
            "PDF files (*.pdf);;All files (*.*)",
        )
        for path in paths:
            self._append_row(
                source_display=os.path.basename(path),
                kind="PDF",
                path=os.path.abspath(path),
            )

    def _is_worker_busy(self) -> bool:
        return self._extract_worker is not None and self._extract_worker.isRunning()

    def _start_extraction(self, paths: list[str], row_map: dict[str, int]) -> None:
        """Kick off _ExtractWorker for *paths*; update table rows via signals (non-blocking)."""
        inv_screen = self._invoice_screen
        if inv_screen is None or not hasattr(inv_screen, "import_pdf_paths"):
            message_box_information_ok(self, "Not available", "Invoice screen is not connected.", ok_tip="Close.")
            return

        if self._is_worker_busy():
            message_box_information_ok(self, "Busy", "Extraction already in progress — wait for it to finish.", ok_tip="Close.")
            return

        # Disable buttons while running
        self._btn_extract_selected.setEnabled(False)
        self._btn_extract_all.setEnabled(False)
        self._btn_extract_all.setText("Extracting…")

        worker = _ExtractWorker(inv_screen, paths)
        self._extract_worker = worker

        def _on_row(pdf_path, outcome, msg):
            r = row_map.get(pdf_path)
            if r is None:
                return
            status_it = self._table.item(r, 3)
            notes_it = self._table.item(r, 4)
            label = {"ok": "Imported", "skip": "Duplicate", "error": "Error"}.get(outcome, outcome)
            if status_it:
                status_it.setText(label)
            if notes_it:
                notes_it.setText(msg)

        def _on_all_done(imported, skipped, errors):
            self._btn_extract_all.setText("Extract All Staged")
            self._update_extract_button_state()
            self._btn_extract_all.setEnabled(True)
            parts = [f"Imported: {imported}", f"Skipped (duplicates): {skipped}"]
            if errors:
                parts.append(f"Errors: {len(errors)}")
                parts.extend(f"  {x}" for x in errors[:5])
            message_box_information_ok(self, "Extraction complete", "\n".join(parts), ok_tip="Close.")

        worker.row_done.connect(_on_row)
        worker.all_done.connect(_on_all_done)
        worker.start()

    def _on_extract_selected(self) -> None:
        """Extract the currently selected staged PDF row via Claude AI (background thread)."""
        if self._is_worker_busy():
            message_box_information_ok(self, "Busy", "Extraction already in progress.", ok_tip="Close.")
            return
        r = self._table.currentRow()
        if r < 0:
            message_box_information_ok(self, "No row selected", "Select a staged PDF row first.", ok_tip="Close.")
            return
        src_it = self._table.item(r, 0)
        if src_it is None:
            return
        path = src_it.data(_ROLE_PATH)
        if not isinstance(path, str) or not path.strip():
            message_box_information_ok(self, "No file", "Selected row has no file path (text rows cannot be extracted).", ok_tip="Close.")
            return

        status_it = self._table.item(r, 3)
        if status_it:
            status_it.setText("Extracting…")

        self._start_extraction([path], {path: r})

    def _on_extract_all(self) -> None:
        """Extract and import every Staged PDF row in the queue (background thread)."""
        if self._is_worker_busy():
            message_box_information_ok(self, "Busy", "Extraction already in progress.", ok_tip="Close.")
            return

        staged_rows: list[tuple[int, str]] = []
        for r in range(self._table.rowCount()):
            kind_it = self._table.item(r, 1)
            status_it = self._table.item(r, 3)
            src_it = self._table.item(r, 0)
            if kind_it and kind_it.text() == "PDF" and status_it and status_it.text() == "Staged":
                if src_it is not None:
                    path = src_it.data(_ROLE_PATH)
                    if isinstance(path, str) and path.strip():
                        staged_rows.append((r, path))

        if not staged_rows:
            message_box_information_ok(self, "Nothing to extract", "No Staged PDF rows found in the queue.", ok_tip="Close.")
            return

        # Mark all as Extracting… immediately so the user sees progress
        for r, _ in staged_rows:
            status_it = self._table.item(r, 3)
            if status_it:
                status_it.setText("Extracting…")

        row_map = {path: r for r, path in staged_rows}
        self._start_extraction([p for _, p in staged_rows], row_map)

    def _on_import_image(self) -> None:
        path, _filt = QFileDialog.getOpenFileName(
            self,
            "Import image",
            "",
            _IMAGE_FILTER,
        )
        if not path:
            return
        self._append_row(
            source_display=os.path.basename(path),
            kind="Image",
            path=os.path.abspath(path),
        )

    def _on_paste_text(self) -> None:
        clip = QGuiApplication.clipboard()
        text = (clip.text() if clip is not None else "") or ""
        if not text.strip():
            message_box_information_ok(
                self,
                "Invoice Intake",
                "Clipboard is empty or has no text.",
                ok_tip="Copy text first, then use Paste text from clipboard.",
            )
            return
        n = len(text.strip())
        label = f"Pasted text ({n} chars)"
        self._append_row(
            source_display=label,
            kind="Text",
            text_payload=text,
            notes="Needs review",
        )

    def _on_remove_selected(self) -> None:
        r = self._table.currentRow()
        if r < 0:
            return
        self._table.removeRow(r)
        self._on_selection_changed()
