"""
ProBooksAi Desktop Application
===============================
A native desktop GUI (PySide6/Qt) for generating the ProBooksAi
accounting workbook.

Run:
    python -m desktop_app.main
"""

import os
import sys
import traceback

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from probooksai.generator import OUTPUT_FILE, build_workbook


# ---------------------------------------------------------------------------
# Background worker thread
# ---------------------------------------------------------------------------

class WorkbookWorker(QThread):
    """Run ``build_workbook`` in a background thread to keep the UI responsive."""

    success = Signal(str)    # emits the saved file path
    failure = Signal(str)    # emits the error message

    def __init__(self, output_path: str) -> None:
        super().__init__()
        self._output_path = output_path

    def run(self) -> None:
        try:
            saved_path = build_workbook(self._output_path)
            self.success.emit(saved_path)
        except Exception:  # noqa: BLE001
            self.failure.emit(traceback.format_exc())


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ProBooksAi – Accounting Workbook Generator")
        self.setMinimumWidth(620)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # --- Title label ---
        title_label = QLabel("ProBooksAi")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        subtitle_label = QLabel("Accounting Workbook Generator")
        sub_font = QFont()
        sub_font.setPointSize(11)
        subtitle_label.setFont(sub_font)
        layout.addWidget(subtitle_label)

        # --- Output path row ---
        path_layout = QHBoxLayout()
        path_label = QLabel("Output file:")
        path_label.setFixedWidth(80)
        path_layout.addWidget(path_label)

        self._path_edit = QLineEdit(os.path.abspath(OUTPUT_FILE))
        path_layout.addWidget(self._path_edit)

        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._browse)
        path_layout.addWidget(browse_btn)
        layout.addLayout(path_layout)

        # --- Generate button ---
        self._generate_btn = QPushButton("Generate Workbook")
        self._generate_btn.setFixedHeight(40)
        btn_font = QFont()
        btn_font.setPointSize(12)
        btn_font.setBold(True)
        self._generate_btn.setFont(btn_font)
        self._generate_btn.clicked.connect(self._generate)
        layout.addWidget(self._generate_btn)

        # --- Log area ---
        log_label = QLabel("Log output:")
        layout.addWidget(log_label)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(180)
        log_font = QFont("Courier New", 10)
        self._log.setFont(log_font)
        layout.addWidget(self._log)

        # --- Status bar ---
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready.")

        self._worker: WorkbookWorker | None = None

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _browse(self) -> None:
        current = self._path_edit.text() or OUTPUT_FILE
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Workbook As…",
            current,
            "Excel Workbook (*.xlsx)",
        )
        if path:
            self._path_edit.setText(path)

    def _generate(self) -> None:
        output_path = self._path_edit.text().strip()
        if not output_path:
            self._log.appendPlainText("⚠  Please specify an output file path.")
            return

        self._generate_btn.setEnabled(False)
        self._log.clear()
        self._log.appendPlainText(f"Generating workbook → {output_path}")
        self._status_bar.showMessage("Generating…")

        self._worker = WorkbookWorker(output_path)
        self._worker.success.connect(self._on_success)
        self._worker.failure.connect(self._on_failure)
        self._worker.start()

    def _on_success(self, saved_path: str) -> None:
        self._log.appendPlainText(f"✅  Workbook saved: {saved_path}")
        self._status_bar.showMessage(f"Done – {saved_path}")
        self._generate_btn.setEnabled(True)
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None

    def _on_failure(self, error: str) -> None:
        self._log.appendPlainText("❌  Error generating workbook:")
        self._log.appendPlainText(error)
        self._status_bar.showMessage("Failed – see log for details.")
        self._generate_btn.setEnabled(True)
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("ProBooksAi")
    app.setOrganizationName("ProBooksAi")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
