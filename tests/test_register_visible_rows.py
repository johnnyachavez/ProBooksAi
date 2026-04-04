"""Register tab: visible pad rows and reconciliation overlay (Qt smoke)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from desktop_app.register_tab import (
    RegisterTab,
    _COL_DATE,
    _COL_RECON_STATUS,
    _REGISTER_MIN_VISIBLE_ROWS,
    _coerce_register_account_id,
    _register_account_ids_equal,
)
from probooksai.bank_import import BankDatabase
from probooksai.coa_db import COADatabase
from probooksai.statement_line_match import STATUS_MATCHED


def test_register_account_id_coerce_and_equal() -> None:
    assert _coerce_register_account_id(None) is None
    assert _coerce_register_account_id(3) == 3
    assert _coerce_register_account_id("7") == 7
    assert _coerce_register_account_id("x") is None
    assert _register_account_ids_equal(1, 1)
    assert _register_account_ids_equal(1, "1")
    assert not _register_account_ids_equal(1, 2)
    assert _register_account_ids_equal(None, None)
    assert not _register_account_ids_equal(None, 1)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_register_tab_shows_minimum_rows_on_build(qapp) -> None:
    p = Path(tempfile.mkdtemp()) / "reg_vis.db"
    db = BankDatabase(str(p))
    try:
        coa = COADatabase(db._conn)
        tab = RegisterTab(db, coa, None)
        assert tab._table.rowCount() == _REGISTER_MIN_VISIBLE_ROWS
        assert 15 <= _REGISTER_MIN_VISIBLE_ROWS <= 25
    finally:
        db.close()


def test_register_reconciliation_mode_keeps_rows_visible(qapp) -> None:
    p = Path(tempfile.mkdtemp()) / "reg_rec.db"
    db = BankDatabase(str(p))
    try:
        coa = COADatabase(db._conn)
        tab = RegisterTab(db, coa, None)
        tab._chk_recon.setChecked(True)
        assert tab._reconciliation_mode
        assert not tab._recon_banner.isHidden()
        assert not tab._table.horizontalHeader().isSectionHidden(_COL_RECON_STATUS)
        assert tab._table.rowCount() == _REGISTER_MIN_VISIBLE_ROWS
    finally:
        db.close()


def test_register_apply_line_match_from_import_sets_overlay(qapp) -> None:
    p = Path(tempfile.mkdtemp()) / "reg_overlay.db"
    db = BankDatabase(str(p))
    try:
        coa = COADatabase(db._conn)
        aid = db.add_bank_account("Primary")
        tid = db.insert_manual_transaction(
            aid, "2024-06-01", -12.0, description="Coffee", ref_number="", memo=""
        )
        tab = RegisterTab(db, coa, None)
        ok = tab.apply_line_match_results_from_import(
            aid,
            [
                {
                    "status": STATUS_MATCHED,
                    "register_id": tid,
                    "stmt_date": "",
                    "stmt_amount": 0.0,
                    "stmt_description": "",
                    "reg_date": "",
                    "reg_amount": 0.0,
                    "reg_description": "",
                }
            ],
        )
        assert ok is True
        assert tab._reconciliation_mode
        assert tab._recon_overlay_bank_import_mode
        assert tab._table.horizontalHeader().isSectionHidden(_COL_RECON_STATUS) is False
        found = False
        for r in range(tab._table.rowCount()):
            it = tab._table.item(r, _COL_DATE)
            if it is None:
                continue
            if it.data(Qt.ItemDataRole.UserRole) != tid:
                continue
            rc = tab._table.item(r, _COL_RECON_STATUS)
            assert rc is not None
            assert rc.text() == STATUS_MATCHED
            found = True
            break
        assert found
    finally:
        db.close()


def test_register_apply_line_match_accepts_string_coercible_ids(qapp) -> None:
    """Bank Import may forward account/register ids as strings; coercion should still apply overlay."""
    p = Path(tempfile.mkdtemp()) / "reg_overlay_str.db"
    db = BankDatabase(str(p))
    try:
        coa = COADatabase(db._conn)
        aid = db.add_bank_account("Primary")
        tid = db.insert_manual_transaction(
            aid, "2024-06-01", -12.0, description="Coffee", ref_number="", memo=""
        )
        tab = RegisterTab(db, coa, None)
        ok = tab.apply_line_match_results_from_import(
            str(aid),
            [
                {
                    "status": STATUS_MATCHED,
                    "register_id": str(tid),
                    "stmt_date": "",
                    "stmt_amount": 0.0,
                    "stmt_description": "",
                    "reg_date": "",
                    "reg_amount": 0.0,
                    "reg_description": "",
                }
            ],
        )
        assert ok is True
        assert tab._recon_txn_status[int(tid)] == STATUS_MATCHED
    finally:
        db.close()


def test_register_apply_line_match_unknown_account_leaves_recon_off(qapp) -> None:
    p = Path(tempfile.mkdtemp()) / "reg_bad_acct.db"
    db = BankDatabase(str(p))
    try:
        coa = COADatabase(db._conn)
        db.add_bank_account("Primary")
        tab = RegisterTab(db, coa, None)
        ok = tab.apply_line_match_results_from_import(
            9_999_999,
            [
                {
                    "status": STATUS_MATCHED,
                    "register_id": 1,
                    "stmt_date": "",
                    "stmt_amount": 0.0,
                    "stmt_description": "",
                    "reg_date": "",
                    "reg_amount": 0.0,
                    "reg_description": "",
                }
            ],
        )
        assert ok is False
        assert tab._reconciliation_mode is False
        assert tab._chk_recon.isChecked() is False
        assert tab._recon_overlay_bank_import_mode is False
    finally:
        db.close()


def test_bank_import_forward_line_match_warns_and_skips_focus_when_register_rejects(
    qapp,
) -> None:
    """``_forward_line_match_to_register`` shows a warning and does not run focus callback if apply fails."""
    from desktop_app.bank_import_tab import BankImportTab

    p = Path(tempfile.mkdtemp()) / "bi_stmt_forward.db"
    db = BankDatabase(str(p))
    try:
        reg = MagicMock()
        reg.apply_line_match_results_from_import.return_value = False
        focus = MagicMock()
        with patch.object(BankImportTab, "_build_ui", lambda self: None), patch.object(
            BankImportTab, "_refresh_accounts", lambda self: None
        ), patch("desktop_app.bank_import_tab.message_box_warning_ok") as warn:
            tab = BankImportTab(
                db,
                None,
                register_tab=reg,
                after_stmt_match_sync=focus,
            )
            payload = [{"register_id": 1, "status": STATUS_MATCHED}]
            tab._forward_line_match_to_register(42, payload)
        reg.apply_line_match_results_from_import.assert_called_once_with(42, payload)
        warn.assert_called_once()
        focus.assert_not_called()
    finally:
        db.close()


def test_bank_import_forward_line_match_coerces_string_account_id(qapp) -> None:
    """Stmt match forwarder coerces account id (e.g. string) before calling Register."""
    from desktop_app.bank_import_tab import BankImportTab

    p = Path(tempfile.mkdtemp()) / "bi_stmt_forward_coerce.db"
    db = BankDatabase(str(p))
    try:
        reg = MagicMock()
        reg.apply_line_match_results_from_import.return_value = True
        focus = MagicMock()
        with patch.object(BankImportTab, "_build_ui", lambda self: None), patch.object(
            BankImportTab, "_refresh_accounts", lambda self: None
        ), patch("desktop_app.bank_import_tab.message_box_warning_ok") as warn:
            tab = BankImportTab(
                db,
                None,
                register_tab=reg,
                after_stmt_match_sync=focus,
            )
            payload = [{"register_id": 1, "status": STATUS_MATCHED}]
            tab._forward_line_match_to_register("99", payload)
        reg.apply_line_match_results_from_import.assert_called_once_with(99, payload)
        warn.assert_not_called()
        focus.assert_called_once()
    finally:
        db.close()


def test_bank_import_forward_line_match_invalid_account_id_skips_register(qapp) -> None:
    from desktop_app.bank_import_tab import BankImportTab

    p = Path(tempfile.mkdtemp()) / "bi_stmt_forward_bad.db"
    db = BankDatabase(str(p))
    try:
        reg = MagicMock()
        focus = MagicMock()
        with patch.object(BankImportTab, "_build_ui", lambda self: None), patch.object(
            BankImportTab, "_refresh_accounts", lambda self: None
        ), patch("desktop_app.bank_import_tab.message_box_warning_ok") as warn:
            tab = BankImportTab(
                db,
                None,
                register_tab=reg,
                after_stmt_match_sync=focus,
            )
            tab._forward_line_match_to_register("x", [])
        reg.apply_line_match_results_from_import.assert_not_called()
        warn.assert_called_once()
        focus.assert_not_called()
    finally:
        db.close()


def test_bank_import_forward_line_match_calls_focus_when_register_accepts(qapp) -> None:
    from desktop_app.bank_import_tab import BankImportTab

    p = Path(tempfile.mkdtemp()) / "bi_stmt_forward_ok.db"
    db = BankDatabase(str(p))
    try:
        reg = MagicMock()
        reg.apply_line_match_results_from_import.return_value = True
        focus = MagicMock()
        with patch.object(BankImportTab, "_build_ui", lambda self: None), patch.object(
            BankImportTab, "_refresh_accounts", lambda self: None
        ), patch("desktop_app.bank_import_tab.message_box_warning_ok") as warn:
            tab = BankImportTab(
                db,
                None,
                register_tab=reg,
                after_stmt_match_sync=focus,
            )
            tab._forward_line_match_to_register(3, [])
        warn.assert_not_called()
        focus.assert_called_once()
    finally:
        db.close()
