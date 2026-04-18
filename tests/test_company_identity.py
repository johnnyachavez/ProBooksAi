"""Company identity keys and invoice header block."""

from __future__ import annotations

from probooksai.bank_import import BankDatabase
from probooksai.company_identity import (
    BUSINESS_TYPES,
    KEY_BUSINESS_TYPE,
    KEY_COMPANY_NAME,
    KEY_TAX_STRUCTURE,
    TAX_STRUCTURES,
    company_identity_plain_block,
    company_identity_print_fields,
    get_company_identity,
    is_company_setup_complete,
    save_company_identity,
)
from probooksai.extensions_schema import apply_extensions


def test_save_and_plain_block_roundtrip(tmp_path) -> None:
    path = str(tmp_path / "co.db")
    db = BankDatabase(path)
    try:
        apply_extensions(db._conn)
        save_company_identity(
            db._conn,
            name="Acme LLC",
            address="1 Main St\nSpringfield, ST 00001",
            phone="555-0100",
            email="billing@acme.example",
            tax_id="12-3456789",
        )
        plain = company_identity_plain_block(db._conn)
        assert "Acme LLC" in plain
        assert "1 Main St" in plain
        assert "555-0100" in plain
        assert "billing@acme.example" in plain
        assert "12-3456789" in plain
        row = db._conn.execute(
            "SELECT value FROM company_settings WHERE key = ?", (KEY_COMPANY_NAME,)
        ).fetchone()
        assert row is not None and row["value"] == "Acme LLC"
    finally:
        db.close()


def test_company_identity_keys_documented() -> None:
    assert KEY_COMPANY_NAME == "company_name"


def test_save_company_identity_persists_business_type_and_tax_structure(tmp_path) -> None:
    """New Company wizard fields round-trip through save → ``get_company_identity``."""
    path = str(tmp_path / "co_extra.db")
    db = BankDatabase(path)
    try:
        apply_extensions(db._conn)
        save_company_identity(
            db._conn,
            name="ExtraCo",
            address="2 Pine St",
            phone="555-2000",
            email="hi@extraco.example",
            tax_id="98-7654321",
            business_type="LLC",
            tax_structure="LLC – Single-member (disregarded)",
        )
        identity = get_company_identity(db._conn)
        assert identity["name"] == "ExtraCo"
        assert identity["business_type"] == "LLC"
        assert identity["tax_structure"] == "LLC – Single-member (disregarded)"
        assert identity["tax_id"] == "98-7654321"
        bt_row = db._conn.execute(
            "SELECT value FROM company_settings WHERE key = ?", (KEY_BUSINESS_TYPE,)
        ).fetchone()
        ts_row = db._conn.execute(
            "SELECT value FROM company_settings WHERE key = ?", (KEY_TAX_STRUCTURE,)
        ).fetchone()
        assert bt_row is not None and bt_row["value"] == "LLC"
        assert ts_row is not None and ts_row["value"].startswith("LLC – Single-member")
    finally:
        db.close()


def test_save_company_identity_back_compat_without_new_kwargs(tmp_path) -> None:
    """Legacy callers that omit ``business_type`` / ``tax_structure`` still work."""
    path = str(tmp_path / "co_compat.db")
    db = BankDatabase(path)
    try:
        apply_extensions(db._conn)
        save_company_identity(
            db._conn,
            name="LegacyCo",
            address="",
            phone="",
            email="",
            tax_id="",
        )
        identity = get_company_identity(db._conn)
        assert identity["name"] == "LegacyCo"
        assert identity["business_type"] == ""
        assert identity["tax_structure"] == ""
    finally:
        db.close()


def test_is_company_setup_complete_requires_name_business_type_tax_structure(tmp_path) -> None:
    """Setup gate is satisfied only after Name + Business Type + Tax Structure are saved."""
    path = str(tmp_path / "co_gate.db")
    db = BankDatabase(path)
    try:
        apply_extensions(db._conn)
        assert is_company_setup_complete(db._conn) is False
        save_company_identity(db._conn, name="OnlyName")
        assert is_company_setup_complete(db._conn) is False, (
            "Name alone must not unlock the app — wizard requires business + tax fields."
        )
        save_company_identity(
            db._conn, name="OnlyName", business_type="LLC"
        )
        assert is_company_setup_complete(db._conn) is False
        save_company_identity(
            db._conn,
            name="OnlyName",
            business_type="LLC",
            tax_structure="LLC – Multi-member (1065)",
        )
        assert is_company_setup_complete(db._conn) is True
    finally:
        db.close()


def test_company_identity_business_type_and_tax_structure_options_have_expected_choices() -> None:
    """The wizard's combo options include the common US business + tax structures."""
    assert "LLC" in BUSINESS_TYPES
    assert "S Corporation" in BUSINESS_TYPES
    assert "Sole Proprietorship" in BUSINESS_TYPES
    assert any("Schedule C" in t for t in TAX_STRUCTURES)
    assert any("1120-S" in t for t in TAX_STRUCTURES)
    assert any("Single-member" in t for t in TAX_STRUCTURES)


def test_company_identity_print_fields_matches_saved_identity(tmp_path) -> None:
    path = str(tmp_path / "co_print.db")
    db = BankDatabase(path)
    try:
        apply_extensions(db._conn)
        save_company_identity(
            db._conn,
            name="PrintCo",
            address="9 Oak Rd",
            phone="555-9999",
            email="hi@printco.example",
            tax_id="XX-1",
        )
        d = company_identity_print_fields(db._conn)
        assert d["name"] == "PrintCo"
        assert d["address"] == "9 Oak Rd"
        assert d["phone"] == "555-9999"
        assert d["email"] == "hi@printco.example"
        assert d["tax_id"] == "XX-1"
    finally:
        db.close()
