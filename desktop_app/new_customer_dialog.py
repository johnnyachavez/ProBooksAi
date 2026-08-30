"""Shared **New customer** dialog (Customers tab and Invoice Bill To).

Same fields and ``business.add_customer`` path as **Customers → New Customer**; no invoice-only schema.
This is not the New Company wizard.
"""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
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


class NewCustomerDialog(QDialog):
    """One-column new-customer form. OK saves; Cancel does nothing."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        parent: QWidget | None = None,
        *,
        initial_name: str = "",
        initial_as_job: bool = False,
        initial_parent_customer_id: int | None = None,
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        self.saved_customer_id: int | None = None
        self.setObjectName("newCustomerDialog")
        self.setWindowTitle("Add Job" if initial_as_job else "New customer")
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setToolTip(
            "Create a customer or job record used for AR invoices, payments, and aging. "
            "Same data as Customer Center (File → Backup / Restore, probooks.backup)."
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(6)

        def _label(text: str) -> QLabel:
            lab = QLabel(text)
            lab.setTextFormat(Qt.TextFormat.PlainText)
            lab.setStyleSheet("font-weight: 600; font-size: 12px;")
            return lab

        self._name = QLineEdit((initial_name or "").strip())
        self._name.setObjectName("newCustomerName")
        self._name.setToolTip("Customer display name (required).")
        self._email = QLineEdit()
        self._email.setObjectName("newCustomerEmail")
        self._email.setToolTip("Contact email (optional).")
        self._phone = QLineEdit()
        self._phone.setObjectName("newCustomerPhone")
        self._phone.setToolTip("Phone number (optional).")
        self._address = QPlainTextEdit()
        self._address.setObjectName("newCustomerAddress")
        self._address.setFixedHeight(64)
        self._address.setToolTip("Mailing or service address (optional).")
        self._notes = QPlainTextEdit()
        self._notes.setObjectName("newCustomerNotes")
        self._notes.setFixedHeight(56)
        self._notes.setToolTip("Internal notes about this customer (optional).")

        self._type = QComboBox()
        self._type.setObjectName("newCustomerType")
        self._type.setToolTip(
            "Standalone: a normal customer (or future mother ship for jobs). "
            "Job: bill under this name; choose the parent account to roll up in Receive Payments."
        )
        self._type.addItem("Standalone Customer", "standalone")
        self._type.addItem("Job under Existing Customer", "job")

        self._parent_lbl = QLabel("Parent customer")
        self._parent_lbl.setObjectName("newCustomerParentLabel")
        self._parent_lbl.setStyleSheet("font-weight: 600; font-size: 12px;")
        self._parent_lbl.setToolTip("Top-level (mother ship) customer this job belongs to.")
        self._parent = QComboBox()
        self._parent.setObjectName("newCustomerParent")
        self._parent.setToolTip(
            "Open invoices for this job appear when the parent is selected in Receive Payments."
        )

        for caption, widget in (
            ("Name", self._name),
            ("Email", self._email),
            ("Phone", self._phone),
            ("Address", self._address),
            ("Notes", self._notes),
            ("Customer type", self._type),
        ):
            root.addWidget(_label(caption))
            root.addWidget(widget)

        root.addWidget(self._parent_lbl)
        root.addWidget(self._parent)

        self._type.currentIndexChanged.connect(lambda _i=None: self._sync_parent_visibility())
        self._refill_parent()
        if initial_as_job:
            self._type.setCurrentIndex(1)
            if initial_parent_customer_id is not None:
                ix = next(
                    (
                        i
                        for i in range(self._parent.count())
                        if coerce_combo_int_id(self._parent.itemData(i))
                        == int(initial_parent_customer_id)
                    ),
                    -1,
                )
                if ix >= 0:
                    self._parent.setCurrentIndex(ix)
        self._sync_parent_visibility()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.setObjectName("newCustomerButtons")
        tip_qdialog_button_box(
            buttons,
            ok="Add the customer with these details.",
            cancel=_DIALOG_CANCEL_TIP,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addSpacing(8)
        root.addWidget(buttons)

    def _refill_parent(self) -> None:
        self._parent.clear()
        for r in business.list_parent_customer_choices(self._conn):
            rid = int(r["id"])
            nm = (r["name"] or "").strip() or f"#{rid}"
            self._parent.addItem(nm, rid)

    def _sync_parent_visibility(self) -> None:
        is_job = self._type.currentData() == "job"
        self._parent_lbl.setVisible(is_job)
        self._parent.setVisible(is_job)

    def _try_save(self) -> int | None:
        name = self._name.text().strip()
        if not name:
            message_box_warning_ok(
                self,
                "Customer",
                "Enter a customer name.",
                ok_tip="Close; type a name, then click OK.",
            )
            return None
        parent_id = None
        if self._type.currentData() == "job":
            if self._parent.count() == 0:
                message_box_warning_ok(
                    self,
                    "Customer",
                    "Create a standalone customer first to use as the parent (mother ship).",
                    ok_tip="Close; add a top-level customer, then add this job again.",
                )
                return None
            parent_id = coerce_combo_int_id(self._parent.currentData())
            if parent_id is None:
                message_box_warning_ok(
                    self,
                    "Customer",
                    "Choose a parent customer for a job account.",
                    ok_tip="Close; pick the mother ship customer in Parent customer.",
                )
                return None
        try:
            return int(
                business.add_customer(
                    self._conn,
                    name,
                    email=self._email.text().strip(),
                    phone=self._phone.text().strip(),
                    address=self._address.toPlainText().strip(),
                    notes=self._notes.toPlainText().strip(),
                    parent_customer_id=parent_id,
                )
            )
        except sqlite3.Error:
            return None
        except ValueError as exc:
            message_box_warning_ok(
                self,
                "Customer",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; fix the validation issue and try again.",
            )
            return None

    def accept(self) -> None:
        cid = self._try_save()
        if cid is None:
            return
        self.saved_customer_id = cid
        super().accept()


def run_new_customer_dialog(
    parent: QWidget | None,
    conn: sqlite3.Connection,
    *,
    initial_name: str = "",
    show_success_message: bool = True,
    initial_as_job: bool = False,
    initial_parent_customer_id: int | None = None,
) -> int | None:
    """Modal new-customer flow. Returns new ``customers.id`` or ``None`` if cancelled / not saved."""
    d = NewCustomerDialog(
        conn,
        parent,
        initial_name=initial_name,
        initial_as_job=initial_as_job,
        initial_parent_customer_id=initial_parent_customer_id,
    )
    if d.exec() != QDialog.DialogCode.Accepted:
        return None
    cid = d.saved_customer_id
    if cid is None:
        return None
    if show_success_message:
        message_box_information_ok(
            parent,
            "Done",
            "Customer added.",
            ok_tip="Close; the customer appears in lists and filters.",
        )
    return int(cid)
