# Win:Computer Use — installer
#
# Installs Python deps and registers the MCP server with Claude Code (if 'claude' is on PATH).
#
# Requirements:
#   - Windows 10/11
#   - Python 3.10+ (3.12 recommended). The Windows Python launcher 'py' must be available,
#     OR you can edit $pythonExe below to point at an absolute interpreter path.

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

# --- 0. Pick a Python interpreter -----------------------------------------
# Prefer py -3.12, fall back to py -3, fall back to whatever 'python' is on PATH.
$pythonExe = $null
$pythonArgs = @()
$candidates = @(
    @{ exe = "py"; args = @("-3.12"); label = "py -3.12" },
    @{ exe = "py"; args = @("-3");    label = "py -3" },
    @{ exe = "python"; args = @();    label = "python" }
)
foreach ($c in $candidates) {
    try {
        $v = & $c.exe @($c.args + @("--version")) 2>$null
        if ($v -match "^Python 3\.(1[0-9]|[2-9][0-9])\.") {
            $pythonExe = $c.exe
            $pythonArgs = $c.args
            Write-Host "Using $($c.label) -> $v"
            break
        }
    } catch { }
}
if (-not $pythonExe) {
    throw "No Python 3.10+ found on PATH. Install Python 3.12 from python.org or the Microsoft Store, then re-run."
}

# --- 1. Install dependencies ----------------------------------------------
Write-Host "[1/3] Installing Python dependencies..."
& $pythonExe @($pythonArgs + @("-m", "pip", "install", "--upgrade", "pip"))
& $pythonExe @($pythonArgs + @("-m", "pip", "install", "-r", (Join-Path $here "requirements.txt")))

# --- 2. Seed default config -----------------------------------------------
Write-Host "[2/3] Seeding default config..."
$cfgDir = Join-Path $env:USERPROFILE ".win_computer_use"
if (-not (Test-Path $cfgDir)) { New-Item -ItemType Directory -Force -Path $cfgDir | Out-Null }
$cfgFile = Join-Path $cfgDir "config.json"
if (-not (Test-Path $cfgFile)) {
    Copy-Item (Join-Path $here "config.default.json") $cfgFile
    Write-Host "  wrote $cfgFile"
} else {
    Write-Host "  $cfgFile already exists, leaving it alone"
}

# --- 3. Register with Claude Code (if available) --------------------------
Write-Host "[3/3] Registering MCP server with Claude Code..."
$resolvedPy = (& $pythonExe @($pythonArgs + @("-c", "import sys; print(sys.executable)"))).Trim()
$server = Join-Path $here "server.py"
$claude = Get-Command claude -ErrorAction SilentlyContinue
if ($claude) {
    & claude mcp add win-computer-use --scope user -- $resolvedPy $server
    Write-Host "  registered at user scope. Restart Claude Code to pick up the new tools."
} else {
    Write-Host "  'claude' CLI not on PATH. To register manually, add this to your MCP config:"
    Write-Host ""
    Write-Host "    `"win-computer-use`": {"
    Write-Host "      `"command`": `"$resolvedPy`","
    Write-Host "      `"args`": [`"$server`"]"
    Write-Host "    }"
}

Write-Host ""
Write-Host "Done."
Write-Host "  Optional: launch the standalone cursor overlay so you can see the AI's cursor:"
Write-Host "    & '$resolvedPy' -m win_computer_use.overlay --standalone"
Write-Host "  Optional: run the Electron manager for permissions / activity / live cursor settings:"
Write-Host "    cd '$(Join-Path $here 'electron-manager')'; npm install; npm start"
