"""Shared **Excel COA workbook** argparse epilog for ``probooks.cli`` and ``desktop_app.main``.

Points at ``python generate_workbook.py`` and the README Excel template; implementation is ``probooksai.generator``.
Also surfaces **SQLite backup** parity (CLI **probooks backup** / **restore**, desktop **File → Backup/Restore**, **probooks.backup**)
and that **exported CSV** from the desktop app and **probooks import csv --errors-out** use **UTF-8 BOM** for Excel.
"""

EXCEL_COA_WORKBOOK_ARGPARSE_EPILOG = (
    "Excel COA workbook (openpyxl): python generate_workbook.py; see README (Excel workbook template). "
    "SQLite company file: probooks backup/restore (probooks.backup); desktop File → Backup/Restore. "
    "Desktop CSV exports and probooks import csv --errors-out use UTF-8 BOM for Excel."
)
