"""Tests for statement line vs register matching (AI reconciliation workflow)."""

from __future__ import annotations

import sys
from pathlib import Path

from probooksai.statement_line_match import (
    STATUS_EXTRA,
    STATUS_MATCHED,
    STATUS_MISSING,
    amounts_equal,
    compare_statement_to_register,
    dates_within_days,
    descriptions_match,
    mock_statement_lines_for_comparison,
    transaction_pair_matches,
)


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


def test_dates_within_days_day_first_when_month_gt_12_impossible() -> None:
    """``13/02/2024`` is parsed as DD/MM (Feb 13), not US month 13."""
    assert dates_within_days("13/02/2024", "2024-02-13", 2)


def test_compare_stmt_mdy_date_matches_register_iso() -> None:
    stmt = [{"txn_date": "1/10/2024", "amount": -10.0, "description": "Gas"}]
    reg = [{"id": 1, "txn_date": "2024-01-10", "amount": -10.0, "description": "Gas"}]
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


def test_descriptions_match_substring_and_fuzzy() -> None:
    assert descriptions_match("AMAZON MARKETPLACE", "amazon")
    assert descriptions_match("coffee", "COFFEE SHOP DOWNTOWN")
    assert descriptions_match("Wire Transfer Acme", "Wire Transfer Acme Corp")
    assert not descriptions_match("x", "yz")


def test_amounts_equal_coerces_currency_strings() -> None:
    assert amounts_equal("$1,234.50", 1234.5)
    assert amounts_equal("  -25.00 ", -25.0)
    assert amounts_equal("(10.00)", -10.0)
    assert amounts_equal("$0", 0.0)
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
    assert out[0]["status"] == STATUS_MISSING


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
        panel._mark_reviewed_all_matched()
        assert panel.reviewed_count() == 1
        panel._clear_reviewed()
        assert panel.reviewed_count() == 0
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
