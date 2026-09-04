# Company Setup storage + Invoice letterhead usage (2026-04-16)

This note documents where Company info is entered/stored in ProBooksAi, how invoice print/PDF uses it today, what is still partial, and what tests were run.

## Where company info is entered / stored

**UI path**
- More → Business → Company (fourth hub sub-tab: Company)

**UI fields**
- Company name
- Address line 1
- Address line 2
- City
- State
- Zip
- Phone
- Email

Each field is currently a `QLineEdit`.

**Persistence**
- Clicking **Save company info** or pressing **Ctrl+S** while that sub-tab has focus writes to the open company **SQLite** DB via:
  - `probooksai.business.set_setting`
  - table/namespace: `company_settings`

**Keys written**
- `company_setup_name`
- `company_setup_addr1`
- `company_setup_addr2`
- `company_setup_city`
- `company_setup_state`
- `company_setup_zip`
- `company_setup_phone`
- `company_setup_email`

## How invoice PDF / print uses it

**Call chain**
- `invoice_html_string` → `_letterhead_plain_from_company_settings` → `build_invoice_print_html(..., company_block_plain=...)`

**How the sender “letterhead” block is built**
`_letterhead_plain_from_company_settings` builds a multiline plain-text sender block using this precedence:

1. If `invoice_company_block` is set, it is used **as-is** (full override).
2. Else it uses structured Company Setup fields in this order, omitting blank lines:
   - name
   - addr1
   - addr2
   - one combined line: `city, ST ZIP` (from city/state/zip)
   - phone
   - email
3. If that yields nothing, it falls back to legacy keys:
   - `invoice_company_name`
   - `invoice_company_address`
   - `invoice_company_phone`

That resulting plain-text block is passed to:
- `build_invoice_print_html(..., company_block_plain=...)`

This is the same path used by:
- Print…
- Export PDF…
- `save_invoice_pdf`

## What remains partial (current truths)

- There is **no migration** from old `invoice_company_*` settings into the newer `company_setup_*` keys.
  - Legacy keys still work until you re-enter data under **More → Business → Company**.
- Overrides:
  - If `invoice_company_block` exists (if ever used), it **still overrides** the structured Company Setup fields.
- Other documents (non-invoice) do **not** use this Company screen yet.

## Update (2026-09-04) — paper template lock + MC / DOT

The print/PDF template now matches the Chavan paper invoice exactly, and every PDF in the
product comes off it:

- Letterhead precedence gained a step: `invoice_company_block` → `company_setup_*` →
  **My Company identity** (`company_name`, `company_address`, `company_phone`,
  `company_email`, `company_tax_id`) → legacy `invoice_company_*`.
- MC / DOT are appended to whichever block wins, from `company_mc_number` /
  `company_dot_number` (fallback `company_setup_mc_number` / `company_setup_dot_number`).
  They are entered on **My Company → Edit** (MC # / DOT #) and are never hardcoded.
- Grid columns are `Serviced On, JL #, Description, BOL#, Qty, Rate, Amount`; the totals
  block is `Subtotal` → CO/compliance-fee line → `Total`; the footer prints the invoice's
  saved terms (default `NET 30`) above the thank-you line.
- `probooksai.invoice_pdf.render_invoice_pdf` (FastAPI `GET /invoices/{id}/pdf`, used for
  bot downloads) is a wrapper around `desktop_app.invoice_pdf.save_invoice_pdf` instead of
  a separate reportlab layout. Server worker threads cannot start Qt, so a file-backed
  company DB is rendered in a child process.

## Tests run and results

Commands executed:

- `pytest tests/test_extensions_business.py::test_invoice_html_string_uses_company_setup_letterhead tests/test_extensions_business.py::test_invoice_html_string_legacy_invoice_company_keys_fallback tests/test_extensions_business.py::test_invoice_html_string_invoice_company_block_overrides_setup tests/test_invoice_print_html.py tests/test_invoice_screen.py -q`
  - Result: **23 passed**

- `pytest tests/test_desktop_main_contract.py::test_main_tab_widgets_have_root_hover_tooltips -q`
  - Result: **1 passed**