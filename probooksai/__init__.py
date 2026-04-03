"""ProBooks+ai shared library (SQLite, migrations, Excel ``.xlsx`` workbook generation via ``openpyxl``); used by the ``probooks`` CLI and desktop app. Re-exports ``build_workbook``. The CLI/desktop ``--help`` Excel workbook line lives in ``probooks.help_epilog``."""

from .generator import build_workbook  # noqa: F401

__all__ = ["build_workbook"]
