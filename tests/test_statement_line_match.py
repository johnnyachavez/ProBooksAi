"""Tests for statement line vs register matching (AI reconciliation workflow)."""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from probooksai.statement_line_match import (
    STATUS_EXTRA,
    STATUS_LIKELY_MATCH,
    STATUS_MATCHED,
    STATUS_MISSING,
    STATUS_NEEDS_REVIEW,
    amounts_equal,
    compare_statement_to_register,
    dates_within_days,
    descriptions_match,
    mock_statement_lines_for_comparison,
    statement_rows_for_line_compare,
    transaction_pair_matches,
    transaction_pair_likely,
    write_line_match_comparison_csv,
)


def test_strip_pasted_breaks_removes_cr_lf_tab() -> None:
    from probooksai.statement_line_match import _strip_pasted_breaks

    assert _strip_pasted_breaks("a\rb\nc\t") == "abc"
    assert _strip_pasted_breaks("1\u200b234") == "1234"
    assert _strip_pasted_breaks("x") == "x"


def test_statement_rows_for_line_compare_maps_bank_transactions() -> None:
    stmt = statement_rows_for_line_compare(
        [
            {
                "txn_date": "2024-01-05",
                "amount": -4.5,
                "description": "Coffee",
                "ref_number": "R1",
                "memo": "M1",
            }
        ]
    )
    assert len(stmt) == 1
    assert stmt[0]["txn_date"] == "2024-01-05"
    assert stmt[0]["amount"] == -4.5
    assert stmt[0]["description"] == "Coffee"
    assert stmt[0]["ref_number"] == "R1"
    assert stmt[0]["memo"] == "M1"


def test_dates_within_days() -> None:
    assert dates_within_days("2024-06-01", "2024-06-01", 2)
    assert dates_within_days("2024-06-01", "2024-06-03", 2)
    assert not dates_within_days("2024-06-01", "2024-06-04", 2)
    assert not dates_within_days("", "2024-06-01", 2)


def test_dates_within_days_mdy_and_iso_datetime_prefix() -> None:
    assert dates_within_days("1/15/2024", "2024-01-15", 2)
    assert dates_within_days("01-15-2024", "2024-01-16", 2)
    assert dates_within_days("2024-06-01T14:30:00", "2024-06-02", 2)
    assert dates_within_days("2024/03/10", "2024-03-11", 2)


def test_dates_within_days_strips_embedded_newlines_and_tabs() -> None:
    assert dates_within_days("01/15/\n2024", "2024-01-15", 2)
    assert dates_within_days("\t2024-06-01\t", "2024-06-01", 2)
    assert dates_within_days("2024-\n01-10", "2024-01-10", 2)
    assert dates_within_days("2024-\u200b01-10", "2024-01-10", 2)


def test_dates_within_days_day_first_when_month_gt_12_impossible() -> None:
    """``13/02/2024`` is parsed as DD/MM (Feb 13), not US month 13."""
    assert dates_within_days("13/02/2024", "2024-02-13", 2)


def test_compare_stmt_mdy_date_matches_register_iso() -> None:
    stmt = [{"txn_date": "1/10/2024", "amount": -10.0, "description": "Gas"}]
    reg = [{"id": 1, "txn_date": "2024-01-10", "amount": -10.0, "description": "Gas"}]
    out = compare_statement_to_register(stmt, reg)
    assert len(out) == 1
    assert out[0]["status"] == STATUS_MATCHED


def test_compare_register_multiline_memo_matches_statement() -> None:
    stmt = [{"txn_date": "2024-01-10", "amount": -5.0, "description": "COFFEE SHOP"}]
    reg = [
        {
            "id": 1,
            "txn_date": "2024-01-10",
            "amount": -5.0,
            "description": "POS",
            "memo": "COFFEE\nSHOP DOWNTOWN",
        }
    ]
    out = compare_statement_to_register(stmt, reg)
    assert len(out) == 1
    assert out[0]["status"] == STATUS_MATCHED


def test_compare_register_memo_helps_match_statement_payee() -> None:
    stmt = [{"txn_date": "2024-01-10", "amount": -5.0, "description": "COFFEE"}]
    reg = [
        {
            "id": 1,
            "txn_date": "2024-01-10",
            "amount": -5.0,
            "description": "POS",
            "memo": "COFFEE SHOP DOWNTOWN",
        }
    ]
    out = compare_statement_to_register(stmt, reg)
    assert len(out) == 1
    assert out[0]["status"] == STATUS_MATCHED


def test_compare_register_ref_number_helps_match_statement_text() -> None:
    stmt = [
        {
            "txn_date": "2024-02-01",
            "amount": -120.0,
            "description": "UTILITY PAYMENT CONF 8844",
        }
    ]
    reg = [
        {
            "id": 1,
            "txn_date": "2024-02-01",
            "amount": -120.0,
            "description": "",
            "memo": "",
            "ref_number": "8844",
        }
    ]
    out = compare_statement_to_register(stmt, reg)
    assert len(out) == 1
    assert out[0]["status"] == STATUS_MATCHED


def test_normalize_paste_whitespace_collapses_breaks_to_spaces() -> None:
    from probooksai.statement_line_match import _normalize_paste_whitespace

    assert _normalize_paste_whitespace("a\nb\tc") == "a b c"
    assert _normalize_paste_whitespace("x\r\ny") == "x y"
    assert _normalize_paste_whitespace("a\u00a0b") == "a b"
    assert _normalize_paste_whitespace("x\u202fy") == "x y"
    assert _normalize_paste_whitespace("foo\u200bbar") == "foobar"
    assert _normalize_paste_whitespace("re\u00adport") == "report"


def test_descriptions_match_treats_newlines_and_tabs_as_spaces() -> None:
    assert descriptions_match("LINE\nONE", "line one")
    assert descriptions_match("a\tb", "a b")
    assert descriptions_match("foo\u00a0bar", "foo bar")
    assert descriptions_match("HELLO", "hel\u200blo")
    assert descriptions_match("OVERDRAFT", "over\u00addraft")


def test_descriptions_match_casefolds_unicode_letters() -> None:
    assert descriptions_match("STRASSE", "straße")
    assert descriptions_match("straße", "STRASSE MAIN")


def test_descriptions_match_substring_and_fuzzy() -> None:
    assert descriptions_match("AMAZON MARKETPLACE", "amazon")
    assert descriptions_match("coffee", "COFFEE SHOP DOWNTOWN")
    assert descriptions_match("Wire Transfer Acme", "Wire Transfer Acme Corp")
    assert not descriptions_match("x", "yz")


def test_amounts_equal_coerces_currency_strings() -> None:
    assert amounts_equal("$1,234.50", 1234.5)
    assert amounts_equal("  -25.00 ", -25.0)
    assert amounts_equal("\u221212.50", -12.5)
    assert amounts_equal("(10.00)", -10.0)
    assert amounts_equal("(\u221210.00)", -10.0)
    assert amounts_equal("$0", 0.0)
    assert amounts_equal("10.00\r\n", 10.0)
    assert amounts_equal("$1,\n234.50", 1234.5)
    assert amounts_equal("\t12.50\t", 12.5)
    assert amounts_equal("1\u200b,234.50", 1234.5)
    assert amounts_equal("1\u202f234.50", 1234.5)
    assert not amounts_equal("n/a", 1.0)
    assert not amounts_equal(None, 1.0)
    assert not amounts_equal(True, 1.0)


def test_compare_stmt_string_amount_matches_register_numeric() -> None:
    stmt = [
        {"txn_date": "2024-01-10", "amount": "-$25.00", "description": "Coffee Shop"},
    ]
    reg = [
        {"id": 1, "txn_date": "2024-01-10", "amount": -25.0, "description": "Coffee Shop"},
    ]
    out = compare_statement_to_register(stmt, reg)
    assert len(out) == 1
    assert out[0]["status"] == STATUS_MATCHED
    assert out[0]["stmt_amount"] == -25.0
    assert out[0]["reg_amount"] == -25.0


def test_compare_perfect_one_to_one() -> None:
    stmt = [
        {"txn_date": "2024-01-10", "amount": -25.0, "description": "Coffee Shop"},
    ]
    reg = [
        {"id": 1, "txn_date": "2024-01-10", "amount": -25.0, "description": "Coffee Shop"},
    ]
    out = compare_statement_to_register(stmt, reg)
    assert len(out) == 1
    assert out[0]["status"] == STATUS_MATCHED
    assert out[0]["register_id"] == 1


def test_compare_date_slop_still_matches() -> None:
    stmt = [{"txn_date": "2024-01-11", "amount": 100.0, "description": "Deposit"}]
    reg = [{"id": 5, "txn_date": "2024-01-10", "amount": 100.0, "description": "Deposit"}]
    out = compare_statement_to_register(stmt, reg)
    assert len(out) == 1
    assert out[0]["status"] == STATUS_MATCHED


def test_compare_missing_statement_only() -> None:
    stmt = [{"txn_date": "2024-02-01", "amount": -10.0, "description": "Unknown charge"}]
    reg: list = []
    out = compare_statement_to_register(stmt, reg)
    assert len(out) == 1
    assert out[0]["status"] == STATUS_NEEDS_REVIEW
    assert out[0]["status"] == STATUS_MISSING  # alias


def test_compare_likely_match_date_slip_beyond_two_days() -> None:
    stmt = [{"txn_date": "2024-01-13", "amount": 100.0, "description": "Deposit"}]
    reg = [{"id": 1, "txn_date": "2024-01-10", "amount": 100.0, "description": "Deposit"}]
    out = compare_statement_to_register(stmt, reg)
    assert len(out) == 1
    assert out[0]["status"] == STATUS_LIKELY_MATCH
    assert out[0]["register_id"] == 1


def test_transaction_pair_likely_weak_fuzzy_same_date() -> None:
    """Weak fuzzy ratio (0.22–0.35) with ±2d date — see ``transaction_pair_likely``."""
    stmt = {"txn_date": "2024-01-10", "amount": -10.0, "description": "AAA0"}
    reg = {"txn_date": "2024-01-10", "amount": -10.0, "description": "BBB0"}
    assert transaction_pair_likely(stmt, reg)


def test_compare_missing_includes_combined_stmt_description() -> None:
    stmt = [
        {
            "txn_date": "2024-02-01",
            "amount": -10.0,
            "description": "X",
            "ref_number": "R1",
            "memo": "Y",
        }
    ]
    reg: list = []
    out = compare_statement_to_register(stmt, reg)
    assert len(out) == 1
    assert out[0]["status"] == STATUS_MISSING
    assert out[0]["stmt_description"] == "X R1 Y"
    assert out[0]["reg_description"] == ""


def test_compare_extra_register_only() -> None:
    stmt: list = []
    reg = [{"id": 9, "txn_date": "2024-03-01", "amount": -5.0, "description": "Only in books"}]
    out = compare_statement_to_register(stmt, reg)
    assert len(out) == 1
    assert out[0]["status"] == STATUS_EXTRA
    assert out[0]["register_id"] == 9


def test_compare_output_stmt_and_reg_description_use_combined_match_text() -> None:
    stmt = [
        {
            "txn_date": "2024-01-10",
            "amount": -5.0,
            "description": "CHK",
            "ref_number": "1001",
            "memo": "WATER CO",
        }
    ]
    reg = [
        {
            "id": 1,
            "txn_date": "2024-01-10",
            "amount": -5.0,
            "description": "CHK",
            "ref_number": "1001",
            "memo": "WATER CO",
        }
    ]
    out = compare_statement_to_register(stmt, reg)
    assert len(out) == 1
    assert out[0]["status"] == STATUS_MATCHED
    assert out[0]["stmt_description"] == "CHK 1001 WATER CO"
    assert out[0]["reg_description"] == "CHK 1001 WATER CO"


def test_compare_output_extra_reg_description_includes_ref_and_memo() -> None:
    stmt: list = []
    reg = [
        {
            "id": 7,
            "txn_date": "2024-04-01",
            "amount": -3.0,
            "description": "D",
            "ref_number": "R9",
            "memo": "M",
        }
    ]
    out = compare_statement_to_register(stmt, reg)
    assert len(out) == 1
    assert out[0]["status"] == STATUS_EXTRA
    assert out[0]["reg_description"] == "D R9 M"


def test_compare_mixed_missing_matched_extra() -> None:
    stmt = [
        {"txn_date": "2024-01-01", "amount": -1.0, "description": "A"},
        {"txn_date": "2024-01-02", "amount": -2.0, "description": "No reg counterpart"},
    ]
    reg = [
        {"id": 1, "txn_date": "2024-01-01", "amount": -1.0, "description": "A"},
        {"id": 2, "txn_date": "2024-01-03", "amount": -99.0, "description": "Orphan reg"},
    ]
    out = compare_statement_to_register(stmt, reg)
    statuses = [r["status"] for r in out]
    assert STATUS_MATCHED in statuses
    assert STATUS_MISSING in statuses
    assert STATUS_EXTRA in statuses
    assert statuses.count(STATUS_MATCHED) == 1


def test_mock_statement_drops_and_synthetic() -> None:
    reg = [
        {"id": i, "txn_date": "2024-01-0%d" % (i + 1), "amount": float(-i - 1), "description": f"D{i}"}
        for i in range(6)
    ]
    stmt = mock_statement_lines_for_comparison(reg)
    assert any("MOCK STATEMENT ONLY" in (r.get("description") or "") for r in stmt)
    assert len(stmt) <= len(reg) + 1
    assert len(stmt) >= 2


def test_transaction_pair_matches_requires_all_three() -> None:
    stmt = {"txn_date": "2024-01-01", "amount": -10.0, "description": "Payee"}
    reg_ok = {"txn_date": "2024-01-01", "amount": -10.0, "description": "Payee"}
    assert transaction_pair_matches(stmt, reg_ok)
    reg_bad_amt = {**reg_ok, "amount": -11.0}
    assert not transaction_pair_matches(stmt, reg_bad_amt)
    reg_bad_date = {**reg_ok, "txn_date": "2024-01-10"}
    assert not transaction_pair_matches(stmt, reg_bad_date)


def test_mock_empty_register_returns_placeholder_line() -> None:
    stmt = mock_statement_lines_for_comparison([])
    assert len(stmt) == 1
    out = compare_statement_to_register(stmt, [])
    assert out[0]["status"] == STATUS_MISSING


def test_amounts_equal() -> None:
    assert amounts_equal(10.001, 10.0)


def test_write_line_match_comparison_csv_requires_flag_alignment() -> None:
    with pytest.raises(ValueError):
        write_line_match_comparison_csv("nope.csv", [{"status": STATUS_MATCHED}], [])


def test_write_line_match_comparison_csv_writes_header_and_rows(tmp_path) -> None:
    rows = [
        {
            "status": STATUS_MATCHED,
            "stmt_date": "2024-01-10",
            "stmt_amount": -1.5,
            "stmt_description": "A",
            "register_id": 9,
            "reg_date": "2024-01-10",
            "reg_amount": -1.5,
            "reg_description": "A",
        }
    ]
    path = tmp_path / "out.csv"
    write_line_match_comparison_csv(str(path), rows, [True])
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    text = path.read_text(encoding="utf-8-sig")
    assert "Reconciled" in text and "Stmt amount" in text
    assert "yes" in text and STATUS_MATCHED in text and "9" in text


def test_bank_import_open_dialog_start_dir_empty_without_saved_dir(tmp_path) -> None:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication(sys.argv)

    from desktop_app.bank_import_csv_export_paths import bank_import_open_dialog_start_dir

    ini = tmp_path / "empty.ini"
    ini.write_text("", encoding="utf-8")
    qs = QSettings(str(ini), QSettings.Format.IniFormat)
    assert bank_import_open_dialog_start_dir(settings=qs) == ""


def test_bank_import_open_dialog_start_dir_falls_back_to_export_dir(tmp_path) -> None:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication(sys.argv)

    from desktop_app.bank_import_csv_export_paths import (
        BANK_IMPORT_LAST_CSV_EXPORT_DIR_KEY,
        bank_import_open_dialog_start_dir,
    )

    exp = tmp_path / "exported_here"
    exp.mkdir()
    ini = tmp_path / "open.ini"
    qs = QSettings(str(ini), QSettings.Format.IniFormat)
    qs.setValue(BANK_IMPORT_LAST_CSV_EXPORT_DIR_KEY, str(exp.resolve()))
    qs.sync()
    assert bank_import_open_dialog_start_dir(settings=qs) == str(exp.resolve())


def test_bank_import_open_dialog_prefers_import_over_export_dir(tmp_path) -> None:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication(sys.argv)

    from desktop_app.bank_import_csv_export_paths import (
        BANK_IMPORT_LAST_CSV_EXPORT_DIR_KEY,
        BANK_IMPORT_LAST_IMPORT_DIR_KEY,
        bank_import_open_dialog_start_dir,
    )

    exp = tmp_path / "exports"
    imp = tmp_path / "imports"
    exp.mkdir()
    imp.mkdir()
    ini = tmp_path / "prio_open.ini"
    qs = QSettings(str(ini), QSettings.Format.IniFormat)
    qs.setValue(BANK_IMPORT_LAST_CSV_EXPORT_DIR_KEY, str(exp.resolve()))
    qs.setValue(BANK_IMPORT_LAST_IMPORT_DIR_KEY, str(imp.resolve()))
    qs.sync()
    assert bank_import_open_dialog_start_dir(settings=qs) == str(imp.resolve())


def test_bank_import_remember_import_dir_sets_open_dialog_start(tmp_path) -> None:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication(sys.argv)

    from desktop_app.bank_import_csv_export_paths import (
        bank_import_open_dialog_start_dir,
        remember_bank_import_import_dir,
    )

    sub = tmp_path / "imports_here"
    sub.mkdir()
    f = sub / "stmt.csv"
    f.write_text("h\n", encoding="utf-8")
    ini = tmp_path / "imp.ini"
    qs = QSettings(str(ini), QSettings.Format.IniFormat)
    remember_bank_import_import_dir(str(f), settings=qs)
    qs.sync()
    assert bank_import_open_dialog_start_dir(settings=qs) == str(sub.resolve())


def test_line_compare_export_default_path_uses_home_without_saved_dir(tmp_path) -> None:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication(sys.argv)

    from desktop_app.bank_import_csv_export_paths import bank_import_csv_default_save_path

    ini = tmp_path / "fresh.ini"
    ini.write_text("", encoding="utf-8")
    qs = QSettings(str(ini), QSettings.Format.IniFormat)
    p = bank_import_csv_default_save_path("suggest.csv", settings=qs)
    assert p == str(Path.home() / "suggest.csv")


def test_line_compare_export_default_path_uses_saved_directory(tmp_path) -> None:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication(sys.argv)

    from desktop_app.bank_import_csv_export_paths import (
        BANK_IMPORT_LAST_CSV_EXPORT_DIR_KEY,
        bank_import_csv_default_save_path,
    )

    export_dir = tmp_path / "saved_exports"
    export_dir.mkdir()
    ini = tmp_path / "st.ini"
    qs = QSettings(str(ini), QSettings.Format.IniFormat)
    qs.setValue(BANK_IMPORT_LAST_CSV_EXPORT_DIR_KEY, str(export_dir.resolve()))
    qs.sync()
    assert bank_import_csv_default_save_path("out.csv", settings=qs) == str(
        export_dir / "out.csv"
    )


def test_bank_import_csv_default_save_path_falls_back_to_import_dir(tmp_path) -> None:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication(sys.argv)

    from desktop_app.bank_import_csv_export_paths import (
        BANK_IMPORT_LAST_IMPORT_DIR_KEY,
        bank_import_csv_default_save_path,
    )

    imp = tmp_path / "from_import"
    imp.mkdir()
    ini = tmp_path / "both.ini"
    qs = QSettings(str(ini), QSettings.Format.IniFormat)
    qs.setValue(BANK_IMPORT_LAST_IMPORT_DIR_KEY, str(imp.resolve()))
    qs.sync()
    assert bank_import_csv_default_save_path("e.csv", settings=qs) == str(imp / "e.csv")


def test_bank_import_csv_default_save_path_prefers_export_over_import_dir(tmp_path) -> None:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication(sys.argv)

    from desktop_app.bank_import_csv_export_paths import (
        BANK_IMPORT_LAST_CSV_EXPORT_DIR_KEY,
        BANK_IMPORT_LAST_IMPORT_DIR_KEY,
        bank_import_csv_default_save_path,
    )

    exp = tmp_path / "exports"
    imp = tmp_path / "imports"
    exp.mkdir()
    imp.mkdir()
    ini = tmp_path / "prio.ini"
    qs = QSettings(str(ini), QSettings.Format.IniFormat)
    qs.setValue(BANK_IMPORT_LAST_CSV_EXPORT_DIR_KEY, str(exp.resolve()))
    qs.setValue(BANK_IMPORT_LAST_IMPORT_DIR_KEY, str(imp.resolve()))
    qs.sync()
    assert bank_import_csv_default_save_path("x.csv", settings=qs) == str(exp / "x.csv")


def test_bank_import_csv_default_save_path_reads_legacy_line_compare_key(tmp_path) -> None:
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication(sys.argv)

    from desktop_app.bank_import_csv_export_paths import bank_import_csv_default_save_path

    export_dir = tmp_path / "legacy_only"
    export_dir.mkdir()
    ini = tmp_path / "legacy.ini"
    qs = QSettings(str(ini), QSettings.Format.IniFormat)
    qs.setValue("bank_import/line_compare_csv_export_dir", str(export_dir.resolve()))
    qs.sync()
    assert bank_import_csv_default_save_path("r.csv", settings=qs) == str(
        export_dir / "r.csv"
    )


def test_suggested_bank_import_batch_csv_filename_reconciliation_variant() -> None:
    from desktop_app.bank_import_csv_export_paths import suggested_bank_import_batch_csv_filename

    assert (
        suggested_bank_import_batch_csv_filename(
            None,
            filename_suffix="reconciliation",
            batch_id_prefix="bank-reconciliation-batch",
            when_no_batch="bank-reconciliation-report.csv",
        )
        == "bank-reconciliation-report.csv"
    )
    assert (
        suggested_bank_import_batch_csv_filename(
            {"filename": r"C:\Data\January Stmt.csv", "id": 1},
            filename_suffix="reconciliation",
            batch_id_prefix="bank-reconciliation-batch",
            when_no_batch="bank-reconciliation-report.csv",
        )
        == "January-Stmt-reconciliation.csv"
    )
    assert (
        suggested_bank_import_batch_csv_filename(
            {"id": 99, "filename": ""},
            filename_suffix="reconciliation",
            batch_id_prefix="bank-reconciliation-batch",
            when_no_batch="bank-reconciliation-report.csv",
        )
        == "bank-reconciliation-batch-99.csv"
    )
    assert (
        suggested_bank_import_batch_csv_filename(
            {"id": "12", "filename": None},
            filename_suffix="reconciliation",
            batch_id_prefix="bank-reconciliation-batch",
            when_no_batch="bank-reconciliation-report.csv",
        )
        == "bank-reconciliation-batch-12.csv"
    )


def test_suggested_line_compare_csv_filename_uses_batch_stem_or_id() -> None:
    from desktop_app.statement_line_match_panel import _suggested_line_compare_csv_filename

    assert _suggested_line_compare_csv_filename(None) == "line-reconciliation-comparison.csv"
    assert (
        _suggested_line_compare_csv_filename(
            {"filename": r"C:\Data\January Stmt.csv", "id": 1}
        )
        == "January-Stmt-line-compare.csv"
    )
    assert (
        _suggested_line_compare_csv_filename({"id": 99, "filename": ""})
        == "line-compare-batch-99.csv"
    )
    assert (
        _suggested_line_compare_csv_filename({"id": "12", "filename": None})
        == "line-compare-batch-12.csv"
    )


def test_write_line_match_comparison_csv_quotes_commas_in_descriptions(tmp_path) -> None:
    rows = [
        {
            "status": STATUS_MATCHED,
            "stmt_date": "2024-01-10",
            "stmt_amount": -1.0,
            "stmt_description": 'Vendor, LLC "memo"',
            "register_id": 1,
            "reg_date": "2024-01-10",
            "reg_amount": -1.0,
            "reg_description": "A, B Corp",
        }
    ]
    path = tmp_path / "quoted.csv"
    write_line_match_comparison_csv(str(path), rows, [False])
    with path.open(encoding="utf-8-sig", newline="") as f:
        rdr = csv.reader(f)
        header = next(rdr)
        row = next(rdr)
    assert len(header) == len(row) == 9
    assert row[4] == 'Vendor, LLC "memo"'
    assert row[7] == "A, B Corp"


def test_statement_line_match_panel_reconciled_buttons_follow_content_and_selection() -> None:
    """Mark-all-Matched needs a Matched row; Mark selected needs a non-empty selection."""
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication(sys.argv)

    from probooksai.bank_import import BankDatabase
    from desktop_app.statement_line_match_panel import StatementLineMatchPanel

    db_path = Path(__file__).resolve().parent / "_stmt_line_match_btn_test.db"
    if db_path.exists():
        db_path.unlink()
    db = BankDatabase(str(db_path))
    try:
        panel = StatementLineMatchPanel(db)
        missing_row = {
            "status": STATUS_MISSING,
            "stmt_date": "2024-01-02",
            "stmt_amount": -2.0,
            "stmt_description": "X",
            "register_id": None,
            "reg_date": "",
            "reg_amount": 0.0,
            "reg_description": "",
        }
        panel.populate([missing_row])
        assert panel._btn_clear.isEnabled()
        assert not panel._btn_mark_matched.isEnabled()
        assert not panel._btn_mark_sel.isEnabled()
        panel._table.selectRow(0)
        assert panel._btn_mark_sel.isEnabled()

        panel.populate(
            [
                {
                    "status": STATUS_MATCHED,
                    "stmt_date": "2024-01-01",
                    "stmt_amount": -1.0,
                    "stmt_description": "A",
                    "register_id": 1,
                    "reg_date": "2024-01-01",
                    "reg_amount": -1.0,
                    "reg_description": "A",
                }
            ]
        )
        assert panel._btn_mark_matched.isEnabled()
    finally:
        db.close()
        if db_path.exists():
            db_path.unlink()


def test_statement_line_match_panel_stmt_and_register_field_plain_helpers() -> None:
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication(sys.argv)

    from probooksai.bank_import import BankDatabase
    from desktop_app.statement_line_match_panel import StatementLineMatchPanel

    db_path = Path(__file__).resolve().parent / "_stmt_line_match_field_plain.db"
    if db_path.exists():
        db_path.unlink()
    db = BankDatabase(str(db_path))
    try:
        panel = StatementLineMatchPanel(db)
        panel.populate(
            [
                {
                    "status": STATUS_MATCHED,
                    "stmt_date": "2024-01-01",
                    "stmt_amount": -1.0,
                    "stmt_description": "A",
                    "register_id": 1,
                    "reg_date": "2024-01-01",
                    "reg_amount": -1.0,
                    "reg_description": "A",
                },
                {
                    "status": STATUS_MISSING,
                    "stmt_date": "2024-02-02",
                    "stmt_amount": -2.5,
                    "stmt_description": "B",
                    "register_id": None,
                    "reg_date": "",
                    "reg_amount": 0.0,
                    "reg_description": "",
                },
                {
                    "status": STATUS_EXTRA,
                    "stmt_date": "",
                    "stmt_amount": 0.0,
                    "stmt_description": "",
                    "register_id": 9,
                    "reg_date": "2024-03-03",
                    "reg_amount": 100.0,
                    "reg_description": "C",
                },
            ]
        )
        assert panel._line_match_stmt_date_plain(0) == "2024-01-01"
        assert panel._line_match_stmt_amount_plain(0) == "-1.00"
        assert panel._line_match_stmt_description_plain(0) == "A"
        assert panel._line_match_reg_date_plain(0) == "2024-01-01"
        assert panel._line_match_reg_amount_plain(0) == "-1.00"
        assert panel._line_match_reg_description_plain(0) == "A"

        assert panel._line_match_stmt_date_plain(1) == "2024-02-02"
        assert panel._line_match_stmt_amount_plain(1) == "-2.50"
        assert panel._line_match_stmt_description_plain(1) == "B"
        assert panel._line_match_reg_date_plain(1) == ""
        assert panel._line_match_reg_amount_plain(1) == ""
        assert panel._line_match_reg_description_plain(1) == ""

        assert panel._line_match_stmt_date_plain(2) == ""
        assert panel._line_match_stmt_amount_plain(2) == ""
        assert panel._line_match_stmt_description_plain(2) == ""
        assert panel._line_match_reg_date_plain(2) == "2024-03-03"
        assert panel._line_match_reg_amount_plain(2) == "100.00"
        assert panel._line_match_reg_description_plain(2) == "C"
    finally:
        db.close()
        if db_path.exists():
            db_path.unlink()


def test_statement_line_match_panel_copy_register_transaction_id() -> None:
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication(sys.argv)

    from probooksai.bank_import import BankDatabase
    from desktop_app.statement_line_match_panel import StatementLineMatchPanel

    db_path = Path(__file__).resolve().parent / "_stmt_line_match_copy_rid.db"
    if db_path.exists():
        db_path.unlink()
    db = BankDatabase(str(db_path))
    try:
        panel = StatementLineMatchPanel(db)
        panel.populate(
            [
                {
                    "status": STATUS_MATCHED,
                    "stmt_date": "2024-01-01",
                    "stmt_amount": -1.0,
                    "stmt_description": "A",
                    "register_id": 42,
                    "reg_date": "2024-01-01",
                    "reg_amount": -1.0,
                    "reg_description": "A",
                },
                {
                    "status": STATUS_MISSING,
                    "stmt_date": "2024-01-02",
                    "stmt_amount": -2.0,
                    "stmt_description": "B",
                    "register_id": None,
                    "reg_date": "",
                    "reg_amount": 0.0,
                    "reg_description": "",
                },
            ]
        )
        assert panel._line_match_register_id_plain(0) == "42"
        assert panel._line_match_register_id_plain(1) == ""
        panel._copy_line_match_register_id(0)
        assert QGuiApplication.clipboard().text() == "42"
        panel._copy_line_match_register_id(1)
        assert QGuiApplication.clipboard().text() == ""
    finally:
        db.close()
        if db_path.exists():
            db_path.unlink()


def test_statement_line_match_panel_copy_descriptions_to_clipboard() -> None:
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication(sys.argv)

    from probooksai.bank_import import BankDatabase
    from desktop_app.statement_line_match_panel import StatementLineMatchPanel

    db_path = Path(__file__).resolve().parent / "_stmt_line_match_copy_desc.db"
    if db_path.exists():
        db_path.unlink()
    db = BankDatabase(str(db_path))
    try:
        panel = StatementLineMatchPanel(db)
        panel.populate(
            [
                {
                    "status": STATUS_MATCHED,
                    "stmt_date": "2024-01-01",
                    "stmt_amount": -1.0,
                    "stmt_description": "Stmt text",
                    "register_id": 1,
                    "reg_date": "2024-01-01",
                    "reg_amount": -1.0,
                    "reg_description": "Reg text",
                },
                {
                    "status": STATUS_MISSING,
                    "stmt_date": "2024-01-02",
                    "stmt_amount": -2.0,
                    "stmt_description": "Only stmt",
                    "register_id": None,
                    "reg_date": "",
                    "reg_amount": 0.0,
                    "reg_description": "",
                },
            ]
        )
        panel._copy_line_match_stmt_description(0)
        assert QGuiApplication.clipboard().text() == "Stmt text"
        panel._copy_line_match_reg_description(0)
        assert QGuiApplication.clipboard().text() == "Reg text"
        panel._copy_line_match_stmt_description(1)
        assert QGuiApplication.clipboard().text() == "Only stmt"
        panel._copy_line_match_reg_description(1)
        assert QGuiApplication.clipboard().text() == ""
    finally:
        db.close()
        if db_path.exists():
            db_path.unlink()


def test_statement_line_match_panel_copy_dates_and_amounts_to_clipboard() -> None:
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication(sys.argv)

    from probooksai.bank_import import BankDatabase
    from desktop_app.statement_line_match_panel import StatementLineMatchPanel

    db_path = Path(__file__).resolve().parent / "_stmt_line_match_copy_amt.db"
    if db_path.exists():
        db_path.unlink()
    db = BankDatabase(str(db_path))
    try:
        panel = StatementLineMatchPanel(db)
        panel.populate(
            [
                {
                    "status": STATUS_MATCHED,
                    "stmt_date": "2024-01-01",
                    "stmt_amount": -1.0,
                    "stmt_description": "",
                    "register_id": 1,
                    "reg_date": "2024-01-01",
                    "reg_amount": -1.0,
                    "reg_description": "",
                },
                {
                    "status": STATUS_MISSING,
                    "stmt_date": "2024-06-15",
                    "stmt_amount": -9.99,
                    "stmt_description": "",
                    "register_id": None,
                    "reg_date": "",
                    "reg_amount": 0.0,
                    "reg_description": "",
                },
            ]
        )
        panel._copy_line_match_stmt_date(0)
        assert QGuiApplication.clipboard().text() == "2024-01-01"
        panel._copy_line_match_stmt_amount(0)
        assert QGuiApplication.clipboard().text() == "-1.00"
        panel._copy_line_match_reg_date(0)
        assert QGuiApplication.clipboard().text() == "2024-01-01"
        panel._copy_line_match_reg_amount(0)
        assert QGuiApplication.clipboard().text() == "-1.00"

        panel._copy_line_match_stmt_date(1)
        assert QGuiApplication.clipboard().text() == "2024-06-15"
        panel._copy_line_match_stmt_amount(1)
        assert QGuiApplication.clipboard().text() == "-9.99"
        panel._copy_line_match_reg_date(1)
        assert QGuiApplication.clipboard().text() == ""
        panel._copy_line_match_reg_amount(1)
        assert QGuiApplication.clipboard().text() == ""
    finally:
        db.close()
        if db_path.exists():
            db_path.unlink()


def test_statement_line_match_panel_copy_extra_row_stmt_empty_register_to_clipboard() -> None:
    """**Extra** rows have register data only; statement-side plains and copies are empty."""
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication(sys.argv)

    from probooksai.bank_import import BankDatabase
    from desktop_app.statement_line_match_panel import StatementLineMatchPanel

    db_path = Path(__file__).resolve().parent / "_stmt_line_match_copy_extra.db"
    if db_path.exists():
        db_path.unlink()
    db = BankDatabase(str(db_path))
    try:
        panel = StatementLineMatchPanel(db)
        panel.populate(
            [
                {
                    "status": STATUS_EXTRA,
                    "stmt_date": "",
                    "stmt_amount": 0.0,
                    "stmt_description": "",
                    "register_id": 9,
                    "reg_date": "2024-03-03",
                    "reg_amount": 100.0,
                    "reg_description": "C",
                },
            ]
        )
        assert panel._line_match_stmt_date_plain(0) == ""
        assert panel._line_match_stmt_amount_plain(0) == ""
        assert panel._line_match_stmt_description_plain(0) == ""

        panel._copy_line_match_stmt_date(0)
        assert QGuiApplication.clipboard().text() == ""
        panel._copy_line_match_stmt_amount(0)
        assert QGuiApplication.clipboard().text() == ""
        panel._copy_line_match_stmt_description(0)
        assert QGuiApplication.clipboard().text() == ""

        panel._copy_line_match_reg_date(0)
        assert QGuiApplication.clipboard().text() == "2024-03-03"
        panel._copy_line_match_reg_amount(0)
        assert QGuiApplication.clipboard().text() == "100.00"
        panel._copy_line_match_reg_description(0)
        assert QGuiApplication.clipboard().text() == "C"
        panel._copy_line_match_register_id(0)
        assert QGuiApplication.clipboard().text() == "9"
    finally:
        db.close()
        if db_path.exists():
            db_path.unlink()


def test_statement_line_match_panel_reviewed_flags_need_qt() -> None:
    """Populate table and toggle reviewed checkboxes (requires QApplication)."""
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication(sys.argv)

    from probooksai.bank_import import BankDatabase
    from desktop_app.statement_line_match_panel import StatementLineMatchPanel

    db_path = Path(__file__).resolve().parent / "_stmt_line_match_ui_test.db"
    if db_path.exists():
        db_path.unlink()
    db = BankDatabase(str(db_path))
    try:
        panel = StatementLineMatchPanel(db)
        panel.populate(
            [
                {
                    "status": STATUS_MATCHED,
                    "stmt_date": "2024-01-01",
                    "stmt_amount": -1.0,
                    "stmt_description": "A",
                    "register_id": 1,
                    "reg_date": "2024-01-01",
                    "reg_amount": -1.0,
                    "reg_description": "A",
                }
            ]
        )
        assert panel.row_status(0) == STATUS_MATCHED
        assert panel.reviewed_count() == 0
        assert "marked reconciled here" not in panel._summary.text()
        panel._mark_reviewed_all_matched()
        assert panel.reviewed_count() == 1
        assert "1 row(s) marked reconciled here" in panel._summary.text()
        panel._clear_reviewed()
        assert panel.reviewed_count() == 0
        assert "marked reconciled here" not in panel._summary.text()
    finally:
        db.close()
        if db_path.exists():
            db_path.unlink()


def test_statement_line_match_panel_run_coerces_string_bank_account_id_in_batch() -> None:
    """``list_transactions`` / signal use int-safe batch ``bank_account_id`` (e.g. str from SQLite)."""
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication(sys.argv)

    from probooksai.bank_import import BankDatabase
    from desktop_app.statement_line_match_panel import StatementLineMatchPanel

    db_path = Path(__file__).resolve().parent / "_stmt_line_match_coerce_test.db"
    if db_path.exists():
        db_path.unlink()
    db = BankDatabase(str(db_path))
    try:
        aid = db.add_bank_account("CoerceTest")
        panel = StatementLineMatchPanel(db)
        emitted: list[int] = []
        panel.line_match_results_ready.connect(lambda a, _r: emitted.append(a))
        batch = {
            "id": 1,
            "bank_account_id": str(aid),
            "statement_start": None,
            "statement_end": None,
        }
        panel.set_context(aid, batch)
        panel._on_run_clicked()
        assert emitted == [aid]
    finally:
        db.close()
        if db_path.exists():
            db_path.unlink()


def test_statement_line_match_panel_line_reconciliation_table_alias() -> None:
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication(sys.argv)

    from probooksai.bank_import import BankDatabase
    from desktop_app.statement_line_match_panel import StatementLineMatchPanel

    db_path = Path(__file__).resolve().parent / "_stmt_line_match_table_alias.db"
    if db_path.exists():
        db_path.unlink()
    db = BankDatabase(str(db_path))
    try:
        panel = StatementLineMatchPanel(db)
        assert panel.line_reconciliation_table() is panel._table
    finally:
        db.close()
        if db_path.exists():
            db_path.unlink()


def test_statement_line_match_panel_try_ctrl_shift_b_without_register_tab_shows_tip() -> None:
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication(sys.argv)

    from probooksai.bank_import import BankDatabase
    from desktop_app.statement_line_match_panel import StatementLineMatchPanel

    db_path = Path(__file__).resolve().parent / "_stmt_line_match_try_b_no_reg.db"
    if db_path.exists():
        db_path.unlink()
    db = BankDatabase(str(db_path))
    try:
        panel = StatementLineMatchPanel(db, register_tab=None)
        panel.populate(
            [
                {
                    "status": STATUS_MATCHED,
                    "stmt_date": "2024-01-01",
                    "stmt_amount": -1.0,
                    "stmt_description": "A",
                    "register_id": 7,
                    "reg_date": "2024-01-01",
                    "reg_amount": -1.0,
                    "reg_description": "A",
                }
            ]
        )
        panel._table.setCurrentCell(0, 0)
        with patch(
            "desktop_app.statement_line_match_panel.message_box_information_ok"
        ) as m:
            panel.try_ctrl_shift_b_open_linked_business()
        m.assert_called_once()
        assert m.call_args[0][1] == "Business link"
    finally:
        db.close()
        if db_path.exists():
            db_path.unlink()


def test_statement_line_match_panel_try_ctrl_shift_b_no_current_row_shows_tip() -> None:
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication(sys.argv)

    from probooksai.bank_import import BankDatabase
    from desktop_app.statement_line_match_panel import StatementLineMatchPanel

    class _Reg:
        def __init__(self) -> None:
            self.tids: list[int] = []

        def open_linked_business_record_for_transaction_id(self, tid: int) -> None:
            self.tids.append(int(tid))

    db_path = Path(__file__).resolve().parent / "_stmt_line_match_try_b_no_row.db"
    if db_path.exists():
        db_path.unlink()
    db = BankDatabase(str(db_path))
    try:
        reg = _Reg()
        panel = StatementLineMatchPanel(db, register_tab=reg)
        panel.populate(
            [
                {
                    "status": STATUS_MATCHED,
                    "stmt_date": "2024-01-01",
                    "stmt_amount": -1.0,
                    "stmt_description": "A",
                    "register_id": 7,
                    "reg_date": "2024-01-01",
                    "reg_amount": -1.0,
                    "reg_description": "A",
                }
            ]
        )
        panel._table.selectionModel().clearCurrentIndex()
        with patch(
            "desktop_app.statement_line_match_panel.message_box_information_ok"
        ) as m:
            panel.try_ctrl_shift_b_open_linked_business()
        m.assert_called_once()
        assert reg.tids == []
    finally:
        db.close()
        if db_path.exists():
            db_path.unlink()


def test_statement_line_match_panel_try_ctrl_shift_b_no_register_id_shows_tip() -> None:
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication(sys.argv)

    from probooksai.bank_import import BankDatabase
    from desktop_app.statement_line_match_panel import StatementLineMatchPanel

    class _Reg:
        def __init__(self) -> None:
            self.tids: list[int] = []

        def open_linked_business_record_for_transaction_id(self, tid: int) -> None:
            self.tids.append(int(tid))

    db_path = Path(__file__).resolve().parent / "_stmt_line_match_try_b_no_rid.db"
    if db_path.exists():
        db_path.unlink()
    db = BankDatabase(str(db_path))
    try:
        reg = _Reg()
        panel = StatementLineMatchPanel(db, register_tab=reg)
        panel.populate(
            [
                {
                    "status": STATUS_MISSING,
                    "stmt_date": "2024-01-02",
                    "stmt_amount": -2.0,
                    "stmt_description": "B",
                    "register_id": None,
                    "reg_date": "",
                    "reg_amount": 0.0,
                    "reg_description": "",
                }
            ]
        )
        panel._table.setCurrentCell(0, 0)
        with patch(
            "desktop_app.statement_line_match_panel.message_box_information_ok"
        ) as m:
            panel.try_ctrl_shift_b_open_linked_business()
        m.assert_called_once()
        assert reg.tids == []
    finally:
        db.close()
        if db_path.exists():
            db_path.unlink()


def test_statement_line_match_panel_try_ctrl_shift_b_delegates_to_register_tab() -> None:
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication(sys.argv)

    from probooksai.bank_import import BankDatabase
    from desktop_app.statement_line_match_panel import StatementLineMatchPanel

    class _Reg:
        def __init__(self) -> None:
            self.tids: list[int] = []

        def open_linked_business_record_for_transaction_id(self, tid: int) -> None:
            self.tids.append(int(tid))

    db_path = Path(__file__).resolve().parent / "_stmt_line_match_try_b_delegate.db"
    if db_path.exists():
        db_path.unlink()
    db = BankDatabase(str(db_path))
    try:
        reg = _Reg()
        panel = StatementLineMatchPanel(db, register_tab=reg)
        panel.populate(
            [
                {
                    "status": STATUS_MATCHED,
                    "stmt_date": "2024-01-01",
                    "stmt_amount": -1.0,
                    "stmt_description": "A",
                    "register_id": 42,
                    "reg_date": "2024-01-01",
                    "reg_amount": -1.0,
                    "reg_description": "A",
                }
            ]
        )
        panel._table.setCurrentCell(0, 0)
        panel.try_ctrl_shift_b_open_linked_business()
        assert reg.tids == [42]
    finally:
        db.close()
        if db_path.exists():
            db_path.unlink()


def test_statement_line_match_panel_double_click_delegates_without_navigable_match() -> None:
    """Double-click forwards to the register tab even when ``get_bank_match`` is empty."""
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication(sys.argv)

    from probooksai.bank_import import BankDatabase
    from desktop_app.statement_line_match_panel import StatementLineMatchPanel

    class _Reg:
        def __init__(self) -> None:
            self.tids: list[int] = []

        def open_linked_business_record_for_transaction_id(self, tid: int) -> None:
            self.tids.append(int(tid))

    db_path = Path(__file__).resolve().parent / "_stmt_line_match_dbl_none.db"
    if db_path.exists():
        db_path.unlink()
    db = BankDatabase(str(db_path))
    try:
        reg = _Reg()
        panel = StatementLineMatchPanel(db, register_tab=reg)
        panel.populate(
            [
                {
                    "status": STATUS_MATCHED,
                    "stmt_date": "2024-01-01",
                    "stmt_amount": -1.0,
                    "stmt_description": "A",
                    "register_id": 7,
                    "reg_date": "2024-01-01",
                    "reg_amount": -1.0,
                    "reg_description": "A",
                }
            ]
        )
        with patch(
            "desktop_app.statement_line_match_panel.business.get_bank_match",
            return_value=None,
        ):
            panel._on_line_match_cell_double_clicked(0, 3)
        assert reg.tids == [7]
    finally:
        db.close()
        if db_path.exists():
            db_path.unlink()


def test_statement_line_match_panel_double_click_with_match_delegates() -> None:
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        QApplication(sys.argv)

    from probooksai.bank_import import BankDatabase
    from desktop_app.statement_line_match_panel import StatementLineMatchPanel

    class _Reg:
        def __init__(self) -> None:
            self.tids: list[int] = []

        def open_linked_business_record_for_transaction_id(self, tid: int) -> None:
            self.tids.append(int(tid))

    db_path = Path(__file__).resolve().parent / "_stmt_line_match_dbl_ok.db"
    if db_path.exists():
        db_path.unlink()
    db = BankDatabase(str(db_path))
    try:
        reg = _Reg()
        panel = StatementLineMatchPanel(db, register_tab=reg)
        panel.populate(
            [
                {
                    "status": STATUS_MATCHED,
                    "stmt_date": "2024-01-01",
                    "stmt_amount": -1.0,
                    "stmt_description": "A",
                    "register_id": 42,
                    "reg_date": "2024-01-01",
                    "reg_amount": -1.0,
                    "reg_description": "A",
                }
            ]
        )
        fake_bm = {"link_type": "ap_payment", "link_id": 3}
        with patch(
            "desktop_app.statement_line_match_panel.business.get_bank_match",
            return_value=fake_bm,
        ):
            panel._on_line_match_cell_double_clicked(0, 1)
        assert reg.tids == [42]
    finally:
        db.close()
        if db_path.exists():
            db_path.unlink()
