"""Bank Statement Intake — phase 1 extractor tests (CSV / pasted text / PDF).

Covers the normalized 10-field ``BankStatementIntakeRow`` produced by
:mod:`probooksai.bank_statement_intake` for all three input shapes the
review-first intake flow accepts. None of these tests touch the database
or post into the Bank Register — Phase 1 is staging-only.
"""

from __future__ import annotations

from probooksai.bank_statement_intake import (
    CONFIDENCE_REVIEW_THRESHOLD,
    SOURCE_TYPE_CSV,
    SOURCE_TYPE_PDF,
    SOURCE_TYPE_TEXT,
    BankStatementIntakeRow,
    detect_csv_column_plan,
    extract_csv_statement,
    extract_pasted_text_statement,
    extract_pdf_statement,
    normalized_field_names,
)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_normalized_field_names_include_all_required_phase1_fields() -> None:
    """The 10-field schema in the spec must be present in stable order."""
    expected = (
        "txn_date",
        "description_raw",
        "debit",
        "credit",
        "amount_signed",
        "running_balance",
        "source_type",
        "source_ref",
        "confidence",
        "needs_review",
    )
    assert normalized_field_names() == expected


def test_intake_row_to_dict_round_trip_keeps_all_fields() -> None:
    row = BankStatementIntakeRow(
        txn_date="2026-04-18",
        description_raw="Test",
        debit=10.0,
        credit=None,
        amount_signed=-10.0,
        running_balance=99.0,
        source_type=SOURCE_TYPE_CSV,
        source_ref="x.csv#L2",
        confidence=1.0,
        needs_review=False,
    )
    d = row.to_dict()
    for field_name in normalized_field_names():
        assert field_name in d


# ---------------------------------------------------------------------------
# CSV intake
# ---------------------------------------------------------------------------


_CSV_SIGNED_AMOUNT_SAMPLE = (
    "Transaction Date,Description,Amount,Balance\n"
    "01/02/2026,Coffee Shop,-4.50,995.50\n"
    "01/03/2026,Payroll Deposit,1500.00,2495.50\n"
    "01/04/2026,ATM Withdrawal,(80.00),2415.50\n"
)


def test_detect_csv_column_plan_signed_amount_layout() -> None:
    plan = detect_csv_column_plan(
        ["Transaction Date", "Description", "Amount", "Balance"]
    )
    assert plan.date_col == "Transaction Date"
    assert plan.description_col == "Description"
    assert plan.amount_col == "Amount"
    assert plan.balance_col == "Balance"
    assert plan.debit_col is None
    assert plan.credit_col is None


def test_extract_csv_signed_amount_layout_normalizes_each_row() -> None:
    rows = extract_csv_statement(
        _CSV_SIGNED_AMOUNT_SAMPLE, source_ref="statements/jan.csv"
    )
    assert len(rows) == 3
    for r in rows:
        assert r.source_type == SOURCE_TYPE_CSV
        assert r.source_ref.startswith("statements/jan.csv#L")
        assert r.txn_date.startswith("2026-01-")
        assert r.confidence >= CONFIDENCE_REVIEW_THRESHOLD
        assert r.needs_review is False

    # Outflow → negative signed amount + debit magnitude only.
    coffee = rows[0]
    assert coffee.amount_signed == -4.50
    assert coffee.debit == 4.50
    assert coffee.credit is None
    assert coffee.running_balance == 995.50

    # Inflow → positive signed amount + credit magnitude only.
    payroll = rows[1]
    assert payroll.amount_signed == 1500.00
    assert payroll.credit == 1500.00
    assert payroll.debit is None
    assert payroll.running_balance == 2495.50

    # Parentheses are interpreted as negative.
    atm = rows[2]
    assert atm.amount_signed == -80.00
    assert atm.debit == 80.00


_CSV_DEBIT_CREDIT_SAMPLE = (
    "Date,Memo,Withdrawals,Deposits,Running Balance\n"
    "2026-02-01,Rent,1200.00,,3800.00\n"
    "2026-02-02,Refund,,25.00,3825.00\n"
)


def test_detect_csv_column_plan_two_column_debit_credit_layout() -> None:
    plan = detect_csv_column_plan(
        ["Date", "Memo", "Withdrawals", "Deposits", "Running Balance"]
    )
    assert plan.date_col == "Date"
    assert plan.description_col == "Memo"
    assert plan.debit_col == "Withdrawals"
    assert plan.credit_col == "Deposits"
    assert plan.balance_col == "Running Balance"
    assert plan.amount_col is None


def test_extract_csv_debit_credit_layout_signs_match_convention() -> None:
    rows = extract_csv_statement(_CSV_DEBIT_CREDIT_SAMPLE, source_ref="feb.csv")
    assert len(rows) == 2

    rent = rows[0]
    assert rent.txn_date == "2026-02-01"
    assert rent.debit == 1200.00
    assert rent.credit is None
    assert rent.amount_signed == -1200.00
    assert rent.running_balance == 3800.00
    assert rent.needs_review is False

    refund = rows[1]
    assert refund.txn_date == "2026-02-02"
    assert refund.debit is None
    assert refund.credit == 25.00
    assert refund.amount_signed == 25.00
    assert refund.running_balance == 3825.00
    assert refund.needs_review is False


def test_extract_csv_debit_and_credit_both_filled_flags_needs_review() -> None:
    """Ambiguous bank exports (both sides filled) must be flagged for review."""
    csv_text = (
        "Date,Description,Debit,Credit\n"
        "01/05/2026,Suspicious Row,10.00,5.00\n"
    )
    rows = extract_csv_statement(csv_text, source_ref="x.csv")
    assert len(rows) == 1
    assert rows[0].needs_review is True
    assert rows[0].debit == 10.00
    assert rows[0].credit == 5.00
    # Sign reflects the larger magnitude (debit dominates).
    assert rows[0].amount_signed == -10.00


def test_extract_csv_unparseable_date_or_amount_marks_needs_review() -> None:
    csv_text = (
        "Date,Description,Amount\n"
        "not-a-date,Bad date row,10.00\n"
        "01/06/2026,Bad amount row,not-a-number\n"
        ",Empty row,\n"
    )
    rows = extract_csv_statement(csv_text, source_ref="bad.csv")
    assert len(rows) == 3
    for r in rows:
        assert r.needs_review is True
    assert rows[0].txn_date == ""
    assert rows[0].amount_signed == 10.00
    assert rows[1].txn_date == "2026-01-06"
    assert rows[1].amount_signed is None
    assert rows[2].txn_date == ""
    assert rows[2].amount_signed is None


def test_extract_csv_empty_input_returns_no_rows() -> None:
    assert extract_csv_statement("") == []
    assert extract_csv_statement("   \n   ") == []


def test_extract_csv_unknown_headers_still_returns_rows_for_review() -> None:
    """When no columns are recognized, every row is staged with low confidence."""
    csv_text = "Foo,Bar\nhello,world\n"
    rows = extract_csv_statement(csv_text, source_ref="weird.csv")
    assert len(rows) == 1
    r = rows[0]
    assert r.txn_date == ""
    assert r.amount_signed is None
    assert r.needs_review is True
    assert r.source_type == SOURCE_TYPE_CSV
    assert r.source_ref == "weird.csv#L2"


def test_extract_csv_source_ref_carries_line_number_for_traceability() -> None:
    rows = extract_csv_statement(_CSV_SIGNED_AMOUNT_SAMPLE, source_ref="jan.csv")
    refs = [r.source_ref for r in rows]
    assert refs == ["jan.csv#L2", "jan.csv#L3", "jan.csv#L4"]


# ---------------------------------------------------------------------------
# Pasted-text intake
# ---------------------------------------------------------------------------


_TEXT_SAMPLE = (
    "Date       Description                 Amount   Balance\n"
    "01/02/2026 Coffee Shop                 -4.50    995.50\n"
    "01/03/2026 Payroll Deposit             1500.00  2495.50\n"
    "01/04/2026 ATM Withdrawal              (80.00)  2415.50\n"
    "skip me — no date here\n"
    "2026-01-05 Wire Transfer               -200.00  2215.50\n"
)


def test_extract_pasted_text_statement_handles_signed_paren_iso_dates() -> None:
    rows = extract_pasted_text_statement(_TEXT_SAMPLE, source_ref="paste-1")
    assert len(rows) == 4
    coffee, payroll, atm, wire = rows

    assert coffee.txn_date == "2026-01-02"
    assert coffee.amount_signed == -4.50
    assert coffee.debit == 4.50
    assert coffee.credit is None
    assert coffee.running_balance == 995.50
    assert "Coffee Shop" in coffee.description_raw

    assert payroll.amount_signed == 1500.00
    assert payroll.credit == 1500.00
    assert payroll.debit is None
    assert payroll.running_balance == 2495.50

    assert atm.amount_signed == -80.00
    assert atm.debit == 80.00

    assert wire.txn_date == "2026-01-05"
    assert wire.amount_signed == -200.00
    assert wire.running_balance == 2215.50

    for r in rows:
        assert r.source_type == SOURCE_TYPE_TEXT
        assert r.source_ref.startswith("paste-1#L")
        assert r.confidence >= CONFIDENCE_REVIEW_THRESHOLD
        assert r.needs_review is False


def test_extract_pasted_text_statement_skips_non_statement_lines() -> None:
    text = (
        "MY BANK STATEMENT\n"
        "Account: 1234\n"
        "01/02/2026 Real Row 12.34\n"
        "no date 9.99\n"
    )
    rows = extract_pasted_text_statement(text)
    assert len(rows) == 1
    assert rows[0].txn_date == "2026-01-02"
    assert rows[0].amount_signed == 12.34


def test_extract_pasted_text_statement_dr_cr_suffix_drives_sign() -> None:
    text = "01/06/2026 Service charge 5.00 DR\n01/06/2026 Interest 0.10 CR\n"
    rows = extract_pasted_text_statement(text)
    assert len(rows) == 2
    assert rows[0].amount_signed == -5.00
    assert rows[0].debit == 5.00
    assert rows[1].amount_signed == 0.10
    assert rows[1].credit == 0.10


def test_extract_pasted_text_statement_empty_input_returns_no_rows() -> None:
    assert extract_pasted_text_statement("") == []
    assert extract_pasted_text_statement("    \n   \n") == []


# ---------------------------------------------------------------------------
# PDF intake (text-layer only; image OCR explicitly out of scope)
# ---------------------------------------------------------------------------


def test_extract_pdf_statement_uses_text_layer_via_monkeypatched_extractor(
    monkeypatch,
) -> None:
    """``extract_pdf_statement`` reuses the text extractor under a PDF source label."""
    fake_text = (
        "01/02/2026 Coffee Shop -4.50 995.50\n"
        "01/03/2026 Payroll Deposit 1500.00 2495.50\n"
    )

    def _fake_extract(path: str) -> str:
        assert path == "/tmp/fake-statement.pdf"
        return fake_text

    monkeypatch.setattr(
        "probooksai.statement_pdf.extract_text_from_pdf", _fake_extract
    )
    rows = extract_pdf_statement(
        "/tmp/fake-statement.pdf", source_ref="january-statement.pdf"
    )
    assert len(rows) == 2
    for r in rows:
        assert r.source_type == SOURCE_TYPE_PDF
        assert r.source_ref.startswith("january-statement.pdf#L")
    assert rows[0].txn_date == "2026-01-02"
    assert rows[0].amount_signed == -4.50
    assert rows[1].amount_signed == 1500.00


def test_extract_pdf_statement_falls_back_to_basename_when_source_ref_blank(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "probooksai.statement_pdf.extract_text_from_pdf",
        lambda path: "01/02/2026 Coffee 4.50\n",
    )
    rows = extract_pdf_statement("/tmp/sub/account-1234.pdf")
    assert len(rows) == 1
    assert rows[0].source_type == SOURCE_TYPE_PDF
    assert rows[0].source_ref.startswith("account-1234.pdf#L")


def test_extract_pdf_statement_empty_text_layer_returns_no_rows(monkeypatch) -> None:
    """Scanned/image-only PDFs (no text layer) come back empty — OCR is out of scope."""
    monkeypatch.setattr(
        "probooksai.statement_pdf.extract_text_from_pdf", lambda path: ""
    )
    assert extract_pdf_statement("/tmp/scanned.pdf") == []


# ---------------------------------------------------------------------------
# Phase-1 invariants
# ---------------------------------------------------------------------------


def test_phase1_extractors_never_classify_to_coa_or_set_account_id() -> None:
    """Schema must not carry COA / register identifiers in phase 1."""
    rows = extract_csv_statement(_CSV_SIGNED_AMOUNT_SAMPLE, source_ref="x.csv")
    rows += extract_pasted_text_statement(_TEXT_SAMPLE)
    for r in rows:
        d = r.to_dict()
        assert "coa_id" not in d
        assert "account_id" not in d
        assert "bank_transaction_id" not in d


def test_phase1_extractors_only_emit_known_source_types() -> None:
    rows = (
        extract_csv_statement(_CSV_SIGNED_AMOUNT_SAMPLE, source_ref="x.csv")
        + extract_pasted_text_statement(_TEXT_SAMPLE)
    )
    seen = {r.source_type for r in rows}
    assert seen.issubset({SOURCE_TYPE_CSV, SOURCE_TYPE_PDF, SOURCE_TYPE_TEXT})
