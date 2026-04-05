"""Shared **Help → More tab shortcuts (F5)…** text for COA, Journal, Reports, and Audit."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from desktop_app.qt_mnemonic import message_box_information_ok
from desktop_app.table_clipboard import VIEW_BANK_REGISTER_KEYS_TOOLTIP


def more_main_tabs_keyboard_shortcuts_help_text() -> str:
    return (
        "These shortcuts apply when the matching main tab or its controls have focus:\n\n"
        "Chart of Accounts — F5 reloads the grid from the database (respects Show inactive).\n"
        "Journal — F5 reloads the entry list and line detail (same as Refresh).\n"
        "Reports — F5 re-runs the last Trial Balance, Income Statement, or Balance Sheet "
        "you opened, if any.\n"
        "Audit log — F5 reloads the log (same as Refresh).\n\n"
        "Export CSV on Journal, Reports, and Audit uses UTF-8 with BOM for Excel. "
        "Register (Ctrl+Shift+E), Business hub, and Bank Import reconciliation / line-compare exports "
        "use the same encoding—see those tabs' Help dialogs. "
        "On **Bank register** and **Bank Import** batch preview, right-click a saved transaction row for "
        "**Copy row**, **Copy transaction id**, **Copy date**, **Copy amount**, **Copy payee / description**, **Copy memo**, **Copy number / ref**, **Copy category (COA)**, "
        "or **Open linked Business record…** when that row has a **complete bank link** (opens in Business). "
        "**Ctrl+Shift+B** on **Bank register** or on **Bank Import** batch preview / line-reconciliation grid "
        "(same as Recon → Transaction Tools → Open linked Business record when the link is complete). "
        "The **Bank Import** line-reconciliation grid (**Matched / Missing / Extra**) adds **Copy row** plus **Copy statement** / **register** date, amount, and description, "
        "**Copy register transaction id**, and **Open linked Business record…** when **Reg #** has a **complete bank link**; see **Help → Bank import shortcuts….**\n\n"
        "View menu: Ctrl+1 Document Intake, Ctrl+2 Bank Import, Ctrl+3 Register, "
        "Ctrl+4 Chart of Accounts, Ctrl+5 Reports, Ctrl+6 Journal, Ctrl+7 Business, "
        "Ctrl+8 Audit log.\n"
        "Tools menu: Ctrl+Shift+I — Invoice… (Business tab, Invoices AR).\n"
        "Help → Document intake shortcuts… lists the same chords plus Intake-specific notes "
        "(including File → Backup company file… / Restore from backup… via probooks.backup).\n"
        "Hover the main window menu bar (File, View, Edit, Tools, Recon, Help) for status bar hints and per-item hover tooltips.\n\n"
        "Right-click the main grid or list on these tabs (including empty area) for "
        "Keyboard shortcuts… (same as this dialog).\n\n"
        "Other shortcuts:\n"
        "Help → Document intake shortcuts… (includes File → Backup / Restore via probooks.backup).\n"
        "Help → Bank import shortcuts…\n"
        "Help → Bank register keyboard shortcuts…\n"
        "Register bulk actions (add transaction, post, export, cleared, link, open linked Business, …): main **Recon** menu; "
        "**Link payment…** also offers **Open linked Business record…** when the stored link is complete (can open in Business).\n"
        "Help → Business shortcuts…\n"
    )


def show_more_main_tabs_keyboard_shortcuts_dialog(parent: QWidget) -> None:
    message_box_information_ok(
        parent,
        "More tab shortcuts (F5)",
        more_main_tabs_keyboard_shortcuts_help_text(),
        ok_tip=(
            "Close; shortcuts apply when COA, Journal, Reports, or Audit has focus. "
            + VIEW_BANK_REGISTER_KEYS_TOOLTIP
            + "Company .db: File → Backup / Restore (probooks.backup)."
        ),
    )
