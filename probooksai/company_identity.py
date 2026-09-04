"""
Company identity (legal / contact) stored in ``company_settings`` (extensions schema).

Used for invoice PDF/print headers and main-window display. Values are stored in the open company file’s
``company_settings`` table. Capture at setup via **File → New Company…** (or update the same keys
programmatically).
"""

from __future__ import annotations

import sqlite3

from probooksai.business import get_setting, set_setting

# Keys in ``company_settings`` (single source of truth for identity text)
KEY_COMPANY_NAME = "company_name"
KEY_COMPANY_ADDRESS = "company_address"
KEY_COMPANY_PHONE = "company_phone"
KEY_COMPANY_EMAIL = "company_email"
KEY_COMPANY_TAX_ID = "company_tax_id"
KEY_BUSINESS_TYPE = "company_business_type"
KEY_TAX_STRUCTURE = "company_tax_structure"
# Motor-carrier authority numbers (printed on the invoice letterhead). Written by the
# My Company page, not by ``save_company_identity`` — that call replaces every key it owns.
KEY_MC_NUMBER = "company_mc_number"
KEY_DOT_NUMBER = "company_dot_number"

# Suggested values; UI dialog picks from these but the column accepts any free text.
BUSINESS_TYPES = (
    "Sole Proprietorship",
    "Partnership",
    "LLC",
    "S Corporation",
    "C Corporation",
    "Nonprofit",
    "Other",
)
TAX_STRUCTURES = (
    "Sole Proprietor (Schedule C)",
    "Partnership (1065)",
    "S Corporation (1120-S)",
    "C Corporation (1120)",
    "LLC – Single-member (disregarded)",
    "LLC – Multi-member (1065)",
    "Nonprofit (990)",
    "Other",
)


def save_company_identity(
    conn: sqlite3.Connection,
    *,
    name: str,
    address: str = "",
    phone: str = "",
    email: str = "",
    tax_id: str = "",
    business_type: str = "",
    tax_structure: str = "",
) -> None:
    """Persist company identity fields (replaces prior values for each key).

    *business_type* and *tax_structure* default to empty for backward compatibility
    with callers/tests that predate the New Company setup wizard.
    """
    set_setting(conn, KEY_COMPANY_NAME, (name or "").strip())
    set_setting(conn, KEY_COMPANY_ADDRESS, (address or "").strip())
    set_setting(conn, KEY_COMPANY_PHONE, (phone or "").strip())
    set_setting(conn, KEY_COMPANY_EMAIL, (email or "").strip())
    set_setting(conn, KEY_COMPANY_TAX_ID, (tax_id or "").strip())
    set_setting(conn, KEY_BUSINESS_TYPE, (business_type or "").strip())
    set_setting(conn, KEY_TAX_STRUCTURE, (tax_structure or "").strip())


def get_company_identity(conn: sqlite3.Connection) -> dict[str, str]:
    """Return the full saved identity (all seven fields, empty strings when unset)."""
    return {
        "name": get_setting(conn, KEY_COMPANY_NAME, "").strip(),
        "address": get_setting(conn, KEY_COMPANY_ADDRESS, "").strip(),
        "phone": get_setting(conn, KEY_COMPANY_PHONE, "").strip(),
        "email": get_setting(conn, KEY_COMPANY_EMAIL, "").strip(),
        "tax_id": get_setting(conn, KEY_COMPANY_TAX_ID, "").strip(),
        "business_type": get_setting(conn, KEY_BUSINESS_TYPE, "").strip(),
        "tax_structure": get_setting(conn, KEY_TAX_STRUCTURE, "").strip(),
    }


def is_company_setup_complete(conn: sqlite3.Connection) -> bool:
    """Return ``True`` once the New Company wizard has been completed for this file.

    Setup is considered complete when **company_name**, **business_type**, and
    **tax_structure** are all non-empty — these are the three required fields the
    wizard enforces before save. Address / Phone / Email / Tax ID are recommended
    but not strictly blocking, mirroring real-world readiness for invoicing.
    """
    name = get_setting(conn, KEY_COMPANY_NAME, "").strip()
    btype = get_setting(conn, KEY_BUSINESS_TYPE, "").strip()
    tstruct = get_setting(conn, KEY_TAX_STRUCTURE, "").strip()
    return bool(name) and bool(btype) and bool(tstruct)


def company_identity_print_fields(conn: sqlite3.Connection) -> dict[str, str]:
    """Values for invoice print/PDF company header (same keys as :func:`company_identity_plain_block`)."""
    return {
        "name": get_setting(conn, KEY_COMPANY_NAME, "").strip(),
        "address": get_setting(conn, KEY_COMPANY_ADDRESS, "").strip(),
        "phone": get_setting(conn, KEY_COMPANY_PHONE, "").strip(),
        "email": get_setting(conn, KEY_COMPANY_EMAIL, "").strip(),
        "tax_id": get_setting(conn, KEY_COMPANY_TAX_ID, "").strip(),
        "mc_number": get_setting(conn, KEY_MC_NUMBER, "").strip(),
        "dot_number": get_setting(conn, KEY_DOT_NUMBER, "").strip(),
    }


def company_identity_plain_block(conn: sqlite3.Connection) -> str:
    """Multi-line plain text for invoice/PDF top-left company block (empty lines omitted)."""
    name = get_setting(conn, KEY_COMPANY_NAME, "").strip()
    addr = get_setting(conn, KEY_COMPANY_ADDRESS, "").strip()
    phone = get_setting(conn, KEY_COMPANY_PHONE, "").strip()
    email = get_setting(conn, KEY_COMPANY_EMAIL, "").strip()
    tax = get_setting(conn, KEY_COMPANY_TAX_ID, "").strip()
    lines: list[str] = []
    if name:
        lines.append(name)
    if addr:
        lines.extend(addr.splitlines())
    if phone:
        lines.append(f"Phone: {phone}")
    if email:
        lines.append(f"Email: {email}")
    if tax:
        lines.append(f"Tax ID: {tax}")
    return "\n".join(lines)
