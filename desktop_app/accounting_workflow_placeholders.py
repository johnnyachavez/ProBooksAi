"""Placeholder panels for main-window AR/AP workflow tabs (invoice, bills, receipts)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

# (tab strip title, tooltip slug, centered body line)
_ACCOUNTING_WORKFLOW_TAB_SPECS: tuple[tuple[str, str, str], ...] = (
    ("🧾  INVOICE", "Invoice", "Create and manage customer invoices."),
    ("📥  ENTER BILLS", "Enter Bills", "Record vendor bills and accounts payable."),
    ("💳  PAY BILLS", "Pay Bills", "Select bills and record payments to vendors."),
    ("💵  RECEIVE CHECKS", "Receive Checks", "Record customer payments and deposits."),
)


def accounting_workflow_tab_specs() -> tuple[tuple[str, str, str], ...]:
    return _ACCOUNTING_WORKFLOW_TAB_SPECS


def make_accounting_workflow_placeholder_tab(tab_title: str, body_line: str) -> QWidget:
    w = QWidget()
    tip = (
        f"{tab_title}: placeholder workspace (full workflow coming later). "
        "Same company SQLite file (File → Backup / Restore, probooks.backup)."
    )
    w.setToolTip(tip)
    lay = QVBoxLayout(w)
    lay.setContentsMargins(24, 24, 24, 24)
    lbl = QLabel(body_line)
    lbl.setWordWrap(True)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet("color: #A0A0B0; font-size: 14px;")
    lbl.setToolTip(tip)
    lay.addStretch(1)
    lay.addWidget(lbl)
    lay.addStretch(1)
    return w
