# Emergency stop discipline

The "panic button" for the user. Take it seriously - both the mechanism and the etiquette.

## What it is

A Win32 `RegisterHotKey` background thread listening for `Ctrl+Shift+X` (configurable). When the user presses it:

1. A flag in `state.json` flips to `emergency_stopped: true`.
2. The `@announced` decorator wrapping every input-bearing tool checks this flag.
3. Subsequent `mouse_*` / `keyboard_*` / `mouse_drag` / etc. calls short-circuit and refuse to act until the flag is cleared.
4. Non-input tools (`screenshot`, `get_state`, `list_windows`, etc.) still work - the user can keep inspecting state.

The Electron manager also has a "STOP" button that flips the same flag.

## Checking it on session start

```
emergency_stop_status()
# -> {"started": true|false, "stopped": true|false, "combo": "ctrl+shift+x"}
```

Three things to read:

- **`started`**: did the hotkey thread successfully register? If `false`, the hotkey **will not work**. The Win32 `RegisterHotKey` call can fail silently if another app already claimed the combo, if the message loop didn't initialize, or for various permission reasons.
- **`stopped`**: is the stop flag currently set?
- **`combo`**: what combo is currently armed (`ctrl+shift+x` by default).

## What to do if `started: false`

This was observed during skill authoring on a live machine. **It means the user's panic button doesn't work.** You have two responsibilities:

1. **Tell the user immediately**, before doing anything destructive. Sample message:
   > Heads up: the Ctrl+Shift+X emergency hotkey isn't currently armed on this MCP server (the `RegisterHotKey` thread didn't start). If you need to stop me, please use the STOP button in the Electron manager, or close the manager / MCP client.

2. **Be more conservative.** Lean toward `permission_set_bypass(enabled=False)` for destructive sessions, slow `set_speed` so the user has time to react, and pause at decision points.

## What to do if `stopped: true`

The user (or a previous agent) pressed the hotkey. **Do not silently `emergency_resume()`.** That defeats the purpose.

Correct flow:

1. Report to the user: "Looks like the emergency stop is engaged. Should I resume?"
2. Wait for explicit confirmation.
3. `emergency_resume()` only after they say yes.

```
emergency_resume()
# -> {"ok": true, "stopped": false}
```

## Clearing stale flags at session start

It's fine (recommended, even) to clear the flag at session start if you're certain there's no in-progress operation to abort:

```
get_state()                         # check if anything looks in-flight
emergency_stop_status()             # was the previous session stopped?
emergency_resume()                  # clear stale flag from a prior session
```

The point is: clearing at start is fine; clearing mid-session after the user just stopped you is not.

## What the stop flag does NOT freeze

These tools keep working when `stopped: true` - by design, so the user and you can investigate:

- All `screenshot*` tools
- `get_state`, `get_virtual_cursor`, `get_cursor_position`, `get_active_window`, `get_battery`
- `list_*` tools (`list_windows`, `list_monitors`, `list_processes`, `list_directory`)
- `pixel_color`
- `permission_status`, `emergency_stop_status`
- `read_text_file`
- `clipboard_get`

What's frozen:

- All `mouse_*` (move, click, drag, scroll, double-click, down/up)
- All `keyboard_*` (type, press, hotkey, down/up)
- `launch_app`, `focus_window`, `close_window`, `move_window`, `minimize/maximize/restore_window`
- `click_text`, `find_text_on_screen` clicking helpers (the find side may work; the click side won't)
- `macro_run`
- `volume_*`, `text_to_speech`
- `record_screen_start` / `record_screen_stop` (so the user can audit what happened)

Treat the freeze as a guideline, not a guarantee - if a tool isn't listed above, assume the safer behavior (frozen).

## Best-practice flow for risky operations

```
emergency_stop_status()            # confirm armed
permission_set_bypass(enabled=True)
set_speed(duration_s=0.4)          # slow enough to react
set_showcase_mode(on=True)
record_screen_start()              # forensic trail

# ... risky work, with screenshots between steps ...

record_screen_stop()
set_showcase_mode(on=False)
permission_set_bypass(enabled=False)
```

The recording is your post-mortem if anything goes wrong. The slow speed gives the user time to hit the hotkey.

## Why this matters

Unlike a remote agent on a sandbox, you're driving the user's actual desktop. The emergency stop is the contract that makes that acceptable. Honoring it - and being honest when it's broken - is non-negotiable.
