"""Invoice Intake — stage delivery tickets, PDFs, images, and pasted text for draft invoicing.

Queue + review; pasted **Text** rows get a conservative labeled-field extraction pass (see
``invoice_intake_text_extract``). **Send to Manual Invoice** opens Manual Invoice with memo, banner,
and high-confidence fields applied to the form where appropriate. PDF/image staging is unchanged.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt
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

from desktop_app.invoice_intake_text_extract import extract_text_intake_fields
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
            "Flow: stage a source → review → Send to Manual Invoice for a draft shell (memo + source); "
            "enter lines and Save."
        )
        flow.setWordWrap(True)
        flow.setStyleSheet(f"color: {_INV_CAPTION}; font-size: 11px; background: transparent;")
        lay.addWidget(flow)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._btn_pdf = QPushButton("Import PDF…")
        self._btn_pdf.setToolTip("Add a PDF to the intake queue (staged for future parsing).")
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
        self._btn_send_draft = QPushButton("Send to Manual Invoice")
        self._btn_send_draft.setToolTip(
            "Open Manual Invoice with a new draft: memo + raw text, and high-confidence text "
            "extraction applied to date/BOL/memo where applicable (confirm before Save)."
        )
        self._btn_send_draft.clicked.connect(self._on_send_to_manual_invoice)
        for b in (
            self._btn_pdf,
            self._btn_img,
            self._btn_paste,
            self._btn_remove,
            self._btn_send_draft,
        ):
            b.setAutoDefault(False)
            b.setDefault(False)
        actions.addWidget(self._btn_pdf)
        actions.addWidget(self._btn_img)
        actions.addWidget(self._btn_paste)
        actions.addWidget(self._btn_remove)
        actions.addWidget(self._btn_send_draft)
        actions.addStretch(1)
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

        rv_cap = QLabel("Review")
        rv_cap.setStyleSheet(
            f"color: {_INV_CAPTION}; font-size: 11px; font-weight: 600; "
            "letter-spacing: 0.03em; background: transparent;"
        )
        rv.addWidget(rv_cap)

        self._lbl_extracted = QLabel("Extracted fields")
        self._lbl_extracted.setStyleSheet(
            f"color: {_INV_CAPTION}; font-size: 11px; background: transparent;"
        )
        rv.addWidget(self._lbl_extracted)

        self._txt_extracted = QPlainTextEdit()
        self._txt_extracted.setReadOnly(True)
        self._txt_extracted.setPlaceholderText(
            "Select a text intake row to see labeled-field extraction (Date, Ticket/BOL, Customer, …)."
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
        self._txt_attachment.setPlaceholderText(
            "For text intake: raw staged source below. For files: path on disk."
        )
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
        self._refresh_send_draft_enabled()

    def _sync_draft_target_hint(self) -> None:
        inv = self._invoice_screen
        num = ""
        if inv is not None and hasattr(inv, "_inv_number"):
            le = getattr(inv, "_inv_number", None)
            if le is not None:
                num = (le.text() or "").strip()
        body = (
            "Use Send to Manual Invoice to open a new draft with this source in the memo.\n"
            f"Suggested invoice # (Manual Invoice form): {num or '—'}"
        )
        self._txt_draft.setPlainText(body)

    def _refresh_send_draft_enabled(self) -> None:
        on = self._invoice_screen is not None and self._table.currentRow() >= 0
        self._btn_send_draft.setEnabled(on)

    def _row_intake_payload(self, row: int) -> Optional[dict]:
        if row < 0 or row >= self._table.rowCount():
            return None
        src_it = self._table.item(row, 0)
        kind_it = self._table.item(row, 1)
        notes_it = self._table.item(row, 4)
        source_display = src_it.text() if src_it is not None else ""
        kind = (kind_it.text() if kind_it is not None else "").strip()
        queue_notes = notes_it.text() if notes_it is not None else ""
        path: Optional[str] = None
        payload: Optional[str] = None
        if src_it is not None:
            v = src_it.data(_ROLE_PATH)
            if isinstance(v, str) and v.strip():
                path = v
            t = src_it.data(_ROLE_TEXT_PAYLOAD)
            if isinstance(t, str):
                payload = t
        return {
            "source_display": source_display,
            "kind": kind,
            "path": path,
            "text_payload": payload,
            "queue_notes": queue_notes,
        }

    def _on_send_to_manual_invoice(self) -> None:
        inv = self._invoice_screen
        if inv is None:
            return
        r = self._table.currentRow()
        if r < 0:
            message_box_information_ok(
                self,
                "Invoice Intake",
                "Select a row in the queue first.",
                ok_tip="Click a row, then use Send to Manual Invoice.",
            )
            return
        if getattr(inv, "_ap_conn", None) is None:
            message_box_information_ok(
                self,
                "Invoice Intake",
                "Open a company file to create an invoice draft.",
                ok_tip="Close; use File → Open company… then try again.",
            )
            return
        data = self._row_intake_payload(r)
        if not data:
            return
        tex = None
        if (data.get("kind") or "").strip() == "Text" and data.get("text_payload"):
            tex = extract_text_intake_fields(str(data["text_payload"]))
        ok = inv.apply_intake_item_to_draft(
            source_display=data["source_display"],
            kind=data["kind"],
            path=data.get("path"),
            text_payload=data.get("text_payload"),
            queue_notes=data.get("queue_notes") or "",
            text_extraction=tex,
        )
        if ok:
            st = self._table.item(r, 3)
            if st is not None:
                st.setText("Sent to draft")

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
            ex = extract_text_intake_fields(payload)
            self._txt_extracted.setPlainText(ex.review_panel_text())
            raw_preview = payload.strip()
            if len(raw_preview) > 4000:
                raw_preview = raw_preview[:4000] + "\n… (truncated)"
            self._txt_attachment.setPlainText(
                "Clipboard / pasted text\n\n--- Raw staged text ---\n" + raw_preview
            )
        elif path:
            self._txt_extracted.setPlainText(
                "Preview for PDF/image files is not available yet — file is staged on disk."
            )
            self._txt_attachment.setPlainText(os.path.normpath(path))
        else:
            self._txt_extracted.setPlainText("")
            self._txt_attachment.setPlainText("—")

        self._sync_draft_target_hint()
        self._refresh_send_draft_enabled()

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
        path, _filt = QFileDialog.getOpenFileName(
            self,
            "Import PDF",
            "",
            "PDF files (*.pdf);;All files (*.*)",
        )
        if not path:
            return
        self._append_row(
            source_display=os.path.basename(path),
            kind="PDF",
            path=os.path.abspath(path),
        )

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
