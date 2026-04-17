"""Shared **New customer** dialog (Customers tab and Invoice Bill To).

Same fields and ``business.add_customer`` path as **Customers → New Customer**; no invoice-only schema.
"""

from __future__ import annotations

import sqlite3

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QWidget,
)

from probooksai import business

from desktop_app.qt_combo_ids import coerce_combo_int_id
from desktop_app.qt_mnemonic import (
    escape_ampersand_for_qt,
    message_box_information_ok,
    message_box_warning_ok,
    tip_qdialog_button_box,
)

_DIALOG_CANCEL_TIP = "Close this dialog without saving changes."


def run_new_customer_dialog(
    parent: QWidget | None,
    conn: sqlite3.Connection,
    *,
    initial_name: str = "",
    show_success_message: bool = True,
) -> int | None:
    """Modal new-customer flow. Returns new ``customers.id`` or ``None`` if cancelled / not saved."""
    d = QDialog(parent)
    d.setWindowTitle("New customer")
    d.setToolTip(
        "Create a customer record used for AR invoices, payments, and aging. "
        "Same data as Customers tab (File → Backup / Restore, probooks.backup)."
    )
    f = QFormLayout(d)
    type_cb = QComboBox()
    type_cb.setToolTip(
        "Standalone: a normal customer (or future mother ship for jobs). "
        "Job: bill under this name; choose the parent account to roll up in Receive Payments."
    )
    type_cb.addItem("Standalone Customer", "standalone")
    type_cb.addItem("Job under Existing Customer", "job")
    parent_lbl = QLabel("Parent customer *")
    parent_lbl.setToolTip("Top-level (mother ship) customer this job belongs to.")
    parent_cb = QComboBox()
    parent_cb.setToolTip(
        "Open invoices for this job appear when the parent is selected in Receive Payments."
    )

    def refill_parent_cb() -> None:
        parent_cb.clear()
        for r in business.list_parent_customer_choices(conn):
            rid = int(r["id"])
            nm = (r["name"] or "").strip() or f"#{rid}"
            parent_cb.addItem(nm, rid)

    def sync_parent_visibility() -> None:
        is_job = type_cb.currentData() == "job"
        parent_lbl.setVisible(is_job)
        parent_cb.setVisible(is_job)

    type_cb.currentIndexChanged.connect(lambda _i=None: sync_parent_visibility())
    refill_parent_cb()
    sync_parent_visibility()

    ne = QLineEdit((initial_name or "").strip())
    ne.setToolTip("Customer display name (required).")
    em = QLineEdit()
    em.setToolTip("Contact email (optional).")
    ph = QLineEdit()
    ph.setToolTip("Phone number (optional).")
    ad = QPlainTextEdit()
    ad.setFixedHeight(56)
    ad.setToolTip("Mailing or service address (optional).")
    no = QPlainTextEdit()
    no.setFixedHeight(48)
    no.setToolTip("Internal notes about this customer (optional).")
    f.addRow("Customer type", type_cb)
    f.addRow(parent_lbl, parent_cb)
    f.addRow("Name *", ne)
    f.addRow("Email", em)
    f.addRow("Phone", ph)
    f.addRow("Address", ad)
    f.addRow("Notes", no)
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    tip_qdialog_button_box(
        bb,
        ok="Add the customer with these details.",
        cancel=_DIALOG_CANCEL_TIP,
    )
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    f.addRow(bb)
    if d.exec() != QDialog.DialogCode.Accepted or not ne.text().strip():
        return None
    mode = type_cb.currentData()
    parent_id = None
    if mode == "job":
        if parent_cb.count() == 0:
            message_box_warning_ok(
                parent,
                "Customer",
                "Create a standalone customer first to use as the parent (mother ship).",
                ok_tip="Close; add a top-level customer, then add this job again.",
            )
            return None
        parent_id = coerce_combo_int_id(parent_cb.currentData())
        if parent_id is None:
            message_box_warning_ok(
                parent,
                "Customer",
                "Choose a parent customer for a job account.",
                ok_tip="Close; pick the mother ship customer in Parent customer.",
            )
            return None
    try:
        cid = business.add_customer(
            conn,
            ne.text().strip(),
            email=em.text().strip(),
            phone=ph.text().strip(),
            address=ad.toPlainText().strip(),
            notes=no.toPlainText().strip(),
            parent_customer_id=parent_id,
        )
    except sqlite3.Error:
        return None
    except ValueError as exc:
        message_box_warning_ok(
            parent,
            "Customer",
            escape_ampersand_for_qt(str(exc)),
            ok_tip="Close; fix the validation issue and try again.",
        )
        return None
    if show_success_message:
        message_box_information_ok(
            parent,
            "Done",
            "Customer added.",
            ok_tip="Close; the customer appears in lists and filters.",
        )
    return int(cid)
