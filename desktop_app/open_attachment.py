"""Open a local file path with the OS default application (Qt)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox, QWidget

from desktop_app.qt_mnemonic import escape_ampersand_for_qt


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
        QMessageBox.information(
            parent,
            escape_ampersand_for_qt(dialog_title),
            escape_ampersand_for_qt(empty_message),
        )
        return
    p = Path(raw).expanduser()
    try:
        resolved = p.resolve(strict=False)
    except OSError:
        resolved = p
    if not resolved.is_file():
        QMessageBox.warning(
            parent,
            escape_ampersand_for_qt(dialog_title),
            f"File not found:\n{escape_ampersand_for_qt(raw)}",
        )
        return
    ok = QDesktopServices.openUrl(QUrl.fromLocalFile(str(resolved)))
    if not ok:
        QMessageBox.warning(
            parent,
            escape_ampersand_for_qt(dialog_title),
            "Unable to open this file with the default application.",
        )
