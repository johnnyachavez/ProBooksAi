"""ProBooks+ai shared library (SQLite, migrations, workbooks); used by the CLI and desktop app. Re-exports ``build_workbook``."""

from .generator import build_workbook  # noqa: F401

__all__ = ["build_workbook"]
