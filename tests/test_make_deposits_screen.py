"""Make Deposits screen — QB Pro Payments to Deposit picker and bank posting."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QApplication,
    QDoubleSpinBox,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
)

from desktop_app.make_deposits_screen import MakeDepositsScreen, PaymentsToDepositDialog
from desktop_app.qt_combo_ids import coerce_combo_int_id
from desktop_app.theme import BG_PRIMARY
from probooksai import business
from probooksai.bank_import import BankDatabase
from probooksai.coa_db import COADatabase
from probooksai.extensions_schema import apply_extensions
from probooksai.gl import GLDatabase


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def db(tmp_path: Path) -> BankDatabase:
    b = BankDatabase(db_path=str(tmp_path / "dep.db"))
    apply_extensions(b._conn)
    yield b
    b.close()


@pytest.fixture
def gl_db(db: BankDatabase) -> BankDatabase:
    COADatabase(db._conn)
    GLDatabase(db._conn)
    ts = "2026-01-01T00:00:00+00:00"
    db._conn.execute(
        "INSERT OR IGNORE INTO coa_accounts "
        "(account_number, account_name, account_type, normal_balance, created_at) "
        "VALUES ('1010', 'CHASE BANK', 'asset', 'debit', ?)",
        (ts,),
    )
    db._conn.commit()
    return db


def _undeposited_payment(db: BankDatabase, *, name: str, amount: float, ref: str = "1001") -> int:
    cid = business.add_customer(db._conn, name)
    iid = business.create_invoice(
        db._conn,
        cid,
        f"INV-{name[:6]}",
        "2026-08-01",
        lines=[{"description": "Work", "qty": 1, "rate": amount}],
    )
    return business.record_ar_payment(
        db._conn,
        cid,
        "2026-08-10",
        amount,
        [(iid, amount)],
        bank_account_id=None,
        method="Check",
        reference=ref,
        memo="",
    )


def _select_bank(w: MakeDepositsScreen, bank_id: int) -> None:
    combo = w._deposit_to
    idx = next(
        (
            i
            for i in range(combo.count())
            if coerce_combo_int_id(combo.itemData(i)) == bank_id
        ),
        -1,
    )
    assert idx >= 0, f"bank {bank_id} not in Deposit To"
    combo.setCurrentIndex(idx)


def test_make_deposits_qb_header_grid_and_footer(qapp: QApplication) -> None:
    w = MakeDepositsScreen()
    labels = [lb.text() for lb in w.findChildren(QLabel)]
    assert "Make Deposits" in labels
    assert "DEPOSIT TO" in labels
    assert "DATE" in labels
    assert "MEMO" in labels
    assert "CASH BACK GOES TO" in labels
    assert "CASH BACK MEMO" in labels
    assert "CASH BACK AMOUNT" in labels
    assert "DEPOSIT SUBTOTAL" in labels
    assert "DEPOSIT TOTAL" in labels
    assert any("Petty Cash" in (lb.text() or "") for lb in w.findChildren(QLabel))

    btns = [b.text() for b in w.findChildren(QPushButton)]
    assert "Previous" in btns
    assert "Next" in btns
    assert "Save" in btns
    assert "Print" in btns
    assert "Payments" in btns
    assert "History" in btns
    assert "Attach" in btns
    assert any("Save" in b and "Close" in b for b in btns)
    assert any("Save" in b and "New" in b for b in btns)
    assert "Clear" in btns

    header = w.findChild(QFrame, "makeDepositsHeaderBand")
    assert header is not None
    wrap = w._deposit_to.parentWidget()
    assert wrap is not None
    assert wrap.objectName() == "makeDepositsMetaField"
    assert "#1a1a2e" not in wrap.styleSheet().lower()

    t = w.findChild(QTableWidget, "makeDepositsTable")
    assert t is not None
    assert t.columnCount() == 6
    assert t.horizontalHeaderItem(0).text() == "RECEIVED FROM"
    assert t.horizontalHeaderItem(1).text() == "FROM ACCOUNT"
    assert t.horizontalHeaderItem(2).text() == "MEMO"
    assert t.horizontalHeaderItem(3).text() == "CHK NO."
    assert t.horizontalHeaderItem(4).text() == "PMT METH."
    assert t.horizontalHeaderItem(5).text() == "AMOUNT"
    assert t.rowCount() >= 8

    memo = w.findChild(QLineEdit, "makeDepositsMemo")
    assert isinstance(memo, QLineEdit)
    assert (memo.placeholderText() or "").strip() == ""
    cash_memo = w.findChild(QLineEdit, "makeDepositsCashBackMemo")
    assert isinstance(cash_memo, QLineEdit)
    assert (cash_memo.placeholderText() or "").strip() == ""


def test_make_deposits_empty_line_cells_are_blank(qapp: QApplication) -> None:
    w = MakeDepositsScreen()
    t = w.findChild(QTableWidget, "makeDepositsTable")
    assert t is not None
    for col in range(5):
        cell = t.cellWidget(0, col)
        assert isinstance(cell, QLineEdit)
        assert (cell.placeholderText() or "").strip() == ""
        assert (cell.text() or "").strip() == ""
    amt = t.cellWidget(0, 5)
    assert isinstance(amt, QDoubleSpinBox)
    assert amt.value() == 0.0
    shown = (amt.lineEdit().text() if amt.lineEdit() is not None else amt.text()) or ""
    assert shown.strip() == ""
    assert "0.00" not in shown
    cash = w.findChild(QDoubleSpinBox, "makeDepositsCashBackAmount")
    assert isinstance(cash, QDoubleSpinBox)
    cash_shown = (cash.lineEdit().text() if cash.lineEdit() is not None else cash.text()) or ""
    assert "0.00" not in cash_shown


def test_make_deposits_meta_captions_stay_light_under_app_dark_theme(
    qapp: QApplication,
) -> None:
    from desktop_app.theme import apply_dark_theme

    old_ss = qapp.styleSheet()
    old_pal = QPalette(qapp.palette())
    try:
        apply_dark_theme(qapp)
        w = MakeDepositsScreen()
        w.show()
        qapp.processEvents()
        navy = BG_PRIMARY.lower()
        for editor in (w._deposit_to, w._dep_date, w._dep_memo):
            wrap = editor.parentWidget()
            assert wrap is not None
            assert wrap.objectName() == "makeDepositsMetaField"
            fill = wrap.palette().color(QPalette.ColorRole.Window).name().lower()
            assert fill != navy
            assert fill in ("#ffffff", "#f4f7fa")
            cap = wrap.findChild(QLabel)
            assert cap is not None
            cap_ss = cap.styleSheet().lower()
            assert "background: transparent" in cap_ss or "background-color: transparent" in cap_ss
            assert navy not in cap_ss
            assert "#1a1a2e" not in cap_ss
        w.close()
    finally:
        qapp.setStyleSheet(old_ss)
        qapp.setPalette(old_pal)


def test_payments_to_deposit_dialog_lists_undeposited(
    qapp: QApplication, db: BankDatabase
) -> None:
    pid = _undeposited_payment(db, name="Flatiron", amount=250.0, ref="779093")
    dlg = PaymentsToDepositDialog(business.list_undeposited_ar_payments(db._conn))
    t = dlg.findChild(QTableWidget, "paymentsToDepositTable")
    assert t is not None
    assert t.rowCount() == 1
    assert t.horizontalHeaderItem(1).text() == "DATE"
    assert t.horizontalHeaderItem(2).text() == "TIME"
    assert t.horizontalHeaderItem(3).text() == "TYPE"
    assert t.horizontalHeaderItem(5).text() == "PAYMENT METHOD"
    assert t.item(0, 3).text() == "PMT"
    assert t.item(0, 4).text() == "779093"
    assert "Flatiron" in (t.item(0, 6).text() or "")
    assert t.item(0, 2).text() == ""
    assert "0 of 1 payments selected" in (dlg._lbl_status.text() or "")
    dlg._on_select_all()
    rows = dlg.selected_rows()
    assert len(rows) == 1
    assert int(rows[0]["id"]) == pid
    assert "1 of 1 payments selected" in (dlg._lbl_status.text() or "")
    assert "250.00" in (dlg._lbl_subtotal.text() or "")
    btns = [b.text() for b in dlg.findChildren(QPushButton)]
    assert "Select All" in btns
    assert "Select None" in btns
    assert "OK" in btns
    assert "Cancel" in btns
    assert "Help" in btns
    dlg.close()


def test_make_deposits_posts_selected_payments_to_chase_bank(
    qapp: QApplication, gl_db: BankDatabase
) -> None:
    db = gl_db
    pid = _undeposited_payment(db, name="Performance Logistics", amount=400.0, ref="33554")
    aid = db.add_bank_account("CHASE BANK", gl_display_account="1010 CHASE BANK")
    w = MakeDepositsScreen(ap_conn=db._conn, bank_db=db)
    _select_bank(w, aid)
    dlg = PaymentsToDepositDialog(business.list_undeposited_ar_payments(db._conn))
    dlg._on_select_all()
    w._apply_dialog_selection(dlg)
    t = w.findChild(QTableWidget, "makeDepositsTable")
    assert t is not None
    received = t.cellWidget(0, 0)
    assert isinstance(received, QLineEdit)
    assert "Performance" in received.text()
    from_acct = t.cellWidget(0, 1)
    assert isinstance(from_acct, QLineEdit)
    assert from_acct.text() == "Undeposited Funds"
    with patch("desktop_app.make_deposits_screen.message_box_information_ok"):
        assert w._persist_deposit(reset=True)
    row = db._conn.execute(
        "SELECT bank_account_id FROM ar_payments WHERE id = ?", (pid,)
    ).fetchone()
    assert int(row["bank_account_id"]) == aid
    leftover = business.list_undeposited_ar_payments(db._conn)
    assert leftover == []
    txn = db._conn.execute(
        "SELECT amount, description, bank_account_id FROM bank_transactions "
        "WHERE bank_account_id = ?",
        (aid,),
    ).fetchone()
    assert txn is not None
    assert float(txn["amount"]) == pytest.approx(400.0)
    assert int(txn["bank_account_id"]) == aid
    je = db._conn.execute(
        "SELECT id FROM journal_entries WHERE source LIKE 'make_deposit:%' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert je is not None
    lines = db._conn.execute(
        "SELECT account, debit, credit FROM journal_entry_lines WHERE entry_id = ?",
        (je["id"],),
    ).fetchall()
    dr = next(l for l in lines if float(l["debit"]) > 0)
    cr = next(l for l in lines if float(l["credit"]) > 0)
    assert float(dr["debit"]) == pytest.approx(400.0)
    assert "CHASE" in (dr["account"] or "").upper() or "1010" in (dr["account"] or "")
    assert "Undeposited Funds" in (cr["account"] or "")
    cleared = t.cellWidget(0, 0)
    assert isinstance(cleared, QLineEdit)
    assert cleared.text() == ""


def test_deposit_ar_payments_skips_already_banked(db: BankDatabase) -> None:
    pid = _undeposited_payment(db, name="Once", amount=10.0)
    aid = db.add_bank_account("CHASE BANK")
    business.deposit_ar_payments(db._conn, [pid], aid, "2026-08-26")
    with pytest.raises(ValueError, match="already deposited"):
        business.deposit_ar_payments(db._conn, [pid], aid, "2026-08-27")


def test_deposit_ar_payments_cash_back_and_extra_line(gl_db: BankDatabase) -> None:
    db = gl_db
    pid = _undeposited_payment(db, name="MixCo", amount=100.0)
    aid = db.add_bank_account("CHASE BANK", gl_display_account="1010 CHASE BANK")
    result = business.deposit_ar_payments(
        db._conn,
        [pid],
        aid,
        "2026-08-26",
        memo="Weekly deposit",
        extra_lines=[
            {
                "received_from": "Owner",
                "from_account": "Owner Draw",
                "memo": "cash",
                "chk_no": "",
                "pmt_meth": "Cash",
                "amount": 20.0,
            }
        ],
        cash_back_account="Petty Cash",
        cash_back_amount=15.0,
        cash_back_memo="till",
    )
    assert result["deposit_total"] == pytest.approx(105.0)
    assert result["payments_total"] == pytest.approx(100.0)
    jeid = result["journal_entry_id"]
    assert jeid is not None
    lines = [
        dict(r)
        for r in db._conn.execute(
            "SELECT account, debit, credit FROM journal_entry_lines WHERE entry_id = ?",
            (jeid,),
        ).fetchall()
    ]
    assert sum(float(l["debit"]) for l in lines) == pytest.approx(
        sum(float(l["credit"]) for l in lines)
    )
    assert any(
        ("CHASE" in (l["account"] or "").upper() or "1010" in (l["account"] or ""))
        and float(l["debit"]) > 0
        for l in lines
    )
    assert any(l["account"] == "Petty Cash" and float(l["debit"]) == pytest.approx(15.0) for l in lines)
    assert any(
        l["account"] == "Undeposited Funds" and float(l["credit"]) == pytest.approx(100.0)
        for l in lines
    )
    assert any(l["account"] == "Owner Draw" and float(l["credit"]) == pytest.approx(20.0) for l in lines)


@pytest.mark.skipif(
    os.environ.get("QT_QPA_PLATFORM") == "offscreen",
    reason="QDialog.exec() enters a modal event loop that segfaults under the headless "
    "offscreen Qt platform (used by CI); construction and accept paths are covered "
    "without exec().",
)
def test_payments_to_deposit_exec_accepts(qapp: QApplication, db: BankDatabase) -> None:
    from PySide6.QtCore import QTimer

    _undeposited_payment(db, name="ExecCo", amount=5.0)
    dlg = PaymentsToDepositDialog(business.list_undeposited_ar_payments(db._conn))
    QTimer.singleShot(0, dlg.accept)
    rc = dlg.exec()
    assert rc == int(dlg.DialogCode.Accepted)
