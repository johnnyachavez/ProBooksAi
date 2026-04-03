"""ProBooks+ai — SQLite-backed ``probooks`` CLI package (shared schema with the PySide6 desktop app)."""

from __future__ import annotations


def __getattr__(name: str):
    if name == "__version__":
        import importlib.metadata

        try:
            return importlib.metadata.version("probooks-ai")
        except importlib.metadata.PackageNotFoundError:
            return "0.1.0"
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
