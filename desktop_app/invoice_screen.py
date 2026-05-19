"""Invoice entry workflow screen — intake queue and Manual Invoice with live SQLite persistence; Bill To uses Customer Center data.

**Invoice Intake** (sub-tab): stage PDFs, images, and pasted text for future draft creation; **Manual Invoice** sub-tab saves to ``invoices`` / ``invoice_lines``.

Dark navy panel styling matches Customers / Vendors AR/AP master tabs. Line grid uses in-cell widgets
so editors stay inline (no multiline popup editors). Bill To is wired to
``probooksai.business`` customers when *ap_conn* is set (same source as Business → Customers).

**Invoice UI dialog policy (print / PDF / file picker)**

Modal UI for *this* workflow tab is allowed only from explicit header buttons:

- **Save** (``_btn_save``): persists to SQLite, then writes **PDF** to the folder from
  **Edit → Preferences → Invoice Options** (or a one-time folder prompt). No print dialog.
- **Export PDF…** (``_btn_export_pdf``): persists, then **Save file** dialog for a single ``.pdf`` path
  (does not change the preferences folder).
- **Print…** (``_btn_print``): ``sender()`` must be that button; ``_invoice_print_dialog_armed``
  gates ``QPrintDialog``. After save, print uses the **same HTML as PDF** (loaded from the saved invoice row).
  Uses the saved printer when set; otherwise ``QPrintDialog`` once (includes “Print to PDF” / virtual printers).

No other signal may trigger Save / Export / Print invoice output paths.
``desktop_app.invoice_pdf.invoice_html_string`` / ``save_invoice_pdf`` also serve tests and CLI.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
from typing import Optional

from PySide6.QtCore import QDate, QEvent, QObject, QSettings, Qt, QTimer
from PySide6.QtGui import QFont, QFontMetrics, QHideEvent, QShowEvent, QTextDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QFileDialog,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

_LOG = logging.getLogger(__name__)

from desktop_app.customer_bill_to_panel import (
    CustomerBillToPanel,
    build_customer_bill_to_panel,
)
from desktop_app.flexible_date import (
    attach_line_edit_us_date_normalization,
    format_iso_to_us_display,
    format_ymd_as_us,
    parse_flexible_date_to_ymd,
)
from desktop_app.invoice_preferences import (
    configure_printer_for_invoice_print,
    ensure_invoice_output_folder,
)
from desktop_app.invoice_intake_panel import InvoiceIntakePanel
from desktop_app.invoice_pdf import invoice_html_string, save_invoice_pdf
from desktop_app.qt_mnemonic import message_box_information_ok
from probooksai import business
from desktop_app.ar_customer_actions import (
    export_invoices_csv,
    open_new_ar_invoice_dialog,
)
from desktop_app.theme import (
    DISABLED_FG,
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
    WORKFLOW_STRIP_BTN_OUTLINE as _INV_STRIP_ACTION_BTN_OUTLINE,
    WORKFLOW_TEXT as _INV_TEXT,
)

# Dark navy workflow theme (aligned with Customers / Vendors AR/AP master tabs).
# Invoice # box: max width. Title uses same 20px weight as Pay Bills / Receive Payments.
_INVOICE_TOP_HEADER_FIELD_MAX_WIDTH_PX = 158
_INVOICE_TITLE_FONT_PX = 20
_INVOICE_NUMBER_FIELD_MAX_WIDTH_PX = int(round(_INVOICE_TOP_HEADER_FIELD_MAX_WIDTH_PX * 0.75))
_INVOICE_TOP_FOUR_FIELD_MIN_WIDTH_PX = 158
# Bill To: ~65% narrower than the old full-stretch right column; body ~20% taller than default (68px).
_INVOICE_BILL_TO_MAX_WIDTH_PX = int(round(_INVOICE_TOP_HEADER_FIELD_MAX_WIDTH_PX * 5 * 0.35))
_INVOICE_BILL_TO_TEXT_HEIGHT_PX = int(round(68 * 1.2))
_INVOICE_BILL_TO_COMBO_MIN_WIDTH_PX = 100
# Top four header line edits: ~half the Bill To multi-line body height, compact padding.
_INVOICE_TOP_FOUR_LINE_HEIGHT_PX = max(22, _INVOICE_BILL_TO_TEXT_HEIGHT_PX // 2)

# Top strip (four fields + Clear / Print / New Customer): one visual system (QB-style).
_TOP_STRIP_RADIUS_PX = 6
_TOP_STRIP_CAPTION_FONT_PX = 11
_TOP_STRIP_BODY_FONT_PX = 12
# Clear Fields / Save / Export PDF / Print / New Customer / Reverse / Forward — per-button outline on dark
# faces (not the outer panel). Same on all six.
_INV_STRIP_ACTION_BTN_BORDER_W = 4


def _top_strip_caption_line_height_px() -> int:
    f = QFont()
    f.setPixelSize(_TOP_STRIP_CAPTION_FONT_PX)
    return QFontMetrics(f).height()


def _top_strip_field_outer_height_px() -> int:
    """Outer height for framed field boxes and matching action buttons (caption + edit row)."""
    ch = _top_strip_caption_line_height_px()
    _mt, _mb = 3, 3
    _gap = 2
    return _mt + ch + _gap + _INVOICE_TOP_FOUR_LINE_HEIGHT_PX + _mb


def _top_strip_line_edit_qss() -> str:
    """Borderless edit inside the outer QFrame (single chrome ring)."""
    return (
        f"QLineEdit {{ background-color: {WORKFLOW_INPUT_BG}; border: none; color: {_INV_TEXT}; "
        f"font-size: {_TOP_STRIP_BODY_FONT_PX}px; padding: 1px 8px; }}"
    )


def _top_strip_action_button_qss() -> str:
    """Stylesheet for the six invoice header-row action buttons (Clear Fields … Forward)."""
    bw = _INV_STRIP_ACTION_BTN_BORDER_W
    bc = _INV_STRIP_ACTION_BTN_OUTLINE
    r = _TOP_STRIP_RADIUS_PX
    return (
        f"QPushButton {{ background-color: {WORKFLOW_CONTROL_FACE}; border: {bw}px solid {bc}; "
        f"border-radius: {r}px; color: {_INV_TEXT}; "
        f"font-size: {_TOP_STRIP_BODY_FONT_PX}px; padding: 0 12px; }}"
        f"QPushButton:hover {{ background-color: {WORKFLOW_CONTROL_HOVER}; border: {bw}px solid {bc}; "
        f"border-radius: {r}px; }}"
        f"QPushButton:pressed {{ background-color: {WORKFLOW_CONTROL_PRESSED}; border: {bw}px solid {bc}; "
        f"border-radius: {r}px; }}"
        f"QPushButton:disabled {{ color: {DISABLED_FG}; background-color: {WORKFLOW_CONTROL_FACE}; "
        f"border: {bw}px solid {bc}; border-radius: {r}px; }}"
    )


# When True, show **Ship To** next to **Bill To** in the invoice header (same layout as before).
# UI-only toggle for a future preference; no persistence yet.
_INVOICE_SHOW_SHIP_TO_UI = False

# Line grid: user-resizable row heights via vertical header; sensible startup defaults.
_INVOICE_LINE_ROW_MIN_HEIGHT_PX = 22
_INVOICE_LINE_ROW_DEFAULT_EXTRA_PX = 10
# Non-Total columns: minimum width while clamping (matches header minimumSectionSize).
_INVOICE_LINE_COL_MIN_OTHER_PX = 40

# Default pixel widths for each column (cols 0–5; col 6 Total fills remaining viewport).
# Order: Date, Code, Description, BOL#, Rate, Qty
_LINE_COL_DEFAULT_WIDTHS: tuple[int, ...] = (72, 72, 520, 100, 110, 100)

# QSettings value: comma-separated column widths (scoped by company file path).
# Bump suffix version to clear any previously saved widths and apply the new defaults.
_INVOICE_LINE_TABLE_WIDTHS_KEY_PREFIX = "invoice_workflow/line_table_column_widths_v2"


def _invoice_line_table_qsettings() -> QSettings:
    """Scoped like ``desktop_app.main`` ``main()`` (``setOrganizationName`` / ``setApplicationName``)."""
    return QSettings("ProBooks+ai", "ProBooks+ai")


def _safe_invoice_pdf_stem(invoice_number: str) -> str:
    """Single path segment for ``Invoice-<stem>.pdf`` (no slashes or Windows-forbidden chars)."""
    raw = (invoice_number or "").strip() or "invoice"
    forbidden = '<>:"/\\|?*\x00'
    cleaned = "".join(ch if ch not in forbidden and ord(ch) >= 32 else "_" for ch in raw)
    cleaned = cleaned.strip(" .") or "invoice"
    return cleaned[:120]


def _cell_line() -> QLineEdit:
    le = QLineEdit()
    le.setStyleSheet(
        f"QLineEdit {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_INV_GRID}; "
        f"padding: 2px 6px; color: {_INV_TEXT}; }}"
    )
    return le


def _qty_spin() -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(0.0, 999_999.99)
    s.setDecimals(2)
    s.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
    s.setStyleSheet(
        f"QDoubleSpinBox {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_INV_GRID}; "
        f"padding: 2px 6px; color: {_INV_TEXT}; }}"
    )
    return s


def _money_spin() -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(0.0, 999_999_999.99)
    s.setDecimals(2)
    s.setPrefix("$ ")
    s.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
    s.setStyleSheet(
        f"QDoubleSpinBox {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_INV_GRID}; "
        f"padding: 2px 6px; color: {_INV_TEXT}; }}"
    )
    return s


def _line_total_spin() -> QDoubleSpinBox:
    """Line **Total** column: derived from Rate × Qty (matches persisted ``invoice_lines.line_total``)."""
    s = _money_spin()
    s.setReadOnly(True)
    s.setToolTip("Rate × quantity — same value saved on the invoice line.")
    return s


def _find_or_create_customer(conn: sqlite3.Connection, name: str, address: str = "") -> int:
    """Return existing customer id by name (case-insensitive) or create a new one."""
    row = conn.execute(
        "SELECT id FROM customers WHERE LOWER(name) = LOWER(?) LIMIT 1", (name,)
    ).fetchone()
    if row:
        return int(row["id"])
    # Parse address — store in the single 'address' column
    lines = [ln.strip() for ln in (address or "").splitlines() if ln.strip()]
    addr = "\n".join(lines)
    cur = conn.execute(
        """INSERT INTO customers (name, address, created_at)
           VALUES (?, ?, datetime('now'))""",
        (name, addr),
    )
    conn.commit()
    return int(cur.lastrowid)


def _ai_extract_invoice(pdf_path: str) -> "dict | None":
    """Call Claude PDF vision to extract invoice fields. Thread-safe (no Qt, no shared DB).

    Returns a dict with invoice fields, or None on failure.
    Uses the standard messages API (no beta required for Claude 3.7+ / Claude 4).
    Falls back to the PDF beta for older Claude 3.5 models.
    Piggybacks on the ``intake_extract`` logger (already set up by the worker).
    """
    # stdlib imports — these always succeed
    import base64  # noqa: PLC0415
    import json  # noqa: PLC0415
    import logging as _logging  # noqa: PLC0415
    import re  # noqa: PLC0415
    import traceback  # noqa: PLC0415

    # Logger FIRST — before anything that might fail, so all errors are captured.
    _ai_log = _logging.getLogger("intake_extract")

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        _ai_log.error("_ai_extract_invoice: ANTHROPIC_API_KEY is empty — aborting")
        return None

    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")
    fname = os.path.basename(pdf_path)
    _ai_log.info(f"_ai_extract_invoice START: {fname}  model={model}")

    try:
        # anthropic import is inside try so ImportError is caught and logged
        import anthropic  # noqa: PLC0415

        with open(pdf_path, "rb") as f:
            raw_bytes = f.read()
        pdf_data = base64.standard_b64encode(raw_bytes).decode()
        _ai_log.info(f"PDF read OK: {len(raw_bytes):,} bytes → {len(pdf_data):,} base64 chars")

        # 120-second hard timeout — prevents the worker from hanging indefinitely
        # if the API server accepts the TCP connection but never sends a response.
        client = anthropic.Anthropic(api_key=api_key, timeout=120.0)

        prompt = """Extract the invoice data (NOT the Bill of Lading or other attachments — invoice only).
Return ONLY a valid JSON object with these exact keys:
{
  "invoice_number": "string",
  "invoice_date": "YYYY-MM-DD",
  "customer_name": "string (the BILL TO company name only, first line)",
  "customer_address": "string (full address, newline separated)",
  "po_contract": "string (PO/CONTRACT# value)",
  "name_job": "string (NAME/JOB# value)",
  "lines": [
    {
      "serviced_on": "MM/DD/YYYY",
      "jl_num": "string",
      "description": "string",
      "bol": "string",
      "qty": number,
      "rate": number,
      "amount": number
    }
  ],
  "total": number
}
Rules: Use empty string for missing fields. qty defaults to 1 if not shown. Only include invoice lines, not BOL/delivery-ticket rows."""

        content = [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_data}},
            {"type": "text", "text": prompt},
        ]

        # Try the standard API first (Claude 3.7+ and Claude 4 support PDFs natively).
        try:
            _ai_log.info("Calling messages.create (standard, no beta)…")
            response = client.messages.create(
                model=model,
                max_tokens=2048,
                messages=[{"role": "user", "content": content}],
            )
            _ai_log.info("Standard API call returned OK")
        except Exception as std_exc:
            _ai_log.warning(f"Standard API failed ({type(std_exc).__name__}: {std_exc}) — retrying with PDF beta…")
            # Fall back to the Claude 3.5 PDF beta for older installs.
            response = client.beta.messages.create(
                model=model,
                max_tokens=2048,
                messages=[{"role": "user", "content": content}],
                betas=["pdfs-2024-09-25"],
            )
            _ai_log.info("Beta API call returned OK")

        raw = response.content[0].text.strip()
        _ai_log.info(f"Raw AI response (first 300 chars): {raw[:300]}")
        raw = re.sub(r'^```[a-zA-Z]*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)
        result = json.loads(raw.strip())
        _ai_log.info(f"JSON parsed OK — inv={result.get('invoice_number')!r}  customer={result.get('customer_name')!r}")
        return result
    except Exception as exc:
        _ai_log.error(f"_ai_extract_invoice FAILED for {fname}: {type(exc).__name__}: {exc}\n{traceback.format_exc()}")
        return None


class InvoiceScreen(QWidget):
    """Manual Invoice: header, line grid, totals; persists to ``invoices`` / ``invoice_lines`` when connected."""

    _LINE_COLS = (
        "Serviced On",
        "JL #",
        "Description",
        "BOL#",
        "Rate",
        "Qty",
        "Amount",
    )
    _N_LINE_ROWS = 15

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        ap_conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        super().__init__(parent)
        self._ap_conn = ap_conn
        self._invoice_number_autofill_value = ""
        self._browse_ids: list[int] = []
        self._browse_index: int | None = None
        # ``None`` = new draft; when set, Save/Export/Print updates this invoice via ``business.update_invoice``.
        self._current_invoice_id: int | None = None
        self._current_status: str = "Open"
        # Block line grid valueChanged/textChanged while loading or clearing (avoids footer flicker).
        self._suppress_invoice_line_recalc: bool = False
        # Memo text from DB when loading (no longer a visible header box after removing blank field).
        self._invoice_memo_notes: str = ""
        # Set True only inside Print click handler while QPrintDialog may run (blocks stray callers).
        self._invoice_print_dialog_armed: bool = False
        self.setToolTip(
            "Manual Invoice: enter lines and totals; Save writes to your company file. "
            "Invoice # suggests the next number from your company file (editable). "
            "Bill To searches customers when connected. "
            "Same .db (File → Backup / Restore, probooks.backup)."
        )
        self._build_ui()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Keep Total column flush to the viewport right when the table is resized."""
        vp = getattr(self, "_invoice_lines_viewport", None)
        if vp is not None and watched is vp and event.type() == QEvent.Type.Resize:
            self._sync_invoice_line_total_column_width_safe()
        return super().eventFilter(watched, event)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if self._ap_conn is not None:
            self._bill_customer_panel.reload_customers()
        self._sync_invoice_number_suggestion()
        self._refresh_browse_state()
        self._update_new_customer_button_state()
        # After layout, anchor Total to the viewport right (width was 0 during build).
        QTimer.singleShot(0, self._sync_invoice_line_total_column_width_safe)

    def hideEvent(self, event: QHideEvent) -> None:
        tmr = getattr(self, "_line_widths_persist_timer", None)
        if tmr is not None and tmr.isActive():
            tmr.stop()
        # Flush debounced widths when leaving the tab (same pattern as Register header state).
        self._persist_invoice_line_column_widths()
        super().hideEvent(event)

    def _update_new_customer_button_state(self) -> None:
        on = self._ap_conn is not None
        self._btn_new_customer.setEnabled(on)
        self._btn_save.setEnabled(on)
        if getattr(self, "_btn_ar_new_inv", None) is not None:
            self._sync_ar_toolbar_enabled()

    def _sync_invoice_number_suggestion(self) -> None:
        """Set invoice # to the next system suggestion unless the user overrode it (new drafts only)."""
        if self._current_invoice_id is not None:
            return
        sug = business.next_default_invoice_number(self._ap_conn)
        cur = self._inv_number.text().strip()
        if cur == "" or cur == self._invoice_number_autofill_value:
            self._inv_number.setText(sug)
        self._invoice_number_autofill_value = sug

    def bill_to_customer_panel(self) -> CustomerBillToPanel:
        return self._bill_customer_panel

    def selected_bill_to_customer_id(self) -> Optional[int]:
        return self._bill_customer_panel.selected_customer_id()

    def prefill_from_document(self, data: dict) -> None:
        """Pre-fill header fields from AI-extracted document data (skips blank values)."""
        from desktop_app.flexible_date import format_ymd_as_us
        inv_num = (data.get("invoice_number") or "").strip()
        if inv_num:
            self._inv_number.setText(inv_num)
            self._invoice_number_autofill_value = inv_num
        iso_date = (data.get("doc_date") or "").strip()
        if iso_date:
            try:
                y, m, d = (int(p) for p in iso_date.split("-"))
                self._date.setText(format_ymd_as_us(m, d, y))
            except (ValueError, AttributeError):
                pass

    def _line_edit_header_style(self) -> str:
        return (
            f"QLineEdit {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_INV_GRID}; "
            f"padding: 4px 8px; color: {_INV_TEXT}; }}"
        )

    def _header_field_box(
        self,
        caption: str,
        editor: QWidget,
        *,
        max_width_px: Optional[int] = None,
        min_width_px: Optional[int] = None,
        left_align: bool = False,
        compact_vertical: bool = False,
        unified_top_strip: bool = False,
    ) -> QFrame:
        """Single header cell: optional caption above control (QuickBooks-style compact box)."""
        fr = QFrame()
        fr.setStyleSheet(
            f"QFrame {{ background-color: {_INV_PANEL}; border: 1px solid {_INV_GRID}; "
            f"border-radius: {_TOP_STRIP_RADIUS_PX}px; }}"
        )
        if min_width_px is not None:
            fr.setMinimumWidth(min_width_px)
        if max_width_px is not None:
            fr.setMaximumWidth(max_width_px)
            fr.setSizePolicy(
                QSizePolicy.Policy.Maximum,
                QSizePolicy.Policy.Preferred,
            )
        lay = QVBoxLayout(fr)
        if compact_vertical:
            lay.setContentsMargins(6, 3, 6, 3)
            lay.setSpacing(2)
        else:
            lay.setContentsMargins(8, 6, 8, 6)
            lay.setSpacing(4)
        if left_align:
            lay.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        if caption:
            cap = QLabel(caption)
            cap.setStyleSheet(
                f"color: {_INV_CAPTION}; font-size: {_TOP_STRIP_CAPTION_FONT_PX}px; "
                "background: transparent;"
            )
            if left_align:
                cap.setAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
                cap.setWordWrap(True)
                lay.addWidget(cap, alignment=Qt.AlignmentFlag.AlignLeft)
            else:
                lay.addWidget(cap)
        elif unified_top_strip and compact_vertical:
            ph = QLabel()
            ph.setFixedHeight(_top_strip_caption_line_height_px())
            ph.setStyleSheet("background: transparent;")
            lay.addWidget(ph, alignment=Qt.AlignmentFlag.AlignLeft)
        if left_align:
            lay.addWidget(editor, alignment=Qt.AlignmentFlag.AlignLeft)
        else:
            lay.addWidget(editor)
        if left_align:
            if isinstance(editor, QLineEdit):
                editor.setAlignment(Qt.AlignmentFlag.AlignLeft)
        if compact_vertical and isinstance(editor, QLineEdit):
            editor.setFixedHeight(_INVOICE_TOP_FOUR_LINE_HEIGHT_PX)
            if unified_top_strip:
                editor.setStyleSheet(_top_strip_line_edit_qss())
        if unified_top_strip and compact_vertical:
            fr.setFixedHeight(_top_strip_field_outer_height_px())
            fr.setSizePolicy(
                QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Fixed,
            )
        return fr

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 8)
        outer.setSpacing(0)

        self._invoice_tabs = QTabWidget(self)
        self._invoice_tabs.setObjectName("invoiceModuleTabs")
        self._invoice_tabs.setToolTip(
            "Manual Invoice: full entry workflow. Invoice Intake: stage documents for future drafting."
        )

        self._btn_ar_new_inv = QPushButton("New invoice (AR)…")
        self._btn_ar_new_inv.setToolTip(
            "Create an invoice using the AR dialog (moved from the Customers tab)."
        )
        self._btn_ar_new_inv.clicked.connect(self._on_ar_new_invoice_dialog)
        self._btn_ar_export_inv = QPushButton("Export invoices CSV…")
        self._btn_ar_export_inv.setToolTip(
            "Export invoice headers to CSV (UTF-8 BOM for Excel)."
        )
        self._btn_ar_export_inv.clicked.connect(self._on_ar_export_invoices_csv)
        for b in (self._btn_ar_new_inv, self._btn_ar_export_inv):
            b.setAutoDefault(False)
            b.setDefault(False)

        _ar_corner = QWidget(self._invoice_tabs)
        _ar_corner_lay = QHBoxLayout(_ar_corner)
        _ar_corner_lay.setContentsMargins(0, 0, 6, 0)
        _ar_corner_lay.setSpacing(6)
        _ar_corner_lay.addWidget(self._btn_ar_new_inv)
        _ar_corner_lay.addWidget(self._btn_ar_export_inv)
        self._invoice_tabs.setCornerWidget(_ar_corner, Qt.Corner.TopRightCorner)
        self._invoice_tabs.tabBar().setExpanding(False)
        self._invoice_tabs.setStyleSheet(
            f"QTabWidget#invoiceModuleTabs::pane {{ border: none; margin: 0; padding: 0; }}"
            f"QTabWidget#invoiceModuleTabs QTabBar::tab {{ padding: 3px 10px; min-height: 20px; }}"
        )

        self._sync_ar_toolbar_enabled()

        page = QFrame()
        page.setObjectName("invoiceLightPanel")
        page.setStyleSheet(
            f"QFrame#invoiceLightPanel {{ background-color: {_INV_BG}; border: 1px solid {_INV_GRID}; "
            "border-radius: 8px; }}"
        )
        play = QVBoxLayout(page)
        play.setContentsMargins(12, 10, 12, 12)
        play.setSpacing(8)

        # ── Title row (Pay Bills / Receive Payments style: title left, key field right) ──
        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        title = QLabel("Invoice")
        title.setStyleSheet(
            f"font-size: {_INVOICE_TITLE_FONT_PX}px; font-weight: 600; color: {_INV_TEXT}; background: transparent;"
        )
        title_row.addWidget(title)
        title_row.addStretch(1)
        self._inv_number = QLineEdit()
        self._inv_number.setPlaceholderText("INVOICE #")
        self._inv_number.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._inv_number.setStyleSheet(self._line_edit_header_style())
        inv_number_box = self._header_field_box(
            "",
            self._inv_number,
            max_width_px=_INVOICE_NUMBER_FIELD_MAX_WIDTH_PX,
            left_align=True,
        )
        title_row.addWidget(inv_number_box, 0, Qt.AlignmentFlag.AlignRight)
        play.addLayout(title_row)

        bill_panel, bill_te = build_customer_bill_to_panel(
            self,
            ap_conn=self._ap_conn,
            layout_max_width_px=_INVOICE_BILL_TO_MAX_WIDTH_PX,
            bill_plain_height_px=_INVOICE_BILL_TO_TEXT_HEIGHT_PX,
            combo_min_width_px=_INVOICE_BILL_TO_COMBO_MIN_WIDTH_PX,
            show_new_customer_button=False,
        )
        self._bill_customer_panel = bill_panel
        self._bill_to = (bill_panel, bill_te)
        if _INVOICE_SHOW_SHIP_TO_UI:
            self._ship_to = self._address_box("Ship To")
        else:
            self._ship_to = None

        # ── Header: Invoice Date / PO / Job + Bill To; buttons evenly spread under the three fields. ──
        top_fields_row = QHBoxLayout()
        top_fields_row.setSpacing(10)

        self._date = QLineEdit()
        qd = QDate.currentDate()
        self._date.setText(format_ymd_as_us(qd.month(), qd.day(), qd.year()))
        self._date.setPlaceholderText("MM/DD/YYYY")
        attach_line_edit_us_date_normalization(self._date)

        self._po = QLineEdit()

        self._job = QLineEdit()

        _top_three_kw = dict(
            min_width_px=_INVOICE_TOP_FOUR_FIELD_MIN_WIDTH_PX,
            max_width_px=None,
            left_align=True,
            compact_vertical=True,
            unified_top_strip=True,
        )

        three_col = QWidget()
        three_lay = QVBoxLayout(three_col)
        three_lay.setContentsMargins(0, 0, 0, 0)
        three_lay.setSpacing(8)
        fields_h = QHBoxLayout()
        fields_h.setSpacing(10)
        fields_h.addWidget(
            self._header_field_box("Invoice Date", self._date, **_top_three_kw),
            0,
        )
        fields_h.addWidget(
            self._header_field_box("PO/Contract #", self._po, **_top_three_kw),
            0,
        )
        fields_h.addWidget(
            self._header_field_box("Name/Job #", self._job, **_top_three_kw),
            0,
        )
        three_lay.addLayout(fields_h)

        self._status_badge = QLabel("Open")
        self._status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_badge.setFixedHeight(24)
        self._status_badge.setMinimumWidth(80)
        self._status_badge.setStyleSheet(
            "background:#1a6b1a; color:#fff; border-radius:4px; font-weight:700; font-size:9pt; padding:2px 10px;"
        )

        btns_h = QHBoxLayout()
        btns_h.setContentsMargins(0, 0, 0, 0)
        btns_h.setSpacing(8)
        self._btn_clear_fields = QPushButton("Clear Fields")
        self._btn_clear_fields.setToolTip(
            "Clear lines and header fields except Invoice #; set Invoice Date to today."
        )
        self._btn_print = QPushButton("Print…")
        self._btn_print.setToolTip(
            "Save this invoice to the company file, then print using the default printer from "
            "Edit → Preferences → Invoice Options (or pick a printer once if unset). "
            "After a successful print, the form resets for the next invoice."
        )
        self._btn_new_customer = QPushButton("New Customer")
        self._btn_new_customer.setToolTip(
            "Add a customer to the company file when no match exists; Bill To fills automatically."
        )
        self._btn_import_pdf = QPushButton("Import PDF…")
        self._btn_import_pdf.setToolTip(
            "Import one or more invoice PDFs created in another system. Claude AI reads each PDF "
            "and creates matching invoice records (status: Sent). Customers are created automatically if not found."
        )
        self._btn_save = QPushButton("Save")
        self._btn_save.setToolTip(
            "Save this invoice to the company file and write a PDF to the folder set under "
            "Edit → Preferences → Invoice Options (you can choose the folder once if unset). "
            "Then start a new blank invoice with the next number."
        )
        self._btn_export_pdf = QPushButton("Export PDF…")
        self._btn_export_pdf.setToolTip(
            "Save this invoice to the company file, then pick a PDF file path (one-time). "
            "Does not change the default folder used by Save. Then start a new blank invoice."
        )
        self._btn_reverse = QPushButton("◄  Prev")
        self._btn_forward = QPushButton("Next  ►")
        self._btn_reverse.setToolTip(
            "Open the previous saved invoice. Keyboard: left-arrow when focus is in the header."
        )
        self._btn_forward.setToolTip(
            "Open the next saved invoice, or a new blank draft after the last one."
        )
        _strip_h = _top_strip_field_outer_height_px()
        _strip_btn_ss = _top_strip_action_button_qss()
        for b in (
            self._btn_clear_fields,
            self._btn_import_pdf,
            self._btn_save,
            self._btn_export_pdf,
            self._btn_print,
            self._btn_new_customer,
            self._btn_reverse,
            self._btn_forward,
        ):
            b.setStyleSheet(_strip_btn_ss)
            b.setFixedHeight(_strip_h)
            # MinimumExpanding + equal stretch shares width evenly under the three field boxes.
            b.setSizePolicy(
                QSizePolicy.Policy.MinimumExpanding,
                QSizePolicy.Policy.Fixed,
            )
            # Fix stray Save/Print validation popups: never treat these as dialog default
            # buttons (Return/Enter from table/header editors must not fire clicked).
            b.setAutoDefault(False)
            b.setDefault(False)
        btns_h.insertWidget(0, self._status_badge)
        for b in (
            self._btn_clear_fields,
            self._btn_import_pdf,
            self._btn_save,
            self._btn_export_pdf,
            self._btn_print,
            self._btn_new_customer,
            self._btn_reverse,
            self._btn_forward,
        ):
            btns_h.addWidget(b, 1)
        three_lay.addLayout(btns_h)

        top_fields_row.addWidget(three_col, 0, Qt.AlignmentFlag.AlignTop)
        top_fields_row.addStretch(1)

        bill_col = QWidget()
        bill_lay = QVBoxLayout(bill_col)
        bill_lay.setContentsMargins(0, 0, 0, 0)
        bill_lay.setSpacing(8)
        bill_lay.addWidget(self._bill_to[0], 0, Qt.AlignmentFlag.AlignTop)
        top_fields_row.addWidget(bill_col, 0, Qt.AlignmentFlag.AlignTop)
        if _INVOICE_SHOW_SHIP_TO_UI and self._ship_to is not None:
            top_fields_row.addWidget(self._ship_to[0], 0, Qt.AlignmentFlag.AlignTop)

        header_band = QFrame()
        header_band.setObjectName("invoiceHeaderBand")
        header_band.setStyleSheet(
            f"QFrame#invoiceHeaderBand {{ background-color: {_INV_PANEL}; "
            f"border: 1px solid {_INV_GRID}; border-radius: 8px; }}"
        )
        hb_lay = QVBoxLayout(header_band)
        hb_lay.setContentsMargins(10, 8, 10, 10)
        hb_lay.setSpacing(8)
        hb_lay.addLayout(top_fields_row)
        play.addWidget(header_band)

        # Save/Print: only clicked → persistence; UniqueConnection prevents duplicate slots.
        _uc = Qt.ConnectionType.UniqueConnection
        self._btn_save.clicked.connect(self._on_save_invoice, _uc)
        self._btn_export_pdf.clicked.connect(self._on_export_pdf_as, _uc)
        self._btn_print.clicked.connect(self._on_print_invoice, _uc)
        self._btn_clear_fields.clicked.connect(self._on_clear_fields, _uc)
        self._btn_import_pdf.clicked.connect(self._on_import_pdf_invoices, _uc)
        self._btn_new_customer.clicked.connect(
            self._bill_customer_panel.open_new_customer_dialog, _uc
        )
        self._btn_reverse.clicked.connect(self._on_reverse_invoice, _uc)
        self._btn_forward.clicked.connect(self._on_forward_invoice, _uc)

        self._update_new_customer_button_state()

        self._sync_invoice_number_suggestion()

        line_sec = QLabel("Line items")
        line_sec.setStyleSheet(
            f"color: {_INV_CAPTION}; font-size: 11px; font-weight: 600; "
            "letter-spacing: 0.03em; background: transparent;"
        )
        line_sec.setToolTip("Service lines; amounts roll into subtotal, tax, and total below.")
        play.addWidget(line_sec)

        # ── Line items grid ──
        self._table = QTableWidget(self._N_LINE_ROWS, len(self._LINE_COLS))
        self._table.setObjectName("invoiceLinesTable")
        self._table.setHorizontalHeaderLabels(self._LINE_COLS)
        for _ci in range(len(self._LINE_COLS)):
            _hi = self._table.horizontalHeaderItem(_ci)
            if _hi is not None:
                _hi.setTextAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
        _hh = self._table.horizontalHeader()
        _hh.setCascadingSectionResizes(False)
        _hh.setSectionsMovable(False)
        # Total width is set in code so its right edge stays on the viewport (no Qt stretch).
        _hh.setStretchLastSection(False)
        for _ci in range(len(self._LINE_COLS)):
            _hh.setSectionResizeMode(_ci, QHeaderView.ResizeMode.Interactive)
        _hh.setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        _hh.setTextElideMode(Qt.TextElideMode.ElideRight)
        _fm = _hh.fontMetrics()
        self._invoice_col_mins = tuple(
            _fm.horizontalAdvance(str(lbl)) + 28 for lbl in self._LINE_COLS
        )
        _hh.setMinimumSectionSize(max(1, min(self._invoice_col_mins)))
        self._table.setCornerButtonEnabled(False)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        self._table.setStyleSheet(
            f"QTableWidget#invoiceLinesTable {{"
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
            " text-align: left;"
            " }}"
        )

        for row in range(self._N_LINE_ROWS):
            dt = _cell_line()
            dt.setPlaceholderText("Date")
            self._table.setCellWidget(row, 0, dt)

            code = _cell_line()
            code.setPlaceholderText("Code")
            self._table.setCellWidget(row, 1, code)

            desc = _cell_line()
            desc.setPlaceholderText("Description")
            self._table.setCellWidget(row, 2, desc)

            bol = _cell_line()
            bol.setPlaceholderText("BOL#")
            self._table.setCellWidget(row, 3, bol)

            rate = _money_spin()
            rate.setValue(0.0)
            self._table.setCellWidget(row, 4, rate)

            qty = _qty_spin()
            qty.setValue(0.0)
            self._table.setCellWidget(row, 5, qty)

            total = _line_total_spin()
            total.setValue(0.0)
            self._table.setCellWidget(row, 6, total)

        self._wire_invoice_line_recalc()

        # Column widths: apply fixed defaults (Date/Code narrow, Description wide, BOL#/Rate/Qty fixed).
        # QSettings saved widths (from a previous session) override these on _restore_invoice_line_column_widths().
        _hh.blockSignals(True)
        try:
            for _ci, _w in enumerate(_LINE_COL_DEFAULT_WIDTHS):
                self._table.setColumnWidth(_ci, _w)
        finally:
            _hh.blockSignals(False)
        self._invoice_table_resizing = False
        self._line_widths_persist_timer: QTimer | None = None
        self._invoice_lines_viewport = self._table.viewport()
        self._invoice_lines_viewport.installEventFilter(self)
        if not self._restore_invoice_line_column_widths():
            self._invoice_table_resizing = True
            _hh.blockSignals(True)
            try:
                self._sync_invoice_line_total_column_width_inner()
            finally:
                _hh.blockSignals(False)
                self._invoice_table_resizing = False
        _hh.sectionResized.connect(self._on_invoice_line_header_section_resized)

        # Row heights: thin vertical gutter (no row numbers) with interactive resize between rows.
        _vh = self._table.verticalHeader()
        _vh.setVisible(True)
        _vh.setSectionsClickable(False)
        _vh.setFixedWidth(14)
        _vh.setDefaultAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        for r in range(self._N_LINE_ROWS):
            _vhi = QTableWidgetItem("")
            _vhi.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._table.setVerticalHeaderItem(r, _vhi)
        _default_row_h = max(
            _INVOICE_LINE_ROW_MIN_HEIGHT_PX + 4,
            self._table.fontMetrics().height() + _INVOICE_LINE_ROW_DEFAULT_EXTRA_PX,
        )
        _vh.setDefaultSectionSize(_default_row_h)
        _vh.setMinimumSectionSize(_INVOICE_LINE_ROW_MIN_HEIGHT_PX)
        _vh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        play.addWidget(self._table, 1)

        # ── Totals ──
        tot_frame = QFrame()
        tot_frame.setStyleSheet(
            f"background-color: {_INV_PANEL}; border: 1px solid {_INV_GRID}; border-radius: 6px;"
        )
        tot = QHBoxLayout(tot_frame)
        tot.setContentsMargins(14, 10, 14, 10)
        tot.addStretch(1)
        tot_col = QVBoxLayout()
        tot_col.setSpacing(4)
        self._lbl_sub = QLabel("Subtotal: $0.00")
        self._lbl_tax = QLabel("Tax: $0.00")
        self._lbl_total = QLabel("Total: $0.00")
        for lb in (self._lbl_sub, self._lbl_tax, self._lbl_total):
            lb.setStyleSheet(f"color: {_INV_TEXT}; font-size: 13px;")
            lb.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._lbl_total.setStyleSheet(
            f"color: {_INV_TEXT}; font-size: 15px; font-weight: 600;"
        )
        tot_col.addWidget(self._lbl_sub)
        tot_col.addWidget(self._lbl_tax)
        tot_col.addWidget(self._lbl_total)
        tot.addLayout(tot_col)
        play.addWidget(tot_frame)

        self._invoice_intake = InvoiceIntakePanel(self._invoice_tabs, invoice_screen=self)
        self._invoice_tabs.addTab(page, "Manual Invoice")
        self._invoice_tabs.addTab(self._invoice_intake, "Invoice Intake")
        self._invoice_tabs.setCurrentIndex(0)
        outer.addWidget(self._invoice_tabs, 1)

        self._refresh_browse_state()

    def open_invoice_by_id(self, invoice_id: int) -> bool:
        """Load an invoice into the Manual Invoice sub-tab (register / in-app navigation)."""
        if self._ap_conn is None:
            message_box_information_ok(
                self,
                "Invoice",
                "Open a company file to edit invoices.",
                ok_tip="Close; use File → Open company… then try the link again.",
            )
            return False
        iid = int(invoice_id)
        inv, _ln = business.get_invoice_detail(self._ap_conn, iid)
        if inv is None:
            message_box_information_ok(
                self,
                "Invoice",
                f"Invoice #{iid} was not found.",
                ok_tip="Close; refresh the register or company data and try again.",
            )
            return False
        self._invoice_tabs.setCurrentIndex(0)
        self._load_invoice_into_form(iid)
        self._bill_customer_panel.reload_customers()
        self._sync_invoice_number_suggestion()
        self._refresh_browse_state()
        try:
            self._browse_index = self._browse_ids.index(iid)
        except ValueError:
            self._browse_index = None
        self._update_browse_buttons()
        return True

    def _sync_ar_toolbar_enabled(self) -> None:
        on = self._ap_conn is not None
        self._btn_ar_new_inv.setEnabled(on)
        self._btn_ar_export_inv.setEnabled(on)

    def _on_ar_new_invoice_dialog(self) -> None:
        if self._ap_conn is None:
            return

        def _after() -> None:
            self._bill_customer_panel.reload_customers()
            self._sync_invoice_number_suggestion()

        open_new_ar_invoice_dialog(self, self._ap_conn, after_save=_after)

    def _on_ar_export_invoices_csv(self) -> None:
        if self._ap_conn is None:
            return
        export_invoices_csv(self, self._ap_conn)

    def _invoice_col_minimum_width(self, col: int) -> int:
        """Minimum width from header label metrics (+ section padding)."""
        mins = getattr(self, "_invoice_col_mins", None)
        if mins is None or col < 0 or col >= len(mins):
            return _INVOICE_LINE_COL_MIN_OTHER_PX
        return int(mins[col])

    def _invoice_line_widths_settings_key(self) -> str:
        """Scope prefs per company file (same idea as Register header state).

        Prefer the open SQLite file path from ``ap_conn`` (works before main window
        writes ``company_database_path`` to QSettings). Fall back to QSettings.
        """
        path = ""
        conn = self._ap_conn
        if conn is not None:
            try:
                for _seq, _name, fname in conn.execute("PRAGMA database_list").fetchall():
                    if fname and str(fname) not in ("", ":memory:"):
                        path = os.path.normcase(
                            os.path.normpath(os.path.abspath(str(fname)))
                        )
                        break
            except sqlite3.Error:
                path = ""
        if not path:
            qs = (
                _invoice_line_table_qsettings().value("company_database_path", "", type=str)
                or ""
            )
            if qs:
                path = os.path.normcase(os.path.normpath(os.path.abspath(qs)))
        if not path:
            sid = "default"
        else:
            sid = hashlib.sha256(path.encode("utf-8", errors="replace")).hexdigest()[:16]
        return f"{_INVOICE_LINE_TABLE_WIDTHS_KEY_PREFIX}_{sid}"

    def _persist_invoice_line_column_widths(self) -> None:
        t = getattr(self, "_table", None)
        if t is None:
            return
        n = t.columnCount()
        if n <= 0:
            return
        parts = [str(max(1, t.columnWidth(i))) for i in range(n)]
        _invoice_line_table_qsettings().setValue(
            self._invoice_line_widths_settings_key(), ",".join(parts)
        )

    def _schedule_persist_invoice_line_column_widths(self) -> None:
        if getattr(self, "_line_widths_persist_timer", None) is None:
            self._line_widths_persist_timer = QTimer(self)
            self._line_widths_persist_timer.setSingleShot(True)
            self._line_widths_persist_timer.timeout.connect(
                self._persist_invoice_line_column_widths
            )
        self._line_widths_persist_timer.stop()
        self._line_widths_persist_timer.start(250)

    def _restore_invoice_line_column_widths(self) -> bool:
        """Restore saved widths for all columns except the last; Total fills the viewport right edge.

        The last column width in settings is ignored — it is always recomputed from the viewport
        so the Total header stays anchored to the table's right side.
        """
        t = getattr(self, "_table", None)
        if t is None:
            return False
        raw = _invoice_line_table_qsettings().value(
            self._invoice_line_widths_settings_key(), ""
        )
        s = str(raw or "").strip()
        if not s:
            return False
        try:
            parts = [int(x.strip()) for x in s.split(",") if x.strip()]
        except ValueError:
            return False
        n = t.columnCount()
        if len(parts) != n:
            return False
        self._invoice_table_resizing = True
        hh = t.horizontalHeader()
        hh.blockSignals(True)
        try:
            for i in range(n - 1):
                m = self._invoice_col_minimum_width(i)
                t.setColumnWidth(i, max(m, parts[i]))
            self._sync_invoice_line_total_column_width_inner()
        finally:
            hh.blockSignals(False)
            self._invoice_table_resizing = False
        return True

    def _sync_invoice_line_total_column_width_inner(self) -> None:
        """Set Total column width so its right edge meets the viewport (>= header minimum).

        Caller should block horizontal header signals and set ``_invoice_table_resizing`` when needed
        to avoid re-entrancy from ``sectionResized``.
        """
        t = getattr(self, "_table", None)
        if t is None:
            return
        n = t.columnCount()
        if n < 1:
            return
        last = n - 1
        vw = max(0, t.viewport().width())
        sum_others = sum(t.columnWidth(i) for i in range(last))
        min_last = self._invoice_col_minimum_width(last)
        w_last = max(min_last, vw - sum_others)
        t.setColumnWidth(last, int(w_last))

    def _sync_invoice_line_total_column_width_safe(self) -> None:
        """Re-anchor Total after show/layout (debounced from ``showEvent``)."""
        if getattr(self, "_invoice_table_resizing", False):
            return
        t = getattr(self, "_table", None)
        if t is None:
            return
        self._invoice_table_resizing = True
        hh = t.horizontalHeader()
        hh.blockSignals(True)
        try:
            self._sync_invoice_line_total_column_width_inner()
        finally:
            hh.blockSignals(False)
            self._invoice_table_resizing = False
        self._schedule_persist_invoice_line_column_widths()

    def _on_invoice_line_header_section_resized(
        self, logical_index: int, old_size: int, new_size: int
    ) -> None:
        """Resize only the section the user dragged; Total column fills the rest (right edge fixed).

        No pair/cascade: neighbors are not adjusted except Total, which always absorbs slack so the
        last column stays flush to the viewport right. Dragging the outer edge of Total is ignored
        (sync overwrites with viewport-derived width).
        """
        del old_size  # Qt provides it; pair-resize logic no longer uses it.
        if getattr(self, "_invoice_table_resizing", False):
            return
        t = getattr(self, "_table", None)
        if t is None:
            return
        n = t.columnCount()
        if n < 2:
            return
        last = n - 1

        self._invoice_table_resizing = True
        hh = t.horizontalHeader()
        hh.blockSignals(True)
        try:
            if logical_index < last:
                m = self._invoice_col_minimum_width(logical_index)
                t.setColumnWidth(logical_index, max(m, int(new_size)))
            # Resizing Total (last) via its right edge: do not honor — keep right glued to viewport.
            self._sync_invoice_line_total_column_width_inner()
        finally:
            hh.blockSignals(False)
            self._invoice_table_resizing = False
        self._schedule_persist_invoice_line_column_widths()

    def _refresh_browse_state(self) -> None:
        if self._ap_conn is None:
            self._browse_ids = []
        else:
            self._browse_ids = business.list_invoice_ids_chronological(self._ap_conn)
        if self._browse_index is not None and (
            self._browse_index < 0 or self._browse_index >= len(self._browse_ids)
        ):
            self._browse_index = None
        self._update_browse_buttons()

    def _update_browse_buttons(self) -> None:
        has_db = self._ap_conn is not None
        has_any = bool(self._browse_ids)
        idx = self._browse_index
        n = len(self._browse_ids)
        # Prev: disabled when no invoices or already at the first one
        can_prev = has_db and has_any and (idx is None or idx > 0)
        # Next: always enabled when there are invoices (wraps to new draft at end)
        can_next = has_db and has_any
        self._btn_reverse.setEnabled(can_prev)
        self._btn_forward.setEnabled(can_next)
        # Show position in tooltip when browsing a saved invoice
        if has_any and idx is not None:
            pos = f"{idx + 1} / {n}"
            self._btn_reverse.setToolTip(f"← Previous invoice  ({pos})")
            self._btn_forward.setToolTip(
                f"Next invoice →  ({pos})"
                if idx < n - 1
                else f"New blank draft  ({pos} — at last)"
            )
        else:
            self._btn_reverse.setToolTip("Open the previous saved invoice.")
            self._btn_forward.setToolTip(
                "Open the next saved invoice, or a new blank draft after the last one."
            )

    def _clear_line_grid(self) -> None:
        self._suppress_invoice_line_recalc = True
        try:
            for r in range(self._N_LINE_ROWS):
                for c in range(len(self._LINE_COLS)):
                    w = self._table.cellWidget(r, c)
                    if isinstance(w, QLineEdit):
                        w.clear()
                    elif isinstance(w, QDoubleSpinBox):
                        w.setValue(0.0)
        finally:
            self._suppress_invoice_line_recalc = False
        self._recalc_invoice_footer_from_grid()

    def _set_totals_labels(self, subtotal: float, tax: float, total: float) -> None:
        self._lbl_sub.setText(f"Subtotal: ${subtotal:,.2f}")
        self._lbl_tax.setText(f"Tax: ${tax:,.2f}")
        self._lbl_total.setText(f"Total: ${total:,.2f}")

    def _invoice_tax_rate_pct(self) -> float:
        """Company default sales tax % (Business hub Tax %); used for Save totals and live footer."""
        conn = self._ap_conn
        if conn is None:
            return 0.0
        raw = business.get_setting(conn, "default_tax_rate_pct", "0") or "0"
        try:
            return float(raw)
        except ValueError:
            return 0.0

    def _wire_invoice_line_recalc(self) -> None:
        """Keep line Totals and footer Subtotal/Tax/Total aligned with Rate×Qty and :meth:`_collect_invoice_lines`."""
        for row in range(self._N_LINE_ROWS):
            rate_w = self._table.cellWidget(row, 4)
            qty_w = self._table.cellWidget(row, 5)
            if isinstance(rate_w, QDoubleSpinBox):
                rate_w.valueChanged.connect(
                    lambda _v, r=row: self._on_invoice_line_rate_qty_changed(r)
                )
            if isinstance(qty_w, QDoubleSpinBox):
                qty_w.valueChanged.connect(
                    lambda _v, r=row: self._on_invoice_line_rate_qty_changed(r)
                )
            for col in range(4):
                w = self._table.cellWidget(row, col)
                if isinstance(w, QLineEdit):
                    w.textChanged.connect(
                        lambda _t, r=row: self._on_invoice_line_text_changed(r)
                    )

    def _on_invoice_line_rate_qty_changed(self, row: int) -> None:
        if self._suppress_invoice_line_recalc:
            return
        self._sync_invoice_line_row_total(row)
        self._recalc_invoice_footer_from_grid()

    def _on_invoice_line_text_changed(self, _row: int) -> None:
        if self._suppress_invoice_line_recalc:
            return
        self._recalc_invoice_footer_from_grid()

    def _sync_invoice_line_row_total(self, row: int) -> None:
        if row < 0 or row >= self._N_LINE_ROWS:
            return
        rate_w = self._table.cellWidget(row, 4)
        qty_w = self._table.cellWidget(row, 5)
        tot_w = self._table.cellWidget(row, 6)
        if not isinstance(rate_w, QDoubleSpinBox) or not isinstance(qty_w, QDoubleSpinBox):
            return
        if not isinstance(tot_w, QDoubleSpinBox):
            return
        lt = round(float(rate_w.value()) * float(qty_w.value()), 2)
        tot_w.blockSignals(True)
        tot_w.setValue(lt)
        tot_w.blockSignals(False)

    def _recalc_invoice_footer_from_grid(self) -> None:
        """Subtotal/tax/total from current lines + default tax % (matches :func:`business.create_invoice`)."""
        if self._suppress_invoice_line_recalc:
            return
        lines = self._collect_invoice_lines()
        sub = 0.0
        for ln in lines:
            sub += round(float(ln.get("qty", 0.0)) * float(ln.get("rate", 0.0)), 2)
        tax_pct = self._invoice_tax_rate_pct()
        tax = round(sub * (tax_pct / 100.0), 2) if tax_pct else 0.0
        total = round(sub + tax, 2)
        self._set_totals_labels(sub, tax, total)

    def _update_status_badge(self, status: str) -> None:
        self._current_status = status
        self._status_badge.setText(status or "Open")
        colors = {
            "Open":   "#1a6b1a",
            "Sent":   "#1a4b8b",
            "Paid":   "#555",
            "Unpaid": "#8b1a1a",
        }
        bg = colors.get(status, "#555")
        self._status_badge.setStyleSheet(
            f"background:{bg}; color:#fff; border-radius:4px; "
            "font-weight:700; font-size:9pt; padding:2px 10px;"
        )

    def _on_clear_fields(self) -> None:
        self._current_invoice_id = None
        self._browse_index = None
        self._update_status_badge("Open")
        qd = QDate.currentDate()
        self._date.setText(format_ymd_as_us(qd.month(), qd.day(), qd.year()))
        self._po.clear()
        self._job.clear()
        self._invoice_memo_notes = ""
        self._bill_customer_panel.clear_bill_to()
        self._clear_line_grid()
        self._update_browse_buttons()

    def _go_to_new_invoice_draft(self) -> None:
        self._current_invoice_id = None
        self._browse_index = None
        self._update_status_badge("Open")
        self._po.clear()
        self._job.clear()
        self._invoice_memo_notes = ""
        self._bill_customer_panel.clear_bill_to()
        self._clear_line_grid()
        self._inv_number.clear()
        self._invoice_number_autofill_value = ""
        qd = QDate.currentDate()
        self._date.setText(format_ymd_as_us(qd.month(), qd.day(), qd.year()))
        self._sync_invoice_number_suggestion()
        self._update_browse_buttons()

    def _load_invoice_by_list_index(self, list_index: int) -> None:
        if not self._browse_ids or list_index < 0 or list_index >= len(self._browse_ids):
            return
        self._load_invoice_into_form(self._browse_ids[list_index])
        self._browse_index = list_index
        self._update_browse_buttons()

    def _load_invoice_into_form(self, invoice_id: int) -> None:
        if self._ap_conn is None:
            return
        inv, lines = business.get_invoice_detail(self._ap_conn, invoice_id)
        if inv is None:
            return
        d = dict(inv)
        num = (d.get("invoice_number") or "").strip()
        self._inv_number.setText(num)
        self._invoice_number_autofill_value = num
        iso = (d.get("invoice_date") or "").strip()
        self._date.setText(format_iso_to_us_display(iso) if iso else "")
        po, job, memo_rest = self._split_memo_po_job((d.get("memo") or "").strip())
        self._po.setText(po)
        self._job.setText(job)
        self._invoice_memo_notes = memo_rest
        self._bill_customer_panel.reload_customers()
        try:
            cid = int(d["customer_id"])
        except (KeyError, TypeError, ValueError):
            self._bill_customer_panel.clear_bill_to()
        else:
            self._bill_customer_panel.select_customer_by_id(cid)
        self._clear_line_grid()
        self._suppress_invoice_line_recalc = True
        try:
            for i, ln in enumerate(lines):
                if i >= self._N_LINE_ROWS:
                    break
                row = dict(ln)
                dt_w = self._table.cellWidget(i, 0)
                code_w = self._table.cellWidget(i, 1)
                desc_w = self._table.cellWidget(i, 2)
                bol_w = self._table.cellWidget(i, 3)
                rate_w = self._table.cellWidget(i, 4)
                qty_w = self._table.cellWidget(i, 5)
                raw_desc = (row.get("description") or "").strip()
                if isinstance(dt_w, QLineEdit):
                    dt_w.clear()
                if isinstance(code_w, QLineEdit):
                    code_w.clear()
                if isinstance(bol_w, QLineEdit):
                    bol_w.clear()
                if isinstance(desc_w, QLineEdit):
                    desc_w.clear()
                if raw_desc and " — " in raw_desc:
                    parts = [p.strip() for p in raw_desc.split(" — ")]
                    if len(parts) == 2 and isinstance(dt_w, QLineEdit) and isinstance(
                        code_w, QLineEdit
                    ):
                        dt_w.setText(parts[0])
                        code_w.setText(parts[1])
                    elif len(parts) == 3:
                        if isinstance(dt_w, QLineEdit):
                            dt_w.setText(parts[0])
                        if isinstance(code_w, QLineEdit):
                            code_w.setText(parts[1])
                        if isinstance(desc_w, QLineEdit):
                            desc_w.setText(parts[2])
                    elif len(parts) >= 4:
                        if isinstance(dt_w, QLineEdit):
                            dt_w.setText(parts[0])
                        if isinstance(code_w, QLineEdit):
                            code_w.setText(parts[1])
                        if isinstance(desc_w, QLineEdit):
                            desc_w.setText(parts[2])
                        if isinstance(bol_w, QLineEdit):
                            bol_w.setText(parts[3])
                elif isinstance(desc_w, QLineEdit):
                    desc_w.setText(raw_desc)
                if isinstance(rate_w, QDoubleSpinBox):
                    rate_w.setValue(float(row.get("rate") or 0.0))
                if isinstance(qty_w, QDoubleSpinBox):
                    qty_w.setValue(float(row.get("qty") or 0.0))
        finally:
            self._suppress_invoice_line_recalc = False
        for r in range(self._N_LINE_ROWS):
            self._sync_invoice_line_row_total(r)
        self._recalc_invoice_footer_from_grid()
        self._current_invoice_id = invoice_id
        self._update_status_badge(d.get("status") or "Open")

    def _split_memo_po_job(self, memo: str) -> tuple[str, str, str]:
        """Split stored memo into PO, Job, and remaining free text (matches :meth:`_build_invoice_memo`)."""
        po, job = "", ""
        extra: list[str] = []
        for raw in (memo or "").split("\n"):
            line = raw.strip()
            if not line:
                continue
            low = line.lower()
            if low.startswith("po:"):
                po = line.split(":", 1)[1].strip()
            elif low.startswith("job:"):
                job = line.split(":", 1)[1].strip()
            else:
                extra.append(raw)
        return po, job, "\n".join(extra).strip()

    def _on_reverse_invoice(self) -> None:
        self._refresh_browse_state()
        if not self._browse_ids:
            return
        if self._browse_index is None:
            self._load_invoice_by_list_index(len(self._browse_ids) - 1)
            return
        if self._browse_index <= 0:
            return
        self._load_invoice_by_list_index(self._browse_index - 1)

    def _on_forward_invoice(self) -> None:
        self._refresh_browse_state()
        if not self._browse_ids:
            return
        if self._browse_index is None:
            self._load_invoice_by_list_index(0)
            return
        if self._browse_index >= len(self._browse_ids) - 1:
            self._go_to_new_invoice_draft()
            return
        self._load_invoice_by_list_index(self._browse_index + 1)

    def _build_invoice_memo(self) -> str:
        parts: list[str] = []
        po = self._po.text().strip()
        job = self._job.text().strip()
        if po:
            parts.append(f"PO: {po}")
        if job:
            parts.append(f"Job: {job}")
        extra = (self._invoice_memo_notes or "").strip()
        if extra:
            parts.append(extra)
        return "\n".join(parts)

    def _collect_invoice_lines(self) -> list[dict]:
        rows: list[dict] = []
        for r in range(self._N_LINE_ROWS):
            dt_w = self._table.cellWidget(r, 0)
            code_w = self._table.cellWidget(r, 1)
            desc_w = self._table.cellWidget(r, 2)
            bol_w = self._table.cellWidget(r, 3)
            rate_w = self._table.cellWidget(r, 4)
            qty_w = self._table.cellWidget(r, 5)
            line_date = dt_w.text().strip() if isinstance(dt_w, QLineEdit) else ""
            code = code_w.text().strip() if isinstance(code_w, QLineEdit) else ""
            desc = desc_w.text().strip() if isinstance(desc_w, QLineEdit) else ""
            bol = bol_w.text().strip() if isinstance(bol_w, QLineEdit) else ""
            rate = float(rate_w.value()) if isinstance(rate_w, QDoubleSpinBox) else 0.0
            qty = float(qty_w.value()) if isinstance(qty_w, QDoubleSpinBox) else 0.0
            if (
                not desc
                and qty == 0.0
                and rate == 0.0
                and not line_date
                and not code
                and not bol
            ):
                continue
            parts_ln: list[str] = []
            if line_date:
                parts_ln.append(line_date)
            if code:
                parts_ln.append(code)
            if desc:
                parts_ln.append(desc)
            if bol:
                parts_ln.append(bol)
            line_desc = " — ".join(parts_ln) if parts_ln else " "
            rows.append(
                {
                    "description": line_desc,
                    "qty": qty,
                    "rate": rate,
                }
            )
        return rows

    def _invoice_feedback_message(self, msg: str) -> None:
        """Non-modal save/print validation feedback (replaces QMessageBox — avoids interrupting typing).

        Modal warnings were mistaken for “random save popups” when Return/Space briefly
        activated a header button. Persistence still runs only from Save/Print; this only
        reports validation/soft errors without grabbing focus.
        """
        if not (msg or "").strip():
            return
        _LOG.info("Invoice (no modal): %s", msg.strip())
        w: QWidget | None = self
        while w is not None:
            if isinstance(w, QMainWindow):
                sb = w.statusBar()
                if sb is not None:
                    sb.showMessage(msg.strip(), 8000)
                    return
            w = w.parentWidget()

    @staticmethod
    def _line_extended_amount(ln: dict) -> float:
        return round(float(ln.get("qty", 0.0)) * float(ln.get("rate", 0.0)), 2)

    def _invoice_line_validation_error(self, lines: list[dict]) -> str | None:
        """Return a user-facing message if lines are not pilot-ready, else ``None``."""
        if not lines:
            return (
                "Add at least one invoice line with a non-zero dollar amount before saving, printing, "
                "or exporting PDF. Set Rate and Quantity on a line so the line total is not $0.00."
            )
        if not any(abs(self._line_extended_amount(ln)) >= 0.01 for ln in lines):
            return (
                "At least one invoice line must have a non-zero amount. Enter Rate and Quantity "
                "(or adjust lines that show $0.00) before saving, printing, or exporting PDF."
            )
        return None

    def _try_persist_invoice(self) -> tuple[bool, str, int | None]:
        """Create or update the current invoice row. Returns ``(ok, message, invoice_id)``.

        Silent DB only — no PDF or print UI here. Call only from Save/Print click paths.
        """
        if self._ap_conn is None:
            return (
                False,
                "Open a company file (File → Open company…) before saving, printing, or exporting PDF.",
                None,
            )
        cid = self.selected_bill_to_customer_id()
        if cid is None:
            return (
                False,
                "Select a customer in Bill To before saving, printing, or exporting PDF.",
                None,
            )
        num = self._inv_number.text().strip()
        if not num:
            return False, "Enter an invoice number before saving, printing, or exporting PDF.", None
        ymd = parse_flexible_date_to_ymd(self._date.text().strip())
        if ymd is None:
            return (
                False,
                "Enter a valid invoice date (for example MM/DD/YYYY) before saving, printing, or exporting PDF.",
                None,
            )
        y, m, d = ymd
        iso_date = f"{y:04d}-{m:02d}-{d:02d}"
        memo = self._build_invoice_memo()
        lines = self._collect_invoice_lines()
        line_err = self._invoice_line_validation_error(lines)
        if line_err is not None:
            return False, line_err, None
        conn = self._ap_conn
        edit_id = self._current_invoice_id
        tax_pct = self._invoice_tax_rate_pct()
        try:
            if edit_id is not None:
                due_s = ""
                row = conn.execute(
                    "SELECT due_date FROM invoices WHERE id = ?", (edit_id,)
                ).fetchone()
                if row is not None and (row["due_date"] or "").strip():
                    due_s = (row["due_date"] or "").strip()[:10]
                business.update_invoice(
                    conn,
                    edit_id,
                    cid,
                    num,
                    iso_date,
                    due_date=due_s,
                    memo=memo,
                    lines=lines,
                    tax_rate_pct=tax_pct,
                )
                return True, "", edit_id
            inv_id = business.create_invoice(
                conn,
                cid,
                num,
                iso_date,
                due_date="",
                memo=memo,
                lines=lines,
                tax_rate_pct=tax_pct,
            )
        except ValueError as exc:
            return False, str(exc), None
        except sqlite3.IntegrityError as exc:
            err = str(exc).upper()
            if "UNIQUE" in err:
                return (
                    False,
                    "That invoice number is already in use. Enter a different invoice number.",
                    None,
                )
            _LOG.warning("Invoice save integrity error: %s", exc)
            return (
                False,
                "Could not save the invoice (data conflict). Check the invoice number and try again.",
                None,
            )
        except sqlite3.Error as exc:
            _LOG.warning("Invoice save database error: %s", exc)
            return (
                False,
                "Could not save the invoice to the company file. Check that the file is writable and not locked.",
                None,
            )
        return True, "", inv_id

    def _save_invoice_data_only(self) -> tuple[bool, str, int | None]:
        """Write current invoice to SQLite only; never opens print/PDF/file dialogs."""
        return self._try_persist_invoice()

    def _on_save_invoice(self) -> None:
        # Phantom dialog fix: only a real Save button click may persist from this slot
        # (sender None is rejected — avoids queued/spurious clicked without a mouse/keyboard source).
        if self.sender() is not self._btn_save:
            return
        folder = ensure_invoice_output_folder(self)
        if folder is None:
            return
        was_new = self._current_invoice_id is None
        ok, msg, inv_id = self._save_invoice_data_only()
        if not ok:
            self._invoice_feedback_message(msg)
            return
        assert inv_id is not None and self._ap_conn is not None
        num = self._inv_number.text().strip()
        pdf_name = f"Invoice-{_safe_invoice_pdf_stem(num)}.pdf"
        pdf_path = os.path.join(folder, pdf_name)
        try:
            save_invoice_pdf(self._ap_conn, inv_id, pdf_path)
        except OSError as exc:
            self._invoice_feedback_message(
                f"Invoice was saved, but the PDF could not be written ({exc}). "
                "Check folder permissions and disk space."
            )
        except Exception as exc:  # noqa: BLE001
            self._invoice_feedback_message(
                f"Invoice was saved, but building the PDF failed: {exc}"
            )
        self._refresh_browse_state()
        if was_new:
            self._go_to_new_invoice_draft()
        else:
            self._load_invoice_into_form(inv_id)

    def _on_export_pdf_as(self) -> None:
        if self.sender() is not self._btn_export_pdf:
            return
        if self._ap_conn is None:
            self._invoice_feedback_message(
                "Open a company file before exporting PDF (File → Open company…)."
            )
            return
        was_new = self._current_invoice_id is None
        ok, msg, inv_id = self._save_invoice_data_only()
        if not ok:
            self._invoice_feedback_message(msg)
            return
        assert inv_id is not None
        num = self._inv_number.text().strip()
        default_name = f"Invoice-{_safe_invoice_pdf_stem(num)}.pdf"
        path, _filt = QFileDialog.getSaveFileName(
            self,
            "Export invoice as PDF",
            default_name,
            "PDF files (*.pdf);;All files (*.*)",
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path = f"{path}.pdf"
        try:
            save_invoice_pdf(self._ap_conn, inv_id, path)
        except OSError as exc:
            self._invoice_feedback_message(
                f"Invoice was saved, but the PDF could not be written ({exc}). "
                "Check folder permissions and disk space."
            )
            return
        except Exception as exc:  # noqa: BLE001
            self._invoice_feedback_message(
                f"Invoice was saved, but building the PDF failed: {exc}"
            )
            return
        self._refresh_browse_state()
        if was_new:
            self._go_to_new_invoice_draft()
        else:
            self._load_invoice_into_form(inv_id)

    def _run_invoice_print_dialog(self, inv_id: int, *, advance_after: bool = True) -> None:
        """Print saved invoice HTML when ``_invoice_print_dialog_armed``; same template as PDF."""
        if not self._invoice_print_dialog_armed:
            return
        if self._ap_conn is None:
            return
        doc = QTextDocument()
        try:
            doc.setHtml(invoice_html_string(self._ap_conn, inv_id))
        except Exception as exc:  # noqa: BLE001 — show any render issue
            self._invoice_feedback_message(
                f"Could not prepare the invoice for printing. Save succeeded; fix data or try again. ({exc})"
            )
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        if not configure_printer_for_invoice_print(self, printer):
            return
        doc.print_(printer)
        self._refresh_browse_state()
        if advance_after:
            self._go_to_new_invoice_draft()
        else:
            self._load_invoice_into_form(inv_id)

    def _on_print_invoice(self) -> None:
        # Phantom dialog fix: require explicit Print button as sender, then arm gate for dialog code only.
        if self.sender() is not self._btn_print:
            return
        if self._ap_conn is None:
            self._invoice_feedback_message(
                "Open a company file before printing (File → Open company…)."
            )
            return
        was_new = self._current_invoice_id is None
        self._invoice_print_dialog_armed = True
        try:
            ok, msg, inv_id = self._save_invoice_data_only()
            if not ok:
                self._invoice_feedback_message(msg)
                return
            assert inv_id is not None
            self._run_invoice_print_dialog(inv_id, advance_after=was_new)
        finally:
            self._invoice_print_dialog_armed = False

    def _address_box(self, caption: str) -> tuple[QFrame, QPlainTextEdit]:
        fr = QFrame()
        fr.setStyleSheet(
            f"QFrame {{ background-color: {_INV_PANEL}; border: 1px solid {_INV_GRID}; "
            "border-radius: 6px; }}"
        )
        lay = QVBoxLayout(fr)
        lay.setContentsMargins(8, 6, 8, 8)
        lay.setSpacing(4)
        cap = QLabel(caption)
        cap.setStyleSheet(f"color: {_INV_TEXT}; font-size: 12px; font-weight: 600;")
        te = QPlainTextEdit()
        te.setPlaceholderText(caption)
        te.setFixedHeight(68)
        te.setStyleSheet(
            f"QPlainTextEdit {{ background: {_INV_PANEL}; color: {_INV_TEXT}; "
            f"border: 1px solid {_INV_GRID}; border-radius: 4px; padding: 4px; }}"
        )
        lay.addWidget(cap)
        lay.addWidget(te)
        return fr, te

    # ── PDF import (AI-powered) ──────────────────────────────────────────────

    def _extract_invoice_from_pdf(self, pdf_path: str) -> dict | None:
        """Delegate to module-level helper (safe to call from main thread or worker)."""
        return _ai_extract_invoice(pdf_path)

    def import_pdf_paths(
        self,
        paths: list[str],
        *,
        on_row_done: "Optional[callable]" = None,
    ) -> dict:
        """Extract and import a list of invoice PDF paths via Claude AI.

        Parameters
        ----------
        paths:
            Absolute paths to PDF files.
        on_row_done:
            Optional callback called after each file with
            ``(path, "ok"|"skip"|"error", message)``.

        Returns
        -------
        dict with keys ``imported``, ``skipped``, ``errors`` (list of str).
        """
        if self._ap_conn is None:
            return {"imported": 0, "skipped": 0, "errors": ["Not connected — open a company file first."]}

        imported = 0
        skipped = 0
        errors: list[str] = []

        for pdf_path in paths:
            fname = os.path.basename(pdf_path)
            data = self._extract_invoice_from_pdf(pdf_path)
            if not data:
                msg = f"{fname}: Could not extract (check ANTHROPIC_API_KEY)"
                errors.append(msg)
                if on_row_done:
                    on_row_done(pdf_path, "error", msg)
                continue

            inv_num = (data.get("invoice_number") or "").strip()
            inv_date = (data.get("invoice_date") or "").strip()
            customer_name = (data.get("customer_name") or "").strip()
            po = (data.get("po_contract") or "").strip()
            name_job = (data.get("name_job") or "").strip()
            total = float(data.get("total") or 0.0)

            if not customer_name:
                msg = f"{fname}: No customer name found"
                errors.append(msg)
                if on_row_done:
                    on_row_done(pdf_path, "error", msg)
                continue

            try:
                customer_id = _find_or_create_customer(
                    self._ap_conn, customer_name, data.get("customer_address", "")
                )
            except Exception as exc:
                msg = f"{fname}: Customer error — {exc}"
                errors.append(msg)
                if on_row_done:
                    on_row_done(pdf_path, "error", msg)
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
                existing = self._ap_conn.execute(
                    "SELECT id FROM invoices WHERE invoice_number = ?", (inv_num,)
                ).fetchone()
                if existing:
                    skipped += 1
                    if on_row_done:
                        on_row_done(pdf_path, "skip", f"{fname}: duplicate #{inv_num}")
                    continue

                business.create_invoice(
                    self._ap_conn,
                    customer_id=customer_id,
                    invoice_number=inv_num,
                    invoice_date=inv_date,
                    memo=memo,
                    lines=inv_lines,
                    status="Sent",
                )
                imported += 1
                if on_row_done:
                    on_row_done(pdf_path, "ok", f"#{inv_num} — {customer_name}")
            except Exception as exc:
                msg = f"{fname}: Save error — {exc}"
                errors.append(msg)
                if on_row_done:
                    on_row_done(pdf_path, "error", msg)

        if imported > 0:
            self._sync_invoice_number_suggestion()
            self._refresh_browse_state()
            self._bill_customer_panel.reload_customers()

        return {"imported": imported, "skipped": skipped, "errors": errors}

    def _on_import_pdf_invoices(self) -> None:
        if self._ap_conn is None:
            message_box_information_ok(self, "Not connected", "Open a company file first.", ok_tip="Close.")
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Import Invoice PDFs", "", "PDF files (*.pdf);;All files (*.*)")
        if not paths:
            return

        result = self.import_pdf_paths(paths)
        imported = result["imported"]
        skipped = result["skipped"]
        errors = result["errors"]

        lines_msg = [f"Imported: {imported}", f"Skipped (duplicates): {skipped}"]
        if errors:
            lines_msg.append(f"Errors: {len(errors)}")
            lines_msg.extend(f"  {e}" for e in errors[:5])
        message_box_information_ok(
            self, "Import complete",
            "\n".join(lines_msg),
            ok_tip="Close; review the Invoices list.",
        )
