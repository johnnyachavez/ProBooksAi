"""Invoice entry workflow screen — Create Invoices (QuickBooks Pro Desktop mimic) + Invoice Intake.

**Create Invoices** (sub-tab): header matches QB Pro (Customer:Job, Bill To | Ship To, Date /
Invoice # / Terms / Due Date / P.O. Number) with live SQLite persistence. **Invoice Intake**
stages PDFs, images, pasted text, and dispatch CSV; **Send to Manual Invoice** opens a new
draft (memo + banner, or full line items from dispatch).

Create Invoices follows QuickBooks Pro Desktop: **Customer:Job** at the top, **Bill To** from the
selected customer, editable **Ship To** saved on the invoice (defaults to Bill To when
the customer has no separate shipping address), auto-sequenced editable invoice #,
``QDateEdit`` invoice date, terms-driven due date, and line **Amount** (qty × rate).

Line grid uses in-cell widgets so editors stay inline (no multiline popup editors). Bill To is
wired to ``probooksai.business`` customers when *ap_conn* is set (same source as Business → Customers).

**Invoice UI dialog policy (print / PDF / file picker)**

Modal UI for *this* workflow tab is allowed only from explicit header buttons:

- **Save & New** (``_btn_save``): persists to SQLite first, then writes **PDF** to the folder from
  **Edit → Preferences → Invoice Options** when that folder is set (or after a one-time pick).
  If no PDF folder is chosen, the invoice is still saved to the company database. Then starts a
  blank invoice (QuickBooks **Save & New**). No print dialog.
- **Save & Close** (``_btn_save_close``): same persist + optional PDF, then stays on the saved
  invoice (tab analog of QuickBooks **Save & Close** — the form is not a floating window).
- **Clear** (``_btn_clear_fields``) / **New**: if the form is dirty, asks **Save invoice ###?** first.
- **Save As** (``_btn_export_pdf``): persists, then a Save dialog with an editable file name
  (default ``8114.pdf``). The folder is shown by the dialog, not in the name box. Remembers
  the last folder per company on this PC. Asks before overwrite.
- Leaving the Invoice tab, or Previous / Next / Find onto another invoice, asks
  **Save invoice ###?** Yes (company file + PDF if a folder is already set) / No (discard
  and leave) / Cancel or **X** (stay; keep the data; do not save or wipe).
- **Print…** (``_btn_print``): ``sender()`` must be that button; ``_invoice_print_dialog_armed``
  gates ``QPrintDialog``. After save, print uses the **same HTML as PDF** (loaded from the saved invoice row).
  Uses the saved printer when set; otherwise ``QPrintDialog`` once (includes “Print to PDF” / virtual printers).

No other signal may trigger Save / Export / Print invoice output paths except the leave-tab prompt.
``desktop_app.invoice_pdf.invoice_html_string`` / ``save_invoice_pdf`` also serve tests and CLI.
Company identity from ``company_settings`` appears above the Create Invoices title and in PDF/print HTML.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
from functools import partial
from typing import Optional

from PySide6.QtCore import QDate, QEvent, QObject, QStringListModel, QSettings, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontMetrics, QHideEvent, QPalette, QShowEvent, QTextDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QComboBox,
    QCompleter,
    QDateEdit,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
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
    configure_qdate_edit_us,
    format_iso_to_us_display,
    parse_flexible_date_to_ymd,
)
from desktop_app.find_matchers import first_matching_row
from desktop_app.invoice_preferences import (
    configure_printer_for_invoice_print,
    ensure_invoice_output_folder,
    get_invoice_output_folder,
    prompt_invoice_save_as_path,
)
from desktop_app.invoice_print_html import parse_invoice_line_description
from desktop_app.invoice_intake_panel import InvoiceIntakePanel
from desktop_app.invoice_intake_text_extract import TextIntakeExtraction
from desktop_app.invoice_pdf import invoice_html_string, save_invoice_pdf
from desktop_app.qt_mnemonic import (
    message_box_information_ok,
    message_box_question_yes_no,
    message_box_question_yes_no_cancel,
    message_box_warning_ok,
)
from probooksai import business
from probooksai.company_identity import company_identity_plain_block
from probooksai.dispatch_intake import (
    DispatchInvoiceDraft,
    job_billing_rule,
    match_named_entity_id,
)
from desktop_app.ar_customer_actions import (
    export_invoices_csv,
    open_new_ar_invoice_dialog,
)
from desktop_app.theme import DISABLED_FG

# QuickBooks Pro Desktop mimic: light paper, compact chrome so the line grid dominates.
_INV_CANVAS   = "#E8ECF1"   # gray surround behind the form
_INV_BG       = "#FFFFFF"   # invoice paper
_INV_PANEL    = "#F4F7FA"   # header band
_INV_STRIPE   = "#D0E6F4"   # QB light-blue alternating rows
_INV_CAPTION  = "#4A5560"   # muted field captions (dark text on white — not a redaction bar)
_INV_GRID     = "#C0C8D0"   # hairlines / borders
_INV_HEADER   = "#D8DEE6"   # table header fill
_INV_TEXT     = "#1A1A1A"   # primary text on light
_INV_ACCENT   = "#2563A8"   # Save & New (QB primary action, slightly cleaner blue)
WORKFLOW_INPUT_BG = "#FFFFFF"
WORKFLOW_CONTROL_FACE = "#F7F8FA"
WORKFLOW_CONTROL_HOVER = "#E4EEF7"
WORKFLOW_CONTROL_PRESSED = "#C9D8EC"
_INV_STRIP_ACTION_BTN_OUTLINE = "#B4BCC6"

# Create Invoices window title on the form is "Invoice"; the module window is Create Invoices.
_INVOICE_TOP_HEADER_FIELD_MAX_WIDTH_PX = 158
_INVOICE_TITLE_FONT_PX = 26
_INVOICE_NUMBER_FIELD_MAX_WIDTH_PX = int(round(_INVOICE_TOP_HEADER_FIELD_MAX_WIDTH_PX * 0.75))
_INVOICE_TOP_FOUR_FIELD_MIN_WIDTH_PX = 110
# Modest address boxes so the line grid keeps the vertical space (QB Pro proportions).
_INVOICE_BILL_TO_MAX_WIDTH_PX = int(round(_INVOICE_TOP_HEADER_FIELD_MAX_WIDTH_PX * 5 * 0.35))
_INVOICE_BILL_TO_TEXT_HEIGHT_PX = 52
_INVOICE_BILL_TO_COMBO_MIN_WIDTH_PX = 200
_RIBBON_BTN_HEIGHT_PX = 22
_FOOTER_BTN_HEIGHT_PX = 24
_RIBBON_MAX_HEIGHT_PX = 50
# DESCRIPTION (index 2) is 0 here = stretch to leftover width (~40%).
_INVOICE_LINE_COL_DEFAULT_PX = (88, 64, 0, 64, 76, 76, 84)
# Never a live-company name. Company files may store their own template label.
_DEFAULT_INVOICE_TEMPLATE = "Standard Invoice"
_DEFAULT_AR_ACCOUNT = "Accounts Receivable"
_CUSTOMER_MESSAGE_CHOICES = (
    "",
    "Thank you for your business.",
    "Please remit payment upon receipt.",
)
# Top four header line edits: ~half the Bill To multi-line body height, compact padding.
_INVOICE_TOP_FOUR_LINE_HEIGHT_PX = 26

# Top strip (four fields + Clear / Print / New Customer): one visual system (QB-style).
_TOP_STRIP_RADIUS_PX = 6
_TOP_STRIP_CAPTION_FONT_PX = 11
_TOP_STRIP_BODY_FONT_PX = 12
# Clear Fields / Save / Save As / Print / New Customer / Reverse / Forward — per-button outline on dark
# faces (not the outer panel). Same on all six.
_INV_STRIP_ACTION_BTN_BORDER_W = 1


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


def _top_strip_date_edit_qss() -> str:
    """Borderless ``QDateEdit`` inside the outer QFrame (single chrome ring)."""
    return (
        f"QDateEdit {{ background-color: {WORKFLOW_INPUT_BG}; border: none; color: {_INV_TEXT}; "
        f"font-size: {_TOP_STRIP_BODY_FONT_PX}px; padding: 1px 8px; }}"
    )


def _top_strip_combo_qss() -> str:
    """Borderless ``QComboBox`` inside the outer QFrame (single chrome ring)."""
    return (
        f"QComboBox {{ background-color: {WORKFLOW_INPUT_BG}; border: none; color: {_INV_TEXT}; "
        f"font-size: {_TOP_STRIP_BODY_FONT_PX}px; padding: 1px 8px; }}"
    )


def _top_strip_action_button_qss(*, primary: bool = False) -> str:
    """Stylesheet for Create Invoices ribbon / footer buttons."""
    bw = _INV_STRIP_ACTION_BTN_BORDER_W
    bc = _INV_STRIP_ACTION_BTN_OUTLINE
    r = _TOP_STRIP_RADIUS_PX
    if primary:
        return (
            f"QPushButton {{ background-color: {_INV_ACCENT}; border: {bw}px solid {_INV_ACCENT}; "
            f"border-radius: {r}px; color: #FFFFFF; "
            f"font-size: {_TOP_STRIP_BODY_FONT_PX}px; padding: 0 14px; font-weight: 600; }}"
            f"QPushButton:hover {{ background-color: #1D4F8C; border: {bw}px solid #1D4F8C; }}"
            f"QPushButton:pressed {{ background-color: #163E6E; }}"
            f"QPushButton:disabled {{ color: #D7E3F0; background-color: #8AA7C7; "
            f"border: {bw}px solid #8AA7C7; }}"
        )
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


# Line grid: user-resizable row heights via vertical header; compact so many rows show.
_INVOICE_LINE_ROW_MIN_HEIGHT_PX = 22
_INVOICE_LINE_ROW_DEFAULT_EXTRA_PX = 4
# Non-Total columns: minimum width while clamping (matches header minimumSectionSize).
_INVOICE_LINE_COL_MIN_OTHER_PX = 24

# QSettings value: comma-separated column widths (scoped by company file path).
_INVOICE_LINE_TABLE_WIDTHS_KEY_PREFIX = "invoice_workflow/line_table_column_widths_v1"


def _light_form_palette() -> QPalette:
    """Light QB-style palette so unnamed QWidget wraps are not navy slabs from the app theme."""
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(_INV_BG))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(_INV_TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(WORKFLOW_INPUT_BG))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(_INV_STRIPE))
    pal.setColor(QPalette.ColorRole.Text, QColor(_INV_TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(WORKFLOW_CONTROL_FACE))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(_INV_TEXT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(_INV_ACCENT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(_INV_CAPTION))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(_INV_PANEL))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(_INV_TEXT))
    return pal


def _invoice_line_table_qsettings() -> QSettings:
    """Scoped like ``desktop_app.main`` ``main()`` (``setOrganizationName`` / ``setApplicationName``)."""
    return QSettings("ProBooks+ai", "ProBooks+ai")


def _safe_invoice_pdf_stem(invoice_number: str) -> str:
    """Single path segment for ``<stem>.pdf`` (no slashes or Windows-forbidden chars)."""
    raw = (invoice_number or "").strip() or "invoice"
    forbidden = '<>:"/\\|?*\x00'
    cleaned = "".join(ch if ch not in forbidden and ord(ch) >= 32 else "_" for ch in raw)
    cleaned = cleaned.strip(" .") or "invoice"
    return cleaned[:120]


def invoice_pdf_basename(invoice_number: str) -> str:
    """PDF file name is the invoice number, e.g. ``8114.pdf``."""
    return f"{_safe_invoice_pdf_stem(invoice_number)}.pdf"


def _cell_line() -> QLineEdit:
    le = QLineEdit()
    le.setStyleSheet(
        f"QLineEdit {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_INV_GRID}; "
        f"padding: 1px 4px; color: {_INV_TEXT}; }}"
    )
    return le


class _InvoiceCodeLineEdit(QLineEdit):
    """Manual Invoice line **Code** field: ``QLineEdit`` that opens its completer popup on focus/click.

    Behaves as a dropdown + type-ahead picker backed by the saved **Codes** table:

    * Clicking or focusing the cell shows the full saved-Codes list (when a completer is attached).
    * Typing narrows the popup live (case-insensitive prefix match via the attached
      :class:`PySide6.QtWidgets.QCompleter`).
    * ``isinstance(widget, QLineEdit)`` stays true so existing save/load paths keep using ``.text()``.
    """

    def _show_invoice_code_completer_popup(self) -> None:
        comp = self.completer()
        if comp is None:
            return
        comp.setCompletionPrefix(self.text())
        comp.complete()

    def focusInEvent(self, event) -> None:  # noqa: D401 - Qt signature
        super().focusInEvent(event)
        QTimer.singleShot(0, self._show_invoice_code_completer_popup)

    def mousePressEvent(self, event) -> None:  # noqa: D401 - Qt signature
        super().mousePressEvent(event)
        self._show_invoice_code_completer_popup()


def _cell_line_invoice_code() -> _InvoiceCodeLineEdit:
    """Manual Invoice line **Code** column widget (dropdown + type-ahead, same styling as ``_cell_line``)."""
    le = _InvoiceCodeLineEdit()
    le.setStyleSheet(
        f"QLineEdit {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_INV_GRID}; "
        f"padding: 1px 4px; color: {_INV_TEXT}; }}"
    )
    return le


def _cell_line_date() -> QLineEdit:
    """Line **Date** column: same US-date normalization as the invoice header date field."""
    le = _cell_line()
    attach_line_edit_us_date_normalization(le)
    return le


def _blank_zero_spin(s: QDoubleSpinBox) -> QDoubleSpinBox:
    """Empty line cells stay blank at 0. Qt ignores an empty specialValueText, so a space stands in."""
    s.setSpecialValueText(" ")
    return s


def _qty_spin() -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(0.0, 999_999.99)
    s.setDecimals(2)
    s.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
    s.setStyleSheet(
        f"QDoubleSpinBox {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_INV_GRID}; "
        f"padding: 1px 4px; color: {_INV_TEXT}; }}"
    )
    return _blank_zero_spin(s)


def _money_spin() -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(0.0, 999_999_999.99)
    s.setDecimals(2)
    s.setPrefix("$ ")
    s.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
    s.setStyleSheet(
        f"QDoubleSpinBox {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_INV_GRID}; "
        f"padding: 1px 4px; color: {_INV_TEXT}; }}"
    )
    return _blank_zero_spin(s)


def _line_total_spin() -> QDoubleSpinBox:
    """Line **Total** column: derived from Rate × Qty (matches persisted ``invoice_lines.line_total``)."""
    s = _money_spin()
    s.setReadOnly(True)
    s.setToolTip("Rate × quantity — same value saved on the invoice line.")
    return s


class InvoiceScreen(QWidget):
    """Create Invoices: QB Pro Desktop header, line grid, totals; persists to ``invoices`` / ``invoice_lines``."""

    customerRecordsChanged = Signal()
    openInvoicesChanged = Signal()

    # Column order matches the live QB Pro Create Invoices template (and print HTML).
    _LINE_COLS = (
        "SERVICED ON",
        "JL #",
        "DESCRIPTION",
        "BOL#",
        "RATE",
        "QUANTITY",
        "AMOUNT",
    )
    _LINE_DESC_COL = 2
    _N_LINE_ROWS = 22

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        ap_conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create Invoices")
        self._ap_conn = ap_conn
        self._invoice_number_autofill_value = ""
        self._browse_ids: list[int] = []
        # Browse position among saved invoices (0..n-1), trailing blank draft (n), or None = unpositioned draft.
        self._browse_slot: int | None = None
        # ``None`` = new draft; when set, Save/Export/Print updates this invoice via ``business.update_invoice``.
        self._current_invoice_id: int | None = None
        # Block line grid valueChanged/textChanged while loading or clearing (avoids footer flicker).
        self._suppress_invoice_line_recalc: bool = False
        # Block Ship To autofill / due-date recalc while hydrating a saved invoice.
        self._suppress_invoice_header_autofill: bool = False
        # Last customer id that auto-filled Ship To (avoid overwrite on tab show/reload).
        self._ship_to_autofill_customer_id: int | None = None
        # Memo text from DB when loading (also shown in the Memo field).
        self._invoice_memo_notes: str = ""
        self._payments_applied: float = 0.0
        # Set True only inside Print click handler while QPrintDialog may run (blocks stray callers).
        self._invoice_print_dialog_armed: bool = False
        # Fingerprint of last loaded/saved form (leave-tab dirty check for saved invoices).
        self._clean_fingerprint: tuple | None = None
        # Last committed Code column text per line (strip); avoids re-applying saved Code rate when only Rate changed.
        # Last committed Code column text per line (strip); avoids re-applying saved Code rate when only Rate changed.
        self._invoice_line_code_committed: list[str] = [""] * self._N_LINE_ROWS
        self.setToolTip(
            "Create Invoices: Customer:Job, Bill To / Ship To, line items; Save writes to your company file. "
            "Invoice # suggests the next number from your company file (editable). "
            "Bill To searches customers when connected. Ship To defaults to Bill To "
            "(QuickBooks Pro when the customer has no separate shipping address) and is saved with the invoice. "
            "Same .db (File → Backup / Restore, probooks.backup)."
        )
        self._build_ui()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Keep DESCRIPTION as the wide stretch column when the table is resized."""
        vp = getattr(self, "_invoice_lines_viewport", None)
        if vp is not None and watched is vp and event.type() == QEvent.Type.Resize:
            self._sync_invoice_line_description_column_width_safe()
        return super().eventFilter(watched, event)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        dirty = self._is_form_dirty()
        # Leaving the main tab switches away then back before the save prompt; do not
        # reload customers or the invoice # while dirty (that would wipe the draft).
        if not dirty:
            if self._ap_conn is not None:
                self._bill_customer_panel.reload_customers()
            self._sync_invoice_number_suggestion()
            self._refresh_browse_state()
        self._refresh_company_identity_header()
        self._update_new_customer_button_state()
        # After layout, give leftover width to DESCRIPTION (width was 0 during build).
        QTimer.singleShot(0, self._sync_invoice_line_description_column_width_safe)

    def hideEvent(self, event: QHideEvent) -> None:
        # Avoid focus landing on Save/Print when switching main tabs (stray Return/Space).
        self._defocus_invoice_action_buttons()
        tmr = getattr(self, "_line_widths_persist_timer", None)
        if tmr is not None and tmr.isActive():
            tmr.stop()
        # Flush debounced widths when leaving the tab (same pattern as Register header state).
        self._persist_invoice_line_column_widths()
        super().hideEvent(event)

    def _defocus_invoice_action_buttons(self) -> None:
        """Move keyboard focus off Save / Export / Print / nav so tab changes cannot activate them."""
        fw = self.focusWidget()
        if fw is None:
            return
        for b in (
            getattr(self, "_btn_save", None),
            getattr(self, "_btn_save_close", None),
            getattr(self, "_btn_ribbon_save", None),
            getattr(self, "_btn_export_pdf", None),
            getattr(self, "_btn_print", None),
            getattr(self, "_btn_clear_fields", None),
            getattr(self, "_btn_reverse", None),
            getattr(self, "_btn_forward", None),
            getattr(self, "_btn_find", None),
            getattr(self, "_btn_intake", None),
            getattr(self, "_btn_new_invoice", None),
        ):
            if b is not None and fw is b:
                t = getattr(self, "_table", None)
                if t is not None:
                    t.setFocus(Qt.FocusReason.OtherFocusReason)
                else:
                    self.setFocus(Qt.FocusReason.OtherFocusReason)
                return

    def _on_invoice_module_subtab_changed(self, _index: int) -> None:
        """Manual Invoice ↔ Invoice Intake: keep draft in memory; never prompt save here."""
        self._defocus_invoice_action_buttons()
        self._sync_create_invoices_module_chrome()

    def _sync_create_invoices_module_chrome(self) -> None:
        """While Create Invoices is showing, hide extra module tabs so the form is the window."""
        tabs = getattr(self, "_invoice_tabs", None)
        if tabs is None:
            return
        on_form = tabs.currentIndex() == 0
        tabs.tabBar().setVisible(not on_form)
        corner = tabs.cornerWidget(Qt.Corner.TopRightCorner)
        if corner is not None:
            corner.setVisible(not on_form)

    def _update_new_customer_button_state(self) -> None:
        on = self._ap_conn is not None
        self._btn_new_customer.setEnabled(on)
        self._btn_save.setEnabled(on)
        if getattr(self, "_btn_save_close", None) is not None:
            self._btn_save_close.setEnabled(on)
        if getattr(self, "_btn_ribbon_save", None) is not None:
            self._btn_ribbon_save.setEnabled(on)
        if getattr(self, "_btn_new_invoice", None) is not None:
            self._btn_new_invoice.setEnabled(True)
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

    def _iso_from_date_edit(self, w: QDateEdit) -> str:
        d = w.date()
        if not d.isValid():
            d = QDate.currentDate()
        return f"{d.year():04d}-{d.month():02d}-{d.day():02d}"

    def _set_date_edit_iso(self, w: QDateEdit, iso: str) -> None:
        ymd = parse_flexible_date_to_ymd((iso or "").strip())
        if ymd is None:
            w.setDate(QDate.currentDate())
            return
        y, m, d = ymd
        w.setDate(QDate(y, m, d))

    def _set_date_edit_from_display(self, w: QDateEdit, display: str) -> None:
        ymd = parse_flexible_date_to_ymd((display or "").strip())
        if ymd is None:
            return
        y, m, d = ymd
        w.setDate(QDate(y, m, d))

    def _set_terms_text(self, terms: str) -> None:
        raw = (terms or "").strip()
        if not raw:
            raw = business.default_invoice_terms(self._ap_conn)
        idx = self._terms.findText(raw)
        if idx < 0:
            self._terms.addItem(raw)
            idx = self._terms.findText(raw)
        self._terms.setCurrentIndex(max(0, idx))

    def _reset_terms_and_due_date_for_draft(self) -> None:
        self._suppress_invoice_header_autofill = True
        try:
            self._set_terms_text(business.default_invoice_terms(self._ap_conn))
            self._set_date_edit_iso(self._date, "")
            self._apply_due_date_from_terms()
        finally:
            self._suppress_invoice_header_autofill = False

    def _apply_due_date_from_terms(self) -> None:
        iso = self._iso_from_date_edit(self._date)
        due = business.due_date_iso_from_terms(iso, self._terms.currentText())
        self._set_date_edit_iso(self._due_date, due)

    def _on_invoice_date_or_terms_changed(self, *_args) -> None:
        if self._suppress_invoice_header_autofill:
            return
        self._apply_due_date_from_terms()

    def _on_bill_to_customer_changed(self, _cid: object) -> None:
        """QB Pro: selecting a customer fills Ship To from that customer's shipping address.

        This company file does not store a separate customer ship-to yet, so Ship To
        defaults to the Bill To block (same as QB when shipping is blank). Re-applying
        the same customer (tab show / combo reload) must not clobber an edited Ship To.
        """
        if self._suppress_invoice_header_autofill:
            return
        try:
            new_id = int(_cid) if _cid is not None else None
        except (TypeError, ValueError):
            new_id = None
        if new_id is not None and new_id == self._ship_to_autofill_customer_id:
            return
        self._ship_to_autofill_customer_id = new_id
        ship = getattr(self, "_ship_to", None)
        if ship is None:
            return
        ship[1].setPlainText(self._bill_to[1].toPlainText())

    def _ship_to_plain(self) -> str:
        ship = getattr(self, "_ship_to", None)
        if ship is None:
            return ""
        return ship[1].toPlainText().strip()

    def _set_ship_to_plain(self, text: str) -> None:
        ship = getattr(self, "_ship_to", None)
        if ship is None:
            return
        ship[1].setPlainText(text or "")

    def bill_to_customer_panel(self) -> CustomerBillToPanel:
        return self._bill_customer_panel

    def selected_bill_to_customer_id(self) -> Optional[int]:
        return self._bill_customer_panel.selected_customer_id()

    def prepare_new_invoice_for_customer(self, customer_id: int) -> None:
        """Tiny Customer Center hook: new invoice draft with Bill To *customer_id*."""
        if not self._prompt_save_unsaved_invoice():
            return
        if getattr(self, "_invoice_tabs", None) is not None:
            self._invoice_tabs.setCurrentIndex(0)
        self._go_to_new_invoice_draft()
        if customer_id and self._ap_conn is not None:
            self._bill_customer_panel.reload_customers()
            self._bill_customer_panel.select_customer_by_id(int(customer_id))
        # A draft holding only the Bill To the Customer Center picked has nothing worth
        # saving, so navigating away again must not stop on "Save invoice?".
        self._mark_form_clean()

    def _line_edit_header_style(self) -> str:
        return (
            f"QLineEdit {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_INV_GRID}; "
            f"padding: 1px 6px; color: {_INV_TEXT}; }}"
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
        elif compact_vertical and isinstance(editor, QDateEdit):
            editor.setFixedHeight(_INVOICE_TOP_FOUR_LINE_HEIGHT_PX)
            if unified_top_strip:
                editor.setStyleSheet(_top_strip_date_edit_qss())
        elif compact_vertical and isinstance(editor, QComboBox):
            editor.setFixedHeight(_INVOICE_TOP_FOUR_LINE_HEIGHT_PX)
            if unified_top_strip:
                editor.setStyleSheet(_top_strip_combo_qss())
        if unified_top_strip and compact_vertical:
            fr.setFixedHeight(_top_strip_field_outer_height_px())
            fr.setSizePolicy(
                QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Fixed,
            )
        return fr

    def _bar_caption(self, text: str) -> QLabel:
        cap = QLabel(text)
        cap.setStyleSheet(
            f"color: {_INV_CAPTION}; font-size: 10px; font-weight: 700; "
            "letter-spacing: 0.04em; background: transparent; border: none;"
        )
        return cap

    def _style_strip_button(self, b: QPushButton, *, primary: bool = False, height: int | None = None) -> None:
        h = height if height is not None else _FOOTER_BTN_HEIGHT_PX
        b.setStyleSheet(_top_strip_action_button_qss(primary=primary))
        b.setFixedHeight(h)
        b.setAutoDefault(False)
        b.setDefault(False)

    def _compact_meta_field(self, caption: str, editor: QWidget) -> QWidget:
        """Caption + 22px editor — tight DATE / INVOICE # / TERMS / DUE DATE stack.

        Wrapper is explicit white: the app dark theme paints unnamed QWidget navy, which
        reads as a redaction bar behind PO/CONTRACT#, DATE, and the other stacked labels.
        """
        w = QWidget()
        w.setObjectName("invoiceCompactMetaField")
        w.setAutoFillBackground(True)
        pal = w.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(_INV_BG))
        pal.setColor(QPalette.ColorRole.WindowText, QColor(_INV_CAPTION))
        w.setPalette(pal)
        w.setStyleSheet(
            f"QWidget#invoiceCompactMetaField {{ background-color: {_INV_BG}; border: none; }}"
        )
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)
        cap = QLabel(caption)
        cap.setStyleSheet(
            f"color: {_INV_CAPTION}; font-size: 9px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        lay.addWidget(cap)
        editor.setFixedHeight(22)
        if isinstance(editor, QLineEdit):
            editor.setStyleSheet(self._line_edit_header_style())
        elif isinstance(editor, QDateEdit):
            editor.setStyleSheet(
                f"QDateEdit {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_INV_GRID}; "
                f"padding: 1px 6px; color: {_INV_TEXT}; }}"
            )
        elif isinstance(editor, QComboBox):
            editor.setStyleSheet(
                f"QComboBox {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_INV_GRID}; "
                f"padding: 1px 6px; color: {_INV_TEXT}; }}"
            )
        lay.addWidget(editor)
        w.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        return w

    def _invoice_template_choices(self) -> list[str]:
        """Built-in template plus whatever the company file stored (never a hardcoded live name)."""
        names = [_DEFAULT_INVOICE_TEMPLATE]
        raw = ""
        if self._ap_conn is not None:
            try:
                raw = (business.get_setting(self._ap_conn, "invoice_template_name", "") or "").strip()
            except (sqlite3.Error, TypeError, ValueError):
                raw = ""
        if raw and raw not in names:
            names.append(raw)
        return names

    def _ar_account_choices(self) -> list[str]:
        names = [_DEFAULT_AR_ACCOUNT]
        if self._ap_conn is not None:
            try:
                label = business._get_coa_account_label(self._ap_conn, "1100")
            except (sqlite3.Error, TypeError, ValueError, AttributeError):
                label = ""
            if label and label != "1100" and label not in names:
                names.insert(0, label)
        return names

    def _build_create_invoices_chrome(self, play: QVBoxLayout) -> None:
        """QB Pro Create Invoices header: slim ribbon, one-row Customer:Job bar, compact Bill To."""
        _uc = Qt.ConnectionType.UniqueConnection
        _bar_combo_qss = (
            f"QComboBox {{ background: {WORKFLOW_INPUT_BG}; color: {_INV_TEXT}; "
            f"border: 1px solid #9AA8B8; padding: 1px 6px; min-height: 20px; max-height: 22px; }}"
        )

        # ── Ribbon (Main / Formatting / Send-Ship / Reports) — fixed slim height ──
        self._invoice_ribbon = QTabWidget()
        self._invoice_ribbon.setObjectName("invoiceRibbonTabs")
        self._invoice_ribbon.setDocumentMode(True)
        self._invoice_ribbon.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        self._invoice_ribbon.setFixedHeight(_RIBBON_MAX_HEIGHT_PX)
        self._invoice_ribbon.setStyleSheet(
            f"QTabWidget#invoiceRibbonTabs::pane {{ border: 1px solid {_INV_GRID}; "
            f"background: {_INV_PANEL}; border-radius: 4px; }}"
            f"QTabWidget#invoiceRibbonTabs QTabBar::tab {{ padding: 2px 8px; min-height: 16px; "
            f"max-height: 18px; }}"
        )

        main_rib = QWidget()
        main_lay = QHBoxLayout(main_rib)
        main_lay.setContentsMargins(6, 2, 6, 2)
        main_lay.setSpacing(4)

        self._btn_find = QPushButton("Find")
        self._btn_find.setToolTip(
            "Search saved invoices by invoice number, customer name, total, or date "
            "(flexible US-style dates), then load the first match into this form. "
            "Use Previous / Next to browse from there."
        )
        self._btn_new_invoice = QPushButton("New")
        self._btn_new_invoice.setToolTip(
            "Start a blank invoice. If this form has unsaved changes, asks Save invoice ###? first."
        )
        self._btn_ribbon_save = QPushButton("Save")
        self._btn_ribbon_save.setToolTip(
            "Save this invoice to the company file and keep it open (QuickBooks ribbon Save)."
        )
        self._btn_print = QPushButton("Print")
        self._btn_print.setToolTip(
            "Save this invoice to the company file, then print using the default printer from "
            "Edit → Preferences → Invoice Options (or pick a printer once if unset). "
            "After a successful print, the form resets for the next invoice."
        )
        self._btn_email = QPushButton("Email")
        self._btn_email.setToolTip(
            "Save this invoice, export a PDF, and open a mailto draft addressed to the "
            "customer (subject and body pre-filled with invoice # and amount). "
            "If the customer has no email address, or your OS has no mail handler, a real "
            "message explains what to do next — no silent failure."
        )
        self._btn_export_pdf = QPushButton("Save As")
        self._btn_export_pdf.setToolTip(
            "Save this invoice to the company file, then pick a PDF file. "
            "The default name is the invoice number (for example 8114.pdf); you can edit it. "
            "Opens in the last folder used for this company on this PC. "
            "Asks before overwriting an existing file."
        )
        self._btn_new_customer = QPushButton("New Customer")
        self._btn_new_customer.setToolTip(
            "Same **New customer** dialog as the Customers tab; Bill To fills when you save."
        )
        self._btn_reverse = QPushButton("Previous")
        self._btn_forward = QPushButton("Next")
        self._btn_reverse.setToolTip(
            "Previous invoice by date, then invoice number (oldest first). "
            "From an unsaved draft, opens the last invoice in that order."
        )
        self._btn_forward.setToolTip(
            "Next invoice by date, then invoice number. After the newest saved invoice, opens one blank draft "
            "(stops there — Next does not cycle to the first invoice)."
        )
        self._btn_intake = QPushButton("Intake")
        self._btn_intake.setToolTip(
            "Open Invoice Intake (stage PDFs / images / pasted text). Hidden from the form tab strip "
            "so Create Invoices keeps the window height."
        )
        for b in (
            self._btn_find,
            self._btn_new_invoice,
            self._btn_ribbon_save,
            self._btn_print,
            self._btn_email,
            self._btn_export_pdf,
            self._btn_new_customer,
            self._btn_reverse,
            self._btn_forward,
            self._btn_intake,
        ):
            self._style_strip_button(b, height=_RIBBON_BTN_HEIGHT_PX)
            main_lay.addWidget(b)
        main_lay.addStretch(1)
        self._invoice_ribbon.addTab(main_rib, "Main")

        def _later_tab(body: str) -> QWidget:
            w = QWidget()
            lay = QHBoxLayout(w)
            lay.setContentsMargins(8, 2, 8, 2)
            lb = QLabel(body)
            lb.setStyleSheet(f"color: {_INV_CAPTION}; font-size: 11px; background: transparent;")
            lay.addWidget(lb)
            return w

        self._invoice_ribbon.addTab(
            _later_tab("Formatting follows later QuickBooks screens."),
            "Formatting",
        )
        self._invoice_ribbon.addTab(
            _later_tab("Send/Ship follows later QuickBooks screens."),
            "Send/Ship",
        )
        self._invoice_ribbon.addTab(
            _later_tab("Reports follows later QuickBooks screens."),
            "Reports",
        )
        play.addWidget(self._invoice_ribbon)

        bill_panel, bill_te = build_customer_bill_to_panel(
            self,
            ap_conn=self._ap_conn,
            layout_max_width_px=None,
            bill_plain_height_px=_INVOICE_BILL_TO_TEXT_HEIGHT_PX,
            combo_min_width_px=_INVOICE_BILL_TO_COMBO_MIN_WIDTH_PX,
            show_new_customer_button=False,
            show_combo_in_panel=False,
        )
        self._bill_customer_panel = bill_panel
        self._bill_to = (bill_panel, bill_te)
        self._bill_customer_panel.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        self._ship_to = self._address_box(
            "Ship To",
            height_px=_INVOICE_BILL_TO_TEXT_HEIGHT_PX,
        )
        self._ship_to[0].setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        self._bill_customer_panel.customerIdChanged.connect(
            self._on_bill_to_customer_changed
        )

        # ── Customer:Job / Account / Template — white strip, dark captions (not a redaction bar) ──
        job_bar = QFrame()
        job_bar.setObjectName("invoiceCustomerJobBar")
        job_bar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        job_bar.setStyleSheet(
            f"QFrame#invoiceCustomerJobBar {{ background-color: {_INV_BG}; "
            f"border: 1px solid {_INV_GRID}; border-radius: 4px; }}"
        )
        jb = QHBoxLayout(job_bar)
        jb.setContentsMargins(8, 4, 8, 4)
        jb.setSpacing(8)
        cj_cap = self._bar_caption("CUSTOMER:JOB")
        cj_cap.setObjectName("invoiceCustomerJobCaption")
        jb.addWidget(cj_cap)
        combo = self._bill_customer_panel.customer_combo()
        combo.setMinimumWidth(_INVOICE_BILL_TO_COMBO_MIN_WIDTH_PX)
        combo.setMaximumHeight(22)
        combo.setStyleSheet(_bar_combo_qss)
        jb.addWidget(combo, 3)
        jb.addWidget(self._bar_caption("ACCOUNT"))
        self._ar_account = QComboBox()
        self._ar_account.setObjectName("invoiceArAccount")
        self._ar_account.setEditable(False)
        self._ar_account.addItems(self._ar_account_choices())
        self._ar_account.setToolTip("Accounts Receivable account for this invoice.")
        self._ar_account.setMaximumHeight(22)
        self._ar_account.setStyleSheet(_bar_combo_qss)
        jb.addWidget(self._ar_account, 2)
        jb.addWidget(self._bar_caption("TEMPLATE"))
        self._invoice_template = QComboBox()
        self._invoice_template.setObjectName("invoiceTemplateCombo")
        self._invoice_template.setEditable(False)
        self._invoice_template.addItems(self._invoice_template_choices())
        self._invoice_template.setCurrentIndex(0)
        self._invoice_template.setToolTip(
            "Invoice template. Default is Standard Invoice — live company names are not hardcoded."
        )
        self._invoice_template.setMaximumHeight(22)
        self._invoice_template.setStyleSheet(_bar_combo_qss)
        jb.addWidget(self._invoice_template, 2)
        play.addWidget(job_bar)

        # ── Compact header: Invoice | Bill To + PO/Job | Ship To | DATE stack ──
        self._date = QDateEdit()
        configure_qdate_edit_us(self._date)
        self._date.setDate(QDate.currentDate())
        self._date.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._date.setToolTip("Invoice date (QuickBooks Pro date control).")

        self._inv_number = QLineEdit()
        self._inv_number.setObjectName("invoiceNumberEdit")
        self._inv_number.setPlaceholderText("Invoice #")
        self._inv_number.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._inv_number.setStyleSheet(self._line_edit_header_style())

        self._terms = QComboBox()
        self._terms.setEditable(False)
        self._terms.addItems(list(business.INVOICE_TERMS_CHOICES))
        self._terms.setToolTip(
            "Payment terms. Changing terms (or the invoice date) fills Due Date."
        )
        self._due_date = QDateEdit()
        configure_qdate_edit_us(self._due_date)
        self._due_date.setDate(QDate.currentDate())
        self._due_date.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._due_date.setToolTip(
            "Due date. Filled from Terms when you change Date or Terms; you can still edit it."
        )
        self._date.dateChanged.connect(self._on_invoice_date_or_terms_changed)
        self._terms.currentIndexChanged.connect(self._on_invoice_date_or_terms_changed)

        self._po = QLineEdit()
        self._po.setPlaceholderText("PO / contract #")
        self._job = QLineEdit()
        self._job.setPlaceholderText("Name / job #")

        header_band = QFrame()
        header_band.setObjectName("invoiceHeaderBand")
        header_band.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        header_band.setStyleSheet(
            f"QFrame#invoiceHeaderBand {{ background-color: {_INV_PANEL}; "
            f"border: 1px solid {_INV_GRID}; border-radius: 6px; }}"
        )
        hb = QGridLayout(header_band)
        hb.setContentsMargins(8, 4, 8, 6)
        hb.setHorizontalSpacing(8)
        hb.setVerticalSpacing(4)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 4, 0, 0)
        title_row.setSpacing(6)
        title = QLabel("Invoice")
        title.setObjectName("createInvoicesTitle")
        title.setStyleSheet(
            f"font-size: {_INVOICE_TITLE_FONT_PX}px; font-weight: 700; color: #3D4A54; "
            "background: transparent;"
        )
        title_row.addWidget(title)
        self._invoice_status_badge = QLabel("")
        self._invoice_status_badge.setObjectName("invoiceStatusBadge")
        self._invoice_status_badge.setVisible(False)
        self._invoice_status_badge.setStyleSheet(
            "QLabel#invoiceStatusBadge { color: #16a34a; font-size: 12px; font-weight: 700; "
            "letter-spacing: 0.06em; background: transparent; padding: 0 8px 0 0; }"
        )
        title_row.addWidget(self._invoice_status_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        title_row.addStretch(1)
        title_wrap = QWidget()
        title_wrap.setObjectName("invoiceLightWrap")
        title_wrap.setStyleSheet(
            f"QWidget#invoiceLightWrap {{ background: transparent; border: none; }}"
        )
        title_wrap.setLayout(title_row)
        title_wrap.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        hb.addWidget(title_wrap, 0, 0, 2, 1, Qt.AlignmentFlag.AlignTop)

        bill_col = QVBoxLayout()
        bill_col.setContentsMargins(0, 0, 0, 0)
        bill_col.setSpacing(3)
        bill_col.addWidget(self._bill_to[0])
        po_job = QHBoxLayout()
        po_job.setSpacing(6)
        po_job.addWidget(self._compact_meta_field("PO/CONTRACT#", self._po), 1)
        po_job.addWidget(self._compact_meta_field("NAME/JOB#", self._job), 1)
        bill_col.addLayout(po_job)
        bill_wrap = QWidget()
        bill_wrap.setObjectName("invoiceLightWrap")
        bill_wrap.setStyleSheet(
            f"QWidget#invoiceLightWrap {{ background: transparent; border: none; }}"
        )
        bill_wrap.setLayout(bill_col)
        bill_wrap.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        hb.addWidget(bill_wrap, 0, 1, 2, 1)

        hb.addWidget(self._ship_to[0], 0, 2, 1, 1, Qt.AlignmentFlag.AlignTop)

        meta = QGridLayout()
        meta.setContentsMargins(0, 0, 0, 0)
        meta.setHorizontalSpacing(6)
        meta.setVerticalSpacing(2)
        meta.addWidget(self._compact_meta_field("DATE", self._date), 0, 0)
        meta.addWidget(self._compact_meta_field("INVOICE #", self._inv_number), 0, 1)
        meta.addWidget(self._compact_meta_field("TERMS", self._terms), 1, 0)
        meta.addWidget(self._compact_meta_field("DUE DATE", self._due_date), 1, 1)
        meta_w = QWidget()
        meta_w.setObjectName("invoiceLightWrap")
        meta_w.setStyleSheet(
            f"QWidget#invoiceLightWrap {{ background: transparent; border: none; }}"
        )
        meta_w.setLayout(meta)
        meta_w.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        hb.addWidget(meta_w, 0, 3, 2, 1, Qt.AlignmentFlag.AlignTop)

        hb.setColumnStretch(0, 1)
        hb.setColumnStretch(1, 3)
        hb.setColumnStretch(2, 2)
        hb.setColumnStretch(3, 2)
        play.addWidget(header_band)

        self._btn_save = QPushButton("Save && New")
        self._btn_save.setToolTip(
            "Save this invoice to the company file and write a PDF when a folder is set, "
            "then start a new blank invoice (QuickBooks Save & New)."
        )
        self._btn_save_close = QPushButton("Save && Close")
        self._btn_save_close.setToolTip(
            "Save this invoice to the company file and keep it on the form "
            "(tab analog of QuickBooks Save & Close)."
        )
        self._btn_clear_fields = QPushButton("Clear")
        self._btn_clear_fields.setToolTip(
            "Clear lines and header fields and start a new draft without saving."
        )
        self._style_strip_button(self._btn_save, primary=True, height=_FOOTER_BTN_HEIGHT_PX)
        self._style_strip_button(self._btn_save_close, height=_FOOTER_BTN_HEIGHT_PX)
        self._style_strip_button(self._btn_clear_fields, height=_FOOTER_BTN_HEIGHT_PX)

        self._btn_save.clicked.connect(self._on_save_invoice, _uc)
        self._btn_save_close.clicked.connect(self._on_save_close_invoice, _uc)
        self._btn_ribbon_save.clicked.connect(self._on_ribbon_save_invoice, _uc)
        self._btn_export_pdf.clicked.connect(self._on_export_pdf_as, _uc)
        self._btn_print.clicked.connect(self._on_print_invoice, _uc)
        self._btn_clear_fields.clicked.connect(self._on_clear_fields, _uc)
        self._btn_new_customer.clicked.connect(
            self._bill_customer_panel.open_new_customer_dialog, _uc
        )
        self._bill_customer_panel.customerCreated.connect(
            lambda _nid: self.customerRecordsChanged.emit()
        )
        self._btn_reverse.clicked.connect(self._on_reverse_invoice, _uc)
        self._btn_forward.clicked.connect(self._on_forward_invoice, _uc)
        self._btn_find.clicked.connect(self._on_find_invoice, _uc)
        self._btn_email.clicked.connect(self._on_email_invoice, _uc)
        self._btn_new_invoice.clicked.connect(self._on_clear_fields, _uc)
        self._btn_intake.clicked.connect(self._on_open_invoice_intake, _uc)

    def _on_open_invoice_intake(self) -> None:
        tabs = getattr(self, "_invoice_tabs", None)
        if tabs is None:
            return
        tabs.setCurrentIndex(1)

    def _build_ui(self) -> None:
        self.setPalette(_light_form_palette())
        self.setAutoFillBackground(True)
        self.setStyleSheet(
            f"InvoiceScreen {{ background-color: {_INV_CANVAS}; color: {_INV_TEXT}; }}"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 2, 4, 4)
        outer.setSpacing(0)

        self._invoice_tabs = QTabWidget(self)
        self._invoice_tabs.setObjectName("invoiceModuleTabs")
        self._invoice_tabs.setToolTip(
            "Create Invoices: QuickBooks Pro invoice form. Invoice Intake: stage sources and send to a draft."
        )
        self._invoice_tabs.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._invoice_tabs.setDocumentMode(True)

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
            f"QTabWidget#invoiceModuleTabs QTabBar::tab {{ padding: 2px 8px; min-height: 16px; }}"
        )

        self._sync_ar_toolbar_enabled()

        page = QFrame()
        page.setObjectName("invoiceLightPanel")
        page.setStyleSheet(
            f"QFrame#invoiceLightPanel {{ background-color: {_INV_BG}; border: 1px solid {_INV_GRID}; "
            "border-radius: 4px; }}"
        )
        play = QVBoxLayout(page)
        play.setContentsMargins(6, 4, 6, 4)
        play.setSpacing(4)

        # Company identity stays on PDF/print; omit it from the form so the grid keeps the height.
        self._company_identity_label = QLabel("")
        self._company_identity_label.setVisible(False)
        self._company_identity_label.setToolTip(
            "Company identity from your company file (File → New Company). "
            "Matches the top-left block on printed and PDF invoices."
        )

        self._build_create_invoices_chrome(play)

        self._update_new_customer_button_state()

        self._sync_invoice_number_suggestion()
        self._reset_terms_and_due_date_for_draft()

        self._invoice_intake_handoff_banner = QLabel("")
        self._invoice_intake_handoff_banner.setObjectName("invoiceIntakeHandoffBanner")
        self._invoice_intake_handoff_banner.setWordWrap(True)
        self._invoice_intake_handoff_banner.setVisible(False)
        self._invoice_intake_handoff_banner.setStyleSheet(
            f"QLabel#invoiceIntakeHandoffBanner {{ color: {_INV_TEXT}; font-size: 12px; "
            f"background-color: {_INV_PANEL}; border: 1px solid {_INV_GRID}; border-radius: 4px; "
            f"padding: 4px 8px; }}"
        )
        play.addWidget(self._invoice_intake_handoff_banner)

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
        # DESCRIPTION stretches to leftover width so columns fit without a horizontal scrollbar.
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
        self._table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._table.setMinimumHeight(220)
        self._table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
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
            f" padding: 4px; border: 1px solid {_INV_GRID};"
            " font-weight: 600;"
            " text-align: left;"
            " }}"
        )

        for row in range(self._N_LINE_ROWS):
            dt = _cell_line_date()
            self._table.setCellWidget(row, 0, dt)

            code = _cell_line_invoice_code()
            code.setToolTip(
                "Pick an invoice code from the saved Codes list, or type to filter. "
                "Click or focus to open the dropdown; typing narrows choices live. "
                "Selecting a saved Code auto-fills Description and Rate on this line "
                "(your manual Rate edits are kept until you change the Code again)."
            )
            self._table.setCellWidget(row, 1, code)

            desc = _cell_line()
            self._table.setCellWidget(row, 2, desc)

            bol = _cell_line()
            self._table.setCellWidget(row, 3, bol)

            rate = _money_spin()
            rate.setValue(0.0)
            self._table.setCellWidget(row, 4, rate)

            qty = _qty_spin()
            qty.setValue(0.0)
            self._table.setCellWidget(row, 5, qty)

            total = _line_total_spin()
            total.setValue(0.0)
            total.setToolTip("Amount — quantity × rate (QuickBooks Pro).")
            self._table.setCellWidget(row, 6, total)

        self._wire_invoice_line_recalc()
        self._setup_invoice_code_helpers()

        # Column widths: DESCRIPTION stretches; others stay narrow (no horizontal scrollbar).
        self._invoice_table_resizing = False
        self._line_widths_persist_timer: QTimer | None = None
        self._invoice_lines_viewport = self._table.viewport()
        self._invoice_lines_viewport.installEventFilter(self)
        if not self._restore_invoice_line_column_widths():
            self._apply_default_invoice_line_column_widths()
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

        # ── Footer strip: message / memo / totals / Save & Close / Save & New / Clear ──
        tot_frame = QFrame()
        tot_frame.setObjectName("invoiceFooterBand")
        tot_frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        tot_frame.setStyleSheet(
            f"QFrame#invoiceFooterBand {{ background-color: {_INV_PANEL}; "
            f"border: 1px solid {_INV_GRID}; border-radius: 4px; }}"
        )
        tot = QHBoxLayout(tot_frame)
        tot.setContentsMargins(8, 4, 8, 4)
        tot.setSpacing(8)

        msg_block = QVBoxLayout()
        msg_block.setContentsMargins(0, 0, 0, 0)
        msg_block.setSpacing(1)
        msg_block.addWidget(self._bar_caption("CUSTOMER MESSAGE"))
        self._customer_message = QComboBox()
        self._customer_message.setObjectName("invoiceCustomerMessage")
        self._customer_message.setEditable(True)
        self._customer_message.setFixedHeight(22)
        self._customer_message.addItems(list(_CUSTOMER_MESSAGE_CHOICES))
        self._customer_message.setToolTip("Printed customer message (saved with the invoice memo).")
        msg_block.addWidget(self._customer_message)
        tot.addLayout(msg_block, 1)

        memo_block = QVBoxLayout()
        memo_block.setContentsMargins(0, 0, 0, 0)
        memo_block.setSpacing(1)
        memo_block.addWidget(self._bar_caption("MEMO"))
        self._memo_edit = QLineEdit()
        self._memo_edit.setObjectName("invoiceMemoEdit")
        self._memo_edit.setPlaceholderText("Memo")
        self._memo_edit.setFixedHeight(22)
        self._memo_edit.setStyleSheet(self._line_edit_header_style())
        self._memo_edit.setToolTip("Internal memo (saved with PO/CONTRACT# and NAME/JOB# on the invoice).")
        memo_block.addWidget(self._memo_edit)
        tot.addLayout(memo_block, 1)

        self._lbl_sub = QLabel("Subtotal: $0.00")
        self._lbl_tax = QLabel("Tax: $0.00")
        self._lbl_total = QLabel("Total: $0.00")
        self._lbl_payments = QLabel("Payments Applied: $0.00")
        self._lbl_balance = QLabel("Balance Due: $0.00")
        for lb in (self._lbl_sub, self._lbl_tax, self._lbl_total, self._lbl_payments, self._lbl_balance):
            lb.setStyleSheet(f"color: {_INV_TEXT}; font-size: 12px;")
            lb.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._lbl_sub.setVisible(False)
        self._lbl_tax.setVisible(False)
        self._lbl_balance.setStyleSheet(
            f"color: {_INV_TEXT}; font-size: 13px; font-weight: 700;"
        )
        tot_col = QVBoxLayout()
        tot_col.setContentsMargins(0, 0, 0, 0)
        tot_col.setSpacing(0)
        tot_col.addWidget(self._lbl_sub)
        tot_col.addWidget(self._lbl_tax)
        tot_col.addWidget(self._lbl_total)
        tot_col.addWidget(self._lbl_payments)
        tot_col.addWidget(self._lbl_balance)
        tot.addLayout(tot_col)
        tot.addWidget(self._btn_save_close)
        tot.addWidget(self._btn_save)
        tot.addWidget(self._btn_clear_fields)
        play.addWidget(tot_frame)

        self._invoice_intake = InvoiceIntakePanel(self._invoice_tabs, invoice_screen=self)
        self._invoice_tabs.addTab(page, "Create Invoices")
        self._invoice_tabs.addTab(self._invoice_intake, "Invoice Intake")
        self._invoice_tabs.setCurrentIndex(0)
        self._invoice_tabs.currentChanged.connect(self._on_invoice_module_subtab_changed)
        outer.addWidget(self._invoice_tabs, 1)
        self._sync_create_invoices_module_chrome()

        self._refresh_company_identity_header()
        self._refresh_browse_state()

    def set_enter_bills_screen(self, screen: Optional[QWidget]) -> None:
        """Wire Enter Bills so Invoice Intake can pre-fill payables from dispatch rows."""
        intake = getattr(self, "_invoice_intake", None)
        if intake is not None and hasattr(intake, "set_enter_bills_screen"):
            intake.set_enter_bills_screen(screen)

    def _refresh_company_identity_header(self) -> None:
        """Keep company identity off the form (PDF/print still use ``company_identity_plain_block``)."""
        lbl = getattr(self, "_company_identity_label", None)
        if lbl is None:
            return
        lbl.setVisible(False)
        if self._ap_conn is None:
            lbl.clear()
            return
        try:
            block = company_identity_plain_block(self._ap_conn).strip()
        except (sqlite3.Error, OSError, TypeError, ValueError):
            block = ""
        lbl.setText(block)

    def apply_intake_item_to_draft(
        self,
        *,
        source_display: str,
        kind: str,
        path: str | None = None,
        text_payload: str | None = None,
        queue_notes: str = "",
        text_extraction: TextIntakeExtraction | None = None,
        extracted_file_text: str | None = None,
        file_extract_note: str | None = None,
    ) -> bool:
        """Switch to Manual Invoice with a new draft; carry intake source into memo (saved on Save).

        Uses staged data only. *text_extraction* (from pasted text or PDF/image text layer / OCR) may
        set invoice date / BOL# when confidence is high — no invented line totals.
        """
        if self._ap_conn is None:
            message_box_information_ok(
                self,
                "Invoice",
                "Open a company file to create an invoice draft.",
                ok_tip="Close; use File → Open company… then try again.",
            )
            return False
        if not self._prompt_save_unsaved_invoice():
            return False
        self._invoice_tabs.setCurrentIndex(0)
        self._go_to_new_invoice_draft()

        src = (source_display or "").strip() or "(unnamed)"
        k = (kind or "").strip() or "?"
        qn = (queue_notes or "").strip()
        memo_lines: list[str] = [
            "[Invoice intake] Draft from staged item — review and edit before Save.",
            f"Source label: {src}",
            f"Type: {k}",
        ]
        p = (path or "").strip()
        if p:
            memo_lines.append(f"Attachment path: {os.path.normpath(p)}")
        if qn:
            memo_lines.append(f"Queue notes: {qn}")
        ex = text_extraction
        if ex is not None:
            applied: list[str] = []
            if ex.date_confidence == "high" and ex.date_display:
                applied.append(f"Invoice date (form): {ex.date_display}")
            if ex.ticket_confidence == "high" and ex.ticket_ref:
                applied.append(f"Line 1 BOL# (form): {ex.ticket_ref}")
            extra_memo = ex.memo_lines_for_handoff()
            if applied or extra_memo:
                memo_lines.append("")
                memo_lines.append("--- Intake extraction (high confidence) ---")
                memo_lines.extend(applied)
                memo_lines.extend(extra_memo)
        if k == "Text" and (text_payload or "").strip():
            body = text_payload.strip()
            if len(body) > 8000:
                body = body[:8000] + "\n… (truncated for memo; paste more in the line grid if needed)"
            memo_lines.append("")
            memo_lines.append("--- Staged text (from clipboard / intake) ---")
            memo_lines.append(body)
        elif k in ("PDF", "Image") and (extracted_file_text or "").strip():
            body = (extracted_file_text or "").strip()
            if len(body) > 8000:
                body = body[:8000] + "\n… (truncated for memo; paste more in the line grid if needed)"
            memo_lines.append("")
            memo_lines.append(
                f"--- Extracted text ({k} file; same source as intake review panel) ---"
            )
            memo_lines.append(body)
        if k in ("PDF", "Image") and (file_extract_note or "").strip():
            memo_lines.append("")
            memo_lines.append("--- Extraction note ---")
            memo_lines.append((file_extract_note or "").strip())

        self._invoice_memo_notes = "\n".join(memo_lines).strip()
        self._set_memo_edit_text(self._invoice_memo_notes)

        if ex is not None:
            if ex.date_confidence == "high" and ex.date_display:
                self._set_date_edit_from_display(self._date, ex.date_display)
            if ex.ticket_confidence == "high" and ex.ticket_ref:
                bol_w = self._table.cellWidget(0, 3)
                if isinstance(bol_w, QLineEdit):
                    bol_w.setText(ex.ticket_ref)

        num = (self._inv_number.text() or "").strip()
        if k == "Text" and (text_payload or "").strip():
            raw = text_payload.strip()
            preview = raw if len(raw) <= 500 else raw[:500] + "…"
            ext_note = ""
            if ex is not None:
                bits: list[str] = []
                if ex.date_confidence == "high":
                    bits.append("invoice date")
                if ex.ticket_confidence == "high":
                    bits.append("BOL#")
                if ex.memo_lines_for_handoff():
                    bits.append("memo lines")
                if bits:
                    ext_note = f"\n\nApplied from text extraction: {', '.join(bits)}."
            banner = (
                f"From Invoice Intake — pasted text ({len(raw)} chars). "
                f"Suggested invoice # {num or '—'}.\n\n"
                f"Preview (full text is saved on the invoice memo):\n{preview}{ext_note}"
            )
        elif k in ("PDF", "Image") and p:
            raw_file = (extracted_file_text or "").strip()
            if raw_file:
                preview = raw_file if len(raw_file) <= 500 else raw_file[:500] + "…"
                ext_note = ""
                if ex is not None:
                    bits: list[str] = []
                    if ex.date_confidence == "high":
                        bits.append("invoice date")
                    if ex.ticket_confidence == "high":
                        bits.append("BOL#")
                    if ex.memo_lines_for_handoff():
                        bits.append("memo lines")
                    if bits:
                        ext_note = f"\n\nApplied from extraction: {', '.join(bits)}."
                banner = (
                    f"From Invoice Intake — {k}: {src} ({len(raw_file)} chars extracted). "
                    f"Suggested invoice # {num or '—'}.\n\n"
                    f"Preview (extracted text is on the invoice memo):\n{preview}{ext_note}"
                )
            else:
                note = (file_extract_note or "").strip() or (
                    "No text extracted from this file; path and any note are in the memo."
                )
                banner = (
                    f"From Invoice Intake — {k}: {src}. Suggested invoice # {num or '—'}.\n\n"
                    f"{note}"
                )
        elif p:
            banner = (
                f"From Invoice Intake — {k}: {src}. Path is in the invoice memo (Save). "
                f"Suggested invoice # {num or '—'}."
            )
        else:
            banner = (
                f"From Invoice Intake — {k}: {src}. Details are in the invoice memo (Save). "
                f"Suggested invoice # {num or '—'}."
            )
        self._invoice_intake_handoff_banner.setText(banner)
        self._invoice_intake_handoff_banner.setVisible(True)

        self._refresh_browse_state()
        self._update_browse_buttons()
        return True

    def apply_dispatch_invoice_draft(self, draft: DispatchInvoiceDraft) -> bool:
        """Pre-fill Create Invoices from grouped dispatch loads. Does not save."""
        if self._ap_conn is None:
            message_box_information_ok(
                self,
                "Invoice",
                "Open a company file to create an invoice draft.",
                ok_tip="Close; use File → Open company… then try again.",
            )
            return False
        if not self._prompt_save_unsaved_invoice():
            return False
        self._invoice_tabs.setCurrentIndex(0)
        self._go_to_new_invoice_draft()

        if draft.date_iso:
            self._set_date_edit_iso(self._date, draft.date_iso)
        self._job.setText(draft.invoice_code)
        self._po.setText(draft.po_load)
        if (draft.qb_inv_no or "").strip():
            self._inv_number.setText(draft.qb_inv_no.strip())

        cid = None
        rule = job_billing_rule(draft.invoice_code)
        if self._ap_conn is not None:
            try:
                choices = business.list_bill_to_customer_choices(self._ap_conn)
            except (sqlite3.Error, TypeError, ValueError):
                choices = []
            needles: list[str] = []
            if rule and rule.get("customer_name"):
                needles.append(rule["customer_name"])
            if draft.invoice_code:
                needles.append(draft.invoice_code)
            for needle in needles:
                cid = match_named_entity_id(choices, needle)
                if cid is not None:
                    break
        self._bill_customer_panel.reload_customers()
        if cid is not None:
            self._bill_customer_panel.select_customer_by_id(cid)

        overflow = 0
        self._suppress_invoice_line_recalc = True
        try:
            for i, ln in enumerate(draft.lines):
                if i >= self._N_LINE_ROWS:
                    overflow = len(draft.lines) - self._N_LINE_ROWS
                    break
                dt_w = self._table.cellWidget(i, 0)
                desc_w = self._table.cellWidget(i, 2)
                bol_w = self._table.cellWidget(i, 3)
                rate_w = self._table.cellWidget(i, 4)
                qty_w = self._table.cellWidget(i, 5)
                if isinstance(dt_w, QLineEdit):
                    dt_w.setText(
                        format_iso_to_us_display(ln.date_iso) if ln.date_iso else ""
                    )
                if isinstance(desc_w, QLineEdit):
                    desc_w.setText(ln.description)
                if isinstance(bol_w, QLineEdit):
                    bol_w.setText(ln.bol)
                if isinstance(rate_w, QDoubleSpinBox):
                    rate_w.setValue(float(ln.rate))
                if isinstance(qty_w, QDoubleSpinBox):
                    qty_w.setValue(float(ln.qty))
        finally:
            self._suppress_invoice_line_recalc = False
        for r in range(self._N_LINE_ROWS):
            self._sync_invoice_line_row_total(r)
        self._recalc_invoice_footer_from_grid()

        memo_lines = [
            "[Dispatch intake] Draft from 1 CHAVAN DISPATCH CSV — review before Save.",
            f"Job / INVOICE code: {draft.invoice_code or '—'}",
            f"Loads: {len(draft.lines)}",
        ]
        if rule:
            memo_lines.append(
                f"Billing: {rule.get('customer_name') or '—'} — {rule.get('how_to_bill') or ''}"
            )
        if overflow:
            memo_lines.append(
                f"{overflow} additional load(s) did not fit the line grid; add them manually."
            )
        self._invoice_memo_notes = "\n".join(memo_lines).strip()
        self._set_memo_edit_text(self._invoice_memo_notes)

        num = (self._inv_number.text() or "").strip()
        banner = (
            f"From Invoice Intake — dispatch CSV ({len(draft.lines)} load"
            f"{'s' if len(draft.lines) != 1 else ''}"
            f" for {draft.invoice_code or 'job'}). "
            f"Invoice # {num or '—'}. Review lines, Bill To, and Save."
        )
        if overflow:
            banner += f" {overflow} load(s) omitted from the grid."
        self._invoice_intake_handoff_banner.setText(banner)
        self._invoice_intake_handoff_banner.setVisible(True)

        self._refresh_browse_state()
        self._update_browse_buttons()
        return True

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
        if iid == self._current_invoice_id:
            self._invoice_tabs.setCurrentIndex(0)
            return True
        self._invoice_tabs.setCurrentIndex(0)
        if not self._prompt_save_unsaved_invoice():
            return False
        self._load_invoice_into_form(iid)
        self._bill_customer_panel.reload_customers()
        self._sync_invoice_number_suggestion()
        self._refresh_browse_state()
        try:
            self._browse_slot = self._browse_ids.index(iid)
        except ValueError:
            self._browse_slot = None
        self._update_browse_buttons()
        return True

    def open_invoice_by_number(self, invoice_number: str) -> bool:
        """Load an invoice into Manual Invoice by ``invoices.invoice_number`` (register / navigation)."""
        if self._ap_conn is None:
            message_box_information_ok(
                self,
                "Invoice",
                "Open a company file to edit invoices.",
                ok_tip="Close; use File → Open company… then try again.",
            )
            return False
        iid = business.get_invoice_id_by_number(self._ap_conn, invoice_number)
        if iid is None:
            num = (invoice_number or "").strip()
            message_box_information_ok(
                self,
                "Invoice",
                f"No invoice with number {num!r} was found.",
                ok_tip="Close; check the number or pick the invoice from Customers / Reports.",
            )
            return False
        return self.open_invoice_by_id(iid)

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
        return f"{_INVOICE_LINE_TABLE_WIDTHS_KEY_PREFIX}_{self._company_settings_sid()}"

    def _company_settings_sid(self) -> str:
        """Stable id for this PC + company file (QSettings keys)."""
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
            return "default"
        return hashlib.sha256(path.encode("utf-8", errors="replace")).hexdigest()[:16]

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
        """Restore saved widths; DESCRIPTION always fills leftover viewport width."""
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
        desc = self._LINE_DESC_COL
        self._invoice_table_resizing = True
        hh = t.horizontalHeader()
        hh.blockSignals(True)
        try:
            for i in range(n):
                if i == desc:
                    continue
                m = self._invoice_col_minimum_width(i)
                t.setColumnWidth(i, max(m, parts[i]))
            self._sync_invoice_line_description_column_width_inner()
        finally:
            hh.blockSignals(False)
            self._invoice_table_resizing = False
        return True

    def _apply_default_invoice_line_column_widths(self) -> None:
        """Narrow SERVICED ON / JL / BOL / RATE / QTY / AMOUNT; DESCRIPTION takes the rest."""
        t = getattr(self, "_table", None)
        if t is None:
            return
        desc = self._LINE_DESC_COL
        self._invoice_table_resizing = True
        hh = t.horizontalHeader()
        hh.blockSignals(True)
        try:
            for i, default in enumerate(_INVOICE_LINE_COL_DEFAULT_PX):
                if i == desc or default <= 0:
                    continue
                m = self._invoice_col_minimum_width(i)
                t.setColumnWidth(i, max(m, int(default)))
            self._sync_invoice_line_description_column_width_inner()
        finally:
            hh.blockSignals(False)
            self._invoice_table_resizing = False

    def _sync_invoice_line_description_column_width_inner(self) -> None:
        """Set DESCRIPTION width so columns fill the viewport with no horizontal scrollbar."""
        t = getattr(self, "_table", None)
        if t is None:
            return
        n = t.columnCount()
        desc = self._LINE_DESC_COL
        if n < 1 or desc < 0 or desc >= n:
            return
        vw = max(0, t.viewport().width())
        sum_others = sum(t.columnWidth(i) for i in range(n) if i != desc)
        min_desc = self._invoice_col_minimum_width(desc)
        t.setColumnWidth(desc, int(max(min_desc, vw - sum_others)))

    def _sync_invoice_line_description_column_width_safe(self) -> None:
        """Re-anchor DESCRIPTION after show/layout."""
        if getattr(self, "_invoice_table_resizing", False):
            return
        t = getattr(self, "_table", None)
        if t is None:
            return
        self._invoice_table_resizing = True
        hh = t.horizontalHeader()
        hh.blockSignals(True)
        try:
            self._sync_invoice_line_description_column_width_inner()
        finally:
            hh.blockSignals(False)
            self._invoice_table_resizing = False
        self._schedule_persist_invoice_line_column_widths()

    def _on_invoice_line_header_section_resized(
        self, logical_index: int, old_size: int, new_size: int
    ) -> None:
        """Resize the dragged column; DESCRIPTION absorbs leftover width."""
        del old_size
        if getattr(self, "_invoice_table_resizing", False):
            return
        t = getattr(self, "_table", None)
        if t is None:
            return
        n = t.columnCount()
        if n < 2:
            return
        desc = self._LINE_DESC_COL

        self._invoice_table_resizing = True
        hh = t.horizontalHeader()
        hh.blockSignals(True)
        try:
            if logical_index != desc:
                m = self._invoice_col_minimum_width(logical_index)
                t.setColumnWidth(logical_index, max(m, int(new_size)))
            self._sync_invoice_line_description_column_width_inner()
        finally:
            hh.blockSignals(False)
            self._invoice_table_resizing = False
        self._schedule_persist_invoice_line_column_widths()

    def _refresh_browse_state(self) -> None:
        prev_slot = self._browse_slot
        if self._ap_conn is None:
            self._browse_ids = []
        else:
            self._browse_ids = business.list_invoice_ids_chronological(self._ap_conn)
        n = len(self._browse_ids)
        cid = self._current_invoice_id
        if cid is not None:
            try:
                self._browse_slot = self._browse_ids.index(cid)
            except ValueError:
                self._browse_slot = None
        else:
            if n == 0:
                self._browse_slot = None
            elif prev_slot is not None and prev_slot > n:
                self._browse_slot = n
        self._update_browse_buttons()

    def _update_browse_buttons(self) -> None:
        has_db = self._ap_conn is not None
        n = len(self._browse_ids)
        has_any = n > 0
        slot = self._browse_slot
        rev = has_db and has_any and (slot is None or slot > 0)
        fwd = has_db and has_any and slot is not None and slot < n
        self._btn_reverse.setEnabled(rev)
        self._btn_forward.setEnabled(fwd)

    def _clear_line_grid(self) -> None:
        for r in range(self._N_LINE_ROWS):
            self._invoice_line_code_committed[r] = ""
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
        paid = float(getattr(self, "_payments_applied", 0.0) or 0.0)
        bal = round(total - paid, 2)
        if getattr(self, "_lbl_payments", None) is not None:
            self._lbl_payments.setText(f"Payments Applied: ${paid:,.2f}")
        if getattr(self, "_lbl_balance", None) is not None:
            self._lbl_balance.setText(f"Balance Due: ${bal:,.2f}")

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

    def _setup_invoice_code_helpers(self) -> None:
        """QCompleter from ``invoice_item_codes``; apply default rate/description when Code text changes.

        Each Code cell is an :class:`_InvoiceCodeLineEdit`, so clicking or focusing
        opens the completer popup as a real dropdown list of saved codes; typing
        narrows the popup live (case-insensitive prefix filter).
        """
        self._invoice_code_completers: list[QCompleter] = []
        for row in range(self._N_LINE_ROWS):
            code_w = self._table.cellWidget(row, 1)
            if not isinstance(code_w, QLineEdit):
                continue
            comp = QCompleter(self)
            comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            comp.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            comp.setFilterMode(Qt.MatchFlag.MatchContains)
            code_w.setCompleter(comp)
            self._invoice_code_completers.append(comp)
            code_w.editingFinished.connect(
                partial(self._on_invoice_line_code_committed, row)
            )
            comp.activated.connect(
                partial(self._on_invoice_line_code_completer_activated, row)
            )
        self.refresh_invoice_item_codes()

    def refresh_invoice_item_codes(self) -> None:
        """Reload code list from DB (after Item List save or company file open)."""
        codes: list[str] = []
        if self._ap_conn is not None:
            try:
                codes = business.list_invoice_item_code_strings(self._ap_conn)
            except sqlite3.Error:
                codes = []
        model = QStringListModel(codes)
        for comp in getattr(self, "_invoice_code_completers", []):
            comp.setModel(model)

    def _line_subtotal_excluding_row(self, row_idx: int) -> float:
        """Sum of Rate×Qty for all lines except *row_idx* (for percent codes)."""
        total = 0.0
        for r in range(self._N_LINE_ROWS):
            if r == row_idx:
                continue
            rate_w = self._table.cellWidget(r, 4)
            qty_w = self._table.cellWidget(r, 5)
            if isinstance(rate_w, QDoubleSpinBox) and isinstance(qty_w, QDoubleSpinBox):
                total += round(float(rate_w.value()) * float(qty_w.value()), 2)
        return total

    def _on_invoice_line_code_completer_activated(self, row: int, _choice: str) -> None:
        """Popup pick updates the line edit; apply saved Code row when it differs from last commit."""
        self._on_invoice_line_code_committed(row)

    def _on_invoice_line_code_committed(self, row: int) -> None:
        """Tab/Enter or completer pick: if Code text changed, fill Rate/Description from **Codes** (or record free text)."""
        if self._suppress_invoice_line_recalc:
            return
        code_w = self._table.cellWidget(row, 1)
        if not isinstance(code_w, QLineEdit):
            return
        raw = code_w.text().strip()
        if raw == self._invoice_line_code_committed[row]:
            return
        if self._ap_conn is None:
            self._invoice_line_code_committed[row] = raw
            return
        if not raw:
            self._invoice_line_code_committed[row] = ""
            return
        item = business.get_invoice_item_code_by_code(self._ap_conn, raw)
        if item is None:
            self._invoice_line_code_committed[row] = raw
            return
        d = dict(item)
        self._apply_invoice_item_code_row(row, d)
        self._invoice_line_code_committed[row] = (d.get("code") or "").strip()

    def _apply_invoice_item_code_row(self, row: int, d: dict) -> None:
        """Fill Code/Description/Rate/Qty from a **Codes** row."""
        self._suppress_invoice_line_recalc = True
        try:
            code_w = self._table.cellWidget(row, 1)
            desc_w = self._table.cellWidget(row, 2)
            rate_w = self._table.cellWidget(row, 4)
            qty_w = self._table.cellWidget(row, 5)
            if isinstance(code_w, QLineEdit):
                code_w.setText((d.get("code") or "").strip())
            if isinstance(desc_w, QLineEdit):
                desc_w.setText((d.get("description") or "").strip())
            rv = float(d.get("rate_value") or 0.0)
            rk = (d.get("rate_kind") or "amount").strip().lower()
            if rk == "percent":
                sub_excl = self._line_subtotal_excluding_row(row)
                rate_amt = round(sub_excl * (rv / 100.0), 2)
            else:
                rate_amt = rv
            if isinstance(rate_w, QDoubleSpinBox):
                rate_w.setValue(rate_amt)
            if isinstance(qty_w, QDoubleSpinBox):
                qty_w.setValue(1.0)
        finally:
            self._suppress_invoice_line_recalc = False
        self._sync_invoice_line_row_total(row)
        self._recalc_invoice_footer_from_grid()

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

    def _hide_invoice_intake_handoff_banner(self) -> None:
        b = getattr(self, "_invoice_intake_handoff_banner", None)
        if b is None:
            return
        b.setVisible(False)
        b.setText("")

    def _on_clear_fields(self) -> None:
        if not self._prompt_save_unsaved_invoice():
            return
        self._current_invoice_id = None
        self._browse_slot = None
        self._suppress_invoice_header_autofill = True
        try:
            self._set_date_edit_iso(self._date, "")
            self._po.clear()
            self._job.clear()
            self._invoice_memo_notes = ""
            self._set_customer_message_text("")
            self._set_memo_edit_text("")
            self._payments_applied = 0.0
            self._hide_invoice_intake_handoff_banner()
            self._bill_customer_panel.clear_bill_to()
            self._set_ship_to_plain("")
            self._ship_to_autofill_customer_id = None
            self._clear_line_grid()
            self._inv_number.clear()
            self._invoice_number_autofill_value = ""
        finally:
            self._suppress_invoice_header_autofill = False
        self._reset_terms_and_due_date_for_draft()
        self._sync_invoice_number_suggestion()
        self._update_browse_buttons()
        self._sync_invoice_status_badge(status=None, balance_due=None)
        self._mark_form_clean()

    def _sync_invoice_status_badge(
        self, *, status: str | None, balance_due: float | None
    ) -> None:
        """Show green PAID when the invoice row is fully paid (Receive Payments excludes these)."""
        b = getattr(self, "_invoice_status_badge", None)
        if b is None:
            return
        bal = float(balance_due) if balance_due is not None else None
        st = (status or "").strip().lower()
        paid = st == "paid" or (bal is not None and bal <= 0.005)
        if paid:
            b.setText("PAID")
            b.setVisible(True)
        else:
            b.clear()
            b.setVisible(False)

    def refresh_loaded_invoice_payment_status(
        self, invoice_ids: Optional[list[int]] = None
    ) -> bool:
        """Re-sync PAID badge / balance for the currently loaded invoice from the live DB.

        Slot for :data:`ReceiveChecksScreen.arPaymentPosted`. Reads the invoice header
        only (no edit-field reload, so unsaved manual edits are preserved) and updates:

        * the PAID badge via :meth:`_sync_invoice_status_badge` (status + balance_due), and
        * browse state (``_browse_ids`` / nav buttons), so paid invoices that drop off
          the open list are reflected in Reverse / Forward.

        Returns ``True`` when the loaded invoice was refreshed; ``False`` otherwise
        (no DB connection, no invoice loaded, or *invoice_ids* did not include the
        currently loaded invoice id).
        """
        cid = self._current_invoice_id
        if cid is None or self._ap_conn is None:
            return False
        if invoice_ids is not None:
            try:
                wanted = {int(x) for x in invoice_ids}
            except (TypeError, ValueError):
                wanted = set()
            if cid not in wanted:
                return False
        try:
            inv, _lines = business.get_invoice_detail(self._ap_conn, cid)
        except sqlite3.Error:
            return False
        if inv is None:
            return False
        d = dict(inv)
        try:
            bd = float(d.get("balance_due") or 0.0)
        except (TypeError, ValueError):
            bd = None
        raw_st = d.get("status")
        st_str = str(raw_st).strip() if raw_st is not None else ""
        self._sync_invoice_status_badge(status=st_str or None, balance_due=bd)
        self._refresh_browse_state()
        return True

    def _go_to_new_invoice_draft(self) -> None:
        self._current_invoice_id = None
        self._browse_slot = None
        self._suppress_invoice_header_autofill = True
        try:
            self._po.clear()
            self._job.clear()
            self._invoice_memo_notes = ""
            self._set_customer_message_text("")
            self._set_memo_edit_text("")
            self._payments_applied = 0.0
            self._hide_invoice_intake_handoff_banner()
            self._bill_customer_panel.clear_bill_to()
            self._set_ship_to_plain("")
            self._ship_to_autofill_customer_id = None
            self._clear_line_grid()
            self._inv_number.clear()
            self._invoice_number_autofill_value = ""
        finally:
            self._suppress_invoice_header_autofill = False
        self._reset_terms_and_due_date_for_draft()
        self._sync_invoice_number_suggestion()
        self._refresh_browse_state()
        self._browse_slot = len(self._browse_ids)
        self._update_browse_buttons()
        self._sync_invoice_status_badge(status=None, balance_due=None)
        self._mark_form_clean()

    def _load_invoice_by_list_index(self, list_index: int) -> None:
        n = len(self._browse_ids)
        if list_index < 0:
            return
        if n == 0:
            return
        if list_index == n:
            self._go_to_new_invoice_draft()
            return
        if list_index > n:
            return
        self._load_invoice_into_form(self._browse_ids[list_index])
        self._browse_slot = list_index
        self._update_browse_buttons()

    def _load_invoice_into_form(self, invoice_id: int) -> None:
        if self._ap_conn is None:
            return
        inv, lines = business.get_invoice_detail(self._ap_conn, invoice_id)
        if inv is None:
            return
        self._hide_invoice_intake_handoff_banner()
        d = dict(inv)
        num = (d.get("invoice_number") or "").strip()
        self._inv_number.setText(num)
        self._invoice_number_autofill_value = num
        iso = (d.get("invoice_date") or "").strip()
        self._suppress_invoice_header_autofill = True
        try:
            self._set_date_edit_iso(self._date, iso)
            terms_raw = (d.get("terms") or "").strip()
            self._set_terms_text(terms_raw)
            due_raw = (d.get("due_date") or "").strip()
            if due_raw:
                self._set_date_edit_iso(self._due_date, due_raw)
            else:
                self._apply_due_date_from_terms()
            po, job, message, memo_rest = self._split_memo_po_job((d.get("memo") or "").strip())
            self._po.setText(po)
            self._job.setText(job)
            self._set_customer_message_text(message)
            self._invoice_memo_notes = memo_rest
            self._set_memo_edit_text(memo_rest)
            self._bill_customer_panel.reload_customers()
            try:
                cid = int(d["customer_id"])
            except (KeyError, TypeError, ValueError):
                self._bill_customer_panel.clear_bill_to()
            else:
                self._bill_customer_panel.select_customer_by_id(cid)
            ship_saved = (d.get("ship_to") or "").strip()
            if ship_saved:
                self._set_ship_to_plain(ship_saved)
            else:
                self._set_ship_to_plain(self._bill_to[1].toPlainText())
            try:
                self._ship_to_autofill_customer_id = int(d["customer_id"])
            except (KeyError, TypeError, ValueError):
                self._ship_to_autofill_customer_id = None
        finally:
            self._suppress_invoice_header_autofill = False
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
                if isinstance(dt_w, QLineEdit):
                    dt_w.clear()
                if isinstance(code_w, QLineEdit):
                    code_w.clear()
                if isinstance(bol_w, QLineEdit):
                    bol_w.clear()
                if isinstance(desc_w, QLineEdit):
                    desc_w.clear()
                serviced, code, desc, bol = parse_invoice_line_description(
                    row.get("description") or ""
                )
                if isinstance(dt_w, QLineEdit):
                    dt_w.setText(serviced)
                if isinstance(code_w, QLineEdit):
                    code_w.setText(code)
                if isinstance(desc_w, QLineEdit):
                    desc_w.setText(desc)
                if isinstance(bol_w, QLineEdit):
                    bol_w.setText(bol)
                if isinstance(rate_w, QDoubleSpinBox):
                    rate_w.setValue(float(row.get("rate") or 0.0))
                if isinstance(qty_w, QDoubleSpinBox):
                    qty_w.setValue(float(row.get("qty") or 0.0))
        finally:
            self._suppress_invoice_line_recalc = False
        for r in range(self._N_LINE_ROWS):
            self._sync_invoice_line_row_total(r)
        self._recalc_invoice_footer_from_grid()
        for i in range(self._N_LINE_ROWS):
            cw = self._table.cellWidget(i, 1)
            self._invoice_line_code_committed[i] = (
                cw.text().strip() if isinstance(cw, QLineEdit) else ""
            )
        self._current_invoice_id = invoice_id
        try:
            tot = float(d.get("total") or 0.0)
        except (TypeError, ValueError):
            tot = 0.0
        try:
            bd = float(d.get("balance_due") or 0.0)
        except (TypeError, ValueError):
            bd = None
        if bd is None:
            self._payments_applied = 0.0
        else:
            self._payments_applied = max(0.0, round(tot - float(bd), 2))
        raw_st = d.get("status")
        st_str = str(raw_st).strip() if raw_st is not None else ""
        self._sync_invoice_status_badge(status=st_str or None, balance_due=bd)
        self._recalc_invoice_footer_from_grid()
        self._mark_form_clean()

    def _set_customer_message_text(self, text: str) -> None:
        w = getattr(self, "_customer_message", None)
        if w is None:
            return
        raw = (text or "").strip()
        idx = w.findText(raw)
        if idx < 0 and raw:
            w.addItem(raw)
            idx = w.findText(raw)
        w.setCurrentIndex(max(0, idx))
        le = w.lineEdit()
        if le is not None:
            le.setText(raw)

    def _set_memo_edit_text(self, text: str) -> None:
        w = getattr(self, "_memo_edit", None)
        if w is not None:
            w.setText(text or "")

    def _split_memo_po_job(self, memo: str) -> tuple[str, str, str, str]:
        """Split stored memo into PO, Job, customer message, and remaining free text."""
        po, job, message = "", "", ""
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
            elif low.startswith("message:"):
                message = line.split(":", 1)[1].strip()
            else:
                extra.append(raw)
        return po, job, message, "\n".join(extra).strip()

    def _on_reverse_invoice(self) -> None:
        if not self._prompt_save_unsaved_invoice():
            return
        self._refresh_browse_state()
        n = len(self._browse_ids)
        if n == 0:
            return
        slot = self._browse_slot
        if slot is None:
            self._load_invoice_by_list_index(n - 1)
            return
        if slot == 0:
            return
        if slot == n:
            self._load_invoice_by_list_index(n - 1)
            return
        self._load_invoice_by_list_index(slot - 1)

    def _on_forward_invoice(self) -> None:
        if not self._prompt_save_unsaved_invoice():
            return
        self._refresh_browse_state()
        n = len(self._browse_ids)
        if n == 0:
            return
        slot = self._browse_slot
        if slot is None:
            return
        if slot >= n:
            return
        self._load_invoice_by_list_index(slot + 1)

    def _build_invoice_memo(self) -> str:
        parts: list[str] = []
        po = self._po.text().strip()
        job = self._job.text().strip()
        msg_w = getattr(self, "_customer_message", None)
        message = msg_w.currentText().strip() if msg_w is not None else ""
        memo_w = getattr(self, "_memo_edit", None)
        extra = (memo_w.text() if memo_w is not None else self._invoice_memo_notes or "").strip()
        if po:
            parts.append(f"PO: {po}")
        if job:
            parts.append(f"Job: {job}")
        if message:
            parts.append(f"Message: {message}")
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
        return rows or [{"description": "Service", "qty": 1.0, "rate": 0.0}]

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

    def _invoice_form_fingerprint(self) -> tuple:
        """Comparable snapshot of fields that Save writes."""
        lines: list[tuple] = []
        for r in range(self._N_LINE_ROWS):
            dt_w = self._table.cellWidget(r, 0)
            code_w = self._table.cellWidget(r, 1)
            desc_w = self._table.cellWidget(r, 2)
            bol_w = self._table.cellWidget(r, 3)
            rate_w = self._table.cellWidget(r, 4)
            qty_w = self._table.cellWidget(r, 5)
            lines.append(
                (
                    dt_w.text().strip() if isinstance(dt_w, QLineEdit) else "",
                    code_w.text().strip() if isinstance(code_w, QLineEdit) else "",
                    desc_w.text().strip() if isinstance(desc_w, QLineEdit) else "",
                    bol_w.text().strip() if isinstance(bol_w, QLineEdit) else "",
                    round(float(rate_w.value()), 2) if isinstance(rate_w, QDoubleSpinBox) else 0.0,
                    round(float(qty_w.value()), 2) if isinstance(qty_w, QDoubleSpinBox) else 0.0,
                )
            )
        msg_w = getattr(self, "_customer_message", None)
        memo_w = getattr(self, "_memo_edit", None)
        return (
            self.selected_bill_to_customer_id(),
            self._inv_number.text().strip(),
            self._iso_from_date_edit(self._date),
            self._iso_from_date_edit(self._due_date),
            self._terms.currentText().strip(),
            self._po.text().strip(),
            self._job.text().strip(),
            (msg_w.currentText().strip() if msg_w is not None else ""),
            (memo_w.text().strip() if memo_w is not None else ""),
            self._ship_to_plain(),
            tuple(lines),
        )

    def _form_has_user_content(self) -> bool:
        """True when a new draft has more than the autofilled invoice # / date."""
        if self.selected_bill_to_customer_id() is not None:
            return True
        if self._po.text().strip() or self._job.text().strip():
            return True
        msg_w = getattr(self, "_customer_message", None)
        if msg_w is not None and msg_w.currentText().strip():
            return True
        memo_w = getattr(self, "_memo_edit", None)
        if memo_w is not None and memo_w.text().strip():
            return True
        if self._ship_to_plain().strip():
            return True
        for r in range(self._N_LINE_ROWS):
            dt_w = self._table.cellWidget(r, 0)
            code_w = self._table.cellWidget(r, 1)
            desc_w = self._table.cellWidget(r, 2)
            bol_w = self._table.cellWidget(r, 3)
            rate_w = self._table.cellWidget(r, 4)
            qty_w = self._table.cellWidget(r, 5)
            if isinstance(dt_w, QLineEdit) and dt_w.text().strip():
                return True
            if isinstance(code_w, QLineEdit) and code_w.text().strip():
                return True
            if isinstance(desc_w, QLineEdit) and desc_w.text().strip():
                return True
            if isinstance(bol_w, QLineEdit) and bol_w.text().strip():
                return True
            if isinstance(rate_w, QDoubleSpinBox) and abs(float(rate_w.value())) > 0.0005:
                return True
            if isinstance(qty_w, QDoubleSpinBox) and abs(float(qty_w.value())) > 0.0005:
                return True
        return False

    def _mark_form_clean(self) -> None:
        self._clean_fingerprint = self._invoice_form_fingerprint()

    def _is_form_dirty(self) -> bool:
        """Used by the main window when leaving the Invoice tab."""
        if self._ap_conn is None:
            return False
        if self._current_invoice_id is None and not self._form_has_user_content():
            return False
        return self._invoice_form_fingerprint() != self._clean_fingerprint

    def _write_pdf_if_folder_already_set(self, inv_id: int) -> None:
        """Write ``<invoice#>.pdf`` only when Invoice Options already has a folder (no picker)."""
        folder = get_invoice_output_folder()
        if not folder or inv_id is None:
            return
        num = self._inv_number.text().strip()
        pdf_path = os.path.join(folder, invoice_pdf_basename(num))
        self._write_invoice_pdf_file(inv_id, pdf_path)

    def _prompt_save_unsaved_invoice(self) -> bool:
        """If the form is dirty, ask **Save invoice ###?** Yes / No / Cancel.

        Yes: save to the company file, and write a PDF when a folder is already set.
        No: do not save (caller may discard or replace the form).
        Cancel or window **X**: stay; keep the data; do not save or wipe.
        Returns ``False`` to stay (Cancel / X, or Yes but save failed).
        """
        if not self._is_form_dirty():
            return True
        num = self._inv_number.text().strip() or "this invoice"
        choice = message_box_question_yes_no_cancel(
            self,
            "Save invoice",
            f"Save invoice {num}?",
            yes_tip="Save this invoice to the company file, then continue.",
            no_tip="Discard these changes and continue.",
            cancel_tip="Stay on this invoice. Keep the data. Do not save.",
            default_yes=True,
        )
        if choice == "cancel":
            return False
        if choice != "yes":
            return True
        ok, msg, inv_id = self._save_invoice_data_only()
        if not ok:
            self._invoice_feedback_message(msg)
            return False
        if inv_id is not None:
            self._current_invoice_id = inv_id
            self._write_pdf_if_folder_already_set(inv_id)
        self._mark_form_clean()
        return True

    def _confirm_leave_loaded_invoice(self) -> bool:
        """Ask **Save invoice ###?** Yes / No / Cancel when leaving the Invoice tab.

        Yes saves (company file + PDF if a folder is already set). No discards and leaves.
        Cancel or **X** stays on the invoice with the data intact. Returns ``False`` to stay
        (Cancel / X, or Yes but save failed).
        """
        was_dirty = self._is_form_dirty()
        if not self._prompt_save_unsaved_invoice():
            return False
        if was_dirty and self._is_form_dirty():
            self._go_to_new_invoice_draft()
        return True

    def _confirm_overwrite_invoice_pdf(self, pdf_path: str) -> bool:
        name = os.path.basename(pdf_path)
        if not os.path.isfile(pdf_path):
            return True
        return message_box_question_yes_no(
            self,
            "Overwrite PDF",
            f"{name} already exists. Overwrite?",
            yes_tip="Replace the existing PDF.",
            no_tip="Keep the existing file.",
            default_yes=False,
        )

    def _write_invoice_pdf_file(self, inv_id: int, pdf_path: str) -> bool:
        """Write Chavan-layout PDF. Asks before overwrite. Returns True if written."""
        if not self._confirm_overwrite_invoice_pdf(pdf_path):
            return False
        assert self._ap_conn is not None
        try:
            save_invoice_pdf(self._ap_conn, inv_id, pdf_path)
        except OSError as exc:
            self._invoice_feedback_message(
                f"Invoice saved, but the PDF could not be written: {exc}"
            )
            return False
        except Exception as exc:  # noqa: BLE001
            self._invoice_feedback_message(
                f"Invoice saved, but PDF export failed: {exc}"
            )
            return False
        return True

    def _try_persist_invoice(self) -> tuple[bool, str, int | None]:
        """Create or update the current invoice row. Returns ``(ok, message, invoice_id)``.

        Silent DB only — no PDF, print, folder, or company-file UI here.
        """
        if self._ap_conn is None:
            return False, "Connect a company file to save invoices.", None
        cid = self.selected_bill_to_customer_id()
        if cid is None:
            return False, "Select a customer in Bill To before saving or printing.", None
        num = self._inv_number.text().strip()
        if not num:
            return False, "Enter an invoice number.", None
        iso_date = self._iso_from_date_edit(self._date)
        if not iso_date:
            return False, "Enter a valid invoice date.", None
        due_s = self._iso_from_date_edit(self._due_date)
        terms_s = self._terms.currentText().strip()
        ship_s = self._ship_to_plain()
        memo = self._build_invoice_memo()
        lines = self._collect_invoice_lines()
        conn = self._ap_conn
        edit_id = self._current_invoice_id
        tax_pct = self._invoice_tax_rate_pct()
        try:
            if edit_id is not None:
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
                    ship_to=ship_s,
                    terms=terms_s,
                )
                self.openInvoicesChanged.emit()
                self._mark_form_clean()
                return True, "", edit_id
            inv_id = business.create_invoice(
                conn,
                cid,
                num,
                iso_date,
                due_date=due_s,
                memo=memo,
                lines=lines,
                tax_rate_pct=tax_pct,
                ship_to=ship_s,
                terms=terms_s,
            )
        except ValueError as exc:
            return False, str(exc), None
        except sqlite3.IntegrityError as exc:
            err = str(exc).upper()
            if "UNIQUE" in err:
                message_box_warning_ok(
                    self,
                    "Duplicate invoice number",
                    "That invoice number is already used in this company file. "
                    "Enter a different invoice number before saving.",
                    ok_tip="Close; change the Invoice # field to a value that is not already saved.",
                )
                return False, "", None
            return False, str(exc), None
        except sqlite3.Error as exc:
            return False, str(exc), None
        self.openInvoicesChanged.emit()
        self._mark_form_clean()
        return True, "", inv_id

    def _save_invoice_data_only(self) -> tuple[bool, str, int | None]:
        """Write current invoice to SQLite only; never opens print/PDF/file dialogs."""
        return self._try_persist_invoice()

    def _persist_invoice_and_optional_pdf(self) -> tuple[bool, int | None, bool]:
        """Save to DB (+ optional prefs PDF). Returns ``(ok, invoice_id, was_new)``."""
        was_new = self._current_invoice_id is None
        ok, msg, inv_id = self._save_invoice_data_only()
        if not ok:
            self._invoice_feedback_message(msg)
            return False, None, was_new
        assert inv_id is not None and self._ap_conn is not None
        folder = ensure_invoice_output_folder(self)
        if folder:
            num = self._inv_number.text().strip()
            pdf_path = os.path.join(folder, invoice_pdf_basename(num))
            self._write_invoice_pdf_file(inv_id, pdf_path)
        else:
            self._invoice_feedback_message(
                "Invoice saved to the company file. "
                "Edit → Preferences → Invoice Options: set a PDF folder to auto-save on Save."
            )
        self._refresh_browse_state()
        return True, inv_id, was_new

    def _on_save_invoice(self) -> None:
        # Phantom dialog fix: only a real Save & New button click may persist from this slot.
        if self.sender() is not self._btn_save:
            return
        ok, inv_id, was_new = self._persist_invoice_and_optional_pdf()
        if not ok or inv_id is None:
            return
        if was_new:
            self._go_to_new_invoice_draft()
        else:
            self._load_invoice_into_form(inv_id)

    def _on_save_close_invoice(self) -> None:
        if self.sender() is not self._btn_save_close:
            return
        ok, inv_id, _was_new = self._persist_invoice_and_optional_pdf()
        if not ok or inv_id is None:
            return
        self._load_invoice_into_form(inv_id)

    def _on_ribbon_save_invoice(self) -> None:
        if self.sender() is not self._btn_ribbon_save:
            return
        ok, inv_id, _was_new = self._persist_invoice_and_optional_pdf()
        if not ok or inv_id is None:
            return
        self._load_invoice_into_form(inv_id)

    def _on_export_pdf_as(self) -> None:
        if self.sender() is not self._btn_export_pdf:
            return
        if self._ap_conn is None:
            self._invoice_feedback_message("Connect a company file to save a PDF.")
            return
        ok, msg, inv_id = self._save_invoice_data_only()
        if not ok:
            self._invoice_feedback_message(msg)
            return
        assert inv_id is not None
        num = self._inv_number.text().strip()
        path = prompt_invoice_save_as_path(
            self, self._company_settings_sid(), invoice_pdf_basename(num)
        )
        if not path:
            self._refresh_browse_state()
            self._load_invoice_into_form(inv_id)
            return
        self._write_invoice_pdf_file(inv_id, path)
        self._refresh_browse_state()
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
                f"Could not prepare the invoice for printing: {exc}"
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
            self._invoice_feedback_message("Connect a company file to print invoices.")
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

    # -- Find (QB Pro-style search) -----------------------------------------

    def find_invoice_id_matching(self, needle: str) -> Optional[int]:
        """Return the first saved invoice id whose number / customer / total / date matches *needle*.

        Called by ``_on_find_invoice`` and by unit tests; pure data path with no UI.
        """
        if self._ap_conn is None:
            return None
        needle = (needle or "").strip()
        if not needle:
            return None
        rows = business.list_invoices(self._ap_conn)
        hit = first_matching_row(
            rows,
            needle,
            number_fields=("invoice_number",),
            name_fields=("customer_name",),
            amount_fields=("total",),
            date_fields=("invoice_date",),
        )
        if hit is None:
            return None
        return int(hit["id"])

    def _on_find_invoice(self) -> None:
        if self.sender() is not self._btn_find:
            return
        if self._ap_conn is None:
            self._invoice_feedback_message("Connect a company file to search invoices.")
            return
        text, ok = QInputDialog.getText(
            self,
            "Find invoice",
            "Invoice #, customer, amount, or date (MM/DD/YYYY):",
        )
        if not ok:
            return
        needle = (text or "").strip()
        if not needle:
            return
        if not self._prompt_save_unsaved_invoice():
            return
        inv_id = self.find_invoice_id_matching(needle)
        if inv_id is None:
            message_box_information_ok(
                self,
                "Find invoice",
                f"No saved invoice matches “{needle}”.",
                ok_tip="Close; try another invoice #, customer, amount, or date.",
            )
            return
        self._load_invoice_into_form(inv_id)
        self._refresh_browse_state()

    # -- Email --------------------------------------------------------------

    def _build_invoice_mailto_url(self, invoice_id: int) -> Optional[QUrl]:
        """Compose a ``mailto:`` URL for *invoice_id*, or ``None`` if no customer email."""
        if self._ap_conn is None:
            return None
        inv, _lines = business.get_invoice_detail(self._ap_conn, invoice_id)
        if inv is None:
            return None
        d = dict(inv)
        cust = business.get_customer(self._ap_conn, int(d["customer_id"]))
        if cust is None:
            return None
        email = (dict(cust).get("email") or "").strip()
        if not email:
            return None
        num = (d.get("invoice_number") or "").strip() or f"#{invoice_id}"
        total = float(d.get("total") or 0)
        date_iso = (d.get("invoice_date") or "").strip()
        date_us = format_iso_to_us_display(date_iso) if date_iso else ""
        url = QUrl(f"mailto:{email}")
        from PySide6.QtCore import QUrlQuery
        q = QUrlQuery()
        q.addQueryItem("subject", f"Invoice {num}")
        body_lines = [
            f"Invoice {num}",
        ]
        if date_us:
            body_lines.append(f"Date: {date_us}")
        body_lines.append(f"Amount due: ${total:,.2f}")
        body_lines.append("")
        body_lines.append("Thanks,")
        q.addQueryItem("body", "\n".join(body_lines))
        url.setQuery(q)
        return url

    def _on_email_invoice(self) -> None:
        if self.sender() is not self._btn_email:
            return
        if self._ap_conn is None:
            self._invoice_feedback_message("Connect a company file to email invoices.")
            return
        cid = self.selected_bill_to_customer_id()
        if cid is None:
            message_box_warning_ok(
                self,
                "Email invoice",
                "Choose a customer on the Bill To panel before emailing.",
                ok_tip="Close; pick a customer, then click Email again.",
            )
            return
        cust = business.get_customer(self._ap_conn, int(cid))
        if cust is None:
            message_box_warning_ok(
                self,
                "Email invoice",
                "The selected customer could not be found.",
                ok_tip="Close; reselect the customer and try again.",
            )
            return
        email_addr = (dict(cust).get("email") or "").strip()
        if not email_addr:
            name = (dict(cust).get("name") or "This customer").strip()
            message_box_warning_ok(
                self,
                "Email invoice",
                f"{name} has no email address on file. Add one in Customers → Edit customer.",
                ok_tip="Close; add an email to the customer record and try again.",
            )
            return
        ok, msg, inv_id = self._save_invoice_data_only()
        if not ok or inv_id is None:
            self._invoice_feedback_message(msg or "Could not save invoice before emailing.")
            return
        url = self._build_invoice_mailto_url(inv_id)
        if url is None:
            message_box_warning_ok(
                self,
                "Email invoice",
                "Could not build the email draft (no customer email on the saved invoice).",
                ok_tip="Close; add an email to the customer record and try again.",
            )
            return
        opened = QDesktopServices.openUrl(url)
        if not opened:
            message_box_warning_ok(
                self,
                "Email invoice",
                "Your operating system has no default mail handler. "
                f"Copy this address and email the invoice manually: {email_addr}",
                ok_tip="Close; set a default mail app in Windows Settings → Apps → Default apps.",
            )
            return
        self._load_invoice_into_form(inv_id)
        self._invoice_feedback_message(
            f"Email draft opened for {email_addr} (invoice saved)."
        )

    def _address_box(
        self,
        caption: str,
        *,
        height_px: int | None = None,
        max_width_px: int | None = None,
    ) -> tuple[QFrame, QPlainTextEdit]:
        fr = QFrame()
        fr.setStyleSheet(
            f"QFrame {{ background-color: {_INV_PANEL}; border: 1px solid {_INV_GRID}; "
            "border-radius: 6px; }}"
        )
        if max_width_px is not None:
            fr.setMaximumWidth(max_width_px)
            fr.setSizePolicy(
                QSizePolicy.Policy.Maximum,
                QSizePolicy.Policy.Preferred,
            )
        lay = QVBoxLayout(fr)
        lay.setContentsMargins(6, 2, 6, 4)
        lay.setSpacing(2)
        cap = QLabel(caption)
        cap.setStyleSheet(f"color: {_INV_TEXT}; font-size: 11px; font-weight: 600; background: transparent;")
        te = QPlainTextEdit()
        te.setPlaceholderText(caption)
        te.setFixedHeight(
            height_px if height_px is not None else _INVOICE_BILL_TO_TEXT_HEIGHT_PX
        )
        te.setStyleSheet(
            f"QPlainTextEdit {{ background: {WORKFLOW_INPUT_BG}; color: {_INV_TEXT}; "
            f"border: 1px solid {_INV_GRID}; border-radius: 4px; padding: 2px; }}"
        )
        te.setToolTip(
            "Ship To is saved with this invoice. Selecting a customer copies Bill To "
            "(QuickBooks Pro default when the customer has no separate shipping address)."
        )
        lay.addWidget(cap)
        lay.addWidget(te)
        return fr, te
