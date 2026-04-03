"""Escape ``&`` for Qt text that uses mnemonic rules (window titles, some labels)."""


def escape_ampersand_for_qt(s: str) -> str:
    """Return *s* with each ``&`` doubled so Qt shows a literal ampersand."""
    return str(s).replace("&", "&&")
