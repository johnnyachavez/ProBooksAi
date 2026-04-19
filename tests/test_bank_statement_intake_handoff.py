"""Bank Statement Intake — phase 2 hand-off-to-register tests.

Locks the contract that the explicit ``post_intake_rows_to_register`` writer:

* Creates a single ``(Statement intake)`` import batch per send.
* Inserts each valid row into ``bank_transactions`` under the chosen
  ``bank_account_id``.
* Reuses the existing fingerprint dedup (re-send is a no-op skip).
* Rejects rows missing ``txn_date`` or ``amount_signed`` as ``invalid``
  without touching the register.
* Returns ``inserted_indexes`` / ``invalid_indexes`` so the panel can
  evict the right rows from its persisted queue.
"""

from __future__ import annotations

from probooksai.bank_import import BankDatabase
from probooksai.bank_statement_intake import (
    SOURCE_TYPE_CSV,
    SOURCE_TYPE_TEXT,
    BankStatementIntakeRow,
)
from probooksai.bank_statement_intake_handoff import (
    STATEMENT_INTAKE_BATCH_FILENAME,
    HandoffResult,
    is_statement_intake_batch_filename,
    post_intake_rows_to_register,
)
from probooksai.extensions_schema import apply_extensions


def _open_db_with_account(tmp_path) -> tuple[BankDatabase, int]:
    db = BankDatabase(str(tmp_path / "handoff.db"))
    apply_extensions(db._conn)
    aid = db.add_bank_account(name="Operating Checking")
    return db, aid


def _row(
    *,
    date: str = "2026-01-02",
    desc: str = "Coffee Shop",
    amount: float = -4.50,
    debit: float | None = 4.50,
    credit: float | None = None,
    needs_review: bool = False,
    source_type: str = SOURCE_TYPE_CSV,
    source_ref: str = "jan.csv#L2",
    confidence: float = 1.0,
) -> BankStatementIntakeRow:
    return BankStatementIntakeRow(
        txn_date=date,
        description_raw=desc,
        debit=debit,
        credit=credit,
        amount_signed=amount,
        running_balance=None,
        source_type=source_type,
        source_ref=source_ref,
        confidence=confidence,
        needs_review=needs_review,
    )


def test_post_intake_rows_inserts_into_bank_transactions(tmp_path) -> None:
    db, aid = _open_db_with_account(tmp_path)
    try:
        rows = [
            _row(date="2026-01-02", desc="Coffee Shop", amount=-4.50, debit=4.50),
            _row(
                date="2026-01-03",
                desc="Payroll",
                amount=1500.0,
                debit=None,
                credit=1500.0,
                source_ref="jan.csv#L3",
            ),
        ]
        result = post_intake_rows_to_register(
            db, bank_account_id=aid, rows=rows, source_label="Jan stmt"
        )
        assert isinstance(result, HandoffResult)
        assert result.inserted == 2
        assert result.skipped_duplicates == 0
        assert result.invalid == 0
        assert result.batch_id is not None

        cur = db._conn.execute(
            "SELECT txn_date, description, amount, ref_number "
            "FROM bank_transactions WHERE bank_account_id = ? ORDER BY txn_date",
            (aid,),
        ).fetchall()
        assert len(cur) == 2
        assert cur[0]["txn_date"] == "2026-01-02"
        assert cur[0]["description"] == "Coffee Shop"
        assert cur[0]["amount"] == -4.50
        assert cur[0]["ref_number"] == "jan.csv#L2"
        assert cur[1]["amount"] == 1500.0
    finally:
        db.close()


def test_post_creates_one_statement_intake_batch_per_send(tmp_path) -> None:
    db, aid = _open_db_with_account(tmp_path)
    try:
        post_intake_rows_to_register(
            db,
            bank_account_id=aid,
            rows=[_row(source_ref="a#L1")],
            source_label="Run-1",
        )
        post_intake_rows_to_register(
            db,
            bank_account_id=aid,
            rows=[_row(date="2026-01-04", source_ref="a#L4")],
            source_label="Run-2",
        )
        cur = db._conn.execute(
            "SELECT filename FROM bank_import_batches "
            "WHERE bank_account_id = ? ORDER BY id",
            (aid,),
        ).fetchall()
        names = [r["filename"] for r in cur]
        assert names == [
            f"{STATEMENT_INTAKE_BATCH_FILENAME} Run-1",
            f"{STATEMENT_INTAKE_BATCH_FILENAME} Run-2",
        ]
        for n in names:
            assert is_statement_intake_batch_filename(n)
    finally:
        db.close()


def test_resending_same_row_is_skipped_by_dedup(tmp_path) -> None:
    db, aid = _open_db_with_account(tmp_path)
    try:
        rows = [_row(source_ref="dup#L1")]
        first = post_intake_rows_to_register(db, bank_account_id=aid, rows=rows)
        assert first.inserted == 1 and first.skipped_duplicates == 0
        # Second send: identical fingerprint → counted as skipped, not inserted
        # again, and the panel can still safely evict the row.
        second = post_intake_rows_to_register(db, bank_account_id=aid, rows=rows)
        assert second.inserted == 0
        assert second.skipped_duplicates == 1
        # ``inserted_indexes`` includes both inserted *and* deduped row
        # positions so the panel evicts duplicates from its queue too
        # (re-staging would just re-skip them).
        assert second.inserted_indexes == (0,)

        # Register only has one copy of the row.
        n = db._conn.execute(
            "SELECT COUNT(*) AS n FROM bank_transactions WHERE bank_account_id = ?",
            (aid,),
        ).fetchone()
        assert int(n["n"]) == 1
    finally:
        db.close()


def test_invalid_rows_are_reported_and_not_inserted(tmp_path) -> None:
    db, aid = _open_db_with_account(tmp_path)
    try:
        rows = [
            _row(source_ref="ok#L1"),
            _row(date="", source_ref="missing-date#L2"),  # invalid: no date
            _row(amount=None, debit=None, credit=None, source_ref="no-amt#L3"),
        ]
        result = post_intake_rows_to_register(db, bank_account_id=aid, rows=rows)
        assert result.inserted == 1
        assert result.invalid == 2
        assert sorted(result.invalid_indexes) == [1, 2]
        # The valid row's index (0) is reported as inserted; the two invalid
        # rows are NOT in inserted_indexes so the panel keeps them for fix-up.
        assert result.inserted_indexes == (0,)

        n = db._conn.execute(
            "SELECT COUNT(*) AS n FROM bank_transactions WHERE bank_account_id = ?",
            (aid,),
        ).fetchone()
        assert int(n["n"]) == 1
    finally:
        db.close()


def test_empty_rows_returns_zero_handoff_result(tmp_path) -> None:
    db, aid = _open_db_with_account(tmp_path)
    try:
        result = post_intake_rows_to_register(db, bank_account_id=aid, rows=[])
        assert result.inserted == 0
        assert result.skipped_duplicates == 0
        assert result.invalid == 0
        assert result.batch_id is None
        # No batch row should have been created for an empty send.
        n = db._conn.execute(
            "SELECT COUNT(*) AS n FROM bank_import_batches WHERE bank_account_id = ?",
            (aid,),
        ).fetchone()
        assert int(n["n"]) == 0
    finally:
        db.close()


def test_all_invalid_rows_does_not_create_a_batch(tmp_path) -> None:
    db, aid = _open_db_with_account(tmp_path)
    try:
        rows = [
            _row(date="", source_ref="a#L1"),
            _row(amount=None, debit=None, credit=None, source_ref="b#L2"),
        ]
        result = post_intake_rows_to_register(db, bank_account_id=aid, rows=rows)
        assert result.inserted == 0
        assert result.invalid == 2
        assert result.batch_id is None
        n = db._conn.execute(
            "SELECT COUNT(*) AS n FROM bank_import_batches WHERE bank_account_id = ?",
            (aid,),
        ).fetchone()
        assert int(n["n"]) == 0
    finally:
        db.close()


def test_handoff_does_not_classify_to_coa(tmp_path) -> None:
    """Hand-off invariant: when the staged row carries no chosen
    ``coa_account``, the register row must end up with ``coa_account == ''``.

    Phase-3 step 2 lets the bookkeeper pre-fill ``coa_account`` on a
    staged row from a rules-engine suggestion; that path is covered in
    :func:`test_handoff_passes_coa_account_through_when_set`. This test
    locks the *empty* path so we never silently auto-classify.
    """
    db, aid = _open_db_with_account(tmp_path)
    try:
        post_intake_rows_to_register(
            db, bank_account_id=aid, rows=[_row(source_ref="coa#L1")]
        )
        row = db._conn.execute(
            "SELECT coa_account, memo FROM bank_transactions WHERE bank_account_id = ?",
            (aid,),
        ).fetchone()
        assert row is not None
        assert row["coa_account"] == ""
        assert row["memo"] == ""
    finally:
        db.close()


def test_handoff_passes_coa_account_through_when_set(tmp_path) -> None:
    """Phase-3 step 2: when the staged row has a chosen ``coa_account``,
    the hand-off must carry it onto the register row verbatim."""
    db, aid = _open_db_with_account(tmp_path)
    try:
        row = _row(source_ref="coa-set#L1")
        row.coa_account = "5010 — Office Supplies"
        post_intake_rows_to_register(db, bank_account_id=aid, rows=[row])
        register_row = db._conn.execute(
            "SELECT coa_account FROM bank_transactions WHERE bank_account_id = ?",
            (aid,),
        ).fetchone()
        assert register_row is not None
        assert register_row["coa_account"] == "5010 — Office Supplies"
    finally:
        db.close()


def test_invalid_account_id_raises(tmp_path) -> None:
    db, _ = _open_db_with_account(tmp_path)
    try:
        try:
            post_intake_rows_to_register(
                db, bank_account_id=0, rows=[_row()]
            )
        except ValueError:
            return
        raise AssertionError("expected ValueError for zero account id")
    finally:
        db.close()


def test_default_source_label_yields_bare_batch_filename(tmp_path) -> None:
    db, aid = _open_db_with_account(tmp_path)
    try:
        post_intake_rows_to_register(
            db, bank_account_id=aid, rows=[_row(source_ref="bare#L1")]
        )
        row = db._conn.execute(
            "SELECT filename FROM bank_import_batches WHERE bank_account_id = ?",
            (aid,),
        ).fetchone()
        assert row is not None
        assert row["filename"] == STATEMENT_INTAKE_BATCH_FILENAME
    finally:
        db.close()


def test_unparseable_date_string_is_treated_as_invalid(tmp_path) -> None:
    db, aid = _open_db_with_account(tmp_path)
    try:
        rows = [_row(date="not-a-date", source_ref="bad#L1")]
        result = post_intake_rows_to_register(db, bank_account_id=aid, rows=rows)
        assert result.inserted == 0
        assert result.invalid == 1
        assert result.batch_id is None
    finally:
        db.close()
