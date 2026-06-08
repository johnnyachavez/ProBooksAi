"""Global hover-message (tooltip / What's-This) suppression — default OFF for the app."""

from __future__ import annotations

import sys

import pytest
from PySide6.QtCore import QEvent, QPoint
from PySide6.QtGui import QHelpEvent
from PySide6.QtWidgets import QApplication, QWidget

from desktop_app.hover_messages import (
    install_global_hover_message_suppression,
    is_hover_message_suppression_installed,
    uninstall_global_hover_message_suppression,
)


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_install_is_idempotent(qapp: QApplication) -> None:
    """Installing twice does not stack multiple filters."""
    uninstall_global_hover_message_suppression(qapp)
    install_global_hover_message_suppression(qapp)
    first = is_hover_message_suppression_installed()
    install_global_hover_message_suppression(qapp)
    again = is_hover_message_suppression_installed()
    assert first is True
    assert again is True


def test_uninstall_clears_filter(qapp: QApplication) -> None:
    install_global_hover_message_suppression(qapp)
    assert is_hover_message_suppression_installed() is True
    uninstall_global_hover_message_suppression(qapp)
    assert is_hover_message_suppression_installed() is False


def test_tooltip_event_is_swallowed_when_installed(qapp: QApplication) -> None:
    """Synthetic ToolTip event is consumed by the suppressor's eventFilter."""
    uninstall_global_hover_message_suppression(qapp)
    suppressor = install_global_hover_message_suppression(qapp)
    w = QWidget()
    w.setToolTip("Should never surface as a popup")
    pos = QPoint(5, 5)
    ev = QHelpEvent(QEvent.Type.ToolTip, pos, w.mapToGlobal(pos))
    consumed = suppressor.eventFilter(w, ev)
    assert consumed is True, "ToolTip events must be consumed when suppression is on."
    whatsthis = QHelpEvent(QEvent.Type.WhatsThis, pos, w.mapToGlobal(pos))
    assert suppressor.eventFilter(w, whatsthis) is True
    assert w.toolTip() == "Should never surface as a popup", (
        "Suppression must NOT strip the underlying setToolTip strings — they remain "
        "as inline documentation referenced by contract tests."
    )


def test_non_tooltip_events_pass_through(qapp: QApplication) -> None:
    """Non-tooltip events are not consumed by the suppressor."""
    uninstall_global_hover_message_suppression(qapp)
    suppressor = install_global_hover_message_suppression(qapp)
    w = QWidget()
    paint_ev = QEvent(QEvent.Type.Paint)
    assert suppressor.eventFilter(w, paint_ev) is False, (
        "Only ToolTip/WhatsThis events should be consumed; Paint must pass through."
    )
