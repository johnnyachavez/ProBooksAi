# scripts/build_desktop.ps1
# Build a standalone ProBooksAi desktop executable on Windows.
#
# Usage (PowerShell):
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\scripts\build_desktop.ps1

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RepoRoot  = Split-Path -Parent $ScriptDir

Set-Location $RepoRoot

# 1. Ensure PyInstaller is installed
python -m pip install --quiet pyinstaller

# 2. Build
python -m PyInstaller `
    --name ProBooksAi `
    --onefile `
    --windowed `
    "--add-data=probooksai;probooksai" `
    desktop_app/main.py

Write-Host ""
Write-Host "Build complete. Executable is in: $RepoRoot\dist\"
