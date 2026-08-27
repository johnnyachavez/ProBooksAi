"""Use Register — QuickBooks Pro account picker, then the two-line checkbook.

The Reg icon / Home Check Register opens this small dialog. OK opens the same
register as double-clicking a Chart of Accounts row. Cancel / close does nothing.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from desktop_app.qt_combo_ids import coerce_combo_int_id
from desktop_app.qt_mnemonic import escape_ampersand_for_qt, tip_qdialog_button_box
from probooksai.bank_import import BankDatabase

_UR_CANVAS = "#E8ECF1"
_UR_PAPER = "#FFFFFF"
_UR_TEXT = "#1A1A1A"
_UR_CAPTION = "#4A5560"
_UR_ACCENT = "#2563A8"
_UR_GRID = "#C0C8D0"


class UseRegisterDialog(QDialog):
    """Select Account → OK opens that account's register; Cancel closes."""

    def __init__(
        self,
        bank_db: BankDatabase,
        *,
        initial_account_id: Optional[int] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._db = bank_db
        self.setObjectName("useRegisterDialog")
        self.setWindowTitle("Use Register")
        self.setModal(True)
        self.resize(360, 120)
        self.setToolTip(
            "Choose which account register to open. OK shows the two-line checkbook; Cancel closes."
        )
        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window, QColor(_UR_CANVAS))
        pal.setColor(QPalette.ColorRole.WindowText, QColor(_UR_TEXT))
        pal.setColor(QPalette.ColorRole.Base, QColor(_UR_PAPER))
        pal.setColor(QPalette.ColorRole.Text, QColor(_UR_TEXT))
        pal.setColor(QPalette.ColorRole.Button, QColor(_UR_PAPER))
        pal.setColor(QPalette.ColorRole.ButtonText, QColor(_UR_TEXT))
        pal.setColor(QPalette.ColorRole.Highlight, QColor(_UR_ACCENT))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
        self.setPalette(pal)
        self.setAutoFillBackground(True)
        self.setStyleSheet(
            f"UseRegisterDialog {{ background-color: {_UR_CANVAS}; color: {_UR_TEXT}; }}"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(12)

        row = QHBoxLayout()
        row.setSpacing(10)
        lbl = QLabel("Select Account")
        lbl.setObjectName("useRegisterSelectLabel")
        lbl.setStyleSheet(
            f"color: {_UR_CAPTION}; font-size: 12px; background: transparent; border: none;"
        )
        row.addWidget(lbl)
        self._account = QComboBox()
        self._account.setObjectName("useRegisterAccount")
        self._account.setMinimumWidth(220)
        self._account.setStyleSheet(
            f"QComboBox {{ background: {_UR_PAPER}; border: 1px solid {_UR_GRID}; "
            f"padding: 2px 8px; color: {_UR_TEXT}; }}"
        )
        self._account.setToolTip("Bank account whose two-line register will open.")
        row.addWidget(self._account, 1)
        lay.addLayout(row)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.setObjectName("useRegisterButtons")
        btns.setStyleSheet(
            f"QPushButton {{ background: #F7F8FA; border: 1px solid {_UR_GRID}; "
            f"border-radius: 4px; color: {_UR_TEXT}; padding: 4px 18px; }}"
            f"QPushButton:default {{ background-color: {_UR_ACCENT}; color: #FFFFFF; "
            f"border: 1px solid {_UR_ACCENT}; font-weight: 600; }}"
        )
        tip_qdialog_button_box(
            btns,
            ok="Open the two-line register for the selected account.",
            cancel="Close without opening a register.",
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        self._populate(initial_account_id)

    def _populate(self, initial_account_id: Optional[int]) -> None:
        self._account.clear()
        accounts = []
        if self._db is not None:
            try:
                accounts = list(self._db.list_bank_accounts())
            except Exception:
                accounts = []
        if not accounts:
            self._account.addItem("(no bank accounts)", None)
            return
        want = coerce_combo_int_id(initial_account_id)
        pick = 0
        for i, acct in enumerate(accounts):
            aid = coerce_combo_int_id(acct["id"])
            if aid is None:
                continue
            name = str(acct["name"] or "").strip() or f"Account {aid}"
            self._account.addItem(escape_ampersand_for_qt(name), aid)
            if want is not None and aid == want:
                pick = self._account.count() - 1
        self._account.setCurrentIndex(pick)

    def selected_bank_account_id(self) -> Optional[int]:
        return coerce_combo_int_id(self._account.currentData())
