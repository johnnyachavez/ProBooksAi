"""Reusable **Bill To** customer lookup for the Invoice screen (and future AR UIs).

Uses ``probooksai.business`` customer rows (same source as Business → Customers / Customer Corral).
Jobs under a parent appear as ``Parent Name > Job Name`` so users can bill to the parent or a
specific job; each list row still maps to one ``customers.id`` for ``invoice.customer_id``.
Optional ``Contact:`` prefix in ``notes`` for quick-add contact name.
"""

from __future__ import annotations

import sqlite3
from PySide6.QtCore import QEvent, QObject, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from probooksai import business

from desktop_app.new_customer_dialog import run_new_customer_dialog
from desktop_app.theme import (
    WORKFLOW_CONTROL_FACE,
    WORKFLOW_CONTROL_HOVER,
    WORKFLOW_CONTROL_PRESSED,
    WORKFLOW_GRID as _INV_GRID,
    WORKFLOW_INPUT_BG,
    WORKFLOW_PANEL_BG as _INV_PANEL,
    WORKFLOW_STRIP_BTN_OUTLINE,
    WORKFLOW_TEXT as _INV_TEXT,
)


def format_customer_bill_to_plaintext(customer: dict) -> str:
    """Format a ``customers`` row for the Bill To multi-line block."""
    lines: list[str] = []
    name = (customer.get("name") or "").strip()
    if name:
        lines.append(name)

    addr = (customer.get("address") or "").strip()
    if addr:
        lines.append(addr)

    notes = (customer.get("notes") or "").strip()
    contact = ""
    extra_notes = ""
    if notes:
        lower = notes.lower()
        if lower.startswith("contact:"):
            first, _, rest = notes.partition("\n")
            contact = first.split(":", 1)[1].strip() if ":" in first else ""
            extra_notes = rest.strip()
        else:
            extra_notes = notes

    if contact:
        lines.append(f"Contact: {contact}")
    ph = (customer.get("phone") or "").strip()
    if ph:
        lines.append(f"Phone: {ph}")
    em = (customer.get("email") or "").strip()
    if em:
        lines.append(f"Email: {em}")
    if extra_notes:
        lines.append(extra_notes)

    return "\n".join(lines)


class CustomerBillToPanel(QFrame):
    """Bill To: type-ahead customer combo + details text; quick-add when needed.

    Focus in the customer field opens the dropdown immediately; typing filters the list
    (completer ``MatchContains``). Enter confirms the highlighted row; Tab confirms when
    the popup is open, then moves focus.
    """

    customerIdChanged = Signal(object)
    customerCreated = Signal(int)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        ap_conn: sqlite3.Connection | None = None,
        layout_max_width_px: int | None = None,
        bill_plain_height_px: int | None = None,
        combo_min_width_px: int | None = None,
        show_new_customer_button: bool = True,
    ) -> None:
        super().__init__(parent)
        self._conn: sqlite3.Connection | None = ap_conn
        self._customer_id: int | None = None
        self._filling_combo = False
        self.setStyleSheet(
            f"QFrame {{ background-color: {_INV_PANEL}; border: 1px solid {_INV_GRID}; "
            "border-radius: 6px; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 8)
        lay.setSpacing(4)
        cap = QLabel("Bill To")
        cap.setStyleSheet(f"color: {_INV_TEXT}; font-size: 12px; font-weight: 600; background: transparent;")
        lay.addWidget(cap)

        row = QHBoxLayout()
        row.setSpacing(8)
        self._combo = QComboBox()
        self._combo.setEditable(True)
        self._combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._combo.setMinimumWidth(
            combo_min_width_px if combo_min_width_px is not None else 200
        )
        self._combo.setStyleSheet(
            f"QComboBox {{ background: {WORKFLOW_INPUT_BG}; border: 1px solid {_INV_GRID}; "
            f"padding: 4px 8px; color: {_INV_TEXT}; border-radius: 4px; }}"
        )
        le = self._combo.lineEdit()
        if le is not None:
            le.setPlaceholderText("Type to find customer…")
            le.installEventFilter(self)
        comp = self._combo.completer()
        if comp is not None:
            comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            comp.setFilterMode(Qt.MatchFlag.MatchContains)
            comp.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)

        self._combo.setMaxVisibleItems(20)

        self._btn_new = QPushButton("New customer…")
        self._btn_new.setToolTip(
            "Add a customer to the company file when no match exists; Bill To fills automatically."
        )
        self._btn_new.setStyleSheet(
            f"QPushButton {{ background-color: {WORKFLOW_CONTROL_FACE}; color: {_INV_TEXT}; "
            f"border: 1px solid {WORKFLOW_STRIP_BTN_OUTLINE}; border-radius: 4px; padding: 4px 10px; }}"
            f"QPushButton:hover {{ background-color: {WORKFLOW_CONTROL_HOVER}; }}"
            f"QPushButton:pressed {{ background-color: {WORKFLOW_CONTROL_PRESSED}; }}"
        )
        self._btn_new.clicked.connect(self._on_new_customer)
        self._btn_new.setVisible(show_new_customer_button)
        row.addWidget(self._combo, 1)
        if show_new_customer_button:
            row.addWidget(self._btn_new, 0)
        lay.addLayout(row)

        self._bill_te = QPlainTextEdit()
        self._bill_te.setPlaceholderText("Bill To")
        self._bill_te.setFixedHeight(
            bill_plain_height_px if bill_plain_height_px is not None else 68
        )
        self._bill_te.setStyleSheet(
            f"QPlainTextEdit {{ background: {WORKFLOW_INPUT_BG}; color: {_INV_TEXT}; "
            f"border: 1px solid {_INV_GRID}; border-radius: 4px; padding: 4px; }}"
        )
        lay.addWidget(self._bill_te)

        self._combo.currentIndexChanged.connect(self._on_combo_index_changed)
        if layout_max_width_px is not None:
            self.setMaximumWidth(layout_max_width_px)
            self.setSizePolicy(
                QSizePolicy.Policy.Maximum,
                QSizePolicy.Policy.Preferred,
            )
        self._apply_conn_state()
        if self._conn is not None:
            self.reload_customers()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        le = self._combo.lineEdit()
        if le is not None and obj is le:
            et = event.type()
            if et == QEvent.Type.FocusIn:
                if (
                    not self._filling_combo
                    and self._conn is not None
                    and self._combo.count() > 0
                ):
                    QTimer.singleShot(0, self._bill_to_show_popup_deferred)
            elif et == QEvent.Type.KeyPress:
                ke = event
                if (
                    ke.key() == Qt.Key.Key_Tab
                    and ke.modifiers() == Qt.KeyboardModifier.NoModifier
                    and self._combo.view().isVisible()
                ):
                    view = self._combo.view()
                    row = view.currentIndex().row()
                    if row < 0:
                        row = self._combo.currentIndex()
                    if row < 0:
                        row = 0
                    if 0 <= row < self._combo.count():
                        self._combo.setCurrentIndex(row)
                        self._combo.hidePopup()
                        ke.accept()
                        return True
        return super().eventFilter(obj, event)

    def _bill_to_show_popup_deferred(self) -> None:
        """Open customer list on first focus (after line edit receives focus)."""
        if self._filling_combo:
            return
        le = self._combo.lineEdit()
        if le is None or not le.hasFocus():
            return
        if self._conn is None or self._combo.count() < 1:
            return
        self._combo.showPopup()

    def bill_text_edit(self) -> QPlainTextEdit:
        return self._bill_te

    def clear_bill_to(self) -> None:
        """Clear Bill To text and customer selection (draft / clear form)."""
        self._customer_id = None
        self._bill_te.clear()
        self._filling_combo = True
        self._combo.blockSignals(True)
        self._combo.setCurrentIndex(-1)
        le = self._combo.lineEdit()
        if le is not None:
            le.clear()
        self._combo.blockSignals(False)
        self._filling_combo = False

    def select_customer_by_id(self, cid: int) -> None:
        """Select a customer by id and fill Bill To from the database."""
        self._apply_customer_id(cid)

    def selected_customer_id(self) -> int | None:
        return self._customer_id

    def set_connection(self, conn: sqlite3.Connection | None) -> None:
        self._conn = conn
        self._apply_conn_state()
        self.reload_customers()

    def _apply_conn_state(self) -> None:
        on = self._conn is not None
        self._combo.setEnabled(on)
        self._btn_new.setEnabled(on)
        if not on:
            tip = (
                "Connect a company database to search customers (same file as Business → Customers)."
            )
        else:
            tip = (
                "Pick or type a customer; jobs show as Parent > Job. Bill To fills from Customer Center. "
                "Use **New customer…** if no match."
            )
        self.setToolTip(tip)
        self._combo.setToolTip(tip)
        self._bill_te.setToolTip("Bill To details; filled when you select a customer (editable).")

    def reload_customers(self) -> None:
        keep_id = self._customer_id
        self._filling_combo = True
        self._combo.blockSignals(True)
        self._combo.clear()
        cur_text = ""
        le = self._combo.lineEdit()
        if le is not None:
            cur_text = le.text()
        if self._conn is not None:
            try:
                for cid, label in business.list_bill_to_customer_choices(self._conn):
                    self._combo.addItem(label, cid)
            except (sqlite3.Error, KeyError, TypeError, ValueError):
                pass
        self._combo.setCurrentIndex(-1)
        if le is not None:
            le.setText(cur_text)
            le.setPlaceholderText("Type to find customer…")
        self._combo.blockSignals(False)
        self._filling_combo = False
        if keep_id is not None and self._conn is not None:
            idx = self._combo.findData(keep_id, Qt.ItemDataRole.UserRole)
            if idx >= 0:
                self._apply_customer_id(keep_id)

    def _on_combo_index_changed(self, index: int) -> None:
        if self._filling_combo or index < 0:
            return
        raw = self._combo.itemData(index, Qt.ItemDataRole.UserRole)
        if raw is None:
            return
        try:
            cid = int(raw)
        except (TypeError, ValueError):
            return
        self._apply_customer_id(cid)

    def _apply_customer_id(self, cid: int) -> None:
        if self._conn is None:
            return
        row = business.get_customer(self._conn, cid)
        if row is None:
            return
        d = dict(row)
        self._customer_id = cid
        self._bill_te.setPlainText(format_customer_bill_to_plaintext(d))
        self._filling_combo = True
        self._combo.blockSignals(True)
        idx = self._combo.findData(cid, Qt.ItemDataRole.UserRole)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)
            le = self._combo.lineEdit()
            if le is not None:
                le.setText(self._combo.itemText(idx))
        self._combo.blockSignals(False)
        self._filling_combo = False
        self.customerIdChanged.emit(cid)

    def open_new_customer_dialog(self) -> None:
        """Run the same flow as **New customer…** (for a host-placed toolbar button)."""
        self._on_new_customer()

    def _on_new_customer(self) -> None:
        if self._conn is None:
            return
        hint = ""
        le = self._combo.lineEdit()
        if le is not None:
            hint = le.text().strip()
        nid = run_new_customer_dialog(
            self, self._conn, initial_name=hint, show_success_message=False
        )
        if nid is None:
            return
        self.reload_customers()
        self._apply_customer_id(nid)
        self.customerCreated.emit(int(nid))


def build_customer_bill_to_panel(
    parent: QWidget | None,
    *,
    ap_conn: sqlite3.Connection | None,
    layout_max_width_px: int | None = None,
    bill_plain_height_px: int | None = None,
    combo_min_width_px: int | None = None,
    show_new_customer_button: bool = True,
) -> tuple[CustomerBillToPanel, QPlainTextEdit]:
    """Build framed Bill To + return ``(panel, plain_text_edit)`` for layout/tests."""
    panel = CustomerBillToPanel(
        parent,
        ap_conn=ap_conn,
        layout_max_width_px=layout_max_width_px,
        bill_plain_height_px=bill_plain_height_px,
        combo_min_width_px=combo_min_width_px,
        show_new_customer_button=show_new_customer_button,
    )
    return panel, panel.bill_text_edit()
