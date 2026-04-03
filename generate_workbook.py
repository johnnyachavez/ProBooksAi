"""
ProBooks+ai – CLI wrapper
=========================
Thin entry-point that delegates to ``probooksai.generator``.

Run:
    python generate_workbook.py

See **[README — Excel workbook template](README.md#excel-workbook-template-openpyxl)** (repository root).
"""

# Re-export everything so existing imports keep working
from probooksai.generator import (  # noqa: F401
    COA_DATA,
    CUSTOMER_HEADERS,
    VENDOR_HEADERS,
    INVOICE_HEADERS,
    BILL_HEADERS,
    AR_PMT_HEADERS,
    AP_PMT_HEADERS,
    INV_LINE_HEADERS,
    JE_HEADERS,
    SAMPLE_CUSTOMERS,
    SAMPLE_VENDORS,
    SAMPLE_INVOICES,
    SAMPLE_BILLS,
    SAMPLE_AR_PMTS,
    SAMPLE_AP_PMTS,
    SAMPLE_INV_LINES,
    SAMPLE_JES,
    build_workbook,
    OUTPUT_FILE,
)

if __name__ == "__main__":
    build_workbook()
