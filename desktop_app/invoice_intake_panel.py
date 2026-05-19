"""Invoice Intake — stage delivery tickets, PDFs, images, and pasted text for draft invoicing.

Foundation only: queue + review placeholders. Source → review → invoice draft is the intended flow;
full extraction and draft creation are not implemented yet.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
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
    """Background thread: AI extraction + DB writes using its own SQLite connection.

    Never touches Qt widgets or the main thread's DB connection — safe to run in a
    QThread.  Signals are queued across thread boundary automatically by Qt.
    """

    row_done = Signal(str, str, str)   # path, outcome ("ok"|"skip"|"error"), message
    all_done = Signal(int, int, list)  # imported, skipped, errors[]

    def __init__(self, db_path: str, pdf_paths: list[str], parent=None):
        super().__init__(parent)
        self._db_path = db_path
        self._paths = pdf_paths

    def run(self) -> None:
        import sqlite3 as _sql
        import logging as _log
        from probooksai import business as _biz
        from desktop_app.invoice_screen import _ai_extract_invoice, _find_or_create_customer

        # Log to file so we can diagnose failures even when the UI is stuck
        _log_path = os.path.join(os.environ.get("APPDATA", ""), "ProBooksAi", "extraction.log")
        try:
            os.makedirs(os.path.dirname(_log_path), exist_ok=True)
            _fh = _log.FileHandler(_log_path, encoding="utf-8")
            _fh.setFormatter(_log.Formatter("%(asctime)s %(levelname)s %(message)s"))
            _logger = _log.getLogger("intake_extract")
            _logger.handlers.clear()
            _logger.addHandler(_fh)
            _logger.setLevel(_log.DEBUG)
        except Exception:
            _logger = _log.getLogger("intake_extract")

        _logger.info(f"Worker started — {len(self._paths)} file(s), db={self._db_path}")
        _logger.info(f"ANTHROPIC_API_KEY set: {bool(os.environ.get('ANTHROPIC_API_KEY','').strip())}")

        try:
            conn = _sql.connect(self._db_path)
            conn.row_factory = _sql.Row
        except Exception as exc:
            _logger.error(f"Cannot open DB: {exc}")
            self.all_done.emit(0, 0, [f"Cannot open company file: {exc}"])
            return

        imported = 0
        skipped = 0
        errors: list[str] = []

        try:
            for pdf_path in self._paths:
                fname = os.path.basename(pdf_path)
                _logger.info(f"Extracting: {fname}")
                data = _ai_extract_invoice(pdf_path)
                if not data:
                    msg = f"{fname}: Could not extract (check ANTHROPIC_API_KEY)"
                    _logger.error(msg)
                    errors.append(msg)
                    self.row_done.emit(pdf_path, "error", msg)
                    continue
                _logger.info(f"AI returned data for {fname}: inv={data.get('invoice_number')} customer={data.get('customer_name')}")

                inv_num = (data.get("invoice_number") or "").strip()
                inv_date = (data.get("invoice_date") or "").strip()
                customer_name = (data.get("customer_name") or "").strip()
                po = (data.get("po_contract") or "").strip()
                name_job = (data.get("name_job") or "").strip()
                total = float(data.get("total") or 0.0)

                if not customer_name:
                    msg = f"{fname}: No customer name found"
                    _logger.error(msg)
                    errors.append(msg)
                    self.row_done.emit(pdf_path, "error", msg)
                    continue

                try:
                    customer_id = _find_or_create_customer(
                        conn, customer_name, data.get("customer_address", "")
                    )
                except Exception as exc:
                    msg = f"{fname}: Customer error — {exc}"
                    errors.append(msg)
                    self.row_done.emit(pdf_path, "error", msg)
                    continue

                memo_parts = []
                if po:
                    memo_parts.append(f"PO: {po}")
                if name_job:
                    memo_parts.append(f"Job: {name_job}")
                memo = "\n".join(memo_parts)

                inv_lines = []
                for ln in (data.get("lines") or []):
                    so = (ln.get("serviced_on") or "").strip()
                    jl = (ln.get("jl_num") or "").strip()
                    desc = (ln.get("description") or "Service").strip()
                    bol = (ln.get("bol") or "").strip()
                    parts = [so, jl, desc, bol]
                    while parts and not parts[-1]:
                        parts.pop()
                    full_desc = " — ".join(parts)
                    inv_lines.append({
                        "description": full_desc,
                        "qty": float(ln.get("qty") or 1),
                        "rate": float(ln.get("rate") or total),
                    })
                if not inv_lines:
                    inv_lines = [{"description": "Trucking Service", "qty": 1.0, "rate": total}]

                try:
                    existing = conn.execute(
                        "SELECT id FROM invoices WHERE invoice_number = ?", (inv_num,)
                    ).fetchone()
                    if existing:
                        skipped += 1
                        self.row_done.emit(pdf_path, "skip", f"Duplicate #{inv_num}")
                        continue

                    _biz.create_invoice(
                        conn,
                        customer_id=customer_id,
                        invoice_number=inv_num,
                        invoice_date=inv_date,
                        memo=memo,
                        lines=inv_lines,
                        status="Sent",
                    )
                    imported += 1
                    self.row_done.emit(pdf_path, "ok", f"#{inv_num} — {customer_name}")
                except Exception as exc:
                    msg = f"{fname}: Save error — {exc}"
                    errors.append(msg)
                    self.row_done.emit(pdf_path, "error", msg)
        finally:
            conn.close()

        self.all_done.emit(imported, skipped, errors)

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

_QUEUE_SAVE_PATH = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "ProBooksAi" / "intake_queue.json"


def _load_queue_from_disk() -> list[dict]:
    """Load persisted intake queue rows from disk. Returns [] if missing or corrupt."""
    try:
        if _QUEUE_SAVE_PATH.exists():
            return json.loads(_QUEUE_SAVE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def _save_queue_to_disk(rows: list[dict]) -> None:
    """Persist the current queue rows to disk."""
    try:
        _QUEUE_SAVE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _QUEUE_SAVE_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

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
        self._restore_queue()
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

        self._btn_extract_all = QPushButton("⚡ Extract & Create Invoices")
        self._btn_extract_all.setToolTip(
            "Send all Staged PDFs to Claude AI, extract invoice data, "
            "and create invoice records (status: Sent)."
        )
        self._btn_extract_all.clicked.connect(self._on_extract_all)
        self._btn_extract_all.setStyleSheet(
            "QPushButton { background-color: #1a4b8b; color: #fff; "
            "border: 1px solid #2a6bd0; border-radius: 4px; padding: 4px 14px; font-weight: 700; }"
            "QPushButton:hover { background-color: #2255a0; }"
            "QPushButton:pressed { background-color: #143870; }"
            "QPushButton:disabled { background-color: #333; color: #666; border-color: #444; }"
        )
        # Keep a stub reference so existing code that checks _btn_extract_selected still works
        self._btn_extract_selected = self._btn_extract_all

        for b in (
            self._btn_pdf,
            self._btn_img,
            self._btn_paste,
            self._btn_remove,
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

    def _current_queue_rows(self) -> list[dict]:
        """Snapshot the table into a list of dicts for persistence."""
        rows = []
        for r in range(self._table.rowCount()):
            src_it = self._table.item(r, 0)
            kind_it = self._table.item(r, 1)
            date_it = self._table.item(r, 2)
            status_it = self._table.item(r, 3)
            notes_it = self._table.item(r, 4)
            if src_it is None:
                continue
            rows.append({
                "source": src_it.text(),
                "path": src_it.data(_ROLE_PATH) or "",
                "payload": src_it.data(_ROLE_TEXT_PAYLOAD) or "",
                "kind": kind_it.text() if kind_it else "",
                "date_added": date_it.text() if date_it else "",
                "status": status_it.text() if status_it else "Staged",
                "notes": notes_it.text() if notes_it else "",
            })
        return rows

    def _save_queue(self) -> None:
        _save_queue_to_disk(self._current_queue_rows())

    def _restore_queue(self) -> None:
        """Reload persisted queue rows from disk into the table."""
        rows = _load_queue_from_disk()
        for row in rows:
            r = self._table.rowCount()
            self._table.insertRow(r)
            s0 = _readonly_item(row.get("source", ""))
            p = row.get("path", "")
            payload = row.get("payload", "")
            if p:
                s0.setData(_ROLE_PATH, p)
            if payload:
                s0.setData(_ROLE_TEXT_PAYLOAD, payload)
            self._table.setItem(r, 0, s0)
            self._table.setItem(r, 1, _readonly_item(row.get("kind", "PDF")))
            self._table.setItem(r, 2, _readonly_item(row.get("date_added", _now_display())))
            status = row.get("status", "Staged")
            # Re-stage anything that was mid-extraction when app closed
            if status == "Extracting…":
                status = "Staged"
            self._table.setItem(r, 3, _editable_item(status))
            self._table.setItem(r, 4, _editable_item(row.get("notes", "")))

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
        self._save_queue()

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

    def _get_db_path(self) -> str:
        """Return the file path of the open company SQLite DB (empty string if unknown)."""
        import sqlite3 as _sql
        inv = self._invoice_screen
        if inv is None:
            return ""
        conn = getattr(inv, "_ap_conn", None)
        if conn is None:
            return ""
        try:
            for _seq, _name, fname in conn.execute("PRAGMA database_list").fetchall():
                if fname and str(fname) not in ("", ":memory:"):
                    return os.path.abspath(str(fname))
        except _sql.Error:
            pass
        return ""

    def _start_extraction(self, paths: list[str], row_map: dict[str, int]) -> None:
        """Kick off _ExtractWorker for *paths*; update table rows via signals (non-blocking)."""
        if self._invoice_screen is None:
            message_box_information_ok(self, "Not available", "Invoice screen is not connected.", ok_tip="Close.")
            return

        if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
            message_box_information_ok(
                self, "API key missing",
                "ANTHROPIC_API_KEY is not set.\n\n"
                "Add it to your .env file in the ProBooksAi folder:\n"
                "  ANTHROPIC_API_KEY=sk-ant-...\n\n"
                "Then restart the app.",
                ok_tip="Close.",
            )
            # Reset statuses back to Staged
            for r in row_map.values():
                it = self._table.item(r, 3)
                if it and it.text() == "Extracting…":
                    it.setText("Staged")
            return

        db_path = self._get_db_path()
        if not db_path:
            message_box_information_ok(self, "No company file", "Open a company file first (File → Open company…).", ok_tip="Close.")
            return

        if self._is_worker_busy():
            message_box_information_ok(self, "Busy", "Extraction already in progress — wait for it to finish.", ok_tip="Close.")
            return

        # Disable buttons while running
        self._btn_extract_selected.setEnabled(False)
        self._btn_extract_all.setEnabled(False)
        self._btn_extract_all.setText("Extracting…")

        worker = _ExtractWorker(db_path, paths)
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
            self._btn_extract_all.setText("⚡ Extract & Create Invoices")
            self._update_extract_button_state()
            self._btn_extract_all.setEnabled(True)
            self._save_queue()
            # Refresh the invoice browse queue and customer list on the main thread
            inv = self._invoice_screen
            if inv is not None and imported > 0:
                if hasattr(inv, "_refresh_browse_state"):
                    inv._refresh_browse_state()
                if hasattr(inv, "_sync_invoice_number_suggestion"):
                    inv._sync_invoice_number_suggestion()
                bp = getattr(inv, "_bill_customer_panel", None)
                if bp is not None and hasattr(bp, "reload_customers"):
                    bp.reload_customers()
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
        self._save_queue()
