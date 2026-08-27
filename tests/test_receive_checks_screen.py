"""Receive Payments screen — QB Pro Customer Payment layout and A/R wiring."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDoubleSpinBox,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QTableWidget,
)

from desktop_app.qt_combo_ids import coerce_combo_int_id
from desktop_app.receive_checks_screen import ReceiveChecksScreen
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
    b = BankDatabase(db_path=str(tmp_path / "rcv.db"))
    apply_extensions(b._conn)
    yield b
    b.close()


def _select_customer(w: ReceiveChecksScreen, customer_id: int) -> None:
    combo = w._customer_filter
    idx = next(
        (
            i
            for i in range(combo.count())
            if coerce_combo_int_id(combo.itemData(i)) == customer_id
        ),
        -1,
    )
    assert idx >= 0, f"customer {customer_id} not in Received From"
    combo.setCurrentIndex(idx)


def test_receive_checks_screen_table_headers(qapp: QApplication) -> None:
    w = ReceiveChecksScreen()
    t = w.findChild(QTableWidget, "receiveChecksTable")
    assert t is not None
    assert t.columnCount() == 6
    assert t.horizontalHeaderItem(0).text() == "✓"
    assert t.horizontalHeaderItem(1).text() == "DATE"
    assert t.horizontalHeaderItem(2).text() == "NUMBER"
    assert t.horizontalHeaderItem(3).text() == "ORIG. AMT."
    assert t.horizontalHeaderItem(4).text() == "AMT. DUE"
    assert t.horizontalHeaderItem(5).text() == "PAYMENT"


def test_receive_payments_qb_header_and_footer(qapp: QApplication) -> None:
    w = ReceiveChecksScreen()
    labels = [lb.text() for lb in w.findChildren(QLabel)]
    assert "Customer Payment" in labels
    assert "RECEIVED FROM" in labels
    assert "PAYMENT AMOUNT" in labels
    assert "DATE" in labels
    assert "CHECK #" in labels
    assert "A/R ACCOUNT" in labels
    assert "CUSTOMER BALANCE" in labels
    assert "MEMO" in labels
    assert "AMOUNTS FOR SELECTED INVOICES" in labels
    assert any("Where does this payment go?" in (lb.text() or "") for lb in w.findChildren(QLabel))

    btns = [b.text() for b in w.findChildren(QPushButton)]
    assert "CASH" in btns
    assert "CHECK" in btns
    assert "CREDIT/DEBIT" in btns
    assert "e-CHECK" in btns
    assert any("Save" in b and "Close" in b for b in btns)
    assert any("Save" in b and "New" in b for b in btns)
    assert "Clear" in btns
    assert "Auto Apply Payment" in btns
    assert "Discounts And Credits" in btns
    assert "Find" in btns
    assert "New" in btns

    ribbon = w.findChild(QTabWidget, "receivePaymentsRibbonTabs")
    assert ribbon is not None
    assert [ribbon.tabText(i) for i in range(ribbon.count())] == [
        "Main",
        "Formatting",
        "Reports",
        "Payments",
    ]
    header = w.findChild(QFrame, "receivePaymentsHeaderBand")
    assert header is not None
    wrap = w._customer_filter.parentWidget()
    assert wrap is not None
    assert wrap.objectName() == "receivePaymentsMetaField"
    assert "#1a1a2e" not in wrap.styleSheet().lower()
    assert w._btn_method_check.isChecked()
    assert w._btn_auto_apply.isChecked()
    t = w.findChild(QTableWidget, "receiveChecksTable")
    assert t is not None
    assert t.rowCount() == 0
    hint = w.findChild(QLabel, "receivePaymentsEmptyHint")
    assert hint is not None
    assert "Received From" in (hint.text() or "")
    check_num = w.findChild(QLineEdit, "receivePaymentsCheckNumber")
    assert isinstance(check_num, QLineEdit)
    assert (check_num.placeholderText() or "").strip() == ""
    memo = w.findChild(QLineEdit, "receivePaymentsMemo")
    assert isinstance(memo, QLineEdit)
    assert (memo.placeholderText() or "").strip() == ""


def test_receive_payments_meta_captions_stay_light_under_app_dark_theme(
    qapp: QApplication,
) -> None:
    from desktop_app.theme import apply_dark_theme

    old_ss = qapp.styleSheet()
    old_pal = QPalette(qapp.palette())
    try:
        apply_dark_theme(qapp)
        w = ReceiveChecksScreen()
        w.show()
        qapp.processEvents()
        navy = BG_PRIMARY.lower()
        for editor in (w._customer_filter, w._pay_amount, w._pay_date, w._check_num, w._ar_account):
            wrap = editor.parentWidget()
            assert wrap is not None
            assert wrap.objectName() == "receivePaymentsMetaField"
            fill = wrap.palette().color(QPalette.ColorRole.Window).name().lower()
            assert fill != navy
            assert fill in ("#ffffff", "#f4f7fa")
            cap = wrap.findChild(QLabel)
            assert cap is not None
            cap_ss = cap.styleSheet().lower()
            assert "transparent" in cap_ss
            assert "#4a5560" in cap_ss or "#1a1a1a" in cap_ss
        w.close()
    finally:
        qapp.setStyleSheet(old_ss)
        qapp.setPalette(old_pal)


def test_receive_checks_parent_vs_job_customer_filter(
    qapp: QApplication, db: BankDatabase
) -> None:
    """Mother ship lists all job open invoices; selecting a job lists only that job."""
    p = business.add_customer(db._conn, "ParentCo")
    j = business.add_customer(db._conn, "JobA", parent_customer_id=p)
    business.create_invoice(
        db._conn,
        p,
        "INV-P",
        "2024-05-01",
        lines=[{"description": "a", "qty": 1, "rate": 30.0}],
    )
    business.create_invoice(
        db._conn,
        j,
        "INV-J",
        "2024-05-02",
        lines=[{"description": "b", "qty": 1, "rate": 20.0}],
    )
    w = ReceiveChecksScreen(ap_conn=db._conn, bank_db=db)
    t = w.findChild(QTableWidget, "receiveChecksTable")
    assert t is not None
    assert t.rowCount() == 0
    combo = w._customer_filter
    idx_p = next(
        i
        for i in range(combo.count())
        if combo.itemData(i) is not None and int(combo.itemData(i)) == p
    )
    idx_j = next(
        i
        for i in range(combo.count())
        if combo.itemData(i) is not None and int(combo.itemData(i)) == j
    )
    combo.setCurrentIndex(idx_j)
    assert t.rowCount() == 1
    assert "INV-J" in (t.item(0, 2).text() or "")
    combo.setCurrentIndex(idx_p)
    assert t.rowCount() == 2
    nums = sorted((t.item(i, 2).text() or "") for i in range(t.rowCount()))
    assert "INV-J" in nums and "INV-P" in nums


def test_receive_checks_loads_open_invoice_row(
    qapp: QApplication, db: BankDatabase
) -> None:
    cid = business.add_customer(db._conn, "PayCo")
    business.create_invoice(
        db._conn,
        cid,
        "INV-R1",
        "2024-06-01",
        due_date="2024-06-15",
        lines=[{"description": "Work", "qty": 1, "rate": 100.0}],
    )
    w = ReceiveChecksScreen(ap_conn=db._conn, bank_db=db)
    t = w.findChild(QTableWidget, "receiveChecksTable")
    assert t is not None
    _select_customer(w, cid)
    assert t.rowCount() == 1
    assert "INV-R1" in (t.item(0, 2).text() or "")
    spin = t.cellWidget(0, 5)
    assert isinstance(spin, QDoubleSpinBox)
    assert spin.maximum() == pytest.approx(100.0)
    assert spin.value() == pytest.approx(0.0)
    shown = (spin.lineEdit().text() if spin.lineEdit() is not None else spin.text()) or ""
    assert shown.strip() == ""
    assert "0.00" not in shown


def test_receive_checks_shows_hierarchical_customer_label_for_job(
    qapp: QApplication, db: BankDatabase
) -> None:
    p = business.add_customer(db._conn, "ShipCo")
    j = business.add_customer(db._conn, "Berth1", parent_customer_id=p)
    business.create_invoice(
        db._conn,
        j,
        "INV-H",
        "2024-09-01",
        lines=[{"description": "x", "qty": 1, "rate": 15.0}],
    )
    w = ReceiveChecksScreen(ap_conn=db._conn, bank_db=db)
    combo = w._customer_filter
    labels = [combo.itemText(i) for i in range(combo.count())]
    assert any("ShipCo > Berth1" in (lb or "") for lb in labels)
    _select_customer(w, j)
    t = w.findChild(QTableWidget, "receiveChecksTable")
    assert t is not None
    assert t.rowCount() == 1
    assert "INV-H" in (t.item(0, 2).text() or "")
    spin = t.cellWidget(0, 5)
    assert isinstance(spin, QDoubleSpinBox)
    assert spin.maximum() == pytest.approx(15.0)


def test_receive_checks_totals_update_when_checked(
    qapp: QApplication, db: BankDatabase
) -> None:
    cid = business.add_customer(db._conn, "PayCo2")
    business.create_invoice(
        db._conn,
        cid,
        "INV-R2",
        "2024-06-01",
        lines=[{"description": "Work", "qty": 1, "rate": 50.0}],
    )
    w = ReceiveChecksScreen(ap_conn=db._conn, bank_db=db)
    t = w.findChild(QTableWidget, "receiveChecksTable")
    assert t is not None
    _select_customer(w, cid)
    cb = t.cellWidget(0, 0)
    spin = t.cellWidget(0, 5)
    assert isinstance(cb, QCheckBox)
    assert isinstance(spin, QDoubleSpinBox)
    cb.setChecked(True)
    spin.setValue(25.0)
    assert "25" in w._lbl_total_selected.text().replace(",", "")
    assert "25" in w._lbl_total_payment.text().replace(",", "")
    assert "25" in w._lbl_applied.text().replace(",", "")


def test_receive_payments_auto_apply_fifo(qapp: QApplication, db: BankDatabase) -> None:
    cid = business.add_customer(db._conn, "FifoCo")
    business.create_invoice(
        db._conn,
        cid,
        "INV-A",
        "2024-01-01",
        lines=[{"description": "a", "qty": 1, "rate": 40.0}],
    )
    business.create_invoice(
        db._conn,
        cid,
        "INV-B",
        "2024-02-01",
        lines=[{"description": "b", "qty": 1, "rate": 30.0}],
    )
    w = ReceiveChecksScreen(ap_conn=db._conn, bank_db=db)
    t = w.findChild(QTableWidget, "receiveChecksTable")
    assert t is not None
    _select_customer(w, cid)
    assert t.rowCount() == 2
    w._btn_auto_apply.setChecked(True)
    w._pay_amount.setValue(50.0)
    qapp.processEvents()
    first = t.cellWidget(0, 5)
    second = t.cellWidget(1, 5)
    assert isinstance(first, QDoubleSpinBox)
    assert isinstance(second, QDoubleSpinBox)
    assert first.value() == pytest.approx(40.0)
    assert second.value() == pytest.approx(10.0)
    assert t.cellWidget(0, 0).isChecked()
    assert t.cellWidget(1, 0).isChecked()


def test_receive_checks_apply_credits_button_present(qapp: QApplication) -> None:
    w = ReceiveChecksScreen()
    texts = [b.text() for b in w.findChildren(QPushButton)]
    assert "Discounts And Credits" in texts


def test_list_open_invoices_for_receive_payments(db: BankDatabase) -> None:
    cid = business.add_customer(db._conn, "ListCo")
    business.create_invoice(
        db._conn,
        cid,
        "INV-L",
        "2024-07-01",
        lines=[{"description": "x", "qty": 1, "rate": 10.0}],
    )
    rows = business.list_open_invoices_for_receive_payments(db._conn)
    assert len(rows) == 1
    assert rows[0]["customer_name"] == "ListCo"
    assert int(rows[0]["invoice_id"]) >= 1


def test_receive_payment_post_reduces_balance_to_undeposited(
    qapp: QApplication, db: BankDatabase
) -> None:
    aid = db.add_bank_account("Checking")
    cid = business.add_customer(db._conn, "PostCo")
    inv_id = business.create_invoice(
        db._conn,
        cid,
        "INV-P",
        "2024-08-01",
        lines=[{"description": "Work", "qty": 1, "rate": 40.0}],
    )
    w = ReceiveChecksScreen(ap_conn=db._conn, bank_db=db)
    t = w.findChild(QTableWidget, "receiveChecksTable")
    assert t is not None
    _select_customer(w, cid)
    assert t.rowCount() == 1
    cb = t.cellWidget(0, 0)
    spin = t.cellWidget(0, 5)
    assert isinstance(cb, QCheckBox)
    assert isinstance(spin, QDoubleSpinBox)
    cb.setChecked(True)
    spin.setValue(40.0)
    with patch("desktop_app.receive_checks_screen.message_box_information_ok"):
        w._on_post_payment()
    row = db._conn.execute(
        "SELECT balance_due, status FROM invoices WHERE id = ?", (inv_id,)
    ).fetchone()
    assert float(row["balance_due"]) == pytest.approx(0.0)
    pid = int(
        db._conn.execute("SELECT id FROM ar_payments ORDER BY id DESC LIMIT 1").fetchone()["id"]
    )
    pay = db._conn.execute(
        "SELECT bank_account_id, amount FROM ar_payments WHERE id = ?", (pid,)
    ).fetchone()
    assert pay["bank_account_id"] is None
    assert float(pay["amount"]) == pytest.approx(40.0)
    bank_n = db._conn.execute(
        "SELECT COUNT(*) AS c FROM bank_transactions WHERE bank_account_id = ?",
        (aid,),
    ).fetchone()["c"]
    assert int(bank_n) == 0
    undeposited = business.list_undeposited_ar_payments(db._conn)
    assert any(int(r["id"]) == pid for r in undeposited)
    assert w._btn_export_ar_pdf.isEnabled()
    assert w._btn_print_ar.isEnabled()
    assert w._last_ar_payment_ids[-1] == pid
    assert t.rowCount() == 0


def test_receive_payment_post_emits_ar_payment_posted_with_invoice_ids(
    qapp: QApplication, db: BankDatabase
) -> None:
    """``arPaymentPosted`` carries the invoice ids that just received an allocation.

    Other screens (Manual Invoice) wire to this signal to refresh the PAID badge /
    balance for an invoice they currently have open without polling.
    """
    db.add_bank_account("Checking")
    cid = business.add_customer(db._conn, "EmitCo")
    inv_id = business.create_invoice(
        db._conn,
        cid,
        "INV-EMIT",
        "2024-08-01",
        lines=[{"description": "Work", "qty": 1, "rate": 25.0}],
    )
    w = ReceiveChecksScreen(ap_conn=db._conn, bank_db=db)
    received: list[list[int]] = []
    w.arPaymentPosted.connect(lambda ids: received.append(list(ids)))
    t = w.findChild(QTableWidget, "receiveChecksTable")
    assert t is not None
    _select_customer(w, cid)
    cb = t.cellWidget(0, 0)
    spin = t.cellWidget(0, 5)
    assert isinstance(cb, QCheckBox)
    assert isinstance(spin, QDoubleSpinBox)
    cb.setChecked(True)
    spin.setValue(25.0)
    with patch("desktop_app.receive_checks_screen.message_box_information_ok"):
        w._on_post_payment()
    assert received, "arPaymentPosted should fire after a successful post"
    assert inv_id in received[-1]


def test_receive_payments_save_new_clears_form(qapp: QApplication, db: BankDatabase) -> None:
    cid = business.add_customer(db._conn, "ClearCo")
    business.create_invoice(
        db._conn,
        cid,
        "INV-C",
        "2024-08-01",
        lines=[{"description": "Work", "qty": 1, "rate": 12.0}],
    )
    w = ReceiveChecksScreen(ap_conn=db._conn, bank_db=db)
    _select_customer(w, cid)
    w._pay_amount.setValue(12.0)
    w._check_num.setText("1001")
    w._memo_edit.setText("deposit later")
    qapp.processEvents()
    t = w.findChild(QTableWidget, "receiveChecksTable")
    assert t is not None
    assert t.rowCount() == 1
    with patch("desktop_app.receive_checks_screen.message_box_information_ok"):
        w._persist_payment(reset=True)
    assert w._customer_filter.currentIndex() == 0
    assert w._pay_amount.value() == pytest.approx(0.0)
    assert w._check_num.text() == ""
    assert w._memo_edit.text() == ""
    assert t.rowCount() == 0
    rows = business.list_undeposited_ar_payments(db._conn)
    assert len(rows) == 1
    assert (rows[0]["reference"] or "") == "1001"
    assert (rows[0]["memo"] or "") == "deposit later"


def test_list_undeposited_ar_payments_skips_banked(db: BankDatabase) -> None:
    cid = business.add_customer(db._conn, "BankedCo")
    iid = business.create_invoice(
        db._conn,
        cid,
        "INV-U",
        "2024-01-01",
        lines=[{"description": "x", "qty": 1, "rate": 10.0}],
    )
    iid2 = business.create_invoice(
        db._conn,
        cid,
        "INV-B",
        "2024-01-02",
        lines=[{"description": "y", "qty": 1, "rate": 8.0}],
    )
    aid = db.add_bank_account("Checking")
    pid_open = business.record_ar_payment(
        db._conn, cid, "2024-01-10", 10.0, [(iid, 10.0)], bank_account_id=None
    )
    business.record_ar_payment(
        db._conn, cid, "2024-01-11", 8.0, [(iid2, 8.0)], bank_account_id=aid
    )
    rows = business.list_undeposited_ar_payments(db._conn)
    ids = [int(r["id"]) for r in rows]
    assert pid_open in ids
    assert len(ids) == 1
