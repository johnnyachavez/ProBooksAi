"""probooksai.business_list_filter — AR/AP grid filter tokens (no Qt)."""

from __future__ import annotations

from probooksai.business_list_filter import (
    AP_BILL_FILTER_KEYS,
    AR_INVOICE_FILTER_KEYS,
    CUSTOMER_ENTITY_KEYS,
    VENDOR_ENTITY_KEYS,
    filter_business_rows,
    filter_entity_rows,
)


def _ar_row(**overrides: object) -> dict:
    r = {
        "id": 1,
        "customer_name": "Acme Corp",
        "invoice_number": "INV-1",
        "invoice_date": "2024-01-01",
        "due_date": "2024-02-01",
        "memo": "",
        "status": "open",
        "subtotal": 90.0,
        "tax_total": 10.0,
        "total": 100.0,
        "balance_due": 50.0,
    }
    r.update(overrides)
    return r


def _ap_row(**overrides: object) -> dict:
    r = {
        "id": 1,
        "vendor_name": "Widget Co",
        "vendor_invoice_number": "PO-9",
        "bill_date": "2024-03-01",
        "due_date": "2024-04-01",
        "memo": "",
        "status": "open",
        "total": 200.0,
        "balance_due": 200.0,
        "attachment_path": "",
    }
    r.update(overrides)
    return r


def test_filter_business_rows_empty_or_whitespace_returns_all():
    rows = [_ar_row()]
    assert filter_business_rows(rows, "", AR_INVOICE_FILTER_KEYS) == rows
    assert filter_business_rows(rows, "   ", AR_INVOICE_FILTER_KEYS) == rows


def test_filter_business_rows_tokens_and_id():
    rows = [
        _ar_row(id=10, customer_name="Acme Corp", invoice_number="A-1"),
        _ar_row(id=42, customer_name="Beta Inc", invoice_number="Z-99"),
    ]
    assert [r["id"] for r in filter_business_rows(rows, "acme", AR_INVOICE_FILTER_KEYS)] == [10]
    assert [r["id"] for r in filter_business_rows(rows, "corp open", AR_INVOICE_FILTER_KEYS)] == [
        10
    ]
    # Use an id that does not appear as a substring of ISO dates (e.g. "20" matches "2024-…").
    assert [r["id"] for r in filter_business_rows(rows, "42", AR_INVOICE_FILTER_KEYS)] == [42]
    assert filter_business_rows(rows, "acme z-99", AR_INVOICE_FILTER_KEYS) == []


def test_filter_business_rows_ap_vendor_keys():
    rows = [_ap_row(vendor_name="North Supply"), _ap_row(id=2, vendor_name="South Parts")]
    assert len(filter_business_rows(rows, "north", AP_BILL_FILTER_KEYS)) == 1
    assert len(filter_business_rows(rows, "po-9", AP_BILL_FILTER_KEYS)) == 2


def test_filter_business_rows_subtotal_tax_total():
    rows = [
        _ar_row(id=1, subtotal=100.0, tax_total=8.25, total=108.25),
        _ar_row(id=2, subtotal=200.0, tax_total=0.0, total=200.0),
    ]
    assert [r["id"] for r in filter_business_rows(rows, "8.25", AR_INVOICE_FILTER_KEYS)] == [1]
    assert [r["id"] for r in filter_business_rows(rows, "200", AR_INVOICE_FILTER_KEYS)] == [2]


def test_filter_business_rows_bill_attachment_path():
    rows = [
        _ap_row(id=1, attachment_path=r"C:\Docs\jan_electric.pdf"),
        _ap_row(id=2, attachment_path=""),
    ]
    assert [r["id"] for r in filter_business_rows(rows, "electric", AP_BILL_FILTER_KEYS)] == [1]
    assert [r["id"] for r in filter_business_rows(rows, "jan_electric", AP_BILL_FILTER_KEYS)] == [1]


def test_filter_business_rows_memo_field():
    rows = [
        _ar_row(id=1, memo="Net 30 consulting"),
        _ar_row(id=2, memo="Rush order"),
    ]
    assert [r["id"] for r in filter_business_rows(rows, "consulting", AR_INVOICE_FILTER_KEYS)] == [1]
    ap_rows = [
        _ap_row(id=1, memo="Annual license"),
        _ap_row(id=2, memo="Hardware only"),
    ]
    assert [r["id"] for r in filter_business_rows(ap_rows, "license", AP_BILL_FILTER_KEYS)] == [1]


def test_filter_entity_rows_customer():
    rows = [
        {"id": 1, "name": "Acme", "email": "a@x.com", "phone": "", "address": "", "notes": ""},
        {"id": 2, "name": "Beta", "email": "", "phone": "555", "address": "", "notes": "vip"},
    ]
    assert [r["id"] for r in filter_entity_rows(rows, "acme", CUSTOMER_ENTITY_KEYS)] == [1]
    assert [r["id"] for r in filter_entity_rows(rows, "vip", CUSTOMER_ENTITY_KEYS)] == [2]


def test_filter_entity_rows_vendor_1099_token():
    rows = [
        {"id": 1, "name": "A", "email": "", "phone": "", "address": "", "notes": "", "is_1099": 0},
        {"id": 2, "name": "B", "email": "", "phone": "", "address": "", "notes": "", "is_1099": 1},
    ]
    assert [r["id"] for r in filter_entity_rows(rows, "1099", VENDOR_ENTITY_KEYS, tag_1099_vendors=True)] == [
        2
    ]


def test_filter_entity_rows_always_include_ids():
    rows = [
        {"id": 1, "name": "Zebra", "email": "", "phone": "", "address": "", "notes": ""},
        {"id": 2, "name": "Acme", "email": "", "phone": "", "address": "", "notes": ""},
    ]
    out = filter_entity_rows(rows, "acme", CUSTOMER_ENTITY_KEYS, always_include_ids=frozenset({1}))
    assert {dict(r)["id"] for r in out} == {1, 2}
    assert [dict(r)["name"] for r in out] == ["Acme", "Zebra"]
