"""desktop_app.qt_mnemonic — no PySide6 import."""

from pathlib import Path

from desktop_app.qt_mnemonic import CSV_EXPORT_OK_TIP_SUFFIX, escape_ampersand_for_qt

_REPO_ROOT = Path(__file__).resolve().parents[1]
_QT_MNEMONIC_PATH = _REPO_ROOT / "desktop_app" / "qt_mnemonic.py"


def test_csv_export_ok_tip_suffix_documents_utf8_bom():
    assert "UTF-8" in CSV_EXPORT_OK_TIP_SUFFIX
    assert CSV_EXPORT_OK_TIP_SUFFIX.startswith(" ")


def test_escape_ampersand_doubles():
    assert escape_ampersand_for_qt("") == ""
    assert escape_ampersand_for_qt("x") == "x"
    assert escape_ampersand_for_qt("a&b") == "a&&b"
    assert escape_ampersand_for_qt("a&&b") == "a&&&&b"


def test_tip_qdialog_button_box_supports_ok_default_kwarg() -> None:
    text = _QT_MNEMONIC_PATH.read_text(encoding="utf-8")
    assert "ok_default: bool = False" in text
    assert "if ok_default:" in text
    assert "setDefault(True)" in text
