"""Home landing tab: first main-window tab (index 0)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QResizeEvent, QShowEvent
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

# Default: repo-root assets/home_bg.png or home_bg.jpg (PNG preferred). Replace with your own image.
_HOME_BG_CANDIDATES = ("home_bg.png", "home_bg.jpg")


def _resolve_home_background_path() -> Path | None:
    root = Path(__file__).resolve().parents[1]
    for name in _HOME_BG_CANDIDATES:
        p = root / "assets" / name
        if p.is_file():
            return p
    return None


class HomeTab(QWidget):
    """Full-bleed background image with welcome overlay (scales on resize, no tiling)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setToolTip(
            "Home: landing page with company background image. "
            "Same company .db as other tabs (File → Backup / Restore, probooks.backup)."
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._bg = QLabel(self)
        self._bg.setScaledContents(False)
        self._bg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bg.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        path = _resolve_home_background_path()
        self._pixmap_src = QPixmap(str(path)) if path is not None else QPixmap()
        if self._pixmap_src.isNull():
            self._bg.setStyleSheet("background-color: #1e2229;")

        self._welcome = QLabel("Welcome to ProBooks+ai", self)
        self._welcome.setWordWrap(True)
        self._welcome.setStyleSheet(
            "color: #ffffff; font-size: 20px; font-weight: 600; "
            "padding: 14px 18px; background-color: rgba(0, 0, 0, 0.58); "
            "border-radius: 8px;"
        )
        self._welcome.adjustSize()
        self._welcome.raise_()

    def _sync_background_and_overlay(self) -> None:
        w, h = self.width(), self.height()
        self._bg.setGeometry(0, 0, w, h)
        if w > 0 and h > 0 and not self._pixmap_src.isNull():
            scaled = self._pixmap_src.scaled(
                w,
                h,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._bg.setPixmap(scaled)
        self._welcome.adjustSize()
        m = 20
        # Bottom-left: reads well on dark asphalt when the upper frame is bright (boat/sky).
        y = max(m, h - self._welcome.height() - m) if h > 0 else m
        self._welcome.move(m, y)
        self._welcome.raise_()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._sync_background_and_overlay()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._sync_background_and_overlay()
