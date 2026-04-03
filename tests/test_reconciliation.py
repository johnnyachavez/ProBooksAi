"""
Tests for bank reconciliation logic in probooksai.bank_import.
"""

from __future__ import annotations

import pytest

from probooksai.bank_import import (
    BankDatabase,
    RECONCILE_TOLERANCE,
    compute_reconciliation,
    parse_csv,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    bdb = BankDatabase(db_path=str(tmp_path / "recon_test.db"))
    yield bdb
    bdb.close()


def _make_txns(rows: list[tuple]) -> list[dict]:
    """Build a list of txn dicts from (date, amount) tuples."""
    return [{"txn_date": d, "amount": a, "description": ""} for d, a in rows]


# ===========================================================================
# compute_reconciliation (pure function)
# ===========================================================================

class TestComputeReconciliation:
    def test_zero_difference_can_reconcile(self):
        txns = _make_txns([("2024-01-05", -4.50), ("2024-01-10", 2500.00)])
        result = compute_reconciliation(txns, beginning_balance=1000.0, ending_balance=3495.50)
        assert result["difference"] == pytest.approx(0.0)
        assert result["can_reconcile"] is True

    def test_nonzero_difference_cannot_reconcile(self):
        txns = _make_txns([("2024-01-05", -4.50)])
        result = compute_reconciliation(txns, beginning_balance=1000.0, ending_balance=999.00)
        assert result["difference"] != pytest.approx(0.0)
        assert result["can_reconcile"] is False

    def test_date_range_filter_start(self):
        txns = _make_txns([
            ("2024-01-01", 100.0),
            ("2024-01-15", 200.0),
            ("2024-02-01", 300.0),
        ])
        result = compute_reconciliation(
            txns,
            beginning_balance=0.0,
            ending_balance=300.0,
            statement_start="2024-01-15",
        )
        # Only 200 + 300 = 500 counted; 100 excluded
        assert result["sum_of_amounts"] == pytest.approx(500.0)
        assert result["transaction_count"] == 2

    def test_date_range_filter_end(self):
        txns = _make_txns([
            ("2024-01-01", 100.0),
            ("2024-01-15", 200.0),
            ("2024-02-01", 300.0),
        ])
        result = compute_reconciliation(
            txns,
            beginning_balance=0.0,
            ending_balance=300.0,
            statement_end="2024-01-31",
        )
        # Only 100 + 200 = 300 counted
        assert result["sum_of_amounts"] == pytest.approx(300.0)
        assert result["transaction_count"] == 2

    def test_date_range_both_bounds(self):
        txns = _make_txns([
            ("2024-01-01", 100.0),
            ("2024-01-15", 200.0),
            ("2024-02-01", 300.0),
        ])
        result = compute_reconciliation(
            txns,
            beginning_balance=0.0,
            ending_balance=200.0,
            statement_start="2024-01-10",
            statement_end="2024-01-31",
        )
        assert result["transaction_count"] == 1
        assert result["sum_of_amounts"] == pytest.approx(200.0)
        assert result["can_reconcile"] is True

    def test_no_transactions_in_range(self):
        txns = _make_txns([("2024-03-01", 500.0)])
        result = compute_reconciliation(
            txns,
            beginning_balance=1000.0,
            ending_balance=1000.0,
            statement_start="2024-01-01",
            statement_end="2024-01-31",
        )
        assert result["transaction_count"] == 0
        assert result["sum_of_amounts"] == pytest.approx(0.0)
        assert result["computed_ending"] == pytest.approx(1000.0)
        assert result["can_reconcile"] is True

    def test_outflows_negative_sign(self):
        txns = _make_txns([("2024-01-05", -100.0)])
        result = compute_reconciliation(txns, 500.0, 400.0)
        assert result["difference"] == pytest.approx(0.0)
        assert result["can_reconcile"] is True

    def test_mixed_signs(self):
        txns = _make_txns([
            ("2024-01-05", -50.0),
            ("2024-01-10", 200.0),
            ("2024-01-15", -30.0),
        ])
        result = compute_reconciliation(txns, beginning_balance=100.0, ending_balance=220.0)
        assert result["sum_of_amounts"] == pytest.approx(120.0)
        assert result["computed_ending"] == pytest.approx(220.0)
        assert result["difference"] == pytest.approx(0.0)
        assert result["can_reconcile"] is True

    def test_computed_ending_formula(self):
        txns = _make_txns([("2024-01-01", 500.0), ("2024-01-15", -200.0)])
        result = compute_reconciliation(txns, beginning_balance=1000.0, ending_balance=9999.0)
        assert result["computed_ending"] == pytest.approx(1000.0 + 500.0 - 200.0)
        assert result["difference"] == pytest.approx(1300.0 - 9999.0)

    def test_odd_statement_range(self):
        """Supports non-month-aligned statement periods."""
        txns = _make_txns([
            ("2024-01-15", 400.0),
            ("2024-02-14", -100.0),
        ])
        result = compute_reconciliation(
            txns,
            beginning_balance=500.0,
            ending_balance=800.0,
            statement_start="2024-01-15",
            statement_end="2024-02-14",
        )
        assert result["can_reconcile"] is True

    def test_returns_all_keys(self):
        result = compute_reconciliation([], 0.0, 0.0)
        for key in (
            "transaction_count",
            "sum_of_amounts",
            "computed_ending",
            "difference",
            "can_reconcile",
            "tolerance_used",
        ):
            assert key in result

    def test_custom_tolerance_allows_small_difference(self):
        txns = _make_txns([("2024-01-05", 999.98)])
        r0 = compute_reconciliation(
            txns, beginning_balance=1000.0, ending_balance=1999.99
        )
        assert r0["difference"] == pytest.approx(-0.01)
        assert r0["can_reconcile"] is False
        assert r0["tolerance_used"] == pytest.approx(0.0)
        r1 = compute_reconciliation(
            txns,
            beginning_balance=1000.0,
            ending_balance=1999.99,
            tolerance=0.05,
        )
        assert r1["can_reconcile"] is True
        assert r1["tolerance_used"] == pytest.approx(0.05)

    def test_rounding_to_two_decimal_places(self):
        txns = _make_txns([("2024-01-01", 0.1), ("2024-01-02", 0.2)])
        result = compute_reconciliation(txns, 0.0, 0.3)
        # 0.1 + 0.2 in float can be 0.30000000000000004 without rounding
        assert result["difference"] == pytest.approx(0.0, abs=1e-9)
        assert result["can_reconcile"] is True


# ===========================================================================
# BankDatabase.reconcile_batch
# ===========================================================================

class TestReconcileBatch:
    def _setup_batch(self, db, beginning_balance, ending_balance,
                     statement_start="2024-01-01", statement_end="2024-01-31"):
        aid = db.add_bank_account("Recon Account")
        bid = db.create_batch(
            aid,
            statement_start=statement_start,
            statement_end=statement_end,
            beginning_balance=beginning_balance,
            ending_balance=ending_balance,
        )
        return aid, bid

    def test_reconcile_marks_batch_when_zero_diff(self, db):
        aid, bid = self._setup_batch(db, 1000.0, 3290.50)
        csv_content = (
            "Date,Description,Amount\n"
            "2024-01-05,Coffee,-4.50\n"
            "2024-01-10,Paycheck,2500.00\n"
            "2024-01-15,Grocery,-85.00\n"
            "2024-01-20,Electric,-120.00\n"
        )
        rows = parse_csv(csv_content, "Date", "Amount", "Description")
        db.import_transactions(bid, aid, rows)
        result = db.reconcile_batch(bid)
        assert result["can_reconcile"] is True
        assert result["reconciled"] is True
        assert db.get_batch(bid)["is_reconciled"] == 1

    def test_reconcile_does_not_mark_when_nonzero_diff(self, db):
        aid, bid = self._setup_batch(db, 1000.0, 9999.0)
        csv_content = "Date,Description,Amount\n2024-01-05,Coffee,-4.50\n"
        rows = parse_csv(csv_content, "Date", "Amount", "Description")
        db.import_transactions(bid, aid, rows)
        result = db.reconcile_batch(bid)
        assert result["can_reconcile"] is False
        assert result["reconciled"] is False
        assert db.get_batch(bid)["is_reconciled"] == 0

    def test_reconcile_marks_batch_within_custom_tolerance(self, db):
        aid, bid = self._setup_batch(db, 1000.0, 1999.99)
        db.import_transactions(
            bid,
            aid,
            [
                {
                    "txn_date": "2024-01-05",
                    "amount": 999.98,
                    "description": "In",
                    "ref_number": "",
                }
            ],
        )
        r0 = db.reconcile_batch(bid)
        assert r0["difference"] == pytest.approx(-0.01)
        assert r0["can_reconcile"] is False
        assert r0["reconciled"] is False
        r1 = db.reconcile_batch(bid, tolerance=0.05)
        assert r1["can_reconcile"] is True
        assert r1["reconciled"] is True
        assert db.get_batch(bid)["is_reconciled"] == 1

    def test_reconcile_invalid_batch_raises(self, db):
        with pytest.raises(ValueError):
            db.reconcile_batch(9999)

    def test_reconcile_returns_batch_id(self, db):
        aid, bid = self._setup_batch(db, 0.0, 0.0)
        result = db.reconcile_batch(bid)
        assert result["batch_id"] == bid

    def test_reconcile_only_counts_in_range_transactions(self, db):
        """Transactions outside the statement period must not affect reconciliation."""
        aid = db.add_bank_account("Range Account")
        # Create two batches for same account
        bid1 = db.create_batch(
            aid,
            statement_start="2024-01-01",
            statement_end="2024-01-31",
            beginning_balance=1000.0,
            ending_balance=1500.0,
        )
        # Import Jan transactions into batch 1
        jan_rows = [{"txn_date": "2024-01-15", "amount": 500.0, "description": "Income", "ref_number": ""}]
        db.import_transactions(bid1, aid, jan_rows)

        # Import Feb transaction into a different batch (same account)
        bid2 = db.create_batch(
            aid,
            statement_start="2024-02-01",
            statement_end="2024-02-29",
            beginning_balance=1500.0,
            ending_balance=1200.0,
        )
        feb_rows = [{"txn_date": "2024-02-10", "amount": -300.0, "description": "Rent", "ref_number": ""}]
        db.import_transactions(bid2, aid, feb_rows)

        # Reconcile January – should only see the Jan 500 credit
        r1 = db.reconcile_batch(bid1)
        assert r1["transaction_count"] == 1
        assert r1["can_reconcile"] is True

        # Reconcile February – should only see the Feb -300 debit
        r2 = db.reconcile_batch(bid2)
        assert r2["transaction_count"] == 1
        assert r2["can_reconcile"] is True

    def test_reconcile_odd_date_range(self, db):
        """Statement dates don't have to align to month boundaries."""
        aid = db.add_bank_account("Odd Range")
        bid = db.create_batch(
            aid,
            statement_start="2024-01-22",
            statement_end="2024-02-21",
            beginning_balance=200.0,
            ending_balance=450.0,
        )
        rows = [
            {"txn_date": "2024-01-22", "amount": 300.0, "description": "Deposit", "ref_number": ""},
            {"txn_date": "2024-02-10", "amount": -50.0, "description": "Fee", "ref_number": ""},
        ]
        db.import_transactions(bid, aid, rows)
        result = db.reconcile_batch(bid)
        assert result["can_reconcile"] is True
        assert result["reconciled"] is True

    def test_reconcile_empty_batch(self, db):
        """Zero transactions with matching balances → can reconcile."""
        aid, bid = self._setup_batch(db, 1000.0, 1000.0)
        result = db.reconcile_batch(bid)
        assert result["transaction_count"] == 0
        assert result["can_reconcile"] is True
