"""
Bundle module — combine an invoice record and its attachments into a ZIP file.

A true PDF-merge step is optional for the initial slice; this module
produces a ZIP archive containing all related files so users can download
everything as one unit.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path


def build_zip(document_id: str, attachment_paths: list[str | Path]) -> bytes:
    """Return a ZIP archive containing all *attachment_paths* for *document_id*.

    Args:
        document_id: Identifier used to name the archive members sensibly.
        attachment_paths: Paths to files that should be bundled together.

    Returns:
        Raw bytes of a ZIP file ready to be streamed to the client.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in attachment_paths:
            p = Path(path)
            if p.exists():
                arcname = f"{document_id}/{p.name}"
                zf.write(p, arcname=arcname)
    buf.seek(0)
    return buf.read()
