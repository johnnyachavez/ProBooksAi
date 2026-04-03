"""HTML escaping for generated markup (e.g. invoice PDF HTML)."""

from __future__ import annotations

import html


def escape_html_text(s: object) -> str:
    """Escape *s* for safe use as HTML element text (``quote=True``)."""
    return html.escape(str(s or ""), quote=True)
