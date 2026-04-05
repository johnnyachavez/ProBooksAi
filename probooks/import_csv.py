"""CSV bank import with row validation (#31, #33, #34).

Reads input CSV with optional BOM by default (same as :data:`probooksai.bank_import.BANK_CSV_READ_ENCODING`).
Amounts use :func:`probooksai.bank_import.parse_amount` (currency symbols, Unicode minus, paste noise);
dates use ``datetime.fromisoformat`` when a time component is present, else :func:`probooksai.bank_import.parse_date` (same patterns as desktop bank CSV, including long month names); :func:`strip_csv_cell_paste_noise` runs before those parsers.
When *errors_file* is set, skipped rows are written as UTF-8 CSV with BOM for Excel.
"""

from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TextIO

from probooksai.bank_import import (
    BANK_CSV_READ_ENCODING,
    parse_amount,
    parse_date,
    strip_csv_cell_paste_noise,
)


@dataclass
class ColumnMap:
    """0-based column indices. Use -1 to omit optional fields."""

    date: int
    amount: int
    payee: int = -1
    memo: int = -1
    reference: int = -1


@dataclass
class ImportResult:
    batch_id: int
    rows_imported: int
    rows_skipped: int
    skip_reasons: list[tuple[int, str]] = field(default_factory=list)


def _parse_date(value: str) -> str | None:
    s = strip_csv_cell_paste_noise(value)
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.date().isoformat()
    except ValueError:
        pass
    return parse_date(s)


def _parse_amount(value: str, *, invert: bool) -> float | None:
    n = parse_amount(value)
    if n is None:
        return None
    return -n if invert else n


def import_bank_csv(
    conn: sqlite3.Connection,
    *,
    bank_account_id: int,
    csv_path: Path,
    columns: ColumnMap,
    skip_rows: int = 0,
    encoding: str = BANK_CSV_READ_ENCODING,
    invert_amounts: bool = False,
    errors_file: Path | None = None,
) -> ImportResult:
    """Insert rows into bank_transactions; create import_batch. Skips bad rows.

    When *errors_file* is set, skipped rows are written as UTF-8 CSV with BOM for Excel.
    Raises :exc:`FileNotFoundError` if *csv_path* is not a regular file (checked before creating a batch).
    """
    if not csv_path.is_file():
        raise FileNotFoundError(str(csv_path))
    raw_name = csv_path.name
    cur = conn.execute(
        """
        INSERT INTO import_batches (bank_account_id, source_filename, rows_imported, rows_skipped)
        VALUES (?, ?, 0, 0)
        """,
        (bank_account_id, raw_name),
    )
    batch_id = int(cur.lastrowid)

    imported = 0
    skipped: list[tuple[int, str]] = []
    err_lines: list[list[str]] = []

    with csv_path.open("r", encoding=encoding, newline="") as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if i < skip_rows:
                continue
            if not row or all(not (c or "").strip() for c in row):
                continue
            def col(idx: int) -> str:
                if idx < 0 or idx >= len(row):
                    return ""
                return row[idx] or ""

            d_raw = col(columns.date)
            a_raw = col(columns.amount)
            date_iso = _parse_date(d_raw)
            amt = _parse_amount(a_raw, invert=invert_amounts)
            if date_iso is None or amt is None:
                reason = []
                if date_iso is None:
                    reason.append("bad_date")
                if amt is None:
                    reason.append("bad_amount")
                msg = ",".join(reason)
                skipped.append((i + 1, msg))
                err_lines.append([str(i + 1), msg, "|".join(row)])
                continue

            payee = col(columns.payee) if columns.payee >= 0 else ""
            memo = col(columns.memo) if columns.memo >= 0 else ""
            ref = col(columns.reference) if columns.reference >= 0 else ""
            raw_desc = "|".join(row)

            conn.execute(
                """
                INSERT INTO bank_transactions (
                  bank_account_id, import_batch_id, txn_date, amount,
                  payee, memo, reference_number, raw_description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bank_account_id,
                    batch_id,
                    date_iso,
                    amt,
                    payee or None,
                    memo or None,
                    ref or None,
                    raw_desc,
                ),
            )
            imported += 1

    conn.execute(
        """
        UPDATE import_batches SET rows_imported = ?, rows_skipped = ? WHERE id = ?
        """,
        (imported, len(skipped), batch_id),
    )
    conn.commit()

    if errors_file is not None and err_lines:
        with errors_file.open("w", encoding="utf-8-sig", newline="") as ef:
            w = csv.writer(ef)
            w.writerow(["row_index", "reason", "raw_cells"])
            w.writerows(err_lines)

    return ImportResult(
        batch_id=batch_id,
        rows_imported=imported,
        rows_skipped=len(skipped),
        skip_reasons=skipped,
    )


def count_transactions(conn: sqlite3.Connection, bank_account_id: int | None = None) -> int:
    if bank_account_id is None:
        return conn.execute("SELECT COUNT(*) FROM bank_transactions").fetchone()[0]
    return conn.execute(
        "SELECT COUNT(*) FROM bank_transactions WHERE bank_account_id = ?",
        (bank_account_id,),
    ).fetchone()[0]
