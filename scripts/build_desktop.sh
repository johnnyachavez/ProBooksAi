#!/usr/bin/env bash
# scripts/build_desktop.sh
# Build a standalone ProBooks+ai desktop executable on macOS / Linux (output: ProBooksPlusAi).
# Bundles the docs/ tree (Help uses docs/ROADMAP.md); CI requires docs/ROADMAP.md to exist.
#
# Usage:
#   chmod +x scripts/build_desktop.sh
#   ./scripts/build_desktop.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

# 1. Ensure PyInstaller is installed (pip install -e ".[desktop]" first)
python -m pip install --quiet pyinstaller

# 1b. Resolved app version (same helper as the desktop UI / --version; pyproject.toml when not installed)
echo "Packaging ProBooks+ai version $(python -c 'from desktop_app.version import application_version; print(application_version())')"

# 2. Build
python -m PyInstaller \
    --noconfirm \
    --clean \
    --name ProBooksPlusAi \
    --onefile \
    --windowed \
    --paths "$REPO_ROOT" \
    --add-data "probooksai:probooksai" \
    --add-data "desktop_app:desktop_app" \
    --add-data "docs:docs" \
    desktop_app/main.py

echo ""
echo "Build complete. Executable is in: $REPO_ROOT/dist/"
