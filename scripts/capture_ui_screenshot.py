"""
capture_ui_screenshot.py
========================
Headless screenshot helper for ProBooks+ai CI and local review.

Usage (with a virtual display already active, e.g. via xvfb-run):
    python scripts/capture_ui_screenshot.py

Offscreen (no Xvfb):
    QT_QPA_PLATFORM=offscreen python scripts/capture_ui_screenshot.py

Saves under ``artifacts/ui/`` (gitignored):

- ``main_window.png`` — full main window on the **Invoices** tab
- ``invoice_create.png`` — Create Invoices (Manual Invoice) form
- ``invoice_create_header.png`` — header close-up (Bill To, Ship To, dates, terms, Amount)

A throwaway company file is opened so the first-run welcome dialog does not
cover the form. Sample Bill To / Ship To / terms / line Amount are filled for
the capture only; invoice save behavior is unchanged.
Exit code 0 on success, non-zero on failure.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def seed_capture_company_db(db_path: Path) -> int:
    """Create a company file with identity + one customer. Returns customer id."""
    from probooksai import business
    from probooksai.bank_import import BankDatabase
    from probooksai.company_identity import save_company_identity
    from probooksai.extensions_schema import apply_extensions

    db = BankDatabase(str(db_path))
    apply_extensions(db._conn)
    save_company_identity(
        db._conn,
        name="COMPANY NAME",
        address="123 Example Street\nPortland, OR 97201",
        phone="555-0100",
        email="billing@example.test",
        tax_id="",
        business_type="LLC",
        tax_structure="LLC – Single-member (disregarded)",
    )
    cid = business.add_customer(
        db._conn,
        "Acme Logistics LLC",
        email="ap@acme.test",
        phone="555-0199",
        address="200 Oak Ave\nPortland, OR 97201",
        notes="Contact: Dana Lee",
    )
    db.close()
    return int(cid)


def fill_create_invoice_form_for_capture(window, customer_id: int) -> None:
    """Switch to Invoices and fill header + one line so QB Pro fields are visible.

    Does not call Save. Demo data is for screenshots only.
    """
    from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QLineEdit

    from desktop_app.invoice_screen import InvoiceScreen

    inv = getattr(window, "_invoice_screen", None)
    tabs = getattr(window, "_tabs", None)
    if inv is None or tabs is None or not isinstance(inv, InvoiceScreen):
        raise RuntimeError("Main window has no Invoices tab.")
    idx = tabs.indexOf(inv)
    if idx < 0:
        raise RuntimeError("Invoices tab is not in the main tab strip.")
    tabs.setCurrentIndex(idx)
    inner = getattr(inv, "_invoice_tabs", None)
    if inner is not None:
        inner.setCurrentIndex(0)
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    inv.show()
    if app is not None:
        app.processEvents()

    panel = inv.bill_to_customer_panel()
    panel.select_customer_by_id(int(customer_id))
    if app is not None:
        app.processEvents()

    inv._terms.setCurrentText("Net 30")
    ship = getattr(inv, "_ship_to", None)
    if ship is not None:
        ship[1].setPlainText("Acme Warehouse\n90 Harbor Rd\nPortland, OR 97201")

    desc = inv._table.cellWidget(0, 2)
    rate = inv._table.cellWidget(0, 4)
    qty = inv._table.cellWidget(0, 5)
    if isinstance(desc, QLineEdit):
        desc.setText("Linehaul")
    if isinstance(rate, QDoubleSpinBox):
        rate.setValue(125.00)
    if isinstance(qty, QDoubleSpinBox):
        qty.setValue(4.0)
    inv._sync_invoice_line_row_total(0)
    inv._recalc_invoice_footer_from_grid()
    if app is not None:
        app.processEvents()


def grab_widget_png(widget, output_path: Path, *, max_height: int | None = None) -> None:
    """Save *widget* via ``QWidget.grab()`` (works under offscreen and Xvfb)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pixmap = widget.grab()
    if pixmap.isNull():
        raise RuntimeError(f"grab() returned a null pixmap for {output_path}")
    if pixmap.width() < 8 or pixmap.height() < 8:
        raise RuntimeError(
            f"grab() pixmap too small ({pixmap.width()}x{pixmap.height()}) for {output_path}"
        )
    if max_height is not None and pixmap.height() > max_height:
        pixmap = pixmap.copy(0, 0, pixmap.width(), max_height)
    if not pixmap.save(str(output_path), "PNG"):
        raise RuntimeError(f"Failed to save screenshot to {output_path}")
    print(f"Screenshot saved to {output_path} ({pixmap.width()}x{pixmap.height()} px)")


def _prepare_main_window_for_capture(window, width: int = 1440, height: int = 960) -> None:
    """Undo first-run maximized geometry so the invoice form is a readable size."""
    from PySide6.QtCore import Qt

    window.setWindowState(Qt.WindowState.WindowNoState)
    window.showNormal()
    window.resize(width, height)
    window.setMinimumSize(width, height)
    window.show()


def main() -> int:
    # Must set the platform plugin before importing Qt widgets.
    # CI sets QT_QPA_PLATFORM=xcb with xvfb-run; local headless uses offscreen.
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

    from PySide6.QtCore import QSettings, QTimer
    from PySide6.QtWidgets import QApplication, QFrame

    sys.path.insert(0, str(_repo_root()))
    from desktop_app.main import MainWindow  # noqa: E402
    from desktop_app.theme import apply_dark_theme  # noqa: E402

    app = QApplication(sys.argv)
    app.setApplicationName("ProBooks+ai")
    app.setOrganizationName("ProBooks+ai")
    apply_dark_theme(app)

    tmp = Path(tempfile.mkdtemp(prefix="probooks-ui-capture-"))
    db_path = tmp / "capture_company.db"
    customer_id = seed_capture_company_db(db_path)
    # Skip the first-run welcome card (needs a saved path *or* an explicit db_path).
    QSettings().setValue("company_file_setup_prompted", True)

    window = MainWindow(db_path=str(db_path))
    _prepare_main_window_for_capture(window)
    app.processEvents()
    fill_create_invoice_form_for_capture(window, customer_id)

    success = False
    out_dir = Path("artifacts") / "ui"

    def take_screenshot() -> None:
        nonlocal success
        try:
            grab_widget_png(window, out_dir / "main_window.png")
            grab_widget_png(window._invoice_screen, out_dir / "invoice_create.png")
            form = window._invoice_screen.findChild(QFrame, "invoiceLightPanel")
            if form is not None:
                grab_widget_png(
                    form,
                    out_dir / "invoice_create_header.png",
                    max_height=560,
                )
            else:
                grab_widget_png(
                    window._invoice_screen,
                    out_dir / "invoice_create_header.png",
                    max_height=560,
                )
        except Exception as exc:  # noqa: BLE001 — surface grab failures to CI logs
            print(f"ERROR: {exc}", file=sys.stderr)
            app.exit(1)
            return
        success = True
        app.quit()

    QTimer.singleShot(700, take_screenshot)

    exit_code = app.exec()
    if not success and exit_code == 0:
        return 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
