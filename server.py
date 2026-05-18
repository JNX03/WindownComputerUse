"""Win:Computer Use — MCP server entry point.

Stdio MCP server exposing mouse/keyboard/screen/window/system tools for Windows.
"""
from __future__ import annotations

import atexit
import base64
import ctypes
import os
import subprocess
import sys
import threading
import time
from typing import Optional

from mcp.server.fastmcp import FastMCP, Image
import pyautogui

from win_computer_use import (
    extras,
    hotkey,
    keyboard_io,
    macro,
    mouse,
    ocr as ocr_tools,
    permission,
    record,
    state,
    system as sys_tools,
    vision,
    window as win_tools,
)


# Make the process DPI-aware so coordinates from mss match what pyautogui sends.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# Apply config knobs to pyautogui.
_cfg = permission.load_config()
pyautogui.FAILSAFE = bool(_cfg.get("fail_safe", True))


mcp = FastMCP("win-computer-use")


# ----- Overlay subprocess + heartbeat ---------------------------------------

_overlay_proc: Optional[subprocess.Popen] = None


def _start_overlay() -> None:
    global _overlay_proc
    if os.environ.get("WCU_DISABLE_OVERLAY"):
        return
    if not permission.load_config().get("overlay_enabled", True):
        return
    if _overlay_proc and _overlay_proc.poll() is None:
        return
    try:
        # CREATE_NEW_CONSOLE forces the child into its own console group; combined
        # with CREATE_NO_WINDOW it gives us a child that doesn't share our stdio,
        # without the strict detachment that breaks tkinter.
        log_path = permission.CONFIG_DIR / "overlay.log"
        permission.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        log_fh = open(log_path, "ab", buffering=0)
        CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        # If a standalone overlay is already running (its PID is in state.json
        # and the process is alive), don't spawn a second one. Verify with
        # GetExitCodeProcess — OpenProcess returns a handle for recently-exited
        # PIDs too, so the old `if h:` check let stale PIDs block respawns and
        # produced the "no cursor" bug.
        existing_pid = state.load().get("overlay_subprocess_pid")
        if existing_pid:
            try:
                import ctypes as _c
                h = _c.windll.kernel32.OpenProcess(0x1000, False, int(existing_pid))
                if h:
                    exit_code = _c.c_ulong(0)
                    ok = _c.windll.kernel32.GetExitCodeProcess(h, _c.byref(exit_code))
                    _c.windll.kernel32.CloseHandle(h)
                    if ok and exit_code.value == 259:  # STILL_ACTIVE
                        print(f"[server] overlay already running (pid {existing_pid}), skipping spawn",
                              file=sys.stderr)
                        return
            except Exception:
                pass
        _overlay_proc = subprocess.Popen(
            [sys.executable, "-m", "win_computer_use.overlay", "--watch-parent-pid", str(os.getpid())],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            stdin=subprocess.DEVNULL,
            stdout=log_fh,
            stderr=log_fh,
            creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
            close_fds=False,
        )
    except Exception as e:
        print(f"[server] overlay spawn failed: {e}", file=sys.stderr)


def _stop_overlay() -> None:
    if _overlay_proc and _overlay_proc.poll() is None:
        try:
            _overlay_proc.terminate()
        except Exception:
            pass


def _heartbeat_loop() -> None:
    pid = os.getpid()
    while True:
        try:
            state.sync_from_config()
            state.heartbeat(pid)
        except Exception:
            pass
        time.sleep(2.0)


# Sync state from config, write our PID, seed virtual cursor at the real cursor,
# start overlay + heartbeat + hotkey.
state.sync_from_config()
state.heartbeat(os.getpid())
try:
    _p = pyautogui.position()
    state.set_virtual_cursor(int(_p.x), int(_p.y), pressed=False)
except Exception:
    pass
_start_overlay()
threading.Thread(target=_heartbeat_loop, daemon=True).start()
hotkey.start()
atexit.register(_stop_overlay)


# ---- Vision ----------------------------------------------------------------

@mcp.tool()
def screenshot(monitor_index: int = 0) -> dict:
    """Capture the screen and return a base64 PNG.

    monitor_index 0 = full virtual desktop spanning all monitors;
    1, 2, ... = individual monitors. Use list_monitors to discover them.
    """
    return vision.screenshot(monitor_index=monitor_index)


@mcp.tool()
def screenshot_region(x: int, y: int, w: int, h: int) -> dict:
    """Capture a specific rectangle of the screen as base64 PNG."""
    return vision.screenshot_region(x, y, w, h)


@mcp.tool()
def list_monitors() -> list[dict]:
    """List physical monitors plus the virtual-desktop bounds (index 0)."""
    return vision.list_monitors()


@mcp.tool()
def list_windows(only_visible: bool = True) -> list[dict]:
    """Enumerate open windows with titles, positions, and states."""
    return vision.list_windows(only_visible=only_visible)


@mcp.tool()
def get_cursor_position() -> dict:
    """Return current mouse cursor coordinates."""
    return vision.get_cursor_position()


# ---- Mouse -----------------------------------------------------------------

@mcp.tool()
def mouse_move(x: int, y: int, duration_s: Optional[float] = None) -> dict:
    """Move the cursor to (x, y) with smooth motion. duration_s overrides config."""
    return mouse.mouse_move(x, y, duration_s=duration_s)


@mcp.tool()
def mouse_click(
    x: Optional[int] = None,
    y: Optional[int] = None,
    button: str = "left",
    clicks: int = 1,
    interval_s: float = 0.05,
    duration_s: Optional[float] = None,
    use_real_cursor: bool = False,
) -> dict:
    """Click at (x, y) or current virtual-cursor position.

    By default uses PostMessage so the user's real cursor is not touched.
    Pass use_real_cursor=True for apps that ignore synthetic clicks (Chromium
    inner content, games, anything DirectX).
    """
    return mouse.mouse_click(
        x=x, y=y, button=button, clicks=clicks, interval_s=interval_s,
        duration_s=duration_s, use_real_cursor=use_real_cursor,
    )


@mcp.tool()
def mouse_double_click(x: int, y: int, button: str = "left", use_real_cursor: bool = False) -> dict:
    """Double-click at (x, y). use_real_cursor=True for Chromium/games."""
    return mouse.mouse_double_click(x, y, button=button, use_real_cursor=use_real_cursor)


@mcp.tool()
def mouse_drag(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    button: str = "left",
    duration_s: Optional[float] = None,
    use_real_cursor: bool = False,
) -> dict:
    """Press at (x1, y1), drag to (x2, y2), release.

    Pass use_real_cursor=True for MS Paint, drawing apps, games — anywhere
    the canvas needs real mouse-down/up events. Default uses PostMessage,
    which doesn't touch the user's real cursor.
    """
    return mouse.mouse_drag(
        x1, y1, x2, y2, button=button, duration_s=duration_s,
        use_real_cursor=use_real_cursor,
    )


@mcp.tool()
def mouse_scroll(
    clicks: int,
    x: Optional[int] = None,
    y: Optional[int] = None,
    duration_s: Optional[float] = None,
    use_real_cursor: bool = False,
) -> dict:
    """Scroll the wheel. Positive = up, negative = down.

    Pass duration_s to smooth the scroll over time (clicks delivered one tick
    at a time). use_real_cursor=True for apps that need a real wheel event.
    """
    return mouse.mouse_scroll(clicks, x=x, y=y, duration_s=duration_s, use_real_cursor=use_real_cursor)


@mcp.tool()
def mouse_move_path(
    points: list,
    duration_s_per_segment: Optional[float] = None,
) -> dict:
    """Animate the AI cursor through a list of [x, y] waypoints.

    Each segment uses the same spring + Bezier animation as mouse_move, so a
    multi-point path produces a continuous string of smooth arcs — handy for
    tracing gestures or visiting a sequence of UI targets in one tool call.
    """
    return mouse.mouse_move_path(points, duration_s_per_segment=duration_s_per_segment)


@mcp.tool()
def mouse_hover(
    x: int,
    y: int,
    dwell_ms: int = 400,
    duration_s: Optional[float] = None,
) -> dict:
    """Move to (x, y) and dwell for dwell_ms — triggers tooltips and hover UI."""
    return mouse.mouse_hover(x, y, dwell_ms=dwell_ms, duration_s=duration_s)


@mcp.tool()
def mouse_down(
    x: Optional[int] = None,
    y: Optional[int] = None,
    button: str = "left",
    duration_s: Optional[float] = None,
    use_real_cursor: bool = False,
) -> dict:
    """Press a mouse button without releasing it. Pair with mouse_up for custom
    drag patterns or hold-while-typing flows.

    PostMessage by default (real cursor untouched). Pass use_real_cursor=True
    for apps that ignore synthetic input — the real cursor will stay at the
    target until mouse_up is called (use the real_pos_before value returned
    here to restore it)."""
    return mouse.mouse_down(
        x=x, y=y, button=button, duration_s=duration_s, use_real_cursor=use_real_cursor,
    )


@mcp.tool()
def mouse_up(
    x: Optional[int] = None,
    y: Optional[int] = None,
    button: str = "left",
    use_real_cursor: bool = False,
    real_pos_before: Optional[list] = None,
) -> dict:
    """Release a previously pressed mouse button. If use_real_cursor was true
    on mouse_down, pass the same real_pos_before list back to restore the
    user's cursor."""
    return mouse.mouse_up(
        x=x, y=y, button=button, use_real_cursor=use_real_cursor,
        real_pos_before=real_pos_before,
    )


# ---- Keyboard --------------------------------------------------------------

@mcp.tool()
def keyboard_type(text: str, interval_s: float = 0.02) -> dict:
    """Type a string. Unicode falls back to clipboard paste."""
    return keyboard_io.keyboard_type(text, interval_s=interval_s)


@mcp.tool()
def keyboard_press(key: str) -> dict:
    """Press a single key. Examples: 'enter', 'tab', 'esc', 'win', 'f5', 'a'."""
    return keyboard_io.keyboard_press(key)


@mcp.tool()
def keyboard_hotkey(keys: list[str]) -> dict:
    """Press a key combo. Example: ['ctrl','c'], ['win','d'], ['alt','tab']."""
    return keyboard_io.keyboard_hotkey(keys)


@mcp.tool()
def keyboard_key_down(key: str) -> dict:
    """Hold a key down (pair with keyboard_key_up)."""
    return keyboard_io.keyboard_key_down(key)


@mcp.tool()
def keyboard_key_up(key: str) -> dict:
    """Release a held key."""
    return keyboard_io.keyboard_key_up(key)


# ---- Window / app ----------------------------------------------------------

@mcp.tool()
def launch_app(name_or_path: str, args: Optional[list[str]] = None, cwd: Optional[str] = None) -> dict:
    """Launch an app by alias ('paint','edge','calc','notepad','explorer') or full path."""
    return win_tools.launch_app(name_or_path, args=args, cwd=cwd)


@mcp.tool()
def focus_window(title_substring: str) -> dict:
    """Bring the first window whose title contains the substring to the foreground."""
    return win_tools.focus_window(title_substring)


@mcp.tool()
def open_file(path: str) -> dict:
    """Open a file with its default Windows handler."""
    return win_tools.open_file(path)


# ---- System ----------------------------------------------------------------

@mcp.tool()
def volume_set(level_0_to_100: int) -> dict:
    """Set master volume level (0-100)."""
    return sys_tools.volume_set(level_0_to_100)


@mcp.tool()
def volume_get() -> dict:
    """Read master volume level and mute state."""
    return sys_tools.volume_get()


@mcp.tool()
def volume_mute(on: Optional[bool] = None) -> dict:
    """Mute/unmute master volume. If 'on' is None, toggle."""
    return sys_tools.volume_mute(on=on)


@mcp.tool()
def wait_seconds(seconds: float) -> dict:
    """Sleep N seconds — useful between launching an app and screenshotting."""
    return sys_tools.wait(seconds)


@mcp.tool()
def clipboard_get() -> dict:
    """Get current clipboard text."""
    return sys_tools.clipboard_get()


@mcp.tool()
def clipboard_set(text: str) -> dict:
    """Set clipboard text."""
    return sys_tools.clipboard_set(text)


# ---- Permission management -------------------------------------------------

@mcp.tool()
def permission_status() -> dict:
    """Return the current permission config."""
    return permission.load_config()


@mcp.tool()
def permission_set_bypass(enabled: bool) -> dict:
    """Enable or disable bypass mode (no per-app approval)."""
    return permission.set_bypass(enabled)


@mcp.tool()
def permission_add_allowed_app(app_name: str) -> dict:
    """Add an app exe name (e.g. 'spotify.exe') to the allowlist."""
    return permission.add_allowed_app(app_name)


# ---- Phase 2 — visibility & UX --------------------------------------------

@mcp.tool()
def set_agent_name(name: str) -> dict:
    """Rename the labeled-cursor overlay (e.g. 'Claude', 'Agent', 'Bot')."""
    cfg = permission.load_config()
    cfg["agent_name"] = str(name)
    permission.save_config(cfg)
    state.sync_from_config()
    return {"ok": True, "agent_name": cfg["agent_name"]}


@mcp.tool()
def set_cursor_color(hex_color: str) -> dict:
    """Set the overlay ring color (e.g. '#3B82F6', '#EF4444')."""
    s = hex_color.strip()
    if not s.startswith("#") or len(s) not in (4, 7):
        return {"ok": False, "error": "expected hex like '#3B82F6'"}
    cfg = permission.load_config()
    cfg["cursor_color"] = s
    permission.save_config(cfg)
    state.sync_from_config()
    return {"ok": True, "cursor_color": s}


@mcp.tool()
def set_speed(duration_s: float) -> dict:
    """Set default mouse_move_duration_s. 0.05 = fast, 0.6 = visible/showcase."""
    d = max(0.0, float(duration_s))
    cfg = permission.load_config()
    cfg["mouse_move_duration_s"] = d
    permission.save_config(cfg)
    return {"ok": True, "mouse_move_duration_s": d}


@mcp.tool()
def set_showcase_mode(on: bool) -> dict:
    """Enable slower, watchable motion (also bumps mouse_move_duration_s to 0.6)."""
    cfg = permission.load_config()
    cfg["showcase_mode"] = bool(on)
    if on:
        cfg["mouse_move_duration_s"] = max(0.5, float(cfg.get("mouse_move_duration_s", 0.6)))
    permission.save_config(cfg)
    return {"ok": True, "showcase_mode": cfg["showcase_mode"], "duration_s": cfg["mouse_move_duration_s"]}


@mcp.tool()
def overlay_show(on: bool) -> dict:
    """Toggle the labeled-cursor overlay. Persists to config."""
    cfg = permission.load_config()
    cfg["overlay_enabled"] = bool(on)
    permission.save_config(cfg)
    state.sync_from_config()
    if on:
        _start_overlay()
    return {"ok": True, "overlay_enabled": bool(on)}


@mcp.tool()
def find_text_on_screen(text: str, region: Optional[dict] = None) -> dict:
    """OCR the screen (or a region) and return bounding boxes of matches for `text`.

    region: {"x": int, "y": int, "w": int, "h": int} in screen coords, or omit for full screen.
    """
    return ocr_tools.find_text_on_screen(text, region=region)


@mcp.tool()
def click_text(text: str, button: str = "left", region: Optional[dict] = None) -> dict:
    """Find text via OCR, then click the first match's center."""
    return ocr_tools.click_text(text, button=button, region=region)


@mcp.tool()
def record_screen_start(path: Optional[str] = None, fps: int = 10, monitor_index: int = 1) -> dict:
    """Start recording the screen to an mp4 file. Returns the path."""
    return record.record_screen_start(path=path, fps=fps, monitor_index=monitor_index)


@mcp.tool()
def record_screen_stop() -> dict:
    """Stop the active screen recording and finalize the mp4."""
    return record.record_screen_stop()


@mcp.tool()
def macro_run(steps: list[dict]) -> dict:
    """Run a sequence of tool calls.

    Each step: {"tool": "mouse_move", "args": {"x":100,"y":200}, "wait_ms": 500}
    """
    return macro.macro_run(steps)


@mcp.tool()
def emergency_stop_status() -> dict:
    """Return whether the emergency-stop hotkey has been pressed and the current combo."""
    return hotkey.status()


@mcp.tool()
def emergency_resume() -> dict:
    """Clear the emergency-stop flag so input tools resume working."""
    return hotkey.resume()


@mcp.tool()
def get_state() -> dict:
    """Return the live state.json — agent name, last action, heartbeat, emergency flag."""
    return state.load()


# ---- Phase 3 — broader tooling --------------------------------------------

@mcp.tool()
def get_virtual_cursor() -> dict:
    """Return the AI's virtual cursor position {x, y, pressed}."""
    return extras.get_virtual_cursor()


@mcp.tool()
def mouse_move_relative(dx: int, dy: int, duration_s: Optional[float] = None) -> dict:
    """Move the AI cursor by a delta from its current position (no real-cursor disturbance)."""
    s = state.load()
    return mouse.mouse_move(
        int(s.get("virtual_cursor_x", 0)) + int(dx),
        int(s.get("virtual_cursor_y", 0)) + int(dy),
        duration_s=duration_s,
    )


@mcp.tool()
def pixel_color(x: int, y: int) -> dict:
    """Return the RGB/hex color of the pixel at (x, y)."""
    return extras.pixel_color(x, y)


@mcp.tool()
def wait_for_pixel_color(x: int, y: int, hex_color: str, timeout_s: float = 10.0, tolerance: int = 6) -> dict:
    """Block until the pixel at (x,y) matches hex_color within tolerance, or timeout."""
    return extras.wait_for_pixel_color(x, y, hex_color, timeout_s=timeout_s, tolerance=tolerance)


@mcp.tool()
def wait_for_window(title_substring: str, timeout_s: float = 10.0) -> dict:
    """Block until a window whose title contains substring exists."""
    return extras.wait_for_window(title_substring, timeout_s=timeout_s)


@mcp.tool()
def wait_for_text(text: str, timeout_s: float = 10.0, region: Optional[dict] = None) -> dict:
    """Block until OCR finds text on screen (optionally in a region)."""
    return extras.wait_for_text(text, timeout_s=timeout_s, region=region)


@mcp.tool()
def get_active_window() -> dict:
    """Title + bounds of the foreground window."""
    return extras.get_active_window()


@mcp.tool()
def close_window(title_substring: str) -> dict:
    """Close the first window matching the substring."""
    return extras.close_window(title_substring)


@mcp.tool()
def move_window(title_substring: str, x: int, y: int, w: int, h: int) -> dict:
    """Move/resize a window."""
    return extras.move_window(title_substring, x, y, w, h)


@mcp.tool()
def minimize_window(title_substring: str) -> dict:
    return extras.minimize_window(title_substring)


@mcp.tool()
def maximize_window(title_substring: str) -> dict:
    return extras.maximize_window(title_substring)


@mcp.tool()
def restore_window(title_substring: str) -> dict:
    return extras.restore_window(title_substring)


@mcp.tool()
def list_processes(name_contains: Optional[str] = None) -> list[dict]:
    """List running processes, optionally filtered by name substring."""
    return extras.list_processes(name_contains)


@mcp.tool()
def kill_process(pid_or_name: str) -> dict:
    """Terminate a process by PID (string of digits) or by exe name."""
    return extras.kill_process(pid_or_name)


@mcp.tool()
def read_text_file(path: str, max_bytes: int = 200_000) -> dict:
    """Read a text file (up to max_bytes)."""
    return extras.read_text_file(path, max_bytes=max_bytes)


@mcp.tool()
def write_text_file(path: str, content: str, append: bool = False) -> dict:
    """Write or append to a text file."""
    return extras.write_text_file(path, content, append=append)


@mcp.tool()
def list_directory(path: str, include_hidden: bool = False) -> dict:
    """List entries in a directory."""
    return extras.list_directory(path, include_hidden=include_hidden)


@mcp.tool()
def delete_path(path: str, recursive: bool = False) -> dict:
    """Delete a file or (if recursive) a directory."""
    return extras.delete_path(path, recursive=recursive)


@mcp.tool()
def http_get(url: str, timeout_s: float = 15.0, max_bytes: int = 200_000) -> dict:
    """HTTP GET a URL and return body + status."""
    return extras.http_get(url, timeout_s=timeout_s, max_bytes=max_bytes)


@mcp.tool()
def download_file(url: str, dest_path: str, timeout_s: float = 60.0) -> dict:
    """Download a URL to a local file."""
    return extras.download_file(url, dest_path, timeout_s=timeout_s)


@mcp.tool()
def text_to_speech(text: str, rate: int = 0) -> dict:
    """Speak the text using the Windows SAPI voice. rate -10 (slow) .. +10 (fast)."""
    return extras.text_to_speech(text, rate=rate)


@mcp.tool()
def screenshot_to_file(path: str, monitor_index: int = 0) -> dict:
    """Save a screenshot directly to a PNG file."""
    return extras.screenshot_to_file(path, monitor_index=monitor_index)


@mcp.tool()
def lock_workstation() -> dict:
    """Lock the Windows session."""
    return extras.lock_workstation()


@mcp.tool()
def get_battery() -> dict:
    """Battery percent + plug status, or error on a desktop."""
    return extras.get_battery()


if __name__ == "__main__":
    mcp.run()
