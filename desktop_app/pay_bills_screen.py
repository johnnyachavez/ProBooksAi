"""Pay Bills workflow screen — UI only (no database or A/P logic).

Light panel styling so the form reads clearly on top of the app dark theme.
"""

from __future__ import annotations

import random
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop_app.flexible_date import configure_qdate_edit_us

# Light “accounting form” palette (local to this screen)
_PAY_BG = "#f7f9fc"
_PAY_PANEL = "#ffffff"
_PAY_STRIPE = "#e8f2fa"
_PAY_GRID = "#c5d4e6"
_PAY_HEADER = "#dce8f4"
_PAY_TEXT = "#1a1a2e"
def _readonly_item(text: str) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    it.setForeground(Qt.GlobalColor.black)
    return it


class PayBillsScreen(QWidget):
    """List-style pay bills layout: filters, grid with checkboxes and payment entry, summary, actions."""

    _COLS = (
        "",  # checkbox (no header text)
        "Payee / Vendor",
        "Ref No.",
        "Due Date",
        "Status",
        "Approval Status",
        "Open Balance",
        "Credit Applied",
        "Payment",
        "Total Amount",
    )
    _N_ROWS = 15

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setToolTip(
            "Pay Bills (visual draft): select rows, enter payment amounts. "
            "No database or register posting yet. Same company .db (File → Backup / Restore, probooks.backup)."
        )
        self._payment_edits: list[QDoubleSpinBox] = []
        self._row_checks: list[QCheckBox] = []
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        page = QFrame()
        page.setObjectName("payBillsLightPanel")
        page.setStyleSheet(
            f"QFrame#payBillsLightPanel {{ background-color: {_PAY_BG}; border: 1px solid {_PAY_GRID}; "
            "border-radius: 8px; }}"
        )
        play = QVBoxLayout(page)
        play.setContentsMargins(16, 16, 16, 16)
        play.setSpacing(12)

        # Title row + optional top-right actions
        title_row = QHBoxLayout()
        title = QLabel("Pay Bills")
        title.setStyleSheet(
            f"font-size: 20px; font-weight: 600; color: {_PAY_TEXT}; background: transparent;"
        )
        title_row.addWidget(title)
        title_row.addStretch(1)
        self._btn_pay = QPushButton("Pay Selected Bills")
        self._btn_pay.setToolTip("Placeholder — no posting yet.")
        self._btn_pay.clicked.connect(self._on_pay_selected)
        self._btn_clear_top = QPushButton("Clear Selection")
        self._btn_clear_top.setToolTip("Uncheck all rows and clear payment fields.")
        self._btn_clear_top.clicked.connect(self._on_clear_selection)
        title_row.addWidget(self._btn_pay)
        title_row.addWidget(self._btn_clear_top)
        play.addLayout(title_row)

        # Controls row
        ctrl = QGridLayout()
        ctrl.setHorizontalSpacing(16)
        ctrl.setVerticalSpacing(8)

        self._filter = QComboBox()
        self._filter.addItems(["All", "Open", "Overdue"])
        self._filter.setToolTip("Filter bills (placeholder).")

        self._vendor_filter = QLineEdit()
        self._vendor_filter.setPlaceholderText("Vendor filter…")
        self._vendor_filter.setMinimumWidth(180)
        self._vendor_filter.setToolTip("Optional vendor search (placeholder).")

        self._pay_date = QDateEdit()
        configure_qdate_edit_us(self._pay_date)
        self._pay_date.setToolTip("Payment date (UI only).")

        self._account = QComboBox()
        self._account.addItems(["Operating — ****1234", "Payroll — ****5678", "Savings — ****9012"])
        self._account.setMinimumWidth(200)
        self._account.setToolTip("Bank account (placeholder).")

        ctrl.addWidget(QLabel("Filter:"), 0, 0)
        ctrl.addWidget(self._filter, 0, 1)
        ctrl.addWidget(QLabel("Vendor:"), 0, 2)
        ctrl.addWidget(self._vendor_filter, 0, 3)
        ctrl.addWidget(QLabel("Payment date:"), 0, 4)
        ctrl.addWidget(self._pay_date, 0, 5)
        ctrl.addWidget(QLabel("Account:"), 0, 6)
        ctrl.addWidget(self._account, 0, 7)
        for c in range(8):
            ctrl.setColumnStretch(c, 0)
        ctrl.setColumnStretch(7, 1)
        play.addLayout(ctrl)

        # Table
        self._table = QTableWidget(self._N_ROWS, len(self._COLS))
        self._table.setObjectName("payBillsTable")
        self._table.setHorizontalHeaderLabels(self._COLS)
        self._table.verticalHeader().setVisible(True)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for col in (0, 2, 3, 4, 5, 6, 7, 8, 9):
            self._table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents
            )

        self._table.setStyleSheet(
            f"QTableWidget#payBillsTable {{"
            f" background-color: {_PAY_PANEL};"
            f" alternate-background-color: {_PAY_STRIPE};"
            f" color: {_PAY_TEXT};"
            f" gridline-color: {_PAY_GRID};"
            f" border: 1px solid {_PAY_GRID};"
            " }"
            f"QHeaderView::section {{"
            f" background-color: {_PAY_HEADER};"
            f" color: {_PAY_TEXT};"
            f" padding: 6px; border: 1px solid {_PAY_GRID};"
            " font-weight: 600;"
            " }}"
        )

        rng = random.Random(42)
        vendors = [
            "Acme Supplies Co.",
            "Northwind Electric",
            "Contoso Logistics",
            "Fabrikam Office",
            "Litware Services",
            "Adventure Works",
            "Wide World Importers",
        ]
        statuses = ("Open", "Open", "Open", "Partial", "Open")
        approvals = ("Approved", "Pending", "Approved", "Pending", "Approved")

        for row in range(self._N_ROWS):
            cb = QCheckBox()
            cb.setStyleSheet("background: transparent; margin-left: 8px;")
            self._table.setCellWidget(row, 0, cb)
            self._row_checks.append(cb)

            v = vendors[rng.randint(0, len(vendors) - 1)]
            ref = f"INV-{2000 + row}-{rng.randint(10, 99)}"
            due = f"2025-{1 + (row % 12):02d}-{(row % 28) + 1:02d}"
            open_bal = rng.randint(50, 5000) + rng.random()
            open_s = f"{open_bal:,.2f}"
            credit_s = "0.00" if rng.random() > 0.2 else f"{rng.randint(0, 50):.2f}"
            total_s = open_s

            self._table.setItem(row, 1, _readonly_item(v))
            self._table.setItem(row, 2, _readonly_item(ref))
            self._table.setItem(row, 3, _readonly_item(due))
            self._table.setItem(row, 4, _readonly_item(statuses[row % len(statuses)]))
            self._table.setItem(row, 5, _readonly_item(approvals[row % len(approvals)]))
            self._table.setItem(row, 6, _readonly_item(open_s))
            self._table.setItem(row, 7, _readonly_item(credit_s))

            pay_spin = QDoubleSpinBox()
            pay_spin.setRange(0.0, 999_999_999.99)
            pay_spin.setDecimals(2)
            pay_spin.setPrefix("$ ")
            pay_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
            pay_spin.setStyleSheet(
                f"QDoubleSpinBox {{ background: {_PAY_PANEL}; border: 1px solid {_PAY_GRID}; "
                f"padding: 2px 6px; color: {_PAY_TEXT}; }}"
            )
            pay_spin.setToolTip("Payment amount for this bill (UI only).")
            self._table.setCellWidget(row, 8, pay_spin)
            self._payment_edits.append(pay_spin)

            self._table.setItem(row, 9, _readonly_item(total_s))

            cb.stateChanged.connect(lambda *_: self._refresh_summary())
            pay_spin.valueChanged.connect(lambda *_: self._refresh_summary())

        play.addWidget(self._table, 1)

        # Summary
        sum_frame = QFrame()
        sum_frame.setStyleSheet(
            f"background-color: {_PAY_PANEL}; border: 1px solid {_PAY_GRID}; border-radius: 6px;"
        )
        sum_lay = QHBoxLayout(sum_frame)
        sum_lay.setContentsMargins(12, 10, 12, 10)
        self._lbl_selected = QLabel("Total selected: 0")
        self._lbl_payment_sum = QLabel("Total payment amount: $0.00")
        for lb in (self._lbl_selected, self._lbl_payment_sum):
            lb.setStyleSheet(f"color: {_PAY_TEXT}; font-size: 13px;")
        sum_lay.addWidget(self._lbl_selected)
        sum_lay.addSpacing(32)
        sum_lay.addWidget(self._lbl_payment_sum)
        sum_lay.addStretch(1)
        play.addWidget(sum_frame)

        # Bottom actions (duplicate for workflow familiarity)
        bot = QHBoxLayout()
        bot.addStretch(1)
        self._btn_pay_bot = QPushButton("Pay Selected Bills")
        self._btn_pay_bot.clicked.connect(self._on_pay_selected)
        self._btn_clear_bot = QPushButton("Clear Selection")
        self._btn_clear_bot.clicked.connect(self._on_clear_selection)
        bot.addWidget(self._btn_pay_bot)
        bot.addWidget(self._btn_clear_bot)
        play.addLayout(bot)

        outer.addWidget(page, 1)
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        n = sum(1 for c in self._row_checks if c.isChecked())
        total = sum(s.value() for s, c in zip(self._payment_edits, self._row_checks) if c.isChecked())
        self._lbl_selected.setText(f"Total selected: {n}")
        self._lbl_payment_sum.setText(f"Total payment amount: ${total:,.2f}")

    def _on_pay_selected(self) -> None:
        n = sum(1 for c in self._row_checks if c.isChecked())
        total = sum(s.value() for s, c in zip(self._payment_edits, self._row_checks) if c.isChecked())
        print(f"[Pay Bills] Pay Selected (placeholder): {n} row(s), total payments ${total:,.2f}")

    def _on_clear_selection(self) -> None:
        for c in self._row_checks:
            c.setChecked(False)
        for s in self._payment_edits:
            s.setValue(0.0)
        self._lbl_selected.setText("Total selected: 0")
        self._lbl_payment_sum.setText("Total payment amount: $0.00")
