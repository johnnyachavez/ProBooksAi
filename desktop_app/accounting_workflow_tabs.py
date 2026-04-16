"""Landing pages for AR/AP workflow tabs (navigation and layout only; no data layer)."""

from __future__ import annotations

import sqlite3
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from desktop_app.accounting_workflow_placeholders import accounting_workflow_tab_specs
from desktop_app.enter_bills_screen import EnterBillsScreen
from desktop_app.invoice_screen import InvoiceScreen
from desktop_app.pay_bills_screen import PayBillsScreen
from desktop_app.receive_checks_screen import ReceiveChecksScreen
from desktop_app.theme import BG_SECONDARY, BORDER, FG_PRIMARY, FG_SECONDARY


def _landing_page(
    *,
    page_title: str,
    subtitle: str,
    placeholder_buttons: tuple[str, ...] = (),
    tab_tooltip: str = "",
) -> QWidget:
    w = QWidget()
    tip = tab_tooltip or f"{page_title}: {subtitle}"
    w.setToolTip(tip)

    outer = QVBoxLayout(w)
    outer.setContentsMargins(40, 36, 40, 36)
    outer.setSpacing(0)

    header = QVBoxLayout()
    header.setSpacing(8)

    title_lbl = QLabel(page_title)
    title_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    title_lbl.setStyleSheet(
        f"font-size: 22px; font-weight: 600; color: {FG_PRIMARY};"
    )
    title_lbl.setToolTip(tip)

    sub_lbl = QLabel(subtitle)
    sub_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    sub_lbl.setWordWrap(True)
    sub_lbl.setStyleSheet(f"font-size: 13px; color: {FG_SECONDARY};")
    sub_lbl.setToolTip(subtitle)

    header.addWidget(title_lbl)
    header.addWidget(sub_lbl)

    outer.addLayout(header)

    if placeholder_buttons:
        outer.addSpacing(20)
        row = QHBoxLayout()
        row.addStretch(1)
        for label in placeholder_buttons:
            btn = QPushButton(label)
            btn.setToolTip("Coming soon — not wired yet.")
            # Non-functional: no signal connection
            row.addWidget(btn)
        row.addStretch(1)
        outer.addLayout(row)

    outer.addSpacing(24)

    work = QFrame()
    work.setFrameShape(QFrame.Shape.StyledPanel)
    work.setMinimumHeight(280)
    work.setStyleSheet(
        f"QFrame {{ background-color: {BG_SECONDARY}; border: 1px solid {BORDER}; "
        "border-radius: 8px; }}"
    )
    inner = QVBoxLayout(work)
    inner.setContentsMargins(20, 20, 20, 20)
    placeholder = QLabel("Working area")
    placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
    placeholder.setStyleSheet(f"color: {FG_SECONDARY}; font-size: 12px;")
    inner.addStretch(1)
    inner.addWidget(placeholder)
    inner.addStretch(1)

    outer.addWidget(work, 1)

    return w


def build_accounting_workflow_tabs(
    ap_conn: Optional[sqlite3.Connection] = None,
) -> tuple[QWidget, QWidget, QWidget, QWidget]:
    """Return one landing widget per :func:`accounting_workflow_tab_specs` row (invoice → enter bills → pay → receive).

    *ap_conn* supplies customer data for :class:`InvoiceScreen` and vendor data for
    :class:`EnterBillsScreen` when connected to a company file.
    """
    button_rows: tuple[tuple[str, ...], ...] = (
        ("New Invoice",),
        ("New Bill",),
        ("Pay Bill",),
        ("Receive Payment",),
    )
    widgets: list[QWidget] = []
    for (_tab_title, page_title, subtitle), btns in zip(
        accounting_workflow_tab_specs(), button_rows, strict=True
    ):
        if page_title == "Invoice":
            widgets.append(InvoiceScreen(ap_conn=ap_conn))
        elif page_title == "Enter Bills":
            widgets.append(EnterBillsScreen(ap_conn=ap_conn))
        elif page_title == "Pay Bills":
            widgets.append(PayBillsScreen(ap_conn=ap_conn))
        elif page_title == "Receive Checks":
            widgets.append(ReceiveChecksScreen(ap_conn=ap_conn))
        else:
            widgets.append(
                _landing_page(
                    page_title=page_title,
                    subtitle=subtitle,
                    placeholder_buttons=btns,
                    tab_tooltip=f"{page_title} — {subtitle}",
                )
            )
    return tuple(widgets)
