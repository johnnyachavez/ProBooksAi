"""Background CSV bank import with progress and cancel (Phase 21)."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class CsvImportWorker(QThread):
    """Runs :meth:`BankDatabase.import_csv` on a dedicated DB connection."""

    finished_ok = Signal(dict)
    failed = Signal(str)
    progress = Signal(int, int)

    def __init__(self, db_path: str, import_kwargs: dict):
        super().__init__()
        self._db_path = db_path
        self._import_kwargs = import_kwargs
        self._cancel = False

    def request_cancel(self):
        self._cancel = True

    def run(self):
        try:
            from probooksai.bank_import import BankDatabase

            bdb = BankDatabase(db_path=self._db_path)

            def _progress(cur: int, total: int):
                self.progress.emit(cur, total)

            def _cancelled() -> bool:
                return self._cancel

            kw = dict(self._import_kwargs)
            kw["progress_callback"] = _progress
            kw["cancel_check"] = _cancelled
            result = bdb.import_csv(**kw)
            bdb.close()
            self.finished_ok.emit(result)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
