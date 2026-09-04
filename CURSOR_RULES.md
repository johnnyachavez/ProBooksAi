# CURSOR_RULES.md

Rules every coding agent must follow on **johnnyachavez/ProBooksAi**.

## 1. Work on main only

Work directly on `main`. Do not create feature branches. Do not open pull requests.

## 2. No live QuickBooks access

Never open, read, write, or log into any live QuickBooks Desktop company file (`.QBW`), Rightworks, or QuickBooks login.

QuickBooks import work is limited to export files Johnny provides later (IIF/CSV): review first, then import. Do not invent balances. Do not build QB import unless the user explicitly asks for it in that job.

## 3. One job per agent

Complete the assigned task only. Do not expand into neighboring features.

## 4. Do not chase unrelated GUI test failures

Do not fix unrelated hanging GUI, `QDialog`, or `MainWindow` tests unless they block the current job. Prefer existing `skipif` and guard patterns.

## 5. Bank work is file-drop only

Bank import uses files Johnny provides (Chase CSV/PDF). No Chase website login or scraping.

## 6. No AI document intake

Do not build or rebuild AI document intake / Document Intake.

## 7. No invented data

Do not invent book numbers, balances, or customer/vendor data.

## 8. Finish cleanly

After changes: run the relevant tests, commit, push to `main`, and summarize what was done versus what was intentionally left out.

## 9. Ask when unsure

If scope is unclear, stop and ask. Do not guess.
