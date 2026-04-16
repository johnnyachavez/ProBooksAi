"""Placeholder **Vendor Roundup** form opened from **File → Vendors → Vendor Roundup…**.

UI-only template aligned with :class:`desktop_app.enter_bills_screen.EnterBillsScreen` /
:class:`desktop_app.invoice_screen.InvoiceScreen` light panels. Replace with real vendor
management when AP workflow is wired.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# Match Enter Bills / Invoice light “accounting form” palette
_VR_BG = "#f7f9fc"
_VR_PANEL = "#ffffff"
_VR_GRID = "#c5d4e6"
_VR_TEXT = "#1a1a2e"
_VR_CAPTION = "#5a6578"

_TERMS_ITEMS = (
    "Due on receipt",
    "Net 10",
    "Net 15",
    "Net 30",
    "Net 60",
)


def _line_style() -> str:
    return (
        f"QLineEdit {{ background: {_VR_PANEL}; border: 1px solid {_VR_GRID}; "
        f"padding: 4px 8px; color: {_VR_TEXT}; border-radius: 4px; }}"
    )


def _combo_style() -> str:
    return (
        f"QComboBox {{ background: {_VR_PANEL}; border: 1px solid {_VR_GRID}; "
        f"padding: 4px 8px; color: {_VR_TEXT}; border-radius: 4px; }}"
    )


def _notes_style() -> str:
    return (
        f"QPlainTextEdit {{ background: {_VR_PANEL}; color: {_VR_TEXT}; "
        f"border: 1px solid {_VR_GRID}; border-radius: 4px; padding: 6px; }}"
    )


class VendorRoundupDialog(QDialog):
    """Modal placeholder vendor template; no database I/O."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Vendor Roundup")
        self.setMinimumSize(520, 620)
        self.resize(560, 680)
        self.setModal(True)
        self.setToolTip(
            "Placeholder vendor template (no save to database yet). "
            "Same company .db as the rest of the app (File → Backup / Restore, probooks.backup)."
        )
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        page = QFrame()
        page.setObjectName("vendorRoundupLightPanel")
        page.setStyleSheet(
            f"QFrame#vendorRoundupLightPanel {{ background-color: {_VR_BG}; "
            f"border: 1px solid {_VR_GRID}; border-radius: 8px; }}"
        )
        play = QVBoxLayout(page)
        play.setContentsMargins(16, 16, 16, 16)
        play.setSpacing(14)

        title = QLabel("Vendor Roundup")
        title.setStyleSheet(
            f"font-size: 20px; font-weight: 600; color: {_VR_TEXT}; background: transparent;"
        )
        play.addWidget(title)

        hint = QLabel("Placeholder template — vendor entry UI only; not saved to the company file yet.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {_VR_CAPTION}; font-size: 12px; background: transparent;")
        play.addWidget(hint)

        form_frame = QFrame()
        form_frame.setStyleSheet(
            f"QFrame {{ background-color: {_VR_PANEL}; border: 1px solid {_VR_GRID}; border-radius: 6px; }}"
        )
        form = QFormLayout(form_frame)
        form.setContentsMargins(14, 12, 14, 12)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        lbl_style = f"color: {_VR_TEXT}; font-size: 13px; background: transparent;"

        def _lbl(text: str) -> QLabel:
            lb = QLabel(text)
            lb.setStyleSheet(lbl_style)
            return lb

        def _le(placeholder: str = "") -> QLineEdit:
            w = QLineEdit()
            w.setStyleSheet(_line_style())
            if placeholder:
                w.setPlaceholderText(placeholder)
            return w

        self._vendor_name = _le("Vendor display name")
        self._contact_name = _le("Primary contact")
        self._company_name = _le("Legal / DBA name")
        self._address = _le("Street address")
        self._city = _le("City")
        self._state = _le()
        self._state.setMaximumWidth(72)
        self._zip = _le()
        self._zip.setMaximumWidth(120)
        self._phone = _le()
        self._email = _le()
        self._account_number = _le()

        self._terms = QComboBox()
        self._terms.addItems(_TERMS_ITEMS)
        self._terms.setStyleSheet(_combo_style())

        form.addRow(_lbl("Vendor Name"), self._vendor_name)
        form.addRow(_lbl("Contact Name"), self._contact_name)
        form.addRow(_lbl("Company Name"), self._company_name)
        form.addRow(_lbl("Address"), self._address)

        city_row = QWidget()
        city_lay = QHBoxLayout(city_row)
        city_lay.setContentsMargins(0, 0, 0, 0)
        city_lay.setSpacing(8)
        city_lay.addWidget(self._city, 2)
        city_lay.addWidget(_lbl("State"))
        city_lay.addWidget(self._state, 0)
        city_lay.addWidget(_lbl("Zip"))
        city_lay.addWidget(self._zip, 0)
        form.addRow(_lbl("City"), city_row)

        form.addRow(_lbl("Phone"), self._phone)
        form.addRow(_lbl("Email"), self._email)
        form.addRow(_lbl("Terms"), self._terms)
        form.addRow(_lbl("Account Number"), self._account_number)

        play.addWidget(form_frame)

        notes_frame = QFrame()
        notes_frame.setStyleSheet(
            f"QFrame {{ background-color: {_VR_PANEL}; border: 1px solid {_VR_GRID}; border-radius: 6px; }}"
        )
        notes_lay = QVBoxLayout(notes_frame)
        notes_lay.setContentsMargins(14, 12, 14, 12)
        notes_lay.setSpacing(6)
        notes_cap = QLabel("Memo / notes")
        notes_cap.setStyleSheet(f"color: {_VR_TEXT}; font-size: 13px; font-weight: 600;")
        self._memo = QPlainTextEdit()
        self._memo.setPlaceholderText("Memo, internal notes, or other details (placeholder).")
        self._memo.setMinimumHeight(100)
        self._memo.setStyleSheet(_notes_style())
        notes_lay.addWidget(notes_cap)
        notes_lay.addWidget(self._memo)
        play.addWidget(notes_frame, 1)

        bot = QHBoxLayout()
        bot.addStretch(1)
        self._btn_save = QPushButton("Save")
        self._btn_save_new = QPushButton("Save && New")
        self._btn_clear = QPushButton("Clear")
        for b in (self._btn_save, self._btn_save_new, self._btn_clear):
            b.setMinimumWidth(100)
        self._btn_save.setToolTip("Placeholder — does not write to the database yet.")
        self._btn_save_new.setToolTip("Placeholder — clear after pretend save (no database).")
        self._btn_clear.setToolTip("Clear all fields on this form.")
        self._btn_save.clicked.connect(self._on_save)
        self._btn_save_new.clicked.connect(self._on_save_new)
        self._btn_clear.clicked.connect(self._clear_form)
        bot.addWidget(self._btn_save)
        bot.addWidget(self._btn_save_new)
        bot.addWidget(self._btn_clear)
        play.addLayout(bot)

        outer.addWidget(page)

    def _clear_form(self) -> None:
        self._vendor_name.clear()
        self._contact_name.clear()
        self._company_name.clear()
        self._address.clear()
        self._city.clear()
        self._state.clear()
        self._zip.clear()
        self._phone.clear()
        self._email.clear()
        self._terms.setCurrentIndex(0)
        self._account_number.clear()
        self._memo.clear()

    def _on_save(self) -> None:
        print("[Vendor Roundup] Save (placeholder — no database)")

    def _on_save_new(self) -> None:
        print("[Vendor Roundup] Save & New (placeholder — no database)")
        self._clear_form()


def show_vendor_roundup_dialog(parent: Optional[QWidget] = None) -> None:
    """Show the modal Vendor Roundup placeholder."""
    dlg = VendorRoundupDialog(parent)
    dlg.exec()
