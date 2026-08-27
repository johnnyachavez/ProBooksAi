"""Write Checks screen — QB Pro check layout and bank payment save flow."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTableWidget,
)

from desktop_app.check_screen import CheckScreen, amount_to_words
from desktop_app.qt_combo_ids import coerce_combo_int_id
from desktop_app.theme import BG_PRIMARY
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
def db(tmp_path: Path) -> BankDatabase:
    b = BankDatabase(db_path=str(tmp_path / "chk.db"))
    apply_extensions(b._conn)
    yield b
    b.close()


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
    assert idx >= 0, f"bank {bank_id} not in BANK ACCOUNT"
    combo.setCurrentIndex(idx)


def _select_payee(w: CheckScreen, vendor_id: int) -> None:
    combo = w._fld_payee
    idx = next(
        (
            i
            for i in range(combo.count())
            if coerce_combo_int_id(combo.itemData(i)) == vendor_id
        ),
        -1,
    )
    assert idx >= 0, f"vendor {vendor_id} not in PAY TO THE ORDER OF"
    combo.setCurrentIndex(idx)


def _fill_first_expense(w: CheckScreen, *, account: str, amount: float, memo: str, job: str = "") -> None:
    acct = w._exp_table.cellWidget(0, 0)
    assert isinstance(acct, QComboBox)
    acct.setEditText(account)
    amt = w._exp_table.cellWidget(0, 1)
    assert isinstance(amt, QDoubleSpinBox)
    amt.setValue(amount)
    memo_w = w._exp_table.cellWidget(0, 2)
    assert isinstance(memo_w, QLineEdit)
    memo_w.setText(memo)
    job_w = w._exp_table.cellWidget(0, 3)
    assert isinstance(job_w, QLineEdit)
    job_w.setText(job)


def test_write_checks_qb_header_grid_and_footer(qapp: QApplication) -> None:
    w = CheckScreen()
    labels = [lb.text() for lb in w.findChildren(QLabel)]
    assert "BANK ACCOUNT" in labels
    assert "ENDING BALANCE" in labels
    assert "NO." in labels
    assert "DATE" in labels
    assert "PAY TO THE ORDER OF" in labels
    assert "DOLLARS" in labels
    assert "ADDRESS" in labels
    assert "MEMO" in labels

    btns = [b.text() for b in w.findChildren(QPushButton)]
    assert "Find" in btns
    assert "New" in btns
    assert "Save" in btns
    assert "Delete" in btns
    assert "Memorize" in btns
    assert "Create a Copy" in btns
    assert "Print" in btns
    assert "Attach File" in btns
    assert "Clear Splits" in btns
    assert "Recalculate" in btns
    assert "Reorder Reminder" in btns
    assert "Order Checks" in btns
    assert any("Save" in b and "Close" in b for b in btns)
    assert any("Save" in b and "New" in b for b in btns)
    assert "Clear" in btns

    paper = w.findChild(QFrame, "writeChecksPaper")
    assert paper is not None
    assert "#1a1a2e" not in paper.styleSheet().lower()

    t = w.findChild(QTableWidget, "writeChecksExpensesTable")
    assert t is not None
    assert t.columnCount() == 5
    assert t.horizontalHeaderItem(0).text() == "ACCOUNT"
    assert t.horizontalHeaderItem(1).text() == "AMOUNT"
    assert t.horizontalHeaderItem(2).text() == "MEMO"
    assert t.horizontalHeaderItem(3).text() == "CUSTOMER:JOB"
    assert t.horizontalHeaderItem(4).text() == "BILLABLE?"
    assert t.rowCount() >= 12

    items = w.findChild(QTableWidget, "writeChecksItemsTable")
    assert items is not None
    assert items.horizontalHeaderItem(0).text() == "ITEM"
    assert items.horizontalHeaderItem(6).text() == "BILLABLE?"

    lines = w.findChild(QTabWidget, "writeChecksLineTabs")
    assert lines is not None
    assert lines.tabText(0).startswith("Expenses")
    assert lines.tabText(1).startswith("Items")

    wrap = w._acct_combo.parentWidget()
    assert wrap is not None
    assert wrap.objectName() == "writeChecksMetaField"
    assert "#1a1a2e" not in wrap.styleSheet().lower()

    memo = w.findChild(QLineEdit, "writeChecksMemo")
    assert isinstance(memo, QLineEdit)
    assert (memo.placeholderText() or "").strip() == ""
    num = w.findChild(QLineEdit, "writeChecksNumber")
    assert isinstance(num, QLineEdit)
    assert (num.placeholderText() or "").strip() == ""
    addr = w.findChild(QPlainTextEdit, "writeChecksAddress")
    assert isinstance(addr, QPlainTextEdit)
    assert (addr.placeholderText() or "").strip() == ""


def test_write_checks_empty_expense_cells_are_blank(qapp: QApplication) -> None:
    w = CheckScreen()
    w.show()
    qapp.processEvents()
    t = w.findChild(QTableWidget, "writeChecksExpensesTable")
    assert t is not None
    acct = t.cellWidget(0, 0)
    assert isinstance(acct, QComboBox)
    assert (acct.currentText() or "").strip() == ""
    assert "(select" not in (acct.itemText(0) or "").lower()
    amt = t.cellWidget(0, 1)
    assert isinstance(amt, QDoubleSpinBox)
    assert amt.value() == 0.0
    shown = (amt.lineEdit().text() if amt.lineEdit() is not None else amt.text()) or ""
    assert shown.strip() == ""
    assert "0.00" not in shown
    memo = t.cellWidget(0, 2)
    job = t.cellWidget(0, 3)
    assert isinstance(memo, QLineEdit) and isinstance(job, QLineEdit)
    assert (memo.placeholderText() or "").strip() == ""
    assert (job.placeholderText() or "").strip() == ""
    billable = t.cellWidget(0, 4)
    assert isinstance(billable, QCheckBox)
    assert billable.isChecked() is False

    items = w.findChild(QTableWidget, "writeChecksItemsTable")
    assert items is not None
    item_amt = items.cellWidget(0, 4)
    assert isinstance(item_amt, QDoubleSpinBox)
    item_shown = (item_amt.lineEdit().text() if item_amt.lineEdit() is not None else item_amt.text()) or ""
    assert item_shown.strip() == ""
    assert "0.00" not in item_shown
    w.close()


def test_write_checks_meta_captions_stay_light_under_app_dark_theme(
    qapp: QApplication,
) -> None:
    from desktop_app.theme import apply_dark_theme

    old_ss = qapp.styleSheet()
    old_pal = QPalette(qapp.palette())
    try:
        apply_dark_theme(qapp)
        w = CheckScreen()
        w.show()
        qapp.processEvents()
        navy = BG_PRIMARY.lower()
        wrap = w._acct_combo.parentWidget()
        assert wrap is not None
        assert wrap.objectName() == "writeChecksMetaField"
        fill = wrap.palette().color(QPalette.ColorRole.Window).name().lower()
        assert fill != navy
        assert fill in ("#ffffff", "#f4f7fa")
        cap = wrap.findChild(QLabel)
        assert cap is not None
        cap_ss = cap.styleSheet().lower()
        assert "transparent" in cap_ss
        assert navy not in cap_ss
        assert "#1a1a2e" not in cap_ss
        for editor in (w._fld_payee, w._fld_memo, w._fld_number, w._date_edit):
            parent = editor.parentWidget()
            assert parent is not None
            assert parent.objectName() == "writeChecksCaptionField"
            cap = parent.findChild(QLabel)
            assert cap is not None
            cap_ss = cap.styleSheet().lower()
            assert "transparent" in cap_ss
            assert navy not in cap_ss
            assert "#1a1a2e" not in cap_ss
            parent_ss = parent.styleSheet().lower()
            assert navy not in parent_ss
            assert "#1a1a2e" not in parent_ss
        paper = w.findChild(QFrame, "writeChecksPaper")
        assert paper is not None
        assert navy not in paper.styleSheet().lower()
        w.close()
    finally:
        qapp.setStyleSheet(old_ss)
        qapp.setPalette(old_pal)


def test_write_checks_vendor_fills_address(qapp: QApplication, db: BankDatabase) -> None:
    vid = business.add_vendor(
        db._conn,
        "Acme Supply",
        email="ap@acme.test",
        phone="555-0100",
        address="100 Main St\nSpringfield",
    )
    w = CheckScreen(bank_db=db, ap_conn=db._conn)
    _select_payee(w, vid)
    text = w._address_edit.toPlainText()
    assert "100 Main St" in text
    assert "ap@acme.test" in text
    assert "555-0100" in text
    w._fld_payee.setCurrentIndex(0)
    assert w._address_edit.toPlainText().strip() == ""


def test_write_checks_saves_vendor_payment_from_chase_bank(
    qapp: QApplication, db: BankDatabase
) -> None:
    aid = db.add_bank_account("CHASE BANK")
    vid = business.add_vendor(db._conn, "Office Depot")
    w = CheckScreen(bank_db=db, ap_conn=db._conn)
    _select_bank(w, aid)
    labels = [w._acct_combo.itemText(i) for i in range(w._acct_combo.count())]
    assert any("CHASE BANK" in (lb or "") for lb in labels)
    _select_payee(w, vid)
    w._fld_number.setText("1042")
    w._fld_memo.setText("August supplies")
    _fill_first_expense(w, account="6100 Office Supplies", amount=87.5, memo="Toner", job="Job:A")
    w._on_recalculate()
    with patch("desktop_app.check_screen.message_box_warning_ok"):
        assert w._persist_check(reset=False)
    txn = db._conn.execute(
        "SELECT * FROM bank_transactions WHERE bank_account_id = ?",
        (aid,),
    ).fetchone()
    assert txn is not None
    assert float(txn["amount"]) == pytest.approx(-87.5)
    assert (txn["description"] or "") == "Office Depot"
    assert (txn["ref_number"] or "") == "1042"
    assert (txn["memo"] or "") == "August supplies"
    assert "6100" in (txn["coa_account"] or "")
    splits = [dict(r) for r in business.list_splits(db._conn, int(txn["id"]))]
    assert len(splits) == 1
    assert float(splits[0]["amount"]) == pytest.approx(-87.5)
    assert "Toner" in (splits[0]["memo"] or "")
    assert "Job:A" in (splits[0]["memo"] or "")


def test_write_checks_multiple_expense_lines_become_splits(
    qapp: QApplication, db: BankDatabase
) -> None:
    aid = db.add_bank_account("CHASE BANK")
    vid = business.add_vendor(db._conn, "FuelCo")
    w = CheckScreen(bank_db=db, ap_conn=db._conn)
    _select_bank(w, aid)
    _select_payee(w, vid)
    _fill_first_expense(w, account="6200 Fuel", amount=40.0, memo="Diesel")
    acct2 = w._exp_table.cellWidget(1, 0)
    assert isinstance(acct2, QComboBox)
    acct2.setEditText("6300 Tolls")
    amt2 = w._exp_table.cellWidget(1, 1)
    assert isinstance(amt2, QDoubleSpinBox)
    amt2.setValue(12.25)
    with patch("desktop_app.check_screen.message_box_warning_ok"):
        assert w._persist_check(reset=True)
    txn = db._conn.execute(
        "SELECT id, amount FROM bank_transactions WHERE bank_account_id = ?",
        (aid,),
    ).fetchone()
    assert txn is not None
    assert float(txn["amount"]) == pytest.approx(-52.25)
    splits = [dict(r) for r in business.list_splits(db._conn, int(txn["id"]))]
    assert len(splits) == 2
    amounts = sorted(abs(float(s["amount"])) for s in splits)
    assert amounts == pytest.approx([12.25, 40.0])
    # Save & New clears the form.
    amt0 = w._exp_table.cellWidget(0, 1)
    assert isinstance(amt0, QDoubleSpinBox)
    assert amt0.value() == 0.0
    shown = (amt0.lineEdit().text() if amt0.lineEdit() is not None else amt0.text()) or ""
    assert "0.00" not in shown


def test_write_checks_clear_resets_rows(qapp: QApplication) -> None:
    w = CheckScreen()
    _fill_first_expense(w, account="6100 Fuel", amount=9.99, memo="x", job="C:J")
    w._expense_billable[0].setChecked(True)
    w._spin_amount.setValue(9.99)
    w._on_clear()
    acct = w._exp_table.cellWidget(0, 0)
    assert isinstance(acct, QComboBox)
    assert (acct.currentText() or "").strip() == ""
    amt = w._exp_table.cellWidget(0, 1)
    assert isinstance(amt, QDoubleSpinBox)
    assert amt.value() == 0.0
    memo = w._exp_table.cellWidget(0, 2)
    assert isinstance(memo, QLineEdit)
    assert memo.text() == ""
    assert w._expense_billable[0].isChecked() is False
    assert w._spin_amount.value() == pytest.approx(0.0)


def test_amount_to_words_check_english() -> None:
    assert amount_to_words(0) == "Zero and 00/100"
    assert "One Thousand Two Hundred Thirty-Four" in amount_to_words(1234.56)
    assert amount_to_words(1234.56).endswith("56/100")


def test_check_screen_select_payee_vendor(qapp: QApplication, db: BankDatabase) -> None:
    vid = business.add_vendor(db._conn, "Office Supplies Co")
    w = CheckScreen(bank_db=db, ap_conn=db._conn)
    w.select_payee_vendor(vid)
    assert coerce_combo_int_id(w._fld_payee.currentData()) == vid
