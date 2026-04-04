"""Regenerate ``tests/fixtures/issue_11_chase_statement.pdf`` (synthetic text-layer PDF).

The file is **not** the real GitHub Issue #11 image; it is a tiny PDF with one bank-like
line so Phase 7 tests can exercise ``extract_text_from_pdf`` + ``parse_statement_text``.
"""

from __future__ import annotations

from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    dest = root / "tests" / "fixtures" / "issue_11_chase_statement.pdf"
    stream = b"BT /F1 12 Tf 72 720 Td (2024-01-05  COFFEE SHOP  -4.50) Tj ET"
    stream_len = len(stream)

    header = b"%PDF-1.4\n"
    parts: list[bytes] = []
    positions: list[int] = []

    def add_obj(n: int, body: bytes) -> None:
        positions.append(len(header) + sum(len(p) for p in parts))
        parts.append(f"{n} 0 obj\n".encode())
        parts.append(body)
        parts.append(b"\nendobj\n")

    add_obj(1, b"<< /Type /Catalog /Pages 2 0 R >>")
    add_obj(2, b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    add_obj(
        3,
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    )
    add_obj(
        4,
        f"<< /Length {stream_len} >>\nstream\n".encode() + stream + b"\nendstream",
    )
    add_obj(5, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    body = header + b"".join(parts)
    xref_pos = len(body)
    xref_lines = [b"xref\n0 6\n", b"0000000000 65535 f \n"]
    for i in range(5):
        xref_lines.append(f"{positions[i]:010d} 00000 n \n".encode())
    xref = b"".join(xref_lines)
    trailer = (
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n"
        + str(xref_pos).encode()
        + b"\n%%EOF\n"
    )
    out = body + xref + trailer
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(out)
    print(f"Wrote {dest} ({len(out)} bytes)")


if __name__ == "__main__":
    main()
