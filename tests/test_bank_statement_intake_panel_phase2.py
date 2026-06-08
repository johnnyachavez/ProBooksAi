"""Bank Statement Intake panel — phase 2 (account combo, send, persistence) tests.

Layered on top of the phase-1 panel suite. Phase-1 tests must keep passing
unchanged because the panel falls back to review-only when ``bank_db`` is
``None``; this file covers what *changes* when the panel is constructed
with a live DB:

* Account combo populates from ``BankDatabase.list_bank_accounts``.
* Send button is disabled until DB + account + at least one staged row.
* Send routes through the hand-off, evicts inserted/duplicate rows from
  the table, keeps invalid rows for fix-up, and emits ``rowsSentToRegister``.
* Cancelling the confirmation prompt is a no-op.
* The persisted queue keeps state across panel reconstruction.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QComboBox, QPushButton

from desktop_app.bank_statement_intake_panel import BankStatementIntakePanel
from probooksai.bank_import import BankDatabase
from probooksai.bank_statement_intake import BankStatementIntakeRow
from probooksai.bank_statement_intake_persistence import (
    QUEUE_TABLE,
    count_intake_queue,
)
from probooksai.extensions_schema import apply_extensions


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _open_db(tmp_path) -> BankDatabase:
    db = BankDatabase(str(tmp_path / "panel-phase2.db"))
    apply_extensions(db._conn)
    return db


# ---------------------------------------------------------------------------
# Account combo
# ---------------------------------------------------------------------------


def test_account_combo_populates_from_bank_db(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        db.add_bank_account(name="Operating")
        db.add_bank_account(name="Savings")
        w = BankStatementIntakePanel(bank_db=db)
        combo = w.findChild(QComboBox, "statementIntakeAccountCombo")
        assert combo is not None
        names = [combo.itemText(i) for i in range(combo.count())]
        assert "Operating" in names and "Savings" in names
    finally:
        db.close()


def test_account_combo_shows_placeholder_when_no_accounts(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        w = BankStatementIntakePanel(bank_db=db)
        combo = w.findChild(QComboBox, "statementIntakeAccountCombo")
        assert combo is not None
        assert combo.count() == 1
        assert "no bank accounts" in combo.itemText(0).lower()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Send button gating
# ---------------------------------------------------------------------------


def _send_button(w) -> QPushButton:
    btns = {b.text(): b for b in w.findChildren(QPushButton)}
    return btns["Send to Bank Register"]


def test_send_button_disabled_without_db(qapp) -> None:
    w = BankStatementIntakePanel()
    assert _send_button(w).isEnabled() is False


def test_send_button_disabled_when_no_account_selected(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        w = BankStatementIntakePanel(bank_db=db)
        assert _send_button(w).isEnabled() is False
    finally:
        db.close()


def test_send_button_disabled_when_no_rows_staged(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        db.add_bank_account(name="Operating")
        w = BankStatementIntakePanel(bank_db=db)
        assert _send_button(w).isEnabled() is False
    finally:
        db.close()


def test_send_button_enabled_when_db_account_and_rows_present(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        db.add_bank_account(name="Operating")
        w = BankStatementIntakePanel(
            bank_db=db,
            confirm_factory=lambda prompt: True,
            info_factory=lambda text: None,
        )
        w.import_pasted_text("01/02/2026 Coffee Shop -4.50 995.50")
        assert _send_button(w).isEnabled() is True
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Send action
# ---------------------------------------------------------------------------


def test_send_inserts_rows_into_register_and_clears_them_from_table(
    qapp, tmp_path
) -> None:
    db = _open_db(tmp_path)
    try:
        aid = db.add_bank_account(name="Operating")
        w = BankStatementIntakePanel(
            bank_db=db,
            confirm_factory=lambda prompt: True,
            info_factory=lambda text: None,
        )
        text = (
            "01/02/2026 Coffee Shop -4.50 995.50\n"
            "01/03/2026 Payroll Deposit 1500.00 2495.50\n"
        )
        w.import_pasted_text(text)
        assert w.row_count() == 2

        sent_count = []
        w.rowsSentToRegister.connect(sent_count.append)
        _send_button(w).click()

        assert sent_count == [2]
        assert w.row_count() == 0

        # Verify register actually received the rows.
        rows = db._conn.execute(
            "SELECT amount FROM bank_transactions WHERE bank_account_id = ? "
            "ORDER BY txn_date",
            (aid,),
        ).fetchall()
        assert [r["amount"] for r in rows] == [-4.50, 1500.0]
    finally:
        db.close()


def test_send_keeps_invalid_rows_in_table_for_fix_up(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        db.add_bank_account(name="Operating")
        w = BankStatementIntakePanel(
            bank_db=db,
            confirm_factory=lambda prompt: True,
            info_factory=lambda text: None,
        )
        # Append one valid row + one invalid (no date / no amount) row directly.
        w.append_rows(
            [
                BankStatementIntakeRow(
                    txn_date="2026-01-02",
                    description_raw="Good",
                    debit=4.50,
                    credit=None,
                    amount_signed=-4.50,
                    source_type="text",
                    source_ref="L1",
                    confidence=1.0,
                    needs_review=False,
                ),
                BankStatementIntakeRow(
                    txn_date="",
                    description_raw="Bad",
                    debit=None,
                    credit=None,
                    amount_signed=None,
                    source_type="text",
                    source_ref="L2",
                    confidence=0.1,
                    needs_review=True,
                ),
            ]
        )
        assert w.row_count() == 2
        _send_button(w).click()
        # Valid row evicted; invalid row kept for the user to fix.
        assert w.row_count() == 1
        remaining = w.collect_rows()
        assert remaining[0].description_raw == "Bad"
    finally:
        db.close()


def test_send_cancelled_by_user_is_a_noop(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        aid = db.add_bank_account(name="Operating")
        w = BankStatementIntakePanel(
            bank_db=db,
            confirm_factory=lambda prompt: False,
            info_factory=lambda text: None,
        )
        w.import_pasted_text("01/02/2026 Coffee Shop -4.50 995.50")
        assert w.row_count() == 1
        _send_button(w).click()
        assert w.row_count() == 1
        n = db._conn.execute(
            "SELECT COUNT(*) AS n FROM bank_transactions WHERE bank_account_id = ?",
            (aid,),
        ).fetchone()
        assert int(n["n"]) == 0
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_appended_rows_are_persisted_to_intake_queue_table(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        db.add_bank_account(name="Operating")
        w = BankStatementIntakePanel(bank_db=db)
        w.import_pasted_text("01/02/2026 Coffee Shop -4.50 995.50")
        assert count_intake_queue(db._conn) == 1
    finally:
        db.close()


def test_clear_persists_empty_queue(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        db.add_bank_account(name="Operating")
        w = BankStatementIntakePanel(bank_db=db)
        w.import_pasted_text("01/02/2026 Coffee Shop -4.50 995.50")
        assert count_intake_queue(db._conn) == 1
        w.clear_rows()
        assert count_intake_queue(db._conn) == 0
    finally:
        db.close()


def test_panel_hydrates_from_persisted_queue_on_construction(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        db.add_bank_account(name="Operating")
        w1 = BankStatementIntakePanel(bank_db=db)
        w1.import_pasted_text(
            "01/02/2026 Coffee Shop -4.50 995.50\n"
            "01/03/2026 Payroll Deposit 1500.00 2495.50\n"
        )
        assert w1.row_count() == 2

        # Simulate an app restart by constructing a brand-new panel against
        # the same DB; the queue must come back.
        w2 = BankStatementIntakePanel(bank_db=db)
        assert w2.row_count() == 2
        descs = {r.description_raw for r in w2.collect_rows()}
        assert "Coffee Shop" in descs
        assert "Payroll Deposit" in descs
    finally:
        db.close()


def test_phase2_send_does_not_classify_to_coa_account(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        aid = db.add_bank_account(name="Operating")
        w = BankStatementIntakePanel(
            bank_db=db,
            confirm_factory=lambda prompt: True,
            info_factory=lambda text: None,
        )
        w.import_pasted_text("01/02/2026 Coffee Shop -4.50 995.50")
        _send_button(w).click()
        row = db._conn.execute(
            "SELECT coa_account FROM bank_transactions WHERE bank_account_id = ?",
            (aid,),
        ).fetchone()
        assert row is not None
        assert row["coa_account"] == ""
    finally:
        db.close()
