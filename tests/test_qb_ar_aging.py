"""A/R Aging Summary data — live open invoices, customer/job rollup, no seed names."""

from __future__ import annotations

from pathlib import Path

import pytest

from probooksai import business
from probooksai import qb_ar_aging as aging
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
    b = BankDatabase(db_path=str(tmp_path / "ar_aging.db"))
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
    data = aging.ar_aging_summary(db._conn, _AS_OF)
    assert data["groups"] == []
    assert data["grand_total"]["total"] == 0.0
    for key in data["bucket_keys"]:
        assert data["grand_total"][key] == 0.0
    for name in _FORBIDDEN:
        assert name not in str(data)


def test_paid_invoice_does_not_age(db: BankDatabase) -> None:
    cid = business.add_customer(db._conn, "Harbor Logistics")
    iid = business.create_invoice(
        db._conn,
        cid,
        "PAID-1",
        "2026-06-01",
        due_date="2026-06-15",
        lines=[{"description": "Haul", "qty": 1, "rate": 80.0}],
    )
    business.record_ar_payment(
        db._conn, cid, "2026-06-20", 80.0, [(iid, 80.0)], method="Check", reference="9"
    )
    data = aging.ar_aging_summary(db._conn, _AS_OF)
    assert data["groups"] == []
    assert data["grand_total"]["total"] == 0.0


def test_buckets_and_job_rollup(db: BankDatabase) -> None:
    parent = business.add_customer(db._conn, "Harbor Logistics")
    job = business.add_customer(db._conn, "Site A", parent_customer_id=parent)
    solo = business.add_customer(db._conn, "Westside Hauling")
    business.create_invoice(
        db._conn,
        parent,
        "HL-OTHER",
        "2026-08-01",
        due_date="2026-08-20",
        lines=[{"description": "Haul", "qty": 1, "rate": 100.0}],
    )
    business.create_invoice(
        db._conn,
        job,
        "JOB-12",
        "2026-07-01",
        due_date="2026-07-10",
        lines=[{"description": "Site", "qty": 1, "rate": 50.0}],
    )
    business.create_invoice(
        db._conn,
        solo,
        "WH-1",
        "2026-01-01",
        due_date="2026-01-15",
        lines=[{"description": "Haul", "qty": 1, "rate": 25.0}],
    )
    data = aging.ar_aging_summary(db._conn, _AS_OF, interval=30, through=90)
    by_name = {g["name"]: g for g in data["groups"]}
    assert "Harbor Logistics" in by_name
    assert "Westside Hauling" in by_name
    harbor = by_name["Harbor Logistics"]
    assert harbor["has_children"] is True
    job_names = [j["name"] for j in harbor["jobs"]]
    assert "Site A" in job_names
    assert "Harbor Logistics - Other" in job_names
    other = next(j for j in harbor["jobs"] if j["kind"] == "other")
    assert other["amounts"]["1_30"] == pytest.approx(100.0)
    site = next(j for j in harbor["jobs"] if j["kind"] == "job")
    assert site["amounts"]["31_60"] == pytest.approx(50.0)
    assert harbor["amounts"]["total"] == pytest.approx(150.0)
    west = by_name["Westside Hauling"]
    assert west["has_children"] is False
    assert west["amounts"]["over_90"] == pytest.approx(25.0)
    assert data["grand_total"]["total"] == pytest.approx(175.0)
    for name in _FORBIDDEN:
        assert name not in str(data)


def test_parent_with_only_job_invoices(db: BankDatabase) -> None:
    parent = business.add_customer(db._conn, "Ridgeway Express")
    job = business.add_customer(db._conn, "Yard B", parent_customer_id=parent)
    business.create_invoice(
        db._conn,
        job,
        "YB-1",
        "2026-08-20",
        due_date="2026-09-20",
        lines=[{"description": "Haul", "qty": 1, "rate": 40.0}],
    )
    data = aging.ar_aging_summary(db._conn, _AS_OF)
    assert len(data["groups"]) == 1
    g = data["groups"][0]
    assert g["name"] == "Ridgeway Express"
    assert [j["name"] for j in g["jobs"]] == ["Yard B"]
    assert g["amounts"]["current"] == pytest.approx(40.0)
    assert not any(j["kind"] == "other" for j in g["jobs"])


def test_sort_by_total(db: BankDatabase) -> None:
    a = business.add_customer(db._conn, "Alpha Co")
    b = business.add_customer(db._conn, "Beta Co")
    business.create_invoice(
        db._conn,
        a,
        "A-1",
        "2026-08-01",
        due_date="2026-09-01",
        lines=[{"description": "x", "qty": 1, "rate": 10.0}],
    )
    business.create_invoice(
        db._conn,
        b,
        "B-1",
        "2026-08-01",
        due_date="2026-09-01",
        lines=[{"description": "x", "qty": 1, "rate": 90.0}],
    )
    data = aging.ar_aging_summary(db._conn, _AS_OF, sort_by="total")
    assert [g["name"] for g in data["groups"]] == ["Beta Co", "Alpha Co"]
