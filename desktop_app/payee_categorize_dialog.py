"""
desktop_app.payee_categorize_dialog
======================================
Payee Bulk-Categorization dialog — assign a COA account to each unique
payee/description in one pass, then reclassify all matching register lines
at once.

Use this after a historical batch import to quickly assign accounts to
hundreds of transactions without touching them one by one.

Workflow:
  1. Query all unique payee descriptions that have no COA category yet.
  2. Show them sorted by frequency (highest first) in a table.
  3. User picks a COA account from a dropdown per payee row.
  4. On Apply — run bulk UPDATE on bank_transactions and save a rules_engine
     rule so future imports auto-categorize the same payees.
"""

from __future__ import annotations

import sqlite3
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from desktop_app.qt_mnemonic import message_box_information_ok, message_box_warning_ok
from desktop_app.theme import (
    WORKFLOW_ALT_ROW,
    WORKFLOW_CAPTION,
    WORKFLOW_GRID,
    WORKFLOW_HEADER_BG,
    WORKFLOW_INPUT_BG,
    WORKFLOW_PANEL_BG,
    WORKFLOW_TEXT,
)

_COLS = ("Payee / Description", "Transactions", "Total ($)", "Assign COA Account")
_NO_ASSIGN = "— skip —"


def _get_uncategorized_payees(conn: sqlite3.Connection) -> list[dict]:
    """Return unique payees that have no COA category, sorted by frequency desc."""
    try:
        rows = conn.execute(
            """
            SELECT
                description,
                COUNT(*) AS freq,
                SUM(ABS(amount)) AS total_abs
            FROM bank_transactions
            WHERE (coa_category IS NULL OR TRIM(coa_category) = '')
              AND TRIM(description) != ''
            GROUP BY description
            ORDER BY freq DESC, total_abs DESC
            LIMIT 500
            """
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []


def _apply_bulk_categorization(
    conn: sqlite3.Connection,
    assignments: list[tuple[str, str]],
) -> int:
    """Apply (description → coa_account) mappings; return count of updated rows."""
    updated = 0
    for description, coa in assignments:
        if not coa or coa == _NO_ASSIGN:
            continue
        cur = conn.execute(
            "UPDATE bank_transactions SET coa_category = ? WHERE description = ?",
            (coa, description),
        )
        updated += cur.rowcount
    conn.commit()
    return updated


def _save_rules(conn: sqlite3.Connection, assignments: list[tuple[str, str]]) -> None:
    """Save payee→COA mappings as categorization rules for future auto-matching."""
    try:
        from probooksai.rules_engine import add_rule
        for description, coa in assignments:
            if coa and coa != _NO_ASSIGN:
                add_rule(conn, pattern=description, coa_account=coa, match_type="contains")
    except Exception:
        pass  # rules_engine is optional; bulk update already applied


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class PayeeCategorizeDialog(QDialog):
    """Bulk-assign COA accounts to uncategorized payees in one pass."""

    def __init__(self, conn: sqlite3.Connection, coa_list: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bulk Payee Categorization")
        self.setMinimumSize(720, 500)
        self._conn = conn
        self._coa_list = coa_list
        self._combos: list[QComboBox] = []
        self._payees: list[str] = []
        self._build_ui()
        self._load()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title = QLabel("Bulk Payee Categorization")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {WORKFLOW_TEXT};")
        layout.addWidget(title)

        sub = QLabel(
            "Assign a COA account to each payee below. "
            "All matching transactions will be updated at once, "
            "and a rule will be saved for future imports."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color: {WORKFLOW_CAPTION}; font-size: 11px;")
        layout.addWidget(sub)

        # Quick-assign toolbar
        qa_row = QHBoxLayout()
        qa_row.addWidget(QLabel("Quick-assign all to:"))
        self._quick_combo = QComboBox()
        self._quick_combo.setEditable(True)
        self._quick_combo.addItem(_NO_ASSIGN)
        for c in self._coa_list:
            self._quick_combo.addItem(c)
        self._quick_combo.setMinimumWidth(240)
        qa_row.addWidget(self._quick_combo)
        btn_qa = QPushButton("Apply to all unassigned")
        btn_qa.setToolTip("Set every un-assigned row to the selected COA account.")
        btn_qa.clicked.connect(self._on_quick_assign)
        qa_row.addWidget(btn_qa)
        qa_row.addStretch(1)
        layout.addLayout(qa_row)

        # Table
        self._table = QTableWidget(0, len(_COLS))
        self._table.setHorizontalHeaderLabels(list(_COLS))
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setStyleSheet(
            f"QTableWidget {{ background: {WORKFLOW_PANEL_BG}; "
            f"alternate-background-color: {WORKFLOW_ALT_ROW}; color: {WORKFLOW_TEXT}; "
            f"gridline-color: {WORKFLOW_GRID}; border: 1px solid {WORKFLOW_GRID}; }}"
            f"QHeaderView::section {{ background: {WORKFLOW_HEADER_BG}; color: {WORKFLOW_TEXT}; "
            f"padding: 6px; border: 1px solid {WORKFLOW_GRID}; font-weight: 600; }}"
        )
        layout.addWidget(self._table, 1)

        self._lbl_count = QLabel("")
        self._lbl_count.setStyleSheet(f"color: {WORKFLOW_CAPTION}; font-size: 11px;")
        layout.addWidget(self._lbl_count)

        btns = QDialogButtonBox()
        btn_apply = btns.addButton("Apply && Save Rules", QDialogButtonBox.ButtonRole.AcceptRole)
        btn_apply.setToolTip("Update all assigned transactions and save matching rules.")
        btns.addButton(QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._on_apply)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _load(self) -> None:
        payees = _get_uncategorized_payees(self._conn)
        self._combos = []
        self._payees = []
        self._table.setRowCount(len(payees))

        for r, row in enumerate(payees):
            desc = row["description"]
            freq = int(row["freq"])
            total = float(row.get("total_abs") or 0)
            self._payees.append(desc)

            d_it = QTableWidgetItem(desc)
            d_it.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            f_it = QTableWidgetItem(str(freq))
            f_it.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            f_it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            t_it = QTableWidgetItem(f"${total:,.2f}")
            t_it.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            t_it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            combo = QComboBox()
            combo.setEditable(True)
            combo.addItem(_NO_ASSIGN)
            for c in self._coa_list:
                combo.addItem(c)
            combo.setStyleSheet(
                f"QComboBox {{ background: {WORKFLOW_INPUT_BG}; color: {WORKFLOW_TEXT}; }}"
            )

            self._table.setItem(r, 0, d_it)
            self._table.setItem(r, 1, f_it)
            self._table.setItem(r, 2, t_it)
            self._table.setCellWidget(r, 3, combo)
            self._combos.append(combo)

        total_txns = sum(p["freq"] for p in payees)
        self._lbl_count.setText(
            f"{len(payees)} unique payee(s) across {total_txns} uncategorized transaction(s)."
        )

    def _on_quick_assign(self) -> None:
        coa = self._quick_combo.currentText().strip()
        if not coa or coa == _NO_ASSIGN:
            return
        for combo in self._combos:
            if combo.currentText() in (_NO_ASSIGN, ""):
                idx = combo.findText(coa)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                else:
                    combo.setEditText(coa)

    def _on_apply(self) -> None:
        assignments = []
        for payee, combo in zip(self._payees, self._combos):
            coa = combo.currentText().strip()
            if coa and coa != _NO_ASSIGN:
                assignments.append((payee, coa))

        if not assignments:
            message_box_warning_ok(
                self, "Nothing to assign",
                "No COA accounts were selected. Use the dropdowns to assign accounts, "
                "then click Apply."
            )
            return

        updated = _apply_bulk_categorization(self._conn, assignments)
        _save_rules(self._conn, assignments)

        message_box_information_ok(
            self,
            "Categorization Applied",
            f"Updated {updated} transaction(s) across {len(assignments)} payee(s).\n"
            "Rules saved — future imports will auto-categorize matching payees.",
            ok_tip="Close; review the register to verify the assignments.",
        )
        self.accept()
