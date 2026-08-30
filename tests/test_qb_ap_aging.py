"""A/P Aging Summary data — live open bills, one row per vendor, no seed names."""

from __future__ import annotations

from pathlib import Path

import pytest

from probooksai import business
from probooksai import qb_ap_aging as aging
from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import apply_extensions

_AS_OF = "2026-08-27"
_FORBIDDEN = (
    "ANVIL STEEL",
    "FLATIRON",
    "BST LINEHAUL",
    "CHAVAN",
    "126,845",
    "335,036.07",
)


@pytest.fixture
def db(tmp_path: Path) -> BankDatabase:
    b = BankDatabase(db_path=str(tmp_path / "ap_aging.db"))
    apply_extensions(b._conn)
    yield b
    b.close()


def test_bucket_columns_default_qb_pro_layout() -> None:
    cols = aging.bucket_columns(30, 90)
    labels = [c[1] for c in cols]
    assert labels == ["Current", "1 - 30", "31 - 60", "61 - 90", "> 90"]


def test_bucket_columns_custom_interval() -> None:
    cols = aging.bucket_columns(15, 60)
    labels = [c[1] for c in cols]
    assert labels == ["Current", "1 - 15", "16 - 30", "31 - 45", "46 - 60", "> 60"]


def test_empty_company_is_zeros(db: BankDatabase) -> None:
    data = aging.ap_aging_summary(db._conn, _AS_OF)
    assert data["groups"] == []
    assert data["grand_total"]["total"] == 0.0
    for key in data["bucket_keys"]:
        assert data["grand_total"][key] == 0.0
    for name in _FORBIDDEN:
        assert name not in str(data)


def test_paid_bill_does_not_age(db: BankDatabase) -> None:
    vid = business.add_vendor(db._conn, "Harbor Fuel")
    bid = business.create_bill(
        db._conn,
        vid,
        "2026-06-01",
        80.0,
        vendor_invoice_number="PAID-1",
        due_date="2026-06-15",
    )
    business.record_ap_payment(
        db._conn, vid, "2026-06-20", 80.0, [(bid, 80.0)], method="Check", reference="9"
    )
    data = aging.ap_aging_summary(db._conn, _AS_OF)
    assert data["groups"] == []
    assert data["grand_total"]["total"] == 0.0


def test_buckets_group_per_vendor(db: BankDatabase) -> None:
    supply = business.add_vendor(db._conn, "Harbor Supply Co")
    fuel = business.add_vendor(db._conn, "Westside Fuel")
    business.create_bill(
        db._conn,
        supply,
        "2026-08-01",
        100.0,
        vendor_invoice_number="HSC-9",
        due_date="2026-08-20",
    )
    business.create_bill(
        db._conn,
        supply,
        "2026-07-01",
        50.0,
        vendor_invoice_number="HSC-10",
        due_date="2026-07-10",
    )
    business.create_bill(
        db._conn,
        fuel,
        "2026-01-01",
        25.0,
        vendor_invoice_number="WF-1",
        due_date="2026-01-15",
    )
    data = aging.ap_aging_summary(db._conn, _AS_OF, interval=30, through=90)
    by_name = {g["name"]: g for g in data["groups"]}
    assert set(by_name) == {"Harbor Supply Co", "Westside Fuel"}
    supply_row = by_name["Harbor Supply Co"]
    assert supply_row["kind"] == "vendor"
    assert supply_row["amounts"]["1_30"] == pytest.approx(100.0)
    assert supply_row["amounts"]["31_60"] == pytest.approx(50.0)
    assert supply_row["amounts"]["total"] == pytest.approx(150.0)
    fuel_row = by_name["Westside Fuel"]
    assert fuel_row["amounts"]["over_90"] == pytest.approx(25.0)
    assert data["grand_total"]["total"] == pytest.approx(175.0)
    for name in _FORBIDDEN:
        assert name not in str(data)


def test_bill_missing_due_date_falls_in_current(db: BankDatabase) -> None:
    vid = business.add_vendor(db._conn, "Nomad Rentals")
    business.create_bill(
        db._conn,
        vid,
        "2026-08-25",
        40.0,
        vendor_invoice_number="NR-1",
    )
    data = aging.ap_aging_summary(db._conn, _AS_OF)
    assert len(data["groups"]) == 1
    g = data["groups"][0]
    assert g["amounts"]["current"] == pytest.approx(40.0)
    assert g["amounts"]["over_90"] == pytest.approx(0.0)


def test_sort_by_total(db: BankDatabase) -> None:
    a = business.add_vendor(db._conn, "Alpha Supply")
    b = business.add_vendor(db._conn, "Beta Freight")
    business.create_bill(
        db._conn, a, "2026-08-01", 10.0, vendor_invoice_number="A-1", due_date="2026-09-01"
    )
    business.create_bill(
        db._conn, b, "2026-08-01", 90.0, vendor_invoice_number="B-1", due_date="2026-09-01"
    )
    data = aging.ap_aging_summary(db._conn, _AS_OF, sort_by="total")
    assert [g["name"] for g in data["groups"]] == ["Beta Freight", "Alpha Supply"]
