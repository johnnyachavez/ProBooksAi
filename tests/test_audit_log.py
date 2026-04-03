"""Audit log CSV export."""

from __future__ import annotations

import csv

from probooksai.audit_log import write_audit_csv


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
    text = path.read_text(encoding="utf-8")
    assert "bank_transaction" in text
    assert "42" in text
    with path.open(encoding="utf-8", newline="") as f:
        r = list(csv.reader(f))
    assert len(r) == 2
    assert r[0][0] == "changed_at"
    assert r[1][0].startswith("2024-06-01")
