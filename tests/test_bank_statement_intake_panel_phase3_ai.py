"""Bank Statement Intake panel — phase 3 step 3 AI-fallback wiring tests.

Locks:

* Default: no AI provider wired → no AI-tagged suggestions appear even
  if the company setting is on.
* Provider wired but ``ai_intake_enabled`` setting OFF → still no AI
  suggestions (flag is the gate).
* Provider wired and flag ON → an AI-tagged suggestion appears for rows
  the rules+normalize path can't categorize.
* Normalize fallback is *always* on when DB is present (no opt-in
  needed at the panel level — it's part of the rules-engine workflow).
"""

from __future__ import annotations

import sys
from typing import Optional

import pytest
from PySide6.QtWidgets import QApplication

from desktop_app.bank_statement_intake_panel import BankStatementIntakePanel
from probooksai.bank_import import BankDatabase
from probooksai.bank_statement_intake import (
    SOURCE_TYPE_CSV,
    BankStatementIntakeRow,
)
from probooksai.bank_statement_intake_categorize import (
    AI_MATCHED_PATTERN_LABEL,
    CategorySuggestion,
)
from probooksai.business import set_setting
from probooksai.extensions_schema import apply_extensions
from probooksai.rules_engine import add_rule


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _open_db(tmp_path) -> BankDatabase:
    db = BankDatabase(str(tmp_path / "panel-ai.db"))
    apply_extensions(db._conn)
    return db


def _row(desc: str) -> BankStatementIntakeRow:
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
    )


def _fixed_provider(coa: str = "8000 — AI Suggested"):
    def _p(desc: str, normalized: str) -> Optional[CategorySuggestion]:
        return CategorySuggestion(
            coa_account=coa,
            matched_pattern="ignored-by-panel",
            confidence=0.55,
        )
    return _p


# ---------------------------------------------------------------------------
# Normalize fallback is always on when DB is present
# ---------------------------------------------------------------------------


def test_normalize_fallback_recovers_match_in_panel(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        add_rule(db._conn, "starbucks", "5010 — Meals", priority=10)
        w = BankStatementIntakePanel(bank_db=db)
        w.append_rows([_row("POS PURCHASE STARBUCKS #1234 NYC NY 02/14")])
        sug = w.category_suggestions_for_row(0)
        assert sug, "expected normalize fallback to recover the match"
        assert sug[0].coa_account == "5010 — Meals"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# AI flag gating
# ---------------------------------------------------------------------------


def test_ai_provider_not_consulted_when_flag_off(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        # Flag explicitly off (also the default).
        set_setting(db._conn, "ai_intake_enabled", "0")
        w = BankStatementIntakePanel(bank_db=db)
        w.set_ai_provider(_fixed_provider())
        w.append_rows([_row("Mystery Vendor 9999")])
        assert w.category_suggestions_for_row(0) == []
    finally:
        db.close()


def test_ai_provider_consulted_when_flag_on(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        set_setting(db._conn, "ai_intake_enabled", "1")
        w = BankStatementIntakePanel(bank_db=db)
        w.set_ai_provider(_fixed_provider("8000 — AI Suggested"))
        w.append_rows([_row("Mystery Vendor 9999")])
        sug = w.category_suggestions_for_row(0)
        assert sug, "expected AI provider to fire when flag is on"
        assert sug[0].coa_account == "8000 — AI Suggested"
        assert sug[0].matched_pattern == AI_MATCHED_PATTERN_LABEL
    finally:
        db.close()


def test_no_provider_wired_means_no_ai_even_with_flag_on(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        set_setting(db._conn, "ai_intake_enabled", "1")
        w = BankStatementIntakePanel(bank_db=db)
        # No set_ai_provider call.
        w.append_rows([_row("Mystery Vendor 9999")])
        assert w.category_suggestions_for_row(0) == []
    finally:
        db.close()


def test_truthy_flag_values_all_enable_ai(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        for value in ("1", "true", "TRUE", "yes", "On"):
            set_setting(db._conn, "ai_intake_enabled", value)
            w = BankStatementIntakePanel(bank_db=db)
            w.set_ai_provider(_fixed_provider())
            w.append_rows([_row("Mystery Vendor 9999")])
            assert (
                w.category_suggestions_for_row(0)
            ), f"expected AI fallback enabled for value={value!r}"
    finally:
        db.close()


def test_falsy_flag_values_all_disable_ai(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        for value in ("0", "false", "no", "off", ""):
            set_setting(db._conn, "ai_intake_enabled", value)
            w = BankStatementIntakePanel(bank_db=db)
            w.set_ai_provider(_fixed_provider())
            w.append_rows([_row("Mystery Vendor 9999")])
            assert (
                w.category_suggestions_for_row(0) == []
            ), f"expected AI fallback disabled for value={value!r}"
    finally:
        db.close()


def test_set_ai_provider_to_none_disables(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        set_setting(db._conn, "ai_intake_enabled", "1")
        w = BankStatementIntakePanel(bank_db=db)
        w.set_ai_provider(_fixed_provider())
        w.append_rows([_row("Mystery Vendor 9999")])
        assert w.category_suggestions_for_row(0)
        w.set_ai_provider(None)
        assert w.category_suggestions_for_row(0) == []
    finally:
        db.close()


def test_apply_suggestions_uses_ai_when_flag_on(qapp, tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        set_setting(db._conn, "ai_intake_enabled", "1")
        w = BankStatementIntakePanel(bank_db=db)
        w.set_ai_provider(_fixed_provider("8000 — AI Suggested"))
        w.append_rows([_row("Mystery Vendor 9999")])
        from PySide6.QtWidgets import QPushButton

        btns = {b.text(): b for b in w.findChildren(QPushButton)}
        btns["Apply suggestions"].click()
        from desktop_app.bank_statement_intake_panel import _HEADERS

        col = list(_HEADERS).index("Suggested category")
        cell = w._table.item(0, col)
        assert cell.text() == "8000 — AI Suggested"
    finally:
        db.close()
