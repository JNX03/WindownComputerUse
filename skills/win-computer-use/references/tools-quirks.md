# Tool quirks observed on real hardware

These are the non-obvious behaviors confirmed by hands-on testing while writing this skill. Each one will save you a debugging round-trip.

## keyboard_type - Unicode triggers paste mode

The tool description says "Unicode falls back to clipboard paste". In practice this fires for **any** non-ASCII character: em dashes (`—`), smart quotes (`'`, `"`), accented letters (`é`), emoji.

Observed: typing `"Hello — world"` returned `{"chars": 14, "method": "paste", "ok": true}`. The user's clipboard was silently overwritten.

**Mitigation:** keep strings ASCII-only, or save and restore the clipboard around `keyboard_type` calls.

## close_window does NOT prompt for unsaved changes

`close_window("Untitled - Notepad")` will close a Notepad window with unsaved edits **without** the "Do you want to save?" prompt. Changes are discarded.

**Mitigation:** save first (`Ctrl+S` or `write_text_file`). Only `close_window` after you've verified state is committed.

## wait_for_window matches pre-existing windows

`wait_for_window("Paint", timeout_s=8)` returns instantly (`found_after_s: 0.0`) if there is already any window whose title contains "Paint". This includes windows you didn't launch and minimized-but-mapped windows.

**Mitigation:** use a more distinctive substring (e.g. `"Untitled - Paint"` for a freshly-launched Paint), or capture `list_windows()` before launch and diff after.

## Window titles starting with `*` signal "modified"

A modified Notepad doc has title `"*Untitled - Notepad"`. If you match on the literal `"Untitled - Notepad"` you will miss the dirty version. Use a substring like `"Notepad"` or strip the leading `*`.

## Minimized windows at (-32000, -32000)

`list_windows()` may show windows with coords `(-32000, -32000)`. That's the Windows convention for "minimized but still mapped" - it's where Windows parks the off-screen rect. Not a bug, not a real position you should click on.

## screenshot_region can blow your token limit

A 1536x300 region returned ~58k characters of base64, which exceeded the 25k-token-ish MCP response cap and was saved to a temp file instead of inlined. The tool result then includes a path you'd need to read separately.

**Mitigation:**
- For UI feedback, take the smallest region that contains the change.
- For "where am I" framing, use `screenshot(monitor_index=1)` of a single monitor, not `monitor_index=0` (which is the full virtual desktop).
- If you need a persisted artifact, use `screenshot_to_file(path=..., monitor_index=...)` instead - returns just the path and dimensions, no inline base64.

## write_text_file normalizes line endings to CRLF

`write_text_file(path=..., content="line1\nline2")` writes `"line1\r\nline2"` to disk (5 chars of overhead on Windows). The returned `bytes_written` is the **input** length, not the on-disk length.

```
write_text_file(content="round-trip test\nline two")
  -> {"ok": true, "bytes_written": 24, ...}    # 24 input chars

read_text_file(path=...)
  -> {"size_bytes": 25, "returned_bytes": 25, "text": "round-trip test\r\nline two"}
```

This bites you if you're checksumming or computing file sizes downstream. Either accept CRLF or write raw bytes via another mechanism.

## clipboard pollution survives sessions

Anything written to the clipboard (by `clipboard_set`, or by `keyboard_type`'s Unicode paste fallback) stays in the clipboard until Windows overwrites it. Multiple agent sessions can step on each other's clipboard.

**Mitigation:** snapshot at start, restore at end:

```
saved = clipboard_get()
# ... work ...
clipboard_set(text=saved.get("text", ""))
```

## last_action in state.json is often null

`get_state()` returns `last_action_args` and `last_action_at` - but `last_action` itself was observed to stay `null` across many tool calls during testing. Don't rely on it as a "did my call register" signal.

Use instead:
- The tool's own return value (most reliable).
- `heartbeat_at` (advances every few seconds).
- `last_action_at` (does advance when an `@announced` decorator fires).

## macro_run uses bare tool names

Inside the `steps=[...]` payload, the `tool` field is just `mouse_move`, not `mcp__win-computer-use__mouse_move`. The MCP namespace prefix is stripped.

```
{"tool": "mouse_move", "args": {"x": 100, "y": 200}, "wait_ms": 50}
```

`wait_ms` is applied **after** the step.

## http_get sends a distinctive User-Agent

`User-Agent: win-computer-use/0.3`. Some sites block it. If a fetch returns 403 / weird HTML, that's the likely cause. Either drive a browser instead, or accept the failure - there's no built-in UA override in the tool signature.

## OCR backend can be silently missing

`find_text_on_screen` and `click_text` use `Windows.Media.Ocr`. The Python `winrt-Windows.Media.Ocr` wheel depends transitively on `winrt-Windows.Globalization`, which is **not** in `requirements.txt`. On a fresh install that didn't grab Globalization, both tools return:

```
{"ok": false, "error": "OCR failed: No module named 'winrt.windows.globalization'"}
```

`wait_for_text` returns `{"ok": false, "error": "timeout"}` after the timeout, not the specific OCR error. So you can't tell from a `wait_for_text` timeout alone whether OCR is broken or the text just isn't on screen yet - test once with `find_text_on_screen("anything-likely-present")` to disambiguate.

**Fix:** `pip install winrt-Windows.Globalization` in the same env that runs the MCP server. See `references/ocr-fallback.md`.

## Emergency hotkey thread can fail to start

`emergency_stop_status()` returned `"started": false` during testing. The Win32 `RegisterHotKey` call can fail silently if the combo is already claimed by another app, or if the hotkey thread didn't initialize. The MCP server doesn't loudly surface this - you have to ask.

**Mitigation:** check `.started` on every session start. If `false`, tell the user; they have the Electron manager STOP button as a backup.

## Wait helpers return shapes

- `wait_for_window(title_substring, timeout_s)` -> `{"ok": true, "found_after_s": float, "title": ..., "x":, "y":, "w":, "h":}` or `{"ok": false, "error": "timeout"}`.
- `wait_for_pixel_color(x, y, hex_color, tolerance, timeout_s)` -> `{"ok": true, ...}` or `{"ok": false, "error": "timeout", "actual": "#hex"}`. The `actual` field is gold for tuning.
- `wait_for_text(text, region, timeout_s)` -> `{"ok": true, ...}` or `{"ok": false, "error": "timeout"}`. Doesn't surface OCR-backend errors distinctly.

## Tool name aliases for launch_app

`launch_app(name_or_path="notepad")` resolves these aliases internally:

| Alias | Resolves to |
|---|---|
| `notepad` | `notepad.exe` |
| `mspaint`, `paint` | `mspaint.exe` |
| `edge` | Microsoft Edge |
| `chrome` | Chrome (if installed and allowed) |
| `calc` | Calculator |
| `explorer` | File Explorer |

Anything else: provide the full path or an exe basename that's in `allowed_apps`.

## permission_status returns more than the schema suggests

`permission_status()` returns the full config blob, not just permission-related fields. You also get `agent_name`, `cursor_color`, `cursor_label_text_color`, `overlay_enabled`, `showcase_mode`, `emergency_hotkey`, `label_hide_after_s`, `cursor_auto_hide_after_s`, `cursor_fade_duration_s`, `cursor_wake_duration_s`, `app_theme`, `app_default_page`. Useful one-stop diagnostic.

## get_battery works on desktops too (sometimes)

The tool description says "or error on a desktop", but on a laptop docked to mains it returns `{"ok": true, "percent": 100, "plugged_in": true, "seconds_left": null}`. `seconds_left` is `null` when plugged in or when the OS can't estimate.

## download_file silently overwrites

`download_file(url=..., dest_path=...)` will overwrite `dest_path` if it exists without a warning. Same for `screenshot_to_file` and `write_text_file` (unless `append=true`). Check existence first if you need to preserve.
