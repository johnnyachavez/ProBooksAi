"""desktop_app/main.py entrypoint strings (no PySide6 import)."""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_MAIN = _REPO / "desktop_app" / "main.py"
_HELP_EPILOG = _REPO / "probooks" / "help_epilog.py"


def test_desktop_main_cli_and_qt_app_strings_use_probooks_plus_ai() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    mod_doc_end = text.index('"""', 3)
    mod_doc = text[: mod_doc_end + 3]
    assert "help_epilog" in mod_doc
    hel = _HELP_EPILOG.read_text(encoding="utf-8")
    assert 'description="ProBooks+ai desktop application"' in text
    assert "epilog=" in text
    assert "EXCEL_COA_WORKBOOK_ARGPARSE_EPILOG" in text
    assert "generate_workbook.py" in hel
    assert "Excel COA workbook" in hel
    assert "Default database paths" in text
    assert "probooksai.database.get_data_dir" in text
    assert "default_intake_db_path().name" in text, (
        "desktop --database help should derive the default filename from probooks.paths"
    )
    assert 'app.setApplicationName("ProBooks+ai")' in text
    assert 'app.setOrganizationName("ProBooks+ai")' in text


def test_register_tab_persists_header_state_via_qsettings() -> None:
    """Register saves/restores horizontal header state like other desktop grids."""
    text = (_MAIN.parent / "register_tab.py").read_text(encoding="utf-8")
    assert "saveState()" in text and "restoreState" in text
    assert "register/table_header_state_" in text


def test_register_tab_cleared_actions_document_shortcuts_in_tooltips() -> None:
    """Toolbar tooltips surface the same Ctrl+Shift shortcuts as QShortcut."""
    text = (_MAIN.parent / "register_tab.py").read_text(encoding="utf-8")
    assert "setToolTip" in text
    assert "Ctrl+Shift+C" in text and "Ctrl+Shift+U" in text


def test_register_table_stylesheet_defines_cell_grid() -> None:
    """Bank register uses per-item borders; native QTable grid is often invisible under QSS."""
    from desktop_app.theme import register_table_style_sheet

    qss = register_table_style_sheet()
    assert "bankRegisterTable" in qss
    assert "QTableWidget#bankRegisterTable::item" in qss
    assert "border-right" in qss and "border-bottom" in qss


def test_theme_normalizes_default_font_before_stylesheet() -> None:
    """Avoid QFont::setPointSize -1 when QSS merges fonts (theme uses pixel size = FONT_SIZE_NORMAL)."""
    theme = (_MAIN.parent / "theme.py").read_text(encoding="utf-8")
    assert "def _ensure_application_font_has_explicit_size" in theme
    assert theme.find("_ensure_application_font_has_explicit_size") < theme.find(
        "app.setStyleSheet(STYLESHEET)", theme.find("def apply_dark_theme")
    )


def test_main_installs_qt_message_filter_before_qapplication() -> None:
    """Spurious QFont::setPointSize can fire before theme runs; filter is installed first in main()."""
    text = _MAIN.read_text(encoding="utf-8")
    main_idx = text.index("def main():")
    spam_idx = text.index("_suppress_qt_font_pointsize_stderr_spam()", main_idx)
    app_idx = text.index("app = QApplication(sys.argv)", main_idx)
    assert spam_idx < app_idx
    assert "qInstallMessageHandler" in text
    assert "Point size <= 0" in text and "must be greater than 0" in text
