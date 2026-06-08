"""Modal **New Company** setup wizard: capture company identity before choosing the new ``.db`` path.

Required fields (the wizard refuses to accept until each is non-empty):

* Company Name
* Business Type
* Tax Structure

Recommended (saved when provided, but the wizard does not block on them):

* Address
* Phone
* Email
* Tax ID (EIN / 1099-related)

Values flow through :func:`probooksai.company_identity.save_company_identity` into the new
company file's ``company_settings`` table and become the source of truth for printed
invoices, PDFs, and reports.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
)

from probooksai.company_identity import BUSINESS_TYPES, TAX_STRUCTURES


def _styled_combo(options: tuple[str, ...]) -> QComboBox:
    """Combo with a leading blank option so an unselected state is clearly invalid."""
    cb = QComboBox()
    cb.addItem("")
    for opt in options:
        cb.addItem(opt)
    return cb


class CreateCompanyFileDialog(QDialog):
    """Collect company identity for a new ProBooks+ai company file.

    Public API:

    * :meth:`exec` returns ``QDialog.Accepted`` only after all required fields
      pass :meth:`_validate_and_accept`.
    * :meth:`identity_values` returns the captured values as a flat dict with
      keys ``name``, ``address``, ``phone``, ``email``, ``tax_id``,
      ``business_type``, and ``tax_structure``. Designed to splat directly
      into :func:`probooksai.company_identity.save_company_identity` as kwargs.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New company")
        self.setMinimumWidth(460)

        self._intro = QLabel(
            "Enter your company details to set up this ProBooks+ai company file. "
            "These values are saved inside the new company database (not in the app code) "
            "and become the source of truth for printed invoices, PDFs, and reports."
        )
        self._intro.setWordWrap(True)
        intro = self._intro

        self._name = QLineEdit()
        self._name.setPlaceholderText("Legal or trade name")
        self._address = QPlainTextEdit()
        self._address.setPlaceholderText("Street, city, state, ZIP")
        self._address.setFixedHeight(72)
        self._phone = QLineEdit()
        self._phone.setPlaceholderText("Main phone")
        self._email = QLineEdit()
        self._email.setPlaceholderText("Billing / contact email")
        self._business_type = _styled_combo(BUSINESS_TYPES)
        self._tax_structure = _styled_combo(TAX_STRUCTURES)
        self._tax_id = QLineEdit()
        self._tax_id.setPlaceholderText("EIN or other tax ID (1099 / reporting)")

        form = QFormLayout()
        form.addRow("Company name *", self._name)
        form.addRow("Address", self._address)
        form.addRow("Phone", self._phone)
        form.addRow("Email", self._email)
        form.addRow("Business type *", self._business_type)
        form.addRow("Tax structure *", self._tax_structure)
        form.addRow("Tax ID", self._tax_id)

        self._error = QLabel("")
        self._error.setStyleSheet("color: #c0392b; font-size: 12px;")
        self._error.setVisible(False)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addWidget(intro)
        root.addLayout(form)
        root.addWidget(self._error)
        root.addWidget(buttons)

    def _set_error(self, msg: str) -> None:
        self._error.setText(msg)
        self._error.setVisible(bool(msg))

    def _validate_and_accept(self) -> None:
        if not (self._name.text() or "").strip():
            self._set_error("Company name is required.")
            self._name.setFocus()
            return
        if not (self._business_type.currentText() or "").strip():
            self._set_error("Business type is required.")
            self._business_type.setFocus()
            return
        if not (self._tax_structure.currentText() or "").strip():
            self._set_error("Tax structure is required.")
            self._tax_structure.setFocus()
            return
        self._set_error("")
        self.accept()

    def identity_values(self) -> dict[str, str]:
        return {
            "name": (self._name.text() or "").strip(),
            "address": (self._address.toPlainText() or "").strip(),
            "phone": (self._phone.text() or "").strip(),
            "email": (self._email.text() or "").strip(),
            "tax_id": (self._tax_id.text() or "").strip(),
            "business_type": (self._business_type.currentText() or "").strip(),
            "tax_structure": (self._tax_structure.currentText() or "").strip(),
        }

    def set_initial_values(self, values: dict[str, str]) -> None:
        """Prefill fields from a saved identity dict (keys match :meth:`identity_values`)."""
        self._name.setText(values.get("name", "") or "")
        self._address.setPlainText(values.get("address", "") or "")
        self._phone.setText(values.get("phone", "") or "")
        self._email.setText(values.get("email", "") or "")
        self._tax_id.setText(values.get("tax_id", "") or "")

        bt = (values.get("business_type", "") or "").strip()
        if bt:
            idx = self._business_type.findText(bt)
            if idx == -1:
                self._business_type.addItem(bt)
                idx = self._business_type.findText(bt)
            self._business_type.setCurrentIndex(idx)

        ts = (values.get("tax_structure", "") or "").strip()
        if ts:
            idx = self._tax_structure.findText(ts)
            if idx == -1:
                self._tax_structure.addItem(ts)
                idx = self._tax_structure.findText(ts)
            self._tax_structure.setCurrentIndex(idx)

    def set_edit_mode(self, *, title: str = "Company info", intro: str | None = None) -> None:
        """Re-skin the dialog for editing existing company identity (no .db creation)."""
        self.setWindowTitle(title)
        if intro is not None:
            self._intro.setText(intro)
