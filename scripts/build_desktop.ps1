# scripts/build_desktop.ps1
# Build a standalone ProBooks+ai desktop executable on Windows (output: ProBooksPlusAi.exe).
# Bundles ai/ (Document Intake Run AI), probooks/, probooksai/, desktop_app/, docs/ (ROADMAP.md),
# pyproject.toml; hidden-import generate_workbook (COA seed); openai + pydantic + httpx/httpcore subtrees; hidden-import pypdf (ai.extractor).
#
# Usage (PowerShell):
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\scripts\build_desktop.ps1

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RepoRoot  = Split-Path -Parent $ScriptDir

Set-Location $RepoRoot

# 1. Ensure PyInstaller is installed; have openai + pypdf installed (e.g. pip install -r requirements.txt or .[ci])
#    so analysis can bundle them. Editable desktop: pip install -e ".[desktop]"
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
    "--add-data=ai;ai" `
    "--add-data=probooks;probooks" `
    "--add-data=probooksai;probooksai" `
    "--add-data=desktop_app;desktop_app" `
    "--add-data=docs;docs" `
    "--add-data=pyproject.toml;." `
    --copy-metadata probooks-ai `
    --hidden-import generate_workbook `
    --collect-submodules openai `
    --collect-submodules pydantic `
    --collect-submodules httpx `
    --collect-submodules httpcore `
    --hidden-import pypdf `
    desktop_app/main.py

Write-Host ""
Write-Host "Build complete. Executable is in: $RepoRoot\dist\"
