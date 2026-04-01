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
| `phase-22-export` | CSV export and reconciliation reports |
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

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

All tests should pass before requesting a review.
