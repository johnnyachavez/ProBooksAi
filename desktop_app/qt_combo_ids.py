"""
Helpers for ``QComboBox`` rows that store integer entity ids in ``itemData`` / ``userData``.

Used by **Bank register** (account, transfer counterparty, manual **Link payment** record id,
selected row / context-menu **transaction ids** from table ``UserRole``, suggestion **link_id**;
**Stmt match** overlay from Bank Import coerces **register_id** / **bank_account_id** payloads),
**Bank Import** (account combo; **Manage Accounts** / **batch** / import **txn** table ``UserRole``;
F5 batch re-select; reconciliation tolerance slider re-finds the current batch by id;
**Stmt match** forward to Register coerces the signal account id; **StatementLineMatchPanel** run uses
coerced batch ``bank_account_id`` for ``list_transactions`` / emit), **Chart of Accounts**
and **Journal** list ``UserRole``, **Audit** entity id filter field + log grid column, **Document Intake**
inbox doc id, **Business** table helpers
(invoice/bill/rule/pay-run row ids; **Edit** invoice/bill coerces **customer_id** / **vendor_id** from SQLite;
**Rules** edit matches list rows to SQLite ids; filtered customer/vendor
combos; AR/AP payment dialogs; allocation row ids; payment bank row), and **Payroll** (new pay run
employee id; payment bank restore with ``start=1``; GL post matches the run grid row to ``_run_rows`` by id)
so ``int`` vs ``str`` (or similar) mismatches from SQLite / Qt do not break lookups.
When building Qt rows from SQLite, invalid ids are **skipped** (row lists / combos omit those rows)
for **COA**, **Manage bank accounts**, **Document Intake** inbox, **Rules** and **AR/AP/Payroll** grids,
**AR/AP** payment bank combos and allocation tables, and **batch reconciled** lookups in the register helper, **Register** bank-account combo reload (skip bad rows),
per-row **transaction id** on the Date cell and **batch_id** for **Clr** / CSV export, and **Bank Import** register preview **UserRole** on import rows.
**Journal** entry list items, **Bank Import** top **bank account** combo and **batch** table (full batch list kept for lookups; grid omits invalid ids), **Register** transfer counterparty combo and **Link payment** manual record combo, and **Payroll** new-run employee combo / run tax-line grid use the same coercion.
**Document Intake** inbox **selected_doc_id** falls back to **coerce_combo_int_id** on visible cell text; **Register** link-payment suggestions omit rows whose **link_id** will not coerce; **Bank Import** stores the table-selected **batch** id as the coerced **bid** and validates account ids on delete/update.
**Business** hub restores **AR/AP** payment bank + customer/vendor combos and the **sub-tab index** from ``QSettings`` via **coerce_combo_int_id** (invalid stored values are ignored or treated as 0).
AR/AP invoice and bill grids use the same helper in ``_table_row_entity_id`` for ``QTABLE_PLAIN_TEXT_ROLE`` and visible cell text when ``UserRole`` is unset.
**Document Intake** ``DetailPane.load_document`` coerces the incoming id, then calls ``get_document`` / ``get_approved`` / ``get_latest_extraction`` with the coerced value; invalid or missing rows reset the pane via ``clear_view``.
**MainWindow** intake slots (**Run AI**, **Approve**, **Posted**, **Reject**, and AI worker **done** / **error**) coerce the signal ``doc_id`` the same way before any ``DocumentDatabase`` writes.
``MainWindow._refresh_inbox`` repopulates the table then calls ``_on_selection_changed`` so the detail pane matches the current row (or clears when nothing valid is selected); ``_on_ai_done`` runs ``_refresh_inbox`` before ``populate_ai_result`` so that sync does not wipe freshly filled AI fields.
Clearing the inbox selection calls ``DetailPane.clear_view`` so the right pane does not keep showing a stale document.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from PySide6.QtWidgets import QComboBox


def coerce_combo_int_id(raw: object) -> int | None:
    """Return ``int(raw)`` or ``None`` when *raw* is ``None`` or not coercible."""
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def combo_int_ids_equal(a: object, b: object) -> bool:
    """True when both are missing or compare equal after ``int(...)`` coercion."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    try:
        return int(a) == int(b)
    except (TypeError, ValueError):
        return False


def combo_index_for_int_user_data(
    combo: QComboBox, target_id: object, *, start: int = 0
) -> Optional[int]:
    """
    First index at or after *start* whose ``itemData`` matches *target_id* by ``int`` equality.

    Returns ``None`` if not found. Skips rows whose data is ``None`` or not coercible to ``int``.
    Use *start* (e.g. ``1``) to skip a leading “none” row on bank pickers.
    """
    want = coerce_combo_int_id(target_id)
    if want is None:
        return None
    if start < 0:
        start = 0
    for i in range(start, combo.count()):
        data = combo.itemData(i)
        if data is None:
            continue
        try:
            if int(data) == want:
                return i
        except (TypeError, ValueError):
            continue
    return None
