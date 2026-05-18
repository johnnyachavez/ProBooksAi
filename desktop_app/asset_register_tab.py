"""
desktop_app.asset_register_tab
================================
Fixed-asset register UI: track cost, depreciation, and book value.

Replaces the need to import decade-old check-register lines just to record
that a piece of equipment was bought in 2015. One row here (with an
opening-balance journal entry) is enough for balance-sheet accuracy.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from probooksai.asset_register import ASSET_TYPES, DEPRECIATION_METHODS, AssetRegister
from desktop_app.theme import (
    WORKFLOW_ALT_ROW,
    WORKFLOW_CAPTION,
    WORKFLOW_CONTROL_FACE,
    WORKFLOW_CONTROL_HOVER,
    WORKFLOW_CONTROL_PRESSED,
    WORKFLOW_GRID,
    WORKFLOW_HEADER_BG,
    WORKFLOW_INPUT_BG,
    WORKFLOW_PAGE_BG,
    WORKFLOW_PANEL_BG,
    WORKFLOW_STRIP_BTN_OUTLINE,
    WORKFLOW_TEXT,
)
from desktop_app.qt_mnemonic import message_box_information_ok, message_box_warning_ok

_COLS = ("Name", "Type", "Purchase Date", "Cost", "Salvage", "Life (yrs)", "Method", "Book Value", "COA Account")
_MONEY_FMT = "${:,.2f}"


def _money_spin(max_val: float = 99_999_999.0) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setMaximum(max_val)
    s.setDecimals(2)
    s.setPrefix("$ ")
    return s


def _plain_item(text: str) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
    return it


# ---------------------------------------------------------------------------
# Add / Edit asset dialog
# ---------------------------------------------------------------------------

class AssetDialog(QDialog):
    def __init__(self, parent=None, *, asset_row=None, coa_list: list[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Add Asset" if asset_row is None else "Edit Asset")
        self.setMinimumWidth(440)
        self._asset_row = asset_row
        self._build_ui(coa_list or [])
        if asset_row:
            self._populate(asset_row)

    def _build_ui(self, coa_list: list[str]) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self._name = QLineEdit()
        self._name.setPlaceholderText("e.g. Delivery Truck, Office Computer")
        form.addRow("Name *:", self._name)

        self._desc = QLineEdit()
        self._desc.setPlaceholderText("Optional description")
        form.addRow("Description:", self._desc)

        self._type = QComboBox()
        self._type.addItems(ASSET_TYPES)
        form.addRow("Asset type:", self._type)

        self._purchase_date = QLineEdit()
        self._purchase_date.setPlaceholderText("YYYY-MM-DD")
        form.addRow("Purchase date:", self._purchase_date)

        self._cost = _money_spin()
        form.addRow("Cost (original):", self._cost)

        self._salvage = _money_spin()
        form.addRow("Salvage value:", self._salvage)

        self._life = QDoubleSpinBox()
        self._life.setRange(0.5, 100.0)
        self._life.setDecimals(1)
        self._life.setValue(5.0)
        self._life.setSuffix(" years")
        form.addRow("Useful life:", self._life)

        self._method = QComboBox()
        self._method.addItems(["Straight-line", "Declining balance (2×)", "No depreciation"])
        form.addRow("Depreciation:", self._method)

        self._coa = QComboBox()
        self._coa.setEditable(True)
        self._coa.addItem("")
        for c in coa_list:
            self._coa.addItem(c)
        form.addRow("COA account:", self._coa)

        self._notes = QLineEdit()
        self._notes.setPlaceholderText("Optional notes")
        form.addRow("Notes:", self._notes)

        layout.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._validate_and_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _populate(self, row) -> None:
        self._name.setText(row["name"] or "")
        self._desc.setText(row["description"] or "")
        idx = self._type.findText(row["asset_type"] or "Equipment")
        if idx >= 0:
            self._type.setCurrentIndex(idx)
        self._purchase_date.setText(row["purchase_date"] or "")
        self._cost.setValue(float(row["cost"] or 0))
        self._salvage.setValue(float(row["salvage_value"] or 0))
        self._life.setValue(float(row["useful_life_years"] or 5))
        method_map = {"straight_line": 0, "declining_balance": 1, "none": 2}
        self._method.setCurrentIndex(method_map.get(row["depreciation_method"] or "straight_line", 0))
        coa = row["coa_account"] or ""
        idx = self._coa.findText(coa)
        if idx >= 0:
            self._coa.setCurrentIndex(idx)
        else:
            self._coa.setEditText(coa)
        self._notes.setText(row["notes"] or "")

    def _validate_and_accept(self) -> None:
        if not self._name.text().strip():
            QMessageBox.warning(self, "Missing field", "Asset name is required.")
            return
        self.accept()

    def _method_key(self) -> str:
        return ["straight_line", "declining_balance", "none"][self._method.currentIndex()]

    def values(self) -> dict:
        return {
            "name": self._name.text().strip(),
            "description": self._desc.text().strip(),
            "asset_type": self._type.currentText(),
            "purchase_date": self._purchase_date.text().strip() or None,
            "cost": self._cost.value(),
            "salvage_value": self._salvage.value(),
            "useful_life_years": self._life.value(),
            "depreciation_method": self._method_key(),
            "coa_account": self._coa.currentText().strip() or None,
            "notes": self._notes.text().strip(),
        }


# ---------------------------------------------------------------------------
# Asset Register Tab
# ---------------------------------------------------------------------------

class AssetRegisterTab(QWidget):
    """Fixed-asset register: list, add, edit, deactivate assets with live book value."""

    assetsChanged = Signal()

    def __init__(self, conn, coa_list: list[str] | None = None, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._coa_list = coa_list or []
        self._db = AssetRegister(conn)
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(8)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("Fixed Asset Register")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {WORKFLOW_TEXT};")
        hdr.addWidget(title)
        hdr.addStretch(1)

        sub = QLabel("Track cost and depreciation without importing historical check-register lines.")
        sub.setStyleSheet(f"color: {WORKFLOW_CAPTION}; font-size: 11px;")

        outer.addLayout(hdr)
        outer.addWidget(sub)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        btn_style = (
            f"QPushButton {{ background: {WORKFLOW_CONTROL_FACE}; color: {WORKFLOW_TEXT}; "
            f"border: 1px solid {WORKFLOW_STRIP_BTN_OUTLINE}; border-radius: 4px; padding: 4px 14px; }}"
            f"QPushButton:hover {{ background: {WORKFLOW_CONTROL_HOVER}; }}"
            f"QPushButton:pressed {{ background: {WORKFLOW_CONTROL_PRESSED}; }}"
        )
        self._btn_add = QPushButton("Add Asset")
        self._btn_add.setToolTip("Add a new fixed asset to the register.")
        self._btn_edit = QPushButton("Edit")
        self._btn_edit.setToolTip("Edit the selected asset.")
        self._btn_deactivate = QPushButton("Retire Asset")
        self._btn_deactivate.setToolTip("Mark the selected asset as retired (hides from active list).")
        self._chk_inactive = QPushButton("Show Retired")
        self._chk_inactive.setCheckable(True)
        self._chk_inactive.setToolTip("Show retired/inactive assets.")
        for btn in (self._btn_add, self._btn_edit, self._btn_deactivate, self._chk_inactive):
            btn.setStyleSheet(btn_style)
            toolbar.addWidget(btn)
        toolbar.addStretch(1)

        self._lbl_total = QLabel("Total book value: $0.00")
        self._lbl_total.setStyleSheet(f"color: {WORKFLOW_TEXT}; font-weight: 600; font-size: 13px;")
        toolbar.addWidget(self._lbl_total)
        outer.addLayout(toolbar)

        # Table
        self._table = QTableWidget(0, len(_COLS))
        self._table.setHorizontalHeaderLabels(list(_COLS))
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSortingEnabled(True)
        hh = self._table.horizontalHeader()
        hh.setStretchLastSection(True)
        for i in range(len(_COLS) - 1):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setStyleSheet(
            f"QTableWidget {{ background: {WORKFLOW_PANEL_BG}; alternate-background-color: {WORKFLOW_ALT_ROW}; "
            f"color: {WORKFLOW_TEXT}; gridline-color: {WORKFLOW_GRID}; border: 1px solid {WORKFLOW_GRID}; }}"
            f"QHeaderView::section {{ background: {WORKFLOW_HEADER_BG}; color: {WORKFLOW_TEXT}; "
            f"padding: 6px; border: 1px solid {WORKFLOW_GRID}; font-weight: 600; }}"
        )
        outer.addWidget(self._table, 1)

        # Signals
        self._btn_add.clicked.connect(self._on_add)
        self._btn_edit.clicked.connect(self._on_edit)
        self._btn_deactivate.clicked.connect(self._on_deactivate)
        self._chk_inactive.toggled.connect(lambda _: self._refresh())

    # -- data ----------------------------------------------------------------

    def _refresh(self) -> None:
        show_inactive = self._chk_inactive.isChecked()
        rows = self._db.list_assets(include_inactive=show_inactive)
        today = date.today().isoformat()

        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(rows))
        total_bv = 0.0
        for r, row in enumerate(rows):
            bv = self._db.book_value(row["id"], today)
            total_bv += bv
            self._table.setItem(r, 0, self._cell(row["name"] or "", row["id"]))
            self._table.setItem(r, 1, _plain_item(row["asset_type"] or ""))
            self._table.setItem(r, 2, _plain_item(row["purchase_date"] or ""))
            self._table.setItem(r, 3, _plain_item(_MONEY_FMT.format(row["cost"] or 0)))
            self._table.setItem(r, 4, _plain_item(_MONEY_FMT.format(row["salvage_value"] or 0)))
            self._table.setItem(r, 5, _plain_item(str(row["useful_life_years"] or 0)))
            method_label = {
                "straight_line": "Straight-line",
                "declining_balance": "Declining (2×)",
                "none": "None",
            }.get(row["depreciation_method"] or "", row["depreciation_method"] or "")
            self._table.setItem(r, 6, _plain_item(method_label))
            bv_item = _plain_item(_MONEY_FMT.format(bv))
            if not row["is_active"]:
                bv_item.setForeground(Qt.GlobalColor.gray)
            self._table.setItem(r, 7, bv_item)
            self._table.setItem(r, 8, _plain_item(row["coa_account"] or ""))
        self._table.setSortingEnabled(True)
        self._lbl_total.setText(f"Total book value: {_MONEY_FMT.format(total_bv)}")

    def _cell(self, text: str, asset_id: int) -> QTableWidgetItem:
        it = _plain_item(text)
        it.setData(Qt.ItemDataRole.UserRole, asset_id)
        return it

    def _selected_id(self) -> Optional[int]:
        r = self._table.currentRow()
        if r < 0:
            return None
        it = self._table.item(r, 0)
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    # -- actions -------------------------------------------------------------

    def _on_add(self) -> None:
        dlg = AssetDialog(self, coa_list=self._coa_list)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            vals = dlg.values()
            self._db.add_asset(**vals)
            self._refresh()
            self.assetsChanged.emit()

    def _on_edit(self) -> None:
        aid = self._selected_id()
        if aid is None:
            message_box_information_ok(self, "No selection", "Select an asset to edit.")
            return
        row = self._db.get_asset(aid)
        if not row:
            return
        dlg = AssetDialog(self, asset_row=row, coa_list=self._coa_list)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._db.update_asset(aid, dlg.values())
            self._refresh()
            self.assetsChanged.emit()

    def _on_deactivate(self) -> None:
        aid = self._selected_id()
        if aid is None:
            message_box_information_ok(self, "No selection", "Select an asset to retire.")
            return
        row = self._db.get_asset(aid)
        if not row:
            return
        res = QMessageBox.question(
            self,
            "Retire Asset",
            f"Retire '{row['name']}'?\nIt will be hidden from the active list but kept for historical records.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if res == QMessageBox.StandardButton.Yes:
            self._db.deactivate_asset(aid)
            self._refresh()
            self.assetsChanged.emit()

    def update_coa_list(self, coa_list: list[str]) -> None:
        self._coa_list = coa_list
