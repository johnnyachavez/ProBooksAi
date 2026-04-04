"""Categorization rules CSV export and import."""

from __future__ import annotations

import csv

import pytest

from probooksai.bank_import import BankDatabase
from probooksai.extensions_schema import apply_extensions
from probooksai import rules_engine
from probooksai.rules_engine import (
    import_rules_replace,
    read_rules_csv,
    validated_rule_tuples,
    write_rules_csv,
)


@pytest.fixture
def rules_db(tmp_path):
    b = BankDatabase(db_path=str(tmp_path / "rules_imp.db"))
    apply_extensions(b._conn)
    yield b
    b.close()


def test_write_rules_csv(tmp_path):
    rows = [
        {
            "pattern": "AMAZON",
            "coa_account": "5010 – Supplies",
            "priority": 10,
            "is_active": 1,
        }
    ]
    p = tmp_path / "rules.csv"
    n = write_rules_csv(str(p), rows)
    assert n == 1
    with p.open(encoding="utf-8-sig", newline="") as f:
        r = list(csv.reader(f))
    assert r[0] == ["pattern", "coa_account", "priority", "is_active"]
    assert r[1][0] == "AMAZON"
    assert r[1][1] == "5010 – Supplies"
    assert r[1][2] == "10"
    assert r[1][3] == "1"


def test_write_rules_csv_empty(tmp_path):
    p = tmp_path / "empty.csv"
    n = write_rules_csv(str(p), [])
    assert n == 0
    text = p.read_text(encoding="utf-8-sig")
    assert "pattern" in text


def test_read_rules_csv_accepts_coa_alias(tmp_path):
    p = tmp_path / "in.csv"
    p.write_text(
        "pattern,coa,priority,is_active\n"
        "FOO,1000 – A,3,1\n",
        encoding="utf-8",
    )
    rows = read_rules_csv(str(p))
    assert len(rows) == 1
    assert rows[0]["pattern"] == "FOO"
    assert rows[0]["coa_account"] == "1000 – A"


def test_import_replace_roundtrip(rules_db, tmp_path):
    rules_engine.add_rule(rules_db._conn, "KEEP", "2000 – B", priority=7)
    rules_engine.add_rule(rules_db._conn, "DROP", "3000 – C", priority=1)
    p = tmp_path / "rules.csv"
    write_rules_csv(str(p), rules_engine.list_rules(rules_db._conn))
    rules_engine.add_rule(rules_db._conn, "EXTRA", "9999 – Z", priority=99)
    import_rules_replace(rules_db._conn, str(p))
    rows = rules_engine.list_rules(rules_db._conn)
    patterns = {r["pattern"] for r in rows}
    assert patterns == {"KEEP", "DROP"}
    assert "EXTRA" not in patterns


def test_import_replace_empty_file_aborts(rules_db, tmp_path):
    rules_engine.add_rule(rules_db._conn, "ONLY", "1000 – X", priority=1)
    p = tmp_path / "bad.csv"
    p.write_text("pattern,coa_account,priority,is_active\n", encoding="utf-8")
    with pytest.raises(ValueError, match="No valid rules"):
        import_rules_replace(rules_db._conn, str(p))
    assert len(rules_engine.list_rules(rules_db._conn)) == 1


def test_validated_rule_tuples_skips_blank():
    assert validated_rule_tuples([{"pattern": "", "coa_account": "x"}]) == []
    assert len(validated_rule_tuples([{"pattern": "a", "coa_account": "b"}])) == 1
