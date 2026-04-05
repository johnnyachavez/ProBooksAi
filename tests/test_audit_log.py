"""Audit log CSV export."""

from __future__ import annotations

import csv

from probooksai.audit_log import audit_field_display_label, write_audit_csv


def test_audit_field_display_label_maps_bank_match_link():
    assert audit_field_display_label("bank_match_link") == "Payment / document link"
    assert audit_field_display_label("memo") == "Memo"
    assert audit_field_display_label("coa_account") == "Category (COA)"
    assert audit_field_display_label("is_reconciled") == "Batch reconciled"
    assert audit_field_display_label("account_name") == "Account name"
    assert audit_field_display_label("unknown_custom_field") == "unknown_custom_field"
    assert audit_field_display_label("") == ""
    assert audit_field_display_label(None) == ""


def test_write_audit_csv_roundtrip(tmp_path):
    rows = [
        {
            "changed_at": "2024-06-01T15:30:00+00:00",
            "entity_type": "bank_transaction",
            "entity_id": 42,
            "field": "memo",
            "old_value": "a",
            "new_value": "b",
        }
    ]
    path = tmp_path / "audit.csv"
    n = write_audit_csv(str(path), rows)
    assert n == 1
    text = path.read_text(encoding="utf-8-sig")
    assert "bank_transaction" in text
    assert "42" in text
    with path.open(encoding="utf-8-sig", newline="") as f:
        r = list(csv.reader(f))
    assert len(r) == 2
    assert r[0][0] == "changed_at"
    assert r[1][0].startswith("2024-06-01")
