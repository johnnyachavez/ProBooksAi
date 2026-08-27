"""Dispatch sheet CSV intake — parse, 160X7 split, grouping, skip-missing-rate, no tax-id columns."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from probooksai.dispatch_intake import (
    DispatchGoogleNotConfigured,
    GOOGLE_DISPATCH_SHEET_ID,
    GOOGLE_DISPATCH_SHEET_TITLE,
    SAMPLE_JOB_BILLING_RULES,
    SAMPLE_TRUCKER_PAY,
    expected_live_dispatch_year_tab,
    fetch_google_dispatch_rows,
    group_bill_drafts,
    group_invoice_drafts,
    is_sensitive_dispatch_header,
    match_named_entity_id,
    parse_dispatch_csv,
    parse_dispatch_csv_text,
    parse_dispatch_date,
    parse_lookup_csv,
    parse_pay_rate_cell,
    parse_qty_rate_cell,
    drafts_for_invoice_row,
    select_live_dispatch_year_tab,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLE_CSV = FIXTURES / "dispatch_intake_sample.csv"
# Sample + synthetic live-tab dates are 2026; pin so tests stay valid in later years.
_AS_OF = date(2026, 8, 27)


def _parse_text(text: str, **kwargs) -> object:
    kwargs.setdefault("as_of", _AS_OF)
    return parse_dispatch_csv_text(text, **kwargs)


def _parse_file(path: Path, **kwargs):
    kwargs.setdefault("as_of", _AS_OF)
    return parse_dispatch_csv(path, **kwargs)


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
    result = _parse_file(SAMPLE_CSV)
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


def test_rows_with_qb_inv_no_are_skipped_not_drafted() -> None:
    """Already invoiced loads (QB Inv No. filled) are not queued or drafted."""
    text = (
        "DATE,INVOICE,DISPATCH,DRIVER,INVOICE RATE,PAY RATE,PO / LOAD#,BOL#,QB Inv No.\n"
        "8.25.2026,3235,Load A,AR,160,100,PO-1,B1,12332\n"
        "8.25.2026,3235,Load B,RAYA,160,100,PO-1,B2,\n"
        "2025-08-01,3235,Old history,AR,160,100,PO-1,B3,\n"
    )
    result = _parse_text(text)
    assert [r.bol for r in result.rows] == ["B2"]
    assert result.rows[0].qb_inv_no == ""
    assert result.rows[0].driver == "RAYA"
    assert len(result.skipped_already_invoiced) == 1
    assert result.skipped_already_invoiced[0].bol == "B1"
    assert result.skipped_already_invoiced[0].qb_inv_no == "12332"
    assert len(result.skipped_history_year) == 1
    assert result.skipped_history_year[0].bol == "B3"
    inv_drafts, inv_skipped = group_invoice_drafts(result.rows)
    assert inv_skipped == []
    assert len(inv_drafts) == 1
    assert len(inv_drafts[0].lines) == 1
    assert inv_drafts[0].lines[0].bol == "B2"
    assert inv_drafts[0].qb_inv_no == ""
    bill_drafts, bill_skipped = group_bill_drafts(result.rows)
    assert bill_skipped == []
    assert len(bill_drafts) == 1
    assert bill_drafts[0].vendor_name == "RAYA"
    # Grouping helpers must not revive the already-invoiced row.
    assert drafts_for_invoice_row(
        list(result.rows) + list(result.skipped_already_invoiced),
        result.skipped_already_invoiced[0],
    ) is None


def test_skip_missing_invoice_rate_does_not_build_draft() -> None:
    text = (
        "DATE,INVOICE,DISPATCH,DRIVER,INVOICE RATE,PAY RATE,PO / LOAD#,BOL#,QB Inv No.\n"
        "2026-08-01,3235,Only this,Alex,,50,PO-1,B1,\n"
    )
    result = _parse_text(text)
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
    result = _parse_file(csv_path)
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
    dumped = _parse_text(csv_path.read_text(encoding="utf-8"))
    assert "MUST-NOT-IMPORT" not in dumped.rows[0].review_text()


@pytest.mark.parametrize(
    "header",
    [
        "SSN",
        "Social Security",
        "EIN",
        "FEIN",
        "Tax ID",
        "DIR",
        "DIR #",
        "Trucker ID",
        "CA#",
        "Bank Account",
        "Routing",
    ],
)
def test_sensitive_header_detector(header: str) -> None:
    assert is_sensitive_dispatch_header(header) is True


def test_dispatch_and_driver_headers_are_not_sensitive() -> None:
    assert is_sensitive_dispatch_header("DISPATCH") is False
    assert is_sensitive_dispatch_header("DRIVER") is False
    assert is_sensitive_dispatch_header("DATE") is False


def test_bill_group_includes_zero_pay_rate_skips_blank() -> None:
    result = _parse_file(SAMPLE_CSV)
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
    assert GOOGLE_DISPATCH_SHEET_TITLE in msg
    assert "CSV" in msg
    assert "current calendar year" in msg
    assert expected_live_dispatch_year_tab() in msg
    assert "DATE | INVOICE | DISPATCH | DRIVER | INVOICE RATE | PAY RATE | PO / LOAD# | BOL# | QB Inv No." in msg
    assert "blank QB Inv No" in msg
    assert "not-a-real-token" not in msg
    assert GOOGLE_DISPATCH_SHEET_ID == "112pHWAkiTIk5N31mAUzUuydsSdUh9fVoBSADnZHzlXQ"
    assert "token" not in GOOGLE_DISPATCH_SHEET_ID.lower()
    assert expected_live_dispatch_year_tab(as_of=date(2031, 6, 1)) == "2031"


def test_live_sheet_dotted_dates_and_bol_hash_header() -> None:
    """CSV shape from 1 CHAVAN DISPATCH loads tab (synthetic unbilled rows, no PII)."""
    text = (
        "DATE,INVOICE,DISPATCH,DRIVER,INVOICE RATE,PAY RATE,PO / LOAD#,BOL #,QB Inv No.\n"
        "1.5.2026,3235,Plant A onsite,RAYA,160,100,PO-A,30609,\n"
        "01.19.2026,3235,Plant A haul,AR,160X7,100,PO-A,31288,\n"
        "1.8.2026,3235,Super 10,SS,160,X,PO-B,3195919,\n"
        "1.6.2026,3235,Super 10 scale,SS,160,SCALE,PO-B,3195917,\n"
        "8.25.2026,3235,Plant A,AR,160,100,PO-A,40001,\n"
    )
    result = _parse_text(text, source_ref="chavan-loads.csv")
    assert [r.date_iso for r in result.rows] == [
        "2026-01-05",
        "2026-01-19",
        "2026-01-08",
        "2026-01-06",
        "2026-08-25",
    ]
    assert result.skipped_already_invoiced == ()
    assert result.rows[0].bol == "30609"
    assert result.rows[1].invoice_qty == 7.0
    assert result.rows[1].invoice_rate == 160.0
    assert result.rows[2].pay_rate_missing is True
    assert result.rows[3].pay_rate_missing is True
    drafts, skipped = group_invoice_drafts(result.rows)
    assert skipped == []
    assert len(drafts) == 5


def test_multiple_drivers_same_job_date_stay_separate_lines() -> None:
    text = (
        "DATE,INVOICE,DISPATCH,DRIVER,INVOICE RATE,PAY RATE,PO / LOAD#,BOL#,QB Inv No.\n"
        "8.25.2026,3235,Plant A,AR,160,100,PO-A,40001,\n"
        "8.25.2026,3235,Plant A,RAYA,160,100,PO-A,40002,\n"
    )
    result = _parse_text(text)
    drafts, skipped = group_invoice_drafts(result.rows)
    assert skipped == []
    assert len(drafts) == 1
    assert [ln.bol for ln in drafts[0].lines] == ["40001", "40002"]
    bills, _ = group_bill_drafts(result.rows)
    assert {d.vendor_name for d in bills} == {"AR", "RAYA"}


def test_history_year_tab_export_is_not_imported() -> None:
    text = (
        "DATE,INVOICE,DISPATCH,DRIVER,INVOICE RATE,PAY RATE,PO / LOAD#,BOL#,QB Inv No.\n"
        "8.25.2026,3235,Would look live,AR,160,100,PO-A,1,\n"
    )
    result = _parse_text(text, source_tab="2025")
    assert result.rows == []
    assert len(result.skipped_history_year) == 1


def test_ticket_hash_header_aliases_to_bol() -> None:
    text = (
        "DATE,INVOICE,DISPATCH,DRIVER,INVOICE RATE,PAY RATE,PO / LOAD#,TICKET #,QB Inv No.\n"
        "2026-08-01,BST,Yard to mill,AR,85,0,LOAD-1,24570,\n"
    )
    result = _parse_text(text)
    assert len(result.rows) == 1
    assert result.rows[0].bol == "24570"
    assert result.rows[0].pay_rate == 0.0
    assert result.rows[0].pay_rate_missing is False


def test_parse_dispatch_date_dotted_us_and_incomplete() -> None:
    assert parse_dispatch_date("1.5.2026") == "2026-01-05"
    assert parse_dispatch_date("02.04.2026") == "2026-02-04"
    assert parse_dispatch_date("8.25.2026") == "2026-08-25"
    assert parse_dispatch_date("1.13") is None


def test_lookup_csv_live_trucker_tab_headers_drop_dir_and_tax_id(tmp_path: Path) -> None:
    path = tmp_path / "trucker_tab.csv"
    path.write_text(
        "COMPANY NAME,TRUCKER,A/C PAYABLE,DIR#,CA#,TAX ID,Trucker ID\n"
        "Sample Hauling LLC,Sample Driver,ap@example.invalid,"
        "MUST-NOT-IMPORT,MUST-NOT-IMPORT,MUST-NOT-IMPORT,MUST-NOT-IMPORT\n",
        encoding="utf-8",
    )
    rows, skipped = parse_lookup_csv(path)
    skipped_l = {h.lower() for h in skipped}
    assert "tax id" in skipped_l
    assert any("dir" in h.lower() for h in skipped)
    assert any("trucker id" in h.lower() for h in skipped)
    assert len(rows) == 1
    assert rows[0]["name"] == "Sample Hauling LLC"
    assert rows[0]["email"] == "ap@example.invalid"
    assert "MUST-NOT-IMPORT" not in repr(rows)
    assert "dir" not in rows[0]
    assert "tax" not in repr(rows[0]).lower()
    assert "CA#" in skipped


def test_select_live_dispatch_year_tab_prefers_current_year_then_highest() -> None:
    tabs = ("TRUCKERS", "2024", "2025", "2026", "Job list")
    assert select_live_dispatch_year_tab(tabs, as_of=date(2026, 8, 27)) == "2026"
    assert select_live_dispatch_year_tab(tabs, as_of=date(2027, 1, 15)) == "2026"
    with_next = tabs + ("2027",)
    assert select_live_dispatch_year_tab(with_next, as_of=date(2027, 3, 1)) == "2027"
    assert select_live_dispatch_year_tab(("Notes", "Pay"), as_of=date(2026, 1, 1)) is None
    assert expected_live_dispatch_year_tab(as_of=date(2031, 12, 31)) == "2031"
