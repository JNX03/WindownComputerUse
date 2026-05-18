# Troubleshooting ladder

Symptom -> first thing to try. If the first thing doesn't fix it, fall through to the diagnostic notes.

## Symptom table

| Symptom | First thing to try |
|---|---|
| `mouse_click` returned `ok:true` but screen unchanged | Retry with `use_real_cursor=true`; confirm `method=real-cursor` in the response |
| Drag on Paint canvas / game / DirectX surface did nothing | `use_real_cursor=true` is mandatory there |
| `click_text` / `find_text_on_screen` returns `OCR failed: No module named 'winrt.windows.globalization'` | OCR backend missing on host - see `ocr-fallback.md`. Fall back to coords or keyboard shortcuts |
| `keyboard_type` returned `"method":"paste"` unexpectedly | Your string had Unicode (em dash, smart quotes, emoji). Either ASCII-ify or accept paste mode |
| Window won't focus after `focus_window` | `list_windows()` -> confirm the exact title; some windows are minimized at `(-32000, -32000)` and need `restore_window` first |
| `wait_for_window` matched the wrong instance | A prior instance was already open. Use a more specific substring, or diff `list_windows()` before/after |
| Coordinates off | `list_monitors()` - figure out if you're computing against virtual desktop (index 0) or an individual monitor (index 1+) |
| App won't launch | `permission_status()` - either `permission_add_allowed_app(app_name=...)` or `permission_set_bypass(enabled=True)` |
| Tool returned `ok:true` but effect didn't happen and `mouse` retry doesn't help | `emergency_stop_status()` - the user may have pressed Ctrl+Shift+X. Resume only with their go-ahead |
| Screenshot result was truncated or dumped to a file path instead of inline | Region was too large. Use a smaller `screenshot_region` or single-monitor `screenshot(monitor_index=1)`, or use `screenshot_to_file` to skip the inline base64 entirely |
| UAC dialog appeared | You can't interact with it - runs on the Secure Desktop. Ask the user to click |
| Recording started but no file appears at the path | Check `~/.win_computer_use/recordings/`. The default path uses a `capture-YYYYMMDD-HHMMSS.mp4` template. Files are finalized only on `record_screen_stop()` |
| `wait_for_text` times out but you can see the text on screen | OCR is probably broken on this host. Test with `find_text_on_screen("known-visible-text")` to confirm; if that also fails, see `ocr-fallback.md` |
| `kill_process` returned `ok:true` but the process is still there | The process was a child / has a watchdog. List processes again, kill the parent, or ask the user |
| `volume_mute` toggled when you wanted to set explicitly | You omitted `on=`. Always pass `on=true` or `on=false`; the default of `null` toggles |

## Diagnostic commands

When you're stuck, run these in parallel:

```
get_state()
permission_status()
emergency_stop_status()
list_windows()
list_monitors()
get_virtual_cursor()
```

Cross-reference:

- `get_state().heartbeat_at` should be within ~5 seconds of now. If older, the overlay process may have died.
- `emergency_stop_status().started` should be `true` for the hotkey to work. `.stopped` should be `false`.
- `permission_status().bypass` - is the AI allowed to launch arbitrary apps right now?
- `get_state().virtual_cursor_x/y` should match where you last moved the virtual cursor. If not, something else updated state mid-flight.

## When the server itself seems dead

- `get_state()` returns nothing or errors -> the MCP server isn't responding. Ask the user to check the Electron manager Activity panel.
- `heartbeat_at` is more than a minute old -> ditto.
- Restart path: user closes the manager and reruns `setup.bat` or `cd electron-manager && npm start`, or restarts the MCP client (Claude Code etc.).

## Activity log for forensics

Every announced tool call is appended to `%USERPROFILE%\.win_computer_use\activity.log` as JSONL. Useful if you need to figure out what happened *before* you joined the session. Read the tail with:

```
read_text_file(path="C:\\Users\\<user>\\.win_computer_use\\activity.log", max_bytes=50000)
```

You'll get a prefix; if `truncated: true`, raise `max_bytes`. JSON-decode each line.
