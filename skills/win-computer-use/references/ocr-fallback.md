# OCR backend - what it is, when it breaks, what to do

The `find_text_on_screen` and `click_text` tools use the Windows built-in OCR engine via `Windows.Media.Ocr`. This is fast, multilingual, and requires no Tesseract install. But the Python wrapper has a fragile dependency chain.

## What "OCR failed" actually means

Observed during skill authoring:

```
find_text_on_screen(text="anything")
  -> {"ok": false, "error": "OCR failed: No module named 'winrt.windows.globalization'"}
```

`winrt-Windows.Media.Ocr` (which **is** in `requirements.txt`) depends transitively on `winrt-Windows.Globalization` (which **is not**). On a fresh install you can end up with the parent installed but the dependency missing. Both `find_text_on_screen` and `click_text` will fail with the same error.

`wait_for_text` doesn't surface this error - it just times out. So if `wait_for_text` keeps timing out on visible text, suspect OCR is broken.

## Quick repair

In the same Python env that the MCP server runs in:

```
py -3.12 -m pip install winrt-Windows.Globalization
```

Or pin the full set in `requirements.txt`:

```
winrt-Windows.Foundation>=2.3.0
winrt-Windows.Globalization>=2.3.0
winrt-Windows.Graphics.Imaging>=2.3.0
winrt-Windows.Media.Ocr>=2.3.0
winrt-Windows.Storage.Streams>=2.3.0
```

Then restart the MCP server. Test:

```
find_text_on_screen(text="File")     # against any visible window with a "File" menu
```

A working response looks like:

```
{"ok": true, "matches": [{"x": ..., "y": ..., "w": ..., "h": ..., "text": "File"}], ...}
```

## Fallback playbook when OCR is unavailable

If you can't fix the environment (e.g. you don't have permission to install packages), here is the priority order:

### 1. Keyboard shortcuts
Often faster than clicking labels even when OCR works:

| Goal | Shortcut |
|---|---|
| Focus URL bar (browser) | `Ctrl+L` |
| Save | `Ctrl+S` |
| Open | `Ctrl+O` |
| Close window | `Alt+F4` |
| Switch app | `Alt+Tab` |
| New tab | `Ctrl+T` |
| Address bar in Explorer | `Ctrl+L` or `Alt+D` |
| Menu bar | `Alt` |

### 2. Tab-and-Enter navigation
For dialogs: `keyboard_press("tab")` to walk focus, `keyboard_press("enter")` or `keyboard_press("space")` to activate. Works in classic Win32 dialogs and most Electron apps.

### 3. Pixel-color waits
If a button changes color when ready (or a status indicator flips), `wait_for_pixel_color(x, y, hex_color)` lets you sync without OCR:

```
wait_for_pixel_color(x=400, y=300, hex_color="#22C55E", tolerance=8, timeout_s=10)
```

On timeout you get `actual: "#<hex>"` so you can tune.

### 4. Coord-based clicks from a screenshot
Take a screenshot, reason about coordinates, click. Verify with a follow-up screenshot. Slow but reliable.

```
screenshot_region(x=..., y=..., w=600, h=200)     # narrow region around the target
# reason about pixel coords from the image
mouse_click(x=..., y=..., use_real_cursor=True)   # real cursor for any non-Win32 surface
screenshot_region(...)                            # verify
```

### 5. Read the window title + structure
`list_windows()` gives you titles, positions, and active/minimized state. Often enough to drive an app without clicking individual labels.

## When OCR works, use it well

- **Constrain the search region.** A full-screen OCR pass is slow and prone to false matches; `region={"x":..,"y":..,"w":..,"h":..}` cuts both.
- **Use distinctive substrings.** OCR'ing for `"OK"` matches everywhere; `"OK, continue"` is rare.
- **Lowercase fallback.** If `click_text("Save")` misses, try `click_text("save")` - OCR can mis-case.
- **Re-screenshot after a click.** OCR may have matched a different "Save" than the one you wanted.
