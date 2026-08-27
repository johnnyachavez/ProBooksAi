"""Income Tracker and Bill Tracker — QuickBooks Pro Desktop-style AR/AP lists.

Colored summary tiles, filter bar, and a roomy transaction grid. Totals come
from the open company file (invoices, payments, bills) — not screenshot figures.
Slightly cleaner spacing than a gray Win32 photocopy; not QuickBooks Online.

Double-click an invoice → Create Invoices; ACTION Receive Payment → Receive
Payments. Double-click a bill → Enter Bills; ACTION Pay Bill → Pay Bills.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QPalette, QShortcut, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from desktop_app.flexible_date import format_iso_to_us_display
from desktop_app.qt_combo_ids import coerce_combo_int_id
from desktop_app.qt_mnemonic import escape_ampersand_for_qt, message_box_information_ok
from desktop_app.table_clipboard import FloatSortTableItem, IntSortTableItem, plain_display_table_item
from probooksai import trackers as tr

_TK_CANVAS = "#E8ECF1"
_TK_PAPER = "#FFFFFF"
_TK_PANEL = "#F4F7FA"
_TK_STRIPE = "#E8F1FA"
_TK_CAPTION = "#4A5560"
_TK_GRID = "#C0C8D0"
_TK_HEADER = "#D8DEE6"
_TK_TEXT = "#1A1A1A"
_TK_TITLE = "#5B6770"
_TK_ACCENT = "#2563A8"
_TK_SELECT = "#2E7D32"
_TK_SELECT_FG = "#FFFFFF"
_TK_OVERDUE = "#C62828"
_STRIP_BTN_OUTLINE = "#B4BCC6"

_TILE_UNBILLED = "#1E4E8C"
_TILE_OPEN = "#E08A1E"
_TILE_OVERDUE = "#B42318"
_TILE_PAID = "#7CB342"
_TILE_GROUP = "#F0F3F6"

_ROLE_KIND = Qt.ItemDataRole.UserRole
_ROLE_RECORD_ID = Qt.ItemDataRole.UserRole + 1
_ROLE_PARTY_ID = Qt.ItemDataRole.UserRole + 2
_ROLE_GROUP = Qt.ItemDataRole.UserRole + 3

_INCOME_HEADERS = (
    "",
    "CUSTOMER",
    "TYPE",
    "NUMBER",
    "DATE",
    "DUE DATE",
    "AMOUNT",
    "OPEN BALANCE",
    "LAST SENT DATE",
    "STATUS",
    "ACTION",
)
_BILL_HEADERS = (
    "",
    "VENDOR",
    "TYPE",
    "NUMBER",
    "DATE",
    "DUE DATE",
    "STATUS",
    "AMOUNT",
    "OPEN BALANCE",
    "ACTION",
)

_COL_CHECK = 0
_IN_COL_PARTY = 1
_IN_COL_TYPE = 2
_IN_COL_NUM = 3
_IN_COL_DATE = 4
_IN_COL_DUE = 5
_IN_COL_AMT = 6
_IN_COL_BAL = 7
_IN_COL_SENT = 8
_IN_COL_STATUS = 9
_IN_COL_ACTION = 10

_BL_COL_PARTY = 1
_BL_COL_TYPE = 2
_BL_COL_NUM = 3
_BL_COL_DATE = 4
_BL_COL_DUE = 5
_BL_COL_STATUS = 6
_BL_COL_AMT = 7
_BL_COL_BAL = 8
_BL_COL_ACTION = 9

def _fmt_money(value: float) -> str:
    return f"{float(value or 0):,.2f}"


def _action_button_qss(*, primary: bool = False) -> str:
    if primary:
        return (
            f"QPushButton {{ background-color: {_TK_ACCENT}; border: 1px solid {_TK_ACCENT}; "
            "border-radius: 4px; color: #FFFFFF; font-size: 12px; padding: 0 12px; "
            "font-weight: 600; }"
            "QPushButton:hover { background-color: #1D4F8C; }"
            "QPushButton:pressed { background-color: #163E6E; }"
            "QPushButton:disabled { color: #D7E3F0; background-color: #8AA7C7; }"
        )
    return (
        f"QPushButton {{ background-color: #F7F8FA; border: 1px solid {_STRIP_BTN_OUTLINE}; "
        f"border-radius: 4px; color: {_TK_TEXT}; font-size: 12px; padding: 0 12px; }}"
        "QPushButton:hover { background-color: #E4EEF7; }"
        "QPushButton:pressed { background-color: #C9D8EC; }"
        "QPushButton:disabled { color: #8A94A0; }"
    )


def _tool_button_qss() -> str:
    return (
        f"QToolButton {{ background-color: #F7F8FA; border: 1px solid {_STRIP_BTN_OUTLINE}; "
        f"border-radius: 4px; color: {_TK_TEXT}; font-size: 12px; padding: 0 12px; }}"
        "QToolButton:hover { background-color: #E4EEF7; }"
        "QToolButton:pressed { background-color: #C9D8EC; }"
        "QToolButton::menu-indicator { width: 10px; }"
    )


def _light_palette() -> QPalette:
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(_TK_CANVAS))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(_TK_TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(_TK_PAPER))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(_TK_STRIPE))
    pal.setColor(QPalette.ColorRole.Text, QColor(_TK_TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(_TK_PAPER))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(_TK_TEXT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(_TK_SELECT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(_TK_SELECT_FG))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(_TK_CAPTION))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(_TK_PANEL))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(_TK_TEXT))
    return pal


def _combo_qss() -> str:
    return (
        f"QComboBox {{ background: {_TK_PAPER}; border: 1px solid {_TK_GRID}; "
        f"padding: 2px 8px; color: {_TK_TEXT}; min-height: 22px; }}"
    )


def _pay_bill_button_qss() -> str:
    return (
        "QToolButton { background: #F4FBF4; border: 1px solid #2E7D32; "
        "padding: 2px 10px; color: #1B5E20; min-height: 22px; font-weight: 600; }"
        "QToolButton:hover { background: #E3F4E3; }"
        "QToolButton::menu-indicator { width: 10px; }"
    )


class _SummaryTile(QFrame):
    """Clickable colored KPI tile (amount + count caption)."""

    clicked = Signal(str)

    def __init__(
        self,
        key: str,
        fill: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._key = key
        self._fill = fill
        self._selected = False
        self.setObjectName(f"trackerTile_{key}")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(150)
        self.setMinimumHeight(72)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)
        self._amount = QLabel("0.00")
        self._amount.setObjectName(f"trackerTileAmount_{key}")
        self._amount.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._caption = QLabel("")
        self._caption.setObjectName(f"trackerTileCaption_{key}")
        self._caption.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._caption.setWordWrap(True)
        lay.addWidget(self._amount)
        lay.addWidget(self._caption)
        self._apply_style()

    def set_values(self, amount: float, caption: str) -> None:
        self._amount.setText(_fmt_money(amount))
        self._caption.setText(caption)

    def set_selected(self, selected: bool) -> None:
        self._selected = bool(selected)
        self._apply_style()

    def _apply_style(self) -> None:
        ring = "3px solid #FFFFFF" if self._selected else "1px solid rgba(0,0,0,0.12)"
        self.setStyleSheet(
            f"QFrame#{self.objectName()} {{ background: {self._fill}; border: {ring}; "
            "border-radius: 4px; }"
            f"QLabel {{ color: #FFFFFF; background: transparent; border: none; }}"
        )
        self._amount.setStyleSheet(
            "color: #FFFFFF; background: transparent; border: none; "
            "font-size: 22px; font-weight: 700;"
        )
        self._caption.setStyleSheet(
            "color: #FFFFFF; background: transparent; border: none; "
            "font-size: 11px; font-weight: 700; letter-spacing: 0.06em;"
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._key)
        super().mousePressEvent(event)


class _TrackerScreenBase(QWidget):
    """Shared tiles + filters + grid + footer. Subclasses fill columns."""

    openInvoiceRequested = Signal(int)
    receivePaymentRequested = Signal(int)
    openArPaymentRequested = Signal(int)
    openBillRequested = Signal(int)
    payBillRequested = Signal(int)

    def __init__(self, conn: Optional[sqlite3.Connection], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._conn = conn
        self._tile = tr.TILE_ALL
        self._all_rows: list[dict] = []
        self._visible_rows: list[dict] = []
        self._paid_ids: set[int] = set()
        self.setAutoFillBackground(True)
        self.setPalette(_light_palette())

    def set_connection(self, conn: Optional[sqlite3.Connection]) -> None:
        self._conn = conn
        self.reload()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self.reload()

    def _input_combo(self, object_name: str, items: tuple[str, ...]) -> QComboBox:
        cb = QComboBox()
        cb.setObjectName(object_name)
        cb.setStyleSheet(_combo_qss())
        cb.addItems(list(items))
        cb.currentIndexChanged.connect(self._on_filters_changed)
        return cb

    def _filter_field(self, caption: str, widget: QWidget) -> QWidget:
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(1)
        lbl = QLabel(caption)
        lbl.setStyleSheet(
            f"color: {_TK_CAPTION}; font-size: 10px; font-weight: 700; "
            "letter-spacing: 0.04em; background: transparent; border: none;"
        )
        lay.addWidget(lbl)
        lay.addWidget(widget)
        return wrap

    def _build_filter_bar(self, fields: list[tuple[str, QWidget]]) -> QFrame:
        bar = QFrame()
        bar.setObjectName("trackerFilterBar")
        bar.setStyleSheet(
            f"QFrame#trackerFilterBar {{ background: #D5DCE4; border: 1px solid {_TK_GRID}; }}"
        )
        row = QHBoxLayout(bar)
        row.setContentsMargins(10, 6, 10, 6)
        row.setSpacing(10)
        for caption, widget in fields:
            row.addWidget(self._filter_field(caption, widget))
        row.addStretch(1)
        return bar

    def _build_table(self, object_name: str, headers: tuple[str, ...]) -> QTableWidget:
        table = QTableWidget()
        table.setObjectName(object_name)
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(list(headers))
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(True)
        table.verticalHeader().setDefaultSectionSize(26)
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        table.setStyleSheet(
            f"QTableWidget#{object_name} {{"
            f" background-color: {_TK_PAPER};"
            f" alternate-background-color: {_TK_STRIPE};"
            f" color: {_TK_TEXT};"
            f" gridline-color: {_TK_GRID};"
            f" border: 1px solid {_TK_GRID};"
            "}"
            f"QTableWidget#{object_name}::item:selected {{"
            f" background-color: {_TK_SELECT}; color: {_TK_SELECT_FG};"
            "}"
            "QHeaderView::section {"
            f" background-color: {_TK_HEADER}; color: {_TK_ACCENT};"
            " font-weight: 700; font-size: 11px; padding: 4px 6px;"
            f" border: 1px solid {_TK_GRID};"
            "}"
        )
        table.doubleClicked.connect(self._on_row_double_clicked)
        table.setSortingEnabled(True)
        return table

    def _build_footer(self) -> QFrame:
        foot = QFrame()
        foot.setObjectName("trackerFooter")
        foot.setStyleSheet(
            f"QFrame#trackerFooter {{ background: {_TK_PANEL}; border-top: 1px solid {_TK_GRID}; }}"
        )
        row = QHBoxLayout(foot)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(8)
        self._btn_batch = QToolButton()
        self._btn_batch.setObjectName("trackerBatchActions")
        self._btn_batch.setText("Batch Actions")
        self._btn_batch.setStyleSheet(_tool_button_qss())
        self._btn_batch.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._btn_batch.setFixedHeight(26)
        batch_menu = QMenu(self._btn_batch)
        self._fill_batch_menu(batch_menu)
        self._btn_batch.setMenu(batch_menu)
        self._btn_batch.setToolTip("Actions for checked tracker rows.")
        self._btn_manage = QToolButton()
        self._btn_manage.setObjectName("trackerManageTransactions")
        self._btn_manage.setText("Manage Transactions")
        self._btn_manage.setStyleSheet(_tool_button_qss())
        self._btn_manage.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._btn_manage.setFixedHeight(26)
        manage_menu = QMenu(self._btn_manage)
        self._fill_manage_menu(manage_menu)
        self._btn_manage.setMenu(manage_menu)
        self._btn_manage.setToolTip("Open or pay the selected row.")
        row.addWidget(self._btn_batch)
        row.addWidget(self._btn_manage)
        row.addStretch(1)
        self._lbl_count = QLabel("Showing 0 - 0 of 0")
        self._lbl_count.setObjectName("trackerShowingCount")
        self._lbl_count.setStyleSheet(
            f"color: {_TK_CAPTION}; font-size: 12px; background: transparent; border: none;"
        )
        self._btn_prev = QPushButton("‹")
        self._btn_prev.setObjectName("trackerPagePrev")
        self._btn_prev.setFixedSize(26, 26)
        self._btn_prev.setStyleSheet(_action_button_qss())
        self._btn_prev.setEnabled(False)
        self._btn_prev.setToolTip("Previous page (all visible rows are on this page).")
        self._btn_next = QPushButton("›")
        self._btn_next.setObjectName("trackerPageNext")
        self._btn_next.setFixedSize(26, 26)
        self._btn_next.setStyleSheet(_action_button_qss())
        self._btn_next.setEnabled(False)
        self._btn_next.setToolTip("Next page (all visible rows are on this page).")
        row.addWidget(self._lbl_count)
        row.addWidget(self._btn_prev)
        row.addWidget(self._btn_next)
        return foot

    def _fill_batch_menu(self, menu: QMenu) -> None:
        raise NotImplementedError

    def _fill_manage_menu(self, menu: QMenu) -> None:
        raise NotImplementedError

    def _on_filters_changed(self, *_args) -> None:
        self._rebuild_visible()

    def _on_tile_clicked(self, key: str) -> None:
        if self._tile == key:
            self._tile = tr.TILE_ALL
        else:
            self._tile = key
        self._sync_tile_selection()
        self._rebuild_visible()

    def _sync_tile_selection(self) -> None:
        for tile in self.findChildren(_SummaryTile):
            tile.set_selected(tile._key == self._tile)

    def _party_filter_id(self) -> Optional[int]:
        return coerce_combo_int_id(self._party.currentData())

    def _row_dict_at_visual(self, visual_row: int) -> Optional[dict]:
        """Map a *visual* table row to tracker data (survives column sort)."""
        it = self._table.item(visual_row, _COL_CHECK)
        if it is None:
            return None
        kind = str(it.data(_ROLE_KIND) or "")
        rec = int(it.data(_ROLE_RECORD_ID) or 0)
        if not kind or kind == "group" or rec <= 0:
            return None
        for row in self._visible_rows:
            if (row.get("kind") or "") == kind and int(row.get("record_id") or 0) == rec:
                return row
        return None

    def _checked_rows(self) -> list[dict]:
        out: list[dict] = []
        for i in range(self._table.rowCount()):
            it = self._table.item(i, _COL_CHECK)
            if it is not None and it.checkState() == Qt.CheckState.Checked:
                row = self._row_dict_at_visual(i)
                if row is not None:
                    out.append(row)
        return out

    def _selected_row(self) -> Optional[dict]:
        r = self._table.currentRow()
        if r < 0:
            return None
        return self._row_dict_at_visual(r)

    def _on_row_double_clicked(self, index) -> None:
        if index is None:
            return
        row = self._row_dict_at_visual(index.row())
        if row is not None:
            self._open_row(row)

    def _open_row(self, row: dict) -> None:
        raise NotImplementedError

    def _money_item(self, value: float) -> QTableWidgetItem:
        amount = float(value or 0)
        it = FloatSortTableItem(_fmt_money(amount), amount)
        it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return it

    def _date_item(self, iso: str) -> QTableWidgetItem:
        display = format_iso_to_us_display(iso or "")
        compact = (iso or "").replace("-", "")[:8]
        sort_key = int(compact) if compact.isdigit() else 0
        it = IntSortTableItem(display, sort_key)
        it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return it

    def _text_item(self, text: str, *, overdue: bool = False) -> QTableWidgetItem:
        it = plain_display_table_item(text)
        it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if overdue:
            it.setForeground(QColor(_TK_OVERDUE))
            font = QFont(it.font())
            font.setBold(True)
            it.setFont(font)
        return it

    def _check_item(self, row: dict) -> QTableWidgetItem:
        it = QTableWidgetItem("")
        it.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsUserCheckable
        )
        it.setCheckState(Qt.CheckState.Unchecked)
        it.setData(_ROLE_KIND, row.get("kind") or "")
        it.setData(_ROLE_RECORD_ID, int(row.get("record_id") or 0))
        it.setData(_ROLE_PARTY_ID, int(row.get("party_id") or 0))
        it.setData(_ROLE_GROUP, 0)
        return it

    def _stamp_ids(self, item: QTableWidgetItem, row: dict) -> None:
        item.setData(_ROLE_KIND, row.get("kind") or "")
        item.setData(_ROLE_RECORD_ID, int(row.get("record_id") or 0))
        item.setData(_ROLE_PARTY_ID, int(row.get("party_id") or 0))

    def _set_showing(self, n: int, total: int) -> None:
        if n <= 0:
            self._lbl_count.setText("Showing 0 of 0")
        else:
            self._lbl_count.setText(f"Showing 1 - {n} of {total}")

    def _on_settings(self) -> None:
        message_box_information_ok(
            self,
            "Tracker settings",
            "Tracker layout uses the open company file. Tile totals refresh from "
            "live invoices, payments, and bills.",
            ok_tip="Close and continue using the tracker.",
        )


class IncomeTrackerScreen(_TrackerScreenBase):
    """QB Pro Income Tracker: unbilled / unpaid / paid tiles + invoice/payment grid."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        ap_conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        super().__init__(ap_conn, parent)
        self.setObjectName("incomeTrackerScreen")
        self.setToolTip(
            "Income Tracker: unbilled time & expenses, open and overdue invoices, "
            "and payments in the last 30 days. Double-click an invoice to open Create Invoices. "
            "Same company .db as other tabs (File → Backup / Restore, probooks.backup)."
        )
        self.setStyleSheet(
            f"IncomeTrackerScreen {{ background-color: {_TK_CANVAS}; color: {_TK_TEXT}; }}"
        )
        self._build_ui()
        sc = QShortcut(QKeySequence("F5"), self)
        sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc.activated.connect(self.reload)
        self.reload()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(6)

        title = QLabel("Income Tracker")
        title.setObjectName("incomeTrackerTitle")
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {_TK_TITLE}; background: transparent;"
        )
        outer.addWidget(title)
        outer.addWidget(self._build_tiles())

        self._party = QComboBox()
        self._party.setObjectName("incomeTrackerCustomer")
        self._party.setStyleSheet(_combo_qss())
        self._party.currentIndexChanged.connect(self._on_filters_changed)
        self._type = self._input_combo("incomeTrackerType", ("All", tr.TYPE_INVOICE, tr.TYPE_PAYMENT))
        self._status = self._input_combo(
            "incomeTrackerStatus", ("All", tr.STATUS_OPEN, tr.STATUS_OVERDUE, tr.STATUS_PAID)
        )
        self._date = self._input_combo("incomeTrackerDate", tr.DATE_CHOICES)
        outer.addWidget(
            self._build_filter_bar(
                [
                    ("CUSTOMER:JOB", self._party),
                    ("TYPE", self._type),
                    ("STATUS", self._status),
                    ("DATE", self._date),
                ]
            )
        )

        self._table = self._build_table("incomeTrackerTable", _INCOME_HEADERS)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(_COL_CHECK, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(_COL_CHECK, 28)
        hdr.setSectionResizeMode(_IN_COL_PARTY, QHeaderView.ResizeMode.Stretch)
        for col in (
            _IN_COL_TYPE,
            _IN_COL_NUM,
            _IN_COL_DATE,
            _IN_COL_DUE,
            _IN_COL_AMT,
            _IN_COL_BAL,
            _IN_COL_SENT,
            _IN_COL_STATUS,
        ):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_IN_COL_ACTION, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(_IN_COL_ACTION, 150)
        self._table.setToolTip(
            "Income Tracker grid: invoices and payments. Double-click an invoice to "
            "open Create Invoices. ACTION can Receive Payment or open the invoice."
        )
        outer.addWidget(self._table, 1)
        outer.addWidget(self._build_footer())

    def _build_tiles(self) -> QWidget:
        wrap = QWidget()
        row = QHBoxLayout(wrap)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        unbilled_col = QVBoxLayout()
        unbilled_col.setSpacing(2)
        unbilled_hdr = QLabel("UNBILLED")
        unbilled_hdr.setStyleSheet(
            f"color: {_TK_CAPTION}; font-size: 10px; font-weight: 700; letter-spacing: 0.08em;"
        )
        unbilled_col.addWidget(unbilled_hdr)
        self._tile_unbilled = _SummaryTile(tr.TILE_UNBILLED, _TILE_UNBILLED)
        self._tile_unbilled.clicked.connect(self._on_tile_clicked)
        unbilled_col.addWidget(self._tile_unbilled)
        row.addLayout(unbilled_col, 1)

        unpaid = QFrame()
        unpaid.setObjectName("incomeUnpaidGroup")
        unpaid.setStyleSheet(
            f"QFrame#incomeUnpaidGroup {{ background: {_TILE_GROUP}; border: 1px solid {_TK_GRID}; "
            "border-radius: 4px; }"
        )
        ug = QVBoxLayout(unpaid)
        ug.setContentsMargins(6, 4, 6, 6)
        ug.setSpacing(4)
        uh = QLabel("UNPAID")
        uh.setStyleSheet(
            f"color: {_TK_CAPTION}; font-size: 10px; font-weight: 700; letter-spacing: 0.08em;"
        )
        ug.addWidget(uh)
        inner = QHBoxLayout()
        inner.setSpacing(6)
        self._tile_open = _SummaryTile(tr.TILE_OPEN, _TILE_OPEN)
        self._tile_overdue = _SummaryTile(tr.TILE_OVERDUE, _TILE_OVERDUE)
        self._tile_open.clicked.connect(self._on_tile_clicked)
        self._tile_overdue.clicked.connect(self._on_tile_clicked)
        inner.addWidget(self._tile_open)
        inner.addWidget(self._tile_overdue)
        ug.addLayout(inner)
        row.addWidget(unpaid, 2)

        paid_col = QVBoxLayout()
        paid_col.setSpacing(2)
        paid_hdr = QLabel("PAID")
        paid_hdr.setStyleSheet(
            f"color: {_TK_CAPTION}; font-size: 10px; font-weight: 700; letter-spacing: 0.08em;"
        )
        paid_col.addWidget(paid_hdr)
        self._tile_paid = _SummaryTile(tr.TILE_PAID_30, _TILE_PAID)
        self._tile_paid.clicked.connect(self._on_tile_clicked)
        paid_col.addWidget(self._tile_paid)
        row.addLayout(paid_col, 1)

        gear = QPushButton("⚙")
        gear.setObjectName("incomeTrackerSettings")
        gear.setFixedSize(28, 28)
        gear.setStyleSheet(_action_button_qss())
        gear.setToolTip("Tracker settings.")
        gear.clicked.connect(self._on_settings)
        row.addWidget(gear, 0, Qt.AlignmentFlag.AlignBottom)
        return wrap

    def _fill_batch_menu(self, menu: QMenu) -> None:
        menu.addAction("Receive Payment", self._on_batch_receive)
        menu.addAction("Open Invoice", self._on_batch_open)

    def _fill_manage_menu(self, menu: QMenu) -> None:
        menu.addAction("Open Invoice", self._on_manage_open)
        menu.addAction("Receive Payment", self._on_manage_receive)

    def reload(self) -> None:
        self._all_rows = []
        summary = {
            "unbilled_total": 0.0,
            "unbilled_count": 0,
            "open_total": 0.0,
            "open_count": 0,
            "overdue_total": 0.0,
            "overdue_count": 0,
            "paid_30_total": 0.0,
            "paid_30_count": 0,
            "paid_invoice_ids": set(),
        }
        if self._conn is not None:
            try:
                self._all_rows = tr.list_income_tracker_rows(self._conn)
                summary = tr.income_tracker_summary(self._conn)
            except sqlite3.Error:
                self._all_rows = []
        self._paid_ids = set(summary.get("paid_invoice_ids") or set())
        self._tile_unbilled.set_values(
            float(summary["unbilled_total"]),
            f"{int(summary['unbilled_count'])} TIME & EXPENSES",
        )
        self._tile_open.set_values(
            float(summary["open_total"]),
            f"{int(summary['open_count'])} OPEN INVOICES",
        )
        self._tile_overdue.set_values(
            float(summary["overdue_total"]),
            f"{int(summary['overdue_count'])} OVERDUE",
        )
        self._tile_paid.set_values(
            float(summary["paid_30_total"]),
            f"{int(summary['paid_30_count'])} PAID LAST 30 DAYS",
        )
        self._populate_party()
        self._rebuild_visible()

    def _populate_party(self) -> None:
        current = self._party_filter_id()
        self._party.blockSignals(True)
        self._party.clear()
        self._party.addItem("All", None)
        names: dict[int, str] = {}
        for row in self._all_rows:
            names[int(row["party_id"])] = row["party_name"]
        for pid, name in sorted(names.items(), key=lambda kv: kv[1].lower()):
            self._party.addItem(escape_ampersand_for_qt(name), pid)
        if current is not None:
            for i in range(self._party.count()):
                if coerce_combo_int_id(self._party.itemData(i)) == current:
                    self._party.setCurrentIndex(i)
                    break
        self._party.blockSignals(False)

    def filter_to_customer(self, customer_id: int) -> None:
        """Tiny Customer Center hook: CUSTOMER:JOB = *customer_id*."""
        self.reload()
        want = int(customer_id)
        for i in range(self._party.count()):
            if coerce_combo_int_id(self._party.itemData(i)) == want:
                self._party.setCurrentIndex(i)
                return

    def _rebuild_visible(self) -> None:
        self._visible_rows = tr.filter_tracker_rows(
            self._all_rows,
            party_id=self._party_filter_id(),
            type_name=self._type.currentText(),
            status_name=self._status.currentText(),
            date_preset=self._date.currentText(),
            tile=self._tile,
            paid_ids=self._paid_ids,
        )
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(self._visible_rows))
        for i, row in enumerate(self._visible_rows):
            overdue = row.get("status") == tr.STATUS_OVERDUE
            chk = self._check_item(row)
            self._table.setItem(i, _COL_CHECK, chk)
            party = self._text_item(row.get("party_name") or "")
            self._stamp_ids(party, row)
            self._table.setItem(i, _IN_COL_PARTY, party)
            self._table.setItem(i, _IN_COL_TYPE, self._text_item(row.get("type") or ""))
            self._table.setItem(i, _IN_COL_NUM, self._text_item(row.get("number") or ""))
            self._table.setItem(i, _IN_COL_DATE, self._date_item(row.get("date") or ""))
            self._table.setItem(i, _IN_COL_DUE, self._date_item(row.get("due_date") or ""))
            self._table.setItem(i, _IN_COL_AMT, self._money_item(float(row.get("amount") or 0)))
            self._table.setItem(
                i, _IN_COL_BAL, self._money_item(float(row.get("open_balance") or 0))
            )
            self._table.setItem(i, _IN_COL_SENT, self._date_item(row.get("last_sent_date") or ""))
            self._table.setItem(
                i, _IN_COL_STATUS, self._text_item(row.get("status") or "", overdue=overdue)
            )
            self._table.setCellWidget(i, _IN_COL_ACTION, self._make_income_action(row, i))
        self._table.setSortingEnabled(True)
        self._table.sortItems(_IN_COL_DATE, Qt.SortOrder.DescendingOrder)
        n = len(self._visible_rows)
        self._set_showing(n, n)

    def _make_income_action(self, row: dict, index: int) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName(f"incomeTrackerAction_{index}")
        btn.setText("Select")
        btn.setStyleSheet(_tool_button_qss())
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        menu = QMenu(btn)
        if row.get("kind") == "invoice":
            if float(row.get("open_balance") or 0) > 0.005:
                menu.addAction(
                    "Receive Payment",
                    lambda r=row: self.receivePaymentRequested.emit(int(r.get("record_id") or 0)),
                )
            menu.addAction("Open Invoice", lambda r=row: self._open_row(r))
        else:
            menu.addAction("Open Payment", lambda r=row: self.openArPaymentRequested.emit(int(r.get("record_id") or 0)))
        btn.setMenu(menu)
        return btn

    def _open_row(self, row: dict) -> None:
        rid = int(row.get("record_id") or 0)
        if rid <= 0:
            return
        if row.get("kind") == "invoice":
            self.openInvoiceRequested.emit(rid)
        else:
            self.openArPaymentRequested.emit(rid)

    def _on_batch_receive(self) -> None:
        rows = [r for r in self._checked_rows() if r.get("kind") == "invoice"]
        if not rows:
            rows = [r for r in [self._selected_row()] if r and r.get("kind") == "invoice"]
        if not rows:
            return
        self.receivePaymentRequested.emit(int(rows[0]["record_id"]))

    def _on_batch_open(self) -> None:
        rows = self._checked_rows() or ([self._selected_row()] if self._selected_row() else [])
        if rows:
            self._open_row(rows[0])

    def _on_manage_open(self) -> None:
        row = self._selected_row()
        if row:
            self._open_row(row)

    def _on_manage_receive(self) -> None:
        row = self._selected_row()
        if row and row.get("kind") == "invoice":
            self.receivePaymentRequested.emit(int(row["record_id"]))


class BillTrackerScreen(_TrackerScreenBase):
    """QB Pro Bill Tracker: unpaid / overdue / paid tiles + vendor bill grid."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        ap_conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        super().__init__(ap_conn, parent)
        self.setObjectName("billTrackerScreen")
        self.setToolTip(
            "Bill Tracker: open bills, overdue bills, and vendor payments in the last 30 days. "
            "Double-click a bill to open Enter Bills. ACTION Pay Bill opens Pay Bills. "
            "Same company .db as other tabs (File → Backup / Restore, probooks.backup)."
        )
        self.setStyleSheet(
            f"BillTrackerScreen {{ background-color: {_TK_CANVAS}; color: {_TK_TEXT}; }}"
        )
        self._build_ui()
        sc = QShortcut(QKeySequence("F5"), self)
        sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        sc.activated.connect(self.reload)
        self.reload()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(6)

        title = QLabel("Bill Tracker")
        title.setObjectName("billTrackerTitle")
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {_TK_TITLE}; background: transparent;"
        )
        outer.addWidget(title)
        outer.addWidget(self._build_tiles())

        self._party = QComboBox()
        self._party.setObjectName("billTrackerVendor")
        self._party.setStyleSheet(_combo_qss())
        self._party.currentIndexChanged.connect(self._on_filters_changed)
        self._type = self._input_combo("billTrackerType", ("All", tr.TYPE_BILL))
        self._status = self._input_combo(
            "billTrackerStatus", ("All", tr.STATUS_OPEN, tr.STATUS_OVERDUE, tr.STATUS_PAID)
        )
        self._date = self._input_combo("billTrackerDate", tr.DATE_CHOICES)
        self._group = self._input_combo("billTrackerGroupBy", ("None", "Vendor"))
        outer.addWidget(
            self._build_filter_bar(
                [
                    ("VENDOR", self._party),
                    ("TYPE", self._type),
                    ("STATUS", self._status),
                    ("DATE", self._date),
                    ("GROUP BY", self._group),
                ]
            )
        )

        self._table = self._build_table("billTrackerTable", _BILL_HEADERS)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(_COL_CHECK, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(_COL_CHECK, 28)
        hdr.setSectionResizeMode(_BL_COL_PARTY, QHeaderView.ResizeMode.Stretch)
        for col in (
            _BL_COL_TYPE,
            _BL_COL_NUM,
            _BL_COL_DATE,
            _BL_COL_DUE,
            _BL_COL_STATUS,
            _BL_COL_AMT,
            _BL_COL_BAL,
        ):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_BL_COL_ACTION, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(_BL_COL_ACTION, 130)
        self._table.setToolTip(
            "Bill Tracker grid. Double-click a bill to open Enter Bills. "
            "ACTION Pay Bill opens Pay Bills with that bill selected."
        )
        outer.addWidget(self._table, 1)
        outer.addWidget(self._build_footer())

    def _build_tiles(self) -> QWidget:
        wrap = QWidget()
        row = QHBoxLayout(wrap)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        unpaid = QFrame()
        unpaid.setObjectName("billUnpaidGroup")
        unpaid.setStyleSheet(
            f"QFrame#billUnpaidGroup {{ background: {_TILE_GROUP}; border: 1px solid {_TK_GRID}; "
            "border-radius: 4px; }"
        )
        ug = QVBoxLayout(unpaid)
        ug.setContentsMargins(6, 4, 6, 6)
        ug.setSpacing(4)
        uh = QLabel("UNPAID")
        uh.setStyleSheet(
            f"color: {_TK_CAPTION}; font-size: 10px; font-weight: 700; letter-spacing: 0.08em;"
        )
        ug.addWidget(uh)
        inner = QHBoxLayout()
        inner.setSpacing(6)
        self._tile_open = _SummaryTile(tr.TILE_OPEN, _TILE_OPEN)
        self._tile_overdue = _SummaryTile(tr.TILE_OVERDUE, _TILE_OVERDUE)
        self._tile_open.clicked.connect(self._on_tile_clicked)
        self._tile_overdue.clicked.connect(self._on_tile_clicked)
        inner.addWidget(self._tile_open)
        inner.addWidget(self._tile_overdue)
        ug.addLayout(inner)
        row.addWidget(unpaid, 2)

        paid_col = QVBoxLayout()
        paid_col.setSpacing(2)
        paid_hdr = QLabel("PAID")
        paid_hdr.setStyleSheet(
            f"color: {_TK_CAPTION}; font-size: 10px; font-weight: 700; letter-spacing: 0.08em;"
        )
        paid_col.addWidget(paid_hdr)
        self._tile_paid = _SummaryTile(tr.TILE_PAID_30, _TILE_PAID)
        self._tile_paid.clicked.connect(self._on_tile_clicked)
        paid_col.addWidget(self._tile_paid)
        row.addLayout(paid_col, 1)

        gear = QPushButton("⚙")
        gear.setObjectName("billTrackerSettings")
        gear.setFixedSize(28, 28)
        gear.setStyleSheet(_action_button_qss())
        gear.setToolTip("Tracker settings.")
        gear.clicked.connect(self._on_settings)
        row.addWidget(gear, 0, Qt.AlignmentFlag.AlignBottom)
        return wrap

    def _fill_batch_menu(self, menu: QMenu) -> None:
        menu.addAction("Pay Bill", self._on_batch_pay)
        menu.addAction("Open Bill", self._on_batch_open)

    def _fill_manage_menu(self, menu: QMenu) -> None:
        menu.addAction("Open Bill", self._on_manage_open)
        menu.addAction("Pay Bill", self._on_manage_pay)

    def reload(self) -> None:
        self._all_rows = []
        summary = {
            "open_total": 0.0,
            "open_count": 0,
            "overdue_total": 0.0,
            "overdue_count": 0,
            "paid_30_total": 0.0,
            "paid_30_count": 0,
            "paid_bill_ids": set(),
        }
        if self._conn is not None:
            try:
                self._all_rows = tr.list_bill_tracker_rows(self._conn)
                summary = tr.bill_tracker_summary(self._conn)
            except sqlite3.Error:
                self._all_rows = []
        self._paid_ids = set(summary.get("paid_bill_ids") or set())
        self._tile_open.set_values(
            float(summary["open_total"]),
            f"{int(summary['open_count'])} OPEN BILLS",
        )
        self._tile_overdue.set_values(
            float(summary["overdue_total"]),
            f"{int(summary['overdue_count'])} OVERDUE",
        )
        self._tile_paid.set_values(
            float(summary["paid_30_total"]),
            f"{int(summary['paid_30_count'])} PAID IN LAST 30 DAYS",
        )
        self._populate_party()
        self._rebuild_visible()

    def _populate_party(self) -> None:
        current = self._party_filter_id()
        self._party.blockSignals(True)
        self._party.clear()
        self._party.addItem("All", None)
        names: dict[int, str] = {}
        for row in self._all_rows:
            names[int(row["party_id"])] = row["party_name"]
        for pid, name in sorted(names.items(), key=lambda kv: kv[1].lower()):
            self._party.addItem(escape_ampersand_for_qt(name), pid)
        if current is not None:
            for i in range(self._party.count()):
                if coerce_combo_int_id(self._party.itemData(i)) == current:
                    self._party.setCurrentIndex(i)
                    break
        self._party.blockSignals(False)

    def filter_to_vendor(self, vendor_id: int) -> None:
        """Tiny Vendor Center hook: VENDOR = *vendor_id*."""
        self.reload()
        want = int(vendor_id)
        for i in range(self._party.count()):
            if coerce_combo_int_id(self._party.itemData(i)) == want:
                self._party.setCurrentIndex(i)
                return

    def _rebuild_visible(self) -> None:
        rows = tr.filter_tracker_rows(
            self._all_rows,
            party_id=self._party_filter_id(),
            type_name=self._type.currentText(),
            status_name=self._status.currentText(),
            date_preset=self._date.currentText(),
            tile=self._tile,
            paid_ids=self._paid_ids,
        )
        group_vendor = self._group.currentText() == "Vendor"
        display: list[dict] = []
        if group_vendor:
            current = None
            for row in sorted(rows, key=lambda r: ((r.get("party_name") or "").lower(), r.get("due_date") or "")):
                name = row.get("party_name") or ""
                if name != current:
                    display.append(
                        {
                            "kind": "group",
                            "record_id": 0,
                            "party_id": int(row.get("party_id") or 0),
                            "party_name": name,
                            "type": "",
                            "number": "",
                            "date": "",
                            "due_date": "",
                            "amount": 0.0,
                            "open_balance": 0.0,
                            "status": "",
                        }
                    )
                    current = name
                display.append(row)
        else:
            display = rows
        self._visible_rows = display
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(display))
        data_count = 0
        for i, row in enumerate(display):
            if row.get("kind") == "group":
                it = self._text_item(row.get("party_name") or "")
                font = QFont(it.font())
                font.setBold(True)
                it.setFont(font)
                it.setBackground(QColor(_TK_HEADER))
                it.setData(_ROLE_GROUP, 1)
                self._table.setItem(i, _COL_CHECK, QTableWidgetItem(""))
                self._table.setItem(i, _BL_COL_PARTY, it)
                for col in range(2, self._table.columnCount()):
                    filler = QTableWidgetItem("")
                    filler.setBackground(QColor(_TK_HEADER))
                    self._table.setItem(i, col, filler)
                continue
            data_count += 1
            overdue = row.get("status") == tr.STATUS_OVERDUE
            chk = self._check_item(row)
            self._table.setItem(i, _COL_CHECK, chk)
            party = self._text_item(row.get("party_name") or "")
            self._stamp_ids(party, row)
            self._table.setItem(i, _BL_COL_PARTY, party)
            self._table.setItem(i, _BL_COL_TYPE, self._text_item(row.get("type") or ""))
            self._table.setItem(i, _BL_COL_NUM, self._text_item(row.get("number") or ""))
            self._table.setItem(i, _BL_COL_DATE, self._date_item(row.get("date") or ""))
            self._table.setItem(i, _BL_COL_DUE, self._date_item(row.get("due_date") or ""))
            self._table.setItem(
                i, _BL_COL_STATUS, self._text_item(row.get("status") or "", overdue=overdue)
            )
            self._table.setItem(i, _BL_COL_AMT, self._money_item(float(row.get("amount") or 0)))
            self._table.setItem(
                i, _BL_COL_BAL, self._money_item(float(row.get("open_balance") or 0))
            )
            self._table.setCellWidget(i, _BL_COL_ACTION, self._make_bill_action(row, i))
        self._table.setSortingEnabled(not group_vendor)
        if not group_vendor:
            self._table.sortItems(_BL_COL_DUE, Qt.SortOrder.AscendingOrder)
        n = data_count
        self._set_showing(n, n)

    def _make_bill_action(self, row: dict, index: int) -> QToolButton:
        open_bal = float(row.get("open_balance") or 0) > 0.005
        btn = QToolButton()
        btn.setObjectName(f"billTrackerAction_{index}")
        btn.setText("Pay Bill" if open_bal else "Open Bill")
        btn.setStyleSheet(_pay_bill_button_qss() if open_bal else _tool_button_qss())
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        menu = QMenu(btn)
        if open_bal:
            menu.addAction(
                "Pay Bill",
                lambda r=row: self.payBillRequested.emit(int(r.get("record_id") or 0)),
            )
            btn.clicked.connect(
                lambda _c=False, r=row: self.payBillRequested.emit(int(r.get("record_id") or 0))
            )
        menu.addAction("Open Bill", lambda r=row: self.openBillRequested.emit(int(r.get("record_id") or 0)))
        if not open_bal:
            btn.clicked.connect(
                lambda _c=False, r=row: self.openBillRequested.emit(int(r.get("record_id") or 0))
            )
        btn.setMenu(menu)
        return btn

    def _open_row(self, row: dict) -> None:
        if row.get("kind") == "group":
            return
        rid = int(row.get("record_id") or 0)
        if rid > 0:
            self.openBillRequested.emit(rid)

    def _on_batch_pay(self) -> None:
        rows = [r for r in self._checked_rows() if r.get("kind") == "bill"]
        if not rows:
            row = self._selected_row()
            rows = [row] if row and row.get("kind") == "bill" else []
        if rows:
            self.payBillRequested.emit(int(rows[0]["record_id"]))

    def _on_batch_open(self) -> None:
        rows = [r for r in self._checked_rows() if r.get("kind") == "bill"]
        if not rows:
            row = self._selected_row()
            rows = [row] if row and row.get("kind") == "bill" else []
        if rows:
            self._open_row(rows[0])

    def _on_manage_open(self) -> None:
        row = self._selected_row()
        if row:
            self._open_row(row)

    def _on_manage_pay(self) -> None:
        row = self._selected_row()
        if row and row.get("kind") == "bill":
            self.payBillRequested.emit(int(row["record_id"]))
