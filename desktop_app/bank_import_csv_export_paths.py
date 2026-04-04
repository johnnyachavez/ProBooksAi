"""
Shared **QSettings** directory memory for Bank Import **CSV** save dialogs.

Uses ``bank_import/last_csv_export_dir``. Falls back to the older
``bank_import/line_compare_csv_export_dir`` when the new key is unset so existing installs
keep their remembered folder.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSettings

BANK_IMPORT_LAST_CSV_EXPORT_DIR_KEY = "bank_import/last_csv_export_dir"
_LEGACY_LINE_COMPARE_CSV_EXPORT_DIR_KEY = "bank_import/line_compare_csv_export_dir"


def _resolved_export_parent(settings: QSettings) -> Optional[Path]:
    for key in (BANK_IMPORT_LAST_CSV_EXPORT_DIR_KEY, _LEGACY_LINE_COMPARE_CSV_EXPORT_DIR_KEY):
        raw = (settings.value(key, "", type=str) or "").strip()
        if not raw:
            continue
        parent = Path(raw)
        if parent.is_dir():
            return parent
    return None


def bank_import_csv_default_save_path(
    suggested_filename: str,
    *,
    settings: Optional[QSettings] = None,
) -> str:
    """Directory from settings + ``suggested_filename``, or home + basename."""
    s = settings if settings is not None else QSettings()
    parent = _resolved_export_parent(s)
    if parent is not None:
        return str(parent / suggested_filename)
    return str(Path.home() / suggested_filename)


def remember_bank_import_csv_export_parent(
    saved_file_path: str,
    *,
    settings: Optional[QSettings] = None,
) -> None:
    """Persist the parent directory of a successful Bank Import CSV export (new key only)."""
    s = settings if settings is not None else QSettings()
    s.setValue(
        BANK_IMPORT_LAST_CSV_EXPORT_DIR_KEY,
        str(Path(saved_file_path).resolve().parent),
    )
