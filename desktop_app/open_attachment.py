"""Open a local file path with the OS default application (Qt)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox, QWidget

from desktop_app.qt_mnemonic import escape_ampersand_for_qt, tip_message_box_buttons


def open_local_attachment(
    parent: QWidget,
    path: str,
    *,
    empty_message: str = "No file path is set.",
    dialog_title: str = "Open attachment",
) -> None:
    """Open *path* with the OS default application; show a dialog if empty or missing."""
    raw = (path or "").strip()
    if not raw:
        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle(escape_ampersand_for_qt(dialog_title))
        box.setText(escape_ampersand_for_qt(empty_message))
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.setToolTip("No file path is set on this row; set a path or use Browse where available.")
        tip_message_box_buttons(
            box,
            ok="Close this dialog; set or copy a file path before opening.",
        )
        box.exec()
        return
    p = Path(raw).expanduser()
    try:
        resolved = p.resolve(strict=False)
    except OSError:
        resolved = p
    if not resolved.is_file():
        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(escape_ampersand_for_qt(dialog_title))
        box.setText(f"File not found:\n{escape_ampersand_for_qt(raw)}")
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.setToolTip("The path does not point to an existing file on this computer.")
        tip_message_box_buttons(
            box,
            ok="Close and verify the path, drive, or network location.",
        )
        box.exec()
        return
    ok = QDesktopServices.openUrl(QUrl.fromLocalFile(str(resolved)))
    if not ok:
        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(escape_ampersand_for_qt(dialog_title))
        box.setText("Unable to open this file with the default application.")
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.setToolTip("The OS could not launch a default application for this file type or path.")
        tip_message_box_buttons(
            box,
            ok="Close; try opening the file from File Explorer or fix the default app for this type.",
        )
        box.exec()
