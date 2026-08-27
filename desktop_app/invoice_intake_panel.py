"""Invoice Intake — stage delivery tickets, PDFs, images, pasted text, and dispatch CSV.

Queue + review; **Text** and **PDF/image** (after text extraction) use the same conservative
``extract_text_intake_fields`` pass. PDFs use the text layer via ``invoice_intake_file_extract``;
images use optional OCR when ``pytesseract``/Tesseract are available.
**Import dispatch CSV** loads Johnny's dispatch sheet export (offline v1). Grouped loads
pre-fill Create Invoices / Enter Bills; they do not replace those QB-like forms.
**Send to Manual Invoice** opens Manual Invoice with memo, banner, and high-confidence fields
when extraction supports them.
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
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop_app.invoice_intake_file_extract import extract_text_for_intake_kind
from desktop_app.invoice_intake_text_extract import extract_text_intake_fields
from probooksai.dispatch_intake import (
    DispatchGoogleNotConfigured,
    DispatchLoadRow,
    drafts_for_bill_row,
    drafts_for_invoice_row,
    fetch_google_dispatch_rows,
    job_billing_rule,
    parse_dispatch_csv,
    row_from_payload,
)
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
# Cached PDF/image extraction (avoid re-reading file on each selection)
_ROLE_FILE_EXTRACTED_TEXT = Qt.ItemDataRole.UserRole + 2
_ROLE_FILE_EXTRACT_WARN = Qt.ItemDataRole.UserRole + 3
_ROLE_FILE_EXTRACT_DONE = Qt.ItemDataRole.UserRole + 4
_ROLE_DISPATCH = Qt.ItemDataRole.UserRole + 5

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
    """Queue of staged sources (text / PDF / image) with extraction review and handoff to Manual Invoice."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        invoice_screen: Optional[QWidget] = None,
        enter_bills_screen: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._invoice_screen = invoice_screen
        self._enter_bills_screen = enter_bills_screen
        self.setObjectName("invoiceIntakePanel")
        self.setMinimumHeight(200)
        self.setToolTip(
            "Invoice Intake: stage PDFs, images, pasted text, or a dispatch CSV. "
            "Review extracted fields and raw text, then Send to Manual Invoice or Send to Enter Bills."
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
            "Flow: stage a PDF, image, pasted text, or dispatch CSV → review → "
            "Send to Manual Invoice (Create Invoices) or Send to Enter Bills. "
            "Dispatch CSV is the offline v1 path for the 1 CHAVAN DISPATCH sheet."
        )
        flow.setWordWrap(True)
        flow.setStyleSheet(f"color: {_INV_CAPTION}; font-size: 11px; background: transparent;")
        lay.addWidget(flow)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._btn_pdf = QPushButton("Import PDF…")
        self._btn_pdf.setToolTip(
            "Add a PDF to the intake queue. Text layer is extracted for review (scanned PDFs may be empty)."
        )
        self._btn_pdf.clicked.connect(self._on_import_pdf)
        self._btn_img = QPushButton("Import image…")
        self._btn_img.setToolTip(
            "Add an image (PNG, JPG, …). OCR runs when pytesseract/Tesseract are installed; otherwise path-only."
        )
        self._btn_img.clicked.connect(self._on_import_image)
        self._btn_paste = QPushButton("Paste text from clipboard")
        self._btn_paste.setToolTip("Create a text intake row from the current clipboard contents.")
        self._btn_paste.clicked.connect(self._on_paste_text)
        self._btn_csv = QPushButton("Import dispatch CSV…")
        self._btn_csv.setToolTip(
            "Load a CSV export of the dispatch loads table (DATE, INVOICE, DISPATCH, DRIVER, "
            "INVOICE RATE, PAY RATE, PO / LOAD#, BOL#, QB Inv No.). Tax ID / SSN / EIN / bank "
            "columns are ignored. Blank invoice rates stay in the queue as needs rate."
        )
        self._btn_csv.clicked.connect(self._on_import_dispatch_csv)
        self._btn_google = QPushButton("Load Google Sheet…")
        self._btn_google.setToolTip(
            "Live Google pull is stubbed in v1 (no API token). Export 1 CHAVAN DISPATCH as CSV instead."
        )
        self._btn_google.clicked.connect(self._on_load_google_sheet)
        self._btn_remove = QPushButton("Remove selected")
        self._btn_remove.setToolTip("Remove the selected queue row.")
        self._btn_remove.clicked.connect(self._on_remove_selected)
        self._btn_send_draft = QPushButton("Send to Manual Invoice")
        self._btn_send_draft.setToolTip(
            "Open Manual Invoice with a new draft: memo + source text, and high-confidence "
            "extraction applied to date/BOL when available (confirm before Save)."
        )
        self._btn_send_draft.clicked.connect(self._on_send_to_manual_invoice)
        self._btn_send_bill = QPushButton("Send to Enter Bills")
        self._btn_send_bill.setToolTip(
            "Open Enter Bills with vendor = driver/trucker name, amount = pay rate, "
            "memo = dispatch + BOL. Blank pay rate stays needs pay; 0 is allowed (owner-operator JC)."
        )
        self._btn_send_bill.clicked.connect(self._on_send_to_enter_bills)
        for b in (
            self._btn_pdf,
            self._btn_img,
            self._btn_paste,
            self._btn_csv,
            self._btn_google,
            self._btn_remove,
            self._btn_send_draft,
            self._btn_send_bill,
        ):
            b.setAutoDefault(False)
            b.setDefault(False)
        actions.addWidget(self._btn_pdf)
        actions.addWidget(self._btn_img)
        actions.addWidget(self._btn_paste)
        actions.addWidget(self._btn_csv)
        actions.addWidget(self._btn_google)
        actions.addWidget(self._btn_remove)
        actions.addWidget(self._btn_send_draft)
        actions.addWidget(self._btn_send_bill)
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
            "Select a queue row: Text, PDF, or Image — extracted fields (Date, Ticket/BOL, …) when text is available."
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
            "Raw source: pasted text, or extracted PDF/image text + file path."
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
        self._refresh_send_bill_enabled()

    def set_enter_bills_screen(self, screen: Optional[QWidget]) -> None:
        self._enter_bills_screen = screen
        self._refresh_send_bill_enabled()

    def _sync_draft_target_hint(self) -> None:
        inv = self._invoice_screen
        num = ""
        if inv is not None and hasattr(inv, "_inv_number"):
            le = getattr(inv, "_inv_number", None)
            if le is not None:
                num = (le.text() or "").strip()
        body = (
            "Use Send to Manual Invoice to open Create Invoices with grouped dispatch lines "
            "(or a memo draft for PDF/text). Send to Enter Bills pre-fills payables from DRIVER + PAY RATE.\n"
            f"Suggested invoice # (Manual Invoice form): {num or '—'}"
        )
        self._txt_draft.setPlainText(body)

    def _refresh_send_draft_enabled(self) -> None:
        on = self._invoice_screen is not None and self._table.currentRow() >= 0
        self._btn_send_draft.setEnabled(on)

    def _refresh_send_bill_enabled(self) -> None:
        r = self._table.currentRow()
        kind = ""
        if r >= 0:
            it = self._table.item(r, 1)
            kind = (it.text() if it is not None else "").strip()
        on = self._enter_bills_screen is not None and r >= 0 and kind == "Dispatch"
        self._btn_send_bill.setEnabled(on)

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

    def _dispatch_state(self, row: int) -> Optional[dict]:
        src_it = self._table.item(row, 0)
        if src_it is None:
            return None
        raw = src_it.data(_ROLE_DISPATCH)
        return raw if isinstance(raw, dict) else None

    def _set_dispatch_state(self, row: int, state: dict) -> None:
        src_it = self._table.item(row, 0)
        if src_it is None:
            return
        src_it.setData(_ROLE_DISPATCH, state)

    def _dispatch_row_at(self, row: int) -> Optional[DispatchLoadRow]:
        state = self._dispatch_state(row)
        if not state:
            return None
        payload = state.get("row")
        if not isinstance(payload, dict):
            return None
        return row_from_payload(payload)

    def _iter_dispatch_queue(self) -> list[tuple[int, DispatchLoadRow, dict]]:
        out: list[tuple[int, DispatchLoadRow, dict]] = []
        for r in range(self._table.rowCount()):
            state = self._dispatch_state(r)
            if not state:
                continue
            payload = state.get("row")
            if not isinstance(payload, dict):
                continue
            out.append((r, row_from_payload(payload), state))
        return out

    def _refresh_dispatch_status(self, row: int) -> None:
        state = self._dispatch_state(row)
        load = self._dispatch_row_at(row)
        if state is None or load is None:
            return
        bits: list[str] = []
        if state.get("invoice_sent"):
            bits.append("Sent to draft")
        elif load.invoice_rate_missing:
            bits.append("needs rate")
        if state.get("bill_sent"):
            bits.append("Sent to bill")
        elif load.pay_rate_missing:
            bits.append("needs pay")
        text = " / ".join(bits) if bits else "Staged"
        st = self._table.item(row, 3)
        if st is not None:
            st.setText(text)

    def _mark_dispatch_sent(self, table_rows: list[int], *, invoice: bool = False, bill: bool = False) -> None:
        for r in table_rows:
            state = self._dispatch_state(r)
            if not state:
                continue
            if invoice:
                state["invoice_sent"] = True
            if bill:
                state["bill_sent"] = True
            self._set_dispatch_state(r, state)
            self._refresh_dispatch_status(r)

    def _ensure_cached_file_text(
        self,
        row: int,
        kind: str,
        path: str,
        src_it: QTableWidgetItem | None,
    ) -> tuple[str, str | None]:
        """Load PDF/image text once per queue row; cache on the Source column item."""
        if src_it is None:
            return "", None
        done = src_it.data(_ROLE_FILE_EXTRACT_DONE)
        if done:
            t = src_it.data(_ROLE_FILE_EXTRACTED_TEXT)
            w = src_it.data(_ROLE_FILE_EXTRACT_WARN)
            out_w = w if isinstance(w, str) and w.strip() else None
            return (t or ""), out_w
        text, warn = extract_text_for_intake_kind(kind, path)
        src_it.setData(_ROLE_FILE_EXTRACTED_TEXT, text or "")
        if warn:
            src_it.setData(_ROLE_FILE_EXTRACT_WARN, warn)
        src_it.setData(_ROLE_FILE_EXTRACT_DONE, True)
        return text or "", warn

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
        kind = (data.get("kind") or "").strip()
        if kind == "Dispatch":
            self._send_dispatch_to_manual_invoice(r)
            return
        tex = None
        extracted_file_text = ""
        file_note: str | None = None
        src_it = self._table.item(r, 0)
        if kind == "Text" and data.get("text_payload"):
            tex = extract_text_intake_fields(str(data["text_payload"]))
        elif kind in ("PDF", "Image") and data.get("path"):
            extracted_file_text, file_note = self._ensure_cached_file_text(
                r, kind, str(data["path"]), src_it
            )
            if extracted_file_text.strip():
                tex = extract_text_intake_fields(extracted_file_text)
        ok = inv.apply_intake_item_to_draft(
            source_display=data["source_display"],
            kind=data["kind"],
            path=data.get("path"),
            text_payload=data.get("text_payload"),
            queue_notes=data.get("queue_notes") or "",
            text_extraction=tex,
            extracted_file_text=extracted_file_text or None,
            file_extract_note=file_note,
        )
        if ok:
            st = self._table.item(r, 3)
            if st is not None:
                st.setText("Sent to draft")

    def _send_dispatch_to_manual_invoice(self, table_row: int) -> None:
        inv = self._invoice_screen
        if inv is None or not hasattr(inv, "apply_dispatch_invoice_draft"):
            return
        target = self._dispatch_row_at(table_row)
        if target is None:
            return
        if target.invoice_rate_missing or target.invoice_rate is None:
            message_box_information_ok(
                self,
                "Invoice Intake",
                "This load has no invoice rate. It stays in the queue as needs rate.",
                ok_tip="Close; fill INVOICE RATE on the sheet, re-import, or enter the invoice manually.",
            )
            return
        queued = self._iter_dispatch_queue()
        live_rows = [
            load
            for _r, load, state in queued
            if not state.get("invoice_sent")
        ]
        # Include already-sent siblings so grouping still matches the sheet,
        # but only mark unsent members after a successful handoff.
        all_loads = [load for _r, load, _st in queued]
        draft = drafts_for_invoice_row(all_loads, target)
        if draft is None:
            message_box_information_ok(
                self,
                "Invoice Intake",
                "This load cannot be grouped into an invoice (needs a job code and date, or a QB Inv No.).",
                ok_tip="Close; check the INVOICE and DATE columns, then try again.",
            )
            return
        # Rebuild from unsent + this target so we do not duplicate already-sent lines.
        unsent_same = [
            load
            for load in live_rows
            if load.source_row in set(draft.source_rows) or load.source_row == target.source_row
        ]
        if not unsent_same:
            unsent_same = [target]
        draft = drafts_for_invoice_row(unsent_same, target) or draft
        ok = inv.apply_dispatch_invoice_draft(draft)
        if not ok:
            return
        sent_table_rows = [
            r
            for r, load, state in queued
            if load.source_row in set(draft.source_rows) and not state.get("invoice_sent")
        ]
        self._mark_dispatch_sent(sent_table_rows, invoice=True)

    def _on_send_to_enter_bills(self) -> None:
        bills = self._enter_bills_screen
        if bills is None:
            return
        r = self._table.currentRow()
        if r < 0:
            message_box_information_ok(
                self,
                "Invoice Intake",
                "Select a dispatch row in the queue first.",
                ok_tip="Click a dispatch CSV row, then use Send to Enter Bills.",
            )
            return
        if getattr(bills, "_ap_conn", None) is None:
            message_box_information_ok(
                self,
                "Invoice Intake",
                "Open a company file to create a bill draft.",
                ok_tip="Close; use File → Open company… then try again.",
            )
            return
        target = self._dispatch_row_at(r)
        if target is None:
            message_box_information_ok(
                self,
                "Invoice Intake",
                "Send to Enter Bills is for dispatch CSV rows.",
                ok_tip="Close; import a dispatch CSV, then select a load row.",
            )
            return
        if target.pay_rate_missing or target.pay_rate is None:
            message_box_information_ok(
                self,
                "Invoice Intake",
                "This load has no pay rate. It stays in the queue as needs pay.",
                ok_tip="Close; fill PAY RATE on the sheet (0 is allowed for owner-operator JC).",
            )
            return
        queued = self._iter_dispatch_queue()
        all_loads = [load for _r, load, _st in queued]
        draft = drafts_for_bill_row(all_loads, target)
        if draft is None:
            message_box_information_ok(
                self,
                "Invoice Intake",
                "This load cannot be grouped into a bill (needs a driver name).",
                ok_tip="Close; check the DRIVER column, then try again.",
            )
            return
        unsent = [
            load
            for _r, load, state in queued
            if not state.get("bill_sent")
            and load.source_row in set(draft.source_rows)
        ]
        if unsent:
            draft = drafts_for_bill_row(unsent, target) or draft
        if not hasattr(bills, "apply_dispatch_bill_draft"):
            return
        ok = bills.apply_dispatch_bill_draft(draft)
        if not ok:
            return
        sent_table_rows = [
            tr
            for tr, load, state in queued
            if load.source_row in set(draft.source_rows) and not state.get("bill_sent")
        ]
        self._mark_dispatch_sent(sent_table_rows, bill=True)
        self._reveal_enter_bills()

    def _reveal_enter_bills(self) -> None:
        bills = self._enter_bills_screen
        if bills is None:
            return
        w: Optional[QWidget] = bills.parentWidget()
        while w is not None:
            if isinstance(w, QTabWidget):
                idx = w.indexOf(bills)
                if idx >= 0:
                    w.setCurrentIndex(idx)
                    return
            w = w.parentWidget()

    def _on_import_dispatch_csv(self) -> None:
        path, _filt = QFileDialog.getOpenFileName(
            self,
            "Import dispatch CSV",
            "",
            "CSV files (*.csv);;All files (*.*)",
        )
        if not path:
            return
        self.load_dispatch_csv_path(path)

    def load_dispatch_csv_path(self, path: str, *, notify: bool = True) -> int:
        """Load a dispatch CSV into the queue. Returns the number of rows added."""
        try:
            result = parse_dispatch_csv(path)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            message_box_information_ok(
                self,
                "Invoice Intake",
                f"Could not read dispatch CSV:\n{exc}",
                ok_tip="Close; export the sheet as CSV (UTF-8) and try again.",
            )
            return 0
        for load in result.rows:
            self._append_dispatch_row(load)
        extra = ""
        if result.skipped_sensitive_headers:
            extra = (
                f" Skipped tax/ID columns: {', '.join(result.skipped_sensitive_headers)}."
            )
        n = len(result.rows)
        if notify:
            message_box_information_ok(
                self,
                "Invoice Intake",
                f"Loaded {n} dispatch load{'s' if n != 1 else ''} from {os.path.basename(path)}."
                f"{extra}",
                ok_tip="Close; review needs rate / needs pay, then Send to Manual Invoice or Enter Bills.",
            )
        return n

    def _append_dispatch_row(self, load: DispatchLoadRow) -> None:
        self._append_row(
            source_display=load.source_label(),
            kind="Dispatch",
            text_payload=load.review_text(),
            notes=load.notes_summary(),
            status=load.queue_status(),
        )
        r = self._table.currentRow()
        src_it = self._table.item(r, 0) if r >= 0 else None
        if src_it is not None:
            src_it.setData(
                _ROLE_DISPATCH,
                {"row": load.as_dict(), "invoice_sent": False, "bill_sent": False},
            )

    def _on_load_google_sheet(self) -> None:
        try:
            fetch_google_dispatch_rows()
        except DispatchGoogleNotConfigured as exc:
            message_box_information_ok(
                self,
                "Invoice Intake",
                str(exc),
                ok_tip="Close; export the sheet as CSV, then use Import dispatch CSV.",
            )

    def _on_selection_changed(self) -> None:
        r = self._table.currentRow()
        if r < 0:
            self._txt_extracted.setPlainText("")
            self._txt_attachment.setPlainText("")
            self._sync_draft_target_hint()
            self._refresh_send_draft_enabled()
            self._refresh_send_bill_enabled()
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
        elif kind == "Dispatch":
            load = self._dispatch_row_at(r)
            if load is not None:
                self._txt_extracted.setPlainText(load.review_text())
                rule = job_billing_rule(load.invoice_code)
                att_bits = [f"Dispatch CSV: {load.source_ref or '—'}", f"Sheet row: {load.source_row}"]
                if rule:
                    att_bits.append(
                        f"Billing rule: {rule.get('customer_name') or '—'} — {rule.get('how_to_bill') or ''}"
                    )
                self._txt_attachment.setPlainText("\n".join(att_bits).strip())
            elif payload:
                self._txt_extracted.setPlainText(payload)
                self._txt_attachment.setPlainText("Dispatch CSV")
            else:
                self._txt_extracted.setPlainText("")
                self._txt_attachment.setPlainText("—")
        elif path and kind in ("PDF", "Image"):
            src_it = self._table.item(r, 0)
            text, warn = self._ensure_cached_file_text(r, kind, path, src_it)
            if text.strip():
                ex = extract_text_intake_fields(text)
                self._txt_extracted.setPlainText(ex.review_panel_text())
            else:
                ex0 = extract_text_intake_fields("")
                header = (
                    f"Source: {kind} — no extractable text for field parsing.\n"
                    f"Status: {warn or 'Not extracted.'}\n\n"
                )
                self._txt_extracted.setPlainText(header + ex0.review_panel_text())
            parts_att: list[str] = [
                f"Path:\n{os.path.normpath(path)}",
                f"Extracted text length: {len(text)} characters.",
            ]
            if warn:
                parts_att.append(f"Note: {warn}")
            if text.strip():
                att_body = text.strip()
                if len(att_body) > 4000:
                    att_body = att_body[:4000] + "\n… (truncated)"
                parts_att.extend(["", "--- Raw extracted text ---", att_body])
            self._txt_attachment.setPlainText("\n".join(parts_att))
        elif path:
            self._txt_extracted.setPlainText("")
            self._txt_attachment.setPlainText(os.path.normpath(path))
        else:
            self._txt_extracted.setPlainText("")
            self._txt_attachment.setPlainText("—")

        self._sync_draft_target_hint()
        self._refresh_send_draft_enabled()
        self._refresh_send_bill_enabled()

    def _append_row(
        self,
        *,
        source_display: str,
        kind: str,
        path: Optional[str] = None,
        text_payload: Optional[str] = None,
        notes: str = "",
        status: str = "Staged",
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
        self._table.setItem(r, 3, _editable_item(status))
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
