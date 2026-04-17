"""Modal wizard: capture company identity before choosing a new company ``.db`` path."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
)


class CreateCompanyFileDialog(QDialog):
    """Collect company name, address, phone, email, and tax ID (EIN / 1099-related)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create company file")
        self.setMinimumWidth(420)

        intro = QLabel(
            "Enter your company details. They are saved inside the new company database "
            "and used on printed invoices and future reports."
        )
        intro.setWordWrap(True)

        self._name = QLineEdit()
        self._name.setPlaceholderText("Legal or trade name")
        self._address = QPlainTextEdit()
        self._address.setPlaceholderText("Street, city, state, ZIP")
        self._address.setFixedHeight(72)
        self._phone = QLineEdit()
        self._phone.setPlaceholderText("Main phone")
        self._email = QLineEdit()
        self._email.setPlaceholderText("Billing / contact email")
        self._tax_id = QLineEdit()
        self._tax_id.setPlaceholderText("EIN or other tax ID (1099 / reporting)")

        form = QFormLayout()
        form.addRow("Company name *", self._name)
        form.addRow("Address", self._address)
        form.addRow("Phone", self._phone)
        form.addRow("Email", self._email)
        form.addRow("Tax ID", self._tax_id)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addWidget(intro)
        root.addLayout(form)
        root.addWidget(buttons)

    def _validate_and_accept(self) -> None:
        if not (self._name.text() or "").strip():
            self._name.setFocus()
            return
        self.accept()

    def identity_values(self) -> dict[str, str]:
        return {
            "name": (self._name.text() or "").strip(),
            "address": (self._address.toPlainText() or "").strip(),
            "phone": (self._phone.text() or "").strip(),
            "email": (self._email.text() or "").strip(),
            "tax_id": (self._tax_id.text() or "").strip(),
        }
