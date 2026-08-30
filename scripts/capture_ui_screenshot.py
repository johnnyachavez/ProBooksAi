"""
capture_ui_screenshot.py
========================
Headless screenshot helper for ProBooks+ai CI.

Usage (with a virtual display already active, e.g. via xvfb-run):
    python scripts/capture_ui_screenshot.py
    python scripts/capture_ui_screenshot.py --tab invoices --output artifacts/ui/create_invoices.png
    python scripts/capture_ui_screenshot.py --tab bills --output artifacts/ui/enter_bills.png
    python scripts/capture_ui_screenshot.py --tab pay-bills --output artifacts/ui/pay_bills.png
    python scripts/capture_ui_screenshot.py --tab payments --output artifacts/ui/receive_payments.png
    python scripts/capture_ui_screenshot.py --tab deposits --output artifacts/ui/make_deposits.png
    python scripts/capture_ui_screenshot.py --tab checks --output artifacts/ui/write_checks.png
    python scripts/capture_ui_screenshot.py --tab vendors --output artifacts/ui/vendor_center.png
    python scripts/capture_ui_screenshot.py --tab customers --output artifacts/ui/customer_center.png
    python scripts/capture_ui_screenshot.py --tab coa --output artifacts/ui/chart_of_accounts.png
    python scripts/capture_ui_screenshot.py --tab register --output artifacts/ui/bank_register.png
    python scripts/capture_ui_screenshot.py --tab use-register --output artifacts/ui/use_register.png
    python scripts/capture_ui_screenshot.py --tab items --output artifacts/ui/item_list.png
    python scripts/capture_ui_screenshot.py --tab edit-item --output artifacts/ui/edit_item.png
    python scripts/capture_ui_screenshot.py --tab income-tracker --output artifacts/ui/income_tracker.png
    python scripts/capture_ui_screenshot.py --tab bill-tracker --output artifacts/ui/bill_tracker.png
    python scripts/capture_ui_screenshot.py --tab calendar --output artifacts/ui/calendar.png
    python scripts/capture_ui_screenshot.py --tab snapshot --output artifacts/ui/company_snapshot.png
    python scripts/capture_ui_screenshot.py --tab my-company --output artifacts/ui/my_company.png
    python scripts/capture_ui_screenshot.py --tab ar-aging --output artifacts/ui/ar_aging_summary.png
    python scripts/capture_ui_screenshot.py --tab ap-aging --output artifacts/ui/ap_aging_summary.png

Saves: artifacts/ui/main_window.png (default)
Exit code 0 on success, non-zero on failure.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path


def _save_pixmap(pixmap, output_path: Path) -> bool:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return bool(pixmap.save(str(output_path), "PNG"))


def _seed_generic_item_list(conn) -> None:
    """Placeholder catalog for screenshots — not Johnny's live QuickBooks names."""
    from probooksai import business

    business.replace_invoice_item_codes(
        conn,
        [
            {
                "code": "Hourly Labor",
                "description": "Standard hourly service",
                "item_type": "Service",
                "coa_account": "4000 – Sales Revenue",
                "rate_value": 85.0,
                "rate_kind": "amount",
                "sort_order": 0,
            },
            {
                "code": "Mileage",
                "description": "Per-mile travel",
                "item_type": "Service",
                "coa_account": "4000 – Sales Revenue",
                "rate_value": 0.7,
                "rate_kind": "amount",
                "sort_order": 1,
            },
            {
                "code": "Fuel Surcharge",
                "description": "Fuel surcharge on the invoice subtotal",
                "item_type": "Other Charge",
                "coa_account": "4000 – Sales Revenue",
                "rate_value": 3.0,
                "rate_kind": "percent",
                "sort_order": 2,
            },
            {
                "code": "Early Pay Discount",
                "description": "Discount for prompt payment",
                "item_type": "Discount",
                "coa_account": "4000 – Sales Revenue",
                "rate_value": -10.0,
                "rate_kind": "percent",
                "sort_order": 3,
            },
            {
                "code": "Line Subtotal",
                "description": "Subtotal of items above this line",
                "item_type": "Subtotal",
                "coa_account": "",
                "rate_value": 0.0,
                "rate_kind": "amount",
                "sort_order": 4,
            },
            {
                "code": "Rush Fee",
                "description": "Expedite fee",
                "item_type": "Other Charge",
                "coa_account": "4000 – Sales Revenue",
                "rate_value": 45.0,
                "rate_kind": "amount",
                "sort_order": 5,
            },
        ],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Headless ProBooks+ai UI screenshot helper.")
    parser.add_argument(
        "--tab",
        default="main",
        help="Which surface to capture: main (default), home, invoices, bills (Enter Bills), pay-bills, payments, deposits, checks, vendors, customers, coa, register, use-register, items, edit-item, income-tracker, bill-tracker, calendar, snapshot, my-company, or ar-aging.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="PNG path (default: artifacts/ui/main_window.png or create_invoices.png).",
    )
    args = parser.parse_args()

    # Must set the platform plugin before importing Qt widgets
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from desktop_app.check_screen import CheckScreen  # noqa: E402
    from desktop_app.coa_tab import COATab  # noqa: E402
    from desktop_app.dashboard_tab import DashboardTab  # noqa: E402
    from desktop_app.enter_bills_screen import EnterBillsScreen  # noqa: E402
    from desktop_app.invoice_codes_screen import EditItemDialog, InvoiceCodesScreen  # noqa: E402
    from desktop_app.invoice_screen import InvoiceScreen  # noqa: E402
    from desktop_app.main import MainWindow  # noqa: E402
    from desktop_app.make_deposits_screen import MakeDepositsScreen  # noqa: E402
    from desktop_app.pay_bills_screen import PayBillsScreen  # noqa: E402
    from desktop_app.receive_checks_screen import ReceiveChecksScreen  # noqa: E402
    from desktop_app.customer_center_screen import CustomerCenterScreen  # noqa: E402
    from desktop_app.register_tab import RegisterTab  # noqa: E402
    from desktop_app.use_register_dialog import UseRegisterDialog  # noqa: E402
    from desktop_app.tracker_screens import BillTrackerScreen, IncomeTrackerScreen  # noqa: E402
    from desktop_app.calendar_screen import CalendarScreen  # noqa: E402
    from desktop_app.company_snapshot_screen import CompanySnapshotScreen  # noqa: E402
    from desktop_app.my_company_screen import MyCompanyScreen  # noqa: E402
    from desktop_app.ap_aging_summary_screen import APAgingSummaryScreen  # noqa: E402
    from desktop_app.ar_aging_summary_screen import ARAgingSummaryScreen  # noqa: E402
    from desktop_app.vendor_center_screen import VendorCenterScreen  # noqa: E402

    app = QApplication(sys.argv)

    tab = (args.tab or "main").strip().lower()
    if args.output:
        output_path = Path(args.output)
    elif tab in ("invoices", "invoice", "create-invoices", "create_invoices"):
        output_path = Path("artifacts") / "ui" / "create_invoices.png"
    elif tab in ("bills", "enter-bills", "enter_bills"):
        output_path = Path("artifacts") / "ui" / "enter_bills.png"
    elif tab in ("pay-bills", "pay_bills", "paybills"):
        output_path = Path("artifacts") / "ui" / "pay_bills.png"
    elif tab in ("payments", "receive-payments", "receive_payments"):
        output_path = Path("artifacts") / "ui" / "receive_payments.png"
    elif tab in ("deposits", "make-deposits", "make_deposits"):
        output_path = Path("artifacts") / "ui" / "make_deposits.png"
    elif tab in ("checks", "write-checks", "write_checks"):
        output_path = Path("artifacts") / "ui" / "write_checks.png"
    elif tab in ("vendors", "vendor-center", "vendor_center"):
        output_path = Path("artifacts") / "ui" / "vendor_center.png"
    elif tab in ("customers", "customer-center", "customer_center"):
        output_path = Path("artifacts") / "ui" / "customer_center.png"
    elif tab in ("home", "dashboard"):
        output_path = Path("artifacts") / "ui" / "home.png"
    elif tab in ("coa", "chart-of-accounts", "chart_of_accounts"):
        output_path = Path("artifacts") / "ui" / "chart_of_accounts.png"
    elif tab in ("register", "bank-register", "bank_register"):
        output_path = Path("artifacts") / "ui" / "bank_register.png"
    elif tab in ("use-register", "use_register"):
        output_path = Path("artifacts") / "ui" / "use_register.png"
    elif tab in ("items", "item-list", "item_list", "codes"):
        output_path = Path("artifacts") / "ui" / "item_list.png"
    elif tab in ("edit-item", "edit_item"):
        output_path = Path("artifacts") / "ui" / "edit_item.png"
    elif tab in ("income-tracker", "income_tracker"):
        output_path = Path("artifacts") / "ui" / "income_tracker.png"
    elif tab in ("bill-tracker", "bill_tracker"):
        output_path = Path("artifacts") / "ui" / "bill_tracker.png"
    elif tab in ("calendar",):
        output_path = Path("artifacts") / "ui" / "calendar.png"
    elif tab in ("snapshot", "company-snapshot", "company_snapshot"):
        output_path = Path("artifacts") / "ui" / "company_snapshot.png"
    elif tab in ("my-company", "my_company"):
        output_path = Path("artifacts") / "ui" / "my_company.png"
    elif tab in ("ar-aging", "ar_aging", "ar-aging-summary", "ar_aging_summary"):
        output_path = Path("artifacts") / "ui" / "ar_aging_summary.png"
    elif tab in ("ap-aging", "ap_aging", "ap-aging-summary", "ap_aging_summary"):
        output_path = Path("artifacts") / "ui" / "ap_aging_summary.png"
    else:
        output_path = Path("artifacts") / "ui" / "main_window.png"

    extra_kw: dict = {}
    if tab in (
        "pay-bills",
        "pay_bills",
        "paybills",
        "vendors",
        "vendor-center",
        "vendor_center",
        "customers",
        "customer-center",
        "customer_center",
        "coa",
        "chart-of-accounts",
        "chart_of_accounts",
        "register",
        "bank-register",
        "bank_register",
        "use-register",
        "use_register",
        "items",
        "item-list",
        "item_list",
        "codes",
        "edit-item",
        "edit_item",
        "income-tracker",
        "income_tracker",
        "bill-tracker",
        "bill_tracker",
        "calendar",
        "snapshot",
        "company-snapshot",
        "company_snapshot",
        "my-company",
        "my_company",
        "ar-aging",
        "ar_aging",
        "ar-aging-summary",
        "ar_aging_summary",
        "ap-aging",
        "ap_aging",
        "ap-aging-summary",
        "ap_aging_summary",
    ):
        shot_dir = Path(tempfile.mkdtemp(prefix="probooks-ui-shot-"))
        extra_kw["db_path"] = str(shot_dir / "shot.db")

    window = MainWindow(**extra_kw)
    window.resize(1400, 900)
    window.show()

    grab_widget = None
    if tab in ("invoices", "invoice", "create-invoices", "create_invoices"):
        inv = getattr(window, "_invoice_screen", None)
        if inv is not None and hasattr(window, "_tabs"):
            idx = window._tabs.indexOf(inv)
            if idx >= 0:
                window._tabs.setCurrentIndex(idx)
        if isinstance(inv, InvoiceScreen):
            grab_widget = inv
            grab_widget.resize(1280, 860)
            grab_widget.show()
    elif tab in ("bills", "enter-bills", "enter_bills"):
        bills = getattr(window, "_enter_bills_screen", None)
        if bills is not None and hasattr(window, "_tabs"):
            idx = window._tabs.indexOf(bills)
            if idx >= 0:
                window._tabs.setCurrentIndex(idx)
        if isinstance(bills, EnterBillsScreen):
            grab_widget = bills
            grab_widget.resize(1280, 860)
            grab_widget.show()
    elif tab in ("pay-bills", "pay_bills", "paybills"):
        from probooksai import business

        pay_bills = getattr(window, "_pay_bills_screen", None)
        conn = getattr(getattr(window, "_bank_db", None), "_conn", None)
        bank_db = getattr(window, "_bank_db", None)
        if conn is not None:
            if bank_db is not None:
                try:
                    bank_db.add_bank_account("Checking")
                except (ValueError, TypeError):
                    pass
            v1 = business.add_vendor(conn, "Office Supplies Co")
            business.create_bill(
                conn,
                v1,
                "2026-08-01",
                450.00,
                vendor_invoice_number="INV-1042",
                due_date="2026-08-31",
            )
            v2 = business.add_vendor(conn, "Warehouse Supply")
            business.create_bill(
                conn,
                v2,
                "2026-07-15",
                1280.50,
                vendor_invoice_number="WS-88",
                due_date="2026-08-14",
            )
            v3 = business.add_vendor(conn, "Fuel Vendor")
            business.create_bill(
                conn,
                v3,
                "2026-06-20",
                96.40,
                vendor_invoice_number="FV-12",
                due_date="2026-07-20",
            )
            if isinstance(pay_bills, PayBillsScreen):
                pay_bills.reload()
        if pay_bills is not None and hasattr(window, "_tabs"):
            idx = window._tabs.indexOf(pay_bills)
            if idx >= 0:
                window._tabs.setCurrentIndex(idx)
        if isinstance(pay_bills, PayBillsScreen):
            grab_widget = pay_bills
            grab_widget.resize(1280, 860)
            grab_widget.setMinimumSize(1280, 860)
            grab_widget.show()
    elif tab in ("payments", "receive-payments", "receive_payments"):
        pay = getattr(window, "_receive_payments_screen", None)
        if pay is not None and hasattr(window, "_tabs"):
            idx = window._tabs.indexOf(pay)
            if idx >= 0:
                window._tabs.setCurrentIndex(idx)
        if isinstance(pay, ReceiveChecksScreen):
            grab_widget = pay
            grab_widget.resize(1280, 860)
            grab_widget.setMinimumSize(1280, 860)
            grab_widget.show()
    elif tab in ("deposits", "make-deposits", "make_deposits"):
        dep = getattr(window, "_make_deposits_screen", None)
        if dep is not None and hasattr(window, "_tabs"):
            idx = window._tabs.indexOf(dep)
            if idx >= 0:
                window._tabs.setCurrentIndex(idx)
        if isinstance(dep, MakeDepositsScreen):
            grab_widget = dep
            grab_widget.resize(1280, 860)
            grab_widget.setMinimumSize(1280, 860)
            grab_widget.show()
    elif tab in ("checks", "write-checks", "write_checks"):
        chk = getattr(window, "_check_screen", None)
        if chk is not None and hasattr(window, "_tabs"):
            idx = window._tabs.indexOf(chk)
            if idx >= 0:
                window._tabs.setCurrentIndex(idx)
        if isinstance(chk, CheckScreen):
            grab_widget = chk
            grab_widget.resize(1280, 860)
            grab_widget.setMinimumSize(1280, 860)
            grab_widget.show()
    elif tab in ("vendors", "vendor-center", "vendor_center"):
        from probooksai import business

        vendors = getattr(window, "_vendors_tab", None)
        conn = getattr(getattr(window, "_bank_db", None), "_conn", None)
        if conn is not None:
            v1 = business.add_vendor(
                conn,
                "Office Supplies Co",
                address="100 Supply Lane\nAustin, TX 78701",
                notes="Office stock — weekly delivery.",
            )
            business.create_bill(
                conn,
                v1,
                "2026-08-01",
                450.00,
                vendor_invoice_number="INV-1042",
                due_date="2026-08-31",
            )
            v2 = business.add_vendor(conn, "Warehouse Supply")
            bid = business.create_bill(
                conn,
                v2,
                "2026-07-15",
                1280.50,
                vendor_invoice_number="WS-88",
                due_date="2026-08-14",
            )
            business.record_ap_payment(
                conn,
                v2,
                "2026-08-10",
                500.00,
                [(bid, 500.00)],
                method="Check",
                reference="1008",
            )
            v3 = business.add_vendor(conn, "Fuel Vendor")
            business.create_bill(
                conn,
                v3,
                "2026-06-20",
                96.40,
                vendor_invoice_number="FV-12",
                due_date="2026-07-20",
            )
            if isinstance(vendors, VendorCenterScreen):
                vendors._focused_vendor_id = v1
                vendors._refresh()
        if vendors is not None and hasattr(window, "_tabs"):
            idx = window._tabs.indexOf(vendors)
            if idx >= 0:
                window._tabs.setCurrentIndex(idx)
        if isinstance(vendors, VendorCenterScreen):
            grab_widget = vendors
            grab_widget.resize(1400, 860)
            grab_widget.setMinimumSize(1400, 860)
            grab_widget.show()
    elif tab in ("customers", "customer-center", "customer_center"):
        from probooksai import business

        customers = getattr(window, "_customers_tab", None)
        conn = getattr(getattr(window, "_bank_db", None), "_conn", None)
        if conn is not None:
            c1 = business.add_customer(
                conn,
                "Harbor Logistics",
                address="200 Harbor Way\nAustin, TX 78701",
                notes="Weekly dispatch — terms Net 30.",
            )
            business.create_invoice(
                conn,
                c1,
                "INV-2101",
                "2026-08-01",
                due_date="2026-08-31",
                lines=[{"description": "Haul", "qty": 1, "rate": 450.00}],
            )
            job = business.add_customer(conn, "Site A", parent_customer_id=c1)
            business.create_invoice(
                conn,
                job,
                "JOB-12",
                "2026-08-05",
                due_date="2026-09-04",
                lines=[{"description": "Site work", "qty": 1, "rate": 200.00}],
            )
            c2 = business.add_customer(conn, "Westside Hauling")
            iid = business.create_invoice(
                conn,
                c2,
                "WH-88",
                "2026-07-15",
                due_date="2026-08-14",
                lines=[{"description": "Haul", "qty": 1, "rate": 1280.50}],
            )
            business.record_ar_payment(
                conn,
                c2,
                "2026-08-10",
                500.00,
                [(iid, 500.00)],
                method="Check",
                reference="1008",
            )
            c3 = business.add_customer(conn, "Metro Freight")
            business.create_invoice(
                conn,
                c3,
                "MF-40",
                "2026-06-20",
                due_date="2026-07-20",
                lines=[{"description": "Haul", "qty": 1, "rate": 96.40}],
            )
            if isinstance(customers, CustomerCenterScreen):
                customers._focused_customer_id = c1
                customers._refresh()
        if customers is not None and hasattr(window, "_tabs"):
            idx = window._tabs.indexOf(customers)
            if idx >= 0:
                window._tabs.setCurrentIndex(idx)
        if isinstance(customers, CustomerCenterScreen):
            grab_widget = customers
            grab_widget.resize(1400, 860)
            grab_widget.setMinimumSize(1400, 860)
            grab_widget.show()
    elif tab in ("home", "dashboard"):
        home = getattr(window, "_dashboard_tab", None)
        if home is not None and hasattr(window, "_tabs"):
            idx = window._tabs.indexOf(home)
            if idx >= 0:
                window._tabs.setCurrentIndex(idx)
        if isinstance(home, DashboardTab):
            grab_widget = home
            grab_widget.resize(1400, 860)
            grab_widget.setMinimumSize(1400, 860)
            grab_widget.show()
    elif tab in ("coa", "chart-of-accounts", "chart_of_accounts"):
        coa_tab = getattr(window, "_coa_tab", None)
        coa_db = getattr(window, "_coa_db", None)
        if coa_db is not None:
            vehicles_id = None
            for row in coa_db.list_accounts(include_inactive=True):
                if str(row["account_name"] or "") == "Vehicles":
                    vehicles_id = int(row["id"])
                    break
            if vehicles_id is not None:
                try:
                    coa_db.add_account(
                        "1701",
                        "Trailer unit",
                        "fixed_asset",
                        sub_type="Fixed Asset",
                        parent_id=vehicles_id,
                    )
                except (ValueError, TypeError):
                    pass
        if isinstance(coa_tab, COATab):
            coa_tab._refresh()
            if coa_tab._table.rowCount() > 0:
                coa_tab._table.selectRow(0)
        if coa_tab is not None and hasattr(window, "_tabs"):
            idx = window._tabs.indexOf(coa_tab)
            if idx >= 0:
                window._tabs.setCurrentIndex(idx)
        grab_widget = coa_tab
        if grab_widget is not None:
            grab_widget.resize(1280, 860)
            grab_widget.setMinimumSize(1280, 860)
            grab_widget.show()
    elif tab in ("register", "bank-register", "bank_register", "use-register", "use_register"):
        bank_db = getattr(window, "_bank_db", None)
        register = getattr(window, "_register_tab", None)
        aid = None
        if bank_db is not None:
            existing = list(bank_db.list_bank_accounts())
            if existing:
                aid = int(existing[0]["id"])
            else:
                aid = bank_db.add_bank_account(
                    "Checking",
                    account_number="1000",
                    gl_display_account="1000 Cash – Checking",
                )
            bank_db.insert_manual_transaction(
                aid,
                "2026-08-05",
                -790.00,
                description="Office Supplies Co",
                ref_number="1001",
                memo="BILLPMT",
                coa_account="2000 Accounts Payable",
            )
            bank_db.insert_manual_transaction(
                aid,
                "2026-08-06",
                391.50,
                description="Deposit",
                ref_number="DEP",
                memo="DEP",
            )
            bank_db.insert_manual_transaction(
                aid,
                "2026-08-07",
                -125.00,
                description="Fuel Vendor",
                ref_number="1002",
                memo="CHK",
                coa_account="6310 Vehicle Expense",
            )
        if isinstance(register, RegisterTab) and aid is not None:
            register.select_bank_account(aid)
            if register._table.rowCount() > 0:
                register._table.selectRow(0)
        if tab in ("use-register", "use_register"):
            dlg = UseRegisterDialog(
                bank_db, initial_account_id=aid, parent=window
            )
            dlg.show()
            grab_widget = dlg
            grab_widget.resize(380, 140)
            grab_widget.show()
        else:
            if register is not None and hasattr(window, "_tabs"):
                idx = window._tabs.indexOf(register)
                if idx >= 0:
                    window._tabs.setCurrentIndex(idx)
            grab_widget = register
            if grab_widget is not None:
                grab_widget.resize(1280, 860)
                grab_widget.setMinimumSize(1280, 860)
                grab_widget.show()
    elif tab in (
        "items",
        "item-list",
        "item_list",
        "codes",
        "edit-item",
        "edit_item",
    ):
        from probooksai import business

        codes = getattr(window, "_invoice_codes_screen", None)
        conn = getattr(getattr(window, "_bank_db", None), "_conn", None)
        labor_id = None
        if conn is not None:
            _seed_generic_item_list(conn)
            row = business.get_invoice_item_code_by_code(conn, "Hourly Labor")
            if row is not None:
                labor_id = int(row["id"])
        if isinstance(codes, InvoiceCodesScreen):
            codes._load_from_db()
            if codes._table.rowCount() > 0:
                codes._table.selectRow(0)
        if tab in ("edit-item", "edit_item"):
            dlg = None
            if isinstance(codes, InvoiceCodesScreen):
                dlg = codes._make_edit_dialog(labor_id)
            if dlg is None and conn is not None:
                dlg = EditItemDialog(
                    conn,
                    item_id=labor_id,
                    coa_db=getattr(window, "_coa_db", None),
                    parent=window,
                )
            if dlg is not None:
                dlg.show()
                grab_widget = dlg
                grab_widget.resize(640, 360)
                grab_widget.show()
        else:
            if codes is not None and hasattr(window, "_tabs"):
                idx = window._tabs.indexOf(codes)
                if idx >= 0:
                    window._tabs.setCurrentIndex(idx)
            grab_widget = codes
            if grab_widget is not None:
                grab_widget.resize(1280, 860)
            grab_widget.setMinimumSize(1280, 860)
            grab_widget.show()
    elif tab in ("income-tracker", "income_tracker", "bill-tracker", "bill_tracker"):
        from probooksai import business

        conn = getattr(getattr(window, "_bank_db", None), "_conn", None)
        if conn is not None:
            c1 = business.add_customer(conn, "Harbor Logistics")
            business.create_invoice(
                conn,
                c1,
                "INV-2101",
                "2026-08-01",
                due_date="2026-09-15",
                lines=[{"description": "Haul", "qty": 1, "rate": 450.00}],
            )
            business.create_invoice(
                conn,
                c1,
                "INV-0888",
                "2026-06-01",
                due_date="2026-07-01",
                lines=[{"description": "Haul", "qty": 1, "rate": 180.00}],
            )
            paid = business.create_invoice(
                conn,
                c1,
                "INV-1990",
                "2026-08-05",
                due_date="2026-08-20",
                lines=[{"description": "Haul", "qty": 1, "rate": 75.00}],
            )
            business.record_ar_payment(
                conn, c1, "2026-08-18", 75.00, [(paid, 75.00)], method="Check", reference="1008"
            )
            v1 = business.add_vendor(conn, "Office Supplies Co")
            v2 = business.add_vendor(conn, "Warehouse Supply")
            business.create_bill(
                conn, v1, "2026-08-01", 450.00, vendor_invoice_number="OS-1042", due_date="2026-09-01"
            )
            business.create_bill(
                conn, v2, "2026-06-20", 96.40, vendor_invoice_number="WS-12", due_date="2026-07-20"
            )
            paid_bill = business.create_bill(
                conn, v1, "2026-08-08", 50.00, vendor_invoice_number="OS-88", due_date="2026-08-22"
            )
            business.record_ap_payment(
                conn, v1, "2026-08-19", 50.00, [(paid_bill, 50.00)], method="Check", reference="1001"
            )
        if tab in ("income-tracker", "income_tracker"):
            screen = getattr(window, "_income_tracker_screen", None)
            if isinstance(screen, IncomeTrackerScreen):
                screen.reload()
                if screen._table.rowCount() > 0:
                    screen._table.selectRow(0)
        else:
            screen = getattr(window, "_bill_tracker_screen", None)
            if isinstance(screen, BillTrackerScreen):
                screen.reload()
                if screen._table.rowCount() > 0:
                    screen._table.selectRow(0)
        if screen is not None and hasattr(window, "_tabs"):
            idx = window._tabs.indexOf(screen)
            if idx >= 0:
                window._tabs.setCurrentIndex(idx)
        grab_widget = screen
        if grab_widget is not None:
            grab_widget.resize(1280, 860)
            grab_widget.setMinimumSize(1280, 860)
            grab_widget.show()
    elif tab in ("calendar",):
        from datetime import date as _date

        from probooksai import business
        from probooksai import qb_calendar as cal

        conn = getattr(getattr(window, "_bank_db", None), "_conn", None)
        if conn is not None:
            c1 = business.add_customer(conn, "Harbor Logistics")
            business.create_invoice(
                conn,
                c1,
                "INV-2101",
                "2026-08-10",
                due_date="2026-09-15",
                lines=[{"description": "Haul", "qty": 1, "rate": 450.00}],
            )
            business.create_invoice(
                conn,
                c1,
                "INV-0888",
                "2026-07-01",
                due_date="2026-08-16",
                lines=[{"description": "Haul", "qty": 1, "rate": 180.00}],
            )
            business.create_invoice(
                conn,
                c1,
                "INV-0400",
                "2026-06-01",
                due_date="2026-07-15",
                lines=[{"description": "Haul", "qty": 1, "rate": 90.00}],
            )
            v1 = business.add_vendor(conn, "Office Supplies Co")
            v2 = business.add_vendor(conn, "Warehouse Supply")
            v3 = business.add_vendor(conn, "Fuel Vendor")
            v4 = business.add_vendor(conn, "Shop Parts LLC")
            business.create_bill(
                conn, v1, "2026-08-10", 450.00, vendor_invoice_number="OS-1042", due_date="2026-08-30"
            )
            business.create_bill(
                conn, v2, "2026-06-20", 210.00, vendor_invoice_number="WS-12", due_date="2026-07-20"
            )
            business.create_bill(
                conn, v3, "2026-06-22", 88.50, vendor_invoice_number="FV-19", due_date="2026-07-21"
            )
            business.create_bill(
                conn, v4, "2026-06-25", 125.00, vendor_invoice_number="SP-4", due_date="2026-07-22"
            )
            business.create_bill(
                conn, v1, "2026-07-01", 64.00, vendor_invoice_number="OS-77", due_date="2026-07-31"
            )
            cal.add_todo(conn, title="Call broker", due_date="2026-08-28", notes="")
        screen = getattr(window, "_calendar_screen", None)
        if isinstance(screen, CalendarScreen):
            screen._today = _date(2026, 8, 27)
            screen._month = _date(2026, 8, 1)
            screen._selected = _date(2026, 8, 26)
            screen.reload()
        if screen is not None and hasattr(window, "_tabs"):
            idx = window._tabs.indexOf(screen)
            if idx >= 0:
                window._tabs.setCurrentIndex(idx)
        grab_widget = screen
        if grab_widget is not None:
            grab_widget.resize(1400, 900)
            grab_widget.setMinimumSize(1400, 900)
            grab_widget.show()
    elif tab in ("snapshot", "company-snapshot", "company_snapshot"):
        from datetime import date as _date

        from probooksai import business

        conn = getattr(getattr(window, "_bank_db", None), "_conn", None)
        bank_db = getattr(window, "_bank_db", None)
        if conn is not None:
            c1 = business.add_customer(conn, "Harbor Logistics")
            business.create_invoice(
                conn,
                c1,
                "INV-2101",
                "2026-01-12",
                due_date="2026-02-10",
                lines=[{"description": "Haul", "qty": 1, "rate": 420.00}],
            )
            business.create_invoice(
                conn,
                c1,
                "INV-0888",
                "2026-06-08",
                due_date="2026-07-08",
                lines=[{"description": "Haul", "qty": 1, "rate": 180.00}],
            )
            business.create_invoice(
                conn,
                c1,
                "INV-1990",
                "2025-11-02",
                due_date="2025-12-01",
                lines=[{"description": "Haul", "qty": 1, "rate": 260.00}],
            )
            c2 = business.add_customer(conn, "Westside Hauling")
            business.create_invoice(
                conn,
                c2,
                "WH-88",
                "2026-08-05",
                due_date="2026-09-04",
                lines=[{"description": "Haul", "qty": 1, "rate": 310.00}],
            )
            c3 = business.add_customer(conn, "Metro Freight")
            business.create_invoice(
                conn,
                c3,
                "MF-40",
                "2026-03-20",
                due_date="2026-04-20",
                lines=[{"description": "Haul", "qty": 1, "rate": 96.40}],
            )
            v1 = business.add_vendor(conn, "Office Supplies Co")
            v2 = business.add_vendor(conn, "Fuel Vendor")
            business.create_bill(
                conn, v1, "2026-02-10", 75.00, vendor_invoice_number="OS-1042", due_date="2026-03-01"
            )
            business.create_bill(
                conn, v2, "2026-06-12", 140.00, vendor_invoice_number="FV-19", due_date="2026-07-12"
            )
            business.create_bill(
                conn, v1, "2025-08-04", 40.00, vendor_invoice_number="OS-88", due_date="2025-09-04"
            )
            if bank_db is not None:
                existing = list(bank_db.list_bank_accounts())
                if existing:
                    aid = int(existing[0]["id"])
                else:
                    aid = bank_db.add_bank_account("Checking", "1000", "Bank")
                bank_db.insert_manual_transaction(
                    aid, "2026-01-05", 800.00, description="Opening"
                )
                bank_db.insert_manual_transaction(
                    aid,
                    "2026-06-02",
                    -140.00,
                    description="Fuel Vendor",
                    coa_account="6310 Vehicle Expense",
                )
                bank_db.insert_manual_transaction(
                    aid,
                    "2026-02-12",
                    -75.00,
                    description="Office Supplies Co",
                    coa_account="6220 Office Supplies",
                )
                bank_db.insert_manual_transaction(
                    aid,
                    "2026-04-03",
                    -48.00,
                    description="Shop rent",
                    coa_account="6100 Rent Expense",
                )
        screen = getattr(window, "_snapshot_screen", None)
        if isinstance(screen, CompanySnapshotScreen):
            screen._today = _date(2026, 8, 27)
            screen.restore_default()
            screen.reload()
        if screen is not None and hasattr(window, "_tabs"):
            idx = window._tabs.indexOf(screen)
            if idx >= 0:
                window._tabs.setCurrentIndex(idx)
        grab_widget = screen
        if grab_widget is not None:
            grab_widget.resize(1400, 900)
            grab_widget.setMinimumSize(1400, 900)
            grab_widget.show()
    elif tab in ("my-company", "my_company"):
        screen = getattr(window, "_my_company_screen", None)
        if screen is not None and hasattr(window, "_tabs"):
            idx = window._tabs.indexOf(screen)
            if idx >= 0:
                window._tabs.setCurrentIndex(idx)
        if isinstance(screen, MyCompanyScreen):
            screen.reload()
        grab_widget = screen
        if grab_widget is not None:
            grab_widget.resize(1400, 900)
            grab_widget.setMinimumSize(1400, 900)
            grab_widget.show()
    elif tab in ("ar-aging", "ar_aging", "ar-aging-summary", "ar_aging_summary"):
        from datetime import date as _date

        from PySide6.QtCore import QDate

        from probooksai import business

        conn = getattr(getattr(window, "_bank_db", None), "_conn", None)
        if conn is not None:
            parent = business.add_customer(conn, "Harbor Logistics")
            job = business.add_customer(conn, "Site A", parent_customer_id=parent)
            business.create_invoice(
                conn,
                parent,
                "INV-2101",
                "2026-08-01",
                due_date="2026-08-20",
                lines=[{"description": "Haul", "qty": 1, "rate": 450.00}],
            )
            business.create_invoice(
                conn,
                job,
                "JOB-12",
                "2026-07-01",
                due_date="2026-07-10",
                lines=[{"description": "Site work", "qty": 1, "rate": 200.00}],
            )
            c2 = business.add_customer(conn, "Westside Hauling")
            iid = business.create_invoice(
                conn,
                c2,
                "WH-88",
                "2026-07-15",
                due_date="2026-08-14",
                lines=[{"description": "Haul", "qty": 1, "rate": 780.50}],
            )
            business.record_ar_payment(
                conn,
                c2,
                "2026-08-10",
                200.00,
                [(iid, 200.00)],
                method="Check",
                reference="1008",
            )
            c3 = business.add_customer(conn, "Metro Freight")
            business.create_invoice(
                conn,
                c3,
                "MF-40",
                "2026-06-01",
                due_date="2026-06-20",
                lines=[{"description": "Haul", "qty": 1, "rate": 96.40}],
            )
            c4 = business.add_customer(conn, "Northwind Cartage")
            business.create_invoice(
                conn,
                c4,
                "NW-7",
                "2026-04-01",
                due_date="2026-04-15",
                lines=[{"description": "Haul", "qty": 1, "rate": 310.00}],
            )
            c5 = business.add_customer(conn, "Ridgeway Express")
            business.create_invoice(
                conn,
                c5,
                "RX-3",
                "2026-08-20",
                due_date="2026-09-20",
                lines=[{"description": "Haul", "qty": 1, "rate": 125.00}],
            )
        screen = getattr(window, "_ar_aging_screen", None)
        if isinstance(screen, ARAgingSummaryScreen):
            as_of = _date(2026, 8, 27)
            screen._dates.blockSignals(True)
            screen._dates.setCurrentText("Custom Date")
            screen._dates.blockSignals(False)
            screen._as_of_edit.blockSignals(True)
            screen._as_of_edit.setDate(QDate(as_of.year, as_of.month, as_of.day))
            screen._as_of_edit.blockSignals(False)
            screen.reload()
        if screen is not None and hasattr(window, "_tabs"):
            idx = window._tabs.indexOf(screen)
            if idx >= 0:
                window._tabs.setCurrentIndex(idx)
        grab_widget = screen
        if grab_widget is not None:
            grab_widget.resize(1400, 900)
            grab_widget.setMinimumSize(1400, 900)
            grab_widget.show()
    elif tab in ("ap-aging", "ap_aging", "ap-aging-summary", "ap_aging_summary"):
        from datetime import date as _date

        from PySide6.QtCore import QDate

        from probooksai import business

        conn = getattr(getattr(window, "_bank_db", None), "_conn", None)
        if conn is not None:
            v1 = business.add_vendor(conn, "Office Supplies Co")
            business.create_bill(
                conn,
                v1,
                "2026-08-01",
                450.00,
                vendor_invoice_number="OS-1042",
                due_date="2026-08-20",
            )
            v2 = business.add_vendor(conn, "Warehouse Supply")
            bid = business.create_bill(
                conn,
                v2,
                "2026-07-01",
                780.50,
                vendor_invoice_number="WS-88",
                due_date="2026-07-15",
            )
            business.record_ap_payment(
                conn,
                v2,
                "2026-08-10",
                200.00,
                [(bid, 200.00)],
                method="Check",
                reference="1008",
            )
            v3 = business.add_vendor(conn, "Fuel Vendor")
            business.create_bill(
                conn,
                v3,
                "2026-06-01",
                96.40,
                vendor_invoice_number="FV-12",
                due_date="2026-06-20",
            )
            v4 = business.add_vendor(conn, "Shop Parts LLC")
            business.create_bill(
                conn,
                v4,
                "2026-04-01",
                310.00,
                vendor_invoice_number="SP-4",
                due_date="2026-04-15",
            )
            v5 = business.add_vendor(conn, "Northwind Freight")
            business.create_bill(
                conn,
                v5,
                "2026-08-20",
                125.00,
                vendor_invoice_number="NF-3",
                due_date="2026-09-20",
            )
        screen = getattr(window, "_ap_aging_screen", None)
        if isinstance(screen, APAgingSummaryScreen):
            as_of = _date(2026, 8, 27)
            screen._dates.blockSignals(True)
            screen._dates.setCurrentText("Custom Date")
            screen._dates.blockSignals(False)
            screen._as_of_edit.blockSignals(True)
            screen._as_of_edit.setDate(QDate(as_of.year, as_of.month, as_of.day))
            screen._as_of_edit.blockSignals(False)
            screen.reload()
        if screen is not None and hasattr(window, "_tabs"):
            idx = window._tabs.indexOf(screen)
            if idx >= 0:
                window._tabs.setCurrentIndex(idx)
        grab_widget = screen
        if grab_widget is not None:
            grab_widget.resize(1400, 900)
            grab_widget.setMinimumSize(1400, 900)
            grab_widget.show()

    success = False

    def take_screenshot() -> None:
        nonlocal success

        pixmap = None
        if grab_widget is not None:
            pixmap = grab_widget.grab()
        if pixmap is None or pixmap.isNull():
            screen = app.primaryScreen()
            if screen is None:
                print("ERROR: No primary screen found.", file=sys.stderr)
                app.exit(1)
                return
            pixmap = screen.grabWindow(int(window.winId()))
        if pixmap.isNull():
            print("ERROR: grab returned a null pixmap.", file=sys.stderr)
            app.exit(1)
            return

        saved = _save_pixmap(pixmap, output_path)
        if not saved:
            print(f"ERROR: Failed to save screenshot to {output_path}", file=sys.stderr)
            app.exit(1)
            return

        print(f"Screenshot saved to {output_path} ({pixmap.width()}x{pixmap.height()} px)")
        success = True
        app.quit()

    QTimer.singleShot(500, take_screenshot)

    exit_code = app.exec()
    if not success and exit_code == 0:
        return 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
