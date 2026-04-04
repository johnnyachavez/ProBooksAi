"""Escape ``&`` for Qt text that uses mnemonic rules (window titles, some labels).

Also provides ``tip_message_box_buttons`` and single-**Ok** helpers
(``message_box_information_ok``, ``message_box_warning_ok``, ``message_box_critical_ok``, ``message_box_about_ok``) for hover hints
on the **Ok** button and the dialog window (``QMessageBox.setToolTip`` uses the same *ok_tip* as the **Ok** control),
and ``tip_qdialog_button_box`` for **QDialogButtonBox** **Ok** / **Save** / **Cancel** / **Close**.

Contract tests require that ``.button(QMessageBox`` and ``.button(QDialogButtonBox`` appear only in this file
(so standard-button hover text stays centralized). Do not call static ``QMessageBox.information`` / ``warning`` /
``critical`` / ``about`` / ``question`` from ``desktop_app`` — use the helpers here or build a ``QMessageBox``
instance with ``tip_message_box_buttons`` / ``setToolTip``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialogButtonBox, QMessageBox, QWidget

# Appended to **Ok** hover tips after a successful CSV save (``encoding="utf-8-sig"``).
CSV_EXPORT_OK_TIP_SUFFIX = " UTF-8 with BOM for Excel."


def escape_ampersand_for_qt(s: str) -> str:
    """Return *s* with each ``&`` doubled so Qt shows a literal ampersand."""
    return str(s).replace("&", "&&")


def tip_message_box_buttons(
    box: QMessageBox,
    *,
    yes: str | None = None,
    no: str | None = None,
    ok: str | None = None,
    cancel: str | None = None,
) -> None:
    """Set hover tooltips on **Yes** / **No** / **Ok** / **Cancel** standard buttons present on *box*."""
    if yes:
        y = box.button(QMessageBox.StandardButton.Yes)
        if y is not None:
            y.setToolTip(yes)
    if no:
        n = box.button(QMessageBox.StandardButton.No)
        if n is not None:
            n.setToolTip(no)
    if ok:
        o = box.button(QMessageBox.StandardButton.Ok)
        if o is not None:
            o.setToolTip(ok)
    if cancel:
        c = box.button(QMessageBox.StandardButton.Cancel)
        if c is not None:
            c.setToolTip(cancel)


def tip_qdialog_button_box(
    bb: QDialogButtonBox,
    *,
    ok: str | None = None,
    save: str | None = None,
    cancel: str | None = None,
    close: str | None = None,
) -> None:
    """Set hover tooltips on **Ok** / **Save** / **Cancel** / **Close** buttons present on *bb*."""
    if ok:
        b = bb.button(QDialogButtonBox.StandardButton.Ok)
        if b is not None:
            b.setToolTip(ok)
    if save:
        b = bb.button(QDialogButtonBox.StandardButton.Save)
        if b is not None:
            b.setToolTip(save)
    if cancel:
        b = bb.button(QDialogButtonBox.StandardButton.Cancel)
        if b is not None:
            b.setToolTip(cancel)
    if close:
        b = bb.button(QDialogButtonBox.StandardButton.Close)
        if b is not None:
            b.setToolTip(close)


def message_box_information_ok(
    parent: QWidget | None,
    title: str,
    text: str,
    *,
    ok_tip: str = "Close this message.",
) -> None:
    """Show an information ``QMessageBox`` with a single **Ok** and optional **Ok** hover *ok_tip*."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.setToolTip(ok_tip)
    tip_message_box_buttons(box, ok=ok_tip)
    box.exec()


def message_box_warning_ok(
    parent: QWidget | None,
    title: str,
    text: str,
    *,
    ok_tip: str = "Close this warning.",
) -> None:
    """Show a warning ``QMessageBox`` with a single **Ok** and optional **Ok** hover *ok_tip*."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.setToolTip(ok_tip)
    tip_message_box_buttons(box, ok=ok_tip)
    box.exec()


def message_box_critical_ok(
    parent: QWidget | None,
    title: str,
    text: str,
    *,
    ok_tip: str = "Close this error message.",
) -> None:
    """Show a critical ``QMessageBox`` with a single **Ok** and optional **Ok** hover *ok_tip*."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.setToolTip(ok_tip)
    tip_message_box_buttons(box, ok=ok_tip)
    box.exec()


def message_box_about_ok(
    parent: QWidget | None,
    title: str,
    text: str,
    *,
    ok_tip: str = "Close this about dialog.",
) -> None:
    """Like ``QMessageBox.about`` but with **RichText** body and an **Ok** hover *ok_tip*."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle(title)
    box.setTextFormat(Qt.TextFormat.RichText)
    box.setText(text)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.setToolTip(ok_tip)
    tip_message_box_buttons(box, ok=ok_tip)
    box.exec()
