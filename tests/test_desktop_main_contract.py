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

_EDIT_TOOLS_HELP_QACTION_NAMES: tuple[str, ...] = (
    "act_undo",
    "act_redo",
    "act_prefs",
    "act_tools",
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
    assert chunk.count("_menu_action_tip(act, ") == 1
    assert "act.setToolTip(" not in chunk
    assert "act.setStatusTip(" not in chunk


def test_edit_tools_help_qactions_use_menu_action_tip_only() -> None:
    """**Edit**, **Tools**, and **Help** menu actions set hover + status via ``_menu_action_tip`` only."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("# Edit menu")
    end = text.index("    # -- drag & drop on window", start)
    chunk = text[start:end]
    for name in _EDIT_TOOLS_HELP_QACTION_NAMES:
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
    assert chunk.count('QLabel("ProBooks+ai")') == 1
    assert "INBOX_HEADER_COLOR" in chunk
    assert chunk.count("setFixedHeight(44)") == 1
    assert chunk.count("QHBoxLayout(self)") == 1
    assert chunk.count("layout.setContentsMargins(14, 0, 14, 0)") == 1
    assert chunk.count("layout.addStretch()") == 1
    assert chunk.count("border-bottom: 2px solid #4a6fa8") == 1
    assert chunk.count(".setToolTip(") == 3
    assert chunk.count("escape_ampersand_for_qt(company_name)") == 1
    assert chunk.count("def set_company_name(self, name: str):") == 1
    assert chunk.count("self._lbl_company.setText(escape_ampersand_for_qt(name))") == 1
    assert "company_name: str = COMPANY_NAME" in chunk


def test_main_window_tab_bar_has_tab_tooltips() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    assert "main_tab_bar = self._tabs.tabBar()" in text
    assert "main_tab_bar.setTabToolTip" in text
    z = text.index("main_tab_bar.setTabToolTip(\n            0,")
    assert "File → Backup" in text[z : z + 320]
    assert text.count("_main_tab_bar_db_hint") == 8
    assert "Bank CSV/PDF import" in text
    assert "Business hub:" in text
    assert "self._tabs.setToolTip(" in text
    assert "Main workspace:" in text
    assert "intake_widget.setToolTip(" in text
    assert "left.setToolTip(" in text
    assert "Document inbox column:" in text
    assert "container.setToolTip(" in text
    assert "company banner and tabbed areas" in text


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
    assert "left.setToolTip(" in bchunk
    assert "Import batches column" in bchunk

    rep = (_DESKTOP_APP_DIR / "reports_tab.py").read_text(encoding="utf-8")
    assert "Financial reports: trial balance" in rep

    jt = (_DESKTOP_APP_DIR / "journal_tab.py").read_text(encoding="utf-8")
    assert "General journal: browse entries" in jt

    at = (_DESKTOP_APP_DIR / "audit_tab.py").read_text(encoding="utf-8")
    assert "Audit trail: field-level changes" in at

    coa = (_DESKTOP_APP_DIR / "coa_tab.py").read_text(encoding="utf-8")
    assert "Chart of accounts: add, edit" in coa

    reg = (_DESKTOP_APP_DIR / "register_tab.py").read_text(encoding="utf-8")
    assert "Bank register for one account:" in reg

    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    assert "class BusinessHub" in et
    hub = et.split("class BusinessHub", 1)[1].split("def _refresh_current_subtab", 1)[0]
    assert "self.setToolTip(" in hub
    assert "Business hub: Rules, AR invoices" in hub
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


def test_main_window_toolbar_and_menu_bar_qaction_counts() -> None:
    """Toolbar: Main bar, non-movable, separator, two ``QAction``s wired; menu bar: 21 ``QAction``s."""
    text = _MAIN.read_text(encoding="utf-8")
    tb_s = text.index("# Toolbar")
    tb_e = text.index("# Container: header banner + tab widget", tb_s)
    tb_chunk = text[tb_s:tb_e]
    assert tb_chunk.count('toolbar = QToolBar("Main")') == 1
    assert tb_chunk.count("toolbar.setMovable(False)") == 1
    assert tb_chunk.count("toolbar.setToolTip(") == 1
    assert tb_chunk.count("toolbar.addSeparator()") == 1
    assert tb_chunk.count("self.addToolBar(toolbar)") == 1
    assert tb_chunk.count("QAction(") == 2
    assert tb_chunk.count(".triggered.connect(") == 2
    assert tb_chunk.count("toolbar.addAction(") == 2
    mb_s = text.index("def _build_menu_bar")
    mb_e = text.index("def dragEnterEvent", mb_s)
    assert text[mb_s:mb_e].count("QAction(") == 21


def test_main_window_build_ui_instantiates_one_toolbar() -> None:
    """``_build_ui`` creates one ``QToolBar`` and calls ``addToolBar`` once (before ``_build_menu_bar``)."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("def _build_ui(self):")
    end = text.index("def _build_menu_bar", start)
    chunk = text[start:end]
    assert chunk.count("QToolBar(") == 1
    assert chunk.count("self.addToolBar(") == 1


def test_main_window_build_ui_sets_central_status_and_eight_main_tabs() -> None:
    """``_build_ui`` attaches one central widget, one status bar, and eight ``_tabs.addTab`` calls."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("def _build_ui(self):")
    end = text.index("def _build_menu_bar", start)
    chunk = text[start:end]
    assert chunk.count("self.setCentralWidget(") == 1
    assert chunk.count("self.setStatusBar(") == 1
    assert chunk.count("self._tabs.addTab(") == 8


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


def test_main_window_build_ui_document_intake_split_inbox_header_and_f5() -> None:
    """Document Intake tab builds inbox header (brand colour), horizontal splitter, sizes, F5, first tab."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("        # ── Tab 1: Document Intake")
    end = text.index("        # ── Tab 2:", start)
    chunk = text[start:end]
    assert chunk.count("INBOX_HEADER_COLOR") == 1
    assert chunk.count('lbl_inbox = QLabel("  Document Inbox")') == 1
    assert chunk.count("QSplitter(Qt.Orientation.Horizontal)") == 1
    assert chunk.count("splitter.setSizes([380, 720])") == 1
    assert chunk.count('QShortcut(QKeySequence("F5"), intake_widget)') == 1
    assert chunk.count("self._tabs.addTab(intake_widget,") == 1
    assert "Document Intake" in chunk


def test_main_window_build_ui_status_bar_ready_message_and_qstatusbar() -> None:
    """``_build_ui`` creates a ``QStatusBar`` with a ready line that mentions File → Backup."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("        # Status bar")
    end = text.index("        # Drag & drop on the main window itself", start)
    chunk = text[start:end]
    assert chunk.count("self._status_bar = QStatusBar()") == 1
    assert chunk.count("self.setStatusBar(self._status_bar)") == 1
    assert chunk.count("self._status_bar.showMessage(") == 1
    assert "File → Backup saves the company .db." in chunk


def test_main_window_init_wires_databases_build_ui_and_refresh() -> None:
    """``MainWindow.__init__`` opens DB layers, seeds COA, builds UI, refreshes inbox, updates banner."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def __init__(self, db_path: str | None = None):")
    end = text.index("    # -- UI construction", start)
    chunk = text[start:end]
    assert chunk.count("self.resize(1100, 700)") == 1
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


def test_main_window_switch_company_database_closes_and_loads_at_path() -> None:
    """``_switch_company_database`` closes document/bank DBs then loads the resolved path once."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _switch_company_database(self, path: str, *, create_new: bool = False) -> None:")
    end = text.index("    def _on_backup_company(self):", start)
    chunk = text[start:end]
    assert chunk.count("self._db.close()") == 1
    assert chunk.count("self._bank_db.close()") == 1
    assert chunk.count("self._load_company_at_path(resolved)") == 1


def test_main_window_switch_company_create_new_mkdir_and_open_missing_paths() -> None:
    """``_switch_company_database`` creates parent dirs for new DBs, prompts if file exists, warns when missing."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _switch_company_database(self, path: str, *, create_new: bool = False) -> None:")
    end = text.index("    def _on_backup_company(self):", start)
    chunk = text[start:end]
    assert chunk.count("p.parent.mkdir(parents=True, exist_ok=True)") == 1
    assert chunk.count("QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No") == 1
    assert chunk.count('"File exists"') == 1
    assert chunk.count("elif not p.exists():") == 1
    assert chunk.count('"Not found"') == 1


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


def test_main_window_on_backup_company_calls_backup_database_and_dialog_flow() -> None:
    """``_on_backup_company`` saves via ``backup_database`` and surfaces busy/failure/success boxes."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_backup_company(self):")
    end = text.index("    def _on_restore_company(self):", start)
    chunk = text[start:end]
    assert chunk.count("QFileDialog.getSaveFileName(") == 1
    assert chunk.count("backup_database(src, Path(path))") == 1
    assert chunk.count('"Backup failed"') == 2
    assert chunk.count('"Backup complete"') == 1
    assert (
        "Wait for AI extraction to finish before backing up." in chunk
    )


def test_main_window_on_restore_company_restores_and_reload_paths() -> None:
    """``_on_restore_company`` closes DBs, calls ``restore_database``, reloads on success and on errors."""
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
    assert (
        "Wait for AI extraction to finish before restoring." in chunk
    )


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


def test_main_window_on_open_company_database_reads_settings_and_switches() -> None:
    """``_on_open_company_database`` uses QSettings start dir and delegates to switch (not create)."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_open_company_database(self):")
    end = text.index("    def _on_new_company_database(self):", start)
    chunk = text[start:end]
    assert chunk.count('QSettings().value("company_database_path", "", type=str)') == 1
    assert chunk.count("QFileDialog.getOpenFileName(") == 1
    assert (
        "Open company database (File → Backup copies the current .db first)" in chunk
    )
    assert chunk.count("self._switch_company_database(path, create_new=False)") == 1


def test_main_window_on_new_company_database_suffixes_db_and_switches() -> None:
    """``_on_new_company_database`` saves a .db path and opens via switch with ``create_new=True``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_new_company_database(self):")
    end = text.index("    def closeEvent(self, event):", start)
    chunk = text[start:end]
    assert chunk.count('QSettings().value("company_database_path", "", type=str)') == 1
    assert chunk.count("QFileDialog.getSaveFileName(") == 1
    assert (
        "New company database (back up any existing .db from File → Backup first)" in chunk
    )
    assert chunk.count('if not path.lower().endswith(".db"):') == 1
    assert chunk.count('path += ".db"') == 1
    assert chunk.count("self._switch_company_database(path, create_new=True)") == 1


def test_main_window_on_run_ai_guards_worker_api_key_and_starts_ai_worker() -> None:
    """``_on_run_ai`` blocks on running worker / missing key, then runs ``AIWorker`` with signal hooks."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_run_ai(self, doc_id: int):")
    end = text.index("    def _on_ai_done(self, doc_id: int, result, suggestions):", start)
    chunk = text[start:end]
    assert chunk.count("if self._worker and self._worker.isRunning():") == 1
    assert '"AI Running"' in chunk
    assert chunk.count("self._db.get_document(doc_id)") == 1
    assert chunk.count('os.environ.get("OPENAI_API_KEY")') == 1
    assert '"API Key Missing"' in chunk
    assert chunk.count('self._db.set_status(doc_id, "Extracted")') == 1
    assert (
        chunk.count(
            "AIWorker(doc_id, row[\"stored_path\"], row[\"mimetype\"], self._coa)"
        )
        == 1
    )
    assert (
        chunk.count(
            ".finished.connect(lambda res, sug: self._on_ai_done(doc_id, res, sug))"
        )
        == 1
    )
    assert (
        chunk.count(
            ".error.connect(lambda err: self._on_ai_error(doc_id, err))"
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
    assert chunk.count("self._db.save_extraction(doc_id, result)") == 1
    assert chunk.count('self._db.set_status(doc_id, "Needs Review")') == 1
    assert chunk.count("self._detail.populate_ai_result(result, suggestions)") == 1
    assert chunk.count("self._refresh_inbox()") == 2
    assert chunk.count('self._db.set_status(doc_id, "Error")') == 1
    assert chunk.count('"AI Extraction Failed"') == 1


def test_main_window_on_approve_mark_posted_reject_detail_flow() -> None:
    """Approve / posted / reject slots persist status, refresh inbox, and reload the detail pane."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_approve(self, doc_id: int):")
    end = text.index("    # -- helpers", start)
    chunk = text[start:end]
    assert chunk.count("self._detail.collect_approved_values()") == 1
    assert chunk.count("self._db.save_approved(doc_id, values)") == 1
    assert chunk.count('self._db.set_status(doc_id, "Approved")') == 1
    assert chunk.count('self._db.set_status(doc_id, "Posted")') == 1
    assert chunk.count('self._db.set_status(doc_id, "Needs Review")') == 1
    assert chunk.count('"Not Yet Approved"') == 1
    assert chunk.count("self._detail.load_document(doc_id, self._db)") == 3


def test_main_window_on_mark_posted_warns_until_approved() -> None:
    """``_on_mark_posted`` blocks until status is Approved, then sets Posted and refreshes UI."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_mark_posted(self, doc_id: int):")
    end = text.index("    def _on_reject(self, doc_id: int):", start)
    chunk = text[start:end]
    assert chunk.count("self._db.get_document(doc_id)") == 1
    assert chunk.count('row["status"] != "Approved"') == 1
    assert chunk.count('"Not Yet Approved"') == 1
    assert chunk.count('self._db.set_status(doc_id, "Posted")') == 1
    assert chunk.count("self._detail.load_document(doc_id, self._db)") == 1


def test_main_window_on_import_and_files_dropped_delegate_to_import_files() -> None:
    """Menu/toolbar import and inbox drops both funnel into ``_import_files``."""
    text = _MAIN.read_text(encoding="utf-8")
    imp_s = text.index("    def _on_import(self):")
    imp_e = text.index("    def _on_files_dropped(self, paths: list[str]):", imp_s)
    imp_chunk = text[imp_s:imp_e]
    assert imp_chunk.count("QFileDialog.getOpenFileNames(") == 1
    assert imp_chunk.count("Import Documents") == 1
    assert imp_chunk.count("self._import_files(paths)") == 1

    drop_s = imp_e
    drop_e = text.index("    def _import_files(self, paths: list[str]):", drop_s)
    drop_chunk = text[drop_s:drop_e]
    assert drop_chunk.count("self._import_files(paths)") == 1


def test_main_window_on_selection_changed_loads_detail_when_row_selected() -> None:
    """Inbox selection changes load the active document into the detail pane."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_selection_changed(self):")
    end = text.index("    def _on_run_ai(self, doc_id: int):", start)
    chunk = text[start:end]
    assert chunk.count("self._inbox.selected_doc_id()") == 1
    assert chunk.count("if doc_id is not None:") == 1
    assert chunk.count("self._detail.load_document(doc_id, self._db)") == 1


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
    assert chunk.count("if imported:") == 1
    assert chunk.count("Imported {imported} document(s).") == 1


def test_main_window_import_files_mime_guess_fallback_and_import_error_status() -> None:
    """``_import_files`` uses ``mimetypes.guess_type`` with PDF/image fallback; failures surface on the status bar."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _import_files(self, paths: list[str]):")
    end = text.index("    def _on_selection_changed(self):", start)
    chunk = text[start:end]
    assert chunk.count("mimetypes.guess_type(path)") == 1
    assert 'mime or ("application/pdf" if ext == ".pdf" else "image/jpeg")' in chunk
    assert "Error importing" in chunk


def test_main_window_refresh_inbox_and_coa_changed_sync_lists() -> None:
    """``_refresh_inbox`` repopulates the inbox; ``_on_coa_changed`` refreshes COA-derived UI."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _refresh_inbox(self):")
    end = text.index("    def _set_main_tab_index(self, index: int) -> None:", start)
    chunk = text[start:end]
    assert chunk.count("self._db.list_documents()") == 1
    assert chunk.count("self._inbox.populate(docs)") == 1
    assert chunk.count("load_coa()") == 1
    assert chunk.count("self._coa_db.display_list()") == 1
    assert chunk.count("self._detail.update_coa(coa_display)") == 1
    assert chunk.count("self._register_tab.refresh_coa_choices()") == 1


def test_main_window_build_menu_bar_wires_all_action_triggers() -> None:
    """Every menu ``QAction`` that should fire a slot has a ``triggered.connect`` (15 wired, 6 disabled stubs)."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _build_menu_bar(self):")
    end = text.index("    # -- drag & drop on window", start)
    chunk = text[start:end]
    assert chunk.count("QAction(") == 21
    assert chunk.count(".triggered.connect(") == 15
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
    assert "docs/ROADMAP.md" in chunk
    assert chunk.count("QUrl.fromLocalFile(str(path))") == 1
    assert chunk.count("QDesktopServices.openUrl(url)") == 1
    assert chunk.count('"Product roadmap"') == 2


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
    assert chunk.count("application_version()") == 1
    assert chunk.count("self.setWindowTitle(") == 2
    assert chunk.count("ProBooks+ai –") == 2
    assert chunk.count("self._sync_window_title()") == 1
    assert chunk.count("self._status_bar.showMessage(") == 1
    assert "File → Backup copies this .db." in chunk
    assert chunk.count("self._header.set_company_name(") == 2


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
    assert chunk.count("self._import_files(paths)") == 1


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


def test_main_window_build_ui_wires_tabs_container_inbox_and_detail_signals() -> None:
    """``_build_ui`` attaches ``QTabWidget`` to the container and wires Intake/COA/Detail slots."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("def _build_ui(self):")
    end = text.index("def _build_menu_bar", start)
    chunk = text[start:end]
    assert chunk.count("self._tabs = QTabWidget()") == 1
    assert chunk.count("container_layout.addWidget(self._header)") == 1
    assert chunk.count("container_layout.addWidget(self._tabs)") == 1
    assert chunk.count("self._coa_tab.coaChanged.connect(self._on_coa_changed)") == 1
    assert chunk.count("self._inbox.filesDropped.connect(self._on_files_dropped)") == 1
    assert chunk.count(
        "self._inbox.itemSelectionChanged.connect(self._on_selection_changed)"
    ) == 1
    assert chunk.count("self._detail.runAI.connect(self._on_run_ai)") == 1
    assert chunk.count("self._detail.approve.connect(self._on_approve)") == 1
    assert chunk.count("self._detail.markPosted.connect(self._on_mark_posted)") == 1
    assert chunk.count("self._detail.reject.connect(self._on_reject)") == 1


def test_main_toolbar_import_and_refresh_tooltips_echo_file_menu_and_backup() -> None:
    """Main toolbar **Import** / **Refresh** mirror File backup hints; no ad-hoc ``setStatusTip``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("# Toolbar")
    end = text.index("# Container: header banner + tab widget", start)
    chunk = text[start:end]
    assert chunk.count("act_import = QAction(") == 1
    assert chunk.count("act_refresh = QAction(") == 1
    assert chunk.count("act_import.setToolTip(") == 1
    assert chunk.count("act_refresh.setToolTip(") == 1
    assert "act_import.setStatusTip(" not in chunk
    assert "act_refresh.setStatusTip(" not in chunk
    ii = chunk.index("act_import.setToolTip(")
    ir = chunk.index("act_refresh.setToolTip(")
    imp = chunk[ii : ii + 520]
    ref = chunk[ir : ir + 520]
    assert "Ctrl+O" in imp
    assert "Import documents" in imp
    assert "File → Backup" in imp or "probooks backup" in imp.lower()
    assert "F5" in ref
    assert "File → Backup" in ref or "probooks backup" in ref.lower()


def test_main_toolbar_import_refresh_trigger_same_handlers_as_shortcuts_help() -> None:
    """Toolbar **Import** / **Refresh** call the same slots as File → Import and F5 refresh."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("# Toolbar")
    end = text.index("# Container: header banner + tab widget", start)
    chunk = text[start:end]
    assert chunk.count("act_import.triggered.connect(self._on_import)") == 1
    assert chunk.count("act_refresh.triggered.connect(self._refresh_inbox)") == 1


def test_menu_action_tip_helper_sets_matching_status_and_hover_text() -> None:
    """``_menu_action_tip`` must keep status bar and QAction hover text in lockstep."""
    text = _MAIN.read_text(encoding="utf-8")
    assert (
        "    act.setStatusTip(tip)\n    act.setToolTip(tip)" in text
    ), "_menu_action_tip should call setStatusTip then setToolTip with the same tip"


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
        f"expected per-menu addAction (File,View,Edit,Tools,Help)=(9,1,3,1,7); "
        f"got {per_menu_add}"
    )
    n_add = sum(per_menu_add)
    assert n_qa == n_tip == n_add == 21, (
        f"expected 21 menu QActions, _menu_action_tip calls, and *.addAction( calls "
        f"(QAction={n_qa}, _menu_action_tip={n_tip}, addAction={n_add})"
    )
    n_dis = chunk.count("setEnabled(False)")
    assert n_dis == 6, (
        f"expected 6 disabled menu actions (Save, Save As, Undo, Redo, Prefs, Tools); "
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
    assert chunk.count("mb.addMenu(") == 5, (
        "expected five top-level menus (File, View, Edit, Tools, Help)"
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
    assert "_menu_action_tip(act, f" in chunk
    ex = chunk.index("act_exit = QAction")
    assert "_menu_action_tip(" in chunk[ex : ex + 400]
    assert "\n            act_intake_keys,\n" in chunk
    assert "\n            act_more_tab_keys,\n" in chunk
    assert chunk.count("_view_tab_tip_suffix") == 2
    assert 'f"Show this main tab ({sc}).{_view_tab_tip_suffix}"' in chunk


def test_main_help_menu_wires_document_intake_shortcuts_dialog() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    assert "show_document_intake_keyboard_shortcuts_dialog" in text
    assert "def _document_intake_keyboard_shortcuts_help_text" in text
    assert "Document &intake shortcuts" in text
    assert "Ctrl+7 Business" in text and "Ctrl+8 Audit log" in text
    assert "all tabs share the open" in text
    assert "Help → Business shortcuts" in text
    assert "toolbar Import Documents is the same command" in text
    assert "status bar" in text
    assert "each menu item" in text
    assert "File, View, Edit, Help, or Tools" in text
    assert "Detail pane:" in text


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
    assert chunk.count("+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX") >= 2


def test_inbox_widget_context_menu_skips_copy_row_when_no_cell() -> None:
    """Empty-area context menu runs shortcuts-only; **Copy row** appears only after a valid row index."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_context_menu(self, pos):")
    end = text.index("    # -- drag & drop", start)
    chunk = text[start:end]
    assert chunk.count("if not idx.isValid():") == 1
    assert chunk.count("m.addSeparator()") == 1
    assert chunk.count('m.addAction("Copy row"') == 1


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
    assert "Company .db: File → Backup / Restore (probooks.backup)." in chunk


def test_desktop_main_document_intake_shortcuts_help_text_sections() -> None:
    """Intake shortcuts help lists File/View/Bank sections and backup cross-links."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("def _document_intake_keyboard_shortcuts_help_text() -> str:")
    end = text.index(
        "def show_document_intake_keyboard_shortcuts_dialog(parent: QWidget) -> None:", start
    )
    chunk = text[start:end]
    assert chunk.count("return (") == 1
    assert "File menu:" in chunk
    assert "View menu:" in chunk
    assert "Bank workflows:" in chunk
    assert "Help → More tab shortcuts" in chunk
    assert "Help → Business shortcuts" in chunk
    assert chunk.count("probooks.backup") >= 2
    assert "Keyboard shortcuts…" in chunk


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
    start = text.index("class AIWorker(QThread):")
    end = text.index("class InboxWidget(QTableWidget):", start)
    chunk = text[start:end]
    assert "finished = Signal(object, object)" in chunk
    assert "error    = Signal(str)" in chunk
    assert chunk.count("from ai.extractor import extract_document") == 1
    assert chunk.count("from ai.categorizer import suggest_categories") == 1
    assert chunk.count("extract_document(self._path, self._mimetype)") == 1
    assert chunk.count("suggest_categories(result, self._coa)") == 1
    assert chunk.count("self.finished.emit(result, suggestions)") == 1
    assert chunk.count("self.error.emit") == 2


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


def test_desktop_main_ai_worker_run_error_paths_extractor_and_exception() -> None:
    """``AIWorker.run`` emits ``error`` when extraction fails or an unexpected exception escapes."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def run(self):", text.index("class AIWorker(QThread):"))
    end = text.index("class InboxWidget(QTableWidget):", start)
    chunk = text[start:end]
    assert chunk.count("if result.error:") == 1
    assert chunk.count("self.error.emit(result.error)") == 1
    assert chunk.count("except Exception as exc:") == 1
    assert chunk.count("self.error.emit(str(exc))") == 1


def test_desktop_main_inbox_widget_drop_emits_paths_and_populate_sets_doc_ids() -> None:
    """``InboxWidget`` emits local paths on drop and stores document ids on items for selection."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class InboxWidget(QTableWidget):")
    end = text.index("class DetailPane(QScrollArea):", start)
    chunk = text[start:end]
    assert chunk.count("filesDropped = Signal(list)") == 1
    assert chunk.count("self.filesDropped.emit(paths)") == 1
    assert chunk.count("hasUrls()") >= 2
    assert chunk.count("IntSortTableItem(str(did), did)") == 1
    assert chunk.count("Qt.ItemDataRole.UserRole") >= 2
    assert chunk.count("def selected_doc_id(self) -> int | None:") == 1


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
    assert chunk.count("setSortingEnabled(") == 3


def test_inbox_widget_header_column_widths_and_stretch_policy() -> None:
    """Inbox grid: column widths, no last-section stretch, alternating rows, hidden row header."""
    text = _MAIN.read_text(encoding="utf-8")
    iw = text.index("class InboxWidget(QTableWidget):")
    start = text.index("    def __init__(self, parent=None):", iw)
    end = text.index("    def _on_context_menu(self, pos):", start)
    chunk = text[start:end]
    assert chunk.count("setStretchLastSection(False)") == 1
    assert chunk.count("setDefaultSectionSize(110)") == 1
    assert chunk.count("setColumnWidth(0, 40)") == 1
    assert chunk.count("setColumnWidth(1, 220)") == 1
    assert chunk.count("setColumnWidth(2, 80)") == 1
    assert chunk.count("setColumnWidth(3, 110)") == 1
    assert chunk.count("setColumnWidth(4, 120)") == 1
    assert chunk.count("setAlternatingRowColors(True)") == 1
    assert chunk.count("verticalHeader().setVisible(False)") == 1


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


def test_inbox_widget_selected_doc_id_user_role_then_clipboard_fallback() -> None:
    """``selected_doc_id`` reads id from column 0 ``UserRole``, else parses display text via ``table_cell_clipboard_text``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def selected_doc_id(self) -> int | None:")
    end = text.index("class DetailPane(QScrollArea):", start)
    chunk = text[start:end]
    assert chunk.count("self.selectedItems()") == 1
    assert chunk.count("self.currentRow()") == 1
    assert chunk.count("Qt.ItemDataRole.UserRole") == 1
    assert chunk.count("table_cell_clipboard_text(self, r, 0)") == 1


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
    """``populate`` stores doc id on column 0, PDF vs Image in type column, date as first 10 chars."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def populate(self, rows: list):")
    end = text.index("    def selected_doc_id(self) -> int | None:", start)
    chunk = text[start:end]
    assert chunk.count("self.setRowCount(len(rows))") == 1
    assert chunk.count('int(row["id"])') == 1
    assert chunk.count("id_cell.setData(Qt.ItemDataRole.UserRole, did)") == 1
    assert chunk.count('doc_type = "PDF" if "pdf" in mime else "Image"') == 1
    assert chunk.count('(row["import_date"] or "")[:10]') == 1


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
    assert "tip.setToolTip" in text.split("class BusinessHub", 1)[1].split("def _refresh_current_subtab", 1)[0]


def test_main_help_menu_wires_more_tab_shortcuts_dialog() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    assert "show_more_main_tabs_keyboard_shortcuts_dialog" in text
    assert "&More tab shortcuts (F5)" in text


def test_more_main_tabs_shortcuts_module_exposes_help_dialog() -> None:
    path = _DESKTOP_APP_DIR / "more_main_tabs_shortcuts.py"
    text = path.read_text(encoding="utf-8")
    assert "def show_more_main_tabs_keyboard_shortcuts_dialog" in text
    assert "def more_main_tabs_keyboard_shortcuts_help_text" in text
    assert "Ctrl+7 Business" in text
    assert "Ctrl+2 Bank Import" in text
    assert "Help → Document intake shortcuts" in text
    assert "status bar" in text
    assert "per-item hover tooltips" in text
    assert "probooks.backup" in text
    assert "ok_tip=" in text


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
    assert "Link payment… — suggested-matches list" in rtab
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


def test_register_tab_exposes_shared_shortcuts_dialog_for_help_menu() -> None:
    rtab = (_DESKTOP_APP_DIR / "register_tab.py").read_text(encoding="utf-8")
    assert "def show_register_keyboard_shortcuts_dialog" in rtab


def test_desktop_main_cli_and_qt_app_strings_use_probooks_plus_ai() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    mod_doc_end = text.index('"""', 3)
    mod_doc = text[: mod_doc_end + 3]
    assert "help_epilog" in mod_doc
    assert "setStatusTip" in mod_doc and "status bar" in mod_doc
    assert "DetailPane" in mod_doc and "tooltips" in mod_doc
    hel = PROBOOKS_HELP_EPILOG.read_text(encoding="utf-8")
    assert "probooks.backup" in hel
    assert "File → Backup" in hel
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
    assert "File → Backup" in text[didx : didx + 700]
    assert "probooks backup" in text[didx : didx + 700]
    assert 'app.setApplicationName("ProBooks+ai")' in text
    assert 'app.setOrganizationName("ProBooks+ai")' in text
    assert "Keyboard shortcuts are summarized under" in text


def test_desktop_main_suppress_qt_font_stderr_handler_installs_chain() -> None:
    """``_suppress_qt_font_pointsize_stderr_spam`` filters ``QFont::setPointSize`` noise via ``qInstallMessageHandler``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("def _suppress_qt_font_pointsize_stderr_spam() -> None:")
    end = text.index("\n\ndef main():", start)
    chunk = text[start:end]
    assert chunk.count("qInstallMessageHandler(_handler)") == 1
    assert chunk.count("QFont::setPointSize") == 1
    assert chunk.count("Point size <= 0") == 1
    assert chunk.count("must be greater than 0") == 1
    assert chunk.count("getattr(_handler, \"_prev\", None)") == 1


def test_desktop_main_entrypoint_boot_sequence() -> None:
    """``main()`` installs the Qt log filter, parses args, applies theme, resumes last DB, shows ``MainWindow``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("def main():")
    end = text.index('\n\nif __name__ == "__main__":', start)
    chunk = text[start:end]
    assert chunk.count("_suppress_qt_font_pointsize_stderr_spam()") == 1
    assert chunk.count("parser.parse_args()") == 1
    assert chunk.count("QApplication(sys.argv)") == 1
    assert chunk.count("apply_dark_theme(app)") == 1
    assert chunk.count("MainWindow(db_path=db_path)") == 1
    assert chunk.count("window.show()") == 1
    assert chunk.count("sys.exit(app.exec())") == 1
    assert chunk.count("db_path = args.database") == 1
    assert chunk.count("if db_path is None:") == 1
    assert chunk.count("db_path = last") == 1
    assert chunk.count('QSettings().value("company_database_path", "", type=str)') == 1
    assert chunk.count("Path(last).is_file()") == 1


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
    assert text.count("+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX") >= 2


def test_reports_tab_run_and_export_buttons_have_tooltips() -> None:
    text = (_DESKTOP_APP_DIR / "reports_tab.py").read_text(encoding="utf-8")
    assert "b.setToolTip(tip)" in text
    assert "btn_export.setToolTip" in text
    assert "F5 re-runs" in text
    assert "_start.setToolTip" in text
    assert "_end.setToolTip" in text
    assert "filt.setToolTip" in text
    assert "_summary.setToolTip" in text
    assert "tip.setToolTip" in text
    assert "self._table.setToolTip(" in text
    assert "act_keys.setToolTip" in text
    assert "act_copy.setToolTip" in text
    assert text.count("+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX") >= 2


def test_bank_import_header_buttons_manage_and_csv_have_tooltips() -> None:
    text = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    assert "btn_manage.setToolTip" in text
    assert "btn_import.setToolTip" in text
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
    assert jt.count("+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX") >= 4


def test_audit_tab_export_and_apply_filter_buttons_have_tooltips() -> None:
    at = (_DESKTOP_APP_DIR / "audit_tab.py").read_text(encoding="utf-8")
    assert "btn_export.setToolTip" in at
    assert "btn_apply.setToolTip" in at
    assert "_ent_type.setToolTip" in at
    assert "_ent_id.setToolTip" in at
    assert "lbl_audit_ent_type.setToolTip" in at
    assert "lbl_audit_ent_id.setToolTip" in at
    assert "hint.setToolTip" in at
    assert "self._tbl.setToolTip(" in at
    assert "act_keys.setToolTip" in at
    assert "act_copy.setToolTip" in at
    assert at.count("+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX") >= 2


def test_bank_import_manage_accounts_and_reconciliation_buttons_have_tooltips() -> None:
    bit = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    assert "_btn_add.setToolTip" in bit
    assert "_btn_reconcile.setToolTip" in bit
    assert "_btn_export_csv.setToolTip" in bit
    rec_chunk = bit.split("class ReconciliationPanel", 1)[1].split("class BankImportTab", 1)[0]
    assert "Compares statement dates and balances" in rec_chunk
    assert "_lbl_status.setToolTip" in rec_chunk


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


def test_detail_pane_scroll_and_main_toolbar_have_hover_tooltips() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class DetailPane")
    end = text.index("class AppHeaderWidget", start)
    chunk = text[start:end]
    assert "self.setToolTip(" in chunk
    assert "Scroll the detail pane" in chunk
    assert "inner.setToolTip(" in chunk
    assert "Preview, extracted fields, categorization" in chunk
    assert "File → Backup" in chunk
    assert "toolbar.setToolTip" in text
    assert "Document Intake toolbar" in text
    assert "probooks backup" in text.split("toolbar.setToolTip", 1)[1][:400]


def test_desktop_main_detail_pane_wires_actions_load_ai_and_clear() -> None:
    """``DetailPane`` buttons emit signals; load/AI/collect/clear paths touch DB and fields."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class DetailPane(QScrollArea):")
    end = text.index("class AppHeaderWidget(QFrame):", start)
    chunk = text[start:end]
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
    assert chunk.count("db.get_document(doc_id)") == 1
    assert chunk.count("db.get_approved(doc_id)") == 1
    assert chunk.count("db.get_latest_extraction(doc_id)") == 1
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
    assert chunk.count('STATUS_COLORS.get(status, "#000")') == 1


def test_desktop_main_detail_pane_load_document_approved_or_extraction_and_enables_buttons() -> None:
    """``load_document`` stores ``_doc_id``, fills fields from approved row else latest extraction, enables actions."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def load_document(self, doc_id: int, db: DocumentDatabase):")
    end = text.index("    def populate_ai_result(self, result, suggestions=None):", start)
    chunk = text[start:end]
    assert chunk.count("self._doc_id = doc_id") == 1
    assert chunk.count("if not row:") == 1
    assert chunk.count("db.get_document(doc_id)") == 1
    assert chunk.count("approved = db.get_approved(doc_id)") == 1
    assert chunk.count("extraction = db.get_latest_extraction(doc_id)") == 1
    assert chunk.count("src = approved or extraction") == 1
    assert chunk.count("self._populate_fields(src)") == 1
    assert chunk.count("if approved:") == 1
    assert chunk.count('approved["coa_account"]') == 1
    assert chunk.count('approved["tax_category"]') == 1
    assert chunk.count("self._set_buttons_enabled(True)") == 1


def test_desktop_main_detail_pane_populate_ai_result_applies_suggestions() -> None:
    """``populate_ai_result`` fills from extraction then maps COA/confidence/rationale from suggestions."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def populate_ai_result(self, result, suggestions=None):")
    end = text.index("    def collect_approved_values(self) -> dict:", start)
    chunk = text[start:end]
    assert chunk.count("_populate_fields_from_extraction(result)") == 1
    assert "suggestions and not suggestions.error" in chunk
    assert chunk.count("findData(s_coa, Qt.ItemDataRole.UserRole)") == 1
    assert chunk.count("self._f_coa.setCurrentIndex(-1)") == 1
    assert chunk.count("self._f_coa.setEditText(s_coa)") == 1
    assert chunk.count("self._f_coa.setCurrentIndex(0)") == 1
    assert chunk.count('self._f_confidence.setText(f"{conf:.0%}")') == 1
    assert chunk.count("self._lbl_rationale.setText(suggestions.rationale or \"\")") == 1


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
    """``collect_approved_values`` dict keys align with ``DocumentDatabase.save_approved`` / ``approved_values``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def collect_approved_values(self) -> dict:")
    end = text.index(
        "    def _show_preview(self, stored_path: str, mimetype: str, page_count):",
        start,
    )
    chunk = text[start:end]
    for key in _DETAIL_APPROVED_VALUE_KEYS:
        assert chunk.count(f'"{key}":') == 1, key


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
    assert chunk.count('mimetype == "application/pdf"') == 1
    assert chunk.count('pages = page_count or "?"') == 1
    assert chunk.count("escape_ampersand_for_qt(Path(stored_path).name)") == 1
    assert chunk.count('"(No preview available)"') == 1


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
    """``DetailPane`` ctor stores doc/COA state and hosts the form on a resizable inner ``QWidget``."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class DetailPane(QScrollArea):")
    init_s = text.index("    def __init__(self, coa_list: list[str], parent=None):", start)
    end = text.index("        # -- Document info ---------------------------------------------------", init_s)
    chunk = text[init_s:end]
    assert chunk.count("self._doc_id: int | None = None") == 1
    assert chunk.count("self._coa_list = coa_list") == 1
    assert chunk.count("self.setWidget(inner)") == 1
    assert chunk.count("self.setWidgetResizable(True)") == 1


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
    """**Categorisation Suggestions** uses four ``QFormLayout`` rows (COA through rationale)."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("        cat_layout = QFormLayout(cat_group)")
    end = text.index("        layout.addWidget(cat_group)", start)
    chunk = text[start:end]
    assert chunk.count("cat_layout.addRow(") == 4


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
    """``_COA_SELECT_LABEL`` seeds the detail COA combo; ``update_coa`` rebuilds and restores selection."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("_COA_SELECT_LABEL = ")
    end = text.index("    def clear_view(self):", start)
    chunk = text[start:end]
    assert "select" in chunk.split("_COA_SELECT_LABEL = ", 1)[1].split("\n", 1)[0]
    assert chunk.count("escape_ampersand_for_qt(_COA_SELECT_LABEL)") == 1
    assert chunk.count("def update_coa(self, coa_list: list[str]):") == 1
    assert chunk.count("def _fill_coa_combo(self, coa_list: list[str]) -> None:") == 1
    assert chunk.count("self._f_coa.clear()") == 1
    assert chunk.count("self._set_coa_combo_raw(current)") == 1
    assert chunk.count("def _coa_combo_raw_value(self) -> str | None:") == 1
    assert chunk.count("def _set_coa_combo_raw(self, raw: str | None) -> None:") == 1


def test_desktop_main_detail_pane_clear_view_resets_doc_fields_and_disables_actions() -> None:
    """``clear_view`` clears selection, preview, extracted fields, COA row, and disables action buttons."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def clear_view(self):")
    end = text.index("class AppHeaderWidget(QFrame):", start)
    chunk = text[start:end]
    assert chunk.count("self._doc_id = None") == 1
    assert chunk.count('self._lbl_filename.setText("No document selected")') == 1
    assert chunk.count('self._preview_label.setText("(Select a document to preview)")') == 1
    assert chunk.count("self._f_vendor.clear()") == 1
    assert chunk.count("self._f_subtotal.setValue(0.0)") == 1
    assert chunk.count("self._f_tax.setValue(0.0)") == 1
    assert chunk.count("self._f_total.setValue(0.0)") == 1
    assert chunk.count('self._f_currency.setText("USD")') == 1
    assert chunk.count('self._f_confidence.setText("\\u2013")') == 1
    assert chunk.count("self._lbl_rationale.clear()") == 1
    assert chunk.count("self._set_buttons_enabled(False)") == 1


def test_main_window_on_reject_sets_needs_review_refreshes_and_status_message() -> None:
    """Reject flags the document for review again, syncs inbox + detail, and updates the status bar."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("    def _on_reject(self, doc_id: int):")
    end = text.index("    # -- helpers", start)
    chunk = text[start:end]
    assert chunk.count('self._db.set_status(doc_id, "Needs Review")') == 1
    assert chunk.count("self._refresh_inbox()") == 1
    assert chunk.count("self._detail.load_document(doc_id, self._db)") == 1
    assert chunk.count("Document flagged \\u2013 Needs Review.") == 1


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
    assert 'tip_message_box_buttons(box, cancel="Close without exporting.")' in chunk
    assert "box.setToolTip(" in chunk
    assert "list filter is active" in chunk


def test_qt_mnemonic_tip_message_box_buttons_helper() -> None:
    mn = (_DESKTOP_APP_DIR / "qt_mnemonic.py").read_text(encoding="utf-8")
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


def test_main_window_detail_pane_thirteen_call_sites() -> None:
    """``MainWindow`` wires the detail pane for signals, load, AI, approve flow, and COA refresh."""
    text = _MAIN.read_text(encoding="utf-8")
    start = text.index("class MainWindow(QMainWindow):")
    end = text.index("\n\n# ---------------------------------------------------------------------------\n# Entry point", start)
    chunk = text[start:end]
    assert chunk.count("self._detail.") == 13


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
    assert chunk.count("self._status_bar.showMessage(") == 11
    assert chunk.count("self._tabs.") == 18
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
    assert chunk.count("self._db.get_document(doc_id)") == 3
    assert chunk.count("self._db.add_document(path, mime, store=True)") == 1
    assert chunk.count("self._db.save_extraction(doc_id, result)") == 1
    assert chunk.count("self._db.save_approved(doc_id, values)") == 1
    assert chunk.count("self._db.set_status(doc_id,") == 6
    assert chunk.count("application_version()") == 2


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
    bi = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    bidx = bi.index("def show_bank_import_keyboard_shortcuts_dialog")
    b = bi[bidx : bi.index("\n\n# =====", bidx)]
    assert needle in b
    reg = (_DESKTOP_APP_DIR / "register_tab.py").read_text(encoding="utf-8")
    ridx = reg.index("def show_register_keyboard_shortcuts_dialog")
    r = reg[ridx : reg.index("\n\nclass RegisterTab", ridx)]
    assert needle in r
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    bidx = et.index("def show_business_keyboard_shortcuts_dialog")
    e = et[bidx : et.index("\n\nclass BusinessHub", bidx)]
    assert needle in e
    mm = (_DESKTOP_APP_DIR / "more_main_tabs_shortcuts.py").read_text(encoding="utf-8")
    m = mm.split("show_more_main_tabs_keyboard_shortcuts_dialog", 1)[1].split("def ", 1)[0]
    assert needle in m


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
    assert "File → Backup" in main_t[sp : sp + 220]
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


def test_extra_tabs_exposes_business_shortcuts_dialog_for_help_menu() -> None:
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    assert "def show_business_keyboard_shortcuts_dialog" in et
    assert "def _business_keyboard_shortcuts_help_text" in et
    assert (
        et.count("lambda: show_business_keyboard_shortcuts_dialog(self)") == 4
    ), "Rules, AR, AP, Payroll grids should open Business shortcuts from context menu"
    assert (
        "show_business_keyboard_shortcuts_dialog(menu_parent)"
        in et[et.index("def _attach_table_copy_row_menu") : et.index("def _wire_find_focuses_line_edit")]
    ), "Business dialog tables should open Business shortcuts from context menu"


def test_bank_import_tab_f5_reload_shortcut_wired() -> None:
    path = _DESKTOP_APP_DIR / "bank_import_tab.py"
    text = path.read_text(encoding="utf-8")
    assert "def _reload_bank_import_view" in text
    assert 'QKeySequence("F5")' in text
    assert "activated.connect(self._reload_bank_import_view)" in text
    assert "F5 refreshes accounts and import batches" in text
    assert "probooks.backup" in text.split("F5 refreshes accounts and import batches", 1)[1][:450]
    assert "Manage Bank Accounts table" in text
    assert "Bank import shortcuts" in text
    assert "Keyboard shortcuts…" in text
    assert "_show_bank_import_keyboard_shortcuts_help" in text


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
    assert "+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX" in bit[ak2 : ak2 + 220]


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
    assert "+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX" in jt[js:je]
    ls = jt.index("def _on_lines_context_menu")
    le = jt.index("def _refresh_list", ls)
    assert "act_copy.setToolTip" in jt[ls:le]
    assert "+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX" in jt[ls:le]

    rep = (_DESKTOP_APP_DIR / "reports_tab.py").read_text(encoding="utf-8")
    rps = rep.index("def _on_report_context_menu")
    rpe = rep.index("def _fill_table", rps)
    assert "act_keys.setToolTip" in rep[rps:rpe]
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
    assert ad_ctx.count("+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX") >= 2

    coa = (_DESKTOP_APP_DIR / "coa_tab.py").read_text(encoding="utf-8")
    cs = coa.index("def _on_coa_context_menu")
    ce = coa.index("def _on_selection", cs)
    assert "act_history.setToolTip" in coa[cs:ce]
    assert coa[cs:ce].count("+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX") >= 2

    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
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


def test_bank_import_transactions_table_widget_has_hover_tooltip() -> None:
    bit = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    start = bit.index("class TransactionsTable")
    end = bit.index("\n\n# ===========================================================================", start)
    chunk = bit[start:end]
    assert "self.setToolTip(" in chunk


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


def test_register_tab_tools_row_and_link_dialog_buttons_have_tooltips() -> None:
    text = (_DESKTOP_APP_DIR / "register_tab.py").read_text(encoding="utf-8")
    for needle in (
        "reg_flag_rcpt.setToolTip",
        "reg_link_pay.setToolTip",
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
        "tip.setToolTip",
    ):
        assert needle in text, f"register_tab should set tooltip on {needle!r}"
    assert text.count("tip_qdialog_button_box(\n            bb,") >= 3
    assert "Set or clear a transfer link" in text
    assert "Split one unposted bank transaction" in text
    assert "Link this bank row to AR" in text
    assert text.count("+ CLIPBOARD_DB_BACKUP_TOOLTIP_SUFFIX") >= 4


def test_register_keyboard_shortcuts_help_text_matches_wired_chords() -> None:
    """Single helper lists the same chords as QShortcut (avoid help drifting from behavior)."""
    text = (_DESKTOP_APP_DIR / "register_tab.py").read_text(encoding="utf-8")
    start = text.index("def _register_keyboard_shortcuts_help_text")
    end = text.index("\n\nclass RegisterTab", start)
    chunk = text[start:end]
    for needle in (
        "Link payment…",
        "F5 — Refresh",
        "Ctrl+Shift+G",
        "Ctrl+Shift+E",
        "Ctrl+Shift+C",
        "Ctrl+Shift+U",
        "Document intake shortcuts",
        "More tab shortcuts (F5)",
        "Business shortcuts",
        "Bank import shortcuts",
    ):
        assert needle in chunk, f"register shortcuts help should mention {needle!r}"


def test_register_context_menu_includes_keyboard_shortcuts_action() -> None:
    text = (_DESKTOP_APP_DIR / "register_tab.py").read_text(encoding="utf-8")
    assert "Keyboard shortcuts…" in text
    assert "_show_register_keyboard_shortcuts_help" in text


def test_register_tab_clr_header_tooltip_documents_batch_reconciled() -> None:
    """Clr column header explains C vs R and points users at Bank Import for batch R."""
    text = (_DESKTOP_APP_DIR / "register_tab.py").read_text(encoding="utf-8")
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
