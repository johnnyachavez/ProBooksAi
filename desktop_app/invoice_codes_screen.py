"""Item List — QuickBooks Pro Desktop item catalog + Edit Item dialog.

Read-only list (NAME / DESCRIPTION / TYPE / ACCOUNT / PRICE / ATTACH) with a
Look-for search row. Double-click a row (or Item → Edit) opens a compact
**Edit Item** dialog. Saving writes ``invoice_item_codes`` so Create Invoices
line Codes pick up the change.

Slightly cleaner spacing than a gray Win32 photocopy — not QuickBooks Online.
Does not seed Johnny's live catalog names.
"""

from __future__ import annotations

import sqlite3
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QPalette, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from probooksai import business
from probooksai.coa_db import COADatabase

from desktop_app.qt_combo_ids import coerce_combo_int_id
from desktop_app.qt_mnemonic import (
    escape_ampersand_for_qt,
    message_box_information_ok,
    message_box_warning_ok,
)
from desktop_app.table_clipboard import plain_display_table_item

# Light canvas like Chart of Accounts / Vendor Center.
_IL_CANVAS = "#E8ECF1"
_IL_PAPER = "#FFFFFF"
_IL_PANEL = "#F4F7FA"
_IL_STRIPE = "#D0E6F4"
_IL_CAPTION = "#4A5560"
_IL_GRID = "#C0C8D0"
_IL_HEADER = "#D8DEE6"
_IL_TEXT = "#1A1A1A"
_IL_ACCENT = "#2563A8"
_IL_SELECT = "#2E7D32"
_IL_SELECT_FG = "#FFFFFF"
_STRIP_BTN_OUTLINE = "#B4BCC6"
_TOP_STRIP_RADIUS_PX = 4
_TOP_STRIP_BODY_FONT_PX = 12

_COL_MARK = 0
_COL_NAME = 1
_COL_DESC = 2
_COL_TYPE = 3
_COL_ACCT = 4
_COL_PRICE = 5
_COL_ATTACH = 6

_ROLE_ITEM_ID = Qt.ItemDataRole.UserRole
_ROLE_DEPTH = Qt.ItemDataRole.UserRole + 1
_ROLE_ACTIVE = Qt.ItemDataRole.UserRole + 2

_SEARCH_FIELDS = (
    "All fields",
    "Name",
    "Description",
    "Type",
    "Account",
    "Price",
)

_TYPE_HELP = {
    "Service": (
        "Use for services you charge for or purchase, like specialized labor, "
        "consulting hours, or professional fees."
    ),
    "Discount": (
        "Use for discounts you give customers, like a percentage off or a dollar amount."
    ),
    "Other Charge": (
        "Use for miscellaneous charges such as freight, setup fees, or other amounts "
        "you add to a sale."
    ),
    "Subtotal": (
        "Use to add up the amounts of the items listed above this line on a form."
    ),
}

_ITEM_TYPES = business.INVOICE_ITEM_TYPES


def parse_rate_input(raw: str) -> tuple[float, str]:
    """Return ``(rate_value, rate_kind)`` where kind is ``amount`` or ``percent``."""
    s = (raw or "").strip().replace(",", "")
    if not s:
        return 0.0, "amount"
    if s.endswith("%"):
        try:
            return float(s[:-1].strip()), "percent"
        except ValueError:
            return 0.0, "percent"
    try:
        return float(s), "amount"
    except ValueError:
        return 0.0, "amount"


def format_rate_display(rate_value: float, rate_kind: str) -> str:
    if (rate_kind or "").lower() == "percent":
        return f"{rate_value:.1f}%"
    return f"{rate_value:.2f}"


def invoice_code_db_row_sort_key(row: object) -> tuple:
    """Sort saved items alphabetically by Name (case-insensitive), then ``sort_order``."""
    d = dict(row)
    return (
        (d.get("code") or "").strip().lower(),
        int(d.get("sort_order") or 0),
    )


def ordered_item_rows(rows: list) -> list[tuple[object, int]]:
    """Return ``(row, depth)`` with subitems indented under their parent."""
    by_id: dict[int, object] = {}
    for row in rows:
        aid = coerce_combo_int_id(row["id"])
        if aid is not None:
            by_id[aid] = row
    children: dict[int, list] = {}
    roots: list = []
    for row in rows:
        aid = coerce_combo_int_id(row["id"])
        if aid is None:
            continue
        pid = coerce_combo_int_id(row["parent_id"]) if "parent_id" in row.keys() else None
        if pid is not None and pid in by_id and pid != aid:
            children.setdefault(pid, []).append(row)
        else:
            roots.append(row)

    out: list[tuple[object, int]] = []

    def _walk(nodes: list, depth: int) -> None:
        for node in sorted(nodes, key=invoice_code_db_row_sort_key):
            out.append((node, depth))
            nid = coerce_combo_int_id(node["id"])
            if nid is not None:
                _walk(children.get(nid, []), depth + 1)

    _walk(roots, 0)
    return out


def _item_search_blob(row: object, field: str) -> str:
    d = dict(row)
    name = str(d.get("code") or "")
    desc = str(d.get("description") or "")
    typ = str(d.get("item_type") or "")
    acct = str(d.get("coa_account") or "")
    price = format_rate_display(
        float(d.get("rate_value") or 0.0),
        str(d.get("rate_kind") or "amount"),
    )
    mapping = {
        "Name": name,
        "Description": desc,
        "Type": typ,
        "Account": acct,
        "Price": price,
        "All fields": " ".join((name, desc, typ, acct, price)),
    }
    return mapping.get(field, mapping["All fields"]).lower()


def _action_button_qss(*, primary: bool = False) -> str:
    r = _TOP_STRIP_RADIUS_PX
    if primary:
        return (
            f"QPushButton {{ background-color: {_IL_ACCENT}; border: 1px solid {_IL_ACCENT}; "
            f"border-radius: {r}px; color: #FFFFFF; "
            f"font-size: {_TOP_STRIP_BODY_FONT_PX}px; padding: 0 12px; font-weight: 600; }}"
            f"QPushButton:hover {{ background-color: #1D4F8C; }}"
            f"QPushButton:pressed {{ background-color: #163E6E; }}"
            f"QPushButton:disabled {{ color: #D7E3F0; background-color: #8AA7C7; }}"
        )
    return (
        f"QPushButton {{ background-color: #F7F8FA; border: 1px solid {_STRIP_BTN_OUTLINE}; "
        f"border-radius: {r}px; color: {_IL_TEXT}; "
        f"font-size: {_TOP_STRIP_BODY_FONT_PX}px; padding: 0 12px; }}"
        f"QPushButton:hover {{ background-color: #E4EEF7; }}"
        f"QPushButton:pressed {{ background-color: #C9D8EC; }}"
        f"QPushButton:disabled {{ color: #8A94A0; }}"
    )


def _light_palette() -> QPalette:
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(_IL_CANVAS))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(_IL_TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(_IL_PAPER))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(_IL_STRIPE))
    pal.setColor(QPalette.ColorRole.Text, QColor(_IL_TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(_IL_PAPER))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(_IL_TEXT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(_IL_SELECT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(_IL_SELECT_FG))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(_IL_CAPTION))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(_IL_PANEL))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(_IL_TEXT))
    return pal


def _income_expense_labels(coa_db: Optional[COADatabase]) -> list[str]:
    if coa_db is None:
        return []
    try:
        rows = coa_db.list_accounts(include_inactive=False)
    except (sqlite3.Error, OSError, TypeError, ValueError):
        return []
    out: list[str] = []
    for row in rows:
        atype = str(row["account_type"] or "").strip().lower()
        if atype not in business.INCOME_EXPENSE_COA_TYPES:
            continue
        out.append(f"{row['account_number']} – {row['account_name']}")
    return out


# ===========================================================================
# Edit Item
# ===========================================================================


class EditItemDialog(QDialog):
    """Compact Edit Item popup (QB Pro Service item layout)."""

    def __init__(
        self,
        ap_conn: sqlite3.Connection,
        *,
        item_id: Optional[int] = None,
        coa_db: Optional[COADatabase] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._ap_conn = ap_conn
        self._coa_db = coa_db
        self._item_id = coerce_combo_int_id(item_id)
        self._notes = ""
        self.setObjectName("editItemDialog")
        self.setWindowTitle("Edit Item" if self._item_id else "New Item")
        self.setModal(True)
        self.resize(620, 340)
        self.setToolTip(
            "Edit one item from the Item List. OK saves to the company file for invoice lines."
        )
        self.setPalette(_light_palette())
        self.setAutoFillBackground(True)
        self.setStyleSheet(
            f"EditItemDialog {{ background-color: {_IL_CANVAS}; color: {_IL_TEXT}; }}"
        )
        self._build_ui()
        if self._item_id is not None:
            self._load(self._item_id)

    def _input_qss(self, widget: str = "QLineEdit") -> str:
        return (
            f"{widget} {{ background: {_IL_PAPER}; border: 1px solid {_IL_GRID}; "
            f"padding: 2px 6px; color: {_IL_TEXT}; font-size: 12px; }}"
        )

    def _build_ui(self) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 10, 10, 10)
        outer.setSpacing(10)

        form = QVBoxLayout()
        form.setSpacing(8)

        type_row = QHBoxLayout()
        type_row.setSpacing(10)
        type_lbl = QLabel("TYPE")
        type_lbl.setStyleSheet(
            f"color: {_IL_CAPTION}; font-size: 11px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        type_row.addWidget(type_lbl)
        self._type = QComboBox()
        self._type.setObjectName("editItemType")
        self._type.setStyleSheet(self._input_qss("QComboBox"))
        self._type.setFixedWidth(150)
        for t in _ITEM_TYPES:
            self._type.addItem(t)
        self._type.currentTextChanged.connect(self._on_type_changed)
        type_row.addWidget(self._type)
        self._type_help = QLabel(_TYPE_HELP["Service"])
        self._type_help.setObjectName("editItemTypeHelp")
        self._type_help.setWordWrap(True)
        self._type_help.setStyleSheet(
            f"color: {_IL_CAPTION}; font-size: 11px; background: transparent; border: none;"
        )
        type_row.addWidget(self._type_help, 1)
        form.addLayout(type_row)

        ident = QGridLayout()
        ident.setHorizontalSpacing(8)
        ident.setVerticalSpacing(6)
        name_lbl = QLabel("Item Name/Number")
        name_lbl.setStyleSheet(
            f"color: {_IL_CAPTION}; font-size: 11px; background: transparent; border: none;"
        )
        ident.addWidget(name_lbl, 0, 0)
        self._name = QLineEdit()
        self._name.setObjectName("editItemName")
        self._name.setStyleSheet(self._input_qss())
        self._name.setPlaceholderText("e.g. Hourly Labor")
        ident.addWidget(self._name, 1, 0)
        self._chk_subitem = QCheckBox("Subitem of")
        self._chk_subitem.setObjectName("editItemSubitem")
        self._chk_subitem.setStyleSheet(
            f"QCheckBox {{ color: {_IL_TEXT}; background: transparent; font-size: 12px; }}"
        )
        ident.addWidget(self._chk_subitem, 0, 1)
        self._parent = QComboBox()
        self._parent.setObjectName("editItemParent")
        self._parent.setStyleSheet(self._input_qss("QComboBox"))
        self._parent.setEnabled(False)
        ident.addWidget(self._parent, 1, 1)
        ident.setColumnStretch(0, 1)
        ident.setColumnStretch(1, 1)
        form.addLayout(ident)
        self._chk_subitem.toggled.connect(self._parent.setEnabled)

        self._chk_assemblies = QCheckBox(
            "This service is used in assemblies or is performed by a subcontractor or partner"
        )
        self._chk_assemblies.setObjectName("editItemAssemblies")
        self._chk_assemblies.setStyleSheet(
            f"QCheckBox {{ color: {_IL_TEXT}; background: transparent; font-size: 12px; }}"
        )
        form.addWidget(self._chk_assemblies)

        box = QFrame()
        box.setObjectName("editItemMainBox")
        box.setStyleSheet(
            f"QFrame#editItemMainBox {{ background: {_IL_PAPER}; border: 1px solid {_IL_GRID}; "
            "border-radius: 4px; }}"
        )
        box_lay = QGridLayout(box)
        box_lay.setContentsMargins(10, 8, 10, 8)
        box_lay.setHorizontalSpacing(12)
        box_lay.setVerticalSpacing(6)

        desc_lbl = QLabel("Description")
        desc_lbl.setStyleSheet(
            f"color: {_IL_CAPTION}; font-size: 11px; background: transparent; border: none;"
        )
        box_lay.addWidget(desc_lbl, 0, 0)
        self._description = QPlainTextEdit()
        self._description.setObjectName("editItemDescription")
        self._description.setFixedHeight(88)
        self._description.setStyleSheet(self._input_qss("QPlainTextEdit"))
        box_lay.addWidget(self._description, 1, 0, 3, 1)

        rate_lbl = QLabel("Rate")
        rate_lbl.setStyleSheet(
            f"color: {_IL_CAPTION}; font-size: 11px; background: transparent; border: none;"
        )
        box_lay.addWidget(rate_lbl, 0, 1)
        self._rate = QLineEdit()
        self._rate.setObjectName("editItemRate")
        self._rate.setStyleSheet(self._input_qss())
        self._rate.setPlaceholderText("0.00 or 3.0%")
        self._rate.setMaximumWidth(140)
        box_lay.addWidget(self._rate, 1, 1)

        acct_lbl = QLabel("Account")
        acct_lbl.setStyleSheet(
            f"color: {_IL_CAPTION}; font-size: 11px; background: transparent; border: none;"
        )
        box_lay.addWidget(acct_lbl, 2, 1)
        self._account = QComboBox()
        self._account.setObjectName("editItemAccount")
        self._account.setStyleSheet(self._input_qss("QComboBox"))
        self._account.setMaximumWidth(220)
        self._account.setEditable(True)
        self._fill_accounts()
        box_lay.addWidget(self._account, 3, 1)

        box_lay.setColumnStretch(0, 3)
        box_lay.setColumnStretch(1, 2)
        form.addWidget(box, 1)

        self._chk_inactive = QCheckBox("Item is inactive")
        self._chk_inactive.setObjectName("editItemInactive")
        self._chk_inactive.setStyleSheet(
            f"QCheckBox {{ color: {_IL_TEXT}; background: transparent; font-size: 12px; }}"
        )
        inact_row = QHBoxLayout()
        inact_row.addStretch(1)
        inact_row.addWidget(self._chk_inactive)
        form.addLayout(inact_row)

        outer.addLayout(form, 1)

        side = QVBoxLayout()
        side.setSpacing(6)
        self._btn_ok = QPushButton("OK")
        self._btn_ok.setObjectName("editItemOk")
        self._btn_ok.setDefault(True)
        self._btn_ok.setStyleSheet(_action_button_qss(primary=True))
        self._btn_ok.setFixedHeight(26)
        self._btn_ok.setFixedWidth(118)
        self._btn_ok.clicked.connect(self._on_ok)
        self._btn_cancel = QPushButton("Cancel")
        self._btn_cancel.setObjectName("editItemCancel")
        self._btn_cancel.setStyleSheet(_action_button_qss())
        self._btn_cancel.setFixedHeight(26)
        self._btn_cancel.setFixedWidth(118)
        self._btn_cancel.clicked.connect(self.reject)
        self._btn_notes = QPushButton("Notes")
        self._btn_notes.setObjectName("editItemNotes")
        self._btn_notes.setStyleSheet(_action_button_qss())
        self._btn_notes.setFixedHeight(26)
        self._btn_notes.setFixedWidth(118)
        self._btn_notes.clicked.connect(self._on_notes)
        self._btn_custom = QPushButton("Custom Fields")
        self._btn_custom.setObjectName("editItemCustomFields")
        self._btn_custom.setStyleSheet(_action_button_qss())
        self._btn_custom.setFixedHeight(26)
        self._btn_custom.setFixedWidth(118)
        self._btn_custom.clicked.connect(self._on_custom_fields)
        self._btn_spelling = QPushButton("Spelling")
        self._btn_spelling.setObjectName("editItemSpelling")
        self._btn_spelling.setStyleSheet(_action_button_qss())
        self._btn_spelling.setFixedHeight(26)
        self._btn_spelling.setFixedWidth(118)
        self._btn_spelling.clicked.connect(self._on_spelling)
        for b in (
            self._btn_ok,
            self._btn_cancel,
            self._btn_notes,
            self._btn_custom,
            self._btn_spelling,
        ):
            b.setAutoDefault(False)
            side.addWidget(b)
        side.addStretch(1)
        outer.addLayout(side)

        self._fill_parents()
        self._on_type_changed(self._type.currentText())

    def _fill_accounts(self) -> None:
        cur = self._account.currentText()
        self._account.blockSignals(True)
        self._account.clear()
        self._account.addItem("")
        for label in _income_expense_labels(self._coa_db):
            self._account.addItem(label)
        idx = self._account.findText(cur)
        self._account.setCurrentIndex(idx if idx >= 0 else 0)
        if idx < 0 and cur:
            self._account.setEditText(cur)
        self._account.blockSignals(False)

    def _fill_parents(self) -> None:
        current = coerce_combo_int_id(self._parent.currentData())
        self._parent.blockSignals(True)
        self._parent.clear()
        self._parent.addItem("", None)
        if self._ap_conn is not None:
            try:
                rows = business.list_invoice_item_codes(self._ap_conn)
            except sqlite3.Error:
                rows = []
            for row in rows:
                rid = coerce_combo_int_id(row["id"])
                if rid is None or rid == self._item_id:
                    continue
                label = str(row["code"] or "").strip()
                if not label:
                    continue
                self._parent.addItem(escape_ampersand_for_qt(label), rid)
        if current is not None:
            for i in range(self._parent.count()):
                if coerce_combo_int_id(self._parent.itemData(i)) == current:
                    self._parent.setCurrentIndex(i)
                    break
        self._parent.blockSignals(False)

    def _on_type_changed(self, text: str) -> None:
        self._type_help.setText(_TYPE_HELP.get(text, _TYPE_HELP["Service"]))
        is_service = text == "Service"
        self._chk_assemblies.setVisible(is_service)
        is_subtotal = text == "Subtotal"
        self._rate.setEnabled(not is_subtotal)
        self._account.setEnabled(not is_subtotal)

    def _load(self, item_id: int) -> None:
        row = business.get_invoice_item_code(self._ap_conn, item_id)
        if row is None:
            return
        d = dict(row)
        self._name.setText(str(d.get("code") or "").strip())
        self._description.setPlainText(str(d.get("description") or ""))
        it = str(d.get("item_type") or "Service").strip()
        idx = self._type.findText(it)
        self._type.setCurrentIndex(idx if idx >= 0 else 0)
        rv = float(d.get("rate_value") or 0.0)
        rk = str(d.get("rate_kind") or "amount")
        self._rate.setText(format_rate_display(rv, rk))
        acct = str(d.get("coa_account") or "").strip()
        aidx = self._account.findText(acct)
        if aidx >= 0:
            self._account.setCurrentIndex(aidx)
        elif acct:
            self._account.setEditText(acct)
        pid = coerce_combo_int_id(d.get("parent_id"))
        self._chk_subitem.setChecked(pid is not None)
        if pid is not None:
            for i in range(self._parent.count()):
                if coerce_combo_int_id(self._parent.itemData(i)) == pid:
                    self._parent.setCurrentIndex(i)
                    break
        self._chk_assemblies.setChecked(bool(d.get("used_in_assemblies")))
        self._chk_inactive.setChecked(bool(d.get("is_inactive")))
        self._notes = str(d.get("notes") or "")

    def collected_row(self) -> dict:
        rv, rk = parse_rate_input(self._rate.text())
        parent_id = None
        if self._chk_subitem.isChecked():
            parent_id = coerce_combo_int_id(self._parent.currentData())
        return {
            "id": self._item_id,
            "code": self._name.text().strip(),
            "description": self._description.toPlainText().strip(),
            "item_type": self._type.currentText().strip(),
            "coa_account": self._account.currentText().strip(),
            "rate_value": rv,
            "rate_kind": rk,
            "parent_id": parent_id,
            "is_inactive": self._chk_inactive.isChecked(),
            "used_in_assemblies": self._chk_assemblies.isChecked()
            and self._type.currentText() == "Service",
            "notes": self._notes,
        }

    def _on_ok(self) -> None:
        data = self.collected_row()
        if not data["code"]:
            message_box_warning_ok(
                self,
                "Edit Item",
                "Item Name/Number is required.",
                ok_tip="Enter a name, then click OK.",
            )
            return
        try:
            self._item_id = business.upsert_invoice_item_code(self._ap_conn, data)
        except (sqlite3.Error, ValueError) as exc:
            message_box_warning_ok(
                self,
                "Edit Item",
                f"Could not save: {exc}",
                ok_tip="Use a unique Item Name/Number and try again.",
            )
            return
        self.accept()

    def _on_notes(self) -> None:
        dlg = QDialog(self)
        dlg.setObjectName("editItemNotesDialog")
        dlg.setWindowTitle("Notes")
        dlg.setPalette(_light_palette())
        dlg.setAutoFillBackground(True)
        dlg.resize(360, 200)
        lay = QVBoxLayout(dlg)
        edit = QPlainTextEdit()
        edit.setPlainText(self._notes)
        edit.setStyleSheet(self._input_qss("QPlainTextEdit"))
        lay.addWidget(edit)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton("OK")
        ok.setStyleSheet(_action_button_qss(primary=True))
        cancel = QPushButton("Cancel")
        cancel.setStyleSheet(_action_button_qss())
        ok.clicked.connect(dlg.accept)
        cancel.clicked.connect(dlg.reject)
        row.addWidget(ok)
        row.addWidget(cancel)
        lay.addLayout(row)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._notes = edit.toPlainText()

    def _on_custom_fields(self) -> None:
        message_box_information_ok(
            self,
            "Custom Fields",
            "Custom fields are not set up for items yet.",
            ok_tip="Close; item custom fields can follow in a later pass.",
        )

    def _on_spelling(self) -> None:
        message_box_information_ok(
            self,
            "Spelling",
            "Spell check is not available yet.",
            ok_tip="Close and continue editing this item.",
        )


# ===========================================================================
# Item List
# ===========================================================================


class InvoiceCodesScreen(QWidget):
    """QB Pro Item List (company file). Double-click opens Edit Item."""

    codesChanged = Signal()

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        ap_conn: Optional[sqlite3.Connection] = None,
        coa_db: Optional[COADatabase] = None,
    ) -> None:
        super().__init__(parent)
        self._ap_conn = ap_conn
        self._coa_db = coa_db
        self._search_term = ""
        self._search_field = "All fields"
        self._within_ids: Optional[set[int]] = None
        self.setObjectName("itemListScreen")
        self.setToolTip(
            "Item List: items and services for invoice lines. Double-click a row to Edit Item. "
            "Same company .db as Create Invoices."
        )
        self.setPalette(_light_palette())
        self.setAutoFillBackground(True)
        self.setStyleSheet(
            f"InvoiceCodesScreen {{ background-color: {_IL_CANVAS}; color: {_IL_TEXT}; }}"
        )
        self._build_ui()
        self._load_from_db()

    def set_connections(
        self,
        ap_conn: Optional[sqlite3.Connection],
        coa_db: Optional[COADatabase],
    ) -> None:
        self._ap_conn = ap_conn
        self._coa_db = coa_db
        self._load_from_db()

    def refresh_coa_combos(self) -> None:
        """Refresh Account labels when the Chart of Accounts changes."""
        self._load_from_db()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(6)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        title = QLabel("Item List")
        title.setObjectName("itemListTitle")
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {_IL_TEXT}; background: transparent;"
        )
        title_row.addWidget(title)
        title_row.addStretch(1)
        self._btn_new = QPushButton("Item")
        self._btn_new.setObjectName("itemListNew")
        self._btn_new.setStyleSheet(_action_button_qss(primary=True))
        self._btn_new.setFixedHeight(26)
        self._btn_new.setToolTip("Create a new item (opens Edit Item).")
        self._btn_new.clicked.connect(self._on_new)
        self._btn_edit = QPushButton("Edit")
        self._btn_edit.setObjectName("itemListEdit")
        self._btn_edit.setStyleSheet(_action_button_qss())
        self._btn_edit.setFixedHeight(26)
        self._btn_edit.setEnabled(False)
        self._btn_edit.setToolTip("Edit the selected item (or double-click a row).")
        self._btn_edit.clicked.connect(self._on_edit)
        self._btn_inactive = QPushButton("Make Inactive")
        self._btn_inactive.setObjectName("itemListInactive")
        self._btn_inactive.setStyleSheet(_action_button_qss())
        self._btn_inactive.setFixedHeight(26)
        self._btn_inactive.setEnabled(False)
        self._btn_inactive.setToolTip("Hide the selected item from invoice line pickers.")
        self._btn_inactive.clicked.connect(self._on_make_inactive)
        self._chk_inactive = QCheckBox("Include inactive")
        self._chk_inactive.setObjectName("itemListIncludeInactive")
        self._chk_inactive.setStyleSheet(
            f"QCheckBox {{ color: {_IL_TEXT}; background: transparent; font-size: 12px; }}"
        )
        self._chk_inactive.toggled.connect(self._load_from_db)
        title_row.addWidget(self._btn_new)
        title_row.addWidget(self._btn_edit)
        title_row.addWidget(self._btn_inactive)
        title_row.addWidget(self._chk_inactive)
        outer.addLayout(title_row)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        look = QLabel("Look for")
        look.setObjectName("itemListLookLabel")
        look.setStyleSheet(
            f"color: {_IL_CAPTION}; font-size: 12px; background: transparent; border: none;"
        )
        search_row.addWidget(look)
        self._search = QLineEdit()
        self._search.setObjectName("itemListSearch")
        self._search.setPlaceholderText("Name, description, type…")
        self._search.setFixedHeight(26)
        self._search.setMinimumWidth(180)
        self._search.setStyleSheet(
            f"QLineEdit {{ background: {_IL_PAPER}; border: 1px solid {_IL_GRID}; "
            f"border-radius: 3px; padding: 2px 8px; color: {_IL_TEXT}; }}"
        )
        self._search.returnPressed.connect(self._on_search)
        search_row.addWidget(self._search, 1)
        in_lbl = QLabel("in")
        in_lbl.setStyleSheet(
            f"color: {_IL_CAPTION}; font-size: 12px; background: transparent; border: none;"
        )
        search_row.addWidget(in_lbl)
        self._field = QComboBox()
        self._field.setObjectName("itemListSearchField")
        self._field.setFixedHeight(26)
        self._field.setStyleSheet(
            f"QComboBox {{ background: {_IL_PAPER}; border: 1px solid {_IL_GRID}; "
            f"padding: 2px 8px; color: {_IL_TEXT}; }}"
        )
        for f in _SEARCH_FIELDS:
            self._field.addItem(f)
        search_row.addWidget(self._field)
        self._btn_search = QPushButton("Search")
        self._btn_search.setObjectName("itemListSearchBtn")
        self._btn_search.setStyleSheet(_action_button_qss(primary=True))
        self._btn_search.setFixedHeight(26)
        self._btn_search.clicked.connect(self._on_search)
        search_row.addWidget(self._btn_search)
        self._btn_reset = QPushButton("Reset")
        self._btn_reset.setObjectName("itemListResetBtn")
        self._btn_reset.setStyleSheet(_action_button_qss())
        self._btn_reset.setFixedHeight(26)
        self._btn_reset.setToolTip("Clear the search filter and show all items.")
        self._btn_reset.clicked.connect(self._on_reset_search)
        search_row.addWidget(self._btn_reset)
        self._chk_within = QCheckBox("Search within results")
        self._chk_within.setObjectName("itemListSearchWithin")
        self._chk_within.setStyleSheet(
            f"QCheckBox {{ color: {_IL_TEXT}; background: transparent; font-size: 12px; }}"
        )
        self._chk_within.setToolTip(
            "When checked, Search looks only at the rows currently shown."
        )
        search_row.addWidget(self._chk_within)
        outer.addLayout(search_row)

        self._table = QTableWidget()
        self._table.setObjectName("itemListTable")
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(
            ["", "NAME", "DESCRIPTION", "TYPE", "ACCOUNT", "PRICE", "ATTACH"]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(True)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(_COL_MARK, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(_COL_NAME, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_DESC, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(_COL_TYPE, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_ACCT, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(_COL_PRICE, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_ATTACH, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(_COL_MARK, 22)
        self._table.setColumnWidth(_COL_ATTACH, 56)
        self._table.verticalHeader().setDefaultSectionSize(24)
        self._table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._table.setStyleSheet(
            f"QTableWidget#itemListTable {{"
            f" background-color: {_IL_PAPER};"
            f" alternate-background-color: {_IL_STRIPE};"
            f" color: {_IL_TEXT};"
            f" gridline-color: {_IL_GRID};"
            f" border: 1px solid {_IL_GRID};"
            f"}}"
            f"QTableWidget#itemListTable::item:selected {{"
            f" background-color: {_IL_SELECT}; color: {_IL_SELECT_FG};"
            f"}}"
            f"QHeaderView::section {{"
            f" background-color: {_IL_HEADER}; color: {_IL_ACCENT};"
            f" font-weight: 700; font-size: 11px; padding: 4px 6px;"
            f" border: 1px solid {_IL_GRID};"
            f"}}"
        )
        self._table.itemSelectionChanged.connect(self._on_selection)
        self._table.doubleClicked.connect(self._on_row_double_clicked)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        self._table.setSortingEnabled(False)
        self._table.setToolTip(
            "Item List: double-click a row to open Edit Item. "
            "Saved items fill Create Invoices line Codes."
        )
        outer.addWidget(self._table, stretch=1)

        self._lbl_count = QLabel("")
        self._lbl_count.setObjectName("itemListCount")
        self._lbl_count.setStyleSheet(
            f"color: {_IL_CAPTION}; font-size: 11px; background: transparent;"
        )
        outer.addWidget(self._lbl_count)

        sc_refresh = QShortcut(QKeySequence("F5"), self)
        sc_refresh.setContext(Qt.WidgetWithChildrenShortcut)
        sc_refresh.activated.connect(self._load_from_db)
        sc_edit = QShortcut(QKeySequence("Return"), self._table)
        sc_edit.setContext(Qt.WidgetWithChildrenShortcut)
        sc_edit.activated.connect(self._on_edit)

    def _on_search(self) -> None:
        self._search_term = (self._search.text() or "").strip()
        self._search_field = self._field.currentText() or "All fields"
        if not self._chk_within.isChecked():
            self._within_ids = None
        self._load_from_db()
        if self._chk_within.isChecked():
            self._within_ids = self._shown_ids()

    def _on_reset_search(self) -> None:
        self._search.clear()
        self._field.setCurrentIndex(0)
        self._chk_within.setChecked(False)
        self._search_term = ""
        self._search_field = "All fields"
        self._within_ids = None
        self._load_from_db()

    def _shown_ids(self) -> set[int]:
        ids: set[int] = set()
        for r in range(self._table.rowCount()):
            it = self._table.item(r, _COL_NAME)
            if it is None:
                continue
            iid = coerce_combo_int_id(it.data(_ROLE_ITEM_ID))
            if iid is not None:
                ids.add(iid)
        return ids

    def _on_selection(self) -> None:
        has = self._selected_id() is not None
        self._btn_edit.setEnabled(has)
        self._btn_inactive.setEnabled(has)

    def _selected_id(self) -> Optional[int]:
        r = self._table.currentRow()
        if r < 0:
            return None
        it = self._table.item(r, _COL_NAME)
        if it is None:
            return None
        return coerce_combo_int_id(it.data(_ROLE_ITEM_ID))

    def _make_edit_dialog(self, item_id: Optional[int] = None) -> Optional[EditItemDialog]:
        if self._ap_conn is None:
            message_box_warning_ok(
                self,
                "Item List",
                "Open a company file before editing items.",
                ok_tip="Use File → Open company…",
            )
            return None
        return EditItemDialog(
            self._ap_conn,
            item_id=item_id,
            coa_db=self._coa_db,
            parent=self,
        )

    def _run_edit_dialog(self, item_id: Optional[int] = None) -> None:
        dlg = self._make_edit_dialog(item_id)
        if dlg is None:
            return
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load_from_db()
            self.codesChanged.emit()
            saved = dlg._item_id
            if saved is not None:
                self._select_item_id(saved)

    def _on_new(self) -> None:
        self._run_edit_dialog(None)

    def _on_edit(self) -> None:
        iid = self._selected_id()
        if iid is None:
            return
        self._run_edit_dialog(iid)

    def _on_row_double_clicked(self, *_args: object) -> None:
        self._on_edit()

    def _on_make_inactive(self) -> None:
        iid = self._selected_id()
        if iid is None or self._ap_conn is None:
            return
        try:
            business.set_invoice_item_inactive(self._ap_conn, iid, inactive=True)
        except sqlite3.Error as exc:
            message_box_warning_ok(
                self,
                "Item List",
                f"Could not update: {exc}",
                ok_tip="Close and try again.",
            )
            return
        self._load_from_db()
        self.codesChanged.emit()

    def _on_context_menu(self, pos) -> None:
        menu = QMenu(self)
        act_new = menu.addAction("New Item…", self._on_new)
        act_new.setToolTip("Open Edit Item for a new catalog row.")
        idx = self._table.indexAt(pos)
        if idx.isValid():
            self._table.selectRow(idx.row())
            act_edit = menu.addAction("Edit Item…", self._on_edit)
            act_edit.setToolTip("Open the compact Edit Item dialog for this row.")
            act_inact = menu.addAction("Make Inactive", self._on_make_inactive)
            act_inact.setToolTip("Hide this item from invoice line pickers.")
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _select_item_id(self, item_id: int) -> None:
        want = coerce_combo_int_id(item_id)
        if want is None:
            return
        for r in range(self._table.rowCount()):
            it = self._table.item(r, _COL_NAME)
            if it is None:
                continue
            if coerce_combo_int_id(it.data(_ROLE_ITEM_ID)) == want:
                self._table.selectRow(r)
                self._table.scrollToItem(it)
                break

    def _load_from_db(self) -> None:
        include_inactive = self._chk_inactive.isChecked()
        db_rows: list = []
        if self._ap_conn is not None:
            try:
                db_rows = list(
                    business.list_invoice_item_codes(
                        self._ap_conn, include_inactive=include_inactive
                    )
                )
            except sqlite3.Error:
                db_rows = []

        needle = self._search_term.lower()
        field = self._search_field or "All fields"
        if needle:
            db_rows = [
                row for row in db_rows if needle in _item_search_blob(row, field)
            ]
        if self._within_ids is not None:
            db_rows = [
                row
                for row in db_rows
                if coerce_combo_int_id(row["id"]) in self._within_ids
            ]

        packed = ordered_item_rows(db_rows)
        self._table.setRowCount(len(packed))
        inactive_n = 0
        for r, (row, depth) in enumerate(packed):
            d = dict(row)
            iid = coerce_combo_int_id(d.get("id"))
            if iid is None:
                continue
            inactive = bool(d.get("is_inactive"))
            if inactive:
                inactive_n += 1
            mark = "✕" if inactive else "◆"
            m_it = plain_display_table_item(mark)
            m_it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            m_it.setData(_ROLE_ITEM_ID, iid)
            m_it.setToolTip("Inactive item" if inactive else "Item")
            self._table.setItem(r, _COL_MARK, m_it)

            indent = "    " * depth
            name_it = plain_display_table_item(indent + str(d.get("code") or ""))
            name_it.setData(_ROLE_ITEM_ID, iid)
            name_it.setData(_ROLE_DEPTH, depth)
            name_it.setData(_ROLE_ACTIVE, 0 if inactive else 1)
            if depth > 0:
                font = QFont(name_it.font())
                font.setItalic(True)
                name_it.setFont(font)
            self._table.setItem(r, _COL_NAME, name_it)
            self._table.setItem(
                r, _COL_DESC, plain_display_table_item(str(d.get("description") or ""))
            )
            self._table.setItem(
                r, _COL_TYPE, plain_display_table_item(str(d.get("item_type") or ""))
            )
            self._table.setItem(
                r, _COL_ACCT, plain_display_table_item(str(d.get("coa_account") or ""))
            )
            price = format_rate_display(
                float(d.get("rate_value") or 0.0),
                str(d.get("rate_kind") or "amount"),
            )
            p_it = plain_display_table_item(price)
            p_it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(r, _COL_PRICE, p_it)
            att = plain_display_table_item("")
            att.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            att.setToolTip("Attachments on this item (none yet).")
            self._table.setItem(r, _COL_ATTACH, att)

        extra = f"  ({inactive_n} inactive)" if include_inactive and inactive_n else ""
        n = len(packed)
        self._lbl_count.setText(f"{n} item{'s' if n != 1 else ''}{extra}")
        self._on_selection()


# Public alias matching the on-screen title.
ItemListScreen = InvoiceCodesScreen
