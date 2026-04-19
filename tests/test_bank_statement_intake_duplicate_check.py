"""Bank Statement Intake — phase 3 step 1: duplicate-against-register tests.

Locks the contract that ``find_register_duplicates``:

* Matches only rows on the **same** ``bank_account_id`` and within the
  configured date window.
* Treats sign as significant (a positive credit never collides with a
  negative debit of equal magnitude).
* Classifies same-day same-description hits as ``"exact"``.
* Returns nothing for unparseable dates / missing amounts.
* Never writes to ``bank_transactions``.
"""

from __future__ import annotations

from probooksai.bank_import import BankDatabase
from probooksai.bank_statement_intake import (
    SOURCE_TYPE_CSV,
    BankStatementIntakeRow,
)
from probooksai.bank_statement_intake_duplicate_check import (
    DEFAULT_DATE_WINDOW_DAYS,
    RegisterDuplicateMatch,
    find_register_duplicates,
)
from probooksai.extensions_schema import apply_extensions


def _open_db_with_account(tmp_path, *, name: str = "Operating") -> tuple[BankDatabase, int]:
    db = BankDatabase(str(tmp_path / "dupcheck.db"))
    apply_extensions(db._conn)
    aid = db.add_bank_account(name=name)
    return db, aid


def _seed_register(
    db: BankDatabase,
    account_id: int,
    *,
    txn_date: str,
    description: str,
    amount: float,
) -> int:
    """Insert one register row and return its id (uses dedicated batch)."""
    batch_id = db.create_batch(
        bank_account_id=account_id,
        filename="(dup-check seed)",
    )
    payload = [
        {
            "txn_date": txn_date,
            "description": description,
            "amount": amount,
            "balance": None,
            "tag_or_check": None,
            "split_label": None,
            "memo": "",
            "extras": {},
        }
    ]
    db.import_transactions(
        batch_id=batch_id,
        bank_account_id=account_id,
        rows=payload,
    )
    row = db._conn.execute(
        "SELECT id FROM bank_transactions WHERE bank_account_id = ? "
        "ORDER BY id DESC LIMIT 1",
        (account_id,),
    ).fetchone()
    return int(row["id"])


def _row(
    *,
    date: str,
    desc: str,
    amount: float,
) -> BankStatementIntakeRow:
    debit = -amount if amount < 0 else None
    credit = amount if amount > 0 else None
    return BankStatementIntakeRow(
        txn_date=date,
        description_raw=desc,
        debit=debit,
        credit=credit,
        amount_signed=amount,
        running_balance=None,
        source_type=SOURCE_TYPE_CSV,
        source_ref="seed.csv#L1",
        confidence=1.0,
        needs_review=False,
    )


def test_same_day_same_description_same_amount_is_exact(tmp_path) -> None:
    db, aid = _open_db_with_account(tmp_path)
    try:
        rid = _seed_register(
            db, aid, txn_date="2026-02-10",
            description="Coffee Shop", amount=-4.50,
        )
        staged = [_row(date="2026-02-10", desc="Coffee Shop", amount=-4.50)]
        out = find_register_duplicates(db, bank_account_id=aid, rows=staged)
        assert 0 in out
        match = out[0]
        assert isinstance(match, RegisterDuplicateMatch)
        assert match.register_txn_id == rid
        assert match.match_strength == "exact"
    finally:
        db.close()


def test_amount_match_within_window_but_different_desc_is_weak(tmp_path) -> None:
    db, aid = _open_db_with_account(tmp_path)
    try:
        _seed_register(
            db, aid, txn_date="2026-02-10",
            description="Some Cafe", amount=-4.50,
        )
        staged = [_row(date="2026-02-12", desc="Coffee Shop", amount=-4.50)]
        out = find_register_duplicates(db, bank_account_id=aid, rows=staged)
        assert 0 in out
        assert out[0].match_strength == "weak"
    finally:
        db.close()


def test_one_day_apart_with_token_overlap_is_strong(tmp_path) -> None:
    db, aid = _open_db_with_account(tmp_path)
    try:
        _seed_register(
            db, aid, txn_date="2026-02-10",
            description="Coffee Shop Downtown", amount=-4.50,
        )
        staged = [_row(date="2026-02-11", desc="Coffee Shop Mainst", amount=-4.50)]
        out = find_register_duplicates(db, bank_account_id=aid, rows=staged)
        assert 0 in out
        assert out[0].match_strength == "strong"
    finally:
        db.close()


def test_amount_outside_epsilon_is_not_a_match(tmp_path) -> None:
    db, aid = _open_db_with_account(tmp_path)
    try:
        _seed_register(
            db, aid, txn_date="2026-02-10",
            description="Coffee Shop", amount=-4.50,
        )
        staged = [_row(date="2026-02-10", desc="Coffee Shop", amount=-4.51)]
        out = find_register_duplicates(db, bank_account_id=aid, rows=staged)
        assert out == {}
    finally:
        db.close()


def test_opposite_sign_is_not_a_match(tmp_path) -> None:
    db, aid = _open_db_with_account(tmp_path)
    try:
        _seed_register(
            db, aid, txn_date="2026-02-10",
            description="Coffee Shop", amount=-4.50,
        )
        staged = [_row(date="2026-02-10", desc="Coffee Shop", amount=4.50)]
        out = find_register_duplicates(db, bank_account_id=aid, rows=staged)
        assert out == {}
    finally:
        db.close()


def test_outside_date_window_is_not_a_match(tmp_path) -> None:
    db, aid = _open_db_with_account(tmp_path)
    try:
        _seed_register(
            db, aid, txn_date="2026-02-10",
            description="Coffee Shop", amount=-4.50,
        )
        staged = [_row(date="2026-02-20", desc="Coffee Shop", amount=-4.50)]
        out = find_register_duplicates(
            db, bank_account_id=aid, rows=staged,
            date_window_days=DEFAULT_DATE_WINDOW_DAYS,
        )
        assert out == {}
    finally:
        db.close()


def test_other_account_rows_are_ignored(tmp_path) -> None:
    db, aid = _open_db_with_account(tmp_path, name="Operating")
    try:
        other_aid = db.add_bank_account(name="Savings")
        _seed_register(
            db, other_aid, txn_date="2026-02-10",
            description="Coffee Shop", amount=-4.50,
        )
        staged = [_row(date="2026-02-10", desc="Coffee Shop", amount=-4.50)]
        out = find_register_duplicates(db, bank_account_id=aid, rows=staged)
        assert out == {}
    finally:
        db.close()


def test_unparseable_date_is_skipped(tmp_path) -> None:
    db, aid = _open_db_with_account(tmp_path)
    try:
        _seed_register(
            db, aid, txn_date="2026-02-10",
            description="Coffee Shop", amount=-4.50,
        )
        staged = [_row(date="not-a-date", desc="Coffee Shop", amount=-4.50)]
        out = find_register_duplicates(db, bank_account_id=aid, rows=staged)
        assert out == {}
    finally:
        db.close()


def test_missing_amount_signed_is_skipped(tmp_path) -> None:
    db, aid = _open_db_with_account(tmp_path)
    try:
        _seed_register(
            db, aid, txn_date="2026-02-10",
            description="Coffee Shop", amount=-4.50,
        )
        staged = [
            BankStatementIntakeRow(
                txn_date="2026-02-10",
                description_raw="Coffee Shop",
                debit=None,
                credit=None,
                amount_signed=None,
                running_balance=None,
                source_type=SOURCE_TYPE_CSV,
                source_ref="x.csv#L1",
                confidence=0.0,
                needs_review=True,
            )
        ]
        out = find_register_duplicates(db, bank_account_id=aid, rows=staged)
        assert out == {}
    finally:
        db.close()


def test_empty_rows_returns_empty_dict(tmp_path) -> None:
    db, aid = _open_db_with_account(tmp_path)
    try:
        out = find_register_duplicates(db, bank_account_id=aid, rows=[])
        assert out == {}
    finally:
        db.close()


def test_finds_strongest_match_when_multiple_register_rows_match_amount(tmp_path) -> None:
    db, aid = _open_db_with_account(tmp_path)
    try:
        _seed_register(
            db, aid, txn_date="2026-02-08",
            description="Generic", amount=-4.50,
        )
        rid_exact = _seed_register(
            db, aid, txn_date="2026-02-10",
            description="Coffee Shop", amount=-4.50,
        )
        staged = [_row(date="2026-02-10", desc="Coffee Shop", amount=-4.50)]
        out = find_register_duplicates(db, bank_account_id=aid, rows=staged)
        assert 0 in out
        assert out[0].match_strength == "exact"
        assert out[0].register_txn_id == rid_exact
    finally:
        db.close()


def test_dup_check_does_not_modify_register(tmp_path) -> None:
    db, aid = _open_db_with_account(tmp_path)
    try:
        _seed_register(
            db, aid, txn_date="2026-02-10",
            description="Coffee Shop", amount=-4.50,
        )
        before = db._conn.execute(
            "SELECT COUNT(*) AS c FROM bank_transactions"
        ).fetchone()["c"]
        staged = [_row(date="2026-02-10", desc="Coffee Shop", amount=-4.50)]
        find_register_duplicates(db, bank_account_id=aid, rows=staged)
        after = db._conn.execute(
            "SELECT COUNT(*) AS c FROM bank_transactions"
        ).fetchone()["c"]
        assert before == after
    finally:
        db.close()


def test_invalid_account_id_raises(tmp_path) -> None:
    db, _ = _open_db_with_account(tmp_path)
    try:
        try:
            find_register_duplicates(
                db,
                bank_account_id=0,
                rows=[_row(date="2026-02-10", desc="x", amount=-1.0)],
            )
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError for invalid account_id")
    finally:
        db.close()


def test_display_label_includes_id_date_and_strength() -> None:
    m = RegisterDuplicateMatch(
        register_txn_id=42,
        register_txn_date="2026-02-10",
        register_amount=-4.50,
        register_description="Coffee Shop",
        match_strength="exact",
    )
    label = m.display_label()
    assert "42" in label
    assert "2026-02-10" in label
    assert "exact" in label
