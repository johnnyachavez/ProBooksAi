"""
probooksai.asset_register
=========================
Fixed-asset register: track cost, depreciation, and book value for
long-lived assets without needing every check-register line item.

Supports straight-line and declining-balance depreciation.
An asset entry plus an opening-balance journal entry is enough to
represent 10 years of ownership without importing decade-old bank data.

Schema lives in the shared company SQLite file.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS assets (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT    NOT NULL,
    description         TEXT,
    asset_type          TEXT    NOT NULL DEFAULT 'Equipment',
    purchase_date       TEXT,           -- ISO YYYY-MM-DD
    cost                REAL    NOT NULL DEFAULT 0.0,
    salvage_value       REAL    NOT NULL DEFAULT 0.0,
    useful_life_years   REAL    NOT NULL DEFAULT 5.0,
    depreciation_method TEXT    NOT NULL DEFAULT 'straight_line',
                                        -- straight_line | declining_balance | none
    coa_account         TEXT,           -- linked COA account (e.g. "1500 – Equipment")
    notes               TEXT,
    is_active           INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS company_settings (
    key     TEXT PRIMARY KEY,
    value   TEXT
);
"""

ASSET_TYPES = [
    "Equipment",
    "Vehicle",
    "Furniture & Fixtures",
    "Computer & Technology",
    "Real Property",
    "Leasehold Improvement",
    "Intangible Asset",
    "Other",
]

DEPRECIATION_METHODS = [
    "straight_line",
    "declining_balance",
    "none",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _years_elapsed(purchase_date: str, as_of: Optional[str] = None) -> float:
    """Fractional years between purchase_date and as_of (default: today)."""
    try:
        start = date.fromisoformat(purchase_date)
        end = date.fromisoformat(as_of) if as_of else date.today()
        return max(0.0, (end - start).days / 365.25)
    except (ValueError, TypeError):
        return 0.0


def compute_book_value(
    cost: float,
    salvage_value: float,
    useful_life_years: float,
    depreciation_method: str,
    purchase_date: Optional[str],
    as_of: Optional[str] = None,
) -> float:
    """Return the book value of an asset as of *as_of* (default: today)."""
    if not purchase_date or depreciation_method == "none" or useful_life_years <= 0:
        return cost

    elapsed = _years_elapsed(purchase_date, as_of)
    depreciable = max(0.0, cost - salvage_value)

    if depreciation_method == "straight_line":
        annual = depreciable / useful_life_years
        accum = min(depreciable, annual * elapsed)
    elif depreciation_method == "declining_balance":
        rate = 2.0 / useful_life_years  # double-declining
        remaining = cost
        for _ in range(int(elapsed)):
            remaining -= remaining * rate
            if remaining < salvage_value:
                remaining = salvage_value
                break
        frac = elapsed - int(elapsed)
        if frac > 0:
            remaining -= remaining * rate * frac
        remaining = max(salvage_value, remaining)
        accum = cost - remaining
    else:
        accum = 0.0

    return max(salvage_value, cost - accum)


# ---------------------------------------------------------------------------
# AssetRegister
# ---------------------------------------------------------------------------

class AssetRegister:
    """CRUD interface for the assets table."""

    def __init__(self, conn_or_path):
        if isinstance(conn_or_path, sqlite3.Connection):
            self._conn = conn_or_path
            self._owns = False
        else:
            self._conn = sqlite3.connect(conn_or_path)
            self._conn.row_factory = sqlite3.Row
            self._owns = True
        self._ensure_schema()

    def close(self):
        if self._owns:
            self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _ensure_schema(self):
        self._conn.executescript(_DDL)
        self._conn.commit()

    # -- CRUD ----------------------------------------------------------------

    def add_asset(
        self,
        *,
        name: str,
        description: str = "",
        asset_type: str = "Equipment",
        purchase_date: Optional[str] = None,
        cost: float = 0.0,
        salvage_value: float = 0.0,
        useful_life_years: float = 5.0,
        depreciation_method: str = "straight_line",
        coa_account: Optional[str] = None,
        notes: str = "",
    ) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO assets
                (name, description, asset_type, purchase_date, cost, salvage_value,
                 useful_life_years, depreciation_method, coa_account, notes,
                 is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                name, description, asset_type, purchase_date, cost, salvage_value,
                useful_life_years, depreciation_method, coa_account, notes, _now(),
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def update_asset(self, asset_id: int, fields: dict) -> None:
        allowed = {
            "name", "description", "asset_type", "purchase_date", "cost",
            "salvage_value", "useful_life_years", "depreciation_method",
            "coa_account", "notes", "is_active",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        sets = ", ".join(f"{k} = ?" for k in updates)
        self._conn.execute(
            f"UPDATE assets SET {sets} WHERE id = ?",
            (*updates.values(), asset_id),
        )
        self._conn.commit()

    def deactivate_asset(self, asset_id: int) -> None:
        self._conn.execute(
            "UPDATE assets SET is_active = 0 WHERE id = ?", (asset_id,)
        )
        self._conn.commit()

    def get_asset(self, asset_id: int) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM assets WHERE id = ?", (asset_id,)
        ).fetchone()

    def list_assets(self, include_inactive: bool = False) -> list:
        if include_inactive:
            return self._conn.execute(
                "SELECT * FROM assets ORDER BY name"
            ).fetchall()
        return self._conn.execute(
            "SELECT * FROM assets WHERE is_active = 1 ORDER BY name"
        ).fetchall()

    def book_value(self, asset_id: int, as_of: Optional[str] = None) -> float:
        row = self.get_asset(asset_id)
        if not row:
            return 0.0
        return compute_book_value(
            cost=row["cost"],
            salvage_value=row["salvage_value"],
            useful_life_years=row["useful_life_years"],
            depreciation_method=row["depreciation_method"],
            purchase_date=row["purchase_date"],
            as_of=as_of,
        )

    # -- Company settings ----------------------------------------------------

    def get_setting(self, key: str) -> Optional[str]:
        row = self._conn.execute(
            "SELECT value FROM company_settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO company_settings (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._conn.commit()
