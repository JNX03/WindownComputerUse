# Win:Computer Use

> **MCP server that gives Claude (and other MCP clients) human-like control of a Windows PC — with its own virtual cursor, an emergency stop, and a manager UI.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6?logo=windows)](https://learn.microsoft.com/windows/)
[![MCP](https://img.shields.io/badge/MCP-stdio-7C3AED)](https://modelcontextprotocol.io/)
[![CI](https://github.com/JNX03/WindownComputerUse/actions/workflows/ci.yml/badge.svg)](https://github.com/JNX03/WindownComputerUse/actions/workflows/ci.yml)
[![GitHub stars](https://img.shields.io/github/stars/JNX03/WindownComputerUse?style=social)](https://github.com/JNX03/WindownComputerUse/stargazers)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

An MCP (Model Context Protocol) server that gives any MCP-capable AI client — Claude Code, Claude Desktop, custom agents, etc. — human-like control of a Windows machine.

**64 tools** covering mouse, keyboard, screen capture, OCR, window/app management, file I/O, HTTP, processes, audio, and a labeled on-screen cursor so you can see what the AI is doing.

The AI gets its own **independent virtual cursor** rendered as an always-on-top labeled overlay (an arrow + agent-name chip). Clicks default to `PostMessage`, so your real Windows cursor is never touched while the AI is working — you can keep using your machine alongside it.

A bundled **Electron manager app** lets you edit permissions, change the cursor color / agent name / motion speed, watch a live activity log, and trigger an emergency stop, without ever opening a JSON file.

## Table of contents

- [Why](#why)
- [Highlights](#highlights)
- [Demo](#demo)
- [Requirements](#requirements)
- [Install — the easy way (recommended)](#install--the-easy-way-recommended)
- [Install — manual](#install--manual)
- [Configuration](#configuration)
- [Tools](#tools)
- [How an agent typically uses it](#how-an-agent-typically-uses-it)
- [Caveats](#caveats)
- [Project layout](#project-layout)
- [Contributing](#contributing)
- [Security](#security)
- [License](#license)

## Demo

<!-- Drop a screenshot or GIF at docs/demo.gif and uncomment:
![Win:Computer Use demo](docs/demo.gif)
-->

A quick tour:

1. Launch the Electron manager — `setup.bat` walks you through Python + deps + client registration.
2. Start your MCP client (Claude Code, Claude Desktop). The server boots; the labeled overlay cursor appears.
3. Ask the model: *"Open Paint, draw a smiley face, save it to my desktop."* You'll see the arrow cursor (carrying its agent-name chip) glide along Bezier curves, click via `PostMessage`, and announce every tool call in the Activity panel.
4. Press `Ctrl+Shift+X` at any time to freeze input until you resume.

---

## Why

Anthropic ships a "computer use" tool for macOS / Linux containers but nothing turn-key for Windows. This server fills that gap with one stdio MCP process that exposes a broad, well-defined tool surface and a permission model designed for both interactive ("ask first") and autonomous ("bypass") use.

## Highlights

- **Independent virtual cursor** — clicks go via Win32 `PostMessage` by default (zero real-cursor disturbance). For apps that ignore synthetic clicks (Chromium, games, Paint canvas), every mouse tool accepts `use_real_cursor: true` to fall back to a brief real-cursor snap.
- **Human-like motion** — virtual cursor animates along a cubic Bezier path with subtle jitter, not a straight line.
- **Labeled overlay cursor** — arrow shape + rounded chip with the agent's name (e.g. `Claude`). Click-through, always-on-top, multi-monitor aware. Reads live settings from `state.json` so changes in the Electron manager apply within ~250ms.
- **Allowlist + bypass permission model** — by default, the AI can only launch apps you've allowed. One flag (`bypass: true`) lifts that for autonomous runs.
- **Native emergency stop** — `Ctrl+Shift+X` (Win32 `RegisterHotKey`) freezes input tools until `emergency_resume()` is called. The Electron manager also has a big STOP button.
- **Activity log** — every tool call is appended to `activity.log` (JSONL); the Electron Activity panel tails it live.
- **Windows OCR built-in** — `find_text_on_screen` / `click_text` use `Windows.Media.Ocr` (no Tesseract or other binaries required).
- **Screen recording** — `record_screen_start` / `_stop` write an mp4 via `imageio-ffmpeg`.

## Requirements

- Windows 10/11.
- Python **3.10+** (3.12 recommended; the official `mcp` SDK requires `>=3.10`).
- An MCP-capable client (Claude Code, Claude Desktop, etc.).
- For the Electron manager: Node.js 18+.

## Install — the easy way (recommended)

```powershell
git clone https://github.com/JNX03/win-computer-use
cd win-computer-use
./setup.bat        # or: ./setup.ps1
```

Double-click `setup.bat` and the **Setup wizard** in the Electron manager walks you through it:

1. **Python 3.10+** — auto-detects `py -3.12`, `py -3`, `python`, or `python3` on your PATH; shows the resolved interpreter.
2. **Python dependencies** — one click runs `pip install -r requirements.txt` with live output.
3. **Configure your AI client** — pick a tab and click *Copy*:
   - **Claude Code**: one-click *"Register with Claude Code now"* if the `claude` CLI is on PATH, otherwise a JSON snippet for `~/.claude.json`.
   - **Claude Desktop**: JSON for `%APPDATA%\Claude\claude_desktop_config.json`.
   - **Codex**: TOML for `~/.codex/config.toml`.
   - **OpenCode**: JSON for `~/.config/opencode/opencode.json`.
   - **Generic / JSON**: the standard MCP stdio entry for any other client.
4. **Cursor overlay (optional)** — one click launches the standalone arrow cursor.

Only Node.js 18+ is required up front; the wizard handles Python + deps + MCP registration itself.

### Install — manual

If you'd rather not run Electron:

```powershell
./install.ps1
```

This picks Python 3.10+, runs `pip install`, seeds config, and registers with Claude Code via `claude mcp add` if the CLI is on PATH.

### Manual MCP registration

Paste the contents of `claude_mcp_snippet.json` into your client's MCP config and replace `REPLACE_WITH_REPO_PATH` with the absolute path to this checkout. Example for `~/.claude.json`:

```json
{
  "mcpServers": {
    "win-computer-use": {
      "command": "py",
      "args": ["-3.12", "C:/path/to/win-computer-use/server.py"]
    }
  }
}
```

### Launch the cursor overlay

The MCP server spawns the overlay automatically when it starts. To keep an overlay alive across MCP server lifecycles (useful for short `claude -p` runs), launch a standalone overlay — or just press the button on the Setup page:

```powershell
py -3.12 -m win_computer_use.overlay --standalone
```

### Re-launch the manager later

```powershell
cd electron-manager
npm start
```

Or enable auto-launch with Windows on the Cursor & Agent page (uses Electron's `setLoginItemSettings`).

## Configuration

Lives at `%USERPROFILE%\.win_computer_use\config.json`:

```json
{
  "bypass": false,
  "allowed_apps": ["mspaint.exe", "msedge.exe", "calc.exe", "explorer.exe", "notepad.exe"],
  "blocked_apps": [],
  "max_screenshot_dim": 1920,
  "mouse_move_duration_s": 0.6,
  "fail_safe": true,
  "agent_name": "Claude",
  "cursor_color": "#3B82F6",
  "overlay_enabled": true,
  "showcase_mode": true,
  "emergency_hotkey": "ctrl+shift+x"
}
```

- `bypass` — `true` lets the AI launch any app without your approval. Use for autonomous demos; flip back to `false` for safer interactive use.
- `allowed_apps` / `blocked_apps` — exe basenames (case-insensitive).
- `fail_safe` — leave on (`pyautogui.FAILSAFE`); slamming the real cursor to (0, 0) aborts.
- `agent_name`, `cursor_color`, `overlay_enabled`, `showcase_mode`, `mouse_move_duration_s` — overlay/motion visuals.

The AI can also flip these at runtime: `permission_set_bypass`, `permission_add_allowed_app`, `set_agent_name`, `set_cursor_color`, `set_speed`, `set_showcase_mode`, `overlay_show`.

## Tools

64 tools, grouped:

**Vision** — `screenshot`, `screenshot_region`, `screenshot_to_file`, `list_monitors`, `list_windows`, `get_cursor_position`, `get_virtual_cursor`, `pixel_color`

**Mouse** (PostMessage by default; `use_real_cursor` for compat) — `mouse_move`, `mouse_move_relative`, `mouse_click`, `mouse_double_click`, `mouse_drag`, `mouse_scroll`

**Keyboard** — `keyboard_type`, `keyboard_press`, `keyboard_hotkey`, `keyboard_key_down`, `keyboard_key_up`

**Wait helpers** — `wait_seconds`, `wait_for_window`, `wait_for_text`, `wait_for_pixel_color`

**Window / app** — `launch_app`, `focus_window`, `open_file`, `get_active_window`, `close_window`, `move_window`, `minimize_window`, `maximize_window`, `restore_window`

**OCR** — `find_text_on_screen`, `click_text`

**Process / system** — `list_processes`, `kill_process`, `volume_get`, `volume_set`, `volume_mute`, `lock_workstation`, `get_battery`, `text_to_speech`

**Files / HTTP** — `read_text_file`, `write_text_file`, `list_directory`, `delete_path`, `http_get`, `download_file`

**Clipboard** — `clipboard_get`, `clipboard_set`

**Recording / macros** — `record_screen_start`, `record_screen_stop`, `macro_run`

**Cursor & overlay** — `set_agent_name`, `set_cursor_color`, `set_speed`, `set_showcase_mode`, `overlay_show`

**Permission** — `permission_status`, `permission_set_bypass`, `permission_add_allowed_app`

**Emergency** — `emergency_stop_status`, `emergency_resume`

**Diagnostics** — `get_state`

See `server.py` for parameter signatures.

## How an agent typically uses it

```text
screenshot()
   -> AI reads the image and decides where to click.
mouse_move(x, y, duration_s=0.6)    # virtual cursor slides on a curve to the target.
mouse_click(x, y)                    # PostMessage click; your real cursor never moves.
screenshot()
   -> verify the result, or recover.
```

For typing: `focus_window("Notepad")` → `keyboard_type("...")`.

For Paint or other apps that need real synthetic input: pass `use_real_cursor: true` to `mouse_drag` / `mouse_click`.

## Caveats

- **PostMessage clicks** don't work in every app. Chromium-rendered content (Edge/Chrome page bodies), games, DirectX, and most fullscreen apps ignore synthetic window messages. Use `use_real_cursor: true` there.
- **UAC dialogs** run on the Secure Desktop and can't be interacted with by user-mode synthetic input. The user has to click "Yes" manually.
- **DPI scaling**: the server sets the process Per-Monitor DPI Aware so coordinates from `mss` match `pyautogui`. Multi-monitor setups with mixed scaling should use per-monitor screenshots over the virtual desktop.
- **`fail_safe`**: keep on (`pyautogui.FAILSAFE`). Slamming the cursor to a screen corner aborts. The `bypass` flag does not disable this.

## Project layout

```
server.py                       MCP entry point (FastMCP)
win_computer_use/
  __init__.py
  permission.py                 allowlist + bypass; config file
  state.py                      shared state.json (heartbeat, virtual cursor, emergency flag)
  activity.py                   JSONL activity log
  announce.py                   @announced decorator: per-call logging + emergency gate
  winapi.py                     ctypes helpers: PostMessage clicks, RegisterHotKey
  mouse.py                      mouse_move/click/drag/scroll — virtual cursor, Bezier motion
  keyboard_io.py                type / press / hotkey
  window.py                     launch_app, focus_window, open_file
  system.py                     volume, wait, clipboard
  vision.py                     screenshot, screenshot_region, list_monitors/windows
  ocr.py                        Windows.Media.Ocr-based find_text_on_screen / click_text
  record.py                     screen recording via mss + imageio-ffmpeg
  hotkey.py                     emergency stop via winapi.RegisterHotKey
  extras.py                     Phase 3 helpers (pixel_color, waits, window mgmt, files, http, tts)
  macro.py                      macro_run — sequential tool call list
  overlay.py                    labeled cursor overlay (tkinter), runs as a separate process

electron-manager/               permissions / activity / cursor settings UI
  main.js                       Electron main: tray, single-instance, IPC
  preload.js                    contextBridge to the renderer
  renderer/index.html|app.js|styles.css

requirements.txt
install.ps1                     one-shot installer + MCP registration
config.default.json             seeded to ~/.win_computer_use/config.json on first run
claude_mcp_snippet.json         manual-register snippet
LICENSE                         MIT
.gitignore
README.md
```

## Contributing

Issues and PRs welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for the ground rules and dev setup. Code of conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Security

Found a security issue? Please **don't** open a public issue — see [SECURITY.md](SECURITY.md) for how to report it.

## License

MIT — see [LICENSE](LICENSE).
