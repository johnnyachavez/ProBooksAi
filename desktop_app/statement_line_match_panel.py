"""
AI-assisted statement line reconciliation panel (Bank Import tab).

Shows Matched / Missing / Extra with review checkboxes (UI state only; no DB writes).
**Export comparison CSV** writes the current grid (including reconciled yes/no) via
``probooksai.statement_line_match.write_line_match_comparison_csv``; the save dialog suggests a
basename from the import batch filename (or batch id) and re-opens in the last folder used
(``QSettings`` key ``bank_import/line_compare_csv_export_dir``).
**Right-click** the grid for **Keyboard shortcuts…** (when wired from Bank Import) and **Copy row** (TSV).
"""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtGui import QColor, QBrush
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

from desktop_app.qt_combo_ids import coerce_combo_int_id
from desktop_app.qt_mnemonic import (
    escape_ampersand_for_qt,
    message_box_critical_ok,
    message_box_information_ok,
)
from desktop_app.table_clipboard import (
    CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX,
    copy_table_row_as_tsv,
)
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

_LINE_COMPARE_CSV_EXPORT_DIR_KEY = "bank_import/line_compare_csv_export_dir"


def _line_compare_export_default_path(
    suggested_filename: str,
    *,
    settings: Optional[QSettings] = None,
) -> str:
    """Initial path for **Export comparison CSV** (remembered directory + suggested basename)."""
    s = settings if settings is not None else QSettings()
    raw = (s.value(_LINE_COMPARE_CSV_EXPORT_DIR_KEY, "", type=str) or "").strip()
    if raw:
        parent = Path(raw)
        if parent.is_dir():
            return str(parent / suggested_filename)
    return str(Path.home() / suggested_filename)


def _suggested_line_compare_csv_filename(batch: Optional[dict]) -> str:
    """
    Default ``*.csv`` basename for **Export comparison CSV** (import batch context).

    Uses the batch ``filename`` stem when set (sanitized); otherwise ``line-compare-batch-{id}``.
    """
    if not batch:
        return "line-reconciliation-comparison.csv"
    raw = str(batch.get("filename") or "").strip()
    if raw:
        base = Path(raw.replace("\\", "/")).name
        stem = Path(base).stem.strip() or "import"
        safe = "".join(
            ch if ch.isalnum() or ch in (" ", "-", "_", ".") else "_" for ch in stem
        )
        safe = safe.strip("._- ")[:100] or "import"
        safe = "-".join(part for part in safe.split() if part)
        return f"{safe}-line-compare.csv"
    bid = coerce_combo_int_id(batch.get("id"))
    if bid is not None:
        return f"line-compare-batch-{bid}.csv"
    return "line-reconciliation-comparison.csv"


class StatementLineMatchPanel(QGroupBox):
    """Table + controls for mock statement extract vs register classification."""

    #: Emitted after a successful compare: ``(bank_account_id, results)`` for Register **Stmt match** sync.
    line_match_results_ready = Signal(int, list)

    def __init__(
        self,
        db: BankDatabase,
        parent=None,
        *,
        bank_import_shortcuts_help: Optional[Callable[[], None]] = None,
    ):
        super().__init__("AI-assisted line reconciliation (mock extract)", parent)
        self._db = db
        self._rows: list[dict] = []
        self._populating = False
        self._bank_import_shortcuts_help = bank_import_shortcuts_help
        self.setToolTip(
            "Compare mock ‘statement’ lines to register transactions for the selected batch period. "
            "Matched / Missing / Extra use amount, date ±2 days, and description similarity. "
            "Reconciled checkboxes are UI-only (no register or import changes). "
            "Real PDF OCR is not used yet—this exercises matching + workflow. "
            "Run also updates **Bank register → Stmt match** when that tab is wired (same account), "
            "focuses that tab, and shows a short **status bar** message (company line returns after)."
        )
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        hint = QLabel(
            "Select an import batch, then <b>Run mock extract and compare</b>. "
            "Statement lines are synthesized for now (simulating PDF extract). "
            "On success the main window switches to <b>Bank register</b>, the "
            "<b>status bar</b> shows a short confirmation, then the usual company line returns."
        )
        hint.setTextFormat(Qt.TextFormat.RichText)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #A0A0B0; font-size: 11px;")
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        self._btn_run = QPushButton("Run mock extract & compare")
        self._btn_run.setToolTip(
            "Build mock statement lines from the register (same period as the batch), "
            "classify Matched / Missing / Extra, and fill the table below. "
            "Also syncs **Stmt match** on **Bank register** for this account, switches there, "
            "and shows a brief status message (company line returns afterward)."
        )
        self._btn_run.clicked.connect(self._on_run_clicked)
        btn_row.addWidget(self._btn_run)

        self._btn_mark_sel = QPushButton("Mark reconciled (selected)")
        self._btn_mark_sel.setToolTip(
            "Set the reconciled flag for selected rows (this panel only; does not change register or import data)."
        )
        self._btn_mark_sel.clicked.connect(self._mark_reviewed_selected)
        btn_row.addWidget(self._btn_mark_sel)

        self._btn_mark_matched = QPushButton("Mark reconciled (all Matched)")
        self._btn_mark_matched.setToolTip(
            "Mark all Matched rows reconciled in this panel only (no DB writes)."
        )
        self._btn_mark_matched.clicked.connect(self._mark_reviewed_all_matched)
        btn_row.addWidget(self._btn_mark_matched)

        self._btn_clear = QPushButton("Clear reconciled flags")
        self._btn_clear.setToolTip("Clear reconciled checkboxes in this table (UI only).")
        self._btn_clear.clicked.connect(self._clear_reviewed)
        btn_row.addWidget(self._btn_clear)

        self._btn_export_csv = QPushButton("Export comparison CSV\u2026")
        self._btn_export_csv.setToolTip(
            "Save the current Matched / Missing / Extra rows to a UTF-8 CSV "
            "(amounts as numbers; Reconciled column reflects checkboxes). "
            "The save dialog suggests a name from the import batch filename when available."
        )
        self._btn_export_csv.clicked.connect(self._on_export_comparison_csv)
        btn_row.addWidget(self._btn_export_csv)

        btn_row.addStretch()
        layout.addLayout(btn_row)

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
            "Right-click: Export comparison CSV when the table has rows; Copy row (TSV) on a data row; "
            "Keyboard shortcuts when this panel is embedded in Bank Import."
        )
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_table_context_menu)
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

    def _on_table_context_menu(self, pos) -> None:
        menu = QMenu(self)
        if self._bank_import_shortcuts_help is not None:
            act_keys = menu.addAction(
                "Keyboard shortcuts…", self._bank_import_shortcuts_help
            )
            act_keys.setToolTip(
                "Same summary as Help → Bank import shortcuts… "
                "(F5, batches, register preview, reconciliation). "
                + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
            )
        if self._rows:
            if menu.actions():
                menu.addSeparator()
            act_export = menu.addAction(
                "Export comparison CSV\u2026", self._on_export_comparison_csv
            )
            act_export.setToolTip(
                "Save all rows in this table to a UTF-8 CSV (same as the toolbar button; "
                "suggested filename from the import batch when available). "
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
        if menu.actions():
            menu.exec(self._table.viewport().mapToGlobal(pos))

    def _on_export_comparison_csv(self) -> None:
        if not self._rows:
            return
        suggest = _suggested_line_compare_csv_filename(self._batch)
        default_path = _line_compare_export_default_path(suggest)
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
        QSettings().setValue(
            _LINE_COMPARE_CSV_EXPORT_DIR_KEY,
            str(Path(path).resolve().parent),
        )
        message_box_information_ok(
            self,
            "Export complete",
            f"Line comparison saved to:\n{escape_ampersand_for_qt(path)}",
            ok_tip="Close; open the CSV from the path shown.",
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
