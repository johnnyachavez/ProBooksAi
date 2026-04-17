"""
Company identity (legal / contact) stored in ``company_settings`` (extensions schema).

Used for invoice PDF/print headers and main-window display; edit via **File → Create Company File**
or by updating the same keys programmatically.
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


def save_company_identity(
    conn: sqlite3.Connection,
    *,
    name: str,
    address: str = "",
    phone: str = "",
    email: str = "",
    tax_id: str = "",
) -> None:
    """Persist company identity fields (replaces prior values for each key)."""
    set_setting(conn, KEY_COMPANY_NAME, (name or "").strip())
    set_setting(conn, KEY_COMPANY_ADDRESS, (address or "").strip())
    set_setting(conn, KEY_COMPANY_PHONE, (phone or "").strip())
    set_setting(conn, KEY_COMPANY_EMAIL, (email or "").strip())
    set_setting(conn, KEY_COMPANY_TAX_ID, (tax_id or "").strip())


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
