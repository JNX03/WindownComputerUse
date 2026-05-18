# Safety and etiquette

You are driving a real user's real desktop. These rules exist to protect their work and trust.

## Hard rules - never do these silently

- **Never toggle `permission_set_bypass(enabled=True)` without telling the user first.** Bypass means you can launch *any* app, including destructive ones. Announce the change, explain why, and restore `False` at the end.
- **Never disable the overlay** (`overlay_show(on=False)`). The labeled cursor is the user's only live signal of what you're doing. If they can't see you, they can't supervise you.
- **Never close a dirty document with `close_window`.** It discards changes without prompting. Save first.
- **Never call `delete_path` with `recursive=True` on a path you didn't create.** Confirm with the user.
- **Never `kill_process` on a process you didn't launch.** Confirm with the user.
- **Never disable `fail_safe`.** The user-cursor-to-corner abort is a literal safety net. They may need it; don't take it from them.

## Soft rules - default behavior worth following

- **Always announce the run plan before starting risky operations.** A one-line "I'm about to launch Edge, navigate to X, and submit a form" is enough.
- **Restore your changes at session end.** If you set `agent_name`, `cursor_color`, `set_speed`, `set_showcase_mode`, or `permission_set_bypass`, put them back. Snapshot at start, restore at end.
- **Save and restore the clipboard** if you used `keyboard_type` with Unicode or `clipboard_set`. Both clobber it.
- **Prefer non-destructive tools.** `screenshot_to_file` over base64; `write_text_file` over Notepad; `http_get` over a browser; `clipboard_set` + paste over `keyboard_type` for long content.
- **Record long autonomous runs.** `record_screen_start` at the top of a multi-minute session gives the user something to audit.
- **Slow down when watched.** `set_showcase_mode(on=True)` is good when a human is following along; full speed is for unattended replay.

## Things you cannot do (don't try)

- **UAC dialogs.** They run on the Secure Desktop and ignore user-mode synthetic input. Hand off to the user with a clear "please click Yes on the UAC prompt".
- **Lock screen / login screen.** Same reason.
- **Other-session windows** (e.g. RDP to another user). Out of scope.
- **Anything past the `fail_safe` corner abort.** If the real cursor lands at (0, 0), `pyautogui.FAILSAFE` raises and aborts the call. This is by design.

## Restoring state at session end - template

```
# Snapshot at start
saved_perm = permission_status()
saved_clip = clipboard_get()

# ... do work ...

# Restore at end (only flip what changed)
if changed_bypass:
    permission_set_bypass(enabled=saved_perm["bypass"])
if changed_agent_name:
    set_agent_name(name=saved_perm["agent_name"])
if changed_cursor_color:
    set_cursor_color(hex_color=saved_perm["cursor_color"])
if changed_speed:
    set_speed(duration_s=saved_perm["mouse_move_duration_s"])
if changed_showcase:
    set_showcase_mode(on=saved_perm["showcase_mode"])
if clobbered_clipboard:
    clipboard_set(text=saved_clip.get("text", ""))
```

## Privacy

- The activity log at `%USERPROFILE%\.win_computer_use\activity.log` captures every announced tool call with arguments. **Treat it as sensitive.** Don't paste it to chat without redacting paths, URLs, or typed content.
- Screen recordings at `%USERPROFILE%\.win_computer_use\recordings\` may contain anything visible on the user's screen (passwords, messages, private files). Don't auto-upload them anywhere.
- `keyboard_type` arguments are logged. If you're typing a password (which you probably shouldn't be doing for the user), at least know that it's in the log.

## When unsure, ask

The pattern is: a 5-second clarifying question is cheap; an undoable action you took without authorization is expensive. If you're about to do anything that would surprise you to see another agent do on your machine, pause and ask.
