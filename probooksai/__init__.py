"""ProBooks+ai shared library (SQLite, migrations, Excel ``.xlsx`` workbook generation via ``openpyxl``); used by the CLI and desktop app. Re-exports ``build_workbook``."""

from .generator import build_workbook  # noqa: F401

__all__ = ["build_workbook"]
