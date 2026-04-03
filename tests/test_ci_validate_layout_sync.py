"""Layout contract: twin validators stay aligned; GitHub Actions workflows keep key commands stable."""

from __future__ import annotations

import re

from tests.repo_paths import (
    CI_VALIDATE_LAYOUT_PS1 as _PS1,
    CI_VALIDATE_LAYOUT_SH as _SH,
    CURSOR_RULE_GITHUB_WORK_CONTEXT_MDC,
    DOCS_BACKLOG_MD,
    DOCS_CONTRIBUTING_MD,
    DOCS_ISSUES_BACKLOG_MD,
    DOCS_ROADMAP_MD,
    GITHUB_ISSUE_TEMPLATE_BUG_REPORT_MD,
    GITHUB_ISSUE_TEMPLATE_CONFIG_YML,
    GITHUB_ISSUE_TEMPLATE_FEATURE_REQUEST_MD,
    GITHUB_PULL_REQUEST_TEMPLATE_MD,
    GITHUB_WORKFLOW_CI_YML,
    GITHUB_WORKFLOW_UI_SCREENSHOT_YML,
    INDEX_HTML,
    INVOICE_HTML,
    README_MD,
    REVIEW_HTML,
    REPO_ROOT,
    TESTS_DIR,
)


def _paths_from_sh(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^require ([^\s]+)\s*$", line.strip())
        if m:
            out.append(m.group(1))
    return out


def _paths_from_ps1(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        m = re.match(r'^Require-File "([^"]+)"\s*$', line.strip())
        if m:
            out.append(m.group(1))
    return out


def test_ci_validate_layout_sh_and_ps1_same_paths_and_order() -> None:
    sh_paths = _paths_from_sh(_SH.read_text(encoding="utf-8"))
    ps1_paths = _paths_from_ps1(_PS1.read_text(encoding="utf-8"))
    assert sh_paths == ps1_paths, (
        "ci_validate_layout.sh and ci_validate_layout.ps1 must list the same paths in the same order.\n"
        f"sh ({len(sh_paths)}): {sh_paths!r}\n"
        f"ps1 ({len(ps1_paths)}): {ps1_paths!r}"
    )


def test_ci_validate_layout_sh_require_paths_exist() -> None:
    """Every ``require`` path in ``ci_validate_layout.sh`` must exist (twin .ps1 uses the same list)."""
    rels = _paths_from_sh(_SH.read_text(encoding="utf-8"))
    assert rels, "expected at least one require line in ci_validate_layout.sh"
    for rel in rels:
        path = REPO_ROOT / rel
        assert path.is_file(), (
            f"ci_validate_layout.sh lists require {rel!r} but {path} is not a file"
        )


def test_layout_validator_hub_cites_require_paths_pytest() -> None:
    """Layout scripts + ci.yml validate comments should point at the pytest that mirrors ``require`` / ``Require-File``."""
    needle = "test_ci_validate_layout_sh_require_paths_exist"
    yml_head = "\n".join(GITHUB_WORKFLOW_CI_YML.read_text(encoding="utf-8").splitlines()[:24])
    assert needle in yml_head, "ci.yml validate job comments should cite pytest require-path test"
    for path, label in ((_SH, "ci_validate_layout.sh"), (_PS1, "ci_validate_layout.ps1")):
        head = "\n".join(path.read_text(encoding="utf-8").splitlines()[:16])
        assert needle in head, f"{label} header should cite pytest {needle!r}"


def test_ci_yml_validate_job_invokes_layout_shell_script() -> None:
    """Keep path checks in scripts/ci_validate_layout.sh, not re-inlined into the workflow YAML."""
    yml = GITHUB_WORKFLOW_CI_YML.read_text(encoding="utf-8")
    assert re.search(r"(?m)^\s*run:\s+bash scripts/ci_validate_layout\.sh\s*$", yml), (
        ".github/workflows/ci.yml validate step must use: run: bash scripts/ci_validate_layout.sh"
    )


def test_ci_yml_python_job_uses_ci_extra_headless_pytest_and_wheel() -> None:
    """Main CI job should match docs: .[ci], offscreen Qt, pytest, Hatch wheel."""
    yml = GITHUB_WORKFLOW_CI_YML.read_text(encoding="utf-8")
    assert 'python-version: "3.12"' in yml
    assert 'pip install -e ".[ci]"' in yml
    assert "QT_QPA_PLATFORM: offscreen" in yml
    assert re.search(r"(?m)^\s*run:\s+python -m pytest\s*$", yml), (
        "ci.yml python job should run tests via: run: python -m pytest"
    )
    assert "pip install build && python -m build --wheel" in yml


def test_ui_screenshot_workflow_uses_xvfb_capture_script_and_desktop_extra() -> None:
    """PR screenshot workflow must stay headless-friendly and match README scripting."""
    yml = GITHUB_WORKFLOW_UI_SCREENSHOT_YML.read_text(encoding="utf-8")
    assert "continue-on-error: true" in yml
    assert "xvfb-run" in yml
    assert "scripts/capture_ui_screenshot.py" in yml
    assert 'pip install -e ".[desktop]"' in yml, (
        'ui-screenshot.yml should install the package with the desktop extra: pip install -e ".[desktop]"'
    )


def test_ci_and_ui_screenshot_workflows_use_matching_python_version() -> None:
    """Avoid drift between the main CI job and the optional screenshot job."""
    ci = GITHUB_WORKFLOW_CI_YML.read_text(encoding="utf-8")
    shot = GITHUB_WORKFLOW_UI_SCREENSHOT_YML.read_text(encoding="utf-8")

    def version_from(text: str) -> str:
        m = re.search(r'python-version:\s*"([^"]+)"', text)
        assert m, "expected setup-python python-version in workflow"
        return m.group(1)

    v_ci = version_from(ci)
    v_shot = version_from(shot)
    assert v_ci == v_shot, (
        f"Use the same python-version in ci.yml and ui-screenshot.yml (got {v_ci!r} vs {v_shot!r})."
    )


def test_contract_test_modules_are_registered_in_layout_validators() -> None:
    """Every tests/test_*_contract.py must appear in ci_validate_layout.sh and .ps1."""
    tests_dir = TESTS_DIR
    names = sorted(p.name for p in tests_dir.glob("test_*_contract.py"))
    assert names, "expected at least one tests/test_*_contract.py"
    sh_text = _SH.read_text(encoding="utf-8")
    ps1_text = _PS1.read_text(encoding="utf-8")
    for name in names:
        rel = f"tests/{name}"
        assert f"require {rel}" in sh_text, f"add 'require {rel}' to scripts/ci_validate_layout.sh"
        assert f'Require-File "{rel}"' in ps1_text, f'add Require-File "{rel}" to scripts/ci_validate_layout.ps1'


def test_contributing_contract_table_rows_match_contract_modules() -> None:
    """docs/CONTRIBUTING.md table must list every tests/test_*_contract.py (onboarding + review)."""
    tests_dir = TESTS_DIR
    names = sorted(p.name for p in tests_dir.glob("test_*_contract.py"))
    md = DOCS_CONTRIBUTING_MD.read_text(encoding="utf-8")
    for name in names:
        row = f"| **`{name}`** |"
        assert row in md, f"add contract table row starting with {row!r} to docs/CONTRIBUTING.md"


def test_readme_opener_mentions_shell_cli_desktop_sqlite() -> None:
    """README lede matches shipped surfaces (static shell, CLI, desktop, Excel workbook, SQLite)."""
    readme = README_MD.read_text(encoding="utf-8")
    assert "Accounting app foundation:" in readme
    start = readme.index("Accounting app foundation:")
    line = readme[start : readme.find("\n", start)]
    for needle in ("static HTML", "probooks", "PySide6 desktop", "Excel COA workbook", "openpyxl", "SQLite"):
        assert needle in line, f"README lede should mention {needle!r}: {line!r}"


def test_readme_python_cli_section_mentions_backup_restore_online_api() -> None:
    """README ## Python CLI should document backup/restore commands and shared probooks.backup."""
    readme = README_MD.read_text(encoding="utf-8")
    start = readme.index("## Python CLI")
    end = readme.index("### CSV import", start)
    section = readme[start:end]
    for needle in (
        "probooks backup",
        "probooks restore",
        "probooks.backup",
        "SQLite online backup",
        "File → Backup",
        "File → Restore",
        "**`--db`**",
    ):
        assert needle in section, f"README Python CLI section should mention {needle!r}"


def test_readme_default_database_paths_notes_two_schemas_and_roadmap() -> None:
    """README should state CLI vs desktop DB files are not interchangeable and point at ROADMAP #21 note."""
    readme = README_MD.read_text(encoding="utf-8")
    head = "### Default database paths (Windows)"
    start = readme.index(head)
    chunk = readme[start : readme.index("\n## ", start)]
    for needle in (
        "probooks.db",
        "probooksai.db",
        "#21",
        "Why not one",
        "docs/ROADMAP.md#implementation-snapshot-repository-2026-04",
        "Bank DDL inventory",
        "tests/test_issue_21_schema_inventory.py",
        "docs/CONTRIBUTING.md#continuous-integration",
        "SQLite issue #21",
    ):
        assert needle in chunk, f"README default DB section should mention {needle!r}"


def test_roadmap_snapshot_why_not_one_db_points_at_issue_21_inventory() -> None:
    """ROADMAP Why not one .db yet should point at the CLI vs desktop DDL inventory tests."""
    text = DOCS_ROADMAP_MD.read_text(encoding="utf-8")
    start = text.index("**Why not one `.db` yet:**")
    end = text.index("\n| Roadmap phases |", start)
    chunk = text[start:end]
    assert "Bank DDL inventory" in chunk
    assert "tests/test_issue_21_schema_inventory.py" in chunk
    assert "](CONTRIBUTING.md#continuous-integration)" in chunk
    assert "**SQLite issue #21** bullet" in chunk


def test_readme_desktop_section_documents_theme_and_qt_font_filter() -> None:
    """README Desktop section stays aligned with Fusion theme + Windows Qt stderr filter."""
    readme = README_MD.read_text(encoding="utf-8")
    head = "## Desktop app (PySide6)"
    start = readme.index(head)
    rest = readme[start + len(head) :]
    next_section = rest.index("\n## ")
    section = rest[:next_section]
    for needle in (
        "Fusion",
        "desktop_app/theme.py",
        "desktop_app/main.py",
        "QFont::setPointSize",
        "test_desktop_main_contract.py",
        "CONTRIBUTING.md",
        "--help",
        "python -m probooks",
        "Excel COA workbook",
        "probooks/help_epilog.py",
        "generate_workbook.py",
        "excel-workbook-template-openpyxl",
    ):
        assert needle in section, f"README Desktop section should mention {needle!r}"


def test_readme_links_contributing_continuous_integration_anchor() -> None:
    """README docs bar and Contributing section should deep-link CONTRIBUTING CI + Running Tests."""
    readme = README_MD.read_text(encoding="utf-8")
    assert "[docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)" in readme
    assert "docs/CONTRIBUTING.md#continuous-integration" in readme
    assert "[Running Tests](docs/CONTRIBUTING.md#running-tests)" in readme


def test_readme_links_roadmap_implementation_snapshot() -> None:
    """README docs bar and Issue-driven section should deep-link ROADMAP implementation snapshot."""
    readme = README_MD.read_text(encoding="utf-8")
    needle = "docs/ROADMAP.md#implementation-snapshot-repository-2026-04"
    assert readme.count(needle) >= 2, f"expected at least two {needle!r} links (docs bar + body)"


def test_readme_links_roadmap_supporting_cross_cutting() -> None:
    """README docs bar and Issue-driven section should deep-link ROADMAP Supporting / cross-cutting."""
    readme = README_MD.read_text(encoding="utf-8")
    needle = "docs/ROADMAP.md#supporting-cross-cutting-issues"
    assert readme.count(needle) >= 2, f"expected at least two {needle!r} links (docs bar + body)"


def test_readme_docs_bar_links_issues_backlog_short_index() -> None:
    """README docs bar should link docs/issues-backlog.md (short index)."""
    readme = README_MD.read_text(encoding="utf-8")
    assert "[Short index](docs/issues-backlog.md)" in readme


def test_hub_docs_shared_issues_backlog_blurb_lists_config_and_review_cards() -> None:
    """ROADMAP, BACKLOG, and CONTRIBUTING should share the same issues-backlog.md related-doc blurb."""
    blurb = (
        "[issues-backlog.md](issues-backlog.md) (short index; **config.yml** chooser + "
        "**`review.html`** Issues cards)"
    )
    for rel in ("docs/ROADMAP.md", "docs/BACKLOG.md", "docs/CONTRIBUTING.md"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert blurb in text, f"{rel} should include the shared issues-backlog.md blurb"


def test_readme_docs_bar_links_desktop_app_anchor() -> None:
    """README top **Docs** line should jump to ## Desktop app (PySide6)."""
    readme = README_MD.read_text(encoding="utf-8")
    assert "[Desktop app](#desktop-app-pyside6)" in readme


def test_readme_docs_bar_links_default_database_paths_anchor() -> None:
    """README top **Docs** line should jump to ### Default database paths (Windows)."""
    readme = README_MD.read_text(encoding="utf-8")
    assert "[Default DB paths](#default-database-paths-windows)" in readme


def test_readme_excel_workbook_subsection_links_help_epilog_and_desktop() -> None:
    """README ### Excel workbook template should cross-link help_epilog and Desktop anchor."""
    readme = README_MD.read_text(encoding="utf-8")
    head = "### Excel workbook template (openpyxl)"
    start = readme.index(head)
    rest = readme[start + len(head) :]
    next_h3 = rest.index("\n### ")
    section = rest[:next_h3]
    for needle in (
        "probooks/help_epilog.py",
        "--help",
        "python -m probooks",
        "python -m desktop_app.main",
        "Excel COA workbook",
        "#desktop-app-pyside6",
    ):
        assert needle in section, f"README Excel workbook subsection should mention {needle!r}"


def test_readme_docs_bar_links_excel_workbook_anchor() -> None:
    """README top **Docs** line should jump to ## Excel workbook template (openpyxl)."""
    readme = README_MD.read_text(encoding="utf-8")
    assert "[Excel workbook](#excel-workbook-template-openpyxl)" in readme


def test_readme_docs_bar_links_python_cli_anchor() -> None:
    """README top **Docs** line should jump to ## Python CLI."""
    readme = README_MD.read_text(encoding="utf-8")
    assert "[Python CLI](#python-cli)" in readme


def test_hub_docs_related_docs_link_readme_excel_workbook_template() -> None:
    """ROADMAP, BACKLOG, and CONTRIBUTING should share the same README Excel segment in Related/Other docs."""
    segment = (
        "[README — Excel workbook template](../README.md#excel-workbook-template-openpyxl) "
        "(**generate_workbook.py**, **openpyxl**; CLI/desktop **`--help`**: **`probooks/help_epilog.py`**)"
    )
    for rel in ("docs/ROADMAP.md", "docs/BACKLOG.md", "docs/CONTRIBUTING.md"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert segment in text, f"{rel} should include the shared README Excel workbook segment"


def test_hub_docs_related_docs_link_readme_default_database_paths() -> None:
    """ROADMAP, BACKLOG, and CONTRIBUTING should share the same README default DB segment in Related/Other docs."""
    segment = (
        "[README — Default database paths](../README.md#default-database-paths-windows) "
        "(CLI **`probooks.db`** vs desktop **`probooksai.db`**, **#21**)"
    )
    for rel in ("docs/ROADMAP.md", "docs/BACKLOG.md", "docs/CONTRIBUTING.md"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert segment in text, f"{rel} should include the shared README default database paths segment"


def test_static_html_links_readme_desktop_section() -> None:
    """Static shell pages that mention the desktop app should deep-link README Desktop."""
    needle = 'href="README.md#desktop-app-pyside6"'
    for path in (INDEX_HTML, INVOICE_HTML, REVIEW_HTML):
        text = path.read_text(encoding="utf-8")
        assert needle in text, f"{path.name} should include {needle!r}"


def test_static_html_links_readme_excel_workbook_section() -> None:
    """Static shell pages should deep-link README Excel workbook template where we surface it."""
    needle = 'href="README.md#excel-workbook-template-openpyxl"'
    for path in (INDEX_HTML, INVOICE_HTML, REVIEW_HTML):
        text = path.read_text(encoding="utf-8")
        assert needle in text, f"{path.name} should include {needle!r}"


def test_review_html_links_readme_web_shell_and_desktop_anchors() -> None:
    """review.html Documentation cards should deep-link README Web shell, Desktop, default DB paths, and Excel template."""
    text = REVIEW_HTML.read_text(encoding="utf-8")
    assert 'href="README.md#web-shell-review"' in text
    assert 'href="README.md#desktop-app-pyside6"' in text
    assert 'href="README.md#default-database-paths-windows"' in text
    assert 'href="README.md#excel-workbook-template-openpyxl"' in text


def test_review_html_readme_default_database_paths_documentation_card() -> None:
    """review.html Documentation grid should surface README default DB paths + #21 next to Desktop/Excel cards."""
    text = REVIEW_HTML.read_text(encoding="utf-8")
    start = text.index("<strong>README — Default database paths</strong>")
    end = text.index("</a>", start)
    card = text[start:end]
    assert "probooks.db" in card
    assert "probooksai.db" in card
    assert "#21" in card
    assert "tests/test_issue_21_schema_inventory.py" in card


def test_review_html_readme_excel_documentation_card_mentions_help_epilog() -> None:
    """README — Excel workbook Documentation card should mention help_epilog next to generate_workbook."""
    text = REVIEW_HTML.read_text(encoding="utf-8")
    start = text.index("<strong>README — Excel workbook</strong>")
    end = text.index("</a>", start)
    card = text[start:end]
    assert "generate_workbook.py" in card
    assert "help_epilog" in card
    assert "--help" in card


def test_review_html_python_desktop_section_mentions_help_epilog() -> None:
    """review.html Python + desktop section: help_epilog, CI, Running Tests / sync-workspace."""
    text = REVIEW_HTML.read_text(encoding="utf-8")
    start = text.index('<h2>Python + desktop (SQLite)</h2>')
    end = text.index("</section>", start)
    chunk = text[start:end]
    assert "probooks/help_epilog.py" in chunk
    assert "--help" in chunk
    assert 'href="README.md#default-database-paths-windows"' in chunk
    assert 'href="docs/ROADMAP.md#supporting-cross-cutting-issues"' in chunk
    assert "tests/test_issue_21_schema_inventory.py" in chunk
    assert 'href="docs/CONTRIBUTING.md#continuous-integration"' in chunk
    assert 'href="docs/CONTRIBUTING.md#running-tests"' in chunk
    assert "sync-workspace.ps1" in chunk
    assert "probooks.backup" in chunk
    assert "SQLite online backup" in chunk


def test_static_shell_page_sub_mentions_help_epilog() -> None:
    """index.html and invoice.html README hints mention help_epilog, --help, CI, and Running Tests (work-context)."""
    for path in (INDEX_HTML, INVOICE_HTML):
        text = path.read_text(encoding="utf-8")
        assert "probooks/help_epilog.py" in text, f"{path.name} should mention probooks/help_epilog.py"
        assert "--help" in text, f"{path.name} should mention --help"
        assert 'href="README.md#default-database-paths-windows"' in text, (
            f"{path.name} should deep-link README default database paths"
        )
        assert "tests/test_issue_21_schema_inventory.py" in text, (
            f"{path.name} should mention DDL inventory tests (issue #21)"
        )
        assert 'href="docs/CONTRIBUTING.md#continuous-integration"' in text, (
            f"{path.name} should link CONTRIBUTING CI (SQLite issue #21 bullet)"
        )
        assert 'href="docs/CONTRIBUTING.md#running-tests"' in text, (
            f"{path.name} should link CONTRIBUTING Running Tests (work-context / sync-workspace)"
        )
        assert "sync-workspace.ps1" in text, (
            f"{path.name} should mention sync-workspace.ps1 in Running Tests hint"
        )
        assert "probooks.backup" in text, f"{path.name} should mention probooks.backup (SQLite online backup)"
        assert "SQLite online backup" in text, f"{path.name} should mention SQLite online backup"


def test_review_html_links_contributing_doc_anchors() -> None:
    """review.html Documentation section should link CONTRIBUTING Running Tests + Continuous integration."""
    text = REVIEW_HTML.read_text(encoding="utf-8")
    assert 'href="docs/CONTRIBUTING.md#running-tests"' in text
    assert 'href="docs/CONTRIBUTING.md#continuous-integration"' in text
    assert "blob/main/docs/CONTRIBUTING.md#running-tests" in text
    assert "blob/main/docs/CONTRIBUTING.md#continuous-integration" in text


def test_review_html_issues_backlog_card_mentions_issue_chooser_config() -> None:
    """review.html issues-backlog cards (local + GitHub blob) should name the same config path as docs/issues-backlog.md."""
    text = REVIEW_HTML.read_text(encoding="utf-8")
    assert 'href="docs/issues-backlog.md"' in text
    assert "blob/main/docs/issues-backlog.md" in text
    assert text.count("ROADMAP snapshot + Supporting / cross-cutting") >= 2, (
        "review.html local + GitHub issues-backlog cards should echo config.yml Doc index ROADMAP wording"
    )
    path = ".github/ISSUE_TEMPLATE/config.yml"
    assert text.count(path) >= 2, f"review.html should mention {path!r} on both issues-backlog Documentation cards"


def test_readme_scripts_mention_work_context_example_json() -> None:
    """README Scripts section should point at work-context.example.json vs generated JSON."""
    readme = README_MD.read_text(encoding="utf-8")
    assert "integrations/work-context.example.json" in readme
    assert "sync-workspace.ps1" in readme
    sync = readme.index("**`sync-workspace.ps1`**")
    sync_line = readme[sync : readme.find("\n", sync)]
    for needle in (
        "index.html",
        "invoice.html",
        "review.html",
        "docs/ROADMAP.md",
        "test_integrations_example_contract.py",
    ):
        assert needle in sync_line, f"sync-workspace README bullet should mention {needle!r}"


def test_readme_ci_validate_layout_bullet_mentions_conftest() -> None:
    """README Scripts section should name tests/conftest.py next to layout validators (PR template parity)."""
    readme = README_MD.read_text(encoding="utf-8")
    head = "## Scripts (`scripts/`)"
    start = readme.index(head)
    chunk = readme[start : readme.index("\n## ", start + 1)]
    assert "ci_validate_layout.sh" in chunk and "ci_validate_layout.ps1" in chunk
    assert "tests/conftest.py" in chunk
    assert "**`.gitattributes`**" in chunk, (
        "README Scripts ci_validate_layout bullet should mention .gitattributes (layout require + LF policy)"
    )


def test_layout_validator_windows_bash_path_guidance_in_hub_ci_scripts_and_cursor_rule() -> None:
    """Keep README, CONTRIBUTING, ci.yml comments, script headers, and .mdc aligned on Windows bash PATH vs .ps1."""
    readme = README_MD.read_text(encoding="utf-8")
    scripts_start = readme.index("## Scripts (`scripts/`)")
    scripts_chunk = readme[scripts_start : readme.index("\n## ", scripts_start + 1)]
    assert "PATH" in scripts_chunk
    assert "bash" in scripts_chunk.lower()
    assert "ci_validate_layout.ps1" in scripts_chunk

    md = DOCS_CONTRIBUTING_MD.read_text(encoding="utf-8")
    ci_start = md.index("### Continuous integration")
    table_start = md.index("| **`test_pyproject_contract.py`**", ci_start)
    ci_pre_table = md[ci_start:table_start]
    yml_bullet = next(
        ln
        for ln in ci_pre_table.splitlines()
        if ln.strip().startswith("- **`.github/workflows/ci.yml`**")
    )
    assert "PATH" in yml_bullet and "README" in yml_bullet and "Scripts" in yml_bullet

    yml = GITHUB_WORKFLOW_CI_YML.read_text(encoding="utf-8")
    assert "bash" in yml.lower()
    assert "PowerShell" in yml or "powershell" in yml.lower()

    sh_top = "\n".join(_SH.read_text(encoding="utf-8").splitlines()[:6])
    ps1_top = "\n".join(_PS1.read_text(encoding="utf-8").splitlines()[:6])
    assert "PATH" in sh_top
    assert "PATH" in ps1_top

    mdc = CURSOR_RULE_GITHUB_WORK_CONTEXT_MDC.read_text(encoding="utf-8")
    layout_lines = [ln for ln in mdc.splitlines() if ln.startswith("**Layout validators:**")]
    assert len(layout_lines) == 1
    layout_para = layout_lines[0]
    assert "PATH" in layout_para
    assert "Git Bash" in layout_para


def test_readme_contributing_section_mentions_conftest() -> None:
    """README ## Contributing should point at tests/conftest.py and Scripts layout validators."""
    readme = README_MD.read_text(encoding="utf-8")
    start = readme.index("## Contributing")
    chunk = readme[start:]
    assert "contract-test" in chunk
    assert "tests/conftest.py" in chunk
    assert "ci_validate_layout.sh" in chunk and "ci_validate_layout.ps1" in chunk
    assert "Scripts" in chunk and "scripts/" in chunk


def test_contributing_ci_documents_work_context_example_touchpoints() -> None:
    """Continuous integration section should list where work-context.example.json must stay in sync."""
    md = DOCS_CONTRIBUTING_MD.read_text(encoding="utf-8")
    assert "### Continuous integration" in md
    ci_start = md.index("### Continuous integration")
    table_start = md.index("| **`test_pyproject_contract.py`**", ci_start)
    ci_chunk = md[ci_start:table_start]
    assert "**`integrations/work-context.example.json`**" in ci_chunk
    assert "test_integrations_example_contract.py" in ci_chunk
    assert "github-work-context.mdc" in ci_chunk


def test_contributing_ci_documents_contributing_md_anchor_touchpoints() -> None:
    """Continuous integration section documents CONTRIBUTING.md fragment sync + review.html tests."""
    md = DOCS_CONTRIBUTING_MD.read_text(encoding="utf-8")
    ci_start = md.index("### Continuous integration")
    table_start = md.index("| **`test_pyproject_contract.py`**", ci_start)
    ci_chunk = md[ci_start:table_start]
    assert "**CONTRIBUTING.md anchors (`#running-tests`, `#continuous-integration`)**" in ci_chunk
    assert "test_review_html_links_contributing_doc_anchors" in ci_chunk


def test_contributing_ci_documents_issues_backlog_review_config_touchpoints() -> None:
    """Continuous integration section lists tests for issues-backlog.md vs review.html vs config.yml."""
    md = DOCS_CONTRIBUTING_MD.read_text(encoding="utf-8")
    ci_start = md.index("### Continuous integration")
    table_start = md.index("| **`test_pyproject_contract.py`**", ci_start)
    ci_chunk = md[ci_start:table_start]
    assert "**issues-backlog + GitHub chooser**" in ci_chunk
    ib_start = ci_chunk.index("**issues-backlog + GitHub chooser**")
    ib_end = ci_chunk.index("\n- **Hub docs — issues-backlog link text**", ib_start)
    ibullet = ci_chunk[ib_start:ib_end]
    assert "the following paragraph ties **Doc index (issues-backlog)** **`about`**" in ibullet
    assert "another paragraph notes **ROADMAP** / **BACKLOG** / **Other docs** hub blurb parity" in ibullet
    assert "another orienting paragraph notes the shared **README — Default database paths** hub segment" in ibullet
    assert "Issues backlog Documentation cards" in ibullet
    assert "blob/.../issues-backlog.md" in ibullet
    for name in (
        "test_issues_backlog_orients_readme_docs_bar_and_github_config",
        "test_review_html_issues_backlog_card_mentions_issue_chooser_config",
        "test_issues_backlog_documents_excel_help_epilog",
        "test_hub_docs_related_docs_link_readme_default_database_paths",
        "test_contributing_ci_documents_hub_readme_default_database_paths_segment",
        "test_pr_template_lists_hub_docs_readme_default_database_paths_checklist",
    ):
        assert name in ibullet, f"issues-backlog + GitHub chooser bullet should mention {name!r}"
    assert "**`PULL_REQUEST_TEMPLATE.md`**" in ibullet
    assert "test_pr_template_issues_backlog_checklist_cites_layout_sync_tests" in ibullet
    assert "test_contributing_ci_documents_issues_backlog_review_config_touchpoints" in ibullet
    assert "test_contributing_ci_documents_config_doc_index_about_review_hub" in ibullet
    assert "**Doc index (issues-backlog)** **`about`** ↔ **ISSUE_TEMPLATE** bullet" in ibullet


def test_contributing_ci_documents_hub_shared_issues_backlog_blurb() -> None:
    """Continuous integration section documents the ROADMAP/BACKLOG/CONTRIBUTING issues-backlog blurb test."""
    md = DOCS_CONTRIBUTING_MD.read_text(encoding="utf-8")
    ci_start = md.index("### Continuous integration")
    table_start = md.index("| **`test_pyproject_contract.py`**", ci_start)
    ci_chunk = md[ci_start:table_start]
    assert "**Hub docs — issues-backlog link text**" in ci_chunk
    hub = ci_chunk.index("**Hub docs — issues-backlog link text**")
    hub_end = ci_chunk.index("\n- **Hub docs — README default database paths segment**", hub)
    hub_bullet = ci_chunk[hub:hub_end]
    assert "test_hub_docs_shared_issues_backlog_blurb_lists_config_and_review_cards" in hub_bullet
    assert "test_contributing_ci_documents_hub_shared_issues_backlog_blurb" in hub_bullet
    assert "test_pr_template_lists_hub_docs_issues_backlog_blurb_checklist" in hub_bullet


def test_contributing_ci_documents_hub_readme_default_database_paths_segment() -> None:
    """Continuous integration section documents the ROADMAP/BACKLOG/CONTRIBUTING README default DB hub segment test."""
    md = DOCS_CONTRIBUTING_MD.read_text(encoding="utf-8")
    ci_start = md.index("### Continuous integration")
    table_start = md.index("| **`test_pyproject_contract.py`**", ci_start)
    ci_chunk = md[ci_start:table_start]
    assert "**Hub docs — README default database paths segment**" in ci_chunk
    hub = ci_chunk.index("**Hub docs — README default database paths segment**")
    hub_end = ci_chunk.index("\n- **ROADMAP snapshot anchor**", hub)
    hub_bullet = ci_chunk[hub:hub_end]
    assert "test_hub_docs_related_docs_link_readme_default_database_paths" in hub_bullet
    assert "test_contributing_ci_documents_hub_readme_default_database_paths_segment" in hub_bullet
    assert "test_pr_template_lists_hub_docs_readme_default_database_paths_checklist" in hub_bullet


def test_pr_template_lists_hub_docs_issues_backlog_blurb_checklist() -> None:
    """PR template should remind editors to sync ROADMAP/BACKLOG/CONTRIBUTING issues-backlog blurb + tests."""
    text = GITHUB_PULL_REQUEST_TEMPLATE_MD.read_text(encoding="utf-8")
    assert "Hub docs — issues-backlog link text" in text
    for name in (
        "test_hub_docs_shared_issues_backlog_blurb_lists_config_and_review_cards",
        "test_contributing_ci_documents_hub_shared_issues_backlog_blurb",
        "test_pr_template_lists_hub_docs_issues_backlog_blurb_checklist",
    ):
        assert name in text, f"PULL_REQUEST_TEMPLATE.md should mention {name!r}"


def test_pr_template_lists_hub_docs_readme_default_database_paths_checklist() -> None:
    """PR template should remind editors to sync ROADMAP/BACKLOG/CONTRIBUTING README default DB hub segment + tests."""
    text = GITHUB_PULL_REQUEST_TEMPLATE_MD.read_text(encoding="utf-8")
    assert "Hub docs — README default database paths segment" in text
    for name in (
        "test_hub_docs_related_docs_link_readme_default_database_paths",
        "test_contributing_ci_documents_hub_readme_default_database_paths_segment",
        "test_pr_template_lists_hub_docs_readme_default_database_paths_checklist",
    ):
        assert name in text, f"PULL_REQUEST_TEMPLATE.md should mention {name!r}"


def test_pr_template_lists_readme_excel_workbook_anchor_checklist() -> None:
    """PR template should remind editors to sync README Excel workbook template anchor + tests."""
    text = GITHUB_PULL_REQUEST_TEMPLATE_MD.read_text(encoding="utf-8")
    assert "excel-workbook-template-openpyxl" in text
    assert "### Excel workbook template (openpyxl)" in text
    assert "**README Excel workbook template anchor**" in text
    assert "**Python + desktop** paragraph" in text
    assert "**`config.yml`**" in text
    assert "issues-backlog.md" in text
    for name in (
        "test_github_issue_templates_reference_core_docs",
        "test_review_html_links_readme_web_shell_and_desktop_anchors",
        "test_static_html_links_readme_excel_workbook_section",
        "test_pr_template_lists_readme_excel_workbook_anchor_checklist",
        "test_contributing_ci_documents_readme_excel_workbook_anchor_bullet",
        "test_hub_docs_related_docs_link_readme_excel_workbook_template",
        "test_readme_docs_bar_links_excel_workbook_anchor",
        "test_review_html_python_desktop_section_mentions_help_epilog",
        "test_static_shell_page_sub_mentions_help_epilog",
        "test_readme_excel_workbook_subsection_links_help_epilog_and_desktop",
        "test_review_html_readme_excel_documentation_card_mentions_help_epilog",
    ):
        assert name in text, f"PULL_REQUEST_TEMPLATE.md should mention {name!r}"


def test_pr_template_readme_desktop_anchor_checklist_cites_help_epilog_tests() -> None:
    """PR template Desktop anchor row should cite help_epilog-related layout tests."""
    text = GITHUB_PULL_REQUEST_TEMPLATE_MD.read_text(encoding="utf-8")
    assert "`## Desktop app (PySide6)`** was renamed" in text
    for name in (
        "test_review_html_python_desktop_section_mentions_help_epilog",
        "test_static_shell_page_sub_mentions_help_epilog",
    ):
        assert name in text, f"PULL_REQUEST_TEMPLATE.md should mention {name!r}"


def test_pr_template_lists_readme_default_database_paths_checklist() -> None:
    """PR template should remind editors to sync README default DB paths + ROADMAP #21 note + tests."""
    text = GITHUB_PULL_REQUEST_TEMPLATE_MD.read_text(encoding="utf-8")
    assert "### Default database paths (Windows)" in text
    assert "**README `### Default database paths (Windows)`**" in text
    assert "**`index.html`** / **`invoice.html`** README hints" in text
    for name in (
        "test_readme_default_database_paths_notes_two_schemas_and_roadmap",
        "test_roadmap_snapshot_why_not_one_db_points_at_issue_21_inventory",
        "test_readme_docs_bar_links_default_database_paths_anchor",
        "test_review_html_links_readme_web_shell_and_desktop_anchors",
        "test_review_html_readme_default_database_paths_documentation_card",
        "test_review_html_python_desktop_section_mentions_help_epilog",
        "test_static_shell_page_sub_mentions_help_epilog",
        "test_pr_template_lists_readme_default_database_paths_checklist",
        "test_contributing_ci_documents_readme_default_database_paths_bullet",
        "test_hub_docs_related_docs_link_readme_default_database_paths",
        "test_contributing_ci_documents_hub_readme_default_database_paths_segment",
        "test_pr_template_lists_hub_docs_readme_default_database_paths_checklist",
        "test_pr_template_lists_issue_21_schema_inventory_checklist",
    ):
        assert name in text, f"PULL_REQUEST_TEMPLATE.md should mention {name!r}"


def test_pr_template_lists_issue_21_schema_inventory_checklist() -> None:
    """PR template should remind editors to sync test_issue_21_schema_inventory when DDL changes."""
    text = GITHUB_PULL_REQUEST_TEMPLATE_MD.read_text(encoding="utf-8")
    assert "**`probooks/migrations/*.sql`**" in text
    assert "**`probooksai/bank_import.py`**" in text
    assert "**`SCHEMA_VERSION`**" in text
    assert "**`_MIGRATIONS`**" in text
    assert "**`tests/test_issue_21_schema_inventory.py`**" in text
    assert "**SQLite issue #21**" in text
    assert "column inventory frozensets" in text
    assert "**`pytest tests/test_issue_21_schema_inventory.py`**" in text
    assert "test_pr_template_lists_issue_21_schema_inventory_checklist" in text


def test_contributing_ci_documents_readme_default_database_paths_bullet() -> None:
    """Continuous integration section documents README default database paths + layout tests."""
    md = DOCS_CONTRIBUTING_MD.read_text(encoding="utf-8")
    ci_start = md.index("### Continuous integration")
    table_start = md.index("| **`test_pyproject_contract.py`**", ci_start)
    chunk = md[ci_start:table_start]
    assert "**README `### Default database paths (Windows)`**" in chunk
    assert "Why not one `.db` yet" in chunk
    assert "**Hub docs — README default database paths segment**" in chunk
    assert "**`index.html`** / **`invoice.html`** README hints" in chunk
    for name in (
        "test_readme_default_database_paths_notes_two_schemas_and_roadmap",
        "test_roadmap_snapshot_why_not_one_db_points_at_issue_21_inventory",
        "test_readme_docs_bar_links_default_database_paths_anchor",
        "test_review_html_links_readme_web_shell_and_desktop_anchors",
        "test_review_html_readme_default_database_paths_documentation_card",
        "test_review_html_python_desktop_section_mentions_help_epilog",
        "test_static_shell_page_sub_mentions_help_epilog",
        "test_pr_template_lists_readme_default_database_paths_checklist",
        "test_contributing_ci_documents_readme_default_database_paths_bullet",
        "test_hub_docs_related_docs_link_readme_default_database_paths",
        "test_contributing_ci_documents_hub_readme_default_database_paths_segment",
        "test_pr_template_lists_hub_docs_readme_default_database_paths_checklist",
    ):
        assert name in chunk, f"CONTRIBUTING CI should mention {name!r} on default DB paths bullet"


def test_contributing_ci_documents_issue_21_schema_inventory_bullet() -> None:
    """Continuous integration section documents SQLite issue #21 schema inventory tests."""
    md = DOCS_CONTRIBUTING_MD.read_text(encoding="utf-8")
    ci_start = md.index("### Continuous integration")
    table_start = md.index("| **`test_pyproject_contract.py`**", ci_start)
    chunk = md[ci_start:table_start]
    assert "**SQLite issue #21 (CLI vs desktop bank DDL)**" in chunk
    assert "**`tests/test_issue_21_schema_inventory.py`**" in chunk
    assert "**`_CLI_BANK_TABLES`**" in chunk
    assert "**`_DESKTOP_BANK_CORE_TABLES`**" in chunk
    assert "**`_CLI_*_COLUMNS`**" in chunk
    assert "**`_SHARED_*_COLUMN_NAMES`**" in chunk
    for name in (
        "test_cli_migrations_user_tables_match_expected",
        "test_desktop_bank_database_user_tables_match_expected",
        "test_cli_and_desktop_bank_share_only_expected_table_names",
        "test_issue_21_bank_table_columns_match_inventory",
        "test_contributing_ci_documents_issue_21_schema_inventory_bullet",
        "test_pr_template_lists_issue_21_schema_inventory_checklist",
    ):
        assert name in chunk, f"CONTRIBUTING CI should mention {name!r} on SQLite issue #21 bullet"


def test_contributing_ci_documents_readme_excel_workbook_anchor_bullet() -> None:
    """Continuous integration section documents the README Excel workbook template anchor + tests."""
    md = DOCS_CONTRIBUTING_MD.read_text(encoding="utf-8")
    ci_start = md.index("### Continuous integration")
    table_start = md.index("| **`test_pyproject_contract.py`**", ci_start)
    chunk = md[ci_start:table_start]
    assert "**README `### Excel workbook template (openpyxl)` anchor**" in chunk
    assert "README.md#excel-workbook-template-openpyxl" in chunk
    assert "**`config.yml`** (**Excel workbook template** contact link)" in chunk
    assert "**ROADMAP** / **BACKLOG** **Related docs**" in chunk
    assert "**README** top **Docs** line" in chunk
    assert "**`index.html`** / **`invoice.html`** (README hints)" in chunk
    assert "**Python + desktop** paragraph" in chunk
    assert "test_static_html_links_readme_excel_workbook_section" in chunk
    assert "test_pr_template_lists_readme_excel_workbook_anchor_checklist" in chunk
    assert "test_contributing_ci_documents_readme_excel_workbook_anchor_bullet" in chunk
    assert "test_hub_docs_related_docs_link_readme_excel_workbook_template" in chunk
    assert "test_readme_docs_bar_links_excel_workbook_anchor" in chunk
    assert "test_review_html_python_desktop_section_mentions_help_epilog" in chunk
    assert "test_static_shell_page_sub_mentions_help_epilog" in chunk
    assert "test_readme_excel_workbook_subsection_links_help_epilog_and_desktop" in chunk
    assert "test_review_html_readme_excel_documentation_card_mentions_help_epilog" in chunk


def test_contributing_ci_documents_readme_python_cli_anchor_bullet() -> None:
    """Continuous integration section documents the README ## Python CLI anchor + layout tests."""
    md = DOCS_CONTRIBUTING_MD.read_text(encoding="utf-8")
    ci_start = md.index("### Continuous integration")
    table_start = md.index("| **`test_pyproject_contract.py`**", ci_start)
    chunk = md[ci_start:table_start]
    start = chunk.index("**README `## Python CLI` anchor**")
    end = chunk.index("\n- **README `## Desktop app (PySide6)` anchor**", start)
    bullet = chunk[start:end]
    assert "#python-cli" in bullet
    assert "../README.md#python-cli" in bullet
    for name in (
        "test_readme_docs_bar_links_python_cli_anchor",
        "test_readme_python_cli_section_mentions_backup_restore_online_api",
        "test_issues_backlog_documents_excel_help_epilog",
        "test_pr_template_lists_readme_python_cli_anchor_checklist",
        "test_contributing_ci_documents_readme_python_cli_anchor_bullet",
    ):
        assert name in bullet, f"CONTRIBUTING Python CLI anchor bullet should mention {name!r}"


def test_contributing_ci_documents_readme_desktop_help_epilog_layout_tests() -> None:
    """Continuous integration README Desktop bullet lists layout tests for help_epilog hub copy."""
    md = DOCS_CONTRIBUTING_MD.read_text(encoding="utf-8")
    ci_start = md.index("### Continuous integration")
    table_start = md.index("| **`test_pyproject_contract.py`**", ci_start)
    chunk = md[ci_start:table_start]
    desk = chunk.index("**README `## Desktop app (PySide6)` anchor**")
    nxt = chunk.index("\n- **README `### Excel workbook", desk)
    bullet = chunk[desk:nxt]
    for name in (
        "test_review_html_python_desktop_section_mentions_help_epilog",
        "test_static_shell_page_sub_mentions_help_epilog",
    ):
        assert name in bullet, f"CONTRIBUTING Desktop anchor bullet should mention {name!r}"


def test_pr_template_issues_backlog_checklist_cites_layout_sync_tests() -> None:
    """PR template row for issues-backlog vs config.yml should list the layout-sync pytest names."""
    text = GITHUB_PULL_REQUEST_TEMPLATE_MD.read_text(encoding="utf-8")
    assert "docs/issues-backlog.md" in text
    assert "orienting paragraphs" in text
    assert "Canonical ordering" in text
    assert "contact_links" in text
    assert "Issues backlog Documentation cards" in text
    assert "issues-backlog + GitHub chooser" in text
    for name in (
        "test_issues_backlog_orients_readme_docs_bar_and_github_config",
        "test_issues_backlog_documents_excel_help_epilog",
        "test_contributing_ci_documents_issues_backlog_review_config_touchpoints",
        "test_github_issue_templates_reference_core_docs",
        "test_review_html_issues_backlog_card_mentions_issue_chooser_config",
        "test_contributing_ci_documents_config_doc_index_about_review_hub",
        "test_hub_docs_related_docs_link_readme_default_database_paths",
        "test_contributing_ci_documents_hub_readme_default_database_paths_segment",
        "test_pr_template_lists_hub_docs_readme_default_database_paths_checklist",
    ):
        assert name in text, f"PULL_REQUEST_TEMPLATE.md should mention {name!r}"
    assert "**Doc index (issues-backlog)** **`about`**" in text


def test_contributing_running_tests_mentions_work_context_example() -> None:
    """Running Tests section should point contributors at work-context example + sync script."""
    md = DOCS_CONTRIBUTING_MD.read_text(encoding="utf-8")
    chunk = md.split("## Running Tests", 1)[1].split("### Continuous integration", 1)[0]
    assert "integrations/work-context.example.json" in chunk
    assert "sync-workspace.ps1" in chunk
    for needle in (
        "index.html",
        "invoice.html",
        "review.html",
        "docs/ROADMAP.md",
        "test_integrations_example_contract.py",
    ):
        assert needle in chunk, f"Running Tests work-context paragraph should mention {needle!r}"


def test_contributing_other_docs_links_readme_contributing_section() -> None:
    """CONTRIBUTING intro should deep-link README ## Contributing (parity with docs bar)."""
    md = DOCS_CONTRIBUTING_MD.read_text(encoding="utf-8")
    assert "../README.md#contributing" in md


def test_contributing_intro_self_links_continuous_integration_and_running_tests() -> None:
    """CONTRIBUTING Other docs line should jump to CI + Running Tests on this page."""
    md = DOCS_CONTRIBUTING_MD.read_text(encoding="utf-8")
    intro = md.split("## Naming Conventions", 1)[0]
    assert "[Continuous integration](#continuous-integration)" in intro
    assert "[Running Tests](#running-tests)" in intro


def test_contributing_other_docs_links_roadmap_implementation_snapshot() -> None:
    """CONTRIBUTING should deep-link ROADMAP implementation snapshot (same anchor as BACKLOG / issues-backlog)."""
    md = DOCS_CONTRIBUTING_MD.read_text(encoding="utf-8")
    assert "ROADMAP.md#implementation-snapshot-repository-2026-04" in md


def test_contributing_other_docs_links_roadmap_supporting_cross_cutting() -> None:
    """CONTRIBUTING Other docs should deep-link ROADMAP Supporting / cross-cutting fragment."""
    md = DOCS_CONTRIBUTING_MD.read_text(encoding="utf-8")
    assert "](ROADMAP.md#supporting-cross-cutting-issues)" in md


def test_contributing_other_docs_links_issues_backlog_short_index() -> None:
    """CONTRIBUTING intro should link the minimal issues-backlog index."""
    md = DOCS_CONTRIBUTING_MD.read_text(encoding="utf-8")
    assert "](issues-backlog.md)" in md


def test_hub_markdown_avoids_unicode_apostrophe_u2019() -> None:
    """Hub docs use ASCII apostrophe (') in contractions; avoid U+2019 (copy/paste from word processors)."""
    for rel in (
        "README.md",
        "docs/CONTRIBUTING.md",
        "docs/ROADMAP.md",
        "docs/BACKLOG.md",
        "docs/issues-backlog.md",
    ):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "\u2019" not in text, f"{rel} must not contain U+2019; use ASCII ' instead"


def test_contributing_ci_documents_hub_markdown_u2019_bullet() -> None:
    """Continuous integration section documents the hub Markdown U+2019 contract test."""
    md = DOCS_CONTRIBUTING_MD.read_text(encoding="utf-8")
    ci_start = md.index("### Continuous integration")
    table_start = md.index("| **`test_pyproject_contract.py`**", ci_start)
    chunk = md[ci_start:table_start]
    assert "**Markdown (hub files)**" in chunk
    assert "test_hub_markdown_avoids_unicode_apostrophe_u2019" in chunk
    assert "test_contributing_ci_documents_hub_markdown_u2019_bullet" in chunk
    assert "test_pr_template_lists_hub_markdown_u2019_checklist" in chunk


def test_pr_template_lists_hub_markdown_u2019_checklist() -> None:
    """PR template should remind editors about ASCII apostrophes in hub Markdown."""
    text = GITHUB_PULL_REQUEST_TEMPLATE_MD.read_text(encoding="utf-8")
    assert "**Markdown (hub files)**" in text
    assert "U+2019" in text
    for name in (
        "test_hub_markdown_avoids_unicode_apostrophe_u2019",
        "test_contributing_ci_documents_hub_markdown_u2019_bullet",
        "test_pr_template_lists_hub_markdown_u2019_checklist",
    ):
        assert name in text, f"PULL_REQUEST_TEMPLATE.md should mention {name!r}"


def test_github_issue_templates_reference_core_docs() -> None:
    """Issue chooser + forms stay aligned with ROADMAP, BACKLOG, README web shell + Desktop + Excel template, CONTRIBUTING naming."""
    naming = "docs/CONTRIBUTING.md#naming-conventions"
    config = GITHUB_ISSUE_TEMPLATE_CONFIG_YML.read_text(encoding="utf-8")
    assert naming in config, "config.yml Contributing guide URL should include CONTRIBUTING.md#naming-conventions"
    assert "CONTRIBUTING.md#running-tests" in config, (
        "config.yml should include Running Tests contact link to CONTRIBUTING.md#running-tests"
    )
    assert "name: Continuous integration" in config, (
        "config.yml should define a Continuous integration contact link"
    )
    assert "name: Local preview (review.html)" in config, (
        "config.yml should keep the Local preview contact label (review.html)"
    )
    assert "name: Running Tests (work-context)" in config, (
        "config.yml should keep the Running Tests contact label (work-context)"
    )
    assert "name: Doc index (issues-backlog)" in config, (
        "config.yml should keep the Doc index contact label (issues-backlog)"
    )
    assert (
        "review.html Issues backlog Documentation cards (local + GitHub blob) echo that ROADMAP snapshot + Supporting / cross-cutting blurb and name .github/ISSUE_TEMPLATE/config.yml"
        in config
    ), (
        "config.yml Doc index about should tie review.html Issues backlog Documentation cards to blurb + config.yml"
    )
    assert "repeat the same issues-backlog.md hub blurb" in config, (
        "config.yml Doc index about should note ROADMAP/BACKLOG/CONTRIBUTING hub blurb parity"
    )
    assert config.count("CONTRIBUTING.md#continuous-integration") >= 1, (
        "config.yml should include Continuous integration contact link to CONTRIBUTING.md#continuous-integration"
    )
    assert "README.md#web-shell-review" in config, (
        "config.yml should include Local preview contact link to README.md#web-shell-review"
    )
    assert "README.md#desktop-app-pyside6" in config, (
        "config.yml should include Desktop app contact link to README.md#desktop-app-pyside6"
    )
    assert "name: Default database paths (Windows)" in config, (
        "config.yml should define Default database paths contact label"
    )
    assert "README.md#default-database-paths-windows" in config, (
        "config.yml should include Default database paths contact URL"
    )
    db_paths_start = config.index("name: Default database paths (Windows)")
    db_paths_end = config.index("name: Excel workbook template (openpyxl)", db_paths_start)
    db_paths_block = config[db_paths_start:db_paths_end]
    assert "DDL inventory" in db_paths_block, (
        "config.yml Default database paths about should name DDL inventory (hub parity with static shells)"
    )
    assert "tests/test_issue_21_schema_inventory.py" in db_paths_block, (
        "config.yml Default database paths about should mention the schema inventory test module"
    )
    assert "CONTRIBUTING.md#continuous-integration SQLite issue #21 bullet" in db_paths_block, (
        "config.yml Default database paths about should point at CONTRIBUTING SQLite issue #21 bullet"
    )
    assert "name: Excel workbook template (openpyxl)" in config, (
        "config.yml should define Excel workbook template contact label"
    )
    assert "README.md#excel-workbook-template-openpyxl" in config, (
        "config.yml should include Excel workbook template contact URL to README.md#excel-workbook-template-openpyxl"
    )
    ex_start = config.index("name: Excel workbook template (openpyxl)")
    ex_end = config.index("name: Running Tests (work-context)", ex_start)
    assert "help_epilog" in config[ex_start:ex_end], (
        "config.yml Excel workbook template about should mention help_epilog (chooser parity)"
    )
    assert "README Web shell + Desktop + Default database paths + Excel workbook template" in config, (
        "config.yml Doc index about should list Default database paths with Web shell + Desktop + Excel"
    )
    assert "README Python CLI (probooks.backup backup/restore)" in config, (
        "config.yml Doc index about should mention README Python CLI + probooks.backup (issues-backlog parity)"
    )
    assert "SQLite online backup via probooks.backup" in config, (
        "config.yml Doc index about should note SQLite online backup (issues-backlog parity)"
    )
    assert "help_epilog" in config, (
        "config.yml Doc index about should note help_epilog / CLI desktop --help (issues-backlog parity)"
    )
    assert "docs/issues-backlog.md" in config, (
        "config.yml should include Doc index contact link to docs/issues-backlog.md"
    )
    assert "ROADMAP snapshot + Supporting / cross-cutting" in config, (
        "config.yml Doc index about should note ROADMAP Supporting / cross-cutting (issues-backlog parity)"
    )
    bug = GITHUB_ISSUE_TEMPLATE_BUG_REPORT_MD.read_text(encoding="utf-8")
    feat = GITHUB_ISSUE_TEMPLATE_FEATURE_REQUEST_MD.read_text(encoding="utf-8")
    roadmap_snap = "ROADMAP.md#implementation-snapshot-repository-2026-04"
    roadmap_supporting = "docs/ROADMAP.md#supporting-cross-cutting-issues"
    readme_shell = "README.md#web-shell-review"
    readme_python_cli = "README.md#python-cli"
    readme_desktop = "README.md#desktop-app-pyside6"
    readme_excel = "README.md#excel-workbook-template-openpyxl"
    readme_dbpaths = "README.md#default-database-paths-windows"
    contrib_rt = "docs/CONTRIBUTING.md#running-tests"
    web_i = bug.index(readme_shell)
    cli_i = bug.index(readme_python_cli)
    desk_i = bug.index(readme_desktop)
    dbp_i = bug.index(readme_dbpaths)
    xls_i = bug.index(readme_excel)
    assert web_i < cli_i < desk_i < dbp_i < xls_i, (
        "bug_report.md triaging line should list README Web shell, Python CLI, Desktop, Default database paths, "
        "then Excel (same order as ROADMAP/BACKLOG/CONTRIBUTING Related docs)"
    )
    assert bug.index(roadmap_snap) < bug.index(roadmap_supporting), (
        "bug_report.md triaging line should list ROADMAP implementation snapshot before Supporting / cross-cutting"
    )
    assert feat.index(roadmap_snap) < feat.index(roadmap_supporting), (
        "feature_request.md should list ROADMAP implementation snapshot before Supporting / cross-cutting"
    )
    for label, text in (("bug_report.md", bug), ("feature_request.md", feat)):
        assert naming in text, f"{label} should link CONTRIBUTING.md#naming-conventions"
        assert contrib_rt in text, f"{label} should deep-link CONTRIBUTING Running Tests"
        assert roadmap_snap in text, f"{label} should deep-link ROADMAP implementation snapshot"
        assert roadmap_supporting in text, f"{label} should deep-link ROADMAP Supporting / cross-cutting"
        assert readme_shell in text, f"{label} should deep-link README Web shell (review)"
        assert readme_python_cli in text, f"{label} should deep-link README Python CLI"
        assert readme_desktop in text, f"{label} should deep-link README Desktop app (PySide6)"
        assert readme_excel in text, f"{label} should deep-link README Excel workbook template"
        assert readme_dbpaths in text, f"{label} should deep-link README default database paths"
        assert "help_epilog" in text, f"{label} should mention help_epilog with Excel workbook template"
        assert "docs/BACKLOG.md" in text, f"{label} should link BACKLOG.md"
        assert "docs/issues-backlog.md" in text, f"{label} should link issues-backlog.md"


def test_contributing_ci_documents_config_doc_index_about_review_hub() -> None:
    """ISSUE_TEMPLATE CI bullet should note Doc index about ↔ review.html, config.yml, hub blurb."""
    md = DOCS_CONTRIBUTING_MD.read_text(encoding="utf-8")
    ci_start = md.index("### Continuous integration")
    table_start = md.index("| **`test_pyproject_contract.py`**", ci_start)
    chunk = md[ci_start:table_start]
    assert "**Doc index (issues-backlog)** **`about`**" in chunk
    iss = chunk.index("**`.github/ISSUE_TEMPLATE/`**")
    nxt = chunk.index("\n- **ROADMAP snapshot", iss)
    issue_bullet = chunk[iss:nxt]
    assert "**Doc index (issues-backlog)** **`about`** text notes" in issue_bullet
    assert "shared **issues-backlog.md** hub blurb" in issue_bullet
    assert "test_github_issue_templates_reference_core_docs" in issue_bullet
    assert "test_contributing_ci_documents_config_doc_index_about_review_hub" in issue_bullet
    assert "**Triaging** lists **ROADMAP** implementation snapshot then **Supporting / cross-cutting**" in issue_bullet


def test_docs_indexes_link_contributing_ci_section() -> None:
    """ROADMAP, BACKLOG, and issues-backlog index should deep-link CONTRIBUTING CI (contract table)."""
    needle = "CONTRIBUTING.md#continuous-integration"
    for rel in ("docs/ROADMAP.md", "docs/BACKLOG.md", "docs/issues-backlog.md"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert needle in text, f"{rel} should contain {needle!r}"


def test_hub_docs_link_roadmap_supporting_cross_cutting_issues() -> None:
    """Hub docs + review.html deep-link ROADMAP Supporting / cross-cutting via explicit HTML anchor + stable fragment."""
    roadmap = DOCS_ROADMAP_MD.read_text(encoding="utf-8")
    assert '<a id="supporting-cross-cutting-issues"></a>' in roadmap
    assert "](ROADMAP.md#supporting-cross-cutting-issues)" in DOCS_BACKLOG_MD.read_text(encoding="utf-8")
    assert "](ROADMAP.md#supporting-cross-cutting-issues)" in DOCS_CONTRIBUTING_MD.read_text(encoding="utf-8")
    assert "](ROADMAP.md#supporting-cross-cutting-issues)" in DOCS_ISSUES_BACKLOG_MD.read_text(encoding="utf-8")
    assert "](#supporting-cross-cutting-issues)" in roadmap
    review = REVIEW_HTML.read_text(encoding="utf-8")
    assert 'href="docs/ROADMAP.md#supporting-cross-cutting-issues"' in review
    assert "blob/main/docs/ROADMAP.md#supporting-cross-cutting-issues" in review


def test_contributing_ci_documents_roadmap_supporting_cross_cutting_bullet() -> None:
    """Continuous integration section documents ROADMAP Supporting / cross-cutting anchor + layout-sync test."""
    md = DOCS_CONTRIBUTING_MD.read_text(encoding="utf-8")
    ci_start = md.index("### Continuous integration")
    table_start = md.index("| **`test_pyproject_contract.py`**", ci_start)
    chunk = md[ci_start:table_start]
    start = chunk.index("**ROADMAP Supporting / cross-cutting**")
    end = chunk.index("\n- **README `## Web shell (review)` anchor**", start)
    bullet = chunk[start:end]
    assert "supporting-cross-cutting-issues" in bullet
    assert "**`review.html`** Documentation cards" in bullet
    assert "blob" in bullet
    assert "**`bug_report.md`**" in bullet
    assert "**README** top **Docs** bar" in bullet
    assert "test_hub_docs_link_roadmap_supporting_cross_cutting_issues" in bullet
    assert "test_readme_links_roadmap_supporting_cross_cutting" in bullet
    assert "test_review_html_python_desktop_section_mentions_help_epilog" in bullet
    assert "test_github_issue_templates_reference_core_docs" in bullet


def test_pr_template_roadmap_row_cites_supporting_cross_cutting_layout_sync_test() -> None:
    """PR template ROADMAP checklist row should cite supporting-cross-cutting anchor + pytest names."""
    text = GITHUB_PULL_REQUEST_TEMPLATE_MD.read_text(encoding="utf-8")
    assert "supporting-cross-cutting-issues" in text
    assert "README.md" in text
    assert "Python + desktop" in text
    for name in (
        "test_hub_docs_link_roadmap_supporting_cross_cutting_issues",
        "test_readme_links_roadmap_supporting_cross_cutting",
        "test_review_html_python_desktop_section_mentions_help_epilog",
    ):
        assert name in text, f"PULL_REQUEST_TEMPLATE.md should mention {name!r}"


def test_issues_backlog_orients_readme_docs_bar_and_github_config() -> None:
    """issues-backlog explains BACKLOG vs this index + README Short index + config.yml chooser."""
    text = DOCS_ISSUES_BACKLOG_MD.read_text(encoding="utf-8")
    assert "](ROADMAP.md#supporting-cross-cutting-issues)" in text
    assert ".github/ISSUE_TEMPLATE/config.yml" in text
    assert "Running Tests, **Doc index (issues-backlog)**)." in text
    assert "Short index" in text
    assert "../README.md#desktop-app-pyside6" in text
    assert "../README.md#default-database-paths-windows" in text
    assert "../README.md#excel-workbook-template-openpyxl" in text
    assert "Excel workbook template (openpyxl)" in text
    assert "integrations/work-context.example.json" in text
    assert "](CONTRIBUTING.md#running-tests)" in text
    assert "Continuous integration" in text
    assert "**Doc index (issues-backlog)** contact **`about`** text" in text
    assert "shown in the GitHub **New issue** chooser" in text
    assert "both **Issues backlog** cards" in text
    assert "**Hub docs — issues-backlog link text**" in text
    assert "**Hub docs — README default database paths segment**" in text
    assert "verbatim-aligned" in text
    assert "**SQLite issue #21**" in text
    assert "tests/test_issue_21_schema_inventory.py" in text
    assert "probooks/migrations/" in text
    assert "probooksai/bank_import.py" in text


def test_issues_backlog_documents_excel_help_epilog() -> None:
    """issues-backlog short index should mention help_epilog, backup API, + both entrypoints (hub parity)."""
    text = DOCS_ISSUES_BACKLOG_MD.read_text(encoding="utf-8")
    assert "probooks/help_epilog.py" in text
    assert "python -m probooks" in text
    assert "python -m desktop_app.main" in text
    assert "probooks.backup" in text
    assert "SQLite online backup" in text
    assert "../README.md#python-cli" in text


def test_backlog_links_readme_desktop_app_section() -> None:
    """BACKLOG implementation row should deep-link README Desktop (theme + Qt notes)."""
    text = DOCS_BACKLOG_MD.read_text(encoding="utf-8")
    assert "../README.md#desktop-app-pyside6" in text


def test_backlog_phase1_storage_row_documents_issue_21_schema_inventory() -> None:
    """BACKLOG Phase 1 storage row should point implementers at the CLI vs desktop DDL inventory tests."""
    text = DOCS_BACKLOG_MD.read_text(encoding="utf-8")
    assert "| Phase 1 storage |" in text
    assert "tests/test_issue_21_schema_inventory.py" in text
    assert "](CONTRIBUTING.md#continuous-integration)" in text
    assert "**SQLite issue #21** bullet" in text


def test_backlog_implementation_row_documents_excel_help_epilog() -> None:
    """BACKLOG MVP-in-repo row stays aligned with ROADMAP Phase 22 / README Desktop --help note."""
    text = DOCS_BACKLOG_MD.read_text(encoding="utf-8")
    assert "probooks/help_epilog.py" in text
    assert "python -m probooks" in text
    assert "python -m desktop_app.main" in text
    assert "](ROADMAP.md#supporting-cross-cutting-issues)" in text, (
        "BACKLOG MVP-in-repo row should link ROADMAP Supporting / cross-cutting for remaining gaps"
    )


def test_hub_docs_link_issues_backlog_short_index() -> None:
    """ROADMAP and BACKLOG Related docs should link issues-backlog.md (same folder)."""
    needle = "](issues-backlog.md)"
    for rel in ("docs/ROADMAP.md", "docs/BACKLOG.md"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert needle in text, f"{rel} should link issues-backlog.md"


def test_docs_indexes_link_readme_web_shell_review() -> None:
    """Hub docs should deep-link README ## Web shell (review) (ROADMAP blockquote, BACKLOG, issues-backlog, CONTRIBUTING)."""
    needle = "../README.md#web-shell-review"
    for rel in ("docs/ROADMAP.md", "docs/BACKLOG.md", "docs/issues-backlog.md", "docs/CONTRIBUTING.md"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert needle in text, f"{rel} should contain {needle!r}"


def test_hub_docs_link_readme_desktop_app_section() -> None:
    """Hub docs deep-link README ## Desktop app (PySide6) (parity with README docs bar)."""
    needle = "../README.md#desktop-app-pyside6"
    for rel in ("docs/ROADMAP.md", "docs/BACKLOG.md", "docs/issues-backlog.md", "docs/CONTRIBUTING.md"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert needle in text, f"{rel} should contain {needle!r}"


def test_hub_docs_link_contributing_running_tests_section() -> None:
    """Hub docs deep-link CONTRIBUTING ## Running Tests (work-context / sync-workspace)."""
    needle = "CONTRIBUTING.md#running-tests"
    for rel in ("docs/ROADMAP.md", "docs/BACKLOG.md", "docs/issues-backlog.md"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert needle in text, f"{rel} should contain {needle!r}"
    contrib = DOCS_CONTRIBUTING_MD.read_text(encoding="utf-8")
    assert "[Running Tests](#running-tests)" in contrib


def test_pr_template_ci_bundle_lists_cursor_rule_and_layout_guard_tests() -> None:
    """PR template CI/layout checklist should cover .cursor rule edits + layout-sync pytest names."""
    text = GITHUB_PULL_REQUEST_TEMPLATE_MD.read_text(encoding="utf-8")
    assert "**`tests/conftest.py`**" in text, (
        "PR template CI row should remind editors to sync CONTRIBUTING when conftest changes"
    )
    assert "**`.cursor/rules/github-work-context.mdc`**" in text
    assert "**`.gitattributes`**" in text, (
        "PR template CI row should remind editors to sync CONTRIBUTING when .gitattributes changes"
    )
    for name in (
        "test_cursor_rule_github_work_context_points_at_contributing_ci",
        "test_contributing_ci_documents_cursor_github_work_context_rule_test",
        "test_ci_validate_layout_sh_and_ps1_same_paths_and_order",
        "test_ci_validate_layout_sh_require_paths_exist",
        "test_layout_validator_hub_cites_require_paths_pytest",
        "test_layout_validator_windows_bash_path_guidance_in_hub_ci_scripts_and_cursor_rule",
        "test_readme_ci_validate_layout_bullet_mentions_conftest",
        "test_readme_contributing_section_mentions_conftest",
        "test_readme_python_cli_section_mentions_backup_restore_online_api",
        "test_readme_docs_bar_links_python_cli_anchor",
        "test_hub_docs_related_docs_link_readme_excel_workbook_template",
        "test_hub_docs_related_docs_link_readme_default_database_paths",
        "test_readme_default_database_paths_notes_two_schemas_and_roadmap",
        "test_roadmap_snapshot_why_not_one_db_points_at_issue_21_inventory",
        "test_readme_docs_bar_links_default_database_paths_anchor",
        "test_review_html_readme_default_database_paths_documentation_card",
        "test_review_html_links_readme_web_shell_and_desktop_anchors",
        "test_review_html_python_desktop_section_mentions_help_epilog",
        "test_static_shell_page_sub_mentions_help_epilog",
        "test_hub_docs_link_roadmap_supporting_cross_cutting_issues",
        "test_github_issue_templates_reference_core_docs",
        "test_pr_template_lists_issue_21_schema_inventory_checklist",
    ):
        assert name in text, f"PULL_REQUEST_TEMPLATE.md should mention {name!r}"


def test_pr_template_lists_readme_python_cli_anchor_checklist() -> None:
    """PR template should remind editors to sync README ## Python CLI / #python-cli + layout tests."""
    text = GITHUB_PULL_REQUEST_TEMPLATE_MD.read_text(encoding="utf-8")
    assert "**`## Python CLI`**" in text
    assert "**`#python-cli`**" in text
    assert "**README `## Python CLI` anchor**" in text
    for name in (
        "test_readme_docs_bar_links_python_cli_anchor",
        "test_readme_python_cli_section_mentions_backup_restore_online_api",
        "test_issues_backlog_documents_excel_help_epilog",
        "test_pr_template_lists_readme_python_cli_anchor_checklist",
        "test_contributing_ci_documents_readme_python_cli_anchor_bullet",
    ):
        assert name in text, f"PULL_REQUEST_TEMPLATE.md should mention {name!r}"


def test_cursor_rule_github_work_context_points_at_contributing_ci() -> None:
    """Cursor work-context rule should point hub doc edits at CONTRIBUTING CI + layout-sync tests."""
    text = CURSOR_RULE_GITHUB_WORK_CONTEXT_MDC.read_text(encoding="utf-8")
    assert "issues-backlog.md" in text
    assert "bug_report.md" in text
    assert "test_github_issue_templates_reference_core_docs" in text
    assert "config.yml" in text
    assert "help_epilog" in text
    assert "test_hub_docs_related_docs_link_readme_excel_workbook_template" in text
    assert "test_hub_docs_related_docs_link_readme_default_database_paths" in text
    assert "### Default database paths (Windows)" in text
    assert "Why not one `.db` yet" in text
    assert "probooks/migrations/*.sql" in text
    assert "probooksai/bank_import.py" in text
    assert "tests/test_issue_21_schema_inventory.py" in text
    assert "test_readme_default_database_paths_notes_two_schemas_and_roadmap" in text
    assert "test_roadmap_snapshot_why_not_one_db_points_at_issue_21_inventory" in text
    assert "test_readme_docs_bar_links_default_database_paths_anchor" in text
    assert "README.md#default-database-paths-windows" in text
    for name in (
        "test_review_html_readme_default_database_paths_documentation_card",
        "test_review_html_links_readme_web_shell_and_desktop_anchors",
        "test_review_html_python_desktop_section_mentions_help_epilog",
        "test_static_shell_page_sub_mentions_help_epilog",
        "test_ci_validate_layout_sh_require_paths_exist",
        "test_layout_validator_hub_cites_require_paths_pytest",
        "test_layout_validator_windows_bash_path_guidance_in_hub_ci_scripts_and_cursor_rule",
        "test_readme_ci_validate_layout_bullet_mentions_conftest",
        "test_readme_contributing_section_mentions_conftest",
        "test_readme_python_cli_section_mentions_backup_restore_online_api",
        "test_readme_docs_bar_links_python_cli_anchor",
        "test_contributing_ci_documents_issue_21_schema_inventory_bullet",
        "test_pr_template_lists_issue_21_schema_inventory_checklist",
    ):
        assert name in text, f"github-work-context.mdc should mention {name!r}"
    assert "review.html" in text
    assert "test_ci_validate_layout_sync.py" in text
    assert "CONTRIBUTING.md#continuous-integration" in text
    assert "ci_validate_layout.sh" in text
    assert "ci_validate_layout.ps1" in text
    assert "tests/conftest.py" in text
    assert "isolated_branded_app_data_env" in text
    assert "**Layout validators:**" in text
    assert "same path in both lists" in text
    assert (
        "**Layout + workflow contracts** documents what **`test_cursor_rule_github_work_context_points_at_contributing_ci`** covers"
        in text
    )
    assert "test_hub_docs_link_roadmap_supporting_cross_cutting_issues" in text


def test_contributing_ci_documents_cursor_github_work_context_rule_test() -> None:
    """Continuous integration section should list the Cursor rule contract test."""
    md = DOCS_CONTRIBUTING_MD.read_text(encoding="utf-8")
    ci_start = md.index("### Continuous integration")
    table_start = md.index("| **`test_pyproject_contract.py`**", ci_start)
    chunk = md[ci_start:table_start]
    assert "**Layout + workflow contracts**" in chunk
    layout_start = chunk.index("- **Layout + workflow contracts**")
    layout_end = chunk.index("\n- **Markdown (hub files)**", layout_start)
    layout_bullet = chunk[layout_start:layout_end]
    assert "**`.gitattributes`**" in layout_bullet, (
        "Layout + workflow contracts bullet should mention .gitattributes in the path-list parity clause"
    )
    assert "probooks/help_epilog.py" in chunk
    assert "tests/conftest.py" in chunk
    assert "isolated_branded_app_data_env" in chunk
    assert "test_layout_validator_windows_bash_path_guidance_in_hub_ci_scripts_and_cursor_rule" in chunk
    assert "test_ci_validate_layout_sh_require_paths_exist" in chunk
    assert "test_layout_validator_hub_cites_require_paths_pytest" in chunk
    assert "test_readme_ci_validate_layout_bullet_mentions_conftest" in chunk
    assert "test_readme_contributing_section_mentions_conftest" in chunk
    assert "test_readme_python_cli_section_mentions_backup_restore_online_api" in chunk
    assert "test_readme_docs_bar_links_python_cli_anchor" in chunk
    assert "test_cursor_rule_github_work_context_points_at_contributing_ci" in chunk
    assert "test_hub_docs_related_docs_link_readme_excel_workbook_template" in chunk
    assert "test_hub_docs_related_docs_link_readme_default_database_paths" in chunk
    assert "test_readme_default_database_paths_notes_two_schemas_and_roadmap" in chunk
    assert "test_roadmap_snapshot_why_not_one_db_points_at_issue_21_inventory" in chunk
    assert "test_readme_docs_bar_links_default_database_paths_anchor" in chunk
    assert "Why not one `.db` yet" in chunk
    assert "test_review_html_readme_default_database_paths_documentation_card" in chunk
    assert "test_review_html_links_readme_web_shell_and_desktop_anchors" in chunk
    assert "test_review_html_python_desktop_section_mentions_help_epilog" in chunk
    assert "test_static_shell_page_sub_mentions_help_epilog" in chunk
    assert "test_github_issue_templates_reference_core_docs" in chunk
    assert (
        ", and **`test_github_issue_templates_reference_core_docs`** for **`.github/ISSUE_TEMPLATE/`** / **`config.yml`** / **`bug_report.md`** **Triaging**"
        in chunk
    )
    assert "test_hub_docs_link_roadmap_supporting_cross_cutting_issues" in chunk
    assert "README.md#default-database-paths-windows" in chunk
    assert "test_contributing_ci_documents_issue_21_schema_inventory_bullet" in chunk
    assert "test_pr_template_lists_issue_21_schema_inventory_checklist" in chunk
    assert "test_pr_template_ci_bundle_lists_cursor_rule_and_layout_guard_tests" in chunk
    assert "**`.cursor/rules/github-work-context.mdc`**" in chunk
    assert "both **`require`** **`.cursor/rules/github-work-context.mdc`**" in chunk
    assert "documented in that file" in chunk
    assert "**Layout validators** paragraph, which references this **Layout + workflow contracts** bullet" in chunk
