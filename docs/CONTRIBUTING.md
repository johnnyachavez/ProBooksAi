# Contributing to ProBooks+ai

Thanks for contributing! Please read this short guide before opening an issue or PR.

**Other docs:** [README — Web shell](../README.md#web-shell-review) (install, CLI, **`review.html`** hub) · [README — Desktop app](../README.md#desktop-app-pyside6) (PySide6 theme + Qt notes) · [README — Excel workbook template](../README.md#excel-workbook-template-openpyxl) (**generate_workbook.py**, **openpyxl**) · [README — Contributing](../README.md#contributing) (tests, PR conventions) · [issues-backlog.md](issues-backlog.md) (short index; **config.yml** chooser + **`review.html`** Issues cards) · [BACKLOG.md](BACKLOG.md) (GitHub issue order) · [ROADMAP.md — Implementation snapshot](ROADMAP.md#implementation-snapshot-repository-2026-04) (phases + what ships in-repo today) · [Continuous integration](#continuous-integration) on this page (workflows, layout validators, contract table) · [Running Tests](#running-tests) (**`sync-workspace.ps1`**, **`integrations/work-context.example.json`**)

---

## Naming Conventions

### Product name

Use **ProBooks+ai** (plus between words, lowercase `ai`) in titles, descriptions, and user-facing copy. The **GitHub repository slug** remains `ProBooksAi` (`+` is not allowed in repo names). **Legacy** on-disk folder names (for example under `%APPDATA%`) may still read `ProBooksAi`; do not rename those in docs without a coordinated migration (see issue #21).

### Issues

Use the format: `<area>: <short description>`

Examples:
- `bank-import: dedupe logic breaks on same-day identical amounts`
- `register: running balance incorrect after sort`
- `reconciliation: mark-reconciled button stays disabled at tolerance boundary`

### Branches

Use the format: `<type>/<short-kebab-description>`

| Type | When to use |
|---|---|
| `feat/` | New feature or user-visible change |
| `fix/` | Bug fix |
| `docs/` | Documentation only |
| `refactor/` | Internal restructuring (no behaviour change) |
| `test/` | Adding or fixing tests only |
| `chore/` | Tooling, CI, dependencies |

Examples:
- `feat/bank-register-tab`
- `fix/csv-import-duplicate-fingerprint`
- `docs/roadmap-reorder`

### Pull Requests

Use [Conventional Commits](https://www.conventionalcommits.org/) style for PR titles:

```
<type>(<scope>): <imperative summary>
```

Examples:
- `feat(bank-import): add column mapping dialog and dedupe fingerprint`
- `fix(register): correct running balance after date sort`
- `docs: add ordered roadmap and banking workflow`

---

## Labels

| Label | Meaning |
|---|---|
| `phase-1-foundations` | Data model / schema changes |
| `phase-2-import` | CSV import, mapping, dedupe |
| `phase-3-register` | Bank register UI |
| `phase-4-reconciliation` | Statement periods, reconciliation |
| `phase-5-gl` | General Ledger posting |
| `phase-6-rules-ai` | Rules engine, AI suggestions |
| `phase-7-ocr` | PDF/OCR intake |
| `phase-8-invoicing` | Customer invoices, AR MVP |
| `phase-9-ar-payments` | Receive payments, AR application |
| `phase-10-ar-aging` | AR aging report |
| `phase-11-bills` | Vendor bills, AP MVP |
| `phase-12-ap-payments` | Pay bills, AP application |
| `phase-13-ap-aging` | AP aging report |
| `phase-14-sales-tax` | Sales tax settings and invoice tax |
| `phase-15-payroll` | Payroll MVP (employees + pay runs) |
| `phase-16-payroll-tax` | Payroll tax placeholder framework |
| `phase-17-bank-matching` | Link bank transactions to AR/AP/payroll |
| `phase-18-splits` | Transaction split support |
| `phase-19-transfers` | Bank-to-bank transfer transactions |
| `phase-20-receipts` | Receipt / document workflow |
| `phase-21-performance` | Large CSV imports, worker threads |
| `phase-22-export` | CSV export, reconciliation reports, Excel COA workbook (**`generate_workbook.py`** / **`openpyxl`**) — [README template](../README.md#excel-workbook-template-openpyxl) |
| `phase-23-audit-log` | Change history / audit trail |
| `phase-24-multi-company` | Multiple books / company files |
| `duplicate` | Issue is a duplicate of another |
| `bug` | Something isn't working |
| `docs` | Documentation changes |
| `good first issue` | Low complexity, good starting point |

---

## Keeping PRs Small

- **Target < 400 lines changed** per PR (excluding generated files and test fixtures).
- **One feature per PR** – if you find a bug while working on a feature, open a separate fix PR.
- **Always include tests** – add or update tests in `tests/` for any logic change.
- **Reference the issue** – include `Closes #<n>` or `Refs #<n>` in the PR description.
- **Update ROADMAP.md** if your PR completes a phase or changes the scope of a future phase.

---

## Running Tests

From the repository root (matches CI and `pyproject.toml` **`.[ci]`** extra):

```bash
pip install -e ".[ci]"
pytest
```

**CLI reference:** `python -m probooks --help` (same as `probooks --help` when the entry point is installed).

On Linux without a display, set `QT_QPA_PLATFORM=offscreen` if Qt fails to start. All tests should pass before requesting a review.

A flat **`requirements.txt`** is also checked in for environments that prefer it; the editable install above is preferred for development.

**Optional (planning / IDE context):** On Windows, **`scripts/sync-workspace.ps1`** (requires **GitHub CLI**, **`gh auth login`**) writes **`integrations/work-context.json`** with **all** repo files under **`localWorkFiles`**, plus open GitHub PRs/issues. The committed **`integrations/work-context.example.json`** is the minimal shape: exactly four sample paths — **`index.html`**, **`invoice.html`**, **`review.html`**, **`docs/ROADMAP.md`** — enforced by **`test_integrations_example_contract.py`**; generated JSON may include extra PR/issue fields from **`gh`**.

### Continuous integration

- **`.github/workflows/ci.yml`** — On **push** / **pull_request** to **`main`** / **`master`**: **`validate`** runs **`bash scripts/ci_validate_layout.sh`** (authoritative path list; twin **`scripts/ci_validate_layout.ps1`** for Windows). **`python`** job: **`python-version: "3.12"`**, **`pip install -e ".[ci]"`**, **`python -m pytest`** with **`QT_QPA_PLATFORM=offscreen`**, then **`pip install build && python -m build --wheel`**.
- **`.github/workflows/ui-screenshot.yml`** — On **PR** / **workflow_dispatch**: **`xvfb-run`** + **`scripts/capture_ui_screenshot.py`**, **`pip install -e ".[desktop]"`**, **`continue-on-error: true`**, PR comment linking the **ui-screenshots** artifact. Uses the same **Python 3.12** as **`ci.yml`**.
- **`.github/ISSUE_TEMPLATE/`** — **`bug_report.md`** / **`feature_request.md`** link **ROADMAP** (**`#implementation-snapshot-repository-2026-04`**), **BACKLOG**, **`issues-backlog.md`**, **README** (**`#web-shell-review`**, **`#desktop-app-pyside6`**, and **`#excel-workbook-template-openpyxl`** on **`main`**), **CONTRIBUTING** at **`#running-tests`** (tests / work-context) and **`#naming-conventions`**; **`config.yml`** contact links: **Contributing guide** (**`#naming-conventions`**), **Continuous integration** (**`CONTRIBUTING.md#continuous-integration`**), **Local preview** (**`README.md#web-shell-review`**), **Desktop app** (**`README.md#desktop-app-pyside6`**), **Excel workbook template** (**`README.md#excel-workbook-template-openpyxl`**), **Running Tests** (**`CONTRIBUTING.md#running-tests`**), **Doc index** (**`docs/issues-backlog.md`**) — **Doc index (issues-backlog)** **`about`** text notes **`review.html`** Issues backlog cards, **`config.yml`**, and **ROADMAP** / **BACKLOG** / **CONTRIBUTING** shared **issues-backlog.md** hub blurb (**`test_github_issue_templates_reference_core_docs`**, **`test_contributing_ci_documents_config_doc_index_about_review_hub`** in **`test_ci_validate_layout_sync.py`**).
- **issues-backlog + GitHub chooser** — **`docs/issues-backlog.md`** blockquote lists **`config.yml`** contact names; the following paragraph ties **Doc index (issues-backlog)** **`about`** ( **`config.yml`** + GitHub **New issue** chooser), **`review.html`** Issues backlog cards, **ROADMAP** / **BACKLOG** / **CONTRIBUTING** hub lines, and **[Continuous integration](#continuous-integration)**; another paragraph notes **ROADMAP** / **BACKLOG** / **Other docs** hub blurb parity (**Hub docs — issues-backlog link text**); **`review.html`** (Issues backlog Documentation cards — local **`docs/issues-backlog.md`** + GitHub **`blob/.../issues-backlog.md`**) each name **`.github/ISSUE_TEMPLATE/config.yml`** (**`test_issues_backlog_orients_readme_docs_bar_and_github_config`**, **`test_review_html_issues_backlog_card_mentions_issue_chooser_config`**, **`test_issues_backlog_documents_excel_help_epilog`**); **`PULL_REQUEST_TEMPLATE.md`** checklist cites the same **`pytest`** names (**`test_pr_template_issues_backlog_checklist_cites_layout_sync_tests`**, including **`test_contributing_ci_documents_issues_backlog_review_config_touchpoints`**); **Doc index (issues-backlog)** **`about`** ↔ **ISSUE_TEMPLATE** bullet is **`test_contributing_ci_documents_config_doc_index_about_review_hub`**.
- **Hub docs — issues-backlog link text** — Verbatim parity for the **issues-backlog.md** related-doc line across **ROADMAP**, **BACKLOG**, and this page **Other docs** — **`test_hub_docs_shared_issues_backlog_blurb_lists_config_and_review_cards`**, **`test_contributing_ci_documents_hub_shared_issues_backlog_blurb`**, **`test_pr_template_lists_hub_docs_issues_backlog_blurb_checklist`** (**`test_ci_validate_layout_sync.py`**).
- **ROADMAP snapshot anchor** — GitHub derives **`#implementation-snapshot-repository-2026-04`** from **`## Implementation snapshot (repository, 2026-04)`**. If you change that heading's month/year text, update every matching fragment (e.g. **README**, **BACKLOG**, **issues-backlog**, **`.github/ISSUE_TEMPLATE/`**, **`review.html`**) and the hard-coded strings in **`test_github_issue_templates_reference_core_docs`**, **`test_readme_links_roadmap_implementation_snapshot`**, and **`test_contributing_other_docs_links_roadmap_implementation_snapshot`**.
- **README `## Web shell (review)` anchor** — **ROADMAP**, **BACKLOG**, **issues-backlog**, this page's **Other docs**, **`review.html`** (Documentation cards), **`.github/ISSUE_TEMPLATE/`** bodies, and **`config.yml`** (**Local preview** contact link) use **`README.md#web-shell-review`**; renaming **`## Web shell (review)`** updates the slug (**`test_docs_indexes_link_readme_web_shell_review`**, **`test_github_issue_templates_reference_core_docs`**, **`test_review_html_links_readme_web_shell_and_desktop_anchors`**).
- **README `## Desktop app (PySide6)` anchor** — **ROADMAP**, **BACKLOG**, **issues-backlog**, this page's **Other docs**, **README** top **Docs** line, **`review.html`** (Documentation cards + **Python + desktop** paragraph) / **`index.html`** / **`invoice.html`**, **`.github/ISSUE_TEMPLATE/`** bodies, and **`config.yml`** (**Desktop app** contact link) use **`README.md#desktop-app-pyside6`**; renaming that heading updates the slug (**`test_hub_docs_link_readme_desktop_app_section`**, **`test_readme_docs_bar_links_desktop_app_anchor`**, **`test_github_issue_templates_reference_core_docs`**, **`test_static_html_links_readme_desktop_section`**, **`test_review_html_links_readme_web_shell_and_desktop_anchors`**, **`test_review_html_python_desktop_section_mentions_help_epilog`**, **`test_static_shell_page_sub_mentions_help_epilog`**).
- **README `### Excel workbook template (openpyxl)` anchor** — **`bug_report.md`** / **`feature_request.md`**, **`review.html`** (Documentation cards + **Python + desktop** paragraph), **`index.html`** / **`invoice.html`** (README hints), **`config.yml`** (**Excel workbook template** contact link), **ROADMAP** / **BACKLOG** **Related docs**, this page **Other docs**, and **README** top **Docs** line use **`README.md#excel-workbook-template-openpyxl`** (or **`../README.md#excel-workbook-template-openpyxl`** from **`docs/`**); renaming that Markdown heading updates the slug (**`test_github_issue_templates_reference_core_docs`**, **`test_review_html_links_readme_web_shell_and_desktop_anchors`**, **`test_static_html_links_readme_excel_workbook_section`**, **`test_pr_template_lists_readme_excel_workbook_anchor_checklist`**, **`test_contributing_ci_documents_readme_excel_workbook_anchor_bullet`**, **`test_hub_docs_related_docs_link_readme_excel_workbook_template`**, **`test_readme_docs_bar_links_excel_workbook_anchor`**, **`test_review_html_python_desktop_section_mentions_help_epilog`**, **`test_static_shell_page_sub_mentions_help_epilog`** in **`test_ci_validate_layout_sync.py`**).
- **CONTRIBUTING.md anchors (`#running-tests`, `#continuous-integration`)** — **`#running-tests`**: **README** docs bar, **ROADMAP**, **BACKLOG**, **issues-backlog**, this page's **Other docs** self-link, **`review.html`** (Documentation raw + GitHub cards), **`.github/ISSUE_TEMPLATE/`** bodies, **`config.yml`** (**Running Tests (work-context)** contact). **`#continuous-integration`**: **README** docs bar (**Contributing**), **ROADMAP** / **BACKLOG** / **issues-backlog**, this page's **Other docs** self-link, **README** **Contributing** section footer, **`review.html`** (Documentation raw + GitHub cards), **`config.yml`** (**Continuous integration** contact). Renaming **`## Running Tests`**, **`### Continuous integration`**, or their heading text updates GitHub slugs — sync all fragments and **`test_hub_docs_link_contributing_running_tests_section`**, **`test_docs_indexes_link_contributing_ci_section`**, **`test_github_issue_templates_reference_core_docs`**, **`test_readme_links_contributing_continuous_integration_anchor`**, **`test_review_html_links_contributing_doc_anchors`**.
- **`integrations/work-context.example.json`** — The **`localWorkFiles`** sample set (**`index.html`**, **`invoice.html`**, **`review.html`**, **`docs/ROADMAP.md`**) is exact-match enforced by **`test_integrations_example_contract.py`**. If you change it, update **Running Tests** (paragraph above), the contract table row for that test, **README** **`sync-workspace.ps1`** bullet, **`scripts/sync-workspace.ps1`** comment help, **`.cursor/rules/github-work-context.mdc`**, and the **PR template** work-context checklist item so every copy of the four paths stays aligned.
- **Layout + workflow contracts** — **`tests/test_ci_validate_layout_sync.py`**: **.sh** / **.ps1** path lists match; both **`require`** **`.cursor/rules/github-work-context.mdc`** (documented in that file's **Layout validators** paragraph); **`ci.yml`** **validate** step stays **`bash scripts/ci_validate_layout.sh`** (not re-inlined **`test -f`**); **ci.yml** / **ui-screenshot.yml** keep the expected install, **pytest**, **Qt**, and **wheel** strings; **Python** versions match across workflows; **`test_cursor_rule_github_work_context_points_at_contributing_ci`** guards that rule file's hub-sync pointers; **`test_pr_template_ci_bundle_lists_cursor_rule_and_layout_guard_tests`** locks the bundled CI row in **`PULL_REQUEST_TEMPLATE.md`** to that **`.mdc`** path plus **`test_ci_validate_layout_sh_and_ps1_same_paths_and_order`** (and related **`pytest`** names in the same checklist line).
- **Markdown (hub files)** — **`README.md`**, **`docs/CONTRIBUTING.md`**, **`docs/ROADMAP.md`**, **`docs/BACKLOG.md`**, **`docs/issues-backlog.md`** use ASCII **`'`** in contractions, not **`U+2019`** (**`test_hub_markdown_avoids_unicode_apostrophe_u2019`**, **`test_contributing_ci_documents_hub_markdown_u2019_bullet`**, **`test_pr_template_lists_hub_markdown_u2019_checklist`** in **`test_ci_validate_layout_sync.py`**).
- **Module contracts** — Files **`tests/test_*_contract.py`**; each must appear in **`ci_validate_layout.sh`** and **`.ps1`** (**`test_contract_test_modules_are_registered_in_layout_validators`** enforces this).

| Test module | Guards |
|---|---|
| **`test_pyproject_contract.py`** | **`pyproject.toml`** (name, description + **Excel COA workbook** / **`openpyxl`** in metadata, **`[project.urls]` Documentation** → README **`#web-shell-review`**, scripts, **`.[ci]`**, Hatch, **pytest** ini) |
| **`test_requirements_contract.py`** | **`requirements.txt`** core deps |
| **`test_package_name_contract.py`** | **`probooks-ai`** in **`desktop_app/version.py`**, **`probooks/__init__.py`** |
| **`test_integrations_example_contract.py`** | **`integrations/work-context.example.json`** (top-level keys; **`localWorkFiles`** exact set **`index.html`**, **`invoice.html`**, **`review.html`**, **`docs/ROADMAP.md`** (each once); sample **PR** / **issue** rows; **`warnings`** strings; see **Running Tests** above) |
| **`test_generate_workbook_contract.py`** | **`generate_workbook.py`** → **`probooksai.generator`** |
| **`test_desktop_main_contract.py`** | **`desktop_app/main.py`** argparse (**`--help`** epilog via **`EXCEL_COA_WORKBOOK_ARGPARSE_EPILOG`**) / **Qt** app strings + **`qInstallMessageHandler`** before **`QApplication`** (filters **`QFont::setPointSize`** stderr noise); **`desktop_app/theme.py`** Fusion style + pixel-sized app font ( **`FONT_SIZE_NORMAL`**) before/after **`setStyleSheet`**; Excel epilog text lives in **`probooks/help_epilog.py`** |
| **`test_probooks_cli_contract.py`** | **`probooks/cli.py`** argparse / epilog ( **`EXCEL_COA_WORKBOOK_ARGPARSE_EPILOG`** from **`probooks/help_epilog.py`**: **Excel COA workbook** / **`generate_workbook.py`**) |
| **`test_probooks_paths_contract.py`** | **`probooks/paths.py`** **`ProBooks+ai`** app dir |
| **`test_probooksai_database_contract.py`** | **`probooksai/database.py`** legacy **`ProBooksAi`** folder |
| **`test_local_docs_contract.py`** | **`desktop_app/local_docs.py`** → **`docs/ROADMAP.md`** |
