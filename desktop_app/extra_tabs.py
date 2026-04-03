"""Rules, AR/AP, payroll, and tax settings (roadmap phases 6, 8–16).

**Business** hub (**F5**): refreshes the active sub-tab list when it defines
``_refresh`` (Rules, Invoices, Bills, Payroll). **Tax %** is settings-only.
The **BusinessHub** root **QWidget** has a hover hint; the nested **QTabWidget** strip has a **setToolTip** for switching subtabs.
Each **sub-tab** on the hub bar has a **setTabToolTip** summary (Rules through Tax %).
**Rules**, **Invoices (AR)**, **Bills (AP)**, **Payroll**, and **Tax %** tab roots also set **self.setToolTip** for margin hover.
**Keyboard shortcuts…** on Rules / AR / AP / Payroll grids (including empty area)
matches **Help → Business shortcuts…**; context-menu **QAction**s use **setToolTip**. The same dialog is offered on Business modal tables
that support **Copy row** (``_attach_table_copy_row_menu``).
Main toolbars on Rules, AR, AP, Payroll, and **Tax %** use **setToolTip** on primary actions.
**Rules** and **Payroll** subtabs include a gray footer hint **QLabel** with its own tooltip.
Rules / AR / AP / Payroll **main grids** also use **setToolTip** (shortcuts + **F5** on Business).
AR/AP **footer** summary lines and payroll **edit tax lines** intro text have hover hints.
**Invoices (AR)** and **Bills (AP)** **Filter** prompts and line edits have **setToolTip** (word-match behavior + persistence).
Payment dialogs label **Apply to open** sections; edit-invoice labels **Line items**; allocation hints have tooltips.
**Tax %** default name and rate fields have **setToolTip**; a gray footer hint explains Ctrl+S and Business hub context.
Inline **QDialog** windows set **setToolTip** on the dialog for a short summary (rules, AR/AP, payroll, tax export prompts).
Modal dialogs built with **QDialogButtonBox** set **OK**/**Save** and **Cancel** tooltips via
``_tip_dialog_ok_cancel`` / ``_tip_dialog_save_cancel``, which delegate to ``tip_qdialog_button_box`` in ``qt_mnemonic`` (including aging as-of and export date prompts).
Simple alerts use ``message_box_information_ok`` / ``message_box_warning_ok`` / ``message_box_critical_ok`` (**Ok** hover hints).
Filtered CSV exports may open a **QMessageBox** (**Visible only** / **All rows** / **Cancel**): custom labels set **setToolTip**; **Cancel** uses ``tip_message_box_buttons(..., cancel=...)``.
Destructive **Yes**/**No** confirms (delete rule, replace-all import) use ``tip_message_box_buttons`` for hover hints.
"""

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
from desktop_app.qt_mnemonic import (
    escape_ampersand_for_qt,
    message_box_critical_ok,
    message_box_information_ok,
    message_box_warning_ok,
    tip_message_box_buttons,
    tip_qdialog_button_box,
)
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
        sc.setContext(Qt.WidgetShortcut)
        sc.activated.connect(edit_handler)


def _attach_table_copy_row_menu(tbl: QTableWidget, menu_parent: QWidget) -> None:
    """Right-click **Keyboard shortcuts…** + **Copy row** (TSV) for Business dialog tables."""
    def _on_ctx(pos):
        idx = tbl.indexAt(pos)
        m = QMenu(menu_parent)
        act_keys = m.addAction(
            "Keyboard shortcuts…",
            lambda: show_business_keyboard_shortcuts_dialog(menu_parent),
        )
        act_keys.setToolTip(
            "Same summary as Help → Business shortcuts… (F5, Tax % Ctrl+S, sub-tab grids)."
        )
        if not idx.isValid():
            m.exec(tbl.viewport().mapToGlobal(pos))
            return
        row = idx.row()
        m.addSeparator()
        act_copy = m.addAction("Copy row", lambda r=row: copy_table_row_as_tsv(tbl, r))
        act_copy.setToolTip(
            "Copy this row as tab-separated text for pasting into a spreadsheet or editor."
        )
        m.exec(tbl.viewport().mapToGlobal(pos))

    tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    tbl.customContextMenuRequested.connect(_on_ctx)


def _wire_find_focuses_line_edit(parent: QWidget, line_edit: QLineEdit) -> None:
    """Standard **Find** shortcut (e.g. Ctrl+F) focuses *line_edit* when *parent* or its children have focus."""
    def _go() -> None:
        line_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        line_edit.selectAll()

    sc = QShortcut(QKeySequence(QKeySequence.StandardKey.Find), parent)
    sc.setContext(Qt.WidgetWithChildrenShortcut)
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
    d.setToolTip(
        "Aging buckets and balances use the as-of date you confirm here (export or report)."
    )
    f = QFormLayout(d)
    de = QDateEdit()
    de.setCalendarPopup(True)
    de.setDisplayFormat("yyyy-MM-dd")
    de.setDate(QDate.currentDate())
    de.setToolTip("Aging balances and buckets are computed as of this date.")
    f.addRow("As of date", de)
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    _tip_dialog_ok_cancel(bb, "Use this as-of date for the aging export.")
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
    box.setToolTip(
        "A list filter is active: export only visible rows, all database rows, or cancel."
    )
    btn_vis = box.addButton("Visible only", QMessageBox.ButtonRole.AcceptRole)
    btn_vis.setToolTip("Export only rows that match the current list filter.")
    btn_all = box.addButton("All rows", QMessageBox.ButtonRole.ActionRole)
    btn_all.setToolTip(
        "Export all records of this type in the database, ignoring the filter."
    )
    cancel_btn = box.addButton(QMessageBox.StandardButton.Cancel)
    tip_message_box_buttons(box, cancel="Close without exporting.")
    box.exec()
    clicked = box.clickedButton()
    if clicked is None or clicked == cancel_btn:
        return None
    if clicked == btn_vis:
        return list(visible_ids)
    if clicked == btn_all:
        return "all"
    return None


_DIALOG_CANCEL_TIP = "Close this dialog without saving changes."


def _tip_dialog_ok_cancel(
    bb: QDialogButtonBox, ok_tip: str, cancel_tip: str = _DIALOG_CANCEL_TIP
) -> None:
    tip_qdialog_button_box(bb, ok=ok_tip, cancel=cancel_tip)


def _tip_dialog_save_cancel(
    bb: QDialogButtonBox, save_tip: str, cancel_tip: str = _DIALOG_CANCEL_TIP
) -> None:
    tip_qdialog_button_box(bb, save=save_tip, cancel=cancel_tip)


class RulesTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self.setToolTip(
            "Categorization rules: description patterns → COA suggestions; grid, CSV import/export, F5 when Business has focus."
        )
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
        self._tbl.setToolTip(
            "Categorization rules. Right-click for Keyboard shortcuts… (empty area OK). "
            "F5 refreshes when Business has focus."
        )
        lay.addWidget(self._tbl)
        row = QHBoxLayout()
        rb_add = QPushButton("Add rule")
        rb_add.setToolTip(
            "Create a new rule (description pattern → COA account, priority)."
        )
        rb_add.clicked.connect(self._add)
        row.addWidget(rb_add)
        rb_edit = QPushButton("Edit selected")
        rb_edit.setToolTip(
            "Edit the selected rule. Double-click a row or press Enter for the same."
        )
        rb_edit.clicked.connect(self._edit)
        row.addWidget(rb_edit)
        rb_del = QPushButton("Delete selected")
        rb_del.setToolTip("Delete the selected rule(s); you will be asked to confirm.")
        rb_del.clicked.connect(self._del)
        row.addWidget(rb_del)
        rb_export = QPushButton("Export CSV…")
        rb_export.setToolTip("Export all rules to a CSV file.")
        rb_export.clicked.connect(self._export_csv)
        row.addWidget(rb_export)
        rb_import = QPushButton("Import CSV…")
        rb_import.setToolTip(
            "Replace all rules from a CSV file after confirmation; the grid refreshes when done."
        )
        rb_import.clicked.connect(self._import_csv)
        row.addWidget(rb_import)
        row.addStretch()
        lay.addLayout(row)
        rules_tip = QLabel(
            "F5 refreshes this rule list when the Business tab has focus. "
            "Help → Business shortcuts…; right-click the grid for Keyboard shortcuts…."
        )
        rules_tip.setWordWrap(True)
        rules_tip.setStyleSheet("color: #A0A0B0; font-size: 11px;")
        rules_tip.setToolTip(
            "Categorization rules match import text to COA; double-click a row to edit; higher priority first."
        )
        lay.addWidget(rules_tip)
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
        idx = self._tbl.indexAt(pos)
        m = QMenu(self)
        act_keys = m.addAction(
            "Keyboard shortcuts…",
            lambda: show_business_keyboard_shortcuts_dialog(self),
        )
        act_keys.setToolTip(
            "Same summary as Help → Business shortcuts… (F5, Rules grid, AR/AP/Payroll)."
        )
        if not idx.isValid():
            m.exec(self._tbl.viewport().mapToGlobal(pos))
            return
        row = idx.row()
        if _rule_id_at_row(self._tbl, row) is None:
            m.exec(self._tbl.viewport().mapToGlobal(pos))
            return
        m.addSeparator()
        act_edit = m.addAction("Edit…", lambda r=row: (self._tbl.selectRow(r), self._edit()))
        act_edit.setToolTip("Open the edit dialog for this categorization rule.")
        act_del = m.addAction("Delete", lambda r=row: (self._tbl.selectRow(r), self._del()))
        act_del.setToolTip("Delete this rule after confirmation.")
        act_copy = m.addAction("Copy row", lambda r=row: copy_table_row_as_tsv(self._tbl, r))
        act_copy.setToolTip(
            "Copy this rule row as tab-separated text for pasting into a spreadsheet or editor."
        )
        m.exec(self._tbl.viewport().mapToGlobal(pos))

    def _add(self):
        d = QDialog(self)
        d.setWindowTitle("New rule")
        d.setToolTip(
            "Add a description pattern and COA line; higher priority rules are considered first when several match."
        )
        f = QFormLayout(d)
        pat = QLineEdit()
        pat.setToolTip(
            "Text that must appear in an import or bank description for this rule to match."
        )
        coa = QLineEdit()
        coa.setToolTip(
            "Chart-of-accounts line to suggest when the pattern matches (e.g. number — name)."
        )
        pr = QSpinBox()
        pr.setRange(-999, 999)
        pr.setValue(10)
        pr.setToolTip("Higher priority rules are considered first when several patterns could match.")
        f.addRow("Description contains", pat)
        f.addRow("COA (e.g. 5010 – Office)", coa)
        f.addRow("Priority (higher first)", pr)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        _tip_dialog_ok_cancel(bb, "Save the new categorization rule.")
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
            message_box_information_ok(
                self,
                "Rules",
                "Select a rule to edit.",
                ok_tip="Close; click a rule row, then Edit again.",
            )
            return
        all_rules = rules_engine.list_rules(self._conn)
        cur = next((x for x in all_rules if x["id"] == rid), None)
        if cur is None:
            self._refresh()
            return
        d = QDialog(self)
        d.setWindowTitle("Edit rule")
        d.setToolTip(
            "Change the pattern, suggested COA, priority, or active flag for this categorization rule."
        )
        f = QFormLayout(d)
        pat = QLineEdit(cur["pattern"])
        pat.setToolTip(
            "Text that must appear in an import or bank description for this rule to match."
        )
        coa = QLineEdit(cur["coa_account"])
        coa.setToolTip(
            "Chart-of-accounts line to suggest when the pattern matches (e.g. number — name)."
        )
        pr = QSpinBox()
        pr.setRange(-999, 999)
        pr.setValue(int(cur["priority"]))
        pr.setToolTip("Higher priority rules are considered first when several patterns could match.")
        active = QSpinBox()
        active.setRange(0, 1)
        active.setValue(1 if cur["is_active"] else 0)
        active.setToolTip("1 = rule is active; 0 = disabled (not used for suggestions).")
        f.addRow("Description contains", pat)
        f.addRow("COA (e.g. 5010 – Office)", coa)
        f.addRow("Priority (higher first)", pr)
        f.addRow("Active (1=yes, 0=no)", active)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        _tip_dialog_ok_cancel(bb, "Save changes to this rule.")
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
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Delete rule")
        box.setText(
            "Delete this categorization rule?\n\nPattern: "
            f"{escape_ampersand_for_qt(pat_preview)}"
        )
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        box.setDefaultButton(QMessageBox.StandardButton.No)
        box.setToolTip(
            "Remove this categorization rule from the company database after you confirm. "
            "Consider File → Backup / probooks backup before bulk deletes."
        )
        tip_message_box_buttons(
            box,
            yes="Permanently remove this rule from the database.",
            no="Keep the rule.",
        )
        confirm = box.exec()
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
            message_box_critical_ok(
                self,
                "Export failed",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; check path, permissions, and disk space.",
            )
            return
        message_box_information_ok(
            self,
            "Export complete",
            f"Exported {n} rule(s) to:\n{escape_ampersand_for_qt(path)}",
            ok_tip="Close; open the CSV from the path shown.",
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
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Replace all rules?")
        box.setText(
            "Import will delete all existing categorization rules and replace them "
            "with the rows in this file.\n\nContinue?"
        )
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        box.setDefaultButton(QMessageBox.StandardButton.No)
        box.setToolTip(
            "Import deletes every existing rule and replaces them with the chosen CSV; confirm to continue. "
            "Use File → Backup / probooks backup first if you may need the old rules."
        )
        tip_message_box_buttons(
            box,
            yes="Delete all current rules and import from the chosen file.",
            no="Cancel; existing rules are unchanged.",
        )
        confirm = box.exec()
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            n = rules_engine.import_rules_replace(self._conn, path)
        except ValueError as exc:
            message_box_warning_ok(
                self,
                "Import rules",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; fix CSV columns or content and try again.",
            )
            return
        except OSError as exc:
            message_box_critical_ok(
                self,
                "Import failed",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; check the file path and permissions.",
            )
            return
        except Exception as exc:
            message_box_critical_ok(
                self,
                "Import failed",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; unexpected error during import — check logs or file format.",
            )
            return
        self._refresh()
        message_box_information_ok(
            self,
            "Import complete",
            f"Imported {n} rule(s) from:\n{escape_ampersand_for_qt(path)}",
            ok_tip="Close; rules list was replaced from the file.",
        )


class ARTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self.setToolTip(
            "Accounts receivable: customers, invoices, payments, PDF export, aging CSV; F5 refreshes lists."
        )
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        ar_new_cust = QPushButton("New customer")
        ar_new_cust.setToolTip("Create a new customer record.")
        ar_new_cust.clicked.connect(self._new_cust)
        row.addWidget(ar_new_cust)
        ar_edit_cust = QPushButton("Edit customer…")
        ar_edit_cust.setToolTip("Choose a customer and edit name, contact, and notes.")
        ar_edit_cust.clicked.connect(self._edit_cust)
        row.addWidget(ar_edit_cust)
        ar_new_inv = QPushButton("New invoice")
        ar_new_inv.setToolTip("Create a new invoice (add a customer first if the list is empty).")
        ar_new_inv.clicked.connect(self._new_inv)
        row.addWidget(ar_new_inv)
        ar_edit_inv = QPushButton("Edit selected invoice…")
        ar_edit_inv.setToolTip(
            "Edit the selected invoice. Double-click a row or press Enter for the same."
        )
        ar_edit_inv.clicked.connect(self._edit_inv)
        row.addWidget(ar_edit_inv)
        ar_record_pay = QPushButton("Record customer payment…")
        ar_record_pay.setToolTip("Record a payment and allocate amounts to open invoices.")
        ar_record_pay.clicked.connect(self._record_ar_payment)
        row.addWidget(ar_record_pay)
        ar_export_aging = QPushButton("Export AR aging CSV")
        ar_export_aging.setToolTip("Export accounts-receivable aging summary to CSV.")
        ar_export_aging.clicked.connect(self._export_aging)
        row.addWidget(ar_export_aging)
        ar_export_cust = QPushButton("Export customers CSV…")
        ar_export_cust.setToolTip("Export all customers to CSV.")
        ar_export_cust.clicked.connect(self._export_customers)
        row.addWidget(ar_export_cust)
        ar_export_inv = QPushButton("Export invoices CSV…")
        ar_export_inv.setToolTip("Export invoice headers to CSV.")
        ar_export_inv.clicked.connect(self._export_invoices)
        row.addWidget(ar_export_inv)
        ar_export_payments = QPushButton("Export AR payments CSV…")
        ar_export_payments.setToolTip("Export customer payment records to CSV.")
        ar_export_payments.clicked.connect(self._export_ar_payments)
        row.addWidget(ar_export_payments)
        ar_export_alloc = QPushButton("Export AR payment allocations CSV…")
        ar_export_alloc.setToolTip("Export how payments were applied to invoices.")
        ar_export_alloc.clicked.connect(self._export_ar_allocations)
        row.addWidget(ar_export_alloc)
        ar_save_pdf = QPushButton("Save invoice PDF…")
        ar_save_pdf.setToolTip("Save the selected invoice as a PDF (pick a row first).")
        ar_save_pdf.clicked.connect(self._save_pdf)
        row.addWidget(ar_save_pdf)
        row.addStretch()
        lay.addLayout(row)
        fil = QHBoxLayout()
        lbl_ar_inv_filter = QLabel("Filter:")
        lbl_ar_inv_filter.setToolTip(
            "Prompt for the invoice list filter; type in the field to the right (words must all match a row)."
        )
        fil.addWidget(lbl_ar_inv_filter)
        self._inv_filter = QLineEdit()
        _saved_ar_filt = QSettings().value(_AR_INVOICE_GRID_FILTER_KEY, "")
        if isinstance(_saved_ar_filt, str) and _saved_ar_filt:
            self._inv_filter.setText(_saved_ar_filt)
        self._inv_filter.setPlaceholderText(
            "Customer, invoice #, memo, dates, status, subtotal, tax, totals, id (words must all match)…"
        )
        self._inv_filter.setToolTip(
            "Narrow the invoice grid: every word you type must appear somewhere in the row’s "
            "visible text (see placeholder). The filter is saved and restored per company."
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
        self._tbl.setToolTip(
            "Open invoices (AR). Right-click for Keyboard shortcuts… (empty area OK). "
            "F5 refreshes when Business has focus."
        )
        lay.addWidget(self._tbl)
        self._ar_footer = QLabel()
        self._ar_footer.setStyleSheet("font-weight: bold;")
        self._ar_footer.setToolTip(
            "Footer summary for the invoice list (count and dollar totals; reflects the active filter)."
        )
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
        idx = self._tbl.indexAt(pos)
        m = QMenu(self)
        act_keys = m.addAction(
            "Keyboard shortcuts…",
            lambda: show_business_keyboard_shortcuts_dialog(self),
        )
        act_keys.setToolTip(
            "Same summary as Help → Business shortcuts… (F5, Invoices AR, payments, PDF)."
        )
        if not idx.isValid():
            m.exec(self._tbl.viewport().mapToGlobal(pos))
            return
        row = idx.row()
        if _table_row_entity_id(self._tbl, row) is None:
            m.exec(self._tbl.viewport().mapToGlobal(pos))
            return
        m.addSeparator()
        act_edit = m.addAction("Edit…", lambda r=row: (self._tbl.selectRow(r), self._edit_inv()))
        act_edit.setToolTip("Edit this invoice (not allowed when payments are applied).")
        act_pdf = m.addAction(
            "Save invoice PDF…", lambda r=row: (self._tbl.selectRow(r), self._save_pdf())
        )
        act_pdf.setToolTip("Export a PDF for this invoice (you choose the save path).")
        act_invno = m.addAction(
            "Copy invoice #",
            lambda r=row: QGuiApplication.clipboard().setText(
                table_cell_clipboard_text(self._tbl, r, 2).strip()
            ),
        )
        act_invno.setToolTip("Copy the invoice number cell to the clipboard.")
        act_copy = m.addAction("Copy row", lambda r=row: copy_table_row_as_tsv(self._tbl, r))
        act_copy.setToolTip(
            "Copy this invoice row as tab-separated text for pasting into a spreadsheet or editor."
        )
        m.exec(self._tbl.viewport().mapToGlobal(pos))

    def _save_pdf(self):
        r = self._tbl.currentRow()
        inv_id = _table_row_entity_id(self._tbl, r)
        if inv_id is None:
            message_box_information_ok(
                self,
                "PDF",
                "Select an invoice row.",
                ok_tip="Close; click an invoice in the grid, then Save invoice PDF again.",
            )
            return
        path, _ = QFileDialog.getSaveFileName(self, "Invoice PDF", "", "PDF (*.pdf)")
        if not path:
            return
        try:
            from desktop_app.invoice_pdf import save_invoice_pdf

            save_invoice_pdf(self._conn, inv_id, path)
        except Exception as exc:  # noqa: BLE001
            message_box_warning_ok(
                self,
                "PDF",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; fix the error shown, then try exporting again.",
            )
            return
        message_box_information_ok(
            self,
            "PDF",
            f"Saved to {escape_ampersand_for_qt(path)}",
            ok_tip="Close; open the PDF from the path shown.",
        )

    def _new_cust(self):
        d = QDialog(self)
        d.setWindowTitle("New customer")
        d.setToolTip("Create a customer record used for AR invoices, payments, and aging.")
        f = QFormLayout(d)
        ne = QLineEdit()
        ne.setToolTip("Customer display name (required).")
        em = QLineEdit()
        em.setToolTip("Contact email (optional).")
        ph = QLineEdit()
        ph.setToolTip("Phone number (optional).")
        ad = QPlainTextEdit()
        ad.setFixedHeight(56)
        ad.setToolTip("Mailing or service address (optional).")
        no = QPlainTextEdit()
        no.setFixedHeight(48)
        no.setToolTip("Internal notes about this customer (optional).")
        f.addRow("Name *", ne)
        f.addRow("Email", em)
        f.addRow("Phone", ph)
        f.addRow("Address", ad)
        f.addRow("Notes", no)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        _tip_dialog_ok_cancel(bb, "Add the customer with these details.")
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
        message_box_information_ok(
            self,
            "Done",
            "Customer added.",
            ok_tip="Close; the customer appears in lists and filters.",
        )
        self._refresh()

    def _edit_cust(self):
        custs = business.list_customers(self._conn)
        if not custs:
            message_box_information_ok(
                self,
                "Customers",
                "No customers to edit.",
                ok_tip="Close; use New customer first.",
            )
            return
        d = QDialog(self)
        d.setWindowTitle("Edit customer")
        d.setToolTip("Filter the list, pick a customer, then update name, contact fields, or notes.")
        f = QFormLayout(d)
        filt = QLineEdit()
        filt.setPlaceholderText("Filter by name, email, phone, address, notes, or id…")
        filt.setClearButtonEnabled(True)
        filt.setToolTip("Narrow the customer list; clear the field to show all customers again.")
        cb = QComboBox()
        cb.setToolTip("Choose the customer to edit.")
        ne = QLineEdit()
        ne.setToolTip("Customer display name (required).")
        em = QLineEdit()
        em.setToolTip("Contact email (optional).")
        ph = QLineEdit()
        ph.setToolTip("Phone number (optional).")
        ad = QPlainTextEdit()
        ad.setFixedHeight(56)
        ad.setToolTip("Mailing or service address (optional).")
        no = QPlainTextEdit()
        no.setFixedHeight(48)
        no.setToolTip("Internal notes about this customer (optional).")

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
        _tip_dialog_ok_cancel(bb, "Save changes to the selected customer.")
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        if not ne.text().strip():
            return
        cid = cb.currentData()
        if cid is None:
            message_box_warning_ok(
                self,
                "Customer",
                "No customer selected (try clearing the filter).",
                ok_tip="Close; pick a customer in the list or clear the filter.",
            )
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
            message_box_warning_ok(
                self,
                "Customer",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; fix the validation issue and try again.",
            )
            return
        self._refresh()

    def _new_inv(self):
        custs = business.list_customers(self._conn)
        if not custs:
            message_box_information_ok(
                self,
                "Customers",
                "Add a customer first.",
                ok_tip="Close; use New customer, then create the invoice.",
            )
            return
        d = QDialog(self)
        d.setWindowTitle("Invoice")
        d.setToolTip(
            "Create an invoice with header fields, one starter line, and tax percent for this customer."
        )
        f = QFormLayout(d)
        cust_filt = QLineEdit()
        cust_filt.setPlaceholderText("Filter customers by name, email, phone…")
        cust_filt.setClearButtonEnabled(True)
        cust_filt.setToolTip("Narrow the customer list; clear to show all again.")
        cb = QComboBox()
        cb.setToolTip("Customer for this invoice (required).")

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
        invno.setToolTip("Unique invoice number for this customer (required).")
        idate = QDateEdit()
        idate.setCalendarPopup(True)
        idate.setDisplayFormat("yyyy-MM-dd")
        idate.setDate(QDate.currentDate())
        idate.setToolTip("Invoice date.")
        due_e = QLineEdit()
        due_e.setToolTip("Due date as text if you track it (optional).")
        memo_e = QLineEdit()
        memo_e.setToolTip("Header memo on the invoice (optional).")
        rate = QDoubleSpinBox()
        rate.setRange(0, 9_999_999)
        rate.setDecimals(2)
        rate.setToolTip("Amount for the single starter line (Services × 1).")
        tax = QDoubleSpinBox()
        tax.setRange(0, 100)
        tax.setDecimals(2)
        tax.setValue(float(business.get_setting(self._conn, "default_tax_rate_pct", "0") or 0))
        tax.setToolTip("Tax percent applied to this new invoice.")
        f.addRow("Invoice # *", invno)
        f.addRow("Date", idate)
        f.addRow("Due date (optional)", due_e)
        f.addRow("Memo", memo_e)
        f.addRow("Line amount", rate)
        f.addRow("Tax %", tax)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        _tip_dialog_ok_cancel(bb, "Create the invoice with one starter line and these header fields.")
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        if not invno.text().strip():
            return
        cust_id = cb.currentData()
        if cust_id is None:
            message_box_warning_ok(
                self,
                "Invoice",
                "Select a customer (try clearing the filter).",
                ok_tip="Close; pick a customer or clear the customer filter.",
            )
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
            message_box_warning_ok(
                self,
                "Duplicate",
                "Invoice number already exists.",
                ok_tip="Close; choose a different invoice number for this customer.",
            )
            return
        _save_entity_combo(cb, _NEW_INVOICE_CUSTOMER_KEY)
        self._refresh()

    def _edit_inv(self):
        r = self._tbl.currentRow()
        inv_id = _table_row_entity_id(self._tbl, r)
        if inv_id is None:
            message_box_information_ok(
                self,
                "Invoice",
                "Select an invoice row.",
                ok_tip="Close; click an invoice, then Edit invoice again.",
            )
            return
        if business.invoice_has_payment_allocations(self._conn, inv_id):
            message_box_information_ok(
                self,
                "Invoice",
                "This invoice has payments applied and cannot be edited.",
                ok_tip="Close; void or adjust payments in AR before editing this invoice.",
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
        d.setToolTip(
            "Edit invoice header, customer, line items, and tax rate (not allowed when payments are applied)."
        )
        outer = QVBoxLayout(d)
        f = QFormLayout()
        inv_cust_id = int(inv["customer_id"])
        ensure_cust = frozenset({inv_cust_id})
        cust_filt = QLineEdit()
        cust_filt.setPlaceholderText("Filter customers (current invoice customer always listed)…")
        cust_filt.setClearButtonEnabled(True)
        cust_filt.setToolTip("Narrow the customer list; the invoice’s customer stays available.")
        cb = QComboBox()
        cb.setToolTip("Customer on this invoice.")

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
        invno.setToolTip("Unique invoice number (required).")
        idate = QDateEdit()
        idate.setCalendarPopup(True)
        idate.setDisplayFormat("yyyy-MM-dd")
        qd = QDate.fromString(inv["invoice_date"] or "", "yyyy-MM-dd")
        idate.setDate(qd if qd.isValid() else QDate.currentDate())
        idate.setToolTip("Invoice date.")
        due_e = QLineEdit(inv["due_date"] or "")
        due_e.setToolTip("Due date as text if you track it (optional).")
        memo_e = QLineEdit(inv["memo"] or "")
        memo_e.setToolTip("Header memo on the invoice (optional).")
        sub = float(inv["subtotal"] or 0)
        tax_amt = float(inv["tax_total"] or 0)
        tax_pct = (100.0 * tax_amt / sub) if sub > 0 else 0.0
        tax = QDoubleSpinBox()
        tax.setRange(0, 100)
        tax.setDecimals(4)
        tax.setValue(tax_pct)
        tax.setToolTip("Tax percent for this invoice (lines × rate; tax recomputed on save).")
        f.addRow("Customer", cb)
        f.addRow("Invoice # *", invno)
        f.addRow("Date", idate)
        f.addRow("Due date (optional)", due_e)
        f.addRow("Memo", memo_e)
        f.addRow("Tax %", tax)
        outer.addLayout(f)
        lbl_edit_inv_lines = QLabel("Line items (description, qty, rate)")
        lbl_edit_inv_lines.setToolTip(
            "Invoice lines below: edit description, quantity, and rate; use Add/Remove line as needed."
        )
        outer.addWidget(lbl_edit_inv_lines)
        line_tbl = QTableWidget()
        line_tbl.setToolTip(
            "Edit line description, quantity, and unit rate. Right-click a row to copy as TSV."
        )
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

        ar_inv_add_line = QPushButton("Add line")
        ar_inv_add_line.setToolTip("Add another line item row to this invoice.")
        ar_inv_add_line.clicked.connect(add_line)
        ar_inv_rm_line = QPushButton("Remove line")
        ar_inv_rm_line.setToolTip(
            "Remove the selected line, or the last line if none is selected (one line always remains)."
        )
        ar_inv_rm_line.clicked.connect(del_line)
        btn_row.addWidget(ar_inv_add_line)
        btn_row.addWidget(ar_inv_rm_line)
        btn_row.addStretch()
        outer.addLayout(btn_row)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        _tip_dialog_ok_cancel(bb, "Save invoice header, line items, and tax rate.")
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
                message_box_warning_ok(
                    self,
                    "Invoice",
                    "Invalid qty or rate on a line.",
                    ok_tip="Close; enter numeric qty and rate for each line.",
                )
                return
            if not desc and qv == 0 and rv == 0:
                continue
            lines_out.append({"description": desc or "Line", "qty": qv, "rate": rv})
        if not lines_out:
            message_box_warning_ok(
                self,
                "Invoice",
                "Add at least one line with an amount.",
                ok_tip="Close; ensure at least one line has qty × rate > 0.",
            )
            return
        new_cust = cb.currentData()
        if new_cust is None:
            message_box_warning_ok(
                self,
                "Invoice",
                "Select a customer (try clearing the filter).",
                ok_tip="Close; pick a customer or clear the customer filter.",
            )
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
            message_box_warning_ok(
                self,
                "Invoice",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; fix the issue described and save again.",
            )
            return
        except sqlite3.IntegrityError:
            message_box_warning_ok(
                self,
                "Duplicate",
                "Invoice number already exists.",
                ok_tip="Close; choose another invoice number.",
            )
            return
        self._refresh()

    def _record_ar_payment(self):
        custs = business.list_customers(self._conn)
        if not custs:
            message_box_information_ok(
                self,
                "AR payment",
                "Add a customer first.",
                ok_tip="Close; create a customer before recording payments.",
            )
            return
        d = QDialog(self)
        d.setWindowTitle("Record customer payment")
        d.setToolTip(
            "Enter payment details and allocate amounts to open invoices; Apply column must sum to the payment."
        )
        d.setMinimumWidth(540)
        outer = QVBoxLayout(d)
        form = QFormLayout()
        cust_filt = QLineEdit()
        cust_filt.setPlaceholderText("Filter customers by name, email, phone…")
        cust_filt.setClearButtonEnabled(True)
        cust_filt.setToolTip("Narrow the customer list; clear to show all again.")
        cust_cb = QComboBox()
        cust_cb.setToolTip("Customer who paid (open invoices load below).")
        form.addRow("Filter list", cust_filt)
        form.addRow("Customer", cust_cb)
        pdate = QDateEdit()
        pdate.setCalendarPopup(True)
        pdate.setDisplayFormat("yyyy-MM-dd")
        pdate.setDate(QDate.currentDate())
        pdate.setToolTip("Date the payment was received.")
        pay_amt = QDoubleSpinBox()
        pay_amt.setRange(0.01, 99_999_999.99)
        pay_amt.setDecimals(2)
        pay_amt.setToolTip("Total payment amount; sum of Apply column must match.")
        method_e = QLineEdit()
        method_e.setToolTip("e.g. Check, ACH, card (optional).")
        ref_e = QLineEdit()
        ref_e.setToolTip("Check number, confirmation id, or bank reference (optional).")
        memo_e = QLineEdit()
        memo_e.setToolTip("Note stored on the payment (optional).")
        bank_cb = QComboBox()
        bank_cb.setToolTip("Bank account where the deposit was recorded, if any.")
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
        lbl_ar_apply_hdr = QLabel("Apply to open invoices:")
        lbl_ar_apply_hdr.setToolTip(
            "Allocate this payment across unpaid invoices for the customer (table below)."
        )
        outer.addWidget(lbl_ar_apply_hdr)
        hint = QLabel('Sum of "Apply" must equal the payment amount.')
        hint.setStyleSheet("color: palette(mid);")
        hint.setToolTip(
            "The total in the Apply column must match the payment amount exactly (within penny rounding)."
        )
        outer.addWidget(hint)
        alloc_tbl = QTableWidget()
        alloc_tbl.setColumnCount(4)
        alloc_tbl.setHorizontalHeaderLabels(["Invoice #", "Date", "Balance", "Apply"])
        alloc_tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        alloc_tbl.setToolTip(
            "Open invoices for the selected customer. Enter Apply amounts; they must sum to the payment."
        )

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
        ar_pay_fill_old = QPushButton("Fill oldest first")
        ar_pay_fill_old.setToolTip(
            "Fill Apply from the oldest open invoice upward until the payment amount is used."
        )
        ar_pay_fill_old.clicked.connect(apply_oldest_first)
        auto_row.addWidget(ar_pay_fill_old)
        auto_row.addStretch()
        outer.addLayout(auto_row)
        _attach_table_copy_row_menu(alloc_tbl, d)
        outer.addWidget(alloc_tbl)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        _tip_dialog_ok_cancel(
            bb,
            "Record the payment and apply amounts to open invoices (totals must match).",
        )
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        outer.addWidget(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        cid = cust_cb.currentData()
        if cid is None:
            message_box_warning_ok(
                self,
                "AR payment",
                "Select a customer (try clearing the filter).",
                ok_tip="Close; pick a customer or clear the filter.",
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
            message_box_warning_ok(
                self,
                "AR payment",
                "Enter an amount in Apply for at least one invoice.",
                ok_tip="Close; type Apply amounts in the table for open invoices.",
            )
            return
        applied = round(sum(a for _, a in allocs), 2)
        if abs(applied - amt) > 0.02:
            message_box_warning_ok(
                self,
                "AR payment",
                f"Apply amounts ({applied:.2f}) must equal payment amount ({amt:.2f}).",
                ok_tip="Close; adjust Apply so the total matches the payment amount.",
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
        message_box_information_ok(
            self,
            "AR payment",
            "Payment recorded.",
            ok_tip="Close; allocations and balances are updated.",
        )

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
        message_box_information_ok(
            self,
            "Export",
            f"Wrote {escape_ampersand_for_qt(path)}\n(As of {as_of})",
            ok_tip="Close; open the aging CSV from the path shown.",
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
            message_box_critical_ok(
                self,
                "Export failed",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; check path, permissions, and disk space.",
            )
            return
        message_box_information_ok(
            self,
            "Export",
            f"Exported {n} customer(s) to {escape_ampersand_for_qt(path)}",
            ok_tip="Close; open the CSV from the path shown.",
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
            message_box_critical_ok(
                self,
                "Export failed",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; check path, permissions, and disk space.",
            )
            return
        message_box_information_ok(
            self,
            "Export",
            f"Exported {n} invoice(s) to {escape_ampersand_for_qt(path)}",
            ok_tip="Close; open the CSV from the path shown.",
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
            message_box_critical_ok(
                self,
                "Export failed",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; check path, permissions, and disk space.",
            )
            return
        except sqlite3.OperationalError as exc:
            message_box_critical_ok(
                self,
                "Export failed",
                escape_ampersand_for_qt(
                    str(exc)
                    + "\n\nRestart the app to apply the latest database upgrade."
                ),
                ok_tip="Close; restart ProBooks+ai after upgrades, then export again.",
            )
            return
        message_box_information_ok(
            self,
            "Export",
            f"Exported {n} payment(s) to {escape_ampersand_for_qt(path)}",
            ok_tip="Close; open the CSV from the path shown.",
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
            message_box_critical_ok(
                self,
                "Export failed",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; check path, permissions, and disk space.",
            )
            return
        message_box_information_ok(
            self,
            "Export",
            f"Exported {n} allocation row(s) to {escape_ampersand_for_qt(path)}",
            ok_tip="Close; open the CSV from the path shown.",
        )


class APTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self.setToolTip(
            "Accounts payable: vendors, bills, attachments, vendor payments, aging CSV; F5 refreshes lists."
        )
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        ap_new_v = QPushButton("New vendor")
        ap_new_v.setToolTip("Create a new vendor record.")
        ap_new_v.clicked.connect(self._new_v)
        row.addWidget(ap_new_v)
        ap_edit_v = QPushButton("Edit vendor…")
        ap_edit_v.setToolTip("Choose a vendor and edit name, contact, 1099 flag, and notes.")
        ap_edit_v.clicked.connect(self._edit_v)
        row.addWidget(ap_edit_v)
        ap_new_b = QPushButton("New bill")
        ap_new_b.setToolTip("Create a new bill (add a vendor first if the list is empty).")
        ap_new_b.clicked.connect(self._new_b)
        row.addWidget(ap_new_b)
        ap_edit_b = QPushButton("Edit selected bill…")
        ap_edit_b.setToolTip(
            "Edit the selected bill. Double-click a row or press Enter for the same."
        )
        ap_edit_b.clicked.connect(self._edit_b)
        row.addWidget(ap_edit_b)
        ap_record_pay = QPushButton("Record vendor payment…")
        ap_record_pay.setToolTip("Record a payment and allocate amounts to open bills.")
        ap_record_pay.clicked.connect(self._record_ap_payment)
        row.addWidget(ap_record_pay)
        ap_export_aging = QPushButton("Export AP aging CSV")
        ap_export_aging.setToolTip("Export accounts-payable aging summary to CSV.")
        ap_export_aging.clicked.connect(self._export_aging)
        row.addWidget(ap_export_aging)
        ap_export_vendors = QPushButton("Export vendors CSV…")
        ap_export_vendors.setToolTip("Export all vendors to CSV.")
        ap_export_vendors.clicked.connect(self._export_vendors)
        row.addWidget(ap_export_vendors)
        ap_export_bills = QPushButton("Export bills CSV…")
        ap_export_bills.setToolTip("Export bill headers to CSV.")
        ap_export_bills.clicked.connect(self._export_bills)
        row.addWidget(ap_export_bills)
        ap_export_payments = QPushButton("Export AP payments CSV…")
        ap_export_payments.setToolTip("Export vendor payment records to CSV.")
        ap_export_payments.clicked.connect(self._export_ap_payments)
        row.addWidget(ap_export_payments)
        ap_export_alloc = QPushButton("Export AP payment allocations CSV…")
        ap_export_alloc.setToolTip("Export how payments were applied to bills.")
        ap_export_alloc.clicked.connect(self._export_ap_allocations)
        row.addWidget(ap_export_alloc)
        row.addStretch()
        lay.addLayout(row)
        fil = QHBoxLayout()
        lbl_ap_bill_filter = QLabel("Filter:")
        lbl_ap_bill_filter.setToolTip(
            "Prompt for the bill list filter; type in the field to the right (words must all match a row)."
        )
        fil.addWidget(lbl_ap_bill_filter)
        self._bill_filter = QLineEdit()
        _saved_ap_filt = QSettings().value(_AP_BILL_GRID_FILTER_KEY, "")
        if isinstance(_saved_ap_filt, str) and _saved_ap_filt:
            self._bill_filter.setText(_saved_ap_filt)
        self._bill_filter.setPlaceholderText(
            "Vendor, vendor inv. #, memo, attachment path/filename, dates, status, id, amounts…"
        )
        self._bill_filter.setToolTip(
            "Narrow the bill grid: every word must appear somewhere in the row’s visible text "
            "(see placeholder). The filter is saved and restored per company."
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
        self._tbl.setToolTip(
            "Bills (AP). Right-click for Keyboard shortcuts… (empty area OK). "
            "F5 refreshes when Business has focus."
        )
        lay.addWidget(self._tbl)
        self._ap_footer = QLabel()
        self._ap_footer.setStyleSheet("font-weight: bold;")
        self._ap_footer.setToolTip(
            "Footer summary for the bill list (count and dollar totals; reflects the active filter)."
        )
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
        idx = self._tbl.indexAt(pos)
        m = QMenu(self)
        act_keys = m.addAction(
            "Keyboard shortcuts…",
            lambda: show_business_keyboard_shortcuts_dialog(self),
        )
        act_keys.setToolTip(
            "Same summary as Help → Business shortcuts… (F5, Bills AP, attachments, payments)."
        )
        if not idx.isValid():
            m.exec(self._tbl.viewport().mapToGlobal(pos))
            return
        row = idx.row()
        if _table_row_entity_id(self._tbl, row) is None:
            m.exec(self._tbl.viewport().mapToGlobal(pos))
            return
        m.addSeparator()
        act_edit = m.addAction("Edit…", lambda r=row: (self._tbl.selectRow(r), self._edit_b()))
        act_edit.setToolTip("Edit this bill (not allowed when AP payments are applied).")
        act_att = m.addAction(
            "Open attachment…",
            lambda r=row: self._open_bill_attachment(r),
        )
        act_att.setToolTip("Open the linked attachment file if a path is set on this bill.")
        act_copy = m.addAction("Copy row", lambda r=row: copy_table_row_as_tsv(self._tbl, r))
        act_copy.setToolTip(
            "Copy this bill row as tab-separated text for pasting into a spreadsheet or editor."
        )
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
        d.setToolTip("Create a vendor record used for AP bills, payments, and 1099-style flags.")
        f = QFormLayout(d)
        ne = QLineEdit()
        ne.setToolTip("Vendor display name (required).")
        em = QLineEdit()
        em.setToolTip("Contact email (optional).")
        ph = QLineEdit()
        ph.setToolTip("Phone number (optional).")
        ad = QPlainTextEdit()
        ad.setFixedHeight(56)
        ad.setToolTip("Mailing or remittance address (optional).")
        no = QPlainTextEdit()
        no.setFixedHeight(48)
        no.setToolTip("Internal notes about this vendor (optional).")
        irs = QCheckBox("1099 vendor")
        irs.setToolTip("Mark if this vendor should be included in 1099-style reporting.")
        f.addRow("Name *", ne)
        f.addRow("Email", em)
        f.addRow("Phone", ph)
        f.addRow("Address", ad)
        f.addRow("Notes", no)
        f.addRow("", irs)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        _tip_dialog_ok_cancel(bb, "Add the vendor with these details.")
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
            message_box_information_ok(
                self,
                "Vendors",
                "No vendors to edit.",
                ok_tip="Close; use New vendor first.",
            )
            return
        d = QDialog(self)
        d.setWindowTitle("Edit vendor")
        d.setToolTip("Filter the list, pick a vendor, then update name, contact fields, notes, or 1099 flag.")
        f = QFormLayout(d)
        filt = QLineEdit()
        filt.setPlaceholderText("Filter by name, email, phone, address, notes, 1099, or id…")
        filt.setClearButtonEnabled(True)
        filt.setToolTip("Narrow the vendor list; clear the field to show all vendors again.")
        cb = QComboBox()
        cb.setToolTip("Choose the vendor to edit.")
        ne = QLineEdit()
        ne.setToolTip("Vendor display name (required).")
        em = QLineEdit()
        em.setToolTip("Contact email (optional).")
        ph = QLineEdit()
        ph.setToolTip("Phone number (optional).")
        ad = QPlainTextEdit()
        ad.setFixedHeight(56)
        ad.setToolTip("Mailing or remittance address (optional).")
        no = QPlainTextEdit()
        no.setFixedHeight(48)
        no.setToolTip("Internal notes about this vendor (optional).")
        irs = QCheckBox("1099 vendor")
        irs.setToolTip("Mark if this vendor should be included in 1099-style reporting.")

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
        _tip_dialog_ok_cancel(bb, "Save changes to the selected vendor.")
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        if not ne.text().strip():
            return
        vid = cb.currentData()
        if vid is None:
            message_box_warning_ok(
                self,
                "Vendor",
                "No vendor selected (try clearing the filter).",
                ok_tip="Close; pick a vendor or clear the filter.",
            )
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
            message_box_warning_ok(
                self,
                "Vendor",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; fix the validation issue and try again.",
            )
            return
        self._refresh()

    def _new_b(self):
        vs = business.list_vendors(self._conn)
        if not vs:
            message_box_information_ok(
                self,
                "Vendors",
                "Add a vendor first.",
                ok_tip="Close; create a vendor before adding bills.",
            )
            return
        d = QDialog(self)
        d.setWindowTitle("New bill")
        d.setToolTip(
            "Enter vendor, amount, bill date, optional due date, memo, and attachment path for a new bill."
        )
        f = QFormLayout(d)
        vend_filt = QLineEdit()
        vend_filt.setPlaceholderText("Filter vendors by name, email, phone, 1099…")
        vend_filt.setClearButtonEnabled(True)
        vend_filt.setToolTip("Narrow the vendor list; clear to show all again.")
        cb = QComboBox()
        cb.setToolTip("Vendor for this bill (required).")

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
        vinv.setToolTip("Vendor’s invoice or reference number (optional).")
        amt = QDoubleSpinBox()
        amt.setRange(0, 9_999_999)
        amt.setDecimals(2)
        amt.setToolTip("Total bill amount (required).")
        bdt = QDateEdit()
        bdt.setCalendarPopup(True)
        bdt.setDisplayFormat("yyyy-MM-dd")
        bdt.setDate(QDate.currentDate())
        bdt.setToolTip("Bill date.")
        due_e = QLineEdit()
        due_e.setToolTip("Due date as text if you track it (optional).")
        memo_e = QLineEdit()
        memo_e.setToolTip("Memo on the bill (optional).")
        att = QLineEdit()
        att.setToolTip("Path to a linked file, or use Browse… (optional).")

        def browse_att():
            path, _ = QFileDialog.getOpenFileName(d, "Attachment", "", "All Files (*.*)")
            if path:
                att.setText(path)

        att_row = QHBoxLayout()
        att_row.addWidget(att)
        ap_bill_att_browse = QPushButton("Browse…")
        ap_bill_att_browse.setToolTip(
            "Choose a file to link as this bill's attachment (optional)."
        )
        ap_bill_att_browse.clicked.connect(browse_att)
        att_row.addWidget(ap_bill_att_browse)
        f.addRow("Vendor invoice #", vinv)
        f.addRow("Amount *", amt)
        f.addRow("Bill date", bdt)
        f.addRow("Due date (optional)", due_e)
        f.addRow("Memo", memo_e)
        f.addRow("Attachment path", att_row)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        _tip_dialog_ok_cancel(bb, "Create the bill with this vendor, amount, and dates.")
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        vid = cb.currentData()
        if vid is None:
            message_box_warning_ok(
                self,
                "Bill",
                "Select a vendor (try clearing the filter).",
                ok_tip="Close; pick a vendor or clear the vendor filter.",
            )
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
            message_box_information_ok(
                self,
                "Bill",
                "Select a bill row.",
                ok_tip="Close; click a bill, then Edit bill again.",
            )
            return
        if business.bill_has_payment_allocations(self._conn, bill_id):
            message_box_information_ok(
                self,
                "Bill",
                "This bill has payments applied and cannot be edited.",
                ok_tip="Close; adjust or void AP payments before editing this bill.",
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
        d.setToolTip(
            "Update vendor, amounts, dates, memo, or attachment (not allowed when AP payments are applied)."
        )
        f = QFormLayout(d)
        bill_vid = int(b["vendor_id"])
        ensure_v = frozenset({bill_vid})
        vend_filt = QLineEdit()
        vend_filt.setPlaceholderText("Filter vendors (current bill vendor always listed)…")
        vend_filt.setClearButtonEnabled(True)
        vend_filt.setToolTip("Narrow the vendor list; the bill’s vendor stays available.")
        cb = QComboBox()
        cb.setToolTip("Vendor on this bill.")

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
        vinv.setToolTip("Vendor’s invoice or reference number (optional).")
        amt = QDoubleSpinBox()
        amt.setRange(0, 9_999_999)
        amt.setDecimals(2)
        amt.setValue(float(b["total"] or 0))
        amt.setToolTip("Total bill amount (required).")
        bdt = QDateEdit()
        bdt.setCalendarPopup(True)
        bdt.setDisplayFormat("yyyy-MM-dd")
        qbd = QDate.fromString(b["bill_date"] or "", "yyyy-MM-dd")
        bdt.setDate(qbd if qbd.isValid() else QDate.currentDate())
        bdt.setToolTip("Bill date.")
        due_e = QLineEdit(b["due_date"] or "")
        due_e.setToolTip("Due date as text if you track it (optional).")
        memo_e = QLineEdit(b["memo"] or "")
        memo_e.setToolTip("Memo on the bill (optional).")
        att = QLineEdit(b["attachment_path"] or "")
        att.setToolTip("Path to a linked file, or use Browse… (optional).")

        def browse_att():
            path, _ = QFileDialog.getOpenFileName(d, "Attachment", "", "All Files (*.*)")
            if path:
                att.setText(path)

        att_row = QHBoxLayout()
        att_row.addWidget(att)
        ap_bill_att_browse = QPushButton("Browse…")
        ap_bill_att_browse.setToolTip(
            "Choose a file to link as this bill's attachment (optional)."
        )
        ap_bill_att_browse.clicked.connect(browse_att)
        att_row.addWidget(ap_bill_att_browse)
        f.addRow("Vendor invoice #", vinv)
        f.addRow("Amount *", amt)
        f.addRow("Bill date", bdt)
        f.addRow("Due date (optional)", due_e)
        f.addRow("Memo", memo_e)
        f.addRow("Attachment path", att_row)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        _tip_dialog_ok_cancel(bb, "Save changes to this bill.")
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        new_vid = cb.currentData()
        if new_vid is None:
            message_box_warning_ok(
                self,
                "Bill",
                "Select a vendor (try clearing the filter).",
                ok_tip="Close; pick a vendor or clear the vendor filter.",
            )
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
            message_box_warning_ok(
                self,
                "Bill",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; fix the issue shown and save again.",
            )
            return
        self._refresh()

    def _record_ap_payment(self):
        vs = business.list_vendors(self._conn)
        if not vs:
            message_box_information_ok(
                self,
                "AP payment",
                "Add a vendor first.",
                ok_tip="Close; create a vendor before recording vendor payments.",
            )
            return
        d = QDialog(self)
        d.setWindowTitle("Record vendor payment")
        d.setToolTip(
            "Enter payment details and allocate amounts to open bills; Apply column must sum to the payment."
        )
        d.setMinimumWidth(540)
        outer = QVBoxLayout(d)
        form = QFormLayout()
        vend_filt = QLineEdit()
        vend_filt.setPlaceholderText("Filter vendors by name, email, phone, 1099…")
        vend_filt.setClearButtonEnabled(True)
        vend_filt.setToolTip("Narrow the vendor list; clear to show all again.")
        vend_cb = QComboBox()
        vend_cb.setToolTip("Vendor you paid (open bills load below).")
        form.addRow("Filter list", vend_filt)
        form.addRow("Vendor", vend_cb)
        pdate = QDateEdit()
        pdate.setCalendarPopup(True)
        pdate.setDisplayFormat("yyyy-MM-dd")
        pdate.setDate(QDate.currentDate())
        pdate.setToolTip("Date the payment was made.")
        pay_amt = QDoubleSpinBox()
        pay_amt.setRange(0.01, 99_999_999.99)
        pay_amt.setDecimals(2)
        pay_amt.setToolTip("Total payment amount; sum of Apply column must match.")
        method_e = QLineEdit()
        method_e.setToolTip("e.g. Check, ACH, card (optional).")
        ref_e = QLineEdit()
        ref_e.setToolTip("Check number, confirmation id, or bank reference (optional).")
        memo_e = QLineEdit()
        memo_e.setToolTip("Note stored on the payment (optional).")
        bank_cb = QComboBox()
        bank_cb.setToolTip("Bank account this payment cleared from, if any.")
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
        lbl_ap_apply_hdr = QLabel("Apply to open bills:")
        lbl_ap_apply_hdr.setToolTip(
            "Allocate this payment across unpaid bills for the vendor (table below)."
        )
        outer.addWidget(lbl_ap_apply_hdr)
        hint = QLabel('Sum of "Apply" must equal the payment amount.')
        hint.setStyleSheet("color: palette(mid);")
        hint.setToolTip(
            "The total in the Apply column must match the payment amount exactly (within penny rounding)."
        )
        outer.addWidget(hint)
        alloc_tbl = QTableWidget()
        alloc_tbl.setColumnCount(4)
        alloc_tbl.setHorizontalHeaderLabels(["Vendor inv. #", "Date", "Balance", "Apply"])
        alloc_tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        alloc_tbl.setToolTip(
            "Open bills for the selected vendor. Enter Apply amounts; they must sum to the payment."
        )

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
        ap_pay_fill_old = QPushButton("Fill oldest first")
        ap_pay_fill_old.setToolTip(
            "Fill Apply from the oldest open bill upward until the payment amount is used."
        )
        ap_pay_fill_old.clicked.connect(apply_oldest_first_ap)
        auto_row.addWidget(ap_pay_fill_old)
        auto_row.addStretch()
        outer.addLayout(auto_row)
        _attach_table_copy_row_menu(alloc_tbl, d)
        outer.addWidget(alloc_tbl)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        _tip_dialog_ok_cancel(
            bb,
            "Record the payment and apply amounts to open bills (totals must match).",
        )
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        outer.addWidget(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        vid = vend_cb.currentData()
        if vid is None:
            message_box_warning_ok(
                self,
                "AP payment",
                "Select a vendor (try clearing the filter).",
                ok_tip="Close; pick a vendor or clear the filter.",
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
            message_box_warning_ok(
                self,
                "AP payment",
                "Enter an amount in Apply for at least one bill.",
                ok_tip="Close; enter Apply amounts for open bills.",
            )
            return
        applied = round(sum(a for _, a in allocs), 2)
        if abs(applied - amt) > 0.02:
            message_box_warning_ok(
                self,
                "AP payment",
                f"Apply amounts ({applied:.2f}) must equal payment amount ({amt:.2f}).",
                ok_tip="Close; adjust Apply so the total matches the payment amount.",
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
        message_box_information_ok(
            self,
            "AP payment",
            "Payment recorded.",
            ok_tip="Close; bill balances and allocations are updated.",
        )

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
        message_box_information_ok(
            self,
            "Export",
            f"Wrote {escape_ampersand_for_qt(path)}\n(As of {as_of})",
            ok_tip="Close; open the AP aging CSV from the path shown.",
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
            message_box_critical_ok(
                self,
                "Export failed",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; check path, permissions, and disk space.",
            )
            return
        message_box_information_ok(
            self,
            "Export",
            f"Exported {n} vendor(s) to {escape_ampersand_for_qt(path)}",
            ok_tip="Close; open the CSV from the path shown.",
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
            message_box_critical_ok(
                self,
                "Export failed",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; check path, permissions, and disk space.",
            )
            return
        message_box_information_ok(
            self,
            "Export",
            f"Exported {n} bill(s) to {escape_ampersand_for_qt(path)}",
            ok_tip="Close; open the CSV from the path shown.",
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
            message_box_critical_ok(
                self,
                "Export failed",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; check path, permissions, and disk space.",
            )
            return
        message_box_information_ok(
            self,
            "Export",
            f"Exported {n} payment(s) to {escape_ampersand_for_qt(path)}",
            ok_tip="Close; open the CSV from the path shown.",
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
            message_box_critical_ok(
                self,
                "Export failed",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; check path, permissions, and disk space.",
            )
            return
        message_box_information_ok(
            self,
            "Export",
            f"Exported {n} allocation row(s) to {escape_ampersand_for_qt(path)}",
            ok_tip="Close; open the CSV from the path shown.",
        )


class PayrollTaxTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self.setToolTip(
            "Payroll: employees, pay runs, tax codes and tax lines, GL posting, tax CSV export (F5 refreshes the runs grid)."
        )
        lay = QVBoxLayout(self)
        row1 = QHBoxLayout()
        pt_new_emp = QPushButton("New employee")
        pt_new_emp.setToolTip("Add an employee record for payroll runs.")
        pt_new_emp.clicked.connect(self._new_emp)
        row1.addWidget(pt_new_emp)
        pt_new_run = QPushButton("New pay run")
        pt_new_run.setToolTip("Create a new pay run row for an employee and pay date.")
        pt_new_run.clicked.connect(self._new_run)
        row1.addWidget(pt_new_run)
        pt_post_gl = QPushButton("Post selected run to GL…")
        pt_post_gl.setToolTip("Post the selected pay run to the general ledger (journal entry).")
        pt_post_gl.clicked.connect(self._post_gl)
        row1.addWidget(pt_post_gl)
        row1.addStretch()
        lay.addLayout(row1)
        row2 = QHBoxLayout()
        pt_tax_codes = QPushButton("Tax codes…")
        pt_tax_codes.setToolTip("View and add payroll tax codes used on runs and reports.")
        pt_tax_codes.clicked.connect(self._tax_codes)
        row2.addWidget(pt_tax_codes)
        pt_run_taxes = QPushButton("Tax lines for run…")
        pt_run_taxes.setToolTip(
            "Edit employee vs employer tax amounts for the selected pay run."
        )
        pt_run_taxes.clicked.connect(self._edit_run_taxes)
        row2.addWidget(pt_run_taxes)
        pt_export_tax = QPushButton("Export tax report CSV…")
        pt_export_tax.setToolTip("Export payroll tax lines for a date range to CSV.")
        pt_export_tax.clicked.connect(self._export_tax_report)
        row2.addWidget(pt_export_tax)
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
        self._tbl.setToolTip(
            "Pay runs by employee. Right-click for Keyboard shortcuts… (empty area OK). "
            "F5 refreshes when Business has focus."
        )
        lay.addWidget(self._tbl)
        pt_grid_tip = QLabel(
            "Double-click a run or use Tax lines for run… to edit withholding splits. "
            "Post selected run to GL… creates a journal entry. F5 refreshes when Business has focus."
        )
        pt_grid_tip.setWordWrap(True)
        pt_grid_tip.setStyleSheet("color: #A0A0B0; font-size: 11px;")
        pt_grid_tip.setToolTip(
            "Payroll toolbar summary: tax codes dialog, tax line editor, CSV export, and GL posting."
        )
        lay.addWidget(pt_grid_tip)
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
            message_box_warning_ok(
                self,
                "Payroll taxes",
                "Tax tables are missing. Restart the app or open a company file "
                "that has been upgraded to the latest schema.",
                ok_tip="Close; restart or open an upgraded company .db; File → Backup / probooks backup first if the file has data you need.",
            )
            return
        d = QDialog(self)
        d.setWindowTitle("Payroll tax codes")
        d.setToolTip(
            "Review company payroll tax codes; add a code or close. Right-click the grid to copy a row."
        )
        v = QVBoxLayout(d)
        tbl = QTableWidget()
        tbl.setColumnCount(4)
        tbl.setHorizontalHeaderLabels(["Code", "Name", "Jurisdiction", "Sort"])
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        tbl.setToolTip("Company payroll tax codes. Right-click a row to copy as TSV.")
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
        pt_tc_add = QPushButton("Add code")
        pt_tc_add.setToolTip("Add a new payroll tax code to this list.")
        pt_tc_add.clicked.connect(lambda: self._add_tax_code(d, tbl))
        btn_row.addWidget(pt_tc_add)
        btn_row.addStretch()
        pt_tc_close = QPushButton("Close")
        pt_tc_close.setToolTip("Close the tax codes dialog.")
        pt_tc_close.clicked.connect(d.accept)
        btn_row.addWidget(pt_tc_close)
        v.addLayout(btn_row)
        d.exec()

    def _add_tax_code(self, parent_dlg: QDialog, tbl: QTableWidget):
        d = QDialog(parent_dlg)
        d.setWindowTitle("New tax code")
        d.setToolTip("Define a short code, name, optional jurisdiction, and sort order for payroll taxes.")
        f = QFormLayout(d)
        code = QLineEdit()
        code.setToolTip("Short code used in payroll tax lines and exports (required).")
        name = QLineEdit()
        name.setToolTip("Full name shown in dialogs and reports (required).")
        jur = QLineEdit()
        jur.setToolTip("State, local, or other jurisdiction label (optional).")
        so = QSpinBox()
        so.setRange(-999, 9999)
        so.setValue(100)
        so.setToolTip("Sort order when listing tax codes (lower first).")
        f.addRow("Code *", code)
        f.addRow("Name *", name)
        f.addRow("Jurisdiction", jur)
        f.addRow("Sort order", so)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        _tip_dialog_ok_cancel(bb, "Add this payroll tax code to the company list.")
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
            message_box_warning_ok(
                self,
                "Payroll taxes",
                "That code already exists.",
                ok_tip="Close; choose a unique tax code.",
            )
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
            message_box_information_ok(
                self,
                "Payroll taxes",
                "Select a pay run row.",
                ok_tip="Close; click a run in the grid, then Tax lines for run again.",
            )
            return
        try:
            items = business.list_payroll_tax_items(self._conn, active_only=True)
        except sqlite3.OperationalError:
            message_box_warning_ok(
                self,
                "Payroll taxes",
                "Tax tables are missing.",
                ok_tip="Close; upgrade schema or restart the app.",
            )
            return
        if not items:
            message_box_information_ok(
                self,
                "Payroll taxes",
                "Add tax codes first.",
                ok_tip="Close; use Tax codes to add at least one active code.",
            )
            return
        existing = {
            row["tax_item_id"]: row
            for row in business.list_payroll_run_tax_lines(self._conn, run_id)
        }
        d = QDialog(self)
        d.setWindowTitle(f"Payroll tax lines — run #{run_id}")
        d.setToolTip(
            "Enter employee and employer amounts per tax code for this pay run; saved lines feed tax CSV export."
        )
        d.setMinimumWidth(520)
        v = QVBoxLayout(d)
        lbl_pt_run_tax_intro = QLabel(
            "Enter employee vs employer portions manually (Phase 16 placeholder). "
            "Totals roll into the tax report CSV."
        )
        lbl_pt_run_tax_intro.setWordWrap(True)
        lbl_pt_run_tax_intro.setToolTip(
            "Placeholder workflow: enter tax amounts per code for this pay run; saved amounts export in tax CSV."
        )
        v.addWidget(lbl_pt_run_tax_intro)
        tbl = QTableWidget(len(items), 4)
        tbl.setHorizontalHeaderLabels(["Code", "Name", "Employee $", "Employer $"])
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        tbl.setToolTip(
            "Employee and employer amounts per tax code for this run. Right-click to copy a row as TSV."
        )
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
        _tip_dialog_save_cancel(
            bb, "Save employee and employer tax amounts for this pay run."
        )
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
        message_box_information_ok(
            self,
            "Payroll taxes",
            "Tax lines saved.",
            ok_tip="Close; amounts are stored on this pay run.",
        )

    def _on_payroll_run_double_clicked(self, row: int, _col: int) -> None:
        if row < 0:
            return
        self._tbl.selectRow(row)
        self._edit_run_taxes()

    def _on_payroll_run_context_menu(self, pos) -> None:
        idx = self._tbl.indexAt(pos)
        m = QMenu(self)
        act_keys = m.addAction(
            "Keyboard shortcuts…",
            lambda: show_business_keyboard_shortcuts_dialog(self),
        )
        act_keys.setToolTip(
            "Same summary as Help → Business shortcuts… (F5, Payroll grid, tax lines, GL post)."
        )
        if not idx.isValid():
            m.exec(self._tbl.viewport().mapToGlobal(pos))
            return
        row = idx.row()
        if _payroll_run_id_at_row(self._tbl, row) is None:
            m.exec(self._tbl.viewport().mapToGlobal(pos))
            return
        m.addSeparator()
        act_tax = m.addAction(
            "Tax lines for run…",
            lambda r=row: (self._tbl.selectRow(r), self._edit_run_taxes()),
        )
        act_tax.setToolTip("Edit employee and employer payroll tax amounts for this pay run.")
        act_gl = m.addAction(
            "Post selected run to GL…",
            lambda r=row: (self._tbl.selectRow(r), self._post_gl()),
        )
        act_gl.setToolTip("Post this pay run to the general ledger (choose wage, cash, and liability accounts).")
        act_copy = m.addAction("Copy row", lambda r=row: copy_table_row_as_tsv(self._tbl, r))
        act_copy.setToolTip(
            "Copy this pay run row as tab-separated text for pasting into a spreadsheet or editor."
        )
        m.exec(self._tbl.viewport().mapToGlobal(pos))

    def _export_tax_report(self):
        d = QDialog(self)
        d.setWindowTitle("Payroll tax report")
        d.setToolTip(
            "Choose pay dates from/to, then pick a CSV path to export summed payroll tax amounts."
        )
        f = QFormLayout(d)
        s = QDateEdit()
        s.setCalendarPopup(True)
        s.setDisplayFormat("yyyy-MM-dd")
        s.setToolTip("Include pay runs with pay date on or after this day.")
        e = QDateEdit()
        e.setCalendarPopup(True)
        e.setDisplayFormat("yyyy-MM-dd")
        e.setDate(QDate.currentDate())
        e.setToolTip("Include pay runs with pay date on or before this day.")
        s.setDate(QDate.currentDate().addMonths(-1))
        f.addRow("From pay date", s)
        f.addRow("To pay date", e)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        _tip_dialog_ok_cancel(
            bb, "Continue to choose a file and export payroll tax totals for this date range."
        )
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        start = s.date().toString("yyyy-MM-dd")
        end = e.date().toString("yyyy-MM-dd")
        if start > end:
            message_box_warning_ok(
                self,
                "Payroll taxes",
                "Start date must be on or before end date.",
                ok_tip="Close; swap or adjust the from/to pay dates.",
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Payroll tax totals", "", "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return
        try:
            rows = business.payroll_tax_totals_by_range(self._conn, start, end)
        except sqlite3.OperationalError:
            message_box_warning_ok(
                self,
                "Payroll taxes",
                "Tax tables are missing.",
                ok_tip="Close; upgrade schema or restart the app.",
            )
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
        message_box_information_ok(
            self,
            "Payroll taxes",
            f"Wrote {escape_ampersand_for_qt(path)}",
            ok_tip="Close; open the payroll tax CSV from the path shown.",
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
            message_box_information_ok(
                self,
                "GL",
                "Select a pay run row.",
                ok_tip="Close; select a run, then Post selected run to GL again.",
            )
            return
        run = next((x for x in self._run_rows if int(x["id"]) == rid), None)
        if run is None:
            self._refresh()
            message_box_information_ok(
                self,
                "GL",
                "Pay run not found; list was refreshed.",
                ok_tip="Close; pick a current run from the refreshed list.",
            )
            return
        if run.get("journal_entry_id"):
            message_box_information_ok(
                self,
                "GL",
                "This run already has a journal_entry_id.",
                ok_tip="Close; this payroll run is already posted to the journal.",
            )
            return
        from PySide6.QtWidgets import QComboBox

        from probooksai.coa_db import COADatabase
        from probooksai.gl import GLDatabase

        cdb = COADatabase(self._conn)
        gl = GLDatabase(self._conn)
        d = QDialog(self)
        d.setWindowTitle("Post payroll to GL")
        d.setToolTip(
            "Map wage expense, cash/bank, and withholdings liability for posting this pay run to the journal."
        )
        f = QFormLayout(d)
        exp = QComboBox()
        exp.setEditable(True)
        exp.setToolTip("Expense account debited for gross wages on this pay run.")
        cash = QComboBox()
        cash.setEditable(True)
        cash.setToolTip("Cash or bank account credited for net pay.")
        liab = QComboBox()
        liab.setEditable(True)
        liab.setToolTip("Liability account credited for withholdings when deductions are greater than zero.")
        for s in cdb.display_list():
            exp.addItem(escape_ampersand_for_qt(s), s)
            cash.addItem(escape_ampersand_for_qt(s), s)
            liab.addItem(escape_ampersand_for_qt(s), s)
        f.addRow("Wage expense (debit gross)", exp)
        f.addRow("Cash / bank (credit net pay)", cash)
        f.addRow("Withholdings liability (credit deductions)", liab)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        _tip_dialog_ok_cancel(bb, "Post this pay run to the general ledger with these accounts.")
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
                message_box_warning_ok(
                    self,
                    "GL",
                    "Enter a liability account for payroll deductions.",
                    ok_tip="Close; choose withholdings liability when deductions are > 0.",
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
            message_box_warning_ok(
                self,
                "GL",
                escape_ampersand_for_qt(str(exc)),
                ok_tip="Close; fix accounts or balances and try posting again.",
            )
            return
        self._conn.execute(
            "UPDATE payroll_runs SET journal_entry_id = ? WHERE id = ?",
            (eid, run["id"]),
        )
        self._conn.commit()
        message_box_information_ok(
            self,
            "GL",
            f"Posted journal entry #{eid}.",
            ok_tip="Close; view this entry on the Journal tab.",
        )
        self._refresh()

    def _new_emp(self):
        d = QDialog(self)
        d.setWindowTitle("New employee")
        d.setToolTip("Add an employee display name for new pay runs and payroll reports.")
        f = QFormLayout(d)
        ne = QLineEdit()
        ne.setToolTip("Employee name as it should appear on pay runs and exports.")
        f.addRow("Name", ne)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        _tip_dialog_ok_cancel(bb, "Add the employee with this display name.")
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
            message_box_information_ok(
                self,
                "Payroll",
                "Add an employee first.",
                ok_tip="Close; use New employee, then create a pay run.",
            )
            return
        from PySide6.QtWidgets import QComboBox

        d = QDialog(self)
        d.setWindowTitle("New pay run")
        d.setToolTip(
            "Create a pay run: pick employee, gross, deductions, and pay date (net = gross − deductions)."
        )
        f = QFormLayout(d)
        cb = QComboBox()
        for e in emps:
            cb.addItem(escape_ampersand_for_qt(e["name"] or ""), e["id"])
        cb.setToolTip("Employee for this pay run.")
        gross = QDoubleSpinBox()
        gross.setRange(0, 9_999_999)
        gross.setDecimals(2)
        gross.setToolTip("Gross pay before deductions.")
        ded = QDoubleSpinBox()
        ded.setRange(0, 9_999_999)
        ded.setDecimals(2)
        ded.setToolTip("Total deductions and withholdings (net = gross − deductions).")
        pd = QDateEdit()
        pd.setCalendarPopup(True)
        pd.setDisplayFormat("yyyy-MM-dd")
        pd.setDate(QDate.currentDate())
        pd.setToolTip("Check or pay date for this run.")
        f.addRow("Employee", cb)
        f.addRow("Gross", gross)
        f.addRow("Deductions", ded)
        f.addRow("Pay date", pd)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        _tip_dialog_ok_cancel(bb, "Create this pay run with gross, deductions, and pay date.")
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
        self.setToolTip(
            "Default sales tax name and rate for new invoices; save or Ctrl+S, export sales tax summary CSV (settings-only, no F5 list)."
        )
        root = QVBoxLayout(self)
        lay = QFormLayout()
        self._tax_name = QLineEdit()
        self._tax_name.setText(
            business.get_setting(self._conn, "default_tax_name", "Sales tax")
            or "Sales tax"
        )
        self._tax_name.setToolTip(
            "Label on new invoices and in sales tax export headers (e.g. Sales tax, GST)."
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
        self._rate.setToolTip(
            "Default percentage for tax on new invoices (saved with Save settings or Ctrl+S)."
        )
        lay.addRow("Default sales tax % (invoices)", self._rate)
        root.addLayout(lay)
        ts_save = QPushButton("Save settings")
        ts_save.setToolTip(
            "Save default tax name and rate for new invoices (Ctrl+S does the same)."
        )
        ts_save.clicked.connect(self._save)
        root.addWidget(ts_save)
        ts_export_csv = QPushButton("Export sales tax summary CSV\u2026")
        ts_export_csv.setToolTip(
            "Choose an invoice date range and export sales tax detail to CSV."
        )
        ts_export_csv.clicked.connect(self._export_sales_tax_csv)
        root.addWidget(ts_export_csv)
        ts_tip = QLabel(
            "Ctrl+S saves default tax name and rate (same as Save settings). "
            "Other Business sub-tabs use F5 to refresh lists; Tax % is settings-only. "
            "Help → Business shortcuts… for details."
        )
        ts_tip.setWordWrap(True)
        ts_tip.setStyleSheet("color: #A0A0B0; font-size: 11px;")
        ts_tip.setToolTip(
            "These defaults apply to new invoices; change tax % when editing an invoice if needed."
        )
        root.addWidget(ts_tip)
        save_sc = QShortcut(QKeySequence(QKeySequence.StandardKey.Save), self)
        save_sc.setContext(Qt.WidgetWithChildrenShortcut)
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
        message_box_information_ok(
            self,
            "Settings",
            "Saved.",
            ok_tip="Close; defaults apply to new invoices.",
        )

    def _export_sales_tax_csv(self):
        d = QDialog(self)
        d.setWindowTitle("Sales tax summary")
        d.setToolTip(
            "Choose invoice dates from/to, then pick a CSV path to export sales tax detail for that range."
        )
        f = QFormLayout(d)
        s = QDateEdit()
        s.setCalendarPopup(True)
        s.setDisplayFormat("yyyy-MM-dd")
        s.setToolTip("Include invoices dated on or after this day.")
        e = QDateEdit()
        e.setCalendarPopup(True)
        e.setDisplayFormat("yyyy-MM-dd")
        e.setDate(QDate.currentDate())
        e.setToolTip("Include invoices dated on or before this day.")
        s.setDate(QDate.currentDate().addMonths(-1))
        f.addRow("From invoice date", s)
        f.addRow("To invoice date", e)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        _tip_dialog_ok_cancel(
            bb, "Continue to choose a file and export sales tax detail for this date range."
        )
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        start = s.date().toString("yyyy-MM-dd")
        end = e.date().toString("yyyy-MM-dd")
        if start > end:
            message_box_warning_ok(
                self,
                "Sales tax",
                "Start date must be on or before end date.",
                ok_tip="Close; adjust the invoice date range.",
            )
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
        message_box_information_ok(
            self,
            "Sales tax",
            f"Wrote {escape_ampersand_for_qt(path)}",
            ok_tip="Close; open the sales tax summary CSV from the path shown.",
        )


def _business_keyboard_shortcuts_help_text() -> str:
    """Plain text for **Help → Business shortcuts…** (aligned with **F5** / **Tax %** **Save**)."""
    return (
        "These shortcuts apply when the Business tab or its controls have focus:\n\n"
        "F5 — Refresh the current sub-tab list (Rules, Invoices, Bills, Payroll). "
        "Tax % has no list to reload.\n\n"
        "On Tax % (settings):\n"
        "Ctrl+S — Save default tax name and rate (standard Save shortcut)\n\n"
        "Right-click the Rules, Invoices, Bills, or Payroll grid (including empty area) "
        "for Keyboard shortcuts… (same as this dialog).\n\n"
        "Business modal dialogs with a copyable grid (payment apply tables, tax lines, etc.): "
        "right-click (including empty area) for Keyboard shortcuts… (same as this dialog).\n\n"
        "Document Intake:\n"
        "Help → Document intake shortcuts… (includes File → Backup / Restore via probooks.backup).\n\n"
        "COA, Journal, Reports, Audit:\n"
        "Help → More tab shortcuts (F5)…\n\n"
        "Other tabs:\n"
        "Help → Bank import shortcuts…\n"
        "Help → Bank register keyboard shortcuts…\n"
    )


def show_business_keyboard_shortcuts_dialog(parent: QWidget) -> None:
    message_box_information_ok(
        parent,
        "Business shortcuts",
        _business_keyboard_shortcuts_help_text(),
        ok_tip="Close; shortcuts apply when the Business hub has focus. "
        "Company .db: File → Backup / Restore (probooks.backup).",
    )


class BusinessHub(QWidget):
    """Nested tabs for rules, AR, AP, payroll, tax."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.setToolTip(
            "Business hub: Rules, AR invoices, AP bills, Payroll, and default Tax % (F5 refreshes the active list sub-tab). "
            "Same company SQLite database as other main tabs; File → Backup / Restore (probooks.backup)."
        )
        self._business_subtabs = QTabWidget()
        self._business_subtabs.setToolTip(
            "Switch between Rules, Invoices (AR), Bills (AP), Payroll, and Tax % "
            "(hover each sub-tab for a summary; F5 refreshes list subtabs). "
            "All sub-tabs share the open company .db (File → Backup / probooks backup)."
        )
        self._business_subtabs.addTab(RulesTab(conn), "Rules")
        self._business_subtabs.addTab(ARTab(conn), "Invoices (AR)")
        self._business_subtabs.addTab(APTab(conn), "Bills (AP)")
        self._business_subtabs.addTab(PayrollTaxTab(conn), "Payroll")
        self._business_subtabs.addTab(TaxSettingsTab(conn), "Tax %")
        bar = self._business_subtabs.tabBar()
        bar.setTabToolTip(
            0,
            "Description-based rules that suggest a COA when importing or categorizing transactions.",
        )
        bar.setTabToolTip(
            1,
            "Customers, invoices, PDF export, and customer payments (accounts receivable).",
        )
        bar.setTabToolTip(
            2,
            "Vendors, bills, attachments, and vendor payments (accounts payable).",
        )
        bar.setTabToolTip(
            3,
            "Employees, pay runs, payroll tax lines, and posting pay runs to the GL.",
        )
        bar.setTabToolTip(
            4,
            "Default sales tax name and rate for new invoices; export sales tax summary CSV.",
        )
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
        tip = QLabel(
            "F5 refreshes the current sub-tab when it has a list (Rules, Invoices, Bills, Payroll). "
            "Tax % is settings-only. Help → Business shortcuts… for details; other main tabs also use F5."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #A0A0B0; font-size: 11px;")
        tip.setToolTip(
            "F5 refreshes the active sub-tab list when available; see Help → Business shortcuts…."
        )
        lay.addWidget(tip)

        sc_business_f5 = QShortcut(QKeySequence("F5"), self)
        sc_business_f5.setContext(Qt.WidgetWithChildrenShortcut)
        sc_business_f5.activated.connect(self._refresh_current_subtab)

    def _refresh_current_subtab(self) -> None:
        w = self._business_subtabs.currentWidget()
        if w is None:
            return
        fn = getattr(w, "_refresh", None)
        if callable(fn):
            fn()

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
