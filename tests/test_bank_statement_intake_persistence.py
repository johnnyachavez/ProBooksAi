"""Bank Statement Intake — phase 2 persisted queue tests.

Locks the contract that the review queue survives an app restart:

* Schema migration v7 creates ``bank_statement_intake_queue``.
* ``replace_intake_queue`` is full-replace (so panel snapshots stay
  authoritative), preserves order, and round-trips every field of
  :class:`probooksai.bank_statement_intake.BankStatementIntakeRow`.
* ``load_intake_queue`` reads back the same dataclass shape.
* Empty replace clears the queue.
* ``delete_intake_queue_rows`` removes a subset by primary key.
"""

from __future__ import annotations

from probooksai.bank_import import BankDatabase
from probooksai.bank_statement_intake import (
    SOURCE_TYPE_CSV,
    SOURCE_TYPE_PDF,
    SOURCE_TYPE_TEXT,
    BankStatementIntakeRow,
)
from probooksai.bank_statement_intake_persistence import (
    QUEUE_TABLE,
    clear_intake_queue,
    count_intake_queue,
    delete_intake_queue_rows,
    load_intake_queue,
    load_intake_queue_with_ids,
    replace_intake_queue,
)
from probooksai.extensions_schema import apply_extensions


def _open_db(tmp_path) -> BankDatabase:
    db = BankDatabase(str(tmp_path / "intake-queue.db"))
    apply_extensions(db._conn)
    return db


def test_extension_schema_v7_creates_intake_queue_table(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        row = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (QUEUE_TABLE,),
        ).fetchone()
        assert row is not None
        # Schema version is bumped past v6 so the migration ran.
        ver = db._conn.execute(
            "SELECT version FROM extension_schema_version WHERE id = 1"
        ).fetchone()
        assert ver is not None and int(ver["version"]) >= 7
    finally:
        db.close()


def test_replace_and_load_round_trip_preserves_every_field(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        rows = [
            BankStatementIntakeRow(
                txn_date="2026-01-02",
                description_raw="Coffee Shop",
                debit=4.50,
                credit=None,
                amount_signed=-4.50,
                running_balance=995.50,
                source_type=SOURCE_TYPE_CSV,
                source_ref="jan.csv#L2",
                confidence=1.0,
                needs_review=False,
            ),
            BankStatementIntakeRow(
                txn_date="2026-01-03",
                description_raw="Payroll Deposit",
                debit=None,
                credit=1500.00,
                amount_signed=1500.00,
                running_balance=2495.50,
                source_type=SOURCE_TYPE_PDF,
                source_ref="acct.pdf#L7",
                confidence=0.85,
                needs_review=True,
            ),
        ]
        n = replace_intake_queue(db._conn, rows)
        assert n == 2
        loaded = load_intake_queue(db._conn)
        assert len(loaded) == 2
        for original, back in zip(rows, loaded):
            assert back.txn_date == original.txn_date
            assert back.description_raw == original.description_raw
            assert back.debit == original.debit
            assert back.credit == original.credit
            assert back.amount_signed == original.amount_signed
            assert back.running_balance == original.running_balance
            assert back.source_type == original.source_type
            assert back.source_ref == original.source_ref
            assert back.confidence == original.confidence
            assert back.needs_review == original.needs_review
    finally:
        db.close()


def test_replace_with_empty_iterable_clears_existing_queue(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        replace_intake_queue(
            db._conn,
            [
                BankStatementIntakeRow(
                    txn_date="2026-01-04",
                    description_raw="X",
                    amount_signed=-1.00,
                    debit=1.00,
                    source_type=SOURCE_TYPE_TEXT,
                    source_ref="L1",
                    confidence=1.0,
                    needs_review=False,
                )
            ],
        )
        assert count_intake_queue(db._conn) == 1
        replace_intake_queue(db._conn, [])
        assert count_intake_queue(db._conn) == 0
        assert load_intake_queue(db._conn) == []
    finally:
        db.close()


def test_replace_preserves_order_via_sort_order(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        rows = [
            BankStatementIntakeRow(
                txn_date="2026-01-05",
                description_raw=f"row-{i}",
                amount_signed=float(-i),
                debit=float(i),
                source_type=SOURCE_TYPE_TEXT,
                source_ref=f"L{i}",
                confidence=1.0,
                needs_review=False,
            )
            for i in range(1, 6)
        ]
        replace_intake_queue(db._conn, rows)
        loaded = load_intake_queue(db._conn)
        assert [r.description_raw for r in loaded] == [
            f"row-{i}" for i in range(1, 6)
        ]
    finally:
        db.close()


def test_delete_intake_queue_rows_removes_only_selected_ids(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        rows = [
            BankStatementIntakeRow(
                txn_date="2026-01-06",
                description_raw=f"row-{i}",
                amount_signed=-1.0,
                debit=1.0,
                source_type=SOURCE_TYPE_TEXT,
                source_ref=f"L{i}",
                confidence=1.0,
                needs_review=False,
            )
            for i in range(3)
        ]
        replace_intake_queue(db._conn, rows)
        with_ids = load_intake_queue_with_ids(db._conn)
        assert len(with_ids) == 3
        first_id = with_ids[0][0]
        last_id = with_ids[-1][0]

        deleted = delete_intake_queue_rows(db._conn, [first_id, last_id])
        assert deleted == 2
        remaining = load_intake_queue(db._conn)
        assert len(remaining) == 1
        assert remaining[0].description_raw == "row-1"
    finally:
        db.close()


def test_clear_intake_queue_removes_everything(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        replace_intake_queue(
            db._conn,
            [
                BankStatementIntakeRow(
                    txn_date="2026-01-07",
                    description_raw="x",
                    amount_signed=-1.0,
                    debit=1.0,
                    source_type=SOURCE_TYPE_TEXT,
                    source_ref="L1",
                    confidence=1.0,
                    needs_review=False,
                )
            ],
        )
        assert count_intake_queue(db._conn) == 1
        deleted = clear_intake_queue(db._conn)
        assert deleted == 1
        assert count_intake_queue(db._conn) == 0
    finally:
        db.close()


def test_delete_with_empty_id_list_is_a_no_op(tmp_path) -> None:
    db = _open_db(tmp_path)
    try:
        deleted = delete_intake_queue_rows(db._conn, [])
        assert deleted == 0
    finally:
        db.close()
