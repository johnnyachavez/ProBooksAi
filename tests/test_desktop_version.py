"""desktop_app.version — no PySide6 import required."""

from __future__ import annotations

import importlib.metadata

import probooks

from desktop_app import version as version_mod
from desktop_app.version import application_version


def test_application_version_is_non_empty():
    v = application_version()
    assert isinstance(v, str)
    assert len(v) >= 3


def test_probooks_version_matches_application_version():
    assert probooks.__version__ == application_version()


def test_version_from_pyproject_reads_project_section():
    v = version_mod._version_from_pyproject_toml()
    assert v is not None
    assert v == probooks.__version__


def test_application_version_falls_back_to_pyproject_when_metadata_missing(monkeypatch):
    parsed = version_mod._version_from_pyproject_toml()
    assert parsed is not None

    def _raise(_name: str) -> str:
        raise importlib.metadata.PackageNotFoundError

    monkeypatch.setattr(importlib.metadata, "version", _raise)
    assert version_mod.application_version() == parsed
