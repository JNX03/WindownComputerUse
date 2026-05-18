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

_lock = threading.Lock()

STATE_PATH = permission.CONFIG_DIR / "state.json"

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


def set_virtual_cursor(x: int, y: int, pressed: Optional[bool] = None) -> None:
    fields: dict[str, Any] = {"virtual_cursor_x": int(x), "virtual_cursor_y": int(y)}
    if pressed is not None:
        fields["virtual_cursor_pressed"] = bool(pressed)
    patch(**fields)


def get_virtual_cursor() -> tuple[int, int]:
    s = load()
    return int(s.get("virtual_cursor_x", 0)), int(s.get("virtual_cursor_y", 0))


def set_pressed(on: bool) -> None:
    patch(virtual_cursor_pressed=bool(on))
