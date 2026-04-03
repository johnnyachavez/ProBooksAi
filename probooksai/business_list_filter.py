"""Substring filter for AR/AP list rows (shared by desktop and tests; no Qt)."""

from __future__ import annotations

AR_INVOICE_FILTER_KEYS = (
    "customer_name",
    "invoice_number",
    "invoice_date",
    "due_date",
    "memo",
    "status",
    "subtotal",
    "tax_total",
    "total",
    "balance_due",
)
AP_BILL_FILTER_KEYS = (
    "vendor_name",
    "vendor_invoice_number",
    "bill_date",
    "due_date",
    "memo",
    "status",
    "total",
    "balance_due",
    "attachment_path",
)
# `customers` / `vendors` table columns (for combo pickers in dialogs)
CUSTOMER_ENTITY_KEYS = ("name", "email", "phone", "address", "notes")
VENDOR_ENTITY_KEYS = ("name", "email", "phone", "address", "notes")


def filter_business_rows(rows: list, q: str, keys: tuple[str, ...]) -> list:
    """Keep rows whose stringified *keys* (plus id) contain all whitespace-separated *q* tokens."""
    text = (q or "").strip()
    if not text:
        return list(rows)
    tokens = [t.lower() for t in text.split() if t]
    if not tokens:
        return list(rows)
    out: list = []
    for r in rows:
        d = dict(r)
        parts = [str(d.get("id"))]
        for k in keys:
            v = d.get(k)
            parts.append("" if v is None else str(v))
        hay = " ".join(parts).lower()
        if all(t in hay for t in tokens):
            out.append(r)
    return out


def filter_entity_rows(
    rows: list,
    q: str,
    keys: tuple[str, ...],
    *,
    tag_1099_vendors: bool = False,
    always_include_ids: frozenset | set | None = None,
) -> list:
    """Filter customer/vendor rows for dialogs; optional 1099 tag so *1099* matches 1099 vendors.

    *always_include_ids* keeps those rows visible even when the filter would hide them
    (e.g. current invoice customer while editing).
    """
    text = (q or "").strip()
    tokens = [t.lower() for t in text.split() if t] if text else []

    def row_matches(r: object) -> bool:
        if not tokens:
            return True
        d = dict(r)
        parts = [str(d.get("id"))]
        for k in keys:
            v = d.get(k)
            parts.append("" if v is None else str(v))
        if tag_1099_vendors and int(d.get("is_1099") or 0):
            parts.append("1099")
        hay = " ".join(parts).lower()
        return all(t in hay for t in tokens)

    base = [r for r in rows if row_matches(r)]
    if not always_include_ids:
        return base
    have = {dict(r)["id"] for r in base}
    extra: list = []
    for r in rows:
        rid = dict(r)["id"]
        if rid in always_include_ids and rid not in have:
            extra.append(r)
    if not extra:
        return base
    out = list(base) + extra
    out.sort(key=lambda r: (dict(r).get("name") or "").lower())
    return out
