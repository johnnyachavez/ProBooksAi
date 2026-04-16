"""Rules, AR/AP, payroll, and tax settings (roadmap phases 6, 8–16).

**Business** hub (**F5**): refreshes the active sub-tab list when it defines
``_refresh`` (Rules, Payroll). **Tax %** and **Company** are settings-only. Full AR/AP grids live on the top-level **Customers** / **Vendors** tabs.
Invoice print/PDF is only from the **Invoice** workflow tab (``invoice_screen``), not AR list toolbars.
The **BusinessHub** root **QWidget** has a hover hint; the nested **QTabWidget** strip has a **setToolTip** for switching subtabs.
Each **sub-tab** on the hub bar has a **setTabToolTip** summary (Rules, Payroll, Tax %, Company).
**Rules**, **Payroll**, and **Tax %** hub tab roots also set **self.setToolTip** for margin hover.
**Keyboard shortcuts…** on Rules / AR / AP / Payroll grids (including empty area)
matches **Help → Business shortcuts…**; context-menu **QAction**s use **setToolTip**. The same dialog is offered on Business modal tables
that support **Copy row** (``_attach_table_copy_row_menu``).
Main toolbars on Rules, AR, AP, Payroll, and **Tax %** use **setToolTip** on primary actions.
**Rules** and **Payroll** subtabs include a gray footer hint **QLabel** with its own tooltip.
Rules / AR / AP / Payroll **main grids** also use **setToolTip** (shortcuts + **F5** on Business or top-level Customers/Vendors).
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
from collections.abc import Callable
from datetime import date as date_cls

from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QFileDialog,
)

from PySide6.QtCore import QDate, QSettings, Qt
from PySide6.QtGui import QGuiApplication, QHideEvent, QKeySequence, QShortcut, QShowEvent

from desktop_app.flexible_date import (
    attach_line_edit_us_date_normalization,
    configure_qdate_edit_us,
    format_iso_to_us_display,
    line_edit_to_iso_or_raw,
)
from desktop_app.qt_combo_ids import (
    coerce_combo_int_id,
    combo_index_for_int_user_data,
    combo_int_ids_equal,
)
from desktop_app.qt_mnemonic import (
    CSV_EXPORT_OK_TIP_SUFFIX,
    escape_ampersand_for_qt,
    message_box_critical_ok,
    message_box_information_ok,
    message_box_warning_ok,
    tip_message_box_buttons,
    tip_qdialog_button_box,
)
from desktop_app.theme import ar_ap_master_tab_stylesheet
from desktop_app.table_clipboard import (
    CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX,
    QTABLE_PLAIN_TEXT_ROLE,
    VIEW_BANK_REGISTER_KEYS_TOOLTIP,
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

# Appended to Business hub CSV export button tooltips (matches Journal / Reports / Audit).
_CSV_EXCEL_ENCODING_TIP = " UTF-8 with BOM for Excel."


def _table_row_entity_id(tbl: QTableWidget, row: int) -> int | None:
    """Read integer id from column 0 (invoice/bill # column), independent of sort order."""
    if row < 0 or row >= tbl.rowCount():
        return None
    it = tbl.item(row, 0)
    if it is None:
        return None
    v = coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole))
    if v is not None:
        return v
    plain = it.data(QTABLE_PLAIN_TEXT_ROLE)
    if isinstance(plain, str) and plain.strip():
        v2 = coerce_combo_int_id(plain.strip())
        if v2 is not None:
            return v2
    return coerce_combo_int_id((it.text() or "").strip())


def _rule_id_at_row(tbl: QTableWidget, row: int) -> int | None:
    """Rule primary key from column 0 ``UserRole`` (stable when the rules table is sorted)."""
    if row < 0 or row >= tbl.rowCount():
        return None
    it = tbl.item(row, 0)
    if it is None:
        return None
    return coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole))


def _payroll_run_id_at_row(tbl: QTableWidget, row: int) -> int | None:
    """Pay run id from column 0 ``UserRole`` (stable when the pay run table is sorted)."""
    if row < 0 or row >= tbl.rowCount():
        return None
    it = tbl.item(row, 0)
    if it is None:
        return None
    return coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole))


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
            "Same summary as Help → Business shortcuts… (F5, Tax % Ctrl+S, sub-tab grids). "
            + VIEW_BANK_REGISTER_KEYS_TOOLTIP
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        if not idx.isValid():
            m.exec(tbl.viewport().mapToGlobal(pos))
            return
        row = idx.row()
        m.addSeparator()
        act_copy = m.addAction("Copy row", lambda r=row: copy_table_row_as_tsv(tbl, r))
        act_copy.setToolTip(
            "Copy this row as tab-separated text for pasting into a spreadsheet or editor. "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
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
    bid = coerce_combo_int_id(raw)
    if bid is None or bid <= 0:
        return
    ix = combo_index_for_int_user_data(cb, bid, start=1)
    if ix is not None:
        cb.setCurrentIndex(ix)


def _save_payment_bank_choice(cb: QComboBox, settings_key: str) -> None:
    """Persist *cb* bank selection (index 0 or missing data → -1)."""
    idx = cb.currentIndex()
    s = QSettings()
    if idx <= 0:
        s.setValue(settings_key, -1)
        return
    bd = coerce_combo_int_id(cb.itemData(idx))
    s.setValue(settings_key, bd if bd is not None else -1)


_NEW_INVOICE_CUSTOMER_KEY = "business/new_invoice_customer_id"
_NEW_BILL_VENDOR_KEY = "business/new_bill_vendor_id"
_AR_PAYMENT_CUSTOMER_KEY = "business/ar_payment_customer_id"
_AP_PAYMENT_VENDOR_KEY = "business/ap_payment_vendor_id"
_AR_INVOICE_GRID_FILTER_KEY = "business/ar_invoice_grid_filter"
_AP_BILL_GRID_FILTER_KEY = "business/ap_bill_grid_filter"
_AR_INVOICE_HEADER_STATE_KEY = "business/ar_invoice_table_header_state"
_AR_CUSTOMER_HEADER_STATE_KEY = "business/ar_customer_table_header_state"
_AP_BILL_HEADER_STATE_KEY = "business/ap_bill_table_header_state"
_AP_VENDOR_HEADER_STATE_KEY = "business/ap_vendor_table_header_state"
_RULES_TABLE_HEADER_STATE_KEY = "business/rules_table_header_state"
_PAYROLL_RUNS_HEADER_STATE_KEY = "business/payroll_runs_table_header_state"
_BUSINESS_HUB_SUBTAB_KEY = "business/hub_subtab_index"


def _restore_entity_combo(cb: QComboBox, settings_key: str) -> None:
    """Reselect last-used customer or vendor id in *cb* if still listed."""
    raw = QSettings().value(settings_key, -1)
    eid = coerce_combo_int_id(raw)
    if eid is None or eid <= 0:
        return
    ix = combo_index_for_int_user_data(cb, eid)
    if ix is not None:
        cb.setCurrentIndex(ix)


def _save_entity_combo(cb: QComboBox, settings_key: str) -> None:
    cid = coerce_combo_int_id(cb.currentData())
    QSettings().setValue(settings_key, cid if cid is not None else -1)


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
    prev_id = coerce_combo_int_id(cb.currentData())
    cb.blockSignals(True)
    cb.clear()
    for r in rows:
        rid = coerce_combo_int_id(r["id"])
        if rid is None:
            continue
        cb.addItem(escape_ampersand_for_qt(r["name"] or ""), rid)
    cb.blockSignals(False)
    if cb.count() == 0:
        return
    ix = combo_index_for_int_user_data(cb, prev_id)
    pick = ix if ix is not None else 0
    cb.setCurrentIndex(min(pick, cb.count() - 1))


def open_ap_bill_edit_dialog(
    parent: QWidget,
    conn: sqlite3.Connection,
    bill_id: int,
    *,
    after_save: Callable[[], None] | None = None,
) -> bool:
    """Modal **Edit bill** dialog (shared by **Enter Bills** and bank/register AP bill links).

    Returns ``False`` if the bill id is missing; otherwise shows the dialog and returns ``True``.
    """
    bid = int(bill_id)
    if business.bill_has_payment_allocations(conn, bid):
        message_box_information_ok(
            parent,
            "Bill",
            "This bill has payments applied and cannot be edited.",
            ok_tip="Close; adjust or void AP payments before editing this bill.",
        )
        return True
    b = business.get_bill(conn, bid)
    if b is None:
        message_box_information_ok(
            parent,
            "Bill",
            f"Bill #{bid} is not in this company file.",
            ok_tip="Close; check Enter Bills or the bank link.",
        )
        return False
    vs = business.list_vendors(conn)
    if not vs:
        return False
    d = QDialog(parent)
    d.setWindowTitle("Edit bill")
    d.setToolTip(
        "Update vendor, amounts, dates, memo, or attachment (not allowed when AP payments are applied)."
    )
    f = QFormLayout(d)
    bill_vid = coerce_combo_int_id(b["vendor_id"])
    if bill_vid is None:
        return False
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
    vidx = combo_index_for_int_user_data(cb, bill_vid)
    cb.setCurrentIndex(vidx if vidx is not None else 0)
    vinv = QLineEdit(b["vendor_invoice_number"] or "")
    vinv.setToolTip("Vendor’s invoice or reference number (optional).")
    amt = QDoubleSpinBox()
    amt.setRange(0, 9_999_999)
    amt.setDecimals(2)
    amt.setValue(float(b["total"] or 0))
    amt.setToolTip("Total bill amount (required).")
    bdt = QDateEdit()
    configure_qdate_edit_us(bdt)
    qbd = QDate.fromString(b["bill_date"] or "", "yyyy-MM-dd")
    bdt.setDate(qbd if qbd.isValid() else QDate.currentDate())
    bdt.setToolTip("Bill date.")
    due_e = QLineEdit(format_iso_to_us_display(b["due_date"] or ""))
    due_e.setToolTip("Due date as text if you track it (optional).")
    attach_line_edit_us_date_normalization(due_e)
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
        return True
    new_vid = coerce_combo_int_id(cb.currentData())
    if new_vid is None:
        message_box_warning_ok(
            parent,
            "Bill",
            "Select a vendor (try clearing the filter).",
            ok_tip="Close; pick a vendor or clear the vendor filter.",
        )
        return True
    try:
        business.update_bill(
            conn,
            bid,
            new_vid,
            bdt.date().toString("yyyy-MM-dd"),
            amt.value(),
            vendor_invoice_number=vinv.text().strip(),
            due_date=(line_edit_to_iso_or_raw(due_e) or ""),
            memo=memo_e.text().strip(),
            attachment_path=att.text().strip(),
        )
    except ValueError as exc:
        message_box_warning_ok(
            parent,
            "Bill",
            escape_ampersand_for_qt(str(exc)),
            ok_tip="Close; fix the issue shown and save again.",
        )
        return True
    if after_save is not None:
        after_save()
    return True


def _prompt_as_of_date(parent: QWidget, title: str) -> str | None:
    """Show dialog for aging *as-of* date; return ``yyyy-mm-dd`` or ``None`` if cancelled."""
    d = QDialog(parent)
    d.setWindowTitle(title)
    d.setToolTip(
        "Aging buckets and balances use the as-of date you confirm here (export or report)."
    )
    f = QFormLayout(d)
    de = QDateEdit()
    configure_qdate_edit_us(de)
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
    box.setInformativeText("The saved CSV uses UTF-8 with BOM for Excel.")
    box.setIcon(QMessageBox.Icon.Question)
    box.setToolTip(
        "A list filter is active: export only visible rows, all database rows, or cancel."
        + _CSV_EXCEL_ENCODING_TIP
    )
    btn_vis = box.addButton("Visible only", QMessageBox.ButtonRole.AcceptRole)
    btn_vis.setToolTip(
        "Export only rows that match the current list filter." + _CSV_EXCEL_ENCODING_TIP
    )
    btn_all = box.addButton("All rows", QMessageBox.ButtonRole.ActionRole)
    btn_all.setToolTip(
        "Export all records of this type in the database, ignoring the filter."
        + _CSV_EXCEL_ENCODING_TIP
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
            "F5 refreshes when Business has focus. "
            "CSV exports (toolbar) use UTF-8 BOM for Excel."
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
        rb_export.setToolTip("Export all rules to a CSV file." + _CSV_EXCEL_ENCODING_TIP)
        rb_export.clicked.connect(self._export_csv)
        row.addWidget(rb_export)
        rb_import = QPushButton("Import CSV…")
        rb_import.setToolTip(
            "Replace all rules from a CSV file after confirmation; the grid refreshes when done. "
            "Read as UTF-8 with optional BOM (matches Export CSV… / Excel)."
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
        packed = [
            (rid, r)
            for r in rows
            if (rid := coerce_combo_int_id(r["id"])) is not None
        ]
        self._tbl.setSortingEnabled(False)
        self._tbl.setRowCount(len(packed))
        for i, (rid, r) in enumerate(packed):
            it0 = plain_display_table_item(r["pattern"] or "")
            it0.setData(Qt.ItemDataRole.UserRole, rid)
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
            "Same summary as Help → Business shortcuts… (F5, Rules grid, AR/AP/Payroll). "
            + VIEW_BANK_REGISTER_KEYS_TOOLTIP
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
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
            "Copy this rule row as tab-separated text for pasting into a spreadsheet or editor. "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
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
        cur = next((x for x in all_rules if combo_int_ids_equal(x["id"], rid)), None)
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
            ok_tip="Close; open the CSV from the path shown." + CSV_EXPORT_OK_TIP_SUFFIX,
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
        self.setObjectName("arMasterTab")
        self.setStyleSheet(ar_ap_master_tab_stylesheet())
        self._conn = conn
        self._customer_summary_by_id: dict[int, dict] = {}
        self._focused_customer_id: int | None = None
        self.setToolTip(
            "Accounts receivable: customer master list, balances, and last activity; "
            "F5 refreshes when Business has focus. "
            "Toolbar export uses UTF-8 BOM for Excel. "
            "(F5 refreshes when this tab has focus.)"
        )
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        ar_new_cust = QPushButton("New Customer")
        ar_new_cust.setToolTip("Create a new customer record.")
        ar_new_cust.clicked.connect(self._new_cust)
        row.addWidget(ar_new_cust)
        ar_edit_cust = QPushButton("Edit Customer…")
        ar_edit_cust.setToolTip("Choose a customer and edit name, contact, and notes.")
        ar_edit_cust.clicked.connect(self._edit_cust)
        row.addWidget(ar_edit_cust)
        ar_export_cust = QPushButton("Export Customers CSV…")
        ar_export_cust.setToolTip("Export all customers to CSV." + _CSV_EXCEL_ENCODING_TIP)
        ar_export_cust.clicked.connect(self._export_customers)
        row.addWidget(ar_export_cust)
        row.addStretch()
        lay.addLayout(row)

        split = QSplitter(Qt.Orientation.Vertical)
        split.setToolTip("Drag to resize selected-customer detail vs customer list.")

        detail_box = QGroupBox("Selected Customer")
        detail_box.setToolTip(
            "Contact fields from the customer master record; balances from open invoices and payments."
        )
        df = QFormLayout(detail_box)
        self._d_name = QLabel("—")
        self._d_address = QLabel("—")
        self._d_address.setWordWrap(True)
        self._d_phone = QLabel("—")
        self._d_email = QLabel("—")
        self._d_terms = QLabel("—")
        self._d_terms.setToolTip(
            "Payment terms are not stored separately yet; describe them in Notes if needed."
        )
        self._d_open_bal = QLabel("—")
        self._d_cur_due = QLabel("—")
        self._d_overdue = QLabel("—")
        self._d_last_inv = QLabel("—")
        self._d_last_pay = QLabel("—")
        self._d_notes = QLabel("—")
        self._d_notes.setWordWrap(True)
        df.addRow("Customer Name", self._d_name)
        df.addRow("Address", self._d_address)
        df.addRow("Phone", self._d_phone)
        df.addRow("Email", self._d_email)
        df.addRow("Terms", self._d_terms)
        df.addRow("Open Balance", self._d_open_bal)
        df.addRow("Current Due", self._d_cur_due)
        df.addRow("Overdue", self._d_overdue)
        df.addRow("Last Invoice Date", self._d_last_inv)
        df.addRow("Last Payment Date", self._d_last_pay)
        df.addRow("Notes", self._d_notes)
        split.addWidget(detail_box)

        list_box = QGroupBox("Customers")
        list_box.setToolTip("Click a row to show that customer in the detail card above.")
        lb_lay = QVBoxLayout(list_box)
        self._customer_tbl = QTableWidget()
        self._customer_tbl.setColumnCount(7)
        self._customer_tbl.setHorizontalHeaderLabels(
            [
                "Customer",
                "Open Balance",
                "Current Due",
                "Overdue",
                "Last Invoice Date",
                "Last Payment Date",
                "Status",
            ]
        )
        self._customer_tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._customer_tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._customer_tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._customer_tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._customer_tbl.setSortingEnabled(True)
        self._customer_tbl.cellClicked.connect(self._on_customer_row_clicked)
        self._customer_tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._customer_tbl.customContextMenuRequested.connect(self._on_customer_context_menu)
        self._customer_tbl.setToolTip(
            "Customer master snapshot; click a row to update the detail card. F5 refreshes. "
            "CSV exports (toolbar) use UTF-8 BOM for Excel."
        )
        lb_lay.addWidget(self._customer_tbl)
        split.addWidget(list_box)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 2)
        lay.addWidget(split, 1)
        self._refresh()

    def persist_header_state(self) -> None:
        QSettings().setValue(
            _AR_CUSTOMER_HEADER_STATE_KEY,
            self._customer_tbl.horizontalHeader().saveState(),
        )

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        raw = QSettings().value(_AR_CUSTOMER_HEADER_STATE_KEY)
        if raw:
            self._customer_tbl.horizontalHeader().restoreState(raw)

    def hideEvent(self, event: QHideEvent) -> None:
        self.persist_header_state()
        super().hideEvent(event)

    def _on_customer_row_clicked(self, row: int, _col: int) -> None:
        if row < 0:
            return
        it = self._customer_tbl.item(row, 0)
        if it is None:
            return
        cid = coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole))
        if cid is None:
            return
        self._focused_customer_id = cid
        self._apply_detail_from_focus()

    def _on_customer_context_menu(self, pos) -> None:
        idx = self._customer_tbl.indexAt(pos)
        m = QMenu(self)
        act_keys = m.addAction(
            "Keyboard shortcuts…",
            lambda: show_business_keyboard_shortcuts_dialog(self),
        )
        act_keys.setToolTip(
            "Same summary as Help → Business shortcuts… (F5, Customers grid). "
            + VIEW_BANK_REGISTER_KEYS_TOOLTIP
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        if not idx.isValid():
            m.exec(self._customer_tbl.viewport().mapToGlobal(pos))
            return
        row = idx.row()
        it = self._customer_tbl.item(row, 0)
        if it is None or coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole)) is None:
            m.exec(self._customer_tbl.viewport().mapToGlobal(pos))
            return
        m.addSeparator()
        act_copy = m.addAction(
            "Copy row", lambda r=row: copy_table_row_as_tsv(self._customer_tbl, r)
        )
        act_copy.setToolTip(
            "Copy this customer row as tab-separated text for pasting into a spreadsheet or editor. "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        m.exec(self._customer_tbl.viewport().mapToGlobal(pos))

    def _apply_detail_from_focus(self) -> None:
        if self._focused_customer_id is None:
            self._clear_detail_card()
            return
        v = business.get_customer(self._conn, self._focused_customer_id)
        summ = self._customer_summary_by_id.get(self._focused_customer_id)
        if v is None:
            self._clear_detail_card()
            return
        d = dict(v)
        self._d_name.setText(escape_ampersand_for_qt(d.get("name") or "—"))
        addr = (d.get("address") or "").strip()
        self._d_address.setText(escape_ampersand_for_qt(addr) if addr else "—")
        self._d_phone.setText(escape_ampersand_for_qt(d.get("phone") or "") or "—")
        self._d_email.setText(escape_ampersand_for_qt(d.get("email") or "") or "—")
        self._d_terms.setText("—")
        notes = (d.get("notes") or "").strip()
        self._d_notes.setText(escape_ampersand_for_qt(notes) if notes else "—")
        if summ is None:
            self._d_open_bal.setText("—")
            self._d_cur_due.setText("—")
            self._d_overdue.setText("—")
            self._d_last_inv.setText("—")
            self._d_last_pay.setText("—")
            return
        self._d_open_bal.setText(f"{float(summ['open_balance']):,.2f}")
        self._d_cur_due.setText(f"{float(summ['current_due']):,.2f}")
        self._d_overdue.setText(f"{float(summ['overdue']):,.2f}")
        self._d_last_inv.setText(summ.get("last_invoice_date") or "—")
        self._d_last_pay.setText(summ.get("last_payment_date") or "—")

    def _clear_detail_card(self) -> None:
        for w in (
            self._d_name,
            self._d_address,
            self._d_phone,
            self._d_email,
            self._d_terms,
            self._d_open_bal,
            self._d_cur_due,
            self._d_overdue,
            self._d_last_inv,
            self._d_last_pay,
            self._d_notes,
        ):
            w.setText("—")

    def _refresh(self) -> None:
        rows = business.list_customer_ar_summaries(self._conn)
        self._customer_summary_by_id = {int(r["customer_id"]): r for r in rows}
        self._customer_tbl.setSortingEnabled(False)
        self._customer_tbl.setRowCount(len(rows))
        for i, r in enumerate(rows):
            cid = int(r["customer_id"])
            nm = r["customer_name"] or ""
            it0 = QTableWidgetItem(escape_ampersand_for_qt(nm))
            it0.setData(Qt.ItemDataRole.UserRole, cid)
            self._customer_tbl.setItem(i, 0, it0)
            ob = float(r["open_balance"] or 0)
            cd = float(r["current_due"] or 0)
            ov = float(r["overdue"] or 0)
            self._customer_tbl.setItem(i, 1, _FloatSortTableItem(f"{ob:.2f}", ob))
            self._customer_tbl.setItem(i, 2, _FloatSortTableItem(f"{cd:.2f}", cd))
            self._customer_tbl.setItem(i, 3, _FloatSortTableItem(f"{ov:.2f}", ov))
            self._customer_tbl.setItem(
                i, 4, plain_display_table_item(r["last_invoice_date"] or "")
            )
            self._customer_tbl.setItem(
                i, 5, plain_display_table_item(r["last_payment_date"] or "")
            )
            self._customer_tbl.setItem(
                i, 6, plain_display_table_item(r.get("ar_status") or "")
            )
        self._customer_tbl.setSortingEnabled(True)
        ids = {int(r["customer_id"]) for r in rows}
        if self._focused_customer_id is not None and self._focused_customer_id not in ids:
            self._focused_customer_id = None
        if self._focused_customer_id is None and rows:
            self._focused_customer_id = int(rows[0]["customer_id"])
        if self._focused_customer_id is not None:
            for row in range(self._customer_tbl.rowCount()):
                it = self._customer_tbl.item(row, 0)
                if it is None:
                    continue
                if coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole)) == self._focused_customer_id:
                    self._customer_tbl.selectRow(row)
                    break
            self._apply_detail_from_focus()
        else:
            self._customer_tbl.clearSelection()
            self._clear_detail_card()

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
                ok_tip="Close; use New Customer first.",
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
            cid = coerce_combo_int_id(cb.currentData())
            if cid is None:
                return
            row = business.get_customer(self._conn, cid)
            if row is None:
                return
            ne.setText(row["name"] or "")
            em.setText(row["email"] or "")
            ph.setText(row["phone"] or "")
            ad.setPlainText(row["address"] or "")
            no.setPlainText(row["notes"] or "")

        def sync_customer_combo() -> None:
            _sync_filtered_entity_combo(
                custs,
                filt.text(),
                cb,
                business_list_filter.CUSTOMER_ENTITY_KEYS,
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
        cid = coerce_combo_int_id(cb.currentData())
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
                cid,
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
            ok_tip="Close; open the CSV from the path shown." + CSV_EXPORT_OK_TIP_SUFFIX,
        )



class APTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.setObjectName("apMasterTab")
        self.setStyleSheet(ar_ap_master_tab_stylesheet())
        self._conn = conn
        self._vendor_summary_by_id: dict[int, dict] = {}
        self._focused_vendor_id: int | None = None
        self.setToolTip(
            "Accounts payable: vendor master list, balances, and last activity; "
            "F5 refreshes when Business has focus. "
            "Toolbar export uses UTF-8 BOM for Excel. "
            "(F5 refreshes when this tab has focus.)"
        )
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        ap_new_v = QPushButton("New Vendor")
        ap_new_v.setToolTip("Create a new vendor record.")
        ap_new_v.clicked.connect(self._new_v)
        row.addWidget(ap_new_v)
        ap_edit_v = QPushButton("Edit Vendor…")
        ap_edit_v.setToolTip("Choose a vendor and edit name, contact, 1099 flag, and notes.")
        ap_edit_v.clicked.connect(self._edit_v)
        row.addWidget(ap_edit_v)
        ap_export_vendors = QPushButton("Export Vendors CSV…")
        ap_export_vendors.setToolTip("Export all vendors to CSV." + _CSV_EXCEL_ENCODING_TIP)
        ap_export_vendors.clicked.connect(self._export_vendors)
        row.addWidget(ap_export_vendors)
        row.addStretch()
        lay.addLayout(row)

        split = QSplitter(Qt.Orientation.Vertical)
        split.setToolTip("Drag to resize selected-vendor detail vs vendor list.")

        detail_box = QGroupBox("Selected Vendor")
        detail_box.setToolTip(
            "Contact fields from the vendor master record; balances from open bills and payments."
        )
        df = QFormLayout(detail_box)
        self._d_name = QLabel("—")
        self._d_address = QLabel("—")
        self._d_address.setWordWrap(True)
        self._d_phone = QLabel("—")
        self._d_email = QLabel("—")
        self._d_tax_id = QLabel("—")
        self._d_tax_id.setToolTip(
            "No dedicated Tax ID column in the database yet; store EIN/TIN in Notes if needed."
        )
        self._d_terms = QLabel("—")
        self._d_terms.setToolTip(
            "Payment terms are not stored separately yet; describe them in Notes if needed."
        )
        self._d_open_bal = QLabel("—")
        self._d_cur_due = QLabel("—")
        self._d_overdue = QLabel("—")
        self._d_last_bill = QLabel("—")
        self._d_last_pay = QLabel("—")
        self._d_notes = QLabel("—")
        self._d_notes.setWordWrap(True)
        df.addRow("Vendor Name", self._d_name)
        df.addRow("Address", self._d_address)
        df.addRow("Phone", self._d_phone)
        df.addRow("Email", self._d_email)
        df.addRow("Tax ID", self._d_tax_id)
        df.addRow("Terms", self._d_terms)
        df.addRow("Open Balance", self._d_open_bal)
        df.addRow("Current Due", self._d_cur_due)
        df.addRow("Overdue", self._d_overdue)
        df.addRow("Last Bill Date", self._d_last_bill)
        df.addRow("Last Payment Date", self._d_last_pay)
        df.addRow("Notes", self._d_notes)
        split.addWidget(detail_box)

        list_box = QGroupBox("Vendors")
        list_box.setToolTip("Click a row to show that vendor in the detail card above.")
        lb_lay = QVBoxLayout(list_box)
        self._vendor_tbl = QTableWidget()
        self._vendor_tbl.setColumnCount(7)
        self._vendor_tbl.setHorizontalHeaderLabels(
            [
                "Vendor",
                "Open Balance",
                "Current Due",
                "Overdue",
                "Last Bill Date",
                "Last Payment Date",
                "Status",
            ]
        )
        self._vendor_tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._vendor_tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._vendor_tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._vendor_tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._vendor_tbl.setSortingEnabled(True)
        self._vendor_tbl.cellClicked.connect(self._on_vendor_row_clicked)
        self._vendor_tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._vendor_tbl.customContextMenuRequested.connect(self._on_vendor_context_menu)
        self._vendor_tbl.setToolTip(
            "Vendor master snapshot; click a row to update the detail card. F5 refreshes. "
            "CSV exports (toolbar) use UTF-8 BOM for Excel."
        )
        lb_lay.addWidget(self._vendor_tbl)
        split.addWidget(list_box)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 2)
        lay.addWidget(split, 1)
        self._refresh()

    def persist_header_state(self) -> None:
        QSettings().setValue(
            _AP_VENDOR_HEADER_STATE_KEY,
            self._vendor_tbl.horizontalHeader().saveState(),
        )

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        raw = QSettings().value(_AP_VENDOR_HEADER_STATE_KEY)
        if raw:
            self._vendor_tbl.horizontalHeader().restoreState(raw)

    def hideEvent(self, event: QHideEvent) -> None:
        self.persist_header_state()
        super().hideEvent(event)

    def _on_vendor_row_clicked(self, row: int, _col: int) -> None:
        if row < 0:
            return
        it = self._vendor_tbl.item(row, 0)
        if it is None:
            return
        vid = coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole))
        if vid is None:
            return
        self._focused_vendor_id = vid
        self._apply_detail_from_focus()

    def _on_vendor_context_menu(self, pos) -> None:
        idx = self._vendor_tbl.indexAt(pos)
        m = QMenu(self)
        act_keys = m.addAction(
            "Keyboard shortcuts…",
            lambda: show_business_keyboard_shortcuts_dialog(self),
        )
        act_keys.setToolTip(
            "Same summary as Help → Business shortcuts… (F5, Vendors grid). "
            + VIEW_BANK_REGISTER_KEYS_TOOLTIP
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        if not idx.isValid():
            m.exec(self._vendor_tbl.viewport().mapToGlobal(pos))
            return
        row = idx.row()
        it = self._vendor_tbl.item(row, 0)
        if it is None or coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole)) is None:
            m.exec(self._vendor_tbl.viewport().mapToGlobal(pos))
            return
        m.addSeparator()
        act_copy = m.addAction(
            "Copy row", lambda r=row: copy_table_row_as_tsv(self._vendor_tbl, r)
        )
        act_copy.setToolTip(
            "Copy this vendor row as tab-separated text for pasting into a spreadsheet or editor. "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
        )
        m.exec(self._vendor_tbl.viewport().mapToGlobal(pos))

    def _apply_detail_from_focus(self) -> None:
        if self._focused_vendor_id is None:
            self._clear_detail_card()
            return
        v = business.get_vendor(self._conn, self._focused_vendor_id)
        summ = self._vendor_summary_by_id.get(self._focused_vendor_id)
        if v is None:
            self._clear_detail_card()
            return
        d = dict(v)
        self._d_name.setText(escape_ampersand_for_qt(d.get("name") or "—"))
        addr = (d.get("address") or "").strip()
        self._d_address.setText(escape_ampersand_for_qt(addr) if addr else "—")
        self._d_phone.setText(escape_ampersand_for_qt(d.get("phone") or "") or "—")
        self._d_email.setText(escape_ampersand_for_qt(d.get("email") or "") or "—")
        self._d_tax_id.setText("—")
        self._d_terms.setText("—")
        notes = (d.get("notes") or "").strip()
        self._d_notes.setText(escape_ampersand_for_qt(notes) if notes else "—")
        if summ is None:
            self._d_open_bal.setText("—")
            self._d_cur_due.setText("—")
            self._d_overdue.setText("—")
            self._d_last_bill.setText("—")
            self._d_last_pay.setText("—")
            return
        self._d_open_bal.setText(f"{float(summ['open_balance']):,.2f}")
        self._d_cur_due.setText(f"{float(summ['current_due']):,.2f}")
        self._d_overdue.setText(f"{float(summ['overdue']):,.2f}")
        self._d_last_bill.setText(summ.get("last_bill_date") or "—")
        self._d_last_pay.setText(summ.get("last_payment_date") or "—")

    def _clear_detail_card(self) -> None:
        for w in (
            self._d_name,
            self._d_address,
            self._d_phone,
            self._d_email,
            self._d_tax_id,
            self._d_terms,
            self._d_open_bal,
            self._d_cur_due,
            self._d_overdue,
            self._d_last_bill,
            self._d_last_pay,
            self._d_notes,
        ):
            w.setText("—")

    def _refresh(self) -> None:
        rows = business.list_vendor_ap_summaries(self._conn)
        self._vendor_summary_by_id = {int(r["vendor_id"]): r for r in rows}
        self._vendor_tbl.setSortingEnabled(False)
        self._vendor_tbl.setRowCount(len(rows))
        for i, r in enumerate(rows):
            vid = int(r["vendor_id"])
            nm = r["vendor_name"] or ""
            it0 = QTableWidgetItem(escape_ampersand_for_qt(nm))
            it0.setData(Qt.ItemDataRole.UserRole, vid)
            self._vendor_tbl.setItem(i, 0, it0)
            ob = float(r["open_balance"] or 0)
            cd = float(r["current_due"] or 0)
            ov = float(r["overdue"] or 0)
            self._vendor_tbl.setItem(i, 1, _FloatSortTableItem(f"{ob:.2f}", ob))
            self._vendor_tbl.setItem(i, 2, _FloatSortTableItem(f"{cd:.2f}", cd))
            self._vendor_tbl.setItem(i, 3, _FloatSortTableItem(f"{ov:.2f}", ov))
            self._vendor_tbl.setItem(
                i, 4, plain_display_table_item(r["last_bill_date"] or "")
            )
            self._vendor_tbl.setItem(
                i, 5, plain_display_table_item(r["last_payment_date"] or "")
            )
            self._vendor_tbl.setItem(
                i, 6, plain_display_table_item(r.get("ap_status") or "")
            )
        self._vendor_tbl.setSortingEnabled(True)
        ids = {int(r["vendor_id"]) for r in rows}
        if self._focused_vendor_id is not None and self._focused_vendor_id not in ids:
            self._focused_vendor_id = None
        if self._focused_vendor_id is None and rows:
            self._focused_vendor_id = int(rows[0]["vendor_id"])
        if self._focused_vendor_id is not None:
            for row in range(self._vendor_tbl.rowCount()):
                it = self._vendor_tbl.item(row, 0)
                if it is None:
                    continue
                if coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole)) == self._focused_vendor_id:
                    self._vendor_tbl.selectRow(row)
                    break
            self._apply_detail_from_focus()
        else:
            self._vendor_tbl.clearSelection()
            self._clear_detail_card()

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
            vid = coerce_combo_int_id(cb.currentData())
            if vid is None:
                return
            row = business.get_vendor(self._conn, vid)
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
        vid = coerce_combo_int_id(cb.currentData())
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
                vid,
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
            ok_tip="Close; open the CSV from the path shown." + CSV_EXPORT_OK_TIP_SUFFIX,
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
        pt_export_tax.setToolTip(
            "Export payroll tax lines for a date range to CSV." + _CSV_EXCEL_ENCODING_TIP
        )
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
            "F5 refreshes when Business has focus. "
            "CSV exports (toolbar) use UTF-8 BOM for Excel."
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

    def open_payroll_run_by_id(self, run_id: int) -> bool:
        """Select a pay run by id and open **Tax lines for run** (returns False if not found)."""
        rid = int(run_id)
        self._refresh()
        for row in range(self._tbl.rowCount()):
            if _payroll_run_id_at_row(self._tbl, row) == rid:
                self._tbl.selectRow(row)
                self._tbl.setFocus()
                self._edit_run_taxes()
                return True
        message_box_information_ok(
            self,
            "Payroll",
            f"Pay run #{rid} is not in the list (removed or different company).",
            ok_tip="Close; check Business → Payroll or the bank link.",
        )
        return False

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
        existing: dict[int, object] = {}
        for row in business.list_payroll_run_tax_lines(self._conn, run_id):
            k = coerce_combo_int_id(row["tax_item_id"])
            if k is not None:
                existing[k] = row
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
        item_rows = [
            (lid, it)
            for it in items
            if (lid := coerce_combo_int_id(it["id"])) is not None
        ]
        if not item_rows:
            message_box_warning_ok(
                self,
                "Payroll taxes",
                "No tax codes with valid ids could be loaded.",
                ok_tip="Close; check company data or schema.",
            )
            return
        tbl = QTableWidget(len(item_rows), 4)
        tbl.setHorizontalHeaderLabels(["Code", "Name", "Employee $", "Employer $"])
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        tbl.setToolTip(
            "Employee and employer amounts per tax code for this run. Right-click to copy a row as TSV."
        )
        tbl.setSortingEnabled(False)
        spin_pairs: list[tuple[int, QDoubleSpinBox, QDoubleSpinBox]] = []
        for i, (lid, it) in enumerate(item_rows):
            tbl.setItem(i, 0, plain_display_table_item(it["code"] or ""))
            tbl.setItem(i, 1, plain_display_table_item(it["name"] or ""))
            se = QDoubleSpinBox()
            se.setRange(-9_999_999.99, 9_999_999.99)
            se.setDecimals(2)
            sr = QDoubleSpinBox()
            sr.setRange(-9_999_999.99, 9_999_999.99)
            sr.setDecimals(2)
            prev = existing.get(lid)
            if prev:
                se.setValue(float(prev["employee_amount"]))
                sr.setValue(float(prev["employer_amount"]))
            tbl.setCellWidget(i, 2, se)
            tbl.setCellWidget(i, 3, sr)
            spin_pairs.append((lid, se, sr))
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
            "Same summary as Help → Business shortcuts… (F5, Payroll grid, tax lines, GL post). "
            + VIEW_BANK_REGISTER_KEYS_TOOLTIP
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
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
            "Copy this pay run row as tab-separated text for pasting into a spreadsheet or editor. "
            + CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
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
        configure_qdate_edit_us(s)
        s.setToolTip("Include pay runs with pay date on or after this day.")
        e = QDateEdit()
        configure_qdate_edit_us(e)
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
        with open(path, "w", newline="", encoding="utf-8-sig") as fp:
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
            ok_tip="Close; open the payroll tax CSV from the path shown." + CSV_EXPORT_OK_TIP_SUFFIX,
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
        self._run_rows = []
        for x in rows:
            d = dict(x)
            if coerce_combo_int_id(d["id"]) is None:
                continue
            self._run_rows.append(d)
        self._tbl.setSortingEnabled(False)
        self._tbl.setRowCount(len(self._run_rows))
        for i, r in enumerate(self._run_rows):
            rid = coerce_combo_int_id(r["id"])
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
            jid = coerce_combo_int_id(je) if je is not None else None
            if jid is None:
                self._tbl.setItem(i, 6, plain_display_table_item(""))
            else:
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
        run = next(
            (x for x in self._run_rows if combo_int_ids_equal(x["id"], rid)), None
        )
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
                memo=f"Payroll run #{rid}",
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
            (eid, rid),
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
            eid = coerce_combo_int_id(e["id"])
            if eid is None:
                continue
            cb.addItem(escape_ampersand_for_qt(e["name"] or ""), eid)
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
        configure_qdate_edit_us(pd)
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
        eid = coerce_combo_int_id(cb.currentData())
        if eid is None:
            message_box_warning_ok(
                self,
                "Payroll",
                "Select a valid employee for this pay run.",
                ok_tip="Close; pick an employee in the combo, then try again.",
            )
            return
        pay_d = pd.date().toPython()
        ps = date_cls(pay_d.year, pay_d.month, 1).isoformat()
        pe = pay_d.isoformat()
        business.create_payroll_run(
            self._conn,
            eid,
            ps,
            pe,
            pd.date().toString("yyyy-MM-dd"),
            gross.value(),
            ded.value(),
        )
        self._refresh()


class CompanySetupTab(QWidget):
    """Company identity stored in ``company_settings``; used for invoice print/PDF letterhead."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self.setToolTip(
            "Legal or DBA name, mailing address, and contact fields saved to your company file; "
            "used as the sender block on printed and exported invoices (Ctrl+S or Save)."
        )
        root = QVBoxLayout(self)
        lay = QFormLayout()
        self._name = QLineEdit()
        self._addr1 = QLineEdit()
        self._addr2 = QLineEdit()
        self._city = QLineEdit()
        self._state = QLineEdit()
        self._zip = QLineEdit()
        self._phone = QLineEdit()
        self._email = QLineEdit()
        for w, tip in (
            (self._name, "Company or DBA name shown at the top of invoices."),
            (self._addr1, "Street address line 1."),
            (self._addr2, "Suite, unit, or second line (optional)."),
            (self._city, "City."),
            (self._state, "State or province."),
            (self._zip, "Postal or ZIP code."),
            (self._phone, "Main business phone (optional)."),
            (self._email, "Contact email (optional)."),
        ):
            w.setToolTip(tip)
        lay.addRow(escape_ampersand_for_qt("Company name"), self._name)
        lay.addRow("Address line 1", self._addr1)
        lay.addRow("Address line 2", self._addr2)
        lay.addRow("City", self._city)
        lay.addRow("State", self._state)
        lay.addRow("Zip", self._zip)
        lay.addRow("Phone", self._phone)
        lay.addRow("Email", self._email)
        root.addLayout(lay)
        self._load_from_settings()
        btn = QPushButton("Save company info")
        btn.setToolTip("Write these fields to the open company database (Ctrl+S does the same).")
        btn.clicked.connect(self._save)
        root.addWidget(btn)
        tip = QLabel(
            "Saved values appear on invoice PDFs and printouts (Invoices tab). "
            "Ctrl+S saves while this sub-tab has focus. Help → Business shortcuts… for hub keys."
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #A0A0B0; font-size: 11px;")
        tip.setToolTip("Same company .db as other tabs; File → Backup / Restore (probooks.backup).")
        root.addWidget(tip)
        save_sc = QShortcut(QKeySequence(QKeySequence.StandardKey.Save), self)
        save_sc.setContext(Qt.WidgetWithChildrenShortcut)
        save_sc.activated.connect(self._save)

    def _load_from_settings(self) -> None:
        g = lambda k: (business.get_setting(self._conn, k, "") or "").strip()
        self._name.setText(g("company_setup_name"))
        self._addr1.setText(g("company_setup_addr1"))
        self._addr2.setText(g("company_setup_addr2"))
        self._city.setText(g("company_setup_city"))
        self._state.setText(g("company_setup_state"))
        self._zip.setText(g("company_setup_zip"))
        self._phone.setText(g("company_setup_phone"))
        self._email.setText(g("company_setup_email"))

    def _save(self) -> None:
        business.set_setting(self._conn, "company_setup_name", (self._name.text() or "").strip())
        business.set_setting(self._conn, "company_setup_addr1", (self._addr1.text() or "").strip())
        business.set_setting(self._conn, "company_setup_addr2", (self._addr2.text() or "").strip())
        business.set_setting(self._conn, "company_setup_city", (self._city.text() or "").strip())
        business.set_setting(self._conn, "company_setup_state", (self._state.text() or "").strip())
        business.set_setting(self._conn, "company_setup_zip", (self._zip.text() or "").strip())
        business.set_setting(self._conn, "company_setup_phone", (self._phone.text() or "").strip())
        business.set_setting(self._conn, "company_setup_email", (self._email.text() or "").strip())
        message_box_information_ok(
            self,
            "Company",
            "Saved.",
            ok_tip="Close; invoice print and PDF use this sender block.",
        )


class TaxSettingsTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self.setToolTip(
            "Default sales tax name and rate for new invoices; save or Ctrl+S; "
            "export sales tax summary CSV uses UTF-8 BOM for Excel (settings-only, no F5 list)."
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
            + _CSV_EXCEL_ENCODING_TIP
        )
        ts_export_csv.clicked.connect(self._export_sales_tax_csv)
        root.addWidget(ts_export_csv)
        ts_tip = QLabel(
            "Ctrl+S saves default tax name and rate (same as Save settings). "
            "Export sales tax summary CSV uses UTF-8 BOM for Excel. "
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
        configure_qdate_edit_us(s)
        s.setToolTip("Include invoices dated on or after this day.")
        e = QDateEdit()
        configure_qdate_edit_us(e)
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
        with open(path, "w", newline="", encoding="utf-8-sig") as fp:
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
            ok_tip="Close; open the sales tax summary CSV from the path shown." + CSV_EXPORT_OK_TIP_SUFFIX,
        )


def _business_keyboard_shortcuts_help_text() -> str:
    """Plain text for **Help → Business shortcuts…** (aligned with **F5** / **Tax %** **Save**)."""
    return (
        "These shortcuts apply when the Business tab or its controls have focus:\n\n"
        "F5 — Refresh the current sub-tab list (Rules, Payroll). "
        "Tax % and Company have no list to reload.\n\n"
        "CSV exports from Business (Rules, payroll tax report, sales tax summary) use UTF-8 with BOM for Excel. "
        "Customer/vendor lists, invoices/bills, and AR/AP payments export from the main **Customers** and **Vendors** tabs.\n"
        "Rules Import CSV… reads UTF-8 with optional BOM (same as files from Export CSV…).\n\n"
        "On Tax % (settings):\n"
        "Ctrl+S — Save default tax name and rate (standard Save shortcut)\n\n"
        "On Company (settings):\n"
        "Ctrl+S — Save company name and address for invoice letterhead\n\n"
        "View menu tab focus: Ctrl+1 Invoices … Ctrl+9 Reconcile, Ctrl+0 More (Reports, Journal, Business, Audit log).\n\n"
        "Tools menu: Ctrl+Shift+I — Invoice… (top-level Invoices tab).\n\n"
        "Right-click the Rules or Payroll grid (including empty area) "
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
        "Register bulk actions (add transaction, post, export, cleared, **Link payment…**, **Open linked Business** when the bank link is complete, …): "
        "main **Recon** menu.\n"
    )


def show_business_keyboard_shortcuts_dialog(parent: QWidget) -> None:
    message_box_information_ok(
        parent,
        "Business shortcuts",
        _business_keyboard_shortcuts_help_text(),
        ok_tip=(
            "Close; shortcuts apply when the Business hub has focus. "
            + VIEW_BANK_REGISTER_KEYS_TOOLTIP
            + "Company .db: File → Backup / Restore (probooks.backup)."
        ),
    )


class BusinessHub(QWidget):
    """Nested tabs for rules, payroll, and tax (AR/AP workflows: main Customers / Vendors tabs)."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self._conn = conn
        self.setToolTip(
            "Business hub: categorization Rules, Payroll, default Tax %, and Company setup "
            "(F5 refreshes the active list sub-tab). "
            "Full AR/AP is on the main Customers and Vendors tabs. "
            "CSV exports use UTF-8 BOM for Excel. "
            "Same company SQLite database as other main tabs; File → Backup / Restore (probooks.backup)."
        )
        self._business_subtabs = QTabWidget()
        self._business_subtabs.setToolTip(
            "Switch between Rules, Payroll, Tax %, and Company "
            "(hover each sub-tab for a summary; F5 refreshes list subtabs). "
            "All sub-tabs share the open company .db (File → Backup / probooks backup)."
        )
        self._business_subtabs.addTab(RulesTab(conn), "Rules")
        self._business_subtabs.addTab(PayrollTaxTab(conn), "Payroll")
        self._business_subtabs.addTab(TaxSettingsTab(conn), "Tax %")
        self._business_subtabs.addTab(CompanySetupTab(conn), "Company")
        bar = self._business_subtabs.tabBar()
        bar.setTabToolTip(
            0,
            "Description-based rules that suggest a COA when importing or categorizing transactions.",
        )
        bar.setTabToolTip(
            1,
            "Employees, pay runs, payroll tax lines, and posting pay runs to the GL.",
        )
        bar.setTabToolTip(
            2,
            "Default sales tax name and rate for new invoices; export sales tax summary CSV (UTF-8 BOM for Excel).",
        )
        bar.setTabToolTip(
            3,
            "Company name, address, and contact for invoice print and PDF letterhead.",
        )
        raw_idx = QSettings().value(_BUSINESS_HUB_SUBTAB_KEY, 0)
        want_idx = coerce_combo_int_id(raw_idx)
        if want_idx is None:
            want_idx = 0
        n_tabs = self._business_subtabs.count()
        want_idx = max(0, min(want_idx, n_tabs - 1))
        self._business_subtabs.setCurrentIndex(want_idx)
        self._prev_business_subtab_idx = want_idx
        self._business_subtabs.currentChanged.connect(self._on_business_subtab_changed)
        lay = QVBoxLayout(self)
        lay.addWidget(self._business_subtabs)
        tip = QLabel(
            "F5 refreshes the current sub-tab when it has a list (Rules, Payroll). "
            "Tax % and Company are settings-only; sales tax CSV export uses UTF-8 BOM for Excel. "
            "Help → Business shortcuts… for details; other main tabs also use F5."
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

    def focus_company_subtab(self) -> None:
        """Select the **Company** (Company Setup) sub-tab."""
        for i in range(self._business_subtabs.count()):
            if isinstance(self._business_subtabs.widget(i), CompanySetupTab):
                self._business_subtabs.setCurrentIndex(i)
                return

    def focus_payroll_subtab(self) -> None:
        """Select the **Payroll** sub-tab (index 1)."""
        idx = 1
        if 0 <= idx < self._business_subtabs.count():
            self._business_subtabs.setCurrentIndex(idx)

    def navigate_bank_match_link(self, parent: QWidget, link_type: str, link_id: int) -> None:
        """Open the linked payroll record from a bank register Match link (AR/AP use main Customers/Vendors)."""
        lt = (link_type or "").strip()
        try:
            lid = int(link_id)
        except (TypeError, ValueError):
            message_box_information_ok(
                parent,
                "Business link",
                "Invalid link id.",
                ok_tip="Close; clear the bank link and set it again if needed.",
            )
            return
        if lt == "payroll_run":
            self.focus_payroll_subtab()
            w = self._business_subtabs.widget(1)
            if isinstance(w, PayrollTaxTab):
                w.open_payroll_run_by_id(lid)
            return
        message_box_information_ok(
            parent,
            "Business link",
            f"Unsupported link type: {lt or '(empty)'}",
            ok_tip="Close; clear the link or pick a supported AR/AP/payroll target.",
        )

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
        elif isinstance(prev_w, PayrollTaxTab):
            prev_w.persist_header_state()
        QSettings().setValue(_BUSINESS_HUB_SUBTAB_KEY, idx)
        self._prev_business_subtab_idx = idx
