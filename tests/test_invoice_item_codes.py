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
    assert EXTENSION_SCHEMA_VERSION >= 6


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
