# Recipes

Worked end-to-end examples for common task families. Each recipe shows the tool sequence; substitute your own coordinates / strings.

## Type and save a text file

**Preferred** (no UI, fastest, no clipboard pollution):

```
write_text_file(
  path="C:\\Users\\jn03o\\Desktop\\out.txt",
  content="Hello world\nSecond line",
)
# -> {"ok": true, "bytes_written": 24, ...}
# Note: line endings are normalized to \r\n on disk, so the file will be slightly larger.
```

**Via UI** (when you must demonstrate Notepad use):

```
launch_app("notepad")
wait_for_window("Notepad", timeout_s=8)
focus_window("Notepad")
keyboard_type("Hello world")
keyboard_press("enter")
keyboard_type("Second line")
keyboard_hotkey(["ctrl","s"])
# Save dialog appears - filename box is focused
keyboard_type("C:\\Users\\jn03o\\Desktop\\out.txt")
keyboard_press("enter")
```

If your content contains non-ASCII characters, `keyboard_type` will return `"method": "paste"` and your clipboard will be overwritten. Save and restore the clipboard if it matters.

## Browser search and navigation

```
launch_app("edge")                            # or "chrome", or full exe path
wait_for_window("Edge", timeout_s=8)
keyboard_hotkey(["ctrl","l"])                 # focus URL bar
keyboard_type("https://example.com")
keyboard_press("enter")
wait_seconds(2)
screenshot(monitor_index=1)                   # verify the page loaded
```

For clicks **inside** the rendered page, use `use_real_cursor: true`. Prefer keyboard navigation (Tab, Enter, Page Down) when possible - those go through real keystrokes and work fine even in Chromium content.

If `find_text_on_screen` works on the host, you can do:

```
click_text("Sign in")
```

If OCR is broken, fall back to coord-based clicks with `use_real_cursor: true` for page-body targets.

## Drawing in MS Paint

```
launch_app("mspaint")
wait_for_window("Paint", timeout_s=8)

# Pick a brush from the ribbon - PostMessage is fine for toolbar
mouse_click(x=<toolbar_x>, y=<toolbar_y>)

# Canvas strokes - MUST use real cursor
mouse_drag(x1=500, y1=450, x2=1000, y2=800, use_real_cursor=True, duration_s=0.5)
mouse_drag(x1=500, y1=800, x2=1000, y2=450, use_real_cursor=True, duration_s=0.5)

# Save (Ctrl+S dialog flow):
keyboard_hotkey(["ctrl","s"])
wait_for_window("Save", timeout_s=4)
keyboard_type("C:\\Users\\jn03o\\Desktop\\out.png")
keyboard_press("enter")
```

The canvas window is the child window that ignores PostMessage. The ribbon, color palette, and File menu all accept PostMessage clicks normally.

## Calculator: 123 + 456

```
launch_app("calc")
wait_for_window("Calculator", timeout_s=6)
keyboard_type("123")
keyboard_press("add")           # named key for the + key
keyboard_type("456")
keyboard_press("enter")
screenshot_region(x=<calc_x>, y=<display_y>, w=400, h=120)   # read the display
```

## Long-running / autonomous flow

```
permission_set_bypass(enabled=True)            # tell the user first!
set_speed(duration_s=0.4)                      # slower so user can audit
set_showcase_mode(on=True)
record_screen_start(fps=10, monitor_index=1)
# -> returns {"path": "C:\\Users\\jn03o\\.win_computer_use\\recordings\\capture-YYYYMMDD-HHMMSS.mp4", ...}

# ... do work ...

record_screen_stop()
# -> returns {"path": "...", "elapsed_s": 7.63}

set_showcase_mode(on=False)
permission_set_bypass(enabled=False)           # restore safe default
```

The mp4 path is returned at both start and stop. If you want a known location, supply `path=...` to `record_screen_start`.

## macro_run for replayable sequences

Use this when you want one tool call that executes multiple steps deterministically (good for tight UI sequences where round-tripping per step is wasteful):

```
macro_run(steps=[
  {"tool": "mouse_move",    "args": {"x": 300, "y": 300, "duration_s": 0.2}, "wait_ms": 200},
  {"tool": "keyboard_press","args": {"key": "enter"},                         "wait_ms": 100},
  {"tool": "screenshot",    "args": {},                                       "wait_ms": 0},
])
```

Important details:

- Step `tool` is the **bare** tool name (`mouse_move`, not `mcp__win-computer-use__mouse_move`).
- `wait_ms` happens **after** each step.
- Result shape: `{"ok": true, "count": N, "results": [{"step": i, "tool": "...", "ok": bool, "result": {...}}, ...]}`. Iterate `results` to detect partial failures.
- Macro execution is sequential, not parallel.

## Read a file's content

```
read_text_file(path="C:\\path\\to\\file.txt", max_bytes=200000)
# -> {"ok": true, "size_bytes": 1234, "returned_bytes": 1234, "truncated": false, "text": "..."}
```

If `truncated: true`, the file was bigger than `max_bytes` and you only got a prefix. Re-call with a larger `max_bytes` if needed.

## HTTP fetch (no browser needed)

```
http_get(url="https://api.example.com/data.json", timeout_s=15, max_bytes=200000)
# -> {"ok": true, "url": "...", "status": 200, "content_type": "application/json", "bytes": 279, "text": "..."}
```

User-Agent sent: `win-computer-use/0.3`. Some sites may reject it; in that case download via a browser flow.

For binaries:

```
download_file(url="https://...", dest_path="C:\\Users\\...\\file.zip", timeout_s=60)
```

## List processes and find one

```
list_processes(name_contains="chrome")
# -> [{"pid": 10196, "name": "chrome.exe", "exe": "...", "cpu_percent": 0, "rss_mb": 58}, ...]
```

Pair with `kill_process(pid=...)` if you need to kill it. Be careful - this is destructive.

## Multi-monitor + DPI

```
list_monitors()
# -> [{"index": 0, "left": 0, "top": 0, "width": ..., "height": ..., "is_virtual": true},
#     {"index": 1, "left": 0, "top": 0, "width": ..., "height": ..., "is_virtual": false},
#     ...]
```

- Index 0 = full virtual desktop spanning all monitors. Mouse/screenshot coords are virtual-desktop-relative.
- Index 1+ = individual monitors.
- The server sets per-monitor DPI awareness (`SetProcessDpiAwareness(2)`), so coords from `list_windows` / `find_text_on_screen` match what mouse tools expect.
- For mixed-DPI setups, prefer per-monitor `screenshot_region` over a full virtual-desktop screenshot.

## Pixel-based wait (instead of OCR)

If you know the color of a "ready" pixel (e.g. a button turns green when an app is loaded):

```
wait_for_pixel_color(x=400, y=300, hex_color="#22C55E", tolerance=6, timeout_s=10)
# success: {"ok": true, ...}
# timeout: {"ok": false, "error": "timeout", "actual": "#3C3C3C"}
```

The `actual` field on timeout tells you what color the pixel actually was - useful for adjusting tolerance.

## Save a screenshot to disk

Use this when you want a persisted artifact and don't need the base64 inline:

```
screenshot_to_file(path="C:\\Users\\jn03o\\Desktop\\debug.png", monitor_index=1)
# -> {"ok": true, "path": "...", "full_width": 1920, "full_height": 1200}
```

This is much cheaper context-wise than `screenshot()` since no base64 is returned.

## Clipboard round-trip (and how to be polite)

If you need to type a long string and don't mind clobbering the clipboard:

```
saved = clipboard_get()
clipboard_set(text="long content here")
focus_window("Notepad")
keyboard_hotkey(["ctrl","v"])
clipboard_set(text=saved["text"])     # restore
```

Or just use `keyboard_type` and accept that Unicode triggers paste mode.
