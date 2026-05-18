# Win:Computer Use — one-click setup launcher (PowerShell).
#
# Opens the Electron manager which walks you through installing Python deps
# and wiring up MCP for Claude Code, Claude Desktop, Codex, OpenCode, etc.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$manager = Join-Path $root "electron-manager"

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "Node.js not found on PATH." -ForegroundColor Red
    Write-Host "Install Node 18+ from https://nodejs.org/ then re-run setup.ps1."
    exit 1
}

Push-Location $manager
try {
    if (-not (Test-Path "node_modules")) {
        Write-Host "[1/2] Installing Electron manager dependencies (one-time)..."
        & npm install --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw "npm install failed" }
    }
    Write-Host "[2/2] Launching manager..."
    & npm start
} finally {
    Pop-Location
}
