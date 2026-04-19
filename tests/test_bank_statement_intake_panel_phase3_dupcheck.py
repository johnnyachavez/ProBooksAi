"""Bank Statement Intake panel — phase 3 step 1: duplicate-check column tests.

Locks the panel-side wiring of ``find_register_duplicates``:

* "Possible duplicate" column is present, read-only, and last in the
  display order.
* Auto-runs after every append / edit / clear and on account changes.
* "Check duplicates" button is present and gated alongside Send.
* Side-map ``duplicate_match_for_row`` returns the right metadata.
* Panel keeps working when ``bank_db`` is absent (Phase-1 fallback).
"""

from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from desktop_app.bank_statement_intake_panel import (
    _DUP_REGISTER_FIELD,
    _HEADERS,
    BankStatementIntakePanel,
)
from probooksai.bank_import import BankDatabase
from probooksai.bank_statement_intake import BankStatementIntakeRow
from probooksai.extensions_schema import apply_extensions


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _open_db(tmp_path) -> BankDatabase:
    db = BankDatabase(str(tmp_path / "panel-phase3.db"))
    apply_extensions(db._conn)
    return db


def _seed_register_row(
    db: BankDatabase,
    account_id: int,
    *,
    txn_date: str,
    description: str,
    amount: float,
) -> int:
    batch_id = db.create_batch(
        bank_account_id=account_id, filename="(seed)"
    )
    db.import_transactions(
        batch_id=batch_id,
        bank_account_id=account_id,
        rows=[
            {
                "txn_date": txn_date,
                "description": description,
                "amount": amount,
                "balance": None,
                "tag_or_check": None,
                "split_label": None,
                "memo": "",
                "extras": {},
            }
        ],
    )
    row = db._conn.execute(
        "SELECT id FROM bank_transactions WHERE bank_account_id = ? "
        "ORDER BY id DESC LIMIT 1",
        (account_id,),
    ).fetchone()
    return int(row["id"])


def _row(date: str, desc: str, amount: float) -> BankStatementIntakeRow:
    return BankStatementIntakeRow(
        txn_date=date,
        description_raw=desc,
        debit=-amount if amount < 0 else None,
        credit=amount if amount > 0 else None,
        amount_signed=amount,
        running_balance=None,
        source_type="csv",
        source_ref="t.csv#L1",
        confidence=1.0,
        needs_review=False,
    )


def _check_button(w) -> QPushButton:
    btns = {b.text(): b for b in w.findChildren(QPushButton)}
    return btns["Check duplicates"]


def _dup_col_index() -> int:
    return list(_HEADERS).index("Possible duplicate")


# ---------------------------------------------------------------------------
# Column structure
# ---------------------------------------------------------------------------


def test_possible_duplicate_column_is_present_and_last(qapp) -> None:
    w = BankStatementIntakePanel()
    assert _HEADERS[-1] == "Possible duplicate"
    assert w._table.columnCount() == len(_HEADERS)


def test_possible_duplicate_column_is_read_only(qapp) -> None:
    w = BankStatementIntakePanel()
    w.append_rows([_row("2026-02-10", "Coffee", -4.50)])
    item = w._table.item(0, _dup_col_index())
    from PySide6.QtCore import Qt

    assert not (item.flags() & Qt.ItemFlag.ItemIsEditable)


def test_check_duplicates_button_exists(qapp) -> None:
    w = BankStatementIntakePanel()
    btns = {b.text() for b in w.findChildren(QPushButton)}
    assert "Check duplicates" in btns


# ---------------------------------------------------------------------------
# Phase-1 fallback: panel still works without bank_db
# ---------------------------------------------------------------------------


def test_dup_column_blank_when_no_bank_db(qapp) -> None:
    w = BankStatementIntakePanel()
    w.append_rows([_row("2026-02-10", "Coffee", -4.50)])
    item = w._table.item(0, _dup_col_index())
    assert item is not None
    assert item.text() == ""
    assert _check_button(w).isEnabled() is False


# ---------------------------------------------------------------------------
# Auto-scan on append / edit / account change
# ---------------------------------------------------------------------------


def test_dup_badge_populates_on_append_when_match_exists(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        aid = db.add_bank_account(name="Operating")
        rid = _seed_register_row(
            db, aid, txn_date="2026-02-10",
            description="Coffee Shop", amount=-4.50,
        )
        w = BankStatementIntakePanel(bank_db=db)
        w.append_rows([_row("2026-02-10", "Coffee Shop", -4.50)])
        item = w._table.item(0, _dup_col_index())
        assert item is not None
        assert str(rid) in item.text()
        assert "exact" in item.text()
        match = w.duplicate_match_for_row(0)
        assert match is not None and match.register_txn_id == rid
    finally:
        db.close()


def test_dup_badge_blank_when_no_register_match(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        db.add_bank_account(name="Operating")
        w = BankStatementIntakePanel(bank_db=db)
        w.append_rows([_row("2026-02-10", "Coffee Shop", -4.50)])
        item = w._table.item(0, _dup_col_index())
        assert item is not None and item.text() == ""
        assert w.duplicate_match_for_row(0) is None
    finally:
        db.close()


def test_dup_badge_refreshes_when_account_changes(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        aid_a = db.add_bank_account(name="Operating")
        aid_b = db.add_bank_account(name="Savings")
        _seed_register_row(
            db, aid_a, txn_date="2026-02-10",
            description="Coffee Shop", amount=-4.50,
        )
        w = BankStatementIntakePanel(bank_db=db)
        w.append_rows([_row("2026-02-10", "Coffee Shop", -4.50)])

        combo = w._account_combo
        # Select Savings (no match).
        idx_b = combo.findData(aid_b)
        assert idx_b >= 0
        combo.setCurrentIndex(idx_b)
        item = w._table.item(0, _dup_col_index())
        assert item.text() == ""
        # Switch to Operating (match).
        idx_a = combo.findData(aid_a)
        assert idx_a >= 0
        combo.setCurrentIndex(idx_a)
        item = w._table.item(0, _dup_col_index())
        assert item.text() != ""
    finally:
        db.close()


def test_check_duplicates_button_runs_scan_on_demand(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        aid = db.add_bank_account(name="Operating")
        w = BankStatementIntakePanel(bank_db=db)
        w.append_rows([_row("2026-02-10", "Coffee Shop", -4.50)])
        # No match yet.
        assert w._table.item(0, _dup_col_index()).text() == ""
        # Seed a register row that should now match.
        _seed_register_row(
            db, aid, txn_date="2026-02-10",
            description="Coffee Shop", amount=-4.50,
        )
        _check_button(w).click()
        assert w._table.item(0, _dup_col_index()).text() != ""
    finally:
        db.close()


def test_dup_column_clears_when_rows_cleared(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        aid = db.add_bank_account(name="Operating")
        _seed_register_row(
            db, aid, txn_date="2026-02-10",
            description="Coffee Shop", amount=-4.50,
        )
        w = BankStatementIntakePanel(
            bank_db=db,
            confirm_factory=lambda prompt: True,
            info_factory=lambda text: None,
        )
        w.append_rows([_row("2026-02-10", "Coffee Shop", -4.50)])
        assert w.duplicate_match_for_row(0) is not None
        w.clear_rows()
        assert w._dup_matches == {}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Persistence invariant: dup column is computed only, never persisted.
# ---------------------------------------------------------------------------


def test_dup_field_name_is_sentinel_not_a_dataclass_field(qapp) -> None:
    """Sentinel field for the dup column must not collide with any
    BankStatementIntakeRow attribute (otherwise persistence would clobber
    or be clobbered by it)."""
    sample = BankStatementIntakeRow()
    assert not hasattr(sample, _DUP_REGISTER_FIELD)
