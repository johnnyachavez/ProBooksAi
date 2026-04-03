"""desktop_app.qt_mnemonic — no PySide6 import."""

from desktop_app.qt_mnemonic import escape_ampersand_for_qt


def test_escape_ampersand_doubles():
    assert escape_ampersand_for_qt("") == ""
    assert escape_ampersand_for_qt("x") == "x"
    assert escape_ampersand_for_qt("a&b") == "a&&b"
    assert escape_ampersand_for_qt("a&&b") == "a&&&&b"
