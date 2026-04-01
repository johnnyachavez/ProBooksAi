"""
desktop_app.theme
=================
Global dark-theme constants and helper for ProBooksAi.

Issue #29 – Dark theme across the entire app (global palette + tables).

Usage
-----
    from desktop_app.theme import apply_dark_theme
    apply_dark_theme(QApplication.instance())
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# ---------------------------------------------------------------------------
# Colour constants
# ---------------------------------------------------------------------------

BG_PRIMARY     = "#1A1A2E"   # main window / panel background
BG_SECONDARY   = "#16213E"   # alternate rows, groupbox backgrounds
BG_ELEVATED    = "#0F3460"   # headers, toolbars, selected items
FG_PRIMARY     = "#E0E0E0"   # default text
FG_SECONDARY   = "#A0A0B0"   # placeholder / secondary text
ACCENT         = "#533483"   # accent / highlight colour
ACCENT_HOVER   = "#6A45A0"
BORDER         = "#2A2A4A"   # subtle gridlines and borders
SELECTION_BG   = "#0F3460"
SELECTION_FG   = "#FFFFFF"
INPUT_BG       = "#1E1E3A"
DISABLED_FG    = "#555577"

# Amount colours
AMOUNT_POSITIVE = "#66BB6A"  # green
AMOUNT_NEGATIVE = "#EF5350"  # red

# Status colours
STATUS_COLORS = {
    "New":          "#42A5F5",   # blue
    "Extracted":    "#AB47BC",   # purple
    "Needs Review": "#FFA726",   # amber
    "Approved":     "#66BB6A",   # green
    "Posted":       "#78909C",   # blue-grey
    "Error":        "#EF5350",   # red
}

FONT_SIZE_NORMAL = "13px"
FONT_SIZE_SMALL  = "11px"
FONT_SIZE_LARGE  = "15px"


# ---------------------------------------------------------------------------
# Stylesheet
# ---------------------------------------------------------------------------

STYLESHEET = f"""
/* ── Global ─────────────────────────────────────────────────────── */
QWidget {{
    background-color: {BG_PRIMARY};
    color: {FG_PRIMARY};
    font-size: {FONT_SIZE_NORMAL};
}}

QMainWindow, QDialog {{
    background-color: {BG_PRIMARY};
}}

/* ── Frames / GroupBoxes ─────────────────────────────────────────── */
QFrame, QGroupBox {{
    background-color: {BG_SECONDARY};
    border: 1px solid {BORDER};
    border-radius: 4px;
}}

QGroupBox::title {{
    color: {FG_PRIMARY};
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 6px;
    font-weight: bold;
}}

/* ── Tabs ────────────────────────────────────────────────────────── */
QTabWidget::pane {{
    background-color: {BG_PRIMARY};
    border: 1px solid {BORDER};
}}

QTabBar::tab {{
    background-color: {BG_SECONDARY};
    color: {FG_SECONDARY};
    padding: 6px 14px;
    border: 1px solid {BORDER};
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    min-width: 80px;
}}

QTabBar::tab:selected {{
    background-color: {BG_ELEVATED};
    color: {FG_PRIMARY};
}}

QTabBar::tab:hover:!selected {{
    background-color: {ACCENT};
    color: {FG_PRIMARY};
}}

/* ── Tables ──────────────────────────────────────────────────────── */
QTableWidget, QTableView {{
    background-color: {BG_PRIMARY};
    alternate-background-color: {BG_SECONDARY};
    color: {FG_PRIMARY};
    gridline-color: {BORDER};
    selection-background-color: {SELECTION_BG};
    selection-color: {SELECTION_FG};
    border: 1px solid {BORDER};
}}

QHeaderView::section {{
    background-color: {BG_ELEVATED};
    color: {FG_PRIMARY};
    padding: 4px 6px;
    border: none;
    border-right: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
    font-weight: bold;
}}

/* ── Inputs ──────────────────────────────────────────────────────── */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit {{
    background-color: {INPUT_BG};
    color: {FG_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 3px 6px;
    selection-background-color: {ACCENT};
    selection-color: {SELECTION_FG};
}}

QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus {{
    border: 1px solid {ACCENT};
}}

QLineEdit:disabled, QPlainTextEdit:disabled {{
    color: {DISABLED_FG};
    background-color: {BG_SECONDARY};
}}

/* ── ComboBox ────────────────────────────────────────────────────── */
QComboBox {{
    background-color: {INPUT_BG};
    color: {FG_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 3px;
    padding: 3px 6px;
    min-width: 80px;
}}

QComboBox:focus {{
    border: 1px solid {ACCENT};
}}

QComboBox QAbstractItemView {{
    background-color: {BG_SECONDARY};
    color: {FG_PRIMARY};
    selection-background-color: {ACCENT};
    selection-color: {SELECTION_FG};
    border: 1px solid {BORDER};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

/* ── Buttons ─────────────────────────────────────────────────────── */
QPushButton {{
    background-color: {BG_ELEVATED};
    color: {FG_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 5px 14px;
    min-height: 24px;
}}

QPushButton:hover {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}

QPushButton:pressed {{
    background-color: {ACCENT_HOVER};
}}

QPushButton:disabled {{
    color: {DISABLED_FG};
    background-color: {BG_SECONDARY};
    border-color: {BORDER};
}}

/* ── Scroll bars ─────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: {BG_SECONDARY};
    width: 10px;
    border: none;
}}

QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 5px;
    min-height: 20px;
}}

QScrollBar::handle:vertical:hover {{
    background: {ACCENT};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background: {BG_SECONDARY};
    height: 10px;
    border: none;
}}

QScrollBar::handle:horizontal {{
    background: {BORDER};
    border-radius: 5px;
    min-width: 20px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {ACCENT};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* ── Splitter ────────────────────────────────────────────────────── */
QSplitter::handle {{
    background-color: {BORDER};
}}

QSplitter::handle:horizontal {{
    width: 2px;
}}

QSplitter::handle:vertical {{
    height: 2px;
}}

/* ── Status bar ──────────────────────────────────────────────────── */
QStatusBar {{
    background-color: {BG_SECONDARY};
    color: {FG_SECONDARY};
    border-top: 1px solid {BORDER};
}}

/* ── Toolbar ─────────────────────────────────────────────────────── */
QToolBar {{
    background-color: {BG_SECONDARY};
    border-bottom: 1px solid {BORDER};
    spacing: 4px;
    padding: 2px;
}}

QToolBar QToolButton {{
    background-color: transparent;
    color: {FG_PRIMARY};
    border: none;
    border-radius: 3px;
    padding: 4px 8px;
}}

QToolBar QToolButton:hover {{
    background-color: {ACCENT};
}}

/* ── Menus ───────────────────────────────────────────────────────── */
QMenuBar {{
    background-color: {BG_SECONDARY};
    color: {FG_PRIMARY};
    border-bottom: 1px solid {BORDER};
}}

QMenuBar::item:selected {{
    background-color: {ACCENT};
}}

QMenu {{
    background-color: {BG_SECONDARY};
    color: {FG_PRIMARY};
    border: 1px solid {BORDER};
}}

QMenu::item:selected {{
    background-color: {ACCENT};
    color: {FG_PRIMARY};
}}

/* ── Tooltips ────────────────────────────────────────────────────── */
QToolTip {{
    background-color: {BG_ELEVATED};
    color: {FG_PRIMARY};
    border: 1px solid {BORDER};
    padding: 3px 6px;
}}

/* ── Checkboxes / Radio buttons ──────────────────────────────────── */
QCheckBox, QRadioButton {{
    color: {FG_PRIMARY};
    spacing: 6px;
}}

QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    background-color: {INPUT_BG};
    border: 1px solid {BORDER};
    border-radius: 2px;
}}

QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}

/* ── Labels ──────────────────────────────────────────────────────── */
QLabel {{
    background-color: transparent;
    border: none;
    color: {FG_PRIMARY};
}}

/* ── Dialog button box ───────────────────────────────────────────── */
QDialogButtonBox QPushButton {{
    min-width: 80px;
}}
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_dark_theme(app: QApplication) -> None:
    """Apply the ProBooksAi dark theme to *app*."""
    app.setStyleSheet(STYLESHEET)

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window,          QColor(BG_PRIMARY))
    palette.setColor(QPalette.ColorRole.WindowText,      QColor(FG_PRIMARY))
    palette.setColor(QPalette.ColorRole.Base,            QColor(INPUT_BG))
    palette.setColor(QPalette.ColorRole.AlternateBase,   QColor(BG_SECONDARY))
    palette.setColor(QPalette.ColorRole.Text,            QColor(FG_PRIMARY))
    palette.setColor(QPalette.ColorRole.BrightText,      QColor(SELECTION_FG))
    palette.setColor(QPalette.ColorRole.Button,          QColor(BG_ELEVATED))
    palette.setColor(QPalette.ColorRole.ButtonText,      QColor(FG_PRIMARY))
    palette.setColor(QPalette.ColorRole.Highlight,       QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(SELECTION_FG))
    palette.setColor(QPalette.ColorRole.ToolTipBase,     QColor(BG_ELEVATED))
    palette.setColor(QPalette.ColorRole.ToolTipText,     QColor(FG_PRIMARY))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(FG_SECONDARY))
    app.setPalette(palette)
