"""
desktop_app.first_run_wizard
==============================
First-run wizard — shown automatically when ProBooks+ai starts with no
company file configured.

Steps
-----
  1. Welcome         — Create new company  OR  Open existing
  2. Company file    — Pick a path for the new .db file
  3. Company info    — Name, address, phone, email, website
  4. Bank account    — First checking/savings account (optional)
  5. Done            — Summary + launch button

On finish the wizard returns the chosen .db path so the main window can
call _switch_company_database() to open it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from desktop_app.qt_mnemonic import message_box_warning_ok
from desktop_app.theme import (
    WORKFLOW_CAPTION,
    WORKFLOW_INPUT_BG,
    WORKFLOW_PAGE_BG,
    WORKFLOW_PANEL_BG,
    WORKFLOW_TEXT,
)

_ACCENT = "#1565C0"
_ACCENT_LIGHT = "#E3F0FF"
_CARD_BG = "#1E2A3A"
_BORDER = "#2C3E55"


def _label(text: str, bold: bool = False, small: bool = False) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    size = "11px" if small else "13px"
    weight = "700" if bold else "400"
    lbl.setStyleSheet(f"color: {WORKFLOW_TEXT}; font-size: {size}; font-weight: {weight};")
    return lbl


def _caption(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color: {WORKFLOW_CAPTION}; font-size: 11px;")
    return lbl


def _field(placeholder: str = "", max_width: int = 0) -> QLineEdit:
    f = QLineEdit()
    f.setPlaceholderText(placeholder)
    f.setStyleSheet(
        f"QLineEdit {{ background: {WORKFLOW_INPUT_BG}; color: {WORKFLOW_TEXT}; "
        f"border: 1px solid {_BORDER}; border-radius: 4px; padding: 6px 8px; font-size: 13px; }}"
        f"QLineEdit:focus {{ border-color: {_ACCENT}; }}"
    )
    if max_width:
        f.setMaximumWidth(max_width)
    return f


# ---------------------------------------------------------------------------
# Individual page builders
# ---------------------------------------------------------------------------

class FirstRunWizard(QDialog):
    """
    Multi-step first-run wizard.

    After exec() returns Accepted, read .db_path for the chosen file path.
    The wizard does NOT open the database — caller does that.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to ProBooks+ai")
        self.setMinimumSize(560, 480)
        self.setStyleSheet(f"QDialog {{ background: {WORKFLOW_PAGE_BG}; }}")

        self.db_path: Optional[str] = None          # set on finish
        self.company_data: dict = {}                 # name/address/etc.
        self.bank_account_data: Optional[dict] = None  # None = skipped

        self._build_ui()

    # -- UI ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top colour bar ──────────────────────────────────────────────
        bar = QWidget()
        bar.setFixedHeight(6)
        bar.setStyleSheet(f"background: {_ACCENT};")
        root.addWidget(bar)

        # ── Content area ────────────────────────────────────────────────
        content = QWidget()
        content.setStyleSheet(f"background: {WORKFLOW_PAGE_BG};")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(40, 28, 40, 20)
        content_layout.setSpacing(0)

        # Step title
        self._lbl_step = QLabel("Step 1 of 4")
        self._lbl_step.setStyleSheet(
            f"color: {_ACCENT}; font-size: 11px; font-weight: 600; "
            "text-transform: uppercase; letter-spacing: 1px;"
        )
        content_layout.addWidget(self._lbl_step)

        self._lbl_title = QLabel("")
        self._lbl_title.setStyleSheet(
            f"color: {WORKFLOW_TEXT}; font-size: 20px; font-weight: 700; margin-bottom: 4px;"
        )
        content_layout.addWidget(self._lbl_title)

        self._lbl_sub = QLabel("")
        self._lbl_sub.setWordWrap(True)
        self._lbl_sub.setStyleSheet(f"color: {WORKFLOW_CAPTION}; font-size: 12px; margin-bottom: 16px;")
        content_layout.addWidget(self._lbl_sub)

        # Stacked pages
        self._stack = QStackedWidget()
        content_layout.addWidget(self._stack, 1)

        self._stack.addWidget(self._build_page_welcome())      # 0
        self._stack.addWidget(self._build_page_file())         # 1
        self._stack.addWidget(self._build_page_company())      # 2
        self._stack.addWidget(self._build_page_bank())         # 3
        self._stack.addWidget(self._build_page_done())         # 4

        root.addWidget(content, 1)

        # ── Bottom nav bar ───────────────────────────────────────────────
        nav = QWidget()
        nav.setStyleSheet(f"background: {WORKFLOW_PANEL_BG}; border-top: 1px solid {_BORDER};")
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(40, 12, 40, 12)

        self._btn_back = QPushButton("← Back")
        self._btn_back.setVisible(False)
        self._btn_back.setStyleSheet(self._ghost_btn_style())
        self._btn_back.clicked.connect(self._go_back)
        nav_layout.addWidget(self._btn_back)

        nav_layout.addStretch(1)

        self._btn_skip = QPushButton("Skip this step")
        self._btn_skip.setVisible(False)
        self._btn_skip.setStyleSheet(self._ghost_btn_style())
        self._btn_skip.clicked.connect(self._go_skip)
        nav_layout.addWidget(self._btn_skip)

        self._btn_next = QPushButton("Next →")
        self._btn_next.setStyleSheet(self._primary_btn_style())
        self._btn_next.clicked.connect(self._go_next)
        nav_layout.addWidget(self._btn_next)

        root.addWidget(nav)

        self._goto(0)

    # -- Pages ---------------------------------------------------------------

    def _build_page_welcome(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(12)

        for icon, title, desc, tag in [
            ("📁", "Create a new company", "Start fresh — ProBooks+ai creates a new database file for you.", "new"),
            ("📂", "Open an existing company", "You already have a ProBooks+ai .db file on this machine.", "open"),
        ]:
            card = self._choice_card(icon, title, desc, tag)
            lay.addWidget(card)

        lay.addStretch(1)
        self._welcome_choice = "new"  # default
        return w

    def _choice_card(self, icon: str, title: str, desc: str, tag: str) -> QWidget:
        card = QWidget()
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setStyleSheet(
            f"QWidget {{ background: {_CARD_BG}; border: 2px solid "
            f"{'#1565C0' if tag == 'new' else _BORDER}; border-radius: 8px; }}"
        )
        lay = QHBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)

        ico = QLabel(icon)
        ico.setStyleSheet("font-size: 28px; border: none;")
        ico.setFixedWidth(40)
        lay.addWidget(ico)

        txt = QVBoxLayout()
        txt.setSpacing(2)
        t = QLabel(title)
        t.setStyleSheet(f"color: {WORKFLOW_TEXT}; font-size: 14px; font-weight: 600; border: none;")
        d = QLabel(desc)
        d.setStyleSheet(f"color: {WORKFLOW_CAPTION}; font-size: 11px; border: none;")
        txt.addWidget(t)
        txt.addWidget(d)
        lay.addLayout(txt)

        radio = QLabel("●" if tag == "new" else "○")
        radio.setObjectName(f"radio_{tag}")
        radio.setStyleSheet(f"color: {'#1565C0' if tag == 'new' else WORKFLOW_CAPTION}; font-size: 18px; border: none;")
        radio.setFixedWidth(24)
        lay.addWidget(radio)

        card.mousePressEvent = lambda e, t=tag: self._on_welcome_select(t)
        return card

    def _on_welcome_select(self, tag: str) -> None:
        self._welcome_choice = tag
        # Update card borders and radio buttons
        for child in self._stack.widget(0).findChildren(QWidget):
            style = child.styleSheet()
            if "border: 2px solid" in style:
                is_new = "📁" in child.findChild(QLabel, "").text() if False else False
        # Simpler: just rebuild visual state via object names
        for w in self._stack.widget(0).findChildren(QLabel):
            name = w.objectName()
            if name == "radio_new":
                w.setText("●" if tag == "new" else "○")
                w.setStyleSheet(f"color: {'#1565C0' if tag == 'new' else WORKFLOW_CAPTION}; font-size: 18px; border: none;")
            elif name == "radio_open":
                w.setText("●" if tag == "open" else "○")
                w.setStyleSheet(f"color: {'#1565C0' if tag == 'open' else WORKFLOW_CAPTION}; font-size: 18px; border: none;")

    def _build_page_file(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(10)

        lay.addWidget(_label("Where should we save your company database?"))
        lay.addWidget(_caption(
            "Choose a location on your computer. We recommend a folder like "
            "Documents\\ProBooksAi\\. The file is a standard SQLite database you can back up any time."
        ))

        path_row = QHBoxLayout()
        self._fld_path = _field("e.g. C:\\Users\\johnn\\Documents\\ProBooksAi\\MyCompany.db")
        path_row.addWidget(self._fld_path, 1)
        btn_browse = QPushButton("Browse…")
        btn_browse.setStyleSheet(self._ghost_btn_style())
        btn_browse.clicked.connect(self._browse_file)
        path_row.addWidget(btn_browse)
        lay.addLayout(path_row)
        lay.addStretch(1)
        return w

    def _browse_file(self) -> None:
        docs = str(Path.home() / "Documents" / "ProBooksAi")
        Path(docs).mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(
            self, "Create company database", str(Path(docs) / "MyCompany.db"),
            "SQLite Database (*.db);;All Files (*.*)"
        )
        if path:
            if not path.lower().endswith(".db"):
                path += ".db"
            self._fld_path.setText(path)

    def _build_page_company(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(8)

        lay.addWidget(_caption("This appears on your invoices and reports. You can change it later in More → Business → Company."))

        fields = [
            ("Company name *", "Acme Consulting LLC", "_co_name"),
            ("Address (line 1)", "123 Main Street", "_co_addr1"),
            ("City, State, ZIP", "Springfield, IL 62701", "_co_addr2"),
            ("Phone", "(555) 123-4567", "_co_phone"),
            ("Email", "billing@mycompany.com", "_co_email"),
            ("Website", "www.mycompany.com", "_co_website"),
        ]
        for label, placeholder, attr in fields:
            lay.addWidget(_label(label, small=True))
            fld = _field(placeholder)
            setattr(self, attr, fld)
            lay.addWidget(fld)

        lay.addStretch(1)
        return w

    def _build_page_bank(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(8)

        lay.addWidget(_caption(
            "Add your primary checking or savings account. "
            "You can add more accounts later in Reconcile → Bank statements."
        ))

        lay.addWidget(_label("Account nickname *", small=True))
        self._bank_name = _field("e.g. Main Checking, Business Savings")
        lay.addWidget(self._bank_name)

        lay.addWidget(_label("Bank name", small=True))
        self._bank_institution = _field("e.g. Chase, Bank of America")
        lay.addWidget(self._bank_institution)

        acct_row = QHBoxLayout()
        acct_row.setSpacing(10)
        left = QVBoxLayout()
        left.addWidget(_label("Last 4 digits", small=True))
        self._bank_last4 = _field("1234", max_width=100)
        left.addWidget(self._bank_last4)
        acct_row.addLayout(left)

        right = QVBoxLayout()
        right.addWidget(_label("Account type", small=True))
        self._bank_type = QComboBox()
        self._bank_type.addItems(["checking", "savings", "credit card", "loan", "other"])
        self._bank_type.setStyleSheet(
            f"QComboBox {{ background: {WORKFLOW_INPUT_BG}; color: {WORKFLOW_TEXT}; "
            f"border: 1px solid {_BORDER}; border-radius: 4px; padding: 6px 8px; }}"
        )
        right.addWidget(self._bank_type)
        acct_row.addLayout(right)
        acct_row.addStretch(1)
        lay.addLayout(acct_row)

        lay.addStretch(1)
        return w

    def _build_page_done(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 16, 0, 0)
        lay.setSpacing(12)

        done_icon = QLabel("✅")
        done_icon.setStyleSheet("font-size: 48px;")
        done_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(done_icon)

        self._lbl_done_detail = QLabel("")
        self._lbl_done_detail.setWordWrap(True)
        self._lbl_done_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_done_detail.setStyleSheet(f"color: {WORKFLOW_CAPTION}; font-size: 12px;")
        lay.addWidget(self._lbl_done_detail)

        hints = QLabel(
            "<b>What's next:</b><br>"
            "• <b>Reconcile → Bank statements</b> — import your bank PDFs or CSVs<br>"
            "• <b>Tools → Opening Balance Wizard</b> — enter starting account balances<br>"
            "• <b>Invoices</b> tab — create your first invoice<br>"
            "• <b>Tools → Bulk Categorize Payees</b> — assign COA after import"
        )
        hints.setTextFormat(Qt.TextFormat.RichText)
        hints.setWordWrap(True)
        hints.setStyleSheet(
            f"color: {WORKFLOW_TEXT}; font-size: 12px; background: {_CARD_BG}; "
            f"border: 1px solid {_BORDER}; border-radius: 6px; padding: 14px;"
        )
        lay.addWidget(hints)
        lay.addStretch(1)
        return w

    # -- Navigation ----------------------------------------------------------

    _STEPS = [
        ("Step 1 of 4", "Welcome", "Let's get you set up in under 2 minutes."),
        ("Step 2 of 4", "Company file", "Where should we store your data?"),
        ("Step 3 of 4", "Company info", "Tell us about your business."),
        ("Step 4 of 4", "Bank account", "Add your primary bank account."),
        ("All done! 🎉", "You're ready to go", "Your company is set up and ready to use."),
    ]

    def _goto(self, idx: int) -> None:
        self._stack.setCurrentIndex(idx)
        step, title, sub = self._STEPS[idx]
        self._lbl_step.setText(step)
        self._lbl_title.setText(title)
        self._lbl_sub.setText(sub)

        self._btn_back.setVisible(idx > 0)
        is_last = idx == 4
        is_welcome = idx == 0
        self._btn_skip.setVisible(idx == 3)   # only bank step is skippable
        self._btn_next.setText("Get Started →" if is_last else ("Next →" if not is_last else ""))
        self._btn_next.setVisible(True)
        if is_last:
            self._btn_next.setText("Open ProBooks+ai →")
            self._btn_next.setStyleSheet(
                self._primary_btn_style().replace(_ACCENT, "#2E7D32")
            )

    def _go_next(self) -> None:
        idx = self._stack.currentIndex()

        if idx == 0:
            # Welcome — handle open existing
            if self._welcome_choice == "open":
                path, _ = QFileDialog.getOpenFileName(
                    self, "Open company database", "",
                    "SQLite Database (*.db);;All Files (*.*)"
                )
                if path:
                    self.db_path = path
                    self.accept()
                return
            self._goto(1)

        elif idx == 1:
            # Validate file path
            path = self._fld_path.text().strip()
            if not path:
                message_box_warning_ok(self, "File path required",
                    "Please enter or browse to a location for your company database.")
                return
            if not path.lower().endswith(".db"):
                path += ".db"
            self.db_path = path
            self._goto(2)

        elif idx == 2:
            # Save company info (required: name)
            name = self._co_name.text().strip()
            if not name:
                message_box_warning_ok(self, "Company name required",
                    "Please enter your company or your own name.")
                return
            addr = "\n".join(filter(None, [
                self._co_addr1.text().strip(),
                self._co_addr2.text().strip(),
            ]))
            self.company_data = {
                "company_name": name,
                "company_address": addr,
                "company_phone": self._co_phone.text().strip(),
                "company_email": self._co_email.text().strip(),
                "company_website": self._co_website.text().strip(),
            }
            self._goto(3)

        elif idx == 3:
            # Save bank account
            bname = self._bank_name.text().strip()
            if not bname:
                message_box_warning_ok(self, "Account name required",
                    "Please enter a nickname for your bank account, or click Skip.")
                return
            self.bank_account_data = {
                "name": bname,
                "bank_name": self._bank_institution.text().strip(),
                "last4": self._bank_last4.text().strip(),
                "account_type": self._bank_type.currentText(),
            }
            self._finish()

        elif idx == 4:
            self.accept()

    def _go_back(self) -> None:
        idx = self._stack.currentIndex()
        if idx > 0:
            self._goto(idx - 1)

    def _go_skip(self) -> None:
        """Skip the bank account step."""
        self.bank_account_data = None
        self._finish()

    def _finish(self) -> None:
        detail = f"Company: {self.company_data.get('company_name', '')}"
        if self.bank_account_data:
            detail += f"\nBank account: {self.bank_account_data['name']}"
        self._lbl_done_detail.setText(detail)
        self._goto(4)

    # -- Styles --------------------------------------------------------------

    def _primary_btn_style(self) -> str:
        return (
            f"QPushButton {{ background: {_ACCENT}; color: white; border: none; "
            f"border-radius: 5px; padding: 8px 20px; font-size: 13px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: #1976D2; }}"
        )

    def _ghost_btn_style(self) -> str:
        return (
            f"QPushButton {{ background: transparent; color: {WORKFLOW_TEXT}; "
            f"border: 1px solid {_BORDER}; border-radius: 5px; padding: 8px 16px; font-size: 13px; }}"
            f"QPushButton:hover {{ border-color: {_ACCENT}; color: {_ACCENT}; }}"
        )


# ---------------------------------------------------------------------------
# Helper: apply wizard results to an open DB connection
# ---------------------------------------------------------------------------

def apply_wizard_results(wizard: FirstRunWizard, bank_db) -> None:
    """
    Persist company settings and bank account from wizard into the open DB.
    Call this after _switch_company_database() has opened the new file.
    """
    conn = bank_db._conn

    # Company settings
    for key, value in wizard.company_data.items():
        if value:
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO company_settings(key, value) VALUES (?, ?)",
                    (key, value),
                )
            except Exception:
                pass
    conn.commit()

    # Bank account
    if wizard.bank_account_data:
        try:
            bank_db.add_bank_account(
                name=wizard.bank_account_data["name"],
                bank_name=wizard.bank_account_data.get("bank_name", ""),
                last4=wizard.bank_account_data.get("last4", ""),
                account_type=wizard.bank_account_data.get("account_type", "checking"),
            )
        except Exception:
            pass
