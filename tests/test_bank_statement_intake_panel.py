"""Bank Statement Intake panel — phase 1 review-table population tests.

Phase-1 hard rules covered here:

* Table populates from CSV / PDF (text-layer) / pasted text via the
  normalized :class:`BankStatementIntakeRow` schema.
* Editing a row in place keeps changes when read back.
* Clearing the table empties it.
* The panel never writes to the database — these tests deliberately do
  *not* construct any ``BankDatabase`` / register infrastructure.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QPushButton, QTableWidget

from desktop_app.bank_statement_intake_panel import (
    BankStatementIntakePanel,
    _HEADERS,
)
from probooksai.bank_statement_intake import (
    SOURCE_TYPE_CSV,
    SOURCE_TYPE_PDF,
    SOURCE_TYPE_TEXT,
)


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


# ---------------------------------------------------------------------------
# UI structure
# ---------------------------------------------------------------------------


def test_panel_has_three_input_actions_and_paste_box(qapp: QApplication) -> None:
    w = BankStatementIntakePanel()
    btns = {b.text() for b in w.findChildren(QPushButton)}
    assert "Import CSV…" in btns
    assert "Import PDF…" in btns
    assert "Extract pasted text" in btns
    assert "Clear staged rows" in btns
    pastes = w.findChildren(QPlainTextEdit)
    assert len(pastes) == 1


def test_panel_review_table_has_all_normalized_columns(qapp: QApplication) -> None:
    w = BankStatementIntakePanel()
    table = w.findChild(QTableWidget)
    assert table is not None
    assert table.columnCount() == len(_HEADERS)
    actual_headers = [
        table.horizontalHeaderItem(i).text() for i in range(table.columnCount())
    ]
    assert actual_headers == list(_HEADERS)


def test_panel_starts_empty_with_zero_rows_label(qapp: QApplication) -> None:
    w = BankStatementIntakePanel()
    assert w.row_count() == 0


# ---------------------------------------------------------------------------
# CSV intake → table
# ---------------------------------------------------------------------------


_CSV_SAMPLE = (
    "Transaction Date,Description,Amount,Balance\n"
    "01/02/2026,Coffee Shop,-4.50,995.50\n"
    "01/03/2026,Payroll Deposit,1500.00,2495.50\n"
)


def test_panel_import_csv_file_populates_review_table(
    qapp: QApplication, tmp_path: Path
) -> None:
    csv_path = tmp_path / "jan-statement.csv"
    csv_path.write_text(_CSV_SAMPLE, encoding="utf-8")

    w = BankStatementIntakePanel()
    appended = w.import_csv_file(str(csv_path))
    assert appended == 2
    assert w.row_count() == 2

    rows = w.collect_rows()
    assert rows[0].txn_date == "2026-01-02"
    assert rows[0].amount_signed == -4.50
    assert rows[0].debit == 4.50
    assert rows[0].credit is None
    assert rows[0].running_balance == 995.50
    assert rows[0].source_type == SOURCE_TYPE_CSV
    assert "jan-statement.csv" in rows[0].source_ref
    assert rows[0].needs_review is False

    assert rows[1].amount_signed == 1500.00
    assert rows[1].credit == 1500.00


def test_panel_import_csv_file_with_unreadable_path_returns_zero(
    qapp: QApplication, tmp_path: Path
) -> None:
    w = BankStatementIntakePanel()
    appended = w.import_csv_file(str(tmp_path / "does-not-exist.csv"))
    assert appended == 0
    assert w.row_count() == 0


def test_panel_import_csv_button_routes_through_file_dialog_factory(
    qapp: QApplication, tmp_path: Path
) -> None:
    csv_path = tmp_path / "via-button.csv"
    csv_path.write_text(_CSV_SAMPLE, encoding="utf-8")

    chosen_path = str(csv_path)

    def fake_factory(*, caption: str, file_filter: str) -> str:
        assert "CSV" in caption
        return chosen_path

    w = BankStatementIntakePanel(file_dialog_factory=fake_factory)
    btns = {b.text(): b for b in w.findChildren(QPushButton)}
    btns["Import CSV…"].click()
    assert w.row_count() == 2


def test_panel_import_csv_button_cancelled_dialog_does_nothing(
    qapp: QApplication,
) -> None:
    def fake_factory(*, caption: str, file_filter: str) -> None:
        return None

    w = BankStatementIntakePanel(file_dialog_factory=fake_factory)
    btns = {b.text(): b for b in w.findChildren(QPushButton)}
    btns["Import CSV…"].click()
    assert w.row_count() == 0


# ---------------------------------------------------------------------------
# PDF intake → table
# ---------------------------------------------------------------------------


def test_panel_import_pdf_file_populates_review_table_via_text_layer(
    qapp: QApplication, monkeypatch
) -> None:
    fake_text = (
        "01/02/2026 Coffee Shop -4.50 995.50\n"
        "01/03/2026 Payroll Deposit 1500.00 2495.50\n"
    )
    monkeypatch.setattr(
        "probooksai.statement_pdf.extract_text_from_pdf", lambda path: fake_text
    )
    w = BankStatementIntakePanel()
    appended = w.import_pdf_file("/tmp/account-1234.pdf")
    assert appended == 2
    assert w.row_count() == 2
    rows = w.collect_rows()
    for r in rows:
        assert r.source_type == SOURCE_TYPE_PDF
        assert "account-1234.pdf" in r.source_ref


def test_panel_import_pdf_handles_missing_pypdf_gracefully(
    qapp: QApplication, monkeypatch
) -> None:
    """When the text-layer extractor blows up the panel just appends nothing."""

    def boom(path: str) -> str:
        raise ImportError("pypdf not installed")

    monkeypatch.setattr(
        "probooksai.statement_pdf.extract_text_from_pdf", boom
    )
    w = BankStatementIntakePanel()
    appended = w.import_pdf_file("/tmp/whatever.pdf")
    assert appended == 0
    assert w.row_count() == 0


# ---------------------------------------------------------------------------
# Pasted text → table
# ---------------------------------------------------------------------------


def test_panel_extract_pasted_text_populates_review_table(qapp: QApplication) -> None:
    text = (
        "01/02/2026 Coffee Shop -4.50 995.50\n"
        "01/03/2026 Payroll Deposit 1500.00 2495.50\n"
    )
    w = BankStatementIntakePanel()
    paste = w.findChild(QPlainTextEdit)
    paste.setPlainText(text)

    btns = {b.text(): b for b in w.findChildren(QPushButton)}
    btns["Extract pasted text"].click()

    assert w.row_count() == 2
    rows = w.collect_rows()
    assert rows[0].txn_date == "2026-01-02"
    assert rows[0].amount_signed == -4.50
    assert rows[0].source_type == SOURCE_TYPE_TEXT
    assert "pasted-text" in rows[0].source_ref


def test_panel_extract_pasted_text_with_empty_buffer_does_nothing(
    qapp: QApplication,
) -> None:
    w = BankStatementIntakePanel()
    btns = {b.text(): b for b in w.findChildren(QPushButton)}
    btns["Extract pasted text"].click()
    assert w.row_count() == 0


# ---------------------------------------------------------------------------
# Editability + clear
# ---------------------------------------------------------------------------


def test_panel_user_edit_to_amount_round_trips_through_collect_rows(
    qapp: QApplication, tmp_path: Path
) -> None:
    csv_path = tmp_path / "edit.csv"
    csv_path.write_text(_CSV_SAMPLE, encoding="utf-8")
    w = BankStatementIntakePanel()
    w.import_csv_file(str(csv_path))
    table = w.findChild(QTableWidget)

    # Locate the description and amount columns by header label.
    header_to_col = {
        table.horizontalHeaderItem(i).text(): i for i in range(table.columnCount())
    }
    desc_col = header_to_col["Description"]
    amt_col = header_to_col["Amount (signed)"]

    # Simulate a user fixing a misread description and overriding amount sign.
    table.item(0, desc_col).setText("Coffee Shop (corrected)")
    table.item(0, amt_col).setText("-9.99")

    rows = w.collect_rows()
    assert rows[0].description_raw == "Coffee Shop (corrected)"
    assert rows[0].amount_signed == -9.99


def test_panel_clear_staged_rows_empties_table(
    qapp: QApplication, tmp_path: Path
) -> None:
    csv_path = tmp_path / "clear.csv"
    csv_path.write_text(_CSV_SAMPLE, encoding="utf-8")
    w = BankStatementIntakePanel()
    w.import_csv_file(str(csv_path))
    assert w.row_count() == 2

    btns = {b.text(): b for b in w.findChildren(QPushButton)}
    btns["Clear staged rows"].click()
    assert w.row_count() == 0


def test_panel_provenance_columns_are_not_editable(
    qapp: QApplication, tmp_path: Path
) -> None:
    csv_path = tmp_path / "ro.csv"
    csv_path.write_text(_CSV_SAMPLE, encoding="utf-8")
    w = BankStatementIntakePanel()
    w.import_csv_file(str(csv_path))
    table = w.findChild(QTableWidget)
    header_to_col = {
        table.horizontalHeaderItem(i).text(): i for i in range(table.columnCount())
    }
    src_col = header_to_col["Source"]
    src_ref_col = header_to_col["Source ref"]

    src_item = table.item(0, src_col)
    src_ref_item = table.item(0, src_ref_col)
    from PySide6.QtCore import Qt

    assert not (src_item.flags() & Qt.ItemFlag.ItemIsEditable)
    assert not (src_ref_item.flags() & Qt.ItemFlag.ItemIsEditable)


# ---------------------------------------------------------------------------
# rowsChanged signal
# ---------------------------------------------------------------------------


def test_panel_rows_changed_signal_fires_on_append_and_clear(
    qapp: QApplication, tmp_path: Path
) -> None:
    csv_path = tmp_path / "sig.csv"
    csv_path.write_text(_CSV_SAMPLE, encoding="utf-8")
    w = BankStatementIntakePanel()
    seen: list[int] = []
    w.rowsChanged.connect(seen.append)
    w.import_csv_file(str(csv_path))
    w.clear_rows()
    assert seen == [2, 0]
