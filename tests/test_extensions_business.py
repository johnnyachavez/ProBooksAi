"""Extension schema, rules on import, and business (AR) helpers."""

from __future__ import annotations

import csv
import os
import sqlite3
import subprocess
import sys
from unittest.mock import patch

import pytest

from probooksai.bank_import import BankDatabase, SCHEMA_VERSION
from probooksai.extensions_schema import apply_extensions, EXTENSION_SCHEMA_VERSION
from probooksai import business, rules_engine


@pytest.fixture
def db(tmp_path):
    b = BankDatabase(db_path=str(tmp_path / "t.db"))
    apply_extensions(b._conn)
    yield b
    b.close()


def test_bank_schema_version_includes_gl_profile(db):
    assert SCHEMA_VERSION >= 5
    db._conn.execute(
        "SELECT gl_display_account, imp_csv_date_col FROM bank_accounts LIMIT 0"
    )


def test_list_open_bills_for_pay_bills(db):
    assert business.list_open_bills_for_pay_bills(db._conn) == []
    vid = business.add_vendor(db._conn, "Vendor X")
    business.create_bill(db._conn, vid, "2024-05-01", 40.0, vendor_invoice_number="VX-1")
    rows = business.list_open_bills_for_pay_bills(db._conn)
    assert len(rows) == 1
    assert dict(rows[0])["vendor_name"] == "Vendor X"
    assert int(dict(rows[0])["bill_id"]) >= 1


def test_list_invoice_ids_chronological_order(db) -> None:
    assert business.list_invoice_ids_chronological(db._conn) == []
    c1 = business.add_customer(db._conn, "A")
    c2 = business.add_customer(db._conn, "B")
    i2 = business.create_invoice(
        db._conn,
        c2,
        "2",
        "2024-02-01",
        lines=[{"description": "b", "qty": 1, "rate": 1.0}],
    )
    i1 = business.create_invoice(
        db._conn,
        c1,
        "1",
        "2024-01-01",
        lines=[{"description": "a", "qty": 1, "rate": 1.0}],
    )
    # ASC order: Jan (i1) before Feb (i2) so ◄/► nav goes oldest → newest
    assert business.list_invoice_ids_chronological(db._conn) == [i1, i2]


def test_next_default_invoice_number_starts_at_13001(db) -> None:
    assert business.next_default_invoice_number(db._conn) == "13001"


def test_next_default_invoice_number_none_conn() -> None:
    assert business.next_default_invoice_number(None) == "13001"


def test_next_default_invoice_number_max_digits_plus_one(db) -> None:
    cid = business.add_customer(db._conn, "C")
    business.create_invoice(
        db._conn,
        cid,
        "13001",
        "2024-01-01",
        lines=[{"description": "x", "qty": 1, "rate": 0.0}],
    )
    assert business.next_default_invoice_number(db._conn) == "13002"
    business.create_invoice(
        db._conn,
        cid,
        "INV-9",
        "2024-01-02",
        lines=[{"description": "y", "qty": 1, "rate": 0.0}],
    )
    assert business.next_default_invoice_number(db._conn) == "13002"
    business.create_invoice(
        db._conn,
        cid,
        "13009",
        "2024-01-03",
        lines=[{"description": "z", "qty": 1, "rate": 0.0}],
    )
    assert business.next_default_invoice_number(db._conn) == "13010"


def test_extension_schema_applied(db):
    row = db._conn.execute(
        "SELECT version FROM extension_schema_version WHERE id = 1"
    ).fetchone()
    assert row["version"] == EXTENSION_SCHEMA_VERSION
    db._conn.execute("SELECT * FROM payroll_tax_items LIMIT 0")
    db._conn.execute("SELECT * FROM payroll_run_tax_lines LIMIT 0")
    db._conn.execute("SELECT * FROM categorization_rules LIMIT 0")


def test_suggest_coa_matches_respects_priority(db):
    rules_engine.add_rule(db._conn, "ALPHA", "1000 – A", priority=1)
    rules_engine.add_rule(db._conn, "BETA", "2000 – B", priority=10)
    rules_engine.add_rule(db._conn, "GAMMA", "3000 – C", priority=5)
    s = rules_engine.suggest_coa_matches(db._conn, "X BETA Y GAMMA Z ALPHA", limit=5)
    assert s[0] == "2000 – B"
    assert "1000 – A" in s and "3000 – C" in s


def test_rule_applied_on_import(db):
    aid = db.add_bank_account("Main")
    rules_engine.add_rule(db._conn, "COFFEE", "6100 – Test Expense", priority=5)
    csv = "Date,Desc,Amt\n2024-02-01,COFFEE SHOP,-3.00\n"
    db.import_csv(
        aid,
        csv,
        date_col="Date",
        amount_col="Amt",
        description_col="Desc",
        apply_categorization_rules=True,
    )
    rows = db.list_transactions(aid)
    assert len(rows) == 1
    assert "6100" in (rows[0]["coa_account"] or "")


def test_payroll_tax_lines_and_report(db):
    eid = business.add_employee(db._conn, "Pat")
    rid = business.create_payroll_run(
        db._conn,
        eid,
        "2024-01-01",
        "2024-01-31",
        "2024-01-31",
        2000.0,
        400.0,
    )
    items = business.list_payroll_tax_items(db._conn)
    assert len(items) >= 1
    tid = items[0]["id"]
    business.upsert_payroll_run_tax_line(db._conn, rid, tid, 100.0, 50.0, "")
    lines = business.list_payroll_run_tax_lines(db._conn, rid)
    assert len(lines) == 1
    assert lines[0]["employee_amount"] == pytest.approx(100.0)
    rep = business.payroll_tax_totals_by_range(db._conn, "2024-01-01", "2024-12-31")
    assert len(rep) == 1
    assert float(rep[0]["employee_total"]) == pytest.approx(100.0)
    assert float(rep[0]["employer_total"]) == pytest.approx(50.0)


def test_suggest_bank_match_and_unlink(db):
    cid = business.add_customer(db._conn, "Acme")
    inv_id = business.create_invoice(
        db._conn,
        cid,
        "I1",
        "2024-05-01",
        lines=[{"description": "Work", "qty": 1, "rate": 100.0}],
    )
    pid = business.record_ar_payment(
        db._conn,
        cid,
        "2024-06-01",
        100.0,
        [(inv_id, 100.0)],
    )
    aid = db.add_bank_account("Chk")
    bid = db.create_batch(aid)
    db.import_transactions(
        bid,
        aid,
        [
            {
                "txn_date": "2024-06-01",
                "description": "Deposit",
                "amount": 100.0,
                "ref_number": "",
            }
        ],
    )
    tid = db.list_transactions(aid)[0]["id"]
    sug = business.suggest_bank_match_candidates(db._conn, tid)
    assert any(s["link_type"] == "ar_payment" and s["link_id"] == pid for s in sug)
    business.link_bank_transaction(db._conn, tid, "ar_payment", pid)
    db.import_transactions(
        bid,
        aid,
        [
            {
                "txn_date": "2024-06-02",
                "description": "Another",
                "amount": 100.0,
                "ref_number": "",
            }
        ],
    )
    rows = db.list_transactions(aid)
    tid2 = rows[-1]["id"]
    sug2 = business.suggest_bank_match_candidates(db._conn, tid2)
    assert not any(
        s["link_type"] == "ar_payment" and s["link_id"] == pid for s in sug2
    )
    business.unlink_bank_transaction(db._conn, tid)
    assert business.get_bank_match(db._conn, tid) is None


def test_bank_match_link_for_navigation_none_when_unlinked(db):
    aid = db.add_bank_account("NavNone")
    bid = db.create_batch(aid)
    db.import_transactions(
        bid,
        aid,
        [
            {
                "txn_date": "2024-06-01",
                "description": "X",
                "amount": 10.0,
                "ref_number": "",
            }
        ],
    )
    tid = db.list_transactions(aid)[0]["id"]
    assert business.bank_match_link_for_navigation(db._conn, tid) is None


def test_bank_match_link_for_navigation_returns_type_and_id(db):
    cid = business.add_customer(db._conn, "NavCo")
    inv = business.create_invoice(
        db._conn,
        cid,
        "NAV-1",
        "2024-06-01",
        lines=[{"description": "Work", "qty": 1, "rate": 25.0}],
    )
    pid = business.record_ar_payment(
        db._conn,
        cid,
        "2024-06-02",
        25.0,
        [(inv, 25.0)],
    )
    aid = db.add_bank_account("NavChk")
    bid = db.create_batch(aid)
    db.import_transactions(
        bid,
        aid,
        [
            {
                "txn_date": "2024-06-02",
                "description": "Pay",
                "amount": 25.0,
                "ref_number": "",
            }
        ],
    )
    tid = db.list_transactions(aid)[0]["id"]
    business.link_bank_transaction(db._conn, tid, "ar_payment", pid)
    assert business.bank_match_link_for_navigation(db._conn, tid) == ("ar_payment", pid)


def test_bank_match_link_for_navigation_none_when_link_type_blank_or_whitespace(db):
    cid = business.add_customer(db._conn, "NavBlank")
    inv = business.create_invoice(
        db._conn,
        cid,
        "NB-1",
        "2024-06-01",
        lines=[{"description": "Work", "qty": 1, "rate": 10.0}],
    )
    pid = business.record_ar_payment(
        db._conn,
        cid,
        "2024-06-02",
        10.0,
        [(inv, 10.0)],
    )
    aid = db.add_bank_account("NavBlankChk")
    bid = db.create_batch(aid)
    db.import_transactions(
        bid,
        aid,
        [
            {
                "txn_date": "2024-06-02",
                "description": "Pay",
                "amount": 10.0,
                "ref_number": "",
            }
        ],
    )
    tid = db.list_transactions(aid)[0]["id"]
    business.link_bank_transaction(db._conn, tid, "ar_payment", pid)
    assert business.bank_match_link_for_navigation(db._conn, tid) == ("ar_payment", pid)
    db._conn.execute(
        "UPDATE bank_match_links SET link_type = '' WHERE bank_transaction_id = ?",
        (tid,),
    )
    db._conn.commit()
    assert business.bank_match_link_for_navigation(db._conn, tid) is None
    db._conn.execute(
        "UPDATE bank_match_links SET link_type = ? WHERE bank_transaction_id = ?",
        ("  \t  ", tid),
    )
    db._conn.commit()
    assert business.bank_match_link_for_navigation(db._conn, tid) is None


def test_bank_match_link_tuple_from_row_aligns_with_navigation(db):
    assert business.bank_match_link_tuple_from_row(None) is None
    cid = business.add_customer(db._conn, "TupleRow")
    inv = business.create_invoice(
        db._conn,
        cid,
        "TR-1",
        "2024-06-01",
        lines=[{"description": "Work", "qty": 1, "rate": 15.0}],
    )
    pid = business.record_ar_payment(
        db._conn,
        cid,
        "2024-06-02",
        15.0,
        [(inv, 15.0)],
    )
    aid = db.add_bank_account("TupleChk")
    bid = db.create_batch(aid)
    db.import_transactions(
        bid,
        aid,
        [
            {
                "txn_date": "2024-06-02",
                "description": "Pay",
                "amount": 15.0,
                "ref_number": "",
            }
        ],
    )
    tid = db.list_transactions(aid)[0]["id"]
    business.link_bank_transaction(db._conn, tid, "ar_payment", pid)
    bm = business.get_bank_match(db._conn, tid)
    assert business.bank_match_link_tuple_from_row(bm) == ("ar_payment", pid)
    assert business.bank_match_link_tuple_from_row(bm) == business.bank_match_link_for_navigation(
        db._conn, tid
    )


def test_bank_match_is_navigable_tracks_tuple_and_blank_link_type(db):
    cid = business.add_customer(db._conn, "NavBool")
    inv = business.create_invoice(
        db._conn,
        cid,
        "NB-1",
        "2024-06-01",
        lines=[{"description": "Work", "qty": 1, "rate": 11.0}],
    )
    pid = business.record_ar_payment(
        db._conn,
        cid,
        "2024-06-02",
        11.0,
        [(inv, 11.0)],
    )
    aid = db.add_bank_account("NavBoolChk")
    bid = db.create_batch(aid)
    db.import_transactions(
        bid,
        aid,
        [
            {
                "txn_date": "2024-06-02",
                "description": "Pay",
                "amount": 11.0,
                "ref_number": "",
            }
        ],
    )
    tid = db.list_transactions(aid)[0]["id"]
    assert not business.bank_match_is_navigable(db._conn, tid)
    business.link_bank_transaction(db._conn, tid, "ar_payment", pid)
    assert business.bank_match_is_navigable(db._conn, tid)
    db._conn.execute(
        "UPDATE bank_match_links SET link_type = '' WHERE bank_transaction_id = ?",
        (tid,),
    )
    db._conn.commit()
    assert not business.bank_match_is_navigable(db._conn, tid)


def test_bank_match_is_navigable_false_on_operational_error(db):
    with patch(
        "probooksai.business.get_bank_match",
        side_effect=sqlite3.OperationalError("no such table: bank_match_links"),
    ):
        assert not business.bank_match_is_navigable(db._conn, 1)


def test_bank_match_link_tuple_from_row_accepts_mapping_like_rows():
    """``sqlite3.Row`` is mapping-like; accept plain dicts for the same key shape."""
    assert business.bank_match_link_tuple_from_row(
        {"link_type": "ar_payment", "link_id": 9}
    ) == ("ar_payment", 9)
    assert business.bank_match_link_tuple_from_row(
        {"link_type": "ar_payment", "link_id": "12"}
    ) == ("ar_payment", 12)
    assert business.bank_match_link_tuple_from_row(
        {"link_type": "ar_payment", "link_id": None}
    ) is None
    assert business.bank_match_link_tuple_from_row(
        {"link_type": "ar_payment", "link_id": "nope"}
    ) is None
    assert business.bank_match_link_tuple_from_row({"link_type": "", "link_id": 1}) is None


def test_suggest_bank_match_includes_old_payment_when_many_recent_exist(db):
    """Date-window query must not drop a correct AR payment outside the newest 200 rows."""
    cid = business.add_customer(db._conn, "Acme")
    inv_match = business.create_invoice(
        db._conn,
        cid,
        "INV-OLD",
        "2020-01-01",
        lines=[{"description": "Work", "qty": 1, "rate": 50.0}],
    )
    pid_match = business.record_ar_payment(
        db._conn,
        cid,
        "2020-01-05",
        50.0,
        [(inv_match, 50.0)],
    )
    for i in range(210):
        inv = business.create_invoice(
            db._conn,
            cid,
            f"F{i}",
            "2024-06-01",
            lines=[{"description": "x", "qty": 1, "rate": 99.99}],
        )
        business.record_ar_payment(
            db._conn,
            cid,
            "2024-06-15",
            99.99,
            [(inv, 99.99)],
        )
    aid = db.add_bank_account("Chk")
    bid = db.create_batch(aid)
    db.import_transactions(
        bid,
        aid,
        [
            {
                "txn_date": "2020-01-06",
                "description": "Deposit",
                "amount": 50.0,
                "ref_number": "",
            }
        ],
    )
    tid = db.list_transactions(aid)[0]["id"]
    sug = business.suggest_bank_match_candidates(db._conn, tid)
    assert any(
        s["link_type"] == "ar_payment" and s["link_id"] == pid_match for s in sug
    )


def test_suggest_bank_match_prefers_party_name_in_bank_text(db):
    """When amount and pay date tie, a customer name in description ranks that AR payment higher."""
    c_nw = business.add_customer(db._conn, "Northwind Traders")
    c_ot = business.add_customer(db._conn, "Otherco Vendor")
    inv_nw = business.create_invoice(
        db._conn,
        c_nw,
        "N1",
        "2024-05-01",
        lines=[{"description": "w", "qty": 1, "rate": 100.0}],
    )
    inv_ot = business.create_invoice(
        db._conn,
        c_ot,
        "O1",
        "2024-05-01",
        lines=[{"description": "w", "qty": 1, "rate": 100.0}],
    )
    pid_nw = business.record_ar_payment(
        db._conn,
        c_nw,
        "2024-06-01",
        100.0,
        [(inv_nw, 100.0)],
    )
    pid_ot = business.record_ar_payment(
        db._conn,
        c_ot,
        "2024-06-01",
        100.0,
        [(inv_ot, 100.0)],
    )
    aid = db.add_bank_account("Chk")
    bid = db.create_batch(aid)
    db.import_transactions(
        bid,
        aid,
        [
            {
                "txn_date": "2024-06-01",
                "description": "ACH credit NORTHWIND TRADERS",
                "amount": 100.0,
                "ref_number": "",
            }
        ],
    )
    tid = db.list_transactions(aid)[0]["id"]
    sug = business.suggest_bank_match_candidates(db._conn, tid)
    ar = [s for s in sug if s["link_type"] == "ar_payment"]
    by_id = {s["link_id"]: s for s in ar}
    assert pid_nw in by_id and pid_ot in by_id
    assert by_id[pid_nw]["score"] < by_id[pid_ot]["score"]


def test_suggest_bank_match_includes_open_ar_invoice(db):
    cid = business.add_customer(db._conn, "Acme")
    inv_id = business.create_invoice(
        db._conn,
        cid,
        "INV-OPEN",
        "2024-06-01",
        lines=[{"description": "Svc", "qty": 1, "rate": 75.5}],
    )
    aid = db.add_bank_account("Chk")
    bid = db.create_batch(aid)
    db.import_transactions(
        bid,
        aid,
        [
            {
                "txn_date": "2024-06-10",
                "description": "Deposit",
                "amount": 75.5,
                "ref_number": "",
            }
        ],
    )
    tid = db.list_transactions(aid)[0]["id"]
    sug = business.suggest_bank_match_candidates(db._conn, tid)
    assert any(
        s["link_type"] == "ar_invoice" and s["link_id"] == inv_id for s in sug
    )


def test_suggest_bank_match_includes_open_ap_bill(db):
    vid = business.add_vendor(db._conn, "VendCo")
    bill_id = business.create_bill(
        db._conn,
        vid,
        "2024-06-01",
        120.0,
        vendor_invoice_number="V-9",
    )
    aid = db.add_bank_account("Chk")
    bid = db.create_batch(aid)
    db.import_transactions(
        bid,
        aid,
        [
            {
                "txn_date": "2024-06-10",
                "description": "ACH bill pay",
                "amount": -120.0,
                "ref_number": "",
            }
        ],
    )
    tid = db.list_transactions(aid)[0]["id"]
    sug = business.suggest_bank_match_candidates(db._conn, tid)
    assert any(
        s["link_type"] == "ap_bill" and s["link_id"] == bill_id for s in sug
    )


def test_suggest_bank_match_excludes_invoice_linked_elsewhere(db):
    cid = business.add_customer(db._conn, "Acme")
    inv_id = business.create_invoice(
        db._conn,
        cid,
        "INV-L",
        "2024-06-01",
        lines=[{"description": "Svc", "qty": 1, "rate": 40.0}],
    )
    aid = db.add_bank_account("Chk")
    bid = db.create_batch(aid)
    db.import_transactions(
        bid,
        aid,
        [
            {
                "txn_date": "2024-06-10",
                "description": "A",
                "amount": 40.0,
                "ref_number": "",
            },
            {
                "txn_date": "2024-06-11",
                "description": "B",
                "amount": 40.0,
                "ref_number": "",
            },
        ],
    )
    rows = db.list_transactions(aid)
    tid_a = rows[0]["id"]
    tid_b = rows[1]["id"]
    business.link_bank_transaction(db._conn, tid_a, "ar_invoice", inv_id)
    sug_b = business.suggest_bank_match_candidates(db._conn, tid_b)
    assert not any(
        s["link_type"] == "ar_invoice" and s["link_id"] == inv_id for s in sug_b
    )


def test_register_filter_bank_match(db):
    cid = business.add_customer(db._conn, "Acme")
    inv_id = business.create_invoice(
        db._conn,
        cid,
        "I1",
        "2024-05-01",
        lines=[{"description": "Work", "qty": 1, "rate": 100.0}],
    )
    pid = business.record_ar_payment(
        db._conn,
        cid,
        "2024-06-01",
        100.0,
        [(inv_id, 100.0)],
    )
    aid = db.add_bank_account("Chk")
    bid = db.create_batch(aid)
    db.import_transactions(
        bid,
        aid,
        [
            {
                "txn_date": "2024-06-01",
                "description": "Deposit",
                "amount": 100.0,
                "ref_number": "",
            },
            {
                "txn_date": "2024-06-02",
                "description": "Other",
                "amount": 50.0,
                "ref_number": "",
            },
        ],
    )
    rows = db.list_transactions(aid)
    tid0 = rows[0]["id"]
    business.link_bank_transaction(db._conn, tid0, "ar_payment", pid)
    assert len(db.list_transactions(aid, register_filter="has_bank_match")) == 1
    assert len(db.list_transactions(aid, register_filter="no_bank_match")) == 1
    assert len(db.list_transactions(aid)) == 2


def test_bank_match_link_writes_audit(db):
    from probooksai.audit_log import list_for_entity

    cid = business.add_customer(db._conn, "Acme")
    inv_paid = business.create_invoice(
        db._conn,
        cid,
        "I1",
        "2024-05-01",
        lines=[{"description": "Work", "qty": 1, "rate": 100.0}],
    )
    pid = business.record_ar_payment(
        db._conn,
        cid,
        "2024-06-01",
        100.0,
        [(inv_paid, 100.0)],
    )
    inv_open = business.create_invoice(
        db._conn,
        cid,
        "I2",
        "2024-05-15",
        lines=[{"description": "More", "qty": 1, "rate": 40.0}],
    )
    aid = db.add_bank_account("Chk")
    bid = db.create_batch(aid)
    db.import_transactions(
        bid,
        aid,
        [
            {
                "txn_date": "2024-06-05",
                "description": "Deposit",
                "amount": 100.0,
                "ref_number": "",
            }
        ],
    )
    tid = db.list_transactions(aid)[0]["id"]
    business.link_bank_transaction(db._conn, tid, "ar_payment", pid)
    ent = list_for_entity(db._conn, "bank_transaction", tid, limit=30)
    assert any(
        x["field"] == "bank_match_link"
        and (x["new_value"] or "") == f"ar_payment:{pid}"
        for x in ent
    )
    business.link_bank_transaction(db._conn, tid, "ar_invoice", inv_open)
    ent2 = list_for_entity(db._conn, "bank_transaction", tid, limit=50)
    assert any(
        x["field"] == "bank_match_link"
        and (x["old_value"] or "") == f"ar_payment:{pid}"
        and (x["new_value"] or "") == f"ar_invoice:{inv_open}"
        for x in ent2
    )
    business.unlink_bank_transaction(db._conn, tid)
    ent3 = list_for_entity(db._conn, "bank_transaction", tid, limit=80)
    assert any(
        x["field"] == "bank_match_link"
        and (x["old_value"] or "") == f"ar_invoice:{inv_open}"
        and (x["new_value"] or "") == ""
        for x in ent3
    )


def test_list_ar_invoice_and_ap_bill_link_choices(db):
    cid = business.add_customer(db._conn, "Cust")
    business.create_invoice(
        db._conn,
        cid,
        "Z1",
        "2024-01-01",
        lines=[{"description": "a", "qty": 1, "rate": 10.0}],
    )
    inv_rows = business.list_ar_invoice_link_choices(db._conn)
    assert len(inv_rows) == 1
    assert float(inv_rows[0]["balance_due"]) == pytest.approx(10.0)
    vid = business.add_vendor(db._conn, "Vend")
    business.create_bill(db._conn, vid, "2024-02-01", 20.0)
    bill_rows = business.list_ap_bill_link_choices(db._conn)
    assert len(bill_rows) == 1
    assert float(bill_rows[0]["balance_due"]) == pytest.approx(20.0)


def test_audit_list_filtered_by_entity(db):
    from probooksai.audit_log import list_filtered, list_for_entity

    aid = db.add_bank_account("Aud")
    bid = db.create_batch(aid)
    db.import_transactions(
        bid,
        aid,
        [
            {
                "txn_date": "2024-01-01",
                "description": "z",
                "amount": -2.0,
                "ref_number": "",
            }
        ],
    )
    tid = db.list_transactions(aid)[0]["id"]
    db.update_transaction(tid, memo="edited")
    one = list_for_entity(db._conn, "bank_transaction", tid, limit=20)
    assert any(x["field"] == "memo" for x in one)
    by_type = list_filtered(db._conn, entity_type="bank_transaction", entity_id=None, limit=500)
    assert len(by_type) >= 1


def test_audit_log_on_bank_txn_update(db):
    from probooksai.audit_log import list_recent

    aid = db.add_bank_account("Aud")
    bid = db.create_batch(aid)
    db.import_transactions(
        bid,
        aid,
        [
            {
                "txn_date": "2024-01-01",
                "description": "z",
                "amount": -2.0,
                "ref_number": "",
            }
        ],
    )
    tid = db.list_transactions(aid)[0]["id"]
    db.update_transaction(tid, memo="edited")
    recent = list_recent(db._conn, 20)
    assert any(r["entity_type"] == "bank_transaction" and r["field"] == "memo" for r in recent)


def test_gl_post_bank_transfer(db):
    from probooksai.gl import GLDatabase

    gdb = GLDatabase(db._conn)
    a1 = db.add_bank_account("Checking", gl_display_account="1010 – C")
    a2 = db.add_bank_account("Savings", gl_display_account="1020 – S")
    bid = db.create_batch(a1)
    db.import_transactions(
        bid,
        a1,
        [
            {
                "txn_date": "2024-04-01",
                "description": "To savings",
                "amount": -40.0,
                "ref_number": "",
            },
        ],
    )
    tid = db.list_transactions(a1)[0]["id"]
    db.update_transaction(tid, transfer_to_bank_account_id=a2)
    eid = gdb.post_transaction(tid, "1010 – C", "")
    lines = gdb.get_entry_lines(eid)
    assert len(lines) == 2
    c_line = next(ln for ln in lines if ln["account"] == "1010 – C")
    s_line = next(ln for ln in lines if ln["account"] == "1020 – S")
    assert c_line["credit"] == 40.0
    assert s_line["debit"] == 40.0


def test_gl_post_uses_bank_splits(db):
    from probooksai.gl import GLDatabase

    gdb = GLDatabase(db._conn)
    aid = db.add_bank_account("Chk")
    bid = db.create_batch(aid)
    db.import_transactions(
        bid,
        aid,
        [
            {
                "txn_date": "2024-02-01",
                "description": "Split pay",
                "amount": -100.0,
                "ref_number": "",
            },
        ],
    )
    tid = db.list_transactions(aid)[0]["id"]
    business.replace_splits(
        db._conn,
        tid,
        [(-40.0, "6100 – Office", ""), (-60.0, "6200 – Travel", "")],
    )
    entry_id = gdb.post_transaction(tid, "1010 Checking", "9999 – ignored")
    lines = gdb.get_entry_lines(entry_id)
    assert len(lines) == 3
    bank = next(ln for ln in lines if ln["account"] == "1010 Checking")
    assert bank["credit"] == 100.0
    assert sum(ln["debit"] for ln in lines if ln["account"] != "1010 Checking") == 100.0


def test_coa_update_writes_audit(db):
    from probooksai.audit_log import list_recent
    from probooksai.coa_db import COADatabase

    cdb = COADatabase(db._conn)
    acct_id = cdb.add_account("8888", "Old Name", "expense")
    cdb.update_account(acct_id, "8888", "New Name", "expense")
    recent = list_recent(db._conn, 50)
    assert any(
        r["entity_type"] == "coa_account"
        and r["field"] == "account_name"
        and (r["new_value"] or "") == "New Name"
        for r in recent
    )


def test_sales_tax_summary_by_invoice_date(db):
    cid = business.add_customer(db._conn, "TaxCo")
    business.create_invoice(
        db._conn,
        cid,
        "T-1",
        "2024-04-10",
        lines=[{"description": "S", "qty": 1, "rate": 200.0}],
        tax_rate_pct=8.0,
    )
    rows = business.sales_tax_invoices_in_range(db._conn, "2024-04-01", "2024-04-30")
    assert len(rows) == 1
    assert float(rows[0]["tax_total"]) == pytest.approx(16.0)
    assert business.sales_tax_collected_sum(
        db._conn, "2024-04-01", "2024-04-30"
    ) == pytest.approx(16.0)


def test_reconcile_batch_writes_audit(db):
    from probooksai.audit_log import list_for_entity

    aid = db.add_bank_account("Rec")
    batch_id = db.create_batch(
        aid,
        statement_start="2024-01-01",
        statement_end="2024-01-31",
        beginning_balance=100.0,
        ending_balance=160.0,
    )
    db.import_transactions(
        batch_id,
        aid,
        [
            {
                "txn_date": "2024-01-10",
                "description": "dep",
                "amount": 60.0,
                "ref_number": "",
            }
        ],
    )
    res = db.reconcile_batch(batch_id)
    assert res["reconciled"] is True
    ent = list_for_entity(db._conn, "bank_import_batch", batch_id, limit=20)
    assert any(x["field"] == "is_reconciled" for x in ent)


def test_ar_invoice_and_aging(db):
    cid = business.add_customer(db._conn, "Acme")
    business.create_invoice(
        db._conn,
        cid,
        "INV-1",
        "2024-01-01",
        due_date="2024-01-15",
        lines=[{"description": "Work", "qty": 1, "rate": 100.0}],
        tax_rate_pct=0,
    )
    invs = business.list_invoices(db._conn)
    assert len(invs) == 1
    assert invs[0]["balance_due"] == pytest.approx(100.0)
    aging = business.ar_aging_buckets(db._conn, "2024-06-01")[0]
    assert "buckets" in aging


def test_ar_ap_aging_bucket_totals_equal_sum_of_lines(db):
    cid = business.add_customer(db._conn, "C1")
    business.create_invoice(
        db._conn,
        cid,
        "A1",
        "2024-01-01",
        due_date="2024-01-05",
        lines=[{"description": "x", "qty": 1, "rate": 10.0}],
    )
    business.create_invoice(
        db._conn,
        cid,
        "A2",
        "2024-01-02",
        due_date="2024-02-20",
        lines=[{"description": "y", "qty": 1, "rate": 20.0}],
    )
    ar = business.ar_aging_buckets(db._conn, "2024-03-01")[0]
    line_sum = sum(float(ln["balance"]) for ln in ar["lines"])
    bucket_sum = sum(float(ar["buckets"][k]) for k in ar["buckets"])
    assert line_sum == pytest.approx(bucket_sum)

    vid = business.add_vendor(db._conn, "V1")
    business.create_bill(db._conn, vid, "2024-01-01", 5.0, due_date="2024-01-10")
    business.create_bill(db._conn, vid, "2024-01-02", 7.0, due_date="2024-03-01")
    ap = business.ap_aging_buckets(db._conn, "2024-03-15")[0]
    line_sum_ap = sum(float(ln["balance"]) for ln in ap["lines"])
    bucket_sum_ap = sum(float(ap["buckets"][k]) for k in ap["buckets"])
    assert line_sum_ap == pytest.approx(bucket_sum_ap)


def test_ap_aging_days_past_due_matches_ar_shape(db):
    vid = business.add_vendor(db._conn, "Supp")
    business.create_bill(
        db._conn,
        vid,
        "2024-01-01",
        50.0,
        due_date="2024-01-10",
    )
    out = business.ap_aging_buckets(db._conn, "2024-02-15")[0]
    assert out["lines"]
    ln = out["lines"][0]
    assert ln["days_past_due"] == 36  # Feb 15 - Jan 10
    assert ln["bucket"] == "31_60"


def test_write_customers_and_vendors_csv(db, tmp_path):
    business.add_customer(db._conn, "Acme", email="a@example.com")
    business.add_vendor(db._conn, "Vendor1", is_1099=True)
    cp = tmp_path / "customers.csv"
    vp = tmp_path / "vendors.csv"
    assert business.write_customers_csv(db._conn, str(cp)) == 1
    assert business.write_vendors_csv(db._conn, str(vp)) == 1
    ctext = cp.read_text(encoding="utf-8-sig")
    assert "Acme" in ctext and "a@example.com" in ctext
    with vp.open(encoding="utf-8-sig", newline="") as f:
        vrows = list(csv.reader(f))
    assert vrows[0][-1] == "is_1099"
    assert vrows[1][1] == "Vendor1"
    assert vrows[1][-1] == "1"


def test_write_invoices_and_bills_csv(db, tmp_path):
    cid = business.add_customer(db._conn, "Buyer")
    vid = business.add_vendor(db._conn, "Supplier")
    business.create_invoice(
        db._conn,
        cid,
        "INV-X",
        "2024-02-01",
        lines=[{"description": "Work", "qty": 1, "rate": 50.0}],
        tax_rate_pct=0,
    )
    business.create_bill(
        db._conn,
        vid,
        "2024-02-15",
        42.0,
        vendor_invoice_number="B-9",
    )
    ip = tmp_path / "inv.csv"
    bp = tmp_path / "bill.csv"
    assert business.write_invoices_csv(db._conn, str(ip)) == 1
    assert business.write_bills_csv(db._conn, str(bp)) == 1
    itext = ip.read_text(encoding="utf-8-sig")
    assert "INV-X" in itext and "Buyer" in itext
    btext = bp.read_text(encoding="utf-8-sig")
    assert "Supplier" in btext and "B-9" in btext


def test_write_invoices_and_bills_csv_subset_ids(db, tmp_path):
    cid = business.add_customer(db._conn, "C")
    vid = business.add_vendor(db._conn, "V")
    i1 = business.create_invoice(
        db._conn,
        cid,
        "INV-1",
        "2024-01-01",
        lines=[{"description": "a", "qty": 1, "rate": 1.0}],
        tax_rate_pct=0,
    )
    i2 = business.create_invoice(
        db._conn,
        cid,
        "INV-2",
        "2024-01-02",
        lines=[{"description": "b", "qty": 1, "rate": 2.0}],
        tax_rate_pct=0,
    )
    ip = tmp_path / "inv_order.csv"
    assert business.write_invoices_csv(db._conn, str(ip), invoice_ids=[i2, i1]) == 2
    inv_text = ip.read_text(encoding="utf-8-sig")
    assert inv_text.index("INV-2") < inv_text.index("INV-1")

    ip_one = tmp_path / "inv_one.csv"
    assert business.write_invoices_csv(db._conn, str(ip_one), invoice_ids=[i2]) == 1
    assert "INV-2" in ip_one.read_text(encoding="utf-8-sig")
    assert "INV-1" not in ip_one.read_text(encoding="utf-8-sig")

    b1 = business.create_bill(db._conn, vid, "2024-02-01", 10.0, vendor_invoice_number="VB1")
    b2 = business.create_bill(db._conn, vid, "2024-02-02", 20.0, vendor_invoice_number="VB2")
    bp = tmp_path / "bills_order.csv"
    assert business.write_bills_csv(db._conn, str(bp), bill_ids=[b2, b1]) == 2
    bill_text = bp.read_text(encoding="utf-8-sig")
    assert bill_text.index("VB2") < bill_text.index("VB1")

    bp_one = tmp_path / "bill_one.csv"
    assert business.write_bills_csv(db._conn, str(bp_one), bill_ids=[b2]) == 1
    one_b = bp_one.read_text(encoding="utf-8-sig")
    assert "VB2" in one_b and "VB1" not in one_b


def _save_invoice_pdf_subprocess(db_path: str, invoice_id: int, pdf_path: str) -> subprocess.CompletedProcess:
    """Run Qt PDF export in a child process so a native Qt crash cannot abort pytest."""
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    code = (
        "import sqlite3\n"
        "from desktop_app.invoice_pdf import save_invoice_pdf\n"
        f"c = sqlite3.connect({db_path!r})\n"
        "c.row_factory = sqlite3.Row\n"
        f"save_invoice_pdf(c, {invoice_id}, {pdf_path!r})\n"
        "c.close()\n"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="QPrinter PDF can abort the Qt process on some Windows builds (0xC0000409); Linux CI runs this test.",
)
def test_save_invoice_pdf_smoke(db, tmp_path):
    pytest.importorskip("PySide6.QtPrintSupport")

    cid = business.add_customer(db._conn, "Acme LLC", address="1 Main St")
    iid = business.create_invoice(
        db._conn,
        cid,
        "INV-PDF",
        "2024-05-01",
        due_date="2024-05-15",
        memo="Terms: net 30 & <keep>",
        lines=[{"description": "Consulting & Co.", "qty": 1, "rate": 100.0}],
        tax_rate_pct=0,
    )
    db._conn.commit()
    out = tmp_path / "invoice.pdf"
    db_path = str(tmp_path / "t.db")
    proc = _save_invoice_pdf_subprocess(db_path, iid, str(out))
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert out.is_file() and out.stat().st_size > 400


def test_invoice_html_string_uses_company_setup_letterhead(db) -> None:
    """Live invoice HTML pulls sender block from Company setup keys in company_settings."""
    from desktop_app.invoice_pdf import invoice_html_string

    cid = business.add_customer(db._conn, "Cust LLC", address="1 Oak St")
    iid = business.create_invoice(
        db._conn,
        cid,
        "L-H-1",
        "2024-06-01",
        lines=[{"description": "Line", "qty": 1, "rate": 10.0}],
        tax_rate_pct=0,
    )
    business.set_setting(db._conn, "company_setup_name", "SetupCo & Sons")
    business.set_setting(db._conn, "company_setup_addr1", "100 Main St")
    business.set_setting(db._conn, "company_setup_city", "Austin")
    business.set_setting(db._conn, "company_setup_state", "TX")
    business.set_setting(db._conn, "company_setup_zip", "78701")
    business.set_setting(db._conn, "company_setup_phone", "555-0100")
    business.set_setting(db._conn, "company_setup_email", "hello@example.com")
    db._conn.commit()
    html = invoice_html_string(db._conn, iid)
    assert "SetupCo &amp; Sons" in html
    assert "100 Main St" in html
    assert "Austin, TX 78701" in html
    assert "555-0100" in html
    assert "hello@example.com" in html


def test_invoice_html_string_legacy_invoice_company_keys_fallback(db) -> None:
    """Older invoice_company_* settings still work when company_setup_* is empty."""
    from desktop_app.invoice_pdf import invoice_html_string

    cid = business.add_customer(db._conn, "Cust2", address="")
    iid = business.create_invoice(
        db._conn,
        cid,
        "L-H-2",
        "2024-06-02",
        lines=[{"description": "x", "qty": 1, "rate": 1.0}],
        tax_rate_pct=0,
    )
    business.set_setting(db._conn, "invoice_company_name", "Legacy Co")
    db._conn.commit()
    html = invoice_html_string(db._conn, iid)
    assert "Legacy Co" in html


def test_invoice_html_string_invoice_company_block_overrides_setup(db) -> None:
    """Multiline invoice_company_block wins over structured company_setup_* fields."""
    from desktop_app.invoice_pdf import invoice_html_string

    cid = business.add_customer(db._conn, "Cust3", address="")
    iid = business.create_invoice(
        db._conn,
        cid,
        "L-H-3",
        "2024-06-03",
        lines=[{"description": "x", "qty": 1, "rate": 1.0}],
        tax_rate_pct=0,
    )
    business.set_setting(db._conn, "company_setup_name", "Ignored Name")
    business.set_setting(
        db._conn,
        "invoice_company_block",
        "Block & Co.\nSecond line",
    )
    db._conn.commit()
    html = invoice_html_string(db._conn, iid)
    assert "Block &amp; Co." in html
    assert "Second line" in html
    assert "Ignored Name" not in html


def test_write_ar_and_ap_payments_csv(db, tmp_path):
    cid = business.add_customer(db._conn, "PayerCo")
    vid = business.add_vendor(db._conn, "PayeeCo")
    iid = business.create_invoice(
        db._conn,
        cid,
        "P-1",
        "2024-02-01",
        lines=[{"description": "x", "qty": 1, "rate": 40.0}],
    )
    bill_id = business.create_bill(db._conn, vid, "2024-02-10", 15.0)
    bank_id = db.add_bank_account("Operating")
    business.record_ar_payment(
        db._conn,
        cid,
        "2024-02-20",
        40.0,
        [(iid, 40.0)],
        bank_account_id=bank_id,
        reference="DEP-1",
    )
    business.record_ap_payment(
        db._conn,
        vid,
        "2024-02-21",
        15.0,
        [(bill_id, 15.0)],
        bank_account_id=bank_id,
        reference="CHK-9",
    )
    arp = tmp_path / "ar_pay.csv"
    app = tmp_path / "ap_pay.csv"
    assert business.write_ar_payments_csv(db._conn, str(arp)) == 1
    assert business.write_ap_payments_csv(db._conn, str(app)) == 1
    art = arp.read_text(encoding="utf-8-sig")
    assert "PayerCo" in art and "DEP-1" in art and "Operating" in art
    apt = app.read_text(encoding="utf-8-sig")
    assert "PayeeCo" in apt and "CHK-9" in apt and "Operating" in apt

    aral = tmp_path / "ar_alloc.csv"
    apal = tmp_path / "ap_alloc.csv"
    assert business.write_ar_payment_allocations_csv(db._conn, str(aral)) == 1
    assert business.write_ap_payment_allocations_csv(db._conn, str(apal)) == 1
    assert "P-1" in aral.read_text(encoding="utf-8-sig") and "40.00" in aral.read_text(
        encoding="utf-8-sig"
    )
    assert "PayeeCo" in apal.read_text(encoding="utf-8-sig") and "15.00" in apal.read_text(
        encoding="utf-8-sig"
    )


def test_update_invoice_and_blocked_after_payment(db):
    cid = business.add_customer(db._conn, "C1")
    iid = business.create_invoice(
        db._conn,
        cid,
        "E1",
        "2024-03-01",
        lines=[{"description": "A", "qty": 1, "rate": 10.0}],
        tax_rate_pct=10.0,
    )
    row = db._conn.execute("SELECT total, balance_due FROM invoices WHERE id = ?", (iid,)).fetchone()
    assert float(row["total"]) == pytest.approx(11.0)
    business.update_invoice(
        db._conn,
        iid,
        cid,
        "E1",
        "2024-03-02",
        memo="x",
        lines=[{"description": "B", "qty": 2, "rate": 5.0}],
        tax_rate_pct=0,
    )
    row2 = db._conn.execute("SELECT total, memo FROM invoices WHERE id = ?", (iid,)).fetchone()
    assert float(row2["total"]) == pytest.approx(10.0)
    assert row2["memo"] == "x"
    business.record_ar_payment(db._conn, cid, "2024-03-10", 10.0, [(iid, 10.0)])
    with pytest.raises(ValueError, match="payments"):
        business.update_invoice(
            db._conn,
            iid,
            cid,
            "E1",
            "2024-03-02",
            lines=[{"description": "B", "qty": 1, "rate": 1.0}],
        )


def test_record_ar_payment_deposit_bank_account(db):
    cid = business.add_customer(db._conn, "Dep")
    iid = business.create_invoice(
        db._conn,
        cid,
        "D1",
        "2024-01-01",
        lines=[{"description": "x", "qty": 1, "rate": 30.0}],
    )
    aid = db.add_bank_account("Checking")
    pid = business.record_ar_payment(
        db._conn,
        cid,
        "2024-01-15",
        30.0,
        [(iid, 30.0)],
        bank_account_id=aid,
    )
    row = db._conn.execute(
        "SELECT bank_account_id FROM ar_payments WHERE id = ?", (pid,)
    ).fetchone()
    assert row["bank_account_id"] == aid

    iid2 = business.create_invoice(
        db._conn,
        cid,
        "D2",
        "2024-01-02",
        lines=[{"description": "y", "qty": 1, "rate": 5.0}],
    )
    pid2 = business.record_ar_payment(
        db._conn,
        cid,
        "2024-01-16",
        5.0,
        [(iid2, 5.0)],
    )
    row2 = db._conn.execute(
        "SELECT bank_account_id FROM ar_payments WHERE id = ?", (pid2,)
    ).fetchone()
    assert row2["bank_account_id"] is None


def test_list_open_invoices_and_bills_for_party(db):
    cid = business.add_customer(db._conn, "C")
    vid = business.add_vendor(db._conn, "V")
    iid = business.create_invoice(
        db._conn,
        cid,
        "Z1",
        "2024-01-10",
        lines=[{"description": "x", "qty": 1, "rate": 40.0}],
    )
    bid = business.create_bill(db._conn, vid, "2024-02-01", 25.0)
    open_inv = business.list_open_invoices_for_customer(db._conn, cid)
    assert len(open_inv) == 1 and open_inv[0]["id"] == iid
    open_b = business.list_open_bills_for_vendor(db._conn, vid)
    assert len(open_b) == 1 and open_b[0]["id"] == bid
    business.record_ar_payment(db._conn, cid, "2024-01-20", 40.0, [(iid, 40.0)])
    assert business.list_open_invoices_for_customer(db._conn, cid) == []
    business.record_ap_payment(db._conn, vid, "2024-02-10", 25.0, [(bid, 25.0)])
    assert business.list_open_bills_for_vendor(db._conn, vid) == []


def test_list_customer_ar_summaries(db):
    cid = business.add_customer(db._conn, "Acme")
    rows = business.list_customer_ar_summaries(db._conn)
    assert len(rows) == 1
    assert rows[0]["customer_id"] == cid
    assert rows[0]["open_balance"] == 0.0
    assert rows[0]["ar_status"] == "Current"
    iid = business.create_invoice(
        db._conn,
        cid,
        "I1",
        "2024-01-10",
        due_date="2024-01-31",
        lines=[{"description": "x", "qty": 1, "rate": 100.0}],
    )
    rows2 = business.list_customer_ar_summaries(db._conn)
    r = next(x for x in rows2 if x["customer_id"] == cid)
    assert r["open_balance"] == 100.0
    assert r["last_invoice_date"] == "2024-01-10"
    business.record_ar_payment(db._conn, cid, "2024-01-15", 100.0, [(iid, 100.0)])
    rows3 = business.list_customer_ar_summaries(db._conn)
    r3 = next(x for x in rows3 if x["customer_id"] == cid)
    assert r3["open_balance"] == 0.0
    assert r3["last_payment_date"] == "2024-01-15"


def test_get_update_customer_and_vendor(db):
    cid = business.add_customer(db._conn, "Old", email="a@x.org")
    row = business.get_customer(db._conn, cid)
    assert row["name"] == "Old"
    business.update_customer(
        db._conn,
        cid,
        "NewCo",
        email="b@x.org",
        phone="555",
        address="1 Main",
        notes="vip",
    )
    row2 = business.get_customer(db._conn, cid)
    assert row2["name"] == "NewCo"
    assert row2["email"] == "b@x.org"
    assert row2["phone"] == "555"
    assert row2["address"] == "1 Main"
    assert row2["notes"] == "vip"
    with pytest.raises(ValueError, match="not found"):
        business.update_customer(db._conn, 99999, "X")

    vid = business.add_vendor(db._conn, "V0", is_1099=False)
    business.update_vendor(
        db._conn,
        vid,
        "V1",
        email="v@v.com",
        is_1099=True,
    )
    vr = business.get_vendor(db._conn, vid)
    assert vr["name"] == "V1"
    assert vr["email"] == "v@v.com"
    assert int(vr["is_1099"]) == 1
    with pytest.raises(ValueError, match="not found"):
        business.update_vendor(db._conn, 99999, "X")


def test_update_bill_and_blocked_after_payment(db):
    vid = business.add_vendor(db._conn, "V1")
    bid = business.create_bill(db._conn, vid, "2024-04-01", 100.0, vendor_invoice_number="X1")
    business.update_bill(
        db._conn,
        bid,
        vid,
        "2024-04-02",
        80.0,
        vendor_invoice_number="X2",
        memo="m",
    )
    row = db._conn.execute(
        "SELECT total, balance_due, memo, vendor_invoice_number FROM bills WHERE id = ?",
        (bid,),
    ).fetchone()
    assert float(row["total"]) == pytest.approx(80.0)
    assert float(row["balance_due"]) == pytest.approx(80.0)
    assert row["memo"] == "m"
    assert row["vendor_invoice_number"] == "X2"
    business.record_ap_payment(db._conn, vid, "2024-04-15", 80.0, [(bid, 80.0)])
    with pytest.raises(ValueError, match="payments"):
        business.update_bill(db._conn, bid, vid, "2024-04-02", 50.0)


def test_list_vendor_ap_summaries_open_current_overdue_and_last_dates(db):
    from datetime import date, timedelta

    today = date.today()
    past = (today - timedelta(days=30)).isoformat()
    future = (today + timedelta(days=30)).isoformat()
    v1 = business.add_vendor(db._conn, "SumVendor")
    business.create_bill(db._conn, v1, "2024-06-01", 40.0, due_date=future)
    business.create_bill(db._conn, v1, "2024-05-01", 60.0, due_date=past)
    by_id = {r["vendor_id"]: r for r in business.list_vendor_ap_summaries(db._conn)}
    r = by_id[v1]
    assert r["open_balance"] == pytest.approx(100.0)
    assert r["current_due"] == pytest.approx(40.0)
    assert r["overdue"] == pytest.approx(60.0)
    assert r["last_bill_date"] == "2024-06-01"
    assert r["ap_status"] == "Overdue"
    business.record_ap_payment(db._conn, v1, "2025-01-15", 1.0, [])
    by_id2 = {r["vendor_id"]: r for r in business.list_vendor_ap_summaries(db._conn)}
    assert by_id2[v1]["last_payment_date"] == "2025-01-15"
