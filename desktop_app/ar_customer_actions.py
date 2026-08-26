"""AR invoice/payment dialogs and CSV exports (moved off the **Customers** tab).

Imported lazily from :mod:`desktop_app.extra_tabs` helpers to avoid circular imports.
"""

from __future__ import annotations

import csv
import sqlite3
from collections.abc import Callable

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from desktop_app.flexible_date import (
    attach_line_edit_us_date_normalization,
    configure_qdate_edit_us,
    format_iso_to_us_display,
    line_edit_to_iso_or_raw,
)
from desktop_app.qt_combo_ids import coerce_combo_int_id, combo_index_for_int_user_data
from desktop_app.qt_mnemonic import (
    CSV_EXPORT_OK_TIP_SUFFIX,
    escape_ampersand_for_qt,
    message_box_critical_ok,
    message_box_information_ok,
    message_box_warning_ok,
)
from desktop_app.table_clipboard import (
    FloatSortTableItem,
    plain_display_table_item,
    table_cell_clipboard_text,
)
from probooksai import business, business_list_filter

_FloatSortTableItem = FloatSortTableItem

_NEW_INVOICE_CUSTOMER_KEY = "business/new_invoice_customer_id"
_AR_PAYMENT_CUSTOMER_KEY = "business/ar_payment_customer_id"
_AR_PAYMENT_BANK_KEY = "business/ar_payment_bank_id"


def _et():
    from desktop_app import extra_tabs as et

    return et


def _attach_table_copy_row_menu_lazy(tbl: QTableWidget, menu_parent: QWidget) -> None:
    et = _et()
    et._attach_table_copy_row_menu(tbl, menu_parent)


def open_new_ar_invoice_dialog(
    parent: QWidget,
    conn: sqlite3.Connection,
    *,
    after_save: Callable[[], None] | None = None,
) -> None:
    et = _et()
    custs = business.list_customers(conn)
    if not custs:
        message_box_information_ok(
            parent,
            "Customers",
            "Add a customer first.",
            ok_tip="Close; use New Customer, then create the invoice.",
        )
        return
    d = QDialog(parent)
    d.setWindowTitle("Invoice")
    d.setToolTip(
        "Create an invoice with header fields, one starter line, and tax percent for this customer."
    )
    f = QFormLayout(d)
    cust_filt = QLineEdit()
    cust_filt.setPlaceholderText("Filter customers by name, email, phone…")
    cust_filt.setClearButtonEnabled(True)
    cust_filt.setToolTip("Narrow the customer list; clear to show all again.")
    cb = QComboBox()
    cb.setToolTip("Customer for this invoice (required).")

    def sync_new_inv_customers() -> None:
        et._sync_filtered_entity_combo(
            custs, cust_filt.text(), cb, business_list_filter.CUSTOMER_ENTITY_KEYS
        )

    cust_filt.textChanged.connect(sync_new_inv_customers)
    f.addRow("Filter list", cust_filt)
    f.addRow("Customer", cb)
    sync_new_inv_customers()
    et._restore_entity_combo(cb, _NEW_INVOICE_CUSTOMER_KEY)
    invno = QLineEdit()
    invno.setToolTip("Unique invoice number (required). Next number is suggested; you can edit it.")
    invno.setText(business.next_default_invoice_number(conn))
    idate = QDateEdit()
    configure_qdate_edit_us(idate)
    idate.setDate(QDate.currentDate())
    idate.setToolTip("Invoice date.")
    due_e = QLineEdit()
    due_e.setToolTip("Due date as text if you track it (optional).")
    attach_line_edit_us_date_normalization(due_e)
    memo_e = QLineEdit()
    memo_e.setToolTip("Header memo on the invoice (optional).")
    rate = QDoubleSpinBox()
    rate.setRange(0, 9_999_999)
    rate.setDecimals(2)
    rate.setToolTip("Amount for the single starter line (Services × 1).")
    tax = QDoubleSpinBox()
    tax.setRange(0, 100)
    tax.setDecimals(2)
    tax.setValue(float(business.get_setting(conn, "default_tax_rate_pct", "0") or 0))
    tax.setToolTip("Tax percent applied to this new invoice.")
    f.addRow("Invoice # *", invno)
    f.addRow("Date", idate)
    f.addRow("Due date (optional)", due_e)
    f.addRow("Memo", memo_e)
    f.addRow("Line amount", rate)
    f.addRow("Tax %", tax)
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    et._tip_dialog_ok_cancel(bb, "Create the invoice with one starter line and these header fields.")
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    f.addRow(bb)
    if d.exec() != QDialog.DialogCode.Accepted:
        return
    if not invno.text().strip():
        return
    cust_id = coerce_combo_int_id(cb.currentData())
    if cust_id is None:
        message_box_warning_ok(
            parent,
            "Invoice",
            "Select a customer (try clearing the filter).",
            ok_tip="Close; pick a customer or clear the customer filter.",
        )
        return
    try:
        business.create_invoice(
            conn,
            cust_id,
            invno.text().strip(),
            idate.date().toString("yyyy-MM-dd"),
            due_date=(line_edit_to_iso_or_raw(due_e) or ""),
            memo=memo_e.text().strip(),
            lines=[{"description": "Services", "qty": 1, "rate": rate.value()}],
            tax_rate_pct=tax.value(),
        )
    except sqlite3.IntegrityError:
        message_box_warning_ok(
            parent,
            "Duplicate",
            "Invoice number already exists.",
            ok_tip="Close; choose a different invoice number for this customer.",
        )
        return
    et._save_entity_combo(cb, _NEW_INVOICE_CUSTOMER_KEY)
    if after_save is not None:
        after_save()


def open_ar_invoice_edit_dialog(
    parent: QWidget,
    conn: sqlite3.Connection,
    invoice_id: int,
    *,
    after_save: Callable[[], None] | None = None,
) -> bool:
    """Edit invoice dialog. Returns ``True`` if the invoice was found (dialog may have been cancelled)."""
    et = _et()
    inv_id = int(invoice_id)
    if business.invoice_has_payment_allocations(conn, inv_id):
        message_box_information_ok(
            parent,
            "Invoice",
            "This invoice has payments applied and cannot be edited.",
            ok_tip="Close; void or adjust payments in AR before editing this invoice.",
        )
        return True
    inv, line_rows = business.get_invoice_detail(conn, inv_id)
    if inv is None:
        message_box_information_ok(
            parent,
            "Invoice",
            f"Invoice #{inv_id} is not in this company file.",
            ok_tip="Close; check the **Invoices** tab or the bank link.",
        )
        return False
    custs = business.list_customers(conn)
    if not custs:
        return False
    d = QDialog(parent)
    d.setWindowTitle("Edit invoice")
    d.setToolTip(
        "Edit invoice header, customer, line items, and tax rate (not allowed when payments are applied)."
    )
    outer = QVBoxLayout(d)
    f = QFormLayout()
    inv_cust_id = coerce_combo_int_id(inv["customer_id"])
    if inv_cust_id is None:
        return False
    ensure_cust = frozenset({inv_cust_id})
    cust_filt = QLineEdit()
    cust_filt.setPlaceholderText("Filter customers (current invoice customer always listed)…")
    cust_filt.setClearButtonEnabled(True)
    cust_filt.setToolTip("Narrow the customer list; the invoice’s customer stays available.")
    cb = QComboBox()
    cb.setToolTip("Customer on this invoice.")

    def sync_edit_inv_customers() -> None:
        et._sync_filtered_entity_combo(
            custs,
            cust_filt.text(),
            cb,
            business_list_filter.CUSTOMER_ENTITY_KEYS,
            always_include_ids=ensure_cust,
        )

    cust_filt.textChanged.connect(sync_edit_inv_customers)
    f.addRow("Filter list", cust_filt)
    f.addRow("Customer", cb)
    sync_edit_inv_customers()
    idx = combo_index_for_int_user_data(cb, inv_cust_id)
    cb.setCurrentIndex(idx if idx is not None else 0)
    invno = QLineEdit(inv["invoice_number"] or "")
    invno.setToolTip("Unique invoice number (required).")
    idate = QDateEdit()
    configure_qdate_edit_us(idate)
    qd = QDate.fromString(inv["invoice_date"] or "", "yyyy-MM-dd")
    idate.setDate(qd if qd.isValid() else QDate.currentDate())
    idate.setToolTip("Invoice date.")
    due_e = QLineEdit(format_iso_to_us_display(inv["due_date"] or ""))
    due_e.setToolTip("Due date as text if you track it (optional).")
    attach_line_edit_us_date_normalization(due_e)
    memo_e = QLineEdit(inv["memo"] or "")
    memo_e.setToolTip("Header memo on the invoice (optional).")
    sub = float(inv["subtotal"] or 0)
    tax_amt = float(inv["tax_total"] or 0)
    tax_pct = (100.0 * tax_amt / sub) if sub > 0 else 0.0
    tax = QDoubleSpinBox()
    tax.setRange(0, 100)
    tax.setDecimals(4)
    tax.setValue(tax_pct)
    tax.setToolTip("Tax percent for this invoice (lines × rate; tax recomputed on save).")
    f.addRow("Customer", cb)
    f.addRow("Invoice # *", invno)
    f.addRow("Date", idate)
    f.addRow("Due date (optional)", due_e)
    f.addRow("Memo", memo_e)
    f.addRow("Tax %", tax)
    outer.addLayout(f)
    lbl_edit_inv_lines = QLabel("Line items (description, qty, rate)")
    lbl_edit_inv_lines.setToolTip(
        "Invoice lines below: edit description, quantity, and rate; use Add/Remove line as needed."
    )
    outer.addWidget(lbl_edit_inv_lines)
    line_tbl = QTableWidget()
    line_tbl.setToolTip(
        "Edit line description, quantity, and unit rate. Right-click a row to copy as TSV."
    )
    line_tbl.setColumnCount(3)
    line_tbl.setHorizontalHeaderLabels(["Description", "Qty", "Rate"])
    line_tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    rate_align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter

    def _edit_inv_rate_item(rate: float) -> QTableWidgetItem:
        x = float(rate)
        disp = f"{x:,.2f}"
        it = _FloatSortTableItem(disp, x)
        it.setTextAlignment(rate_align)
        return it

    nlines = max(1, len(line_rows))
    line_tbl.setRowCount(nlines)
    for i, ln in enumerate(line_rows):
        line_tbl.setItem(i, 0, plain_display_table_item(str(ln["description"] or "")))
        line_tbl.setItem(i, 1, plain_display_table_item(str(ln["qty"])))
        line_tbl.setItem(i, 2, _edit_inv_rate_item(float(ln["rate"])))
    if not line_rows:
        line_tbl.setItem(0, 0, plain_display_table_item("Services"))
        line_tbl.setItem(0, 1, plain_display_table_item("1"))
        line_tbl.setItem(0, 2, _edit_inv_rate_item(0.0))
    _attach_table_copy_row_menu_lazy(line_tbl, d)
    outer.addWidget(line_tbl)
    btn_row = QHBoxLayout()

    def add_line():
        line_tbl.insertRow(line_tbl.rowCount())
        r = line_tbl.rowCount() - 1
        line_tbl.setItem(r, 0, plain_display_table_item(""))
        line_tbl.setItem(r, 1, plain_display_table_item(""))
        line_tbl.setItem(r, 2, _edit_inv_rate_item(0.0))

    def del_line():
        if line_tbl.rowCount() <= 1:
            return
        line_tbl.removeRow(line_tbl.currentRow() if line_tbl.currentRow() >= 0 else line_tbl.rowCount() - 1)

    ar_inv_add_line = QPushButton("Add line")
    ar_inv_add_line.setToolTip("Add another line item row to this invoice.")
    ar_inv_add_line.clicked.connect(add_line)
    ar_inv_rm_line = QPushButton("Remove line")
    ar_inv_rm_line.setToolTip(
        "Remove the selected line, or the last line if none is selected (one line always remains)."
    )
    ar_inv_rm_line.clicked.connect(del_line)
    btn_row.addWidget(ar_inv_add_line)
    btn_row.addWidget(ar_inv_rm_line)
    btn_row.addStretch()
    outer.addLayout(btn_row)
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    et._tip_dialog_ok_cancel(bb, "Save invoice header, line items, and tax rate.")
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    outer.addWidget(bb)
    if d.exec() != QDialog.DialogCode.Accepted:
        return True
    if not invno.text().strip():
        return True
    lines_out: list[dict] = []
    for row_i in range(line_tbl.rowCount()):
        desc = table_cell_clipboard_text(line_tbl, row_i, 0).strip()
        qtxt = table_cell_clipboard_text(line_tbl, row_i, 1).strip() or "1"
        rtx = table_cell_clipboard_text(line_tbl, row_i, 2).strip() or "0"
        try:
            qv = float(qtxt)
            rv = float(rtx.replace(",", ""))
        except ValueError:
            message_box_warning_ok(
                parent,
                "Invoice",
                "Invalid qty or rate on a line.",
                ok_tip="Close; enter numeric qty and rate for each line.",
            )
            return True
        if not desc and qv == 0 and rv == 0:
            continue
        lines_out.append({"description": desc or "Line", "qty": qv, "rate": rv})
    if not lines_out:
        message_box_warning_ok(
            parent,
            "Invoice",
            "Add at least one line with an amount.",
            ok_tip="Close; ensure at least one line has qty × rate > 0.",
        )
        return True
    new_cust = coerce_combo_int_id(cb.currentData())
    if new_cust is None:
        message_box_warning_ok(
            parent,
            "Invoice",
            "Select a customer (try clearing the filter).",
            ok_tip="Close; pick a customer or clear the customer filter.",
        )
        return True
    try:
        business.update_invoice(
            conn,
            inv_id,
            new_cust,
            invno.text().strip(),
            idate.date().toString("yyyy-MM-dd"),
            due_date=(line_edit_to_iso_or_raw(due_e) or ""),
            memo=memo_e.text().strip(),
            lines=lines_out,
            tax_rate_pct=tax.value(),
        )
    except ValueError as exc:
        message_box_warning_ok(
            parent,
            "Invoice",
            escape_ampersand_for_qt(str(exc)),
            ok_tip="Close; fix the issue described and save again.",
        )
        return True
    except sqlite3.IntegrityError:
        message_box_warning_ok(
            parent,
            "Duplicate",
            "Invoice number already exists.",
            ok_tip="Close; choose another invoice number.",
        )
        return True
    if after_save is not None:
        after_save()
    return True


def open_record_ar_payment_dialog(
    parent: QWidget,
    conn: sqlite3.Connection,
    *,
    after_save: Callable[[], None] | None = None,
) -> None:
    et = _et()
    custs = business.list_customers(conn)
    if not custs:
        message_box_information_ok(
            parent,
            "AR payment",
            "Add a customer first.",
            ok_tip="Close; create a customer before recording payments.",
        )
        return
    d = QDialog(parent)
    d.setWindowTitle("Record customer payment")
    d.setToolTip(
        "Enter payment details and allocate amounts to open invoices; Apply column must sum to the payment."
    )
    d.setMinimumWidth(540)
    outer = QVBoxLayout(d)
    form = QFormLayout()
    cust_filt = QLineEdit()
    cust_filt.setPlaceholderText("Filter customers by name, email, phone…")
    cust_filt.setClearButtonEnabled(True)
    cust_filt.setToolTip("Narrow the customer list; clear to show all again.")
    cust_cb = QComboBox()
    cust_cb.setToolTip("Customer who paid (open invoices load below).")
    form.addRow("Filter list", cust_filt)
    form.addRow("Customer", cust_cb)
    pdate = QDateEdit()
    configure_qdate_edit_us(pdate)
    pdate.setDate(QDate.currentDate())
    pdate.setToolTip("Date the payment was received.")
    pay_amt = QDoubleSpinBox()
    pay_amt.setRange(0.01, 99_999_999.99)
    pay_amt.setDecimals(2)
    pay_amt.setToolTip("Total payment amount; sum of Apply column must match.")
    method_e = QLineEdit()
    method_e.setToolTip("e.g. Check, ACH, card (optional).")
    ref_e = QLineEdit()
    ref_e.setToolTip("Check number, confirmation id, or bank reference (optional).")
    memo_e = QLineEdit()
    memo_e.setToolTip("Note stored on the payment (optional).")
    bank_cb = QComboBox()
    bank_cb.setToolTip("Bank account where the deposit was recorded, if any.")
    bank_cb.addItem("(None)")
    try:
        banks = conn.execute(
            "SELECT id, name FROM bank_accounts WHERE is_active = 1 ORDER BY name"
        ).fetchall()
    except sqlite3.OperationalError:
        banks = []
    for b in banks:
        bid = coerce_combo_int_id(b["id"])
        if bid is None:
            continue
        bank_cb.addItem(escape_ampersand_for_qt(b["name"] or ""), bid)
    et._restore_payment_bank_combo(bank_cb, _AR_PAYMENT_BANK_KEY)
    form.addRow("Payment date", pdate)
    form.addRow("Amount *", pay_amt)
    form.addRow("Deposit to bank", bank_cb)
    form.addRow("Method", method_e)
    form.addRow("Reference #", ref_e)
    form.addRow("Memo", memo_e)
    outer.addLayout(form)
    lbl_ar_apply_hdr = QLabel("Apply to open invoices:")
    lbl_ar_apply_hdr.setToolTip(
        "Allocate this payment across unpaid invoices for the customer (table below). "
        "If you pick a parent (mother ship) customer, open invoices include all jobs under that account."
    )
    outer.addWidget(lbl_ar_apply_hdr)
    hint = QLabel('Sum of "Apply" must equal the payment amount.')
    hint.setStyleSheet("color: palette(mid);")
    hint.setToolTip(
        "The total in the Apply column must match the payment amount exactly (within penny rounding)."
    )
    outer.addWidget(hint)
    alloc_tbl = QTableWidget()
    alloc_tbl.setColumnCount(4)
    alloc_tbl.setHorizontalHeaderLabels(["Invoice #", "Date", "Balance", "Apply"])
    alloc_tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    alloc_tbl.setToolTip(
        "Open invoices for the selected customer (parent customers include job invoices). "
        "Enter Apply amounts; they must sum to the payment."
    )

    def rebuild_ar_alloc_table(_idx: int | None = None) -> None:
        cid = coerce_combo_int_id(cust_cb.currentData())
        alloc_tbl.setSortingEnabled(False)
        alloc_tbl.setRowCount(0)
        if cid is None:
            alloc_tbl.setSortingEnabled(True)
            return
        opens = business.list_open_invoices_for_ar_payment_customer(conn, cid)
        open_packed = [
            (iid, r)
            for r in opens
            if (iid := coerce_combo_int_id(r["id"])) is not None
        ]
        alloc_tbl.setRowCount(len(open_packed))
        align_rc = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        for i, (iid, r) in enumerate(open_packed):
            it0 = plain_display_table_item(r["invoice_number"] or "")
            it0.setData(Qt.ItemDataRole.UserRole, iid)
            alloc_tbl.setItem(i, 0, it0)
            alloc_tbl.setItem(i, 1, plain_display_table_item(r["invoice_date"] or ""))
            bal = float(r["balance_due"])
            bal_it = _FloatSortTableItem(f"{bal:,.2f}", bal)
            bal_it.setTextAlignment(align_rc)
            alloc_tbl.setItem(i, 2, bal_it)
            sp = QDoubleSpinBox()
            sp.setRange(0, float(r["balance_due"]))
            sp.setDecimals(2)
            alloc_tbl.setCellWidget(i, 3, sp)
        alloc_tbl.setSortingEnabled(True)

    def sync_ar_payment_customers() -> None:
        et._sync_filtered_entity_combo(
            custs, cust_filt.text(), cust_cb, business_list_filter.CUSTOMER_ENTITY_KEYS
        )
        rebuild_ar_alloc_table()

    def apply_oldest_first() -> None:
        remaining = round(pay_amt.value(), 2)
        for row in range(alloc_tbl.rowCount()):
            w = alloc_tbl.cellWidget(row, 3)
            if not isinstance(w, QDoubleSpinBox):
                continue
            cap = round(float(w.maximum()), 2)
            use = min(remaining, cap)
            w.setValue(use)
            remaining = round(remaining - use, 2)
            if remaining <= 0.001:
                break

    cust_filt.textChanged.connect(sync_ar_payment_customers)
    cust_cb.currentIndexChanged.connect(rebuild_ar_alloc_table)
    sync_ar_payment_customers()
    et._restore_entity_combo(cust_cb, _AR_PAYMENT_CUSTOMER_KEY)
    auto_row = QHBoxLayout()
    ar_pay_fill_old = QPushButton("Fill oldest first")
    ar_pay_fill_old.setToolTip(
        "Fill Apply from the oldest open invoice upward until the payment amount is used."
    )
    ar_pay_fill_old.clicked.connect(apply_oldest_first)
    auto_row.addWidget(ar_pay_fill_old)
    auto_row.addStretch()
    outer.addLayout(auto_row)
    _attach_table_copy_row_menu_lazy(alloc_tbl, d)
    outer.addWidget(alloc_tbl)
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    et._tip_dialog_ok_cancel(
        bb,
        "Record the payment and apply amounts to open invoices (totals must match).",
    )
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    outer.addWidget(bb)
    if d.exec() != QDialog.DialogCode.Accepted:
        return
    cid = coerce_combo_int_id(cust_cb.currentData())
    if cid is None:
        message_box_warning_ok(
            parent,
            "AR payment",
            "Select a customer (try clearing the filter).",
            ok_tip="Close; pick a customer or clear the filter.",
        )
        return
    amt = round(pay_amt.value(), 2)
    allocs: list[tuple[int, float]] = []
    for row in range(alloc_tbl.rowCount()):
        it = alloc_tbl.item(row, 0)
        w = alloc_tbl.cellWidget(row, 3)
        if it is None or not isinstance(w, QDoubleSpinBox):
            continue
        v = round(w.value(), 2)
        if v <= 0.005:
            continue
        iid = coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole))
        if iid is None:
            continue
        allocs.append((iid, v))
    if not allocs:
        message_box_warning_ok(
            parent,
            "AR payment",
            "Enter an amount in Apply for at least one invoice.",
            ok_tip="Close; type Apply amounts in the table for open invoices.",
        )
        return
    applied = round(sum(a for _, a in allocs), 2)
    if abs(applied - amt) > 0.02:
        message_box_warning_ok(
            parent,
            "AR payment",
            f"Apply amounts ({applied:.2f}) must equal payment amount ({amt:.2f}).",
            ok_tip="Close; adjust Apply so the total matches the payment amount.",
        )
        return
    bidx = bank_cb.currentIndex()
    bank_account_id = coerce_combo_int_id(bank_cb.itemData(bidx)) if bidx > 0 else None
    business.record_ar_payment(
        conn,
        cid,
        pdate.date().toString("yyyy-MM-dd"),
        amt,
        allocs,
        bank_account_id=bank_account_id,
        method=method_e.text().strip(),
        reference=ref_e.text().strip(),
        memo=memo_e.text().strip(),
    )
    et._save_entity_combo(cust_cb, _AR_PAYMENT_CUSTOMER_KEY)
    et._save_payment_bank_choice(bank_cb, _AR_PAYMENT_BANK_KEY)
    if after_save is not None:
        after_save()
    message_box_information_ok(
        parent,
        "AR payment",
        "Payment recorded.",
        ok_tip="Close; allocations and balances are updated.",
    )


def export_ar_aging_csv(parent: QWidget, conn: sqlite3.Connection) -> None:
    et = _et()
    as_of = et._prompt_as_of_date(parent, "Export AR aging")
    if as_of is None:
        return
    path, _ = QFileDialog.getSaveFileName(parent, "AR aging", "", "CSV (*.csv)")
    if not path:
        return
    data = business.ar_aging_buckets(conn, as_of)[0]
    with open(path, "w", newline="", encoding="utf-8-sig") as fp:
        w = csv.writer(fp)
        w.writerow(
            ["Customer", "Invoice id", "Balance", "Bucket", "Days past due", "As of"]
        )
        for ln in data["lines"]:
            w.writerow(
                [
                    ln["customer"],
                    ln["invoice_id"],
                    f"{ln['balance']:.2f}",
                    ln["bucket"],
                    ln.get("days_past_due", ""),
                    as_of,
                ]
            )
        et._append_aging_bucket_totals_csv(w, data["buckets"], as_of)
    message_box_information_ok(
        parent,
        "Export",
        f"Wrote {escape_ampersand_for_qt(path)}\n(As of {as_of})",
        ok_tip="Close; open the aging CSV from the path shown." + CSV_EXPORT_OK_TIP_SUFFIX,
    )


def export_invoices_csv(parent: QWidget, conn: sqlite3.Connection) -> None:
    et = _et()
    path, _ = QFileDialog.getSaveFileName(
        parent, "Export invoices", "invoices.csv", "CSV (*.csv)"
    )
    if not path:
        return
    if not path.lower().endswith(".csv"):
        path += ".csv"
    try:
        n = business.write_invoices_csv(conn, path, invoice_ids=None)
    except OSError as exc:
        message_box_critical_ok(
            parent,
            "Export failed",
            escape_ampersand_for_qt(str(exc)),
            ok_tip="Close; check path, permissions, and disk space.",
        )
        return
    message_box_information_ok(
        parent,
        "Export",
        f"Exported {n} invoice(s) to {escape_ampersand_for_qt(path)}",
        ok_tip="Close; open the CSV from the path shown." + CSV_EXPORT_OK_TIP_SUFFIX,
    )


def export_ar_payments_csv(parent: QWidget, conn: sqlite3.Connection) -> None:
    path, _ = QFileDialog.getSaveFileName(
        parent, "Export AR payments", "ar_payments.csv", "CSV (*.csv)"
    )
    if not path:
        return
    if not path.lower().endswith(".csv"):
        path += ".csv"
    try:
        n = business.write_ar_payments_csv(conn, path)
    except OSError as exc:
        message_box_critical_ok(
            parent,
            "Export failed",
            escape_ampersand_for_qt(str(exc)),
            ok_tip="Close; check path, permissions, and disk space.",
        )
        return
    except sqlite3.OperationalError as exc:
        message_box_critical_ok(
            parent,
            "Export failed",
            escape_ampersand_for_qt(
                str(exc) + "\n\nRestart the app to apply the latest database upgrade."
            ),
            ok_tip="Close; restart ProBooks+ai after upgrades, then export again.",
        )
        return
    message_box_information_ok(
        parent,
        "Export",
        f"Exported {n} payment(s) to {escape_ampersand_for_qt(path)}",
        ok_tip="Close; open the CSV from the path shown." + CSV_EXPORT_OK_TIP_SUFFIX,
    )


def export_ar_payment_allocations_csv(parent: QWidget, conn: sqlite3.Connection) -> None:
    path, _ = QFileDialog.getSaveFileName(
        parent,
        "Export AR payment allocations",
        "ar_payment_allocations.csv",
        "CSV (*.csv)",
    )
    if not path:
        return
    if not path.lower().endswith(".csv"):
        path += ".csv"
    try:
        n = business.write_ar_payment_allocations_csv(conn, path)
    except OSError as exc:
        message_box_critical_ok(
            parent,
            "Export failed",
            escape_ampersand_for_qt(str(exc)),
            ok_tip="Close; check path, permissions, and disk space.",
        )
        return
    message_box_information_ok(
        parent,
        "Export",
        f"Exported {n} allocation row(s) to {escape_ampersand_for_qt(path)}",
        ok_tip="Close; open the CSV from the path shown." + CSV_EXPORT_OK_TIP_SUFFIX,
    )
