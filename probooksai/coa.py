"""
probooksai.coa
==============
Helpers to load the Chart of Accounts from ``generate_workbook.py`` and
expose it in a consistent format for UI dropdowns and AI categorisation.
"""

from __future__ import annotations

from typing import NamedTuple


class COAEntry(NamedTuple):
    account_number: str
    account_name: str
    account_type: str      # Asset / Liability / Equity / Revenue / Expense
    sub_type: str
    normal_balance: str    # Debit / Credit
    description: str

    @property
    def display(self) -> str:
        return f"{self.account_number} – {self.account_name}"


def load_coa() -> list[COAEntry]:
    """
    Load the Chart of Accounts from the workbook generator module.

    Returns a list of :class:`COAEntry` objects sorted by account number.
    """
    from generate_workbook import COA_DATA  # type: ignore[import]

    entries: list[COAEntry] = []
    for row in COA_DATA:
        acct_no, name, acct_type, sub_type, normal_bal, description = row[:6]
        entries.append(
            COAEntry(
                account_number=acct_no,
                account_name=name,
                account_type=acct_type,
                sub_type=sub_type,
                normal_balance=normal_bal,
                description=description,
            )
        )
    return sorted(entries, key=lambda e: e.account_number)


def coa_display_list(coa: list[COAEntry] | None = None) -> list[str]:
    """Return a list of ``'NNNN – Account Name'`` strings for UI dropdowns."""
    if coa is None:
        coa = load_coa()
    return [e.display for e in coa]
