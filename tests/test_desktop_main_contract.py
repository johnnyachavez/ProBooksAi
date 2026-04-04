"""Contract tests for the PySide6 ``desktop_app`` package via source scans (no Qt import).

Asserts main-window wiring, tab and dialog hover ``setToolTip`` / menu patterns, ``qt_mnemonic``
helpers, and guardrails against static ``QMessageBox`` dialogs and ad-hoc ``.button(Q*StandardButton`` lookups.
"""

from __future__ import annotations

from pathlib import Path

from tests.repo_paths import (
    DESKTOP_APP_DIR as _DESKTOP_APP_DIR,
    PROBOOKS_HELP_EPILOG,
    REPO_ROOT,
)

_MAIN = _DESKTOP_APP_DIR / "main.py"


def _iter_desktop_app_py_files() -> list[Path]:
    return sorted(_DESKTOP_APP_DIR.rglob("*.py"))


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


def test_main_toolbar_import_tooltip_echoes_file_menu_ctrl_o() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    assert "act_import.setToolTip" in text
    i = text.index("act_import.setToolTip")
    assert "Ctrl+O" in text[i : i + 420]
    assert "File → Backup" in text[i : i + 420]


def test_main_menu_bar_sets_status_tips_for_shortcut_actions() -> None:
    text = _MAIN.read_text(encoding="utf-8")
    assert "def _menu_action_tip" in text
    assert "act.setStatusTip(tip)" in text
    start = text.index("def _build_menu_bar")
    end = text.index("def dragEnterEvent", start)
    chunk = text[start:end]
    assert ".setStatusTip(" not in chunk
    assert chunk.count("_menu_action_tip(") >= 21
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
    assert "probooks.backup" in chunk
    assert "Company .db safety: File → Backup / Restore (probooks.backup)." in chunk


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
    assert "Company .db safety: File → Backup / Restore (probooks.backup)." in text


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
    assert text.count("Company .db safety: File → Backup / Restore (probooks.backup).") >= 1


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
    assert text.count("Company .db safety: File → Backup / Restore (probooks.backup).") >= 2


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
    assert jt.count("Company .db safety: File → Backup / Restore (probooks.backup).") >= 4


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
    assert at.count("Company .db safety: File → Backup / Restore (probooks.backup).") >= 1


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
    assert "Company .db safety: File → Backup / Restore (probooks.backup)." in ad[h0:h1]


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
    assert "probooks.backup" in bit[ak2 : ak2 + 220]


def test_grids_context_menus_use_qaction_hover_tooltips() -> None:
    """Bank, register, COA, journal, reports, audit, Business, and audit dialog context menus tip QActions."""
    bit = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    txn_s = bit.index("def _on_import_txn_context_menu")
    txn_e = bit.index("def _open_import_txn_attachment", txn_s)
    txn_chunk = bit[txn_s:txn_e]
    assert "act_keys.setToolTip" in txn_chunk
    assert "probooks.backup" in txn_chunk
    assert "act_att.setToolTip" in txn_chunk
    assert "act_history.setToolTip" in txn_chunk
    acc_s = bit.index("def _on_accounts_table_context_menu")
    acc_e = bit.index("def _refresh(self):", acc_s)
    assert "act_keys.setToolTip" in bit[acc_s:acc_e]

    reg = (_DESKTOP_APP_DIR / "register_tab.py").read_text(encoding="utf-8")
    rs = reg.index("def _on_register_context_menu")
    re = reg.index("def _open_register_attachment", rs)
    assert "probooks.backup" in reg[rs:re]
    assert "act_clr.setToolTip" in reg[rs:re]
    assert "act_history.setToolTip" in reg[rs:re]

    jt = (_DESKTOP_APP_DIR / "journal_tab.py").read_text(encoding="utf-8")
    js = jt.index("def _on_journal_list_context_menu")
    je = jt.index("def _on_lines_context_menu", js)
    assert "act_keys.setToolTip" in jt[js:je]
    assert "probooks.backup" in jt[js:je]
    ls = jt.index("def _on_lines_context_menu")
    le = jt.index("def _refresh_list", ls)
    assert "act_copy.setToolTip" in jt[ls:le]
    assert "probooks.backup" in jt[ls:le]

    rep = (_DESKTOP_APP_DIR / "reports_tab.py").read_text(encoding="utf-8")
    rps = rep.index("def _on_report_context_menu")
    rpe = rep.index("def _fill_table", rps)
    assert "act_keys.setToolTip" in rep[rps:rpe]
    assert "probooks.backup" in rep[rps:rpe]

    at = (_DESKTOP_APP_DIR / "audit_tab.py").read_text(encoding="utf-8")
    aus = at.index("def _on_audit_context_menu")
    aue = at.index("def _export_csv", aus)
    assert "act_copy.setToolTip" in at[aus:aue]
    assert "probooks.backup" in at[aus:aue]

    ad = (_DESKTOP_APP_DIR / "audit_dialog.py").read_text(encoding="utf-8")
    assert "act_keys.setToolTip" in ad
    assert "def _audit_history_table_context_menu" in ad

    coa = (_DESKTOP_APP_DIR / "coa_tab.py").read_text(encoding="utf-8")
    cs = coa.index("def _on_coa_context_menu")
    ce = coa.index("def _on_selection", cs)
    assert "act_history.setToolTip" in coa[cs:ce]
    assert "probooks.backup" in coa[cs:ce]

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
    assert "Company .db safety: File → Backup / Restore (probooks.backup)." in inv_chunk


def test_bank_import_transactions_table_widget_has_hover_tooltip() -> None:
    bit = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    start = bit.index("class TransactionsTable")
    end = bit.index("\n\n# ===========================================================================", start)
    chunk = bit[start:end]
    assert "self.setToolTip(" in chunk


def test_bank_import_context_menu_copy_row_tooltips_mention_backup_safety() -> None:
    bit = (_DESKTOP_APP_DIR / "bank_import_tab.py").read_text(encoding="utf-8")
    assert bit.count("Company .db safety: File → Backup / Restore (probooks.backup).") >= 3


def test_extra_tabs_business_main_grids_have_hover_tooltips() -> None:
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    assert et.count("F5 refreshes when Business has focus.") == 5


def test_extra_tabs_business_copy_row_tooltips_mention_backup_safety() -> None:
    et = (_DESKTOP_APP_DIR / "extra_tabs.py").read_text(encoding="utf-8")
    assert et.count("Company .db safety: File → Backup / Restore (probooks.backup).") >= 6


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
    assert text.count("Company .db safety: File → Backup / Restore (probooks.backup).") >= 2


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
