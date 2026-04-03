"""desktop_app/main.py entrypoint strings (no PySide6 import)."""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_MAIN = _REPO / "desktop_app" / "main.py"
_HELP_EPILOG = _REPO / "probooks" / "help_epilog.py"


def test_main_help_menu_wires_register_keyboard_shortcuts_dialog() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    assert "show_register_keyboard_shortcuts_dialog" in text
    assert "Bank &register keyboard shortcuts" in text


def test_main_help_menu_wires_bank_import_shortcuts_dialog() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    assert "show_bank_import_keyboard_shortcuts_dialog" in text
    assert "Bank &import shortcuts" in text


def test_bank_import_tab_exposes_shortcuts_dialog_for_help_menu() -> None:
    bit = (_MAIN.parent / "bank_import_tab.py").read_text(encoding="utf-8")
    assert "def show_bank_import_keyboard_shortcuts_dialog" in bit
    assert "def _bank_import_keyboard_shortcuts_help_text" in bit


def test_register_tab_exposes_shared_shortcuts_dialog_for_help_menu() -> None:
    rtab = (_MAIN.parent / "register_tab.py").read_text(encoding="utf-8")
    assert "def show_register_keyboard_shortcuts_dialog" in rtab


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


def test_bank_import_tab_f5_reload_shortcut_wired() -> None:
    path = _MAIN.parent / "bank_import_tab.py"
    text = path.read_text(encoding="utf-8")
    assert "def _reload_bank_import_view" in text
    assert 'QKeySequence("F5")' in text
    assert "activated.connect(self._reload_bank_import_view)" in text
    assert "F5 refreshes accounts and import batches" in text
    assert "Bank import shortcuts" in text
    assert "Keyboard shortcuts…" in text
    assert "_show_bank_import_keyboard_shortcuts_help" in text


def test_register_tab_persists_header_state_via_qsettings() -> None:
    """Register saves/restores horizontal header state like other desktop grids."""
    text = (_MAIN.parent / "register_tab.py").read_text(encoding="utf-8")
    assert "saveState()" in text and "restoreState" in text
    assert "register/table_header_state_" in text


def test_register_tab_cleared_actions_document_shortcuts_in_tooltips() -> None:
    """Register shortcuts (F5, Ctrl+Shift+*) match tooltips and QShortcut wiring."""
    text = (_MAIN.parent / "register_tab.py").read_text(encoding="utf-8")
    assert "setToolTip" in text
    assert "Ctrl+Shift+C" in text and "Ctrl+Shift+U" in text
    assert "Ctrl+Shift+E" in text and "Ctrl+Shift+G" in text
    assert 'QKeySequence("F5")' in text
    assert "activated.connect(self._export_csv)" in text
    assert "activated.connect(self._reload_current)" in text
    assert "activated.connect(self._post_selected)" in text


def test_register_keyboard_shortcuts_help_text_matches_wired_chords() -> None:
    """Single helper lists the same chords as QShortcut (avoid help drifting from behavior)."""
    text = (_MAIN.parent / "register_tab.py").read_text(encoding="utf-8")
    start = text.index("def _register_keyboard_shortcuts_help_text")
    end = text.index("\n\nclass RegisterTab", start)
    chunk = text[start:end]
    for needle in (
        "F5 — Refresh",
        "Ctrl+Shift+G",
        "Ctrl+Shift+E",
        "Ctrl+Shift+C",
        "Ctrl+Shift+U",
        "Bank import shortcuts",
    ):
        assert needle in chunk, f"register shortcuts help should mention {needle!r}"


def test_register_context_menu_includes_keyboard_shortcuts_action() -> None:
    text = (_MAIN.parent / "register_tab.py").read_text(encoding="utf-8")
    assert "Keyboard shortcuts…" in text
    assert "_show_register_keyboard_shortcuts_help" in text


def test_register_tab_clr_header_tooltip_documents_batch_reconciled() -> None:
    """Clr column header explains C vs R and points users at Bank Import for batch R."""
    text = (_MAIN.parent / "register_tab.py").read_text(encoding="utf-8")
    assert "horizontalHeaderItem(_COL_CLR)" in text
    assert "Bank Import" in text


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
