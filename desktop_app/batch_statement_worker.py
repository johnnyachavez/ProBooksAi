"""
desktop_app.batch_statement_worker
====================================
Background worker for importing multiple bank statement files (PDF, JPG,
PNG, etc.) in one pass.

Each file is processed in sequence:
  1. PDF text layer extraction (fast, no AI)
  2. If no text / few rows found → Claude vision extraction (AI_PROVIDER)
  3. Row deduplication against existing bank_transactions
  4. Batch creation and insert

Emits per-file progress so the UI can show "File 3 of 10: statement_mar.pdf".
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal


class BatchStatementWorker(QThread):
    """Process a list of statement files and import each into the register.

    Signals
    -------
    file_started(index, total, filename)
    file_done(index, total, filename, inserted, skipped)
    file_error(index, total, filename, error_message)
    all_done(total_inserted, total_skipped, errors)
    """

    file_started = Signal(int, int, str)        # index, total, name
    file_done = Signal(int, int, str, int, int)  # index, total, name, inserted, skipped
    file_error = Signal(int, int, str, str)      # index, total, name, error
    all_done = Signal(int, int, list)            # inserted, skipped, [(name, error)]

    def __init__(
        self,
        db_path: str,
        account_id: int,
        file_paths: list[str],
    ):
        super().__init__()
        self._db_path = db_path
        self._account_id = account_id
        self._file_paths = file_paths
        self._cancel = False

    def request_cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        from probooksai.bank_import import BankDatabase
        from probooksai.statement_extract import parse_statement_text

        total = len(self._file_paths)
        total_inserted = 0
        total_skipped = 0
        errors: list[tuple[str, str]] = []

        bdb = BankDatabase(db_path=self._db_path)

        for idx, path in enumerate(self._file_paths):
            if self._cancel:
                break
            name = Path(path).name
            self.file_started.emit(idx + 1, total, name)
            try:
                rows = self._extract_rows(path)
                if not rows:
                    errors.append((name, "No transaction rows found."))
                    self.file_error.emit(idx + 1, total, name, "No transaction rows found.")
                    continue

                # Infer statement dates from the rows themselves
                dates = [r.get("txn_date", "") for r in rows if r.get("txn_date")]
                start = min(dates) if dates else ""
                end = max(dates) if dates else ""

                try:
                    from probooksai.rules_engine import apply_rules_to_parsed_rows
                    apply_rules_to_parsed_rows(bdb._conn, rows)
                except Exception:
                    pass

                batch_id = bdb.create_batch(
                    self._account_id,
                    filename=name,
                    statement_start=start,
                    statement_end=end,
                    beginning_balance=None,
                    ending_balance=None,
                )
                result = bdb.import_transactions(batch_id, self._account_id, rows)
                inserted = result.get("inserted", 0)
                skipped = result.get("skipped", 0)
                total_inserted += inserted
                total_skipped += skipped
                self.file_done.emit(idx + 1, total, name, inserted, skipped)

            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                errors.append((name, msg))
                self.file_error.emit(idx + 1, total, name, msg)

        bdb.close()
        self.all_done.emit(total_inserted, total_skipped, errors)

    # -- extraction ----------------------------------------------------------

    def _extract_rows(self, path: str) -> list[dict]:
        """Try text extraction first; fall back to Claude vision for scanned files."""
        ext = Path(path).suffix.lower()
        is_pdf = ext == ".pdf"
        is_image = ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".tif")

        if is_pdf:
            rows = self._extract_pdf_rows(path)
            if rows:
                return rows
            # Scanned PDF — try Claude vision
            return self._extract_via_claude(path, "application/pdf")

        if is_image:
            mime_map = {
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".webp": "image/webp",
                ".gif": "image/gif", ".bmp": "image/bmp",
                ".tiff": "image/tiff", ".tif": "image/tiff",
            }
            mime = mime_map.get(ext, "image/jpeg")
            return self._extract_via_claude(path, mime)

        return []

    def _extract_pdf_rows(self, path: str) -> list[dict]:
        """Extract rows from a digital (text-layer) PDF."""
        try:
            from probooksai.statement_pdf import extract_text_from_pdf
            from probooksai.statement_extract import parse_statement_text
            text = extract_text_from_pdf(path)
            if not (text or "").strip():
                return []
            return parse_statement_text(text)
        except Exception:
            return []

    def _extract_via_claude(self, path: str, mime: str) -> list[dict]:
        """Use Claude vision to extract transaction rows from a scanned statement."""
        import json, os
        try:
            from ai.extractor import extract_document
            result = extract_document(path, mime)
            if result.error or not result.line_items:
                # If Claude returned line_items, use them; otherwise try notes field
                if result.line_items:
                    return self._line_items_to_rows(result)
                # Fall back: parse any text Claude put in notes
                return []
            return self._line_items_to_rows(result)
        except Exception:
            return []

    def _line_items_to_rows(self, result) -> list[dict]:
        """Convert ExtractionResult line_items to bank import row dicts."""
        rows = []
        for item in (result.line_items or []):
            desc = item.get("description", "")
            amt = item.get("amount")
            if amt is None:
                continue
            rows.append({
                "txn_date": result.doc_date or "",
                "description": desc,
                "amount": float(amt),
                "ref_number": "",
            })
        return rows
