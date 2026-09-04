"""AP journal-entry wiring: Enter Bills / Pay Bills post to the GL exactly once.

The double-counting hazard these tests pin down: a bill debits the expense when it is
entered, so the bank line that later clears the payment must not debit the expense a
second time.
"""

from __future__ import annotations

import sqlite3

import pytest

from probooksai import business
from probooksai.bank_import import BankDatabase
from probooksai.coa_db import COADatabase
from probooksai.extensions_schema import apply_extensions
from probooksai.financial_reports import income_statement
from probooksai.gl import GLDatabase


AP = "2000 – Accounts Payable"
RENT = "6100 – Rent Expense"
FUEL = "6310 – Vehicle Expense"
MISC = "6900 – Miscellaneous Expense"
CHECKING = "1000 – Cash – Checking"


@pytest.fixture
def db(tmp_path):
    b = BankDatabase(db_path=str(tmp_path / "ap.db"))
    apply_extensions(b._conn)
    coa = COADatabase(b._conn)
    coa.seed_from_workbook()
    GLDatabase(b._conn)
    yield b
    b.close()


@pytest.fixture
def gl(db):
    return GLDatabase(db._conn)


@pytest.fixture
def bank_account(db):
    return db.add_bank_account("Operating", gl_display_account=CHECKING)


def _lines(conn: sqlite3.Connection, source: str) -> list[dict]:
    entry = conn.execute(
        "SELECT id FROM journal_entries WHERE source = ?", (source,)
    ).fetchone()
    if entry is None:
        return []
    rows = conn.execute(
        "SELECT account, debit, credit FROM journal_entry_lines "
        "WHERE entry_id = ? ORDER BY id",
        (entry["id"],),
    ).fetchall()
    return [dict(r) for r in rows]


def _net_by_account(conn: sqlite3.Connection) -> dict[str, float]:
    rows = conn.execute(
        "SELECT account, SUM(debit) - SUM(credit) AS net "
        "FROM journal_entry_lines GROUP BY account"
    ).fetchall()
    return {r["account"]: round(r["net"], 2) for r in rows}


def _expense_line(line: dict, amount: float) -> dict:
    return dict(line_date="2025-01-05", amount=amount, **line)


# ---------------------------------------------------------------------------
# Enter Bills
# ---------------------------------------------------------------------------

def test_create_bill_posts_expense_and_ap(db):
    vid = business.add_vendor(db._conn, "Landlord LLC")
    bid = business.create_bill(
        db._conn, vid, "2025-01-05", 0.0,
        vendor_invoice_number="R-1",
        expense_lines=[
            {"line_date": "2025-01-05", "coa_account": RENT, "amount": 1200.0},
        ],
    )
    lines = _lines(db._conn, f"ap_bill:{bid}")
    assert len(lines) == 2
    dr = next(ln for ln in lines if ln["debit"] > 0)
    cr = next(ln for ln in lines if ln["credit"] > 0)
    assert dr["account"] == RENT
    assert dr["debit"] == pytest.approx(1200.0)
    assert cr["account"] == AP
    assert cr["credit"] == pytest.approx(1200.0)


def test_bill_lines_group_by_expense_account(db):
    vid = business.add_vendor(db._conn, "Multi Co")
    bid = business.create_bill(
        db._conn, vid, "2025-02-01", 0.0,
        expense_lines=[
            {"coa_account": RENT, "amount": 500.0},
            {"coa_account": FUEL, "amount": 100.0},
            {"coa_account": RENT, "amount": 250.0},
        ],
    )
    lines = _lines(db._conn, f"ap_bill:{bid}")
    assert len(lines) == 3
    by_account = {ln["account"]: ln for ln in lines}
    assert by_account[RENT]["debit"] == pytest.approx(750.0)
    assert by_account[FUEL]["debit"] == pytest.approx(100.0)
    assert by_account[AP]["credit"] == pytest.approx(850.0)


def test_legacy_account_text_in_ticket_ref_still_resolves(db):
    """Enter Bills stored the account label in ``ticket_ref`` before the AP posting work."""
    vid = business.add_vendor(db._conn, "Legacy Co")
    bid = business.create_bill(
        db._conn, vid, "2025-02-02", 0.0,
        expense_lines=[{"ticket_ref": "6100 Rent Expense", "amount": 300.0}],
    )
    lines = _lines(db._conn, f"ap_bill:{bid}")
    assert {ln["account"] for ln in lines} == {RENT, AP}


@pytest.mark.parametrize(
    "text", ["6100", "6100 Rent Expense", "6100 – Rent Expense", "Rent Expense"]
)
def test_resolve_bill_expense_account_label_accepts_account_spellings(db, text):
    label = business.resolve_bill_expense_account_label(db._conn, {"ticket_ref": text})
    assert label == RENT


def test_line_without_a_usable_account_falls_back_to_misc_expense(db):
    vid = business.add_vendor(db._conn, "Unknown Acct Co")
    bid = business.create_bill(
        db._conn, vid, "2025-02-03", 0.0,
        expense_lines=[{"ticket_ref": "not an account", "amount": 75.0}],
    )
    lines = _lines(db._conn, f"ap_bill:{bid}")
    assert {ln["account"] for ln in lines} == {MISC, AP}


def test_item_code_line_uses_the_item_coa_account(db):
    business.replace_invoice_item_codes(
        db._conn,
        [{"code": "FUEL", "description": "Diesel", "coa_account": FUEL}],
    )
    vid = business.add_vendor(db._conn, "Fuel Depot")
    bid = business.create_bill(
        db._conn, vid, "2025-02-04", 0.0,
        expense_lines=[{"ticket_ref": "FUEL", "amount": 420.0}],
    )
    lines = _lines(db._conn, f"ap_bill:{bid}")
    assert {ln["account"] for ln in lines} == {FUEL, AP}


def test_header_only_bill_balances_against_misc_expense(db):
    vid = business.add_vendor(db._conn, "Header Only Co")
    bid = business.create_bill(db._conn, vid, "2025-02-05", 640.0)
    lines = _lines(db._conn, f"ap_bill:{bid}")
    assert len(lines) == 2
    assert sum(ln["debit"] for ln in lines) == pytest.approx(640.0)
    by_account = {ln["account"]: ln for ln in lines}
    assert by_account[MISC]["debit"] == pytest.approx(640.0)
    assert by_account[AP]["credit"] == pytest.approx(640.0)


def test_zero_value_bill_posts_nothing(db):
    vid = business.add_vendor(db._conn, "Zero Co")
    bid = business.create_bill(db._conn, vid, "2025-02-06", 0.0)
    assert _lines(db._conn, f"ap_bill:{bid}") == []


def test_update_bill_replaces_its_entry_instead_of_stacking(db):
    vid = business.add_vendor(db._conn, "Edit Co")
    bid = business.create_bill(
        db._conn, vid, "2025-03-01", 0.0,
        expense_lines=[{"coa_account": RENT, "amount": 200.0}],
    )
    business.update_bill(
        db._conn, bid, vid, "2025-03-01", 0.0,
        expense_lines=[{"coa_account": RENT, "amount": 325.0}],
    )
    count = db._conn.execute(
        "SELECT COUNT(*) AS n FROM journal_entries WHERE source = ?", (f"ap_bill:{bid}",)
    ).fetchone()["n"]
    assert count == 1
    assert _net_by_account(db._conn)[RENT] == pytest.approx(325.0)


# ---------------------------------------------------------------------------
# Pay Bills
# ---------------------------------------------------------------------------

def test_ap_payment_posts_ap_and_cash_only(db, bank_account):
    vid = business.add_vendor(db._conn, "Payee Co")
    bid = business.create_bill(
        db._conn, vid, "2025-04-01", 0.0,
        expense_lines=[{"coa_account": RENT, "amount": 900.0}],
    )
    pid = business.record_ap_payment(
        db._conn, vid, "2025-04-10", 900.0, [(bid, 900.0)],
        bank_account_id=bank_account, reference="1001",
    )
    lines = _lines(db._conn, f"ap_payment:{pid}")
    assert len(lines) == 2
    by_account = {ln["account"]: ln for ln in lines}
    assert by_account[AP]["debit"] == pytest.approx(900.0)
    assert by_account[CHECKING]["credit"] == pytest.approx(900.0)
    assert RENT not in by_account


def test_bill_and_payment_leave_ap_flat_and_expense_once(db, bank_account):
    vid = business.add_vendor(db._conn, "Cycle Co")
    bid = business.create_bill(
        db._conn, vid, "2025-04-01", 0.0,
        expense_lines=[{"coa_account": RENT, "amount": 900.0}],
    )
    business.record_ap_payment(
        db._conn, vid, "2025-04-10", 900.0, [(bid, 900.0)],
        bank_account_id=bank_account,
    )
    net = _net_by_account(db._conn)
    assert net[RENT] == pytest.approx(900.0)
    assert net[AP] == pytest.approx(0.0)
    assert net[CHECKING] == pytest.approx(-900.0)


def test_ap_payment_without_a_bank_account_credits_default_cash(db):
    vid = business.add_vendor(db._conn, "Cash Co")
    bid = business.create_bill(db._conn, vid, "2025-04-01", 100.0)
    pid = business.record_ap_payment(
        db._conn, vid, "2025-04-02", 100.0, [(bid, 100.0)], bank_account_id=None
    )
    accounts = {ln["account"] for ln in _lines(db._conn, f"ap_payment:{pid}")}
    assert accounts == {AP, CHECKING}


# ---------------------------------------------------------------------------
# Bank import must not double-count what AP already booked
# ---------------------------------------------------------------------------

def _paid_bill(db, bank_account, *, amount=900.0):
    vid = business.add_vendor(db._conn, "Bank Match Co")
    bid = business.create_bill(
        db._conn, vid, "2025-05-01", 0.0,
        expense_lines=[{"coa_account": RENT, "amount": amount}],
    )
    pid = business.record_ap_payment(
        db._conn, vid, "2025-05-05", amount, [(bid, amount)],
        bank_account_id=bank_account, reference="2002",
    )
    return bid, pid


def test_matching_a_bank_line_to_a_payment_attaches_the_existing_entry(
    db, gl, bank_account
):
    _bid, pid = _paid_bill(db, bank_account)
    tid = db.insert_manual_transaction(
        bank_account, "2025-05-06", -900.0, description="CHECK 2002"
    )
    business.link_bank_transaction(db._conn, tid, "ap_payment", pid)

    txn = dict(db.get_transaction(tid))
    assert txn["is_posted"] == 1
    assert txn["journal_entry_id"] == business.ap_payment_journal_entry_id(db._conn, pid)
    net = _net_by_account(db._conn)
    assert net[RENT] == pytest.approx(900.0)
    assert net[CHECKING] == pytest.approx(-900.0)


def test_posting_a_matched_bank_line_does_not_create_a_second_entry(
    db, gl, bank_account
):
    _bid, pid = _paid_bill(db, bank_account)
    tid = db.insert_manual_transaction(
        bank_account, "2025-05-06", -900.0, description="CHECK 2002", coa_account=RENT
    )
    business.link_bank_transaction(db._conn, tid, "ap_payment", pid)
    before = db._conn.execute("SELECT COUNT(*) AS n FROM journal_entries").fetchone()["n"]

    entry_id = gl.post_transaction(tid, CHECKING, RENT)

    after = db._conn.execute("SELECT COUNT(*) AS n FROM journal_entries").fetchone()["n"]
    assert after == before
    assert entry_id == business.ap_payment_journal_entry_id(db._conn, pid)
    net = _net_by_account(db._conn)
    assert net[RENT] == pytest.approx(900.0)
    assert net[CHECKING] == pytest.approx(-900.0)


def test_matching_after_posting_removes_the_stand_in_bank_entry(db, gl, bank_account):
    """The register may post a bank line before anyone notices it is a bill payment."""
    _bid, pid = _paid_bill(db, bank_account)
    tid = db.insert_manual_transaction(
        bank_account, "2025-05-06", -900.0, description="CHECK 2002", coa_account=RENT
    )
    stand_in = gl.post_transaction(tid, CHECKING, RENT)
    assert _net_by_account(db._conn)[RENT] == pytest.approx(1800.0)  # counted twice

    business.link_bank_transaction(db._conn, tid, "ap_payment", pid)

    assert db._conn.execute(
        "SELECT id FROM journal_entries WHERE id = ?", (stand_in,)
    ).fetchone() is None
    net = _net_by_account(db._conn)
    assert net[RENT] == pytest.approx(900.0)
    assert net[CHECKING] == pytest.approx(-900.0)


def test_matching_does_not_discard_a_hand_written_entry(db, gl, bank_account):
    _bid, pid = _paid_bill(db, bank_account)
    tid = db.insert_manual_transaction(
        bank_account, "2025-05-06", -900.0, description="CHECK 2002"
    )
    manual = gl.create_journal_entry(
        "2025-05-06",
        [
            {"account": RENT, "debit": 900.0, "credit": 0.0},
            {"account": CHECKING, "debit": 0.0, "credit": 900.0},
        ],
        source="manual",
    )
    db._conn.execute(
        "UPDATE bank_transactions SET is_posted = 1, journal_entry_id = ? WHERE id = ?",
        (manual, tid),
    )
    db._conn.commit()

    business.link_bank_transaction(db._conn, tid, "ap_payment", pid)

    assert db._conn.execute(
        "SELECT id FROM journal_entries WHERE id = ?", (manual,)
    ).fetchone() is not None
    assert dict(db.get_transaction(tid))["journal_entry_id"] == manual


def test_unlinking_makes_the_bank_line_postable_again(db, gl, bank_account):
    _bid, pid = _paid_bill(db, bank_account)
    tid = db.insert_manual_transaction(
        bank_account, "2025-05-06", -900.0, description="CHECK 2002", coa_account=RENT
    )
    business.link_bank_transaction(db._conn, tid, "ap_payment", pid)
    assert dict(db.get_transaction(tid))["is_posted"] == 1

    business.unlink_bank_transaction(db._conn, tid)

    txn = dict(db.get_transaction(tid))
    assert txn["is_posted"] == 0
    assert txn["journal_entry_id"] is None
    gl.post_transaction(tid, CHECKING, RENT)
    assert dict(db.get_transaction(tid))["is_posted"] == 1


def test_bulk_post_attaches_matched_lines_without_a_category(db, gl, bank_account):
    _bid, pid = _paid_bill(db, bank_account)
    tid = db.insert_manual_transaction(
        bank_account, "2025-05-06", -900.0, description="CHECK 2002"
    )
    business.link_bank_transaction(db._conn, tid, "ap_payment", pid)

    result = gl.post_transactions_bulk([tid], CHECKING, {})

    assert result["skipped"] == []
    assert result["errors"] == []
    assert result["posted"] == [
        (tid, business.ap_payment_journal_entry_id(db._conn, pid))
    ]


def test_matching_a_bank_line_to_an_open_bill_attaches_the_bill_entry(db, bank_account):
    vid = business.add_vendor(db._conn, "Direct Pay Co")
    bid = business.create_bill(
        db._conn, vid, "2025-06-01", 0.0,
        expense_lines=[{"coa_account": FUEL, "amount": 60.0}],
    )
    tid = db.insert_manual_transaction(bank_account, "2025-06-02", -60.0)
    business.link_bank_transaction(db._conn, tid, "ap_bill", bid)

    txn = dict(db.get_transaction(tid))
    assert txn["is_posted"] == 1
    assert txn["journal_entry_id"] == business.ap_bill_journal_entry_id(db._conn, bid)


def test_unmatched_bank_expense_still_posts_normally(db, gl, bank_account):
    tid = db.insert_manual_transaction(
        bank_account, "2025-06-03", -40.0, description="Gas station", coa_account=FUEL
    )
    gl.post_transaction(tid, CHECKING, FUEL)
    net = _net_by_account(db._conn)
    assert net[FUEL] == pytest.approx(40.0)
    assert net[CHECKING] == pytest.approx(-40.0)


# ---------------------------------------------------------------------------
# Backfill + reporting
# ---------------------------------------------------------------------------

def test_backfill_posts_only_what_is_missing(db, bank_account):
    vid = business.add_vendor(db._conn, "Backfill Co")
    b1 = business.create_bill(
        db._conn, vid, "2025-07-01", 0.0,
        expense_lines=[{"coa_account": RENT, "amount": 100.0}],
    )
    b2 = business.create_bill(
        db._conn, vid, "2025-07-02", 0.0,
        expense_lines=[{"coa_account": RENT, "amount": 200.0}],
    )
    pid = business.record_ap_payment(
        db._conn, vid, "2025-07-03", 100.0, [(b1, 100.0)],
        bank_account_id=bank_account,
    )
    for source in (f"ap_bill:{b2}", f"ap_payment:{pid}"):
        eid = business.journal_entry_id_for_source(db._conn, source)
        db._conn.execute("DELETE FROM journal_entry_lines WHERE entry_id = ?", (eid,))
        db._conn.execute("DELETE FROM journal_entries WHERE id = ?", (eid,))
    db._conn.commit()

    assert business.backfill_ap_journals(db._conn) == 2
    assert business.backfill_ap_journals(db._conn) == 0
    assert business.ap_bill_journal_entry_id(db._conn, b1) is not None
    assert business.ap_bill_journal_entry_id(db._conn, b2) is not None
    assert business.ap_payment_journal_entry_id(db._conn, pid) is not None


def test_backfill_relinks_bank_lines_matched_before_ap_posted(db, bank_account):
    vid = business.add_vendor(db._conn, "Relink Co")
    bid = business.create_bill(
        db._conn, vid, "2025-07-10", 0.0,
        expense_lines=[{"coa_account": RENT, "amount": 55.0}],
    )
    pid = business.record_ap_payment(
        db._conn, vid, "2025-07-11", 55.0, [(bid, 55.0)],
        bank_account_id=bank_account,
    )
    tid = db.insert_manual_transaction(bank_account, "2025-07-11", -55.0)
    business.link_bank_transaction(db._conn, tid, "ap_payment", pid)

    old_entry = business.ap_payment_journal_entry_id(db._conn, pid)
    db._conn.execute("DELETE FROM journal_entry_lines WHERE entry_id = ?", (old_entry,))
    db._conn.execute("DELETE FROM journal_entries WHERE id = ?", (old_entry,))
    db._conn.commit()

    business.backfill_ap_journals(db._conn)

    new_entry = business.ap_payment_journal_entry_id(db._conn, pid)
    assert new_entry is not None
    assert dict(db.get_transaction(tid))["journal_entry_id"] == new_entry


def test_income_statement_counts_the_bill_expense_once(db, gl, bank_account):
    vid = business.add_vendor(db._conn, "P&L Co")
    bid = business.create_bill(
        db._conn, vid, "2025-08-01", 0.0,
        expense_lines=[{"coa_account": RENT, "amount": 1500.0}],
    )
    pid = business.record_ap_payment(
        db._conn, vid, "2025-08-15", 1500.0, [(bid, 1500.0)],
        bank_account_id=bank_account, reference="3003",
    )
    tid = db.insert_manual_transaction(
        bank_account, "2025-08-16", -1500.0, description="CHECK 3003", coa_account=RENT
    )
    business.link_bank_transaction(db._conn, tid, "ap_payment", pid)
    gl.post_transactions_bulk([tid], CHECKING, {tid: RENT})

    pl = income_statement(db._conn, "2025-01-01", "2025-12-31")
    assert pl["expenses"] == pytest.approx(1500.0)
