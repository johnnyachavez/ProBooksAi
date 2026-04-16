"""
AI-assisted statement line reconciliation panel (Bank Import tab).

Shows Matched / Missing / Extra with review checkboxes (UI state only; no DB writes).
**Export comparison CSV** writes the current grid (including reconciled yes/no) via
``probooksai.statement_line_match.write_line_match_comparison_csv`` (UTF-8 with BOM for Excel);
the save dialog suggests a
basename from the import batch filename (or batch id) and re-opens in the last folder used
for Bank Import CSV exports (``bank_import/last_csv_export_dir``; legacy
``bank_import/line_compare_csv_export_dir`` is still read if unset).
**Right-click** the grid for **Keyboard shortcuts…** (when wired from Bank Import), **Copy row** (TSV), **Copy statement date** / amount / description when the mock statement side is filled (**Matched** / **Missing**), **Copy register date** / amount / description when the register side is filled (**Matched** / **Extra**), **Copy register transaction id** when **Reg #** is set, and **Open linked Business record…** when Bank Import wires the register tab and that transaction has a **complete bank link**. **Double-click** a row when **Reg #** is set uses the same **Business link** prompts as **Bank register** (opens **Business** when the link is complete; otherwise an explanatory message).
"""

from __future__ import annotations

import sqlite3
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QFileDialog,
    QLabel,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from desktop_app.bank_import_csv_export_paths import (
    bank_import_csv_default_save_path,
    remember_bank_import_csv_export_parent,
    suggested_bank_import_batch_csv_filename,
)
from desktop_app.qt_combo_ids import coerce_combo_int_id
from desktop_app.qt_mnemonic import (
    CSV_EXPORT_OK_TIP_SUFFIX,
    escape_ampersand_for_qt,
    message_box_critical_ok,
    message_box_information_ok,
)
from desktop_app.table_clipboard import (
    CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX,
    VIEW_BANK_REGISTER_KEYS_TOOLTIP,
    copy_table_row_as_tsv,
)
from probooksai import business
from probooksai.statement_line_match import (
    STATUS_EXTRA,
    STATUS_MATCHED,
    STATUS_MISSING,
    write_line_match_comparison_csv,
)

if TYPE_CHECKING:
    from probooksai.bank_import import BankDatabase

_COL_REVIEWED = 0
_COL_STATUS = 1
_COL_STMT_DATE = 2
_COL_STMT_AMT = 3
_COL_STMT_DESC = 4
_COL_REG_DATE = 5
_COL_REG_AMT = 6
_COL_REG_DESC = 7
_COL_REG_ID = 8

_HEADERS = [
    "Reconciled",
    "Status",
    "Stmt date",
    "Stmt $",
    "Stmt description",
    "Register date",
    "Register $",
    "Register description",
    "Reg #",
]

# Subtle row backgrounds (R, G, B)
_BG_MATCHED = QColor(28, 60, 40)
_BG_MISSING = QColor(70, 50, 22)
_BG_EXTRA = QColor(28, 45, 70)

def _suggested_line_compare_csv_filename(batch: Optional[dict]) -> str:
    """
    Default ``*.csv`` basename for **Export comparison CSV** (import batch context).

    Uses the batch ``filename`` stem when set (sanitized); otherwise ``line-compare-batch-{id}``.
    """
    return suggested_bank_import_batch_csv_filename(
        batch,
        filename_suffix="line-compare",
        batch_id_prefix="line-compare-batch",
        when_no_batch="line-reconciliation-comparison.csv",
    )


class StatementLineMatchPanel(QGroupBox):
    """Table + controls for mock statement extract vs register classification."""

    #: Emitted after a successful compare: ``(bank_account_id, results)`` for Register **Match overlay** sync.
    line_match_results_ready = Signal(int, list)

    def __init__(
        self,
        db: BankDatabase,
        parent=None,
        *,
        bank_import_shortcuts_help: Optional[Callable[[], None]] = None,
        register_tab=None,
    ):
        super().__init__("Line Reconciliation (AI)", parent)
        self._db = db
        self._rows: list[dict] = []
        self._populating = False
        self._bank_import_shortcuts_help = bank_import_shortcuts_help
        self._register_tab = register_tab
        self.setToolTip(
            "Compare mock statement lines to register transactions for the selected batch period "
            "(Matched / Missing / Extra). Reconciled checkboxes are UI-only. "
            "**Run extract & compare** updates **Bank register → Match overlay** when wired, "
            "then focuses the register tab and shows a short **status bar** message; "
            "the usual company line returns after. "
            "Right-click the table for Copy row, field copies, and Open linked Business when **Reg #** allows. "
            "Help → Bank import shortcuts…. View → Reconcile (Ctrl+9) → Bank import; Bank Register (Ctrl+5)."
        )
        self.setStyleSheet(
            "QGroupBox { font-weight: 600; margin-top: 8px; } "
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
        )
        self._build_ui()

    def line_reconciliation_table(self) -> QTableWidget:
        return self._table

    def try_ctrl_shift_b_open_linked_business(self) -> None:
        """Same **Business link** flow as row context **Open linked Business record…** when **Reg #** resolves to a transaction id."""
        if self._register_tab is None:
            message_box_information_ok(
                self,
                "Business link",
                "Open linked Business is not available here (register tab not wired).",
                ok_tip="Close; open the company in the main window.",
            )
            return
        row = self._table.currentRow()
        if row < 0:
            message_box_information_ok(
                self,
                "Business link",
                "Click a line-reconciliation row first.",
                ok_tip="Close; pick a row in the Matched / Missing / Extra grid.",
            )
            return
        if row >= len(self._rows):
            return
        tid = coerce_combo_int_id(self._rows[row].get("register_id"))
        if tid is None:
            message_box_information_ok(
                self,
                "Business link",
                "This row has no Reg # (register transaction id).",
                ok_tip="Close; pick a Matched or Extra row with a linked register line.",
            )
            return
        self._register_tab.open_linked_business_record_for_transaction_id(tid)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        primary = QHBoxLayout()
        primary.setSpacing(8)
        self._btn_run = QPushButton("Run extract & compare")
        self._btn_run.setToolTip(
            "Build mock statement lines from the register (same period as the batch), "
            "classify Matched / Missing / Extra, and fill the table below. "
            "Syncs **Bank register → Match overlay** for this account when wired, switches there, "
            "and shows a brief status message."
        )
        self._btn_run.clicked.connect(self._on_run_clicked)
        primary.addWidget(self._btn_run)

        self._btn_mark_sel = QPushButton("Mark reconciled")
        self._btn_mark_sel.setToolTip(
            "Set the reconciled flag for selected rows (this panel only; no register or import DB writes)."
        )
        self._btn_mark_sel.clicked.connect(self._mark_reviewed_selected)
        primary.addWidget(self._btn_mark_sel)

        primary.addStretch()
        layout.addLayout(primary)

        secondary = QHBoxLayout()
        secondary.setSpacing(8)
        self._btn_mark_matched = QPushButton("Mark all matched")
        self._btn_mark_matched.setToolTip(
            "Mark every **Matched** row reconciled in this panel only (no DB writes)."
        )
        self._btn_mark_matched.clicked.connect(self._mark_reviewed_all_matched)
        secondary.addWidget(self._btn_mark_matched)

        self._btn_clear = QPushButton("Clear flags")
        self._btn_clear.setToolTip("Clear reconciled checkboxes in this table (UI only).")
        self._btn_clear.clicked.connect(self._clear_reviewed)
        secondary.addWidget(self._btn_clear)

        self._btn_export_csv = QPushButton("Export comparison CSV\u2026")
        self._btn_export_csv.setToolTip(
            "Save the current Matched / Missing / Extra rows to a UTF-8 CSV with BOM (Excel-friendly) "
            "(amounts as numbers; Reconciled column reflects checkboxes). "
            "The save dialog suggests a name from the import batch file or batch id, re-opens in the last "
            "folder used for Bank Import CSV exports (shared with reconciliation Export report CSV), "
            "or in the last import folder if you have not exported CSV yet, "
            "and appends .csv if the path has no extension."
        )
        self._btn_export_csv.clicked.connect(self._on_export_comparison_csv)
        secondary.addWidget(self._btn_export_csv)

        secondary.addStretch()
        layout.addLayout(secondary)

        self._table = QTableWidget()
        self._table.setColumnCount(len(_HEADERS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(False)
        self._table.verticalHeader().setVisible(False)
        self._table.setMinimumHeight(200)
        for c in range(len(_HEADERS)):
            self._table.horizontalHeader().setSectionResizeMode(
                c,
                QHeaderView.ResizeMode.ResizeToContents
                if c != _COL_STMT_DESC and c != _COL_REG_DESC
                else QHeaderView.ResizeMode.Stretch,
            )
        self._table.setToolTip(
            "Status colors: Matched (green tint), Missing statement-side (amber), "
            "Extra register-side (blue). Reconciled checkboxes are local UI state only. "
            "Export comparison CSV uses UTF-8 with BOM for Excel. "
            "Right-click: Export comparison CSV when the table has rows; Copy row (TSV) on a data row; "
            "Copy statement or register date, amount, or description when that side of the row has data; "
            "Copy register transaction id when **Reg #** is set; "
            "Open linked Business record when that id has a **complete bank link** (register tab wired); "
            "**Ctrl+Shift+B** when this grid has focus does the same when **Reg #** is set; "
            "**double-click** with **Reg #** set: same **Business link** messages as **Bank register**. "
            "Keyboard shortcuts when this panel is embedded in Bank Import. "
            "View → Reconcile (Ctrl+9) → Bank import; Bank Register (Ctrl+5)."
        )
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_table_context_menu)
        self._table.cellDoubleClicked.connect(self._on_line_match_cell_double_clicked)
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.selectionModel().selectionChanged.connect(
            lambda *_: self._refresh_reconciled_action_states()
        )
        layout.addWidget(self._table)

        self._summary = QLabel("—")
        self._summary.setStyleSheet("color: #A0A0B0; font-size: 11px;")
        layout.addWidget(self._summary)

        self.clear_results()

    def set_context(
        self,
        account_id: Optional[int],
        batch: Optional[dict],
    ) -> None:
        """Enable run when a batch is selected; clear table when context changes."""
        self._account_id = account_id
        self._batch = batch
        ok = account_id is not None and batch is not None
        self._btn_run.setEnabled(ok)
        self.clear_results()

    def clear_results(self) -> None:
        self._rows = []
        self._populating = True
        self._table.setRowCount(0)
        self._populating = False
        self._summary.setText("—")
        self._refresh_reconciled_action_states()

    def _refresh_reconciled_action_states(self) -> None:
        n = self._table.rowCount()
        if n <= 0:
            self._btn_mark_sel.setEnabled(False)
            self._btn_mark_matched.setEnabled(False)
            self._btn_clear.setEnabled(False)
            self._btn_export_csv.setEnabled(False)
            return
        self._btn_clear.setEnabled(True)
        self._btn_export_csv.setEnabled(True)
        has_matched = any(
            (r.get("status") or "") == STATUS_MATCHED for r in self._rows
        )
        self._btn_mark_matched.setEnabled(has_matched)
        rows_sel = self._table.selectionModel().selectedRows()
        self._btn_mark_sel.setEnabled(len(rows_sel) > 0)

    def populate(self, rows: list[dict]) -> None:
        self._rows = list(rows)
        self._populating = True
        self._table.blockSignals(True)
        self._table.setRowCount(len(rows))
        matched = missing = extra = 0
        for r, row in enumerate(rows):
            st = row.get("status") or ""
            if st == STATUS_MATCHED:
                matched += 1
            elif st == STATUS_MISSING:
                missing += 1
            elif st == STATUS_EXTRA:
                extra += 1

            rev = QTableWidgetItem()
            rev.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            rev.setCheckState(Qt.CheckState.Unchecked)
            self._table.setItem(r, _COL_REVIEWED, rev)

            st_item = QTableWidgetItem(st)
            st_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            if st == STATUS_MATCHED:
                st_item.setForeground(QColor("#6ecf8a"))
            elif st == STATUS_MISSING:
                st_item.setForeground(QColor("#e8b060"))
            elif st == STATUS_EXTRA:
                st_item.setForeground(QColor("#7eb3e8"))
            self._table.setItem(r, _COL_STATUS, st_item)

            def _text_item(text: str) -> QTableWidgetItem:
                it = QTableWidgetItem(text)
                it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                return it

            self._table.setItem(r, _COL_STMT_DATE, _text_item(str(row.get("stmt_date") or "")))
            sa = row.get("stmt_amount")
            stmt_amt = "" if st == STATUS_EXTRA else f"${float(sa):,.2f}"
            self._table.setItem(r, _COL_STMT_AMT, _text_item(stmt_amt))
            self._table.setItem(
                r, _COL_STMT_DESC, _text_item(str(row.get("stmt_description") or ""))
            )

            self._table.setItem(r, _COL_REG_DATE, _text_item(str(row.get("reg_date") or "")))
            ra = row.get("reg_amount")
            reg_amt = "" if st == STATUS_MISSING else f"${float(ra):,.2f}"
            self._table.setItem(r, _COL_REG_AMT, _text_item(reg_amt))
            self._table.setItem(
                r, _COL_REG_DESC, _text_item(str(row.get("reg_description") or ""))
            )
            rid = row.get("register_id")
            self._table.setItem(
                r,
                _COL_REG_ID,
                _text_item("" if rid is None else str(rid)),
            )

            bg = None
            if st == STATUS_MATCHED:
                bg = _BG_MATCHED
            elif st == STATUS_MISSING:
                bg = _BG_MISSING
            elif st == STATUS_EXTRA:
                bg = _BG_EXTRA
            if bg is not None:
                brush = QBrush(bg)
                for c in range(len(_HEADERS)):
                    it = self._table.item(r, c)
                    if it is not None:
                        it.setBackground(brush)

        self._table.blockSignals(False)
        self._populating = False
        self._refresh_match_summary_footer(matched, missing, extra)
        self._refresh_reconciled_action_states()

    def _refresh_match_summary_footer(
        self,
        matched: int,
        missing: int,
        extra: int,
    ) -> None:
        n = len(self._rows)
        base = (
            f"Summary: {matched} Matched, {missing} Missing, {extra} Extra ({n} rows)."
        )
        nrev = self.reviewed_count()
        if nrev:
            base += f" {nrev} row(s) marked reconciled here (UI only)."
        base += " Reconciled column does not change register or import data."
        self._summary.setText(base)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._populating or item.column() != _COL_REVIEWED:
            return
        self._sync_summary_after_review_edit()

    def _line_match_register_id_plain(self, row: int) -> str:
        if row < 0 or row >= len(self._rows):
            return ""
        rid = self._rows[row].get("register_id")
        if rid is None:
            return ""
        coerced = coerce_combo_int_id(rid)
        return "" if coerced is None else str(coerced)

    def _copy_line_match_register_id(self, row: int) -> None:
        QGuiApplication.clipboard().setText(self._line_match_register_id_plain(row))

    def _line_match_stmt_date_plain(self, row: int) -> str:
        if row < 0 or row >= len(self._rows):
            return ""
        r = self._rows[row]
        if (r.get("status") or "") == STATUS_EXTRA:
            return ""
        return str(r.get("stmt_date") or "").strip()

    def _line_match_stmt_amount_plain(self, row: int) -> str:
        if row < 0 or row >= len(self._rows):
            return ""
        r = self._rows[row]
        if (r.get("status") or "") == STATUS_EXTRA:
            return ""
        sa = r.get("stmt_amount")
        if sa is None:
            return ""
        try:
            return f"{float(sa):.2f}"
        except (TypeError, ValueError):
            return ""

    def _line_match_reg_date_plain(self, row: int) -> str:
        if row < 0 or row >= len(self._rows):
            return ""
        r = self._rows[row]
        if (r.get("status") or "") == STATUS_MISSING:
            return ""
        return str(r.get("reg_date") or "").strip()

    def _line_match_reg_amount_plain(self, row: int) -> str:
        if row < 0 or row >= len(self._rows):
            return ""
        r = self._rows[row]
        if (r.get("status") or "") == STATUS_MISSING:
            return ""
        ra = r.get("reg_amount")
        if ra is None:
            return ""
        try:
            return f"{float(ra):.2f}"
        except (TypeError, ValueError):
            return ""

    def _line_match_stmt_description_plain(self, row: int) -> str:
        if row < 0 or row >= len(self._rows):
            return ""
        r = self._rows[row]
        if (r.get("status") or "") == STATUS_EXTRA:
            return ""
        return str(r.get("stmt_description") or "").strip()

    def _line_match_reg_description_plain(self, row: int) -> str:
        if row < 0 or row >= len(self._rows):
            return ""
        r = self._rows[row]
        if (r.get("status") or "") == STATUS_MISSING:
            return ""
        return str(r.get("reg_description") or "").strip()

    def _copy_line_match_stmt_date(self, row: int) -> None:
        QGuiApplication.clipboard().setText(self._line_match_stmt_date_plain(row))

    def _copy_line_match_stmt_amount(self, row: int) -> None:
        QGuiApplication.clipboard().setText(self._line_match_stmt_amount_plain(row))

    def _copy_line_match_reg_date(self, row: int) -> None:
        QGuiApplication.clipboard().setText(self._line_match_reg_date_plain(row))

    def _copy_line_match_reg_amount(self, row: int) -> None:
        QGuiApplication.clipboard().setText(self._line_match_reg_amount_plain(row))

    def _copy_line_match_stmt_description(self, row: int) -> None:
        QGuiApplication.clipboard().setText(self._line_match_stmt_description_plain(row))

    def _copy_line_match_reg_description(self, row: int) -> None:
        QGuiApplication.clipboard().setText(self._line_match_reg_description_plain(row))

    def _on_line_match_cell_double_clicked(self, row: int, col: int) -> None:
        """Double-click: same **Business link** behavior as register **Match** when **Reg #** is set."""
        del col
        if self._register_tab is None:
            return
        if row < 0 or row >= len(self._rows):
            return
        tid = coerce_combo_int_id(self._rows[row].get("register_id"))
        if tid is None:
            return
        self._register_tab.open_linked_business_record_for_transaction_id(tid)

    def _on_table_context_menu(self, pos) -> None:
        menu = QMenu(self)
        if self._bank_import_shortcuts_help is not None:
            act_keys = menu.addAction(
                "Keyboard shortcuts…", self._bank_import_shortcuts_help
            )
            act_keys.setToolTip(
                "Same summary as Help → Bank import shortcuts… "
                "(F5, batches, register preview, AI line reconciliation, row field copies). "
                + VIEW_BANK_REGISTER_KEYS_TOOLTIP
                + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
            )
        if self._rows:
            if menu.actions():
                menu.addSeparator()
            act_export = menu.addAction(
                "Export comparison CSV\u2026", self._on_export_comparison_csv
            )
            act_export.setToolTip(
                "Save all rows to a UTF-8 CSV with BOM (same as the toolbar button; "
                "suggested name from the import batch; shared export folder with reconciliation report CSV; "
                "last import folder if you have not exported CSV yet). "
                + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
            )
        idx = self._table.indexAt(pos)
        if idx.isValid() and idx.row() >= 0:
            if menu.actions():
                menu.addSeparator()
            row = idx.row()
            act_copy = menu.addAction(
                "Copy row", partial(copy_table_row_as_tsv, self._table, row)
            )
            act_copy.setToolTip(
                "Copy this reconciliation row as tab-separated text for pasting into a spreadsheet or editor. "
                + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
            )
            sd = self._line_match_stmt_date_plain(row)
            if sd:
                act_sd = menu.addAction(
                    "Copy statement date", partial(self._copy_line_match_stmt_date, row)
                )
                act_sd.setToolTip(
                    "Copy the statement-side date for this row (mock extract; **Stmt date** column). "
                    + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
                )
            sa = self._line_match_stmt_amount_plain(row)
            if sa:
                act_sa = menu.addAction(
                    "Copy statement amount", partial(self._copy_line_match_stmt_amount, row)
                )
                act_sa.setToolTip(
                    "Copy the statement-side amount (two decimals; **Stmt $** column). "
                    + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
                )
            sdesc = self._line_match_stmt_description_plain(row)
            if sdesc:
                act_sdesc = menu.addAction(
                    "Copy statement description",
                    partial(self._copy_line_match_stmt_description, row),
                )
                act_sdesc.setToolTip(
                    "Copy the statement-side description (**Stmt description** column). "
                    + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
                )
            rd = self._line_match_reg_date_plain(row)
            if rd:
                act_rd = menu.addAction(
                    "Copy register date", partial(self._copy_line_match_reg_date, row)
                )
                act_rd.setToolTip(
                    "Copy the register-side date for this row (**Register date** column). "
                    + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
                )
            ra = self._line_match_reg_amount_plain(row)
            if ra:
                act_ra = menu.addAction(
                    "Copy register amount", partial(self._copy_line_match_reg_amount, row)
                )
                act_ra.setToolTip(
                    "Copy the register-side amount (two decimals; **Register $** column). "
                    + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
                )
            rdesc = self._line_match_reg_description_plain(row)
            if rdesc:
                act_rdesc = menu.addAction(
                    "Copy register description",
                    partial(self._copy_line_match_reg_description, row),
                )
                act_rdesc.setToolTip(
                    "Copy the register-side description (**Register description** column). "
                    + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
                )
            reg_plain = self._line_match_register_id_plain(row)
            if reg_plain:
                act_rid = menu.addAction(
                    "Copy register transaction id",
                    partial(self._copy_line_match_register_id, row),
                )
                act_rid.setToolTip(
                    "Copy the linked bank_transactions id (same as **Reg #** and **Match** overlay on Bank register). "
                    + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
                )
            tid = (
                coerce_combo_int_id(self._rows[row].get("register_id"))
                if 0 <= row < len(self._rows)
                else None
            )
            if tid is not None and self._register_tab is not None:
                nav_ok = business.bank_match_is_navigable(self._db._conn, tid)
                if nav_ok:
                    act_open_biz = menu.addAction(
                        "Open linked Business record…",
                        partial(
                            self._register_tab.open_linked_business_record_for_transaction_id,
                            tid,
                        ),
                    )
                    act_open_biz.setToolTip(
                        "Switch to the Business tab: open the invoice or bill editor, payroll tax lines, "
                        "or a short summary for AR/AP payments."
                    )
        if menu.actions():
            menu.exec(self._table.viewport().mapToGlobal(pos))

    def _on_export_comparison_csv(self) -> None:
        if not self._rows:
            return
        suggest = _suggested_line_compare_csv_filename(self._batch)
        default_path = bank_import_csv_default_save_path(suggest)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save line reconciliation comparison (CSV)",
            default_path,
            "CSV spreadsheets (*.csv);;All files (*.*)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        flags: list[bool] = []
        for r in range(len(self._rows)):
            it = self._table.item(r, _COL_REVIEWED)
            flags.append(
                it is not None and it.checkState() == Qt.CheckState.Checked
            )
        try:
            write_line_match_comparison_csv(path, self._rows, flags)
        except (OSError, ValueError) as exc:
            message_box_critical_ok(
                self,
                "Export failed",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; check path, permissions, disk space, and row alignment.",
            )
            return
        remember_bank_import_csv_export_parent(path)
        message_box_information_ok(
            self,
            "Export complete",
            f"Line comparison saved to:\n{escape_ampersand_for_qt(path)}",
            ok_tip="Close; open the CSV from the path shown." + CSV_EXPORT_OK_TIP_SUFFIX,
        )

    def _on_run_clicked(self) -> None:
        from probooksai.statement_line_match import (
            compare_statement_to_register,
            mock_statement_lines_for_comparison,
        )

        if self._account_id is None or self._batch is None:
            return
        b = self._batch
        acct = coerce_combo_int_id(b.get("bank_account_id"))
        if acct is None:
            return
        txns = self._db.list_transactions(
            acct,
            statement_start=b.get("statement_start"),
            statement_end=b.get("statement_end"),
        )
        reg = [dict(t) for t in txns]
        stmt = mock_statement_lines_for_comparison(reg)
        results = compare_statement_to_register(stmt, reg)
        self.populate(results)
        self.line_match_results_ready.emit(acct, results)

    def _mark_reviewed_selected(self) -> None:
        self._populating = True
        self._table.blockSignals(True)
        for idx in sorted({i.row() for i in self._table.selectedIndexes()}):
            it = self._table.item(idx, _COL_REVIEWED)
            if it is not None:
                it.setCheckState(Qt.CheckState.Checked)
        self._table.blockSignals(False)
        self._populating = False
        self._sync_summary_after_review_edit()

    def _mark_reviewed_all_matched(self) -> None:
        self._populating = True
        self._table.blockSignals(True)
        for r in range(self._table.rowCount()):
            st_it = self._table.item(r, _COL_STATUS)
            if st_it is None or st_it.text() != STATUS_MATCHED:
                continue
            it = self._table.item(r, _COL_REVIEWED)
            if it is not None:
                it.setCheckState(Qt.CheckState.Checked)
        self._table.blockSignals(False)
        self._populating = False
        self._sync_summary_after_review_edit()

    def _clear_reviewed(self) -> None:
        self._populating = True
        self._table.blockSignals(True)
        for r in range(self._table.rowCount()):
            it = self._table.item(r, _COL_REVIEWED)
            if it is not None:
                it.setCheckState(Qt.CheckState.Unchecked)
        self._table.blockSignals(False)
        self._populating = False
        self._sync_summary_after_review_edit()

    def _sync_summary_after_review_edit(self) -> None:
        if not self._rows:
            return
        matched = sum(
            1 for r in self._rows if (r.get("status") or "") == STATUS_MATCHED
        )
        missing = sum(
            1 for r in self._rows if (r.get("status") or "") == STATUS_MISSING
        )
        extra = sum(
            1 for r in self._rows if (r.get("status") or "") == STATUS_EXTRA
        )
        self._refresh_match_summary_footer(matched, missing, extra)

    def reviewed_count(self) -> int:
        n = 0
        for r in range(self._table.rowCount()):
            it = self._table.item(r, _COL_REVIEWED)
            if it is not None and it.checkState() == Qt.CheckState.Checked:
                n += 1
        return n

    def row_status(self, row: int) -> str:
        it = self._table.item(row, _COL_STATUS)
        return (it.text() if it is not None else "") or ""
