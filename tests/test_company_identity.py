"""Company identity keys and invoice header block."""

from __future__ import annotations

from probooksai.bank_import import BankDatabase
from probooksai.company_identity import (
    KEY_COMPANY_NAME,
    company_identity_plain_block,
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
