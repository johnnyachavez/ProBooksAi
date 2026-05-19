"""
desktop_app.batch_statement_worker
====================================
Background worker for importing multiple bank statement files (PDF, JPG,
PNG, etc.) in one pass.

Each file is processed in sequence:
  1. PDF text layer extraction (fast, no AI)
  2. If no text / few rows found → Claude vision extraction (AI_PROVIDER)
  3. Deposit rows (amount > 0) are filtered out — deposits must be entered
     manually so they can be matched to invoices / received payments.
  4. Row deduplication against existing bank_transactions
  5. Batch creation and insert

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
        """Extract rows from a digital (text-layer) PDF.

        Strategy:
          1. Try section-based parser (Chase-style: DEPOSITS AND ADDITIONS,
             ATM & DEBIT CARD WITHDRAWALS, ELECTRONIC WITHDRAWALS, FEES …).
             This handles the vast majority of Chase/JPMorgan statements.
          2. Fall back to the generic line-regex parser for other banks.

        Deposits and checks are excluded by default; ACH/online payments are
        flagged but still returned (caller may filter further).
        """
        import os
        try:
            from probooksai.statement_pdf import extract_text_from_pdf
            text = extract_text_from_pdf(path)
            if not (text or "").strip():
                return []

            # ── Pass 1: section-aware parser (Chase format) ──────────────────
            try:
                from probooksai.statement_section_parser import parse_section_statement
                # Infer year from filename (e.g. 20220131-statements-…)
                import re as _re
                fname = os.path.basename(path)
                m = _re.match(r"(\d{4})", fname)
                default_year = int(m.group(1)) if m else __import__("datetime").date.today().year
                entries = parse_section_statement(text, default_year=default_year)
                # Keep only entries that are included by default (excludes deposits,
                # checks, ACH — exactly what we want for auto-import)
                rows = [
                    {
                        "txn_date":    e.txn_date,
                        "description": e.description,
                        "amount":      e.amount,
                        "ref_number":  "",
                    }
                    for e in entries
                    if e.include and not e.is_ach
                ]
                if rows:
                    return rows
            except Exception:
                pass

            # ── Pass 2: generic line-regex parser (other bank formats) ───────
            from probooksai.statement_extract import parse_statement_text
            return parse_statement_text(text, filter_deposits=True)

        except Exception:
            return []

    def _extract_via_claude(self, path: str, mime: str) -> list[dict]:
        """Use Claude vision to extract transaction rows from a scanned statement.

        Deposits (amount > 0) are filtered out — they must be entered manually.
        """
        try:
            import anthropic, base64, json, os
            client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
            with open(path, "rb") as f:
                data = base64.standard_b64encode(f.read()).decode()
            prompt = (
                "This is a bank statement. Extract ONLY debit/withdrawal/payment transactions "
                "(not deposits or credits). For each debit transaction return a JSON object with: "
                '"date" (YYYY-MM-DD or MM/DD/YYYY), "description" (payee/memo), '
                '"amount" (negative number, e.g. -42.99). '
                "Return a JSON array. If no debits found, return []."
            )
            response = client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=2048,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "document", "source": {"type": "base64", "media_type": mime, "data": data}},
                        {"type": "text", "text": prompt},
                    ],
                }],
            )
            raw = response.content[0].text.strip()
            # Extract JSON array from the response
            m = __import__("re").search(r"\[.*\]", raw, __import__("re").DOTALL)
            if not m:
                return []
            rows_raw = json.loads(m.group())
            rows = []
            for item in rows_raw:
                date_str = str(item.get("date") or "").strip()
                desc = str(item.get("description") or "Transaction").strip()
                try:
                    amt = float(item.get("amount") or 0)
                except (TypeError, ValueError):
                    continue
                if amt >= 0:
                    continue  # skip deposits
                from probooksai.bank_import import parse_date
                date_norm = parse_date(date_str) or date_str
                rows.append({"txn_date": date_norm, "description": desc,
                             "amount": round(amt, 2), "ref_number": ""})
            return rows
        except Exception:
            return []
