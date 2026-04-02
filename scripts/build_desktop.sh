#!/usr/bin/env bash
# scripts/build_desktop.sh
# Build a standalone ProBooksAi desktop executable on macOS / Linux.
#
# Usage:
#   chmod +x scripts/build_desktop.sh
#   ./scripts/build_desktop.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

# 1. Ensure PyInstaller is installed
python -m pip install --quiet pyinstaller

# 2. Build
python -m PyInstaller \
    --name ProBooksAi \
    --onefile \
    --windowed \
    --add-data "probooksai:probooksai" \
    desktop_app/main.py

echo ""
echo "Build complete. Executable is in: $REPO_ROOT/dist/"
