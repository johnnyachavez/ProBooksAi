"""Shared **Excel COA workbook** argparse epilog for ``probooks.cli`` and ``desktop_app.main``.

Points at ``python generate_workbook.py`` and the README Excel template; implementation is ``probooksai.generator``.
Also surfaces **SQLite backup** parity (CLI **probooks backup** / **restore**, desktop **File → Backup/Restore**, **probooks.backup**);
**exported CSV** (desktop and **probooks import csv --errors-out**) as **UTF-8 BOM** for Excel;
and **bank CSV import** (desktop Bank Import and **probooks import csv**) reading **UTF-8 with optional BOM**.
"""

EXCEL_COA_WORKBOOK_ARGPARSE_EPILOG = (
    "Excel COA workbook (openpyxl): python generate_workbook.py; see README (Excel workbook template). "
    "SQLite company file: probooks backup/restore (probooks.backup); desktop File → Backup/Restore. "
    "Desktop CSV exports and probooks import csv --errors-out use UTF-8 BOM for Excel. "
    "Bank CSV import (desktop Bank Import and probooks import csv) reads UTF-8 with optional BOM."
)
