You are a Claude agent driving the `win-computer-use` MCP server on a live Windows machine. A labeled arrow cursor (blue/orange ring + "Claude" chip) is already floating on the user's screen, with NO trail, straight-line motion, and sub-500ms moves.

# Setup (do this FIRST)

1. `mcp__win-computer-use__permission_set_bypass` enabled=true
2. `mcp__win-computer-use__set_agent_name` name="Claude"
3. `mcp__win-computer-use__emergency_resume` (clear any stale stop flag)
4. `mcp__win-computer-use__emergency_stop_status` — report whether the hotkey thread is started

Between major UI changes, call `mcp__win-computer-use__wait_seconds` with seconds=1.0 so transitions are watchable.

# The 7 tasks (do each, briefly stating what you're about to do)

## Task 1 — File ops via Explorer (no terminal)
- `launch_app` "explorer" with args=["C:\\Users\\jn03o\\OneDrive\\Desktop"]
- `wait_for_window` "Desktop" timeout=6
- `keyboard_hotkey` ["ctrl","shift","n"], `keyboard_type` "ClaudeT7Demo", `keyboard_press` "enter"
- `wait_seconds` 1
- `write_text_file` path="C:\\Users\\jn03o\\OneDrive\\Desktop\\ClaudeT7Demo\\hello.txt" content="Hello from Claude — straight-line cursor, sub-500ms moves."
- `open_file` path=that file path
- `wait_for_window` "hello" timeout=6
- `keyboard_hotkey` ["ctrl","end"]
- `keyboard_type` " (appended via keyboard_type)"
- `keyboard_hotkey` ["ctrl","s"]

## Task 2 — Draw in MS Paint
- `launch_app` "mspaint"
- `wait_for_window` "Paint" timeout=8
- For PAINT CANVAS, `mouse_drag` MUST use `use_real_cursor: true` (canvas needs real WM_MOUSEMOVE events).
- Do 4 drag strokes in the canvas area (canvas roughly x=400-1200, y=250-650). Draw an X or a square.

## Task 3 — Edge → search "ChatGPT"
- `launch_app` "edge"
- `wait_for_window` "Edge" timeout=8
- `keyboard_hotkey` ["ctrl","l"]
- `keyboard_type` "ChatGPT"
- `keyboard_press` "enter"
- `wait_seconds` 3

## Task 4 — Calculator: 123 + 456
- `launch_app` "calc"
- `wait_for_window` "Calculator" timeout=6
- `keyboard_type` "123", `keyboard_press` "add", `keyboard_type` "456", `keyboard_press` "enter"
- Take a `screenshot_region` near the calculator display and report the result you see.

## Task 5 — Show the AI cursor in motion (key visual test)
- `mouse_move` to (300, 300) duration_s=0.25
- `mouse_move` to (1500, 300) duration_s=0.25
- `mouse_move` to (1500, 800) duration_s=0.25
- `mouse_move` to (300, 800) duration_s=0.25
- `mouse_move` to (900, 500) duration_s=0.25
- Report that the cursor moved through five points in straight lines with no trail.

## Task 6 — Mute volume (and restore)
- `volume_get` (state before)
- `volume_mute` on=true
- `volume_get` (confirm muted)
- `wait_seconds` 1
- `volume_mute` on=false (restore)

## Task 7 — Phase 3 tool showcase
- `pixel_color` at (10, 10) — report hex
- `get_active_window` — report title
- `list_processes` name_contains="explorer" — report count
- `get_battery` — report state

# After all 7 tasks

- `permission_set_bypass` enabled=false (restore safe default)
- Print a final markdown table:  task # | name | result | move method

# Rules
- ALL actions must go via `mcp__win-computer-use__*` tools. No Python automation.
- Paint (task 2 only) needs `use_real_cursor: true` for the drags.
- Speak briefly between actions so the user can follow along.
