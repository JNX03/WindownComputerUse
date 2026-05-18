---
name: win-computer-use
description: Drive a live Windows machine through the win-computer-use MCP server. Use when you need to automate a Windows desktop UI - move the mouse, click, type, take screenshots, open or close apps, run OCR, manage windows, read or write files, record the screen, or play back macros. Covers the virtual labeled cursor, PostMessage vs real-cursor click model, OCR fallback behavior, and the emergency-stop hotkey. Activate for tasks mentioning Windows automation, GUI testing, computer use, MCP, screenshot, mouse, keyboard, "click on", or "open the app".
license: MIT
compatibility: Requires the win-computer-use MCP server running on Windows 10/11 with Python 3.10+. Some tools (OCR, screen recording) need optional Python deps to be installed correctly - the skill describes fallbacks.
metadata:
  repo: https://github.com/JNX03/WindownComputerUse
  tool_prefix: mcp__win-computer-use__
  tool_count: "64"
  version: "1.0"
---

# win-computer-use — operational guide for AI agents

You have access to the `win-computer-use` MCP server. It exposes 64 tools that let you drive a real Windows desktop: mouse, keyboard, screen capture, OCR, window/app management, files, HTTP, processes, audio, screen recording, macros, and a labeled on-screen virtual cursor. Tool names in this guide use the `mcp__win-computer-use__` prefix that Claude clients see; other clients may strip it - apply the same prefix convention your client uses.

This file is the entry point. Detailed references are split into smaller files in `references/` and loaded only when relevant.

## TL;DR

1. You have a **virtual cursor** rendered as an always-on-top labeled overlay. Clicks default to Win32 `PostMessage` so the user's real cursor is **not** touched. Pass `use_real_cursor: true` when PostMessage won't work (Paint canvas, Chromium page bodies, games).
2. Tools return `ok: true` for "I dispatched the call", not "the effect happened". **Always screenshot and verify** for UI-changing actions whose effect you cannot predict.
3. The **emergency hotkey may not be active** in this install. Check `emergency_stop_status().started` on session start and warn the user if it is `false`.
4. **OCR may be broken** on the host (missing `winrt-Windows.Globalization` transitive dep). Have a hotkey/coord fallback ready.
5. Prefer **direct tools over UI** when you can: use `write_text_file` instead of typing into Notepad, `http_get` instead of driving a browser, `clipboard_set` instead of typing long text.
6. **Don't toggle `permission_set_bypass` silently** and **don't close dirty docs without saving** - `close_window` discards changes without prompting.

## First-turn checklist

Run these in parallel at session start, then act on the results:

```
get_state()                  -> overlay alive? heartbeat fresh?
permission_status()          -> bypass on/off, what apps are allowed
emergency_stop_status()      -> if .started=false, WARN the user
emergency_resume()           -> clear stale stop flag from a prior session
list_monitors()              -> coord system and virtual desktop bounds
list_windows()               -> what is open; what to avoid touching
screenshot(monitor_index=1)  -> ground yourself visually
```

Then set your identity so the user can see who is driving:

```
set_agent_name(name="<your model name>")
set_cursor_color(hex_color="#3B82F6")   # any hex
```

A self-contained startup check is in `scripts/startup_check.py` if you want a single-shot diagnostic.

## The golden loop

```
screenshot -> reason about what is on screen -> act -> screenshot -> verify
```

Re-screenshot after any UI-changing action whose effect you cannot predict. For predictable sequences (typing into an already-focused app) you can batch several keystrokes between screenshots.

## Cursor model quick rules

| Target | Use |
|---|---|
| Notepad text area, Explorer, classic dialogs, Win32 menus, app toolbars | PostMessage (default) |
| Paint canvas, MS Paint drawing surface | `use_real_cursor: true` |
| Chromium page bodies (Edge / Chrome content area) | `use_real_cursor: true`, or keyboard navigation |
| Games, DirectX, full-screen apps | `use_real_cursor: true` |
| URL bar / tab strip in Chromium | Unreliable - prefer `keyboard_hotkey(["ctrl","l"])` |

Mouse tools (`mouse_click`, `mouse_drag`, `mouse_scroll`, `mouse_double_click`) all accept `use_real_cursor`. The response includes `"method": "postmessage"` or `"method": "real-cursor"` so you can see which path ran.

**Recovery pattern:** if a PostMessage action returned `ok:true` but the next screenshot shows no change, retry with `use_real_cursor: true`. Confirm via the `method` field in the response.

See `references/cursor-model.md` for the full theory and confirmed test results.

## Typing - non-obvious behavior

- ASCII strings are sent as real keystrokes.
- **Non-ASCII characters (em dashes, smart quotes, emoji, accented letters) trigger clipboard-paste fallback** - response shows `"method": "paste"`. The user's clipboard is overwritten. Save and restore it if it matters.
- For hotkeys: `keyboard_hotkey(keys=["ctrl","l"])` (lowercase, list form). For single special keys: `keyboard_press(key="enter")`.

## Targeting elements you can see but cannot coord-pick

Preferred order:

1. **OCR** - `click_text(text="Save")` or `find_text_on_screen(text="Save")`.
   **Heads-up:** OCR may be unavailable. Both tools then return `{"ok": false, "error": "OCR failed: No module named 'winrt.windows.globalization'"}`. See `references/ocr-fallback.md` for the fix and fallbacks.
2. **Keyboard shortcuts** - usually faster and more reliable. `Ctrl+S`, `Ctrl+L`, `Alt+F4`, `Tab`, `Enter`.
3. **Estimate coords from a screenshot** - last resort; verify with a follow-up screenshot.

## When to skip the UI entirely

If the goal is to put text in a file, fetch a URL, or read filesystem contents, use the direct tools instead of driving Notepad / Edge / Explorer:

- `write_text_file(path=..., content=...)` / `read_text_file(path=...)` - synchronous, clean results. Note: line endings are normalized to `\r\n` on write.
- `list_directory(path=..., include_hidden=false)` - returns entries with `is_dir`, `size_bytes`, `modified` (unix epoch).
- `delete_path(path=..., recursive=...)` - destructive, confirm first.
- `http_get(url=..., max_bytes=200000, timeout_s=15)` - returns `{status, content_type, bytes, text}`. User-Agent is `win-computer-use/0.3`.
- `download_file(url=..., dest_path=..., timeout_s=60)` - for binaries.
- `clipboard_get()` / `clipboard_set(text=...)`.
- `list_processes(name_contains=...)` - returns pid, exe, cpu_percent, rss_mb.

UI automation is for tasks that genuinely require the GUI (drawing, demos, app-specific features without an API).

## Worked recipes

See `references/recipes.md` for full step-by-step examples covering:

- Type-and-save a text file (UI vs direct)
- Browser search and navigation
- Drawing in MS Paint (canvas needs `use_real_cursor`)
- Calculator
- Long-running autonomous flow with screen recording
- `macro_run` for replayable multi-step sequences
- Multi-monitor + DPI handling

## Screenshots and the token-cap trap

Base64 PNGs grow fast. A 1536x300 region can exceed your client's per-response token cap and arrive truncated, or be dumped to a temp file instead of inlined. Rules of thumb:

- For UI feedback after a single action: smallest region that contains the change.
- For "where am I" framing: `screenshot(monitor_index=1)` and accept it is larger.
- Need a saved artifact? Use `screenshot_to_file(path=..., monitor_index=...)` - returns just the path and dimensions, no inline base64.
- If a screenshot result gets dumped to a file, take a smaller region rather than parsing the dump.

## Emergency stop discipline

- Default hotkey: `Ctrl+Shift+X`. Check the live value at `emergency_stop_status().combo`.
- **`.started: false` means the hotkey thread never registered** - the hotkey will NOT freeze input. Tell the user.
- After any failure that looks like "tool returned but nothing happened on screen", call `emergency_stop_status()`. If `.stopped: true`, the user hit the hotkey - do **not** silently `emergency_resume()`. Confirm with them first.

See `references/emergency-stop.md` for the full discipline.

## Settings - what persists, what doesn't

Per-session settings the AI can change at runtime:

| Tool | Effect | Persists to disk? |
|---|---|---|
| `set_agent_name(name)` | Overlay chip label | Yes (`config.json`) |
| `set_cursor_color(hex_color)` | Overlay ring color | Yes |
| `set_speed(duration_s)` | Default mouse-move duration | Yes |
| `set_showcase_mode(on)` | Slower watchable motion | Yes |
| `overlay_show(on)` | Toggle overlay visibility | Yes |
| `permission_set_bypass(enabled)` | Skip per-app approval | Yes |
| `permission_add_allowed_app(app_name)` | Add exe to allowlist | Yes |

All of these are persisted to `%USERPROFILE%\.win_computer_use\config.json` and reflected in `get_state()` immediately. **Restore changes at session end** so you don't pollute the user's defaults.

## Where to look in the repo

- `server.py` - MCP entry point, source of truth for tool signatures.
- `win_computer_use/mouse.py` - Bezier motion, PostMessage clicks, virtual cursor.
- `win_computer_use/ocr.py` - `find_text_on_screen` / `click_text` impl.
- `win_computer_use/permission.py` - config schema, bypass, allowlist.
- `win_computer_use/overlay.py` - labeled cursor overlay process.
- `win_computer_use/hotkey.py` - emergency stop hotkey.
- `win_computer_use/macro.py` - `macro_run` impl.
- `README.md` section "Tools" - full categorized tool catalog.
- `testing/demo_prompt.md` - worked 7-task example you can use as a sanity test.
- `%USERPROFILE%\.win_computer_use\config.json` - live config.
- `%USERPROFILE%\.win_computer_use\state.json` - heartbeat + virtual cursor pos.
- `%USERPROFILE%\.win_computer_use\activity.log` - JSONL of every tool call.
- `%USERPROFILE%\.win_computer_use\recordings\` - where `record_screen_start` writes mp4s.

## Detailed references in this skill

Lazy-load these when the task calls for them:

- `references/cursor-model.md` - PostMessage vs real cursor, the full theory and confirmed test results.
- `references/recipes.md` - worked recipes for common task families.
- `references/tools-quirks.md` - per-tool gotchas observed on real hardware.
- `references/troubleshooting.md` - symptom -> first thing to try table.
- `references/ocr-fallback.md` - what to do when OCR is missing or wrong.
- `references/emergency-stop.md` - hotkey discipline, started:false handling.
- `references/safety.md` - etiquette, what not to do without telling the user.
- `scripts/startup_check.py` - single-shot diagnostic you can run via Bash.
