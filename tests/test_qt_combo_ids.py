"""Tests for ``desktop_app.qt_combo_ids`` (QComboBox integer ``userData`` matching)."""

from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QApplication, QComboBox

from desktop_app.qt_combo_ids import (
    coerce_combo_int_id,
    combo_index_for_int_user_data,
    combo_int_ids_equal,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_coerce_combo_int_id() -> None:
    assert coerce_combo_int_id(None) is None
    assert coerce_combo_int_id(3) == 3
    assert coerce_combo_int_id("7") == 7
    assert coerce_combo_int_id("x") is None


def test_combo_int_ids_equal() -> None:
    assert combo_int_ids_equal(1, 1)
    assert combo_int_ids_equal(1, "1")
    assert not combo_int_ids_equal(1, 2)
    assert combo_int_ids_equal(None, None)
    assert not combo_int_ids_equal(None, 1)


def test_combo_index_for_int_user_data(qapp) -> None:
    cb = QComboBox()
    cb.addItem("a", 1)
    cb.addItem("b", "2")
    cb.addItem("none", None)
    assert combo_index_for_int_user_data(cb, 1) == 0
    assert combo_index_for_int_user_data(cb, 2) == 1
    assert combo_index_for_int_user_data(cb, None) is None
    assert combo_index_for_int_user_data(cb, "x") is None


def test_combo_index_for_int_user_data_respects_start(qapp) -> None:
    cb = QComboBox()
    cb.addItem("(none)", None)
    cb.addItem("bank", "5")
    assert combo_index_for_int_user_data(cb, 5) == 1
    assert combo_index_for_int_user_data(cb, 5, start=1) == 1
    assert combo_index_for_int_user_data(cb, 5, start=2) is None
