"""Bank Statement Intake — phase 2 hand-off to the Bank Register.

Bridges the **review-only** intake queue (rows the user has staged in the
``BankStatementIntakePanel``) into the canonical ``bank_transactions``
table. The Bank Register remains the single source of truth — this module
is the *only* approved write path between intake and register.

Behavior at a glance
--------------------

* The user explicitly chooses the bank account first; rows in the queue
  are not bound to an account at extraction time.
* A dedicated import batch is created per send (filename
  :data:`STATEMENT_INTAKE_BATCH_FILENAME`), so the resulting register
  rows are visually distinct from CSV-file imports and Manual entries.
* Existing fingerprint dedup
  (:meth:`probooksai.bank_import.BankDatabase.import_transactions`) is
  reused — re-sending the same row is a no-op skip, not a duplicate.
* Rows missing required register fields (``txn_date`` or
  ``amount_signed``) are reported as ``invalid`` and never inserted; the
  panel keeps them in the queue so the user can fix them.
* ``description`` is taken from ``description_raw``, ``memo`` is left
  empty, ``coa_account`` is left empty (Phase 2 does **not** classify —
  classification is a future AI phase).

Returns a ``HandoffResult`` so the panel can show an accurate post-send
summary and evict only the successfully-inserted rows from the queue.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

from probooksai.bank_import import BankDatabase, parse_date
from probooksai.bank_statement_intake import BankStatementIntakeRow

STATEMENT_INTAKE_BATCH_FILENAME = "(Statement intake)"


@dataclass(frozen=True)
class HandoffResult:
    """Outcome of a single :func:`post_intake_rows_to_register` call.

    * ``inserted`` – rows that became new ``bank_transactions``.
    * ``skipped_duplicates`` – rows the dedup fingerprint already saw.
    * ``invalid`` – rows missing required fields (date or signed amount).
    * ``batch_id`` – id of the new ``bank_import_batches`` row, or
      ``None`` when ``inserted == 0`` and no batch was needed.
    * ``inserted_indexes`` – indexes (into the input ``rows`` list) of
      rows that were either inserted **or** skipped as duplicates — i.e.
      rows the panel can safely evict from its persisted queue.
    * ``invalid_indexes`` – indexes of rows the panel should keep in the
      queue so the user can correct them.
    """

    inserted: int = 0
    skipped_duplicates: int = 0
    invalid: int = 0
    batch_id: Optional[int] = None
    inserted_indexes: tuple[int, ...] = field(default_factory=tuple)
    invalid_indexes: tuple[int, ...] = field(default_factory=tuple)

    @property
    def attempted(self) -> int:
        return self.inserted + self.skipped_duplicates + self.invalid


def _is_valid_for_register(row: BankStatementIntakeRow) -> bool:
    """``txn_date`` must parse to ISO; ``amount_signed`` must be a real number."""
    if not row.txn_date:
        return False
    if parse_date(row.txn_date) is None:
        return False
    if row.amount_signed is None:
        return False
    try:
        float(row.amount_signed)
    except (TypeError, ValueError):
        return False
    return True


def _row_to_register_dict(row: BankStatementIntakeRow) -> dict:
    """Map a staged review row to the dict-shape expected by ``import_transactions``."""
    iso = parse_date(row.txn_date) or row.txn_date
    description = (row.description_raw or "").strip()
    ref_number = (row.source_ref or "").strip()
    return {
        "txn_date": iso,
        "description": description,
        "amount": float(row.amount_signed or 0.0),
        "ref_number": ref_number,
        "memo": "",
        "coa_account": "",
    }


def post_intake_rows_to_register(
    bank_db: BankDatabase,
    *,
    bank_account_id: int,
    rows: Sequence[BankStatementIntakeRow],
    source_label: str = "",
) -> HandoffResult:
    """Send *rows* to ``bank_transactions`` under *bank_account_id*.

    Creates exactly one new ``bank_import_batches`` row tagged with
    :data:`STATEMENT_INTAKE_BATCH_FILENAME` (suffixed with *source_label*
    when supplied) so users can audit the batch in Bank Register.

    Validation, dedup, and the inserted/skipped accounting all happen
    here so the caller (the review panel) does not need to duplicate the
    logic.
    """
    if bank_db is None:
        raise ValueError("bank_db is required for register hand-off")
    if not isinstance(bank_account_id, int) or bank_account_id <= 0:
        raise ValueError("bank_account_id must be a positive integer")

    rows_list = list(rows or [])
    if not rows_list:
        return HandoffResult()

    invalid_indexes: list[int] = []
    valid_indexes: list[int] = []
    valid_payload: list[dict] = []
    for i, r in enumerate(rows_list):
        if _is_valid_for_register(r):
            valid_payload.append(_row_to_register_dict(r))
            valid_indexes.append(i)
        else:
            invalid_indexes.append(i)

    if not valid_payload:
        return HandoffResult(
            inserted=0,
            skipped_duplicates=0,
            invalid=len(invalid_indexes),
            batch_id=None,
            inserted_indexes=(),
            invalid_indexes=tuple(invalid_indexes),
        )

    label = (source_label or "").strip()
    if label:
        batch_filename = f"{STATEMENT_INTAKE_BATCH_FILENAME} {label}"
    else:
        batch_filename = STATEMENT_INTAKE_BATCH_FILENAME

    batch_id = bank_db.create_batch(
        bank_account_id=bank_account_id,
        filename=batch_filename,
    )

    summary = bank_db.import_transactions(
        batch_id=batch_id,
        bank_account_id=bank_account_id,
        rows=valid_payload,
    )

    inserted = int(summary.get("inserted", 0))
    skipped = int(summary.get("skipped", 0))

    return HandoffResult(
        inserted=inserted,
        skipped_duplicates=skipped,
        invalid=len(invalid_indexes),
        batch_id=batch_id,
        inserted_indexes=tuple(valid_indexes),
        invalid_indexes=tuple(invalid_indexes),
    )


def is_statement_intake_batch_filename(filename: str) -> bool:
    """``True`` for any filename produced by :data:`STATEMENT_INTAKE_BATCH_FILENAME`."""
    if not filename:
        return False
    return filename.startswith(STATEMENT_INTAKE_BATCH_FILENAME)


__all__ = [
    "HandoffResult",
    "STATEMENT_INTAKE_BATCH_FILENAME",
    "post_intake_rows_to_register",
    "is_statement_intake_batch_filename",
]


# Keep an Iterable import-time symbol around for callers that prefer it.
_IterableHint = Iterable[BankStatementIntakeRow]  # noqa: F841 (doc-only)
