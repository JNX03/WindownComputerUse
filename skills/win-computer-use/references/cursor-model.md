# Cursor model - PostMessage vs real cursor

The single most important concept in this MCP. Reading this once will save you a lot of "why did my click do nothing" debugging.

## What's actually happening

The MCP renders an **independent virtual cursor** as a labeled tkinter overlay window. The overlay is click-through and always-on-top. Your actions update the virtual cursor position; whether they also produce real input depends on `use_real_cursor`.

Two delivery mechanisms:

### PostMessage (default)
- The server sends `WM_LBUTTONDOWN` / `WM_LBUTTONUP` / `WM_MOUSEMOVE` messages directly to the target window's HWND via Win32 `PostMessage`.
- **The user's real cursor is not moved.** The overlay animates instead.
- Many Win32 apps process these messages as if a real click happened, but a growing class of modern apps (anything that uses raw input, DirectX, or its own hit-testing pipeline) ignores them entirely.

### Real cursor (`use_real_cursor: true`)
- The server briefly drives the real Windows cursor with `pyautogui` to the target, performs the click, then can release.
- Visible to the user. Disruptive if they were using the machine.
- Works on anything that responds to real input - which means everything.

## Where each one works (confirmed)

| Target | PostMessage | Real cursor |
|---|---|---|
| Notepad text area | works | works |
| Win32 menu bar, classic dialog buttons | works | works |
| Explorer file pane | works | works |
| App ribbon / toolbar (Paint, Office) | works | works |
| Paint canvas (drawing strokes) | **silent no-op** | works |
| Edge / Chrome page body (Chromium content) | **silent no-op** | works |
| Edge / Chrome URL bar | unreliable (Chromium UI) | works |
| Games, DirectX surfaces | **silent no-op** | works |
| Full-screen apps | **silent no-op** | works |

"Silent no-op" means the tool returns `ok: true` with `"method": "postmessage"` and nothing visible happens on screen. This was verified on Paint canvas during skill authoring: PostMessage drag returned success, but the next screenshot showed no stroke; the same drag with `use_real_cursor: true` drew the expected line.

## The response field that tells you which path ran

Every mouse tool result includes a `method` field. Trust it more than your assumptions.

```
mouse_drag(..., use_real_cursor=true)
  -> {"ok": true, "method": "real-cursor", "from": [...], "to": [...]}

mouse_drag(..., use_real_cursor=false)
  -> {"ok": true, "method": "postmessage", "hwnd": 3803292, "from": [...], "to": [...]}
```

The PostMessage variant also returns the target `hwnd` it found - useful for debugging "is it even hitting the right window".

## Recovery pattern (the canonical one)

```
1. mouse_click(x=..., y=...)                            # default PostMessage
2. screenshot_region(x=..., y=..., w=..., h=...)        # verify
3. If nothing changed:
     mouse_click(x=..., y=..., use_real_cursor=true)    # retry
4. screenshot_region(...)                               # verify again
```

This pattern works for any of the mouse tools. The cost of the extra screenshot is small; the cost of assuming a silent click landed is large.

## When to skip PostMessage entirely

If the *first* click of a session is going into a Chromium page body or a game canvas, just start with `use_real_cursor: true`. Don't burn a round trip on a PostMessage attempt you already know will fail.

For Paint specifically: toolbar clicks (tool selection, color picker, ribbon buttons) stay on PostMessage; only the canvas drags need real cursor. Mixing them in one workflow is fine.

## Cursor speed and showcase mode

`mouse_move_duration_s` (settable via `set_speed(duration_s=...)`) controls how long virtual-cursor moves take. The animation follows a cubic Bezier with subtle jitter, not a straight line. Lower values feel snappier; higher values are easier for a user to watch (good for demos and audits).

`set_showcase_mode(on=true)` bumps `mouse_move_duration_s` to 0.6 and is the recommended setting if a human will be watching the run.

## Things the cursor model does NOT change

- `keyboard_*` tools are unaffected by the PostMessage/real-cursor distinction - they use SendInput-style real keystrokes (or clipboard paste on Unicode).
- `screenshot*` reads the framebuffer directly via `mss`; no cursor activity involved.
- `find_text_on_screen` / `click_text` use OCR; the click itself goes through PostMessage by default.
- `focus_window` uses Win32 `SetForegroundWindow` and ignores the cursor model entirely.
