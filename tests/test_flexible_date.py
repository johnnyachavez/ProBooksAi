"""Unit tests for ``desktop_app.flexible_date`` parsing and US display formatting."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QDateEdit, QLineEdit

from desktop_app.flexible_date import (
    configure_qdate_edit_us,
    create_app_date_edit,
    expand_two_digit_year,
    format_iso_to_us_display,
    format_ymd_as_us,
    line_edit_to_iso_or_raw,
    normalize_line_edit_us_date,
    parse_flexible_date_to_ymd,
)


def _ymd(s: str) -> tuple[int, int, int] | None:
    p = parse_flexible_date_to_ymd(s)
    if p is None:
        return None
    y, m, d = p
    return (y, m, d)


def test_expand_two_digit_year_pivot() -> None:
    assert expand_two_digit_year(26) == 2026
    assert expand_two_digit_year(36) == 2036
    assert expand_two_digit_year(69) == 2069
    assert expand_two_digit_year(70) == 1970
    assert expand_two_digit_year(99) == 1999


@pytest.mark.parametrize(
    "text,expected",
    [
        ("5/21/26", (2026, 5, 21)),
        ("05/21/26", (2026, 5, 21)),
        ("5/21/2026", (2026, 5, 21)),
        ("05/21/2026", (2026, 5, 21)),
        ("5.21.26", (2026, 5, 21)),
        ("05.21.26", (2026, 5, 21)),
        (".05.21.26", (2026, 5, 21)),
        ("052126", (2026, 5, 21)),
        ("05212026", (2026, 5, 21)),
        ("5-21-26", (2026, 5, 21)),
        ("5 21 26", (2026, 5, 21)),
        ("2026-05-21", (2026, 5, 21)),
        ("5-1-2026", (2026, 5, 1)),
    ],
)
def test_parse_flexible_variants(text: str, expected: tuple[int, int, int]) -> None:
    assert _ymd(text) == expected


def test_format_ymd_as_us_padding() -> None:
    assert format_ymd_as_us(5, 1, 2026) == "05/01/2026"


def test_format_iso_to_us_display() -> None:
    assert format_iso_to_us_display("2026-05-21") == "05/21/2026"


def test_invalid_does_not_crash() -> None:
    assert parse_flexible_date_to_ymd("13/40/2026") is None
    assert parse_flexible_date_to_ymd("not a date") is None
    assert parse_flexible_date_to_ymd("") is None


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_line_edit_normalize_and_to_iso(qapp) -> None:
    le = QLineEdit("5/21/26")
    normalize_line_edit_us_date(le)
    assert le.text() == "05/21/2026"
    assert line_edit_to_iso_or_raw(le) == "2026-05-21"


def test_line_edit_unparsed_passthrough(qapp) -> None:
    le = QLineEdit("Q4 estimate")
    normalize_line_edit_us_date(le)
    assert le.text() == "Q4 estimate"
    assert line_edit_to_iso_or_raw(le) == "Q4 estimate"


def test_configure_qdate_edit_us_no_calendar_mmddyyyy(qapp) -> None:
    w = QDateEdit()
    configure_qdate_edit_us(w)
    assert w.calendarPopup() is False
    assert w.displayFormat() == "MM/dd/yyyy"


def test_create_app_date_edit_matches_configure(qapp) -> None:
    w = create_app_date_edit()
    assert w.calendarPopup() is False
    assert w.displayFormat() == "MM/dd/yyyy"
