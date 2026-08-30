"""A/P Aging Summary — live open bills grouped by vendor.

Buckets follow QuickBooks Pro Desktop A/P Aging Summary: Current, then
``interval``-day slices through ``through`` days past due, then ``> through``.
Empty company files yield zeros — this module never seeds demo names or totals.

The bucket-column primitives (``bucket_columns`` / ``days_past_due`` /
``bucket_key_for_days`` / ``empty_amounts``) are shared with the A/R Aging
Summary via ``probooksai.qb_ar_aging``. Vendors have no parent/child ("jobs")
in QuickBooks Pro Desktop, so the AP grid is a flat list per vendor.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from probooksai.qb_ar_aging import (
    bucket_columns,
    bucket_key_for_days,
    days_past_due,
    empty_amounts,
)

__all__ = [
    "bucket_columns",
    "bucket_key_for_days",
    "days_past_due",
    "empty_amounts",
    "ap_aging_summary",
]

_OPEN_EPS = 0.005


def _add_into(dst: dict[str, float], src: dict[str, float]) -> None:
    for k, v in src.items():
        dst[k] = round(float(dst.get(k) or 0) + float(v or 0), 2)


def _nonzero(amounts: dict[str, float]) -> bool:
    return abs(float(amounts.get("total") or 0)) > _OPEN_EPS


def ap_aging_summary(
    conn: sqlite3.Connection,
    as_of: str,
    *,
    interval: int = 30,
    through: int = 90,
    sort_by: str = "default",
) -> dict:
    """Build a vendor A/P Aging Summary from live ``bills.balance_due``.

    Returns bucket metadata, one row per vendor with a non-zero balance, and
    a grand-total row. Paid bills (balance_due ≈ 0) are omitted. Bills with a
    missing or invalid ``due_date`` fall in ``Current`` (days-past-due = 0),
    matching the A/R helper's behavior.
    """
    as_of_d = date.fromisoformat(as_of)
    columns = bucket_columns(interval, through)
    keys = [c[0] for c in columns]
    labels = [c[1] for c in columns]

    rows = conn.execute(
        """
        SELECT b.id, b.vendor_id, b.balance_due, b.due_date,
               v.name AS vendor_name
        FROM bills b
        JOIN vendors v ON v.id = b.vendor_id
        WHERE b.balance_due > 0.005
        """
    ).fetchall()

    by_vendor: dict[int, dict] = {}
    for r in rows:
        vid = int(r["vendor_id"])
        rec = by_vendor.get(vid)
        if rec is None:
            rec = {
                "vendor_id": vid,
                "name": (r["vendor_name"] or "").strip(),
                "amounts": empty_amounts(columns),
            }
            by_vendor[vid] = rec
        days = days_past_due(r["due_date"] or "", as_of_d)
        key = bucket_key_for_days(days, columns)
        bal = round(float(r["balance_due"] or 0), 2)
        rec["amounts"][key] = round(rec["amounts"].get(key, 0.0) + bal, 2)
        rec["amounts"]["total"] = round(rec["amounts"]["total"] + bal, 2)

    groups: list[dict] = []
    grand = empty_amounts(columns)
    for rec in by_vendor.values():
        if not _nonzero(rec["amounts"]):
            continue
        groups.append(
            {
                "kind": "vendor",
                "vendor_id": int(rec["vendor_id"]),
                "name": rec["name"],
                "amounts": dict(rec["amounts"]),
            }
        )
        _add_into(grand, rec["amounts"])

    sort_key = (sort_by or "default").strip().lower()
    if sort_key == "total":
        groups.sort(key=lambda g: (-float(g["amounts"]["total"]), (g["name"] or "").lower()))
    else:
        groups.sort(key=lambda g: (g["name"] or "").lower())

    return {
        "as_of": as_of,
        "interval": max(1, int(interval or 1)),
        "through": max(1, int(through or 1)),
        "bucket_keys": keys,
        "bucket_labels": labels,
        "groups": groups,
        "grand_total": grand,
    }
