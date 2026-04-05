"""
Shared QStyledItemDelegate for bank register-style tables: two-band rows (lighter upper /
darker lower) with optional Payee / Number column layouts.

``RegisterTab`` uses full layout; ``BlankBankRegisterTable`` (Bank Import preview) uses
``simple_band_rows`` so every column draws a single line in the upper band (shorter
``sizeHint``). Keyboard focus draws a high-contrast cosmetic outline on the active cell
(visible on the dark register theme). Inline editors are sized to the full cell via
``updateEditorGeometry``. Disabled items use ``DISABLED_FG`` for text and omit the focus ring.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QFontMetrics, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
    QTableWidget,
    QWidget,
)

from desktop_app.theme import (
    DISABLED_FG,
    FG_PRIMARY,
    FG_SECONDARY,
    REGISTER_BAND_DIVIDER,
    REGISTER_GRID_LINE,
    REGISTER_ROW_HEIGHT_MIN_FULL,
    REGISTER_ROW_HEIGHT_MIN_PREVIEW,
    SELECTION_BG,
    SELECTION_FG,
    register_row_band_colors_hex,
)

# Item data for payee / ref split rendering (RegisterTab sets these on items).
REGISTER_MISSING_COA_ROLE = Qt.ItemDataRole.UserRole + 50
REGISTER_PAYEE_UPPER_PLAIN = Qt.ItemDataRole.UserRole + 51
REGISTER_PAYEE_LOWER_PLAIN = Qt.ItemDataRole.UserRole + 52
REGISTER_REF_UPPER_PLAIN = Qt.ItemDataRole.UserRole + 53
REGISTER_REF_LOWER_PLAIN = Qt.ItemDataRole.UserRole + 54

_DEFAULT_REGISTER_RIGHT_COLS = frozenset({4, 5, 7})


class RegisterBandDelegate(QStyledItemDelegate):
    """Paints checkbook-style upper / lower bands; register columns or simple preview mode."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        simple_band_rows: bool = False,
        missing_flag_date_col: int = 0,
        ref_col: int | None = 1,
        payee_col: int | None = 2,
        center_col: int | None = 6,
        right_aligned_cols: frozenset[int] | None = None,
    ):
        super().__init__(parent)
        self._simple = simple_band_rows
        self._missing_date_col = missing_flag_date_col
        self._ref_col = ref_col
        self._payee_col = payee_col
        self._center_col = center_col
        self._right_cols = (
            right_aligned_cols
            if right_aligned_cols is not None
            else _DEFAULT_REGISTER_RIGHT_COLS
        )

    def _row_missing_coa(self, index) -> bool:
        if self._simple:
            return False
        table = self.parent()
        if not isinstance(table, QTableWidget):
            return False
        sid = table.model().index(index.row(), self._missing_date_col)
        v = table.model().data(sid, REGISTER_MISSING_COA_ROLE)
        return bool(v)

    @staticmethod
    def _split_rect(full: QRect) -> tuple[QRect, QRect]:
        h = max(full.height() // 2, 1)
        top = QRect(full.left(), full.top(), full.width(), h)
        bot = QRect(full.left(), full.top() + h, full.width(), full.height() - h)
        return top, bot

    def sizeHint(self, option, index) -> QSize:
        fm = QFontMetrics(option.font)
        if self._simple:
            h = max(fm.height() + 14, REGISTER_ROW_HEIGHT_MIN_PREVIEW)
        else:
            h = max(fm.height() * 2 + 10, REGISTER_ROW_HEIGHT_MIN_FULL)
        return QSize(super().sizeHint(option, index).width(), h)

    def updateEditorGeometry(self, editor, option, index) -> None:
        """Keep editors flush with the cell; tall banded rows can otherwise leave odd insets."""
        super().updateEditorGeometry(editor, option, index)
        if editor is not None:
            editor.setGeometry(option.rect)

    def paint(self, painter: QPainter, option, index) -> None:
        table = self.parent()
        if not isinstance(table, QTableWidget):
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setClipRect(option.rect)

        sel = bool(option.state & QStyle.StateFlag.State_Selected)
        top_r, bot_r = self._split_rect(option.rect)

        if sel:
            painter.fillRect(option.rect, QColor(SELECTION_BG))
        else:
            row = index.row()
            uh, lh = register_row_band_colors_hex(row % 2 == 1, self._row_missing_coa(index))
            painter.fillRect(top_r, QColor(uh))
            painter.fillRect(bot_r, QColor(lh))
            painter.setPen(QPen(QColor(REGISTER_BAND_DIVIDER), 1))
            y = top_r.bottom()
            painter.drawLine(option.rect.left(), y, option.rect.right(), y)

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        enabled = bool(opt.state & QStyle.StateFlag.State_Enabled)
        if sel:
            opt.palette.setColor(QPalette.ColorRole.Text, QColor(SELECTION_FG))
        else:
            br = index.data(Qt.ItemDataRole.ForegroundRole)
            if isinstance(br, QBrush):
                opt.palette.setBrush(QPalette.ColorRole.Text, br)

        font = opt.font
        fm = QFontMetrics(font)
        col = index.column()

        def draw_payee_two_bands(top: QRect, bot: QRect, line1: str, line2: str) -> None:
            painter.setFont(font)
            if not enabled:
                painter.setPen(QColor(DISABLED_FG))
            elif sel:
                painter.setPen(QColor(SELECTION_FG))
            else:
                painter.setPen(QColor(FG_PRIMARY))
            t1 = fm.elidedText(line1, Qt.TextElideMode.ElideRight, top.width() - 10)
            painter.drawText(
                top.adjusted(6, 3, -6, 0),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
                t1,
            )
            if not enabled:
                painter.setPen(QColor(DISABLED_FG))
            elif sel:
                painter.setPen(QColor(SELECTION_FG))
            else:
                painter.setPen(QColor(FG_SECONDARY))
            t2 = fm.elidedText(line2, Qt.TextElideMode.ElideRight, bot.width() - 10)
            painter.drawText(
                bot.adjusted(6, 2, -6, 0),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
                t2,
            )

        payee_c = self._payee_col
        ref_c = self._ref_col
        if not self._simple and payee_c is not None and col == payee_c:
            l1 = index.data(REGISTER_PAYEE_UPPER_PLAIN)
            l2 = index.data(REGISTER_PAYEE_LOWER_PLAIN)
            if not isinstance(l1, str):
                l1 = (opt.text or "").split("\n", 1)[0]
            if not isinstance(l2, str):
                parts = (opt.text or "").split("\n", 1)
                l2 = parts[1] if len(parts) > 1 else ""
            draw_payee_two_bands(top_r, bot_r, l1, l2)
        elif not self._simple and ref_c is not None and col == ref_c:
            l1 = index.data(REGISTER_REF_UPPER_PLAIN)
            l2 = index.data(REGISTER_REF_LOWER_PLAIN)
            if not isinstance(l1, str):
                parts = (opt.text or "").split("\n", 1)
                l1 = parts[0]
            if not isinstance(l2, str):
                parts = (opt.text or "").split("\n", 1)
                l2 = parts[1] if len(parts) > 1 else ""
            painter.setFont(font)
            if not enabled:
                pen = QColor(DISABLED_FG)
            else:
                pen = QColor(SELECTION_FG if sel else opt.palette.color(QPalette.ColorRole.Text))
            painter.setPen(pen)
            combined = f"{l1} · {l2}" if (l2 or "").strip() else l1
            elide_w = top_r.width() - 12
            t = fm.elidedText(combined.strip(), Qt.TextElideMode.ElideRight, elide_w)
            flags = int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            painter.drawText(top_r.adjusted(6, 0, -6, 0), flags, t)
        else:
            painter.setFont(font)
            if not enabled:
                pen = QColor(DISABLED_FG)
            else:
                pen = QColor(SELECTION_FG if sel else opt.palette.color(QPalette.ColorRole.Text))
            painter.setPen(pen)
            text = (opt.text or "").replace("\n", " ").strip()
            align_right = col in self._right_cols
            ctr = self._center_col
            align_ctr = ctr is not None and col == ctr
            elide_w = top_r.width() - 12
            t = fm.elidedText(text, Qt.TextElideMode.ElideRight, elide_w)
            flags = int(
                Qt.AlignmentFlag.AlignVCenter
                | (
                    Qt.AlignmentFlag.AlignRight
                    if align_right
                    else Qt.AlignmentFlag.AlignHCenter
                    if align_ctr
                    else Qt.AlignmentFlag.AlignLeft
                )
            )
            painter.drawText(top_r.adjusted(6, 0, -6, 0), flags, t)

        if enabled and (opt.state & QStyle.StateFlag.State_HasFocus):
            ring = QPen(QColor(SELECTION_FG), 2)
            ring.setCosmetic(True)
            painter.setPen(ring)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(option.rect.adjusted(2, 2, -3, -3))

        # Classic register grid (horizontal + vertical rules); custom paint bypasses QSS ::item borders.
        grid_pen = QPen(QColor(REGISTER_GRID_LINE), 1)
        grid_pen.setCosmetic(True)
        painter.setPen(grid_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        r = option.rect
        painter.drawLine(r.left(), r.bottom(), r.right(), r.bottom())
        painter.drawLine(r.right(), r.top(), r.right(), r.bottom())

        painter.restore()
