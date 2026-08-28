"""A/R Aging Summary — live open invoices grouped by customer / job.

Buckets follow QuickBooks Pro Desktop A/R Aging Summary: Current, then
``interval``-day slices through ``through`` days past due, then ``> through``.
Empty company files yield zeros — this module never seeds demo names or totals.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Optional

from probooksai import business

_OPEN_EPS = 0.005


def bucket_columns(interval: int = 30, through: int = 90) -> list[tuple[str, str, int, Optional[int]]]:
    """Return ``(key, label, low_inclusive, high_inclusive)`` aging columns.

    *Current* is days past due ``<= 0``. Numbered slices start at 1 and stop at
    *through*. The last column is ``> through`` (open-ended).
    """
    interval = max(1, int(interval or 1))
    through = max(1, int(through or 1))
    cols: list[tuple[str, str, int, Optional[int]]] = [
        ("current", "Current", -10_000_000, 0),
    ]
    start = 1
    while start <= through:
        end = min(start + interval - 1, through)
        key = f"{start}_{end}"
        label = str(start) if start == end else f"{start} - {end}"
        cols.append((key, label, start, end))
        start = end + 1
    cols.append((f"over_{through}", f"> {through}", through + 1, None))
    return cols


def days_past_due(due_iso: str, as_of: date) -> int:
    """Days past *due_iso* vs *as_of*. Missing/invalid due dates are current (0)."""
    raw = (due_iso or "").strip()[:10]
    if not raw:
        return 0
    try:
        due = date.fromisoformat(raw)
    except ValueError:
        return 0
    return (as_of - due).days


def bucket_key_for_days(
    days_past: int, columns: list[tuple[str, str, int, Optional[int]]]
) -> str:
    for key, _label, low, high in columns:
        if high is None:
            if days_past >= low:
                return key
        elif low <= days_past <= high:
            return key
    return columns[0][0]


def empty_amounts(columns: list[tuple[str, str, int, Optional[int]]]) -> dict[str, float]:
    out = {key: 0.0 for key, _label, _lo, _hi in columns}
    out["total"] = 0.0
    return out


def _add_into(dst: dict[str, float], src: dict[str, float]) -> None:
    for k, v in src.items():
        dst[k] = round(float(dst.get(k) or 0) + float(v or 0), 2)


def _nonzero(amounts: dict[str, float]) -> bool:
    return abs(float(amounts.get("total") or 0)) > _OPEN_EPS


def _party_amounts(
    columns: list[tuple[str, str, int, Optional[int]]],
) -> dict[str, float]:
    return empty_amounts(columns)


def ar_aging_summary(
    conn: sqlite3.Connection,
    as_of: str,
    *,
    interval: int = 30,
    through: int = 90,
    sort_by: str = "default",
) -> dict:
    """Build a customer/job A/R Aging Summary from live ``invoices.balance_due``.

    Returns bucket metadata, per-customer groups (jobs indented under parents),
    and a grand-total row. Paid invoices (balance_due ≈ 0) are omitted.
    """
    as_of_d = date.fromisoformat(as_of)
    columns = bucket_columns(interval, through)
    keys = [c[0] for c in columns]
    labels = [c[1] for c in columns]

    rows = conn.execute(
        """
        SELECT i.id, i.customer_id, i.balance_due, i.due_date,
               c.name AS customer_name, c.parent_customer_id
        FROM invoices i
        JOIN customers c ON c.id = i.customer_id
        WHERE i.balance_due > 0.005
        """
    ).fetchall()

    by_customer: dict[int, dict] = {}
    for r in rows:
        cid = int(r["customer_id"])
        rec = by_customer.get(cid)
        if rec is None:
            pid = r["parent_customer_id"]
            rec = {
                "customer_id": cid,
                "name": (r["customer_name"] or "").strip(),
                "parent_customer_id": int(pid) if pid is not None else None,
                "amounts": _party_amounts(columns),
            }
            by_customer[cid] = rec
        days = days_past_due(r["due_date"] or "", as_of_d)
        key = bucket_key_for_days(days, columns)
        bal = round(float(r["balance_due"] or 0), 2)
        rec["amounts"][key] = round(rec["amounts"].get(key, 0.0) + bal, 2)
        rec["amounts"]["total"] = round(rec["amounts"]["total"] + bal, 2)

    # Parents with jobs but no invoices of their own still need a row for grouping.
    for rec in list(by_customer.values()):
        pid = rec.get("parent_customer_id")
        if pid is None or int(pid) in by_customer:
            continue
        parent = business.get_customer(conn, int(pid))
        if parent is None:
            rec["parent_customer_id"] = None
            continue
        pd = dict(parent)
        by_customer[int(pid)] = {
            "customer_id": int(pid),
            "name": (pd.get("name") or "").strip(),
            "parent_customer_id": None,
            "amounts": _party_amounts(columns),
        }

    children_of: dict[int, list[dict]] = {}
    for rec in by_customer.values():
        pid = rec.get("parent_customer_id")
        if pid is None:
            continue
        children_of.setdefault(int(pid), []).append(rec)

    groups: list[dict] = []
    grand = empty_amounts(columns)

    for rec in by_customer.values():
        if rec.get("parent_customer_id") is not None:
            continue
        cid = int(rec["customer_id"])
        jobs = [j for j in children_of.get(cid, []) if _nonzero(j["amounts"])]
        jobs.sort(key=lambda j: (j["name"] or "").lower())
        own = rec["amounts"]
        has_jobs = bool(jobs)
        if not has_jobs and not _nonzero(own):
            continue

        if has_jobs:
            rollup = empty_amounts(columns)
            _add_into(rollup, own)
            job_rows: list[dict] = []
            for job in jobs:
                job_rows.append(
                    {
                        "kind": "job",
                        "customer_id": int(job["customer_id"]),
                        "name": job["name"],
                        "amounts": dict(job["amounts"]),
                    }
                )
                _add_into(rollup, job["amounts"])
            if _nonzero(own):
                job_rows.append(
                    {
                        "kind": "other",
                        "customer_id": cid,
                        "name": f"{rec['name']} - Other",
                        "amounts": dict(own),
                    }
                )
            groups.append(
                {
                    "kind": "parent",
                    "customer_id": cid,
                    "name": rec["name"],
                    "amounts": rollup,
                    "jobs": job_rows,
                    "has_children": True,
                }
            )
            _add_into(grand, rollup)
        else:
            groups.append(
                {
                    "kind": "standalone",
                    "customer_id": cid,
                    "name": rec["name"],
                    "amounts": dict(own),
                    "jobs": [],
                    "has_children": False,
                }
            )
            _add_into(grand, own)

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
