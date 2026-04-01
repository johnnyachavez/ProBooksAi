"""Standard data directory and database path (Windows-friendly)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_APP_DIR_NAME = "ProBooks+ai"
_DB_NAME = "probooks.db"


def app_data_dir() -> Path:
    """Return per-user application data directory for ProBooks+ai."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / _APP_DIR_NAME
        return Path.home() / "AppData" / "Local" / _APP_DIR_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / _APP_DIR_NAME
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / _APP_DIR_NAME.lower().replace("+", "")
    return Path.home() / ".local" / "share" / _APP_DIR_NAME.lower().replace("+", "")


def default_db_path() -> Path:
    return app_data_dir() / _DB_NAME


def ensure_app_dirs() -> Path:
    d = app_data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d
