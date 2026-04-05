#!/usr/bin/env bash
# scripts/build_desktop.sh
# Build a standalone ProBooks+ai desktop executable on macOS / Linux (output: ProBooksPlusAi).
# Bundles ai/ (Document Intake Run AI), probooks/, probooksai/, desktop_app/, docs/ (ROADMAP.md),
# pyproject.toml; hidden-import generate_workbook (COA seed); full OpenAI SDK subtree + hidden-import pypdf (ai.extractor).
#
# Usage:
#   chmod +x scripts/build_desktop.sh
#   ./scripts/build_desktop.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

# 1. Ensure PyInstaller is installed; have openai + pypdf installed (e.g. pip install -r requirements.txt or .[ci])
#    so analysis can bundle them. Editable desktop: pip install -e ".[desktop]"
python -m pip install --quiet pyinstaller

# 1b. Resolved app version (same helper as the desktop UI / --version; pyproject.toml when not installed)
echo "Packaging ProBooks+ai version $(python -c 'from desktop_app.version import application_version; print(application_version())')"

# 2. Build (paths + bundled packages for frozen runtime; copy-metadata needs pip install -e ".[desktop]" first)
python -m PyInstaller \
    --noconfirm \
    --clean \
    --name ProBooksPlusAi \
    --onefile \
    --windowed \
    --paths "$REPO_ROOT" \
    --add-data "ai:ai" \
    --add-data "probooks:probooks" \
    --add-data "probooksai:probooksai" \
    --add-data "desktop_app:desktop_app" \
    --add-data "docs:docs" \
    --add-data "pyproject.toml:." \
    --copy-metadata probooks-ai \
    --hidden-import generate_workbook \
    --collect-submodules openai \
    --hidden-import pypdf \
    desktop_app/main.py

echo ""
echo "Build complete. Executable is in: $REPO_ROOT/dist/"
