"""Contract tests for the PySide6 ``desktop_app`` package via source scans (no Qt import).

Asserts main-window wiring, tab and dialog hover ``setToolTip`` / menu patterns, ``qt_mnemonic``
helpers, and guardrails against static ``QMessageBox`` dialogs and ad-hoc ``.button(Q*StandardButton`` lookups.
"""

from __future__ import annotations

import re
from pathlib import Path

from desktop_app.table_clipboard import CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX

from tests.repo_paths import (
    DESKTOP_APP_DIR as _DESKTOP_APP_DIR,
    PROBOOKS_HELP_EPILOG,
    REPO_ROOT,
)

_MAIN = _DESKTOP_APP_DIR / "main.py"


def test_desktop_main_imports_partial_for_inbox_context_menu() -> None:
    """``main`` binds **Copy row** with ``functools.partial`` (see ``InboxWidget._on_context_menu``)."""
    text = _MAIN.read_text(encoding="utf-8")
    assert "from functools import partial" in text


def test_desktop_main_imports_backup_data_layers_and_tab_widgets() -> None:
    """``main`` pulls in ``probooks.backup``, SQLite data layers, and tab classes wired by ``MainWindow``."""
    text = _MAIN.read_text(encoding="utf-8")
    head = text.split("def _document_intake_keyboard_shortcuts_help_text", 1)[0]
    assert "from probooks.backup import backup_database, restore_database" in head
    assert (
        "from probooks.help_epilog import EXCEL_COA_WORKBOOK_ARGPARSE_EPILOG" in head
    )
    assert "from probooks.paths import default_intake_db_path" in head
    assert "from probooksai.database import DocumentDatabase" in head
    assert "from probooksai.html_escape import escape_html_text" in head
    assert "from probooksai.coa import coa_display_list, load_coa" in head
    assert "from probooksai.bank_import import BankDatabase" in head
    assert "from probooksai.coa_db import COADatabase" in head
    assert "from probooksai.gl import GLDatabase" in head
    assert "from probooksai.extensions_schema import apply_extensions" in head
    assert "from desktop_app.bank_import_tab import" in head and "BankImportTab" in head
    assert "from desktop_app.coa_tab import COATab" in head
    assert (
        "from desktop_app.register_tab import RegisterTab, show_register_keyboard_shortcuts_dialog"
        in head
    )
    assert "from desktop_app.reports_tab import ReportsTab" in head
    assert "from desktop_app.journal_tab import JournalTab" in head
    assert (
        "from desktop_app.extra_tabs import BusinessHub, show_business_keyboard_shortcuts_dialog"
        in head
    )
    assert "from desktop_app.audit_tab import AuditTab" in head
    assert (
        "from desktop_app.theme import apply_dark_theme, STATUS_COLORS as THEME_STATUS_COLORS"
        in head
    )
    assert "from desktop_app.local_docs import resolve_local_roadmap_path" in head
    assert "from desktop_app.version import application_version" in head
    assert "from desktop_app.more_main_tabs_shortcuts import" in head
    assert "show_more_main_tabs_keyboard_shortcuts_dialog" in head
    assert "from desktop_app.qt_mnemonic import" in head
    assert "escape_ampersand_for_qt" in head
    assert "message_box_about_ok" in head
    assert "message_box_critical_ok" in head
    assert "message_box_information_ok" in head
    assert "message_box_warning_ok" in head
    assert "tip_message_box_buttons" in head
    assert "from desktop_app.qt_combo_ids import coerce_combo_int_id" in head
    assert "from desktop_app.table_clipboard import" in head
    assert "CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX" in head
    assert "VIEW_BANK_REGISTER_KEYS_TOOLTIP" in head
    assert "IntSortTableItem" in head
    assert "copy_table_row_as_tsv" in head
    assert "plain_display_table_item" in head
    assert "table_cell_clipboard_text" in head
    assert "show_bank_import_keyboard_shortcuts_dialog" in head


def test_desktop_main_imports_pyside6_core_widgets() -> None:
    """``main`` imports the Qt types used by ``MainWindow``, workers, and dialogs."""
    text = _MAIN.read_text(encoding="utf-8")
    head = text.split("def _document_intake_keyboard_shortcuts_help_text", 1)[0]
    assert "QThread" in head
    assert "Signal" in head
    assert "QTimer" in head
    assert "QMimeData" in head
    assert "qInstallMessageHandler" in head
    assert "QMainWindow" in head
    assert "QApplication" in head
    assert "QSettings" in head and "QUrl" in head
    assert "QDragEnterEvent" in head and "QDropEvent" in head
    assert "QKeySequence" in head and "QShortcut" in head
    assert "QDesktopServices" in head
    assert "QAction" in head
    assert "QColor" in head and "QPixmap" in head
    assert "QFileDialog" in head and "QMessageBox" in head
    assert "QTableWidget" in head and "QTabWidget" in head
    assert "QSplitter" in head and "QScrollArea" in head
    assert "QMenu" in head and "QStatusBar" in head
    assert "QWidget" in head
    assert "QFrame" in head and "QLabel" in head
    assert "QVBoxLayout" in head and "QHBoxLayout" in head
    assert "QFormLayout" in head
    assert "QComboBox" in head and "QLineEdit" in head
    assert "QDoubleSpinBox" in head and "QPlainTextEdit" in head
    assert "QPushButton" in head and "QGroupBox" in head


def test_desktop_main_imports_pyside6_core_gui_widgets_source_order() -> None:
    """``main`` groups PySide6 imports **QtCore → QtGui → QtWidgets** in that order."""
    text = _MAIN.read_text(encoding="utf-8")
    head = text.split("def _document_intake_keyboard_shortcuts_help_text", 1)[0]
    c = head.index("from PySide6.QtCore import (")
    g = head.index("from PySide6.QtGui import (")
    w = head.index("from PySide6.QtWidgets import (")
    assert c < g < w


def test_desktop_main_imports_probooks_probooksai_desktop_app_source_order() -> None:
    """Third-party import block runs **probooks** → **probooksai** → **desktop_app** (first line of each)."""
    text = _MAIN.read_text(encoding="utf-8")
    head = text.split("def _document_intake_keyboard_shortcuts_help_text", 1)[0]
    pb = head.index("from probooks.backup import backup_database, restore_database")
    pai = head.index("from probooksai.database import DocumentDatabase")
    da = head.index("from desktop_app.bank_import_tab import (")
    assert pb < pai < da


def test_desktop_main_imports_stdlib_os_path_sqlite_mimetypes_argparse() -> None:
    """``main`` uses stdlib for CLI, MIME guessing, env vars, and SQLite error typing."""
    text = _MAIN.read_text(encoding="utf-8")
    head = text.split("def _document_intake_keyboard_shortcuts_help_text", 1)[0]
    assert "import argparse" in head
    assert "import mimetypes" in head
    assert "import os" in head
    assert "import sqlite3" in head
    assert "import sys" in head
    assert "from pathlib import Path" in head


def test_desktop_main_future_annotations_before_stdlib_imports() -> None:
    """``main`` opts into postponed evaluation of annotations (PEP 563) before other imports."""
    text = _MAIN.read_text(encoding="utf-8")
    fx = text.index("from __future__ import annotations")
    ap = text.index("import argparse")
    assert fx < ap


def _iter_desktop_app_py_files() -> list[Path]:
    return sorted(_DESKTOP_APP_DIR.rglob("*.py"))


def test_clipboard_db_backup_tooltip_suffix_wording() -> None:
    assert CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX == (
        "Company .db safety: File → Backup / Restore (probooks.backup)."
    )


def test_desktop_backup_tip_literal_only_defined_in_table_clipboard() -> None:
    """Copy-to-clipboard QActions should reference ``CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX`` (single source)."""
    literal = CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX
    for path in _iter_desktop_app_py_files():
        text = path.read_text(encoding="utf-8")
        if path.name == "table_clipboard.py":
            assert text.count(literal) == 1
        else:
            assert literal not in text, f"{path.name} should not embed the backup tip literal; import the constant"


def test_act_keys_settooltip_includes_clipboard_backup_suffix() -> None:
    """Each ``act_keys.setToolTip(...)`` should append ``CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX``."""
    marker = "act_keys.setToolTip("
    suffix_op = "+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX"
    for path in _iter_desktop_app_py_files():
        text = path.read_text(encoding="utf-8")
        tails = text.split(marker)[1:]
        if not tails:
            continue
        for i, tail in enumerate(tails, start=1):
            window = tail[:1200]
            assert suffix_op in window, (
                f"{path.name}: act_keys.setToolTip block #{i} should use {suffix_op!r} "
                f"near the start of the call (within {len(window)} chars)"
            )


def test_act_copy_settooltip_includes_clipboard_backup_suffix() -> None:
    """Each ``act_copy.setToolTip(...)`` should append ``CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX``."""
    marker = "act_copy.setToolTip("
    suffix_op = "+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX"
    for path in _iter_desktop_app_py_files():
        text = path.read_text(encoding="utf-8")
        tails = text.split(marker)[1:]
        if not tails:
            continue
        for i, tail in enumerate(tails, start=1):
            window = tail[:1200]
            assert suffix_op in window, (
                f"{path.name}: act_copy.setToolTip block #{i} should use {suffix_op!r} "
                f"near the start of the call (within {len(window)} chars)"
            )


_RE_ACT_COPY_ASSIGN = re.compile(
    r"^\s*act_copy\s*=\s*(?:m|menu)\.addAction\(", re.MULTILINE
)
_RE_ACT_KEYS_ASSIGN = re.compile(
    r"^\s*act_keys\s*=\s*(?:m|menu)\.addAction\(", re.MULTILINE
)
_RE_ACT_INVNO_ASSIGN = re.compile(
    r"^\s*act_invno\s*=\s*m\.addAction\(", re.MULTILINE
)


def test_act_keys_act_copy_act_invno_assignments_match_settooltip_counts() -> None:
    """Each **Keyboard shortcuts…** / copy QAction gets a ``setToolTip`` (and vice versa)."""
    n_keys_a = n_keys_t = 0
    n_copy_a = n_copy_t = 0
    n_inv_a = n_inv_t = 0
    for path in _iter_desktop_app_py_files():
        text = path.read_text(encoding="utf-8")
        n_keys_a += len(_RE_ACT_KEYS_ASSIGN.findall(text))
        n_keys_t += text.count("act_keys.setToolTip(")
        n_copy_a += len(_RE_ACT_COPY_ASSIGN.findall(text))
        n_copy_t += text.count("act_copy.setToolTip(")
        n_inv_a += len(_RE_ACT_INVNO_ASSIGN.findall(text))
        n_inv_t += text.count("act_invno.setToolTip(")
    assert n_keys_a == n_keys_t, (
        f"act_keys addAction lines ({n_keys_a}) must match act_keys.setToolTip calls ({n_keys_t})"
    )
    assert n_copy_a == n_copy_t, (
        f"act_copy addAction lines ({n_copy_a}) must match act_copy.setToolTip calls ({n_copy_t})"
    )
    assert n_inv_a == n_inv_t, (
        f"act_invno addAction lines ({n_inv_a}) must match act_invno.setToolTip calls ({n_inv_t})"
    )


def test_act_invno_settooltip_includes_clipboard_backup_suffix() -> None:
    """AR invoice grid **Copy invoice #** uses ``act_invno`` (not ``act_copy``)."""
    marker = "act_invno.setToolTip("
    suffix_op = "+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX"
    for path in _iter_desktop_app_py_files():
        text = path.read_text(encoding="utf-8")
        tails = text.split(marker)[1:]
        if not tails:
            continue
        for i, tail in enumerate(tails, start=1):
            window = tail[:1200]
            assert suffix_op in window, (
                f"{path.name}: act_invno.setToolTip block #{i} should use {suffix_op!r} "
                f"near the start of the call (within {len(window)} chars)"
            )


def test_main_menu_action_tip_mentioning_clipboard_includes_backup_suffix() -> None:
    """File menu **Copy company database path** uses ``_menu_action_tip``, not ``act_copy.setToolTip``.

    Match **to the clipboard** (user-facing copy wording), not bare ``clipboard`` — later code in
    ``main.py`` can reference ``QApplication.clipboard()`` within a long scan window.
    """
    text = _MAIN.read_text(encoding="utf-8")
    marker = "_menu_action_tip("
    suffix_op = "+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX"
    copy_phrase = "to the clipboard"
    for i, tail in enumerate(text.split(marker)[1:], start=1):
        window = tail[:2500]
        if copy_phrase not in window.lower():
            continue
        assert suffix_op in window, (
            f"main.py: _menu_action_tip block #{i} mentions {copy_phrase!r} but should append {suffix_op!r} "
            f"in the tip string (within {len(window)} chars)"
        )


_FILE_MENU_QACTION_NAMES: tuple[str, ...] = (
    "act_import_docs",
    "act_open_company",
    "act_new_company",
    "act_backup",
    "act_restore",
    "act_copy_db_path",
    "act_save",
    "act_save_as",
    "act_exit",
)

# Edit → Tools (Invoice) → Recon (12 register QActions) → Help; all use ``_menu_action_tip`` only
# (chunk is ``# Edit menu`` through ``# -- drag & drop`` in ``_build_menu_bar``).
_EDIT_TOOLS_RECON_HELP_QACTION_NAMES: tuple[str, ...] = (
    "act_undo",
    "act_redo",
    "act_prefs",
    "act_tools_invoice",
    "act_reg_add",
    "act_reg_post",
    "act_reg_export",
    "act_reg_mark_clr",
    "act_reg_clear_clr",
    "act_reg_attach",
    "act_reg_clear_att",
    "act_reg_splits",
    "act_reg_transfer",
    "act_reg_link",
    "act_reg_flag_rcpt",
    "act_reg_clear_rcpt",
    "act_roadmap",
    "act_intake_keys",
    "act_bank_import_keys",
    "act_register_keys",
    "act_business_keys",
    "act_more_tab_keys",
    "act_about",
)


def test_file_menu_qactions_use_menu_action_tip_only() -> None:
    """**File** menu actions set hover + status text only via ``_menu_action_tip``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("# File menu")
    end = text.index("# View menu", start)
    chunk = text[start:end]
    for name in _FILE_MENU_QACTION_NAMES:
        assert chunk.count(f"{name} = QAction(") == 1, name
        tip_hdr = f"_menu_action_tip(\n            {name},"
        assert chunk.count(tip_hdr) == 1, f"{name} should use _menu_action_tip once"
        assert f"{name}.setToolTip(" not in chunk, (
            f"{name} should not call setToolTip directly; use _menu_action_tip"
        )
        assert f"{name}.setStatusTip(" not in chunk, (
            f"{name} should not call setStatusTip directly; use _menu_action_tip"
        )


def test_file_menu_dialog_qactions_use_horizontal_ellipsis_in_title() -> None:
    """File → actions that open/save dialogs end with Unicode U+2026 in the visible menu title."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("# File menu")
    end = text.index("# View menu", start)
    chunk = text[start:end]
    ell = "\u2026"
    ell_esc = "\\u2026"
    for name in (
        "act_import_docs",
        "act_open_company",
        "act_new_company",
        "act_backup",
        "act_restore",
        "act_save_as",
    ):
        line = next(ln for ln in chunk.splitlines() if f"{name} = QAction(" in ln)
        assert ell in line or ell_esc in line, name
    for name in ("act_copy_db_path", "act_save", "act_exit"):
        line = next(ln for ln in chunk.splitlines() if f"{name} = QAction(" in ln)
        assert ell not in line and ell_esc not in line, name


def test_file_menu_keyboard_shortcuts_import_open_copy_save_exit() -> None:
    """**File** menu wires expected ``QKeySequence`` shortcuts (import, company open, path copy, save, exit)."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("# File menu")
    end = text.index("# View menu", start)
    chunk = text[start:end]
    assert 'act_import_docs.setShortcut("Ctrl+O")' in chunk
    assert 'act_open_company.setShortcut("Ctrl+Shift+O")' in chunk
    assert 'act_copy_db_path.setShortcut("Ctrl+Alt+P")' in chunk
    assert 'act_save.setShortcut("Ctrl+S")' in chunk
    assert 'act_exit.setShortcut("Ctrl+Q")' in chunk


def test_file_menu_save_and_save_as_are_disabled_stubs() -> None:
    """**File** → **Save** / **Save As…** stay disabled with explicit not-yet tips."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("# File menu")
    end = text.index("# View menu", start)
    chunk = text[start:end]
    assert chunk.count("act_save.setEnabled(False)") == 1
    assert chunk.count("act_save_as.setEnabled(False)") == 1
    assert "Save is not used in this desktop shell yet (Ctrl+S)." in chunk
    assert "Save As is not used in this desktop shell yet." in chunk
    assert chunk.count("file_menu.addAction(act_save)") == 1
    assert chunk.count("file_menu.addAction(act_save_as)") == 1
    save_as_ln = next(ln for ln in chunk.splitlines() if "act_save_as = QAction(" in ln)
    assert "Save &As" in save_as_ln
    assert "\\u2026" in save_as_ln or "\u2026" in save_as_ln or "…" in save_as_ln


def test_file_menu_wires_triggered_slots_for_core_company_actions() -> None:
    """**File** menu actions that perform work connect to the expected ``MainWindow`` slots."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("# File menu")
    end = text.index("# View menu", start)
    chunk = text[start:end]
    assert chunk.count("act_import_docs.triggered.connect(self._on_import)") == 1
    assert (
        chunk.count(
            "act_open_company.triggered.connect(self._on_open_company_database)"
        )
        == 1
    )
    assert (
        chunk.count(
            "act_new_company.triggered.connect(self._on_new_company_database)"
        )
        == 1
    )
    assert chunk.count("act_backup.triggered.connect(self._on_backup_company)") == 1
    assert chunk.count("act_restore.triggered.connect(self._on_restore_company)") == 1
    assert (
        chunk.count(
            "act_copy_db_path.triggered.connect(self._on_copy_company_database_path)"
        )
        == 1
    )


def test_edit_menu_keyboard_shortcuts_undo_redo() -> None:
    """**Edit** menu wires standard undo/redo shortcuts (both disabled stubs in this shell)."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("# Edit menu")
    end = text.index("# Tools menu", start)
    chunk = text[start:end]
    assert 'act_undo.setShortcut("Ctrl+Z")' in chunk
    assert 'act_redo.setShortcut("Ctrl+Y")' in chunk
    assert chunk.count("act_undo.setEnabled(False)") == 1
    assert chunk.count("act_redo.setEnabled(False)") == 1
    assert "Undo is not available in this version (Ctrl+Z)." in chunk
    assert "Redo is not available in this version (Ctrl+Y)." in chunk
    assert chunk.count("edit_menu.addAction(act_undo)") == 1
    assert chunk.count("edit_menu.addAction(act_redo)") == 1


def test_edit_menu_preferences_disabled_stub() -> None:
    """**Edit** → **Preferences…** is a disabled stub (ellipsis title, not-available tip)."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("# Edit menu")
    end = text.index("# Tools menu", start)
    chunk = text[start:end]
    line = next(ln for ln in chunk.splitlines() if "act_prefs = QAction(" in ln)
    assert "\\u2026" in line or "\u2026" in line
    assert chunk.count("act_prefs.setEnabled(False)") == 1
    assert "Application preferences are not available yet." in chunk
    assert chunk.count("edit_menu.addAction(act_prefs)") == 1


def test_view_menu_tab_actions_use_menu_action_tip_only() -> None:
    """**View** menu tab shortcuts use ``_menu_action_tip(act, …)`` only (no direct tip methods).

    The loop body is written once in source; the list must still enumerate eight main tabs.
    """
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("# View menu")
    end = text.index("# Edit menu", start)
    chunk = text[start:end]
    assert chunk.count('("Ctrl+') == 8
    assert chunk.count("act = QAction(") == 1
    assert chunk.count("_menu_action_tip(") == 1
    assert "view_menu.addAction(act)" in chunk
    assert "act.setToolTip(" not in chunk
    assert "act.setStatusTip(" not in chunk


def test_main_window_view_menu_ctrl_1_through_8_tuple_source_order() -> None:
    """**View** menu shortcut list keeps **Ctrl+1 … Ctrl+8** paired rows in tab-index order."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("# View menu")
    end = text.index("# Edit menu", start)
    chunk = text[start:end]
    pairs = tuple(
        f'("Ctrl+{n}",' for n in range(1, 9)
    )
    positions = [chunk.index(p) for p in pairs]
    assert positions == sorted(positions)


def test_edit_tools_recon_help_qactions_use_menu_action_tip_only() -> None:
    """**Edit**, **Tools** (Invoice), **Recon** (register), and **Help** actions use ``_menu_action_tip`` only."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("# Edit menu")
    end = text.index("    # -- drag & drop on window", start)
    chunk = text[start:end]
    for name in _EDIT_TOOLS_RECON_HELP_QACTION_NAMES:
        assert chunk.count(f"{name} = QAction(") == 1, name
        tip_hdr = f"_menu_action_tip(\n            {name},"
        assert chunk.count(tip_hdr) == 1, f"{name} should use _menu_action_tip once"
        assert f"{name}.setToolTip(" not in chunk, (
            f"{name} should not call setToolTip directly; use _menu_action_tip"
        )
        assert f"{name}.setStatusTip(" not in chunk, (
            f"{name} should not call setStatusTip directly; use _menu_action_tip"
        )


# Static ``QMessageBox.*`` entry points skip ``tip_message_box_buttons`` / ``setToolTip`` on the dialog.
_DESKTOP_FORBIDDEN_STATIC_QMESSAGEBOX_CALLS: tuple[str, ...] = (
    "QMessageBox.information(",
    "QMessageBox.warning(",
    "QMessageBox.critical(",
    "QMessageBox.about(",
    "QMessageBox.question(",
)


def _assert_desktop_sources_avoid_static_qmessagebox_dialog_methods() -> None:
    for path in _iter_desktop_app_py_files():
        text = path.read_text(encoding="utf-8")
        for n in _DESKTOP_FORBIDDEN_STATIC_QMESSAGEBOX_CALLS:
            assert n not in text, f"{path.relative_to(REPO_ROOT)} should not use {n}"


def _assert_desktop_sources_avoid_substring_except_in_qt_mnemonic(
    needle: str, remediation: str
) -> None:
    """``qt_mnemonic.py`` is the only module that may call ``.button(Q*StandardButton...)`` for tooltips."""
    for path in _iter_desktop_app_py_files():
        if path.name == "qt_mnemonic.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert needle not in text, (
            f"{path.relative_to(REPO_ROOT)} should not use {needle!r}; {remediation}"
        )


def test_main_window_intake_tab_f5_refreshes_inbox() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    assert "sc_intake_f5" in text
    assert "QShortcut(QKeySequence(\"F5\"), intake_widget)" in text
    assert "sc_intake_f5.activated.connect(self._refresh_inbox)" in text


def test_app_header_banner_frame_has_hover_tooltip() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class AppHeaderWidget")
    end = text.index(
        "\n\n# ---------------------------------------------------------------------------\n# Main window",
        start,
    )
    chunk = text[start:end]
    assert "self.setToolTip(" in chunk
    assert "App banner" in chunk


def test_desktop_main_app_header_banner_branding_and_set_company_name() -> None:
    """``AppHeaderWidget`` shows ProBooks+ai + company label; ``set_company_name`` escapes Qt text."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class AppHeaderWidget(QFrame):")
    end = text.index(
        "\n\n# ---------------------------------------------------------------------------\n# Main window",
        start,
    )
    chunk = text[start:end]
    assert "right-aligned" in chunk and "ProBooks+ai" in chunk
    assert chunk.count("super().__init__(parent)") == 1
    assert chunk.count('QLabel("ProBooks+ai")') == 1
    assert "INBOX_HEADER_COLOR" in chunk
    assert chunk.count("setFixedHeight(52)") == 1
    assert chunk.count("QHBoxLayout(self)") == 1
    assert chunk.count("layout.setContentsMargins(14, 6, 14, 6)") == 1
    assert chunk.count("layout.addStretch(1)") == 1
    assert "QVBoxLayout()" in chunk
    assert chunk.count("border-bottom: 2px solid #4a6fa8") == 1
    assert chunk.count(".setToolTip(") == 3
    assert "AI line reconciliation" in chunk
    assert chunk.count("escape_ampersand_for_qt(company_name)") == 1
    assert chunk.count("def set_company_name(self, name: str):") == 1
    assert chunk.count("self._lbl_company.setText(escape_ampersand_for_qt(name))") == 1
    assert "company_name: str = COMPANY_NAME" in chunk
    assert "application_version()" in chunk


def test_desktop_main_app_header_widget_ctor_banner_layout_company_order() -> None:
    """``AppHeaderWidget.__init__`` styles the frame, stretch, right column with app then company labels."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def __init__(self, company_name: str = COMPANY_NAME, parent=None):")
    end = text.index("    def set_company_name(self, name: str):", start)
    chunk = text[start:end]
    su = chunk.index("super().__init__(parent)")
    sty = chunk.index("self.setStyleSheet(")
    fh = chunk.index("self.setFixedHeight(52)")
    ban = chunk.index("App banner; company name is the open SQLite file")
    lay = chunk.index("layout = QHBoxLayout(self)")
    st = chunk.index("layout.addStretch(1)")
    rv = chunk.index("right = QVBoxLayout()")
    app = chunk.index('lbl_app = QLabel("ProBooks+ai")')
    wa = chunk.index(
        "right.addWidget(lbl_app, alignment=Qt.AlignmentFlag.AlignRight)"
    )
    co = chunk.index(
        "self._lbl_company = QLabel(escape_ampersand_for_qt(company_name))"
    )
    wc = chunk.index(
        "right.addWidget(self._lbl_company, alignment=Qt.AlignmentFlag.AlignRight)"
    )
    al = chunk.index("layout.addLayout(right)")
    assert su < sty < fh < ban < lay < st < rv < app < wa < co < wc < al


def test_main_window_defines_bank_import_view_pointer_for_intake_tooltips() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    assert "_BANK_IMPORT_VIEW_POINTER = (" in text
    assert text.count("+ _BANK_IMPORT_VIEW_POINTER") >= 3
    assert "View → Bank Import (Ctrl+2). " in text


def test_main_window_tab_bar_has_tab_tooltips() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    assert "main_tab_bar = self._tabs.tabBar()" in text
    assert "main_tab_bar.setTabToolTip" in text
    assert '_tab_bar_csv_excel_hint = " CSV: UTF-8 with BOM for Excel."' in text
    assert text.count("_tab_bar_csv_excel_hint") == 7
    z = text.index("main_tab_bar.setTabToolTip(\n            0,")
    assert "Bank Import (Ctrl+2)" in text[z : z + 420]
    assert "File → Backup" in text[z : z + 420]
    assert text.count("_main_tab_bar_db_hint") == 8
    assert "Bank CSV/PDF import" in text
    assert "AI line reconciliation (row field copies" in text
    assert "Stmt match (Bank Import AI line reconciliation can populate it)" in text
    assert "Business hub:" in text
    assert "self._tabs.setToolTip(" in text
    assert "Main workspace:" in text
    assert "Bank Import includes AI line reconciliation" in text
    assert "intake_widget.setToolTip(" in text
    assert "AI line reconciliation are on Bank Import (View menu)" in text
    iw = text.split("class InboxWidget(QTableWidget):", 1)[1].split(
        "    def _on_context_menu(self, pos):", 1
    )[0]
    assert "+ _BANK_IMPORT_VIEW_POINTER" in iw
    left_tip = text.split("left.setToolTip(", 1)[1][:320]
    assert "+ _BANK_IMPORT_VIEW_POINTER" in left_tip
    assert "left.setToolTip(" in text
    assert "Document inbox column:" in text
    assert "container.setToolTip(" in text
    assert "company banner and tabbed areas" in text
    assert "Bank Import includes AI line reconciliation and Stmt match sync to Register" in text


def test_main_tab_widgets_have_root_hover_tooltips() -> None:
    """Major tabs set ``self.setToolTip`` so empty margins still show context."""
    bit = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    assert "class BankImportTab" in bit
    bstart = bit.index("class BankImportTab")
    bend = bit.index("def _refresh_accounts", bstart)
    bchunk = bit[bstart:bend]
    assert "def _build_ui(self):" in bchunk
    assert "self.setToolTip(" in bchunk
    assert "Bank CSV/PDF import and reconciliation" in bchunk
    assert "AI-assisted line reconciliation" in bchunk
    assert "exported CSV uses UTF-8 BOM for Excel" in bchunk
    assert "left.setToolTip(" in bchunk
    assert "Import batches column" in bchunk
    assert "statement reconciliation, and AI line reconciliation on the right" in bchunk
    assert "View → Register (Ctrl+3)" in bchunk

    rep = (_DESKTOP_APP_DIR / "reports_tab.py").read_text(encoding="utf-8")
    assert "Financial reports: trial balance" in rep
    assert "with optional date range and CSV export " in rep
    assert '(UTF-8 BOM for Excel) "' in rep

    jt = (_DESKTOP_APP_DIR / "journal_tab.py").read_text(encoding="utf-8")
    assert "General journal: browse entries" in jt
    assert "export CSV (UTF-8 BOM for Excel;" in jt

    at = (_DESKTOP_APP_DIR / "audit_tab.py").read_text(encoding="utf-8")
    assert "Audit trail: field-level changes" in at
    assert "export CSV (UTF-8 BOM for Excel;" in at

    coa = (_DESKTOP_APP_DIR / "coa_tab.py").read_text(encoding="utf-8")
    assert "Chart of accounts: add, edit" in coa

    reg = (_DESKTOP_APP_DIR / "register_tab.py").read_text(encoding="utf-8")
    assert "Bank register for one account:" in reg
    assert "Reconciliation mode + Stmt match can be updated from Bank Import AI line reconciliation" in reg
    assert "View → Bank Import (Ctrl+2), Register (Ctrl+3)" in reg
    assert "and export CSV (UTF-8 BOM for Excel)" in reg

    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    assert "class BusinessHub" in et
    hub = et.split("class BusinessHub", 1)[1].split("def _refresh_current_subtab", 1)[0]
    assert "self.setToolTip(" in hub
    assert "Business hub: Rules, AR invoices" in hub
    assert "CSV exports use UTF-8 BOM for Excel" in hub
    assert "self._business_subtabs.setToolTip(" in hub
    assert "Switch between Rules, Invoices (AR)" in hub
    rules = et.split("class RulesTab", 1)[1].split("class ARTab", 1)[0]
    assert "self.setToolTip(" in rules
    assert "description patterns → COA suggestions" in rules
    ar = et.split("class ARTab", 1)[1].split("class APTab", 1)[0]
    assert "Accounts receivable:" in ar
    ap = et.split("class APTab", 1)[1].split("class PayrollTaxTab", 1)[0]
    assert "Accounts payable:" in ap
    pay = et.split("class PayrollTaxTab", 1)[1].split("class TaxSettingsTab", 1)[0]
    assert "Payroll: employees, pay runs" in pay
    tax = et.split("class TaxSettingsTab", 1)[1].split("class BusinessHub", 1)[0]
    assert "Default sales tax name and rate" in tax


def test_file_menu_restore_tip_mentions_sqlite_backup_api() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("act_restore = QAction")
    end = text.index("act_copy_db_path = QAction", start)
    assert "SQLite backup API" in text[start:end]
    assert "probooks.backup" in text[start:end]


def test_file_menu_backup_tip_mentions_sqlite_online_backup() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("act_backup = QAction")
    end = text.index("act_restore = QAction", start)
    assert "SQLite online backup" in text[start:end]
    assert "probooks.backup" in text[start:end]


def test_backup_company_uses_shared_backup_helper() -> None:
    """File → Backup delegates to probooks.backup (SQLite online backup, safe while DB is open)."""
    text = _MAIN.read_text(encoding="utf-8")
    assert "from probooks.backup import" in text
    start = text.index("def _on_backup_company")
    end = text.index("def _on_restore_company", start)
    chunk = text[start:end]
    assert "backup_database(" in chunk


def test_backup_restore_success_and_confirm_copy_mentions_probooks_cli_parity() -> None:
    """Backup/restore dialogs remind users the desktop path matches the probooks CLI."""
    text = _MAIN.read_text(encoding="utf-8")
    bk = text.split("def _on_backup_company", 1)[1].split("def _on_restore_company", 1)[0]
    assert "Backup complete" in bk
    assert "probooks backup" in bk
    assert "probooks.backup" in bk
    assert "Backup company database (probooks backup)" in bk
    rs = text.split("def _on_restore_company", 1)[1].split("def _on_open_company_database", 1)[0]
    assert "Same engine as probooks restore (probooks.backup)" in rs
    assert "Restore complete" in rs
    assert "probooks restore" in rs
    assert "Select backup to restore (probooks restore)" in rs
    assert 'box.setWindowTitle("Restore company database (probooks restore)")' in rs


def test_open_new_company_qfiledialog_titles_mention_backup() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    assert (
        "Open company database (File → Backup copies the current .db first)" in text
    )
    assert (
        "New company database (back up any existing .db from File → Backup first)"
        in text
    )


def test_main_workspace_status_and_switch_company_copy_mentions_backup() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    assert "File → Backup saves the company .db" in text
    assert "File → Backup copies this .db" in text
    assert "probooks backup / restore" in text
    sc = text.split("def _switch_company_database", 1)[1].split(
        "def _on_backup_company", 1
    )[0]
    assert "File → Backup" in sc
    assert "probooks.backup" in sc


def test_detail_pane_action_buttons_have_tooltips() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    assert "_btn_run.setToolTip" in text
    assert "_btn_approve.setToolTip" in text
    assert "_btn_post.setToolTip" in text
    assert "_btn_reject.setToolTip" in text
    assert "_f_doctype.setToolTip" in text
    assert "_f_coa.setToolTip" in text
    assert "_preview_label.setToolTip" in text
    assert "_f_vendor.setToolTip" in text
    assert "_f_notes.setToolTip" in text
    assert "_f_confidence.setToolTip" in text
    assert "_lbl_rationale.setToolTip" in text
    assert "preview_group.setToolTip" in text
    assert "fields_group.setToolTip" in text
    assert "cat_group.setToolTip" in text
    assert "_lbl_filename.setToolTip" in text
    assert "_lbl_status.setToolTip" in text


def test_main_banner_and_inbox_header_have_tooltips() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    assert "lbl_app.setToolTip" in text
    assert "self._lbl_company.setToolTip" in text
    assert "lbl_inbox.setToolTip" in text


def test_app_header_tooltips_mention_file_backup() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    hdr = text.split("class AppHeaderWidget", 1)[1].split("class MainWindow", 1)[0]
    assert "File → Backup" in hdr
    assert "probooks.backup" in hdr


def test_file_menu_company_file_actions_tips_mention_backup_pointer() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    o = text.index("act_open_company = QAction")
    open_chunk = text[o : text.index("act_new_company = QAction", o)]
    assert "probooks backup" in open_chunk
    n = text.index("act_new_company = QAction")
    new_chunk = text[n : text.index("act_backup = QAction", n)]
    assert "File → Backup" in new_chunk
    c = text.index("act_copy_db_path = QAction")
    copy_chunk = text[c : text.index("act_save = QAction", c)]
    assert "probooks backup" in copy_chunk
    assert "+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX" in copy_chunk


def test_copy_db_path_empty_dialog_tip_mentions_backup() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    s = text.index("def _on_copy_company_database_path")
    chunk = text[s : text.index("def _on_help_roadmap", s)]
    assert "File → Backup" in chunk
    assert "probooks.backup" in chunk


def test_help_roadmap_menu_tip_mentions_backup_snapshot() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    r = text.index("act_roadmap = QAction")
    chunk = text[r : text.index("act_intake_keys = QAction", r)]
    assert "probooks.backup" in chunk


def test_file_exit_menu_tip_suggests_backup() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    e = text.index("_menu_action_tip(\n            act_exit,")
    chunk = text[e : text.index("act_exit.triggered", e)]
    assert "File → Backup" in chunk


def test_main_window_no_toolbar_menu_bar_qaction_counts() -> None:
    """``_build_ui`` has no main ``QToolBar``; menu bar defines 33 ``QAction``s."""
    text = _MAIN.read_text(encoding="utf-8")
    bu_s = text.index("def _build_ui(self):")
    bu_e = text.index("    def _build_menu_bar(self):", bu_s)
    bu_chunk = text[bu_s:bu_e]
    assert "QToolBar(" not in bu_chunk
    assert "addToolBar(" not in bu_chunk
    assert "# Toolbar" not in bu_chunk
    mb_s = text.index("def _build_menu_bar")
    mb_e = text.index("def dragEnterEvent", mb_s)
    assert text[mb_s:mb_e].count("QAction(") == 33


def test_file_menu_import_wires_on_import_and_mentions_ctrl_o() -> None:
    """File → Import documents… still connects to ``_on_import`` with Ctrl+O shortcut."""
    text = _MAIN.read_text(encoding="utf-8")
    mb_s = text.index("def _build_menu_bar")
    mb_e = text.index("def dragEnterEvent", mb_s)
    chunk = text[mb_s:mb_e]
    assert chunk.count("act_import_docs = QAction(") == 1
    assert chunk.count("act_import_docs.triggered.connect(self._on_import)") == 1
    assert "Ctrl+O" in chunk
    assert "Import documents" in chunk


def test_main_window_build_ui_has_no_toolbar() -> None:
    """``_build_ui`` does not construct a main-window import/refresh toolbar."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("def _build_ui(self):")
    end = text.index("def _build_menu_bar", start)
    chunk = text[start:end]
    assert chunk.count("QToolBar(") == 0
    assert chunk.count("self.addToolBar(") == 0


def test_main_window_build_ui_sets_central_status_and_eight_main_tabs() -> None:
    """``_build_ui`` attaches one central widget, one status bar, and eight ``_tabs.addTab`` calls."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("def _build_ui(self):")
    end = text.index("def _build_menu_bar", start)
    chunk = text[start:end]
    assert chunk.count("self.setCentralWidget(") == 1
    assert chunk.count("self.setStatusBar(") == 1
    assert chunk.count("self._tabs.addTab(") == 8


def test_main_window_build_ui_tab_strip_titles_intake_through_audit() -> None:
    """Eight ``addTab`` lines keep Document Intake first and Audit log last, with stable user-visible titles."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("        # ── Tab 1: Document Intake")
    end = text.index("        main_tab_bar = self._tabs.tabBar()", start)
    chunk = text[start:end]
    lines = [ln.strip() for ln in chunk.splitlines() if "self._tabs.addTab(" in ln]
    assert len(lines) == 8
    want = (
        "Document Intake",
        "Bank Import",
        "Bank register",
        "Chart of Accounts",
        "Reports",
        "Journal",
        "Business",
        "Audit log",
    )
    for i, title in enumerate(want):
        assert title in lines[i], (i, title, lines[i])


def test_main_window_build_ui_tab_section_banner_comments_order() -> None:
    """``_build_ui`` keeps **Tab 1→4** section banners before the **Tabs 5–7** block."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("def _build_ui(self):")
    end = text.index("def _build_menu_bar", start)
    chunk = text[start:end]
    markers = (
        "        # ── Tab 1: Document Intake",
        "        # ── Tab 2: Bank Import",
        "        # ── Tab 3: Bank register",
        "        # ── Tab 4: Chart of Accounts",
        "        # ── Tabs 5–7:",
    )
    positions = [chunk.index(m) for m in markers]
    assert positions == sorted(positions)


def test_main_window_build_ui_structural_inline_comments_order() -> None:
    """``_build_ui`` orders menu call, container, tabs, Intake splitter panes, status bar, window DnD."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("def _build_ui(self):")
    end = text.index("    def _build_menu_bar(self):", start)
    chunk = text[start:end]
    assert chunk.index("        self._build_menu_bar()") < chunk.index(
        "        # Container: header banner + tab widget"
    )
    assert chunk.index("        # Container: header banner + tab widget") < chunk.index(
        "        # Tab widget"
    )
    assert chunk.index("        # Tab widget") < chunk.index(
        "        # ── Tab 1: Document Intake"
    )
    t1 = chunk.index("        # ── Tab 1: Document Intake")
    t2 = chunk.index("        # ── Tab 2:", t1)
    intake = chunk[t1:t2]
    assert intake.index("        # Splitter ") < intake.index("        # Left: inbox")
    assert intake.index("        # Left: inbox") < intake.index("        # Right: detail pane")
    assert chunk.index("        # ── Tabs 5–7:") < chunk.index("        # Status bar")
    assert chunk.index("        # Status bar") < chunk.index(
        "        # Drag & drop on the main window itself"
    )


def test_main_window_build_ui_tab_tooltips_intake_f5_and_window_drops() -> None:
    """``_build_ui`` sets eight tab bar tooltips, Intake F5 shortcut, and main-window drag/drop."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("def _build_ui(self):")
    end = text.index("def _build_menu_bar", start)
    chunk = text[start:end]
    assert chunk.count("main_tab_bar.setTabToolTip(") == 8
    assert chunk.count("_main_tab_bar_db_hint") == 8, (
        "one _main_tab_bar_db_hint assignment plus seven tab tooltips that append it (tab 0 uses inline text)"
    )
    assert chunk.count('QShortcut(QKeySequence("F5"), intake_widget)') == 1
    assert chunk.count("sc_intake_f5.setContext(Qt.WidgetWithChildrenShortcut)") == 1
    assert chunk.count("sc_intake_f5.activated.connect(self._refresh_inbox)") == 1
    assert chunk.count("self.setAcceptDrops(True)") == 1


def test_main_window_build_ui_central_status_bar_before_window_accept_drops_order() -> None:
    """``_build_ui`` sets the central widget and status bar before enabling main-window file drops."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("def _build_ui(self):")
    end = text.index("def _build_menu_bar", start)
    chunk = text[start:end]
    cen = chunk.index("self.setCentralWidget(container)")
    stc = chunk.index("        # Status bar")
    ssb = chunk.index("self._status_bar = QStatusBar()")
    dnd = chunk.index("        # Drag & drop on the main window itself")
    acc = chunk.index("self.setAcceptDrops(True)")
    assert cen < stc < ssb < dnd < acc


def test_main_window_intake_left_inbox_header_row_before_inbox_widget_order() -> None:
    """Document Intake left column adds the navy **Document Inbox** header before constructing ``InboxWidget``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("        # Left: inbox")
    end = text.index("        splitter.addWidget(left)", start)
    chunk = text[start:end]
    hdr = chunk.index("left_layout.addWidget(lbl_inbox)")
    ib = chunk.index("self._inbox = InboxWidget()")
    assert hdr < ib


def test_main_window_build_ui_document_intake_split_inbox_header_and_f5() -> None:
    """Document Intake tab builds inbox header (brand colour), horizontal splitter, sizes, F5, first tab."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("        # ── Tab 1: Document Intake")
    end = text.index("        # ── Tab 2:", start)
    chunk = text[start:end]
    assert chunk.count("intake_layout.setContentsMargins(0, 0, 0, 0)") == 1
    assert chunk.count("intake_layout.setSpacing(0)") == 1
    assert chunk.count("left_layout.setContentsMargins(0, 0, 0, 0)") == 1
    assert chunk.count("left_layout.setSpacing(0)") == 1
    assert (
        "review extraction and categorization on the right."
        in chunk
    )
    assert chunk.count("INBOX_HEADER_COLOR") == 1
    assert chunk.count('lbl_inbox = QLabel("  Document Inbox")') == 1
    assert 'font-size: 13px; padding: 6px;' in chunk
    assert chunk.count("lbl_inbox.setToolTip(") == 1
    assert "before bulk deletes or experiments." in chunk
    assert chunk.count("coa_display_list(self._coa)") == 1
    assert chunk.count("DetailPane(coa_display)") == 1
    assert chunk.count("self._detail.runAI.connect(self._on_run_ai)") == 1
    assert chunk.count("self._detail.approve.connect(self._on_approve)") == 1
    assert (
        chunk.count("self._detail.markPosted.connect(self._on_mark_posted)") == 1
    )
    assert chunk.count("self._detail.reject.connect(self._on_reject)") == 1
    assert chunk.count("QSplitter(Qt.Orientation.Horizontal)") == 1
    assert chunk.count("splitter.addWidget(") == 2
    assert chunk.index("splitter.addWidget(left)") < chunk.index(
        "splitter.addWidget(self._detail)"
    )
    assert chunk.count("splitter.setSizes([380, 720])") == 1
    assert (
        "Drag the handle to resize the document inbox and the extraction detail pane."
        in chunk
    )
    assert chunk.count("self._inbox.filesDropped.connect(self._on_files_dropped)") == 1
    assert (
        chunk.count(
            "self._inbox.itemSelectionChanged.connect(self._on_selection_changed)"
        )
        == 1
    )
    assert chunk.count('QShortcut(QKeySequence("F5"), intake_widget)') == 1
    assert chunk.count("self._tabs.addTab(intake_widget,") == 1
    assert "Document Intake" in chunk
    tab_line = next(
        ln for ln in chunk.splitlines() if "self._tabs.addTab(intake_widget," in ln
    )
    assert "\\U0001f4c4" in tab_line or "📄" in tab_line


def test_main_window_build_ui_intake_f5_shortcut_before_add_tab_order() -> None:
    """Document Intake wires the widget-scoped **F5** shortcut before the tab is added to ``_tabs``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("        # ── Tab 1: Document Intake")
    end = text.index("        # ── Tab 2:", start)
    chunk = text[start:end]
    assert chunk.index('QShortcut(QKeySequence("F5"), intake_widget)') < chunk.index(
        "self._tabs.addTab(intake_widget,"
    )


def test_main_window_build_ui_status_bar_ready_message_and_qstatusbar() -> None:
    """``_build_ui`` creates a ``QStatusBar`` with a ready line that mentions File → Backup."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("        # Status bar")
    end = text.index("        # Drag & drop on the main window itself", start)
    chunk = text[start:end]
    assert chunk.count("self._status_bar = QStatusBar()") == 1
    assert chunk.count("self.setStatusBar(self._status_bar)") == 1
    assert chunk.count("self._status_bar.showMessage(") == 1
    assert "application_version()" in chunk
    assert "ProBooks+ai v" in chunk
    assert "AI line reconciliation" in chunk
    assert "Bank Import" in chunk
    assert "File → Backup saves the company .db." in chunk
    assert "drag & drop documents" in chunk
    assert "\\u2013" in chunk


def test_main_window_init_wires_databases_build_ui_and_refresh() -> None:
    """``MainWindow.__init__`` opens DB layers, seeds COA, builds UI, refreshes inbox, updates banner."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def __init__(self, db_path: str | None = None):")
    end = text.index("    # -- UI construction", start)
    chunk = text[start:end]
    assert chunk.count("super().__init__()") == 1
    assert chunk.count("self.resize(1100, 700)") == 1
    assert chunk.count("self._db_path = db_path") == 1
    assert chunk.count("DocumentDatabase(") == 1
    assert chunk.count("BankDatabase(") == 1
    assert chunk.count("apply_extensions(") == 1
    assert chunk.count("GLDatabase(") == 1
    assert chunk.count("COADatabase(") == 1
    assert chunk.count("seed_from_workbook()") == 1
    assert chunk.count("load_coa()") == 1
    assert chunk.count("self._build_ui()") == 1
    assert chunk.count("self._refresh_inbox()") == 1
    assert chunk.count("self._update_company_status()") == 1
    assert chunk.count("self._worker: AIWorker | None = None") == 1


def test_main_window_init_database_and_ui_bootstrap_order() -> None:
    """``MainWindow.__init__`` applies document/bank/GL/COA wiring before ``_build_ui`` → refresh → status."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def __init__(self, db_path: str | None = None):")
    end = text.index("    # -- UI construction", start)
    chunk = text[start:end]
    markers = (
        "self._db = DocumentDatabase(db_path)",
        "self._bank_db = BankDatabase(db_path)",
        "apply_extensions(self._bank_db._conn)",
        "self._gl_db = GLDatabase(self._bank_db._conn)",
        "self._coa_db = COADatabase(self._bank_db._conn)",
        "self._coa_db.seed_from_workbook()",
        "self._coa = load_coa()",
        "self._worker: AIWorker | None = None",
        "self._build_ui()",
        "self._refresh_inbox()",
        "self._update_company_status()",
    )
    positions = [chunk.index(m) for m in markers]
    assert positions == sorted(positions)


def test_main_window_init_super_resize_before_db_path_assignment_order() -> None:
    """``MainWindow.__init__`` calls ``super``, resizes the window, then records ``_db_path``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def __init__(self, db_path: str | None = None):")
    end = text.index("    # -- UI construction", start)
    chunk = text[start:end]
    su = chunk.index("super().__init__()")
    rs = chunk.index("self.resize(1100, 700)")
    dp = chunk.index("self._db_path = db_path")
    assert su < rs < dp


def test_main_window_load_company_at_path_reopens_dbs_rebuilds_tabs_and_refreshes() -> None:
    """``_load_company_at_path`` mirrors startup DB wiring, rebuilds bank tabs, clears/refreshes UI."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _load_company_at_path(self, resolved: str) -> None:")
    end = text.index("    def _switch_company_database(", start)
    chunk = text[start:end]
    assert chunk.count("DocumentDatabase(") == 1
    assert chunk.count("BankDatabase(") == 1
    assert chunk.count("apply_extensions(") == 1
    assert chunk.count("GLDatabase(") == 1
    assert chunk.count("COADatabase(") == 1
    assert chunk.count("seed_from_workbook()") == 1
    assert chunk.count("load_coa()") == 1
    assert chunk.count('QSettings().setValue("company_database_path", resolved)') == 1
    assert chunk.count("self._rebuild_bank_related_tabs()") == 1
    assert chunk.count("self._detail.clear_view()") == 1
    assert chunk.count("self._detail.update_coa(self._coa_db.display_list())") == 1
    assert chunk.count("self._refresh_inbox()") == 1
    assert chunk.count("self._update_company_status()") == 1
    assert "Open SQLite at *resolved*" in chunk


def test_main_window_load_company_at_path_statement_order() -> None:
    """``_load_company_at_path`` persists path, reopens DB layers, rebuilds tabs, resets detail, refreshes UI."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _load_company_at_path(self, resolved: str) -> None:")
    end = text.index("    def _switch_company_database(", start)
    chunk = text[start:end]
    markers = (
        "self._db_path = resolved",
        'QSettings().setValue("company_database_path", resolved)',
        "self._db = DocumentDatabase(resolved)",
        "self._bank_db = BankDatabase(resolved)",
        "apply_extensions(self._bank_db._conn)",
        "self._gl_db = GLDatabase(self._bank_db._conn)",
        "self._coa_db = COADatabase(self._bank_db._conn)",
        "self._coa_db.seed_from_workbook()",
        "self._coa = load_coa()",
        "self._rebuild_bank_related_tabs()",
        "self._detail.clear_view()",
        "self._detail.update_coa(self._coa_db.display_list())",
        "self._refresh_inbox()",
        "self._update_company_status()",
    )
    positions = [chunk.index(m) for m in markers]
    assert positions == sorted(positions)


def test_main_window_switch_company_resolves_path_closes_dbs_before_reload() -> None:
    """``_switch_company_database`` resolves the path, closes both DB handles, then ``_load_company_at_path``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _switch_company_database(self, path: str, *, create_new: bool = False) -> None:")
    end = text.index("    def _on_backup_company(self):", start)
    chunk = text[start:end]
    r = chunk.index("resolved = str(p.resolve())")
    c1 = chunk.index("self._db.close()")
    c2 = chunk.index("self._bank_db.close()")
    ld = chunk.index("self._load_company_at_path(resolved)")
    assert r < c1 < c2 < ld


def test_main_window_switch_company_database_busy_worker_guard_before_path_resolution_order() -> None:
    """``_switch_company_database`` blocks on a running ``AIWorker`` before wrapping ``path`` in ``Path``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _switch_company_database(self, path: str, *, create_new: bool = False) -> None:")
    end = text.index("    def _on_backup_company(self):", start)
    chunk = text[start:end]
    busy = chunk.index("if self._worker and self._worker.isRunning():")
    pp = chunk.index("p = Path(path)")
    assert busy < pp


def test_main_window_switch_company_path_wrap_create_new_branch_before_missing_file_else_order() -> None:
    """``_switch_company_database`` uses ``Path(path)``, then ``if create_new:``, then ``elif not p.exists()``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _switch_company_database(self, path: str, *, create_new: bool = False) -> None:")
    end = text.index("    def _on_backup_company(self):", start)
    chunk = text[start:end]
    pp = chunk.index("p = Path(path)")
    cn = chunk.index("if create_new:")
    miss = chunk.index("elif not p.exists():")
    assert pp < cn < miss


def test_main_window_switch_company_create_new_existing_file_qmessagebox_icon_title_text_before_buttons_order() -> None:
    """When ``create_new`` targets an existing path, the prompt ``QMessageBox`` sets icon, title, body, then buttons."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _switch_company_database(self, path: str, *, create_new: bool = False) -> None:")
    end = text.index("    def _on_backup_company(self):", start)
    chunk = text[start:end]
    sub_start = chunk.index("            if p.exists():")
    sub_end = chunk.index("        elif not p.exists():", sub_start)
    sub = chunk[sub_start:sub_end]
    bx = sub.index("box = QMessageBox(self)")
    ic = sub.index("box.setIcon(QMessageBox.Icon.Question)")
    wt = sub.index('box.setWindowTitle("File exists")')
    tx = sub.index("box.setText(")
    sb = sub.index("box.setStandardButtons(")
    assert bx < ic < wt < tx < sb


def test_main_window_switch_company_create_new_file_exists_qmessagebox_buttons_tooltip_tip_exec_order() -> None:
    """File-exists prompt sets standard/default buttons, dialog tooltip, button tips, then ``exec``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _switch_company_database(self, path: str, *, create_new: bool = False) -> None:")
    end = text.index("    def _on_backup_company(self):", start)
    chunk = text[start:end]
    sub_start = chunk.index("            if p.exists():")
    sub_end = chunk.index("        elif not p.exists():", sub_start)
    sub = chunk[sub_start:sub_end]
    sb = sub.index("box.setStandardButtons(")
    db = sub.index("box.setDefaultButton(QMessageBox.StandardButton.No)")
    dlg_tt = sub.index("box.setToolTip(")
    tip = sub.index("tip_message_box_buttons(")
    ex = sub.index("reply = box.exec()")
    assert sb < db < dlg_tt < tip < ex


def test_main_window_rebuild_removes_tabs_before_tab_specs_insert() -> None:
    """``_rebuild_bank_related_tabs`` removes old tabs, defines ``tab_specs``, then ``insertTab`` in a loop."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _rebuild_bank_related_tabs(self):")
    end = text.index("    def _load_company_at_path(", start)
    chunk = text[start:end]
    rm = chunk.index("for i in range(7, 0, -1):")
    ts = chunk.index("        tab_specs = [")
    ins = chunk.index("for i, (title, widget) in enumerate(tab_specs, start=1):")
    assert rm < ts < ins


def test_main_window_rebuild_bank_tabs_insert_loop_then_widget_refs_and_coa_signal_order() -> None:
    """After ``insertTab`` loop, ``_rebuild_bank_related_tabs`` caches tab refs **1→3** then wires ``coaChanged``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _rebuild_bank_related_tabs(self):")
    end = text.index("    def _load_company_at_path(", start)
    chunk = text[start:end]
    ins = chunk.index("for i, (title, widget) in enumerate(tab_specs, start=1):")
    w1 = chunk.index("self._bank_tab = self._tabs.widget(1)")
    w2 = chunk.index("self._register_tab = self._tabs.widget(2)")
    w3 = chunk.index("self._coa_tab = self._tabs.widget(3)")
    sig = chunk.index("self._coa_tab.coaChanged.connect(self._on_coa_changed)")
    assert ins < w1 < w2 < w3 < sig


def test_main_window_on_backup_save_dialog_try_backup_before_complete_dialog() -> None:
    """``_on_backup_company`` runs ``backup_database`` before the **Backup complete** dialog."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_backup_company(self):")
    end = text.index("    def _on_restore_company(self):", start)
    chunk = text[start:end]
    b = chunk.index("backup_database(src, Path(path))")
    c = chunk.index('"Backup complete"')
    assert b < c


def test_main_window_on_backup_company_dialog_empty_path_suffix_before_backup_database_order() -> None:
    """``_on_backup_company`` picks a path, skips empty, normalizes ``.db``, then calls ``backup_database``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_backup_company(self):")
    end = text.index("    def _on_restore_company(self):", start)
    chunk = text[start:end]
    dlg = chunk.index("QFileDialog.getSaveFileName(")
    emp = chunk.index("if not path:")
    suf = chunk.index('if not path.lower().endswith(".db"):')
    bk = chunk.index("backup_database(src, Path(path))")
    assert dlg < emp < suf < bk


def test_main_window_on_backup_company_busy_worker_guard_before_src_resolve_order() -> None:
    """``_on_backup_company`` blocks on a running ``AIWorker`` before resolving the live ``src`` path."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_backup_company(self):")
    end = text.index("    def _on_restore_company(self):", start)
    chunk = text[start:end]
    busy = chunk.index("if self._worker and self._worker.isRunning():")
    src = chunk.index("src = Path(self._bank_db._db_path).resolve()")
    assert busy < src


def test_main_window_on_backup_company_try_backup_database_except_valueerror_before_os_sqlite_order() -> None:
    """``_on_backup_company`` wraps ``backup_database`` in ``try`` / ``ValueError`` / ``OSError|sqlite`` handlers."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_backup_company(self):")
    end = text.index("    def _on_restore_company(self):", start)
    chunk = text[start:end]
    tr = chunk.index("        try:")
    bk = chunk.index("backup_database(src, Path(path))")
    ev = chunk.index("        except ValueError as exc:")
    eo = chunk.index("        except (OSError, sqlite3.Error) as exc:")
    assert tr < bk < ev < eo


def test_main_window_on_restore_company_try_restore_database_except_valueerror_before_os_sqlite_order() -> None:
    """``_on_restore_company`` wraps ``restore_database`` in ``try`` / ``ValueError`` / ``OSError|sqlite`` handlers."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_restore_company(self):")
    end = text.index("    def _on_open_company_database(self):", start)
    chunk = text[start:end]
    bc = chunk.index("        self._bank_db.close()")
    tr = chunk.index("        try:", bc)
    rst = chunk.index("            restore_database(Path(path), target, overwrite=True)")
    ev = chunk.index("        except ValueError as exc:", bc)
    eo = chunk.index("        except (OSError, sqlite3.Error) as exc:", bc)
    assert bc < tr < rst < ev < eo


def test_main_window_on_restore_company_success_reload_before_complete_information_dialog_order() -> None:
    """On successful restore, ``_load_company_at_path`` runs at module indent before the **Restore complete** dialog."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_restore_company(self):")
    end = text.index("    def _on_open_company_database(self):", start)
    chunk = text[start:end]
    ld = chunk.index("        self._load_company_at_path(str(target))")
    done = chunk.index('"Restore complete"')
    assert ld < done


def test_main_window_on_restore_confirm_dialog_picker_close_restore_reload_complete_order() -> None:
    """``_on_restore_company`` confirms, picks a backup, closes DBs, restores, reloads, then **Restore complete**."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_restore_company(self):")
    end = text.index("    def _on_open_company_database(self):", start)
    chunk = text[start:end]
    ex = chunk.index("reply = box.exec()")
    pick = chunk.index("path, _ = QFileDialog.getOpenFileName(")
    c1 = chunk.index("self._db.close()")
    rst = chunk.index("restore_database(Path(path), target, overwrite=True)")
    sub = "self._load_company_at_path(str(target))"
    assert chunk.count(sub) >= 1
    last_reload = chunk.rindex(sub)
    done = chunk.index('"Restore complete"')
    assert ex < pick < c1 < rst < last_reload < done


def test_main_window_on_restore_company_confirm_box_exec_before_backup_picker_order() -> None:
    """``_on_restore_company`` constructs the warning ``QMessageBox``, ``exec``s it, then shows the open-file dialog."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_restore_company(self):")
    end = text.index("    def _on_open_company_database(self):", start)
    chunk = text[start:end]
    bx = chunk.index("box = QMessageBox(self)")
    ex = chunk.index("reply = box.exec()")
    pick = chunk.index("path, _ = QFileDialog.getOpenFileName(")
    assert bx < ex < pick


def test_main_window_on_restore_company_busy_worker_guard_before_confirm_box_order() -> None:
    """``_on_restore_company`` blocks on a running ``AIWorker`` before building the warning ``QMessageBox``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_restore_company(self):")
    end = text.index("    def _on_open_company_database(self):", start)
    chunk = text[start:end]
    busy = chunk.index("if self._worker and self._worker.isRunning():")
    box = chunk.index("box = QMessageBox(self)")
    assert busy < box


def test_main_window_on_restore_company_qmessagebox_icon_title_text_before_standard_buttons_order() -> None:
    """Destructive restore confirm builds icon, title, body text, then standard buttons on the ``QMessageBox``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_restore_company(self):")
    end = text.index("    def _on_open_company_database(self):", start)
    chunk = text[start:end]
    bx = chunk.index("box = QMessageBox(self)")
    ic = chunk.index("box.setIcon(QMessageBox.Icon.Warning)")
    wt = chunk.index('box.setWindowTitle("Restore company database (probooks restore)")')
    tx = chunk.index("box.setText(")
    sb = chunk.index("box.setStandardButtons(")
    assert bx < ic < wt < tx < sb


def test_main_window_on_restore_company_qmessagebox_buttons_tooltip_tip_exec_order() -> None:
    """Restore confirm sets standard/default buttons, dialog tooltip, ``tip_message_box_buttons``, then ``exec``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_restore_company(self):")
    end = text.index("    def _on_open_company_database(self):", start)
    chunk = text[start:end]
    pick = chunk.index("path, _ = QFileDialog.getOpenFileName(")
    sb = chunk.index("box.setStandardButtons(")
    db = chunk.index("box.setDefaultButton(QMessageBox.StandardButton.No)")
    dlg_tt = chunk.index("box.setToolTip(")
    tip = chunk.index("tip_message_box_buttons(")
    ex = chunk.index("reply = box.exec()")
    assert sb < db < dlg_tt < tip < ex < pick


def test_main_window_on_restore_company_picker_target_same_file_guard_before_close_databases_order() -> None:
    """After the backup picker, ``_on_restore_company`` resolves target, blocks same-as-live path, then closes DBs."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_restore_company(self):")
    end = text.index("    def _on_open_company_database(self):", start)
    chunk = text[start:end]
    pick = chunk.index("path, _ = QFileDialog.getOpenFileName(")
    emp = chunk.index("if not path:")
    tgt = chunk.index("target = Path(self._bank_db._db_path).resolve()")
    same = chunk.index("if Path(path).resolve() == target:")
    cdb = chunk.index("self._db.close()")
    assert pick < emp < tgt < same < cdb


def test_main_window_rebuild_bank_related_tabs_replaces_seven_tabs_and_rewires_coa() -> None:
    """``_rebuild_bank_related_tabs`` removes indices 7..1, inserts seven widgets, reconnects COA."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _rebuild_bank_related_tabs(self):")
    end = text.index("    def _load_company_at_path(", start)
    chunk = text[start:end]
    assert chunk.count("for i in range(7, 0, -1):") == 1
    assert chunk.count("self._tabs.removeTab(i)") == 1
    assert chunk.count("self._tabs.insertTab(i, widget, title)") == 1
    assert chunk.count("for i, (title, widget) in enumerate(tab_specs, start=1):") == 1
    assert chunk.count("self._bank_tab = self._tabs.widget(1)") == 1
    assert chunk.count("self._register_tab = self._tabs.widget(2)") == 1
    assert chunk.count("self._coa_tab = self._tabs.widget(3)") == 1
    assert chunk.count("BankImportTab(") == 1
    assert chunk.count("RegisterTab(") == 1
    assert chunk.count("COATab(") == 1
    assert chunk.count("ReportsTab(") == 1
    assert chunk.count("JournalTab(") == 1
    assert chunk.count("BusinessHub(") == 1
    assert chunk.count("AuditTab(") == 1
    assert chunk.count("self._coa_tab.coaChanged.connect(self._on_coa_changed)") == 1
    assert chunk.count("w = self._tabs.widget(i)") == 1
    assert chunk.count("if w is not None:") == 1
    assert chunk.count("w.deleteLater()") == 1
    assert "Replace bank/GL/COA-related tabs" in chunk
    for title in (
        "🏦  Bank Import",
        "📒  Bank register",
        "📊  Chart of Accounts",
        "📈  Reports",
        "📗  Journal",
        "🧾  Business",
        "📜  Audit log",
    ):
        assert title in chunk, f"tab_specs should include {title!r}"


def test_main_window_switch_company_database_closes_and_loads_at_path() -> None:
    """``_switch_company_database`` closes document/bank DBs then loads the resolved path once."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _switch_company_database(self, path: str, *, create_new: bool = False) -> None:")
    end = text.index("    def _on_backup_company(self):", start)
    chunk = text[start:end]
    assert chunk.count("p = Path(path)") == 1
    assert chunk.count("resolved = str(p.resolve())") == 1
    assert chunk.count("self._db.close()") == 1
    assert chunk.count("self._bank_db.close()") == 1
    assert chunk.count("self._load_company_at_path(resolved)") == 1
    assert (
        "Wait for AI extraction to finish before switching company files." in chunk
    )
    assert (
        'ok_tip="Close; wait for AI, then switch; consider File → Backup / probooks backup before replacing the .db."'
        in chunk
    )


def test_main_window_switch_company_create_new_mkdir_and_open_missing_paths() -> None:
    """``_switch_company_database`` creates parent dirs for new DBs, prompts if file exists, warns when missing."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _switch_company_database(self, path: str, *, create_new: bool = False) -> None:")
    end = text.index("    def _on_backup_company(self):", start)
    chunk = text[start:end]
    assert chunk.index("        if create_new:") < chunk.index("        elif not p.exists():")
    assert chunk.count("if create_new:") == 1
    assert chunk.count("p.parent.mkdir(parents=True, exist_ok=True)") == 1
    assert chunk.count("QMessageBox.Icon.Question") == 1
    assert chunk.count("QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No") == 1
    assert chunk.count("box.setDefaultButton(QMessageBox.StandardButton.No)") == 1
    assert chunk.count("tip_message_box_buttons(") == 1
    assert chunk.count("box.setToolTip(") == 1
    assert (
        "This path already exists; Yes opens it as the company database (reload from disk), No cancels."
        in chunk
    )
    assert (
        "File → Backup / probooks backup can copy your current .db before switching." in chunk
    )
    assert chunk.count('"File exists"') == 1
    assert chunk.count("Open this existing file as the company database?") == 1
    assert chunk.count("reply = box.exec()") == 1
    assert chunk.count("if reply != QMessageBox.StandardButton.Yes:") == 1
    assert chunk.count("elif not p.exists():") == 1
    assert chunk.count('"Not found"') == 1
    assert "File does not exist:" in chunk
    assert (
        'ok_tip="Close; pick an existing .db or use File → New company; back up live data with File → Backup (probooks.backup)."'
        in chunk
    )
    assert (
        'yes="Switch to this .db (reload from disk); use File → Backup / probooks backup on the current file first if needed."'
        in chunk
    )
    assert (
        'no="Cancel; keep the current company file (back it up with File → Backup before switching if unsure)."'
        in chunk
    )


def test_main_window_destructive_yes_no_dialogs_use_tip_message_box_buttons() -> None:
    """New-company file-exists and restore-confirm prompts use ``tip_message_box_buttons`` for Ok/Cancel hints."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class MainWindow(QMainWindow):")
    end = text.index("\n\n# ---------------------------------------------------------------------------\n# Entry point", start)
    chunk = text[start:end]
    assert chunk.count("tip_message_box_buttons(") == 2


def test_main_window_close_event_closes_database_connections() -> None:
    """``closeEvent`` closes document and bank DBs before the base handler."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def closeEvent(self, event):")
    end = text.index("\n\n# ---------------------------------------------------------------------------\n# Entry point", start)
    chunk = text[start:end]
    assert chunk.count("self._db.close()") == 1
    assert chunk.count("self._bank_db.close()") == 1
    assert chunk.count("super().closeEvent(event)") == 1
    a = chunk.index("self._db.close()")
    b = chunk.index("self._bank_db.close()")
    c = chunk.index("super().closeEvent(event)")
    assert a < b < c


def test_main_window_switch_backup_restore_guard_busy_ai_worker() -> None:
    """Switch company, File → Backup, and File → Restore each block on a running ``AIWorker``."""
    text = _MAIN.read_text(encoding="utf-8")
    spans = (
        (
            "    def _switch_company_database(self, path: str, *, create_new: bool = False) -> None:",
            "    def _on_backup_company(self):",
        ),
        ("    def _on_backup_company(self):", "    def _on_restore_company(self):"),
        (
            "    def _on_restore_company(self):",
            "    def _on_open_company_database(self):",
        ),
    )
    for start_m, end_m in spans:
        start = text.index(start_m)
        end = text.index(end_m, start)
        chunk = text[start:end]
        assert chunk.count("if self._worker and self._worker.isRunning():") == 1, start_m
        assert chunk.count('"Busy"') == 1, start_m


def test_main_window_on_backup_company_calls_backup_database_and_dialog_flow() -> None:
    """Backup: resolved src path, default *-backup.db name, ``.db`` suffix, ``backup_database``, dialogs."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_backup_company(self):")
    end = text.index("    def _on_restore_company(self):", start)
    chunk = text[start:end]
    assert chunk.count("QFileDialog.getSaveFileName(") == 1
    assert chunk.count("Backup company database (probooks backup)") == 1
    assert chunk.count("src = Path(self._bank_db._db_path).resolve()") == 1
    assert chunk.count('f"{src.stem}-backup.db"') == 1
    assert chunk.count('if not path.lower().endswith(".db"):') == 1
    assert chunk.count('path += ".db"') == 1
    assert chunk.count("backup_database(src, Path(path))") == 1
    assert chunk.count("if not path:") == 1
    assert chunk.count('"Backup failed"') == 2
    assert chunk.count('"Backup complete"') == 1
    assert "Same engine as probooks backup" in chunk
    assert (
        "Wait for AI extraction to finish before backing up." in chunk
    )
    assert chunk.count("except ValueError as exc:") == 1
    assert chunk.count("except (OSError, sqlite3.Error) as exc:") == 1
    assert "disk space, permissions, and locks" in chunk
    assert "repair it" in chunk
    assert "open a valid company" in chunk
    assert chunk.count('"SQLite Database (*.db);;All Files (*.*)"') == 1
    assert (
        'ok_tip="Close; wait for AI, then File → Backup again (same engine as probooks backup)."'
        in chunk
    )
    assert (
        'ok_tip="Close; the backup file is ready at the path shown."' in chunk
    )


def test_main_window_on_restore_company_restores_and_reload_paths() -> None:
    """Restore flow: backup picker, reject live .db path, ``restore_database``, reload + dialogs."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_restore_company(self):")
    end = text.index("    def _on_open_company_database(self):", start)
    chunk = text[start:end]
    assert chunk.count("self._db.close()") == 1
    assert chunk.count("self._bank_db.close()") == 1
    assert chunk.count("restore_database(Path(path), target, overwrite=True)") == 1
    assert chunk.count("self._load_company_at_path(str(target))") == 3
    assert chunk.count('"Restore failed"') == 2
    assert chunk.count('"Restore complete"') == 1
    assert chunk.count("QFileDialog.getOpenFileName(") == 1
    assert chunk.count("if not path:") == 1
    assert chunk.count("Select backup to restore (probooks restore)") == 1
    assert chunk.count("Path(path).resolve() == target") == 1
    assert chunk.count("target = Path(self._bank_db._db_path).resolve()") == 1
    assert "Choose a different file than the active company database." in chunk
    assert chunk.count("QMessageBox.Icon.Warning") == 1
    assert chunk.count("Restore company database (probooks restore)") == 1
    assert "Unsaved work in memory is discarded." in chunk
    assert "Continue?" in chunk
    assert "Restore overwrites the active company database on disk via probooks.backup" in chunk
    assert chunk.count("box.setDefaultButton(QMessageBox.StandardButton.No)") == 1
    assert chunk.count("tip_message_box_buttons(") == 1
    assert (
        'yes="Overwrite the live company .db with the backup (probooks restore / File → Restore; probooks.backup)."'
        in chunk
    )
    assert (
        'no="Cancel restore; keep the current file (File → Backup first if you want a copy)."'
        in chunk
    )
    assert chunk.count("reply = box.exec()") == 1
    assert chunk.count("if reply != QMessageBox.StandardButton.Yes:") == 1
    assert (
        "Wait for AI extraction to finish before restoring." in chunk
    )
    assert (
        'ok_tip="Close; wait for AI, then File → Restore again (same engine as probooks restore)."'
        in chunk
    )
    assert (
        'ok_tip="Close; pick a backup copy, not the live .db (same rules as probooks restore / probooks.backup)."'
        in chunk
    )
    assert (
        'ok_tip="Close; you are now on the restored company database."' in chunk
    )
    assert (
        'ok_tip="Close; release locks and retry; probooks restore uses the same engine (probooks.backup)."'
        in chunk
    )
    assert chunk.count("except ValueError as exc:") == 1
    assert chunk.count("except (OSError, sqlite3.Error) as exc:") == 1
    assert "Try closing other apps using the database" in chunk
    assert "Company data was reloaded from the backup." in chunk
    assert chunk.count('"SQLite Database (*.db);;All Files (*.*)"') == 1
    assert "pick a valid SQLite backup" in chunk
    assert chunk.count("except Exception:") == 2


def test_main_window_backup_restore_database_calls_are_singletons() -> None:
    """``MainWindow`` invokes ``backup_database`` / ``restore_database`` only from File → Backup / Restore."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class MainWindow(QMainWindow):")
    end = text.index("\n\n# ---------------------------------------------------------------------------\n# Entry point", start)
    chunk = text[start:end]
    assert chunk.count("backup_database(src, Path(path))") == 1
    assert chunk.count("restore_database(Path(path), target, overwrite=True)") == 1


def test_main_window_question_and_warning_icons_for_company_dialogs() -> None:
    """Existing-company switch uses **Question**; restore confirmation uses **Warning**."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class MainWindow(QMainWindow):")
    end = text.index("\n\n# ---------------------------------------------------------------------------\n# Entry point", start)
    chunk = text[start:end]
    assert chunk.count("QMessageBox.Icon.Question") == 1
    assert chunk.count("QMessageBox.Icon.Warning") == 1


def test_main_window_two_stacked_qmessagebox_instances_for_yes_no_flows() -> None:
    """``MainWindow`` builds two ``QMessageBox(self)`` boxes: new-company file exists, restore confirm."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class MainWindow(QMainWindow):")
    end = text.index("\n\n# ---------------------------------------------------------------------------\n# Entry point", start)
    chunk = text[start:end]
    assert chunk.count("box = QMessageBox(self)") == 2


def test_main_window_on_open_company_database_reads_settings_and_switches() -> None:
    """``_on_open_company_database`` uses QSettings start dir and delegates to switch (not create)."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_open_company_database(self):")
    end = text.index("    def _on_new_company_database(self):", start)
    chunk = text[start:end]
    assert chunk.count('QSettings().value("company_database_path", "", type=str)') == 1
    assert (
        'start_dir = str(Path(prev).parent) if prev else ""' in chunk
    )
    assert chunk.count("QFileDialog.getOpenFileName(") == 1
    assert (
        "Open company database (File → Backup copies the current .db first)" in chunk
    )
    assert chunk.count("if path:") == 1
    assert chunk.count("self._switch_company_database(path, create_new=False)") == 1
    assert chunk.count('"SQLite Database (*.db);;All Files (*.*)"') == 1
    assert chunk.index("QFileDialog.getOpenFileName(") < chunk.index(
        "self._switch_company_database(path, create_new=False)"
    )


def test_main_window_on_open_company_database_prev_start_dir_before_file_dialog_order() -> None:
    """``_on_open_company_database`` reads settings, derives ``start_dir``, then shows the open-file dialog."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_open_company_database(self):")
    end = text.index("    def _on_new_company_database(self):", start)
    chunk = text[start:end]
    prev = chunk.index('prev = QSettings().value("company_database_path", "", type=str) or ""')
    sd = chunk.index('start_dir = str(Path(prev).parent) if prev else ""')
    dlg = chunk.index("QFileDialog.getOpenFileName(")
    assert prev < sd < dlg


def test_main_window_on_new_company_database_suffixes_db_and_switches() -> None:
    """``_on_new_company_database`` saves a .db path and opens via switch with ``create_new=True``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_new_company_database(self):")
    end = text.index("    def closeEvent(self, event):", start)
    chunk = text[start:end]
    assert chunk.count('QSettings().value("company_database_path", "", type=str)') == 1
    assert (
        'start_dir = str(Path(prev).parent) if prev else ""' in chunk
    )
    assert chunk.count("QFileDialog.getSaveFileName(") == 1
    assert (
        "New company database (back up any existing .db from File → Backup first)" in chunk
    )
    assert chunk.count("if path:") == 1
    assert chunk.count('if not path.lower().endswith(".db"):') == 1
    assert chunk.count('path += ".db"') == 1
    assert chunk.count("self._switch_company_database(path, create_new=True)") == 1
    assert chunk.count('"SQLite Database (*.db);;All Files (*.*)"') == 1
    assert chunk.index("QFileDialog.getSaveFileName(") < chunk.index("if path:")
    assert chunk.index("if path:") < chunk.index('if not path.lower().endswith(".db"):')
    assert chunk.index('if not path.lower().endswith(".db"):') < chunk.index(
        "self._switch_company_database(path, create_new=True)"
    )


def test_main_window_on_new_company_database_prev_start_dir_before_save_dialog_order() -> None:
    """``_on_new_company_database`` reads settings, derives ``start_dir``, then shows the save-file dialog."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_new_company_database(self):")
    end = text.index("    def closeEvent(self, event):", start)
    chunk = text[start:end]
    prev = chunk.index('prev = QSettings().value("company_database_path", "", type=str) or ""')
    sd = chunk.index('start_dir = str(Path(prev).parent) if prev else ""')
    dlg = chunk.index("QFileDialog.getSaveFileName(")
    assert prev < sd < dlg


def test_main_window_on_run_ai_guards_worker_api_key_and_starts_ai_worker() -> None:
    """``_on_run_ai`` blocks on running worker / missing key, then runs ``AIWorker`` with signal hooks."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_run_ai(self, doc_id: int):")
    end = text.index("    def _on_ai_done(self, doc_id: int, result, suggestions):", start)
    chunk = text[start:end]
    assert "did = coerce_combo_int_id(doc_id)" in chunk
    assert chunk.count("if self._worker and self._worker.isRunning():") == 1
    assert '"AI Running"' in chunk
    assert chunk.count("self._db.get_document(did)") == 1
    assert chunk.count("if not row:") == 1
    assert (
        "Please wait \\u2013 AI extraction is already in progress." in chunk
    )
    assert "Running AI extraction on" in chunk and "\\u2026" in chunk
    assert chunk.count('os.environ.get("OPENAI_API_KEY")') == 1
    assert '"API Key Missing"' in chunk
    assert (
        'ok_tip="Close; wait for the current extraction to finish before running again."'
        in chunk
    )
    assert 'ok_tip="Close; set the key, restart the app, then run AI again."' in chunk
    assert chunk.count('self._db.set_status(did, "Extracted")') == 1
    assert (
        chunk.count(
            "AIWorker(did, row[\"stored_path\"], row[\"mimetype\"], self._coa)"
        )
        == 1
    )
    assert (
        chunk.count(
            ".finished.connect(lambda res, sug: self._on_ai_done(did, res, sug))"
        )
        == 1
    )
    assert (
        chunk.count(
            ".error.connect(lambda err: self._on_ai_error(did, err))"
        )
        == 1
    )
    assert chunk.count("self._worker.start()") == 1


def test_main_window_on_ai_done_and_error_finalize_extraction() -> None:
    """``_on_ai_done`` persists extraction; ``_on_ai_error`` marks error and shows a critical box."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_ai_done(self, doc_id: int, result, suggestions):")
    end = text.index("    def _on_approve(self, doc_id: int):", start)
    chunk = text[start:end]
    assert chunk.count("self._db.save_extraction(did, result)") == 1
    assert chunk.count('self._db.set_status(did, "Needs Review")') == 1
    assert chunk.count("self._detail.populate_ai_result(result, suggestions)") == 1
    assert chunk.count("self._refresh_inbox()") == 2
    assert chunk.count('self._db.set_status(did, "Error")') == 1
    assert chunk.count('"AI Extraction Failed"') == 1
    assert chunk.count("message_box_critical_ok(") == 1
    assert (
        'ok_tip="Close; check network, API key, and document format, then retry."'
        in chunk
    )
    assert "AI extraction complete for" in chunk
    assert "AI extraction failed." in chunk


def test_main_window_on_approve_mark_posted_reject_detail_flow() -> None:
    """Approve / posted / reject slots persist status and refresh inbox (selection sync reloads detail)."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_approve(self, doc_id: int):")
    end = text.index("    # -- helpers", start)
    chunk = text[start:end]
    assert chunk.count("self._detail.collect_approved_values()") == 1
    assert chunk.count("self._db.save_approved(did, values)") == 1
    assert chunk.count('self._db.set_status(did, "Approved")') == 1
    assert chunk.count('self._db.set_status(did, "Posted")') == 1
    assert chunk.count('self._db.set_status(did, "Needs Review")') == 1
    assert chunk.count('"Not Yet Approved"') == 1
    assert chunk.count("self._detail.load_document(did, self._db)") == 0
    assert "Document approved and values saved." in chunk
    assert "Document marked as Posted." in chunk
    flagged = "Document flagged \u2013 Needs Review."
    flagged_esc = "Document flagged \\u2013 Needs Review."
    assert flagged in chunk or flagged_esc in chunk


def test_main_window_on_mark_posted_warns_until_approved() -> None:
    """``_on_mark_posted`` blocks until status is Approved, then sets Posted and refreshes UI."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_mark_posted(self, doc_id: int):")
    end = text.index("    def _on_reject(self, doc_id: int):", start)
    chunk = text[start:end]
    assert chunk.count("self._db.get_document(did)") == 1
    assert chunk.count('row["status"] != "Approved"') == 1
    assert chunk.count('"Not Yet Approved"') == 1
    assert "Please approve the document before marking it as Posted." in chunk
    assert 'ok_tip="Close; use Approve in the detail pane first."' in chunk
    assert chunk.count('self._db.set_status(did, "Posted")') == 1
    assert chunk.count("self._detail.load_document(did, self._db)") == 0


def test_main_window_on_mark_posted_fetches_row_before_not_approved_gate() -> None:
    """``_on_mark_posted`` loads the document row before the **Not Yet Approved** dialog."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_mark_posted(self, doc_id: int):")
    end = text.index("    def _on_reject(self, doc_id: int):", start)
    chunk = text[start:end]
    g = chunk.index("self._db.get_document(did)")
    n = chunk.index('"Not Yet Approved"')
    p = chunk.index('self._db.set_status(did, "Posted")')
    assert g < n < p


def test_main_window_on_mark_posted_success_branch_persist_refresh_detail_message_order() -> None:
    """After the **Not Yet Approved** gate, posted flow sets **Posted**, refreshes (syncs detail), status."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_mark_posted(self, doc_id: int):")
    end = text.index("    def _on_reject(self, doc_id: int):", start)
    chunk = text[start:end]
    gate = chunk.index('"Not Yet Approved"')
    st = chunk.index('self._db.set_status(did, "Posted")')
    rf = chunk.index("self._refresh_inbox()")
    msg = chunk.index("Document marked as Posted.")
    assert gate < st < rf < msg


def test_main_window_on_run_ai_busy_fetch_key_status_worker_start_order() -> None:
    """``_on_run_ai`` checks busy state, loads the row, API key, status message, **Extracted**, worker, ``start``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_run_ai(self, doc_id: int):")
    end = text.index("    def _on_ai_done(self, doc_id: int, result, suggestions):", start)
    chunk = text[start:end]
    co = chunk.index("did = coerce_combo_int_id(doc_id)")
    busy = chunk.index("if self._worker and self._worker.isRunning():")
    row = chunk.index("row = self._db.get_document(did)")
    key = chunk.index('if not os.environ.get("OPENAI_API_KEY"):')
    msg = chunk.index("Running AI extraction on")
    st = chunk.index('self._db.set_status(did, "Extracted")')
    wk = chunk.index("self._worker = AIWorker(")
    go = chunk.index("self._worker.start()")
    assert co < busy < row < key < msg < st < wk < go


def test_main_window_on_ai_done_save_status_detail_refresh_message_order() -> None:
    """``_on_ai_done`` saves extraction, sets **Needs Review**, refreshes inbox (syncs detail), fills AI fields, status."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_ai_done(self, doc_id: int, result, suggestions):")
    end = text.index("    def _on_ai_error(self, doc_id: int, error: str):", start)
    chunk = text[start:end]
    co = chunk.index("did = coerce_combo_int_id(doc_id)")
    a = chunk.index("self._db.save_extraction(did, result)")
    b = chunk.index('self._db.set_status(did, "Needs Review")')
    c = chunk.index("self._refresh_inbox()")
    d = chunk.index("self._detail.populate_ai_result(result, suggestions)")
    e = chunk.index("AI extraction complete for")
    assert co < a < b < c < d < e


def test_main_window_on_ai_error_status_refresh_critical_then_status_message_order() -> None:
    """``_on_ai_error`` marks **Error**, refreshes inbox, shows the critical box, then a failed status line."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_ai_error(self, doc_id: int, error: str):")
    end = text.index("    def _on_approve(self, doc_id: int):", start)
    chunk = text[start:end]
    co = chunk.index("did = coerce_combo_int_id(doc_id)")
    a = chunk.index('self._db.set_status(did, "Error")')
    b = chunk.index("self._refresh_inbox()")
    c = chunk.index('"AI Extraction Failed"')
    d = chunk.index('self._status_bar.showMessage("AI extraction failed.")')
    assert co < a < b < c < d


def test_main_window_on_approve_save_status_refresh_detail_message_order() -> None:
    """``_on_approve`` saves values, sets **Approved**, refreshes inbox (syncs detail), then status text."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_approve(self, doc_id: int):")
    end = text.index("    def _on_mark_posted(self, doc_id: int):", start)
    chunk = text[start:end]
    co = chunk.index("did = coerce_combo_int_id(doc_id)")
    a = chunk.index("self._detail.collect_approved_values()")
    b = chunk.index("self._db.save_approved(did, values)")
    c = chunk.index('self._db.set_status(did, "Approved")')
    d = chunk.index("self._refresh_inbox()")
    f = chunk.index("Document approved and values saved.")
    assert co < a < b < c < d < f


def test_main_window_on_reject_status_refresh_detail_message_order() -> None:
    """``_on_reject`` sets **Needs Review**, refreshes inbox (syncs detail), then status text."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_reject(self, doc_id: int):")
    end = text.index("    # -- helpers", start)
    chunk = text[start:end]
    co = chunk.index("did = coerce_combo_int_id(doc_id)")
    a = chunk.index('self._db.set_status(did, "Needs Review")')
    b = chunk.index("self._refresh_inbox()")
    d = chunk.index("Document flagged")
    assert co < a < b < d


def test_main_window_import_files_refresh_before_skipped_then_import_count_messages() -> None:
    """``_import_files`` refreshes the inbox before skipped/imported status messaging."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _import_files(self, paths: list[str]):")
    end = text.index("    def _on_selection_changed(self):", start)
    chunk = text[start:end]
    r = chunk.index("self._refresh_inbox()")
    s = chunk.index('"Skipped Files"')
    m = chunk.index("Imported {imported} document(s).")
    assert r < s < m


def test_desktop_main_detail_pane_load_document_hydration_pipeline_order() -> None:
    """``load_document`` coerces id, stores it, loads row, filename, preview, approved/extraction, fields, then enables actions."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def load_document(self, doc_id: int, db: DocumentDatabase):")
    end = text.index("    def populate_ai_result(self, result, suggestions=None):", start)
    chunk = text[start:end]
    co = chunk.index("did = coerce_combo_int_id(doc_id)")
    a = chunk.index("self._doc_id = did")
    b = chunk.index("row = db.get_document(did)")
    c = chunk.index('self._lbl_filename.setText(escape_ampersand_for_qt(row["filename"]))')
    d = chunk.index('self._show_preview(row["stored_path"], row["mimetype"], row["page_count"])')
    e = chunk.index("approved = db.get_approved(did)")
    ex = chunk.index("extraction = db.get_latest_extraction(did)")
    sr = chunk.index("src = approved or extraction")
    f = chunk.index("self._populate_fields(src)")
    cat = chunk.index("        if approved:")
    coa = chunk.index('self._set_coa_combo_raw(approved["coa_account"])')
    tax = chunk.index('self._f_tax_cat.setText(approved["tax_category"] or "")')
    g = chunk.index("self._set_buttons_enabled(True)")
    assert co < a < b < c < d < e < ex < sr < f < cat < coa < tax < g


def test_desktop_main_detail_pane_load_document_filename_status_richtext_before_preview_order() -> None:
    """``load_document`` sets filename, builds rich status text, then calls ``_show_preview``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def load_document(self, doc_id: int, db: DocumentDatabase):")
    end = text.index("    def populate_ai_result(self, result, suggestions=None):", start)
    chunk = text[start:end]
    fn = chunk.index('self._lbl_filename.setText(escape_ampersand_for_qt(row["filename"]))')
    st = chunk.index('status = row["status"]')
    fmt = chunk.index("self._lbl_status.setTextFormat(Qt.TextFormat.RichText)")
    lab = chunk.index('self._lbl_status.setText(f"Status: <b style')
    pv = chunk.index('self._show_preview(row["stored_path"], row["mimetype"], row["page_count"])')
    assert fn < st < fmt < lab < pv


def test_desktop_main_detail_pane_load_document_get_row_guard_before_filename_order() -> None:
    """``load_document`` fetches the row, applies the empty guard, then sets the filename label."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def load_document(self, doc_id: int, db: DocumentDatabase):")
    end = text.index("    def populate_ai_result(self, result, suggestions=None):", start)
    chunk = text[start:end]
    gr = chunk.index("row = db.get_document(did)")
    gu = chunk.index("if not row:")
    fn = chunk.index('self._lbl_filename.setText(escape_ampersand_for_qt(row["filename"]))')
    assert gr < gu < fn


def test_desktop_main_detail_pane_populate_ai_result_extraction_before_suggestions() -> None:
    """``populate_ai_result`` fills from extraction before the suggestions branch."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def populate_ai_result(self, result, suggestions=None):")
    end = text.index("    def collect_approved_values(self) -> dict:", start)
    chunk = text[start:end]
    ext = chunk.index("self._populate_fields_from_extraction(result)")
    sug = chunk.index("if suggestions and not suggestions.error:")
    assert ext < sug


def test_desktop_main_detail_pane_update_coa_snapshot_fill_restore_order() -> None:
    """``update_coa`` reads current value, rebuilds the combo, then restores selection."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def update_coa(self, coa_list: list[str]):")
    end = text.index("    def _fill_coa_combo(self, coa_list: list[str]) -> None:", start)
    chunk = text[start:end]
    a = chunk.index("current = self._coa_combo_raw_value()")
    b = chunk.index("self._fill_coa_combo(coa_list)")
    c = chunk.index("self._set_coa_combo_raw(current)")
    assert a < b < c


def test_desktop_main_detail_pane_fill_coa_combo_clear_placeholder_then_rows() -> None:
    """``_fill_coa_combo`` clears the combo, adds the placeholder row, then appends COA lines."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _fill_coa_combo(self, coa_list: list[str]) -> None:")
    end = text.index("    def _coa_combo_raw_value(self) -> str | None:", start)
    chunk = text[start:end]
    cl = chunk.index("self._f_coa.clear()")
    ph = chunk.index("escape_ampersand_for_qt(_COA_SELECT_LABEL)")
    lp = chunk.index("for coa in coa_list:")
    assert cl < ph < lp


def test_desktop_main_detail_pane_clear_view_resets_id_first_disables_actions_last() -> None:
    """``clear_view`` clears ``_doc_id`` first and disables action buttons last."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def clear_view(self):")
    end = text.index(
        "\n\n# ---------------------------------------------------------------------------\n# App header / banner",
        start,
    )
    chunk = text[start:end]
    first = chunk.index("self._doc_id = None")
    mid = chunk.index('self._lbl_filename.setText("No document selected")')
    last = chunk.index("self._set_buttons_enabled(False)")
    assert first < mid < last


def test_main_window_on_import_and_files_dropped_delegate_to_import_files() -> None:
    """File → Import and inbox drops both funnel into ``_import_files``."""
    text = _MAIN.read_text(encoding="utf-8")
    imp_s = text.index("    def _on_import(self):")
    imp_e = text.index("    def _on_files_dropped(self, paths: list[str]):", imp_s)
    imp_chunk = text[imp_s:imp_e]
    assert imp_chunk.count("QFileDialog.getOpenFileNames(") == 1
    assert imp_chunk.count("Import Documents") == 1
    assert imp_chunk.count("if paths:") == 1
    assert imp_chunk.count("self._import_files(paths)") == 1
    assert (
        'Documents (*.pdf *.jpg *.jpeg *.png);;All Files (*.*)' in imp_chunk
    )
    dlg = imp_chunk.index("QFileDialog.getOpenFileNames(")
    gate = imp_chunk.index("if paths:")
    imp = imp_chunk.index("self._import_files(paths)")
    assert dlg < gate < imp

    drop_s = imp_e
    drop_e = text.index("    def _import_files(self, paths: list[str]):", drop_s)
    drop_chunk = text[drop_s:drop_e]
    assert drop_chunk.count("self._import_files(paths)") == 1


def test_main_window_on_selection_changed_loads_detail_when_row_selected() -> None:
    """Inbox selection changes load the active document or clear the detail pane when nothing is selected."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_selection_changed(self):")
    end = text.index("    def _on_run_ai(self, doc_id: int):", start)
    chunk = text[start:end]
    assert chunk.count("self._inbox.selected_doc_id()") == 1
    assert chunk.count("if doc_id is not None:") == 1
    assert chunk.count("self._detail.load_document(doc_id, self._db)") == 1
    assert chunk.count("self._detail.clear_view()") == 1


def test_main_window_on_selection_changed_doc_id_before_load_document_order() -> None:
    """``_on_selection_changed`` reads ``selected_doc_id`` before load vs clear."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_selection_changed(self):")
    end = text.index("    def _on_run_ai(self, doc_id: int):", start)
    chunk = text[start:end]
    d = chunk.index("doc_id = self._inbox.selected_doc_id()")
    g = chunk.index("if doc_id is not None:")
    ld = chunk.index("self._detail.load_document(doc_id, self._db)")
    cl = chunk.index("self._detail.clear_view()")
    assert d < g < ld < cl


def test_main_window_import_files_filters_extensions_adds_documents_refreshes_inbox() -> None:
    """``_import_files`` skips unknown extensions, stores accepted types, then refreshes the inbox."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _import_files(self, paths: list[str]):")
    end = text.index("    def _on_selection_changed(self):", start)
    chunk = text[start:end]
    assert chunk.count("ACCEPTED_EXTENSIONS") == 1
    assert chunk.count("skipped.append(Path(path).name)") == 1
    assert chunk.count("self._db.add_document(path, mime, store=True)") == 1
    assert chunk.count("imported += 1") == 1
    assert chunk.count("self._refresh_inbox()") == 1
    assert chunk.count("if skipped:") == 1
    assert chunk.count('"Skipped Files"') == 1
    assert "use PDF or supported images only for Intake import." in chunk
    assert (
        'ok_tip="Close; use PDF or supported images only for Intake import."' in chunk
    )
    assert chunk.count("if imported:") == 1
    assert chunk.count("Imported {imported} document(s).") == 1
    assert ' + "\\n".join(escape_ampersand_for_qt(s) for s in skipped)' in chunk
    assert "imported = 0" in chunk
    assert "skipped  = []" in chunk


def test_main_window_import_files_per_path_ext_gate_before_mime_before_add_document_order() -> None:
    """Each import path checks extension, skips early, guesses MIME, then calls ``add_document``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _import_files(self, paths: list[str]):")
    end = text.index("    def _on_selection_changed(self):", start)
    chunk = text[start:end]
    lp = chunk.index("for path in paths:")
    ex = chunk.index("ext = Path(path).suffix.lower()")
    sk = chunk.index("if ext not in ACCEPTED_EXTENSIONS:")
    mt = chunk.index("mime, _ = mimetypes.guess_type(path)")
    ad = chunk.index("self._db.add_document(path, mime, store=True)")
    assert lp < ex < sk < mt < ad


def test_main_window_import_files_mime_guess_fallback_and_import_error_status() -> None:
    """``_import_files`` uses ``mimetypes.guess_type`` with PDF/image fallback; failures surface on the status bar."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _import_files(self, paths: list[str]):")
    end = text.index("    def _on_selection_changed(self):", start)
    chunk = text[start:end]
    assert chunk.count("mimetypes.guess_type(path)") == 1
    assert 'mime or ("application/pdf" if ext == ".pdf" else "image/jpeg")' in chunk
    assert chunk.count("try:") == 1
    assert chunk.count("except Exception as exc:") == 1
    assert "Error importing" in chunk


def test_main_window_import_files_try_add_document_before_except_order() -> None:
    """``_import_files`` wraps ``add_document`` in ``try`` / ``except`` around each accepted path."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _import_files(self, paths: list[str]):")
    end = text.index("    def _on_selection_changed(self):", start)
    chunk = text[start:end]
    tr = chunk.index("try:")
    ad = chunk.index("self._db.add_document(path, mime, store=True)")
    ex = chunk.index("except Exception as exc:")
    assert tr < ad < ex


def test_main_window_refresh_inbox_and_coa_changed_sync_lists() -> None:
    """``_refresh_inbox`` repopulates the inbox and syncs selection; ``_on_coa_changed`` refreshes COA-derived UI."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _refresh_inbox(self):")
    end = text.index("    def _set_main_tab_index(self, index: int) -> None:", start)
    chunk = text[start:end]
    assert chunk.count("self._db.list_documents()") == 1
    assert chunk.count("self._inbox.populate(docs)") == 1
    assert chunk.count("self._on_selection_changed()") == 1
    assert chunk.count("load_coa()") == 1
    assert chunk.count("self._coa_db.display_list()") == 1
    assert chunk.count("self._detail.update_coa(coa_display)") == 1
    assert chunk.count("self._register_tab.refresh_coa_choices()") == 1
    assert "Called when the COA editor modifies the chart of accounts." in chunk
    assert (
        "# Refresh the dropdown list used in the document intake detail pane" in chunk
    )


def test_main_window_refresh_inbox_list_documents_before_populate_order() -> None:
    """``_refresh_inbox`` lists docs, populates inbox, then syncs selection to the detail pane."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _refresh_inbox(self):")
    end = text.index("    def _on_coa_changed(self):", start)
    chunk = text[start:end]
    assert chunk.index("docs = self._db.list_documents()") < chunk.index(
        "self._inbox.populate(docs)"
    )
    assert chunk.index("self._inbox.populate(docs)") < chunk.index(
        "self._on_selection_changed()"
    )


def test_main_window_on_coa_changed_load_coa_update_detail_then_register_order() -> None:
    """``_on_coa_changed`` reloads COA, refreshes the detail combo, then register choices."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_coa_changed(self):")
    end = text.index("    def _set_main_tab_index(self, index: int) -> None:", start)
    chunk = text[start:end]
    a = chunk.index("self._coa = load_coa()")
    b = chunk.index("coa_display = self._coa_db.display_list()")
    c = chunk.index("self._detail.update_coa(coa_display)")
    d = chunk.index("self._register_tab.refresh_coa_choices()")
    assert a < b < c < d


def test_main_window_set_main_tab_index_hasattr_bounds_then_set_current_order() -> None:
    """``_set_main_tab_index`` checks ``_tabs``, bounds, then changes the current tab."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _set_main_tab_index(self, index: int) -> None:")
    end = text.index("    def _sync_window_title(self) -> None:", start)
    chunk = text[start:end]
    h = chunk.index('if not hasattr(self, "_tabs"):')
    b = chunk.index("if index < 0 or index >= self._tabs.count():")
    s = chunk.index("self._tabs.setCurrentIndex(index)")
    assert h < b < s


def test_main_window_update_company_status_status_message_before_header_sync_title_order() -> None:
    """``_update_company_status`` updates the status bar and header before syncing the window title."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _update_company_status(self) -> None:")
    end = text.index("    def _rebuild_bank_related_tabs(self):", start)
    chunk = text[start:end]
    p = chunk.index(
        'p = getattr(self._bank_db, "_db_path", None) or self._db_path or ""'
    )
    assert "application_version()" in chunk
    assert "ProBooks+ai v" in chunk
    msg = chunk.index("self._status_bar.showMessage(")
    br = chunk.index("        if p:")
    syn = chunk.index("        self._sync_window_title()")
    assert p < msg < br < syn


def test_main_window_on_copy_company_database_path_empty_guard_before_clipboard_order() -> None:
    """``_on_copy_company_database_path`` shows the empty-path dialog before any clipboard write."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_copy_company_database_path(self) -> None:")
    end = text.index("    def _on_help_roadmap(self):", start)
    chunk = text[start:end]
    g = chunk.index("if not raw:")
    res = chunk.index("resolved = str(Path(raw).resolve())")
    clip = chunk.index("QApplication.clipboard().setText(resolved)")
    stat = chunk.index("self._status_bar.showMessage(")
    assert g < res < clip < stat


def test_main_window_on_help_roadmap_resolve_none_branch_before_open_url_order() -> None:
    """``_on_help_roadmap`` handles a missing file before attempting ``QDesktopServices.openUrl``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_help_roadmap(self):")
    end = text.index("    def _on_about(self):", start)
    chunk = text[start:end]
    r = chunk.index("path = resolve_local_roadmap_path()")
    none_br = chunk.index("if path is None:")
    url = chunk.index("url = QUrl.fromLocalFile(str(path))")
    open_br = chunk.index("if not QDesktopServices.openUrl(url):")
    assert r < none_br < url < open_br


def test_main_window_build_menu_bar_top_level_menu_comments_order() -> None:
    """``_build_menu_bar`` lists **File → View → Edit → Tools → Recon → Help** section comments in that order."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _build_menu_bar(self):")
    end = text.index("\n\n    # -- drag & drop on window", start)
    chunk = text[start:end]
    markers = (
        "        # File menu",
        "        # View menu",
        "        # Edit menu",
        "        # Tools menu",
        "        # Recon menu",
        "        # Help menu",
    )
    positions = [chunk.index(m) for m in markers]
    assert positions == sorted(positions)


def test_main_window_help_menu_qaction_definitions_order() -> None:
    """**Help** menu defines roadmap → intake → bank → register → business → more tabs, separator, then About."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("        # Help menu")
    end = text.index("\n\n    # -- drag & drop on window", start)
    chunk = text[start:end]
    names = (
        "act_roadmap = QAction",
        "act_intake_keys = QAction",
        "act_bank_import_keys = QAction",
        "act_register_keys = QAction",
        "act_business_keys = QAction",
        "act_more_tab_keys = QAction",
        "help_menu.addSeparator()",
        "act_about = QAction",
    )
    positions = [chunk.index(n) for n in names]
    assert positions == sorted(positions)


def test_main_window_file_menu_qaction_definitions_order() -> None:
    """**File** menu defines import → open/new company → backup/restore → copy path → save stubs, separator, exit."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("        # File menu")
    end = text.index("        # View menu", start)
    chunk = text[start:end]
    names = (
        "act_import_docs = QAction",
        "act_open_company = QAction",
        "act_new_company = QAction",
        "act_backup = QAction",
        "act_restore = QAction",
        "act_copy_db_path = QAction",
        "act_save = QAction",
        "act_save_as = QAction",
        "file_menu.addSeparator()",
        "act_exit = QAction",
    )
    positions = [chunk.index(n) for n in names]
    assert positions == sorted(positions)
    im = chunk.index("act_import_docs = QAction")
    op = chunk.index("act_open_company = QAction")
    assert "+ _BANK_IMPORT_VIEW_POINTER" in chunk[im:op]


def test_main_window_edit_menu_qaction_definitions_order() -> None:
    """**Edit** menu defines undo, redo, separator, then preferences (stub)."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("        # Edit menu")
    end = text.index("        # Tools menu", start)
    chunk = text[start:end]
    u = chunk.index("act_undo = QAction")
    r = chunk.index("act_redo = QAction")
    sep = chunk.index("edit_menu.addSeparator()")
    p = chunk.index("act_prefs = QAction")
    assert u < r < sep < p


def test_main_window_tools_menu_invoice_and_recon_menu_has_register_submenus() -> None:
    """**Tools** has Invoice; **Recon** groups bank register actions under five submenus."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("        # Tools menu")
    end = text.index("        # Help menu", start)
    chunk = text[start:end]
    assert chunk.count("tools_menu = mb.addMenu(\"&Tools\")") == 1
    assert chunk.count("recon_menu = mb.addMenu(\"&Recon\")") == 1
    assert chunk.count("tools_menu.addMenu(") == 0
    assert chunk.count("recon_menu.addMenu(") == 5
    assert "act_tools_invoice = QAction" in chunk
    assert "triggered.connect(self._on_tools_invoice)" in chunk
    assert "act_tools = QAction" not in chunk


def test_main_window_rebuild_bank_tab_specs_title_order() -> None:
    """``_rebuild_bank_related_tabs`` keeps **tab_specs** titles Bank → register → COA → reports → journal → business → audit."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("        tab_specs = [")
    end = text.index("        for i, (title, widget) in enumerate(tab_specs, start=1):", start)
    chunk = text[start:end]
    titles = (
        '("🏦  Bank Import"',
        '("📒  Bank register"',
        '("📊  Chart of Accounts"',
        '("📈  Reports"',
        '("📗  Journal"',
        '("🧾  Business"',
        '("📜  Audit log"',
    )
    positions = [chunk.index(t) for t in titles]
    assert positions == sorted(positions)
    assert "after_stmt_match_sync=self._focus_bank_register_tab" in chunk


def test_main_window_build_ui_wires_stmt_match_sync_focus_register() -> None:
    """``MainWindow`` passes ``after_stmt_match_sync`` into ``BankImportTab`` (build + rebuild) and defines ``_focus_bank_register_tab``."""
    text = _MAIN.read_text(encoding="utf-8")
    assert "def _focus_bank_register_tab(self)" in text
    assert text.count("after_stmt_match_sync=self._focus_bank_register_tab") == 2
    assert "Stmt match updated on Bank register" in text
    assert "line-reconciliation grid" in text
    assert "_STMT_MATCH_SYNC_STATUS_MS = 8000" in text
    focus_body = text.split("def _focus_bank_register_tab", 1)[1].split(
        "def _sync_window_title", 1
    )[0]
    assert "_STMT_MATCH_SYNC_STATUS_MS" in focus_body
    assert "QTimer.singleShot" in focus_body
    assert "self._update_company_status" in focus_body


def test_main_window_build_menu_bar_wires_all_action_triggers() -> None:
    """Every enabled menu ``QAction`` wires ``triggered.connect`` (28 wired; 5 disabled stubs)."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _build_menu_bar(self):")
    end = text.index("    # -- drag & drop on window", start)
    chunk = text[start:end]
    assert chunk.count("QAction(") == 33
    assert chunk.count(".triggered.connect(") == 28
    assert (
        chunk.count(
            "lambda checked=False, i=idx: self._set_main_tab_index(i)"
        )
        == 1
    )
    assert chunk.count("act_exit.triggered.connect(self.close)") == 1


def test_main_window_on_copy_company_database_path_clipboard_or_missing_dialog() -> None:
    """``_on_copy_company_database_path`` copies a resolved path or explains when none is set."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_copy_company_database_path(self) -> None:")
    end = text.index("    def _on_help_roadmap(self):", start)
    chunk = text[start:end]
    assert chunk.count("getattr(self._bank_db, \"_db_path\", None) or self._db_path or \"\"") == 1
    assert chunk.count('"Copy path"') == 1
    assert "No company database path is available." in chunk
    assert (
        'ok_tip="Open or create a company first (File menu); then File → Backup / probooks backup (probooks.backup) applies."'
        in chunk
    )
    assert chunk.count("QApplication.clipboard().setText(resolved)") == 1
    assert chunk.count("str(Path(raw).resolve())") == 1
    assert "Copied path:" in chunk
    assert ", 6000" in chunk


def test_main_window_on_help_roadmap_opens_local_md_or_warns() -> None:
    """``_on_help_roadmap`` resolves ROADMAP.md, opens it, or shows information/warning dialogs."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_help_roadmap(self):")
    end = text.index("    def _on_about(self):", start)
    chunk = text[start:end]
    assert chunk.count("resolve_local_roadmap_path()") == 1
    assert chunk.count("if path is None:") == 1
    assert "docs/ROADMAP.md" in chunk
    assert chunk.count("QUrl.fromLocalFile(str(path))") == 1
    assert chunk.count("QDesktopServices.openUrl(url)") == 1
    assert chunk.count("if not QDesktopServices.openUrl(url):") == 1
    assert "Unable to open the file" in chunk
    assert chunk.count("message_box_warning_ok(") == 1
    assert chunk.count('"Product roadmap"') == 2
    assert (
        'ok_tip="Close; open ROADMAP.md from the repo in your editor if you are developing."'
        in chunk
    )
    assert (
        'ok_tip="Close; open the path in Explorer or associate a Markdown viewer."'
        in chunk
    )


def test_main_window_on_about_shows_branded_version_dialog() -> None:
    """``_on_about`` uses ``message_box_about_ok`` with ProBooks+ai branding."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_about(self):")
    end = text.index("    def _on_import(self):", start)
    chunk = text[start:end]
    assert chunk.count("message_box_about_ok(") == 1
    assert chunk.count("application_version()") == 1
    assert chunk.count('"About ProBooks+ai"') == 1
    assert chunk.count("<b>ProBooks+ai</b>") == 1
    assert "AI-powered bookkeeping for small business." in chunk
    assert "Keyboard shortcuts are summarized under <b>Help</b>." in chunk
    assert "\\u00a9 2026 ProBooks+ai" in chunk
    assert (
        'ok_tip="Close; Help lists shortcuts (including UTF-8 BOM CSV for Excel); "'
        in chunk
        and "Bank Import covers AI line reconciliation" in chunk
        and 'File → Backup/Restore uses probooks.backup (same as CLI)."' in chunk
    )


def test_main_window_set_tab_sync_title_and_company_status_helpers() -> None:
    """``_set_main_tab_index`` guards on ``_tabs``; title/status helpers use bank path and version."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _set_main_tab_index(self, index: int) -> None:")
    end = text.index("    def _rebuild_bank_related_tabs(self):", start)
    chunk = text[start:end]
    assert chunk.count('if not hasattr(self, "_tabs"):') == 1
    assert chunk.count("if index < 0 or index >= self._tabs.count():") == 1
    assert chunk.count("self._tabs.setCurrentIndex(index)") == 1
    assert chunk.count("self._tabs.count()") == 1
    assert chunk.count("application_version()") == 2
    assert chunk.count("self.setWindowTitle(") == 2
    assert chunk.count("ProBooks+ai –") == 2
    assert chunk.count("self._sync_window_title()") == 1
    assert chunk.count("self._status_bar.showMessage(") == 2
    assert "File → Backup copies this .db." in chunk
    assert chunk.count("self._header.set_company_name(") == 2
    assert 'self._header.set_company_name("No company file")' in chunk
    assert 'self.setWindowTitle(f"ProBooks+ai – Desktop v{ver}")' in chunk
    assert chunk.count("escape_ampersand_for_qt(Path(p).name)") == 1
    assert chunk.count("self._header.set_company_name(Path(p).name)") == 1
    assert 'f"Company: {p}  \\u2013  drag & drop or Import;' in chunk
    assert "Bank Import (Ctrl+2)" in chunk


def test_main_window_sync_window_title_includes_company_name_or_desktop_only() -> None:
    """``_sync_window_title`` mirrors bank/db path into the window caption with escaped file name."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _sync_window_title(self) -> None:")
    end = text.index("    def _update_company_status(self) -> None:", start)
    chunk = text[start:end]
    assert chunk.count("application_version()") == 1
    assert (
        chunk.count('getattr(self._bank_db, "_db_path", None) or self._db_path or ""')
        == 1
    )
    assert chunk.count("if p:") == 1
    assert chunk.count("self.setWindowTitle(") == 2
    assert chunk.count("escape_ampersand_for_qt(Path(p).name)") == 1
    assert "ProBooks+ai –" in chunk
    assert "Desktop v{ver}" in chunk


def test_main_window_drag_drop_handlers_follow_menu_bar() -> None:
    """``MainWindow`` implements window-level drag/drop after ``_build_menu_bar`` (``setAcceptDrops``)."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    # -- drag & drop on window")
    end = text.index("    # -- slots", start)
    chunk = text[start:end]
    assert chunk.count("def dragEnterEvent(") == 1
    assert chunk.count("def dropEvent(") == 1
    assert "event.mimeData().hasUrls()" in chunk
    assert "event.acceptProposedAction()" in chunk
    assert "event.ignore()" not in chunk
    assert "self._import_files(paths)" in chunk


def test_main_window_drop_event_maps_local_urls_before_import() -> None:
    """Main-window ``dropEvent`` keeps only local file URLs, then calls ``_import_files``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    # -- drag & drop on window")
    de = text.index("    def dropEvent(self, event: QDropEvent):", start)
    end = text.index("    # -- slots", start)
    chunk = text[de:end]
    assert "u.toLocalFile()" in chunk
    assert "u.isLocalFile()" in chunk
    assert chunk.count("if paths:") == 1
    assert chunk.count("self._import_files(paths)") == 1


def test_main_window_drag_enter_event_def_before_drop_event_def() -> None:
    """Window-level DnD declares ``dragEnterEvent`` before ``dropEvent`` (same section as ``setAcceptDrops``)."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    # -- drag & drop on window")
    end = text.index("    # -- slots", start)
    chunk = text[start:end]
    assert chunk.index("    def dragEnterEvent(self, event: QDragEnterEvent):") < chunk.index(
        "    def dropEvent(self, event: QDropEvent):"
    )


def test_main_window_build_ui_instantiates_core_tab_widgets_once_each() -> None:
    """``_build_ui`` wires one header, intake split, detail pane, and each main-tab class."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("def _build_ui(self):")
    end = text.index("def _build_menu_bar", start)
    chunk = text[start:end]
    assert chunk.count("AppHeaderWidget()") == 1
    assert chunk.count("QSplitter(") == 1
    assert chunk.count("InboxWidget()") == 1
    assert chunk.count("coa_display_list(") == 1
    assert chunk.count("DetailPane(") == 1
    assert chunk.count("BankImportTab(") == 1
    assert chunk.count("RegisterTab(") == 1
    assert chunk.count("COATab(") == 1
    assert chunk.count("ReportsTab(") == 1
    assert chunk.count("JournalTab(") == 1
    assert chunk.count("BusinessHub(") == 1
    assert chunk.count("AuditTab(") == 1
    assert chunk.count("self._bank_tab = BankImportTab(") == 1
    assert chunk.count("self._register_tab = RegisterTab(") == 1
    assert chunk.count("self._coa_tab = COATab(") == 1


def test_main_window_build_ui_bank_register_coa_tabs_receive_expected_db_deps() -> None:
    """Bank Import, Register, and COA tabs are constructed with ``BankDatabase`` / ``COADatabase`` / ``GLDatabase`` wiring."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("        # ── Tab 2: Bank Import")
    end = text.index("        # ── Tabs 5–7:", start)
    chunk = text[start:end]
    assert chunk.count("register_tab=self._register_tab") == 1
    assert chunk.count("after_stmt_match_sync=self._focus_bank_register_tab") == 1
    assert chunk.count("RegisterTab(self._bank_db, self._coa_db, self._gl_db)") == 1
    assert chunk.count("COATab(self._coa_db)") == 1


def test_main_window_build_ui_tabs_2_through_4_ctor_before_add_tab_coa_signal_before_add_tab_order() -> None:
    """Tabs 2–4 construct each widget before ``addTab``; COA tab wires ``coaChanged`` before ``addTab``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("        # ── Tab 2: Bank Import")
    end = text.index("        # ── Tabs 5–7:", start)
    chunk = text[start:end]
    r_ctor = chunk.index(
        "self._register_tab = RegisterTab(self._bank_db, self._coa_db, self._gl_db)"
    )
    b_ctor = chunk.index("self._bank_tab = BankImportTab(")
    b_tab = chunk.index('self._tabs.addTab(self._bank_tab, "🏦  Bank Import")')
    r_tab = chunk.index('self._tabs.addTab(self._register_tab, "📒  Bank register")')
    c_ctor = chunk.index("self._coa_tab = COATab(self._coa_db)")
    c_sig = chunk.index("self._coa_tab.coaChanged.connect(self._on_coa_changed)")
    c_tab = chunk.index('self._tabs.addTab(self._coa_tab, "📊  Chart of Accounts")')
    assert r_ctor < b_ctor < b_tab < r_tab < c_ctor < c_sig < c_tab


def test_main_window_build_ui_reports_journal_business_audit_use_shared_bank_connection() -> None:
    """Reports, Journal, Business, and Audit tabs are built from ``self._bank_db._conn`` (shared GL SQLite)."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("        # ── Tabs 5–7:")
    end = text.index("        main_tab_bar = self._tabs.tabBar()", start)
    chunk = text[start:end]
    assert chunk.count("ReportsTab(self._bank_db._conn)") == 1
    assert chunk.count("JournalTab(self._bank_db._conn)") == 1
    assert chunk.count("BusinessHub(self._bank_db._conn)") == 1
    assert chunk.count("AuditTab(self._bank_db._conn)") == 1


def test_main_window_build_ui_wires_tabs_container_inbox_and_detail_signals() -> None:
    """``_build_ui`` attaches ``QTabWidget`` to the container and wires Intake/COA/Detail slots."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("def _build_ui(self):")
    end = text.index("def _build_menu_bar", start)
    chunk = text[start:end]
    assert chunk.count("self._tabs = QTabWidget()") == 1
    assert chunk.count("container = QWidget()") == 1
    assert chunk.count("container_layout.setContentsMargins(0, 0, 0, 0)") == 1
    assert chunk.count("container_layout.setSpacing(0)") == 1
    assert chunk.count("container_layout.addWidget(self._header)") == 1
    assert chunk.count("container_layout.addWidget(self._tabs)") == 1
    assert chunk.index("container_layout.addWidget(self._header)") < chunk.index(
        "container_layout.addWidget(self._tabs)"
    )
    assert chunk.count("self._coa_tab.coaChanged.connect(self._on_coa_changed)") == 1
    assert chunk.count("self._inbox.filesDropped.connect(self._on_files_dropped)") == 1
    assert chunk.count(
        "self._inbox.itemSelectionChanged.connect(self._on_selection_changed)"
    ) == 1
    assert chunk.count("self._detail.runAI.connect(self._on_run_ai)") == 1
    assert chunk.count("self._detail.approve.connect(self._on_approve)") == 1
    assert chunk.count("self._detail.markPosted.connect(self._on_mark_posted)") == 1
    assert chunk.count("self._detail.reject.connect(self._on_reject)") == 1


def test_main_window_build_ui_detail_pane_signal_connect_run_approve_post_reject_order() -> None:
    """Intake ``DetailPane`` slots wire **Run AI → Approve → Mark Posted → Reject** in source order."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("def _build_ui(self):")
    end = text.index("def _build_menu_bar", start)
    chunk = text[start:end]
    r = chunk.index("self._detail.runAI.connect(self._on_run_ai)")
    a = chunk.index("self._detail.approve.connect(self._on_approve)")
    p = chunk.index("self._detail.markPosted.connect(self._on_mark_posted)")
    j = chunk.index("self._detail.reject.connect(self._on_reject)")
    assert r < a < p < j


def test_desktop_main_detail_pane_extracted_fields_form_row_order() -> None:
    """``DetailPane`` **Extracted Fields** ``QFormLayout`` rows follow vendor → … → notes."""
    text = _MAIN.read_text(encoding="utf-8")
    fs = text.index("        form = QFormLayout(fields_group)")
    fe = text.index("        layout.addWidget(fields_group)", fs)
    form = text[fs:fe]
    rows = (
        'form.addRow("Vendor / Customer:", self._f_vendor)',
        'form.addRow("Doc Type:", self._f_doctype)',
        'form.addRow("Invoice #:", self._f_inv_num)',
        'form.addRow("Date:", self._f_date)',
        'form.addRow("Due Date:", self._f_due_date)',
        'form.addRow("Subtotal:", self._f_subtotal)',
        'form.addRow("Tax:", self._f_tax)',
        'form.addRow("Total:", self._f_total)',
        'form.addRow("Currency:", self._f_currency)',
        'form.addRow("Notes:", self._f_notes)',
    )
    positions = [form.index(r) for r in rows]
    assert positions == sorted(positions)


def test_desktop_main_detail_pane_extracted_fields_group_tooltip_form_before_vendor_widget_order() -> None:
    """``DetailPane.__init__`` builds **Extracted Fields** group, tooltip, ``QFormLayout``, then the vendor field."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index('        fields_group = QGroupBox("Extracted Fields")')
    end = text.index("        self._f_vendor   = QLineEdit()", start)
    chunk = text[start:end]
    fg = chunk.index('        fields_group = QGroupBox("Extracted Fields")')
    tt = chunk.index("        fields_group.setToolTip(")
    frm = chunk.index("        form = QFormLayout(fields_group)")
    assert fg < tt < frm


def test_desktop_main_detail_pane_categorisation_form_row_order() -> None:
    """``DetailPane`` **Categorisation** form rows follow COA → tax → confidence → rationale."""
    text = _MAIN.read_text(encoding="utf-8")
    cs = text.index("        cat_layout = QFormLayout(cat_group)")
    ce = text.index("        layout.addWidget(cat_group)", cs)
    chunk = text[cs:ce]
    rows = (
        'cat_layout.addRow("COA Account:", self._f_coa)',
        'cat_layout.addRow("Tax Category:", self._f_tax_cat)',
        'cat_layout.addRow("AI Confidence:", self._f_confidence)',
        'cat_layout.addRow("Rationale:", self._lbl_rationale)',
    )
    positions = [chunk.index(r) for r in rows]
    assert positions == sorted(positions)


def test_desktop_main_detail_pane_categorisation_group_tooltip_layout_combo_fill_editable_order() -> None:
    """Categorisation: ``QGroupBox`` → tooltip → ``QFormLayout`` → COA combo → fill → ``setEditable``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index('        cat_group = QGroupBox("Categorisation Suggestions")')
    end = text.index("        self._f_coa.setToolTip(", start)
    chunk = text[start:end]
    cg = chunk.index('        cat_group = QGroupBox("Categorisation Suggestions")')
    tt = chunk.index("        cat_group.setToolTip(")
    cl = chunk.index("        cat_layout = QFormLayout(cat_group)")
    fc = chunk.index("        self._f_coa      = QComboBox()")
    fil = chunk.index("        self._fill_coa_combo(coa_list)")
    ed = chunk.index("        self._f_coa.setEditable(True)")
    assert cg < tt < cl < fc < fil < ed


def test_desktop_main_detail_pane_action_buttons_toolbar_order() -> None:
    """Detail action buttons are **Run AI → Approve → Mark Posted → Reject** (define, loop, style, slots)."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("        # -- Action buttons --------------------------------------------------")
    end = text.index("        self._set_buttons_enabled(False)", start)
    chunk = text[start:end]
    br = chunk.index("self._btn_run")
    ba = chunk.index("self._btn_approve")
    bp = chunk.index("self._btn_post")
    bj = chunk.index("self._btn_reject")
    assert br < ba < bp < bj
    assert chunk.index("(self._btn_run, self._btn_approve, self._btn_post, self._btn_reject)") > bj
    cr = chunk.index("self._btn_run.clicked.connect(self._on_run_ai)")
    ca = chunk.index("self._btn_approve.clicked.connect(self._on_approve)")
    cp = chunk.index("self._btn_post.clicked.connect(self._on_post)")
    cj = chunk.index("self._btn_reject.clicked.connect(self._on_reject)")
    assert cr < ca < cp < cj


def test_inbox_widget_context_menu_keyboard_shortcuts_before_copy_row() -> None:
    """Inbox context menu adds **Keyboard shortcuts…** before **Copy row** (when a cell is selected)."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_context_menu(self, pos):")
    end = text.index("    # -- drag & drop ---------------------------------------------------------", start)
    chunk = text[start:end]
    assert chunk.index('"Keyboard shortcuts…"') < chunk.index('"Copy row"')
    assert "Bank import pointers" in chunk


def test_menu_action_tip_helper_sets_matching_status_and_hover_text() -> None:
    """``_menu_action_tip`` must keep status bar and QAction hover text in lockstep."""
    text = _MAIN.read_text(encoding="utf-8")
    assert (
        "    act.setStatusTip(tip)\n    act.setToolTip(tip)" in text
    ), "_menu_action_tip should call setStatusTip then setToolTip with the same tip"


def test_menu_action_tip_helper_docstring_mentions_status_bar() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("def _menu_action_tip(act: QAction, tip: str) -> None:")
    end = text.index("class MainWindow(QMainWindow):", start)
    chunk = text[start:end]
    assert "status-bar hint" in chunk
    assert "hover tooltip" in chunk


def test_tools_menu_has_no_disabled_placeholder_action() -> None:
    """**Tools** has Invoice; **Recon** holds register actions (no disabled **(Coming soon)** stub)."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("# Tools menu")
    end = text.index("# Help menu", start)
    chunk = text[start:end]
    assert 'act_tools = QAction("(Coming soon)", self)' not in chunk
    assert "tools_register_add_transaction" in chunk


def test_help_menu_roadmap_about_seven_actions_and_separator() -> None:
    """**Help** menu lists seven actions, one separator before About, and wires roadmap + about slots."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("# Help menu")
    end = text.index("    # -- drag & drop on window", start)
    chunk = text[start:end]
    assert chunk.count("help_menu.addAction(") == 7
    assert chunk.count("help_menu.addSeparator()") == 1
    assert chunk.count("act_roadmap.triggered.connect(self._on_help_roadmap)") == 1
    assert chunk.count("act_about.triggered.connect(self._on_about)") == 1
    roadmap_ln = next(ln for ln in chunk.splitlines() if "act_roadmap = QAction(" in ln)
    assert "Product &roadmap (local file)" in roadmap_ln
    assert "\\u2026" in roadmap_ln or "\u2026" in roadmap_ln or "…" in roadmap_ln
    assert "Open docs/ROADMAP.md" in chunk


def test_help_menu_shortcut_dialogs_use_show_function_lambdas() -> None:
    """Help → keyboard shortcut items still delegate to the shared ``show_*_shortcuts_dialog(self)`` helpers."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("# Help menu")
    end = text.index("    # -- drag & drop on window", start)
    chunk = text[start:end]
    assert "lambda: show_document_intake_keyboard_shortcuts_dialog(self)" in chunk
    assert "lambda: show_bank_import_keyboard_shortcuts_dialog(self)" in chunk
    assert "lambda: show_register_keyboard_shortcuts_dialog(self)" in chunk
    assert "lambda: show_business_keyboard_shortcuts_dialog(self)" in chunk
    assert "lambda: show_more_main_tabs_keyboard_shortcuts_dialog(self)" in chunk


def test_main_menu_bar_sets_status_tips_for_shortcut_actions() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    assert "def _menu_action_tip" in text
    assert "act.setStatusTip(tip)" in text
    start = text.index("def _build_menu_bar")
    end = text.index("def dragEnterEvent", start)
    chunk = text[start:end]
    assert ".setStatusTip(" not in chunk
    assert ".setToolTip(" not in chunk, (
        "_build_menu_bar must not call setToolTip on QActions; use _menu_action_tip only"
    )
    n_qa = chunk.count("QAction(")
    n_tip = chunk.count("_menu_action_tip(")
    per_menu_add = (
        chunk.count("file_menu.addAction("),
        chunk.count("view_menu.addAction("),
        chunk.count("edit_menu.addAction("),
        chunk.count("tools_menu.addAction("),
        chunk.count("help_menu.addAction("),
    )
    assert per_menu_add == (9, 1, 3, 1, 7), (
        f"expected top-level addAction counts (File,View,Edit,Tools,Help)=(9,1,3,1,7); "
        f"Recon register actions use 12 submenu addAction (counted separately); "
        f"got {per_menu_add}"
    )
    n_reg_sub_add = (
        chunk.count("m_reg_actions.addAction(")
        + chunk.count("m_reg_recon.addAction(")
        + chunk.count("m_reg_attach.addAction(")
        + chunk.count("m_reg_txn.addAction(")
        + chunk.count("m_reg_flags.addAction(")
    )
    assert n_reg_sub_add == 12
    n_add = sum(per_menu_add) + n_reg_sub_add
    assert n_qa == n_tip == n_add == 33, (
        f"expected 33 menu QActions, _menu_action_tip calls, and *.addAction( calls "
        f"(QAction={n_qa}, _menu_action_tip={n_tip}, addAction={n_add})"
    )
    n_dis = chunk.count("setEnabled(False)")
    assert n_dis == 5, (
        f"expected 5 disabled menu actions (Save, Save As, Undo, Redo, Prefs); "
        f"got {n_dis}"
    )
    n_trig = chunk.count(".triggered.connect(")
    assert n_trig == n_qa - n_dis, (
        f"each enabled menu QAction should wire .triggered.connect( "
        f"(QAction={n_qa}, setEnabled(False)={n_dis}, .triggered.connect={n_trig})"
    )
    assert chunk.count(".addSeparator()") == 3, (
        "expected file_menu, edit_menu, and help_menu each to call addSeparator() once"
    )
    assert chunk.count("self.menuBar()") == 1
    assert chunk.count("mb.addMenu(") == 6, (
        "expected six top-level menus (File, View, Edit, Tools, Recon, Help)"
    )
    n_scut = chunk.count(".setShortcut(")
    assert n_scut == 8, (
        f"expected 8 menu bar .setShortcut( (5 File + View loop + Undo/Redo); got {n_scut}"
    )
    n_sctx = chunk.count(".setShortcutContext(")
    assert n_sctx == 2, (
        f"expected 2 .setShortcutContext(Qt.ApplicationShortcut) (copy path, View tabs); "
        f"got {n_sctx}"
    )
    assert "\n            act_import_docs,\n" in chunk
    assert "\n            act_open_company,\n" in chunk
    assert "\n            act_copy_db_path,\n" in chunk
    assert "_menu_action_tip(\n                act, f" in chunk
    ex = chunk.index("act_exit = QAction")
    assert "_menu_action_tip(" in chunk[ex : ex + 400]
    assert "\n            act_intake_keys,\n" in chunk
    assert "\n            act_more_tab_keys,\n" in chunk
    assert chunk.count("_view_tab_tip_suffix") == 2
    assert "_view_tab_tip_extra" in chunk
    assert "Document Intake; bank CSV/PDF and line reconciliation on Ctrl+2" in chunk
    assert "AI line reconciliation and Stmt match sync" in chunk
    assert 'f"Show this main tab ({sc}).{extra}{_view_tab_tip_suffix}"' in chunk


def test_main_window_build_menu_bar_menu_bar_before_file_menu_order() -> None:
    """``_build_menu_bar`` calls ``menuBar()`` before adding the **File** menu."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _build_menu_bar(self):")
    end = text.index("\n\n    # -- drag & drop on window", start)
    chunk = text[start:end]
    mb = chunk.index("mb = self.menuBar()")
    fm = chunk.index('file_menu = mb.addMenu("&File")')
    assert mb < fm


def test_main_help_menu_wires_document_intake_shortcuts_dialog() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    assert "show_document_intake_keyboard_shortcuts_dialog" in text
    assert "def _document_intake_keyboard_shortcuts_help_text" in text
    assert "Document &intake shortcuts" in text
    assert "Ctrl+7 Business" in text and "Ctrl+8 Audit log" in text
    assert "all tabs share the open" in text
    assert "Help → Business shortcuts" in text
    assert "Import documents" in text and "Ctrl+O" in text
    assert "status bar" in text
    assert "each menu item" in text
    assert "File, View, Edit, Tools, Recon, Help" in text
    assert "Detail pane:" in text


def test_main_window_view_menu_enumerates_ctrl_one_through_eight() -> None:
    """View menu builds eight tab actions with Ctrl+1 … Ctrl+8 in a fixed order."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("# View menu — tab shortcuts")
    end = text.index("# Edit menu", start)
    chunk = text[start:end]
    for n in range(1, 9):
        assert f'("Ctrl+{n}"' in chunk
    tuples = (
        '("Ctrl+1", "Document &Intake")',
        '("Ctrl+2", "&Bank Import")',
        '("Ctrl+3", "&Register")',
        '("Ctrl+4", "Chart of &Accounts")',
        '("Ctrl+5", "&Reports")',
        '("Ctrl+6", "&Journal")',
        '("Ctrl+7", "&Business")',
        '("Ctrl+8", "A&udit log")',
    )
    for line in tuples:
        assert line in chunk
    positions = [chunk.index(t) for t in tuples]
    assert positions == sorted(positions)
    assert chunk.count("act.setShortcutContext(Qt.ApplicationShortcut)") == 1


def test_main_window_main_tab_bar_set_tab_tooltip_index_order() -> None:
    """``main_tab_bar.setTabToolTip`` uses indices **0–7** in ascending order (matches tab strip)."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("main_tab_bar = self._tabs.tabBar()")
    end = text.index("container_layout.addWidget(self._tabs)", start)
    chunk = text[start:end]
    prev = -1
    for i in range(8):
        needle = f"main_tab_bar.setTabToolTip(\n            {i},"
        pos = chunk.index(needle)
        assert pos > prev
        prev = pos


def test_inbox_widget_context_menu_includes_keyboard_shortcuts_help() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    assert "class InboxWidget" in text
    assert "Keyboard shortcuts…" in text
    assert "show_document_intake_keyboard_shortcuts_dialog(self)" in text
    start = text.index("def _on_context_menu(self, pos):")
    end = text.index("def dragEnterEvent", start)
    chunk = text[start:end]
    assert "act_keys.setToolTip" in chunk
    assert "act_copy.setToolTip" in chunk
    assert "+ VIEW_BANK_REGISTER_KEYS_TOOLTIP" in chunk
    assert chunk.count("+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX") >= 2


def test_inbox_widget_context_menu_skips_copy_row_when_no_cell() -> None:
    """Context menu: ``indexAt``, empty-cell early ``exec``, else separator + Copy row; both use viewport global pos."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_context_menu(self, pos):")
    end = text.index("    # -- drag & drop", start)
    chunk = text[start:end]
    assert chunk.count("m = QMenu(self)") == 1
    assert chunk.count("Keyboard shortcuts") == 1
    assert chunk.count("self.indexAt(pos)") == 1
    assert chunk.count("if not idx.isValid():") == 1
    assert chunk.count("m.addSeparator()") == 1
    assert chunk.count('m.addAction("Copy row"') == 1
    assert chunk.count("self.viewport().mapToGlobal(pos)") == 2
    assert chunk.count("m.exec(self.viewport().mapToGlobal(pos))") == 2


def test_inbox_widget_context_menu_actions_and_branches_source_order() -> None:
    """``_on_context_menu`` builds the menu, shortcuts action + tip, invalid early exit, then copy + final ``exec``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_context_menu(self, pos):")
    end = text.index("    # -- drag & drop", start)
    chunk = text[start:end]
    ia = chunk.index("idx = self.indexAt(pos)")
    mn = chunk.index("m = QMenu(self)")
    ka = chunk.index("act_keys = m.addAction(")
    kt = chunk.index("act_keys.setToolTip(")
    iv = chunk.index("if not idx.isValid():")
    rr = chunk.index("row = idx.row()")
    sp = chunk.index("m.addSeparator()")
    ca = chunk.index('act_copy = m.addAction("Copy row"')
    ct = chunk.index("act_copy.setToolTip(")
    ex0 = chunk.index("m.exec(self.viewport().mapToGlobal(pos))")
    ex1 = chunk.rindex("m.exec(self.viewport().mapToGlobal(pos))")
    assert ia < mn < ka < kt < iv < rr
    assert iv < ex0 < rr
    assert rr < sp < ca < ct < ex1


def test_inbox_widget_context_menu_copy_row_binds_partial_tsv_helper() -> None:
    """Inbox **Copy row** uses ``functools.partial`` with ``copy_table_row_as_tsv``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class InboxWidget(QTableWidget):")
    end = text.index("class DetailPane(QScrollArea):", start)
    chunk = text[start:end]
    assert chunk.count("partial(copy_table_row_as_tsv, self, row)") == 1


def test_desktop_main_show_intake_shortcuts_dialog_delegates_to_message_box() -> None:
    """``show_document_intake_keyboard_shortcuts_dialog`` is a thin ``message_box_information_ok`` wrapper."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index(
        "def show_document_intake_keyboard_shortcuts_dialog(parent: QWidget) -> None:"
    )
    end = text.index("\n\n# Accepted MIME types / file extensions", start)
    chunk = text[start:end]
    assert chunk.count("message_box_information_ok(") == 1
    assert chunk.count('"Document intake shortcuts"') == 1
    assert chunk.count("_document_intake_keyboard_shortcuts_help_text()") == 1
    assert (
        'ok_tip="Close; shortcuts apply when Document Intake has focus. "' in chunk
    )
    assert "Ctrl+2 Bank Import" in chunk
    assert "Ctrl+3 Register" in chunk
    assert "Company .db: File → Backup / Restore (probooks.backup)." in chunk


def test_desktop_main_show_intake_shortcuts_dialog_title_before_help_text_call_order() -> None:
    """Dialog title string appears before ``_document_intake_keyboard_shortcuts_help_text()`` in the call."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index(
        "def show_document_intake_keyboard_shortcuts_dialog(parent: QWidget) -> None:"
    )
    end = text.index("\n\n# Accepted MIME types / file extensions", start)
    chunk = text[start:end]
    tit = chunk.index('"Document intake shortcuts"')
    hel = chunk.index("_document_intake_keyboard_shortcuts_help_text()")
    assert tit < hel


def test_desktop_main_document_intake_shortcuts_help_text_sections() -> None:
    """Intake shortcuts help lists File/View/Bank sections and backup cross-links."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("def _document_intake_keyboard_shortcuts_help_text() -> str:")
    end = text.index(
        "def show_document_intake_keyboard_shortcuts_dialog(parent: QWidget) -> None:", start
    )
    chunk = text[start:end]
    assert "Plain text for **Help → Document intake shortcuts" in chunk
    assert "aligned with **F5**" in chunk and "InboxWidget" in chunk
    assert chunk.count("return (") == 1
    assert "File menu:" in chunk
    assert "View menu:" in chunk
    assert "Bank workflows:" in chunk
    assert "Help → More tab shortcuts" in chunk
    assert "Help → Business shortcuts" in chunk
    assert chunk.count("probooks.backup") >= 2
    assert "Keyboard shortcuts…" in chunk
    assert "UTF-8 with BOM for Excel" in chunk
    assert "reconciliation report and line-compare" in chunk
    assert "Bank Import Import CSV" in chunk and "optional BOM" in chunk
    assert "batch preview, AI line reconciliation" in chunk
    assert "Hover Bank Import and Register in View for status tips" in chunk
    assert "**Recon** menu" in chunk and "Bank register" in chunk
    assert "**Tools** menu" in chunk and "Invoice" in chunk


def test_desktop_main_document_intake_help_text_file_view_bank_section_order() -> None:
    """Intake shortcuts help string orders **File** → **View**; **Business** precedes **Bank workflows**."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("def _document_intake_keyboard_shortcuts_help_text() -> str:")
    end = text.index(
        "def show_document_intake_keyboard_shortcuts_dialog(parent: QWidget) -> None:", start
    )
    chunk = text[start:end]
    f = chunk.index('"File menu:\\n"')
    v = chunk.index('"View menu:\\n"')
    b = chunk.index('"Bank workflows:\\n"')
    assert f < v < b
    bus = chunk.index('"Business:\\n"')
    assert bus < b


def test_desktop_main_intake_accepted_mimes_extensions_and_status_colors_alias() -> None:
    """Intake import filters use shared MIME/extension sets; status colours follow the theme."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("# Accepted MIME types / file extensions")
    end = text.index("INBOX_HEADER_COLOR = ", start)
    chunk = text[start:end]
    assert "ACCEPTED_MIMES = " in chunk
    assert "ACCEPTED_EXTENSIONS = " in chunk
    assert "application/pdf" in chunk
    assert "image/jpeg" in chunk
    assert "image/png" in chunk
    assert ".jpg" in chunk and ".jpeg" in chunk and ".png" in chunk
    assert "STATUS_COLORS = THEME_STATUS_COLORS" in chunk
    assert (
        'ACCEPTED_MIMES = {"application/pdf", "image/jpeg", "image/png"}' in chunk
    )
    assert (
        'ACCEPTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}' in chunk
    )


def test_desktop_main_accepted_mimes_extensions_status_colors_source_order() -> None:
    """Module-level intake filters declare **MIMES → EXTENSIONS → STATUS_COLORS** in that order."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("# Accepted MIME types / file extensions")
    end = text.index("INBOX_HEADER_COLOR = ", start)
    chunk = text[start:end]
    m = chunk.index("ACCEPTED_MIMES = ")
    e = chunk.index("ACCEPTED_EXTENSIONS = ")
    s = chunk.index("STATUS_COLORS = THEME_STATUS_COLORS")
    assert m < e < s


def test_desktop_main_inbox_header_color_and_placeholder_company_name() -> None:
    """Banner navy colour and default company label string live before the AI worker section."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("INBOX_HEADER_COLOR = ")
    end = text.index(
        "# ---------------------------------------------------------------------------\n# Background worker",
        start,
    )
    chunk = text[start:end]
    assert 'INBOX_HEADER_COLOR = "#1F3864"' in chunk
    assert 'COMPANY_NAME = "CHAVAN TRUCKING CORPORATION"' in chunk
    assert "placeholder" in chunk


def test_desktop_main_ai_worker_runs_extractor_and_categorizer_in_run() -> None:
    """``AIWorker`` loads ai modules in ``run``, emits ``finished`` or ``error``."""
    text = _MAIN.read_text(encoding="utf-8")
    bw = text.index("# ---------------------------------------------------------------------------\n# Background worker")
    start = text.index("class AIWorker(QThread):")
    assert bw < start
    assert "runs AI extraction off the UI thread" in text[bw:start]
    end = text.index("class InboxWidget(QTableWidget):", start)
    chunk = text[start:end]
    assert "finished = Signal(object, object)" in chunk
    assert "ExtractionResult" in chunk and "CategorySuggestions" in chunk
    assert "error    = Signal(str)" in chunk
    assert chunk.count("from ai.extractor import extract_document") == 1
    assert chunk.count("from ai.categorizer import suggest_categories") == 1
    assert chunk.count("extract_document(self._path, self._mimetype)") == 1
    assert chunk.count("suggest_categories(result, self._coa)") == 1
    assert chunk.count("self.finished.emit(result, suggestions)") == 1
    assert chunk.count("self.error.emit") == 2


def test_desktop_main_ai_worker_signal_declarations_order() -> None:
    """``AIWorker`` declares the ``finished`` signal before ``error`` in the class body."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class AIWorker(QThread):")
    end = text.index(
        "    def __init__(self, doc_id: int, path: str, mimetype: str, coa: list):",
        start,
    )
    chunk = text[start:end]
    assert chunk.index("finished = Signal(object, object)") < chunk.index(
        "error    = Signal(str)"
    )


def test_desktop_main_ai_worker_init_assigns_doc_path_mimetype_and_coa() -> None:
    """``AIWorker`` stores job inputs on the instance before ``run`` loads extractor/categorizer."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index(
        "    def __init__(self, doc_id: int, path: str, mimetype: str, coa: list):"
    )
    end = text.index("    def run(self):", start)
    chunk = text[start:end]
    assert chunk.count("super().__init__()") == 1
    assert chunk.count("self._doc_id  = doc_id") == 1
    assert chunk.count("self._path    = path") == 1
    assert chunk.count("self._mimetype = mimetype") == 1
    assert chunk.count("self._coa     = coa") == 1


def test_desktop_main_ai_worker_init_super_doc_path_mimetype_coa_assignment_order() -> None:
    """``AIWorker.__init__`` calls ``super`` then assigns ``_doc_id`` → ``_path`` → ``_mimetype`` → ``_coa``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index(
        "    def __init__(self, doc_id: int, path: str, mimetype: str, coa: list):"
    )
    end = text.index("    def run(self):", start)
    chunk = text[start:end]
    su = chunk.index("super().__init__()")
    d = chunk.index("self._doc_id  = doc_id")
    p = chunk.index("self._path    = path")
    m = chunk.index("self._mimetype = mimetype")
    c = chunk.index("self._coa     = coa")
    assert su < d < p < m < c


def test_desktop_main_ai_worker_run_extract_error_gate_suggest_finish_order() -> None:
    """``AIWorker.run`` extracts, checks ``result.error``, categorizes, then emits ``finished``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def run(self):", text.index("class AIWorker(QThread):"))
    end = text.index("class InboxWidget(QTableWidget):", start)
    chunk = text[start:end]
    ex = chunk.index("result = extract_document(self._path, self._mimetype)")
    er = chunk.index("if result.error:")
    sg = chunk.index("suggestions = suggest_categories(result, self._coa)")
    fn = chunk.index("self.finished.emit(result, suggestions)")
    assert ex < er < sg < fn


def test_desktop_main_ai_worker_run_try_imports_extractor_before_categorizer_order() -> None:
    """``AIWorker.run`` imports ``extract_document`` before ``suggest_categories`` inside the ``try`` block."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def run(self):", text.index("class AIWorker(QThread):"))
    end = text.index("class InboxWidget(QTableWidget):", start)
    chunk = text[start:end]
    imx = chunk.index("from ai.extractor import extract_document")
    imc = chunk.index("from ai.categorizer import suggest_categories")
    assert imx < imc


def test_desktop_main_ai_worker_run_error_paths_extractor_and_exception() -> None:
    """``AIWorker.run`` emits ``error`` when extraction fails or an unexpected exception escapes."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def run(self):", text.index("class AIWorker(QThread):"))
    end = text.index("class InboxWidget(QTableWidget):", start)
    chunk = text[start:end]
    assert chunk.count("if result.error:") == 1
    assert chunk.count("self.error.emit(result.error)") == 1
    assert "self.error.emit(result.error)\n                return" in chunk
    assert chunk.count("except Exception as exc:") == 1
    assert "noqa: BLE001" in chunk
    assert chunk.count("self.error.emit(str(exc))") == 1


def test_desktop_main_inbox_widget_drop_emits_paths_and_populate_sets_doc_ids() -> None:
    """``InboxWidget`` emits local paths on drop and stores document ids on items for selection."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class InboxWidget(QTableWidget):")
    end = text.index("class DetailPane(QScrollArea):", start)
    chunk = text[start:end]
    assert "Displays imported documents with their statuses." in chunk
    assert chunk.count("filesDropped = Signal(list)") == 1
    assert chunk.count("self.filesDropped.emit(paths)") == 1
    assert chunk.count("hasUrls()") >= 2
    assert chunk.count("IntSortTableItem(str(did), did)") == 1
    assert chunk.count("Qt.ItemDataRole.UserRole") >= 2
    assert chunk.count("def selected_doc_id(self) -> int | None:") == 1


def test_inbox_widget_class_docstring_mentions_context_menu_tooltips() -> None:
    """``InboxWidget`` module docstring notes context-menu tooltips for shortcuts and copy."""
    text = _MAIN.read_text(encoding="utf-8")
    iw = text.index("class InboxWidget(QTableWidget):")
    end = text.index("    COLUMNS = ", iw)
    head = text[iw:end]
    assert "Context menu" in head
    assert "Keyboard shortcuts" in head
    assert "Copy row" in head


def test_inbox_widget_columns_constant_before_init_definition_order() -> None:
    """``COLUMNS`` is defined on ``InboxWidget`` before ``__init__`` uses ``len(self.COLUMNS)``."""
    text = _MAIN.read_text(encoding="utf-8")
    iw = text.index("class InboxWidget(QTableWidget):")
    cols = text.index('    COLUMNS = ["#", "Filename", "Type", "Status", "Date"]', iw)
    init = text.index("    def __init__(self, parent=None):", iw)
    assert cols < init


def test_desktop_main_inbox_widget_columns_selection_dnd_and_sorting() -> None:
    """``InboxWidget`` uses fixed columns, row selection, no in-grid edit, drops, and sort toggles in populate."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index('    COLUMNS = ["#", "Filename", "Type", "Status", "Date"]')
    end = text.index("    def selected_doc_id(self) -> int | None:", start)
    chunk = text[start:end]
    assert chunk.count("setHorizontalHeaderLabels(self.COLUMNS)") == 1
    assert chunk.count("SelectionBehavior.SelectRows") == 1
    assert chunk.count("EditTrigger.NoEditTriggers") == 1
    assert chunk.count("setAcceptDrops(True)") == 1
    assert chunk.count("CustomContextMenu") == 1
    assert (
        chunk.count(
            "self.customContextMenuRequested.connect(self._on_context_menu)"
        )
        == 1
    )
    assert chunk.count("setSortingEnabled(") == 3


def test_inbox_widget_header_column_widths_and_stretch_policy() -> None:
    """Inbox grid: ``QTableWidget`` super, column widths, stretch policy, stripes, hidden row header."""
    text = _MAIN.read_text(encoding="utf-8")
    iw = text.index("class InboxWidget(QTableWidget):")
    start = text.index("    def __init__(self, parent=None):", iw)
    end = text.index("    def _on_context_menu(self, pos):", start)
    chunk = text[start:end]
    assert chunk.count("super().__init__(parent)") == 1
    assert chunk.count("setColumnCount(len(self.COLUMNS))") == 1
    assert chunk.count("setStretchLastSection(False)") == 1
    assert chunk.count("setDefaultSectionSize(110)") == 1
    assert chunk.count("setColumnWidth(0, 40)") == 1
    assert chunk.count("setColumnWidth(1, 220)") == 1
    assert chunk.count("setColumnWidth(2, 80)") == 1
    assert chunk.count("setColumnWidth(3, 110)") == 1
    assert chunk.count("setColumnWidth(4, 120)") == 1
    assert chunk.count("setAlternatingRowColors(True)") == 1
    assert chunk.count("verticalHeader().setVisible(False)") == 1


def test_inbox_widget_init_super_before_set_column_count_order() -> None:
    """``InboxWidget.__init__`` calls ``super().__init__`` before ``setColumnCount``."""
    text = _MAIN.read_text(encoding="utf-8")
    iw = text.index("class InboxWidget(QTableWidget):")
    start = text.index("    def __init__(self, parent=None):", iw)
    end = text.index("    def _on_context_menu(self, pos):", start)
    chunk = text[start:end]
    su = chunk.index("super().__init__(parent)")
    cc = chunk.index("self.setColumnCount(len(self.COLUMNS))")
    assert su < cc


def test_inbox_widget_init_set_column_count_before_horizontal_header_labels_order() -> None:
    """``InboxWidget.__init__`` sets the column count before applying header labels."""
    text = _MAIN.read_text(encoding="utf-8")
    iw = text.index("class InboxWidget(QTableWidget):")
    start = text.index("    def __init__(self, parent=None):", iw)
    end = text.index("    def _on_context_menu(self, pos):", start)
    chunk = text[start:end]
    cc = chunk.index("self.setColumnCount(len(self.COLUMNS))")
    hl = chunk.index("self.setHorizontalHeaderLabels(self.COLUMNS)")
    assert cc < hl


def test_inbox_widget_init_set_column_width_indices_ascending_source_order() -> None:
    """``InboxWidget.__init__`` applies column widths for indices **0 → 4** in ascending order."""
    text = _MAIN.read_text(encoding="utf-8")
    iw = text.index("class InboxWidget(QTableWidget):")
    start = text.index("    def __init__(self, parent=None):", iw)
    end = text.index("    def _on_context_menu(self, pos):", start)
    chunk = text[start:end]
    w0 = chunk.index("self.setColumnWidth(0, 40)")
    w1 = chunk.index("self.setColumnWidth(1, 220)")
    w2 = chunk.index("self.setColumnWidth(2, 80)")
    w3 = chunk.index("self.setColumnWidth(3, 110)")
    w4 = chunk.index("self.setColumnWidth(4, 120)")
    assert w0 < w1 < w2 < w3 < w4


def test_inbox_widget_drag_enter_move_accept_urls_ignore_other_mimes() -> None:
    """``InboxWidget`` accepts URL drags on enter/move; non-URL drags are ignored on enter."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class InboxWidget(QTableWidget):")
    de = text.index("    def dragEnterEvent(self, event: QDragEnterEvent):", start)
    pe = text.index("    def populate(self, rows: list):", start)
    chunk = text[de:pe]
    assert chunk.count("def dragEnterEvent(self, event: QDragEnterEvent):") == 1
    assert chunk.count("def dragMoveEvent(self, event):") == 1
    assert chunk.count("def dropEvent(self, event: QDropEvent):") == 1
    assert chunk.count("acceptProposedAction()") == 2
    assert chunk.count("event.ignore()") == 1


def test_inbox_widget_drag_enter_drag_move_drop_method_definition_order() -> None:
    """``InboxWidget`` declares URL drag handlers **enter → move → drop** before ``populate``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class InboxWidget(QTableWidget):")
    de = text.index("    def dragEnterEvent(self, event: QDragEnterEvent):", start)
    dm = text.index("    def dragMoveEvent(self, event):", start)
    dr = text.index("    def dropEvent(self, event: QDropEvent):", start)
    po = text.index("    def populate(self, rows: list):", start)
    assert de < dm < dr < po


def test_inbox_widget_drop_event_maps_local_urls_before_emit() -> None:
    """``InboxWidget.dropEvent`` reads URL list, keeps local files, then emits paths."""
    text = _MAIN.read_text(encoding="utf-8")
    iw = text.index("class InboxWidget(QTableWidget):")
    start = text.index("    def dropEvent(self, event: QDropEvent):", iw)
    end = text.index("    # -- population", start)
    chunk = text[start:end]
    assert chunk.count("urls = event.mimeData().urls()") == 1
    assert chunk.count("u.toLocalFile()") == 1
    assert chunk.count("u.isLocalFile()") == 1
    assert chunk.count("if paths:") == 1
    assert chunk.count("self.filesDropped.emit(paths)") == 1


def test_inbox_widget_selected_doc_id_user_role_then_clipboard_fallback() -> None:
    """``selected_doc_id`` reads id from column 0 ``UserRole``, else parses display text via ``table_cell_clipboard_text``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def selected_doc_id(self) -> int | None:")
    end = text.index("class DetailPane(QScrollArea):", start)
    chunk = text[start:end]
    assert chunk.count("self.selectedItems()") == 1
    assert chunk.count("self.currentRow()") == 1
    assert chunk.count("Qt.ItemDataRole.UserRole") == 1
    assert "coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole))" in chunk
    assert chunk.count("table_cell_clipboard_text(self, r, 0)") == 1
    assert "return coerce_combo_int_id(raw)" in chunk


def test_inbox_widget_selected_doc_id_selection_row_item_before_clipboard_fallback_order() -> None:
    """``selected_doc_id`` consults ``UserRole`` on column 0 before parsing clipboard text."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def selected_doc_id(self) -> int | None:")
    end = text.index("class DetailPane(QScrollArea):", start)
    chunk = text[start:end]
    si = chunk.index("rows = self.selectedItems()")
    emp = chunk.index("if not rows:")
    cr = chunk.index("r = self.currentRow()")
    it = chunk.index("it = self.item(r, 0)")
    clip = chunk.index("raw = table_cell_clipboard_text(self, r, 0).strip()")
    assert si < emp < cr < it < clip


def test_inbox_widget_populate_plain_cells_and_status_color() -> None:
    """``populate`` fills text columns with ``plain_display_table_item`` and colours status from ``STATUS_COLORS``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def populate(self, rows: list):")
    end = text.index("    def selected_doc_id(self) -> int | None:", start)
    chunk = text[start:end]
    assert chunk.count("plain_display_table_item(") == 4
    assert chunk.count('STATUS_COLORS.get(status, "#000000")') == 1
    assert chunk.count("status_item.setForeground(QColor(color))") == 1


def test_inbox_widget_populate_sortable_id_cells_type_column_and_import_date() -> None:
    """``populate`` toggles sorting, stores id/type/date cells, and re-enables sort after rebuild."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def populate(self, rows: list):")
    end = text.index("    def selected_doc_id(self) -> int | None:", start)
    chunk = text[start:end]
    assert chunk.count("self.setSortingEnabled(False)") == 1
    assert chunk.count("self.setSortingEnabled(True)") == 1
    assert chunk.count("self.setRowCount(len(packed))") == 1
    assert "coerce_combo_int_id(row[\"id\"])" in chunk
    assert chunk.count("id_cell.setData(Qt.ItemDataRole.UserRole, did)") == 1
    assert chunk.count('doc_type = "PDF" if "pdf" in mime else "Image"') == 1
    assert chunk.count('(row["import_date"] or "")[:10]') == 1
    assert chunk.count('fn = row["filename"] or ""') == 1


def test_inbox_widget_populate_sort_off_rows_loop_sort_on_order() -> None:
    """``populate`` disables sorting, sets row count, fills rows, then re-enables sorting."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def populate(self, rows: list):")
    end = text.index("    def selected_doc_id(self) -> int | None:", start)
    chunk = text[start:end]
    off = chunk.index("self.setSortingEnabled(False)")
    rc = chunk.index("self.setRowCount(len(packed))")
    lp = chunk.index("for r, (did, row) in enumerate(packed):")
    on = chunk.index("self.setSortingEnabled(True)")
    assert off < rc < lp < on


def test_inbox_widget_populate_setitem_columns_in_table_order() -> None:
    """``populate`` writes inbox columns **# → Filename → Type → Status → Date** (indices 0–4)."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def populate(self, rows: list):")
    end = text.index("    def selected_doc_id(self) -> int | None:", start)
    chunk = text[start:end]
    c0 = chunk.index("self.setItem(r, 0, id_cell)")
    c1 = chunk.index("self.setItem(r, 1,")
    c2 = chunk.index("self.setItem(r, 2,")
    c3 = chunk.index("self.setItem(r, 3, status_item)")
    c4 = chunk.index("self.setItem(r, 4,")
    assert c0 < c1 < c2 < c3 < c4


def test_inbox_widget_table_has_hover_tooltip() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class InboxWidget")
    end = text.index("class DetailPane", start)
    chunk = text[start:end]
    assert "self.setToolTip(" in chunk
    assert "Drag PDF or image files here" in chunk
    assert "File → Backup" in chunk and "probooks backup" in chunk


def test_main_help_menu_wires_register_keyboard_shortcuts_dialog() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    assert "show_register_keyboard_shortcuts_dialog" in text
    assert "Bank &register keyboard shortcuts" in text


def test_main_help_menu_wires_business_shortcuts_dialog() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    assert "show_business_keyboard_shortcuts_dialog" in text
    assert "&Business shortcuts" in text


def test_business_hub_subtab_bar_has_tab_tooltips() -> None:
    text = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    assert "class BusinessHub" in text
    assert "bar.setTabToolTip" in text
    assert "accounts receivable" in text
    assert "accounts payable" in text
    hub = text.split("class BusinessHub", 1)[1].split("def _refresh_current_subtab", 1)[0]
    assert "tip.setToolTip" in hub
    assert "export sales tax summary CSV (UTF-8 BOM for Excel)" in hub
    assert "sales tax CSV export uses UTF-8 BOM for Excel" in hub


def test_main_help_menu_wires_more_tab_shortcuts_dialog() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    assert "show_more_main_tabs_keyboard_shortcuts_dialog" in text
    assert "&More tab shortcuts (F5)" in text


def test_main_help_menu_status_tips_mention_utf8_bom_csv_exports() -> None:
    """Help menu hover tips echo CSV encoding where the linked dialog covers exports."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("        # Help menu")
    end = text.index("\n\n    # -- drag & drop on window", start)
    chunk = text[start:end]
    intake = chunk.split("act_intake_keys = QAction", 1)[1].split(
        "act_bank_import_keys = QAction", 1
    )[0]
    assert "UTF-8 BOM CSV exports on Bank Import (batch preview + AI line reconciliation)" in intake
    assert "Register, Reports, Journal, Business, and Audit" in intake
    assert "Bank Import Import CSV" in intake and "reads UTF-8 optional BOM" in intake
    assert "View → Bank Import and Register status tips" in intake
    bi = chunk.split("act_bank_import_keys = QAction", 1)[1].split(
        "act_register_keys = QAction", 1
    )[0]
    assert "Import CSV reads UTF-8 with optional BOM" in bi
    assert "line-compare CSV uses UTF-8 BOM for Excel" in bi
    assert "batch preview: copy row, txn id, date, amount, payee, memo, ref, COA" in bi
    assert (
        "line-reconciliation grid: statement/register date, amount, description, register txn id"
        in bi
    )
    reg = chunk.split("act_register_keys = QAction", 1)[1].split(
        "act_business_keys = QAction", 1
    )[0]
    assert "register grid shortcuts (row menu: copy row, txn id, date, amount, payee, memo, ref, COA)" in reg
    assert "Ctrl+Shift+E export CSV uses UTF-8 BOM for Excel" in reg
    assert "AI line-reconciliation field copies" in reg
    bus = chunk.split("act_business_keys = QAction", 1)[1].split(
        "act_more_tab_keys = QAction", 1
    )[0]
    assert "CSV exports use UTF-8 BOM for Excel" in bus
    more = chunk.split("act_more_tab_keys = QAction", 1)[1].split(
        "help_menu.addSeparator()", 1
    )[0]
    assert "line-reconciliation grid" in more
    assert "UTF-8 BOM CSV exports" in more
    assert "cross-links Register, Business, and Bank Import" in more
    about = chunk.split("act_about = QAction", 1)[1].split(
        "help_menu.addAction(act_about)", 1
    )[0]
    assert "Help shortcuts (UTF-8 BOM CSV)" in about
    assert "status bar" in about
    assert "banner ProBooks+ai" in about


def test_more_main_tabs_shortcuts_module_exposes_help_dialog() -> None:
    path = _DESKTOP_APP_DIR / "more_main_tabs_shortcuts.py"
    text = path.read_text(encoding="utf-8")
    assert "def show_more_main_tabs_keyboard_shortcuts_dialog" in text
    assert "def more_main_tabs_keyboard_shortcuts_help_text" in text
    assert "UTF-8 with BOM for Excel" in text
    assert "Ctrl+Shift+E" in text
    assert "line-compare" in text
    assert "Ctrl+7 Business" in text
    assert "Ctrl+2 Bank Import" in text
    assert "Help → Document intake shortcuts" in text
    assert "Register bulk actions" in text and "main **Recon** menu" in text
    assert "status bar" in text
    assert "per-item hover tooltips" in text
    assert "probooks.backup" in text
    assert "ok_tip=" in text
    assert "from desktop_app.table_clipboard import VIEW_BANK_REGISTER_KEYS_TOOLTIP" in text
    assert "+ VIEW_BANK_REGISTER_KEYS_TOOLTIP" in text
    assert "Copy payee / description" in text
    assert "**Copy memo**" in text
    assert "**Copy number / ref**" in text
    assert "**Copy date**" in text
    assert "**Copy amount**" in text
    assert "**Copy transaction id**" in text
    assert "Copy category (COA)" in text
    assert "**Bank Import** batch preview" in text
    assert "line-reconciliation grid" in text
    assert "Matched / Missing / Extra" in text
    assert "Copy register transaction id" in text


def test_main_tab_root_tooltips_mention_shared_company_backup() -> None:
    needle = "Same company SQLite database as other main tabs; File → Backup / Restore (probooks.backup)."
    for rel in (
        "bank_import_tab.py",
        "register_tab.py",
        "coa_tab.py",
        "reports_tab.py",
        "journal_tab.py",
        "audit_tab.py",
    ):
        t = (_DESKTOP_APP_DIR / rel).read_text(encoding="utf-8")
        assert needle in t, rel
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    hub = et.split("class BusinessHub", 1)[1].split("def _refresh_current_subtab", 1)[0]
    assert needle in hub
    assert "File → Backup / probooks backup" in hub


def test_audit_dialog_change_history_context_menu_includes_shortcuts_help() -> None:
    path = _DESKTOP_APP_DIR / "audit_dialog.py"
    text = path.read_text(encoding="utf-8")
    assert "def _audit_history_shortcuts_help" in text
    assert "Keyboard shortcuts…" in text
    assert "_audit_history_table_context_menu" in text
    assert "tip_qdialog_button_box(box, close=" in text
    assert "tbl.setToolTip(" in text
    assert "empty_lbl.setToolTip" in text
    assert "act_copy.setToolTip" in text
    assert "+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX" in text


def test_register_link_payment_suggestion_list_opens_register_shortcuts_help() -> None:
    rtab = (_DESKTOP_APP_DIR / "register_tab.py").read_text(encoding="utf-8")
    assert rtab.count("show_register_keyboard_shortcuts_dialog(self)") >= 2
    assert "on_sug_context_menu" in rtab
    assert "Link payment… (Recon → Transaction Tools) — suggested-matches list" in rtab
    assert "sug_list.setToolTip(" in rtab


def test_coa_journal_reports_audit_wired_to_more_tab_shortcuts_dialog() -> None:
    count = 0
    for rel in (
        "coa_tab.py",
        "journal_tab.py",
        "reports_tab.py",
        "audit_tab.py",
    ):
        count += (_DESKTOP_APP_DIR / rel).read_text(encoding="utf-8").count(
            "lambda: show_more_main_tabs_keyboard_shortcuts_dialog(self)"
        )
    assert count == 5, "COA grid + Journal list + Journal lines + Reports + Audit"


def test_main_help_menu_wires_bank_import_shortcuts_dialog() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    assert "show_bank_import_keyboard_shortcuts_dialog" in text
    assert "Bank &import shortcuts" in text


def test_bank_import_tab_exposes_shortcuts_dialog_for_help_menu() -> None:
    bit = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    assert "def show_bank_import_keyboard_shortcuts_dialog" in bit
    assert "def _bank_import_keyboard_shortcuts_help_text" in bit
    assert "Help → Business shortcuts" in bit
    assert "Help → Document intake shortcuts" in bit
    assert "If that account cannot be opened on the register" in bit
    assert "status bar" in bit.lower()
    assert "restores the company line" in bit
    assert "AI line-reconciliation panel below" in bit
    assert "Line-by-line Matched / Missing / Extra is in AI-assisted line" in bit
    assert "The same dialog summarizes the main Bank Import tab" in bit
    assert "line-reconciliation grid" in bit
    assert "Export comparison CSV" in bit
    assert "last folder you used" in bit
    assert "Export reconciliation report (CSV)" in bit
    assert "import file" in bit
    assert "last import folder" in bit
    assert "last CSV export folder" in bit
    assert "last folder you picked a bank file" in bit
    assert "reads UTF-8 with optional BOM" in bit
    assert "banded-row styling" in bit
    assert "arrow keys move the cell focus" in bit
    assert "UTF-8 CSV with a BOM for Excel" in bit
    assert "writes UTF-8 with a BOM for Excel" in bit
    assert "last CSV export folder if you have not imported yet" in bit
    assert "empty viewport" in bit


def test_register_tab_exposes_shared_shortcuts_dialog_for_help_menu() -> None:
    rtab = (_DESKTOP_APP_DIR / "register_tab.py").read_text(encoding="utf-8")
    assert "def show_register_keyboard_shortcuts_dialog" in rtab


def test_desktop_main_cli_and_qt_app_strings_use_probooks_plus_ai() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    mod_doc_end = text.index('"""', 3)
    mod_doc = text[: mod_doc_end + 3]
    assert "ProBooks+ai desktop application" in mod_doc
    assert "===============================\n" in mod_doc
    assert "Requires PySide6:" in mod_doc
    assert "Run with:" in mod_doc
    assert "Or directly:" in mod_doc
    assert "help_epilog" in mod_doc
    assert "README Desktop + Excel template" in mod_doc
    assert "``--help``" in mod_doc
    assert "**Help → Document intake shortcuts…**" in mod_doc
    assert "**Help → About**" in mod_doc
    assert "rich text + **Ok** hover hint" in mod_doc
    assert "Import documents" in mod_doc and "F5" in mod_doc
    assert "window-level hover hint" in mod_doc
    assert "content-area hint" in mod_doc
    assert "resize hint on hover" in mod_doc
    assert "**filename** / **status**" in mod_doc
    assert "**ProBooks+ai**" in mod_doc
    assert "Main window **menu bar**" in mod_doc
    assert "Top-level menus:" in mod_doc
    assert "**Recon** (bank register bulk actions" in mod_doc
    assert "**Tools** (e.g. **Invoice…**" in mod_doc
    assert "``setStatusTip``" in mod_doc
    assert "``setToolTip``" in mod_doc
    assert "``message_box_information_ok``" in mod_doc
    assert "**Ok** tooltip" in mod_doc
    assert "message_box_information_ok" in mod_doc
    assert "**F5** refreshes the inbox" in mod_doc
    assert "inbox **right-click**" in mod_doc
    assert "right-click" in mod_doc
    assert "Categorisation" in mod_doc
    assert "**InboxWidget**" in mod_doc
    assert "grid has a hover **tooltip**" in mod_doc
    assert "**AppHeaderWidget**" in mod_doc
    assert "installed package **version**" in mod_doc
    assert "**Ready** line" in mod_doc
    assert "**QSplitter**" in mod_doc
    assert "**QScrollArea**" in mod_doc
    assert "drag-and-drop" in mod_doc
    assert "(import, drag-and-drop, F5, shortcuts)" in mod_doc
    assert "**Extracted Fields**" in mod_doc
    assert "**Preview**" in mod_doc
    assert "**QTabWidget**" in mod_doc
    assert "sets a **setToolTip**" in mod_doc
    assert "**QFrame**" in mod_doc
    assert "**QLabel**" in mod_doc
    assert "left splitter pane" in mod_doc
    assert "inbox **column** **QWidget**" in mod_doc
    assert "group boxes and the **filename**" in mod_doc
    assert "also have hover hints" in mod_doc
    assert "(banner + tab widget)" in mod_doc
    assert "**central** **QWidget**" in mod_doc
    assert "margin hover hint" in mod_doc
    assert "inner **QWidget**" in mod_doc
    assert "**LineEdit** / spin fields" in mod_doc
    assert "action buttons use **tooltips**" in mod_doc
    assert "**Doc Type**" in mod_doc
    assert "**COA Account**" in mod_doc
    assert "**AI confidence**" in mod_doc
    assert "**rationale**" in mod_doc
    assert "empty area" in mod_doc
    assert "**Keyboard shortcuts…**" in mod_doc
    assert "match that dialog" in mod_doc
    assert "root **QWidget** has a hover hint for the whole tab" in mod_doc
    assert "short margin hint" in mod_doc
    assert "tab strip area" in mod_doc
    assert "Destructive **Yes**/**No** prompts" in mod_doc
    assert "``QAction``" in mod_doc
    assert "setStatusTip" in mod_doc and "status bar" in mod_doc
    assert "DetailPane" in mod_doc and "tooltips" in mod_doc
    assert "**tip_message_box_buttons**" in mod_doc
    assert "tip_message_box_buttons" in mod_doc
    assert "button hover hints" in mod_doc
    assert "new company file exists" in mod_doc and "database restore" in mod_doc
    assert "**QMessageBox.setToolTip**" in mod_doc
    assert "QMessageBox.setToolTip" in mod_doc
    assert "for the dialog window" in mod_doc
    assert "``_menu_action_tip``" in mod_doc
    assert "_menu_action_tip" in mod_doc
    assert "setTabToolTip" in mod_doc
    assert "Intake through Audit log" in mod_doc
    assert "``message_box_about_ok``" in mod_doc
    assert "message_box_about_ok" in mod_doc
    assert "python -m desktop_app.main" in mod_doc
    assert "python desktop_app/main.py" in mod_doc
    assert "pip install PySide6" in mod_doc
    hel = PROBOOKS_HELP_EPILOG.read_text(encoding="utf-8")
    assert "probooks.backup" in hel
    assert "File → Backup" in hel
    assert "UTF-8 BOM for Excel" in hel
    assert "import csv --errors-out" in hel
    assert "Bank CSV import" in hel
    assert "reads UTF-8 with optional BOM" in hel
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
    didx = text.index('"--database"')
    assert 'metavar="PATH"' in text[didx : didx + 220]
    assert "File → Backup" in text[didx : didx + 700]
    assert "probooks backup" in text[didx : didx + 700]
    assert 'app.setApplicationName("ProBooks+ai")' in text
    assert 'app.setOrganizationName("ProBooks+ai")' in text
    assert "Keyboard shortcuts are summarized under" in text


def test_desktop_main_major_section_banner_comments_top_to_bottom() -> None:
    """``main.py`` keeps stable ``#`` section dividers: worker, inbox, detail, banner, main window, entry."""
    text = _MAIN.read_text(encoding="utf-8")
    markers = (
        "# Background worker – runs AI extraction off the UI thread",
        "# Inbox list (left panel)",
        "# Detail pane (right panel)",
        "# App header / banner",
        "# Main window",
        "# Entry point",
    )
    positions = [text.index(m) for m in markers]
    assert positions == sorted(positions)


def test_desktop_main_inbox_widget_subsection_banners_order() -> None:
    """``InboxWidget`` keeps **drag & drop** before **population** in the class body."""
    text = _MAIN.read_text(encoding="utf-8")
    iw = text.index("class InboxWidget(QTableWidget):")
    dp = text.index("class DetailPane(QScrollArea):", iw)
    chunk = text[iw:dp]
    assert chunk.index("    # -- drag & drop ") < chunk.index("    # -- population ")


def test_desktop_main_detail_pane_init_subsection_banners_order() -> None:
    """``DetailPane.__init__`` builds **Document info → Preview → fields → categorisation → actions**."""
    text = _MAIN.read_text(encoding="utf-8")
    dp = text.index("class DetailPane(QScrollArea):")
    init = text.index("    def __init__(self, coa_list: list[str], parent=None):", dp)
    pub = text.index("    # -- public interface ----------------------------------------------------", init)
    chunk = text[init:pub]
    markers = (
        "        # -- Document info ",
        "        # -- Preview ",
        "        # -- Extracted fields ",
        "        # -- Categorisation ",
        "        # -- Action buttons ",
    )
    positions = [chunk.index(m) for m in markers]
    assert positions == sorted(positions)


def test_desktop_main_detail_pane_document_info_filename_before_status_labels_order() -> None:
    """``DetailPane.__init__`` wires filename (create → add) before status (create → add)."""
    text = _MAIN.read_text(encoding="utf-8")
    dp = text.index("class DetailPane(QScrollArea):")
    init = text.index("    def __init__(self, coa_list: list[str], parent=None):", dp)
    di = text.index("        # -- Document info ", init)
    pr = text.index("        # -- Preview ", init)
    chunk = text[di:pr]
    fn = chunk.index('self._lbl_filename = QLabel("No document selected")')
    af = chunk.index("layout.addWidget(self._lbl_filename)")
    st = chunk.index('self._lbl_status = QLabel("")')
    as_ = chunk.index("layout.addWidget(self._lbl_status)")
    assert fn < af < st < as_


def test_main_window_intake_coa_display_list_before_detail_pane_ctor_order() -> None:
    """Intake builds ``coa_display_list(self._coa)`` before constructing ``DetailPane(coa_display)``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("        # Right: detail pane")
    end = text.index("        splitter.addWidget(self._detail)", start)
    chunk = text[start:end]
    cd = chunk.index("coa_display = coa_display_list(self._coa)")
    dp = chunk.index("self._detail = DetailPane(coa_display)")
    assert cd < dp


def test_desktop_main_detail_pane_extracted_fields_widget_ctor_vendor_through_notes_order() -> None:
    """``DetailPane.__init__`` constructs extracted-field widgets **vendor → … → notes** before ``form.addRow``."""
    text = _MAIN.read_text(encoding="utf-8")
    dp = text.index("class DetailPane(QScrollArea):")
    init = text.index("    def __init__(self, coa_list: list[str], parent=None):", dp)
    fs = text.index("        # -- Extracted fields ", init)
    fe = text.index("        form.addRow(\"Vendor / Customer:\", self._f_vendor)", fs)
    chunk = text[fs:fe]
    v = chunk.index("self._f_vendor   = QLineEdit()")
    dt = chunk.index("self._f_doctype  = QComboBox()")
    inv = chunk.index("self._f_inv_num  = QLineEdit()")
    d = chunk.index("self._f_date     = QLineEdit()")
    due = chunk.index("self._f_due_date = QLineEdit()")
    sub = chunk.index("self._f_subtotal = QDoubleSpinBox()")
    tax = chunk.index("self._f_tax      = QDoubleSpinBox()")
    tot = chunk.index("self._f_total    = QDoubleSpinBox()")
    cur = chunk.index("self._f_currency = QLineEdit()")
    notes = chunk.index("self._f_notes    = QPlainTextEdit()")
    assert v < dt < inv < d < due < sub < tax < tot < cur < notes


def test_desktop_main_detail_pane_init_super_inner_scroll_layout_filename_status_before_preview() -> None:
    """``DetailPane.__init__`` attaches the inner widget, lays out filename/status, then the preview group."""
    text = _MAIN.read_text(encoding="utf-8")
    dp = text.index("class DetailPane(QScrollArea):")
    init = text.index("    def __init__(self, coa_list: list[str], parent=None):", dp)
    pub = text.index("    # -- public interface ----------------------------------------------------", init)
    chunk = text[init:pub]
    su = chunk.index("super().__init__(parent)")
    inn = chunk.index("inner = QWidget()")
    sw = chunk.index("self.setWidget(inner)")
    lv = chunk.index("layout = QVBoxLayout(inner)")
    fn = chunk.index('self._lbl_filename = QLabel("No document selected")')
    af = chunk.index("layout.addWidget(self._lbl_filename)")
    st = chunk.index('self._lbl_status = QLabel("")')
    pr = chunk.index('preview_group = QGroupBox("Preview")')
    assert su < inn < sw < lv < fn < af < st < pr


def test_desktop_main_detail_pane_preview_group_layout_label_inner_outer_add_widget_order() -> None:
    """``DetailPane.__init__`` builds the preview ``QGroupBox``, inner layout, label, then inner/outer ``addWidget``."""
    text = _MAIN.read_text(encoding="utf-8")
    dp = text.index("class DetailPane(QScrollArea):")
    init = text.index("    def __init__(self, coa_list: list[str], parent=None):", dp)
    pub = text.index("    # -- public interface ----------------------------------------------------", init)
    chunk = text[init:pub]
    pr = text.index("        # -- Preview ", init)
    fe = text.index("        # -- Extracted fields ", init)
    prev = text[pr:fe]
    pg = prev.index('preview_group = QGroupBox("Preview")')
    pl = prev.index("preview_layout = QVBoxLayout(preview_group)")
    lb = prev.index('self._preview_label = QLabel("(Select a document to preview)")')
    inn = prev.index("preview_layout.addWidget(self._preview_label)")
    out = prev.index("layout.addWidget(preview_group)")
    assert pg < pl < lb < inn < out


def test_desktop_main_main_window_subsection_banners_order() -> None:
    """``MainWindow`` keeps UI build, menu bar, window DnD, slots, then helpers in that order."""
    text = _MAIN.read_text(encoding="utf-8")
    mw = text.index("class MainWindow(QMainWindow):")
    ent = text.index("\n\n# ---------------------------------------------------------------------------\n# Entry point", mw)
    chunk = text[mw:ent]
    markers = (
        "    # -- UI construction ",
        "    # -- menu bar ",
        "    # -- drag & drop on window ",
        "    # -- slots ",
        "    # -- helpers ",
    )
    positions = [chunk.index(m) for m in markers]
    assert positions == sorted(positions)


def test_desktop_main_detail_pane_class_subsection_banners_order() -> None:
    """``DetailPane`` keeps **public interface → private helpers → button slots** after ``__init__``."""
    text = _MAIN.read_text(encoding="utf-8")
    dp = text.index("class DetailPane(QScrollArea):")
    hdr = text.index(
        "\n\n# ---------------------------------------------------------------------------\n# App header / banner",
        dp,
    )
    chunk = text[dp:hdr]
    pub = chunk.index("    # -- public interface ")
    priv = chunk.index("    # -- private helpers ")
    btn = chunk.index("    # -- button slots ")
    assert pub < priv < btn


def test_desktop_main_suppress_qt_font_stderr_handler_installs_chain() -> None:
    """``_suppress_qt_font_pointsize_stderr_spam`` filters ``QFont::setPointSize`` noise via ``qInstallMessageHandler``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("def _suppress_qt_font_pointsize_stderr_spam() -> None:")
    end = text.index("\n\ndef main():", start)
    chunk = text[start:end]
    assert '"""Drop known-harmless Qt warning' in chunk
    assert "global QSS" in chunk
    assert chunk.count("qInstallMessageHandler(_handler)") == 1
    assert chunk.count("QFont::setPointSize") == 1
    assert chunk.count("Point size <= 0") == 1
    assert chunk.count("must be greater than 0") == 1
    assert chunk.count("getattr(_handler, \"_prev\", None)") == 1
    assert 'message.decode("utf-8", errors="replace")' in chunk
    assert "isinstance(message, (bytes, bytearray))" in chunk
    assert "_handler._prev = qInstallMessageHandler(_handler)" in chunk
    assert chunk.count("prev(msg_type, context, message)") == 1


def test_desktop_main_entrypoint_boot_sequence() -> None:
    """``main()`` installs the Qt log filter, parses args, applies theme, resumes last DB, shows ``MainWindow``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("def main():")
    end = text.index('\n\nif __name__ == "__main__":', start)
    chunk = text[start:end]
    assert chunk.count("_suppress_qt_font_pointsize_stderr_spam()") == 1
    assert chunk.count("argparse.ArgumentParser(") == 1
    assert chunk.count("parser.add_argument(") == 2
    assert chunk.count("parser.parse_args()") == 1
    assert chunk.count("QApplication(sys.argv)") == 1
    assert chunk.count('app.setApplicationName("ProBooks+ai")') == 1
    assert chunk.count('app.setOrganizationName("ProBooks+ai")') == 1
    assert chunk.count("apply_dark_theme(app)") == 1
    assert chunk.count("MainWindow(db_path=db_path)") == 1
    assert chunk.count("window.show()") == 1
    assert chunk.count("sys.exit(app.exec())") == 1
    assert chunk.count("db_path = args.database") == 1
    assert chunk.count("if db_path is None:") == 1
    assert chunk.count("db_path = last") == 1
    assert chunk.count('QSettings().value("company_database_path", "", type=str)') == 1
    assert chunk.count("Path(last).is_file()") == 1
    assert chunk.count("ver = application_version()") == 1
    assert 'action="version"' in chunk
    assert 'version=f"ProBooks+ai {ver}"' in chunk
    assert chunk.index("QApplication(sys.argv)") < chunk.index(
        'app.setApplicationName("ProBooks+ai")'
    )
    assert chunk.index('app.setApplicationName("ProBooks+ai")') < chunk.index(
        'app.setOrganizationName("ProBooks+ai")'
    )
    assert chunk.index('app.setOrganizationName("ProBooks+ai")') < chunk.index(
        "apply_dark_theme(app)"
    )
    assert chunk.index("apply_dark_theme(app)") < chunk.index("MainWindow(db_path=db_path)")
    assert chunk.index("MainWindow(db_path=db_path)") < chunk.index("window.show()")
    assert chunk.index("window.show()") < chunk.index("sys.exit(app.exec())")
    assert chunk.index("_suppress_qt_font_pointsize_stderr_spam()") < chunk.index(
        "ver = application_version()"
    )


def test_desktop_main_main_argparse_build_parse_before_qapplication_order() -> None:
    """``main()`` resolves version, builds the parser, adds flags, parses args, then constructs ``QApplication``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("def main():")
    end = text.index('\n\nif __name__ == "__main__":', start)
    chunk = text[start:end]
    ver = chunk.index("ver = application_version()")
    prs = chunk.index("parser = argparse.ArgumentParser(")
    av = chunk.index('"--version",')
    adb = chunk.index('"--database",')
    par = chunk.index("args = parser.parse_args()")
    qap = chunk.index("QApplication(sys.argv)")
    assert ver < prs < av < adb < par < qap


def test_desktop_main_module_main_guard_invokes_main() -> None:
    """Running ``desktop_app/main.py`` as a script should call ``main()``."""
    text = _MAIN.read_text(encoding="utf-8")
    guard = text.index('if __name__ == "__main__":')
    tail = text[guard : guard + 80]
    assert "main()" in tail


def test_audit_tab_f5_refresh_shortcut_wired() -> None:
    path = _DESKTOP_APP_DIR / "audit_tab.py"
    text = path.read_text(encoding="utf-8")
    assert 'QKeySequence("F5")' in text
    assert "activated.connect(self._refresh)" in text


def test_audit_tab_entity_id_uses_coerce_combo_int_id() -> None:
    at = (_DESKTOP_APP_DIR / "audit_tab.py").read_text(encoding="utf-8")
    assert "from desktop_app.qt_combo_ids import coerce_combo_int_id" in at
    assert at.count("coerce_combo_int_id(id_txt)") == 2
    ref = at.split("def _refresh(self):", 1)[1].split("def _on_audit_context_menu", 1)[0]
    assert "coerce_combo_int_id(r[\"entity_id\"])" in ref


def test_reports_tab_f5_rerun_last_report_shortcut_wired() -> None:
    path = _DESKTOP_APP_DIR / "reports_tab.py"
    text = path.read_text(encoding="utf-8")
    assert 'QKeySequence("F5")' in text
    assert "activated.connect(self._rerun_last_report)" in text
    assert "_last_report_kind" in text


def test_coa_tab_f5_refresh_shortcut_wired() -> None:
    path = _DESKTOP_APP_DIR / "coa_tab.py"
    text = path.read_text(encoding="utf-8")
    assert 'QKeySequence("F5")' in text
    assert "activated.connect(self._refresh)" in text


def test_coa_tab_toolbar_buttons_have_tooltips() -> None:
    text = (_DESKTOP_APP_DIR / "coa_tab.py").read_text(encoding="utf-8")
    assert "_chk_inactive.setToolTip" in text
    assert "F5 reloads the grid" in text
    assert "_btn_add.setToolTip" in text
    assert "tip_qdialog_button_box(\n            btns," in text
    assert "save=\"Save this COA account and close the dialog.\"" in text
    assert "self._table.setToolTip(" in text
    assert "_f_number.setToolTip" in text
    assert "_f_type.setToolTip" in text
    assert "_f_active.setToolTip" in text
    assert "_lbl_count.setToolTip" in text
    assert "tip.setToolTip" in text
    assert "class AddEditCOADialog" in text
    assert "self.setToolTip(" in text
    assert "chart-of-accounts row" in text
    assert "box.setToolTip(" in text
    assert "hidden from COA pickers" in text
    assert "act_keys.setToolTip" in text
    assert "act_copy.setToolTip" in text
    assert "+ VIEW_BANK_REGISTER_KEYS_TOOLTIP" in text
    assert text.count("+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX") >= 2


def test_reports_tab_run_and_export_buttons_have_tooltips() -> None:
    text = (_DESKTOP_APP_DIR / "reports_tab.py").read_text(encoding="utf-8")
    assert "b.setToolTip(tip)" in text
    assert "btn_export.setToolTip" in text
    assert "UTF-8 with BOM for Excel" in text
    assert "F5 re-runs" in text
    assert "_start.setToolTip" in text
    assert "_end.setToolTip" in text
    assert "filt.setToolTip" in text
    assert "_summary.setToolTip" in text
    assert "tip.setToolTip" in text
    assert "self._table.setToolTip(" in text
    assert "act_keys.setToolTip" in text
    assert "act_copy.setToolTip" in text
    assert "+ VIEW_BANK_REGISTER_KEYS_TOOLTIP" in text
    assert text.count("+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX") >= 2


def test_bank_import_header_buttons_manage_and_csv_have_tooltips() -> None:
    text = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    assert "btn_manage.setToolTip" in text
    assert "btn_import.setToolTip" in text
    assert "btn_pdf.setToolTip" in text
    assert "read as UTF-8 with optional BOM (Excel-friendly)" in text
    assert "last folder you picked from Import CSV or Import PDF" in text
    assert "CSV export folder if you have not imported yet" in text
    assert "Keyboard shortcuts" in text
    assert "hdr_lbl.setToolTip" in text
    assert "lbl_import_batches.setToolTip" in text
    assert "tip.setToolTip" in text
    assert "cancel_csv.setToolTip" in text
    assert "prog_dlg.setCancelButton(cancel_csv)" in text
    assert "prog_dlg.setToolTip" in text
    assert "_acct_combo.setToolTip" in text
    assert "self._batch_table.setToolTip(" in text
    assert "class _AccountEditDialog" in text
    assert "Save this bank account and close the dialog." in text
    assert "_name.setToolTip" in text
    assert "if self._coa_db is not None:" in text
    assert "Chart-of-accounts cash or bank line" in text


def test_journal_tab_f5_refresh_shortcut_wired() -> None:
    path = _DESKTOP_APP_DIR / "journal_tab.py"
    text = path.read_text(encoding="utf-8")
    assert 'QKeySequence("F5")' in text
    assert "activated.connect(self._refresh_list)" in text


def test_journal_tab_export_csv_button_has_tooltip() -> None:
    jt = (_DESKTOP_APP_DIR / "journal_tab.py").read_text(encoding="utf-8")
    assert "btn_export.setToolTip" in jt
    assert "journal entries" in jt
    assert "UTF-8 with BOM for Excel" in jt
    assert "_start.setToolTip" in jt
    assert "_end.setToolTip" in jt
    assert "lbl_j_from.setToolTip" in jt
    assert "lbl_j_to.setToolTip" in jt
    assert "split.setToolTip" in jt
    assert "tip.setToolTip" in jt
    assert "self._list.setToolTip(" in jt
    assert "self._lines.setToolTip(" in jt
    assert "act_keys.setToolTip" in jt
    assert "act_copy.setToolTip" in jt
    assert "+ VIEW_BANK_REGISTER_KEYS_TOOLTIP" in jt
    assert jt.count("+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX") >= 4


def test_audit_tab_export_and_apply_filter_buttons_have_tooltips() -> None:
    at = (_DESKTOP_APP_DIR / "audit_tab.py").read_text(encoding="utf-8")
    assert "btn_export.setToolTip" in at
    assert "UTF-8 with BOM for Excel" in at
    assert "btn_apply.setToolTip" in at
    assert "_ent_type.setToolTip" in at
    assert "_ent_id.setToolTip" in at
    assert "lbl_audit_ent_type.setToolTip" in at
    assert "lbl_audit_ent_id.setToolTip" in at
    assert "hint.setToolTip" in at
    assert "self._tbl.setToolTip(" in at
    assert "act_keys.setToolTip" in at
    assert "act_copy.setToolTip" in at
    assert "+ VIEW_BANK_REGISTER_KEYS_TOOLTIP" in at
    assert at.count("+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX") >= 2


def test_bank_import_manage_accounts_and_reconciliation_buttons_have_tooltips() -> None:
    bit = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    assert "_btn_add.setToolTip" in bit
    assert "_btn_reconcile.setToolTip" in bit
    assert "_btn_export_csv.setToolTip" in bit
    rec_chunk = bit.split("class ReconciliationPanel", 1)[1].split("class BankImportTab", 1)[0]
    assert "Compares statement dates and balances" in rec_chunk
    assert "AI-assisted line reconciliation below" in rec_chunk
    assert "_lbl_status.setToolTip" in rec_chunk
    assert "UTF-8 with BOM for Excel" in rec_chunk
    assert "Export comparison CSV" in rec_chunk
    assert "last import folder" in rec_chunk
    assert "appends .csv" in rec_chunk


def test_bank_import_column_and_statement_dialog_buttons_have_tooltips() -> None:
    bit = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    assert bit.count("tip_qdialog_button_box(\n            btns,") >= 3
    assert "class ColumnMappingDialog" in bit
    assert "Apply this column mapping" in bit
    assert "_date_col.setToolTip" in bit
    assert "_amount_col.setToolTip" in bit
    assert "Choose which CSV columns hold" in bit
    assert "class StatementPeriodDialog" in bit
    assert "statement period and opening/closing balances" in bit
    assert "stored on this import batch for reconciliation" in bit
    assert "_begin_bal.setToolTip" in bit
    assert "note.setToolTip" in bit


def test_bank_import_manage_and_account_edit_dialogs_have_window_tooltips() -> None:
    bit = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    assert 'self.setWindowTitle("Manage Bank Accounts")' in bit
    assert "Add, edit, or delete bank accounts used for CSV/PDF import" in bit
    mad = bit.split("class ManageAccountsDialog", 1)[1].split("def _build_ui", 1)[0]
    assert "File → Backup" in mad and "probooks backup" in mad
    mad_ui = bit.split("class ManageAccountsDialog", 1)[1].split(
        "def _on_accounts_table_context_menu", 1
    )[0]
    di = mad_ui.index("_btn_del.setToolTip(")
    assert "File → Backup" in mad_ui[di : di + 200]
    assert "Bank account label, institution, type" in bit


def test_detail_pane_scroll_and_app_header_have_hover_tooltips() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class DetailPane")
    end = text.index("class AppHeaderWidget", start)
    chunk = text[start:end]
    assert "self.setToolTip(" in chunk
    assert "Scroll the detail pane" in chunk
    assert "Bank statement CSV/PDF import is on Bank Import" in chunk
    assert "inner.setToolTip(" in chunk
    inn = chunk.split("inner.setToolTip(", 1)[1].split("self.setWidget(inner)", 1)[0]
    assert "Bank statement CSV/PDF import is on Bank Import" in inn
    assert "Preview, extracted fields, categorization" in chunk
    assert "File → Backup" in chunk
    assert "toolbar.setToolTip" not in text
    hdr = text.split("class AppHeaderWidget", 1)[1].split("class MainWindow", 1)[0]
    assert "self.setToolTip(" in hdr
    assert "ProBooks+ai" in hdr
    assert "AlignRight" in hdr


def test_desktop_main_detail_pane_wires_actions_load_ai_and_clear() -> None:
    """``DetailPane`` buttons emit signals; load/AI/collect/clear paths touch DB and fields."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class DetailPane(QScrollArea):")
    end = text.index("class AppHeaderWidget(QFrame):", start)
    chunk = text[start:end]
    assert "Shows document preview + extracted fields + action buttons." in chunk
    assert chunk.count("runAI      = Signal(int)") == 1
    assert chunk.count("approve    = Signal(int)") == 1
    assert chunk.count("markPosted = Signal(int)") == 1
    assert chunk.count("reject     = Signal(int)") == 1
    assert chunk.count("self._btn_run.clicked.connect(self._on_run_ai)") == 1
    assert chunk.count("self._btn_approve.clicked.connect(self._on_approve)") == 1
    assert chunk.count("self._btn_post.clicked.connect(self._on_post)") == 1
    assert chunk.count("self._btn_reject.clicked.connect(self._on_reject)") == 1
    assert chunk.count("self.runAI.emit(self._doc_id)") == 1
    assert chunk.count("self.approve.emit(self._doc_id)") == 1
    assert chunk.count("self.markPosted.emit(self._doc_id)") == 1
    assert chunk.count("self.reject.emit(self._doc_id)") == 1
    assert chunk.count("db.get_document(did)") == 1
    assert chunk.count("db.get_approved(did)") == 1
    assert chunk.count("db.get_latest_extraction(did)") == 1
    assert chunk.count("self._show_preview(row[\"stored_path\"]") == 1
    assert chunk.count("def populate_ai_result(self, result, suggestions=None):") == 1
    assert chunk.count("def collect_approved_values(self) -> dict:") == 1
    assert chunk.count('"coa_account":') == 1
    assert chunk.count("mimetype.startswith(\"image/\")") == 1
    assert chunk.count('mimetype == "application/pdf"') == 1
    assert chunk.count("self._doc_id = None") == 1
    assert "No document selected" in chunk


def test_desktop_main_detail_pane_load_document_escapes_status_for_rich_text() -> None:
    """``load_document`` renders status as rich HTML with ``escape_html_text`` for safety."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def load_document(self, doc_id: int, db: DocumentDatabase):")
    end = text.index("    def populate_ai_result(self, result, suggestions=None):", start)
    chunk = text[start:end]
    assert chunk.count("escape_html_text(status)") == 1
    assert chunk.count("Qt.TextFormat.RichText") == 1
    assert chunk.count("self._lbl_status.setTextFormat(Qt.TextFormat.RichText)") == 1
    assert chunk.count('STATUS_COLORS.get(status, "#000")') == 1


def test_desktop_main_detail_pane_load_document_approved_or_extraction_and_enables_buttons() -> None:
    """``load_document`` stores ``_doc_id``, fills fields from approved row else latest extraction, enables actions."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def load_document(self, doc_id: int, db: DocumentDatabase):")
    end = text.index("    def populate_ai_result(self, result, suggestions=None):", start)
    chunk = text[start:end]
    assert "did = coerce_combo_int_id(doc_id)" in chunk
    assert chunk.count("self._doc_id = did") == 1
    assert chunk.count("if not row:") == 1
    assert chunk.count("db.get_document(did)") == 1
    assert chunk.count("approved = db.get_approved(did)") == 1
    assert chunk.count("extraction = db.get_latest_extraction(did)") == 1
    assert chunk.count("src = approved or extraction") == 1
    assert chunk.count("self._populate_fields(src)") == 1
    assert chunk.count("if approved:") == 1
    assert chunk.count('approved["coa_account"]') == 1
    assert chunk.count('approved["tax_category"]') == 1
    assert chunk.count("self._set_buttons_enabled(True)") == 1
    assert chunk.count("self._lbl_filename.setText(escape_ampersand_for_qt(row[\"filename\"]))") == 1
    assert (
        chunk.count(
            'self._show_preview(row["stored_path"], row["mimetype"], row["page_count"])'
        )
        == 1
    )


def test_desktop_main_detail_pane_populate_ai_result_applies_suggestions() -> None:
    """``populate_ai_result`` fills from extraction then maps COA/confidence/rationale from suggestions."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def populate_ai_result(self, result, suggestions=None):")
    end = text.index("    def collect_approved_values(self) -> dict:", start)
    chunk = text[start:end]
    assert "Fill the form with AI extraction + categorisation results." in chunk
    assert chunk.count("_populate_fields_from_extraction(result)") == 1
    assert "suggestions and not suggestions.error" in chunk
    assert chunk.count("findData(s_coa, Qt.ItemDataRole.UserRole)") == 1
    assert chunk.count("self._f_coa.setCurrentIndex(-1)") == 1
    assert chunk.count("self._f_coa.setEditText(s_coa)") == 1
    assert chunk.count("self._f_coa.setCurrentIndex(0)") == 1
    assert chunk.count('self._f_confidence.setText(f"{conf:.0%}")') == 1
    assert chunk.count("self._lbl_rationale.setText(suggestions.rationale or \"\")") == 1
    assert '(suggestions.coa_account or "").strip()' in chunk
    assert chunk.count("if s_coa:") == 1
    assert chunk.count("if idx >= 0:") == 1
    assert chunk.count('self._f_tax_cat.setText(suggestions.tax_category or "")') == 1


_DETAIL_APPROVED_VALUE_KEYS = (
    "vendor",
    "doc_type",
    "invoice_number",
    "doc_date",
    "due_date",
    "subtotal",
    "tax",
    "total",
    "currency",
    "notes",
    "coa_account",
    "tax_category",
)


def test_desktop_main_detail_pane_collect_approved_values_keys_match_approved_values_columns() -> None:
    """``collect_approved_values`` keys match DB columns; COA value comes from ``_coa_combo_raw_value()``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def collect_approved_values(self) -> dict:")
    end = text.index(
        "    def _show_preview(self, stored_path: str, mimetype: str, page_count):",
        start,
    )
    chunk = text[start:end]
    assert "Return the current form values as a dict for saving." in chunk
    for key in _DETAIL_APPROVED_VALUE_KEYS:
        assert chunk.count(f'"{key}":') == 1, key
    assert chunk.count("self._coa_combo_raw_value()") == 1
    assert 'self._f_currency.text().strip() or "USD"' in chunk
    assert chunk.count(".strip() or None") == 6
    assert "self._f_notes.toPlainText().strip() or None" in chunk


def test_desktop_main_detail_pane_collect_approved_values_dict_literal_source_key_order() -> None:
    """``collect_approved_values`` return dict lists keys in the same order as ``_DETAIL_APPROVED_VALUE_KEYS``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def collect_approved_values(self) -> dict:")
    end = text.index(
        "    def _show_preview(self, stored_path: str, mimetype: str, page_count):",
        start,
    )
    chunk = text[start:end]
    positions = [chunk.index(f'        "{k}":') for k in _DETAIL_APPROVED_VALUE_KEYS]
    assert positions == sorted(positions)


def test_desktop_main_detail_pane_set_coa_combo_raw_empty_count_placeholder_find_or_freetext_order() -> None:
    """``_set_coa_combo_raw`` checks empty combo, placeholder index, then ``findData`` vs free-text edit."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _set_coa_combo_raw(self, raw: str | None) -> None:")
    end = text.index("    def clear_view(self):", start)
    chunk = text[start:end]
    z = chunk.index("if self._f_coa.count() == 0:")
    ph = chunk.index('if not (raw or "").strip():')
    ph_idx = chunk.index("self._f_coa.setCurrentIndex(0)")
    rstrip = chunk.index("r = raw.strip()")
    fd = chunk.index("idx = self._f_coa.findData(r, Qt.ItemDataRole.UserRole)")
    br = chunk.index("        if idx >= 0:")
    el = chunk.index("        else:")
    neg = chunk.index("self._f_coa.setCurrentIndex(-1)")
    ed = chunk.index("self._f_coa.setEditText(r)")
    assert z < ph < ph_idx < rstrip < fd < br < el
    assert br < neg < ed


def test_desktop_main_detail_pane_populate_ai_result_suggestions_tail_updates_order() -> None:
    """After the COA branch, ``populate_ai_result`` sets tax, confidence, then rationale."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def populate_ai_result(self, result, suggestions=None):")
    end = text.index("    def collect_approved_values(self) -> dict:", start)
    chunk = text[start:end]
    sug = chunk.index("if suggestions and not suggestions.error:")
    scoa = chunk.index('s_coa = (suggestions.coa_account or "").strip()')
    if_s = chunk.index("            if s_coa:")
    fd = chunk.index(
        "idx = self._f_coa.findData(s_coa, Qt.ItemDataRole.UserRole)"
    )
    tax = chunk.index('self._f_tax_cat.setText(suggestions.tax_category or "")')
    conf = chunk.index("conf = suggestions.confidence")
    rat = chunk.index('self._lbl_rationale.setText(suggestions.rationale or "")')
    assert sug < scoa < if_s < fd < tax < conf < rat


def test_desktop_main_detail_pane_show_preview_image_scaled_pdf_stub_or_fallback() -> None:
    """``_show_preview`` scales images, shows a PDF stub with escaped file name, or a no-preview placeholder."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _show_preview(self, stored_path: str, mimetype: str, page_count):")
    end = text.index("    def _populate_fields(self, row):", start)
    chunk = text[start:end]
    assert chunk.count("mimetype and mimetype.startswith(\"image/\")") == 1
    assert chunk.count("QPixmap(stored_path)") == 1
    assert chunk.count("if not pix.isNull():") == 1
    assert chunk.count("400, 300") == 1
    assert chunk.count("Qt.AspectRatioMode.KeepAspectRatio") == 1
    assert chunk.count("Qt.TransformationMode.SmoothTransformation") == 1
    assert chunk.count("self._preview_label.setPixmap(pix)") == 1
    assert chunk.count('self._preview_label.setText("")') == 1
    assert chunk.count('mimetype == "application/pdf"') == 1
    assert chunk.count('pages = page_count or "?"') == 1
    assert chunk.count("escape_ampersand_for_qt(Path(stored_path).name)") == 1
    assert chunk.count('"(No preview available)"') == 1


def test_desktop_main_detail_pane_show_preview_branch_order_image_pdf_fallback() -> None:
    """``_show_preview`` tries the image branch, then PDF stub, then the generic placeholder."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _show_preview(self, stored_path: str, mimetype: str, page_count):")
    end = text.index("    def _populate_fields(self, row):", start)
    chunk = text[start:end]
    img = chunk.index('if mimetype and mimetype.startswith("image/")')
    pdf = chunk.index('elif mimetype == "application/pdf"')
    fb = chunk.index('self._preview_label.setText("(No preview available)")')
    assert img < pdf < fb


def test_desktop_main_detail_pane_populate_fields_maps_sqlite_row_columns() -> None:
    """``_populate_fields`` no-ops on falsy rows; otherwise maps approved/extraction columns into widgets."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _populate_fields(self, row):")
    end = text.index("    def _populate_fields_from_extraction(self, result):", start)
    chunk = text[start:end]
    assert chunk.count("if not row:") == 1
    assert chunk.count('row["vendor"]') == 1
    assert chunk.count('row["doc_type"]') == 1
    assert chunk.count('row["invoice_number"]') == 1
    assert chunk.count('row["doc_date"]') == 1
    assert chunk.count('row["due_date"]') == 1
    assert chunk.count('row["subtotal"]') == 1
    assert chunk.count('row["tax"]') == 1
    assert chunk.count('row["total"]') == 1
    assert chunk.count('row["currency"]') == 1
    assert chunk.count('row["notes"]') == 1
    assert chunk.count('self._f_doctype.findText(row["doc_type"] or "")') == 1
    assert chunk.count("if idx >= 0:") == 1


def test_desktop_main_detail_pane_populate_fields_widget_assignment_order() -> None:
    """``_populate_fields`` fills widgets **vendor → doc type → … → notes** after the empty-row guard."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _populate_fields(self, row):")
    end = text.index("    def _populate_fields_from_extraction(self, result):", start)
    chunk = text[start:end]
    v = chunk.index('self._f_vendor.setText(row["vendor"] or "")')
    dt = chunk.index('idx = self._f_doctype.findText(row["doc_type"] or "")')
    dt_idx = chunk.index("self._f_doctype.setCurrentIndex(idx)")
    inv = chunk.index('self._f_inv_num.setText(row["invoice_number"] or "")')
    d = chunk.index('self._f_date.setText(row["doc_date"] or "")')
    due = chunk.index('self._f_due_date.setText(row["due_date"] or "")')
    sub = chunk.index('self._f_subtotal.setValue(float(row["subtotal"] or 0))')
    tax = chunk.index('self._f_tax.setValue(float(row["tax"] or 0))')
    tot = chunk.index('self._f_total.setValue(float(row["total"] or 0))')
    cur = chunk.index('self._f_currency.setText(row["currency"] or "USD")')
    notes = chunk.index('self._f_notes.setPlainText(row["notes"] or "")')
    assert v < dt < dt_idx < inv < d < due < sub < tax < tot < cur < notes


def test_desktop_main_detail_pane_populate_fields_from_extraction_maps_result() -> None:
    """``_populate_fields_from_extraction`` copies ``ExtractionResult`` fields into the detail form + confidence."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _populate_fields_from_extraction(self, result):")
    end = text.index("    def _set_buttons_enabled(self, enabled: bool):", start)
    chunk = text[start:end]
    assert chunk.count("result.vendor or") == 1
    assert chunk.count("result.doc_type or") == 1
    assert chunk.count("result.invoice_number or") == 1
    assert chunk.count("result.doc_date or") == 1
    assert chunk.count("result.due_date or") == 1
    assert chunk.count("result.subtotal or 0") == 1
    assert chunk.count("result.tax or 0") == 1
    assert chunk.count("result.total or 0") == 1
    assert chunk.count("result.currency or") == 1
    assert chunk.count("result.notes or") == 1
    assert chunk.count('self._f_confidence.setText(f"{result.confidence:.0%}")') == 1
    assert chunk.count('self._f_doctype.findText(result.doc_type or "")') == 1


def test_desktop_main_detail_pane_populate_fields_from_extraction_widget_assignment_order() -> None:
    """``_populate_fields_from_extraction`` fills **vendor → … → notes**, then **confidence** last."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _populate_fields_from_extraction(self, result):")
    end = text.index("    def _set_buttons_enabled(self, enabled: bool):", start)
    chunk = text[start:end]
    v = chunk.index('self._f_vendor.setText(result.vendor or "")')
    dt = chunk.index('idx = self._f_doctype.findText(result.doc_type or "")')
    dt_idx = chunk.index("self._f_doctype.setCurrentIndex(idx)")
    inv = chunk.index('self._f_inv_num.setText(result.invoice_number or "")')
    d = chunk.index('self._f_date.setText(result.doc_date or "")')
    due = chunk.index('self._f_due_date.setText(result.due_date or "")')
    sub = chunk.index("self._f_subtotal.setValue(float(result.subtotal or 0))")
    tax = chunk.index("self._f_tax.setValue(float(result.tax or 0))")
    tot = chunk.index("self._f_total.setValue(float(result.total or 0))")
    cur = chunk.index('self._f_currency.setText(result.currency or "USD")')
    notes = chunk.index('self._f_notes.setPlainText(result.notes or "")')
    conf = chunk.index('self._f_confidence.setText(f"{result.confidence:.0%}")')
    assert v < dt < dt_idx < inv < d < due < sub < tax < tot < cur < notes < conf


def test_desktop_main_detail_pane_button_slots_require_selected_doc() -> None:
    """Detail pane toolbar actions emit only when ``_doc_id`` is set."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    # -- button slots --------------------------------------------------------")
    end = text.index("    def update_coa(self, coa_list: list[str]):", start)
    chunk = text[start:end]
    assert chunk.count("if self._doc_id is not None:") == 4


def test_desktop_main_detail_pane_document_type_combo_fixed_values() -> None:
    """Detail pane **Doc Type** lists the five supported workflow kinds."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("        self._f_doctype  = QComboBox()")
    end = text.index("        self._f_inv_num  = QLineEdit()", start)
    chunk = text[start:end]
    assert (
        'self._f_doctype.addItems(["invoice", "bill", "receipt", "credit_note", "other"])'
        in chunk
    )


def test_desktop_main_detail_pane_scroll_wraps_resizable_inner_widget() -> None:
    """``DetailPane`` ctor: super, state, inner widget, ``QVBoxLayout`` margins/spacing, resizable scroll."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class DetailPane(QScrollArea):")
    init_s = text.index("    def __init__(self, coa_list: list[str], parent=None):", start)
    inner = text.index("        inner = QWidget()", init_s)
    chunk = text[init_s:inner]
    assert chunk.count("super().__init__(parent)") == 1
    end = text.index("        # -- Document info ---------------------------------------------------", init_s)
    chunk = text[init_s:end]
    assert chunk.count("self._doc_id: int | None = None") == 1
    assert chunk.count("self._coa_list = coa_list") == 1
    assert chunk.count("self.setWidget(inner)") == 1
    assert chunk.count("self.setWidgetResizable(True)") == 1
    assert chunk.count("layout = QVBoxLayout(inner)") == 1
    assert chunk.count("layout.setContentsMargins(12, 12, 12, 12)") == 1
    assert chunk.count("layout.setSpacing(10)") == 1


def test_desktop_main_detail_pane_extracted_fields_ten_form_rows() -> None:
    """**Extracted Fields**: ten ``QFormLayout`` rows plus money spin limits, currency width, notes height."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("        form = QFormLayout(fields_group)")
    end = text.index("        layout.addWidget(fields_group)", start)
    chunk = text[start:end]
    assert chunk.count("form.addRow(") == 10
    assert chunk.count("setMaximum(9_999_999)") == 3
    assert chunk.count("setDecimals(2)") == 3
    assert chunk.count("setMaxLength(3)") == 1
    assert chunk.count("setFixedWidth(55)") == 1
    assert chunk.count("setFixedHeight(60)") == 1


def test_desktop_main_detail_pane_categorisation_four_form_rows() -> None:
    """**Categorisation**: editable COA combo filled from ctor list, four form rows, rationale styling."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index('        cat_group = QGroupBox("Categorisation Suggestions")')
    end = text.index("        layout.addWidget(cat_group)", start)
    chunk = text[start:end]
    assert chunk.count("self._fill_coa_combo(coa_list)") == 1
    assert chunk.count("self._f_coa.setEditable(True)") == 1
    assert chunk.count("cat_layout.addRow(") == 4
    assert chunk.count("self._lbl_rationale.setWordWrap(True)") == 1
    assert chunk.count("self._lbl_rationale.setTextFormat(Qt.TextFormat.PlainText)") == 1


def test_desktop_main_detail_pane_three_section_group_boxes() -> None:
    """Detail layout uses **Preview**, **Extracted Fields**, and **Categorisation** group boxes before actions."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index('        preview_group = QGroupBox("Preview")')
    end = text.index("        # -- Action buttons", start)
    chunk = text[start:end]
    assert chunk.count('QGroupBox("Preview")') == 1
    assert chunk.count('QGroupBox("Extracted Fields")') == 1
    assert chunk.count('QGroupBox("Categorisation Suggestions")') == 1


def test_desktop_main_detail_pane_document_filename_and_status_labels() -> None:
    """Detail header row: bold plain-text filename placeholder and empty status line with tooltips."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index('        self._lbl_filename = QLabel("No document selected")')
    end = text.index("        # -- Preview", start)
    chunk = text[start:end]
    assert chunk.count("self._lbl_filename.setTextFormat(Qt.TextFormat.PlainText)") == 1
    assert chunk.count("Qt.TextFormat.PlainText") == 1
    assert chunk.count('font-weight: bold; font-size: 14px;') == 1
    assert chunk.count('self._lbl_status = QLabel("")') == 1
    assert chunk.count("layout.addWidget(self._lbl_filename)") == 1
    assert chunk.count("layout.addWidget(self._lbl_status)") == 1


def test_desktop_main_detail_pane_preview_placeholder_label_styling() -> None:
    """Preview area uses a centered, minimum-height placeholder with light background before loading media."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index(
        '        self._preview_label = QLabel("(Select a document to preview)")'
    )
    end = text.index("        layout.addWidget(preview_group)", start)
    chunk = text[start:end]
    assert chunk.count("Qt.TextFormat.PlainText") == 1
    assert chunk.count("Qt.AlignmentFlag.AlignCenter") == 1
    assert chunk.count("setMinimumHeight(180)") == 1
    assert chunk.count("background: #f0f0f0") == 1
    assert chunk.count("preview_layout.addWidget(self._preview_label)") == 1


def test_desktop_main_detail_pane_four_action_buttons_toolbar_loop_and_styles() -> None:
    """Detail actions: four buttons, styles, ``clicked.connect``, layout stretch, then disabled until a doc loads."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("        # -- Action buttons --------------------------------------------------")
    end = text.index(
        "    def load_document(self, doc_id: int, db: DocumentDatabase):",
        start,
    )
    chunk = text[start:end]
    assert chunk.count("QPushButton(") == 4
    assert chunk.count("for btn in (self._btn_run, self._btn_approve, self._btn_post, self._btn_reject):") == 1
    assert chunk.count("btn.setMinimumHeight(32)") == 1
    assert chunk.count("self._btn_run.setStyleSheet(") == 1
    assert chunk.count("self._btn_reject.setStyleSheet(") == 1
    assert chunk.count("layout.addLayout(btn_layout)") == 1
    assert chunk.count("layout.addStretch()") == 1
    assert chunk.count("self._set_buttons_enabled(False)") == 1


def test_desktop_main_coa_select_placeholder_and_combo_refresh() -> None:
    """``_fill_coa_combo`` adds placeholder + non-empty COA rows; ``update_coa`` rebuilds and restores selection."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("_COA_SELECT_LABEL = ")
    end = text.index("    def clear_view(self):", start)
    chunk = text[start:end]
    assert "select" in chunk.split("_COA_SELECT_LABEL = ", 1)[1].split("\n", 1)[0]
    assert chunk.count("escape_ampersand_for_qt(_COA_SELECT_LABEL)") == 1
    assert chunk.count("def update_coa(self, coa_list: list[str]):") == 1
    assert "Refresh the COA dropdown with an updated list." in chunk
    assert chunk.count("def _fill_coa_combo(self, coa_list: list[str]) -> None:") == 1
    assert chunk.count('escape_ampersand_for_qt(_COA_SELECT_LABEL), ""') == 1
    assert chunk.count("for coa in coa_list:") == 1
    assert chunk.count("if not c:") == 1
    assert chunk.count("self._f_coa.addItem(escape_ampersand_for_qt(c), c)") == 1
    assert chunk.count("self._f_coa.clear()") == 1
    assert chunk.count("self._set_coa_combo_raw(current)") == 1
    assert chunk.count("def _coa_combo_raw_value(self) -> str | None:") == 1
    assert chunk.count("def _set_coa_combo_raw(self, raw: str | None) -> None:") == 1


def test_desktop_main_detail_pane_coa_combo_raw_value_read_branch_order() -> None:
    """``_coa_combo_raw_value`` checks index 0, list ``UserRole`` data, then falls back to edit text."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _coa_combo_raw_value(self) -> str | None:")
    end = text.index("    def _set_coa_combo_raw(self, raw: str | None) -> None:", start)
    chunk = text[start:end]
    i = chunk.index("i = self._f_coa.currentIndex()")
    z = chunk.index("        if i == 0:")
    pos = chunk.index("        if i > 0:")
    data = chunk.index("data = self._f_coa.itemData(i, Qt.ItemDataRole.UserRole)")
    t = chunk.index("t = self._f_coa.currentText().strip()")
    assert i < z < pos < data < t


def test_desktop_main_detail_pane_coa_combo_raw_read_and_set_by_data_or_free_text() -> None:
    """``_coa_combo_raw_value`` / ``_set_coa_combo_raw`` map list data, placeholder, and typed COA text."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _coa_combo_raw_value(self) -> str | None:")
    end = text.index("    def clear_view(self):", start)
    chunk = text[start:end]
    assert chunk.count("if i == 0:") == 1
    assert chunk.count("if i > 0:") == 1
    assert chunk.count("self._f_coa.itemData(i, Qt.ItemDataRole.UserRole)") == 1
    assert chunk.count("t == _COA_SELECT_LABEL") == 1
    assert chunk.count("if self._f_coa.count() == 0:") == 1
    assert chunk.count("self._f_coa.findData(r, Qt.ItemDataRole.UserRole)") == 1
    assert chunk.count("self._f_coa.setCurrentIndex(-1)") == 1
    assert chunk.count("self._f_coa.setEditText(r)") == 1


def test_desktop_main_detail_pane_clear_view_resets_doc_fields_and_disables_actions() -> None:
    """``clear_view`` clears selection, preview, extracted fields, COA row, and disables action buttons."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def clear_view(self):")
    end = text.index("class AppHeaderWidget(QFrame):", start)
    chunk = text[start:end]
    assert "Reset the detail pane when switching company database." in chunk
    assert chunk.count("self._doc_id = None") == 1
    assert chunk.count('self._lbl_filename.setText("No document selected")') == 1
    assert chunk.count("self._lbl_status.setTextFormat(Qt.TextFormat.PlainText)") == 1
    assert chunk.count('self._preview_label.setText("(Select a document to preview)")') == 1
    assert chunk.count("self._f_vendor.clear()") == 1
    assert chunk.count("self._f_notes.clear()") == 1
    assert chunk.count("self._f_tax_cat.clear()") == 1
    assert chunk.count("self._f_subtotal.setValue(0.0)") == 1
    assert chunk.count("self._f_tax.setValue(0.0)") == 1
    assert chunk.count("self._f_total.setValue(0.0)") == 1
    assert chunk.count('self._f_currency.setText("USD")') == 1
    assert chunk.count('self._f_confidence.setText("\\u2013")') == 1
    assert chunk.count("self._lbl_rationale.clear()") == 1
    assert chunk.count("self._set_buttons_enabled(False)") == 1


def test_desktop_main_detail_pane_clear_view_preview_notes_rationale_coa_before_disable_order() -> None:
    """``clear_view`` resets the preview stub, clears key fields, resets COA index, then disables actions."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def clear_view(self):")
    end = text.index("class AppHeaderWidget(QFrame):", start)
    chunk = text[start:end]
    pr = chunk.index('self._preview_label.setText("(Select a document to preview)")')
    v = chunk.index("self._f_vendor.clear()")
    n = chunk.index("self._f_notes.clear()")
    rat = chunk.index("self._lbl_rationale.clear()")
    coa = chunk.index("if self._f_coa.count() > 0:")
    dis = chunk.index("self._set_buttons_enabled(False)")
    assert pr < v < n < rat < coa < dis


def test_main_window_on_reject_sets_needs_review_refreshes_and_status_message() -> None:
    """Reject flags the document for review again, syncs inbox + detail, and updates the status bar."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_reject(self, doc_id: int):")
    end = text.index("    # -- helpers", start)
    chunk = text[start:end]
    assert chunk.count('self._db.set_status(did, "Needs Review")') == 1
    assert chunk.count("self._refresh_inbox()") == 1
    assert chunk.count("Document flagged \\u2013 Needs Review.") == 1


def test_extra_tabs_business_csv_export_tooltips_append_excel_bom_hint() -> None:
    """Business CSV exports and the filtered export scope dialog share one UTF-8 BOM suffix string."""
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    assert '_CSV_EXCEL_ENCODING_TIP = " UTF-8 with BOM for Excel."' in et
    assert et.count("_CSV_EXCEL_ENCODING_TIP") == 17


def test_extra_tabs_business_main_grids_mention_csv_utf8_bom_for_excel() -> None:
    """Rules / AR / AP / Payroll primary grids echo toolbar CSV encoding (Excel BOM)."""
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    needle = "CSV exports (toolbar) use UTF-8 BOM for Excel"
    rules = et.split("class RulesTab", 1)[1].split("class ARTab", 1)[0]
    ar = et.split("class ARTab", 1)[1].split("class APTab", 1)[0]
    ap = et.split("class APTab", 1)[1].split("class PayrollTaxTab", 1)[0]
    pay = et.split("class PayrollTaxTab", 1)[1].split("class TaxSettingsTab", 1)[0]
    for label, chunk in (
        ("RulesTab", rules),
        ("ARTab", ar),
        ("APTab", ap),
        ("PayrollTaxTab", pay),
    ):
        assert needle in chunk, f"{label} grid tooltip should mention {needle!r}"


def test_rules_tab_toolbar_buttons_have_tooltips() -> None:
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    start = et.index("class RulesTab")
    end = et.index("\n\nclass ARTab", start)
    chunk = et[start:end]
    for needle in (
        "rb_add.setToolTip",
        "rb_edit.setToolTip",
        "rb_del.setToolTip",
        "rb_export.setToolTip",
        "rb_import.setToolTip",
        "Read as UTF-8 with optional BOM (matches Export CSV… / Excel).",
        "pat.setToolTip",
        "Higher priority rules are considered first",
        "rules_tip.setToolTip",
    ):
        assert needle in chunk, f"Rules toolbar should set tooltip on {needle!r}"


def test_ar_tab_toolbar_buttons_have_tooltips() -> None:
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    start = et.index("class ARTab")
    end = et.index("\n\nclass APTab", start)
    chunk = et[start:end]
    for needle in (
        "ar_new_cust.setToolTip",
        "ar_edit_inv.setToolTip",
        "ar_record_pay.setToolTip",
        "ar_export_alloc.setToolTip",
        "ar_save_pdf.setToolTip",
        "ar_inv_add_line.setToolTip",
        "ar_inv_rm_line.setToolTip",
        "ar_pay_fill_old.setToolTip",
        "_inv_filter.setToolTip",
        "cust_filt.setToolTip",
        "line_tbl.setToolTip",
        "alloc_tbl.setToolTip",
        "lbl_ar_inv_filter.setToolTip",
        "lbl_ar_apply_hdr.setToolTip",
        "lbl_edit_inv_lines.setToolTip",
        "_ar_footer.setToolTip",
    ):
        assert needle in chunk, f"AR tab UI should set tooltip on {needle!r}"


def test_ap_tab_toolbar_buttons_have_tooltips() -> None:
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    start = et.index("class APTab")
    end = et.index("\n\nclass PayrollTaxTab", start)
    chunk = et[start:end]
    for needle in (
        "ap_new_v.setToolTip",
        "ap_edit_b.setToolTip",
        "ap_record_pay.setToolTip",
        "ap_export_alloc.setToolTip",
        "ap_pay_fill_old.setToolTip",
        "_bill_filter.setToolTip",
        "vend_filt.setToolTip",
        "Open bills for the selected vendor",
        "lbl_ap_bill_filter.setToolTip",
        "lbl_ap_apply_hdr.setToolTip",
        "_ap_footer.setToolTip",
    ):
        assert needle in chunk, f"AP tab UI should set tooltip on {needle!r}"


def test_ap_bill_new_and_edit_attachment_browse_buttons_have_tooltips() -> None:
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    assert et.count("ap_bill_att_browse.setToolTip") == 2


def test_payroll_tax_tab_toolbar_and_tax_codes_dialog_have_tooltips() -> None:
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    start = et.index("class PayrollTaxTab")
    end = et.index("\n\nclass TaxSettingsTab", start)
    chunk = et[start:end]
    for needle in (
        "pt_new_emp.setToolTip",
        "pt_post_gl.setToolTip",
        "pt_export_tax.setToolTip",
        "pt_tc_add.setToolTip",
        "pt_tc_close.setToolTip",
        "code.setToolTip",
        "exp.setToolTip",
        "Expense account debited for gross wages",
        "Include pay runs with pay date",
        "lbl_pt_run_tax_intro.setToolTip",
        "pt_grid_tip.setToolTip",
    ):
        assert needle in chunk, f"Payroll UI should set tooltip on {needle!r}"


def test_tax_settings_tab_buttons_have_tooltips() -> None:
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    start = et.index("class TaxSettingsTab")
    end = et.index("\n\ndef _business_keyboard_shortcuts_help_text", start)
    chunk = et[start:end]
    assert "ts_save.setToolTip" in chunk
    assert "ts_export_csv.setToolTip" in chunk
    assert "self._tax_name.setToolTip" in chunk
    assert "self._rate.setToolTip" in chunk
    assert "Include invoices dated on or after" in chunk
    assert "Include invoices dated on or before" in chunk
    assert "ts_tip.setToolTip" in chunk
    assert "export sales tax summary CSV uses UTF-8 BOM for Excel" in chunk
    assert "Export sales tax summary CSV uses UTF-8 BOM for Excel" in chunk


def test_extra_tabs_as_of_date_prompt_has_field_tooltip() -> None:
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    assert "def _prompt_as_of_date" in et
    start = et.index("def _prompt_as_of_date")
    end = et.index("def _prompt_list_csv_export_scope", start)
    chunk = et[start:end]
    assert "de.setToolTip" in chunk
    assert "Aging balances and buckets" in chunk
    assert "d.setToolTip(" in chunk
    assert "as-of date you confirm" in chunk


def test_extra_tabs_business_qdialog_windows_have_hover_tooltips() -> None:
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    for needle in (
        "higher priority rules are considered first",
        "Create a customer record used for AR invoices",
        "Edit invoice header, customer, line items",
        "Enter payment details and allocate amounts to open invoices",
        "Create a vendor record used for AP bills",
        "Enter payment details and allocate amounts to open bills",
        "Review company payroll tax codes",
        "Map wage expense, cash/bank, and withholdings liability",
        "d.setWindowTitle(\"New employee\")",
        "Choose invoice dates from/to",
    ):
        assert needle in et, f"extra_tabs.py should document modal window tooltips: {needle!r}"


def test_extra_tabs_dialog_button_boxes_use_tooltip_helpers() -> None:
    """QDialogButtonBox OK/Cancel and Save/Cancel get hover tips (Business + shared prompts)."""
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    assert "def _tip_dialog_ok_cancel" in et
    assert "def _tip_dialog_save_cancel" in et
    assert "_DIALOG_CANCEL_TIP" in et
    assert et.count("_tip_dialog_ok_cancel(bb") >= 15
    assert "_tip_dialog_save_cancel(\n            bb" in et
    assert "tip_qdialog_button_box(bb, ok=ok_tip, cancel=cancel_tip)" in et
    assert "tip_qdialog_button_box(bb, save=save_tip, cancel=cancel_tip)" in et


def test_extra_tabs_filtered_csv_export_scope_message_box_has_button_tooltips() -> None:
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    start = et.index("def _prompt_list_csv_export_scope")
    end = et.index("\n\n_DIALOG_CANCEL_TIP", start)
    chunk = et[start:end]
    assert "btn_vis.setToolTip" in chunk
    assert "btn_all.setToolTip" in chunk
    assert "box.setInformativeText" in chunk
    assert "UTF-8 with BOM for Excel" in chunk
    assert "_CSV_EXCEL_ENCODING_TIP" in chunk
    assert 'tip_message_box_buttons(box, cancel="Close without exporting.")' in chunk
    assert "box.setToolTip(" in chunk
    assert "list filter is active" in chunk


def test_qt_mnemonic_tip_message_box_buttons_helper() -> None:
    mn = (_DESKTOP_APP_DIR / "qt_mnemonic.py").read_text(encoding="utf-8")
    assert "CSV_EXPORT_OK_TIP_SUFFIX" in mn
    assert "UTF-8 with BOM for Excel" in mn
    assert "def tip_message_box_buttons" in mn
    assert "def message_box_information_ok" in mn
    assert "def message_box_warning_ok" in mn
    assert "def message_box_critical_ok" in mn
    assert "def message_box_about_ok" in mn
    assert "Qt.TextFormat.RichText" in mn
    assert "StandardButton.Yes" in mn
    assert "StandardButton.Cancel" in mn
    assert "y.setToolTip(yes)" in mn
    assert "n.setToolTip(no)" in mn
    assert "o.setToolTip(ok)" in mn
    assert "c.setToolTip(cancel)" in mn
    assert mn.count("box.setToolTip(ok_tip)") == 4
    assert "def tip_qdialog_button_box" in mn
    assert "QDialogButtonBox.StandardButton.Save" in mn
    assert "QDialogButtonBox.StandardButton.Close" in mn


def test_open_attachment_message_boxes_set_ok_button_tooltips() -> None:
    oa = (_DESKTOP_APP_DIR / "open_attachment.py").read_text(encoding="utf-8")
    assert oa.count("tip_message_box_buttons(") == 3
    assert oa.count("box.setToolTip(") == 3
    assert "StandardButton.Ok" in oa
    assert "File not found" in oa


def test_audit_dialog_shortcuts_help_uses_ok_button_tooltip() -> None:
    ad = (_DESKTOP_APP_DIR / "audit_dialog.py").read_text(encoding="utf-8")
    assert "def _audit_history_shortcuts_help" in ad
    assert "message_box_information_ok(" in ad
    assert "ok_tip=" in ad
    assert "dlg.setToolTip(" in ad
    assert "Field-level audit trail" in ad
    assert "tip_qdialog_button_box(box, close=" in ad
    h0 = ad.index("def _audit_history_shortcuts_help")
    h1 = ad.index("\n\ndef _audit_history_table_context_menu", h0)
    assert "+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX" in ad[h0:h1]


def test_desktop_app_avoids_static_qmessagebox_information_warning_critical() -> None:
    """Prefer helpers over static ``QMessageBox.*`` dialog methods so buttons get hover tooltips."""
    _assert_desktop_sources_avoid_static_qmessagebox_dialog_methods()


def test_desktop_app_avoids_raw_qdialogbuttonbox_button_lookup() -> None:
    """Standard-button tooltips go through ``tip_qdialog_button_box`` (or extra_tabs wrappers)."""
    _assert_desktop_sources_avoid_substring_except_in_qt_mnemonic(
        ".button(QDialogButtonBox",
        "use tip_qdialog_button_box or _tip_dialog_ok_cancel / _tip_dialog_save_cancel",
    )


def test_desktop_app_avoids_raw_qmessagebox_button_lookup() -> None:
    """Standard-button tooltips on ``QMessageBox`` go through ``tip_message_box_buttons`` (or helpers)."""
    _assert_desktop_sources_avoid_substring_except_in_qt_mnemonic(
        ".button(QMessageBox",
        "use tip_message_box_buttons or message_box_information_ok / warning_ok / critical_ok / about_ok",
    )


def test_main_window_uses_warning_and_critical_ok_helpers() -> None:
    main_t = _MAIN.read_text(encoding="utf-8")
    assert "message_box_warning_ok(" in main_t
    assert "message_box_critical_ok(" in main_t
    assert "message_box_about_ok(" in main_t
    assert "QMessageBox.about(" not in main_t


def test_main_window_message_box_information_ok_six_user_feedback_paths() -> None:
    """``MainWindow`` uses ``message_box_information_ok`` for copy path, roadmap, AI busy, backup/restore outcomes."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class MainWindow(QMainWindow):")
    end = text.index("\n\n# ---------------------------------------------------------------------------\n# Entry point", start)
    chunk = text[start:end]
    assert chunk.count("message_box_information_ok(") == 6


def test_main_window_message_box_warning_critical_and_file_dialog_counts() -> None:
    """``MainWindow`` keeps a stable mix of warning/critical dialogs and five file-picker call sites."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class MainWindow(QMainWindow):")
    end = text.index("\n\n# ---------------------------------------------------------------------------\n# Entry point", start)
    chunk = text[start:end]
    assert chunk.count("message_box_warning_ok(") == 8
    assert chunk.count("message_box_critical_ok(") == 5
    assert chunk.count("QFileDialog.getOpenFileNames(") == 1
    assert chunk.count("QFileDialog.getOpenFileName(") == 2
    assert chunk.count("QFileDialog.getSaveFileName(") == 2


def test_main_window_refresh_inbox_eight_call_sites() -> None:
    """``MainWindow`` refreshes the document inbox from import, AI, approval, and company switch paths."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class MainWindow(QMainWindow):")
    end = text.index("\n\n# ---------------------------------------------------------------------------\n# Entry point", start)
    chunk = text[start:end]
    assert chunk.count("self._refresh_inbox()") == 8


def test_main_window_inbox_widget_referenced_four_times() -> None:
    """``MainWindow`` connects the inbox, reads selection, and repopulates from one list call site."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class MainWindow(QMainWindow):")
    end = text.index("\n\n# ---------------------------------------------------------------------------\n# Entry point", start)
    chunk = text[start:end]
    assert chunk.count("self._inbox.") == 4


def test_main_window_detail_pane_eleven_call_sites() -> None:
    """``MainWindow`` wires the detail pane for signals, load/clear-on-deselect, AI populate, approve collect, COA."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class MainWindow(QMainWindow):")
    end = text.index("\n\n# ---------------------------------------------------------------------------\n# Entry point", start)
    chunk = text[start:end]
    assert chunk.count("self._detail.") == 11


def test_main_window_coa_database_four_call_sites() -> None:
    """``MainWindow`` seeds COA at startup/reload and reads ``display_list`` for the detail pane and COA tab."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class MainWindow(QMainWindow):")
    end = text.index("\n\n# ---------------------------------------------------------------------------\n# Entry point", start)
    chunk = text[start:end]
    assert chunk.count("self._coa_db.") == 4


def test_main_window_banner_tabs_status_bar_and_worker_counts() -> None:
    """Chrome widgets and ``self._worker`` substring occurrences (busy guards count twice per line)."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class MainWindow(QMainWindow):")
    end = text.index("\n\n# ---------------------------------------------------------------------------\n# Entry point", start)
    chunk = text[start:end]
    assert chunk.count("self._header.") == 2
    assert chunk.count("self._status_bar.showMessage(") == 12
    assert chunk.count("self._tabs.") == 31
    assert chunk.count("self._worker") == 13


def test_main_window_bank_database_closes_and_applies_extensions_twice() -> None:
    """``BankDatabase`` is closed on switch/restore/quit; ``apply_extensions`` runs on open and reload."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class MainWindow(QMainWindow):")
    end = text.index("\n\n# ---------------------------------------------------------------------------\n# Entry point", start)
    chunk = text[start:end]
    assert chunk.count("self._bank_db.close()") == 3
    assert chunk.count("apply_extensions(self._bank_db._conn)") == 2


def test_main_window_sqlite_layers_constructed_twice_and_document_db_closed_thrice() -> None:
    """Boot and ``_load_company_at_path`` each build document/bank/GL/COA; closing matches bank shutdown sites."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class MainWindow(QMainWindow):")
    end = text.index("\n\n# ---------------------------------------------------------------------------\n# Entry point", start)
    chunk = text[start:end]
    assert chunk.count("self._db.close()") == 3
    assert chunk.count("DocumentDatabase(") == 2
    assert chunk.count("BankDatabase(") == 2
    assert chunk.count("GLDatabase(") == 2
    assert chunk.count("COADatabase(") == 2


def test_main_window_coa_tab_changed_signal_wired_after_initial_and_rebuild() -> None:
    """``COATab.coaChanged`` is connected in ``_build_ui`` and again after ``_rebuild_bank_related_tabs``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class MainWindow(QMainWindow):")
    end = text.index("\n\n# ---------------------------------------------------------------------------\n# Entry point", start)
    chunk = text[start:end]
    assert chunk.count("self._coa_tab.coaChanged.connect(self._on_coa_changed)") == 2


def test_main_window_load_coa_three_times_seed_workbook_twice() -> None:
    """``load_coa`` runs at startup, on COA edits, and after company reload; workbook seed matches bank reopen."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class MainWindow(QMainWindow):")
    end = text.index("\n\n# ---------------------------------------------------------------------------\n# Entry point", start)
    chunk = text[start:end]
    assert chunk.count("load_coa()") == 3
    assert chunk.count("seed_from_workbook()") == 2


def test_main_window_document_database_call_counts_for_intake_and_workflow() -> None:
    """``MainWindow`` uses ``DocumentDatabase`` for listing, fetch, import, AI save, approve, and six status updates."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class MainWindow(QMainWindow):")
    end = text.index("\n\n# ---------------------------------------------------------------------------\n# Entry point", start)
    chunk = text[start:end]
    assert chunk.count("self._db.list_documents()") == 1
    assert chunk.count("self._db.get_document(did)") == 3
    assert chunk.count("self._db.add_document(path, mime, store=True)") == 1
    assert chunk.count("self._db.save_extraction(did, result)") == 1
    assert chunk.count("self._db.save_approved(did, values)") == 1
    assert chunk.count("self._db.set_status(did,") == 6
    assert chunk.count("application_version()") == 4


def test_main_window_custom_qmessagebox_yes_no_defaults_to_no() -> None:
    """Destructive Yes/No prompts build ``QMessageBox(self)`` and default to **No**."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class MainWindow(QMainWindow):")
    end = text.index("\n\n# ---------------------------------------------------------------------------\n# Entry point", start)
    chunk = text[start:end]
    assert chunk.count("QMessageBox(self)") == 2
    assert chunk.count("box.setDefaultButton(QMessageBox.StandardButton.No)") == 2


def test_about_dialog_ok_tip_mentions_file_backup_cli_parity() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("def _on_about")
    chunk = text[start : text.index("def _on_import", start)]
    assert "probooks.backup" in chunk
    assert "File → Backup/Restore" in chunk
    assert "status bar" in chunk
    assert "banner name tooltip" in chunk


def test_help_about_menu_tip_mentions_ok_backup_hint() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("act_about = QAction")
    chunk = text[start : text.index("help_menu.addAction(act_about)", start)]
    assert "probooks.backup" in chunk
    assert "File backup" in chunk


def test_help_menu_bank_register_business_shortcuts_tips_point_at_intake_backup() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    assert text.count("Document intake help lists File backup/restore.") >= 3


def test_help_keyboard_shortcuts_dialog_ok_tips_mention_company_db_backup() -> None:
    needle = "Company .db: File → Backup / Restore (probooks.backup)."
    main_t = _MAIN.read_text(encoding="utf-8")
    midx = main_t.index("def show_document_intake_keyboard_shortcuts_dialog")
    inc = main_t[midx : main_t.index("\n\n# Accepted MIME", midx)]
    assert needle in inc
    assert "register bulk actions: Recon menu" in inc
    bi = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    bidx = bi.index("def show_bank_import_keyboard_shortcuts_dialog")
    b = bi[bidx : bi.index("\n\n# =====", bidx)]
    assert needle in b
    assert "register bulk actions" in b and "Recon" in b
    assert "Ctrl+3" in b and "Stmt match" in b
    reg = (_DESKTOP_APP_DIR / "register_tab.py").read_text(encoding="utf-8")
    ridx = reg.index("def show_register_keyboard_shortcuts_dialog")
    r = reg[ridx : reg.index("\n\nclass RegisterTab", ridx)]
    assert needle in r
    assert "Recon menu" in r and "Register Actions" in r
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    bidx = et.index("def show_business_keyboard_shortcuts_dialog")
    e = et[bidx : et.index("\n\nclass BusinessHub", bidx)]
    assert needle in e
    assert "+ VIEW_BANK_REGISTER_KEYS_TOOLTIP" in e
    mm = (_DESKTOP_APP_DIR / "more_main_tabs_shortcuts.py").read_text(encoding="utf-8")
    m = mm.split("show_more_main_tabs_keyboard_shortcuts_dialog", 1)[1].split("def ", 1)[0]
    assert needle in m
    assert "+ VIEW_BANK_REGISTER_KEYS_TOOLTIP" in m


def test_help_menu_keyboard_shortcuts_dialogs_use_information_ok_helper() -> None:
    """Help → shortcuts dialogs should set Ok hover text via message_box_information_ok."""
    main_t = _MAIN.read_text(encoding="utf-8")
    assert "message_box_information_ok(" in main_t
    assert "Document intake shortcuts" in main_t
    bi = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    assert "show_bank_import_keyboard_shortcuts_dialog" in bi
    assert "message_box_information_ok(" in bi
    reg = (_DESKTOP_APP_DIR / "register_tab.py").read_text(encoding="utf-8")
    assert "message_box_information_ok(" in reg
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    assert "show_business_keyboard_shortcuts_dialog" in et
    assert "message_box_information_ok(" in et
    mm = (_DESKTOP_APP_DIR / "more_main_tabs_shortcuts.py").read_text(encoding="utf-8")
    assert "message_box_information_ok(" in mm
    assert "More tab shortcuts (F5)" in mm


def test_intake_and_bank_import_splitters_have_resize_tooltips() -> None:
    main_t = _MAIN.read_text(encoding="utf-8")
    assert "splitter.setToolTip" in main_t
    assert "document inbox" in main_t
    sp = main_t.index("Drag the handle to resize the document inbox")
    assert "File → Backup" in main_t[sp : sp + 400]
    assert "View → Bank Import" in main_t[sp : sp + 400]
    bi = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    assert "splitter.setToolTip" in bi
    assert "right_splitter.setToolTip" in bi
    assert "reconciliation" in bi
    assert "left.setToolTip(" in bi
    assert "Import batches column" in bi


def test_destructive_yes_no_message_boxes_use_shared_button_tooltips() -> None:
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    assert et.count("tip_message_box_buttons") >= 2
    assert "Permanently remove this rule" in et
    assert "Remove this categorization rule from the company database" in et
    assert "File → Backup" in et and "probooks backup" in et.split(
        "Remove this categorization rule from the company database", 1
    )[1][:400]
    assert "Import deletes every existing rule" in et
    ridx = et.index("Import deletes every existing rule and replaces")
    assert "File → Backup" in et[ridx : ridx + 280]
    coa = (_DESKTOP_APP_DIR / "coa_tab.py").read_text(encoding="utf-8")
    assert "tip_message_box_buttons" in coa
    assert "hides from pick lists" in coa
    assert "File → Backup before wide COA changes" in coa
    cde = coa.index("Deactivated accounts stay in the database")
    assert "File → Backup" in coa[cde : cde + 220]
    bi = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    assert "tip_message_box_buttons" in bi
    bdel = bi.index("Permanently removes this bank account")
    assert "File → Backup" in bi[bdel : bdel + 220]
    main_t = _MAIN.read_text(encoding="utf-8")
    assert main_t.count("tip_message_box_buttons") >= 2
    assert "Overwrite the live company .db" in main_t
    assert "File → Backup first" in main_t
    assert main_t.count("box.setToolTip(") >= 2
    assert "This path already exists; Yes opens it" in main_t
    assert "File → Backup / probooks backup on the current file first" in main_t
    assert "Restore overwrites the active company database" in main_t


def test_business_hub_f5_refresh_current_subtab_shortcut_wired() -> None:
    path = _DESKTOP_APP_DIR / "extra_tabs.py"
    text = path.read_text(encoding="utf-8")
    assert "sc_business_f5" in text
    assert 'QKeySequence("F5")' in text
    assert "sc_business_f5.activated.connect(self._refresh_current_subtab)" in text
    assert "def _refresh_current_subtab" in text


def test_extra_tabs_filtered_entity_combo_uses_qt_combo_ids() -> None:
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    qi = et.index("from desktop_app.qt_combo_ids import")
    qj = et.index("\n\n", qi)
    id_block = et[qi:qj]
    assert "coerce_combo_int_id" in id_block
    assert "combo_index_for_int_user_data" in id_block
    assert "combo_int_ids_equal" in id_block
    sync = et.split("def _sync_filtered_entity_combo", 1)[1].split(
        "def _prompt_as_of_date", 1
    )[0]
    assert "prev_id = coerce_combo_int_id(cb.currentData())" in sync
    assert "combo_index_for_int_user_data(cb, prev_id)" in sync


def test_extra_tabs_exposes_business_shortcuts_dialog_for_help_menu() -> None:
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    assert "def show_business_keyboard_shortcuts_dialog" in et
    assert "def _business_keyboard_shortcuts_help_text" in et
    bus_help = et.split("def _business_keyboard_shortcuts_help_text", 1)[1].split(
        "def show_business_keyboard_shortcuts_dialog", 1
    )[0]
    assert "UTF-8 with BOM for Excel" in bus_help
    assert "Rules Import CSV" in bus_help and "optional BOM" in bus_help
    assert "View menu tab focus: Ctrl+1 Document Intake, Ctrl+2 Bank Import, Ctrl+3 Register, " in bus_help
    assert (
        "Ctrl+4 Chart of Accounts, Ctrl+5 Reports, Ctrl+6 Journal, Ctrl+7 Business, Ctrl+8 Audit log."
        in bus_help
    )
    assert "Register bulk actions" in bus_help and "main **Recon** menu" in bus_help
    assert (
        et.count("lambda: show_business_keyboard_shortcuts_dialog(self)") == 4
    ), "Rules, AR, AP, Payroll grids should open Business shortcuts from context menu"
    assert (
        "show_business_keyboard_shortcuts_dialog(menu_parent)"
        in et[et.index("def _attach_table_copy_row_menu") : et.index("def _wire_find_focuses_line_edit")]
    ), "Business dialog tables should open Business shortcuts from context menu"


def test_qt_combo_ids_module_defines_int_user_data_helpers() -> None:
    t = (_DESKTOP_APP_DIR / "qt_combo_ids.py").read_text(encoding="utf-8")
    assert "def coerce_combo_int_id" in t
    assert "def combo_int_ids_equal" in t
    assert "def combo_index_for_int_user_data" in t
    assert "start: int = 0" in t


def test_extra_tabs_save_entity_and_payment_bank_use_coerce_combo_int_id() -> None:
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    pay = et.split("def _save_payment_bank_choice", 1)[1].split(
        "_NEW_INVOICE_CUSTOMER_KEY", 1
    )[0]
    assert "coerce_combo_int_id(cb.itemData(idx))" in pay
    ent = et.split("def _save_entity_combo", 1)[1].split(
        "def _sync_filtered_entity_combo", 1
    )[0]
    assert "coerce_combo_int_id(cb.currentData())" in ent


def test_extra_tabs_restore_payment_bank_uses_combo_index_start_one() -> None:
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    fn = et.split("def _restore_payment_bank_combo", 1)[1].split(
        "def _save_payment_bank_choice", 1
    )[0]
    assert "bid = coerce_combo_int_id(raw)" in fn
    assert "combo_index_for_int_user_data(cb, bid, start=1)" in fn


def test_extra_tabs_new_pay_run_coerces_employee_combo_id() -> None:
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    chunk = et.split("def _new_run(self):", 1)[1].split("class TaxSettingsTab", 1)[0]
    assert "eid = coerce_combo_int_id(cb.currentData())" in chunk
    assert "business.create_payroll_run(\n            self._conn,\n            eid," in chunk


def test_extra_tabs_sync_entity_combo_and_ar_ap_payments_coerce_int_ids() -> None:
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    rent = et.split("def _restore_entity_combo", 1)[1].split(
        "def _save_entity_combo", 1
    )[0]
    assert "eid = coerce_combo_int_id(raw)" in rent
    sync = et.split("def _sync_filtered_entity_combo(", 1)[1].split(
        "def _prompt_as_of_date", 1
    )[0]
    assert "prev_id = coerce_combo_int_id(cb.currentData())" in sync
    assert "combo_index_for_int_user_data(cb, prev_id)" in sync
    ar = et.split("def rebuild_ar_alloc_table", 1)[1].split("def sync_ar_payment_customers", 1)[0]
    assert "cid = coerce_combo_int_id(cust_cb.currentData())" in ar
    ar_pay = et.split("if d.exec() != QDialog.DialogCode.Accepted:\n            return\n        cid = coerce_combo_int_id(cust_cb.currentData())", 1)[
        1
    ].split("business.record_ar_payment", 1)[0]
    assert "iid = coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole))" in ar_pay
    assert (
        "bank_account_id = (\n            coerce_combo_int_id(bank_cb.itemData(bidx)) if bidx > 0 else None\n        )"
        in et
    )
    assert "business.record_ar_payment(\n            self._conn,\n            cid," in et
    assert "business.record_ap_payment(\n            self._conn,\n            vid," in et


def test_bank_import_tab_account_combo_uses_int_safe_restore_and_current_data() -> None:
    """Bank Import account combo restores selection and reads currentData with int coercion (like Register)."""
    bit = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    ref = bit.split("def _refresh_accounts(self):", 1)[1].split(
        "def _on_account_changed", 1
    )[0]
    assert "combo_index_for_int_user_data" in ref
    oc = bit.split("def _on_account_changed(self):", 1)[1].split(
        "def _refresh_batches", 1
    )[0]
    assert "aid = coerce_combo_int_id(self._acct_combo.currentData())" in oc


def test_bank_import_tab_batch_and_txn_tables_coerce_user_role_ids() -> None:
    bit = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    assert "combo_int_ids_equal" in bit
    sel = bit.split("def _selected_account(self):", 1)[1].split("def _on_add(self):", 1)[0]
    assert "coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole))" in sel
    reload_chunk = bit.split("def _reload_bank_import_view", 1)[1].split(
        "def _show_bank_import_keyboard_shortcuts_help", 1
    )[0]
    assert "combo_int_ids_equal(bid, saved_batch)" in reload_chunk
    batch_sel = bit.split("def _on_batch_selected(self):", 1)[1].split(
        "def _on_reconciliation_tolerance_changed", 1
    )[0]
    assert "combo_int_ids_equal(b[\"id\"], bid)" in batch_sel
    txn_ctx = bit.split("def _on_import_txn_context_menu", 1)[1].split(
        "def _open_import_txn_attachment", 1
    )[0]
    assert "tid = (\n            coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole))" in txn_ctx
    assert "Copy payee / description" in txn_ctx
    assert "Copy date" in txn_ctx
    assert "Copy transaction id" in txn_ctx
    assert "_copy_import_txn_id" in txn_ctx
    assert "_copy_import_txn_date" in txn_ctx
    assert "Copy amount" in txn_ctx
    assert "_copy_import_txn_amount" in txn_ctx
    assert "Copy memo" in txn_ctx
    assert "Copy number / ref" in txn_ctx
    assert "Copy category (COA)" in txn_ctx
    assert "_copy_import_txn_description" in txn_ctx
    assert "_copy_import_txn_memo" in txn_ctx
    assert "_copy_import_txn_ref_number" in txn_ctx
    assert "_copy_import_txn_coa" in txn_ctx
    tol_chunk = bit.split("def _on_reconciliation_tolerance_changed", 1)[1].split(
        "def _load_batch", 1
    )[0]
    assert "combo_int_ids_equal(b[\"id\"], self._current_batch_id)" in tol_chunk
    assert "_clip_import_txn_string_field" in bit
    assert (
        bit.count("(F5, batches, register preview, AI line reconciliation, row field copies)")
        == 2
    )
    assert (
        "(F5, batches, Manage accounts, register preview, AI line reconciliation, row field copies)"
        in bit
    )


def test_extra_tabs_rules_edit_matches_rule_row_by_int_safe_id() -> None:
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    edit = et.split("def _edit(self):", 1)[1].split("def _del(self):", 1)[0]
    assert "combo_int_ids_equal(x[\"id\"], rid)" in edit


def test_extra_tabs_payroll_post_gl_matches_run_row_by_int_safe_id() -> None:
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    post = et.split("def _post_gl(self):", 1)[1].split("def _new_emp(self):", 1)[0]
    assert "combo_int_ids_equal(x[\"id\"], rid)" in post


def test_extra_tabs_payroll_run_tax_lines_lookup_uses_coerce_combo_int_id() -> None:
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    chunk = et.split("def _edit_run_taxes(self):", 1)[1].split(
        "def _on_payroll_run_double_clicked", 1
    )[0]
    assert "coerce_combo_int_id(row[\"tax_item_id\"])" in chunk
    assert "if (lid := coerce_combo_int_id(it[\"id\"])) is not None" in chunk
    assert "prev = existing.get(lid)" in chunk


def test_extra_tabs_edit_invoice_and_bill_coerce_customer_vendor_ids() -> None:
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    inv = et.split("def _edit_inv(self):", 1)[1].split("def _record_ar_payment(self):", 1)[0]
    assert "inv_cust_id = coerce_combo_int_id(inv[\"customer_id\"])" in inv
    bill = et.split("def _edit_b(self):", 1)[1].split("def _record_ap_payment(self):", 1)[0]
    assert "bill_vid = coerce_combo_int_id(b[\"vendor_id\"])" in bill


def test_bank_import_keyboard_shortcuts_help_text_lists_view_chords() -> None:
    bit = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    start = bit.index("def _bank_import_keyboard_shortcuts_help_text")
    end = bit.index("\n\n\ndef show_bank_import_keyboard_shortcuts_dialog", start)
    chunk = bit[start:end]
    assert (
        "View menu tab focus: Ctrl+1 Document Intake, Ctrl+2 Bank Import, Ctrl+3 Register."
        in chunk
    )
    assert "Recon" in chunk and "Register Actions" in chunk


def test_bank_import_tab_f5_reload_shortcut_wired() -> None:
    path = _DESKTOP_APP_DIR / "bank_import_tab.py"
    text = path.read_text(encoding="utf-8")
    assert "def _reload_bank_import_view" in text
    assert 'QKeySequence("F5")' in text
    assert "activated.connect(self._reload_bank_import_view)" in text
    assert "F5 refreshes accounts and import batches" in text
    _f5_tail = text.split("F5 refreshes accounts and import batches", 1)[1][:900]
    assert "UTF-8 BOM for Excel" in _f5_tail
    assert "probooks.backup" in _f5_tail
    assert "AI line-reconciliation grid" in _f5_tail
    assert "preview rows and that grid also offer Copy row" in _f5_tail
    assert "Manage Bank Accounts table" in text
    assert "Bank import shortcuts" in text
    assert "Keyboard shortcuts…" in text
    assert "_show_bank_import_keyboard_shortcuts_help" in text


def test_bank_import_tab_csv_import_file_dialog_caption() -> None:
    """CSV import picker explains mapping step and uses consistent filter wording."""
    bit = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    assert "Import bank transactions CSV (map columns next)" in bit
    assert "CSV spreadsheets (*.csv);;All files (*.*)" in bit


def test_bank_import_tab_imports_bank_database_not_parse_csv() -> None:
    """Tab uses ``BankDatabase.import_csv``; low-level ``parse_csv`` stays in ``probooksai.bank_import`` only."""
    bit = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    lines = [ln for ln in bit.splitlines() if ln.startswith("from probooksai.bank_import import")]
    assert len(lines) == 1
    assert "ACCOUNT_TYPES" in lines[0]
    assert "BankDatabase" in lines[0]
    assert "BANK_CSV_READ_ENCODING" in lines[0]
    assert "parse_csv" not in lines[0]


def test_bank_import_csv_export_paths_wires_bidirectional_folder_fallbacks() -> None:
    """Open dialog: import dir then export dir. Save path: export dir then import dir."""
    p = (_DESKTOP_APP_DIR / "bank_import_csv_export_paths.py").read_text(encoding="utf-8")
    open_fn = p.split("def bank_import_open_dialog_start_dir", 1)[1].split(
        "def remember_bank_import_import_dir", 1
    )[0]
    assert "_resolved_import_parent(s)" in open_fn
    assert "_resolved_export_parent(s)" in open_fn
    save_fn = p.split("def bank_import_csv_default_save_path", 1)[1].split(
        "def remember_bank_import_csv_export_parent", 1
    )[0]
    assert "_resolved_export_parent(s)" in save_fn
    assert "_resolved_import_parent(s)" in save_fn


def test_csv_import_worker_module_documents_decoded_utf8_sig_content() -> None:
    text = (_DESKTOP_APP_DIR / "csv_import_worker.py").read_text(encoding="utf-8")
    assert "BANK_CSV_READ_ENCODING" in text
    assert "csv_content" in text


def test_bank_import_csv_flow_column_map_then_statement_then_worker() -> None:
    """CSV path: map columns → statement period → save profile → threaded import with progress UI."""
    bit = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    start = bit.index("    def _on_import_csv(self):")
    end = bit.index("\n    def _on_manage_accounts(self):", start)
    chunk = bit[start:end]
    assert "bank_import_open_dialog_start_dir()" in chunk
    assert "remember_bank_import_import_dir(path)" in chunk
    i_col = chunk.index("col_dlg = ColumnMappingDialog")
    i_per = chunk.index("period_dlg = StatementPeriodDialog")
    i_save = chunk.index("self._db.save_import_column_profile")
    i_work = chunk.index("worker = CsvImportWorker")
    assert i_col < i_per < i_save < i_work
    assert "read_text(encoding=BANK_CSV_READ_ENCODING)" in chunk
    assert 'prog_dlg.setWindowTitle("Importing bank CSV")' in chunk
    assert "CSV import progress. Cancel stops further rows" in chunk


def test_bank_import_tab_reconciliation_export_file_dialog_caption() -> None:
    """Reconciliation export save dialog states format and matches CSV filter wording."""
    bit = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    bio = (REPO_ROOT / "probooksai" / "bank_import.py").read_text(encoding="utf-8")
    ex = bio.split("def export_batch_reconciliation_csv", 1)[1].split(
        "    def import_transactions", 1
    )[0]
    assert 'encoding="utf-8-sig"' in ex
    assert "Save bank reconciliation report (CSV)" in bit
    assert "def _suggested_reconciliation_csv_filename(self)" in bit
    assert "suggested_bank_import_batch_csv_filename" in bit
    assert "bank_import_csv_default_save_path" in bit
    assert "remember_bank_import_csv_export_parent" in bit
    start = bit.index("def _on_export_reconciliation_csv(self):")
    end = bit.index("\n\n    def _on_reconcile(self):", start)
    chunk = bit[start:end]
    assert chunk.count("CSV spreadsheets (*.csv);;All files (*.*)") == 1
    assert 'path += ".csv"' in chunk


def test_bank_import_blank_register_table_columns_empty_rows_and_pdf_dialog() -> None:
    """Right pane: blank register shell (Date…Balance, 15 editable empty rows, Register tab styling) + PDF caption."""
    bit = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    assert "BlankBankRegisterTable()" in bit
    assert "Import bank statement PDF (selectable text required)" in bit
    pdf_chunk = bit.split("def _on_import_pdf(self):", 1)[1].split(
        "def _on_import_csv(self):", 1
    )[0]
    assert "bank_import_open_dialog_start_dir()" in pdf_chunk
    assert "remember_bank_import_import_dir(path)" in pdf_chunk
    start = bit.index("class BlankBankRegisterTable")
    end = bit.index(
        "\n\n# ===========================================================================\n# ReconciliationPanel",
        start,
    )
    chunk = bit[start:end]
    assert 'COLUMNS = ["Date", "Description", "Debit", "Credit", "Balance"]' in chunk
    assert "DEFAULT_ROW_COUNT = 15" in chunk
    assert "setRowCount(self.DEFAULT_ROW_COUNT)" in chunk
    assert 'QTableWidgetItem("")' in chunk
    assert "register_table_style_sheet()" in chunk
    assert "RegisterBandDelegate(" in chunk and "simple_band_rows=True" in chunk
    init_body = chunk.split("def __init__(self, parent=None):", 1)[1].split(
        "\n    def reset_blank", 1
    )[0]
    assert init_body.index("self.setItemDelegate(") < init_body.index("self.reset_blank()")
    assert "setDefaultSectionSize(REGISTER_ROW_HEIGHT_MIN_PREVIEW)" in init_body
    assert 'setObjectName("bankRegisterTable")' in chunk
    assert "EditTrigger.DoubleClicked" in chunk
    assert "NoEditTriggers" not in chunk
    assert "def reset_blank(self)" in chunk
    assert "def populate_import_batch(" in chunk
    assert "beginning_balance: Optional[float]" in chunk
    assert "date_it.setToolTip" in chunk and "desc_it.setToolTip" in chunk
    assert "debit_it.setToolTip" in chunk and "credit_it.setToolTip" in chunk
    assert "bal_it.setToolTip" in chunk and "Running balance:" in chunk
    assert "running + amt" in chunk or "running = round(running + amt" in chunk
    assert "amt > 0" in chunk and "amt < 0" in chunk
    assert "_HEADER_TIPS" in chunk
    assert "horizontalHeaderItem(col)" in chunk
    assert "Running total after each row when the batch has a beginning balance " in chunk
    assert "CSV exports in reconciliation below use UTF-8 BOM for Excel" in chunk
    assert "+ VIEW_BANK_REGISTER_KEYS_TOOLTIP" in init_body
    assert "AMOUNT_NEGATIVE" in chunk
    assert "bal_it.setForeground" in chunk
    assert chunk.count("setData(QTABLE_PLAIN_TEXT_ROLE,") >= 3
    assert "debit_it.setForeground(QColor(AMOUNT_POSITIVE))" in chunk
    assert "credit_it.setForeground(QColor(AMOUNT_NEGATIVE))" in chunk
    assert "lbl_recon_header" in bit
    assert "Statement reconciliation:" in bit
    assert "_recon_placeholder" in bit
    assert "_recon_panel_empty_hint" in bit


def test_bank_import_load_batch_populates_register_preview() -> None:
    """Selecting a batch fills the register preview from ``list_transactions``."""
    bit = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    start = bit.index("    def _load_batch(self, batch):")
    end = bit.index("\n    # -----------------------------------------------------------------------", start)
    chunk = bit[start:end]
    assert chunk.count("self._txn_table.populate_import_batch(") == 1
    assert "beginning_balance=batch.get(" in chunk
    assert "list_transactions(" in chunk


def test_bank_import_tab_wires_ai_statement_line_match_panel() -> None:
    """Bank Import embeds mock extract vs register reconciliation (Matched / Missing / Extra)."""
    bit = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    assert "from desktop_app.statement_line_match_panel import StatementLineMatchPanel" in bit
    assert "StatementLineMatchPanel(" in bit
    assert "_line_match_panel" in bit
    assert "_line_match_panel.set_context(" in bit
    assert "line_match_results_ready.connect" in bit
    assert "_forward_line_match_to_register" in bit
    assert "if applied and fn is not None:" in bit
    assert "Stmt match sync" in bit
    assert "Stmt match was not updated" in bit
    fwd = bit.split("    def _forward_line_match_to_register", 1)[1].split(
        "    def _build_ui(self):", 1
    )[0]
    assert "coerce_combo_int_id(bank_account_id)" in fwd
    assert "Invalid bank account id for Stmt match sync." in fwd
    assert "after_stmt_match_sync" in bit
    assert "_after_stmt_match_sync" in bit
    sm = (_DESKTOP_APP_DIR / "statement_line_match_panel.py").read_text(encoding="utf-8")
    assert "from desktop_app.bank_import_csv_export_paths import" in sm
    assert "suggested_bank_import_batch_csv_filename" in sm
    assert "from desktop_app.qt_combo_ids import coerce_combo_int_id" in sm
    assert "customContextMenuRequested" in sm
    assert "copy_table_row_as_tsv" in sm
    assert "Copy register transaction id" in sm
    assert "Copy statement date" in sm
    assert "Copy statement amount" in sm
    assert "Copy statement description" in sm
    assert "Copy register date" in sm
    assert "Copy register amount" in sm
    assert "Copy register description" in sm
    assert "_line_match_stmt_date_plain" in sm
    assert "_line_match_stmt_amount_plain" in sm
    assert "_line_match_stmt_description_plain" in sm
    assert "_line_match_reg_date_plain" in sm
    assert "_line_match_reg_amount_plain" in sm
    assert "_line_match_reg_description_plain" in sm
    assert "_copy_line_match_stmt_date" in sm
    assert "_copy_line_match_stmt_amount" in sm
    assert "_copy_line_match_stmt_description" in sm
    assert "_copy_line_match_reg_date" in sm
    assert "_copy_line_match_reg_amount" in sm
    assert "_copy_line_match_reg_description" in sm
    assert "_copy_line_match_register_id" in sm
    assert "_line_match_register_id_plain" in sm
    assert "bank_import_shortcuts_help" in sm
    assert "Right-click the table for Copy row and statement/register field copies" in sm
    assert "View → Bank Import (Ctrl+2), Register (Ctrl+3)" in sm
    assert "+ VIEW_BANK_REGISTER_KEYS_TOOLTIP" in sm
    assert "StatementLineMatchPanel(" in bit and "bank_import_shortcuts_help=" in bit
    run_sm = sm.split("def _on_run_clicked", 1)[1].split("def _mark_reviewed_selected", 1)[0]
    assert "coerce_combo_int_id(b.get(\"bank_account_id\"))" in run_sm
    assert "line_match_results_ready = Signal(int, list)" in sm
    assert "Run mock extract & compare" in sm
    assert "compare_statement_to_register" in sm
    assert "write_line_match_comparison_csv" in sm
    slm_py = (REPO_ROOT / "probooksai" / "statement_line_match.py").read_text(encoding="utf-8")
    wcsv = slm_py.split("def write_line_match_comparison_csv", 1)[1].split(
        "def mock_statement_lines_for_comparison", 1
    )[0]
    assert 'encoding="utf-8-sig"' in wcsv
    assert "UTF-8 CSV with BOM" in sm
    assert "AI line reconciliation, row field copies" in sm
    assert "Export comparison CSV uses UTF-8 with BOM for Excel" in sm
    assert "Export comparison CSV" in sm
    assert "Export report CSV" in sm
    assert "last import folder" in sm
    assert "last import folder if you have not exported CSV yet" in sm
    assert "appends .csv" in sm
    assert "_refresh_match_summary_footer" in sm
    assert "_refresh_reconciled_action_states" in sm
    assert "selectionChanged.connect" in sm
    assert "act_export = menu.addAction" in sm
    assert "_suggested_line_compare_csv_filename" in sm
    export_sm = sm.split("def _on_export_comparison_csv", 1)[1].split(
        "def _on_run_clicked", 1
    )[0]
    assert 'path += ".csv"' in export_sm
    assert "bank_import_csv_default_save_path" in export_sm
    assert "remember_bank_import_csv_export_parent" in export_sm
    assert "STATUS_MATCHED" in sm
    assert "Bank register" in sm
    assert "status bar" in sm.lower()
    assert "company line" in sm.lower()
    assert "returns after" in sm.lower() or "returns." in sm.lower()


def test_bank_import_recon_panel_empty_hint_when_no_batch_selected() -> None:
    """Reconciliation stack shows a fixed line when batches exist but none is selected."""
    bit = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    msg = "Select a batch on the left to view statement reconciliation"
    assert msg in bit
    hint_idx = bit.index("_recon_panel_empty_hint = QLabel")
    assert "color: #A0A0B0; font-size: 11px;" in bit[hint_idx : hint_idx + 400]
    sync_start = bit.index("    def _sync_right_pane_placeholder_visibility(self)")
    sync_end = bit.index("    def _reload_bank_import_view(self)", sync_start)
    sync = bit[sync_start:sync_end]
    assert sync.count("self._recon_panel_empty_hint.setVisible(True)") == 1
    assert sync.count("self._recon_panel_empty_hint.setVisible(False)") == 2


def test_bank_import_tab_shows_batch_workflow_hint_by_batch_list() -> None:
    """Bank Import left pane explains how batches appear and what selection does."""
    bit = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    assert "batch_hint" in bit
    assert "Batches appear after you" in bit


def test_bank_import_tab_shows_import_format_hint_under_header() -> None:
    """Bank Import shows a visible CSV vs PDF (text-layer) hint below the import buttons."""
    bit = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    assert "Import formats:" in bit
    assert "import_hint" in bit
    assert "optional BOM for Excel" in bit
    assert "selectable" in bit


def test_bank_import_on_import_pdf_text_layer_then_statement_scan_fallback_order() -> None:
    """PDF import tries text extraction + parse, then ``extract_rows_from_statement_scan`` (Phase 7 OCR hook)."""
    bit = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    start = bit.index("    def _on_import_pdf(self):")
    end = bit.index("    def _on_import_csv(self):", start)
    chunk = bit[start:end]
    assert chunk.count("extract_text_from_pdf(path)") == 1
    assert chunk.count("parse_statement_text(text)") == 1
    assert chunk.count("ocr_result = extract_rows_from_statement_scan(") == 1
    assert chunk.count('mime_type="application/pdf"') == 1
    assert "StatementScanStatus" in chunk
    assert "text_layer_empty" in chunk
    assert "No selectable text was found" in chunk
    assert "Automatic OCR for scanned statements is not available" in chunk
    assert "StatementScanStatus.FAILED" in chunk
    assert "Statement scan could not finish" in chunk
    tx = chunk.index("text = extract_text_from_pdf(path)")
    pr = chunk.index("rows = parse_statement_text(text)")
    oc = chunk.index("ocr_result = extract_rows_from_statement_scan(")
    assert tx < pr < oc


def test_manage_accounts_dialog_accounts_table_opens_bank_import_shortcuts_help() -> None:
    bit = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    assert "Manage Bank Accounts (dialog):" in bit
    assert "def _on_accounts_table_context_menu" in bit
    assert "lambda: show_bank_import_keyboard_shortcuts_dialog(self)" in bit
    assert "self._table.setToolTip(" in bit
    assert "Confirm Delete" in bit
    assert "box.setToolTip(" in bit
    assert "Permanently removes this bank account" in bit
    ak = bit.index("def _on_accounts_table_context_menu")
    ak2 = bit.index("act_keys.setToolTip(", ak)
    assert "+ VIEW_BANK_REGISTER_KEYS_TOOLTIP" in bit[ak2 : ak2 + 400]
    assert "+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX" in bit[ak2 : ak2 + 400]


def test_grids_context_menus_use_qaction_hover_tooltips() -> None:
    """Bank, register, COA, journal, reports, audit, Business, and audit dialog context menus tip QActions."""
    bit = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    txn_s = bit.index("def _on_import_txn_context_menu")
    txn_e = bit.index("def _open_import_txn_attachment", txn_s)
    txn_chunk = bit[txn_s:txn_e]
    assert "act_keys.setToolTip" in txn_chunk
    assert txn_chunk.count("+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX") >= 2
    assert "act_att.setToolTip" in txn_chunk
    assert "act_history.setToolTip" in txn_chunk
    acc_s = bit.index("def _on_accounts_table_context_menu")
    acc_e = bit.index("def _refresh(self):", acc_s)
    assert "act_keys.setToolTip" in bit[acc_s:acc_e]

    reg = (_DESKTOP_APP_DIR / "register_tab.py").read_text(encoding="utf-8")
    rs = reg.index("def _on_register_context_menu")
    re = reg.index("def _open_register_attachment", rs)
    assert reg[rs:re].count("+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX") >= 2
    assert "act_clr.setToolTip" in reg[rs:re]
    assert "act_history.setToolTip" in reg[rs:re]
    lk = reg.index("def _link_payment_dialog")
    link_dlg = reg[lk:]
    assert "Copy suggestion line" in link_dlg
    assert "act_copy.setToolTip" in link_dlg
    assert link_dlg.count("+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX") >= 2

    jt = (_DESKTOP_APP_DIR / "journal_tab.py").read_text(encoding="utf-8")
    js = jt.index("def _on_journal_list_context_menu")
    je = jt.index("def _on_lines_context_menu", js)
    assert "act_keys.setToolTip" in jt[js:je]
    assert "+ VIEW_BANK_REGISTER_KEYS_TOOLTIP" in jt[js:je]
    assert "+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX" in jt[js:je]
    ls = jt.index("def _on_lines_context_menu")
    le = jt.index("def _refresh_list", ls)
    assert "act_copy.setToolTip" in jt[ls:le]
    assert "+ VIEW_BANK_REGISTER_KEYS_TOOLTIP" in jt[ls:le]
    assert "+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX" in jt[ls:le]

    rep = (_DESKTOP_APP_DIR / "reports_tab.py").read_text(encoding="utf-8")
    rps = rep.index("def _on_report_context_menu")
    rpe = rep.index("def _fill_table", rps)
    assert "act_keys.setToolTip" in rep[rps:rpe]
    assert "+ VIEW_BANK_REGISTER_KEYS_TOOLTIP" in rep[rps:rpe]
    assert "+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX" in rep[rps:rpe]

    at = (_DESKTOP_APP_DIR / "audit_tab.py").read_text(encoding="utf-8")
    aus = at.index("def _on_audit_context_menu")
    aue = at.index("def _export_csv", aus)
    assert "act_copy.setToolTip" in at[aus:aue]
    assert at[aus:aue].count("+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX") >= 2

    ad = (_DESKTOP_APP_DIR / "audit_dialog.py").read_text(encoding="utf-8")
    ad_cm = ad.index("def _audit_history_table_context_menu")
    ad_ce = ad.index("def show_entity_audit_history", ad_cm)
    ad_ctx = ad[ad_cm:ad_ce]
    assert "act_keys.setToolTip" in ad_ctx
    assert "+ VIEW_BANK_REGISTER_KEYS_TOOLTIP" in ad_ctx
    assert ad_ctx.count("+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX") >= 2

    coa = (_DESKTOP_APP_DIR / "coa_tab.py").read_text(encoding="utf-8")
    cs = coa.index("def _on_coa_context_menu")
    ce = coa.index("def _on_selection", cs)
    assert "act_history.setToolTip" in coa[cs:ce]
    assert "+ VIEW_BANK_REGISTER_KEYS_TOOLTIP" in coa[cs:ce]
    assert coa[cs:ce].count("+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX") >= 2

    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    assert et.count("+ VIEW_BANK_REGISTER_KEYS_TOOLTIP") >= 5
    acs = et.index("def _attach_table_copy_row_menu")
    ace = et.index("def _wire_find_focuses_line_edit", acs)
    assert "act_copy.setToolTip" in et[acs:ace]
    rs2 = et.index("def _on_rules_context_menu")
    assert "act_edit.setToolTip" in et[rs2 : rs2 + 900]
    inv_s = et.index("def _on_invoice_context_menu")
    inv_e = et.index("\n    def _save_pdf", inv_s)
    inv_chunk = et[inv_s:inv_e]
    assert "act_pdf.setToolTip" in inv_chunk
    assert "act_invno.setToolTip" in inv_chunk
    assert inv_chunk.count("+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX") >= 2


def test_bank_import_batch_table_column_header_tooltips() -> None:
    """Batch list headers explain import date, statement span, and reconciled flag."""
    bit = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    i = bit.index('self._batch_table.setHorizontalHeaderLabels(["Imported", "Statement Period", "Reconciled"])')
    window = bit[i : i + 700]
    assert window.count("horizontalHeaderItem(col)") >= 1
    assert "Date this batch was imported (YYYY-MM-DD)." in window
    assert "Whether Mark Reconciled has been applied for this batch." in window


def test_bank_import_context_menu_copy_row_tooltips_mention_backup_safety() -> None:
    bit = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    assert bit.count("+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX") >= 6


def test_extra_tabs_business_main_grids_have_hover_tooltips() -> None:
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    assert et.count("F5 refreshes when Business has focus.") == 5


def test_extra_tabs_business_copy_row_tooltips_mention_backup_safety() -> None:
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    assert et.count("+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX") >= 11


def test_register_tab_persists_header_state_via_qsettings() -> None:
    """Register saves/restores horizontal header state like other desktop grids."""
    text = (_DESKTOP_APP_DIR / "register_tab.py").read_text(encoding="utf-8")
    assert "saveState()" in text and "restoreState" in text
    assert "register/table_header_state_" in text


def test_register_and_bank_import_module_docstrings_document_tab_architecture() -> None:
    """Module docstrings record: Register = primary bank_transactions grid; Bank Import = import + recon."""
    reg = (_DESKTOP_APP_DIR / "register_tab.py").read_text(encoding="utf-8")
    reg_doc = reg.split('"""', 2)[1]
    assert "Architecture note" in reg_doc
    assert "primary" in reg_doc.lower()
    assert "bank account register" in reg_doc.lower()
    assert "Bank Import" in reg_doc
    assert "manual" in reg_doc.lower() or "add transaction" in reg_doc.lower()
    bi = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    bi_doc = bi.split('"""', 2)[1]
    assert "**Architecture:**" in bi_doc
    assert "Bank register" in bi_doc
    assert "reconciliation" in bi_doc.lower()


def test_register_tab_transfer_and_manual_link_coerce_combo_int_ids() -> None:
    rtab = (_DESKTOP_APP_DIR / "register_tab.py").read_text(encoding="utf-8")
    assert "coerce_combo_int_id(cb.currentData())" in rtab
    assert "coerce_combo_int_id(pay.currentData())" in rtab
    sel = rtab.split("def _selected_txn_ids(self)", 1)[1].split(
        "def _on_register_cell_double_clicked", 1
    )[0]
    assert (
        "coerce_combo_int_id(it.data(Qt.ItemDataRole.UserRole))" in sel
    ), "Selected register rows should resolve txn id via int-safe UserRole coercion"
    stmt = rtab.split("def apply_line_match_results_from_import", 1)[1].split(
        "def _select_bank_account_for_overlay", 1
    )[0]
    assert "coerce_combo_int_id(rid)" in stmt
    assert "want_acct = coerce_combo_int_id(bank_account_id)" in stmt
    demo = rtab.split("def _maybe_fill_demo_reconciliation_overlay", 1)[1].split(
        "def _refresh_all_recon_cells", 1
    )[0]
    assert "coerce_combo_int_id(res.get(\"register_id\"))" in demo


def test_register_tab_min_visible_rows_and_reconciliation_mode() -> None:
    """Register always pads visible rows; reconciliation mode adds banner + Stmt match column."""
    import re

    text = (_DESKTOP_APP_DIR / "register_tab.py").read_text(encoding="utf-8")
    m = re.search(r"_REGISTER_MIN_VISIBLE_ROWS = (\d+)", text)
    assert m is not None
    assert 15 <= int(m.group(1)) <= 25
    assert "Bank Import Run mock extract & compare can populate Stmt match" in text
    assert "Reconciliation Mode Active" in text
    assert "_COL_RECON_STATUS" in text
    assert "n_vis = max(n_data, _REGISTER_MIN_VISIBLE_ROWS)" in text
    assert "def _fill_pad_row(self, row: int)" in text
    assert "def _on_reconciliation_mode_toggled(self" in text
    assert "horizontalHeader().setSectionHidden" in text
    for needle in (
        "Reconciliation mode",
        "Stmt match",
        "_REGISTER_HEADERS_FULL",
        "_maybe_fill_demo_reconciliation_overlay",
        "apply_line_match_results_from_import",
        "_select_bank_account_for_overlay(self, bank_account_id: int) -> bool",
        "_coerce_register_account_id",
        "_register_account_ids_equal",
        "combo_index_for_int_user_data",
        "_recon_overlay_bank_import_mode",
        "tools_register_add_transaction",
    ):
        assert needle in text, needle


def test_register_tab_manual_entry_dialog_and_insert_wiring() -> None:
    """Register exposes Add transaction… and persists via BankDatabase.insert_manual_transaction."""
    text = (_DESKTOP_APP_DIR / "register_tab.py").read_text(encoding="utf-8")
    assert "Add transaction…" in text
    assert "class ManualTransactionDialog(QDialog):" in text
    assert "Category (COA)" in text
    assert "_COA_COMBO_TIP_BODY" in text
    assert "_manual_add_coa_combo_tooltip" in text
    assert "_sync_coa_combo_tooltip" in text
    assert "Category to save with this line:" in text
    assert "Copy category (COA)" in text
    assert "Copy payee / description" in text
    assert "Copy memo" in text
    assert "Copy number / ref" in text
    assert "Copy date" in text
    assert "Copy amount" in text
    assert "Copy transaction id" in text
    assert "_copy_register_txn_id" in text
    assert "_copy_register_row_txn_date" in text
    assert "_copy_register_row_amount" in text
    assert "_register_row_coa_user_data" in text
    assert "_register_clip_txn_string_field" in text
    assert "Statement vs register field copies for AI line reconciliation" in text
    assert "Bank Import AI line-reconciliation row copies" in text
    assert "_copy_register_row_coa" in text
    assert "_copy_register_row_payee_description" in text
    assert "_copy_register_row_memo" in text
    assert "_copy_register_row_ref_number" in text
    assert "coa_choices=self._coa_choices" in text
    assert "conn=self._db._conn" in text
    assert "initial_coa=saved_coa" in text
    assert "initial_txn_date=latest_date" in text
    assert "latest_txn_date_for_account" in text
    assert "Ctrl+Return" in text
    assert "QShortcut(QKeySequence" in text
    assert "ok_default=True" in text
    assert "QTimer.singleShot(0, self._amount.setFocus)" in text
    assert "register/manual_entry_last_coa_" in text
    assert "coa_account=v.get" in text or "coa_account=v[" in text
    assert "insert_manual_transaction" in text
    assert "_on_add_manual_transaction" in text
    assert "parse_amount" in text
    assert "QDateEdit" in text
    load = text.index("def _load_transactions(self, bank_account_id: int):")
    load_end = text.index("def _set_footer(self, debits: float", load)
    load_chunk = text[load:load_end]
    assert "n_vis = max(n_data, _REGISTER_MIN_VISIBLE_ROWS)" in load_chunk
    assert "payee_item.setToolTip(escape_ampersand_for_qt(payee_plain))" in load_chunk
    assert "ref_item.setToolTip(escape_ampersand_for_qt(num_plain))" in load_chunk
    assert "memo_stripped" in load_chunk and "memo_item.setToolTip" in load_chunk
    assert "d_item.setToolTip" in load_chunk and "d_date_raw" in load_chunk
    assert "Running balance:" in load_chunk and "bal_item.setToolTip" in load_chunk
    assert "Debit:" in load_chunk and "debit_item.setToolTip" in load_chunk
    assert "Credit:" in load_chunk and "credit_item.setToolTip" in load_chunk
    assert "link_lbl" in load_chunk and "Linked AR, AP, or payroll:" in load_chunk
    assert "_register_coa_combo_tooltip" in load_chunk
    assert "setSortingEnabled(True)" in load_chunk
    assert "Posted to GL — category is read-only" in text
    assert "Saved category:" in text
    assert "EditTrigger.SelectedClicked" in text
    assert "SelectionBehavior.SelectItems" in text


def test_register_tab_export_csv_writes_utf8_sig_for_excel() -> None:
    """Register Export CSV uses UTF-8 with BOM so Excel opens amounts/dates reliably."""
    text = (_DESKTOP_APP_DIR / "register_tab.py").read_text(encoding="utf-8")
    chunk = text.split("def _export_csv(self):", 1)[1].split("def _on_coa_changed", 1)[0]
    assert 'encoding="utf-8-sig"' in chunk


def test_register_journal_reports_audit_grid_hints_mention_csv_utf8_bom_for_excel() -> None:
    """Main grids / footer hints echo toolbar Export CSV encoding (Excel-friendly BOM)."""
    reg = (_DESKTOP_APP_DIR / "register_tab.py").read_text(encoding="utf-8")
    assert "Ctrl+Shift+E export (UTF-8 BOM for Excel)" in reg
    assert "Ctrl+Shift+E exports CSV (UTF-8 BOM for Excel)" in reg
    rep = (_DESKTOP_APP_DIR / "reports_tab.py").read_text(encoding="utf-8")
    assert rep.count("Toolbar Export CSV uses UTF-8 BOM for Excel") == 1
    assert "Export CSV uses UTF-8 BOM for Excel" in rep
    jt = (_DESKTOP_APP_DIR / "journal_tab.py").read_text(encoding="utf-8")
    assert jt.count("Toolbar Export CSV uses UTF-8 BOM for Excel") == 2
    assert "Export CSV uses UTF-8 BOM for Excel" in jt
    at = (_DESKTOP_APP_DIR / "audit_tab.py").read_text(encoding="utf-8")
    assert "Toolbar Export CSV uses UTF-8 BOM for Excel" in at


def test_probooksai_tab_csv_writers_use_utf8_sig_for_excel() -> None:
    """Journal, Reports, Audit, Rules, and AR/AP list exports share Excel-friendly CSV encoding."""
    gl = (REPO_ROOT / "probooksai" / "gl.py").read_text(encoding="utf-8")
    assert re.search(
        r"def write_journal_export_csv\(.*?encoding=\"utf-8-sig\"",
        gl,
        re.DOTALL,
    )

    fr = (REPO_ROOT / "probooksai" / "financial_reports.py").read_text(encoding="utf-8")
    assert re.search(
        r"def write_report_csv\(.*?encoding=\"utf-8-sig\"",
        fr,
        re.DOTALL,
    )

    al = (REPO_ROOT / "probooksai" / "audit_log.py").read_text(encoding="utf-8")
    assert re.search(
        r"def write_audit_csv\(.*?encoding=\"utf-8-sig\"",
        al,
        re.DOTALL,
    )

    re_csv = (REPO_ROOT / "probooksai" / "rules_engine.py").read_text(encoding="utf-8")
    wru = re_csv.split("def write_rules_csv", 1)[1].split("def read_rules_csv", 1)[0]
    assert 'encoding="utf-8-sig"' in wru

    bu = (REPO_ROOT / "probooksai" / "business.py").read_text(encoding="utf-8")
    assert bu.count('with open(path, "w", newline="", encoding="utf-8-sig") as f:') == 8


def test_register_tab_cleared_actions_document_shortcuts_in_tooltips() -> None:
    """Register shortcuts (F5, Ctrl+Shift+*) match tooltips and QShortcut wiring."""
    text = (_DESKTOP_APP_DIR / "register_tab.py").read_text(encoding="utf-8")
    assert "setToolTip" in text
    assert "Ctrl+Shift+C" in text and "Ctrl+Shift+U" in text
    assert "Ctrl+Shift+E" in text and "Ctrl+Shift+G" in text
    assert 'QKeySequence("F5")' in text
    assert "activated.connect(self._export_csv)" in text
    assert "activated.connect(self._reload_current)" in text
    assert "activated.connect(self._post_selected)" in text


def test_register_tab_recon_menu_entrypoints_and_link_dialog_tooltips() -> None:
    """Register control row has no action buttons; Recon menu calls ``tools_register_*`` handlers."""
    reg = (_DESKTOP_APP_DIR / "register_tab.py").read_text(encoding="utf-8")
    assert "btn_refresh = QPushButton" not in reg
    assert "def tools_register_add_transaction" in reg
    assert "def tools_register_export_csv" in reg
    assert "def tools_register_link_payment_dialog" in reg
    for needle in (
        "reg_link_suggestion.setToolTip",
        "reg_link_btn_clear.setToolTip",
        "_acct_combo.setToolTip",
        "_filter_combo.setToolTip",
        "self._table.setToolTip(",
        "combo.setToolTip",
        "categorization rules",
        "kind.setToolTip",
        "pay.setToolTip",
        "lbl_bank_acct.setToolTip",
        "lbl_register_filter.setToolTip",
        "lbl_link_suggestions.setToolTip",
        "lbl_link_manual.setToolTip",
        "lbl_current_link.setToolTip",
        "_lbl_debits.setToolTip",
        "self._register_help_tip.setToolTip",
    ):
        assert needle in reg, f"register_tab should set tooltip on {needle!r}"
    assert reg.count("tip_qdialog_button_box(\n            bb,") >= 3
    assert "Set or clear a transfer link" in reg
    assert "Split one unposted bank transaction" in reg
    assert "Link this bank row to AR" in reg
    assert reg.count("+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX") >= 4


def test_main_recon_menu_register_action_submenus_and_slots() -> None:
    """Recon → Register Actions / Reconciliation / … wires to ``RegisterTab.tools_register_*``."""
    text = _MAIN.read_text(encoding="utf-8")
    assert 'm_reg_actions = recon_menu.addMenu("Register &Actions")' in text
    assert 'm_reg_recon = recon_menu.addMenu("&Reconciliation")' in text
    assert 'm_reg_attach = recon_menu.addMenu("&Attachments")' in text
    assert 'm_reg_txn = recon_menu.addMenu("&Transaction Tools")' in text
    assert 'm_reg_flags = recon_menu.addMenu("&Flags")' in text
    assert text.count("self._register_tab.tools_register_add_transaction()") == 1
    assert text.count("self._register_tab.tools_register_post_selected()") == 1
    assert text.count("self._register_tab.tools_register_export_csv()") == 1
    assert text.count("self._register_tab.tools_register_mark_cleared()") == 1
    assert text.count("self._register_tab.tools_register_clear_cleared()") == 1
    assert text.count("self._register_tab.tools_register_attach_file()") == 1
    assert text.count("self._register_tab.tools_register_clear_attachment()") == 1
    assert text.count("self._register_tab.tools_register_splits_dialog()") == 1
    assert text.count("self._register_tab.tools_register_transfer_dialog()") == 1
    assert text.count("self._register_tab.tools_register_link_payment_dialog()") == 1
    assert text.count("self._register_tab.tools_register_flag_needs_receipt()") == 1
    assert text.count("self._register_tab.tools_register_clear_needs_receipt()") == 1


def test_register_keyboard_shortcuts_help_text_matches_wired_chords() -> None:
    """Single helper lists the same chords as QShortcut (avoid help drifting from behavior)."""
    text = (_DESKTOP_APP_DIR / "register_tab.py").read_text(encoding="utf-8")
    start = text.index("def _register_keyboard_shortcuts_help_text")
    end = text.index("\n\nclass RegisterTab", start)
    chunk = text[start:end]
    for needle in (
        "Recon menu",
        "Add transaction…",
        "manual-entry batch",
        "Reconciliation mode",
        "Practice rows",
        "two-band rows",
        "arrow keys",
        "Link payment…",
        "F5 — Refresh",
        "Ctrl+Shift+G",
        "Ctrl+Shift+E",
        "BOM",
        "Ctrl+Shift+C",
        "Ctrl+Shift+U",
        "Document intake shortcuts",
        "More tab shortcuts (F5)",
        "Business shortcuts",
        "Bank import shortcuts",
        "statement/register copies",
        "Ctrl+2 Bank Import",
        "Ctrl+3 Register",
        "status bar",
        "company line",
    ):
        assert needle in chunk, f"register shortcuts help should mention {needle!r}"


def test_register_context_menu_includes_keyboard_shortcuts_action() -> None:
    text = (_DESKTOP_APP_DIR / "register_tab.py").read_text(encoding="utf-8")
    assert "Keyboard shortcuts…" in text
    assert "_show_register_keyboard_shortcuts_help" in text
    grid_ctx = text.split("def _on_register_context_menu", 1)[1].split("\n    def ", 1)[0]
    assert "AI line-reconciliation field copies" in grid_ctx
    assert "+ VIEW_BANK_REGISTER_KEYS_TOOLTIP" in grid_ctx
    assert text.count("+ VIEW_BANK_REGISTER_KEYS_TOOLTIP") == 2


def test_register_tab_clr_header_tooltip_documents_batch_reconciled() -> None:
    """Clr column header explains C vs R and points users at Bank Import for batch R."""
    text = (_DESKTOP_APP_DIR / "register_tab.py").read_text(encoding="utf-8")
    assert "horizontalHeaderItem(_COL_CLR)" in text
    assert "Bank Import" in text


def test_register_table_stylesheet_defines_cell_grid() -> None:
    """Register grid lines: ``::item`` has no border (avoids double lines); delegate draws rules."""
    from desktop_app.theme import register_table_style_sheet

    qss = register_table_style_sheet()
    assert "bankRegisterTable" in qss
    assert "QTableWidget#bankRegisterTable::item" in qss
    assert "border: none" in qss
    assert "gridline-color:" in qss
    rbd = (_DESKTOP_APP_DIR / "register_band_delegate.py").read_text(encoding="utf-8")
    assert "REGISTER_GRID_LINE" in rbd


def test_theme_register_row_height_constants_track_delegate_mins() -> None:
    """Row height mins are shared by theme, RegisterBandDelegate, and register/preview tables."""
    theme = (_DESKTOP_APP_DIR / "theme.py").read_text(encoding="utf-8")
    assert "REGISTER_ROW_HEIGHT_MIN_FULL = 46" in theme
    assert "REGISTER_ROW_HEIGHT_MIN_PREVIEW = 38" in theme
    reg = (_DESKTOP_APP_DIR / "register_tab.py").read_text(encoding="utf-8")
    assert "setDefaultSectionSize(REGISTER_ROW_HEIGHT_MIN_FULL)" in reg


def test_theme_normalizes_default_font_before_stylesheet() -> None:
    """Avoid QFont::setPointSize -1 when QSS merges fonts (theme uses pixel size = FONT_SIZE_NORMAL)."""
    theme = (_DESKTOP_APP_DIR / "theme.py").read_text(encoding="utf-8")
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
