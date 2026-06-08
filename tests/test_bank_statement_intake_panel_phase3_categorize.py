"""Bank Statement Intake panel — phase 3 step 2 categorization tests.

Locks the panel-side wiring of ``suggest_categories_for_rows``:

* "Suggested category" column is present and editable.
* Tooltips on cells show rule-engine suggestions when a rule matches.
* "Apply suggestions" button writes the top suggestion into empty cells
  only — never overwrites a user-typed COA.
* Persistence round-trips ``coa_account`` across panel reconstruction.
* Hand-off carries the chosen ``coa_account`` to ``bank_transactions``.
"""

from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from desktop_app.bank_statement_intake_panel import (
    _HEADERS,
    BankStatementIntakePanel,
)
from probooksai.bank_import import BankDatabase
from probooksai.bank_statement_intake import (
    SOURCE_TYPE_CSV,
    BankStatementIntakeRow,
)
from probooksai.extensions_schema import apply_extensions
from probooksai.rules_engine import add_rule


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _open_db(tmp_path) -> BankDatabase:
    db = BankDatabase(str(tmp_path / "panel-categorize.db"))
    apply_extensions(db._conn)
    return db


def _row(desc: str, *, coa: str = "") -> BankStatementIntakeRow:
    return BankStatementIntakeRow(
        txn_date="2026-03-10",
        description_raw=desc,
        debit=4.50,
        credit=None,
        amount_signed=-4.50,
        running_balance=None,
        source_type=SOURCE_TYPE_CSV,
        source_ref="x.csv#L1",
        confidence=1.0,
        needs_review=False,
        coa_account=coa,
    )


def _apply_button(w) -> QPushButton:
    btns = {b.text(): b for b in w.findChildren(QPushButton)}
    return btns["Apply suggestions"]


def _coa_col_index() -> int:
    return list(_HEADERS).index("Suggested category")


# ---------------------------------------------------------------------------
# Column structure
# ---------------------------------------------------------------------------


def test_suggested_category_column_is_present(qapp) -> None:
    w = BankStatementIntakePanel()
    assert "Suggested category" in _HEADERS


def test_suggested_category_column_is_editable(qapp) -> None:
    from PySide6.QtCore import Qt

    w = BankStatementIntakePanel()
    w.append_rows([_row("STARBUCKS NYC")])
    item = w._table.item(0, _coa_col_index())
    assert item is not None
    assert bool(item.flags() & Qt.ItemFlag.ItemIsEditable)


def test_apply_suggestions_button_exists(qapp) -> None:
    w = BankStatementIntakePanel()
    btns = {b.text() for b in w.findChildren(QPushButton)}
    assert "Apply suggestions" in btns


# ---------------------------------------------------------------------------
# Phase-1 fallback: panel still works without bank_db
# ---------------------------------------------------------------------------


def test_apply_button_disabled_without_db(qapp) -> None:
    w = BankStatementIntakePanel()
    w.append_rows([_row("STARBUCKS NYC")])
    assert _apply_button(w).isEnabled() is False


def test_apply_button_disabled_without_rows(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        w = BankStatementIntakePanel(bank_db=db)
        assert _apply_button(w).isEnabled() is False
    finally:
        db.close()


def test_apply_button_enabled_with_db_and_rows(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        w = BankStatementIntakePanel(bank_db=db)
        w.append_rows([_row("STARBUCKS NYC")])
        assert _apply_button(w).isEnabled() is True
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Auto-suggestion side-map + tooltips
# ---------------------------------------------------------------------------


def test_suggestions_populate_after_append_when_rule_matches(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        add_rule(db._conn, "starbucks", "5010 — Meals", priority=10)
        w = BankStatementIntakePanel(bank_db=db)
        w.append_rows([_row("STARBUCKS NYC"), _row("Random Vendor")])
        assert w.category_suggestions_for_row(0)[0].coa_account == "5010 — Meals"
        assert w.category_suggestions_for_row(1) == []
        # Tooltip is set on the matched row's cell.
        cell = w._table.item(0, _coa_col_index())
        assert "Rules-engine" in cell.toolTip()
        assert "5010 — Meals" in cell.toolTip()
    finally:
        db.close()


def test_apply_writes_top_suggestion_into_empty_cell(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        add_rule(db._conn, "starbucks", "5010 — Meals", priority=10)
        w = BankStatementIntakePanel(bank_db=db)
        w.append_rows([_row("STARBUCKS NYC")])
        cell = w._table.item(0, _coa_col_index())
        assert cell.text() == ""
        _apply_button(w).click()
        cell = w._table.item(0, _coa_col_index())
        assert cell.text() == "5010 — Meals"
    finally:
        db.close()


def test_apply_does_not_overwrite_user_typed_coa(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        add_rule(db._conn, "starbucks", "5010 — Meals", priority=10)
        w = BankStatementIntakePanel(bank_db=db)
        w.append_rows([_row("STARBUCKS NYC", coa="9999 — User Override")])
        _apply_button(w).click()
        cell = w._table.item(0, _coa_col_index())
        assert cell.text() == "9999 — User Override"
    finally:
        db.close()


def test_apply_is_noop_when_no_rule_fires(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        w = BankStatementIntakePanel(bank_db=db)
        w.append_rows([_row("Some Mystery Vendor")])
        _apply_button(w).click()
        cell = w._table.item(0, _coa_col_index())
        assert cell.text() == ""
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Persistence round-trip
# ---------------------------------------------------------------------------


def test_coa_account_persists_across_panel_reconstruction(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        add_rule(db._conn, "starbucks", "5010 — Meals", priority=10)
        w1 = BankStatementIntakePanel(bank_db=db)
        w1.append_rows([_row("STARBUCKS NYC")])
        _apply_button(w1).click()
        cell = w1._table.item(0, _coa_col_index())
        assert cell.text() == "5010 — Meals"

        w2 = BankStatementIntakePanel(bank_db=db)
        cell2 = w2._table.item(0, _coa_col_index())
        assert cell2 is not None
        assert cell2.text() == "5010 — Meals"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Hand-off integration
# ---------------------------------------------------------------------------


def test_send_carries_coa_account_into_register(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        aid = db.add_bank_account(name="Operating")
        add_rule(db._conn, "starbucks", "5010 — Meals", priority=10)
        w = BankStatementIntakePanel(
            bank_db=db,
            confirm_factory=lambda prompt: True,
            info_factory=lambda text: None,
        )
        w.append_rows([_row("STARBUCKS NYC")])
        _apply_button(w).click()
        # Trigger send via the Send button.
        btns = {b.text(): b for b in w.findChildren(QPushButton)}
        btns["Send to Bank Register"].click()

        row = db._conn.execute(
            "SELECT coa_account FROM bank_transactions WHERE bank_account_id = ?",
            (aid,),
        ).fetchone()
        assert row is not None
        assert row["coa_account"] == "5010 — Meals"
    finally:
        db.close()
