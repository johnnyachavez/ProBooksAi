"""Regression: Write Checks **Find** is a real search across #/payee/amount/date."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from desktop_app.check_screen import CheckScreen
from desktop_app.qt_combo_ids import coerce_combo_int_id
from probooksai import business
from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import apply_extensions


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def db(tmp_path: Path):
    b = BankDatabase(db_path=str(tmp_path / "chk_find.db"))
    apply_extensions(b._conn)
    yield b
    b.close()


def _seed_three_checks(db: BankDatabase) -> tuple[int, list[int]]:
    aid = db.add_bank_account("Checking")
    business.add_vendor(db._conn, "Office Depot")
    business.add_vendor(db._conn, "Fuel Vendor")
    business.add_vendor(db._conn, "Shop Parts")
    ids = [
        db.insert_manual_transaction(
            aid, "2026-08-01", -125.00, description="Office Depot", ref_number="1001", memo="Toner"
        ),
        db.insert_manual_transaction(
            aid, "2026-08-05", -76.50, description="Fuel Vendor", ref_number="1002", memo="Diesel"
        ),
        db.insert_manual_transaction(
            aid, "2026-08-12", -450.00, description="Shop Parts", ref_number="1003", memo="Brakes"
        ),
    ]
    return aid, ids


def _select_bank(w: CheckScreen, bank_id: int) -> None:
    combo = w._acct_combo
    idx = next(
        (
            i
            for i in range(combo.count())
            if coerce_combo_int_id(combo.itemData(i)) == bank_id
        ),
        -1,
    )
    assert idx >= 0
    combo.setCurrentIndex(idx)


def test_find_button_enabled_once_a_check_exists(qapp, db) -> None:
    aid, _ = _seed_three_checks(db)
    w = CheckScreen(bank_db=db, ap_conn=db._conn)
    try:
        _select_bank(w, aid)
        assert w._btn_find.isEnabled()
        assert w._btn_find.text() == "Find"
        assert "search" in (w._btn_find.toolTip() or "").lower()
    finally:
        w.deleteLater()


def test_find_button_opens_search_dialog_and_loads_hit(qapp, db, monkeypatch) -> None:
    """Click Find → getText prompt → matching row loaded into the form."""
    aid, ids = _seed_three_checks(db)
    w = CheckScreen(bank_db=db, ap_conn=db._conn)
    try:
        _select_bank(w, aid)
        import desktop_app.check_screen as chk_mod

        monkeypatch.setattr(
            chk_mod.QInputDialog, "getText", staticmethod(lambda *a, **k: ("1002", True))
        )
        w._btn_find.click()
        qapp.processEvents()
        assert w._browse_index is not None
        assert w._browse_ids[w._browse_index] == ids[1]
    finally:
        w.deleteLater()


class TestCheckFindMatchers:
    def test_by_check_number(self, qapp, db) -> None:
        aid, ids = _seed_three_checks(db)
        w = CheckScreen(bank_db=db, ap_conn=db._conn)
        try:
            _select_bank(w, aid)
            hit = w.find_check_id_matching("1002")
            assert hit == ids[1]
        finally:
            w.deleteLater()

    def test_by_payee_substring_case_insensitive(self, qapp, db) -> None:
        aid, ids = _seed_three_checks(db)
        w = CheckScreen(bank_db=db, ap_conn=db._conn)
        try:
            _select_bank(w, aid)
            hit = w.find_check_id_matching("fuel")
            assert hit == ids[1]
        finally:
            w.deleteLater()

    def test_by_amount_absolute(self, qapp, db) -> None:
        aid, ids = _seed_three_checks(db)
        w = CheckScreen(bank_db=db, ap_conn=db._conn)
        try:
            _select_bank(w, aid)
            hit = w.find_check_id_matching("450")
            assert hit == ids[2]
            hit_signed = w.find_check_id_matching("-450.00")
            assert hit_signed == ids[2]
        finally:
            w.deleteLater()

    def test_by_us_date(self, qapp, db) -> None:
        aid, ids = _seed_three_checks(db)
        w = CheckScreen(bank_db=db, ap_conn=db._conn)
        try:
            _select_bank(w, aid)
            hit = w.find_check_id_matching("08/05/2026")
            assert hit == ids[1]
        finally:
            w.deleteLater()

    def test_by_iso_date(self, qapp, db) -> None:
        aid, ids = _seed_three_checks(db)
        w = CheckScreen(bank_db=db, ap_conn=db._conn)
        try:
            _select_bank(w, aid)
            hit = w.find_check_id_matching("2026-08-12")
            assert hit == ids[2]
        finally:
            w.deleteLater()

    def test_returns_none_for_no_match(self, qapp, db) -> None:
        aid, _ = _seed_three_checks(db)
        w = CheckScreen(bank_db=db, ap_conn=db._conn)
        try:
            _select_bank(w, aid)
            assert w.find_check_id_matching("9999") is None
        finally:
            w.deleteLater()

    def test_returns_none_when_no_bank_account_selected(self, qapp, db) -> None:
        w = CheckScreen(bank_db=db, ap_conn=db._conn)
        try:
            assert w.find_check_id_matching("anything") is None
        finally:
            w.deleteLater()
