"""probooksai.html_escape — no PySide6."""

from probooksai.html_escape import escape_html_text


def test_escape_html_text_ampersand_and_brackets():
    out = escape_html_text("Terms: net 30 & <keep>")
    assert "&amp;" in out
    assert "&lt;keep&gt;" in out


def test_escape_html_text_empty():
    assert escape_html_text("") == ""
    assert escape_html_text(None) == ""


def test_escape_html_text_quotes_escaped():
    out = escape_html_text('say "hi" and \'bye\'')
    assert "&quot;" in out
    assert "&#x27;" in out or "&apos;" in out
