"""App-wide hover-message (tooltip / What's-This) suppression switch.

ProBooks+ai prefers a quiet UI: hover popups are **off by default** across the app.
We do not strip the underlying ``QWidget.setToolTip(...)`` / ``QAction.setToolTip(...)``
strings — they remain in the source as inline documentation and are referenced by
the contract test suite. We simply install a global ``QApplication`` event filter
that swallows the ``QEvent.Type.ToolTip`` / ``QEvent.Type.WhatsThis`` events before
Qt has a chance to show a popup.

Usage (single switch, called once from :func:`desktop_app.main.main`):

    from desktop_app.hover_messages import install_global_hover_message_suppression
    install_global_hover_message_suppression(app)

The filter is idempotent: re-installing on the same ``QApplication`` does not stack
multiple filters. Tests can opt back into native Qt tooltip behavior by calling
:func:`uninstall_global_hover_message_suppression`.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication

# Qt event types we silence. ToolTip is the hover popup; WhatsThis is the older
# Shift+F1 contextual help popup we also do not want surfacing by accident.
_SUPPRESSED_EVENT_TYPES = frozenset(
    {QEvent.Type.ToolTip, QEvent.Type.WhatsThis}
)


class _HoverMessageSuppressor(QObject):
    """Application-level event filter that consumes ToolTip / WhatsThis events."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: D401 - Qt signature
        if event.type() in _SUPPRESSED_EVENT_TYPES:
            return True
        return super().eventFilter(watched, event)


_INSTALLED_SUPPRESSOR: Optional[_HoverMessageSuppressor] = None


def install_global_hover_message_suppression(
    app: Optional[QApplication] = None,
) -> _HoverMessageSuppressor:
    """Install (or reuse) the application-level tooltip-suppressing event filter.

    Returns the active filter object. Calling this multiple times is safe — it
    installs at most one filter on the running ``QApplication``.
    """
    global _INSTALLED_SUPPRESSOR
    target = app or QApplication.instance()
    if target is None:
        raise RuntimeError(
            "install_global_hover_message_suppression requires an active QApplication"
        )
    if _INSTALLED_SUPPRESSOR is None:
        _INSTALLED_SUPPRESSOR = _HoverMessageSuppressor()
        target.installEventFilter(_INSTALLED_SUPPRESSOR)
    return _INSTALLED_SUPPRESSOR


def uninstall_global_hover_message_suppression(
    app: Optional[QApplication] = None,
) -> None:
    """Remove the suppression filter (used by tests that need native tooltip behavior)."""
    global _INSTALLED_SUPPRESSOR
    if _INSTALLED_SUPPRESSOR is None:
        return
    target = app or QApplication.instance()
    if target is not None:
        target.removeEventFilter(_INSTALLED_SUPPRESSOR)
    _INSTALLED_SUPPRESSOR = None


def is_hover_message_suppression_installed() -> bool:
    return _INSTALLED_SUPPRESSOR is not None
