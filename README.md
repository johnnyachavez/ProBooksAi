# ProBooks+ai

Accounting app foundation: **dark UI shell** (static HTML) and a **Python + SQLite** core with migrations and CLI.

## Web shell (review)

```bash
python -m http.server 8765
```

Open [http://127.0.0.1:8765/review.html](http://127.0.0.1:8765/review.html).

## Python CLI

```bash
pip install -e ".[dev]"
probooks status
probooks migrate
probooks accounts list
probooks accounts add --name "Checking" --type checking --institution "Chase" --last4 1234
probooks backup --output ./backups/demo-backup.db
probooks restore --input ./backups/demo-backup.db --yes
```

### CSV import (issues #31, #33, #34)

Prepare a CSV with at least **date** and **amount** columns (0-based indices). Example:

```bash
probooks import csv --account 1 --file examples/sample_bank.csv --skip-rows 1 --date-col 0 --amount-col 1 --payee-col 2 --errors-out import-errors.csv
python -m probooks transactions --account 1 --limit 20
```

Skipped rows (bad date/amount) go to `--errors-out` when set; amounts support `$`, commas, and `(123.45)` as negative.

Database file (Windows): `%LOCALAPPDATA%\ProBooks+ai\probooks.db`.

## Issue-driven build order

See [docs/BACKLOG.md](docs/BACKLOG.md) for phased GitHub issues. Recent work targets **#21 / #27 / #28** (storage + migrations + backup) and **#30** (bank accounts).

## Tests

```bash
pytest
```
