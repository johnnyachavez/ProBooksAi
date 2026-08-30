"""My Company — company information for the open company file.

Loads name, address, phone, email, and EIN/tax ID from ``company_settings``
(same keys as File → Company Setup). If the file has no saved name, the
header uses the company ``.db`` filename. Edit + Save writes those fields
back to the same open file. This page does not sell apps or services.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QIcon,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
    QPolygonF,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from desktop_app.qt_mnemonic import (
    message_box_information_ok,
    tip_qdialog_button_box,
)
from desktop_app.version import application_version
from probooksai import business
from probooksai.company_identity import get_company_identity, save_company_identity

_MC_CANVAS = "#E8ECF1"
_MC_PAPER = "#FFFFFF"
_MC_PANEL = "#F4F7FA"
_MC_BORDER = "#C5CDD6"
_MC_LINE = "#D8DEE6"
_MC_TEXT = "#1A1A1A"
_MC_CAPTION = "#4A5560"
_MC_TITLE = "#5B6770"
_MC_ACCENT = "#2563A8"
_MC_MUTED = "#8A94A0"

PLACEHOLDER_COMPANY_NAME = "COMPANY NAME"
PRODUCT_DISPLAY_NAME = "ProBooks+ai Desktop"
PRODUCT_LICENSE = "0000-0000-0000-000"
PRODUCT_NUMBER = "000-000"
PRODUCT_SEATS = "1"
PRODUCT_ACTIVATION = "ACTIVATED"
SSN_PLACEHOLDER = "000-00-0000"

_FIELD_KEYS = (
    ("contact_address", "company_address"),
    ("phone", "company_phone"),
    ("fax", "company_fax"),
    ("email", "company_email"),
    ("website", "company_website"),
    ("legal_address", "company_legal_name_address"),
    ("ein", "company_tax_id"),
    ("ssn", "company_ssn"),
    ("tax_form", "company_income_tax_form"),
    ("payroll_contact", "company_payroll_contact"),
)

def _light_palette() -> QPalette:
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(_MC_CANVAS))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(_MC_TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(_MC_PAPER))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(_MC_PANEL))
    pal.setColor(QPalette.ColorRole.Text, QColor(_MC_TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(_MC_PAPER))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(_MC_TEXT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(_MC_ACCENT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(_MC_MUTED))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(_MC_PANEL))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(_MC_TEXT))
    return pal


def _label_qss(*, size: str = "11px", weight: str = "400", color: str = _MC_CAPTION) -> str:
    return (
        f"color: {color}; font-size: {size}; font-weight: {weight}; "
        "background: transparent; border: none;"
    )


def _setting(conn: Optional[sqlite3.Connection], key: str) -> str:
    if conn is None:
        return ""
    try:
        return (business.get_setting(conn, key, "") or "").strip()
    except Exception:
        return ""


def company_file_display_name(conn: Optional[sqlite3.Connection]) -> str:
    """Human name from the open ``.db`` path when settings have no ``company_name``."""
    if conn is None:
        return ""
    try:
        rows = conn.execute("PRAGMA database_list").fetchall()
    except sqlite3.Error:
        return ""
    path = ""
    for row in rows:
        db_name = str(row[1] if not isinstance(row, sqlite3.Row) else row["name"])
        db_file = str(row[2] if not isinstance(row, sqlite3.Row) else row["file"])
        if db_name == "main":
            path = (db_file or "").strip()
            break
    if not path:
        return ""
    lowered = path.lower()
    if lowered in {":memory:", "memory"} or lowered.startswith("file:"):
        return ""
    stem = Path(path).stem.strip()
    if not stem or stem.startswith(":"):
        return ""
    return " ".join(stem.replace("-", " ").replace("_", " ").split())


def load_my_company_fields(conn: Optional[sqlite3.Connection]) -> dict[str, str]:
    """Read identity from the open company file; filename stem if name is unset."""
    data = {ui: _setting(conn, db_key) for ui, db_key in _FIELD_KEYS}
    identity: dict[str, str] = {}
    if conn is not None:
        try:
            identity = get_company_identity(conn)
        except Exception:
            identity = {}
    name = (identity.get("name") or _setting(conn, "company_name")).strip()
    if not name:
        name = company_file_display_name(conn)
    data["name"] = name if name else PLACEHOLDER_COMPANY_NAME
    if not data["contact_address"]:
        data["contact_address"] = (identity.get("address") or "").strip()
    if not data["phone"]:
        data["phone"] = (identity.get("phone") or "").strip()
    if not data["email"]:
        data["email"] = (identity.get("email") or "").strip()
    if not data["ein"]:
        data["ein"] = (identity.get("tax_id") or "").strip()
    if not data["tax_form"]:
        data["tax_form"] = (
            _setting(conn, "company_tax_structure")
            or (identity.get("tax_structure") or "").strip()
        )
    return data


def save_my_company_fields(conn: sqlite3.Connection, values: dict[str, str]) -> None:
    """Write My Company fields into the same open company file (identity + extras)."""
    name = (values.get("name") or "").strip()
    if name == PLACEHOLDER_COMPANY_NAME:
        name = ""
    existing: dict[str, str] = {}
    try:
        existing = get_company_identity(conn)
    except Exception:
        existing = {}
    save_company_identity(
        conn,
        name=name,
        address=(values.get("contact_address") or "").strip(),
        phone=(values.get("phone") or "").strip(),
        email=(values.get("email") or "").strip(),
        tax_id=(values.get("ein") or "").strip(),
        business_type=(existing.get("business_type") or "").strip(),
        tax_structure=(existing.get("tax_structure") or "").strip(),
    )
    for ui, db_key in _FIELD_KEYS:
        business.set_setting(conn, db_key, (values.get(ui) or "").strip())


def _pencil_icon(size: int = 18) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(_MC_ACCENT), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.setBrush(QColor("#E8F1FA"))
    p.drawLine(QPointF(3, size - 4), QPointF(size - 5, 4))
    p.drawRect(QRectF(size - 7, 2, 4, 4))
    p.setBrush(QColor(_MC_ACCENT))
    p.drawPolygon(
        QPolygonF(
            [
                QPointF(3, size - 4),
                QPointF(6, size - 3),
                QPointF(4, size - 6),
            ]
        )
    )
    p.end()
    return QIcon(pm)


class _InfoRow(QWidget):
    """Caption on the left, value on the right — QB My Company field pair."""

    def __init__(self, caption: str, object_name: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(12)
        cap = QLabel(caption)
        cap.setTextFormat(Qt.TextFormat.PlainText)
        cap.setStyleSheet(_label_qss(weight="700"))
        cap.setMinimumWidth(168)
        cap.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        row.addWidget(cap, 0)
        self.value = QLabel("")
        self.value.setObjectName(object_name)
        self.value.setTextFormat(Qt.TextFormat.PlainText)
        self.value.setWordWrap(True)
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.value.setStyleSheet(_label_qss(color=_MC_TEXT, size="12px"))
        row.addWidget(self.value, 1)

    def set_value(self, text: str, *, placeholder: str = "") -> None:
        raw = (text or "").strip()
        if raw:
            self.value.setText(raw)
            self.value.setStyleSheet(_label_qss(color=_MC_TEXT, size="12px"))
        else:
            self.value.setText(placeholder)
            self.value.setStyleSheet(_label_qss(color=_MC_MUTED, size="12px"))


class MyCompanyEditDialog(QDialog):
    """Edit contact / legal / tax fields shown on My Company."""

    def __init__(
        self,
        values: dict[str, str],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Company Information")
        self.setModal(True)
        self.setObjectName("myCompanyEditDialog")
        self.setMinimumWidth(520)
        self.setToolTip(
            "Edit name, address, phone, email, and EIN/tax ID for this company file. "
            "Save writes the same keys as File → Company Setup."
        )
        root = QVBoxLayout(self)
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        def _line(name: str, placeholder: str = "") -> QLineEdit:
            w = QLineEdit()
            w.setObjectName(name)
            w.setPlaceholderText(placeholder)
            return w

        self._name = _line("myCompanyEditName", PLACEHOLDER_COMPANY_NAME)
        self._contact = QPlainTextEdit()
        self._contact.setObjectName("myCompanyEditContact")
        self._contact.setFixedHeight(72)
        self._phone = _line("myCompanyEditPhone")
        self._fax = _line("myCompanyEditFax")
        self._email = _line("myCompanyEditEmail")
        self._website = _line("myCompanyEditWebsite")
        self._legal = QPlainTextEdit()
        self._legal.setObjectName("myCompanyEditLegal")
        self._legal.setFixedHeight(72)
        self._ein = _line("myCompanyEditEin")
        self._ssn = _line("myCompanyEditSsn", SSN_PLACEHOLDER)
        self._tax = _line("myCompanyEditTaxForm")
        self._payroll = _line("myCompanyEditPayroll")

        form.addRow("Display name", self._name)
        form.addRow("Contact Name && Address", self._contact)
        form.addRow("Main Phone", self._phone)
        form.addRow("Fax", self._fax)
        form.addRow("Email", self._email)
        form.addRow("Website", self._website)
        form.addRow("Legal Name && Address", self._legal)
        form.addRow("EIN", self._ein)
        form.addRow("SSN", self._ssn)
        form.addRow("Income Tax Form", self._tax)
        form.addRow("Payroll Contact", self._payroll)
        root.addLayout(form)

        hint = QLabel(
            "Leave identity fields blank if you do not want them on this page. "
            "SSN may stay empty or use 000-00-0000 as a fake placeholder."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(_label_qss())
        root.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        tip_qdialog_button_box(
            buttons,
            save="Save these fields into the open company file.",
            cancel="Close without saving.",
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        name = (values.get("name") or "").strip()
        self._name.setText("" if name == PLACEHOLDER_COMPANY_NAME else name)
        self._contact.setPlainText(values.get("contact_address") or "")
        self._phone.setText(values.get("phone") or "")
        self._fax.setText(values.get("fax") or "")
        self._email.setText(values.get("email") or "")
        self._website.setText(values.get("website") or "")
        self._legal.setPlainText(values.get("legal_address") or "")
        self._ein.setText(values.get("ein") or "")
        self._ssn.setText(values.get("ssn") or "")
        self._tax.setText(values.get("tax_form") or "")
        self._payroll.setText(values.get("payroll_contact") or "")

    def values(self) -> dict[str, str]:
        name = self._name.text().strip()
        return {
            "name": name if name else PLACEHOLDER_COMPANY_NAME,
            "contact_address": self._contact.toPlainText().strip(),
            "phone": self._phone.text().strip(),
            "fax": self._fax.text().strip(),
            "email": self._email.text().strip(),
            "website": self._website.text().strip(),
            "legal_address": self._legal.toPlainText().strip(),
            "ein": self._ein.text().strip(),
            "ssn": self._ssn.text().strip(),
            "tax_form": self._tax.text().strip(),
            "payroll_contact": self._payroll.text().strip(),
        }


class MyCompanyScreen(QWidget):
    """Company information for the open file, plus ProBooks+ai product details."""

    navigateRequested = Signal(str)

    def __init__(
        self,
        ap_conn: Optional[sqlite3.Connection] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._conn = ap_conn
        self.setObjectName("myCompanyPage")
        self.setAutoFillBackground(True)
        self.setPalette(_light_palette())
        self.setStyleSheet(f"QWidget#myCompanyPage {{ background: {_MC_CANVAS}; }}")
        self.setToolTip(
            "My Company: contact, legal, and product information for this company file. "
            "Same company .db (File → Backup / Restore, probooks.backup)."
        )
        self._build_ui()
        self.reload()

    def set_connection(self, conn: Optional[sqlite3.Connection]) -> None:
        self._conn = conn
        self.reload()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self.reload()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setObjectName("myCompanyScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: {_MC_CANVAS}; border: none; }}")
        outer.addWidget(scroll)

        content = QWidget()
        content.setObjectName("myCompanyCanvas")
        content.setAutoFillBackground(True)
        pal = content.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(_MC_CANVAS))
        content.setPalette(pal)
        board = QVBoxLayout(content)
        board.setContentsMargins(20, 16, 20, 18)
        board.setSpacing(14)

        header = QHBoxLayout()
        self._lbl_company = QLabel(PLACEHOLDER_COMPANY_NAME)
        self._lbl_company.setObjectName("myCompanyHeaderName")
        self._lbl_company.setTextFormat(Qt.TextFormat.PlainText)
        self._lbl_company.setStyleSheet(
            f"color: {_MC_TEXT}; font-size: 22px; font-weight: 800; letter-spacing: 0.04em; "
            "background: transparent; border: none;"
        )
        header.addWidget(self._lbl_company, 1)
        board.addLayout(header)

        main_card = QFrame()
        main_card.setObjectName("myCompanyMainCard")
        main_card.setStyleSheet(
            f"QFrame#myCompanyMainCard {{ background: {_MC_PAPER}; "
            f"border: 1px solid {_MC_BORDER}; border-radius: 4px; }}"
        )
        main_lay = QHBoxLayout(main_card)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        main_lay.addWidget(self._build_company_info(), 3)
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setStyleSheet(f"color: {_MC_LINE};")
        main_lay.addWidget(divider)
        main_lay.addWidget(self._build_product_sidebar(), 2)
        board.addWidget(main_card)
        board.addStretch(1)
        scroll.setWidget(content)

    def _build_company_info(self) -> QWidget:
        box = QWidget()
        box.setObjectName("myCompanyInfoBox")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(16, 12, 16, 16)
        lay.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("COMPANY INFORMATION")
        title.setObjectName("myCompanyInfoTitle")
        title.setStyleSheet(_label_qss(size="12px", weight="700", color=_MC_TITLE))
        head.addWidget(title)
        head.addStretch(1)
        edit = QToolButton()
        edit.setObjectName("myCompanyEditButton")
        edit.setIcon(_pencil_icon())
        edit.setIconSize(QSize(18, 18))
        edit.setAutoRaise(True)
        edit.setCursor(Qt.CursorShape.PointingHandCursor)
        edit.setToolTip("Edit company information for this company file.")
        edit.clicked.connect(self._on_edit)
        head.addWidget(edit)
        lay.addLayout(head)

        cols = QHBoxLayout()
        cols.setSpacing(24)
        left = QVBoxLayout()
        left.setSpacing(8)
        self._row_contact = _InfoRow("Contact Name & Address", "myCompanyContactAddress")
        self._row_phone = _InfoRow("Main Phone", "myCompanyPhone")
        self._row_fax = _InfoRow("Fax", "myCompanyFax")
        self._row_email = _InfoRow("Email", "myCompanyEmail")
        self._row_website = _InfoRow("Website", "myCompanyWebsite")
        for row in (
            self._row_contact,
            self._row_phone,
            self._row_fax,
            self._row_email,
            self._row_website,
        ):
            left.addWidget(row)
        left.addStretch(1)
        right = QVBoxLayout()
        right.setSpacing(8)
        self._row_legal = _InfoRow("Legal Name & Address", "myCompanyLegalAddress")
        self._row_ein = _InfoRow("EIN", "myCompanyEin")
        self._row_ssn = _InfoRow("SSN", "myCompanySsn")
        self._row_tax = _InfoRow("Income Tax Form", "myCompanyTaxForm")
        self._row_payroll = _InfoRow("Payroll Contact", "myCompanyPayrollContact")
        for row in (
            self._row_legal,
            self._row_ein,
            self._row_ssn,
            self._row_tax,
            self._row_payroll,
        ):
            right.addWidget(row)
        right.addStretch(1)
        cols.addLayout(left, 1)
        cols.addLayout(right, 1)
        lay.addLayout(cols, 1)
        return box

    def _build_product_sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("myCompanyAccountSidebar")
        side.setMinimumWidth(260)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        product = QFrame()
        product.setObjectName("myCompanyProductBox")
        product.setStyleSheet(
            f"QFrame#myCompanyProductBox {{ background: {_MC_PANEL}; "
            f"border: 1px solid {_MC_BORDER}; border-radius: 4px; }}"
        )
        p_lay = QGridLayout(product)
        p_lay.setContentsMargins(10, 10, 10, 10)
        p_lay.setHorizontalSpacing(12)
        p_lay.setVerticalSpacing(6)
        hdr = QLabel("Product Information")
        hdr.setObjectName("myCompanyProductTitle")
        hdr.setStyleSheet(_label_qss(weight="700", color=_MC_TITLE, size="12px"))
        p_lay.addWidget(hdr, 0, 0, 1, 2)
        pairs = (
            ("Product Name", PRODUCT_DISPLAY_NAME, "myCompanyProductName"),
            ("License #", PRODUCT_LICENSE, "myCompanyLicense"),
            ("Product #", PRODUCT_NUMBER, "myCompanyProductNumber"),
            ("No. of Seats", PRODUCT_SEATS, "myCompanySeats"),
            ("Activation", PRODUCT_ACTIVATION, "myCompanyActivation"),
        )
        for i, (cap, val, name) in enumerate(pairs, start=1):
            c = QLabel(cap)
            c.setStyleSheet(_label_qss(weight="700"))
            v = QLabel(val)
            v.setObjectName(name)
            v.setStyleSheet(_label_qss(color=_MC_TEXT, size="12px"))
            p_lay.addWidget(c, i, 0)
            p_lay.addWidget(v, i, 1)
        lay.addWidget(product)
        ver = QLabel(f"ProBooks+ai v{application_version()}")
        ver.setObjectName("myCompanyProductVersion")
        ver.setStyleSheet(_label_qss(size="10px"))
        lay.addWidget(ver)
        lay.addStretch(1)
        return side

    def reload(self) -> None:
        data = load_my_company_fields(self._conn)
        self._lbl_company.setText(data["name"])
        self._row_contact.set_value(data["contact_address"])
        self._row_phone.set_value(data["phone"])
        self._row_fax.set_value(data["fax"])
        self._row_email.set_value(data["email"])
        self._row_website.set_value(data["website"])
        self._row_legal.set_value(data["legal_address"])
        self._row_ein.set_value(data["ein"])
        self._row_ssn.set_value(data["ssn"], placeholder=SSN_PLACEHOLDER)
        self._row_tax.set_value(data["tax_form"])
        self._row_payroll.set_value(data["payroll_contact"])

    def _on_edit(self) -> None:
        dlg = MyCompanyEditDialog(load_my_company_fields(self._conn), self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if self._conn is None:
            return
        try:
            save_my_company_fields(self._conn, dlg.values())
        except Exception:
            message_box_information_ok(
                self,
                "Company Information",
                "Could not save company information for this file.",
                ok_tip="Close; verify the company file is writable.",
            )
            return
        self.reload()
