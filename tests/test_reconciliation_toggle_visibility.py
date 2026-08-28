"""Main tab strip: no recon-driven hiding of top-level tabs (Step 1)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from probooksai.bank_import import BankDatabase


@pytest.fixture
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_all_main_tabs_remain_visible_regardless_of_register_reconciliation_mode(
    qapp: QApplication, tmp_path: Path
) -> None:
    from desktop_app.main import MainWindow

    db_path = tmp_path / "recon_vis.db"
    BankDatabase(str(db_path)).close()
    w = MainWindow(db_path=str(db_path))
    try:
        tabs = w._tabs
        tb = tabs.tabBar()
        reg = w._register_tab
        chk = reg._recon_checkbox
        idx_reg = tabs.indexOf(reg)
        tabs.setCurrentIndex(idx_reg)
        qapp.processEvents()
        chk.setChecked(True)
        qapp.processEvents()
        assert reg.is_reconciliation_mode()
        aging_idx = tabs.indexOf(w._ar_aging_screen)
        for i in range(tabs.count()):
            if i == aging_idx:
                assert not tb.isTabVisible(i)
            else:
                assert tb.isTabVisible(i)
        chk.setChecked(False)
        qapp.processEvents()
        for i in range(tabs.count()):
            if i == aging_idx:
                assert not tb.isTabVisible(i)
            else:
                assert tb.isTabVisible(i)
    finally:
        w.close()
