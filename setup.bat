@echo off
REM Win:Computer Use — one-click setup launcher.
REM
REM Opens the Electron manager which walks you through installing Python deps
REM and wiring up MCP for Claude Code, Claude Desktop, Codex, OpenCode, etc.
REM
REM Requires: Node.js 18+. If you don't have it, install from https://nodejs.org first.

setlocal
set "ROOT=%~dp0"
set "MANAGER=%ROOT%electron-manager"

where node >nul 2>nul
if errorlevel 1 (
    echo Node.js not found on PATH.
    echo Install Node 18+ from https://nodejs.org/ then re-run setup.bat.
    pause
    exit /b 1
)

pushd "%MANAGER%"
if not exist "node_modules\" (
    echo [1/2] Installing Electron manager dependencies (one-time)...
    call npm install --no-audit --no-fund
    if errorlevel 1 (
        echo npm install failed. Check the output above.
        popd
        pause
        exit /b 1
    )
)

echo [2/2] Launching manager...
call npm start
popd
endlocal
