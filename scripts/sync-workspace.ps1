<#
.SYNOPSIS
  Writes integrations/work-context.json with all local work-tree file paths plus GitHub pull requests and issues.

.DESCRIPTION
  Requires GitHub CLI (gh) installed and authenticated: gh auth login
  Run from repo root or any path; resolves repository root automatically.
  The committed integrations/work-context.example.json documents a minimal shape for tests and onboarding
  (four sample localWorkFiles paths: index.html, invoice.html, review.html, docs/ROADMAP.md).
  The generated integrations/work-context.json lists all repo files under localWorkFiles and may include extra fields on pullRequests/issues from gh (labels, author, timestamps, etc.).

.PARAMETER IncludeClosed
  Also fetch closed issues and merged/closed PRs (higher combined limit).

.EXAMPLE
  .\scripts\sync-workspace.ps1
  .\scripts\sync-workspace.ps1 -IncludeClosed
#>
[CmdletBinding()]
param(
  [switch] $IncludeClosed
)

function Invoke-GhJson([string[]] $GhArgs) {
  $prev = $ErrorActionPreference
  $ErrorActionPreference = "SilentlyContinue"
  try {
    $out = & gh @GhArgs 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    return $out
  } finally {
    $ErrorActionPreference = $prev
  }
}

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$outDir = Join-Path $root "integrations"
$outFile = Join-Path $outDir "work-context.json"

if (-not (Test-Path $outDir)) {
  New-Item -ItemType Directory -Path $outDir | Out-Null
}

$warnings = [System.Collections.Generic.List[string]]::new()
$repoInfo = $null

$gh = Get-Command gh -ErrorAction SilentlyContinue
if (-not $gh) {
  $warnings.Add("GitHub CLI (gh) not found. Install: https://cli.github.com/ - issues and PRs will be empty.")
}

$issues = @()
$pullRequests = @()

if ($gh) {
  Push-Location $root
  try {
    $repoStr = Invoke-GhJson @("repo", "view", "--json", "nameWithOwner,url")
    if ($repoStr) {
      try { $repoInfo = $repoStr | ConvertFrom-Json } catch { $warnings.Add("Could not parse gh repo view JSON.") }
    } else {
      $warnings.Add("gh repo view failed. Use a git repo with a GitHub remote, or run: gh repo set-default")
    }

    $state = if ($IncludeClosed) { "all" } else { "open" }
    $limit = if ($IncludeClosed) { 80 } else { 100 }

    $issuesRaw = Invoke-GhJson @("issue", "list", "--state", $state, "--limit", "$limit", "--json", "number,title,url,labels,state,author,createdAt,updatedAt")
    if ($issuesRaw) {
      try { $issues = $issuesRaw | ConvertFrom-Json } catch { $warnings.Add("Could not parse gh issue list JSON.") }
    } else {
      $warnings.Add("gh issue list failed (is this directory a GitHub repo?).")
    }

    $prState = if ($IncludeClosed) { "all" } else { "open" }
    $prsRaw = Invoke-GhJson @("pr", "list", "--state", $prState, "--limit", "$limit", "--json", "number,title,url,state,author,headRefName,baseRefName,createdAt,updatedAt,isDraft")
    if ($prsRaw) {
      try { $pullRequests = $prsRaw | ConvertFrom-Json } catch { $warnings.Add("Could not parse gh pr list JSON.") }
    } else {
      $warnings.Add("gh pr list failed (is this directory a GitHub repo?).")
    }
  } finally {
    Pop-Location
  }
}

$rootPath = $root.Path
$localWorkFiles = @()
Get-ChildItem -Path $rootPath -Recurse -File -Force | ForEach-Object {
  $full = $_.FullName
  if ($full -match '[\\/]\.git[\\/]') { return }
  if ($full -match '[\\/]node_modules[\\/]') { return }
  if ($full -match '[\\/]Thumbs\.db$') { return }
  if ($full -match '[\\/]integrations[\\/]work-context\.json$') { return }
  $prefix = $rootPath.TrimEnd('\') + '\'
  if ($full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
    $rel = $full.Substring($prefix.Length)
  } else {
    $rel = $_.Name
  }
  $localWorkFiles += @{
    path         = ($rel -replace '\\', '/')
    lastWriteUtc = $_.LastWriteTimeUtc.ToString("o")
  }
}

$payload = [ordered]@{
  generatedAt    = (Get-Date).ToUniversalTime().ToString("o")
  repository     = if ($repoInfo) { $repoInfo.nameWithOwner } else { $null }
  repositoryUrl  = if ($repoInfo) { $repoInfo.url } else { $null }
  localWorkFiles = $localWorkFiles
  pullRequests   = @($pullRequests)
  issues         = @($issues)
  warnings       = @($warnings)
}

$json = $payload | ConvertTo-Json -Depth 12
[System.IO.File]::WriteAllText($outFile, $json, [System.Text.UTF8Encoding]::new($false))
$f = $localWorkFiles.Count; $p = $pullRequests.Count; $i = $issues.Count
Write-Host "Wrote $outFile ($f files, $p PRs, $i issues)"
if ($warnings.Count) {
  foreach ($w in $warnings) { Write-Warning $w }
}
