# scripts/build_desktop.ps1
# Build a standalone ProBooks+ai desktop executable on Windows (output: ProBooksPlusAi.exe).
# Bundles the docs/ tree (Help uses docs/ROADMAP.md); CI requires docs/ROADMAP.md to exist.
#
# Usage (PowerShell):
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\scripts\build_desktop.ps1

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RepoRoot  = Split-Path -Parent $ScriptDir

Set-Location $RepoRoot

# 1. Ensure PyInstaller is installed (install editable + desktop extra first: pip install -e ".[desktop]")
python -m pip install --quiet pyinstaller

# 1b. Resolved app version (same helper as the desktop UI / --version; pyproject.toml when not installed)
$PackagingVersion = python -c "from desktop_app.version import application_version; print(application_version())"
Write-Host "Packaging ProBooks+ai version $PackagingVersion"

# 2. Build (paths + bundled packages for frozen runtime; copy-metadata needs pip install -e ".[desktop]" first)
python -m PyInstaller `
    --noconfirm `
    --clean `
    --name ProBooksPlusAi `
    --onefile `
    --windowed `
    "--paths=$RepoRoot" `
    "--add-data=probooksai;probooksai" `
    "--add-data=desktop_app;desktop_app" `
    "--add-data=docs;docs" `
    --copy-metadata probooks-ai `
    desktop_app/main.py

Write-Host ""
Write-Host "Build complete. Executable is in: $RepoRoot\dist\"
