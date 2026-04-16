"""Clipboard helpers for ``QTableWidget`` and ``QListWidget``.

Read-only text cells should use :func:`plain_display_table_item` (Qt-escaped ``text()``,
verbatim string on ``QTABLE_PLAIN_TEXT_ROLE`` for **Copy row** / TSV). Amounts and
sortable numeric columns use :class:`NumericAmountTableItem`, :class:`IntSortTableItem`,
or :class:`FloatSortTableItem`. Lists with escaped labels set ``QLIST_PLAIN_TEXT_ROLE``.
Inline-editable cells stay plain ``QTableWidgetItem`` unless editing is delegated.
``CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX`` is the shared **File → Backup** line for copy QActions.
``VIEW_BANK_REGISTER_KEYS_TOOLTIP`` is the shared **View → Bank Import / Register** line plus a
**Recon** menu pointer for register row actions, for **Keyboard shortcuts…** QActions on non-bank tabs.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QListWidget,
    QLineEdit,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
)

from desktop_app.qt_mnemonic import escape_ampersand_for_qt

# Verbatim line for "Copy …" on ``QListWidget`` rows whose ``.text()`` is
# ``escape_ampersand_for_qt``-wrapped (so clipboard matches DB/UI strings).
QLIST_PLAIN_TEXT_ROLE = Qt.ItemDataRole.UserRole + 32

# Same for ``QTableWidgetItem`` cells (optional per-cell; see ``_table_cell_text``).
QTABLE_PLAIN_TEXT_ROLE = Qt.ItemDataRole.UserRole + 33

# Suffix for QActions (and similar tips) that copy company SQLite–backed data; keep in sync with File → Backup.
CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX = (
    "Company .db safety: File → Backup / Restore (probooks.backup)."
)

# Mid-sentence fragment for **Keyboard shortcuts…** on tabs that open **Help → More / Business / Intake** dialogs.
VIEW_BANK_REGISTER_KEYS_TOOLTIP = (
    "Bank CSV/PDF and AI line reconciliation: View → Bank Import (Ctrl+3); "
    "Match overlay on Register (Ctrl+8). "
    "Register bulk actions: Recon menu. "
)


def plain_display_table_item(raw: str) -> QTableWidgetItem:
    """Read-only cell: Qt-escaped ``text()``, verbatim string for copy/TSV."""
    it = QTableWidgetItem(escape_ampersand_for_qt(raw))
    it.setData(QTABLE_PLAIN_TEXT_ROLE, raw)
    return it


class NumericAmountTableItem(QTableWidgetItem):
    """Comma-formatted currency string; sorts by numeric *amount*; copy uses plain role."""

    def __init__(self, amount: float) -> None:
        disp = f"{amount:,.2f}"
        super().__init__(escape_ampersand_for_qt(disp))
        self._amount = amount
        self.setData(QTABLE_PLAIN_TEXT_ROLE, disp)

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, NumericAmountTableItem):
            return self._amount < other._amount
        return super().__lt__(other)


class IntSortTableItem(QTableWidgetItem):
    """Integer sort key; ``text()`` Qt-escaped; copy/TSV uses ``QTABLE_PLAIN_TEXT_ROLE``."""

    def __init__(self, display: str, sort_key: int) -> None:
        super().__init__(escape_ampersand_for_qt(display))
        self._sort_key = sort_key
        self.setData(QTABLE_PLAIN_TEXT_ROLE, display)

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, IntSortTableItem):
            return self._sort_key < other._sort_key
        return super().__lt__(other)


class FloatSortTableItem(QTableWidgetItem):
    """Float sort key; same escape + plain role as :class:`IntSortTableItem`."""

    def __init__(self, display: str, sort_key: float) -> None:
        super().__init__(escape_ampersand_for_qt(display))
        self._sort_key = sort_key
        self.setData(QTABLE_PLAIN_TEXT_ROLE, display)

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, FloatSortTableItem):
            return self._sort_key < other._sort_key
        return super().__lt__(other)


def copy_qlistwidget_row_text(list_widget: QListWidget, row: int) -> None:
    """Copy the item at *row*; use ``QLIST_PLAIN_TEXT_ROLE`` when set (verbatim line)."""
    it = list_widget.item(row)
    if it is None:
        QGuiApplication.clipboard().setText("")
        return
    plain = it.data(QLIST_PLAIN_TEXT_ROLE)
    if isinstance(plain, str):
        QGuiApplication.clipboard().setText(plain)
    else:
        QGuiApplication.clipboard().setText(it.text())


def _table_cell_text(table: QTableWidget, row: int, col: int) -> str:
    """Text for one cell: ``QTableWidgetItem`` or common embedded widgets."""
    w = table.cellWidget(row, col)
    if w is not None:
        if isinstance(w, QDoubleSpinBox):
            return f"{w.value():.2f}"
        if isinstance(w, QSpinBox):
            return str(int(w.value()))
        if isinstance(w, QAbstractSpinBox):
            return (w.text() or "").strip()
        if isinstance(w, QCheckBox):
            return "Yes" if w.isChecked() else "No"
        if isinstance(w, QLineEdit):
            return w.text()
        if isinstance(w, QComboBox):
            d = w.currentData(Qt.ItemDataRole.UserRole)
            if d is not None:
                if isinstance(d, str):
                    return d
                return str(d)
            return (w.currentText() or "").strip()
        return ""
    it = table.item(row, col)
    if it is None:
        return ""
    plain = it.data(QTABLE_PLAIN_TEXT_ROLE)
    if isinstance(plain, str):
        return plain
    return it.text()


def copy_table_row_as_tsv(table: QTableWidget, row: int) -> None:
    """Copy visible cells in *row* as one tab-separated line."""
    parts = [_table_cell_text(table, row, c) for c in range(table.columnCount())]
    QGuiApplication.clipboard().setText("\t".join(parts))


def table_cell_clipboard_text(table: QTableWidget, row: int, col: int) -> str:
    """Clipboard-oriented text for one cell (plain role, combo ``userData``, etc.)."""
    return _table_cell_text(table, row, col)
