"""Rules, AR/AP, payroll, and tax settings (roadmap phases 6, 8–16)."""

from __future__ import annotations

import csv
import sqlite3
from datetime import date as date_cls

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QFileDialog,
)

from PySide6.QtCore import QDate, QSettings, Qt
from PySide6.QtGui import QGuiApplication, QHideEvent, QKeySequence, QShortcut, QShowEvent

from desktop_app.open_attachment import open_local_attachment
from desktop_app.qt_mnemonic import escape_ampersand_for_qt
from desktop_app.table_clipboard import (
    QTABLE_PLAIN_TEXT_ROLE,
    FloatSortTableItem,
    IntSortTableItem,
    copy_table_row_as_tsv,
    plain_display_table_item,
    table_cell_clipboard_text,
)

_IntSortTableItem = IntSortTableItem
_FloatSortTableItem = FloatSortTableItem
from probooksai import business, business_list_filter, rules_engine


_AGING_BUCKET_ROWS: list[tuple[str, str]] = [
    ("current", "Current"),
    ("1_30", "1–30 days"),
    ("31_60", "31–60 days"),
    ("61_90", "61–90 days"),
    ("91_plus", "91+ days"),
]


def _table_row_entity_id(tbl: QTableWidget, row: int) -> int | None:
    """Read integer id from column 0 (invoice/bill # column), independent of sort order."""
    if row < 0 or row >= tbl.rowCount():
        return None
    it = tbl.item(row, 0)
    if it is None:
        return None
    v = it.data(Qt.ItemDataRole.UserRole)
    if v is not None:
        try:
            return int(v)
        except (TypeError, ValueError):
            pass
    plain = it.data(QTABLE_PLAIN_TEXT_ROLE)
    if isinstance(plain, str) and plain.strip():
        try:
            return int(plain.strip())
        except ValueError:
            pass
    try:
        return int((it.text() or "").strip())
    except ValueError:
        return None


def _rule_id_at_row(tbl: QTableWidget, row: int) -> int | None:
    """Rule primary key from column 0 ``UserRole`` (stable when the rules table is sorted)."""
    if row < 0 or row >= tbl.rowCount():
        return None
    it = tbl.item(row, 0)
    if it is None:
        return None
    v = it.data(Qt.ItemDataRole.UserRole)
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _payroll_run_id_at_row(tbl: QTableWidget, row: int) -> int | None:
    """Pay run id from column 0 ``UserRole`` (stable when the pay run table is sorted)."""
    if row < 0 or row >= tbl.rowCount():
        return None
    it = tbl.item(row, 0)
    if it is None:
        return None
    v = it.data(Qt.ItemDataRole.UserRole)
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _wire_enter_opens_edit(tbl: QTableWidget, edit_handler) -> None:
    """While *tbl* has focus, Return / Enter runs *edit_handler* (same as double-click edit)."""
    for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
        sc = QShortcut(QKeySequence(key), tbl)
        sc.setContext(Qt.ShortcutContext.WidgetShortcut)
        sc.activated.connect(edit_handler)


def _attach_table_copy_row_menu(tbl: QTableWidget, menu_parent: QWidget) -> None:
    """Right-click **Copy row** (TSV) for dialog tables."""
    def _on_ctx(pos):
        idx = tbl.indexAt(pos)
        if not idx.isValid():
            return
        row = idx.row()
        m = QMenu(menu_parent)
        m.addAction("Copy row", lambda r=row: copy_table_row_as_tsv(tbl, r))
        m.exec(tbl.viewport().mapToGlobal(pos))

    tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    tbl.customContextMenuRequested.connect(_on_ctx)


def _wire_find_focuses_line_edit(parent: QWidget, line_edit: QLineEdit) -> None:
    """Standard **Find** shortcut (e.g. Ctrl+F) focuses *line_edit* when *parent* or its children have focus."""
    def _go() -> None:
        line_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        line_edit.selectAll()

    sc = QShortcut(QKeySequence(QKeySequence.StandardKey.Find), parent)
    sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
    sc.activated.connect(_go)


def _append_aging_bucket_totals_csv(
    w: csv.writer, buckets: dict[str, float], as_of: str
) -> None:
    """Append blank line + per-bucket balance sums (matches detail *bucket* keys)."""
    w.writerow([])
    w.writerow(["Bucket totals (open balances)", "", "", "", "", as_of])
    for key, label in _AGING_BUCKET_ROWS:
        tot = float(buckets.get(key, 0) or 0)
        w.writerow([label, "", f"{tot:.2f}", "(bucket total)", "", as_of])


_AR_PAYMENT_BANK_KEY = "business/ar_payment_bank_id"
_AP_PAYMENT_BANK_KEY = "business/ap_payment_bank_id"


def _restore_payment_bank_combo(cb: QComboBox, settings_key: str) -> None:
    """Select last-used bank account id in *cb* (index 0 = none), if still listed."""
    raw = QSettings().value(settings_key, -1)
    try:
        bid = int(raw) if raw is not None and raw != "" else -1
    except (TypeError, ValueError):
        bid = -1
    if bid <= 0:
        return
    for i in range(1, cb.count()):
        data = cb.itemData(i)
        if data is not None and int(data) == bid:
            cb.setCurrentIndex(i)
            break


def _save_payment_bank_choice(cb: QComboBox, settings_key: str) -> None:
    """Persist *cb* bank selection (index 0 or missing data → -1)."""
    idx = cb.currentIndex()
    s = QSettings()
    if idx <= 0:
        s.setValue(settings_key, -1)
        return
    bd = cb.itemData(idx)
    s.setValue(settings_key, int(bd) if bd is not None else -1)


_NEW_INVOICE_CUSTOMER_KEY = "business/new_invoice_customer_id"
_NEW_BILL_VENDOR_KEY = "business/new_bill_vendor_id"
_AR_PAYMENT_CUSTOMER_KEY = "business/ar_payment_customer_id"
_AP_PAYMENT_VENDOR_KEY = "business/ap_payment_vendor_id"
_AR_INVOICE_GRID_FILTER_KEY = "business/ar_invoice_grid_filter"
_AP_BILL_GRID_FILTER_KEY = "business/ap_bill_grid_filter"
_AR_INVOICE_HEADER_STATE_KEY = "business/ar_invoice_table_header_state"
_AP_BILL_HEADER_STATE_KEY = "business/ap_bill_table_header_state"
_RULES_TABLE_HEADER_STATE_KEY = "business/rules_table_header_state"
_PAYROLL_RUNS_HEADER_STATE_KEY = "business/payroll_runs_table_header_state"
_BUSINESS_HUB_SUBTAB_KEY = "business/hub_subtab_index"


def _restore_entity_combo(cb: QComboBox, settings_key: str) -> None:
    """Reselect last-used customer or vendor id in *cb* if still listed."""
    raw = QSettings().value(settings_key, -1)
    try:
        eid = int(raw) if raw is not None and raw != "" else -1
    except (TypeError, ValueError):
        eid = -1
    if eid <= 0:
        return
    for i in range(cb.count()):
        data = cb.itemData(i)
        if data is not None and int(data) == eid:
            cb.setCurrentIndex(i)
            break


def _save_entity_combo(cb: QComboBox, settings_key: str) -> None:
    data = cb.currentData()
    QSettings().setValue(settings_key, int(data) if data is not None else -1)


def _sync_filtered_entity_combo(
    all_rows: list,
    filter_text: str,
    cb: QComboBox,
    keys: tuple[str, ...],
    *,
    tag_1099: bool = False,
    always_include_ids: frozenset | set | None = None,
) -> None:
    """Rebuild *cb* with rows matching *filter_text*; keep prior selection when still listed."""
    rows = business_list_filter.filter_entity_rows(
        all_rows,
        filter_text,
        keys,
        tag_1099_vendors=tag_1099,
        always_include_ids=always_include_ids,
    )
    prev = cb.currentData()
    cb.blockSignals(True)
    cb.clear()
    for r in rows:
        cb.addItem(escape_ampersand_for_qt(r["name"] or ""), int(r["id"]))
    cb.blockSignals(False)
    if cb.count() == 0:
        return
    pick = next((i for i in range(cb.count()) if cb.itemData(i) == prev), 0)
    cb.setCurrentIndex(min(pick, cb.count() - 1))


def _prompt_as_of_date(parent: QWidget, title: str) -> str | None:
    """Show dialog for aging *as-of* date; return ``yyyy-mm-dd`` or ``None`` if cancelled."""
    d = QDialog(parent)
    d.setWindowTitle(title)
    f = QFormLayout(d)
    de = QDateEdit()
    de.setCalendarPopup(True)
    de.setDisplayFormat("yyyy-MM-dd")
    de.setDate(QDate.currentDate())
    f.addRow("As of date", de)
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    f.addRow(bb)
    if d.exec() != QDialog.DialogCode.Accepted:
        return None
    return de.date().toString("yyyy-MM-dd")


def _prompt_list_csv_export_scope(
    parent: QWidget,
    title_plural: str,
    filter_nonempty: bool,
    visible_ids: list[int],
) -> list[int] | str | None:
    """Return ``\"all\"`` for full export, a list of ids for visible-only, or ``None`` if cancelled."""
    if not filter_nonempty:
        return "all"
    box = QMessageBox(parent)
    box.setWindowTitle(f"Export {title_plural} CSV")
    box.setText(
        "The list filter is active. Export only visible rows, or all records?"
    )
    box.setIcon(QMessageBox.Icon.Question)
    btn_vis = box.addButton("Visible only", QMessageBox.ButtonRole.AcceptRole)
    btn_all = box.addButton("All rows", QMessageBox.ButtonRole.ActionRole)
    cancel_btn = box.addButton(QMessageBox.StandardButton.Cancel)
    box.exec()
    clicked = box.clickedButton()
    if clicked is None or clicked == cancel_btn:
        return None
    if clicked == btn_vis:
        return list(visible_ids)
    if clicked == btn_all:
        return "all"
    return None


class RulesTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        lay = QVBoxLayout(self)
        self._tbl = QTableWidget()
        self._tbl.setColumnCount(4)
        self._tbl.setHorizontalHeaderLabels(["Pattern", "COA account", "Priority", "Active"])
        self._tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._tbl.setSortingEnabled(True)
        self._tbl.cellDoubleClicked.connect(self._on_rule_row_double_clicked)
        _wire_enter_opens_edit(self._tbl, self._edit)
        self._tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tbl.customContextMenuRequested.connect(self._on_rules_context_menu)
        lay.addWidget(self._tbl)
        row = QHBoxLayout()
        row.addWidget(QPushButton("Add rule", clicked=self._add))
        row.addWidget(QPushButton("Edit selected", clicked=self._edit))
        row.addWidget(QPushButton("Delete selected", clicked=self._del))
        row.addWidget(QPushButton("Export CSV…", clicked=self._export_csv))
        row.addWidget(QPushButton("Import CSV…", clicked=self._import_csv))
        row.addStretch()
        lay.addLayout(row)
        self._refresh()

    def persist_header_state(self) -> None:
        QSettings().setValue(
            _RULES_TABLE_HEADER_STATE_KEY,
            self._tbl.horizontalHeader().saveState(),
        )

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        raw = QSettings().value(_RULES_TABLE_HEADER_STATE_KEY)
        if raw:
            self._tbl.horizontalHeader().restoreState(raw)

    def hideEvent(self, event: QHideEvent) -> None:
        self.persist_header_state()
        super().hideEvent(event)

    def _refresh(self):
        rows = rules_engine.list_rules(self._conn)
        self._tbl.setSortingEnabled(False)
        self._tbl.setRowCount(len(rows))
        for i, r in enumerate(rows):
            it0 = plain_display_table_item(r["pattern"] or "")
            it0.setData(Qt.ItemDataRole.UserRole, int(r["id"]))
            self._tbl.setItem(i, 0, it0)
            self._tbl.setItem(i, 1, plain_display_table_item(r["coa_account"] or ""))
            pri = int(r["priority"])
            self._tbl.setItem(i, 2, _IntSortTableItem(str(pri), pri))
            self._tbl.setItem(
                i,
                3,
                plain_display_table_item("Yes" if r["is_active"] else "No"),
            )
        self._tbl.setSortingEnabled(True)

    def _on_rule_row_double_clicked(self, row: int, _col: int) -> None:
        if row < 0:
            return
        self._tbl.selectRow(row)
        self._edit()

    def _on_rules_context_menu(self, pos) -> None:
        row = self._tbl.rowAt(pos.y())
        if row < 0 or _rule_id_at_row(self._tbl, row) is None:
            return
        m = QMenu(self)
        m.addAction("Edit…", lambda r=row: (self._tbl.selectRow(r), self._edit()))
        m.addAction("Delete", lambda r=row: (self._tbl.selectRow(r), self._del()))
        m.addAction("Copy row", lambda r=row: copy_table_row_as_tsv(self._tbl, r))
        m.exec(self._tbl.viewport().mapToGlobal(pos))

    def _add(self):
        d = QDialog(self)
        d.setWindowTitle("New rule")
        f = QFormLayout(d)
        pat = QLineEdit()
        coa = QLineEdit()
        pr = QSpinBox()
        pr.setRange(-999, 999)
        pr.setValue(10)
        f.addRow("Description contains", pat)
        f.addRow("COA (e.g. 5010 – Office)", coa)
        f.addRow("Priority (higher first)", pr)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        if not pat.text().strip() or not coa.text().strip():
            return
        rules_engine.add_rule(self._conn, pat.text(), coa.text(), priority=pr.value())
        self._refresh()

    def _edit(self):
        r = self._tbl.currentRow()
        rid = _rule_id_at_row(self._tbl, r)
        if rid is None:
            QMessageBox.information(self, "Rules", "Select a rule to edit.")
            return
        all_rules = rules_engine.list_rules(self._conn)
        cur = next((x for x in all_rules if x["id"] == rid), None)
        if cur is None:
            self._refresh()
            return
        d = QDialog(self)
        d.setWindowTitle("Edit rule")
        f = QFormLayout(d)
        pat = QLineEdit(cur["pattern"])
        coa = QLineEdit(cur["coa_account"])
        pr = QSpinBox()
        pr.setRange(-999, 999)
        pr.setValue(int(cur["priority"]))
        active = QSpinBox()
        active.setRange(0, 1)
        active.setValue(1 if cur["is_active"] else 0)
        f.addRow("Description contains", pat)
        f.addRow("COA (e.g. 5010 – Office)", coa)
        f.addRow("Priority (higher first)", pr)
        f.addRow("Active (1=yes, 0=no)", active)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        if not pat.text().strip() or not coa.text().strip():
            return
        rules_engine.update_rule(
            self._conn,
            rid,
            pat.text(),
            coa.text(),
            pr.value(),
            bool(active.value()),
        )
        self._refresh()

    def _del(self):
        r = self._tbl.currentRow()
        rid = _rule_id_at_row(self._tbl, r)
        if rid is None:
            return
        pat_preview = table_cell_clipboard_text(self._tbl, r, 0).strip() or f"id {rid}"
        confirm = QMessageBox.question(
            self,
            "Delete rule",
            "Delete this categorization rule?\n\nPattern: "
            f"{escape_ampersand_for_qt(pat_preview)}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        rules_engine.delete_rule(self._conn, rid)
        self._refresh()

    def _export_csv(self):
        rows = rules_engine.list_rules(self._conn)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export categorization rules",
            "categorization_rules.csv",
            "CSV (*.csv);;All Files (*.*)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            n = rules_engine.write_rules_csv(path, list(rows))
        except OSError as exc:
            QMessageBox.critical(
                self, "Export failed", escape_ampersand_for_qt(str(exc))
            )
            return
        QMessageBox.information(
            self,
            "Export complete",
            f"Exported {n} rule(s) to:\n{escape_ampersand_for_qt(path)}",
        )

    def _import_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import categorization rules",
            "",
            "CSV (*.csv);;All Files (*.*)",
        )
        if not path:
            return
        confirm = QMessageBox.question(
            self,
            "Replace all rules?",
            "Import will delete all existing categorization rules and replace them "
            "with the rows in this file.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            n = rules_engine.import_rules_replace(self._conn, path)
        except ValueError as exc:
            QMessageBox.warning(
                self, "Import rules", escape_ampersand_for_qt(str(exc))
            )
            return
        except OSError as exc:
            QMessageBox.critical(
                self, "Import failed", escape_ampersand_for_qt(str(exc))
            )
            return
        except Exception as exc:
            QMessageBox.critical(
                self, "Import failed", escape_ampersand_for_qt(str(exc))
            )
            return
        self._refresh()
        QMessageBox.information(
            self,
            "Import complete",
            f"Imported {n} rule(s) from:\n{escape_ampersand_for_qt(path)}",
        )


class ARTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QPushButton("New customer", clicked=self._new_cust))
        row.addWidget(QPushButton("Edit customer…", clicked=self._edit_cust))
        row.addWidget(QPushButton("New invoice", clicked=self._new_inv))
        row.addWidget(QPushButton("Edit selected invoice…", clicked=self._edit_inv))
        row.addWidget(QPushButton("Record customer payment…", clicked=self._record_ar_payment))
        row.addWidget(QPushButton("Export AR aging CSV", clicked=self._export_aging))
        row.addWidget(QPushButton("Export customers CSV…", clicked=self._export_customers))
        row.addWidget(QPushButton("Export invoices CSV…", clicked=self._export_invoices))
        row.addWidget(QPushButton("Export AR payments CSV…", clicked=self._export_ar_payments))
        row.addWidget(
            QPushButton("Export AR payment allocations CSV…", clicked=self._export_ar_allocations)
        )
        row.addWidget(QPushButton("Save invoice PDF…", clicked=self._save_pdf))
        row.addStretch()
        lay.addLayout(row)
        fil = QHBoxLayout()
        fil.addWidget(QLabel("Filter:"))
        self._inv_filter = QLineEdit()
        _saved_ar_filt = QSettings().value(_AR_INVOICE_GRID_FILTER_KEY, "")
        if isinstance(_saved_ar_filt, str) and _saved_ar_filt:
            self._inv_filter.setText(_saved_ar_filt)
        self._inv_filter.setPlaceholderText(
            "Customer, invoice #, memo, dates, status, subtotal, tax, totals, id (words must all match)…"
        )
        self._inv_filter.setClearButtonEnabled(True)
        self._inv_filter.textChanged.connect(self._persist_ar_invoice_filter_and_refresh)
        fil.addWidget(self._inv_filter)
        lay.addLayout(fil)
        _wire_find_focuses_line_edit(self, self._inv_filter)
        self._tbl = QTableWidget()
        self._tbl.setColumnCount(8)
        self._tbl.setHorizontalHeaderLabels(
            ["#", "Customer", "Invoice #", "Date", "Due", "Total", "Balance", "Status"]
        )
        self._tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._tbl.setSortingEnabled(True)
        self._tbl.cellDoubleClicked.connect(self._on_invoice_row_double_clicked)
        _wire_enter_opens_edit(self._tbl, self._edit_inv)
        self._tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tbl.customContextMenuRequested.connect(self._on_invoice_context_menu)
        lay.addWidget(self._tbl)
        self._ar_footer = QLabel()
        self._ar_footer.setStyleSheet("font-weight: bold;")
        lay.addWidget(self._ar_footer)
        self._refresh()

    def persist_header_state(self) -> None:
        QSettings().setValue(
            _AR_INVOICE_HEADER_STATE_KEY,
            self._tbl.horizontalHeader().saveState(),
        )

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        raw = QSettings().value(_AR_INVOICE_HEADER_STATE_KEY)
        if raw:
            self._tbl.horizontalHeader().restoreState(raw)

    def hideEvent(self, event: QHideEvent) -> None:
        self.persist_header_state()
        super().hideEvent(event)

    def _persist_ar_invoice_filter_and_refresh(self) -> None:
        QSettings().setValue(_AR_INVOICE_GRID_FILTER_KEY, self._inv_filter.text())
        self._refresh()

    def _refresh(self):
        all_rows = business.list_invoices(self._conn)
        rows = business_list_filter.filter_business_rows(
            all_rows, self._inv_filter.text(), business_list_filter.AR_INVOICE_FILTER_KEYS
        )
        self._tbl.setSortingEnabled(False)
        self._tbl.setRowCount(len(rows))
        for i, r in enumerate(rows):
            rid = int(r["id"])
            id_it = _IntSortTableItem(str(rid), rid)
            id_it.setData(Qt.ItemDataRole.UserRole, rid)
            self._tbl.setItem(i, 0, id_it)
            self._tbl.setItem(i, 1, plain_display_table_item(r["customer_name"] or ""))
            self._tbl.setItem(i, 2, plain_display_table_item(r["invoice_number"] or ""))
            self._tbl.setItem(i, 3, plain_display_table_item(r["invoice_date"] or ""))
            self._tbl.setItem(i, 4, plain_display_table_item(r["due_date"] or ""))
            tot = float(r["total"] or 0)
            bal = float(r["balance_due"] or 0)
            self._tbl.setItem(i, 5, _FloatSortTableItem(f"{tot:.2f}", tot))
            self._tbl.setItem(i, 6, _FloatSortTableItem(f"{bal:.2f}", bal))
            self._tbl.setItem(i, 7, plain_display_table_item(r["status"] or ""))
        self._tbl.setSortingEnabled(True)
        n = len(rows)
        sum_total = sum(float(r["total"] or 0) for r in rows)
        sum_bal = sum(float(r["balance_due"] or 0) for r in rows)
        filt = len(all_rows) - n
        extra = f" ({filt} hidden by filter)" if filt else ""
        self._ar_footer.setText(
            f"{n} invoice(s){extra} · Invoice total: {sum_total:,.2f} · Balance due: {sum_bal:,.2f}"
        )

    def _on_invoice_row_double_clicked(self, row: int, _col: int) -> None:
        if row < 0:
            return
        self._tbl.selectRow(row)
        self._edit_inv()

    def _on_invoice_context_menu(self, pos) -> None:
        row = self._tbl.rowAt(pos.y())
        if row < 0 or _table_row_entity_id(self._tbl, row) is None:
            return
        m = QMenu(self)
        m.addAction("Edit…", lambda r=row: (self._tbl.selectRow(r), self._edit_inv()))
        m.addAction(
            "Save invoice PDF…", lambda r=row: (self._tbl.selectRow(r), self._save_pdf())
        )
        m.addAction(
            "Copy invoice #",
            lambda r=row: QGuiApplication.clipboard().setText(
                table_cell_clipboard_text(self._tbl, r, 2).strip()
            ),
        )
        m.addAction("Copy row", lambda r=row: copy_table_row_as_tsv(self._tbl, r))
        m.exec(self._tbl.viewport().mapToGlobal(pos))

    def _save_pdf(self):
        r = self._tbl.currentRow()
        inv_id = _table_row_entity_id(self._tbl, r)
        if inv_id is None:
            QMessageBox.information(self, "PDF", "Select an invoice row.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Invoice PDF", "", "PDF (*.pdf)")
        if not path:
            return
        try:
            from desktop_app.invoice_pdf import save_invoice_pdf

            save_invoice_pdf(self._conn, inv_id, path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "PDF", escape_ampersand_for_qt(str(exc)))
            return
        QMessageBox.information(
            self, "PDF", f"Saved to {escape_ampersand_for_qt(path)}"
        )

    def _new_cust(self):
        d = QDialog(self)
        d.setWindowTitle("New customer")
        f = QFormLayout(d)
        ne = QLineEdit()
        em = QLineEdit()
        ph = QLineEdit()
        ad = QPlainTextEdit()
        ad.setFixedHeight(56)
        no = QPlainTextEdit()
        no.setFixedHeight(48)
        f.addRow("Name *", ne)
        f.addRow("Email", em)
        f.addRow("Phone", ph)
        f.addRow("Address", ad)
        f.addRow("Notes", no)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.DialogCode.Accepted or not ne.text().strip():
            return
        business.add_customer(
            self._conn,
            ne.text().strip(),
            email=em.text().strip(),
            phone=ph.text().strip(),
            address=ad.toPlainText().strip(),
            notes=no.toPlainText().strip(),
        )
        QMessageBox.information(self, "Done", "Customer added.")
        self._refresh()

    def _edit_cust(self):
        custs = business.list_customers(self._conn)
        if not custs:
            QMessageBox.information(self, "Customers", "No customers to edit.")
            return
        d = QDialog(self)
        d.setWindowTitle("Edit customer")
        f = QFormLayout(d)
        filt = QLineEdit()
        filt.setPlaceholderText("Filter by name, email, phone, address, notes, or id…")
        filt.setClearButtonEnabled(True)
        cb = QComboBox()
        ne = QLineEdit()
        em = QLineEdit()
        ph = QLineEdit()
        ad = QPlainTextEdit()
        ad.setFixedHeight(56)
        no = QPlainTextEdit()
        no.setFixedHeight(48)

        def load_customer(_index: int | None = None) -> None:
            cid = cb.currentData()
            if cid is None:
                return
            row = business.get_customer(self._conn, int(cid))
            if row is None:
                return
            ne.setText(row["name"] or "")
            em.setText(row["email"] or "")
            ph.setText(row["phone"] or "")
            ad.setPlainText(row["address"] or "")
            no.setPlainText(row["notes"] or "")

        def sync_customer_combo() -> None:
            _sync_filtered_entity_combo(
                custs, filt.text(), cb, business_list_filter.CUSTOMER_ENTITY_KEYS
            )
            load_customer()

        cb.currentIndexChanged.connect(load_customer)
        filt.textChanged.connect(sync_customer_combo)
        f.addRow("Filter list", filt)
        f.addRow("Customer", cb)
        sync_customer_combo()
        f.addRow("Name *", ne)
        f.addRow("Email", em)
        f.addRow("Phone", ph)
        f.addRow("Address", ad)
        f.addRow("Notes", no)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        if not ne.text().strip():
            return
        cid = cb.currentData()
        if cid is None:
            QMessageBox.warning(self, "Customer", "No customer selected (try clearing the filter).")
            return
        try:
            business.update_customer(
                self._conn,
                int(cid),
                ne.text().strip(),
                email=em.text().strip(),
                phone=ph.text().strip(),
                address=ad.toPlainText().strip(),
                notes=no.toPlainText().strip(),
            )
        except ValueError as exc:
            QMessageBox.warning(
                self, "Customer", escape_ampersand_for_qt(str(exc))
            )
            return
        self._refresh()

    def _new_inv(self):
        custs = business.list_customers(self._conn)
        if not custs:
            QMessageBox.information(self, "Customers", "Add a customer first.")
            return
        d = QDialog(self)
        d.setWindowTitle("Invoice")
        f = QFormLayout(d)
        cust_filt = QLineEdit()
        cust_filt.setPlaceholderText("Filter customers by name, email, phone…")
        cust_filt.setClearButtonEnabled(True)
        cb = QComboBox()

        def sync_new_inv_customers() -> None:
            _sync_filtered_entity_combo(
                custs, cust_filt.text(), cb, business_list_filter.CUSTOMER_ENTITY_KEYS
            )

        cust_filt.textChanged.connect(sync_new_inv_customers)
        f.addRow("Filter list", cust_filt)
        f.addRow("Customer", cb)
        sync_new_inv_customers()
        _restore_entity_combo(cb, _NEW_INVOICE_CUSTOMER_KEY)
        invno = QLineEdit()
        idate = QDateEdit()
        idate.setCalendarPopup(True)
        idate.setDisplayFormat("yyyy-MM-dd")
        idate.setDate(QDate.currentDate())
        due_e = QLineEdit()
        memo_e = QLineEdit()
        rate = QDoubleSpinBox()
        rate.setRange(0, 9_999_999)
        rate.setDecimals(2)
        tax = QDoubleSpinBox()
        tax.setRange(0, 100)
        tax.setDecimals(2)
        tax.setValue(float(business.get_setting(self._conn, "default_tax_rate_pct", "0") or 0))
        f.addRow("Invoice # *", invno)
        f.addRow("Date", idate)
        f.addRow("Due date (optional)", due_e)
        f.addRow("Memo", memo_e)
        f.addRow("Line amount", rate)
        f.addRow("Tax %", tax)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        if not invno.text().strip():
            return
        cust_id = cb.currentData()
        if cust_id is None:
            QMessageBox.warning(self, "Invoice", "Select a customer (try clearing the filter).")
            return
        try:
            business.create_invoice(
                self._conn,
                int(cust_id),
                invno.text().strip(),
                idate.date().toString("yyyy-MM-dd"),
                due_date=due_e.text().strip(),
                memo=memo_e.text().strip(),
                lines=[{"description": "Services", "qty": 1, "rate": rate.value()}],
                tax_rate_pct=tax.value(),
            )
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Duplicate", "Invoice number already exists.")
            return
        _save_entity_combo(cb, _NEW_INVOICE_CUSTOMER_KEY)
        self._refresh()

    def _edit_inv(self):
        r = self._tbl.currentRow()
        inv_id = _table_row_entity_id(self._tbl, r)
        if inv_id is None:
            QMessageBox.information(self, "Invoice", "Select an invoice row.")
            return
        if business.invoice_has_payment_allocations(self._conn, inv_id):
            QMessageBox.information(
                self,
                "Invoice",
                "This invoice has payments applied and cannot be edited.",
            )
            return
        inv, line_rows = business.get_invoice_detail(self._conn, inv_id)
        if inv is None:
            self._refresh()
            return
        custs = business.list_customers(self._conn)
        if not custs:
            return
        d = QDialog(self)
        d.setWindowTitle("Edit invoice")
        outer = QVBoxLayout(d)
        f = QFormLayout()
        inv_cust_id = int(inv["customer_id"])
        ensure_cust = frozenset({inv_cust_id})
        cust_filt = QLineEdit()
        cust_filt.setPlaceholderText("Filter customers (current invoice customer always listed)…")
        cust_filt.setClearButtonEnabled(True)
        cb = QComboBox()

        def sync_edit_inv_customers() -> None:
            _sync_filtered_entity_combo(
                custs,
                cust_filt.text(),
                cb,
                business_list_filter.CUSTOMER_ENTITY_KEYS,
                always_include_ids=ensure_cust,
            )

        cust_filt.textChanged.connect(sync_edit_inv_customers)
        f.addRow("Filter list", cust_filt)
        f.addRow("Customer", cb)
        sync_edit_inv_customers()
        idx = next(
            (i for i in range(cb.count()) if cb.itemData(i) == inv_cust_id),
            0,
        )
        cb.setCurrentIndex(idx)
        invno = QLineEdit(inv["invoice_number"] or "")
        idate = QDateEdit()
        idate.setCalendarPopup(True)
        idate.setDisplayFormat("yyyy-MM-dd")
        qd = QDate.fromString(inv["invoice_date"] or "", "yyyy-MM-dd")
        idate.setDate(qd if qd.isValid() else QDate.currentDate())
        due_e = QLineEdit(inv["due_date"] or "")
        memo_e = QLineEdit(inv["memo"] or "")
        sub = float(inv["subtotal"] or 0)
        tax_amt = float(inv["tax_total"] or 0)
        tax_pct = (100.0 * tax_amt / sub) if sub > 0 else 0.0
        tax = QDoubleSpinBox()
        tax.setRange(0, 100)
        tax.setDecimals(4)
        tax.setValue(tax_pct)
        f.addRow("Customer", cb)
        f.addRow("Invoice # *", invno)
        f.addRow("Date", idate)
        f.addRow("Due date (optional)", due_e)
        f.addRow("Memo", memo_e)
        f.addRow("Tax %", tax)
        outer.addLayout(f)
        outer.addWidget(QLabel("Line items (description, qty, rate)"))
        line_tbl = QTableWidget()
        line_tbl.setColumnCount(3)
        line_tbl.setHorizontalHeaderLabels(["Description", "Qty", "Rate"])
        line_tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        rate_align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter

        def _edit_inv_rate_item(rate: float) -> QTableWidgetItem:
            x = float(rate)
            disp = f"{x:,.2f}"
            it = _FloatSortTableItem(disp, x)
            it.setTextAlignment(rate_align)
            return it

        nlines = max(1, len(line_rows))
        line_tbl.setRowCount(nlines)
        for i, ln in enumerate(line_rows):
            line_tbl.setItem(
                i, 0, plain_display_table_item(str(ln["description"] or ""))
            )
            line_tbl.setItem(i, 1, plain_display_table_item(str(ln["qty"])))
            line_tbl.setItem(i, 2, _edit_inv_rate_item(float(ln["rate"])))
        if not line_rows:
            line_tbl.setItem(0, 0, plain_display_table_item("Services"))
            line_tbl.setItem(0, 1, plain_display_table_item("1"))
            line_tbl.setItem(0, 2, _edit_inv_rate_item(0.0))
        _attach_table_copy_row_menu(line_tbl, d)
        outer.addWidget(line_tbl)
        btn_row = QHBoxLayout()

        def add_line():
            line_tbl.insertRow(line_tbl.rowCount())
            r = line_tbl.rowCount() - 1
            line_tbl.setItem(r, 0, plain_display_table_item(""))
            line_tbl.setItem(r, 1, plain_display_table_item(""))
            line_tbl.setItem(r, 2, _edit_inv_rate_item(0.0))

        def del_line():
            if line_tbl.rowCount() <= 1:
                return
            line_tbl.removeRow(line_tbl.currentRow() if line_tbl.currentRow() >= 0 else line_tbl.rowCount() - 1)

        btn_row.addWidget(QPushButton("Add line", clicked=add_line))
        btn_row.addWidget(QPushButton("Remove line", clicked=del_line))
        btn_row.addStretch()
        outer.addLayout(btn_row)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        outer.addWidget(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        if not invno.text().strip():
            return
        lines_out: list[dict] = []
        for row_i in range(line_tbl.rowCount()):
            desc = table_cell_clipboard_text(line_tbl, row_i, 0).strip()
            qtxt = table_cell_clipboard_text(line_tbl, row_i, 1).strip() or "1"
            rtx = table_cell_clipboard_text(line_tbl, row_i, 2).strip() or "0"
            try:
                qv = float(qtxt)
                rv = float(rtx.replace(",", ""))
            except ValueError:
                QMessageBox.warning(self, "Invoice", "Invalid qty or rate on a line.")
                return
            if not desc and qv == 0 and rv == 0:
                continue
            lines_out.append({"description": desc or "Line", "qty": qv, "rate": rv})
        if not lines_out:
            QMessageBox.warning(self, "Invoice", "Add at least one line with an amount.")
            return
        new_cust = cb.currentData()
        if new_cust is None:
            QMessageBox.warning(self, "Invoice", "Select a customer (try clearing the filter).")
            return
        try:
            business.update_invoice(
                self._conn,
                inv_id,
                int(new_cust),
                invno.text().strip(),
                idate.date().toString("yyyy-MM-dd"),
                due_date=due_e.text().strip(),
                memo=memo_e.text().strip(),
                lines=lines_out,
                tax_rate_pct=tax.value(),
            )
        except ValueError as exc:
            QMessageBox.warning(
                self, "Invoice", escape_ampersand_for_qt(str(exc))
            )
            return
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Duplicate", "Invoice number already exists.")
            return
        self._refresh()

    def _record_ar_payment(self):
        custs = business.list_customers(self._conn)
        if not custs:
            QMessageBox.information(self, "AR payment", "Add a customer first.")
            return
        d = QDialog(self)
        d.setWindowTitle("Record customer payment")
        d.setMinimumWidth(540)
        outer = QVBoxLayout(d)
        form = QFormLayout()
        cust_filt = QLineEdit()
        cust_filt.setPlaceholderText("Filter customers by name, email, phone…")
        cust_filt.setClearButtonEnabled(True)
        cust_cb = QComboBox()
        form.addRow("Filter list", cust_filt)
        form.addRow("Customer", cust_cb)
        pdate = QDateEdit()
        pdate.setCalendarPopup(True)
        pdate.setDisplayFormat("yyyy-MM-dd")
        pdate.setDate(QDate.currentDate())
        pay_amt = QDoubleSpinBox()
        pay_amt.setRange(0.01, 99_999_999.99)
        pay_amt.setDecimals(2)
        method_e = QLineEdit()
        ref_e = QLineEdit()
        memo_e = QLineEdit()
        bank_cb = QComboBox()
        bank_cb.addItem("(None)")
        try:
            banks = self._conn.execute(
                "SELECT id, name FROM bank_accounts WHERE is_active = 1 ORDER BY name"
            ).fetchall()
        except sqlite3.OperationalError:
            banks = []
        for b in banks:
            bank_cb.addItem(
                escape_ampersand_for_qt(b["name"] or ""), int(b["id"])
            )
        _restore_payment_bank_combo(bank_cb, _AR_PAYMENT_BANK_KEY)
        form.addRow("Payment date", pdate)
        form.addRow("Amount *", pay_amt)
        form.addRow("Deposit to bank", bank_cb)
        form.addRow("Method", method_e)
        form.addRow("Reference #", ref_e)
        form.addRow("Memo", memo_e)
        outer.addLayout(form)
        outer.addWidget(QLabel("Apply to open invoices:"))
        hint = QLabel('Sum of "Apply" must equal the payment amount.')
        hint.setStyleSheet("color: palette(mid);")
        outer.addWidget(hint)
        alloc_tbl = QTableWidget()
        alloc_tbl.setColumnCount(4)
        alloc_tbl.setHorizontalHeaderLabels(["Invoice #", "Date", "Balance", "Apply"])
        alloc_tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        def rebuild_ar_alloc_table(_idx: int | None = None) -> None:
            cid = cust_cb.currentData()
            alloc_tbl.setSortingEnabled(False)
            alloc_tbl.setRowCount(0)
            if cid is None:
                alloc_tbl.setSortingEnabled(True)
                return
            opens = business.list_open_invoices_for_customer(self._conn, int(cid))
            alloc_tbl.setRowCount(len(opens))
            align_rc = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            for i, r in enumerate(opens):
                it0 = plain_display_table_item(r["invoice_number"] or "")
                it0.setData(Qt.ItemDataRole.UserRole, int(r["id"]))
                alloc_tbl.setItem(i, 0, it0)
                alloc_tbl.setItem(
                    i, 1, plain_display_table_item(r["invoice_date"] or "")
                )
                bal = float(r["balance_due"])
                bal_it = _FloatSortTableItem(f"{bal:,.2f}", bal)
                bal_it.setTextAlignment(align_rc)
                alloc_tbl.setItem(i, 2, bal_it)
                sp = QDoubleSpinBox()
                sp.setRange(0, float(r["balance_due"]))
                sp.setDecimals(2)
                alloc_tbl.setCellWidget(i, 3, sp)
            alloc_tbl.setSortingEnabled(True)

        def sync_ar_payment_customers() -> None:
            _sync_filtered_entity_combo(
                custs, cust_filt.text(), cust_cb, business_list_filter.CUSTOMER_ENTITY_KEYS
            )
            rebuild_ar_alloc_table()

        def apply_oldest_first() -> None:
            remaining = round(pay_amt.value(), 2)
            for row in range(alloc_tbl.rowCount()):
                w = alloc_tbl.cellWidget(row, 3)
                if not isinstance(w, QDoubleSpinBox):
                    continue
                cap = round(float(w.maximum()), 2)
                use = min(remaining, cap)
                w.setValue(use)
                remaining = round(remaining - use, 2)
                if remaining <= 0.001:
                    break

        cust_filt.textChanged.connect(sync_ar_payment_customers)
        cust_cb.currentIndexChanged.connect(rebuild_ar_alloc_table)
        sync_ar_payment_customers()
        _restore_entity_combo(cust_cb, _AR_PAYMENT_CUSTOMER_KEY)
        auto_row = QHBoxLayout()
        auto_row.addWidget(QPushButton("Fill oldest first", clicked=apply_oldest_first))
        auto_row.addStretch()
        outer.addLayout(auto_row)
        _attach_table_copy_row_menu(alloc_tbl, d)
        outer.addWidget(alloc_tbl)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        outer.addWidget(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        cid = cust_cb.currentData()
        if cid is None:
            QMessageBox.warning(
                self,
                "AR payment",
                "Select a customer (try clearing the filter).",
            )
            return
        amt = round(pay_amt.value(), 2)
        allocs: list[tuple[int, float]] = []
        for row in range(alloc_tbl.rowCount()):
            it = alloc_tbl.item(row, 0)
            w = alloc_tbl.cellWidget(row, 3)
            if it is None or not isinstance(w, QDoubleSpinBox):
                continue
            v = round(w.value(), 2)
            if v <= 0.005:
                continue
            iid = int(it.data(Qt.ItemDataRole.UserRole))
            allocs.append((iid, v))
        if not allocs:
            QMessageBox.warning(
                self,
                "AR payment",
                "Enter an amount in Apply for at least one invoice.",
            )
            return
        applied = round(sum(a for _, a in allocs), 2)
        if abs(applied - amt) > 0.02:
            QMessageBox.warning(
                self,
                "AR payment",
                f"Apply amounts ({applied:.2f}) must equal payment amount ({amt:.2f}).",
            )
            return
        bidx = bank_cb.currentIndex()
        bank_account_id = None
        if bidx > 0:
            bd = bank_cb.itemData(bidx)
            if bd is not None:
                bank_account_id = int(bd)
        business.record_ar_payment(
            self._conn,
            int(cid),
            pdate.date().toString("yyyy-MM-dd"),
            amt,
            allocs,
            bank_account_id=bank_account_id,
            method=method_e.text().strip(),
            reference=ref_e.text().strip(),
            memo=memo_e.text().strip(),
        )
        _save_entity_combo(cust_cb, _AR_PAYMENT_CUSTOMER_KEY)
        _save_payment_bank_choice(bank_cb, _AR_PAYMENT_BANK_KEY)
        self._refresh()
        QMessageBox.information(self, "AR payment", "Payment recorded.")

    def _export_aging(self):
        as_of = _prompt_as_of_date(self, "Export AR aging")
        if as_of is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "AR aging", "", "CSV (*.csv)")
        if not path:
            return
        data = business.ar_aging_buckets(self._conn, as_of)[0]
        with open(path, "w", newline="", encoding="utf-8") as fp:
            w = csv.writer(fp)
            w.writerow(
                ["Customer", "Invoice id", "Balance", "Bucket", "Days past due", "As of"]
            )
            for ln in data["lines"]:
                w.writerow(
                    [
                        ln["customer"],
                        ln["invoice_id"],
                        f"{ln['balance']:.2f}",
                        ln["bucket"],
                        ln.get("days_past_due", ""),
                        as_of,
                    ]
                )
            _append_aging_bucket_totals_csv(w, data["buckets"], as_of)
        QMessageBox.information(
            self,
            "Export",
            f"Wrote {escape_ampersand_for_qt(path)}\n(As of {as_of})",
        )

    def _export_customers(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export customers", "customers.csv", "CSV (*.csv)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            n = business.write_customers_csv(self._conn, path)
        except OSError as exc:
            QMessageBox.critical(
                self, "Export failed", escape_ampersand_for_qt(str(exc))
            )
            return
        QMessageBox.information(
            self,
            "Export",
            f"Exported {n} customer(s) to {escape_ampersand_for_qt(path)}",
        )

    def _export_invoices(self):
        filt = self._inv_filter.text().strip()
        all_rows = business.list_invoices(self._conn)
        filtered = business_list_filter.filter_business_rows(
            all_rows, filt, business_list_filter.AR_INVOICE_FILTER_KEYS
        )
        vis_ids = [int(r["id"]) for r in filtered]
        scope = _prompt_list_csv_export_scope(self, "invoices", bool(filt), vis_ids)
        if scope is None:
            return
        invoice_ids = None if scope == "all" else scope
        path, _ = QFileDialog.getSaveFileName(
            self, "Export invoices", "invoices.csv", "CSV (*.csv)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            n = business.write_invoices_csv(
                self._conn, path, invoice_ids=invoice_ids
            )
        except OSError as exc:
            QMessageBox.critical(
                self, "Export failed", escape_ampersand_for_qt(str(exc))
            )
            return
        QMessageBox.information(
            self,
            "Export",
            f"Exported {n} invoice(s) to {escape_ampersand_for_qt(path)}",
        )

    def _export_ar_payments(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export AR payments", "ar_payments.csv", "CSV (*.csv)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            n = business.write_ar_payments_csv(self._conn, path)
        except OSError as exc:
            QMessageBox.critical(
                self, "Export failed", escape_ampersand_for_qt(str(exc))
            )
            return
        except sqlite3.OperationalError as exc:
            QMessageBox.critical(
                self,
                "Export failed",
                escape_ampersand_for_qt(
                    str(exc)
                    + "\n\nRestart the app to apply the latest database upgrade."
                ),
            )
            return
        QMessageBox.information(
            self,
            "Export",
            f"Exported {n} payment(s) to {escape_ampersand_for_qt(path)}",
        )

    def _export_ar_allocations(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export AR payment allocations",
            "ar_payment_allocations.csv",
            "CSV (*.csv)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            n = business.write_ar_payment_allocations_csv(self._conn, path)
        except OSError as exc:
            QMessageBox.critical(
                self, "Export failed", escape_ampersand_for_qt(str(exc))
            )
            return
        QMessageBox.information(
            self,
            "Export",
            f"Exported {n} allocation row(s) to {escape_ampersand_for_qt(path)}",
        )


class APTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QPushButton("New vendor", clicked=self._new_v))
        row.addWidget(QPushButton("Edit vendor…", clicked=self._edit_v))
        row.addWidget(QPushButton("New bill", clicked=self._new_b))
        row.addWidget(QPushButton("Edit selected bill…", clicked=self._edit_b))
        row.addWidget(QPushButton("Record vendor payment…", clicked=self._record_ap_payment))
        row.addWidget(QPushButton("Export AP aging CSV", clicked=self._export_aging))
        row.addWidget(QPushButton("Export vendors CSV…", clicked=self._export_vendors))
        row.addWidget(QPushButton("Export bills CSV…", clicked=self._export_bills))
        row.addWidget(QPushButton("Export AP payments CSV…", clicked=self._export_ap_payments))
        row.addWidget(
            QPushButton("Export AP payment allocations CSV…", clicked=self._export_ap_allocations)
        )
        row.addStretch()
        lay.addLayout(row)
        fil = QHBoxLayout()
        fil.addWidget(QLabel("Filter:"))
        self._bill_filter = QLineEdit()
        _saved_ap_filt = QSettings().value(_AP_BILL_GRID_FILTER_KEY, "")
        if isinstance(_saved_ap_filt, str) and _saved_ap_filt:
            self._bill_filter.setText(_saved_ap_filt)
        self._bill_filter.setPlaceholderText(
            "Vendor, vendor inv. #, memo, attachment path/filename, dates, status, id, amounts…"
        )
        self._bill_filter.setClearButtonEnabled(True)
        self._bill_filter.textChanged.connect(self._persist_ap_bill_filter_and_refresh)
        fil.addWidget(self._bill_filter)
        lay.addLayout(fil)
        _wire_find_focuses_line_edit(self, self._bill_filter)
        self._tbl = QTableWidget()
        self._tbl.setColumnCount(7)
        self._tbl.setHorizontalHeaderLabels(
            ["#", "Vendor", "Bill date", "Due", "Total", "Balance", "Status"]
        )
        self._tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._tbl.setSortingEnabled(True)
        self._tbl.cellDoubleClicked.connect(self._on_bill_row_double_clicked)
        _wire_enter_opens_edit(self._tbl, self._edit_b)
        self._tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tbl.customContextMenuRequested.connect(self._on_bill_context_menu)
        lay.addWidget(self._tbl)
        self._ap_footer = QLabel()
        self._ap_footer.setStyleSheet("font-weight: bold;")
        lay.addWidget(self._ap_footer)
        self._refresh()

    def persist_header_state(self) -> None:
        QSettings().setValue(
            _AP_BILL_HEADER_STATE_KEY,
            self._tbl.horizontalHeader().saveState(),
        )

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        raw = QSettings().value(_AP_BILL_HEADER_STATE_KEY)
        if raw:
            self._tbl.horizontalHeader().restoreState(raw)

    def hideEvent(self, event: QHideEvent) -> None:
        self.persist_header_state()
        super().hideEvent(event)

    def _persist_ap_bill_filter_and_refresh(self) -> None:
        QSettings().setValue(_AP_BILL_GRID_FILTER_KEY, self._bill_filter.text())
        self._refresh()

    def _refresh(self):
        all_rows = business.list_bills(self._conn)
        rows = business_list_filter.filter_business_rows(
            all_rows, self._bill_filter.text(), business_list_filter.AP_BILL_FILTER_KEYS
        )
        self._tbl.setSortingEnabled(False)
        self._tbl.setRowCount(len(rows))
        for i, r in enumerate(rows):
            bid = int(r["id"])
            id_it = _IntSortTableItem(str(bid), bid)
            id_it.setData(Qt.ItemDataRole.UserRole, bid)
            self._tbl.setItem(i, 0, id_it)
            self._tbl.setItem(i, 1, plain_display_table_item(r["vendor_name"] or ""))
            self._tbl.setItem(i, 2, plain_display_table_item(r["bill_date"] or ""))
            self._tbl.setItem(i, 3, plain_display_table_item(r["due_date"] or ""))
            tot = float(r["total"] or 0)
            bal = float(r["balance_due"] or 0)
            self._tbl.setItem(i, 4, _FloatSortTableItem(f"{tot:.2f}", tot))
            self._tbl.setItem(i, 5, _FloatSortTableItem(f"{bal:.2f}", bal))
            self._tbl.setItem(i, 6, plain_display_table_item(r["status"] or ""))
        self._tbl.setSortingEnabled(True)
        n = len(rows)
        sum_total = sum(float(r["total"] or 0) for r in rows)
        sum_bal = sum(float(r["balance_due"] or 0) for r in rows)
        filt = len(all_rows) - n
        extra = f" ({filt} hidden by filter)" if filt else ""
        self._ap_footer.setText(
            f"{n} bill(s){extra} · Bill total: {sum_total:,.2f} · Balance due: {sum_bal:,.2f}"
        )

    def _on_bill_row_double_clicked(self, row: int, _col: int) -> None:
        if row < 0:
            return
        self._tbl.selectRow(row)
        self._edit_b()

    def _on_bill_context_menu(self, pos) -> None:
        row = self._tbl.rowAt(pos.y())
        if row < 0 or _table_row_entity_id(self._tbl, row) is None:
            return
        m = QMenu(self)
        m.addAction("Edit…", lambda r=row: (self._tbl.selectRow(r), self._edit_b()))
        m.addAction(
            "Open attachment…",
            lambda r=row: self._open_bill_attachment(r),
        )
        m.addAction("Copy row", lambda r=row: copy_table_row_as_tsv(self._tbl, r))
        m.exec(self._tbl.viewport().mapToGlobal(pos))

    def _open_bill_attachment(self, row: int) -> None:
        self._tbl.selectRow(row)
        bid = _table_row_entity_id(self._tbl, row)
        if bid is None:
            return
        b = business.get_bill(self._conn, bid)
        if b is None:
            return
        apath = (dict(b).get("attachment_path") or "").strip()
        open_local_attachment(
            self,
            apath,
            empty_message="No attachment path is set for this bill.",
        )

    def _new_v(self):
        d = QDialog(self)
        d.setWindowTitle("New vendor")
        f = QFormLayout(d)
        ne = QLineEdit()
        em = QLineEdit()
        ph = QLineEdit()
        ad = QPlainTextEdit()
        ad.setFixedHeight(56)
        no = QPlainTextEdit()
        no.setFixedHeight(48)
        irs = QCheckBox("1099 vendor")
        f.addRow("Name *", ne)
        f.addRow("Email", em)
        f.addRow("Phone", ph)
        f.addRow("Address", ad)
        f.addRow("Notes", no)
        f.addRow("", irs)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.DialogCode.Accepted or not ne.text().strip():
            return
        business.add_vendor(
            self._conn,
            ne.text().strip(),
            email=em.text().strip(),
            phone=ph.text().strip(),
            address=ad.toPlainText().strip(),
            notes=no.toPlainText().strip(),
            is_1099=irs.isChecked(),
        )
        self._refresh()

    def _edit_v(self):
        vs = business.list_vendors(self._conn)
        if not vs:
            QMessageBox.information(self, "Vendors", "No vendors to edit.")
            return
        d = QDialog(self)
        d.setWindowTitle("Edit vendor")
        f = QFormLayout(d)
        filt = QLineEdit()
        filt.setPlaceholderText("Filter by name, email, phone, address, notes, 1099, or id…")
        filt.setClearButtonEnabled(True)
        cb = QComboBox()
        ne = QLineEdit()
        em = QLineEdit()
        ph = QLineEdit()
        ad = QPlainTextEdit()
        ad.setFixedHeight(56)
        no = QPlainTextEdit()
        no.setFixedHeight(48)
        irs = QCheckBox("1099 vendor")

        def load_vendor(_index: int | None = None) -> None:
            vid = cb.currentData()
            if vid is None:
                return
            row = business.get_vendor(self._conn, int(vid))
            if row is None:
                return
            ne.setText(row["name"] or "")
            em.setText(row["email"] or "")
            ph.setText(row["phone"] or "")
            ad.setPlainText(row["address"] or "")
            no.setPlainText(row["notes"] or "")
            irs.setChecked(bool(int(row["is_1099"] or 0)))

        def sync_vendor_combo() -> None:
            _sync_filtered_entity_combo(
                vs,
                filt.text(),
                cb,
                business_list_filter.VENDOR_ENTITY_KEYS,
                tag_1099=True,
            )
            load_vendor()

        cb.currentIndexChanged.connect(load_vendor)
        filt.textChanged.connect(sync_vendor_combo)
        f.addRow("Filter list", filt)
        f.addRow("Vendor", cb)
        sync_vendor_combo()
        f.addRow("Name *", ne)
        f.addRow("Email", em)
        f.addRow("Phone", ph)
        f.addRow("Address", ad)
        f.addRow("Notes", no)
        f.addRow("", irs)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        if not ne.text().strip():
            return
        vid = cb.currentData()
        if vid is None:
            QMessageBox.warning(self, "Vendor", "No vendor selected (try clearing the filter).")
            return
        try:
            business.update_vendor(
                self._conn,
                int(vid),
                ne.text().strip(),
                email=em.text().strip(),
                phone=ph.text().strip(),
                address=ad.toPlainText().strip(),
                notes=no.toPlainText().strip(),
                is_1099=irs.isChecked(),
            )
        except ValueError as exc:
            QMessageBox.warning(
                self, "Vendor", escape_ampersand_for_qt(str(exc))
            )
            return
        self._refresh()

    def _new_b(self):
        vs = business.list_vendors(self._conn)
        if not vs:
            QMessageBox.information(self, "Vendors", "Add a vendor first.")
            return
        d = QDialog(self)
        d.setWindowTitle("New bill")
        f = QFormLayout(d)
        vend_filt = QLineEdit()
        vend_filt.setPlaceholderText("Filter vendors by name, email, phone, 1099…")
        vend_filt.setClearButtonEnabled(True)
        cb = QComboBox()

        def sync_new_bill_vendors() -> None:
            _sync_filtered_entity_combo(
                vs,
                vend_filt.text(),
                cb,
                business_list_filter.VENDOR_ENTITY_KEYS,
                tag_1099=True,
            )

        vend_filt.textChanged.connect(sync_new_bill_vendors)
        f.addRow("Filter list", vend_filt)
        f.addRow("Vendor", cb)
        sync_new_bill_vendors()
        _restore_entity_combo(cb, _NEW_BILL_VENDOR_KEY)
        vinv = QLineEdit()
        amt = QDoubleSpinBox()
        amt.setRange(0, 9_999_999)
        amt.setDecimals(2)
        bdt = QDateEdit()
        bdt.setCalendarPopup(True)
        bdt.setDisplayFormat("yyyy-MM-dd")
        bdt.setDate(QDate.currentDate())
        due_e = QLineEdit()
        memo_e = QLineEdit()
        att = QLineEdit()

        def browse_att():
            path, _ = QFileDialog.getOpenFileName(d, "Attachment", "", "All Files (*.*)")
            if path:
                att.setText(path)

        att_row = QHBoxLayout()
        att_row.addWidget(att)
        att_row.addWidget(QPushButton("Browse…", clicked=browse_att))
        f.addRow("Vendor invoice #", vinv)
        f.addRow("Amount *", amt)
        f.addRow("Bill date", bdt)
        f.addRow("Due date (optional)", due_e)
        f.addRow("Memo", memo_e)
        f.addRow("Attachment path", att_row)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        vid = cb.currentData()
        if vid is None:
            QMessageBox.warning(self, "Bill", "Select a vendor (try clearing the filter).")
            return
        business.create_bill(
            self._conn,
            int(vid),
            bdt.date().toString("yyyy-MM-dd"),
            amt.value(),
            vendor_invoice_number=vinv.text().strip(),
            due_date=due_e.text().strip(),
            memo=memo_e.text().strip(),
            attachment_path=att.text().strip(),
        )
        _save_entity_combo(cb, _NEW_BILL_VENDOR_KEY)
        self._refresh()

    def _edit_b(self):
        r = self._tbl.currentRow()
        bill_id = _table_row_entity_id(self._tbl, r)
        if bill_id is None:
            QMessageBox.information(self, "Bill", "Select a bill row.")
            return
        if business.bill_has_payment_allocations(self._conn, bill_id):
            QMessageBox.information(
                self,
                "Bill",
                "This bill has payments applied and cannot be edited.",
            )
            return
        b = business.get_bill(self._conn, bill_id)
        if b is None:
            self._refresh()
            return
        vs = business.list_vendors(self._conn)
        if not vs:
            return
        d = QDialog(self)
        d.setWindowTitle("Edit bill")
        f = QFormLayout(d)
        bill_vid = int(b["vendor_id"])
        ensure_v = frozenset({bill_vid})
        vend_filt = QLineEdit()
        vend_filt.setPlaceholderText("Filter vendors (current bill vendor always listed)…")
        vend_filt.setClearButtonEnabled(True)
        cb = QComboBox()

        def sync_edit_bill_vendors() -> None:
            _sync_filtered_entity_combo(
                vs,
                vend_filt.text(),
                cb,
                business_list_filter.VENDOR_ENTITY_KEYS,
                tag_1099=True,
                always_include_ids=ensure_v,
            )

        vend_filt.textChanged.connect(sync_edit_bill_vendors)
        f.addRow("Filter list", vend_filt)
        f.addRow("Vendor", cb)
        sync_edit_bill_vendors()
        vidx = next(
            (i for i in range(cb.count()) if cb.itemData(i) == bill_vid),
            0,
        )
        cb.setCurrentIndex(vidx)
        vinv = QLineEdit(b["vendor_invoice_number"] or "")
        amt = QDoubleSpinBox()
        amt.setRange(0, 9_999_999)
        amt.setDecimals(2)
        amt.setValue(float(b["total"] or 0))
        bdt = QDateEdit()
        bdt.setCalendarPopup(True)
        bdt.setDisplayFormat("yyyy-MM-dd")
        qbd = QDate.fromString(b["bill_date"] or "", "yyyy-MM-dd")
        bdt.setDate(qbd if qbd.isValid() else QDate.currentDate())
        due_e = QLineEdit(b["due_date"] or "")
        memo_e = QLineEdit(b["memo"] or "")
        att = QLineEdit(b["attachment_path"] or "")

        def browse_att():
            path, _ = QFileDialog.getOpenFileName(d, "Attachment", "", "All Files (*.*)")
            if path:
                att.setText(path)

        att_row = QHBoxLayout()
        att_row.addWidget(att)
        att_row.addWidget(QPushButton("Browse…", clicked=browse_att))
        f.addRow("Vendor invoice #", vinv)
        f.addRow("Amount *", amt)
        f.addRow("Bill date", bdt)
        f.addRow("Due date (optional)", due_e)
        f.addRow("Memo", memo_e)
        f.addRow("Attachment path", att_row)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        new_vid = cb.currentData()
        if new_vid is None:
            QMessageBox.warning(self, "Bill", "Select a vendor (try clearing the filter).")
            return
        try:
            business.update_bill(
                self._conn,
                bill_id,
                int(new_vid),
                bdt.date().toString("yyyy-MM-dd"),
                amt.value(),
                vendor_invoice_number=vinv.text().strip(),
                due_date=due_e.text().strip(),
                memo=memo_e.text().strip(),
                attachment_path=att.text().strip(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Bill", escape_ampersand_for_qt(str(exc)))
            return
        self._refresh()

    def _record_ap_payment(self):
        vs = business.list_vendors(self._conn)
        if not vs:
            QMessageBox.information(self, "AP payment", "Add a vendor first.")
            return
        d = QDialog(self)
        d.setWindowTitle("Record vendor payment")
        d.setMinimumWidth(540)
        outer = QVBoxLayout(d)
        form = QFormLayout()
        vend_filt = QLineEdit()
        vend_filt.setPlaceholderText("Filter vendors by name, email, phone, 1099…")
        vend_filt.setClearButtonEnabled(True)
        vend_cb = QComboBox()
        form.addRow("Filter list", vend_filt)
        form.addRow("Vendor", vend_cb)
        pdate = QDateEdit()
        pdate.setCalendarPopup(True)
        pdate.setDisplayFormat("yyyy-MM-dd")
        pdate.setDate(QDate.currentDate())
        pay_amt = QDoubleSpinBox()
        pay_amt.setRange(0.01, 99_999_999.99)
        pay_amt.setDecimals(2)
        method_e = QLineEdit()
        ref_e = QLineEdit()
        memo_e = QLineEdit()
        bank_cb = QComboBox()
        bank_cb.addItem("(None)")
        try:
            banks = self._conn.execute(
                "SELECT id, name FROM bank_accounts WHERE is_active = 1 ORDER BY name"
            ).fetchall()
        except sqlite3.OperationalError:
            banks = []
        for b in banks:
            bank_cb.addItem(
                escape_ampersand_for_qt(b["name"] or ""), int(b["id"])
            )
        _restore_payment_bank_combo(bank_cb, _AP_PAYMENT_BANK_KEY)
        form.addRow("Payment date", pdate)
        form.addRow("Amount *", pay_amt)
        form.addRow("Paid from bank", bank_cb)
        form.addRow("Method", method_e)
        form.addRow("Reference #", ref_e)
        form.addRow("Memo", memo_e)
        outer.addLayout(form)
        outer.addWidget(QLabel("Apply to open bills:"))
        hint = QLabel('Sum of "Apply" must equal the payment amount.')
        hint.setStyleSheet("color: palette(mid);")
        outer.addWidget(hint)
        alloc_tbl = QTableWidget()
        alloc_tbl.setColumnCount(4)
        alloc_tbl.setHorizontalHeaderLabels(["Vendor inv. #", "Date", "Balance", "Apply"])
        alloc_tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        def rebuild_ap_alloc_table(_idx: int | None = None) -> None:
            vid = vend_cb.currentData()
            alloc_tbl.setSortingEnabled(False)
            alloc_tbl.setRowCount(0)
            if vid is None:
                alloc_tbl.setSortingEnabled(True)
                return
            opens = business.list_open_bills_for_vendor(self._conn, int(vid))
            alloc_tbl.setRowCount(len(opens))
            align_rc = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            for i, r in enumerate(opens):
                label = (r["vendor_invoice_number"] or "").strip() or f"Bill #{r['id']}"
                it0 = plain_display_table_item(label)
                it0.setData(Qt.ItemDataRole.UserRole, int(r["id"]))
                alloc_tbl.setItem(i, 0, it0)
                alloc_tbl.setItem(
                    i, 1, plain_display_table_item(r["bill_date"] or "")
                )
                bal = float(r["balance_due"])
                bal_it = _FloatSortTableItem(f"{bal:,.2f}", bal)
                bal_it.setTextAlignment(align_rc)
                alloc_tbl.setItem(i, 2, bal_it)
                sp = QDoubleSpinBox()
                sp.setRange(0, float(r["balance_due"]))
                sp.setDecimals(2)
                alloc_tbl.setCellWidget(i, 3, sp)
            alloc_tbl.setSortingEnabled(True)

        def sync_ap_payment_vendors() -> None:
            _sync_filtered_entity_combo(
                vs,
                vend_filt.text(),
                vend_cb,
                business_list_filter.VENDOR_ENTITY_KEYS,
                tag_1099=True,
            )
            rebuild_ap_alloc_table()

        def apply_oldest_first_ap() -> None:
            remaining = round(pay_amt.value(), 2)
            for row in range(alloc_tbl.rowCount()):
                w = alloc_tbl.cellWidget(row, 3)
                if not isinstance(w, QDoubleSpinBox):
                    continue
                cap = round(float(w.maximum()), 2)
                use = min(remaining, cap)
                w.setValue(use)
                remaining = round(remaining - use, 2)
                if remaining <= 0.001:
                    break

        vend_filt.textChanged.connect(sync_ap_payment_vendors)
        vend_cb.currentIndexChanged.connect(rebuild_ap_alloc_table)
        sync_ap_payment_vendors()
        _restore_entity_combo(vend_cb, _AP_PAYMENT_VENDOR_KEY)
        auto_row = QHBoxLayout()
        auto_row.addWidget(QPushButton("Fill oldest first", clicked=apply_oldest_first_ap))
        auto_row.addStretch()
        outer.addLayout(auto_row)
        _attach_table_copy_row_menu(alloc_tbl, d)
        outer.addWidget(alloc_tbl)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        outer.addWidget(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        vid = vend_cb.currentData()
        if vid is None:
            QMessageBox.warning(
                self,
                "AP payment",
                "Select a vendor (try clearing the filter).",
            )
            return
        amt = round(pay_amt.value(), 2)
        allocs: list[tuple[int, float]] = []
        for row in range(alloc_tbl.rowCount()):
            it = alloc_tbl.item(row, 0)
            w = alloc_tbl.cellWidget(row, 3)
            if it is None or not isinstance(w, QDoubleSpinBox):
                continue
            v = round(w.value(), 2)
            if v <= 0.005:
                continue
            bid = int(it.data(Qt.ItemDataRole.UserRole))
            allocs.append((bid, v))
        if not allocs:
            QMessageBox.warning(
                self,
                "AP payment",
                "Enter an amount in Apply for at least one bill.",
            )
            return
        applied = round(sum(a for _, a in allocs), 2)
        if abs(applied - amt) > 0.02:
            QMessageBox.warning(
                self,
                "AP payment",
                f"Apply amounts ({applied:.2f}) must equal payment amount ({amt:.2f}).",
            )
            return
        bidx = bank_cb.currentIndex()
        bank_account_id = None
        if bidx > 0:
            bd = bank_cb.itemData(bidx)
            if bd is not None:
                bank_account_id = int(bd)
        business.record_ap_payment(
            self._conn,
            int(vid),
            pdate.date().toString("yyyy-MM-dd"),
            amt,
            allocs,
            bank_account_id=bank_account_id,
            method=method_e.text().strip(),
            reference=ref_e.text().strip(),
            memo=memo_e.text().strip(),
        )
        _save_entity_combo(vend_cb, _AP_PAYMENT_VENDOR_KEY)
        _save_payment_bank_choice(bank_cb, _AP_PAYMENT_BANK_KEY)
        self._refresh()
        QMessageBox.information(self, "AP payment", "Payment recorded.")

    def _export_aging(self):
        as_of = _prompt_as_of_date(self, "Export AP aging")
        if as_of is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "AP aging", "", "CSV (*.csv)")
        if not path:
            return
        data = business.ap_aging_buckets(self._conn, as_of)[0]
        with open(path, "w", newline="", encoding="utf-8") as fp:
            w = csv.writer(fp)
            w.writerow(
                ["Vendor", "Bill id", "Balance", "Bucket", "Days past due", "As of"]
            )
            for ln in data["lines"]:
                w.writerow(
                    [
                        ln["vendor"],
                        ln["bill_id"],
                        f"{ln['balance']:.2f}",
                        ln["bucket"],
                        ln.get("days_past_due", ""),
                        as_of,
                    ]
                )
            _append_aging_bucket_totals_csv(w, data["buckets"], as_of)
        QMessageBox.information(
            self,
            "Export",
            f"Wrote {escape_ampersand_for_qt(path)}\n(As of {as_of})",
        )

    def _export_vendors(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export vendors", "vendors.csv", "CSV (*.csv)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            n = business.write_vendors_csv(self._conn, path)
        except OSError as exc:
            QMessageBox.critical(
                self, "Export failed", escape_ampersand_for_qt(str(exc))
            )
            return
        QMessageBox.information(
            self,
            "Export",
            f"Exported {n} vendor(s) to {escape_ampersand_for_qt(path)}",
        )

    def _export_bills(self):
        filt = self._bill_filter.text().strip()
        all_rows = business.list_bills(self._conn)
        filtered = business_list_filter.filter_business_rows(
            all_rows, filt, business_list_filter.AP_BILL_FILTER_KEYS
        )
        vis_ids = [int(r["id"]) for r in filtered]
        scope = _prompt_list_csv_export_scope(self, "bills", bool(filt), vis_ids)
        if scope is None:
            return
        bill_ids = None if scope == "all" else scope
        path, _ = QFileDialog.getSaveFileName(
            self, "Export bills", "bills.csv", "CSV (*.csv)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            n = business.write_bills_csv(self._conn, path, bill_ids=bill_ids)
        except OSError as exc:
            QMessageBox.critical(
                self, "Export failed", escape_ampersand_for_qt(str(exc))
            )
            return
        QMessageBox.information(
            self,
            "Export",
            f"Exported {n} bill(s) to {escape_ampersand_for_qt(path)}",
        )

    def _export_ap_payments(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export AP payments", "ap_payments.csv", "CSV (*.csv)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            n = business.write_ap_payments_csv(self._conn, path)
        except OSError as exc:
            QMessageBox.critical(
                self, "Export failed", escape_ampersand_for_qt(str(exc))
            )
            return
        QMessageBox.information(
            self,
            "Export",
            f"Exported {n} payment(s) to {escape_ampersand_for_qt(path)}",
        )

    def _export_ap_allocations(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export AP payment allocations",
            "ap_payment_allocations.csv",
            "CSV (*.csv)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            n = business.write_ap_payment_allocations_csv(self._conn, path)
        except OSError as exc:
            QMessageBox.critical(
                self, "Export failed", escape_ampersand_for_qt(str(exc))
            )
            return
        QMessageBox.information(
            self,
            "Export",
            f"Exported {n} allocation row(s) to {escape_ampersand_for_qt(path)}",
        )


class PayrollTaxTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        lay = QVBoxLayout(self)
        row1 = QHBoxLayout()
        row1.addWidget(QPushButton("New employee", clicked=self._new_emp))
        row1.addWidget(QPushButton("New pay run", clicked=self._new_run))
        row1.addWidget(QPushButton("Post selected run to GL…", clicked=self._post_gl))
        row1.addStretch()
        lay.addLayout(row1)
        row2 = QHBoxLayout()
        row2.addWidget(QPushButton("Tax codes…", clicked=self._tax_codes))
        row2.addWidget(QPushButton("Tax lines for run…", clicked=self._edit_run_taxes))
        row2.addWidget(QPushButton("Export tax report CSV…", clicked=self._export_tax_report))
        row2.addStretch()
        lay.addLayout(row2)
        self._tbl = QTableWidget()
        self._tbl.setColumnCount(7)
        self._tbl.setHorizontalHeaderLabels(
            ["Run #", "Employee", "Pay date", "Gross", "Ded", "Net", "JE #"]
        )
        self._tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._tbl.setSortingEnabled(True)
        self._tbl.cellDoubleClicked.connect(self._on_payroll_run_double_clicked)
        _wire_enter_opens_edit(self._tbl, self._edit_run_taxes)
        self._tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tbl.customContextMenuRequested.connect(self._on_payroll_run_context_menu)
        lay.addWidget(self._tbl)
        self._refresh()

    def persist_header_state(self) -> None:
        QSettings().setValue(
            _PAYROLL_RUNS_HEADER_STATE_KEY,
            self._tbl.horizontalHeader().saveState(),
        )

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        raw = QSettings().value(_PAYROLL_RUNS_HEADER_STATE_KEY)
        if raw:
            self._tbl.horizontalHeader().restoreState(raw)

    def hideEvent(self, event: QHideEvent) -> None:
        self.persist_header_state()
        super().hideEvent(event)

    def _tax_codes(self):
        try:
            items = business.list_payroll_tax_items(self._conn, active_only=False)
        except sqlite3.OperationalError:
            QMessageBox.warning(
                self,
                "Payroll taxes",
                "Tax tables are missing. Restart the app or open a company file "
                "that has been upgraded to the latest schema.",
            )
            return
        d = QDialog(self)
        d.setWindowTitle("Payroll tax codes")
        v = QVBoxLayout(d)
        tbl = QTableWidget()
        tbl.setColumnCount(4)
        tbl.setHorizontalHeaderLabels(["Code", "Name", "Jurisdiction", "Sort"])
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        tbl.setSortingEnabled(False)
        tbl.setRowCount(len(items))
        for i, it in enumerate(items):
            tbl.setItem(i, 0, plain_display_table_item(it["code"] or ""))
            tbl.setItem(i, 1, plain_display_table_item(it["name"] or ""))
            tbl.setItem(
                i, 2, plain_display_table_item(it["jurisdiction"] or "")
            )
            so = int(it["sort_order"])
            tbl.setItem(i, 3, _IntSortTableItem(str(so), so))
        tbl.setSortingEnabled(True)
        _attach_table_copy_row_menu(tbl, d)
        v.addWidget(tbl)
        btn_row = QHBoxLayout()
        btn_row.addWidget(QPushButton("Add code", clicked=lambda: self._add_tax_code(d, tbl)))
        btn_row.addStretch()
        btn_row.addWidget(QPushButton("Close", clicked=d.accept))
        v.addLayout(btn_row)
        d.exec()

    def _add_tax_code(self, parent_dlg: QDialog, tbl: QTableWidget):
        d = QDialog(parent_dlg)
        d.setWindowTitle("New tax code")
        f = QFormLayout(d)
        code = QLineEdit()
        name = QLineEdit()
        jur = QLineEdit()
        so = QSpinBox()
        so.setRange(-999, 9999)
        so.setValue(100)
        f.addRow("Code *", code)
        f.addRow("Name *", name)
        f.addRow("Jurisdiction", jur)
        f.addRow("Sort order", so)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        if not code.text().strip() or not name.text().strip():
            return
        try:
            business.add_payroll_tax_item(
                self._conn,
                code.text().strip(),
                name.text().strip(),
                jur.text().strip(),
                so.value(),
            )
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Payroll taxes", "That code already exists.")
            return
        items = business.list_payroll_tax_items(self._conn, active_only=False)
        tbl.setSortingEnabled(False)
        tbl.setRowCount(len(items))
        for i, it in enumerate(items):
            tbl.setItem(i, 0, plain_display_table_item(it["code"] or ""))
            tbl.setItem(i, 1, plain_display_table_item(it["name"] or ""))
            tbl.setItem(
                i, 2, plain_display_table_item(it["jurisdiction"] or "")
            )
            so = int(it["sort_order"])
            tbl.setItem(i, 3, _IntSortTableItem(str(so), so))
        tbl.setSortingEnabled(True)

    def _edit_run_taxes(self):
        r = self._tbl.currentRow()
        run_id = _payroll_run_id_at_row(self._tbl, r)
        if run_id is None or not getattr(self, "_run_rows", None):
            QMessageBox.information(self, "Payroll taxes", "Select a pay run row.")
            return
        try:
            items = business.list_payroll_tax_items(self._conn, active_only=True)
        except sqlite3.OperationalError:
            QMessageBox.warning(self, "Payroll taxes", "Tax tables are missing.")
            return
        if not items:
            QMessageBox.information(self, "Payroll taxes", "Add tax codes first.")
            return
        existing = {
            row["tax_item_id"]: row
            for row in business.list_payroll_run_tax_lines(self._conn, run_id)
        }
        d = QDialog(self)
        d.setWindowTitle(f"Payroll tax lines — run #{run_id}")
        d.setMinimumWidth(520)
        v = QVBoxLayout(d)
        v.addWidget(
            QLabel(
                "Enter employee vs employer portions manually (Phase 16 placeholder). "
                "Totals roll into the tax report CSV."
            )
        )
        tbl = QTableWidget(len(items), 4)
        tbl.setHorizontalHeaderLabels(["Code", "Name", "Employee $", "Employer $"])
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        tbl.setSortingEnabled(False)
        spin_pairs: list[tuple[int, QDoubleSpinBox, QDoubleSpinBox]] = []
        for i, it in enumerate(items):
            iid = it["id"]
            tbl.setItem(i, 0, plain_display_table_item(it["code"] or ""))
            tbl.setItem(i, 1, plain_display_table_item(it["name"] or ""))
            se = QDoubleSpinBox()
            se.setRange(-9_999_999.99, 9_999_999.99)
            se.setDecimals(2)
            sr = QDoubleSpinBox()
            sr.setRange(-9_999_999.99, 9_999_999.99)
            sr.setDecimals(2)
            prev = existing.get(iid)
            if prev:
                se.setValue(float(prev["employee_amount"]))
                sr.setValue(float(prev["employer_amount"]))
            tbl.setCellWidget(i, 2, se)
            tbl.setCellWidget(i, 3, sr)
            spin_pairs.append((iid, se, sr))
        tbl.setSortingEnabled(True)
        _attach_table_copy_row_menu(tbl, d)
        v.addWidget(tbl)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        v.addWidget(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        for tax_item_id, se, sr in spin_pairs:
            business.upsert_payroll_run_tax_line(
                self._conn,
                run_id,
                tax_item_id,
                se.value(),
                sr.value(),
                "",
            )
        QMessageBox.information(self, "Payroll taxes", "Tax lines saved.")

    def _on_payroll_run_double_clicked(self, row: int, _col: int) -> None:
        if row < 0:
            return
        self._tbl.selectRow(row)
        self._edit_run_taxes()

    def _on_payroll_run_context_menu(self, pos) -> None:
        row = self._tbl.rowAt(pos.y())
        if row < 0 or _payroll_run_id_at_row(self._tbl, row) is None:
            return
        m = QMenu(self)
        m.addAction(
            "Tax lines for run…",
            lambda r=row: (self._tbl.selectRow(r), self._edit_run_taxes()),
        )
        m.addAction(
            "Post selected run to GL…",
            lambda r=row: (self._tbl.selectRow(r), self._post_gl()),
        )
        m.addAction("Copy row", lambda r=row: copy_table_row_as_tsv(self._tbl, r))
        m.exec(self._tbl.viewport().mapToGlobal(pos))

    def _export_tax_report(self):
        d = QDialog(self)
        d.setWindowTitle("Payroll tax report")
        f = QFormLayout(d)
        s = QDateEdit()
        s.setCalendarPopup(True)
        s.setDisplayFormat("yyyy-MM-dd")
        e = QDateEdit()
        e.setCalendarPopup(True)
        e.setDisplayFormat("yyyy-MM-dd")
        e.setDate(QDate.currentDate())
        s.setDate(QDate.currentDate().addMonths(-1))
        f.addRow("From pay date", s)
        f.addRow("To pay date", e)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        start = s.date().toString("yyyy-MM-dd")
        end = e.date().toString("yyyy-MM-dd")
        if start > end:
            QMessageBox.warning(self, "Payroll taxes", "Start date must be on or before end date.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Payroll tax totals", "", "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return
        try:
            rows = business.payroll_tax_totals_by_range(self._conn, start, end)
        except sqlite3.OperationalError:
            QMessageBox.warning(self, "Payroll taxes", "Tax tables are missing.")
            return
        with open(path, "w", newline="", encoding="utf-8") as fp:
            w = csv.writer(fp)
            w.writerow(
                ["code", "name", "jurisdiction", "employee_total", "employer_total"]
            )
            for r in rows:
                w.writerow(
                    [
                        r["code"],
                        r["name"],
                        r["jurisdiction"] or "",
                        f"{float(r['employee_total'] or 0):.2f}",
                        f"{float(r['employer_total'] or 0):.2f}",
                    ]
                )
        QMessageBox.information(
            self, "Payroll taxes", f"Wrote {escape_ampersand_for_qt(path)}"
        )

    def _refresh(self):
        rows = self._conn.execute(
            """
            SELECT p.id, e.name, p.pay_date, p.gross, p.deductions, p.net_pay, p.journal_entry_id
            FROM payroll_runs p
            JOIN employees e ON e.id = p.employee_id
            ORDER BY p.pay_date DESC
            """
        ).fetchall()
        self._run_rows = [dict(x) for x in rows]
        self._tbl.setSortingEnabled(False)
        self._tbl.setRowCount(len(self._run_rows))
        for i, r in enumerate(self._run_rows):
            rid = int(r["id"])
            it0 = _IntSortTableItem(str(rid), rid)
            it0.setData(Qt.ItemDataRole.UserRole, rid)
            self._tbl.setItem(i, 0, it0)
            self._tbl.setItem(
                i, 1, plain_display_table_item(str(r.get("name") or ""))
            )
            self._tbl.setItem(
                i, 2, plain_display_table_item(str(r.get("pay_date") or ""))
            )
            g = float(r.get("gross") or 0)
            d = float(r.get("deductions") or 0)
            n = float(r.get("net_pay") or 0)
            self._tbl.setItem(i, 3, _FloatSortTableItem(f"{g:.2f}", g))
            self._tbl.setItem(i, 4, _FloatSortTableItem(f"{d:.2f}", d))
            self._tbl.setItem(i, 5, _FloatSortTableItem(f"{n:.2f}", n))
            je = r.get("journal_entry_id")
            if je is None:
                self._tbl.setItem(i, 6, plain_display_table_item(""))
            else:
                jid = int(je)
                self._tbl.setItem(i, 6, _IntSortTableItem(str(jid), jid))
        self._tbl.setSortingEnabled(True)

    def _post_gl(self):
        r = self._tbl.currentRow()
        rid = _payroll_run_id_at_row(self._tbl, r)
        if rid is None or not getattr(self, "_run_rows", None):
            QMessageBox.information(self, "GL", "Select a pay run row.")
            return
        run = next((x for x in self._run_rows if int(x["id"]) == rid), None)
        if run is None:
            self._refresh()
            QMessageBox.information(self, "GL", "Pay run not found; list was refreshed.")
            return
        if run.get("journal_entry_id"):
            QMessageBox.information(self, "GL", "This run already has a journal_entry_id.")
            return
        from PySide6.QtWidgets import QComboBox

        from probooksai.coa_db import COADatabase
        from probooksai.gl import GLDatabase

        cdb = COADatabase(self._conn)
        gl = GLDatabase(self._conn)
        d = QDialog(self)
        d.setWindowTitle("Post payroll to GL")
        f = QFormLayout(d)
        exp = QComboBox()
        exp.setEditable(True)
        cash = QComboBox()
        cash.setEditable(True)
        liab = QComboBox()
        liab.setEditable(True)
        for s in cdb.display_list():
            exp.addItem(escape_ampersand_for_qt(s), s)
            cash.addItem(escape_ampersand_for_qt(s), s)
            liab.addItem(escape_ampersand_for_qt(s), s)
        f.addRow("Wage expense (debit gross)", exp)
        f.addRow("Cash / bank (credit net pay)", cash)
        f.addRow("Withholdings liability (credit deductions)", liab)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        gross = float(run["gross"])
        net = float(run["net_pay"])
        ded = float(run["deductions"])
        exp_a = (exp.currentData() or exp.currentText() or "").strip()
        cash_a = (cash.currentData() or cash.currentText() or "").strip()
        liab_a = (liab.currentData() or liab.currentText() or "").strip()
        if not exp_a or not cash_a:
            return
        lines = [
            {"account": exp_a, "debit": gross, "credit": 0.0, "description": "Payroll"},
            {"account": cash_a, "debit": 0.0, "credit": net, "description": "Net pay"},
        ]
        if ded > 0.005:
            if not liab_a:
                QMessageBox.warning(
                    self, "GL", "Enter a liability account for payroll deductions."
                )
                return
            lines.append(
                {
                    "account": liab_a,
                    "debit": 0.0,
                    "credit": ded,
                    "description": "Withholdings",
                }
            )
        try:
            eid = gl.create_journal_entry(
                entry_date=str(run["pay_date"]),
                lines=lines,
                memo=f"Payroll run #{run['id']}",
                source="payroll",
            )
        except ValueError as exc:
            QMessageBox.warning(self, "GL", escape_ampersand_for_qt(str(exc)))
            return
        self._conn.execute(
            "UPDATE payroll_runs SET journal_entry_id = ? WHERE id = ?",
            (eid, run["id"]),
        )
        self._conn.commit()
        QMessageBox.information(self, "GL", f"Posted journal entry #{eid}.")
        self._refresh()

    def _new_emp(self):
        d = QDialog(self)
        f = QFormLayout(d)
        ne = QLineEdit()
        f.addRow("Name", ne)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.DialogCode.Accepted or not ne.text().strip():
            return
        business.add_employee(self._conn, ne.text().strip())
        self._refresh()

    def _new_run(self):
        emps = business.list_employees(self._conn)
        if not emps:
            QMessageBox.information(self, "Payroll", "Add an employee first.")
            return
        from PySide6.QtWidgets import QComboBox

        d = QDialog(self)
        f = QFormLayout(d)
        cb = QComboBox()
        for e in emps:
            cb.addItem(escape_ampersand_for_qt(e["name"] or ""), e["id"])
        gross = QDoubleSpinBox()
        gross.setRange(0, 9_999_999)
        gross.setDecimals(2)
        ded = QDoubleSpinBox()
        ded.setRange(0, 9_999_999)
        ded.setDecimals(2)
        pd = QDateEdit()
        pd.setCalendarPopup(True)
        pd.setDisplayFormat("yyyy-MM-dd")
        pd.setDate(QDate.currentDate())
        f.addRow("Employee", cb)
        f.addRow("Gross", gross)
        f.addRow("Deductions", ded)
        f.addRow("Pay date", pd)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        pay_d = pd.date().toPython()
        ps = date_cls(pay_d.year, pay_d.month, 1).isoformat()
        pe = pay_d.isoformat()
        business.create_payroll_run(
            self._conn,
            cb.currentData(),
            ps,
            pe,
            pd.date().toString("yyyy-MM-dd"),
            gross.value(),
            ded.value(),
        )
        self._refresh()


class TaxSettingsTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        root = QVBoxLayout(self)
        lay = QFormLayout()
        self._tax_name = QLineEdit()
        self._tax_name.setText(
            business.get_setting(self._conn, "default_tax_name", "Sales tax")
            or "Sales tax"
        )
        lay.addRow(
            escape_ampersand_for_qt("Tax name (reports & labels)"),
            self._tax_name,
        )
        self._rate = QDoubleSpinBox()
        self._rate.setRange(0, 100)
        self._rate.setDecimals(3)
        self._rate.setValue(
            float(business.get_setting(self._conn, "default_tax_rate_pct", "0") or 0)
        )
        lay.addRow("Default sales tax % (invoices)", self._rate)
        root.addLayout(lay)
        root.addWidget(QPushButton("Save settings", clicked=self._save))
        root.addWidget(
            QPushButton("Export sales tax summary CSV\u2026", clicked=self._export_sales_tax_csv)
        )
        save_sc = QShortcut(QKeySequence(QKeySequence.StandardKey.Save), self)
        save_sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        save_sc.activated.connect(self._save)

    def _save(self):
        business.set_setting(
            self._conn,
            "default_tax_name",
            (self._tax_name.text() or "").strip() or "Sales tax",
        )
        business.set_setting(
            self._conn, "default_tax_rate_pct", str(self._rate.value())
        )
        QMessageBox.information(self, "Settings", "Saved.")

    def _export_sales_tax_csv(self):
        d = QDialog(self)
        d.setWindowTitle("Sales tax summary")
        f = QFormLayout(d)
        s = QDateEdit()
        s.setCalendarPopup(True)
        s.setDisplayFormat("yyyy-MM-dd")
        e = QDateEdit()
        e.setCalendarPopup(True)
        e.setDisplayFormat("yyyy-MM-dd")
        e.setDate(QDate.currentDate())
        s.setDate(QDate.currentDate().addMonths(-1))
        f.addRow("From invoice date", s)
        f.addRow("To invoice date", e)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        start = s.date().toString("yyyy-MM-dd")
        end = e.date().toString("yyyy-MM-dd")
        if start > end:
            QMessageBox.warning(self, "Sales tax", "Start date must be on or before end date.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Sales tax summary", "", "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return
        rows = business.sales_tax_invoices_in_range(self._conn, start, end)
        total = business.sales_tax_collected_sum(self._conn, start, end)
        label = (
            business.get_setting(self._conn, "default_tax_name", "Sales tax")
            or "Sales tax"
        )
        with open(path, "w", newline="", encoding="utf-8") as fp:
            w = csv.writer(fp)
            w.writerow(["ProBooks+ai sales tax summary"])
            w.writerow(["Tax label", label])
            w.writerow(["Invoice date from", start])
            w.writerow(["Invoice date to", end])
            w.writerow(["Total tax collected", f"{total:.2f}"])
            w.writerow([])
            w.writerow(
                [
                    "invoice_number",
                    "invoice_date",
                    "customer",
                    "subtotal",
                    "tax_total",
                    "invoice_total",
                ]
            )
            for r in rows:
                w.writerow(
                    [
                        r["invoice_number"],
                        r["invoice_date"],
                        r["customer_name"],
                        f"{float(r['subtotal']):.2f}",
                        f"{float(r['tax_total']):.2f}",
                        f"{float(r['total']):.2f}",
                    ]
                )
        QMessageBox.information(
            self, "Sales tax", f"Wrote {escape_ampersand_for_qt(path)}"
        )


class BusinessHub(QWidget):
    """Nested tabs for rules, AR, AP, payroll, tax."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._business_subtabs = QTabWidget()
        self._business_subtabs.addTab(RulesTab(conn), "Rules")
        self._business_subtabs.addTab(ARTab(conn), "Invoices (AR)")
        self._business_subtabs.addTab(APTab(conn), "Bills (AP)")
        self._business_subtabs.addTab(PayrollTaxTab(conn), "Payroll")
        self._business_subtabs.addTab(TaxSettingsTab(conn), "Tax %")
        raw_idx = QSettings().value(_BUSINESS_HUB_SUBTAB_KEY, 0)
        try:
            want_idx = int(raw_idx) if raw_idx is not None and raw_idx != "" else 0
        except (TypeError, ValueError):
            want_idx = 0
        n_tabs = self._business_subtabs.count()
        want_idx = max(0, min(want_idx, n_tabs - 1))
        self._business_subtabs.setCurrentIndex(want_idx)
        self._prev_business_subtab_idx = want_idx
        self._business_subtabs.currentChanged.connect(self._on_business_subtab_changed)
        lay = QVBoxLayout(self)
        lay.addWidget(self._business_subtabs)

    def _on_business_subtab_changed(self, idx: int) -> None:
        prev_w = self._business_subtabs.widget(self._prev_business_subtab_idx)
        if isinstance(prev_w, RulesTab):
            prev_w.persist_header_state()
        elif isinstance(prev_w, ARTab):
            prev_w.persist_header_state()
        elif isinstance(prev_w, APTab):
            prev_w.persist_header_state()
        elif isinstance(prev_w, PayrollTaxTab):
            prev_w.persist_header_state()
        QSettings().setValue(_BUSINESS_HUB_SUBTAB_KEY, idx)
        self._prev_business_subtab_idx = idx
