"""invoice_item_codes table and business helpers."""

from __future__ import annotations

import sqlite3

import pytest

from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import EXTENSION_SCHEMA_VERSION, apply_extensions
from probooksai import business


@pytest.fixture
def db(tmp_path):
    b = BankDatabase(db_path=str(tmp_path / "codes.db"))
    apply_extensions(b._conn)
    yield b
    b.close()


def test_extension_schema_version_includes_v6(db):
    row = db._conn.execute(
        "SELECT version FROM extension_schema_version WHERE id = 1"
    ).fetchone()
    assert row["version"] == EXTENSION_SCHEMA_VERSION
    assert EXTENSION_SCHEMA_VERSION >= 10
    cols = {
        r[1]
        for r in db._conn.execute("PRAGMA table_info(invoice_item_codes)").fetchall()
    }
    assert {"parent_id", "is_inactive", "used_in_assemblies", "notes"} <= cols


def test_replace_and_lookup_invoice_item_codes(db):
    business.replace_invoice_item_codes(
        db._conn,
        [
            {
                "code": "FS-1",
                "description": "FLATBED TRUCKING",
                "item_type": "Service",
                "coa_account": "4000 – Income",
                "rate_value": 160.0,
                "rate_kind": "amount",
                "sort_order": 0,
            },
            {
                "code": "BROKER",
                "description": "LESS BROKER FEE",
                "item_type": "Discount",
                "coa_account": "4000 – Income",
                "rate_value": -10.0,
                "rate_kind": "percent",
                "sort_order": 1,
            },
        ],
    )
    rows = business.list_invoice_item_codes(db._conn)
    assert len(rows) == 2
    r = business.get_invoice_item_code_by_code(db._conn, "fs-1")
    assert r is not None
    assert (r["description"] or "").strip() == "FLATBED TRUCKING"
    assert float(r["rate_value"]) == pytest.approx(160.0)
    assert business.list_invoice_item_code_strings(db._conn) == ["FS-1", "BROKER"]


def test_duplicate_code_rejected_on_replace(db):
    with pytest.raises(sqlite3.IntegrityError):
        business.replace_invoice_item_codes(
            db._conn,
            [
                {
                    "code": "A",
                    "description": "x",
                    "item_type": "Service",
                    "coa_account": "",
                    "rate_value": 1.0,
                    "rate_kind": "amount",
                    "sort_order": 0,
                },
                {
                    "code": "a",
                    "description": "y",
                    "item_type": "Service",
                    "coa_account": "",
                    "rate_value": 2.0,
                    "rate_kind": "amount",
                    "sort_order": 1,
                },
            ],
        )


def test_upsert_and_inactive_hidden_from_invoice_strings(db):
    iid = business.upsert_invoice_item_code(
        db._conn,
        {
            "code": "Hourly Labor",
            "description": "Standard hourly service",
            "item_type": "Service",
            "coa_account": "4000 – Sales Revenue",
            "rate_value": 85.0,
            "rate_kind": "amount",
        },
    )
    assert iid > 0
    business.upsert_invoice_item_code(
        db._conn,
        {
            "code": "Early Pay Discount",
            "description": "Prompt-pay discount",
            "item_type": "Discount",
            "coa_account": "4000 – Sales Revenue",
            "rate_value": -10.0,
            "rate_kind": "percent",
        },
    )
    business.upsert_invoice_item_code(
        db._conn,
        {
            "code": "Line Subtotal",
            "description": "Subtotal of items above",
            "item_type": "Subtotal",
            "coa_account": "",
            "rate_value": 0.0,
            "rate_kind": "amount",
        },
    )
    strings = business.list_invoice_item_code_strings(db._conn)
    assert "Hourly Labor" in strings
    assert "Early Pay Discount" in strings
    assert "Line Subtotal" in strings
    business.set_invoice_item_inactive(db._conn, iid, inactive=True)
    strings2 = business.list_invoice_item_code_strings(db._conn)
    assert "Hourly Labor" not in strings2
    assert "Early Pay Discount" in strings2
    active_only = business.list_invoice_item_codes(db._conn, include_inactive=False)
    assert all(str(r["code"]) != "Hourly Labor" for r in active_only)


def test_upsert_updates_existing_and_rejects_blank_name(db):
    iid = business.upsert_invoice_item_code(
        db._conn,
        {
            "code": "Mileage",
            "description": "Per-mile travel",
            "item_type": "Service",
            "rate_value": 0.7,
            "rate_kind": "amount",
        },
    )
    business.upsert_invoice_item_code(
        db._conn,
        {
            "id": iid,
            "code": "Mileage",
            "description": "Updated mileage",
            "item_type": "Service",
            "rate_value": 0.85,
            "rate_kind": "amount",
        },
    )
    row = business.get_invoice_item_code(db._conn, iid)
    assert row is not None
    assert (row["description"] or "").strip() == "Updated mileage"
    assert float(row["rate_value"]) == pytest.approx(0.85)
    with pytest.raises(ValueError):
        business.upsert_invoice_item_code(db._conn, {"code": "  "})
