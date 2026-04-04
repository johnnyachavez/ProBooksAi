"""desktop_app.qt_mnemonic — no PySide6 import."""

from desktop_app.qt_mnemonic import CSV_EXPORT_OK_TIP_SUFFIX, escape_ampersand_for_qt


def test_csv_export_ok_tip_suffix_documents_utf8_bom():
    assert "UTF-8" in CSV_EXPORT_OK_TIP_SUFFIX
    assert CSV_EXPORT_OK_TIP_SUFFIX.startswith(" ")


def test_escape_ampersand_doubles():
    assert escape_ampersand_for_qt("") == ""
    assert escape_ampersand_for_qt("x") == "x"
    assert escape_ampersand_for_qt("a&b") == "a&&b"
    assert escape_ampersand_for_qt("a&&b") == "a&&&&b"
