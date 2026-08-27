"""
capture_ui_screenshot.py
========================
Headless screenshot helper for ProBooks+ai CI.

Usage (with a virtual display already active, e.g. via xvfb-run):
    python scripts/capture_ui_screenshot.py
    python scripts/capture_ui_screenshot.py --tab invoices --output artifacts/ui/create_invoices.png
    python scripts/capture_ui_screenshot.py --tab bills --output artifacts/ui/enter_bills.png
    python scripts/capture_ui_screenshot.py --tab payments --output artifacts/ui/receive_payments.png

Saves: artifacts/ui/main_window.png (default)
Exit code 0 on success, non-zero on failure.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _save_pixmap(pixmap, output_path: Path) -> bool:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return bool(pixmap.save(str(output_path), "PNG"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Headless ProBooks+ai UI screenshot helper.")
    parser.add_argument(
        "--tab",
        default="main",
        help="Which surface to capture: main (default), invoices, bills (Enter Bills), or payments.",
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
    from desktop_app.enter_bills_screen import EnterBillsScreen  # noqa: E402
    from desktop_app.invoice_screen import InvoiceScreen  # noqa: E402
    from desktop_app.main import MainWindow  # noqa: E402
    from desktop_app.receive_checks_screen import ReceiveChecksScreen  # noqa: E402

    app = QApplication(sys.argv)

    tab = (args.tab or "main").strip().lower()
    if args.output:
        output_path = Path(args.output)
    elif tab in ("invoices", "invoice", "create-invoices", "create_invoices"):
        output_path = Path("artifacts") / "ui" / "create_invoices.png"
    elif tab in ("bills", "enter-bills", "enter_bills"):
        output_path = Path("artifacts") / "ui" / "enter_bills.png"
    elif tab in ("payments", "receive-payments", "receive_payments"):
        output_path = Path("artifacts") / "ui" / "receive_payments.png"
    else:
        output_path = Path("artifacts") / "ui" / "main_window.png"

    window = MainWindow()
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
