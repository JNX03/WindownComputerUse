"""Shared runtime state for overlay + manager + server.

state.json schema:
  agent_name        — current agent label shown on overlay
  cursor_color      — hex color of the overlay ring
  overlay_enabled   — whether the overlay should render itself
  last_action       — last tool call name (or null)
  last_action_args  — abbreviated arg dict
  last_action_at    — ISO timestamp
  emergency_stopped — bool, set by hotkey, blocks input tools
  server_pid        — PID of the MCP server process (overlay exits if it disappears)
  heartbeat_at      — ISO timestamp updated by server every 2s
"""
from __future__ import annotations
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from . import permission

import mmap
import struct

_lock = threading.Lock()

STATE_PATH = permission.CONFIG_DIR / "state.json"
CURSOR_POS_PATH = permission.CONFIG_DIR / "cursor_pos.bin"

# Binary IPC for the high-frequency cursor stream. A 24-byte fixed record
# (x:int32, y:int32, angle:float64, pressed:int32, version:int32) is mapped
# into both the server and overlay processes via mmap. Writes are in-place
# memcpys — no truncate, no encoding, no file locking — so the overlay never
# catches an empty/partial record. The version counter lets a reader detect
# a tear (writer mid-update) and retry.
_CURSOR_FMT = "<iidii"
_CURSOR_SIZE = struct.calcsize(_CURSOR_FMT)
_mm_cursor: Optional["mmap.mmap"] = None
_mm_lock = threading.Lock()

DEFAULT_STATE: dict[str, Any] = {
    "agent_name": "Claude",
    "cursor_color": "#3B82F6",
    "overlay_enabled": True,
    "last_action": None,
    "last_action_args": None,
    "last_action_at": None,
    "emergency_stopped": False,
    "server_pid": None,
    "heartbeat_at": None,
    # AI's virtual cursor — independent of the real Windows cursor.
    "virtual_cursor_x": 0,
    "virtual_cursor_y": 0,
    "virtual_cursor_angle_rad": 0.0,
    # Set to true briefly when a real click/drag is happening so the overlay
    # can render a "pressed" pulse.
    "virtual_cursor_pressed": False,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _read() -> dict[str, Any]:
    permission.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_PATH.exists():
        STATE_PATH.write_text(json.dumps(DEFAULT_STATE, indent=2), encoding="utf-8")
        return dict(DEFAULT_STATE)
    try:
        s = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        s = {}
    merged = dict(DEFAULT_STATE)
    merged.update(s)
    return merged


def _write(s: dict[str, Any]) -> None:
    permission.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Atomic write with retry — Windows os.replace can fail with PermissionError
    # if another thread/process has the destination open at that moment.
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(s, indent=2), encoding="utf-8")
    for attempt in range(6):
        try:
            os.replace(tmp, STATE_PATH)
            return
        except PermissionError:
            time.sleep(0.02 * (attempt + 1))
    # Last resort: write directly (non-atomic) so we don't crash callers.
    try:
        STATE_PATH.write_text(json.dumps(s, indent=2), encoding="utf-8")
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def load() -> dict[str, Any]:
    return _read()


def patch(**fields: Any) -> dict[str, Any]:
    with _lock:
        s = _read()
        s.update(fields)
        _write(s)
        return s


def set_current_action(tool: str, args: Optional[dict] = None) -> None:
    # Trim noisy args (base64 images, long text)
    safe: dict[str, Any] = {}
    if args:
        for k, v in args.items():
            if isinstance(v, str) and len(v) > 80:
                safe[k] = v[:77] + "..."
            elif isinstance(v, (bytes, bytearray)):
                safe[k] = f"<{len(v)} bytes>"
            else:
                safe[k] = v
    patch(last_action=tool, last_action_args=safe, last_action_at=_now())


def clear_current_action() -> None:
    patch(last_action=None, last_action_args=None)


def heartbeat(pid: int) -> None:
    patch(server_pid=pid, heartbeat_at=_now())


def sync_from_config() -> None:
    """Mirror config-driven fields (agent_name, cursor_color, overlay_enabled) into state."""
    cfg = permission.load_config()
    patch(
        agent_name=cfg.get("agent_name", "Claude"),
        cursor_color=cfg.get("cursor_color", "#3B82F6"),
        overlay_enabled=bool(cfg.get("overlay_enabled", True)),
    )


def set_emergency(on: bool) -> None:
    patch(emergency_stopped=bool(on))


def is_emergency() -> bool:
    return bool(load().get("emergency_stopped", False))


def set_virtual_cursor(x: int, y: int, pressed: Optional[bool] = None, angle_rad: Optional[float] = None) -> None:
    fields: dict[str, Any] = {"virtual_cursor_x": int(x), "virtual_cursor_y": int(y)}
    if pressed is not None:
        fields["virtual_cursor_pressed"] = bool(pressed)
    if angle_rad is not None:
        fields["virtual_cursor_angle_rad"] = float(angle_rad)
    patch(**fields)
    # Also mirror into the lightweight position file so the overlay (which
    # polls at ~25 Hz) always has a fresh, cheap-to-read value.
    cur_angle = float(angle_rad) if angle_rad is not None else 0.0
    cur_pressed = bool(pressed) if pressed is not None else False
    write_cursor_pos(int(x), int(y), cur_angle, cur_pressed)


def get_virtual_cursor() -> tuple[int, int]:
    s = load()
    return int(s.get("virtual_cursor_x", 0)), int(s.get("virtual_cursor_y", 0))


def set_pressed(on: bool) -> None:
    patch(virtual_cursor_pressed=bool(on))
    # Refresh the pressed bit in the lightweight position file too so the
    # overlay's pressed-ripple turns on/off without waiting for state.json.
    pos = read_cursor_pos()
    if pos is not None:
        x, y, angle, _ = pos
        write_cursor_pos(x, y, angle, bool(on))


# ---- Lightweight, high-frequency cursor position channel -----------------
#
# During an animation we update the AI cursor position up to ~90 times per
# second. Routing every one of those through state.json (atomic rename, retry
# loop, contention with the overlay reader) was the dominant source of jitter.
# Instead we keep a tiny plaintext side-file that's written with a single
# Path.write_text — overlay reads it cheaply.

def _cursor_mmap() -> Optional["mmap.mmap"]:
    """Open (and cache) the shared cursor-position mmap region."""
    global _mm_cursor
    if _mm_cursor is not None:
        return _mm_cursor
    with _mm_lock:
        if _mm_cursor is not None:
            return _mm_cursor
        try:
            permission.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            if not CURSOR_POS_PATH.exists() or CURSOR_POS_PATH.stat().st_size < _CURSOR_SIZE:
                # Pre-allocate the file at the exact record size.
                with open(CURSOR_POS_PATH, "wb") as f:
                    f.write(b"\x00" * _CURSOR_SIZE)
            f = open(CURSOR_POS_PATH, "r+b")
            _mm_cursor = mmap.mmap(f.fileno(), _CURSOR_SIZE)
        except OSError:
            _mm_cursor = None
    return _mm_cursor


_write_version = 0


def write_cursor_pos(x: int, y: int, angle_rad: float, pressed: bool) -> None:
    global _write_version
    mm = _cursor_mmap()
    if mm is None:
        return
    _write_version += 1
    try:
        struct.pack_into(
            _CURSOR_FMT, mm, 0,
            int(x), int(y), float(angle_rad), 1 if pressed else 0, int(_write_version),
        )
    except (ValueError, struct.error):
        # If the buffer is somehow invalid, drop the frame rather than crash.
        pass


def read_cursor_pos() -> Optional[tuple[int, int, float, bool]]:
    mm = _cursor_mmap()
    if mm is None:
        return None
    # Tear-detection: read the version, the record, then re-read the version.
    # If they differ, the writer updated mid-read — retry once. With mmap
    # writes being a single struct.pack_into (~50ns memcpy), a tear is
    # extremely rare, but the check is essentially free.
    try:
        x, y, ang, pressed, v1 = struct.unpack_from(_CURSOR_FMT, mm, 0)
        x2, y2, ang2, pressed2, v2 = struct.unpack_from(_CURSOR_FMT, mm, 0)
        if v1 != v2:
            x, y, ang, pressed = x2, y2, ang2, pressed2
    except (ValueError, struct.error):
        return None
    if v1 == 0 and v2 == 0 and x == 0 and y == 0:
        # Region is zeroed (no write has happened yet).
        return None
    return int(x), int(y), float(ang), bool(pressed)
