"""``desktop_app.table_clipboard`` — requires PySide6 (install ``.[ci]`` or ``.[desktop]``; CI uses ``.[ci]`` + ``QT_QPA_PLATFORM=offscreen``)."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtGui import QGuiApplication
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QTableWidget,
    QTableWidgetItem,
)

from desktop_app.qt_mnemonic import escape_ampersand_for_qt
from desktop_app.table_clipboard import (
    CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX,
    QLIST_PLAIN_TEXT_ROLE,
    QTABLE_PLAIN_TEXT_ROLE,
    VIEW_BANK_REGISTER_KEYS_TOOLTIP,
    FloatSortTableItem,
    IntSortTableItem,
    NumericAmountTableItem,
    _table_cell_text,
    copy_qlistwidget_row_text,
    copy_table_row_as_tsv,
    plain_display_table_item,
    table_cell_clipboard_text,
)


def test_view_bank_register_keys_tooltip_strings() -> None:
    assert "Bank Import (Ctrl+3)" in VIEW_BANK_REGISTER_KEYS_TOOLTIP
    assert "Register (Ctrl+8)" in VIEW_BANK_REGISTER_KEYS_TOOLTIP
    assert "Recon menu" in VIEW_BANK_REGISTER_KEYS_TOOLTIP
    assert VIEW_BANK_REGISTER_KEYS_TOOLTIP.endswith(" ")
    assert CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX not in VIEW_BANK_REGISTER_KEYS_TOOLTIP


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_table_cell_text_items(qapp):
    t = QTableWidget(1, 2)
    t.setItem(0, 0, QTableWidgetItem("a"))
    t.setItem(0, 1, QTableWidgetItem("b"))
    assert _table_cell_text(t, 0, 0) == "a"
    assert _table_cell_text(t, 0, 1) == "b"


def test_table_cell_text_prefers_qtable_plain_text_role(qapp):
    t = QTableWidget(1, 1)
    raw = "A & B"
    it = QTableWidgetItem(escape_ampersand_for_qt(raw))
    it.setData(QTABLE_PLAIN_TEXT_ROLE, raw)
    t.setItem(0, 0, it)
    assert _table_cell_text(t, 0, 0) == raw


def test_numeric_amount_table_item_sorts_and_copies_plain(qapp):
    hi = NumericAmountTableItem(1000.0)
    lo = NumericAmountTableItem(200.0)
    assert lo.__lt__(hi) is True
    assert hi.__lt__(lo) is False
    t = QTableWidget(1, 1)
    t.setItem(0, 0, NumericAmountTableItem(-12.5))
    assert _table_cell_text(t, 0, 0) == "-12.50"


def test_plain_display_table_item_verbatim_for_copy_and_helpers(qapp):
    t = QTableWidget(1, 1)
    raw = "A & B"
    t.setItem(0, 0, plain_display_table_item(raw))
    assert _table_cell_text(t, 0, 0) == raw
    assert table_cell_clipboard_text(t, 0, 0) == raw
    assert t.item(0, 0).text() == escape_ampersand_for_qt(raw)


def test_int_sort_table_item_copy_prefers_plain_role(qapp):
    """``IntSortTableItem`` uses escaped ``text()`` and plain role for copy/TSV."""
    raw = "10 & 20"
    t = QTableWidget(1, 1)
    t.setItem(0, 0, IntSortTableItem(raw, 999))
    assert _table_cell_text(t, 0, 0) == raw
    assert t.item(0, 0).text() == escape_ampersand_for_qt(raw)


def test_float_sort_table_item_copy_and_sort(qapp):
    disp = "1,234.50"
    t = QTableWidget(2, 1)
    hi = FloatSortTableItem(disp, 1234.5)
    lo = FloatSortTableItem("9.00", 9.0)
    assert lo.__lt__(hi) is True
    assert hi.__lt__(lo) is False
    t.setItem(0, 0, FloatSortTableItem("10 & 00", 10.0))
    assert _table_cell_text(t, 0, 0) == "10 & 00"
    assert t.item(0, 0).text() == escape_ampersand_for_qt("10 & 00")


def test_table_row_entity_id_uses_plain_text_role(qapp):
    from PySide6.QtCore import Qt

    from desktop_app.extra_tabs import _table_row_entity_id

    t = QTableWidget(1, 1)
    t.setItem(0, 0, IntSortTableItem("42", 42))
    assert _table_row_entity_id(t, 0) == 42
    assert _table_row_entity_id(t, -1) is None
    assert _table_row_entity_id(t, 5) is None

    t2 = QTableWidget(1, 1)
    t2.setItem(0, 0, QTableWidgetItem("7"))
    assert _table_row_entity_id(t2, 0) == 7

    t3 = QTableWidget(1, 1)
    it3 = IntSortTableItem("1", 1)
    it3.setData(Qt.ItemDataRole.UserRole, 999)
    t3.setItem(0, 0, it3)
    assert _table_row_entity_id(t3, 0) == 999


def test_table_cell_text_double_spin(qapp):
    t = QTableWidget(1, 1)
    sp = QDoubleSpinBox()
    sp.setDecimals(2)
    sp.setValue(12.5)
    t.setCellWidget(0, 0, sp)
    assert _table_cell_text(t, 0, 0) == "12.50"


def test_table_cell_text_combo_and_line_edit(qapp):
    t = QTableWidget(1, 2)
    cb = QComboBox()
    cb.addItems(["Alpha", "Beta"])
    cb.setCurrentIndex(1)
    t.setCellWidget(0, 0, cb)
    le = QLineEdit("x")
    t.setCellWidget(0, 1, le)
    assert _table_cell_text(t, 0, 0) == "Beta"
    assert _table_cell_text(t, 0, 1) == "x"


def test_table_cell_text_combo_prefers_userdata_raw_value(qapp):
    """Register COA (and similar) combos store raw account in ``userData``."""
    t = QTableWidget(1, 1)
    cb = QComboBox()
    raw = "5010 – Office & Supplies"
    cb.addItem(escape_ampersand_for_qt(raw), raw)
    cb.setCurrentIndex(0)
    t.setCellWidget(0, 0, cb)
    assert _table_cell_text(t, 0, 0) == raw


def test_table_cell_text_checkbox(qapp):
    t = QTableWidget(1, 1)
    cx = QCheckBox()
    cx.setChecked(True)
    t.setCellWidget(0, 0, cx)
    assert _table_cell_text(t, 0, 0) == "Yes"
    cx.setChecked(False)
    assert _table_cell_text(t, 0, 0) == "No"


def test_copy_qlistwidget_prefers_plain_text_role(qapp):
    lw = QListWidget()
    plain = "2024-01-01  #1  Memo & co."
    it = QListWidgetItem(escape_ampersand_for_qt(plain))
    it.setData(Qt.ItemDataRole.UserRole, 99)
    it.setData(QLIST_PLAIN_TEXT_ROLE, plain)
    lw.addItem(it)
    copy_qlistwidget_row_text(lw, 0)
    assert QGuiApplication.clipboard().text() == plain


def test_copy_table_row_as_tsv_mixed(qapp):
    t = QTableWidget(1, 4)
    t.setItem(0, 0, QTableWidgetItem("id-1"))
    t.setItem(0, 1, QTableWidgetItem(""))
    sp = QDoubleSpinBox()
    sp.setDecimals(2)
    sp.setValue(99.0)
    t.setCellWidget(0, 2, sp)
    t.setItem(0, 3, QTableWidgetItem("tail"))
    copy_table_row_as_tsv(t, 0)
    assert QGuiApplication.clipboard().text() == "id-1\t\t99.00\ttail"


def test_inbox_selected_doc_id_prefers_user_role(qapp):
    """Intake ``#`` column: ``UserRole`` holds doc id; copy still uses plain-display role."""
    from desktop_app.main import InboxWidget

    w = InboxWidget()
    w.populate(
        [
            {
                "id": 42,
                "filename": " Stmt & Co.pdf",
                "mimetype": "application/pdf",
                "status": "imported",
                "import_date": "2025-06-01",
            }
        ]
    )
    w.selectRow(0)
    assert w.selected_doc_id() == 42
    assert isinstance(w.item(0, 0), IntSortTableItem)


def test_inbox_selected_doc_id_falls_back_to_plain_cell_text(qapp):
    """If ``UserRole`` is unset, id still parses from ``QTABLE_PLAIN_TEXT_ROLE`` / display."""
    from desktop_app.main import InboxWidget

    w = InboxWidget()
    w.setRowCount(1)
    w.setColumnCount(5)
    w.setHorizontalHeaderLabels(InboxWidget.COLUMNS)
    w.setItem(0, 0, plain_display_table_item("7"))
    w.selectRow(0)
    assert w.selected_doc_id() == 7


def test_coa_account_number_table_item(qapp):
    from desktop_app.coa_tab import _CoaAccountNumberTableItem

    hi = _CoaAccountNumberTableItem("100", 1)
    lo = _CoaAccountNumberTableItem("20", 2)
    assert lo.__lt__(hi) is True
    assert hi.__lt__(lo) is False

    aa = _CoaAccountNumberTableItem("5010-A", 3)
    ab = _CoaAccountNumberTableItem("5010-B", 4)
    assert aa.__lt__(ab) is True

    t = QTableWidget(1, 1)
    cell = _CoaAccountNumberTableItem("5&10", 99)
    t.setItem(0, 0, cell)
    assert cell.data(Qt.ItemDataRole.UserRole) == 99
    assert _table_cell_text(t, 0, 0) == "5&10"
