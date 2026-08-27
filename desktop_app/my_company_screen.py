"""My Company — QuickBooks Pro Desktop-style company information page.

Layout only: boxed company information, account/product sidebar, apps bar,
and a recommended-apps carousel. Slightly roomier than a gray Win32 photocopy;
not QuickBooks Online.

Home → My Company opens this screen. Identity values stay blank or generic
placeholders (header COMPANY NAME). This page does not buy apps or services.
"""

from __future__ import annotations

import sqlite3
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
    QPushButton,
    QScrollArea,
    QSizePolicy,
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

_MC_CANVAS = "#E8ECF1"
_MC_PAPER = "#FFFFFF"
_MC_PANEL = "#F4F7FA"
_MC_BORDER = "#C5CDD6"
_MC_LINE = "#D8DEE6"
_MC_TEXT = "#1A1A1A"
_MC_CAPTION = "#4A5560"
_MC_TITLE = "#5B6770"
_MC_ACCENT = "#2563A8"
_MC_LINK = "#1565C0"
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

_RECOMMENDED = (
    ("cart", "Get E-commerce Integration", "Connect an online store to invoices and payments."),
    ("payroll", "Turn On Payroll", "Track pay runs when payroll is enabled later."),
    ("cards", "Accept Credit Cards", "Record card payments you already take."),
    ("checks", "Order Checks", "Print checks from Write Checks when you are ready."),
    ("plus", "ProBooks+ai Desktop Plus", "More seats and desktop tools when you need them."),
    ("inventory", "Advanced Inventory", "Item quantities stay on the Item List for now."),
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


def _link_qss() -> str:
    return (
        f"QPushButton {{ background: transparent; border: none; color: {_MC_LINK}; "
        "font-size: 12px; text-align: left; padding: 2px 0px; }}"
        f"QPushButton:hover {{ color: {_MC_ACCENT}; }}"
    )


def _primary_btn_qss() -> str:
    return (
        f"QPushButton {{ background-color: {_MC_ACCENT}; border: 1px solid {_MC_ACCENT}; "
        "border-radius: 3px; color: #FFFFFF; font-size: 13px; font-weight: 700; "
        "padding: 8px 16px; }"
        "QPushButton:hover { background-color: #1D4F8C; }"
        "QPushButton:pressed { background-color: #163E6E; }"
    )


def _setting(conn: Optional[sqlite3.Connection], key: str) -> str:
    if conn is None:
        return ""
    try:
        return (business.get_setting(conn, key, "") or "").strip()
    except Exception:
        return ""


def load_my_company_fields(conn: Optional[sqlite3.Connection]) -> dict[str, str]:
    """Read My Company fields. Empty company files stay blank except the header placeholder."""
    data = {ui: _setting(conn, db_key) for ui, db_key in _FIELD_KEYS}
    name = _setting(conn, "company_name")
    data["name"] = name if name else PLACEHOLDER_COMPANY_NAME
    if not data["tax_form"]:
        data["tax_form"] = _setting(conn, "company_tax_structure")
    return data


def save_my_company_fields(conn: sqlite3.Connection, values: dict[str, str]) -> None:
    """Persist editable My Company fields. Does not write a legal name into defaults."""
    name = (values.get("name") or "").strip()
    if name == PLACEHOLDER_COMPANY_NAME:
        name = ""
    business.set_setting(conn, "company_name", name)
    mapping = dict(_FIELD_KEYS)
    for ui, db_key in mapping.items():
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


def _app_icon_pixmap(kind: str, size: int = 40) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    box = QRectF(2, 2, size - 4, size - 4)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#E8F1FA"))
    p.drawEllipse(box)
    p.setPen(QPen(QColor(_MC_ACCENT), 1.4))
    p.setBrush(QColor("#D6E8F8"))
    inner = box.adjusted(6, 6, -6, -6)
    if kind == "cart":
        p.drawRoundedRect(inner.adjusted(2, 6, -2, -8), 2, 2)
        p.setBrush(QColor(_MC_ACCENT))
        p.drawEllipse(QPointF(inner.left() + 8, inner.bottom() - 2), 2.4, 2.4)
        p.drawEllipse(QPointF(inner.right() - 8, inner.bottom() - 2), 2.4, 2.4)
    elif kind == "payroll":
        p.drawRoundedRect(inner, 2, 2)
        p.setPen(QPen(QColor(_MC_ACCENT), 1.1))
        for i in range(3):
            y = inner.top() + 6 + i * 5
            p.drawLine(QPointF(inner.left() + 4, y), QPointF(inner.right() - 4, y))
    elif kind == "cards":
        p.drawRoundedRect(inner.adjusted(0, 4, 0, -4), 3, 3)
        p.setBrush(QColor(_MC_ACCENT))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(QRectF(inner.left(), inner.top() + 8, inner.width(), 5))
    elif kind == "checks":
        p.drawRoundedRect(inner.adjusted(1, 3, -1, -3), 2, 2)
        p.setPen(QPen(QColor(_MC_ACCENT), 1.1))
        p.drawLine(
            QPointF(inner.left() + 4, inner.center().y()),
            QPointF(inner.right() - 4, inner.center().y()),
        )
    elif kind == "plus":
        p.drawRoundedRect(inner, 3, 3)
        p.setPen(QPen(QColor(_MC_ACCENT), 1.1))
        p.drawLine(QPointF(inner.center().x(), inner.top() + 4), QPointF(inner.center().x(), inner.bottom() - 4))
        p.drawLine(QPointF(inner.left() + 4, inner.center().y()), QPointF(inner.right() - 4, inner.center().y()))
    else:
        p.setBrush(QColor("#43A047"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(QRectF(inner.left() + 2, inner.bottom() - 8, 5, 6))
        p.setBrush(QColor("#F9A825"))
        p.drawRect(QRectF(inner.left() + 9, inner.bottom() - 12, 5, 10))
        p.setBrush(QColor(_MC_ACCENT))
        p.drawRect(QRectF(inner.left() + 16, inner.bottom() - 16, 5, 14))
    p.end()
    return pm


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


class _AppCard(QFrame):
    clicked = Signal(str)

    def __init__(self, kind: str, title: str, body: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._kind = kind
        self.setObjectName(f"myCompanyAppCard_{kind}")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(168, 148)
        self.setStyleSheet(
            f"QFrame#myCompanyAppCard_{kind} {{ background: {_MC_PAPER}; "
            f"border: 1px solid {_MC_BORDER}; border-radius: 4px; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 10)
        lay.setSpacing(6)
        icon = QLabel()
        icon.setPixmap(_app_icon_pixmap(kind))
        icon.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        icon.setStyleSheet("background: transparent; border: none;")
        lay.addWidget(icon)
        ttl = QLabel(title)
        ttl.setTextFormat(Qt.TextFormat.PlainText)
        ttl.setWordWrap(True)
        ttl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        ttl.setStyleSheet(_label_qss(color=_MC_TEXT, size="12px", weight="700"))
        lay.addWidget(ttl)
        desc = QLabel(body)
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        desc.setStyleSheet(_label_qss(size="10px"))
        lay.addWidget(desc, 1)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._kind)
        super().mousePressEvent(event)


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
            "Edit contact and legal fields stored in this company file. "
            "Header placeholder stays COMPANY NAME until you save a display name."
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
    """QB Pro My Company: company information, product block, recommended apps."""

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
        sign_in = QPushButton("Sign In")
        sign_in.setObjectName("myCompanySignIn")
        sign_in.setCursor(Qt.CursorShape.PointingHandCursor)
        sign_in.setStyleSheet(_link_qss())
        sign_in.setToolTip("Account sign-in is a layout placeholder on this page.")
        sign_in.clicked.connect(self._on_placeholder_account)
        header.addWidget(sign_in, 0, Qt.AlignmentFlag.AlignTop)
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
        main_lay.addWidget(self._build_account_sidebar(), 2)
        board.addWidget(main_card)

        apps_bar = QFrame()
        apps_bar.setObjectName("myCompanyAppsBar")
        apps_bar.setStyleSheet(
            f"QFrame#myCompanyAppsBar {{ background: {_MC_PANEL}; "
            f"border: 1px solid {_MC_BORDER}; border-radius: 4px; }}"
        )
        bar = QHBoxLayout(apps_bar)
        bar.setContentsMargins(14, 8, 14, 8)
        manage = QLabel("MANAGE YOUR APPS, SERVICES & SUBSCRIPTIONS")
        manage.setObjectName("myCompanyManageAppsLabel")
        manage.setTextFormat(Qt.TextFormat.PlainText)
        manage.setStyleSheet(_label_qss(size="11px", weight="700", color=_MC_TITLE))
        bar.addWidget(manage)
        bar.addStretch(1)
        missing = QPushButton("Not seeing all your services?")
        missing.setObjectName("myCompanyMissingServices")
        missing.setCursor(Qt.CursorShape.PointingHandCursor)
        missing.setStyleSheet(_link_qss())
        missing.clicked.connect(self._on_placeholder_account)
        bar.addWidget(missing)
        board.addWidget(apps_bar)

        rec_title = QLabel("APPS, SERVICES & SUBSCRIPTIONS RECOMMENDED FOR YOU")
        rec_title.setObjectName("myCompanyRecommendedTitle")
        rec_title.setTextFormat(Qt.TextFormat.PlainText)
        rec_title.setStyleSheet(_label_qss(size="11px", weight="700", color=_MC_TITLE))
        board.addWidget(rec_title)
        board.addWidget(self._build_carousel())
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

    def _build_account_sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("myCompanyAccountSidebar")
        side.setMinimumWidth(260)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        manage = QPushButton("Manage Your Account")
        manage.setObjectName("myCompanyManageAccount")
        manage.setCursor(Qt.CursorShape.PointingHandCursor)
        manage.setStyleSheet(_primary_btn_qss())
        manage.setToolTip("Account management is a layout placeholder on this page.")
        manage.clicked.connect(self._on_placeholder_account)
        lay.addWidget(manage)

        links_title = QLabel("Quick links")
        links_title.setStyleSheet(_label_qss(weight="700", color=_MC_TITLE))
        lay.addWidget(links_title)
        for key, caption in (
            ("history", "Order/Payment History"),
            ("users", "Authorized Users"),
            ("methods", "Payment Methods"),
            ("details", "Account Details"),
        ):
            btn = QPushButton(f"•  {caption}")
            btn.setObjectName(f"myCompanyQuickLink_{key}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(_link_qss())
            btn.clicked.connect(self._on_placeholder_account)
            lay.addWidget(btn)

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

    def _build_carousel(self) -> QWidget:
        wrap = QWidget()
        wrap.setObjectName("myCompanyCarousel")
        row = QHBoxLayout(wrap)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        def _arrow(name: str, text: str) -> QToolButton:
            btn = QToolButton()
            btn.setObjectName(name)
            btn.setText(text)
            btn.setFixedSize(28, 148)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                f"QToolButton {{ background: {_MC_PAPER}; border: 1px solid {_MC_BORDER}; "
                f"border-radius: 4px; color: {_MC_TITLE}; font-size: 16px; font-weight: 700; }}"
                "QToolButton:hover { background: #E8F1FA; }"
            )
            return btn

        self._btn_prev = _arrow("myCompanyCarouselPrev", "<")
        self._btn_next = _arrow("myCompanyCarouselNext", ">")
        self._btn_prev.clicked.connect(lambda: self._scroll_carousel(-180))
        self._btn_next.clicked.connect(lambda: self._scroll_carousel(180))
        row.addWidget(self._btn_prev)

        self._carousel_scroll = QScrollArea()
        self._carousel_scroll.setObjectName("myCompanyCarouselScroll")
        self._carousel_scroll.setWidgetResizable(False)
        self._carousel_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._carousel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._carousel_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._carousel_scroll.setFixedHeight(156)
        self._carousel_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        host = QWidget()
        host.setObjectName("myCompanyCarouselHost")
        cards = QHBoxLayout(host)
        cards.setContentsMargins(0, 0, 0, 0)
        cards.setSpacing(10)
        for kind, title, body in _RECOMMENDED:
            card = _AppCard(kind, title, body)
            card.clicked.connect(self._on_placeholder_app)
            cards.addWidget(card)
        host.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        host.adjustSize()
        self._carousel_scroll.setWidget(host)
        row.addWidget(self._carousel_scroll, 1)
        row.addWidget(self._btn_next)
        return wrap

    def _scroll_carousel(self, delta: int) -> None:
        bar = self._carousel_scroll.horizontalScrollBar()
        bar.setValue(bar.value() + int(delta))

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

    def _on_placeholder_account(self) -> None:
        message_box_information_ok(
            self,
            "Account",
            "This control is layout-only. Nothing is purchased or billed from My Company.",
            ok_tip="Close; company information stays in this company file.",
        )

    def _on_placeholder_app(self, _kind: str = "") -> None:
        message_box_information_ok(
            self,
            "Recommended for you",
            "These cards match the My Company layout. They do not subscribe to a service.",
            ok_tip="Close; keep using ProBooks+ai from Home and the other tabs.",
        )
