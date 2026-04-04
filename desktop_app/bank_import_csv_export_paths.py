"""
**QSettings** paths for Bank Import file dialogs (import + CSV export).

**Export:** ``bank_import/last_csv_export_dir`` (legacy read:
``bank_import/line_compare_csv_export_dir``).

**Open (CSV/PDF):** ``bank_import/last_import_dir`` — folder of the last file chosen
for **Import CSV…** or **Import PDF…**.

Also provides **suggested export basenames** from the import batch (sanitized file stem or
``{prefix}-{id}.csv``), used by reconciliation report and line-comparison exports.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSettings

from desktop_app.qt_combo_ids import coerce_combo_int_id

BANK_IMPORT_LAST_CSV_EXPORT_DIR_KEY = "bank_import/last_csv_export_dir"
BANK_IMPORT_LAST_IMPORT_DIR_KEY = "bank_import/last_import_dir"
_LEGACY_LINE_COMPARE_CSV_EXPORT_DIR_KEY = "bank_import/line_compare_csv_export_dir"


def suggested_bank_import_batch_csv_filename(
    batch: Optional[dict],
    *,
    filename_suffix: str,
    batch_id_prefix: str,
    when_no_batch: str,
) -> str:
    """
    Default ``*.csv`` basename from a **bank_import_batches** row dict.

    ``filename_suffix`` is the trailing tag (e.g. ``line-compare``, ``reconciliation``).
    ``batch_id_prefix`` is used before the numeric id when ``filename`` is empty
    (e.g. ``line-compare-batch``, ``bank-reconciliation-batch``).
    """
    if not batch:
        return when_no_batch
    raw = str(batch.get("filename") or "").strip()
    if raw:
        base = Path(raw.replace("\\", "/")).name
        stem = Path(base).stem.strip() or "import"
        safe = "".join(
            ch if ch.isalnum() or ch in (" ", "-", "_", ".") else "_" for ch in stem
        )
        safe = safe.strip("._- ")[:100] or "import"
        safe = "-".join(part for part in safe.split() if part)
        return f"{safe}-{filename_suffix}.csv"
    bid = coerce_combo_int_id(batch.get("id"))
    if bid is not None:
        return f"{batch_id_prefix}-{bid}.csv"
    return when_no_batch


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


def bank_import_open_dialog_start_dir(
    *,
    settings: Optional[QSettings] = None,
) -> str:
    """Initial directory for **Import CSV…** / **Import PDF…** (empty string if unset)."""
    s = settings if settings is not None else QSettings()
    raw = (s.value(BANK_IMPORT_LAST_IMPORT_DIR_KEY, "", type=str) or "").strip()
    if not raw:
        return ""
    parent = Path(raw)
    if parent.is_dir():
        return str(parent)
    return ""


def remember_bank_import_import_dir(
    chosen_file_path: str,
    *,
    settings: Optional[QSettings] = None,
) -> None:
    """Remember the folder after the user picks a file in an import open dialog."""
    s = settings if settings is not None else QSettings()
    s.setValue(
        BANK_IMPORT_LAST_IMPORT_DIR_KEY,
        str(Path(chosen_file_path).resolve().parent),
    )
