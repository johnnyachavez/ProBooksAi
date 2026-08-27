"""Dispatch sheet CSV intake — parse, 160X7 split, grouping, skip-missing-rate, no tax-id columns."""

from __future__ import annotations

from pathlib import Path

import pytest

from probooksai.dispatch_intake import (
    DispatchGoogleNotConfigured,
    SAMPLE_JOB_BILLING_RULES,
    SAMPLE_TRUCKER_PAY,
    fetch_google_dispatch_rows,
    group_bill_drafts,
    group_invoice_drafts,
    is_sensitive_dispatch_header,
    match_named_entity_id,
    parse_dispatch_csv,
    parse_dispatch_csv_text,
    parse_lookup_csv,
    parse_pay_rate_cell,
    parse_qty_rate_cell,
    drafts_for_invoice_row,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLE_CSV = FIXTURES / "dispatch_intake_sample.csv"


def test_parse_qty_rate_160x7_splits_rate_and_quantity() -> None:
    rate, qty, missing = parse_qty_rate_cell("160X7")
    assert missing is False
    assert rate == 160.0
    assert qty == 7.0
    rate2, qty2, missing2 = parse_qty_rate_cell("160 x 7")
    assert (rate2, qty2, missing2) == (160.0, 7.0, False)
    rate3, qty3, missing3 = parse_qty_rate_cell("$1,250.00")
    assert missing3 is False
    assert rate3 == 1250.0
    assert qty3 == 1.0


def test_parse_qty_rate_blank_is_missing_zero_is_present() -> None:
    rate, qty, missing = parse_qty_rate_cell("")
    assert missing is True
    assert rate is None
    assert qty == 1.0
    z_rate, z_qty, z_missing = parse_qty_rate_cell("0")
    assert z_missing is False
    assert z_rate == 0.0
    assert z_qty == 1.0
    n_rate, _, n_missing = parse_qty_rate_cell("n/a")
    assert n_missing is True
    assert n_rate is None


def test_parse_pay_rate_zero_allowed_for_owner_operator() -> None:
    amt, missing = parse_pay_rate_cell("0")
    assert missing is False
    assert amt == 0.0
    blank, blank_missing = parse_pay_rate_cell("")
    assert blank_missing is True
    assert blank is None
    x_amt, x_missing = parse_pay_rate_cell("160X7")
    assert x_missing is False
    assert x_amt == 1120.0


def test_parse_sample_csv_three_3235_loads_and_blank_rate() -> None:
    result = parse_dispatch_csv(SAMPLE_CSV)
    assert result.skipped_sensitive_headers == ()
    jobs = [r.invoice_code for r in result.rows]
    assert jobs.count("3235") == 4
    drafts, skipped = group_invoice_drafts(result.rows)
    job_3235 = [d for d in drafts if d.invoice_code == "3235"]
    assert len(job_3235) == 1
    draft = job_3235[0]
    assert len(draft.lines) == 3
    assert [ln.bol for ln in draft.lines] == ["BOL-101", "BOL-102", "BOL-103"]
    assert draft.lines[0].date_iso == "2026-08-01"
    assert draft.lines[0].description == "Plant A to Site North"
    assert draft.lines[0].rate == 150.0
    assert draft.lines[0].qty == 1.0
    assert draft.lines[0].amount == 150.0
    assert draft.lines[2].rate == 160.0
    assert draft.lines[2].qty == 7.0
    assert draft.lines[2].amount == 1120.0
    assert draft.po_load == "PO-3235-A"
    skipped_3235 = [r for r in skipped if r.invoice_code == "3235"]
    assert len(skipped_3235) == 1
    assert skipped_3235[0].invoice_rate_missing is True
    assert skipped_3235[0].bol == "BOL-104"
    assert skipped_3235[0].queue_status() == "needs rate"


def test_group_invoice_by_qb_inv_no_overrides_job_date() -> None:
    text = (
        "DATE,INVOICE,DISPATCH,DRIVER,INVOICE RATE,PAY RATE,PO / LOAD#,BOL#,QB Inv No.\n"
        "2026-08-01,3235,Load A,Alex,10,1,PO-1,B1,QB-9\n"
        "2026-08-02,3235,Load B,Alex,20,1,PO-1,B2,QB-9\n"
        "2026-08-01,3235,Load C,Alex,30,1,PO-1,B3,\n"
    )
    result = parse_dispatch_csv_text(text)
    drafts, skipped = group_invoice_drafts(result.rows)
    assert skipped == []
    by_qb = [d for d in drafts if d.qb_inv_no == "QB-9"]
    assert len(by_qb) == 1
    assert len(by_qb[0].lines) == 2
    same_day = [d for d in drafts if not d.qb_inv_no]
    assert len(same_day) == 1
    assert len(same_day[0].lines) == 1


def test_skip_missing_invoice_rate_does_not_build_draft() -> None:
    text = (
        "DATE,INVOICE,DISPATCH,DRIVER,INVOICE RATE,PAY RATE,PO / LOAD#,BOL#,QB Inv No.\n"
        "2026-08-01,3235,Only this,Alex,,50,PO-1,B1,\n"
    )
    result = parse_dispatch_csv_text(text)
    drafts, skipped = group_invoice_drafts(result.rows)
    assert drafts == []
    assert len(skipped) == 1
    assert skipped[0].queue_status() == "needs rate"
    assert drafts_for_invoice_row(result.rows, result.rows[0]) is None


def test_sensitive_tax_id_columns_are_not_imported(tmp_path: Path) -> None:
    csv_path = tmp_path / "loads_with_pii_headers.csv"
    csv_path.write_text(
        "DATE,INVOICE,DISPATCH,DRIVER,INVOICE RATE,PAY RATE,PO / LOAD#,BOL#,QB Inv No.,"
        "SSN,EIN,Tax ID,DIR #,Bank Account,Routing\n"
        "2026-08-02,T1,Sample plant to job,Sample Hauling LLC,50,40,PO-T1,BOL-9,,"
        "MUST-NOT-IMPORT,MUST-NOT-IMPORT,MUST-NOT-IMPORT,MUST-NOT-IMPORT,"
        "MUST-NOT-IMPORT,MUST-NOT-IMPORT\n",
        encoding="utf-8",
    )
    result = parse_dispatch_csv(csv_path)
    sensitive = {h.lower() for h in result.skipped_sensitive_headers}
    assert "ssn" in sensitive
    assert "ein" in sensitive
    assert any("tax id" in h.lower() for h in result.skipped_sensitive_headers)
    assert any("dir" in h.lower() for h in result.skipped_sensitive_headers)
    assert any("bank" in h.lower() for h in result.skipped_sensitive_headers)
    assert len(result.rows) == 1
    blob = repr(result.rows[0].as_dict()).lower()
    assert "must-not-import" not in blob
    assert "ssn" not in blob
    assert "ein" not in blob
    dumped = parse_dispatch_csv_text(csv_path.read_text(encoding="utf-8"))
    assert "MUST-NOT-IMPORT" not in dumped.rows[0].review_text()


@pytest.mark.parametrize(
    "header",
    ["SSN", "Social Security", "EIN", "FEIN", "Tax ID", "DIR", "DIR #", "Bank Account", "Routing"],
)
def test_sensitive_header_detector(header: str) -> None:
    assert is_sensitive_dispatch_header(header) is True


def test_dispatch_and_driver_headers_are_not_sensitive() -> None:
    assert is_sensitive_dispatch_header("DISPATCH") is False
    assert is_sensitive_dispatch_header("DRIVER") is False
    assert is_sensitive_dispatch_header("DATE") is False


def test_bill_group_includes_zero_pay_rate_skips_blank() -> None:
    result = parse_dispatch_csv(SAMPLE_CSV)
    drafts, skipped = group_bill_drafts(result.rows)
    # Four 3235 rows have pay rates (100, 100, 100, 90); BST has 0.
    alex = [d for d in drafts if d.vendor_name == "Alex Rivera"]
    assert len(alex) == 1
    assert len(alex[0].lines) == 4
    bst = [d for d in drafts if d.vendor_name == "Sample Hauling LLC"]
    assert len(bst) == 1
    assert bst[0].lines[0].amount == 0.0
    assert skipped == []


def test_lookup_csv_drops_tax_id_keeps_name_and_email(tmp_path: Path) -> None:
    path = tmp_path / "truckers.csv"
    path.write_text(
        "Name,Email,SSN,EIN,DIR\n"
        "Sample Hauling LLC,ap@example.invalid,MUST-NOT-IMPORT,MUST-NOT-IMPORT,MUST-NOT-IMPORT\n",
        encoding="utf-8",
    )
    rows, skipped = parse_lookup_csv(path)
    assert any(h.lower() == "ssn" for h in skipped)
    assert len(rows) == 1
    assert rows[0]["name"] == "Sample Hauling LLC"
    assert rows[0]["email"] == "ap@example.invalid"
    assert "MUST-NOT-IMPORT" not in repr(rows)


def test_sample_lookups_have_no_tax_identifiers() -> None:
    blob = repr(SAMPLE_JOB_BILLING_RULES) + repr(SAMPLE_TRUCKER_PAY)
    for needle in ("ssn", "ein", "tax id", "dir #", "social"):
        assert needle not in blob.lower()
    for row in SAMPLE_TRUCKER_PAY:
        assert set(row.keys()) <= {"name", "email"}


def test_match_named_entity_id_job_and_parent_label() -> None:
    choices = [(1, "Sample Materials Co"), (2, "Acme > 3235"), (3, "BST Sample Logistics")]
    assert match_named_entity_id(choices, "3235") == 2
    assert match_named_entity_id(choices, "Sample Materials Co") == 1
    assert match_named_entity_id(choices, "BST") == 3


def test_google_live_pull_is_stubbed_without_using_a_token() -> None:
    with pytest.raises(DispatchGoogleNotConfigured) as ei:
        fetch_google_dispatch_rows(api_token="not-a-real-token")
    msg = str(ei.value)
    assert "1 CHAVAN DISPATCH" in msg
    assert "CSV" in msg
    assert "not-a-real-token" not in msg
