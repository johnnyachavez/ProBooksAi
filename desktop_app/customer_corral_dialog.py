"""Placeholder **Customer Corral** form opened from **File → Customers → Customer Corral…**.

UI-only template aligned with :class:`desktop_app.vendor_roundup_dialog.VendorRoundupDialog` and
AR/AP light panels. Replace with real customer management when AR workflow is wired.
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

_CC_BG = "#f7f9fc"
_CC_PANEL = "#ffffff"
_CC_GRID = "#c5d4e6"
_CC_TEXT = "#1a1a2e"
_CC_CAPTION = "#5a6578"
_CC_GROUP = "#dce8f4"

_TERMS_ITEMS = (
    "Due on receipt",
    "Net 10",
    "Net 15",
    "Net 30",
    "Net 60",
)


def _line_style() -> str:
    return (
        f"QLineEdit {{ background: {_CC_PANEL}; border: 1px solid {_CC_GRID}; "
        f"padding: 4px 8px; color: {_CC_TEXT}; border-radius: 4px; }}"
    )


def _combo_style() -> str:
    return (
        f"QComboBox {{ background: {_CC_PANEL}; border: 1px solid {_CC_GRID}; "
        f"padding: 4px 8px; color: {_CC_TEXT}; border-radius: 4px; }}"
    )


def _notes_style() -> str:
    return (
        f"QPlainTextEdit {{ background: {_CC_PANEL}; color: {_CC_TEXT}; "
        f"border: 1px solid {_CC_GRID}; border-radius: 4px; padding: 6px; }}"
    )


def _address_block_style() -> str:
    return _notes_style()


class CustomerCorralDialog(QDialog):
    """Modal placeholder customer template; no database I/O."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Customer Corral")
        self.setMinimumSize(540, 720)
        self.resize(580, 760)
        self.setModal(True)
        self.setToolTip(
            "Placeholder customer template (no save to database yet). "
            "Same company .db as the rest of the app (File → Backup / Restore, probooks.backup)."
        )
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        page = QFrame()
        page.setObjectName("customerCorralLightPanel")
        page.setStyleSheet(
            f"QFrame#customerCorralLightPanel {{ background-color: {_CC_BG}; "
            f"border: 1px solid {_CC_GRID}; border-radius: 8px; }}"
        )
        play = QVBoxLayout(page)
        play.setContentsMargins(16, 16, 16, 16)
        play.setSpacing(14)

        title = QLabel("Customer Corral")
        title.setStyleSheet(
            f"font-size: 20px; font-weight: 600; color: {_CC_TEXT}; background: transparent;"
        )
        play.addWidget(title)

        hint = QLabel(
            "Placeholder template — customer entry UI only; not saved to the company file yet."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {_CC_CAPTION}; font-size: 12px; background: transparent;")
        play.addWidget(hint)

        form_frame = QFrame()
        form_frame.setStyleSheet(
            f"QFrame {{ background-color: {_CC_PANEL}; border: 1px solid {_CC_GRID}; border-radius: 6px; }}"
        )
        form = QFormLayout(form_frame)
        form.setContentsMargins(14, 12, 14, 12)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        lbl_style = f"color: {_CC_TEXT}; font-size: 13px; background: transparent;"

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

        def _addr_block(placeholder: str) -> QPlainTextEdit:
            te = QPlainTextEdit()
            te.setPlaceholderText(placeholder)
            te.setFixedHeight(56)
            te.setStyleSheet(_address_block_style())
            return te

        self._customer_name = _le("Customer display name")
        self._company_name = _le("Legal / DBA name")
        self._contact_name = _le("Primary contact")

        form.addRow(_lbl("Customer Name"), self._customer_name)
        form.addRow(_lbl("Company Name"), self._company_name)
        form.addRow(_lbl("Contact Name"), self._contact_name)

        bill_group = QFrame()
        bill_group.setStyleSheet(
            f"QFrame {{ background-color: {_CC_GROUP}; border: 1px solid {_CC_GRID}; "
            "border-radius: 6px; }}"
        )
        bill_lay = QVBoxLayout(bill_group)
        bill_lay.setContentsMargins(10, 8, 10, 8)
        bill_lay.setSpacing(6)
        bill_cap = QLabel("Bill To")
        bill_cap.setStyleSheet(
            f"color: {_CC_TEXT}; font-size: 12px; font-weight: 600; background: transparent;"
        )
        self._bill_to = _addr_block("Bill To street address")
        bill_lay.addWidget(bill_cap)
        bill_lay.addWidget(self._bill_to)
        form.addRow(bill_group)

        ship_group = QFrame()
        ship_group.setStyleSheet(
            f"QFrame {{ background-color: {_CC_GROUP}; border: 1px solid {_CC_GRID}; "
            "border-radius: 6px; }}"
        )
        ship_lay = QVBoxLayout(ship_group)
        ship_lay.setContentsMargins(10, 8, 10, 8)
        ship_lay.setSpacing(6)
        ship_cap = QLabel("Ship To")
        ship_cap.setStyleSheet(
            f"color: {_CC_TEXT}; font-size: 12px; font-weight: 600; background: transparent;"
        )
        self._ship_to = _addr_block("Ship To street address (if different)")
        ship_lay.addWidget(ship_cap)
        ship_lay.addWidget(self._ship_to)
        form.addRow(ship_group)

        self._city = _le("City")
        self._state = _le()
        self._state.setMaximumWidth(72)
        self._zip = _le()
        self._zip.setMaximumWidth(120)
        self._phone = _le()
        self._email = _le()

        self._terms = QComboBox()
        self._terms.addItems(_TERMS_ITEMS)
        self._terms.setStyleSheet(_combo_style())

        self._job_name = _le("Job or project name")
        self._job_number = _le("Job #")

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
        form.addRow(_lbl("Job Name"), self._job_name)
        form.addRow(_lbl("Job Number"), self._job_number)

        play.addWidget(form_frame)

        notes_frame = QFrame()
        notes_frame.setStyleSheet(
            f"QFrame {{ background-color: {_CC_PANEL}; border: 1px solid {_CC_GRID}; border-radius: 6px; }}"
        )
        notes_lay = QVBoxLayout(notes_frame)
        notes_lay.setContentsMargins(14, 12, 14, 12)
        notes_lay.setSpacing(6)
        notes_cap = QLabel("Memo")
        notes_cap.setStyleSheet(f"color: {_CC_TEXT}; font-size: 13px; font-weight: 600;")
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
        self._customer_name.clear()
        self._company_name.clear()
        self._contact_name.clear()
        self._bill_to.clear()
        self._ship_to.clear()
        self._city.clear()
        self._state.clear()
        self._zip.clear()
        self._phone.clear()
        self._email.clear()
        self._terms.setCurrentIndex(0)
        self._job_name.clear()
        self._job_number.clear()
        self._memo.clear()

    def _on_save(self) -> None:
        print("[Customer Corral] Save (placeholder — no database)")

    def _on_save_new(self) -> None:
        print("[Customer Corral] Save & New (placeholder — no database)")
        self._clear_form()


def show_customer_corral_dialog(parent: Optional[QWidget] = None) -> None:
    """Show the modal Customer Corral placeholder."""
    dlg = CustomerCorralDialog(parent)
    dlg.exec()
