"""Bank Statement Intake — phase 3 step 1: duplicate-against-register check.

Pre-flight scan that compares **staged** review rows against the
``bank_transactions`` already in Bank Register for a chosen account. The
goal is to give the user a visible "this row already exists" badge
*before* they hit Send, so they can drop accidental re-staging instead
of relying on the silent fingerprint dedup at post time.

Hard rules (Phase-3 invariants):

* **Suggest only.** This module never deletes, edits, or marks rows in
  ``bank_transactions``. It only returns match metadata for display.
* **Single account scope.** A scan is bound to the bank account the user
  selected for the upcoming hand-off — cross-account "duplicates" are not
  duplicates in the register-of-record sense.
* **Same sign convention.** Compares signed amounts directly so a
  positive credit is not matched against a negative debit.
* **Configurable date window.** Defaults to 3 days on either side because
  pasted-text statements often disagree with the register on
  posting-vs-trade date.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, Optional, Sequence

from probooksai.bank_import import BankDatabase
from probooksai.bank_statement_intake import BankStatementIntakeRow

DEFAULT_DATE_WINDOW_DAYS = 3
AMOUNT_EPSILON = 0.005  # half a cent — tighter than register rounding


@dataclass(frozen=True)
class RegisterDuplicateMatch:
    """One match between a staged row and an existing register row.

    ``match_strength`` is a coarse, monotonic label suitable for badges:

    * ``"exact"``  – same date, same amount, same description.
    * ``"strong"`` – same amount, date within 1 day, description token overlap.
    * ``"weak"``   – same amount, date within ``date_window_days``.
    """

    register_txn_id: int
    register_txn_date: str
    register_amount: float
    register_description: str
    match_strength: str

    def display_label(self) -> str:
        """Short label shown in the panel's "Possible duplicate" column."""
        return (
            f"#{self.register_txn_id} \u00b7 "
            f"{self.register_txn_date} \u00b7 {self.match_strength}"
        )


# ---------------------------------------------------------------------------
# Date / description helpers (private)
# ---------------------------------------------------------------------------


def _parse_iso_date(value: str) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    """Lower-cased alphanumeric token set; drops single-letter noise."""
    if not text:
        return set()
    return {t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 1}


def _amounts_equal(a: Optional[float], b: Optional[float]) -> bool:
    if a is None or b is None:
        return False
    try:
        return abs(float(a) - float(b)) < AMOUNT_EPSILON
    except (TypeError, ValueError):
        return False


def _classify_match(
    *,
    staged_date: Optional[date],
    staged_desc: str,
    register_date: Optional[date],
    register_desc: str,
) -> str:
    """Return ``"exact"`` / ``"strong"`` / ``"weak"`` for a same-amount pair."""
    if staged_date is not None and register_date is not None:
        if staged_date == register_date:
            staged_tokens = _tokens(staged_desc)
            register_tokens = _tokens(register_desc)
            if (
                staged_tokens
                and register_tokens
                and staged_tokens & register_tokens
            ):
                return "exact"
            if not staged_tokens and not register_tokens:
                return "exact"
        delta = abs((staged_date - register_date).days)
        if delta <= 1:
            staged_tokens = _tokens(staged_desc)
            register_tokens = _tokens(register_desc)
            if staged_tokens and register_tokens and staged_tokens & register_tokens:
                return "strong"
    return "weak"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def find_register_duplicates(
    bank_db: BankDatabase,
    *,
    bank_account_id: int,
    rows: Sequence[BankStatementIntakeRow],
    date_window_days: int = DEFAULT_DATE_WINDOW_DAYS,
) -> dict[int, RegisterDuplicateMatch]:
    """Return ``{row_index: RegisterDuplicateMatch}`` for staged rows that
    already look present in the register.

    Each staged row is checked for register rows on the same account whose
    signed amount equals the staged amount (within
    :data:`AMOUNT_EPSILON`) and whose date is within ``date_window_days``.
    The strongest available match per staged row is returned; rows with
    no match are absent from the dict.
    """
    if bank_db is None:
        raise ValueError("bank_db is required for register duplicate check")
    if not isinstance(bank_account_id, int) or bank_account_id <= 0:
        raise ValueError("bank_account_id must be a positive integer")
    rows_list = list(rows or [])
    if not rows_list:
        return {}
    if date_window_days < 0:
        date_window_days = 0

    conn: sqlite3.Connection = bank_db._conn

    out: dict[int, RegisterDuplicateMatch] = {}
    for idx, staged in enumerate(rows_list):
        amount = staged.amount_signed
        if amount is None:
            continue
        staged_date = _parse_iso_date(staged.txn_date)
        if staged_date is None:
            continue

        date_low = (staged_date - timedelta(days=date_window_days)).isoformat()
        date_high = (staged_date + timedelta(days=date_window_days)).isoformat()

        candidates = conn.execute(
            """
            SELECT id, txn_date, description, amount
            FROM bank_transactions
            WHERE bank_account_id = ?
              AND txn_date BETWEEN ? AND ?
              AND ABS(amount - ?) < ?
            """,
            (bank_account_id, date_low, date_high, float(amount), AMOUNT_EPSILON),
        ).fetchall()
        if not candidates:
            continue

        best: Optional[RegisterDuplicateMatch] = None
        best_rank = -1
        rank_for = {"weak": 0, "strong": 1, "exact": 2}
        for c in candidates:
            register_date = _parse_iso_date(c["txn_date"])
            strength = _classify_match(
                staged_date=staged_date,
                staged_desc=staged.description_raw or "",
                register_date=register_date,
                register_desc=c["description"] or "",
            )
            r = rank_for.get(strength, 0)
            if r > best_rank:
                best_rank = r
                best = RegisterDuplicateMatch(
                    register_txn_id=int(c["id"]),
                    register_txn_date=c["txn_date"] or "",
                    register_amount=float(c["amount"]),
                    register_description=c["description"] or "",
                    match_strength=strength,
                )
        if best is not None:
            out[idx] = best
    return out


__all__ = [
    "AMOUNT_EPSILON",
    "DEFAULT_DATE_WINDOW_DAYS",
    "RegisterDuplicateMatch",
    "find_register_duplicates",
]


# Reserved typing alias for callers that prefer ``Iterable`` ergonomics.
_IterableHint = Iterable[BankStatementIntakeRow]  # noqa: F841 (doc-only)
