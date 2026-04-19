"""Bank Statement Intake — phase 2 review panel with Bank Register hand-off.

Three-input intake (CSV upload, PDF upload, pasted text) → normalized review
table that mirrors :class:`probooksai.bank_statement_intake.BankStatementIntakeRow`,
**plus** an explicit "Send to Bank Register" hand-off and a persisted intake
queue that survives app restarts (Phase 2).

Phase-2 rules layered on top of phase 1:

* **Hand-off is explicit.** Nothing posts to ``bank_transactions`` until the
  user picks a bank account and confirms the send. The review table itself
  never auto-posts.
* **Per-send batch.** Each send creates a dedicated import batch tagged
  ``(Statement intake)`` so register rows are auditable.
* **Dedup-aware.** Re-sending the same row is silently skipped (existing
  fingerprint dedup in :meth:`probooksai.bank_import.BankDatabase.import_transactions`).
* **Persisted queue.** When constructed with a ``bank_db`` the panel
  hydrates from ``bank_statement_intake_queue`` on load and re-snapshots
  the queue on every append / edit / clear / send.
* **Standalone fallback.** Constructing without ``bank_db`` keeps the
  Phase-1 review-only behavior — no account combo, no Send button, no
  persistence — so the panel still works in tests and previews.

Phase-1 hard rules also still enforced:

* **No COA classification.** The review table never sets ``coa_account``.
* **Editable rows.** Every cell except the read-only ``Source`` provenance
  pair (``source_type`` / ``source_ref``) is user-editable.
* **Image OCR out of scope.** PDF intake uses the text layer only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from probooksai.bank_import import BANK_CSV_READ_ENCODING, BankDatabase
from probooksai.bank_statement_intake import (
    SOURCE_TYPE_CSV,
    SOURCE_TYPE_PDF,
    SOURCE_TYPE_TEXT,
    BankStatementIntakeRow,
    extract_csv_statement,
    extract_pasted_text_statement,
    extract_pdf_statement,
)
from probooksai.bank_statement_intake_duplicate_check import (
    RegisterDuplicateMatch,
    find_register_duplicates,
)
from probooksai.bank_statement_intake_handoff import (
    HandoffResult,
    post_intake_rows_to_register,
)
from probooksai.bank_statement_intake_persistence import (
    load_intake_queue,
    replace_intake_queue,
)
from desktop_app.qt_mnemonic import (
    message_box_information_ok,
    message_box_warning_ok,
    tip_message_box_buttons,
)
from desktop_app.theme import (
    WORKFLOW_CONTROL_FACE,
    WORKFLOW_GRID,
    WORKFLOW_HEADER_BG,
    WORKFLOW_INPUT_BG,
    WORKFLOW_PAGE_BG,
    WORKFLOW_PANEL_BG,
    WORKFLOW_TEXT,
)

# Phase-3 sentinel field name for the read-only "Possible duplicate" column.
# It does not map to any :class:`BankStatementIntakeRow` field — the cell is
# rendered from a panel-side side-map and persisted to nothing.
_DUP_REGISTER_FIELD = "_dup_register_match"

# Display-order columns for the review table. The header strings are what
# the user sees; the underlying schema field names live in the column-index
# map below.
_REVIEW_COLUMNS: tuple[tuple[str, str], ...] = (
    ("Date", "txn_date"),
    ("Description", "description_raw"),
    ("Debit", "debit"),
    ("Credit", "credit"),
    ("Amount (signed)", "amount_signed"),
    ("Running balance", "running_balance"),
    ("Source", "source_type"),
    ("Source ref", "source_ref"),
    ("Confidence", "confidence"),
    ("Needs review", "needs_review"),
    # Phase-3 step 1: pre-flight duplicate scan against ``bank_transactions``
    # for the chosen account. Read-only and computed; never serialized into
    # the persisted intake queue.
    ("Possible duplicate", _DUP_REGISTER_FIELD),
)

_HEADERS: tuple[str, ...] = tuple(h for h, _ in _REVIEW_COLUMNS)
_FIELD_FOR_COLUMN: dict[int, str] = {
    i: field_name for i, (_, field_name) in enumerate(_REVIEW_COLUMNS)
}

# Read-only columns: provenance pair (Phase 1) plus the computed
# duplicate column (Phase 3 step 1). Everything else is user-editable so
# the bookkeeper can correct extraction noise before any hand-off.
_READONLY_COLUMNS: frozenset[int] = frozenset(
    {
        i
        for i, (_, field_name) in enumerate(_REVIEW_COLUMNS)
        if field_name in {"source_type", "source_ref", _DUP_REGISTER_FIELD}
    }
)

_CSV_FILE_FILTER = "CSV files (*.csv);;All files (*.*)"
_PDF_FILE_FILTER = "PDF files (*.pdf);;All files (*.*)"


def _format_money(value: Optional[float]) -> str:
    if value is None:
        return ""
    return f"{value:,.2f}"


def _format_confidence(value: Optional[float]) -> str:
    if value is None:
        return ""
    return f"{value:.2f}"


def _format_bool(value: bool) -> str:
    return "Yes" if value else "No"


def _make_item(text: str, *, editable: bool, monospace: bool = False) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
    if editable:
        flags |= Qt.ItemFlag.ItemIsEditable
    item.setFlags(flags)
    if monospace:
        f = QFont("Consolas")
        f.setStyleHint(QFont.StyleHint.Monospace)
        item.setFont(f)
    return item


class BankStatementIntakePanel(QWidget):
    """Review-first staging panel for CSV / PDF / pasted bank statement text.

    Phase-2 capable: when constructed with a ``bank_db`` the panel persists
    its review queue across sessions and exposes a "Send to Bank Register"
    hand-off bound to a chosen ``bank_accounts`` row. Without a ``bank_db``
    it stays in pure-review mode (Phase-1 behavior).

    Signals:

    * :attr:`rowsChanged` (``int``) — emitted after every append / clear
      action with the new row count. Embedders can listen for badge updates.
    * :attr:`rowsSentToRegister` (``int``) — emitted after a successful
      send-to-register hand-off with the count of newly-inserted register
      rows. Embedders refresh their Bank Register view in response.
    """

    rowsChanged = Signal(int)
    rowsSentToRegister = Signal(int)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        file_dialog_factory: Optional[Callable[..., Optional[str]]] = None,
        bank_db: Optional[BankDatabase] = None,
        confirm_factory: Optional[Callable[..., bool]] = None,
        info_factory: Optional[Callable[..., None]] = None,
    ) -> None:
        super().__init__(parent)
        # Test seam: a callable matching ``getOpenFileName`` so unit tests can
        # inject a path without bringing up a real native dialog.
        self._file_dialog_factory = file_dialog_factory
        # Phase-2 hand-off DB. ``None`` keeps the panel in review-only mode.
        self._bank_db = bank_db
        # Test seams for the send-confirmation prompt and post-send summary
        # so headless tests don't have to drive a real modal.
        self._confirm_factory = confirm_factory
        self._info_factory = info_factory
        # Phase-3 step 1: side-map of {table_row_index -> RegisterDuplicateMatch}.
        # Cleared on every table mutation; re-populated by ``_refresh_duplicate_check``
        # whenever the chosen bank account or staged rows change.
        self._dup_matches: dict[int, RegisterDuplicateMatch] = {}
        self.setObjectName("bankStatementIntakePanel")
        self.setStyleSheet(
            f"QWidget#bankStatementIntakePanel {{ background-color: {WORKFLOW_PAGE_BG}; "
            f"color: {WORKFLOW_TEXT}; }}"
        )
        self._build_ui()
        if self._bank_db is not None:
            self._refresh_account_combo()
            self._hydrate_from_persisted_queue()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 12)
        outer.setSpacing(8)

        banner = QLabel(
            "<b>Bank Statement Intake</b> &mdash; review-only staging. "
            "Nothing here is posted to the Bank Register. Edit any row, then "
            "use a future phase-2 hand-off to send rows downstream."
        )
        banner.setTextFormat(Qt.TextFormat.RichText)
        banner.setWordWrap(True)
        banner.setStyleSheet(
            f"QLabel {{ color: {WORKFLOW_TEXT}; background: transparent; "
            f"padding: 4px 0; font-size: 12px; }}"
        )
        outer.addWidget(banner)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self._btn_import_csv = QPushButton("Import CSV…")
        self._btn_import_pdf = QPushButton("Import PDF…")
        self._btn_extract_text = QPushButton("Extract pasted text")
        self._btn_clear = QPushButton("Clear staged rows")
        for b in (
            self._btn_import_csv,
            self._btn_import_pdf,
            self._btn_extract_text,
            self._btn_clear,
        ):
            b.setStyleSheet(
                f"QPushButton {{ background-color: {WORKFLOW_CONTROL_FACE}; "
                f"color: {WORKFLOW_TEXT}; border: 1px solid {WORKFLOW_GRID}; "
                f"padding: 4px 12px; border-radius: 4px; }}"
            )
            b.setAutoDefault(False)
            b.setDefault(False)
            action_row.addWidget(b)
        action_row.addStretch(1)

        self._row_count_label = QLabel("0 rows staged.")
        self._row_count_label.setStyleSheet(
            f"QLabel {{ color: {WORKFLOW_TEXT}; background: transparent; }}"
        )
        action_row.addWidget(self._row_count_label)
        outer.addLayout(action_row)

        self._paste_box = QPlainTextEdit()
        self._paste_box.setObjectName("bankStatementPasteBox")
        self._paste_box.setPlaceholderText(
            "Paste raw bank statement text here — date-led lines with money "
            "values are extracted into the review table below."
        )
        self._paste_box.setStyleSheet(
            f"QPlainTextEdit#bankStatementPasteBox {{ background-color: {WORKFLOW_INPUT_BG}; "
            f"color: {WORKFLOW_TEXT}; border: 1px solid {WORKFLOW_GRID}; "
            f"selection-background-color: #2D5AA0; padding: 6px; }}"
        )
        self._paste_box.setFixedHeight(140)
        outer.addWidget(self._paste_box)

        self._table = QTableWidget(0, len(_HEADERS))
        self._table.setHorizontalHeaderLabels(list(_HEADERS))
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(
            f"QTableWidget {{ background-color: {WORKFLOW_PANEL_BG}; "
            f"alternate-background-color: {WORKFLOW_PAGE_BG}; "
            f"color: {WORKFLOW_TEXT}; gridline-color: {WORKFLOW_GRID}; }}"
            f"QHeaderView::section {{ background-color: {WORKFLOW_HEADER_BG}; "
            f"color: {WORKFLOW_TEXT}; padding: 4px 8px; "
            f"border: 1px solid {WORKFLOW_GRID}; }}"
        )
        header = self._table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        # Description should claim free space; provenance / source columns can
        # stay narrow.
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        outer.addWidget(self._table, 1)

        # Phase-2 hand-off row: bank-account picker + Send to Bank Register.
        # Always built (so test discovery stays simple); disabled cleanly
        # when no ``bank_db`` was provided.
        handoff_row = QHBoxLayout()
        handoff_row.setSpacing(8)

        handoff_label = QLabel("Send to Bank Register:")
        handoff_label.setStyleSheet(
            f"QLabel {{ color: {WORKFLOW_TEXT}; background: transparent; }}"
        )
        handoff_row.addWidget(handoff_label)

        self._account_combo = QComboBox()
        self._account_combo.setObjectName("statementIntakeAccountCombo")
        self._account_combo.setMinimumWidth(220)
        self._account_combo.setStyleSheet(
            f"QComboBox#statementIntakeAccountCombo {{ background-color: {WORKFLOW_INPUT_BG}; "
            f"color: {WORKFLOW_TEXT}; border: 1px solid {WORKFLOW_GRID}; "
            f"padding: 3px 6px; }}"
        )
        handoff_row.addWidget(self._account_combo)

        self._btn_send_to_register = QPushButton("Send to Bank Register")
        self._btn_send_to_register.setStyleSheet(
            f"QPushButton {{ background-color: {WORKFLOW_CONTROL_FACE}; "
            f"color: {WORKFLOW_TEXT}; border: 1px solid {WORKFLOW_GRID}; "
            f"padding: 4px 12px; border-radius: 4px; }}"
        )
        self._btn_send_to_register.setAutoDefault(False)
        self._btn_send_to_register.setDefault(False)
        handoff_row.addWidget(self._btn_send_to_register)

        # Phase-3 step 1: explicit "Check duplicates" action so the user can
        # re-run the scan after editing rows (the panel also auto-runs the
        # check on append / account change, but a manual button keeps the
        # action discoverable).
        self._btn_check_duplicates = QPushButton("Check duplicates")
        self._btn_check_duplicates.setStyleSheet(
            f"QPushButton {{ background-color: {WORKFLOW_CONTROL_FACE}; "
            f"color: {WORKFLOW_TEXT}; border: 1px solid {WORKFLOW_GRID}; "
            f"padding: 4px 12px; border-radius: 4px; }}"
        )
        self._btn_check_duplicates.setAutoDefault(False)
        self._btn_check_duplicates.setDefault(False)
        handoff_row.addWidget(self._btn_check_duplicates)

        # Phase-3 step 1: dedicated label for the duplicate-scan summary so
        # it doesn't fight with the send-result label for screen real estate.
        self._duplicate_status_label = QLabel("")
        self._duplicate_status_label.setStyleSheet(
            f"QLabel {{ color: {WORKFLOW_TEXT}; background: transparent; "
            f"font-size: 11px; }}"
        )
        handoff_row.addWidget(self._duplicate_status_label)
        handoff_row.addStretch(1)

        self._handoff_status_label = QLabel("")
        self._handoff_status_label.setStyleSheet(
            f"QLabel {{ color: {WORKFLOW_TEXT}; background: transparent; "
            f"font-size: 11px; }}"
        )
        handoff_row.addWidget(self._handoff_status_label)

        outer.addLayout(handoff_row)

        self._btn_import_csv.clicked.connect(self._on_import_csv_clicked)
        self._btn_import_pdf.clicked.connect(self._on_import_pdf_clicked)
        self._btn_extract_text.clicked.connect(self._on_extract_text_clicked)
        self._btn_clear.clicked.connect(self._on_clear_clicked)
        self._btn_send_to_register.clicked.connect(
            self._on_send_to_register_clicked
        )
        self._btn_check_duplicates.clicked.connect(
            self._on_check_duplicates_clicked
        )
        self._account_combo.currentIndexChanged.connect(
            self._on_account_changed
        )

        self._refresh_row_count_label()
        self._refresh_send_button_state()

    # -------------------------------------------------------------- helpers

    def _refresh_row_count_label(self) -> None:
        n = self._table.rowCount()
        needs = sum(1 for r in self.collect_rows() if r.needs_review)
        if n == 0:
            self._row_count_label.setText("0 rows staged.")
        else:
            self._row_count_label.setText(
                f"{n} row{'s' if n != 1 else ''} staged "
                f"({needs} need review)."
            )

    def _emit_changed(self) -> None:
        self._refresh_row_count_label()
        self._refresh_send_button_state()
        self._persist_current_queue()
        # Phase-3 step 1: re-scan against the register so the "Possible
        # duplicate" badges stay in sync after every append / edit / clear.
        self._refresh_duplicate_check()
        self.rowsChanged.emit(self._table.rowCount())

    def _on_account_changed(self, *_args) -> None:
        """Account change updates Send-button state AND re-runs duplicate scan."""
        self._refresh_send_button_state()
        self._refresh_duplicate_check()

    # ----------------------------------------------------------- handoff state
    def _refresh_send_button_state(self, *_args) -> None:
        """Enable Send only when DB + account + at least one staged row exist.

        Phase-3 step 1: also gates the **Check duplicates** button on the
        same precondition (DB + account + rows) so the action is only
        offered when a meaningful scan is possible.
        """
        if not hasattr(self, "_btn_send_to_register"):
            return
        has_db = self._bank_db is not None
        has_account = self._selected_bank_account_id() is not None
        has_rows = self._table.rowCount() > 0 if hasattr(self, "_table") else False
        ready = has_db and has_account and has_rows
        self._btn_send_to_register.setEnabled(ready)
        if hasattr(self, "_btn_check_duplicates"):
            self._btn_check_duplicates.setEnabled(ready)
            if ready:
                self._btn_check_duplicates.setToolTip(
                    "Re-scan staged rows against Bank Register for the "
                    "selected account."
                )
            else:
                self._btn_check_duplicates.setToolTip(
                    "Pick a company file, account, and stage at least one "
                    "row to enable the duplicate scan."
                )
        if not has_db:
            self._btn_send_to_register.setToolTip(
                "Bank Register hand-off needs an open company file."
            )
        elif not has_account:
            self._btn_send_to_register.setToolTip(
                "Pick a bank account to receive these rows."
            )
        elif not has_rows:
            self._btn_send_to_register.setToolTip(
                "Stage at least one row before sending to the register."
            )
        else:
            self._btn_send_to_register.setToolTip(
                "Post staged rows into Bank Register under the selected account."
            )

    def _selected_bank_account_id(self) -> Optional[int]:
        if not hasattr(self, "_account_combo"):
            return None
        data = self._account_combo.currentData()
        if data is None:
            return None
        try:
            aid = int(data)
        except (TypeError, ValueError):
            return None
        return aid if aid > 0 else None

    def _refresh_account_combo(self) -> None:
        """(Re)populate the bank-account combo from the current ``bank_db``.

        Idempotent — safe to call after the user creates a new account
        elsewhere in the app and the panel needs to pick it up.
        """
        if self._bank_db is None or not hasattr(self, "_account_combo"):
            return
        prior = self._selected_bank_account_id()
        self._account_combo.blockSignals(True)
        self._account_combo.clear()
        try:
            accounts = self._bank_db.list_bank_accounts(include_inactive=False)
        except Exception:
            accounts = []
        if not accounts:
            self._account_combo.addItem("(no bank accounts)", None)
        else:
            for a in accounts:
                name = a["name"] if "name" in a.keys() else str(a[0])
                aid = int(a["id"]) if "id" in a.keys() else int(a[0])
                self._account_combo.addItem(name, aid)
            if prior is not None:
                idx = self._account_combo.findData(prior)
                if idx >= 0:
                    self._account_combo.setCurrentIndex(idx)
        self._account_combo.blockSignals(False)
        self._refresh_send_button_state()

    # ----------------------------------------------------------- persistence
    def _persist_current_queue(self) -> None:
        """Snapshot the live review table to ``bank_statement_intake_queue``."""
        if self._bank_db is None:
            return
        conn = getattr(self._bank_db, "_conn", None)
        if conn is None:
            return
        try:
            replace_intake_queue(conn, self.collect_rows())
        except Exception:
            # Persistence is best-effort; review state still lives in the
            # in-memory table. Silently swallowing keeps the panel usable
            # even if a transient DB issue blocks the snapshot.
            pass

    def _hydrate_from_persisted_queue(self) -> None:
        """Reload any rows persisted from a previous session into the table."""
        if self._bank_db is None:
            return
        conn = getattr(self._bank_db, "_conn", None)
        if conn is None:
            return
        try:
            rows = load_intake_queue(conn)
        except Exception:
            rows = []
        if not rows:
            self._refresh_row_count_label()
            return
        for r in rows:
            self._append_one(r)
        self._refresh_row_count_label()
        self._refresh_send_button_state()
        # Run the duplicate scan once after hydration so re-opened sessions
        # immediately show "Possible duplicate" badges where they apply.
        self._refresh_duplicate_check()

    # ----------------------------------------------------- duplicate check
    def _refresh_duplicate_check(self) -> None:
        """Re-run the register duplicate scan and repaint the column.

        Silent no-op when DB or account is missing — the badge column stays
        blank in that case so the panel still looks coherent in standalone /
        Phase-1 mode.
        """
        if not hasattr(self, "_table"):
            return
        self._dup_matches = {}
        if self._bank_db is None:
            self._render_duplicate_column()
            return
        account_id = self._selected_bank_account_id()
        if account_id is None:
            self._render_duplicate_column()
            return
        rows = self.collect_rows()
        if not rows:
            self._render_duplicate_column()
            return
        try:
            self._dup_matches = find_register_duplicates(
                self._bank_db,
                bank_account_id=account_id,
                rows=rows,
            )
        except Exception:
            self._dup_matches = {}
        self._render_duplicate_column()

    def _render_duplicate_column(self) -> None:
        """Write the current ``_dup_matches`` into the read-only badge column."""
        col = self._duplicate_column_index()
        if col < 0:
            return
        for r in range(self._table.rowCount()):
            match = self._dup_matches.get(r)
            text = match.display_label() if match is not None else ""
            existing = self._table.item(r, col)
            if existing is None:
                self._table.setItem(r, col, _make_item(text, editable=False))
            else:
                existing.setText(text)
        self._refresh_duplicate_status_label()

    def _refresh_duplicate_status_label(self) -> None:
        if not hasattr(self, "_duplicate_status_label"):
            return
        n = len(self._dup_matches)
        if n == 0:
            self._duplicate_status_label.setText("")
            return
        self._duplicate_status_label.setText(
            f"{n} possible duplicate{'s' if n != 1 else ''} of existing "
            f"register rows."
        )

    @staticmethod
    def _duplicate_column_index() -> int:
        for i, (_, field_name) in enumerate(_REVIEW_COLUMNS):
            if field_name == _DUP_REGISTER_FIELD:
                return i
        return -1

    def _on_check_duplicates_clicked(self) -> None:
        """Manual re-scan trigger (also runs automatically on edits / account change)."""
        self._refresh_duplicate_check()

    def duplicate_match_for_row(
        self, row_index: int
    ) -> Optional[RegisterDuplicateMatch]:
        """Public read-only accessor (used by tests / future Phase-3 steps)."""
        return self._dup_matches.get(row_index)

    # -------------------------------------------------------------- actions
    def _open_file_path(self, *, caption: str, file_filter: str) -> Optional[str]:
        if self._file_dialog_factory is not None:
            return self._file_dialog_factory(
                caption=caption, file_filter=file_filter
            )
        path, _ = QFileDialog.getOpenFileName(self, caption, "", file_filter)
        return path or None

    def _on_import_csv_clicked(self) -> None:
        path = self._open_file_path(
            caption="Choose bank statement CSV", file_filter=_CSV_FILE_FILTER
        )
        if not path:
            return
        self.import_csv_file(path)

    def _on_import_pdf_clicked(self) -> None:
        path = self._open_file_path(
            caption="Choose bank statement PDF", file_filter=_PDF_FILE_FILTER
        )
        if not path:
            return
        self.import_pdf_file(path)

    def _on_extract_text_clicked(self) -> None:
        text = self._paste_box.toPlainText()
        if not text or not text.strip():
            return
        rows = extract_pasted_text_statement(text, source_ref="pasted-text")
        self.append_rows(rows)

    def _on_clear_clicked(self) -> None:
        self._table.setRowCount(0)
        self._emit_changed()

    # ------------------------------------------------------- send to register
    def _on_send_to_register_clicked(self) -> None:
        """Confirm + post staged rows to the Bank Register under the chosen account.

        Behavior:

        * If the user has rows selected in the review table, only those rows
          are sent. Otherwise every staged row is sent.
        * A Yes / No confirmation prompt shows the row count and the chosen
          account so accidental clicks don't post the queue silently.
        * Successfully-inserted *and* skipped-as-duplicate rows are evicted
          from the review table (and the persisted queue). Rows the
          hand-off rejected as ``invalid`` (missing date or amount) stay so
          the user can fix them.
        """
        if self._bank_db is None:
            return
        account_id = self._selected_bank_account_id()
        if account_id is None:
            message_box_warning_ok(
                self,
                "Send to Bank Register",
                "Pick a bank account before sending staged rows to the register.",
                ok_tip="Close; choose an account, then send again.",
            )
            return

        rows_with_indexes = self._collect_rows_for_send()
        if not rows_with_indexes:
            return
        indexes_for_send = [i for i, _ in rows_with_indexes]
        rows_for_send = [r for _, r in rows_with_indexes]

        account_name = self._account_combo.currentText()
        needs_review_count = sum(1 for r in rows_for_send if r.needs_review)
        prompt = (
            f"Post {len(rows_for_send)} staged "
            f"row{'s' if len(rows_for_send) != 1 else ''} to "
            f"\u201C{account_name}\u201D in Bank Register?\n\n"
            f"\u2022 Duplicates of existing register rows are skipped automatically.\n"
            f"\u2022 Rows missing a date or amount are kept here for you to fix.\n"
        )
        if needs_review_count:
            prompt += (
                f"\u2022 {needs_review_count} row"
                f"{'s' if needs_review_count != 1 else ''} are flagged "
                f"\u201CNeeds review\u201D \u2014 they will still be posted "
                f"so review the table before confirming.\n"
            )
        if not self._confirm_send(prompt):
            return

        try:
            result = post_intake_rows_to_register(
                self._bank_db,
                bank_account_id=account_id,
                rows=rows_for_send,
                source_label=account_name or "",
            )
        except Exception as exc:
            message_box_warning_ok(
                self,
                "Send to Bank Register",
                f"Send failed: {exc}",
                ok_tip="Close; the staged rows are unchanged.",
            )
            return

        # Map hand-off-relative indexes back to table rows so we evict the
        # right ones without disturbing rows the user must still fix.
        evict_table_rows = sorted(
            {indexes_for_send[i] for i in result.inserted_indexes},
            reverse=True,
        )
        for r in evict_table_rows:
            self._table.removeRow(r)

        self._emit_changed()
        if result.inserted > 0:
            self.rowsSentToRegister.emit(result.inserted)

        self._show_send_summary(result, account_name)

    def _collect_rows_for_send(
        self,
    ) -> list[tuple[int, BankStatementIntakeRow]]:
        """Selected rows when any are highlighted, else every staged row."""
        all_rows = self.collect_rows()
        if not all_rows:
            return []
        sel = self._table.selectionModel()
        if sel is not None:
            selected_rows = sorted({idx.row() for idx in sel.selectedRows()})
            if selected_rows:
                return [
                    (r, all_rows[r]) for r in selected_rows if 0 <= r < len(all_rows)
                ]
        return list(enumerate(all_rows))

    def _confirm_send(self, prompt: str) -> bool:
        if self._confirm_factory is not None:
            return bool(self._confirm_factory(prompt))
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Send to Bank Register")
        box.setText(prompt)
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        box.setDefaultButton(QMessageBox.StandardButton.No)
        tip_message_box_buttons(
            box,
            yes="Post these rows into Bank Register now.",
            no="Cancel; staged rows are unchanged.",
        )
        return box.exec() == QMessageBox.StandardButton.Yes

    def _show_send_summary(
        self, result: HandoffResult, account_name: str
    ) -> None:
        bits: list[str] = []
        bits.append(
            f"Inserted {result.inserted} row"
            f"{'s' if result.inserted != 1 else ''}."
        )
        if result.skipped_duplicates:
            bits.append(
                f"Skipped {result.skipped_duplicates} duplicate"
                f"{'s' if result.skipped_duplicates != 1 else ''}."
            )
        if result.invalid:
            bits.append(
                f"{result.invalid} row"
                f"{'s' if result.invalid != 1 else ''} kept "
                f"(missing date or amount)."
            )
        text = " ".join(bits)
        self._handoff_status_label.setText(
            f"Last send to \u201C{account_name}\u201D: {text}"
        )
        if self._info_factory is not None:
            self._info_factory(text)
            return
        message_box_information_ok(
            self,
            "Send to Bank Register",
            text,
            ok_tip="Close; check Bank Register to see the new rows.",
        )

    def refresh_account_combo(self) -> None:
        """Public re-population hook for embedders (after creating a new account)."""
        self._refresh_account_combo()

    # -------------------------------------------------------------- public API
    def import_csv_file(self, path: str) -> int:
        """Read *path* as bank-CSV text, extract rows, append to the review table.

        Returns the number of rows actually appended. Encoding follows
        :data:`probooksai.bank_import.BANK_CSV_READ_ENCODING` (UTF-8 with
        optional BOM, matching the existing CSV import path). Unreadable
        files are silently skipped — phase-1 intake never raises out of the
        UI in normal flow.
        """
        try:
            content = Path(path).read_text(encoding=BANK_CSV_READ_ENCODING)
        except OSError:
            return 0
        rows = extract_csv_statement(content, source_ref=Path(path).name)
        return self.append_rows(rows)

    def import_pdf_file(self, path: str) -> int:
        """Extract text-layer rows from a PDF statement at *path* and append."""
        try:
            rows = extract_pdf_statement(path, source_ref=Path(path).name)
        except (OSError, ImportError):
            return 0
        return self.append_rows(rows)

    def import_pasted_text(self, text: str, *, source_ref: str = "pasted-text") -> int:
        """Programmatic entry point for extracting from a string of statement text."""
        rows = extract_pasted_text_statement(text or "", source_ref=source_ref)
        return self.append_rows(rows)

    def append_rows(self, rows: Iterable[BankStatementIntakeRow]) -> int:
        """Append *rows* to the review table; return how many were appended."""
        rows_list = list(rows)
        for r in rows_list:
            self._append_one(r)
        if rows_list:
            self._emit_changed()
        return len(rows_list)

    def clear_rows(self) -> None:
        """Drop all staged rows from the review table (UI-only)."""
        self._table.setRowCount(0)
        self._emit_changed()

    def collect_rows(self) -> list[BankStatementIntakeRow]:
        """Snapshot the current review-table contents back into the schema dataclass.

        Empty / unparseable cells map to ``None`` (money) or ``""`` (text);
        ``confidence`` and ``needs_review`` round-trip through the table as
        strings so we re-parse them defensively here.
        """
        out: list[BankStatementIntakeRow] = []
        for r in range(self._table.rowCount()):
            out.append(self._row_to_dataclass(r))
        return out

    def row_count(self) -> int:
        return self._table.rowCount()

    # -------------------------------------------------------------- internals
    def _append_one(self, row: BankStatementIntakeRow) -> None:
        r_idx = self._table.rowCount()
        self._table.insertRow(r_idx)
        for c, (_, field_name) in enumerate(_REVIEW_COLUMNS):
            text = self._format_value(field_name, row)
            editable = c not in _READONLY_COLUMNS
            monospace = field_name in {
                "debit",
                "credit",
                "amount_signed",
                "running_balance",
                "confidence",
            }
            item = _make_item(text, editable=editable, monospace=monospace)
            self._table.setItem(r_idx, c, item)

    @staticmethod
    def _format_value(field_name: str, row: BankStatementIntakeRow) -> str:
        if field_name == "txn_date":
            return row.txn_date or ""
        if field_name == "description_raw":
            return row.description_raw or ""
        if field_name == "debit":
            return _format_money(row.debit)
        if field_name == "credit":
            return _format_money(row.credit)
        if field_name == "amount_signed":
            return _format_money(row.amount_signed)
        if field_name == "running_balance":
            return _format_money(row.running_balance)
        if field_name == "source_type":
            return row.source_type or ""
        if field_name == "source_ref":
            return row.source_ref or ""
        if field_name == "confidence":
            return _format_confidence(row.confidence)
        if field_name == "needs_review":
            return _format_bool(row.needs_review)
        return ""

    def _row_to_dataclass(self, r: int) -> BankStatementIntakeRow:
        get = lambda c: (self._table.item(r, c).text() if self._table.item(r, c) else "")
        out = BankStatementIntakeRow()
        for c, (_, field_name) in enumerate(_REVIEW_COLUMNS):
            raw = (get(c) or "").strip()
            if field_name == "txn_date":
                out.txn_date = raw
            elif field_name == "description_raw":
                out.description_raw = raw
            elif field_name == "debit":
                out.debit = _maybe_money(raw)
            elif field_name == "credit":
                out.credit = _maybe_money(raw)
            elif field_name == "amount_signed":
                out.amount_signed = _maybe_money(raw)
            elif field_name == "running_balance":
                out.running_balance = _maybe_money(raw)
            elif field_name == "source_type":
                out.source_type = raw
            elif field_name == "source_ref":
                out.source_ref = raw
            elif field_name == "confidence":
                out.confidence = _maybe_confidence(raw)
            elif field_name == "needs_review":
                out.needs_review = raw.strip().lower() in {"yes", "true", "y", "1"}
        return out


def _maybe_money(raw: str) -> Optional[float]:
    s = (raw or "").replace(",", "").replace("$", "").strip()
    if not s:
        return None
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def _maybe_confidence(raw: str) -> float:
    try:
        return round(float((raw or "0").strip()), 2)
    except ValueError:
        return 0.0


__all__ = [
    "BankStatementIntakePanel",
    "SOURCE_TYPE_CSV",
    "SOURCE_TYPE_PDF",
    "SOURCE_TYPE_TEXT",
]
