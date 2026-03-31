# Contributing to ProBooksAi

Thanks for contributing! Please read this short guide before opening an issue or PR.

---

## Naming Conventions

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

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

All tests should pass before requesting a review.
