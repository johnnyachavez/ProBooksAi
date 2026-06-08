# ProBooksAi — working notes for Claude

A PySide6 desktop accounting app (`desktop_app/`) over a Python core (`probooks/`,
`probooksai/`), with an Excel workbook template and HTML mockups.

## Run / test

```bash
pip install -e ".[ci]"                 # runtime + test deps (matches CI "python" job)
python -m desktop_app.main             # launch the desktop app (needs a display)
QT_QPA_PLATFORM=offscreen python -m pytest -q   # full suite, headless
```

Headless notes:
- Qt needs system libs `libEGL1`/`libGL1` present, and `QT_QPA_PLATFORM=offscreen`.
- A modal `QDialog.exec()` segfaults under the offscreen platform; tests that rely on a
  real modal loop are `skipif`-guarded on `QT_QPA_PLATFORM == "offscreen"` (see
  `tests/test_vendor_roundup_dialog.py`). Don't add unguarded `.exec()` calls to tests.
- Headless screenshot: `QT_QPA_PLATFORM=offscreen python scripts/capture_ui_screenshot.py`
  → `artifacts/ui/main_window.png`.

## Branching workflow (read this first)

Work is done on short-lived feature branches and lands on `main` via PRs. The hazard to
avoid: a feature branch that is pushed but **never merged**, while `main` moves on — the
work then looks "lost" because new sessions branch fresh off `main`. (This is exactly how
the Write Checks / Dashboard / Assets work went missing once.)

Rules:

1. **Before starting new work**, check for existing unmerged work first:
   ```bash
   git fetch --all --prune
   git branch -a            # local + remote branches
   ```
   Also skim open PRs. If a relevant branch already exists, build on it (or merge it to
   `main` first) instead of cutting a brand-new branch off `main`.

2. **Branch from the latest `main`** (or from the branch you're extending), not from a
   stale base.

3. **Commit and push early and often.** This repo is developed in ephemeral cloud
   containers — anything not committed *and pushed* is gone when the container is
   reclaimed.

4. **Open a PR early** (draft is fine) so the work is visible and tracked. Keep PRs small
   and merge them promptly; don't let a branch accumulate dozens of unmerged commits.

5. **`main` is the single source of truth.** Merge feature branches back into `main` (via
   PR + green CI) and delete the branch once merged.

## CI

GitHub Actions runs three checks on PRs: `validate` (required-path layout checks via
`scripts/ci_validate_layout.sh`), `python` (the pytest suite, `QT_QPA_PLATFORM=offscreen`),
and a non-blocking `Capture UI Screenshot`. Keep the suite green headless before asking for
a merge. See `docs/CONTRIBUTING.md` for details.
