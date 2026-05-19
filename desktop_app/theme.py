"""
desktop_app.theme
=================
Global dark-theme constants and helper for ProBooks+ai.

Issue #29 – Dark theme across the entire app (global palette + tables).

Usage
-----
    from desktop_app.theme import apply_dark_theme
    apply_dark_theme(QApplication.instance())
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

# ---------------------------------------------------------------------------
# Colour constants
# ---------------------------------------------------------------------------

BG_PRIMARY     = "#1A1A2E"   # main window / panel background
BG_SECONDARY   = "#16213E"   # alternate rows, groupbox backgrounds
BG_ELEVATED    = "#0F3460"   # headers, toolbars, selected items
# Top-level Customers / Vendors: one step darker than BG_PRIMARY / BG_SECONDARY (richer navy body).
AR_AP_MASTER_BG_PRIMARY = "#13162A"
AR_AP_MASTER_BG_SECONDARY = "#0E182E"
AR_AP_MASTER_TABLE_ALT = "#0B1528"
FG_PRIMARY     = "#E0E0E0"   # default text
FG_SECONDARY   = "#A0A0B0"   # placeholder / secondary text
ACCENT         = "#533483"   # accent / highlight colour
ACCENT_HOVER   = "#6A45A0"
BORDER         = "#2A2A4A"   # subtle gridlines and borders
# Bank register: global QTableWidget styles often hide the native grid; draw per-cell borders instead.
REGISTER_GRID_LINE = "#6B8299"  # visible column/row rules (classic register; works on band fills)
REGISTER_ALT_STRIPE = "#15282A"   # subtle green-grey zebra (dark theme; evokes classic register tint)
# Two-band row panels (checkbook-style upper lighter / lower darker); painted by RegisterBandDelegate.
REGISTER_BAND_UPPER_EVEN = "#252542"
REGISTER_BAND_LOWER_EVEN = "#151528"
REGISTER_BAND_UPPER_ODD = "#1E3438"
REGISTER_BAND_LOWER_ODD = "#131E22"
REGISTER_BAND_UPPER_MISSING = "#4A4024"
REGISTER_BAND_LOWER_MISSING = "#342C18"
REGISTER_BAND_DIVIDER = "#5A6E90"
# Minimum row heights (px); keep in sync with :class:`desktop_app.register_band_delegate.RegisterBandDelegate`.
REGISTER_ROW_HEIGHT_MIN_FULL = 46
REGISTER_ROW_HEIGHT_MIN_PREVIEW = 38
SELECTION_BG   = "#0F3460"
SELECTION_FG   = "#FFFFFF"
INPUT_BG       = "#1E1E3A"
DISABLED_FG    = "#555577"

# Top-level workflow tabs (Invoices, Enter Bills, Pay Bills, Receive Payments): same navy stack as
# Customers / Vendors AR/AP master body — dark panels, light text, visible gridlines on dark fills.
WORKFLOW_PAGE_BG = AR_AP_MASTER_BG_PRIMARY
WORKFLOW_PANEL_BG = AR_AP_MASTER_BG_SECONDARY
WORKFLOW_ALT_ROW = AR_AP_MASTER_TABLE_ALT
WORKFLOW_GRID = "#4A5F80"
WORKFLOW_HEADER_BG = BG_ELEVATED
WORKFLOW_TEXT = "#ECEFF4"
WORKFLOW_CAPTION = "#A8B4C9"
WORKFLOW_INPUT_BG = INPUT_BG
WORKFLOW_CONTROL_FACE = "#1A2840"
WORKFLOW_CONTROL_HOVER = "#243552"
WORKFLOW_CONTROL_PRESSED = "#2D4568"
WORKFLOW_STRIP_BTN_OUTLINE = "#5A6E90"

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

# Main window ``QTabWidget`` tab bar (``MainWindow._build_ui``); compact strip scoped by objectName.
MAIN_WORKSPACE_TAB_BAR_OBJECT_NAME = "mainWorkspaceTabBar"
MAIN_WORKSPACE_TAB_MIN_HEIGHT_PX = 32
MAIN_WORKSPACE_TAB_PADDING = "4px 10px"
MAIN_WORKSPACE_TAB_FONT_SIZE = "11px"
MAIN_WORKSPACE_TAB_FONT_WEIGHT = "500"
MAIN_WORKSPACE_TAB_BAR_WIDGET_MIN_HEIGHT_PX = 32


def register_row_band_colors_hex(alternate_row: bool, missing_coa: bool) -> tuple[str, str]:
    """Return ``(upper_hex, lower_hex)`` for register row panels (even/odd zebra; missing-COA tint)."""
    if missing_coa:
        return REGISTER_BAND_UPPER_MISSING, REGISTER_BAND_LOWER_MISSING
    if alternate_row:
        return REGISTER_BAND_UPPER_ODD, REGISTER_BAND_LOWER_ODD
    return REGISTER_BAND_UPPER_EVEN, REGISTER_BAND_LOWER_EVEN


def register_table_style_sheet() -> str:
    """Styles for register-style tables (object name ``bankRegisterTable``): Register tab and Bank Import preview.

    Row bands and cell border lines are painted by
    :class:`desktop_app.register_band_delegate.RegisterBandDelegate` (using ``REGISTER_GRID_LINE``).
    ``::item`` uses ``border: none`` so those lines are not doubled.
    """
    return f"""
QTableWidget#bankRegisterTable {{
    background-color: {BG_PRIMARY};
    alternate-background-color: {BG_PRIMARY};
    gridline-color: {REGISTER_GRID_LINE};
    outline: none;
}}
QTableWidget#bankRegisterTable::item {{
    background: transparent;
    border: none;
    padding: 3px 6px;
}}
QTableWidget#bankRegisterTable::item:selected {{
    background-color: {SELECTION_BG};
    color: {SELECTION_FG};
}}
"""


def ar_ap_master_tab_stylesheet() -> str:
    """Return QSS for top-level **Customers** / **Vendors** tabs (darker panels; same blue table headers)."""
    return f"""
QWidget#arMasterTab, QWidget#apMasterTab {{
    background-color: {AR_AP_MASTER_BG_PRIMARY};
}}
QWidget#arMasterTab QGroupBox, QWidget#apMasterTab QGroupBox {{
    background-color: {AR_AP_MASTER_BG_SECONDARY};
    border: 1px solid {BORDER};
    border-radius: 4px;
}}
QWidget#arMasterTab QTableWidget, QWidget#apMasterTab QTableWidget {{
    background-color: {AR_AP_MASTER_BG_PRIMARY};
    alternate-background-color: {AR_AP_MASTER_TABLE_ALT};
    color: {FG_PRIMARY};
    gridline-color: {BORDER};
    border: 1px solid {BORDER};
}}
QWidget#arMasterTab QTableWidget::item:selected,
QWidget#apMasterTab QTableWidget::item:selected {{
    background-color: {SELECTION_BG};
    color: {SELECTION_FG};
}}
QWidget#arMasterTab QHeaderView::section,
QWidget#apMasterTab QHeaderView::section {{
    background-color: {BG_ELEVATED};
    color: {FG_PRIMARY};
    padding: 4px 6px;
    border: none;
    border-right: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
    font-weight: bold;
}}
QWidget#arMasterTab QSplitter::handle,
QWidget#apMasterTab QSplitter::handle {{
    background-color: {BORDER};
}}
"""


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
QFrame {{
    background-color: {BG_SECONDARY};
    border: 1px solid {BORDER};
    border-radius: 4px;
}}

QGroupBox {{
    background-color: {BG_SECONDARY};
    border: 1px solid {BORDER};
    border-radius: 4px;
    margin-top: 20px;   /* reserve space above content for the title label */
    padding-top: 4px;
}}

QGroupBox::title {{
    color: {FG_PRIMARY};
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 8px;
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

/* Main workspace tab strip only (objectName set on ``MainWindow`` tab bar). */
QTabBar#{MAIN_WORKSPACE_TAB_BAR_OBJECT_NAME}::tab {{
    min-height: {MAIN_WORKSPACE_TAB_MIN_HEIGHT_PX}px;
    padding: {MAIN_WORKSPACE_TAB_PADDING};
    font-size: {MAIN_WORKSPACE_TAB_FONT_SIZE};
    font-weight: {MAIN_WORKSPACE_TAB_FONT_WEIGHT};
    qproperty-alignment: AlignCenter;
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


def _ensure_application_font_has_explicit_size(app: QApplication) -> None:
    """Give *app* a plain QFont with an explicit pixel size before setStyleSheet.

    Global QSS uses ``font-size: {FONT_SIZE_NORMAL}`` (pixels). If the default
    application font is point-sized, Qt's merge path can end up calling
    ``setPointSize(-1)`` on Windows. Match the stylesheet with a fresh
    **pixel-sized** font (same numeric size as ``FONT_SIZE_NORMAL``).
    """
    raw = FONT_SIZE_NORMAL.strip().lower().removesuffix("px").strip()
    try:
        pixel = max(int(raw), 1)
    except ValueError:
        pixel = 13
    src = app.font()
    family = src.family() or "Segoe UI"
    fixed = QFont()
    fixed.setFamily(family)
    fixed.setPixelSize(pixel)
    app.setFont(fixed)


def apply_dark_theme(app: QApplication) -> None:
    """Apply the ProBooks+ai dark theme to *app*."""
    # Fusion + explicit app font before/after QSS: Windows native style can merge
    # fonts in a way that triggers setPointSize(-1) when a global stylesheet sets px sizes.
    app.setStyle("Fusion")
    _ensure_application_font_has_explicit_size(app)
    app.setStyleSheet(STYLESHEET)
    _ensure_application_font_has_explicit_size(app)

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
