"""
capture_ui_screenshot.py
========================
Headless screenshot helper for ProBooks+ai CI.

Usage (with a virtual display already active, e.g. via xvfb-run):
    python scripts/capture_ui_screenshot.py

Saves: artifacts/ui/main_window.png
Exit code 0 on success, non-zero on failure.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    # Must set the platform plugin before importing Qt widgets
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    # Import the application's main window
    # Adjust the import path so this script can be run from the repo root.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from desktop_app.main import MainWindow  # noqa: E402

    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    # Allow the event loop to process paint/layout events for 400 ms,
    # then grab the screenshot and quit.
    success = False

    def take_screenshot() -> None:
        nonlocal success

        output_path = Path("artifacts") / "ui" / "main_window.png"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        screen = app.primaryScreen()
        if screen is None:
            print("ERROR: No primary screen found.", file=sys.stderr)
            app.exit(1)
            return

        pixmap = screen.grabWindow(int(window.winId()))
        if pixmap.isNull():
            print("ERROR: grabWindow returned a null pixmap.", file=sys.stderr)
            app.exit(1)
            return

        saved = pixmap.save(str(output_path), "PNG")
        if not saved:
            print(f"ERROR: Failed to save screenshot to {output_path}", file=sys.stderr)
            app.exit(1)
            return

        print(f"Screenshot saved to {output_path} ({pixmap.width()}x{pixmap.height()} px)")
        success = True
        app.quit()

    QTimer.singleShot(400, take_screenshot)

    exit_code = app.exec()
    if not success and exit_code == 0:
        # quit() was not called by our timer (shouldn't happen), treat as failure
        return 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
