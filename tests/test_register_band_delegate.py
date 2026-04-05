"""Register / import preview band delegate (row height + role constants)."""

from __future__ import annotations

import sys

import pytest
from PySide6.QtCore import QModelIndex, QRect, Qt
from PySide6.QtGui import QFontMetrics, QImage, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QLineEdit,
    QStyle,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
)

from desktop_app.register_band_delegate import (
    REGISTER_LINK_BASE_TOOLTIP,
    REGISTER_LINK_LOWER_PLAIN,
    REGISTER_LINK_UPPER_PLAIN,
    REGISTER_MISSING_COA_ROLE,
    REGISTER_PAYEE_LOWER_PLAIN,
    REGISTER_PAYEE_UPPER_PLAIN,
    REGISTER_REF_LOWER_PLAIN,
    REGISTER_REF_UPPER_PLAIN,
    RegisterBandDelegate,
)
from desktop_app.theme import REGISTER_ROW_HEIGHT_MIN_FULL, REGISTER_ROW_HEIGHT_MIN_PREVIEW


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_register_item_data_roles_are_distinct() -> None:
    roles = [
        REGISTER_MISSING_COA_ROLE,
        REGISTER_PAYEE_UPPER_PLAIN,
        REGISTER_PAYEE_LOWER_PLAIN,
        REGISTER_REF_UPPER_PLAIN,
        REGISTER_REF_LOWER_PLAIN,
        REGISTER_LINK_UPPER_PLAIN,
        REGISTER_LINK_LOWER_PLAIN,
        REGISTER_LINK_BASE_TOOLTIP,
    ]
    assert len(roles) == len(set(roles))


def test_register_band_delegate_simple_mode_shorter_than_full(qapp) -> None:
    table = QTableWidget(3, 5)
    full = RegisterBandDelegate(table, simple_band_rows=False)
    simple = RegisterBandDelegate(table, simple_band_rows=True)
    opt = QStyleOptionViewItem()
    opt.font = table.font()
    idx = QModelIndex()
    assert full.sizeHint(opt, idx).height() >= simple.sizeHint(opt, idx).height()
    assert simple.sizeHint(opt, idx).height() >= REGISTER_ROW_HEIGHT_MIN_PREVIEW
    assert full.sizeHint(opt, idx).height() >= REGISTER_ROW_HEIGHT_MIN_FULL


def test_register_band_delegate_paint_disabled_item_runs(qapp) -> None:
    table = QTableWidget(1, 1)
    it = QTableWidgetItem("x")
    it.setFlags(Qt.ItemFlag.ItemIsSelectable)
    table.setItem(0, 0, it)
    delg = RegisterBandDelegate(table, simple_band_rows=True)
    img = QImage(180, 48, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    opt = QStyleOptionViewItem()
    opt.rect = QRect(0, 0, 180, 48)
    opt.state = QStyle.StateFlag.State_None
    idx = table.model().index(0, 0)
    delg.paint(p, opt, idx)
    p.end()


def test_register_band_delegate_update_editor_geometry_fills_option_rect(qapp) -> None:
    table = QTableWidget(1, 1)
    table.setItem(0, 0, QTableWidgetItem("x"))
    delg = RegisterBandDelegate(table, simple_band_rows=True)
    editor = QLineEdit()
    opt = QStyleOptionViewItem()
    opt.rect = QRect(5, 7, 120, 44)
    idx = table.model().index(0, 0)
    delg.updateEditorGeometry(editor, opt, idx)
    assert editor.geometry() == opt.rect


def test_register_band_delegate_simple_matches_two_line_font_metric(qapp) -> None:
    table = QTableWidget(1, 1)
    full = RegisterBandDelegate(table, simple_band_rows=False)
    opt = QStyleOptionViewItem()
    opt.font = table.font()
    fm = QFontMetrics(opt.font)
    idx = QModelIndex()
    assert full.sizeHint(opt, idx).height() >= fm.height() * 2 + 10
