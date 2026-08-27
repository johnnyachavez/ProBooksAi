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


def main() -> int:
    parser = argparse.ArgumentParser(description="Headless ProBooks+ai UI screenshot helper.")
    parser.add_argument(
        "--tab",
        default="main",
        help="Which surface to capture: main (default), home, invoices, bills (Enter Bills), pay-bills, payments, deposits, checks, vendors, or customers.",
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
    from desktop_app.dashboard_tab import DashboardTab  # noqa: E402
    from desktop_app.enter_bills_screen import EnterBillsScreen  # noqa: E402
    from desktop_app.invoice_screen import InvoiceScreen  # noqa: E402
    from desktop_app.main import MainWindow  # noqa: E402
    from desktop_app.make_deposits_screen import MakeDepositsScreen  # noqa: E402
    from desktop_app.pay_bills_screen import PayBillsScreen  # noqa: E402
    from desktop_app.receive_checks_screen import ReceiveChecksScreen  # noqa: E402
    from desktop_app.customer_center_screen import CustomerCenterScreen  # noqa: E402
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
