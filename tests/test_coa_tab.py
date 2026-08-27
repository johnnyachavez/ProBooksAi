"""Chart of Accounts — QB Pro list, search, indent, double-click to register."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
)

from desktop_app.coa_tab import (
    COATab,
    _COL_NAME,
    _COL_TYPE,
    is_bank_like_coa,
    ordered_coa_rows,
    qb_coa_type_label,
)
from desktop_app.use_register_dialog import UseRegisterDialog
from desktop_app.register_tab import RegisterTab, _register_number_type_tag
from probooksai.bank_import import BankDatabase
from probooksai.coa_db import COADatabase
from probooksai.extensions_schema import apply_extensions
from probooksai.gl import GLDatabase

_FORBIDDEN_QB = (
    "CHASE BANK",
    "WELLS FARGO",
    "TRUCK #1010",
    "AR TRUCKING",
    "71,419.40",
    "BANK WELLS FARGO CLOSED ACCOUNT",
)


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def db(tmp_path: Path) -> BankDatabase:
    b = BankDatabase(db_path=str(tmp_path / "coa_t.db"))
    apply_extensions(b._conn)
    yield b
    b.close()


def test_qb_coa_type_label_bank_and_ar() -> None:
    class _R(dict):
        def __getitem__(self, k):
            return dict.get(self, k, "")

        def keys(self):
            return dict.keys(self)

    bank = _R(
        account_name="Cash – Checking",
        account_type="asset",
        sub_type="Current Asset",
    )
    ar = _R(
        account_name="Accounts Receivable",
        account_type="asset",
        sub_type="Current Asset",
    )
    assert qb_coa_type_label(bank) == "Bank"
    assert is_bank_like_coa(bank)
    assert qb_coa_type_label(ar) == "Accounts Receivable"
    assert not is_bank_like_coa(ar)


def test_ordered_coa_rows_indents_children(db: BankDatabase) -> None:
    coa = COADatabase(db._conn)
    parent = coa.add_account("1500", "Vehicles", "fixed_asset")
    coa.add_account("1501", "Trailer A", "fixed_asset", parent_id=parent)
    packed = ordered_coa_rows(coa.list_accounts())
    names = [(r["account_name"], d) for r, d in packed]
    assert ("Vehicles", 0) in names
    assert ("Trailer A", 1) in names
    vi = names.index(("Vehicles", 0))
    ti = names.index(("Trailer A", 1))
    assert ti == vi + 1


def test_coa_tab_qb_chrome(qapp: QApplication, db: BankDatabase) -> None:
    coa = COADatabase(db._conn)
    coa.add_account("1000", "Cash – Checking", "bank")
    coa.add_account("1100", "Accounts Receivable", "current_asset")
    w = COATab(coa, gl_db=GLDatabase(db._conn))
    labels = [lb.text() for lb in w.findChildren(QLabel)]
    assert "Look for account name or number" in labels
    btns = [b.text() for b in w.findChildren(QPushButton)]
    assert "Search" in btns
    assert "Reset" in btns
    tbl = w.findChild(QTableWidget, "chartOfAccountsTable")
    assert tbl is not None
    headers = [tbl.horizontalHeaderItem(i).text() for i in range(tbl.columnCount())]
    assert "NAME" in headers
    assert "TYPE" in headers
    assert "BALANCE TOTAL" in headers
    assert "ATTACH" in headers
    search = w.findChild(QLineEdit, "chartOfAccountsSearch")
    assert search is not None
    assert tbl.rowCount() >= 2


def test_coa_tab_search_filters(qapp: QApplication, db: BankDatabase) -> None:
    coa = COADatabase(db._conn)
    coa.add_account("1000", "Cash – Checking", "bank")
    coa.add_account("4000", "Sales Revenue", "income")
    w = COATab(coa)
    w._search.setText("Sales")
    w._on_search()
    assert w._table.rowCount() == 1
    assert "Sales" in w._table.item(0, _COL_NAME).text()
    w._on_reset_search()
    assert w._table.rowCount() == 2


def test_coa_tab_double_click_emits_register(qapp: QApplication, db: BankDatabase) -> None:
    coa = COADatabase(db._conn)
    aid = coa.add_account("1000", "Cash – Checking", "bank")
    w = COATab(coa)
    seen: list[int] = []
    w.openRegisterRequested.connect(seen.append)
    w._table.selectRow(0)
    w._on_row_double_clicked()
    assert seen == [aid]


def test_capture_script_has_coa_and_register_tabs() -> None:
    text = Path("scripts/capture_ui_screenshot.py").read_text(encoding="utf-8")
    assert "--tab coa" in text
    assert "--tab register" in text
    assert "--tab use-register" in text


def test_coa_tab_does_not_copy_real_qb_names() -> None:
    roots = [
        Path("desktop_app/coa_tab.py"),
        Path("desktop_app/use_register_dialog.py"),
        Path("desktop_app/register_tab.py"),
        Path("desktop_app/main.py"),
        Path("desktop_app/check_screen.py"),
        Path("scripts/capture_ui_screenshot.py"),
    ]
    for path in roots:
        text = path.read_text(encoding="utf-8")
        for name in _FORBIDDEN_QB:
            assert name not in text, f"{name!r} must not appear in {path}"


def test_use_register_dialog_lists_accounts(qapp: QApplication, db: BankDatabase) -> None:
    db.add_bank_account("Checking")
    dlg = UseRegisterDialog(db)
    assert dlg.windowTitle() == "Use Register"
    assert dlg._account.count() >= 1
    assert dlg.selected_bank_account_id() is not None
    labels = [lb.text() for lb in dlg.findChildren(QLabel)]
    assert "Select Account" in labels


def test_register_headers_are_qb_checkbook(qapp: QApplication, db: BankDatabase) -> None:
    coa = COADatabase(db._conn)
    tab = RegisterTab(db, coa, None)
    headers = [
        tab._table.horizontalHeaderItem(i).text()
        for i in range(tab._table.columnCount() - 1)
    ]
    assert headers[0] == "DATE"
    assert headers[1] == "NUMBER / TYPE"
    assert headers[2] == "PAYEE / ACCOUNT"
    assert headers[3] == "MEMO"
    assert headers[4] == "PAYMENT"
    assert headers[5] == "✓"
    assert headers[6] == "DEPOSIT"
    assert "Go to..." in [b.text() for b in tab.findChildren(QPushButton)]
    assert tab._chk_one_line.isChecked() is False
    assert tab._sort_combo.currentText() == "Date, Type, Number/Ref"


def test_register_shows_billpmt_dep_chk(qapp: QApplication, db: BankDatabase) -> None:
    coa = COADatabase(db._conn)
    aid = db.add_bank_account("Checking")
    db.insert_manual_transaction(
        aid, "2026-08-05", -79.00, description="Office Supplies Co",
        ref_number="1001", memo="BILLPMT",
    )
    db.insert_manual_transaction(
        aid, "2026-08-06", 50.00, description="Deposit",
        ref_number="DEP", memo="DEP",
    )
    db.insert_manual_transaction(
        aid, "2026-08-07", -25.00, description="Fuel Vendor",
        ref_number="1002", memo="CHK",
    )
    tab = RegisterTab(db, coa, None)
    tab.select_bank_account(aid)
    tags = []
    for r in range(tab._table.rowCount()):
        it = tab._table.item(r, 1)
        if it is None:
            continue
        lower = it.data(Qt.ItemDataRole.UserRole + 54)
        text = (it.text() or "") + " " + str(lower or "")
        if "BILLPMT" in text:
            tags.append("BILLPMT")
        if "\nDEP" in text or text.endswith("DEP"):
            tags.append("DEP")
        if "CHK" in text:
            tags.append("CHK")
    assert "BILLPMT" in tags
    assert "DEP" in tags
    assert "CHK" in tags
    assert _register_number_type_tag({"amount": -25, "ref_number": "1002", "memo": "CHK"}) == "CHK"


def test_coa_double_click_opens_register_in_main(qapp: QApplication, tmp_path: Path) -> None:
    from desktop_app.main import MainWindow

    db_path = tmp_path / "coa_main.db"
    BankDatabase(str(db_path)).close()
    w = MainWindow(db_path=str(db_path))
    try:
        conn = w._bank_db._conn
        coa = w._coa_db
        aid = coa.add_account("1099", "Operating Checking", "bank")
        w._coa_tab._refresh()
        w._on_coa_open_register(aid)
        assert w._tabs.currentWidget() is w._register_tab
        assert w._register_tab._current_account_id is not None
    finally:
        w.close()
